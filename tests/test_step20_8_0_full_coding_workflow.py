"""RazaAI full coding-agent workflow."""

import json
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class RepairingClient:
    """First plan has a syntax defect; repair pass fixes it."""

    def __init__(self):
        self.calls = 0
        self.saw_existing_source = False

    def chat(self, messages, tools=None):
        self.calls += 1
        assert tools is None
        user = messages[-1]["content"]
        if "RELEVANT EXISTING SOURCE" in user and "STYLE_TOKEN" in user:
            self.saw_existing_source = True

        if self.calls == 1:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "files": [
                                {
                                    "path": "app.py",
                                    "content": (
                                        "STYLE_TOKEN = 'existing-style'\n"
                                        "def list_files(path):\n"
                                        "    return [name for name in path.iterdir(\n"
                                    ),
                                    "purpose": "Add file-listing implementation.",
                                },
                                {
                                    "path": "README.md",
                                    "content": (
                                        "# File Tool\n\n"
                                        "Lists files from a selected directory.\n"
                                    ),
                                    "purpose": "Document the feature.",
                                },
                            ],
                            "summary": "Implemented the file-listing feature.",
                        }
                    )
                }
            }

        # Repair call is constrained to changed files and receives compile evidence.
        assert "VERIFICATION FAILURES" in user
        assert "app.py" in user
        return {
            "message": {
                "content": json.dumps(
                    {
                        "files": [
                            {
                                "path": "app.py",
                                "content": (
                                    "STYLE_TOKEN = 'existing-style'\n"
                                    "def list_files(path):\n"
                                    "    return [name.name for name in path.iterdir()]\n"
                                ),
                            }
                        ],
                        "summary": "Corrected the syntax defect.",
                    }
                )
            }
        }


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.0 Full Coding Workflow")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.py").write_text(
            "STYLE_TOKEN = 'existing-style'\n"
            "def old_behavior():\n"
            "    return []\n",
            encoding="utf-8",
        )

        client = RepairingClient()
        coworker = WorkspaceCoworker(
            client=client,
            manager=WorkspaceManager(root),
        )

        result = coworker.handle(
            "update this python project to list files and document the change"
        )

        assert client.saw_existing_source
        assert client.calls == 2
        assert (root / "app.py").is_file()
        assert (root / "README.md").is_file()
        assert "existing-style" in (root / "app.py").read_text(encoding="utf-8")
        assert "Verification: PASS" in result
        assert "Automatic repair passes: 1" in result
        assert "Updated:" in result and "`app.py`" in result
        assert "Created:" in result and "`README.md`" in result
        print("[PASS] existing source guides a multi-file edit and bounded repair loop")

        compile_result = WorkspaceManager(root).run_command(
            ["python3", "-m", "py_compile", "app.py"]
        )
        assert compile_result["exit_code"] == 0
        print("[PASS] final completion claim is backed by real Python verification")

    source = Path("app/coding/coworker.py").read_text(encoding="utf-8")
    assert "MAX_REPAIR_PASSES = 2" in source
    assert "_snapshot_paths" in source
    assert "_rollback_snapshot" in source
    assert "_verification_commands" in source
    assert "_git_evidence" in source
    assert "Preserve the project's existing architecture" in source
    print("[PASS] workflow has style-aware planning, transaction safety, tests and Git evidence")

    print()
    print("=" * 78)
    print("STEP 20.8.0 FULL CODING WORKFLOW PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
