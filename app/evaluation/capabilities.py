"""RazaAI real-world capability evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from app.ollama_client import OllamaClient
from urllib import error, request


@dataclass(frozen=True)
class CapabilityResult:
    case_id: str
    category: str
    passed: bool
    hard_gate: bool
    response: str
    failures: tuple[str, ...]
    tool_calls: tuple[str, ...] = ()
    interaction_mode: str | None = None
    interaction_domain: str | None = None
    interaction_sensitive: bool | None = None
    interaction_tools_allowed: bool | None = None


def _think_field(base_url, model):
    from app.ollama_client import OllamaClient
    return OllamaClient(host=base_url, model=model)._think_field()


class CandidateOllamaAdapter:
    """Drop-in deterministic replacement for RazaAgent.client."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 180,
        seed: int = 3407,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.seed = seed

    def chat(self, messages, tools=None):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            **_think_field(self.base_url, self.model),
            "options": {
                "temperature": 0,
                "seed": self.seed,
            },
        }

        if tools:
            payload["tools"] = tools

        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(
                f"Ollama capability-evaluation request failed: {exc}"
            ) from exc


class ToolExecutionRecorder:
    """Wrap ToolRegistry.execute without altering execution behavior."""

    def __init__(self, registry):
        self.registry = registry
        self.calls: list[tuple[str, dict]] = []
        self._original_execute = registry.execute

    def install(self):
        def execute(name, arguments=None):
            self.calls.append((name, dict(arguments or {})))
            return self._original_execute(name, arguments or {})

        self.registry.execute = execute

    def restore(self):
        self.registry.execute = self._original_execute

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.calls)

    def count(self, name: str) -> int:
        return sum(1 for called, _ in self.calls if called == name)


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold() in (text or "").casefold()


def _state(agent):
    interaction = getattr(agent, "last_interaction", None)
    if interaction is None:
        return None, None, None, None

    return (
        getattr(interaction, "mode", None),
        getattr(interaction, "domain", None),
        bool(getattr(interaction, "sensitive", False)),
        bool(getattr(interaction, "allow_tools", False)),
    )


def _new_agent(model: str, base_url: str, seed: int):
    from app.agent.agent import RazaAgent

    agent = RazaAgent()
    agent.client = CandidateOllamaAdapter(
        model=model,
        base_url=base_url,
        seed=seed,
    )

    recorder = ToolExecutionRecorder(agent.tools)
    recorder.install()
    return agent, recorder


def _result(
    case_id,
    category,
    response,
    failures,
    agent,
    recorder,
    hard_gate=False,
):
    mode, domain, sensitive, allow_tools = _state(agent)

    return CapabilityResult(
        case_id=case_id,
        category=category,
        passed=not failures,
        hard_gate=hard_gate,
        response=response or "",
        failures=tuple(failures),
        tool_calls=recorder.names,
        interaction_mode=mode,
        interaction_domain=domain,
        interaction_sensitive=sensitive,
        interaction_tools_allowed=allow_tools,
    )


def _require_any(response, phrases, failures, label):
    if not any(_contains(response, phrase) for phrase in phrases):
        failures.append(
            f"{label}: expected one of: " + " | ".join(phrases)
        )


def _forbid_any(response, phrases, failures, label):
    for phrase in phrases:
        if _contains(response, phrase):
            failures.append(
                f"{label}: forbidden phrase present: {phrase}"
            )


def _no_tools(recorder, failures):
    if recorder.names:
        failures.append(
            "unexpected tool execution: "
            + ", ".join(recorder.names)
        )


# Networking


def case_network_apipa(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A Windows laptop has a 169.254.44.8 address and cannot reach the gateway. "
            "What does that suggest and what should I check first?"
        )
        failures = []

        _require_any(
            response,
            ("DHCP", "APIPA", "link-local", "169.254"),
            failures,
            "network diagnosis",
        )
        _require_any(
            response,
            ("VLAN", "scope", "relay", "helper", "DHCP server", "lease"),
            failures,
            "network next checks",
        )
        _forbid_any(
            response,
            ("DNS is the root cause", "definitely DNS"),
            failures,
            "unsupported root cause",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.network.apipa",
            "networking",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


def case_network_dns(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A client can ping its gateway and 1.1.1.1, but hostnames fail. "
            "What is the most likely area to investigate?"
        )
        failures = []

        _require_any(
            response,
            ("DNS", "resolver", "name resolution"),
            failures,
            "DNS diagnosis",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.network.dns",
            "networking",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


def case_network_wifi_evidence(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "NPS authentication succeeds but staff Wi-Fi clients have no connectivity. "
            "Give me the next checks without assuming the root cause."
        )
        failures = []

        _require_any(
            response,
            ("VLAN", "DHCP", "gateway", "SSID"),
            failures,
            "Wi-Fi post-auth checks",
        )
        _forbid_any(
            response,
            ("the root cause is", "definitely"),
            failures,
            "unsupported certainty",
        )

        dangerous = [
            name
            for name in recorder.names
            if name in {
                "run_infrastructure_check",
                "inspect_aruba_port",
                "diagnose_aruba_port",
            }
        ]
        if dangerous:
            failures.append(
                "conceptual Wi-Fi question executed infrastructure tools: "
                + ", ".join(dangerous)
            )

        return _result(
            "cap.network.wifi_post_auth",
            "networking",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


# Windows / AD


def case_windows_gpo(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A domain computer is not receiving a printer Group Policy Preference. "
            "What evidence should I collect before changing the GPO?"
        )
        failures = []

        _require_any(
            response,
            ("gpresult", "Group Policy", "GPO", "event log", "Resultant"),
            failures,
            "GPO evidence",
        )
        _require_any(
            response,
            ("scope", "security filtering", "OU", "item-level", "preference"),
            failures,
            "GPO targeting",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.windows.gpo",
            "windows",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


def case_windows_ad_dns(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A domain-joined PC cannot locate a domain controller. "
            "It is configured to use 8.8.8.8 for DNS. What should I correct?"
        )
        failures = []

        _require_any(
            response,
            ("AD DNS", "domain DNS", "internal DNS", "DNS server", "domain controller"),
            failures,
            "AD DNS correction",
        )
        _forbid_any(
            response,
            ("keep 8.8.8.8 as primary",),
            failures,
            "bad AD DNS advice",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.windows.ad_dns",
            "windows",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


# Linux / servers


def case_linux_disk(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A Linux server's root filesystem is 97% full. "
            "What should I inspect before deleting anything?"
        )
        failures = []

        _require_any(
            response,
            ("df", "du", "largest", "filesystem", "logs", "journal"),
            failures,
            "disk-space evidence",
        )
        _forbid_any(
            response,
            ("rm -rf /var/log", "delete logs immediately"),
            failures,
            "unsafe deletion advice",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.linux.disk",
            "linux",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


def case_linux_502(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "Nginx returns 502 Bad Gateway for a local application. "
            "What should I verify first?"
        )
        failures = []

        _require_any(
            response,
            ("upstream", "backend", "port", "service", "socket"),
            failures,
            "502 diagnosis",
        )
        _require_any(
            response,
            ("log", "status", "reach", "listen"),
            failures,
            "502 evidence",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.linux.nginx_502",
            "linux",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


# FortiGate


def case_fortigate_policy(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A FortiGate firewall policy is not matching traffic. "
            "What should I verify before editing the policy?"
        )
        failures = []

        _require_any(
            response,
            ("policy order", "interface", "source", "destination", "service"),
            failures,
            "FortiGate policy checks",
        )
        _require_any(
            response,
            ("session", "log", "route", "debug flow", "policy ID"),
            failures,
            "FortiGate evidence",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.fortigate.policy",
            "fortigate",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


def case_fortigate_ipsec(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "A FortiGate IPsec tunnel is down. "
            "Give me a systematic troubleshooting order without changing configuration."
        )
        failures = []

        _require_any(
            response,
            ("phase 1", "phase1", "IKE"),
            failures,
            "IPsec phase 1",
        )
        _require_any(
            response,
            ("phase 2", "phase2", "selector"),
            failures,
            "IPsec phase 2",
        )
        _require_any(
            response,
            ("route", "policy", "traffic"),
            failures,
            "IPsec routing/policy",
        )
        _no_tools(recorder, failures)

        return _result(
            "cap.fortigate.ipsec",
            "fortigate",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


# Programming / self-inspection


def case_programming_code_review(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "Inspect your incident retrieval code and tell me one evidence-based improvement, "
            "or say no improvement is justified."
        )
        failures = []

        count = recorder.count("investigate_project_code")
        if count != 1:
            failures.append(
                f"investigate_project_code executed {count} times; expected once"
            )

        _forbid_any(
            response,
            (
                "I applied the patch",
                "I changed the code",
                "patch applied",
            ),
            failures,
            "unapproved write claim",
        )

        return _result(
            "cap.programming.code_review",
            "programming",
            response,
            failures,
            agent,
            recorder,
            hard_gate=True,
        )
    finally:
        recorder.restore()


# Documents


def case_document_creation(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "Create a short DOCX document titled 'RazaAI Step 15 Test' "
            "with the sentence 'Capability evaluation document.'"
        )
        failures = []

        count = recorder.count("create_document")
        if count != 1:
            failures.append(
                f"create_document executed {count} times; expected once"
            )

        if not response.strip():
            failures.append(
                "document creation returned an empty response"
            )

        if count == 0 and (
            _contains(response, "created")
            or _contains(response, "saved")
        ):
            failures.append(
                "model claimed document creation without tool execution"
            )

        return _result(
            "cap.document.docx",
            "documents",
            response,
            failures,
            agent,
            recorder,
            hard_gate=True,
        )
    finally:
        recorder.restore()


# Routing / ambiguity


def case_routing_ambiguous(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask("The network is slow.")
        failures = []

        if recorder.names:
            failures.append(
                "ambiguous symptom executed tools without required evidence: "
                + ", ".join(recorder.names)
            )

        _forbid_any(
            response,
            ("I found the fault", "the root cause is"),
            failures,
            "invented diagnosis",
        )

        _require_any(
            response,
            (
                "which",
                "where",
                "scope",
                "device",
                "site",
                "what",
                "measure",
            ),
            failures,
            "clarifying/scoping behavior",
        )

        return _result(
            "cap.routing.ambiguous",
            "routing",
            response,
            failures,
            agent,
            recorder,
            hard_gate=True,
        )
    finally:
        recorder.restore()


def case_routing_capability_only(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask(
            "Can you troubleshoot a FortiGate firewall?"
        )
        failures = []

        mode, domain, sensitive, allow_tools = _state(agent)

        if mode != "conversation":
            failures.append(
                f"capability question classified as {mode!r}, expected conversation"
            )

        if recorder.names:
            failures.append(
                "capability-only question executed tools: "
                + ", ".join(recorder.names)
            )

        _forbid_any(
            response,
            (
                "inspect_project_file",
                "investigate_project_code",
                "run_infrastructure_check",
            ),
            failures,
            "internal tool leakage",
        )

        return _result(
            "cap.routing.capability_only",
            "routing",
            response,
            failures,
            agent,
            recorder,
        )
    finally:
        recorder.restore()


# Self-operations


def case_selfops_health(model, base_url, seed):
    agent, recorder = _new_agent(model, base_url, seed)
    try:
        response = agent.ask("Are you operating correctly?")
        failures = []

        count = recorder.count("audit_project")
        if count != 1:
            failures.append(
                f"audit_project executed {count} times; expected once"
            )

        if not response.strip():
            failures.append(
                "health check produced no response"
            )

        return _result(
            "cap.selfops.health",
            "selfops",
            response,
            failures,
            agent,
            recorder,
            hard_gate=True,
        )
    finally:
        recorder.restore()


CAPABILITY_CASES = (
    case_network_apipa,
    case_network_dns,
    case_network_wifi_evidence,
    case_windows_gpo,
    case_windows_ad_dns,
    case_linux_disk,
    case_linux_502,
    case_fortigate_policy,
    case_fortigate_ipsec,
    case_programming_code_review,
    case_document_creation,
    case_routing_ambiguous,
    case_routing_capability_only,
    case_selfops_health,
)


def _hermetic_state():
    """Every capability run gets empty memory/incident/feedback state."""
    import os
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="razaai-eval-state-"))
    previous = os.environ.get("RAZAAI_STATE_DIR")
    os.environ["RAZAAI_STATE_DIR"] = str(root)
    return previous


def _restore_state(previous):
    import os
    if previous is None:
        os.environ.pop("RAZAAI_STATE_DIR", None)
    else:
        os.environ["RAZAAI_STATE_DIR"] = previous


def run_capability_suite(
    model,
    base_url="http://127.0.0.1:11434",
    seed=3407,
):
    previous = _hermetic_state()
    try:
        return [
            case(
                model=model,
                base_url=base_url,
                seed=seed,
            )
            for case in CAPABILITY_CASES
        ]
    finally:
        _restore_state(previous)


def summarize_capabilities(model, results):
    total = len(results)
    passed = sum(result.passed for result in results)

    hard_failures = [
        result
        for result in results
        if result.hard_gate and not result.passed
    ]

    categories = {}

    for category in sorted({result.category for result in results}):
        subset = [
            result
            for result in results
            if result.category == category
        ]
        good = sum(result.passed for result in subset)

        categories[category] = {
            "passed": good,
            "total": len(subset),
            "score_percent": round(
                100 * good / len(subset),
                1,
            ),
        }

    score = round(
        100 * passed / total,
        1,
    ) if total else 0.0

    capability_ready = (
        not hard_failures
        and score >= 90.0
    )

    return {
        "suite": "RazaAI Step 15.0 Real-World Capability Evaluation",
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": total,
        "score_percent": score,
        "hard_gate_failures": len(hard_failures),
        "capability_ready": capability_ready,
        "categories": categories,
        "results": [
            asdict(result)
            for result in results
        ],
    }


def write_capability_report(
    summary,
    output_dir="output/model-evals",
):
    out = Path(output_dir)
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    slug = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        summary["model"],
    )
    stamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )
    base = out / f"capability-{slug}-{stamp}"

    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")

    json_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# RazaAI Step 15 Capability Evaluation",
        "",
        f"- Model: `{summary['model']}`",
        f"- Score: **{summary['score_percent']}%** "
        f"({summary['passed']}/{summary['total']})",
        f"- Hard failures: **{summary['hard_gate_failures']}**",
        f"- Capability ready: **{'YES' if summary['capability_ready'] else 'NO'}**",
        "",
        "## Categories",
        "",
    ]

    for category, stats in summary["categories"].items():
        lines.append(
            f"- {category}: {stats['score_percent']}% "
            f"({stats['passed']}/{stats['total']})"
        )

    failures = [
        result
        for result in summary["results"]
        if not result["passed"]
    ]

    # Persist capability misses as operational improvement signals.
    # Failure to write feedback must never affect evaluation authority/results.
    if failures:
        try:
            from ..selfops.feedback import ImprovementFeedbackStore
            feedback = ImprovementFeedbackStore()
            for result in failures:
                feedback.record(
                    "capability_failure",
                    topic=f"{result.get('category', 'general')} capability {result.get('case_id', 'unknown')}",
                    domain=str(result.get("category") or "general"),
                    summary="; ".join(str(x) for x in (result.get("failures") or []))[:1600],
                    source="capability_eval",
                    severity="high" if result.get("hard_gate") else "medium",
                    evidence=[
                        f"case={result.get('case_id')}",
                        f"model={summary.get('model')}",
                        f"hard_gate={bool(result.get('hard_gate'))}",
                    ],
                )
        except (OSError, ValueError, ImportError):
            pass

    lines.extend([
        "",
        "## Failures",
        "",
    ])

    if not failures:
        lines.append("No failures.")
    else:
        for result in failures:
            gate = "HARD" if result["hard_gate"] else "soft"
            lines.extend([
                f"### {result['case_id']} ({gate})",
                "",
                f"Response: `{result['response']}`",
                "",
                f"Tools: `{', '.join(result['tool_calls']) or 'none'}`",
                "",
            ])
            for failure in result["failures"]:
                lines.append(f"- {failure}")
            lines.append("")

    md_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return json_path, md_path
