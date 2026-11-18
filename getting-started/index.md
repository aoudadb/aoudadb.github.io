---
title: "Getting Started"
nav_order: 1
has_children: true
---

# Getting Started with Aouda

This is the comprehensive guide to using Aouda. It covers both deployment models (embedded and server), data operations, schema management, and server authentication. By the end, you will understand how to create databases, insert and query data, and secure your Aouda server.

**This guide does NOT cover the Application Auth Service** (using Aouda as an authentication provider for your app's end users — signup, signin, sessions, JWTs for end users). That is a separate product feature documented in [Getting-Started-Auth.md](auth.md). Ad-hoc insert/query examples below are for **admin and service** callers. Browser-tier apps use [named queries](../guides/named-queries.md) on the [data-plane listener](../guides/direct-client-access.md).

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
printf '%s' "ChangeMeNow!" | aouda init \
  --admin-email admin@derive.local \
  --admin-password-stdin \
  --server http://localhost:5433 \
  --json
```

On Windows, `printf` is not a command in PowerShell or `cmd`. Pipe the password from an environment variable instead:

```powershell
$env:ADMIN_PASSWORD | aouda init `
  --admin-email admin@derive.local `
  --admin-password-stdin `
  --server http://localhost:5433 `
  --json
```

`aouda init` never prompts for a password, on any platform: a prompt that reads the terminal is what stalls a script or an agent. Without
`--admin-password-file` or `--admin-password-stdin` it stops with `ADMIN_CREDENTIALS_REQUIRED` and names both (**BL-1226, 0.9.0**;
before, the message named neither). Windows PowerShell 5.1 encodes what it pipes to a program as ASCII by default, so a password with
non-ASCII characters belongs in `--admin-password-file` (or in PowerShell 7).

`aouda init` does **not** start Aouda. Run `aouda start`, Docker, Windows Service, `systemd`, or another host first, then point `aouda init` at that running server.

Required and optional arguments:

- `--server` is optional. If omitted, the CLI uses the locally started server from `aouda start`, then `AOUDA_SERVER` / `AOUDA_URL`, then `http://localhost:5000`. Passing `--server` is recommended for non-default ports such as `5433` or service-managed servers.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
- `--token` can be supplied when you already have an admin token and want `aouda init` to verify the server state without signing in.

`aouda init` is state-aware and retryable. It checks setup status, creates the first server admin if needed, and returns JSON describing what changed. It does not create databases.

Create whatever databases your application needs as explicit follow-up steps:

```bash
aouda databases create --name auth --kind auth --server http://localhost:5433 --token <admin-token>
aouda databases create --name user --auth-enabled --auth-database auth --server http://localhost:5433 --token <admin-token>
aouda databases create --name analytics --server http://localhost:5433 --token <admin-token>
aouda databases create --name cache --server http://localhost:5433 --token <admin-token>
```

**Keys are shown once.** `aouda databases create` for a database linked to an auth database (`--kind auth`, or `--auth-enabled`) prints
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
generated them. The server keeps a hash, so it cannot show a key again, and a create that finds the keys already issued (the auth
database already holds that name's system keys) returns none. The CLI says which happened on stderr, also under `--json`, so stdout stays one JSON document: do not merge `2>&1` into a JSON parser (**BL-1226, 0.9.0**). To
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
  [Named service keys and overlapping rotation](../reference/http-api.md) (authentication section).
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

This explicit server-then-database flow is intentional: it maps cleanly to production behavior and avoids hidden provisioning during startup.

### 2. Docker

```bash
docker run -d --name aouda -m 2g --cpus 4 -p 127.0.0.1:5000:5000 -v aouda-data:/data \
  ghcr.io/aoudadb/aouda-server:<version>
```

The image is private (`docker login ghcr.io` with a token that has `read:packages` first), `-m` is what makes the server size its memory from the container's limit, and `127.0.0.1:` keeps the admin API off the host's other interfaces. See [Docker](../deployment/docker.md) for why each matters.

### 3. Docker Compose — server + Studio

```bash
docker compose up
```

- Aouda at `http://localhost:5000`
- Aouda Studio at `http://localhost:3000`

The compose file takes one declaration: an operator in a declaration file, `aouda.json` next to the compose file with its volume line uncommented, and `AOUDA_DECLARATION=/etc/aouda/aouda.json` plus, for a first admin seeded from `{ "password": { "env": "AOUDA_ADMIN_PASSWORD" } }`, `AOUDA_ADMIN_PASSWORD=<something long>` in `.env` (**BL-1464, next train**; a key-only operator needs no human admin), or, for a throwaway, `AOUDA_DEV_ADMIN=true docker compose up` (**BL-1423, 0.12.0**; the line to read is the `AOUDA-DEV-ADMIN` line of `docker compose logs aouda`). With none, the server waits in setup mode and `/ready` answers `503 setup_required`. The old `AOUDA_SERVER_KEY`, `AOUDA_ROOT_EMAIL` and `AOUDA_ROOT_PASSWORD` are no longer passed. See [Docker](../deployment/docker.md#compose).

### 4. Aouda.Setup — interactive installer (Windows + Linux)

No PowerShell or bash knowledge required. Extract the release archive and run:

- **Windows:** double-click `Aouda.Setup.exe`
- **Linux:** `sudo ./Aouda.Setup`

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

See [Aouda.Setup guide](../guides/studio.md#12-aoudasetup-installer) for the full interaction and service registration details.

### 5. Hosted Studio at `studio.aouda.com` (no Studio install needed)

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

> **Firefox / Safari:** blocked by mixed-content policy when connecting to HTTP localhost from HTTPS Studio. Use Chrome or Edge. See [Studio guide §10.3](../guides/studio.md#103-browser-compatibility-for-localhost-access).

### Studio authentication after `aouda init` (important)

If you initialize server auth (for example with `aouda init`) and then open Studio, there is no separate username/password login screen in direct mode.

Use one of these Studio modes:

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
- **Hub mode** (`NEXT_PUBLIC_HUB_URL` is set) — sign in on `/login` with your Hub account, then select a registered server and provide server credentials when prompted.

For direct mode, use a server auth credential (`/api/auth/...`) such as:

- a short-lived access token from `aouda init --json` or `/api/auth/signin`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

```bash
curl -s http://localhost:5000/api/auth/whoami \
  -H "Authorization: Bearer $AOUDA_KEY"
```

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

---

For app-auth setup, initialize server admin first, then create/link databases explicitly (see [Getting-Started-Auth.md](auth.md)).
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
13. [Backup and Restore](backup.md)
14. [What's Next](#14-whats-next)
15. [Contributor / Internal Developer Workflows](https://github.com/aoudadb/aouda/blob/main/docs/dev/Aouda-Developer.md)
16. [Native Production Hosting (Windows + Linux)](#16-native-production-hosting-windows--linux) — including Aouda.Setup interactive installer (§16.9)

---

## 1. What is Aouda?

Aouda is a **columnar database engine** for .NET with fine-grained control over what lives in memory. It stores data in column-oriented structures optimized for analytical queries, caching, and time-series workloads. You decide what stays in memory — from keeping everything in-memory for sub-millisecond latency, to storing terabytes on disk with only active partitions loaded, to any mix in between. Persistence uses a write-ahead log (WAL) to disk.

Key characteristics:

- **Columnar storage** — Data is stored column-by-column, not row-by-row. This makes analytical queries (filtering, aggregation, projection) significantly faster because the engine only reads the columns needed.
- **Configurable memory residency** — You control what stays in memory. Hot data can live in uncompressed arrays (`int[]`, `double[]`, `string[]`) for sub-millisecond access. Cold data is encoded per 2,048-row vector — frame-of-reference and delta bit-packing, run-length, ALP for doubles, sorted dictionaries for strings (**ColumnarRead, 0.3.0**) and can remain on disk, loaded on demand. For large datasets like time-series or logs, only a small working set needs to be in memory.
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
        Durability = "strict",       // WAL written through before a write is visible (default: "strict")
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
using Aouda.Abstractions.Attributes;

public class Order
{
    public long Id { get; set; }
    public string Customer { get; set; } = "";
    [AoudaDecimal(18, 2)]              // a decimal declares its precision and scale
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

**Positional records and other constructor-built types** (**BL-1390, 0.11.0**). A row type with no public parameterless
constructor, such as a positional record, is built through its single public constructor. Each parameter is bound to the result
column of the same name (case-insensitive; a `[AoudaColumn]` on the same-named property renames the column), then the remaining
settable properties (`init`, `required`, `set`) are written:

```csharp
public sealed record Trade(long Id, string Name, double Price, int? Lots = null)
{
    public string? Desk { get; init; }
}

List<Trade> trades = await db.GetTable<Trade>().ToListAsync();
```

- A column the type does not use is ignored.
- A column missing from the result is an error naming the type, the parameter and the column, unless the parameter has a default
  value, is `Nullable<T>`, or is a nullable reference (`string?`); then it gets that default or `null`.
- A null cell given to a non-nullable value-type parameter gives `default(T)`, exactly as it does for a property.
- A class that has a parameterless constructor keeps using it. A class with several public constructors and no parameterless one is
  refused when `GetTable<T>()` is called, and the error lists them; give it a parameterless constructor (or a single constructor).
  There is no attribute to choose one.
- A parameter whose property is `[AoudaIgnore]`d is not a column: it is never read or required and gets `default(T)` (`null` for a reference type). `AoudaIgnore` applies to properties, so on a record write `[property: AoudaIgnore] object State`. The embedded engine's schema inference honours `[AoudaIgnore]` too.
- A `record struct` works the same way, and so does a struct that declares exactly one public constructor (before, it was built as
  `default` and its properties written).
- Writing reads the type's public properties, so a record's properties are the columns. A get-only property that only a
  constructor sets is not a column.

The same holds in the embedded engine and for `ClientColumnarResult.ToObjects<T>()`.

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
| `Durability` | `string` | `"strict"` | `"strict"`, `"os"`, `"unlogged"`, `"memory"` | (**Lead S26, 0.6.0**) The database's durability level: `strict` writes the WAL through to disk before a write is visible (survives a power loss), `os` writes it to the operating system (survives a process crash), `unlogged` has no WAL (kept whole by a clean close; after any other stop it keeps its flushed rows, or is emptied if it was being changed — (**Lead S26c, 0.6.0**)), `memory` has no WAL and no data files. Also set by config `Aouda:Durability`. It replaces `EnableWal`: setting `EnableWal` (in code or as `Aouda:EnableWal`) makes the open throw, naming `Durability`. See [Write Path Durability](../guides/write-durability.md#durability-levels-lead-s26-060). |
| `MemoryBudget` | `long?` | `null` | `null` (no limit); any non-negative `long` (bytes) | Maximum memory in bytes. `null` = no limit. |
| `TreatMissingAsEmpty` | `bool` | `true` | `true`, `false` | When `true`, querying a non-existent table returns empty results instead of an error. Useful for cache-style usage. |

**Integration tests that need Application Auth** (OIDC discovery, JWT validation, real signup/signin against the HTTP API) cannot use embedded mode alone, because Application Auth requires the Aouda HTTP server. For those tests, use the **`Aouda.Testing`** package to start an in-process server from `dotnet test` — see [Getting-Started-Testing.md](testing.md).

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

> **Internal/source workflows:** If you are developing Aouda itself (running from `src/`, local tool packaging, IDE task wiring, AppHost setup), use [Aouda-Developer.md](https://github.com/aoudadb/aouda/blob/main/docs/dev/Aouda-Developer.md). This user guide intentionally stays product-facing.

#### Option B: Configuration File (local development)

For local development, you may place an optional `appsettings.json` in the directory from which you run `aouda start`. **Release installs and Setup do not use this file** — they pass `--data-path` and `--port` on the service command line instead. See [Server configuration](../guides/server-configuration.md).

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5433,
    "Databases": {
      "myapp": {
        "Durability": "strict"
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
docker run -d --name aouda -m 2g --cpus 4 -p 127.0.0.1:5000:5000 -v aouda-data:/data \
  ghcr.io/aoudadb/aouda-server:<version>
```

The image is private: log in first with `docker login ghcr.io` (a token with `read:packages`). `-m` makes the server size its memory from the container's limit and `127.0.0.1:` keeps the admin API off the host's other interfaces ([Docker](../deployment/docker.md) says why).

- Server at `http://localhost:5000`
- Data persists in the `aouda-data` named volume across container restarts

Key environment variables:

| Variable | Default | Allowed values | Description |
|----------|---------|----------------|-------------|
| `AOUDA_DATA_PATH` | `/data` | Any valid filesystem path | Data directory inside the container |
| `AOUDA_BIND` | `0.0.0.0:5000` | Any valid `{address}:{port}` string (e.g. `0.0.0.0:5433`, `127.0.0.1:5000`) | Bind address |

For production with custom configuration, pass environment variables:

```bash
docker run -d --name aouda -m 2g --cpus 4 -p 127.0.0.1:5000:5000 \
  -v aouda-data:/data \
  -e AOUDA_DATA_PATH=/data \
  ghcr.io/aoudadb/aouda-server:<version>
```

#### Option E: Docker Compose — server + Studio

The `docker-compose.yml` in the Aouda repository starts the server and Studio together:

```bash
docker compose up
```

- **Aouda** at `http://localhost:5000`
- **Aouda Studio** at `http://localhost:3000`

The compose file takes one declaration: an operator in a declaration file, `aouda.json` next to the compose file with its volume line uncommented, and `AOUDA_DECLARATION=/etc/aouda/aouda.json` plus, for a first admin seeded from `{ "password": { "env": "AOUDA_ADMIN_PASSWORD" } }`, `AOUDA_ADMIN_PASSWORD=<something long>` in `.env` (**BL-1464, next train**; a key-only operator needs no human admin), or, for a throwaway, `AOUDA_DEV_ADMIN=true docker compose up` (**BL-1423, 0.12.0**; the line to read is the `AOUDA-DEV-ADMIN` line of `docker compose logs aouda`). With none, the server waits in setup mode and `/ready` answers `503 setup_required`. The old `AOUDA_SERVER_KEY`, `AOUDA_ROOT_EMAIL` and `AOUDA_ROOT_PASSWORD` are no longer passed. See [Docker](../deployment/docker.md#compose).

Studio connects to Aouda automatically. No additional configuration needed — open `http://localhost:3000` to browse your databases.

**For a real deployment**, declare the databases, keys, roles and schema files instead of creating them by hand, so that a wipe and a plain start bring them back: [Declare a deployment](../guides/declare-a-deployment.md) (**0.15.0**) is one complete working set with a compose file, `aouda plan` and `aouda reload`.

The compose file sets `stop_grace_period: 130s` on the server so Docker waits longer than the host's 120 s `Aouda:ShutdownTimeout`. If you copy the file, keep those two numbers paired — a shorter grace SIGKILLs the process before shutdown has finished. See [Server configuration §8](../guides/server-configuration.md#8-startup-shutdown-and-slow-opens).

For a 3-node cluster with replication and a witness node:

```bash
docker compose -f docker-compose.cluster.yml up
```

### Creating Databases via API

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

```bash
# Create a database
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $AOUDA_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "name": "myapp" }'

# Create a database with a durability level and memory limits
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $AOUDA_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "analytics",
    "durability": "strict",
    "maxMemoryShareBytes": 1073741824
  }'

# List databases
curl -H "Authorization: Bearer $AOUDA_SERVER_KEY" http://localhost:5433/api/databases

# Get database info
curl -H "Authorization: Bearer $AOUDA_SERVER_KEY" http://localhost:5433/api/databases/myapp

# Drop a database
curl -X DELETE -H "Authorization: Bearer $AOUDA_SERVER_KEY" http://localhost:5433/api/databases/myapp
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

**Data you already hold as columns** (**Lead S13, 0.6.0**) — read from Parquet or Arrow, a data frame, another database —
goes in as a `ColumnBatch`, without a dictionary per row. It is the fast path for inserts and bulk loads alike:

```csharp
using Aouda.Protocol.BulkLoad;

var batch = ColumnBatch.Of(
    ColumnBatchColumn.FromInt64s("id", new long[] { 3, 4 }),
    ColumnBatchColumn.FromStrings("name", new[] { "Sprocket", "Gizmo" }),
    ColumnBatchColumn.FromDecimals("price", new[] { 4.50m, 12.00m }, scale: 2));

var inserted = await client.GetTable("products").InsertAsync(batch);   // InsertResult: RowsInserted, GeneratedValues
await client.BulkLoadAsync("products", batches);                       // IAsyncEnumerable<ColumnBatch>, a list, or one batch
```

The full .NET client reference — options, inserts, column batches, bulk load, what is retried, errors — is
[.NET Client](../clients/dotnet.md).

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

##### A rejected key is not a retry (**BL-1386, 0.11.0**)

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

```csharp
AuthFailurePolicy = new AuthFailurePolicy
{
    FailFast = true,       // throw AoudaAuthenticationFatalException: stop, the credential is bad
    SustainedAfter = 3,    // consecutive failures with no success between them (default 3)
    OnSustained = info =>  // once per streak; carries no key
        alerts.Raise($"Aouda rejected our key: {info.ErrorCode} x{info.ConsecutiveFailures} since {info.FirstSeenAt:u}"),
}
```

`AoudaAuthenticationFatalException` is an `AoudaAuthenticationException` (an existing `catch` still sees it) with the original failure as `InnerException`. A batch writer (`CreateBatchWriter`) faults on one even when `ContinueOnError` is set, instead of dropping batch after batch; `BulkLoadAsync` surfaces it on `:begin`. A 403 `AUTHORIZATION_DENIED` (and `AUTH_PLS_*`, `AUTH_GRANT_*`) is not an authentication failure: the key is valid and a different table may be allowed. The streak counts HTTP requests through the client's transport; a realtime socket's own handshake is not counted, and an authentication failure does not count toward the circuit breaker. The client does not persist or re-send what it could not write: a caller that must not lose rows holds them until the key is fixed (a durable spool is a separate card, BL-1387, not built). An HTTP 403 now reports `StatusCode` 403 (it reported 400), and an authentication failure's `ErrorCode` carries the server's code (the client reads both of the server's error shapes), so `AUTH_KEY_ROUTE_MISMATCH` and the other 403 refusals match the policy.

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
    { name: "total", type: "Decimal", precision: 18, scale: 2 },
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
// One row per category: category, SUM_total, COUNT — keys ascending, nulls last
var byCategory = await engine.Table("orders")
    .Where(r => r.Col("status").Eq("completed"))
    .GroupBy("category")
    .Sum("total")
    .Count()
    .GroupAggregateAsync();

// No GroupBy: one AggregateResult over every matching row
var totals = await engine.Table("orders")
    .Where(r => r.Col("status").Eq("completed"))
    .Sum("total")
    .Count()
    .AggregateAsync();
```

A grouped query runs through `GroupAggregateAsync()`; `AggregateAsync()` refuses one, and `GroupBy` does not combine
with `Select` — the result is the keys and the aggregates (**ColumnarRead, 0.3.0**). A `SUM` over no value is
`null`, not `0` (**BL-757, 0.3.0**). Over HTTP, the same question is the query message's `aggregates` / `groupBy`
([HTTP API](../reference/http-api.md#aggregates-and-group-by)).

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

### How a C# property becomes a column type

`SchemaInferrer` maps each property through this table. It is the same map used by
`AutoCreateSchema` (create the table) and by `AutoReconcileSchema` (compare an existing table
against the model), so a mismatch here is what a reconcile failure is reporting.

| C# type | Column `type` |
|---|---|
| `bool` | `Bool` |
| `byte` | `Byte` |
| `short` / `int` / `long` | `Int16` / `Int32` / `Int64` |
| `ushort` / `uint` / `ulong` | `UInt16` / `UInt32` / `UInt64` |
| `float` / `double` | `Float32` / `Double` |
| `decimal` | `Decimal(p,s)` from the property's `[AoudaDecimal(p, s)]`, which it must carry (**LoadSpeed S13, 0.4.0**: a `decimal` property without it is refused, naming the property — see [`Decimal(p,s)`](../guides/schema.md#decimalps-a-decimal-stored-as-a-scaled-integer-columnarcore-s13-020)) |
| `string` | `String` |
| `DateTime` / `DateTimeOffset` | `Timestamp` |
| `DateOnly` | `Date` |
| `Guid` | `Guid` |
| `T?` (`Nullable<T>`) | the underlying `T`'s type, `nullable: true` |
| **`enum`** | **the type of its *underlying* integral type — `Int32` unless the enum declares otherwise** |

Anything else throws `NotSupportedException` at inference time, naming the type.

A `DateTime` of kind `Local` or `Utc` is written with its offset, and a `DateTime` of kind `Unspecified` (`new DateTime(2026, 3, 1)`) is
read as UTC; a `Timestamp` is the instant and a `Date` is the calendar day on the value, on every machine. See
[Timestamp — time zones](../reference/timestamp.md#which-instant-which-day-time-zones-bl-1225-090) (**BL-1225, 0.9.0**).

> **⚠️ An enum is `Int32` unless you say otherwise.**
>
> A C# enum declared the ordinary way —
>
> ```csharp
> public enum RoomType { Direct = 0, Group = 1, Public = 2 }
> ```
>
> — has an underlying type of `int`, so the model expects an **`Int32`** column. It does not
> matter that every value fits in a byte. If the schema file declares
>
> ```json
> "Type": { "type": "Byte" }
> ```
>
> then the column and the model disagree, and the first write through
> `AutoReconcileSchema` fails:
>
> ```
> AoudaSchemaException: Table 'Rooms': column 'Type' has type 'Byte' in the database
> but the model expects 'Int32'. Automatic type migration is not supported by
> AutoReconcileSchema.
> ```
>
> **This is not migrated automatically, and that is deliberate** — the two directions are not
> symmetric. Reading a `Byte` into an `Int32` is lossless; writing an `Int32` into a `Byte` is
> not, and a reconcile cannot know which way the data will travel. Widening a populated column
> rewrites it, which is a decision an operator makes, not a side effect of an application's first
> insert. Fix it at the declaration, one of two ways:
>
> - **Change the schema to match the model** — `"Type": { "type": "Int32" }`. Correct for a new
>   or empty table, and the default choice.
> - **Change the enum to match the schema** — `public enum RoomType : byte { … }`. Correct when
>   the `Byte` column already holds data you would rather not rewrite, and when the value range
>   genuinely is 0–255.
>
> If the column is already populated and you need it widened, do it explicitly through
> `ISchemaOperations.ApplyAsync` (a Tier-1 widening; see
> [Schema § changing a column type](../guides/schema.md#columndefinition-entry-in-columns)) and
> keep `AutoReconcileSchema = false` until that has run.
>
> The same trap applies to any property whose C# type you have not checked against the schema
> file. `bool IsPublic` is `Bool`, not `String`; `DateOnly` is `Date`, not `Timestamp`.

> **⚠️ A typed update writes values. It does not change the table's columns.** (**BL-1178, 0.9.0**)
>
> `UpdateAsync(new { name = "b" })` sets `name` and leaves every other column in place. It does not reconcile, whatever
> `ReconcilePolicy` is.
>
> `AutoReconcileSchema` still defaults to `true`. `ReconcilePolicy` defaults to `Safe`: before the first typed insert, the client
> adds the columns the class has and the table lacks, and it does not drop a column the class omits. (**BL-1178, 0.9.0**)
> `Unsafe` is opt-in. It drops non-key columns the class does not declare — a derived column such as `SearchText`, a
> server-stamped column, or a column left off the row type on purpose — and it never drops a primary-key column.
>
> If the table comes from `aouda.schema.json`, turn reconcile off:
>
> ```csharp
> var client = new AoudaClient(new AoudaClientOptions
> {
>     ServerUrl = "http://localhost:5433",
>     DatabaseName = "myapp",
>     AutoReconcileSchema = false, // the schema file owns these tables
> });
> ```
>
> From the 0.9.0 (**BL-1177**), the server refuses HTTP DDL on a table that schema apply created, in every `InferenceMode`.
> A default client is `Safe`, so that insert no longer tries to drop a column the class omits: the write succeeds and the column
> stays. (**BL-1178, 0.9.0**) An explicit `Unsafe` client still fails that drop with `AoudaSchemaException`, and the column
> survives. On 0.7.0 and earlier the default was `Unsafe`: in `On` (the default) or `Off`, the drop succeeded and the insert
> reported success. `Safe` is no fix for a class that has a property the table lacks: the add is refused too, and the write throws.
> Bulk load never reconciles.


### Seeding explicit IDs (identity-insert)

Sometimes you need to insert **client-chosen** values into an `autoIncrement` column (reserved ranges, reseed from another system, literal `0`) **without** flipping the column to manual via schema apply (BL-126). Use request-scoped **identity-insert**:

| Mode | When to use |
|------|-------------|
| Normal insert (`identityInsert` omitted/`false`) | Everyday writes. `0` or **omitting** the column means “please generate” (`generatedValues` returns the allocated id; BL-429). An explicit non-zero id is stored, and the counter moves past it so a later generated id cannot repeat it (**ColumnarMerge S02, 0.2.0**) — whether sent as an integer, a numeric string or an integral number such as `5.0` (**BL-703, 0.2.0**). |
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
  "columns": ["id", "status"],
  "data": [[1000], ["seeded"]]
}
```

Over HTTP the rows are column arrays: `columns`, and `data` with one array per column (**Lead S12, 0.6.0**: a `rows` array of
objects is refused `400 ROW_OBJECTS_UNSUPPORTED`; see [the write body](../reference/http-api.md#column-arrays-the-write-body)).
The SDK calls above still take rows.

Rules of thumb:
- Prefer identity-insert over temporarily disabling `autoIncrement` for one-shot seeds.
- Prefer [bulk-load identity-insert](../guides/bulk-load.md) when the seed is large enough for the P20 protocol.
- Studio does not expose an identity-insert UI — use the API/SDK (BL-130/131 Non-Scope).

### Explicit Schema Definition

For production use, you often want explicit control over data types, primary keys, partition keys, and auto-increment:

```csharp
// The same request in the .NET client (client.Schema) and the embedded engine (db.Schema)
await client.Schema.CreateTableAsync(new CreateTableRequest
{
    Name = "orders",
    Columns =
    [
        new() { Name = "order_id", Type = "Int64", PrimaryKeyOrder = 1, IsAutoIncrement = true },
        new() { Name = "tenant_id", Type = "String", PartitionKeyOrder = 1 },
        new() { Name = "customer", Type = "String" },
        new() { Name = "amount", Type = "Decimal", Precision = 18, Scale = 2 },   // Decimal(18,2)
        new() { Name = "status", Type = "String" },
        new() { Name = "created_at", Type = "Timestamp" },
    ],
});
```

(**BL-035, 0.9.0**) A column can also hold a whole array per row — `Double[]`, `Float32[]`, `Int32[]`, `Int64[]`, `Byte[]` or
`String[]` — see [Array columns](../guides/array-columns.md). The embedded engine does not take them yet.

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
        { "name": "amount", "type": "Decimal", "precision": 18, "scale": 2 },
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

For complete Application Auth documentation, see [Getting-Started-Auth.md](auth.md).

---

## 8. Server Authentication — Securing Database Access

> **This section is about controlling who can connect to the Aouda server and access databases.** This is the equivalent of SQL Server authentication, PostgreSQL roles, or MongoDB SCRAM. It has nothing to do with authenticating your application's end users — that is a separate feature called the [Application Auth Service](auth.md).

### The Server Auth Hierarchy

Server authentication follows the same pattern as traditional databases: a server-level identity layer where credentials are scoped to specific databases.

```
Aouda Server Instance
├── Server Admin (superuser)
│   ├─ Access: ALL databases, ALL operations
│   └─ Analogy: PostgreSQL's `postgres`, SQL Server's `sa`
│
├── Server Users (database-scoped)
a principal, its statements, and an aouda_ key or a session (GET /api/auth/whoami)
│   └─ Analogy: PostgreSQL roles with per-database GRANT
│
├── Server API Keys (database-scoped)
a principal, its statements, and an aouda_ key or a session (GET /api/auth/whoami)
│   └─ Analogy: Service accounts / connection strings
│
├── Database: "myapp"     ← server users/keys need db_* role to access
├── Database: "analytics"  ← separate role grants
└── Database: "cache"      ← no linked auth database: open before setup;
                               after it, server credentials on the admin listener (BL-1017)
```

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
5. The server validates the token and checks whether the user has the required role for the target database.

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Default roles (applied per database):

| Role | Permissions |
|------|------------|
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Auth state is stored in an internal database called `_serverauth`. This database is managed by Aouda and is not directly accessible as a user database.

### Step 1: Bootstrap the First Admin

When the server starts with no admin accounts **and nothing declared**, it enters **setup mode**. In setup mode, only the bootstrap endpoint is available, and only from localhost.

(**BL-1462, 0.14.0**) Setup mode exists only for a data directory that has **never been set up** (no server auth database)
and nothing is declared. Once set up, a server never re-enters it: an operator it already has (an admin, or a principal holding
`admin` with an active key) operates it, and with nobody who can manage the server and nothing declared the start is refused
(`SERVER_HAS_NO_OPERATOR`, naming the ways out). (**BL-1464, next train**) An operator declared in the declaration file's
`server.principals` means no setup mode: a key-only operator (the role `admin` and a `derivedKey` or stored key) operates the
server from the first start, with no human admin, and a first admin named by an email with a password seed is created at start
(Option B below). Setup mode is the interactive first run for a server that declares neither. The old `Aouda:Auth:Bootstrap:*`,
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
`aouda-admin-password`, are refused at start (`SETTING_REMOVED`, exit status `78`).

Every other request gets `503 SETUP_REQUIRED` with **no `Retry-After`**: setup mode ends when you create the first admin, not after a wait. While the server is still starting (before setup mode or normal service), requests get `503 SERVER_STARTING`, which (**BL-944, 0.4.0**) carries `Retry-After: 5`. The health probes answer in setup mode too: `/health` and `/startup` are `200`, `/ready` is `503` with `setup_required` (**BL-1462, 0.14.0**; see [the probes](../reference/http-api.md#the-probes-one-meaning-each)).

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

The three flags follow setup mode alone (**BL-1462, 0.14.0**): a server with a declared key-only operator and no user answers
`"setupMode": false`, `"serverAuthConfigured": true`, `"adminBootstrapRequired": false`. Before, "no user" alone made it answer
`setupMode: true` and point at `POST /api/auth/setup`, which that server refuses with `403 ALREADY_CONFIGURED`.

For server setup, prefer the retryable initializer:

```bash
printf '%s' "ChangeMeNow!" | aouda init \
  --admin-email admin@example.com \
  --admin-password-stdin \
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

#### Option B: Declare the first admin (**BL-1464, next train**)

Declare the admin in the declaration file, `aouda.json`: a `server.principals` entry named by the email, holding the role `admin`,
with a password seed read from a file or an environment variable (or `{ "hash": ... }`), never written into the file:

```json
{ "version": 1, "server": { "principals": { "admin@example.com": { "roles": ["admin"],
    "credentials": { "password": { "env": "AOUDA_ADMIN_PASSWORD" } } } } } }
```

and name the file at start: `aouda start --declaration ./aouda.json` (or `Aouda__Declaration`; there is no default path). The server
creates the admin when the principal is created, with a forced password change at the first sign-in; the seed is never applied
again, so a later change of the variable changes nothing. See [Declared access](../guides/declared-access.md).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
(`SETTING_REMOVED`, exit status `78`), naming this declaration as its replacement; an empty value counts as not set.

#### Option C: Local Bootstrap Command

```bash
# an aouda_ key or a session. GET /api/auth/whoami names the principal.
  --email admin@example.com \
  --password-stdin \
  --data ./data
```

This creates the admin directly in the data directory without starting the server. ⚠️ **Only with the server stopped**
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
(`POST /api/auth/setup` from the server's host, or stop the server). Before, it wrote behind the running server's back and the
server stayed in setup mode until a restart. For binary-only or air-gapped installs, the native server artifact also supports the same local bootstrap operation:

```bash
# an aouda_ key or a session. GET /api/auth/whoami names the principal.
  --email admin@example.com \
  --password-stdin \
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
  -d '{ "database": "myapp", "table": "orders", "limit": 10 }'
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
| `/api/auth/signout` | POST | Yes | End this session (`scope`: `others`, `global` for more) |
| `/api/auth/whoami` | GET | A credential, or `anonymous` on the data plane | Who this credential is and what it may do |
| `/api/databases/{db}/auth/me` | PATCH | Yes | Update the signed-in profile. `GET …/auth/me` is not a route |
| `/api/auth/password` | PUT | Yes | Change password |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

### SDK usage

One credential: a key or a session. [Client integration](../auth/client-integration.md).

#### .NET Client

```csharp
using Aouda.Client;

var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5000",
    DatabaseName = "myapp",
    Credential = AoudaCredential.Key(key),
});

var who = await client.WhoAmIAsync();
var rows = await client.GetTable("orders").Limit(10).ToListAsync();
```

#### TypeScript Client

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "myapp",
  apiKey: key,
});

const who = await client.whoami();
const rows = await client.table("orders").limit(10).execute();
```

`apiKey` or `session`, never both.

### A key for a service

A service is a principal with a key (`aouda_<id>_<secret>`). Mint a stored key on that principal. The body is `{ "name"?, "expiresAt"? }`. The answer shows the key once. A declared principal uses `aouda keys derive` instead, and the key is the same after a wipe. What the key may do is the principal's statements. `GET /api/auth/whoami` says which principal the caller is.

```bash
curl -s -X POST http://localhost:5000/api/auth/_serverauth/principals/ops/keys \
  -H "Authorization: Bearer $AOUDA_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "name": "orders-api" }'
```

```json
{ "key": "aouda_<id>_<secret>", "id": "aouda_<id>", "principal": "ops", "name": "orders-api" }
```

### Common Auth Error Codes

| Code | HTTP | Meaning |
|---|---|---|
| `AUTH_CREDENTIAL_MISSING` | 401 | No credential on the admin listener. Remedy `sign-in` |
| `AUTH_KEY_MALFORMED` | 401 | Bad shape or checksum, or a retired `mk_` key. Remedy `fix-key` |
| `AUTH_CREDENTIAL_INVALID` | 401 | Unknown id, wrong secret, or a bad session. Remedy `fix-key` |
| `AUTH_CREDENTIAL_EXPIRED` | 401 | The key or session has expired. Remedy `renew` |
| `AUTH_CREDENTIAL_REVOKED` | 401 | Revoked, or the principal is disabled. Remedy `none` |
| `AUTH_POLICY_DENIED` | 403 | The statements do not allow it. Remedy `grant` |
| `AUTH_ACCOUNT_DISABLED` | 423 | A refresh of a disabled principal |

The list, including `remedy`, is [whoami and remedy](../auth/whoami.md). `AUTH_TOKEN_MISSING`, `AUTH_TOKEN_INVALID`, `AUTH_TOKEN_EXPIRED`, `AUTH_TOKEN_REVOKED`, `AUTHORIZATION_DENIED` and `INSUFFICIENT_PERMISSIONS` are not produced.

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

While the server has no server auth database (before `/api/auth/setup`), clients can access this database without any credentials:

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

**Who may reach a database without auth (**BL-1017, 0.4.0**).** A database with no linked auth database is open only while
the server has no server auth database — a fresh server before [server authentication](#8-server-authentication--securing-database-access) is set up. Once the server admin exists (`/api/auth/setup`,
or a configured root user), every request to such a database on the **admin listener** needs server credentials, exactly as
`/api/databases` itself does: reads, writes, DDL, `DELETE /api/databases/{db}`, quarantine, `inspect`, WebSocket and long-poll. A
An operator's key (a principal with `manage` on `server`) is the credential. Any other credential
gets `401` or `403`, and so does a request naming a database that does not exist. An application's own keys and tokens are not server
credentials. On the **data-plane** listener nothing changes: such a database stays open to the routes that listener serves
(named queries and mutations, WebSocket, long-poll). In 0.3.0 and earlier the admin listener served it to anyone, drop included.

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

**Security for no-auth databases:** Use network-level security (firewalls, VPNs, Kubernetes network policies) to control who can reach the server. Before setup, a no-auth database is open to anyone who can connect to the port; after it, to anyone who can connect to the data-plane port, through the named artifacts that listener serves.

---

## 10. Managing Multiple Databases

A single Aouda server can host many databases. Each database is independent — separate storage, separate schema, separate auth configuration.

```bash
# Create databases for different purposes
curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -d '{ "name": "app_production", "durability": "strict" }'

curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -d '{ "name": "app_staging", "durability": "strict" }'

curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -d '{ "name": "cache", "durability": "unlogged" }'

# List all databases
curl http://localhost:5433/api/databases
```

Or declare them in an optional `appsettings.json` for local dev (API-created databases are the usual path in production):

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Databases": {
      "production": { "Durability": "strict" },
      "staging": { "Durability": "strict" },
      "cache": { "Durability": "unlogged" }
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

When `MaxHotBytes` and `MaxPageCacheBytes` are 0, the engine derives them from the governed budget: 45% for the hot tier (floor 32 MB) and 10% for the page cache (floor 8 MB). The page cache is on (**ColumnarRead, 0.3.0**; it was off in `Constrained`, the resource mode a database started in — the modes are deleted, **WorkloadCore S17, 0.3.0**); `Aouda:Memory:PageCacheEnabled = false` turns it off. See [Defaults reference](../guides/defaults-reference.md).

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

- **[Backup and Restore](backup.md)** — Incremental backups to local filesystem or S3 (including S3-compatible services such as MinIO and LocalStack). REST and TypeScript client APIs for exact restore and point-in-time recovery. Retention and GC.

### Authentication & Authorization

- **[Application Auth Service](auth.md)** — Use Aouda as an authentication provider for your app's end users (signup, signin, JWTs, Partition-Level Security, multi-tenancy). Covers the two-layer auth model, architecture patterns A-D, API keys, and AI agent workflows.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

### General

- **[.NET Client](../clients/dotnet.md)** — `Aouda.Client`: connecting, queries, inserts, column batches, bulk load, retries and errors.
- **[Testing with Aouda.Testing](testing.md)** — In-process integration tests, including Application Auth, xUnit/NUnit/MSTest fixtures, and CI-friendly `dotnet test` workflows.
- **[Architecture](https://github.com/aoudadb/aouda/blob/main/docs/ARCHITECTURE.md)** — Deep dive into Aouda's technical design.
- **[ADR Index](https://github.com/aoudadb/aouda/tree/main/docs/decisions)** — All architecture decision records.
- **[HTTP API](../reference/http-api.md)** — Wire contract, including authentication headers and error codes.
- **[Aouda Studio](https://github.com/aouda/aouda-studio)** — Web management console.

---

## 15. Contributor / Internal Developer Workflows

Internal contributor workflows (running Aouda from source, local `.nupkg` tool distribution, IDE task wiring, AppHost orchestration, and source-build setup) are documented in [Aouda-Developer.md](https://github.com/aoudadb/aouda/blob/main/docs/dev/Aouda-Developer.md).

This guide intentionally stays focused on Aouda users and production-facing usage.

---

## 16. Native Production Hosting (Windows + Linux)

Aouda runs from **one binary**. `aouda` and `Aouda.Server` are two names for the same executable —
there is no separate CLI to install, and no second thing to keep in step. What changes between
deployments is only which supervisor owns the process.

> **Deploying, rather than learning?** The per-platform guides carry the whole procedure, and they
> are the pages kept current:
>
> - [Linux (systemd)](../deployment/linux.md)
> - [Windows Service](../deployment/windows.md)
> - [Docker](../deployment/docker.md)
> - [Kubernetes and Helm](../deployment/kubernetes.md)
>
> This section covers what those pages have in common: the artefact, the prerequisite, and the auth
> bootstrap.

### 16.1 The three ways to run it

| Mode | Command | Best for |
|---|---|---|
| **Development** | `aouda start --data-path ./data --port 5433` | Demos, quick testing, local AI-agent workflows |
| **Production service** | `aouda service install`, then systemd or the Windows SCM owns it | VMs, bare metal, on-premise |
| **Container** | `docker run … ghcr.io/aoudadb/aouda-server` | Containerised environments, Kubernetes |

The engine and the auth model are identical in all three. What changes is who keeps the process
alive.

⚠️ **`start` is explicit.** `aouda --port 5433` is an error, not a shortcut — a CLI that binds a port
and creates a `./data` directory when you fumble a flag is a bad CLI. This matters most in a service
registration, where a missing subcommand installs cleanly and then fails to start.

### 16.2 The artefact, and the one prerequisite

⚠️ **Aouda ships framework-dependent.** The binaries do not bundle a .NET runtime, so **the .NET 10
ASP.NET Core runtime must be installed on the target machine** before anything can start. There is
no self-contained artefact. (**BL-739, 0.2.0**: server 0.1.40 and earlier need the .NET 8 runtime instead.)

This is not a footnote. Without the runtime, the process fails in the .NET host loader — *before a
single line of Aouda code runs* — so there is no Aouda error message at all, and there cannot be.
The install scripts check for it first and print what to run; `aouda doctor` reports the runtime's
**version**, because by the time it can run, the runtime is present by definition.

```bash
sudo apt-get install -y aspnetcore-runtime-10.0          # Debian / Ubuntu
dotnet --list-runtimes | grep Microsoft.AspNetCore.App  # verify
```

**Platforms:** `linux-x64`, `linux-arm64`, `win-x64`, `win-arm64`.

⚠️ **The artefacts are private.** They are published to the private GitHub Releases of
`aoudadb/aouda`, and the container image to `ghcr.io/aoudadb/aouda-server`. There is no public
download, no `curl | sh`, and no anonymous `docker pull` — every one needs a token with access to
that organisation. See each platform page for the exact command.

### 16.3 Directory layout

Keep **data** outside the binary folder, so an upgrade that replaces binaries cannot touch it.

| | Windows | Linux |
|---|---|---|
| Binaries | `C:\Program Files\Aouda\` | `/opt/aouda/` |
| Data | `C:\ProgramData\Aouda\data\` | `/var/lib/aouda/` |
| Logs | console → the SCM | console → `journalctl` |
| Bootstrap | the service command line: `start --data-path … --port … --bind …` | the same, in systemd `ExecStart` |

⚠️ **`--data-path`, not `--contentRoot`.** `--contentRoot` is an ASP.NET Core switch that sets where
the host looks for content files; **it does not set Aouda's data directory**. A server started with
it stores its databases wherever the process happened to be launched from. If you have a service
registration carrying `--contentRoot`, that is what it is doing.

`aouda service install` writes the command line for you, which is the reliable way to get this
right. See [Server configuration](../guides/server-configuration.md) for full precedence.

### 16.4 Bootstrapping the first admin

⚠️ **Aouda does not accept a password on the command line.** On Linux a command line is
world-readable at `/proc/<pid>/cmdline` for the life of the process, and on every platform it is
kept by shell history, by process-launch audit rules, by CI logs and by an agent's transcript. None
of that can be un-leaked, which is why the option was removed rather than deprecated — a deprecation
warning is printed *after* the leak has already happened.

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
remedy (`POST /api/auth/setup` from the server's host, or stop the server) (**BL-1462, 0.14.0**). A service that declares a
key-only operator in its declaration file needs no admin at all (**BL-1464, next train**).

**Three supported paths.**

*A file, readable only by its owner:*

```bash
sudo install -m 600 /dev/null /etc/aouda/admin-password
sudo sh -c 'printf "%s" "$PASSWORD" > /etc/aouda/admin-password'

# an aouda_ key or a session. GET /api/auth/whoami names the principal.
  --password-file /etc/aouda/admin-password --data /var/lib/aouda
```

⚠️ A file readable beyond its owner is **refused** — on Linux/macOS, by mode (naming the mode it
found and the `chmod 600` to fix it); on Windows, by DACL (naming `icacls` if `Everyone`,
`Authenticated Users`, or `BUILTIN\Users` can read it, including by inheritance from the directory).

*Standard input, which touches no filesystem — the right answer in a pipeline or for an agent:*

```bash
# an aouda_ key or a session. GET /api/auth/whoami names the principal.
  --email admin@example.com --password-stdin --data /var/lib/aouda
```

⚠️ `printf`, not `echo`: `echo` appends a newline. Aouda strips exactly one trailing newline and no
other whitespace, so both work — but a password that silently gains a character is a failure nobody
diagnoses from the symptom.

*A declared first admin, which is the right answer for a service — the server creates the first
admin itself on its first start* (**BL-1464, next train**). In the declaration file:

```json
{ "version": 1, "server": { "principals": { "admin@example.com": { "roles": ["admin"],
    "credentials": { "password": { "file": "/etc/aouda/admin-password" } } } } } }
```

and start the server with `--declaration <path>` (for the unit, `Environment=Aouda__Declaration=<path>`). The seed is applied only
when the principal is created, with a forced password change at the first sign-in, and never again. `aouda service install
--admin-password-credential` / `--admin-email` are removed (a usage error, exit `64`), and a unit that still loads the
`aouda-admin-password` credential refuses to start (`SETTING_REMOVED`): remove its `LoadCredential=` line. See
[Linux](../deployment/linux.md#the-first-admin).

*Or, first run only, over loopback:*

```bash
curl -X POST http://localhost:5433/api/auth/setup \
  -H "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{"email": "admin@example.com", "password": "REPLACE-ME"}
JSON
```

### 16.5 A key for an application

Mint a stored key on the operator's principal, or derive one (`aouda keys derive`) for a principal the declaration owns. The key is shown once.

```bash
curl -s -X POST http://localhost:5000/api/auth/_serverauth/principals/ops/keys \
  -H "Authorization: Bearer $AOUDA_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "name": "orders-api" }'
```

Store the returned key in a secret manager immediately. Do not keep it in source control or in a plaintext install script.

### 16.6 Installing the service

One command, on either platform:

```bash
sudo aouda service install                 # Linux: writes and starts a systemd unit
```

```powershell
aouda service install                      # Windows, elevated: registers with the SCM
```

It writes a unit (or a service registration) carrying the resource limits and hardening that a
production server needs, starts it, and prints what it did. `--dry-run` shows the exact output
without changing anything.

⚠️ **It is not a thin wrapper over a hand-written unit file.** The generated systemd unit sets
`Type=notify` so `systemctl start` waits for WAL recovery instead of returning while the node is
still replaying; `MemoryMax`, which decides whether Aouda sizes its budget from a real grant or a
guess; `LimitNOFILE`, because Aouda stores a file per column; and a hardening block.
[The Linux page](../deployment/linux.md#the-unit-file) shows the file and explains each line.

Day-to-day:

```bash
aouda service status | start | stop | uninstall
aouda status        # running? ready? where? which version? what budget?
aouda doctor        # what is misconfigured on this machine
```

Both `status` and `doctor` take `--output json`, which every command accepts; commands with
structured output then print one JSON document. `status` finds an installed service from its
registration, so it needs no arguments for a default install. Exit codes are listed in
[Linux deployment](../deployment/linux.md#exit-codes) and are the same on every platform.

### 16.7 Scripted installs

The install scripts remain the entry point for CI/CD and scripted deployment, and they now do
exactly one thing the binary cannot: check for the .NET 10 runtime before running a binary that needs
it. Everything else they delegate.

```powershell
.\scripts\install-aouda.ps1 -ArtifactDir .\win-x64 --port 5433
```

```bash
sudo ./scripts/install-aouda.sh --artifact-dir ./linux-x64 --port 5433
```

Any option a script does not recognise is passed through to `aouda service install`.

⚠️ **They take no password and print no key.** Bootstrap auth separately, with one of §16.4's paths.

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
