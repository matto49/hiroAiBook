#!/usr/bin/env python3
"""Build a JIS B5 Chinese reference anthology from eight translated articles.

The body is printed from HTML by headless Chrome so Mermaid diagrams remain
vector graphics. ReportLab and pypdf add the cover, numbered contents, running
headers, page numbers, metadata, and PDF outline entries.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import logging
import re
import subprocess
import urllib.request
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "docs/claude code/inside-claude-code-full-references"
TMP = ROOT / "tmp/pdfs/inside-claude-code-reference-zh"
OUTPUT = ROOT / "output/pdf/claude-code-inside-reference-zh.pdf"
BODY_HTML = TMP / "body.html"
BODY_PDF = TMP / "body.pdf"
FRONT_PDF = TMP / "front.pdf"
MERMAID_JS = TMP / "mermaid.min.js"
MERMAID_URL = (
    "https://y-agent.github.io/inside-claude-code/"
    "site_libs/quarto-diagram/mermaid.min.js"
)
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
BODY_FONT = Path.home() / "Library/Fonts/SimSun.ttf"
HEADING_FONT = Path.home() / "Library/Fonts/SimHei.ttf"
PAGE_SIZE = (182 * mm, 257 * mm)

ARTICLES = [
    ("02-agent-loop-query-engine", "Agent Loop 与 QueryEngine"),
    ("03-prompt-assembly", "Prompt 组装流水线"),
    ("04-context-compaction", "上下文压缩（Context Compaction）"),
    ("05-tool-system", "工具系统与注册表（Tool System & Registry）"),
    ("06-safety-sandbox", "安全与沙箱"),
    ("08-cli-commands-ui", "CLI、Commands 与终端 UI"),
    ("09-auth-providers-flags", "认证、Provider 与 Feature Flag"),
    ("11-hooks-lifecycle", "Hooks 与生命周期事件"),
]


def normalize(text: str) -> str:
    return (
        text.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    return text[end + 5 :].lstrip("\n") if end >= 0 else text


def inline_html(text: str) -> str:
    """Render the small Markdown inline subset used by the archive."""
    text = normalize(text.strip())
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"ZXQHTML{len(placeholders) - 1:04d}QXZ"

    text = re.sub(
        r"`+([^`\n]+?)`+",
        lambda match: stash(f"<code>{html.escape(match.group(1))}</code>"),
        text,
    )

    def link(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            return stash(
                f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>'
            )
        return stash(f'<span class="local-link">{html.escape(label)}</span>')

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(
        r"<(https?://[^>]+)>",
        lambda match: stash(
            f'<a href="{html.escape(match.group(1), quote=True)}">'
            f"{html.escape(match.group(1))}</a>"
        ),
        text,
    )
    text = re.sub(
        r"</?(?:sup|sub|br|i|b)(?:\s[^>]*)?>",
        lambda match: stash(match.group(0)),
        text,
    )
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    for index, value in enumerate(placeholders):
        text = text.replace(f"ZXQHTML{index:04d}QXZ", value)
    return text


def split_table_row(line: str) -> list[str]:
    value = line.strip().strip("|")
    return [cell.replace(r"\|", "|").strip() for cell in re.split(r"(?<!\\)\|", value)]


def table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def render_table(lines: list[str]) -> str:
    rows = [split_table_row(line) for line in lines if not table_separator(line)]
    if not rows:
        return ""
    head, *body = rows
    parts = ["<div class=\"table-wrap\"><table><thead><tr>"]
    parts.extend(f"<th>{inline_html(cell)}</th>" for cell in head)
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>")
        parts.extend(f"<td>{inline_html(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def markdown_to_html(text: str, article_index: int) -> str:
    lines = strip_frontmatter(text).splitlines()
    translator_note = ""
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip().startswith("> 译者说明："):
        translator_note = lines.pop(0).strip()[1:].strip()
        while lines and not lines[0].strip():
            lines.pop(0)
    output: list[str] = [f'<article class="article article-{article_index}">']
    paragraph: list[str] = []
    index = 0
    seen_h1 = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        merged = " ".join(item.strip() for item in paragraph)
        css = "caption" if merged.startswith("*") and merged.endswith("*") and "图" in merged else ""
        output.append(f'<p class="{css}">{inline_html(merged)}</p>')
        paragraph.clear()

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            source = "\n".join(code)
            if language == "mermaid":
                output.append(f'<div class="diagram"><pre class="mermaid">{html.escape(source)}</pre></div>')
            else:
                output.append(
                    f'<pre class="code-block"><code>{html.escape(source)}</code></pre>'
                )
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            title = inline_html(heading.group(2))
            if level == 1 and not seen_h1:
                output.append(
                    f'<div class="article-kicker">参考资料 {article_index}</div>'
                    f'<h1 id="article-{article_index}">{title}</h1>'
                )
                if translator_note:
                    output.append(
                        f'<blockquote class="translator-note">{inline_html(translator_note)}</blockquote>'
                    )
                seen_h1 = True
            else:
                output.append(f"<h{level}>{title}</h{level}>")
            index += 1
            continue
        if stripped == "---":
            flush_paragraph()
            output.append("<hr>")
            index += 1
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip()[1:].strip())
                index += 1
            output.append(f"<blockquote>{inline_html(' '.join(quote))}</blockquote>")
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            flush_paragraph()
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            output.append(render_table(table_lines))
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        numbered = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if bullet or numbered:
            flush_paragraph()
            ordered = numbered is not None
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while index < len(lines):
                current = lines[index]
                match = (
                    re.match(r"^\s*(\d+)\.\s+(.+)$", current)
                    if ordered
                    else re.match(r"^\s*[-*]\s+(.+)$", current)
                )
                if not match:
                    break
                items.append(match.group(2) if ordered else match.group(1))
                index += 1
            output.append(f"<{tag}>" + "".join(f"<li>{inline_html(item)}</li>" for item in items) + f"</{tag}>")
            continue
        paragraph.append(line)
        index += 1
    flush_paragraph()
    output.append("</article>")
    return "\n".join(output)


CSS = r"""
@page { size: 182mm 257mm; margin: 16mm 15mm 17mm 15mm; }
* { box-sizing: border-box; }
html { background: #fff; }
body {
  margin: 0; color: #22272c; font-family: "SimSun", "Songti SC", serif;
  font-size: 9.4pt; line-height: 1.68; text-align: justify;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.article { break-before: page; }
.article:first-child { break-before: auto; }
.article-kicker {
  margin-top: 18mm; color: #71889a; font-family: "SimHei", "Heiti SC", sans-serif;
  font-size: 9pt; letter-spacing: .16em; text-align: center;
}
h1, h2, h3, h4, h5, h6 {
  font-family: "SimHei", "Heiti SC", sans-serif; color: #233f58;
  text-align: left; break-after: avoid; page-break-after: avoid;
}
h1 {
  margin: 6mm 0 12mm; font-size: 22pt; line-height: 1.35; text-align: center;
  padding-bottom: 5mm; border-bottom: 1.2pt solid #91a8ba;
}
h2 { margin: 8mm 0 3.5mm; font-size: 15pt; line-height: 1.4; }
h3 { margin: 6mm 0 2.5mm; font-size: 11.5pt; line-height: 1.45; color: #3e607a; }
h4 { margin: 4mm 0 2mm; font-size: 10pt; color: #536f84; }
p { margin: 0 0 3.5mm; orphans: 2; widows: 2; }
strong { color: #172f43; }
em { color: #3e4c57; }
a, .local-link { color: #315d86; text-decoration: none; }
code {
  font-family: "SFMono-Regular", Menlo, Consolas, "SimHei", monospace;
  font-size: .88em; color: #7a3152; background: #f3f5f6; padding: .05em .22em;
  border-radius: 2px;
}
pre.code-block {
  margin: 3mm 0 4.5mm; padding: 3.2mm 3.6mm; border: .5pt solid #d2dbe1;
  border-radius: 3px; background: #f6f7f8; color: #26333d;
  font: 6.5pt/1.5 "SFMono-Regular", Menlo, Consolas, "SimHei", monospace;
  white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word;
  break-inside: avoid-page; text-align: left;
}
pre.code-block code { padding: 0; background: transparent; color: inherit; }
blockquote {
  margin: 3mm 0 5mm; padding: 3mm 4mm; color: #3e4f5b; background: #f1f6f8;
  border-left: 2.3pt solid #86a2b7; break-inside: avoid-page;
}
blockquote.translator-note {
  margin-top: -5mm; margin-bottom: 7mm; font-size: 7.7pt; line-height: 1.5;
  color: #5a6d7a; background: #f5f7f8; border-left-color: #a6b6c1;
}
ul, ol { margin: 1.5mm 0 4mm; padding-left: 6mm; }
li { margin: 0 0 1.2mm; }
hr { border: 0; border-top: .55pt solid #d5dce2; margin: 6mm 0; }
.diagram {
  margin: 4mm 0 2mm; padding: 2mm; text-align: center; background: #fff;
  break-inside: avoid-page; page-break-inside: avoid;
}
.diagram svg { display: block; margin: 0 auto; max-width: 100% !important; width: 100%; height: auto !important; max-height: 178mm; }
p.caption {
  margin: 1.5mm 4mm 5mm; color: #5a7080; font-size: 7.7pt; line-height: 1.55;
  text-align: left; break-before: avoid; page-break-before: avoid;
}
.table-wrap { margin: 3mm 0 5mm; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 6.7pt; line-height: 1.42; }
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
th, td { border: .45pt solid #cbd4da; padding: 1.4mm 1.5mm; vertical-align: top; overflow-wrap: anywhere; }
th { background: #3d5972; color: white; font-family: "SimHei", sans-serif; text-align: left; }
tbody tr:nth-child(even) { background: #f5f7f8; }
"""


def make_body_html() -> None:
    articles = []
    for index, (slug, _) in enumerate(ARTICLES, 1):
        source = COLLECTION / slug / "translation-zh.md"
        articles.append(markdown_to_html(source.read_text(encoding="utf-8"), index))
    mermaid_uri = MERMAID_JS.resolve().as_uri()
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Claude Code 源码解析中文参考合订本</title>
<style>{CSS}</style></head><body>
{''.join(articles)}
<script src="{mermaid_uri}"></script>
<script>
mermaid.initialize({{startOnLoad: false, securityLevel: 'loose', theme: 'neutral'}});
mermaid.run({{querySelector: '.mermaid'}}).then(() => {{
  document.body.dataset.mermaidReady = 'true';
}}).catch((error) => {{
  document.body.dataset.mermaidError = String(error);
}});
</script></body></html>"""
    BODY_HTML.write_text(document, encoding="utf-8")


def ensure_mermaid() -> None:
    if MERMAID_JS.exists() and MERMAID_JS.stat().st_size > 1_000_000:
        return
    print(f"Downloading Mermaid runtime: {MERMAID_URL}", flush=True)
    request = urllib.request.Request(MERMAID_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        MERMAID_JS.write_bytes(response.read())


def print_body() -> None:
    command = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=30000",
        "--no-pdf-header-footer",
        f"--print-to-pdf={BODY_PDF}",
        BODY_HTML.resolve().as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not BODY_PDF.exists():
        raise RuntimeError(f"Chrome PDF build failed: {result.stderr[-2000:]}")


def locate_article_pages() -> list[int]:
    starts: list[int] = []
    with pdfplumber.open(BODY_PDF) as document:
        page_text = [(page.extract_text() or "").replace(" ", "") for page in document.pages]
    search_from = 0
    for article_index, (_, title) in enumerate(ARTICLES, 1):
        # Article titles can also occur in "next article" links at the end of
        # the preceding chapter. The generated kicker is unique and therefore
        # a more reliable page-start marker.
        compact = f"参考资料{article_index}"
        found = None
        for page_index in range(search_from, len(page_text)):
            if compact in page_text[page_index]:
                found = page_index
                break
        if found is None:
            raise ValueError(f"Article title was not found in body PDF: {title}")
        starts.append(found)
        search_from = found + 1
    return starts


def register_fonts() -> None:
    if not BODY_FONT.exists() or not HEADING_FONT.exists():
        raise FileNotFoundError("SimSun.ttf or SimHei.ttf is missing from ~/Library/Fonts")
    pdfmetrics.registerFont(TTFont("HiroSerif", str(BODY_FONT)))
    pdfmetrics.registerFont(TTFont("HiroSans", str(HEADING_FONT)))


class FrontDoc(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=PAGE_SIZE,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, 0, 0, 0, 0)
        self.addPageTemplates(PageTemplate(id="front", frames=[frame]))


def make_front(body_starts: list[int], body_pages: int) -> int:
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "front-base",
        parent=styles["BodyText"],
        fontName="HiroSerif",
        fontSize=9.5,
        leading=15,
        textColor=colors.HexColor("#263039"),
        wordWrap="CJK",
    )
    title = ParagraphStyle(
        "front-title",
        parent=base,
        fontName="HiroSans",
        fontSize=25,
        leading=35,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#233F58"),
        spaceAfter=8 * mm,
    )
    subtitle = ParagraphStyle(
        "front-subtitle",
        parent=base,
        fontName="HiroSans",
        fontSize=11,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5C7486"),
    )
    contents_title = ParagraphStyle(
        "contents-title",
        parent=title,
        fontSize=20,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=7 * mm,
    )
    row_style = ParagraphStyle(
        "contents-row",
        parent=base,
        fontName="HiroSans",
        fontSize=9.2,
        leading=14,
        textColor=colors.HexColor("#304B61"),
    )
    note = ParagraphStyle(
        "front-note",
        parent=base,
        fontSize=8.2,
        leading=13,
        textColor=colors.HexColor("#60717D"),
    )

    # The front matter is intentionally fixed to two pages. Body page numbers
    # therefore begin at 3 in the final anthology.
    body_offset = 2
    story = [
        Spacer(1, 40 * mm),
        Paragraph("Claude Code 源码解析", title),
        Paragraph("中文参考合订本", title),
        HRFlowable(width="42%", color=colors.HexColor("#8AA4B8"), thickness=1.1),
        Spacer(1, 10 * mm),
        Paragraph("八篇第三方源码分析文章·完整中文翻译", subtitle),
        Spacer(1, 47 * mm),
        Paragraph("基于 2026-08-12 抓取页面整理", subtitle),
        Paragraph("原文分析快照：Claude Code v2.1.88 Source Map", subtitle),
        PageBreak(),
        Paragraph("目录", contents_title),
    ]
    rows = []
    for index, ((_, article_title), body_page) in enumerate(zip(ARTICLES, body_starts), 1):
        final_page = body_offset + body_page + 1
        rows.append(
            [
                Paragraph(f"{index:02d}", row_style),
                Paragraph(article_title, row_style),
                Paragraph(str(final_page), row_style),
            ]
        )
    table = Table(rows, colWidths=[12 * mm, 118 * mm, 12 * mm], rowHeights=12 * mm)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6DEE3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 8 * mm),
            Paragraph(
                "说明：本文档保留原文的代码、表格、图注、链接与 Mermaid 图。"
                "文件行数、工具数量和阈值属于相应页面快照，不应直接外推到其他 Claude Code 版本。",
                note,
            ),
            Spacer(1, 3 * mm),
            Paragraph(f"正文 {body_pages} 页；合订本共 {body_pages + body_offset} 页。", note),
        ]
    )
    FrontDoc(str(FRONT_PDF)).build(story)
    pages = len(PdfReader(str(FRONT_PDF)).pages)
    if pages != body_offset:
        raise ValueError(f"Front matter expected {body_offset} pages, got {pages}")
    return pages


def overlay_page(page_number: int, total_pages: int, running_title: str) -> PdfReader:
    packet = io.BytesIO()
    surface = canvas.Canvas(packet, pagesize=PAGE_SIZE)
    width, height = PAGE_SIZE
    if page_number > 1:
        surface.setStrokeColor(colors.HexColor("#D5DCE2"))
        surface.setLineWidth(0.45)
        surface.line(15 * mm, height - 11.8 * mm, width - 15 * mm, height - 11.8 * mm)
        surface.setFillColor(colors.HexColor("#667A88"))
        surface.setFont("HiroSans", 7.1)
        surface.drawString(15 * mm, height - 9.3 * mm, running_title)
        surface.drawRightString(width - 15 * mm, height - 9.3 * mm, "中文参考合订本")
        surface.drawCentredString(width / 2, 8.5 * mm, f"{page_number} / {total_pages}")
    surface.showPage()
    surface.save()
    packet.seek(0)
    return PdfReader(packet)


def merge_and_finish(front_pages: int, body_starts: list[int]) -> None:
    front = PdfReader(str(FRONT_PDF))
    body = PdfReader(str(BODY_PDF))
    pages = list(front.pages) + list(body.pages)
    total = len(pages)
    final_starts = [front_pages + page for page in body_starts]

    writer = PdfWriter()
    writer.add_metadata(
        {
            "/Title": "Claude Code 源码解析：中文参考合订本",
            "/Author": "Zhuoran Yang；中文翻译整理",
            "/Subject": "八篇 Claude Code 第三方源码分析文章完整中文翻译",
            "/Keywords": "Claude Code, Agent Loop, Prompt, Tool, Sandbox, Hooks",
        }
    )
    for page_index, page in enumerate(pages):
        article_title = "目录" if page_index == 1 else "Claude Code 源码解析"
        for start, (_, title) in zip(final_starts, ARTICLES):
            if page_index >= start:
                article_title = title
        overlay = overlay_page(page_index + 1, total, article_title).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)

    root_outline = writer.add_outline_item("Claude Code 源码解析：中文参考合订本", 0)
    writer.add_outline_item("目录", 1, parent=root_outline)
    for start, (_, title) in zip(final_starts, ARTICLES):
        writer.add_outline_item(title, start, parent=root_outline)
    writer.page_mode = "/UseOutlines"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as stream:
        writer.write(stream)


def verify(article_starts: list[int]) -> dict[str, object]:
    reader = PdfReader(str(OUTPUT))
    width = float(reader.pages[0].mediabox.width)
    height = float(reader.pages[0].mediabox.height)
    if abs(width - PAGE_SIZE[0]) > 1 or abs(height - PAGE_SIZE[1]) > 1:
        raise ValueError(f"Unexpected page size: {width} x {height}")
    with pdfplumber.open(OUTPUT) as document:
        texts = [(page.extract_text() or "") for page in document.pages]
    joined = "\n".join(texts)
    for _, title in ARTICLES:
        if title.replace(" ", "") not in joined.replace(" ", ""):
            raise ValueError(f"Missing article title in final PDF: {title}")
    mermaid_leaks = [token for token in ("flowchart LR", "flowchart TD", "%%{init:") if token in joined]
    if mermaid_leaks:
        raise ValueError(f"Mermaid source leaked into PDF: {mermaid_leaks}")
    nearly_blank = [index + 1 for index, value in enumerate(texts) if len(value.strip()) < 8]
    # The cover intentionally has little extractable text, but no other page may be blank.
    if any(page != 1 for page in nearly_blank):
        raise ValueError(f"Unexpected blank pages: {nearly_blank}")
    return {
        "output": str(OUTPUT),
        "pages": len(reader.pages),
        "page_width_pt": round(width, 2),
        "page_height_pt": round(height, 2),
        "article_body_starts": article_starts,
        "bytes": OUTPUT.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-html", action="store_true", help="reuse the existing body PDF")
    args = parser.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    logging.disable(logging.WARNING)
    register_fonts()
    if not args.skip_html:
        if not CHROME.exists():
            raise FileNotFoundError(f"Google Chrome not found: {CHROME}")
        ensure_mermaid()
        make_body_html()
        print_body()
    if not BODY_PDF.exists():
        raise FileNotFoundError(BODY_PDF)
    body_starts = locate_article_pages()
    body_pages = len(PdfReader(str(BODY_PDF)).pages)
    front_pages = make_front(body_starts, body_pages)
    merge_and_finish(front_pages, body_starts)
    result = verify([front_pages + value + 1 for value in body_starts])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
