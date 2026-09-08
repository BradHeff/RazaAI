"""Targeted acceptance."""

import subprocess
import sys

MODULES = (
    "tests.test_step15_0_1_capability_hardening",
    "tests.test_step15_1_tool_authority",
)


def main():
    failures = []
    print("=" * 64)
    print("RazaAI Step 15.1 Acceptance")
    print("=" * 64)

    for module in MODULES:
        proc = subprocess.run([sys.executable, "-m", module], text=True)
        if proc.returncode != 0:
            failures.append(module)

    if failures:
        print("STEP 15.1 ACCEPTANCE FAILED")
        for module in failures:
            print("[FAIL]", module)
        raise SystemExit(1)

    print("=" * 64)
    print("STEP 15.1 ACCEPTANCE PASSED")
    print("=" * 64)


if __name__ == "__main__":
    main()
