from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_validation_engine
from domain.mapping import MappingPlan
from domain.transformation import ValidationReport
from services.validation import ValidationEngine

router = APIRouter()


class ValidateRequest(BaseModel):
    mapping: MappingPlan


@router.post("/validate", response_model=ValidationReport)
async def validate(
    body: ValidateRequest,
    engine: Annotated[ValidationEngine, Depends(get_validation_engine)],
) -> ValidationReport:
    return engine.validate(body.mapping)
