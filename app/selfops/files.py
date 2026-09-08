from __future__ import annotations

from pathlib import Path
import re

from ..config import BASE_DIR


class ProjectFileBrowser:
    """Read-only project file discovery with secret-content safeguards."""

    SKIP_DIRS = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "vectorstore",
        "self_repairs",
    }

    TEXT_EXTENSIONS = {
        ".py",
        ".md",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".txt",
        ".toml",
        ".ini",
        ".cfg",
        ".csv",
    }

    SENSITIVE_NAME_RE = re.compile(
        r"(?:^|[._-])(?:passwords?|credentials?|secrets?|tokens?|private[_-]?keys?|"
        r"ssh[_-]?keys?|recovery[_-]?codes?|\.env)(?:$|[._-])",
        re.I,
    )

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root or BASE_DIR).resolve()

    def _iter_files(self):
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                rel = path.relative_to(self.project_root)
            except ValueError:
                continue
            if any(part in self.SKIP_DIRS for part in rel.parts):
                continue
            yield path, rel

    @classmethod
    def _sensitive_name(cls, rel: Path) -> bool:
        text = "/".join(rel.parts).lower()
        if rel.name in {".env", ".env.local", ".env.production", ".env.development"}:
            return True
        return bool(cls.SENSITIVE_NAME_RE.search(text))

    def search(self, query: str, max_results: int = 20) -> dict:
        if not query or len(query) > 300:
            raise ValueError("File search query must be 1-300 characters.")

        q = query.strip().lower()
        q_name = Path(q).name
        tokens = [t for t in re.findall(r"[a-zA-Z0-9_.-]+", q) if len(t) >= 2]
        scored = []

        for path, rel in self._iter_files():
            rel_text = rel.as_posix().lower()
            name = rel.name.lower()
            score = 0

            if name == q_name:
                score += 100
            elif q_name and q_name in name:
                score += 50
            if q in rel_text:
                score += 40
            for token in tokens:
                if token == name:
                    score += 25
                elif token in name:
                    score += 10
                elif token in rel_text:
                    score += 3

            if score <= 0:
                continue

            # Prefer shallower paths. A root-level dataset must outrank a
            # nested copy with the same name (adapter/export/job directories),
            # instead of falling through to an alphabetical tie-break.
            depth = len(rel.parts) - 1
            score -= min(depth, 8) * 4

            scored.append(
                {
                    "file": rel.as_posix(),
                    "name": rel.name,
                    "size_bytes": path.stat().st_size,
                    "extension": path.suffix.lower(),
                    "sensitive_name": self._sensitive_name(rel),
                    "score": score,
                }
            )

        scored.sort(key=lambda item: (-item["score"], item["file"]))
        return {
            "query": query,
            "results": scored[: min(max(int(max_results), 1), 50)],
            "found": bool(scored),
            "rule": "This search returns file metadata only; it does not expose file contents.",
        }

    def inspect_text(self, relative_path: str, start_line: int = 1, end_line: int = 200) -> dict:
        rel = Path(relative_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Only project-relative paths are allowed.")
        path = (self.project_root / rel).resolve()
        try:
            rel = path.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("Path escapes project root.") from exc
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(relative_path)
        if self._sensitive_name(rel):
            raise PermissionError(
                "Sensitive credential/secret-like file content is blocked from inspection."
            )
        if path.suffix.lower() not in self.TEXT_EXTENSIONS:
            raise ValueError("File type is not approved for text inspection.")
        if path.stat().st_size > 2_000_000:
            raise ValueError("File is too large for interactive text inspection.")

        start = max(1, int(start_line))
        end = min(max(start, int(end_line)), start + 399)
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = [
            f"{number}: {lines[number - 1]}"
            for number in range(start, min(end, len(lines)) + 1)
        ]
        return {
            "file": rel.as_posix(),
            "start_line": start,
            "end_line": min(end, len(lines)),
            "content": "\n".join(selected),
        }
