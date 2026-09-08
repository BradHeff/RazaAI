from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import BASE_DIR

PATCH_ID_RE = re.compile(r"PATCH-\d{8}-\d{6}-\d{6}")


@dataclass(frozen=True)
class PatchProposal:
    patch_id: str
    created_at: str
    file: str
    rationale: str
    old_text: str
    new_text: str
    tests: tuple[str, ...]
    status: str = "proposed"

    def to_dict(self) -> dict:
        return asdict(self)


class SelfRepairManager:
    """Guarded self-repair for RazaAI."""

    EDITABLE_ROOTS = ("app", "scripts", "tests")
    PROTECTED_NAMES = {
        ".env",
        "Modelfile",
        "Modelfile.edge",
    }

    # These files implement the authority boundary for self-modification.
    # RazaAI may inspect them, but it cannot rewrite its own approval gate.
    PROTECTED_RELATIVE_FILES = {
        "app/selfops/repair.py",
        "app/tools/selfops.py",
        "app/tools/registry.py",
        "app/agent/edge_router.py",
        "app/interaction/router.py",
        "app/selfops/files.py",
        "app/tools/project_files.py",
        "app/config.py",
        "app/memory/store.py",
        "app/memory/manager.py",
        "app/tools/memory.py",
        "app/selfops/improvement.py",
        "app/selfops/training.py",
        "app/selfops/model_lifecycle.py",
        "app/tools/improvement.py",
        "app/context/curated.py",
    }

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root or BASE_DIR).resolve()
        self.state_root = self.project_root / "data" / "self_repairs"
        self.proposals_dir = self.state_root / "proposals"
        self.backups_dir = self.state_root / "backups"
        self.history_dir = self.state_root / "history"

        for path in (
            self.proposals_dir,
            self.backups_dir,
            self.history_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _patch_id() -> str:
        now = datetime.now(timezone.utc)
        return "PATCH-" + now.strftime("%Y%m%d-%H%M%S-%f")

    def _resolve_editable(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("A project-relative file path is required.")

        rel = Path(relative_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Only project-relative paths are allowed.")
        if not rel.parts or rel.parts[0] not in self.EDITABLE_ROOTS:
            raise ValueError("Self-repair is limited to app/, scripts/, and tests/.")
        if rel.name in self.PROTECTED_NAMES:
            raise ValueError(f"Protected file cannot be modified: {rel.name}")

        normalised_rel = rel.as_posix()
        if normalised_rel in self.PROTECTED_RELATIVE_FILES:
            raise ValueError(
                f"Self-repair authority file requires manual maintenance: "
                f"{normalised_rel}"
            )

        path = (self.project_root / rel).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("Path escapes the RazaAI project root.") from exc

        if path.is_symlink():
            raise ValueError("Self-repair will not modify symlinked files.")
        if path.exists() and not path.is_file():
            raise ValueError("Target must be a regular file.")
        return path

    @staticmethod
    def _valid_test(module: str) -> bool:
        return bool(
            module.startswith("tests.")
            and all(part.replace("_", "").isalnum() for part in module.split("."))
        )

    def inspect(
        self, relative_path: str, start_line: int = 1, end_line: int = 240
    ) -> dict:
        path = self._resolve_editable(relative_path)
        if not path.exists():
            raise FileNotFoundError(relative_path)

        start = max(1, int(start_line))
        end = min(max(start, int(end_line)), start + 399)
        lines = path.read_text(encoding="utf-8").splitlines()

        numbered = [
            f"{number}: {lines[number - 1]}"
            for number in range(start, min(end, len(lines)) + 1)
        ]
        return {
            "file": str(path.relative_to(self.project_root)),
            "start_line": start,
            "end_line": min(end, len(lines)),
            "content": "\n".join(numbered),
        }

    def search(self, query: str, max_results: int = 20) -> dict:
        if not query or len(query) > 200:
            raise ValueError("Search query must be 1-200 characters.")

        results = []
        needle = query.lower()
        for root_name in self.EDITABLE_ROOTS:
            base = self.project_root / root_name
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeError):
                    continue
                for number, line in enumerate(lines, start=1):
                    if needle in line.lower():
                        results.append(
                            {
                                "file": str(path.relative_to(self.project_root)),
                                "line": number,
                                "text": line.strip()[:500],
                            }
                        )
                        if len(results) >= min(max(int(max_results), 1), 50):
                            return {"query": query, "results": results}
        return {"query": query, "results": results}

    def investigate(
        self,
        query: str,
        max_files: int = 3,
        context_lines: int = 100,
    ) -> dict:
        """Locate and inspect a project area from a natural-language query."""
        if not query or len(query) > 500:
            raise ValueError("Investigation query must be 1-500 characters.")

        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "can",
            "code",
            "could",
            "do",
            "for",
            "i",
            "improve",
            "inspect",
            "into",
            "it",
            "me",
            "my",
            "of",
            "please",
            "project",
            "razaai",
            "review",
            "source",
            "tell",
            "the",
            "to",
            "whether",
            "you",
            "your",
            "analyse",
            "analyze",
            "better",
            "refactor",
            "smarter",
            "make",
        }
        raw_tokens = re.findall(r"[a-zA-Z0-9_]+", query.lower())
        tokens = []
        for token in raw_tokens:
            if len(token) < 3 or token in stopwords:
                continue

            variants = {token}
            if token.endswith("s") and len(token) > 4:
                variants.add(token[:-1])
            if token.endswith("al") and len(token) > 5:
                variants.add(token[:-2])
            if token.endswith("er") and len(token) > 5:
                variants.add(token[:-2])
            tokens.extend(sorted(variants))

        tokens = list(dict.fromkeys(tokens))
        if not tokens:
            raise ValueError(
                "Investigation query did not contain searchable project terms."
            )

        candidates = []
        for root_name in self.EDITABLE_ROOTS:
            base = self.project_root / root_name
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue

                rel = str(path.relative_to(self.project_root))
                path_lower = rel.lower()
                text_lower = text.lower()

                score = (
                    10 if root_name == "app" else (4 if root_name == "scripts" else 0)
                )
                matched = []
                line_hits = []

                lines = text.splitlines()
                for token in tokens:
                    token_score = 0
                    if token in path_lower:
                        token_score += 12
                    occurrences = text_lower.count(token)
                    if occurrences:
                        token_score += min(occurrences, 8)
                        for number, line in enumerate(lines, start=1):
                            if token in line.lower():
                                line_hits.append((number, token))
                                break
                    if token_score:
                        matched.append(token)
                        score += token_score

                if not matched:
                    continue
                score += max(0, len(set(matched)) - 1) * 8

                anchor = min((item[0] for item in line_hits), default=1)
                candidates.append((score, len(set(matched)), rel, anchor, matched))

        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))

        # Protected authority files may rank highly for a natural-language
        # improvement query, but autonomous self-improvement must never inspect
        # them as patch targets. Skip non-inspectable authority files and keep
        # scanning for the next editable candidate instead of aborting the
        # entire investigation.
        limit = min(max(int(max_files), 1), 5)
        selected = []
        skipped_protected = []
        for candidate in candidates:
            _, _, rel, _, _ = candidate
            try:
                self._resolve_editable(rel)
            except ValueError as exc:
                message = str(exc)
                if (
                    "authority file requires manual maintenance" in message
                    or "Protected file cannot be modified" in message
                ):
                    skipped_protected.append(rel)
                    continue
                continue
            selected.append(candidate)
            if len(selected) >= limit:
                break

        results = []
        for score, _, rel, anchor, matched in selected:
            half = max(10, min(int(context_lines), 200) // 2)
            start = max(1, anchor - half)
            end = start + min(max(int(context_lines), 20), 200) - 1
            excerpt = self.inspect(rel, start, end)
            results.append(
                {
                    "file": rel,
                    "score": score,
                    "matched_terms": sorted(set(matched)),
                    "start_line": excerpt["start_line"],
                    "end_line": excerpt["end_line"],
                    "content": excerpt["content"],
                }
            )

        return {
            "query": query,
            "searched_terms": tokens,
            "results": results,
            "evidence_found": bool(results),
            "skipped_protected": skipped_protected,
            "rule": (
                "Only propose code improvements supported by successfully "
                "inspected source in these results. If evidence_found is false, "
                "do not invent an improvement."
            ),
        }

    def propose(
        self,
        *,
        file: str,
        old_text: str,
        new_text: str,
        rationale: str,
        tests: list[str] | None = None,
    ) -> PatchProposal:
        path = self._resolve_editable(file)
        if not path.exists():
            raise FileNotFoundError(file)
        if not old_text:
            raise ValueError("old_text must be an exact non-empty source fragment.")
        if old_text == new_text:
            raise ValueError("Patch does not change the source.")

        source = path.read_text(encoding="utf-8")
        occurrences = source.count(old_text)
        if occurrences != 1:
            raise ValueError(
                f"old_text must match exactly once; found {occurrences} matches."
            )

        selected_tests = tuple(tests or ())
        if len(selected_tests) > 5:
            raise ValueError("A patch may specify at most five targeted tests.")
        for module in selected_tests:
            if not self._valid_test(module):
                raise ValueError(
                    f"Invalid test module {module!r}; only tests.* is allowed."
                )

        proposal = PatchProposal(
            patch_id=self._patch_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            file=str(path.relative_to(self.project_root)),
            rationale=(rationale or "").strip()[:4000],
            old_text=old_text,
            new_text=new_text,
            tests=selected_tests,
        )
        self._write_proposal(proposal)
        return proposal

    def _proposal_path(self, patch_id: str) -> Path:
        if not PATCH_ID_RE.fullmatch(patch_id or ""):
            raise ValueError("Invalid patch ID.")
        return self.proposals_dir / f"{patch_id}.json"

    def _write_proposal(self, proposal: PatchProposal) -> None:
        self._proposal_path(proposal.patch_id).write_text(
            json.dumps(proposal.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def get_proposal(self, patch_id: str) -> PatchProposal:
        path = self._proposal_path(patch_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(patch_id) from exc
        return PatchProposal(
            patch_id=data["patch_id"],
            created_at=data["created_at"],
            file=data["file"],
            rationale=data.get("rationale", ""),
            old_text=data["old_text"],
            new_text=data["new_text"],
            tests=tuple(data.get("tests", [])),
            status=data.get("status", "proposed"),
        )

    def latest_proposal(self) -> PatchProposal | None:
        files = sorted(self.proposals_dir.glob("PATCH-*.json"))
        if not files:
            return None
        return self.get_proposal(files[-1].stem)

    def _set_status(self, proposal: PatchProposal, status: str) -> None:
        data = proposal.to_dict()
        data["status"] = status
        self._proposal_path(proposal.patch_id).write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _run_test(self, module: str, timeout: int = 180) -> dict:
        proc = subprocess.run(
            [sys.executable, "-m", module],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(self.project_root)},
        )
        return {
            "module": module,
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:],
        }

    def _compile_target(self, path: Path) -> dict:
        if path.suffix != ".py":
            return {"success": True, "check": "compile", "skipped": True}
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "success": proc.returncode == 0,
            "check": "py_compile",
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }

    def apply(self, patch_id: str) -> dict:
        proposal = self.get_proposal(patch_id)
        if proposal.status != "proposed":
            raise ValueError(
                f"Patch {patch_id} is not pending; status={proposal.status}."
            )

        path = self._resolve_editable(proposal.file)
        source = path.read_text(encoding="utf-8")
        if source.count(proposal.old_text) != 1:
            raise ValueError(
                "Source changed since proposal; exact patch anchor no longer matches once."
            )

        backup_dir = self.backups_dir / proposal.patch_id
        backup_path = backup_dir / proposal.file
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)

        updated = source.replace(proposal.old_text, proposal.new_text, 1)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        checks = [self._compile_target(path)]
        for module in proposal.tests:
            checks.append(self._run_test(module))

        success = all(item.get("success") for item in checks)
        rolled_back = False

        if not success:
            shutil.copy2(backup_path, path)
            rolled_back = True
            self._set_status(proposal, "rolled_back")
        else:
            self._set_status(proposal, "applied")

        result = {
            "patch_id": proposal.patch_id,
            "file": proposal.file,
            "success": success,
            "rolled_back": rolled_back,
            "backup": str(backup_path.relative_to(self.project_root)),
            "checks": checks,
            "rationale": proposal.rationale,
        }
        (self.history_dir / f"{proposal.patch_id}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    def rollback(self, patch_id: str) -> dict:
        proposal = self.get_proposal(patch_id)
        path = self._resolve_editable(proposal.file)
        backup_path = self.backups_dir / patch_id / proposal.file
        if not backup_path.exists():
            raise FileNotFoundError(f"No backup exists for {patch_id}.")
        shutil.copy2(backup_path, path)
        self._set_status(proposal, "rolled_back")
        return {
            "patch_id": patch_id,
            "file": proposal.file,
            "success": True,
            "status": "rolled_back",
        }
