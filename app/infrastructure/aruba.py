from .ssh_client import ReadOnlySSHClient

# Aruba CX 6000/6100 family (AOS-CX)
AOS_CX_CHECKS = {
    "system": "show system",
    "version": "show version",
    "interfaces": "show interface brief",
    "vlans": "show vlan",
    "mac_table": "show mac-address-table",
    "lldp": "show lldp neighbor-info",
    "spanning_tree": "show spanning-tree",
    "routes": "show ip route",
    "arp": "show arp",
    "lacp": "show lacp interfaces",
    "poe": "show power-over-ethernet",
}


# Aruba 2930F/2930M family (ArubaOS-Switch)
AOS_SWITCH_CHECKS = {
    "system": "show system",
    "version": "show version",
    "interfaces": "show interfaces brief",
    "vlans": "show vlans",
    "mac_table": "show mac-address",
    "lldp": "show lldp info remote-device",
    "spanning_tree": "show spanning-tree",
    "routes": "show ip route",
    "arp": "show arp",
    "trunks": "show trunks",
}
ARUBA_CHECK_ALIASES = {
    # System
    "system-status": "system",
    "system_status": "system",
    "status": "system",
    # Interfaces
    "interface": "interfaces",
    "interface-status": "interfaces",
    "interface_status": "interfaces",
    "ports": "interfaces",
    "port-status": "interfaces",
    # VLANs
    "vlan": "vlans",
    "vlan-list": "vlans",
    "vlan_list": "vlans",
    # MAC table
    "mac": "mac_table",
    "mac-table": "mac_table",
    "mac_address_table": "mac_table",
    # LLDP
    "neighbors": "lldp",
    "neighbours": "lldp",
    "lldp-neighbors": "lldp",
    "lldp-neighbours": "lldp",
    # Spanning tree
    "stp": "spanning_tree",
    "spanning-tree": "spanning_tree",
    # Routing
    "route": "routes",
    "routing": "routes",
    "routing-table": "routes",
    # ARP
    "arp-table": "arp",
    # PoE
    "power": "poe",
    "power-over-ethernet": "poe",
    # LACP / trunks
    "link-aggregation": "lacp",
    "lag": "lacp",
    "trunk": "trunks",
}


class ArubaReadOnlyAdapter:
    """Read-only SSH adapter for Aruba switches."""

    SUPPORTED_PLATFORMS = {
        "aos-cx",
        "aos-switch",
    }

    def __init__(
        self,
        target,
        password=None,
    ):
        self.target = target

        self.platform = target.get("platform", "").strip().lower()

        if self.platform not in self.SUPPORTED_PLATFORMS:
            raise ValueError(
                "Unsupported Aruba platform "
                f"{self.platform!r}. Expected one of: "
                f"{sorted(self.SUPPORTED_PLATFORMS)}"
            )

        self.client = ReadOnlySSHClient(
            host=target["host"],
            port=target.get("port", 22),
            username=target["username"],
            password=password,
        )

    def _checks(self):
        if self.platform == "aos-cx":
            return AOS_CX_CHECKS

        if self.platform == "aos-switch":
            return AOS_SWITCH_CHECKS

        raise ValueError(f"Unsupported Aruba platform: " f"{self.platform}")

    def run_check(self, check):
        checks = self._checks()

        check = str(check).strip().lower().replace(" ", "-")

        check = ARUBA_CHECK_ALIASES.get(
            check,
            check,
        )

        if check not in checks:
            raise ValueError(
                f"Unsupported Aruba read-only check "
                f"{check!r} for {self.platform}. "
                f"Allowed checks: "
                f"{sorted(checks)}"
            )

        return self.client.execute(checks[check])

    def checks(self):
        return sorted(self._checks())

    @classmethod
    def checks_for_platform(
        cls,
        platform,
    ):
        platform = platform.strip().lower()

        if platform == "aos-cx":
            return sorted(AOS_CX_CHECKS)

        if platform == "aos-switch":
            return sorted(AOS_SWITCH_CHECKS)

        raise ValueError(f"Unsupported Aruba platform: " f"{platform}")
