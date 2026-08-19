---
title: "Home"
nav_order: 0
description: "Aouda — columnar database engine for .NET with TypeScript client SDK"
---

# Aouda Documentation

Aouda is a **columnar database engine** for .NET with a TypeScript client SDK. It runs embedded in your process (like SQLite) or as a standalone server (like PostgreSQL). You control what stays in memory — from fully in-memory sub-millisecond access to terabytes on disk with only active partitions loaded.

---

## Install and run in 60 seconds

**Option A — CLI + .NET client:**

```bash
# Install the CLI and client
dotnet tool install -g Aouda.Cli
dotnet add package Aouda.Client

# Start a server
aouda start --port 5433
# Then in a new terminal: create a database
aouda databases create --name myapp
```

```csharp
// Connect, insert, and query
using Aouda.Client;

var client = new AoudaClient("http://localhost:5433", "myapp");

await client.GetTable("events").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1, ["name"] = "page_view", ["duration_ms"] = 123
});

var rows = await client.GetTable("events")
    .Where("duration_ms", "gte", 100)
    .ToListAsync();
// rows[0]["name"] == "page_view"
```

**Option B — Embedded (.NET only, no server needed):**

```bash
dotnet add package Aouda.Embedded
```

```csharp
using Aouda.Abstractions;
using Aouda.Embedded;

await using IAoudaDatabase db = await AoudaEmbedded.OpenDatabaseAsync();

await db.GetTable("events").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1, ["name"] = "page_view", ["duration_ms"] = 123
});

var rows = await db.GetTable("events")
    .Where("duration_ms", "gte", 100)
    .ToListAsync();
// rows[0]["name"] == "page_view"
// Database is automatically cleaned up when disposed
```

**Option C — TypeScript client:**

```bash
npm install @aouda/client
```

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
});
await client.connect();

await client.table("events").insert({ id: 1, name: "page_view", duration_ms: 123 });

const results = await client.table("events")
  .where("duration_ms", ">=", 100)
  .execute();
console.log(results.rows[0].name); // "page_view"
```

**Option D — Docker (server + Studio):**

```bash
docker compose up
# Aouda at http://localhost:5000  •  Studio at http://localhost:3000
```

---

## What Aouda gives you

| Capability | Detail |
|---|---|
| **Columnar storage** | Data stored column-by-column — analytical queries only read the columns they need |
| **Configurable memory residency** | Hot data in raw arrays for sub-ms access; cold data compressed on disk, loaded on demand |
| **Schema-on-write** | Tables and columns created automatically on first insert — no upfront design required |
| **Zero index management** | Zone maps, bloom filters, and sparse primary indexes maintained automatically |
| **Dual deployment** | Embedded (in-process, no network) or server (HTTP, multi-client, multi-language) |
| **Two-layer auth** | Server auth (who can connect) + Application auth (your app's end users) — independent systems |
| **Named queries** | Server-authored, hash-pinned read/write contracts for browsers; optional data-plane listener; access-surface diff in CI |
| **AI-native** | `aouda start` starts with defaults; structured errors include a `suggestion` field explaining what to do next; schema inference from POCO types |

---

## Where to start

**Building an application on Aouda?**
→ [Getting Started](getting-started/) — full guide covering embedded mode, server mode, data operations, schema, and auth

**Using the TypeScript client?**
→ [TypeScript Client](clients/typescript/) — query builder, typed queries, auth, MCP tools

**Exposing Aouda to a browser or SPA?**
→ [Direct client access](guides/direct-client-access.md) — listeners, `mk_pub_*`, named queries. [Division of responsibility](guides/division-of-responsibility.md) — what belongs in a service.

**Already have an app with services and a BFF in front of Aouda?**
→ [Adopting Aouda](guides/adoption.md) — target architecture, which hops to delete, migration order, and where the SDKs lag the engine.

**Setting up authentication?**
→ [Auth and Authorization](auth/) — two-layer auth model, API keys, JWT, ADRA modes

**Deploying to production?**
→ [Deployment](deployment/) — Kubernetes, Helm, Docker, Windows Service, systemd

**Building with AI agents?**
→ [AI Agent Quick Start](ai/quick-start/) — minimal bootstrap for agent-driven workflows

---

## Key concepts

Aouda has **two deployment modes** — the database engine is the same in both:

- **Embedded** — engine runs inside your process, direct API calls, no network, ideal for tests, tools, and single-process apps
- **Server** — standalone HTTP server, multiple clients, .NET + TypeScript + HTTP, replication, Studio management console

Aouda has **two independent auth systems**:

- **Server auth** — controls which services and developers can connect to the Aouda server (like PostgreSQL roles)
- **Application auth** — provides signup/signin/JWT for your app's end users (like Supabase Auth or Auth0)

Either can be used independently, together, or not at all.
