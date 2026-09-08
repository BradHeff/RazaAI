import tempfile
from pathlib import Path

from app.context.curated import CuratedProjectContext
from app.diagnostics.contextual import contextual_diagnostic_query
from app.diagnostics.ranking import rank_incident_evidence
from app.interaction.corrections import correction_followup_guidance
from app.interaction.router import InteractionRouter
from app.experts.router import ExpertRouter
from app.playbooks.technical_guidance import (
    fortigate_turn_guidance,
    is_conceptual_fortigate_question,
)


def main():
    print("=" * 72)
    print("RazaAI Step 20.13.15 Support Context Isolation")
    print("=" * 72)

    # Regression for the exact production failure: common stopwords must never
    # make BRANDING.md look relevant to FortiGate troubleshooting.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "knowledge/project").mkdir(parents=True)
        (root / "BRANDING.md").write_text(
            "# Brand\nUse green and gold. Error states use red.\n",
            encoding="utf-8",
        )
        ctx = CuratedProjectContext(root)
        bad_queries = [
            "what console command to check http and https ports open on fortigate",
            "that command gives Unknown action 0 error on fortigate",
            "what has that to do with checking http and https access to the fortigate?",
        ]
        for query in bad_queries:
            paths = [doc.path for _, doc in ctx.search(query, document_request=False)]
            assert "BRANDING.md" not in paths, (query, paths)
        assert "BRANDING.md" in ctx.guidance("create a staff document", document_request=True)
        assert "BRANDING.md" in ctx.guidance("what is our branding style?", document_request=False)
        print("[PASS] branding context cannot leak into unrelated ICT turns")

    messages = [
        {"role": "user", "content": "i can ping and connect SSH but not via web. error is connection refused"},
        {"role": "assistant", "content": "Use tcpdump to inspect traffic."},
        {"role": "user", "content": "what console command to check http and https ports open on fortigate"},
        {"role": "assistant", "content": "show webfilter ftgd-local-rating"},
    ]
    query = contextual_diagnostic_query(
        "that command gives Unknown action 0 error on fortigate",
        messages,
        previous_domain="networking",
        current_domain="networking",
    )
    assert "ping and connect SSH" in query
    assert "http and https ports" in query
    assert "tcpdump" not in query
    assert "ftgd-local-rating" not in query
    print("[PASS] diagnostic follow-ups reuse user context but never assistant mistakes")

    wrong = {
        "score": 0.95,
        "semantic_score": 0.95,
        "text": (
            "FortiGate web filter local category override. Use show webfilter "
            "ftgd-local-rating and show webfilter ftgd-local-cat."
        ),
        "citation": {"title": "Web filter overrides"},
    }
    right = {
        "score": 0.72,
        "semantic_score": 0.72,
        "text": (
            "FortiGate GUI HTTPS administrative access. Check set allowaccess https, "
            "admin-sport, diagnose sys tcpsock and diagnose sniffer packet."
        ),
        "citation": {"title": "Admin GUI access"},
    }
    ranked = rank_incident_evidence(
        "FortiGate web GUI connection refused; SSH works; check HTTP HTTPS admin port 443",
        [wrong, right],
    )
    assert len(ranked) == 1
    assert ranked[0]["citation"]["title"] == "Admin GUI access"
    print("[PASS] same-vendor/different-subsystem evidence is rejected")

    router = ExpertRouter()
    interaction = InteractionRouter().classify(
        "i lost access to my fortigate GUI the web gui does not load",
        expert_route=router.route("i lost access to my fortigate GUI the web gui does not load"),
    )
    assert interaction.mode == "troubleshooting"
    assert interaction.domain == "networking"
    print("[PASS] GUI access-loss wording enters troubleshooting mode immediately")

    command_question = "what console command to check http and https ports open on fortigate"
    assert is_conceptual_fortigate_question(command_question)
    guidance = fortigate_turn_guidance(command_question)
    assert "FORTIGATE ADMIN GUI ACCESS" in guidance
    assert "diagnose sys tcpsock" in guidance
    assert "admin-sport" in guidance
    assert "allowaccess" in guidance
    assert "tcpdump" in guidance  # Appears only in the explicit 'do not suggest' rule
    assert "ftgd-local-rating" not in guidance
    assert "FORTIGATE POLICY EVIDENCE" not in guidance
    print("[PASS] FortiGate admin-plane questions get admin-plane CLI guidance")

    correction = correction_followup_guidance(
        "what has that to do with checking http and https access to the fortigate?",
        messages,
    )
    assert "USER CORRECTION / RE-ANCHOR" in correction
    assert "http and https ports" in correction
    assert "show webfilter" not in correction
    print("[PASS] user challenges re-anchor to user intent, not assistant output")

    kb = Path("knowledge/networking/fortigate-admin-gui-access-troubleshooting.md")
    text = kb.read_text(encoding="utf-8")
    for required in (
        "show system interface <interface>",
        "admin-port",
        "admin-sport",
        "diagnose sys tcpsock",
        "diagnose sniffer packet",
    ):
        assert required in text
    assert "show webfilter ftgd-local-rating" not in text
    print("[PASS] curated FortiGate GUI recovery knowledge is present")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    engine = Path("app/diagnostics/engine.py").read_text(encoding="utf-8")
    assert "contextual_diagnostic_query" in agent
    assert "retrieval_query=diagnostic_retrieval_query" in agent
    assert "correction_followup_guidance" in agent
    assert "retrieval_query: str | None = None" in engine
    print("[PASS] agent/diagnostic pipeline is wired to contextual retrieval")

    print("\n" + "=" * 72)
    print("STEP 20.13.15 SUPPORT CONTEXT ISOLATION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
