from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import re

from .store import MemoryStore


_TOKEN_RE = re.compile(r"[a-z0-9]+")

_SECRET_TERMS = re.compile(
    r"\b(?:password|passphrase|credential|api[ _-]?key|access[ _-]?token|"
    r"refresh[ _-]?token|private[ _-]?key|recovery[ _-]?code|secret)\b",
    re.I,
)

_SECRET_VALUE_HINTS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


_DURABLE_FACT_SUBJECTS = {
    "editor",
    "shell",
    "operating system",
    "os",
    "distro",
    "linux distro",
    "job title",
    "role",
    "company",
    "organisation",
    "organization",
    "core switch",
    "firewall",
    "laptop",
    "desktop",
}

_TRANSIENT_VALUE_RE = re.compile(
    r"\b(?:down|offline|unreachable|broken|slow|failing|failed|error|"
    r"not working|disconnected|full|high cpu|high memory)\b",
    re.I,
)


def _tokens(value):
    return set(_TOKEN_RE.findall(str(value or "").casefold()))


def _slug(value, limit=42):
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return result[:limit] or "item"


def is_sensitive_memory(text):
    value = str(text or "")
    if _SECRET_TERMS.search(value):
        return True
    return any(pattern.search(value) for pattern in _SECRET_VALUE_HINTS)


class MemoryManager:
    """Persistent user memory and low-authority experiential learning."""

    def __init__(self, store=None):
        self.store = store or MemoryStore()

    def remember_explicit(self, text, *, domain=None):
        value = re.sub(
            r"\s+",
            " ",
            re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "").strip()),
        ).strip()
        if not value:
            raise ValueError("Nothing was supplied to remember")
        if len(value) > 1000:
            raise ValueError("Persistent memory entry is too long (maximum 1000 characters)")
        if is_sensitive_memory(value):
            raise ValueError(
                "Sensitive credentials/secrets are not allowed in persistent memory"
            )

        kind, key, clean_value = self._classify_personal_statement(value)
        if kind is None:
            kind = "note"
            clean_value = value
            key = f"user.note.{_slug(value)}"

        return self.store.upsert(
            kind=kind,
            key=key,
            value=clean_value,
            confidence=1.0,
            source="user_explicit",
            domain=domain,
            tags=("explicit",),
            provenance={
                "evidence": "explicit remember request",
            },
        )

    def user_name(self):
        """Return the active user name fact, if one has been explicitly established."""
        matches = [
            record for record in self.store.records()
            if record.kind == "fact" and record.key == "user.name"
        ]
        if not matches:
            return None
        matches.sort(key=lambda record: record.updated_at, reverse=True)
        return matches[0].value

    @staticmethod
    def _looks_person_name(value):
        text = str(value or "").strip().strip(".!?")
        words = [part for part in re.split(r"\s+", text) if part]
        if not 2 <= len(words) <= 5:
            return False
        if any(word.casefold() in {"the", "a", "an", "not", "very", "really"} for word in words):
            return False
        return all(re.match(r"^[A-Z][A-Za-z'’-]*$", word) for word in words)

    @staticmethod
    def _profile_job_from_title(title, user_name=None):
        value = str(title or "").strip()
        if user_name and value.casefold().startswith(str(user_name).casefold()):
            value = value[len(str(user_name)):].lstrip(" -|:")
        value = re.sub(r"\|\s*LinkedIn.*$", "", value, flags=re.I).strip(" -|:")
        if not value:
            return None
        role_hint = re.compile(
            r"\b(?:manager|engineer|administrator|developer|director|officer|technician|"
            r"architect|consultant|specialist|analyst|teacher|principal|founder|owner|lead)\b",
            re.I,
        )
        return value if role_hint.search(value) else None

    @staticmethod
    def _profile_organisation_from_snippet(snippet):
        text = str(snippet or "")
        match = re.search(
            r"\b(?:as\s+.{1,80}?\s+)?at\s+([A-Z][A-Za-z0-9&.'’() -]{2,80}?)(?=,|\.|\s+(?:where|and|with)\b)",
            text,
        )
        return match.group(1).strip() if match else None

    def remember_online_profile(
        self, *, title, url=None, snippet="", source_id=None, query=None, user_name=None
    ):
        """Persist a web/profile identity only after explicit user confirmation."""
        title = re.sub(r"\s+", " ", str(title or "").strip())
        snippet = re.sub(r"\s+", " ", str(snippet or "").strip())
        url = str(url or "").strip() or None
        if not title:
            raise ValueError("Confirmed online profile is missing a title")
        if any(is_sensitive_memory(part) for part in (title, snippet, url or "")):
            raise ValueError("Sensitive credentials/secrets are not allowed in persistent memory")

        inferred_name = str(user_name or "").strip() or None
        if not inferred_name:
            candidate = re.split(r"\s+-\s+|\s+\|\s+", title, maxsplit=1)[0].strip()
            if self._looks_person_name(candidate):
                inferred_name = candidate
        if inferred_name:
            self.store.upsert(
                kind="fact", key="user.name", value=inferred_name, confidence=1.0,
                source="user_confirmed_web", tags=("identity", "user-confirmed"),
                provenance={"evidence": "confirmed online profile"},
            )

        provenance = {
            "title": title,
            "url": url,
            "snippet": snippet,
            "source_id": str(source_id or "") or None,
            "query": str(query or "") or None,
            "authority": "user-confirmed web/profile identity",
        }
        profile = self.store.upsert(
            kind="fact", key="user.fact.online-profile", value=title, confidence=1.0,
            source="user_confirmed_web", tags=("online-profile", "identity", "user-confirmed"),
            provenance=provenance,
        )

        name = inferred_name or self.user_name()
        job = self._profile_job_from_title(title, name)
        if job:
            self.store.upsert(
                kind="fact", key="user.fact.job-title", value=job, confidence=1.0,
                source="user_confirmed_web", tags=("identity", "occupation", "user-confirmed"),
                provenance={"profile_memory_id": profile.memory_id, "title": title, "url": url},
            )
        organisation = self._profile_organisation_from_snippet(snippet)
        if organisation:
            self.store.upsert(
                kind="fact", key="user.fact.organization", value=organisation, confidence=1.0,
                source="user_confirmed_web", tags=("identity", "occupation", "user-confirmed"),
                provenance={"profile_memory_id": profile.memory_id, "title": title, "url": url},
            )
        return profile

    def remember_profile_text(self, text):
        """Persist user-confirmed pasted profile text without inventing a URL."""
        value = re.sub(r"\s+", " ", str(text or "").strip())
        if not value:
            raise ValueError("No profile text was supplied")
        title, sep, snippet = value.partition(":")
        if "linkedin" not in title.casefold() and "linkedin" in value.casefold():
            # Keep the visible identity/title segment stable even when punctuation differs.
            idx = value.casefold().find("linkedin") + len("linkedin")
            title, snippet = value[:idx], value[idx:].lstrip(" :·-")
        return self.remember_online_profile(
            title=title.strip() or value[:180],
            snippet=(snippet if sep or snippet else value),
            user_name=self.user_name(),
        )

    def identity_profile(self, query=""):
        """Return a Python-owned, user-only identity profile for deterministic recall."""
        records = self.store.records()
        by_key = {}
        for record in sorted(records, key=lambda item: item.updated_at):
            if record.kind == "fact":
                by_key[record.key] = record
        name_rec = by_key.get("user.name")
        job_rec = by_key.get("user.fact.job-title") or by_key.get("user.fact.role")
        org_rec = by_key.get("user.fact.organization") or by_key.get("user.fact.organisation") or by_key.get("user.fact.company")
        relation_rec = by_key.get("user.fact.razaai-relationship")
        profile_rec = by_key.get("user.fact.online-profile")

        name = name_rec.value if name_rec else None
        job = job_rec.value if job_rec else None
        organisation = org_rec.value if org_rec else None
        relationship = relation_rec.value if relation_rec else None
        profile = None
        if profile_rec is not None:
            profile = {
                "title": profile_rec.provenance.get("title") or profile_rec.value,
                "url": profile_rec.provenance.get("url"),
                "snippet": profile_rec.provenance.get("snippet"),
                "source_id": profile_rec.provenance.get("source_id"),
                "query": profile_rec.provenance.get("query"),
            }
            if not job:
                job = self._profile_job_from_title(profile["title"], name)
            if not organisation:
                organisation = self._profile_organisation_from_snippet(profile.get("snippet") or "")

        return {
            "query": str(query or ""),
            "name": name,
            "job_title": job,
            "organization": organisation,
            "razaai_relationship": relationship,
            "online_profile": profile,
            "has_identity": any((name, job, organisation, relationship, profile)),
        }

    def record_episode(self, *, symptom, resolution, domain=None):
        """Persist a user-confirmed resolution as episodic memory."""
        symptom_clean = re.sub(r"\s+", " ", str(symptom or "").strip())[:200]
        resolution_clean = re.sub(r"\s+", " ", str(resolution or "").strip())[:300]
        if not symptom_clean or not resolution_clean:
            return None
        if is_sensitive_memory(symptom_clean) or is_sensitive_memory(resolution_clean):
            return None
        key = f"episode.{_slug(domain or 'general')}.{_slug(symptom_clean[:60])}"
        return self.store.upsert(
            kind="episode_summary",
            key=key,
            value=f"Fixed: {symptom_clean} → {resolution_clean}",
            confidence=0.6,
            source="user_confirmed_outcome",
            domain=domain,
            tags=("learned-resolution", "user-confirmed"),
            provenance={
                "authority": "user confirmed the fix worked; not independently validated",
            },
        )

    def observe_user_turn(
        self,
        text,
        *,
        domain=None,
        previous_domain=None,
        allow_technical=True,
        session_id=None,
    ):
        """Capture only strong direct-user statements; never infer from model text."""
        value = re.sub(
            r"\s+",
            " ",
            re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "").strip()),
        ).strip()
        if not value or len(value) > 1000 or is_sensitive_memory(value):
            return None

        kind, key, clean_value = self._classify_personal_statement(value)
        if kind is not None:
            return self.store.upsert(
                kind=kind,
                key=key,
                value=clean_value,
                confidence=0.95,
                source="user_direct",
                domain=domain,
                tags=("direct-user-statement",),
                provenance={
                    "evidence": value,
                },
            )

        active_domain = previous_domain or domain
        if not allow_technical:
            return None

        cause = re.match(
            r"^\s*(?:it|that)\s+was\s+(.+?)[.!]?\s*$",
            value,
            re.I,
        )
        if cause and active_domain:
            cause_value = cause.group(1).strip()
            if is_sensitive_memory(cause_value):
                return None
            key = f"technical.{_slug(active_domain)}.cause.{_slug(cause_value)}"
            return self.store.upsert(
                kind="technical_observation",
                key=key,
                value=cause_value,
                confidence=0.65,
                source="user_reported_outcome",
                domain=active_domain,
                tags=("root-cause-report",),
                provenance={
                    "evidence": value,
                    "authority": "user-reported; not independently validated",
                    "last_observed_session": session_id,
                },
            )

        if re.match(
            r"^\s*(?:it(?:'s|\s+is)|that(?:'s|\s+is))\s+working\s+now[.!]?\s*$",
            value,
            re.I,
        ) and active_domain:
            return self._validate_latest_observation(
                active_domain,
                session_id=session_id,
            )

        return None

    @staticmethod
    def _classify_personal_statement(text):
        relationship = re.match(
            r"^(?:i am|i'm|im)\s+(?:the\s+)?creator\s+of\s+razaai[.!]?$",
            text,
            re.I,
        )
        if relationship:
            return "fact", "user.fact.razaai-relationship", "Creator of RazaAI"

        job = re.match(
            r"^(?:my\s+(?:job|job title|role)\s+is|i\s+work\s+as)\s+(.+?)[.!]?$",
            text,
            re.I,
        )
        if job:
            return "fact", "user.fact.job-title", job.group(1).strip()

        organisation = re.match(
            r"^(?:i\s+work\s+at|my\s+(?:company|organisation|organization)\s+is)\s+(.+?)[.!]?$",
            text,
            re.I,
        )
        if organisation:
            return "fact", "user.fact.organization", organisation.group(1).strip()

        person = re.match(r"^(?:i am|i'm|im)\s+(.+?)[.!]?$", text, re.I)
        if person and MemoryManager._looks_person_name(person.group(1).strip()):
            return "fact", "user.name", person.group(1).strip().strip(".!?")

        patterns = (
            (
                "fact",
                "user.name",
                re.compile(
                    r"^(?:my name is|call me)\s+(.+?)[.!]?$",
                    re.I,
                ),
            ),
            (
                "fact",
                "user.timezone",
                re.compile(
                    r"^my timezone is\s+(.+?)[.!]?$",
                    re.I,
                ),
            ),
            (
                "fact",
                "user.location",
                re.compile(
                    r"^(?:i live in|i am based in|i'm based in)\s+(.+?)[.!]?$",
                    re.I,
                ),
            ),
        )

        for kind, key, pattern in patterns:
            match = pattern.match(text)
            if match:
                return kind, key, match.group(1).strip()

        pref = re.match(
            r"^i prefer\s+(.+?)[.!]?$",
            text,
            re.I,
        )
        if pref:
            value = pref.group(1).strip()
            return (
                "preference",
                f"user.preference.{_slug(value)}",
                value,
            )

        # Explicit "my X is Y" facts are useful but deliberately reject
        # credential/security words before this function is called.
        fact = re.match(
            r"^my\s+([a-z][a-z0-9 _-]{1,40})\s+is\s+(.+?)[.!]?$",
            text,
            re.I,
        )
        if fact:
            subject = fact.group(1).strip()
            value = fact.group(2).strip()
            subject_norm = subject.casefold()
            if (
                subject_norm in _DURABLE_FACT_SUBJECTS
                and not _TRANSIENT_VALUE_RE.search(value)
            ):
                return (
                    "fact",
                    f"user.fact.{_slug(subject)}",
                    value,
                )

        return None, None, None

    def _validate_latest_observation(self, domain, *, session_id=None):
        observations = [
            record
            for record in self.store.records(include_inactive=False)
            if record.kind == "technical_observation"
            and record.domain == domain
            and record.state == "active"
        ]
        if not observations:
            return None

        observations.sort(key=lambda item: item.updated_at, reverse=True)
        latest = observations[0]

        validation_sessions = list(
            latest.provenance.get("validation_sessions") or []
        )
        session_key = str(session_id or "unknown-session")
        is_new_validation_session = session_key not in validation_sessions

        if is_new_validation_session:
            validation_sessions.append(session_key)

        updated = self.store.upsert(
            kind=latest.kind,
            key=latest.key,
            value=latest.value,
            confidence=max(latest.confidence, 0.75),
            source="user_reported_validation",
            domain=latest.domain,
            tags=latest.tags,
            provenance={
                "authority": "user-reported cause plus user-reported recovery",
                "validation_sessions": validation_sessions,
            },
            validation=is_new_validation_session,
        )

        # Promotion is intentionally conservative: the same remembered outcome
        # must be validated in at least two distinct RazaAI sessions. Repeating
        # the same phrase in one conversation cannot manufacture a pattern.
        if (
            updated.validations >= 2
            and len(validation_sessions) >= 2
        ):
            return self.store.upsert(
                kind="technical_pattern",
                key=latest.key.replace(".cause.", ".pattern."),
                value=latest.value,
                confidence=0.85,
                source="memory_promotion",
                domain=latest.domain,
                tags=("promoted-experience",),
                provenance={
                    "source_memory_id": latest.memory_id,
                    "validation_sessions": validation_sessions,
                    "rule": ">=2 distinct-session validated user-reported outcomes",
                },
                validation=True,
            )

        return updated

    def search(
        self,
        query,
        *,
        domain=None,
        kinds=None,
        top_k=5,
        min_score=0.18,
    ):
        query_tokens = _tokens(query)
        records = self.store.records()

        results = []
        for record in records:
            if kinds and record.kind not in set(kinds):
                continue
            if record.kind == "technical_observation":
                # Observations are only useful in the same technical domain.
                if not domain or record.domain != domain:
                    continue
            if record.kind == "technical_pattern" and domain and record.domain != domain:
                continue

            text = f"{record.key} {record.value} {' '.join(record.tags)}"
            record_tokens = _tokens(text)
            overlap = len(query_tokens & record_tokens)
            union = len(query_tokens | record_tokens)
            lexical = overlap / union if union else 0.0

            exact_bonus = 0.0
            if record.key == "user.name" and re.search(
                r"\b(?:my name|who am i|what(?:'s| is) my name|call me)\b",
                query,
                re.I,
            ):
                exact_bonus = 0.9
            elif record.key == "user.timezone" and "timezone" in query.casefold():
                exact_bonus = 0.9
            elif record.kind == "preference" and "prefer" in query.casefold():
                exact_bonus = 0.35

            domain_bonus = 0.15 if domain and record.domain == domain else 0.0
            confidence_bonus = record.confidence * 0.18
            score = lexical + exact_bonus + domain_bonus + confidence_bonus

            if score >= min_score:
                results.append((score, record))

        results.sort(
            key=lambda item: (
                -item[0],
                -item[1].confidence,
                item[1].updated_at,
            )
        )
        return results[:max(0, int(top_k))]

    def guidance(self, query, *, domain=None, max_chars=1600):
        matches = self.search(query, domain=domain, top_k=5)
        if not matches:
            return ""

        lines = [
            "PERSISTENT MEMORY EVIDENCE",
            "These records came from prior user-confirmed/direct statements or "
            "conservative memory promotion. Use only when relevant.",
            "Personal facts/preferences may personalize the answer. Technical "
            "memory is historical context only and never proves a current root cause.",
            "Live tool evidence and explicit current user state outrank memory. If current "
            "evidence contradicts a technical memory, retire that memory as a hypothesis for "
            "the current incident and continue diagnosis; do not repeat the remembered fix.",
        ]

        for score, record in matches:
            if record.kind == "technical_pattern":
                label = "LEARNED PATTERN"
            elif record.kind == "technical_observation":
                label = "PRIOR USER-REPORTED OBSERVATION"
            elif record.kind == "episode_summary":
                label = "LEARNED RESOLUTION (user-confirmed episode)"
            elif record.kind == "session_summary":
                label = "PRIOR SESSION DIGEST (model-summarized, user-stored)"
            else:
                label = record.kind.upper()

            candidate = (
                f"\n{label}: key={record.key}; value={record.value}; "
                f"confidence={record.confidence:.2f}; source={record.source}; "
                f"confirmations={record.confirmations}; validations={record.validations}"
            )
            if len("\n".join(lines) + candidate) > max_chars:
                break
            lines.append(candidate)

        return "\n".join(lines)

    def summary(self, *, personal_only=True):
        records = self.store.records()
        if personal_only:
            records = [
                record
                for record in records
                if record.kind in {"fact", "preference", "note"}
            ]
        records.sort(key=lambda item: (item.kind, item.key, item.updated_at))
        return records

    def forget(self, query):
        if not str(query or "").strip():
            raise ValueError("Tell me what memory to forget")
        return self.store.forget(query)
