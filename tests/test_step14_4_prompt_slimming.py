from pathlib import Path


def main():
    print()
    print("========================================")
    print("RazaAI Step 14.4 Prompt Slimming")
    print("========================================")
    print()

    source = (Path(__file__).resolve().parents[1] / "app/agent/agent.py").read_text()

    base_start = source.index('RAZAAI_CORE_IDENTITY = """')
    runtime_start = source.index('RAZAAI_RUNTIME_CONTRACT = """')
    doc_start = source.index('DOCUMENT_TOOL_GUIDANCE = """')
    base_block = source[base_start:runtime_start]
    runtime_block = source[runtime_start:doc_start]

    assert len(base_block) < 600
    assert "Brad Heffernan created RazaAI" not in runtime_block
    assert "Qwen3 4B Heretic Q4_K_M is your underlying" not in runtime_block
    assert "Ollama is the runtime" not in runtime_block
    print("[PASS] application runtime prompt no longer re-teaches persistent identity")

    guidance_start = source.index("def _build_interaction_turn_guidance")
    guidance_end = source.index("class RazaAgent:", guidance_start)
    guidance = source[guidance_start:guidance_end]
    assert "Cortana-inspired" not in guidance
    assert "How can I help" not in guidance
    assert "SENSITIVE SECURITY" in guidance
    assert "Never request, display" in guidance
    print("[PASS] per-turn guidance is routing/security state, not personality training")

    identity_start = source.index('self_identity_guidance = ""')
    identity_end = source.index('if edge_route.kind == "document"', identity_start)
    identity = source[identity_start:identity_end]
    # A later step re-introduced a compact, immutable identity anchor that is
    # injected ONLY on explicit identity turns (guarded by self_identity_turn).
    assert "if self_identity_turn:" in identity
    assert "Brad Heffernan" in identity and "Do not use tools to verify them" in identity
    assert identity.count("Brad Heffernan") <= 2  # Creator + created-in-2019
    print("[PASS] identity facts are a compact anchor on identity turns only")

    prompt_start = source.index('if mode == "conversation"', source.index("current_personality_guidance ="))
    prompt_end = source.index("combined_system_guidance =", prompt_start)
    prompt = source[prompt_start:prompt_end]
    assert "RAZAAI_BASE_PERSONA," not in prompt
    assert "RAZAAI_RUNTIME_CONTRACT" in prompt
    print("[PASS] base persona is no longer injected into every turn")

    assert "neutral_sensitive_ack" in source
    assert 'mode="conversation"' in source[source.index("neutral_sensitive_ack"):source.index("self.last_interaction = interaction")]
    print("[PASS] neutral ok/thanks can close stale sensitive advice context")

    print()
    print("========================================")
    print("STEP 14.4 PROMPT SLIMMING PASSED")
    print("========================================")


if __name__ == "__main__":
    main()
