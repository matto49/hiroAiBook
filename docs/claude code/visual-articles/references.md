# 内容与参考关系

本页把三篇图解文章与两篇深度研究材料按主题对齐，供后续搭建文章大纲和核对事实时使用。

## 来源编号

| 编号 | 来源 | 类型 | 主要价值 |
| --- | --- | --- | --- |
| V1 | [*Claude Code's Architecture, Explained Visually!*](https://blog.dailydoseofds.com/p/claude-codes-architecture-explained) / [中文译稿](architecture-explained-visually/translation-zh.md) | 第三方图解文章 | 用一张六层架构图建立总体心智模型 |
| V2 | [*End-to-End Workflow*](https://y-agent.github.io/inside-claude-code/01-end-to-end-workflow.html) / [中文译稿](end-to-end-workflow/translation-zh.md) | 第三方 Source Map 解析 | 用七阶段流程解释单次请求生命周期 |
| V3 | [*Multi-Agent Orchestration*](https://y-agent.github.io/inside-claude-code/07-multi-agent-orchestration.html) / [中文译稿](multi-agent-orchestration/translation-zh.md) | 第三方 Source Map 解析 | 解释生成路径、智能体类型、隔离、协调和资源管理 |
| P1 | [*Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems* 中文译稿](../2604.14228v2-zh.md) | 第三方论文/源码级分析 | 为 agent loop、Prompt、工具、安全、上下文、Subagent 等提供更系统的证据 |
| P2 | [*Agent Team Work Zone* 中文译稿](../2607.22917-zh.md) | 第三方论文 | 聚焦长期 Agent Team 的状态恢复、压缩丢失、handoff 与技术债务 |

## 主题—来源矩阵

| 后续内容主题 | 主参考 | 补充参考 | 使用方式 |
| --- | --- | --- | --- |
| Claude Code 不只是“模型套壳” | V1 | P1 | 用 V1 的六层图开场，用 P1 补足设计空间与源码证据 |
| 从输入到结果的完整生命周期 | V2 | P1 | 以 V2 七阶段为叙事骨架，用 P1 核对各阶段机制 |
| Agent loop 与工具调用 | V1、V2 | P1 | V2 负责顺序与读图，P1 负责实现细节 |
| Prompt 组装与上下文工程 | V2 | P1 | 区分稳定机制和版本相关的片段数、大小、阈值 |
| 权限、安全与 Hooks | V1、V2 | P1 | 图解说明执行位置，论文补足权限模型与安全边界 |
| Fork 与 fresh agent | V3 | P1 | 以 V3 的两条生成路径解释上下文继承，再用 P1 交叉核验 |
| 五种智能体类型 | V3 | P1 | 适合做成本—能力连续谱，但类型名和默认模型需按发布版本标注 |
| Git worktree 隔离 | V1、V3 | P1 | 用 V3 的图解释工作副本隔离，避免写成数据库或进程级强隔离 |
| Coordinator 与 Teammate | V3 | P2 | V3 讲拓扑与协议，P2 讲长期协作中的状态问题 |
| 团队内存与跨会话恢复 | V3 | P2 | 先说明共享/私有边界，再引入 compaction、handoff 和恢复失败 |
| Token、缓存与成本 | V3 | P1 | 说明缓存前缀原理；规模数据和节省比例必须保留来源限定 |
| 多智能体何时值得使用 | V3 | P1、P2 | 从上下文隔离、任务独立性、协调成本三方面给出判断 |
| 多智能体的失败模式 | P2 | V3 | 用 V3 建立理想结构，再用 P2 展示长期运行中的裂缝 |

## 推荐的后续行文层次

1. **整体图：** Claude Code 是 Agent Harness，而模型只是其中一层（V1）。
2. **单智能体时间线：** 一次请求怎样经过七个阶段，并在 Agent loop 中反复调用工具（V2）。
3. **分叉点：** 单个上下文为什么不够，父智能体何时选择 fork 或 fresh agent（V3）。
4. **执行隔离：** 不同智能体怎样获得不同提示词、工具、模型和 worktree（V3、P1）。
5. **协调拓扑：** Coordinator 的星型结构与 Teammate 的网状结构有什么差别（V3）。
6. **理想结构的裂缝：** compaction、恢复、handoff、长期状态与 agentic technical debt（P2）。
7. **实践结论：** 多智能体不是越多越好；收益取决于任务可分解性、上下文隔离价值和合并成本。

这只是资料导航，不等于最终文章大纲。正式梳理大纲时，可以从上述层次中重新选择叙事顺序。

## 引用与核验规则

- 描述作者观察到的实现时，使用“文章基于某版本分析”“作者在 Source Map 中观察到”等限定语。
- 工具数量、Prompt 大小、压缩阈值、模型默认值、功能开关、每周生成量和成本节省比例都属于高漂移事实，发布前应重新核验。
- 架构图适合解释关系，不应单独承担精确事实证明；关键论断至少与 P1、P2 或对应版本的官方文档交叉核对。
- V1 中的赞助内容与推广段落已为保证全译完整性而保留，但不属于后续技术文章的参考主体。
- 引用图片时保留原作者、文章名和原文链接；若需要重新绘制中文图，应把它标为“据原图重绘”，而不是冒充原图。

