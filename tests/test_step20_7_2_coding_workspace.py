"""Coding workspace containment and tool authority."""

import os
import tempfile
from pathlib import Path

from app.tools.workspace import WorkspaceManager


def main():
    print("=" * 78)
    print("RazaAI Step 20.7.1 Coding Workspace Authority")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
        root = Path(tmp)
        other = Path(outside)
        manager = WorkspaceManager(root)

        created = manager.write_file(
            "app.py",
            'print("hello from workspace")\n',
        )
        assert created["path"] == "app.py"
        assert (root / "app.py").is_file()

        read = manager.read_file("app.py")
        assert "hello from workspace" in read["content"]

        patched = manager.patch_file(
            "app.py",
            'hello from workspace',
            'hello from RazaAI',
        )
        assert patched["patched"] is True
        assert "hello from RazaAI" in (root / "app.py").read_text(encoding="utf-8")

        listing = manager.list_files()
        assert any(item["path"] == "app.py" for item in listing["entries"])

        search = manager.search("RazaAI")
        assert search["results"][0]["file"] == "app.py"
        print("[PASS] workspace create/read/patch/list/search stay inside root")

        try:
            manager.read_file("../outside.txt")
        except ValueError:
            pass
        else:
            raise AssertionError("path traversal must be blocked")

        (other / "secret.txt").write_text("outside", encoding="utf-8")
        try:
            (root / "escape").symlink_to(other, target_is_directory=True)
            manager.read_file("escape/secret.txt")
        except (ValueError, OSError):
            pass
        else:
            raise AssertionError("symlink escape must be blocked")
        print("[PASS] traversal and symlink escapes are blocked")

        result = manager.run_command(["python3", "app.py"])
        assert result["exit_code"] == 0
        assert "hello from RazaAI" in result["stdout"]

        try:
            manager.run_command(["python3", "-c", "print('escape')"])
        except ValueError:
            pass
        else:
            raise AssertionError("python -c must be blocked")

        try:
            manager.run_command(["bash", "-lc", "touch escaped"])
        except ValueError:
            pass
        else:
            raise AssertionError("shell execution must be blocked")

        try:
            manager.run_command(["/usr/bin/python3", "app.py"])
        except ValueError:
            pass
        else:
            raise AssertionError("executable filesystem paths must be blocked")

        (root / ".env").write_text("PASSWORD=real-secret\n", encoding="utf-8")
        try:
            manager.read_file(".env")
        except ValueError:
            pass
        else:
            raise AssertionError("secret-bearing workspace files must not be exposed")
        print("[PASS] command and credential guardrails block common workspace escapes")

        registry_source = Path("app/tools/registry.py").read_text(encoding="utf-8")
        assert "def __init__(self, workspace_root=None)" in registry_source
        assert 'if self.workspace is not None:' in registry_source
        for name in (
            "workspace_list",
            "workspace_read_file",
            "workspace_write_file",
            "workspace_patch_file",
            "workspace_run_command",
        ):
            assert f'"{name}"' in registry_source
        print("[PASS] registry enables coding tools only for an explicit workspace")

        agent_source = Path("app/agent/agent.py").read_text(encoding="utf-8")
        assert "def _workspace_tools_for_turn" in agent_source
        assert '"workspace_write_file"' in agent_source
        assert '"workspace_run_command"' in agent_source
        assert 'return self._workspace_tools_for_turn(user_input)' in agent_source
        assert "full infrastructure/playbook/self-repair prompt is irrelevant" in agent_source
        print("[PASS] create-app requests use compact workspace authority, not self-modification authority")

    print()
    print("=" * 78)
    print("STEP 20.7.1 CODING WORKSPACE AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
