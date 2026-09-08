"""Deterministic self-improvement orchestration."""

import json
import tempfile
from pathlib import Path

from app.selfops.orchestrator import ControlledImprovementOrchestrator


class Result:
    def __init__(self, success=True, result=None, error=None):
        self.success = success
        self.result = result
        self.error = error


class FakeTools:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.calls = []
        self.job = {
            "improvement_id": "IMPROVE-20260822-010101-123456",
            "status": "investigating",
            "risk": "low",
            "changed_files": [],
            "targeted_tests": [],
            "candidate_tests": [],
            "verified": False,
            "regressions": 0,
            "verification": None,
        }

    def execute(self, name, arguments=None):
        arguments = dict(arguments or {})
        self.calls.append((name, arguments))

        if name == "investigate_project_code":
            if str(arguments.get("query", "")).endswith(" test"):
                return Result(True, {
                    "evidence_found": True,
                    "results": [{
                        "file": "tests/test_nps.py",
                        "start_line": 1,
                        "end_line": 8,
                    }],
                })
            return Result(True, {
                "evidence_found": True,
                "results": [{
                    "file": "app/nps.py",
                    "start_line": 1,
                    "end_line": 8,
                }],
            })

        if name == "start_self_improvement":
            self.job["targeted_tests"] = list(arguments.get("targeted_tests") or [])
            return Result(True, dict(self.job))

        if name == "stage_improvement_patch":
            path = self.project_root / arguments["file"]
            source = path.read_text(encoding="utf-8")
            old = arguments["old_text"]
            new = arguments["new_text"]
            if source.count(old) != 1:
                return Result(False, error="old_text mismatch")
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            self.job["status"] = "candidate"
            self.job["changed_files"] = [arguments["file"]]
            return Result(True, dict(self.job))

        if name == "verify_self_improvement":
            self.job["status"] = "verified"
            self.job["verified"] = True
            self.job["verification"] = {"success": True, "regressions": 0}
            self.job["regressions"] = 0
            return Result(True, dict(self.job))

        if name == "self_improvement_status":
            return Result(True, dict(self.job))

        raise AssertionError(name)


class FakeClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        assert tools is None
        return {
            "message": {
                "content": json.dumps({
                    "patches": [{
                        "file": "app/nps.py",
                        "old_text": 'MODE = "vlan-first"',
                        "new_text": 'MODE = "evidence-first"',
                        "rationale": "Prefer current NPS evidence before historical VLAN fixes.",
                    }],
                    "reason": "Current source is VLAN-first.",
                })
            }
        }


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.6 Deterministic Improvement")
    print("=" * 76)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app").mkdir()
        (root / "tests").mkdir()
        (root / "app/nps.py").write_text(
            'MODE = "vlan-first"\n',
            encoding="utf-8",
        )
        (root / "tests/test_nps.py").write_text(
            'def main():\n    assert True\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8",
        )

        tools = FakeTools(root)
        client = FakeClient()
        orchestrator = ControlledImprovementOrchestrator(
            tools=tools,
            client=client,
            project_root=root,
            context_window=4096,
            output_reserve=700,
        )
        result = orchestrator.run("NPS EAP WiFi troubleshooting")

        assert result["status"] == "verified"
        assert result["verified"] is True
        assert result["changed_files"] == ["app/nps.py"]
        assert result["targeted_tests"] == ["tests.test_nps"]
        assert (root / "app/nps.py").read_text() == 'MODE = "evidence-first"\n'

        names = [name for name, _ in tools.calls]
        assert names[:3] == [
            "investigate_project_code",
            "investigate_project_code",
            "start_self_improvement",
        ]
        assert "stage_improvement_patch" in names
        assert names[-1] == "verify_self_improvement"
        assert client.calls == 1
        print("[PASS] Python deterministically inspects, creates, stages and verifies")

    source = Path("app/selfops/orchestrator.py").read_text(encoding="utf-8")
    assert "Return JSON only" in source
    assert "old_text MUST be copied exactly" in source
    assert "Do not alter identity" in source
    assert "Production promotion is deliberately outside this class" in source
    print("[PASS] model is limited to structured evidence-based candidate planning")

    print()
    print("=" * 76)
    print("STEP 20.5.6 DETERMINISTIC IMPROVEMENT PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
