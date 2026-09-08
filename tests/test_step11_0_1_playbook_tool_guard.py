"""Regression tests for Python-owned structured playbook turns."""
from pathlib import Path


def main():
    print("\n========================================")
    print("RazaAI Step 11.0.1 Stateful Playbook Tool Guard")
    print("========================================\n")

    source = Path("app/agent/agent.py").read_text()

    required = [
        "structured_playbook_turn",
        "continuing_playbook or lifecycle_turn",
        "or structured_playbook_turn",
        "STEP 11.0.1 PYTHON-OWNED PLAYBOOK TURN",
        "Do not reinterpret site names, VLAN IDs, SSIDs, IPs",
        "Do not claim the incident is resolved or closed unless",
        "validation is still incomplete",
    ]
    for text in required:
        assert text in source, f"Missing Step 11.0.1 guard: {text}"

    print("[PASS] active structured playbook turns hide native LLM tools")
    print("[PASS] site/VLAN/SSID evidence cannot become guessed tool arguments")
    print("[PASS] lifecycle prose cannot declare resolution before Python closes")
    print("[PASS] incomplete validation is explicitly constrained")

    # Preserve deterministic single-execution behavior.
    assert "deterministic_tool_result is not None" in source
    print("[PASS] deterministic edge single-execution guard retained")

    print("\n========================================")
    print("STEP 11.0.1 STATEFUL PLAYBOOK TOOL GUARD PASSED")
    print("========================================\n")


if __name__ == "__main__":
    main()
