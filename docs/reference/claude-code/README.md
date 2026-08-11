# Claude Code 多智能体参考索引

核对日期：2026-08-12

用途：为第三章《Claude Code 如何解决复杂问题》核对机制、版本边界和引用来源。

这份索引只公开来源导航和自写的阅读判断，不收录第三方文章全文、网页快照、原图、论文 PDF 或完整翻译。第三章正文见 [`chapters/ch03.tex`](../../../chapters/ch03.tex)，更完整的研究记录见 [`claude-code-multi-agent-research.md`](../../plan/claude-code-multi-agent-research.md)。

## 先分清三类材料

Claude Code 的产品行为会随版本改变。写作时，官方文档用于核对当前入口和能力边界；第三方图解文章适合建立讲解顺序；论文和源码分析则用来补足设计空间、失败模式与长期协作问题。三类材料不能互相替代。

### 官方文档

| 来源 | 适合核对的内容 |
| --- | --- |
| [Run agents in parallel](https://code.claude.com/docs/en/agents) | 并行智能体的产品入口和使用方式 |
| [Create custom subagents](https://code.claude.com/docs/en/sub-agents) | Subagent 的上下文、工具、权限与配置 |
| [Orchestrate teams of Claude Code sessions](https://code.claude.com/docs/en/agent-teams) | Agent Teams 的共享任务、消息和协作边界 |
| [Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees) | Worktree 的创建、隔离范围和清理方式 |
| [How Claude Code uses prompt caching](https://code.claude.com/docs/en/prompt-caching) | Prompt 缓存的工作条件和成本影响 |

官方文档适合回答“当前产品怎样使用”，但不会完整解释第三章采用的叙事结构。

### 第三方图解文章

| 编号 | 来源 | 在第三章中的作用 | 使用限制 |
| --- | --- | --- | --- |
| V1 | Avi Chawla, [*Claude Code's Architecture, Explained Visually!*](https://blog.dailydoseofds.com/p/claude-codes-architecture-explained) | 建立 Agent Harness 的整体视图 | 六层划分属于作者的讲解模型，不是官方架构 |
| V2 | Inside Claude Code, [*End-to-End Workflow*](https://y-agent.github.io/inside-claude-code/01-end-to-end-workflow.html) | 跟踪一次请求怎样进入 Agent Loop、调用工具并结束 | 文中的数字、文件名和阶段划分依赖作者分析的版本 |
| V3 | Inside Claude Code, [*Multi-Agent Orchestration*](https://y-agent.github.io/inside-claude-code/07-multi-agent-orchestration.html) | 解释 fork、fresh agent、角色、Worktree 与团队协作 | 不应把角色、上下文继承和文件隔离写成同一层概念 |

第三章借用了这些文章的读图方式，但所有示意图都按本文的认证故障案例重新绘制，没有直接复制原图。

### 论文与源码级分析

| 编号 | 来源 | 主要价值 |
| --- | --- | --- |
| P1 | Ziyu Xiong 等，[ *Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems*](https://arxiv.org/abs/2604.14228) | 从 Agent Loop、上下文、工具、安全和 Subagent 等方面补足系统性分析 |
| P2 | Edgar A. Duéñez-Guzmán 等，[ *Agent Team Work Zone: An Automated, Persistent Workspace for Long-Lived Claude Code Agent Teams*](https://arxiv.org/abs/2607.22917) | 讨论长期 Agent Team 的恢复、handoff、压缩丢失和持久状态 |

论文能支撑机制与失败模式，但同样不能替代当前产品文档。若论文描述的是源码快照或实验系统，正文应明确写出这一限定。

## 第三章怎样组合这些来源

| 第三章要回答的问题 | 主参考 | 补充核对 |
| --- | --- | --- |
| Claude Code 在模型调用前准备了什么 | V2、P1 | 官方 Prompt caching 文档 |
| 单个 Agent 怎样读取、执行并根据结果继续 | V2、P1 | V1 |
| 什么时候值得把旁支交给另一个智能体 | V3、P1 | 官方 Agents 与 Subagents 文档 |
| Subagent 与 Agent Teams 有什么不同 | 官方 Subagents、Agent Teams 文档 | V3、P2 |
| Worktree 隔离了什么，又没有隔离什么 | 官方 Worktrees 文档、V3 | P1 |
| 多个结果怎样重新汇合并接受验证 | P1、P2 | V2 |

这张表表示“哪个来源回答哪个问题”，不是论文排行榜，也不是推荐阅读顺序。

## 引用与版本规则

- 描述第三方观察到的实现时，使用“该文基于某版本分析”“作者观察到”等归属语。
- 工具数量、Prompt 大小、压缩阈值、默认模型、功能开关和成本比例都属于高漂移信息，发布前重新核对官方文档。
- Subagent、Agent Teams、Agent View、Worktree 和批量编排解决的是不同问题，不合并成一个“多智能体模式”。
- Worktree 主要隔离工作副本和分支，不会自动复制数据库、端口、缓存或外部服务。
- 图解文章适合说明关系；涉及精确行为时，至少再核对官方文档、论文或对应版本的源码分析。

## 仓库内的相关文件

- [`claude-code-multi-agent-research.md`](../../plan/claude-code-multi-agent-research.md)：来源分级、产品边界和实践建议。
- [`claude-code-multi-agent-article-outline.md`](../../plan/claude-code-multi-agent-article-outline.md)：第三章形成前的结构草案。
- [`chapters/ch03.tex`](../../../chapters/ch03.tex)：最终进入小册子的正文与重绘图表。

本机研究目录 `docs/claude code/` 仍可保存阅读用全文、翻译和图像，但这些第三方材料不进入公开 Git 历史。需要公开引用时，使用本页列出的原文链接。
