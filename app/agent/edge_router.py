"""Deterministic action routing for small edge models."""

from dataclasses import dataclass, field
import re

from ..playbooks.technical_guidance import NPS_EAP_ENTRY_RESPONSE


@dataclass
class EdgeRoute:
    kind: str = "model"
    tool: str | None = None
    arguments: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    reason: str = ""
    interrupts_playbook: bool = False
    response: str | None = None


LOCAL_FACT_TOOLS = {
    "gateway": "get_ip_configuration",
    "ip": "get_ip_configuration",
    "dns": "get_ip_configuration",
    "routes": "get_routing_table",
    "interfaces": "get_network_interfaces",
    "system": "get_system_info",
}

_LOCAL_ANCHOR = re.compile(
    r"\b(?:this (?:machine|host|box|device|computer|system|jetson)|my (?:machine|host|box|device|computer|system)|"
    r"locally|local(?:ly)?\b|here|razaai(?:'s)?|your (?:own )?(?:machine|host|box|ip|gateway|routes?|interfaces?)|"
    r"are you (?:on|using)|do you have|what(?:'s| is) (?:my|your)|my (?:ip|gateway|dns|routes?|interfaces?|address))\b",
    re.I,
)
_CONCEPTUAL = re.compile(
    r"\b(?:what (?:is|does) an?\b|what does .* mean|explain|how does|difference between|in general|definition)\b",
    re.I,
)
_REMOTE_TARGET = re.compile(
    r"\b(?:on|of|for|at)\s+(?:the\s+)?(?:server|switch|router|firewall|fortigate|aruba|core|host\s+\S+|"
    r"\d{1,3}(?:\.\d{1,3}){3}|[a-z0-9-]+\.[a-z0-9.-]+\b)",
    re.I,
)


def local_fact_route(lower: str):
    """Read-only facts about the machine RazaAI runs on are deterministic."""
    if _CONCEPTUAL.search(lower) or _REMOTE_TARGET.search(lower):
        return None
    local = bool(_LOCAL_ANCHOR.search(lower))
    imperative = bool(re.match(r"\s*(?:show|check|get|list|display|print|run|what(?:'s| is| are))\b", lower))
    if not (local or imperative):
        return None
    if re.search(r"\b(?:default )?gateway\b", lower):
        return LOCAL_FACT_TOOLS["gateway"]
    if re.search(r"\brout(?:e|es|ing)\b", lower):
        return LOCAL_FACT_TOOLS["routes"]
    if re.search(r"\bdns\b", lower):
        return LOCAL_FACT_TOOLS["dns"]
    if re.search(r"\b(?:interfaces?|nics?|network adapters?|ethernet ports?)\b", lower):
        return LOCAL_FACT_TOOLS["interfaces"]
    if re.search(r"\b(?:ip(?:v4|v6)? (?:address(?:es)?|config(?:uration)?)|ip addr|what ip\b|my ip|your ip|which ip)\b", lower):
        return LOCAL_FACT_TOOLS["ip"]
    if local and re.search(r"\b(?:hostname|uptime|cpu|memory|ram|disk|os version|kernel|system info(?:rmation)?)\b", lower):
        return LOCAL_FACT_TOOLS["system"]
    return None


class EdgeIntentRouter:
    PORT_CX = re.compile(r"\b\d+/\d+/\d+\b")
    PATCH_ID = re.compile(r"\bPATCH-\d{8}-\d{6}-\d{6}\b", re.I)
    IMPROVEMENT_ID = re.compile(r"\bIMPROVE-\d{8}-\d{6}-\d{6}\b", re.I)
    TRAINING_ID = re.compile(r"\bTRAIN-\d{8}-\d{6}-\d{6}\b", re.I)
    MODEL_ID = re.compile(r"\bMODEL-\d{8}-\d{6}-\d{6}\b", re.I)
    PORT_AOS = re.compile(r"\b(?:[A-Za-z]\d+|\d{1,2})\b")

    def __init__(self, manager=None):
        if manager is None:
            from ..infrastructure import InfrastructureManager
            manager = InfrastructureManager()
        self.manager = manager

    @staticmethod
    def _is_document_request(text):
        t = text.lower()

        action = any(
            value in t
            for value in (
                "create",
                "generate",
                "produce",
                "save",
                "export",
                "write",
            )
        )

        document = any(
            value in t
            for value in (
                "document",
                "docx",
                "word",
                "pdf",
                "report",
            )
        )

        return action and document

    @staticmethod
    def _document_arguments(text):
        lower = text.lower()

        fmt = (
            "both"
            if (("word" in lower or "docx" in lower) and "pdf" in lower)
            else ("pdf" if "pdf" in lower else "docx")
        )

        title = None

        match = re.search(
            r"(?:called|named|titled)\s+"
            r"(.+?)"
            r"(?:\s+with\s+(?:a\s+)?"
            r"(?:summary|section)\b|[.!?]?$)",
            text,
            re.I,
        )

        if match:
            title = match.group(1).strip(" .\"'")

        summary = None

        match = re.search(
            r"\bsummary\s+section\s+"
            r"(?:saying|that says|stating)\s+"
            r"(.+?)(?:[.!?]?\s*$)",
            text,
            re.I,
        )

        if match:
            summary = match.group(1).strip(" \"'")

            if summary and summary[-1] not in ".!?":
                summary += "."

        if title and summary:
            return {
                "title": title,
                "filename": title,
                "format": fmt,
                "template": "general_document",
                "sections": [
                    {
                        "heading": "Summary",
                        "paragraphs": [summary],
                    }
                ],
            }

        return None

    def _host(self, text):
        lower = text.lower()

        hosts = [
            host["name"] for host in self.manager.list_hosts() if host.get("enabled")
        ]

        for host in sorted(
            hosts,
            key=len,
            reverse=True,
        ):
            if re.search(
                rf"(?<![\w-]){re.escape(host.lower())}(?![\w-])",
                lower,
            ):
                return host

        # Friendly aliases resolve only when inventory makes the
        # target unambiguous. Python never invents a hostname.
        enabled = [
            item
            for item in self.manager.list_hosts()
            if item.get("enabled")
        ]

        if any(
            phrase in lower
            for phrase in ("aruba switch", "aruba core", "the aruba")
        ):
            aruba_hosts = [
                item["name"]
                for item in enabled
                if item.get("type") == "aruba"
            ]
            if len(aruba_hosts) == 1:
                return aruba_hosts[0]

        if "fortigate" in lower:
            fortigate_hosts = [
                item["name"]
                for item in enabled
                if item.get("type") == "fortigate"
            ]
            if len(fortigate_hosts) == 1:
                return fortigate_hosts[0]

        return None

    def _port(self, text, host=None):
        match = self.PORT_CX.search(text)

        if match:
            return match.group(0)

        match = re.search(
            r"\bport\s+([A-Za-z]\d+|\d{1,2})\b",
            text,
            re.I,
        )

        if match:
            return match.group(1)

        return None

    def route(self, user_input, interaction=None, user_name=None):
        text = user_input.strip()
        lower = text.lower()

        nps_eap_advice = bool(
            re.search(r"\b(?:nps|radius)\b", lower)
            and re.search(r"\b(?:eap|802\.?1x|peap|wifi|wi-fi|wlan)\b", lower)
            and (
                re.search(r"\b(?:how|why|troubleshoot|fix|issue|problem)\b", lower)
                or "not working" in lower
            )
        )
        if nps_eap_advice and not re.search(
            r"\b(?:check|inspect|run|show|get|query)\s+(?:the\s+)?(?:server|nps|logs?|event|radius)\b",
            lower,
        ):
            return EdgeRoute(
                kind="deterministic_response",
                response=NPS_EAP_ENTRY_RESPONSE,
                reason="Evidence-first NPS/EAP troubleshooting guidance",
                interrupts_playbook=True,
            )

        # Sensitive-content action requests never become tool calls.
        if interaction is not None and interaction.mode == "sensitive_action":
            return EdgeRoute(
                kind="model",
                reason="Sensitive action is conversation-only; secret contents stay blocked.",
                interrupts_playbook=True,
            )

        # Local read-only facts never depend on the model choosing a tool.
        local_tool = local_fact_route(lower)
        if local_tool:
            return EdgeRoute(
                kind="deterministic_tool",
                tool=local_tool,
                arguments={},
                reason="Local host fact requested; Python runs the read-only tool and renders the answer",
                interrupts_playbook=False,
            )

        # Overall capability descriptions are Python-owned. A small
        # model should not improvise capabilities such as credential inspection
        # that conflict with deterministic security/tool boundaries.
        capability_summary_request = bool(
            re.search(
                r"\b(?:what can you do(?: so far)?|what are your capabilities|"
                r"what features do you have|what do you support|tell me your capabilities)\b",
                lower,
                re.I,
            )
        )
        if capability_summary_request:
            return EdgeRoute(
                kind="deterministic_response",
                response=(
                    "I can help with technical troubleshooting and ICT work, inspect "
                    "authorized local/infrastructure evidence through tools, create "
                    "DOCX/PDF documents, use grounded read-only public web information, "
                    "remember safe non-secret facts and preferences, learn conservatively "
                    "from validated outcomes, audit my project, and build/test controlled "
                    "self-improvement candidates. I protect passwords, credentials, API "
                    "keys, and other secrets rather than exposing them. Production code "
                    "promotion, model training, and active-model replacement require "
                    "explicit approval."
                ),
                reason="Authoritative capability summary",
                interrupts_playbook=True,
            )

        # Persistent memory is Python-owned. Specific memory
        # operations take priority over generic capability questions.
        remember_match = re.match(
            r"^\s*(?:please\s+)?remember(?:\s+that)?\s+(.+?)\s*$",
            text,
            re.I,
        )
        if remember_match:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="remember_memory",
                arguments={
                    "text": remember_match.group(1).strip(),
                    "domain": getattr(interaction, "domain", None),
                },
                reason="Explicit persistent memory write",
                interrupts_playbook=True,
            )

        forget_match = re.match(
            r"^\s*(?:please\s+)?forget(?:\s+(?:that|about))?\s+(.+?)\s*$",
            text,
            re.I,
        )
        if forget_match and forget_match.group(1).strip().casefold() not in {
            "it",
            "that",
            "never mind",
        }:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="forget_memory",
                arguments={
                    "query": forget_match.group(1).strip(),
                },
                reason="Explicit persistent memory deletion",
                interrupts_playbook=True,
            )

        if re.search(
            r"\b(?:memory status|show memory status|how much do you remember)\b",
            lower,
            re.I,
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="memory_status",
                arguments={},
                reason="Persistent memory status request",
                interrupts_playbook=True,
            )

        known_user_name = str(user_name or "").strip()
        identity_profile_recall = bool(
            re.search(
                r"\b(?:who am i|what(?:'s| is) my job|what do i do|"
                r"what(?:'s| is) my online profile|tell me my online profile|"
                r"do you remember my online profile|do you know my online profile)\b",
                lower,
                re.I,
            )
        )
        if known_user_name and re.search(re.escape(known_user_name), text, re.I):
            identity_profile_recall = identity_profile_recall or bool(
                re.search(r"\b(?:who is|job|role|online profile|what does)\b", lower, re.I)
            )

        if identity_profile_recall:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="get_identity_profile",
                arguments={"query": text},
                reason="User identity/profile recall request",
                interrupts_playbook=True,
            )

        if re.search(
            r"\b(?:what do you remember about me|what do you remember|"
            r"show (?:me )?(?:your )?memories|list (?:your )?memories)\b",
            lower,
            re.I,
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="search_memory",
                arguments={
                    "query": "",
                    "top_k": 20,
                },
                reason="Persistent memory summary request",
                interrupts_playbook=True,
            )

        if re.search(
            r"\b(?:what(?:'s| is) my name|who am i|what do i prefer|"
            r"what(?:'s| is) my timezone)\b",
            lower,
            re.I,
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="search_memory",
                arguments={
                    "query": text,
                    "domain": getattr(interaction, "domain", None),
                    "top_k": 5,
                },
                reason="Persistent memory recall request",
                interrupts_playbook=True,
            )

        memory_capability_request = bool(
            re.search(
                r"\b(?:can you|do you|are you able to)\b.{0,24}"
                r"\b(?:learn|remember|have memory|use memory)\b",
                lower,
                re.I,
            )
        ) or lower in {
            "what about memory",
            "do you have a memory",
            "do you have memory",
        }

        if memory_capability_request:
            return EdgeRoute(
                kind="deterministic_response",
                response=(
                    "Yes. I have persistent local memory. I can retain safe "
                    "user-confirmed facts and preferences, recall them in later "
                    "sessions, and conservatively learn technical patterns from "
                    "repeated user-reported outcomes. Secrets are never stored, "
                    "and live evidence outranks memory."
                ),
                reason="Persistent memory capability question",
                interrupts_playbook=True,
            )

        # Web access is explicit, read-only, and Python-owned.
        # Capability questions do not themselves perform a network request.
        web_capability_request = bool(
            re.search(
                r"\b(?:can you|do you|are you able to)\b.{0,24}"
                r"\b(?:use|access|search|browse)\b.{0,16}\b(?:web|internet|online)\b",
                lower,
                re.I,
            )
        )

        if web_capability_request:
            return EdgeRoute(
                kind="deterministic_response",
                response=(
                    "Yes. I have read-only public web search and webpage retrieval. "
                    "I only use it when you explicitly ask for web/current information, "
                    "and web-derived claims carry source provenance."
                ),
                reason="Web capability question",
                interrupts_playbook=True,
            )

        explicit_url_match = re.search(
            r"https?://[^\s<>\"]+",
            text,
            re.I,
        )
        fetch_markers = (
            "open",
            "read",
            "fetch",
            "summarize",
            "summarise",
            "check this url",
            "check this page",
            "look at",
        )

        if explicit_url_match and any(
            marker in lower
            for marker in fetch_markers
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="fetch_web_page",
                arguments={
                    "url": explicit_url_match.group(0).rstrip(".,);]"),
                    "max_chars": 12000,
                },
                reason="Explicit public webpage retrieval request",
                interrupts_playbook=True,
            )

        explicit_web_markers = (
            "search the web",
            "search web",
            "search the internet",
            "search internet",
            "look it up online",
            "look up online",
            "look this up online",
            "find online",
            "web search",
            "browse the web",
            "check online",
            "search online",
        )

        # Tolerate common misspellings of "search" before an
        # online/web/internet qualifier ("sear online for X" was observed
        # live and fell through to a chat answer). Targeted: only fixes the
        # verb directly preceding an online qualifier.
        typo_lower = re.sub(
            r"\b(?:sear|serach|saerch|serch|seacrh|sarch)\s+"
            r"(?=online|the web|web|the internet|internet)",
            "search ",
            lower,
            flags=re.I,
        )

        freshness_request = bool(
            re.search(
                r"\b(?:latest|recent|newest|today's|today)\b",
                lower,
                re.I,
            )
        )
        # Time-anchored change questions are freshness questions too.
        # "what changed in Ollama this month?" / "what's new in X?" /
        # "is there a newer version of Y?" cannot be answered from training data.
        freshness_request = freshness_request or bool(
            re.search(
                r"\b(?:what(?:'s| is| has| have)?\s+(?:changed|new)|"
                r"(?:this|last|past)\s+(?:week|month|year|quarter)|"
                r"(?:newer|new(?:est)?|updated|upgraded)\s+(?:version|release|build|firmware)|"
                r"release notes|changelog|change log|what'?s new)\b",
                lower,
                re.I,
            )
        )

        # "current" is too common in local diagnostics ("current IP config",
        # "current route"). Route it to the web only when paired with an
        # obviously external/fresh information concept.
        current_external_request = (
            "current" in lower
            and any(
                term in lower
                for term in (
                    "release",
                    "version",
                    "firmware",
                    "news",
                    "price",
                    "weather",
                    "documentation",
                    "advisory",
                    "cve",
                    "vulnerability",
                    "status page",
                )
            )
        )

        freshness_request = freshness_request or current_external_request

        local_current_markers = (
            "routing table",
            "route table",
            "ip config",
            "interface",
            "this machine",
            "this host",
            "current ip",
            "current interface",
            "current route",
            "current routing",
            "current vlan",
            "current configuration",
            "current config",
            "current system",
            "current host",
        )

        if any(marker in lower for marker in local_current_markers):
            freshness_request = False
        # Conceptual/historical comparisons are not freshness requests.
        if re.match(r"\s*(?:explain|describe|compare|what is the difference)\b", lower) or re.search(
            r"\bbetween\s+\S+.{0,40}\band\b", lower
        ):
            freshness_request = False

        web_search_request = any(
            marker in typo_lower
            for marker in explicit_web_markers
        ) or freshness_request

        if web_search_request:
            # Normalise the misspelled verb in the original-cased text so the
            # marker stripping below removes it from the query cleanly.
            query = re.sub(
                r"\b(?:sear|serach|saerch|serch|seacrh|sarch)\s+"
                r"(?=online|the web|web|the internet|internet)",
                "search ",
                text,
                flags=re.I,
            )

            for marker in explicit_web_markers:
                query = re.sub(
                    re.escape(marker),
                    " ",
                    query,
                    flags=re.I,
                )

            query = re.sub(
                r"\s+",
                " ",
                query,
            ).strip(" ?")

            if not query:
                return EdgeRoute(
                    kind="deterministic_response",
                    response="Tell me what you want me to search the web for.",
                    reason="Web search requires a query",
                    interrupts_playbook=True,
                )

            return EdgeRoute(
                kind="deterministic_tool",
                tool="search_web",
                arguments={
                    "query": query,
                    "max_results": 5,
                },
                reason="Explicit/fresh public web research request",
                interrupts_playbook=True,
            )

        # Infrastructure inventory discovery is deterministic.
        # Listing configured targets is local metadata only; it does not contact
        # a switch/server/firewall or read credentials.
        infrastructure_list_request = any(
            phrase in lower
            for phrase in (
                "what hosts can you see",
                "which hosts can you see",
                "what infrastructure can you see",
                "which infrastructure can you see",
                "list infrastructure",
                "list your infrastructure",
                "show infrastructure",
                "what devices can you see",
                "which devices can you see",
            )
        )

        if infrastructure_list_request:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="list_infrastructure",
                arguments={},
                reason="Explicit infrastructure inventory discovery request",
                interrupts_playbook=True,
            )

        # Filename existence/location questions use a filename/path
        # browser rather than Python source-code search. This returns metadata only.
        explicit_file = getattr(interaction, "explicit_file", None) if interaction else None
        if explicit_file and re.search(
            r"\b(?:can you see|do you see|can you find|locate|does .* exist|is .* there)\b",
            lower,
            re.I,
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="search_project_files",
                arguments={"query": explicit_file, "max_results": 10},
                reason="Explicit project-file existence/location request",
                interrupts_playbook=True,
            )

        self_improvement_capability = bool(
            re.search(
                r"\b(?:do you have|can you|is there)\b.{0,40}"
                r"\b(?:self[ -]?improvement|improve yourself|self[ -]?repair)\b",
                lower,
                re.I,
            )
        )
        if self_improvement_capability:
            return EdgeRoute(
                kind="deterministic_response",
                response=(
                    "Yes. I can build code improvements in an isolated sandbox, "
                    "add regression tests, compare candidate behavior against trusted "
                    "tests, and prepare a verified candidate for approval. I can also "
                    "prepare model-training jobs and stage/test GGUF candidates. "
                    "Production code changes, expensive training, and active-model "
                    "replacement still require explicit approval and retain rollback."
                ),
                reason="Controlled self-improvement capability question",
                interrupts_playbook=True,
            )

        improvement_match = self.IMPROVEMENT_ID.search(text)
        training_match = self.TRAINING_ID.search(text)
        model_match = self.MODEL_ID.search(text)

        if improvement_match and any(word in lower for word in ("apply", "approve", "promote")):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="promote_self_improvement",
                arguments={"improvement_id": improvement_match.group(0).upper()},
                reason="Explicit user approval to promote a verified self-improvement candidate",
                interrupts_playbook=True,
            )

        if improvement_match and any(word in lower for word in ("rollback", "revert")):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="rollback_self_improvement",
                arguments={"improvement_id": improvement_match.group(0).upper()},
                reason="Explicit user request to roll back a promoted self-improvement",
                interrupts_playbook=True,
            )

        if training_match and any(word in lower for word in ("run", "approve", "train", "start")):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="run_model_training",
                arguments={"training_id": training_match.group(0).upper()},
                reason="Explicit user approval to run prepared model training",
                interrupts_playbook=True,
            )

        if model_match and any(word in lower for word in ("apply", "approve", "promote", "replace")):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="promote_model_candidate",
                arguments={"model_id": model_match.group(0).upper()},
                reason="Explicit user approval to replace the active Ollama model with a verified candidate",
                interrupts_playbook=True,
            )

        if model_match and any(word in lower for word in ("rollback", "revert")):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="rollback_model_candidate",
                arguments={"model_id": model_match.group(0).upper()},
                reason="Explicit user request to restore the prior Ollama model",
                interrupts_playbook=True,
            )

        patch_match = self.PATCH_ID.search(text)

        if ("apply" in lower or "approve" in lower) and (
            "patch" in lower or patch_match
        ):
            arguments = {}
            if patch_match:
                arguments["patch_id"] = patch_match.group(0).upper()
            return EdgeRoute(
                kind="deterministic_tool",
                tool="apply_self_patch",
                arguments=arguments,
                reason="Explicit user approval to apply a prepared self-repair patch",
                interrupts_playbook=True,
            )

        if ("rollback" in lower or "revert" in lower) and patch_match:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="rollback_self_patch",
                arguments={"patch_id": patch_match.group(0).upper()},
                reason="Explicit user request to roll back an applied self-repair patch",
                interrupts_playbook=True,
            )

        self_reference = any(
            phrase in lower
            for phrase in (
                "your code",
                "yourself",
                "self audit",
                "self-audit",
                "self check",
                "self-check",
                "razaai code",
                "razaai health",
            )
        )

        audit_request = (
            self_reference
            and any(
                word in lower
                for word in (
                    "audit",
                    "check",
                    "inspect",
                    "test",
                    "operating correctly",
                    "working correctly",
                    "healthy",
                )
            )
        ) or any(
            phrase in lower
            for phrase in (
                "are you operating correctly",
                "are you working correctly",
                "check your code",
                "audit your code",
                "run a self check",
            )
        )

        code_investigation_request = (
            ("your" in lower or "razaai" in lower)
            and "code" in lower
            and any(
                word in lower
                for word in (
                    "inspect",
                    "review",
                    "analyse",
                    "analyze",
                    "improve",
                    "refactor",
                    "optimise",
                    "optimize",
                )
            )
            and not any(
                phrase in lower
                for phrase in (
                    "check your code",
                    "audit your code",
                    "self audit",
                    "self-audit",
                )
            )
        )

        if code_investigation_request:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="investigate_project_code",
                arguments={
                    "query": text,
                    "max_files": 3,
                    "context_lines": 120,
                },
                reason=(
                    "Natural-language RazaAI code review; Python locates source "
                    "before inspection so the model cannot guess filenames."
                ),
                interrupts_playbook=True,
            )

        if audit_request:
            mode = (
                "full"
                if any(
                    value in lower
                    for value in ("full", "complete", "all tests", "thorough")
                )
                else "quick"
            )
            return EdgeRoute(
                kind="deterministic_tool",
                tool="audit_project",
                arguments={
                    "mode": mode,
                    "check_ollama": True,
                },
                reason="Explicit RazaAI self-health/code-audit request",
                interrupts_playbook=True,
            )

        if any(
            phrase in lower
            for phrase in (
                "operational brief",
                "operational briefing",
                "anything i should be worried about",
                "anything should i be worried about",
                "what needs my attention",
            )
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="get_operational_brief",
                arguments={"run_audit": False},
                reason="Explicit proactive operational briefing request",
                interrupts_playbook=True,
            )

        if "health" in lower and any(
            value in lower for value in ("razaai", "your", "system")
        ):
            return EdgeRoute(
                kind="deterministic_tool",
                tool="get_operational_health",
                arguments={"run_audit": True, "audit_mode": "quick"},
                reason="Explicit RazaAI operational-health request",
                interrupts_playbook=True,
            )

        if self._is_document_request(text):
            document_arguments = self._document_arguments(text)

            if document_arguments:
                return EdgeRoute(
                    kind="deterministic_tool",
                    tool="create_document",
                    arguments=document_arguments,
                    reason=(
                        "Explicit document request with "
                        "fully extractable title/content"
                    ),
                    interrupts_playbook=True,
                )

            return EdgeRoute(
                kind="document",
                reason="Explicit document creation request",
                interrupts_playbook=True,
            )

        host = self._host(text)

        if not host:
            return EdgeRoute()

        # "What about <known-host>?" is metadata discovery, not permission
        # to connect to the target.
        host_metadata_request = bool(
            re.match(
                r"^\s*(?:what\s+about|do\s+you\s+(?:know|see)|"
                r"can\s+you\s+see|is\s+there)\b",
                lower,
                re.I,
            )
        )

        if host_metadata_request:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="list_infrastructure",
                arguments={"host": host},
                reason="Configured infrastructure host metadata lookup",
                interrupts_playbook=True,
            )

        port_words = any(
            value in lower
            for value in (
                "port",
                "interface",
                "switch port",
            )
        )

        diagnose_words = any(
            value in lower
            for value in (
                "diagnose",
                "troubleshoot",
                "offline",
                "not working",
                "down",
            )
        )

        inspect_words = any(
            value in lower
            for value in (
                "inspect",
                "check port",
                "show port",
            )
        )

        port = self._port(
            text,
            host=host,
        )

        if port_words and (diagnose_words or inspect_words):
            if not port:
                return EdgeRoute(
                    kind="needs_input",
                    missing=["port"],
                    reason=(
                        "A switch-port operation requires "
                        "an explicit port; Python will not invent one."
                    ),
                    interrupts_playbook=True,
                )

            tool = "diagnose_aruba_port" if diagnose_words else "inspect_aruba_port"

            return EdgeRoute(
                kind="deterministic_tool",
                tool=tool,
                arguments={
                    "host": host,
                    "port": port,
                },
                reason="Explicit Aruba port operation",
                interrupts_playbook=True,
            )

        system_status = (
            "system status" in lower
            or "switch status" in lower
            or "system health" in lower
            or "switch health" in lower
        )

        if system_status:
            return EdgeRoute(
                kind="deterministic_tool",
                tool="run_infrastructure_check",
                arguments={
                    "host": host,
                    "check": "system",
                },
                reason="Explicit infrastructure system-status request",
                interrupts_playbook=True,
            )

        return EdgeRoute()
