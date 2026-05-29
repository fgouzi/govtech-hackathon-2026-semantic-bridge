from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.interoperability_agent import InteroperabilityAgent
from api.dependencies import get_agent, get_concepts, get_matching_service
from domain.concept import I14YConcept
from domain.mapping import MappingPlan
from domain.schema import DatasetSchema
from services.matching import SemanticMatchingService

router = APIRouter()


class MatchRequest(BaseModel):
    schema_: DatasetSchema
    use_ai: bool = True

    model_config = {"populate_by_name": True}


@router.post("/match", response_model=MappingPlan)
async def match_schema(
    body: MatchRequest,
    matching: Annotated[SemanticMatchingService, Depends(get_matching_service)],
    concepts: Annotated[list[I14YConcept], Depends(get_concepts)],
    agent: Annotated[InteroperabilityAgent, Depends(get_agent)],
) -> MappingPlan:
    plan = matching.match_schema(body.schema_, concepts)
    if body.use_ai:
        plan = await agent.enrich_plan(plan, concepts)
    return plan
