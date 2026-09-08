from pathlib import Path

from app.interaction import InteractionRouter
from app.experts import ExpertRouter
from app.agent.edge_router import EdgeIntentRouter
from app.selfops.files import ProjectFileBrowser


class EmptyManager:
    def list_hosts(self):
        return []


def main():
    print()
    print("========================================")
    print("RazaAI Step 13.3 Tool / Action Boundary")
    print("========================================")
    print()

    ir = InteractionRouter()
    er = ExpertRouter()
    edge = EdgeIntentRouter(manager=EmptyManager())

    q = "can you see requirements.txt?"
    context = ir.classify(q, expert_route=er.route(q))
    route = edge.route(q, interaction=context)
    assert context.mode == "action"
    assert route.kind == "deterministic_tool"
    assert route.tool == "search_project_files"
    assert route.arguments["query"] == "requirements.txt"
    print("[PASS] explicit filename lookup uses project-file search, not code search")

    browser = ProjectFileBrowser(Path(__file__).resolve().parents[1])
    found = browser.search("requirements.txt", max_results=3)
    assert found["found"]
    assert found["results"][0]["file"] == "requirements.txt", found["results"][:3]
    print("[PASS] root-level JSONL dataset is discoverable")

    q = "Let's discuss passwords inside a text file"
    context = ir.classify(q, expert_route=er.route(q))
    route = edge.route(q, interaction=context)
    assert context.allow_tools is False
    assert route.kind == "model"
    print("[PASS] advice does not become an automatic tool operation")

    agent_source = (Path(__file__).resolve().parents[1] / "app/agent/agent.py").read_text()
    assert "or not interaction.allow_tools" in agent_source
    assert "STEP 13 INTERACTION CONTEXT" in (
        Path(__file__).resolve().parents[1] / "app/interaction/router.py"
    ).read_text()
    print("[PASS] agent structurally hides tools for non-action interaction modes")

    print()
    print("========================================")
    print("STEP 13.3 TOOL / ACTION BOUNDARY PASSED")
    print("========================================")


if __name__ == "__main__":
    main()
