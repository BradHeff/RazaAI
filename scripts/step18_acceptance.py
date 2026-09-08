"""RazaAI Controlled Self-Improvement Acceptance."""
import subprocess, sys

MODULES=(
    "tests.test_step12_2_guarded_self_repair",
    "tests.test_step12_3_self_improvement",
    "tests.test_step15_0_1_capability_hardening",
    "tests.test_step17_10_staff_rollout_documents",
    "tests.test_step18_0_controlled_self_improvement",
    "tests.test_step18_1_training_pipeline",
    "tests.test_step18_2_model_lifecycle",
    "tests.test_step18_3_authority_integration",
)

def main():
    print("="*78)
    print("RazaAI Step 18.4 Controlled Self-Improvement Acceptance")
    print("="*78)
    failed=[]
    for module in MODULES:
        print(f"\nRunning {module} ...")
        result=subprocess.run([sys.executable,"-m",module])
        if result.returncode: failed.append(module)
    print("\n"+"="*78)
    if failed:
        print("STEP 18 ACCEPTANCE FAILED")
        for module in failed: print(f"[FAIL] {module}")
        print("="*78); raise SystemExit(1)
    print("STEP 18.4 END-TO-END ACCEPTANCE PASSED")
    print("STEP 18 COMPLETE")
    print("="*78)

if __name__=="__main__": main()
