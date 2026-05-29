from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_transformation_engine
from domain.mapping import MappingPlan
from domain.transformation import TransformationPlan
from services.transformation import TransformationEngine

router = APIRouter()


class TransformRequest(BaseModel):
    mapping: MappingPlan
    records: list[dict[str, Any]]


class TransformResponse(BaseModel):
    transformed: list[dict[str, Any]]
    plan: TransformationPlan


@router.post("/transform", response_model=TransformResponse)
async def transform(
    body: TransformRequest,
    engine: Annotated[TransformationEngine, Depends(get_transformation_engine)],
) -> TransformResponse:
    plan = engine.generate_plan(body.mapping)
    transformed = engine.apply_batch(body.records, plan)
    return TransformResponse(transformed=transformed, plan=plan)
