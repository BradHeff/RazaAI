from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .retrieval import IncidentRetriever


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "incident-pattern"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class PromotionCandidate:
    fingerprint: str
    eligible: bool
    reason: str
    category: str
    site: str | None
    system: str | None
    playbook_id: str
    symptom: str
    root_cause: str
    resolution: str
    validation_required: tuple[str, ...]
    incident_ids: tuple[str, ...]
    count: int
    distinct_dates: int
    first_seen: str
    last_seen: str
    confidence: str

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "eligible": self.eligible,
            "reason": self.reason,
            "category": self.category,
            "site": self.site,
            "system": self.system,
            "playbook_id": self.playbook_id,
            "symptom": self.symptom,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "validation_required": list(self.validation_required),
            "incident_ids": list(self.incident_ids),
            "count": self.count,
            "distinct_dates": self.distinct_dates,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PromotionResult:
    status: str
    fingerprint: str
    knowledge_path: str | None
    metadata_path: str | None
    count: int
    distinct_dates: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "fingerprint": self.fingerprint,
            "knowledge_path": self.knowledge_path,
            "metadata_path": self.metadata_path,
            "count": self.count,
            "distinct_dates": self.distinct_dates,
            "reason": self.reason,
        }


class KnowledgePromotionEngine:
    """Write validated sources under knowledge/<category>/promoted/. Promotion does NOT directly mutate Qdrant."""

    def __init__(self, store, *, project_root: Path | None = None):
        self.store = store
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self.knowledge_root = self.project_root / "knowledge"
        # An explicit project_root keeps its own state; only the
        # default is redirectable via RAZAAI_STATE_DIR.
        if project_root is not None:
            self.state_root = self.project_root / "data" / "knowledge_promotions"
        else:
            from ..config import state_dir
            self.state_root = state_dir() / "knowledge_promotions"
        self.index_path = self.state_root / "index.json"

    def _eligible_records(self):
        try:
            records = self.store.list_records()
        except (OSError, ValueError, KeyError):
            return []
        return [record for record in records if IncidentRetriever._eligible(record)]

    @staticmethod
    def _group_key(record) -> tuple[str, str, str, str, str, str]:
        # User-confirmed outcomes all share playbook_id
        # "user-confirmed" and have no site/system; group them by symptom so
        # unrelated fixes don't merge into one knowledge candidate.
        if _norm(record.playbook_id) == "user-confirmed":
            thread = _norm(record.symptom)[:120]
        else:
            thread = _norm(record.playbook_id)
        return (
            _norm(record.category) or "general",
            thread,
            _norm(record.site),
            _norm(record.system),
            _norm(record.root_cause),
            _norm(record.resolution),
        )

    @staticmethod
    def _fingerprint(key: tuple[str, ...]) -> str:
        payload = "\n".join(key).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def evaluate(self) -> list[PromotionCandidate]:
        groups: dict[tuple[str, ...], list] = {}
        for record in self._eligible_records():
            groups.setdefault(self._group_key(record), []).append(record)

        candidates: list[PromotionCandidate] = []

        for key, records in groups.items():
            records.sort(key=lambda r: (r.closed_at, r.incident_id))
            representative = records[-1]
            dates = {_dt(record.closed_at).date().isoformat() for record in records}
            distinct_dates = len(dates)
            count = len(records)
            # User-confirmed outcomes are weaker evidence than
            # playbook-validated records. Pure user-confirmed groups need a
            # higher bar (4 across 3 dates) and cap at medium confidence;
            # any playbook-validated record in the group restores the
            # original 3-across-2-dates rule.
            validated_count = sum(
                1 for r in records if r.evidence_source == "validated_playbook"
            )
            validation_sets = [
                {k for k, value in record.validation.items() if value is True}
                for record in records
            ]
            common_validation = (
                set.intersection(*validation_sets) if validation_sets else set()
            )
            if validated_count:
                eligible = count >= 3 and distinct_dates >= 2
            else:
                eligible = count >= 4 and distinct_dates >= 3

            if validated_count and count < 3:
                reason = "requires at least 3 validated incidents"
            elif validated_count and distinct_dates < 2:
                reason = "same-day recurrence is insufficient for durable knowledge promotion"
            elif not validated_count and count < 4:
                reason = "user-confirmed outcomes require at least 4 incidents"
            elif not validated_count and distinct_dates < 3:
                reason = "user-confirmed outcomes require 3 distinct dates (weaker evidence)"
            else:
                reason = "validated recurrence has sufficient temporal spread"

            if not eligible:
                confidence = "low"
            elif validated_count == 0:
                confidence = "medium" if count >= 5 and distinct_dates >= 4 else "low"
            else:
                confidence = (
                    "high"
                    if count >= 4 and distinct_dates >= 3
                    else "medium"
                )

            candidates.append(
                PromotionCandidate(
                    fingerprint=self._fingerprint(key),
                    eligible=eligible,
                    reason=reason,
                    category=(representative.category or "general").lower(),
                    site=representative.site,
                    system=representative.system,
                    playbook_id=representative.playbook_id,
                    symptom=representative.symptom,
                    root_cause=representative.root_cause,
                    resolution=representative.resolution,
                    validation_required=tuple(sorted(common_validation)),
                    incident_ids=tuple(record.incident_id for record in records),
                    count=count,
                    distinct_dates=distinct_dates,
                    first_seen=records[0].closed_at,
                    last_seen=records[-1].closed_at,
                    confidence=confidence,
                )
            )

        candidates.sort(
            key=lambda item: (
                not item.eligible,
                -item.distinct_dates,
                -item.count,
                item.category,
                item.fingerprint,
            )
        )
        return candidates

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"promotions": {}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"promotions": {}}
        if not isinstance(data, dict):
            return {"promotions": {}}
        data.setdefault("promotions", {})
        return data

    def _save_index(self, data: dict) -> None:
        _atomic_write(
            self.index_path,
            json.dumps(data, indent=2, sort_keys=True) + "\n",
        )

    @staticmethod
    def _verification_first(candidate: PromotionCandidate) -> str:
        if candidate.playbook_id == "wifi-nps-no-connectivity":
            return (
                "Verify the current WLAN/SSID Access VLAN in the wireless "
                "controller or AP configuration before applying this resolution."
            )
        return (
            "Verify current evidence matches this root cause before applying "
            "the historical resolution."
        )

    def _paths(self, candidate: PromotionCandidate) -> tuple[Path, Path]:
        label = "-".join(
            part
            for part in (
                candidate.site or "",
                candidate.system or "",
                candidate.playbook_id,
            )
            if part
        )
        filename = f"{_slug(label)}-{candidate.fingerprint}.md"
        directory = self.knowledge_root / candidate.category / "promoted"
        path = directory / filename
        return path, Path(str(path) + ".meta.json")

    def _markdown(self, candidate: PromotionCandidate) -> str:
        validation = (
            "\n".join(f"- {item}" for item in candidate.validation_required)
            or "- validated closure"
        )
        incident_ids = "\n".join(f"- {item}" for item in candidate.incident_ids)
        scope = (
            "/".join(part for part in (candidate.site, candidate.system) if part)
            or "general"
        )

        return (
            f"# Validated Operational Pattern: {scope}\n\n"
            f"## Symptom\n{candidate.symptom}\n\n"
            f"## Validated Root Cause\n{candidate.root_cause}\n\n"
            f"## Validated Resolution\n{candidate.resolution}\n\n"
            f"## Validation Required\n{validation}\n\n"
            f"## Verification Before Reuse\n{self._verification_first(candidate)}\n\n"
            f"## Evidence Basis\n"
            f"- Validated incidents: {candidate.count}\n"
            f"- Distinct dates: {candidate.distinct_dates}\n"
            f"- First seen: {candidate.first_seen}\n"
            f"- Last seen: {candidate.last_seen}\n"
            f"- Confidence: {candidate.confidence}\n"
            f"- Playbook: {candidate.playbook_id}\n\n"
            f"### Source Incident IDs\n{incident_ids}\n\n"
            "## Usage Rule\n"
            "This is promoted historical operational knowledge, not proof of a "
            "new incident's current root cause. Confirm current evidence before "
            "applying the resolution.\n"
        )

    def _metadata(self, candidate: PromotionCandidate) -> dict:
        tags = [
            "promoted-incident-knowledge",
            "validated-resolution",
            candidate.playbook_id,
        ]
        if candidate.site:
            tags.append(candidate.site.lower())
        if candidate.system:
            tags.append(candidate.system.lower())

        return {
            "title": (
                f"Validated operational pattern - "
                f"{candidate.site or 'general'} {candidate.system or ''}"
            ).strip(),
            "category": candidate.category,
            "author": "RazaAI validated incident memory",
            "knowledge_type": "validated_operational_pattern",
            "scope": "site-specific" if candidate.site else "general",
            "confidence": candidate.confidence,
            "knowledge_status": "active",
            "confidence_score": 0.8 if candidate.confidence == "high" else 0.7,
            "confirmations": candidate.count,
            "contradictions": 0,
            "last_confirmed": candidate.last_seen,
            "stale_days": 0,
            "tags": tags,
        }

    def promote(self, candidate: PromotionCandidate) -> PromotionResult:
        if not candidate.eligible:
            return PromotionResult(
                status="blocked",
                fingerprint=candidate.fingerprint,
                knowledge_path=None,
                metadata_path=None,
                count=candidate.count,
                distinct_dates=candidate.distinct_dates,
                reason=candidate.reason,
            )

        knowledge_path, metadata_path = self._paths(candidate)
        index = self._load_index()
        prior = index["promotions"].get(candidate.fingerprint)

        markdown = self._markdown(candidate)
        metadata = (
            json.dumps(self._metadata(candidate), indent=2, sort_keys=True) + "\n"
        )

        _atomic_write(knowledge_path, markdown)
        _atomic_write(metadata_path, metadata)

        now = datetime.now(timezone.utc).isoformat()
        index["promotions"][candidate.fingerprint] = {
            "knowledge_path": str(knowledge_path),
            "metadata_path": str(metadata_path),
            "incident_ids": list(candidate.incident_ids),
            "count": candidate.count,
            "distinct_dates": candidate.distinct_dates,
            "first_seen": candidate.first_seen,
            "last_seen": candidate.last_seen,
            "confidence": candidate.confidence,
            "promoted_at": (prior or {}).get("promoted_at", now),
            "updated_at": now,
        }
        self._save_index(index)

        return PromotionResult(
            status="updated" if prior else "promoted",
            fingerprint=candidate.fingerprint,
            knowledge_path=str(knowledge_path),
            metadata_path=str(metadata_path),
            count=candidate.count,
            distinct_dates=candidate.distinct_dates,
            reason=candidate.reason,
        )

    def promote_eligible(self) -> list[PromotionResult]:
        return [
            self.promote(candidate)
            for candidate in self.evaluate()
            if candidate.eligible
        ]
