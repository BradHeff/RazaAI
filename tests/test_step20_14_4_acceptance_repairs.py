"""RazaAI:  repairs from the first full Jetson gate."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.coding.coworker import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager
from scripts.upgrade_cleanup import cleanup_obsolete_paths


def main():
    print("=" * 78)
    print("RazaAI Step 20.14.4 Acceptance Repair")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        stale = root / "app/tools/app/tools"
        stale.mkdir(parents=True)
        (stale / "legacy.py").write_text("OLD = True\n", encoding="utf-8")
        removed = cleanup_obsolete_paths(root)
        assert removed == ["app/tools/app"]
        assert not (root / "app/tools/app").exists()
    deploy = Path("deploy.sh").read_text(encoding="utf-8")
    assert "python3 -m scripts.upgrade_cleanup" in deploy
    print("[PASS] in-place upgrades remove the retired nested app/tools/app source tree")

    old_gate = Path("tests/test_step20_8_11_procedure_guidance_memory.py").read_text(encoding="utf-8")
    guidance = Path("app/playbooks/technical_guidance.py").read_text(encoding="utf-8")
    assert "guidance_source" in old_gate and "technical_guidance.py" in old_gate
    assert "'Evidence:' line" in guidance and "a hypothesis without evidence is incomplete" in guidance
    print("[PASS] decomposed FortiGate guidance is tested at its owning playbook module")

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "package.json").write_text(json.dumps({
            "name": "demo", "scripts": {"test": "node --test"}
        }), encoding="utf-8")
        (ws / "math.js").write_text("export const x = 1;\n", encoding="utf-8")
        (ws / "math.test.js").write_text("// test fixture\n", encoding="utf-8")
        manager = WorkspaceManager(ws)
        coworker = WorkspaceCoworker(client=None, manager=manager)
        profile = coworker._project_profile(coworker._list())
        assert ["node", "--test"] in coworker._verification_commands(profile)
        assert manager._validate_command(["node", "--test"]) == ["node", "--test"]
        try:
            manager._validate_command(["node", "--inspect"])
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe generic Node option unexpectedly allowed")
    print("[PASS] node --test projects verify without requiring npm and Node authority stays narrow")

    from app.config import APP_VERSION, version_tuple
    assert version_tuple(APP_VERSION) >= (20, 14, 4), APP_VERSION
    print(f"[PASS] APP_VERSION={APP_VERSION}")

    print("=" * 78)
    print("STEP 20.14.4 ACCEPTANCE REPAIR PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
