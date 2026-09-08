"""Run RazaAI direct-model evaluation."""

import argparse

from app.evaluation.cases import build_default_suite
from app.evaluation.runner import (
    ModelEvaluator,
    OllamaChatClient,
    summarize_results,
    write_report,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="raza-edge:4b-v3")
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
    print("RazaAI Step 14.2 Deterministic Semantic + Style Evaluation")
    print("=" * 68)
    print(f"Model: {args.model}")
    print(f"Cases: {len(suite.cases)}")
    print(f"Seed:  {args.seed}")
    print("=" * 68)

    results = []
    for index, case in enumerate(suite.cases, 1):
        result = evaluator.run_case(args.model, case)
        results.append(result)

        sem = "PASS" if result.semantic_passed else "FAIL"
        sty = "PASS" if result.style_passed else "FAIL"
        gate = " [HARD]" if result.hard_gate else ""

        print(
            f"[SEM:{sem} STYLE:{sty}] "
            f"{index:02d}/{len(suite.cases):02d} "
            f"{case.case_id}{gate}"
        )

        for failure in result.semantic_failures:
            print(f"       SEM  - {failure}")
        for failure in result.style_failures:
            print(f"       STYLE- {failure}")

    summary = summarize_results(
        args.model,
        suite,
        results,
    )
    json_path, md_path = write_report(
        summary,
        args.output_dir,
    )

    print()
    print("=" * 68)
    print("STEP 14.2 MODEL EVALUATION COMPLETE")
    print("=" * 68)
    print(
        f"Semantic score:      "
        f"{summary['semantic_score_percent']}%"
    )
    print(
        f"Style score:         "
        f"{summary['style_score_percent']}%"
    )
    print(
        f"Combined score:      "
        f"{summary['combined_score_percent']}%"
    )
    print(
        f"Hard-gate failures:  "
        f"{summary['hard_gate_failures']}"
    )
    print(
        f"Promotion eligible:  "
        f"{'YES' if summary['promotion_eligible'] else 'NO'}"
    )
    print(f"JSON report:          {json_path}")
    print(f"Markdown report:      {md_path}")
    print("=" * 68)

    raise SystemExit(
        0 if summary["promotion_eligible"] else 2
    )


if __name__ == "__main__":
    main()
