"""Raza-code launcher, TUI header, and version authority."""

from pathlib import Path

from app.config import APP_VERSION
from app.tui.session import parse_command


def main():
    print("=" * 78)
    print("RazaAI Step 20.7.2 Coding Workspace UX")
    print("=" * 78)

    assert tuple(int(part) for part in APP_VERSION.split(".")) >= (20, 7, 2)
    print("[PASS] application version is at or beyond the 20.7.2 workspace milestone")

    main_source = Path("app/main.py").read_text(encoding="utf-8")
    assert '"--workspace"' in main_source
    assert "RazaAgent(workspace_root=workspace_root)" in main_source
    assert "run_tui(agent=agent)" in main_source
    print("[PASS] app.main wires an explicit coding workspace into the agent/TUI")

    launcher = Path("raza-code").read_text(encoding="utf-8")
    assert 'WORKSPACE="$(pwd -P)"' in launcher
    assert '--workspace "$WORKSPACE"' in launcher
    assert "PYTHONPATH" in launcher
    print("[PASS] raza-code launches RazaAI against the terminal working directory")

    deploy = Path("deploy.sh").read_text(encoding="utf-8")
    assert 'for launcher in razaai razaai-8g raza-code' in deploy
    assert '$HOME/.local/bin/$launcher' in deploy
    print("[PASS] deploy.sh installs the raza-code command")

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    assert "Workspace" in tui
    assert 'workspace_root = getattr(self.agent, "workspace_root", None)' in tui
    print("[PASS] active coding directory is rendered in the fixed TUI header")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "RAZAAI CODING WORKSPACE" in agent
    assert "Work as a coding coworker" in agent
    assert "workspace_write_file" in agent
    assert "workspace_run_command" in agent
    assert "full infrastructure/playbook/self-repair prompt is irrelevant" in agent
    print("[PASS] coworker mode has a compact create/edit/verify contract")

    help_result = parse_command("/help")
    assert help_result.handled
    assert "raza-code" in str(help_result.message)
    print("[PASS] /help advertises coding coworker mode")

    print()
    print("=" * 78)
    print("STEP 20.7.2 CODING WORKSPACE UX PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
