from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR, OLLAMA_HOST, OLLAMA_MODEL
from ..memory import MemoryStore


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    check: str
    message: str
    file: str | None = None
    function: str | None = None
    line: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    audit_id: str
    created_at: str
    mode: str
    status: str
    passed: int
    failed: int
    checks: tuple[dict, ...]
    findings: tuple[AuditFinding, ...]
    model: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["findings"] = [item.to_dict() for item in self.findings]
        return data


class SelfAuditEngine:
    """Read-only RazaAI project audit."""

    DEFAULT_FULL_TESTS = (
        "tests.test_step10_5_edge_routing",
        "tests.test_step10_5_1_single_execution",
        "tests.test_step11_7_end_to_end",
    )

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        self.audit_dir = self.project_root / "data" / "self_audits"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id(now: datetime) -> str:
        return "AUDIT-" + now.strftime("%Y%m%d-%H%M%S-%f")

    def _python_files(self) -> list[Path]:
        files = []
        for directory in ("app", "scripts", "tests"):
            base = self.project_root / directory
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                if "__pycache__" not in path.parts:
                    files.append(path)
        return sorted(files)

    @staticmethod
    def _symbol_for_line(path: Path, line: int | None) -> str | None:
        if not line:
            return None
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        best = None
        best_span = None
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", start)
            if start is None or end is None or not (start <= line <= end):
                continue
            span = end - start
            if best_span is None or span < best_span:
                best_span = span
                best = node.name
        return best

    def _compile_check(self) -> tuple[dict, list[AuditFinding]]:
        failures = []
        count = 0

        for path in self._python_files():
            count += 1
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, str(path), "exec")
            except SyntaxError as exc:
                rel = str(path.relative_to(self.project_root))
                failures.append(
                    AuditFinding(
                        severity="critical",
                        check="python_compile",
                        message=exc.msg,
                        file=rel,
                        function=self._symbol_for_line(path, exc.lineno),
                        line=exc.lineno,
                    )
                )
            except (OSError, UnicodeError) as exc:
                rel = str(path.relative_to(self.project_root))
                failures.append(
                    AuditFinding(
                        severity="high",
                        check="python_compile",
                        message=str(exc),
                        file=rel,
                    )
                )

        return {
            "name": "python_compile",
            "success": not failures,
            "files_checked": count,
        }, failures

    def _structure_check(self) -> tuple[dict, list[AuditFinding]]:
        required = (
            "app/agent/agent.py",
            "app/tools/registry.py",
            "app/ollama_client.py",
            "app/incidents/store.py",
            "app/memory/store.py",
            "app/memory/manager.py",
        )
        missing = [
            item for item in required if not (self.project_root / item).is_file()
        ]
        findings = [
            AuditFinding(
                severity="critical",
                check="project_structure",
                message="Required RazaAI project file is missing.",
                file=item,
            )
            for item in missing
        ]
        return {
            "name": "project_structure",
            "success": not missing,
            "required_files": len(required),
        }, findings

    def _ast_check(self) -> tuple[dict, list[AuditFinding]]:
        failures = []
        count = 0
        for path in self._python_files():
            count += 1
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:

                pass
            except (OSError, UnicodeError) as exc:
                failures.append(
                    AuditFinding(
                        severity="medium",
                        check="ast_parse",
                        message=str(exc),
                        file=str(path.relative_to(self.project_root)),
                    )
                )

        return {
            "name": "ast_parse",
            "success": not failures,
            "files_checked": count,
        }, failures

    def _memory_check(self) -> tuple[dict, list[AuditFinding]]:
        """Validate the persistent memory store without modifying it."""
        store = MemoryStore(self.project_root / "data" / "memory")

        try:
            records = store.records(include_inactive=True)
        except (OSError, ValueError) as exc:
            return {
                "name": "persistent_memory",
                "success": False,
                "records": None,
            }, [
                AuditFinding(
                    severity="high",
                    check="persistent_memory",
                    message=str(exc),
                    file="data/memory/memories.json",
                )
            ]

        review = sum(1 for item in records if item.state == "review")
        active = sum(1 for item in records if item.state == "active")

        return {
            "name": "persistent_memory",
            "success": True,
            "records": len(records),
            "active": active,
            "review": review,
        }, []

    def _ollama_check(self) -> tuple[dict, list[AuditFinding]]:
        request = urllib.request.Request(
            OLLAMA_HOST.rstrip("/") + "/api/tags",
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = {
                item.get("name") or item.get("model")
                for item in payload.get("models", [])
                if isinstance(item, dict)
            }
            available = OLLAMA_MODEL in models or any(
                str(name).split(":")[0] == OLLAMA_MODEL.split(":")[0]
                for name in models
                if name
            )
            findings = []
            if not available:
                findings.append(
                    AuditFinding(
                        severity="high",
                        check="ollama_model",
                        message=(
                            f"Ollama is reachable but configured model "
                            f"{OLLAMA_MODEL!r} was not listed."
                        ),
                        file="app/config.py",
                    )
                )
            return {
                "name": "ollama_model",
                "success": available,
                "reachable": True,
                "configured_model": OLLAMA_MODEL,
            }, findings
        except Exception as exc:
            return {
                "name": "ollama_model",
                "success": False,
                "reachable": False,
                "configured_model": OLLAMA_MODEL,
            }, [
                AuditFinding(
                    severity="high",
                    check="ollama_model",
                    message=f"Unable to verify Ollama/model: {exc}",
                    file="app/config.py",
                )
            ]

    @staticmethod
    def _valid_test_module(module: str) -> bool:
        return bool(
            module
            and module.startswith("tests.")
            and all(part.replace("_", "").isalnum() for part in module.split("."))
        )

    def run_test_module(self, module: str, timeout: int = 120) -> dict:
        if not self._valid_test_module(module):
            raise ValueError("Only Python test modules under tests.* are allowed.")

        proc = subprocess.run(
            [sys.executable, "-m", module],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=min(max(int(timeout), 1), 300),
            env={**os.environ, "PYTHONPATH": str(self.project_root)},
        )
        return {
            "module": module,
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }

    def _test_checks(self, modules) -> tuple[list[dict], list[AuditFinding]]:
        checks = []
        findings = []
        for module in modules:
            result = self.run_test_module(module)
            checks.append(
                {
                    "name": f"test:{module}",
                    "success": result["success"],
                    "exit_code": result["exit_code"],
                }
            )
            if not result["success"]:
                raw = (
                    result["stderr"].strip()
                    or result["stdout"].strip()
                    or f"{module} exited with {result['exit_code']}"
                )

                file = None
                function = None
                line = None
                frames = re.findall(
                    r'File "([^"]+)", line (\d+), in ([^\n]+)',
                    raw,
                )
                for frame_file, frame_line, frame_function in frames:
                    try:
                        frame_path = Path(frame_file).resolve()
                        relative = frame_path.relative_to(self.project_root)
                    except (OSError, ValueError):
                        continue
                    file = str(relative)
                    line = int(frame_line)
                    function = frame_function.strip()

                nonempty = [item.strip() for item in raw.splitlines() if item.strip()]
                summary = nonempty[-1] if nonempty else f"{module} failed"
                if len(summary) > 1000:
                    summary = summary[-1000:]

                findings.append(
                    AuditFinding(
                        severity="high",
                        check=f"test:{module}",
                        message=summary,
                        file=file,
                        function=function,
                        line=line,
                    )
                )
        return checks, findings

    def run(
        self,
        *,
        mode: str = "quick",
        check_ollama: bool = True,
        tests: list[str] | None = None,
    ) -> AuditReport:
        if mode not in {"quick", "full"}:
            raise ValueError("Audit mode must be 'quick' or 'full'.")

        now = datetime.now(timezone.utc)
        checks = []
        findings = []

        for check in (
            self._structure_check,
            self._compile_check,
            self._ast_check,
            self._memory_check,
        ):
            result, new_findings = check()
            checks.append(result)
            findings.extend(new_findings)

        if check_ollama:
            result, new_findings = self._ollama_check()
            checks.append(result)
            findings.extend(new_findings)

        modules = []
        if tests is not None:
            modules = list(tests)
        elif mode == "full":
            modules = [
                module
                for module in self.DEFAULT_FULL_TESTS
                if (self.project_root / (module.replace(".", "/") + ".py")).exists()
            ]

        if modules:
            test_checks, test_findings = self._test_checks(modules)
            checks.extend(test_checks)
            findings.extend(test_findings)

        failed = sum(1 for item in checks if not item.get("success"))
        status = "healthy" if failed == 0 else "degraded"

        report = AuditReport(
            audit_id=self._id(now),
            created_at=now.isoformat(),
            mode=mode,
            status=status,
            passed=len(checks) - failed,
            failed=failed,
            checks=tuple(checks),
            findings=tuple(findings),
            model=OLLAMA_MODEL,
        )

        path = self.audit_dir / f"{report.audit_id}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report

    def latest(self) -> dict | None:
        reports = sorted(self.audit_dir.glob("AUDIT-*.json"))
        if not reports:
            return None
        try:
            return json.loads(reports[-1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
