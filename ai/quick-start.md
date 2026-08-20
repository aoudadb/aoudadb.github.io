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
# Bootstrap server admin, then POST /api/databases with auth enabled — see auth/setup.md
```

Capture `anonKey` and `serviceRoleKey` from the create-database JSON response, then:

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "default",
  appAuth: { apiKey: "mk_anon_..." },  // key from startup output
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

All Aouda errors follow a stable machine-readable contract:

```json
{
  "error": "AUTH_TOKEN_EXPIRED",
  "message": "The access token has expired.",
  "suggestion": "Call POST /api/auth/refresh with your refreshToken.",
  "requestId": "req_abc123"
}
```

Use `error` for programmatic retry/fix logic. Use `suggestion` to generate the corrective action.

---

## What's available for AI agents today

| Capability | Status |
|---|---|
| `aouda start` local server bootstrap | Available |
| Password reset / invite email (server email provider) | Available — configure `Aouda:Auth:Email` (`console` or `sendgrid`) — see [auth/notifications.md](../auth/notifications.md) |
| Schema-on-write (no DDL needed) | Available |
| Identity-insert (`identityInsert: true` on insert / bulk-load) | Available — seed reserved autoIncrement IDs without schema flip; see [Getting Started](../getting-started/index.md) |
| Structured errors with `suggestion` field | Available |
| Two-layer auth with generated API keys | Available |
| MCP cluster tools in `@aouda/client` | Available |
| Full MCP server package (`@aouda/mcp-server`) | Planned |
| Natural-language query interface | Planned |

For full capability details see [AI Agents](index.md).

---

## Key links

**Next step, once the bootstrap above works:** [How to build apps effortlessly with Aouda](../guides/build-apps.md) — the canonical build path for a real application, including a [Rules for AI agents](../guides/build-apps.md#rules-for-ai-agents) section with the reading order, the hard rules, the per-screen decision procedure, the error contract, and a self-verification checklist. This page gets you a database; that page gets you an application.

- [Full Getting Started guide](../getting-started/) — embedded mode, server mode, schema, auth, identity-insert
- [Bulk Load](../guides/bulk-load/) — high-throughput ingest + `options.identityInsert`
- [Auth for AI agents](index.md#212-scenario-playbooks-minimum-three) — bootstrap, service key, ADRA grant flows
- [HTTP API reference](../reference/http-api/) — all endpoints
- [Named queries](../guides/named-queries.md) — pin hashes; do not compose ad-hoc queries with `mk_pub_*`
- [Direct client access](../guides/direct-client-access.md) — data-plane vs admin. PKCE is not shipped.
- [TypeScript client](../clients/typescript/) — full SDK reference
