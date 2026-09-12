# MCP：统一能力接口，协议版本必须说清楚

> 状态：draft | 来源核验：2026-09-12 | 当前规范：2026-07-28；配套实测工程：TypeScript SDK 2.0.0

如果同一个“查资料”功能要接多个Agent宿主，分别为每个宿主写一套发现和调用协议会重复工作。MCP提供统一消息接口：服务端说明提供哪些能力，客户端发现并调用，宿主决定何时向模型提供这些能力及是否允许执行。协议解决互操作，不替代检索算法，也不保证被调用工具安全或答案正确。

| 角色/对象 | 在教学案例中的对应物 |
| --- | --- |
| Host | 运行Agent、构造上下文、控制授权的应用 |
| Client | Host里与某个MCP Server通信的连接/请求组件 |
| Server | 对外暴露 `search_docs` 的本地进程 |
| Tool | 可调用的搜索动作及输入输出Schema |
| Resource / Prompt | 可读取的资料与可复用提示模板；不等于可执行工具 |

`tools/list` 只是在询问“有哪些工具”，`tools/call` 才请求执行工具。Host 可以发现十个工具，只给当前模型调用提供其中两个；服务端暴露的全部能力不必原样塞进每次上下文。

## 当前版本与兼容路线

截至核验日期，官方最新规范是2026-07-28，官方TypeScript SDK v2已经稳定并拆分为`@modelcontextprotocol/client`、`server`、`core`和运行时包。本仓固定`client@2.0.0`、`server@2.0.0`与Zod 4.6.2。

只安装v2包并不自动保证正在使用2026协议。普通`Client`/`McpServer`构造仍可走2025时代兼容路径；当前协议需要显式的版本协商/服务入口。本仓真实stdio客户端使用`versionNegotiation: {mode: "auto"}`，服务端使用`serveStdio`，测试断言最终协商为`2026-07-28`。内存`InMemoryTransport.createLinkedPair()`测试则明确设为`legacy`，只用于覆盖旧握手兼容，不能冒充当前协议验证。

| 对照项 | 旧兼容路径 | 本仓当前路径 |
| --- | --- | --- |
| 协议版本 | 2025-11-25时代握手 | 2026-07-28 |
| SDK | v1单包或v2 legacy模式 | v2拆分包 |
| 初始化 | `initialize` / `initialized` | 自包含请求；客户端可先`server/discover`协商 |
| 会话 | 协议级有状态生命周期 | 核心协议无状态；状态由扩展或应用层管理 |
| 本库验证 | 内存传输 | 真实stdio子进程、发现、调用和关闭 |

升级不能只改`protocolVersion`字符串。协议版本、SDK包版本和传输部署方式是三个不同维度，都应写进Trace和兼容测试。

## 能力矩阵：发现不等于授权

| 能力 | 方向与用途 | 宿主仍需负责 |
| --- | --- | --- |
| Tools | Client发现并请求Server执行动作 | 工具筛选、参数/输出校验、主体与资源授权 |
| Resources | Client读取或订阅Server提供的内容 | 访问控制、来源、时效、缓存和注入隔离 |
| Prompts | Client获取可复用提示模板 | 是否向模型加载、变量验证、版本与信任 |
| Extensions / Tasks | 可选扩展表达长任务或额外能力 | 协商支持、状态恢复、取消、幂等和产物验收 |
| `subscriptions/listen` | 当前规范的统一订阅流 | 断线重连、背压、重复事件和权限变化 |
| Authorization（HTTP） | OAuth相关发现、认证与令牌使用 | TLS、受众/资源校验、最小scope、令牌保密 |

客户端只能使用双方协商支持的能力。列表里出现工具也不等于模型或用户已获准调用；Resource和工具输出中的文本也仍是不可信数据。

## 搜索请求实际经过什么

[server.ts](../05-code/mcp-server-typescript/src/server.ts)注册工具，声明`query`是非空字符串，输出是带ID和原文的文档列表。[client.ts](../05-code/mcp-server-typescript/src/client.ts)启动子进程、自动协商版本、列出工具、调用搜索，并在`finally`关闭客户端。stdio使用标准输入输出传输协议消息，所以服务器的调试日志必须写stderr；往stdout写“服务启动成功”会污染消息流。

```typescript
const client = new Client(info, { versionNegotiation: { mode: "auto" } });
const listing = await client.listTools();
const result = await client.callTool({
  name: "search_docs", arguments: { query: "上下文" }
});
if (result.isError) { /* 处理工具失败，不能当作空结果 */ }
```

SDK示例返回`structuredContent`，同时提供JSON文本，便于兼容消费方。参数只有空格会通过结构Schema，但被业务代码拒绝；这正好用于验证结构校验与业务校验的区别。

## 错误分层与本仓实测

传输故障、JSON-RPC错误和工具业务错误不是同一回事。使用v2.0.0的本仓测试观察到：空格查询由handler返回`isError:true`；不存在的工具抛出`ProtocolError`，错误码`-32602`；错误参数类型由SDK返回`isError:true`。客户端因此既要捕获请求异常，也要检查结果标志。这个行为是固定版本测试结果，不应无条件外推到其他SDK、协议模式或未来版本。

## 从v1/2025实现迁移到v2/2026的清单

1. 把单体`@modelcontextprotocol/sdk`导入迁移到`client`、`server`、`core`和所需运行时包，并改用Zod 4 / Standard Schema写法。
2. 服务端采用当前传输入口（stdio可用`serveStdio`）；客户端选择`auto`或明确固定协议版本，并记录协商结果。
3. 移除对协议级会话和旧初始化回调的隐含依赖；需要请求级状态时，用`requestState`等应用机制并验证其完整性。
4. 评估`server/discover`、工具`resultType`、统一`subscriptions/listen`以及缓存字段`ttlMs`/`cacheScope`对现有代码的影响。
5. 重测工具、Resource、Prompt、扩展、通知、错误映射、取消、并发、断线与重连；不要只跑Happy Path。
6. 远程HTTP另行验证TLS、OAuth元数据、资源指示、token audience、代理配置和跨租户授权。
7. 保留旧客户端互操作测试和回滚路径，发布记录同时写明协议、SDK与服务端部署版本。

本地stdio成功不等于远程部署完成。相关身份边界见[委托授权](05-delegated-authorization.md)，运行步骤见[工程README](../05-code/mcp-server-typescript/README.md)。

一手来源：[2026-07-28变更](https://modelcontextprotocol.io/specification/2026-07-28/changelog)、[TypeScript SDK v2](https://ts.sdk.modelcontextprotocol.io/v2/)、[v2升级指南](https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2)、[2026协议支持指南](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28)。
