"""Dataset comparison service — orchestrates matching, validation and scoring."""

from __future__ import annotations

from domain.comparison import (
    ComparisonResult,
    FieldPair,
    LampColor,
    MappingTableSuggestion,
    compute_lamp,
)
from domain.concept import I14YConcept
from domain.mapping import MappingPlan
from domain.schema import DatasetSchema
from services.mapping import MappingGenerationService
from services.validation import ValidationEngine

_FIELD_LAMP_GREEN = 0.70
_FIELD_LAMP_ORANGE = 0.50


class DatasetComparisonService:
    """Compare two DatasetSchemas via shared I14Y concepts."""

    def __init__(
        self,
        mapping_service: MappingGenerationService,
        validation_engine: ValidationEngine,
    ) -> None:
        self._mapping = mapping_service
        self._validation = validation_engine

    def compare(
        self,
        schema_a: DatasetSchema,
        schema_b: DatasetSchema,
        concepts: list[I14YConcept],
        dataset_a_id: str = "",
        dataset_b_id: str = "",
        dataset_a_title: str = "",
        dataset_b_title: str = "",
        dataset_a_ogd: bool = True,
        dataset_b_ogd: bool = True,
    ) -> ComparisonResult:
        """Run full comparison and return a ComparisonResult with lamp color."""
        # Step 1 — Map both schemas to I14Y concepts
        source_plan, target_plan = self._mapping.generate_bridge_mapping(
            schema_a, schema_b, concepts
        )

        # Step 2 — Find fields sharing a common concept (join candidates)
        raw_candidates = self._mapping.find_join_candidates(source_plan, target_plan)

        # Step 3 — Validate source plan
        val_report = self._validation.validate(source_plan)
        errors = len(val_report.errors)
        warnings = len(val_report.warnings)

        # Step 4 — Overall score
        overall_score = round(
            (source_plan.overall_confidence + target_plan.overall_confidence) / 2, 3
        )

        # Step 5 — Build FieldPair list
        join_candidates = _build_field_pairs(source_plan, target_plan, raw_candidates)

        # Step 6 — Collect unmapped fields
        unmapped_source = source_plan.unmatched_fields()
        unmapped_target = target_plan.unmatched_fields()

        # Step 7 — Suggest mapping table rows for ORANGE pairs (transformation needed)
        mapping_table_suggestion = _build_mapping_table_suggestions(
            source_plan, target_plan, raw_candidates
        )

        # Step 8 — Global lamp
        lamp = compute_lamp(overall_score, errors, warnings)

        # Step 9 — Natural language explanation
        explanation, recommendation = _build_explanation(
            lamp, overall_score, join_candidates, unmapped_source, unmapped_target,
            dataset_a_title or dataset_a_id, dataset_b_title or dataset_b_id,
            dataset_a_ogd, dataset_b_ogd,
        )

        return ComparisonResult(
            dataset_a_id=dataset_a_id,
            dataset_b_id=dataset_b_id,
            dataset_a_title=dataset_a_title or dataset_a_id,
            dataset_b_title=dataset_b_title or dataset_b_id,
            dataset_a_ogd=dataset_a_ogd,
            dataset_b_ogd=dataset_b_ogd,
            overall_score=overall_score,
            lamp=lamp,
            join_candidates=join_candidates,
            unmapped_source=unmapped_source,
            unmapped_target=unmapped_target,
            validation_errors=errors,
            validation_warnings=warnings,
            mapping_table_suggestion=mapping_table_suggestion,
            explanation=explanation,
            recommendation=recommendation,
        )


# ─── Private helpers ──────────────────────────────────────────────────────────


def _build_field_pairs(
    source_plan: MappingPlan,
    target_plan: MappingPlan,
    raw_candidates: list[tuple[str, str, str]],
) -> list[FieldPair]:
    """Build FieldPair objects with per-field lamp colors."""
    # Index source and target mappings by concept id for fast lookup
    source_by_concept = {
        m.matched_concept.id: m
        for m in source_plan.accepted_mappings()
        if m.matched_concept
    }
    target_by_concept = {
        m.matched_concept.id: m
        for m in target_plan.accepted_mappings()
        if m.matched_concept
    }

    pairs: list[FieldPair] = []
    for src_field, tgt_field, concept_name in raw_candidates:
        # Find confidence for this pair (average of both sides)
        src_mapping = next(
            (m for m in source_plan.accepted_mappings() if m.source_field == src_field), None
        )
        tgt_mapping = next(
            (m for m in target_plan.accepted_mappings() if m.source_field == tgt_field), None
        )

        src_conf = src_mapping.confidence if src_mapping else 0.5
        tgt_conf = tgt_mapping.confidence if tgt_mapping else 0.5
        pair_conf = round((src_conf + tgt_conf) / 2, 3)

        # Per-field lamp
        if pair_conf >= _FIELD_LAMP_GREEN:
            field_lamp = LampColor.GREEN
        elif pair_conf >= _FIELD_LAMP_ORANGE:
            field_lamp = LampColor.ORANGE
        else:
            field_lamp = LampColor.RED

        # Detect transformation hint
        transformation_hint = _detect_transformation(src_mapping, tgt_mapping)

        # Get shared concept id
        concept_id = ""
        if src_mapping and src_mapping.matched_concept:
            concept_id = src_mapping.matched_concept.id

        pairs.append(FieldPair(
            source_field=src_field,
            target_field=tgt_field,
            shared_concept_name=concept_name,
            shared_concept_id=concept_id,
            confidence=pair_conf,
            lamp=field_lamp,
            transformation_hint=transformation_hint,
        ))

    # Sort: GREEN first, then ORANGE, then RED, then by confidence desc
    pairs.sort(key=lambda p: (p.lamp.value, -p.confidence))
    return pairs


def _detect_transformation(src_mapping: object | None, tgt_mapping: object | None) -> str | None:
    """Return a human-readable transformation hint if types differ."""
    if src_mapping is None or tgt_mapping is None:
        return None
    src_concept = getattr(src_mapping, "matched_concept", None)
    tgt_concept = getattr(tgt_mapping, "matched_concept", None)
    if src_concept and tgt_concept and src_concept.data_type != tgt_concept.data_type:
        return f"{src_concept.data_type.value} → {tgt_concept.data_type.value}"
    return None


def _build_mapping_table_suggestions(
    source_plan: MappingPlan,
    target_plan: MappingPlan,
    raw_candidates: list[tuple[str, str, str]],
) -> list[MappingTableSuggestion]:
    """Generate I14Y mapping table suggestions for pairs that need transformation."""
    suggestions: list[MappingTableSuggestion] = []
    seen: set[tuple[str, str]] = set()

    for src_field, tgt_field, concept_name in raw_candidates:
        src_mapping = next(
            (m for m in source_plan.accepted_mappings() if m.source_field == src_field), None
        )
        tgt_mapping = next(
            (m for m in target_plan.accepted_mappings() if m.source_field == tgt_field), None
        )

        if not src_mapping or not tgt_mapping:
            continue
        if not src_mapping.matched_concept or not tgt_mapping.matched_concept:
            continue

        src_concept = src_mapping.matched_concept
        tgt_concept = tgt_mapping.matched_concept

        # Only suggest if concepts differ (mapping table needed) or types differ
        concepts_differ = src_concept.id != tgt_concept.id
        types_differ = src_concept.data_type != tgt_concept.data_type
        if not concepts_differ and not types_differ:
            continue

        key = (src_concept.id, tgt_concept.id)
        if key in seen:
            continue
        seen.add(key)

        # Determine transformation rule
        if types_differ:
            rule = f"cast {src_concept.data_type.value} → {tgt_concept.data_type.value}"
        else:
            rule = "rename"  # same type, different concept name

        avg_confidence = round((src_mapping.confidence + tgt_mapping.confidence) / 2, 3)

        suggestions.append(MappingTableSuggestion(
            name=f"Mapping_{src_concept.name}_to_{tgt_concept.name}",
            description=(
                f"Correspondance entre le concept '{src_concept.name}' (dataset A) "
                f"et '{tgt_concept.name}' (dataset B)"
            ),
            source_concept_id=src_concept.id,
            source_concept_name=src_concept.name,
            target_concept_id=tgt_concept.id,
            target_concept_name=tgt_concept.name,
            source_field=src_field,
            target_field=tgt_field,
            transformation_rule=rule,
            confidence=avg_confidence,
        ))

    return suggestions


def _build_explanation(
    lamp: LampColor,
    score: float,
    join_candidates: list[FieldPair],
    unmapped_source: list[str],
    unmapped_target: list[str],
    title_a: str,
    title_b: str,
    ogd_a: bool,
    ogd_b: bool,
) -> tuple[str, str]:
    """Generate human-readable explanation and recommendation."""
    n_keys = len(join_candidates)
    n_green = sum(1 for p in join_candidates if p.lamp == LampColor.GREEN)
    n_orange = sum(1 for p in join_candidates if p.lamp == LampColor.ORANGE)

    if lamp == LampColor.GREEN:
        explanation = (
            f"{n_keys} clé(s) de jointure trouvée(s) entre les deux datasets "
            f"(dont {n_green} correspondance(s) directe(s)). "
            f"Score de compatibilité: {score:.2f}."
        )
        recommendation = (
            f"Les datasets '{title_a}' et '{title_b}' peuvent être fusionnés directement. "
            "Tapez `harmoniser` pour générer le fichier CSV résultant."
        )
    elif lamp == LampColor.ORANGE:
        explanation = (
            f"{n_keys} clé(s) de jointure trouvée(s) "
            f"({n_orange} nécessitant une transformation). "
            f"Score: {score:.2f}."
        )
        recommendation = (
            "Une correction ou transformation est nécessaire pour certains champs. "
            "Tapez `exporter table mapping` pour obtenir les correspondances suggérées, "
            "puis `harmoniser` pour générer le fichier."
        )
    else:  # RED
        if not ogd_a or not ogd_b:
            closed = []
            if not ogd_a:
                closed.append(f"'{title_a}'")
            if not ogd_b:
                closed.append(f"'{title_b}'")
            explanation = (
                f"Le(s) dataset(s) {', '.join(closed)} n'ont pas de distribution publique."
            )
        elif n_keys == 0:
            explanation = (
                f"Aucune clé de jointure commune trouvée entre les deux datasets. "
                f"Score: {score:.2f}."
            )
        else:
            explanation = (
                f"Trop d'incompatibilités structurelles pour une fusion fiable. "
                f"Score: {score:.2f}."
            )
        recommendation = (
            "La fusion n'est pas possible avec les données actuelles. "
            "Consultez les champs non mappés pour identifier les problèmes."
        )

    return explanation, recommendation
