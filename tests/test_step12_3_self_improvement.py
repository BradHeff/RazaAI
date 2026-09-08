import tempfile
from pathlib import Path

from app.selfops import SelfRepairManager


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.3 Self Improvement")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app").mkdir()
        path = root / "app/sample.py"
        path.write_text(
            "def add(a, b):\n"
            "    return a + b\n",
            encoding="utf-8",
        )

        manager = SelfRepairManager(root)

        found = manager.search("def add")
        assert found["results"][0]["file"] == "app/sample.py"
        assert found["results"][0]["line"] == 1

        inspected = manager.inspect(
            "app/sample.py",
            1,
            2,
        )
        assert "1: def add(a, b):" in inspected["content"]

        print("[PASS] model can search and inspect its own project code read-only")

        proposal = manager.propose(
            file="app/sample.py",
            old_text="return a + b",
            new_text="return sum((a, b))",
            rationale="Demonstrate controlled refactoring proposal.",
        )

        assert proposal.patch_id.startswith("PATCH-")
        assert "return a + b" in path.read_text(encoding="utf-8")

        print("[PASS] model can prepare evidence-based refactoring proposal")

    tools_source = (
        Path(__file__).resolve().parents[1]
        / "app/tools/selfops.py"
    ).read_text(encoding="utf-8")
    registry_source = (
        Path(__file__).resolve().parents[1]
        / "app/tools/registry.py"
    ).read_text(encoding="utf-8")

    assert '"model_exposed": True' in tools_source
    assert '"model_exposed": False' in tools_source
    assert 'prepare_self_patch' in registry_source
    assert 'apply_self_patch' in registry_source
    assert 'metadata.get("model_exposed", True)' in registry_source

    print("[PASS] write/rollback tools are hidden from Qwen")

    print()
    print("========================================")
    print("STEP 12.3 SELF IMPROVEMENT PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
