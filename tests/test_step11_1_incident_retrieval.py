import tempfile
from pathlib import Path

from app.incidents import IncidentStore, IncidentRetriever


def create_record(
    store,
    *,
    closed_at,
    category,
    site,
    system,
    symptom,
    root_cause,
    resolution,
    playbook_id,
):
    return store.create(
        status="resolved",
        category=category,
        site=site,
        system=system,
        symptom=symptom,
        root_cause=root_cause,
        resolution=resolution,
        validation={
            "dhcp": True,
            "gateway": True,
            "connectivity": True,
        },
        evidence_source="validated_playbook",
        playbook_id=playbook_id,
        created_at=closed_at,
        closed_at=closed_at,
        evidence={
            "lifecycle_context": {
                "site": site,
                "ssid": system,
            }
        },
    )


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.1 Incident Retrieval Test")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        store = IncidentStore(Path(tmp) / "incidents")

        clare = create_record(
            store,
            closed_at="2026-08-19T05:00:00+00:00",
            category="networking",
            site="Clare",
            system="Staff",
            symptom=(
                "NPS authentication succeeds but the school " "Wi-Fi client cannot join"
            ),
            root_cause=("Staff at the example campus used Access VLAN 30 instead of VLAN 80"),
            resolution="Changed Staff WLAN Access VLAN to VLAN 80",
            playbook_id="wifi-nps-no-connectivity",
        )

        balaklava = create_record(
            store,
            closed_at="2026-08-18T05:00:00+00:00",
            category="networking",
            site="Balaklava",
            system="Staff",
            symptom=(
                "NPS authentication succeeds but the school " "Wi-Fi client cannot join"
            ),
            root_cause=("Staff WLAN had an incorrect access VLAN at Balaklava"),
            resolution="Corrected Staff WLAN VLAN",
            playbook_id="wifi-nps-no-connectivity",
        )

        create_record(
            store,
            closed_at="2026-08-17T05:00:00+00:00",
            category="microsoft",
            site="Clare",
            system="Printer",
            symptom="Printer deployment failed through Group Policy",
            root_cause="Printer GPP item was configured incorrectly",
            resolution="Corrected the printer deployment item",
            playbook_id="printer-deployment-failure",
        )

        retriever = IncidentRetriever(store)

        query = (
            "NPS authentication succeeds but Example-Staff at the example campus "
            "cannot connect to Wi-Fi"
        )

        matches = retriever.search(
            query,
            category="networking",
            playbook_id="wifi-nps-no-connectivity",
            top_k=3,
        )

        if not matches:
            raise AssertionError("Exact prior incident was not retrieved")

        if matches[0].incident.incident_id != clare.incident_id:
            raise AssertionError("Clare Wi-Fi incident did not rank first")

        if matches[0].confidence != "high":
            raise AssertionError("Exact recurrence should have high confidence")

        print("[PASS] exact Clare Wi-Fi recurrence ranks first")

        if (
            len(matches) > 1
            and matches[1].incident.incident_id != balaklava.incident_id
        ):
            raise AssertionError(
                "Same-playbook Balaklava incident should outrank unrelated history"
            )

        print("[PASS] same-playbook history outranks unrelated incidents")

        unrelated = retriever.search(
            "Linux desktop Nvidia Xorg display driver failure",
            category="linux",
            playbook_id=None,
            top_k=3,
        )

        if unrelated:
            raise AssertionError("Unrelated incident history was not suppressed")

        print("[PASS] unrelated history suppressed below threshold")

        again = retriever.search(
            query,
            category="networking",
            playbook_id="wifi-nps-no-connectivity",
            top_k=3,
        )

        if [m.incident.incident_id for m in matches] != [
            m.incident.incident_id for m in again
        ]:
            raise AssertionError("Ranking is not deterministic")

        print("[PASS] deterministic ordering")

        guidance = retriever.guidance(matches[:2])

        if len(guidance) > 1800:
            raise AssertionError("4B incident context exceeded budget")

        for required in [
            "VALIDATED PRIOR INCIDENT MEMORY",
            clare.incident_id,
            "historical evidence only",
            "Do NOT assume a prior root cause",
        ]:
            if required not in guidance:
                raise AssertionError(f"Missing compact guidance text: {required}")

        print("[PASS] compact 4B historical-evidence context")

        assert all(
            match.incident.status == "resolved"
            and match.incident.evidence_source == "validated_playbook"
            and all(match.incident.validation.values())
            for match in matches
        )

        print("[PASS] only validated resolved incidents are eligible")

    print()
    print("========================================")
    print("STEP 11.1 INCIDENT RETRIEVAL PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
