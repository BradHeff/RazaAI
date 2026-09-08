import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.incidents import (
    IncidentStore,
    IncidentPatternAnalyzer,
    LearnedResolutionAnalyzer,
)
from app.incidents.retrieval import IncidentMatch


def _create(store, *, closed_at, site="Clare", system="Staff"):
    created_at = (
        datetime.fromisoformat(closed_at) - timedelta(minutes=5)
    ).isoformat()

    return store.create(
        status="resolved",
        category="networking",
        site=site,
        system=system,
        symptom="NPS authentication succeeds but Wi-Fi client cannot join",
        root_cause="Staff at the example campus used Access VLAN 30 instead of VLAN 80",
        resolution="Changed Staff WLAN Access VLAN to VLAN 80",
        validation={
            "dhcp": True,
            "gateway": True,
            "connectivity": True,
        },
        evidence_source="validated_playbook",
        playbook_id="wifi-nps-no-connectivity",
        created_at=created_at,
        closed_at=closed_at,
        evidence={
            "lifecycle_context": {
                "site": "Clare",
                "ssid": "Staff",
                "access_vlan": 30,
                "expected_vlan": 80,
            },
            "resolution_evidence": {"configured_vlan": 80},
            "validation_evidence": {
                "dhcp": True,
                "gateway": True,
                "connectivity": True,
            },
        },
    )


def _match(record):
    return IncidentMatch(
        incident=record,
        score=16.0,
        confidence="high",
        reasons=("same playbook", "same site", "same system"),
    )


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.4 Learned Resolutions")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        store = IncidentStore(root=Path(tmp) / "incidents")
        base = datetime(2026, 8, 19, 1, 0, tzinfo=timezone.utc)

        only = _create(store, closed_at=base.isoformat())
        patterns = IncidentPatternAnalyzer(store).analyze_matches([_match(only)])
        learned = LearnedResolutionAnalyzer(store).analyze_patterns(patterns)

        assert learned == []
        print("[PASS] single prior incident does not become learned resolution")

    with tempfile.TemporaryDirectory() as tmp:
        store = IncidentStore(root=Path(tmp) / "incidents")
        base = datetime(2026, 8, 19, 1, 0, tzinfo=timezone.utc)
        records = [
            _create(store, closed_at=(base + timedelta(minutes=i * 10)).isoformat())
            for i in range(3)
        ]

        patterns = IncidentPatternAnalyzer(store).analyze_matches([_match(records[-1])])
        learned = LearnedResolutionAnalyzer(store).analyze_patterns(patterns)

        assert len(learned) == 1
        item = learned[0]
        assert item.count == 3
        assert item.confidence == "high"
        assert item.site == "Clare"
        assert item.system == "Staff"
        assert "VLAN 30" in item.root_cause
        assert "VLAN 80" in item.resolution

        print("[PASS] repeated validated fix becomes learned resolution")

        assert set(item.validation_required) == {
            "dhcp",
            "gateway",
            "connectivity",
        }
        print("[PASS] common validated closure requirements retained")

        assert "Verify the current WLAN/SSID Access VLAN" in item.verification_first
        print("[PASS] current-evidence verification required before historical fix")

        guidance = LearnedResolutionAnalyzer(store).guidance(learned)
        assert "LEARNED RESOLUTION INTELLIGENCE" in guidance
        assert "NOT as proof of the current root cause" in guidance
        assert "Do not state that the current cause is confirmed" in guidance
        assert len(guidance) <= 1300

        print("[PASS] compact 4B guidance prevents automatic root-cause promotion")

    print()
    print("========================================")
    print("STEP 11.4 LEARNED RESOLUTION INTELLIGENCE PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
