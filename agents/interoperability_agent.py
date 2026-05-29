"""AI agent for semantic interoperability orchestration via LiteLLM."""

from __future__ import annotations

import json
from typing import Any

from core.config import get_settings
from core.exceptions import AgentError
from core.logging import get_logger
from domain.concept import I14YConcept
from domain.mapping import FieldMapping, MappingPlan
from domain.schema import DatasetSchema

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are an expert in Swiss administrative data interoperability and the I14Y platform.
Your role is to help match dataset field names to official I14Y interoperability concepts.

When given a field name and a list of candidate concepts, you:
1. Select the best matching concept
2. Explain the reasoning briefly (1-2 sentences)
3. Assign a confidence score (0.0-1.0)

You understand Swiss government data standards: BFS numbers, AHV numbers, commune registers,
DCAT metadata vocabulary, and common data harmonisation patterns.

Respond ONLY with a valid JSON object:
{
  "concept_id": "...",
  "concept_name": "...",
  "confidence": 0.XX,
  "explanation": "..."
}"""


class InteroperabilityAgent:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = self._settings.llm_model

    async def enrich_mapping(
        self,
        field_name: str,
        candidates: list[I14YConcept],
        field_samples: list[str] | None = None,
    ) -> FieldMapping | None:
        """Ask LLM to pick the best concept for a low-confidence field."""
        if not candidates:
            return None

        candidates_text = "\n".join(
            f"- {c.id}: {c.name} — {c.description} (type: {c.data_type.value})"
            for c in candidates[:5]
        )
        samples_text = f"\nSample values: {', '.join(field_samples[:3])}" if field_samples else ""

        prompt = (
            f"Field name: '{field_name}'{samples_text}\n\n"
            f"Candidate I14Y concepts:\n{candidates_text}\n\n"
            "Which concept best matches this field? Respond with JSON only."
        )

        try:
            import litellm  # noqa: PLC0415

            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 256,
            }
            if self._settings.using_infomaniak:
                kwargs["api_base"] = self._settings.infomaniak_base_url
                kwargs["api_key"] = self._settings.infomaniak_api_key

            response = await litellm.acompletion(**kwargs)

            content = response.choices[0].message.content or ""
            data = _parse_json_response(content)

            concept = next((c for c in candidates if c.id == data.get("concept_id")), None)
            if concept is None:
                concept = next((c for c in candidates if c.name == data.get("concept_name")), None)
            if concept is None and candidates:
                concept = candidates[0]

            return FieldMapping(
                source_field=field_name,
                matched_concept=concept,
                confidence=float(data.get("confidence", 0.6)),
                method="llm",
                explanation=data.get("explanation"),
            )

        except Exception as exc:
            log.warning("agent_enrich_failed", field=field_name, model=self._model, error=str(exc))
            return None

    async def enrich_plan(
        self,
        plan: MappingPlan,
        concepts: list[I14YConcept],
        threshold: float = 0.70,
    ) -> MappingPlan:
        """Enrich low-confidence mappings with LLM assistance."""
        enriched: list[FieldMapping] = []
        for mapping in plan.mappings:
            if mapping.confidence < threshold and mapping.matched_concept:
                candidates = [mapping.matched_concept] + [
                    c for c in concepts if c != mapping.matched_concept
                ][:4]
                field_obj = next(
                    (f for f in plan.source_schema.fields if f.name == mapping.source_field), None
                )
                samples = field_obj.sample_values if field_obj else []
                improved = await self.enrich_mapping(mapping.source_field, candidates, samples)
                enriched.append(improved or mapping)
            else:
                enriched.append(mapping)
        return MappingPlan(source_schema=plan.source_schema, mappings=enriched)

    async def generate_explanation(self, plan: MappingPlan) -> str:
        """Generate a human-readable summary of a mapping plan."""
        accepted = plan.accepted_mappings()
        if not accepted:
            return "No mappings were found for this schema."

        lines = [
            f"- '{m.source_field}' → {m.matched_concept.name} "  # type: ignore[union-attr]
            f"(confidence: {m.confidence:.0%}, method: {m.method})"
            for m in accepted[:8]
        ]
        mapping_text = "\n".join(lines)

        prompt = (
            f"Schema: '{plan.source_schema.name}' ({plan.source_schema.row_count} rows)\n"
            f"Overall confidence: {plan.overall_confidence:.0%}\n"
            f"Mappings:\n{mapping_text}\n\n"
            "Write a 2-3 sentence summary explaining what this dataset contains and "
            "how well it maps to Swiss I14Y interoperability standards. Be concise."
        )

        try:
            import litellm  # noqa: PLC0415

            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 200,
            }
            if self._settings.using_infomaniak:
                kwargs["api_base"] = self._settings.infomaniak_base_url
                kwargs["api_key"] = self._settings.infomaniak_api_key

            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as exc:
            log.warning("agent_explanation_failed", error=str(exc))
            return f"Schema '{plan.source_schema.name}' mapped with {plan.overall_confidence:.0%} overall confidence."


def _parse_json_response(content: str) -> dict[str, Any]:
    content = content.strip()
    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return {}
