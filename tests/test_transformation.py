"""Tests for transformation engine."""

import pytest

from domain.concept import I14YConcept
from domain.mapping import FieldMapping, MappingPlan
from domain.schema import DataType, DatasetSchema, SchemaField
from domain.transformation import TransformationRule
from services.transformation import TransformationEngine, _cast_value


class TestTransformationEngine:
    @pytest.fixture
    def engine(self) -> TransformationEngine:
        return TransformationEngine()

    def test_generate_rename_plan(
        self, engine: TransformationEngine, sample_mapping_plan: MappingPlan
    ) -> None:
        plan = engine.generate_plan(sample_mapping_plan)
        # Only accepted mappings (with matched_concept) get rules
        accepted = [m for m in sample_mapping_plan.mappings if m.matched_concept]
        assert len(plan.rules) == len(accepted)

    def test_apply_rename(self, engine: TransformationEngine) -> None:
        schema = DatasetSchema(name="test", fields=[
            SchemaField(name="bfs_nr", data_type=DataType.INTEGER)
        ])
        concept = ImaginaryConcept()
        mapping = MappingPlan(
            source_schema=schema,
            mappings=[FieldMapping(
                source_field="bfs_nr",
                matched_concept=concept,
                confidence=0.9,
            )],
        )
        plan = engine.generate_plan(mapping)
        record = {"bfs_nr": 351, "extra": "keep"}
        transformed = engine.apply(record, plan)
        assert concept.name in transformed
        assert transformed[concept.name] == 351
        assert "bfs_nr" not in transformed
        assert transformed.get("extra") == "keep"

    def test_apply_cast_int(self, engine: TransformationEngine) -> None:
        from domain.transformation import TransformationPlan
        schema = DatasetSchema(name="t", fields=[SchemaField(name="pop", data_type=DataType.STRING)])
        rule = TransformationRule(
            operation="cast",
            source_field="pop",
            target_field="population",
            params={"to_type": "int"},
        )
        plan = TransformationPlan(rules=[rule], source_schema=schema)
        result = engine.apply({"pop": "12345"}, plan)
        assert result["population"] == 12345

    def test_apply_normalize(self, engine: TransformationEngine) -> None:
        from domain.transformation import TransformationPlan
        schema = DatasetSchema(name="t", fields=[SchemaField(name="city", data_type=DataType.STRING)])
        rule = TransformationRule(
            operation="normalize",
            source_field="city",
            target_field="city_normalized",
        )
        plan = TransformationPlan(rules=[rule], source_schema=schema)
        result = engine.apply({"city": "  ZÜRICH  "}, plan)
        assert result["city_normalized"] == "zürich"

    def test_apply_concat(self, engine: TransformationEngine) -> None:
        from domain.transformation import TransformationPlan
        schema = DatasetSchema(name="t", fields=[
            SchemaField(name="first", data_type=DataType.STRING),
            SchemaField(name="last", data_type=DataType.STRING),
        ])
        rule = TransformationRule(
            operation="concat",
            source_field="first",
            target_field="full_name",
            params={"other_field": "last", "sep": " "},
        )
        plan = TransformationPlan(rules=[rule], source_schema=schema)
        result = engine.apply({"first": "Anna", "last": "Müller"}, plan)
        assert result["full_name"] == "Anna Müller"

    def test_apply_batch(self, engine: TransformationEngine) -> None:
        from domain.transformation import TransformationPlan
        schema = DatasetSchema(name="t", fields=[SchemaField(name="x", data_type=DataType.STRING)])
        rule = TransformationRule(operation="rename", source_field="x", target_field="y")
        plan = TransformationPlan(rules=[rule], source_schema=schema)
        records = [{"x": 1}, {"x": 2}, {"x": 3}]
        results = engine.apply_batch(records, plan)
        assert len(results) == 3
        assert all(r["y"] in [1, 2, 3] for r in results)

    def test_missing_source_field_skipped(self, engine: TransformationEngine) -> None:
        from domain.transformation import TransformationPlan
        schema = DatasetSchema(name="t", fields=[])
        rule = TransformationRule(operation="rename", source_field="nonexistent", target_field="y")
        plan = TransformationPlan(rules=[rule], source_schema=schema)
        result = engine.apply({"other": "value"}, plan)
        assert "y" not in result
        assert result["other"] == "value"


class TestCastValue:
    def test_cast_to_int(self) -> None:
        assert _cast_value("42", {"to_type": "int"}) == 42
        assert _cast_value("42.9", {"to_type": "integer"}) == 42

    def test_cast_to_float(self) -> None:
        assert _cast_value("3.14", {"to_type": "float"}) == pytest.approx(3.14)

    def test_cast_none(self) -> None:
        assert _cast_value(None, {"to_type": "int"}) is None

    def test_cast_to_string(self) -> None:
        assert _cast_value(123, {"to_type": "string"}) == "123"


class ImaginaryConcept(I14YConcept):
    def __init__(self) -> None:
        super().__init__(
            id="bfs.municipality_number",
            name="BFS.MunicipalityNumber",
            description="BFS number",
            data_type=DataType.INTEGER,
        )
