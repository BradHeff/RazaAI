"""RazaAI structural capability tests."""

from app.evaluation.capabilities import (
    CAPABILITY_CASES,
    CapabilityResult,
    summarize_capabilities,
)


def result(case_id, category, passed=True, hard=False):
    return CapabilityResult(
        case_id=case_id,
        category=category,
        passed=passed,
        hard_gate=hard,
        response="test",
        failures=() if passed else ("failure",),
        tool_calls=(),
    )


def main():
    print("=" * 52)
    print("RazaAI Step 15.0 Capability Evaluation")
    print("=" * 52)

    assert len(CAPABILITY_CASES) == 14
    print(
        "[PASS] suite defines 14 real-world capability cases"
    )

    names = {
        case.__name__
        for case in CAPABILITY_CASES
    }

    required = {
        "case_network_apipa",
        "case_windows_gpo",
        "case_linux_disk",
        "case_fortigate_policy",
        "case_programming_code_review",
        "case_document_creation",
        "case_routing_ambiguous",
        "case_selfops_health",
    }

    assert required.issubset(names)
    print(
        "[PASS] networking/Windows/Linux/FortiGate/code/docs/"
        "routing/selfops are covered"
    )

    good = [
        result("a", "networking"),
        result("b", "windows"),
        result("c", "programming", hard=True),
        result("d", "documents", hard=True),
        result("e", "routing", hard=True),
        result("f", "selfops", hard=True),
        result("g", "linux"),
        result("h", "fortigate"),
        result("i", "networking"),
        result("j", "windows"),
    ]

    summary = summarize_capabilities(
        "candidate",
        good,
    )
    assert summary["capability_ready"]
    print(
        "[PASS] clean capability result can become ready"
    )

    bad = list(good)
    bad[2] = result(
        "c",
        "programming",
        passed=False,
        hard=True,
    )

    summary = summarize_capabilities(
        "candidate",
        bad,
    )
    assert not summary["capability_ready"]
    assert summary["hard_gate_failures"] == 1
    print(
        "[PASS] one hard tool/evidence failure blocks readiness"
    )

    print()
    print("=" * 52)
    print("STEP 15.0 CAPABILITY EVALUATION PASSED")
    print("=" * 52)


if __name__ == "__main__":
    main()
