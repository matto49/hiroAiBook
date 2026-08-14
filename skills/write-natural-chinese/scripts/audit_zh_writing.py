#!/usr/bin/env python3
"""中文写作启发式风格审校工具。

本脚本只提供复核线索，不检测 AI 作者身份，不计算所谓“AI 概率”，也不修改文件。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_SUFFIXES = {".md", ".markdown", ".tex", ".txt"}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str
    pattern: re.Pattern[str]
    suggestion: str


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule_id: str
    category: str
    severity: str
    excerpt: str
    suggestion: str


RULES = (
    Rule(
        "universal-opening",
        "结构",
        "medium",
        re.compile(r"(?:在|随着).{0,18}(?:快速发展|飞速发展|不断发展|日新月异).{0,12}(?:时代|背景|今天|当下)"),
        "考虑直接从具体问题、观察或冲突开始。",
    ),
    Rule(
        "inflated-significance",
        "证据",
        "high",
        re.compile(r"(?:里程碑式|划时代|前所未有|深远意义|新纪元|奠定了?坚实基础|注入了?新的活力)"),
        "用可核实的机制、结果和适用范围替代宏大评价。",
    ),
    Rule(
        "vague-authority",
        "证据",
        "high",
        re.compile(r"(?:有|相关|大量|多项)?研究表明|专家(?:指出|认为)|业内普遍认为|众所周知"),
        "检查是否给出可追溯来源及准确范围。",
    ),
    Rule(
        "empty-emphasis",
        "表达",
        "low",
        re.compile(r"值得注意的是|不难发现|毋庸置疑|显而易见|不可忽视的是"),
        "若后文事实本身足够清楚，删除提示语；否则补充证据。",
    ),
    Rule(
        "mechanical-sequence",
        "节奏",
        "medium",
        re.compile(r"首先.{0,80}其次.{0,80}(?:最后|再次|第三)"),
        "检查三段式是否来自真实结构，而不是为了整齐。",
    ),
    Rule(
        "forced-binary",
        "表达",
        "low",
        re.compile(r"不是.{1,45}而是|不仅.{1,45}(?:而且|更是|还)"),
        "对比确有澄清作用时保留，否则直接陈述核心判断。",
    ),
    Rule(
        "generic-conclusion",
        "结构",
        "medium",
        re.compile(r"综上所述|总而言之|未来可期|让我们拭目以待|具有广阔的?前景"),
        "让结尾回答开头的问题，并交代边界或真实未决点。",
    ),
    Rule(
        "chat-residue",
        "体裁",
        "high",
        re.compile(r"希望(?:以上|这些|这)对你有帮助|当然[，,]?(?:以下|这里|我可以)|如果你还需要"),
        "从交付正文中删除服务型对话残留。",
    ),
    Rule(
        "nominalized-action",
        "中文表达",
        "low",
        re.compile(r"(?:进行|实现|开展).{0,16}的(?:分析|研究|处理|优化|提升|构建|实现)"),
        "找回实际施动者和动作，减少抽象名词套叠。",
    ),
)

RULE_LABELS = {
    "universal-opening": "万能开场",
    "inflated-significance": "夸大意义",
    "vague-authority": "模糊权威",
    "empty-emphasis": "空洞强调",
    "mechanical-sequence": "机械三段式",
    "forced-binary": "强制二元对比",
    "generic-conclusion": "泛化结论",
    "chat-residue": "对话残留",
    "nominalized-action": "动作名词化",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扫描中文写作中的机械表达和证据风险；不是 AI 检测器。"
    )
    parser.add_argument("paths", nargs="+", type=Path, help="文件或目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="发现高风险（high）问题时返回退出码 1（默认始终返回 0）",
    )
    return parser.parse_args()


def iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for raw_path in paths:
        path = raw_path.resolve()
        if path.is_file():
            candidates = (path,)
        elif path.is_dir():
            candidates = sorted(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
            )
        else:
            print(f"警告：路径不存在：{raw_path}", file=sys.stderr)
            continue

        for candidate in candidates:
            if candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if candidate not in seen:
                seen.add(candidate)
                yield candidate


def visible_lines(text: str, suffix: str) -> Iterable[tuple[int, str]]:
    in_fence = False
    fence_mark = ""
    in_verbatim = False

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()

        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence and suffix in {".md", ".markdown"}:
            mark = fence.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_mark = mark
            elif mark == fence_mark:
                in_fence = False
                fence_mark = ""
            continue
        if in_fence:
            continue

        if suffix == ".tex":
            if re.search(r"\\begin\{(?:verbatim|lstlisting|minted)\}", line):
                in_verbatim = True
                continue
            if re.search(r"\\end\{(?:verbatim|lstlisting|minted)\}", line):
                in_verbatim = False
                continue
            if in_verbatim or stripped.startswith("%"):
                continue

        if stripped:
            yield line_no, line


def excerpt(line: str, start: int, width: int = 88) -> str:
    clean = re.sub(r"\s+", " ", line).strip()
    if len(clean) <= width:
        return clean
    left = max(0, start - width // 3)
    right = min(len(clean), left + width)
    prefix = "…" if left else ""
    suffix = "…" if right < len(clean) else ""
    return prefix + clean[left:right] + suffix


def scan_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"警告：文件不是 UTF-8 编码，已跳过：{path}", file=sys.stderr)
        return []

    findings: list[Finding] = []
    for line_no, line in visible_lines(text, path.suffix.lower()):
        for rule in RULES:
            match = rule.pattern.search(line)
            if match:
                findings.append(
                    Finding(
                        path=str(path),
                        line=line_no,
                        rule_id=rule.rule_id,
                        category=rule.category,
                        severity=rule.severity,
                        excerpt=excerpt(line, match.start()),
                        suggestion=rule.suggestion,
                    )
                )
    return findings


def print_text(findings: list[Finding], file_count: int) -> None:
    if not findings:
        print(f"已扫描 {file_count} 个文件：没有发现启发式信号。")
        print("这不能证明作者身份或文本质量。")
        return

    severity_order = {"high": 0, "medium": 1, "low": 2}
    severity_labels = {"high": "高", "medium": "中", "low": "低"}
    findings.sort(key=lambda item: (severity_order[item.severity], item.path, item.line))
    for item in findings:
        print(
            f"{item.path}:{item.line}: [{severity_labels[item.severity]}] "
            f"{RULE_LABELS[item.rule_id]}（{item.rule_id}，{item.category}）"
        )
        print(f"  {item.excerpt}")
        print(f"  建议：{item.suggestion}")

    totals = {level: 0 for level in ("high", "medium", "low")}
    for item in findings:
        totals[item.severity] += 1
    print(
        f"已扫描 {file_count} 个文件：发现 {len(findings)} 条信号"
        f"（高={totals['high']}，中={totals['medium']}，低={totals['low']}）。"
    )
    print("请结合上下文复核每条信号；这不是 AI 作者身份评分。")


def main() -> int:
    args = parse_args()
    files = list(iter_files(args.paths))
    findings = [finding for path in files for finding in scan_file(path)]

    if args.json:
        payload = {
            "disclaimer": "仅提供启发式风格信号，不检测 AI 作者身份。",
            "files_scanned": len(files),
            "findings": [asdict(item) for item in findings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(findings, len(files))

    if args.strict and any(item.severity == "high" for item in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
