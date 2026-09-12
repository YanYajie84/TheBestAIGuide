# Context Builder：把候选信息变成模型输入

> 状态：draft
> 目标：给出不依赖特定框架的构建流程和最小数据契约。

## 职责

Context Builder 位于信息源和模型调用之间，负责：

1. 收集候选信息。
2. 标注来源、信任、版本、时效和敏感度。
3. 应用硬性权限与安全规则。
4. 按当前子任务选择、去重和排序。
5. 在预算内转换为模型可消费的形式。
6. 输出构建记录，支持 Trace、回放和评测。

它不负责决定工具是否真的执行，也不负责把所有历史永久保存；这分别属于 Runtime 和 Memory/State。

## 适用条件

以下情况通常值得建立独立的 Context Builder：

- 信息同时来自系统策略、用户、状态、检索、工具和环境；
- 任务跨越多轮或多个工具，需要稳定维护目标与约束；
- 系统需要控制 Token、敏感数据、时效和跨用户隔离；
- 失败后需要解释“哪些信息被选择、丢弃或压缩”；
- 多个模型入口需要共享一致的上下文规则。

对于一次性、输入固定且没有权限差异的简单调用，完整 Builder 可能增加不必要的复杂度，可以先使用明确的组装函数和 Schema。

## 输入契约

一个最小输入可以表示为：

```yaml
request:
  goal: "定位并修复支付回调重复入账"
  constraints:
    - "不得修改生产数据"
  acceptance:
    - "失败测试先复现，修复后通过"
state:
  current_step: "分析幂等键写入路径"
  open_items: []
candidates:
  - id: "repo:payment/webhook.py"
    tenant: "payments"
    kind: "workspace_file"
    trust: "workspace"
    version: "git:abc123"
    content_ref: "workspace://payment/webhook.py"
    sensitive: false
  - id: "trace:run-042"
    tenant: "payments"
    kind: "tool_result"
    trust: "runtime"
    observed_at: "2026-09-03T10:20:00+08:00"
    content_ref: "trace-store://run-042"
    sensitive: true
tools:
  - name: "run_tests"
    permission: "read_execute"
budget:
  max_input_tokens: 32000
```

数值只是 Schema 示例，不是推荐预算。

`content_ref` 是受控加载器可解析的引用，不是让模型自行访问的 URL。构建器先根据主体、租户、敏感度、用途和有效期判断能否读取，再由加载器取回正文；若候选一开始就内嵌 `content`，所谓“读前授权”已经失去意义。可信度也不等于访问权：一个来源可以可信，但当前主体仍可能无权读取。

## 构建流水线

```python
def build_context(request, state, candidates, tools, budget):
    items = normalize(candidates)
    items = enforce_access_policy(items)
    items = mark_untrusted_instructions(items)
    items = drop_expired_or_wrong_scope(items)
    items = resolve_exact_duplicates(items)
    items = rank_for_current_step(items, request, state)
    items = transform_with_provenance(items, budget)
    envelope = pack(request, state, items, tools, budget)
    validate_invariants(envelope)
    return envelope
```

这是架构伪代码，函数名代表需分别实现的步骤，不能直接复制运行。顺序不是唯一实现，但有两个关键要求：权限检查应在读取或向模型/外部排序器发送正文之前完成；有损压缩后仍要保留来源和回读能力。`mark_untrusted_instructions` 只能标明外部来源，不能据此保证模型不会受注入影响，最终动作仍由 Runtime 独立授权。

## 选择规则

### 先做硬过滤

- 当前主体无权读取的内容；
- 其他用户或租户的数据；
- 明确过期且不应作为历史证据的状态；
- 与当前环境版本不匹配的配置；
- 已标记为撤销、失败或污染的记忆。

### 再做软排序

排序可以综合当前步骤相关性、来源权威性、时间、具体程度和覆盖增益。不要只按向量相似度排序，因为高度相似的片段可能重复、过期或不可信。

### 最后做覆盖检查

在预算耗尽前，确认这些信息是否存在：

- 目标与验收条件；
- 不可违反的约束；
- 当前状态与未完成事项；
- 做出本轮决策所需的最小证据；
- 可用工具及其限制；
- 输出格式和停止条件。

## 预算分配

不要把固定百分比当作普适答案。更稳妥的做法是：

1. 为硬约束、当前请求和输出契约预留不可挤占空间。
2. 为模型输出和工具往返预留余量。
3. 候选证据按边际价值逐步加入。
4. 超出预算时，优先去重和删除无关项，再考虑摘要。
5. 记录被删除或压缩的内容，以便失败分析。

对于长任务，还要控制“下一轮会新增多少内容”，避免本轮刚好装满后无法继续工作。

## 输出契约

Builder 不应只返回最终消息，还应返回构建元数据：

```json
{
  "messages": [],
  "selected_item_ids": ["repo:payment/webhook.py", "trace:run-042"],
  "dropped": [
    {"id": "trace:run-001", "reason": "superseded"}
  ],
  "transformations": [
    {
      "output_id": "summary:trace-042",
      "source_ids": ["trace:run-042"],
      "method": "structured_extract",
      "lossy": true
    }
  ],
  "budget": {
    "estimated_input_tokens": 18200,
    "max_input_tokens": 32000
  },
  "warnings": []
}
```

这些数字同样只是格式示例。

## 确定性代码与模型的分工

优先使用确定性逻辑完成：

- 权限过滤；
- 版本、时间和作用域判断；
- 精确去重和固定格式解析；
- Token 估算和硬预算；
- Schema 校验；
- 敏感字段遮蔽。

模型更适合：

- 语义相关性判断；
- 查询改写；
- 开放文本摘要；
- 冲突线索提取；
- 在复杂目标下判断信息覆盖。

模型产出的排序或摘要仍需记录版本、输入和不确定性。

## 缓存与可变前缀

缓存优化不能只看命中率。应把上下文分为：

- 稳定前缀：系统策略、稳定工具 Schema、长期不变的示例；
- 任务级部分：本次目标、仓库状态、检索证据；
- 轮次级尾部：最新观察、工具结果和下一步计划。

稳定内容尽量保持字节级一致，可变内容追加在后；但当策略或工具版本改变时必须失效缓存，不能为了命中率继续使用旧约束。

## 代价与反模式

独立 Builder 会增加数据建模、版本管理、Trace 存储和性能开销；如果所有调用都经过同一个过度复杂的入口，它本身也可能成为延迟和维护瓶颈。

常见反模式包括：

- 只保存最终 Prompt，不记录选择和转换过程；
- 先做语义排序，再做权限过滤；
- 把来源权威性、时效、权限和相关性压成一个无法解释的分数；
- 超出预算时直接截断尾部；
- 用摘要覆盖原文且不保留来源和回读路径；
- 让 Builder 隐式执行有副作用的动作。

## 最小测试集

Context Builder 至少需要覆盖：

- 预算不足以容纳硬约束时显式失败，不发送缺约束的请求；
- 不可信文档中的命令不会覆盖系统策略；
- 过期状态被替换而非同时注入；
- 工具失败不会被转换成成功事实；
- 摘要带有原始来源和 `lossy` 标记；
- 相同输入和配置可重放构建结果；
- 跨用户数据不会混入；
- 关键冲突会产生警告或中止，而不是静默消解。

下一步通过[上下文评测](../01-concepts/03-context-evaluation.md)设计测试，再进入[配套实验](../04-labs/README.md)记录运行结果。

## 从预算公式到可运行打包

可用证据预算并不等于模型窗口长度：

$$
B_{evidence}=W-B_{output}-B_{protocol}-B_{tools}-B_{mandatory}.
$$

$W$ 是窗口上限；四个扣除项依次是输出预留、消息模板/协议开销、工具定义与工具往返预留，以及目标/硬约束等必留输入。若教学窗口为 1000、输出预留 200、协议 50、工具 50、必留 200，剩余证据预算为 500。不要重复扣除：若供应商计数器已把工具 Schema 编入协议消息，应把它归入 `B_protocol`，并令 `B_tools` 只表示未来工具结果的预留。

可选片段每个有成本 $t_i$ 和预估价值 $u_i$，选择 $x_i\in\{0,1\}$，可以写成预算约束问题：最大化 $\sum_i u_ix_i$，满足 $\sum_i t_ix_i\le B_{evidence}$。它是一个简化模型：片段会互相补充或重复，效用不一定可加。按 $u_i/t_i$ 贪心只是易解释的启发式，并非一般情况下的最优解。

例如证据预算为 10，片段 A 的成本/价值为 6/12，B 和 C 各为 5/9。按单位价值排序会先取 A，只剩 4，最终价值 12；取 B+C 则价值 18。这个反例解释了为什么“先取最高性价比”只是近似。实际还要考虑覆盖：结论和限定条件分在两个片段中时，应一起保留，而不是独立打分后只留下结论。

[Python 参考实现](../05-code/context-builder-python/README.md)使用“元数据引用 + 延迟正文加载器”，在读取正文前检查租户、信任、敏感度和有效期；之后执行必留检查、精确去重、事实冲突检测和预算打包，并把分隔符算入成本。预算不足容纳目标/约束/验收条件或必留候选时直接报错。测试还固定了跨租户正文从未被加载、必留项拥有重复内容、空集合指标不除零等边界。

计数器可注入；实验默认字节 tokenizer，不能把输出数字当成 GPT/Claude 计费 token。`TokenizerCounter` 适配供应商 tokenizer，`ChatTemplateCounter` 用于对渲染后的消息和工具定义整体计数。上文构建流水线仍是完整架构伪代码；参考实现只覆盖读前授权、必留检查、精确去重、结构化事实冲突、预算打包与来源记录，不包含语义排序、开放文本摘要、PII 脱敏或模型调用。

## 接入真实 Tokenizer 与聊天模板

不要只对拼接后的正文调用 tokenizer。供应商实际请求还可能编码角色标记、消息边界、工具 Schema、图片、缓存控制和其他协议字段；同一段文字在不同模型或模板下的计数也可能不同。生产接入应冻结并记录 `provider/model/tokenizer_version/chat_template_version`，对**最终序列化请求**计数：

```python
counter = TokenizerCounter(provider_tokenizer.encode)
template_counter = ChatTemplateCounter(
    render=render_complete_chat_request,
    counter=counter,
)
estimated = template_counter.count(messages=messages, tools=tools)
```

这里的函数名是适配器示意，不代表各供应商存在同名 API。上线前用供应商返回的 usage 做校准样本，并为文本、工具调用、多模态输入、缓存命中和长输出分别测试；模型或聊天模板升级后重新校准。推理 Token、输出上限与上下文窗口是否共享同一额度，应以所用模型当期官方文档和真实 API 响应为准。

安全规则和来源记录的解释见[安全边界与来源追踪](../03-security-provenance/README.md)。
