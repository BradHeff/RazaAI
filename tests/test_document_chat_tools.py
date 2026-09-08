from pathlib import Path

from app.tools.documents import (
    create_document,
    list_document_templates,
)


def main():
    print()
    print("========================================")
    print("RazaAI Document Chat Tool Test")
    print("========================================")
    print()

    templates = list_document_templates()
    ids = {
        item["id"]
        for item in templates["templates"]
    }

    assert "general_document" in ids
    assert "incident_report" in ids
    print("[PASS] document templates available")

    result = create_document(
        title="RazaAI Tool Test",
        format="both",
        template="general_document",
        filename="RazaAI_Tool_Test",
        sections=[
            {
                "heading": "Summary",
                "paragraphs": [
                    "Document tool integration is working."
                ],
            }
        ],
    )

    docx = Path(result["docx"]["path"])
    pdf = Path(result["pdf"]["path"])

    assert docx.exists()
    assert pdf.exists()

    print("[PASS] create_document generated DOCX")
    print("[PASS] create_document generated PDF")
    print()
    print(docx)
    print(pdf)
    print()
    print("========================================")
    print("DOCUMENT CHAT TOOL TEST PASSED")
    print("========================================")


if __name__ == "__main__":
    main()
