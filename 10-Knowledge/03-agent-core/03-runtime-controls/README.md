# 运行时控制：超时、审批、幂等与用量预算

> 状态：verified | 配套代码：`loop.py` 的离线测试覆盖以下控制路径

模型提出动作，不等于动作可以直接执行。运行时仍要根据工具属性、调用主体和剩余预算决定执行、拒绝、暂停还是停止。本章最小实现增加四种控制。

| 风险 | 程序控制 | 结果语义 |
| --- | --- | --- |
| 工具运行过久 | `Tool.timeout_seconds` | 只读工具返回 `timeout`；副作用工具返回 `timeout_side_effect_unknown` |
| 高影响动作 | `Tool.requires_approval` | 保存动作、决策ID和摘要，进入 `waiting_for_input` |
| 重复写入 | `require_idempotency_key` | 缺少稳定键时拒绝执行，重试仍需由后端按键去重 |
| 模型用量过高 | `max_total_tokens` | 累计供应商返回的usage并停止后续动作 |
| 用户取消长任务 | `should_cancel` | 在下一次模型决策前进入 `stopped/cancelled` |
| 暂停后进程重启 | `save_checkpoint/load_checkpoint` | UTF-8 JSON保存完整history、usage与待审批对象 |

## 超时不等于没有执行

线程超时只能让调用方停止等待，不能可靠终止正在运行的Python函数。副作用工具超时后，系统不知道写入是否已经发生，因此返回 `side_effect_unknown=true`，不得自动重试。生产系统还应查询远端操作状态，或依靠服务端幂等键确认结果。

## 审批必须绑定具体动作

审批请求保存 `decision_id`、完整动作和动作摘要。`resume_agent` 同时核对决策ID和摘要，避免用户批准A后系统实际执行已经变化的B。批准只对该动作生效，不会永久放宽工具权限。拒绝也会成为模型可见的Observation，使策略可以换方案或正常结束。

## 用量上限的边界

`max_total_tokens` 使用适配器返回的 `prompt_tokens + completion_tokens`。调用前只能根据已发生用量判断是否继续；一次新请求仍可能使总量越过上限。本例在收到usage后停止该动作。真正的硬预算还需要调用前限制输入、设置最大输出，并使用服务端计量核对。

取消检查发生在决策之间，不能抢占已经进入handler的Python代码。JSON checkpoint采用临时文件替换以避免写出半个文件，但不是多进程数据库或事务日志。完整系统还需要外部沙箱、持久队列、跨进程锁和服务端幂等实现。
