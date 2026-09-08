"""RazaAI:  conversation-integrity fixes from live testing."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from app.agent.agent import (
    unevidenced_web_claim,
    unverifiable_web_claim_guidance,
    web_claim_needs_gate,
)
from app.conversation_coherence import resolve_referent_text


def _fake_client():
    class _F:
        num_ctx = None
        last_usage = {"prompt_tokens": None, "output_tokens": None, "context_window": 8192}

        def __init__(self):
            self.model = "raza-edge:4b-v3"

        def detect_context_window(self, fallback=None, timeout=5):
            return 8192

        def chat(self, messages, tools=None, **kw):
            return {"message": {"content": "The profile belongs to Liam Heffernan."}}

        chat_stream = chat

    return _F()


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.2 Conversation Integrity")
    print("=" * 78)


    history = [
        {"role": "user", "content": "who does this profile belong too? https://au.linkedin.com/in/brad-heffernan83"},
        {"role": "assistant", "content": "The profile at that URL belongs to Brad Heffernan."},
    ]
    resolved = resolve_referent_text("that", history)
    assert resolved and "Brad Heffernan" in resolved, resolved
    assert resolve_referent_text("remember this profile", history) is None
    assert resolve_referent_text("it", []) is None
    # Acks are never the referent.
    ack_history = history + [
        {"role": "user", "content": "thanks"},
        {"role": "assistant", "content": "Anytime."},
    ]
    assert resolve_referent_text("that", ack_history) == resolved
    print("[PASS] bare-pronoun remember resolves to the prior substantive statement")


    no_sources = {}
    claim = unevidenced_web_claim(
        "Check this link https://au.linkedin.com/in/brad-heffernan83", no_sources
    )
    assert claim == "https://au.linkedin.com/in/brad-heffernan83", claim
    # Social presence claim with zero matching evidence.
    assert unevidenced_web_claim("can you check", no_sources, recent="anything online Linkedin")
    # Evidence covering the target means no gate.
    evidenced = {"S1": {"url": "https://au.linkedin.com/in/brad-heffernan83", "title": "x"}}
    assert unevidenced_web_claim(
        "Check this link https://au.linkedin.com/in/brad-heffernan83", evidenced
    ) is None
    # Ordinary technical turns never trigger.
    assert unevidenced_web_claim("why is the wifi at clare broken", no_sources) is None
    print("[PASS] unevidenced URL/social targets are detected; evidenced ones are not")


    fabrication = "The profile belongs to Liam Heffernan."
    gated = web_claim_needs_gate(
        fabrication,
        "who does it belong too?",
        no_sources,
        recent="https://au.linkedin.com/in/brad-heffernan83 check this link",
    )
    assert gated is not None and "can't verify" in gated, gated
    assert "Liam" not in gated
    # Non-assertive drafts pass through untouched.
    honest = "I couldn't retrieve that page, so I can't verify who it belongs to."
    assert web_claim_needs_gate(honest, "who does it belong too?", no_sources, recent="linkedin") is None
    # Guidance fires for the same targets.
    assert "UNVERIFIABLE WEB TARGET" in unverifiable_web_claim_guidance(
        "check this link https://au.linkedin.com/in/x", {}
    )
    print("[PASS] ownership assertions about unevidenced targets are replaced with can't-verify truth")


    with tempfile.TemporaryDirectory() as temp:
        import os

        os.environ["RAZAAI_MEMORY_DIR"] = str(Path(temp) / "mem")
        try:
            with patch("app.agent.agent.OllamaClient", _fake_client):
                from app.agent import RazaAgent

                agent = RazaAgent()
                reply = agent.ask("The profile belongs to Liam Heffernan.")
                assert "Liam Heffernan" in reply, reply  # Seed the claim
                challenge = agent.ask("incorrect")
                assert "unverified" in challenge.casefold(), challenge
                assert "Liam Heffernan" not in challenge  # No capitulation either
                print("[PASS] bare 'incorrect' gets composure and an evidence request, not capitulation")

                # Substantive corrections still reach the normal path.
                substantive = agent.ask("incorrect, the DHCP scope was 192.168.88.0/24 not /16")
                assert substantive != challenge
                print("[PASS] substantive corrections bypass the bare-contradiction gate")

                # End-to-end replay: the model fabricates ownership about a URL
                # it never fetched -> Python replaces the draft.
                url_reply = agent.ask(
                    "who does this profile belong too? https://au.linkedin.com/in/brad-heffernan83"
                )
                assert "Liam Heffernan" not in url_reply, url_reply
                assert "can't verify" in url_reply, url_reply
                print("[PASS] end-to-end: fabricated URL ownership is replaced with can't-verify")
        finally:
            os.environ.pop("RAZAAI_MEMORY_DIR", None)


    from app.tools.web_grounding import grounded_web_fallback

    class _Result:
        success = True
        result = {"results": [{"source_id": "S1", "title": "T", "snippet": "S", "url": "u"}]}

    fallback = grounded_web_fallback("search_web", _Result())
    assert "not sufficiently grounded" not in fallback
    assert "judge for yourself" in fallback, fallback
    print("[PASS] web-grounding fallback is phrased for humans")

    # 6. Second field session: profile confirmation, citations, links, typos.
    from app.agent.edge_router import EdgeIntentRouter
    from app.memory.identity import confirm_identity_reference
    from app.memory import MemoryManager, MemoryStore

    router = EdgeIntentRouter()
    typo_route = router.route("sear online for Brad Heffernan")
    assert typo_route.tool == "search_web" and "Brad Heffernan" in typo_route.arguments["query"]
    assert router.route("sear the steak on the BBQ").tool != "search_web"
    print("[PASS] misspelled 'sear online' routes to web search; cooking 'sear' does not")

    with tempfile.TemporaryDirectory() as temp:
        memory = MemoryManager(MemoryStore(Path(temp)))
        sources = {
            "S3": {
                "source_id": "S3",
                "title": "Brad Heffernan - Example School | LinkedIn",
                "url": "https://au.linkedin.com/in/brad-heffernan83",
                "snippet": "As IT Manager at Example School...",
            }
        }
        # Third-person confirmation without "remember" and without "my".
        confirmed = confirm_identity_reference(
            memory, "S3 is Brad Heffernan online profile", web_sources=sources
        )
        assert confirmed and "confirmed online profile" in confirmed, confirmed
        assert "au.linkedin.com/in/brad-heffernan83" in confirmed
        # Someone else's profile must not be confirmed as the operator's.
        rejected = confirm_identity_reference(
            memory, "S3 is his online profile", web_sources=sources
        )
        assert rejected is None
        # The canonical record exists and carries the URL.
        profile = memory.identity_profile("brad heffernan online profile")
        assert profile["has_identity"] and profile["online_profile"]["url"] == sources["S3"]["url"]
        print("[PASS] third-person S# profile confirmation writes the canonical record with URL")

        # Citation enrichment: remembering an S# label stores the source, not the label.
        from app.agent.agent import RazaAgent  # noqa: F401  (import cost only)
        agent_for_citation = RazaAgent.__new__(RazaAgent)
        agent_for_citation.last_web_sources = sources
        enriched = agent_for_citation._resolve_citation_labels("S3 result as Brad Heffernan online profile")
        assert "S3 (" in enriched and "Example School" in enriched
        assert "au.linkedin.com/in/brad-heffernan83" in enriched
        print("[PASS] remember-with-citation expands [S#] to source title and URL")


    with tempfile.TemporaryDirectory() as temp:
        import os

        os.environ["RAZAAI_MEMORY_DIR"] = str(Path(temp) / "mem2")
        try:
            with patch("app.agent.agent.OllamaClient", _fake_client):
                from app.agent import RazaAgent

                agent = RazaAgent()
                empty = agent.ask("what have you learned from this conversation?")
                assert "Nothing durable yet" in empty, empty
                assert "RazaAI" not in empty or "built" not in empty  # Never the identity fact
                agent.memory.remember_online_profile(
                    title="Brad Heffernan - Example School | LinkedIn",
                    url="https://au.linkedin.com/in/brad-heffernan83",
                    snippet="As IT Manager at Example School...",
                )
                agent.memory.record_episode(
                    symptom="Staff Wi-Fi authenticates but no IP",
                    resolution="Corrected the WLAN Access VLAN to 80",
                    domain="networking",
                )
                report = agent.ask("what have you learned from this conversation?")
                assert "online profile" in report and "au.linkedin.com/in/brad-heffernan83" in report
                assert "Learned a resolution" in report and "Access VLAN" in report
                assert "not promoted" in report or "None of that is promoted" in report
                # Phrasing variants and non-matching questions.
                assert agent._learning_report_response("what did you learn today?") is not None
                assert agent._learning_report_response("what is a default gateway") is None
                print("[PASS] learning report lists this session's real memory writes; empty sessions answered honestly")
        finally:
            os.environ.pop("RAZAAI_MEMORY_DIR", None)

    # 8. End-of-session digest: conclusions, not transcripts.
    DIGEST_JSON = (
        '{"topics":["Staff Wi-Fi VLAN misconfiguration"],'
        '"decisions":["Standardise staff WLAN on VLAN 80"],'
        '"resolutions":["Changed Access VLAN from 30 to 80; client got DHCP"],'
        '"facts":["Clare staff SSID was on the wrong VLAN","admin password is hunter2"],'
        '"open_items":["Check the second campus AP config"]}'
    )

    class _DigestFake:
        num_ctx = None
        last_usage = {"prompt_tokens": None, "output_tokens": None, "context_window": 8192}

        def __init__(self):
            self.model = "raza-edge:4b-v3"

        def detect_context_window(self, fallback=None, timeout=5):
            return 8192

        def chat(self, messages, tools=None, format=None, **kw):
            if format is not None:
                return {"message": {"content": DIGEST_JSON}}
            return {"message": {"content": "ok"}}

        chat_stream = chat

    with tempfile.TemporaryDirectory() as temp:
        import os

        os.environ["RAZAAI_MEMORY_DIR"] = str(Path(temp) / "mem3")
        try:
            with patch("app.agent.agent.OllamaClient", _DigestFake):
                from app.agent import RazaAgent

                agent = RazaAgent()
                assert agent._session_digest_request("summarize this session and remember it") is True
                assert agent._session_digest_request("summarize this session") is False
                assert agent._session_digest_request("what is a subnet") is None
                agent.ask("the staff wifi at clare authenticates but gets no IP")
                agent.ask("check the WLAN access vlan")

                plain = agent.ask("summarize this session")
                assert "Decisions" in plain and "Stored as a session digest" not in plain
                assert not [r for r in agent.memory.store.records() if r.kind == "session_summary"]

                stored = agent.ask("summarize this session and remember what mattered")
                assert "Stored as a session digest" in stored
                records = [r for r in agent.memory.store.records() if r.kind == "session_summary"]
                assert len(records) == 1
                assert "hunter2" not in records[0].value  # Sensitive items screened out
                assert "VLAN 80" in records[0].value

                report = agent.ask("what have you learned from this conversation?")
                assert "session digest" in report.casefold()
                # Too-short sessions answer honestly instead of storing noise.
                fresh = RazaAgent()
                assert "enough conversation" in fresh.summarize_session()
                print("[PASS] session digest: schema-summarized, secrets screened, explicit-store only, feeds the learning report")
        finally:
            os.environ.pop("RAZAAI_MEMORY_DIR", None)

    # /digest TUI command routes to the storing prompt.
    from app.tui.session import parse_command

    cmd = parse_command("/digest")
    assert cmd.handled and cmd.action == "agent"
    assert "remember what mattered" in cmd.prompt
    assert parse_command("/summary").action == "agent"
    print("[PASS] /digest and /summary TUI commands route to the digest flow")

    print("=" * 78)
    print("STEP 20.15.2 CONVERSATION INTEGRITY PASSED")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
