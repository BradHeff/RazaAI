""":  explicit coding targets outrank semantic context and planner drift."""

import json
import os
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.coding.explore import explicit_request_paths, plan_gaps, select_context
from app.tools.workspace import WorkspaceManager


def _files(manager):
    return [
        item["path"]
        for item in manager.list_files(".", recursive=True, max_entries=500)["entries"]
        if item["type"] == "file"
    ]


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.1.4 Coding Target Authority")
    print("=" * 78)

    state = Path(tempfile.mkdtemp())
    os.environ["RAZAAI_STATE_DIR"] = str(state)

    ws = Path(tempfile.mkdtemp())
    (ws / "app").mkdir()
    (ws / "tests").mkdir()
    (ws / "output" / "documents").mkdir(parents=True)
    (ws / "app" / "main.py").write_text("def main():\n    print('hello')\n", encoding="utf-8")
    (ws / "tests" / "test_tool_result.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    # Deliberately noisy files that used to outrank an explicitly named target.
    for i in range(24):
        (ws / f"noise_{i}.py").write_text(
            "# app main test comment create print file output documents\n" * 20,
            encoding="utf-8",
        )
    (ws / "requirements.txt").write_text("", encoding="utf-8")

    mgr = WorkspaceManager(ws)
    files = _files(mgr)

    assert explicit_request_paths("edit app/main.py to add a test comment", files) == ["app/main.py"]
    assert explicit_request_paths(r"create wow\.py to print 'this is wow'", files) == ["wow.py"]
    sel = select_context(
        mgr,
        "edit app/main.py to add a test comment",
        files,
        max_chars=9000,
        priority_files=("README.md", "requirements.txt"),
    )
    assert sel.files[0] == "app/main.py", sel.files
    assert not any(path.startswith("noise_") for path in sel.files), sel.files
    assert "explicit request target" in "; ".join(sel.reasons["app/main.py"])
    print("[PASS] explicit app/main.py target is first and noisy semantic matches are excluded")

    good = {
        "files": [
            {
                "path": "app/main.py",
                "mode": "append",
                "content": "# test comment\n",
            }
        ]
    }
    assert plan_gaps("edit app/main.py to add a test comment", good, set(files)) == []
    paired_test = {
        "files": [
            {"path": "app/main.py", "mode": "append", "content": "# implementation\n"},
            {"path": "app/test_main.py", "mode": "create", "content": "def test_main():\n    assert True\n"},
        ]
    }
    assert plan_gaps("edit app/main.py and add a unittest for it", paired_test, set(files)) == []
    bad = {
        "files": [
            {
                "path": "output/documents/razoai-agent.json",
                "mode": "append",
                "content": "{}",
            }
        ]
    }
    gaps = plan_gaps("edit app/main.py to add a test comment", bad, set(files))
    assert len(gaps) == 1 and "do not modify unrelated path" in gaps[0], gaps
    print("[PASS] 'test comment' is not test-suite intent and unrelated planner paths are gaps")

    class WrongThenTarget:
        def __init__(self):
            self.calls = []

        def chat(self, messages, tools=None, **kwargs):
            user = messages[-1]["content"]
            system = messages[0]["content"]
            self.calls.append((system, user))
            if len(self.calls) == 1:
                plan = {
                    "files": [
                        {
                            "path": "output/documents/razoai-agent.json",
                            "mode": "append",
                            "content": "{}\n",
                        }
                    ],
                    "summary": "wrong target",
                }
            else:
                assert "do not modify unrelated path" in user
                plan = {
                    "files": [
                        {
                            "path": "app/main.py",
                            "mode": "append",
                            "content": "# test comment\n",
                        }
                    ],
                    "summary": "add requested comment",
                }
            return {"message": {"content": json.dumps(plan)}}

    client = WrongThenTarget()
    coworker = WorkspaceCoworker(client=client, manager=mgr, require_approval=True)
    proposal = coworker.handle("edit app/main.py to add a test comment")
    assert len(client.calls) == 2, len(client.calls)
    assert "explicit user target path(s): app/main.py" in client.calls[0][0]
    assert "EXPLICIT TARGET STATE: app/main.py=EXISTS" in client.calls[0][1]
    assert "### append `app/main.py`" in proposal, proposal
    assert "output/documents" not in proposal, proposal
    assert (ws / "app" / "main.py").read_text(encoding="utf-8") == "def main():\n    print('hello')\n"
    coworker.reject()
    print("[PASS] off-target first plan is retried and only app/main.py reaches proposal")

    class EscapedCreate:
        def chat(self, messages, tools=None, **kwargs):
            system = messages[0]["content"]
            user = messages[-1]["content"]
            assert "wow.py" in system and "mode=create" in system
            assert "EXPLICIT TARGET STATE: wow.py=NEW" in user
            plan = {
                "files": [
                    {
                        "path": r"wow\.py",
                        "mode": "create",
                        "content": "print(\"this is wow\")\n",
                    }
                ],
                "summary": "create wow",
            }
            return {"message": {"content": json.dumps(plan)}}

    cw2 = WorkspaceCoworker(client=EscapedCreate(), manager=mgr, require_approval=True)
    proposal2 = cw2.handle(r"create wow\.py to print \"this is wow\"")
    assert "### create `wow.py`" in proposal2, proposal2
    assert "wow\\.py" not in proposal2
    assert not (ws / "wow.py").exists(), "proposal must not write before /approve"
    cw2.reject()
    print("[PASS] Markdown/terminal path escapes normalize to wow.py without weakening approval")

    class AlwaysWrong:
        def chat(self, messages, tools=None, **kwargs):
            plan = {
                "files": [
                    {
                        "path": r"tests/test\_tool\_result.py",
                        "mode": "append",
                        "content": "# wrong\n",
                    }
                ],
                "summary": "wrong",
            }
            return {"message": {"content": json.dumps(plan)}}

    cw3 = WorkspaceCoworker(client=AlwaysWrong(), manager=mgr, require_approval=True)
    result = cw3.handle(r"create wow\.py to print \"this is wow\"")
    assert result.startswith("I did not change the workspace."), result
    assert "outside the explicit target" in result, result
    assert cw3.pending is None
    print("[PASS] repeated planner drift fails closed; unrelated files never reach /approve")

    package_source = Path("scripts/package_release.py").read_text(encoding="utf-8")
    assert "external_attr" in package_source and "executable mode mismatch" in package_source
    for executable in (
        "bin/raza", "raza-code", "razaai", "razaai-8g", "endpoint-install", "deploy.sh",
        "deploy/jetson-headless.sh", "scripts/package_release.sh",
    ):
        assert Path(executable).stat().st_mode & 0o111, executable
    print("[PASS] release tooling fails closed if executable mode bits are not preserved")

    print("=" * 78)
    print("STEP 20.15.1.4 CODING TARGET AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
