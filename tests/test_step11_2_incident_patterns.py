import tempfile
from pathlib import Path

from app.incidents import IncidentStore, IncidentRetriever, IncidentPatternAnalyzer


def make(
    store,
    incident_id,
    *,
    site="Clare",
    system="Staff",
    root=None,
    resolution=None,
    closed="2026-08-19T01:00:00+00:00"
):
    return store.create(
        incident_id=incident_id,
        status="resolved",
        category="networking",
        site=site,
        system=system,
        symptom="NPS authentication succeeds but school Wi-Fi client cannot join",
        root_cause=root or "Staff at the example campus used Access VLAN 30 instead of VLAN 80",
        resolution=resolution or "Changed Staff WLAN Access VLAN to VLAN 80",
        validation={"dhcp": True, "gateway": True, "connectivity": True},
        evidence_source="validated_playbook",
        playbook_id="wifi-nps-no-connectivity",
        created_at="2026-08-19T00:00:00+00:00",
        closed_at=closed,
        evidence={"lifecycle_context": {"site": site, "ssid": "Staff"}},
    )


def main():
    print("\n========================================")
    print("RazaAI Step 11.2 Incident Pattern Intelligence")
    print("========================================\n")

    with tempfile.TemporaryDirectory() as tmp:
        store = IncidentStore(Path(tmp) / "incidents")
        make(store, "INC-20260819-0001", closed="2026-08-19T01:00:00+00:00")
        make(store, "INC-20260819-0002", closed="2026-08-19T02:00:00+00:00")
        make(store, "INC-20260819-0003", closed="2026-08-19T03:00:00+00:00")
        make(
            store,
            "INC-20260819-0004",
            site="Balaklava",
            system="Printer",
            root="Printer queue stalled",
            resolution="Restarted print spooler",
            closed="2026-08-19T04:00:00+00:00",
        )

        retriever = IncidentRetriever(store)
        analyzer = IncidentPatternAnalyzer(store)
        matches = retriever.search(
            "NPS authentication succeeds but Example-Staff at the example campus cannot connect to Wi-Fi",
            category="networking",
            playbook_id="wifi-nps-no-connectivity",
            top_k=2,
        )
        patterns = analyzer.analyze_matches(matches)

        assert patterns
        p = patterns[0]
        assert p.count == 3
        assert p.site == "Clare"
        assert p.system == "Staff"
        assert p.confidence == "high"
        assert p.incident_ids == (
            "INC-20260819-0001",
            "INC-20260819-0002",
            "INC-20260819-0003",
        )
        print("[PASS] repeated validated incident pattern counted")
        print("[PASS] unrelated incident excluded from recurrence")
        print("[PASS] first/last seen ordering deterministic")

        guidance = analyzer.guidance(patterns)
        assert "count=3" in guidance
        assert "does NOT prove" in guidance
        assert len(guidance) <= 1000
        print("[PASS] compact 4B recurrence context")
        print("[PASS] recurrence cannot be treated as current proof")

        store2 = IncidentStore(Path(tmp) / "single")
        make(store2, "INC-20260819-0001")
        r2 = IncidentRetriever(store2)
        a2 = IncidentPatternAnalyzer(store2)
        m2 = r2.search(
            "NPS authentication succeeds at the example campus",
            category="networking",
            playbook_id="wifi-nps-no-connectivity",
        )
        assert a2.analyze_matches(m2) == []
        print("[PASS] single prior incident is not labelled recurrence")

    print("\n========================================")
    print("STEP 11.2 INCIDENT PATTERN INTELLIGENCE PASSED")
    print("========================================\n")


if __name__ == "__main__":
    main()
