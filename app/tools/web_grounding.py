"""RazaAI web-answer grounding helpers."""

from __future__ import annotations

import re


_CITATION_RE = re.compile(r"\[(S\d+|W\d+)\]")


def web_source_map(tool_name, result):
    """Return exact valid source IDs -> source metadata for one web result."""
    if result is None or not getattr(result, "success", False):
        return {}

    payload = result.result if isinstance(result.result, dict) else {}

    if tool_name == "search_web":
        return {
            str(item.get("source_id")): item
            for item in payload.get("results") or []
            if item.get("source_id")
        }

    if tool_name == "fetch_web_page":
        source_id = payload.get("source_id")
        return {str(source_id): payload} if source_id else {}

    return {}


def extract_web_citations(text):
    return {
        match.group(1)
        for match in _CITATION_RE.finditer(text or "")
    }


def validate_web_answer(tool_name, result, answer):
    """Validate that a web-derived answer cites only returned source IDs."""
    sources = web_source_map(tool_name, result)

    if not sources:
        return False, "no source evidence returned"

    cited = extract_web_citations(answer)

    if not cited:
        return False, "web-derived answer omitted source citations"

    unknown = cited - set(sources)
    if unknown:
        return (
            False,
            "answer cited source IDs that were not returned: "
            + ", ".join(sorted(unknown)),
        )

    return True, ""


def grounded_web_fallback(tool_name, result):
    """Return evidence-only output when model citation grounding fails."""
    if result is None or not getattr(result, "success", False):
        return "I couldn't retrieve usable web evidence."

    payload = result.result if isinstance(result.result, dict) else {}

    if tool_name == "search_web":
        results = payload.get("results") or []

        if not results:
            return (
                "The web search returned no usable results. "
                "I won't invent an answer without source evidence."
            )

        preferred = [
            item
            for item in results
            if item.get("authority") == "preferred"
        ]
        selected = (preferred or results)[:3]

        lines = [
            "I couldn't produce a summary of these sources that I actually trust, "
            "so here they are in their own words — judge for yourself:"
        ]

        for item in selected:
            source_id = item.get("source_id") or "S?"
            title = item.get("title") or "Untitled source"
            snippet = re.sub(
                r"\s+",
                " ",
                str(item.get("snippet") or ""),
            ).strip()

            if snippet:
                lines.append(
                    f"- {title}: {snippet} [{source_id}]"
                )
            else:
                lines.append(
                    f"- {title} [{source_id}]"
                )

        return "\n".join(lines)

    if tool_name == "fetch_web_page":
        source_id = payload.get("source_id") or "W1"
        title = payload.get("title") or payload.get("url") or "Webpage"
        text = re.sub(
            r"\s+",
            " ",
            str(payload.get("text") or ""),
        ).strip()

        if not text:
            return (
                "The webpage was retrieved but contained no usable text evidence."
            )

        excerpt = text[:700]
        if len(text) > 700:
            excerpt += "…"

        return f"{title}: {excerpt} [{source_id}]"

    return "No grounded web evidence is available."
