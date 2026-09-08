"""RazaAI Web Answer Grounding."""

from app.tools.result import ToolResult
from app.tools.web_grounding import (
    validate_web_answer,
    grounded_web_fallback,
)


def search_result():
    return ToolResult(
        True,
        "search_web",
        result={
            "query": "latest FortiOS release",
            "result_count": 2,
            "results": [
                {
                    "source_id": "S1",
                    "citation": "[S1]",
                    "title": "Fortinet Release Notes",
                    "url": "https://docs.fortinet.com/",
                    "snippet": "FortiOS 8.0 release information.",
                    "authority": "preferred",
                },
                {
                    "source_id": "S2",
                    "citation": "[S2]",
                    "title": "Community post",
                    "url": "https://example.com/",
                    "snippet": "Discussion of FortiOS.",
                    "authority": "normal",
                },
            ],
        },
    )


def main():
    print("=" * 60)
    print("RazaAI Step 16.6 Web Answer Grounding")
    print("=" * 60)

    result = search_result()

    valid, reason = validate_web_answer(
        "search_web",
        result,
        "The source reports FortiOS 8.0. [S1]",
    )
    assert valid and not reason
    print("[PASS] returned citation IDs validate")

    valid, reason = validate_web_answer(
        "search_web",
        result,
        "The source reports FortiOS 8.0.",
    )
    assert not valid
    assert "omitted" in reason
    print("[PASS] uncited web answer is rejected")

    valid, reason = validate_web_answer(
        "search_web",
        result,
        "The source reports FortiOS 8.0. [S9]",
    )
    assert not valid
    assert "not returned" in reason
    print("[PASS] invented citation ID is rejected")

    fallback = grounded_web_fallback(
        "search_web",
        result,
    )
    assert "Fortinet Release Notes" in fallback
    assert "[S1]" in fallback
    assert "Community post" not in fallback
    print("[PASS] fallback prefers authoritative returned sources")

    page = ToolResult(
        True,
        "fetch_web_page",
        result={
            "source_id": "W1",
            "citation": "[W1]",
            "title": "Vendor Page",
            "url": "https://vendor.example/page",
            "text": "Supported page text.",
        },
    )

    valid, _ = validate_web_answer(
        "fetch_web_page",
        page,
        "The page says this. [W1]",
    )
    assert valid

    valid, _ = validate_web_answer(
        "fetch_web_page",
        page,
        "The page says this. [S1]",
    )
    assert not valid
    print("[PASS] page answers must cite the returned webpage source ID")

    print()
    print("=" * 60)
    print("STEP 16.6 WEB ANSWER GROUNDING PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
