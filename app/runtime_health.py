"""Startup memory visibility for edge devices."""

from __future__ import annotations

import os
from pathlib import Path

LOW_AVAILABLE_MB = 1024
SWAP_WARN_MB = 256


def _meminfo() -> dict:
    values = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            digits = "".join(ch for ch in rest if ch.isdigit())
            if digits:
                values[key.strip()] = int(digits) // 1024  # KB -> MB
    except (OSError, UnicodeError, ValueError):
        pass
    return values


def _largest_process_rss_mb(names=("llama-server", "ollama")) -> tuple[str | None, int]:
    best_name, best_rss = None, 0
    proc = Path("/proc")
    try:
        entries = [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError:
        return None, 0
    for entry in entries:
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
            if comm not in names:
                continue
            for line in (entry / "status").read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    rss = int("".join(ch for ch in line if ch.isdigit()) or 0) // 1024
                    if rss > best_rss:
                        best_name, best_rss = comm, rss
                    break
        except (OSError, UnicodeError, ValueError):
            continue
    return best_name, best_rss


def memory_snapshot() -> dict:
    info = _meminfo()
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    swap_total = info.get("SwapTotal", 0)
    swap_used = max(0, swap_total - info.get("SwapFree", 0))
    model_proc, model_rss = _largest_process_rss_mb()
    warnings = []
    if total and available < LOW_AVAILABLE_MB:
        warnings.append(
            f"only {available} MB available; the model may be competing with other processes"
        )
    # Swap alone is not a symptom on a workstation with plenty of RAM
    # (Linux parks idle pages there). It is a symptom when memory is also tight.
    if swap_used > SWAP_WARN_MB and total and available < max(LOW_AVAILABLE_MB, total // 4):
        warnings.append(
            f"{swap_used} MB in swap with only {available} MB available; on an edge device this "
            "usually means the model spilled out of RAM and every turn will stall"
        )
    return {
        "total_mb": total,
        "available_mb": available,
        "swap_used_mb": swap_used,
        "swap_total_mb": swap_total,
        "model_process": model_proc,
        "model_rss_mb": model_rss,
        "warnings": warnings,
        "supported": bool(total),
    }


def format_memory_line(snapshot: dict | None = None) -> str:
    snap = snapshot or memory_snapshot()
    if not snap.get("supported"):
        return "Memory: unavailable on this platform"
    parts = [
        f"Memory: {snap['available_mb']} MB available of {snap['total_mb']} MB",
        f"swap {snap['swap_used_mb']} MB",
    ]
    if snap.get("model_process"):
        parts.append(f"{snap['model_process']} {snap['model_rss_mb']} MB")
    line = " · ".join(parts)
    if snap["warnings"]:
        line += "\n  WARNING: " + "; ".join(snap["warnings"])
    return line
