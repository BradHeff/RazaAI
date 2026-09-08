"""Python-authoritative coding coworker execution."""

import json
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class FakeClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        assert tools is None
        return {
            "message": {
                "content": json.dumps(
                    {
                        "files": [
                            {
                                "path": "app.py",
                                "content": (
                                    "import tkinter as tk\n"
                                    "from tkinter import filedialog\n\n"
                                    "def choose():\n"
                                    "    path = filedialog.askdirectory()\n"
                                    "    if path:\n"
                                    "        label.config(text=path)\n\n"
                                    "root = tk.Tk()\n"
                                    "root.title('File Browser')\n"
                                    "label = tk.Label(root, text='Choose a directory')\n"
                                    "label.pack()\n"
                                    "tk.Button(root, text='Browse', command=choose).pack()\n"
                                    "root.mainloop()\n"
                                ),
                            }
                        ],
                        "summary": "Created a Tkinter directory browser.",
                    }
                )
            }
        }


def main():
    print("=" * 78)
    print("RazaAI Step 20.7.2 Workspace Coworker Execution")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as tmp:
        manager = WorkspaceManager(tmp)
        coworker = WorkspaceCoworker(client=FakeClient(), manager=manager)
        result = coworker.handle("create app to list files in python")
        app = Path(tmp) / "app.py"
        assert app.is_file()
        assert app.stat().st_size > 100
        assert "tkinter" in app.read_text(encoding="utf-8")
        assert "Created:" in result
        assert "`app.py`" in result
        assert "Verification: PASS" in result
        print("[PASS] create-app request produces a real non-empty workspace file")

        shown = coworker.handle("show me the code")
        assert "### app.py" in shown
        assert "tkinter" in shown
        print("[PASS] show-code response is grounded by an actual workspace read")

        listing = coworker.handle("show workspace files")
        assert "app.py" in listing
        assert str(Path(tmp).resolve()) in listing
        print("[PASS] workspace listing reports real filesystem state")

    source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "self.workspace_coworker.should_handle(user_input)" in source
    assert "Coding workspace operation failed" in source
    print("[PASS] agent intercepts coworker operations before unsupported model narration")

    print()
    print("=" * 78)
    print("STEP 20.7.2 WORKSPACE COWORKER EXECUTION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
