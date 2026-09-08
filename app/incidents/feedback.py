from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .promotions import KnowledgePromotionEngine, PromotionCandidate
from .retrieval import IncidentRetriever


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class KnowledgeFeedback:
    fingerprint: str
    knowledge_status: str
    confidence: str
    confidence_score: float
    confirmations: int
    contradictions: int
    distinct_dates: int
    stale_days: int
    last_confirmed: str
    reason: str
    knowledge_path: str
    metadata_path: str

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "knowledge_status": self.knowledge_status,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "confirmations": self.confirmations,
            "contradictions": self.contradictions,
            "distinct_dates": self.distinct_dates,
            "stale_days": self.stale_days,
            "last_confirmed": self.last_confirmed,
            "reason": self.reason,
            "knowledge_path": self.knowledge_path,
            "metadata_path": self.metadata_path,
        }


class KnowledgeFeedbackEngine:
    """Update confidence from validated incidents; the LLM never authors confirmation or contradiction state."""

    def __init__(
        self,
        store,
        *,
        project_root: Path | None = None,
        now_fn=None,
    ):
        self.store = store
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self.promotions = KnowledgePromotionEngine(
            store,
            project_root=self.project_root,
        )
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _eligible_records(self):
        try:
            records = self.store.list_records()
        except (OSError, ValueError, KeyError):
            return []
        return [record for record in records if IncidentRetriever._eligible(record)]

    @staticmethod
    def _scope_key(record) -> tuple[str, str, str, str]:
        return (
            _norm(record.category) or "general",
            _norm(record.playbook_id),
            _norm(record.site),
            _norm(record.system),
        )

    @staticmethod
    def _candidate_scope(candidate: PromotionCandidate) -> tuple[str, str, str, str]:
        return (
            _norm(candidate.category) or "general",
            _norm(candidate.playbook_id),
            _norm(candidate.site),
            _norm(candidate.system),
        )

    @staticmethod
    def _same_resolution(record, candidate: PromotionCandidate) -> bool:
        return _norm(record.root_cause) == _norm(candidate.root_cause) and _norm(
            record.resolution
        ) == _norm(candidate.resolution)

    @staticmethod
    def _stale_penalty(stale_days: int) -> float:
        if stale_days >= 365:
            return 0.15
        if stale_days >= 180:
            return 0.10
        if stale_days >= 90:
            return 0.05
        return 0.0

    def _score(
        self,
        *,
        confirmations: int,
        distinct_dates: int,
        contradictions: int,
        stale_days: int,
    ) -> float:
        score = 0.55
        score += min(confirmations, 5) * 0.06
        score += min(distinct_dates, 4) * 0.03
        score -= min(contradictions, 3) * 0.18
        score -= self._stale_penalty(stale_days)
        return round(max(0.05, min(0.99, score)), 2)

    @staticmethod
    def _classify(score: float, contradictions: int, stale_days: int):
        if contradictions >= 2 or score < 0.50:
            return "review", "low"
        if stale_days >= 365:
            return "stale", "low" if score < 0.65 else "medium"
        if score >= 0.80:
            return "active", "high"
        if score >= 0.65:
            return "active", "medium"
        return "watch", "low"

    @staticmethod
    def _reason(status: str, contradictions: int, stale_days: int) -> str:
        if status == "review":
            return (
                "validated same-scope incidents contradict this promoted "
                "root cause/resolution; human review is required"
            )
        if status == "stale":
            return (
                "promoted knowledge has not been reconfirmed recently; keep it "
                "available but verify aggressively before reuse"
            )
        if status == "watch":
            return "promoted knowledge remains available, but confidence is reduced"
        if contradictions:
            return (
                "promoted knowledge remains active with some contradictory "
                "validated evidence"
            )
        return "promoted knowledge is supported by validated confirmations"

    def evaluate(self) -> list[KnowledgeFeedback]:
        index = self.promotions._load_index()
        promoted = index.get("promotions", {})
        if not promoted:
            return []

        candidates = {
            candidate.fingerprint: candidate for candidate in self.promotions.evaluate()
        }
        records = self._eligible_records()
        now = self.now_fn()
        feedback: list[KnowledgeFeedback] = []

        for fingerprint, entry in sorted(promoted.items()):
            candidate = candidates.get(fingerprint)
            if candidate is None:

                continue

            same_scope = [
                record
                for record in records
                if self._scope_key(record) == self._candidate_scope(candidate)
            ]
            confirmations = [
                record
                for record in same_scope
                if self._same_resolution(record, candidate)
            ]
            contradictions = [
                record
                for record in same_scope
                if not self._same_resolution(record, candidate)
            ]

            confirmation_dates = {
                _dt(record.closed_at).date().isoformat() for record in confirmations
            }
            latest = max(
                (_dt(record.closed_at) for record in confirmations),
                default=_dt(candidate.last_seen),
            )
            stale_days = max(0, (now.date() - latest.date()).days)

            score = self._score(
                confirmations=len(confirmations),
                distinct_dates=len(confirmation_dates),
                contradictions=len(contradictions),
                stale_days=stale_days,
            )
            status, confidence = self._classify(
                score,
                len(contradictions),
                stale_days,
            )

            feedback.append(
                KnowledgeFeedback(
                    fingerprint=fingerprint,
                    knowledge_status=status,
                    confidence=confidence,
                    confidence_score=score,
                    confirmations=len(confirmations),
                    contradictions=len(contradictions),
                    distinct_dates=len(confirmation_dates),
                    stale_days=stale_days,
                    last_confirmed=latest.isoformat(),
                    reason=self._reason(status, len(contradictions), stale_days),
                    knowledge_path=entry["knowledge_path"],
                    metadata_path=entry["metadata_path"],
                )
            )

        return feedback

    def _update_sidecar(self, item: KnowledgeFeedback) -> None:
        path = Path(item.metadata_path)
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}

        metadata.update(
            {
                "confidence": item.confidence,
                "knowledge_status": item.knowledge_status,
                "confidence_score": item.confidence_score,
                "confirmations": item.confirmations,
                "contradictions": item.contradictions,
                "last_confirmed": item.last_confirmed,
                "stale_days": item.stale_days,
            }
        )
        _atomic_write(
            path,
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        )

    def _update_index(self, feedback: list[KnowledgeFeedback]) -> None:
        index = self.promotions._load_index()
        now = self.now_fn().isoformat()

        for item in feedback:
            entry = index.get("promotions", {}).get(item.fingerprint)
            if entry is None:
                continue
            entry["feedback"] = {
                "knowledge_status": item.knowledge_status,
                "confidence": item.confidence,
                "confidence_score": item.confidence_score,
                "confirmations": item.confirmations,
                "contradictions": item.contradictions,
                "distinct_dates": item.distinct_dates,
                "stale_days": item.stale_days,
                "last_confirmed": item.last_confirmed,
                "reason": item.reason,
                "updated_at": now,
            }

        self.promotions._save_index(index)

    def refresh_all(self) -> list[KnowledgeFeedback]:
        feedback = self.evaluate()
        for item in feedback:
            self._update_sidecar(item)
        if feedback:
            self._update_index(feedback)
        return feedback
