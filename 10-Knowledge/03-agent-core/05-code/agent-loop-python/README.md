# 最小 Python Agent Loop

> 状态：verified | 验证：2026-09-11，Windows/Python 3.12，21项单元测试通过

输入查询“上下文”，离线规则策略调用只读搜索，取得教学文档，再返回带ID的文字。Python 3.11+，运行无需第三方包。

从本目录运行：

```bash
PYTHONPATH=src python -m agent_loop.cli 上下文
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m agent_loop.eval fixtures/teaching-tasks.json
```

PowerShell：先执行 `$env:PYTHONPATH="src"`，再执行上述`python`命令。也可 `python -m pip install -e .` 安装后正常import；打包工具需已安装或可联网取得。

| 文件 | 看什么 |
| --- | --- |
| [models.py](src/agent_loop/models.py) | Action、State、模型接口与两种离线策略 |
| [loop.py](src/agent_loop/loop.py) | 完整动作历史、审批恢复、超时、用量预算和重复停止 |
| [adapters.py](src/agent_loop/adapters.py) | 可选的OpenAI-compatible Chat Completions传输与动作解析 |
| [tools.py](src/agent_loop/tools.py) | 只读中文子串检索教学语料 |
| [trace.py](src/agent_loop/trace.py) | 按事件写JSONL；使用新文件防覆盖 |
| [verification.py](src/agent_loop/verification.py) | 带全局修订上限的生成—验证循环 |
| [planning.py](src/agent_loop/planning.py) | 显式计划、依赖验收和保留已完成产物的重规划 |
| [checkpoint.py](src/agent_loop/checkpoint.py) | UTF-8 JSON状态保存与恢复 |
| [eval.py](src/agent_loop/eval.py) | 执行合成fixture并报告逐条通过结果 |
| [test_loop.py](tests/test_loop.py) | 21条离线测试，覆盖成功、失败、安全边界、适配器、审批、超时、取消、checkpoint、计划、评测与修订 |

公开入口：`run_agent(...) -> AgentState`与`resume_agent(...) -> AgentState`。`model.decide(state)`返回`Action`或带usage的`ModelDecision`；`state.history`保留完整动作—观察对。高影响工具可暂停到`waiting_for_input`，恢复时审批必须匹配决策ID和动作摘要。`--trace new-run.jsonl`写新文件，已存在则报错。

真实模型示例通过`OpenAICompatibleAdapter`连接实现Chat Completions兼容格式的服务；API密钥由调用者注入，不写入Trace。该适配器只支持单个完整响应和单工具调用，不支持流式、并行工具或供应商特有字段。OpenAI官方接口也允许一次返回多个工具调用，因此这里的单调用是教学Loop的显式限制。

```python
import os
from agent_loop import OpenAICompatibleAdapter, default_tools, run_agent

tools = default_tools()
model = OpenAICompatibleAdapter(
    base_url=os.environ["CHAT_API_BASE_URL"],
    api_key=os.environ["CHAT_API_KEY"],
    model=os.environ["CHAT_MODEL"],
    tools=tools,
)
state = run_agent(model, tools, "上下文预算应该怎样分配？", max_steps=4)
```

本实现不执行外部命令、不提供进程沙箱或分布式任务队列；线程超时也不能杀死已经开始的handler，因此进程内handler须可信。JSON checkpoint可保存教学状态，但不提供多进程锁和事务协调。`completed`仅表示合法结束，需要另行评分。运行时控制的边界见[运行时控制](../../03-runtime-controls/README.md)。
