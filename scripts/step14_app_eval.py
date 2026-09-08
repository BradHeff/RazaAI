"""Run RazaAI application-level evaluation."""

import argparse
import subprocess
import sys

from app.evaluation.application import (
    APPLICATION_CASES,
    run_application_suite,
    summarize_application,
    write_application_report,
)


REGRESSION_MODULES = (
    "tests.test_step10_5_1_single_execution",
    "tests.test_step11_7_end_to_end",
    "tests.test_step12_6_live_hardening",
)


def run_regressions():
    failures = []

    print()
    print("=" * 68)
    print("RazaAI Step 14.3 Existing Regression Suites")
    print("=" * 68)

    for module in REGRESSION_MODULES:
        print(f"\nRunning {module} ...")
        proc = subprocess.run(
            [sys.executable, "-m", module],
            text=True,
        )
        if proc.returncode != 0:
            failures.append(module)

    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="raza-edge:4b-v3")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--output-dir", default="output/model-evals")
    parser.add_argument(
        "--run-regressions",
        action="store_true",
        help="Also run existing Step 10.5.1, 11.7, and 12.6 suites.",
    )
    args = parser.parse_args()

    print("=" * 68)
    print("RazaAI Step 14.3 Application-Level Evaluation")
    print("=" * 68)
    print(f"Candidate model: {args.model}")
    print(f"Cases:           {len(APPLICATION_CASES)}")
    print(f"Seed:            {args.seed}")
    print("=" * 68)

    results = run_application_suite(
        model=args.model,
        base_url=args.ollama_url,
        seed=args.seed,
    )

    for index, result in enumerate(results, 1):
        status = "PASS" if result.passed else "FAIL"
        gate = " [HARD]" if result.hard_gate else ""

        print(
            f"[{status}] {index:02d}/{len(results):02d} "
            f"{result.case_id}{gate}"
        )
        print(
            f"       interaction="
            f"{result.interaction_mode}/"
            f"{result.interaction_domain} "
            f"sensitive={result.interaction_sensitive} "
            f"tools_allowed={result.interaction_tools_allowed}"
        )
        print(
            f"       tools="
            f"{', '.join(result.tool_calls) if result.tool_calls else 'none'}"
        )

        for failure in result.failures:
            print(f"       - {failure}")

    summary = summarize_application(
        args.model,
        results,
    )

    regression_failures = []
    if args.run_regressions:
        regression_failures = run_regressions()
        summary["regression_modules"] = list(REGRESSION_MODULES)
        summary["regression_failures"] = regression_failures
        if regression_failures:
            summary["production_ready"] = False

    json_path, md_path = write_application_report(
        summary,
        args.output_dir,
    )

    print()
    print("=" * 68)
    print("STEP 14.3 APPLICATION EVALUATION COMPLETE")
    print("=" * 68)
    print(f"Application score:    {summary['score_percent']}%")
    print(f"Hard-gate failures:   {summary['hard_gate_failures']}")
    if args.run_regressions:
        print(f"Regression failures:  {len(regression_failures)}")
    print(
        f"Production ready:     "
        f"{'YES' if summary['production_ready'] else 'NO'}"
    )
    print(f"JSON report:          {json_path}")
    print(f"Markdown report:      {md_path}")
    print("=" * 68)

    raise SystemExit(
        0 if summary["production_ready"] else 2
    )


if __name__ == "__main__":
    main()
