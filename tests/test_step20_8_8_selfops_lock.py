"""RazaAI:  self-modification is locked unless RAZAAI_SELFOPS is enabled."""

import importlib
import os

import app.config as config
import app.tools.registry as registry_module


def _registry(enabled):
    os.environ["RAZAAI_SELFOPS"] = "1" if enabled else "0"
    importlib.reload(config)
    importlib.reload(registry_module)
    return registry_module.ToolRegistry()


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.6 Self-Ops Lock")
    print("=" * 78)

    locked = _registry(False)
    assert locked.selfops_enabled is False

    blocked = [m["name"] for m in locked.list_tools() if locked.is_self_modifying(m["name"])]
    for name in ("apply_self_patch", "promote_self_improvement", "run_model_training",
                 "promote_model_candidate", "rollback_model_candidate", "add_model_training_example"):
        assert name in blocked, name
    for name in ("audit_project", "search_project_code", "get_operational_health",
                 "self_improvement_status", "model_training_status"):
        assert name not in blocked, name
    print(f"[PASS] {len(blocked)} self-modifying tools identified by risk class; read-only self-ops untouched")

    exposed = {d["function"]["name"] for d in locked.get_definitions()}
    assert not (exposed & set(blocked)), exposed & set(blocked)
    assert "audit_project" in exposed
    print("[PASS] locked build never shows self-modifying tool schemas to the model")

    result = locked.execute("apply_self_patch", {"patch_id": "x"})
    assert not result.success and "disabled on this build" in (result.error or "")
    result = locked.execute("run_model_training", {})
    assert not result.success and "RAZAAI_SELFOPS" in (result.error or "")
    print("[PASS] direct execution of self-modifying tools is refused with a clear reason")

    unlocked = _registry(True)
    assert unlocked.selfops_enabled is True
    unlocked_exposed = {d["function"]["name"] for d in unlocked.get_definitions()}
    # Apply_self_patch is additionally model_exposed=False by design;
    # the lock must not change that, but model-exposed self-modifying tools return.
    assert "apply_self_patch" not in unlocked_exposed
    assert unlocked_exposed & set(blocked), "some self-modifying tools should be model-exposed when unlocked"
    assert unlocked.execute("self_improvement_status", {}).success
    print("[PASS] RAZAAI_SELFOPS=1 restores the workstation behaviour without widening Step 12.3 hiding")

    # Restore default for any test that follows in the same interpreter.
    _registry(False)

    from pathlib import Path
    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "_SELFOPS_DISABLED_MESSAGE" in agent
    assert "if not self.tools.selfops_enabled:" in agent
    assert agent.count("if not self.tools.selfops_enabled:") >= 2
    print("[PASS] /improve and /improve auto are gated at the agent entry points")

    print("=" * 78)
    print("STEP 20.8.6 SELF-OPS LOCK PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
