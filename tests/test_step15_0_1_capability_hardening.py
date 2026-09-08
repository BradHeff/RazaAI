"""Capability-hardening structural checks."""

from pathlib import Path


def main():
    print("=" * 56)
    print("RazaAI Step 15.0.1 Capability Hardening")
    print("=" * 56)

    path = Path("app/agent/agent.py")
    text = path.read_text(encoding="utf-8")

    assert "_is_capability_only_question" in text
    assert 'mode="conversation"' in text
    print("[PASS] capability-only questions are forced to conversation")

    technical = Path("app/playbooks/technical_guidance.py").read_text(encoding="utf-8")
    assert "_is_conceptual_fortigate_question" in text
    assert "_fortigate_turn_guidance" in text
    assert "Phase 2 selectors/proposals" in technical
    assert "session/log/debug-flow or matched policy ID evidence" in technical
    assert "FORTIGATE ADMIN GUI ACCESS" in technical
    print("[PASS] FortiGate policy/IPsec/admin evidence guidance is present")

    assert "Blocked duplicate create_document execution" in text
    assert "executed_tools_this_turn" in text
    print("[PASS] duplicate document execution is structurally blocked")

    assert 'arguments["sections"]' in text
    assert '"paragraphs": [body_text]' in text
    print("[PASS] simple DOCX request is normalized before first execution")

    print()
    print("=" * 56)
    print("STEP 15.0.1 CAPABILITY HARDENING PASSED")
    print("=" * 56)


if __name__ == "__main__":
    main()
