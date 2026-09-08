"""RazaAI TUI/import + slash-command integration hotfix."""

from pathlib import Path
from app.config import OLLAMA_CONTEXT_WINDOW
from app.tui.session import parse_command


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.3 Integration Hotfix")
    print("=" * 76)

    assert isinstance(OLLAMA_CONTEXT_WINDOW, int) and OLLAMA_CONTEXT_WINDOW > 0

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    import_line = next(
        line for line in tui.splitlines()
        if line.startswith("from ..config import")
    )
    assert "OLLAMA_CONTEXT_WINDOW" in import_line
    assert 'id="status-tokens"' in tui
    print("[PASS] TUI imports the context-window symbol used by token status")

    improve = parse_command("/improve NPS EAP WiFi troubleshooting")
    assert improve.handled
    assert improve.action == "improve"
    assert improve.topic == "NPS EAP WiFi troubleshooting"
    assert improve.prompt is None
    print("[PASS] /improve uses the first-class controlled workflow contract")

    reasoning = Path(
        "tests/test_step20_5_reasoning_memory_commands.py"
    ).read_text(encoding="utf-8")
    assert 'assert improve.action == "agent"' not in reasoning
    assert 'assert improve.action == "improve"' in reasoning
    assert 'assert improve.prompt is None' in reasoning
    print("[PASS] legacy Step20.5 prompt-rewrite assertions are removed")

    print()
    print("=" * 76)
    print("STEP 20.5.3 INTEGRATION HOTFIX PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
