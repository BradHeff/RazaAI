from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .models import MemoryRecord, utc_now


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


class MemoryStore:
    """Small file-backed durable memory store."""

    VERSION = 1
    RETENTION_DAYS = int(os.getenv("RAZAAI_MEMORY_RETENTION_DAYS", "30"))
    MAX_RECORDS = int(os.getenv("RAZAAI_MEMORY_MAX_RECORDS", "500"))

    def __init__(self, root=None):
        if root is None:
            root = os.getenv("RAZAAI_MEMORY_DIR")
        if root is None:
            from ..config import state_dir
            root = state_dir() / "memory"
        self.root = Path(root)
        self.path = self.root / "memories.json"

    def _empty(self):
        return {
            "version": self.VERSION,
            "records": [],
        }

    def _load(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._empty()
        except json.JSONDecodeError as exc:
            # Quarantine and rebuild instead of bricking memory.
            # A corrupt file previously raised on every turn forever.
            quarantine = self.root / (
                f"memories.corrupt-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
            )
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                self.path.replace(quarantine)
                print(
                    f"[Memory] WARNING: corrupt store quarantined at {quarantine} ({exc}); "
                    "starting a fresh memory. Inspect the quarantine file for recoverable facts."
                )
            except OSError:
                print(f"[Memory] WARNING: corrupt store could not be quarantined: {exc}")
            return self._empty()

        if payload.get("version") != self.VERSION:
            raise ValueError("Unsupported persistent memory store version")
        if not isinstance(payload.get("records"), list):
            raise ValueError("Malformed persistent memory store")
        return payload

    def _purge_retention(self, records):
        """Enforce the retention rules on a record list."""
        if self.RETENTION_DAYS > 0:
            cutoff = datetime.now(timezone.utc).timestamp() - self.RETENTION_DAYS * 86400
            kept = []
            for record in records:
                if record.state in {"forgotten", "superseded"}:
                    try:
                        stale = datetime.fromisoformat(record.updated_at).timestamp() < cutoff
                    except (ValueError, TypeError):
                        stale = False
                    if stale:
                        continue
                kept.append(record)
            records = kept

        if len(records) <= self.MAX_RECORDS:
            return records

        def _evict_rank(record):
            order = {"forgotten": 0, "superseded": 1, "review": 2, "active": 3}
            return (
                order.get(record.state, 4),
                record.updated_at,  # Oldest first within a state
            )

        protected_kinds = {"fact", "preference", "note", "episode_summary"}
        evictable = [
            record for record in records
            if not (record.state == "active" and record.kind in protected_kinds)
        ]
        overflow = len(records) - self.MAX_RECORDS
        if evictable:
            evictable.sort(key=_evict_rank)
            drop = {record.memory_id for record in evictable[:overflow]}
            records = [record for record in records if record.memory_id not in drop]
        return records

    def _save(self, payload):
        self.root.mkdir(parents=True, exist_ok=True)
        if isinstance(payload.get("records"), list):
            try:
                parsed = [MemoryRecord.from_dict(item) for item in payload["records"]]
                payload = {
                    "version": self.VERSION,
                    "records": [item.to_dict() for item in self._purge_retention(parsed)],
                }
            except (ValueError, TypeError, KeyError):
                pass  # Never block a save because retention failed
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        fd, temp_name = tempfile.mkstemp(
            prefix="memories-",
            suffix=".tmp",
            dir=self.root,
        )
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                handle.write(text)
                handle.flush()
            Path(temp_name).replace(self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            temp = Path(temp_name)
            if temp.exists():
                temp.unlink(missing_ok=True)

    @staticmethod
    def _id(kind, key, value, now):
        digest = hashlib.sha256(
            f"{kind}|{key}|{value}|{now}".encode("utf-8")
        ).hexdigest()[:12].upper()
        return f"MEM-{digest}"

    def records(self, *, include_inactive=False):
        payload = self._load()
        records = []
        # A single malformed record must not brick retrieval.
        for item in payload["records"]:
            try:
                records.append(MemoryRecord.from_dict(item))
            except (ValueError, TypeError, KeyError):
                continue
        if include_inactive:
            return records
        return [record for record in records if record.state == "active"]

    def get(self, memory_id):
        for record in self.records(include_inactive=True):
            if record.memory_id == memory_id:
                return record
        raise KeyError(memory_id)

    def upsert(
        self,
        *,
        kind,
        key,
        value,
        confidence,
        source,
        domain=None,
        tags=(),
        provenance=None,
        validation=False,
    ):
        payload = self._load()
        records = [MemoryRecord.from_dict(item) for item in payload["records"]]
        now = utc_now()
        key_norm = _norm(key)
        value_norm = _norm(value)

        same = next(
            (
                record for record in records
                if record.state == "active"
                and _norm(record.key) == key_norm
                and _norm(record.value) == value_norm
                and record.kind == kind
            ),
            None,
        )

        if same is not None:
            updated = replace(
                same,
                confidence=max(same.confidence, float(confidence)),
                updated_at=now,
                confirmations=same.confirmations + 1,
                validations=same.validations + (1 if validation else 0),
                provenance={
                    **same.provenance,
                    "last_source": source,
                    "last_seen_at": now,
                    **(provenance or {}),
                },
            )
            records = [
                updated if item.memory_id == same.memory_id else item
                for item in records
            ]
            self._save({
                "version": self.VERSION,
                "records": [item.to_dict() for item in records],
            })
            return updated

        conflicting = [
            record for record in records
            if record.state == "active"
            and _norm(record.key) == key_norm
            and _norm(record.value) != value_norm
        ]

        new_id = self._id(kind, key, value, now)

        # Explicit user facts/preferences are latest-value authoritative.
        supersedes = None
        if kind in {"fact", "preference", "note"} and source.startswith("user"):
            for old in conflicting:
                supersedes = old.memory_id
                replacement = replace(
                    old,
                    state="superseded",
                    updated_at=now,
                    contradicted_by=tuple(
                        list(old.contradicted_by) + [new_id]
                    ),
                )
                records = [
                    replacement if item.memory_id == old.memory_id else item
                    for item in records
                ]

        # Technical conflicts are not resolved automatically.
        state = "active"
        if kind in {"technical_observation", "technical_pattern"} and conflicting:
            state = "review"
            for old in conflicting:
                if old.kind in {"technical_observation", "technical_pattern"}:
                    replacement = replace(
                        old,
                        state="review",
                        updated_at=now,
                        contradicted_by=tuple(
                            list(old.contradicted_by) + [new_id]
                        ),
                    )
                    records = [
                        replacement if item.memory_id == old.memory_id else item
                        for item in records
                    ]

        record = MemoryRecord(
            memory_id=new_id,
            kind=kind,
            key=key,
            value=value,
            confidence=float(confidence),
            state=state,
            source=source,
            created_at=now,
            updated_at=now,
            confirmations=1,
            validations=1 if validation else 0,
            domain=domain,
            tags=tuple(tags),
            provenance=provenance or {},
            supersedes=supersedes,
        )
        records.append(record)
        self._save({
            "version": self.VERSION,
            "records": [item.to_dict() for item in records],
        })
        return record

    def forget(self, query):
        query_norm = _norm(query)
        forget_all = query_norm in {
            "all",
            "all memories",
            "everything",
            "everything you remember",
            "everything about me",
        }
        tokens = set(re.findall(r"[a-z0-9]+", query_norm))
        payload = self._load()
        records = [MemoryRecord.from_dict(item) for item in payload["records"]]

        matches = []
        for record in records:
            if record.state not in {"active", "review"}:
                continue
            hay = _norm(f"{record.key} {record.value}")
            hay_tokens = set(re.findall(r"[a-z0-9]+", hay))
            if (
                forget_all
                or query_norm in hay
                or (tokens and tokens.issubset(hay_tokens))
            ):
                matches.append(record)

        now = utc_now()
        ids = {record.memory_id for record in matches}
        records = [
            replace(record, state="forgotten", updated_at=now)
            if record.memory_id in ids
            else record
            for record in records
        ]
        if ids:
            self._save({
                "version": self.VERSION,
                "records": [item.to_dict() for item in records],
            })
        return matches
