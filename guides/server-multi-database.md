---
title: "Server and Multi-Database"
nav_order: 20
parent: "Guides"
---

# Aouda Functionality: Server Process and Multi-Database Lifecycle

Document status: Complete  
Primary owner: Engineering  
Last updated: 2026-08-13

Coverage phases: P4 (Server & Clients), P6, P7, P16  
Primary task folders: `docs/tasks/P4-Server-And-Clients-COMPLETION.md`, `docs/tasks/P6-COMPLETION.md`, `docs/tasks/P7-COMPLETION.md`, `docs/tasks/P16-COMPLETION.md`  
Primary ADRs: `docs/decisions/0006-target-scope.md`, `docs/decisions/0026-aouda-cloud-and-hub-architecture.md`  
Related functionality docs: `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Partitioning-And-Multitenancy.md`, `docs/dev/Functionality-Replication-And-Clustering.md`, `docs/dev/Functionality-Cloud-And-Hub.md`, `docs/dev/Functionality-Storage-And-Persistence.md`, `docs/dev/Functionality-Write-Path-Durability.md`

---

## Start Here

If your question is "How do I start the server and manage databases?", start with:
- §2.3 Defaults and zero-config behavior
- §2.12 Scenario playbooks

If your question is "What is implemented vs missing?", jump to:
- §2.4 Availability status
- §2.6 Capability coverage matrix
- §2.11 API and CLI coverage matrix

If your question is "How does the server route requests across databases?", go to:
- §2.7 Core concepts and mental model
- §2.8.1 Critical path walk-throughs

If your question is "What endpoints exist for operators?", go to:
- §2.11 API coverage matrix
- §2.13 Operations and observability

---

## 2.1 Why This Functionality Exists

**User problem:** Developers need a way to run Aouda as a standalone, externally-accessible server process and to host multiple isolated datasets (databases) within a single process. Without this layer, Aouda is only usable as an embedded library.

**Operational outcomes this provides:**
- A single server binary that operators start, stop, configure, and monitor.
- Strict per-database isolation: each database has its own catalog, WAL, tables, materialized query directory, and memory budget.
- A single HTTP surface that data-plane clients, management tooling, Studio, and AI agents can all address uniformly.
- Observability surfaces (memory, metrics, health) per database and at the server level.
- Deterministic lifecycle (create / active / dropping / dropped) for database provisioning and decommissioning.

**Scope boundaries (what this document does NOT cover):**
- Replication wire protocol details and write-concern semantics → `Functionality-Replication-And-Clustering.md`.
- Memory budget internals and hot/cold demotion ladder → `Functionality-HotCold-And-Memory.md`.
- On-disk storage layout and segment format → `Functionality-Storage-And-Persistence.md`.
- Cloud, Hub, Kubernetes, and Docker packaging → `Functionality-Cloud-And-Hub.md`.
- Studio and TypeScript client → `Functionality-Studio.md`, `Functionality-TypeScript-Client.md`.

---

## 2.2 Discovery and Navigation Map

| If you need to know… | Go to section |
|---|---|
| What server configuration knobs exist | §2.10 Configuration reference |
| How to start / stop the server | §2.12 Scenario 1 (first-run) |
| How to create and list databases | §2.11 API coverage matrix, §2.12 Scenario 2 |
| Which routes are scoped by database vs server-wide | §2.7 Core concepts, §2.8.1 Critical path |
| How `POST /api/server/shutdown` works | §2.8.1 Critical path walk-through #3 |
| Observability endpoints and metrics | §2.13 Operations and observability |
| Health endpoints for Kubernetes probes | §2.13 Operations and observability |
| What changed between P4 flat routes and P6 database-scoped routes | §2.5 Phase coverage matrix, §2.7 Core concepts |
| Known gaps and missing .NET client operations | §2.18 Known gaps |

**Role-based map:**

| Role | Primary sections |
|---|---|
| App developer | §2.3, §2.11 (.NET / TypeScript examples), §2.12 |
| Operator / DevOps | §2.10, §2.12 Scenario 1 & 3, §2.13, §2.14 |
| SDK maintainer | §2.7, §2.8, §2.11 (API matrix + missing API) |
| Engine contributor | §2.8, §2.8.1, §2.16 (test coverage map) |

**Source map:**

| Source | Contents |
|---|---|
| `docs/tasks/P4-Server-And-Clients-COMPLETION.md` | HTTP server, wire protocol, C# client, metrics, health, structured logging, tracing |
| `docs/tasks/P6-COMPLETION.md` | Multi-database registry, `DatabaseManager`, scoped routes, memory governance, per-db metrics |
| `docs/tasks/P7-COMPLETION.md` | Graceful shutdown API (`BL-028`), count endpoint |
| `docs/tasks/P16-COMPLETION.md` SA6 / A.* | Unified CLI (`aouda start/stop/databases`), admin API expansion, witness, Helm |
| `docs/decisions/0006-target-scope.md` | Managed-service and thin-client scope decision |
| `docs/decisions/0026-aouda-cloud-and-hub-architecture.md` | Hub architecture, single-binary philosophy |
| `src/Aouda.Server/` | All server-side implementation |
| `src/Aouda.Engine.Api/DatabaseManager.cs` | Multi-engine orchestrator |
| `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs` | Per-database memory coordination |
| `src/Aouda.Engine.Storage/Registry/` | `DatabaseRegistry`, `DatabaseRegistryStore`, `DatabaseState`, `DatabaseOptions` |
| `src/Aouda.Client/Databases/AoudaDatabasesApi.cs` | .NET client database API |

---

## 2.3 Defaults and Zero-Config Behavior

Starting `aouda start` (or `Aouda.Server.exe start`) with no arguments produces:

| Setting / behavior | Default | Practical impact |
|---|---|---|
| Listen port | `5000` | HTTP/1.1 + HTTP/2 on `localhost:5000` |
| Data directory | `./data` | Created if absent |
| Database registry | `./data/Server/databases.json` | Empty on first run; no databases created automatically |
| Database layout | `./data/Databases/{name}/…` | Per-db subtree created on first `POST /api/databases` |
| Memory ceiling | ~70% of detected RAM | One process RSS ceiling, shared as **weighted shares** across databases |
| Hot segment budget | Auto (70% of ceiling) | Allocated from total RAM |
| Page cache budget | Auto (20% of ceiling) | Allocated from total RAM |
| Request timeout | `30 000 ms` | Returns HTTP 504 on breach |
| Max concurrent requests | `50` | Returns HTTP 503 when exceeded; queue up to 100 |
| HTTP/2 | `true` | Kestrel serves HTTP/1.1 and HTTP/2 simultaneously |
| Tracing | `false` | OpenTelemetry disabled until opt-in |
| Structured (JSON) logging | `false` | Simple console formatter; enable via `Logging:Console:FormatterName: json` |
| Health startup delay | `10 s` | `/ready` suppresses failures during startup window |
| Database WAL | `true` per-db | WAL-backed durability by default |
| Replication mode | `Replicate` per-db | Tables replicated to secondaries by default |
| Write concern | `One` per-db | Acknowledged by primary WAL only |
| Write concern timeout | `5 000 ms` | Applies when `majority` or `all` is requested |
| Write concern timeout behavior | `DegradeAndLog` | Logs a warning and degrades to `One`; does not fail the write |

---

## 2.4 Availability Status

### Available now

- **HTTP server process** — ASP.NET Core (`Aouda.Server`), Kestrel, HTTP/1.1 + HTTP/2.
- **Single-engine mode (pre-P6)** — Single database, flat `/api/*` routes.
- **Multi-database mode (P6)** — One `AoudaEngine` per database, `DatabaseManager`, `databases.json` registry, `/api/databases/{db}/…` routing.
- **Database CRUD** — `POST/GET/DELETE /api/databases` and `GET /api/databases/{db}`.
- **Database-scoped data API** — Query, insert, schema, materialized queries, streaming, branches all under `/api/databases/{db}/…`.
- **Server-level observability** — `/api/server/memory`, `/api/server/metrics`, `/api/server/databases/{db}/metrics`, `/api/admin/metrics`, `/health`, `/ready`, `/health/detailed`.
- **Graceful shutdown** — `POST /api/server/shutdown` (loopback-only).
- **Row count** — `POST /api/databases/{db}/query/count`.
- **Connection lifecycle middleware** — request timeout (504), concurrency limit (503), correlation ID propagation, request logging.
- **AOUDA_\* environment variable configuration** — Full config surface via env vars and CLI args.
- **Structured JSON logging** — opt-in via `Logging:Console:FormatterName: json`.
- **OpenTelemetry tracing** — opt-in; OTLP export configured in `Aouda:Tracing`.
- **Per-database memory governance** — `ServerMemoryBudgetManager` with per-engine budget tracking.
- **Per-database health checks** — `DatabaseHealthCheck` included in `/health/detailed`.
- **Unified CLI** — `aouda start`, `aouda stop`, `aouda databases list|get|create|drop`, `aouda version`.
- **`Aouda.Server.exe` split** — `Aouda.Server.exe start` and `create-admin` only; all operator workflows via `aouda`.
- **First-run bootstrap** — `GET /api/auth/setup/status`, `aouda init`.

### Planned / Proposed

- **TypeScript client `client.Databases.get(name)` and `drop(name)`** — HTTP `GET /api/databases/{db}` and `DELETE /api/databases/{db}` exist on the server; the TypeScript client wraps are tracked as a follow-on item.
- **`client.Databases.DropAsync()` in .NET client** — `AoudaDatabasesApi` currently exposes only `ListAsync` and `CreateAsync`; `GET /api/databases/{db}` and `DELETE /api/databases/{db}` are server-implemented but not wrapped. Backlog item.
- **Per-database Prometheus scrape** — Current metrics API emits JSON; Prometheus format is explicitly deferred.
- **`ActiveConnections` counter in `MetricsSummary`** — Returns 0; HTTP connection tracking wiring is not yet complete.
- **Historical per-database metrics series** — Point-in-time snapshots only; no time-series store for per-db metrics.

### Reserved / Not Yet Wired

- **`aouda dev` command** — ADR 0026 lists `aouda dev` as an ephemeral-server mode. P16 SA6 shipped `aouda start` as the unified entry point; `aouda dev` behavior is not evidenced in source materials as a distinct command. See §2.18.

---

## 2.5 Phase Coverage Matrix

| Phase | Tasks / Reports | Delivered capability | Undone / deferred | Backlog |
|---|---|---|---|---|
| **P4** (Server & Clients) | Epics A, B, C; Command Surface Separation; First-Run Init | HTTP server process; REST query + schema + insert APIs; connection lifecycle middleware; `AOUDA_*` config; wire protocol (`Aouda.Protocol`); C# thin client (`Aouda.Abstractions`); connection resilience; metrics REST API; structured logging; OpenTelemetry tracing; health endpoints; `Aouda.Server.exe create-admin`; `aouda init` | `MemoryBudgetManager` not wired to storage (BL-001); `ActiveConnections` counter returns 0; `MetricsCollector.RecordQueryLatency()` not called; Prometheus export deferred | BL-001 (resolved P6), BL-002 (ORDER BY — resolved P5) |
| **P6** (Multi-Database) | Epics A–F | Multi-database registry (`databases.json`); `DatabaseManager`; database-scoped routes (`/api/databases/{db}/…`); database CRUD; wire protocol v2 (required `database` field); .NET client `AoudaClient(url, dbName)`, `client.Databases.List/Create`; per-database memory governance (`ServerMemoryBudgetManager`); per-database metrics (`DatabaseMetricsTracker`); per-database health check; `GET /api/server/memory`, `/api/server/metrics`, `/api/server/databases/{db}/metrics`; replication v2/v3; write concern | TypeScript multi-database client (Epic C.3) not evidenced in this repo; Studio DB navigation (Epic D) not evidenced; per-database Prometheus deferred; dynamic table-subscription reconfig requires reconnect | BL-001 resolved; per-db Prometheus deferred |
| **P7** (Production Scenarios) | T6 (durability), T10 (harness reports), bug-fix session | `POST /api/server/shutdown` (loopback-only, BL-028); `POST /api/databases/{db}/query/count`; `RemoteTableQuery.CountAsync`; harness scenario M.1–M.8 multi-database validation | BL-028 formal resolution carried into P14 write-path improvements | BL-028 resolved here; BL-023, BL-024 partially open |
| **P16** (Cloud & Hub), SA6 | A.1–A.11, SA6, ENG1 | Unified CLI: `aouda start/stop/databases`; `ServerHostRunner`; admin API expansion under `/admin/*` (cluster, backup, config, node, capabilities); `cluster-state.json` + `backup-config.json` runtime persistence; CORS defaults for Hub; `Aouda:Bind`, `Aouda:Join`, `Aouda:Role` config keys | `aouda dev` not evidenced as distinct command vs `aouda start`; Hub/Studio/TypeScript implementations in sibling repos | BL-042, BL-043 (OAuth) deferred |

---

## 2.6 Capability Coverage Matrix

| Capability | Impl. | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| HTTP server process (Kestrel, HTTP/1.1+2) | ✅ | | | `src/Aouda.Server/`, P4 §2 #1 | |
| REST query API | ✅ | | | `src/Aouda.Server/Controllers/QueryController.cs` | |
| Schema management API (9 DDL endpoints) | ✅ | | | `src/Aouda.Server/Controllers/TablesController.cs` | |
| Connection lifecycle middleware (timeout, rate limit, correlation ID) | ✅ | | | `src/Aouda.Server/Middleware/`, P4 §3.4 | |
| `AOUDA_*` env var + CLI arg configuration | ✅ | | | `src/Aouda.Server/Configuration/`, P4 §3.5 | |
| Wire protocol `Aouda.Protocol` with version headers | ✅ | | | `src/Aouda.Protocol/`, P4 §3.6 | |
| Multi-database registry (`databases.json`) | ✅ | | | `src/Aouda.Engine.Storage/Registry/DatabaseRegistryStore.cs`, P6 §2 #2 | |
| `DatabaseManager` lifecycle orchestration | ✅ | | | `src/Aouda.Engine.Api/DatabaseManager.cs`, P6 §2 #3 | |
| Database CRUD via HTTP | ✅ | | | `src/Aouda.Server/Controllers/DatabasesController.cs`, P6 §5.2 | |
| Database-scoped data routes `/api/databases/{db}/…` | ✅ | | | P6 §5.2; code in `TablesController.cs`, `QueryController.cs` | |
| Startup `Aouda:Databases` reconcile | ✅ | | | P6 §2 #7 | |
| Database lifecycle state machine (Creating/Active/Dropping/Dropped) | ✅ | | | `src/Aouda.Engine.Storage/Registry/DatabaseState.cs` | |
| Per-database memory governance | ✅ | | | `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs`, P6 §2 #14 | |
| Per-database metrics tracking | ✅ | | | `src/Aouda.Server/Metrics/DatabaseMetricsTracker.cs`, P6 §2 #15 | |
| `GET /api/server/memory` | ✅ | | | `src/Aouda.Server/Controllers/ServerController.cs` line 44 | |
| `GET /api/server/metrics` | ✅ | | | `src/Aouda.Server/Controllers/ServerController.cs` line 81 | |
| `GET /api/server/databases/{db}/metrics` | ✅ | | | `src/Aouda.Server/Controllers/ServerController.cs` line 122 | |
| `/api/admin/metrics` subsystem metrics | ✅ | | | `src/Aouda.Server/Controllers/MetricsController.cs`, P4 §2 #15 | |
| `/health`, `/ready`, `/health/detailed` | ✅ | | | `src/Aouda.Server/Controllers/HealthController.cs`, P4 §2 #18 | |
| Per-database health check | ✅ | | | `src/Aouda.Server/Health/DatabaseHealthCheck.cs`, P6 §2 #15 | |
| `POST /api/server/shutdown` (loopback only) | ✅ | | | `src/Aouda.Server/Controllers/ServerController.cs` line 162, P7 §2 #11 | |
| `POST /api/databases/{db}/query/count` | ✅ | | | `src/Aouda.Server/Controllers/QueryController.cs`, P7 §2; `RemoteTableQuery.CountAsync` | |
| Structured JSON logging | ✅ | | | `src/Aouda.Server/Logging/JsonConsoleFormatter.cs`, P4 §2 #16 | opt-in |
| OpenTelemetry tracing | ✅ | | | `src/Aouda.Engine.Diagnostics/Tracing/AoudaActivitySources.cs`, P4 §2 #17 | opt-in |
| Unified CLI (`aouda start/stop/databases`) | ✅ | | | `src/Aouda.Cli/Commands/`, `src/Aouda.Server/Hosting/ServerHostRunner.cs`, P16 §5.4 | |
| `Aouda.Server.exe` / `aouda` command split | ✅ | | | `src/Aouda.Server/Cli/CliParser.cs`, P4 §2 #19 | |
| First-run bootstrap (`GET /api/auth/setup/status`, `aouda init`) | ✅ | | | `src/Aouda.Server/Controllers/SetupController.cs`, `src/Aouda.Cli/Commands/InitCommand.cs` | |
| `Aouda.Embedded.Hot` hot cache client | | | ❌ | withdrawn BL-162 (2026-08-13) | Rebuild as named-query materialization (BL-164) |
| .NET client `client.Databases.ListAsync/CreateAsync` | ✅ | | | `src/Aouda.Client/Databases/AoudaDatabasesApi.cs` | |
| .NET client `client.Databases.GetAsync / DropAsync` | | | ❌ | P6 §5.2 (HTTP endpoints exist); `AoudaDatabasesApi.cs` has only List + Create | See §2.18 |
| Admin management API under `/admin/*` (P16) | ✅ | | | `src/Aouda.Server/Controllers/Cluster|Backup|Config|Node|CapabilitiesController.cs`, P16 §5.3 | |
| Runtime config persistence (`cluster-state.json`, `backup-config.json`) | ✅ | | | P16 §3.2, §5.6 | |
| Prometheus scrape format | | | ❌ | P4 §10 (deferred); P6 §10 | See §2.18 |
| `ActiveConnections` counter | | ❌ | | `MetricsSummary` returns 0; P4 §10 | See §2.18 |
| `aouda dev` as distinct ephemeral mode | | ❌ | | ADR 0026; P16 SA6 not evidenced; `aouda start` is the shipped entry point | See §2.18 |

---

## 2.7 Core Concepts and Mental Model

### The server-as-orchestrator pattern

An `Aouda.Server` process is a thin ASP.NET Core host. Its role is to:

1. **Own zero data logic.** All data operations delegate to `AoudaEngine` via DI. Controllers are thin: no engine construction, no blocking inline async.
2. **Orchestrate one engine per database.** `DatabaseManager` maintains a `ConcurrentDictionary<string, AoudaEngine>` keyed by database name. Engine lookups (the hot path for request routing) are lock-free `TryGetValue` calls. Lifecycle mutations (create / drop) are serialized by a `SemaphoreSlim(1,1)`.
3. **Route HTTP by database.** Incoming requests carry a database name — either in the URL path (`/api/databases/{db}/…`) or in the request body (`database` field). A mismatch between path and body returns `400 INVALID_REQUEST`.
4. **Govern memory across engines.** `ServerMemoryBudgetManager` tracks each engine's memory usage and assigns **weighted shares of one server budget**. HTTP create still accepts `maxMemoryBytes` as a cap on that computed share.

### Directory layout

```
{DataPath}/
  Server/
    databases.json            ← registry of all database definitions
    cluster-state.json        ← runtime cluster config (P16, present if cluster joined)
    backup-config.json        ← runtime backup schedule (P16)
  Databases/
    {dbName}/
      catalog/
        catalog.json          ← table/column definitions (WAL-backed)
      wal/
        wal_000000001.log   ← segmented write-ahead log (not insert.wal)
        CHECKPOINT          ← crash redo horizon
      tables/
        {tableName}/          ← column files, segment manifests
      materialized/           ← materialized query definitions + data
```

### Route taxonomy

| Prefix | Scope | Examples |
|---|---|---|
| `/api/databases` | Server-level database management (no db context required) | `GET /api/databases`, `POST /api/databases` |
| `/api/databases/{db}/…` | Per-database data plane | `/api/databases/{db}/query`, `/api/databases/{db}/tables/*` |
| `/api/server/…` | Server-level observability | `/api/server/memory`, `/api/server/metrics`, `/api/server/shutdown` |
| `/api/admin/metrics` | Global Perf-counter metrics (P4) | `/api/admin/metrics/query` |
| `/admin/…` | Management-plane admin (P16, requires server-auth scope) | `/admin/cluster/*`, `/admin/backup/*`, `/admin/config`, `/admin/node`, `/admin/capabilities` |
| `/health`, `/ready`, `/health/detailed` | Kubernetes / load-balancer probes | |
| `/api/auth/…` | Authentication and setup | `/api/auth/setup/status` |
| `/api/subscribe/hot` | SSE hot-segment subscription | |

### Flat vs database-scoped routes (P4 → P6 clean break)

P4 introduced a flat `/api/*` surface (single engine, no database context). P6 moved the data plane to `/api/databases/{db}/*` and introduced server-level endpoints at `/api/server/*`. The transition was a **clean break** — no backward-compatibility shim exists in source materials. Clients written against P4 flat routes must be updated to include the `database` URL segment and the `database` field in request bodies.

### Database lifecycle state machine

```
POST /api/databases
  → Creating → Active
              ↓
DELETE /api/databases/{db}
              → Dropping → Dropped (removed from registry on next save)
```

`DatabaseManager.InitializeAsync` opens all `Active` entries at startup. `Failed` databases (failed to open) are tracked in `_failedDatabases` and visible in health responses.

### Key invariants

- Database names are case-insensitive for lookup (`StringComparer.OrdinalIgnoreCase`).
- A single `AoudaEngine` instance is always registered as a DI singleton per hosted service invocation; in multi-database mode, `DatabaseManager` is the singleton and engines are per-database.
- `AoudaHostedService.StartAsync` completes before the first request is served.
- `StopAsync` calls `DisposeAsync` on all engines, flushing WAL and in-flight transactions for graceful shutdown.
- Dropping a database performs a fast foreground switch (remove engine from routing, persist `Dropping` state) and returns `204` immediately; all cleanup (engine dispose, directory delete with exponential-backoff retry, registry completion) runs in a background `PendingOpsWorker` job that is persisted to `pending_jobs.json` and automatically resumes after a server restart or crash.

---

## 2.8 How Aouda Implements It

### Architecture path

```
Process start
  → WebApplication.CreateBuilder
  → AddAoudaServer (DI registration)
      - DatabaseRegistry + DatabaseRegistryStore (registry)
      - DatabaseManager (orchestrator)
      - ServerMemoryBudgetManager (memory governance)
      - DatabaseMetricsTracker (per-db ops metrics)
      - MetricsCollector (global Perf counters)
      - HealthAggregator + IComponentHealthCheck implementations
      - StructuredLogging + OtelConfiguration
  → MapControllers
  → StartAsync
      DatabaseManager.InitializeAsync
        → reads databases.json via DatabaseRegistryStore
        → calls AoudaEngine.OpenAsync for each Active database
        → registers each engine with ServerMemoryBudgetManager
      PendingOpsWorker.StartAsync
        → prunes Done/Failed jobs from pending_jobs.json
        → re-enqueues any Running/Interrupted jobs (crash recovery)
        → starts background processing loop (Channel-based)
  → Kestrel begins accepting requests
  → Middleware pipeline:
      ProtocolVersionMiddleware
      CorrelationIdMiddleware
      LogContextEnricherMiddleware
      RequestLoggingMiddleware
      RateLimiter (concurrency 50 / queue 100)
      RequestTimeouts (30 s)
      Controllers (database-aware routing)
  → StopAsync
      PendingOpsWorker.StopAsync
        → drains in-flight job (waits for current handler to complete or cancels)
        → marks interrupted jobs as Interrupted in pending_jobs.json
      DatabaseManager.DisposeAsync
        → AoudaEngine.DisposeAsync for each engine (WAL flush + cleanup)
```

### Component interactions

| Component | Location | Role |
|---|---|---|
| `AoudaHostedService` | `src/Aouda.Server/Startup/AoudaHostedService.cs` | Single-engine mode (pre-P6); opens one engine at startup |
| `DatabaseManager` | `src/Aouda.Engine.Api/DatabaseManager.cs` | Multi-database orchestrator; lock-free engine lookup, serialized lifecycle |
| `PendingOpsWorker` | `src/Aouda.Engine.Api/Jobs/PendingOpsWorker.cs` | Channel-based persistent job queue; dispatches to `IPendingJobHandler`; startup crash recovery; exponential-backoff retry |
| `DropDatabaseJobHandler` | `src/Aouda.Engine.Api/Jobs/DropDatabaseJobHandler.cs` | First `IPendingJobHandler`; three-phase drop (engine dispose → directory delete → registry complete) |
| `PendingJobStore` | `src/Aouda.Engine.Storage/Jobs/PendingJobStore.cs` | JSON persistence for `PendingJobRecord`s; atomic write; survives crashes |
| `DatabaseRegistry` | `src/Aouda.Engine.Storage/Registry/DatabaseRegistry.cs` | In-memory registry state with read-lock |
| `DatabaseRegistryStore` | `src/Aouda.Engine.Storage/Registry/DatabaseRegistryStore.cs` | Serializes registry to/from `databases.json` with atomic writes |
| `ServerMemoryBudgetManager` | `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs` | Coordinates per-engine budgets; exposes `GetServerUsage()` |
| `DatabaseMetricsTracker` | `src/Aouda.Server/Metrics/DatabaseMetricsTracker.cs` | Records per-db query/insert ops; snapshots for `GET /api/server/metrics` |
| `DatabaseHealthCheck` | `src/Aouda.Server/Health/DatabaseHealthCheck.cs` | Non-critical health check; queries engine reachability |
| `ServerController` | `src/Aouda.Server/Controllers/ServerController.cs` | `GET /api/server/memory`, `/api/server/metrics`, `/api/server/databases/{db}/metrics`, `POST /api/server/shutdown` |
| `DatabasesController` | `src/Aouda.Server/Controllers/DatabasesController.cs` | `GET/POST /api/databases`, `GET/DELETE /api/databases/{db}` |
| `MetricsCollector` | `src/Aouda.Server/Metrics/MetricsCollector.cs` | Samples 250+ Perf counters; 1 h circular buffer; `/api/admin/metrics` |
| `HealthAggregator` | `src/Aouda.Server/Health/HealthAggregator.cs` | Aggregates six component checks; `/health/detailed` |

### Critical P6 invariants

- `DatabaseManager` constructor accepts an optional `ServerMemoryBudgetManager?`; it is null in isolated test contexts.
- `DatabasesController` validates that the `database` field in request bodies matches the `{db}` path segment; mismatch → `400 INVALID_REQUEST`.
- `TableDurabilityOptions` null fields inherit database-level defaults. `EnableWal=true` is invalid when the database-level WAL is disabled.
- Write concern resolution order: per-write → table → database → `One`.

---

## 2.8.1 Critical Path Walk-throughs

### Walk-through 1: Database creation

```
POST /api/databases
  → ProtocolVersionMiddleware (echo/set headers)
  → CorrelationIdMiddleware (X-Correlation-ID)
  → RateLimiter (concurrency check)
  → RequestTimeouts (start 30 s clock)
  → DatabasesController.CreateDatabase(request, ct)
      → validate request.Name is not empty → 400 if empty
      → DatabaseManager.CreateDatabaseAsync(name, options)
          → _lifecycleLock.WaitAsync()       // serialize create/drop
          → DatabaseRegistry.Exists(name)?   // → 409 if already exists
          → DatabaseRegistryStore.CreateAsync(name, options)
              → write Creating state to databases.json (atomic)
              → create Databases/{name}/ directory scaffold
          → AoudaEngine.OpenAsync(dbPath)    // open catalog + WAL + store
          → register engine with _engines[name]
          → _serverBudgetManager?.Register(name, engine.BudgetManager)
          → DatabaseRegistry.SetState(name, Active) → write to databases.json
          → _lifecycleLock.Release()
      → return 201 Created + DatabaseInfoResponse
  → RequestLoggingMiddleware (log duration)
```

**State mutations:** `databases.json` updated twice (Creating → Active); directory scaffold created; engine opened.
**Failure behavior:** if `OpenAsync` throws, state remains `Creating`; `_failedDatabases` list records the error; `_lifecycleLock` is released in `finally`.
**Observability:** `Perf.DatabasesCreated` counter incremented; structured log at `Information`.
**Tests:** `tests/Aouda.Engine.Api.Tests/DatabaseManagerTests.cs`, `tests/Aouda.Server.Tests/DatabasesIntegrationTests.cs`.

### Walk-through 2: Database drop

```
DELETE /api/databases/{db}
  → middleware chain (protocol, correlation, rate limit, timeout)
  → DatabasesController.DropDatabase(db, ct)
      → DatabaseManager.DropDatabaseAsync(db)
          → _lifecycleLock.WaitAsync()        // serialize create/drop
          → verify engine is in Active state  // → 404 if not found, 204 idempotent if already Dropping
          → remove engine from _engines[db]   // no more queries routed to this engine
          → unregister from _serverBudgetManager
          → collect branch engines (snapshots, replicas)
          → DatabaseRegistry.MarkForDropAsync(db)  // persist Dropping state (atomic write)
          → _lifecycleLock.Release()          // ← lock released here; 204 about to return
          → PendingOpsWorker.EnqueueAsync(    // persisted to pending_jobs.json BEFORE return
              "DropDatabase",
              '{"name":"<db>"}',
              inMemoryContext: (engine, branchEngines))
      → return 204 No Content
  → background: PendingOpsWorker dequeues + dispatches to DropDatabaseJobHandler
      Phase 1 (if inMemoryContext not null):  engine.DropDisposeAsync()
                                               // skips HRA snapshot; WAL/data discarded
                                               // branch engines also disposed
      Phase 2 (retry loop):  Directory.Delete(recursive) — 1s→2s→…→30s cap
      Phase 3 (retry loop):  DatabaseRegistry.CompleteDropAsync(db)
                                               // removes Dropping entry; atomic write
```

**State mutations:** engine removed from routing immediately (foreground); directory and registry entry removed later (background).  
**Crash safety:** `pending_jobs.json` is written atomically before `204` is returned. On restart, `PendingOpsWorker.StartAsync` loads `Running`/`Interrupted` jobs and re-executes them; phase 1 (engine dispose) is skipped on the recovery path since the engine is no longer in memory.  
**Idempotency:** Re-issuing `DELETE` while a drop is in progress returns `204` (idempotent, no second job enqueued).  
**Observability:** `Perf.DatabasesDropped` counter; structured log at `Information` per phase; `Error`-level log if retry eventually fails.  
**Tests:** `tests/Aouda.Engine.Api.Tests/DatabaseManagerTests.cs` (BL-127 ACs 1–14); `tests/Aouda.Engine.Api.Tests/Jobs/PendingOpsWorkerTests.cs` (BL-129 ACs S2-1–S2-8).

### Walk-through 3: Database-scoped query routing

```
POST /api/databases/{db}/query
  Body: { "database": "{db}", "table": "orders", "limit": 100 }
  → middleware chain (protocol, correlation, rate limit, timeout)
  → QueryController.ExecuteQuery(db, request, ct)
      → validate request.Database == db (path match) → 400 if mismatch
      → DatabaseManager.GetEngine(db) → lock-free TryGetValue
          → 404 DATABASE_NOT_FOUND if engine absent
      → QueryTranslator.Translate(engine, request) → TableQuery
      → TableQuery.ToColumnarAsync(ct)    // engine evaluates
      → BuildColumnarResponse(result) → JSON
  → return 200 + ColumnarResult JSON
```

**State mutations:** none (read-only query path).
**Observability:** `DatabaseMetricsTracker.RecordQuery(db, ms, rowsReturned)` called; `Perf.QueryTotal` incremented; `aouda.query` OTel span.
**Tests:** `tests/Aouda.Server.Tests/MultiDatabaseIntegrationTests.cs`, `tests/Aouda.Server.Tests/QueryIntegrationTests.cs`.

### Walk-through 4: Graceful shutdown

```
POST /api/server/shutdown  (must originate from loopback)
  → middleware chain
  → ServerController.Shutdown()
      → ServerController.IsShutdownCallerLoopback(HttpContext)
          → IPAddress.IsLoopback(RemoteIpAddress) → 403 if non-loopback
      → _hostLifetime.StopApplication()
          → CancellationToken cancellation propagates to all hosted services
          → AoudaHostedService.StopAsync (or DatabaseManager.DisposeAsync)
              → foreach engine: AoudaEngine.DisposeAsync()
                  → WAL flush → hot segment seal → resource cleanup
      → return 202 Accepted + { "status": "shutting down" }
```

**State mutations:** all engines flushed and closed; data directory left in clean state.
**Usage:** the P7 test harness (`ServerManager.StopAsync`) calls this endpoint before restart. Falls back to process kill if no response within timeout.
**Tests:** `tests/Aouda.Server.Tests/CountIntegrationTests.cs`, `tests/Aouda.TestHarness.Tests/ServerManagerTests.cs`.

### Walk-through 4: Server startup reconcile with pre-configured databases

```
Startup config: { "Aouda": { "Databases": { "analytics": { "EnableWal": true, "MaxMemoryShareBytes": 1073741824 } } } }
  → AoudaServerOptions binds DatabaseConfigSection entries
  → AoudaHostedService (or server startup middleware) reads Aouda:Databases
  → foreach entry name in config:
      → if !DatabaseManager.DatabaseExists(name):
          → DatabaseManager.CreateDatabaseAsync(name, configOptions)  // idempotent
      → if exists: no-op (reconcile is additive, not destructive)
  → normal InitializeAsync opens all Active databases
```

**Result:** declared databases are available immediately after server start without manual `POST /api/databases` calls.
**Tests:** P6 Integration tests (`tests/Aouda.Server.Tests/MultiDatabaseIntegrationTests.cs`).

---

## 2.9 Why Aouda Is Different

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Multi-database isolation model | Shared buffer pool; namespace-level isolation | Separate `AoudaEngine` per database: own catalog, WAL, table storage, memory budget | A slow table in `analytics` cannot consume resources from `trading`; drop is clean |
| Server + CLI bundled | Separate server binary and CLI tool | Single `aouda` binary via `Aouda.Cli`; `Aouda.Server.exe` restricted to runtime ops only | One binary to distribute; operators and AI agents learn one tool |
| Management API design | Often requires config files or restarts | All mutations (cluster join, backup schedule, config) go through HTTP APIs; state persists in focused JSON files | Safe to automate with idempotent API calls; no server restart for most changes |
| Observability granularity | Global metrics or none | Per-database memory + ops metrics alongside global Perf-counter subsystems; per-db health check in `/health/detailed` | Diagnose per-tenant hotspots without shared metrics noise |
| Shutdown semantics | SIGTERM → hope | `POST /api/server/shutdown` calls `StopApplication()` → WAL flush → clean exit | Durability tests can trigger and verify clean shutdown without `kill -9` |

---

## 2.10 Configuration and Settings Reference

### Server process settings (`src/Aouda.Server/Configuration/AoudaServerOptions.cs`)

| Setting | Type | Default | Env var / CLI | Notes |
|---|---|---|---|---|
| `Aouda:DataPath` | `string` | `"./data"` | `AOUDA_DATAPATH` or `AOUDA_DATA_PATH` / `--data-path` | Root data directory; `AOUDA_DATA_PATH` is a Docker/K8s alias |
| `Aouda:Port` | `int` | `5000` | `AOUDA_PORT` / `--port` | Must be 1–65535 |
| `Aouda:Bind` | `string` | `null` | `AOUDA_BIND` / `--bind` | Override Kestrel binding (e.g., `0.0.0.0:5000`); P16 |
| `Aouda:EnableHttp2` | `bool` | `true` | `AOUDA_ENABLEHTTP2` | HTTP/1.1 + HTTP/2 simultaneous |
| `Aouda:MaxConnections` | `int` | `100` | `AOUDA_MAXCONNECTIONS` | Kestrel `MaxConcurrentConnections` |
| `Aouda:MaxConcurrentRequests` | `int` | `50` | `AOUDA_MAXCONCURRENTREQUESTS` | Concurrency limiter; returns 503 at capacity |
| `Aouda:RequestQueueLimit` | `int` | `100` | — | Queue depth before 503 |
| `Aouda:RequestTimeoutMs` | `int` | `30000` | `AOUDA_REQUESTTIMEOUTMS` | Must be ≥ 100 ms; returns 504 on breach |
| `Aouda:Join` | `string` | `null` | `AOUDA_JOIN` / `--join` | Join-on-startup primary address (P16) |
| `Aouda:Role` | `string` | `null` | `AOUDA_ROLE` / `--role` | Startup role hint, e.g., `witness` (P16) |
| `AOUDA_CORS_ORIGINS` / `Aouda:CorsOrigins` | `string[]` | Hub + localhost | env/config | Default CORS policy origins; comma-separated |

### Memory settings (`Aouda:Memory`)

| Setting | Type | Default | Env var | Notes |
|---|---|---|---|---|
| `Aouda:Memory:MaxTotalRamBytes` | `long` | ~70% of detected RAM | `AOUDA_MEMORY__MAXTOTALRAMBYTES` | Process RSS ceiling; shared as per-database shares |
| `Aouda:Memory:MaxHotBytes` | `long` | `0` (auto: 70%) | `AOUDA_MEMORY__MAXHOTBYTES` | Hot segment budget; 0 = auto |
| `Aouda:Memory:MaxPageCacheBytes` | `long` | `0` (auto: 20%) | `AOUDA_MEMORY__MAXPAGECACHEBYTES` | Page cache budget; 0 = auto |

### Tracing settings (`Aouda:Tracing`)

| Setting | Type | Default | Notes |
|---|---|---|---|
| `Aouda:Tracing:Enabled` | `bool` | `false` | Opt-in; disabled by default |
| `Aouda:Tracing:OtlpEndpoint` | `string` | `"http://localhost:4317"` | OTLP collector |
| `Aouda:Tracing:Protocol` | `string` | `"Grpc"` | `"Grpc"` or `"Http"` |
| `Aouda:Tracing:SamplingRatio` | `double` | `1.0` | 0.0–1.0 |
| `Aouda:Tracing:ConsoleExport` | `bool` | `false` | Debug only |
| `Aouda:Tracing:ServiceName` | `string` | `"Aouda.Server"` | OTEL service name |

### Health settings (`Aouda:Health`)

| Setting | Type | Default | Notes |
|---|---|---|---|
| `Aouda:Health:StartupDelaySeconds` | `int` | `10` | Suppress readiness failures during startup window |
| `Aouda:Health:CheckTimeoutMs` | `int` | `5000` | Per-component check timeout |
| `Aouda:Health:Thresholds:ReplicationLagDegradedSeconds` | `int` | `10` | |
| `Aouda:Health:Thresholds:WalQueueDegradedPercent` | `int` | `80` | |
| `Aouda:Health:Thresholds:MemoryDegradedPercent` | `int` | `80` | |

### Per-database settings (`Aouda:Databases:<name>`)

These can be declared in config to provision databases at startup or to set defaults; they map to `DatabaseOptions` in the registry.

| Setting | Type | Default | Notes |
|---|---|---|---|
| `Aouda:Databases:<name>:EnableWal` | `bool` | `true` | WAL for this database |
| `Aouda:Databases:<name>:ReplicationMode` | `string` | `Replicate` | `Replicate` or `DoNotReplicate` |
| `Aouda:Databases:<name>:MaxMemoryShareBytes` | `long?` | `null` | Optional cap on this database's share of the server budget |
| `Aouda:Databases:<name>:DefaultTemperature` | `string` | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` |
| `Aouda:Databases:<name>:WriteConcern` | `string` | `One` | `One`, `Majority`, `All` |
| `Aouda:Databases:<name>:WriteConcernTimeoutMs` | `int` | `5000` | ACK wait timeout (≥ 100 ms) |
| `Aouda:Databases:<name>:OnWriteConcernTimeout` | `string` | `DegradeAndLog` | `Fail`, `Degrade`, `DegradeAndLog` |

### Logging

| Setting | Type | Default | Notes |
|---|---|---|---|
| `Logging:Console:FormatterName` | `string` | `"simple"` | Set to `"json"` for structured production logging |

### Configuration source priority (lowest → highest)

See **[Server configuration](server-configuration.md)** for the full model (install bootstrap, restart behavior, and data-directory persistence).

Startup binding for `AoudaServerOptions`:

`code defaults → appsettings.json (optional) → appsettings.{Env}.json → environment variables → AOUDA_* env vars → CLI flags (--data-path, --port, …)`

{: .important }
**Release installs do not ship `appsettings.json`.** `Aouda.Setup` and `install-aouda.ps1` pass `--data-path` and `--port` on the Windows Service / systemd command line instead.

Nested sections use `__` separator in env vars: `AOUDA_MEMORY__MAXTOTALRAMBYTES`.

---

## 2.11 API and CLI Coverage Reference

### A) API coverage matrix

| Capability | .NET API | HTTP | Status | Notes |
|---|---|---|---|---|
| List databases | `client.Databases.ListAsync()` | `GET /api/databases` | ✅ | |
| Create database | `client.Databases.CreateAsync(name, opts)` | `POST /api/databases` | ✅ | |
| Get database | — | `GET /api/databases/{db}` | ⚠️ Partial | HTTP endpoint exists; .NET client wrapper missing (see §2.18) |
| Drop database | — | `DELETE /api/databases/{db}` | ⚠️ Partial | HTTP endpoint exists; .NET client wrapper missing |
| Query (columnar) | `client.Table(t).ToColumnarAsync()` | `POST /api/databases/{db}/query` | ✅ | |
| Query count | `client.Table(t).CountAsync()` | `POST /api/databases/{db}/query/count` | ✅ | |
| Insert rows | `client.Table(t).InsertAsync(rows)` | `POST /api/databases/{db}/tables/{t}/rows` | ✅ | |
| Schema DDL | `client.Schema.*` | `GET/POST/DELETE/PATCH /api/databases/{db}/tables/*` | ✅ | |
| Server memory | — | `GET /api/server/memory` | ✅ | Operator/monitoring use |
| Server metrics | — | `GET /api/server/metrics` | ✅ | Operator/monitoring use |
| Per-db metrics | — | `GET /api/server/databases/{db}/metrics` | ✅ | Operator/monitoring use |
| Global Perf metrics | — | `GET /api/admin/metrics[/{subsystem}]` | ✅ | 12 subsystems, 1 h history |
| Health liveness | `client.GetHealthAsync()` | `GET /health` | ✅ | Always 200 if process alive |
| Health readiness | — | `GET /ready` | ✅ | 503 if critical component unhealthy |
| Health detailed | — | `GET /health/detailed` | ✅ | All 6 component checks |
| Graceful shutdown | — | `POST /api/server/shutdown` | ✅ | Loopback only; 403 for non-loopback |
| First-run status | — | `GET /api/auth/setup/status` | ✅ | Loopback-exempt; returns setup state |
| `aouda init` bootstrap | CLI `aouda init` | — | ✅ | Idempotent; no data creation |
| Cluster lifecycle | — | `POST/DELETE/PATCH /admin/cluster/*` | ✅ (P16) | Server-auth scope required |
| Backup/restore admin | — | `POST/GET /admin/backup/*` | ✅ (P16) | Server-auth scope required |
| Runtime config | — | `GET/PATCH /admin/config[/schema]` | ✅ (P16) | Mutable fields only; `cluster-state.json` |
| Capabilities discovery | — | `GET /admin/capabilities` | ✅ (P16) | Feature-flags payload |
| Node info + logs | — | `GET /admin/node[/logs[/stream]]` | ✅ (P16) | SSE for `/stream` |

### B) Missing API matrix

| Intended capability | Missing surface | Workaround | Planned source | Priority |
|---|---|---|---|---|
| Get single database info via .NET | `AoudaDatabasesApi.GetAsync(name)` | Call `ListAsync()` and filter | Backlog item (not formally tracked in P6 reports) | Medium |
| Drop database via .NET | `AoudaDatabasesApi.DropAsync(name)` | Use HTTP `DELETE /api/databases/{db}` directly | Same backlog item | Medium |
| Prometheus metrics scrape | `GET /metrics` in Prometheus format | Use JSON API and adapt | Explicitly deferred in P4/P6 sources | Low |
| Write concern status in .NET result | `InsertResult.WriteConcernStatus` | Read from HTTP response body (`writeConcernStatus`) | Backlog (P6 §10) | Low |

### .NET client examples

```csharp
// Construct client (database name required since P6)
using var client = new AoudaClient("http://localhost:5000", "analytics");

// List all databases
var list = await client.Databases.ListAsync();
foreach (var db in list.Databases)
    Console.WriteLine($"  {db.Name} ({db.State})");

// Create a database with a cap on its share of the server budget (HTTP field name is still maxMemoryBytes)
var created = await client.Databases.CreateAsync("trading", new CreateDatabaseOptions
{
    EnableWal = true,
    ReplicationMode = "Replicate",
    MaxMemoryBytes = 2L * 1024 * 1024 * 1024,
    DefaultTemperature = "Auto"
});

// Query a table in the created database
var tradeClient = new AoudaClient("http://localhost:5000", "trading");
var result = await tradeClient.Table("orders")
    .Where("status", "eq", "open")
    .Select("id", "price", "qty")
    .Limit(50)
    .ToColumnarAsync();

Console.WriteLine($"{result.RowCount} open orders returned in {result.Stats.ExecutionMs} ms");

// Count (no row materialization)
long count = await tradeClient.Table("orders")
    .Where("status", "eq", "filled")
    .CountAsync();
```

### HTTP examples

```bash
# Create a database
curl -s -X POST http://localhost:5000/api/databases \
     -H "Content-Type: application/json" \
     -d '{"name":"analytics","enableWal":true,"replicationMode":"Replicate","maxMemoryBytes":1073741824}'
# → 201 + { "name": "analytics", "state": "Active", ... }

# List databases
curl -s http://localhost:5000/api/databases
# → 200 + { "databases": [...], "count": 2 }

# Database-scoped query
curl -s -X POST http://localhost:5000/api/databases/analytics/query \
     -H "Content-Type: application/json" \
     -d '{"database":"analytics","table":"events","limit":10}'

# Server-wide memory snapshot
curl -s http://localhost:5000/api/server/memory

# Per-database metrics
curl -s http://localhost:5000/api/server/databases/analytics/metrics

# Graceful shutdown (loopback only)
curl -s -X POST http://localhost:5000/api/server/shutdown
# → 202 + { "status": "shutting down" }
```

### CLI examples

```bash
# Start the server
aouda start --bind 0.0.0.0:5000 --data-dir /var/aouda/data

# Stop the server (sends loopback shutdown request, then falls back to process kill)
aouda stop --server http://localhost:5000

# Database management
aouda databases list   --server http://localhost:5000
aouda databases create --name trading --server http://localhost:5000
aouda databases get    --name trading --server http://localhost:5000
aouda databases drop   --name trading --server http://localhost:5000

# One-off version check
aouda version

# Offline admin bootstrap (Aouda.Server.exe only)
./Aouda.Server create-admin --email admin@example.com --password "s3cret" \
    --data /var/aouda/data
```

---

## 2.12 Scenario Playbooks

### Scenario 1: Single-server first run

**When to use:** fresh installation, local development, single-database workloads.

```bash
# 1. Start the server
aouda start --data-dir ./data --bind 0.0.0.0:5000

# 2. Bootstrap admin user (interactive, or --json for automation)
aouda init --admin-email admin@example.com --admin-password "s3cret" \
    --server http://localhost:5000

# 3. Create a database
curl -s -X POST http://localhost:5000/api/databases \
     -H "Content-Type: application/json" \
     -d '{"name":"app","enableWal":true}'

# 4. Verify readiness
curl -s http://localhost:5000/ready
# → { "status": "healthy", ... }

# 5. Insert and query data
curl -s -X POST http://localhost:5000/api/databases/app/tables/users/rows \
     -H "Content-Type: application/json" \
     -d '{"database":"app","rows":[{"id":1,"name":"Alice","age":30}]}'

curl -s -X POST http://localhost:5000/api/databases/app/query \
     -H "Content-Type: application/json" \
     -d '{"database":"app","table":"users","limit":10}'
```

**Expected result:** server starts, admin bootstrapped, database `app` created, row inserted and returned.  
**Common mistake:** omitting `"database"` from the request body — returns `400 MISSING_DATABASE`.

---

### Scenario 2: Multi-database production setup with declarative config

**When to use:** hosting multiple application workloads with isolated memory budgets.

```json
// appsettings.Production.json
{
  "Aouda": {
    "DataPath": "/var/aouda/data",
    "Port": 5000,
    "Memory": { "MaxTotalRamBytes": 8589934592 },
    "Databases": {
      "analytics": {
        "MaxMemoryShareBytes": 4294967296,
        "DefaultTemperature": "ColdPreferred",
        "WriteConcern": "One"
      },
      "trading": {
        "MaxMemoryShareBytes": 2147483648,
        "DefaultTemperature": "HotOnly",
        "WriteConcern": "Majority",
        "WriteConcernTimeoutMs": 3000,
        "OnWriteConcernTimeout": "Fail"
      }
    },
    "Logging": {
      "Console": { "FormatterName": "json" }
    }
  }
}
```

```bash
# Start with declarative config (databases provisioned automatically at startup)
ASPNETCORE_ENVIRONMENT=Production aouda start

# Verify both databases are active
curl -s http://localhost:5000/api/databases
# → { "databases": [{"name":"analytics","state":"Active"}, {"name":"trading","state":"Active"}], "count": 2 }

# Check per-database memory
curl -s http://localhost:5000/api/server/memory
```

**Expected result:** both databases open at startup without manual `POST /api/databases` calls; memory partitioned as declared.  
**Common mistake:** declaring `MaxMemoryShareBytes` that exceeds the server `MaxTotalRamBytes` ceiling — server validates at startup.

---

### Scenario 3: Operator graceful maintenance restart

**When to use:** applying config changes or upgrades that require a server restart while ensuring WAL is flushed cleanly.

```bash
# 1. Stop accepting new requests (set at load-balancer level, out-of-scope)

# 2. Verify no in-flight requests via metrics
curl -s http://localhost:5000/api/server/metrics
# Inspect queryCount and insertCount trends

# 3. Trigger graceful shutdown from the same host
curl -s -X POST http://localhost:5000/api/server/shutdown
# → 202 + { "status": "shutting down" }
# Server flushes all WAL buffers and exits cleanly

# 4. Apply config changes, upgrade binary, etc.

# 5. Restart
aouda start --data-dir /var/aouda/data

# 6. Confirm all databases recovered
curl -s http://localhost:5000/ready
# → { "status": "healthy" }

curl -s http://localhost:5000/api/databases
# → all databases back in Active state
```

**Expected result:** clean WAL flush on shutdown; all data durable; databases re-open at startup without manual reconciliation.  
**Common mistake:** calling `POST /api/server/shutdown` from outside the local machine — returns `403 Forbidden`.

---

## 2.13 Operations and Observability

### What to monitor first

| Question | Endpoint | Practical answer |
|---|---|---|
| Is the server alive? | `GET /health` | Always 200 if process is running. Not a signal that databases are `Active`. |
| Is the server ready for traffic? | `GET /ready` | 503 if catalog or WAL check fails. Does not fail for one DB `Dropping`. |
| Is this database serving? | `GET /api/databases/{name}` | 200 + `state=Active` before schema apply. 404 if missing or `Dropping`. |
| Which databases are under memory pressure? | `GET /api/server/memory` | Check `pressure` field per database |
| What is query throughput and latency per database? | `GET /api/server/metrics` | `queryCount`, `queryMs`, `rowsReturned` per db |
| Global Perf counters (query, storage, WAL, bloom) | `GET /api/admin/metrics` | 12 subsystems; sparkline via `history` |
| Which database is consuming the most memory? | `GET /api/server/memory` | `perDatabaseUsage[{name}].totalBytes` |
| Node role, version, uptime | `GET /admin/node` | P16 admin endpoint |
| Recent server log events | `GET /admin/node/logs` | Buffered recent log entries |
| Tail logs in real time | `GET /admin/node/logs/stream` | SSE text/event-stream |

### Key observability signals

| Signal | Source | Notes |
|---|---|---|
| `Perf.QueryTotal` | `Aouda.Engine.Diagnostics` | Global query count |
| `DatabaseMetricsTracker.QueryCount[db]` | `Aouda.Server.Metrics` | Per-db query count |
| `ServerMemoryUsageSnapshot.PerDatabaseUsage[db].Pressure` | `ServerMemoryBudgetManager` | `Low` / `Medium` / `High` / `Critical` |
| `X-Correlation-ID` response header | `CorrelationIdMiddleware` | Trace requests through logs |
| `aouda.query` OTel span | `AoudaActivitySources` | Root query span; child `scan`, `filter` spans |
| `/health/detailed` JSON | `HealthAggregator` | `healthy` / `degraded` / `unhealthy` per component |

### Tuning sequence

1. If memory pressure is `High` or `Critical` on a database: increase `Aouda:Databases:{db}:MaxMemoryShareBytes` via `/admin/config PATCH` or restart with new config.
2. If `/ready` returns 503 on startup: check `Aouda:Health:StartupDelaySeconds` (default 10 s) and increase if catalog initialization is slow.
3. If queries are timing out (`504`): increase `Aouda:RequestTimeoutMs` (default 30 000 ms).
4. If server returns `503 SERVICE_UNAVAILABLE` under load: increase `Aouda:MaxConcurrentRequests` (default 50) and/or `Aouda:RequestQueueLimit` (default 100).
5. If write concern timeouts are noisy: switch `OnWriteConcernTimeout` from `Fail` to `DegradeAndLog` for non-critical tables, or increase `WriteConcernTimeoutMs`.

### Recovery and restart expectations

- **Clean restart:** `POST /api/server/shutdown` → WAL flush → clean exit → `aouda start` → all databases re-open; all data durable.
- **Crash restart:** `aouda start` → engine WAL replay on `OpenAsync` → databases recover from last durable WAL position.
- **Failed-to-open database:** recorded in `_failedDatabases`; visible in `/health/detailed`; does not block other databases from opening.
- **`Creating` state after crash:** partial directory scaffold; no engine was opened; safe to retry `POST /api/databases` with the same name.

---

## 2.14 Troubleshooting by Symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `400 MISSING_DATABASE` on query/insert | Request body missing `"database"` field | Add `"database": "{db}"` to request body; confirm field matches URL path `{db}` |
| `400 INVALID_REQUEST` on scoped route | `database` body field does not match `{db}` URL segment | Ensure path and body carry the same database name |
| `404 DATABASE_NOT_FOUND` on scoped route | Database name typo or database not yet created | Call `GET /api/databases` to list; create with `POST /api/databases` if missing |
| `409 CONFLICT` on `POST /api/databases` | Database already exists | Check `GET /api/databases`; database is `Active` or `Creating` |
| `503 SERVICE_UNAVAILABLE` on all requests | Server at concurrency limit | Increase `MaxConcurrentRequests`; check for runaway queries holding connections |
| `504 REQUEST_TIMEOUT` on heavy query | Query exceeded `RequestTimeoutMs` | Increase timeout or add predicates to reduce scan scope |
| `403 Forbidden` on `POST /api/server/shutdown` | Non-loopback caller | Only call from same machine (e.g., `curl http://localhost:5000/api/server/shutdown`) |
| `/ready` returns 503 shortly after start | Startup delay window active | Wait for `StartupDelaySeconds` (default 10 s) before load-balancer routing |
| `/ready` returns 503 after startup | Catalog or WAL check failing | Call `/health/detailed`; check `catalog` and `wal` component statuses; inspect logs |
| Database stays in `Creating` state after restart | Process crashed during `CreateDatabaseAsync` | Delete partial directory and retry `POST /api/databases`; or call admin cleanup |
| High memory pressure on one database | Tables fully loaded in hot tier | Add `Aouda:Databases:{db}:MaxMemoryShareBytes` cap; review table `StoragePolicy` |
| Write concern timeouts on insert | Replica ACK slower than `WriteConcernTimeoutMs` | Increase timeout or switch `OnWriteConcernTimeout` to `DegradeAndLog`; check replication lag via `/admin/replication/topology` |
| `AOUDA_*` env vars ignored | Wrong naming or missing `__` for nested keys | Top-level: `AOUDA_PORT`, `AOUDA_DATAPATH`. Nested: `AOUDA_MEMORY__MAXTOTALRAMBYTES` (double `__`, not single `_`). See [Server configuration](server-configuration.md#21-environment-variable-naming-aouda_) |
| Flat `/api/query` route returns 404 | P4-era flat routes removed in P6 | Update client to use `/api/databases/{db}/query` with `"database"` field in body |

---

## 2.15 Verification Ledger

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Server starts and `/health` returns 200 | `aouda start && curl http://localhost:5000/health` | Pass | 2026-05-19 | P4-era test suite `tests/Aouda.Server.Tests/ServerIntegrationTests.cs` |
| Database create/list/drop via HTTP | `tests/Aouda.Server.Tests/DatabasesIntegrationTests.cs` | Pass | 2026-05-19 | P6 |
| Multi-database routing isolation | `tests/Aouda.Server.Tests/MultiDatabaseIntegrationTests.cs` | Pass | 2026-05-19 | P6 scenarios M.1–M.8 |
| `POST /api/server/shutdown` loopback check | `tests/Aouda.Server.Tests/CountIntegrationTests.cs` (shutdown path) | Pass | 2026-05-19 | P7 BL-028 |
| Count endpoint | `tests/Aouda.Client.Tests/RemoteTableQueryCountAsyncTests.cs` | Pass | 2026-05-19 | P7 |
| Per-database metrics endpoints | `tests/Aouda.Server.Tests/Metrics/PerDatabaseMetricsIntegrationTests.cs` | Pass | 2026-05-19 | P6 |
| ServerMemoryBudgetManager | `tests/Aouda.Engine.Api.Tests/ServerMemoryBudgetManagerTests.cs` | Pass | 2026-05-19 | P6 |
| CLI `aouda start/stop/databases` | `tests/Aouda.Cli.Tests/` | Pass | 2026-05-19 | P16 SA6 |
| Health endpoints (liveness / readiness / detailed) | `tests/Aouda.Server.Tests/Health/HealthEndpointIntegrationTests.cs` | Pass | 2026-05-19 | P4 |
| Cluster lifecycle API (P16) | `tests/Aouda.Server.Tests/Cluster/ClusterControllerTests.cs` | Pass | 2026-05-19 | P16 |

---

## 2.16 Test Coverage Matrix

| Capability | Test files / suites | Status | Coverage strength | Notes |
|---|---|---|---|---|
| HTTP server lifecycle | `tests/Aouda.Server.Tests/ServerIntegrationTests.cs`, `ServerOptionsTests.cs` | Pass | Strong | P4 |
| Database CRUD | `tests/Aouda.Server.Tests/DatabasesIntegrationTests.cs` | Pass | Strong | P6 |
| Multi-database routing | `tests/Aouda.Server.Tests/MultiDatabaseIntegrationTests.cs` | Pass | Strong | P6 M.1–M.8 |
| `DatabaseManager` lifecycle | `tests/Aouda.Engine.Api.Tests/DatabaseManagerTests.cs` | Pass | Strong | P6 |
| Registry / `databases.json` | `tests/Aouda.Engine.Storage.Tests/Registry/*` | Pass | Strong | P6 |
| Per-database memory | `tests/Aouda.Engine.Api.Tests/ServerMemoryBudgetManagerTests.cs`, `PerDatabaseBudgetIntegrationTests.cs` | Pass | Strong | P6 |
| Per-database metrics | `tests/Aouda.Server.Tests/Metrics/PerDatabaseMetricsIntegrationTests.cs` | Pass | Medium | P6 |
| Per-database health check | `tests/Aouda.Server.Tests/Health/DatabaseHealthCheckTests.cs` | Pass | Medium | P6 |
| Wire protocol database field | `tests/Aouda.Server.Tests/WireProtocolDatabaseFieldTests.cs` | Pass | Strong | P6 |
| Connection lifecycle middleware | `tests/Aouda.Server.Tests/CorrelationIdMiddlewareTests.cs`, `ConnectionLifecycleIntegrationTests.cs` | Pass | Strong | P4 |
| Server configuration validation | `tests/Aouda.Server.Tests/AoudaServerOptionsValidatorTests.cs`, `ConfigurationIntegrationTests.cs` | Pass | Strong | P4 |
| Graceful shutdown | `tests/Aouda.Server.Tests/CountIntegrationTests.cs` (shutdown path) | Pass | Medium | P7 BL-028 |
| Count endpoint | `tests/Aouda.Client.Tests/RemoteTableQueryCountAsyncTests.cs` | Pass | Strong | P7 |
| Health endpoints | `tests/Aouda.Server.Tests/Health/HealthEndpointIntegrationTests.cs`, `HealthAggregatorTests.cs` | Pass | Strong | P4 |
| Global metrics (admin) | `tests/Aouda.Server.Tests/Metrics/MetricsIntegrationTests.cs` | Pass | Strong | P4 |
| Structured logging | `tests/Aouda.Server.Tests/Logging/JsonConsoleFormatterTests.cs`, `JsonFormatterIntegrationTests.cs` | Pass | Strong | P4 |
| OpenTelemetry tracing | `tests/Aouda.Server.Tests/Telemetry/TracingIntegrationTests.cs` | Pass | Medium | P4 |
| CLI `start/stop/databases` | `tests/Aouda.Cli.Tests/` | Pass | Medium | P16 |
| Cluster lifecycle API | `tests/Aouda.Server.Tests/Cluster/ClusterControllerTests.cs`, `ClusterManagementServiceTests.cs` | Pass | Strong | P16 |
| Backup admin API | `tests/Aouda.Server.Tests/Backup/BackupControllerTests.cs`, `BackupManagementServiceTests.cs` | Pass | Strong | P16 |
| `AoudaDatabasesApi` (.NET client) | Not located in test reports | Unknown | Weak | See §2.17 |

---

## 2.17 Testing Gaps and Proposed Tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| `AoudaDatabasesApi` unit test suite | No test evidence found for `ListAsync` / `CreateAsync` client wrappers; correctness of `CreateDatabaseRequestDto` mapping is untested at unit level | Add `tests/Aouda.Client.Tests/AoudaDatabasesApiTests.cs` with mock transport | High |
| `GET /api/databases/{db}` and `DELETE /api/databases/{db}` integration test | HTTP endpoints exist on server; no client wrapper; no integration test confirmed in source materials | Add `tests/Aouda.Server.Tests/DatabasesIntegrationTests.cs` assertions for get-by-name and drop | Medium |
| Startup reconcile for `Aouda:Databases` config | Declarative provisioning on startup is described in P6 but no dedicated test confirmed | Add scenario: config declares two databases → server starts → both are Active without manual POST | High |
| `Creating` state recovery after crash | Partial directory scaffold on aborted create; behavior on retry not covered | Add `DatabaseManagerTests` case: simulate crash after directory creation but before `Active` write; verify retry creates successfully | Medium |
| Non-loopback caller rejection on shutdown | Unit test for `IsShutdownCallerLoopback` is in `CountIntegrationTests.cs` but path coverage of `RemoteIpAddress == null` fallback is unclear | Add unit test with null `RemoteIpAddress` and loopback `LocalIpAddress` | Low |
| `ActiveConnections` counter wiring | Returns 0 always; when connection tracking is added, test should verify accurate reporting | Add integration test: open N concurrent connections, read `MetricsSummary.ActiveConnections` | Low (deferred) |

---

## 2.18 Known Gaps and Undone Work

- **`AoudaDatabasesApi` missing `GetAsync` and `DropAsync`** — The `AoudaDatabasesApi` in `src/Aouda.Client/Databases/AoudaDatabasesApi.cs` exposes only `ListAsync` and `CreateAsync`. `GET /api/databases/{db}` and `DELETE /api/databases/{db}` are fully implemented on the server side but have no .NET client wrapper. No formal backlog ID found in source materials; treat as medium-priority follow-on.

- **TypeScript multi-database client (P6 Epic C.3)** — The TypeScript `@aouda/client` multi-database wrappers are documented as delivered in P6 reports but are in the `aouda-client-ts` sibling repository and not verifiable at symbol level here. See `docs/tasks/P6-COMPLETION.md` §10.

- **`aouda dev` as a distinct command** — ADR 0026 mentions `aouda dev` as an ephemeral development server entry point. P16 SA6 shipped `aouda start` as the unified entry point; no `aouda dev` command is evidenced in `src/Aouda.Cli/` source materials in this repository. The `dev`-like behavior (ephemeral in-memory data path) is achievable with `aouda start --data-dir /tmp/aouda-dev`. This is a documentation drift between ADR 0026 intent and shipped P16 behavior.

- **`ActiveConnections` in `MetricsSummary`** — Returns 0 until HTTP connection tracking is wired. Noted in `P4-Server-And-Clients-COMPLETION.md` §10.

- **Prometheus scrape format** — JSON metrics API exists; Prometheus `/metrics` endpoint is explicitly deferred (P4 §10, P6 §10). No backlog ID confirmed.

- **Dynamic table-subscription reconfig** — Changing per-table replication subscriptions (`TableFilter`) requires secondary reconnect. Dynamic hot-reconfiguration is deferred. See `docs/tasks/P6-COMPLETION.md` §10.

- **Per-database historical metrics series** — `GET /api/server/databases/{db}/metrics` returns point-in-time snapshots. Time-series store for per-db metrics is deferred. See P6 §10.

- **`aouda dev` ephemeral mode** — See drift note above. Operators who need ephemeral dev databases use `aouda start` with a temp data path.

---

## 2.19 References

**ADRs:**
- `docs/decisions/0006-target-scope.md` — Managed-service model and thin-client philosophy motivating P4 Epic B.
- `docs/decisions/0026-aouda-cloud-and-hub-architecture.md` — Hub architecture, single-binary approach, three deployment tiers.
- `docs/decisions/0010-cluster-membership-replication.md` — Replication protocol extended by P6 per-database streaming.
- `docs/decisions/0011-memory-prioritization.md` — Memory budget architecture extended by P6 `ServerMemoryBudgetManager`.

**Task docs (primary sources):**
- `docs/tasks/P4-Server-And-Clients-COMPLETION.md` — HTTP server, wire protocol, C# client, monitoring, telemetry.
- `docs/tasks/P6-COMPLETION.md` — Multi-database registry, `DatabaseManager`, scoped routes, memory governance, per-db metrics.
- `docs/tasks/P7-COMPLETION.md` — Graceful shutdown (BL-028), count endpoint, harness multi-db scenarios.
- `docs/tasks/P16-COMPLETION.md` — Unified CLI (SA6), admin API expansion, cluster/backup/config/node endpoints.

**Code paths:**
- `src/Aouda.Server/` — All server-side implementation; controllers, middleware, configuration, health, metrics.
- `src/Aouda.Engine.Api/DatabaseManager.cs` — Multi-database orchestrator.
- `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs` — Per-database memory coordination.
- `src/Aouda.Engine.Storage/Registry/` — `DatabaseRegistry`, `DatabaseRegistryStore`, `DatabaseOptions`, `DatabaseState`.
- `src/Aouda.Client/Databases/AoudaDatabasesApi.cs` — .NET client database API.
- `src/Aouda.Client/AoudaClient.cs` — Top-level .NET client entry point.
- `src/Aouda.Cli/Commands/` — `StartCommand`, `StopCommand`, `DatabasesCommandHandler`.
- `src/Aouda.Server/Hosting/ServerHostRunner.cs` — Server lifecycle runner for CLI-hosted server.
- `src/Aouda.Server/Controllers/ServerController.cs` — Memory, metrics, shutdown endpoints.
- `src/Aouda.Server/Controllers/DatabasesController.cs` — Database CRUD.

**Tests:**
- `tests/Aouda.Server.Tests/` — Server integration tests (all capabilities).
- `tests/Aouda.Engine.Api.Tests/DatabaseManagerTests.cs` — `DatabaseManager` unit tests.
- `tests/Aouda.Engine.Storage.Tests/Registry/` — Registry / `databases.json` tests.
- `tests/Aouda.Cli.Tests/` — CLI command tests.

**Related Functionality docs:**
- `docs/dev/Functionality-HotCold-And-Memory.md` — Memory budget internals; `MemoryBudgetManager` per-engine.
- `docs/dev/Functionality-Partitioning-And-Multitenancy.md` — `DatabaseManager` narrative and PLS details; cross-link from here.
- `docs/dev/Functionality-Replication-And-Clustering.md` — Wire protocol v2/v3, write concern, table subscription filtering.
- `docs/dev/Functionality-Cloud-And-Hub.md` — CLI unification, Helm chart, Hub architecture.
- `docs/dev/Functionality-Storage-And-Persistence.md` — On-disk layout for each database's segment files.

---

## 2.20 What Is Missing from This Document?

- **`Aouda.Server.exe` vs `aouda` CLI internals** — The exact CLI command surface of `aouda databases get` and `drop` (P16 SA6) is documented at the HTTP layer; the internal CLI command handler (`DatabasesCommandHandler`) is not confirmed at method-level in source materials. No test artifacts for these CLI sub-commands are confirmed.
- **TypeScript multi-database API** — Not verifiable in this repository; described as delivered in P6 and P16 reports in the `aouda-client-ts` sibling repo.
- **Admin endpoint authentication details** — The `/admin/*` routes require `ServerAuth` scope (P16); the full auth middleware flow is documented in `Functionality-Auth-And-Authorization.md` rather than repeated here.
