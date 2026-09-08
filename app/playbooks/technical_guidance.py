"""Editable technical diagnostic guidance for RazaAI."""

import re

NPS_EAP_ENTRY_RESPONSE = (
    "Start with the NPS/RADIUS evidence before changing the WLAN. "
    "Confirm whether NPS receives the authentication request, then check "
    "the NPS Event Viewer event/reason code and which Network Policy matched. "
    "If NPS rejects the request, verify the policy conditions/constraints, "
    "configured EAP method and NPS server certificate. If NPS returns "
    "Access-Accept but the client still cannot join or obtain connectivity, "
    "then move to post-authentication checks such as the assigned WLAN VLAN, "
    "DHCP and firewall/ACL path. A previous VLAN fix is historical evidence, "
    "not proof of the current cause."
)

VOICE_IPSEC_GUIDANCE = (
    "VOICE OVER IPSEC DIAGNOSTIC METHOD\n"
    "Treat signalling and media as separate paths. One-way audio usually means "
    "SIP signalling succeeded but RTP media is only passing in one direction.\n"
    "- Establish call direction and exactly which side cannot hear.\n"
    "- Verify SIP signalling completes in both directions; do not confuse a "
    "completed call setup with healthy audio.\n"
    "- Identify the actual RTP/media source and destination IPs and UDP ports "
    "negotiated for the call.\n"
    "- Verify bidirectional routes and FortiGate policies for the phone/PBX/media "
    "subnets across the IPsec tunnel.\n"
    "- Verify Phase 2 selectors include every voice/PBX/media subnet used by RTP.\n"
    "- Check NAT is not unintentionally applied to inter-site voice traffic and "
    "that SIP helpers/ALG behavior is understood before changing it.\n"
    "- Use FortiGate session/debug-flow or packet capture on BOTH sites to prove "
    "where RTP stops.\n"
    "- Prefer one test call plus packet evidence over generic configuration changes."
)

NPS_EAP_GUIDANCE = (
    "NPS / EAP WIFI DIAGNOSTIC METHOD\n"
    "Do not jump straight to a remembered VLAN fix. First identify the failing layer.\n"
    "1. Confirm whether NPS receives the RADIUS request from the expected AP/controller.\n"
    "2. If NPS rejects it, use the NPS Event Viewer event/reason code and matched "
    "Network Policy as primary evidence.\n"
    "3. Verify policy conditions/constraints and the configured EAP method "
    "(for example PEAP/MS-CHAPv2 where applicable).\n"
    "4. Verify the NPS server certificate is current, trusted by clients, has "
    "the required Server Authentication purpose, and matches the deployed EAP design.\n"
    "5. Verify the user/computer account and AD authentication path only after "
    "the reason code points there.\n"
    "6. If NPS says Access-Accept/authentication succeeded but the client still "
    "cannot join or obtain connectivity, move AFTER authentication: WLAN VLAN "
    "assignment, DHCP, ACL/firewall policy, and client lease/state.\n"
    "Historical incident resolutions are hypotheses only. Verify the current "
    "WLAN/VLAN and current NPS evidence before recommending a change."
)


def networking_reasoning_guidance(text):
    """Return evidence-first guidance for high-value networking domains."""
    value = str(text or "").casefold()

    voice_terms = ("one way audio", "one-way audio", "nec phone", "sip", "rtp", "voice")
    vpn_terms = ("ipsec", "vpn", "between campus", "between campuses", "inter-campus")
    if any(term in value for term in voice_terms) and any(term in value for term in vpn_terms):
        return VOICE_IPSEC_GUIDANCE

    nps_terms = ("nps", "radius", "eap", "802.1x", "8021x", "peap", "ms-chap", "mschap")
    wifi_terms = ("wifi", "wi-fi", "wlan", "ssid", "wireless")
    if any(term in value for term in nps_terms) and any(term in value for term in wifi_terms):
        return NPS_EAP_GUIDANCE

    return ""


def is_conceptual_fortigate_question(text):
    """Return True when the user wants FortiOS guidance, not local tool execution."""
    value = (text or "").lower()
    if not any(term in value for term in ("fortigate", "fortios", "ipsec", "firewall policy")):
        return False
    conceptual_markers = (
        "what should i verify", "what should i check", "what do i check",
        "what would you check", "how would you troubleshoot",
        "troubleshooting order", "systematic troubleshooting",
        "without changing configuration", "before editing", "before changing",
        "what command", "which command", "console command", "cli command",
        "command to check", "command to verify", "how do i check",
        "how can i check", "how do i verify", "how can i verify",
    )
    return any(marker in value for marker in conceptual_markers)


def fortigate_turn_guidance(text):
    """Return subsystem-specific FortiGate guidance without cross-topic steering."""
    value = (text or "").lower()
    if not any(term in value for term in ("fortigate", "fortios", "ipsec", "firewall policy")):
        return ""

    if "ipsec" in value:
        return (
            "FORTIGATE IPSEC CHECK ORDER\n"
            "- Stay read-only unless the user explicitly requests a change.\n"
            "- Check Phase 1 / IKE first.\n"
            "- Then check Phase 2 selectors/proposals.\n"
            "- Then verify routing, firewall policy, and whether traffic is triggering the tunnel.\n"
            "- Use logs/diagnostics as evidence; do not assume the failed phase.\n"
            "- If the user asks for an order/process, cover every phase above; a single "
            "'check Phase 1 first' line is not an answer.\n"
            "- Always name the evidence: diagnose vpn ike gateway list, diagnose vpn tunnel list, "
            "IKE debug, routing table entry, matched policy ID."
        )

    admin_markers = (
        "gui", "web interface", "web gui", "admin interface", "admin access",
        "administrative access", "https", "http", "connection refused",
        "admin-sport", "admin-port", "allowaccess", "port 443", "port 80",
    )
    if any(marker in value for marker in admin_markers):
        return (
            "FORTIGATE ADMIN GUI ACCESS\n"
            "This is FortiGate local administrative access, not forwarded firewall-policy traffic.\n"
            "- Use FortiOS CLI commands; do not suggest Linux tcpdump. FortiGate packet capture is "
            "`diagnose sniffer packet ...`.\n"
            "- Verify the ingress interface permits HTTPS/HTTP with `show system interface <interface>` "
            "and inspect `set allowaccess ...` (normally HTTPS is preferred).\n"
            "- Verify configured admin ports with `show full system global | grep admin-port` and "
            "`show full system global | grep admin-sport` (defaults are HTTP 80 and HTTPS 443).\n"
            "- Before restarting GUI processes, inspect the configured certificate with "
            "`show full system global | grep admin-server-cert`. Fortinet documents GUI connection-refused "
            "failures caused by a missing/invalid admin certificate; when evidence supports that cause, the "
            "documented recovery is `config system global`, `set admin-server-cert \"Fortinet_Factory\"`, `end`.\n"
            "- To inspect listening TCP sockets, use `diagnose sys tcpsock` and look for the configured "
            "admin port / httpsd listener.\n"
            "- If the browser gets connection refused/RST, capture the attempt with "
            "`diagnose sniffer packet any 'host <client-ip> and port <admin-port>' 4 0 l`.\n"
            "- Do not discuss web-filter categories unless the user is troubleshooting web filtering."
        )

    if "firewall policy" in value or re.search(r"\bpolicy\b", value):
        return (
            "FORTIGATE POLICY EVIDENCE\n"
            "- Before editing a policy, verify policy order and interface pair.\n"
            "- Verify source, destination, service, schedule/NAT as relevant.\n"
            "- Check routing plus session/log/debug-flow or matched policy ID evidence.\n"
            "- Do not change policy from symptoms alone.\n"
            "- Every answer must end with an 'Evidence:' line naming the session table, "
            "forward-traffic log, route lookup, debug flow, or policy ID that confirms it; "
            "a hypothesis without evidence is incomplete."
        )

    return (
        "FORTIGATE GENERAL\n"
        "Use FortiOS-native commands and keep the answer scoped to the subsystem the user named. "
        "Do not substitute firewall-policy, web-filter, VPN, or routing diagnostics without evidence "
        "that those subsystems are involved."
    )
