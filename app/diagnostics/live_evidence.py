import re

from app.infrastructure import InfrastructureManager


ARUBA_HOST_RE = re.compile(
    r"\b([A-Za-z0-9_.-]*aruba[A-Za-z0-9_.-]*)\b",
    re.I,
)

AOS_CX_PORT_RE = re.compile(
    r"\b(\d+/\d+/\d+)\b"
)


class LiveEvidenceCollector:
    """Deterministic live-evidence collection for diagnostic playbooks."""

    def __init__(self):
        self.infrastructure = InfrastructureManager()

    def collect(
        self,
        user_input,
        playbook=None,
    ):
        if not playbook:
            return None

        playbook_id = playbook.get("id")

        if playbook_id == "aruba-port-connectivity":
            return self._collect_aruba_port(
                user_input
            )

        return None

    def _collect_aruba_port(self, user_input):
        host_match = ARUBA_HOST_RE.search(
            user_input
        )

        port_match = AOS_CX_PORT_RE.search(
            user_input
        )

        if not host_match or not port_match:
            return {
                "collected": False,
                "reason": (
                    "Aruba port diagnosis requires both a configured "
                    "Aruba host name and a switch port identifier."
                ),
                "missing": [
                    name
                    for name, match in [
                        ("host", host_match),
                        ("port", port_match),
                    ]
                    if match is None
                ],
            }

        host = host_match.group(1)
        port = port_match.group(1)

        try:
            result = (
                self.infrastructure
                .diagnose_aruba_port(
                    host,
                    port,
                )
            )
        except Exception as exc:
            return {
                "collected": False,
                "host": host,
                "port": port,
                "reason": str(exc),
                "missing": [],
            }

        return {
            "collected": True,
            "kind": "aruba_port_diagnostic",
            "host": host,
            "port": port,
            "result": result,
        }

    @staticmethod
    def guidance(evidence):
        if not evidence:
            return ""

        if not evidence.get("collected"):
            return (
                "LIVE EVIDENCE COLLECTION\n"
                "Python could not collect the requested live evidence.\n"
                f"Reason: {evidence.get('reason')}\n"
                f"Missing: {evidence.get('missing', [])}\n"
                "Ask only for the missing information or explain the "
                "connection/tool failure. Do not pretend the check ran."
            )

        result = evidence["result"]

        return (
            "LIVE INFRASTRUCTURE EVIDENCE\n"
            f"Host: {evidence['host']}\n"
            f"Port: {evidence['port']}\n"
            f"Primary finding: {result.get('primary_finding')}\n"
            f"Severity: {result.get('severity')}\n"
            f"Next check: {result.get('next_check')}\n"
            f"Structured evidence: {result.get('evidence')}\n\n"
            "This data was collected automatically by Python from the "
            "configured read-only infrastructure tool. Treat it as "
            "'From live tools'. Do NOT ask the user to run "
            "diagnose_aruba_port again. Lead with the primary finding "
            "and give only the returned next_check unless the user asks "
            "for deeper detail."
        )
