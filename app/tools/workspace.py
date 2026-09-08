from __future__ import annotations

import os
import re
import shlex
import signal
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


_IGNORED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".venv", "venv", "pyvenv", "node_modules",
    "dist", "build",
}

_TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml",
    ".yml", ".md", ".txt", ".html", ".css", ".scss", ".sh", ".bash", ".zsh",
    ".ini", ".cfg", ".conf", ".xml", ".sql", ".go", ".rs", ".java", ".c",
    ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".vue", ".svelte",
}

_ALLOWED_EXECUTABLES = {
    "python", "python3", "pytest", "ruff", "black", "mypy",
    "git", "node", "npm", "pnpm", "yarn", "go", "cargo",
}

_GIT_SUBCOMMANDS = {"status", "diff", "log", "show", "rev-parse"}
_NPM_SAFE = {"test", "run", "build", "lint"}
_GO_SAFE = {"test", "build", "vet", "fmt"}
_CARGO_SAFE = {"check", "test", "build", "fmt"}

_SENSITIVE_BASENAMES = {
    ".env", ".env.local", ".env.production", ".env.development",
    "id_rsa", "id_ed25519", "credentials", "credentials.json",
    "secrets", "secrets.json",
}


def _looks_sensitive_path(path: Path) -> bool:
    name = path.name.casefold()
    if name in _SENSITIVE_BASENAMES:
        return True
    if name.startswith(".env."):
        return True
    if name in {".netrc", ".npmrc", ".pypirc"}:
        return True
    if path.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}:
        return True
    if name.startswith("credentials.") or name.startswith("secrets."):
        return True
    return False


def _definition(name, description, properties, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
            },
        },
    }


def _meta(name, risk="read_only", timeout=30):
    return {
        "name": name,
        "category": "workspace",
        "risk": risk,
        "permission": "automatic",
        "timeout": timeout,
        "model_exposed": True,
    }


class WorkspaceManager:
    """Filesystem and command authority constrained to one explicit directory."""

    # Project-local interpreter/tool locations, checked in order.
    _PYTHON_ENV_DIRS = (".venv", "venv", "pyvenv", "env", ".env-py")
    _NODE_BIN_DIR = "node_modules/.bin"

    def __init__(self, root):
        path = Path(root).expanduser()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Coding workspace does not exist or is not a directory: {path}")
        self.root = path.resolve()
        self._interpreters = None

    _VERIFICATION_SKIP_DIRS = {
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
        ".git", ".hg", ".svn",
    }

    @contextmanager
    def verification_workspace(self):
        """Yield an isolated disposable copy for tests/builds."""
        parent = Path(tempfile.mkdtemp(prefix="razaai-verify-"))
        clone = parent / "workspace"
        dependency_dirs = set(self._PYTHON_ENV_DIRS) | {"node_modules"}

        def _ignore(directory, names):
            ignored = []
            for name in names:
                if name in self._VERIFICATION_SKIP_DIRS or name in dependency_dirs:
                    ignored.append(name)
            return ignored

        try:
            shutil.copytree(self.root, clone, symlinks=True, ignore=_ignore)
            for name in sorted(dependency_dirs):
                original = self.root / name
                target = clone / name
                if not original.exists() or target.exists():
                    continue
                # Absolute link is intentional: under bwrap it resolves through
                # the read-only host bind, while the disposable workspace remains RW.
                target.symlink_to(original, target_is_directory=True)
            manager = type(self)(clone)
            manager.verification_origin = self.root
            yield manager
        finally:
            shutil.rmtree(parent, ignore_errors=True)

    def project_interpreters(self, refresh=False):
        """Describe which project-local interpreters exist."""
        if self._interpreters is not None and not refresh:
            return self._interpreters

        python = None
        source = "system"
        for name in self._PYTHON_ENV_DIRS:
            env_dir = self.root / name
            if not env_dir.is_dir():
                continue
            for candidate in ("bin/python3", "bin/python", "Scripts/python.exe"):
                exe = env_dir / candidate
                if exe.is_file() and os.access(exe, os.X_OK):
                    python = exe
                    source = name
                    break
            if python:
                break

        node_bin = self.root / self._NODE_BIN_DIR
        self._interpreters = {
            "python": str(python) if python else None,
            "python_source": source,
            "node_bin": str(node_bin) if node_bin.is_dir() else None,
        }
        return self._interpreters

    def _inside(self, path: Path) -> bool:
        try:
            path.relative_to(self.root)
            return True
        except ValueError:
            return False

    def resolve(self, relative_path=".", *, must_exist=False, directory=False):
        raw = str(relative_path or ".").strip()
        candidate_raw = Path(raw)
        if candidate_raw.is_absolute():
            raise ValueError("Workspace paths must be relative to the coding workspace.")
        if any(part == ".." for part in candidate_raw.parts):
            raise ValueError("Workspace path traversal is not allowed.")

        candidate = self.root / candidate_raw

        # Existing targets are fully resolved so symlinks cannot escape.
        if candidate.exists() or candidate.is_symlink():
            resolved = candidate.resolve()
        else:
            # For a new file, resolve the closest existing parent and append
            # only lexical child components after that point.
            parent = candidate.parent
            missing = [candidate.name]
            while not parent.exists():
                missing.append(parent.name)
                parent = parent.parent
            resolved_parent = parent.resolve()
            resolved = resolved_parent.joinpath(*reversed(missing))

        if not self._inside(resolved):
            raise ValueError("Workspace operation would escape the coding workspace.")

        if must_exist and not resolved.exists():
            raise ValueError(f"Workspace path does not exist: {raw}")
        if directory and resolved.exists() and not resolved.is_dir():
            raise ValueError(f"Workspace path is not a directory: {raw}")
        return resolved

    def _relative(self, path: Path):
        return path.resolve().relative_to(self.root).as_posix() or "."

    def status(self):
        return {
            "root": str(self.root),
            "name": self.root.name,
            "exists": self.root.exists(),
            "writable": os.access(self.root, os.W_OK),
        }

    def list_files(self, path=".", recursive=False, max_entries=200):
        base = self.resolve(path, must_exist=True, directory=True)
        max_entries = max(1, min(int(max_entries), 500))
        items = []

        iterator = base.rglob("*") if recursive else base.iterdir()
        for item in iterator:
            try:
                rel = item.relative_to(self.root)
            except ValueError:
                continue
            if any(part in _IGNORED_DIRS for part in rel.parts):
                continue
            # Never follow/report symlinks that escape the root.
            if item.is_symlink():
                try:
                    if not self._inside(item.resolve()):
                        continue
                except OSError:
                    continue
            kind = "directory" if item.is_dir() else "file"
            size = None
            if kind == "file":
                try:
                    size = item.stat().st_size
                except OSError:
                    size = None
            items.append({"path": rel.as_posix(), "type": kind, "size": size})
            if len(items) >= max_entries:
                break

        items.sort(key=lambda x: (x["type"] != "directory", x["path"].casefold()))
        return {"root": str(self.root), "path": self._relative(base), "entries": items}

    def read_file(self, path, max_chars=24000):
        target = self.resolve(path, must_exist=True)
        if not target.is_file():
            raise ValueError(f"Workspace path is not a file: {path}")
        if _looks_sensitive_path(target):
            raise ValueError(
                "Credential/secret-bearing workspace files are not exposed to the model."
            )
        if target.stat().st_size > 2_000_000:
            raise ValueError("Workspace file is too large to inspect safely.")
        data = target.read_text(encoding="utf-8")
        max_chars = max(500, min(int(max_chars), 60000))
        clipped = len(data) > max_chars
        return {
            "path": self._relative(target),
            "content": data[:max_chars],
            "clipped": clipped,
            "chars": len(data),
        }

    def search(self, query, path=".", max_results=20):
        query = str(query or "").strip()
        if not query:
            raise ValueError("Workspace search query is required.")
        base = self.resolve(path, must_exist=True, directory=True)
        max_results = max(1, min(int(max_results), 50))
        needle = query.casefold()
        results = []

        for item in base.rglob("*"):
            if not item.is_file():
                continue
            try:
                rel = item.relative_to(self.root)
            except ValueError:
                continue
            if any(part in _IGNORED_DIRS for part in rel.parts):
                continue
            if _looks_sensitive_path(item):
                continue
            if item.suffix and item.suffix.casefold() not in _TEXT_EXTENSIONS:
                continue
            try:
                if item.stat().st_size > 1_000_000:
                    continue
                lines = item.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(lines, 1):
                if needle in line.casefold():
                    results.append(
                        {"file": rel.as_posix(), "line": number, "text": line[:500]}
                    )
                    if len(results) >= max_results:
                        return {"query": query, "results": results}
        return {"query": query, "results": results}

    def mkdir(self, path):
        target = self.resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"created": self._relative(target), "type": "directory"}

    @staticmethod
    def _atomic_write_text(target: Path, text: str):
        """Replace a text file atomically so interruption cannot leave a partial file."""
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = None
        if target.exists():
            try:
                mode = target.stat().st_mode & 0o777
            except OSError:
                mode = None
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.raza-", dir=str(target.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, target)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def read_file_exact(self, path, max_bytes=2_000_000):
        """Internal full-file read for safe mutation/snapshot logic; never model-clipped."""
        target = self.resolve(path, must_exist=True)
        if not target.is_file():
            raise ValueError(f"Workspace path is not a file: {path}")
        if _looks_sensitive_path(target):
            raise ValueError("Credential/secret-bearing workspace files cannot be modified or exposed.")
        if target.stat().st_size > int(max_bytes):
            raise ValueError("Workspace file is too large to modify safely.")
        return target.read_text(encoding="utf-8")

    def write_file(self, path, content, overwrite=False):
        target = self.resolve(path)
        if _looks_sensitive_path(target):
            raise ValueError("Credential/secret-bearing workspace files cannot be modified.")
        existed = target.exists()
        if existed and not overwrite:
            raise ValueError(
                f"Workspace file already exists: {path}. Read it first, then use "
                "workspace_patch_file or explicitly set overwrite=true."
            )
        if existed and not target.is_file():
            raise ValueError(f"Workspace path is not a file: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Parent may contain a symlink created between resolve and mkdir.
        parent = target.parent.resolve()
        if not self._inside(parent):
            raise ValueError("Workspace write would escape through a symlinked parent.")
        text = str(content)
        self._atomic_write_text(target, text)
        return {
            "path": self._relative(target),
            "written": True,
            "chars": len(text),
            "created": not existed,
        }

    def append_file(self, path, content):
        """Append without ever using the model-facing clipped read path."""
        source = self.read_file_exact(path)
        addition = str(content).strip("\n")
        updated = source.rstrip("\n") + "\n\n\n" + addition + "\n"
        return self.write_file(path, updated, overwrite=True)

    def patch_file(self, path, old_text, new_text):
        target = self.resolve(path, must_exist=True)
        source = self.read_file_exact(path)
        old_text = str(old_text)
        count = source.count(old_text)
        if not old_text or count != 1:
            raise ValueError(
                f"Exact workspace patch requires old_text to occur once; found {count} matches."
            )
        updated = source.replace(old_text, str(new_text), 1)
        self._atomic_write_text(target, updated)
        return {
            "path": self._relative(target),
            "patched": True,
            "old_chars": len(source),
            "new_chars": len(updated),
        }

    def _validate_command(self, command):
        if isinstance(command, str):
            args = shlex.split(command)
        elif isinstance(command, list):
            args = [str(item) for item in command]
        else:
            raise ValueError("Command must be a string or argument list.")

        if not args:
            raise ValueError("Command is empty.")

        exe = Path(args[0]).name
        if exe != args[0]:
            raise ValueError("Command executable must be invoked by name, not by filesystem path.")
        if exe not in _ALLOWED_EXECUTABLES:
            raise ValueError(
                f"Command executable '{exe}' is not allowed in coding workspace mode."
            )

        for arg in args[1:]:
            if (
                arg.startswith("/")
                or arg.startswith("../")
                or "/../" in arg
                or arg.endswith("/..")
                or "=/" in arg
            ):
                raise ValueError(
                    "Command arguments may not reference paths outside the coding workspace."
                )

        if exe in {"python", "python3"}:
            if len(args) < 2:
                raise ValueError("Python command must name a workspace script or an allowed -m module.")
            if args[1] in {"-c", "-"}:
                raise ValueError("Inline/stdin Python execution is blocked; create a workspace file first.")
            if args[1] == "-m":
                if len(args) < 3 or args[2] not in {
                    "pytest", "unittest", "compileall", "py_compile"
                }:
                    raise ValueError("Only pytest/unittest/compileall/py_compile Python modules are allowed.")
            elif args[1].startswith("-"):
                raise ValueError("Unsupported Python execution option.")
            else:
                script = self.resolve(args[1], must_exist=True)
                if not script.is_file():
                    raise ValueError("Python target must be a workspace file.")
                args[1] = str(script)

        elif exe == "node":
            if args == ["node", "--test"]:
                # Safe verification-only form: execute Node's built-in test
                # discovery inside the already isolated workspace.
                pass
            else:
                if len(args) < 2 or args[1] in {"-e", "--eval"} or args[1].startswith("-"):
                    raise ValueError("Node must execute a workspace script file or use bare --test.")
                script = self.resolve(args[1], must_exist=True)
                if not script.is_file():
                    raise ValueError("Node target must be a workspace file.")
                args[1] = str(script)

        elif exe == "git":
            if len(args) < 2 or args[1] not in _GIT_SUBCOMMANDS:
                raise ValueError("Only read-only git status/diff/log/show/rev-parse commands are allowed.")

        elif exe in {"npm", "pnpm", "yarn"}:
            if len(args) < 2 or args[1] not in _NPM_SAFE:
                raise ValueError("Package installation is blocked; only test/run/build/lint commands are allowed.")

        elif exe == "go":
            if len(args) < 2 or args[1] not in _GO_SAFE:
                raise ValueError("Only go test/build/vet/fmt commands are allowed.")

        elif exe == "cargo":
            if len(args) < 2 or args[1] not in _CARGO_SAFE:
                raise ValueError("Only cargo check/test/build/fmt commands are allowed.")

        return args

    def _project_local_args(self, args):
        """Rewrite an already-validated command to use project-local tools."""
        interpreters = self.project_interpreters()
        args = list(args)
        exe = args[0]
        if exe in {"python", "python3"} and interpreters["python"]:
            args[0] = interpreters["python"]
        elif exe == "pytest" and interpreters["python"]:
            # Run pytest through the project's interpreter so its plugins/deps load.
            args = [interpreters["python"], "-m", "pytest", *args[1:]]
        elif exe in {"ruff", "black", "mypy"} and interpreters["python"]:
            venv_bin = Path(interpreters["python"]).parent / exe
            if venv_bin.is_file():
                args[0] = str(venv_bin)
        return args

    @staticmethod
    def sandbox_available():
        return shutil.which("bwrap") is not None

    # Probe what this kernel actually permits, once per manager.
    # Ubuntu 24.04 / JetPack restrict unprivileged user namespaces: bwrap can
    # isolate the filesystem but `--unshare-net` fails with
    # "loopback: Failed RTM_NEWADDR: Operation not permitted".
    _SANDBOX_LEVELS = (
        ("bwrap", ["--unshare-net", "--unshare-pid"]),
        ("bwrap-fs", ["--unshare-pid"]),
        ("bwrap-fs-nopid", []),
    )
    _sandbox_probe_cache = {}

    @classmethod
    def probe_sandbox(cls, refresh=False):
        """Return (level, extra_flags) for the strongest bubblewrap profile that runs `true`."""
        if not refresh and cls._sandbox_probe_cache:
            return cls._sandbox_probe_cache["level"], cls._sandbox_probe_cache["flags"]
        level, flags = "unavailable", []
        if cls.sandbox_available():
            for name, extra in cls._SANDBOX_LEVELS:
                cmd = ["bwrap", "--die-with-parent", *extra, "--ro-bind", "/", "/",
                       "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--", "true"]
                try:
                    probe = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if probe.returncode == 0:
                    level, flags = name, extra
                    break
        cls._sandbox_probe_cache = {"level": level, "flags": flags}
        return level, flags

    @staticmethod
    def is_sandbox_error(result):
        """True when a command failed because of the sandbox itself, not the project."""
        err = str(result.get("stderr") or "")
        return result.get("exit_code", 0) != 0 and err.lstrip().startswith("bwrap:")

    @staticmethod
    def _resolve_host_executable(args, env):
        """Resolve an already-authorised executable before sandbox entry."""
        args = list(args)
        if not args or Path(args[0]).is_absolute():
            return args
        resolved = shutil.which(args[0], path=str(env.get("PATH") or ""))
        if resolved:
            # Dereference launcher symlinks where possible so bwrap receives an
            # executable path that exists in the read-only host bind.
            try:
                resolved = str(Path(resolved).resolve(strict=True))
            except (OSError, RuntimeError):
                resolved = str(Path(resolved).absolute())
            args[0] = resolved
        return args

    def _sandboxed_args(self, args, cwd_path, env=None):
        """Wrap a verification command in bubblewrap when available."""
        if os.getenv("RAZAAI_SANDBOX", "1").strip().casefold() in {"0", "false", "no", "off"}:
            return args, "disabled"
        level, flags = self.probe_sandbox()
        if level == "unavailable":
            return args, "unavailable"

        # The sandbox boundary is self-defending.  Even though
        # run_command() resolves the executable before it gets here, resolve it
        # again immediately before constructing the final bwrap argv.  A bare
        # executable is never handed to bwrap: if the controlled PATH cannot
        # resolve it, fail closed with a clear error instead of producing
        # `bwrap: execvp <name>: No such file or directory`.
        args = self._resolve_host_executable(args, env or os.environ)
        if args and not Path(str(args[0])).is_absolute():
            raise FileNotFoundError(f"Command not resolvable before sandbox entry: {args[0]}")

        wrapped = [
            "bwrap", "--die-with-parent", *flags,
            "--ro-bind", "/", "/",
            "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--bind", str(self.root), str(self.root),
            "--chdir", str(cwd_path),
            "--setenv", "HOME", "/tmp",
        ]
        if env and env.get("PATH"):
            # Make the inner environment explicit.  This is important for NVM
            # and other non-system runtime locations on Jetson deployments.
            wrapped += ["--setenv", "PATH", str(env["PATH"])]
        wrapped += ["--"] + list(args)
        return wrapped, level

    def run_command(self, command, cwd=".", timeout=20):
        cwd_path = self.resolve(cwd, must_exist=True, directory=True)
        args = self._validate_command(command)
        args = self._project_local_args(args)
        display = list(args)
        timeout = max(1, min(int(timeout), 60))

        env = os.environ.copy()
        env["RAZAAI_WORKSPACE"] = str(self.root)
        interpreters = self.project_interpreters()
        if interpreters["python"]:
            venv_bin = str(Path(interpreters["python"]).parent)
            env["VIRTUAL_ENV"] = str(Path(venv_bin).parent)
            env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
            env.pop("PYTHONHOME", None)
        if interpreters["node_bin"]:
            env["PATH"] = interpreters["node_bin"] + os.pathsep + env.get("PATH", "")
        # Keep command behavior predictable and avoid interactive prompts.
        env["PYTHONUNBUFFERED"] = "1"
        env["CI"] = env.get("CI", "1")
        # Verification must not litter the workspace (or the checkpoint) with bytecode.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # Py_compile/compileall write bytecode by design; send it outside the workspace.
        env["PYTHONPYCACHEPREFIX"] = os.path.join(tempfile.gettempdir(), "razaai-pycache")

        # Resolve the executable only after command validation and controlled PATH
        # construction.  also re-validates this at the bwrap boundary so
        # no caller can accidentally hand bubblewrap a bare executable name.
        args = self._resolve_host_executable(args, env)
        resolved_executable = str(args[0]) if args else ""

        process = None
        try:
            args, sandbox = self._sandboxed_args(args, cwd_path, env=env)
            process = subprocess.Popen(
                args,
                cwd=cwd_path,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
            stdout, stderr = process.communicate(timeout=timeout)
        except FileNotFoundError as exc:
            return {
                "command": display,
                "cwd": self._relative(cwd_path),
                "exit_code": 127,
                "stdout": "",
                "stderr": str(exc) or f"Command not installed: {resolved_executable or display[0]}",
                "resolved_executable": resolved_executable,
            }
        except subprocess.TimeoutExpired as exc:
            # Kill the entire process group, not only the immediate test/build
            # process. This prevents a timed-out script from leaving children
            # running on the Jetson after RazaAI has moved on.
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (AttributeError, ProcessLookupError, PermissionError, OSError):
                    process.kill()
                tail_out, tail_err = process.communicate()
            else:
                tail_out, tail_err = "", ""
            return {
                "command": display,
                "cwd": self._relative(cwd_path),
                "exit_code": 124,
                "stdout": str((exc.stdout or "") or tail_out or "")[-12000:],
                "stderr": (
                    str((exc.stderr or "") or tail_err or "")[-10000:]
                    + f"\nCommand timed out after {timeout} seconds; process group terminated."
                ).strip(),
                "sandbox": sandbox,
            }
        result = {
            "command": display,
            "cwd": self._relative(cwd_path),
            "exit_code": process.returncode,
            "stdout": (stdout or "")[-12000:],
            "stderr": (stderr or "")[-12000:],
            "sandbox": sandbox,
            "resolved_executable": resolved_executable,
        }
        if sandbox.startswith("bwrap") and self.is_sandbox_error(result) and not getattr(self, "_sandbox_retry", False):
            # The sandbox, not the project, failed (e.g. a capability the kernel
            # refuses). Re-probe for the strongest level that works and retry once.
            type(self)._sandbox_probe_cache = {}
            self._sandbox_retry = True
            try:
                retry = self.run_command(command, cwd=cwd, timeout=timeout)
            finally:
                self._sandbox_retry = False
            retry["sandbox_note"] = f"{sandbox} failed ({result['stderr'].strip().splitlines()[0][:120]}); retried as {retry['sandbox']}"
            return retry
        return result

    def exists(self, path):
        try:
            target = self.resolve(path)
        except ValueError:
            return False
        return target.exists()

    def remove_file(self, path):
        """Remove one workspace file. Used only for transactional rollback."""
        target = self.resolve(path, must_exist=True)
        if not target.is_file():
            raise ValueError(f"Workspace path is not a file: {path}")
        if _looks_sensitive_path(target):
            raise ValueError("Credential/secret-bearing workspace files cannot be modified.")
        target.unlink()
        return {"path": str(path), "removed": True}

    # The only Git writes RazaAI may perform, and only on raza/* branches.
    CHECKPOINT_BRANCH_PREFIX = "raza/"
    # Never commit build/test artefacts, even if the project has no .gitignore.
    CHECKPOINT_EXCLUDES = (
        ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/*.pyc",
        ":(exclude,glob)**/.pytest_cache/**", ":(exclude,glob)**/.mypy_cache/**",
        ":(exclude,glob)**/.ruff_cache/**", ":(exclude,glob)**/node_modules/**",
        ":(exclude,glob)**/.venv/**", ":(exclude,glob)**/venv/**", ":(exclude,glob)**/pyvenv/**",
        ":(exclude,glob)**/dist/**", ":(exclude,glob)**/build/**", ":(exclude,glob)**/target/**",
    )

    def _git(self, *args, timeout=15):
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, timeout=timeout)

    def git_checkpoint(self, message):
        if not (self.root / ".git").exists():
            raise ValueError("This workspace is not a Git repository.")
        message = " ".join(str(message or "raza checkpoint").split())[:200]
        head = self._git("rev-parse", "--abbrev-ref", "HEAD")
        branch = head.stdout.strip() if head.returncode == 0 else ""
        if not branch.startswith(self.CHECKPOINT_BRANCH_PREFIX):
            import datetime as _dt
            target = f"{self.CHECKPOINT_BRANCH_PREFIX}{_dt.date.today().isoformat()}"
            exists = self._git("rev-parse", "--verify", "--quiet", f"refs/heads/{target}").returncode == 0
            switch = self._git("checkout", target) if exists else self._git("checkout", "-b", target)
            if switch.returncode != 0:
                raise ValueError(f"Could not switch to checkpoint branch {target}: {switch.stderr.strip()}")
            branch = target
        add = self._git("add", "-A", "--", ".", *self.CHECKPOINT_EXCLUDES)
        if add.returncode != 0:
            raise ValueError(f"git add failed: {add.stderr.strip()}")
        staged = self._git("diff", "--cached", "--quiet")
        if staged.returncode == 0:
            return {"committed": False, "branch": branch, "reason": "nothing to commit"}
        commit = self._git(
            "-c", "user.name=RazaAI", "-c", "user.email=razaai@localhost",
            "commit", "-q", "-m", f"raza: {message}",
        )
        if commit.returncode != 0:
            raise ValueError(f"git commit failed: {commit.stderr.strip()}")
        sha = self._git("rev-parse", "--short", "HEAD").stdout.strip()
        summary = self._git("show", "--stat", "--oneline", "HEAD").stdout.strip()
        return {"committed": True, "branch": branch, "commit": sha, "summary": summary}

    def git_branch(self):
        """Current branch + local branches, Python-rendered (never the model)."""
        current = self._git("rev-parse", "--abbrev-ref", "HEAD")
        if current.returncode != 0:
            return {"exit_code": current.returncode, "current": None, "branches": [],
                    "stderr": current.stderr.strip()}
        listing = self._git("branch", "--no-color")
        branches = [line.strip().lstrip("* ").strip() for line in listing.stdout.splitlines() if line.strip()]
        return {"exit_code": 0, "current": current.stdout.strip(), "branches": branches, "stderr": ""}

    def git_status(self):
        return self.run_command(["git", "status", "--short"], timeout=10)

    def git_diff(self):
        return self.run_command(["git", "diff", "--"], timeout=10)


WORKSPACE_STATUS_DEFINITION = _definition(
    "workspace_status",
    "Report the coding workspace root and whether it is writable.",
    {},
)
WORKSPACE_LIST_DEFINITION = _definition(
    "workspace_list",
    "List files/directories inside the active coding workspace. Paths are relative to the workspace root.",
    {
        "path": {"type": "string", "default": "."},
        "recursive": {"type": "boolean", "default": False},
        "max_entries": {"type": "integer", "default": 200},
    },
)
WORKSPACE_READ_DEFINITION = _definition(
    "workspace_read_file",
    "Read a UTF-8 text/code file inside the active coding workspace before editing it.",
    {
        "path": {"type": "string"},
        "max_chars": {"type": "integer", "default": 24000},
    },
    ("path",),
)
WORKSPACE_SEARCH_DEFINITION = _definition(
    "workspace_search",
    "Search text/code files inside the active coding workspace for a literal query.",
    {
        "query": {"type": "string"},
        "path": {"type": "string", "default": "."},
        "max_results": {"type": "integer", "default": 20},
    },
    ("query",),
)
WORKSPACE_MKDIR_DEFINITION = _definition(
    "workspace_mkdir",
    "Create a directory inside the active coding workspace.",
    {"path": {"type": "string"}},
    ("path",),
)
WORKSPACE_WRITE_DEFINITION = _definition(
    "workspace_write_file",
    "Create or explicitly overwrite one UTF-8 code/text file inside the active coding workspace.",
    {
        "path": {"type": "string"},
        "content": {"type": "string"},
        "overwrite": {"type": "boolean", "default": False},
    },
    ("path", "content"),
)
WORKSPACE_PATCH_DEFINITION = _definition(
    "workspace_patch_file",
    "Patch an existing workspace text/code file by replacing one exact unique old_text fragment.",
    {
        "path": {"type": "string"},
        "old_text": {"type": "string"},
        "new_text": {"type": "string"},
    },
    ("path", "old_text", "new_text"),
)
WORKSPACE_RUN_DEFINITION = _definition(
    "workspace_run_command",
    "Run a guarded non-shell build/test/lint/runtime command in the coding workspace. Use it to verify code after creating or editing files.",
    {
        "command": {
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
            ]
        },
        "cwd": {"type": "string", "default": "."},
        "timeout": {"type": "integer", "default": 20},
    },
    ("command",),
)
WORKSPACE_GIT_STATUS_DEFINITION = _definition(
    "workspace_git_status",
    "Show read-only git status for the active coding workspace.",
    {},
)
WORKSPACE_GIT_DIFF_DEFINITION = _definition(
    "workspace_git_diff",
    "Show the current read-only git diff for the active coding workspace.",
    {},
)

WORKSPACE_STATUS_METADATA = _meta("workspace_status")
WORKSPACE_LIST_METADATA = _meta("workspace_list")
WORKSPACE_READ_METADATA = _meta("workspace_read_file")
WORKSPACE_SEARCH_METADATA = _meta("workspace_search")
WORKSPACE_MKDIR_METADATA = _meta("workspace_mkdir", "workspace_write")
WORKSPACE_WRITE_METADATA = _meta("workspace_write_file", "workspace_write")
WORKSPACE_PATCH_METADATA = _meta("workspace_patch_file", "workspace_write")
WORKSPACE_RUN_METADATA = _meta("workspace_run_command", "workspace_execute", 65)
WORKSPACE_GIT_STATUS_METADATA = _meta("workspace_git_status")
WORKSPACE_GIT_DIFF_METADATA = _meta("workspace_git_diff")
