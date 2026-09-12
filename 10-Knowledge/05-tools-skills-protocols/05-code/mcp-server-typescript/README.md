# MCP Server与Client版本协商示例

> 状态：verified | 实测：2026-09-12；`@modelcontextprotocol/client`/`server` 2.0.0，Zod 4.6.2，Node 24.15.0

这是官方TypeScript SDK v2的最小教学实现。真实stdio路径使用自动版本协商并断言当前2026-07-28协议；内存路径显式使用legacy模式，覆盖2025-11-25时代握手兼容。协议差异见[MCP文章](../../01-concepts/03-mcp.md)。

从本目录运行：

```bash
npm ci
npm test
node dist/src/client.js 上下文
```

客户端真实启动本地stdio子进程，协商版本、发现`search_docs`工具、搜索教学文档、读取结构化输出，最后关闭连接。无需模型API或外部资料。服务端stdout只写协议消息，诊断应写stderr。

[server.ts](src/server.ts)使用`serveStdio`注册工具与输入/输出Schema；[client.ts](src/client.ts)使用`versionNegotiation.mode="auto"`完成协商、发现、调用与关闭；[integration.test.ts](test/integration.test.ts)验证legacy内存传输、业务错误、未知工具、错误参数和当前协议stdio子进程。v2.0.0实测中，未知工具抛`ProtocolError(-32602)`，空格查询和错误参数类型返回`isError:true`，因此消费方既要捕获异常，也要检查结果标志。

未实现HTTP部署、OAuth、多租户资源授权、Resources、Prompts、订阅、Tasks扩展或生产监控。锁文件用于重现本次测试，不代表依赖永远无需升级；SDK或协议升级后必须重跑互操作、错误和授权测试。
