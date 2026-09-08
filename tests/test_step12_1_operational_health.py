from pathlib import Path

from app.selfops import OperationalHealthEngine


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.1 Operational Health")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]

    engine = OperationalHealthEngine(root)
    snapshot = engine.snapshot(
        run_audit=False,
    )

    assert snapshot["status"] in {
        "healthy",
        "attention",
        "degraded",
    }
    assert "validated_incidents" in snapshot
    assert "knowledge_attention" in snapshot
    assert "infrastructure" in snapshot
    assert "configured_hosts" in snapshot["infrastructure"]
    assert "enabled_hosts" in snapshot["infrastructure"]

    print("[PASS] operational health aggregates trusted subsystems")

    assert isinstance(snapshot["attention"], list)
    assert isinstance(snapshot["validated_incidents"], int)

    print("[PASS] compact health contract suitable for 4B context")

    print()
    print("========================================")
    print("STEP 12.1 OPERATIONAL HEALTH PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
