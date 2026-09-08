# Client has a 169.254.x.x (APIPA) address :  DHCP failure troubleshooting

## What it means
A 169.254.0.0/16 address is **APIPA / link-local**: Windows (and most clients) self-assign it when a DHCP request gets **no DHCP offer**. The client is not misconfigured so much as unanswered. It will never reach its gateway because there is no gateway on the link-local range. The question is always: why did no DHCP server answer on this segment?

## Check first, in order
1. **Is it one client or the whole VLAN?** One client → client/port problem. Many clients on the same VLAN → DHCP service, relay, or scope problem. `ipconfig /all` on the affected client shows `Autoconfiguration Enabled`, no `DHCP Server` line and no lease :  confirm that before anything else.
2. **Physical/link and the port's VLAN.** Is the switch port up, and is it in the VLAN the client is supposed to be in? A port placed in the wrong VLAN (or a native-VLAN / trunk tagging mismatch) puts the client on a segment with no DHCP server and produces exactly this symptom. Check the port's access VLAN and any 802.1X/NAC dynamic VLAN assignment (a failed auth often lands the client in a guest or quarantine VLAN).
3. **Does a DHCP server serve this VLAN?** Either the server has an interface on the VLAN or the gateway has a **DHCP relay / IP helper** (`ip helper-address`, FortiGate "DHCP relay", Aruba `dhcp-relay`) pointing at it. A missing or wrong relay address after a VLAN/gateway change is the most common cause on multi-VLAN networks.
4. **Is the scope alive?** On the DHCP server: is there a **scope** for that subnet, is it **active**, is the **lease pool exhausted** (address-pool statistics / "no free leases"), and in Windows Server is the DHCP service running and **authorized** in Active Directory? An exhausted pool or a deactivated scope answers nobody.
5. **Is the server actually receiving the discover?** DHCP server audit log (Windows: `%SystemRoot%\System32\dhcp\DhcpSrvLog-*.log`, ISC: syslog) shows DISCOVER/OFFER per MAC. No DISCOVER for this MAC = the request never arrives (relay, VLAN, firewall, or a rogue/blocking switch feature such as DHCP snooping marking the port untrusted). DISCOVER with no OFFER = scope/pool/reservation problem.
6. **Rogue DHCP or snooping.** DHCP snooping with the uplink not marked trusted drops legitimate offers; a rogue DHCP server hands out wrong addresses (a different symptom, but check the snooping binding table while you are there).
7. **Client-side last.** `ipconfig /release` + `/renew`, a stale static entry, disabled DHCP Client service, or a misbehaving VPN/virtual adapter. Only after the segment has been cleared.

## Evidence to collect
- `ipconfig /all` from the client (DHCP enabled? server? lease?).
- Switch port status and VLAN membership for that client's port; NAC/802.1X assignment if used.
- The gateway's DHCP relay / IP helper configuration for that VLAN.
- DHCP server scope state and address-pool utilisation for the subnet.
- DHCP server audit log lines for the client's MAC (DISCOVER / OFFER / NAK).
