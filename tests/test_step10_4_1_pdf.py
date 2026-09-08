import tempfile
from pathlib import Path

from pypdf import PdfReader

from app.documents import (
    DocumentEngine,
    DocumentModel,
    DocumentSection,
    DocumentTable,
    KeyValueItem,
)


def build_model():
    return DocumentModel(
        title="Clare Wi-Fi Incident Report",
        subtitle="Example-Staff Connectivity Failure",
        organisation="Example School",
        author="RazaAI",
        document_id="RAZA-INC-2026-0001",
        status="Final",
        classification="Internal",
        sections=[
            DocumentSection(
                heading="Incident Summary",
                paragraphs=[
                    (
                        "Staff wireless authentication succeeded, "
                        "but clients could not obtain usable "
                        "network connectivity."
                    )
                ],
                key_values=[
                    KeyValueItem(
                        "Site",
                        "Clare",
                    ),
                    KeyValueItem(
                        "SSID",
                        "Example-Staff",
                    ),
                ],
            ),
            DocumentSection(
                heading="Root Cause",
                paragraphs=[
                    (
                        "The WLAN Access VLAN was configured "
                        "as VLAN 30 instead of VLAN 80."
                    )
                ],
            ),
            DocumentSection(
                heading="Resolution",
                numbered=[
                    "Changed the WLAN Access VLAN from 30 to 80.",
                    "Reconnected the client.",
                ],
            ),
            DocumentSection(
                heading="Validation",
                bullets=[
                    "Client received an IP address.",
                    "Gateway ping succeeded.",
                    "Internet connectivity was restored.",
                ],
            ),
            DocumentSection(
                heading="Evidence",
                tables=[
                    DocumentTable(
                        headers=[
                            "Check",
                            "Result",
                        ],
                        rows=[
                            [
                                "NPS authentication",
                                "Passed",
                            ],
                            [
                                "Access VLAN",
                                "Corrected to 80",
                            ],
                            [
                                "Internet",
                                "Passed",
                            ],
                        ],
                    )
                ],
            ),
        ],
    )


def main():
    print()
    print("========================================")
    print("RazaAI Step 10.4.1 PDF Renderer Test")
    print("========================================")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        engine = DocumentEngine(
            project_root=root
        )

        model = build_model()

        result = engine.create_pdf(
            model,
            filename="../../unsafe Clare PDF",
        )

        path = Path(
            result["path"]
        )

        if not path.exists():
            raise AssertionError(
                "PDF was not created"
            )

        print("[PASS] PDF generated")

        if (
            path.parent
            != root / "output" / "documents"
        ):
            raise AssertionError(
                "PDF escaped safe output directory"
            )

        print(
            "[PASS] PDF constrained to "
            "output/documents"
        )

        reader = PdfReader(
            str(path)
        )

        if len(reader.pages) < 1:
            raise AssertionError(
                "PDF contains no pages"
            )

        print("[PASS] PDF contains pages")

        text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

        for required in [
            "Clare Wi-Fi Incident Report",
            "Incident Summary",
            "Root Cause",
            "Resolution",
            "Validation",
            "Evidence",
        ]:
            if required not in text:
                raise AssertionError(
                    f"Missing PDF text: {required}"
                )

        print("[PASS] PDF text verified")

        both = engine.create_both(
            model,
            filename="Example_WiFi_Incident_Report",
        )

        docx_path = Path(
            both["docx"]["path"]
        )

        pdf_path = Path(
            both["pdf"]["path"]
        )

        if not docx_path.exists():
            raise AssertionError(
                "DOCX from create_both missing"
            )

        if not pdf_path.exists():
            raise AssertionError(
                "PDF from create_both missing"
            )

        print("[PASS] DOCX + PDF generated from same model")

        print()
        print(f"Generated PDF: {path}")
        print()

    print("========================================")
    print("STEP 10.4.1 PDF RENDERER PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
