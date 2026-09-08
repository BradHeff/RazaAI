from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    handled: bool
    action: str | None = None
    message: str | None = None
    prompt: str | None = None
    topic: str | None = None


def parse_command(text: str) -> CommandResult:
    value = (text or "").strip()
    if not value.startswith("/"):
        return CommandResult(False)

    command = value.casefold()
    if command in {"/exit", "/quit", "/bye"}:
        return CommandResult(True, "quit")
    if command == "/clear":
        return CommandResult(True, "clear")
    if command == "/debug":
        return CommandResult(True, "debug")
    # Coding-session commands go to the agent, which owns the coworker state.
    if command == "/model":
        return CommandResult(True, "agent", prompt=value)
    if command in {"/approve", "/reject", "/undo", "/workspace"} or command.startswith("/checkpoint"):
        return CommandResult(True, "agent", prompt=value)
    if command in {"/audit", "/audit quick"}:
        return CommandResult(True, "agent", prompt="audit your code and report the findings")
    if command == "/audit full":
        return CommandResult(True, "agent", prompt="run a full audit of your code and report the findings")
    # End-of-session digest :  summarize what mattered and store it.
    if command in {"/digest", "/summary"}:
        return CommandResult(
            True, "agent", prompt="summarize this session and remember what mattered"
        )
    if command in {"/improvements", "/improve discover"}:
        return CommandResult(True, "discover_improvements")
    if command == "/improvements signals":
        return CommandResult(True, "improvement_signals")
    if command == "/improvements history":
        return CommandResult(True, "improvement_history")
    if command == "/improve auto":
        return CommandResult(True, "improve_auto")
    if command == "/improve":
        return CommandResult(
            True,
            "message",
            "Usage: `/improve <topic>`, `/improve auto`, or `/improvements`.",
        )
    if command.startswith("/improve "):
        topic = value[len("/improve "):].strip()
        if not topic:
            return CommandResult(True, "message", "Usage: `/improve <topic or capability>`.")
        return CommandResult(True, "improve", topic=topic)
    if command == "/help":
        return CommandResult(
            True,
            "message",
            (
                "**RazaAI terminal commands**\n\n"
                "- `/help` : show this help\n"
                "- `/clear` : clear the visible conversation\n"
                "- `/debug` : show or hide captured routing/tool output\n"
                "- `/model` : which model answers this session, which is resident, and why\n"
                "- `/workspace` : show the active coding workspace and project profile\n"
                "- `/audit` : run a quick Python-authoritative self-audit\n"
                "- `/audit full` : run the full self-audit\n"
                "- `/digest` : summarize this session's decisions/resolutions/open items and store them as a session digest\n"
                "- `/improvements` : discover and rank current evidence-backed improvement opportunities\n"
                "- `/improvements signals` : show persistent operational quality signals and repeated weaknesses\n"
                "- `/improvements history` : measure post-promotion outcomes against later signals\n"
                "- `/improve auto` : auto-select the safest highest-ranked opportunity and build/verify it\n"
                "- `/improve <topic>` : build and verify a controlled self-improvement candidate\n"
                "- `/exit`, `/quit`, `/bye` : close RazaAI\n\n"
                "Use `python3 -m app.main --classic` for the original scrolling CLI.\n\n"
                "For coding coworker mode, `cd` into a project directory and run "
                "`razaai code` or `razaai-8g code` (`raza-code` remains a shortcut). The active workspace will be shown in the TUI header. "
                "RazaAI can inspect existing projects, make multi-file changes, run guarded "
                "tests/builds, diagnose failures, repair code, and report Git status/diff evidence.\n"
                "Coding changes are proposed as a diff first: `/approve` applies and verifies, `/reject` discards, "
                "`/undo` restores the last applied task, `/checkpoint [message]` commits on a raza/ branch. "
                "Verification commands run under bubblewrap when it is installed."
            ),
        )
    return CommandResult(True, "message", f"Unknown command: `{value}`. Type `/help`.")
