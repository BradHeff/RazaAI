"""Baseline-vs-candidate semantic/style comparison."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re


def compare_summaries(baseline: dict, candidate: dict) -> dict:
    bmap = {
        result["case_id"]: result
        for result in baseline["results"]
    }
    cmap = {
        result["case_id"]: result
        for result in candidate["results"]
    }

    if set(bmap) != set(cmap):
        raise ValueError("Baseline and candidate evaluation suites differ")

    semantic_regressions = []
    semantic_improvements = []
    style_regressions = []
    style_improvements = []

    for case_id in sorted(bmap):
        b = bmap[case_id]
        c = cmap[case_id]

        common = {
            "case_id": case_id,
            "category": c["category"],
            "hard_gate": bool(c["hard_gate"]),
            "baseline_response": b["response"],
            "candidate_response": c["response"],
        }

        if b["semantic_passed"] and not c["semantic_passed"]:
            semantic_regressions.append({
                **common,
                "candidate_failures": c["semantic_failures"],
            })
        elif not b["semantic_passed"] and c["semantic_passed"]:
            semantic_improvements.append(common)

        if b["style_passed"] and not c["style_passed"]:
            style_regressions.append({
                **common,
                "candidate_failures": c["style_failures"],
            })
        elif not b["style_passed"] and c["style_passed"]:
            style_improvements.append(common)

    hard_semantic_regressions = [
        item
        for item in semantic_regressions
        if item["hard_gate"]
    ]

    category_deltas = {}
    categories = sorted(
        set(baseline["categories"])
        | set(candidate["categories"])
    )

    for category in categories:
        b = baseline["categories"][category]
        c = candidate["categories"][category]
        category_deltas[category] = {
            "baseline_semantic": b["semantic_score_percent"],
            "candidate_semantic": c["semantic_score_percent"],
            "semantic_delta": round(
                c["semantic_score_percent"]
                - b["semantic_score_percent"],
                1,
            ),
            "baseline_style": b["style_score_percent"],
            "candidate_style": c["style_score_percent"],
            "style_delta": round(
                c["style_score_percent"]
                - b["style_score_percent"],
                1,
            ),
        }

    # Candidate may be more concise or stylistic without sacrificing any
    # previously correct semantic behavior.
    eligible = (
        bool(candidate["promotion_eligible"])
        and not semantic_regressions
        and candidate["semantic_score_percent"]
            >= baseline["semantic_score_percent"]
        and candidate["combined_score_percent"]
            >= baseline["combined_score_percent"]
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_model": baseline["model"],
        "candidate_model": candidate["model"],

        "baseline_semantic_score": baseline["semantic_score_percent"],
        "candidate_semantic_score": candidate["semantic_score_percent"],
        "semantic_delta": round(
            candidate["semantic_score_percent"]
            - baseline["semantic_score_percent"],
            1,
        ),

        "baseline_style_score": baseline["style_score_percent"],
        "candidate_style_score": candidate["style_score_percent"],
        "style_delta": round(
            candidate["style_score_percent"]
            - baseline["style_score_percent"],
            1,
        ),

        "baseline_combined_score": baseline["combined_score_percent"],
        "candidate_combined_score": candidate["combined_score_percent"],
        "combined_delta": round(
            candidate["combined_score_percent"]
            - baseline["combined_score_percent"],
            1,
        ),

        "semantic_regressions": semantic_regressions,
        "semantic_improvements": semantic_improvements,
        "style_regressions": style_regressions,
        "style_improvements": style_improvements,

        "hard_semantic_regressions": len(hard_semantic_regressions),
        "candidate_hard_gate_failures": candidate["hard_gate_failures"],
        "category_deltas": category_deltas,
        "promotion_eligible": eligible,
    }


def write_comparison(
    report: dict,
    output_dir: str | Path = "output/model-evals",
):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    def slug(value):
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = out / (
        f"compare-{slug(report['baseline_model'])}"
        f"-vs-{slug(report['candidate_model'])}-{stamp}"
    )

    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# RazaAI Model Comparison",
        "",
        f"- Baseline: `{report['baseline_model']}`",
        f"- Candidate: `{report['candidate_model']}`",
        "",
        f"- Semantic: {report['baseline_semantic_score']}% → "
        f"{report['candidate_semantic_score']}% "
        f"({report['semantic_delta']:+.1f})",
        f"- Style: {report['baseline_style_score']}% → "
        f"{report['candidate_style_score']}% "
        f"({report['style_delta']:+.1f})",
        f"- Combined: {report['baseline_combined_score']}% → "
        f"{report['candidate_combined_score']}% "
        f"({report['combined_delta']:+.1f})",
        "",
        f"- Semantic regressions: **{len(report['semantic_regressions'])}**",
        f"- Semantic improvements: **{len(report['semantic_improvements'])}**",
        f"- Style regressions: **{len(report['style_regressions'])}**",
        f"- Style improvements: **{len(report['style_improvements'])}**",
        f"- Hard semantic regressions: **{report['hard_semantic_regressions']}**",
        f"- Candidate hard failures: **{report['candidate_hard_gate_failures']}**",
        f"- Promotion eligible: **{'YES' if report['promotion_eligible'] else 'NO'}**",
        "",
        "## Category deltas",
        "",
    ]

    for category, delta in report["category_deltas"].items():
        lines.append(
            f"- {category}: semantic "
            f"{delta['baseline_semantic']}% → "
            f"{delta['candidate_semantic']}% "
            f"({delta['semantic_delta']:+.1f}); style "
            f"{delta['baseline_style']}% → "
            f"{delta['candidate_style']}% "
            f"({delta['style_delta']:+.1f})"
        )

    lines.extend(["", "## Semantic regressions", ""])
    if not report["semantic_regressions"]:
        lines.append("No semantic regressions.")
    else:
        for item in report["semantic_regressions"]:
            lines.extend([
                f"### {item['case_id']}"
                f"{' [HARD]' if item['hard_gate'] else ''}",
                "",
                f"Baseline: `{item['baseline_response']}`",
                "",
                f"Candidate: `{item['candidate_response']}`",
                "",
            ])

    lines.extend(["", "## Semantic improvements", ""])
    if not report["semantic_improvements"]:
        lines.append("No semantic improvements.")
    else:
        for item in report["semantic_improvements"]:
            lines.extend([
                f"### {item['case_id']}",
                "",
                f"Baseline: `{item['baseline_response']}`",
                "",
                f"Candidate: `{item['candidate_response']}`",
                "",
            ])

    md_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return json_path, md_path
