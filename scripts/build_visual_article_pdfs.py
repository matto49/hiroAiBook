#!/usr/bin/env python3
"""Build three illustrated Chinese Claude Code article PDFs from Markdown."""

from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image as PILImage
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
    Image,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
    XPreformatted,
)


ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "docs/claude code/visual-articles"
OUTPUT = ROOT / "output/pdf/claude-code-visual-articles"
BODY_FONT = Path.home() / "Library/Fonts/SimSun.ttf"
HEADING_FONT = Path.home() / "Library/Fonts/SimHei.ttf"

ARTICLES = [
    {
        "slug": "architecture-explained-visually",
        "title": "Claude Code 的架构：图解",
        "output": "claude-code-architecture-explained-visually-zh.pdf",
    },
    {
        "slug": "end-to-end-workflow",
        "title": "Claude Code 端到端工作流",
        "output": "claude-code-end-to-end-workflow-zh.pdf",
    },
    {
        "slug": "multi-agent-orchestration",
        "title": "Claude Code 多智能体编排",
        "output": "claude-code-multi-agent-orchestration-zh.pdf",
    },
]


def normalize(text: str) -> str:
    """Use extraction-safe ASCII punctuation where typographically acceptable."""
    return (
        text.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\\leq", "≤")
        .replace("\\delta", "δ")
        .replace("\\(", "")
        .replace("\\)", "")
    )


def inline_markup(text: str) -> str:
    text = normalize(text.strip())
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"@@PH{len(placeholders)-1}@@"

    text = re.sub(
        r"`([^`]+)`",
        lambda m: stash(f'<font name="HiroSans" color="#7A3152">{html.escape(m.group(1))}</font>'),
        text,
    )
    def render_link(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            return stash(
                f'<link href="{html.escape(target, quote=True)}" color="#315D86">'
                f'{html.escape(label)}</link>'
            )
        return stash(f'<font color="#315D86">{html.escape(label)}</font>')

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", render_link, text)
    text = re.sub(
        r"<((?:https?|mailto):[^>]+)>",
        lambda m: stash(
            f'<link href="{html.escape(m.group(1), quote=True)}" color="#315D86">'
            f'{html.escape(m.group(1))}</link>'
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
    samples = getSampleStyleSheet()
    body = ParagraphStyle(
        "BodyCN",
        parent=samples["BodyText"],
        fontName="HiroSerif",
        fontSize=9.5,
        leading=15.2,
        textColor=colors.HexColor("#22252A"),
        alignment=TA_LEFT,
        wordWrap="CJK",
        spaceAfter=3.0 * mm,
    )
    return {
        "body": body,
        "title": ParagraphStyle(
            "TitleCN", parent=body, fontName="HiroSans", fontSize=24,
            leading=33, alignment=TA_CENTER, textColor=colors.HexColor("#233A52"),
            spaceBefore=23 * mm, spaceAfter=9 * mm,
        ),
        "h2": ParagraphStyle(
            "H2CN", parent=body, fontName="HiroSans", fontSize=16,
            leading=22, textColor=colors.HexColor("#233A52"),
            spaceBefore=7 * mm, spaceAfter=3.5 * mm, keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3CN", parent=body, fontName="HiroSans", fontSize=12.5,
            leading=18, textColor=colors.HexColor("#3D5972"),
            spaceBefore=5 * mm, spaceAfter=2.5 * mm, keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "H4CN", parent=body, fontName="HiroSans", fontSize=10.8,
            leading=16, textColor=colors.HexColor("#536D82"),
            spaceBefore=4 * mm, spaceAfter=2 * mm, keepWithNext=True,
        ),
        "quote": ParagraphStyle(
            "QuoteCN", parent=body, leftIndent=7 * mm, rightIndent=3 * mm,
            borderColor=colors.HexColor("#8AA4B8"), borderWidth=1.2,
            borderPadding=(2.5 * mm, 3 * mm, 2.5 * mm, 4 * mm),
            backColor=colors.HexColor("#F2F6F8"), textColor=colors.HexColor("#3E4D58"),
            spaceBefore=2 * mm, spaceAfter=4 * mm,
        ),
        "bullet": ParagraphStyle(
            "BulletCN", parent=body, leftIndent=6 * mm, firstLineIndent=-4 * mm,
            spaceAfter=1.5 * mm,
        ),
        "caption": ParagraphStyle(
            "CaptionCN", parent=body, fontSize=8.1, leading=12.2,
            alignment=TA_CENTER, textColor=colors.HexColor("#536D82"),
            spaceBefore=2 * mm, spaceAfter=5 * mm,
        ),
        "code": ParagraphStyle(
            "CodeCN", parent=body, fontName="HiroSans", fontSize=7.4,
            leading=10.8, leftIndent=3 * mm, rightIndent=3 * mm,
            borderColor=colors.HexColor("#D5DCE2"), borderWidth=0.5,
            borderPadding=3 * mm, backColor=colors.HexColor("#F6F7F8"),
            spaceBefore=2 * mm, spaceAfter=4 * mm,
        ),
        "table": ParagraphStyle(
            "TableCN", parent=body, fontSize=7.2, leading=10.3, spaceAfter=0,
        ),
        "table_head": ParagraphStyle(
            "TableHeadCN", parent=body, fontName="HiroSans", fontSize=7.2,
            leading=10.3, textColor=colors.white, spaceAfter=0,
        ),
    }


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def separator_row(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def table_widths(rows: list[list[str]], available: float) -> list[float]:
    count = max(len(row) for row in rows)
    weights = []
    for col in range(count):
        lengths = [len(row[col]) if col < len(row) else 0 for row in rows]
        weights.append(max(8, min(max(lengths, default=8), 40)))
    minimum = 21 * mm if count <= 4 else 15 * mm
    widths = [max(minimum, available * weight / sum(weights)) for weight in weights]
    scale = available / sum(widths)
    return [width * scale for width in widths]


def make_table(lines: list[str], styles, available: float):
    raw = [split_row(line) for line in lines if not separator_row(line)]
    columns = max(len(row) for row in raw)
    raw = [row + [""] * (columns - len(row)) for row in raw]
    rows = []
    for row_index, row in enumerate(raw):
        style = styles["table_head"] if row_index == 0 else styles["table"]
        rows.append([Paragraph(inline_markup(cell), style) for cell in row])
    table = LongTable(rawRows := rows, colWidths=table_widths(raw, available), repeatRows=1, splitByRow=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3D5972")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD4DA")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index in range(1, len(rawRows)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F4F6F7")))
    table.setStyle(TableStyle(commands))
    return table


def image_flowable(path: Path, available_width: float):
    with PILImage.open(path) as source:
        pixel_width, pixel_height = source.size
    max_width = available_width
    max_height = 205 * mm
    scale = min(max_width / pixel_width, max_height / pixel_height)
    result = Image(str(path), width=pixel_width * scale, height=pixel_height * scale)
    result.hAlign = "CENTER"
    return result


def markdown_story(markdown: Path, styles, available: float):
    lines = normalize(markdown.read_text(encoding="utf-8")).splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
            lines = lines[end + 1:]
        except ValueError:
            pass
    story = []
    paragraph_lines: list[str] = []
    title_seen = False

    def flush_paragraph():
        if not paragraph_lines:
            return
        merged = " ".join(line.strip() for line in paragraph_lines)
        style = styles["caption"] if merged.startswith("*") and merged.endswith("*") and "图 " in merged else styles["body"]
        story.append(Paragraph(inline_markup(merged), style))
        paragraph_lines.clear()

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph(); index += 1; continue
        if stripped.startswith("```"):
            flush_paragraph(); code = []; index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index]); index += 1
            story.append(XPreformatted(html.escape("\n".join(code)), styles["code"]))
            index += 1; continue
        image_match = re.match(r"^!\[[^\]]*\]\(([^)]+)\)$", stripped)
        if image_match:
            flush_paragraph()
            path = (markdown.parent / image_match.group(1)).resolve()
            story.extend([Spacer(1, 2 * mm), image_flowable(path, available), Spacer(1, 1 * mm)])
            index += 1; continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph(); level = len(heading.group(1)); content = inline_markup(heading.group(2))
            if level == 1 and not title_seen:
                story.extend([
                    Paragraph(content, styles["title"]),
                    HRFlowable(width="45%", color=colors.HexColor("#8AA4B8")),
                    Spacer(1, 8 * mm),
                ])
                title_seen = True
            else:
                style = styles["h2"] if level <= 2 else styles["h3"] if level == 3 else styles["h4"]
                story.append(Paragraph(content, style))
            index += 1; continue
        if stripped == "---":
            flush_paragraph(); story.extend([
                Spacer(1, 2 * mm), HRFlowable(width="100%", color=colors.HexColor("#D5DCE2")), Spacer(1, 2 * mm)
            ]); index += 1; continue
        if stripped.startswith(">"):
            flush_paragraph(); quote = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip()[1:].strip()); index += 1
            story.append(Paragraph(inline_markup(" ".join(quote)), styles["quote"])); continue
        if stripped.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            flush_paragraph(); table = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index].strip()); index += 1
            story.extend([make_table(table, styles, available), Spacer(1, 4 * mm)]); continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if bullet or numbered:
            flush_paragraph(); marker = "•" if bullet else f"{numbered.group(1)}."
            content = bullet.group(1) if bullet else numbered.group(2)
            story.append(Paragraph(f"{html.escape(marker)}&nbsp;&nbsp;{inline_markup(content)}", styles["bullet"]))
            index += 1; continue
        paragraph_lines.append(line); index += 1
    flush_paragraph()
    return story


class ArticleDoc(BaseDocTemplate):
    def __init__(self, filename: str, short_title: str, **kwargs):
        super().__init__(filename, **kwargs)
        self.short_title = short_title
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, 0, 0, 0, 0)
        self.addPageTemplates(PageTemplate(id="article", frames=[frame], onPage=self.draw_page))

    def draw_page(self, canvas, doc):
        canvas.saveState(); width, height = A4
        canvas.setStrokeColor(colors.HexColor("#D5DCE2")); canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, height - 13 * mm, width - doc.rightMargin, height - 13 * mm)
        canvas.setFont("HiroSans", 7.5); canvas.setFillColor(colors.HexColor("#687A88"))
        canvas.drawString(doc.leftMargin, height - 10 * mm, self.short_title)
        canvas.drawRightString(width - doc.rightMargin, height - 10 * mm, "中文全译·图文版")
        canvas.drawCentredString(width / 2, 8 * mm, str(doc.page)); canvas.restoreState()


def build(article, styles):
    source = COLLECTION / article["slug"] / "translation-zh.md"
    target = OUTPUT / article["output"]
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = ArticleDoc(
        str(target), article["title"], pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=19 * mm, bottomMargin=16 * mm,
        title=f'{article["title"]} - 中文全译图文版',
        author="Original authors; Chinese translation prepared for local research",
        subject="Complete Chinese translation retaining original figures, code and tables",
    )
    doc.build(markdown_story(source, styles, doc.width))
    print(target)


def main():
    if not BODY_FONT.exists() or not HEADING_FONT.exists():
        raise FileNotFoundError("Required SimSun.ttf or SimHei.ttf font is missing")
    pdfmetrics.registerFont(TTFont("HiroSerif", str(BODY_FONT)))
    pdfmetrics.registerFont(TTFont("HiroSans", str(HEADING_FONT)))
    styles = make_styles()
    for article in ARTICLES:
        build(article, styles)


if __name__ == "__main__":
    main()
