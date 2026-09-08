import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.incidents import (
    IncidentStore,
    IncidentPatternAnalyzer,
    IncidentTrendAnalyzer,
)
from app.incidents.retrieval import IncidentMatch


def _create(store, closed_at):
    created_at = (
        datetime.fromisoformat(closed_at)
        - timedelta(minutes=5)
    ).isoformat()

    return store.create(
        status="resolved",
        category="networking",
        site="Clare",
        system="Staff",
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
        evidence={},
    )


def _match(record):
    return IncidentMatch(
        incident=record,
        score=16.0,
        confidence="high",
        reasons=("same playbook", "same site"),
    )


def _analyze(times):
    tmp = tempfile.TemporaryDirectory()
    store = IncidentStore(root=Path(tmp.name) / "incidents")
    records = [_create(store, value.isoformat()) for value in times]
    patterns = IncidentPatternAnalyzer(store).analyze_matches([_match(records[-1])])
    trends = IncidentTrendAnalyzer(store).analyze_patterns(patterns)
    return tmp, trends


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.3 Operational Trends")
    print("========================================")
    print()

    base = datetime(2026, 8, 19, 1, 0, tzinfo=timezone.utc)
    tmp, trends = _analyze([base, base + timedelta(hours=2), base + timedelta(hours=4)])
    try:
        assert trends[0].status == "watch"
        assert trends[0].distinct_dates == 1
        assert trends[0].escalation_required is False
    finally:
        tmp.cleanup()
    print("[PASS] same-day duplicates do not become operational escalation")

    base = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
    tmp, trends = _analyze([base, base + timedelta(days=4), base + timedelta(days=8)])
    try:
        assert trends[0].status == "trend"
        assert trends[0].distinct_dates == 3
        assert trends[0].escalation_required is False
    finally:
        tmp.cleanup()
    print("[PASS] repeated validated incidents across dates become trend")

    base = datetime(2026, 7, 1, 1, 0, tzinfo=timezone.utc)
    tmp, trends = _analyze([
        base,
        base + timedelta(days=7),
        base + timedelta(days=14),
        base + timedelta(days=21),
    ])
    try:
        trend = trends[0]
        assert trend.status == "escalate"
        assert trend.distinct_dates == 4
        assert trend.escalation_required is True
        assert "standardise" in trend.recommendation.lower()

        guidance = IncidentTrendAnalyzer(
            IncidentStore(root=Path(tmp.name) / "incidents")
        ).guidance(trends)

        assert "ESCALATION RECOMMENDED" in guidance
        assert "permanent corrective action" in guidance
        assert len(guidance) <= 1200
    finally:
        tmp.cleanup()

    print("[PASS] persistent recurrence triggers deterministic escalation")
    print("[PASS] compact 4B escalation guidance")

    print()
    print("========================================")
    print("STEP 11.3 OPERATIONAL TREND INTELLIGENCE PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
