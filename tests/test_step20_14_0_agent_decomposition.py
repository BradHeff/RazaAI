"""Ordered agent turn-stage decomposition."""
import ast
from pathlib import Path

from app.agent.stages import TurnContext, TurnPipeline


class FakeAgent:
    def __init__(self, terminal=None):
        self.calls = []
        self.terminal = terminal

    def _stage_prepare_turn(self, ctx):
        self.calls.append("prepare")
        ctx.interaction = object()

    def _stage_preflight_reply(self, ctx):
        self.calls.append("preflight")
        return "preflight-result" if self.terminal == "preflight" else None

    def _stage_prepare_edge(self, ctx):
        self.calls.append("edge-prepare")

    def _stage_edge_reply(self, ctx):
        self.calls.append("edge")
        return "edge-result" if self.terminal == "edge" else None

    def _stage_playbook(self, ctx):
        self.calls.append("playbook")
        return "playbook-result" if self.terminal == "playbook" else None

    def _stage_build_prompt(self, ctx):
        self.calls.append("prompt")
        ctx.turn_messages = [{"role": "user", "content": ctx.user_input}]

    def _stage_model_turn(self, ctx):
        self.calls.append("model")
        return "model-result"


def test_default_stage_order():
    agent = FakeAgent()
    result = TurnPipeline.default().run(agent, TurnContext("hello"))
    assert result == "model-result"
    assert agent.calls == [
        "prepare", "preflight", "edge-prepare", "edge", "playbook", "prompt", "model"
    ]


def test_preflight_short_circuits_lower_priority_stages():
    agent = FakeAgent("preflight")
    result = TurnPipeline.default().run(agent, TurnContext("/model"))
    assert result == "preflight-result"
    assert agent.calls == ["prepare", "preflight"]


def test_edge_short_circuits_playbook_and_model():
    agent = FakeAgent("edge")
    result = TurnPipeline.default().run(agent, TurnContext("show route"))
    assert result == "edge-result"
    assert agent.calls == ["prepare", "preflight", "edge-prepare", "edge"]


def test_playbook_short_circuits_prompt_and_model():
    agent = FakeAgent("playbook")
    result = TurnPipeline.default().run(agent, TurnContext("validation passed"))
    assert result == "playbook-result"
    assert agent.calls[-1] == "playbook"
    assert "prompt" not in agent.calls and "model" not in agent.calls


def test_prompt_precedes_model():
    agent = FakeAgent()
    TurnPipeline.default().run(agent, TurnContext("explain ospf"))
    assert agent.calls.index("prompt") < agent.calls.index("model")


def test_ask_is_a_short_dispatcher():
    source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    ask = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "RazaAgent":
            ask = next(
                item for item in node.body
                if isinstance(item, ast.FunctionDef) and item.name == "ask"
            )
            break
    assert ask is not None
    assert len(ask.body) <= 5
    ask_source = ast.get_source_segment(source, ask) or ""
    assert "TurnPipeline.default().run" in ask_source
    assert "while True" not in ask_source


def test_cross_stage_state_is_explicit():
    source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    context = Path("app/agent/stages/context.py").read_text(encoding="utf-8")
    assert "diagnostic_retrieval_query: str" in context
    assert "ctx.diagnostic_retrieval_query = diagnostic_retrieval_query" in source
    assert source.count("diagnostic_retrieval_query = ctx.diagnostic_retrieval_query") >= 2


def test_20_13_16_guards_survive_refactor():
    source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "RazaAgent":
            methods = {
                item.name: ast.get_source_segment(source, item) or ""
                for item in node.body
                if isinstance(item, ast.FunctionDef)
            }
            break

    playbook = methods["_stage_playbook"]
    model = methods["_stage_model_turn"]
    preflight = methods["_stage_preflight_reply"]

    assert "retrieval_query=diagnostic_retrieval_query" in playbook
    assert "workspace_coworker.should_handle" in preflight
    assert "if tool_name not in allowed_model_tool_names:" in model
    assert "Blocked unsolicited document creation" in model
    assert "max_model_tool_rounds = 6" in model
    assert "max_model_tool_calls = 12" in model
    assert "validate_web_answer" in model

def main():
    print("=" * 78)
    print("RazaAI Step 20.14.0 Agent Decomposition")
    print("=" * 78)
    tests = [
        test_default_stage_order,
        test_preflight_short_circuits_lower_priority_stages,
        test_edge_short_circuits_playbook_and_model,
        test_playbook_short_circuits_prompt_and_model,
        test_prompt_precedes_model,
        test_ask_is_a_short_dispatcher,
        test_cross_stage_state_is_explicit,
        test_20_13_16_guards_survive_refactor,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("=" * 78)
    print("STEP 20.14.0 AGENT DECOMPOSITION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
