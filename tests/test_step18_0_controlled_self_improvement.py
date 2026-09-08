import tempfile
from pathlib import Path

from app.selfops.improvement import SelfImprovementManager


def main():
    print("="*72)
    print("RazaAI Step 18.0 Controlled Self-Improvement")
    print("="*72)

    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"app").mkdir(); (root/"tests").mkdir(); (root/"scripts").mkdir()
        (root/"app/__init__.py").write_text("",encoding="utf-8")
        (root/"tests/__init__.py").write_text("",encoding="utf-8")
        (root/"app/sample.py").write_text("def value():\n    return 1\n",encoding="utf-8")
        (root/"tests/test_goal.py").write_text(
            "from app.sample import value\n"
            "assert value() == 2\n",
            encoding="utf-8",
        )

        manager=SelfImprovementManager(root)
        job=manager.start(
            "Improve sample value behavior",
            targeted_tests=["tests.test_goal"],
        )
        iid=job["improvement_id"]
        assert "return 1" in (root/"app/sample.py").read_text()
        print("[PASS] improvement begins in isolated workspace")

        job=manager.stage_patch(
            iid,file="app/sample.py",old_text="return 1",new_text="return 2",
            rationale="Targeted test requires corrected value.",
        )
        assert "return 1" in (root/"app/sample.py").read_text()
        sandbox=root/job["workspace"]/"app/sample.py"
        assert "return 2" in sandbox.read_text()
        print("[PASS] candidate patch changes sandbox only")

        job=manager.stage_patch(
            iid,file="tests/test_improvement_value.py",old_text=None,
            new_text="from app.sample import value\nassert value() == 2\n",
            rationale="Lock corrected behavior.",candidate_test=True,
        )
        print("[PASS] autonomous job may add a new regression test")

        try:
            manager.stage_patch(
                iid,file="tests/test_goal.py",old_text="== 2",new_text="== 1",
                rationale="weaken test",
            )
        except ValueError as exc:
            assert "immutable" in str(exc)
        else:
            raise AssertionError("existing trusted test was editable")
        print("[PASS] existing trusted tests cannot be weakened")

        verified=manager.verify(iid,full=False)
        assert verified["verified"] is True
        assert verified["regressions"] == 0
        assert verified["verification"]["baseline"][0]["success"] is False
        assert verified["verification"]["candidate"][0]["success"] is True
        print("[PASS] Python compares baseline and candidate before promotion")

        promoted=manager.promote(iid)
        assert promoted["status"]=="promoted"
        assert "return 2" in (root/"app/sample.py").read_text()
        print("[PASS] approved verified candidate promotes atomically")

        rolled=manager.rollback(iid)
        assert rolled["status"]=="rolled_back"
        assert "return 1" in (root/"app/sample.py").read_text()
        print("[PASS] promoted improvement has rollback")

        assert manager.classify_risk("app/agent/agent.py")=="protected"
        assert manager.classify_risk("app/documents/pdf_writer.py")=="medium"
        assert manager.classify_risk("app/helpers.py")=="low"
        print("[PASS] improvement files are risk classified")

    print("\n"+"="*72)
    print("STEP 18.0 CONTROLLED SELF-IMPROVEMENT PASSED")
    print("="*72)


if __name__=="__main__":
    main()
