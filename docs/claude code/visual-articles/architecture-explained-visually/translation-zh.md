---
title: "图解 Claude Code 架构"
original_title: "Claude Code's Architecture, Explained Visually!"
author: "Avi Chawla"
date: "2026-05-11"
source_url: "https://blog.dailydoseofds.com/p/claude-codes-architecture-explained"
translated: "2026-08-02"
---

# 图解 Claude Code 架构

- 原题：*Claude Code's Architecture, Explained Visually!*
- 作者：Avi Chawla
- 原文：<https://blog.dailydoseofds.com/p/claude-codes-architecture-explained>
- 获取日期：2026-08-02

> 译者说明：本文按可获取网页正文的原始顺序完整翻译，保留赞助内容、文末推广、链接与五张原图。文中的工具数量、压缩阈值、Subagent 嵌套限制和 Worktree 行为属于作者在特定时间点的描述，不代表所有 Claude Code 版本；译文忠实保留原说法，后续写作时应另行核对官方文档。

### **[为 AI Agent 构建实时知识图谱](https://github.com/getzep/graphiti)**

![原文图 1](assets/figure-01.png)

RAG 无法跟上实时数据的变化速度。

**[Graphiti](https://github.com/getzep/graphiti)** 可以构建实时的双时态知识图谱，让你的 AI Agent 始终能够基于最新事实进行推理。它支持语义搜索、关键词搜索和图搜索。

完全开源，拥有 26,000 个 GitHub Star。

**[GitHub 仓库（别忘了点 Star）→](https://github.com/getzep/graphiti)**

[在 GitHub 上查看 Graphiti](https://github.com/getzep/graphiti)

---

### [图解 Claude Code 架构](https://www.dailydoseofds.com/p/the-anatomy-of-an-agent-harness/)

Claude Code 远不只是一个调用 Claude 模型的命令行工具。

实际系统包含六个层次，而模型只是循环中的一个节点。这张图拆解了其中的每个组件：

![原文图 2](assets/figure-02.png)

**输入层（Input Layer）**负责会话管理、权限门控和基于 YAML 的信任等级。在任何内容到达模型之前，都会先经过这一层。

**知识层（Knowledge Layer）**包含 Skill 注册表、上下文压缩器、任务图和跨会话记忆存储。模型权重之外的 Harness 智能就位于这里。

上下文压缩器采用五层级联结构，大约在上下文窗口达到 95% 容量时启动。它并不像 ChatGPT 那样简单总结对话，而是对文件路径、代码片段和错误历史进行结构化抽取，同时裁剪重复的工具输出。目标不只是让上下文变小，而是让它继续可用。

**执行层（Execution Layer）**通过带类型的注册表分派工具，每种工具都有自己的处理器，例如 Bash、Read、Write、Grep、Glob 和 Revert。

流式运行时负责并行执行；Prompt Cache 则复用稳定前缀，其成本约为原始处理成本的 10%。

**集成层（Integration Layer）**通过 MCP 运行时连接外部服务器，例如文件系统、Git 和自定义服务。工具向内注册，记忆则向外写入可以跨会话保存的 Markdown 文件 `agent_memory.md`。

**多 Agent 层（Multi-Agent Layer）**是最容易被低估的一层，而且它的工作方式与大多数人的想象非常不同。

Claude Code 支持两种层次的并行：Subagent 和 Agent Teams（**[这里有详细介绍](https://www.dailydoseofds.com/p/claude-subagents-vs-agent-teams/)**）。

![原文图 3](assets/figure-03.png)

- Subagent 是运行在当前会话内部的轻量 Worker。它们拥有自己的上下文窗口，执行聚焦的任务，例如搜索代码库或探索文件树，随后把结果返回给父 Agent。它们不能彼此通信，也不能生成自己的 Subagent。这是一种严格的父子层级。
- Agent Teams 更进一步。一个会话充当 Team Lead，并生成多个独立 Teammate；每位 Teammate 都作为完整的 Claude Code 实例运行，拥有自己的上下文窗口。Team Lead 会拆解任务、分配子任务并监控进度。

协调通过两种机制完成：保存在磁盘 JSON 文件中的共享任务列表，以及用于点对点消息传递的 Mailbox 系统。

每位 Teammate 都会获得 Git Worktree 隔离。它是一个单独的工作目录，拥有自己的分支，同时共享同一份仓库历史。

这意味着多个 Agent 可以修改代码库中重叠的区域，而不会立即产生文件冲突。任务完成后，没有改动的 Worktree 会被自动清理；包含改动的 Worktree 则保留下来，供人类审查后再合并。

**可观测性层（Observability Layer）**包裹着整个系统。带有生命周期 Hook 的事件总线会记录所有工具调用和消息，形成一份完整的 Agent 行动与决策审计轨迹。

后台执行器在守护线程中非阻塞运行，因此可观测性逻辑不会阻塞主循环。

---

主 Agent Loop 位于六层结构的中心，而且被有意设计得非常简单。它组装上下文、调用模型、接收工具请求、执行工具、把结果送回模型，然后重复上述过程。每次迭代就是一轮。

在某一轮中，模型可能请求调用工具。该请求经过权限系统、获得执行，输出再作为下一次输入反馈给循环。

这个循环本身被有意设计为单线程。智能都存在于循环周围的层次中，而不在循环逻辑本身。Anthropic 将其称为“笨循环（dumb loop）”：模型负责推理，Harness 负责调停。

这就是 Claude Code 背后的架构。

**[我们最近还写了一篇深入文章，从头解释 Anthropic、OpenAI、LangChain 等团队怎样构建这种模式 →](https://www.dailydoseofds.com/p/the-anatomy-of-an-agent-harness/)**

本文到这里就结束了。

---

### **附：如果你想培养“工业级机器学习”能力**

![原文图 4](assets/figure-04.png)

归根结底，所有企业真正关心的都是*影响*。仅此而已。

- 你能降低成本吗？
- 你能增加收入吗？
- 你能扩展机器学习模型吗？
- 你能在趋势发生前进行预测吗？

我们还讨论过许多与这些问题一致的主题，并提供了相应实现。

[培养“工业级机器学习”能力](https://www.dailydoseofds.com/membership)

下面列出其中一部分：

- 通过这套[分为九部分的速成课程 →](https://www.dailydoseofds.com/model-context-protocol-crash-course-part-1/)全面学习 MCP。
- 通过这套[分为十四部分的速成课程](https://www.dailydoseofds.com/ai-agents-crash-course-part-1-with-implementation/)学习怎样构建 Agent 系统。
- 通过[这套速成课程](https://www.dailydoseofds.com/a-crash-course-on-building-rag-systems-part-1-with-implementations/)学习怎样构建、评估和扩展真实世界中的 RAG 应用。

![原文图 5](assets/figure-05.png)

- 学习复杂的图架构，以及如何用图数据训练这些架构。
- 许多真实世界的 NLP 系统都依赖成对上下文评分。可以在[这里](https://www.dailydoseofds.com/bi-encoders-and-cross-encoders-for-sentence-pair-similarity-scoring-part-1/)学习可扩展的方法。
- 学习使用[量化技术](https://www.dailydoseofds.com/quantization-optimize-ml-models-to-run-them-on-tiny-hardware/)，让大型模型能够运行在小型设备上。
- 学习使用[Conformal Prediction](https://www.dailydoseofds.com/conformal-predictions-build-confidence-in-your-ml-models-predictions/)，生成带有强统计保证的预测区间或预测集合，从而提高可信度。
- 通过[这套速成课程](https://www.dailydoseofds.com/a-crash-course-on-causality-part-1/)学习如何识别因果关系并回答业务问题。
- 通过这份[实践指南](https://www.dailydoseofds.com/how-to-scale-model-training/)学习如何扩展并实现模型训练。
- 学习如何在生产环境中可靠地[测试新模型](https://www.dailydoseofds.com/5-must-know-ways-to-test-ml-models-in-production-implementation-included/)。
- 使用[联邦学习](https://www.dailydoseofds.com/federated-learning-a-critical-step-towards-privacy-preserving-machine-learning/)构建隐私优先的机器学习系统。
- 学习六种带实现的[模型压缩](https://www.dailydoseofds.com/model-compression-a-critical-step-towards-efficient-machine-learning/)技术。

这些资源将帮助你培养企业和公司真正重视的关键能力。
