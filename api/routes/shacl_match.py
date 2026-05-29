"""POST /shacl-match — Shape-to-shape matching between two I14Y datasets."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_shacl_matcher
from domain.shacl_shape import SHACLMatchPlan
from services.shacl_matching import SHACLShapeMatcher

router = APIRouter()


class SHACLMatchRequest(BaseModel):
    source_dataset_id: str
    """I14Y dataset UUID or identifier for the source shape."""

    target_dataset_id: str
    """I14Y dataset UUID or identifier for the target shape."""


@router.post("/shacl-match", response_model=SHACLMatchPlan)
async def shacl_match(
    body: SHACLMatchRequest,
    matcher: Annotated[SHACLShapeMatcher, Depends(get_shacl_matcher)],
) -> SHACLMatchPlan:
    """Compare SHACL shapes of two I14Y datasets field-by-field.

    Combines semantic embedding similarity, lexical fuzzy matching,
    and structural constraint compatibility (datatype + cardinality).
    """
    return await matcher.match(body.source_dataset_id, body.target_dataset_id)
