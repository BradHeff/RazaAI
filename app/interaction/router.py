from __future__ import annotations

from dataclasses import dataclass, asdict
import re


@dataclass(frozen=True)
class InteractionContext:
    mode: str
    domain: str | None
    action_requested: bool
    sensitive: bool
    sensitive_kind: str | None
    troubleshooting: bool
    allow_tools: bool
    reason: str
    explicit_file: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class InteractionRouter:
    """Small deterministic interaction-mode classifier."""

    FILE_RE = re.compile(
        r"(?<![\w./-])([\w./-]+\.(?:py|md|jsonl?|ya?ml|txt|toml|ini|cfg|csv))(?![\w.-])",
        re.I,
    )

    SENSITIVE_PATTERNS = {
        "credentials": (
            r"\bpasswords?\b",
            r"\bpassphrases?\b",
            r"\bcredentials?\b",
            r"\bapi[ _-]?keys?\b",
            r"\baccess[ _-]?tokens?\b",
            r"\brefresh[ _-]?tokens?\b",
            r"\bprivate[ _-]?keys?\b",
            r"\bssh[ _-]?keys?\b",
            r"\brecovery[ _-]?codes?\b",
            r"\bsecrets?\b",
        ),
    }

    ADVICE_MARKERS = (
        "discuss",
        "talk about",
        "what do you think",
        "what would you recommend",
        "recommend",
        "should i",
        "should we",
        "is it safe",
        "is this safe",
        "good idea",
        "bad idea",
        "why",
        "explain",
        "what if",
        "how would i",
        "how would we",
        "how do i",
        "how do we",
        "how can i",
        "how can we",
        "how should i",
        "how should we",
    )

    ACTION_WORDS = {
        "run",
        "check",
        "inspect",
        "find",
        "locate",
        "search",
        "show",
        "read",
        "open",
        "view",
        "list",
        "create",
        "generate",
        "test",
        "diagnose",
        "troubleshoot",
        "apply",
        "change",
        "update",
        "delete",
        "remove",
        "write",
        "edit",
        "modify",
        "fix",
        "repair",
        "improve",
        "retrain",
        "train",
        "promote",
        "ping",
        "query",
    }

    FAILURE_PATTERNS = (
        r"\boffline\b",
        r"\bdown\b",
        r"\bnot working\b",
        r"\bwon't connect\b",
        r"\bcannot connect\b",
        r"\bcan't connect\b",
        r"\bfail(?:ed|ing|ure)?\b",
        r"\berror\b",
        r"\bproblem\b",
        r"\bissue\b",
        r"\bno connectivity\b",
        r"\bno internet\b",
        r"\blost access\b",
        r"\b(?:cannot|can't|unable to) access\b",
        r"\b(?:does not|doesn't|won't|will not) load\b",
        r"\bconnection refused\b",
        r"\brefused\b",
        r"\btimed? out\b",
    )

    CAPABILITY_PATTERNS = (
        r"\bwhat (?:can|capabilities)\b",
        r"\bwhat capabilities\b",
        r"\bcan you (?:do|access|see files|inspect files)\b",
        r"\bwhat are you able to\b",
    )

    @staticmethod
    def _normalise(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    @classmethod
    def _credential_reference_is_procedural(cls, text: str) -> bool:
        """Return True when credentials are mentioned only as login instructions."""
        value = cls._normalise(text)

        credential_words = bool(
            re.search(
                r"\b(?:passwords?|passphrases?|credentials?|"
                r"api[ _-]?keys?|access[ _-]?tokens?|refresh[ _-]?tokens?|"
                r"private[ _-]?keys?|ssh[ _-]?keys?|recovery[ _-]?codes?|"
                r"secrets?)\b",
                value,
                re.I,
            )
        )
        if not credential_words:
            return False

        # Only ordinary authentication/password terminology gets the procedural
        # exception. API keys, tokens, private keys, recovery codes and generic
        # secrets always remain sensitive.
        if re.search(
            r"\b(?:api[ _-]?keys?|access[ _-]?tokens?|refresh[ _-]?tokens?|"
            r"private[ _-]?keys?|ssh[ _-]?keys?|recovery[ _-]?codes?|secrets?)\b",
            value,
            re.I,
        ):
            return False

        # Merely mentioning a Word/PDF document is not an authentication
        # procedure. accidentally let "is a Word document safe for
        # passwords?" escape the sensitive-security route because "document"
        # alone satisfied this check. Require actual login/authentication context.
        authentication_context = bool(
            re.search(
                r"\b(?:connect(?:ing)?|sign[ -]?in|log[ -]?in|login|"
                r"authentication|authenticate|eap|802\.?1x|wifi|wi-fi|ssid)\b",
                value,
                re.I,
            )
        )
        if not authentication_context:
            return False

        # Requests to retrieve, expose or transform actual secret material
        # remain sensitive even if "document" or "instructions" also appears.
        secret_action = bool(
            re.search(
                r"\b(?:show|reveal|display|print|dump|read|open|view|list|"
                r"retrieve|extract|decrypt|decode|recover|copy|expose)\b"
                r".{0,48}\b(?:passwords?|passphrases?|credentials?)\b",
                value,
                re.I,
            )
            or re.search(
                r"\b(?:passwords?|passphrases?|credentials?)\b"
                r".{0,48}\b(?:show|reveal|display|print|dump|read|open|view|"
                r"list|retrieve|extract|decrypt|decode|recover|copy|expose)\b",
                value,
                re.I,
            )
        )
        if secret_action:
            return False

        # Referencing a likely secret-bearing file is not merely procedural.
        if re.search(
            r"\b(?:passwords?|credentials?|secrets?)\b.{0,32}"
            r"\b(?:file|txt|csv|json|env|vault)\b",
            value,
            re.I,
        ):
            return False

        # Detect supplied/assigned real credential values.  Generic descriptions
        # such as "the password staff use to login" do not match these forms.
        supplied_secret = bool(
            re.search(
                r"\b(?:password|passphrase|credential)\s*(?:is|=|:)\s*"
                r"(?!(?:the|their|your|a|an)\b)\S+",
                value,
                re.I,
            )
            or re.search(
                r"\b(?:include|put|write|add)\b.{0,32}"
                r"\b(?:password|passphrase|credential)\b.{0,12}"
                r"(?:is|=|:)\s*\S+",
                value,
                re.I,
            )
        )
        if supplied_secret:
            return False

        return True

    @classmethod
    def _sensitive_kind(cls, text: str) -> str | None:
        # Credential terminology used only to explain an authentication process
        # is not itself secret material. This allows safe documentation such as
        # "enter your normal username and password" while keeping actual
        # credential retrieval/disclosure behind the sensitive boundary.
        if cls._credential_reference_is_procedural(text):
            return None

        for kind, patterns in cls.SENSITIVE_PATTERNS.items():
            if any(re.search(pattern, text, re.I) for pattern in patterns):
                return kind
        return None

    @classmethod
    def _explicit_file(cls, text: str) -> str | None:
        match = cls.FILE_RE.search(text or "")
        return match.group(1) if match else None

    @staticmethod
    def _short_followup(text: str) -> bool:
        words = re.findall(r"[A-Za-z0-9']+", text)
        return 0 < len(words) <= 7

    @staticmethod
    def _sensitive_topic_followup(text: str) -> bool:
        """Recognise referential credential-storage follow-ups beyond the short-turn limit."""
        value = str(text or "").casefold()
        if re.search(r"\b(?:what|how) about\b", value):
            return True
        return bool(
            re.search(r"\b(?:them|those|it|that)\b", value)
            and re.search(
                r"\b(?:save|store|keep|write|put|paper|sticky note|notepad|"
                r"word|document|excel|spreadsheet|file|keepass|password manager|vault)\b",
                value,
            )
        )

    @classmethod
    def _action_requested(cls, text: str) -> bool:
        words = set(re.findall(r"[a-zA-Z]+", text.lower()))
        if words & cls.ACTION_WORDS:
            return True

        # Polite/request forms that still clearly ask for an operation.
        if re.search(
            r"\b(?:can|could|would|will) you\s+"
            r"(?:run|check|inspect|find|locate|search|show|read|open|view|list|"
            r"create|generate|test|diagnose|apply|change|update|delete|write|edit|"
            r"modify|fix|repair|improve|retrain|train|promote|ping)\b",
            text,
            re.I,
        ):
            return True
        return False

    @classmethod
    def _is_capability_question(cls, text: str) -> bool:
        return any(re.search(pattern, text, re.I) for pattern in cls.CAPABILITY_PATTERNS)

    @classmethod
    def _is_advice(cls, text: str) -> bool:
        lower = text.lower()
        return any(marker in lower for marker in cls.ADVICE_MARKERS)

    @classmethod
    def _is_troubleshooting(cls, text: str) -> bool:
        return any(re.search(pattern, text, re.I) for pattern in cls.FAILURE_PATTERNS)

    def classify(
        self,
        text: str,
        *,
        expert_route=None,
        previous: InteractionContext | None = None,
    ) -> InteractionContext:
        normal = self._normalise(text)
        explicit_file = self._explicit_file(text)
        sensitive_kind = self._sensitive_kind(normal)

        # A short follow-up can inherit a sensitive/topic context so "show it"
        # after a credential discussion does not lose the security boundary.
        if (
            sensitive_kind is None
            and previous is not None
            and previous.sensitive
            and (
                self._short_followup(normal)
                or self._sensitive_topic_followup(normal)
            )
        ):
            sensitive_kind = previous.sensitive_kind

        sensitive = sensitive_kind is not None
        capability = self._is_capability_question(normal)
        advice = self._is_advice(normal)
        action = self._action_requested(normal)
        troubleshooting = self._is_troubleshooting(normal)

        domain = getattr(expert_route, "category", None)
        if sensitive:
            domain = "cybersecurity"
        elif (
            domain is None
            and previous is not None
            and self._short_followup(normal)
            and previous.domain is not None
        ):
            domain = previous.domain

        # Discussion/advice semantics override incidental technical/action words.
        if advice and not re.match(
            r"^(?:run|check|inspect|find|locate|search|show|read|open|view|list|"
            r"create|generate|test|diagnose|apply|change|update|delete|remove|"
            r"write|edit|modify|fix|repair|ping)\b",
            normal,
        ):
            action = False

        # "Can you see <specific file>?" is an existence lookup, not a request
        # to expose its contents. EdgeIntentRouter can satisfy this safely.
        if explicit_file and re.search(
            r"\b(?:can you see|do you see|does .* exist|can you find|locate)\b",
            normal,
            re.I,
        ):
            action = True

        if sensitive and action:
            mode = "sensitive_action"
            allow_tools = False
            reason = (
                "Sensitive credential/secret subject combined with an action request; "
                "do not expose or retrieve secret contents."
            )
        elif troubleshooting:
            mode = "troubleshooting"
            allow_tools = True
            reason = "Current turn describes an active technical fault."
        elif advice or sensitive:
            mode = "advice"
            allow_tools = False
            reason = (
                "Current turn asks for discussion/advice rather than an operation."
            )
        elif action and not capability:
            mode = "action"
            allow_tools = True
            reason = "Current turn explicitly requests an operation."
        else:
            mode = "conversation"
            allow_tools = False
            reason = "No explicit action requested; answer conversationally."

        # Keep simple conversational follow-ups conversational instead of
        # accidentally turning them into new tasks.
        if (
            previous is not None
            and self._short_followup(normal)
            and not action
            and not troubleshooting
            and not advice
        ):
            if previous.mode in {"conversation", "advice"}:
                mode = previous.mode
                allow_tools = False
                if previous.sensitive:
                    sensitive = True
                    sensitive_kind = previous.sensitive_kind
                    domain = previous.domain
                reason = "Short follow-up inherits the prior conversational context."

        return InteractionContext(
            mode=mode,
            domain=domain,
            action_requested=action,
            sensitive=sensitive,
            sensitive_kind=sensitive_kind,
            troubleshooting=troubleshooting,
            allow_tools=allow_tools,
            reason=reason,
            explicit_file=explicit_file,
        )

    @staticmethod
    def guidance(context: InteractionContext) -> str:
        lines = [
            "STEP 13 INTERACTION CONTEXT",
            f"Mode: {context.mode}",
            f"Domain: {context.domain or 'general'}",
            f"Action requested: {context.action_requested}",
            f"Sensitive: {context.sensitive}",
            f"Reason: {context.reason}",
        ]

        if context.mode == "conversation":
            lines += [
                "This is conversation, not an action request.",
                "Do not call tools merely because technical nouns appear.",
                "Respond naturally and contextually. Personality may be more visible.",
            ]
        elif context.mode == "advice":
            lines += [
                "Discuss and advise; do not perform an operation unless the user explicitly asks.",
                "Give practical recommendations and explain trade-offs.",
            ]
        elif context.mode == "action":
            lines += [
                "The user explicitly requested an operation.",
                "Use only tools relevant to that operation and report actual results.",
            ]
        elif context.mode == "troubleshooting":
            lines += [
                "Treat this as active troubleshooting.",
                "Evidence and diagnostic state outrank personality. Use tools/playbooks when appropriate.",
            ]
        elif context.mode == "sensitive_action":
            lines += [
                "The user requested action involving credentials or secrets.",
                "Do not retrieve, display, echo, copy, search for, or expose secret contents.",
                "Explain the safer alternative instead.",
            ]

        if context.sensitive:
            lines += [
                "SECURITY-AWARE CONVERSATION",
                "Do not ask the user to paste real passwords, tokens, private keys, recovery codes, or credentials.",
                "If plaintext password storage is discussed, advise against it and recommend a password manager or appropriate secret store.",
                "For an obviously unsafe practice stated casually, do not answer like a policy disclaimer: lead with one concise dry/sarcastic or pointed reaction, then give the corrective guidance.",
                "An honest question or distress needs a clear answer, not ridicule.",
                "If confirmed user-role context makes the mistake especially incongruous, you may say they should know better; never invent a role or personal fact.",
            ]

        return "\n".join(lines)
