"""RazaAI complete controlled-web acceptance."""

import subprocess
import sys


MODULES = (
    "tests.test_step15_0_1_capability_hardening",
    "tests.test_step15_1_tool_authority",
    "tests.test_step16_0_web_safety",
    "tests.test_step16_1_web_routing",
    "tests.test_step16_2_web_provenance",
    "tests.test_step16_3_end_to_end",
    "tests.test_step16_4_agent_integration",
    "tests.test_step16_6_web_grounding",
)


def main():
    print("=" * 72)
    print("RazaAI Step 16.5 External Knowledge Acceptance")
    print("=" * 72)

    failures = []

    for module in MODULES:
        print(f"\nRunning {module} ...")
        proc = subprocess.run(
            [sys.executable, "-m", module],
            text=True,
        )
        if proc.returncode != 0:
            failures.append(module)

    print()
    print("=" * 72)

    if failures:
        print("STEP 16 ACCEPTANCE FAILED")
        for module in failures:
            print("[FAIL]", module)
        print("=" * 72)
        raise SystemExit(1)

    print("STEP 16.5 END-TO-END ACCEPTANCE PASSED")
    print("STEP 16 COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
