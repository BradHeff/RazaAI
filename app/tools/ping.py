import ipaddress
import re
import subprocess

PING_METADATA = {
    "name": "ping_host",
    "category": "network",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 15,
}

_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")

def _validate_target(target):
    if not isinstance(target, str) or not target.strip():
        raise ValueError("target must be a non-empty hostname or IP address")
    target = target.strip()
    try:
        ipaddress.ip_address(target)
        return target
    except ValueError:
        pass
    if len(target) > 253 or not _HOST_RE.fullmatch(target):
        raise ValueError("target contains invalid hostname characters")
    return target

def ping_host(target, count=4, timeout=2):
    target = _validate_target(target)
    try:
        count = int(count)
        timeout = int(timeout)
    except (TypeError, ValueError):
        raise ValueError("count and timeout must be integers")
    count = max(1, min(count, 10))
    timeout = max(1, min(timeout, 10))
    result = subprocess.run(
        ["ping", "-n", "-c", str(count), "-W", str(timeout), target],
        capture_output=True,
        text=True,
        timeout=min(15, count * timeout + 5),
        check=False,
    )
    output = result.stdout.strip()
    stderr = result.stderr.strip()
    transmitted = received = packet_loss_percent = None
    rtt = None
    packet_match = re.search(r"(\d+)\s+packets transmitted,\s+(\d+)\s+received.*?([\d.]+)%\s+packet loss", output)
    if packet_match:
        transmitted = int(packet_match.group(1))
        received = int(packet_match.group(2))
        packet_loss_percent = float(packet_match.group(3))
    rtt_match = re.search(r"(?:rtt|round-trip).*?=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms", output)
    if rtt_match:
        rtt = {"min_ms": float(rtt_match.group(1)), "avg_ms": float(rtt_match.group(2)), "max_ms": float(rtt_match.group(3)), "mdev_ms": float(rtt_match.group(4))}
    return {
        "target": target,
        "success": result.returncode == 0,
        "return_code": result.returncode,
        "packets_transmitted": transmitted,
        "packets_received": received,
        "packet_loss_percent": packet_loss_percent,
        "rtt": rtt,
        "error": stderr or None,
        "raw_output": output,
    }

PING_DEFINITION = {
    "type": "function",
    "function": {
        "name": "ping_host",
        "description": "Ping a hostname or IP address from the RazaAI host to test basic network reachability, packet loss and round-trip latency.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Hostname or IP address to ping."},
                "count": {"type": "integer", "description": "Number of echo requests, from 1 to 10.", "default": 4},
                "timeout": {"type": "integer", "description": "Per-packet timeout in seconds, from 1 to 10.", "default": 2},
            },
            "required": ["target"],
        },
    },
}
