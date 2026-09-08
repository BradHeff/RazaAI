from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .patterns import IncidentPattern


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class IncidentTrend:
    trend_type: str
    status: str
    count: int
    distinct_dates: int
    span_days: int
    first_seen: str
    last_seen: str
    site: str | None
    system: str | None
    playbook_id: str
    root_cause: str
    resolution: str
    incident_ids: tuple[str, ...]
    confidence: str
    escalation_required: bool
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "trend_type": self.trend_type,
            "status": self.status,
            "count": self.count,
            "distinct_dates": self.distinct_dates,
            "span_days": self.span_days,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "site": self.site,
            "system": self.system,
            "playbook_id": self.playbook_id,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "incident_ids": list(self.incident_ids),
            "confidence": self.confidence,
            "escalation_required": self.escalation_required,
            "recommendation": self.recommendation,
        }


class IncidentTrendAnalyzer:
    """Deterministic operational trend/escalation intelligence."""

    def __init__(self, store):
        self.store = store

    def _records_for_pattern(self, pattern: IncidentPattern):
        records = []

        for incident_id in pattern.incident_ids:
            try:
                record = self.store.get(incident_id)
            except (OSError, ValueError, KeyError):
                continue

            if record is not None:
                records.append(record)

        return records

    @staticmethod
    def _recommendation(pattern: IncidentPattern, status: str) -> str:
        if status == "watch":
            return (
                "Keep the repeated pattern under observation. The validated "
                "records are concentrated on one date, so do not treat them "
                "as proof of a persistent operational trend yet."
            )

        if pattern.playbook_id == "wifi-nps-no-connectivity":
            return (
                "Review and standardise the site-to-WLAN VLAN mapping, then "
                "add a configuration verification step to wireless changes. "
                "Address the repeated validated cause as a configuration/process "
                "problem rather than as isolated client faults."
            )

        return (
            "Review the repeated validated root cause and implement a permanent "
            "corrective action or process control rather than resolving each "
            "incident independently."
        )

    def analyze_patterns(self, patterns: list[IncidentPattern]) -> list[IncidentTrend]:
        trends: list[IncidentTrend] = []

        for pattern in patterns:
            records = self._records_for_pattern(pattern)

            if len(records) < 2:
                continue

            closed = sorted(_dt(record.closed_at) for record in records)
            first = closed[0]
            last = closed[-1]
            dates = {value.date().isoformat() for value in closed}

            distinct_dates = len(dates)
            span_days = max(0, (last.date() - first.date()).days)
            count = len(records)

            if distinct_dates >= 3 and count >= 4:
                status = "escalate"
                confidence = "high"
                escalation_required = True
            elif distinct_dates >= 2 and count >= 3:
                status = "trend"
                confidence = "medium"
                escalation_required = False
            else:
                status = "watch"
                confidence = "low"
                escalation_required = False

            trends.append(
                IncidentTrend(
                    trend_type="validated_operational_trend",
                    status=status,
                    count=count,
                    distinct_dates=distinct_dates,
                    span_days=span_days,
                    first_seen=first.isoformat(),
                    last_seen=last.isoformat(),
                    site=pattern.site,
                    system=pattern.system,
                    playbook_id=pattern.playbook_id,
                    root_cause=pattern.root_cause,
                    resolution=pattern.resolution,
                    incident_ids=pattern.incident_ids,
                    confidence=confidence,
                    escalation_required=escalation_required,
                    recommendation=self._recommendation(pattern, status),
                )
            )

        rank = {"escalate": 0, "trend": 1, "watch": 2}
        trends.sort(
            key=lambda trend: (
                rank.get(trend.status, 99),
                -trend.count,
                -trend.distinct_dates,
                trend.last_seen,
                trend.incident_ids[-1],
            )
        )
        return trends

    def guidance(self, trends: list[IncidentTrend], max_chars: int = 1200) -> str:
        if not trends:
            return ""

        blocks = [
            "VALIDATED OPERATIONAL TREND INTELLIGENCE",
            (
                "Python separately evaluated temporal recurrence. A repeated "
                "incident pattern is NOT automatically a long-term operational "
                "trend. Same-day repetitions may be testing, retries, or repeated "
                "documentation. Do not overstate them."
            ),
        ]

        for trend in trends[:2]:
            if trend.status == "watch":
                headline = (
                    "WATCH ONLY - recurrence exists, but temporal spread is "
                    "insufficient for operational escalation."
                )
            elif trend.status == "trend":
                headline = (
                    "RECURRING OPERATIONAL TREND - repeated validated incidents "
                    "occurred across multiple dates."
                )
            else:
                headline = (
                    "ESCALATION RECOMMENDED - repeated validated incidents span "
                    "multiple dates and justify permanent corrective action."
                )

            block = (
                f"\nTREND\n"
                f"status={trend.status}; confidence={trend.confidence}; "
                f"count={trend.count}; distinct_dates={trend.distinct_dates}; "
                f"span_days={trend.span_days}; escalation_required="
                f"{trend.escalation_required}\n"
                f"site={trend.site or '-'}; system={trend.system or '-'}; "
                f"playbook={trend.playbook_id}\n"
                f"{headline}\n"
                f"Recommendation: {trend.recommendation}"
            )

            candidate = "\n".join(blocks) + block
            if len(candidate) > max_chars:
                break
            blocks.append(block)

        return "\n".join(blocks)
