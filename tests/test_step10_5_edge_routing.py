from app.agent.edge_router import EdgeIntentRouter
from unittest.mock import Mock


def main():
    print("\n========================================")
    print("RazaAI Step 10.5 Edge Routing Test")
    print("========================================\n")

    manager = Mock()
    manager.list_hosts.return_value = [{"name": "aruba-core-6100", "type": "aruba", "enabled": True}]
    r = EdgeIntentRouter(manager=manager)

    x = r.route("Check the system status of aruba-core-6100.")
    assert x.kind == "deterministic_tool"
    assert x.tool == "run_infrastructure_check"
    assert x.arguments == {"host": "aruba-core-6100", "check": "system"}
    print("[PASS] system status routes deterministically to system check")

    x = r.route("Inspect port 1/1/5 on aruba-core-6100.")
    assert x.tool == "inspect_aruba_port"
    assert x.arguments["port"] == "1/1/5"
    print("[PASS] explicit Aruba port inspection is deterministic")

    x = r.route("The AP on port 1/1/5 on aruba-core-6100 is offline. Diagnose the switch port.")
    assert x.tool == "diagnose_aruba_port"
    assert x.arguments["port"] == "1/1/5"
    print("[PASS] explicit Aruba port diagnosis is deterministic")

    x = r.route("Diagnose the port on aruba-core-6100.")
    assert x.kind == "needs_input"
    assert "port" in x.missing
    assert not x.arguments
    print("[PASS] missing port is requested; Python never invents one")

    x = r.route(
        "Create a Word and PDF document called Edge Test Report with a Summary section saying the 4B document tool test passed."
    )
    assert x.kind == "deterministic_tool"
    assert x.tool == "create_document"
    assert x.arguments["template"] == "general_document"
    assert x.arguments["format"] == "both"
    assert x.arguments["sections"][0]["paragraphs"] == [
        "the 4B document tool test passed."
    ]
    assert x.interrupts_playbook
    print("[PASS] simple document request is deterministic and playbook-isolated")

    x = r.route("Create an incident report about the Aruba problem.")
    assert x.kind == "document"
    assert x.interrupts_playbook
    print("[PASS] ambiguous incident document stays guarded; facts are not invented")

    print("\n========================================")
    print("STEP 10.5 EDGE ROUTING PASSED")
    print("========================================\n")


if __name__ == "__main__":
    main()
