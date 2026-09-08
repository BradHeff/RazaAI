import re


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"[a-z0-9_.:-]{3,}",
            _norm(text),
        )
    )


def _symptom_phrases(text: str) -> set[str]:
    phrases = {
        "authentication succeeds",
        "authentication succeeded",
        "nps authentication succeeds",
        "nps authentication succeeded",
        "cannot join",
        "can't join",
        "will not join",
        "won't join",
        "no internet",
        "no connectivity",
        "fails to connect",
        "failed to connect",
        "drops after auth",
        "obtaining ip",
        "no ip",
        "no dhcp",
        "wrong vlan",
        "vlan assignment",
        "vlan mapping",
        "certificate",
        "peap",
        "radius",
        "nps",
        "ssid",
        "dhcp",
    }

    haystack = _norm(text)

    return {
        phrase
        for phrase in phrases
        if phrase in haystack
    }


def _topic_compatible(query: str, text: str) -> bool:
    """Reject obvious same-vendor/different-subsystem retrieval collisions."""
    q = _norm(query)
    t = _norm(text)

    fortigate_named = "fortigate" in q or "fortios" in q
    strong_admin_terms = (
        "gui", "web gui", "web interface", "admin access", "administrative access",
        "admin-sport", "admin-port", "admin-server-cert", "fortinet_factory", "certificate", "allowaccess", "connection refused",
    )
    port_admin_query = (
        any(term in q for term in ("http", "https", "443", "80"))
        and any(term in q for term in ("port", "ports", "open", "listen", "listening", "access"))
    )
    if fortigate_named and (any(term in q for term in strong_admin_terms) or port_admin_query):
        evidence_admin_terms = strong_admin_terms + (
            "diagnose sys tcpsock", "diagnose sniffer packet", "management port",
            "administrative gui", "admin-server-cert", "fortinet_factory", "certificate", "httpsd", "http_authd",
        )
        return any(term in t for term in evidence_admin_terms)

    if fortigate_named and any(term in q for term in (
        "webfilter", "web filter", "fortiguard", "ftgd-local", "local category", "rating override"
    )):
        return any(term in t for term in (
            "webfilter", "web filter", "fortiguard", "ftgd-local", "local category", "rating override"
        ))

    if fortigate_named and any(term in q for term in (
        "ipsec", "ike", "phase 1", "phase 2", "vpn tunnel", "selectors"
    )):
        return any(term in t for term in (
            "ipsec", "ike", "phase 1", "phase 2", "vpn tunnel", "selectors"
        ))

    if fortigate_named and any(term in q for term in (
        "firewall policy", "policy not matching", "matched policy", "policy id", "policy_id"
    )):
        return any(term in t for term in (
            "firewall policy", "matched policy", "policy id", "policy_id", "debug flow", "session table"
        ))

    return True

def incident_similarity(query: str, item: dict) -> float:
    """Score how closely a retrieved knowledge chunk matches the observed incident."""

    text = item.get("text", "")
    base = float(
        item.get(
            "score",
            item.get("semantic_score", 0.0),
        )
    )

    q_tokens = _tokens(query)
    t_tokens = _tokens(text)

    token_overlap = (
        len(q_tokens & t_tokens)
        / max(1, len(q_tokens))
    )

    q_symptoms = _symptom_phrases(query)
    t_symptoms = _symptom_phrases(text)

    symptom_overlap = (
        len(q_symptoms & t_symptoms)
        / max(1, len(q_symptoms))
        if q_symptoms
        else 0.0
    )

    technical_terms = {
        token
        for token in q_tokens
        if (
            any(ch.isdigit() for ch in token)
            or "." in token
            or "-" in token
            or token in {
                "nps",
                "radius",
                "vlan",
                "ssid",
                "dhcp",
                "peap",
                "802.1x",
                "fsck",
                "fsck.ext4",
                "intune",
                "gpo",
                "ldaps",
                "lxd",
            }
        )
    }

    exact_technical = (
        len(technical_terms & t_tokens)
        / max(1, len(technical_terms))
        if technical_terms
        else 0.0
    )

    final_score = (
        0.52 * base
        + 0.18 * token_overlap
        + 0.20 * symptom_overlap
        + 0.10 * exact_technical
    )

    return round(final_score, 4)


def rank_incident_evidence(query: str, evidence: list[dict]) -> list[dict]:
    ranked = []

    for item in evidence:
        if not _topic_compatible(query, item.get("text", "")):
            continue
        updated = dict(item)
        updated["incident_score"] = incident_similarity(
            query,
            item,
        )
        ranked.append(updated)

    ranked.sort(
        key=lambda x: x["incident_score"],
        reverse=True,
    )

    for index, item in enumerate(ranked):
        item["evidence_rank"] = index + 1
        item["evidence_role"] = (
            "primary"
            if index == 0
            else "secondary"
        )

    return ranked
