"""Run RazaAI real-world capability evaluation."""

import argparse
import subprocess
import sys

from app.config import OLLAMA_MODEL, OLLAMA_HOST

from app.evaluation.capabilities import (
    CAPABILITY_CASES,
    run_capability_suite,
    summarize_capabilities,
    write_capability_report,
)


REGRESSION_MODULES = (
    "tests.test_step10_5_1_single_execution",
    "tests.test_step11_7_end_to_end",
    "tests.test_step12_6_live_hardening",
    "tests.test_step14_3_application_eval",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=OLLAMA_MODEL)
    parser.add_argument("--ollama-url", default=OLLAMA_HOST)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--output-dir", default="output/model-evals")
    parser.add_argument("--run-regressions", action="store_true")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help=(
            "Run the capability suite N times (seed + run index) and "
            "count a case as passed only if it passes in every run. One run "
            "cannot distinguish a fix from sampling luck at temperature 0.6."
        ),
    )
    args = parser.parse_args()
    args.runs = max(1, int(args.runs))

    print("=" * 72)
    print("RazaAI Capability Evaluation")
    print("=" * 72)
    print(f"Model: {args.model}")
    print(f"Cases: {len(CAPABILITY_CASES)}")
    print(f"Seed:  {args.seed}")
    print("=" * 72)

    results = run_capability_suite(
        model=args.model,
        base_url=args.ollama_url,
        seed=args.seed,
    )

    flaky = {}
    if args.runs > 1:
        print(f"Stability runs: {args.runs} (a case passes only if it passes every run)")
        by_id = {r.case_id: r for r in results}
        for run_index in range(1, args.runs):
            extra = run_capability_suite(
                model=args.model,
                base_url=args.ollama_url,
                seed=args.seed + run_index,
            )
            for result in extra:
                base = by_id.get(result.case_id)
                if base is None:
                    continue
                if base.passed and not result.passed:
                    # Demote: the first run was luck. Keep this run's failures.
                    flaky[result.case_id] = flaky.get(result.case_id, 0) + 1
                    by_id[result.case_id] = result
                elif not base.passed and result.passed:
                    flaky[result.case_id] = flaky.get(result.case_id, 0) + 1
        results = [by_id[r.case_id] for r in results]

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
            f"{result.interaction_domain or 'general'} "
            f"sensitive={result.interaction_sensitive} "
            f"tools_allowed={result.interaction_tools_allowed}"
        )
        print(
            "       tools="
            + (
                ", ".join(result.tool_calls)
                if result.tool_calls
                else "none"
            )
        )

        for failure in result.failures:
            print(f"       - {failure}")
        if result.case_id in flaky:
            print(
                f"       - UNSTABLE: outcome differed across {args.runs} runs "
                f"({flaky[result.case_id]} flip(s)); treated as FAIL"
            )

    summary = summarize_capabilities(
        args.model,
        results,
    )

    regression_failures = []

    if args.run_regressions:
        print()
        print("=" * 72)
        print("RazaAI Regression Suites")
        print("=" * 72)

        for module in REGRESSION_MODULES:
            print(f"\nRunning {module} ...")
            proc = subprocess.run(
                [sys.executable, "-m", module],
                text=True,
            )
            if proc.returncode != 0:
                regression_failures.append(module)

        summary["regression_modules"] = list(
            REGRESSION_MODULES
        )
        summary["regression_failures"] = regression_failures

        if regression_failures:
            summary["capability_ready"] = False

    json_path, md_path = write_capability_report(
        summary,
        args.output_dir,
    )

    print()
    print("=" * 72)
    print("CAPABILITY EVALUATION COMPLETE")
    print("=" * 72)
    print(
        f"Capability score:     "
        f"{summary['score_percent']}%"
    )
    print(
        f"Hard-gate failures:   "
        f"{summary['hard_gate_failures']}"
    )
    if args.run_regressions:
        print(
            f"Regression failures:  "
            f"{len(regression_failures)}"
        )
    print(
        f"Capability ready:     "
        f"{'YES' if summary['capability_ready'] else 'NO'}"
    )
    print(f"JSON report:          {json_path}")
    print(f"Markdown report:      {md_path}")
    print("=" * 72)

    raise SystemExit(
        0 if summary["capability_ready"] else 2
    )


if __name__ == "__main__":
    main()
