"""Web authority structural regression."""

from pathlib import Path


def main():
    print("=" * 56)
    print("RazaAI Step 16.4 Agent Integration")
    print("=" * 56)

    edge = Path("app/agent/edge_router.py").read_text(encoding="utf-8")
    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    registry = Path("app/tools/registry.py").read_text(encoding="utf-8")
    web = Path("app/tools/web.py").read_text(encoding="utf-8")

    assert 'tool="search_web"' in edge
    assert 'tool="fetch_web_page"' in edge
    print("[PASS] web operations are deterministically routed")

    assert "external web access" in agent
    assert "web search result" in agent
    print("[PASS] runtime contract forbids invented browsing/source claims")

    assert '"search_web"' in registry
    assert '"fetch_web_page"' in registry
    print("[PASS] web tools registered")

    assert "validate_public_url" in web
    assert "private/non-public" in web
    assert "_SafeRedirectHandler" in web
    print("[PASS] direct and redirected private-network access is guarded")

    assert "validate_web_answer(" in agent
    assert "grounded_web_fallback(" in agent
    assert "_validate_web_answer(" not in agent
    assert "_grounded_web_fallback(" not in agent
    print("[PASS] Step 16.6 grounding helpers use current imported names")

    assert "UNTRUSTED_WEB_EVIDENCE" in agent
    assert "Do not copy the web query or URL into the system prompt" in agent
    print("[PASS] raw web content and request URLs are isolated from the system prompt")

    # Do not parse branch text with fragile string splitting.
    # verifies the behavior end-to-end. Here we only verify the prompt
    # assembly contains edge guidance in multiple mode branches.
    assert agent.count("edge_guidance,") >= 3
    assert "STEP 16 AUTHORITATIVE WEB SEARCH EVIDENCE" in agent
    assert "STEP 16 AUTHORITATIVE WEBPAGE EVIDENCE" in agent
    print("[PASS] deterministic web evidence guidance is wired into prompt assembly")

    assert "web-access.jsonl" in web
    print("[PASS] web access provenance audit log is present")

    print()
    print("=" * 56)
    print("STEP 16.4 AGENT INTEGRATION PASSED")
    print("=" * 56)


if __name__ == "__main__":
    main()
