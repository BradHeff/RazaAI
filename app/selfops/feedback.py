from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR


_ISSUE_KINDS = {
    "user_correction",
    "tool_failure",
    "document_failure",
    "context_overflow",
    "web_grounding_rejection",
    "capability_failure",
    "audit_failure",
}

_POSITIVE_KINDS = {"successful_resolution"}

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you",
    "how", "what", "when", "where", "why", "can", "could", "would", "should",
    "issue", "problem", "fix", "improve", "troubleshooting", "current", "razaai",
}

_CORRECTION_RE = re.compile(
    r"(?:^|\b)(?:no[,. ]|actually\b|that(?:'s| is) (?:wrong|incorrect)|"
    r"not (?:right|correct)|you (?:forgot|missed)|it(?:'s| is) already\b|"
    r"its already\b|already on\b|i said\b|i told you\b)",
    re.I,
)

_SUCCESS_RE = re.compile(
    r"(?:\bit(?:'s| is) working now\b|\bworking now\b|\bthat worked\b|"
    r"\bfixed now\b|\bit(?:'s| is) fixed\b|\bresolved now\b|\bproblem solved\b)",
    re.I,
)

# Conversation fragments persisted as signals are redacted before
# they touch disk, and the file is bounded.
_REDACT_RE = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|session[_-]?id|cookie"
    r")\b\s*[:=]\s*\S+"
)
MAX_SIGNALS = int(os.getenv("RAZAAI_SIGNALS_MAX", "500"))


def redact_snippet(value, limit=500):
    text = str(value or "")[:limit]
    return _REDACT_RE.sub(r"\1=[redacted]", text)


class ImprovementFeedbackStore:
    """Persistent operational quality signals for controlled self-improvement."""

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        if project_root is not None:
            self.root = self.project_root / "data" / "improvement_feedback"
        else:
            from ..config import state_dir
            self.root = state_dir() / "improvement_feedback"
        self.signals_path = self.root / "signals.jsonl"
        self.promotions_path = self.root / "promotions.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _keywords(value, limit=8):
        words = re.findall(r"[a-z0-9_]+", str(value or "").casefold())
        keep = []
        for word in words:
            if len(word) < 3 or word in _STOPWORDS:
                continue
            if word not in keep:
                keep.append(word)
            if len(keep) >= limit:
                break
        return keep

    @classmethod
    def topic_key(cls, value):
        words = cls._keywords(value)
        return ":".join(words) if words else "general"

    @staticmethod
    def _fingerprint(kind, domain, topic_key, source="runtime"):
        raw = f"{kind}|{domain}|{topic_key}|{source}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:20]

    @staticmethod
    def _append(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n")

    @classmethod
    def _append_bounded(cls, path, data):
        """Append, then bound the file: signals must not grow forever."""
        cls._append(path, data)
        try:
            items = cls._read_jsonl(path)
            if len(items) > MAX_SIGNALS * 2:
                keep = items[-MAX_SIGNALS:]
                tmp = path.with_suffix(".jsonl.tmp")
                tmp.write_text(
                    "".join(
                        json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n"
                        for item in keep
                    ),
                    encoding="utf-8",
                )
                tmp.replace(path)
        except OSError:
            pass

    @staticmethod
    def _read_jsonl(path):
        if not path.exists():
            return []
        items = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                items.append(item)
        return items

    def record(
        self,
        kind,
        *,
        topic,
        domain="general",
        summary="",
        source="runtime",
        severity="medium",
        evidence=None,
        file=None,
        metadata=None,
    ):
        kind = str(kind or "").strip()
        if not kind:
            raise ValueError("Signal kind is required")
        topic = redact_snippet(topic, 1200)
        domain = str(domain or "general").strip().casefold() or "general"
        key = self.topic_key(topic)
        signal = {
            "signal_id": "SIG-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"),
            "created_at": self._now(),
            "kind": kind,
            "topic": redact_snippet(topic, 1200),
            "topic_key": key,
            "domain": domain,
            "summary": redact_snippet(summary, 2000),
            "source": str(source or "runtime")[:100],
            "severity": str(severity or "medium").casefold(),
            "fingerprint": self._fingerprint(kind, domain, key, source),
            "evidence": [redact_snippet(item, 1000) for item in (evidence or [])][:12],
            "file": str(file)[:500] if file else None,
            "metadata": dict(metadata or {}),
        }
        self._append_bounded(self.signals_path, signal)
        return signal

    def observe_user_followup(
        self,
        user_input,
        *,
        previous_user=None,
        previous_assistant=None,
        domain="general",
        sensitive=False,
    ):
        if sensitive:
            return None
        current = str(user_input or "").strip()
        previous_user = str(previous_user or "").strip()
        previous_assistant = str(previous_assistant or "").strip()
        if not current or not previous_assistant:
            return None

        if _CORRECTION_RE.search(current):
            topic = previous_user or f"{domain} response quality"
            return self.record(
                "user_correction",
                topic=topic,
                domain=domain,
                summary="User corrected or contradicted the immediately preceding RazaAI answer.",
                source="conversation",
                severity="medium",
                evidence=[f"correction={current[:400]}", f"previous_answer={previous_assistant[:500]}"],
            )

        if _SUCCESS_RE.search(current):
            topic = previous_user or f"{domain} resolution"
            return self.record(
                "successful_resolution",
                topic=topic,
                domain=domain,
                summary="User explicitly reported that the issue is working/fixed.",
                source="conversation",
                severity="low",
                evidence=[f"outcome={current[:400]}"],
            )
        return None

    def record_promotion(self, job):
        data = {
            "improvement_id": str(job.get("improvement_id") or ""),
            "promoted_at": str(job.get("promoted_at") or self._now()),
            "goal": str(job.get("goal") or "")[:2000],
            "topic_key": self.topic_key(job.get("goal") or ""),
            "changed_files": list(job.get("changed_files") or []),
            "risk": str(job.get("risk") or "unknown"),
        }
        self._append(self.promotions_path, data)
        return data

    def signals(self, limit=100):
        return self._read_jsonl(self.signals_path)[-max(1, min(int(limit), 1000)):]

    def promotions(self, limit=100):
        return self._read_jsonl(self.promotions_path)[-max(1, min(int(limit), 1000)):]

    @staticmethod
    def _confidence(count):
        if count >= 4:
            return "high"
        if count >= 2:
            return "medium"
        return "low"

    @staticmethod
    def _keyword_overlap(left, right):
        a = set(str(left or "").split(":")) - {"general", ""}
        b = set(str(right or "").split(":")) - {"general", ""}
        return len(a & b)

    def aggregate(self, *, min_occurrences=2, limit=10):
        groups = defaultdict(list)
        for signal in self.signals(limit=1000):
            if signal.get("kind") not in _ISSUE_KINDS:
                continue
            groups[signal.get("fingerprint")].append(signal)

        rows = []
        for fingerprint, items in groups.items():
            items.sort(key=lambda item: str(item.get("created_at") or ""))
            latest = items[-1]
            count = len(items)
            if count < int(min_occurrences):
                continue
            rows.append({
                "fingerprint": fingerprint,
                "kind": latest.get("kind"),
                "domain": latest.get("domain"),
                "topic": latest.get("topic"),
                "topic_key": latest.get("topic_key"),
                "summary": latest.get("summary"),
                "file": latest.get("file"),
                "occurrences": count,
                "confidence": self._confidence(count),
                "first_seen": items[0].get("created_at"),
                "last_seen": latest.get("created_at"),
                "evidence": [e for item in items[-3:] for e in (item.get("evidence") or [])][-8:],
            })
        rows.sort(key=lambda item: (-int(item["occurrences"]), str(item["last_seen"])), reverse=False)
        return rows[:max(1, min(int(limit), 50))]

    def history(self, limit=20):
        signals = self.signals(limit=1000)
        promotions = self.promotions(limit=limit)
        rows = []
        for promotion in reversed(promotions):
            promoted_at = str(promotion.get("promoted_at") or "")
            key = promotion.get("topic_key")
            after = [
                signal for signal in signals
                if str(signal.get("created_at") or "") > promoted_at
                and signal.get("kind") in _ISSUE_KINDS
                and self._keyword_overlap(key, signal.get("topic_key")) >= 1
            ]
            positive = [
                signal for signal in signals
                if str(signal.get("created_at") or "") > promoted_at
                and signal.get("kind") in _POSITIVE_KINDS
                and self._keyword_overlap(key, signal.get("topic_key")) >= 1
            ]
            rows.append({
                **promotion,
                "issue_signals_after": len(after),
                "successful_outcomes_after": len(positive),
                "measurement": (
                    "needs_review" if len(after) >= 2
                    else ("positive" if positive and not after else "insufficient_evidence")
                ),
            })
        return rows[:max(1, min(int(limit), 100))]

    def status(self):
        signals = self.signals(limit=1000)
        return {
            "enabled": True,
            "signals": len(signals),
            "issue_signals": sum(1 for item in signals if item.get("kind") in _ISSUE_KINDS),
            "positive_signals": sum(1 for item in signals if item.get("kind") in _POSITIVE_KINDS),
            "repeated_weaknesses": len(self.aggregate(min_occurrences=2, limit=100)),
            "promotions": len(self.promotions(limit=1000)),
        }
