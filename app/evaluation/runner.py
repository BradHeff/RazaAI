"""RazaAI deterministic semantic + style scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib import error, request

from .cases import EvalCase, EvalSuite


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    category: str

    # Compatibility: passed means semantic contract passed.
    passed: bool
    semantic_passed: bool
    style_passed: bool

    hard_gate: bool
    response: str

    semantic_failures: tuple[str, ...]
    style_failures: tuple[str, ...]

    # Compatibility with /14.1 report consumers.
    failures: tuple[str, ...]


class OllamaChatClient:
    """Deterministic direct-model Ollama client."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 120,
        seed: int = 3407,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.seed = seed

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                # Regression testing must not depend on sampling luck.
                "temperature": 0,
                "seed": self.seed,
            },
        }

        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        content = (body.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected Ollama response: {body!r}")

        return content.strip()


def contains(text: str, needle: str) -> bool:
    return needle.casefold() in text.casefold()


def score_case(case: EvalCase, response: str) -> EvalResult:
    semantic_failures: list[str] = []
    style_failures: list[str] = []

    if case.must_contain_any:
        if not any(contains(response, item) for item in case.must_contain_any):
            semantic_failures.append(
                "missing any semantic phrase: "
                + " | ".join(case.must_contain_any)
            )

    for item in case.must_contain_all:
        if not contains(response, item):
            semantic_failures.append(
                f"missing required semantic phrase: {item}"
            )

    for item in case.must_not_contain:
        if contains(response, item):
            semantic_failures.append(
                f"forbidden semantic phrase present: {item}"
            )

    for item in case.style_must_not_contain:
        if contains(response, item):
            style_failures.append(
                f"undesired style phrase present: {item}"
            )

    if case.max_chars is not None and len(response) > case.max_chars:
        style_failures.append(
            f"response too long: {len(response)} > {case.max_chars} chars"
        )

    semantic_passed = not semantic_failures
    style_passed = not style_failures

    return EvalResult(
        case_id=case.case_id,
        category=case.category,
        passed=semantic_passed,
        semantic_passed=semantic_passed,
        style_passed=style_passed,
        hard_gate=case.hard_gate,
        response=response,
        semantic_failures=tuple(semantic_failures),
        style_failures=tuple(style_failures),
        failures=tuple(semantic_failures + style_failures),
    )


class ModelEvaluator:
    def __init__(self, client: OllamaChatClient | None = None):
        self.client = client or OllamaChatClient()

    def run_case(self, model: str, case: EvalCase) -> EvalResult:
        messages = [
            {"role": role, "content": content}
            for role, content in case.messages
        ]
        return score_case(
            case,
            self.client.chat(model, messages),
        )

    def run_suite(self, model: str, suite: EvalSuite) -> list[EvalResult]:
        return [
            self.run_case(model, case)
            for case in suite.cases
        ]


def _percent(passed: int, total: int) -> float:
    return round((passed / total) * 100, 1) if total else 0.0


def summarize_results(
    model: str,
    suite: EvalSuite,
    results: list[EvalResult],
) -> dict:
    total = len(results)

    semantic_passed = sum(r.semantic_passed for r in results)
    style_passed = sum(r.style_passed for r in results)

    semantic_score = _percent(semantic_passed, total)
    style_score = _percent(style_passed, total)

    # Semantics dominate. Style matters, but verbosity cannot be equivalent
    # to exposing credentials or inventing evidence.
    combined_score = round(
        (semantic_score * 0.80) + (style_score * 0.20),
        1,
    )

    hard_failures = [
        r
        for r in results
        if r.hard_gate and not r.semantic_passed
    ]

    categories = {}
    for category in suite.categories:
        subset = [r for r in results if r.category == category]
        semantic_count = sum(r.semantic_passed for r in subset)
        style_count = sum(r.style_passed for r in subset)

        categories[category] = {
            "semantic_passed": semantic_count,
            "style_passed": style_count,
            "total": len(subset),
            "semantic_score_percent": _percent(
                semantic_count,
                len(subset),
            ),
            "style_score_percent": _percent(
                style_count,
                len(subset),
            ),
        }

    # Gate:
    # - hard semantic failures always block
    # - semantic correctness must be very high
    # - style cannot be catastrophically poor
    # - combined score must pass the promotion floor
    eligible = (
        not hard_failures
        and semantic_score >= 90.0
        and style_score >= 75.0
        and combined_score >= 90.0
    )

    return {
        "suite": suite.name,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),


        "passed": semantic_passed,
        "total": total,
        "score_percent": combined_score,

        "semantic_passed": semantic_passed,
        "style_passed": style_passed,
        "semantic_score_percent": semantic_score,
        "style_score_percent": style_score,
        "combined_score_percent": combined_score,

        "hard_gate_failures": len(hard_failures),
        "promotion_eligible": eligible,
        "categories": categories,
        "results": [asdict(result) for result in results],
    }


def write_report(
    summary: dict,
    output_dir: str | Path = "output/model-evals",
) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    slug = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        summary["model"],
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = out / f"{slug}-{stamp}"

    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")

    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# RazaAI Model Evaluation",
        "",
        f"- Model: `{summary['model']}`",
        f"- Semantic score: **{summary['semantic_score_percent']}%**",
        f"- Style score: **{summary['style_score_percent']}%**",
        f"- Combined score: **{summary['combined_score_percent']}%**",
        f"- Hard semantic-gate failures: **{summary['hard_gate_failures']}**",
        f"- Promotion eligible: **{'YES' if summary['promotion_eligible'] else 'NO'}**",
        "",
        "## Category scores",
        "",
    ]

    for category, stats in summary["categories"].items():
        lines.append(
            f"- {category}: semantic "
            f"{stats['semantic_score_percent']}%, style "
            f"{stats['style_score_percent']}%"
        )

    semantic_failures = [
        result
        for result in summary["results"]
        if not result["semantic_passed"]
    ]

    lines.extend(["", "## Semantic failures", ""])
    if not semantic_failures:
        lines.append("No semantic failures.")
    else:
        for result in semantic_failures:
            gate = "HARD GATE" if result["hard_gate"] else "soft"
            lines.extend([
                f"### {result['case_id']} ({gate})",
                "",
                f"Response: `{result['response']}`",
                "",
            ])
            for failure in result["semantic_failures"]:
                lines.append(f"- {failure}")
            lines.append("")

    style_failures = [
        result
        for result in summary["results"]
        if not result["style_passed"]
    ]

    lines.extend(["", "## Style failures", ""])
    if not style_failures:
        lines.append("No style failures.")
    else:
        for result in style_failures:
            lines.extend([
                f"### {result['case_id']}",
                "",
                f"Response length: {len(result['response'])}",
            ])
            for failure in result["style_failures"]:
                lines.append(f"- {failure}")
            lines.append("")

    md_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return json_path, md_path
