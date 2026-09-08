import json
from pathlib import Path

from .config import KNOWLEDGE_DIR


def _sidecar_path(path: Path) -> Path:
    return Path(str(path) + ".meta.json")


def infer_category(path: Path):
    try:
        relative = path.resolve().relative_to(KNOWLEDGE_DIR.resolve())
    except ValueError:
        return None

    if len(relative.parts) <= 1:
        return None

    return relative.parts[0].lower()


def load_source_metadata(path: Path):
    """Build source metadata from path plus an optional sidecar JSON file."""

    path = Path(path)

    metadata = {
        "title": path.stem,
        "category": infer_category(path),
        "vendor": None,
        "product": None,
        "version": None,
        "url": None,
        "author": None,
        "knowledge_type": "reference",
        "scope": "general",
        "confidence": "source-derived",
        "tags": [],
    }

    sidecar = _sidecar_path(path)

    if sidecar.exists():
        try:
            supplied = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Invalid metadata sidecar {sidecar}: {exc}"
            ) from exc

        allowed = {
            "title",
            "category",
            "vendor",
            "product",
            "version",
            "url",
            "author",
            "knowledge_type",
            "scope",
            "confidence",
            "knowledge_status",
            "confidence_score",
            "confirmations",
            "contradictions",
            "last_confirmed",
            "stale_days",
            "tags",
        }

        for key in allowed:
            if key in supplied:
                metadata[key] = supplied[key]

    metadata["source"] = str(path)
    metadata["filename"] = path.name
    metadata["extension"] = path.suffix.lower()

    return metadata
