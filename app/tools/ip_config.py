import socket
import psutil
import subprocess

TOOL_METADATA = {
    "name": "get_ip_configuration",
    "category": "network",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}


def _get_default_gateway():
    """Return the default IPv4 gateway using the Linux ip command."""

    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            return None

        line = result.stdout.strip()

        if not line:
            return None

        parts = line.split()

        if "via" in parts:
            index = parts.index("via")

            if index + 1 < len(parts):
                return parts[index + 1]

        return None

    except Exception:
        return None


def _get_dns_servers():
    """Read configured DNS servers."""

    dns_servers = []

    try:
        with open(
            "/etc/resolv.conf",
            "r",
            encoding="utf-8",
        ) as file:

            for line in file:

                line = line.strip()

                if not line.startswith("nameserver"):
                    continue

                parts = line.split()

                if len(parts) >= 2:
                    dns_servers.append(parts[1])

    except OSError:
        pass

    return dns_servers


def get_ip_configuration():
    """Return diagnostic IP configuration for the local machine."""

    interfaces = {}

    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for interface_name, interface_addresses in addresses.items():

        is_up = stats.get(interface_name).isup if interface_name in stats else False

        ipv4 = []
        ipv6 = []

        for address in interface_addresses:

            if address.family == socket.AF_INET:

                ipv4.append(
                    {
                        "address": address.address,
                        "netmask": address.netmask,
                        "broadcast": address.broadcast,
                    }
                )

            elif address.family == socket.AF_INET6:

                ipv6.append(
                    {
                        "address": address.address,
                        "netmask": address.netmask,
                    }
                )

        if ipv4 or ipv6:

            interfaces[interface_name] = {
                "is_up": is_up,
                "ipv4": ipv4,
                "ipv6": ipv6,
            }

    return {
        "hostname": socket.gethostname(),
        "interfaces": interfaces,
        "default_gateway": _get_default_gateway(),
        "dns_servers": _get_dns_servers(),
    }


IP_CONFIGURATION_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_ip_configuration",
        "description": (
            "Get the current IP configuration of the computer running "
            "RazaAI, including active interface addresses, default "
            "gateway, DNS servers, and hostname. Use this when "
            "diagnosing local network configuration."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
