from datetime import date
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    ListFlowable,
    ListItem,
    KeepTogether,
)

from .models import DocumentModel


NAVY = colors.HexColor("#173C5E")
TEAL = colors.HexColor("#2A7C91")
PALE_BLUE = colors.HexColor("#EDF5F8")
PALE_GREY = colors.HexColor("#F5F7F9")
MID_GREY = colors.HexColor("#D6DEE4")
TEXT = colors.HexColor("#202B33")
MUTED = colors.HexColor("#66737D")
TIP_BG = colors.HexColor("#EAF4F7")
IMPORTANT_BG = colors.HexColor("#FFF5DB")
EXAMPLE_BG = colors.HexColor("#EDF7EF")


class PdfWriter:
    """ReportLab renderer for RazaAI documents."""

    def __init__(self):
        self.page_size = A4
        self.NAVY = NAVY
        self.TEAL = TEAL
        self.MUTED = MUTED

    def _apply_theme(self, model):
        theme = (getattr(model, "metadata", {}) or {}).get("theme") or {}
        def c(key, default):
            value = theme.get(key)
            return colors.HexColor("#" + value) if value else default
        self.NAVY = c("primary_color", NAVY)
        self.TEAL = c("accent_color", TEAL)
        self.MUTED = c("muted_color", MUTED)

    def _styles(self, guide=False):
        styles = getSampleStyleSheet()

        styles.add(ParagraphStyle(
            name="RazaTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21 if guide else 22,
            leading=27,
            textColor=self.NAVY if guide else TEXT,
            spaceAfter=5,
            alignment=TA_LEFT,
        ))
        styles.add(ParagraphStyle(
            name="RazaSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=13,
            textColor=self.MUTED,
            spaceAfter=11,
        ))
        styles.add(ParagraphStyle(
            name="RazaHeading1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13.5 if guide else 15,
            leading=18,
            textColor=self.TEAL if guide else TEXT,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ))
        styles.add(ParagraphStyle(
            name="RazaBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.4 if guide else 9.5,
            leading=12.4,
            textColor=TEXT,
            spaceAfter=6,
        ))
        styles.add(ParagraphStyle(
            name="RazaBodyBold",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=TEXT,
        ))
        styles.add(ParagraphStyle(
            name="RazaSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=TEXT,
        ))
        styles.add(ParagraphStyle(
            name="RazaSmallBold",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=TEXT,
        ))
        styles.add(ParagraphStyle(
            name="RazaStepNumber",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.white,
            alignment=TA_LEFT,
        ))
        return styles

    @staticmethod
    def _escape(value):
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _rich(self, value):
        """Escape user/model content, then allow tiny safe markdown emphasis."""
        text = self._escape(value)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        return text

    def _page_header_footer(self, canvas, doc, model, guide):
        canvas.saveState()
        width, height = self.page_size

        if guide:
            canvas.setStrokeColor(self.TEAL)
            canvas.setLineWidth(1.2)
            canvas.line(18 * mm, height - 13 * mm, width - 18 * mm, height - 13 * mm)
            header = model.organisation or "Staff Guide"
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(self.MUTED)
            canvas.drawString(18 * mm, height - 10 * mm, str(header)[:80])

            canvas.setStrokeColor(MID_GREY)
            canvas.setLineWidth(0.35)
            canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
            canvas.setFont("Helvetica", 7.3)
            canvas.setFillColor(self.MUTED)
            canvas.drawString(18 * mm, 8.5 * mm, model.title[:70])
            canvas.drawRightString(width - 18 * mm, 8.5 * mm, f"Page {doc.page}")
        else:
            organisation = model.organisation or "RazaAI"
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(TEXT)
            canvas.drawRightString(width - 18 * mm, height - 12 * mm, organisation)
            canvas.setStrokeColor(colors.HexColor("#BFBFBF"))
            canvas.setLineWidth(0.4)
            canvas.line(18 * mm, height - 15 * mm, width - 18 * mm, height - 15 * mm)
            footer_text = (
                f"{model.document_id or 'RazaAI Document'}  |  "
                f"Version {model.version}  |  {model.classification}  |  Page {doc.page}"
            )
            canvas.setFont("Helvetica", 7.5)
            canvas.drawCentredString(width / 2, 10 * mm, footer_text)

        canvas.restoreState()

    def _build_metadata_table(self, model, styles):
        created = model.created_date or date.today().isoformat()
        rows = [
            ["Document ID", model.document_id or "-"],
            ["Author", model.author],
            ["Status", model.status],
            ["Version", model.version],
            ["Classification", model.classification],
            ["Created", created],
        ]
        data = [
            [Paragraph(self._escape(k), styles["RazaSmallBold"]),
             Paragraph(self._escape(v), styles["RazaSmall"])]
            for k, v in rows
        ]
        table = Table(data, colWidths=[34 * mm, 120 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ]))
        return table

    def _build_key_value_table(self, items, styles, guide=False):
        data = []
        for item in items:
            data.append([
                Paragraph(self._rich(item.key), styles["RazaSmallBold"]),
                Paragraph(self._rich(item.value), styles["RazaBody"] if guide else styles["RazaSmall"]),
            ])
        table = Table(data, colWidths=[39 * mm, 115 * mm], hAlign="LEFT")
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.35, MID_GREY),
            ("BACKGROUND", (0, 0), (0, -1), PALE_BLUE if guide else colors.HexColor("#F3F3F3")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7 if guide else 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7 if guide else 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5 if guide else 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if guide else 4),
        ]
        if guide:
            commands += [
                ("TEXTCOLOR", (0, 0), (0, -1), self.NAVY),
                ("LINEBEFORE", (0, 0), (0, -1), 2, self.TEAL),
            ]
        table.setStyle(TableStyle(commands))
        return table

    def _build_data_table(self, table_model, styles, guide=False):
        header = [Paragraph(self._rich(v), styles["RazaSmallBold"]) for v in table_model.headers]
        data = [header]
        for row in table_model.rows:
            data.append([Paragraph(self._rich(v), styles["RazaSmall"]) for v in row])
        usable_width = 154 * mm
        if table_model.widths:
            total = sum(table_model.widths)
            col_widths = [usable_width * (v / total) for v in table_model.widths]
        else:
            count = max(1, len(table_model.headers))
            col_widths = [usable_width / count for _ in range(count)]
        table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.NAVY if guide else colors.HexColor("#E7E6E6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if guide else TEXT),
            ("GRID", (0, 0), (-1, -1), 0.35, MID_GREY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GREY]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    def _callout(self, text, styles):
        raw = str(text).strip()
        m = re.match(r"^(Tip|Important|Note|Example)\s*:\s*(.*)$", raw, re.I)
        if not m:
            return None
        label, body = m.group(1).title(), m.group(2)
        bg = IMPORTANT_BG if label == "Important" else EXAMPLE_BG if label == "Example" else TIP_BG
        accent = colors.HexColor("#C99017") if label == "Important" else colors.HexColor("#4C8F5F") if label == "Example" else self.TEAL
        content = Paragraph(f"<b>{self._escape(label)}:</b> {self._rich(body)}", styles["RazaBody"])
        table = Table([[content]], colWidths=[154 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.3, MID_GREY),
            ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _step_card(self, number, text, styles):
        badge = Table([[Paragraph(str(number), styles["RazaStepNumber"])]], colWidths=[10 * mm], rowHeights=[10 * mm])
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self.NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        body = Paragraph(self._rich(text), styles["RazaBody"])
        card = Table([[badge, body]], colWidths=[14 * mm, 140 * mm], hAlign="LEFT")
        card.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (1, 0), PALE_GREY),
            ("BOX", (1, 0), (1, 0), 0.35, MID_GREY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (1, 0), (1, 0), 9),
            ("RIGHTPADDING", (1, 0), (1, 0), 9),
            ("TOPPADDING", (1, 0), (1, 0), 5),
            ("BOTTOMPADDING", (1, 0), (1, 0), 3),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 4),
            ("TOPPADDING", (0, 0), (0, 0), 0),
            ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ]))
        return KeepTogether([card, Spacer(1, 3)])

    def write(self, model: DocumentModel, output_path: Path):
        model.validate()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        guide = str(getattr(model, "style", "professional")).lower() == "guide"
        self._apply_theme(model)
        styles = self._styles(guide=guide)
        doc = BaseDocTemplate(
            str(output_path), pagesize=self.page_size,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=17 * mm if guide else 22 * mm,
            bottomMargin=16 * mm if guide else 18 * mm,
            title=model.title, author=model.author, subject=model.subtitle or "",
        )
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
        doc.addPageTemplates([PageTemplate(
            id="main", frames=[frame],
            onPage=lambda canvas, document: self._page_header_footer(canvas, document, model, guide),
        )])

        story = []
        if guide:
            story.append(Spacer(1, 4))
        story.append(Paragraph(self._rich(model.title), styles["RazaTitle"]))
        if model.subtitle:
            story.append(Paragraph(self._rich(model.subtitle), styles["RazaSubtitle"]))

        if guide:
            story.append(Spacer(1, 1))
            accent = Table([[""]], colWidths=[35 * mm], rowHeights=[2.2 * mm], hAlign="LEFT")
            accent.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), self.TEAL)]))
            story += [accent, Spacer(1, 9)]
        else:
            story += [self._build_metadata_table(model, styles), Spacer(1, 8)]

        for section in model.sections:
            block = [Paragraph(self._rich(section.heading), styles["RazaHeading1"])]

            for paragraph in section.paragraphs:
                callout = self._callout(paragraph, styles) if guide else None
                if callout:
                    block += [callout, Spacer(1, 6)]
                else:
                    block.append(Paragraph(self._rich(paragraph), styles["RazaBody"]))

            if section.key_values:
                block += [self._build_key_value_table(section.key_values, styles, guide=guide), Spacer(1, 7)]

            if section.numbered:
                if guide:
                    for idx, value in enumerate(section.numbered, 1):
                        block.append(self._step_card(idx, value, styles))
                else:
                    items = [ListItem(Paragraph(self._rich(v), styles["RazaBody"]), leftIndent=10) for v in section.numbered]
                    block += [ListFlowable(items, bulletType="1", start="1", leftIndent=20), Spacer(1, 4)]

            if section.bullets:
                items = [ListItem(Paragraph(self._rich(v), styles["RazaBody"]), leftIndent=10) for v in section.bullets]
                block += [ListFlowable(items, bulletType="bullet", leftIndent=18, bulletFontName="Helvetica", bulletFontSize=8), Spacer(1, 5)]

            for table in section.tables:
                block += [self._build_data_table(table, styles, guide=guide), Spacer(1, 7)]

            story.extend(block)

        doc.build(story)
        return output_path
