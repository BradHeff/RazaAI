import tempfile
from pathlib import Path

from app.selfops.audit import SelfAuditEngine
from app.selfops.repair import SelfRepairManager


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.6 Live Behaviour Hardening")
    print("========================================")
    print()

    project_root = Path(__file__).resolve().parents[1]

    # Natural-language code investigation must locate source before inspection.
    manager = SelfRepairManager(project_root=project_root)
    result = manager.investigate(
        "Inspect your incident retrieval code and tell me whether you can improve it."
    )
    assert result["evidence_found"] is True
    assert result["results"]
    assert result["results"][0]["file"] == "app/incidents/retrieval.py"
    assert "class IncidentRetriever" in result["results"][0]["content"]
    print("[PASS] natural code review searches before inspection and finds production source")

    # Router source must select the composite investigation tool rather than
    # allowing a small model to guess filenames. This source-level assertion
    # avoids importing optional infrastructure/RAG dependencies in the test.
    edge_source = (project_root / "app/agent/edge_router.py").read_text(encoding="utf-8")
    assert "code_investigation_request" in edge_source
    assert 'tool="investigate_project_code"' in edge_source
    assert '"query": text' in edge_source
    print("[PASS] natural self-code review is deterministically routed to investigation")

    # A failed test must be localized to the real project file/line when a
    # traceback provides that information.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app/agent").mkdir(parents=True)
        (root / "app/tools").mkdir(parents=True)
        (root / "app/incidents").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)
        (root / "data").mkdir(parents=True)

        for rel in (
            "app/__init__.py",
            "app/agent/__init__.py",
            "app/tools/__init__.py",
            "app/incidents/__init__.py",
            "tests/__init__.py",
        ):
            (root / rel).write_text("", encoding="utf-8")

        for rel in (
            "app/agent/agent.py",
            "app/tools/registry.py",
            "app/ollama_client.py",
            "app/incidents/store.py",
        ):
            (root / rel).write_text("VALUE = 1\n", encoding="utf-8")

        failing = root / "tests/test_fault_location.py"
        failing.write_text(
            "def main():\n"
            "    value = 1\n"
            "    assert value == 2, 'deliberate Step 12.6 fault'\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n",
            encoding="utf-8",
        )

        audit = SelfAuditEngine(project_root=root)
        report = audit.run(
            mode="quick",
            check_ollama=False,
            tests=["tests.test_fault_location"],
        )
        assert report.status == "degraded"
        finding = next(
            item for item in report.findings
            if item.check == "test:tests.test_fault_location"
        )
        assert finding.file == "tests/test_fault_location.py"
        assert finding.function == "main"
        assert finding.line == 3
        assert "deliberate Step 12.6 fault" in finding.message
    print("[PASS] failed tests report exact file, function, line, and assertion evidence")

    # Guidance must forbid improvement claims after failed inspection and must
    # preserve audit severity instead of letting Qwen minimize failures.
    agent_source = (project_root / "app/agent/agent.py").read_text(encoding="utf-8")
    assert "Never propose a code improvement or patch after a failed inspection" in agent_source
    assert "do not call the project healthy" in agent_source
    assert "STEP 12.6 AUTHORITATIVE SELF-AUDIT REPORTING" in agent_source
    assert "STEP 12.6 CODE INVESTIGATION CONTRACT" in agent_source
    print("[PASS] model guidance forbids unsupported fixes and audit severity downgrades")

    # Old single-execution regression must now be formatting/extension tolerant.
    guard_test = (project_root / "tests/test_step10_5_1_single_execution.py").read_text(
        encoding="utf-8"
    )
    assert "guard = compact[start:end]" in guard_test
    assert "expected = (" not in guard_test
    print("[PASS] Step 10.5.1 regression checks behavior rather than exact guard formatting")

    print()
    print("========================================")
    print("STEP 12.6 LIVE BEHAVIOUR HARDENING PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
