"""Capture the *accepted deployment venv* as an exact runtime lock."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.config import BASE_DIR


def _payload():
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--local"],
        text=True, capture_output=True, timeout=60,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr.strip() or "pip freeze failed")
    lines = []
    for line in proc.stdout.splitlines():
        value = line.strip()
        if not value or value.startswith("-e ") or " @ file:" in value:
            continue
        lines.append(value)
    if not lines:
        raise SystemExit("Refusing to write an empty runtime lock.")
    header = (
        "# RazaAI accepted-runtime lock. Generated on the deployment device.\n"
        f"# Python: {sys.version.split()[0]}\n"
        "# Regenerate only after the full device acceptance suite passes.\n"
    )
    return header + "\n".join(sorted(set(lines), key=str.casefold)) + "\n"


def main(argv=None):
    explicit = bool(argv)
    if explicit:
        targets = [Path(argv[0]).expanduser()]
    else:
        persistent = Path(
            os.getenv(
                "RAZAAI_RUNTIME_LOCK",
                str(Path.home() / ".local" / "share" / "razaai" / "requirements.lock"),
            )
        ).expanduser()
        targets = [persistent, BASE_DIR / "requirements.lock"]

    payload = _payload()
    written = []
    for target in dict.fromkeys(targets):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        written.append(target)
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
