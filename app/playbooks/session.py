from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone


@dataclass
class PlaybookSession:
    playbook_id: str
    playbook_name: str
    current_step: int = 0
    status: str = "waiting_for_evidence"
    observations: list[dict[str, Any]] = field(default_factory=list)
    initial_query: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    lifecycle_context: dict[str, Any] = field(default_factory=dict)
    resolution_evidence: dict[str, Any] = field(default_factory=dict)
    validation_evidence: dict[str, Any] = field(default_factory=dict)
    persisted_incident_id: str | None = None

    def current_check(self, playbook: dict) -> str | None:
        checks = playbook.get("checks", [])
        if 0 <= self.current_step < len(checks):
            return checks[self.current_step]
        return None

    def add_observation(self, text: str):
        self.observations.append({
            "step": self.current_step + 1,
            "text": text,
        })

    def advance(self, playbook: dict):
        checks = playbook.get("checks", [])
        if self.current_step + 1 < len(checks):
            self.current_step += 1
            self.status = "waiting_for_evidence"
            return True
        self.status = "needs_resolution"
        return False

    def resolve(self):
        self.status = "resolved"

    def reset(self):
        self.current_step = 0
        self.status = "waiting_for_evidence"
        self.observations.clear()
