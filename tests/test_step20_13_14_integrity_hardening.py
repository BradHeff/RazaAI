"""Regression gate for integrity/deployment hardening."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.coding.coworker import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


def _raises(fn, needle=""):
    try:
        fn()
    except ValueError as exc:
        if needle:
            assert needle.casefold() in str(exc).casefold(), (needle, exc)
        return
    raise AssertionError("expected ValueError")


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager = WorkspaceManager(root)
        coworker = WorkspaceCoworker(client=None, manager=manager)

        # The model-facing read deliberately clips at 60k. Mutation paths must not.
        original = "0123456789abcdef\n" * 5000  # > 60k chars
        (root / "big.py").write_text(original, encoding="utf-8")
        assert manager.read_file("big.py", max_chars=60000)["clipped"] is True
        snapshot = coworker._snapshot_paths(["big.py"])
        assert snapshot["big.py"]["content"] == original
        written, errors, _ = coworker._apply_operations(
            [{"path": "big.py", "mode": "append", "content": "# appended safely"}]
        )
        assert written == ["big.py"] and not errors
        after = (root / "big.py").read_text(encoding="utf-8")
        assert len(after) > len(original) and after.startswith(original.rstrip("\n"))
        rollback = coworker._rollback_snapshot(snapshot)
        assert not rollback["failures"]
        assert (root / "big.py").read_text(encoding="utf-8") == original
        print("[PASS] >60K file snapshots, append, and rollback preserve unseen source")

        # Sensitive paths are read/write/patch protected, including new files.
        for rel in (
            ".env",
            ".env.staging",
            "credentials.json",
            "id_rsa",
            ".netrc",
            ".npmrc",
        ):
            _raises(
                lambda rel=rel: manager.write_file(rel, "SECRET=value", overwrite=True),
                "credential",
            )
        (root / "safe.txt").write_text("safe", encoding="utf-8")
        manager.write_file("safe.txt", "still safe", overwrite=True)
        (root / ".env").write_text("SECRET=value", encoding="utf-8")
        _raises(lambda: manager.patch_file(".env", "value", "changed"), "credential")
        print(
            "[PASS] credential-bearing workspace paths cannot be created, overwritten, or patched"
        )

        # Generic read-only Git execution must not expose branch mutations.
        _raises(
            lambda: manager._validate_command(["git", "branch", "model-created"]),
            "read-only git",
        )
        assert manager._validate_command(["git", "status", "--short"])[1] == "status"
        print("[PASS] model-exposed Git runner cannot create/delete/rename branches")

    service = Path("deploy/razaai-server.service").read_text(encoding="utf-8")
    env = Path("deploy/razaai-server.env").read_text(encoding="utf-8")
    jetson = Path("deploy/jetson-headless.sh").read_text(encoding="utf-8")
    doctor = Path("app/doctor.py").read_text(encoding="utf-8")
    assert "@PROJECT_ROOT@/@LAUNCHER@ web" in service
    assert "RAZAAI_SERVER_HOST=127.0.0.1" in env
    assert "change-me" not in env
    assert "razaai-8g.conf" in jetson
    assert "APPROVED_CODE_MODEL" in doctor
    print("[PASS] clean deployment uses one .venv and the approved coder model everywhere")

    assert not Path("app/tools/app").exists()
    from scripts.package_release import public_files
    names = {str(p.relative_to(Path.cwd())) for p in public_files()}
    assert ".raza-url-token" not in names
    assert not any(n.startswith(("data/", "logs/", ".git/")) for n in names)
    print(
        "[PASS] duplicate nested tools tree removed; release script excludes local secret/state paths"
    )

    from app.config import APP_VERSION, version_tuple

    assert version_tuple(APP_VERSION) >= (20, 13, 14)
    print("=" * 78)
    print("STEP 20.13.14 INTEGRITY HARDENING PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
