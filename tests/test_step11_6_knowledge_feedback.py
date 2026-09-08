import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.incidents import (
    IncidentStore,
    KnowledgePromotionEngine,
    KnowledgeFeedbackEngine,
)
import importlib.util

_hybrid_path = Path(__file__).resolve().parents[1] / "app" / "knowledge" / "hybrid.py"
_spec = importlib.util.spec_from_file_location("razaai_hybrid_test", _hybrid_path)
_hybrid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hybrid)
rerank = _hybrid.rerank


def _create(
    store,
    closed_at,
    *,
    root_cause="Staff at the example campus used Access VLAN 30 instead of VLAN 80",
    resolution="Changed Staff WLAN Access VLAN to VLAN 80",
):
    return store.create(
        status="resolved",
        category="networking",
        site="Clare",
        system="Staff",
        symptom="NPS authentication succeeds but Wi-Fi client cannot join",
        root_cause=root_cause,
        resolution=resolution,
        validation={"dhcp": True, "gateway": True, "connectivity": True},
        evidence_source="validated_playbook",
        playbook_id="wifi-nps-no-connectivity",
        created_at=(closed_at - timedelta(minutes=5)).isoformat(),
        closed_at=closed_at.isoformat(),
        evidence={},
    )


def _promote(root, store):
    engine = KnowledgePromotionEngine(store, project_root=root)
    result = engine.promote_eligible()
    assert len(result) == 1
    return result[0]


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.6 Knowledge Feedback")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = IncidentStore(root=root / "data" / "incidents")
        base = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
        for days in (0, 5, 12):
            _create(store, base + timedelta(days=days))
        promoted = _promote(root, store)

        now = base + timedelta(days=13)
        feedback = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: now,
        ).refresh_all()[0]
        assert feedback.knowledge_status == "active"
        baseline = feedback.confidence_score
        assert feedback.confirmations == 3
        assert feedback.contradictions == 0

        _create(store, base + timedelta(days=20))
        feedback = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=21),
        ).refresh_all()[0]
        assert feedback.confirmations == 4
        assert feedback.confidence_score > baseline
        assert feedback.knowledge_status == "active"
        print("[PASS] later validated confirmation strengthens promoted knowledge")

        _create(
            store,
            base + timedelta(days=25),
            root_cause="DHCP relay was missing on VLAN 80",
            resolution="Restored DHCP relay for VLAN 80",
        )
        one_contradiction = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=26),
        ).refresh_all()[0]
        assert one_contradiction.contradictions == 1
        assert one_contradiction.confidence_score < feedback.confidence_score
        print("[PASS] validated contradiction lowers confidence")

        _create(
            store,
            base + timedelta(days=30),
            root_cause="AP trunk omitted VLAN 80",
            resolution="Allowed VLAN 80 on the AP uplink trunk",
        )
        review = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=31),
        ).refresh_all()[0]
        assert review.contradictions == 2
        assert review.knowledge_status == "review"
        assert review.confidence == "low"
        assert Path(promoted.knowledge_path).exists()
        print("[PASS] repeated contradictions move knowledge to review without deletion")

        metadata = json.loads(Path(review.metadata_path).read_text(encoding="utf-8"))
        assert metadata["knowledge_status"] == "review"
        assert metadata["contradictions"] == 2
        assert metadata["confidence_score"] == review.confidence_score
        print("[PASS] feedback persisted into promoted knowledge metadata")

        index = json.loads(
            (root / "data" / "knowledge_promotions" / "index.json").read_text()
        )
        entry = next(iter(index["promotions"].values()))
        assert entry["feedback"]["knowledge_status"] == "review"
        assert entry["feedback"]["contradictions"] == 2
        print("[PASS] provenance index retains deterministic feedback state")

        ranked = rerank(
            "Horizon Staff VLAN 80",
            [
                {
                    "semantic_score": 0.90,
                    "text": "Horizon Staff VLAN 80",
                    "citation": {
                        "knowledge_type": "validated_operational_pattern",
                        "knowledge_status": "review",
                        "confidence_score": review.confidence_score,
                    },
                },
                {
                    "semantic_score": 0.82,
                    "text": "Horizon Staff VLAN 80",
                    "citation": {
                        "knowledge_type": "reference",
                        "confidence": "source-derived",
                    },
                },
            ],
        )
        assert ranked[0]["citation"]["knowledge_type"] == "reference"
        print("[PASS] review status measurably down-ranks promoted RAG knowledge")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = IncidentStore(root=root / "data" / "incidents")
        base = datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
        for days in (0, 5, 12):
            _create(store, base + timedelta(days=days))
        promoted = _promote(root, store)

        stale = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=500),
        ).refresh_all()[0]
        assert stale.stale_days >= 365
        assert stale.knowledge_status == "stale"
        assert Path(promoted.knowledge_path).exists()
        print("[PASS] stale knowledge decays but is never silently deleted")

    print()
    print("========================================")
    print("STEP 11.6 KNOWLEDGE FEEDBACK PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
