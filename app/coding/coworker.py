from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..personality import CODING_PERSONA

from .explore import (
    SessionState, explicit_request_paths, normalize_path_token, plan_gaps, request_wants_tests, select_context,
)
from .transactions import ACTIVE_STATES, TransactionJournal


_CODE_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".html", ".css",
    ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".sh", ".go",
    ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb",
    ".vue", ".svelte",
}

_PRIORITY_FILES = (
    "README.md",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements.txt",
    "pytest.ini",
    "tox.ini",
    "package.json",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
)


class WorkspaceCoworker:
    """Python-authoritative full coding-agent workflow."""

    MAX_PLAN_FILES = 12
    MAX_CONTEXT_FILES = 10
    MAX_REPAIR_PASSES = 2
    # When verification still fails after all repair passes, restore
    # the pre-task snapshot instead of leaving broken partial work on disk.
    ROLLBACK_ON_FAILED_VERIFICATION = True

    # Budgets below were tuned for a 4096-token window; they scale linearly
    # with the detected context window, capped at 4x.
    BASE_CONTEXT_WINDOW = 4096
    BASE_PLANNER_CHARS = 10500
    BASE_FILE_READ_CHARS = 3600
    BASE_REPAIR_READ_CHARS = 6500

    MAX_PREVIEW_LINES = 80

    def __init__(self, *, client, manager, context_window=None, require_approval=False):
        self.client = client
        self.manager = manager
        self.set_context_window(context_window or self.BASE_CONTEXT_WINDOW)
        # Plan -> preview -> approve -> apply. Direct construction keeps
        # the legacy immediate-apply behaviour; the agent enables approval.
        self.require_approval = bool(require_approval)
        self.session = SessionState()
        self.last_context = None
        self.pending = None
        self.last_applied = None
        self._last_summary = None
        # Every mutation is backed by a durable transaction journal.
        # A new process can restore pending approval, auto-rollback an interrupted
        # apply/verify/repair, and retain /undo authority after restart.
        self.journal = TransactionJournal(self.manager.root)
        self.recovery_notice = None
        self._recover_durable_state()

    def set_context_window(self, context_window):
        """Refresh planner/read budgets when the broker changes active model."""
        window = int(context_window or self.BASE_CONTEXT_WINDOW)
        scale = max(0.5, min(4.0, window / self.BASE_CONTEXT_WINDOW))
        self.context_window = window
        self.planner_chars = int(self.BASE_PLANNER_CHARS * scale)
        self.file_read_chars = int(self.BASE_FILE_READ_CHARS * scale)
        self.REPAIR_READ_CHARS = int(self.BASE_REPAIR_READ_CHARS * scale)

    def _recover_durable_state(self):
        """Recover coding authority after a RazaAI/process/device restart."""
        active = self.journal.latest(ACTIVE_STATES)
        if active is not None:
            txid = str(active.get("id") or "")
            try:
                snapshot = self.journal.load_snapshot(txid)
                result = self._rollback_snapshot(snapshot)
                if result["failures"]:
                    self.journal.update(
                        txid, "failed", recovery=True, rollback_failures=result["failures"]
                    )
                    self.recovery_notice = (
                        "Interrupted coding transaction recovery was incomplete: "
                        + "; ".join(result["failures"])
                    )
                else:
                    recovered_state = "undone" if active.get("state") == "undoing" else "rolled_back"
                    self.journal.update(
                        txid, recovered_state, recovery=True, restored=result["restored"]
                    )
                    action = "undo" if recovered_state == "undone" else "coding transaction"
                    self.recovery_notice = (
                        f"Recovered interrupted {action} {txid}: restored "
                        f"{len(result['restored'])} path(s) to the pre-task snapshot."
                    )
            except (ValueError, OSError, UnicodeError) as exc:
                self.journal.update(txid, "failed", recovery=True, recovery_error=str(exc))
                self.recovery_notice = (
                    f"Interrupted coding transaction {txid} could not be safely recovered: {exc}"
                )

        pending = self.journal.latest(frozenset({"pending_approval"}))
        if pending is not None:
            self.pending = {
                "txid": pending["id"],
                "request": pending.get("request") or "",
                "operations": list(pending.get("operations") or []),
                "errors": list(pending.get("errors") or []),
                "plan": dict(pending.get("plan") or {}),
                "before_paths": set(pending.get("before_paths") or []),
                "summary": pending.get("summary") or "",
            }

        # An approved transaction without a durable snapshot cannot have safely
        # modified anything: fail it closed instead of guessing/resuming writes.
        approved = self.journal.latest(frozenset({"approved"}))
        if approved is not None:
            self.journal.update(
                approved["id"], "failed", recovery=True,
                recovery_error="restart occurred before durable snapshot/apply",
            )

        verified = self.journal.latest(frozenset({"verified"}))
        if verified is not None:
            txid = str(verified.get("id") or "")
            try:
                snapshot = self.journal.load_snapshot(txid)
            except (ValueError, OSError, UnicodeError):
                snapshot = None
            if snapshot is not None:
                self.last_applied = {
                    "txid": txid,
                    "snapshot": snapshot,
                    "written": list(verified.get("written") or []),
                    "summary": verified.get("summary") or None,
                }
                self._last_summary = verified.get("summary") or None

    def recovery_status(self):
        return self.recovery_notice

    def pop_recovery_notice(self):
        notice = self.recovery_notice
        self.recovery_notice = None
        return notice

    class PlanTruncated(ValueError):
        """The model's JSON stopped mid-way: retryable, never a crash."""

    @classmethod
    def _extract_json(cls, value):
        text = str(value or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0:
                raise ValueError("Coding planner did not return valid JSON.")
            if end <= start:
                # Opened but never closed: the output stopped mid-plan.
                raise cls.PlanTruncated(
                    f"plan JSON ended early ({exc.msg} at char {exc.pos} of {len(text)})"
                ) from exc
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError as inner:
                raise cls.PlanTruncated(
                    f"plan JSON ended early ({inner.msg} at char {inner.pos} of {len(text)})"
                ) from exc
        if not isinstance(data, dict):
            raise ValueError("Coding planner returned an invalid plan object.")
        return data

    # A question about code is conversation, not authority to write.
    _QUESTION_PATTERNS = (
        r"^\s*(?:how|why|what|which|where|when|who|whether|can|could|would|should|"
        r"is|are|do|does|did|will|explain|describe|tell me|help me understand)\b",
        r"\?\s*$",
        r"\b(?:how (?:do|would|should|can) (?:i|we|you)|what (?:does|is|would|should)|"
        r"why (?:does|is|did)|is it (?:possible|safe|better)|any idea|thoughts on)\b",
    )
    _IMPERATIVE_OVERRIDE = re.compile(
        r"^\s*(?:please\s+)?(?:go ahead and\s+|now\s+|just\s+)?"
        r"(?:create|build|implement|write|make|generate|add|edit|modify|change|"
        r"update|fix|repair|refactor|remove|delete|rename|move)\b"
    )

    @classmethod
    def is_question(cls, text):
        value = str(text or "").strip().casefold()
        if not value:
            return False
        # A leading imperative wins even if the sentence ends with '?'
        # ("fix the failing tests?" is still a request to act).
        if cls._IMPERATIVE_OVERRIDE.search(value):
            return False
        return any(re.search(pattern, value) for pattern in cls._QUESTION_PATTERNS)

    @staticmethod
    def _is_read_or_status(value):
        if re.search(r"\b(?:show|display|read|open)\b.{0,28}\b(?:code|source|file|files)\b", value):
            return True
        if re.search(r"\b(?:list|show)\b.{0,20}\b(?:files|workspace|directory|folder)\b", value):
            return True
        if re.search(r"\b(?:what|which)\b.{0,24}\b(?:workspace|directory|folder|project)\b", value):
            return True
        if re.search(r"\b(?:git\s+)?(?:status|diff)\b", value):
            return True
        if re.search(r"\b(?:what|which|show|why)\b.{0,40}\b(?:error|failed|failure|went wrong|exception)\b|\blast error\b", value):
            return True
        if re.search(r"\bgit\s+branch\b|\b(?:current|which|what)\s+(?:git\s+)?branch\b|\bwhat branch\b", value):
            return True
        if re.search(
            r"\b(?:run|execute|check|verify)\b.{0,24}\b(?:tests?|pytest|unittest|build|lint|compile)\b",
            value,
        ):
            return True
        return False

    @classmethod
    def is_mutation(cls, text):
        value = str(text or "").strip().casefold()
        if not value or cls.is_question(value):
            return False
        mutation = re.search(
            r"\b(?:create|reate|build|implement|write|make|generate|add|edit|modify|"
            r"change|update|fix|repair|refactor|remove|delete|rename|move)\b",
            value,
        )
        coding = re.search(
            r"\b(?:app|application|script|program|code|python|javascript|typescript|"
            r"node|gui|api|website|web app|project|file|module|class|function|"
            r"tests?|bug|error|failure|feature|endpoint|component|\.py|\.js|\.ts|\.json|\.yaml|\.yml|\.md)\b",
            value,
        )
        return bool(mutation and coding)

    @staticmethod
    def _normalize_request_typo(text):
        """Normalize a narrow, high-confidence leading mutation typo."""
        value = str(text or "")
        if re.match(r"^\s*reate\b", value, re.I) and re.search(
            r"\b[^\s,;:()]+\.(?:py|pyi|js|jsx|ts|tsx|json|toml|yaml|yml|md|txt|sh|cfg|conf|ini)\b",
            value,
            re.I,
        ):
            return re.sub(r"^(\s*)reate\b", r"\1create", value, count=1, flags=re.I)
        return value

    @classmethod
    def should_handle(cls, text):
        """Python-owned read/status operations or explicit mutation requests only."""
        value = str(text or "").strip().casefold()
        if not value:
            return False
        if cls._is_read_or_status(value):
            return True
        return cls.is_mutation(value)

    def _list(self):
        return self.manager.list_files(".", recursive=True, max_entries=350)

    def _file_paths(self, listing):
        return [
            str(item.get("path") or "")
            for item in listing.get("entries") or []
            if item.get("type") == "file"
        ]

    def _project_profile(self, listing=None):
        listing = listing or self._list()
        files = set(self._file_paths(listing))
        suffixes = {Path(path).suffix.casefold() for path in files}

        languages = []
        if ".py" in suffixes or ".pyi" in suffixes:
            languages.append("python")
        if suffixes & {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}:
            languages.append("node")
        if "go.mod" in files or ".go" in suffixes:
            languages.append("go")
        if "Cargo.toml" in files or ".rs" in suffixes:
            languages.append("rust")

        frameworks = []
        package = {}
        if "package.json" in files:
            try:
                package = json.loads(
                    self.manager.read_file("package.json", max_chars=20000)["content"]
                )
                deps = {}
                deps.update(package.get("dependencies") or {})
                deps.update(package.get("devDependencies") or {})
                for name in ("react", "next", "vue", "svelte", "express", "vite"):
                    if name in deps:
                        frameworks.append(name)
            except (ValueError, json.JSONDecodeError, KeyError, TypeError):
                package = {}

        if "pyproject.toml" in files:
            try:
                pyproject = self.manager.read_file(
                    "pyproject.toml", max_chars=20000
                )["content"].casefold()
            except ValueError:
                pyproject = ""
            for name in ("django", "flask", "fastapi", "pytest", "ruff"):
                if name in pyproject and name not in frameworks:
                    frameworks.append(name)

        has_tests = any(
            path.startswith("tests/")
            or Path(path).name.startswith("test_")
            or Path(path).name.endswith((".test.js", ".test.ts", ".spec.js", ".spec.ts"))
            for path in files
        )

        python_test_runner = None
        if "python" in languages and has_tests:
            pytest_evidence = False
            for metadata_path in ("pyproject.toml", "requirements.txt", "pytest.ini", "tox.ini"):
                if metadata_path not in files:
                    continue
                try:
                    metadata_text = self.manager.read_file(
                        metadata_path, max_chars=16000
                    )["content"].casefold()
                except ValueError:
                    continue
                if "pytest" in metadata_text:
                    pytest_evidence = True
                    break
            if not pytest_evidence:
                for test_path in sorted(files):
                    if not (
                        test_path.startswith("tests/")
                        or Path(test_path).name.startswith("test_")
                    ):
                        continue
                    try:
                        test_text = self.manager.read_file(
                            test_path, max_chars=3500
                        )["content"].casefold()
                    except ValueError:
                        continue
                    if "import pytest" in test_text or "@pytest." in test_text:
                        pytest_evidence = True
                        break
            python_test_runner = "pytest" if pytest_evidence else "unittest"

        git = self.manager.resolve(".git").exists()
        interpreters = self.manager.project_interpreters(refresh=True)
        return {
            "root": str(self.manager.root),
            "python_interpreter": interpreters["python_source"],
            "files": sorted(files),
            "languages": languages,
            "frameworks": frameworks,
            "has_tests": has_tests,
            "python_test_runner": python_test_runner,
            "git": git,
            "package": package,
        }

    @staticmethod
    def _request_terms(request):
        return {
            term
            for term in re.findall(r"[a-zA-Z_][a-zA-Z0-9_.-]{2,}", str(request).casefold())
            if term not in {
                "the", "and", "with", "from", "that", "this", "into", "make",
                "create", "build", "implement", "please", "code", "app", "application",
                "project", "file", "files", "change", "update", "fix",
            }
        }

    def _rank_context_files(self, request, listing):
        terms = self._request_terms(request)
        ranked = []
        for path in self._file_paths(listing):
            p = Path(path)
            if p.suffix.casefold() not in _CODE_EXTENSIONS and p.name not in _PRIORITY_FILES:
                continue
            score = 0
            lower = path.casefold()
            if p.name in _PRIORITY_FILES:
                score += 20
            for term in terms:
                if term in lower:
                    score += 12
            if p.name.startswith("test_") or "test" in p.parts:
                score += 3
            if p.suffix.casefold() in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs"}:
                score += 4
            ranked.append((score, path))
        ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
        return [path for _, path in ranked[: self.MAX_CONTEXT_FILES]]

    def _readable_context(self, request, listing, *, max_chars=None):
        max_chars = int(max_chars or self.planner_chars)
        chunks = []
        used = 0
        for path in self._rank_context_files(request, listing):
            try:
                result = self.manager.read_file(path, max_chars=self.file_read_chars)
            except (OSError, ValueError, UnicodeError):
                continue
            content = str(result.get("content") or "")
            clipped = bool(result.get("clipped"))
            remaining = max_chars - used
            if remaining <= 0:
                break
            content = content[:remaining]
            chunks.append(
                f"FILE: {path}\nCLIPPED: {'yes' if clipped else 'no'}\n{content}"
            )
            used += len(content)
        return "\n\n".join(chunks)

    MAX_COMPLETENESS_RETRIES = 1
    _REWRITE_RE = re.compile(
        r"\b(?:rewrite|regenerate|replace (?:the )?(?:whole|entire|file)|from scratch|overwrite|"
        r"rename|remove|delete|drop|strip out|get rid of|clean up|simplify|refactor)\b", re.I)

    # A request about something failing must come with the failure.
    _FIX_INTENT = re.compile(
        r"\b(?:fix|failing|fails|failure|broken|breaks|bug|error|exception|traceback|"
        r"doesn'?t (?:work|pass)|not (?:working|passing)|regression|crash(?:es|ing)?)\b",
        re.I,
    )
    PRE_EVIDENCE_CHARS = 1800

    def _current_failure_evidence(self, request, profile):
        """Run the project's own checks BEFORE planning a fix and return the failing output."""
        if not self._FIX_INTENT.search(request or ""):
            return None
        commands = self._verification_commands(profile)
        if not commands:
            return None
        failures = []
        for command in commands[:2]:
            try:
                result = self.manager.run_command(command, timeout=60)
            except (ValueError, OSError) as exc:
                failures.append(f"$ {' '.join(command)}\n(not run: {exc})")
                continue
            if int(result.get("exit_code", 1)) != 0:
                output = (result.get("stderr") or "") + "\n" + (result.get("stdout") or "")
                failures.append(f"$ {' '.join(result.get('command') or command)}  (exit {result['exit_code']})\n{output.strip()[-1200:]}")
        if not failures:
            return "CURRENT VERIFICATION: all project checks pass right now; the reported failure is not reproduced by the test suite."
        text = "CURRENT VERIFICATION OUTPUT (run by Python before planning; fix the CODE so these pass):\n" + "\n\n".join(failures)
        return text[: self.PRE_EVIDENCE_CHARS]

    # Grammar-constrained plans. Small models fail structured output
    # far more often than they fail the coding itself; the schema removes that
    # failure mode entirely (no prose, no fences, no missing keys).
    PLAN_SCHEMA = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "mode": {"type": "string", "enum": ["create", "replace", "patch", "append"]},
                        "content": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                        "purpose": {"type": "string"},
                    },
                    "required": ["path", "mode"],
                },
            },
            "summary": {"type": "string"},
            "verification_hint": {"type": "string"},
        },
        "required": ["files", "summary"],
    }

    PLAN_NUM_PREDICT = 3072  # Plans with whole-file content are long; never let a default cap cut them

    def _chat_json(self, messages):
        """Request a JSON plan within the active model's context budget."""
        from ..context_budget import estimate_messages

        remaining = self.context_window - estimate_messages(messages) - 192
        if remaining < 256:
            raise ValueError("Coding context is full. Request fewer files or use the standard profile.")
        output_limit = min(self.PLAN_NUM_PREDICT, remaining)
        try:
            return self.client.chat(messages, tools=None, format=self.PLAN_SCHEMA, num_predict=output_limit)
        except TypeError:
            try:
                return self.client.chat(messages, tools=None, format=self.PLAN_SCHEMA)
            except TypeError:
                return self.client.chat(messages, tools=None)

    def _planner(self, request, listing, profile, gaps=None, previous_plan=None):
        existing = self._file_paths(listing)
        # Deterministic exploration picks files and symbols; the model
        # no longer receives "first 3600 chars of a keyword-matched file".
        selection = select_context(
            self.manager, request, existing, max_chars=self.planner_chars,
            priority_files=_PRIORITY_FILES,
        )
        self.last_context = selection
        source_context = selection.rendered
        target_paths = list(selection.requested_paths)
        new_target_paths = set(selection.new_paths)
        target_contract = ""
        if target_paths:
            target_contract = (
                " Python has extracted explicit user target path(s): "
                + ", ".join(target_paths)
                + ". Treat these paths as authoritative. Do NOT substitute or invent "
                  "a different path. Do not Markdown-escape punctuation inside JSON path "
                  "strings (write app/main.py, not app/main\\.py or test\\_x.py)."
            )
            if new_target_paths:
                target_contract += (
                    " These target path(s) do not currently exist and must use mode=create: "
                    + ", ".join(sorted(new_target_paths))
                    + "."
                )

        system = (
            "You are RazaAI's coding-plan component inside an existing working "
            "directory. Return JSON only. Python performs all real writes and "
            "verification. Implement the user's request now; do not merely explain "
            "how. Preserve the project's existing architecture, naming, formatting, "
            "imports, public APIs and coding style unless the request requires a "
            "change. Prefer the smallest coherent multi-file change. For NEW files, "
            "use mode=create with complete non-empty content. For an EXISTING file, "
            "prefer mode=patch with an exact unique old_text fragment copied from the "
            "supplied source and the desired new_text. Use mode=replace only when the "
            "entire existing file is supplied with CLIPPED: no. If CLIPPED: yes, you "
            "MUST use patch mode so unseen source is preserved. "
            "Use relative paths only. Never include secrets. Do not claim that code "
            "was executed, tested, written, or successful. Schema: "
            '{"files":[{"path":"relative/path","mode":"create|replace|patch",'
            '"content":"complete content for create/replace",'
            '"old_text":"exact source fragment for patch","new_text":"replacement",'
            '"purpose":"why this file changes"}],"summary":"implementation intent",'
            '"verification_hint":"optional short hint"}. '
            f"At most {self.MAX_PLAN_FILES} files."
            + target_contract
            + "\n" + CODING_PERSONA
        )

        gap_block = ""
        if gaps:
            gap_block = (
                "\nYOUR PREVIOUS PLAN WAS INCOMPLETE. Python checked it against the request and found:\n"
                + "\n".join(f"- {g}" for g in gaps)
                + "\nReturn a corrected complete plan that closes every gap above.\n"
                + (f"PREVIOUS PLAN: {json.dumps(previous_plan, ensure_ascii=False)[:3000]}\n" if previous_plan else "")
            )
        related = ", ".join(selection.related_tests[:6]) or "<none found>"
        session_block = self.session.render()
        evidence_block = self._current_failure_evidence(request, profile)
        if target_paths:
            prompt_existing = [p for p in selection.files if p in existing][:60]
            # The exact target existence state is more useful to a 3B planner than
            # hundreds of unrelated filenames.
            target_state = ", ".join(
                f"{p}={'NEW' if p in new_target_paths else 'EXISTS'}" for p in target_paths
            )
        else:
            prompt_existing = existing[:220]
            target_state = "<no explicit path target>"
        user = (
            f"REQUEST: {request}\n"
            f"WORKSPACE ROOT (Python authority): {self.manager.root}\n"
            f"EXPLICIT TARGET STATE: {target_state}\n"
            f"PROJECT PROFILE: {json.dumps({k:v for k,v in profile.items() if k != 'package'}, ensure_ascii=False)}\n"
            f"RELEVANT EXISTING FILES: {prompt_existing or ['<none>']}\n"
            f"RELATED TEST/SOURCE FILES: {related}\n"
            + (f"\n{session_block}\n" if session_block else "")
            + (f"\n{evidence_block}\n" if evidence_block else "")
            + gap_block
            + f"\nRELEVANT EXISTING SOURCE (selected by Python):\n{source_context or '<none>'}"
        )

        result = self._chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        content = ((result or {}).get("message") or {}).get("content") or ""
        self._trace("plan", system=system, user=user, reply=content, request=request, gaps=list(gaps or []))
        return self._extract_json(content)

    def _snapshot_paths(self, paths):
        snapshot = {}
        for path in paths:
            try:
                if self.manager.exists(path):
                    content = self.manager.read_file_exact(path)
                    snapshot[path] = {
                        "existed": True,
                        "content": content,
                    }
                else:
                    snapshot[path] = {"existed": False, "content": None}
            except (ValueError, OSError, UnicodeError):
                raise ValueError(f"Cannot safely snapshot workspace file: {path}")
        return snapshot

    def _rollback_snapshot(self, snapshot):
        restored = []
        failures = []
        for path, state in snapshot.items():
            try:
                if state["existed"]:
                    self.manager.write_file(
                        path,
                        state["content"],
                        overwrite=self.manager.exists(path),
                    )
                elif self.manager.exists(path):
                    self.manager.remove_file(path)
                restored.append(path)
            except (ValueError, OSError) as exc:
                failures.append(f"{path}: {exc}")
        return {"restored": restored, "failures": failures}

    def _validate_plan(self, plan, before_paths):
        """Turn a planner JSON into guarded operations without touching disk."""
        files = list(plan.get("files") or [])[: self.MAX_PLAN_FILES]
        operations = []
        errors = []

        for item in files:
            raw_path = str(item.get("path") or "").strip()
            path = normalize_path_token(raw_path)
            mode = str(item.get("mode") or "").strip().casefold()
            content = item.get("content")
            old_text = item.get("old_text")
            new_text = item.get("new_text")

            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                errors.append(f"Rejected unsafe or missing file path: {path or '<missing path>'}")
                continue

            exists = path in before_paths

            # Backwards compatibility with the planner schema:
            # content-only plans create new files or replace known existing files.
            if not mode:
                mode = "replace" if exists else "create"

            if mode == "append":
                # Add to the END of an existing file with no anchor at all.
                content = item.get("content") if isinstance(item.get("content"), str) else item.get("new_text")
                if path not in before_paths:
                    errors.append(f"Rejected append to a file that does not exist: {path} (use create)")
                    continue
                if not isinstance(content, str) or len(content.strip()) < 3:
                    errors.append(f"Rejected empty append: {path}")
                    continue
                operations.append({"path": path, "mode": "append", "content": content})
                continue
            if mode == "patch":
                if not exists:
                    errors.append(f"Rejected patch for non-existing file: {path}")
                    continue
                if (
                    not isinstance(old_text, str)
                    or not old_text
                    or not isinstance(new_text, str)
                    or old_text == new_text
                ):
                    errors.append(f"Rejected incomplete exact patch: {path}")
                    continue
                # Prove the anchor exists exactly once NOW, not at /approve time.
                try:
                    current = self.manager.read_file_exact(path)
                except (ValueError, OSError, UnicodeError) as exc:
                    errors.append(f"Rejected patch for unreadable file {path}: {exc}")
                    continue
                occurrences = current.count(old_text)
                if occurrences != 1:
                    errors.append(
                        f"Patch anchor for {path} occurs {occurrences} time(s) in the current file; "
                        "old_text must be copied verbatim from the supplied source and be unique"
                    )
                    continue
                operations.append(
                    {
                        "path": path,
                        "mode": "patch",
                        "old_text": old_text,
                        "new_text": new_text,
                    }
                )
                continue

            if mode not in {"create", "replace"}:
                errors.append(f"Rejected unsupported file operation {mode!r}: {path}")
                continue
            if mode == "create" and exists:
                errors.append(f"Rejected create because file already exists: {path}")
                continue
            if mode == "replace" and not exists:
                # A model may call a new-file operation replace; safely normalize.
                mode = "create"
            if not isinstance(content, str) or len(content.strip()) < 8:
                errors.append(f"Rejected incomplete file plan: {path}")
                continue
            if mode == "replace" and self._shrinks_too_much(path, content):
                errors.append(
                    f"Rejected replacement that would remove more than "
                    f"{int(self.MAX_SILENT_SHRINK_RATIO * 100)}% of {path}; use patch mode"
                )
                continue

            operations.append(
                {
                    "path": path,
                    "mode": mode,
                    "content": content,
                }
            )

        return operations, errors

    def _apply_operations(self, operations, *, txid=None):
        """Write guarded operations transactionally with a durable pre-write snapshot."""
        errors = []
        if not operations:
            return [], errors, {}
        snapshot = self._snapshot_paths([item["path"] for item in operations])
        if txid:
            # Snapshot reaches stable storage before the first workspace write.
            self.journal.save_snapshot(txid, snapshot)
            self.journal.update(txid, "applying", applied_paths=[])
        written = []
        try:
            for item in operations:
                path = item["path"]
                if item["mode"] == "patch":
                    self.manager.patch_file(path, item["old_text"], item["new_text"])
                elif item["mode"] == "append":
                    self.manager.append_file(path, item["content"])
                else:
                    self.manager.write_file(path, item["content"], overwrite=item["mode"] == "replace")
                written.append(path)
                if txid:
                    self.journal.update(txid, "applying", applied_paths=list(written))
        except (ValueError, OSError) as exc:
            rollback = self._rollback_snapshot(snapshot)
            errors.append(f"Write failed and transaction was rolled back: {exc}")
            errors.extend(f"Rollback failure: {item}" for item in rollback["failures"])
            if txid:
                state = "rolled_back" if not rollback["failures"] else "failed"
                self.journal.update(
                    txid, state, apply_error=str(exc), restored=rollback["restored"],
                    rollback_failures=rollback["failures"],
                )
            return [], errors, snapshot
        return written, errors, snapshot

    def _write_plan(self, plan, before_paths):
        operations, errors = self._validate_plan(plan, before_paths)
        written, apply_errors, snapshot = self._apply_operations(operations)
        return written, errors + apply_errors, snapshot

    # ---- preview / approve / undo / checkpoint ----------------------

    def _preview_text(self, path, mode, old_content, new_content):
        import difflib
        before = (old_content or "").splitlines(keepends=True)
        after = (new_content or "").splitlines(keepends=True)
        diff = difflib.unified_diff(before, after, fromfile=f"a/{path}", tofile=f"b/{path}", n=2)
        text = "".join(diff)
        lines = text.splitlines()
        if len(lines) > self.MAX_PREVIEW_LINES:
            text = "\n".join(lines[: self.MAX_PREVIEW_LINES]) + f"\n... ({len(lines) - self.MAX_PREVIEW_LINES} more diff lines)"
        return text

    def _render_proposal(self, operations, errors, summary):
        lines = ["Proposed changes (nothing written yet):"]
        if not operations:
            lines.append("(no applicable file operations — see guarded items below)")
        for op in operations:
            path = op["path"]
            if op["mode"] == "create":
                old, new = "", op["content"]
            elif op["mode"] == "append":
                old = self.manager.read_file_exact(path)
                new = old.rstrip("\n") + "\n\n\n" + op["content"].strip("\n") + "\n"
            elif op["mode"] == "replace":
                old = self.manager.read_file_exact(path)
                new = op["content"]
            else:
                old = self.manager.read_file_exact(path)
                new = old.replace(op["old_text"], op["new_text"], 1)
            preview = self._preview_text(path, op["mode"], old, new)
            lines.append(f"\n### {op['mode']} `{path}`")
            lines.append("```diff\n" + (preview if preview.strip() else "(no change — identical content)") + "\n```")
        if summary:
            lines.append(f"\nIntent: {summary}")
        if errors:
            lines.append("Guarded plan items (will not be applied):")
            lines.extend(f"- {item}" for item in errors[:6])
        fixes = getattr(self, "last_autofix", None) or []
        if fixes:
            lines.append("Python completed mechanical steps in this plan:")
            lines.extend(f"- {n}" for n in fixes)
        remaining = getattr(self, "last_gaps", None) or []
        if remaining:
            lines.append("Completeness check (Python): this plan does NOT fully satisfy the request:")
            lines.extend(f"- {g}" for g in remaining)
            lines.append("You can `/approve` the partial change, or `/reject` and rephrase.")
        lines.append("\nReply `/approve` to apply and verify, `/reject` to discard.")
        return "\n".join(lines)

    # Optional planner diagnostics stay in the local data directory.
    TRACE_DIR = "coder_traces"

    def _trace(self, kind, **fields):
        """Append one JSONL record per planner call when RAZAAI_CODER_TRACE=1."""
        if os.getenv("RAZAAI_CODER_TRACE", "").strip().casefold() not in {"1", "true", "yes", "on"}:
            return
        try:
            from ..config import BASE_DIR
            import datetime as _dt
            root = Path(os.getenv("RAZAAI_CODER_TRACE_DIR") or (BASE_DIR / "data" / self.TRACE_DIR))
            root.mkdir(parents=True, exist_ok=True)
            record = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "kind": kind,
                      "model": getattr(self.client, "model", None), "workspace": str(self.manager.root), **fields}
            with (root / f"{_dt.date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - tracing must never affect the turn
            pass

    def has_pending(self):
        return self.pending is not None

    def _remember_error(self, text):
        self.last_error = text
        self.session.record("error", text)
        return text

    def last_error_report(self):
        if not getattr(self, "last_error", None):
            return "There is no recorded error from the last coding operation in this session."
        return f"Last coding error (recorded by Python):\n{self.last_error}"

    def reject(self):
        if self.pending is None:
            return "There is no pending proposal to reject."
        pending = self.pending
        summary = pending.get("summary") or ""
        txid = pending.get("txid")
        if txid:
            self.journal.update(txid, "rejected")
        self.pending = None
        return "Discarded the pending proposal. Nothing was written." + (f" ({summary})" if summary else "")

    def approve(self):
        if self.pending is None:
            return "There is no pending proposal to approve."
        pending = self.pending
        txid = pending.get("txid")
        if txid:
            self.journal.update(txid, "approved")
        self.pending = None
        return self._apply_and_verify(
            request=pending["request"],
            operations=pending["operations"],
            errors=pending["errors"],
            plan=pending["plan"],
            before_paths=pending["before_paths"],
            txid=txid,
        )

    def undo(self):
        """Restore the durable snapshot from the last successfully applied task."""
        if not self.last_applied:
            return "There is nothing to undo in this session."
        snapshot = self.last_applied.get("snapshot") or {}
        txid = self.last_applied.get("txid")
        if txid:
            self.journal.update(txid, "undoing")
        result = self._rollback_snapshot(snapshot)
        if txid:
            self.journal.update(
                txid, "undone" if not result["failures"] else "failed",
                undo_restored=result["restored"], undo_failures=result["failures"],
            )
        self.last_applied = None
        self.session.record("undo", ", ".join(result["restored"]), touched=result["restored"])
        lines = [f"Undo: restored {len(result['restored'])} path(s) to their pre-task state."]
        lines.extend(f"- `{p}`" for p in result["restored"])
        for item in result["failures"]:
            lines.append(f"- Undo failure: {item}")
        return "\n".join(lines)

    def checkpoint(self, message=None):
        """Commit the workspace on a raza/* branch (the only Git writes allowed)."""
        try:
            result = self.manager.git_checkpoint(message or self._last_summary or "raza checkpoint")
        except (ValueError, OSError) as exc:
            return f"Checkpoint failed: {exc}"
        if not result.get("committed"):
            return f"Checkpoint: {result.get('reason') or 'nothing to commit'} (branch `{result.get('branch')}`)."
        self.session.record("checkpoint", f"{result['commit']} on {result['branch']}")
        return (
            f"Checkpoint committed on branch `{result['branch']}`: {result['commit']}\n"
            f"{result.get('summary') or ''}".rstrip()
        )

    def _python_compile_checks(self, changed, *, manager=None):
        manager = manager or self.manager
        checks = []
        for path in dict.fromkeys(changed):  # Compile each file once
            if Path(path).suffix.casefold() != ".py":
                continue
            checks.append(
                manager.run_command(
                    ["python3", "-m", "py_compile", path],
                    timeout=20,
                )
            )
        return checks

    def _verification_commands(self, profile, *, changed=None, before_paths=None, request=""):
        commands = []
        files = set(profile.get("files") or [])

        # A newly-created standalone top-level file is verified by
        # its file-level syntax/build check. Existing project tests are not a
        # correctness requirement for an unrelated scratch/example script. Edits
        # to existing project code, nested project modules, and explicit test
        # requests still run the normal project-wide checks.
        changed = [str(path) for path in (changed or [])]
        before_paths = set(before_paths or [])
        standalone_new = bool(changed) and all(
            path not in before_paths
            and len(Path(path).parts) == 1
            and not Path(path).name.startswith("test_")
            for path in changed
        )
        if standalone_new and not request_wants_tests(request):
            return commands

        if "python" in profile.get("languages", []):
            if profile.get("has_tests"):
                if profile.get("python_test_runner") == "pytest":
                    commands.append(["python3", "-m", "pytest", "-q"])
                else:
                    commands.append(["python3", "-m", "unittest", "discover"])
            else:
                # Compile the project without importing or executing application code.
                commands.append(["python3", "-m", "compileall", "-q", "."])

        if "node" in profile.get("languages", []) and "package.json" in files:
            scripts = (profile.get("package") or {}).get("scripts") or {}
            test_script = str(scripts.get("test") or "").strip()
            if test_script and "no test specified" not in test_script.casefold():
                # The coding eval is eligible when Node exists.  Do not
                # make a plain `node --test` project depend on npm also being
                # installed/healthy on the Jetson; execute the declared runner
                # directly through the same workspace command authority.
                if test_script in {"node --test", "node --test ."}:
                    commands.append(["node", "--test"])
                else:
                    commands.append(["npm", "test"])
            if "lint" in scripts:
                commands.append(["npm", "run", "lint"])
            if "build" in scripts:
                commands.append(["npm", "run", "build"])

        if "go" in profile.get("languages", []):
            commands.append(["go", "test", "./..."])

        if "rust" in profile.get("languages", []):
            commands.append(["cargo", "test"])

        # Keep the edge workflow bounded.
        return commands[:4]

    def _run_verification(self, changed, profile, *, request="", before_paths=None):
        """Verify in a disposable workspace copy, never against live source."""
        try:
            with self.manager.verification_workspace() as verify_manager:
                checks = self._python_compile_checks(changed, manager=verify_manager)
                for command in self._verification_commands(
                    profile, changed=changed, before_paths=before_paths, request=request
                ):
                    # Avoid duplicate whole-project compile when individual Python files
                    # have already been checked and this is a tiny no-test project.
                    if (
                        command[:3] == ["python3", "-m", "compileall"]
                        and any(Path(path).suffix.casefold() == ".py" for path in changed)
                    ):
                        continue
                    checks.append(verify_manager.run_command(command, timeout=60))
                for item in checks:
                    item["verification_isolated"] = True
                return checks
        except (OSError, ValueError) as exc:
            # Fail closed. Verification is not allowed to fall back to executing
            # project code in the live workspace merely because isolation failed.
            return [{
                "command": ["verification-isolation"],
                "cwd": ".",
                "exit_code": 125,
                "stdout": "",
                "stderr": f"Could not create isolated verification workspace: {exc}",
                "sandbox": "isolation-failed",
                "verification_isolated": False,
            }]

    @staticmethod
    def _verification_ok(checks):
        return all(int(item.get("exit_code", 1)) == 0 for item in checks)

    @staticmethod
    def _command_label(item):
        return " ".join(str(part) for part in item.get("command") or [])

    def _failure_evidence(self, checks):
        blocks = []
        for item in checks:
            if int(item.get("exit_code", 1)) == 0:
                continue
            output = str(item.get("stderr") or item.get("stdout") or "verification failed")
            blocks.append(
                f"COMMAND: {self._command_label(item)}\n"
                f"EXIT: {item.get('exit_code')}\n"
                f"OUTPUT:\n{output[-3500:]}"
            )
        return "\n\n".join(blocks)

    REPAIR_READ_CHARS = BASE_REPAIR_READ_CHARS
    # A full-file replacement that removes more than this fraction of the
    # original content is refused unless the model explicitly marks the
    # shrink as intentional. Protects against clipped-context truncation.
    MAX_SILENT_SHRINK_RATIO = 0.40

    def _repair(self, request, changed, checks, pass_number):
        source = []
        clipped_paths = set()
        for path in changed:
            try:
                data = self.manager.read_file(path, max_chars=self.REPAIR_READ_CHARS)
            except ValueError:
                continue
            clipped = bool(data.get("clipped"))
            if clipped:
                clipped_paths.add(path)
            source.append(
                f"FILE: {path}\nCLIPPED: {'yes' if clipped else 'no'}\n{data.get('content', '')}"
            )

        system = (
            "You are RazaAI's bounded coding repair component. Return JSON only. "
            "Repair only files listed in ALLOWED FILES using the concrete verification "
            "errors. Preserve working behavior and project style. "
            "For a file shown with CLIPPED: no you may return mode=replace with complete "
            "corrected content. For a file shown with CLIPPED: yes you MUST use mode=patch "
            "with an exact unique old_text fragment copied from the shown source and the "
            "corrected new_text, because unseen source must be preserved. "
            "Do not claim success. "
            'Schema: {"files":[{"path":"relative/path","mode":"replace|patch",'
            '"content":"complete content for replace",'
            '"old_text":"exact fragment for patch","new_text":"replacement"}],'
            '"summary":"repair intent"}.'
            + "\n" + CODING_PERSONA
        )
        user = (
            f"ORIGINAL REQUEST: {request}\n"
            f"REPAIR PASS: {pass_number}/{self.MAX_REPAIR_PASSES}\n"
            f"ALLOWED FILES: {changed}\n"
            f"VERIFICATION FAILURES:\n{self._failure_evidence(checks)}\n\n"
            f"CURRENT CHANGED SOURCE:\n" + "\n\n".join(source)
        )

        result = self._chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        plan = self._extract_json(((result or {}).get("message") or {}).get("content") or "")

        allowed = set(changed)
        repaired = []
        rejected = []
        for item in list(plan.get("files") or [])[: self.MAX_PLAN_FILES]:
            path = str(item.get("path") or "").strip()
            if path not in allowed:
                rejected.append(f"{path or '<missing path>'}: not an allowed repair target")
                continue

            mode = str(item.get("mode") or "").strip().casefold()
            old_text = item.get("old_text")
            new_text = item.get("new_text")
            content = item.get("content")
            if not mode:
                mode = "patch" if isinstance(old_text, str) and old_text else "replace"

            if mode == "patch":
                if (
                    not isinstance(old_text, str) or not old_text
                    or not isinstance(new_text, str) or old_text == new_text
                ):
                    rejected.append(f"{path}: incomplete exact patch")
                    continue
                parse_error = self._would_not_parse(path, item)
                if parse_error:
                    rejected.append(f"{path}: repair rejected, result would not parse ({parse_error})")
                    continue
                try:
                    self.manager.patch_file(path, old_text, new_text)
                except (ValueError, OSError) as exc:
                    rejected.append(f"{path}: patch failed ({exc})")
                    continue
                repaired.append(path)
                continue

            if mode != "replace":
                rejected.append(f"{path}: unsupported repair mode {mode!r}")
                continue
            if path in clipped_paths:
                # The model never saw this file in full. Replacing it
                # would silently truncate unseen source.
                rejected.append(f"{path}: full replacement refused for clipped file; patch required")
                continue
            if not isinstance(content, str) or len(content.strip()) < 8:
                rejected.append(f"{path}: incomplete replacement content")
                continue
            if self._shrinks_too_much(path, content):
                rejected.append(
                    f"{path}: replacement would remove more than "
                    f"{int(self.MAX_SILENT_SHRINK_RATIO * 100)}% of the file; refused"
                )
                continue
            parse_error = self._would_not_parse(path, item)
            if parse_error:
                rejected.append(f"{path}: repair rejected, result would not parse ({parse_error})")
                continue
            self.manager.write_file(path, content, overwrite=True)
            repaired.append(path)

        self.last_repair_rejections = rejected
        return repaired

    def _simulate(self, path, item):
        """Post-operation content of a file for one plan item, without writing."""
        mode = str(item.get("mode") or "").casefold()
        if mode == "create":
            return str(item.get("content") or "")
        try:
            current = self.manager.read_file_exact(path)
        except (ValueError, OSError, UnicodeError):
            return None
        if mode == "replace":
            return str(item.get("content") or "")
        if mode == "append":
            content = item.get("content") if isinstance(item.get("content"), str) else str(item.get("new_text") or "")
            return current.rstrip("\n") + "\n\n\n" + content.strip("\n") + "\n"
        old, new = item.get("old_text"), item.get("new_text")
        if isinstance(old, str) and isinstance(new, str) and current.count(old) == 1:
            return current.replace(old, new, 1)
        return None

    def _symbol_loss_gaps(self, plan):
        """A replace/patch that silently drops existing functions or tests is a gap unless the request asked to rename/remove/rewrite. This is how 'add one function' was breaking four old tests: the model regenerated the test file from memory."""
        if self._rewrite_requested:
            return []
        import ast as _ast

        def names(text):
            try:
                tree = _ast.parse(text)
            except SyntaxError:
                return None
            return {n.name for n in _ast.walk(tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))}

        gaps = []
        for item in list(plan.get("files") or [])[: self.MAX_PLAN_FILES]:
            path = str(item.get("path") or "").strip()
            if not path.endswith(".py") or str(item.get("mode") or "").casefold() == "create":
                continue
            try:
                current = self.manager.read_file_exact(path)
            except (ValueError, OSError, UnicodeError):
                continue
            after = self._simulate(path, item)
            if after is None:
                continue
            before_names, after_names = names(current), names(after)
            if before_names is None or after_names is None:
                continue
            lost = sorted(before_names - after_names)
            if lost:
                gaps.append(
                    f"Your change to {path} removes existing definitions {lost}; the request did not ask to remove or rename "
                    "anything. Keep every existing function/test and ADD to the file with mode=patch"
                )
        return gaps

    def _would_not_parse(self, path, item):
        """Syntax message if applying this Python item would leave the file unparsable."""
        if not path.endswith((".py", ".pyi")):
            return None
        simulated = self._simulate(path, item)
        if simulated is None:
            return None
        import ast as _ast
        try:
            _ast.parse(simulated)
        except SyntaxError as exc:
            return f"{exc.msg} at line {exc.lineno}"
        return None

    # ---- Python completes mechanical steps the model keeps missing -------
    def _autofix_plan(self, plan, before_paths):
        """Return (plan, notes)."""
        import ast as _ast
        notes = []
        items = list(plan.get("files") or [])[: self.MAX_PLAN_FILES]
        fixed = []
        for item in items:
            path = str(item.get("path") or "").strip()
            mode = str(item.get("mode") or "").casefold()
            if not path.endswith(".py") or path not in before_paths:
                fixed.append(item); continue
            try:
                current = self.manager.read_file_exact(path)
            except (ValueError, OSError, UnicodeError):
                fixed.append(item); continue
            if mode == "patch":
                old, new = item.get("old_text"), item.get("new_text")
                # (5) substitution: old_text is an existing definition and new_text swaps it for a
                # different one ("add mul3" done as "replace mul2 with mul3"). Keep the old, add the new.
                if isinstance(old, str) and isinstance(new, str) and current.count(old) == 1 and not self._rewrite_requested:
                    old_defs = self._def_names(old)
                    new_defs = self._def_names(new)
                    if old_defs and old_defs - new_defs and new_defs - old_defs:
                        if self._is_top_level_defs(old.strip("\n") + "\n") and self._is_top_level_defs(new.strip("\n") + "\n"):
                            fixed.append({"path": path, "mode": "append", "content": new.strip("\n") + "\n"})
                            notes.append(f"{path}: the patch would have replaced {sorted(old_defs - new_defs)} with {sorted(new_defs - old_defs)}; the existing definition was kept and the new one appended")
                            continue
                        # Method-level inside a class: keep old method, add new after it
                        fixed.append({"path": path, "mode": "patch", "old_text": old, "new_text": old.rstrip("\n") + "\n\n" + new.strip("\n") + "\n"})
                        notes.append(f"{path}: the patch would have replaced {sorted(old_defs - new_defs)} with {sorted(new_defs - old_defs)}; both are kept")
                        continue
                if isinstance(old, str) and isinstance(new, str) and current.count(old) != 1 and new.startswith(old):
                    addition = new[len(old):]
                    if self._is_top_level_defs(addition):
                        fixed.append({"path": path, "mode": "append", "content": addition})
                        notes.append(f"{path}: the patch anchor was not found; the new top-level definition was appended instead")
                        continue
            if mode == "replace":
                content = str(item.get("content") or "")
                try:
                    before_defs = {n.name: n for n in _ast.parse(current).body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))}
                    after_tree = _ast.parse(content)
                except SyntaxError:
                    fixed.append(item); continue
                after_defs = [n for n in after_tree.body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))]
                after_names = {n.name for n in after_defs}
                lost = set(before_defs) - after_names
                new_defs = [n for n in after_defs if n.name not in before_defs]
                if lost and new_defs and not self._rewrite_requested:
                    lines = content.splitlines()
                    addition = "\n\n\n".join("\n".join(lines[n.lineno - 1: getattr(n, "end_lineno", n.lineno)]) for n in new_defs) + "\n"
                    fixed.append({"path": path, "mode": "append", "content": addition})
                    notes.append(f"{path}: the rewrite would have dropped {sorted(lost)}; only the new definition(s) {[n.name for n in new_defs]} were appended")
                    continue
                # Same at method level: a class present in both, where the rewrite drops
                # existing methods but adds new ones -> patch the new methods into the class.
                if not lost and not self._rewrite_requested:
                    converted = []
                    for cls_name, before_cls in before_defs.items():
                        if not isinstance(before_cls, _ast.ClassDef):
                            continue
                        after_cls = next((n for n in after_defs if isinstance(n, _ast.ClassDef) and n.name == cls_name), None)
                        if after_cls is None:
                            continue
                        b_methods = {n.name: n for n in before_cls.body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))}
                        a_methods = [n for n in after_cls.body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))]
                        lost_m = set(b_methods) - {n.name for n in a_methods}
                        new_m = [n for n in a_methods if n.name not in b_methods]
                        if lost_m and new_m:
                            cur_lines = current.splitlines()
                            last = before_cls.body[-1]
                            end = getattr(last, "end_lineno", last.lineno) - 1
                            start = max(0, end - 1)
                            anchor = None
                            while start >= 0:
                                frag = "\n".join(cur_lines[start:end + 1]) + "\n"
                                if current.count(frag) == 1:
                                    anchor = frag; break
                                start -= 1
                            if anchor is None:
                                continue
                            lines = content.splitlines()
                            methods_src = "\n\n".join("\n".join(lines[n.lineno - 1: getattr(n, "end_lineno", n.lineno)]) for n in new_m)
                            converted.append({"path": path, "mode": "patch", "old_text": anchor, "new_text": anchor + "\n" + methods_src + "\n"})
                            notes.append(f"{path}: the rewrite would have dropped methods {sorted(lost_m)} from class {cls_name}; only {[n.name for n in new_m]} were added to the class")
                    if converted:
                        fixed.extend(converted)
                        continue
            fixed.append(item)
        plan = {**plan, "files": fixed}

        # Missing imports: add the name to the existing `from <module> import ...` line
        merged = self._merged_contents(plan)
        extra = []
        for gap in self._undefined_name_gaps(plan):
            m = re.match(r"(\w+) in (\S+) uses `(\w+)`.*\(it is defined in ([^)]+)\); patch the import line \(old_text=(\"(?:[^\"\\]|\\.)*\")\)", gap)
            if not m:
                continue
            _, path, name, defined_in, anchor_json = m.groups()
            try:
                anchor = json.loads(anchor_json)
            except ValueError:
                continue
            module_stems = {Path(p.strip()).stem for p in defined_in.split(",")}
            im = re.match(r"from (\S+) import (.+)\n", anchor)
            if not im or im.group(1).split(".")[-1] not in module_stems:
                continue
            names = [n.strip() for n in im.group(2).split(",") if n.strip()]
            if name in names:
                continue
            new_line = f"from {im.group(1)} import {', '.join(names + [name])}\n"
            extra.append({"path": path, "mode": "patch", "old_text": anchor, "new_text": new_line})
            notes.append(f"{path}: added `{name}` to `{anchor.strip()}`")
        if extra:
            plan = {**plan, "files": extra + plan["files"]}
        return plan, notes

    @staticmethod
    def _def_names(text):
        """Names of function/class definitions in a fragment (tolerates method indentation)."""
        import ast as _ast
        import textwrap as _tw
        try:
            tree = _ast.parse(_tw.dedent(text))
        except SyntaxError:
            return set()
        return {n.name for n in _ast.walk(tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))}

    @staticmethod
    def _is_top_level_defs(text):
        import ast as _ast
        try:
            tree = _ast.parse(text)
        except SyntaxError:
            return False
        return bool(tree.body) and all(isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)) for n in tree.body)

    def _merged_contents(self, plan):
        merged = {}
        for item in list(plan.get("files") or [])[: self.MAX_PLAN_FILES]:
            path = str(item.get("path") or "").strip()
            base = merged.get(path)
            if base is None:
                simulated = self._simulate(path, item)
            else:
                mode = str(item.get("mode") or "").casefold()
                old, new = item.get("old_text"), item.get("new_text")
                if mode == "append":
                    content = item.get("content") if isinstance(item.get("content"), str) else str(item.get("new_text") or "")
                    simulated = base.rstrip("\n") + "\n\n\n" + content.strip("\n") + "\n"
                else:
                    simulated = base.replace(old, new, 1) if isinstance(old, str) and isinstance(new, str) and base.count(old) == 1 else base
            if simulated is not None:
                merged[path] = simulated
        return merged

    def _undefined_name_gaps(self, plan):
        """New code that uses a name the module never binds (the classic 'forgot to add it to the import line') is a gap, with the import line handed back as the anchor. Catches NameError before any proposal."""
        import ast as _ast
        import builtins as _builtins
        gaps = []
        merged = {}
        originals = {}
        for item in list(plan.get("files") or [])[: self.MAX_PLAN_FILES]:
            path = str(item.get("path") or "").strip()
            if not path.endswith(".py"):
                continue
            base = merged.get(path)
            if base is None:
                try:
                    originals[path] = self.manager.read_file_exact(path) if str(item.get("mode") or "").casefold() != "create" else ""
                except (ValueError, OSError, UnicodeError):
                    originals[path] = ""
                simulated = self._simulate(path, item)
            else:
                old, new = item.get("old_text"), item.get("new_text")
                mode = str(item.get("mode") or "").casefold()
                if mode == "append":
                    content = item.get("content") if isinstance(item.get("content"), str) else str(item.get("new_text") or "")
                    simulated = base.rstrip("\n") + "\n\n\n" + content.strip("\n") + "\n"
                else:
                    simulated = base.replace(old, new, 1) if isinstance(old, str) and isinstance(new, str) and base.count(old) == 1 else base
            if simulated is None:
                continue
            merged[path] = simulated

        def bound_names(tree):
            names = set(dir(_builtins))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    for alias in node.names:
                        names.add((alias.asname or alias.name).split(".")[0])
                elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    names.add(node.name)
                elif isinstance(node, _ast.Name) and isinstance(node.ctx, _ast.Store):
                    names.add(node.id)
                elif isinstance(node, _ast.arg):
                    names.add(node.arg)
                elif isinstance(node, (_ast.For, _ast.comprehension)):
                    pass
            return names

        for path, text in merged.items():
            try:
                before_tree = _ast.parse(originals.get(path) or "")
                after_tree = _ast.parse(text)
            except SyntaxError:
                continue
            before_funcs = {n.name for n in _ast.walk(before_tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))}
            bound = bound_names(after_tree)
            missing = {}
            for node in _ast.walk(after_tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and node.name not in before_funcs:
                    local = {a.arg for a in node.args.args + node.args.kwonlyargs} | ({node.args.vararg.arg} if node.args.vararg else set()) | ({node.args.kwarg.arg} if node.args.kwarg else set())
                    for sub in _ast.walk(node):
                        if isinstance(sub, _ast.Name) and isinstance(sub.ctx, _ast.Load) and sub.id not in bound and sub.id not in local:
                            missing.setdefault(sub.id, node.name)
            if missing:
                lines_ = text.splitlines()
                # Prefer a `from <workspace module> import ...` line that already defines the name's sibling.
                from_lines = [l for l in lines_ if l.startswith("from ") and " import " in l and not l.startswith(("from unittest", "from typing", "from __future__"))]
                other = [l for l in lines_ if l.startswith(("from ", "import "))]
                for name, func in missing.items():
                    defined_in = [p for p, body in merged.items() if p != path and f"def {name}(" in body or f"class {name}" in body]
                    candidates = [l for l in from_lines if defined_in and any(Path(p).stem in l for p in defined_in)] or from_lines or other
                    anchor = json.dumps(candidates[0] + "\n") if candidates else "(no import line yet — add one at the top)"
                    where = f" (it is defined in {', '.join(defined_in)})" if defined_in else ""
                    gaps.append(
                        f"{func} in {path} uses `{name}`, which is not imported or defined in that file{where}; "
                        f"patch the import line (old_text={anchor}) to include it"
                    )
        return gaps

    def _syntax_gaps(self, plan):
        """A plan whose result does not parse is sent back with the exact error."""
        import ast as _ast
        gaps = []
        merged = {}
        for item in list(plan.get("files") or [])[: self.MAX_PLAN_FILES]:
            path = str(item.get("path") or "").strip()
            if not path.endswith((".py", ".pyi")):
                continue
            base = merged.get(path)
            if base is None:
                simulated = self._simulate(path, item)
            else:
                old, new = item.get("old_text"), item.get("new_text")
                simulated = base.replace(old, new, 1) if isinstance(old, str) and isinstance(new, str) and base.count(old) == 1 else base
            if simulated is None:
                continue
            merged[path] = simulated
        for path, text in merged.items():
            try:
                _ast.parse(text)
            except SyntaxError as exc:
                line = (text.splitlines()[exc.lineno - 1] if exc.lineno and exc.lineno - 1 < len(text.splitlines()) else "").strip()
                gaps.append(
                    f"After your patch, {path} does not parse: {exc.msg} at line {exc.lineno} "
                    f"({line[:80]!r}). Fix the indentation/quoting so the file is valid Python"
                )
        return gaps

    def _shrinks_too_much(self, path, new_content):
        try:
            current = self.manager.read_file(path, max_chars=60000)
        except (ValueError, OSError):
            return False
        before = int(current.get("chars") or 0)
        if before < 400:
            return False
        after = len(new_content)
        return after < before * (1.0 - self.MAX_SILENT_SHRINK_RATIO)

    def _git_branch_name(self):
        try:
            result = self.manager.git_branch()
        except (ValueError, OSError):
            return None
        return result.get("current") if not result.get("exit_code") else None

    def _git_evidence(self):
        try:
            status = self.manager.git_status()
        except (ValueError, OSError):
            status = None
        try:
            diff = self.manager.git_diff()
        except (ValueError, OSError):
            diff = None

        if status and int(status.get("exit_code", 1)) != 0:
            status = None
        if diff and int(diff.get("exit_code", 1)) != 0:
            diff = None
        return {"status": status, "diff": diff}

    @staticmethod
    def _format_check(check):
        label = " ".join(str(part) for part in check.get("command") or [])
        code = int(check.get("exit_code", 1))
        if code == 0:
            return f"- PASS: `{label}`"
        output = str(check.get("stderr") or check.get("stdout") or "").strip()
        detail = output.splitlines()[-1] if output else f"exit {code}"
        return f"- FAIL: `{label}` — {detail[:300]}"

    def _final_report(
        self,
        *,
        before_paths,
        written,
        checks,
        plan,
        errors,
        git_evidence,
        repair_passes,
        rolled_back=None,
    ):
        if rolled_back is not None:
            lines = [
                "Verification: FAILED after "
                f"{repair_passes} automatic repair pass(es); the workspace was restored "
                "to its pre-task state.",
            ]
            lines.extend(self._format_check(item) for item in checks)
            lines.append(
                f"Restored: {', '.join(f'`{p}`' for p in rolled_back.get('restored') or []) or 'nothing'}"
            )
            for item in rolled_back.get("failures") or []:
                lines.append(f"- Rollback failure: {item}")
            summary = str(plan.get("summary") or "").strip()
            if summary:
                lines.append(f"Attempted: {summary}")
            if errors:
                lines.append("Guarded plan items:")
                lines.extend(f"- {item}" for item in errors[:6])
            lines.append("No files were changed. I am not claiming the task is complete.")
            return "\n".join(lines)

        after = self._list()
        actual = {
            item.get("path")
            for item in after.get("entries") or []
            if item.get("type") == "file"
        }
        confirmed = list(dict.fromkeys(path for path in written if path in actual))
        if not confirmed:
            return (
                "The requested workspace changes could not be confirmed on disk. "
                "I will not claim that files were created or modified."
            )

        created = [path for path in confirmed if path not in before_paths]
        updated = [path for path in confirmed if path in before_paths]

        lines = []
        if created:
            lines.append("Created:")
            lines.extend(f"- `{path}`" for path in created)
        if updated:
            lines.append("Updated:")
            lines.extend(f"- `{path}`" for path in updated)

        if checks:
            if self._verification_ok(checks):
                lines.append("Verification: PASS")
            else:
                lines.append("Verification: FAILED")
            lines.extend(self._format_check(item) for item in checks)
            sandboxes = {str(item.get("sandbox") or "unknown") for item in checks}
            lines.append("Sandbox: " + ", ".join(sorted(sandboxes)))
            notes = {str(item["sandbox_note"]) for item in checks if item.get("sandbox_note")}
            lines.extend(f"- {note}" for note in sorted(notes))
        else:
            lines.append(
                "Verification: no executable project check was applicable; "
                "filesystem writes were confirmed."
            )

        if repair_passes:
            lines.append(f"Automatic repair passes: {repair_passes}")

        branch = self._git_branch_name()
        if branch:
            lines.append(f"Git branch: `{branch}`")
        status = (git_evidence.get("status") or {}).get("stdout", "").strip()
        if status:
            lines.append("Git status:")
            lines.append("```text\n" + status[-2200:] + "\n```")

        diff = (git_evidence.get("diff") or {}).get("stdout", "").strip()
        if diff:
            # Give useful evidence without flooding the 4096-context TUI.
            diff_lines = diff.splitlines()
            plus = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
            minus = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
            lines.append(f"Git diff: +{plus} / -{minus} lines.")

        summary = str(plan.get("summary") or "").strip()
        if summary:
            lines.append(summary)
        if self.last_context is not None and self.last_context.files:
            lines.append("Context given to the planner: " + ", ".join(f"`{p}`" for p in self.last_context.files[:8]))

        if errors:
            lines.append("Skipped/guarded plan items:")
            lines.extend(f"- {item}" for item in errors[:5])

        if checks and not self._verification_ok(checks):
            lines.append(
                "The changes remain in the workspace for review, but I am not "
                "claiming the task is complete because verification is failing."
            )

        return "\n".join(lines)

    def show_code(self):
        listing = self._list()
        files = [
            item.get("path")
            for item in listing.get("entries") or []
            if item.get("type") == "file"
            and Path(str(item.get("path") or "")).suffix.casefold() in _CODE_EXTENSIONS
        ]
        if not files:
            return "The active coding workspace contains no readable code/text files."
        sections = [f"Workspace: `{self.manager.root}`"]
        for path in files[:8]:
            try:
                result = self.manager.read_file(path, max_chars=10000)
            except ValueError as exc:
                sections.append(f"`{path}`: {exc}")
                continue
            suffix = Path(path).suffix.lstrip(".") or "text"
            sections.append(
                f"### {path}\n```{suffix}\n{result.get('content', '')}\n```"
            )
        if len(files) > 8:
            sections.append(f"{len(files) - 8} additional files were not displayed.")
        return "\n\n".join(sections)

    def describe_workspace(self):
        listing = self._list()
        profile = self._project_profile(listing)
        entries = listing.get("entries") or []
        lines = [f"Active coding workspace: `{self.manager.root}`"]
        if not entries:
            lines.append("The workspace is currently empty.")
            return "\n".join(lines)
        lines.append(
            "Project: "
            + (", ".join(profile["languages"]) if profile["languages"] else "text/mixed")
            + (
                f" · frameworks: {', '.join(profile['frameworks'])}"
                if profile["frameworks"] else ""
            )
            + f" · tests: {'yes' if profile['has_tests'] else 'no'}"
            + f" · git: {'yes' if profile['git'] else 'no'}"
        )
        if "python" in profile["languages"]:
            lines.append(f"Python interpreter: {profile['python_interpreter']}")
        lines.append("Files:")
        lines.extend(f"- {item.get('path')}" for item in entries[:100])
        return "\n".join(lines)

    def git_status(self):
        result = self.manager.git_status()
        if int(result.get("exit_code", 1)) != 0:
            return "This workspace is not currently available as a readable Git repository."
        output = str(result.get("stdout") or "").strip()
        return "Git status is clean." if not output else f"Git status:\n```text\n{output}\n```"

    def git_branch(self):
        result = self.manager.git_branch()
        if result.get("exit_code"):
            return "This workspace is not currently available as a readable Git repository."
        lines = [f"Current branch: `{result['current']}`"]
        others = [b for b in result["branches"] if b != result["current"]]
        if others:
            lines.append("Other local branches: " + ", ".join(f"`{b}`" for b in others))
        return "\n".join(lines)

    def git_diff(self):
        result = self.manager.git_diff()
        if int(result.get("exit_code", 1)) != 0:
            return "This workspace is not currently available as a readable Git repository."
        output = str(result.get("stdout") or "").strip()
        return "There is no unstaged Git diff." if not output else f"```diff\n{output[-12000:]}\n```"

    def run_project_checks(self):
        listing = self._list()
        profile = self._project_profile(listing)
        commands = self._verification_commands(profile)
        if not commands:
            # Still give Python projects a meaningful compile check.
            if "python" in profile["languages"]:
                commands = [["python3", "-m", "compileall", "-q", "."]]
            else:
                return "No supported automatic test/build command was detected for this workspace."

        try:
            with self.manager.verification_workspace() as verify_manager:
                checks = [verify_manager.run_command(command, timeout=60) for command in commands]
                for item in checks:
                    item["verification_isolated"] = True
        except (OSError, ValueError) as exc:
            checks = [{
                "command": ["verification-isolation"], "cwd": ".", "exit_code": 125,
                "stdout": "", "stderr": f"Could not create isolated verification workspace: {exc}",
                "sandbox": "isolation-failed", "verification_isolated": False,
            }]
        lines = ["Project verification:"]
        lines.extend(self._format_check(item) for item in checks)
        lines.append(
            "Overall: **PASS**" if self._verification_ok(checks) else "Overall: **FAILED**"
        )
        return "\n".join(lines)

    def _sanitize_explicit_target_plan(self, request, plan, before_paths):
        """Drop planner file drift that Python can prove is outside explicit targets."""
        targets = explicit_request_paths(request, before_paths)
        if not targets:
            return plan, []
        from .explore import rename_old_identifiers

        rename_old = rename_old_identifiers(request)
        allowed_by_rename = set()
        if rename_old:
            for path in before_paths:
                try:
                    text = str(self.manager.read_file(path) or "").casefold()
                except Exception:  # noqa: BLE001 - unreadable files cannot be proven targets
                    continue
                if any(name in text for name in rename_old):
                    allowed_by_rename.add(normalize_path_token(str(path)))
        kept = []
        rejected = []
        for item in list(plan.get("files") or [])[: self.MAX_PLAN_FILES]:
            candidate = normalize_path_token(str(item.get("path") or ""))
            probe = plan_gaps(request, {"files": [{"path": candidate}]}, before_paths)
            if any("do not modify unrelated path" in gap for gap in probe):
                if candidate and candidate in allowed_by_rename:
                    kept.append(item)
                    continue
                if candidate:
                    rejected.append(candidate)
                continue
            kept.append(item)
        if not rejected:
            return plan, []
        # The model's summary may itself claim the rejected work is required. Use
        # the user's request as the authoritative intent after sanitization.
        cleaned = {**plan, "files": kept, "summary": str(request).strip()}
        return cleaned, sorted(set(rejected))

    def handle(self, request):
        value = self._normalize_request_typo(request).strip()
        lower = value.casefold()

        if re.search(r"^\s*(?:what|which)\b.{0,24}\b(?:workspace|directory|folder|project)\b", lower):
            return self.describe_workspace()
        if re.search(r"^\s*(?:show|display|read|open)\b.{0,28}\b(?:code|source)\b", lower):
            return self.show_code()
        if re.search(r"^\s*(?:list|show)\b.{0,20}\b(?:files|workspace)\b", lower):
            return self.describe_workspace()
        if re.search(r"\bgit\s+status\b|^\s*status\s*$", lower):
            return self.git_status()
        if re.search(r"\bgit\s+diff\b|^\s*(?:show\s+)?diff\s*$", lower):
            return self.git_diff()
        if re.search(r"\bgit\s+branch\b|\b(?:current|which|what)\s+(?:git\s+)?branch\b|\bwhat branch\b", lower):
            return self.git_branch()
        if re.search(r"\b(?:what|which|show|why)\b.{0,40}\b(?:error|failed|failure|went wrong|exception)\b|\blast error\b", lower):
            return self.last_error_report()
        if re.search(
            r"\b(?:run|execute|check|verify)\b.{0,24}\b(?:tests?|pytest|unittest|build|lint|compile)\b",
            lower,
        ):
            return self.run_project_checks()

        before = self._list()
        before_paths = set(self._file_paths(before))
        profile = self._project_profile(before)

        try:
            plan = self._planner(value, before, profile)
        except self.PlanTruncated as exc:
            # Retry once asking for a compact plan (patches, not whole files).
            self.session.record("plan-truncated", str(exc))
            try:
                plan = self._planner(
                    value, before, profile,
                    gaps=[f"Your previous reply was cut off before the JSON was complete ({exc}). "
                          "Return a SHORTER plan: use mode=patch with small old_text/new_text fragments "
                          "instead of whole-file content, and omit the purpose field."],
                    previous_plan={"files": [], "summary": "truncated"},
                )
            except self.PlanTruncated as exc2:
                self._remember_error(f"plan truncated twice: {exc2}")
                return f"I did not change the workspace. The coding plan was cut off twice ({exc2}); try a smaller request."
        files = list(plan.get("files") or [])[: self.MAX_PLAN_FILES]
        if not files:
            # An empty plan is a gap, not an answer :  one retry with the reason.
            reason = str(plan.get("summary") or "").strip()
            try:
                plan = self._planner(
                    value, before, profile,
                    gaps=[f"The plan contained no file changes ({reason or 'no summary given'}); the request requires "
                          "concrete create/patch operations on the files shown"],
                    previous_plan=plan,
                )
            except (ValueError, json.JSONDecodeError):
                plan = {"files": [], "summary": reason}
            files = list(plan.get("files") or [])[: self.MAX_PLAN_FILES]
            if not files:
                self._remember_error(f"planner proposed no files twice: {reason or 'no reason given'}")
                return f"I did not change the workspace. {reason or 'The coding planner proposed no files.'}"

        self._rewrite_requested = bool(self._REWRITE_RE.search(value))
        # Python checks the plan against the request before anyone sees it.
        # invalid patch anchors are gaps too :  fix them before proposing.
        def _all_gaps(candidate):
            _, validation_errors = self._validate_plan(candidate, before_paths)
            return plan_gaps(value, candidate, before_paths) + [
                e for e in validation_errors
                if "Patch anchor" in e or "incomplete exact patch" in e or "syntax" in e.casefold()
            ] + self._syntax_gaps(candidate) + self._symbol_loss_gaps(candidate) + self._undefined_name_gaps(candidate)

        plan, autofix_notes = self._autofix_plan(plan, before_paths)
        target_rejections = []
        gaps = _all_gaps(plan)
        retries = 0
        while gaps and retries < self.MAX_COMPLETENESS_RETRIES:
            retries += 1
            try:
                retry_plan = self._planner(value, before, profile, gaps=gaps, previous_plan=plan)
            except (ValueError, json.JSONDecodeError):  # Includes PlanTruncated: keep the plan we have
                break
            if list(retry_plan.get("files") or []):
                plan, more_notes = self._autofix_plan(retry_plan, before_paths)
                autofix_notes = more_notes
                files = list(plan.get("files") or [])[: self.MAX_PLAN_FILES]
            gaps = _all_gaps(plan)

        # Preserve the existing one-shot planner correction opportunity. Only
        # after that retry is exhausted does Python remove provably unrelated
        # explicit-target drift from the final proposal/completeness state.
        plan, target_rejections = self._sanitize_explicit_target_plan(value, plan, before_paths)
        gaps = _all_gaps(plan)
        self.last_gaps = gaps
        self.last_autofix = autofix_notes
        if gaps:
            self.session.record("incomplete-plan", "; ".join(gaps)[:200])

        operations, errors = self._validate_plan(plan, before_paths)
        if target_rejections:
            errors.append(
                "Rejected planner operations outside the explicit target: "
                + ", ".join(target_rejections)
            )
        explicit_targets = set(explicit_request_paths(value, before_paths))
        if explicit_targets:
            # Fail closed even if the small model ignored retry guidance. Tests are
            # permitted only when plan_gaps established real test intent; unrelated
            # operations are never allowed to reach proposal/apply.
            target_gaps = plan_gaps(value, {"files": operations}, before_paths)
            if any("do not modify unrelated path" in gap for gap in target_gaps):
                allowed_ops = []
                rejected = []
                for op in operations:
                    candidate = normalize_path_token(op.get("path"))
                    probe = plan_gaps(value, {"files": [{"path": candidate}]}, before_paths)
                    if any("do not modify unrelated path" in gap for gap in probe):
                        rejected.append(candidate)
                    else:
                        allowed_ops.append(op)
                operations = allowed_ops
                if rejected:
                    errors.append(
                        "Rejected planner operations outside the explicit target: "
                        + ", ".join(sorted(set(rejected)))
                    )
        if not operations:
            detail = "; ".join(errors) if errors else "No valid file writes were produced."
            self._remember_error(detail)
            return f"I did not change the workspace. {detail}"

        if self.require_approval:
            # A new proposal supersedes any older unapproved proposal for this
            # workspace, but never silently applies it.
            if self.pending and self.pending.get("txid"):
                self.journal.update(self.pending["txid"], "rejected", superseded=True)
            txid = self.journal.create_proposal(
                request=value, operations=operations, errors=errors, plan=plan,
                before_paths=before_paths, summary=plan.get("summary"),
            )
            self.pending = {
                "txid": txid, "request": value, "operations": operations, "errors": errors,
                "plan": plan, "before_paths": before_paths, "summary": plan.get("summary"),
            }
            return self._render_proposal(operations, errors, str(plan.get("summary") or "").strip())

        txid = self.journal.create_direct(
            request=value, operations=operations, errors=errors, plan=plan,
            before_paths=before_paths, summary=plan.get("summary"),
        )
        return self._apply_and_verify(
            request=value, operations=operations, errors=errors, plan=plan, before_paths=before_paths, txid=txid,
        )

    def _apply_and_verify(self, *, request, operations, errors, plan, before_paths, txid=None):
        value = request
        if txid is None:
            txid = self.journal.create_direct(
                request=value, operations=operations, errors=errors, plan=plan,
                before_paths=before_paths, summary=plan.get("summary"),
            )
        written, apply_errors, snapshot = self._apply_operations(operations, txid=txid)
        errors = list(errors) + list(apply_errors)
        if not written:
            detail = "; ".join(errors) if errors else "No valid file writes were produced."
            self._remember_error(detail)
            return f"I did not change the workspace. {detail}"
        self._last_summary = str(plan.get("summary") or "").strip() or None

        # Re-profile after writes so newly created test/build manifests affect verification.
        after_write = self._list()
        verify_profile = self._project_profile(after_write)
        self.journal.update(txid, "verifying", written=list(written), summary=self._last_summary or "")
        checks = self._run_verification(
            written, verify_profile, request=value, before_paths=before_paths
        )

        repair_passes = 0
        while (
            checks
            and not self._verification_ok(checks)
            and not any(self.manager.is_sandbox_error(item) for item in checks)
            and repair_passes < self.MAX_REPAIR_PASSES
        ):
            repair_passes += 1
            self.journal.update(txid, "repairing", repair_pass=repair_passes, written=list(written))
            try:
                repaired = self._repair(value, written, checks, repair_passes)
            except (ValueError, OSError, json.JSONDecodeError):
                repaired = []
            if not repaired:
                break
            self.journal.update(txid, "verifying", repair_pass=repair_passes, written=list(written))
            checks = self._run_verification(
                written, self._project_profile(self._list()),
                request=value, before_paths=before_paths,
            )

        self._trace("outcome", request=value, written=written, passed=bool(checks) and self._verification_ok(checks),
                    checks=[self._format_check(i) for i in checks], plan=plan)
        rolled_back = None
        if checks and not self._verification_ok(checks) and self.ROLLBACK_ON_FAILED_VERIFICATION:
            rolled_back = self._rollback_snapshot(snapshot)
            errors = list(errors) + list(getattr(self, "last_repair_rejections", []) or [])
            self.journal.update(
                txid, "rolled_back" if not rolled_back["failures"] else "failed",
                verification_passed=False, restored=rolled_back["restored"],
                rollback_failures=rolled_back["failures"], repair_passes=repair_passes,
            )
        else:
            # /undo is deliberately one level deep. Once a newer task verifies,

            # Longer an undo candidate, matching the in-memory semantics.
            previous_verified = self.journal.latest(frozenset({"verified"}))
            if previous_verified is not None and previous_verified.get("id") != txid:
                self.journal.update(previous_verified["id"], "superseded")
            self.last_applied = {
                "txid": txid, "snapshot": snapshot, "written": written, "summary": self._last_summary
            }
            self.journal.update(
                txid, "verified", verification_passed=True, written=list(written),
                summary=self._last_summary or "", repair_passes=repair_passes,
            )
            self.session.record("applied", self._last_summary or value, touched=written)
        if rolled_back is not None:
            first_fail = next((self._format_check(i) for i in checks if int(i.get("exit_code", 1)) != 0), "verification failed")
            self.session.record("verification-failed", first_fail, touched=written)
            failing = [self._format_check(i) for i in checks if int(i.get("exit_code", 1)) != 0]
            self.last_error = "Verification failed and the workspace was restored:\n" + "\n".join(failing)

        git_evidence = self._git_evidence()
        return self._final_report(
            before_paths=before_paths,
            written=written,
            checks=checks,
            plan=plan,
            errors=errors,
            git_evidence=git_evidence,
            repair_passes=repair_passes,
            rolled_back=rolled_back,
        )
