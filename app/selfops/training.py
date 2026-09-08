from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR


TRAINING_ID_RE = re.compile(r"TRAIN-\d{8}-\d{6}-\d{6}")


_SECRET_VALUE_PATTERNS = (
    re.compile(r"\b(?:password|passphrase|credential)\s*(?:is|=|:)\s*(?!<redacted>|example\b)\S+", re.I),
    re.compile(r"\b(?:api[ _-]?key|access[ _-]?token|refresh[ _-]?token|secret)\s*(?:is|=|:)\s*\S+", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)

def _contains_secret_value(text):
    return any(pattern.search(str(text or "")) for pattern in _SECRET_VALUE_PATTERNS)


@dataclass(frozen=True)
class TrainingJob:
    training_id: str
    created_at: str
    goal: str
    status: str
    base_model: str
    dataset: str | None
    epochs: float
    max_seq: int
    batch_size: int
    grad_accum: int
    learning_rate: float

    def to_dict(self):
        return asdict(self)


TRAINING_SYSTEM = (
    "You are RazaAI. Brad Heffernan created RazaAI. "
    "Be concise, technically precise, evidence-first, and never invent tool results."
)

class ModelTrainingManager:
    """Manage approved jobs for an explicitly configured external trainer."""

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        self.root = self.project_root / "data" / "model_training"
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id():
        return "TRAIN-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    def _dir(self, training_id):
        if not TRAINING_ID_RE.fullmatch(training_id or ""):
            raise ValueError("Invalid training ID")
        return self.jobs_dir / training_id

    def _path(self, training_id):
        return self._dir(training_id) / "job.json"

    def _load(self, training_id):
        try:
            return json.loads(self._path(training_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(training_id) from exc

    def _write(self, data):
        path = self._path(data["training_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _resolve_dataset(self, value):
        if not value:
            return None
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Training dataset must be project-relative")
        resolved = (self.project_root / path).resolve()
        resolved.relative_to(self.project_root)
        if resolved.suffix.lower() != ".jsonl":
            raise ValueError("Training dataset must be JSONL")
        if not resolved.exists():
            raise FileNotFoundError(str(path))
        return path.as_posix()

    def prepare(
        self,
        goal,
        dataset=None,
        base_model="MassivDash/Qwen3-4B-heretic",
        epochs=4.0,
        max_seq=2048,
        batch_size=1,
        grad_accum=2,
        learning_rate=5e-5,
    ):
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("Training goal is required")
        dataset = self._resolve_dataset(dataset)

        training_id = self._id()
        data = TrainingJob(
            training_id=training_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            goal=goal,
            status="prepared",
            base_model=str(base_model),
            dataset=dataset,
            epochs=float(epochs),
            max_seq=int(max_seq),
            batch_size=int(batch_size),
            grad_accum=int(grad_accum),
            learning_rate=float(learning_rate),
        ).to_dict()
        data["candidate_examples"] = []
        data["output_dir"] = f"data/model_training/jobs/{training_id}/output"
        self._write(data)
        return data

    def add_example(self, training_id, messages):
        data = self._load(training_id)
        if data["status"] not in {"prepared", "dataset_ready"}:
            raise ValueError(f"Training job cannot accept examples in {data['status']}")

        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError("Training example requires at least user and assistant messages")
        messages = list(messages)
        if messages and str(messages[0].get("role") or "") != "system":
            messages.insert(0, {"role": "system", "content": TRAINING_SYSTEM})
        clean = []
        for item in messages:
            if not isinstance(item, dict):
                raise ValueError("Each message must be an object")
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role not in {"system", "user", "assistant"} or not content:
                raise ValueError("Training messages require valid role/content")
            if _contains_secret_value(content):
                raise ValueError("Secrets/credentials cannot be added to autonomous training data")
            clean.append({"role": role, "content": content[:8000]})

        if not any(item["role"] == "assistant" for item in clean):
            raise ValueError("Training example requires an assistant target")

        data.setdefault("candidate_examples", []).append({"messages": clean})
        data["status"] = "dataset_ready"
        self._write(data)
        return data

    def _combined_dataset(self, data):
        job_dir = self._dir(data["training_id"])
        output = job_dir / "combined_training.jsonl"
        rows = []
        if data.get("dataset"):
            source = self.project_root / data["dataset"]
            rows.extend(
                line.rstrip("\n")
                for line in source.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        rows.extend(json.dumps(item, ensure_ascii=False) for item in data.get("candidate_examples") or [])
        if not rows:
            raise ValueError("Training job has no base dataset or candidate examples")
        output.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return output

    def _trainer_script(self):
        configured = os.getenv("RAZAAI_TRAINER_SCRIPT", "").strip()
        if not configured:
            raise FileNotFoundError(
                "Training scripts are maintained separately. Set RAZAAI_TRAINER_SCRIPT "
                "to a compatible trainer on the dedicated training machine."
            )
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        path = path.resolve()
        if not path.is_file() or path.suffix != ".py":
            raise FileNotFoundError("RAZAAI_TRAINER_SCRIPT must name an existing Python trainer")
        return path

    def run(self, training_id):
        if os.getenv("RAZAAI_ALLOW_MODEL_TRAINING") != "1":
            raise PermissionError(
                "Model training is disabled. Set RAZAAI_ALLOW_MODEL_TRAINING=1 "
                "on the dedicated training machine before approving this job."
            )
        if platform.machine().lower() in {"aarch64", "arm64"} and os.getenv("RAZAAI_ALLOW_EDGE_TRAINING") != "1":
            raise PermissionError(
                "Training on ARM/Jetson is blocked by default. Use a CUDA training "
                "workstation or explicitly set RAZAAI_ALLOW_EDGE_TRAINING=1."
            )

        data = self._load(training_id)
        if data["status"] not in {"prepared", "dataset_ready", "failed"}:
            raise ValueError(f"Training job cannot run in status {data['status']}")

        dataset = self._combined_dataset(data)
        trainer = self._trainer_script()
        output_dir = self._dir(training_id) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        adapter_dir = output_dir / "adapter"
        gguf_dir = output_dir / "gguf"
        checkpoints = output_dir / "checkpoints"
        command = [
            os.getenv("RAZAAI_TRAINER_PYTHON") or sys.executable,
            str(trainer),
            "--base", str(data["base_model"]),
            "--data", str(dataset),
            "--epochs", str(data["epochs"]),
            "--max-seq", str(data["max_seq"]),
            "--batch-size", str(data["batch_size"]),
            "--grad-accum", str(data["grad_accum"]),
            "--learning-rate", str(data["learning_rate"]),
            "--warmup-steps", "12",
            "--lora-r", "16",
            "--lora-alpha", "32",
            "--seed", "3407",
            "--outdir", str(checkpoints),
            "--adapter-dir", str(adapter_dir),
            "--gguf-dir", str(gguf_dir),
            "--quant", "q4_k_m",
            "--ollama-model", f"raza-candidate:{training_id.lower()}",
        ]
        data["command"] = command
        data["status"] = "running"
        self._write(data)

        log_path = self._dir(training_id) / "training.log"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                command,
                cwd=self.project_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
            )

        artifacts = []
        for path in sorted(output_dir.rglob("*.gguf")):
            artifacts.append(path.relative_to(self.project_root).as_posix())
        data["exit_code"] = proc.returncode
        data["log"] = str(log_path.relative_to(self.project_root))
        data["gguf_candidates"] = artifacts[-20:]
        data["status"] = "trained" if proc.returncode == 0 else "failed"
        data["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        return data

    def status(self, training_id=None):
        if training_id:
            return self._load(training_id)
        jobs = []
        for path in sorted(self.jobs_dir.glob("TRAIN-*")):
            try:
                jobs.append(self._load(path.name))
            except Exception:
                continue
        return {"jobs": jobs[-20:]}
