# 22580：从 GPT-2 到 Kimi K3，详解

原文作者：[@waterloo_intern](https://x.com/waterloo_intern/status/2081762065392541951)

译注：本文按照原文顺序翻译。模型、算法和硬件术语第一次出现时保留英文，代码块及其标识符按原文保留，原文图示继续使用作者发布的图片。

![原文图示 1](https://pbs.twimg.com/media/HOPBpfvaoAA1hox?format=jpg&name=medium)

二万二千五百八十。

这就是一个 Kimi K3（2026）的参数量所能容纳的 GPT-2（2019）模型数量。七年间，我们把规模扩大了 22,580 倍。但变化真的只是……规模吗？

在这篇工作记录中，我会带你回顾我们是怎样走到今天的，以及从那时起，真正发生的改变究竟有多少——或者有多么少。我们将沿着通往 Kimi K3 的路径，梳理其中最重要的架构进展。

![原文图示 2](https://pbs.twimg.com/media/HOPJNzLaUAA2lE7?format=jpg&name=medium)

## GPT-2

GPT-2 是一种纯解码器（decoder-only）架构：

> 代码块 1：GPT-2 主干前向传播。

```python
tok_emb = self.transformer.wte(idx) # token embeddings of shape (b, t, n_embd)
pos_emb = self.transformer.wpe(pos) # position embeddings of shape (t, n_embd)
x = self.transformer.drop(tok_emb + pos_emb)
for block in self.transformer.h:
    x = block(x)
x = self.transformer.ln_f(x)
logits = self.lm_head(x)
return logits
```

输入首先获得 token embedding 和 position embedding：

![原文图示 3](https://pbs.twimg.com/media/HOPB7byaQAEfxxf?format=jpg&name=medium)

把单个 Transformer block 放大来看，它的结构如下：

> 代码块 2：带有注意力层和 MLP 的 Transformer block。

```python
class Block(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.ln_1 = LayerNorm(config.n_embd, bias=config.bias)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = LayerNorm(config.n_embd, bias=config.bias)
        self.mlp = MLP(config)

    def forward(self, x):
        x = x + self.attn(self.ln_1(x))
        x = x + self.mlp(self.ln_2(x))
        return x
```

![原文图示 4](https://pbs.twimg.com/media/HOPB9OXbwAAmP85?format=jpg&name=medium)

注意力的计算过程如下：

> 代码块 3：GPT-2 的因果自注意力实现。

```python
        B, T, C = x.size() # batch size, sequence length, embedding dimensionality (n_embd)

        # calculate query, key, values for all heads in batch and move head forward to be the batch dim
        q, k, v  = self.c_attn(x).split(self.n_embd, dim=2)
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)

        # manual implementation of attention
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        att = att.masked_fill(self.bias[:,:,:T,:T] == 0, float('-inf'))
        att = F.softmax(att, dim=-1)
        att = self.attn_dropout(att)
        y = att @ v # (B, nh, T, T) x (B, nh, T, hs) -> (B, nh, T, hs)
        y = y.transpose(1, 2).contiguous().view(B, T, C) # re-assemble all head outputs side by side

        # output projection
        y = self.resid_dropout(self.c_proj(y))
        return y
```

得到最终的隐藏状态矩阵之后，语言模型头会把它映射为整个词表上的 logits。在自回归解码过程中，选择下一个 token 时，只需要最后一个位置的 logits。

> 这暴露了纯解码器生成过程中的一处低效：模型会计算输入中每个位置的表示，但在每一步解码时，实际只消费最后一个位置的 logits。如果不做缓存，为生成下一个 token，其中大量计算还会再重复一次。

![原文图示 5](https://pbs.twimg.com/media/HOPCABLaAAApmFz?format=png&name=medium)

KV Cache 来自一个非常直接的观察：在输入末尾追加刚生成的 token 后，如果什么都不缓存，模型就必须重新计算此前所有 token 的投影。保存这些 token 的 Key 和 Value 向量，就能避免这部分重复工作。

保存这些向量的空间就是 KV Cache。它会保留前面 `N-1` 个 token 的向量，体积可能膨胀到足以形成显存带宽瓶颈。

总体来看，假设词表大约有 5 万个 token、12 个 block、12 个注意力头，embedding 维度为 768，那么这个基线模型大约有 1.24 亿个参数。

> 代码块 4：GPT-2 的词表、层数、注意力头数和 embedding 维度配置。

```python
vocab_size: int = 50304 # GPT-2 vocab_size of 50257, padded up to nearest multiple of 64 for efficiency
n_layer: int = 12
n_head: int = 12
n_embd: int = 768
```

Kimi K3 有 2.8 万亿个参数。因此，仅从参数量来看，一个 Kimi K3 大致相当于 22,580 个 GPT-2。

## 线性注意力

Softmax 注意力先计算 `q·k`，然后再施加非线性，因此每个 Query 都会与每个 Key 发生耦合。线性注意力则分别对 `q` 和 `k` 应用某种特征映射，例如 `ELU+1`。这样一来，乘法就可以重新结合，不断增长的 K、V 向量集合也能被折叠进一个固定大小的 `D×D` 状态。

论文里关于 `O(N²)` 的表述一开始让我有些困惑。“Transformer 每个时间步的成本，会随当前序列长度的平方增长”这句话并不准确——FlashAttention 解决的不正是这个问题吗？……后来我才注意到，这篇论文发表于 2020 年。

在当时，训练通常会显式构造完整的 `N×N` 注意力矩阵；FlashAttention 还没有出现；用于说明原理的自回归实现也经常没有 KV Cache，而是反复计算整个 token 历史。

> 代码块 5：带 KV Cache 的标准 Softmax 注意力。

```python
def forward(self, x, mask=None, past_kv=None):
  # x is b,t,d
  b,t,d=x.shape
  d_head=d//self.num_heads
  h=self.num_heads
  qkv=self.qkv_proj(x)

  q=qkv[:, :, :d].view(b,t,h,d_head).transpose(1,2)
  k=qkv[:, :, d:2*d].view(b,t,h,d_head).transpose(1,2)
  v=qkv[:, :, 2*d:].view(b,t,h,d_head).transpose(1,2)

  # at prefill, q,k,v have shapes b,h,t,d
  # at decode, shape is b, h, 1, d
  # so i cat at the t dimension, dim(2)

  if past_kv is not None:
    k_past=past_kv[0]
    v_past=past_kv[1]
    k=torch.cat((k_past, k), dim=2)
    v=torch.cat((v_past, v), dim=2)

  scores=(q@k.transpose(-1,-2))/math.sqrt(d_head)
  if past_kv is None: #we're in prefill and need to mask
    causal_mask=torch.ones(t,t,dtype=bool, device=q.device)
    causal_mask=torch.triu(causal_mask, diagonal=1)
    scores=scores.masked_fill(causal_mask, float('-inf'))

  if mask is not None:
    scores=scores.masked_fill(~mask, float('-inf'))

  #get attn (bhtt x bhtd)
  attn=scores.softmax(-1)#bhtt
  o=attn@v #bhtd
  o=o.transpose(1,2).contiguous().view(b,t,d)  #b,t,d

  # use x to get qkv
  o_proj=self.o_proj(o)
  past_kv=(k, v)
  return o_proj, past_kv
```

用图来观察同一过程会更直观。每一步解码都要从 HBM 执行两次 `ND` 规模的读取和两次 `1D` 规模的写入；与此同时，KV Cache 会以 `O(N)` 的速度随序列长度线性增长。

![原文图示 6](https://pbs.twimg.com/media/HOPCIK6b0AADP6e?format=png&name=large)

注意其中过量的读写。论文用下面的方法替代了它：

> 代码块 6：把历史 K、V 折叠到固定状态 `S` 和归一化状态 `z` 中的线性注意力。

```python
def forward(self, x, mask=None, cache=None):
  # x is b,t,d
  b,t,d=x.shape
  d_head=d//self.num_heads
  h=self.num_heads
  qkv=self.qkv_proj(x)

  q=qkv[:, :, :d].view(b,t,h,d_head).transpose(1,2)
  k=qkv[:, :, d:2*d].view(b,t,h,d_head).transpose(1,2)
  v=qkv[:, :, 2*d:].view(b,t,h,d_head).transpose(1,2)

  k=F.elu(k)+1
  k=k.transpose(-1,-2)
  q=F.elu(q)+1

  S,z=cache if cache is not None else (0.0, 0.0)
  S=S+k@v
  z=z+k

 o=q@S #bhtd
 denom=q@z
 o_scaled=o/denom
 o_scaled=o_scaled.transpose(1,2).contiguous().view(b,t,d)
 o_proj=self.o_proj(o_scaled)
 cache=(S,z)

 return o_proj, cache
```

这里存在一项取舍。

我们不再像 Softmax 那样，在 `q` 与 `k` 相互作用后使用指数函数；而是在二者相互作用之前，分别对它们应用 `ELU+1`。两种方法都会对最后得到的分数进行归一化，但线性注意力使用的特征映射，只是对 Softmax kernel 的一种表达能力较弱的近似。

这种近似可能降低信息保真度，不过实际损失多少精度，仍取决于具体架构和任务负载。

还要注意，我们仍然需要除以全部 `qk` 的和；为了简化，图中省略了这一步。从高层来看，注意力包含三个步骤：

1. 让 `qk` 分数变为非负数。线性注意力使用 `ELU+1`，Softmax 使用指数函数。
2. 除以所有分数的总和。
3. 对 Value 计算加权平均。

因此，线性注意力仍然满足注意力机制的基本约定，只是用表达能力较弱的特征映射，让 QK 分数保持非负。

## DeltaNet（Fast Weight Programmers）

容量有限的缓存必须覆盖已有信息，或者把新信息与已有信息合并。来自第 `i-1` 个 token 的状态不会获得一个独立槽位，而是被加进同一个 `D×D` 矩阵。因此，新的 Query 无法再从中取回每个早期 token 完全彼此隔离的表示。

但这种加法也正是效率提升的来源。通过相加而不是拼接来更新缓存，可以避免缓存以 `O(N)` 的速度增长；可同一个操作也会让不同信息相互干扰。DeltaNet 要解决的，就是这种信息不可恢复的问题。

![原文图示 7](https://pbs.twimg.com/media/HOPCYjNbAAAMe7P?format=png&name=medium)

Schlag 在《Fast Weight Programmers》论文中很准确地描述了这个问题：

> 当序列长度超过存储容量时，模型可能进入容量过载状态。为了在这种状态下正常工作，模型应该学会与记忆内容动态交互，并有选择地决定保留哪些 Key–Value 关联、删除哪些关联。纯加法式的写入指令可能并不适合这种用途……像公式 17 那样，不断向有限大小的记忆中添加新关联，最终必然会触及极限。

让线性注意力具有吸引力的工作区间——`N` 远大于 `D`——也恰好暴露了它最主要的局限。一旦状态超出其有效容量，关联就会开始彼此干扰，因为更新只有加法，没有任何东西会离开缓存。

> 代码块 7：带有逐 token 写入强度 `beta` 的 Delta 更新。

```python
def forward(self, x, mask=None, cache=None):
  # x is b,t,d
  b,t,d=x.shape
  d_head=d//self.num_heads
  h=self.num_heads
  qkv=self.qkv_proj(x)

  q=qkv[:, :, :d].view(b,t,h,d_head).transpose(1,2)
  k=qkv[:, :, d:2*d].view(b,t,h,d_head).transpose(1,2)
  v=qkv[:, :, 2*d:].view(b,t,h,d_head).transpose(1,2)

  q = F.normalize(F.silu(q), dim=-1)
  k = F.normalize(F.silu(k), dim=-1)
  beta = torch.sigmoid(self.w_beta(x)).view(b, 1, t, 1)
  # new: per-token write strength

  S = cache if cache is not None else 0.0

  v_old = k @ S # read the board at this key
  u = beta * (v - v_old) # the delta: only what's actually new
  S = S + k.transpose(-1, -2) @ u # same outer-product write as before

  o = q @ S # read, no denominator
  o = o.transpose(1, 2).contiguous().view(b, t, d)
  return self.o_proj(o), S
```

用一个可视化例子更容易理解。

![原文图示 8](https://pbs.twimg.com/media/HOPCc7BaEAAQDtO?format=jpg&name=medium)

假设我们把一条关联写成 `S = kᵀ @ v`。如果随后使用同一个 Key 读回，就会得到 `k @ (kᵀ @ v)`，也就是 `(k @ kᵀ)v`。它等于 `k` 的范数平方乘以 `v`。

换句话说，读取得到的是一个按 Key 范数平方缩放过的结果。如果把 `k` 归一化到单位长度，或者用结果除以这个范数，就可以精确取回 `v`。

Q 同样是一个学习得到的指针。`Wq` 和 `Wk` 读取同一条残差流；当模型要查询某项事实时，其 Query 会指向写入该事实时所使用的 Key 方向。

更新时，模型首先询问：当前 Key 能从缓存里取回什么信息？然后从我们希望存入的 Value 中减去已有信息，将 Key 与这个差值相乘，再把结果加回状态。这样，旧信息被移除，新信息被写入原来的位置。

## DeltaNet（使用 Delta Rule 并行化线性 Transformer）

这是整篇文章最难的一节。我花了大约七个小时，才形成一套能够实际工作的理解，所以接下来会从实现出发逐步解释。

简而言之，DeltaNet 实现了一阶线性递归，并使用广义 Householder 转移矩阵，使模型能够按 chunk 并行执行前向传播，从而在硬件上高效地进行线性时间训练。它把输入与输出划分为若干个大小为 `C` 的 chunk；每个 chunk 的输出，由前一个 chunk 的最终状态，以及当前 chunk 的 Query、Key、Value block 共同计算得到。

实际要解决的问题是 prefill。直接在长度为 `T` 的序列上执行 Delta Rule，会得到如下实现：

> 代码块 8：逐 token 顺序执行 Delta Rule 的 prefill。

```python
S = torch.zeros(b, h, dh, dh) if cache is None else cache
outs = []
for i in range(t):
    k_i = k[:, :, i:i+1]
    v_i = v[:, :, i:i+1]
    b_i = beta[:, :, i:i+1]
    v_old = k_i @ S
    u_i  = b_i * (v_i - v_old)
    S = S + k_i.transpose(-1, -2) @ u_i # write
    outs.append(q[:, :, i:i+1] @ S)
o = torch.cat(outs, dim=2)
```

与标准注意力不同，这种形式需要针对每一个 Key 向量执行一次修正，因此很难直接把它改写成并行矩阵乘法。即使暂时不考虑 Delta Rule，朴素的线性注意力 prefill 也仍然是顺序执行的：

> 代码块 9：逐 token 更新线性注意力状态。

```python
S = torch.zeros(b, h, dh, dh) if cache is None else cache
outs = []
for i in range(t):
    q = q[:, :, i:i+1]
    k = k[:, :, i:i+1]
    v = v[:, :, i:i+1]

    S=S_old+k@v
      o=q@S #bhtd
      o=self.norm(o)
    o=o.transpose(1, 2).contiguous().view(b, t, d)

    out=self.o_proj(o)
    cache=S
    outs.append(out)

o = torch.cat(outs, dim=2)
```

使用分块形式可以得到更高效的方法。通过一个例子会更容易看清它的机制：

![原文图示 9](https://pbs.twimg.com/media/HOPCe0wbMAE0uFp?format=jpg&name=medium)

当 `C=N` 时，我们重新得到标准的 `O(N²)` 注意力；当 `C=1` 时，得到普通线性注意力。介于二者之间的值，则通过增加 chunk 内部的计算量，换取更好的硬件利用率。

实践中，`C` 通常取 64 或 128，因为 Tensor Core 指令能以这种粒度高效运行；UMMA 就是其中一个例子。

中间产生的 tile 会在状态更新时被折叠进 `S`：

![原文图示 10](https://pbs.twimg.com/media/HOPChdebUAA-UJA?format=jpg&name=medium)

> 代码块 10：分块线性注意力中的状态更新。

```python
S = torch.zeros(b, h, dh, dh) if cache is None else cache
outs = []
for i in range(t//C):
    q_c = q[:, :, i*C:(i+1)*C]
    k_c = k[:, :, i*C:(i+1)*C]
    v_c = v[:, :, i*C:(i+1)*C]

      o_prev=q_c@S #this is everything up to this block

      attn=(q_c@k_c.transpose(-1,-2)).tril() #masked attention
      o_curr=attn@v_c

        o=o_prev+o_curr

    S_new=k_c.transpose(-1,-2)@v_c #recurrent attention
    S=S+S_new
    outs.append(o)

o = torch.cat(outs, dim=2)
```

在一个 block 内部，我们计算 `q(kᵀv)`：先得到分数，这是带掩码的普通注意力顺序。在不同 block 之间，则计算 `(kᵀv)q`：先形成状态，再用 Query 读取，这是递归顺序。

普通注意力会以 `O(N²)` 增长，而这种方法不会。block 内部执行真实注意力，也就是带掩码的 `QKᵀ` 再乘以 `V`；跨 block 时，则把所有信息折叠进状态，再用一次矩阵乘法读回。

因此，总成本可以拆成两部分：

- 固定部分为 `2Ld²`，来自状态计算，与 `C` 无关。
- 增长部分为 `2LCd`，来自对角线位置上的分数矩阵。

全注意力只是 `C=L` 的特殊情况，此时第二项变成 `2L²d`，也就是二次复杂度。因此，`C` 越小，所需 FLOPs 越少。

单看 FLOPs，`C=1` 最便宜，但它的实际运行时间不一定最短。当计算能高效映射到 GPU 的矩阵乘法硬件上时，GPU 完成更多算术运算反而可能用时更少。

下一步，是把同一种分块方法扩展到 DeltaNet。

![原文图示 11](https://pbs.twimg.com/media/HOPOzBxa4AIVluu?format=jpg&name=medium)

根本问题很简单：用于纯加法注意力的 chunk 方法，不能直接应用于 Delta 更新。

> 代码块 11：读取旧 Value，再计算需要写入的差值。

```python
v_old = k_i @ S
u_i  = b_i * (v_i - v_old)
```

为了计算需要从状态中减去的信息，我们必须依次获得每一个中间状态。如果不做数学上的重新参数化，就无法用相同方式把它并行化。

因此，作者先把 Delta 更新从下面这种形式开始改写：

> 代码块 12：`u = v_new - v_old` 的顺序状态更新。

```python
u=v_new-v_old
S_t= S_(t-1)+K.T@u
o=q@S_T
```

在这里，顺序循环的每一次迭代只能计算一个 delta。重新参数化之后，形式变为：

> 代码块 13（重参数化形式）：

```python
S_t = S_{t-1}(I − β_t k_t k_tᵀ)  +  β_t v_t k_tᵀ
o_t = S_t q_t
```
>
> `S_t = S_{t-1}(I - β_t k_t k_tᵀ) + β_t v_t k_tᵀ`
>
> `o_t = S_t q_t`

这种形式使分块代码可以一次计算全部 `C` 个 delta：

> 代码块 14：`chunk_delta_rule_forward` 的并行实现。

```python
def chunk_delta_rule_forward(Q, K, V, beta, C):
        # L: sequence length, d: head dimension
        L, d = Q.shape
        # chunking
        Q, K, V = map(lambda x: x.reshape(-1,C,d), [Q, K, V])
        beta = beta.reshape(-1, C)
        K_beta = K * beta.unsqueeze(-1)
        V_beta = V * beta.unsqueeze(-1)

        # compute eq. 10 with vectorized forward substitution for fast inverse
        T = -(K_beta @ K.t()).tril(-1)
        for i in range(1, C):
                T[i, :i] = T[i, :i] + (T[i, :, None] * T[:, :i]).sum(-2)

        T += torch.eye(C)
        W = T @ K_beta
        U = T @ V_beta

        # chunkwise parallel. Eq. 8-9
        S = torch.zeros(d, d)
        O = torch.empty_like(V)

        for i in range(L//C):
                q_i, k_i, w_i = Q[i], K[i], W[i]
                u_i = U[i] - w_i @ S # the corrections, all of one chunk
                o_inter = q_i @ S
                A_i = (q_i @ k_i.t()).tril() #qk.t
                o_intra = A_i @ u_i # attention @ v (with corrections, so u)
                S += k_i.t() @ u_i # update state with addition
                O[i] = o_intra + o_inter #update output with flash + recurrent
        return O.reshape(L, d)
```

由此，我们得到了第一个可直接比较的节点：多头注意力 Transformer 与 DeltaNet Transformer。

![原文图示 12](https://pbs.twimg.com/media/HOPCok6agAAa4aK?format=jpg&name=medium)

## Gated DeltaNet

现在，我们已经有办法对缓存进行精确修改。每出现一项新事实——也就是一个新的 Key 向量——模型都能准确读取该位置原来保存的信息，再把它替换为我们希望注意的新信息。

然而，这个机制只能遗忘那些已经有明确替代内容的关联。发生上下文切换时，它无法高效地一次清除多项关联，也无法让记忆整体衰减，以释放容量。

假设我们使用的是纯加法线性注意力，那么加入遗忘能力会很简单：只需要一个参数来控制旧状态的保留程度。

> 代码块 15：`cache = alpha * S_old + S_new`。

```python
S_old=cache
S_new=k@v
# cache=S_old+S_new
cache=alpha * S_old + S_new
```

![原文图示 13](https://pbs.twimg.com/media/HOPCu6NaoAAK6Fi?format=png&name=medium)

这就是 Mamba-2 的贡献。我们先让旧缓存衰减，再以完整强度加入新缓存，从而避免状态无限增长。

在每个时间步，用一个动态比例统一衰减所有 Key–Value 关联，是一种确实可行的方法；Mamba 使用的就是这种方法。但它没有考虑不同 Key–Value 关联的重要程度并不相同。

也就是说，如果模型只想遗忘一项特定关联，所有关联却都会以相同比例被遗忘。与之相反，Delta Rule 可以只更新一项事实，却无法让其余事实自然衰减。

因此，Gated Delta Rule 把 Mamba 的门控更新与 Delta Rule 结合起来。它加入参数 `alpha`：当 `alpha=1` 时退化为纯 Delta Rule；当 `alpha=0` 时清空记忆。困难仍在于，如何用同一种并行 chunk 方法实现它。

实现继续使用上一节介绍的 DeltaNet 重参数化。数学形式几乎完全相同，只多出一个依赖数据、取值在 0 到 1 之间的标量，用来控制旧状态的衰减。

这就把有效的 Key–Value 关联学习，与自适应的记忆管理结合到了一起。对应的代码变化如下：

![原文图示 14](https://pbs.twimg.com/media/HOPC0xXaQAEoedu?format=jpg&name=medium)

其中 `γʳ/γⁱ` 这一项用于表示累计衰减。在时间步 `x` 写入、并在 `x+t` 读出的 token，已经依次乘过

`αₓ αₓ₊₁ αₓ₊₂ … αₓ₊ₜ`。

这可以看作前缀和在乘法意义下的对应形式。

最终得到的架构如下：

![原文图示 15](https://pbs.twimg.com/media/HOPC2QUb0AErJNt?format=jpg&name=medium)

## KDA / Kimi Linear

走到这里，研究人员开始尝试混合模型：在同一个架构中组合多种注意力形式，例如把 Gated DeltaNet 与 Mamba 结合起来。

Kimi Linear 最受关注的一项主张是：在受控对比中，它的表现超过了全注意力。作者把它描述为一种可以直接替换原有注意力的架构，不仅质量更好，解码吞吐量最高还能提升 6 倍。

Kimi Linear 对 Gated DeltaNet 的改进，是引入更细粒度的门控。它不再只学习一个标量衰减值，而是为每个通道分别学习一个衰减值。

![原文图示 16](https://pbs.twimg.com/media/HOPC6DqbMAENuzH?format=jpg&name=medium)

KDA 的更新规则仍然相似，但代码变成了下面这样：

![原文图示 17](https://pbs.twimg.com/media/HOPC82ZaYAA5Gsc?format=jpg&name=medium)

这里的 `alpha.reshape(nb, C, d)` 捕捉了论文最重要的贡献：对记忆衰减进行细粒度控制。

把它与 DeltaNet Transformer 并排比较，Kimi Linear 架构包含三项主要变化：

1. 使用混合系统，在模型中交错插入多头潜注意力（Multi-head Latent Attention，MLA）层。
2. 用混合专家（Mixture-of-Experts，MoE）层替代 MLP。
3. 通过 alpha projection 为 DeltaNet 增加容量。

![原文图示 18](https://pbs.twimg.com/media/HOPDDj7acAAXOYK?format=jpg&name=medium)

后面的章节会更详细地讨论 MLA 和 MoE。此处最重要的一点是：这不是盲目扩张规模。新增容量具有明确的数学用途——逐通道缩放使模型可以更精细地控制记忆衰减。

Scaling Law 依然成立，但容量必须加在正确的位置，并以系统能够有效利用的形式加入。在这条演进路径中，每一种新架构，都是通过增加一种有针对性的能力，解决前代架构的具体限制。

## Kimi K3

最终，Kimi K3 的语言模型主干与上面介绍的 Kimi Linear 很相似。它包含 23 个四层宏循环（macrocycle）。每个宏循环中，前三层使用 Kimi Delta Attention，第四层使用 Multi-head Latent Attention。

第一层使用稠密前馈网络，其余每一层都使用潜空间 Mixture-of-Experts。

乍看之下，相比 Kimi Linear，它的变化似乎并不多：

- 大幅扩大规模；
- 每 12 层加入一次 blockwise AttnRes；
- MLA Query LoRA 与输出门控；
- 潜空间 MoE；
- SiTU 激活函数；
- Gated MLA。

KDA 提供固定状态大小的递归记忆；周期性插入的 MLA 层，则保留了对整个上下文执行完整 Softmax 检索的能力。下面这张简化图可以作为理解后续变化的参考。

![原文图示 19](https://pbs.twimg.com/media/HOPDG6jbEAA1CIV?format=jpg&name=medium)

先看几项比较直接的变化：Gated MLA、潜空间 MoE，以及 SiTU 激活函数。

Gated MLA 决定从 MLA 检索到的每项特征中，有多少信息可以进入残差流。实现方式是：从输入投影得到一个门，再让检索特征与它逐元素相乘。

在传统 MoE 中，学习得到的路由器使用点积相似度，把每个 token 发送给一部分专家网络。Kimi K3 总共有 898 个专家。其中两个是共享专家，会处理每一个 token；在剩下的 896 个专家中，路由器会为每个 token 选择 16 个。

Kimi K3 还修改了专家网络的激活函数。传统路径会先对 up projection 应用 SiLU，与门逐元素相乘，再执行 down projection；Kimi K3 则使用 SiTU：

> 代码块 16：SiTU 激活函数实现。

```text
d = x.shape[-1] // 2
gate = x[..., :d].to(torch.float32)
up = x[..., d:].to(torch.float32)
situ_a = self.beta * torch.tanh(gate / self.beta) * torch.sigmoid(gate)
if self.linear_beta is not None:
    up = self.linear_beta * torch.tanh(up / self.linear_beta)
return (situ_a * up).to(x.dtype)
```

模型还会把共享专家的输入向下投影，并把这些专家的最终求和结果再向上投影：

![原文图示 20](https://pbs.twimg.com/media/HOPDJJcawAAT8VT?format=jpg&name=medium)

这体现了模型推理中的一个常见难题：如果没有融合 kernel，新的激活路径几乎会比原路径慢三倍。

一项抵消这种开销的优化是，让专家在压缩后的潜空间中运行。这样能大幅加快专家前向传播，并把 FLOPs 几乎削减一半。

剩余变化包括 MLA Query LoRA、输出门控，以及每 12 层一次的 blockwise Attention Residual。AttnRes 大约会增加 2% 的推理延迟，但带来两项重要收益：

- 有选择地检索较早的表示，从而缓解残差稀释和隐藏状态不断增长的问题；
- 获得约 1.25 倍的计算优势。

AttnRes 和 MLA 从两个不同方向解决同一个根本限制。KDA 层只使用固定大小的状态，因此必然需要丢弃信息；MLA 从 token 上下文中重新检索信息，而 AttnRes 则从较早的、沿模型深度分布的表示中检索信息。

## AttnRes

感谢 @chloey3k 对本节的帮助。

在每次前向传播中，输入都会穿过一叠层。这里的每一层都包含一个注意力 block（KDA 或 MLA），以及一个 MLP 或 MoE block。

通常，第 `l` 层的输入等于原始 embedding 加上此前每一层的输出，并且所有项的权重相同：

`h_l = h_1 + Σᶫ⁻¹ᵢ₌₁ f_i(h_i)`

这里，`h_i` 是第 `i` 层的输入；`h_1` 是当前 token 的 embedding，也就是截至目前序列中最后一个 token 的 embedding；`f_i(h_i)` 是第 `i` 层的输出，可以来自注意力 block，也可以来自 MLP block。

问题在于，这种结构缺乏选择性访问能力。不同类型的层都会收到相同的聚合状态，即使它们真正需要的加权方式可能完全不同。

由于这个递归过程只做加法，越靠后的层还必须学习输出越来越大的值，才能对不断累积的残差产生足够影响。这会让训练变得不稳定。

AttnRes 不再平等对待所有层，而是给求和中的每一项乘以一个专门的权重。模型因此可以根据当前上下文，更重视最有用的层：

`h_l = α₀·h_1 + Σᶫ⁻¹ᵢ₌₁ α_i·f_i(h_i)`

每个权重 `α_i` 都通过 Query–Key 点积计算。每一层拥有学习得到的 Query，而 Key 和 Value 来自更早的残差流状态。分数经过归一化，使总和为 1，然后用于对这些状态进行加权组合。

![原文图示 21](https://pbs.twimg.com/media/HOPDLG3aQAADVOf?format=jpg&name=medium)

因此，模型不再只能依赖紧邻的上一层。AttnRes 让每一层都能有选择地访问更早的层输出，并通过学习得到的 Query，检索对当前计算最有用的表示。

后面的伪代码把同一种思想应用到了 block 粒度。这里的 block，是 12 个解码器层中注意力输出与 MLP 输出逐元素累加的结果；它作为单一的深度表示保存下来，供后续 AttnRes 混合使用。

如果在每一层都应用残差注意力，训练和推理成本会过高。只在固定的 block 边界应用，就能以较低成本保留大部分收益。

在 Kimi K3 中，每经过 12 个解码器层，就会出现一个这样的边界。23 个四层宏循环一共形成 8 个 AttnRes block，从而提高推理速度。

下面这部分可能是 `block_attn_res` 函数中最重要的实现：

> 代码块 17：堆叠深度表示，以学习得到的 Query 对早期 block 做加权检索。

```python
V = torch.stack(blocks + [partial_block]) # [N+1, B, T, D]
K = norm(V)
logits = torch.einsum('d, n b t d -> n b t', proj.weight.squeeze(), K)
h = torch.einsum('n b t, n b t d -> b t d', logits.softmax(0), V)
return h
```

至此，我们完成了从 GPT-2 到 Kimi K3 的整条演进路径。

最核心的变化并不只是规模。每一步架构演进，都改变了模型保存什么、如何更新状态，或者如何重新检索那些固定大小状态无法保留的信息。

Kimi K3 把下面几种能力组合在一起：

- 固定状态大小的递归记忆；
- 周期性的 Softmax 上下文检索；
- 稀疏专家容量；
- 对不同深度残差表示的选择性访问。

得到的系统会把额外容量放在具有明确功能的位置上。

从本质上说，固定容量、固定维度的关联记忆必须具备一种淘汰策略。纯加法线性操作在达到容量上限后，必然会让信息相互干扰。

因此，系统需要学习得到的选择机制，例如门控、路由或衰减；而注意力机制，则是最有效的选择性读取方式。
