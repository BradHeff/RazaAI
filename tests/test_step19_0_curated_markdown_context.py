import tempfile
from pathlib import Path

from app.context import CuratedProjectContext


def main():
    print("="*72)
    print("RazaAI Step 19.0 Curated Markdown Context")
    print("="*72)

    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"knowledge/project").mkdir(parents=True)
        (root/"Branding.md").write_text(
            "---\n"
            "scope: branding\n"
            "priority: 95\n"
            "primary_color: #102A43\n"
            "accent_color: #0E7490\n"
            "organisation: Example School\n"
            "---\n"
            "# Brand\n"
            "Use a clean, calm school-facing style.\n"
            "footer_text: Example School\n",
            encoding="utf-8",
        )
        (root/"knowledge/project/FortiClient.md").write_text(
            "---\nscope: cybersecurity\npriority: 80\n---\n"
            "# FortiClient\n"
            "FortiClient EMS is replacing Linewize in this project.\n",
            encoding="utf-8",
        )

        context=CuratedProjectContext(root)
        status=context.status()
        assert status["count"]==2
        theme=status["document_theme"]
        assert theme["primary_color"]=="102A43"
        assert theme["accent_color"]=="0E7490"
        assert theme["organisation"]=="Example School"
        print("[PASS] BRANDING.md provides safe document-theme values")

        results=context.search("FortiClient Linewize",top_k=3)
        assert results and results[0][1].path.endswith("FortiClient.md")
        print("[PASS] arbitrary project Markdown under knowledge/project is searchable")

        guidance=context.guidance("Create a staff document",document_request=True)
        assert "Branding.md" in guidance
        assert "CURATED PROJECT CONTEXT" in guidance
        print("[PASS] branding/document Markdown is surfaced for document creation")

    print("\n"+"="*72)
    print("STEP 19.0 CURATED MARKDOWN CONTEXT PASSED")
    print("="*72)


if __name__=="__main__":
    main()
