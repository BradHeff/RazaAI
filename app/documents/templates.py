from .models import (
    DocumentModel,
    DocumentSection,
    KeyValueItem,
)


def incident_report_template(
    *,
    title,
    summary,
    symptoms,
    root_cause,
    resolution,
    validation,
    organisation=None,
    author="RazaAI",
    document_id=None,
):
    return DocumentModel(
        title=title,
        subtitle="ICT Incident Report",
        organisation=organisation,
        author=author,
        document_id=document_id,
        status="Final",
        classification="Internal",
        sections=[
            DocumentSection(
                heading="Incident Summary",
                paragraphs=[summary],
            ),
            DocumentSection(
                heading="Symptoms",
                bullets=list(symptoms),
            ),
            DocumentSection(
                heading="Root Cause",
                paragraphs=[root_cause],
            ),
            DocumentSection(
                heading="Resolution",
                paragraphs=[resolution],
            ),
            DocumentSection(
                heading="Validation",
                bullets=list(validation),
            ),
        ],
    )
