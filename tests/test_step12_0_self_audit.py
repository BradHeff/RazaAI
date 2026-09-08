import tempfile
from pathlib import Path

from app.selfops import SelfAuditEngine


def _project(tmp):
    root = Path(tmp)
    for rel in (
        "app/agent",
        "app/tools",
        "app/incidents",
        "scripts",
        "tests",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)

    (root / "app/agent/agent.py").write_text(
        "def healthy():\n    return True\n",
        encoding="utf-8",
    )
    (root / "app/tools/registry.py").write_text(
        "TOOLS = {}\n",
        encoding="utf-8",
    )
    (root / "app/ollama_client.py").write_text(
        "class OllamaClient:\n    pass\n",
        encoding="utf-8",
    )
    (root / "app/incidents/store.py").write_text(
        "class IncidentStore:\n    pass\n",
        encoding="utf-8",
    )

    (root / "app/memory").mkdir(parents=True, exist_ok=True)
    (root / "app/memory/store.py").write_text(
        "class MemoryStore:\n    pass\n",
        encoding="utf-8",
    )
    (root / "app/memory/manager.py").write_text(
        "class MemoryManager:\n    pass\n",
        encoding="utf-8",
    )
    return root


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.0 Self Audit")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = _project(tmp)
        engine = SelfAuditEngine(root)

        report = engine.run(
            mode="quick",
            check_ollama=False,
        )

        assert report.status == "healthy"
        assert report.failed == 0
        assert engine.latest()["audit_id"] == report.audit_id

        print("[PASS] healthy project audit persisted")

        broken = root / "app/agent/broken.py"
        broken.write_text(
            "def broken():\n"
            "    value = 1\n"
            "    if value\n"
            "        return value\n",
            encoding="utf-8",
        )

        report = engine.run(
            mode="quick",
            check_ollama=False,
        )

        assert report.status == "degraded"

        findings = [
            item for item in report.findings
            if item.file == "app/agent/broken.py"
        ]

        assert findings
        assert findings[0].line == 3
        assert findings[0].check == "python_compile"

        print("[PASS] syntax fault reported with exact file and line")

        broken.unlink()
        report = engine.run(
            mode="quick",
            check_ollama=False,
        )
        assert report.status == "healthy"

        print("[PASS] repaired project returns to healthy state")

    print()
    print("========================================")
    print("STEP 12.0 SELF AUDIT PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
