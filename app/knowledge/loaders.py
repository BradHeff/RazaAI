from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import SUPPORTED_EXTENSIONS
from .metadata import load_source_metadata
from .chunking import chunk_markdown_incidents


def load_document(path: Path):
    """Extract a document into logical sections."""

    path = Path(path)
    extension = path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported knowledge file type: {extension}"
        )

    metadata = load_source_metadata(path)
    sections = []

    if extension in {".md", ".markdown"}:
        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        incident_chunks = chunk_markdown_incidents(
            text
        )

        for record in incident_chunks:
            sections.append({
                "text": record["text"],
                "page": None,
                "heading": record["heading"],
                "heading_level": record["heading_level"],
                "incident_part": record["part"],
                "pre_chunked": True,
            })

    elif extension == ".txt":
        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        sections.append({
            "text": text,
            "page": None,
            "heading": None,
            "heading_level": None,
            "incident_part": None,
            "pre_chunked": False,
        })

    elif extension in {".html", ".htm"}:
        raw = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        soup = BeautifulSoup(raw, "html.parser")

        for element in soup(
            ["script", "style", "noscript"]
        ):
            element.decompose()

        sections.append({
            "text": soup.get_text("\n", strip=True),
            "page": None,
            "heading": None,
            "heading_level": None,
            "incident_part": None,
            "pre_chunked": False,
        })

    elif extension == ".pdf":
        reader = PdfReader(str(path))
        metadata["page_count"] = len(reader.pages)

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            text = page.extract_text() or ""

            if text.strip():
                sections.append({
                    "text": text,
                    "page": page_number,
                    "heading": None,
                    "heading_level": None,
                    "incident_part": None,
                    "pre_chunked": False,
                })

    return {
        "metadata": metadata,
        "sections": sections,
    }
