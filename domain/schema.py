from enum import Enum

import pandas as pd
from pydantic import BaseModel, Field


class DataType(str, Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    UNKNOWN = "UNKNOWN"


class SchemaField(BaseModel):
    name: str
    data_type: DataType
    sample_values: list[str] = Field(default_factory=list)
    nullable: bool = True


class DatasetSchema(BaseModel):
    name: str
    fields: list[SchemaField]
    row_count: int = 0

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, name: str) -> "DatasetSchema":
        fields: list[SchemaField] = []
        for col in df.columns:
            dtype = _infer_data_type(df[col])
            samples = [str(v) for v in df[col].dropna().head(3).tolist()]
            fields.append(SchemaField(name=col, data_type=dtype, sample_values=samples))
        return cls(name=name, fields=fields, row_count=len(df))


def _infer_data_type(series: pd.Series) -> DataType:
    dtype_str = str(series.dtype)
    if "int" in dtype_str:
        return DataType.INTEGER
    if "float" in dtype_str:
        return DataType.FLOAT
    if "bool" in dtype_str:
        return DataType.BOOLEAN
    if "datetime" in dtype_str:
        return DataType.DATE
    # Try to parse as date
    sample = series.dropna().head(5)
    if len(sample) > 0:
        try:
            pd.to_datetime(sample, format="mixed")
            return DataType.DATE
        except (ValueError, TypeError):
            pass
    return DataType.STRING
