"""RazaAI static acceptance."""

import subprocess
import sys


MODULES = (
    "tests.test_step14_2_semantic_style",
    "tests.test_step14_2_model_compare",
    "tests.test_step14_3_application_eval",
    "tests.test_step15_0_capability_eval",
)


def main():
    print("=" * 72)
    print("RazaAI Step 15.0 Acceptance")
    print("=" * 72)

    failures = []

    for module in MODULES:
        proc = subprocess.run(
            [sys.executable, "-m", module],
            text=True,
        )
        if proc.returncode != 0:
            failures.append(module)

    print()
    print("=" * 72)

    if failures:
        print("STEP 15.0 ACCEPTANCE FAILED")
        for module in failures:
            print(f"[FAIL] {module}")
        print("=" * 72)
        raise SystemExit(1)

    print("STEP 15.0 ACCEPTANCE PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
