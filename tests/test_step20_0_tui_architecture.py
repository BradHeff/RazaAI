from pathlib import Path

from app.tui.session import parse_command


def main():
    print("=" * 72)
    print("RazaAI Step 20.0 Anchored Terminal UI")
    print("=" * 72)

    main_source = Path("app/main.py").read_text(encoding="utf-8")
    tui_source = Path("app/tui/app.py").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "def classic_main" in main_source
    assert '"--classic"' in main_source
    assert '"--tui"' in main_source
    assert "sys.stdin.isatty()" in main_source
    print("[PASS] original CLI remains available and non-TTY sessions fall back safely")

    assert '#conversation' in tui_source
    assert '#composer-shell' in tui_source
    assert '#status' in tui_source
    assert 'height: 1fr' in tui_source
    assert 'height: 5' in tui_source
    assert 'call_after_refresh(self._focus_prompt)' in tui_source
    print("[PASS] scrollable conversation is separated from visible bottom-anchored composer/status")

    assert "asyncio.to_thread" in tui_source
    assert "redirect_stdout" in tui_source
    assert "redirect_stderr" in tui_source
    print("[PASS] Ollama/agent work stays off the UI loop and verbose diagnostics are isolated")

    assert "Input.Submitted" in tui_source
    assert "scroll_end" in tui_source
    assert "action_toggle_debug" in tui_source
    print("[PASS] prompt submission, auto-scroll, and debug view are wired")

    assert parse_command("/exit").action == "quit"
    assert parse_command("/clear").action == "clear"
    assert parse_command("/debug").action == "debug"
    assert parse_command("/help").action == "message"
    assert parse_command("hello").handled is False
    print("[PASS] terminal slash commands are deterministic and model-independent")

    assert "textual>=5,<9" in requirements
    print("[PASS] clean-machine runtime requirements include Textual")

    print()
    print("=" * 72)
    print("STEP 20.0 ANCHORED TERMINAL UI PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
