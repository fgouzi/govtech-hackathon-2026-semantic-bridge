"""Domain models for dataset comparison results and mapping table suggestions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, computed_field


class LampColor(str, Enum):
    GREEN = "GREEN"
    ORANGE = "ORANGE"
    RED = "RED"

    @property
    def emoji(self) -> str:
        return {"GREEN": "✅", "ORANGE": "🟡", "RED": "🔴"}[self.value]

    @property
    def label_fr(self) -> str:
        return {"GREEN": "Compatible", "ORANGE": "Partiel", "RED": "Incompatible"}[self.value]


def compute_lamp(score: float, errors: int, warnings: int) -> LampColor:
    """Determine the validation lamp color from score and validation issue counts."""
    if score < 0.40 or errors > 2:
        return LampColor.RED
    if score >= 0.70 and errors == 0:
        return LampColor.GREEN
    # 0.40 <= score < 0.70 OR (errors > 0 AND errors <= 2)
    return LampColor.ORANGE


class FieldPair(BaseModel):
    """A matched pair of fields from two datasets sharing an I14Y concept."""

    source_field: str
    target_field: str
    shared_concept_name: str
    shared_concept_id: str
    confidence: float
    lamp: LampColor
    transformation_hint: str | None = None  # e.g. "cast INTEGER → STRING"


class MappingTableSuggestion(BaseModel):
    """Specification for a new I14Y mapping table row — ready to submit on i14y.admin.ch."""

    name: str  # proposed table name
    description: str
    source_concept_id: str
    source_concept_name: str
    target_concept_id: str
    target_concept_name: str
    source_field: str
    target_field: str
    transformation_rule: str  # human-readable, e.g. "rename" / "cast date → string"
    confidence: float


class ComparisonResult(BaseModel):
    """Full comparison result between two I14Y datasets."""

    dataset_a_id: str
    dataset_b_id: str
    dataset_a_title: str
    dataset_b_title: str
    dataset_a_ogd: bool = True   # False if closed/private
    dataset_b_ogd: bool = True

    overall_score: float
    lamp: LampColor

    join_candidates: list[FieldPair] = []
    unmapped_source: list[str] = []   # fields in A with no I14Y concept match
    unmapped_target: list[str] = []   # fields in B with no I14Y concept match

    validation_errors: int = 0
    validation_warnings: int = 0

    mapping_table_suggestion: list[MappingTableSuggestion] = []

    explanation: str = ""
    recommendation: str = ""

    @computed_field  # type: ignore[misc]
    @property
    def lamp_display(self) -> str:
        return f"{self.lamp.emoji} {self.lamp.label_fr} (score: {self.overall_score:.2f})"

    def to_chat_markdown(self) -> str:
        """Format the comparison result as a Markdown chat message."""
        lines: list[str] = []

        # Header
        lines.append(f"## {self.lamp.emoji} Comparaison: *{self.dataset_a_title}* vs *{self.dataset_b_title}*")
        lines.append("")
        lines.append(f"**Score global:** `{self.overall_score:.2f}` | **Statut:** {self.lamp.label_fr}")
        lines.append(f"**Erreurs:** {self.validation_errors} | **Avertissements:** {self.validation_warnings}")
        lines.append("")

        # Join candidates table
        if self.join_candidates:
            lines.append(f"### Clés de jointure trouvées ({len(self.join_candidates)})")
            lines.append("")
            lines.append("| Champ A | Champ B | Concept I14Y | Score | Statut |")
            lines.append("|---------|---------|--------------|-------|--------|")
            for fp in self.join_candidates:
                hint = f" *(→ {fp.transformation_hint})*" if fp.transformation_hint else ""
                lines.append(
                    f"| `{fp.source_field}` | `{fp.target_field}` | {fp.shared_concept_name}{hint}"
                    f" | {fp.confidence:.2f} | {fp.lamp.emoji} |"
                )
            lines.append("")

        # Unmapped fields
        if self.unmapped_source:
            lines.append(f"**Champs non mappés (Dataset A):** {', '.join(f'`{f}`' for f in self.unmapped_source)}")
        if self.unmapped_target:
            lines.append(f"**Champs non mappés (Dataset B):** {', '.join(f'`{f}`' for f in self.unmapped_target)}")
        if self.unmapped_source or self.unmapped_target:
            lines.append("")

        # Mapping table suggestion
        if self.mapping_table_suggestion:
            lines.append(f"### Table de mapping I14Y suggérée ({len(self.mapping_table_suggestion)} correspondances)")
            lines.append("")
            lines.append("| Concept A | Concept B | Transformation | Score |")
            lines.append("|-----------|-----------|----------------|-------|")
            for s in self.mapping_table_suggestion:
                lines.append(
                    f"| {s.source_concept_name} | {s.target_concept_name}"
                    f" | {s.transformation_rule} | {s.confidence:.2f} |"
                )
            lines.append("")
            lines.append(
                "> 💡 Cette table peut être soumise sur **https://www.i14y.admin.ch** "
                "pour enrichir le catalogue national de correspondances."
            )
            lines.append("")

        # Explanation
        if self.explanation:
            lines.append(f"**Analyse:** {self.explanation}")
            lines.append("")

        # Action hints
        if self.lamp in (LampColor.GREEN, LampColor.ORANGE):
            if not self.dataset_a_ogd or not self.dataset_b_ogd:
                lines.append(
                    "> ⚠️ Un ou plusieurs datasets n'ont pas de distribution publique — "
                    "l'harmonisation fichier n'est pas disponible."
                )
            else:
                lines.append(
                    "> ➡️ Tapez **`harmoniser`** pour générer le fichier CSV fusionné, "
                    "ou **`exporter table mapping`** pour télécharger la table de correspondances."
                )
        elif self.lamp == LampColor.RED:
            lines.append(f"> ❌ Fusion impossible. {self.recommendation}")

        return "\n".join(lines)
