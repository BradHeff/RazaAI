"""Generalized troubleshooting-outcome capture."""

from __future__ import annotations

import re

from .models import IncidentRecord, utc_now

# A user confirming resolution. Deliberately broad: a solo operator says
# "sorted", "fixed", "working", "good now", "you beauty".
RESOLUTION_CONFIRM_RE = re.compile(
    r"\b(?:"
    r"it(?:'s| is| was)? (?:all )?(?:working|fixed|sorted|good|good now|resolved)|"
    r"that(?:'s| is| was)? (?:fixed|sorted|worked|it)|"
    r"working (?:now|again)|"
    r"all (?:good|sorted|working now)|"
    r"problem(?:'s| is)? (?:fixed|solved|sorted|gone)|"
    r"fixed|sorted|solved|"
    r"(?:you )?(?:beauty|legend|champion)[,!]"  # Operator flavour; harmless
    r")\b",
    re.I,
)

# Same words negated: must be checked BEFORE treating a turn as confirmation.
RESOLUTION_NEGATIVE_RE = re.compile(
    r"\b(?:not|isn'?t|wasn'?t|still|no longer working correctly|"
    r"hasn'?t|didn'?t|doesn'?t|don'?t think)\b|"
    r"\b(?:issue|problem|error|it|they)(?:'s| is| was| has)? (?:back|returned|recurred)|"
    r"\bhappening again\b",
    re.I,
)

RESOLUTION_DENIAL_RE = re.compile(
    r"\b(?:"
    r"same (?:issue|problem|thing)|"
    r"no change|no joy|no luck|"
    r"still (?:broken|down|failing|not working|not fixed|happening|the same)|"
    r"(?:is|that|it)(?:'s| is| was)? still (?:broken|not working|not fixed)|"
    r"not (?:working|fixed|sorted|resolved) (?:yet|still)|"
    r"hasn'?t (?:worked|fixed)"
    r")\b",
    re.I,
)

MAX_SYMPTOM_CHARS = 240
MAX_RESOLUTION_CHARS = 400
MAX_CAUSE_CHARS = 240


_QUESTION_START_RE = re.compile(
    r"^(?:what|why|how|when|who|where|is|are|do|does|did|can|could|would|should|will|has|have)\b",
    re.I,
)


def is_resolution_confirmation(text: str) -> bool:
    value = str(text or "").strip()
    if not value or len(value) > 400:
        return False
    if "?" in value or _QUESTION_START_RE.match(value):
        return False  # A question about fixing is not a confirmation
    if RESOLUTION_NEGATIVE_RE.search(value):
        return False
    return bool(RESOLUTION_CONFIRM_RE.search(value))


def is_resolution_denial(text: str) -> bool:
    """User reporting the problem persists."""
    value = str(text or "").strip()
    if not value or len(value) > 400:
        return False
    return bool(RESOLUTION_DENIAL_RE.search(value))


def _clean(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    return value[:limit].rstrip()


class OutcomeSessionTracker:
    """Tracks one conversation's troubleshooting thread, Python-side only."""

    def __init__(self):
        self.persisted_fingerprints: set[str] = set()
        self.reset()

    def reset(self):
        self.active = False
        self.domain = None
        self.category = None
        self.symptom = None
        self.last_assistant_reply = None
        self.cause = None
        self.user_turns = 0

    _DIAGNOSTIC_MODES = {"troubleshooting", "advice", "action"}

    def note_user_turn(self, text, *, mode=None, domain=None):
        from ..memory.manager import is_sensitive_memory

        value = _clean(text, MAX_SYMPTOM_CHARS)
        if not value or is_sensitive_memory(value):
            return
        if mode in self._DIAGNOSTIC_MODES and not self.active:
            self.active = True
            self.domain = domain
            self.symptom = value
        elif self.active:
            self.user_turns += 1

    def note_assistant_reply(self, text):
        if not self.active:
            return
        value = _clean(text, MAX_RESOLUTION_CHARS)
        if len(value) >= 40:  # Ignore acks/one-liners
            self.last_assistant_reply = value

    def note_cause(self, cause):
        value = _clean(cause, MAX_CAUSE_CHARS)
        if value:
            self.cause = value

    def take_outcome(self) -> dict | None:
        """Return captured facts if the thread has enough substance."""
        if not self.active or not self.symptom:
            return None
        resolution = self.last_assistant_reply
        if not resolution:
            return None
        outcome = {
            "category": self.category or self.domain,
            "site": None,
            "system": None,
            "symptom": self.symptom,
            "root_cause": self.cause or "User confirmed the fix without attributing a root cause",
            "resolution": resolution,
        }
        self.reset()
        return outcome


class IncidentOutcomeBridge:
    """Persists user-confirmed outcomes as incident records."""

    def __init__(self, store):
        self.store = store

    def persist_outcome(self, tracker: OutcomeSessionTracker) -> IncidentRecord | None:
        if not tracker.active:
            return None
        cause_reported = bool(tracker.cause)
        outcome = tracker.take_outcome()
        if outcome is None:
            return None
        fingerprint = "|".join(
            part.casefold().strip() for part in (outcome["symptom"], outcome["resolution"])
        )
        if fingerprint in tracker.persisted_fingerprints:
            return None
        now = utc_now()
        record = self.store.create(
            status="resolved",
            category=outcome["category"],
            site=outcome["site"],
            system=outcome["system"],
            symptom=outcome["symptom"],
            root_cause=outcome["root_cause"],
            resolution=outcome["resolution"],
            validation={"user_confirmed": True},
            evidence_source="user_confirmed_outcome",
            playbook_id="user-confirmed",
            created_at=now,
            closed_at=now,
            evidence={
                "conversation_outcome": {
                    "captured_by": "app.incidents.outcomes",
                    "cause_reported_by_user": cause_reported,
                },
            },
        )
        tracker.persisted_fingerprints.add(fingerprint)
        return record
