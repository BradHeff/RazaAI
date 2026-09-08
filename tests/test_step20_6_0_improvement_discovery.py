"""RazaAI evidence-backed improvement discovery."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.selfops.discovery import ImprovementDiscoveryEngine


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main():
    print("=" * 76)
    print("RazaAI Step 20.6.0 Improvement Discovery")
    print("=" * 76)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app/playbooks").mkdir(parents=True)
        (root / "app/agent").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)
        (root / "scripts").mkdir(parents=True)
        (root / "output/model-evals").mkdir(parents=True)
        (root / "data/self_audits").mkdir(parents=True)

        (root / "app/playbooks/technical_guidance.py").write_text(
            'GUIDANCE = "needs evidence"\n', encoding="utf-8"
        )
        (root / "app/agent/edge_router.py").write_text(
            'ROUTER = "authority"\n', encoding="utf-8"
        )
        (root / "tests/test_live_gap.py").write_text(
            'def main():\n    raise AssertionError("live gap")\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8",
        )
        (root / "tests/test_stale_gap.py").write_text(
            'def main():\n    assert True\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8",
        )

        now = datetime.now(timezone.utc)
        audit = {
            "audit_id": "AUDIT-TEST-FULL",
            "created_at": now.isoformat(),
            "mode": "full",
            "status": "degraded",
            "findings": [
                {
                    "severity": "high",
                    "check": "test:tests.test_live_gap",
                    "message": "AssertionError: live gap",
                    "file": "app/playbooks/technical_guidance.py",
                },
                {
                    "severity": "high",
                    "check": "test:tests.test_stale_gap",
                    "message": "AssertionError: stale gap",
                    "file": "app/playbooks/technical_guidance.py",
                },
                {
                    "severity": "critical",
                    "check": "authority_boundary",
                    "message": "Router authority requires manual review",
                    "file": "app/agent/edge_router.py",
                },
            ],
        }
        _write_json(root / "data/self_audits/AUDIT-TEST-FULL.json", audit)

        engine = ImprovementDiscoveryEngine(project_root=root)
        report = engine.discover(limit=5)
        opportunities = report["opportunities"]

        assert any(item["case_id"] == "tests.test_live_gap" for item in opportunities)
        assert not any(item["case_id"] == "tests.test_stale_gap" for item in opportunities)
        print("[PASS] persisted test failures are revalidated; stale failures are retired")

        protected = next(item for item in opportunities if item["file"] == "app/agent/edge_router.py")
        assert protected["risk"] == "protected"
        assert protected["auto_eligible"] is False
        print("[PASS] protected authority findings are discovered but manual-only")

        selected = report["selected"]
        assert selected is not None
        assert selected["case_id"] == "tests.test_live_gap"
        assert selected["auto_eligible"] is True
        print("[PASS] highest-ranked safe current opportunity is selected for auto improvement")

        # A failed capability report becomes stale if source changed after it.
        old = now - timedelta(hours=1)
        eval_report = {
            "generated_at": old.isoformat(),
            "model": "raza-edge:4b-v3",
            "results": [{
                "case_id": "cap.old.failure",
                "category": "networking",
                "passed": False,
                "hard_gate": True,
                "failures": ["old failure"],
            }],
        }
        _write_json(root / "output/model-evals/capability-old.json", eval_report)
        os.utime(root / "app/playbooks/technical_guidance.py", None)
        report = engine.discover(limit=10)
        assert not any(item.get("case_id") == "cap.old.failure" for item in report["opportunities"])
        print("[PASS] capability failures older than current source are not auto-reused")

    print()
    print("=" * 76)
    print("STEP 20.6.0 IMPROVEMENT DISCOVERY PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
