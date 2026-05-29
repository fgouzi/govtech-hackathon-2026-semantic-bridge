"""Shared pytest fixtures."""

import pytest

from domain.concept import I14YConcept
from domain.mapping import FieldMapping, MappingPlan
from domain.schema import DataType, DatasetSchema, SchemaField


@pytest.fixture
def sample_concepts() -> list[I14YConcept]:
    return [
        I14YConcept(
            id="person.full_name",
            name="Person.FullName",
            description="Full name of a person",
            data_type=DataType.STRING,
            aliases=["full_name", "name", "display_name"],
        ),
        I14YConcept(
            id="person.date_of_birth",
            name="Person.DateOfBirth",
            description="Date of birth of a person",
            data_type=DataType.DATE,
            aliases=["birth_date", "dob", "date_naissance"],
        ),
        I14YConcept(
            id="address.postal_code",
            name="Address.PostalCode",
            description="Swiss postal code (PLZ)",
            data_type=DataType.INTEGER,
            aliases=["plz", "zip", "npa", "postal_code"],
        ),
        I14YConcept(
            id="address.municipality",
            name="Address.Municipality",
            description="Name of Swiss municipality",
            data_type=DataType.STRING,
            aliases=["gemeinde", "city", "municipality"],
        ),
        I14YConcept(
            id="bfs.municipality_number",
            name="BFS.MunicipalityNumber",
            description="Official BFS municipality number",
            data_type=DataType.INTEGER,
            aliases=["bfs_nr", "gemeinde_id", "municipality_id"],
        ),
    ]


@pytest.fixture
def sample_schema() -> DatasetSchema:
    return DatasetSchema(
        name="communes",
        fields=[
            SchemaField(name="bfs_nr", data_type=DataType.INTEGER, sample_values=["1", "2", "351"]),
            SchemaField(name="gemeinde_name", data_type=DataType.STRING, sample_values=["Zürich", "Bern"]),
            SchemaField(name="plz", data_type=DataType.INTEGER, sample_values=["8001", "3001"]),
            SchemaField(name="kanton_kuerzel", data_type=DataType.STRING, sample_values=["ZH", "BE"]),
        ],
        row_count=20,
    )


@pytest.fixture
def sample_mapping_plan(sample_schema: DatasetSchema, sample_concepts: list[I14YConcept]) -> MappingPlan:
    return MappingPlan(
        source_schema=sample_schema,
        mappings=[
            FieldMapping(
                source_field="bfs_nr",
                matched_concept=sample_concepts[4],
                confidence=0.92,
                method="embedding+lexical",
            ),
            FieldMapping(
                source_field="gemeinde_name",
                matched_concept=sample_concepts[3],
                confidence=0.88,
                method="embedding+lexical",
            ),
            FieldMapping(
                source_field="plz",
                matched_concept=sample_concepts[2],
                confidence=0.79,
                method="embedding+lexical",
            ),
            FieldMapping(
                source_field="kanton_kuerzel",
                matched_concept=None,
                confidence=0.35,
                method="heuristic",
            ),
        ],
    )
