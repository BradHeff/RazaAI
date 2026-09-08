import tempfile
import zipfile
from pathlib import Path

from app.documents import DocumentModel, DocumentSection
from app.documents.docx_writer import DocxWriter


def main():
    print("="*72)
    print("RazaAI Step 19.1 Document Theme Integration")
    print("="*72)

    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"theme.docx"
        model=DocumentModel(
            title="Theme Test",
            subtitle="Curated branding",
            style="guide",
            organisation="Example School",
            sections=[DocumentSection(
                heading="Overview",
                paragraphs=["A themed document."],
            )],
            metadata={"theme":{
                "primary_color":"102A43",
                "accent_color":"0E7490",
                "muted_color":"52606D",
            }},
        )
        DocxWriter().write(model,path)
        assert path.exists()
        with zipfile.ZipFile(path,"r") as z:
            combined=""
            for name in z.namelist():
                if name.startswith("word/") and name.endswith(".xml"):
                    combined += z.read(name).decode("utf-8",errors="ignore")
        assert "102A43" in combined
        assert "0E7490" in combined
        print("[PASS] curated primary/accent colors reach generated DOCX XML")

    documents=Path("app/tools/documents.py").read_text(encoding="utf-8")
    pdf=Path("app/documents/pdf_writer.py").read_text(encoding="utf-8")
    agent=Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "CuratedProjectContext().document_theme()" in documents
    assert "self._apply_theme(model)" in pdf
    assert "CuratedProjectContext" in agent
    assert "project_context_evidence" in agent
    print("[PASS] document tool, PDF writer and agent consume curated project context")

    print("\n"+"="*72)
    print("STEP 19.1 DOCUMENT THEME INTEGRATION PASSED")
    print("="*72)


if __name__=="__main__":
    main()
