"""RazaAI instruction-guide content completeness."""

from pathlib import Path

from pypdf import PdfReader

from app.documents.guide_builder import (
    normalize_instruction_guide_arguments,
    is_substantive_instruction_guide,
)
from app.tools.documents import create_document


WIFI_REQUEST = (
    "create a pdf outlining how to connect to staff wifi, the staff wifi is "
    "eap so it takes username and password staff use to login to computer. "
    "the username is beginning of an email (without @example.edu) "
    "the SSID name is Example-Staff. Make sure the pdf is easy to understand "
    "by non technical people."
)


def main():
    print("=" * 72)
    print("RazaAI Step 17.9 Instruction Guide Content Completeness")
    print("=" * 72)

    bad_model_args = {
        "title": "How to Connect to Staff WiFi",
        "format": "pdf",
        "template": "instruction_guide",
        "subtitle": "Connecting to Staff WiFi",
        "sections": [
            {
                "heading": "Overview",
                "paragraphs": [
                    "To connect to the Example-Staff WiFi network, follow these steps."
                ],
            }
        ],
        "incident": {
            "resolution": "Enter the correct username and password",
            "root_cause": "Incorrect WiFi credentials",
            "summary": "Connecting to Example-Staff WiFi",
            "symptoms": ["WiFi not working"],
            "validation": ["internet access works"],
        },
    }

    agent_source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "normalize_instruction_guide_arguments(" in agent_source
    assert "arguments = normalize_instruction_guide_arguments" in agent_source
    print("[PASS] agent normalizes instruction-guide content before tool execution")

    normalized = normalize_instruction_guide_arguments(
        bad_model_args,
        WIFI_REQUEST,
    )

    assert normalized["template"] == "instruction_guide"
    assert normalized["style"] == "guide"
    assert "incident" not in normalized
    assert normalized["title"] == "Connecting to Example-Staff Wi-Fi"
    assert is_substantive_instruction_guide(normalized["sections"])
    print("[PASS] sparse incident-shaped model payload is rebuilt before execution")

    headings = [section["heading"] for section in normalized["sections"]]
    for expected in (
        "The short version",
        "Before you start",
        "Windows laptop",
        "Mac",
        "iPhone or iPad",
        "Android phone or tablet",
        "If it does not connect",
    ):
        assert expected in headings
    print("[PASS] rebuilt Wi-Fi guide contains complete reader-facing sections")

    joined = repr(normalized["sections"])
    assert "Example-Staff" in joined
    assert "@example.edu" in joined
    assert "school computer password" in joined
    assert "Incorrect WiFi credentials" not in joined
    assert "root_cause" not in joined
    print("[PASS] user-supplied facts are preserved and invented incident facts removed")

    output = create_document(**normalized, filename="step17_9_wifi_guide_test")
    path = Path(output["path"] if isinstance(output, dict) and "path" in output else output)
    assert path.exists()

    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(str(path)).pages
    )
    assert "Example-Staff" in text
    assert "Windows laptop" in text
    assert "Android phone or tablet" in text
    assert "If it does not connect" in text
    assert "never send or tell another person your school password" in text.lower()
    print("[PASS] rendered PDF contains the complete guide, not a one-paragraph shell")

    try:
        create_document(
            title="Sparse Generic Guide",
            format="pdf",
            template="instruction_guide",
            sections=[
                {
                    "heading": "Overview",
                    "paragraphs": ["One short paragraph."],
                }
            ],
            filename="step17_9_sparse_should_fail",
        )
    except ValueError as exc:
        assert "instruction_guide content is incomplete" in str(exc)
    else:
        raise AssertionError("Sparse guide was allowed to render")
    print("[PASS] unsupported sparse guides are rejected before a junk file is written")

    path.unlink(missing_ok=True)

    print()
    print("=" * 72)
    print("STEP 17.9 INSTRUCTION GUIDE CONTENT COMPLETENESS PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
