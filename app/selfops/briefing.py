from __future__ import annotations

from pathlib import Path

from .health import OperationalHealthEngine


class OperationalBriefingEngine:
    """Produce a structured proactive brief for the language model."""

    def __init__(self, project_root: str | Path | None = None):
        self.health = OperationalHealthEngine(project_root)

    def build(self, *, run_audit: bool = False) -> dict:
        snapshot = self.health.snapshot(run_audit=run_audit)

        priorities = []
        audit = snapshot.get("latest_audit") or {}
        for finding in (audit.get("findings") or [])[:5]:
            priorities.append({
                "kind": "self_audit",
                "severity": finding.get("severity", "unknown"),
                "message": finding.get("message", ""),
                "file": finding.get("file"),
                "function": finding.get("function"),
                "line": finding.get("line"),
            })

        for item in snapshot.get("knowledge_attention", [])[:5]:
            priorities.append({
                "kind": "knowledge",
                "severity": (
                    "high"
                    if item.get("knowledge_status") == "review"
                    else "medium"
                ),
                "message": item.get("reason"),
                "fingerprint": item.get("fingerprint"),
                "status": item.get("knowledge_status"),
            })

        return {
            "status": snapshot["status"],
            "summary": (
                "No current RazaAI operational concerns were detected."
                if not priorities
                else f"{len(priorities)} operational item(s) deserve attention."
            ),
            "priorities": priorities,
            "health": snapshot,
        }
