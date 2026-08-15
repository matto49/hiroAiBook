# End-to-End Workflow 引用页完整归档

这份资料包收录《端到端工作流》中以“完整……见……”明确指向的八篇文章。每篇保留原始 HTML、便于检索的英文 Markdown，以及完整中文译稿。代码、表格、Mermaid 图源、普通图片、标题锚点和原始链接均保留。

> 仅供本地研究。原文版权属于 Zhuoran Yang；不要把这批网页全文直接提交到公开仓库。页面分析基于 Claude Code v2.1.88 的 Source Map，版本相关数字不能直接外推。

> 抓取时的页面内容与现有《端到端工作流》译稿并非完全同一快照。例如，部分补充页已经使用 `250+ fragments` 等新表述，而旧译稿仍写 `65+ fragments`。后续整合应逐项标注来源页面和抓取日期，不要直接混用数字。

## 中文合订本

[Claude Code 源码解析：中文参考合订本](../../../output/pdf/claude-code-inside-reference-zh.pdf)：JIS B5，137 页，收录八篇完整译稿、51 张 Mermaid 图、目录、页码和 PDF 书签。

## 页面索引

| 主文引用 | 页面 | 英文存档 | 中文全译 | 规模 |
| --- | --- | --- | --- | --- |
| 完整的 Agent Loop 架构 | [Agent Loop & Query Engine](https://y-agent.github.io/inside-claude-code/02-agent-loop-query-engine.html) | [source.md](02-agent-loop-query-engine/source.md) | [translation-zh.md](02-agent-loop-query-engine/translation-zh.md) | 46348 字符，9 个标题，12 个代码块，1 张表，7 张 Mermaid 图 |
| 完整的 Prompt 片段分类和组装流水线 | [Prompt Assembly Pipeline](https://y-agent.github.io/inside-claude-code/03-prompt-assembly.html) | [source.md](03-prompt-assembly/source.md) | [translation-zh.md](03-prompt-assembly/translation-zh.md) | 61229 字符，21 个标题，15 个代码块，6 张表，7 张 Mermaid 图 |
| 完整的上下文压缩机制 | [Context Compaction](https://y-agent.github.io/inside-claude-code/04-context-compaction.html) | [source.md](04-context-compaction/source.md) | [translation-zh.md](04-context-compaction/translation-zh.md) | 55230 字符，20 个标题，9 个代码块，18 张表，6 张 Mermaid 图 |
| 工具结果截断、工具注册表和执行流水线 | [Tool System & Registry](https://y-agent.github.io/inside-claude-code/05-tool-system.html) | [source.md](05-tool-system/source.md) | [translation-zh.md](05-tool-system/translation-zh.md) | 44437 字符，16 个标题，10 个代码块，6 张表，5 张 Mermaid 图 |
| 完整的权限流水线和沙箱实现 | [Safety & Sandbox](https://y-agent.github.io/inside-claude-code/06-safety-sandbox.html) | [source.md](06-safety-sandbox/source.md) | [translation-zh.md](06-safety-sandbox/translation-zh.md) | 31007 字符，10 个标题，7 个代码块，1 张表，6 张 Mermaid 图 |
| 完整的启动序列和终端渲染架构 | [CLI, Commands & Terminal UI](https://y-agent.github.io/inside-claude-code/08-cli-commands-ui.html) | [source.md](08-cli-commands-ui/source.md) | [translation-zh.md](08-cli-commands-ui/translation-zh.md) | 45442 字符，21 个标题，7 个代码块，5 张表，7 张 Mermaid 图 |
| 配置、认证和 Feature Flag 系统 | [Auth, Providers & Feature Flags](https://y-agent.github.io/inside-claude-code/09-auth-providers-flags.html) | [source.md](09-auth-providers-flags/source.md) | [translation-zh.md](09-auth-providers-flags/translation-zh.md) | 34993 字符，17 个标题，11 个代码块，5 张表，7 张 Mermaid 图 |
| Stop Hook 的实现和生命周期机制 | [Hooks & Lifecycle](https://y-agent.github.io/inside-claude-code/11-hooks-lifecycle.html) | [source.md](11-hooks-lifecycle/source.md) | [translation-zh.md](11-hooks-lifecycle/translation-zh.md) | 41939 字符，19 个标题，12 个代码块，6 张表，6 张 Mermaid 图 |

## 文件约定

- `source.html`：抓取时的原始网页，用于核对版式、锚点和未被转换器覆盖的结构。
- `source.md`：正文级转换稿，用于全文搜索、翻译和后续 PDF 排版。
- `translation-zh.md`：完整中文译稿，保留原文结构、代码、表格、Mermaid 图源、链接和数字口径。
- `assets/`：页面中的普通图片；Mermaid 图以代码块形式保留在 `source.md`。
- `manifest.json`：来源 URL、抓取日期、原始 HTML 哈希和内容计数。

## 暂不纳入本批的链接

系列导航中的 Multi-Agent 与 MCP 属于延伸阅读，并非正文中的“完整机制见”引用。Multi-Agent 已在 `visual-articles/multi-agent-orchestration/` 单独归档；MCP 可在整合扩展章节时另行收集。
