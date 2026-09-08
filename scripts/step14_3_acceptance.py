"""RazaAI static acceptance."""

import subprocess
import sys


MODULES = (
    "tests.test_step14_2_semantic_style",
    "tests.test_step14_2_model_compare",
    "tests.test_step14_3_application_eval",
)


def main():
    print("=" * 68)
    print("RazaAI Step 14.3 Acceptance")
    print("=" * 68)

    failed = []

    for module in MODULES:
        proc = subprocess.run(
            [sys.executable, "-m", module],
            text=True,
        )
        if proc.returncode != 0:
            failed.append(module)

    print()
    print("=" * 68)

    if failed:
        print("STEP 14.3 ACCEPTANCE FAILED")
        for module in failed:
            print(f"[FAIL] {module}")
        print("=" * 68)
        raise SystemExit(1)

    print("STEP 14.3 ACCEPTANCE PASSED")
    print("=" * 68)


if __name__ == "__main__":
    main()
