from pydantic import BaseModel

from domain.schema import DataType


class I14YConcept(BaseModel):
    id: str
    name: str
    description: str
    data_type: DataType = DataType.UNKNOWN
    uri: str = ""
    category: str = ""
    aliases: list[str] = []

    @property
    def searchable_text(self) -> str:
        parts = [self.name, self.description] + self.aliases
        return " ".join(parts)
