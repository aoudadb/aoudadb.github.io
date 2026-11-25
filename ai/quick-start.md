---
title: "Quick Start for AI Agents"
parent: "AI Agents"
nav_order: 1
---

# Quick Start for AI Agents

This is the minimal path for an AI agent to get a working Aouda database, connect to it, and run queries. No DBA setup required.

---

## Option A — Local server (fastest, local)

```bash
# Pass flags directly (recommended) or use an optional appsettings.json in the working directory:
aouda start --port 5433 --data-dir ./data
# Create database via POST /api/databases if not auto-created from config
```

**Do not run `aouda start -h` / `--help`.** On current CLI builds, `start` forwards args to the server host; help is ignored and the process boots on port **5000** with data under **`./data`**. For a throwaway probe that must not collide with an existing server, use unused ports, `--data-dir` under the OS temp folder, then `aouda stop -s http://127.0.0.1:<port> --force` — full recipe and schema/data-plane traps: [Local CLI testing (agents)](local-cli-testing.md).

Connect with TypeScript:

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "default",
});

await client.connect();

await client.table("events").insert({
  id: 1,
  name: "startup",
  timestamp: new Date().toISOString(),
});

const result = await client.table("events").execute();
console.log(result.rows);
```

Connect with .NET:

```csharp
using Aouda.Client;

var client = new AoudaClient("http://localhost:5433", "default");

await client.GetTable("events").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1,
    ["name"] = "startup",
    ["timestamp"] = DateTime.UtcNow
});

var rows = await client.GetTable("events").ToListAsync();
```

Data already held as columns inserts and bulk-loads as a `ColumnBatch` (`ColumnBatch.Of(ColumnBatchColumn.FromInt64s(...), ...)`,
then `InsertAsync(batch)` or `client.BulkLoadAsync(table, batches)`), without a dictionary per row (**Lead S13, 0.6.0**). See
[.NET client](../clients/dotnet.md).

---

## Option B — Embedded (in-process, zero setup)

No server, no network, no auth. The database lives in your process.

```csharp
using Aouda.Abstractions;
using Aouda.Embedded;

await using IAoudaDatabase db = await AoudaEmbedded.OpenDatabaseAsync();

await db.GetTable("cache").InsertAsync(new Dictionary<string, object?>
{
    ["key"] = "result:abc",
    ["value"] = "42",
    ["created_at"] = DateTime.UtcNow
});

var rows = await db.GetTable("cache")
    .Where("key", "eq", "result:abc")
    .ToListAsync();
```

Use embedded mode for:
- Throwaway databases during agent execution
- Unit and integration tests
- CLI tools and scripts that need local storage
- Any single-process workflow where network overhead isn't needed

---

## Option C — Local server with app auth (for user-facing apps)

```bash
aouda start --port 5433 --data-dir ./data
# Create the operator (aouda init), then POST /api/databases with auth enabled — see auth/setup.md
```

Create does not return a key, and a browser app needs none: a user signs in, and the session is the credential. Enable `signup` with the statements a user needs first ([Signup](../auth/principals.md#signup)); a signed-up principal can do nothing until you do. A backend's key belongs to a principal: declare it, or mint a key on it (**BL-1464, 0.16.0**).

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "default",
});

await client.connect();

// Sign up an app user
await client.auth.signUp("alice@example.com", "Password123!");

// Sign in
const session = await client.auth.signIn("alice@example.com", "Password123!");
// client now makes requests in Alice's context
```

---

## Error format

Access refusals follow a stable machine-readable contract:

```json
{
  "error": "AUTH_CREDENTIAL_EXPIRED",
  "message": "The session token has expired.",
  "requestId": "00000000000000000000000000000000",
  "remedy": { "kind": "renew", "expiredAt": "2026-11-25T09:30:00+00:00" }
}
```

Use `error` for programmatic retry/fix logic. Use [`remedy`](../auth/whoami.md#remedy) to generate the corrective action. Other errors carry `error` and `message`, and some a `suggestion`.

---

## What's available for AI agents today

| Capability | Status |
|---|---|
| `aouda start` local server bootstrap | Available |
| Password reset / invite email (server email provider) | Available — configure `Aouda:Auth:Email` (`console` or `sendgrid`) — see [auth/notifications.md](../auth/notifications.md) |
| Schema-on-write (no DDL needed) | Available |
| Identity-insert (`identityInsert: true` on insert / bulk-load) | Available — seed reserved autoIncrement IDs without schema flip; see [Getting Started](../getting-started/index.md) |
| Structured errors with a `remedy` | Available |
| One access model: principals, statements, one credential; `whoami` and `policy explain` | Available |
| MCP cluster tools in `@aouda/client` | Available |
| Full MCP server package (`@aouda/mcp-server`) | Planned |
| Natural-language query interface | Planned |

For full capability details see [AI Agents](index.md).

---

## Key links

**Next step, once the bootstrap above works:** [How to build apps effortlessly with Aouda](../guides/build-apps.md) — the canonical build path for a real application, including a [Rules for AI agents](../guides/build-apps.md#rules-for-ai-agents) section with the reading order, the hard rules, the per-screen decision procedure, the error contract, and a self-verification checklist. This page gets you a database; that page gets you an application.

- [Local CLI testing (agents)](local-cli-testing.md) — throwaway server recipe + CLI/schema/data-plane traps
- [Full Getting Started guide](../getting-started/index.md) — embedded mode, server mode, schema, auth, identity-insert
- [Bulk Load](../guides/bulk-load.md) — high-throughput ingest + `options.identityInsert`
- [Auth for AI agents](index.md#212-scenario-playbooks-minimum-three) — bootstrap, acting for a user, attributes and row conditions
- [HTTP API reference](../reference/http-api.md) — all endpoints
- [Named queries](../guides/named-queries.md) — execute by name; a browser does not compose ad-hoc queries
- [Direct client access](../guides/direct-client-access.md) — data-plane vs admin. A hosted OAuth login page is not shipped.
- [.NET client](../clients/dotnet.md) — full `Aouda.Client` reference, including column batches and bulk load
- [TypeScript client](../clients/typescript.md) — full SDK reference
