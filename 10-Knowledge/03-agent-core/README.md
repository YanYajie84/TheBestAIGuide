# Agent Core

> 状态：draft | Python 3.11/3.12离线测试与Notebook已验证；真实模型效果仍需单独评测

从“检索资料并带证据回答”理解Agent。先掌握动作与状态如何变化，再增加计划、验证和恢复。

| 阅读顺序 | 解决的问题 | 对应实践 |
| --- | --- | --- |
| [边界与组成](01-concepts/01-agent-boundaries.md) | 什么时候需要Agent，哪些控制仍应写成程序 | 目标、状态、动作字段 |
| [Agent Loop](01-concepts/02-agent-loop.md) | 循环如何推进，怎么防止不停执行 | [Loop源码](05-code/agent-loop-python/src/agent_loop/loop.py) |
| [模型适配器](01-concepts/03-model-adapters.md) | 如何把API输出接入执行器 | [动作与模型接口](05-code/agent-loop-python/src/agent_loop/models.py) |
| [ReAct与计划执行](02-patterns/01-react-and-plan-execute.md) | 逐步探索与预先分解怎样选 | 同工具、同Loop组合子任务 |
| [反思与验证](02-patterns/02-reflection-verification-human-loop.md) | 完成后如何检查，失败后怎么修 | 引用检查与有界修订 |
| [运行时控制](03-runtime-controls/README.md) | 超时、审批、幂等与用量预算怎样落到代码 | 暂停/恢复与副作用不确定性 |

先照[工程README](05-code/agent-loop-python/README.md)运行单测和合成评测，再打开[实验Notebook](04-labs/01-agent-loop.ipynb)比较成功、重复与预算耗尽。教学策略是确定性的，不把它称作模型推理效果。可选的 OpenAI-compatible Chat Completions 适配器只验证传输与动作解析契约，不代表任何模型的任务成功率。

来源见[参考资料](references.md)。下一站：[上下文工程](../04-context-engineering/README.md)与[工具契约](../05-tools-skills-protocols/README.md)。

## 从规则策略走到真实模型

读懂最小 Loop 后，进入 [learning-workbench](../../20-Projects/learning-workbench/README.md)，沿“模型文本 → `ActionModel` 解析 → 本章 `run_agent` → 工具观察 → 下一次决策”读一遍。先查看 [agent-comparison.json](../../20-Projects/learning-workbench/artifacts/real-models/agent-comparison.json)，区分选对工具、正常结束与答对三种结果，再按项目说明运行。受限单工具流程由宿主控制结束阶段，不能把它的成绩当成自由循环能力。
