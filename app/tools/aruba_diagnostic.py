from app.infrastructure import InfrastructureManager


ARUBA_PORT_DIAGNOSTIC_METADATA = {
    "name": "diagnose_aruba_port",
    "category": "infrastructure",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 45,
}


def diagnose_aruba_port(host, port):
    manager = InfrastructureManager()

    return manager.diagnose_aruba_port(
        host_name=host,
        port=port,
    )


ARUBA_PORT_DIAGNOSTIC_DEFINITION = {
    "type": "function",
    "function": {
        "name": "diagnose_aruba_port",
        "description": (
            "Run a targeted read-only Aruba switch-port diagnostic and return "
            "structured live evidence with one prioritised primary finding and "
            "one next check. Prefer this tool for troubleshooting a specific "
            "device or switch port instead of manually requesting many separate "
            "switch checks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Configured Aruba infrastructure target.",
                },
                "port": {
                    "type": "string",
                    "description": (
                        "Port identifier. AOS-CX example: 1/1/5. "
                        "ArubaOS-Switch example: 5 or A1."
                    ),
                },
            },
            "required": ["host", "port"],
        },
    },
}
