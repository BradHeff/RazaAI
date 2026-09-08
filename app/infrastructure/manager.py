from .inventory import InfrastructureInventory
from .linux import LinuxReadOnlyAdapter
from .fortigate import FortiGateReadOnlyAdapter
from .windows import WindowsReadOnlyAdapter
from .aruba import ArubaReadOnlyAdapter
from .aruba_port import ArubaPortDiagnosticAdapter
from .aruba_evidence import ArubaPortEvidenceAnalyzer


class InfrastructureManager:
    """Dispatches explicitly allowlisted read-only checks."""

    def __init__(self, inventory=None):
        self.inventory = (
            inventory
            if inventory is not None
            else InfrastructureInventory()
        )

    def list_hosts(self):
        return self.inventory.list_hosts()

    def list_checks(self, host_name):
        target = self.inventory.get(host_name)
        target_type = target.get("type")

        if target_type == "linux":
            return LinuxReadOnlyAdapter.checks()

        if target_type == "fortigate":
            return FortiGateReadOnlyAdapter.checks()

        if target_type == "windows":
            return WindowsReadOnlyAdapter.checks()

        if target_type == "aruba":
            return (
                ArubaReadOnlyAdapter
                .checks_for_platform(
                    target.get("platform", "")
                )
            )

        raise ValueError(
            f"Unsupported infrastructure type: "
            f"{target_type}"
        )

    def _password_for(self, target):
        if not target.get("password_env"):
            return None

        return self.inventory.resolve_secret(
            target["password_env"]
        )

    def run_check(self, host_name, check):
        target = self.inventory.get(host_name)
        target_type = target.get("type")
        password = self._password_for(target)

        if target_type == "linux":
            adapter = LinuxReadOnlyAdapter(
                target,
                password=password,
            )

        elif target_type == "fortigate":
            adapter = FortiGateReadOnlyAdapter(
                target,
                password=password,
            )

        elif target_type == "aruba":
            adapter = ArubaReadOnlyAdapter(
                target,
                password=password,
            )

        elif target_type == "windows":
            if password is None:
                raise ValueError(
                    "Windows WinRM target requires "
                    "password_env"
                )

            adapter = WindowsReadOnlyAdapter(
                target,
                password=password,
            )

        else:
            raise ValueError(
                f"Unsupported infrastructure type: "
                f"{target_type}"
            )

        result = adapter.run_check(check)

        return {
            "host": host_name,
            "type": target_type,
            "site": target.get("site"),
            "check": check,
            **result,
        }

    def inspect_aruba_port(self, host_name, port):
        target = self.inventory.get(host_name)

        if target.get("type") != "aruba":
            raise ValueError(
                f"Host '{host_name}' is not an Aruba target"
            )

        password = self._password_for(target)

        adapter = ArubaPortDiagnosticAdapter(
            target,
            password=password,
        )

        result = adapter.inspect_port(port)

        return {
            "host": host_name,
            "type": "aruba",
            "site": target.get("site"),
            "model": target.get("model"),
            **result,
        }

    def diagnose_aruba_port(self, host_name, port):
        inspection = self.inspect_aruba_port(
            host_name=host_name,
            port=port,
        )

        analyzer = ArubaPortEvidenceAnalyzer()

        analysis = analyzer.analyze(
            inspection
        )

        return {
            "host": host_name,
            "site": inspection.get("site"),
            "model": inspection.get("model"),
            "port": inspection.get("port"),
            **analysis,
        }
