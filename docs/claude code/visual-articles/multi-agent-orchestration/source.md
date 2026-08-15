---
title: "Multi-Agent Orchestration"
author: "Zhuoran Yang"
date: "2026"
source_url: "https://y-agent.github.io/inside-claude-code/07-multi-agent-orchestration.html"
retrieved: "2026-08-02"
---

# Multi-Agent Orchestration

- Author: Zhuoran Yang
- Source: <https://y-agent.github.io/inside-claude-code/07-multi-agent-orchestration.html>
- Retrieved: 2026-08-02

1. [II. Agent Harness](./02-agent-loop-query-engine.html)
2. [II.3 — Multi-Agent Orchestration](./07-multi-agent-orchestration.html)

fork() for AI – five agent types, worktree isolation, and swarm coordination

## Why Multi-Agent?

In Unix, when a process needs to do two things at once, it calls `fork()`. The kernel copies the process – same binary, same memory layout, same file descriptors – and the child runs independently. The parent can wait for the result, or carry on with its own work. This is the fundamental primitive of parallel computation in operating systems: clone yourself, diverge, reconverge.

Claude Code does the same thing with AI agents.

When a task is too large for a single context window, or when multiple pieces of work can proceed independently, the main agent spawns sub-agents – each with its own context, tools, and working directory. The sub-agent executes, reports back, and terminates. The parent synthesizes results. This is not an analogy stretched for rhetorical effect. The code literally calls it “fork.” The feature flag is `FORK_SUBAGENT`. The function is `buildForkedMessages`. The child’s system prompt begins: *“STOP. READ THIS FIRST. You are a forked worker process. You are NOT the main agent.”*

This post covers how Claude Code decomposes tasks across multiple agents, isolates their work in git worktrees, manages their budgets, and synthesizes their results – the same decompose-execute-aggregate pattern that appears as MapReduce, fork-join parallelism, and actor-model concurrency in systems programming. The agent loop that each sub-agent runs is described in [Part II.1](./02-agent-loop-query-engine.html); the tool system through which agents are dispatched is in [Part IV.1](./05-tool-system.html); the safety layer that constrains their actions is in [Part IV.2](./06-safety-sandbox.html).

![Figure 1: The four pillars of multi-agent orchestration covered in this post – five agent types, git worktree isolation, coordination models (Coordinator vs. Teammate), and resource management (token budgets, model selection, cleanup) – all feed into a final result synthesis and merge step where the parent agent integrates child outputs.](assets/figure-01-fig-post-territory.png)

*Figure 1: The four pillars of multi-agent orchestration covered in this post – five agent types, git worktree isolation, coordination models (Coordinator vs. Teammate), and resource management (token budgets, model selection, cleanup) – all feed into a final result synthesis and merge step where the parent agent integrates child outputs.*

**How to read this diagram.** Start from the four boxes on the left – Five Agent Types, Worktree Isolation, Coordination Models, and Resource Management – each representing a major section of this post. All four arrows converge on the Result Synthesis and Merge box on the right, showing that these pillars are independent concerns that combine at the end when the parent agent integrates child outputs.

**Source files covered in this post:**

| File | Purpose | Size |
| --- | --- | --- |
| `src/tools/AgentTool/AgentTool.tsx` | AgentTool entry point and UI | ~500 LOC |
| `src/tools/AgentTool/runAgent.ts` | Agent execution with cleanup | ~400 LOC |
| `src/tools/AgentTool/forkSubagent.ts` | Fork-based async workers | ~300 LOC |
| `src/tools/AgentTool/loadAgentsDir.ts` | Agent discovery and YAML frontmatter parsing | ~756 LOC |
| `src/tools/AgentTool/builtInAgents.ts` | Built-in agent definitions (Explore, Plan, etc.) | ~300 LOC |
| `src/tools/AgentTool/prompt.ts` | Sub-agent system prompt assembly | ~200 LOC |
| `src/tools/AgentTool/agentMemory.ts` | Agent-scoped memory management | ~150 LOC |
| `src/services/teamMemorySync/` | Team memory synchronization protocol | 5 files |
| `src/coordinator/` | Swarm coordinator mode | ~3 files |

---

## The fork() Analogy

The connection between sub-agents and Unix processes is not metaphorical – it is structural. A Unix `fork()` creates a child process with a copy of the parent’s memory; Claude Code’s fork path creates a child agent with a copy of the parent’s conversation history and system prompt. A Unix child inherits file descriptors; a fork child inherits the parent’s exact tool pool. A Unix child runs in its own virtual address space; a fork child runs in its own git worktree. The isolation boundaries, the communication primitives, and the lifecycle management all map directly.

The AgentTool implementation – spanning 14 files and over 6,000 lines of TypeScript in `tools/AgentTool/` – is the single entry point for all delegation. Every sub-agent in Claude Code, whether a cheap read-only explorer or a persistent teammate running for hours, is spawned through this one tool:

```typescript
interface AgentInput {
  prompt: string;             // Full task description
  description: string;        // 3-5 word summary (for task lists)
  subagent_type?: string;     // "Explore" | "Plan" | "subagent" | "teammate" | "custom"
  model?: "sonnet" | "opus" | "haiku";  // Per-agent model override
  run_in_background?: boolean;  // Async execution (returns task_id)
  name?: string;              // Makes agent addressable via SendMessage
  isolation?: "worktree";     // Git worktree isolation
}
```

Every field is a lever the orchestrating agent pulls. The `model` field enables per-agent cost optimization: an Explore agent doing simple searches runs on `haiku` (cheapest), while a Subagent implementing complex logic uses `opus` (most capable). The `run_in_background` flag determines whether the parent blocks (synchronous delegation) or continues working (asynchronous execution). And `name` makes the agent addressable for follow-up messages via `SendMessage`, enabling multi-turn collaboration.

The crucial detail is what happens when `subagent_type` is omitted. When the `FORK_SUBAGENT` feature flag is active, omitting the type triggers implicit forking – the child inherits the parent’s full conversation context and system prompt. When the flag is off, the system defaults to the `general-purpose` agent type. This single conditional branch is the difference between two entirely different spawning strategies: fresh-start delegation versus context-inheriting forking.

### Two Spawn Paths – Fork vs. Fresh Agent

The codebase implements two distinct spawn paths, and the context each child receives differs dramatically between them.

**Path A: Fork.** Triggered when the model calls the Agent tool *without* specifying a `subagent_type`. The child receives the parent’s **full conversation history**, the **identical system prompt**, and the parent’s **exact tool pool** (byte-identical, for prompt cache sharing). The function `buildForkedMessages()` constructs exactly two messages to append after the parent’s conversation:

1. A clone of the parent’s last assistant message (all `tool_use` blocks, thinking blocks, text blocks).
2. A single user message containing placeholder `tool_result` blocks (identical text across all forks, again for cache sharing) plus the child’s specific task directive. The directive enforces 10 non-negotiable rules: do not re-delegate, do not converse, do not editorialize, use tools directly, stay in scope, keep the report under 500 words, begin with “Scope:”, report structured facts, then stop.

Because the system prompt, tools, and conversation prefix are byte-identical between parent and all fork children, the LLM API’s prompt cache treats all but the first child as a cache hit. Only the final directive message differs per child.

**Path B: Fresh agent.** Triggered when the model *specifies* a `subagent_type` (Explore, Plan, subagent, teammate, or custom). The child starts with **zero conversation context**. It receives only a single user message containing the task prompt. It gets its own system prompt assembled from the agent type definition, its own freshly assembled tool pool, and a fresh file state cache. It has no knowledge of what the parent discussed, what files were read, or what decisions were made.

All five named agent types use Path B. The fork path (Path A) is a separate mechanism that fires only when the type is omitted.

This is the fundamental context trade-off: fork children see everything the parent knows (expensive, high-context) while typed agents see only the task description (cheap, focused). The fork path is for tasks that require the parent’s accumulated understanding. The typed agent path is for tasks where a clean slate and a specialized role are more valuable than shared history.

The Agent tool is not just a tool – it is a meta-tool that creates new agents. From the parent’s perspective, it is a function call that returns a result. From the child’s perspective, it is the beginning of an entire agent lifecycle. This duality – tool from above, agent from within – is what makes the system recursive. See [Part IV.1](./05-tool-system.html) for how this fits into the broader tool dispatch pipeline.

---

## Five Agent Types – A Cost-Capability Spectrum

Claude Code does not have one type of sub-agent. It has five, arranged along a spectrum from cheap-and-constrained to expensive-and-capable. Choosing the right type for a task is the multi-agent equivalent of choosing the right data structure: the cheapest option that meets the requirements wins.

Think of it like hiring for a project. You would not pay a senior architect to do a grep search, and you would not ask an intern to design the system architecture. Each role has a cost, a capability set, and an appropriate scope of work.

![Figure 2: Five agent types arranged along a cost-capability spectrum. Explore agents are read-only with the cheapest Haiku model and fire-and-forget semantics. Plan agents are also read-only but produce structured implementation strategies. Custom agents are YAML-defined with configurable tool subsets. Subagents get full tool access for self-contained tasks. Teammates are persistent, named agents with bidirectional messaging via SendMessage. Cost and capability increase left to right.](assets/figure-02-fig-agent-types.png)

*Figure 2: Five agent types arranged along a cost-capability spectrum. Explore agents are read-only with the cheapest Haiku model and fire-and-forget semantics. Plan agents are also read-only but produce structured implementation strategies. Custom agents are YAML-defined with configurable tool subsets. Subagents get full tool access for self-contained tasks. Teammates are persistent, named agents with bidirectional messaging via SendMessage. Cost and capability increase left to right.*

**How to read this diagram.** Read left to right along the cost-capability spectrum. Explore (leftmost) is the cheapest and most constrained agent type – read-only, Haiku model, fire-and-forget. Each step rightward adds capability and cost, culminating in Teammate (rightmost), which has full tools, persistence, and peer messaging. The arrows represent increasing investment: choose the leftmost type that satisfies your task’s requirements.

### Explore

Explore agents are the cheapest option. Their system prompt opens with a bold block you cannot miss:

> *“=== CRITICAL: READ-ONLY MODE ===”*

This is not a polite suggestion. The prompt includes a prominent **READ-ONLY MODE** block that explicitly prohibits all file writes, creates, deletes, moves, and redirects. Tools are restricted at the registry level to `Read`, `Glob`, `Grep`, `WebFetch`, and a `Bash` that rejects any write command. Even if the model attempts to call `Write`, the call is rejected before execution. The model is set to `haiku` – the cheapest available – because search does not require frontier reasoning.

An important cost optimization: Explore agents have `omitClaudeMd: true`, which strips the CLAUDE.md instruction hierarchy from their context. Critically, git status is also omitted – another token-saving measure that compounds at scale. The code comment notes this *“saves ~5-15 Gtok/week across 34M+ Explore spawns.”* That is an extraordinary number – 34 million Explore agents per week – and explains why shaving even a few hundred tokens per spawn matters at fleet scale. Explore agents are fire-and-forget: spawn, search, return findings, terminate.

### Plan

Plan agents share Explore’s read-only tool restriction but serve a fundamentally different purpose: they produce structured implementation plans. The separation of planning from execution is deliberate. Planning requires broad context (reading many files to understand architecture) but minimal capability (no writing). Execution requires deep capability but narrower context (working on one file at a time). Splitting these avoids the context window pressure of doing both in one agent.

The Plan agent’s prompt enforces a structured four-phase reasoning process with named stages: (i) **Understand Requirements**, (ii) **Explore Thoroughly**, (iii) **Design Solution**, and (iv) **Detail the Plan**. The required output includes a **“Critical Files for Implementation”** section listing 3 to 5 files that are central to the planned changes. This structured output ensures that plans are actionable rather than abstract.

Plan agents also carry `omitClaudeMd: true` and omit git status, matching the same cost optimizations as Explore – they can read CLAUDE.md directly if needed, but carrying it in every spawn’s context is wasted tokens.

### Custom

Custom agents are defined by markdown files in `.claude/agents/` with YAML frontmatter specifying name, description, tool allowlist/denylist, model, permission mode, hooks, MCP servers, skills, memory scope, and isolation mode. The `loadAgentsDir.ts` file (756 LOC) discovers and parses these definitions, supporting agents from five sources: built-in, plugin, user settings, project settings, and managed policy settings. When sources conflict, later sources override earlier ones – project overrides user, managed overrides project. A “security-reviewer” agent can be restricted to read-only tools while an “api-doc-writer” gets `Write` access but no `Bash`. This fine-grained capability control is the extension point for team workflows.

### Subagent

Subagents (also referred to as the “general-purpose” type) get full tool access (`tools: ['*']`) and operate fire-and-forget. The parent spawns a subagent with a self-contained task (“Implement the `UserService` class”), it executes, and returns. Its system prompt is spare:

> *“Complete the task fully – don’t gold-plate, but don’t leave it half-done.”*

Unlike Explore and Plan, the general-purpose subagent **includes the full CLAUDE.md instruction hierarchy and git status** in its context. This is a deliberate trade-off: subagents perform write operations and need project conventions, coding standards, and repository state to produce correct output. The additional prompt cost is justified because subagents are spawned far less frequently than Explore agents, and their tasks require the richer context.

Subagents are appropriate when the task is well-defined and needs full capability but no follow-up interaction.

### Teammate

Teammates are the most sophisticated type. Unlike all others, they are persistent and named. They do not terminate after returning a result – they go idle, consuming zero compute, waiting for new messages via SendMessage. Teammates get the full tool set plus coordination tools (`TaskCreate`, `TaskGet`, `TaskList`, `TaskUpdate`, `SendMessage`). Their system prompt is the most expensive: the full main agent prompt, custom instructions, and team memory.

The idle-wake cycle is key to teammate economics. When a new message arrives, the teammate wakes with full context from its previous work, processes the message, and either responds or goes idle again. This is the coroutine pattern applied to agents: suspend at yield points, resume with state intact.

---

## Subagent Prompt Assembly – What Each Type Receives

**Each agent type receives a fundamentally different system prompt, assembled by a dedicated function (`dQ6()`) that composes three parts: an agent-specific prompt, thread notes, and environment info. The cost difference between types is not just about model selection – it is about prompt size.**

The main agent’s system prompt (`DX()`) runs approximately 20 KB across 17 sections. Sub-agents receive dramatically smaller prompts – the Explore agent’s prompt is roughly 3 KB, a 7x reduction. This size difference is a direct cost optimization: at 34 million Explore spawns per week, every kilobyte matters.

The `dQ6()` assembly function constructs every sub-agent prompt from three parts:

![Figure 3: Subagent prompt assembly via the dQ6() function. Three parts compose into a type-specific system prompt: Part I is the agent-specific prompt (varying from 3 KB for Explore to 20 KB for Teammate), Part II contains thread notes with behavioral constraints (absolute paths, no emojis), and Part III provides runtime environment info (CWD, git status, platform). The 7x size difference between Explore and Teammate prompts is a primary lever for cost control at fleet scale.](assets/figure-03-fig-subagent-prompt.png)

*Figure 3: Subagent prompt assembly via the dQ6() function. Three parts compose into a type-specific system prompt: Part I is the agent-specific prompt (varying from 3 KB for Explore to 20 KB for Teammate), Part II contains thread notes with behavioral constraints (absolute paths, no emojis), and Part III provides runtime environment info (CWD, git status, platform). The 7x size difference between Explore and Teammate prompts is a primary lever for cost control at fleet scale.*

**How to read this diagram.** Start from the three input boxes on the left (Part I: Agent-Specific Prompt, Part II: Thread Notes, Part III: Environment Info), which all feed into the central dQ6() assembly function. From there, follow the arrows right to see the five output variants, each labeled with its approximate prompt size. The key takeaway is the 7x size difference between Explore (~3 KB) and Teammate (~20 KB), which is the primary lever for cost control at fleet scale.

**Part I.2: Agent-Specific Prompt.** This is where the types diverge. Each type receives a prompt tuned to its role:

| Type | Opening Line | Key Directives |
| --- | --- | --- |
| **Explore** | *“You are a file search specialist for Claude Code”* | `=== CRITICAL: READ-ONLY MODE ===`; restricted to Glob, Grep, Read, WebFetch, Bash (read-only) |
| **Plan** | *“You are a software architect and planning specialist”* | Read-only; four phases: Understand, Explore, Design, Detail |
| **General-purpose** | *“You are an agent for Claude Code. Given the user’s message, use tools to complete”* | Full tool access; no restrictions |
| **Custom** | User-defined in `.claude/agents/*.md` | YAML frontmatter specifies tool allowlist/denylist, model, permissions |
| **Teammate** | Full main agent `DX()` prompt + custom instructions + team memory | All tools + `SendMessage` + `TaskCreate/Get/List/Update`; persistent, named |

The Explore and Plan prompts share a critical optimization: `omitClaudeMd: true`. This strips the CLAUDE.md instruction hierarchy – which can be 5–15 KB of project-specific instructions – from the sub-agent’s context. The code comment notes this saves *“~5–15 Gtok/week across 34M+ Explore spawns.”* The sub-agent can always `Read` the CLAUDE.md file directly if needed, but carrying it in every spawn’s system prompt is wasted tokens at fleet scale.

**Part II.1: Thread Notes.** A set of behavioral constraints shared across all sub-agent types. All agent types share four specific thread notes appended to their prompt: (1) use absolute file paths (because the child’s working directory resets between Bash calls), (2) no emojis, (3) no colons before tool calls, and (4) include code snippets only when the exact text is load-bearing (e.g., a bug found, a function signature requested). These are the “house rules” that prevent sub-agents from producing output that confuses the parent.

**Part III.1: Environment Info.** Runtime context injected into every sub-agent: current working directory, git status snapshot, platform (darwin/linux), shell type, OS version, model ID, and knowledge cutoff date. This ensures every sub-agent knows where it is and what it is running on without needing to discover this information via tool calls.

The Teammate type deserves special attention. Its Part I.2 includes the *entire* main agent prompt (`DX()`) – all 17 sections, all behavioral rules – plus custom agent instructions and synchronized team memory. This is why Teammates are the most expensive type: their prompt alone costs as much as the main agent’s. The justification is that Teammates are persistent and long-running; they amortize this startup cost over many interactions, unlike fire-and-forget types that pay it once and terminate.

The prompt size spectrum – 3 KB for Explore, 20 KB for Teammate – is not incidental. It is the primary lever for cost control in a system that spawns millions of sub-agents per week. Every fragment included in a sub-agent’s prompt is a deliberate choice: worth the tokens for the capability it provides, or stripped to save budget. This is the same principle as the [prompt assembly pipeline](./03-prompt-assembly.html)’s conditional inclusion – but applied at the agent level rather than the fragment level.

---

## Worktree Isolation – Process Isolation for Code Changes

When two agents edit the same file in parallel, they clobber each other’s changes. Git worktrees solve this by giving each agent its own working copy of the repository – process isolation applied to the filesystem. This is the most operationally important feature in the multi-agent system.

Setting `isolation: "worktree"` in the Agent tool input creates a separate git worktree for the child agent. A git worktree is an independent working directory linked to the same `.git` object database. Each worktree can be on a different branch, with different uncommitted changes, without interference.

![Figure 4: Git worktree isolation for parallel agent work. The main repository and two worktrees (A and B) share the same .git object database but maintain independent working directories. Agent A modifies auth.ts while Agent B modifies api.ts, with no interference – analogous to copy-on-write virtual memory where pages are shared until written. Conflict resolution defers to merge time, mirroring how human developers use branches.](assets/figure-04-fig-worktree.png)

*Figure 4: Git worktree isolation for parallel agent work. The main repository and two worktrees (A and B) share the same .git object database but maintain independent working directories. Agent A modifies auth.ts while Agent B modifies api.ts, with no interference – analogous to copy-on-write virtual memory where pages are shared until written. Conflict resolution defers to merge time, mirroring how human developers use branches.*

**How to read this diagram.** The center subgraph (Main) contains the shared .git object database, while Worktree A and Worktree B on either side are independent working directories. Dashed arrows from .git to each worktree indicate shared objects. Notice that auth.ts is bold/modified in Worktree A while api.ts is bold/modified in Worktree B – each agent edits different files in its own copy with no interference, and conflicts are deferred to merge time.

The analogy to process isolation is precise. In an OS, each process gets its own virtual address space. Writing to address `0x1000` in process A does not affect address `0x1000` in process B. Similarly, editing `auth.ts` in Worktree A has no effect on `auth.ts` in Worktree B or in the main directory. Conflict resolution happens at merge time, not at write time – the same as IPC versus shared memory.

When a fork child runs in a worktree, it receives a special notice via `buildWorktreeNotice()`:

> *“You’ve inherited the conversation context above from a parent agent working in [parentCwd]. You are operating in an isolated git worktree at [worktreeCwd] – same repository, same relative file structure, separate working copy. Paths in the inherited context refer to the parent’s working directory; translate them to your worktree root.”*

The lifecycle is carefully managed. The `createAgentWorktree` utility creates the worktree. If the agent completes without changes (checked by `hasWorktreeChanges`), the worktree is cleaned up automatically by `removeAgentWorktree`. If changes persist, the worktree path and branch are returned in the agent’s result for the parent to review, merge, or discard. This mirrors how human developers work: branch, make changes, open a PR, merge or close. No stale directories accumulate.

---

## The Teammate Protocol – Persistent Peer Collaboration

Where all other agent types are fire-and-forget, the Teammate system introduces persistence, naming, and bidirectional messaging. Teammates differ from other types in three fundamental ways.

First, they are **persistent and named** – they do not terminate after returning a result. Instead, they go idle, consuming zero compute, waiting for a new message via `SendMessage`. Second, they communicate **bidirectionally** – any teammate can message any other teammate directly, forming a mesh topology rather than a star. Third, they share **team memory** – a synchronized knowledge base that persists across sessions and is invisible to agents outside the team.

The `SendMessage` tool enables peer-to-peer communication. When teammate `backend-dev` needs to tell `frontend-dev` about an API contract change, it calls `SendMessage({ to: "frontend-dev", message: "..." })`. The message arrives as a user-role message in the target’s conversation, waking it from idle if necessary. This enables emergent coordination: the backend developer can negotiate an API contract with the frontend developer without routing every message through the main agent. The test writer can ask the backend developer to clarify an edge case. The main agent need not be the bottleneck for every inter-agent communication.

In-process teammates (checked via `isInProcessTeammate()`) share the terminal with the parent and can show permission prompts. Remote and background teammates cannot. The system tracks this distinction through the `canShowPermissionPrompts` parameter, which determines whether the agent’s permission mode should auto-deny prompts or bubble them to the user.

Team memory is synchronized through `services/teamMemorySync/`, which implements a full sync protocol with an Anthropic backend server. The data model is flat key-value storage: keys are file paths relative to the team memory directory (like `MEMORY.md`, `patterns.md`), values are UTF-8 string content. The sync protocol handles conflicts via version numbers and ETags, with per-key checksums for efficient diff detection. A secret scanner (`secretScanner.ts`) and `teamMemSecretGuard.ts` prevent accidental leakage of credentials into team memory.

---

## Swarm Coordination – Coordinator Mode

Coordinator Mode replaces the normal agent loop with a hub-and-spoke delegation model. Feature-flagged under `COORDINATOR_MODE`, this mode is activated by the `CLAUDE_CODE_COORDINATOR_MODE` environment variable and is mutually exclusive with fork-based spawning. The coordinator plans and delegates; workers execute and report. Workers cannot see each other and cannot communicate directly.

The coordinator’s system prompt is a 369-line document that defines the entire orchestration protocol, organized into four phases:

![Figure 5: Coordinator Mode’s four-phase workflow (Research, Synthesis, Implementation, Verification) paired with its hub-and-spoke topology. Workers investigate the codebase in parallel during Research, the Coordinator synthesizes findings into implementation specs, workers make targeted changes, then workers verify the changes compile and pass tests. Workers are invisible to each other – all communication routes through the central Coordinator, making this a MapReduce-style orchestration pattern.](assets/figure-05-fig-coordinator.png)

*Figure 5: Coordinator Mode’s four-phase workflow (Research, Synthesis, Implementation, Verification) paired with its hub-and-spoke topology. Workers investigate the codebase in parallel during Research, the Coordinator synthesizes findings into implementation specs, workers make targeted changes, then workers verify the changes compile and pass tests. Workers are invisible to each other – all communication routes through the central Coordinator, making this a MapReduce-style orchestration pattern.*

**How to read this diagram.** The top subgraph shows the four-phase workflow reading left to right: Research, Synthesis, Implementation, Verification. Below it, the Hub-and-Spoke subgraph shows the Coordinator at the center with arrows fanning out to three workers (W1, W2, W3). Workers cannot see or message each other – all communication routes through the Coordinator, making this a centralized MapReduce-style orchestration pattern where the coordinator is both planner and bottleneck.

The coordinator prompt contains two striking anti-patterns that are explicitly forbidden:

> *“Never write ‘based on your findings, fix the bug’ or ‘based on the research, implement it.’ Those phrases push synthesis onto the agent instead of doing it yourself.”*

This forces the coordinator to actually understand research results before delegating implementation.

> *“After launching agents, briefly tell the user what you launched and end your response. Never fabricate or predict agent results in any format.”*

This prevents the coordinator from hallucinating results it has not received.

Worker results arrive as `<task-notification>` XML in user-role messages. The coordinator parses the notification, extracts the result, and decides the next action: continue the worker (via `SendMessage` with the agent ID), spawn a fresh one, or report to the user. The decision of continue vs. spawn is governed by context overlap:

> *“High overlap – continue. Low overlap – spawn fresh.”*

### Coordinator vs. Teammates

The two orchestration models represent a classic systems trade-off:

| Dimension | Coordinator Mode | Teammate System |
| --- | --- | --- |
| **Topology** | Hub-and-spoke (star) | Mesh (peer-to-peer) |
| **Worker lifecycle** | Fire-and-forget, stateless | Persistent, named, idle/wake |
| **Communication** | One-way delegation | Bidirectional messaging |
| **State management** | All state in coordinator | Distributed + shared team memory |
| **Inter-worker visibility** | Workers cannot see each other | Teammates can DM peers |
| **Best for** | Parallel batch processing | Collaborative, interdependent work |

---

## Resource Management – Token Budgets, Models, and Cleanup

Sub-agents need resource limits for the same reason OS processes do: without them, one runaway agent consumes the entire budget. Claude Code enforces several constraints at multiple levels.

**Max turns.** Each agent defaults to 200 turns, configurable via frontmatter. This is the equivalent of `ulimit -t` – a hard CPU time limit that prevents infinite loops. When the limit is reached, the agent receives a `max_turns_reached` attachment message and stops.

**Per-agent model selection.** The `model` field in the Agent tool input controls per-turn cost. Explore on haiku costs a fraction of Subagent on opus. The `getAgentModel()` function resolves the effective model through a cascade: explicit tool input overrides agent definition, which overrides parent model, which overrides the default. Custom agents can specify `model: 'inherit'` to match the parent.

**Permission bubbling.** Fork agents use `permissionMode: 'bubble'` – permission prompts surface to the parent terminal rather than being silently denied or independently handled. This prevents 10 concurrent agents from each prompting the user simultaneously.

**Cache-aware forking.** The fork path is not just another spawning strategy – it is a cache optimization that transforms the cost of multi-agent work from linear to near-constant. The function `buildForkedMessages` ensures that all fork children start with byte-identical prompt prefixes. LLM APIs cache prompt prefixes; if two requests share the same prefix, the second gets a cache hit. By making fork children byte-identical up to the fork point, Claude Code pays full prompt cost once and gets cache hits for all subsequent children.

![Figure 6: Cache-aware forking exploits LLM prompt caching. All fork children start with a byte-identical prefix (system prompt + tool descriptions + conversation history + fork boilerplate). Child 1 pays the full prompt cost. Children 2 through N get cache hits on the shared prefix, paying only for their unique task directive. This transforms multi-agent cost from O(N x M) to approximately O(M + N x delta), yielding 70-85% cost reduction at scale.](assets/figure-06-fig-cache-forking.png)

*Figure 6: Cache-aware forking exploits LLM prompt caching. All fork children start with a byte-identical prefix (system prompt + tool descriptions + conversation history + fork boilerplate). Child 1 pays the full prompt cost. Children 2 through N get cache hits on the shared prefix, paying only for their unique task directive. This transforms multi-agent cost from O(N x M) to approximately O(M + N x delta), yielding 70-85% cost reduction at scale.*

**How to read this diagram.** Start at the top with the Shared Prefix box, which represents the byte-identical portion (system prompt, tool descriptions, conversation history, fork boilerplate) common to all children. Follow the three arrows down to the children: Child 1 pays full cost because it is the first to process the prefix, while Children 2 and 3 get cache hits on the shared prefix and pay only for their unique task directives. This transforms multi-agent cost from linear to near-constant.

The cost savings are dramatic. For 5 fork agents, the first child pays full cost for the shared prefix. Children 2 through 5 get cache hits on that prefix, paying only for their unique directive. Without forking, 5 agents at \(M\) prompt tokens each costs \(5M\) tokens. With forking, it costs approximately \(M + 4\delta\) – about a 70% reduction.

**State access boundaries** enforce isolation through three distinct patterns:

| Function | Behavior | Purpose |
| --- | --- | --- |
| `setAppState` | No-op for async agents | Prevents race conditions in parent’s state |
| `setAppStateForTasks` | Always reaches root agent | Task progress must be globally visible |
| `getAppState` | Returns root agent’s state (read-only) | Consistent view without mutation risk |

**Cleanup.** When an agent terminates, `runAgent` cleans up eight distinct resources in its `finally` block: agent-specific MCP servers, session hooks, prompt cache tracking state, cloned file state cache, fork context messages, Perfetto trace entries, transcript subdirectory mappings, orphaned todo entries, and background bash tasks. In a system that spawns 34 million Explore agents per week, even tiny per-agent leaks become catastrophic at scale. This is the agent equivalent of a destructor in RAII: every resource acquired during agent startup must be released during shutdown.

---

## Memory Hierarchy – What Is Shared, What Is Private

The multi-agent memory model has four scopes, arranged like a CPU cache hierarchy: each level is larger, slower to update, and shared more broadly.

Agent memory is the innermost scope – private working state that dies when the agent terminates. It is the agent’s scratchpad: intermediate search results, partial analyses, draft plans. No other agent sees it. This is L1 cache: the fastest, most private, most volatile.

Team memory is synchronized across all teammates in a team via `services/teamMemorySync/`. The sync protocol uses versioned entries with ETags for conflict detection. Team memory is invisible to agents outside the team. This is L2 cache: shared within a group, with coherence protocols.

**Session memory** survives context compaction – the process where older messages are summarized to free context space (see [Part III.1](./03-prompt-assembly.html)). Session memory entries are preserved across compaction and re-injected into the context. This is L3 cache: survives local eviction, re-filled after capacity events.

**MEMORY.md** is the outermost scope – global project memory, persisted to disk, readable by all agents across all sessions. It lives in `.claude/` at the project root, with three sub-scopes: user-level, project-level, and local (not checked into version control). This is main memory: persistent, globally accessible, the authoritative record.

The layered approach prevents the “noisy neighbor” problem. One agent’s intermediate findings do not pollute another’s context window. Global decisions flow down (all agents read MEMORY.md). Team decisions stay within teams. Working state stays private. This is the same principle that makes CPU cache hierarchies work: data locality determines placement.

---

## When to Spawn – The Agent Selection Decision

Not every task needs multi-agent coordination. The overhead of spawning, managing, and synthesizing across agents is only justified when the task exceeds what a single context window can handle – or when the intermediate output is not worth keeping in the parent’s context.

A critical architectural point: the spawning decision is **entirely model-driven**. There is no programmatic heuristic that forces sub-agent creation. The model sees the Agent tool in its tool menu, listed alongside Read, Bash, Edit, and every other tool, and decides autonomously whether to invoke it. The Agent tool’s description includes guidance on when delegation is appropriate, examples of effective sub-agent prompts, and descriptions of the available agent types. From the model’s perspective, spawning a sub-agent is an ordinary tool call that returns a text result. The system imposes no rule like “if task complexity exceeds threshold X, spawn a child.” The model reads the context, evaluates its own capacity, and makes the call.

The fork prompt captures this decision criterion directly:

> *“Fork yourself when the intermediate tool output isn’t worth keeping in your context. The criterion is qualitative – ‘will I need this output again’ – not task size.”*

The prompt also warns against two failure modes:

> *“Don’t peek”*: do not read the fork’s output file mid-execution – it pulls tool noise into the parent’s context, defeating the purpose.
> 
> *“Don’t race”*: do not fabricate or predict results before the notification arrives.

The principle is straightforward: the cheapest agent type that can do the job is the right choice. Using Teammates for tasks that could be handled by Subagents wastes tokens on idle management overhead. Using Subagents for tasks that only need a search wastes tokens on unnecessary tool capabilities in the system prompt. Using Explore for tasks that need file edits wastes the agent’s time on rejected tool calls.

---

## Summary

Several design principles emerge from Claude Code’s multi-agent architecture that generalize beyond this specific system.

**Sub-agents are fork() for AI.** Same binary, different context, isolated working directory. The mental model from OS process management – fork, exec, wait, collect – transfers directly. The coordination complexity is also the same: shared state is dangerous, message passing is safe, and every child needs resource limits. The code does not hide this connection; it embraces it with function names like `buildForkedMessages`, `isInForkChild`, and `FORK_SUBAGENT`.

**Five agent types exist because different tasks have different requirements.** Explore at one end is cheap and constrained. Teammates at the other end are expensive and maximally capable. The implementation chooses the cheapest type that satisfies the task’s requirements — the same reasoning behind choosing the right data structure.

**Git worktrees are process isolation for code changes.** The same way virtual memory prevents processes from corrupting each other’s state, worktrees prevent agents from clobbering each other’s files. Conflict resolution happens at merge time, just like with human developers on separate branches. The alternatives – file locking, operational transforms, or restricting agents to non-overlapping files – all have worse trade-offs.

**Cache-aware forking transforms linear cost into near-constant cost.** By ensuring byte-identical prompt prefixes across children, the system pays once and caches N-1 times. At 34 million Explore spawns per week, the fleet-scale savings are measured in billions of tokens. This is the COW fork analogy made concrete: share everything, copy only what diverges.

**Centralized vs. decentralized orchestration is a classic systems trade-off.** Coordinator Mode (MapReduce-style, coordinator is the bottleneck) vs. Teammates (actor model, more complex but higher throughput). Neither is universally better – the task structure determines the choice. Independent parallel tasks want a coordinator. Interdependent collaborative tasks want teammates.

**Context is the bottleneck, not compute.** Every design decision in the sub-agent system traces back to the scarce context window. Fork children keep intermediate outputs out of the parent’s context. Explore agents strip CLAUDE.md to save tokens. One-shot agents skip the SendMessage trailer. The 500-word report limit on forks. Everything is token economics – the same constraint that drives the prompt assembly pipeline described in [Part III.1](./03-prompt-assembly.html) and the architecture overview in [Part I.1](./00-birds-eye-architecture.html).

---

*For the CLI interface through which users interact with multi-agent sessions, see [Part V.1 – CLI, Commands & UI](./08-cli-commands-ui.html). For the end-to-end workflow that ties the agent loop, tools, and orchestration together, see [Part I.2 – End-to-End Workflow](./01-end-to-end-workflow.html).*
