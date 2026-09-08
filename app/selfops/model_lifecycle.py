from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR


MODEL_ID_RE = re.compile(r"MODEL-\d{8}-\d{6}-\d{6}")


class ModelLifecycleManager:
    """Stage, canary-test, promote and roll back local Ollama GGUF candidates."""

    def __init__(self, project_root=None, runner=None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        self.root = self.project_root / "data" / "model_candidates"
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.runner = runner or self._run

    @staticmethod
    def _id():
        return "MODEL-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    @staticmethod
    def _run(command, cwd):
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3600,
            env=os.environ.copy(),
        )
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }

    def _dir(self, model_id):
        if not MODEL_ID_RE.fullmatch(model_id or ""):
            raise ValueError("Invalid model candidate ID")
        return self.jobs_dir / model_id

    def _path(self, model_id):
        return self._dir(model_id) / "job.json"

    def _write(self, data):
        path = self._path(data["model_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load(self, model_id):
        try:
            return json.loads(self._path(model_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(model_id) from exc

    def _resolve_gguf(self, gguf):
        path = Path(str(gguf))
        if path.is_absolute():
            resolved = path.resolve()
        else:
            if ".." in path.parts:
                raise ValueError("GGUF path may not escape project root")
            resolved = (self.project_root / path).resolve()
            resolved.relative_to(self.project_root)
        if resolved.suffix.lower() != ".gguf" or not resolved.exists():
            raise FileNotFoundError(f"GGUF candidate not found: {resolved}")
        return resolved

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def stage(
        self,
        gguf,
        *,
        active_tag="raza-edge:4b-v3",
        modelfile="Modelfile.raza-edge-v3",
    ):
        gguf_path = self._resolve_gguf(gguf)
        template = (self.project_root / modelfile).resolve()
        template.relative_to(self.project_root)
        if not template.exists():
            raise FileNotFoundError(modelfile)

        model_id = self._id()
        candidate_tag = f"raza-candidate:{model_id.lower().replace('model-', '')}"
        data = {
            "model_id": model_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "staged",
            "gguf": str(gguf_path),
            "sha256": self._sha256(gguf_path),
            "active_tag": active_tag,
            "candidate_tag": candidate_tag,
            "backup_tag": f"{active_tag}-backup-{model_id[-6:].lower()}",
            "modelfile_template": str(template.relative_to(self.project_root)),
            "verification": None,
        }
        self._write(data)
        return data

    def _candidate_modelfile(self, data):
        template = self.project_root / data["modelfile_template"]
        text = template.read_text(encoding="utf-8")
        lines = text.splitlines()
        replaced = False
        for index, line in enumerate(lines):
            if line.strip().upper().startswith("FROM "):
                lines[index] = f'FROM "{data["gguf"]}"'
                replaced = True
                break
        if not replaced:
            lines.insert(0, f'FROM "{data["gguf"]}"')
        output = self._dir(data["model_id"]) / "Candidate.Modelfile"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output

    def verify(self, model_id, *, full=True):
        if os.getenv("RAZAAI_ALLOW_MODEL_RUNTIME_CHANGES") != "1":
            raise PermissionError(
                "Candidate Ollama model creation is disabled. Set "
                "RAZAAI_ALLOW_MODEL_RUNTIME_CHANGES=1 on the evaluation machine."
            )

        data = self._load(model_id)
        modelfile = self._candidate_modelfile(data)
        create = self.runner(
            ["ollama", "create", data["candidate_tag"], "-f", str(modelfile)],
            self.project_root,
        )
        checks = [{"name": "ollama_create_candidate", **create}]

        capability_ready = False
        if create["success"]:
            smoke = self.runner(
                [
                    "ollama", "run", data["candidate_tag"],
                    "Reply with exactly: RazaAI candidate ready",
                ],
                self.project_root,
            )
            checks.append({"name": "ollama_smoke", **smoke})

            if full and smoke["success"]:
                capability = self.runner(
                    [
                        sys.executable if "sys" in globals() else "python3",
                        "-m", "scripts.step15_capability_eval",
                        "--model", data["candidate_tag"],
                        "--run-regressions",
                    ],
                    self.project_root,
                )
                checks.append({"name": "capability_eval", **capability})
                capability_ready = (
                    capability["success"]
                    and "Capability ready:     YES" in capability["stdout"]
                    and "Hard-gate failures:   0" in capability["stdout"]
                    and "Regression failures:  0" in capability["stdout"]
                )
            elif smoke["success"]:
                capability_ready = True

        success = all(item["success"] for item in checks) and capability_ready
        data["verification"] = {
            "success": success,
            "capability_ready": capability_ready,
            "checks": checks,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        data["status"] = "verified" if success else "rejected"
        self._write(data)
        return data

    def promote(self, model_id):
        if os.getenv("RAZAAI_ALLOW_MODEL_RUNTIME_CHANGES") != "1":
            raise PermissionError("Model runtime changes are disabled")
        data = self._load(model_id)
        if data["status"] != "verified" or not data.get("verification", {}).get("capability_ready"):
            raise ValueError("Only a verified capability-ready model can be promoted")

        backup = self.runner(
            ["ollama", "cp", data["active_tag"], data["backup_tag"]],
            self.project_root,
        )
        if not backup["success"]:
            raise RuntimeError(f"Failed to create Ollama rollback tag: {backup['stderr']}")

        promote = self.runner(
            ["ollama", "cp", data["candidate_tag"], data["active_tag"]],
            self.project_root,
        )
        if not promote["success"]:
            self.runner(["ollama", "cp", data["backup_tag"], data["active_tag"]], self.project_root)
            raise RuntimeError(f"Model promotion failed: {promote['stderr']}")

        show = self.runner(["ollama", "show", data["active_tag"]], self.project_root)
        if not show["success"]:
            self.runner(["ollama", "cp", data["backup_tag"], data["active_tag"]], self.project_root)
            raise RuntimeError("Promoted model failed post-promotion verification")

        data["status"] = "promoted"
        data["promoted_at"] = datetime.now(timezone.utc).isoformat()
        data["promotion"] = {"backup": backup, "promote": promote, "show": show}
        self._write(data)
        return data

    def rollback(self, model_id):
        data = self._load(model_id)
        result = self.runner(
            ["ollama", "cp", data["backup_tag"], data["active_tag"]],
            self.project_root,
        )
        if not result["success"]:
            raise RuntimeError(result["stderr"] or "Model rollback failed")
        data["status"] = "rolled_back"
        data["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        return data

    def status(self, model_id=None):
        if model_id:
            return self._load(model_id)
        jobs = []
        for path in sorted(self.jobs_dir.glob("MODEL-*")):
            try:
                jobs.append(self._load(path.name))
            except Exception:
                continue
        return {"jobs": jobs[-20:]}
