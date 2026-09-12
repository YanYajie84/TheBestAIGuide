# Context Engineering Labs

> 状态：verified
> 执行日期：2026-09-12；Python 3.12；两本共 7 个代码单元真实执行。

| 实验 | 看什么 | 实际结果 |
| --- | --- | --- |
| [预算打包](01-token-budget.ipynb) | 读前权限、硬约束及输出/协议/工具预算 | 360 字节头截断漏证据；297 字节打包保留目标/约束/证据，跨租户正文未加载 |
| [结构化压缩](02-context-compaction.ipynb) | 失败不能变成功，约束不能被观察覆盖，事实带来源 | 原始 5759 字节 → 297 字节；已标注字段 3/3 保留，截断基线仅 1/3 |
| [开放文本压缩评测协议](03-open-text-compaction-eval.md) | 否定、数字、条件、来源、幻觉和间接注入如何评测 | 设计稿；尚未运行模型，不报告质量分数 |

输入全是人工构造教学事件。默认计数器每 UTF-8 字节算一个教学 token，不是任何商用模型的 tokenizer；代码允许注入真实计数函数。两本 Notebook 没有调用模型，没有测试 Context Rot 或开放式摘要质量；第三份文档给出真实模型评测协议，但当前状态仍是 `design`。

[Python 参考包](../05-code/context-builder-python/README.md)是正式实现与测试入口；[context_lab.py](context_lab.py)只为旧链接保留兼容包装。正文对应 [Context Builder](../02-patterns/01-context-builder.md)、[优化策略](../02-patterns/02-optimization-strategies.md)和[安全边界](../03-security-provenance/README.md)。所有 Notebook 均保存中间量、检查、对照和局限。

源码只依赖标准库；重新运行 Notebook 时先按[统一环境说明](../../../scripts/README.md)安装依赖并选择内核。从仓库根目录执行：

```bash
python scripts/check_notebooks.py --execute 10-Knowledge/04-context-engineering/04-labs/01-token-budget.ipynb
python scripts/check_notebooks.py --execute 10-Knowledge/04-context-engineering/04-labs/02-context-compaction.ipynb
```

也可在 Jupyter 中打开本子并“重启内核并运行全部”。先预测结果：把窗口缩到放不下必留项时应显式报错；把最后一次测试失败删去，压缩结果才会回到此前的通过。两种现象分别检验硬约束保护和事件覆盖顺序，不依赖语言模型。

## 标准内核验证更新（2026-09-06）

初次保存输出的本地环境限制内核 socket，因此用了独立进程内的 IPython；提交 `5e5a40c09e00028c7887fd3bf3bd559d96fc972f` 的 [GitHub Actions 标准 Jupyter 执行](https://github.com/HarryYangthu/TheBestAIGuide/actions/runs/34013521515)随后成功。两条记录验证的后端不同，不代表所有 Notebook 前端均已验收。后续结果见 [Round2 完成记录](../../../00-Home/Round2-Completion.md)。
