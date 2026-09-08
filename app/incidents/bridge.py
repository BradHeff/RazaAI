from __future__ import annotations

from .models import utc_now


class IncidentLifecycleBridge:
    """Converts authoritative closed playbook state into durable incident facts."""

    def __init__(self, store):
        self.store = store

    def persist_closed(self, *, playbook: dict, session, category: str | None = None):
        if session.status != "closed":
            return None
        validation = dict(getattr(session, "validation_evidence", {}) or {})
        required = self._required_validation(playbook)
        if any(validation.get(key) is not True for key in required):
            return None
        if getattr(session, "persisted_incident_id", None):
            return self.store.get(session.persisted_incident_id)

        facts = self._facts(playbook, session)
        if not facts:
            return None
        now = utc_now()
        record = self.store.create(
            status="resolved",
            category=category,
            site=facts.get("site"),
            system=facts.get("system"),
            symptom=getattr(session, "initial_query", "") or facts["symptom"],
            root_cause=facts["root_cause"],
            resolution=facts["resolution"],
            validation={key: True for key in required},
            evidence_source="validated_playbook",
            playbook_id=playbook["id"],
            created_at=getattr(session, "created_at", now),
            closed_at=now,
            evidence={
                "lifecycle_context": dict(
                    getattr(session, "lifecycle_context", {}) or {}
                ),
                "resolution_evidence": dict(
                    getattr(session, "resolution_evidence", {}) or {}
                ),
                "validation_evidence": validation,
            },
        )
        session.persisted_incident_id = record.incident_id
        return record

    def _required_validation(self, playbook: dict) -> list[str]:
        if playbook.get("id") == "wifi-nps-no-connectivity":
            return ["dhcp", "gateway", "connectivity"]
        if playbook.get("id") == "fortigate-admin-gui-refused":
            return ["gui_access"]

        return []

    def _facts(self, playbook: dict, session):
        if playbook.get("id") == "fortigate-admin-gui-refused":
            ctx = dict(getattr(session, "lifecycle_context", {}) or {})
            fix = dict(getattr(session, "resolution_evidence", {}) or {})
            if ctx.get("fault") != "admin_server_certificate":
                return None
            command = fix.get("resolution_command") or ctx.get("resolution_command")
            if not command:
                return None
            return {
                "site": None,
                "system": "FortiGate administrative GUI",
                "symptom": "FortiGate responds to ping/SSH but the administrative web GUI returns connection refused",
                "root_cause": "The configured FortiGate admin-server-cert was incorrect or invalid for GUI service startup",
                "resolution": str(command),
            }

        if playbook.get("id") != "wifi-nps-no-connectivity":
            return None
        ctx = dict(getattr(session, "lifecycle_context", {}) or {})
        fix = dict(getattr(session, "resolution_evidence", {}) or {})
        site, ssid = ctx.get("site"), ctx.get("ssid")
        wrong, expected = ctx.get("access_vlan"), ctx.get("expected_vlan")
        configured = fix.get("configured_vlan")
        if not all(v is not None for v in (site, ssid, wrong, expected, configured)):
            return None
        if configured != expected or wrong == expected:
            return None
        return {
            "site": site,
            "system": ssid,
            "symptom": "NPS authentication succeeds but Wi-Fi client cannot join",
            "root_cause": f"{ssid} at {site} used Access VLAN {wrong} instead of VLAN {expected}",
            "resolution": f"Changed {ssid} WLAN Access VLAN to VLAN {configured}",
        }
