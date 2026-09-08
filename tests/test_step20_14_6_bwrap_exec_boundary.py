"""RazaAI:  the final bubblewrap argv must never contain a bare runtime."""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.tools.workspace import WorkspaceManager


def main():
    print("=" * 78)
    print("RazaAI Step 20.14.6 Bubblewrap Exec Boundary")
    print("=" * 78)

    # Exercise the real run_command -> sandbox wiring with a fake runtime and a
    # mocked Popen that captures the final argv.  This catches the gap:
    # unit-testing _resolve_host_executable alone was not enough.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime_dir = root / "runtime-bin"
        runtime_dir.mkdir()
        fake_node = runtime_dir / "node"
        fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_node.chmod(fake_node.stat().st_mode | stat.S_IXUSR)

        manager = WorkspaceManager(root)
        captured = {}

        class _Proc:
            pid = 4242
            returncode = 0
            def __init__(self, args, **kwargs):
                captured["args"] = list(args)
                self.returncode = 0
            def communicate(self, timeout=None):
                return "", ""

        env = os.environ.copy()
        env["PATH"] = str(runtime_dir) + os.pathsep + env.get("PATH", "")
        with patch.dict(os.environ, env, clear=True), \
             patch.object(WorkspaceManager, "probe_sandbox", classmethod(lambda cls, refresh=False: ("bwrap", ["--unshare-net"]))), \
             patch("app.tools.workspace.subprocess.Popen", _Proc):
            result = manager.run_command(["node", "--test"])

        assert result["exit_code"] == 0, result
        wrapped = captured["args"]
        sep = wrapped.index("--")
        inner_exe = wrapped[sep + 1]
        assert Path(inner_exe).is_absolute(), wrapped
        assert Path(inner_exe).resolve() == fake_node.resolve(), wrapped
        assert result.get("resolved_executable") == str(fake_node.resolve()), result
    print("[PASS] run_command hands bwrap an absolute authorised runtime, not a bare executable")

    # The bwrap wrapper itself must fail closed if an earlier caller somehow
    # supplies a bare runtime that cannot be resolved from the controlled PATH.
    with tempfile.TemporaryDirectory() as td:
        manager = WorkspaceManager(td)
        with patch.object(WorkspaceManager, "probe_sandbox", classmethod(lambda cls, refresh=False: ("bwrap", []))):
            try:
                manager._sandboxed_args(["definitely-not-a-raza-runtime", "--test"], Path(td), env={"PATH": "/nonexistent"})
            except FileNotFoundError as exc:
                assert "not resolvable before sandbox entry" in str(exc)
            else:
                raise AssertionError("bwrap boundary accepted an unresolved bare executable")
    print("[PASS] unresolved bare executables fail closed before bubblewrap")

    # On a provisioned Jetson this becomes an actual end-to-end probe.  Keep it
    # optional elsewhere so source-package testing does not require bubblewrap.
    host_node = shutil.which("node")
    host_bwrap = shutil.which("bwrap")
    if host_node and host_bwrap:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"type":"module","scripts":{"test":"node --test"}}\n', encoding="utf-8")
            (root / "smoke.test.js").write_text(
                "import test from 'node:test';\nimport assert from 'node:assert';\n"
                "test('smoke', () => assert.strictEqual(1 + 1, 2));\n",
                encoding="utf-8",
            )
            manager = WorkspaceManager(root)
            manager.probe_sandbox(refresh=True)
            result = manager.run_command(["node", "--test"], timeout=30)
            assert result["exit_code"] == 0, (
                f"Jetson bubblewrap Node probe failed: {result}\n"
                f"host_node={host_node} PATH={os.environ.get('PATH')}"
            )
            assert Path(result.get("resolved_executable") or "").is_absolute(), result
        print(f"[PASS] live bubblewrap Node smoke test ({host_node})")
    else:
        print(f"[SKIP] live bubblewrap Node smoke test (node={host_node!r}, bwrap={host_bwrap!r})")

    from app.config import APP_VERSION, version_tuple
    assert version_tuple(APP_VERSION) >= (20, 14, 6), APP_VERSION
    print(f"[PASS] APP_VERSION={APP_VERSION}")
    print("=" * 78)
    print("STEP 20.14.6 BUBBLEWRAP EXEC BOUNDARY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
