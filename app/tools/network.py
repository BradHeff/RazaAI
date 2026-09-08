import socket
import psutil


TOOL_METADATA = {
    "name": "get_network_interfaces",
    "category": "network",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}


def get_network_interfaces():
    """Return information about network interfaces on the local system."""

    interfaces = {}

    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for interface_name, interface_addresses in addresses.items():

        interface_info = {
            "is_up": False,
            "speed_mbps": None,
            "mtu": None,
            "addresses": [],
        }

        if interface_name in stats:
            interface_info["is_up"] = stats[interface_name].isup
            interface_info["speed_mbps"] = stats[interface_name].speed
            interface_info["mtu"] = stats[interface_name].mtu

        for address in interface_addresses:

            if address.family == socket.AF_INET:
                family = "IPv4"

            elif address.family == socket.AF_INET6:
                family = "IPv6"

            elif getattr(psutil, "AF_LINK", None) == address.family:
                family = "MAC"

            else:
                family = str(address.family)

            interface_info["addresses"].append({
                "family": family,
                "address": address.address,
                "netmask": address.netmask,
                "broadcast": address.broadcast,
            })

        interfaces[interface_name] = interface_info

    return interfaces


NETWORK_INTERFACE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_network_interfaces",
        "description": (
            "Get read-only information about network interfaces on the "
            "computer running RazaAI, including interface status, IP "
            "addresses, MAC addresses, MTU, and link speed."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
