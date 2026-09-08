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

    from tests.run_offline import discover
    assert {'test_step20_8_1_project_checks_git', 'test_step20_8_0_full_coding_workflow', 'test_step20_8_3_exact_patch_preservation'} <= set(discover())
    print("[PASS] the offline runner includes these regression checks")

    print()
    print("=" * 78)
    print("STEP 20.8.0 VERSION + UX AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
