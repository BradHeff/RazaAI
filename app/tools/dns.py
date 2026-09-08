import socket
import time

DNS_LOOKUP_METADATA = {
    "name": "dns_lookup",
    "category": "network",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}

def dns_lookup(hostname):
    if not isinstance(hostname, str) or not hostname.strip():
        raise ValueError("hostname must be a non-empty string")
    hostname = hostname.strip()
    start = time.perf_counter()
    try:
        records = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        return {"hostname": hostname, "resolved": False, "addresses": [], "error": str(exc), "lookup_time_ms": round((time.perf_counter() - start) * 1000, 2)}
    addresses = []
    for record in records:
        family = record[0]
        address = record[4][0]
        if family == socket.AF_INET:
            family_name = "IPv4"
        elif family == socket.AF_INET6:
            family_name = "IPv6"
        else:
            continue
        item = {"family": family_name, "address": address}
        if item not in addresses:
            addresses.append(item)
    return {"hostname": hostname, "resolved": bool(addresses), "addresses": addresses, "error": None, "lookup_time_ms": round((time.perf_counter() - start) * 1000, 2)}

DNS_LOOKUP_DEFINITION = {
    "type": "function",
    "function": {
        "name": "dns_lookup",
        "description": "Perform a live DNS lookup using the RazaAI host's configured resolver. Use this to test whether a hostname resolves and obtain its IP addresses.",
        "parameters": {
            "type": "object",
            "properties": {"hostname": {"type": "string", "description": "Hostname or fully-qualified domain name to resolve."}},
            "required": ["hostname"],
        },
    },
}
