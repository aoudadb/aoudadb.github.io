---
title: "Query Execution"
nav_order: 1
parent: "Guides"
---

# Aouda Functionality: Query Execution and Optimization

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-03-31

Coverage phases: P3, P4, P7, P12
Primary task folders: `docs/tasks/P3/`, `docs/tasks/P4/`, `docs/tasks/P7/`, `docs/tasks/P12/`
Primary ADRs: `docs/decisions/0015-materialized-queries.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-RealTime-Streaming.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How do I query Aouda today?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.15 Verification ledger`
- `2.16 Test coverage matrix`

---

## 2.1 Why this functionality exists

Aouda query execution exists to make one query contract work consistently across hot, cold, and mixed segment states without exposing storage complexity to users.

- User problem solved:
  - Query current data even when some rows are still in HRA and others are already compacted to cold segments.
  - Keep query behavior stable as data moves between hot/cold/delta storage.
  - Expose a single API family across server HTTP, .NET client, and TypeScript client.
- Operational outcomes:
  - Predictable defaults (`columnar` format, bounded limits, strict validation).
  - Observable execution through performance counters and query stats.
  - Incremental optimization through pruning and vectorized paths without API changes.
- Scope boundaries:
  - This document covers execution and optimization for single-table query surfaces.
  - It does not claim full public JOIN support in fluent SDKs.
  - Dedicated HTTP count endpoint is `POST /api/databases/{db}/query/count` (aggregate path); .NET `RemoteTableQuery.CountAsync` uses it for remote counts.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What defaults apply if I do nothing? | `2.3 Defaults and zero-config behavior` |
| What is shipped vs planned vs reserved? | `2.4 Availability status` |
| Which phase delivered which capability? | `2.5 Phase coverage matrix` |
| End-to-end capability completeness | `2.6 Capability coverage matrix` |
| Runtime concepts and invariants | `2.7 Core concepts and mental model` |
| How query execution is implemented | `2.8 How Aouda implements it` |
| Full settings and request surface | `2.10 Configuration and settings reference` |
| API examples and known API gaps | `2.11 API and CLI coverage reference` |
| Which paths are verified now | `2.15 Verification ledger`, `2.16 Test coverage matrix` |
| What remains undone | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer (.NET/TS) | `2.3`, `2.11`, `2.12`, `2.14` |
| API consumer (HTTP/REST) | `2.3`, `2.10`, `2.11`, `2.14` |
| Operator/SRE | `2.10`, `2.13`, `2.14`, `2.15` |
| Engine contributor | `2.6`, `2.8`, `2.8.1`, `2.16`, `2.17` |
| SDK maintainer | `2.11` (especially missing API matrix), `2.18` |

### Source map

| Evidence type | Primary sources |
|---|---|
| Phase/task reports | `docs/tasks/P3/P3-Task6-QueryEngineHotColdIntegration-Report.md`, `docs/tasks/P4/P4-EpicA-Task2-RestQueryApi-Report.md`, `docs/tasks/P4/P4-EpicG-BL007-QueryEngineDeltaIntegration-Report.md`, `docs/tasks/P4/P4-EpicH-BL016-QueryEngineDataDecoding-Report.md`, `docs/tasks/P4/P4-EpicH-BL017-TableQueryPredicateFiltering-Report.md`, `docs/tasks/P4/P4-EpicH-R10.4-QueryUnflushedHraTableData-Report.md`, `docs/tasks/P7/C2-QueryCorrectness-Summary.md`, `docs/tasks/P12/BL-038-QueryEngine-RowWindow-BatchContract-Report.md`, `docs/tasks/P12/BL-038A-Remove-Legacy-QueryEngine-ExecuteAsync-TupleContract-Report.md` |
| Runtime code | `src/Aouda.Server/Controllers/QueryController.cs`, `src/Aouda.Server/Query/QueryTranslator.cs`, `src/Aouda.Engine.Api/TableQuery.cs`, `src/Aouda.Engine.Storage/Query/QueryEngine.cs`, `src/Aouda.Engine.Storage/Query/RowFilterEngine.cs`, `src/Aouda.Engine.Storage/Query/ParallelSegmentScanner.cs`, `src/Aouda.Engine.Storage/Query/QueryBatch.cs`, `src/Aouda.Engine.Diagnostics/Perf.cs` |
| Protocol/limits | `src/Aouda.Protocol/Messages.cs`, `src/Aouda.Protocol/ProtocolConstants.cs` |
| Client surfaces | `src/Aouda.Client/RemoteTableQuery.cs`, `src/Aouda.Client/RemoteConditionBuilder.cs`, `src/Aouda.Client/Internal/QueryMessageBuilder.cs`, `aouda-client-ts/src/query-builder.ts`, `aouda-client-ts/src/types.ts` |
| Gap tracking | `docs/BACKLOG.md` (`BL-003`, `BL-009`, `BL-010`, `BL-044`) |

## 2.3 Defaults and zero-config behavior

If you issue a query without custom tuning, Aouda applies protocol defaults and engine safeguards.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| HTTP query response format | `columnar` | Lower payload overhead by default; row format is opt-in (`format=rows`). |
| `limit` when omitted/negative | `1000` (`ProtocolConstants.DefaultLimit`) | Prevents accidental unbounded results. |
| `limit` upper bound | `10000` (`ProtocolConstants.MaxLimit`) | Oversized client limits are capped server-side. |
| `limit = 0` | Unlimited | Still valid on `/query` for unbounded reads; remote `.CountAsync()` uses `/query/count` instead. |
| `offset` | `0` | No row skipping unless explicitly requested. |
| `orderBy` max columns | `8` (`ProtocolConstants.MaxOrderByColumns`) | Prevents unbounded sort-key complexity in requests. |
| `where` omitted | No predicate filtering | Full scan path across discovered segments. |
| `crossPartitionAccess` | `false` | Partition enforcement remains active unless explicitly bypassed by authorized callers. |
| Read preference | Default parse behavior when omitted | Server validates role/visibility compatibility before query execution. |

## 2.4 Availability status (implementation honesty)

### Available now

- Server query endpoint: `POST /api/databases/{db}/query` with protocol validation and typed error payloads.
- Server count endpoint: `POST /api/databases/{db}/query/count` — same request body shape as `/query` (where/cross-partition); `limit`/`offset`/`orderBy`/`select` ignored for translation; returns `CountResult` with aggregate stats.
- `columnar` and `rows` output formats, with explicit format validation.
- Fluent query APIs:
  - Engine-side `TableQuery` (`Where`, `Select`, `Skip`, `Limit`, `OrderBy`, `ThenBy`, aggregates).
  - .NET remote `RemoteTableQuery` with ordering and cross-partition flag propagation.
  - TypeScript `TableQuery` with immutable chaining and operator mapping.
- Hot/cold query execution through one path:
  - Unflushed HRA visibility via virtual hot segment projection.
  - Cold decode path with row-window contract (`QueryBatch`).
  - Predicate-aware cold execution via `RowFilterEngine` (row-aligned semantics).
- Optimization primitives in execution path:
  - Page pruning (`PagePruner`) including multi-column pruning.
  - Bloom-filter-assisted page skipping when available.
  - Parallel multi-segment scanning with global offset/limit handling.
  - Segment-level pruning via cluster stats where available.
- Delta-segment read support integrated into query path.
- Materialized-query auto-routing hooks in `TableQuery`/matcher path (when a compatible materialized table exists).

### Planned / proposed

- Full SDK adoption of nested `WhereClause.Groups` builders (backlog `BL-044`).
- Max nesting depth guardrails in `QueryTranslator.ValidateWhereClause` (backlog `BL-044`).
- Fluent JOIN API exposure (`BL-009`) and subsequent materialized-query JOIN support (`BL-010`).

### Reserved / not yet wired

- Public, stable nested-group builder parity across all client SDKs (wire supports `Groups`; SDK ergonomics are incomplete).
- End-to-end JOIN workflow through fluent query builders and materialized query definitions.
- Hard server-side safety policy for arbitrarily deep boolean recursion in request payloads.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P3 | `P3-Task6-QueryEngineHotColdIntegration-Report.md`, `P7-BL025-CrossColumnPagePruning-Report.md` | Hot/cold-aware execution integration, aggregate path alignment, query performance counters, and restored cross-column cold pruning | Advanced optimization maturity remains iterative | — |
| P4 | `P4-EpicA-Task2-RestQueryApi-Report.md`, `P4-EpicG-BL007-QueryEngineDeltaIntegration-Report.md`, `P4-EpicH-BL016-QueryEngineDataDecoding-Report.md`, `P4-EpicH-BL017-TableQueryPredicateFiltering-Report.md`, `P4-EpicH-R10.4-QueryUnflushedHraTableData-Report.md` | REST query API, delta integration, cold decode correctness fix, row-filter predicate correctness, unflushed HRA query visibility | Fluent JOINs still deferred | `BL-009`, `BL-010` |
| P7 | `C2-QueryCorrectness-Summary.md` | Correctness hardening for mixed hot/cold query results, pruning alignment fixes, race-safe query visibility through freeze-and-swap model | Some scenario tightening is optional follow-up | (documented in P7 summary) |
| P12 | `BL-038-QueryEngine-RowWindow-BatchContract-Report.md`, `BL-038A-Remove-Legacy-QueryEngine-ExecuteAsync-TupleContract-Report.md` | QueryEngine standardized on explicit `QueryBatch` contract and removed legacy tuple path | No major deferred items in this specific refactor scope | N/A |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| REST query endpoint with validation and typed errors | Yes | No | No | P4 EpicA report + `QueryController` + `QueryIntegrationTests` | Supports request/body validation and protocol error mapping. |
| Fluent projection/filter/pagination/ordering in engine API | Yes | No | No | `TableQuery` + storage tests + API tests | Immutable chaining with ordering and pagination behavior. |
| .NET remote fluent ordering/query parity | Yes | No | No | `RemoteTableQuery` + client wiring | Includes `OrderBy`, `ThenBy`, `WithCrossPartitionAccess`. |
| TypeScript fluent ordering/query parity | Yes | Partial | No | `query-builder.ts` + `query-builder.test.ts` | Core parity present; nested group API not exposed. |
| Nested boolean groups over HTTP (`WhereClause.Groups`) | Yes | No | No | `Messages.cs` + `QueryTranslator` recursion | Server/wire supports nested groups. |
| Nested boolean groups in .NET client builders | No | Yes | No | `RemoteConditionBuilder` + `QueryMessageBuilder` | Groups flattened; nested composition not fully emitted. |
| Nested boolean groups in TypeScript builder | No | Yes | No | `aouda-client-ts/src/types.ts` + `query-builder.ts` | `WhereClause` has `and/or` only. |
| Hot + cold + unflushed HRA unified visibility | Yes | No | No | P4 R10.4 report + `TableQuery` + P7 summary tests | Virtual hot segment merged into query execution paths. |
| Delta segment query inclusion | Yes | No | No | P4 BL007 report + `QueryEngine` page reader delta branch | Transparent to callers. |
| Page pruning and multi-column pruning | Yes | Partial | No | `QueryEngine`, `RowFilterEngine`, `PagePruner` usage | Ongoing tuning and backlog refinement remain. |
| Bloom-filter-assisted pruning | Yes | Partial | No | `RowFilterEngine` bloom path + perf counters | Requires bloom index availability and equality predicates. |
| Parallel multi-segment scanning | Yes | No | No | `ParallelSegmentScanner` + perf counters | Global offset/limit handled after merge/materialization. |
| Dedicated count API endpoint | Yes (`/query/count`) | No | Yes | Implemented (2026-04-04, `BL-026`) | TS client still on query path until updated. |
| Fluent JOIN query support | No | No | Yes | Backlog + absence in fluent APIs | Internal planner support exists but not exposed in fluent APIs. |

## 2.7 Core concepts and mental model

- `QueryMessage`: the wire-level request contract (`database`, `table`, `select`, `where`, `orderBy`, `offset`, `limit`, `crossPartitionAccess`).
- `TableQuery`: engine-facing immutable builder used by server translation and direct engine consumers.
- `QueryTranslator`: server bridge from wire DTO to `TableQuery`; enforces defaults and limits.
- `QueryEngine`: per-segment execution and decode pipeline; emits row-window aligned batches.
- `QueryBatch`: canonical internal result unit (row count + per-column arrays + optional validity bitmaps).
- `RowFilterEngine`: specialized predicate path for row-aligned filtering over cold/hot segments.
- `ParallelSegmentScanner`: orchestrator for multi-segment parallel execution with global offset/limit semantics.
- Optimization layers:
  - page-level pruning (min/max and joint windows),
  - optional bloom index pruning,
  - segment-level pruning where stats are available,
  - parallel segment execution.

Key invariants:

- Query results should be correct regardless of temperature state (hot-only, cold-only, mixed, plus unflushed HRA).
- Protocol defaults and limits are centralized (for consistency across clients).
- Request validation occurs before heavy execution work.
- `ThenBy()` requires `OrderBy()` first in both .NET and TypeScript APIs.

## 2.8 How Aouda implements it

At a high level:

1. HTTP receives `QueryMessage` in `QueryController.ExecuteQuery`.
2. `QueryTranslator.Validate` performs request-level checks (database/table presence, `offset`, operators, order-by constraints, recursive `Groups` validation).
3. Security layers run (PLS/RLS and optional cross-partition rate limiting/auditing).
4. `QueryTranslator.Translate` builds an immutable `TableQuery` chain with:
   - projection,
   - predicate,
   - pagination defaults/caps,
   - ordering,
   - cross-partition flag.
5. `TableQuery` resolves schema/segments and selects execution path:
   - materialized table routing path when matcher hits,
   - row-filter path for predicate-correct cold/hot execution,
   - parallel segment path for materialized or aggregate execution.
6. Storage query execution uses `QueryEngine` / `RowFilterEngine` over discovered segment IDs, including delta segments.
7. Results are returned as columnar by default and converted to row format when requested.

Runtime notes:

- `limit=0` on `/query` is interpreted as no cap for full reads.
- For unflushed writes, `TableQuery` can synthesize a virtual hot segment from HRA snapshots so queries see current data before flush.
- `QueryEngine` increments decode/scan/perf counters and emits `QueryBatch` objects to keep row windows aligned across projected columns.
- `ParallelSegmentScanner` applies global offset/limit after segment execution to preserve query semantics.

## 2.8.1 Critical path walk-throughs (implementation-level)

### Path A: HTTP query request -> translated query -> response

1. Entry point: `QueryController.ExecuteQuery`.
2. Validates format (`columnar`/`rows`), database/path consistency, and query payload.
3. Applies authorization and partition security enforcement.
4. Translates to `TableQuery` with normalized defaults (`DefaultLimit`, `MaxLimit`, `MaxOrderByColumns`).
5. Executes and returns `ColumnarResult` or row-converted response.
6. Tests: `tests/Aouda.Server.Tests/QueryIntegrationTests.cs`, `tests/Aouda.Server.Tests/QueryTranslatorTests.cs`.

### Path B: Predicate query on cold/mixed segments

1. Entry point: `TableQuery.ToColumnarAsync` (or list path) with predicate set.
2. Route selection enters `ExecuteWithRowFilterAsync` for row-aligned filtering.
3. `RowFilterEngine` builds page windows and applies:
   - min/max pruning,
   - optional bloom pruning,
   - decode only required row ranges.
4. Validity bitmaps and deletion masks are preserved through decode/projection.
5. Tests: `tests/Aouda.Engine.Storage.Tests/RowFilterEngineColdValidityTests.cs`, `tests/Aouda.Engine.Storage.Tests/RowFilterEngineDriverPruningTypeTests.cs`, `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`.

### Path C: Aggregate/count with mixed hot+cold and unflushed rows

1. Entry point: `TableQuery.AggregateAsync` or client-side `Count`.
2. Discovery includes persisted segments plus virtual hot segment from HRA snapshot.
3. Aggregate request sent to `ParallelSegmentScanner.ExecuteAggregatesAsync`.
4. Merged aggregate result reflects both cold and current hot state.
5. Tests/evidence: P4 R10.4 report + `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`.

### Path D: QueryEngine row-window contract

1. Entry point: single-segment execute path in `QueryEngine.ExecuteAsync`.
2. Engine decodes columns and yields explicit `QueryBatch` records.
3. Legacy tuple contract removed; consumers depend on batch alignment guarantees.
4. Tests/evidence: P12 BL-038/BL-038A reports + `tests/Aouda.Engine.Storage.Tests/QueryEngineRowWindowBatchTests.cs`.

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Do I need separate APIs for hot vs cold data? | Often yes (cache + store split) | One query surface across hot/cold/unflushed HRA | Simpler app code and fewer consistency surprises. |
| Is pruning/optimization user-managed? | Often index/query-hint heavy | Optimization is mostly internal (pruning, bloom, parallel scan) | Lower tuning burden for common workloads. |
| Are count semantics an independent API today? | Yes (HTTP `/query/count`; .NET `CountAsync`) | TS client may still use full query | C# path avoids columnar materialization. |
| Can query routing exploit materialized tables automatically? | Usually manual endpoint/view selection | Matcher-based auto-routing in query path | Potential speedup without endpoint changes. |
| Do clients and server share one protocol contract? | Sometimes fragmented | Shared protocol DTOs + translator + SDK mappers | Predictable behavior across HTTP/.NET/TS surfaces. |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `format` | Query parameter | `columnar` | `columnar`, `rows` | HTTP request (`/query`) | Invalid values return `InvalidFormat`. |
| `readPreference` | Query parameter / header | Parsed default | replication preference values | HTTP request (`readPreference` or `X-Read-Preference`) | Query parameter takes precedence over header. |
| `database` | Request body field | None | existing database name | `QueryMessage` | Must match URL path database. |
| `table` | Request body field | None | existing table name | `QueryMessage` | Required. |
| `select` | Request body field | null (all columns) | list of column names | `QueryMessage` | Empty/null means full projection. |
| `where.and` / `where.or` / `where.groups` | Request body field | null | valid conditions | `QueryMessage.Where` | Server supports recursive `groups`. |
| `orderBy` | Request body field | null | up to 8 columns | `QueryMessage` | Duplicate columns rejected by validator. |
| `offset` | Request body field | `0` | `>=0` | `QueryMessage` | Negative rejected. |
| `limit` | Request body field | `1000` effective when omitted/negative | `0` or positive; capped at `10000` | `QueryMessage` -> `QueryTranslator` | `0` means unlimited. |
| `crossPartitionAccess` | Request body field | `false` | bool | `QueryMessage` | Requires security context permitting bypass. |
| `Aouda:PlsCrossPartitionRateLimit:Enabled` | Server config | `false` | bool | server options | Enables rate limiting for PLS cross-partition bypass path. |
| `Aouda:PlsCrossPartitionRateLimit:PermitLimit` | Server config | `60` | positive int | server options | Requests per window. |
| `Aouda:PlsCrossPartitionRateLimit:WindowSeconds` | Server config | `60` | positive int | server options | Window length in seconds. |

Precedence/override notes:

- Response format: request `format` controls projection shape; there is no higher-layer persistent override.
- Read preference: query parameter overrides header when both are present.
- Limit handling: request value is normalized by translator (`0` special-case, negative->default, positive->cap).
- Cross-partition behavior: request can ask for bypass, but security/authorization/rate-limit layers still gate execution.

### Operator and query-option glossary

#### Where operators (wire protocol)

| Wire op | Meaning | Example |
|---|---|---|
| `eq` | Equals | `{ "column":"status", "op":"eq", "value":"active" }` |
| `ne` | Not equals | `{ "column":"status", "op":"ne", "value":"deleted" }` |
| `gt` | Greater than | `{ "column":"price", "op":"gt", "value":100 }` |
| `gte` | Greater than or equal | `{ "column":"price", "op":"gte", "value":100 }` |
| `lt` | Less than | `{ "column":"price", "op":"lt", "value":1000 }` |
| `lte` | Less than or equal | `{ "column":"price", "op":"lte", "value":1000 }` |

Notes:
- Server-side validator currently accepts only the six operators above for this query API.
- Type normalization is column-aware in `QueryTranslator` (for example `Timestamp`, `Date`, `Bool`, unsigned numeric types).

#### SDK symbol/operator mapping

| SDK input | Sent wire op |
|---|---|
| `=` | `eq` |
| `!=` | `ne` |
| `>` | `gt` |
| `>=` | `gte` |
| `<` | `lt` |
| `<=` | `lte` |

#### Other common query options

| Option | Meaning | Example |
|---|---|---|
| `format=columnar` | Return `ColumnarResult` (default) | `POST /query?format=columnar` |
| `format=rows` | Return row-oriented result payload | `POST /query?format=rows` |
| `orderBy[].descending=true` | Descending sort for that column | `{ "column":"createdAt", "descending":true }` |
| `offset` | Skip N rows before returning data | `"offset": 100` |
| `limit` | Max rows returned (`0` means unlimited) | `"limit": 1000` |
| `crossPartitionAccess` | Request partition-bypass mode | `"crossPartitionAccess": true` |

## 2.11 API and CLI coverage reference (complete + gap-aware)

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Basic query execute | `RemoteTableQuery.ToColumnarAsync()/ToListAsync()` | `table().execute()` | `POST /api/databases/{db}/query` | Implemented | Columnar is default response shape. |
| Filtering (AND-style chaining) | `.Where(...)`, `.WhereAnd(...)`, `.WhereOr(...)` | `.where(...)` (AND chaining) | `where.and`, `where.or` | Implemented | TS builder emits `and` for chained where. |
| Nested boolean groups | Partial (flattening in builder path) | Missing builder surface | `where.groups` supported | Partial | Server supports; SDK ergonomics lag (`BL-044`). |
| Projection | `.Select(...)` | `.select(...)` | `select` | Implemented | Null/omitted means all columns. |
| Pagination | `.Skip()`, `.Limit()` | `.offset()`, `.limit()` | `offset`, `limit` | Implemented | `limit=0` treated as unlimited. |
| Ordering | `.OrderBy().ThenBy()` | `.orderBy().thenBy()` | `orderBy[]` | Implemented | Max 8 order-by columns. |
| Count convenience | `.CountAsync()` → `/query/count` | `.count()` (query-based until updated) | `POST .../query/count` | Partial | TypeScript client follow-up. |
| Cross-partition query flag | `.WithCrossPartitionAccess()` | No dedicated fluent method in current builder | `crossPartitionAccess` bool | Partial | TS can still send raw request outside builder. |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Nested group builder parity (.NET) | `.Group(...)`-style nested condition API in `RemoteConditionBuilder` | Build raw `QueryMessage.Where.Groups` when using lower-level transport | `BL-044` | High |
| Nested group builder parity (TypeScript) | `groups` in `WhereClause` + fluent group builder | Use flat `and/or` only, or custom transport payload | `BL-044` | High |
| Efficient count endpoint | Implemented (`/query/count`, .NET) | Use query execution with `limit=0` and rowCount | TS adoption | Medium |
| Fluent JOIN workflows | `Join()` API across SDK fluent builders | Use planner/internal paths only (no stable public fluent route) | `BL-009` | High |
| JOINed materialized query support | Materialized-query JOIN definition + maintenance | Single-table materialized patterns only | `BL-010` | Medium |

### .NET example

```csharp
var rows = await client
    .Table("orders")
    .Where("status", "eq", "active")
    .OrderBy("createdAt", descending: true)
    .ThenBy("id")
    .Limit(100)
    .ToListAsync<dynamic>();
```

Expected result:
- Up to 100 rows, sorted by `createdAt DESC, id ASC`.

Common mistake:
- Calling `ThenBy()` before `OrderBy()` throws.

### TypeScript example

```ts
const result = await client
  .table("orders")
  .where("status", "=", "active")
  .orderBy("createdAt", "desc")
  .thenBy("id", "asc")
  .limit(100)
  .execute();

console.log(result.rows.length, result.stats.executionMs);
```

Expected result:
- Rows in requested order with `QueryStats` in `result.stats`.

Common mistake:
- Assuming multiple `.where()` calls produce OR behavior; they are AND-combined.

### HTTP example

```http
POST /api/databases/appdb/query?format=columnar
Content-Type: application/json

{
  "database": "appdb",
  "table": "orders",
  "select": ["id", "status", "createdAt"],
  "where": {
    "and": [
      { "column": "status", "op": "eq", "value": "active" }
    ]
  },
  "orderBy": [
    { "column": "createdAt", "descending": true }
  ],
  "offset": 0,
  "limit": 100
}
```

Expected result:
- `ColumnarResult` payload with `columns`, `types`, `data`, `rowCount`, and `stats`.

Common mistake:
- Omitting `database` in body or mismatching it with route path returns `InvalidRequest`/`MissingDatabase`.

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run baseline query path check

When to use:
- Validate that basic query pipeline is healthy after environment/bootstrap changes.

Steps:
1. Insert a small sample table.
2. Execute one filtered query via HTTP or SDK.
3. Run the targeted server query tests:
   - `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~QueryIntegrationTests|FullyQualifiedName~QueryTranslatorTests" --verbosity minimal`

Expected checks:
- Query returns expected rows.
- Invalid format/request cases return protocol errors, not unhandled exceptions.

### Scenario 2: Production-safe mixed-state correctness

When to use:
- Validate correctness when data spans unflushed HRA + cold segments.

Steps:
1. Insert rows, force flush/compaction for a subset.
2. Insert additional rows (remain hot/unflushed).
3. Run filtered query and count query.
4. Run targeted correctness suites (`C2` mirrors and storage query tests).

Expected checks:
- No duplicates or missing rows across mixed temperature states.
- Count reflects both cold and current hot data.

### Scenario 3: Query API compatibility across SDKs

When to use:
- Ensure .NET and TypeScript clients serialize equivalent query contracts.

Steps:
1. Build equivalent filter/order/limit query in .NET and TS.
2. Inspect outgoing payloads in tests (`query-builder.test.ts`, .NET integration tests).
3. Execute both and compare logical result sets.

Expected checks:
- Operator mapping and order-by serialization match protocol expectations.
- TS and .NET both return consistent row counts/order for equivalent query intent.

## 2.13 Operations and observability

What to monitor first:

- Query throughput and latency: `Perf.QueryApiCalls`, `Perf.QueryApiMs`.
- Data-temperature scan mix: `Perf.HotScanRows`, `Perf.ColdScanRows`, `Perf.DeltaRowsQueried`.
- Decode pressure: `Perf.DecodeCount`, `Perf.DecodeMs`.
- Pruning effectiveness: `Perf.PagesPrunedByMinMax`, `Perf.PagesPrunedByJoint`, `Perf.SegmentsPrunedFully`, bloom counters.
- Parallel execution behavior: `Perf.ParallelSegmentScans`, `Perf.ParallelScanMs`, `Perf.ParallelEarlyTerminations`.

Quick-answer matrix:

| Question | Practical answer |
|---|---|
| Are queries CPU-bound on decode? | Check `DecodeMs`/`DecodeCount` against row volume. |
| Is pruning helping? | Watch min/max/joint/bloom prune counters over representative traffic. |
| Are LIMIT queries terminating early? | Track `ParallelEarlyTerminations`. |
| Are we scanning unexpected cold/delta volume? | Compare `ColdScanRows` and `DeltaRowsQueried` trends. |
| Are query API calls increasing but rows flat? | Inspect query shape defaults (limit/order/filter) and client behavior. |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `Invalid format` error | `format` not `columnar` or `rows` | Fix query parameter; use one of supported format values. |
| `Database is required` or path/body mismatch | Missing or inconsistent `database` field | Ensure body `database` matches `/api/databases/{db}` route. |
| `ThenBy() requires OrderBy()` exception | Secondary sort called first | Add `OrderBy()` before `ThenBy()` in query chain. |
| Query returns fewer rows than expected | Default/capped limit applied | Set explicit `limit` (or `0` when intentionally unbounded). |
| Cross-partition query rejected/rate-limited | Missing authorization or bypass rate limit engaged | Verify credentials/claims and `PlsCrossPartitionRateLimit` settings. |
| Nested boolean request works over HTTP but not SDK builder | SDK does not expose groups API yet | Use raw protocol payload or flatten conditions; track `BL-044`. |
| Slow cold predicate query | Limited pruning selectivity or high decode volume | Validate predicate columns, check pruning counters, review data distribution/segment stats. |

## 2.15 Verification ledger

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Server query endpoint + translator behavior | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~QueryIntegrationTests|FullyQualifiedName~QueryTranslatorTests" --verbosity minimal` | Pass | 2026-03-31 | Covers request validation, translation defaults/limits, integration query flow. |
| Storage query engine batch/pruning/validity paths | `dotnet test tests/Aouda.Engine.Storage.Tests --no-build --filter "FullyQualifiedName~QueryEngineRowWindowBatchTests|FullyQualifiedName~QueryEnginePrunedExecutionTests|FullyQualifiedName~RowFilterEngineColdValidityTests" --verbosity minimal` | Pass | 2026-03-31 | Confirms row-window batch contract, pruning execution, cold validity behavior. |
| TypeScript query builder contract | `npm test -- query-builder.test.ts` | Pass | 2026-03-31 | Confirms immutable builder behavior, operator/order/limit serialization, endpoint path usage. |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| HTTP query integration and error handling | `tests/Aouda.Server.Tests/QueryIntegrationTests.cs` | Pass | Strong | Exercises endpoint behavior and protocol responses. |
| Query translation/validation/defaults | `tests/Aouda.Server.Tests/QueryTranslatorTests.cs` | Pass | Strong | Validates translator rules and normalization. |
| QueryEngine `QueryBatch` contract | `tests/Aouda.Engine.Storage.Tests/QueryEngineRowWindowBatchTests.cs` | Pass | Strong | Verifies row-window aligned batch semantics. |
| Pruned execution behavior | `tests/Aouda.Engine.Storage.Tests/QueryEnginePrunedExecutionTests.cs` | Pass | Medium | Focuses pruning outcomes and execution correctness. |
| Cold validity + filter path correctness | `tests/Aouda.Engine.Storage.Tests/RowFilterEngineColdValidityTests.cs` | Pass | Strong | Covers validity alignment in cold predicate execution. |
| TypeScript query payload mapping | `aouda-client-ts/tests/query-builder.test.ts` | Pass | Strong | Covers builder immutability, operators, order, pagination serialization. |
| Mixed-state correctness (hot/cold/unflushed) | `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`, `tests/Aouda.Engine.Api.Tests/C2ScenarioMirrorIntegrationTests.cs` | Not run in this pass | Medium | Evidence from prior report cycle; re-run recommended for release gates. |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| Nested `WhereClause.Groups` parity across SDKs | Server supports groups but SDK ergonomics lag | Add SDK tests that round-trip nested groups (groups-within-groups) into wire payload | High |
| Depth guardrail for recursive groups | Prevent extreme nested payload abuse | Add translator validation tests for max group depth and explicit error code | High |
| Count endpoint efficiency baseline | Baseline large-table count latency vs full query | Add benchmark comparing `/query/count` vs materialized full query | Medium |
| Cross-partition query builder parity in TS | Missing fluent API increases accidental inconsistencies | Add TS builder API + integration tests for `crossPartitionAccess` request emission | Medium |
| Materialized query auto-routing explainability tests | Ensure routing decisions remain deterministic | Extend `MaterializedQueryAutoRoutingTests` with coverage of rejected matches and fallback path | Medium |

## 2.18 Known gaps and undone work

_Updated 2026-04-08 after P14, P15, P16 completion._

### Resolved gaps

- ~~Nested group construction is not first-class in current SDK query builders~~ — ✅ **Resolved (P14, BL-044)**: WhereClause.Groups adopted end-to-end across SDKs/helpers with nested group support.
- ~~No max-depth validation for deeply recursive `WhereClause.Groups`~~ — ✅ **Resolved (P14, BL-044)**: depth guardrails implemented.
- ~~TypeScript client count may still use full query~~ — ✅ **Resolved (P14, BL-026)**: server-side `POST .../query/count` endpoint shipped; both .NET `CountAsync` and TS `count()` use it.
- ~~Fluent/public JOIN APIs remain unavailable~~ — ✅ **Resolved (P14 BL-009, P15)**: complete join engine with all five join types (INNER, LEFT, RIGHT, FULL OUTER, CROSS), post-join SELECT/WHERE/ORDER BY/LIMIT/aggregates, multi-column keys, chained joins (up to 8 tables), Grace hash join with spill-to-disk. Exposed in both .NET `TableQuery` and TypeScript `@aouda/client` query builders.
- ~~Bool predicate overload parity~~ — ✅ **Resolved (P14, BL-038)**: `ConstBool`, `ColumnRef.Eq/Ne(bool)` added.
- ~~Guid PK mixed-type comparison failure~~ — ✅ **Resolved (P14, BL-039)**: added `IsGuid`/`CompileGuid` path in `RowFilterEngine`.
- ~~Nullable timestamp update failure~~ — ✅ **Resolved (P14, BL-040)**: deletion mask applied to validity bitmap.
- Cold-path pruning is restored with cross-column page pruning (`P7-BL025`); further tuning remains normal performance work, not a correctness blocker.

### New capabilities (P15/P16)

- **Extended filter operators (P16 H.2)**: TypeScript client now supports `in()`, `notIn()`, `like()`, `isNull()`, `isNotNull()`, `between()` in addition to the six comparison operators.
- **Aggregate query builder (P16 H.1)**: TypeScript client supports `sum()`, `min()`, `max()`, `count()`, `groupBy()`, `groupAggregate()`.
- **Columnar output (P16 H.4)**: `.toColumnar()` execution method for high-performance columnar access.

### Remaining gaps

- Materialized query JOIN support depends on fluent JOIN foundation and remains out of current scope: `BL-010`.
- Sort-merge join as alternative algorithm: deferred to future performance optimization.
- Join reordering optimizer: deferred to future cost-based optimizer work.
- Distributed/multi-node joins: deferred (requires distributed query engine).

## 2.19 References

- `docs/dev/Functionality-Document-Template.md`
- `docs/dev/Functionality-Overview.md`
- `docs/tasks/P3/P3-Task6-QueryEngineHotColdIntegration-Report.md`
- `docs/tasks/P4/P4-EpicA-Task2-RestQueryApi-Report.md`
- `docs/tasks/P4/P4-EpicG-BL007-QueryEngineDeltaIntegration-Report.md`
- `docs/tasks/P4/P4-EpicH-BL016-QueryEngineDataDecoding-Report.md`
- `docs/tasks/P4/P4-EpicH-BL017-TableQueryPredicateFiltering-Report.md`
- `docs/tasks/P4/P4-EpicH-R10.4-QueryUnflushedHraTableData-Report.md`
- `docs/tasks/P7/C2-QueryCorrectness-Summary.md`
- `docs/tasks/P7/P7-BL025-CrossColumnPagePruning-Report.md`
- `docs/tasks/P12/BL-038-QueryEngine-RowWindow-BatchContract-Report.md`
- `docs/tasks/P12/BL-038A-Remove-Legacy-QueryEngine-ExecuteAsync-TupleContract-Report.md`
- `docs/decisions/0015-materialized-queries.md`
- `docs/BACKLOG.md`
- `src/Aouda.Server/Controllers/QueryController.cs`
- `src/Aouda.Server/Query/QueryTranslator.cs`
- `src/Aouda.Protocol/Messages.cs`
- `src/Aouda.Protocol/ProtocolConstants.cs`
- `src/Aouda.Engine.Api/TableQuery.cs`
- `src/Aouda.Engine.Storage/Query/QueryEngine.cs`
- `src/Aouda.Engine.Storage/Query/QueryBatch.cs`
- `src/Aouda.Engine.Storage/Query/RowFilterEngine.cs`
- `src/Aouda.Engine.Storage/Query/ParallelSegmentScanner.cs`
- `src/Aouda.Engine.Diagnostics/Perf.cs`
- `src/Aouda.Client/RemoteTableQuery.cs`
- `src/Aouda.Client/RemoteConditionBuilder.cs`
- `src/Aouda.Client/Internal/QueryMessageBuilder.cs`
- `aouda-client-ts/src/query-builder.ts`
- `aouda-client-ts/src/types.ts`
- `tests/Aouda.Server.Tests/QueryIntegrationTests.cs`
- `tests/Aouda.Server.Tests/QueryTranslatorTests.cs`
- `tests/Aouda.Engine.Storage.Tests/QueryEngineRowWindowBatchTests.cs`
- `tests/Aouda.Engine.Storage.Tests/QueryEnginePrunedExecutionTests.cs`
- `tests/Aouda.Engine.Storage.Tests/RowFilterEngineColdValidityTests.cs`
- `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`
- `tests/Aouda.Engine.Api.Tests/C2ScenarioMirrorIntegrationTests.cs`
- `aouda-client-ts/tests/query-builder.test.ts`

## 2.20 What is missing from this document? (meta completeness)

- This document validates core query execution paths with targeted suites, but does not include a fresh full-suite run across all query-adjacent test projects in this pass.
- P14 query-related work is represented through protocol/code/backlog evidence (not a dedicated P14 query report in the audited set).
- Backlog contains some historical entries whose status may not reflect current shipped behavior (for example ORDER BY API exposure); backlog hygiene can be improved separately.
