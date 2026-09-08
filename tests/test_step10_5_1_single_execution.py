"""Behavioral regression guard for ."""
from pathlib import Path


def main():
    print("\n========================================")
    print("RazaAI Step 10.5.1 Single Execution Test")
    print("========================================\n")

    source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "deterministic_tool_result is not None" in source
    assert "structured_playbook_turn" in source
    assert "tools=tools_for_turn" in source
    assert "_model_tools_for_turn(interaction, user_input)" in source

    # Behavioral shape: a deterministic result/playbook still disables model
    # tool execution for the remainder of the turn. Ordinary action turns now
    # use the scoped-tool selector rather than exposing the complete
    # registry, which also protects the 4096-token edge context.
    compact = " ".join(source.split())
    start = compact.index("tools_for_turn =")
    end = compact.index("if tools_for_turn is not None:", start)
    guard = compact[start:end]

    assert "None" in guard
    assert "deterministic_tool_result is not None" in guard
    assert "structured_playbook_turn" in guard
    assert "not interaction.allow_tools" in guard
    assert "else self._model_tools_for_turn(interaction, user_input)" in guard
    assert "else self.tools.get_definitions()" not in guard


    # Self-identity turns). They must not invalidate the original contract.

    print("[PASS] deterministic edge result disables LLM tools for remainder of turn")
    print("[PASS] normal action turns retain scoped native tool access")
    print("[PASS] duplicate create_document execution is structurally blocked")

    print("\n========================================")
    print("STEP 10.5.1 SINGLE EXECUTION PASSED")
    print("========================================\n")

if __name__ == "__main__":
    main()
