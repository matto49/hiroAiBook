#!/usr/bin/env python3
"""Archive the full pages referenced by the End-to-End Workflow article.

The output is a local research archive. Each page keeps the original HTML and
also gets a searchable Markdown rendering with headings, code, tables, Mermaid
sources, captions, and ordinary images.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://y-agent.github.io/inside-claude-code/"
OUTPUT = ROOT / "docs/claude code/inside-claude-code-full-references"

PAGES = [
    {
        "slug": "02-agent-loop-query-engine",
        "title": "Agent Loop & Query Engine",
        "reason": "完整的 Agent Loop 架构",
    },
    {
        "slug": "03-prompt-assembly",
        "title": "Prompt Assembly Pipeline",
        "reason": "完整的 Prompt 片段分类和组装流水线",
    },
    {
        "slug": "04-context-compaction",
        "title": "Context Compaction",
        "reason": "完整的上下文压缩机制",
    },
    {
        "slug": "05-tool-system",
        "title": "Tool System & Registry",
        "reason": "工具结果截断、工具注册表和执行流水线",
    },
    {
        "slug": "06-safety-sandbox",
        "title": "Safety & Sandbox",
        "reason": "完整的权限流水线和沙箱实现",
    },
    {
        "slug": "08-cli-commands-ui",
        "title": "CLI, Commands & Terminal UI",
        "reason": "完整的启动序列和终端渲染架构",
    },
    {
        "slug": "09-auth-providers-flags",
        "title": "Auth, Providers & Feature Flags",
        "reason": "配置、认证和 Feature Flag 系统",
    },
    {
        "slug": "11-hooks-lifecycle",
        "title": "Hooks & Lifecycle",
        "reason": "Stop Hook 的实现和生命周期机制",
    },
]


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)


class TreeParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def classes(node: Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def find(node: Node, predicate) -> Node | None:
    if predicate(node):
        return node
    for child in node.children:
        if isinstance(child, Node):
            result = find(child, predicate)
            if result:
                return result
    return None


def walk(node: Node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from walk(child)


def text_content(node: Node) -> str:
    parts: list[str] = []
    for child in node.children:
        parts.append(child if isinstance(child, str) else text_content(child))
    return "".join(parts)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def safe_name(value: str) -> str:
    value = urllib.parse.unquote(value).split("?")[0].split("#")[0]
    name = Path(value).name or "image"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
    return name[:160]


class MarkdownRenderer:
    SKIP = {"script", "style", "nav", "button", "svg", "noscript"}

    def __init__(self, page_url: str, image_map: dict[str, str]) -> None:
        self.page_url = page_url
        self.image_map = image_map

    def inline(self, item: Node | str) -> str:
        if isinstance(item, str):
            # Keep one boundary space around inline tags. Quarto often emits
            # "Query <span>Engine</span>"; stripping child text would turn it
            # into "QueryEngine" in the Markdown copy.
            return re.sub(r"\s+", " ", item)
        if item.tag in self.SKIP or "anchorjs-link" in classes(item):
            return ""
        inner = "".join(self.inline(child) for child in item.children)
        if item.tag in {"strong", "b"}:
            return f"**{inner.strip()}**"
        if item.tag in {"em", "i"}:
            return f"*{inner.strip()}*"
        if item.tag == "code":
            code = text_content(item).strip()
            fence = "``" if "`" in code else "`"
            return f"{fence}{code}{fence}"
        if item.tag == "a":
            label = compact_text(inner) or item.attrs.get("href", "")
            href = urllib.parse.urljoin(self.page_url, item.attrs.get("href", ""))
            return f"[{label}]({href})" if href else label
        if item.tag == "br":
            return "  \n"
        if item.tag == "img":
            src = item.attrs.get("src", "")
            alt = item.attrs.get("alt", "")
            target = self.image_map.get(src, urllib.parse.urljoin(self.page_url, src))
            return f"![{alt}]({target})"
        if item.tag == "sup":
            return f"<sup>{inner.strip()}</sup>"
        if item.tag == "sub":
            return f"<sub>{inner.strip()}</sub>"
        return inner

    def list_item(self, node: Node, marker: str, indent: int = 0) -> str:
        lead: list[Node | str] = []
        nested: list[Node] = []
        for child in node.children:
            if isinstance(child, Node) and child.tag in {"ul", "ol"}:
                nested.append(child)
            else:
                lead.append(child)
        line = compact_text("".join(self.inline(child) for child in lead))
        output = " " * indent + marker + " " + line + "\n"
        for child in nested:
            output += self.render_list(child, indent + 2)
        return output

    def render_list(self, node: Node, indent: int = 0) -> str:
        output = ""
        number = 1
        for child in node.children:
            if isinstance(child, Node) and child.tag == "li":
                marker = "-" if node.tag == "ul" else f"{number}."
                output += self.list_item(child, marker, indent)
                number += 1
        return output + "\n"

    def render_table(self, node: Node) -> str:
        rows: list[list[str]] = []
        for row in walk(node):
            if row.tag != "tr":
                continue
            cells = []
            for child in row.children:
                if isinstance(child, Node) and child.tag in {"th", "td"}:
                    value = compact_text(self.inline(child)).replace("|", "\\|")
                    cells.append(value)
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        width = max(map(len, rows))
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines) + "\n\n"

    def render(self, node: Node) -> str:
        if node.tag in self.SKIP:
            return ""
        if node.tag == "header" and "quarto-title-block" in classes(node):
            heading = find(node, lambda item: item.tag == "h1")
            return self.render(heading) if heading else ""
        if re.fullmatch(r"h[1-6]", node.tag):
            level = int(node.tag[1])
            title = compact_text(self.inline(node))
            anchor = node.attrs.get("id", "")
            prefix = f'<a id="{anchor}"></a>\n' if anchor else ""
            return f"{prefix}{'#' * level} {title}\n\n"
        if node.tag == "p":
            value = compact_text(self.inline(node))
            # A few upstream pages contain literal Markdown headings at the
            # end of a <p> element (for example, "...host. ### Heading").
            # Restore the intended block boundary in the searchable copy.
            value = re.sub(r"\s+(#{2,6}\s+)", r"\n\n\1", value)
            return value + "\n\n" if value else ""
        if node.tag == "pre":
            value = text_content(node).strip("\n")
            if "mermaid" in classes(node):
                language = "mermaid"
            else:
                code = find(node, lambda item: item.tag == "code")
                language = ""
                if code:
                    for name in classes(code):
                        if name.startswith("language-"):
                            language = name.removeprefix("language-")
                            break
            fence = "````" if "```" in value else "```"
            return f"{fence}{language}\n{value}\n{fence}\n\n"
        if node.tag in {"ul", "ol"}:
            return self.render_list(node)
        if node.tag == "table":
            return self.render_table(node)
        if node.tag == "blockquote":
            value = "".join(self.render(child) if isinstance(child, Node) else child for child in node.children)
            return "\n".join("> " + line if line else ">" for line in value.strip().splitlines()) + "\n\n"
        if node.tag == "hr":
            return "---\n\n"
        if node.tag == "figcaption":
            value = compact_text(self.inline(node))
            return f"*{value}*\n\n" if value else ""
        if node.tag == "img":
            return self.inline(node) + "\n\n"
        if node.tag == "details":
            summary = find(node, lambda item: item.tag == "summary")
            title = compact_text(self.inline(summary)) if summary else "补充内容"
            body = "".join(
                self.render(child) if isinstance(child, Node) else ""
                for child in node.children
                if child is not summary
            )
            return f"**{title}**\n\n{body}"
        return "".join(self.render(child) if isinstance(child, Node) else "" for child in node.children)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 local research archiver"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def download_images(main: Node, page_url: str, assets_dir: Path) -> dict[str, str]:
    image_map: dict[str, str] = {}
    assets_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    for node in walk(main):
        if node.tag != "img" or not node.attrs.get("src"):
            continue
        src = node.attrs["src"]
        if src.startswith("data:"):
            continue
        image_url = urllib.parse.urljoin(page_url, src)
        name = safe_name(src)
        base, suffix = Path(name).stem, Path(name).suffix
        counter = 2
        while name in used:
            name = f"{base}-{counter}{suffix}"
            counter += 1
        used.add(name)
        target = assets_dir / name
        target.write_bytes(fetch(image_url))
        image_map[src] = f"assets/{name}"
    if not any(assets_dir.iterdir()):
        assets_dir.rmdir()
    return image_map


def clean_markdown(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip() + "\n"


def page_stats(markdown: str) -> dict[str, int]:
    return {
        "characters": len(markdown),
        "headings": len(re.findall(r"^#{1,6} ", markdown, re.M)),
        "code_blocks": len(re.findall(r"^```+[^\n]*$", markdown, re.M)) // 2,
        "mermaid_blocks": len(re.findall(r"^```mermaid$", markdown, re.M)),
        "tables": len(re.findall(r"^\| ---", markdown, re.M)),
        "images": len(re.findall(r"^!\[", markdown, re.M)),
    }


def archive_page(item: dict[str, str]) -> dict[str, object]:
    slug = item["slug"]
    page_url = urllib.parse.urljoin(BASE_URL, f"{slug}.html")
    page_dir = OUTPUT / slug
    # Translations are editorial work, not generated archive data. Preserve
    # them when refreshing the upstream HTML and Markdown snapshot.
    translation = None
    translation_path = page_dir / "translation-zh.md"
    if translation_path.exists():
        translation = translation_path.read_bytes()
    if page_dir.exists():
        shutil.rmtree(page_dir)
    page_dir.mkdir(parents=True)
    if translation is not None:
        (page_dir / "translation-zh.md").write_bytes(translation)

    raw = fetch(page_url)
    (page_dir / "source.html").write_bytes(raw)
    parser = TreeParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    main = find(parser.root, lambda node: node.tag == "main" and node.attrs.get("id") == "quarto-document-content")
    if not main:
        raise RuntimeError(f"Article body not found: {page_url}")

    image_map = download_images(main, page_url, page_dir / "assets")
    body = clean_markdown(MarkdownRenderer(page_url, image_map).render(main))
    frontmatter = (
        "---\n"
        f'title: "{item["title"]}"\n'
        'author: "Zhuoran Yang"\n'
        f'source_url: "{page_url}"\n'
        f'retrieved: "{date.today().isoformat()}"\n'
        'scope: "complete article body for local research"\n'
        "---\n\n"
    )
    markdown = frontmatter + body
    (page_dir / "source.md").write_text(markdown, encoding="utf-8")
    stats = page_stats(markdown)
    return {
        **item,
        "source_url": page_url,
        "local_markdown": f"{slug}/source.md",
        "local_html": f"{slug}/source.html",
        "sha256": hashlib.sha256(raw).hexdigest(),
        **stats,
    }


def write_index(manifest: list[dict[str, object]]) -> None:
    lines = [
        "# End-to-End Workflow 引用页完整归档",
        "",
        "这份资料包收录《端到端工作流》中以“完整……见……”明确指向的八篇文章。每篇保留原始 HTML，另提供便于检索和翻译的 Markdown。代码、表格、Mermaid 图源、普通图片、标题锚点和原始链接均保留。",
        "",
        "> 仅供本地研究。原文版权属于 Zhuoran Yang；不要把这批网页全文直接提交到公开仓库。页面分析基于 Claude Code v2.1.88 的 Source Map，版本相关数字不能直接外推。",
        "",
        "> 抓取时的页面内容与现有《端到端工作流》译稿并非完全同一快照。例如，部分补充页已经使用 `250+ fragments` 等新表述，而旧译稿仍写 `65+ fragments`。后续整合应逐项标注来源页面和抓取日期，不要直接混用数字。",
        "",
        "## 页面索引",
        "",
        "| 主文引用 | 页面 | 英文存档 | 中文全译 | 规模 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in manifest:
        scale = (
            f'{item["characters"]} 字符，{item["headings"]} 个标题，'
            f'{item["code_blocks"]} 个代码块，{item["tables"]} 张表，'
            f'{item["mermaid_blocks"]} 张 Mermaid 图'
        )
        lines.append(
            f'| {item["reason"]} | [{item["title"]}]({item["source_url"]}) | '
            f'[{item["slug"]}/source.md]({item["slug"]}/source.md) | '
            f'[{item["slug"]}/translation-zh.md]({item["slug"]}/translation-zh.md) | {scale} |'
        )
    lines += [
        "",
        "## 文件约定",
        "",
        "- `source.html`：抓取时的原始网页，用于核对版式、锚点和未被转换器覆盖的结构。",
        "- `source.md`：正文级转换稿，用于全文搜索、翻译和后续 PDF 排版。",
        "- `translation-zh.md`：完整中文译稿，保留原文结构、代码、表格、Mermaid 图源、链接和数字口径。",
        "- `assets/`：页面中的普通图片；Mermaid 图以代码块形式保留在 `source.md`。",
        "- `manifest.json`：来源 URL、抓取日期、原始 HTML 哈希和内容计数。",
        "",
        "## 暂不纳入本批的链接",
        "",
        "系列导航中的 Multi-Agent 与 MCP 属于延伸阅读，并非正文中的“完整机制见”引用。Multi-Agent 已在 `visual-articles/multi-agent-orchestration/` 单独归档；MCP 可在整合扩展章节时另行收集。",
        "",
    ]
    (OUTPUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (OUTPUT / "manifest.json").write_text(
        json.dumps({"retrieved": date.today().isoformat(), "pages": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for item in PAGES:
        print(f'Archiving {item["slug"]}...')
        manifest.append(archive_page(item))
    write_index(manifest)
    print(f"Archived {len(manifest)} pages under {OUTPUT}")


if __name__ == "__main__":
    main()
