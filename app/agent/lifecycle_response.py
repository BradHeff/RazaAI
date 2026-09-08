"""Deterministic user-facing responses for Python-owned incident lifecycle turns."""

_VALIDATION_LABELS = {
    "dhcp": "DHCP/IP assignment",
    "gateway": "Gateway reachability",
    "connectivity": "Internet/end-to-end connectivity",
}


def _label(key: str) -> str:
    return _VALIDATION_LABELS.get(key, key.replace("_", " ").title())


def render_lifecycle_response(session, decision, persisted_incident=None) -> str:
    """Render lifecycle state without asking the LLM to interpret it."""
    status = getattr(session, "status", "unknown")
    action = getattr(decision, "action", "")
    evidence = dict(getattr(session, "validation_evidence", {}) or {})
    missing = list(getattr(decision, "missing_evidence", []) or [])

    if status == "closed" and action == "close":
        ctx = dict(getattr(session, "lifecycle_context", {}) or {})
        resolution = dict(getattr(session, "resolution_evidence", {}) or {})

        if getattr(session, "playbook_id", "") == "fortigate-admin-gui-refused":
            command = resolution.get("resolution_command") or ctx.get("resolution_command")
            lines = [
                "Incident resolved and validated.",
                "",
                "Root cause:",
                "- The FortiGate administrative GUI was refusing connections because the configured `admin-server-cert` was incorrect/invalid.",
                "",
                "Resolution:",
            ]
            if command:
                lines += ["```text", str(command), "```"]
            else:
                lines.append('- Restored the GUI certificate to `Fortinet_Factory`.')
            lines += [
                "",
                "Validation:",
                "- HTTPS GUI access: PASS",
            ]
            if persisted_incident is not None:
                lines += ["", f"Incident memory: {persisted_incident.incident_id}"]
            return "\n".join(lines)

        site = ctx.get("site")
        ssid = ctx.get("ssid")
        old_vlan = ctx.get("access_vlan")
        expected_vlan = ctx.get("expected_vlan")
        configured_vlan = resolution.get("configured_vlan", expected_vlan)

        lines = ["Incident resolved and validated.", ""]
        if site and ssid and old_vlan is not None and expected_vlan is not None:
            lines += [
                "Root cause:",
                f"- {ssid} at {site} used Access VLAN {old_vlan} instead of VLAN {expected_vlan}.",
                "",
            ]
        if configured_vlan is not None:
            target = f"{ssid} WLAN" if ssid else "WLAN"
            lines += [
                "Resolution:",
                f"- Changed {target} Access VLAN to VLAN {configured_vlan}.",
                "",
            ]
        lines += ["Validation:"]
        for key in ("dhcp", "gateway", "connectivity"):
            state = "PASS" if evidence.get(key) is True else "FAIL"
            lines.append(f"- {_label(key)}: {state}")
        if persisted_incident is not None:
            lines += ["", f"Incident memory: {persisted_incident.incident_id}"]
        return "\n".join(lines)

    if status == "waiting_for_validation":
        if getattr(session, "playbook_id", "") == "fortigate-admin-gui-refused":
            gui_state = evidence.get("gui_access")
            state = "PASS" if gui_state is True else ("FAIL" if gui_state is False else "PENDING")
            lines = [
                "The reported certificate fix has been accepted, but the incident is not resolved until GUI access is verified.",
                "",
                "Validation status:",
                f"- HTTPS GUI access: {state}",
            ]
            if action == "validation_failed":
                lines += ["", "The GUI is still failing, so the incident remains open."]
            else:
                lines += ["", "Check next: Open the FortiGate HTTPS login page and confirm it loads."]
            return "\n".join(lines)

        lines = [
            "The reported fix has been accepted, but the incident is not resolved yet.",
            "",
            "Validation status:",
        ]
        for key in ("dhcp", "gateway", "connectivity"):
            value = evidence.get(key)
            state = (
                "PASS" if value is True else ("FAIL" if value is False else "PENDING")
            )
            lines.append(f"- {_label(key)}: {state}")

        if action == "validation_failed":
            failed = [key for key, value in evidence.items() if value is False]
            lines += ["", "Validation failed:"]
            for key in failed:
                lines.append(f"- {_label(key)}")
            lines += ["", "The incident remains open."]
            return "\n".join(lines)

        if not missing:
            missing = [
                key
                for key in ("dhcp", "gateway", "connectivity")
                if evidence.get(key) is not True
            ]
        if missing:
            lines += ["", "Still required:"]
            for key in missing:
                lines.append(f"- {_label(key)}")
            lines += ["", f"Check next: Confirm {_label(missing[0]).lower()}."]
        return "\n".join(lines)

    if status == "waiting_for_fix":
        lines = ["The incident is not resolved yet."]
        if missing:
            lines += ["", "Still required:"]
            for item in missing:
                lines.append(f"- {item}")
        else:
            lines += ["", "Still required:", "- Explicit corrective change"]
        return "\n".join(lines)

    # Safe fallback: never promote an unknown lifecycle state to resolved.
    return (
        "The incident remains open. Python has not completed the required "
        "resolution and validation lifecycle yet."
    )
