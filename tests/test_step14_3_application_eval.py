"""Application-evaluation structural tests."""

from app.evaluation.application import (
    APPLICATION_CASES,
    AppEvalResult,
    summarize_application,
)


def make(case_id, passed=True, hard=True, category="security"):
    return AppEvalResult(
        case_id=case_id,
        category=category,
        passed=passed,
        hard_gate=hard,
        response="test",
        failures=() if passed else ("failure",),
        tool_calls=(),
    )


def main():
    print("=" * 48)
    print("RazaAI Step 14.3 Application Evaluation")
    print("=" * 48)

    assert len(APPLICATION_CASES) >= 10
    print(
        f"[PASS] application suite defines {len(APPLICATION_CASES)} "
        "full-stack cases"
    )

    names = {case.__name__ for case in APPLICATION_CASES}
    required = {
        "case_sensitive_python_boundary",
        "case_sensitive_persistence",
        "case_sensitive_identity_reset",
        "case_sensitive_neutral_ack_reset",
        "case_real_self_audit_single_execution",
        "case_fake_audit_needs_evidence",
        "case_self_repair_authority",
        "case_code_investigation_truthfulness",
    }
    assert required.issubset(names)
    print("[PASS] Python security/self-ops authority cases are present")

    good = [
        make("a", True, True, "security"),
        make("b", True, True, "selfops"),
        make("c", True, False, "conversation"),
    ]
    summary = summarize_application("candidate", good)
    assert summary["production_ready"]
    assert summary["hard_gate_failures"] == 0
    print("[PASS] clean full-stack result can become production-ready")

    hard_bad = [
        make("a", False, True, "security"),
        make("b", True, True, "selfops"),
        make("c", True, False, "conversation"),
    ]
    summary = summarize_application("candidate", hard_bad)
    assert not summary["production_ready"]
    assert summary["hard_gate_failures"] == 1
    print("[PASS] one hard Python-boundary failure blocks production")

    print()
    print("=" * 48)
    print("STEP 14.3 APPLICATION EVALUATION PASSED")
    print("=" * 48)


if __name__ == "__main__":
    main()
