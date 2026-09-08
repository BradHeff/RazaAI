import tempfile
from pathlib import Path

from app.selfops import SelfAuditEngine, SelfRepairManager


def _project(tmp):
    root = Path(tmp)
    for rel in (
        "app/agent",
        "app/tools",
        "app/incidents",
        "app/memory",
        "scripts",
        "tests",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)

    files = {
        "app/agent/agent.py": "def status():\n    return 'old'\n",
        "app/tools/registry.py": "TOOLS = {}\n",
        "app/ollama_client.py": "class OllamaClient:\n    pass\n",
        "app/incidents/store.py": "class IncidentStore:\n    pass\n",

        "app/memory/store.py": "class MemoryStore:\n    pass\n",
        "app/memory/manager.py": "class MemoryManager:\n    pass\n",
    }
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8")

    return root


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.5 End-to-End Acceptance")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = _project(tmp)
        audit = SelfAuditEngine(root)
        repair = SelfRepairManager(root)

        initial = audit.run(
            mode="quick",
            check_ollama=False,
        )
        assert initial.status == "healthy"

        print("[PASS] RazaAI can establish its own code-health baseline")

        proposal = repair.propose(
            file="app/agent/agent.py",
            old_text="return 'old'",
            new_text="return 'improved'",
            rationale="Acceptance-test controlled self-improvement.",
        )

        before = (
            root / "app/agent/agent.py"
        ).read_text(encoding="utf-8")
        assert "return 'old'" in before

        print("[PASS] self-improvement remains proposal-only before approval")

        result = repair.apply(proposal.patch_id)
        assert result["success"] is True

        after = (
            root / "app/agent/agent.py"
        ).read_text(encoding="utf-8")
        assert "return 'improved'" in after

        print("[PASS] explicit approval applies a backed-up verified patch")

        post = audit.run(
            mode="quick",
            check_ollama=False,
        )
        assert post.status == "healthy"

        print("[PASS] post-repair self-audit remains healthy")

        rolled = repair.rollback(proposal.patch_id)
        assert rolled["success"] is True

        restored = (
            root / "app/agent/agent.py"
        ).read_text(encoding="utf-8")
        assert "return 'old'" in restored

        print("[PASS] explicit rollback restores original source")

    tools_source = (
        Path(__file__).resolve().parents[1]
        / "app/tools/selfops.py"
    ).read_text(encoding="utf-8")
    registry_source = (
        Path(__file__).resolve().parents[1]
        / "app/tools/registry.py"
    ).read_text(encoding="utf-8")

    for tool_name in (
        "audit_project",
        "get_operational_health",
        "get_operational_brief",
        "prepare_self_patch",
    ):
        assert tool_name in registry_source

    assert 'APPLY_SELF_PATCH_METADATA' in tools_source
    assert '"model_exposed": False' in tools_source
    assert 'metadata.get("model_exposed", True)' in registry_source

    print("[PASS] model can inspect/propose but cannot self-authorize writes")

    agent_source = (
        Path(__file__).resolve().parents[1]
        / "app/agent/agent.py"
    ).read_text(encoding="utf-8")
    assert "SELFOPS_TOOL_GUIDANCE" in agent_source
    assert "explicit user" in agent_source.lower()

    print("[PASS] agent carries explicit self-repair approval contract")

    print()
    print("========================================")
    print("STEP 12.5 END-TO-END ACCEPTANCE PASSED")
    print("STEP 12 COMPLETE")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
