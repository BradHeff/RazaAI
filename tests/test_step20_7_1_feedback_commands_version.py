"""RazaAI feedback commands and version authority."""

from pathlib import Path

from app.config import APP_VERSION
from app.tui.session import parse_command


def main():
    print("=" * 78)
    print("RazaAI Step 20.7.0 Commands + Version Authority")
    print("=" * 78)

    version_tuple = tuple(int(part) for part in APP_VERSION.split("."))
    assert version_tuple >= (20, 7, 0)
    print("[PASS] application version is at or beyond the completed 20.7.0 milestone")

    signals = parse_command("/improvements signals")
    history = parse_command("/improvements history")
    assert signals.handled and signals.action == "improvement_signals"
    assert history.handled and history.action == "improvement_history"
    print("[PASS] feedback signal/history slash commands are first-class actions")

    help_result = parse_command("/help")
    assert "/improvements signals" in help_result.message
    assert "/improvements history" in help_result.message
    assert "/improve auto" in help_result.message
    print("[PASS] /help exposes the complete adaptive improvement workflow")

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    assert "def _improvement_signals_sync" in tui
    assert "def _improvement_history_sync" in tui
    assert 'command.action == "improvement_signals"' in tui
    assert 'command.action == "improvement_history"' in tui
    assert "asyncio.to_thread(self._improvement_signals_sync" in tui
    assert "asyncio.to_thread(self._improvement_history_sync" in tui
    print("[PASS] feedback reporting remains off the Textual event loop")

    acceptance = Path("scripts/step20_acceptance.py").read_text(encoding="utf-8")
    assert "APP_VERSION" in acceptance
    assert "REQUIRED_VERSION" in acceptance
    assert "tests.test_step20_7_0_feedback_loop" in acceptance
    assert "tests.test_step20_7_1_feedback_commands_version" in acceptance
    print("[PASS] Step 20 acceptance gates the declared application version")

    print()
    print("=" * 78)
    print("STEP 20.7.0 COMMANDS + VERSION AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
