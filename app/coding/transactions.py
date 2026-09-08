from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from ..config import state_dir


ACTIVE_STATES = frozenset({"applying", "snapshot_ready", "verifying", "repairing", "undoing"})
TERMINAL_STATES = frozenset({"verified", "rolled_back", "rejected", "failed", "undone"})
# Journal retention. Terminal transactions carry full pre-task
# snapshots and would otherwise grow without bound on the Jetson's storage.
MAX_RETAINED_TRANSACTIONS = int(os.getenv("RAZAAI_TX_RETENTION", "40"))


class TransactionJournal:
    """Durable coding-transaction journal scoped to one workspace."""

    SCHEMA = 1

    def __init__(self, workspace_root: Path, root: Path | None = None):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        digest = hashlib.sha256(str(self.workspace_root).encode("utf-8")).hexdigest()[:20]
        self.root = Path(root or (state_dir() / "coding_transactions")) / digest
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_json(
            self.root / "workspace.json",
            {"schema": self.SCHEMA, "workspace": str(self.workspace_root)},
        )

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        try:
            fd = os.open(str(path), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _atomic_bytes(cls, target: Path, payload: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp, target)
            cls._fsync_dir(target.parent)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def _atomic_json(cls, target: Path, data: dict) -> None:
        payload = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        cls._atomic_bytes(target, payload)

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _tx_dir(self, txid: str) -> Path:
        if not txid or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in txid):
            raise ValueError("Invalid coding transaction ID.")
        return self.root / txid

    def _meta_path(self, txid: str) -> Path:
        return self._tx_dir(txid) / "transaction.json"

    def new_id(self) -> str:
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        return f"{stamp}-{uuid.uuid4().hex[:10]}"

    def create_proposal(self, *, request, operations, errors, plan, before_paths, summary) -> str:
        txid = self.new_id()
        tx_dir = self._tx_dir(txid)
        tx_dir.mkdir(parents=True, exist_ok=False)
        now = time.time()
        data = {
            "schema": self.SCHEMA,
            "id": txid,
            "workspace": str(self.workspace_root),
            "state": "pending_approval",
            "created_at": now,
            "updated_at": now,
            "request": str(request or ""),
            "operations": list(operations or []),
            "errors": list(errors or []),
            "plan": dict(plan or {}),
            "before_paths": sorted(str(p) for p in (before_paths or [])),
            "summary": str(summary or ""),
        }
        self._atomic_json(self._meta_path(txid), data)
        self._prune_retention()
        return txid

    def _prune_retention(self):
        """Delete oldest terminal transactions beyond the retention window."""
        try:
            terminal = [
                (float(item.get("updated_at") or 0), str(item.get("id") or ""))
                for item in self.list_transactions()
                if str(item.get("state")) in TERMINAL_STATES
            ]
            terminal.sort()
            excess = len(terminal) - MAX_RETAINED_TRANSACTIONS
            for _, txid in terminal[:max(0, excess)]:
                tx_dir = self.root / txid
                if tx_dir.is_dir():
                    for path in sorted(tx_dir.rglob("*"), reverse=True):
                        try:
                            if path.is_file() or path.is_symlink():
                                path.unlink()
                            elif path.is_dir():
                                path.rmdir()
                        except OSError:
                            break
                    try:
                        tx_dir.rmdir()
                    except OSError:
                        pass
        except OSError:
            pass

    def create_direct(self, *, request, operations, errors, plan, before_paths, summary) -> str:
        txid = self.create_proposal(
            request=request,
            operations=operations,
            errors=errors,
            plan=plan,
            before_paths=before_paths,
            summary=summary,
        )
        self.update(txid, "approved")
        return txid

    def load(self, txid: str) -> dict | None:
        data = self._read_json(self._meta_path(txid))
        if not data or data.get("workspace") != str(self.workspace_root):
            return None
        return data

    def update(self, txid: str, state: str | None = None, **fields) -> dict:
        data = self.load(txid)
        if data is None:
            raise ValueError(f"Unknown coding transaction: {txid}")
        if state is not None:
            data["state"] = str(state)
        data.update(fields)
        data["updated_at"] = time.time()
        self._atomic_json(self._meta_path(txid), data)
        return data

    def save_snapshot(self, txid: str, snapshot: dict) -> dict:
        tx_dir = self._tx_dir(txid)
        snap_dir = tx_dir / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        records = {}
        for index, (path, state) in enumerate(sorted(snapshot.items())):
            existed = bool(state.get("existed"))
            record = {"existed": existed, "file": None, "sha256": None}
            if existed:
                content = str(state.get("content") if state.get("content") is not None else "")
                payload = content.encode("utf-8")
                name = f"{index:04d}.txt"
                self._atomic_bytes(snap_dir / name, payload)
                record["file"] = name
                record["sha256"] = hashlib.sha256(payload).hexdigest()
            records[str(path)] = record
        self._atomic_json(tx_dir / "snapshot.json", {"schema": self.SCHEMA, "files": records})
        self.update(txid, "snapshot_ready", snapshot_paths=sorted(records))
        return records

    def load_snapshot(self, txid: str) -> dict:
        tx_dir = self._tx_dir(txid)
        manifest = self._read_json(tx_dir / "snapshot.json")
        if not manifest or not isinstance(manifest.get("files"), dict):
            raise ValueError(f"Coding transaction {txid} has no valid durable snapshot.")
        snapshot = {}
        for path, record in manifest["files"].items():
            if not isinstance(record, dict):
                raise ValueError(f"Invalid snapshot record for {path}")
            if not record.get("existed"):
                snapshot[path] = {"existed": False, "content": None}
                continue
            name = record.get("file")
            if not name:
                raise ValueError(f"Missing snapshot payload for {path}")
            payload = (tx_dir / "snapshots" / str(name)).read_bytes()
            expected = record.get("sha256")
            if expected and hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f"Snapshot integrity check failed for {path}")
            snapshot[path] = {"existed": True, "content": payload.decode("utf-8")}
        return snapshot

    def list_transactions(self) -> list[dict]:
        items = []
        for path in self.root.iterdir():
            if not path.is_dir():
                continue
            data = self._read_json(path / "transaction.json")
            if data and data.get("workspace") == str(self.workspace_root):
                items.append(data)
        items.sort(key=lambda d: (float(d.get("updated_at") or 0), str(d.get("id") or "")), reverse=True)
        return items

    def latest(self, states: set[str] | frozenset[str] | None = None) -> dict | None:
        for data in self.list_transactions():
            if states is None or str(data.get("state")) in states:
                return data
        return None
