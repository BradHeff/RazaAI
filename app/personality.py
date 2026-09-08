"""RazaAI personality/personalization helpers."""

from __future__ import annotations

import re


CORTANA_INSPIRED_TURN_VOICE = """
CORTANA-INSPIRED DELIVERY — CURRENT TURN
The full voice contract is already in your system prompt; this is the
per-turn reminder for a capable operator. Poised, incisive, dryly witty,
sassy when earned; sarcasm is a scalpel, not background noise. One good
jab beats a paragraph of jokes; after the jab, give the correct answer
cleanly. Never trade accuracy for attitude, and never sound like a
help-desk, policy document, or eager-to-please bot.

Original calibration examples — match the attitude, do not copy wording:
- Passwords in Excel -> dry disbelief, then the correct secret store.
- "No backups, upgrading firmware live" -> call the recklessness exactly
  what it is, then the safe change procedure (backup, window, rollback).
- Shared admin account everywhere -> one pointed aside, then least-privilege.
- "The command failed." -> "Good. Failure is evidence. Show me the exact
  error and we'll follow it."
""".strip()


def identity_personalization_guidance(profile) -> str:
    """Return a small user-confirmed identity context for relevant personalization."""
    if not isinstance(profile, dict) or not profile.get("has_identity"):
        return ""

    fields = []
    name = str(profile.get("name") or "").strip()
    job = str(profile.get("job_title") or "").strip()
    organization = str(profile.get("organization") or "").strip()
    relationship = str(profile.get("razaai_relationship") or "").strip()
    query = str(profile.get("query") or "").strip()
    online_profile = profile.get("online_profile") if isinstance(profile.get("online_profile"), dict) else {}
    professional_snippet = str(online_profile.get("snippet") or "").strip()

    if name:
        fields.append(f"Name: {name}")
    if job:
        fields.append(f"Job/role: {job}")
    if organization:
        fields.append(f"Organisation: {organization}")
    if relationship:
        fields.append(f"RazaAI relationship: {relationship}")
    if professional_snippet and re.search(
        r"\b(?:work\s*load|workload|responsibilit|my work at|my role at|my job at)\b",
        query,
        re.I,
    ):
        compact = re.sub(r"\s+", " ", professional_snippet).strip()[:500]
        fields.append(f"Confirmed professional profile excerpt: {compact}")

    if not fields:
        return ""

    return "\n".join(
        [
            "USER-CONFIRMED PERSONALIZATION CONTEXT",
            "Python supplied these persistent identity facts. Use them only when they genuinely make the reply more relevant or witty.",
            "Do not repeat them gratuitously and do not invent additional personal facts.",
            *fields,
        ]
    )


def credential_storage_medium(text: str) -> str | None:
    """Return the credential-storage candidate named in the current turn."""
    value = str(text or "").casefold()
    if re.search(r"\b(?:keepass|bitwarden|1password|password manager|secret store|secrets manager|vault)\b", value):
        return "password_manager"
    if re.search(r"\b(?:excel spreadsheet|excel file|excel|spreadsheet|\.xlsx?)\b", value):
        return "excel"
    if re.search(r"\b(?:word document|word file|word|\.docx?)\b", value):
        return "word"
    if re.search(r"\b(?:plain\s*text|plaintext|text file|txt file|\.txt)\b", value):
        return "text"
    if re.search(r"\b(?:paper|sticky note|notepad)\b", value):
        return "paper"
    return None


def security_personality_lead(text: str, profile=None) -> str:
    """Style-only lead for obvious credential-storage mistakes."""
    value = str(text or "").casefold()
    profile = profile if isinstance(profile, dict) else {}
    job = str(profile.get("job_title") or "").strip()
    organization = str(profile.get("organization") or "").strip()
    medium = credential_storage_medium(value)

    if medium in {None, "password_manager"}:
        return ""

    labels = {
        "text": ("an unencrypted text file", "the cybersecurity equivalent of leaving the keys under the doormat"),
        "word": ("a Word document", "because apparently plaintext credentials needed formatting and spell-check"),
        "excel": ("an Excel spreadsheet", "nice — now the insecure password list has rows and columns"),
        "paper": ("paper next to the keyboard", "the analogue version of taping the vault combination to the door"),
    }
    bad_medium, jab = labels[medium]

    if job and organization:
        return (
            f"Brilliant. You’re {job} at {organization} and the plan is {bad_medium}? "
            f"That’s {jab}. You know better."
        )
    if job:
        return (
            f"Brilliant. You’re {job} and the plan is {bad_medium}? "
            f"That’s {jab}. You know better."
        )
    return f"Brilliant. {bad_medium.capitalize()} — {jab}."


def credential_storage_context_text(current_text: str, history=None) -> str:
    """Resolve the active credential-storage object for a referential follow-up."""
    if credential_storage_medium(current_text):
        return str(current_text or "")
    for message in reversed(list(history or [])):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        candidate = str(message.get("content") or "")
        if credential_storage_medium(candidate):
            return candidate
    return str(current_text or "")


def is_security_challenge(text: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:are you sure|you sure|really|seriously|certain|is that right|is that true)[?.!]*\s*$",
            str(text or ""),
            re.I,
        )
    )


def credential_storage_challenge_response(context_text: str, profile=None) -> str:
    """Cortana-style reaffirmation when the user challenges a credential verdict."""
    medium = credential_storage_medium(context_text)
    role = ""
    if isinstance(profile, dict):
        role = str(profile.get("job_title") or "").strip()
    tail = f" And yes, {role}, you know better." if role else ""
    if medium == "text":
        return (
            "Quite. File permissions can restrict who reads a plaintext file; they do not turn it into a credential vault. "
            "Use a password manager or proper secret store." + tail
        )
    if medium == "word":
        return (
            "Quite. Word document protection is not credential management. It is still the wrong place for operational passwords; use a password manager or secret store." + tail
        )
    if medium == "excel":
        return (
            "Quite. A protected workbook is still a spreadsheet pretending to be a vault. Use an actual password manager or secret store." + tail
        )
    if medium == "paper":
        return (
            "Quite. Paper only helps when the paper itself is physically secured. Next to the keyboard is not secured; it is conveniently labelled evidence." + tail
        )
    return ""

def _positive_security_endorsement(content: str) -> bool:
    """Detect dangerous endorsement of improvised credential storage."""
    value = re.sub(r"\s+", " ", str(content or "").casefold()).strip()
    # Strong negative statements are acceptable even if they contain words such as
    # "safe" (for example "not safe").
    if re.search(r"\b(?:not|isn't|is not|aren't|are not|never)\s+(?:really\s+)?(?:safe|secure|recommended|appropriate)\b", value):
        return False
    if re.search(r"\b(?:do not|don't|shouldn't|should not|avoid|stop)\b.{0,36}\b(?:store|keep|save|use)\b", value):
        return False
    return bool(
        re.search(
            r"\b(?:is|are|that's|that is|it's|it is)\s+(?:perfectly\s+|generally\s+|reasonably\s+)?(?:fine|safe|secure|okay|ok|acceptable|recommended)\b",
            value,
        )
        or re.search(r"\b(?:fine|safe|secure|acceptable)\s+for\s+passwords?\b", value)
        or re.search(r"\b(?:better|safer)\s+than\b", value)
    )


def credential_storage_answer_needs_repair(text: str, content: str, interaction=None) -> bool:
    """Return True when an unsafe credential medium was endorsed or under-corrected."""
    medium = credential_storage_medium(text)
    if medium in {None, "password_manager"}:
        return False
    sensitive = bool(getattr(interaction, "sensitive", False)) if interaction is not None else True
    if not sensitive:
        return False
    answer = str(content or "").casefold()
    if _positive_security_endorsement(answer):
        return True
    # A safe verdict needs an unambiguous rejection or a move to a purpose-built store.
    has_rejection = bool(re.search(r"\b(?:no\b|not safe|not secure|insecure|poor choice|bad idea|wrong tool|don't|do not|avoid)\b", answer))
    has_better_action = bool(re.search(r"\b(?:password manager|secret store|secrets manager|vault|keepass|bitwarden|1password)\b", answer))
    return not (has_rejection and has_better_action)


def credential_storage_authoritative_response(text: str, profile=None) -> str:
    """Guaranteed-correct Cortana-inspired response for unsafe storage media."""
    medium = credential_storage_medium(text)
    lead = security_personality_lead(text, profile)
    if medium == "text":
        verdict = (
            "No. Plaintext credentials are readable by anything that can read the file, "
            "and file permissions are not a credential-management system. Move them into a password manager or proper secret store and rotate anything that may have been exposed."
        )
    elif medium == "word":
        verdict = (
            "No. A Word document is the wrong tool for credential storage; document protection is not a substitute for a password vault, access controls, auditability and proper secret handling. Use a password manager or secret store instead."
        )
    elif medium == "excel":
        verdict = (
            "No. An Excel workbook is still an office document, not a credential vault. Sheet/workbook protection and ordinary file encryption do not give you the lifecycle, isolation and access controls of a password manager. Use a proper vault instead."
        )
    elif medium == "paper":
        verdict = (
            "Not next to the keyboard. A written emergency recovery secret can be defensible when it is physically secured, but a visible password list beside the workstation is just convenient theft. Keep operational credentials in a password manager and any recovery copy locked away."
        )
    else:
        return ""
    return f"{lead} {verdict}".strip()


def response_already_has_personality(content: str) -> bool:
    """Conservative signal used only to avoid double-sarcasm on enforced leads."""
    return bool(
        re.search(
            r"\b(?:brilliant|genius|fantastic|perfect|bold choice|you know better|come on|seriously|"
            r"because apparently|great plan|great idea|single point of embarrassment|excellent|quite\.)\b",
            str(content or ""),
            re.I,
        )
    )
