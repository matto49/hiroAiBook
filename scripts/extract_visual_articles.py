#!/usr/bin/env python3
"""Extract the three selected web articles into stable Markdown snapshots.

The script is deliberately source-specific: it preserves article order, code,
tables, links, figures, and Mermaid sources without pulling navigation chrome.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin

from lxml import etree, html


ROOT = Path("/Users/matto/github/person/hiroAiBook")
BASE = ROOT / "docs/claude code/visual-articles"

ARTICLES = [
    {
        "slug": "architecture-explained-visually",
        "html": Path("/private/tmp/claude-architecture-visually.html"),
        "url": "https://blog.dailydoseofds.com/p/claude-codes-architecture-explained",
        "title": "Claude Code's Architecture, Explained Visually!",
        "author": "Avi Chawla",
        "date": "2026-05-11",
        "root_xpath": '//div[contains(@class,"body") and contains(@class,"markup")]',
    },
    {
        "slug": "end-to-end-workflow",
        "html": Path("/private/tmp/claude-end-to-end.html"),
        "url": "https://y-agent.github.io/inside-claude-code/01-end-to-end-workflow.html",
        "title": "End-to-End Workflow",
        "author": "Zhuoran Yang",
        "date": "2026",
        "root_xpath": '//*[@id="quarto-document-content"]',
    },
    {
        "slug": "multi-agent-orchestration",
        "html": Path("/private/tmp/claude-multi-agent.html"),
        "url": "https://y-agent.github.io/inside-claude-code/07-multi-agent-orchestration.html",
        "title": "Multi-Agent Orchestration",
        "author": "Zhuoran Yang",
        "date": "2026",
        "root_xpath": '//*[@id="quarto-document-content"]',
    },
]

BLOCK_TAGS = {"h1", "h2", "h3", "h4", "p", "pre", "blockquote", "ul", "ol", "table", "figure", "hr"}


def clean_ws(text: str) -> str:
    text = html_lib.unescape(text)
    text = text.replace("\u00a0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", text)


def inline(node: etree._Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        tag = child.tag.lower() if isinstance(child.tag, str) else ""
        content = inline(child)
        if tag == "code":
            ticks = "``" if "`" in content else "`"
            content = f"{ticks}{content.strip()}{ticks}"
        elif tag in {"strong", "b"}:
            content = f"**{content.strip()}**"
        elif tag in {"em", "i"}:
            content = f"*{content.strip()}*"
        elif tag == "a":
            href = child.get("href") or ""
            content = f"[{content.strip()}]({href})" if href else content
        elif tag == "br":
            content = "\n"
        parts.append(content)
        if child.tail:
            parts.append(child.tail)
    return clean_ws("".join(parts)).strip()


def table_md(node: etree._Element) -> str:
    rows = []
    for tr in node.xpath(".//tr"):
        cells = [inline(c).replace("|", "\\|").replace("\n", " ") for c in tr.xpath("./th|./td")]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(map(len, rows))
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join(out)


def list_md(node: etree._Element, ordered: bool) -> str:
    out = []
    for i, li in enumerate(node.xpath("./li"), 1):
        text = inline(li).replace("\n", " ").strip()
        out.append(f"{i}. {text}" if ordered else f"- {text}")
    return "\n".join(out)


def original_image_url(img: etree._Element, page_url: str) -> str:
    attrs = img.get("data-attrs")
    if attrs:
        try:
            src = json.loads(attrs).get("src")
            if src:
                return src
        except json.JSONDecodeError:
            pass
    return urljoin(page_url, img.get("src") or "")


def is_nested_block(node: etree._Element, root: etree._Element) -> bool:
    parent = node.getparent()
    while parent is not None and parent is not root:
        tag = parent.tag.lower() if isinstance(parent.tag, str) else ""
        if tag in BLOCK_TAGS:
            return True
        parent = parent.getparent()
    return False


def extract(article: dict) -> dict:
    doc = html.parse(str(article["html"]))
    roots = doc.xpath(article["root_xpath"])
    if len(roots) != 1:
        raise RuntimeError(f"Expected one article root for {article['slug']}, found {len(roots)}")
    root = roots[0]
    out_dir = BASE / article["slug"]
    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(article["html"], out_dir / "source.html")

    lines = [
        "---",
        f'title: "{article["title"]}"',
        f'author: "{article["author"]}"',
        f'date: "{article["date"]}"',
        f'source_url: "{article["url"]}"',
        'retrieved: "2026-08-02"',
        "---",
        "",
        f"# {article['title']}",
        "",
        f"- Author: {article['author']}",
        f"- Source: <{article['url']}>",
        f"- Retrieved: 2026-08-02",
        "",
    ]
    image_manifest = []
    fig_index = 0
    seen_title = False

    xpath = ".//*[%s]" % " or ".join(f"self::{tag}" for tag in BLOCK_TAGS)
    for node in root.xpath(xpath):
        if is_nested_block(node, root):
            continue
        tag = node.tag.lower()
        block = ""
        if tag in {"h1", "h2", "h3", "h4"}:
            text = inline(node)
            if not text or (tag == "h1" and seen_title):
                continue
            if tag == "h1" and text == article["title"]:
                seen_title = True
                continue
            level = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}[tag]
            block = f"{'#' * level} {text}"
        elif tag == "p":
            block = inline(node)
        elif tag == "ul":
            block = list_md(node, False)
        elif tag == "ol":
            block = list_md(node, True)
        elif tag == "blockquote":
            text = "\n\n".join(inline(p) for p in node.xpath("./p") if inline(p)) or inline(node)
            block = "\n".join("> " + line for line in text.splitlines())
        elif tag == "table":
            block = table_md(node)
        elif tag == "hr":
            block = "---"
        elif tag == "pre":
            classes = node.get("class") or ""
            if "mermaid" not in classes:
                code = "".join(node.itertext()).strip("\n")
                lang = ""
                code_nodes = node.xpath(".//code")
                if code_nodes:
                    cls = code_nodes[0].get("class") or ""
                    match = re.search(r"sourceCode\s+([\w+-]+)|language-([\w+-]+)", cls)
                    if match:
                        lang = next(g for g in match.groups() if g)
                block = f"```{lang}\n{code}\n```"
        elif tag == "figure":
            fig_index += 1
            mermaid = node.xpath('.//pre[contains(concat(" ", normalize-space(@class), " "), " mermaid ")]')
            caption = " ".join(clean_ws(" ".join(node.xpath(".//figcaption//text()"))).split())
            if mermaid:
                label = mermaid[0].get("data-label") or f"figure-{fig_index:02d}"
                mmd_name = f"figure-{fig_index:02d}-{label}.mmd"
                png_name = f"figure-{fig_index:02d}-{label}.png"
                mmd_text = "".join(mermaid[0].itertext()).strip()
                (assets / mmd_name).write_text(mmd_text + "\n", encoding="utf-8")
                block = f"![{caption or label}](assets/{png_name})"
                image_manifest.append({"index": fig_index, "kind": "mermaid", "label": label, "file": png_name, "source": mmd_name, "caption": caption})
            else:
                imgs = node.xpath(".//img")
                if not imgs:
                    continue
                url = original_image_url(imgs[0], article["url"])
                suffix = Path(url.split("?", 1)[0]).suffix.lower() or ".png"
                if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    suffix = ".png"
                name = f"figure-{fig_index:02d}{suffix}"
                alt = imgs[0].get("alt") or caption or f"Original figure {fig_index}"
                block = f"![{alt}](assets/{name})"
                image_manifest.append({"index": fig_index, "kind": "image", "file": name, "url": url, "caption": caption, "alt": alt})
            if caption:
                block += f"\n\n*{caption}*"
        if block and block.strip():
            lines.extend([block.strip(), ""])

    (out_dir / "source.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (out_dir / "assets/manifest.json").write_text(json.dumps(image_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"slug": article["slug"], "blocks": len(lines), "figures": fig_index, "manifest": image_manifest}


def main() -> None:
    results = [extract(article) for article in ARTICLES]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
