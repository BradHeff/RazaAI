import re


def _stdout(checks, name):
    item = checks.get(name) or {}
    return (item.get("stdout") or "").strip()


def _match_bool(text, pattern):
    match = re.search(pattern, text, re.I | re.M)

    if not match:
        return None

    return match.group(1).lower() == "up"


def _parse_int(text, pattern):
    match = re.search(pattern, text, re.I | re.M)

    if not match:
        return None

    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


class ArubaPortEvidenceAnalyzer:
    """Convert Aruba port inspection output into structured live evidence."""

    def analyze(self, inspection):
        checks = inspection.get("checks") or {}
        platform = inspection.get("platform")
        port = inspection.get("port")

        status = _stdout(checks, "status")
        counters = _stdout(checks, "counters")
        vlans = _stdout(checks, "vlans")
        macs = _stdout(checks, "macs")
        lldp = _stdout(checks, "lldp")
        poe = _stdout(checks, "poe")

        aggregation = (
            _stdout(checks, "lacp")
            if platform == "aos-cx"
            else _stdout(checks, "trunks")
        )

        evidence = {
            "port": port,
            "platform": platform,
            "admin_up": None,
            "link_up": None,
            "errors_detected": None,
            "rx_drops": None,
            "tx_drops": None,
            "macs_present": None,
            "lldp_neighbor_present": None,
            "lldp_neighbor_count": None,
            "poe_delivering": None,
            "poe_status": None,
            "vlan_summary": None,
            "native_vlan": None,
            "allowed_vlans": None,
            "aggregation_present": None,
        }


        admin_match = re.search(
            r"(?mi)^\s*"
            r"admin(?:istrative)?\s+(?:state|status)"
            r"\s*(?:is|[:=])\s*"
            r"(up|down)\b",
            status,
        )

        if admin_match:
            evidence["admin_up"] = admin_match.group(1).lower() == "up"


        link_match = re.search(
            r"(?mi)^\s*" r"link\s+(?:state|status)" r"\s*(?:is|[:=])\s*" r"(up|down)\b",
            status,
        )

        if link_match:
            evidence["link_up"] = link_match.group(1).lower() == "up"

        if evidence["link_up"] is None:
            interface_match = re.search(
                r"(?mi)^\s*interface\s+\S+\s+is\s+" r"(up|down)\b",
                status,
            )

            if interface_match:
                evidence["link_up"] = interface_match.group(1).lower() == "up"

        if evidence["link_up"] is None:
            old_switch_match = re.search(
                r"(?mi)^\s*port\s+\S+\s+is\s+" r"(up|down)\b",
                status,
            )

            if old_switch_match:
                evidence["link_up"] = old_switch_match.group(1).lower() == "up"


        native_vlan = _parse_int(
            status,
            r"(?mi)^\s*Native VLAN\s*:\s*(\d+)\s*$",
        )

        if native_vlan is not None:
            evidence["native_vlan"] = native_vlan

        allowed_match = re.search(
            r"(?mi)^\s*Allowed VLAN List\s*:\s*(.+?)\s*$",
            status,
        )

        if allowed_match:
            evidence["allowed_vlans"] = allowed_match.group(1).strip()


        rx_drops = None
        tx_drops = None

        if counters and port:
            row_match = re.search(
                rf"(?mi)^\s*{re.escape(str(port))}\s+"
                r"(\d+)\s+"  # RX Bytes
                r"(\d+)\s+"  # RX Packets
                r"(\d+)\s+"  # RX Drops
                r"(\d+)\s+"  # TX Bytes
                r"(\d+)\s+"  # TX Packets
                r"(\d+)\b",  # TX Drops
                counters,
            )

            if row_match:
                rx_drops = int(row_match.group(3))
                tx_drops = int(row_match.group(6))

                evidence["rx_drops"] = rx_drops
                evidence["tx_drops"] = tx_drops

                evidence["errors_detected"] = rx_drops > 0 or tx_drops > 0

        if evidence["errors_detected"] is None and status:
            total_error_values = []

            for label in [
                "Dropped",
                "Errors",
                "CRC/FCS",
                "Collision",
                "Runts",
                "Giants",
            ]:
                match = re.search(
                    rf"(?mi)^\s*{re.escape(label)}\s+"
                    r"(\d+|n/a)\s+"
                    r"(\d+|n/a)"
                    r"(?:\s+(\d+|n/a))?",
                    status,
                )

                if match:
                    for value in match.groups():
                        if value and value.lower() != "n/a":
                            total_error_values.append(int(value))

            if total_error_values:
                evidence["errors_detected"] = any(
                    value > 0 for value in total_error_values
                )

        if macs:
            mac_pattern = re.compile(
                r"\b(?:[0-9a-f]{2}[:-]){5}"
                r"[0-9a-f]{2}\b"
                r"|"
                r"\b[0-9a-f]{4}[.-]"
                r"[0-9a-f]{4}[.-]"
                r"[0-9a-f]{4}\b",
                re.I,
            )

            no_mac_phrases = [
                "no entries",
                "no mac",
                "not found",
                "0 entries",
            ]

            if any(phrase in macs.lower() for phrase in no_mac_phrases):
                evidence["macs_present"] = False
            else:
                evidence["macs_present"] = bool(mac_pattern.search(macs))


        neighbor_count = _parse_int(
            lldp,
            r"(?mi)^\s*Neighbor Entries\s*:\s*(\d+)\s*$",
        )

        if neighbor_count is not None:
            evidence["lldp_neighbor_count"] = neighbor_count

            evidence["lldp_neighbor_present"] = neighbor_count > 0

        elif lldp:
            lower_lldp = lldp.lower()

            if any(
                phrase in lower_lldp
                for phrase in [
                    "no neighbors",
                    "no neighbour",
                    "no neighbor",
                    "no remote device",
                    "not found",
                ]
            ):
                evidence["lldp_neighbor_present"] = False

            elif re.search(
                r"(?mi)^\s*(?:System Name|Neighbor System-Name)" r"\s*:\s*\S+",
                lldp,
            ):
                evidence["lldp_neighbor_present"] = True


        if aggregation:
            lower_aggregation = aggregation.lower()

            if re.search(
                r"\bis\s+not\s+(?:a\s+)?member\s+of\s+lag\b",
                lower_aggregation,
            ):
                evidence["aggregation_present"] = False

            elif re.search(
                r"\bmember\s+of\s+lag\b",
                lower_aggregation,
            ):
                evidence["aggregation_present"] = True

            elif "no trunk" in lower_aggregation:
                evidence["aggregation_present"] = False

            elif "trunk" in lower_aggregation:
                evidence["aggregation_present"] = True


        poe_status_match = re.search(
            r"(?mi)^\s*PoE Port Status\s*:\s*(\S+)",
            poe,
        )

        if poe_status_match:
            evidence["poe_status"] = poe_status_match.group(1).strip().lower()

        power_match = re.search(
            r"(?mi)^\s*PD Power Draw\s*:\s*" r"([0-9.]+)\s*W",
            poe,
        )

        power_draw = None

        if power_match:
            try:
                power_draw = float(power_match.group(1))
            except ValueError:
                power_draw = None

        if evidence["poe_status"]:
            if evidence["poe_status"] in {
                "delivering",
                "powered",
                "on",
            }:
                evidence["poe_delivering"] = True

            elif evidence["poe_status"] in {
                "searching",
                "disabled",
                "fault",
                "off",
            }:
                evidence["poe_delivering"] = False

        if evidence["poe_delivering"] is None and power_draw is not None:
            evidence["poe_delivering"] = power_draw > 0.0

        if vlans:
            evidence["vlan_summary"] = " ".join(vlans.split())[:700]

        if evidence["admin_up"] is False:
            primary = f"Port {port} is administratively disabled."

            severity = "high"

            next_check = (
                "Confirm whether the port is intentionally disabled. "
                "Do not investigate VLANs, DHCP, or routing until the "
                "administrative state is expected to be enabled."
            )

        elif evidence["link_up"] is False:
            primary = f"Port {port} has no physical link."

            severity = "high"

            next_check = (
                "Verify the device is physically connected to this exact "
                "port and check the cable and device power before "
                "investigating VLANs, routing, DHCP, or authentication."
            )

        elif evidence["errors_detected"] is True:
            primary = (
                f"Port {port} is up but interface counters show "
                "packet drops or errors."
            )

            severity = "medium"

            next_check = (
                "Inspect the cable or optic and confirm negotiated "
                "speed/duplex, then compare counters after a short "
                "traffic test."
            )

        elif evidence["link_up"] is True and evidence["macs_present"] is False:
            primary = (
                f"Port {port} is physically up but no MAC address " "is being learned."
            )

            severity = "medium"

            next_check = (
                "Confirm the connected device is transmitting and then "
                "verify the port's VLAN/native VLAN configuration."
            )

        elif evidence["link_up"] is True and evidence["macs_present"] is True:
            primary = f"Port {port} has physical link and is learning " "MAC addresses."

            severity = "info"

            next_check = (
                "Physical Layer 1/2 connectivity is established. "
                "If the endpoint still has a problem, continue with "
                "VLAN, DHCP/addressing, and gateway reachability."
            )

        else:
            primary = (
                f"Port {port} inspection completed, but the available "
                "switch evidence did not isolate a single fault."
            )

            severity = "info"

            next_check = (
                "Review the raw interface status and collect the minimum "
                "additional evidence needed to determine link state."
            )

        return {
            "primary_finding": primary,
            "severity": severity,
            "next_check": next_check,
            "evidence": evidence,
            "raw": inspection,
            "diagnostic_policy": (
                "Treat primary_finding as live infrastructure evidence. "
                "Do not dump unrelated possibilities. Give one next check. "
                "Only widen the investigation if that check does not "
                "isolate or resolve the issue."
            ),
        }
