"""RazaAI Curated Markdown Knowledge/Branding Acceptance."""
import subprocess,sys

MODULES=(
    "tests.test_step19_0_curated_markdown_context",
    "tests.test_step19_1_document_theme_integration",
    "tests.test_step19_3_mui_branding",
    "tests.test_step17_10_staff_rollout_documents",
)

def main():
    print("="*78)
    print("RazaAI Step 19.2 Curated Markdown Knowledge & Branding Acceptance")
    print("="*78)
    failed=[]
    for module in MODULES:
        print(f"\nRunning {module} ...")
        result=subprocess.run([sys.executable,"-m",module])
        if result.returncode: failed.append(module)
    print("\n"+"="*78)
    if failed:
        print("STEP 19 ACCEPTANCE FAILED")
        for module in failed: print(f"[FAIL] {module}")
        print("="*78); raise SystemExit(1)
    print("STEP 19.2 ACCEPTANCE PASSED")
    print("STEP 19 COMPLETE")
    print("="*78)

if __name__=="__main__": main()
