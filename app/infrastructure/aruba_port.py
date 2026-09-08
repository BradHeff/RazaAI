import re

from .ssh_client import ReadOnlySSHClient


CX_PORT_RE = re.compile(
    r"^\d+/\d+/\d+$"
)

AOS_SWITCH_PORT_RE = re.compile(
    r"^[A-Za-z]?\d+$"
)


def validate_port(
    platform,
    port,
):
    value = str(port).strip()

    if platform == "aos-cx":
        if not CX_PORT_RE.match(value):
            raise ValueError(
                "Invalid AOS-CX port format. "
                "Expected format such as 1/1/5"
            )

    elif platform == "aos-switch":
        if not AOS_SWITCH_PORT_RE.match(value):
            raise ValueError(
                "Invalid ArubaOS-Switch port format. "
                "Expected format such as 1, 24, A1"
            )

    else:
        raise ValueError(
            f"Unsupported Aruba platform: {platform}"
        )

    return value


def _cx_commands(port):
    return {
        "status": f"show interface {port}",
        "counters": f"show interface {port} statistics",
        "vlans": f"show vlan port {port}",
        "macs": f"show mac-address-table port {port}",
        "lldp": f"show lldp neighbor-info {port}",
        "poe": f"show power-over-ethernet {port}",
        "lacp": f"show lacp interfaces {port}",
    }


def _aos_switch_commands(port):
    return {
        "status": f"show interfaces {port}",
        "counters": f"show interfaces {port} counters",
        "vlans": f"show vlans ports {port}",
        "macs": f"show mac-address {port}",
        "lldp": f"show lldp info remote-device {port}",
        "poe": f"show power-over-ethernet {port}",
        "trunks": "show trunks",
    }


class ArubaPortDiagnosticAdapter:
    """Targeted read-only port diagnostics."""

    def __init__(
        self,
        target,
        password=None,
    ):
        self.target = target
        self.platform = (
            target.get("platform", "")
            .strip()
            .lower()
        )

        self.client = ReadOnlySSHClient(
            host=target["host"],
            port=target.get("port", 22),
            username=target["username"],
            password=password,
        )

    def inspect_port(
        self,
        port,
    ):
        port = validate_port(
            self.platform,
            port,
        )

        if self.platform == "aos-cx":
            commands = _cx_commands(port)

        elif self.platform == "aos-switch":
            commands = _aos_switch_commands(port)

        else:
            raise ValueError(
                f"Unsupported Aruba platform: "
                f"{self.platform}"
            )

        results = {}

        for check, command in commands.items():
            try:
                results[check] = (
                    self.client.execute(command)
                )
            except Exception as exc:
                results[check] = {
                    "success": False,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": str(exc),
                }

        return {
            "port": port,
            "platform": self.platform,
            "checks": results,
        }
