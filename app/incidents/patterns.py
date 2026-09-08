from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import IncidentRecord
from .retrieval import IncidentMatch, IncidentRetriever


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fingerprint(record: IncidentRecord) -> tuple[str, str, str, str, str]:
    """Trusted recurrence key built only from validated persisted facts."""
    return (
        _norm(record.playbook_id),
        _norm(record.site),
        _norm(record.system),
        _norm(record.root_cause),
        _norm(record.resolution),
    )


@dataclass(frozen=True)
class IncidentPattern:
    pattern_type: str
    count: int
    first_seen: str
    last_seen: str
    site: str | None
    system: str | None
    playbook_id: str
    root_cause: str
    resolution: str
    incident_ids: tuple[str, ...]
    confidence: str

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "site": self.site,
            "system": self.system,
            "playbook_id": self.playbook_id,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "incident_ids": list(self.incident_ids),
            "confidence": self.confidence,
        }


class IncidentPatternAnalyzer:
    """Deterministic recurrence intelligence over trusted incident memory."""

    def __init__(self, store):
        self.store = store

    def _eligible_records(self) -> list[IncidentRecord]:
        try:
            records = self.store.list_records()
        except (OSError, ValueError, KeyError):
            return []
        return [
            record
            for record in records
            if IncidentRetriever._eligible(record)
        ]

    def analyze_matches(
        self,
        matches: list[IncidentMatch],
        *,
        min_count: int = 2,
    ) -> list[IncidentPattern]:
        if not matches:
            return []

        records = self._eligible_records()
        patterns: list[IncidentPattern] = []
        seen: set[tuple[str, str, str, str, str]] = set()

        for match in matches:
            representative = match.incident
            key = _fingerprint(representative)
            if key in seen:
                continue
            seen.add(key)

            group = [record for record in records if _fingerprint(record) == key]
            if len(group) < min_count:
                continue

            group.sort(key=lambda record: (_dt(record.closed_at), record.incident_id))
            first = group[0]
            last = group[-1]
            count = len(group)

            confidence = "high" if count >= 3 else "medium"
            patterns.append(
                IncidentPattern(
                    pattern_type="validated_recurrence",
                    count=count,
                    first_seen=first.closed_at,
                    last_seen=last.closed_at,
                    site=representative.site,
                    system=representative.system,
                    playbook_id=representative.playbook_id,
                    root_cause=representative.root_cause,
                    resolution=representative.resolution,
                    incident_ids=tuple(record.incident_id for record in group),
                    confidence=confidence,
                )
            )

        patterns.sort(
            key=lambda pattern: (
                -pattern.count,
                pattern.last_seen,
                pattern.incident_ids[-1],
            )
        )
        return patterns

    def guidance(self, patterns: list[IncidentPattern], max_chars: int = 1000) -> str:
        if not patterns:
            return ""

        blocks = [
            "VALIDATED INCIDENT RECURRENCE INTELLIGENCE",
            "Python found repeated validated historical incidents. This raises "
            "the priority of checking the repeated pattern, but it does NOT prove "
            "the current incident has the same root cause. Confirm with current evidence.",
            "Evidence-source rule: use a controller/AP/switch configuration view or a "
            "configured network-device tool to prove WLAN Access VLAN configuration. "
            "Endpoint IP/interface tools do not prove the WLAN's configured Access VLAN.",
        ]

        for pattern in patterns[:2]:
            block = (
                f"\nRECURRENT PATTERN\n"
                f"count={pattern.count}; confidence={pattern.confidence}; "
                f"site={pattern.site or '-'}; system={pattern.system or '-'}; "
                f"playbook={pattern.playbook_id}\n"
                f"first_seen={pattern.first_seen}; last_seen={pattern.last_seen}\n"
                f"Repeated prior root cause: {pattern.root_cause}\n"
                f"Repeated prior resolution: {pattern.resolution}\n"
                f"validated_incidents={', '.join(pattern.incident_ids)}"
            )
            candidate = "\n".join(blocks) + block
            if len(candidate) > max_chars:
                break
            blocks.append(block)

        return "\n".join(blocks)
