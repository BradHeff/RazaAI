"""Legacy regression alignment for scoped tool schemas."""

from pathlib import Path


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.5 Legacy Regression Alignment")
    print("=" * 76)

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    legacy = Path("tests/test_step10_5_1_single_execution.py").read_text(
        encoding="utf-8"
    )

    assert "_model_tools_for_turn(interaction, user_input)" in agent
    assert "_model_tools_for_turn(interaction, user_input)" in legacy
    print("[PASS] Step10.5.1 follows the scoped-tool architecture")

    compact = " ".join(agent.split())
    start = compact.index("tools_for_turn =")
    end = compact.index("if tools_for_turn is not None:", start)
    guard = compact[start:end]

    assert "deterministic_tool_result is not None" in guard
    assert "structured_playbook_turn" in guard
    assert "not interaction.allow_tools" in guard
    assert "None" in guard
    assert "else self._model_tools_for_turn(interaction, user_input)" in guard
    print("[PASS] deterministic/safe turns still suppress model tool execution")

    # The legacy regression must explicitly require the scoped selector on the
    # ordinary-action branch, not the pre-full-registry implementation.
    legacy_compact = " ".join(legacy.split())
    assert 'assert "else self._model_tools_for_turn(interaction, user_input)" in guard' in legacy_compact
    print("[PASS] legacy test now guards behavior instead of the removed full-registry path")

    print()
    print("=" * 76)
    print("STEP 20.5.5 LEGACY REGRESSION ALIGNMENT PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
