"""Shared state passed through the ordered RazaAI turn stages."""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TurnContext:
    user_input: str
    on_stream: Any = None
    # Native reasoning (RAZAAI_THINK=1) streams here instead of the
    # chat body, so the UI can animate it without displaying raw thinking.
    on_thinking: Any = None
    preview_route: Any = None
    previous_interaction: Any = None
    previous_learned_resolutions: list = field(default_factory=list)
    interaction: Any = None
    task_route: Any = None
    diagnostic_retrieval_query: str = ""
    explicit_self_identity_turn: bool = False
    self_identity_turn: bool = False
    turn_playbook_suspended: bool = False
    edge_route: Any = None
    deterministic_tool_result: Any = None
    lifecycle_turn: bool = False
    continuing_playbook: bool = False
    turn_messages: list = field(default_factory=list)
    executed_tools_this_turn: set = field(default_factory=set)


@dataclass(frozen=True)
class StageResult:
    handled: bool = False
    content: Optional[str] = None

    @classmethod
    def continue_turn(cls):
        return cls(False, None)

    @classmethod
    def complete(cls, content):
        return cls(True, content)
