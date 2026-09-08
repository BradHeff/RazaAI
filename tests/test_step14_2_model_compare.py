from app.evaluation.compare import compare_summaries


def summary(model, semantic, style, combined, results, hard=0):
    return {
        "model": model,
        "semantic_score_percent": semantic,
        "style_score_percent": style,
        "combined_score_percent": combined,
        "hard_gate_failures": hard,
        "promotion_eligible": hard == 0 and semantic >= 90 and combined >= 90,
        "categories": {
            "identity": {
                "semantic_score_percent": semantic,
                "style_score_percent": style,
            }
        },
        "results": results,
    }


def result(case_id, sem, style, hard=False):
    return {
        "case_id": case_id,
        "category": "identity",
        "hard_gate": hard,
        "semantic_passed": sem,
        "style_passed": style,
        "response": "response",
        "semantic_failures": [],
        "style_failures": [],
    }


def main():
    print("=" * 48)
    print("RazaAI Step 14.2 Model Comparison")
    print("=" * 48)

    baseline = summary(
        "base",
        80,
        20,
        68,
        [
            result("a", True, False, True),
            result("b", False, False),
        ],
        hard=1,
    )
    candidate = summary(
        "candidate",
        100,
        100,
        100,
        [
            result("a", True, True, True),
            result("b", True, True),
        ],
        hard=0,
    )

    report = compare_summaries(
        baseline,
        candidate,
    )

    assert report["semantic_delta"] == 20
    assert report["style_delta"] == 80
    assert len(report["semantic_regressions"]) == 0
    assert len(report["semantic_improvements"]) == 1
    assert report["promotion_eligible"]
    print("[PASS] semantic and style improvements are separated")

    regressed = summary(
        "candidate2",
        100,
        100,
        100,
        [
            result("a", False, True, True),
            result("b", True, True),
        ],
        hard=0,
    )
    # Force headline scores high to prove per-case semantic regression wins.
    regressed["semantic_score_percent"] = 100
    regressed["combined_score_percent"] = 100
    regressed["promotion_eligible"] = True

    report2 = compare_summaries(
        candidate,
        regressed,
    )
    assert len(report2["semantic_regressions"]) == 1
    assert not report2["promotion_eligible"]
    print("[PASS] aggregate score cannot hide semantic regression")

    print()
    print("=" * 48)
    print("STEP 14.2 MODEL COMPARISON PASSED")
    print("=" * 48)


if __name__ == "__main__":
    main()
