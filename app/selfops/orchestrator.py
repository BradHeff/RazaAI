from __future__ import annotations

import json
import re
from pathlib import Path


class ControlledImprovementOrchestrator:
    """Stage and verify model proposals. Production promotion is deliberately outside this class."""

    def __init__(
        self,
        *,
        tools,
        client,
        project_root,
        context_compactor=None,
        context_window=4096,
        output_reserve=700,
    ):
        self.tools = tools
        self.client = client
        self.project_root = Path(project_root).resolve()
        self.context_compactor = context_compactor
        self.context_window = int(context_window)
        self.output_reserve = int(output_reserve)

    @staticmethod
    def _tool_result(result):
        if not getattr(result, "success", False):
            raise RuntimeError(getattr(result, "error", None) or "tool execution failed")
        return dict(getattr(result, "result", None) or {})

    @staticmethod
    def _extract_json(text):
        value = str(text or "").strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
            value = re.sub(r"\s*```$", "", value)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("Model did not return a JSON improvement plan")
            return json.loads(value[start:end + 1])

    def _raw_evidence(self, investigation, *, max_chars=10500):
        evidence = []
        total = 0
        for item in investigation.get("results") or []:
            rel = Path(str(item.get("file") or ""))
            if (
                not rel.parts
                or rel.is_absolute()
                or ".." in rel.parts
                or rel.parts[0] not in {"app", "scripts", "tests"}
            ):
                continue
            path = (self.project_root / rel).resolve()
            try:
                path.relative_to(self.project_root)
            except ValueError:
                continue
            if not path.is_file():
                continue

            lines = path.read_text(encoding="utf-8").splitlines()
            start = max(1, int(item.get("start_line") or 1))
            end = min(len(lines), int(item.get("end_line") or start + 59))
            raw = "\n".join(lines[start - 1:end])
            remaining = max_chars - total
            if remaining <= 0:
                break
            raw = raw[:remaining]
            total += len(raw)
            evidence.append(
                {
                    "file": rel.as_posix(),
                    "start_line": start,
                    "end_line": end,
                    "content": raw,
                }
            )
        return evidence

    @staticmethod
    def _candidate_tests(investigations):
        modules = []
        for investigation in investigations:
            for item in investigation.get("results") or []:
                rel = Path(str(item.get("file") or ""))
                if (
                    len(rel.parts) >= 2
                    and rel.parts[0] == "tests"
                    and rel.suffix == ".py"
                    and rel.name.startswith("test_")
                ):
                    module = ".".join(rel.with_suffix("").parts)
                    if module not in modules:
                        modules.append(module)
        return modules[:3]

    def _plan(self, topic, improvement_id, evidence):
        allowed_files = [
            item["file"]
            for item in evidence
            if not item["file"].startswith("tests/")
        ]
        if not allowed_files:
            return {"patches": [], "reason": "No editable implementation evidence found."}

        evidence_text = "\n\n".join(
            f"FILE: {item['file']}\n"
            f"LINES: {item['start_line']}-{item['end_line']}\n"
            f"{item['content']}"
            for item in evidence
        )

        system = (
            "You are the code-planning component of RazaAI's controlled "
            "self-improvement sandbox. Return JSON only. You are NOT applying "
            "production changes. Use only exact source evidence supplied below. "
            "Do not alter identity, credential protection, approval boundaries, "
            "web safety, production-promotion controls, or test authority. "
            "Prefer one small evidence-based replacement. "
            "Schema: "
            '{"patches":[{"file":"app/x.py","old_text":"exact contiguous source",'
            '"new_text":"replacement source","rationale":"why"}],"reason":"..."}. '
            "old_text MUST be copied exactly from the supplied file content and "
            "must be specific enough to occur once. new_text must be complete "
            "replacement text for that fragment. At most 2 patches. If the "
            "evidence does not justify a safe improvement, return patches:[]."
        )
        user = (
            f"IMPROVEMENT ID: {improvement_id}\n"
            f"GOAL: {topic}\n"
            f"ALLOWED IMPLEMENTATION FILES: {', '.join(allowed_files)}\n\n"
            f"SOURCE EVIDENCE:\n{evidence_text}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if self.context_compactor is not None:
            messages, _ = self.context_compactor(
                messages,
                tools=None,
                context_window=self.context_window,
                reserve_output_tokens=self.output_reserve,
            )
        result = self.client.chat(messages, tools=None)
        content = ((result or {}).get("message") or {}).get("content") or ""
        return self._extract_json(content)

    def run(self, topic):
        topic = str(topic or "").strip()
        if not topic:
            raise ValueError("Improvement topic is required")

        primary = self._tool_result(
            self.tools.execute(
                "investigate_project_code",
                {"query": topic, "max_files": 3, "context_lines": 70},
            )
        )
        if not primary.get("evidence_found"):
            return {
                "status": "no_evidence",
                "goal": topic,
                "reason": "No project source evidence matched this improvement goal.",
            }

        try:
            tests_investigation = self._tool_result(
                self.tools.execute(
                    "investigate_project_code",
                    {"query": f"{topic} test", "max_files": 3, "context_lines": 50},
                )
            )
        except Exception:
            tests_investigation = {"results": [], "evidence_found": False}

        targeted_tests = self._candidate_tests([primary, tests_investigation])

        started = self._tool_result(
            self.tools.execute(
                "start_self_improvement",
                {"goal": topic, "targeted_tests": targeted_tests},
            )
        )
        improvement_id = started.get("improvement_id")
        if not improvement_id:
            raise RuntimeError("Self-improvement manager returned no improvement ID")

        evidence = self._raw_evidence(primary)
        plan = self._plan(topic, improvement_id, evidence)
        patches = list(plan.get("patches") or [])[:2]

        allowed = {item["file"] for item in evidence if not item["file"].startswith("tests/")}
        staged = []
        failures = []

        for patch in patches:
            file = str(patch.get("file") or "")
            old_text = patch.get("old_text")
            new_text = patch.get("new_text")
            rationale = patch.get("rationale") or "Evidence-based controlled improvement."

            if file not in allowed:
                failures.append(f"Rejected patch outside inspected files: {file}")
                continue
            if not isinstance(old_text, str) or not old_text.strip():
                failures.append(f"Rejected {file}: missing exact old_text")
                continue
            if not isinstance(new_text, str) or not new_text.strip() or new_text == old_text:
                failures.append(f"Rejected {file}: replacement is empty or unchanged")
                continue

            result = self.tools.execute(
                "stage_improvement_patch",
                {
                    "improvement_id": improvement_id,
                    "file": file,
                    "old_text": old_text,
                    "new_text": new_text,
                    "rationale": str(rationale)[:2000],
                    "candidate_test": False,
                },
            )
            if getattr(result, "success", False):
                staged.append(file)
            else:
                failures.append(f"{file}: {getattr(result, 'error', 'stage failed')}")

        if not staged:
            reason = str(
                plan.get("reason")
                or "No evidence-based source change is justified."
            ).strip()
            evidence_refs = [
                f"{item['file']}:{item['start_line']}-{item['end_line']}"
                for item in evidence[:10]
            ]
            status = self._tool_result(
                self.tools.execute(
                    "complete_self_improvement_no_change",
                    {
                        "improvement_id": improvement_id,
                        "reason": reason,
                        "evidence": evidence_refs,
                    },
                )
            )
            status["orchestration_reason"] = reason
            status["orchestration_failures"] = failures
            return status

        verified = self.tools.execute(
            "verify_self_improvement",
            {"improvement_id": improvement_id, "full": True},
        )
        if not getattr(verified, "success", False):
            status = self._tool_result(
                self.tools.execute(
                    "self_improvement_status",
                    {"improvement_id": improvement_id},
                )
            )
            status["orchestration_failures"] = failures + [
                str(getattr(verified, "error", "verification failed"))
            ]
            return status

        status = dict(getattr(verified, "result", None) or {})
        status["orchestration_failures"] = failures
        return status
