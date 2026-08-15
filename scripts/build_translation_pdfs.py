#!/usr/bin/env python3
"""Build polished Chinese reading PDFs from the two translated Markdown papers."""

from __future__ import annotations

import html
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
    XPreformatted,
)


ROOT = Path(__file__).resolve().parents[1]
BODY_FONT = Path.home() / "Library/Fonts/SimSun.ttf"
HEADING_FONT = Path.home() / "Library/Fonts/SimHei.ttf"


PAPERS = [
    {
        "markdown": ROOT / "docs/claude code/2604.14228v2-zh.md",
        "source_pdf": ROOT / "docs/claude code/2604.14228v2.pdf",
        "output": ROOT / "output/pdf/dive-into-claude-code-zh.pdf",
        "temporary": ROOT / "tmp/pdfs/dive-into-claude-code-zh-body.pdf",
        "short_title": "深入 Claude Code",
        "reference_pages": range(41, 49),
    },
    {
        "markdown": ROOT / "docs/claude code/2607.22917-zh.md",
        "source_pdf": ROOT / "docs/claude code/2607.22917.pdf",
        "output": ROOT / "output/pdf/agent-team-work-zone-zh.pdf",
        "temporary": ROOT / "tmp/pdfs/agent-team-work-zone-zh-body.pdf",
        "short_title": "Agent Team Work Zone",
        "reference_pages": range(24, 31),
    },
]


def normalize_text(text: str) -> str:
    """Normalize dash variants that are fragile in PDF text extraction."""
    return (
        text.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def inline_markup(text: str) -> str:
    text = normalize_text(text.strip())
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"@@PH{len(placeholders) - 1}@@"

    text = re.sub(
        r"`([^`]+)`",
        lambda m: stash(
            f'<font name="HiroSans" color="#7A3152">{html.escape(m.group(1))}</font>'
        ),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda m: stash(
            f'<link href="{html.escape(m.group(2), quote=True)}" color="#315D86">'
            f"{html.escape(m.group(1))}</link>"
        ),
        text,
    )
    text = re.sub(
        r"<(https?://[^>]+)>",
        lambda m: stash(
            f'<link href="{html.escape(m.group(1), quote=True)}" color="#315D86">'
            f"{html.escape(m.group(1))}</link>"
        ),
        text,
    )
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    for index, value in enumerate(placeholders):
        text = text.replace(f"@@PH{index}@@", value)
    return text


def make_styles():
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "BodyCN",
        parent=styles["BodyText"],
        fontName="HiroSerif",
        fontSize=9.4,
        leading=15.2,
        textColor=colors.HexColor("#22252A"),
        alignment=TA_LEFT,
        wordWrap="CJK",
        spaceAfter=3.2 * mm,
    )
    return {
        "body": base,
        "title": ParagraphStyle(
            "TitleCN",
            parent=base,
            fontName="HiroSans",
            fontSize=23,
            leading=31,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#233A52"),
            spaceBefore=24 * mm,
            spaceAfter=10 * mm,
        ),
        "h2": ParagraphStyle(
            "H2CN",
            parent=base,
            fontName="HiroSans",
            fontSize=16,
            leading=22,
            textColor=colors.HexColor("#233A52"),
            spaceBefore=7 * mm,
            spaceAfter=3.5 * mm,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3CN",
            parent=base,
            fontName="HiroSans",
            fontSize=12.5,
            leading=18,
            textColor=colors.HexColor("#3D5972"),
            spaceBefore=5 * mm,
            spaceAfter=2.5 * mm,
            keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "H4CN",
            parent=base,
            fontName="HiroSans",
            fontSize=10.5,
            leading=16,
            textColor=colors.HexColor("#536D82"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "quote": ParagraphStyle(
            "QuoteCN",
            parent=base,
            leftIndent=7 * mm,
            rightIndent=3 * mm,
            borderColor=colors.HexColor("#8AA4B8"),
            borderWidth=1.2,
            borderPadding=(2.5 * mm, 3 * mm, 2.5 * mm, 4 * mm),
            backColor=colors.HexColor("#F2F6F8"),
            textColor=colors.HexColor("#3E4D58"),
            spaceBefore=2 * mm,
            spaceAfter=4 * mm,
        ),
        "bullet": ParagraphStyle(
            "BulletCN",
            parent=base,
            leftIndent=6 * mm,
            firstLineIndent=-4 * mm,
            spaceAfter=1.5 * mm,
        ),
        "code": ParagraphStyle(
            "CodeCN",
            parent=base,
            fontName="HiroSerif",
            fontSize=7.7,
            leading=11.5,
            leftIndent=4 * mm,
            rightIndent=4 * mm,
            borderColor=colors.HexColor("#D5DCE2"),
            borderWidth=0.5,
            borderPadding=3 * mm,
            backColor=colors.HexColor("#F6F7F8"),
            spaceBefore=2 * mm,
            spaceAfter=4 * mm,
        ),
        "table": ParagraphStyle(
            "TableCN",
            parent=base,
            fontSize=7.3,
            leading=10.4,
            spaceAfter=0,
        ),
        "table_head": ParagraphStyle(
            "TableHeadCN",
            parent=base,
            fontName="HiroSans",
            fontSize=7.3,
            leading=10.4,
            textColor=colors.white,
            spaceAfter=0,
        ),
        "appendix_note": ParagraphStyle(
            "AppendixNote",
            parent=base,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#536D82"),
            spaceBefore=5 * mm,
        ),
    }


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def column_widths(rows: list[list[str]], available: float) -> list[float]:
    count = max(len(row) for row in rows)
    weights = []
    for column in range(count):
        lengths = [len(row[column]) if column < len(row) else 0 for row in rows]
        weights.append(max(8, min(max(lengths, default=8), 38)))
    total = sum(weights)
    widths = [available * weight / total for weight in weights]
    minimum = 24 * mm if count <= 4 else 17 * mm
    widths = [max(minimum, width) for width in widths]
    scale = available / sum(widths)
    return [width * scale for width in widths]


def table_flowable(lines: list[str], styles, available: float):
    raw_rows = [split_table_row(line) for line in lines if not is_table_separator(line)]
    columns = max(len(row) for row in raw_rows)
    raw_rows = [row + [""] * (columns - len(row)) for row in raw_rows]
    rows = []
    for row_index, row in enumerate(raw_rows):
        style = styles["table_head"] if row_index == 0 else styles["table"]
        rows.append([Paragraph(inline_markup(cell), style) for cell in row])
    table = LongTable(
        rows,
        colWidths=column_widths(raw_rows, available),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3D5972")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "HiroSans"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD4DA")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            commands.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F4F6F7"))
            )
    table.setStyle(TableStyle(commands))
    return table


def markdown_story(text: str, styles, available: float):
    lines = normalize_text(text).splitlines()
    story = []
    paragraph_lines: list[str] = []
    title_seen = False

    def flush_paragraph():
        if paragraph_lines:
            merged = " ".join(line.strip() for line in paragraph_lines)
            story.append(Paragraph(inline_markup(merged), styles["body"]))
            paragraph_lines.clear()

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            story.append(XPreformatted(html.escape("\n".join(code_lines)), styles["code"]))
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            content = inline_markup(heading.group(2))
            if level == 1 and not title_seen:
                story.append(Paragraph(content, styles["title"]))
                story.append(HRFlowable(width="45%", color=colors.HexColor("#8AA4B8")))
                story.append(Spacer(1, 8 * mm))
                title_seen = True
            else:
                style = styles["h2"] if level <= 2 else styles["h3"] if level == 3 else styles["h4"]
                story.append(Paragraph(content, style))
            index += 1
            continue

        if stripped == "---":
            flush_paragraph()
            story.append(Spacer(1, 2 * mm))
            story.append(HRFlowable(width="100%", color=colors.HexColor("#D5DCE2")))
            story.append(Spacer(1, 2 * mm))
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            story.append(Paragraph(inline_markup(" ".join(quote_lines)), styles["quote"]))
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            flush_paragraph()
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            story.append(table_flowable(table_lines, styles, available))
            story.append(Spacer(1, 4 * mm))
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if bullet or numbered:
            flush_paragraph()
            marker = "•" if bullet else f"{numbered.group(1)}."
            content = bullet.group(1) if bullet else numbered.group(2)
            story.append(
                Paragraph(
                    f"{html.escape(marker)}&nbsp;&nbsp;{inline_markup(content)}",
                    styles["bullet"],
                )
            )
            index += 1
            continue

        paragraph_lines.append(line)
        index += 1

    flush_paragraph()
    return story


class ReadingDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, short_title: str, **kwargs):
        super().__init__(filename, **kwargs)
        self.short_title = short_title
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="reading", frames=[frame], onPage=self.draw_page))

    def draw_page(self, canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#D5DCE2"))
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, height - 13 * mm, width - doc.rightMargin, height - 13 * mm)
        canvas.setFont("HiroSans", 7.5)
        canvas.setFillColor(colors.HexColor("#687A88"))
        canvas.drawString(doc.leftMargin, height - 10 * mm, self.short_title)
        canvas.drawRightString(width - doc.rightMargin, height - 10 * mm, "中文译读版")
        canvas.drawCentredString(width / 2, 8 * mm, str(doc.page))
        canvas.restoreState()


def build_body(config, styles):
    output = config["temporary"]
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = ReadingDocTemplate(
        str(output),
        config["short_title"],
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=19 * mm,
        bottomMargin=16 * mm,
        title=f"{config['short_title']} - 中文译读版",
        author="hiroAiBook reference edition",
        subject="Chinese reading edition prepared from the translated Markdown source",
    )
    story = markdown_story(config["markdown"].read_text(encoding="utf-8"), styles, doc.width)
    story.extend(
        [
            PageBreak(),
            Paragraph("原文参考文献（保持英文）", styles["title"]),
            Paragraph(
                "以下页面直接取自源 PDF，以完整保留作者、英文题名、出版信息、arXiv 编号、DOI 与 URL。",
                styles["appendix_note"],
            ),
        ]
    )
    doc.build(story)


def merge_reference_pages(config):
    body = PdfReader(str(config["temporary"]))
    source = PdfReader(str(config["source_pdf"]))
    writer = PdfWriter()
    for page in body.pages:
        writer.add_page(page)
    for page_index in config["reference_pages"]:
        writer.add_page(source.pages[page_index])
    writer.add_metadata(
        {
            "/Title": f"{config['short_title']} - 中文译读版",
            "/Author": "Original authors; Chinese translation prepared separately",
            "/Subject": "Chinese reading edition with original bibliography pages",
        }
    )
    config["output"].parent.mkdir(parents=True, exist_ok=True)
    with config["output"].open("wb") as stream:
        writer.write(stream)


def main():
    if not BODY_FONT.exists() or not HEADING_FONT.exists():
        raise FileNotFoundError("Required SimSun.ttf or SimHei.ttf font is missing")
    pdfmetrics.registerFont(TTFont("HiroSerif", str(BODY_FONT)))
    pdfmetrics.registerFont(TTFont("HiroSans", str(HEADING_FONT)))
    styles = make_styles()
    for config in PAPERS:
        build_body(config, styles)
        merge_reference_pages(config)
        print(config["output"])


if __name__ == "__main__":
    main()
