from pathlib import Path

from app.agent.edge_router import EdgeIntentRouter
from app.playbooks.engine import PlaybookEngine
from app.playbooks.evaluator import PlaybookDecisionEvaluator


def main():
    print("=" * 72)
    print("RazaAI Step 20.13.16 Support State + Tool Authority")
    print("=" * 72)

    engine = PlaybookEngine()

    query = "Fortigate i can ping and connect SSH but not via web. error is connection refused"
    match = engine.match(query, expert="networking")
    assert match is not None, "FortiGate GUI refusal should match a stateful playbook"
    assert match.id == "fortigate-admin-gui-refused", match.id
    print("[PASS] FortiGate GUI refusal enters a dedicated stateful playbook")

    # A generic server refusal must not collide with a FortiGate-only playbook.
    generic = engine.match("nginx web interface connection refused", expert="servers")
    assert generic is None or generic.id != "fortigate-admin-gui-refused"
    print("[PASS] FortiGate playbook requires FortiGate/FortiOS scope")

    session = engine.start_session(match)
    evaluator = PlaybookDecisionEvaluator()

    decision1 = evaluator.evaluate(
        match.playbook,
        session,
        "Yes they are and the interface has allowed http and https access",
    )
    assert decision1.decision == "passed", decision1
    session.add_observation("Yes they are and the interface has allowed http and https access")
    session.advance(match.playbook)
    assert session.current_step == 1
    print("[PASS] confirmed allowaccess/admin-port evidence advances exactly once")

    resolved = (
        'I found the issue. The system certificate was set to the wrong certificate. '
        'I entered: config system global\n'
        'set admin-server-cert "Fortinet_Factory"\nend\n'
        'now i have access to the web gui'
    )
    decision2 = evaluator.evaluate(match.playbook, session, resolved)
    assert decision2.decision == "isolated", decision2
    assert decision2.evidence.get("fault") == "admin_server_certificate"
    assert decision2.evidence.get("factory_certificate_applied") is True
    assert decision2.evidence.get("gui_access_restored") is True
    assert decision2.evidence.get("resolution_command") == (
        'config system global\nset admin-server-cert "Fortinet_Factory"\nend'
    )
    print("[PASS] wrong admin certificate is isolated and exact known-good fix is preserved")

    # Deterministic lifecycle also works when isolation, correction and
    # validation arrive across separate turns.
    from app.playbooks.lifecycle import PlaybookLifecycleEvaluator
    from app.agent.lifecycle_response import render_lifecycle_response
    from app.incidents.store import IncidentStore
    from app.incidents.bridge import IncidentLifecycleBridge
    import tempfile

    lifecycle = PlaybookLifecycleEvaluator()
    session2 = engine.start_session(match)
    session2.current_step = 1
    session2.status = "needs_resolution"
    session2.lifecycle_context = {"fault": "admin_server_certificate"}
    fix_decision = lifecycle.evaluate_resolution(
        match.playbook,
        session2,
        'config system global\nset admin-server-cert "Fortinet_Factory"\nend',
    )
    assert fix_decision.action == "begin_validation", fix_decision
    session2.status = "waiting_for_validation"
    session2.resolution_evidence = dict(fix_decision.evidence)
    validate_decision = lifecycle.evaluate_validation(
        match.playbook, session2, "the web gui loads now and I have access"
    )
    assert validate_decision.action == "close", validate_decision
    session2.status = "closed"
    session2.validation_evidence = dict(validate_decision.evidence)
    with tempfile.TemporaryDirectory() as td:
        store = IncidentStore(td)
        record = IncidentLifecycleBridge(store).persist_closed(
            playbook=match.playbook, session=session2, category="networking"
        )
        assert record is not None
        assert "admin-server-cert" in record.resolution
        rendered = render_lifecycle_response(session2, validate_decision, record)
        assert "Fortinet_Factory" in rendered
        assert "HTTPS GUI access: PASS" in rendered
    print("[PASS] FortiGate fix/validation closes into durable incident memory")

    knowledge = Path(
        "knowledge/networking/fortigate-admin-gui-access-troubleshooting.md"
    ).read_text(encoding="utf-8")
    cert_pos = knowledge.index("admin-server-cert")
    listener_pos = knowledge.index("diagnose sys tcpsock")
    assert cert_pos < listener_pos
    assert 'set admin-server-cert "Fortinet_Factory"' in knowledge
    print("[PASS] certificate check precedes process/listener restart guidance")

    tech = Path("app/playbooks/technical_guidance.py").read_text(encoding="utf-8")
    assert "admin-server-cert" in tech
    assert "Fortinet_Factory" in tech
    print("[PASS] FortiGate turn guidance includes certificate evidence path")

    fix_message = (
        'I found the issue. The system certificate was wrong; '
        'set admin-server-cert "Fortinet_Factory" fixed it.'
    )
    assert not EdgeIntentRouter._is_document_request(fix_message)
    assert EdgeIntentRouter._is_document_request(
        "create a PDF incident report for this resolved FortiGate issue"
    )
    print("[PASS] reporting a fix is not interpreted as a document request")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "if tool_name not in allowed_model_tool_names:" in agent
    assert "Blocked model-requested tool" in agent
    assert "Blocked unsolicited document creation" in agent
    assert "Incident facts alone are NOT a request to create a document" in agent
    assert "max_model_tool_rounds = 6" in agent
    assert "max_model_tool_calls = 12" in agent
    assert "tool_loop_guard" in agent
    print("[PASS] model tool schemas are enforced as an authority boundary")
    print("[PASS] model tool loops have hard per-turn round/call ceilings")

    docs = Path("app/tools/documents.py").read_text(encoding="utf-8")
    assert "Incident facts alone are not permission to create a file" in docs
    print("[PASS] document schema no longer encourages unsolicited incident reports")

    from app.config import APP_VERSION, version_tuple
    assert version_tuple(APP_VERSION) >= (20, 13, 16), APP_VERSION
    print(f"[PASS] APP_VERSION={APP_VERSION}")

    print("=" * 72)
    print("STEP 20.13.16 SUPPORT STATE + TOOL AUTHORITY PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
