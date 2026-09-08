"""RazaAI deterministic baseline-vs-candidate comparison."""

import argparse

from app.evaluation.cases import build_default_suite
from app.evaluation.compare import (
    compare_summaries,
    write_comparison,
)
from app.evaluation.runner import (
    ModelEvaluator,
    OllamaChatClient,
    summarize_results,
)


def evaluate(model, evaluator, suite):
    print(f"\nEvaluating {model}...")
    results = []

    for index, case in enumerate(suite.cases, 1):
        result = evaluator.run_case(model, case)
        results.append(result)

        sem = "PASS" if result.semantic_passed else "FAIL"
        style = "PASS" if result.style_passed else "FAIL"

        print(
            f"[SEM:{sem} STYLE:{style}] "
            f"{index:02d}/{len(suite.cases):02d} "
            f"{case.case_id}"
        )

    return summarize_results(
        model,
        suite,
        results,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output-dir", default="output/model-evals")
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()

    suite = build_default_suite()
    evaluator = ModelEvaluator(
        OllamaChatClient(
            base_url=args.ollama_url,
            seed=args.seed,
        )
    )

    print("=" * 68)
    print("RazaAI Step 14.2 Deterministic Model Comparison")
    print("=" * 68)
    print(f"Seed: {args.seed}")

    baseline = evaluate(
        args.baseline,
        evaluator,
        suite,
    )
    candidate = evaluate(
        args.candidate,
        evaluator,
        suite,
    )

    report = compare_summaries(
        baseline,
        candidate,
    )
    json_path, md_path = write_comparison(
        report,
        args.output_dir,
    )

    print()
    print("=" * 68)
    print("STEP 14.2 MODEL COMPARISON COMPLETE")
    print("=" * 68)
    print(
        f"Baseline semantic:   "
        f"{report['baseline_semantic_score']}%"
    )
    print(
        f"Candidate semantic:  "
        f"{report['candidate_semantic_score']}%"
    )
    print(
        f"Semantic delta:      "
        f"{report['semantic_delta']:+.1f}"
    )
    print(
        f"Baseline style:      "
        f"{report['baseline_style_score']}%"
    )
    print(
        f"Candidate style:     "
        f"{report['candidate_style_score']}%"
    )
    print(
        f"Style delta:         "
        f"{report['style_delta']:+.1f}"
    )
    print(
        f"Baseline combined:   "
        f"{report['baseline_combined_score']}%"
    )
    print(
        f"Candidate combined:  "
        f"{report['candidate_combined_score']}%"
    )
    print(
        f"Combined delta:      "
        f"{report['combined_delta']:+.1f}"
    )
    print(
        f"Semantic regressions:"
        f" {len(report['semantic_regressions'])}"
    )
    print(
        f"Semantic improvements:"
        f" {len(report['semantic_improvements'])}"
    )
    print(
        f"Candidate hard fails:"
        f" {report['candidate_hard_gate_failures']}"
    )
    print(
        f"Promotion eligible:  "
        f"{'YES' if report['promotion_eligible'] else 'NO'}"
    )
    print(f"JSON report:          {json_path}")
    print(f"Markdown report:      {md_path}")
    print("=" * 68)

    raise SystemExit(
        0 if report["promotion_eligible"] else 2
    )


if __name__ == "__main__":
    main()
