"""RazaAI persistent memory store."""

from pathlib import Path
import tempfile

from app.memory import MemoryManager, MemoryStore


def main():
    print("=" * 64)
    print("RazaAI Step 17.0 Persistent Memory")
    print("=" * 64)

    with tempfile.TemporaryDirectory() as temp:
        store = MemoryStore(Path(temp))
        manager = MemoryManager(store)

        first = manager.remember_explicit("my name is Brad Heffernan")
        assert first.kind == "fact"
        assert first.key == "user.name"
        assert first.value == "Brad Heffernan"

        reopened = MemoryManager(MemoryStore(Path(temp)))
        matches = reopened.search("what is my name", top_k=3)
        assert matches
        assert matches[0][1].value == "Brad Heffernan"
        print("[PASS] user fact survives a new MemoryManager instance")

        second = reopened.remember_explicit("my name is Bradley")
        assert second.value == "Bradley"

        all_records = reopened.store.records(include_inactive=True)
        old = next(item for item in all_records if item.memory_id == first.memory_id)
        assert old.state == "superseded"
        assert second.supersedes == first.memory_id
        print("[PASS] changed user fact supersedes prior value with provenance")

        forgotten = reopened.forget("Bradley")
        assert len(forgotten) == 1
        assert not reopened.search("what is my name")
        print("[PASS] explicit forget removes memory from active retrieval")

        transient = reopened.observe_user_turn(
            "my firewall is unreachable",
            domain="networking",
        )
        assert transient is None
        print("[PASS] transient outage state is not auto-promoted to durable personal memory")

        reopened.remember_explicit("my editor is vim")
        reopened.remember_explicit("my role is systems engineer")
        all_forgotten = reopened.forget("all memories")
        assert len(all_forgotten) >= 2
        assert not reopened.store.records()
        print("[PASS] explicit forget-all removes every active memory")

        try:
            reopened.remember_explicit("my password is Hunter2")
        except ValueError as exc:
            assert "Sensitive" in str(exc)
        else:
            raise AssertionError("secret was persisted")
        print("[PASS] credentials/secrets are blocked from persistent memory")

        mode = (Path(temp) / "memories.json").stat().st_mode & 0o777
        assert mode == 0o600
        print("[PASS] memory store is written with user-only permissions")

    print()
    print("=" * 64)
    print("STEP 17.0 PERSISTENT MEMORY PASSED")
    print("=" * 64)


if __name__ == "__main__":
    main()
