import re

TECHNICAL_PATTERNS = [
    re.compile(r"\bVLAN\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b(?:0x)?[0-9A-F]{6,}\b", re.IGNORECASE),
    re.compile(r"\b\d{3,5}\b"),
    re.compile(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+\b"),
    re.compile(
        r"\b(?:fsck(?:\.ext4)?|systemctl|journalctl|nslookup|dig|ping|traceroute)\b",
        re.IGNORECASE,
    ),
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def technical_terms(query: str):
    terms = set()

    for pattern in TECHNICAL_PATTERNS:
        for match in pattern.findall(query):
            if isinstance(match, tuple):
                terms.update(item for item in match if item)
            else:
                terms.add(str(match))

    words = re.findall(r"[A-Za-z0-9_.:-]{3,}", query)

    stop = {
        "what",
        "when",
        "where",
        "which",
        "with",
        "from",
        "this",
        "that",
        "have",
        "does",
        "should",
        "could",
        "would",
        "about",
        "there",
        "their",
        "into",
        "your",
        "using",
        "used",
        "issue",
        "problem",
    }

    for word in words:
        if word.lower() not in stop:
            terms.add(word)

    return sorted(terms, key=len, reverse=True)


def lexical_score(query: str, text: str) -> float:
    """Simple exact-term score designed for ICT artefacts such as commands, error codes, product names, VLAN IDs and model numbers."""

    haystack = normalize(text)
    score = 0.0

    for term in technical_terms(query):
        needle = normalize(term)

        if needle and needle in haystack:
            if any(char.isdigit() for char in needle):
                score += 1.5
            elif "." in needle or "-" in needle or "_" in needle:
                score += 1.25
            else:
                score += 0.5

    return score


def rerank(query: str, results: list[dict], semantic_weight=0.82, lexical_weight=0.18):
    if not results:
        return []

    raw_lexical = [lexical_score(query, item.get("text", "")) for item in results]

    max_lexical = max(raw_lexical) or 1.0

    ranked = []

    for item, lex in zip(results, raw_lexical):
        semantic = float(item.get("semantic_score", item.get("score", 0.0)))
        lexical_norm = lex / max_lexical if lex else 0.0

        hybrid = semantic_weight * semantic + lexical_weight * lexical_norm

        citation = item.get("citation") or {}
        if citation.get("knowledge_type") == "validated_operational_pattern":
            status = citation.get("knowledge_status") or "active"
            try:
                confidence_score = float(citation.get("confidence_score", 0.8))
            except (TypeError, ValueError):
                confidence_score = 0.8

            confidence_score = max(0.0, min(1.0, confidence_score))
            factor = 0.75 + (0.25 * confidence_score)

            if status == "review":
                factor *= 0.55
            elif status == "stale":
                factor *= 0.75
            elif status == "watch":
                factor *= 0.85

            hybrid *= factor

        updated = dict(item)
        updated["lexical_score"] = round(lexical_norm, 4)
        updated["score"] = round(hybrid, 4)
        ranked.append(updated)

    return sorted(
        ranked,
        key=lambda item: item["score"],
        reverse=True,
    )
