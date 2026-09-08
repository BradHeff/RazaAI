from dataclasses import dataclass, field
from typing import Any


VALID_DECISIONS = {"isolated", "passed", "unclear"}


@dataclass
class DiagnosticDecision:
    decision: str
    reason: str
    missing_evidence: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.decision = self.decision.strip().lower()
        if self.decision not in VALID_DECISIONS:
            raise ValueError(
                f"Invalid diagnostic decision: {self.decision!r}. "
                f"Expected one of {sorted(VALID_DECISIONS)}"
            )

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            decision=str(data.get("decision", "")).strip().lower(),
            reason=str(data.get("reason", "")).strip(),
            missing_evidence=list(data.get("missing_evidence") or []),
            evidence=dict(data.get("evidence") or {}),
        )
