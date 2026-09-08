""":  Cortana personality authority + credential truth guard."""

from pathlib import Path

from app.config import APP_VERSION, RAZAAI_VOICE_CONTRACT, version_tuple
from app.interaction.router import InteractionRouter
from app.personality import (
    CORTANA_INSPIRED_TURN_VOICE,
    credential_storage_answer_needs_repair,
    credential_storage_authoritative_response,
    credential_storage_challenge_response,
    credential_storage_context_text,
    credential_storage_medium,
    is_security_challenge,
    security_personality_lead,
)
from app.reasoning_context import personality_turn_guidance

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.8 Cortana Personality Authority")
    print("=" * 78)

    check(version_tuple(APP_VERSION) >= version_tuple("20.15.1.8"), "version gate is at least 20.15.1.8")

    voice = (RAZAAI_VOICE_CONTRACT + "\n" + CORTANA_INSPIRED_TURN_VOICE).casefold()
    check(all(x in voice for x in ("cortana", "sassy", "sarcastic", "help-desk", "capable operator")), "Cortana-inspired voice is an explicit application contract")
    check("original calibration examples" in voice, "late voice card includes original style calibration examples")

    router = InteractionRouter()
    word = router.classify("is a Word document safe for passwords?")
    check(word.sensitive and word.mode == "advice", "Word-password question enters sensitive advice rather than procedural-document mode")

    excel = router.classify("what about Excel?", previous=word)
    check(excel.sensitive and excel.mode == "advice", "Excel comparison inherits credential-security context")

    text = router.classify("im using text file for storing passwords")
    check(text.sensitive and text.mode == "advice", "plaintext-password statement is sensitive advice")

    sure = router.classify("are you sure?", previous=text)
    check(sure.sensitive and sure.mode == "advice", "challenge follow-up retains sensitive context")

    # Auth documentation must still remain procedural rather than secret-bearing.
    eap = router.classify("create a PDF explaining EAP username and password login")
    check(not eap.sensitive, "real EAP/login documentation remains procedural")

    check(credential_storage_medium("what about Excel?") == "excel", "current Excel object is identified")
    check(credential_storage_medium("I use a Word document") == "word", "current Word object is identified")
    check(credential_storage_medium("I use KeePass") == "password_manager", "proper password manager is distinguished")

    check(
        credential_storage_answer_needs_repair(
            "im using text file for storing passwords",
            "A text file is fine for passwords if the file itself is protected.",
            text,
        ),
        "dangerous plaintext endorsement is rejected",
    )
    check(
        credential_storage_answer_needs_repair(
            "what about Excel?",
            "Excel can expose passwords if the sheet is shared publicly.",
            excel,
        ),
        "under-corrected Excel answer is rejected",
    )
    check(
        not credential_storage_answer_needs_repair(
            "is a Word document safe for passwords?",
            "No. A Word document is not safe credential storage. Use a password manager instead.",
            word,
        ),
        "unambiguous safe technical answer passes the truth guard",
    )

    profile = {"has_identity": True, "job_title": "IT Manager", "organization": "Example School"}
    lead = security_personality_lead("im using text file for storing passwords", profile)
    check("IT Manager" in lead and "know better" in lead, "confirmed role can drive context-aware disappointment")
    guarded = credential_storage_authoritative_response("what about Excel?", profile)
    check("rows and columns" in guarded and "password manager" in guarded.casefold(), "authoritative Excel response keeps both sass and corrective action")
    check("No." in guarded, "authoritative response gives an unambiguous verdict")

    history = [
        {"role": "user", "content": "im using text file for storing passwords"},
        {"role": "assistant", "content": guarded},
        {"role": "user", "content": "are you sure?"},
    ]
    resolved = credential_storage_context_text("are you sure?", history)
    check(credential_storage_medium(resolved) == "text", "security challenge resolves the preceding credential-storage object")
    check(is_security_challenge("are you sure?"), "challenge follow-up is explicitly recognised")
    challenged = credential_storage_challenge_response(resolved, profile)
    check("Quite." in challenged and "password manager" in challenged, "challenge reply keeps Cortana-style confidence and the safe verdict")

    late = personality_turn_guidance(text).casefold()
    check("cortana-inspired delivery" in late and "dryly" in late and "security attitude" in late, "Cortana voice is reinforced at the end of turn guidance")

    agent_source = (ROOT / "app" / "agent" / "agent.py").read_text(encoding="utf-8")
    check('and not bool(getattr(interaction, "sensitive", False))' in agent_source, "sensitive drafts are buffered until validation")
    check("credential_storage_answer_needs_repair(" in agent_source, "agent validates unsafe credential-storage drafts")
    check("credential_storage_authoritative_response(" in agent_source, "agent has an authoritative personality-preserving fallback")

    print("=" * 78)
    print("STEP 20.15.1.8 CORTANA PERSONALITY AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
