"""RazaAI exact-patch preservation for existing projects."""

import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class NoModelClient:
    def chat(self, messages, tools=None):
        raise AssertionError("this regression exercises Python write authority directly")


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.0 Exact Patch Preservation")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = (
            "HEADER = 'keep'\n"
            "def target():\n"
            "    return 'old'\n\n"
            + "\n".join(f"UNCHANGED_{i} = {i}" for i in range(600))
            + "\nTAIL = 'must-survive'\n"
        )
        (root / "large.py").write_text(original, encoding="utf-8")

        coworker = WorkspaceCoworker(
            client=NoModelClient(),
            manager=WorkspaceManager(root),
        )
        before = coworker._list()
        written, errors, snapshot = coworker._write_plan(
            {
                "files": [
                    {
                        "path": "large.py",
                        "mode": "patch",
                        "old_text": "def target():\n    return 'old'",
                        "new_text": "def target():\n    return 'new'",
                    }
                ]
            },
            set(coworker._file_paths(before)),
        )

        assert errors == []
        assert written == ["large.py"]
        updated = (root / "large.py").read_text(encoding="utf-8")
        assert "return 'new'" in updated
        assert "TAIL = 'must-survive'" in updated
        assert "UNCHANGED_599 = 599" in updated
        assert len(updated) > 10000
        print("[PASS] exact patch changes only the intended fragment of a large file")

        context = coworker._readable_context("change target", coworker._list())
        assert "FILE: large.py" in context
        assert "CLIPPED: yes" in context
        print("[PASS] planner is told when source context is clipped")

    source = Path("app/coding/coworker.py").read_text(encoding="utf-8")
    assert "MUST use patch mode" in source
    assert "self.manager.patch_file" in source
    assert "_rollback_snapshot" in source
    print("[PASS] clipped-file replacement is structurally guarded")

    print()
    print("=" * 78)
    print("STEP 20.8.0 EXACT PATCH PRESERVATION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
