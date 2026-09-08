"""RazaAI Persistent Memory & Learning Acceptance."""

import subprocess
import sys


MODULES = (
    "scripts.step16_acceptance",
    "tests.test_step17_0_persistent_memory",
    "tests.test_step17_1_learning",
    "tests.test_step17_2_memory_routing",
    "tests.test_step17_3_memory_authority",
    "tests.test_step17_4_agent_memory",
    "tests.test_step17_5_operational_memory",
    "tests.test_step17_8_document_guides",
    "tests.test_step17_9_instruction_guide_content",
    "tests.test_step17_10_staff_rollout_documents",
)


def main():
    print("=" * 76)
    print("RazaAI Step 17.6 Persistent Memory & Learning Acceptance")
    print("=" * 76)

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
    print("=" * 76)

    if failures:
        print("STEP 17 ACCEPTANCE FAILED")
        for module in failures:
            print(f"[FAIL] {module}")
        print("=" * 76)
        raise SystemExit(1)

    print("STEP 17.6 END-TO-END ACCEPTANCE PASSED")
    print("STEP 17 COMPLETE")
    print("=" * 76)


if __name__ == "__main__":
    main()
