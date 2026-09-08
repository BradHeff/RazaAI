import re

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200):
    """Generic overlapping text chunker."""

    text = " ".join(text.split())

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = text.rfind(" ", start, end)

            if boundary > start + (chunk_size // 2):
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


def split_markdown_incidents(text: str):
    """Split Markdown by headings before generic chunking."""

    if not text or not text.strip():
        return []

    matches = list(HEADING_RE.finditer(text))

    if not matches:
        return [
            {
                "heading": None,
                "level": None,
                "text": text.strip(),
            }
        ]

    sections = []

    # Preserve any preamble before the first heading.
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()

        if preamble:
            sections.append(
                {
                    "heading": None,
                    "level": None,
                    "text": preamble,
                }
            )

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        section_text = text[start:end].strip()

        if not section_text:
            continue

        sections.append(
            {
                "heading": match.group(2).strip(),
                "level": len(match.group(1)),
                "text": section_text,
            }
        )

    return sections


def chunk_markdown_incidents(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
):
    """Incident-aware Markdown chunking."""

    sections = split_markdown_incidents(text)
    records = []

    for section in sections:
        heading = section["heading"]
        level = section["level"]
        section_text = section["text"].strip()

        if len(section_text) <= chunk_size:
            records.append(
                {
                    "text": section_text,
                    "heading": heading,
                    "heading_level": level,
                    "part": 1,
                }
            )
            continue

        body = section_text

        if heading:
            lines = section_text.splitlines()
            if lines and HEADING_RE.match(lines[0]):
                body = "\n".join(lines[1:]).strip()

        subchunks = chunk_text(
            body,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for part_number, subchunk in enumerate(subchunks, start=1):
            if heading:
                prefix = f"{'#' * (level or 2)} {heading}\n"
                final_text = prefix + subchunk
            else:
                final_text = subchunk

            records.append(
                {
                    "text": final_text.strip(),
                    "heading": heading,
                    "heading_level": level,
                    "part": part_number,
                }
            )

    return records
