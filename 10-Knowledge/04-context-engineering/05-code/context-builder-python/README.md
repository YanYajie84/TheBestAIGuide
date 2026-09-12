# Context Builder Python

这是本章可运行、可测试的确定性参考实现。它演示安全边界与预算机制，不声称是完整生产框架，也不调用模型。

## 已实现的契约

- 先检查候选元数据的租户、信任、敏感度和有效期，再调用正文加载器；
- 请求目标、硬约束和验收条件组成不可静默删除的信封；
- 输出、消息协议与工具往返分别预留预算；
- 精确去重保留来源变换记录，事实冲突默认中止；
- 可注入真实 tokenizer 或完整聊天模板计数器；
- 结构化压缩按租户隔离，并阻止低权威观察覆盖约束；
- 空集合评测返回“不适用”，不除零也不自动记满分。

语义排序、开放文本摘要、PII 脱敏和模型调用不在这个最小实现内；接入生产系统时应放在经过权限过滤的边界之后，并保留可回读来源。

## 运行

从本目录执行：

```bash
python -m unittest discover -s tests -v
```

项目采用 `src` 布局。未安装包时可在仓库根目录运行：

```bash
$env:PYTHONPATH="10-Knowledge/04-context-engineering/05-code/context-builder-python/src"
python -m unittest discover -s 10-Knowledge/04-context-engineering/05-code/context-builder-python/tests -v
```

入口与数据类型见 `context_builder/__init__.py`，行为边界由测试固定。
