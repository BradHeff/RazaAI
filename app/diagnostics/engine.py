from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from app.knowledge import KnowledgeEngine
from .ranking import rank_incident_evidence


TROUBLESHOOTING_TERMS = {
    "not working",
    "doesn't work",
    "does not work",
    "cannot",
    "can't",
    "fails",
    "failed",
    "failure",
    "issue",
    "problem",
    "error",
    "offline",
    "down",
    "broken",
    "drops",
    "disconnect",
    "timeout",
    "timed out",
    "no internet",
    "no network",
    "won't join",
    "will not join",
    "unable to",
    "why is",
    "why does",
    # Application/VPN symptoms and evidence-first phrasing.
    "502",
    "503",
    "504",
    "bad gateway",
    "gateway timeout",
    "tunnel is down",
    "tunnel down",
    "not responding",
    "unreachable",
    "lost access",
    "cannot access",
    "can't access",
    "unable to access",
    "does not load",
    "doesn't load",
    "won't load",
    "will not load",
    "connection refused",
    "refused",
    "what should i verify",
    "verify first",
    "check first",
}


# The user is asking for a full method/order, not the single next check.
PROCEDURE_REQUEST_TERMS = (
    "troubleshooting order",
    "systematic",
    "step by step",
    "step-by-step",
    "all the checks",
    "all checks",
    "everything to verify",
    "everything to check",
    "checklist",
    "full process",
    "the process",
    "methodical",
    "walk me through",
    "in order",
    "what order",
    "how would you troubleshoot",
    "how do i troubleshoot",
    "how should i troubleshoot",
)


def is_procedure_request(query: str) -> bool:
    text = (query or "").lower()
    return any(term in text for term in PROCEDURE_REQUEST_TERMS)


@dataclass
class DiagnosticContext:
    is_troubleshooting: bool
    expert: str
    category: str | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    primary_evidence: dict[str, Any] | None = None
    secondary_evidence: list[dict[str, Any]] = field(default_factory=list)
    prior_incidents: list[dict[str, Any]] = field(default_factory=list)
    procedure_request: bool = False


class DiagnosticEngine:
    def is_troubleshooting(self, query: str) -> bool:
        text = query.lower()

        if any(term in text for term in TROUBLESHOOTING_TERMS):
            return True

        symptom_terms = {
            "nps", "radius", "wifi", "wi-fi", "vlan", "dhcp",
            "dns", "routing", "gateway", "intune", "gpo",
            "initramfs", "fsck", "kernel", "service", "authentication",
            "nginx", "apache", "proxy", "upstream", "ipsec", "vpn", "tunnel",
            "fortigate", "phase 1", "phase 2",
        }

        action_terms = {
            "why", "what should i check", "diagnose",
            "troubleshoot", "fix", "resolve", "investigate",
        }

        return (
            any(term in text for term in symptom_terms)
            and any(term in text for term in action_terms)
        )

    def retrieve_evidence(
        self,
        query: str,
        category: str | None,
        top_k: int = 8,
    ) -> list[dict]:
        engine = KnowledgeEngine()

        try:
            return engine.search(
                query=query,
                top_k=top_k,
                category=category,
            )
        finally:
            engine.close()

    def build_context(
        self,
        query: str,
        route,
        retrieval_query: str | None = None,
    ) -> DiagnosticContext:
        troubleshooting = self.is_troubleshooting(query)
        evidence_query = (retrieval_query or query).strip()

        context = DiagnosticContext(
            is_troubleshooting=troubleshooting,
            procedure_request=troubleshooting and is_procedure_request(query),
            expert=route.expert,
            category=route.category,
        )

        if troubleshooting:
            raw = self.retrieve_evidence(
                query=evidence_query,
                category=route.category,
                top_k=8,
            )

            ranked = rank_incident_evidence(
                evidence_query,
                raw,
            )

            context.evidence = ranked
            context.primary_evidence = (
                ranked[0]
                if ranked
                else None
            )
            context.secondary_evidence = ranked[1:3]

        return context

    def _format_item(
        self,
        item: dict,
        label: str,
    ) -> str:
        citation = item.get("citation") or {}
        title = (
            citation.get("title")
            or citation.get("filename")
            or "Unknown source"
        )
        knowledge_type = (
            citation.get("knowledge_type")
            or "reference"
        )
        scope = (
            citation.get("scope")
            or "general"
        )
        incident_score = item.get(
            "incident_score",
            0,
        )
        text = (
            item.get("text")
            or ""
        ).strip()

        # Curated reference documents are written to be read from the
        # top (meaning -> ordered checks -> evidence). A single mid-document
        # chunk :  or a bare title chunk :  loses the checklist, so reference
        # items always carry the document head.
        if knowledge_type == "reference":
            expanded = self._expand_reference_document(item, self.THIN_CHUNK_EXPANSION_CHARS)
            if expanded:
                text = expanded

        if len(text) > self.MAX_ITEM_CHARS:
            text = text[: self.MAX_ITEM_CHARS].rstrip() + "..."

        return (
            f"{label}\n"
            f"title={title!r}; "
            f"type={knowledge_type}; "
            f"scope={scope}; "
            f"incident_score={incident_score}\n"
            f"{text}"
        )

    # A procedure request needs the whole reference document in order,
    # not the handful of best-scoring chunks (which may be only the intro).
    PROCEDURE_DOCUMENT_CHARS = 4200
    THIN_CHUNK_CHARS = 220
    THIN_CHUNK_EXPANSION_CHARS = 2200
    MAX_ITEM_CHARS = 2200

    @staticmethod
    def _expand_reference_document(item: dict, max_chars: int) -> str | None:
        citation = item.get("citation") or {}
        if (citation.get("knowledge_type") or "reference") != "reference":
            return None
        source = citation.get("source")
        if not source:
            return None
        try:
            path = Path(source)
            if not path.is_file():
                # The vector store may have been built on another
                # machine (absolute sandbox paths). Re-resolve under this
                # project's knowledge directory by the path tail.
                from ..config import BASE_DIR
                parts = Path(source).parts
                if "knowledge" in parts:
                    tail = Path(*parts[parts.index("knowledge") + 1:])
                    path = BASE_DIR / "knowledge" / tail
                if not path.is_file():
                    return None
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            return None
        text = text.strip()
        if len(text) > max_chars:
            cut = text.rfind("\n## ", 0, max_chars)
            text = text[: cut if cut > max_chars // 2 else max_chars].rstrip() + "\n..."
        return text

    def procedure_evidence_summary(self, context: DiagnosticContext) -> str:
        if not context.evidence:
            return "No retrieved evidence."
        primary = context.primary_evidence or context.evidence[0]
        expanded = self._expand_reference_document(primary, self.PROCEDURE_DOCUMENT_CHARS)
        parts = []
        if expanded:
            citation = primary.get("citation") or {}
            title = citation.get("title") or citation.get("filename") or "Unknown source"
            parts.append(
                "PRIMARY EVIDENCE (full reference document, in order)\n"
                f"title={title!r}; type=reference\n{expanded}"
            )
            seen = {citation.get("source")}
        else:
            parts.append(self._format_item(primary, "PRIMARY EVIDENCE"))
            seen = {(primary.get("citation") or {}).get("source")}
        # One additional distinct source for context, never a second chunk of the same doc.
        for item in context.secondary_evidence:
            source = (item.get("citation") or {}).get("source")
            if source in seen:
                continue
            parts.append(self._format_item(item, "SECONDARY EVIDENCE"))
            break
        return "\n\n".join(parts)

    def evidence_summary(
        self,
        context: DiagnosticContext,
    ) -> str:
        if not context.evidence:
            return (
                "No relevant local field-note evidence "
                "was retrieved."
            )

        parts = []
        seen_sources = set()

        def _source(item):
            return (item.get("citation") or {}).get("source")

        if context.primary_evidence:
            parts.append(
                self._format_item(
                    context.primary_evidence,
                    "PRIMARY EVIDENCE",
                )
            )
            seen_sources.add(_source(context.primary_evidence))

        index = 0
        for item in context.secondary_evidence:
            # A reference document already shown in full is not
            # repeated as fragments; distinct sources still appear.
            citation = item.get("citation") or {}
            if (
                citation.get("knowledge_type") == "reference"
                and _source(item) in seen_sources
            ):
                continue
            index += 1
            parts.append(
                self._format_item(
                    item,
                    f"SECONDARY EVIDENCE {index}",
                )
            )
            seen_sources.add(_source(item))

        return "\n\n".join(parts)

    def guidance(
        self,
        context: DiagnosticContext,
    ) -> str:
        if not context.is_troubleshooting:
            return (
                "This does not appear to be a troubleshooting incident. "
                "Answer normally and use tools or knowledge only when useful."
            )

        if context.procedure_request:
            return self._procedure_guidance(
                context, self.procedure_evidence_summary(context)
            )

        evidence_text = self.evidence_summary(
            context
        )

        return f"""
You are handling an ICT troubleshooting incident as the {context.expert} expert.

Use this method:
OBSERVE -> RETRIEVE -> HYPOTHESISE -> VERIFY -> ISOLATE -> RESOLVE -> VALIDATE

STRICT DIAGNOSTIC RULES:

1. Do NOT dump a long list of generic possibilities.
2. Base the PRIMARY HYPOTHESIS on PRIMARY EVIDENCE unless:
   a) live tool data directly contradicts it, or
   b) the primary evidence clearly does not match the observed symptom.
3. If you override PRIMARY EVIDENCE, explicitly say why.
4. Give at most TWO alternative hypotheses.
5. Prefer the minimum next check that can confirm or falsify the primary hypothesis.
6. Do not widen the search until that targeted check fails.
7. Evidence labels must be accurate:
   - "From our field notes/knowledge:" only for retrieved evidence.
   - "From live tools:" only for actual tool results.
   - "Additional diagnosis:" only for your own reasoning.
8. Never present a secondary incident as though it were the strongest known match.
9. If confidence is limited, say so.
10. Keep troubleshooting answers concise and operational.

Preferred answer structure:

Primary hypothesis:
...

Why:
...

Check first:
...

If confirmed:
...

If not:
...

Retrieved evidence:
{evidence_text}
""".strip()

    @staticmethod
    def _procedure_guidance(context: DiagnosticContext, evidence_text: str) -> str:
        """The user asked for a systematic order, not a single next check."""
        return f"""
You are answering as the {context.expert} expert. The user asked for a SYSTEMATIC
troubleshooting ORDER, not a single diagnosis.

PROCEDURE RULES:

1. Give an ordered list that covers EVERY layer relevant to the symptom, from the
   outside in (for a VPN/tunnel: underlay reachability -> Phase 1 / IKE ->
   Phase 2 / selectors and proposals -> routing and firewall policy -> stability;
   for a service: process/listener -> logs -> reachability -> permissions ->
   resources -> configuration).
2. Use the retrieved evidence below as the checklist source. Include its steps;
   do not collapse it to its title or its first item.
3. For EACH step name the concrete evidence that settles it: the command, log,
   counter, session table, debug output, or matched policy ID to look at.
4. Stay read-only: describe what to inspect, never a configuration change,
   unless the user explicitly asked for one.
5. End with an "Evidence to collect:" line listing the outputs to gather before
   anything is changed.
6. Be concise per step, but do not omit steps. Do not claim any check was run.

Answer structure:

Order:
1. <layer> — what to verify — evidence: <command/log/output>
2. ...

Evidence to collect:
- ...

Retrieved evidence:
{evidence_text}
""".strip()
