from .ssh_client import ReadOnlySSHClient


FORTIGATE_CHECKS = {
    "system": "get system status",
    "interfaces": "get system interface physical",
    "addresses": "diagnose ip address list",
    "routes": "get router info routing-table all",
    "bgp_summary": "get router info bgp summary",
    "arp": "get system arp",
    "dhcp_leases": (
        "execute dhcp lease-list"
    ),
}


class FortiGateReadOnlyAdapter:
    def __init__(self, target, password=None):
        self.target = target
        self.client = ReadOnlySSHClient(
            host=target["host"],
            port=target.get("port", 22),
            username=target["username"],
            password=password,
        )

    def run_check(self, check):
        if check not in FORTIGATE_CHECKS:
            raise ValueError(
                f"Unsupported FortiGate read-only check: {check}"
            )

        return self.client.execute(
            FORTIGATE_CHECKS[check]
        )

    @staticmethod
    def checks():
        return sorted(FORTIGATE_CHECKS)
