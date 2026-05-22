---
title: "Materialized Queries"
nav_order: 12
parent: "Guides"
---

# Aouda Functionality: Materialized Queries

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

Coverage phases: P4, P10, P11
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P10/`, `docs/tasks/P11/`
Primary ADRs: `docs/decisions/0015-materialized-queries.md`, `docs/decisions/0020-real-time-streaming.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Query-Execution.md`, `docs/dev/Functionality-RealTime-Streaming.md`, `docs/dev/Functionality-Storage-And-Persistence.md`

## Start Here

If you are new to materialized queries, start with:
- `2.1 Why this functionality exists` (plain-language explanation)
- `2.1.1 What a materialized query is (in plain language)`
- `2.1.2 How it works in Aouda (step-by-step)`

If your question is "How do I use materialized queries now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Materialized queries in Aouda are for "compute once, keep fresh, read instantly" workloads.

### 2.1.1 What a materialized query is (in plain language)

A materialized query is a saved query result that Aouda keeps up to date for you.

Without a materialized query:
- each read request re-runs the full query logic against source data.

With a materialized query:
- Aouda computes the result once,
- stores that result as a table,
- and updates that result incrementally as source rows change.

Simple example:
- Source table: `orders`
- Query idea: "latest order per customer"
- Materialized query table: `latest_order_per_customer`
- Reads now hit the precomputed table instead of rebuilding the answer each time.

### 2.1.2 How it works in Aouda (step-by-step)

At a high level, Aouda does this:

1. You define a materialized query (for example latest-per-key, aggregate, or filter).
2. Aouda performs an initial build from the source table.
3. Aouda stores the result as a normal catalog table (same namespace as other tables).
4. New writes to the source table emit change events.
5. The materialized-query maintainer applies only incremental changes to the result table.
6. Reads query the result table directly, or are auto-routed there when a match exists.

What is different in Aouda vs many systems:
- The result is a regular table, not a special hidden object type.
- The query name is the table name (unified namespace; no `_mq_` prefix).
- Subscription uses the normal table streaming path (`target = queryName`), not a custom protocol target.

- User problem solved:
  - Avoid re-running expensive query logic (for example aggregates, latest-per-key projections) on every read.
  - Keep query reads low-latency while source table writes continue.
- Operational outcomes:
  - Predictable read path for precomputed results.
  - Incremental maintenance through source-table change events.
  - Unified table semantics: materialized results are regular catalog tables.
- Scope boundaries:
  - This functionality does not currently provide JOIN-based materialized queries.
  - This functionality does not currently provide first-class TypeScript or HTTP APIs for MQ create/drop/list/status.
  - This functionality does not currently resolve the known MQ result-table duplicate-row bug after flush (P11 handoff).

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What is a materialized query in simple terms? | `2.1.1 What a materialized query is (in plain language)` |
| How does Aouda's approach work end-to-end? | `2.1.2 How it works in Aouda (step-by-step)` |
| What happens by default? | `2.3 Defaults and zero-config behavior` |
| What is shipped vs planned vs reserved? | `2.4 Availability status` |
| Which phase delivered what? | `2.5 Phase coverage matrix` |
| End-to-end capability completeness | `2.6 Capability coverage matrix` |
| Runtime model and invariants | `2.7 Core concepts and mental model` |
| Engine internals and critical paths | `2.8 How Aouda implements it` |
| Full settings and defaults | `2.10 Configuration and settings reference` |
| API parity and missing surfaces | `2.11 API and CLI coverage reference` |
| What is verified now | `2.15 Verification ledger`, `2.16 Test coverage matrix` |
| Current known limits and backlog items | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.3`, `2.11`, `2.12` |
| Operator/SRE | `2.10`, `2.13`, `2.14` |
| SDK maintainer | `2.11`, `2.17`, `2.18` |
| Engine contributor | `2.5`, `2.8`, `2.16`, `2.19` |

### Source map

- Task/report evidence:
  - `docs/tasks/P4/P4-EpicH-MaterializedQueries-Tasks.md`
  - `docs/tasks/P4/P4-EpicH-Task1-MaterializedQueryInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicH-Task2-LatestPerKeyPattern-Report.md`
  - `docs/tasks/P4/P4-EpicH-Task4-FilterPattern-Report.md`
  - `docs/tasks/P4/P4-EpicH-Task5-IncrementalUpdateSubscription-Report.md`
  - `docs/tasks/P4/P4-EpicH-Refactoring-Completion.md`
  - `docs/tasks/P4/P4-EpicH-BL020-QueryPlannerAutoRouting-Report.md`
  - `docs/tasks/P4/P4-EpicH-BL021-UnifiedTableNamespace-Report.md`
  - `docs/tasks/P4/P4-EpicH-R10.4-QueryUnflushedHraTableData-Report.md`
  - `docs/tasks/P10/P10-S10-MaterializedQuerySubscriptions.md`
  - `docs/tasks/P11/P11-Fix-R8-MaterializedQueryFlushIntegrationTests-Report.md`
- Core code:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
  - `src/Aouda.Engine.Api/TableQuery.cs`
  - `src/Aouda.Engine.Query/MaterializedQueryMatcher.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryDefinition.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQuerySubscriptionManager.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedResultTableManager.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Engine.Diagnostics/Perf.cs`
- TypeScript client code (cross-repo):
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/streaming/subscription.ts`
  - `../aouda-client-ts/src/tables.ts`
- Test evidence:
  - `tests/Aouda.Engine.Api.Tests/MaterializedQueryApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/LatestPerKeyApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/AggregateApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/FilterApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/MaterializedQueryAutoRoutingTests.cs`
  - `tests/Aouda.Engine.Api.Tests/IncrementalUpdateSubscriptionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Materialized/`
  - `tests/Aouda.Engine.Query.Tests/MaterializedQueryMatcherTests.cs`
  - `tests/Aouda.Client.Tests/Streaming/MaterializedQuerySubscriptionApiTests.cs`
  - `../aouda-client-ts/tests/streaming/subscription.test.ts`

## 2.3 Defaults and zero-config behavior

If you create a materialized query with standard helpers and no special options:

- `UpdateMode` defaults to `Async`.
- `CreatedUtc` is auto-set if omitted.
- Result table naming uses unified namespace (`result table name == MQ name`).
- Normal `TableQuery` reads attempt MQ auto-routing when a compatible MQ is `Ready`.
- Result-table storage temperature defaults by query type:
  - `Aggregate`, `LatestPerKey`, `FirstPerKey`: `HotOnly`
  - `Filter`, `TopNPerGroup`: `Auto`
- Subscription manager defaults:
  - `MaxLag = 1s`
  - `MaxQueueDepth = 10000`
  - `ProcessingBatchSize = 100`

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `MaterializedQueryDefinition.UpdateMode` | `Async` | Base writes usually stay fast; result visibility can lag |
| `MaterializedQueryDefinition.CreatedUtc` | set to `DateTime.UtcNow` when missing | Definitions always have creation timestamp |
| `MaterializedQueryDefinition.ResultTableName` | `Name` (BL-021) | Query/subscription uses normal table name |
| `TableQuery` routing mode | auto-routing enabled | Compatible base-table queries are served from MQ result tables unless `WithDirectScan()` is used |
| Result table temperature (`Aggregate`) | `HotOnly` | Keeps small aggregate result sets hot |
| Result table temperature (`LatestPerKey`) | `HotOnly` | Keeps lookup-style results hot |
| Result table temperature (`Filter`) | `Auto` | Allows larger result sets to use hot/cold policy |
| `SubscriptionManagerOptions.MaxLag` | `1 second` | Threshold for lag/backpressure signaling |
| `SubscriptionManagerOptions.MaxQueueDepth` | `10000` | Queue bound for async MQ update processing |
| `SubscriptionManagerOptions.ProcessingBatchSize` | `100` | Batch size for update queue drain |

## 2.4 Availability status (implementation honesty)

### Available now

- Core infrastructure:
  - MQ definition/catalog/store/status lifecycle (`Building`, `Ready`, `Rebuilding`, `Error`).
  - Create/drop/list/status APIs in .NET engine.
- Implemented query patterns:
  - `LatestPerKey`, `Aggregate`, `Filter`.
- Incremental maintenance:
  - Update routing via `MaterializedQuerySubscriptionManager` with `Async` and `Sync` modes.
  - Guard against infinite loops for result-table events.
- Table-based result storage:
  - MQ results are regular catalog tables (compaction/hot-cold/persistence integration).
  - Unified namespace (no `_mq_` prefix).
- Planner integration:
  - Auto-routing from base-table `TableQuery` to matching MQ in `Ready` state.
  - `WithDirectScan()` bypass and routing decision visibility.
- Streaming behavior:
  - Subscribe to MQ results through normal table subscription path.
  - No protocol-level MQ target-kind required.

### Planned / proposed

- Explicit roadmap/backlog items still open:
  - BL-010: JOIN support in materialized queries (depends on BL-009).
  - BL-053: Distinct `MATERIALIZED_QUERY_NOT_READY` subscription error code.
- Query API expansion that unblocks richer MQ usage:
  - BL-003: nested AND/OR predicate support in REST query API.
  - BL-009: JOIN exposure in `TableQuery` API.

### Reserved / not yet wired

- MQ types declared in enum but not implemented end-to-end as maintainers:
  - `FirstPerKey`
  - `TopNPerGroup`

Note: TypeScript and HTTP management surfaces for MQ lifecycle (create/drop/list/status) were shipped in P16 Epic H (task H.3) and are no longer reserved. See §2.11 for the API reference.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P4 | Epic H tasks/reports (`Task1`, `Task2`, `Task4`, `Task5`, refactor completion) | Core MQ infra, latest/aggregate/filter, table-based storage, incremental updates | FirstPerKey/TopN maintainers and broader API parity not completed | `docs/BACKLOG.md` BL-010, BL-009 |
| P4 | BL-020 report | Auto-routing matcher + planner integration + route telemetry | No cost-based or JOIN-aware routing | `docs/BACKLOG.md` BL-010 |
| P4 | BL-021 report | Unified table namespace and bidirectional name-collision checks | N/A (landed) | `docs/BACKLOG.md` BL-021 complete |
| P4 | R10.4 report | Immediate query visibility for unflushed HRA data | Does not by itself solve post-flush duplicate bug in P11 handoff | `docs/tasks/P11/P11-Fix-R8-MaterializedQueryFlushIntegrationTests-Report.md` |
| P10 | S10 spec/report intent | Standard table subscription path for MQ result tables | Distinct not-ready error code deferred | `docs/BACKLOG.md` BL-053 |
| P11 | R8 fix report (handoff) | Honest documentation of unresolved duplicate-row issue; test-relaxation reverted | Engine-side fix still pending | `docs/BACKLOG.md` BL-019 |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Define/register/drop materialized queries | Yes | No | No | P4 Task1 report, `AoudaEngine.CreateMaterializedQueryAsync` | .NET engine surface is available |
| Latest-per-key materialization | Yes | No | No | P4 Task2 report, `LatestPerKeyApiTests` | Includes initial build and incremental updates |
| Aggregate materialization | Yes | No | No | `AggregateApiTests`, storage maintainer tests | Grouping logic has known BL-019 investigations |
| Filter materialization | Yes | No | No | P4 Task4 report, `FilterApiTests` | Incremental updates handle insert/update/delete paths |
| Async/sync update modes | Yes | No | No | P4 Task5 report, subscription manager code | `Async` default; `Sync` commit-path updates |
| Auto-routing of base queries to MQ | Yes | No | No | BL-020 report, `MaterializedQueryAutoRoutingTests` | Can bypass via `WithDirectScan()` |
| Unified namespace (MQ name == table name) | Yes | No | No | BL-021 report, `ResultTableName`, table listing behavior | Applies to query and subscription paths |
| Subscribe to MQ result streams via table API | Yes | No | No | P10-S10, client streaming tests | No special protocol field required |
| FirstPerKey maintainer/runtime | No | No | Yes | Enum + no dedicated maintainer path/tests | Reserved type only |
| TopNPerGroup maintainer/runtime | No | No | Yes | Enum + no dedicated maintainer path/tests | Reserved type only |
| HTTP/TS API for MQ lifecycle management | No | Yes | No | No server controller/TS surface; .NET only | Workaround: create in .NET, query as table |
| Correct no-duplicate result-table reads after flush | No | Yes | No | P11 R8 handoff report | Known engine bug |

## 2.7 Core concepts and mental model

- `MaterializedQueryDefinition`:
  - Durable definition describing source table, type, config JSON, update mode, storage preferences.
- `MaterializedQueryEntry`:
  - Runtime catalog entry with current state and status metadata.
- Result table:
  - A normal Aouda table produced/maintained for an MQ definition.
  - Under BL-021, its name is the MQ name.
- Maintainer:
  - Pattern-specific logic that builds initial state and applies incremental updates.
- Update mode:
  - `Async`: enqueue and apply later.
  - `Sync`: apply in commit path.
- Routing decision:
  - Planner result that says "serve from MQ result table" or "scan base table."

Invariants:

- Result-table writes must not recursively re-trigger the maintainer pipeline.
- Name collisions are checked in both directions:
  - table create cannot reuse existing MQ name,
  - MQ create cannot reuse existing table name.
- Auto-routing only applies when a matching MQ is found and is ready; otherwise query falls back.

## 2.8 How Aouda implements it

High-level flow:

1. A definition is created (or helper API is called for latest/aggregate/filter).
2. Initial build scans source table and populates result table via maintainer.
3. MQ state transitions to `Ready`.
4. Source-table commits emit row changes.
5. Subscription manager routes changes to maintainers (`Sync` immediate or `Async` queue).
6. Reads use either:
   - direct result-table query (`engine.TableAsync(queryName)`), or
   - auto-routed base query.

Key implementation anchors:

- Definition + status + runtime state:
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryDefinition.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryStatus.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryCatalog.cs`
- Creation and pattern helpers:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
- Result table lifecycle:
  - `src/Aouda.Engine.Storage/Materialized/MaterializedResultTableManager.cs`
- Incremental update path:
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQuerySubscriptionManager.cs`
- Planner routing:
  - `src/Aouda.Engine.Query/MaterializedQueryMatcher.cs`
  - `src/Aouda.Engine.Api/TableQuery.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Create aggregate MQ and reach Ready state

1. Entry point: `AoudaEngine.CreateAggregateQueryAsync(...)`.
2. Validation:
   - validates name/source table/grouping/aggregate definitions,
   - validates numeric source columns for `SUM` and `AVG`,
   - runs BL-021 name-collision checks.
3. State and persistence:
   - registers definition in catalog/store,
   - scans base table,
   - creates result table via `MaterializedResultTableManager`,
   - creates maintainer and registers with catalog + subscription manager,
   - updates state to `Ready` and updates row count.
4. Observability:
   - materialized query counters and pattern counters in `Perf`.
5. Tests:
   - `AggregateApiTests.cs`
   - storage materialized tests (`AggregateMaintainerTests.cs`).

### Walk-through B: Incremental update routing after source write

1. Entry point: source table change event -> `MaterializedQuerySubscriptionManager.OnChangeEvent(...)`.
2. Validation/branching:
   - converts event to row payload and routes through `OnRowsCommitted`,
   - exits early if event table is itself an MQ result table (`_catalog.Exists(tableName)` guard).
3. State mutation:
   - finds maintainers subscribed to source table,
   - if `Sync`, applies immediately,
   - if `Async`, enqueues for background processing.
4. Observability:
   - `SubscriptionUpdatesEnqueued`, `SubscriptionUpdatesProcessed`,
   - `SubscriptionQueueDepth`, `SubscriptionLagMs`, update error/drop counters.
5. Tests:
   - `IncrementalUpdateSubscriptionTests.cs`
   - `tests/Aouda.Engine.Storage.Tests/Materialized/MaterializedQuerySubscriptionManager*.cs`.

### Walk-through C: Auto-routing query to MQ result table

1. Entry point: `TableQuery.ToResultAsync()`.
2. Routing check:
   - unless `WithDirectScan()` was used, `MaterializedQueryMatcher.FindMatch(...)` runs before segment scan.
3. Branching:
   - match found -> execute on result table and capture routed decision,
   - no match or unsupported predicate projection -> record not-routed reason and direct-scan.
4. Observability:
   - `MaterializedQueryRoutes`, `MaterializedQueryRouteMisses`,
   - `MaterializedQueryMatchTimeNs`.
5. Tests:
   - `MaterializedQueryAutoRoutingTests.cs`
   - `MaterializedQueryMatcherTests.cs`.

### Walk-through D: Subscription to MQ via standard table API

1. Entry point:
   - .NET: `client.GetTable(queryName).SubscribeAsync()` pattern in client tests,
   - TypeScript: `client.table(queryName).subscribe(...)`.
2. Protocol path:
   - standard streaming subscribe message with `target = queryName`.
3. Runtime behavior:
   - snapshot sent first,
   - incremental changes follow when result-table rows change.
4. Observability:
   - standard streaming subsystem counters/events, plus MQ update counters.
5. Tests:
   - `tests/Aouda.Client.Tests/Streaming/MaterializedQuerySubscriptionApiTests.cs`
   - `../aouda-client-ts/tests/streaming/subscription.test.ts`.

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Do materialized results use a special hidden path? | Often special object namespaces and API paths | Result is a normal table in unified namespace | One mental model for query + subscribe |
| Can planner routing happen automatically? | Often manual hinting or explicit query rewrite | Matcher-based auto-routing with fallback and direct-scan override | Better default performance without loss of control |
| Is incremental maintenance tied to change events? | Varies; sometimes coarse refresh jobs | Source-table events feed maintainers in sync/async modes | Lower recomputation cost and fresher reads |
| Are hot/cold/flush semantics reused? | Sometimes separate custom storage stack | MQ results use normal table/compaction/hot-cold pipeline | Operational consistency and less feature drift |
| Is implementation status explicit? | Docs often blur planned and shipped | This domain is split into available/planned/reserved with backlog links | Lower risk of assuming unavailable capability |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `MaterializedQueryDefinition.Type` | enum | none (required) | `LatestPerKey`, `FirstPerKey`, `Aggregate`, `Filter`, `TopNPerGroup` | .NET definition/helper APIs | Only `LatestPerKey`/`Aggregate`/`Filter` are shipped end-to-end |
| `MaterializedQueryDefinition.ConfigJson` | JSON string | none (required) | type-specific schema | .NET definition/helper APIs | Serialized pattern config |
| `MaterializedQueryDefinition.UpdateMode` | enum | `Async` | `Async`, `Sync` | .NET definition/helper APIs | Controls commit-path vs queued maintenance |
| `MaterializedQueryDefinition.Storage.StorageTemperature` | enum | type-derived | `Auto`, `HotOnly`, `ColdPreferred` | .NET definition/helper APIs | Optional override; else defaults by type |
| `SubscriptionManagerOptions.MaxLag` | `TimeSpan` | `1s` | positive | Engine wiring | Lag threshold/backpressure signal |
| `SubscriptionManagerOptions.MaxQueueDepth` | int | `10000` | positive | Engine wiring | Async queue upper bound |
| `SubscriptionManagerOptions.ProcessingBatchSize` | int | `100` | positive | Engine wiring | Async queue processing granularity |
| `TableQuery.WithDirectScan()` | query option | off | enabled/disabled per query | .NET query API | Disables auto-routing for a query |
| `TablesController includeSystemTables` | query flag | `false` | `true/false` | HTTP table list request | MQ result tables hidden by default |

Configuration precedence and operational notes:

- Precedence:
  - Explicit definition fields (for type/config/update/storage) override type-derived defaults.
- Dynamic vs restart-required:
  - MQ create/drop/list/status operations are dynamic at runtime.
  - Subscription manager options are engine construction-time concerns.
- Safety-gated:
  - BL-021 name-collision checks prevent ambiguous namespace behavior.
- Deprecated/reserved:
  - No public "deprecated" MQ settings currently; reserved types (`FirstPerKey`, `TopNPerGroup`) are not fully wired.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (create + query + status + routing control)

```csharp
await engine.CreateLatestPerKeyAsync(
    name: "latest_order_per_customer",
    sourceTable: "orders",
    groupByColumn: "customer_id",
    orderByColumn: "created_at",
    descending: true);

var status = await engine.GetMaterializedQueryStatusAsync("latest_order_per_customer");
var routed = await (await engine.TableAsync("orders"))
    .Where("customer_id", "eq", "c-1")
    .ToResultAsync();

var direct = await (await engine.TableAsync("orders"))
    .WithDirectScan()
    .Where("customer_id", "eq", "c-1")
    .ToResultAsync();
```

Expected result: MQ is created and eventually `Ready`; default query may route to MQ result, while direct-scan bypasses routing.

Common mistake: assuming `CreateMaterializedQueryAsync` alone builds maintainers for all enum types; only implemented pattern paths are fully functional.

### TypeScript example (lifecycle management via `client.materializedQueries`)

The TypeScript management API was shipped in P16 (Epic H, task H.3). Use `client.materializedQueries` to create, drop, list, check status, and query MQ results.

```typescript
import { createAoudaClient } from "@aouda/client";
import { MaterializedQueryType } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
});

// Create a latest-per-key MQ (type 1 = LatestPerKey)
await client.materializedQueries.create({
  name: "latest_order_per_customer",
  sourceTable: "orders",
  type: 1,
  config: {
    groupByColumn: "customer_id",
    orderByColumn: "created_at",
    descending: true,
  },
});

// Check status (state: 0=Building, 1=Ready, 2=Rebuilding, 3=Error)
const status = await client.materializedQueries.status("latest_order_per_customer");
console.log(status.state, status.rowCount);

// List all materialized queries for the database
const all = await client.materializedQueries.list();

// Execute a query directly against the MQ result set
const result = await client.materializedQueries.query("latest_order_per_customer");
console.log(result.rows);

// Drop the MQ and its result table
await client.materializedQueries.drop("latest_order_per_customer");
```

Expected result: MQ is created, transitions to `state: 1` (Ready), and the result set is queryable directly or as a normal table.

The `MaterializedQueryType` constant object maps names to their numeric wire values: `{ LatestPerKey: 1, FirstPerKey: 2, Aggregate: 3, Filter: 4, TopNPerGroup: 5 }`. Only `LatestPerKey` (1), `Aggregate` (3), and `Filter` (4) are fully shipped end-to-end. Passing `FirstPerKey` (2) or `TopNPerGroup` (5) creates a definition record but no maintainer is wired.

### TypeScript example (query and subscribe MQ result as table)

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
});

const mqResult = await client
  .table("latest_order_per_customer")
  .where("customer_id", "=", "c-1")
  .execute();

const sub = client.table("latest_order_per_customer").subscribe({
  onSnapshot: (rows) => console.log("snapshot", rows.length),
  onChange: (evt) => console.log("change", evt.op, evt.version),
});
```

Expected result: query and subscription both work through regular table APIs.

Common mistake: the dedicated `client.materializedQueries.*` API is for lifecycle management (create/drop/list/status); reading result rows still uses the normal table query or subscribe path, or `client.materializedQueries.query(name)` for a direct snapshot read.

### HTTP / protocol examples

**MQ lifecycle management (shipped in P16 SH2):**

```http
POST /api/databases/appdb/materialized-queries
Content-Type: application/json

{
  "version": 1,
  "name": "latest_order_per_customer",
  "sourceTable": "orders",
  "type": 1,
  "configJson": "{\"groupByColumn\":\"customer_id\",\"orderByColumn\":\"created_at\",\"descending\":true}"
}
```

```http
GET /api/databases/appdb/materialized-queries
```

```http
GET /api/databases/appdb/materialized-queries/latest_order_per_customer
```

```http
DELETE /api/databases/appdb/materialized-queries/latest_order_per_customer
```

**Query MQ result set directly:**

```http
POST /api/databases/appdb/materialized-queries/latest_order_per_customer/query
Content-Type: application/json

{}
```

**Query MQ result table via standard query endpoint (same as normal table):**

```http
POST /api/databases/appdb/query
Content-Type: application/json

{
  "database": "appdb",
  "table": "latest_order_per_customer",
  "where": {
    "and": [
      { "column": "customer_id", "op": "eq", "value": "c-1" }
    ]
  },
  "limit": 100
}
```

**Streaming subscribe (same as normal target):**

```json
{
  "type": "subscribe",
  "id": "sub-1",
  "target": "latest_order_per_customer"
}
```

Expected result: snapshot then changes on the same target name.

Common mistake: expecting a protocol field like `target_kind = materialized_query` (not part of shipped design).

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Create latest-per-key MQ | `CreateLatestPerKeyAsync(...)` | `client.materializedQueries.create(spec)` with `type: 1` | `POST /api/databases/{db}/materialized-queries` | Implemented | TS and HTTP management surfaces shipped in P16 |
| Create aggregate MQ | `CreateAggregateQueryAsync(...)` | `client.materializedQueries.create(spec)` with `type: 3` | Same endpoint | Implemented | TS and HTTP shipped in P16 |
| Create filter MQ | `CreateFilterQueryAsync(...)` | `client.materializedQueries.create(spec)` with `type: 4` | Same endpoint | Implemented | TS and HTTP shipped in P16 |
| Generic create/drop/list/status | `CreateMaterializedQueryAsync`, `DropMaterializedQueryAsync`, `ListMaterializedQueriesAsync`, `GetMaterializedQueryStatusAsync` | `client.materializedQueries.create/drop/list/status` | `GET/POST/DELETE /api/databases/{db}/materialized-queries[/{name}]` | Implemented | Full TS + HTTP surface shipped in P16 |
| Query MQ results | `TableAsync(queryName)` and `QueryMaterializedAsync(...)` | `client.table(queryName).execute()` or `client.materializedQueries.query(name)` | `POST /api/databases/{db}/query` or `POST /api/databases/{db}/materialized-queries/{name}/query` | Implemented | Two paths: normal table query or dedicated MQ query endpoint |
| Subscribe MQ results | `GetTable(queryName).SubscribeAsync()` pattern in client tests | `client.table(queryName).subscribe(...)` | standard `subscribe` message `target=queryName` | Implemented | No MQ-specific target type |
| Auto-routing base query to MQ | `TableQuery` matcher + `WithDirectScan()` | Missing explicit control | Not exposed as route flag | Partial | Routing logic is server-side engine behavior |
| Explain routing decision | `ExplainRoutingAsync(...)` | Missing | Missing | Partial | .NET diagnostic API only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Distinct not-ready subscription error | No `MATERIALIZED_QUERY_NOT_READY` protocol/server code | Current `TABLE_NOT_FOUND` handling | `docs/BACKLOG.md` BL-053 | Low |
| JOIN-based MQ definitions | No query/API support for JOIN materialization | Build denormalized source table first | `docs/BACKLOG.md` BL-010 (depends BL-009) | Medium |
| Rich routed-query controls in TS | No TS equivalent of .NET `WithDirectScan()` | Use query shape changes / backend controls | Future query API parity work | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run baseline MQ (latest-per-key)

When to use:
- You need fast "latest row per entity" reads.

Steps:
1. Create base table `orders`.
2. Call `CreateLatestPerKeyAsync("latest_order_per_customer", "orders", "customer_id", "created_at")`.
3. Insert base rows.
4. Query `latest_order_per_customer` as a normal table.

Expected checks:
- MQ status transitions to `Ready`.
- Query result has one row per `customer_id`.
- Reads come back without building aggregations at read time.

### Scenario 2: Production-safe rollout with async lag control

When to use:
- Write-heavy workload where synchronous maintenance would increase commit latency.

Steps:
1. Create MQ with default `UpdateMode.Async`.
2. Monitor `SubscriptionQueueDepth` and `SubscriptionLagMs`.
3. If lag is unacceptable, evaluate switching selected queries to `Sync` mode.

Expected checks:
- Write path latency remains stable with async.
- Queue/lag counters stay within acceptable limits.
- Result table converges quickly after bursts.

### Scenario 3: Real-time subscriber on MQ result table

When to use:
- Dashboard/notification workload over precomputed result stream.

Steps:
1. Start `client.table(queryName).subscribe(...)`.
2. Confirm initial snapshot arrives.
3. Insert/update source-table rows.
4. Ensure maintainer updates are flushed (`FlushSubscriptionsAsync` in .NET integration path).

Expected checks:
- Subscriber receives snapshot then incremental changes.
- No need for separate MQ-specific subscription protocol.
- If MQ/result table is missing, subscriber gets normal table-not-found behavior.

## 2.13 Operations and observability

Monitor first:

- Lifecycle and pattern activity:
  - `MaterializedQueriesCreated`, `MaterializedQueriesDropped`, `MaterializedQueriesActive`
  - `LatestPerKeyQueries`, `AggregateQueries`, `FilterQueries`
- Incremental pipeline health:
  - `SubscriptionUpdatesEnqueued`, `SubscriptionUpdatesProcessed`, `SubscriptionDroppedUpdates`, `SubscriptionUpdateErrors`
  - `SubscriptionQueueDepth`, `SubscriptionLagMs`
- Routing outcomes:
  - `MaterializedQueryRoutes`, `MaterializedQueryRouteMisses`, `MaterializedQueryMatchTimeNs`

Recovery/restart expectations:

- Definitions are persisted and restored through catalog/store.
- Result tables are normal catalog tables and survive restart.
- Behavior under restart has coverage, but unresolved flush duplicate bug must be considered in production verification.

Suggested tuning sequence:
1. Start with default async mode and observe lag/queue metrics.
2. Tune queue depth/batch size only if lag remains sustained.
3. Use `Sync` mode selectively for strict freshness paths.

| Question | Practical answer |
|---|---|
| How to confirm routing is helping? | Watch `MaterializedQueryRoutes` rising with stable miss rate |
| How to detect update backlog? | `SubscriptionQueueDepth` and `SubscriptionLagMs` rising together |
| How to hide MQ internals from app table listings? | Keep `includeSystemTables=false` (default) on list-tables calls |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Query against MQ name returns table not found | MQ not created, not ready, or dropped; same error shape as missing table | Verify MQ status in .NET host and table presence in catalog |
| Base query does not auto-route | No compatible MQ, MQ not ready, or predicate/shape mismatch | Use `ExplainRoutingAsync` and inspect matcher conditions |
| MQ result update lag spikes | Async queue pressure or maintainer exceptions | Check queue/lag/error counters and consider `Sync` for critical flows |
| Duplicate rows after compaction/flush on MQ result table | Known unresolved engine bug from P11 R8 | Track/fix through P11 handoff; do not relax correctness assertions |
| Attempted FirstPerKey/TopN definition fails or is unusable | Type reserved but no full maintainer path | Use supported patterns only (`LatestPerKey`, `Aggregate`, `Filter`) |
| Subscription loops or floods unexpectedly | Incorrect result-table re-routing would cause loops, but guard prevents this | Confirm `_catalog.Exists(tableName)` guard remains intact and unmodified |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Engine API MQ feature suites | `dotnet test tests/Aouda.Engine.Api.Tests --no-build --filter "FullyQualifiedName~MaterializedQueryApiTests|FullyQualifiedName~LatestPerKeyApiTests|FullyQualifiedName~AggregateApiTests|FullyQualifiedName~FilterApiTests|FullyQualifiedName~MaterializedQueryAutoRoutingTests|FullyQualifiedName~IncrementalUpdateSubscriptionTests" --verbosity minimal` | Pass (`99/99`) | 2026-03-31 | Covers create/build/update/routing flows |
| Storage-layer MQ tests | `dotnet test tests/Aouda.Engine.Storage.Tests --no-build --filter "FullyQualifiedName~Materialized" --verbosity minimal` | Pass (`267/267`) | 2026-03-31 | Covers maintainers/catalog/store/subscription manager internals |
| Query matcher/routing logic | `dotnet test tests/Aouda.Engine.Query.Tests --no-build --filter "FullyQualifiedName~MaterializedQueryMatcherTests" --verbosity minimal` | Pass (`21/21`) | 2026-03-31 | Confirms matcher contract and routing eligibility logic |
| .NET client streaming MQ subscription tests | `dotnet test tests/Aouda.Client.Tests --no-build --filter "FullyQualifiedName~MaterializedQuerySubscriptionApiTests" --verbosity minimal` | Pass (`2/2`) | 2026-03-31 | Confirms standard table subscription path for MQ result names |
| TypeScript streaming subscription tests | `npm test -- tests/streaming/subscription.test.ts` (in `../aouda-client-ts`) | Pass (`5/5`) | 2026-03-31 | Confirms TS subscribe flow behavior and message handling |
| Known unresolved correctness issue | `tests/Aouda.Engine.Api.Tests/MaterializedQueryFlushIntegrationTests.cs` (tracked via P11 report) | Fail (known bug) | 2026-03-31 | Duplicate-row bug after flush; engine fix pending |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Core lifecycle (create/drop/status/list) | `MaterializedQueryApiTests.cs`, `CompactionIntegrationTests.cs` | Pass | Strong | Includes restart/drop and status behavior |
| Latest-per-key pattern | `LatestPerKeyApiTests.cs`, `LatestPerKeyMaintainerTests.cs` | Pass | Strong | Includes incremental behavior and rebuild-related checks |
| Aggregate pattern | `AggregateApiTests.cs`, `AggregateMaintainerTests.cs` | Pass | Medium/Strong | Strong on core behavior; BL-019 signals deeper grouping edge cases |
| Filter pattern | `FilterApiTests.cs`, `FilterMaintainerTests.cs` | Pass | Strong | Includes insert/update/delete maintenance paths |
| Subscription manager queue/routing | `IncrementalUpdateSubscriptionTests.cs`, `MaterializedQuerySubscriptionManager*.cs`, `MaterializedQueryUpdateQueueTests.cs` | Pass | Strong | Includes sync/async routing and queue mechanics |
| Auto-routing and matcher | `MaterializedQueryAutoRoutingTests.cs`, `MaterializedQueryMatcherTests.cs` | Pass | Strong | Includes route/miss conditions and bypass behavior |
| Streaming subscription to MQ result | `MaterializedQuerySubscriptionApiTests.cs`, `../aouda-client-ts/tests/streaming/subscription.test.ts` | Pass | Medium | Good protocol-path coverage; TS tests are transport-level, not full server E2E |
| Flush correctness (no duplicates) | `MaterializedQueryFlushIntegrationTests.cs` | Fail (known bug) | Weak (currently red) | P11 handoff explicitly tracks unresolved engine issue |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No passing guardrail test for "no duplicate rows after flush" | Correctness regression risk on production read paths | Keep strict `MaterializedQueryFlushIntegrationTests` assertions and fix engine path | High |
| No explicit end-to-end tests for reserved types (`FirstPerKey`, `TopNPerGroup`) failing clearly | Users can infer support from enum values | Add API validation tests that reject or clearly mark unsupported types | High |
| No TS parity tests for route-control semantics | TS users cannot intentionally bypass routing like .NET `WithDirectScan()` | Add tracked parity tests once API is introduced | Medium |
| No HTTP API contract tests for MQ lifecycle endpoints | Management API gap remains opaque | Add server contract tests when endpoints are implemented | Medium |
| Limited long-run stress tests for async queue saturation | Backpressure behavior can regress under bursty writes | Add deterministic load test asserting queue/lag/drop/error counters | Medium |

## 2.18 Known gaps and undone work

- BL-019 (open):
  - MQ result-table query path can return duplicate rows after flush/compaction in specific scenarios.
  - User impact: strict correctness expectations for some flush-integration scenarios are not yet met.
- BL-010 (open, depends BL-009):
  - JOIN-based materialized queries are not supported.
  - User impact: multi-table precomputation requires manual denormalization or other workarounds.
- BL-053 (open):
  - No distinct error code for MQ-not-ready subscriptions (`TABLE_NOT_FOUND` is used).
  - User impact: clients cannot distinguish "table missing" vs "MQ exists but not ready" from error code alone.
- Reserved type support:
  - `FirstPerKey` and `TopNPerGroup` are represented in type enums but not fully shipped as end-to-end capabilities.
- Surface parity gap:
  - MQ lifecycle management is currently .NET engine-centric; there is no first-class HTTP/TypeScript management API.

## 2.19 References

- ADRs:
  - `docs/decisions/0015-materialized-queries.md`
  - `docs/decisions/0020-real-time-streaming.md`
- Tasks/reports:
  - `docs/tasks/P4/P4-EpicH-MaterializedQueries-Tasks.md`
  - `docs/tasks/P4/P4-EpicH-Task1-MaterializedQueryInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicH-Task2-LatestPerKeyPattern-Report.md`
  - `docs/tasks/P4/P4-EpicH-Task4-FilterPattern-Report.md`
  - `docs/tasks/P4/P4-EpicH-Task5-IncrementalUpdateSubscription-Report.md`
  - `docs/tasks/P4/P4-EpicH-Refactoring-Completion.md`
  - `docs/tasks/P4/P4-EpicH-BL020-QueryPlannerAutoRouting-Report.md`
  - `docs/tasks/P4/P4-EpicH-BL021-UnifiedTableNamespace-Report.md`
  - `docs/tasks/P4/P4-EpicH-R10.4-QueryUnflushedHraTableData-Report.md`
  - `docs/tasks/P10/P10-S10-MaterializedQuerySubscriptions.md`
  - `docs/tasks/P11/P11-Fix-R8-MaterializedQueryFlushIntegrationTests-Report.md`
- Backlog:
  - `docs/BACKLOG.md` (BL-019, BL-009, BL-010, BL-053, BL-003)
- Code paths:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
  - `src/Aouda.Engine.Api/TableQuery.cs`
  - `src/Aouda.Engine.Query/MaterializedQueryMatcher.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryDefinition.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryStatus.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQueryCatalog.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedQuerySubscriptionManager.cs`
  - `src/Aouda.Engine.Storage/Materialized/MaterializedResultTableManager.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Engine.Diagnostics/Perf.cs`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/streaming/subscription.ts`
  - `../aouda-client-ts/src/tables.ts`
- Tests:
  - `tests/Aouda.Engine.Api.Tests/MaterializedQueryApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/LatestPerKeyApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/AggregateApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/FilterApiTests.cs`
  - `tests/Aouda.Engine.Api.Tests/MaterializedQueryAutoRoutingTests.cs`
  - `tests/Aouda.Engine.Api.Tests/IncrementalUpdateSubscriptionTests.cs`
  - `tests/Aouda.Engine.Api.Tests/MaterializedQueryFlushIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Materialized/`
  - `tests/Aouda.Engine.Query.Tests/MaterializedQueryMatcherTests.cs`
  - `tests/Aouda.Client.Tests/Streaming/MaterializedQuerySubscriptionApiTests.cs`
  - `../aouda-client-ts/tests/streaming/subscription.test.ts`

## 2.20 What is missing from this document? (meta completeness)

_Updated 2026-04-08 after P16 completion._

- This document does not include full serialized `ConfigJson` schema examples for every pattern permutation; it documents the callable surfaces and behavior boundaries.
- ~~This document does not claim HTTP/TypeScript lifecycle APIs for MQ management because those surfaces are not shipped.~~ — ✅ **Resolved (P16 Epic H, task H.3)**: TypeScript client now provides `client.materializedQueries.list()`, `.create(spec)`, `.drop(name)`, `.status(name)`, `.query(name, queryOptions)`. Full reference: `docs/dev/Functionality-TypeScript-Client.md` §13. Server-side routes for materialized query endpoints implemented as part of P16 SH2.
- ~~Studio has no materialized query UI~~ — ✅ **Resolved (P16 Epic D, task D.16)**: Studio materialized queries browser lists queries with freshness status, allows querying results and dropping queries. See `docs/dev/Functionality-Studio.md` §11.
- This document intentionally keeps the P11 duplicate-row bug visible as unresolved; once fixed, `2.4`, `2.15`, `2.16`, and `2.18` must be updated together.
