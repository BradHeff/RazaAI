"""RazaAI version and UX authority."""

from pathlib import Path

from app.config import APP_VERSION, version_tuple


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.0 Version + UX Authority")
    print("=" * 78)

    assert version_tuple(APP_VERSION) >= (20, 8, 0), APP_VERSION
    print(f"[PASS] APP_VERSION {APP_VERSION} is at or beyond the 20.8.0 milestone")

    coworker = Path("app/coding/coworker.py").read_text(encoding="utf-8")
    for capability in (
        "_project_profile",
        "_rank_context_files",
        "_write_plan",
        "_run_verification",
        "_repair",
        "_git_evidence",
        "run_project_checks",
    ):
        assert capability in coworker
    print("[PASS] full coding-agent workflow is structurally present")

    help_source = Path("app/tui/session.py").read_text(encoding="utf-8")
    assert "multi-file changes" in help_source
    assert "tests/builds" in help_source
    assert "Git status/diff evidence" in help_source
    print("[PASS] /help documents mature coding coworker capability")

    acceptance = Path("scripts/step20_acceptance.py").read_text(encoding="utf-8")
    assert "REQUIRED_VERSION" in acceptance and "APP_VERSION" in acceptance
    assert "tests.test_step20_8_0_full_coding_workflow" in acceptance
    assert "tests.test_step20_8_1_project_checks_git" in acceptance
    assert "tests.test_step20_8_3_exact_patch_preservation" in acceptance
    print("[PASS] Step 20 acceptance gates the 20.8.0 milestone")

    print()
    print("=" * 78)
    print("STEP 20.8.0 VERSION + UX AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
