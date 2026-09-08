import re
from pathlib import Path


SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(value: str, extension: str):
    value = (value or "").strip()

    if not value:
        value = "document"

    # Drop any user/model supplied path and keep only the final name.
    value = Path(value).name

    value = value.replace(" ", "_")
    value = SAFE_FILENAME_RE.sub("_", value)
    value = value.strip("._")

    if not value:
        value = "document"

    extension = extension.lower().lstrip(".")

    suffix = f".{extension}"

    if not value.lower().endswith(suffix):
        value += suffix

    return value


def ensure_output_directory(project_root: Path):
    output = (
        project_root
        / "output"
        / "documents"
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    return output
