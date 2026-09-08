"""RazaAI polished instruction-guide documents."""

from pathlib import Path
import tempfile

from pypdf import PdfReader

from app.documents import DocumentEngine, DocumentModel, DocumentSection, KeyValueItem
from app.tools.documents import DOCUMENT_TEMPLATES, CREATE_DOCUMENT_DEFINITION


def main():
    print("=" * 68)
    print("RazaAI Step 17.8 Polished Instruction Guides")
    print("=" * 68)

    assert "instruction_guide" in DOCUMENT_TEMPLATES
    enum = CREATE_DOCUMENT_DEFINITION["function"]["parameters"]["properties"]["template"]["enum"]
    assert "instruction_guide" in enum
    print("[PASS] instruction_guide is a first-class document template")

    model = DocumentModel(
        title="Connecting to Example WiFi",
        subtitle="A simple guide for staff",
        style="guide",
        sections=[
            DocumentSection(
                heading="What you'll need",
                key_values=[
                    KeyValueItem("Network", "Example-Staff"),
                    KeyValueItem("Username", "Your normal staff username"),
                ],
                paragraphs=["Tip: Use your current login details."],
            ),
            DocumentSection(
                heading="How to connect",
                numbered=[
                    "Open WiFi settings.",
                    "Choose **Example-Staff**.",
                    "Enter your normal staff login details.",
                ],
            ),
            DocumentSection(
                heading="If it does not connect",
                bullets=["Check the username.", "Try again with your current password."],
                paragraphs=["Important: Do not share your password with another person."],
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as temp:
        engine = DocumentEngine(project_root=Path(temp))
        result = engine.create_pdf(model, filename="guide-test")
        pdf = Path(result["path"])
        assert pdf.exists() and pdf.stat().st_size > 2500
        reader = PdfReader(str(pdf))
        assert len(reader.pages) >= 1
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "How to connect" in text
        assert "What you'll need" in text
        assert "Document ID" not in text
        print("[PASS] guide PDF uses the reader-facing layout instead of report metadata")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "use template='instruction_guide'" in agent
    assert "Do NOT paste the user's task sentence" in agent
    assert 'arguments["template"] = "instruction_guide"' in agent
    print("[PASS] agent requests structured guide content and normalizes guide template")

    print()
    print("=" * 68)
    print("STEP 17.8 POLISHED INSTRUCTION GUIDES PASSED")
    print("=" * 68)


if __name__ == "__main__":
    main()
