import subprocess

ROUTING_TABLE_METADATA = {
    "name": "get_routing_table",
    "category": "network",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}

def get_routing_table():
    output = {}
    for family, command in {
        "ipv4": ["ip", "-4", "route", "show"],
        "ipv6": ["ip", "-6", "route", "show"],
    }.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            # Never raise out of a read-only fact tool; report the gap.
            output[family] = {"success": False, "error": f"{command[0]} unavailable: {exc}", "routes": []}
            continue
        if result.returncode != 0:
            output[family] = {"success": False, "error": result.stderr.strip() or f"Command returned {result.returncode}", "routes": []}
        else:
            output[family] = {"success": True, "routes": [line.strip() for line in result.stdout.splitlines() if line.strip()]}
    return output

ROUTING_TABLE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_routing_table",
        "description": "Inspect the live IPv4 and IPv6 routing tables on the RazaAI host. Use this to diagnose gateways, routes and network reachability.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
