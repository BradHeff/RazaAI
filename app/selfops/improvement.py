from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR
from .repair import SelfRepairManager
from .feedback import ImprovementFeedbackStore


IMPROVEMENT_ID_RE = re.compile(r"IMPROVE-\d{8}-\d{6}-\d{6}")


@dataclass(frozen=True)
class ImprovementJob:
    improvement_id: str
    created_at: str
    goal: str
    status: str
    risk: str
    changed_files: tuple[str, ...] = ()
    targeted_tests: tuple[str, ...] = ()
    candidate_tests: tuple[str, ...] = ()
    verified: bool = False
    regressions: int = 0
    notes: str = ""

    def to_dict(self):
        return asdict(self)


class SelfImprovementManager:
    """Sandboxed test -> patch -> verify -> approval -> promote workflow."""

    EDITABLE_ROOTS = ("app", "scripts", "tests")
    TRUSTED_REGRESSION_TESTS = (
        "tests.test_step12_6_live_hardening",
        "tests.test_step15_0_1_capability_hardening",
        "tests.test_step16_4_agent_integration",
        "tests.test_step17_3_memory_authority",
        "tests.test_step17_10_staff_rollout_documents",
    )
    PROTECTED_PREFIXES = (
        "app/agent/",
        "app/interaction/",
        "app/selfops/",
        "app/tools/registry.py",
        "app/tools/memory.py",
        "app/memory/",
        "app/tools/web.py",
        "app/tools/web_grounding.py",
        "app/evaluation/",
        "scripts/step",
    )
    MEDIUM_PREFIXES = (
        "app/documents/",
        "app/knowledge/",
        "app/incidents/",
        "app/playbooks/",
        "app/tools/",
    )

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        self.root = self.project_root / "data" / "self_improvement"
        self.jobs_dir = self.root / "jobs"
        self.history_dir = self.root / "history"
        self.backups_dir = self.root / "backups"
        for path in (self.jobs_dir, self.history_dir, self.backups_dir):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id():
        return "IMPROVE-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    def _job_dir(self, improvement_id):
        if not IMPROVEMENT_ID_RE.fullmatch(improvement_id or ""):
            raise ValueError("Invalid improvement ID")
        return self.jobs_dir / improvement_id

    def _manifest_path(self, improvement_id):
        return self._job_dir(improvement_id) / "job.json"

    def _workspace(self, improvement_id):
        return self._job_dir(improvement_id) / "workspace"

    @staticmethod
    def _valid_test(module):
        return bool(
            module.startswith("tests.")
            and all(part.replace("_", "").isalnum() for part in module.split("."))
        )

    def _copy_workspace(self, destination):
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("app", "scripts", "tests"):
            source = self.project_root / name
            if not source.exists():
                continue
            shutil.copytree(
                source,
                destination / name,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        for name in (
            "requirements.txt",
            "Modelfile.raza-edge-v3",
            "README.md",
            "README_TRAINING.md",
        ):
            source = self.project_root / name
            if source.exists() and source.is_file():
                shutil.copy2(source, destination / name)

    def _write(self, data):
        path = self._manifest_path(data["improvement_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _prune_old_jobs(self, keep: int = 3):
        """Each job copies the whole app/scripts/tests tree; without pruning the jobs directory grows by ~tens of MB per attempt forever. Keeps the newest `keep` finished jobs, never an unfinished one."""
        try:
            jobs = []
            for entry in self.jobs_dir.iterdir():
                if not entry.is_dir() or not IMPROVEMENT_ID_RE.fullmatch(entry.name):
                    continue
                try:
                    manifest = json.loads((entry / "job.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                state = str(manifest.get("state") or "")
                if state not in {"promoted", "rolled_back", "rejected"}:
                    continue
                jobs.append((str(manifest.get("updated_at") or ""), entry))
            jobs.sort()
            for _, entry in jobs[: max(0, len(jobs) - keep)]:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            pass

    def _load(self, improvement_id):
        try:
            return json.loads(self._manifest_path(improvement_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(improvement_id) from exc

    def start(self, goal, targeted_tests=None):
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("Improvement goal is required")
        if len(goal) > 2000:
            raise ValueError("Improvement goal is too long")

        selected = tuple(targeted_tests or ())
        for module in selected:
            if not self._valid_test(module):
                raise ValueError(f"Invalid targeted test: {module}")

        self._prune_old_jobs()
        improvement_id = self._id()
        workspace = self._workspace(improvement_id)
        self._copy_workspace(workspace)
        data = ImprovementJob(
            improvement_id=improvement_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            goal=goal,
            status="investigating",
            risk="low",
            targeted_tests=selected,
        ).to_dict()
        data["patches"] = []
        data["verification"] = None
        data["workspace"] = str(workspace.relative_to(self.project_root))
        self._write(data)
        return data

    def _resolve_workspace_file(self, improvement_id, relative_path, *, allow_new=False):
        rel = Path(str(relative_path))
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError("Only project-relative paths are allowed")
        if rel.parts[0] not in self.EDITABLE_ROOTS:
            raise ValueError("Improvement patches are limited to app/, scripts/, and tests/")

        production = (self.project_root / rel).resolve()
        workspace = (self._workspace(improvement_id) / rel).resolve()
        workspace.relative_to(self._workspace(improvement_id).resolve())

        # Existing trusted tests cannot be weakened. New regression tests are allowed.
        if rel.parts[0] == "tests" and production.exists():
            raise ValueError(
                "Existing regression tests are immutable in autonomous improvement jobs; "
                "add a new test instead."
            )
        if not allow_new and not workspace.exists():
            raise FileNotFoundError(str(rel))
        return rel, production, workspace

    @classmethod
    def classify_risk(cls, relative_path):
        value = Path(relative_path).as_posix()
        if any(value == prefix.rstrip("/") or value.startswith(prefix) for prefix in cls.PROTECTED_PREFIXES):
            return "protected"
        if any(value == prefix.rstrip("/") or value.startswith(prefix) for prefix in cls.MEDIUM_PREFIXES):
            return "medium"
        return "low"

    @staticmethod
    def _risk_max(a, b):
        order = {"low": 0, "medium": 1, "protected": 2}
        return a if order[a] >= order[b] else b

    def stage_patch(
        self,
        improvement_id,
        *,
        file,
        old_text=None,
        new_text,
        rationale,
        candidate_test=False,
    ):
        data = self._load(improvement_id)
        if data["status"] not in {"investigating", "candidate"}:
            raise ValueError(f"Job cannot accept patches in status {data['status']}")

        allow_new = old_text is None
        rel, production, workspace = self._resolve_workspace_file(
            improvement_id, file, allow_new=allow_new
        )
        workspace.parent.mkdir(parents=True, exist_ok=True)

        if allow_new:
            if workspace.exists() or production.exists():
                raise ValueError("New-file patch target already exists")
            if rel.parts[0] == "tests" and not rel.name.startswith("test_"):
                raise ValueError("New autonomous test files must start with test_")
            original = ""
            updated = str(new_text)
        else:
            source = workspace.read_text(encoding="utf-8")
            occurrences = source.count(str(old_text))
            if occurrences != 1:
                raise ValueError(
                    f"old_text must match exactly once in sandbox; found {occurrences}"
                )
            original = str(old_text)
            updated = source.replace(str(old_text), str(new_text), 1)

        if not updated.strip():
            raise ValueError("Patch cannot leave a file empty")

        workspace.write_text(updated, encoding="utf-8")
        risk = self.classify_risk(rel)
        data["risk"] = self._risk_max(data.get("risk", "low"), risk)

        patches = data.setdefault("patches", [])
        patches.append({
            "file": rel.as_posix(),
            "rationale": str(rationale or "").strip()[:4000],
            "risk": risk,
            "new_file": allow_new,
            "old_text": original,
        })

        changed = list(data.get("changed_files") or [])
        if rel.as_posix() not in changed:
            changed.append(rel.as_posix())
        data["changed_files"] = changed

        if candidate_test:
            if rel.parts[0] != "tests" or not rel.name.startswith("test_"):
                raise ValueError("candidate_test requires a new tests/test_*.py file")
            module = ".".join(rel.with_suffix("").parts)
            candidates = list(data.get("candidate_tests") or [])
            if module not in candidates:
                candidates.append(module)
            data["candidate_tests"] = candidates

        data["status"] = "candidate"
        data["verified"] = False
        self._write(data)
        return data

    def _run(self, cwd, module, timeout=300):
        proc = subprocess.run(
            [sys.executable, "-m", module],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(cwd)},
        )
        return {
            "module": module,
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-10000:],
            "stderr": proc.stderr[-10000:],
        }

    def _compile_changed(self, data):
        results = []
        workspace = self._workspace(data["improvement_id"])
        for rel in data.get("changed_files") or []:
            path = workspace / rel
            if path.suffix != ".py":
                results.append({"file": rel, "success": True, "skipped": True})
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )
            results.append({
                "file": rel,
                "success": proc.returncode == 0,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            })
        return results

    def verify(self, improvement_id, *, full=True):
        data = self._load(improvement_id)
        if not data.get("changed_files"):
            raise ValueError("No candidate changes have been staged")

        workspace = self._workspace(improvement_id)
        compile_results = self._compile_changed(data)

        tests = list(data.get("targeted_tests") or [])
        if full:
            for module in self.TRUSTED_REGRESSION_TESTS:
                if module not in tests and (self.project_root / Path(*module.split(".")).with_suffix(".py")).exists():
                    tests.append(module)

        baseline = []
        candidate = []
        for module in tests:
            baseline.append(self._run(self.project_root, module))
            candidate.append(self._run(workspace, module))

        candidate_tests = []
        for module in data.get("candidate_tests") or []:
            candidate_tests.append(self._run(workspace, module))

        regressions = 0
        for before, after in zip(baseline, candidate):
            if before["success"] and not after["success"]:
                regressions += 1

        success = (
            all(item.get("success") for item in compile_results)
            and all(item.get("success") for item in candidate)
            and all(item.get("success") for item in candidate_tests)
            and regressions == 0
        )

        verification = {
            "success": success,
            "compile": compile_results,
            "baseline": baseline,
            "candidate": candidate,
            "candidate_tests": candidate_tests,
            "regressions": regressions,
            "full": bool(full),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        data["verification"] = verification
        data["verified"] = success
        data["regressions"] = regressions
        data["status"] = "verified" if success else "rejected"
        self._write(data)
        return data

    def complete_no_change(self, improvement_id, *, reason, evidence=None):
        """Close an investigating job when evidence justifies no code change."""
        data = self._load(improvement_id)
        if data.get("status") not in {"investigating", "candidate"}:
            raise ValueError(
                f"Job cannot be completed as no-change from status {data.get('status')}"
            )
        if data.get("changed_files"):
            raise ValueError(
                "A job with staged changes cannot be completed as no-change"
            )

        reason = str(reason or "").strip()
        if not reason:
            raise ValueError("No-change completion requires a reason")

        data["status"] = "not_required"
        data["verified"] = False
        data["regressions"] = 0
        data["no_change_reason"] = reason[:4000]
        data["no_change_evidence"] = list(evidence or [])[:20]
        data["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        (self.history_dir / f"{improvement_id}.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return data

    def status(self, improvement_id=None):
        if improvement_id:
            return self._load(improvement_id)
        jobs = []
        for path in sorted(self.jobs_dir.glob("IMPROVE-*")):
            try:
                jobs.append(self._load(path.name))
            except Exception:
                continue
        return {"jobs": jobs[-20:]}

    def promote(self, improvement_id):
        data = self._load(improvement_id)
        if data.get("status") != "verified" or not data.get("verified"):
            raise ValueError("Only a verified improvement candidate can be promoted")

        backup_root = self.backups_dir / improvement_id
        workspace = self._workspace(improvement_id)
        applied = []

        try:
            for rel_text in data.get("changed_files") or []:
                rel = Path(rel_text)
                source = workspace / rel
                target = self.project_root / rel
                backup = backup_root / rel
                backup.parent.mkdir(parents=True, exist_ok=True)

                if target.exists():
                    shutil.copy2(target, backup)
                else:
                    backup.write_text("__RAZAAI_NEW_FILE__\n", encoding="utf-8")

                target.parent.mkdir(parents=True, exist_ok=True)
                fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
                os.close(fd)
                shutil.copy2(source, temp_name)
                os.replace(temp_name, target)

                # Remove stale bytecode before post-promotion verification.
                # Same-length edits inside one filesystem timestamp window can
                # otherwise cause Python to import a pre-patch .pyc.
                pycache = target.parent / "__pycache__"
                if pycache.exists():
                    shutil.rmtree(pycache, ignore_errors=True)

                applied.append(rel_text)

            # Post-apply trusted verification. This uses production files now.
            post = []
            modules = list(data.get("targeted_tests") or [])
            for module in self.TRUSTED_REGRESSION_TESTS:
                test_path = self.project_root / Path(*module.split(".")).with_suffix(".py")
                if module not in modules and test_path.exists():
                    modules.append(module)
            for module in modules:
                post.append(self._run(self.project_root, module))

            if not all(item["success"] for item in post):
                raise RuntimeError("Post-promotion regression verification failed")

            data["status"] = "promoted"
            data["promoted_at"] = datetime.now(timezone.utc).isoformat()
            data["post_promotion_tests"] = post
            self._write(data)
            (self.history_dir / f"{improvement_id}.json").write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            try:
                ImprovementFeedbackStore(self.project_root).record_promotion(data)
            except (OSError, ValueError):
                # Feedback measurement must never invalidate a successful promotion.
                pass
            return data

        except Exception:
            for rel_text in reversed(applied):
                rel = Path(rel_text)
                target = self.project_root / rel
                backup = backup_root / rel
                if backup.exists():
                    marker = backup.read_text(encoding="utf-8", errors="ignore") if backup.stat().st_size < 64 else ""
                    if marker == "__RAZAAI_NEW_FILE__\n":
                        target.unlink(missing_ok=True)
                    else:
                        shutil.copy2(backup, target)
            data["status"] = "rolled_back"
            data["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
            self._write(data)
            raise

    def rollback(self, improvement_id):
        data = self._load(improvement_id)
        backup_root = self.backups_dir / improvement_id
        if not backup_root.exists():
            raise FileNotFoundError("No production backup exists for this improvement")
        for rel_text in data.get("changed_files") or []:
            rel = Path(rel_text)
            backup = backup_root / rel
            target = self.project_root / rel
            if not backup.exists():
                continue
            marker = backup.read_text(encoding="utf-8", errors="ignore") if backup.stat().st_size < 64 else ""
            if marker == "__RAZAAI_NEW_FILE__\n":
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
        data["status"] = "rolled_back"
        data["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        return data
