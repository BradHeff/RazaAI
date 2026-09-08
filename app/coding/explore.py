"""Workspace exploration for the coding coworker."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_STOP = {
    "the", "and", "with", "from", "that", "this", "into", "make", "create", "build",
    "implement", "please", "code", "app", "application", "project", "file", "files",
    "change", "update", "fix", "add", "for", "its", "it", "a", "an", "to", "of", "in",
    "on", "function", "functions", "method", "class", "module", "new", "also", "then",
    "unittest", "unit", "test", "tests", "testing",
}
_CODE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".vue", ".svelte"}
_SMALL_FILE_CHARS = 2500

# Explicit path mentions are Python-owned routing evidence. Small
# coder models must not be allowed to reinterpret ``app/main.py`` as a vague
# semantic hint and then edit an unrelated high-scoring file.
_PATH_SUFFIXES = _CODE_SUFFIXES | {".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".sh", ".cfg", ".conf", ".ini"}


def normalize_path_token(value: str) -> str:
    """Normalize harmless CLI/Markdown escaping in a relative path token."""
    token = str(value or "").strip().strip("`\"'")
    token = token.rstrip(".,;:!?)]}")
    token = token.lstrip("([{")
    # Terminal transcripts / small models sometimes escape punctuation as if
    # rendering Markdown (wow\.py, test\_x.py). Linux project paths in RazaAI
    # are POSIX relative paths, so canonicalize those presentation escapes.
    token = re.sub(r"\\([._/\-])", r"\1", token)
    while token.startswith("./"):
        token = token[2:]
    return token


def explicit_request_paths(request: str, files=()) -> list[str]:
    """Return canonical path-like targets explicitly named by the user."""
    file_list = [str(p) for p in files]
    file_set = set(file_list)
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in file_list:
        by_name[Path(path).name].append(path)

    # Capture whitespace-delimited / quoted tokens, then require a known file
    # suffix. This intentionally avoids treating ordinary prose as a path.
    raw_tokens = re.findall(r"`[^`]+`|\"[^\"]+\"|'[^']+'|[^\s,;:()]+", str(request or ""))
    found: list[str] = []
    for raw in raw_tokens:
        token = normalize_path_token(raw)
        if not token or Path(token).suffix.casefold() not in _PATH_SUFFIXES:
            continue
        if Path(token).is_absolute() or ".." in Path(token).parts:
            continue
        canonical = token
        if token not in file_set and "/" not in token:
            matches = by_name.get(Path(token).name, [])
            if len(matches) == 1:
                canonical = matches[0]
        if canonical not in found:
            found.append(canonical)
    return found


# Symbols


@dataclass
class Symbol:
    path: str
    name: str
    kind: str
    start: int
    end: int
    signature: str = ""


_JS_DEF = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>)", re.M)
_GO_DEF = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.M)
_RS_DEF = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:fn|struct|enum|trait|impl)\s+(\w+)", re.M)


class SymbolIndex:
    def __init__(self, manager):
        self.manager = manager
        self._by_file: dict[str, list[Symbol]] = {}
        self._text: dict[str, str] = {}

    def _read(self, path: str) -> str | None:
        if path in self._text:
            return self._text[path]
        try:
            data = self.manager.read_file(path, max_chars=60000)
        except (ValueError, OSError, UnicodeError):
            self._text[path] = None
            return None
        text = data.get("content") if not data.get("clipped") else data.get("content")
        self._text[path] = text or ""
        return self._text[path]

    def symbols(self, path: str) -> list[Symbol]:
        if path in self._by_file:
            return self._by_file[path]
        text = self._read(path) or ""
        suffix = Path(path).suffix.casefold()
        found: list[Symbol] = []
        if suffix in {".py", ".pyi"}:
            try:
                tree = ast.parse(text)
            except SyntaxError:
                tree = None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        end = getattr(node, "end_lineno", node.lineno)
                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        sig = text.splitlines()[node.lineno - 1].strip() if node.lineno - 1 < len(text.splitlines()) else node.name
                        found.append(Symbol(path, node.name, kind, node.lineno, end, sig))
        else:
            pattern = {".go": _GO_DEF, ".rs": _RS_DEF}.get(suffix, _JS_DEF)
            lines = text.splitlines()
            for m in pattern.finditer(text):
                name = next((g for g in m.groups() if g), None)
                if not name:
                    continue
                start = text.count("\n", 0, m.start()) + 1
                # Crude end: next definition or EOF, capped
                end = min(len(lines), start + 60)
                for m2 in pattern.finditer(text, m.end()):
                    end = text.count("\n", 0, m2.start())
                    break
                found.append(Symbol(path, name, "definition", start, max(start, end), lines[start - 1].strip()))
        found.sort(key=lambda s: s.start)
        self._by_file[path] = found
        return found

    def body(self, symbol: Symbol, max_chars: int = 2400) -> str:
        text = self._read(symbol.path) or ""
        lines = text.splitlines()
        chunk = "\n".join(lines[symbol.start - 1: symbol.end])
        if len(chunk) > max_chars:
            chunk = chunk[:max_chars].rstrip() + "\n# ... (clipped)"
        return chunk

    def outline(self, path: str) -> str:
        syms = self.symbols(path)
        if not syms:
            return ""
        return "\n".join(f"  L{s.start}-{s.end} {s.kind} {s.name}: {s.signature[:90]}" for s in syms[:40])


# Relations


def _module_name(path: str) -> str:
    p = Path(path)
    if p.suffix not in {".py", ".pyi"}:
        return ""
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def import_graph(index: SymbolIndex, files: list[str]) -> dict[str, set[str]]:
    """Importer -> {imported workspace modules (as file paths)}."""
    modules = {_module_name(f): f for f in files if _module_name(f)}
    graph: dict[str, set[str]] = defaultdict(set)
    for path in files:
        if Path(path).suffix not in {".py", ".pyi"}:
            continue
        text = index._read(path) or ""
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                for candidate in (name, name.rsplit(".", 1)[0] if "." in name else None):
                    if candidate and candidate in modules and modules[candidate] != path:
                        graph[path].add(modules[candidate])
    return graph


def test_pairs(files: list[str]) -> dict[str, set[str]]:
    """Source <-> tests, both directions, by conventional naming."""
    pairs: dict[str, set[str]] = defaultdict(set)
    stems = {Path(f).stem: f for f in files if Path(f).suffix in _CODE_SUFFIXES}
    for f in files:
        stem = Path(f).stem
        m = re.match(r"^(?:test_)?(.+?)(?:_test|\.test|\.spec|_spec)?$", stem)
        base = m.group(1) if m else stem
        is_test = stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec", "_spec")) or "/tests/" in f"/{f}"
        if is_test:
            src = stems.get(base)
            if src and src != f:
                pairs[f].add(src)
                pairs[src].add(f)
    return pairs


# Search


def request_terms(request: str) -> list[str]:
    terms = []
    for term in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{1,}", str(request or "")):
        low = term.casefold()
        if low in _STOP or len(low) < 2:
            continue
        if low not in terms:
            terms.append(low)
    return terms[:12]


def term_search(manager, terms: list[str], max_hits: int = 40) -> dict[str, int]:
    """Path -> hit count for any term; ripgrep when available, else Python scan."""
    if not terms:
        return {}
    hits: dict[str, int] = defaultdict(int)
    root = str(manager.root)
    if shutil.which("rg"):
        pattern = "|".join(re.escape(t) for t in terms)
        try:
            proc = subprocess.run(
                ["rg", "-i", "-c", "--no-messages", "-g", "!.git", "-g", "!node_modules", "-g", "!__pycache__",
                 "-g", "!*.pyc", "-e", pattern, "."],
                cwd=root, capture_output=True, text=True, timeout=20,
            )
            for line in proc.stdout.splitlines():
                path, _, count = line.rpartition(":")
                if path and count.isdigit():
                    hits[path[2:] if path.startswith("./") else path] += int(count)
            return dict(sorted(hits.items(), key=lambda kv: -kv[1])[:max_hits])
        except (OSError, subprocess.TimeoutExpired):
            pass
    listing = manager.list_files(".", recursive=True, max_entries=500)
    lowered = [t.casefold() for t in terms]
    for item in listing.get("entries") or []:
        if item.get("type") != "file":
            continue
        path = item["path"]
        if Path(path).suffix.casefold() not in _CODE_SUFFIXES | {".md", ".txt", ".toml", ".json", ".yaml", ".yml"}:
            continue
        try:
            text = manager.read_file(path, max_chars=60000)["content"].casefold()
        except (ValueError, OSError, UnicodeError):
            continue
        count = sum(text.count(t) for t in lowered)
        if count:
            hits[path] = count
    return dict(sorted(hits.items(), key=lambda kv: -kv[1])[:max_hits])


# Patch anchors: Python hands the planner guaranteed-unique old_text
# fragments so it never has to guess where to insert.


def patch_anchors(text: str, path: str) -> str:
    if not path.endswith((".py", ".pyi")) or not text.strip():
        return ""
    lines = text.splitlines()
    hints = []

    def unique_tail(end_line_idx, want=2):
        # The last `want` lines up to end_line_idx (0-based), grown until unique in the file
        start = max(0, end_line_idx - want + 1)
        while start >= 0:
            frag = "\n".join(lines[start:end_line_idx + 1]) + "\n"
            if text.count(frag) == 1:
                return frag
            start -= 1
        return None

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    # End-of-file anchor
    last_idx = max((i for i, l in enumerate(lines) if l.strip()), default=None)
    if last_idx is not None:
        frag = unique_tail(last_idx)
        if frag:
            hints.append("append a top-level definition: use mode=append (no anchor needed), or patch old_text=" + json.dumps(frag))
    # Class anchors: last statement line of each class body
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.body:
            end = getattr(node.body[-1], "end_lineno", node.body[-1].lineno) - 1
            frag = unique_tail(end)
            if frag:
                hints.append(f"add a method to class {node.name}: patch old_text=" + json.dumps(frag) + " and put the new method (indented 4 spaces) after those lines in new_text")
    return ("PATCH ANCHORS (verbatim, each occurs exactly once):\n" + "\n".join(f"- {h}" for h in hints)) if hints else ""


# Context selection


@dataclass
class ContextSelection:
    files: list[str]
    rendered: str
    symbols: list[str] = field(default_factory=list)
    related_tests: list[str] = field(default_factory=list)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    requested_paths: list[str] = field(default_factory=list)
    new_paths: list[str] = field(default_factory=list)


def select_context(manager, request: str, files: list[str], *, max_chars: int, priority_files=()) -> ContextSelection:
    index = SymbolIndex(manager)
    terms = request_terms(request)
    file_set = set(files)
    requested_paths = explicit_request_paths(request, files)
    existing_targets = [p for p in requested_paths if p in file_set]
    new_targets = [p for p in requested_paths if p not in file_set]
    hits = term_search(manager, terms)
    graph = import_graph(index, files)
    pairs = test_pairs(files)

    score: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)

    # Explicit user paths outrank every semantic signal. When paths are named,
    # restrict context to those targets, directly related source/tests/imports,
    # and small project manifests. This prevents a 3B planner being drowned in
    # unrelated keyword hits. New-file-only requests get manifests, not random
    # source files.
    allowed_scope: set[str] | None = None
    if requested_paths:
        allowed_scope = set(existing_targets)
        for target in existing_targets:
            allowed_scope.update(pairs.get(target, ()))
            for importer, imported in graph.items():
                if target in imported:
                    allowed_scope.add(importer)
                if importer == target:
                    allowed_scope.update(imported)
        manifest_names = {name for name in priority_files if name != "README.md"}
        allowed_scope.update(
            p for p in files
            if "/" not in p and Path(p).name in manifest_names
        )
        for target in existing_targets:
            score[target] += 10000
            reasons[target].append("explicit request target")

    for path, count in hits.items():
        if allowed_scope is not None and path not in allowed_scope:
            continue
        score[path] += 10 + min(count, 10)
        reasons[path].append(f"{count} term hit(s)")
    for path in list(score):
        for other in pairs.get(path, ()):
            if allowed_scope is None or other in allowed_scope:
                score[other] += 8
                reasons[other].append(f"test/source pair of {path}")
        for importer, imported in graph.items():
            if path in imported and (allowed_scope is None or importer in allowed_scope):
                score[importer] += 4
                reasons[importer].append(f"imports {path}")
            if importer == path:
                for dep in imported:
                    if allowed_scope is None or dep in allowed_scope:
                        score[dep] += 3
                        reasons[dep].append(f"imported by {path}")
    for path in files:
        if allowed_scope is not None and path not in allowed_scope:
            continue
        name = Path(path).name
        if name in priority_files:
            score[path] += 6
            reasons[path].append("project manifest")
        low = path.casefold()
        for term in terms:
            if term in low:
                score[path] += 12
                reasons[path].append(f"name matches '{term}'")
    ranked = [p for p, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0].casefold())) if p in file_set]
    # Small projects / no hits: the planner must still see the code. Append the
    # remaining code files smallest-first; the budget below bounds the total.
    leftovers = [
        p for p in files
        if p not in score
        and (allowed_scope is None or p in allowed_scope)
        and (Path(p).suffix.casefold() in _CODE_SUFFIXES or Path(p).name in priority_files)
    ]
    sizes = {}
    for p in leftovers:
        try:
            sizes[p] = int(manager.read_file(p, max_chars=500).get("chars") or 0)
        except (ValueError, OSError, UnicodeError):
            sizes[p] = 10**9
    ranked += sorted(leftovers, key=lambda p: (sizes[p], p.casefold()))
    for p in leftovers:
        reasons[p].append("no term hits; included as remaining project source")

    # Render: small files whole, large files as outline + matching symbol bodies.
    chunks, used, chosen, symbol_names, tests = [], 0, [], [], []
    for path in ranked:
        if used >= max_chars:
            break
        if Path(path).suffix.casefold() not in _CODE_SUFFIXES and Path(path).name not in priority_files:
            continue
        try:
            data = manager.read_file(path, max_chars=60000)
        except (ValueError, OSError, UnicodeError):
            continue
        text = data.get("content") or ""
        clipped = bool(data.get("clipped"))
        if len(text) <= _SMALL_FILE_CHARS and not clipped:
            anchors = patch_anchors(text, path)
            block = f"FILE: {path}\nCLIPPED: no\nWHY: {'; '.join(reasons.get(path, [])[:3])}\n{text}" + (f"\n{anchors}" if anchors else "")
        else:
            syms = index.symbols(path)
            wanted = [s for s in syms if any(t in s.name.casefold() for t in terms)]
            bodies = "\n\n".join(f"# {s.kind} {s.name} (L{s.start}-{s.end})\n{index.body(s)}" for s in wanted[:6])
            symbol_names.extend(f"{path}:{s.name}" for s in wanted[:6])
            anchors = patch_anchors(text, path)  # Anchors for clipped files too
            block = (
                f"FILE: {path}\nCLIPPED: yes (outline + matching symbols shown; NEVER replace this file — "
                f"use mode=append for a new top-level definition or mode=patch on an anchor below)\n"
                f"WHY: {'; '.join(reasons.get(path, [])[:3])}\nOUTLINE:\n{index.outline(path)}\n"
                + (f"\nSYMBOLS:\n{bodies}" if bodies else "")
                + (f"\n{anchors}" if anchors else "")
            )
        remaining = max_chars - used
        block = block[:remaining]
        chunks.append(block)
        used += len(block)
        chosen.append(path)
        if path in pairs and any(Path(p).stem.startswith("test_") or "test" in p for p in [path]):
            tests.append(path)
    return ContextSelection(files=chosen, rendered="\n\n".join(chunks), symbols=symbol_names,
                            related_tests=sorted({t for p in chosen for t in pairs.get(p, ()) if t != p}),
                            reasons=dict(reasons), requested_paths=requested_paths, new_paths=new_targets)


# Completeness


# Asking FOR tests ("and a unittest for it", "add tests", "with a test case"), not merely
# mentioning them ("keep the existing tests passing", "without changing the tests").
_TEST_INTENT = re.compile(
    r"\b(?:add|write|create|include|including|update|extend|adjust|fix up)\s+"
    r"(?:its|the|their|a|an|some|new)?\s*(?:unit ?tests|unittests|tests|test cases|specs)\b"
    r"|\b(?:and|including|plus)\s+(?:the\s+|its\s+|their\s+)?tests\b"
    r"|\b(?:add|write|create|include)\s+(?:a|an|one|new|the)?\s*"
    r"(?:unit ?test|unittest|test case|spec)\b(?=\s*(?:for|that|to|cover|$|[,.]))"
    r"|\b(?:unit ?tests?|unittests?|tests?|test cases?|specs?)\s+(?:for|covering|that cover)\b"
    r"|\btest coverage\b",
    re.I,
)
_TEST_NEGATION = re.compile(r"\b(?:without|don'?t|do not|no need to|not)\s+(?:\w+\s+){0,3}(?:chang|touch|modif|edit|updat)\w*\s+(?:the\s+)?tests?\b|\bkeep(?:ing)? (?:the )?(?:existing )?tests? passing\b", re.I)
_NAME_IN_REQUEST = re.compile(r"\b(?:function|method|class|endpoint|command|module)\s+(?:called\s+|named\s+)?`?([A-Za-z_][A-Za-z0-9_]*)`?|\b(?:a|an|the)\s+`?([a-z_][a-z0-9_]{2,})`?\s+(?:function|method|class)", re.I)


def request_wants_tests(request: str) -> bool:
    """Return True only when the user explicitly asked to add/change test coverage."""
    return bool(_TEST_INTENT.search(str(request or ""))) and not _TEST_NEGATION.search(str(request or ""))


_RENAME_DIRECTIVE_RE = re.compile(
    r"\brename\s+([A-Za-z_][A-Za-z0-9_]*)\s+to\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.I,
)


def _rename_new_identifiers(request: str) -> tuple[str, ...]:
    """NEW identifiers from 'rename X to Y' directives (casefolded)."""
    return tuple({new.casefold() for _, new in _RENAME_DIRECTIVE_RE.findall(str(request or ""))})


def rename_old_identifiers(request: str) -> tuple[str, ...]:
    """OLD identifiers from 'rename X to Y' directives (casefolded)."""
    return tuple({old.casefold() for old, _ in _RENAME_DIRECTIVE_RE.findall(str(request or ""))})


def plan_gaps(request: str, plan: dict, files_before: set[str]) -> list[str]:
    """Concrete, checkable gaps between what was asked and what the plan does."""
    gaps = []
    items = list(plan.get("files") or [])
    paths = [str(i.get("path") or "") for i in items]
    blob = "\n".join(
        str(i.get("content") or "") + "\n" + str(i.get("new_text") or "") for i in items
    )
    wants_tests = request_wants_tests(request)

    # Target-path authority: if the user named concrete file paths,
    # a planner may not silently substitute unrelated files. Requested tests are
    # the only implicit expansion because their exact path is often not named.
    targets = explicit_request_paths(request, files_before)
    if targets:
        allowed = set(targets)
        if wants_tests:
            # The user explicitly asked for test coverage but commonly does not
            # name the test file. Permit only recognisable test paths, including
            # a new test file paired to an explicitly targeted source file.
            allowed.update(
                p for p in files_before
                if Path(p).name.startswith("test_")
                or p.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
                or "/tests/" in f"/{p}"
            )
            for target in targets:
                target_path = Path(target)
                stem = target_path.stem
                suffix = target_path.suffix.casefold()
                parent = target_path.parent
                if suffix in {".py", ".pyi"}:
                    candidates = [
                        parent / f"test_{stem}.py",
                        parent / f"{stem}_test.py",
                        parent / "tests" / f"test_{stem}.py",
                        Path("tests") / f"test_{stem}.py",
                    ]
                elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
                    base_suffix = ".ts" if suffix in {".ts", ".tsx"} else ".js"
                    candidates = [
                        parent / f"{stem}.test{base_suffix}",
                        parent / f"{stem}.spec{base_suffix}",
                        parent / "tests" / f"{stem}.test{base_suffix}",
                        Path("tests") / f"{stem}.test{base_suffix}",
                    ]
                else:
                    candidates = []
                allowed.update(str(candidate) for candidate in candidates)
        # Rename/refactor-everywhere requests. A rename touches every
        # file containing the symbol; those files are definitionally on-target
        # even when the request names none of them. A planned file counts as
        # part of the rename when its planned content carries one of the NEW
        # identifiers :  drift to unrelated files still fails, because their
        # content cannot contain the renamed symbol.
        rename_new_names = _rename_new_identifiers(request)
        if rename_new_names:
            for item in items:
                planned = normalize_path_token(str(item.get("path") or ""))
                if not planned or planned in allowed:
                    continue
                text = f"{item.get('content') or ''}\n{item.get('new_text') or ''}".casefold()
                if any(name in text for name in rename_new_names):
                    allowed.add(planned)
        off_target = []
        for item in items:
            planned = normalize_path_token(str(item.get("path") or ""))
            if planned and planned not in allowed:
                off_target.append(planned)
        if off_target:
            gaps.append(
                "The request explicitly targets "
                + ", ".join(f"`{p}`" for p in targets)
                + "; do not modify unrelated path(s): "
                + ", ".join(f"`{p}`" for p in sorted(set(off_target)))
            )
    touches_tests = any(Path(p).name.startswith("test_") or p.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts")) or "/tests/" in f"/{p}" for p in paths)
    if wants_tests and not touches_tests:
        existing = sorted(p for p in files_before if Path(p).name.startswith("test_") or "/tests/" in f"/{p}")
        hint = f" (existing test file(s): {', '.join(existing[:3])} — patch one of them)" if existing else " (create a test file)"
        gaps.append("The request asks for tests but the plan touches no test file" + hint)
    for m in _NAME_IN_REQUEST.finditer(request):
        name = next((g for g in m.groups() if g), None)
        if name and name.casefold() not in _STOP and not re.search(rf"\b{re.escape(name)}\b", blob):
            gaps.append(
                f"The request names `{name}`; define it with EXACTLY that identifier — `{name}` — "
                "not a synonym, expansion or abbreviation (the plan never defines or uses it)"
            )
    return gaps


# Session state


class SessionState:
    """Rolling, bounded summary of the coding session injected into every plan."""

    MAX_EVENTS = 12
    MAX_CHARS = 1200

    def __init__(self):
        self.events: list[str] = []
        self.touched: list[str] = []
        self.last_failure: str | None = None

    def record(self, kind: str, detail: str, touched=()):
        self.events.append(f"{kind}: {detail[:140]}")
        self.events = self.events[-self.MAX_EVENTS:]
        for path in touched:
            if path not in self.touched:
                self.touched.append(path)
        self.touched = self.touched[-20:]
        if kind == "verification-failed":
            self.last_failure = detail[:300]
        elif kind in {"applied", "undo"}:
            self.last_failure = None

    def render(self) -> str:
        if not self.events:
            return ""
        lines = ["SESSION STATE (authoritative, from Python):"]
        if self.touched:
            lines.append("Files touched this session: " + ", ".join(self.touched[-10:]))
        lines.extend(f"- {e}" for e in self.events[-8:])
        if self.last_failure:
            lines.append(f"Last failing check: {self.last_failure}")
        text = "\n".join(lines)
        return text[: self.MAX_CHARS]
