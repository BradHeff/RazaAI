from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .improvement import SelfImprovementManager
from .feedback import ImprovementFeedbackStore


@dataclass(frozen=True)
class ImprovementOpportunity:
    opportunity_id: str
    topic: str
    reason: str
    source: str
    score: int
    risk: str
    auto_eligible: bool
    evidence: tuple[str, ...] = ()
    file: str | None = None
    case_id: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


class ImprovementDiscoveryEngine:
    """Read-only evidence discovery for controlled self-improvement."""

    SEVERITY_SCORE = {
        "critical": 100,
        "high": 80,
        "medium": 55,
        "low": 30,
    }

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
        self.audit_dir = self.project_root / "data" / "self_audits"
        self.eval_dir = self.project_root / "output" / "model-evals"
        self.feedback = ImprovementFeedbackStore(self.project_root)

    @staticmethod
    def _opportunity_id(index: int) -> str:
        return f"OPP-{index:02d}"

    @staticmethod
    def _valid_test(module: str) -> bool:
        return bool(
            module.startswith("tests.")
            and all(part.replace("_", "").isalnum() for part in module.split("."))
        )

    def _run_test(self, module: str, timeout: int = 120) -> dict:
        if not self._valid_test(module):
            return {"module": module, "success": False, "invalid": True}
        try:
            proc = subprocess.run(
                [sys.executable, "-m", module],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=min(max(int(timeout), 1), 300),
                env={**os.environ, "PYTHONPATH": str(self.project_root)},
            )
        except subprocess.TimeoutExpired:
            return {"module": module, "success": False, "timeout": True}
        return {
            "module": module,
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-6000:],
            "stderr": proc.stderr[-6000:],
        }

    @staticmethod
    def _load_json(path: Path) -> dict | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _latest_audits(self) -> list[dict]:
        reports = []
        # Keep the newest report for each audit mode so a newer quick audit does
        # not hide a still-relevant full-test result.
        for mode in ("quick", "full"):
            matched = []
            for path in self.audit_dir.glob("AUDIT-*.json"):
                data = self._load_json(path)
                if data and data.get("mode") == mode:
                    matched.append((str(data.get("created_at") or ""), path.name, data))
            if matched:
                reports.append(sorted(matched)[-1][2])
        return reports

    def _latest_capability_eval(self) -> dict | None:
        candidates = []
        for path in self.eval_dir.glob("capability-*.json"):
            data = self._load_json(path)
            if not data:
                continue
            stamp = str(data.get("generated_at") or "")
            candidates.append((stamp, path.name, data))
        return sorted(candidates)[-1][2] if candidates else None

    @staticmethod
    def _test_module_from_check(check: str) -> str | None:
        prefix = "test:"
        if str(check).startswith(prefix):
            return str(check)[len(prefix):]
        return None

    def _audit_opportunities(self) -> list[dict]:
        items = []
        seen = set()
        for report in self._latest_audits():
            audit_id = str(report.get("audit_id") or "unknown")
            for finding in report.get("findings") or []:
                if not isinstance(finding, dict):
                    continue
                check = str(finding.get("check") or "audit")
                module = self._test_module_from_check(check)

                # Persisted test failures are only current evidence if the exact
                # test still fails now. A passing rerun retires the stale finding.
                if module:
                    live = self._run_test(module)
                    if live.get("success"):
                        continue
                    live_summary = (
                        str(live.get("stderr") or "").strip().splitlines()
                        or str(live.get("stdout") or "").strip().splitlines()
                        or [f"{module} still fails"]
                    )[-1]
                else:
                    live_summary = ""

                file = str(finding.get("file") or "").strip() or None
                severity = str(finding.get("severity") or "medium").casefold()
                message = str(finding.get("message") or "Audit finding").strip()
                key = (check, file, message)
                if key in seen:
                    continue
                seen.add(key)

                risk = SelfImprovementManager.classify_risk(file) if file else "medium"
                manual = risk == "protected"
                score = self.SEVERITY_SCORE.get(severity, 50) + (10 if module else 0)
                topic = (
                    f"Fix current regression {module}: {message}"
                    if module
                    else f"Improve {check}: {message}"
                )
                evidence = [f"audit={audit_id}", f"severity={severity}"]
                if file:
                    evidence.append(f"file={file}")
                if live_summary:
                    evidence.append(f"live_test={live_summary[-500:]}")
                items.append({
                    "topic": topic,
                    "reason": (
                        f"Current self-audit evidence reports {check}: {message}."
                        + (" The failing test was revalidated live." if module else "")
                    ),
                    "source": "self_audit",
                    "score": score,
                    "risk": risk,
                    "auto_eligible": not manual,
                    "evidence": tuple(evidence),
                    "file": file,
                    "case_id": module,
                })
        return items

    def _capability_eval_is_stale(self, report: dict) -> bool:
        stamp = str(report.get("generated_at") or "").strip()
        if not stamp:
            return True
        try:
            generated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if generated.tzinfo is None:
                generated = generated.replace(tzinfo=timezone.utc)
        except ValueError:
            return True

        generated_ts = generated.timestamp()
        for root_name in ("app", "scripts", "tests"):
            base = self.project_root / root_name
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                try:
                    if path.stat().st_mtime > generated_ts + 1.0:
                        return True
                except OSError:
                    continue
        return False

    def _capability_opportunities(self) -> list[dict]:
        report = self._latest_capability_eval()
        if not report or self._capability_eval_is_stale(report):
            return []
        results = report.get("results") or []
        items = []
        for result in results:
            if not isinstance(result, dict) or result.get("passed") is not False:
                continue
            case_id = str(result.get("case_id") or "unknown")
            category = str(result.get("category") or "general")
            failures = [str(item) for item in result.get("failures") or [] if str(item).strip()]
            if not failures:
                failures = ["Capability case failed"]
            hard = bool(result.get("hard_gate"))
            score = 95 if hard else 65
            reason = "; ".join(failures[:3])
            items.append({
                "topic": f"Improve {category} capability for {case_id}: {reason}",
                "reason": f"Latest capability evaluation failed {case_id}: {reason}",
                "source": "capability_eval",
                "score": score,
                "risk": "medium",
                "auto_eligible": True,
                "evidence": (
                    f"case={case_id}",
                    f"hard_gate={hard}",
                    f"model={report.get('model', 'unknown')}",
                ),
                "file": None,
                "case_id": case_id,
            })
        return items


    def _signal_opportunities(self) -> list[dict]:
        """Promote only repeated operational weaknesses into discovery results."""
        items = []
        for weakness in self.feedback.aggregate(min_occurrences=2, limit=20):
            # Audit/capability failures already have stronger freshness-aware
            # discovery paths above; keep their persisted signals for history
            # without duplicating the same opportunity here.
            if weakness.get("kind") in {"audit_failure", "capability_failure"}:
                continue
            file = weakness.get("file")
            risk = SelfImprovementManager.classify_risk(file) if file else "medium"
            confidence = str(weakness.get("confidence") or "low")
            occurrences = int(weakness.get("occurrences") or 0)
            kind = str(weakness.get("kind") or "runtime")
            manual = risk == "protected"
            # Repeated evidence earns more weight, but operational signals do not
            # outrank current hard-gate audit/evaluation failures.
            score = min(78, 38 + occurrences * 9 + (8 if confidence == "high" else 0))
            topic = str(weakness.get("topic") or "runtime response quality")
            items.append({
                "topic": f"Improve {topic}",
                "reason": (
                    f"Repeated {kind.replace('_', ' ')} signal observed {occurrences} times "
                    f"(confidence={confidence}). Latest summary: {weakness.get('summary') or 'operational weakness'}"
                ),
                "source": "feedback_signal",
                "score": score,
                "risk": risk,
                "auto_eligible": (not manual and occurrences >= 2),
                "evidence": tuple(
                    [
                        f"kind={kind}",
                        f"occurrences={occurrences}",
                        f"confidence={confidence}",
                        f"first_seen={weakness.get('first_seen')}",
                        f"last_seen={weakness.get('last_seen')}",
                    ]
                    + list(weakness.get("evidence") or [])[:4]
                ),
                "file": file,
                "case_id": weakness.get("fingerprint"),
            })
        return items

    def discover(self, limit: int = 5) -> dict:
        candidates = (
            self._audit_opportunities()
            + self._capability_opportunities()
            + self._signal_opportunities()
        )

        # Deduplicate semantically equivalent opportunities by case/file/topic.
        deduped = []
        seen = set()
        for item in sorted(candidates, key=lambda x: (-int(x["score"]), x["topic"])):
            key = (item.get("case_id"), item.get("file"), item.get("topic"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        opportunities = []
        for index, item in enumerate(deduped[: max(1, min(int(limit), 10))], start=1):
            opportunities.append(
                ImprovementOpportunity(
                    opportunity_id=self._opportunity_id(index),
                    topic=item["topic"],
                    reason=item["reason"],
                    source=item["source"],
                    score=int(item["score"]),
                    risk=item["risk"],
                    auto_eligible=bool(item["auto_eligible"]),
                    evidence=tuple(item.get("evidence") or ()),
                    file=item.get("file"),
                    case_id=item.get("case_id"),
                )
            )

        selected = next((item for item in opportunities if item.auto_eligible), None)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "opportunities": [item.to_dict() for item in opportunities],
            "selected": selected.to_dict() if selected else None,
            "clean": not opportunities,
            "rule": (
                "Only current or repeated operational evidence may trigger automatic improvement. "
                "Protected authority findings are manual-only. A single conversational signal is "
                "insufficient. Discovery never edits source."
            ),
        }
