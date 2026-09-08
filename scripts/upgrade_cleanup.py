"""Remove obsolete source paths left behind by in-place RazaAI upgrades."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import BASE_DIR


OBSOLETE_PATHS = (
    "app/tools/app",  # Retired duplicate tool source tree
)


def cleanup_obsolete_paths(project_root: Path | str = BASE_DIR) -> list[str]:
    root = Path(project_root).expanduser().resolve()
    removed: list[str] = []
    for relative in OBSOLETE_PATHS:
        target = root / relative
        # Keep cleanup authority pinned to the project root even if a stale path
        # was replaced by a symlink.
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
        removed.append(relative)
    return removed


def main() -> int:
    removed = cleanup_obsolete_paths()
    if removed:
        for path in removed:
            print(f"[CLEAN] removed obsolete upgrade path: {path}")
    else:
        print("[CLEAN] no obsolete upgrade paths found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
