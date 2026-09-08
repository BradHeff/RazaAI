""":  reasoning-first context isolation + personality priority."""

from pathlib import Path

from app.config import APP_VERSION, version_tuple
from app.interaction.router import InteractionRouter
from app.personality import security_personality_lead
from app.reasoning_context import (
    current_turn_focus,
    focus_repair_guidance,
    personality_turn_guidance,
    reasoning_turn_guidance,
    response_addresses_focus,
    should_retrieve_incident_context,
    should_retrieve_persistent_memory,
    should_retrieve_project_context,
    should_use_identity_personalization,
)

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.7 Reasoning Context Isolation")
    print("=" * 78)

    check(version_tuple(APP_VERSION) >= version_tuple("20.15.1.7"), "version gate is at least 20.15.1.7")

    general = InteractionRouter().classify("why is the sky blue?")
    check(not should_retrieve_persistent_memory("why is the sky blue?", general), "general knowledge does not retrieve persistent memory")
    check(not should_retrieve_project_context("why is the sky blue?", interaction=general), "general knowledge does not retrieve project context")
    check(not should_retrieve_incident_context(general), "general knowledge does not retrieve incident history")

    check(should_retrieve_persistent_memory("what is my job?", general), "direct user-profile question may retrieve persistent memory")
    check(should_retrieve_persistent_memory("what did we fix last time?", general), "explicit historical recall may retrieve persistent memory")
    check(should_retrieve_project_context("how does this RazaAI project route coding?", interaction=general), "explicit RazaAI project question may retrieve project context")

    troubleshooting = InteractionRouter().classify("FortiGate GUI is down but SSH works")
    check(should_retrieve_incident_context(troubleshooting), "active troubleshooting may retrieve incident context")

    profile = {
        "has_identity": True,
        "name": "Example User",
        "job_title": "IT Manager",
        "organization": "Example School",
    }
    check(not should_use_identity_personalization("why is the sky blue?", general, profile), "identity facts stay out of neutral general reasoning")

    sensitive = InteractionRouter().classify("i save passwords in a text file")
    check(should_use_identity_personalization("i save passwords in a text file", sensitive, profile), "confirmed role may personalize an unsafe security response")

    paper_followup = InteractionRouter().classify(
        "what if i write them on paper next to my keyboard?",
        previous=sensitive,
    )
    check(paper_followup.sensitive and paper_followup.mode == "advice", "referential paper follow-up retains credential-security context")
    check(should_use_identity_personalization("what if i write them on paper next to my keyboard?", paper_followup, profile), "long credential-storage follow-up retains contextual personality")

    check(current_turn_focus("what about excel spreadsheet?") == "excel spreadsheet", "Excel follow-up is the current candidate")
    focus_guidance = reasoning_turn_guidance("what about excel spreadsheet?").casefold()
    check("current explicit focus/candidate: excel spreadsheet" in focus_guidance, "late reasoning contract pins the current comparison object")
    check("previous" in focus_guidance and "from scratch" in focus_guidance, "late reasoning contract rejects stale prior-answer reuse")

    check(not response_addresses_focus("A Word document is still unsafe.", "excel spreadsheet"), "stale Word answer fails Excel focus validation")
    check(response_addresses_focus("An Excel spreadsheet is still poor credential storage.", "excel spreadsheet"), "correct Excel answer passes focus validation")
    check("excel spreadsheet" in focus_repair_guidance("excel spreadsheet").casefold(), "bounded retry explicitly re-anchors the current object")

    voice = personality_turn_guidance(sensitive).casefold()
    check(all(token in voice for token in ("sassy", "sarcasm", "help-desk")), "late personality contract keeps the Cortana-style voice visible")

    word = security_personality_lead("I save passwords in a Word document", profile)
    excel = security_personality_lead("I store passwords in an Excel spreadsheet", profile)
    paper = security_personality_lead("I put passwords on paper next to my keyboard", profile)
    vault = security_personality_lead("what about KeePass?", profile)
    check("Word document" in word and "know better" in word, "Word credential storage gets a contextual personality fallback")
    check("Excel spreadsheet" in excel and "rows and columns" in excel, "Excel credential storage gets a current-object sarcastic fallback")
    check("paper next to the keyboard" in paper, "paper credential storage gets a current-object personality fallback")
    check(vault == "", "proper password-manager candidate is not mocked as unsafe")

    agent_source = (ROOT / "app" / "agent" / "agent.py").read_text(encoding="utf-8")
    check("should_retrieve_persistent_memory(user_input, interaction)" in agent_source, "agent gates persistent-memory retrieval")
    check("should_retrieve_project_context(" in agent_source, "agent gates curated project context")
    check("should_retrieve_incident_context(" in agent_source, "agent gates incident history")
    check(
        agent_source.index("current_reasoning_guidance = reasoning_turn_guidance(user_input)")
        < agent_source.index("combined_system_guidance ="),
        "current-turn reasoning contract is assembled before the model request",
    )
    check(
        "current_personality_guidance = personality_turn_guidance(interaction)" in agent_source
        and agent_source.count("current_personality_guidance,") >= 3,
        "late personality reinforcement is included across conversational/operational prompt paths",
    )

    print("=" * 78)
    print("STEP 20.15.1.7 REASONING CONTEXT ISOLATION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
