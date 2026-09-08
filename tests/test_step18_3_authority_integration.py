from pathlib import Path
from app.interaction import InteractionRouter
from app.agent.edge_router import EdgeIntentRouter


def main():
    print("="*72)
    print("RazaAI Step 18.3 Authority Integration")
    print("="*72)
    registry=Path("app/tools/registry.py").read_text(encoding="utf-8")
    tools=Path("app/tools/improvement.py").read_text(encoding="utf-8")
    edge=Path("app/agent/edge_router.py").read_text(encoding="utf-8")
    agent=Path("app/agent/agent.py").read_text(encoding="utf-8")

    for name in (
        "start_self_improvement","stage_improvement_patch","verify_self_improvement",
        "prepare_model_training","add_model_training_example","stage_model_candidate",
        "verify_model_candidate","search_project_context",
    ):
        assert f'"{name}"' in registry
    print("[PASS] autonomous candidate-building tools are registered")

    for name in (
        "promote_self_improvement","rollback_self_improvement",
        "run_model_training","promote_model_candidate","rollback_model_candidate",
    ):
        assert name in tools
    for marker in (
        'PROMOTE_SELF_IMPROVEMENT_METADATA=_meta("promote_self_improvement","selfops","source_write",900,False)',
        'ROLLBACK_SELF_IMPROVEMENT_METADATA=_meta("rollback_self_improvement","selfops","source_write",300,False)',
        'RUN_MODEL_TRAINING_METADATA=_meta("run_model_training","model_training","gpu_training",86400,False)',
        'PROMOTE_MODEL_CANDIDATE_METADATA=_meta("promote_model_candidate","model_lifecycle","active_model_replace",600,False)',
        'ROLLBACK_MODEL_CANDIDATE_METADATA=_meta("rollback_model_candidate","model_lifecycle","active_model_replace",600,False)',
    ):
        assert marker in tools
    print("[PASS] production/model-changing operations remain hidden from model")

    edge_router=EdgeIntentRouter(manager=object())
    improve_route=edge_router.route("Approve IMPROVE-20260821-123456-123456")
    assert improve_route.kind=="deterministic_tool"
    assert improve_route.tool=="promote_self_improvement"
    assert improve_route.arguments["improvement_id"]=="IMPROVE-20260821-123456-123456"

    rollback_route=edge_router.route("Rollback IMPROVE-20260821-123456-123456")
    assert rollback_route.tool=="rollback_self_improvement"

    training_route=edge_router.route("Run TRAIN-20260821-123456-123456")
    assert training_route.tool=="run_model_training"

    model_route=edge_router.route("Promote MODEL-20260821-123456-123456")
    assert model_route.tool=="promote_model_candidate"

    model_rollback=edge_router.route("Rollback MODEL-20260821-123456-123456")
    assert model_rollback.tool=="rollback_model_candidate"
    print("[PASS] production/model changes require deterministic ID-based user approval")

    assert "start_self_improvement" in agent
    assert "Never replace the active tag yourself" in agent
    assert "CuratedProjectContext" in agent
    assert "project_context_evidence" in agent
    print("[PASS] agent understands sandbox/training/model/context contracts")

    context=InteractionRouter().classify("improve yourself at FortiGate IPsec troubleshooting")
    assert context.mode=="action" and context.allow_tools is True
    training=InteractionRouter().classify("retrain yourself to improve concise technical replies")
    assert training.mode=="action" and training.allow_tools is True
    print("[PASS] improvement and retraining requests enter actionable tool mode")

    print("\n"+"="*72)
    print("STEP 18.3 AUTHORITY INTEGRATION PASSED")
    print("="*72)


if __name__=="__main__":
    main()
