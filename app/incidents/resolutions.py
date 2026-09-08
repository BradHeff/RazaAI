from __future__ import annotations

from dataclasses import dataclass

from .patterns import IncidentPattern
from .retrieval import IncidentRetriever


@dataclass(frozen=True)
class LearnedResolution:
    """A repeated, Python-validated historical resolution pattern."""

    resolution_type: str
    count: int
    confidence: str
    site: str | None
    system: str | None
    playbook_id: str
    symptom: str
    root_cause: str
    resolution: str
    validation_required: tuple[str, ...]
    incident_ids: tuple[str, ...]
    verification_first: str

    def to_dict(self) -> dict:
        return {
            "resolution_type": self.resolution_type,
            "count": self.count,
            "confidence": self.confidence,
            "site": self.site,
            "system": self.system,
            "playbook_id": self.playbook_id,
            "symptom": self.symptom,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "validation_required": list(self.validation_required),
            "incident_ids": list(self.incident_ids),
            "verification_first": self.verification_first,
        }


class LearnedResolutionAnalyzer:
    """Derive historical operational experience, not proof of a current root cause."""

    def __init__(self, store):
        self.store = store

    def _records_for_pattern(self, pattern: IncidentPattern):
        records = []
        for incident_id in pattern.incident_ids:
            try:
                record = self.store.get(incident_id)
            except (OSError, ValueError, KeyError):
                continue
            if IncidentRetriever._eligible(record):
                records.append(record)
        return records

    @staticmethod
    def _verification_instruction(pattern: IncidentPattern) -> str:
        if pattern.playbook_id == "wifi-nps-no-connectivity":
            return (
                "Verify the current WLAN/SSID Access VLAN in the wireless "
                "controller or AP configuration before recommending any VLAN change."
            )

        return (
            "Verify current evidence that matches the historical root cause "
            "before recommending or applying the prior resolution."
        )

    def analyze_patterns(
        self,
        patterns: list[IncidentPattern],
        *,
        min_count: int = 2,
    ) -> list[LearnedResolution]:
        learned: list[LearnedResolution] = []

        for pattern in patterns:
            if pattern.count < min_count:
                continue

            records = self._records_for_pattern(pattern)
            if len(records) < min_count:
                continue

            records.sort(key=lambda record: (record.closed_at, record.incident_id))
            representative = records[-1]

            validation_sets = [
                {key for key, value in record.validation.items() if value is True}
                for record in records
            ]
            common_validation = (
                set.intersection(*validation_sets) if validation_sets else set()
            )

            confidence = "high" if len(records) >= 3 else "medium"

            learned.append(
                LearnedResolution(
                    resolution_type="validated_learned_resolution",
                    count=len(records),
                    confidence=confidence,
                    site=pattern.site,
                    system=pattern.system,
                    playbook_id=pattern.playbook_id,
                    symptom=representative.symptom,
                    root_cause=pattern.root_cause,
                    resolution=pattern.resolution,
                    validation_required=tuple(sorted(common_validation)),
                    incident_ids=tuple(record.incident_id for record in records),
                    verification_first=self._verification_instruction(pattern),
                )
            )

        learned.sort(
            key=lambda item: (
                -item.count,
                item.playbook_id,
                item.site or "",
                item.system or "",
                item.incident_ids[-1],
            )
        )
        return learned

    def guidance(
        self,
        learned: list[LearnedResolution],
        max_chars: int = 1300,
    ) -> str:
        if not learned:
            return ""

        blocks = [
            "LEARNED RESOLUTION INTELLIGENCE",
            (
                "Python found a repeated resolution that was validated in prior "
                "closed incidents. Treat it as high-value historical guidance, "
                "NOT as proof of the current root cause. Verify current evidence "
                "before recommending or applying the historical fix."
            ),
        ]

        for item in learned[:2]:
            validation = ", ".join(item.validation_required) or "validated closure"
            block = (
                f"\nLEARNED RESOLUTION\n"
                f"count={item.count}; confidence={item.confidence}; "
                f"site={item.site or '-'}; system={item.system or '-'}; "
                f"playbook={item.playbook_id}\n"
                f"Historical symptom: {item.symptom}\n"
                f"Repeated validated root cause: {item.root_cause}\n"
                f"Repeated validated resolution: {item.resolution}\n"
                f"Historical validation required: {validation}\n"
                f"VERIFY FIRST: {item.verification_first}\n"
                "RULE: Do not state that the current cause is confirmed and do not "
                "apply the historical resolution until current evidence supports it. "
                "If the user or a live tool shows the historical prerequisite is already "
                "correct, mark that historical hypothesis falsified for the current incident "
                "and continue to the next diagnostic layer."
            )
            candidate = "\n".join(blocks) + block
            if len(candidate) > max_chars:
                break
            blocks.append(block)

        return "\n".join(blocks)
