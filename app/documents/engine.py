from pathlib import Path

from .docx_writer import DocxWriter
from .pdf_writer import PdfWriter
from .models import DocumentModel
from .safety import (
    ensure_output_directory,
    safe_filename,
)


class DocumentEngine:
    """Safe local document-generation engine."""

    def __init__(self, project_root=None):
        if project_root is None:
            project_root = (
                Path(__file__)
                .resolve()
                .parents[2]
            )

        self.project_root = Path(project_root)

        self.output_directory = (
            ensure_output_directory(
                self.project_root
            )
        )

        self.docx_writer = DocxWriter()
        self.pdf_writer = PdfWriter()

    def create_docx(
        self,
        model: DocumentModel,
        filename=None,
    ):
        name = safe_filename(
            filename or model.title,
            "docx",
        )

        output_path = (
            self.output_directory
            / name
        )

        self.docx_writer.write(
            model,
            output_path,
        )

        return {
            "format": "docx",
            "filename": name,
            "path": str(output_path),
            "size_bytes": output_path.stat().st_size,
        }

    def create_pdf(
        self,
        model: DocumentModel,
        filename=None,
    ):
        name = safe_filename(
            filename or model.title,
            "pdf",
        )

        output_path = (
            self.output_directory
            / name
        )

        self.pdf_writer.write(
            model,
            output_path,
        )

        return {
            "format": "pdf",
            "filename": name,
            "path": str(output_path),
            "size_bytes": output_path.stat().st_size,
        }

    def create_both(
        self,
        model: DocumentModel,
        filename=None,
    ):
        base_name = (
            filename
            or model.title
        )

        docx = self.create_docx(
            model,
            filename=base_name,
        )

        pdf = self.create_pdf(
            model,
            filename=base_name,
        )

        return {
            "format": "both",
            "docx": docx,
            "pdf": pdf,
        }
