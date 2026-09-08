from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_KINDS = {
    "fact",
    "preference",
    "note",
    "technical_observation",
    "technical_pattern",
    # User-confirmed troubleshooting outcomes (episode summaries).
    "episode_summary",
    # User-requested end-of-session digests (model-summarized,
    # Python-guarded, stored only on explicit /digest or "remember" intent).
    "session_summary",
}
VALID_STATES = {
    "active",
    "superseded",
    "review",
    "forgotten",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    kind: str
    key: str
    value: str
    confidence: float
    state: str
    source: str
    created_at: str
    updated_at: str
    confirmations: int = 1
    validations: int = 0
    domain: str | None = None
    tags: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    supersedes: str | None = None
    contradicted_by: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in VALID_KINDS:
            raise ValueError(f"Invalid memory kind: {self.kind}")
        if self.state not in VALID_STATES:
            raise ValueError(f"Invalid memory state: {self.state}")
        if not self.key.strip():
            raise ValueError("Memory key is required")
        if not self.value.strip():
            raise ValueError("Memory value is required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("Memory confidence must be between 0 and 1")

    def to_dict(self):
        data = asdict(self)
        data["tags"] = list(self.tags)
        data["contradicted_by"] = list(self.contradicted_by)
        return data

    @classmethod
    def from_dict(cls, data):
        clean = dict(data)
        clean["tags"] = tuple(clean.get("tags") or ())
        clean["contradicted_by"] = tuple(clean.get("contradicted_by") or ())
        return cls(**clean)
