"""RazaAI:  questions about code never authorise workspace writes."""

import json
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class _NeverCall:
    def chat(self, messages, tools=None):
        raise AssertionError("planner must not be invoked for a question")


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.2 Question vs Mutation Routing")
    print("=" * 78)

    questions = (
        "how do I fix this error?",
        "should I update the project README?",
        "what would you change in this function?",
        "why does the build fail",
        "is it safe to delete the cache module?",
        "can you add a REST endpoint?",
        "explain the error in main.py file",
    )
    for q in questions:
        assert WorkspaceCoworker.is_question(q), q
        assert not WorkspaceCoworker.should_handle(q), q
    print("[PASS] questions containing mutation verbs are not routed to the planner")

    mutations = (
        "fix the failing tests",
        "fix the failing tests?",
        "add a REST endpoint and tests for it",
        "refactor the parser and update its tests",
        "please create a python gui app to list files",
        "update the README file with install steps",
    )
    for m in mutations:
        assert WorkspaceCoworker.is_mutation(m), m
        assert WorkspaceCoworker.should_handle(m), m
    print("[PASS] imperative coding requests still reach the planner")

    reads = ("show me the code", "git status", "run tests", "what directory are we in", "list files")
    for r in reads:
        assert WorkspaceCoworker.should_handle(r), r
    print("[PASS] Python-owned read/status operations are unchanged")

    # End to end: a question must not touch the filesystem or the model planner.
    ws = Path(tempfile.mkdtemp())
    (ws / "main.py").write_text("print('hi')\n", encoding="utf-8")
    cw = WorkspaceCoworker(client=_NeverCall(), manager=WorkspaceManager(ws))
    assert not cw.should_handle("how would you fix the error in main.py file?")
    assert sorted(p.name for p in ws.iterdir()) == ["main.py"]
    print("[PASS] a question leaves the workspace untouched")

    print("=" * 78)
    print("STEP 20.8.2 QUESTION VS MUTATION ROUTING PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
