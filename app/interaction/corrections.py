from __future__ import annotations

import re


_CORRECTION_RE = re.compile(
    r"(?:"
    r"what\s+has\s+that\s+to\s+do\s+with"
    r"|what\s+does\s+that\s+have\s+to\s+do\s+with"
    r"|that\s+has\s+nothing\s+to\s+do\s+with"
    r"|that(?:'s|\s+is)\s+not\s+what\s+i\s+asked"
    r"|not\s+what\s+i\s+asked"
    r"|that(?:'s|\s+is)\s+irrelevant"
    r"|wrong\s+(?:command|answer|topic)"
    r")",
    re.I,
)


def correction_followup_guidance(current: str, messages: list[dict] | None) -> str:
    """Ground a user correction in prior user intent, never prior assistant claims."""
    if not _CORRECTION_RE.search(str(current or "")):
        return ""

    prior: list[str] = []
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        text = str(message.get("content") or "").strip()
        if not text:
            continue
        prior.append(text)
        if len(prior) >= 3:
            break
    prior.reverse()

    lines = [
        "USER CORRECTION / RE-ANCHOR",
        "The user is challenging the relevance or correctness of the previous assistant answer.",
        "Do not defend the previous answer and do not treat previous assistant text as evidence.",
        "Acknowledge the mismatch briefly, then answer the user's actual technical objective.",
    ]
    if prior:
        lines.append("Recent user-provided context:")
        lines.extend(f"- {item}" for item in prior)
    return "\n".join(lines)
