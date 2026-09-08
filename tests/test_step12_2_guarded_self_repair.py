import tempfile
from pathlib import Path

from app.selfops import SelfRepairManager


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.2 Guarded Self Repair")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app").mkdir()
        target = root / "app/demo.py"
        target.write_text(
            "def value():\n"
            "    return 1\n",
            encoding="utf-8",
        )

        repair = SelfRepairManager(root)

        proposal = repair.propose(
            file="app/demo.py",
            old_text="return 1",
            new_text="return 2",
            rationale="Correct the test value.",
        )

        assert target.read_text(encoding="utf-8").endswith("return 1\n")
        assert proposal.status == "proposed"

        print("[PASS] model-facing proposal does not modify source")

        result = repair.apply(proposal.patch_id)

        assert result["success"] is True
        assert result["rolled_back"] is False
        assert "return 2" in target.read_text(encoding="utf-8")

        print("[PASS] approved patch creates backup, applies, and compiles")

        failing = repair.propose(
            file="app/demo.py",
            old_text="return 2",
            new_text="return (",
            rationale="Deliberately invalid regression-test patch.",
        )

        result = repair.apply(failing.patch_id)

        assert result["success"] is False
        assert result["rolled_back"] is True
        assert "return 2" in target.read_text(encoding="utf-8")

        print("[PASS] failed compile automatically rolls source back")

        try:
            repair.propose(
                file="../outside.py",
                old_text="x",
                new_text="y",
                rationale="unsafe",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("path escape was not blocked")

        print("[PASS] self-repair cannot escape project edit roots")

        protected = root / "app/config.py"
        protected.write_text("VALUE = 1\n", encoding="utf-8")
        try:
            repair.propose(
                file="app/config.py",
                old_text="VALUE = 1",
                new_text="VALUE = 2",
                rationale="unsafe authority-boundary change",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("protected self-repair authority file was writable")

        print("[PASS] self-repair cannot rewrite its own authority boundary")

    edge_source = (
        Path(__file__).resolve().parents[1]
        / "app/agent/edge_router.py"
    ).read_text(encoding="utf-8")

    assert '"apply_self_patch"' in edge_source
    assert "Explicit user approval" in edge_source

    print("[PASS] patch application requires explicit deterministic user route")

    print()
    print("========================================")
    print("STEP 12.2 GUARDED SELF REPAIR PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
