"""RazaAI:  thin reference chunks expand to real content; APIPA and FortiGate-policy knowledge exists and leads; Modelfile caps the prefill batch."""

from pathlib import Path

from app.diagnostics.engine import DiagnosticEngine
from app.experts.router import ExpertRouter
from app.tools.registry import ToolRegistry

APIPA = ("A Windows laptop has a 169.254.44.8 address and cannot reach the gateway. "
         "What does that suggest and what should I check first?")
POLICY = ("A FortiGate firewall policy is not matching traffic. "
          "What should I verify before editing the policy?")


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.12 Thin Evidence + Knowledge Coverage")
    print("=" * 78)

    for rel in ("knowledge/networking/apipa-169-254-dhcp-failure-troubleshooting.md",
                "knowledge/networking/fortigate-policy-not-matching-troubleshooting.md"):
        assert Path(rel).is_file() and Path(rel + ".meta.json").is_file(), rel
    apipa_doc = Path("knowledge/networking/apipa-169-254-dhcp-failure-troubleshooting.md").read_text(encoding="utf-8").lower()
    assert all(t in apipa_doc for t in ("dhcp relay", "scope", "lease", "vlan", "ip helper"))
    policy_doc = Path("knowledge/networking/fortigate-policy-not-matching-troubleshooting.md").read_text(encoding="utf-8").lower()
    assert all(t in policy_doc for t in ("policy order", "session", "debug flow", "policy id", "route"))
    print("[PASS] APIPA/DHCP and FortiGate policy-matching reference documents exist")

    registry = ToolRegistry()
    for query, filename in ((APIPA, "apipa-169-254-dhcp-failure-troubleshooting.md"),
                            (POLICY, "fortigate-policy-not-matching-troubleshooting.md")):
        result = registry.execute("search_knowledge", {"query": query, "category": "networking"})
        assert result.success, result.error
        assert result.result["results"][0]["citation"]["filename"] == filename
    print("[PASS] both capability prompts retrieve the new documents as primary evidence")

    engine = DiagnosticEngine()
    router = ExpertRouter()
    thin = {"text": "# FortiGate firewall policy not matching traffic — verify before editing",
            "citation": {"knowledge_type": "reference",
                         "source": str(Path("knowledge/networking/fortigate-policy-not-matching-troubleshooting.md").resolve()),
                         "title": "policy doc"}}
    rendered = engine._format_item(thin, "PRIMARY EVIDENCE")
    assert "policy_id=" in rendered and "Policy order" in rendered
    print("[PASS] a bare-title reference chunk is expanded to the document's opening sections")

    guidance = engine.guidance(engine.build_context(POLICY, router.route(POLICY)))
    assert "diagnose sys session" in guidance and "debug flow" in guidance
    guidance2 = engine.guidance(engine.build_context(APIPA, router.route(APIPA)))
    assert "DHCP relay" in guidance2 or "dhcp relay" in guidance2.lower()
    assert "Primary hypothesis:" in guidance2  # Still the compact incident template
    print("[PASS] both prompts now carry an actionable checklist inside the incident template")

    from app.profiles import PROFILES
    assert "PARAMETER num_batch 128" in PROFILES["8g"].modelfile("example")
    assert "PARAMETER num_batch 512" in PROFILES["standard"].modelfile("example")
    print("[PASS] generated model definitions cap prompt batches for each device")

    print("=" * 78)
    print("STEP 20.8.12 THIN EVIDENCE + KNOWLEDGE COVERAGE PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
