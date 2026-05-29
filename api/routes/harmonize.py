"""Dataset harmonization endpoint — merges two OGD datasets via shared I14Y concepts."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import (
    get_comparison_service,
    get_concepts,
    get_schema_resolver,
    get_transformation_engine,
)
from api.routes.compare import _safe_resolve
from core.exceptions import ClosedDatasetError
from core.logging import get_logger
from domain.comparison import LampColor
from domain.concept import I14YConcept
from services.comparison import DatasetComparisonService
from services.schema_resolver import SchemaResolver
from services.transformation import TransformationEngine

log = get_logger(__name__)
router = APIRouter(tags=["harmonize"])


class HarmonizeRequest(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    output_format: Literal["csv", "json"] = "csv"


class HarmonizeMetadata(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    dataset_a_title: str
    dataset_b_title: str
    rows_a: int
    rows_b: int
    rows_merged: int
    columns_merged: int
    join_keys: list[str]
    overall_score: float
    lamp: str
    generated_at: str


@router.post("/harmonize")
async def harmonize_datasets(
    body: HarmonizeRequest,
    resolver: Annotated[SchemaResolver, Depends(get_schema_resolver)],
    comparison: Annotated[DatasetComparisonService, Depends(get_comparison_service)],
    transformation: Annotated[TransformationEngine, Depends(get_transformation_engine)],
    concepts: Annotated[list[I14YConcept], Depends(get_concepts)],
) -> StreamingResponse:
    """Merge two OGD datasets into a harmonized CSV or JSON file.

    1. Resolves schemas (with OGD fallback).
    2. Compares datasets — blocks if lamp is RED.
    3. Downloads distribution content via MCP.
    4. Applies transformation rules to normalize column names.
    5. Merges on shared I14Y concept keys.
    6. Streams the result with provenance metadata columns.
    """
    # ── Resolve schemas ────────────────────────────────────────────────────────
    schema_a, title_a, url_a, ogd_a = await _safe_resolve(body.dataset_a_id, resolver)
    schema_b, title_b, url_b, ogd_b = await _safe_resolve(body.dataset_b_id, resolver)

    if schema_a is None or not ogd_a:
        raise HTTPException(
            status_code=422,
            detail=f"Dataset A '{body.dataset_a_id}' n'a pas de distribution publique — harmonisation impossible.",
        )
    if schema_b is None or not ogd_b:
        raise HTTPException(
            status_code=422,
            detail=f"Dataset B '{body.dataset_b_id}' n'a pas de distribution publique — harmonisation impossible.",
        )

    # ── Compare ────────────────────────────────────────────────────────────────
    result = comparison.compare(
        schema_a, schema_b, concepts,
        dataset_a_id=body.dataset_a_id,
        dataset_b_id=body.dataset_b_id,
        dataset_a_title=title_a,
        dataset_b_title=title_b,
        dataset_a_ogd=ogd_a,
        dataset_b_ogd=ogd_b,
    )

    if result.lamp == LampColor.RED:
        raise HTTPException(
            status_code=422,
            detail=f"Datasets incompatibles (🔴 ROUGE, score {result.overall_score:.2f}): {result.explanation}",
        )

    if not result.join_candidates:
        raise HTTPException(
            status_code=422,
            detail="Aucune clé de jointure commune trouvée — fusion impossible.",
        )

    # ── Load distribution content ──────────────────────────────────────────────
    content_a = await _load_content(body.dataset_a_id, url_a, resolver)
    content_b = await _load_content(body.dataset_b_id, url_b, resolver)

    df_a = _parse_dataframe(content_a, body.dataset_a_id)
    df_b = _parse_dataframe(content_b, body.dataset_b_id)

    # ── Build mapping plans for transformation ─────────────────────────────────
    from services.mapping import MappingGenerationService  # noqa: PLC0415
    from services.matching import SemanticMatchingService  # noqa: PLC0415
    # We already have these via comparison service internals — rebuild lightweight
    source_plan, target_plan = comparison._mapping.generate_bridge_mapping(
        schema_a, schema_b, concepts
    )

    # ── Normalize column names towards I14Y concept names ─────────────────────
    plan_a = transformation.generate_plan(source_plan)
    plan_b = transformation.generate_plan(target_plan)

    df_a = _apply_plan_to_df(df_a, plan_a)
    df_b = _apply_plan_to_df(df_b, plan_b)

    # ── Determine join keys (shared concept names after normalization) ─────────
    join_keys = [fp.shared_concept_name for fp in result.join_candidates if fp.shared_concept_name]
    # Only keep join keys that actually exist in both DataFrames after normalization
    join_keys = [k for k in join_keys if k in df_a.columns and k in df_b.columns]

    if not join_keys:
        # Fallback: try the raw field names
        join_keys = [fp.source_field for fp in result.join_candidates if fp.source_field in df_a.columns and fp.source_field in df_b.columns]

    if not join_keys:
        raise HTTPException(
            status_code=422,
            detail="Les clés de jointure n'ont pas pu être normalisées dans les deux datasets.",
        )

    # ── Merge ─────────────────────────────────────────────────────────────────
    try:
        df_merged = pd.merge(df_a, df_b, on=join_keys, how="inner", suffixes=("_A", "_B"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur lors de la fusion: {exc}") from exc

    # ── Add provenance columns ─────────────────────────────────────────────────
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    df_merged["_source_a"] = body.dataset_a_id
    df_merged["_source_b"] = body.dataset_b_id
    df_merged["_merged_at"] = now_iso
    df_merged["_join_keys"] = ",".join(join_keys)
    df_merged["_score"] = result.overall_score

    meta = HarmonizeMetadata(
        dataset_a_id=body.dataset_a_id,
        dataset_b_id=body.dataset_b_id,
        dataset_a_title=title_a,
        dataset_b_title=title_b,
        rows_a=len(df_a),
        rows_b=len(df_b),
        rows_merged=len(df_merged),
        columns_merged=len(df_merged.columns),
        join_keys=join_keys,
        overall_score=result.overall_score,
        lamp=result.lamp.value,
        generated_at=now_iso,
    )

    log.info(
        "harmonize_done",
        rows_merged=meta.rows_merged,
        join_keys=join_keys,
        lamp=result.lamp.value,
        score=result.overall_score,
    )

    # ── Stream output ──────────────────────────────────────────────────────────
    if body.output_format == "json":
        records = df_merged.to_dict(orient="records")
        payload = json.dumps(
            {"metadata": meta.model_dump(), "data": records},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return StreamingResponse(
            iter([payload]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=harmonized.json"},
        )

    # Default: CSV
    csv_buffer = io.StringIO()
    # Write metadata as comments at the top
    csv_buffer.write(f"# semantic-bridge harmonized dataset\n")
    csv_buffer.write(f"# source_a: {body.dataset_a_id} ({title_a})\n")
    csv_buffer.write(f"# source_b: {body.dataset_b_id} ({title_b})\n")
    csv_buffer.write(f"# join_keys: {','.join(join_keys)}\n")
    csv_buffer.write(f"# score: {result.overall_score:.3f}  lamp: {result.lamp.value}\n")
    csv_buffer.write(f"# generated_at: {now_iso}\n")
    df_merged.to_csv(csv_buffer, index=False)

    return StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=harmonized.csv"},
    )


# ─── Private helpers ──────────────────────────────────────────────────────────


async def _load_content(dataset_id: str, url: str | None, resolver: SchemaResolver) -> bytes:
    """Load distribution content — reuse cached content from resolver if available."""
    if url:
        return await resolver.get_cached_content(url)
    # No URL means schema came from structured MCP — we need to find the distribution
    # Re-resolve to get the URL (will use schema cache hit path)
    try:
        _, _, download_url = await resolver.resolve(dataset_id)
        if download_url:
            return await resolver.get_cached_content(download_url)
    except Exception:
        pass
    raise HTTPException(
        status_code=422,
        detail=f"Dataset '{dataset_id}' n'a pas de contenu téléchargeable.",
    )


def _parse_dataframe(content: bytes, name_hint: str) -> pd.DataFrame:
    """Parse bytes to DataFrame (CSV or JSON)."""
    text = content.decode("utf-8", errors="replace")
    try:
        return pd.read_csv(io.StringIO(text), on_bad_lines="skip", sep=None, engine="python")
    except Exception:
        pass
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return pd.json_normalize(data)
        for key in ("data", "results", "records"):
            if isinstance(data.get(key), list):
                return pd.json_normalize(data[key])
    except Exception:
        pass
    raise HTTPException(
        status_code=422,
        detail=f"Dataset '{name_hint}' ne peut pas être parsé (format non reconnu).",
    )


def _apply_plan_to_df(df: pd.DataFrame, plan: object) -> pd.DataFrame:
    """Apply a TransformationPlan's rename rules to a DataFrame."""
    rename_map: dict[str, str] = {}
    for rule in getattr(plan, "rules", []):
        op = getattr(rule, "operation", "")
        src = getattr(rule, "source_field", "")
        tgt = getattr(rule, "target_field", "")
        if op in ("rename", "cast") and src in df.columns and src != tgt:
            rename_map[src] = tgt
    if rename_map:
        df = df.rename(columns=rename_map)
    return df
