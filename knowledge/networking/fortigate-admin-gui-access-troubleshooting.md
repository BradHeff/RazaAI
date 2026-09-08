# FortiGate administrative GUI unavailable while SSH works

## Scope
Use this when the FortiGate itself is reachable (for example ping and/or SSH works) but the HTTP/HTTPS administrative GUI does not load, refuses the TCP connection, or returns a TCP reset.

This is **local administrative access to the FortiGate**, not ordinary forwarded firewall-policy traffic and not web-filter category troubleshooting.

## Verify first, in order

1. **Confirm administrative access is enabled on the interface receiving the connection, and confirm the browser is using the configured port.**
   - Inspect the relevant interface:
     `show system interface <interface>`
   - Look for `set allowaccess ... https ...` (and `http` only if HTTP administration is intentionally enabled).
   - Check the configured ports:
     `show full system global | grep admin-port`
     `show full system global | grep admin-sport`
   - Defaults are TCP/80 for HTTP and TCP/443 for HTTPS. If a custom port is configured, include it in the URL.

2. **Check the administrative GUI certificate before restarting processes.**
   - Inspect the configured certificate:
     `show full system global | grep admin-server-cert`
   - Fortinet documents `ERR_CONNECTION_REFUSED` cases where the configured GUI certificate is missing, invalid, incompatible, or broken after an upgrade.
   - If the evidence points to the configured certificate, a recovery action documented by Fortinet is:
     ```text
     config system global
         set admin-server-cert "Fortinet_Factory"
     end
     ```
   - Treat this as a configuration change: recommend it only when the certificate check supports it or the user explicitly asks for the corrective command. Preserve the user's exact working command when recording a resolution.

3. **If the certificate is valid, check whether FortiOS is actually listening and whether the GUI process exists.**
   - Socket/listener evidence:
     `diagnose sys tcpsock | grep httpsd`
     or inspect the configured port with `diagnose sys tcpsock`.
   - Process evidence:
     `diagnose sys process pidof httpsd`
   - Fortinet's troubleshooting cheat sheet documents `diagnose sys process pidof <daemon>` and `diagnose sys kill 11 <pid>`. Do not restart a process merely because the GUI is unavailable; first collect certificate/listener evidence.
   - On FortiOS releases where administrative login handling uses `http_authd`, use version-appropriate debug/process commands rather than guessing a daemon name.

4. **Capture one GUI connection attempt before widening the investigation.**
   - FortiGate uses the FortiOS sniffer command, not Linux `tcpdump`:
     `diagnose sniffer packet any 'host <client-ip> and port <admin-port>' 4 0 l`
   - SYN with no FortiGate response suggests path/local handling needs investigation.
   - SYN followed immediately by RST means the FortiGate is actively refusing/resetting the connection; correlate that with certificate, listener, crashlog/debug, local-in restrictions, port conflicts, and firmware version.

5. **Only after the checks above, investigate conflicts or firmware-specific faults.**
   - Check local-in policy, VIP/port conflicts, SSL-VPN/admin port overlap, and other local services only when evidence points there.
   - Fortinet has documented GUI refusal/TCP-RST conditions in specific firmware branches. Do not assume a firmware defect until interface access, port, certificate, and listener state have been checked.

## Evidence to collect
- `show system interface <interface>` output containing `allowaccess`.
- `show full system global | grep admin-port`.
- `show full system global | grep admin-sport`.
- `show full system global | grep admin-server-cert`.
- `diagnose sys tcpsock` lines for the configured GUI port.
- One `diagnose sniffer packet` capture while attempting GUI access.
- FortiOS version if the FortiGate sends an immediate TCP RST despite correct configuration.

## Source notes
Fortinet documentation/community references used to curate this procedure:
- FortiGate CLI reference: `diagnose sys tcpsock` lists TCP socket information.
- Fortinet Community: "Error ERR_CONNECTION_REFUSED is received while attempting to access FortiGate via a GUI or web browser" documents checking `admin-server-cert`, restoring `Fortinet_Factory` when the configured certificate is missing/invalid, checking crash logs, and verifying the HTTPS listener.
- Fortinet CLI troubleshooting cheat sheet documents `diagnose sys process pidof <daemon>` and `diagnose sys kill 11 <pid>`.
- Fortinet GUI troubleshooting guidance documents version-aware `httpsd` / `http_authd` debugging and certificate failures that prevent the admin GUI from loading.
- Fortinet troubleshooting guidance documents TCP-RST/GUI refusal cases where switching `admin-server-cert` to `Fortinet_Factory` restores access.
