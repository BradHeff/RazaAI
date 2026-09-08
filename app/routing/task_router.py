"""Task routing foundation."""
from dataclasses import dataclass, asdict
import re

@dataclass(frozen=True)
class TaskRoute:
    task: str
    domain: str
    confidence: float
    reason: str

    def to_dict(self):
        return asdict(self)

class TaskRouter:
    def route(self, text: str, interaction=None):
        value = (text or "").casefold()
        stripped = value.strip()

        # Transaction commands belong to the coding capability too.
        # Keeping the coder selected across /approve matters because failed
        # verification may need a coder repair pass before rollback.
        if stripped in {"/approve", "/reject", "/undo"} or stripped.startswith("/checkpoint"):
            return TaskRoute("coding", "programming", 1.0, "coding transaction command")

        # Coding requests are capability requests, not only
        # workspace mutation requests. Detect intent before tools/model use.
        coding_action = re.search(
            r"\b(edit|modify|refactor|patch|change|update|fix|add|remove|create|reate|write)\b",
            value,
        )
        code_target = re.search(
            r"\b[\w./-]+\.(py|js|ts|json|yaml|yml|md|sh|conf|cfg)\b",
            value,
        )
        if coding_action and code_target:
            return TaskRoute("coding", "programming", 0.95, "coding capability request")

        # Infrastructure incidents need the support capability even
        # when the interaction classifier has not yet marked the thread as
        # troubleshooting.
        support_markers = (
            r"fortigate", r"firewall", r"router", r"switch", r"wifi",
            r"vpn", r"dns", r"certificate", r"ssh",
            r"gui unavailable", r"not accessible", r"cannot access",
            r"not working", r"error", r"failed", r"issue", r"problem",
        )
        failure_context = any(
            re.search(marker, value)
            for marker in (
                r"unavailable", r"not working", r"error", r"failed",
                r"issue", r"problem", r"cannot", r"can't", r"unable",
                r"refused", r"timed out", r"offline",
            )
        )
        if any(re.search(marker, value) for marker in support_markers) and failure_context:
            return TaskRoute("support", "infrastructure", 0.85, "technical diagnostic request")

        if interaction and getattr(interaction, "troubleshooting", False):
            return TaskRoute("support", getattr(interaction, "domain", None) or "technical", 0.85, "troubleshooting interaction")

        if re.search(r"\b(research|compare|investigate|find sources|analyse|analyze)\b", value):
            return TaskRoute("research", "general", 0.75, "research request")

        return TaskRoute("conversation", "general", 0.70, "default conversational route")
