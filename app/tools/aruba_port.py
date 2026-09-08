from app.infrastructure import InfrastructureManager


ARUBA_PORT_METADATA = {
    "name": "inspect_aruba_port",
    "category": "infrastructure",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 45,
}


def inspect_aruba_port(
    host,
    port,
):
    manager = InfrastructureManager()

    return manager.inspect_aruba_port(
        host_name=host,
        port=port,
    )


ARUBA_PORT_DEFINITION = {
    "type": "function",
    "function": {
        "name": "inspect_aruba_port",
        "description": (
            "Inspect one specific port on a configured Aruba switch. "
            "Collects read-only interface status, counters, VLAN information, "
            "MAC addresses, LLDP neighbour data, PoE and aggregation state "
            "where supported. Use this instead of dumping the entire switch "
            "when troubleshooting a specific connected device or port."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": (
                        "Configured Aruba infrastructure target name."
                    ),
                },
                "port": {
                    "type": "string",
                    "description": (
                        "Switch port identifier. AOS-CX example: 1/1/5. "
                        "ArubaOS-Switch example: 5 or A1."
                    ),
                },
            },
            "required": [
                "host",
                "port",
            ],
        },
    },
}
