# 工具与协议一手来源

> 状态：draft | 核验日期：2026-09-12

| 来源 | 版本/用途 | 本库验证范围 |
| --- | --- | --- |
| [JSON Schema](https://json-schema.org/understanding-json-schema/reference/object) | 2020-12对象语义 | Python与TS共同验证12个基础正反例和47个边界反例 |
| [Agent Skills](https://agentskills.io/specification) | 持续更新格式，按核验日阅读 | 格式解释、加载预算算例与本仓教学包；宿主自动触发未测 |
| [MCP当前变更](https://modelcontextprotocol.io/specification/2026-07-28/changelog) | 2026-07-28 | 文档核验；stdio自动协商到当前协议，未覆盖全部能力 |
| [TypeScript SDK v2](https://ts.sdk.modelcontextprotocol.io/v2/) | client/server固定2.0.0，Zod 4.6.2 | 安装、编译、legacy内存及当前协议stdio子进程集成 |
| [v2升级指南](https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2) | v1单包迁移到v2拆分包 | 导入、Schema和传输入口已迁移 |
| [2026协议支持指南](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28) | 协商、无状态核心与新能力 | 本仓验证stdio协商；其他能力形成迁移清单 |
| [MCP授权](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) | 2026-07-28 | 机制说明，未接OAuth服务 |
| [A2A规范](https://a2a-protocol.org/v0.3.0/specification/) | 配套教学端点固定0.3.0 | 两个本地HTTP端点的文本/JSON-RPC子集；未声称完整一致性 |
| [A2A 0.3.0任务生命周期](https://a2a-protocol.org/v0.3.0/topics/life-of-a-task/) | 固定0.3.0 | 恢复、终态不可重启与产物版本问题 |
| [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) | OAuth令牌交换标准 | 委托概念，不要求所有系统强制采用 |

2026-09-12 复核确认：MCP 2026-07-28 变更页仍将上一版列为2025-11-25，新版本移除协议级会话与初始化握手并增加`server/discover`；TypeScript SDK v2已稳定，但必须显式采用当前版本协商/服务入口。本仓已迁移到2.0.0，并分别标出legacy内存测试与当前协议stdio测试。Agent Skills规范仍要求目录至少包含带`name`/`description` frontmatter的`SKILL.md`，`allowed-tools`仍标为实验字段；A2A公开稳定规范仍为0.3.0，Roadmap中的1.0不是已发布版本。

依赖安全检查同日发现 `ajv@8.17.1` 命中 [GHSA-2g4f-4pwh-qvx6](https://github.com/advisories/GHSA-2g4f-4pwh-qvx6)；参考 Runtime 已升级到 8.20.0，`npm audit` 返回 0 个已知漏洞。该检查只覆盖锁文件在核验时的公告结果，不是长期安全保证。
