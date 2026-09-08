from __future__ import annotations

import asyncio
import io
import inspect
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass

from textual import on
from rich.markup import escape
from rich.markdown import Markdown as RichMarkdown
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.timer import Timer
from textual.widgets import Input, Markdown, Static

from ..agent import RazaAgent
from ..config import APP_NAME, APP_VERSION, OLLAMA_MODEL, OLLAMA_CONTEXT_WINDOW, SELFOPS_ENABLED, PROFILE
from ..ollama_client import OllamaError
from .session import parse_command


@dataclass
class AskResult:
    response: str
    debug_output: str = ""
    error: bool = False


class ChatMessage(Vertical):
    """One role-labelled chat turn."""

    def __init__(self, role: str, text: str, *, error: bool = False) -> None:
        super().__init__(classes=f"message {'error' if error else role.casefold()}")
        self.role = role
        self.text = text

    def compose(self) -> ComposeResult:
        yield Static(self.role, classes="role")
        yield Markdown(self.text, classes="message-body")


class StreamingMessage(ChatMessage):
    """Assistant turn whose body can be updated incrementally."""

    def __init__(self, role: str = "RazaAI") -> None:
        super().__init__(role, "")
        self._stream_text = ""
        self._thinking_label = ""

    def compose(self) -> ComposeResult:
        yield Static(self.role, classes="role")
        # Static.update is synchronous, which makes it safe for Textual's
        # call_from_thread bridge while Ollama is producing chunks.
        yield Static("", classes="message-body streaming-body", markup=False)

    def show_thinking(self, label: str) -> None:
        """Display the animated thinking label inside the message bubble."""
        self._thinking_label = str(label or "")
        body = self.query_one(".streaming-body", Static)
        body.add_class("thinking-label")
        body.update(self._thinking_label)

    def stop_thinking(self) -> None:
        if self._thinking_label:
            self._thinking_label = ""
            body = self.query_one(".streaming-body", Static)
            body.remove_class("thinking-label")
            body.update("")

    def append_chunk(self, chunk: str) -> None:
        self._stream_text += str(chunk or "")
        if self._thinking_label:
            self._thinking_label = ""
            self.query_one(".streaming-body", Static).remove_class("thinking-label")
        self.query_one(".streaming-body", Static).update(self._stream_text)

    def set_text(self, text: str) -> None:
        self._stream_text = str(text or "")
        self.query_one(".streaming-body", Static).update(RichMarkdown(self._stream_text, code_theme="monokai"))


class RazaTUI(App):
    """Full-screen RazaAI terminal interface with a bottom-anchored composer."""

    TITLE = "RazaAI"
    SUB_TITLE = "Local AI Systems Assistant"

    # Rotate a short activity label while waiting for the model.
    THINKING_VERBS = (
        # Cerebral & analytical
        "Cogitating", "Contemplating", "Deliberating", "Pondering", "Ruminating",
        "Mulling", "Inferring", "Deciphering", "Deducing", "Calculating",
        "Correlating", "Cross-referencing", "Untangling", "Reasoning",
        # Culinary
        "Brewing", "Marinating", "Simmering", "Stewing", "Fermenting",
        "Percolating", "Whisking", "Baking", "Reducing", "Julienning",
        # Kinetic & quirky
        "Moseying", "Meandering", "Shimmying", "Wandering", "Scampering",
        "Skedaddling", "Schlepping", "Scurrying", "Vaulting", "Sashaying",
        # Pure whimsy
        "Booping", "Canoodling", "Dilly-dallying", "Lollygagging",
        "Flibbertigibbeting", "Discombobulating", "Honking", "Hullaballooing",
        "Wibbling", "Snorking", "Blorping",
        # Cortana flavour
        "Scheming", "Plotting", "Outsmarting", "Bamboozling", "Calculating odds",
        "Choosing our moment", "Reading the room", "Being smarter than the problem",
    )
    THINKING_VERB_SECONDS = 1.6

    CSS = """
    Screen {
        layout: vertical;
        background: #0b0e0d;
        color: #e8ece9;
    }

    #brand {
        height: 8;
        padding: 1 3 0 3;
        background: #0b0e0d;
        color: #dce7df;
    }

    #conversation {
        height: 1fr;
        padding: 0 4 1 4;
        scrollbar-size: 1 1;
        background: #0b0e0d;
    }

    .message {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    .role {
        height: 1;
        text-style: bold;
        color: #f4b942;
    }

    .assistant .role {
        color: #4a8b3b;
    }

    .error .role {
        color: #d55e5e;
    }

    .message-body {
        height: auto;
        margin: 0;
        padding: 0;
        background: transparent;
    }

    .streaming-body.thinking-label {
        color: #6f8a7a;
        text-style: italic;
    }

    #debug-panel {
        display: none;
        height: 8;
        margin: 0 4;
        padding: 0 1;
        border: round #445148;
        color: #a9b5ad;
        background: #111613;
        overflow-y: auto;
    }

    #debug-panel.visible {
        display: block;
    }

    #composer-shell {
        /* Reserve three editable rows inside the borders. */
        height: 5;
        margin: 0 3;
        padding: 0 1;
        border-top: solid #5a655d;
        border-bottom: solid #5a655d;
        background: #0b0e0d;
        align-vertical: middle;
    }

    #prompt-mark {
        width: 2;
        height: 3;
        content-align: center middle;
        color: #f4b942;
        text-style: bold;
    }

    #prompt {
        width: 1fr;
        height: 3;
        border: none;
        background: transparent;
        color: #f4f7f5;
        padding: 0 1;
    }

    #prompt:focus {
        border: none;
        background: #111613;
    }

    #status {
        height: 2;
        padding: 0 5;
        background: #0b0e0d;
    }

    #status-left {
        width: 1fr;
        height: 2;
        color: #8f9b93;
        content-align: left middle;
    }

    #status-tokens {
        width: auto;
        min-width: 26;
        height: 2;
        color: #aeb9b1;
        content-align: right middle;
        text-align: right;
    }
    """

    BINDINGS = [
        ("ctrl+l", "clear_chat", "Clear"),
        ("ctrl+d", "toggle_debug", "Debug"),
        ("ctrl+q", "quit", "Quit"),
    ]

    SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, agent: RazaAgent | None = None) -> None:
        super().__init__()
        self.agent = agent or RazaAgent()
        self._busy = False
        self._spinner_index = 0
        self._spinner_timer: Timer | None = None
        self._debug_chunks: list[str] = []
        self._active_assistant: StreamingMessage | None = None
        self._last_prompt_tokens: int | None = None
        self._last_output_tokens: int | None = None
        # Characters of native reasoning streamed this turn.
        self._thinking_chars = 0
        self._thinking_verb_index = 0
        self._thinking_verb_timer: Timer | None = None

    def _brand_markup(self) -> str:
        workspace_root = getattr(self.agent, "workspace_root", None)
        workspace_label = "Workspace"
        if workspace_root is None:
            # Normal conversational coding is intentionally rooted at
            # the RazaAI source project. Surface that authority so users do not
            # have to infer the active write boundary from their shell cwd.
            project_coworker = getattr(self.agent, "project_coworker", None)
            manager = getattr(project_coworker, "manager", None)
            workspace_root = getattr(manager, "root", None)
            workspace_label = "Coding workspace"
        workspace_line = ""
        if workspace_root is not None:
            workspace_line = (
                f"\n[dim]             {workspace_label}: [/]"
                f"[b #c8d6cc]{escape(str(workspace_root))}[/]"
            )
        return (
            "[b #4A8B3B]  ▄▟█▙▄[/]     "
            f"[b]{PROFILE.model}[/] v{APP_VERSION}\n"
            "[b #4A8B3B] ▐█╋╋╋█▌[/]    "
            f"{self._active_model_label()}\n"
            "[b #4A8B3B] ▐█╋●╋█▌[/]    "
            "[dim]Tools: Enabled · Backend: Ollama[/]\n"
            "[b #4A8B3B]  ▀▜█▛▀[/]     "
            f"[dim]Documents: DOCX / PDF · Self-ops: {'enabled' if SELFOPS_ENABLED else 'locked'} · /help[/]"
            + workspace_line
        )

    def _refresh_brand(self) -> None:
        """Keep the header synchronized with broker-driven model changes."""
        try:
            self.query_one("#brand", Static).update(self._brand_markup())
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Static(self._brand_markup(), id="brand", markup=True)
        yield VerticalScroll(id="conversation")
        yield Static("", id="debug-panel", markup=False)
        with Horizontal(id="composer-shell"):
            yield Static("❯", id="prompt-mark")
            yield Input(placeholder="Ask RazaAI…", id="prompt")
        with Horizontal(id="status"):
            yield Static(self._ready_status(), id="status-left")
            yield Static(self._token_status(), id="status-tokens")

    def on_mount(self) -> None:
        # Focus after the first layout/paint pass.  This is more reliable over
        # SSH and with terminals that negotiate their size immediately after
        # Textual enters the alternate screen.
        self.call_after_refresh(self._focus_prompt)

    def _focus_prompt(self) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = self._busy
        if not self._busy:
            prompt.focus()

    def _ready_status(self) -> str:
        model = getattr(getattr(self.agent, "client", None), "model", None) or OLLAMA_MODEL
        return f"Ready   {model}   Ctrl+D Debug   Ctrl+Q Quit"

    @staticmethod
    def _format_tokens(value: int | None) -> str:
        if value is None:
            return "?"
        if value >= 1000:
            return f"{value / 1000:.1f}k"
        return str(value)

    def _active_model_label(self) -> str:
        """Show the model this session actually talks to (coder model in raza-code)."""
        agent = getattr(self, "agent", None)
        client = getattr(agent, "client", None)
        active = getattr(client, "model", None) or OLLAMA_MODEL
        if active != OLLAMA_MODEL:
            return f"session model: {active}  (conversation model: {OLLAMA_MODEL})"
        return f"session model: {active}"

    def _context_window(self) -> int:
        """Live window detected from the Ollama Modelfile, else the fallback."""
        agent = getattr(self, "agent", None)
        return int(getattr(agent, "context_window", None) or OLLAMA_CONTEXT_WINDOW)

    def _token_status(self) -> str:
        return (
            f"In {self._format_tokens(self._last_prompt_tokens)} · "
            f"Out {self._format_tokens(self._last_output_tokens)} · "
            f"Ctx {self._context_window()}"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#status-left", Static).update(text)

    def _refresh_token_status(self) -> None:
        self.query_one("#status-tokens", Static).update(self._token_status())

    def _capture_last_usage(self) -> None:
        client = getattr(self.agent, "client", None)
        usage = getattr(client, "last_usage", None)
        if not isinstance(usage, dict):
            return
        prompt = usage.get("prompt_tokens")
        output = usage.get("output_tokens")
        if isinstance(prompt, int):
            self._last_prompt_tokens = prompt
        if isinstance(output, int):
            self._last_output_tokens = output
        self._refresh_token_status()

    async def _append(self, role: str, text: str, *, error: bool = False) -> None:
        view = self.query_one("#conversation", VerticalScroll)
        await view.mount(ChatMessage(role, text, error=error))
        view.scroll_end(animate=False)

    def _start_spinner(self) -> None:
        self._spinner_index = 0
        self._spinner_timer = self.set_interval(0.1, self._spin)

    def _stop_spinner(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._refresh_brand()
        self._set_status(self._ready_status())

    def _spin(self) -> None:
        frame = self.SPINNER[self._spinner_index % len(self.SPINNER)]
        self._spinner_index += 1
        self._refresh_brand()
        # While native reasoning streams (RAZAAI_THINK=1), show the
        # thinking volume :  an animated indicator, never the raw reasoning.
        detail = ""
        if self._thinking_chars > 0:
            kb = self._thinking_chars / 1000.0
            detail = f" · {kb:.1f}k reasoning" if kb >= 1 else f" · {self._thinking_chars} chars reasoning"
        self._set_status(f"{frame} Thinking{detail}   {self._active_model_label()}")

    def _thinking_chunk_from_worker(self, chunk: str) -> None:
        # Reasoning arrives on a worker thread; just count it, never display it.
        self._thinking_chars += len(str(chunk or ""))
        self.call_from_thread(self._spin)
        self.call_from_thread(self._render_thinking_verb)

    def _thinking_verb_label(self) -> str:
        verb = self.THINKING_VERBS[self._thinking_verb_index % len(self.THINKING_VERBS)]
        label = f"{verb}…"
        if self._thinking_chars > 0:
            kb = self._thinking_chars / 1000.0
            label += f" ({kb:.1f}k reasoning)" if kb >= 1 else f" ({self._thinking_chars} chars reasoning)"
        return label

    def _render_thinking_verb(self) -> None:
        if self._active_assistant is not None and self._thinking_verb_timer is not None:
            self._active_assistant.show_thinking(self._thinking_verb_label())

    def _cycle_thinking_verb(self) -> None:
        self._thinking_verb_index += 1
        self._render_thinking_verb()

    def _start_thinking_verbs(self) -> None:
        """Animate thinking words inside the assistant bubble until content."""
        self._stop_thinking_verbs()
        if self._active_assistant is None:
            return
        self._thinking_verb_index = 0
        self._active_assistant.show_thinking(self._thinking_verb_label())
        self._thinking_verb_timer = self.set_interval(
            self.THINKING_VERB_SECONDS, self._cycle_thinking_verb
        )

    def _stop_thinking_verbs(self) -> None:
        if self._thinking_verb_timer is not None:
            self._thinking_verb_timer.stop()
            self._thinking_verb_timer = None
        if self._active_assistant is not None:
            self._active_assistant.stop_thinking()

    def _stream_chunk_from_worker(self, chunk: str) -> None:
        # Ollama runs in asyncio.to_thread(); Textual widgets must only be
        # touched on the UI thread. call_from_thread bridges that boundary.
        self.call_from_thread(self._stream_chunk_ui, str(chunk or ""))

    def _stream_chunk_ui(self, chunk: str) -> None:
        if not chunk or self._active_assistant is None:
            return
        # First visible token replaces the thinking words with the answer.
        if self._thinking_verb_timer is not None:
            self._thinking_verb_timer.stop()
            self._thinking_verb_timer = None
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._active_assistant.append_chunk(chunk)
        self.query_one("#conversation", VerticalScroll).scroll_end(animate=False)
        self._set_status(f"● Generating   {self._active_model_label()}")

    def _ask_sync(self, prompt: str) -> AskResult:
        """Run the agent off the UI thread and capture verbose diagnostics."""
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                parameters = inspect.signature(self.agent.ask).parameters
                if "on_stream" in parameters:
                    kwargs = {"on_stream": self._stream_chunk_from_worker}
                    # Reasoning streams to the spinner counter only.
                    if "on_thinking" in parameters:
                        kwargs["on_thinking"] = self._thinking_chunk_from_worker
                    response = self.agent.ask(prompt, **kwargs)
                else:
                    # Compatibility with simple/fake agents used by TUI tests.
                    response = self.agent.ask(prompt)
            return AskResult(str(response), captured.getvalue())
        except OllamaError as exc:
            return AskResult(f"RazaAI backend error: {exc}", captured.getvalue(), True)
        except Exception as exc:
            return AskResult(f"RazaAI agent error: {exc}", captured.getvalue(), True)

    def _improve_sync(self, topic: str) -> AskResult:
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                runner = getattr(self.agent, "run_self_improvement", None)
                if runner is None:
                    return AskResult(
                        "This agent does not expose the controlled self-improvement orchestrator.",
                        captured.getvalue(),
                        True,
                    )
                response = runner(topic)
            return AskResult(str(response), captured.getvalue())
        except Exception as exc:
            return AskResult(
                f"RazaAI self-improvement error: {exc}",
                captured.getvalue(),
                True,
            )

    def _discover_improvements_sync(self) -> AskResult:
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                runner = getattr(self.agent, "discover_self_improvements", None)
                if runner is None:
                    return AskResult(
                        "This agent does not expose improvement discovery.",
                        captured.getvalue(),
                        True,
                    )
                response = runner()
            return AskResult(str(response), captured.getvalue())
        except Exception as exc:
            return AskResult(
                f"RazaAI improvement discovery error: {exc}",
                captured.getvalue(),
                True,
            )

    def _improvement_signals_sync(self) -> AskResult:
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                runner = getattr(self.agent, "improvement_signal_report", None)
                if runner is None:
                    return AskResult(
                        "This agent does not expose improvement signal reporting.",
                        captured.getvalue(),
                        True,
                    )
                response = runner()
            return AskResult(str(response), captured.getvalue())
        except Exception as exc:
            return AskResult(
                f"RazaAI improvement signal error: {exc}",
                captured.getvalue(),
                True,
            )

    def _improvement_history_sync(self) -> AskResult:
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                runner = getattr(self.agent, "improvement_history_report", None)
                if runner is None:
                    return AskResult(
                        "This agent does not expose improvement history reporting.",
                        captured.getvalue(),
                        True,
                    )
                response = runner()
            return AskResult(str(response), captured.getvalue())
        except Exception as exc:
            return AskResult(
                f"RazaAI improvement history error: {exc}",
                captured.getvalue(),
                True,
            )

    def _improve_auto_sync(self) -> AskResult:
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                runner = getattr(self.agent, "run_auto_self_improvement", None)
                if runner is None:
                    return AskResult(
                        "This agent does not expose automatic controlled self-improvement.",
                        captured.getvalue(),
                        True,
                    )
                response = runner()
            return AskResult(str(response), captured.getvalue())
        except Exception as exc:
            return AskResult(
                f"RazaAI automatic self-improvement error: {exc}",
                captured.getvalue(),
                True,
            )

    @on(Input.Submitted, "#prompt")
    async def submit_prompt(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt or self._busy:
            return

        command = parse_command(prompt)
        agent_prompt = prompt
        if command.handled:
            if command.action == "quit":
                self.exit()
                return
            if command.action == "clear":
                await self.action_clear_chat()
                return
            if command.action == "debug":
                self.action_toggle_debug()
                return
            if command.action == "agent" and command.prompt:
                agent_prompt = command.prompt
            elif command.action == "improve" and command.topic:
                agent_prompt = None
            elif command.action in {
                "discover_improvements",
                "improvement_signals",
                "improvement_history",
                "improve_auto",
            }:
                agent_prompt = None
            else:
                if command.message:
                    await self._append("RazaAI", command.message)
                return

        await self._append("You", prompt)
        self._busy = True
        event.input.disabled = True
        self._thinking_chars = 0
        self._start_spinner()

        # Mount one assistant turn up-front. It shows Claude-Code-style
        # thinking words until real content streams; buffered/tool/web turns
        # fill it when complete.
        view = self.query_one("#conversation", VerticalScroll)
        self._active_assistant = StreamingMessage("RazaAI")
        await view.mount(self._active_assistant)
        self._start_thinking_verbs()
        view.scroll_end(animate=False)

        if command.handled and command.action == "improve" and command.topic:
            result = await asyncio.to_thread(self._improve_sync, command.topic)
        elif command.handled and command.action == "discover_improvements":
            result = await asyncio.to_thread(self._discover_improvements_sync)
        elif command.handled and command.action == "improvement_signals":
            result = await asyncio.to_thread(self._improvement_signals_sync)
        elif command.handled and command.action == "improvement_history":
            result = await asyncio.to_thread(self._improvement_history_sync)
        elif command.handled and command.action == "improve_auto":
            result = await asyncio.to_thread(self._improve_auto_sync)
        else:
            result = await asyncio.to_thread(self._ask_sync, agent_prompt)

        self._capture_last_usage()
        self._stop_spinner()
        self._stop_thinking_verbs()
        if result.debug_output.strip():
            self._debug_chunks.append(result.debug_output.strip()[-12000:])
            self._debug_chunks = self._debug_chunks[-8:]
            self._refresh_debug()

        if self._active_assistant is not None:
            self._active_assistant.set_text(result.response)
            if result.error:
                self._active_assistant.add_class("error")
            view.scroll_end(animate=False)
        self._active_assistant = None

        self._busy = False
        event.input.disabled = False
        event.input.focus()

    async def action_clear_chat(self) -> None:
        if self._busy:
            return
        await self.query_one("#conversation", VerticalScroll).remove_children()
        self.query_one("#prompt", Input).focus()

    def action_toggle_debug(self) -> None:
        panel = self.query_one("#debug-panel", Static)
        panel.toggle_class("visible")
        self._refresh_debug()
        self.call_after_refresh(self._focus_prompt)

    def _refresh_debug(self) -> None:
        panel = self.query_one("#debug-panel", Static)
        if not self._debug_chunks:
            panel.update("No captured routing/tool diagnostics yet.")
            return
        panel.update("\n\n".join(self._debug_chunks[-8:])[-12000:])


def run_tui(agent: RazaAgent | None = None) -> None:
    RazaTUI(agent=agent).run()
