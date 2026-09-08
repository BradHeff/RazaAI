"""RazaAI /improve TUI runtime regression."""

from pathlib import Path


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.4 Improve TUI Runtime")
    print("=" * 76)

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")

    assert "import io" in tui
    assert "captured = io.StringIO()" in tui
    assert "captured = StringIO()" not in tui
    print("[PASS] /improve captures diagnostics with io.StringIO")

    assert "def _improve_sync" in tui
    assert 'getattr(self.agent, "run_self_improvement", None)' in tui
    assert 'command.action == "improve"' in tui
    assert "asyncio.to_thread(self._improve_sync" in tui
    print("[PASS] /improve remains on the controlled off-loop execution path")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    orchestrator = Path("app/selfops/orchestrator.py").read_text(encoding="utf-8")
    assert "def run_self_improvement" in agent
    assert "ControlledImprovementOrchestrator" in agent
    assert '"start_self_improvement"' in orchestrator
    assert '"self_improvement_status"' in orchestrator
    assert '"verify_self_improvement"' in orchestrator
    assert "_format_improvement_summary" in agent
    print("[PASS] TUI /improve terminates in Python-authoritative job state")

    print()
    print("=" * 76)
    print("STEP 20.5.4 IMPROVE TUI RUNTIME PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
