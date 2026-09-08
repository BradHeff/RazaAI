"""RazaAI:  resolve approved runtimes before bubblewrap entry."""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.tools.workspace import WorkspaceManager


def main():
    print("=" * 78)
    print("RazaAI Step 20.14.5 Bubblewrap Runtime Resolution")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime_dir = root.parent / (root.name + "-runtime")
        runtime_dir.mkdir()
        try:
            fake_node = runtime_dir / "node"
            fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_node.chmod(fake_node.stat().st_mode | stat.S_IXUSR)
            manager = WorkspaceManager(root)
            env = {"PATH": str(runtime_dir)}
            resolved = manager._resolve_host_executable(["node", "--test"], env)
            assert Path(resolved[0]).is_absolute()
            assert Path(resolved[0]).resolve() == fake_node.resolve()

            with patch.object(WorkspaceManager, "probe_sandbox", classmethod(lambda cls, refresh=False: ("bwrap", ["--unshare-net"]))):
                wrapped, level = manager._sandboxed_args(resolved, root, env=env)
            assert level == "bwrap"
            sep = wrapped.index("--")
            assert wrapped[sep + 1] == str(fake_node.resolve())
            assert "--setenv" in wrapped and "PATH" in wrapped and str(runtime_dir) in wrapped
        finally:
            import shutil
            shutil.rmtree(runtime_dir, ignore_errors=True)
    print("[PASS] approved Node runtime is resolved to an absolute host path before bwrap")

    with tempfile.TemporaryDirectory() as td:
        manager = WorkspaceManager(td)
        try:
            manager._validate_command(["node", "--inspect"])
        except ValueError:
            pass
        else:
            raise AssertionError("runtime resolution must not widen Node command authority")
    print("[PASS] runtime resolution occurs after the existing command/subcommand allowlist")

    from app.config import APP_VERSION, version_tuple
    assert version_tuple(APP_VERSION) >= (20, 14, 5), APP_VERSION
    print(f"[PASS] APP_VERSION={APP_VERSION}")
    print("=" * 78)
    print("STEP 20.14.5 BUBBLEWRAP RUNTIME RESOLUTION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
