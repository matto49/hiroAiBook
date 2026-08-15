#!/usr/bin/env python3
"""Translate the archived Inside Claude Code articles into natural Chinese.

Code fences, inline code, URLs, and math are replaced with opaque placeholders
before translation and restored byte-for-byte afterwards. The script keeps
per-page progress so an interrupted run can resume safely.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/claude code/inside-claude-code-full-references"
PROGRESS = ROOT / "tmp/translations/inside-claude-code-full-references"
CLAUDE = Path("/opt/homebrew/bin/claude")

TITLE_ZH = {
    "02-agent-loop-query-engine": "Agent Loop 与查询引擎",
    "03-prompt-assembly": "Prompt 组装流水线",
    "04-context-compaction": "上下文压缩",
    "05-tool-system": "工具系统与注册表",
    "06-safety-sandbox": "安全与沙箱",
    "08-cli-commands-ui": "CLI、命令与终端界面",
    "09-auth-providers-flags": "认证、模型提供方与 Feature Flag",
    "11-hooks-lifecycle": "Hook 与生命周期",
}

TOKEN_RE = re.compile(r"ZXQ(?:FENCE|INLINE|URL|MATH|HTML)\d{4}QXZ")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')
    return values, text[end + 5 :].lstrip("\n")


def stash(pattern: re.Pattern[str], text: str, kind: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = f"ZXQ{kind}{len(values):04d}QXZ"
        values[token] = match.group(0)
        return token

    return pattern.sub(replace, text)


def mask_protected(text: str) -> tuple[str, dict[str, str]]:
    values: dict[str, str] = {}
    text = stash(re.compile(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", re.M | re.S), text, "FENCE", values)
    text = stash(re.compile(r"`+[^`\n]+?`+"), text, "INLINE", values)
    text = stash(re.compile(r"(?<=\]\()[^)\s]+(?=\))"), text, "URL", values)
    text = stash(re.compile(r"<https?://[^>]+>"), text, "URL", values)
    text = stash(re.compile(r"https?://[^\s)>]+"), text, "URL", values)
    text = stash(re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.S), text, "MATH", values)
    text = stash(re.compile(r"</?(?:sup|sub|br|i|b)(?:\s[^>]*)?>"), text, "HTML", values)
    return text, values


def restore(text: str, values: dict[str, str]) -> str:
    found = Counter(TOKEN_RE.findall(text))
    expected = Counter({token: 1 for token in values})
    missing = expected - found
    extra = found - expected
    repeated = {token: count for token, count in found.items() if count != 1}
    if missing or extra or repeated:
        raise ValueError(
            f"placeholder mismatch: missing={list(missing)[:8]} "
            f"extra={list(extra)[:8]} repeated={list(repeated.items())[:8]}"
        )
    for token, value in values.items():
        text = text.replace(token, value)
    return text


def placeholders_match(source_chunk: str, translated_chunk: str) -> bool:
    """Return whether a cached chunk still belongs to the current source split."""
    return Counter(TOKEN_RE.findall(source_chunk)) == Counter(TOKEN_RE.findall(translated_chunk))


def strip_outer_fence(text: str) -> str:
    text = text.strip()
    match = re.fullmatch(r"```(?:markdown)?\s*\n(.*)\n```", text, re.S)
    return match.group(1).strip() if match else text


def translation_prompt(masked_body: str, chunk_index: int, chunk_count: int) -> str:
    return f"""你正在翻译一篇 Claude Code 源码分析文章。请把下方英文 Markdown 完整翻译成简体中文，只输出译文，不写说明，也不要在外面包一层代码围栏。

这是全文按原顺序切出的第 {chunk_index}/{chunk_count} 段。只翻译当前提供的内容，不要自行补写前后文。

翻译要求：
1. 保留原文顺序、每一段信息、标题层级、列表层级、表格、引用和分隔线。不得摘要、删节、合并章节或补充原文没有的事实。
2. 所有形如 ZXQ...QXZ 的占位符必须逐字保留，位置不变，每个只出现一次。它们代表代码、命令、URL、公式或 HTML。
3. 表格逐格翻译，但列数、行数和 Markdown 管道符结构不变。
4. 技术术语保持稳定。Agent Loop、AsyncGenerator、ReAct、System Prompt、Tool、Hook、Token、Prompt Caching、Feature Flag 等可保留英文；第一次出现时可以给出简短中文解释。
5. 数字、版本、文件行数、阈值、百分比和例子严格保留，不得改写成新的口径。原文结论属于作者对 Claude Code v2.1.88 Source Map 的分析，不要扩大为当前所有版本的事实。
6. 中文要像作者在解释一个具体系统：写清动作、输入、输出、原因和代价。避免“值得注意的是”“关键洞见”“这不仅……更……”等空泛综述腔。
7. 原文的 How to read this diagram 段落要完整翻译，但直接说明图中节点、箭头和关系，不要每次机械地写“如何阅读这张图”。
8. 原文若用整段粗体、Not X but Y、密集破折号或夸张类比制造强调，可以改成克制的普通陈述，但不能删除其中的事实和推理。
9. 保留原作者的分析立场。不要虚构译者经历，也不要加入筱泽广角色对白。

待翻译正文：

{masked_body}
"""


def run_claude(prompt: str, slug: str) -> str:
    command = [
        str(CLAUDE),
        "-p",
        "--safe-mode",
        "--no-session-persistence",
        "--model",
        "sonnet",
        "--effort",
        "high",
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
        prompt,
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    deltas: list[str] = []
    final_result = ""
    last_report = 0
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("type") == "stream_event":
            event = item.get("event", {})
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                deltas.append(delta.get("text", ""))
                size = sum(map(len, deltas))
                if size - last_report >= 4000:
                    print(f"  {slug}: generated {size} chars", flush=True)
                    last_report = size
        elif item.get("type") == "result":
            final_result = item.get("result", "") or ""
    stderr = process.stderr.read() if process.stderr else ""
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"Claude exited {returncode}: {stderr[-2000:]}")
    text = "".join(deltas).strip()
    if not text:
        text = final_result.strip()
    if not text:
        raise RuntimeError(f"Claude returned no text: {stderr[-2000:]}")
    return strip_outer_fence(text)


def split_large_block(block: str, limit: int) -> list[str]:
    if len(block) <= limit:
        return [block]
    paragraphs = re.split(r"(\n{2,})", block)
    pieces: list[str] = []
    current = ""
    for part in paragraphs:
        if current and len(current) + len(part) > limit:
            pieces.append(current)
            current = ""
        if len(part) > limit:
            # Very long tables or prose paragraphs are kept line-aligned.
            for line in part.splitlines(keepends=True):
                if current and len(current) + len(line) > limit:
                    pieces.append(current)
                    current = ""
                current += line
        else:
            current += part
    if current:
        pieces.append(current)
    return pieces


def split_translation_chunks(masked: str, limit: int = 9000) -> list[str]:
    sections = re.split(r"(?=^##(?:#)?\s+)", masked, flags=re.M)
    units: list[str] = []
    for section in sections:
        if not section:
            continue
        if len(section) <= limit:
            units.append(section)
            continue
        subsections = re.split(r"(?=^###\s+)", section, flags=re.M)
        for subsection in subsections:
            if subsection:
                units.extend(split_large_block(subsection, limit))
    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) > limit:
            chunks.append(current.rstrip())
            current = ""
        current += unit
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def heading_signature(text: str) -> list[int]:
    return [len(mark) for mark, _ in re.findall(r"^(#{1,6})\s+(.+)$", text, re.M)]


def table_shapes(text: str) -> list[list[int]]:
    shapes: list[list[int]] = []
    current: list[int] = []
    for line in text.splitlines() + [""]:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            current.append(len(re.split(r"(?<!\\)\|", line.strip())) - 2)
        elif current:
            if any(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in line.split("|") if cell):
                pass
            shapes.append(current)
            current = []
    return shapes


def fenced_blocks(text: str) -> list[str]:
    return [match.group(0) for match in re.finditer(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", text, re.M | re.S)]


def validate(source: str, translated: str) -> None:
    errors: list[str] = []
    if heading_signature(source) != heading_signature(translated):
        errors.append("heading level/count mismatch")
    if fenced_blocks(source) != fenced_blocks(translated):
        errors.append("fenced code mismatch")
    if table_shapes(source) != table_shapes(translated):
        errors.append("table row/column mismatch")
    source_targets = re.findall(r"\]\(([^)]+)\)", source)
    translated_targets = re.findall(r"\]\(([^)]+)\)", translated)
    if source_targets != translated_targets:
        errors.append("link target mismatch")
    source_inline = re.findall(r"`+[^`\n]+?`+", source)
    translated_inline = re.findall(r"`+[^`\n]+?`+", translated)
    # Natural Chinese may reverse two inline-code items within one sentence.
    # Require identical values and multiplicities, not identical prose order.
    if Counter(source_inline) != Counter(translated_inline):
        errors.append("inline code mismatch")
    if len(translated) < len(source) * 0.42:
        errors.append("translation appears too short")
    if errors:
        raise ValueError("; ".join(errors))


def frontmatter(slug: str, metadata: dict[str, str]) -> str:
    title_en = metadata.get("title", slug)
    return (
        "---\n"
        f'title: "{TITLE_ZH[slug]}"\n'
        f'original_title: "{title_en}"\n'
        f'author: "{metadata.get("author", "Zhuoran Yang")}"\n'
        f'source_url: "{metadata.get("source_url", "")}"\n'
        'source_retrieved: "2026-08-12"\n'
        'translated: "2026-08-12"\n'
        'language: "zh-CN"\n'
        'scope: "complete Chinese translation for local research"\n'
        "---\n\n"
        "> 译者说明：本文按 2026-08-12 抓取的网页完整翻译，保留原始章节、代码、表格、Mermaid 图源、图注和链接。原文分析基于 Claude Code v2.1.88 的 Source Map；文件行数、工具数量、阈值和实现细节属于该页面快照，不应直接外推到其他版本。\n\n"
    )


def translate_page(slug: str, force: bool = False) -> None:
    page = ARCHIVE / slug
    source_path = page / "source.md"
    target_path = page / "translation-zh.md"
    if target_path.exists() and not force:
        print(f"Skipping {slug}: translation already exists", flush=True)
        return
    metadata, body = split_frontmatter(source_path.read_text(encoding="utf-8"))
    masked, values = mask_protected(body)
    chunks = split_translation_chunks(masked)
    print(
        f"Translating {slug}: source={len(body)} chars, "
        f"protected={len(values)}, model_input={len(masked)} chars, chunks={len(chunks)}",
        flush=True,
    )
    started = time.monotonic()
    progress_dir = PROGRESS / slug
    progress_dir.mkdir(parents=True, exist_ok=True)
    translated_chunks: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        progress_path = progress_dir / f"chunk-{index:03d}.md"
        translated_chunk = ""
        if progress_path.exists() and not force:
            cached_chunk = progress_path.read_text(encoding="utf-8").strip()
            if placeholders_match(chunk, cached_chunk):
                translated_chunk = cached_chunk
                print(f"  {slug}: resumed chunk {index}/{len(chunks)}", flush=True)
            else:
                print(
                    f"  {slug}: source boundary changed; regenerating chunk "
                    f"{index}/{len(chunks)}",
                    flush=True,
                )
        if not translated_chunk:
            label = f"{slug} {index}/{len(chunks)}"
            translated_chunk = run_claude(
                translation_prompt(chunk, index, len(chunks)), label
            )
            progress_path.write_text(translated_chunk.strip() + "\n", encoding="utf-8")
            print(f"  {slug}: completed chunk {index}/{len(chunks)}", flush=True)
        chunk_tokens = TOKEN_RE.findall(chunk)
        chunk_values = {token: values[token] for token in chunk_tokens}
        translated_chunks.append(restore(translated_chunk, chunk_values).strip())
    translated = "\n\n".join(translated_chunks)
    validate(body, translated)
    target_path.write_text(frontmatter(slug, metadata) + translated.strip() + "\n", encoding="utf-8")
    print(
        f"Completed {slug}: output={len(translated)} chars, "
        f"elapsed={time.monotonic() - started:.1f}s",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slugs", nargs="*", choices=sorted(TITLE_ZH))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    slugs = args.slugs or list(TITLE_ZH)
    for slug in slugs:
        translate_page(slug, force=args.force)


if __name__ == "__main__":
    main()
