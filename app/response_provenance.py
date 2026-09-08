"""Python-owned attribution for the previous substantive RazaAI response."""

from __future__ import annotations

import re


PROVENANCE_QUERY_RE = re.compile(
    r"\b(?:"
    r"(?:was|is|did)\s+(?:that|this|your (?:last )?(?:answer|response))\s+"
    r"(?:from|using|based on)\s+(?:persistent\s+)?memory|"
    r"(?:was|is)\s+(?:that|this)\s+(?:a\s+)?memory\s+(?:answer|response)|"
    r"did\s+(?:that|this)\s+come\s+from\s+(?:persistent\s+)?memory|"
    r"where\s+did\s+(?:that|this|your (?:last )?answer)\s+come\s+from|"
    r"what\s+(?:source|evidence)\s+did\s+you\s+use\s+for\s+(?:that|this)"
    r")\b",
    re.I,
)

MEMORY_EXCLUSION_RE = re.compile(
    r"\b(?:something\s+not\s+in\s+(?:persistent\s+)?memory|"
    r"without\s+(?:using\s+)?(?:persistent\s+)?memory|"
    r"do\s+not\s+use\s+(?:persistent\s+)?memory|"
    r"don't\s+use\s+(?:persistent\s+)?memory)\b",
    re.I,
)


def is_provenance_query(text: str) -> bool:
    return bool(PROVENANCE_QUERY_RE.search(str(text or "")))


def explicitly_excludes_memory(text: str) -> bool:
    return bool(MEMORY_EXCLUSION_RE.search(str(text or "")))


def render_response_provenance(origin) -> str:
    """Explain the previous answer's source without letting the model guess."""
    if not isinstance(origin, dict) or not origin.get("kind"):
        return "I don't have a previous substantive answer to attribute yet."

    kind = str(origin.get("kind") or "").strip()
    identity_used = bool(origin.get("identity_memory_used"))
    identity_available = bool(origin.get("identity_memory_available"))
    memory_context = bool(origin.get("memory_context_available"))
    local_context = bool(origin.get("local_context_available"))
    tools = [str(item) for item in (origin.get("tools") or []) if str(item).strip()]

    if kind == "persistent_memory":
        return "Yes. That answer came from Python-owned persistent memory."
    if kind == "web_evidence":
        return "No. That answer came from live web evidence returned for that turn, not persistent memory."
    if kind == "live_tool_evidence":
        return "No. That answer came from live tool/infrastructure evidence for that turn, not persistent memory."
    if kind == "coding_workflow":
        return "No. That came from the transactional coding workflow and workspace evidence, not persistent memory."
    if kind == "runtime_state":
        return "No. That was Python-owned RazaAI runtime state/capability information, not persistent memory."
    if kind == "model_knowledge":
        if identity_used:
            return (
                "Not the technical answer. That came from the model's general knowledge/reasoning; "
                "I used confirmed identity/profile facts from persistent memory only to personalize the response."
            )
        if identity_available:
            return (
                "No. The substantive answer came from general model knowledge/reasoning. Confirmed identity/profile memory "
                "was available only as personalization context."
            )
        if memory_context:
            return (
                "It was model-generated. Persistent memory was available as context, but I can't honestly claim "
                "the answer itself came from memory unless Python performed a memory lookup."
            )
        if local_context:
            return (
                "No. It was model-generated with curated local project/incident context available, not a persistent-memory lookup."
            )
        return "No. That was general model knowledge/reasoning, not persistent memory."
    if kind == "model_with_tools":
        suffix = f" ({', '.join(tools)})" if tools else ""
        if identity_used:
            return (
                f"No. The substantive answer used current tool evidence{suffix}; persistent identity facts were used only for personalization."
            )
        return f"No. The substantive answer used current tool evidence{suffix}, not persistent memory."

    return "I can identify that as a RazaAI response, but its source classification is unavailable."
