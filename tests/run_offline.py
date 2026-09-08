"""Run regression tests with isolated synthetic knowledge."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Requires a reachable Ollama with the RazaAI model, or real network/system access.
LIVE_TESTS = {
    "test_agent": "talks to Ollama",
    "test_connection": "talks to Ollama",
    "test_ip_agent": "talks to Ollama",
    "test_network_agent": "talks to Ollama",
    "test_step8_diagnostics": "talks to Ollama",
    "test_tool_request": "talks to Ollama",
    "test_step3_network": "needs the Linux `ip` binary and real interfaces",
}

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent


def discover():
    return sorted(p.stem for p in TESTS_DIR.glob("test_*.py"))


def run_module(name, timeout=300):
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", f"tests.{name}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, time.monotonic() - started, proc.stdout, proc.stderr


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="also run LIVE_TESTS")
    parser.add_argument("--list", action="store_true", help="print classification and exit")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    modules = discover()
    offline = [m for m in modules if m not in LIVE_TESTS]
    live = [m for m in modules if m in LIVE_TESTS]

    if args.list:
        for m in offline:
            print(f"offline  {m}")
        for m in live:
            print(f"live     {m}  ({LIVE_TESTS[m]})")
        return 0

    from .knowledge_fixture import indexed
    print("[setup] building the synthetic knowledge index")
    fixture = indexed()

    selected = offline + (live if args.live else [])
    print("=" * 78)
    print(f"RazaAI offline test suite: {len(offline)} offline"
          + (f" + {len(live)} live" if args.live else f" ({len(live)} live skipped)"))
    print("=" * 78)

    failures = []
    for name in selected:
        try:
            code, seconds, out, err = run_module(name, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            code, seconds, out, err = 124, args.timeout, "", "timeout"
        status = "PASS" if code == 0 else "FAIL"
        print(f"[{status}] {name} ({seconds:.1f}s)")
        if code != 0:
            tail = "\n".join((err or out).strip().splitlines()[-8:])
            failures.append((name, tail))

    fixture.cleanup()
    print("=" * 78)
    if failures:
        for name, tail in failures:
            print(f"\n--- {name} ---\n{tail}")
        print(f"\nOFFLINE SUITE FAILED: {len(failures)}/{len(selected)}")
        return 1
    print(f"OFFLINE SUITE PASSED: {len(selected)}/{len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
