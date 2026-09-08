import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.incidents import IncidentStore, KnowledgePromotionEngine


def _create(store, closed_at, *, category="networking"):
    created_at = (closed_at - timedelta(minutes=5)).isoformat()
    return store.create(
        status="resolved",
        category=category,
        site="Clare",
        system="Staff",
        symptom="NPS authentication succeeds but Wi-Fi client cannot join",
        root_cause="Staff at the example campus used Access VLAN 30 instead of VLAN 80",
        resolution="Changed Staff WLAN Access VLAN to VLAN 80",
        validation={"dhcp": True, "gateway": True, "connectivity": True},
        evidence_source="validated_playbook",
        playbook_id="wifi-nps-no-connectivity",
        created_at=created_at,
        closed_at=closed_at.isoformat(),
        evidence={},
    )


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.5 Knowledge Promotion")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = IncidentStore(root=root / "data" / "incidents")
        base = datetime(2026, 8, 19, 1, 0, tzinfo=timezone.utc)
        for offset in (0, 10, 20):
            _create(store, base + timedelta(minutes=offset))

        engine = KnowledgePromotionEngine(store, project_root=root)
        candidates = engine.evaluate()
        assert len(candidates) == 1
        assert candidates[0].eligible is False
        assert candidates[0].distinct_dates == 1
        assert engine.promote_eligible() == []
        assert not (root / "knowledge" / "networking" / "promoted").exists()

        print("[PASS] same-day test duplicates cannot promote to knowledge")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = IncidentStore(root=root / "data" / "incidents")
        base = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
        for days in (0, 5, 12):
            _create(store, base + timedelta(days=days))

        engine = KnowledgePromotionEngine(store, project_root=root)
        candidates = engine.evaluate()
        candidate = candidates[0]
        assert candidate.eligible is True
        assert candidate.count == 3
        assert candidate.distinct_dates == 3

        result = engine.promote(candidate)
        assert result.status == "promoted"
        path = Path(result.knowledge_path)
        meta = Path(result.metadata_path)
        assert path.exists()
        assert meta.exists()
        text = path.read_text(encoding="utf-8")
        assert "Validated Root Cause" in text
        assert "Access VLAN 30 instead of VLAN 80" in text
        assert "Changed Staff WLAN Access VLAN to VLAN 80" in text
        assert "not proof of a new incident" in text

        metadata = json.loads(meta.read_text(encoding="utf-8"))
        assert metadata["category"] == "networking"
        assert metadata["knowledge_type"] == "validated_operational_pattern"

        print(
            "[PASS] temporally credible validated pattern promotes to curated Markdown"
        )
        print("[PASS] promoted metadata preserves knowledge category and provenance")

        _create(store, base + timedelta(days=20))
        updated = engine.promote_eligible()
        assert len(updated) == 1
        assert updated[0].status == "updated"
        promoted_files = list(
            (root / "knowledge" / "networking" / "promoted").glob("*.md")
        )
        assert len(promoted_files) == 1

        print("[PASS] repeated promotion updates one durable knowledge source")

        index = json.loads(
            (root / "data" / "knowledge_promotions" / "index.json").read_text()
        )
        assert len(index["promotions"]) == 1
        entry = next(iter(index["promotions"].values()))
        assert entry["count"] == 4

        print("[PASS] promotion provenance index tracks supporting incidents")

    print()
    print("========================================")
    print("STEP 11.5 KNOWLEDGE PROMOTION PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
