import json
import os
from pathlib import Path


class InfrastructureInventory:
    """Loads explicitly configured infrastructure targets."""

    def __init__(self, path=None):
        project_root = Path(__file__).resolve().parents[2]

        if path is not None:
            self.paths = [Path(path)]
        else:
            self.paths = [
                project_root / "config" / "infrastructure.json",
                project_root / "config" / "server.json",
            ]

        self.data = {"hosts": {}}
        self._load_all()

    def _load_all(self):
        merged = {}

        for path in self.paths:
            if not path.exists():
                continue

            data = json.loads(
                path.read_text(encoding="utf-8")
            )

            for name, item in data.get("hosts", {}).items():
                if name in merged:
                    raise ValueError(
                        f"Duplicate infrastructure host name "
                        f"'{name}' found while merging inventories"
                    )

                merged[name] = item

        self.data = {
            "hosts": merged,
        }

    def list_hosts(self):
        result = []

        for name, item in self.data.get("hosts", {}).items():
            result.append({
                "name": name,
                "type": item.get("type"),
                "host": item.get("host"),
                "port": item.get("port"),
                "site": item.get("site"),
                "platform": item.get("platform"),
                "model": item.get("model"),
                "enabled": bool(item.get("enabled", False)),
            })

        return sorted(
            result,
            key=lambda x: x["name"],
        )

    def get(self, name):
        item = self.data.get("hosts", {}).get(name)

        if item is None:
            raise ValueError(
                f"Unknown infrastructure host: {name}"
            )

        if not item.get("enabled", False):
            raise ValueError(
                f"Infrastructure host '{name}' is disabled"
            )

        return dict(item)

    @staticmethod
    def resolve_secret(env_name):
        if not env_name:
            return None

        value = os.environ.get(env_name)

        if value is None:
            raise ValueError(
                f"Required secret environment variable "
                f"'{env_name}' is not set"
            )

        return value
