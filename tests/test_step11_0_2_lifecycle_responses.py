from types import SimpleNamespace
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "raza_lifecycle_response",
    Path("app/agent/lifecycle_response.py"),
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
render_lifecycle_response = module.render_lifecycle_response


def session(status, validation=None):
    return SimpleNamespace(
        status=status,
        validation_evidence=validation or {},
        lifecycle_context={"site":"Clare","ssid":"Staff","access_vlan":30,"expected_vlan":80},
        resolution_evidence={"configured_vlan":80},
    )


def decision(action, missing=None):
    return SimpleNamespace(action=action, missing_evidence=missing or [], evidence={})


def main():
    print("\n========================================")
    print("RazaAI Step 11.0.2 Deterministic Lifecycle Responses")
    print("========================================\n")

    r=render_lifecycle_response(session("waiting_for_validation"), decision("begin_validation"))
    assert "not resolved yet" in r
    assert "DHCP/IP assignment: PENDING" in r
    assert "Internet/end-to-end connectivity: PENDING" in r
    print("[PASS] accepted fix cannot be described as resolved")

    r=render_lifecycle_response(session("waiting_for_validation", {"dhcp":True}), decision("need_validation_evidence", ["gateway","connectivity"]))
    assert "DHCP/IP assignment: PASS" in r
    assert "Gateway reachability: PENDING" in r
    assert "Check next: Confirm gateway reachability." in r
    assert "incident is resolved" not in r.lower()
    print("[PASS] DHCP evidence asks only for remaining validation")

    r=render_lifecycle_response(session("waiting_for_validation", {"dhcp":True,"gateway":True}), decision("need_validation_evidence", ["connectivity"]))
    assert "Gateway reachability: PASS" in r
    assert "Internet/end-to-end connectivity: PENDING" in r
    assert "Check next: Confirm internet/end-to-end connectivity." in r
    print("[PASS] gateway success cannot prematurely close incident")

    inc=SimpleNamespace(incident_id="INC-20260819-0002")
    r=render_lifecycle_response(session("closed", {"dhcp":True,"gateway":True,"connectivity":True}), decision("close"), inc)
    assert "Incident resolved and validated." in r
    assert "Access VLAN 30 instead of VLAN 80" in r
    assert "Incident memory: INC-20260819-0002" in r
    print("[PASS] closed lifecycle renders authoritative resolution summary")

    r=render_lifecycle_response(session("waiting_for_fix"), decision("need_fix_evidence", ["corrected access VLAN"]))
    assert "not resolved yet" in r
    assert "corrected access VLAN" in r
    print("[PASS] waiting-for-fix remains explicitly open")

    print("\n========================================")
    print("STEP 11.0.2 DETERMINISTIC LIFECYCLE RESPONSES PASSED")
    print("========================================\n")

if __name__ == "__main__":
    main()
