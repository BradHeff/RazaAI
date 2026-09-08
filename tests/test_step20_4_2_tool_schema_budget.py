"""RazaAI tool-schema budgeting and advice routing."""

from pathlib import Path

from app.interaction import InteractionRouter


class Expert:
    category = "networking"


NEC = (
    "what if i want to check 1 way audio on NEC phone for internal calls "
    "between campus over ipsec VPN tunnel?"
)


def main():
    print("=" * 76)
    print("RazaAI Step 20.4.2 Tool Schema Budget")
    print("=" * 76)

    context = InteractionRouter().classify(NEC, expert_route=Expert())
    assert context.mode == "advice"
    assert context.action_requested is False
    assert context.allow_tools is False
    assert context.domain == "networking"
    print("[PASS] hypothetical NEC/IPsec question is advice, not a live tool action")

    active = InteractionRouter().classify(
        "check the route to 10.10.20.5 over the IPsec VPN",
        expert_route=Expert(),
    )
    assert active.mode == "action"
    assert active.allow_tools is True
    print("[PASS] genuine explicit networking checks still allow tools")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    registry = Path("app/tools/registry.py").read_text(encoding="utf-8")

    assert "_model_tools_for_turn" in agent
    assert "else self._model_tools_for_turn(interaction, user_input)" in agent
    assert "else self.tools.get_definitions()" not in agent
    assert "scoped model schemas" in agent
    print("[PASS] agent no longer sends the full tool registry on action turns")

    assert "categories=None, names=None" in registry
    assert 'metadata.get("category") not in categories' in registry
    assert 'name not in names' in registry
    print("[PASS] registry supports category/name-scoped model definitions")

    # Networking scopes must not drag unrelated high-cost authority families in.
    helper_start = agent.index("def _model_tools_for_turn")
    helper_end_candidates = [
        pos for marker in ("def _format_improvement_summary", "def ask(")
        if (pos := agent.find(marker, helper_start + 1)) >= 0
    ]
    assert helper_end_candidates
    helper = agent[helper_start:min(helper_end_candidates)]
    assert '"create_document"' in helper  # Only in explicit document branch
    assert '"start_self_improvement"' not in helper
    assert '"run_model_training"' not in helper
    assert '"promote_model_candidate"' not in helper
    print("[PASS] networking schema selection excludes unrelated improvement/model tools")

    print()
    print("=" * 76)
    print("STEP 20.4.2 TOOL SCHEMA BUDGET PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
