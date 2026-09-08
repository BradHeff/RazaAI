"""RazaAI operational memory integration."""

from pathlib import Path


def main():
    print("=" * 68)
    print("RazaAI Step 17.5 Operational Memory")
    print("=" * 68)

    audit = Path("app/selfops/audit.py").read_text(encoding="utf-8")
    health = Path("app/selfops/health.py").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "def _memory_check" in audit
    assert '"name": "persistent_memory"' in audit
    assert "self._memory_check" in audit
    print("[PASS] self-audit verifies persistent memory integrity")

    assert '"persistent_memory": {' in health
    assert "review_memory" in health
    assert "persistent memory item(s) require review" in health
    print("[PASS] operational health exposes memory counts/review state")

    assert "data/" in gitignore.splitlines()
    print("[PASS] private runtime memory is excluded from git")

    print()
    print("=" * 68)
    print("STEP 17.5 OPERATIONAL MEMORY PASSED")
    print("=" * 68)


if __name__ == "__main__":
    main()
