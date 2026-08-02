# Claude Code Multi-Agent 资料包与写作边界

## 文档定位

这份文档用于为后续文章固定事实边界、资料优先级和问题链。当前阶段只收集、校准和组织材料，不开始编写正文，也不预设筱泽广场景。

资料快照日期：2026-08-02。

本机当前可执行版本：

```text
Claude Code 2.1.205
```

Claude Code 的多代理功能迭代很快。在线文档已经包含晚于本机版本的行为说明，部分页面写到 2.1.219 及之后。后续文章中的命令、默认值和限制必须标注适用版本；长期概念与短期实现应分开讲。

---

## 一、参考文章实际讲了什么

参考文章：[万字长文图解 Claude Code 源码：Multi-Agent 机制](https://zhuanlan.zhihu.com/p/2042176049291714775)，作者小林 coding。页面显示编辑于 2026-05-25。

文章从反编译或泄露源码的视角，组织了四层内容：

1. 常规 Subagent：独立工具池、上下文和生命周期；
2. 父子通信：后台任务、待处理消息和完成通知；
3. Fork Subagent：继承父会话前缀，以提高上下文复用和缓存命中；
4. Coordinator：主代理只负责分配、等待和综合，worker 并行执行。

它最值得借鉴的不是源码符号，而是以下问题顺序：

```text
单代理为什么不够
→ 如何拆出独立执行单元
→ 隔离哪些状态、共享哪些状态
→ 父子之间怎样传递结果
→ 怎样真正并发
→ 并发带来多少成本和新故障
```

但它不适合作为唯一事实源：文章引用的内部文件名、环境变量和工具名称属于高漂移实现细节，而且当前官方文档已经明确记录了与文章不同的行为。

---

## 二、现在应区分的多代理形态

“Claude Code multi-agent”现在不是单一功能，至少要区分以下形态。

| 形态 | 谁负责协调 | 上下文 | 代理间通信 | 适合任务 | 关键代价 |
| --- | --- | --- | --- | --- | --- |
| 普通 Subagent | 主会话 | 子代理通常从新上下文开始 | 结果回到调用者；当前版本也支持命名代理消息和有限嵌套 | 独立、聚焦、输出很长的旁支任务 | 启动和重新获取上下文有成本 |
| Fork / conversation fork | 主会话 | 继承父会话完整历史、模型和工具 | 结果回到主会话，可继续定向消息 | 需要大量既有背景的并行尝试 | 输入隔离变弱，继承内容更多 |
| Agent Teams | team lead | 每个 teammate 是独立会话 | 共享任务列表，teammate 可直接互发消息 | 并行研究、竞争假设、跨层开发 | 实验性、协调开销高、token 多、会有文件冲突 |
| Agent View | 用户 | 多个独立后台会话 | 主要由用户分别查看和介入 | 多个互不依赖的任务 | 用户承担调度；不是自动协作团队 |
| Dynamic Workflows | JavaScript 工作流脚本 | 中间结果主要放在脚本变量中 | 脚本编排大量 subagent | 大规模审计、迁移、交叉验证研究 | 成本和规模可能迅速增长，流程需预审 |
| Worktrees | 不负责协调 | 每个 checkout 有独立文件状态 | 无 | 防止并行写入相互覆盖 | 合并和清理成本；它是隔离机制，不是代理类型 |

一个实用的选择顺序是：

```text
只是旁支任务、最后只要摘要？
→ Subagent

旁支任务依赖当前对话的大量背景？
→ Fork

几个长任务需要彼此讨论、共享任务状态？
→ Agent Teams

用户想分别管理几个独立会话？
→ Agent View

任务要扩展到几十或几百个代理，而且编排要可重复？
→ Dynamic Workflows

会并行修改文件？
→ 在上述方案之外再考虑 Worktrees
```

---

## 三、参考文章需要校准的地方

### 1. `Task` 已不是当前主名称

官方文档记录：Claude Code 2.1.63 将 `Task` 工具改名为 `Agent`，旧的 `Task(...)` 仍作为兼容别名。文章和旧教程若持续使用 `Task`，应明确它属于旧命名。

### 2. “Subagent 不能再派 Subagent”已经过时

参考文章把禁止递归派生当作通用工具黑名单的一部分。当前官方文档则允许 subagent 嵌套，并按版本调整深度：

- 2.1.172–2.1.216：默认最多五层；
- 2.1.217–2.1.218：默认一层；
- 2.1.219 起：默认三层，可用 `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` 调整。

本机 2.1.205 落在“五层”区间。可长期保留的原理是“必须限制递归和总量”，而不是“产品永远禁止嵌套”。

### 3. Agent Teams 的创建和清理机制已经变化

当前 Agent Teams 文档说明：自 2.1.178 起，生成第一个 teammate 时团队自动形成，退出时自动清理；早期使用的 `TeamCreate` 和 `TeamDelete` 已被移除。因此，参考文章中的 Coordinator 内部工具图只能作为历史实现快照。

### 4. Fork 的用户入口也在变化

当前官方文档说明，2.1.212 起会话内 fork 使用 `/subtask`；此前使用 `/fork`。同时，当 Agent View 开启时，`/fork` 可能代表复制整个会话为后台 session，而不再等价于会话内 forked subagent。

本机是 2.1.205，所以本机行为不能直接代表读者的更新版本。

### 5. 后台代理的默认行为和权限处理变化频繁

官方文档记录：

- 2.1.186 起，后台 subagent 的权限请求可浮到主会话；
- 2.1.198 起，subagent 默认在后台运行，只有主会话必须先拿到结果时才前台阻塞；
- 后台 subagent 的内置工具池会被进一步缩小；Fork 例外地继承父会话工具池。

因此，“异步 agent 固定只拥有某一份白名单”不应写成跨版本不变事实。

### 6. 现在的产品图景比参考文章更大

参考文章围绕常规 Subagent、Fork 和 Coordinator 展开。当前官方入口还包括 Agent View 和 Dynamic Workflows；后者把编排计划放进可读、可重跑的 JavaScript 脚本，和由模型逐回合调度的 Agent Teams 是不同路线。

### 7. “源码证明”必须降级为二手证据

参考文章给出了内部 TypeScript 路径和代码片段，但没有提供可稳定复核的官方源码版本、commit 和 tag。后续正文不应逐行引用这些片段来证明当前产品行为。更安全的用法是：

- 用它寻找值得解释的机制问题；
- 用官方文档和本机实验验证外部可观察行为；
- 内部实现只以“该版本的逆向观察”表述；
- 不复刻大段代码或插图。

---

## 四、可形成文章的问题链

这篇文章不宜写成“功能列表”。更自然的技术因果链是：

### 问题 1：为什么不让一个 agent 从头做到尾

单代理会同时遇到：

- 调研、实现和评审材料挤在同一个上下文；
- 所有工具输出都污染主会话；
- 独立任务只能串行等待；
- 同一个推理轨迹容易造成锚定偏差。

### 问题 2：把工作派出去后，子代理知道什么

普通 Subagent 用新上下文换取隔离和压缩，但必须重新说明任务；Fork 继承整段会话，减少背景重述并复用 prompt cache，却牺牲部分输入隔离。

这里可把“上下文”拆成四层：

```text
系统提示与工具定义
→ 项目规则和 CLAUDE.md
→ 会话历史
→ 当前任务说明
```

不同代理形态并不是简单的“有上下文 / 没上下文”，而是继承层级不同。

### 问题 3：并发完成不等于协作完成

Subagent 可以并发执行独立任务，但结果主要回到主会话。Agent Teams 增加共享任务列表和 mailbox，让 teammate 能互相质疑、认领任务和解除依赖；代价是引入新的分布式状态问题：任务状态滞后、提前收尾、消息和权限等待、会话恢复失败。

### 问题 4：多个 agent 会不会改坏同一份代码

上下文隔离不等于文件隔离。多个 agent 即使各自拥有独立对话，也可能同时编辑同一个 checkout。Worktree 才是解决文件状态冲突的机制；任务仍应按模块或文件所有权切分。

### 问题 5：为什么不是 agent 越多越好

官方材料和研究共同指向三个约束：

- 并行、可分解任务最适合扩展；顺序依赖强的任务可能退化；
- 相同提示、相同工具的同质代理容易重复犯错，增加角色和证据路径的差异比单纯增加数量更有价值；
- 多代理把性能建立在更多 token、更多工具调用和更多协调状态上，必须用验证门控制错误传播。

### 问题 6：谁来握住计划

这是连接当前产品形态的收束问题：

- 主会话逐回合决定：Subagents；
- lead 逐回合协调 peer：Agent Teams；
- 用户分别协调独立会话：Agent View；
- 脚本固定循环、分支和验证：Dynamic Workflows。

这比把所有方案统称为“Coordinator 模式”更准确。

---

## 五、优先资料清单

### A. 当前产品行为：必须优先引用

1. [Run agents in parallel](https://code.claude.com/docs/en/agents)
   - 当前总览；用于比较 Subagents、Agent View、Agent Teams、Dynamic Workflows 和 Worktrees。

2. [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
   - 定义文件、scope、工具、模型、权限、前后台行为、嵌套、Fork、上下文继承和限制。
   - 这是校准参考文章最重要的页面。

3. [Orchestrate teams of Claude Code sessions](https://code.claude.com/docs/en/agent-teams)
   - lead、teammate、共享 task list、mailbox、直接通信、质量 hooks、适用场景和已知限制。
   - 页面明确说明该能力仍是 experimental，并记录多个版本差异。

4. [Manage multiple agents with agent view](https://code.claude.com/docs/en/agent-view)
   - 用于说明“用户管理多个后台会话”与“代理自行组队”的差异。

5. [Orchestrate subagents at scale with dynamic workflows](https://code.claude.com/docs/en/workflows)
   - JavaScript 编排、`/deep-research`、`agent()`、`pipeline()`、恢复、规模和成本限制。
   - 适合用来建立“计划在模型里，还是在代码里”的对照。

6. [Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees)
   - 文件隔离、`--worktree`、subagent 的 `isolation: worktree` 和清理行为。

7. [Manage costs effectively](https://code.claude.com/docs/en/costs)
   - 上下文、prompt caching、`/usage`、代理团队成本和 rate limit。
   - 官方给出的经验值是 Agent Teams 在 teammate 使用 plan mode 时约为标准会话的 7 倍 token；应标为官方估计，不当作普遍常数。

8. [How Claude Code uses prompt caching](https://code.claude.com/docs/en/prompt-caching)
   - 精确前缀匹配、系统提示层、项目上下文层和会话层；用于解释为什么 Fork 能复用父会话 cache，以及哪些改动会使 cache 失效。

9. [Claude Code changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
   - 用于给命令、默认值和行为标版本。写作时应固定一个版本区间，不用“目前永远如此”的口吻。

### B. 架构原理：用于解释为什么这样设计

10. [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
    - 区分 workflow 与 agent；给出 parallelization、orchestrator-workers、evaluator-optimizer 等可组合模式。
    - 可作为文章的长期概念骨架。

11. [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
    - Anthropic 的生产经验：并行 subagent 作为上下文压缩器，lead 负责规划和综合。
    - 内部研究评测中，多代理配置比单代理 Opus 4 高 90.2%，但 multi-agent 约消耗普通 chat 15 倍 token。两项数字都只代表该系统和该评测，不能外推为 Claude Code 的普遍收益或成本。

### C. 反例和限制：防止写成宣传文

12. [Towards a Science of Scaling Agent Systems](https://arxiv.org/abs/2512.08296)
    - 260 种配置、六个 agent benchmark、五种架构。
    - 论文报告：可分解任务可能显著受益，顺序规划可能明显退化；集中验证比没有集中验证更能抑制错误传播。

13. [Google Research 对该研究的介绍](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)
    - 更适合作为读者友好的辅助解释；核心数字仍应回到论文。

14. [Understanding Agent Scaling in LLM-Based Multi-Agent Systems via Diversity](https://arxiv.org/abs/2602.03794)
    - 预印本指出同质 agent 数量增加会快速出现边际收益递减，异质模型、提示、角色和工具更可能贡献互补证据。
    - 研究主要基于 7B–8B 开源模型及 vote/debate 结构，不能直接当作 Claude Code 工程任务的定律；适合放在延伸阅读或局限部分。

---

## 六、后续需要补的可复现实验

正式写文章前，建议在单独测试仓库中记录以下实验。这样能把“官方说明”转化成读者能观察到的现象。

1. 普通 Subagent 与 Fork：给同一任务，比较启动提示、上下文继承、首轮 cache 和最终 token；
2. 前台与后台 Subagent：观察主会话是否阻塞、权限请求怎样出现、结果何时回传；
3. 嵌套代理：在 2.1.205 和更新版本分别记录默认深度与工具变化；
4. Agent Teams：让三个 teammate 分别做安全、性能和测试评审，观察 task list、直接消息和 lead 综合；
5. 同文件冲突：让两个 worker 修改同一文件，再用 worktree 隔离复现实验；
6. 顺序任务反例：设计一个强依赖流水线，比较单代理、Subagent 和 Agent Teams 的时间、token 与正确率；
7. 多样性实验：比较三个同提示 reviewer 与三个不同审查维度 reviewer；
8. 失败注入：让一个 worker 返回错误结论，比较“直接汇总”和“独立 verifier”能否发现。

每次实验至少记录：

```text
Claude Code 版本
模型与 effort
功能开关
代理数量与角色
是否使用 worktree
总 token / wall time
最终正确性
中途故障与人工介入
```

---

## 七、写作时的事实检查清单

- 是否把 Subagent、Fork、Agent Teams、Agent View、Workflow 和 Worktree 分开定义？
- 是否给命令和默认值标了 Claude Code 版本？
- 是否把参考文章的内部源码观察标为二手、易漂移材料？
- 是否解释了上下文隔离与文件隔离不是同一件事？
- 是否给出“多代理不适合顺序依赖任务”的反例？
- 是否同时报告质量、token、延迟和协调失败，而不是只报告速度？
- 是否说明 Agent Teams 仍属 experimental？
- 是否让 lead 或 verifier 真正综合和校验，而不是只拼接各代理输出？
- 是否避免复制参考文章的大段源码、插图或表述？

这套边界固定后，再选择筱泽广场景和文章文体会更稳。

---

## 八、X / 外网优质文章清单（2026-08-02 补充）

下面按“对这篇文章的实际价值”排序，而不是按热度排序。核心清单优先保留产品团队一手材料、官方工程复盘和能提供反例的资料；普通 SEO 教程不作为事实依据。

### A. 最值得先读的六篇

1. [How and when to use subagents in Claude Code](https://claude.com/blog/subagents-in-claude-code)
   - Claude 官方，2026-04-07。
   - 最适合回答“什么时候应该拆 subagent”：适用于会制造大量中间输出的研究、日志分析和相对独立的工作；不应把所有步骤都机械地代理化。
   - 文章还把轻量 subagent 与更重、更贵、允许成员互相通信的 Agent Teams 分开了。

2. [Building multi-agent systems: When and how to use them](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)
   - Claude 官方，2026-01-23。
   - 给出三个值得多代理化的条件：避免 context pollution、任务可并行、需要专业化角色。
   - 官方提醒多代理常消耗单代理约 3--10 倍 token，而且并行化的主要收益经常是“覆盖更全面”，不一定是更快。这个判断很适合用来纠正“多开几个就一定提速”的直觉。

3. [Multi-agent coordination patterns: Five approaches and when to use them](https://claude.com/blog/multi-agent-coordination-patterns)
   - Claude 官方，2026-04-10。
   - 将多代理系统整理为 generator--verifier、orchestrator--subagent、agent teams、message bus 和 shared state 五种协调模式。
   - 适合作为正文的概念骨架：不要只按 Claude Code 功能菜单介绍，而要先讲任务依赖、通信方式和冲突面。

4. [Boris Cherny：Claude Code 团队的工作方式与技巧串](https://x.com/bcherny/status/2017742741636321619)
   - Claude Code 创建者的一手实践串，2026-02-01。
   - 其中最有价值的三点是：同时运行 3--5 个 git worktree；复杂任务先进入 plan mode；必要时让第二个 Claude 以 staff engineer 视角审查计划。
   - 这是团队成员的个人工作流，不是普适性能结论。文章可以借它引出“并发会话、subagent、agent team 是三种不同层次的并行”。

5. [Using Claude Code: session management and 1M context](https://claude.com/blog/using-claude-code-session-management-and-1m-context)
   - Claude Code 团队成员 Thariq Shihipar，2026-04-15。
   - 系统比较 continue、rewind、clear、compact 和 subagent；很适合解释 context rot，以及“我以后还需要完整工具输出，还是只需要结论”这个拆分判断。

6. [A harness for every task: dynamic workflows in Claude Code](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code)
   - Claude 官方的 Dynamic Workflows 文章。
   - 重点不是“生成更多 agent”，而是让 Claude 为特定任务生成 JavaScript 编排器，把并行、依赖、重试和汇总写成可执行控制流。
   - 适合放在正文后半段，作为从自然语言调度走向显式 harness 的进阶路线；成本高，应该用于高价值、结构明确的任务。

### B. 用来补足上下文、工具与实现原理

7. [Seeing like an agent: how we design tools in Claude Code](https://claude.com/blog/seeing-like-an-agent)
   - 说明 Claude Code 为什么会随模型能力演进工具设计，例如从个人待办工具转向支持代理间协调的 Tasks。
   - 对文章最有用的观点是 progressive disclosure：不要把所有说明一次塞进主上下文，可通过专用 subagent 按需返回结论。

8. [Lessons from building Claude Code: Prompt caching is everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything)
   - 解释长会话、cache 前缀和 compaction 的工程关系。
   - 可用于补足“代理为什么贵”的底层解释：成本不仅取决于 agent 数量，也取决于它们能否复用稳定前缀以及何时发生 cache miss。

9. [Redesigning Claude Code on desktop for parallel agents](https://claude.com/blog/claude-code-desktop-redesign)
   - 从产品界面解释另一种多代理：不是 lead 自动派生 teammate，而是用户作为 orchestrator 管理多个独立 session。
   - 很适合用来区分 Agent View / Desktop 并行会话与 Agent Teams。

10. [Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems](https://arxiv.org/abs/2604.14228)
    - 对 Claude Code 的 source-level 逆向研究，覆盖 agent loop、权限、上下文、subagent delegation、worktree isolation 和 session persistence。
    - 信息密度很高，但基于特定时间点的实现快照，不是官方契约；只能辅助理解，所有当前产品行为仍须回查官方文档和 changelog。

### C. X 上值得引用的一手更新与反例

11. [Boris Cherny：内置 git worktree 支持](https://x.com/bcherny/status/2025007393290272904)
    - 2026-02-21。可作为“文件隔离是并行编码的基础设施”的产品演进证据。

12. [Lydia Hallie：Agent Teams research preview](https://x.com/lydiahallie/status/2019469032844587505)
    - 2026-02-06。简洁展示 lead 分派任务、teammate 并行执行并相互协调的官方定位。

13. [Boris Cherny：nested subagents 支持](https://x.com/bcherny/status/2064327225504403752)
    - 2026-06-09。发布时初始深度限制为 5；这是版本性事实，正式写稿前需再查 changelog。

14. [Boris Cherny：subagents 默认后台运行](https://x.com/bcherny/status/2071647677591466098)
    - 2026-06-30。说明默认前后台行为也会变化，不能把旧教程里的交互现象写成永久机制。

15. [Claude Developers：过度生成并行 subagent 的额度事故](https://x.com/ClaudeDevs/status/2061501787769893055)
    - 2026-06-02。官方称一个问题导致部分 session 生成过多并行 subagent，使 Pro / Max 使用额度异常快速消耗，修复后重置了受影响用户的 rate limit。
    - 这是非常好的反例：并发失控不仅是 token 成本问题，也可能成为产品可靠性和配额治理问题。

### D. 不建议当核心来源的材料

- 未附实验仓库、版本号和任务定义的“十倍效率”帖子；
- 只展示大量终端窗格、没有最终正确性与 token 数据的截图串；
- 把 subagent、Agent Teams、多个 worktree session 混称为 swarm 的教程；
- 复述官方文档但没有注明日期的聚合站和 SEO 文章；
- 产品发布帖中的内部效率数字。它们可以描述特定团队的观察，不能外推为普通项目的稳定收益。

建议的阅读顺序是：先读 1--3 建立选择标准，再读 4--6 看实际工作流，最后用 7--15 补上下文机制、版本变化和失败边界。

---

## 九、非官方实践文章与独立证据（针对上一轮补正）

上一节的核心清单仍偏向 Claude 官方。下面刻意排除 Anthropic / Claude 自有博客，优先选择实际团队复盘、公开配置、可复现实验和带失败数据的材料。

### A. 非官方必读

1. [How we're shipping faster with Claude Code and Git Worktrees](https://incident.io/blog/shipping-faster-with-claude-code-and-git-worktrees)
   - incident.io 工程团队的实际工作流，Rory Bain，2025-06-27。
   - 团队从单会话逐步发展到同时运行四五个 Claude agent，并公开了自制 worktree manager 的 gist。
   - 价值不在“多开窗口”，而在它记录了启动、分支命名、独立会话、Plan Mode、人工持续引导之间的完整工作方式。
   - 局限：属于团队自述，没有严谨对照实验；发布时 Claude Code 尚未提供今天的全部原生 multi-agent 功能。

2. [We ditched worktrees for Claude Code. Here's what we use instead](https://trigger.dev/blog/parallel-agents-gitbutler)
   - Trigger.dev CTO Eric Allam，2026-04-16。
   - 与 incident.io 构成非常好的正反对照：大型 TypeScript monorepo 中，源码虽然被隔离了，端口、PostgreSQL、Redis、ClickHouse、依赖安装和构建产物并没有自动隔离。
   - 他们最终改用 GitButler virtual branches，让一个工作目录承载多个逻辑分支。文章也诚实说明：如果两个 agent 会改同一文件，或测试会修改共享状态，真正的 worktree / 环境隔离仍更安全。
   - 这篇最适合用来建立一个关键结论：代码分支隔离不等于运行环境隔离。

3. [Advanced Context Engineering for Coding Agents](https://www.humanlayer.dev/blog/advanced-context-engineering)
   - HumanLayer 团队的实践文章，附公开 research / plan / implementation prompts 和真实代码库案例。
   - 它反对把 subagent 拟人化成虚构公司岗位，主张 subagent 的首要价值是控制上下文：让它承担搜索、阅读和压缩，只把结论交回主 agent。
   - 推荐的 Research--Plan--Implement 工作流中，只有实现阶段通常需要 worktree；研究与规划可以先在主分支完成。
   - 作者所在团队销售 agent 工具，观点带有自身方法论立场，但示例和提示词可以直接检查。

4. [Running Parallel Claude Code Agents with Git Worktrees](https://unmarkdown.com/blog/parallel-agents-worktrees-claude-code)
   - 独立开发者复盘三个 Claude Code 实例并行开发三个功能。
   - 文章没有把它写成万能提速：作者认为只有单项工作足够大（约 1--2 小时 agent 工作量）、文件边界清楚且无共享写入时，并行的启动、监督和合并开销才划算。
   - 他在 200 多次顺序 session 中只约十次真正使用并行。这是对“默认 swarm”很有价值的经验反例，但时间阈值只是个人经验，不应写成通用常数。

5. [I Haven't Written a Line of Code in 4 Months (But I Ship More Than Ever)](https://x.com/kaxil/status/2037503513350005134)
   - Apache Airflow PMC、Astronomer 工程负责人 Kaxil Naik 的 X 长文，2026-03。
   - 记录某个真实工作日运行 27 个 Claude Code sessions、覆盖 6 个仓库；同时说明 subagents 用于上下文 / 权限隔离，Agent Teams 用于大型任务的并行部分。
   - 重点是支撑这一规模的 skills、hooks、CLI、测试环境和人工审查，而不是一句“开 27 个窗口”。数据均为作者自述，适合作为个案，不适合作为效率基准。

### B. 有公开代码或研究方法的材料

6. [AWS sample: Claude Code Multi-Agent Development](https://github.com/aws-samples/sample-claude-code-agent-team)
   - 可直接查看的 `.claude` 配置样例：lead、coding、DevOps、review、solutions architect，外加 rules、skills、hooks 与权限配置。
   - 比普通教程更有价值，因为读者可以检查角色描述、模型分配、工具权限和验证链怎样落到文件上。
   - AWS 明确标注它只是起点、未经生产批准，并要求根据项目安全要求调整；不应直接复制到真实项目。

7. [StatsClaw: An AI-Collaborative Workflow for Statistical Software Development](https://arxiv.org/abs/2604.04871)
   - Cambridge / Stanford 作者提出的 Claude Code 八代理工作流，并在 R、Python 统计包中演示。
   - 最值得借鉴的是信息屏障：builder 不知道 ground truth，simulator 不知道算法实现，tester 使用确定性标准验证，从流程上减少“写代码的 agent 顺便证明自己正确”。
   - 这是比“planner / coder / reviewer 三个角色”更扎实的独立验证设计。

8. [Agent Team Work Zone](https://arxiv.org/abs/2607.22917)
   - 2026-07 的新预印本，直接针对长期 Agent Teams 的四个问题：进程结束后 teammate 状态难以恢复、compaction 丢细节、历史决策形成 agentic technical debt，以及反复写长 handoff prompt。
   - 提出的做法是把工作状态、技能、hook 和脚本保存到文件系统中的 workstation，而不是让关键知识只存在会话里。
   - 论文很新，经验验证仍有限，适合作为“文件化状态与恢复”的设计线索，不宜当成熟标准。

### C. 失败数据和负面材料

9. [Claude Code is unusable for complex engineering tasks with the Feb updates](https://github.com/anthropics/claude-code/issues/42796)
   - AMD AI 工程负责人 Stella Laurenzo 在 Claude Code issue 中提交的数据化回归报告，分析 6,852 个 session 文件，并用 stop-hook violation 作为机器可读信号。
   - 这是用户提交到官方仓库的独立报告，不等于 Anthropic 已认可全部因果判断；但它展示了应该如何保留 session、工具调用和失败日志，而不是只凭主观手感评价 agent。

10. [SubagentStart / SubagentStop hooks unreliable](https://github.com/anthropics/claude-code/issues/27755)
    - 带复现步骤的生命周期问题：并行 dispatch 中 hook 不可靠会破坏 tracing、cleanup、proof gate 和自动验证流水线。
    - 适合用来说明 multi-agent 系统不能只考虑“任务能否分出去”，还要考虑可观测性、结束语义和失败恢复。

### D. 对正文选材的影响

非官方资料给出的文章主线应当从“功能介绍”改为一组互相冲突的工程选择：

```text
incident.io：worktree 让多个会话真正可管理
        vs.
Trigger.dev：worktree 只隔离源码，复杂运行环境会让成本爆炸

HumanLayer：subagent 首先是上下文压缩器
        vs.
角色扮演式教程：为每个职位创建一个 agent

Kaxil：成熟工具链下可以运行几十个 session
        vs.
Unmarkdown：绝大多数任务顺序执行反而更便宜、更干净

StatsClaw：通过信息屏障获得独立验证
        vs.
同一上下文派生的 reviewer：可能只是重复实现者的假设
```

这组冲突比“Claude Code 支持哪些 multi-agent 功能”更适合成为文章的叙事骨架。

---

## 十、第三方机制解析文章

这一组与上一节的“使用经验”不同，重点是解释 Claude Code 的代理层次、文件协议、上下文和调度机制。

1. [Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems](https://arxiv.org/abs/2604.14228)
   - 当前最系统的第三方 source-level 解析。
   - 从公开 TypeScript 源码快照追踪 agent loop、权限系统、五层 compaction、MCP / plugins / skills / hooks、subagent delegation、worktree isolation 和 append-only session storage。
   - 优点是引用到具体实现结构；缺点是实现快照会随 Claude Code 版本快速漂移，不能替代当前文档。

2. [Claude Code Agent Teams: How They Work Under the Hood](https://www.claudecodecamp.com/p/claude-code-agent-teams-how-they-work-under-the-hood)
   - Abhishek Ray 在 Claude Code 2.1.45 上运行一周 Agent Teams，并观察其生成的 JSON、team config、task 和 inbox 文件。
   - 具体解释 subagent 的一次性返回与 Agent Teams 的持久 session、共享 task queue、inbox 和文件系统通信差异。
   - 是最贴近本文 multi-agent 主题的民间拆解；内部文件名与限制必须标注版本。

3. [Claude Code agents: what they actually are](https://joseparreogarcia.substack.com/p/claude-code-agents-explained)
   - José Parreño García 的概念澄清文。
   - 把内置 agent、custom subagent、Agent Teams 和 Claude Agent SDK 分成四层，重点解释为什么 subagent 的主要价值是隔离搜索中间过程、控制 context rot。
   - 源码深度不如前两篇，但适合作为读者进入主题的第一篇。

4. [Claude Code Agent Teams：when it works, and when it breaks](https://reliantlabs.io/blog/claude-code-agent-teams)
   - Reliant Labs 从任务结构角度分析 Agent Teams：read-heavy 并行探索效果最好，代码生成必须先划清文件边界。
   - 特别指出当前协调层缺少强制验证关卡：teammate 声明完成后，lead 可能直接相信，错误会沿后续步骤传播。
   - 作者同时经营自己的 agent workflow 产品，因此对显式 workflow 的偏好需要结合其商业立场阅读。

5. [Claude Code Agent Teams Explained](https://www.youtube.com/watch?v=1jlKUxqRQAw)
   - Mark Kashef 的第三方视频解析，包含 Subagents / Agent Teams 决策流程、task lifecycle、通信协议、token 成本、文件覆盖、无法恢复等 gotchas，并演示监控面板。
   - 适合用来理解动态过程和准备文章配图；具体功能仍需按视频日期回查版本。

6. [How Anthropic Claude Code Actually Works: A--Z Deep Dive](https://agent-cookbook.com/tutorial/how-anthropic-claude-code-actually-works-a-z-deep-dive)
   - 覆盖从基本 agent loop、工具调用到 context 和 subagent 的通俗长文。
   - 阅读友好，但很多内容是对其他材料的再组织，不应作为内部机制的唯一来源；适合辅助解释，不如前两篇严谨。

如果只读三篇，顺序建议是：José 的概念澄清 → ClaudeCodeCamp 的 Agent Teams 实验 → `Dive into Claude Code` 的 source-level 全景。

---

## 十一、arXiv 上的 Claude Code / multi-agent 相关论文

### A. 直接研究 Claude Code 或基于它构建系统

1. [Agent Team Work Zone: An Automated, Persistent Workspace for Long-Lived Coding Agent Teams](https://arxiv.org/abs/2607.22917)
   - 直接围绕 Claude Code Agent Teams，讨论 teammate 无法恢复、compaction 丢细节、历史决策形成 agentic technical debt，以及重复 handoff prompt 的问题。
   - 提出用文件系统 workstation 保存 agent 状态、skill、hook 和脚本。与“多代理长期运行如何保存状态”高度相关，但论文较新，验证仍有限。

2. [StatsClaw: An AI-Collaborative Workflow for Statistical Software Development](https://arxiv.org/abs/2604.04871)
   - Claude Code 八代理工作流；通过 builder、simulator、tester 之间的信息屏障保证验证相对独立。
   - 这是“多代理为什么不只是多开几个相同角色”的好案例。

3. [On the Use of Agentic Coding Manifests: An Empirical Study of Claude Code](https://arxiv.org/abs/2509.14744)
   - 分析 242 个仓库中的 253 个 `CLAUDE.md`，研究真实项目怎样组织命令、技术说明和架构上下文。
   - 不是 Agent Teams 论文，但适合解释所有 agent 启动前共享的项目上下文从哪里来。

4. [Context Engineering for Multi-Agent LLM Code Assistants Using Elicit, NotebookLM, ChatGPT, and Claude Code](https://arxiv.org/abs/2508.08322)
   - 把需求澄清、文献检索、文档综合与 Claude Code 多代理代码生成 / 验证串成一个工作流。
   - 更像应用型方案，实验主要是 Next.js 个案和定性结果，证据强度低于受控 benchmark。

5. [Adoption and Impact of Command-Line AI Coding Agents](https://arxiv.org/abs/2607.01418)
   - 研究微软在 2026 年初向数万名工程师推广 Claude Code 和 GitHub Copilot CLI 的采用与影响。
   - 作者估计采用者合并 PR 数约增加 24%，但明确承认“合并 PR”不等于实际价值；适合写组织采用，不适合证明 multi-agent 本身有效。

6. [IssueTrojanBench: Benchmarking AI Coding Agents Against Malicious Issue Requests](https://arxiv.org/abs/2607.20759)
   - 比较 Claude Code、Codex Desktop 和 Cursor 面对恶意 issue / 间接提示注入时的行为。
   - 适合补充多代理系统的安全边界：更多 agent 和工具调用也意味着更大的攻击与权限传播面。

### B. 不是 Claude Code 专论文，但直接支撑 multi-agent 论证

7. [OrchBench: Evaluating Multi-Agent Orchestration Plans in Isolation](https://arxiv.org/abs/2607.25656)
   - 用 DAG、agent budget、context limit 和跨 agent 信息保留率单独评测编排计划，并用 Claude Code 执行结果做相关性验证。
   - 论文报告模拟得分与 Claude Code 运行质量的 Pearson 相关系数为 0.816；核心结论是保存任务关键上下文比单纯增加 agent 数量更重要。

8. [Do More Agents Help?](https://arxiv.org/abs/2606.05670)
   - 在统一 loader、工具、输出协议、token 记账和 trajectory logging 下比较单代理与多代理。
   - 多数 MAS 没有超过匹配的单代理基线；其中提到的是 `Claude-Code-style runtime workflow`，不能误写成对 Claude Code Agent Teams 的直接官方评测。

9. [Towards a Science of Scaling Agent Systems](https://arxiv.org/abs/2512.08296)
   - 研究任务特性、拓扑、协调开销和错误传播。并行任务可能获益，而顺序推理任务中的多代理版本明显退化。

10. [Understanding Agent Scaling via Diversity](https://arxiv.org/abs/2602.03794)
    - 研究同质 agent 的边际收益递减与异质 agent 的互补性；论文实验中两个多样化 agent 可匹配或超过十六个同质 agent。
    - 主要基于通用 MAS 实验，不应直接外推为 Claude Code 的固定数量建议。

11. [Rethinking the Value of Multi-Agent Workflow: A Strong Single Agent Baseline](https://arxiv.org/abs/2601.12307)
    - 论证同质多代理工作流经常能由一个多轮单代理模拟，并通过 KV cache 复用降低成本。
    - 可作为文章中反对“角色越多越先进”的理论材料。

对本文章最有价值的阅读顺序：`Agent Team Work Zone` → `StatsClaw` → `OrchBench` → `Do More Agents Help?`。前两篇给 Claude Code 具体系统，后两篇提供评测和反例。
