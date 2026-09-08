from pathlib import Path
from tempfile import TemporaryDirectory

from app.incidents import IncidentLifecycleBridge, IncidentStore
from app.playbooks.session import PlaybookSession


PB = {"id": "wifi-nps-no-connectivity", "name": "Wi-Fi", "validation": ["dhcp", "gateway", "connectivity"]}


def session(status="closed"):
    s = PlaybookSession(PB["id"], PB["name"])
    s.status = status
    s.initial_query = "NPS authentication succeeds but the school Wi-Fi client cannot join"
    s.lifecycle_context = {"site": "Clare", "ssid": "Example-Staff", "access_vlan": 30, "expected_vlan": 80}
    s.resolution_evidence = {"configured_vlan": 80}
    s.validation_evidence = {"dhcp": True, "gateway": True, "connectivity": True}
    return s


def main():
    print("\n========================================")
    print("RazaAI Step 11.0 Persistent Incident Memory")
    print("========================================\n")
    with TemporaryDirectory() as tmp:
        store = IncidentStore(Path(tmp) / "incidents")
        bridge = IncidentLifecycleBridge(store)

        assert bridge.persist_closed(playbook=PB, session=session("waiting_for_validation"), category="networking") is None
        print("[PASS] open/waiting incident cannot persist")

        isolated = session("needs_resolution")
        assert bridge.persist_closed(playbook=PB, session=isolated, category="networking") is None
        print("[PASS] isolated root cause alone cannot persist")

        no_validation = session()
        no_validation.validation_evidence = {"dhcp": True}
        assert bridge.persist_closed(playbook=PB, session=no_validation, category="networking") is None
        print("[PASS] fix without complete validation cannot persist")

        closed = session()
        record = bridge.persist_closed(playbook=PB, session=closed, category="networking")
        assert record is not None
        assert record.status == "resolved"
        assert record.site == "Clare"
        assert record.system == "Example-Staff"
        assert "VLAN 30" in record.root_cause and "VLAN 80" in record.root_cause
        assert record.validation == {"dhcp": True, "gateway": True, "connectivity": True}
        assert record.evidence_source == "validated_playbook"
        print("[PASS] validated Python-closed incident persists")

        again = bridge.persist_closed(playbook=PB, session=closed, category="networking")
        assert again.incident_id == record.incident_id
        assert len(store.list_records()) == 1
        print("[PASS] duplicate write protection")

        reopened = IncidentStore(Path(tmp) / "incidents")
        loaded = reopened.get(record.incident_id)
        assert loaded.to_dict() == record.to_dict()
        print("[PASS] records survive a new IncidentStore instance")

        record_path = reopened.records_dir / f"{record.incident_id}.json"
        record_path.write_text("{ definitely broken", encoding="utf-8")
        try:
            reopened.get(record.incident_id)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt record did not fail closed")
        print("[PASS] corrupt record fails safely")

    print("\n========================================")
    print("STEP 11.0 PERSISTENT INCIDENT MEMORY PASSED")
    print("========================================\n")


if __name__ == "__main__":
    main()
