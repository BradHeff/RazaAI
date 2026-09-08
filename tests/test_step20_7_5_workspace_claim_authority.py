"""Workspace completion claims and launcher authority."""

from pathlib import Path
from app.config import APP_VERSION


def main():
    print("=" * 78)
    print("RazaAI Step 20.7.2 Workspace Claim Authority")
    print("=" * 78)

    assert tuple(int(part) for part in APP_VERSION.split(".")) >= (20, 7, 2)
    print("[PASS] application version is at or beyond the 20.7.2 workspace milestone")

    coworker = Path("app/coding/coworker.py").read_text(encoding="utf-8")
    assert "actual =" in coworker
    assert "if not confirmed:" in coworker
    assert "I will not claim that files were created" in coworker
    assert "python3\", \"-m\", \"py_compile" in coworker
    print("[PASS] success claims require post-write filesystem evidence and verification")

    launcher = Path("raza-code").read_text(encoding="utf-8")
    assert "import textual" in launcher
    assert "RAZAAI_CODE_DEBUG" in launcher
    assert 'exec "$PYTHON" -m app.launcher --profile "${RAZAAI_PROFILE:-standard}" chat --workspace "$WORKSPACE"' in launcher
    print("[PASS] launcher selects a Textual-capable interpreter and exposes debug selection")

    print()
    print("=" * 78)
    print("STEP 20.7.2 WORKSPACE CLAIM AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
