"""Personality + response provenance regression."""

from __future__ import annotations

from pathlib import Path

from app.config import APP_VERSION, RAZAAI_VOICE_CONTRACT, version_tuple
from app.interaction.router import InteractionRouter
from app.personality import (
    identity_personalization_guidance,
    response_already_has_personality,
    security_personality_lead,
)
from app.response_provenance import (
    explicitly_excludes_memory,
    is_provenance_query,
    render_response_provenance,
)

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.6 Personality + Provenance")
    print("=" * 78)

    check(version_tuple(APP_VERSION) >= version_tuple("20.15.1.6"), "version is at least 20.15.1.6")

    voice = RAZAAI_VOICE_CONTRACT.casefold()
    check(
        all(word in voice for word in ("sassy", "sarcastic", "blunt", "customer-service")),
        "voice contract makes sass/sarcasm/bluntness application-authoritative",
    )

    context = InteractionRouter().classify("i save passwords in a text file")
    guidance = InteractionRouter.guidance(context).casefold()
    check(
        context.mode == "advice" and context.sensitive and "sarcastic" in guidance,
        "plaintext-password statement receives security-aware personality guidance",
    )

    profile = {
        "has_identity": True,
        "name": "Example User",
        "job_title": "IT Manager",
        "organization": "Example School",
        "razaai_relationship": "creator",
    }
    identity = identity_personalization_guidance(profile)
    check(
        "IT Manager" in identity and "Example School" in identity,
        "confirmed role/organisation can personalize relevant replies",
    )
    lead = security_personality_lead("I save passwords in a text file", profile)
    check(
        "IT Manager" in lead and "text file" in lead and "know better" in lead,
        "obvious plaintext-password mistake gets a contextual blunt/sarcastic lead",
    )
    check(response_already_has_personality(lead), "personality lead is not duplicated")

    check(is_provenance_query("is this memory response?"), "memory-attribution follow-up is detected")
    check(is_provenance_query("was that from memory?"), "alternate memory-attribution follow-up is detected")
    check(
        "general model knowledge/reasoning" in render_response_provenance({"kind": "model_knowledge"}),
        "general model knowledge is not falsely called persistent memory",
    )
    personalized = render_response_provenance(
        {"kind": "model_knowledge", "identity_memory_used": True}
    )
    check(
        "technical answer" in personalized and "personalize" in personalized,
        "provenance separates technical reasoning from identity-memory personalization",
    )
    check(
        "persistent memory" in render_response_provenance({"kind": "persistent_memory"}).casefold(),
        "true memory lookup is identified as persistent memory",
    )

    query = "tell me something not in memory about networking"
    check(explicitly_excludes_memory(query), "explicit no-memory request is detected")

    agent_source = (ROOT / "app" / "agent" / "agent.py").read_text()
    check(
        "core_identity_for(active_model, full_voice=True)" in agent_source,
        "raza-edge receives the full voice contract from the application",
    )
    check(
        "edge_route = self._response_provenance_route(user_input)" in agent_source
        and agent_source.index("edge_route = self._response_provenance_route(user_input)")
        < agent_source.index("edge_route = self._referential_identity_memory_route(user_input)"),
        "provenance follow-ups are resolved before generic memory routing",
    )
    check(
        'not memory_excluded' in agent_source
        and 'project_context_needed' in agent_source
        and 'incident_context_needed' in agent_source,
        "explicit no-memory turns suppress stored project/incident history as well as personal memory",
    )
    check(
        "security_personality_lead(" in agent_source
        and "response_already_has_personality(content)" in agent_source,
        "high-signal security mistakes have a deterministic anti-boilerplate personality safeguard",
    )

    print("=" * 78)
    print("STEP 20.15.1.6 PERSONALITY + PROVENANCE PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
