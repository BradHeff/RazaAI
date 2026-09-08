import json
import tempfile
from pathlib import Path

from app.infrastructure.inventory import (
    InfrastructureInventory,
)
from app.infrastructure.manager import (
    InfrastructureManager,
)


def main():
    print()
    print("========================================")
    print("RazaAI Step 10 Infrastructure Test")
    print("========================================")
    print()

    data = {
        "hosts": {
            "linux01": {
                "type": "linux",
                "host": "10.0.0.10",
                "port": 22,
                "username": "readonly",
                "enabled": True,
                "site": "test",
            },
            "fg01": {
                "type": "fortigate",
                "host": "10.0.0.1",
                "port": 22,
                "username": "readonly",
                "enabled": True,
                "site": "test",
            },
            "win01": {
                "type": "windows",
                "host": "dc01.test.local",
                "username": "TEST\\readonly",
                "password_env": "TEST_PASSWORD",
                "enabled": True,
                "site": "test",
            },
            "disabled01": {
                "type": "linux",
                "host": "10.0.0.99",
                "username": "readonly",
                "enabled": False,
            },
        }
    }

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "inventory.json"
        path.write_text(
            json.dumps(data),
            encoding="utf-8",
        )

        inventory = InfrastructureInventory(path)
        manager = InfrastructureManager(inventory)

        hosts = manager.list_hosts()

        if len(hosts) != 4:
            raise AssertionError(
                "Inventory did not list all configured hosts"
            )

        print("[PASS] inventory loads configured hosts")

        linux_checks = manager.list_checks("linux01")

        for required in [
            "system",
            "disk",
            "routes",
            "failed_services",
        ]:
            if required not in linux_checks:
                raise AssertionError(
                    f"Missing Linux check: {required}"
                )

        print("[PASS] Linux checks are allowlisted")

        fg_checks = manager.list_checks("fg01")

        for required in [
            "system",
            "routes",
            "bgp_summary",
            "dhcp_leases",
        ]:
            if required not in fg_checks:
                raise AssertionError(
                    f"Missing FortiGate check: {required}"
                )

        print("[PASS] FortiGate checks are allowlisted")

        win_checks = manager.list_checks("win01")

        for required in [
            "system",
            "addresses",
            "routes",
            "dns",
        ]:
            if required not in win_checks:
                raise AssertionError(
                    f"Missing Windows check: {required}"
                )

        print("[PASS] Windows checks are allowlisted")

        try:
            manager.list_checks("disabled01")
        except ValueError:
            print("[PASS] disabled targets are blocked")
        else:
            raise AssertionError(
                "Disabled host was not blocked"
            )

    print()
    print("========================================")
    print("STEP 10 INFRASTRUCTURE TOOLS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
