from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_EVIDENCE_SOURCES = ("validated_playbook", "user_confirmed_outcome")


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    status: str
    category: str | None
    site: str | None
    system: str | None
    symptom: str
    root_cause: str
    resolution: str
    validation: dict[str, bool]
    evidence_source: str
    playbook_id: str
    created_at: str
    closed_at: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IncidentRecord":
        required = {
            "incident_id", "status", "category", "site", "system",
            "symptom", "root_cause", "resolution", "validation",
            "evidence_source", "playbook_id", "created_at", "closed_at",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValueError(f"Malformed incident record; missing: {', '.join(missing)}")
        if data["status"] != "resolved":
            raise ValueError("Persisted incident status must be 'resolved'")
        if data["evidence_source"] not in VALID_EVIDENCE_SOURCES:
            raise ValueError(
                "Persisted incident must come from validated_playbook or "
                "user_confirmed_outcome evidence"
            )
        if not isinstance(data["validation"], dict) or not data["validation"]:
            raise ValueError("Persisted incident requires validation evidence")
        if not all(value is True for value in data["validation"].values()):
            raise ValueError("All persisted validation evidence must be true")
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
