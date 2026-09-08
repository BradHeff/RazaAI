from __future__ import annotations

import re


_FOLLOWUP_RE = re.compile(
    r"(?:"
    r"^\s*(?:that|this|it|same|still|now)\b"
    r"|\b(?:that|the|this)\s+(?:command|check|test|output|result|error)\b"
    r"|\bunknown\s+action\b"
    r"|\bstill\s+(?:fails?|failing|not|doesn['’]?t|won['’]?t)\b"
    r"|\b(?:command|check|test)\s+(?:fails?|failed|errors?|returns?)\b"
    r")",
    re.I,
)


def contextual_diagnostic_query(
    current: str,
    messages: list[dict] | None,
    *,
    previous_domain: str | None = None,
    current_domain: str | None = None,
    max_prior_user_turns: int = 2,
) -> str:
    """Build retrieval text for an underspecified technical follow-up."""
    current_text = str(current or "").strip()
    if not current_text:
        return current_text

    if previous_domain and current_domain and previous_domain != current_domain:
        return current_text

    words = re.findall(r"[A-Za-z0-9']+", current_text)
    is_followup = bool(_FOLLOWUP_RE.search(current_text)) and len(words) <= 28
    if not is_followup:
        return current_text

    prior: list[str] = []
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        text = str(message.get("content") or "").strip()
        if not text or text.startswith("/"):
            continue
        prior.append(text)
        if len(prior) >= max(1, int(max_prior_user_turns)):
            break

    if not prior:
        return current_text

    prior.reverse()
    return "\n".join([
        "Earlier user context:",
        *[f"- {item}" for item in prior],
        "Current user update:",
        current_text,
    ])
