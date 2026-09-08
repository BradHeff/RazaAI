""":  identity/follow-up authority and workload topic reset."""

from pathlib import Path

from app.config import APP_VERSION, version_tuple
from app.conversation_coherence import (
    analyze_conversation_turn,
    self_identity_authoritative_response,
    validate_conversation_response,
)
from app.personality import identity_personalization_guidance

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.10 Identity + Follow-up Authority")
    print("=" * 78)

    check(version_tuple(APP_VERSION) >= version_tuple("20.15.1.10"), "version gate is at least 20.15.1.10")

    who = self_identity_authoritative_response("who are you?", identity_context_active=False)
    check(who is not None and who.startswith("RazaAI"), "`who are you?` is Python-owned RazaAI identity")
    check("Qwen" not in who, "base-model lineage cannot replace RazaAI identity")

    creator = self_identity_authoritative_response(
        "made by whome?", identity_context_active=True, user_name="Brad Heffernan"
    )
    check(creator is not None and "Brad Heffernan" in creator, "typoed creator follow-up resolves deterministically")
    check("You" in creator, "confirmed creator can receive a concise personal callback")

    timeline = self_identity_authoritative_response("when", identity_context_active=True)
    check(timeline is not None and "2019" in timeline and "2024" in timeline, "short `when` resolves the authoritative two-stage RazaAI timeline")

    model = self_identity_authoritative_response("what model are you using?", identity_context_active=False)
    check(model is not None and "RazaAI" in model and __import__("app.config", fromlist=["IDENTITY_FACTS"]).IDENTITY_FACTS["model"] in model, "explicit model question distinguishes RazaAI identity from underlying model")

    history = [
        {"role": "user", "content": "what do you recommend for a secret store?"},
        {"role": "assistant", "content": "Bitwarden Secrets Manager, HashiCorp Vault or Azure Key Vault."},
    ]
    question = "what are your thoughts on my workload at the school?"
    focus = analyze_conversation_turn(question, history)
    check(focus.intent == "opinion" and focus.previous_topic == "secret store", "workload turn records the previous secret-store topic without inheriting it")

    bad = "I've seen workloads grow too fast. If the school is a real customer, it's outpacing the secret store."
    valid, _, _ = validate_conversation_response(question, bad, history)
    check(not valid, "generic workload wording plus stale secret-store comparison is rejected")

    good = (
        "Your workload at the school is heavy for one person. You're carrying a broad operational role, "
        "and the amount of responsibility is the part I'd fix before it becomes permanent background noise. "
        "Apparently delegation is still waiting for a maintenance window."
    )
    valid, _, _ = validate_conversation_response(question, good, history)
    check(valid, "substantive workload assessment passes while retaining a Cortana-style callback")

    profile = {
        "has_identity": True,
        "query": question,
        "name": "Brad Heffernan",
        "job_title": "IT Manager | Senior System Engineer",
        "organization": "Example School",
        "online_profile": {
            "snippet": "As IT Manager at Example School, I lead initiatives across on-premises and cloud systems, Active Directory, Azure AD and network security."
        },
    }
    guidance = identity_personalization_guidance(profile)
    check("Confirmed professional profile excerpt" in guidance and "network security" in guidance, "workload opinions receive confirmed professional detail rather than stale chat topics")

    agent_source = (ROOT / "app" / "agent" / "agent.py").read_text(encoding="utf-8")
    check("self_identity_authoritative_response(" in agent_source, "agent final path calls Python identity authority before model improvisation")
    check("ctx.self_identity_turn or self.self_identity_context_active" in agent_source, "short identity follow-ups inherit the active identity thread")

    print("=" * 78)
    print("STEP 20.15.1.10 IDENTITY + FOLLOW-UP AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
