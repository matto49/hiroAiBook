# Claude Code 图解文章译读资料库

本目录收录三篇第三方 Claude Code 图解文章的原文快照、中文全译、原图/流程图和 PDF。资料获取与翻译日期为 2026-08-02。

## 阅读入口

| 顺序 | 文章 | 适合解决的问题 | 中文译稿 | 图文 PDF |
| --- | --- | --- | --- | --- |
| 1 | *Claude Code's Architecture, Explained Visually!* | 先建立六层架构的整体视图 | [图解 Claude Code 架构](architecture-explained-visually/translation-zh.md) | [PDF](../../../output/pdf/claude-code-visual-articles/claude-code-architecture-explained-visually-zh.pdf) |
| 2 | *End-to-End Workflow* | 追踪一次请求经过的七个阶段 | [端到端工作流](end-to-end-workflow/translation-zh.md) | [PDF](../../../output/pdf/claude-code-visual-articles/claude-code-end-to-end-workflow-zh.pdf) |
| 3 | *Multi-Agent Orchestration* | 深入生成、隔离、通信、资源和结果汇总 | [多智能体编排](multi-agent-orchestration/translation-zh.md) | [PDF](../../../output/pdf/claude-code-visual-articles/claude-code-multi-agent-orchestration-zh.pdf) |

建议按上表顺序阅读：先回答“系统由什么组成”，再回答“一次请求怎样运行”，最后聚焦“一个智能体怎样变成多个智能体”。

## 内容总目录

### 1. 图解 Claude Code 架构

- Claude Code 为何不只是“模型加命令行”；
- 输入层、知识层、智能体层、集成层、可观测层、输出层；
- Agent loop、工具调用、Hooks、MCP、Skills、任务图、记忆和上下文压缩；
- Subagent 与 Agent Team 的视觉对照；
- 作者的实践提示与文末延伸阅读。

原文含 5 张图片，正文中的赞助内容和文末推广也按网页顺序保留。

### 2. 端到端工作流

- 引言：一个请求、七个阶段；
- 阶段 1：启动与输入；
- 阶段 2：组装 System Prompt；
- 阶段 3：Agent Loop；
- 阶段 4：工具执行；
- 阶段 5：权限与安全；
- 阶段 6：流式输出；
- 阶段 7：完成与持久化；
- 一次完整请求的合成追踪与系列导航。

原文含 5 张 Mermaid 流程图、2 个表格和 2 个代码块。

### 3. 多智能体编排

- 为什么需要多智能体，以及 `fork()` 心智模型；
- Fork 与全新智能体两条生成路径；
- Explore、Plan、Custom、Subagent、Teammate 五种类型；
- 不同类型的提示词组装与成本差异；
- Git worktree 隔离；
- Teammate 的持久化、命名、双向通信和团队内存；
- Coordinator Mode 的中心辐射式协作；
- Token 预算、模型选择、缓存复用与资源清理；
- 四层内存模型与“何时生成”决策。

原文含 6 张 Mermaid 图、4 个表格和 1 个代码块。

## 目录结构

```text
visual-articles/
├── README.md                         # 当前总目录
├── references.md                     # 主题—来源对应表与引用建议
├── architecture-explained-visually/
│   ├── source.html                   # 网页快照
│   ├── source.md                     # 可检索英文正文
│   ├── translation-zh.md             # 中文全译
│   └── assets/                       # 5 张原图与清单
├── end-to-end-workflow/
│   ├── source.html
│   ├── source.md
│   ├── translation-zh.md
│   └── assets/                       # 5 张 PNG + Mermaid 源码与清单
└── multi-agent-orchestration/
    ├── source.html
    ├── source.md
    ├── translation-zh.md
    └── assets/                       # 6 张 PNG + Mermaid 源码与清单
```

PDF 位于 `output/pdf/claude-code-visual-articles/`。网页正文抽取、流程图抓取和 PDF 构建脚本分别为：

- [`extract_visual_articles.py`](../../../scripts/extract_visual_articles.py)
- [`capture_visual_article_diagrams.mjs`](../../../scripts/capture_visual_article_diagrams.mjs)
- [`build_visual_article_pdfs.py`](../../../scripts/build_visual_article_pdfs.py)

## 与其他研究材料的关系

三篇图解文章负责“看懂运行方式”，另外两篇论文负责“补足源码证据和长期多智能体问题”：

- [《深入 Claude Code：当代与未来 AI 智能体系统的设计空间》中文译稿](../2604.14228v2-zh.md)
- [《Agent Team Work Zone》中文译稿](../2607.22917-zh.md)
- [Claude Code Multi-Agent 研究汇总](../../plan/claude-code-multi-agent-research.md)
- [已有文章大纲草案](../../plan/claude-code-multi-agent-article-outline.md)

具体怎样交叉引用，见 [references.md](references.md)。

## 版本与使用说明

- 这些文章属于第三方分析，不是 Anthropic 官方文档。
- *Inside Claude Code* 两篇文章明确基于 Claude Code v2.1.88 Source Map；函数名、功能开关、工具数量、Prompt 大小和运行阈值都可能随版本变化。
- 架构图中的工具数量、压缩阈值、Subagent 限制和 Worktree 行为同样属于作者发布时的描述。
- 译文保留原文说法；后续正式写作时，应把稳定的设计思想与易变化的实现细节分开，并对关键版本事实再次核验。
- 本资料库用于本地研究与写作。转载、公开分发译文或原图前，应另行确认原作者和站点的授权要求，并保留作者与原文链接。

