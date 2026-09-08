"""RazaAI conservative learning."""

from pathlib import Path
import tempfile

from app.memory import MemoryManager, MemoryStore


def main():
    print("=" * 64)
    print("RazaAI Step 17.1 Persistent Learning")
    print("=" * 64)

    with tempfile.TemporaryDirectory() as temp:
        manager = MemoryManager(MemoryStore(Path(temp)))

        manager.observe_user_turn(
            "I prefer concise technical answers",
            domain="general",
        )
        matches = manager.search(
            "how do I prefer answers",
            domain="general",
            top_k=5,
        )
        assert any(
            record.kind == "preference"
            and "concise technical answers" in record.value
            for _, record in matches
        )
        print("[PASS] direct user preference is retrievable")

        # First observed incident: historical observation only.
        manager.observe_user_turn(
            "it was policy",
            domain="networking",
            previous_domain="networking",
            session_id="session-a",
        )
        manager.observe_user_turn(
            "it's working now",
            domain="networking",
            previous_domain="networking",
            session_id="session-a",
        )

        # Repeating it in the same session must not manufacture learning.
        manager.observe_user_turn(
            "it was policy",
            domain="networking",
            previous_domain="networking",
            session_id="session-a",
        )
        manager.observe_user_turn(
            "it's working now",
            domain="networking",
            previous_domain="networking",
            session_id="session-a",
        )

        records = manager.store.records()
        assert any(item.kind == "technical_observation" for item in records)
        assert not any(item.kind == "technical_pattern" for item in records)
        print("[PASS] repeated wording in one session does not become a durable pattern")

        # A second distinct RazaAI session can provide the second validation.
        manager.observe_user_turn(
            "it was policy",
            domain="networking",
            previous_domain="networking",
            session_id="session-b",
        )
        manager.observe_user_turn(
            "it's working now",
            domain="networking",
            previous_domain="networking",
            session_id="session-b",
        )

        records = manager.store.records()
        patterns = [
            item for item in records
            if item.kind == "technical_pattern"
        ]
        assert patterns
        assert patterns[0].confidence >= 0.85
        assert patterns[0].source == "memory_promotion"
        assert len(patterns[0].provenance["validation_sessions"]) >= 2
        print("[PASS] distinct-session validated outcomes can promote to low-authority pattern")

        guidance = manager.guidance(
            "network policy issue",
            domain="networking",
        )
        assert "never proves a current root cause" in guidance
        assert "LEARNED PATTERN" in guidance
        print("[PASS] learned pattern is explicitly subordinate to live evidence")

        # Same technical key with contradictory value must enter review.
        manager.store.upsert(
            kind="technical_pattern",
            key="technical.networking.pattern.routing",
            value="policy",
            confidence=0.85,
            source="memory_promotion",
            domain="networking",
        )
        conflict = manager.store.upsert(
            kind="technical_pattern",
            key="technical.networking.pattern.routing",
            value="route",
            confidence=0.85,
            source="memory_promotion",
            domain="networking",
        )
        assert conflict.state == "review"
        matching = [
            item for item in manager.store.records(include_inactive=True)
            if item.key == "technical.networking.pattern.routing"
        ]
        assert all(item.state == "review" for item in matching)
        print("[PASS] contradictory technical learning moves to review")

    print()
    print("=" * 64)
    print("STEP 17.1 PERSISTENT LEARNING PASSED")
    print("=" * 64)


if __name__ == "__main__":
    main()
