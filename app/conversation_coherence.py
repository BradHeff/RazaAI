"""Conversation coherence helpers for RazaAI ."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re


@dataclass(frozen=True)
class ConversationFocus:
    intent: str
    topic: str | None = None
    previous_intent: str | None = None
    previous_topic: str | None = None
    loop_feedback: bool = False
    referential: bool = False


_LOOP_RE = re.compile(
    r"\b(?:we(?:'re| are) looping|you(?:'re| are) looping|looping now|"
    r"you(?:'re| are) repeating|you repeated|you already said|"
    r"same answer|stop repeating|going in circles|we(?:'re| are) going in circles)\b",
    re.I,
)
# Accept the common one-m typo "recomend" as well as "recommend". Intent
# classification should be more tolerant than execution/path parsing.
_RECOMMEND_WORD = r"reco(?:m|mm)end"
_RECOMMEND_RE = re.compile(
    rf"\b(?:what\s+(?:do|would)\s+you\s+{_RECOMMEND_WORD}|what\s+should\s+i\s+use|"
    rf"which\s+(?:one|option)\s+should\s+i\s+use|{_RECOMMEND_WORD}(?:\s+me)?|suggest(?:\s+me)?)\b",
    re.I,
)
_LOCATE_RE = re.compile(
    r"\b(?:where\s+can\s+i\s+(?:get|find|download|buy|obtain|sign\s*up\s+for|access)|"
    r"where\s+do\s+i\s+(?:get|find|download|buy|obtain)|how\s+do\s+i\s+(?:get|obtain|access))\b",
    re.I,
)
_COMPARE_RE = re.compile(
    r"\b(?:compare|versus|\bvs\.?\b|difference between|better than|which is better)\b",
    re.I,
)
_OPINION_RE = re.compile(
    r"\b(?:what\s+are\s+your\s+thoughts\s+(?:on|about)|what\s+do\s+you\s+think\s+(?:of|about)|"
    r"your\s+opinion\s+(?:on|about))\b",
    re.I,
)
_EXPLAIN_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are)|how\s+(?:does|do|is|are)|explain|tell\s+me\s+about)\b",
    re.I,
)
_REFERENTIAL_RE = re.compile(r"\b(?:one|it|that|this|them|those|there)\b", re.I)

_STOPWORDS = {
    "what", "about", "your", "thoughts", "think", "opinion", "recommend", "recomend", "suggest",
    "where", "can", "get", "find", "download", "buy", "obtain", "access", "one", "the",
    "and", "for", "with", "from", "that", "this", "how", "does", "work", "should", "use",
    "are", "you", "do", "is", "of", "at", "my", "me", "a", "an", "to", "on", "in",
}

# Concrete signals used only as a conservative coherence check. This is not a
# product allowlist; it simply lets a recommendation like "Use Azure Key Vault"
# count as addressing a referential "which secret store?" turn even when the
# answer does not repeat the category words "secret store".
_CONCRETE_OPTION_RE = re.compile(
    r"\b(?:azure key vault|hashicorp vault|aws secrets manager|amazon secrets manager|"
    r"gcp secret manager|google secret manager|bitwarden secrets manager|bitwarden|"
    r"keepass|1password|vaultwarden|cyberark|doppler|infisical)\b",
    re.I,
)


def _clean_topic(value: str) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n?!.\"'")
    text = re.sub(r"^(?:a|an|the)\s+", "", text, flags=re.I)
    if not text or text.casefold() in {"one", "it", "that", "this", "them", "those"}:
        return None
    return text[:180]


def classify_followup_intent(text: str) -> str:
    value = str(text or "").strip()
    if _LOOP_RE.search(value):
        return "loop_feedback"
    if _LOCATE_RE.search(value):
        return "locate"
    if _RECOMMEND_RE.search(value):
        return "recommend"
    if _COMPARE_RE.search(value):
        return "compare"
    if _OPINION_RE.search(value):
        return "opinion"
    if _EXPLAIN_RE.search(value):
        return "explain"
    return "respond"


def _explicit_topic(text: str, intent: str) -> str | None:
    value = str(text or "").strip()
    patterns: list[str] = []
    if intent == "recommend":
        patterns = [
            rf"what\s+(?:do|would)\s+you\s+{_RECOMMEND_WORD}\s+(?:for|as)\s+(.+)$",
            r"what\s+should\s+i\s+use\s+(?:for|as)\s+(.+)$",
            rf"{_RECOMMEND_WORD}(?:\s+me)?\s+(?:a|an|the)?\s*(.+)$",
            r"suggest(?:\s+me)?\s+(?:a|an|the)?\s*(.+)$",
        ]
    elif intent == "locate":
        patterns = [
            r"where\s+can\s+i\s+(?:get|find|download|buy|obtain|sign\s*up\s+for|access)\s+(.+)$",
            r"where\s+do\s+i\s+(?:get|find|download|buy|obtain)\s+(.+)$",
            r"how\s+do\s+i\s+(?:get|obtain|access)\s+(.+)$",
        ]
    elif intent == "opinion":
        patterns = [
            r"what\s+are\s+your\s+thoughts\s+(?:on|about)\s+(.+)$",
            r"what\s+do\s+you\s+think\s+(?:of|about)\s+(.+)$",
            r"your\s+opinion\s+(?:on|about)\s+(.+)$",
        ]
    elif intent == "explain":
        patterns = [
            r"what\s+(?:is|are)\s+(.+)$",
            r"how\s+(?:does|do)\s+(.+?)\s+work$",
            r"tell\s+me\s+about\s+(.+)$",
            r"explain\s+(.+)$",
        ]
    elif intent == "compare":
        patterns = [r"compare\s+(.+)$", r"difference\s+between\s+(.+)$"]

    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            return _clean_topic(match.group(1))

    # Short comparison/follow-up: "what about Excel?". This is deliberately
    # available even when the broad intent classifier returns "respond".
    match = re.match(r"^\s*(?:and\s+)?(?:what|how)\s+about\s+(.+?)[?!.]*\s*$", value, re.I)
    if match:
        return _clean_topic(match.group(1))
    return None


def _last_user_messages(history, limit: int = 6):
    result = []
    for item in reversed(list(history or [])):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            result.append(content)
        if len(result) >= limit:
            break
    return result


_BARE_PRONOUN_RE = re.compile(
    r"^(?:that|it|this|these|those|them|so)[.!]?$",
    re.I,
)


def resolve_referent_text(text: str, history=None, limit: int = 500) -> str | None:
    """Resolve a bare-pronoun memory object to the prior statement."""
    if not _BARE_PRONOUN_RE.match(str(text or "").strip()):
        return None
    messages = list(history or [])
    for role in ("assistant", "user"):
        for message in reversed(messages):
            if str(message.get("role") or "") != role:
                continue
            value = re.sub(r"\s+", " ", str(message.get("content") or "")).strip()
            # Skip non-substantive acks ("Thanks.", "Anytime.", closings).
            if value and len(value) >= 12 and value.casefold() not in {
                "anytime.", "thanks.", "perfect.", "hi.", "ok.",
            }:
                return value[:limit]
    return None


def resolve_conversation_topic(text: str, history=None, intent: str | None = None) -> tuple[str | None, bool]:
    intent = intent or classify_followup_intent(text)
    topic = _explicit_topic(text, intent)
    if topic:
        return topic, False

    referential = bool(_REFERENTIAL_RE.search(str(text or "")))
    if not referential and intent != "loop_feedback":
        return None, False

    # Resolve a short referential follow-up from the most recent user topic.
    for previous in _last_user_messages(history):
        previous_intent = classify_followup_intent(previous)
        prior_topic = _explicit_topic(previous, previous_intent)
        if prior_topic:
            return prior_topic, True

        # Conservative named-subject fallback for otherwise free-form turns.
        named = re.findall(
            r"\b(?:secret store|secrets manager|password manager|bitwarden|keepass|1password|"
            r"azure key vault|hashicorp vault|aws secrets manager|gcp secret manager|excel|"
            r"word document|text file|work\s*load(?: at the school)?|workload(?: at the school)?|"
            r"bgp|ospf|fortigate|aruba)\b",
            previous,
            re.I,
        )
        if named:
            return _clean_topic(named[-1]), True
    return None, referential


def analyze_conversation_turn(text: str, history=None) -> ConversationFocus:
    intent = classify_followup_intent(text)
    topic, referential = resolve_conversation_topic(text, history, intent)
    previous_intent = None
    previous_topic = None
    prior_users = _last_user_messages(history, limit=1)
    if prior_users:
        previous_intent = classify_followup_intent(prior_users[0])
        previous_topic, _ = resolve_conversation_topic(prior_users[0], None, previous_intent)
    return ConversationFocus(
        intent=intent,
        topic=topic,
        previous_intent=previous_intent,
        previous_topic=previous_topic,
        loop_feedback=(intent == "loop_feedback"),
        referential=referential,
    )


def coherence_requires_buffering(focus: ConversationFocus) -> bool:
    """Return True when Python must validate the draft before it is displayed."""
    if focus.loop_feedback:
        return True
    if focus.intent in {"recommend", "locate", "compare", "opinion"}:
        return True
    # Intent transitions are where the 4B model most often recycles an earlier
    # answer. Buffer them so a rejected draft never flashes in the TUI.
    return bool(focus.previous_intent and focus.previous_intent != focus.intent)


def conversation_coherence_guidance(text: str, history=None) -> str:
    focus = analyze_conversation_turn(text, history)
    lines = [
        "CURRENT TURN CONVERSATION COHERENCE",
        f"Current intent: {focus.intent}",
        "Answer the current intent first. Previous replies are context, never a template to repeat.",
        "A joke or callback may decorate the answer, but it may never replace the substantive answer.",
        "If the subject changed, reset to the new subject before making any callback to an older topic.",
    ]
    if focus.topic:
        lines.append(f"Current topic: {focus.topic}")
    if focus.previous_intent and focus.previous_intent != focus.intent:
        lines.append(
            f"Intent transition: {focus.previous_intent} -> {focus.intent}. The answer must visibly change with that transition."
        )
    if focus.previous_topic and focus.topic and focus.previous_topic.casefold() != focus.topic.casefold():
        lines.append(
            f"Previous topic: {focus.previous_topic}. Current topic: {focus.topic}. Do not let the previous topic replace the current answer; any callback belongs after a complete substantive answer."
        )

    if focus.intent == "recommend":
        lines += [
            "The user asked for a recommendation. Give concrete named option(s), choose a sensible default when possible, and briefly explain why.",
            "Do not merely define the category again.",
        ]
    elif focus.intent == "locate":
        lines += [
            "The user asked where/how to obtain or access it. Give concrete acquisition/access paths or provider/product names.",
            "Do not repeat the definition instead of answering where to get it.",
        ]
    elif focus.intent == "compare":
        lines.append("Compare the current candidates directly and state the practical trade-off or preferred fit.")
    elif focus.intent == "opinion":
        lines += [
            "The user asked for an assessment. Give an actual opinion/assessment of the current topic before any joke or callback.",
            "For a user-specific topic, use only confirmed context supplied by Python and clearly distinguish what is known from what is inferred.",
        ]
    elif focus.intent == "loop_feedback":
        lines += [
            "The user says the conversation is looping. Acknowledge it once, do not restate the same distinction, and move the conversation forward.",
            "Use the last unresolved user intent/topic and answer it concretely in a different way.",
        ]
        if focus.previous_intent in {"recommend", "locate", "compare", "opinion", "explain"}:
            lines.append(f"The last user intent before the loop complaint was: {focus.previous_intent}.")
    elif focus.intent == "explain":
        lines.append("Explain the current topic directly. Recommendations are secondary unless the user asks for them.")

    # Correct a recurring factual confusion without turning every answer into a
    # product lecture. Human password management and application secret
    # management overlap, but they are not the same use case.
    if focus.topic and re.search(r"\b(?:secret store|secrets manager|password manager|bitwarden)\b", focus.topic, re.I):
        lines += [
            "Credential-management distinction: a password manager such as Bitwarden is a legitimate choice for human/user credentials.",
            "For application/service secrets and runtime injection, recommend a purpose-built secrets manager such as Bitwarden Secrets Manager, Azure Key Vault, HashiCorp Vault, AWS Secrets Manager or the equivalent appropriate to the environment.",
            "Do not tell the user to keep the password manager and secret store on the same machine as a security requirement; that is not a general best practice.",
        ]

    return "\n".join(lines)


def _normalise_for_similarity(text: str) -> str:
    words = re.findall(r"[a-z0-9+#.-]+", str(text or "").casefold())
    return " ".join(words)


def _similarity(a: str, b: str) -> float:
    na = _normalise_for_similarity(a)
    nb = _normalise_for_similarity(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    sa, sb = set(na.split()), set(nb.split())
    jac = len(sa & sb) / max(1, len(sa | sb))
    return max(seq, jac)


def _recent_assistant_answers(history, limit: int = 4):
    answers = []
    for item in reversed(list(history or [])):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            answers.append(content)
        if len(answers) >= limit:
            break
    return answers


def _topic_terms(topic: str | None):
    if not topic:
        return []
    return [
        token for token in re.findall(r"[a-z0-9+#.-]+", topic.casefold())
        if len(token) >= 3 and token not in _STOPWORDS
    ]


def _recommendation_signal(answer: str) -> bool:
    return bool(
        _CONCRETE_OPTION_RE.search(answer)
        or re.search(
            rf"\b(?:i(?:'d| would)\s+(?:use|choose|pick|go with)|{_RECOMMEND_WORD}\s+|"
            r"my pick is|best fit is|best option is|go with\s+)\b",
            answer,
            re.I,
        )
    )


def _access_signal(answer: str) -> bool:
    # A product-name list is not enough for "where can I get one?". Require an
    # actual acquisition/access cue so the turn materially progresses.
    return bool(
        re.search(
            r"\b(?:official (?:site|website)|(?:site|website|portal|marketplace|github|repository)|"
            r"download|install|sign up|self-host|package|"
            r"available\s+(?:from|through|via|in|at)|get (?:it|one) from|access (?:it|one) (?:through|via|in))\b",
            answer,
            re.I,
        )
    )


def _opinion_addresses_topic(answer: str, topic: str | None, previous_topic: str | None = None) -> bool:
    lower = str(answer or "").casefold()
    terms = _topic_terms(topic)

    if topic and re.search(r"\bwork\s*load|\bworkload|\bwork at|\bresponsibilit", topic, re.I):
        # Merely saying the word "workload" is not an assessment.
        # The opening substantive sentence must actually judge the user's load;
        # stale callbacks (Excel/secret-store/etc.) are allowed only afterwards.
        first = re.split(r"(?<=[.!?])\s+", str(answer or "").strip(), maxsplit=1)[0].casefold()
        subject_signal = bool(re.search(
            r"\b(?:your workload|workload|responsibilit|covering|role|school|it manager|engineer|one person|capacity)\b",
            first,
        ))
        judgement_signal = bool(re.search(
            r"\b(?:heavy|too much|high|broad|large|substantial|significant|demanding|overloaded|"
            r"unsustainable|unreasonable|stretched|spread thin|wearing too many hats|multiple roles|"
            r"one person|capacity|burnout|delegat|ridiculous|a lot|too many)\b",
            first,
        ))
        if not (subject_signal and judgement_signal):
            return False

        # If the first sentence is still anchored on the prior topic, it has not
        # actually reset to the user's current workload question.
        prior_terms = _topic_terms(previous_topic)
        if prior_terms and any(term in first for term in prior_terms):
            return False
        return True

    if any(term in lower for term in terms):
        return True
    return not terms


def validate_conversation_response(text: str, content: str, history=None) -> tuple[bool, str, ConversationFocus]:
    """Conservatively reject stale/looping drafts for conversation/advice turns."""
    focus = analyze_conversation_turn(text, history)
    answer = str(content or "").strip()
    lower = answer.casefold()
    if not answer:
        return False, "empty response", focus

    terms = _topic_terms(focus.topic)
    if focus.intent in {"explain", "compare"} and terms:
        if not any(term in lower for term in terms):
            return False, f"response does not address current topic '{focus.topic}'", focus
    if focus.intent == "opinion" and not _opinion_addresses_topic(answer, focus.topic, focus.previous_topic):
        return False, f"opinion does not assess current topic '{focus.topic}' before callbacks", focus

    # Detect a repeated answer when the user changed intent or explicitly called out a loop.
    recent = _recent_assistant_answers(history)
    if recent:
        threshold = 0.75 if focus.loop_feedback else 0.72
        if focus.loop_feedback or (focus.previous_intent and focus.previous_intent != focus.intent):
            if max(_similarity(answer, old) for old in recent) >= threshold:
                return False, "response repeats a recent answer despite a new/loop-breaking intent", focus

    if focus.intent == "recommend" and not _recommendation_signal(answer):
        return False, "recommendation request was answered without a concrete recommendation", focus

    if focus.intent == "locate" and not _access_signal(answer):
        return False, "location/access request was answered without telling the user where/how to get it", focus

    # A loop complaint must actually change course. The similarity gate catches
    # verbatim/semantic repeats; these intent checks catch a polite apology that
    # still fails to progress the prior request.
    if focus.loop_feedback and focus.previous_intent == "recommend" and not _recommendation_signal(answer):
        return False, "loop-breaking reply did not progress the pending recommendation", focus
    if focus.loop_feedback and focus.previous_intent == "locate" and not _access_signal(answer):
        return False, "loop-breaking reply did not progress the pending access/location request", focus

    return True, "ok", focus


def coherence_repair_guidance(focus: ConversationFocus, reason: str) -> str:
    lines = [
        "CONVERSATION COHERENCE CORRECTION",
        f"Your draft was rejected because: {reason}.",
        f"Current intent: {focus.intent}",
        "Re-answer the current user message from scratch. Do not reuse the rejected wording.",
        "Answer the user's substantive request first; personality/callbacks come after the answer, not instead of it.",
        "Keep RazaAI's Cortana-inspired composure, dry wit and blunt confidence. Do not fall back to generic help-desk prose.",
    ]
    if focus.topic:
        lines.append(f"Current topic: {focus.topic}")
    if focus.intent == "recommend":
        lines.append("Name concrete options and make a recommendation; do not redefine the category.")
    elif focus.intent == "locate":
        lines.append("Tell the user where/how to obtain or access it, with concrete provider/product paths.")
    elif focus.intent == "opinion":
        lines.append("Give an actual assessment of the current topic and do not fall back to a stale prior joke/topic.")
    elif focus.intent == "loop_feedback":
        lines.append("Acknowledge the loop once and move the unresolved request forward in a new, concrete way.")
        if focus.previous_intent == "recommend":
            lines.append("Make the pending recommendation now with concrete options.")
        elif focus.previous_intent == "locate":
            lines.append("Give the concrete access/provider path now instead of repeating definitions.")
    return "\n".join(lines)


_SELF_NAME_RE = re.compile(
    r"^\s*(?:who|what)\s+are\s+you[?.!]*\s*$|^\s*what(?:'s| is)\s+your\s+name[?.!]*\s*$|^\s*identify\s+yourself[?.!]*\s*$",
    re.I,
)
_SELF_CREATOR_RE = re.compile(
    r"\b(?:who\s+(?:created|made|built|developed)\s+you|who\s+is\s+your\s+creator|"
    r"(?:made|created|built|developed)\s+by\s+(?:who|whom|whome)|who\s+made\s+razaai)\b",
    re.I,
)
_SELF_MODEL_RE = re.compile(
    r"\b(?:what|which)\s+(?:underlying\s+)?model\s+(?:are\s+you|do\s+you\s+use|powers?\s+you)|"
    r"\bwhat\s+model\s+is\s+razaai\b",
    re.I,
)
_SELF_RUNTIME_RE = re.compile(
    r"\b(?:what\s+runtime\s+do\s+you\s+use|what\s+do\s+you\s+run\s+on|which\s+runtime\s+are\s+you\s+using)\b",
    re.I,
)
_VIGILGLM_RE = re.compile(
    r"\bvigil\s*glm(?:\.ai)?\b|"
    r"\b(?:are\s+you|who\s+is|who's|what(?:'s|\s+is))\s+sierra\b|"
    r"\bsierra\b.{0,30}\b(?:assistant|model|vigil|glm|cloud|ai)\b",
    re.I,
)
_OTHER_PRODUCTS_RE = re.compile(
    r"\bbrad(?:\s+heffernan)?\b.{0,40}\b(?:other|another|any\s+other)\s+"
    r"(?:ai\s+)?(?:platform|project|product|assistant|app)s?\b|"
    r"\b(?:other|another|any\s+other)\s+(?:ai\s+)?"
    r"(?:platform|project|product|assistant|app)s?\b.{0,40}\bbrad(?:\s+heffernan)?\b",
    re.I,
)
_SHORT_CREATOR_FOLLOWUP_RE = re.compile(
    r"^\s*(?:made|created|built|developed)\s+by\s+(?:who|whom|whome)[?.!]*\s*$|"
    r"^\s*by\s+(?:who|whom|whome)[?.!]*\s*$",
    re.I,
)


def self_identity_authoritative_response(
    text: str,
    *,
    identity_context_active: bool,
    user_name: str | None = None,
) -> str | None:
    """Return Python-owned RazaAI identity facts before the LLM can improvise."""
    from .config import IDENTITY_FACTS

    value = re.sub(r"\s+", " ", str(text or "")).strip()
    lower = value.casefold()

    if _SELF_NAME_RE.search(value):
        return "RazaAI. Try to keep up."

    if _SELF_CREATOR_RE.search(value) or (
        identity_context_active and _SHORT_CREATOR_FOLLOWUP_RE.search(value)
    ):
        creator = str(IDENTITY_FACTS.get("creator") or "Brad Heffernan")
        if user_name and str(user_name).strip().casefold() in {"brad", "brad heffernan"}:
            return f"{creator}. You, in other words."
        return f"{creator}."

    if _SELF_MODEL_RE.search(value):
        model = str(IDENTITY_FACTS.get("model") or "").strip()
        runtime = str(IDENTITY_FACTS.get("runtime") or "").strip()
        return f"I’m RazaAI. Underneath, my conversation model is {model}, running through {runtime}."

    if _SELF_RUNTIME_RE.search(value):
        runtime = str(IDENTITY_FACTS.get("runtime") or "Ollama")
        return f"{runtime}. That’s the runtime; I’m still RazaAI."

    # VigilGLM is a confirmed Python-authority fact. Left to the
    # model, evidence discipline makes it deny Brad's own cloud platform.
    if _VIGILGLM_RE.search(value) or _OTHER_PRODUCTS_RE.search(value):
        from .config import PRODUCT_FACTS

        vigil = PRODUCT_FACTS.get("vigilglm") or {}
        if vigil:
            return (
                f"{vigil['name']} ({vigil['url']}) — {vigil['summary']}. "
                f"Its assistant is {vigil['assistant']} on {vigil['model']}; "
                "I'm the local one. Pricing lives on the site."
            )

    timeline = self_identity_timeline_response(
        value,
        identity_context_active=identity_context_active,
    )
    if timeline is not None:
        return timeline

    return None

def self_identity_timeline_response(text: str, *, identity_context_active: bool) -> str | None:
    """Python-owned answer for ambiguous RazaAI origin-date questions."""
    value = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    short_when = value in {"when", "when?", "when was that", "when was that?"}
    has_when = bool(re.search(r"\bwhen\b", value))
    names_razaai = bool(re.search(r"\b(?:razaai|you|your)\b", value))
    creation_verb = bool(re.search(r"\b(?:created|made|built|started|began|begin|born|developed|development)\b", value))
    explicit_origin_when = has_when and names_razaai and creation_verb
    if not ((identity_context_active and short_when) or explicit_origin_when):
        return None
    return (
        "The original RazaAI began in 2019 — a simple movie-scripts-and-keyword chatbot built for funny responses. "
        "Serious development resumed in 2024 as modern AI tooling and proper LLMs became widely available. "
        "So 2024 is the modern chapter, not the beginning."
    )
