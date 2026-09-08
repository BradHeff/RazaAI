# Nginx 502 Bad Gateway :  evidence-first troubleshooting

## What a 502 means
Nginx accepted the client request but the **upstream** (the backend application it proxies to :  gunicorn, uWSGI, php-fpm, Node, a container, another host) did not return a valid response. A 502 is almost never an nginx configuration syntax problem; it is nginx telling you the backend is unreachable, refused, crashed, or answered something nginx could not parse.

## Verify first, in this order
1. **Is the upstream process actually running and listening?**
   - `systemctl status <app-service>` and `journalctl -u <app-service> -n 100` :  look for crash loops, OOM kills, failed migrations.
   - `ss -ltnp` (TCP) or `ss -lxp` (unix sockets) :  confirm something is **listening** on the port or socket path nginx proxies to.
2. **Does the nginx error log name the cause?**
   - `tail -n 50 /var/log/nginx/error.log` :  the 502 line states it: `connect() failed (111: Connection refused)` = nothing listening; `(13: Permission denied)` on a socket = nginx user cannot access the socket file; `upstream prematurely closed connection` = backend crashed mid-request; `upstream timed out` = backend alive but slow (that usually surfaces as 504).
3. **Can nginx reach the upstream address itself?**
   - Read the `proxy_pass` / `fastcgi_pass` target in the site config and test it from the nginx host: `curl -v http://127.0.0.1:<port>/` or `curl --unix-socket /run/app.sock http://localhost/`.
   - Mismatched port, wrong socket path, or a container whose port mapping changed are the common causes after deployments.
4. **Socket permissions and SELinux/AppArmor.** For unix sockets, the socket file owner/group and mode must allow the nginx worker user (`www-data` / `nginx`). On SELinux hosts, `ausearch -m avc -ts recent` and `setsebool httpd_can_network_connect 1` if nginx proxies over TCP.
5. **Resource exhaustion.** `free -m`, `dmesg | grep -i oom`, open-file limits on the backend, and php-fpm `pm.max_children` reached (`server reached pm.max_children` in the php-fpm log).
6. **Only then** look at nginx itself: `nginx -t` for config validity, buffer sizes (`proxy_buffer_size`) if headers are large, and `proxy_read_timeout` if the backend is legitimately slow.

## Evidence to collect before changing anything
- Exact timestamped 502 line from `/var/log/nginx/error.log`.
- `ss -ltnp` / `ss -lxp` output showing whether the upstream port/socket is in a LISTEN state.
- `systemctl status` and last 100 journal lines of the upstream service.
- `curl -v` directly against the upstream, bypassing nginx.

## Related
- 504 Gateway Timeout: upstream reachable but too slow :  check backend performance before raising nginx timeouts.
- 503: nginx deliberately refusing (rate limit, maintenance, all upstreams marked down).
