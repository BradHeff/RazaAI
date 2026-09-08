import json
import tempfile
from pathlib import Path

from app.infrastructure.inventory import (
    InfrastructureInventory,
)


def main():
    print()
    print("========================================")
    print("RazaAI Step 10.2 Inventory Merge Test")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        infra = root / "infrastructure.json"
        servers = root / "server.json"

        infra.write_text(
            json.dumps(
                {
                    "hosts": {
                        "switch01": {
                            "type": "aruba",
                            "host": "10.0.0.2",
                            "enabled": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        servers.write_text(
            json.dumps(
                {
                    "hosts": {
                        "server01": {
                            "type": "linux",
                            "host": "10.0.0.10",
                            "enabled": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        inv = InfrastructureInventory(path=infra)

        assert len(inv.list_hosts()) == 1

        merged = InfrastructureInventory.__new__(InfrastructureInventory)
        merged.paths = [
            infra,
            servers,
        ]
        merged.data = {"hosts": {}}
        merged._load_all()

        names = {item["name"] for item in merged.list_hosts()}

        assert names == {
            "switch01",
            "server01",
        }

    print("[PASS] infrastructure.json + server.json merge")

    print()
    print("========================================")
    print("STEP 10.2 INVENTORY MERGE PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
