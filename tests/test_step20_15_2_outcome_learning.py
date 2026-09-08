"""RazaAI generalized outcome learning and the closed loop."""

from pathlib import Path
import tempfile

from app.incidents import IncidentStore, KnowledgePromotionEngine
from app.incidents.models import IncidentRecord
from app.incidents.outcomes import (
    IncidentOutcomeBridge,
    OutcomeSessionTracker,
    is_resolution_confirmation,
    is_resolution_denial,
)
from app.incidents.retrieval import IncidentRetriever
from app.memory import MemoryManager, MemoryStore


def _thread(tracker, *, symptom, replies, cause=None):
    tracker.note_user_turn(symptom, mode="troubleshooting", domain="networking")
    for reply in replies:
        tracker.note_assistant_reply(reply)
    if cause:
        tracker.note_cause(cause)


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.2 Outcome Learning")
    print("=" * 78)


    assert is_resolution_confirmation("it's working now")
    assert is_resolution_confirmation("that fixed it")
    assert is_resolution_confirmation("all sorted, thanks")
    assert is_resolution_confirmation("Fixed")
    assert is_resolution_confirmation("the printer's fixed!")
    assert not is_resolution_confirmation("it's not working")
    assert not is_resolution_confirmation("still not working")
    assert not is_resolution_confirmation("fixed the config file earlier but the issue is back")
    assert not is_resolution_confirmation("what does fixed mean?")
    assert is_resolution_denial("still not working")
    assert is_resolution_denial("no, same problem as before")
    assert not is_resolution_denial("working now")
    print("[PASS] resolution confirmation and denial detection")

    # 2. Tracker + bridge: a user-confirmed thread becomes an incident record.
    with tempfile.TemporaryDirectory() as temp:
        store = IncidentStore(root=Path(temp))
        tracker = OutcomeSessionTracker()
        _thread(
            tracker,
            symptom="Staff Wi-Fi at the example campus authenticates but clients never get an IP",
            replies=[
                "Check the WLAN Access VLAN: it should be VLAN 80 for staff. "
                "Change the Access VLAN from 30 to 80 in the Aruba SSID profile, "
                "then reconnect a client and confirm DHCP succeeds."
            ],
            cause="the access vlan was wrong",
        )
        bridge = IncidentOutcomeBridge(store)
        record = bridge.persist_outcome(tracker)
        assert record is not None
        assert record.evidence_source == "user_confirmed_outcome"
        assert record.validation == {"user_confirmed": True}
        assert record.playbook_id == "user-confirmed"
        assert "VLAN 80" in record.resolution
        assert record.root_cause == "the access vlan was wrong"
        assert record.category == "networking"

        # Reload round-trip must accept the new evidence class.
        loaded = store.get(record.incident_id)
        assert loaded.evidence_source == "user_confirmed_outcome"

        # Dedup: the same thread cannot be persisted twice.
        tracker2 = OutcomeSessionTracker()
        _thread(
            tracker2,
            symptom="Staff Wi-Fi at the example campus authenticates but clients never get an IP",
            replies=[record.resolution],
            cause="the access vlan was wrong",
        )
        assert bridge.persist_outcome(tracker2) is not None
        # A tracker that already persisted this fingerprint refuses a repeat.
        _thread(tracker2, symptom=record.symptom, replies=[record.resolution])
        assert bridge.persist_outcome(tracker2) is None
        print("[PASS] user-confirmed outcome persists as an incident with weaker evidence class")

        # No substance, no record.
        empty = OutcomeSessionTracker()
        assert bridge.persist_outcome(empty) is None
        print("[PASS] thread without substance is not persisted")

        # 3. Retrieval: user-confirmed records are eligible but rank lower.
        retriever = IncidentRetriever(store)
        matches = retriever.search(
            "staff Wi-Fi at the example campus authenticates but clients get no IP", category="networking"
        )
        assert any(
            m.incident.evidence_source == "user_confirmed_outcome" for m in matches
        )
        print("[PASS] user-confirmed incidents are retrievable guidance with weaker-evidence reasons")

        # 4. Promotion thresholds: user-confirmed groups need 4 across 3 dates.
        engine = KnowledgePromotionEngine(store, project_root=Path(temp) / "proj")
        candidates = {c.fingerprint: c for c in engine.evaluate()}
        user_groups = [
            c for c in candidates.values() if c.playbook_id == "user-confirmed"
        ]
        assert user_groups, candidates
        group = user_groups[0]
        assert group.count == 2 and not group.eligible
        assert "user-confirmed" in group.reason

        # Add records on two more distinct dates -> 4 incidents / 3 dates.
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        for i in (2, 3):
            day = (base + timedelta(days=i * 7)).isoformat(timespec="seconds")
            store.create(
                status="resolved",
                category="networking",
                site=None,
                system=None,
                symptom=record.symptom,
                root_cause="the access vlan was wrong",
                resolution=record.resolution,
                validation={"user_confirmed": True},
                evidence_source="user_confirmed_outcome",
                playbook_id="user-confirmed",
                created_at=day,
                closed_at=day,
                evidence={},
            )
        candidates = engine.evaluate()
        group = next(
            c for c in candidates if c.playbook_id == "user-confirmed"
        )
        assert group.count >= 4 and group.distinct_dates >= 3, (group.count, group.distinct_dates)
        assert group.eligible, group.reason
        assert group.confidence in {"low", "medium"}  # Capped below playbook high
        print("[PASS] user-confirmed promotion requires 4 incidents across 3 dates; confidence capped")

        # Playbook-validated groups keep the original 3-across-2 rule.
        vday = lambda i: (base + timedelta(days=i)).isoformat(timespec="seconds")  # noqa: E731
        for i in (10, 20, 30):
            store.create(
                status="resolved",
                category="networking",
                site="Example campus",
                system="FortiGate administrative GUI",
                symptom="FortiGate responds to ping but GUI refuses",
                root_cause="invalid admin-server-cert",
                resolution="set a valid admin-server-cert",
                validation={"gui_access": True},
                evidence_source="validated_playbook",
                playbook_id="fortigate-admin-gui-refused",
                created_at=vday(i),
                closed_at=vday(i),
                evidence={},
            )
        group = next(
            c
            for c in engine.evaluate()
            if c.playbook_id == "fortigate-admin-gui-refused"
        )
        assert group.count == 3 and group.eligible and group.reason == (
            "validated recurrence has sufficient temporal spread"
        )
        print("[PASS] playbook-validated groups keep the original 3-across-2-dates rule")

        # 5. Episodic memory: recorded, searchable, labelled as learned resolution.
        memory = MemoryManager(MemoryStore(Path(temp) / "mem"))
        rec = memory.record_episode(
            symptom=record.symptom, resolution=record.resolution, domain="networking"
        )
        assert rec is not None and rec.kind == "episode_summary"
        text = memory.guidance("staff wifi authenticates but no IP", domain="networking")
        assert "LEARNED RESOLUTION" in text and "VLAN 80" in text
        # Sensitive content is refused.
        assert (
            memory.record_episode(
                symptom="password is hunter2", resolution="changed it", domain="general"
            )
            is None
        )
        print("[PASS] episodic memory records user-confirmed resolutions and surfaces them as guidance")


    loop = Path("scripts/learning_loop.py").read_text(encoding="utf-8")
    assert "promote_eligible" in loop and "refresh_all" in loop and "ingest_all" in loop
    headless = Path("deploy/jetson-headless.sh").read_text(encoding="utf-8")
    assert "razaai-learning.timer" in Path("scripts/install-service.sh").read_text()
    timer = Path("deploy/razaai-learning.timer").read_text(encoding="utf-8")
    assert "OnCalendar" in timer
    service = Path("deploy/razaai-learning.service").read_text(encoding="utf-8")
    assert "MemoryMax" in service and "@LAUNCHER@ learn" in service
    print("[PASS] nightly learning loop ships and is wired into deployment")

    print("=" * 78)
    print("STEP 20.15.2 OUTCOME LEARNING PASSED")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
