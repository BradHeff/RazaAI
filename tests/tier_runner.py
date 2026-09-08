from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Short feedback gate used during development/refactors.
FAST = (
    "tests.test_step20_8_3_exact_patch_preservation",
    "tests.test_step20_8_5_question_vs_mutation",
    "tests.test_step20_8_6_context_window_authority",
    "tests.test_step20_10_0_approve_undo_checkpoint_sandbox",
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
    "tests.test_step20_15_1_10_identity_followup_authority",
)

# Core behavior that should pass before packaging, but is slower than FAST.
CORE = (
    "tests.test_step20_7_4_workspace_coworker_execution",
    "tests.test_step20_7_5_workspace_claim_authority",
    "tests.test_step20_8_0_full_coding_workflow",
    "tests.test_step20_8_1_project_checks_git",
    "tests.test_step20_8_4_repair_truncation_rollback",
    "tests.test_step20_8_7_project_interpreter",
    "tests.test_step20_11_0_exploration_planning",
    "tests.test_step20_12_0_coding_eval",
)

# External/runtime-library integrations. These belong on a fully provisioned
# deployment environment, not in the sub-minute edit/refactor loop.
INTEGRATION = (
    "tests.test_step10_4_documents",
    "tests.test_step10_4_1_pdf",
    "tests.test_step11_1_incident_retrieval",
    "tests.test_step11_5_knowledge_promotion",
    "tests.test_step16_0_web_safety",
    "tests.test_step16_6_web_grounding",
    "tests.test_step17_8_document_guides",
    "tests.test_step20_8_8_selfops_lock",
    "tests.test_step20_12_1_coder_model",
    "tests.test_step20_13_0_offline_reliability",
)

# Needs real Ollama / device network / system state.
DEVICE = (
    "tests.test_agent",
    "tests.test_connection",
    "tests.test_ip_agent",
    "tests.test_network_agent",
    "tests.test_step8_diagnostics",
    "tests.test_tool_request",
    "tests.test_step3_network",
)

TIERS = {"fast": FAST, "core": CORE, "integration": INTEGRATION, "device": DEVICE}


def run_tier(name: str, timeout: int = 180) -> int:
    from .knowledge_fixture import indexed
    fixture = indexed() if name != "device" else None
    modules = TIERS[name]
    print("=" * 78)
    print(f"RazaAI {name.upper()} test tier: {len(modules)} module(s)")
    print("=" * 78)
    failures = []
    for module in modules:
        started = time.monotonic()
        try:
            result = subprocess.run(
                [sys.executable, "-m", module], cwd=PROJECT_ROOT,
                text=True, capture_output=True, timeout=timeout,
            )
            code = result.returncode
            detail = result.stderr or result.stdout
        except subprocess.TimeoutExpired:
            code = 124
            detail = f"timed out after {timeout}s"
        elapsed = time.monotonic() - started
        print(f"[{'PASS' if code == 0 else 'FAIL'}] {module} ({elapsed:.1f}s)")
        if code:
            failures.append((module, "\n".join(str(detail).strip().splitlines()[-10:])))
    if fixture is not None:
        fixture.cleanup()
    if failures:
        print("=" * 78)
        for module, detail in failures:
            print(f"\n--- {module} ---\n{detail}")
        print(f"{name.upper()} TIER FAILED: {len(failures)}/{len(modules)}")
        return 1
    print("=" * 78)
    print(f"{name.upper()} TIER PASSED: {len(modules)}/{len(modules)}")
    return 0
