from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeyValueItem:
    key: str
    value: str


@dataclass
class DocumentTable:
    headers: list[str]
    rows: list[list[str]]
    widths: list[float] | None = None


@dataclass
class DocumentSection:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    numbered: list[str] = field(default_factory=list)
    key_values: list[KeyValueItem] = field(default_factory=list)
    tables: list[DocumentTable] = field(default_factory=list)


@dataclass
class DocumentModel:
    title: str
    subtitle: str | None = None
    author: str = "RazaAI"
    organisation: str | None = None
    document_id: str | None = None
    version: str = "1.0"
    status: str = "Draft"
    classification: str = "Internal"
    created_date: str | None = None
    style: str = "professional"
    sections: list[DocumentSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self):
        if not self.title or not self.title.strip():
            raise ValueError("Document title is required")

        if not self.sections:
            raise ValueError("Document must contain at least one section")

        for section in self.sections:
            if not section.heading or not section.heading.strip():
                raise ValueError("Every section requires a heading")

            for table in section.tables:
                if not table.headers:
                    raise ValueError("Document table requires headers")

                expected = len(table.headers)

                for row in table.rows:
                    if len(row) != expected:
                        raise ValueError(
                            "Every table row must contain the same "
                            "number of cells as the headers"
                        )
