# FortiGate firewall policy not matching traffic :  verify before editing

## Principle
A policy that "does not match" is almost always matched by a *different* policy first, or the traffic never reaches the policy lookup (routing, interface pair, or implicit deny). Prove which policy the session actually hits before changing anything.

## Verify first, in order
1. **Which policy is the traffic hitting right now?** Session table: `diagnose sys session filter src <ip>` / `dst <ip>` then `diagnose sys session list` :  the `policy_id=` field names the matched policy (0 = implicit deny). Also the **forward-traffic log** (Log & Report → Forward Traffic, or `execute log filter` + `execute log display`) shows the matched policy ID per session.
2. **Policy order.** Policies are evaluated top-down per interface pair; the first match wins. A broader policy above yours (any/any, a wider address group, a wider service) will match first. Check the policy list with the intended interface pair selected, or `show firewall policy` and read the sequence.
3. **Interface pair.** The incoming and outgoing interfaces in the policy must be the ones the packet actually uses. Confirm the egress interface with a route lookup: `get router info routing-table details <dst-ip>`. Zones, SD-WAN zones and VLAN sub-interfaces are different objects from their physical parents.
4. **Source / destination / service / schedule.** Address objects must contain the real source and destination (subnet vs host vs FQDN that has not resolved), the service must include the real protocol/port (watch custom services and port ranges), and the schedule must be active. NAT settings can change the source address seen by downstream policies.
5. **Debug flow for a definitive answer.** `diagnose debug flow filter addr <ip>`, `diagnose debug flow trace start 10`, `diagnose debug enable` :  the trace states `allowed by policy-<id>`, `denied by forward policy check`, `reverse path check fail`, or `no matching route`. Disable debug afterwards.
6. **Security profiles / implicit deny / VIPs.** An allowed session may be dropped later by a security profile (IPS, AV, web filter) :  the log will show the UTM event :  and VIP/destination-NAT objects need their own policy with the VIP as destination.

## Evidence to collect
- Session entry showing `policy_id` for the flow.
- Forward-traffic log line for the flow (matched policy ID, action).
- Route lookup result for the destination (egress interface).
- Debug flow trace for one test packet.
- The policy list for that interface pair, in sequence order.
