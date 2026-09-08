"""RazaAI terminal UI + coding coworker acceptance."""

import subprocess
import sys


MODULES = (
    "tests.test_step20_0_tui_architecture",
    "tests.test_step20_1_prompt_focus",
    "tests.test_step20_3_capability_performance",
    "tests.test_step20_4_streaming_context",
    "tests.test_step20_4_1_context_retry",
    "tests.test_step20_4_2_tool_schema_budget",
    "tests.test_step20_5_reasoning_memory_commands",
    "tests.test_step20_5_1_improve_orchestration",
    "tests.test_step20_5_2_token_status",
    "tests.test_step20_5_3_integration_hotfix",
    "tests.test_step20_5_4_improve_tui_runtime",
    "tests.test_step20_5_5_legacy_regression_alignment",
    "tests.test_step20_5_6_deterministic_improvement",
    "tests.test_step20_5_7_protected_improvement_routing",
    "tests.test_step20_5_8_no_change_completion",
    "tests.test_step20_6_0_improvement_discovery",
    "tests.test_step20_6_1_discovery_commands",
    "tests.test_step20_7_0_feedback_loop",
    "tests.test_step20_7_1_feedback_commands_version",
    "tests.test_step20_7_2_coding_workspace",
    "tests.test_step20_7_3_raza_code_launcher",
    "tests.test_step20_7_4_workspace_coworker_execution",
    "tests.test_step20_7_5_workspace_claim_authority",
    "tests.test_step20_8_0_full_coding_workflow",
    "tests.test_step20_8_1_project_checks_git",
    "tests.test_step20_8_2_version_acceptance",
    "tests.test_step20_8_3_exact_patch_preservation",
    "tests.test_step20_8_4_repair_truncation_rollback",
    "tests.test_step20_8_5_question_vs_mutation",
    "tests.test_step20_8_6_context_window_authority",
    "tests.test_step20_8_7_project_interpreter",
    "tests.test_step20_8_8_selfops_lock",
    "tests.test_step20_8_9_file_search_ranking",
    "tests.test_step20_8_10_advice_evidence_routing",
    "tests.test_step20_8_11_procedure_guidance_memory",
    "tests.test_step20_8_12_identity_origin",
    "tests.test_step20_8_13_hermetic_eval_state",
    "tests.test_step20_8_14_thin_evidence_knowledge",
    "tests.test_step20_9_0_service_mode",
    "tests.test_step20_9_3_local_facts",
    "tests.test_step20_10_0_approve_undo_checkpoint_sandbox",
    "tests.test_step20_11_0_exploration_planning",
    "tests.test_step20_12_0_coding_eval",
    "tests.test_step20_12_1_coder_model",
    "tests.test_step20_13_0_offline_reliability",
    "tests.test_step20_13_14_integrity_hardening",
    "tests.test_step20_13_15_support_context",
    "tests.test_step20_13_16_support_state",
    "tests.test_step20_14_0_agent_decomposition",
    "tests.test_step20_14_1_transaction_durability",
    "tests.test_step20_14_2_verification_isolation",
    "tests.test_step20_14_3_runtime_hardening",
    "tests.test_step20_14_4_acceptance_repairs",
    "tests.test_step20_14_5_bwrap_runtime_resolution",
    "tests.test_step20_14_6_bwrap_exec_boundary",
    "tests.test_step20_15_1_4_coding_target_authority",
    "tests.test_step20_15_1_5_identity_and_coding_gaps",
    "tests.test_step20_15_1_6_personality_provenance",
    "tests.test_step20_15_1_7_reasoning_context_isolation",
    "tests.test_step20_15_1_8_cortana_personality",
    "tests.test_step20_15_1_9_conversation_coherence",
)

REQUIRED_VERSION = (20, 15, 1)


def main():
    from tests.knowledge_fixture import indexed
    fixture = indexed()
    print("=" * 76)
    print("RazaAI Step 20 Full Coding Agent Acceptance")
    print("=" * 76)
    failures = []

    for module in MODULES:
        print(f"\nRunning {module} ...")
        result = subprocess.run([sys.executable, "-m", module])
        if result.returncode:
            failures.append(module)

    fixture.cleanup()
    print()
    print("=" * 76)
    if failures:
        print("STEP 20 ACCEPTANCE FAILED")
        for module in failures:
            print(f"[FAIL] {module}")
        print("=" * 76)
        raise SystemExit(1)

    from app.config import APP_VERSION, version_tuple
    if version_tuple(APP_VERSION) < REQUIRED_VERSION:
        required = ".".join(str(v) for v in REQUIRED_VERSION)
        print(f"[FAIL] APP_VERSION={APP_VERSION!r}; this suite requires >= {required}")
        raise SystemExit(1)

    print(f"STEP 20 ACCEPTANCE PASSED (APP_VERSION {APP_VERSION})")
    print("STEP 20 COMPLETE")
    print("=" * 76)


if __name__ == "__main__":
    main()
