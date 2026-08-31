---
title: "Getting Started"
nav_order: 1
has_children: true
---

# Getting Started with Aouda

This is the comprehensive guide to using Aouda. It covers both deployment models (embedded and server), data operations, schema management, and server authentication. By the end, you will understand how to create databases, insert and query data, and secure your Aouda server.

**This guide does NOT cover the Application Auth Service** (using Aouda as an authentication provider for your app's end users — signup, signin, sessions, JWTs for end users). That is a separate product feature documented in [Getting-Started-Auth.md](Getting-Started-Auth.md). Ad-hoc insert/query examples below are for **admin and service** callers. Browser-tier apps use [named queries](../guides/named-queries.md) on the [data-plane listener](../guides/direct-client-access.md).

---

## Quick Start

The fastest ways to get Aouda running:

### 1. CLI — instant, no Docker needed

```bash
# Install once
dotnet tool install -g Aouda.Cli

# Start server (no databases auto-created)
# --data-dir: root directory for catalog, WAL, and database files (default if omitted: ./data relative to cwd)
aouda start --port 5433 --data-dir ./aouda-data
```

Do **not** pass `-h` / `--help` to `aouda start` — current CLI builds ignore help on that subcommand and start a server on port **5000** with data under `./data`. AI agents that need a disposable probe: [Local CLI testing (agents)](../ai/local-cli-testing.md).

Set `--data-dir` (or `-d` / `--data-path`, same setting) to a stable path so data survives restarts, matches production layout, and is easy to back up. Server starts at `http://localhost:5433`. Create databases explicitly through API or `aouda databases create`.

```bash
# Create your first database explicitly
aouda databases create --name myapp
```

For a secured server, initialize the server admin after the server is running:

```bash
aouda init \
  --admin-email admin@derive.local \
  --admin-password "ChangeMeNow!" \
  --server http://localhost:5433 \
  --json
```

`aouda init` does **not** start Aouda. Run `aouda start`, Docker, Windows Service, `systemd`, or another host first, then point `aouda init` at that running server.

Required and optional arguments:

- `--server` is optional. If omitted, the CLI uses the locally started server from `aouda start`, then `AOUDA_SERVER` / `AOUDA_URL`, then `http://localhost:5000`. Passing `--server` is recommended for non-default ports such as `5433` or service-managed servers.
- `--admin-email` and `--admin-password` are required when the server is still in setup mode. On an already initialized server, provide them to sign in and return a token, or omit them to only verify that setup is complete.
- `--token` can be supplied when you already have an admin token and want `aouda init` to verify the server state without signing in.

`aouda init` is state-aware and retryable. It checks setup status, creates the first server admin if needed, and returns JSON describing what changed. It does not create databases.

Create whatever databases your application needs as explicit follow-up steps:

```bash
aouda databases create --name auth --kind auth --server http://localhost:5433 --token <admin-token>
aouda databases create --name user --auth-enabled --auth-database auth --server http://localhost:5433 --token <admin-token>
aouda databases create --name analytics --server http://localhost:5433 --token <admin-token>
aouda databases create --name cache --server http://localhost:5433 --token <admin-token>
```

This explicit server-then-database flow is intentional: it maps cleanly to production behavior and avoids hidden provisioning during startup.

### 2. Docker

```bash
docker run -p 5000:5000 -v aouda-data:/data aouda/server
```

### 3. Docker Compose — server + Studio

```bash
docker compose up
```

- Aouda at `http://localhost:5000`
- Aouda Studio at `http://localhost:3000`

### 4. Aouda.Setup — interactive installer (Windows + Linux)

No PowerShell or bash knowledge required. Extract the release archive and run:

- **Windows:** double-click `Aouda.Setup.exe`
- **Linux:** `sudo ./aouda-setup`

Answer five prompts (install mode, port, directories, admin email, password). Setup installs the Windows Service or systemd unit, creates a Start Menu / `.desktop` shortcut, and prints your API key.

See [Aouda.Setup guide](../guides/studio.md#12-aoudasetup-installer) for the full interaction and service registration details.

### 5. Hosted Studio at `studio.aouda.com` (no Studio install needed)

Visit `https://studio.aouda.com` in **Chrome or Edge**. Click **Connect**, enter your server URL (`http://localhost:5000` for local) and API key. The hosted Studio connects directly from your browser.

> **Firefox / Safari:** blocked by mixed-content policy when connecting to HTTP localhost from HTTPS Studio. Use Chrome or Edge. See [Studio guide §10.3](../guides/studio.md#103-browser-compatibility-for-localhost-access).

### Studio authentication after `aouda init` (important)

If you initialize server auth (for example with `aouda init`) and then open Studio, there is no separate username/password login screen in direct mode.

Use one of these Studio modes:

- **Direct mode (local Docker/npm)** — open Studio, go to **Settings → Authentication & API Keys**, and paste a **server credential** into **Connection API key**.
- **Hosted Studio (`studio.aouda.com`)** — click the server URL in the top nav (or wait for the first-run Connect dialog), enter your server URL and API key in the **Connect** dialog. Use Chrome or Edge for localhost connections.
- **Hub mode** (`NEXT_PUBLIC_HUB_URL` is set) — sign in on `/login` with your Hub account, then select a registered server and provide server credentials when prompted.

For direct mode, use a server auth credential (`/api/auth/...`) such as:

- a short-lived access token from `aouda init --json` or `/api/auth/signin`
- or a long-lived server admin key (`mk_srv_...`) created via:

```bash
curl -X POST http://localhost:5433/api/auth/admin/keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "studio-local"
  }'
```

Do not use application auth keys (`mk_anon_...` / `mk_svc_...`) as your Studio connection credential when you need server-wide administration.

---

For app-auth setup, initialize server admin first, then create/link databases explicitly (see [Getting-Started-Auth.md](Getting-Started-Auth.md)).
For the embedded / in-process path (no server): [Section 3](#3-embedded-mode--in-process-database).

---

## Table of Contents

1. [What is Aouda?](#1-what-is-aouda)
2. [Two Deployment Models](#2-two-deployment-models)
3. [Embedded Mode — In-Process Database](#3-embedded-mode--in-process-database)
4. [Server Mode — Standalone Database Server](#4-server-mode--standalone-database-server)
5. [Working with Data](#5-working-with-data)
6. [Schema Management](#6-schema-management)
7. [Choosing Your Auth Configuration](#7-choosing-your-auth-configuration)
8. [Server Authentication — Securing Database Access](#8-server-authentication--securing-database-access)
9. [Databases Without Authentication](#9-databases-without-authentication)
10. [Managing Multiple Databases](#10-managing-multiple-databases)
11. [Hot/Cold Storage and Memory Control](#11-hotcold-storage-and-memory-control)
12. [Branches](#12-branches)
13. [Backup and Restore](Getting-Started-Backup.md)
14. [What's Next](#14-whats-next)
15. [Contributor / Internal Developer Workflows](Aouda-Developer.md)
16. [Native Production Hosting (Windows + Linux)](#16-native-production-hosting-windows--linux) — including Aouda.Setup interactive installer (§16.9)

---

## 1. What is Aouda?

Aouda is a **columnar database engine** for .NET with fine-grained control over what lives in memory. It stores data in column-oriented structures optimized for analytical queries, caching, and time-series workloads. You decide what stays in memory — from keeping everything in-memory for sub-millisecond latency, to storing terabytes on disk with only active partitions loaded, to any mix in between. Persistence uses a write-ahead log (WAL) to disk.

Key characteristics:

- **Columnar storage** — Data is stored column-by-column, not row-by-row. This makes analytical queries (filtering, aggregation, projection) significantly faster because the engine only reads the columns needed.
- **Configurable memory residency** — You control what stays in memory. Hot data can live in uncompressed arrays (`int[]`, `double[]`, `string[]`) for sub-millisecond access. Cold data is compressed (Delta-Bitpack, Gorilla, Dictionary encoding) and can remain on disk, loaded on demand. For large datasets like time-series or logs, only a small working set needs to be in memory.
- **Schema-on-write** — Tables and columns are created automatically when you first insert data. No upfront schema design required, though explicit schemas are supported.
- **Zero index management** — The engine automatically maintains zone maps, bloom filters, and sparse primary indexes. You never create, tune, or rebuild an index.
- **Dual deployment** — Run it embedded in your process (like SQLite) or as a standalone server (like PostgreSQL).

Aouda is **not** a key-value store. It supports typed columns (Int32, Int64, Double, Decimal, String, Boolean, Timestamp, Guid), predicates (`=`, `!=`, `>`, `>=`, `<`, `<=`, `Between`, `In`, `IsNull`), projections, aggregations (SUM, COUNT, MIN, MAX), ordering, and pagination.

---

## 2. Two Deployment Models

Aouda operates in two fundamentally different modes. The database engine is the same in both — only the access layer differs.

### Embedded Mode

The database engine runs **inside your application process**. There is no server, no network, no HTTP. You call the database API directly through .NET method calls. Data lives in your process's memory.

```
┌──────────────────────────────────┐
│         Your Application          │
│                                  │
│   var db = AoudaEmbedded         │
│       .OpenDatabaseAsync();      │
│                                  │
│   ┌──────────────────────────┐   │
│   │     Aouda Engine          │   │
│   │  (in-process, no network) │   │
│   │  Storage: memory + disk   │   │
│   └──────────────────────────┘   │
└──────────────────────────────────┘
```

**When to use embedded mode:**
- Unit tests and integration tests (ephemeral databases that vanish after the test)
- CLI tools and scripts that need a local data store
- Single-process applications that don't need external access
- AI agent workflows where the agent needs instant, throwaway databases
- Prototyping and local development
- Applications where you want database functionality without running a server

**No server authentication needed.** Your process owns the database directly. There is no network boundary, no remote clients, and no reason to authenticate — the code that opens the database _is_ the only code that can access it.

### Server Mode

Aouda runs as a **standalone HTTP server** built on ASP.NET Core. Clients connect over the network using .NET or TypeScript SDKs (or raw HTTP). The server can host **multiple databases**, each with independent storage, schema, and access control.

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  .NET Client      │  │  TypeScript       │  │  curl / HTTP      │
│  (Aouda.Client)   │  │  (@aouda/client)  │  │                  │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                      │
         └─────────────────────┼──────────────────────┘
                               │ HTTP / REST
                    ┌──────────▼──────────┐
                    │   Aouda Server       │
                    │   (ASP.NET Core)     │
                    │                     │
                    │  ┌───────────────┐  │
                    │  │  Database A    │  │
                    │  │  Database B    │  │
                    │  │  Database C    │  │
                    │  └───────────────┘  │
                    └─────────────────────┘
```

**When to use server mode:**
- Multiple applications or services need to share the same data
- You need clients in different languages (TypeScript, .NET, or raw HTTP)
- You want centralized database management with monitoring (Aouda Studio)
- Production deployments with access control
- You want replication across multiple nodes

**Server authentication is available and recommended** for production. It controls which clients can connect and what they're allowed to do. See [Section 8](#8-server-authentication--securing-database-access).

### Choosing Between Modes

| Factor | Embedded | Server |
|--------|----------|--------|
| Network required | No | Yes |
| Multiple clients | No (single process) | Yes |
| Languages | .NET only | .NET, TypeScript, HTTP |
| Authentication | Not needed | Available |
| Replication | No | Yes |
| Aouda Studio | No | Yes |
| Setup complexity | Zero | Minimal |
| Performance | Fastest (no serialization) | Fast (HTTP overhead) |
| Use case | In-process, tests, tools | Multi-user, production |

---

## 3. Embedded Mode — In-Process Database

### Installation

```bash
dotnet add package Aouda.Embedded
```

### Creating an Ephemeral Database

An ephemeral database uses a temporary directory that is automatically deleted when the database is disposed. Perfect for tests and throwaway workloads.

```csharp
using Aouda.Abstractions;
using Aouda.Embedded;

// Open an ephemeral database — data goes to a temp directory and is cleaned up on dispose
await using IAoudaDatabase db = await AoudaEmbedded.OpenDatabaseAsync();

// Insert data — table "orders" is created automatically (schema-on-write)
await db.GetTable("orders").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1,
    ["customer"] = "Acme Corp",
    ["total"] = 249.99,
    ["created_at"] = DateTime.UtcNow
});

// Query data
var rows = await db.GetTable("orders")
    .Where("total", "gte", 100)
    .Select("id", "customer", "total")
    .Limit(10)
    .ToListAsync();

// When db is disposed, the temp directory is deleted
```

### Creating a Persistent Database

A persistent database writes to a specific directory. Data survives process restarts. The WAL (write-ahead log) ensures crash safety.

```csharp
await using IAoudaDatabase db = await AoudaEmbedded.OpenDatabaseAsync(
    new AoudaEmbeddedOptions
    {
        DataPath = "./my-database",  // Data stored here, survives restarts
        EnableWal = true,            // Write-ahead log for crash recovery (default: true)
    });

await db.GetTable("users").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1,
    ["name"] = "Alice",
    ["email"] = "alice@example.com"
});

// Dispose and re-open — data is still there
```

### Typed POCO Usage

Instead of dictionaries, you can use C# classes. Aouda infers the schema from the type:

```csharp
public class Order
{
    public long Id { get; set; }
    public string Customer { get; set; } = "";
    public decimal Total { get; set; }
    public DateTime CreatedAt { get; set; }
}

await using var db = await AoudaEmbedded.OpenDatabaseAsync();

// Insert a typed object — table and columns are inferred from Order
await db.GetTable<Order>().InsertAsync(new Order
{
    Id = 1,
    Customer = "Acme Corp",
    Total = 249.99m,
    CreatedAt = DateTime.UtcNow
});

// Query returns typed objects
List<Order> bigOrders = await db.GetTable<Order>()
    .Where("Total", "gte", 100)
    .ToListAsync();
```

### Synchronous API (Scripts and AI Agents)

For simple scripts or AI agent scenarios where async isn't needed:

```csharp
using IAoudaDatabase db = AoudaEmbedded.OpenDatabase();

// Synchronous — blocks the calling thread
db.GetTable("cache").InsertAsync(new Dictionary<string, object?>
{
    ["key"] = "session:abc",
    ["value"] = "data"
}).GetAwaiter().GetResult();
```

### Environment Variable Configuration

`AoudaEmbedded.OpenDatabaseAsync()` (no arguments) reads from environment variables:

| Variable | Purpose |
|----------|---------|
| `AOUDA_DATA_PATH` | Data directory. If not set, creates an ephemeral database. |
| `AOUDA_DATABASE` | Database name (for logging and identification). |

This allows the same code to run ephemerally in tests and persistently in production by just changing environment variables.

### Low-Level Engine Access

For advanced scenarios, you can access the underlying `AoudaEngine` directly:

```csharp
// CreateAsync returns EmbeddedDatabase with full engine access
await using var db = await AoudaEmbedded.CreateAsync("./data");

// Use the engine directly for explicit schema, custom options
await db.Engine.CreateTableAsync("sensors", new[]
{
    new ColumnDef("sensor_id", DataType.String, isPrimaryKey: true),
    new ColumnDef("timestamp", DataType.Timestamp),
    new ColumnDef("value", DataType.Double)
});

// Fluent query API on the engine
var recent = await db.Engine.Table("sensors")
    .Where(r => r.Col("timestamp").Gte(DateTime.UtcNow.AddHours(-1)))
    .OrderBy("timestamp", descending: true)
    .Limit(100)
    .ToListAsync();
```

### Embedded Options Reference

| Option | Type | Default | Allowed values | Description |
|--------|------|---------|----------------|-------------|
| `DataPath` | `string?` | `null` | `null` (ephemeral); any valid filesystem path | Directory for data files. `null` = ephemeral (temp dir, auto-deleted). |
| `EnableWal` | `bool` | `true` | `true`, `false` | Enable write-ahead log for crash recovery. |
| `MemoryBudget` | `long?` | `null` | `null` (no limit); any non-negative `long` (bytes) | Maximum memory in bytes. `null` = no limit. |
| `TreatMissingAsEmpty` | `bool` | `true` | `true`, `false` | When `true`, querying a non-existent table returns empty results instead of an error. Useful for cache-style usage. |

**Integration tests that need Application Auth** (OIDC discovery, JWT validation, real signup/signin against the HTTP API) cannot use embedded mode alone, because Application Auth requires the Aouda HTTP server. For those tests, use the **`Aouda.Testing`** package to start an in-process server from `dotnet test` — see [Getting-Started-Testing.md](Getting-Started-Testing.md).

---

## 4. Server Mode — Standalone Database Server

### Starting the Server

#### Option A: CLI Tool

```bash
dotnet tool install -g Aouda.Cli
aouda start --port 5433 --data-dir ./data
```

This starts the server at `http://localhost:5433`. Databases are created explicitly after startup.

Then create one or more databases via CLI or API (see [Creating Databases via API](#creating-databases-via-api)).

```bash
aouda databases create --name myapp
```

The `aouda` tool is the recommended local/developer command surface. It can start a foreground server for quick work, call the HTTP admin API, and provide script-friendly operations. In production, run the native server artifact under a service manager or container runtime, then administer it through `aouda`, HTTP APIs, Studio, or future MCP tools.

#### Common Server Startup Patterns

**1. No Auth — prototyping and testing**

```bash
aouda start --port 5433
```

No authentication is configured. All endpoints are open. Best for rapid prototyping and learning Aouda.

**2. With Application Auth — building user-facing apps**

```bash
aouda start --port 5433 --data-dir ./data
```

Then create an auth database and link your app database explicitly (see [Authentication Setup](auth.md)). For password reset and invite emails, configure an email provider on the server — `console` for local testing or SendGrid for production ([Email, SMS & Notifications](../auth/notifications.md)).

**3. Server Auth only — securing multi-database access**

For development environments that mirror production server auth (without app auth), bootstrap an admin and use server API keys. See [Section 8: Server Authentication](#8-server-authentication--securing-database-access).

> **Tip for AI Agents**: Use explicit startup + API flows (`aouda start`, `POST /api/databases`, auth setup endpoints). For managed or production instances, prefer the HTTP admin API and future MCP tools over shelling out to the server executable.

> **Internal/source workflows:** If you are developing Aouda itself (running from `src/`, local tool packaging, IDE task wiring, AppHost setup), use [Aouda-Developer.md](Aouda-Developer.md). This user guide intentionally stays product-facing.

#### Option B: Configuration File (local development)

For local development, you may place an optional `appsettings.json` in the directory from which you run `aouda start`. **Release installs and Setup do not use this file** — they pass `--data-path` and `--port` on the service command line instead. See [Server configuration](../guides/server-configuration.md).

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5433,
    "Databases": {
      "myapp": {
        "EnableWal": true
      }
    }
  }
}
```

Run Aouda from the directory containing this config:

```bash
aouda start
```

CLI flags and `AOUDA_*` environment variables override values in this file.

#### Option C: Hosting in Your Own ASP.NET Application

You can embed the Aouda server inside your own ASP.NET Core application:

```csharp
var builder = WebApplication.CreateBuilder(args);

// Register Aouda server services
builder.Services.AddAoudaServer(builder.Configuration);

builder.Services.AddControllers()
    .AddApplicationPart(typeof(Aouda.Server.Controllers.TablesController).Assembly);

var app = builder.Build();

app.UseAoudaAuthentication();
app.MapControllers();

app.Run();
```

This gives you a full Aouda server running inside your own host, alongside your own controllers and middleware.

#### Option D: Docker

Run the official Docker image:

```bash
docker run -p 5000:5000 -v aouda-data:/data aouda/server
```

- Server at `http://localhost:5000`
- Data persists in the `aouda-data` named volume across container restarts

Key environment variables:

| Variable | Default | Allowed values | Description |
|----------|---------|----------------|-------------|
| `AOUDA_DATA_PATH` | `/data` | Any valid filesystem path | Data directory inside the container |
| `AOUDA_BIND` | `0.0.0.0:5000` | Any valid `{address}:{port}` string (e.g. `0.0.0.0:5433`, `127.0.0.1:5000`) | Bind address |

For production with custom configuration, pass environment variables:

```bash
docker run -p 5000:5000 \
  -v aouda-data:/data \
  -e AOUDA_DATA_PATH=/data \
  aouda/server
```

#### Option E: Docker Compose — server + Studio

The `docker-compose.yml` in the Aouda repository starts the server and Studio together:

```bash
docker compose up
```

- **Aouda** at `http://localhost:5000`
- **Aouda Studio** at `http://localhost:3000`

Studio connects to Aouda automatically. No additional configuration needed — open `http://localhost:3000` to browse your databases.

For a 3-node cluster with replication and a witness node:

```bash
docker compose -f docker-compose.cluster.yml up
```

### Creating Databases via API

Once the server is running, create databases via HTTP:

```bash
# Create a database
curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -d '{ "name": "myapp" }'

# Create a database with WAL and memory limits
curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -d '{
    "name": "analytics",
    "enableWal": true,
    "maxMemoryBytes": 1073741824
  }'

# List databases
curl http://localhost:5433/api/databases

# Get database info
curl http://localhost:5433/api/databases/myapp

# Drop a database
curl -X DELETE http://localhost:5433/api/databases/myapp
```

### Connecting with the .NET Client

```bash
dotnet add package Aouda.Client
```

```csharp
using Aouda.Client;

// Connect to the server and target a specific database
var client = new AoudaClient("http://localhost:5433", "myapp");

// Insert data — table is auto-created if schema-on-write is enabled
await client.GetTable("products").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1,
    ["name"] = "Widget",
    ["price"] = 19.99,
    ["category"] = "Tools"
});

// Insert a typed object
await client.GetTable<Product>().InsertAsync(new Product
{
    Id = 2,
    Name = "Gadget",
    Price = 29.99m,
    Category = "Electronics"
});

// Query
var cheap = await client.GetTable("products")
    .Where("price", "lt", 25)
    .Select("id", "name", "price")
    .OrderBy("price")
    .Limit(50)
    .ToListAsync();
```

#### Client Options

```csharp
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    Timeout = TimeSpan.FromSeconds(30),
    AutoCreateSchema = true,       // Tables created on first insert
    TreatMissingAsEmpty = true,    // Missing tables = empty, not error
    RetryPolicy = RetryPolicy.Default,
    CircuitBreakerPolicy = CircuitBreakerPolicy.Disabled,
});
```

### Connecting with the TypeScript Client

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

// Insert
await client.table("products").insert({
  id: 1,
  name: "Widget",
  price: 19.99,
  category: "Tools",
});

// Insert many
await client.table("products").insertMany([
  { id: 2, name: "Gadget", price: 29.99, category: "Electronics" },
  { id: 3, name: "Doohickey", price: 9.99, category: "Tools" },
]);

// Query
const results = await client.table("products")
  .where("price", "<", 25)
  .orderBy("price", "asc")
  .limit(50)
  .select("id", "name", "price")
  .execute();

console.log(results.rows);
```

#### Typed TypeScript Client

Generate TypeScript types from your database schema for type-safe queries:

```bash
npx @aouda/client generate --server http://localhost:5433 --output ./types/schema.ts
```

```typescript
import { createAoudaClient, SchemaLike } from "@aouda/client";

interface Product {
  id: number;
  name: string;
  price: number;
  category: string;
}

interface AppSchema extends SchemaLike {
  tables: {
    products: Product;
  };
}

const client = createAoudaClient<AppSchema>({
  serverUrl: "http://localhost:5433",
  database: "myapp",
});

// client.table("products") returns TableQuery<Product> — fully typed
const results = await client.table("products").execute();
// results.rows is Product[]
```

### Tables API (TypeScript)

```typescript
// List tables
const tables = await client.tables.list();

// Get table schema
const schema = await client.tables.get("products");

// Create table explicitly
await client.tables.createTable({
  name: "orders",
  columns: [
    { name: "id", type: "Int64", isPrimaryKey: true },
    { name: "product_id", type: "Int64" },
    { name: "quantity", type: "Int32" },
    { name: "total", type: "Decimal" },
  ],
});

// Schema relationships (for ER diagrams)
const rels = await client.tables.relationships();
```

### Databases API (TypeScript)

```typescript
// List databases
const dbs = await client.databases.list();

// Create database
await client.databases.create("analytics");

// Drop database
await client.databases.drop("old-db");
```

---

## 5. Working with Data

These patterns work in both embedded and server modes. The API is the same — `IAoudaDatabase` (embedded) and `AoudaClient` (server) expose matching methods.

### Insert

```csharp
// Dictionary insert
await db.GetTable("orders").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1,
    ["customer"] = "Acme",
    ["total"] = 249.99,
    ["status"] = "pending"
});

// Typed insert
await db.GetTable<Order>().InsertAsync(new Order
{
    Id = 2, Customer = "Globex", Total = 500.00m, Status = "shipped"
});
```

### Query with Predicates

```csharp
// Filter + select + order + limit
var results = await db.GetTable("orders")
    .Where("total", "gte", 100)
    .Where("status", "eq", "pending")
    .Select("id", "customer", "total")
    .OrderBy("total", descending: true)
    .Limit(20)
    .Offset(0)
    .ToListAsync();
```

Supported predicates: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `nin`, `like`. Note: `ne` (not `neq`) is the not-equal operator. Using `ne` with `null` as value translates to `IS NOT NULL`. Empty `in` / `nin` arrays are rejected (`IN/NIN requires at least one value` — HTTP 400 on the server; the C# client throws before sending). `like` is ordinal and case-sensitive.

```csharp
// String-op form (Embedded and Aouda.Client)
var byIds = await db.GetTable("orders")
    .Where("Id", "in", new[] { 1, 2, 3 })
    .ToListAsync();

// Fluent In / Nin (Aouda.Client RemoteColumnRef and Embedded ColumnRef)
var clientRows = await client.GetTable("orders")
    .Where(r => r.Col("Id").In(1, 2, 3))
    .ToListAsync();
```

### Common Data Operation Errors

**Table not found:** Querying a table that does not exist throws `AoudaNotFoundException` (HTTP 404) unless `TreatMissingAsEmpty` is `true` (the default in `AoudaEmbeddedOptions`, not in `AoudaClientOptions`).

```csharp
// AoudaClientOptions.TreatMissingAsEmpty defaults to false — throws if table missing
// AoudaEmbeddedOptions.TreatMissingAsEmpty defaults to true — returns empty

// For the server client, enable it explicitly:
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    TreatMissingAsEmpty = true  // returns empty list for non-existent tables
});
```

**Schema mismatch on insert:** Inserting a value of the wrong type (e.g., a string into an `Int64` column) returns a structured error with an HTTP 400 status and a `suggestion` field explaining what the engine expected:

```json
{
  "error": "TYPE_MISMATCH",
  "message": "Column 'id' expects Int64 but received String 'abc'",
  "suggestion": "Cast the value to Int64 or check the schema with GET /api/databases/myapp/tables/orders"
}
```

**Insert without AutoCreateSchema (server mode):** If `AutoCreateSchema` is `false` (the default in `AoudaClientOptions`) and the table does not exist, inserting throws `AoudaNotFoundException`. Either create the table explicitly first, or set `AutoCreateSchema = true`.

**Missing auth token:** If server auth is enabled and no token is provided, the server returns HTTP 401 with `AUTH_TOKEN_MISSING`. See [Section 8](#8-server-authentication--securing-database-access) for the full error code table.

### Engine-Level Fluent Queries (Embedded)

When using the embedded engine directly, you get a richer predicate API:

```csharp
var results = await engine.Table("orders")
    .Where(r => r.Col("total").Gte(100) & r.Col("status").Eq("pending"))
    .Select("id", "customer", "total")
    .OrderBy("total", descending: true)
    .Limit(20)
    .ToListAsync();

// Between, In, IsNull
var filtered = await engine.Table("orders")
    .Where(r => r.Col("total").Between(50, 200)
              & r.Col("category").In("electronics", "tools")
              & r.Col("notes").IsNull())
    .ToListAsync();
```

Empty `In(...)` / `in` arrays throw `ArgumentException` (`IN/NIN requires at least one value`) rather than matching nothing.

### TypeScript Queries

```typescript
const results = await client.table("orders")
  .where("total", ">=", 100)
  .where("status", "=", "pending")
  .select("id", "customer", "total")
  .orderBy("total", "desc")
  .limit(20)
  .offset(0)
  .execute();

// Access results
for (const row of results.rows) {
  console.log(row.id, row.customer, row.total);
}
```

### Update and Delete

Both `.update()` and `.delete()` require at least one `.where()` condition — the server
rejects requests with no predicate as a safety guard.

```typescript
// Update — requires at least one where clause
await client.table("orders")
  .where("id", "=", 1)
  .update({ status: "shipped" });

// Delete — requires at least one where clause
await client.table("orders")
  .where("id", "=", 1)
  .delete();
```

```csharp
// .NET — same safety guard
await client.Table("orders")
    .Where("id", "eq", 1)
    .UpdateAsync(new Dictionary<string, object?> { ["status"] = "shipped" });

await client.Table("orders")
    .Where("id", "eq", 1)
    .DeleteAsync();
```

**Bulk mutation features (P27):** The update and delete surfaces have been extended with:

- **Expression SET** — evaluate server-side expressions without a read round-trip:
  ```ts
  await client.table('products')
    .where('status', '=', 'active')
    .update({ price: { $mul: 0.9 }, attempts: { $inc: 1 } });
  ```
- **TRUNCATE** — clear all rows atomically (requires `Truncate` auth scope):
  ```ts
  await client.table('logs').truncate();
  ```
- **DELETE with LIMIT** — safe rolling deletes with a `hasMore` loop:
  ```ts
  const result = await client.table('auditLog')
    .where('createdAt', '<', cutoff)
    .orderBy('createdAt', 'asc')
    .limit(1000)
    .delete();
  // result.hasMore → true if more rows remain
  ```
- **RETURNING** — capture which rows were changed in the same response:
  ```ts
  const result = await client.table('sessions')
    .where('expiresAt', '<', new Date())
    .delete({ returning: ['id', 'userId'] });
  // result.rows contains the deleted session data
  ```
- **Computed columns in SELECT** — server-side column math without storing:
  ```ts
  const result = await client.table('products')
    .selectExpr({ discounted: { $mul: { $col: 'price' }, 0.9 } })
    .execute();
  ```

For the full reference, examples, and common patterns, see the
[Bulk Mutations guide](../guides/bulk-mutations.md).

### Aggregations (Engine-Level)

```csharp
var stats = await engine.Table("orders")
    .Where(r => r.Col("status").Eq("completed"))
    .Select("category")
    .Sum("total")
    .Count()
    .GroupBy("category")
    .AggregateAsync();
```

---

## 6. Schema Management

### Schema-on-Write (Automatic)

When `AutoCreateSchema` is enabled (default in embedded mode), inserting into a non-existent table creates it. Column types are inferred from the values:

```csharp
// First insert creates the table with inferred schema
await db.GetTable("events").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1L,                           // → Int64
    ["name"] = "page_view",                // → String
    ["timestamp"] = DateTime.UtcNow,       // → Timestamp
    ["duration_ms"] = 123.45,              // → Double
    ["is_bot"] = false                     // → Boolean
});
```

When using typed POCOs, schema is inferred from the class properties. **Auto-increment must be declared explicitly** using `[AutoIncrement]` — plain integer properties are not auto-assigned by the server:

```csharp
using Aouda.Abstractions.Attributes;

public class Event
{
    [PrimaryKey, AutoIncrement]       // server assigns an incrementing Int64 on insert
    public long Id { get; set; }
    public string Name { get; set; } = "";
    public DateTime Timestamp { get; set; }
    public double DurationMs { get; set; }
    public bool IsBot { get; set; }
}

await db.GetTable<Event>().InsertAsync(new Event { ... });
// Table "Event" created; Id is populated by the server after insert
```

> **Why explicit attributes?**
> Aouda requires `[AutoIncrement]` instead of inferring auto-increment from a property name. This means the schema is fully described in the code — there are no hidden naming conventions to trip over, and renaming a property never silently changes the storage behavior.

**`[AutoIncrement]` vs. `[PrimaryKey]`** — these are two independent concerns:

| Attribute | Meaning |
|---|---|
| `[PrimaryKey]` | This column is the primary key (uniqueness, fast lookup). |
| `[AutoIncrement]` | The server assigns the value on insert (auto-incrementing integer). |

Use both together for the common surrogate-key pattern. You can have a primary key without auto-increment (e.g. a `Guid` you supply), or an auto-incrementing column that is not the primary key.

`[AutoIncrement]` behaves identically in both embedded mode and server mode — there are no naming conventions or implicit rules in either path.

### Seeding explicit IDs (identity-insert)

Sometimes you need to insert **client-chosen** values into an `autoIncrement` column (reserved ranges, reseed from another system, literal `0`) **without** flipping the column to manual via schema apply (BL-126). Use request-scoped **identity-insert**:

| Mode | When to use |
|------|-------------|
| Normal insert (`identityInsert` omitted/`false`) | Everyday writes. `0` / omitted means “please generate”. Explicit non-zero without the flag is stored but does **not** advance the counter. |
| Identity-insert (`identityInsert: true`) | Seed / reserved IDs. Every autoIncrement column required and non-null; `0` is a real stored value; after success the counter becomes `max(inserted)`. |
| Schema toggle (BL-126) | Permanently switch the column between Auto and Manual for all future writes. |
| Bulk-load `options.identityInsert` (BL-131) | Same semantics as identity-insert for large P20 begin/append/commit jobs — see [Bulk Load guide](../guides/bulk-load.md). |

```csharp
// C# / Embedded — Bond equivalent: isAutoIncrementDisabled: true
await table.InsertAsync(
    new Dictionary<string, object?> { ["Id"] = 1000L, ["Name"] = "Seeded" },
    identityInsert: true);

// Next normal insert gets 1001
await table.InsertAsync(new Dictionary<string, object?> { ["Id"] = 0L, ["Name"] = "Auto" });
```

```typescript
await client.table("orders").insert(
  { id: 1000, status: "seeded" },
  { identityInsert: true }
);

await client.table("orders").insertMany(
  [
    { id: 0, status: "literal-zero" },
    { id: 500, status: "reserved" },
  ],
  { identityInsert: true }
);
// Next auto-generated id is max(0, 500) + 1 = 501
```

```http
POST /api/databases/mydb/tables/orders/rows
Content-Type: application/json

{
  "database": "mydb",
  "table": "orders",
  "identityInsert": true,
  "rows": [{ "id": 1000, "status": "seeded" }]
}
```

Rules of thumb:
- Prefer identity-insert over temporarily disabling `autoIncrement` for one-shot seeds.
- Prefer [bulk-load identity-insert](../guides/bulk-load.md) when the seed is large enough for the P20 protocol.
- Studio does not expose an identity-insert UI — use the API/SDK (BL-130/131 Non-Scope).

### Explicit Schema Definition

For production use, you often want explicit control over data types, primary keys, partition keys, and auto-increment:

```csharp
await engine.CreateTableAsync("orders", new[]
{
    new ColumnDef("order_id", DataType.Int64, isPrimaryKey: true, isAutoIncrement: true),
    new ColumnDef("tenant_id", DataType.String, isPartitionKey: true),
    new ColumnDef("customer", DataType.String),
    new ColumnDef("amount", DataType.Decimal),
    new ColumnDef("status", DataType.String),
    new ColumnDef("created_at", DataType.Timestamp)
});
```

### Schema Operations via TypeScript Client

```typescript
// Export schema as JSON
const schema = await client.schema.export();

// Apply schema changes
await client.schema.apply(schemaDefinition);

// View schema diff
const diff = await client.schema.diff(newSchema);

// View schema history
const history = await client.schema.history();
```

### Declarative Schema (`aouda.schema.json`)

Aouda supports a declarative schema file that serves as the source of truth. Define your schema in JSON, and Aouda will diff and apply changes:

```json
{
  "tables": {
    "orders": {
      "columns": [
        { "name": "order_id", "type": "Int64", "isPrimaryKey": true, "autoIncrement": true },
        { "name": "tenant_id", "type": "String", "isPartitionKey": true },
        { "name": "amount", "type": "Decimal" },
        { "name": "created_at", "type": "Timestamp" }
      ]
    }
  }
}
```

### Adding Columns

Adding a column to an existing table does not backfill existing rows. Existing rows return the column's default value (null or type default) at query time:

```typescript
await client.tables.addColumn("orders", {
  name: "shipped_at",
  type: "Timestamp",
});
```

---

## 7. Choosing Your Auth Configuration

Aouda is flexible — it supports everything from zero-auth development to full production security with server auth and application auth. This section helps you choose the right configuration for your use case.

### The Auth Decision Flowchart

```
Is the database embedded in your process?
  YES → No auth needed. Your code is the only accessor.

Is this for local development or prototyping?
  YES → Use `aouda start --port 5433` (no auth)
        Then create databases explicitly via API/CLI

Do end users of YOUR APPLICATION need accounts?
  (signup, signin, user profiles, per-user data isolation)
  YES → Enable Application Auth on the database
        See: Getting-Started-Auth.md

Do you need to control which SERVICES/DEVELOPERS access the server?
  (database-scoped permissions, CI/CD service accounts)
  YES → Enable Server Authentication
        See: Section 8 below

Is this a cache or low-sensitivity internal database?
  YES → Consider running without auth (network security only)
        See: Section 9 below
```

### Deployment Scenarios at a Glance

| Scenario | Server Auth | App Auth | Setup |
|----------|:-----------:|:--------:|-------|
| **Embedded** (in-process, tests, tools) | — | — | `AoudaEmbedded.OpenDatabaseAsync()` |
| **Server (prototyping, no auth)** | — | — | `aouda start --port 5433` |
| **Server with app auth** (testing auth flows) | — | Yes | `aouda start --port 5433` + create/link auth DB |
| **Production cache** (low sensitivity) | Optional | — | Create DB without `auth.enabled` |
| **Production with server auth** (internal services) | Yes | — | Bootstrap admin, create API keys |
| **Production full-stack** (user-facing app) | Yes | Yes | Bootstrap admin + create DB with `auth.enabled` |
| **AI agent** (zero-friction) | — | Optional | `aouda start` + create DB via API |

### Aouda's Two Auth Systems

Aouda has **two independent auth systems** that serve different purposes:

| | Server Authentication | Application Auth Service |
|---|---|---|
| **Purpose** | Control who accesses the Aouda server | Provide signup/signin for your app's end users |
| **Analogy** | PostgreSQL roles, SQL Server logins | Supabase Auth, Firebase Auth, Auth0 |
| **Users** | DBAs, developers, CI/CD, backend services | Your app's customers and employees |
| **Routes** | `/api/auth/...` | `/api/databases/{db}/auth/...` |
| **Database** | `_serverauth` | `_auth` (or custom) |
| **Use independently?** | Yes | Yes |

They can be used independently, together, or not at all. A database can have server auth only, app auth only, both, or neither.

For complete Application Auth documentation, see [Getting-Started-Auth.md](Getting-Started-Auth.md).

---

## 8. Server Authentication — Securing Database Access

> **This section is about controlling who can connect to the Aouda server and access databases.** This is the equivalent of SQL Server authentication, PostgreSQL roles, or MongoDB SCRAM. It has nothing to do with authenticating your application's end users — that is a separate feature called the [Application Auth Service](Getting-Started-Auth.md).

### The Server Auth Hierarchy

Server authentication follows the same pattern as traditional databases: a server-level identity layer where credentials are scoped to specific databases.

```
Aouda Server Instance
├── Server Admin (superuser)
│   ├─ Access: ALL databases, ALL operations
│   └─ Analogy: PostgreSQL's `postgres`, SQL Server's `sa`
│
├── Server Users (database-scoped)
│   ├─ JWT claim: db_roles: { "myapp": ["db_writer"], "analytics": ["db_reader"] }
│   └─ Analogy: PostgreSQL roles with per-database GRANT
│
├── Server API Keys (database-scoped)
│   ├─ Prefix: mk_srv_
│   └─ Analogy: Service accounts / connection strings
│
├── Database: "myapp"     ← server users/keys need db_* role to access
├── Database: "analytics"  ← separate role grants
└── Database: "cache"      ← no auth (open access)
```

A server user or API key with `db_writer` on "myapp" **cannot** access "analytics" unless explicitly granted a role there.

### When Do You Need Server Authentication?

| Scenario | Server Auth Needed? |
|----------|-------------------|
| **Embedded mode** (in-process database) | **No** — your process owns the database |
| **Local development server** (single developer) | **Optional** — convenient to skip during development |
| **Server with multiple users/services** | **Yes** — control who can access what |
| **Production deployment** | **Yes** — always secure production servers |
| **Cache database** (low-sensitivity data) | **Optional** — you can create databases without auth |

### How Server Authentication Works

Like MS SQL Server or PostgreSQL, Aouda has a **server-level identity layer** where credentials are scoped to specific databases.

1. An **admin account** is created during initial setup (bootstrap). This is the superuser — equivalent to PostgreSQL's `postgres` role or SQL Server's `sa`.
2. The admin creates **server users** and **server API keys**, each with database-scoped roles that control which databases they can access and what they can do.
3. Clients authenticate (sign in or send API key) to receive/use a JWT.
4. The JWT includes a `db_roles` claim that maps databases to roles: `{ "myapp": ["db_writer"], "analytics": ["db_reader"] }`.
5. The server validates the token and checks whether the user has the required role for the target database.

**Server auth roles are database-scoped.** A service account with `db_writer` on "myapp" CANNOT access "analytics" unless explicitly granted a role there. This is the same model as PostgreSQL's `GRANT` or SQL Server's database-level users.

Default roles (applied per database):

| Role | Permissions |
|------|------------|
| `db_admin` | Full access — read, write, delete, create/alter/drop tables, manage users |
| `db_writer` | Read, write, and delete data |
| `db_reader` | Read-only access |

The server admin (superuser) has implicit `db_admin` on ALL databases. Regular server users and API keys must be granted roles for each database they need access to.

Auth state is stored in an internal database called `_serverauth`. This database is managed by Aouda and is not directly accessible as a user database.

### Step 1: Bootstrap the First Admin

When the server starts with no admin accounts, it enters **setup mode**. In setup mode, only the bootstrap endpoint is available, and only from localhost.

You can inspect first-run state in a machine-readable way:

```bash
curl http://localhost:5433/api/auth/setup/status
```

Response while setup is required:

```json
{
  "setupMode": true,
  "serverAuthConfigured": false,
  "adminBootstrapRequired": true,
  "allowedActions": ["postSetup"],
  "nextStep": "POST /api/auth/setup"
}
```

For server setup, prefer the retryable initializer:

```bash
aouda init \
  --admin-email admin@example.com \
  --admin-password "ChangeMeNow!" \
  --server http://localhost:5433 \
  --json
```

This assumes the server is already running. `aouda init` creates the first server admin if needed, or reports that the server is already initialized. It does not create auth or data databases.

After server init, create databases explicitly:

```bash
aouda databases create --name auth --kind auth --server http://localhost:5433 --token <admin-token>
aouda databases create --name user --auth-enabled --auth-database auth --server http://localhost:5433 --token <admin-token>
```

`--server` defaults to the locally started server or `http://localhost:5000`; pass it when using a different port or a service-managed server.

#### Option A: Setup Endpoint

```bash
curl -X POST http://localhost:5433/api/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "ChangeMeNow!"
  }'
```

Response:

```json
{
  "accessToken": "eyJhbG...",
  "refreshToken": "...",
  "expiresInSeconds": 900,
  "expiresAt": "2026-01-01T00:00:00Z"
}
```

Setup mode automatically disables after the first admin is created.

#### Option B: Configuration File (local development / advanced ops)

For local development or advanced operator setups, you may set the root user in an optional `appsettings.json` under `Aouda:Auth:RootUser`. Production installs via Setup use `create-admin` instead. Precedence: see [Server configuration](../guides/server-configuration.md).

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5433,
    "Auth": {
      "RootUser": {
        "Email": "admin@example.com",
        "Password": "ChangeMeNow!"
      }
    }
  }
}
```

The server creates the admin on first startup if the `_serverauth` database has no users.

**Security note:** Remove the plaintext password from configuration after the first admin is created.

#### Option C: Local Bootstrap Command

```bash
aouda create-admin \
  --email admin@example.com \
  --password "ChangeMeNow!" \
  --data ./data
```

This creates the admin directly in the data directory without starting the server. For binary-only or air-gapped installs, the native server artifact also supports the same local bootstrap operation:

```bash
./Aouda.Server create-admin \
  --email admin@example.com \
  --password "ChangeMeNow!" \
  --data ./data
```

Use this native command only for local/offline bootstrap against a data directory. Normal administration belongs in `aouda`, the HTTP admin API, Studio, and future MCP tools.

### Step 2: Sign In

After bootstrap, clients sign in to get a JWT:

```bash
curl -X POST http://localhost:5433/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "ChangeMeNow!"
  }'
```

Response:

```json
{
  "user": { "id": "...", "email": "admin@example.com" },
  "accessToken": "eyJhbG...",
  "refreshToken": "dGhpcyBp...",
  "expiresIn": 900
}
```

The `accessToken` is a JWT valid for 15 minutes. The `refreshToken` is valid for 30 days and can be exchanged for a new access token.

### Step 3: Use the Token

Include the access token in the `Authorization` header on database requests:

```bash
# Query a protected database
curl http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer eyJhbG..." \
  -H "Content-Type: application/json" \
  -d '{ "table": "orders", "limit": 10 }'
```

### Step 4: Token Refresh

When the access token expires, use the refresh token to get a new one:

```bash
curl -X POST http://localhost:5433/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{ "refreshToken": "dGhpcyBp..." }'
```

### Step 5: Sign Out

Revoke the session and invalidate the refresh token:

```bash
curl -X POST http://localhost:5433/api/auth/signout \
  -H "Authorization: Bearer eyJhbG..."
```

### Server Auth Endpoints Reference

All server auth endpoints are under `/api/auth/...` and resolve to the internal `_serverauth` database:

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/api/auth/setup` | POST | No (setup mode only) | Bootstrap first admin |
| `/api/auth/signin` | POST | No | Sign in, get JWT |
| `/api/auth/refresh` | POST | No | Refresh access token |
| `/api/auth/signout` | POST | Yes | Revoke session |
| `/api/auth/me` | GET | Yes | Current user profile |
| `/api/auth/me` | PATCH | Yes | Update profile metadata |
| `/api/auth/password` | PUT | Yes | Change password |
| `/api/auth/admin/users` | GET | Yes (`db_admin`) | List server users |
| `/api/auth/admin/users/{id}` | GET | Yes (`db_admin`) | Get user details |
| `/api/auth/admin/users/{id}` | PATCH | Yes (`db_admin`) | Update user |
| `/api/auth/admin/users/{id}/disable` | POST | Yes (`db_admin`) | Disable user |
| `/api/auth/admin/users/{id}/enable` | POST | Yes (`db_admin`) | Enable user |
| `/api/auth/admin/roles` | GET/POST | Yes (`db_admin`) | List/create roles |
| `/api/auth/admin/roles/{id}` | PATCH/DELETE | Yes (`db_admin`) | Update/delete role |
| `/api/auth/admin/users/{id}/roles` | GET/PUT | Yes (`db_admin`) | View/replace user role assignments |
| `/api/auth/admin/keys` | GET/POST | Yes (`db_admin`) | List/create API keys |
| `/api/auth/admin/keys/{id}` | DELETE | Yes (`db_admin`) | Revoke API key |

### SDK Usage with Server Auth

> **Server Auth vs Application Auth use separate options types.**
> The .NET client uses `ServerAuth = new ServerAuthOptions { ... }` for server-level access and `AppAuth = new AppAuthOptions { ... }` for application-user access. The TypeScript client uses `serverAuth` and `appAuth` respectively. These two properties are mutually exclusive.

#### .NET Client

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

// Recommended: Server API key (for production, CI/CD, services)
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    ServerAuth = new ServerAuthOptions
    {
        ApiKey = "mk_srv_..."       // Server API key — no refresh needed, long-lived
    }
});

var rows = await client.GetTable("orders").Limit(10).ToListAsync();
```

Other credential modes:

```csharp
// Email/password — for development and interactive tools
ServerAuth = new ServerAuthOptions
{
    Email = "admin@example.com",
    Password = "ChangeMeNow!"
}

// Pre-obtained token
ServerAuth = new ServerAuthOptions
{
    Token = "eyJhbG...",
    RefreshToken = "dGhpcyBp..."  // Optional — enables auto-refresh
}
```

#### TypeScript Client

Use `serverAuth` for server-level access. The TypeScript client does not support `email`/`password` in the constructor; use the REST API directly for server auth sign-in if needed.

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  serverAuth: {
    apiKey: "mk_srv_...",  // Server API key
  },
});

await client.connect();
const rows = await client.table("orders").limit(10).execute();
```

For pre-obtained server JWT:

```typescript
serverAuth: { token: "eyJhbG...", refreshToken: "..." }
```

### API Keys for Machine-to-Machine Access

For CI/CD pipelines, background jobs, and service-to-service communication, use API keys instead of email/password. **Server API keys are database-scoped** — specify which databases the key can access and with what roles.

```bash
# Create an API key scoped to specific databases (requires server admin)
curl -X POST http://localhost:5433/api/auth/admin/keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "myapp-backend",
    "databaseRoles": {
      "myapp": ["db_writer"],
      "analytics": ["db_reader"]
    }
  }'
```

Response includes the key (shown only once):

```json
{
  "id": "...",
  "name": "myapp-backend",
  "key": "mk_srv_abc123...",
  "databaseRoles": {
    "myapp": ["db_writer"],
    "analytics": ["db_reader"]
  }
}
```

This key can read/write `myapp` data and read `analytics` data. It cannot access any other database.

Use the API key as a bearer token:

```bash
# Access myapp — allowed (db_writer)
curl http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer mk_srv_abc123..." \
  -d '{ "table": "orders", "limit": 10 }'

# Access analytics — allowed (db_reader, read-only)
curl http://localhost:5433/api/databases/analytics/query \
  -H "Authorization: Bearer mk_srv_abc123..." \
  -d '{ "table": "events", "limit": 10 }'

# Access cache — DENIED (no role for this database)
curl http://localhost:5433/api/databases/cache/query \
  -H "Authorization: Bearer mk_srv_abc123..." \
  -d '{ "table": "data", "limit": 10 }'
# → 403 AUTHORIZATION_DENIED
```

### Server Auth vs Application Auth API Keys

If a database has Application Auth enabled (see [Getting-Started-Auth.md](Getting-Started-Auth.md)), it also has auto-generated **app API keys** (`mk_anon_...`, `mk_svc_...`). These are different from server API keys:

| | Server API Keys (`mk_srv_`) | App API Keys (`mk_anon_`, `mk_svc_`) |
|---|---|---|
| **Created by** | Server admin | Auto-generated when app auth is enabled |
| **Stored in** | `_serverauth` | `_auth` (app auth database) |
| **Scope** | One or more databases (via `databaseRoles`) | One specific database |
| **Use case** | Backend services, CI/CD, cross-database access | Frontend clients, per-database backend access |
| **PLS** | Never enforced | `mk_anon_`: enforced, `mk_svc_`: bypassed |

For a backend that only needs one database with app auth, the `mk_svc_` key is the simplest option. For cross-database access or databases without app auth, use server API keys (`mk_srv_`).

### Common Auth Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `AUTH_TOKEN_MISSING` | 401 | No Authorization header |
| `AUTH_TOKEN_INVALID` | 401 | Malformed or tampered JWT |
| `AUTH_TOKEN_EXPIRED` | 401 | JWT has expired — refresh it |
| `AUTH_TOKEN_REVOKED` | 401 | Session was signed out |
| `AUTH_API_KEY_INVALID` | 401 | API key not recognized or revoked |
| `AUTH_INVALID_CREDENTIALS` | 401 | Wrong email or password |
| `AUTHORIZATION_DENIED` | 403 | Valid token, insufficient permissions |
| `AUTH_ACCOUNT_LOCKED` | 423 | Too many failed attempts |
| `AUTH_RATE_LIMITED` | 429 | Rate limit exceeded |

### Security Best Practices

- **Remove plaintext passwords** from configuration files after initial bootstrap.
- **Use TLS** (HTTPS) for all non-local connections.
- **Prefer API keys** for machine-to-machine access — they don't expire and avoid the refresh dance.
- **Use short-lived JWTs** (15 minutes default) and rely on the refresh flow.
- **Rotate API keys** periodically and revoke unused keys.

---

## 9. Databases Without Authentication

Not every database needs authentication. For cache-style usage, development, or low-sensitivity data, you can create databases without auth:

```bash
# Create database without auth — no authentication required for access
curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -d '{ "name": "cache" }'
```

Clients can access this database without any credentials:

```csharp
// No auth needed
var client = new AoudaClient("http://localhost:5433", "cache");

await client.GetTable("fx_quotes").InsertAsync(new Dictionary<string, object?>
{
    ["key"] = "EURUSD.BID",
    ["value"] = 1.10234,
    ["timestamp"] = DateTime.UtcNow
});
```

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "cache",
  // No auth property — open access
});
```

Authentication is enforced **only** for databases that are explicitly linked to an auth database. Databases created without auth are openly accessible to anyone who can reach the server.

**When no-auth databases are appropriate:**
- Local development and prototyping
- Internal caches (volatile, low-sensitivity data)
- Read-only public datasets
- Embedded mode equivalents running in server mode for convenience

**When you should add auth:**
- Any database exposed to the internet
- Data with privacy requirements (PII, financial, health)
- Multi-tenant applications
- Any production deployment with untrusted clients

**Security for no-auth databases:** Use network-level security (firewalls, VPNs, Kubernetes network policies) to control who can reach the server. A no-auth database is open to anyone who can connect to the port.

---

## 10. Managing Multiple Databases

A single Aouda server can host many databases. Each database is independent — separate storage, separate schema, separate auth configuration.

```bash
# Create databases for different purposes
curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "app_production", "enableWal": true }'

curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "app_staging", "enableWal": true }'

curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "cache", "enableWal": false }'

# List all databases
curl http://localhost:5433/api/databases
```

Or declare them in an optional `appsettings.json` for local dev (API-created databases are the usual path in production):

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Databases": {
      "production": { "EnableWal": true },
      "staging": { "EnableWal": true },
      "cache": { "EnableWal": false }
    }
  }
}
```

See [Server configuration](../guides/server-configuration.md) for when this file applies vs service CLI flags.

Databases are stored in separate directories under the data path:

```
./data/
├── databases/
│   ├── production/
│   │   ├── catalog/
│   │   ├── tables/
│   │   └── wal/
│   ├── staging/
│   │   └── ...
│   └── cache/
│       └── ...
├── _serverauth/
│   └── ...
└── _auth/
    └── ...
```

---

## 11. Hot/Cold Storage and Memory Control

### Temperature Policies

Each table can have a different storage temperature policy:

```csharp
// Keep everything in raw memory — fastest queries
new TableOptions { StorageTemperaturePolicy = StorageTemperaturePolicy.HotOnly }

// Compress as soon as possible — minimum memory
new TableOptions { StorageTemperaturePolicy = StorageTemperaturePolicy.ColdPreferred }

// Let the engine decide based on age and memory pressure
new TableOptions
{
    StorageTemperaturePolicy = StorageTemperaturePolicy.Auto,
    TimeColumn = "timestamp",
    HotRetention = TimeSpan.FromHours(24)  // Keep last 24h hot
}
```

### Memory Budget

Control the total memory Aouda uses:

```json
{
  "Aouda": {
    "Memory": {
      "MaxTotalRamBytes": 4294967296,
      "MaxHotBytes": 0,
      "MaxPageCacheBytes": 0
    }
  }
}
```

When `MaxHotBytes` and `MaxPageCacheBytes` are 0, the engine uses heuristic defaults (70% hot, 20% page cache, 10% overhead).

### Per-Table Memory

```csharp
new TableOptions
{
    HotByteBudget = 1073741824,  // 1 GB max hot memory for this table
}
```

---

## 12. Branches

Create lightweight branches for testing or migrations:

```typescript
// Create a branch
await client.branches.create({ name: "feature-x", parentBranch: "main" });

// List branches
const branches = await client.branches.list();

// Get branch info
const branch = await client.branches.get("feature-x");

// View diff between branch and parent
const diff = await client.branches.diff("feature-x");

// Merge branch (execute: true applies changes; omit or dryRun: true to preview only)
await client.branches.merge("feature-x", { execute: true });

// Delete branch
await client.branches.delete("feature-x");
```

---

## 14. What's Next

### Backup and Restore

- **[Backup and Restore](Getting-Started-Backup.md)** — Incremental backups to local filesystem or S3 (including S3-compatible services such as MinIO and LocalStack). REST and TypeScript client APIs for exact restore. Retention and GC. Point-in-time recovery is not implemented yet — see the guide's PITR note.

### Authentication & Authorization

- **[Application Auth Service](Getting-Started-Auth.md)** — Use Aouda as an authentication provider for your app's end users (signup, signin, JWTs, Partition-Level Security, multi-tenancy). Covers the two-layer auth model, architecture patterns A-D, API keys, and AI agent workflows.
- **[Auth ADR (0023)](../decisions/0023-authentication-and-authorization.md)** — The architecture decision record covering the full auth design, including Partition-Level Security and RBAC.

### General

- **[Testing with Aouda.Testing](Getting-Started-Testing.md)** — In-process integration tests, including Application Auth, xUnit/NUnit/MSTest fixtures, and CI-friendly `dotnet test` workflows.
- **[Architecture](../ARCHITECTURE.md)** — Deep dive into Aouda's technical design.
- **[ADR Index](../decisions/)** — All architecture decision records.
- **[HTTP API](../reference/http-api.md)** — Wire contract, including authentication headers and error codes.
- **[Aouda Studio](https://github.com/aouda/aouda-studio)** — Web management console.

---

## 15. Contributor / Internal Developer Workflows

Internal contributor workflows (running Aouda from source, local `.nupkg` tool distribution, IDE task wiring, AppHost orchestration, and source-build setup) are documented in [Aouda-Developer.md](Aouda-Developer.md).

This guide intentionally stays focused on Aouda users and production-facing usage.

---

## 16. Native Production Hosting (Windows + Linux)

This section makes the non-Docker deployment path explicit: publish Aouda as a normal executable, run it as a service, and secure it with server auth on first install.

Aouda intentionally separates the runtime artifact from the administration surface:

- `Aouda.Server.exe` / `./Aouda.Server` runs the database server and supports local/offline bootstrap commands such as `create-admin`.
- Windows Service Control Manager, `systemd`, Docker, or Kubernetes should own production process lifecycle.
- `aouda`, HTTP admin APIs, Studio, and future MCP tools should own normal administration.

### 16.1 Usage Modes You Should Offer

For cross-platform teams, offer these three paths side-by-side:

| Mode | Command style | Best for |
|---|---|---|
| **Development/local** | `aouda start ...`, then `aouda databases ...` / API | Demos, quick testing, local AI-agent workflows |
| **Production service** | `Aouda.Server.exe` / `./Aouda.Server` under SCM, `systemd`, Docker, or Kubernetes | VMs, bare metal, containers, managed hosts |
| **Native bootstrap** | `Aouda.Server create-admin --data ...` | Binary-only or air-gapped first install before the service is exposed |

The engine and auth model are the same in all modes. What changes is ownership: service managers keep the server process alive, while `aouda`, HTTP APIs, Studio, and future MCP tools administer the running instance.

### 16.2 Publish Aouda as a Native Executable

For user/deployment workflows, use prebuilt Aouda server artifacts for your target platform (`win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`).

If you need to build artifacts from source, use the contributor guide: [Aouda-Developer.md](Aouda-Developer.md).

Choose framework-dependent or self-contained artifacts depending on your runtime requirements.

### 16.3 Production Directory Layout (Recommended)

Use explicit directories so upgrades are predictable and data survives binary replacement:

- **Windows**
  - Binary: `C:\Program Files\Aouda\` (or any install path chosen in Setup)
  - Data: `C:\ProgramData\Aouda\data\` (default; operator may choose another folder)
  - Bootstrap: Windows Service command line — `--data-path` and `--port` (not a config file)
  - Logs: console by default; optional operator logging config
- **Linux**
  - Binary: `/opt/aouda/` (or install path from Setup)
  - Data: `/var/lib/aouda/` (default)
  - Bootstrap: systemd `ExecStart` flags — `--data-path` and `--port`
  - Logs: `/var/log/aouda/` (created by install scripts on Linux)

Keep **data** outside the binary folder. See [Server configuration](../guides/server-configuration.md) for precedence and restart behavior.

### 16.4 Production Install Flow (with Server Auth)

For production, treat auth bootstrap as part of installation:

1. Install binaries and create persistent data/config directories.
2. Bootstrap the first admin with either local/offline data-directory bootstrap or the localhost setup endpoint.
3. Start Aouda under the production service manager or container runtime.
4. Create service API key(s) for applications.
5. Remove plaintext bootstrap password from config (if used).
6. Point apps to API key auth.

#### Option A: Bootstrap admin locally with the native artifact

```powershell
& "C:\Program Files\Aouda\Aouda.Server.exe" create-admin `
  --email admin@example.com `
  --password "Use-A-Strong-Secret" `
  --data "C:\ProgramData\Aouda\data"
```

Linux equivalent:

```bash
/opt/aouda/Aouda.Server create-admin \
  --email admin@example.com \
  --password "Use-A-Strong-Secret" \
  --data /var/lib/aouda
```

Use this path when the server is not running yet or when you want a minimal binary-only install. It writes directly to the local data directory and does not require `Aouda.Client` or a reachable HTTP endpoint.

#### Option B: Bootstrap admin with `aouda create-admin`

```bash
aouda create-admin \
  --email admin@example.com \
  --password "Use-A-Strong-Secret" \
  --data /var/lib/aouda
```

This is the friendlier CLI path for install scripts and operator laptops. It uses the same local bootstrap implementation but keeps humans and scripts on the normal `aouda` command surface.

#### Option C: Bootstrap via setup endpoint (first run only, localhost)

```bash
curl -X POST http://localhost:5433/api/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "Use-A-Strong-Secret"
  }'
```

### 16.5 Create Service API Keys for Applications

After admin bootstrap, sign in once and create scoped server API keys (`mk_srv_...`) per service:

```bash
curl -X POST http://localhost:5433/api/auth/admin/keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "orders-api",
    "databaseRoles": {
      "orders": ["db_writer"],
      "analytics": ["db_reader"]
    }
  }'
```

Store returned keys in a secret manager. Do not keep them in source control or plaintext install scripts.

### 16.6 Run as a Windows Service

After publishing and copying files, install Aouda under Service Control Manager:

```powershell
sc.exe create Aouda binPath= "\"C:\Program Files\Aouda\Aouda.Server.exe\" --contentRoot \"C:\ProgramData\Aouda\"" start= auto
sc.exe start Aouda
```

Use `sc.exe stop Aouda`, the Services UI, or your deployment system to stop the service. Do not use the server executable as the normal process-control client. For first install, bootstrap admin before exposing the server beyond localhost/firewalled boundaries.

### 16.7 Run as a Linux `systemd` Service

Example unit file (`/etc/systemd/system/aouda.service`):

```ini
[Unit]
Description=Aouda Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/aouda
ExecStart=/opt/aouda/Aouda.Server --contentRoot /etc/aouda
Restart=always
RestartSec=5
User=aouda
Group=aouda

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable aouda
sudo systemctl start aouda
```

Use `sudo systemctl stop aouda`, `restart`, and `status` for lifecycle operations. Use `aouda`, HTTP admin APIs, Studio, or future MCP tools for administration of the running instance.

### 16.8 Make Cross-Platform Setup Equally Simple

To keep Windows and Linux equally easy, ship:

1. Prebuilt artifacts for `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`.
2. One install script per OS that:
   - copies binaries and config templates
   - creates data directories with correct permissions
   - bootstraps first admin
   - creates initial service API key
   - installs/starts OS service
3. A single "Day 1" checklist in docs:
   - install
   - bootstrap auth
   - create app key
   - connect first client

If you do this, Docker becomes optional instead of required, and native deployment is first-class on both Windows and Linux.

### 16.9 Interactive Installer: Aouda.Setup

For first-time installs where the operator prefers a guided experience over running scripts, use **Aouda.Setup** — a zero-dependency .NET 8 console app shipped alongside the server binary in the release archive:

| Platform | Binary | Requires |
|----------|--------|----------|
| Windows | `Aouda.Setup.exe` (double-click) | Run as Administrator |
| Linux | `aouda-setup` | `sudo ./aouda-setup` |

The setup app:
1. Prompts for install mode (Windows Service / systemd, or manual), port, directories, admin email, and password.
2. Copies binaries to the install directory (no `appsettings.json`).
3. Registers the OS service with `--data-path` and `--port` on the command line.
4. Bootstraps the first admin (`Aouda.Server create-admin` directly to the data directory).
5. Creates a Start Menu shortcut (Windows) or `.desktop` shortcut (Linux).
6. Prints a completion banner with the server URL and API key.

See [Aouda.Setup guide](../guides/studio.md#12-aoudasetup-installer) for the full interactive sequence, manual mode, service registration details, and shortcut paths.

### 16.10 Automated Install Scripts (Windows + Linux)

For CI/CD pipelines and scripted deployments, the non-interactive install scripts are unchanged and remain the preferred tool:

- binary copy and directory setup
- initial server admin bootstrap (`Aouda.Server create-admin` or `aouda create-admin`)
- service installation/start (Windows Service or `systemd`)
- full server administrator API key creation (`mk_srv_...`, all server-level access)

Scripts:

- `scripts/install-aouda.ps1`
- `scripts/install-aouda.sh`

#### Prerequisites

1. You have published/extracted Aouda server artifacts for the target OS.
2. `aouda` CLI is installed on the host (`dotnet tool install -g Aouda.Cli`) if the script creates API keys or performs remote administration. A minimal bootstrap-only install can use the native `Aouda.Server create-admin` command.
3. You run the script with elevated privileges:
   - Windows: PowerShell as Administrator
   - Linux: `sudo`

#### Windows example

```powershell
.\scripts\install-aouda.ps1 `
  -ArtifactDir "C:\temp\aouda-win-x64-sc" `
  -AdminEmail "admin@example.com" `
  -AdminPassword "Use-A-Strong-Secret" `
  -ApiKeyName "primary-admin-key"
```

#### Linux example

```bash
chmod +x ./scripts/install-aouda.sh
sudo ./scripts/install-aouda.sh \
  --artifact-dir /tmp/aouda-linux-x64-sc \
  --admin-email admin@example.com \
  --admin-password 'Use-A-Strong-Secret' \
  --api-key-name primary-admin-key
```

#### Security notes

- The script prints the generated API key once. Store it immediately in your secret manager.
- Avoid passing secrets on shared shells where command history is collected.
- Rotate the bootstrap admin password and service API keys according to your security policy.

---

## Quick Reference: Embedded vs Server API

| Operation | Embedded (.NET) | Server (.NET Client) | Server (TypeScript) |
|-----------|----------------|---------------------|-------------------|
| Open/connect | `AoudaEmbedded.OpenDatabaseAsync()` | `new AoudaClient(url, db)` | `createAoudaClient({...})` |
| Get table | `db.GetTable("t")` | `client.GetTable("t")` | `client.table("t")` |
| Insert dict | `.InsertAsync(dict)` | `.InsertAsync(dict)` | `.insert({...})` |
| Insert typed | `.InsertAsync(obj)` | `.InsertAsync(obj)` | `.insert({...})` |
| Identity-insert | `.InsertAsync(..., identityInsert: true)` | `.InsertAsync(..., identityInsert: true)` | `.insert(row, { identityInsert: true })` |
| Bulk-load identity-insert | `BulkLoadOptions { IdentityInsert = true }` | same | `.bulkLoad(rows, { identityInsert: true })` |
| Query | `.Where(...).ToListAsync()` | `.Where(...).ToListAsync()` | `.where(...).execute()` |
| List tables | `db.Schema.ListTablesAsync()` | `client.Schema.ListTablesAsync()` | `client.tables.list()` |
| Dispose | `await db.DisposeAsync()` | `await client.DisposeAsync()` | `await client.disconnect()` |
