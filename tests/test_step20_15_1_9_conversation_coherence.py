""":  conversation coherence, anti-looping, and identity timeline."""

from pathlib import Path

from app.config import APP_VERSION, IDENTITY_FACTS, IDENTITY_ORIGIN_STORY, RAZAAI_VOICE_CONTRACT, version_tuple
from app.conversation_coherence import (
    analyze_conversation_turn,
    coherence_repair_guidance,
    coherence_requires_buffering,
    conversation_coherence_guidance,
    self_identity_timeline_response,
    validate_conversation_response,
)
from app.reasoning_context import should_use_identity_personalization

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.9 Conversation Coherence")
    print("=" * 78)

    check(version_tuple(APP_VERSION) >= version_tuple("20.15.1.9"), "version gate is at least 20.15.1.9")

    definition = (
        "A secret store is a dedicated credential management system. It securely holds "
        "passwords, API keys and connection strings, supports auditing and rotation, and "
        "integrates with application runtimes."
    )
    history = [
        {"role": "user", "content": "how does a secret store work?"},
        {"role": "assistant", "content": definition},
    ]

    recommend_text = "what do you recomend for a secret store?"
    recommend_focus = analyze_conversation_turn(recommend_text, history)
    check(recommend_focus.intent == "recommend", "common `recomend` typo still routes as recommendation intent")
    check(recommend_focus.topic == "secret store", "recommendation extracts the current secret-store topic")
    check(coherence_requires_buffering(recommend_focus), "recommendation transition is buffered before display")

    valid, reason, _ = validate_conversation_response(recommend_text, definition, history)
    check(not valid and "repeat" in reason, "repeated secret-store definition is rejected after explain -> recommend")

    recommendation = (
        "For application secrets, I'd use Azure Key Vault in a Microsoft-heavy environment; "
        "Bitwarden Secrets Manager or HashiCorp Vault are solid alternatives."
    )
    valid, _, _ = validate_conversation_response(recommend_text, recommendation, history)
    check(valid, "concrete named secret-store recommendation passes")

    history += [
        {"role": "user", "content": recommend_text},
        {"role": "assistant", "content": recommendation},
    ]
    locate_text = "where can i get one?"
    locate_focus = analyze_conversation_turn(locate_text, history)
    check(locate_focus.intent == "locate" and locate_focus.topic == "secret store", "`where can I get one?` resolves the prior secret-store topic")
    check(coherence_requires_buffering(locate_focus), "referential location/access turn is buffered")

    valid, reason, _ = validate_conversation_response(locate_text, definition, history)
    check(not valid, "definition-only answer is rejected for a location/access request")
    product_list_only = "Microsoft Azure Key Vault, HashiCorp Vault, AWS Secrets Manager and GCP Secret Manager can all work."
    valid, _, _ = validate_conversation_response(locate_text, product_list_only, history)
    check(not valid, "a bare product list is not accepted as an answer to `where can I get one?`")
    access_answer = "Azure Key Vault is available through the Azure portal; HashiCorp Vault is available from HashiCorp's official site."
    valid, _, _ = validate_conversation_response(locate_text, access_answer, history)
    check(valid, "concrete provider/access answer passes the location intent")

    history += [
        {"role": "user", "content": locate_text},
        {"role": "assistant", "content": access_answer},
    ]
    loop_text = "ok were looping now"
    loop_focus = analyze_conversation_turn(loop_text, history)
    check(loop_focus.loop_feedback and loop_focus.previous_intent == "locate", "explicit loop feedback retains the unresolved prior intent")
    check(coherence_requires_buffering(loop_focus), "loop-breaking turn is always buffered")
    valid, _, _ = validate_conversation_response(loop_text, definition, history)
    check(not valid, "loop feedback cannot be answered by repeating the original definition")
    loop_answer = "Fair. I was circling the definition. Azure Key Vault is in the Azure portal; if you want self-hosted, get HashiCorp Vault from its official site."
    valid, _, _ = validate_conversation_response(loop_text, loop_answer, history)
    check(valid, "loop-breaking answer acknowledges the problem and progresses the pending access request")

    workload_history = [
        {"role": "user", "content": "what about Excel?"},
        {"role": "assistant", "content": "Excellent. Now the insecure password list has rows and columns."},
    ]
    workload_text = "what are your thoughts on my work load at the school?"
    workload_focus = analyze_conversation_turn(workload_text, workload_history)
    check(workload_focus.intent == "opinion", "workload question is classified as an opinion/assessment")
    valid, _, _ = validate_conversation_response(
        workload_text,
        "Better than an Excel spreadsheet. Keep credentials out of the document.",
        workload_history,
    )
    check(not valid, "stale Excel callback cannot replace the requested workload assessment")
    workload_answer = (
        "Your workload at the school looks heavy for one person: the role spans infrastructure, "
        "networking and operational responsibility. The Excel joke can wait; delegation probably shouldn't."
    )
    valid, _, _ = validate_conversation_response(workload_text, workload_answer, workload_history)
    check(valid, "substantive workload assessment may still carry a personality callback")

    profile = {"has_identity": True, "job_title": "IT Manager", "organization": "Example School"}
    check(
        should_use_identity_personalization(workload_text, profile=profile),
        "workload opinion can use compact confirmed identity context without broad memory retrieval",
    )

    guidance = conversation_coherence_guidance(recommend_text, history).casefold()
    check("bitwarden is a legitimate choice for human/user credentials" in guidance, "Bitwarden Password Manager is not incorrectly dismissed for human credentials")
    check("bitwarden secrets manager" in guidance and "azure key vault" in guidance, "application secret-manager use case is distinguished")

    repair = coherence_repair_guidance(recommend_focus, "test").casefold()
    check("cortana-inspired" in repair and "dry wit" in repair, "coherence repair preserves the established Cortana-inspired personality")
    check("cortana" in RAZAAI_VOICE_CONTRACT.casefold(), "20.15.1.8 personality contract remains intact")

    check(IDENTITY_FACTS["origin_year"] == 2019 and IDENTITY_FACTS["resumed_year"] == 2024, "Python identity facts preserve both RazaAI milestones")
    check("movie scripts" in IDENTITY_ORIGIN_STORY and "keyword detection" in IDENTITY_ORIGIN_STORY, "2019 origin accurately describes the movie-script/keyword chatbot rather than inventing an early LLM")
    timeline = self_identity_timeline_response("when?", identity_context_active=True)
    check(timeline is not None and "2019" in timeline and "2024" in timeline, "ambiguous identity `when?` returns both confirmed RazaAI milestones")
    explicit_timeline = self_identity_timeline_response("when were you made?", identity_context_active=False)
    check(explicit_timeline is not None and "2019" in explicit_timeline and "2024" in explicit_timeline, "explicit RazaAI creation-date question uses Python-owned timeline")
    check(self_identity_timeline_response("when is BGP used?", identity_context_active=False) is None, "unrelated `when` questions do not trigger RazaAI identity history")

    agent_source = (ROOT / "app" / "agent" / "agent.py").read_text(encoding="utf-8")
    check("coherence_buffered = coherence_requires_buffering" in agent_source, "agent computes a pre-display coherence buffer gate")
    check("and not coherence_buffered" in agent_source, "coherence-sensitive drafts are not streamed before validation")
    check("validate_conversation_response(" in agent_source and "coherence_repair_guidance(" in agent_source, "agent final-answer path validates and repairs incoherent drafts")

    print("=" * 78)
    print("STEP 20.15.1.9 CONVERSATION COHERENCE PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
