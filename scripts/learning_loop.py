"""Promote validated incidents, update feedback and refresh the knowledge index."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from app.incidents import IncidentStore, KnowledgePromotionEngine
    from app.incidents.feedback import KnowledgeFeedbackEngine

    store = IncidentStore()
    promotions = KnowledgePromotionEngine(store)

    print("[learning-loop] 1/3 evaluating promotions")
    promoted = []
    failed = False
    try:
        promoted = promotions.promote_eligible()
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"[learning-loop] promotion error: {exc}")
    for result in promoted:
        print(f"[learning-loop] promoted: {result.knowledge_path} ({result.status})")

    print("[learning-loop] 2/3 refreshing promoted-knowledge feedback")
    try:
        feedback = KnowledgeFeedbackEngine(store)
        results = feedback.refresh_all()
        for item in results:
            print(
                f"[learning-loop] feedback {item.knowledge_status.upper()}: "
                f"{item.fingerprint} score={item.confidence_score:.2f}"
            )
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"[learning-loop] feedback error: {exc}")

    print("[learning-loop] 3/3 re-ingesting knowledge store")
    engine = None
    try:
        from app.knowledge.engine import KnowledgeEngine

        engine = KnowledgeEngine()
        stats = engine.ingest_all(force=False)
        print(f"[learning-loop] ingest complete: {stats}")
    except ImportError:
        failed = True
        print(
            "[learning-loop] embedding stack unavailable on this device; "
            "run on the workstation: python3 -m scripts.ingest_knowledge"
        )
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"[learning-loop] ingest error: {exc}; run scripts/ingest_knowledge")

    finally:
        if engine is not None:
            engine.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
