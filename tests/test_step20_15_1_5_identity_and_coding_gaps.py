""":  close standalone coding verification and user identity/profile gaps."""

import json
import os
import tempfile
from pathlib import Path

from app.agent.edge_router import EdgeIntentRouter
from app.coding import WorkspaceCoworker
from app.memory import MemoryManager
from app.memory.identity import confirm_identity_reference, render_identity_profile
from app.routing import TaskRouter
from app.tools.workspace import WorkspaceManager


class FakeInfra:
    def list_hosts(self):
        return []


class Interaction:
    mode = "conversation"
    domain = "general"
    sensitive = False


class DriftPlanner:
    def chat(self, messages, tools=None, **kwargs):
        return {
            "message": {
                "content": json.dumps(
                    {
                        "files": [
                            {
                                "path": "wow.py",
                                "mode": "create",
                                "content": "print('this is wow')\n",
                            },
                            {
                                "path": "requirements.txt",
                                "mode": "replace",
                                "content": "",
                            },
                        ],
                        "summary": "create wow.py and update requirements.txt",
                    }
                )
            }
        }


def _coding_checks():
    router = TaskRouter()
    route = router.route('reate wow.py to print "this is wow"', Interaction())
    assert route.task == "coding", route
    assert WorkspaceCoworker.should_handle('reate wow.py to print "this is wow"')

    state = Path(tempfile.mkdtemp())
    workspace = Path(tempfile.mkdtemp())
    old_state = os.environ.get("RAZAAI_STATE_DIR")
    old_sandbox = os.environ.get("RAZAAI_SANDBOX")
    os.environ["RAZAAI_STATE_DIR"] = str(state)
    os.environ["RAZAAI_SANDBOX"] = "0"
    try:
        (workspace / "tests").mkdir()
        # The project has a test tree, but this standalone file is unrelated.
        (workspace / "tests" / "not_discoverable.py").write_text("x = 1\n", encoding="utf-8")
        (workspace / "requirements.txt").write_text("", encoding="utf-8")
        manager = WorkspaceManager(workspace)
        coworker = WorkspaceCoworker(
            client=DriftPlanner(), manager=manager, require_approval=True
        )
        proposal = coworker.handle('reate wow.py to print "this is wow"')
        assert "### create `wow.py`" in proposal, proposal
        assert "does NOT fully satisfy" not in proposal, proposal
        assert "Intent: create wow.py to print" in proposal, proposal
        # Planner drift may be reported as guarded noise, but never as required work.
        assert "partial change" not in proposal.casefold(), proposal
        result = coworker.approve()
        assert (workspace / "wow.py").read_text(encoding="utf-8") == "print('this is wow')\n"
        assert "Verification: PASS" in result, result
        assert "py_compile wow.py" in result, result
        assert "unittest discover" not in result, result
    finally:
        if old_state is None:
            os.environ.pop("RAZAAI_STATE_DIR", None)
        else:
            os.environ["RAZAAI_STATE_DIR"] = old_state
        if old_sandbox is None:
            os.environ.pop("RAZAAI_SANDBOX", None)
        else:
            os.environ["RAZAAI_SANDBOX"] = old_sandbox


def _memory_checks():
    root = Path(tempfile.mkdtemp())
    old_memory = os.environ.get("RAZAAI_MEMORY_DIR")
    os.environ["RAZAAI_MEMORY_DIR"] = str(root)
    try:
        memory = MemoryManager()
        memory.observe_user_turn("I am Brad Heffernan", session_id="s1")
        memory.observe_user_turn("I am the Creator of RazaAI", session_id="s1")
        memory.remember_online_profile(
            title="Brad Heffernan - IT Manager | Senior System Engineer | LinkedIn",
            url="https://example.invalid/brad-heffernan",
            snippet=(
                "As IT Manager at Example School, I bring over five years "
                "of experience in technology management and network security."
            ),
            source_id="S3",
            query="Brad Heffernan",
        )

        reopened = MemoryManager()
        profile = reopened.identity_profile("who am I")
        assert profile["name"] == "Brad Heffernan", profile
        assert profile["job_title"] == "IT Manager | Senior System Engineer", profile
        assert profile["organization"] == "Example School", profile
        assert profile["razaai_relationship"] == "Creator of RazaAI", profile
        assert profile["online_profile"]["url"] == "https://example.invalid/brad-heffernan", profile

        edge = EdgeIntentRouter(manager=FakeInfra())
        for text in (
            "who am I",
            "what is my job",
            "what do I do?",
            "what is my online profile?",
            "do you remember my online profile?",
            "who is Brad Heffernan",
            "Brad Heffernan job",
        ):
            route = edge.route(text, interaction=Interaction(), user_name="Brad Heffernan")
            assert route.kind == "deterministic_tool", (text, route)
            assert route.tool == "get_identity_profile", (text, route)

        answer = render_identity_profile(
            reopened.identity_profile("who is Brad Heffernan"),
            "who is Brad Heffernan",
        )
        assert "Brad Heffernan is you" in answer, answer
        assert "IT Manager | Senior System Engineer" in answer, answer
        assert "creator of RazaAI" in answer, answer

        # A transient S3 reference is resolved immediately into durable provenance.
        sources = {
            "S3": {
                "source_id": "S3",
                "title": "Brad Heffernan - IT Manager | Senior System Engineer | LinkedIn",
                "url": "https://example.invalid/brad-heffernan",
                "snippet": "As IT Manager at Example School, I lead hybrid IT environments.",
            }
        }
        routed = confirm_identity_reference(
            MemoryManager(),
            "S3 is me remember that",
            web_sources=sources,
            web_query="Brad Heffernan",
        )
        assert routed is not None and "confirmed online profile" in routed, routed

        # A verified pasted profile can also be remembered without inventing a URL.
        previous = (
            "Brad Heffernan - IT Manager | Senior System Engineer | LinkedIn: "
            "IT Manager | Senior System Engineer · As IT Manager at Example School, "
            "I manage hybrid IT environments."
        )
        routed2 = confirm_identity_reference(
            MemoryManager(),
            "yes its verified. Remember that",
            previous_user=previous,
        )
        assert routed2 is not None and "user-verified" in routed2, routed2
    finally:
        if old_memory is None:
            os.environ.pop("RAZAAI_MEMORY_DIR", None)
        else:
            os.environ["RAZAAI_MEMORY_DIR"] = old_memory


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.5 Identity + Coding Gap Regression")
    print("=" * 78)
    _coding_checks()
    print("[PASS] typo-safe coding routing, target sanitization and standalone verification")
    _memory_checks()
    print("[PASS] persistent user identity/profile/entity resolution across sessions")
    print("=" * 78)
    print("STEP 20.15.1.5 IDENTITY + CODING GAP REGRESSION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
