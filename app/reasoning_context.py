"""Reasoning-first context gating for RazaAI."""

from __future__ import annotations

import re

from .personality import CORTANA_INSPIRED_TURN_VOICE


_MEMORY_INTENT_RE = re.compile(
    r"\b(?:"
    r"remember|memory|remembered|profile|preference|preferences|"
    r"who am i|what(?:'s| is) my (?:job|role|name|profile)|what do i do|"
    r"do you know my|what did (?:i|we|you)|last time|previously|earlier|"
    r"we (?:fixed|confirmed|discussed|decided|used)|known fix|confirmed fix|"
    r"happened before|again"
    r")\b",
    re.I,
)

_PROJECT_CONTEXT_RE = re.compile(
    r"\b(?:razaai|this project|project (?:code|source|branding|document|knowledge)|"
    r"branding|style guide|workspace|repository|repo|codebase)\b",
    re.I,
)

_COMPARISON_RE = re.compile(
    r"^\s*(?:and\s+)?(?:what|how)\s+about\s+(.+?)[?!.]*\s*$",
    re.I,
)

_STORAGE_MEDIUM_RE = re.compile(
    r"\b(?:plain\s*text|plaintext|text file|txt file|word document|word file|"
    r"excel spreadsheet|excel file|spreadsheet|paper|sticky note|notepad|"
    r"keepass|bitwarden|1password|password manager|secret store|vault)\b",
    re.I,
)


def should_retrieve_persistent_memory(text: str, interaction=None) -> bool:
    """Return True only when the current turn has an actual memory intent."""
    value = str(text or "").strip()
    if not value:
        return False
    if _MEMORY_INTENT_RE.search(value):
        return True

    # Direct durable-user-fact phrasing can benefit from user memory even when
    # it avoids the literal word "memory".
    if re.search(
        r"\b(?:my (?:job|role|name|online profile|preferred|preference)|"
        r"where do i work|who created you|am i your creator)\b",
        value,
        re.I,
    ):
        return True

    return False


def should_retrieve_project_context(text: str, *, document_request=False, interaction=None) -> bool:
    """Gate curated project Markdown so it cannot pollute generic reasoning."""
    if document_request:
        return True
    value = str(text or "").strip()
    if not value:
        return False
    return bool(_PROJECT_CONTEXT_RE.search(value))


def should_retrieve_incident_context(interaction=None, *, continuing_playbook=False, lifecycle_turn=False) -> bool:
    """Historical incident context is for active diagnostics, not general chat."""
    if continuing_playbook or lifecycle_turn:
        return True
    mode = str(getattr(interaction, "mode", "") or "")
    return mode == "troubleshooting"


def should_use_identity_personalization(text: str, interaction=None, profile=None) -> bool:
    """Use identity facts only when directly useful to the current reply."""
    if not isinstance(profile, dict) or not profile.get("has_identity"):
        return False
    value = str(text or "")
    if should_retrieve_persistent_memory(value, interaction):
        return True

    # User-specific opinion/workload questions benefit from the
    # compact confirmed identity profile (role/organisation) without opening
    # the broader persistent-memory retrieval floodgate.
    if re.search(
        r"\b(?:what are your thoughts (?:on|about) me|what do you think (?:of|about) me|"
        r"my work\s*load|my workload|my work at|my role at|my job at|my responsibilities)\b",
        value,
        re.I,
    ):
        return True

    # For unsafe security advice, role/context can make a pointed response
    # genuinely more relevant.  It must not be sprayed across neutral facts.
    if bool(getattr(interaction, "sensitive", False)) and str(
        getattr(interaction, "mode", "") or ""
    ) in {"advice", "conversation"}:
        return True

    return False


def current_turn_focus(text: str) -> str | None:
    """Extract an explicit current comparison candidate when possible."""
    value = str(text or "").strip()
    if not value:
        return None

    match = _COMPARISON_RE.match(value)
    if match:
        candidate = match.group(1).strip(" \t\r\n?!.\"'")
        if candidate:
            return candidate[:160]

    media = list(_STORAGE_MEDIUM_RE.finditer(value))
    if media:
        return media[-1].group(0).strip()
    return None


def reasoning_turn_guidance(text: str) -> str:
    """Compact, late prompt contract that makes the current turn authoritative."""
    focus = current_turn_focus(text)
    lines = [
        "CURRENT TURN REASONING CONTRACT",
        "Reason about the user's current request before using prior conversation or retrieved context.",
        "Retrieved memory/history is optional evidence, never a substitute for reasoning.",
        "The current user message outranks stale wording from previous assistant replies.",
        "If the current turn changes the object being compared, re-evaluate that object from scratch and name it correctly.",
        "Do not copy the prior answer merely because the topic is related.",
        "Check that your explanation supports your conclusion. If a check contradicts it, reconsider before answering.",
    ]
    if focus:
        lines += [
            f"Current explicit focus/candidate: {focus}",
            "Answer about this candidate. Earlier candidates are comparison context only.",
        ]
    return "\n".join(lines)


def personality_turn_guidance(interaction=None) -> str:
    """Late, high-priority voice card so operational context cannot bury RazaAI."""
    mode = getattr(interaction, "mode", None)
    sensitive = bool(getattr(interaction, "sensitive", False))

    if sensitive:
        return (
            CORTANA_INSPIRED_TURN_VOICE
            + "\n\nSECURITY ATTITUDE FOR THIS TURN\n"
            "If the user proposes unsafe credential handling, do not hedge, validate it, or sound like a policy leaflet. "
            "State the concrete risk and correct practice. A reckless choice can earn one dry aside; an honest question does not deserve ridicule."
        )

    if mode == "troubleshooting":
        return (
            "CORTANA-INSPIRED DELIVERY - CURRENT TURN (diagnostic)\n"
            "Evidence and diagnostic state outrank personality. Answer with the "
            "finding first, in RazaAI's composed, confident voice. At most one "
            "dry aside; wit must never slow down or cloud a live diagnosis."
        )

    return CORTANA_INSPIRED_TURN_VOICE


def response_addresses_focus(content: str, focus: str | None) -> bool:
    """Conservative check that a comparison response names the current target."""
    if not focus:
        return True
    answer = str(content or "").casefold()
    candidate = str(focus or "").casefold()
    terms = [
        token for token in re.findall(r"[a-z0-9.+#-]+", candidate)
        if len(token) >= 3 and token not in {"the", "and", "with", "about", "file"}
    ]
    if not terms:
        return True
    return any(term in answer for term in terms)


def focus_repair_guidance(focus: str) -> str:
    """Instruction for one bounded retry when the model answered the old object."""
    return (
        "CURRENT-OBJECT CORRECTION\n"
        f"Your draft did not clearly address the user's current comparison target: {focus}.\n"
        "Re-answer the current user turn from scratch. Name the current target explicitly, "
        "reason about that target, and do not repeat the previous candidate's name or answer. "
        "Keep RazaAI's normal confident/sassy voice where appropriate."
    )
