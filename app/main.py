import argparse
import sys
import threading
import time
from pathlib import Path

from .agent import RazaAgent
from .ollama_client import OllamaError
from .config import APP_NAME, APP_VERSION, CODE_MODEL, OLLAMA_MODEL, SELFOPS_ENABLED
from .runtime_health import format_memory_line


class ResponseIndicator:
    """Animated terminal indicator shown while RazaAI is responding in classic mode."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _animate(self):
        frame = 0
        while self.running:
            sys.stdout.write(f"\rThinking {self.FRAMES[frame % len(self.FRAMES)]}")
            sys.stdout.flush()
            frame += 1
            time.sleep(0.1)


def print_banner():
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DARK_GREEN = "\033[38;5;28m"
    DIM = "\033[2m"
    art = ["  ▄▟█▙▄  ", " ▐█╋╋╋█▌ ", " ▐█╋●╋█▌ ", "  ▀▜█▛▀  "]

    print()
    print(f"{DARK_GREEN}{art[0]}{RESET}   {BOLD}{APP_NAME}{RESET} v{APP_VERSION}")
    shown_model = OLLAMA_MODEL if CODE_MODEL == OLLAMA_MODEL else f"{OLLAMA_MODEL} · code: {CODE_MODEL}"
    print(f"{DARK_GREEN}{art[1]}{RESET}   {shown_model}")
    print(f"{DARK_GREEN}{art[2]}{RESET}   {DIM}Tools: Enabled · Backend: Ollama{RESET}")
    selfops = "Self-ops: ENABLED" if SELFOPS_ENABLED else "Self-ops: locked"
    print(f"{DARK_GREEN}{art[3]}{RESET}   {DIM}Documents: DOCX / PDF · {selfops}{RESET}")
    print()
    print(f"  {DIM}{format_memory_line()}{RESET}")
    print(f"  {DIM}Type /exit to quit{RESET}")
    print()


def classic_main(agent=None):
    """Original scrolling CLI retained for SSH/debugging and non-interactive use."""
    agent = agent or RazaAgent()
    print_banner()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"/exit", "/quit", "/bye"}:
            print("Goodbye.")
            break

        indicator = ResponseIndicator()
        indicator.start()
        try:
            response = agent.ask(user_input)
        except OllamaError as exc:
            indicator.stop()
            print(f"\n[RazaAI Error] {exc}\n")
            continue
        except Exception as exc:
            indicator.stop()
            print(f"\n[RazaAI Agent Error] {exc}\n")
            continue
        finally:
            indicator.stop()

        print(f"\nRazaAI: {response}\n")


def _parser():
    parser = argparse.ArgumentParser(description="RazaAI terminal client")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--classic",
        action="store_true",
        help="Use the original scrolling terminal interface.",
    )
    mode.add_argument(
        "--tui",
        action="store_true",
        help="Force the full-screen anchored terminal interface.",
    )
    parser.add_argument(
        "--workspace",
        metavar="PATH",
        help=(
            "Enable coding-workspace coworker mode rooted at PATH. "
            "All workspace file tools are constrained to this directory."
        ),
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)

    workspace_root = None
    if args.workspace:
        workspace_root = Path(args.workspace).expanduser().resolve()
        if not workspace_root.exists() or not workspace_root.is_dir():
            raise SystemExit(f"RazaAI coding workspace is not a directory: {workspace_root}")

    agent = RazaAgent(workspace_root=workspace_root)

    # Broker-driven coding can occur inside a normal conversation,
    # so restore the conversation model on exit whenever the active model changed.
    import atexit

    def _restore_conversation_model():
        try:
            client = getattr(agent, "client", None)
            if client is None or getattr(client, "model", None) == OLLAMA_MODEL:
                return
            switcher = getattr(client, "switch_model", None)
            if callable(switcher):
                switcher(OLLAMA_MODEL, unload_previous=True)
            else:
                client.model = OLLAMA_MODEL
            from .server import warm_model
            # The default warm timeout (300s) would stall shutdown
            # for minutes on a wedged Ollama; 20s restores the model or gives up.
            result = warm_model(model=OLLAMA_MODEL, timeout=20.0)
            print(f"[Model] Restored {OLLAMA_MODEL}: {'ok' if result['loaded'] else result['error']}")
        except Exception:  # noqa: BLE001 - exit cleanup must never block shutdown
            pass

    atexit.register(_restore_conversation_model)

    # Piped/non-interactive sessions should never try to take over the terminal.
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if args.classic or (not interactive and not args.tui):
        classic_main(agent=agent)
        return

    try:
        from .tui.app import run_tui
    except ImportError as exc:
        if args.tui:
            print(
                "RazaAI TUI requires Textual. Install project requirements or run "
                "`pip install textual`, then try again.\n"
                f"Import error: {exc}"
            )
            raise SystemExit(2) from exc

        print(
            "[RazaAI] Textual is not installed; falling back to classic mode. "
            "Run `pip install textual` to enable the full-screen interface.\n"
        )
        classic_main(agent=agent)
        return

    run_tui(agent=agent)


if __name__ == "__main__":
    main()
