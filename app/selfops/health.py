from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR, OLLAMA_MODEL
from ..incidents import IncidentStore, KnowledgeFeedbackEngine
from ..memory import MemoryStore
from .audit import SelfAuditEngine


class OperationalHealthEngine:
    """Aggregate trusted operational state into a compact health model."""

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        self.audit = SelfAuditEngine(self.project_root)
        self.incidents = IncidentStore(self.project_root / "data" / "incidents")
        self.feedback = KnowledgeFeedbackEngine(
            self.incidents,
            project_root=self.project_root,
        )
        self.memory = MemoryStore(self.project_root / "data" / "memory")

    def snapshot(self, *, run_audit: bool = False, audit_mode: str = "quick") -> dict:
        audit = (
            self.audit.run(mode=audit_mode).to_dict()
            if run_audit
            else self.audit.latest()
        )

        try:
            incidents = self.incidents.list_records()
        except (OSError, ValueError, KeyError):
            incidents = []

        try:
            feedback = self.feedback.evaluate()
        except Exception:
            feedback = []

        try:
            memory_records = self.memory.records(include_inactive=True)
        except (OSError, ValueError):
            memory_records = []

        active_memory = [
            item for item in memory_records
            if item.state == "active"
        ]
        review_memory = [
            item for item in memory_records
            if item.state == "review"
        ]

        promoted_attention = [
            item.to_dict()
            for item in feedback
            if item.knowledge_status in {"review", "stale", "watch"}
        ]

        hosts = []
        seen = set()
        try:
            for inventory_name in ("infrastructure.json", "server.json"):
                path = self.project_root / "config" / inventory_name
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                for name, item in data.get("hosts", {}).items():
                    if name in seen:
                        continue
                    seen.add(name)
                    hosts.append(
                        {
                            "name": name,
                            "enabled": bool(item.get("enabled", False)),
                        }
                    )
        except (OSError, json.JSONDecodeError, AttributeError):
            hosts = []

        enabled_hosts = [host for host in hosts if host.get("enabled")]

        status = "healthy"
        attention = []

        if audit and audit.get("status") != "healthy":
            status = "degraded"
            attention.append("Latest RazaAI self-audit reports a fault.")

        if promoted_attention:
            if status == "healthy":
                status = "attention"
            attention.append(
                f"{len(promoted_attention)} promoted knowledge item(s) need attention."
            )

        if review_memory:
            if status == "healthy":
                status = "attention"
            attention.append(
                f"{len(review_memory)} persistent memory item(s) require review."
            )

        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "model": OLLAMA_MODEL,
            "latest_audit": audit,
            "validated_incidents": len(incidents),
            "knowledge_attention": promoted_attention[:5],
            "persistent_memory": {
                "active": len(active_memory),
                "review": len(review_memory),
                "total": len(memory_records),
            },
            "infrastructure": {
                "configured_hosts": len(hosts),
                "enabled_hosts": len(enabled_hosts),
            },
            "attention": attention,
        }
