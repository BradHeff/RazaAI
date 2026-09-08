from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .models import IncidentRecord

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return set(_TOKEN_RE.findall(value.lower()))


def _contains_phrase(query: str, value: str | None) -> bool:
    if not value:
        return False
    return value.lower() in query.lower()


def _age_bonus(closed_at: str) -> float:
    """Very small recency tie-breaker only; never dominates relevance."""
    try:
        dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = max(0.0, (now - dt).total_seconds() / 86400.0)
    except Exception:
        return 0.0
    return max(0.0, 0.25 - min(days, 365.0) / 1460.0)


@dataclass(frozen=True)
class IncidentMatch:
    incident: IncidentRecord
    score: float
    confidence: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident.incident_id,
            "score": round(self.score, 4),
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "site": self.incident.site,
            "system": self.incident.system,
            "category": self.incident.category,
            "playbook_id": self.incident.playbook_id,
            "symptom": self.incident.symptom,
            "root_cause": self.incident.root_cause,
            "resolution": self.incident.resolution,
            "validation": dict(self.incident.validation),
            "closed_at": self.incident.closed_at,
        }


class IncidentRetriever:
    """Deterministic retrieval over validated persistent incident records."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def _eligible(record: IncidentRecord) -> bool:
        # User-confirmed outcomes are retrievable guidance too, but
        # callers see them labelled as weaker evidence than playbook records.
        return (
            record.status == "resolved"
            and record.evidence_source in ("validated_playbook", "user_confirmed_outcome")
            and bool(record.validation)
            and all(value is True for value in record.validation.values())
        )

    def _records(self) -> Iterable[IncidentRecord]:
        try:
            records = self.store.list_records()
        except (OSError, ValueError, KeyError):
            return []
        return [record for record in records if self._eligible(record)]

    def _score(
        self,
        query: str,
        record: IncidentRecord,
        *,
        category: str | None = None,
        playbook_id: str | None = None,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        query_tokens = _tokens(query)

        if playbook_id and record.playbook_id == playbook_id:
            score += 5.0
            reasons.append("same playbook")

        if category and record.category and record.category == category:
            score += 1.5
            reasons.append("same category")

        if _contains_phrase(query, record.site):
            score += 3.5
            reasons.append("same site")

        system_tokens = _tokens(record.system)
        if system_tokens and system_tokens.issubset(query_tokens):
            score += 3.0
            reasons.append("same system")

        symptom_tokens = _tokens(record.symptom)
        if symptom_tokens:
            overlap = len(query_tokens & symptom_tokens)
            union = len(query_tokens | symptom_tokens)
            jaccard = overlap / union if union else 0.0
            score += jaccard * 5.0
            if jaccard >= 0.20:
                reasons.append("similar symptom")

        evidence = record.evidence or {}
        lifecycle = evidence.get("lifecycle_context") or {}
        for key in ("ssid", "site"):
            value = lifecycle.get(key)
            if value and _contains_phrase(query, str(value)):
                score += 0.75

        score += _age_bonus(record.closed_at)
        if record.evidence_source == "user_confirmed_outcome":
            # Weaker evidence: rank below equally similar playbook-validated
            # incidents and say so in the reasons.
            score -= 0.5
            reasons.append("user-confirmed (weaker than playbook-validated)")
        return score, reasons

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        playbook_id: str | None = None,
        top_k: int = 3,
        min_score: float = 3.25,
    ) -> list[IncidentMatch]:
        matches: list[IncidentMatch] = []

        for record in self._records():
            score, reasons = self._score(
                query,
                record,
                category=category,
                playbook_id=playbook_id,
            )
            if score < min_score:
                continue

            confidence = "high" if score >= 8.0 else "medium" if score >= 5.0 else "low"
            matches.append(
                IncidentMatch(
                    incident=record,
                    score=score,
                    confidence=confidence,
                    reasons=tuple(reasons),
                )
            )

        matches.sort(
            key=lambda match: (
                -match.score,
                match.incident.closed_at,
                match.incident.incident_id,
            )
        )

        unique: list[IncidentMatch] = []
        seen: set[tuple] = set()
        for match in matches:
            incident = match.incident
            fingerprint = (
                incident.playbook_id,
                (incident.site or "").lower(),
                (incident.system or "").lower(),
                incident.root_cause.lower(),
                incident.resolution.lower(),
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(match)
            if len(unique) >= max(0, int(top_k)):
                break

        return unique

    def guidance(self, matches: list[IncidentMatch], max_chars: int = 1800) -> str:
        if not matches:
            return ""

        blocks = [
            "VALIDATED PRIOR INCIDENT MEMORY",
            "These are previously resolved incidents captured by Python. "
            "Use them as historical evidence only. Do NOT assume a prior root "
            "cause is the current root cause until current evidence confirms it. "
            "If current user/tool evidence contradicts a prior cause, retire that prior "
            "hypothesis for this incident and continue diagnosis rather than repeating its fix. "
            "Incidents sourced 'user_confirmed_outcome' carry one human confirmation, "
            "not playbook validation: weigh them below validated incidents.",
        ]

        for index, match in enumerate(matches, start=1):
            incident = match.incident
            validation = ", ".join(
                f"{key}=PASS"
                for key, value in incident.validation.items()
                if value is True
            )
            block = (
                f"\nPRIOR INCIDENT {index}\n"
                f"id={incident.incident_id}; confidence={match.confidence}; "
                f"score={match.score:.2f}; reasons={', '.join(match.reasons) or 'structured similarity'}\n"
                f"site={incident.site or '-'}; system={incident.system or '-'}; "
                f"playbook={incident.playbook_id}\n"
                f"Prior symptom: {incident.symptom}\n"
                f"Prior root cause: {incident.root_cause}\n"
                f"Prior resolution: {incident.resolution}\n"
                f"Prior validation: {validation}"
            )
            candidate = "\n".join(blocks) + block
            if len(candidate) > max_chars:
                break
            blocks.append(block)

        return "\n".join(blocks)
