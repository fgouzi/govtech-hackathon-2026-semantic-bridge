"""Domain models for SHACL shape-to-shape matching."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class SHACLProperty(BaseModel):
    """Represents a single sh:property node extracted from a SHACL shape."""

    path: str
    """sh:path — local name of the property (e.g. 'EGID', 'GKAT')."""

    datatype: str | None = None
    """sh:datatype — XSD datatype URI (e.g. 'xsd:integer')."""

    min_count: int = 0
    """sh:minCount — minimum cardinality (0 = optional)."""

    max_count: int | None = None
    """sh:maxCount — maximum cardinality (None = unbounded)."""

    name: str | None = None
    """sh:name — human-readable label (multilingual, FR preferred)."""

    description: str | None = None
    """sh:description — human-readable description."""

    @property
    def label(self) -> str:
        """Best display label: name > path."""
        return self.name or self.path

    @property
    def is_required(self) -> bool:
        return self.min_count > 0

    @property
    def is_single_valued(self) -> bool:
        return self.max_count == 1

    @property
    def xsd_type(self) -> str:
        """Normalised XSD local name (e.g. 'integer', 'string')."""
        if not self.datatype:
            return "unknown"
        return self.datatype.rsplit("#", 1)[-1].rsplit("/", 1)[-1].lower()


class SHACLShape(BaseModel):
    """A parsed SHACL NodeShape from an I14Y dataset."""

    dataset_id: str
    dataset_title: str = ""
    shape_uri: str = ""
    properties: list[SHACLProperty] = Field(default_factory=list)

    @property
    def property_count(self) -> int:
        return len(self.properties)

    @property
    def property_paths(self) -> set[str]:
        return {p.path for p in self.properties}


class SHACLPropertyMatch(BaseModel):
    """Match result between one property from shape A and one from shape B."""

    source_path: str
    target_path: str
    source_label: str
    target_label: str
    score: float
    """Combined score [0.0, 1.0]."""

    score_semantic: float
    """Embedding cosine similarity contribution."""

    score_lexical: float
    """rapidfuzz token_sort_ratio contribution."""

    score_structural: float
    """Structural compatibility (datatype + cardinality) contribution."""

    confidence_level: str
    """'high' ≥ 0.70 | 'medium' ≥ 0.50 | 'low' < 0.50"""

    @property
    def icon(self) -> str:
        if self.score >= 0.70:
            return "✅"
        if self.score >= 0.50:
            return "⚠️"
        return "❌"


class SHACLMatchPlan(BaseModel):
    """Full shape-to-shape matching result."""

    source_dataset_id: str
    target_dataset_id: str
    source_title: str = ""
    target_title: str = ""
    matches: list[SHACLPropertyMatch] = Field(default_factory=list)

    @computed_field  # type: ignore[misc]
    @property
    def overall_confidence(self) -> float:
        if not self.matches:
            return 0.0
        return round(sum(m.score for m in self.matches) / len(self.matches), 3)

    @computed_field  # type: ignore[misc]
    @property
    def high_confidence_count(self) -> int:
        return sum(1 for m in self.matches if m.score >= 0.70)

    @computed_field  # type: ignore[misc]
    @property
    def coverage(self) -> float:
        """Fraction of source properties with a high-confidence match."""
        if not self.matches:
            return 0.0
        return round(self.high_confidence_count / len(self.matches), 3)
