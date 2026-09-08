from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.incidents import (
    IncidentStore,
    IncidentRetriever,
    IncidentPatternAnalyzer,
    IncidentTrendAnalyzer,
    LearnedResolutionAnalyzer,
    KnowledgePromotionEngine,
    KnowledgeFeedbackEngine,
)

QUERY = "NPS authentication succeeds but Example-Staff at the example campus cannot connect to Wi-Fi"
PLAYBOOK_ID = "wifi-nps-no-connectivity"
CATEGORY = "networking"
SITE = "Clare"
SYSTEM = "Staff"
ROOT_CAUSE = "Staff at the example campus used Access VLAN 30 instead of VLAN 80"
RESOLUTION = "Changed Staff WLAN Access VLAN to VLAN 80"


def _create(
    store: IncidentStore,
    closed_at: datetime,
    *,
    root_cause: str = ROOT_CAUSE,
    resolution: str = RESOLUTION,
):
    return store.create(
        status="resolved",
        category=CATEGORY,
        site=SITE,
        system=SYSTEM,
        symptom="NPS authentication succeeds but Wi-Fi client cannot join",
        root_cause=root_cause,
        resolution=resolution,
        validation={
            "dhcp": True,
            "gateway": True,
            "connectivity": True,
        },
        evidence_source="validated_playbook",
        playbook_id=PLAYBOOK_ID,
        created_at=(closed_at - timedelta(minutes=15)).isoformat(),
        closed_at=closed_at.isoformat(),
        evidence={"source": "step11.7 acceptance"},
    )


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.7 End-to-End Acceptance")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = IncidentStore(root=root / "data" / "incidents")

        base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        confirmations = [
            _create(store, base),
            _create(store, base + timedelta(days=7)),
            _create(store, base + timedelta(days=14)),
        ]

        assert len(store.list_records()) == 3
        print("[PASS] validated incident history persisted")

        retriever = IncidentRetriever(store)
        matches = retriever.search(
            QUERY,
            category=CATEGORY,
            playbook_id=PLAYBOOK_ID,
            top_k=2,
        )
        assert matches
        assert matches[0].incident.site == SITE
        assert matches[0].incident.system == SYSTEM
        assert matches[0].confidence == "high"
        print("[PASS] validated prior incident retrieved and ranked")

        pattern_analyzer = IncidentPatternAnalyzer(store)
        patterns = pattern_analyzer.analyze_matches(matches)
        assert patterns
        assert patterns[0].count == 3
        assert set(patterns[0].incident_ids) == {
            record.incident_id for record in confirmations
        }
        print("[PASS] recurrence pattern reconstructed from full incident store")

        trend_analyzer = IncidentTrendAnalyzer(store)
        trends = trend_analyzer.analyze_patterns(patterns)
        assert trends
        assert trends[0].status == "trend"
        assert trends[0].distinct_dates == 3
        assert trends[0].escalation_required is False
        print("[PASS] temporal recurrence classified as operational trend")

        learned_analyzer = LearnedResolutionAnalyzer(store)
        learned = learned_analyzer.analyze_patterns(patterns)
        assert learned
        assert learned[0].root_cause == ROOT_CAUSE
        assert learned[0].resolution == RESOLUTION
        assert set(learned[0].validation_required) == {
            "dhcp",
            "gateway",
            "connectivity",
        }
        assert "Verify" in learned[0].verification_first
        print("[PASS] repeated validated fix became learned resolution")

        promotions = KnowledgePromotionEngine(store, project_root=root)
        candidates = promotions.evaluate()
        eligible = [candidate for candidate in candidates if candidate.eligible]
        assert len(eligible) == 1
        candidate = eligible[0]
        assert candidate.count == 3
        assert candidate.distinct_dates == 3

        promoted = promotions.promote(candidate)
        assert promoted.status == "promoted"
        assert promoted.knowledge_path
        assert promoted.metadata_path
        knowledge_path = Path(promoted.knowledge_path)
        metadata_path = Path(promoted.metadata_path)
        assert knowledge_path.exists()
        assert metadata_path.exists()

        markdown = knowledge_path.read_text(encoding="utf-8")
        assert ROOT_CAUSE in markdown
        assert RESOLUTION in markdown
        assert "Confirm current evidence" in markdown
        print("[PASS] temporally credible pattern promoted to curated knowledge")

        feedback = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=15),
        )
        items = feedback.refresh_all()
        assert len(items) == 1
        initial = items[0]
        assert initial.knowledge_status == "active"
        assert initial.confidence == "high"
        assert initial.confirmations == 3
        assert initial.contradictions == 0
        print("[PASS] promoted knowledge starts active from validated confirmations")

        fourth = _create(store, base + timedelta(days=21))
        assert fourth.incident_id

        updated = promotions.promote_eligible()
        assert len(updated) == 1
        assert updated[0].status == "updated"
        assert updated[0].knowledge_path == str(knowledge_path)

        feedback = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=22),
        )
        reinforced = feedback.refresh_all()[0]
        assert reinforced.knowledge_status == "active"
        assert reinforced.confidence == "high"
        assert reinforced.confirmations == 4
        assert reinforced.contradictions == 0
        assert knowledge_path.exists()
        print("[PASS] later confirmation strengthens one durable knowledge source")

        _create(
            store,
            base + timedelta(days=28),
            root_cause="DHCP relay on VLAN 80 was misconfigured",
            resolution="Corrected the VLAN 80 DHCP relay configuration",
        )
        _create(
            store,
            base + timedelta(days=35),
            root_cause="DHCP scope for VLAN 80 was exhausted",
            resolution="Restored available leases in the VLAN 80 DHCP scope",
        )

        feedback = KnowledgeFeedbackEngine(
            store,
            project_root=root,
            now_fn=lambda: base + timedelta(days=36),
        )
        reviewed = feedback.refresh_all()[0]
        assert reviewed.knowledge_status == "review"
        assert reviewed.confidence == "low"
        assert reviewed.confirmations == 4
        assert reviewed.contradictions == 2
        assert knowledge_path.exists(), "review must not delete promoted knowledge"

        sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert sidecar["knowledge_status"] == "review"
        assert sidecar["contradictions"] == 2
        print("[PASS] contradictory validated incidents move knowledge to review")
        print("[PASS] review state preserves the promoted knowledge source")

        promotion_source = (
            (
                Path(__file__).resolve().parents[1]
                / "app"
                / "incidents"
                / "promotions.py"
            )
            .read_text(encoding="utf-8")
            .lower()
        )
        assert "qdrant_client" not in promotion_source
        assert "upsert(" not in promotion_source
        print("[PASS] promotion remains file-backed; Qdrant ingestion stays separate")

    print()
    print("========================================")
    print("STEP 11.7 END-TO-END ACCEPTANCE PASSED")
    print("STEP 11 COMPLETE")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
