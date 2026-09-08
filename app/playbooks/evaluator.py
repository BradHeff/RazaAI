import json
import re

from .decision import DiagnosticDecision


class PlaybookDecisionEvaluator:
    """Deterministic evidence gate for playbook steps."""

    def evaluate(self, playbook: dict, session, user_input: str) -> DiagnosticDecision:
        step_number = session.current_step + 1
        evaluators = playbook.get("evaluators", {})
        rule = evaluators.get(str(step_number))

        if not rule:
            return DiagnosticDecision(
                decision="unclear",
                reason=(
                    "This playbook step has no deterministic evaluator yet. "
                    "More explicit evidence is required before Python can advance it."
                ),
                missing_evidence=["explicit check result"],
            )

        evaluator_type = rule.get("type")

        if evaluator_type == "site_ssid_vlan":
            return self._site_ssid_vlan(rule, session, user_input)

        if evaluator_type == "dhcp_lease":
            return self._dhcp_lease(rule, session, user_input)

        if evaluator_type == "fortigate_admin_access":
            return self._fortigate_admin_access(rule, session, user_input)

        if evaluator_type == "fortigate_admin_cert":
            return self._fortigate_admin_cert(rule, session, user_input)

        if evaluator_type == "fortigate_gui_listener":
            return self._fortigate_gui_listener(rule, session, user_input)

        return DiagnosticDecision(
            decision="unclear",
            reason=f"Unsupported evaluator type: {evaluator_type}",
            missing_evidence=["explicit check result"],
        )

    def _all_text(self, session, user_input: str) -> str:
        previous = " ".join(str(item.get("text", "")) for item in session.observations)
        return f"{previous} {user_input}".strip()

    def _site_ssid_vlan(self, rule, session, user_input):
        text = self._all_text(session, user_input)
        lower = text.lower()

        site = None
        for candidate in rule.get("sites", []):
            if candidate.lower() in lower:
                site = candidate
                break

        ssid = None
        ssid_alias = None
        for canonical, aliases in rule.get("ssids", {}).items():
            for alias in aliases:
                if alias.lower() in lower:
                    ssid = canonical
                    ssid_alias = alias
                    break
            if ssid:
                break

        vlan = None
        vlan_match = re.search(
            r"\bvlan\s*[:=#-]?\s*(\d{1,4})\b",
            lower,
            flags=re.I,
        )
        if vlan_match:
            vlan = int(vlan_match.group(1))

        missing = []
        if site is None:
            missing.append("site")
        if ssid is None:
            missing.append("ssid")
        if vlan is None:
            missing.append("access_vlan")

        evidence = {
            "site": site,
            "ssid": ssid,
            "access_vlan": vlan,
        }

        if missing:
            return DiagnosticDecision(
                decision="unclear",
                reason=(
                    "The Access VLAN cannot be validated until the site, "
                    "SSID, and configured VLAN are all known."
                ),
                missing_evidence=missing,
                evidence=evidence,
            )

        expected_map = rule.get("expected", {})
        expected = expected_map.get(site, {}).get(ssid)

        if expected is None:
            return DiagnosticDecision(
                decision="unclear",
                reason=(
                    f"No expected VLAN mapping is defined for " f"{site} / {ssid}."
                ),
                missing_evidence=["known site/SSID VLAN mapping"],
                evidence=evidence,
            )

        evidence["expected_vlan"] = expected

        if vlan != expected:
            return DiagnosticDecision(
                decision="isolated",
                reason=(
                    f"{site} {ssid} is configured for VLAN {vlan}, "
                    f"but the playbook expects VLAN {expected}. "
                    "This mismatch explains successful RADIUS authentication "
                    "followed by failed client network access."
                ),
                evidence=evidence,
            )

        return DiagnosticDecision(
            decision="passed",
            reason=(
                f"{site} {ssid} is configured for VLAN {vlan}, "
                "which matches the expected VLAN."
            ),
            evidence=evidence,
        )

    def _dhcp_lease(self, rule, session, user_input):
        text = self._all_text(session, user_input).lower()

        failure_patterns = [
            r"\b169\.254\.\d{1,3}\.\d{1,3}\b",
            r"\bapipa\b",
            r"\bno (?:dhcp )?lease\b",
            r"\bno ip\b",
            r"\bdoesn'?t get (?:an )?ip\b",
            r"\bdoes not get (?:an )?ip\b",
            r"\bdhcp (?:fails|failed|failure|timeout|times out)\b",
        ]

        for pattern in failure_patterns:
            if re.search(pattern, text):
                return DiagnosticDecision(
                    decision="isolated",
                    reason=(
                        "The client is not receiving a valid DHCP lease on "
                        "the authenticated VLAN, isolating the fault to the "
                        "DHCP/VLAN delivery path."
                    ),
                    evidence={"dhcp": "failed"},
                )

        ipv4 = re.search(
            r"\b(?!(?:169\.254\.))" r"(?:\d{1,3}\.){3}\d{1,3}\b",
            text,
        )

        positive_patterns = [
            r"\bgot (?:an )?ip\b",
            r"\bgets (?:an )?ip\b",
            r"\breceived (?:an )?ip\b",
            r"\bdhcp lease (?:exists|received|works|working)\b",
        ]

        if ipv4 or any(re.search(p, text) for p in positive_patterns):
            return DiagnosticDecision(
                decision="passed",
                reason=(
                    "The client has evidence of a valid DHCP lease, so the "
                    "DHCP lease check did not isolate the fault."
                ),
                evidence={
                    "dhcp": "passed",
                    "ip": ipv4.group(0) if ipv4 else None,
                },
            )

        return DiagnosticDecision(
            decision="unclear",
            reason=(
                "There is not enough evidence yet to determine whether the "
                "client receives a valid DHCP lease."
            ),
            missing_evidence=["client IP address or explicit DHCP lease result"],
        )

    @staticmethod
    def _positive(text: str) -> bool:
        return bool(re.search(
            r"\b(?:yes|correct|confirmed|enabled|allowed|it is|they are|works|working|present|listening|running)\b",
            text,
            re.I,
        ))

    @staticmethod
    def _negative(text: str) -> bool:
        return bool(re.search(
            r"\b(?:no|not|isn['’]?t|is not|aren['’]?t|are not|disabled|missing|wrong|incorrect|invalid|not listening|not running)\b",
            text,
            re.I,
        ))

    def _fortigate_admin_access(self, rule, session, user_input):
        text = self._all_text(session, user_input)
        latest = user_input.lower()

        # Explicit configuration evidence is stronger than a bare yes/no.
        allowaccess_https = bool(re.search(r"set\s+allowaccess[^\n]*\bhttps\b", text, re.I))
        mentions_access = any(term in latest for term in (
            "allowaccess", "http", "https", "interface", "admin port", "admin-sport", "admin-port", "port"
        ))
        wrong_access = bool(re.search(
            r"(?:https?|allowaccess|admin[- ]?s?port|port).{0,40}\b(?:wrong|incorrect|disabled|missing|not enabled|not allowed)\b",
            latest,
            re.I,
        ))
        if wrong_access:
            return DiagnosticDecision(
                decision="isolated",
                reason=(
                    "The reported interface/admin-port configuration is incorrect or does not permit the intended GUI access."
                ),
                evidence={"fault": "admin_access_or_port"},
            )

        if allowaccess_https and ("admin-sport" in text or "admin port" in text or "port" in latest):
            return DiagnosticDecision(
                decision="passed",
                reason="HTTPS administrative access and the intended admin port are reported/configured correctly.",
                evidence={"allowaccess_https": True, "admin_port_confirmed": True},
            )

        # In a stateful playbook, a concise confirmation is valid when it directly
        # answers the current combined check.
        if mentions_access and self._positive(latest) and not self._negative(latest):
            return DiagnosticDecision(
                decision="passed",
                reason="The user confirmed both the configured admin port and interface HTTP/HTTPS administrative access are correct.",
                evidence={"allowaccess_confirmed": True, "admin_port_confirmed": True},
            )

        return DiagnosticDecision(
            decision="unclear",
            reason="Python still needs explicit evidence for both interface allowaccess and the configured admin port.",
            missing_evidence=["interface allowaccess", "configured admin port"],
        )

    def _fortigate_admin_cert(self, rule, session, user_input):
        latest = user_input.lower()
        all_text = self._all_text(session, user_input)

        bad_cert = bool(re.search(
            r"(?:admin[- ]server[- ]cert|certificate|cert).{0,60}\b(?:wrong|incorrect|invalid|missing|broken|bad|expired|sha[- ]?1|not found)\b|"
            r"\b(?:wrong|incorrect|invalid|missing|broken|bad|expired)\b.{0,60}(?:certificate|cert)",
            latest,
            re.I,
        ))
        factory_fix = "admin-server-cert" in latest and "fortinet_factory" in latest
        access_restored = bool(re.search(
            r"\b(?:now|after|then)?\s*(?:i\s+)?(?:have|got|regained|restored)?\s*(?:web|gui|access).{0,30}\b(?:works|working|back|restored|accessible|access)\b|"
            r"\bnow i have access\b|\bweb gui (?:works|is working|loads)\b",
            latest,
            re.I,
        ))

        if bad_cert or (factory_fix and access_restored):
            evidence = {
                "fault": "admin_server_certificate",
                "admin_server_cert_bad": True,
            }
            if factory_fix:
                evidence["factory_certificate_applied"] = True
                evidence["resolution_command"] = 'config system global\nset admin-server-cert "Fortinet_Factory"\nend'
            if access_restored:
                evidence["gui_access_restored"] = True
            if factory_fix and access_restored:
                evidence["resolution_validated"] = True
            return DiagnosticDecision(
                decision="isolated",
                reason=(
                    "The GUI server certificate is reported invalid/incorrect; this matches FortiGate ERR_CONNECTION_REFUSED failure modes and isolates the admin-server-cert as the cause."
                ),
                evidence=evidence,
            )

        # A pasted known-good built-in certificate is positive evidence.
        if "set admin-server-cert" in all_text.lower() and "fortinet_factory" in all_text.lower():
            return DiagnosticDecision(
                decision="passed",
                reason="The configured admin-server-cert is the Fortinet_Factory certificate, so this check did not isolate the fault.",
                evidence={"admin_server_cert": "Fortinet_Factory"},
            )

        if any(term in latest for term in ("certificate", "cert", "admin-server-cert")) and self._positive(latest) and not self._negative(latest):
            return DiagnosticDecision(
                decision="passed",
                reason="The user confirmed the GUI server certificate is valid/correct.",
                evidence={"admin_server_cert_confirmed": True},
            )

        return DiagnosticDecision(
            decision="unclear",
            reason="The GUI server certificate has not yet been explicitly verified.",
            missing_evidence=["show full system global | grep admin-server-cert"],
        )

    def _fortigate_gui_listener(self, rule, session, user_input):
        latest = user_input.lower()
        text = self._all_text(session, user_input).lower()

        pids = re.findall(r"(?m)^\s*(\d{2,7})\s*$", user_input)
        listener_terms = any(term in latest for term in (
            "listening", "listener", "tcpsock", "httpsd", "http_authd", "pidof", "process"
        ))
        missing_listener = bool(re.search(
            r"\b(?:not listening|no listener|nothing listening|httpsd (?:is )?not running|no httpsd|process (?:is )?missing)\b",
            latest,
            re.I,
        ))
        if missing_listener:
            return DiagnosticDecision(
                decision="isolated",
                reason="FortiOS is not listening/running the GUI service on the configured administrative port.",
                evidence={"fault": "gui_listener_or_process", "listener": False},
            )

        if pids or (listener_terms and self._positive(latest) and not self._negative(latest)) or latest.strip() in {"yes", "it is", "it is listening", "yes it is"}:
            return DiagnosticDecision(
                decision="passed",
                reason="The GUI listener/process is present, so process absence did not isolate the fault.",
                evidence={"listener": True, "pids": pids},
            )

        return DiagnosticDecision(
            decision="unclear",
            reason="Python still needs explicit listener/process evidence for the configured GUI port.",
            missing_evidence=["diagnose sys tcpsock or diagnose sys process pidof httpsd output"],
        )

