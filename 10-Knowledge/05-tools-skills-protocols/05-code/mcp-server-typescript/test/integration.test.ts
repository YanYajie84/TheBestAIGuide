import test from "node:test";
import assert from "node:assert/strict";
import { Client, InMemoryTransport } from "@modelcontextprotocol/client";
import { createServer } from "../src/server.js";
import { searchLocal } from "../src/client.js";

test("SDK discovery, arguments, structured data and execution error", async () => {
  const server = createServer();
  // The v2 in-memory pair deliberately exercises the legacy 2025 handshake.
  const client = new Client(
    { name: "test", version: "1" },
    { versionNegotiation: { mode: "legacy" } },
  );
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    assert.equal(client.getNegotiatedProtocolVersion(), "2025-11-25");
    const listing = await client.listTools();
    assert.equal(listing.tools[0].name, "search_docs");
    const valid = await client.callTool({ name: "search_docs", arguments: { query: "上下文" } });
    assert.deepEqual(valid.structuredContent, { documents: [{ id: "doc-1", text: "上下文预算为输出和工具结果预留空间。" }] });
    const bad = await client.callTool({ name: "search_docs", arguments: { query: " " } });
    assert.equal(bad.isError, true);
    // v2 rejects an unknown tool as a protocol error. Its high-level server
    // converts schema validation failure into a tool error result.
    const protocolError = (error: unknown) =>
      typeof error === "object" && error !== null && "code" in error && error.code === -32602;
    await assert.rejects(
      client.callTool({ name: "missing", arguments: {} }),
      protocolError,
    );
    const wrongType = await client.callTool({
      name: "search_docs",
      arguments: { query: 7 },
    });
    assert.equal(wrongType.isError, true);
  } finally { await client.close(); await server.close(); }
});
test("real stdio subprocess starts, lists, calls and closes", async () => {
  const response = await searchLocal("工具");
  assert.equal(response.protocolVersion, "2026-07-28");
  assert.deepEqual(response.tools, ["search_docs"]);
  assert.equal(response.result.isError ?? false, false);
  assert.ok(JSON.stringify(response.result.structuredContent).includes("doc-2"));
});
