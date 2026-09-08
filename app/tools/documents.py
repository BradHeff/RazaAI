from pathlib import Path

from app.documents import (
    DocumentEngine,
    DocumentModel,
    DocumentSection,
    DocumentTable,
    KeyValueItem,
)
from app.documents.templates import (
    incident_report_template,
)
from app.documents.guide_builder import (
    validate_instruction_guide_sections,
)
from app.context import CuratedProjectContext


DOCUMENT_TEMPLATES = {
    "general_document": {
        "name": "General Document",
        "description": (
            "Flexible document with headings, paragraphs, bullets, "
            "numbered lists, key/value fields and tables."
        ),
    },
    "instruction_guide": {
        "name": "Instruction Guide",
        "description": (
            "Polished step-by-step guide with strong visual hierarchy, "
            "key facts, numbered procedures, tips and troubleshooting."
        ),
    },
    "incident_report": {
        "name": "ICT Incident Report",
        "description": (
            "Structured ICT incident report with summary, symptoms, "
            "root cause, resolution and validation."
        ),
    },
}


def _section_from_dict(data):
    key_values = [
        KeyValueItem(
            key=str(item.get("key", "")),
            value=str(item.get("value", "")),
        )
        for item in (data.get("key_values") or [])
    ]

    tables = []

    for table in data.get("tables") or []:
        tables.append(
            DocumentTable(
                headers=[
                    str(value)
                    for value in (table.get("headers") or [])
                ],
                rows=[
                    [
                        str(value)
                        for value in row
                    ]
                    for row in (table.get("rows") or [])
                ],
                widths=table.get("widths"),
            )
        )

    return DocumentSection(
        heading=str(data.get("heading", "")).strip(),
        paragraphs=[
            str(value)
            for value in (data.get("paragraphs") or [])
        ],
        bullets=[
            str(value)
            for value in (data.get("bullets") or [])
        ],
        numbered=[
            str(value)
            for value in (data.get("numbered") or [])
        ],
        key_values=key_values,
        tables=tables,
    )


def _build_general_document(
    *,
    title,
    subtitle=None,
    author="RazaAI",
    organisation=None,
    document_id=None,
    version="1.0",
    status="Draft",
    classification="Internal",
    sections=None,
    style="professional",
):
    return DocumentModel(
        title=title,
        subtitle=subtitle,
        author=author,
        organisation=organisation,
        document_id=document_id,
        version=version,
        status=status,
        classification=classification,
        style=style,
        sections=[
            _section_from_dict(section)
            for section in (sections or [])
        ],
    )


def _build_incident_report(
    *,
    title,
    organisation=None,
    author="RazaAI",
    document_id=None,
    incident=None,
):
    incident = incident or {}

    return incident_report_template(
        title=title,
        summary=str(
            incident.get("summary", "")
        ),
        symptoms=[
            str(value)
            for value in (incident.get("symptoms") or [])
        ],
        root_cause=str(
            incident.get("root_cause", "")
        ),
        resolution=str(
            incident.get("resolution", "")
        ),
        validation=[
            str(value)
            for value in (incident.get("validation") or [])
        ],
        organisation=organisation,
        author=author,
        document_id=document_id,
    )


def create_document(
    title,
    format="docx",
    template="general_document",
    filename=None,
    subtitle=None,
    author="RazaAI",
    organisation=None,
    document_id=None,
    version="1.0",
    status="Draft",
    classification="Internal",
    sections=None,
    incident=None,
    style=None,
):
    """Create a local DOCX, PDF, or both."""

    format = str(format).strip().lower()
    template = str(template).strip().lower()

    if format not in {
        "docx",
        "pdf",
        "both",
    }:
        raise ValueError(
            "format must be one of: docx, pdf, both"
        )

    if template not in DOCUMENT_TEMPLATES:
        raise ValueError(
            f"Unknown document template: {template}. "
            f"Available: {sorted(DOCUMENT_TEMPLATES)}"
        )

    if template == "incident_report":
        model = _build_incident_report(
            title=title,
            organisation=organisation,
            author=author,
            document_id=document_id,
            incident=incident,
        )

    else:
        if template == "instruction_guide":
            # Incident semantics are invalid for a user-facing how-to guide.
            # The argument may be present in a small-model tool call, but it is
            # never consumed by this template.
            incident = None
            validate_instruction_guide_sections(sections)

        resolved_style = style or (
            "guide" if template == "instruction_guide" else "professional"
        )
        model = _build_general_document(
            title=title,
            subtitle=subtitle,
            author=author,
            organisation=organisation,
            document_id=document_id,
            version=version,
            status=status,
            classification=classification,
            sections=sections,
            style=resolved_style,
        )

    # Apply operator-curated branding/document theme when present.
    theme = CuratedProjectContext().document_theme()
    if theme:
        model.metadata["theme"] = theme
        if not model.organisation and theme.get("organisation"):
            model.organisation = theme["organisation"]

    engine = DocumentEngine()

    if format == "docx":
        return engine.create_docx(
            model,
            filename=filename,
        )

    if format == "pdf":
        return engine.create_pdf(
            model,
            filename=filename,
        )

    return engine.create_both(
        model,
        filename=filename,
    )


def list_document_templates():
    return {
        "templates": [
            {
                "id": key,
                **value,
            }
            for key, value
            in DOCUMENT_TEMPLATES.items()
        ]
    }


def list_generated_documents():
    engine = DocumentEngine()

    files = []

    for path in sorted(
        engine.output_directory.glob("*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        if not path.is_file():
            continue

        if path.suffix.lower() not in {
            ".docx",
            ".pdf",
        }:
            continue

        files.append({
            "filename": path.name,
            "path": str(path),
            "format": path.suffix.lower().lstrip("."),
            "size_bytes": path.stat().st_size,
        })

    return {
        "directory": str(engine.output_directory),
        "documents": files[:50],
    }


CREATE_DOCUMENT_METADATA = {
    "name": "create_document",
    "category": "documents",
    "risk": "write_local",
    "permission": "automatic",
    "timeout": 60,
}


LIST_DOCUMENT_TEMPLATES_METADATA = {
    "name": "list_document_templates",
    "category": "documents",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}


LIST_GENERATED_DOCUMENTS_METADATA = {
    "name": "list_generated_documents",
    "category": "documents",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}


CREATE_DOCUMENT_DEFINITION = {
    "type": "function",
    "function": {
        "name": "create_document",
        "description": (
            "Create a professional local document as DOCX, PDF, or both. "
            "Use this tool whenever the user asks to create, generate, save, "
            "write, export, or produce a Word/DOCX or PDF document. "
            "For ordinary flexible documents use template=general_document. "
            "For user-facing how-to, setup, onboarding or instruction guides use "
            "template=instruction_guide and provide useful structured sections. "
            "For an explicitly requested resolved ICT incident report use template=incident_report. Incident facts alone are not permission to create a file. "
            "Do not send incident/root-cause/resolution fields with instruction_guide."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Document title.",
                },
                "format": {
                    "type": "string",
                    "enum": [
                        "docx",
                        "pdf",
                        "both",
                    ],
                    "description": (
                        "Output format. Use both when the user asks for "
                        "Word/DOCX and PDF."
                    ),
                },
                "template": {
                    "type": "string",
                    "enum": [
                        "general_document",
                        "instruction_guide",
                        "incident_report",
                    ],
                },
                "style": {
                    "type": "string",
                    "enum": ["professional", "guide"],
                    "description": (
                        "Optional visual style. instruction_guide defaults to guide."
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Optional base filename only. Do not provide paths."
                    ),
                },
                "subtitle": {
                    "type": "string",
                },
                "author": {
                    "type": "string",
                },
                "organisation": {
                    "type": "string",
                },
                "document_id": {
                    "type": "string",
                },
                "version": {
                    "type": "string",
                },
                "status": {
                    "type": "string",
                },
                "classification": {
                    "type": "string",
                },
                "sections": {
                    "type": "array",
                    "description": (
                        "Document sections. Each section must have a heading and may "
                        "contain paragraphs, bullets, numbered steps, key/value items "
                        "and tables. For instruction_guide, provide a useful complete "
                        "guide rather than echoing the user request: normally include "
                        "an overview, key details/requirements, numbered steps, and "
                        "troubleshooting/help when relevant. Sparse one-section guides "
                        "are rejected before a file is written."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {
                                "type": "string",
                            },
                            "paragraphs": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "bullets": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "numbered": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "key_values": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "key": {
                                            "type": "string",
                                        },
                                        "value": {
                                            "type": "string",
                                        },
                                    },
                                    "required": [
                                        "key",
                                        "value",
                                    ],
                                },
                            },
                            "tables": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "headers": {
                                            "type": "array",
                                            "items": {
                                                "type": "string",
                                            },
                                        },
                                        "rows": {
                                            "type": "array",
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "type": "string",
                                                },
                                            },
                                        },
                                    },
                                    "required": [
                                        "headers",
                                        "rows",
                                    ],
                                },
                            },
                        },
                        "required": [
                            "heading",
                        ],
                    },
                },
                "incident": {
                    "type": "object",
                    "description": (
                        "Content for incident_report."
                    ),
                    "properties": {
                        "summary": {
                            "type": "string",
                        },
                        "symptoms": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                        },
                        "root_cause": {
                            "type": "string",
                        },
                        "resolution": {
                            "type": "string",
                        },
                        "validation": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                        },
                    },
                    "required": [
                        "summary",
                        "symptoms",
                        "root_cause",
                        "resolution",
                        "validation",
                    ],
                },
            },
            "required": [
                "title",
                "format",
                "template",
            ],
        },
    },
}


LIST_DOCUMENT_TEMPLATES_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_document_templates",
        "description": (
            "List document templates RazaAI can generate."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


LIST_GENERATED_DOCUMENTS_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_generated_documents",
        "description": (
            "List DOCX and PDF files previously generated in "
            "RazaAI's safe output/documents directory."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
