from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .models import IncidentRecord


class IncidentStore:
    """Durable store for Python-validated, closed incidents only."""

    def __init__(self, root: str | Path | None = None):
        project_root = Path(__file__).resolve().parents[2]
        if root is not None:
            self.root = Path(root)
        else:
            from ..config import state_dir
            self.root = state_dir() / "incidents"
        self.records_dir = self.root / "records"
        self.index_path = self.root / "index.json"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._atomic_json(self.index_path, {"version": 1, "records": []})

    def _atomic_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _load_index(self) -> dict:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Incident index is corrupt: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise ValueError("Incident index is malformed")
        return data

    def _next_id(self, index: dict, closed_at: str) -> str:
        day = datetime.fromisoformat(closed_at.replace("Z", "+00:00")).strftime(
            "%Y%m%d"
        )
        prefix = f"INC-{day}-"
        nums = []
        for item in index["records"]:
            incident_id = item.get("incident_id", "") if isinstance(item, dict) else ""
            m = re.fullmatch(re.escape(prefix) + r"(\d{4})", incident_id)
            if m:
                nums.append(int(m.group(1)))
        return f"{prefix}{(max(nums, default=0) + 1):04d}"

    def save(self, record: IncidentRecord) -> IncidentRecord:

        IncidentRecord.from_dict(record.to_dict())
        index = self._load_index()
        for item in index["records"]:
            if item.get("incident_id") == record.incident_id:
                return self.get(record.incident_id)
        path = self.records_dir / f"{record.incident_id}.json"
        if path.exists():
            return self.get(record.incident_id)
        self._atomic_json(path, record.to_dict())
        index["records"].append(
            {
                "incident_id": record.incident_id,
                "playbook_id": record.playbook_id,
                "status": record.status,
                "closed_at": record.closed_at,
                "path": f"records/{record.incident_id}.json",
            }
        )
        self._atomic_json(self.index_path, index)
        return record

    def create(self, **fields) -> IncidentRecord:
        index = self._load_index()
        closed_at = fields["closed_at"]
        incident_id = fields.pop("incident_id", None) or self._next_id(index, closed_at)
        return self.save(IncidentRecord(incident_id=incident_id, **fields))

    def get(self, incident_id: str) -> IncidentRecord:
        if not re.fullmatch(r"INC-\d{8}-\d{4}", incident_id):
            raise ValueError("Invalid incident ID")
        path = self.records_dir / f"{incident_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(incident_id) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Incident record {incident_id} is corrupt: {exc}"
            ) from exc
        return IncidentRecord.from_dict(data)

    def list_records(self) -> list[IncidentRecord]:
        index = self._load_index()
        return [self.get(item["incident_id"]) for item in index["records"]]
