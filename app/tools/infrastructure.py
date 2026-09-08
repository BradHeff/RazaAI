from app.infrastructure import InfrastructureManager


LIST_INFRASTRUCTURE_METADATA = {
    "name": "list_infrastructure",
    "category": "infrastructure",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}


def list_infrastructure(host=None):
    """List configured targets. No credentials are read and no network connection is attempted."""
    manager = InfrastructureManager()
    hosts = manager.list_hosts()

    if host:
        wanted = str(host).strip().casefold()
        matches = [
            item
            for item in hosts
            if str(item.get("name", "")).casefold() == wanted
        ]

        if not matches:
            raise ValueError(
                f"Unknown infrastructure host: {host}"
            )

        return {
            "hosts": matches,
        }

    return {
        "hosts": hosts,
    }


LIST_INFRASTRUCTURE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_infrastructure",
        "description": (
            "List explicitly configured infrastructure "
            "targets that RazaAI may inspect read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": (
                        "Optional configured inventory name to look up. "
                        "Omit to list all configured targets."
                    ),
                },
            },
            "required": [],
        },
    },
}


RUN_INFRASTRUCTURE_CHECK_METADATA = {
    "name": "run_infrastructure_check",
    "category": "infrastructure",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 30,
}


def run_infrastructure_check(host, check):
    manager = InfrastructureManager()

    return manager.run_check(
        host_name=host,
        check=check,
    )


RUN_INFRASTRUCTURE_CHECK_DEFINITION = {
    "type": "function",
    "function": {
        "name": "run_infrastructure_check",
        "description": (
            "Run one predefined read-only diagnostic check "
            "against an explicitly configured Linux, FortiGate "
            "or Windows infrastructure target. Arbitrary commands "
            "are not supported."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": (
                        "Configured infrastructure inventory name."
                    ),
                },
                "check": {
                    "type": "string",
                    "description": (
                        "Allowlisted diagnostic check name."
                    ),
                },
            },
            "required": [
                "host",
                "check",
            ],
        },
    },
}
