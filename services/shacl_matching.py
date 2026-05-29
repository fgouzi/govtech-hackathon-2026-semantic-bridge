"""SHACL shape-to-shape matching service.

Pipeline:
1. Fetch I14Y dataset JSON-LD via the public API (direct httpx — no MCP needed)
2. Parse with rdflib to extract sh:property nodes
3. Score each property pair:
   - 0.60 × cosine(embed_A, embed_B)   [sentence-transformers / FAISS]
   - 0.30 × token_sort_ratio(name_A, name_B)  [rapidfuzz]
   - 0.10 × structural_compat(dtype, cardinality)
4. Return SHACLMatchPlan with ranked matches
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import numpy as np
from rapidfuzz import fuzz
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from core.logging import get_logger
from domain.shacl_shape import (
    SHACLMatchPlan,
    SHACLProperty,
    SHACLPropertyMatch,
    SHACLShape,
)
from services.embedding import EmbeddingService

log = get_logger(__name__)

SH = Namespace("http://www.w3.org/ns/shacl#")

_WEIGHT_SEMANTIC = 0.60
_WEIGHT_LEXICAL = 0.30
_WEIGHT_STRUCTURAL = 0.10

_I14Y_API = "https://api.i14y.admin.ch/api/public/v1"

# XSD types considered compatible for structural scoring
_TYPE_COMPAT: dict[str, set[str]] = {
    "string": {"string", "anyuri", "langstring", "unknown"},
    "integer": {"integer", "int", "long", "short", "nonnegativeinteger", "float", "decimal", "unknown"},
    "float": {"float", "double", "decimal", "integer", "unknown"},
    "decimal": {"decimal", "float", "double", "integer", "unknown"},
    "date": {"date", "datetime", "gyear", "string", "unknown"},
    "datetime": {"datetime", "date", "string", "unknown"},
    "boolean": {"boolean", "unknown"},
    "unknown": set(),  # matches anything
}


def _type_compat_score(type_a: str, type_b: str) -> float:
    """Return 1.0 if types are compatible, 0.3 otherwise."""
    if type_a == "unknown" or type_b == "unknown":
        return 0.7
    compat = _TYPE_COMPAT.get(type_a, set())
    return 1.0 if type_b in compat else 0.3


def _cardinality_compat_score(prop_a: SHACLProperty, prop_b: SHACLProperty) -> float:
    """Bonus when both properties have the same required/optional status."""
    if prop_a.is_required == prop_b.is_required:
        return 1.0
    return 0.7


def _structural_score(prop_a: SHACLProperty, prop_b: SHACLProperty) -> float:
    type_s = _type_compat_score(prop_a.xsd_type, prop_b.xsd_type)
    card_s = _cardinality_compat_score(prop_a, prop_b)
    return round((type_s + card_s) / 2.0, 3)


def _extract_multilang(graph: Graph, node: Any, predicate: Any, langs: tuple[str, ...] = ("fr", "de", "en")) -> str | None:
    """Extract first matching language value from a multilingual literal."""
    values: dict[str, str] = {}
    for obj in graph.objects(node, predicate):
        if isinstance(obj, Literal):
            lang = obj.language or ""
            values[lang] = str(obj)
    for lang in langs:
        if lang in values:
            return values[lang]
    # Fallback: any value
    return next(iter(values.values()), None)


def _parse_shacl_graph(graph: Graph, dataset_id: str, dataset_title: str) -> SHACLShape:
    """Extract sh:property nodes from a parsed rdflib Graph."""
    properties: list[SHACLProperty] = []

    # Find NodeShapes (sh:NodeShape or subjects of sh:property)
    shape_nodes: set[Any] = set()
    for s in graph.subjects(RDF.type, SH.NodeShape):
        shape_nodes.add(s)
    # Also find any subject that has sh:property (implicit NodeShape)
    for s in graph.subjects(SH.property, None):
        shape_nodes.add(s)

    shape_uri = str(next(iter(shape_nodes), ""))

    seen_paths: set[str] = set()
    for shape_node in shape_nodes:
        for prop_shape in graph.objects(shape_node, SH.property):
            # Extract sh:path
            path_node = graph.value(prop_shape, SH.path)
            if path_node is None:
                continue
            path_str = str(path_node).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            # sh:datatype
            datatype_node = graph.value(prop_shape, SH.datatype)
            datatype = str(datatype_node) if datatype_node else None

            # sh:minCount / sh:maxCount
            min_count_node = graph.value(prop_shape, SH.minCount)
            max_count_node = graph.value(prop_shape, SH.maxCount)
            min_count = int(str(min_count_node)) if min_count_node is not None else 0
            max_count = int(str(max_count_node)) if max_count_node is not None else None

            # sh:name (multilingual label)
            name = _extract_multilang(graph, prop_shape, SH.name)
            # sh:description
            description = _extract_multilang(graph, prop_shape, SH.description)

            properties.append(
                SHACLProperty(
                    path=path_str,
                    datatype=datatype,
                    min_count=min_count,
                    max_count=max_count,
                    name=name,
                    description=description,
                )
            )

    log.info("shacl_shape_parsed", dataset_id=dataset_id, property_count=len(properties))
    return SHACLShape(
        dataset_id=dataset_id,
        dataset_title=dataset_title,
        shape_uri=shape_uri,
        properties=properties,
    )


async def _fetch_dataset_title(client: httpx.AsyncClient, dataset_id: str) -> str:
    """Fetch dataset title from I14Y public API."""
    try:
        resp = await client.get(f"{_I14Y_API}/datasets/{dataset_id}")
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            title = data.get("title", {})
            if isinstance(title, dict):
                return title.get("fr") or title.get("de") or title.get("en") or dataset_id
    except Exception as exc:
        log.warning("fetch_dataset_title_failed", dataset_id=dataset_id, error=str(exc))
    return dataset_id


async def _fetch_shacl_shape(
    client: httpx.AsyncClient, dataset_id: str, dataset_title: str
) -> SHACLShape | None:
    """Fetch and parse SHACL shape from I14Y JSON-LD export."""
    # Try the JSON-LD structure endpoint
    url = f"{_I14Y_API}/datasets/{dataset_id}/structures/exports/JsonLd"
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            log.warning("shacl_fetch_failed", dataset_id=dataset_id, status=resp.status_code)
            return None

        raw = resp.text
        graph = Graph()
        graph.parse(data=raw, format="json-ld")

        if len(graph) == 0:
            log.warning("shacl_graph_empty", dataset_id=dataset_id)
            return None

        return _parse_shacl_graph(graph, dataset_id, dataset_title)

    except Exception as exc:
        log.warning("shacl_parse_failed", dataset_id=dataset_id, error=str(exc))
        return None


def _build_shape_from_metadata(dataset_id: str, dataset_title: str, concepts_raw: list[dict]) -> SHACLShape:
    """Fallback: build a synthetic SHACLShape from I14Y concept keywords when JSON-LD is unavailable."""
    properties: list[SHACLProperty] = []
    for raw in concepts_raw:
        name_obj = raw.get("name", {})
        name = (
            name_obj.get("fr") or name_obj.get("de") or name_obj.get("en", "")
            if isinstance(name_obj, dict) else str(name_obj)
        )
        desc_obj = raw.get("description", {})
        desc = (
            desc_obj.get("fr") or desc_obj.get("de") or desc_obj.get("en", "")
            if isinstance(desc_obj, dict) else str(desc_obj)
        )
        identifier = raw.get("identifier", raw.get("id", ""))
        ctype = raw.get("codeListEntryValueType", raw.get("conceptType", ""))
        xsd_map = {"String": "xsd:string", "Integer": "xsd:integer", "Date": "xsd:date"}
        datatype = xsd_map.get(ctype)

        properties.append(
            SHACLProperty(
                path=identifier,
                datatype=datatype,
                name=name,
                description=desc[:300] if desc else None,
            )
        )

    return SHACLShape(
        dataset_id=dataset_id,
        dataset_title=dataset_title,
        properties=properties,
    )


class SHACLShapeMatcher:
    """Matches two SHACL shapes from I14Y datasets using semantic + structural scoring."""

    def __init__(self, embedding_service: EmbeddingService) -> None:
        self._embeddings = embedding_service

    async def fetch_shape(self, dataset_id: str) -> SHACLShape | None:
        """Fetch and parse the SHACL shape for an I14Y dataset."""
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            title = await _fetch_dataset_title(client, dataset_id)
            shape = await _fetch_shacl_shape(client, dataset_id, title)
            return shape

    async def match(
        self,
        source_id: str,
        target_id: str,
        source_shape: SHACLShape | None = None,
        target_shape: SHACLShape | None = None,
    ) -> SHACLMatchPlan:
        """Perform shape-to-shape matching. Fetches shapes if not provided."""
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            if source_shape is None:
                src_title = await _fetch_dataset_title(client, source_id)
                source_shape = await _fetch_shacl_shape(client, source_id, src_title)
            if target_shape is None:
                tgt_title = await _fetch_dataset_title(client, target_id)
                target_shape = await _fetch_shacl_shape(client, target_id, tgt_title)

        if source_shape is None or target_shape is None:
            log.warning(
                "shacl_match_missing_shape",
                source_available=source_shape is not None,
                target_available=target_shape is not None,
            )
            return SHACLMatchPlan(
                source_dataset_id=source_id,
                target_dataset_id=target_id,
                source_title=source_shape.dataset_title if source_shape else source_id,
                target_title=target_shape.dataset_title if target_shape else target_id,
                matches=[],
            )

        matches = self._score_properties(source_shape, target_shape)

        return SHACLMatchPlan(
            source_dataset_id=source_id,
            target_dataset_id=target_id,
            source_title=source_shape.dataset_title,
            target_title=target_shape.dataset_title,
            matches=matches,
        )

    def _score_properties(
        self,
        source: SHACLShape,
        target: SHACLShape,
    ) -> list[SHACLPropertyMatch]:
        """For each source property, find the best-matching target property."""
        if not source.properties or not target.properties:
            return []

        src_labels = [p.label for p in source.properties]
        tgt_labels = [p.label for p in target.properties]

        # Encode all labels at once (batch is more efficient)
        all_labels = src_labels + tgt_labels
        try:
            all_vectors = self._embeddings.encode(all_labels)
            src_vecs = all_vectors[: len(src_labels)]
            tgt_vecs = all_vectors[len(src_labels):]
        except Exception as exc:
            log.warning("shacl_embedding_failed", error=str(exc))
            # Fallback: zero vectors (lexical + structural only)
            dim = 384
            src_vecs = np.zeros((len(src_labels), dim), dtype=np.float32)
            tgt_vecs = np.zeros((len(tgt_labels), dim), dtype=np.float32)

        # Cosine similarity matrix (already normalized by encode())
        sim_matrix = src_vecs @ tgt_vecs.T  # shape: (n_src, n_tgt)

        matches: list[SHACLPropertyMatch] = []
        for i, src_prop in enumerate(source.properties):
            best_j = int(np.argmax(sim_matrix[i]))
            tgt_prop = target.properties[best_j]

            sem_score = float(sim_matrix[i, best_j])
            sem_score = max(0.0, min(1.0, sem_score))

            lex_score = fuzz.token_sort_ratio(
                src_prop.label.lower().replace("_", " "),
                tgt_prop.label.lower().replace("_", " "),
            ) / 100.0

            struct_score = _structural_score(src_prop, tgt_prop)

            combined = (
                _WEIGHT_SEMANTIC * sem_score
                + _WEIGHT_LEXICAL * lex_score
                + _WEIGHT_STRUCTURAL * struct_score
            )
            combined = round(combined, 3)

            confidence_level = (
                "high" if combined >= 0.70 else "medium" if combined >= 0.50 else "low"
            )

            matches.append(
                SHACLPropertyMatch(
                    source_path=src_prop.path,
                    target_path=tgt_prop.path,
                    source_label=src_prop.label,
                    target_label=tgt_prop.label,
                    score=combined,
                    score_semantic=round(sem_score, 3),
                    score_lexical=round(lex_score, 3),
                    score_structural=round(struct_score, 3),
                    confidence_level=confidence_level,
                )
            )

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches
