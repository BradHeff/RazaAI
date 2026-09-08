"""Python-authoritative user identity/profile composition and confirmation."""

from __future__ import annotations

import re


def render_identity_profile(payload, query=""):
    """Render user-confirmed identity facts without delegating entity resolution to an LLM."""
    payload = payload if isinstance(payload, dict) else {}
    query = str(query or payload.get("query") or "").casefold()
    if not payload.get("has_identity"):
        return "I don't have a confirmed identity profile for you in persistent memory yet."

    name = str(payload.get("name") or "").strip() or None
    job = str(payload.get("job_title") or "").strip() or None
    organisation = str(payload.get("organization") or "").strip() or None
    relationship = str(payload.get("razaai_relationship") or "").strip() or None
    profile = payload.get("online_profile") if isinstance(payload.get("online_profile"), dict) else None

    if "online profile" in query:
        if not profile:
            return "I don't have a confirmed online profile for you in persistent memory yet."
        title = str(profile.get("title") or "").strip()
        url = str(profile.get("url") or "").strip()
        response = f"Your confirmed online profile is {title}." if title else "I have your confirmed online profile."
        if url:
            response += f" URL: {url}"
        return response

    if re.search(r"\b(?:job|what do i do|role)\b", query):
        if job and organisation:
            return f"You are {job} at {organisation}."
        if job:
            return f"Your confirmed job/role is {job}."
        if organisation:
            return f"Your confirmed organisation is {organisation}."
        return "I have your identity in memory, but no confirmed job title yet."

    named_third_person = bool(
        name and name.casefold() in query and re.search(r"\bwho is\b", query)
    )
    if named_third_person:
        parts = [f"{name} is you."]
        if job and organisation:
            parts.append(f"You are {job} at {organisation}.")
        elif job:
            parts.append(f"You are {job}.")
        if relationship and "creator" in relationship.casefold():
            parts.append("You are the creator of RazaAI.")
        return " ".join(parts)

    parts = []
    if name:
        parts.append(f"You are {name}.")
    if job and organisation:
        parts.append(f"You are {job} at {organisation}.")
    elif job:
        parts.append(f"Your confirmed job/role is {job}.")
    if relationship and "creator" in relationship.casefold():
        parts.append("You are the creator of RazaAI.")
    return " ".join(parts) or "I don't have a confirmed identity profile for you yet."


def confirm_identity_reference(
    manager,
    text,
    *,
    web_sources=None,
    web_query=None,
    previous_user="",
):
    """Resolve explicit 'remember' confirmations into durable identity records."""
    text = str(text or "").strip()
    lower = text.casefold()
    source_match = re.search(r"\b(S\d+)\b", text, re.I)
    confirms_self = bool(
        re.search(r"\b(?:is|that's|that is)\s+(?:me|mine|my\s+online\s+profile)\b", lower)
        or re.search(r"\bmy\s+online\s+profile\b", lower)
    )
    # Users confirm profiles in third person too ("Remember S3 result
    # as Brad Heffernan online profile", "S3 is Brad Heffernan online profile").
    # Still explicit confirmation: a session search label plus a profile claim,
    # and never a claim about somebody *else's* profile.
    third_person = bool(re.search(r"\b(?:his|her|their|someone else(?:'s)?|another person)'?s?\b", lower))
    negated = bool(re.search(r"\b(?:not|isn't|is not|isn't the|wrong|different person)\b", lower))
    profile_claim = bool(
        not third_person
        and not negated
        and re.search(r"\b(?:online|linkedin|web)\s+profile\b", lower)
        and re.search(r"\b(?:remember|is|that's|that is|confirm(?:ed)?)\b", lower)
    )
    if source_match and (confirms_self or profile_claim):
        source_id = source_match.group(1).upper()
        source = dict((web_sources or {}).get(source_id) or {})
        if not source:
            return (
                f"I can't safely persist {source_id} by itself because that source label "
                "belongs to a previous or unavailable search. Search again and confirm the result."
            )
        record = manager.remember_online_profile(
            title=source.get("title") or source_id,
            url=source.get("url"),
            snippet=source.get("snippet") or "",
            source_id=source_id,
            query=web_query,
            user_name=manager.user_name(),
        )
        title = record.provenance.get("title") or record.value
        url = record.provenance.get("url")
        response = f"Remembered: {title} is your confirmed online profile."
        if url:
            response += f" URL: {url}"
        return response

    referential = bool(
        re.search(r"\bremember\s+that\b", lower)
        and re.search(r"\b(?:verified|correct|yes|that's right|that is right)\b", lower)
    )
    if referential and previous_user:
        previous = str(previous_user)
        if (
            "linkedin" in previous.casefold()
            or re.search(r"\b(?:online profile|it manager|engineer)\b", previous, re.I)
        ):
            record = manager.remember_profile_text(previous)
            title = record.provenance.get("title") or record.value
            return f"Remembered and marked as user-verified: {title}."
    return None
