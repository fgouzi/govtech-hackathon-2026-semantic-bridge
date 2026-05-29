"""Dataset comparison and mapping table export endpoints."""

from __future__ import annotations

import csv
import io
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import (
    get_comparison_service,
    get_concepts,
    get_schema_resolver,
)
from core.exceptions import ClosedDatasetError
from core.logging import get_logger
from domain.comparison import ComparisonResult, LampColor
from domain.concept import I14YConcept
from services.comparison import DatasetComparisonService
from services.schema_resolver import SchemaResolver

log = get_logger(__name__)
router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    dataset_a_id: str
    dataset_b_id: str


class ExportMappingTableRequest(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    format: Literal["json", "csv"] = "json"


@router.post("/compare", response_model=ComparisonResult)
async def compare_datasets(
    body: CompareRequest,
    resolver: Annotated[SchemaResolver, Depends(get_schema_resolver)],
    comparison: Annotated[DatasetComparisonService, Depends(get_comparison_service)],
    concepts: Annotated[list[I14YConcept], Depends(get_concepts)],
) -> ComparisonResult:
    """Compare two I14Y datasets and return a compatibility score with lamp color.

    Automatically falls back to distribution content for OGD datasets without
    a structured schema. Returns RED lamp immediately for closed datasets.
    """
    # Resolve schema A
    schema_a, title_a, url_a, ogd_a = await _safe_resolve(body.dataset_a_id, resolver)
    if schema_a is None:
        return _closed_result(body.dataset_a_id, body.dataset_b_id, title_a, "?", label="A")

    # Resolve schema B
    schema_b, title_b, url_b, ogd_b = await _safe_resolve(body.dataset_b_id, resolver)
    if schema_b is None:
        return _closed_result(body.dataset_a_id, body.dataset_b_id, title_a, title_b, label="B")

    # Check schemas are not empty
    if not schema_a.fields or not schema_b.fields:
        empty = "A" if not schema_a.fields else "B"
        return _closed_result(
            body.dataset_a_id, body.dataset_b_id, title_a, title_b,
            label=empty, reason=f"Dataset {empty} has no parseable fields"
        )

    log.info(
        "compare_start",
        a=body.dataset_a_id, fields_a=len(schema_a.fields),
        b=body.dataset_b_id, fields_b=len(schema_b.fields),
    )

    result = comparison.compare(
        schema_a, schema_b, concepts,
        dataset_a_id=body.dataset_a_id,
        dataset_b_id=body.dataset_b_id,
        dataset_a_title=title_a,
        dataset_b_title=title_b,
        dataset_a_ogd=ogd_a,
        dataset_b_ogd=ogd_b,
    )

    log.info("compare_done", lamp=result.lamp, score=result.overall_score)
    return result


@router.post("/compare/export-mapping-table")
async def export_mapping_table(
    body: ExportMappingTableRequest,
    resolver: Annotated[SchemaResolver, Depends(get_schema_resolver)],
    comparison: Annotated[DatasetComparisonService, Depends(get_comparison_service)],
    concepts: Annotated[list[I14YConcept], Depends(get_concepts)],
) -> StreamingResponse:
    """Export the suggested I14Y mapping table as JSON or CSV.

    This table can be manually submitted on https://www.i14y.admin.ch
    to enrich the national interoperability catalogue.
    """
    compare_req = CompareRequest(dataset_a_id=body.dataset_a_id, dataset_b_id=body.dataset_b_id)
    result = await compare_datasets(compare_req, resolver, comparison, concepts)

    if not result.mapping_table_suggestion:
        raise HTTPException(
            status_code=404,
            detail="No mapping table suggestions generated — datasets may be directly compatible (no transformation needed).",
        )

    suggestions = result.mapping_table_suggestion

    if body.format == "json":
        payload = json.dumps(
            {
                "dataset_a": {"id": body.dataset_a_id, "title": result.dataset_a_title},
                "dataset_b": {"id": body.dataset_b_id, "title": result.dataset_b_title},
                "generated_by": "semantic-bridge",
                "submit_url": "https://www.i14y.admin.ch",
                "mappings": [s.model_dump() for s in suggestions],
            },
            ensure_ascii=False,
            indent=2,
        )
        return StreamingResponse(
            iter([payload]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=mapping_table_suggestion.json"},
        )

    # CSV format
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "name", "description",
            "source_concept_id", "source_concept_name",
            "target_concept_id", "target_concept_name",
            "source_field", "target_field",
            "transformation_rule", "confidence",
        ],
    )
    writer.writeheader()
    for s in suggestions:
        writer.writerow(s.model_dump())
    csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mapping_table_suggestion.csv"},
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _safe_resolve(
    dataset_id: str, resolver: SchemaResolver
) -> tuple[object | None, str, str | None, bool]:
    """Resolve schema, returning (None, title, url, ogd=False) on ClosedDatasetError."""
    try:
        schema, title, url = await resolver.resolve(dataset_id)
        return schema, title, url, True
    except ClosedDatasetError as exc:
        log.warning("dataset_closed", dataset_id=dataset_id, reason=exc.reason)
        return None, dataset_id, None, False
    except Exception as exc:
        log.error("schema_resolve_error", dataset_id=dataset_id, exc=str(exc))
        return None, dataset_id, None, False


def _closed_result(
    a_id: str, b_id: str, title_a: str, title_b: str,
    label: str = "A", reason: str = "No public distribution available"
) -> ComparisonResult:
    return ComparisonResult(
        dataset_a_id=a_id,
        dataset_b_id=b_id,
        dataset_a_title=title_a,
        dataset_b_title=title_b,
        dataset_a_ogd=label != "A",
        dataset_b_ogd=label != "B",
        overall_score=0.0,
        lamp=LampColor.RED,
        explanation=f"Dataset {label} non accessible publiquement: {reason}",
        recommendation="Seuls les datasets avec une distribution publique (OGD) peuvent être comparés.",
    )
