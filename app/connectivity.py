"""Connectivity probe."""

from __future__ import annotations

import os
import socket
import time

_PROBES = (("1.1.1.1", 53), ("8.8.8.8", 53), ("9.9.9.9", 53))
_CACHE = {"value": None, "checked": 0.0}
CACHE_SECONDS = 30.0


def is_online(timeout: float = 1.0, refresh: bool = False) -> bool:
    forced = os.getenv("RAZAAI_OFFLINE", "").strip().casefold()
    if forced in {"1", "true", "yes", "on"}:
        return False
    if os.getenv("RAZAAI_ONLINE", "").strip().casefold() in {"1", "true", "yes", "on"}:
        return True
    now = time.monotonic()
    if not refresh and _CACHE["value"] is not None and now - _CACHE["checked"] < CACHE_SECONDS:
        return _CACHE["value"]
    online = False
    for host, port in _PROBES:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                online = True
                break
        except OSError:
            continue
    _CACHE.update(value=online, checked=now)
    return online


def offline_reason() -> str:
    if os.getenv("RAZAAI_OFFLINE", "").strip().casefold() in {"1", "true", "yes", "on"}:
        return "offline mode is forced by RAZAAI_OFFLINE=1"
    return "no route to the public internet (1-second probe to public DNS resolvers failed)"
