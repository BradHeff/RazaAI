# FortiGate IPsec tunnel down :  systematic, read-only troubleshooting order

Work from the outside in and do not change configuration until the failing layer is proven. Each step names the evidence that settles it.

## 1. Underlay reachability (before IKE)
- Can the two gateways reach each other on their public/WAN addresses? `execute ping <peer-ip>` from the FortiGate, and check the WAN interface is up with an address and default route (`get router info routing-table all`).
- Is UDP 500 (IKE), UDP 4500 (NAT-T) and ESP (IP protocol 50) allowed end to end? An upstream firewall or ISP CGNAT change is a common silent cause.
- `diagnose sniffer packet any 'host <peer-ip> and (udp port 500 or udp port 4500)' 4` shows whether IKE packets leave and whether anything returns.

## 2. Phase 1 (IKE SA)
- `diagnose vpn ike gateway list` :  is the phase 1 established? `get vpn ike gateway` shows state and the negotiated proposal.
- `diagnose debug application ike -1` + `diagnose debug enable` (then disable) :  mismatches show as `no proposal chosen`, `peer id mismatch`, `PSK auth failed`, or DH group / IKE version disagreement.
- Check both sides agree on IKE version (v1 vs v2), encryption/hash/DH proposal, mode (main/aggressive), local/peer ID, pre-shared key, NAT traversal, and dead-peer-detection. Certificate expiry if using certificate auth.

## 3. Phase 2 (IPsec SA / selectors)
- `diagnose vpn tunnel list name <tunnel>` :  is a phase 2 SA up? Look at `sa=0` (none), the proxy-id / **selectors** (`src:` / `dst:`), and SPI counters.
- Phase 1 up but phase 2 down almost always means the **selectors do not match**: the local and remote subnets (quick mode selectors / traffic selectors) must mirror each other exactly, including 0.0.0.0/0 vs specific subnets. Also compare phase 2 proposal, PFS/DH group, key lifetime, replay detection, and auto-negotiate / auto-keep-alive.
- With dial-up or multiple phase 2 entries, the wrong phase 2 may match first.

## 4. Routing and policy (tunnel up but no traffic)
- **Route**: is there a static route (or BGP/OSPF over the tunnel) sending the remote subnet into the tunnel interface? `get router info routing-table details <remote-subnet>`. Interface-mode tunnels need a route; policy-mode tunnels need the IPsec action in the policy.
- **Policy**: a firewall policy must exist in each direction (LAN → tunnel and tunnel → LAN) with the correct source/destination objects; `diagnose debug flow` with a filter on the test host shows whether traffic is matched by a policy or dropped (`no matching policy`, `reverse path check fail`).
- Asymmetric routing, overlapping subnets, or NAT applied on the tunnel policy can make a healthy tunnel look down.

## 5. Stability problems (flapping rather than down)
- DPD settings, mismatched key lifetimes causing rekey failures, MTU/fragmentation (set `tcp-mss` on the tunnel or enable fragmentation), and ISP path changes. `diagnose vpn ike log-filter` narrows logs to one peer.

## Evidence to collect
- Output of `diagnose vpn ike gateway list` and `diagnose vpn tunnel list name <tunnel>`.
- The exact IKE debug lines around the failure (both sides if possible).
- Routing table entry for the remote subnet and the matching firewall policy IDs.
- Sniffer confirmation that UDP 500/4500 is bidirectional.
