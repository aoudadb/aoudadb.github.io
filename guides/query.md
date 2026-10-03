---
title: "Query Execution"
nav_order: 1
parent: "Guides"
---

# Aouda Functionality: Query Execution and Optimization

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

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
  - Keep query behavior stable as data moves between hot and cold storage.
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
| Runtime code | `src/Aouda.Server/Controllers/QueryController.cs`, `src/Aouda.Server/Query/QueryTranslator.cs`, `src/Aouda.Engine.Api/TableQuery.cs`, `src/Aouda.Engine.Storage/Query/Scan/TableScan.cs`, `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs`, `src/Aouda.Engine.Core/Query/Scan/PredicateProgram.cs`, `src/Aouda.Engine.Diagnostics/Perf.cs` |
| Protocol/limits | `src/Aouda.Protocol/Messages.cs`, `src/Aouda.Protocol/ProtocolConstants.cs` |
| Client surfaces | `src/Aouda.Client/RemoteTableQuery.cs`, `src/Aouda.Client/RemoteConditionBuilder.cs`, `src/Aouda.Client/Internal/QueryMessageBuilder.cs`, `aouda-client-ts/src/query-builder.ts`, `aouda-client-ts/src/types.ts` |
| Gap tracking | `docs/BACKLOG.md` (`BL-003`, `BL-009`, `BL-010`, `BL-044`) |

## 2.3 Defaults and zero-config behavior

If you issue a query without custom tuning, Aouda applies protocol defaults and engine safeguards.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| HTTP query response format | `columnar` | Lower payload overhead by default; row format is opt-in (`format=rows`). A request whose `Accept` lists `application/vnd.aouda.column-batch` gets binary column-batch frames instead, and both SDKs ask for them by default (**ColumnarRead S16, next train**; [HTTP reference](../reference/http-api.md#post-apidatabasesdbquery)). |
| `limit` when omitted/negative | `1000` (`ProtocolConstants.DefaultLimit`) | Prevents accidental unbounded results. With `aggregates` / `groupBy` it counts **groups** (**ColumnarRead S16, next train**): set `limit` and page with `offset` when a query can make more. |
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
- **Expression SELECT projections** — `selectExpr` field on `QueryMessage` adds server-side computed columns to query results without storing them (P27 / S7 / BL-080). See `guides/bulk-mutations.md` §8.
- Fluent query APIs:
  - Engine-side `TableQuery` (`Where`, `Select`, `SelectExpr`, `Skip`, `Limit`, `OrderBy`, `ThenBy`, aggregates).
  - .NET remote `RemoteTableQuery` with ordering and cross-partition flag propagation, plus `.SelectExpr()`.
  - TypeScript `TableQuery` with immutable chaining and operator mapping, plus `.selectExpr()`.
- Hot/cold query execution through one path — **one scan** (**ColumnarRead, next train**): every read (rows, columns,
  `COUNT(*)`, aggregates, GROUP BY, `ORDER BY … LIMIT`, `DISTINCT`, joins' sides, streaming) and every write-side scan
  (DELETE / UPDATE matching, constraint checks) reads cold segments, hot segments and the unflushed write buffer through
  `TableScan`, with one predicate evaluator (`PredicateProgram`). `QueryEngine`, `RowFilterEngine`, `PagePruner`,
  `ParallelSegmentScanner` and the other old engines are deleted.
- Optimization in the execution path (**ColumnarRead, next train**):
  - Each 8,192-row row group is classified from its statistics (`RowGroupClassifier`): none of its rows can match → not
    read; every row matches → the filter is not evaluated. Only the filter's columns are decoded first; the others only for
    the 2,048-row vectors that hold a selected row.
  - Aggregates and `DISTINCT` answer a row group the filter selects whole, with no deleted row, from its statistics.
  - `ORDER BY … LIMIT` keeps a top-K whose threshold skips row groups that cannot beat it.
  - A filter pinning every series column by equality reads only that series' rows, from each segment's run directory; a
    full-key read of a cold segment reads only the rows the key map located.
  - Scans above 65,536 rows of work run on several workers within the query's CPU grant (morsels); answers do not depend on
    the degree.
  - Partition-key pruning as before. A bloom filter is read only by primary-key lookups (a `Strict` table writes one),
    not by filters on other columns; the adaptive bloom path is deleted.
- Late rows are flushed inline; there are no delta segments to read (**ColumnarRead, next train**).
- Materialized-query routing on every read path and over HTTP, to a current result only
  ([routing](materialized.md#routing-a-read-to-a-maintained-result); **ColumnarRead S18, next train**).

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
| TypeScript fluent ordering/query parity | Yes | No | No | `query-builder.ts` + `query-builder.test.ts` | Core parity present including nested group API (`whereGroup()`). Resolved P14, BL-044. |
| Nested boolean groups over HTTP (`WhereClause.Groups`) | Yes | No | No | `Messages.cs` + `QueryTranslator` recursion | Server/wire supports nested groups. |
| Nested boolean groups in .NET client builders | Yes | No | No | `RemoteConditionBuilder` + `QueryMessageBuilder` | Resolved P14, BL-044; nested group composition now emitted. |
| Nested boolean groups in TypeScript builder | Yes | No | No | `aouda-client-ts/src/query-builder.ts` (`WhereGroupBuilder`, `whereGroup()`) | `whereGroup()` builds nested `WhereClause.groups` entries. Resolved P14, BL-044. |
| Hot + cold + unflushed HRA unified visibility | Yes | No | No | P4 R10.4 report + `TableQuery` + P7 summary tests | Virtual hot segment merged into query execution paths. |
| Delta segment query inclusion | No | No | Yes | P4 BL007 report | Removed with delta segments (**ColumnarRead, next train**): late rows are flushed inline. |
| Page pruning and multi-column pruning | Yes | No | No | `TableScan` + `RowGroupClassifier` (**ColumnarRead, next train**; `QueryEngine`, `RowFilterEngine`, `PagePruner` deleted) | Per 8,192-row row group, from the segment footer's statistics; `AND` / `OR` / `NOT` in three-valued logic. |
| Bloom-filter-assisted pruning | No | Partial | No | Key probe only (**ColumnarRead, next train**) | Only primary-key lookups read a bloom (`Strict` tables); the adaptive bloom path is deleted. |
| Parallel multi-segment scanning | Yes | No | No | Morsels on the query's CPU grant (**ColumnarRead, next train**; `ParallelSegmentScanner` deleted) | Above 65,536 rows of work; rows come back in the sequential order. `ORDER BY … LIMIT` stays on one thread. |
| Dedicated count API endpoint | Yes (`/query/count`) | No | Yes | Implemented (2026-04-04, `BL-026`) | TS client still on query path until updated. |
| Fluent JOIN query support | No | No | Yes | Backlog + absence in fluent APIs | Internal planner support exists but not exposed in fluent APIs. |

## 2.7 Core concepts and mental model

- `QueryMessage`: the wire-level request contract (`database`, `table`, `select`, `where`, `orderBy`, `offset`, `limit`, `crossPartitionAccess`).
- `TableQuery`: engine-facing immutable builder used by server translation and direct engine consumers.
- `QueryTranslator`: server bridge from wire DTO to `TableQuery`; enforces defaults and limits.
- `TableScan` (**ColumnarRead, next train**): the one scan every read and write-side scan runs on, over one fixed view of
  the table's segments, their deletion masks and the write buffer; sinks for rows, aggregates, GROUP BY, top-K and
  `DISTINCT`.
- `PredicateProgram`: the one predicate evaluator (three-valued: a null makes a comparison unknown).
- `RowGroupClassifier`: decides from a row group's statistics whether none, all or some of its rows can match.
- `QueryEngine`, `QueryBatch`, `RowFilterEngine` and `ParallelSegmentScanner` are deleted (**ColumnarRead, next train**).
- Optimization layers:
  - row-group pruning from page statistics,
  - series and key lookups that read only the rows they return,
  - top-K thresholds for `ORDER BY … LIMIT`,
  - parallel morsels for large scans.

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
   - a current materialized result that holds the answer, when one does ([routing](materialized.md#routing-a-read-to-a-maintained-result)),
   - otherwise the one scan (`TableScan`) for rows, columns, aggregates, GROUP BY, top-K and `DISTINCT` alike (**ColumnarRead, next train**).
6. The scan reads the segments the table's catalog names; no directory is listed (**ColumnarRead, next train**).
7. Results are returned as columnar by default and converted to row format when requested.

Runtime notes:

- `limit=0` on `/query` is interpreted as no cap for full reads.
- Unflushed writes are read from the write buffer where they are — its frozen arrays and sealed 4,096-row chunks, with the rows the read must not see masked — so queries see current data before flush without copying the buffer (**ColumnarRead S19, next train**; it was flattened into fresh arrays on every read).
- A read is one view (**ColumnarRead, next train**): its segments, their deletion masks and the unflushed rows are fixed at one instant, so a concurrent MERGE, UPDATE, flush or coalesce is seen wholly or not at all — never half, never twice. A read no longer re-runs when a segment leaves under it. A read whose catalog names a segment it cannot resolve (a Hot segment with no hot copy, for more than a second) fails rather than returning short. A catalog change is visible to reads only once it is durable; if a catalog journal append fails, the table's reads are refused until the database is reopened.
- `OFFSET` / `LIMIT` without an `ORDER BY` stop the scan; with one, a top-K (or, without a `LIMIT`, a sort of a permutation of the rows) applies them after ordering (**ColumnarRead, next train**).

## 2.8.1 Critical path walk-throughs (implementation-level)

### Path A: HTTP query request -> translated query -> response

1. Entry point: `QueryController.ExecuteQuery`.
2. Validates format (`columnar`/`rows`), database/path consistency, and query payload.
3. Applies authorization and partition security enforcement.
4. Translates to `TableQuery` with normalized defaults (`DefaultLimit`, `MaxLimit`, `MaxOrderByColumns`).
5. Executes and returns `ColumnarResult` or row-converted response.
6. Tests: `tests/Aouda.Server.Tests/QueryIntegrationTests.cs`, `tests/Aouda.Server.Tests/QueryTranslatorTests.cs`.

### Path B: Predicate query on cold/mixed segments

(**ColumnarRead, next train:** `RowFilterEngine` and `ExecuteWithRowFilterAsync` are deleted; this path is the one scan.)

1. Entry point: `TableQuery.ToColumnarAsync` (or list path) with predicate set.
2. The read fixes its view: the segments its catalog names, their deletion masks and the write buffer, at one instant.
3. `TableScan` classifies each 8,192-row row group from its statistics (`RowGroupClassifier`), decodes the filter's
   columns for the rest, evaluates the predicate with `PredicateProgram`, and decodes the other columns only for the
   2,048-row vectors holding a selected row.
4. Validity bitmaps and deletion masks are preserved through decode/projection.
5. Tests: the differential oracle (`ReadRuleOracle*Tests`) and the reference fuzzer (`ReadFuzz*Tests`) in
   `tests/Aouda.Engine.Api.Tests/ColumnarRead/`, `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`.

### Path C: Aggregate/count with mixed hot+cold and unflushed rows

1. Entry point: `TableQuery.AggregateAsync` or client-side `Count`.
2. The read's view includes persisted segments plus the unflushed write buffer.
3. Every aggregate runs on the one scan (**ColumnarRead, next train**; `ParallelSegmentScanner` is deleted). An 8,192-row row group the filter selects whole and that has no deleted row is answered
   from its page statistics — row and null counts, exact integer and decimal sums, exact bounds — without reading a page; a
   double's `SUM` and a string's `MIN` / `MAX` are decoded for that row group, and a row group with a deletion is decoded
   whole. `SUM` of a `String`, `Bool`, `Guid`, `Timestamp` or `Date` column is refused. A `GroupBy` query given to
   `AggregateAsync()` is refused rather than answered ungrouped — use `GroupAggregateAsync()` (item 6).
4. Merged aggregate result reflects both cold and current hot state.
5. **Nulls (**BL-735, 0.2.0**):** `Min`, `Max`, `Sum` and `Count(column)` skip a column's nulls, as SQL does;
   a bare `Count()` counts every row. Before, a null was aggregated as its type's default (`0`), so `Min` over positive
   values with a null read `0`.
   **`Sum` over no value is `null` (**BL-757, next train**)** — a filter that matches nothing, or a column null in every
   matching row — on every path, joins included; it was `0` when a segment was read and `null` when none was. `Min` / `Max`
   over no value are `null`; `Count` over nothing is `0`. `Min` / `Max` of a `String` (code-point order) or `Bool` column
   now answer the value instead of `null` (**ColumnarRead, next train**).
6. **Grouped aggregates in the embedded engine (**ColumnarRead, next train**):** `TableQuery.GroupBy("Ticker", "Source")`, or
   `GroupBy(GroupKey.Column("Ticker"), GroupKey.Truncate("DateTime", PartitionFunction.TruncateToMinute, "Minute"))` for a
   time bucket of a `Timestamp` column, with `Count()`, `Count(col)`, `Sum`, `Min`, `Max`, `First(col, orderBy)` and
   `Last(col, orderBy)`, executed by `GroupAggregateAsync()`. The result is a `ColumnarQueryResult`: the keys, then one
   column per aggregate (`COUNT`, `SUM_<col>`, `MIN_<col>`, `FIRST_<col>` …), ordered by the keys ascending with nulls
   last; `Skip` / `Limit` apply after grouping. An integer `SUM` is an exact `Int64` (an overflow throws). **ColumnarRead S16
   (next train):** `OrderBy` over a grouped result (by a key's or an aggregate's output name, before `Skip` / `Limit`); `Avg(col)`
   and `CountDistinct(col)`; `GroupAggregateAsync()` without `GroupBy()` answers one row. Over HTTP as the query message's
   `aggregates` / `groupBy` ([reference](../reference/http-api.md#aggregates-and-group-by)).
7. **The latest (or first) row per key (**BL-450, ColumnarRead S18, next train**):** `TableQuery.LatestPerKey("DateTime",
   "Ticker", "Source")` keeps, per distinct key, the row with the greatest `DateTime` among the rows the filter selects;
   `FirstPerKey` the least. A row whose order column is null is not a candidate; among rows tied on it, the lowest primary
   key wins. `Select`, `OrderBy`, `Skip` / `Limit` and `WithTotalMatches` apply to the collapsed rows; `ToListAsync`,
   `ToResultAsync` and `ToColumnarAsync` answer it. It is read from a `LatestPerKey` / `FirstPerKey` materialized query of the
   same keys and order column when one is current and the filter is on the keys only
   ([routing](materialized.md#routing-a-read-to-a-maintained-result)); the table answers otherwise. Not over HTTP yet.
8. **Routing (**ColumnarRead S18, next train**):** every one of these reads — rows, columns, aggregates, GROUP BY, the per-key
   collapse — is answered from a materialized query that holds the answer and is current
   ([routing](materialized.md#routing-a-read-to-a-maintained-result)); `WithDirectScan()` reads the table regardless.
9. Tests/evidence: P4 R10.4 report + `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`; ColumnarRead
   `OneScanAggregateTests`, `GroupByTests`, the differential oracle (`RowGroupAggregates`; S18's `ReadRuleOracleRoutingTests`
   for routing) and the reference fuzzer.

### Path D: QueryEngine row-window contract

(**ColumnarRead, next train:** `QueryEngine` and `QueryBatch` are deleted with their tests; this path no longer exists. Kept
for its history.)

1. Entry point: single-segment execute path in `QueryEngine.ExecuteAsync`.
2. Engine decodes columns and yields explicit `QueryBatch` records.
3. Legacy tuple contract removed; consumers depend on batch alignment guarantees.
4. Tests/evidence: P12 BL-038/BL-038A reports + `tests/Aouda.Engine.Storage.Tests/QueryEngineRowWindowBatchTests.cs`.

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Do I need separate APIs for hot vs cold data? | Often yes (cache + store split) | One query surface across hot/cold/unflushed HRA | Simpler app code and fewer consistency surprises. |
| Is pruning/optimization user-managed? | Often index/query-hint heavy | Optimization is mostly internal (row-group statistics, series and key lookups, top-K, parallel morsels) | Lower tuning burden for common workloads. |
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
- The server-side `QueryTranslator.IsValidOperator` accepts only the six comparison operators above (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`). Requests containing any other operator string are rejected with a validation error.
- The TypeScript client also accepts user-facing operators `in`, `notIn`, `like`, `isNull`, `isNotNull`, and `between`. The `isNull`/`isNotNull` and `between` operators are expanded client-side to standard wire predicates before the request is sent (see SDK mapping table below). The `in`, `notIn`, and `like` operators are translated to wire ops `in`, `nin`, `like` respectively, but the server's current validator rejects them — these are planned for a future server-side extension.
- Type normalization is column-aware in `QueryTranslator` (for example `Timestamp`, `Date`, `Bool`, unsigned numeric types).
- `gt` / `gte` / `lt` / `lte` on a `String` column compare by ordinal UTF-8 byte (code-point) order, case-sensitive, no locale (**BL-750, next train**; the server refused a string value for them before). See [HTTP API — operators](../reference/http-api.md).

#### SDK symbol/operator mapping

| SDK input | SDK | Sent wire op | Server-side support |
|---|---|---|---|
| `=` | All | `eq` | Yes |
| `!=` | All | `ne` | Yes |
| `>` | All | `gt` | Yes |
| `>=` | All | `gte` | Yes |
| `<` | All | `lt` | Yes |
| `<=` | All | `lte` | Yes |
| `in` | TypeScript only | `in` | No — server rejects; planned extension |
| `notIn` | TypeScript only | `nin` | No — server rejects; planned extension |
| `like` | TypeScript only | `like` | No — server rejects; planned extension |
| `isNull` | TypeScript only | `eq null` (expanded client-side) | Yes — expanded before sending |
| `isNotNull` | TypeScript only | `ne null` (expanded client-side) | Yes — expanded before sending |
| `between` | TypeScript only | `gte min` + `lte max` (expanded client-side) | Yes — two AND predicates |

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
| Nested boolean groups | `.whereGroup()` / `WhereGroupBuilder` (P14, BL-044) | `.whereGroup()` / `WhereGroupBuilder` (P14, BL-044) | `where.groups` supported | Implemented | Both .NET and TypeScript builder surfaces now emit nested `groups`. |
| Projection | `.Select(...)` | `.select(...)` | `select` | Implemented | Null/omitted means all columns. |
| Pagination | `.Skip()`, `.Limit()` | `.offset()`, `.limit()` | `offset`, `limit` | Implemented | `limit=0` treated as unlimited. |
| Ordering | `.OrderBy().ThenBy()` | `.orderBy().thenBy()` | `orderBy[]` | Implemented | Max 8 order-by columns. |
| Grouped aggregates | Embedded engine: `TableQuery.GroupBy(...)` + `GroupAggregateAsync()`; remote: `RemoteTableQuery.GroupBy(...)` / `Sum` / `Avg` / `CountDistinct` … + `AggregateAsync()` (**ColumnarRead, next train**) | `.groupBy(...)`, `.sum()`, `.avg()`, `.countRows()`, `.countDistinct()` … (**ColumnarRead S16, next train**) | `aggregates`, `groupBy` in the query message (**S16**) | Implemented (next train) | Time buckets (`minute` … `year`); `orderBy` over the result's names. `First` / `Last` embedded only. |
| Total matches with a page | Embedded engine: `TableQuery.WithTotalMatches()` → `TotalMatches` on the result (**ColumnarRead, next train**) | — | Named queries: `count: true` → `totalMatches` | Embedded + named queries | Counted by the same read over the same snapshot as the page, ignoring `Skip` / `Limit`. |
| Rows as views | Embedded engine: `ToListAsync()` rows read the result's columns (**ColumnarRead, next train**) | — | — | Embedded | A row is a view over the result's column arrays: the indexer boxes one cell, `Get<T>` reads a typed column without boxing, `ToDictionary()` copies. |
| Count convenience | `.CountAsync()` → `/query/count` | `.count()` uses `/query?limit=0` (not the dedicated endpoint) | `POST .../query/count` | Partial | .NET uses dedicated count endpoint; TS adoption is an open follow-up. |
| Cross-partition query flag | `.WithCrossPartitionAccess()` | No dedicated fluent method in current builder | `crossPartitionAccess` bool | Partial | TS can still send raw request outside builder. |
|| Expression SELECT (computed columns) | `.SelectExpr((alias, expr), ...)` | `.selectExpr({ alias: expr })` | `selectExpr[]` in query body | Implemented (P27 S7 / P40 S08) | Server-computed columns appended to result; type is inferred where the expression permits (`Unknown` otherwise). Always nullable. See [browser-tier read limits](browser-tier-read-limits.md#selectexpr-result-types) and [Bulk Mutations](bulk-mutations.md). |
|| Literal UPDATE | `.UpdateAsync(dict)` | `.update(values)` | `PATCH .../rows` | Implemented | Requires at least one WHERE predicate. See [Bulk Mutations guide](bulk-mutations.md). |
|| Expression SET UPDATE | `.UpdateAsync(setBuilder)` | `.update({ col: { \$inc: 1 } })` | `PATCH .../rows` (`setExpr`) | Implemented (P27 S1) | Server-side expression evaluation; WAL stores concrete resolved values. |
|| DELETE with WHERE | `.DeleteAsync()` | `.delete()` | `DELETE .../rows` | Implemented | Requires at least one WHERE predicate. |
|| DELETE with LIMIT | `.DeleteAsync()` + `.Limit()` | `.delete()` + `.limit()` | `DELETE .../rows` (`limit`, `orderBy`) | Implemented (P27 S2) | Returns `hasMore` sentinel; pair with `orderBy` for deterministic rolling deletes. |
|| TRUNCATE | `.TruncateAsync()` | `.truncate()` | `POST .../truncate` | Implemented (P27 S2) | Requires `Truncate` auth scope; crash-safe. |
|| RETURNING on UPDATE/DELETE | `.UpdateAsync(..., returning:[...])` | `.update(v, { returning:[...] })` | `returning` field on PATCH/DELETE | Implemented (P27 S3) | UPDATE returns post-update; DELETE returns pre-delete values. |
|| Batch mutation | `.BatchAsync([...])` | `.batch([...])` | `POST .../rows/batch` | Implemented (P27 S4) | Multiple operations, single WAL commit. |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| TypeScript `in`/`notIn`/`like` operators — server-side support | Server `QueryTranslator.IsValidOperator` only accepts `eq/ne/gt/gte/lt/lte`; TS client sends `in`/`nin`/`like` which the server rejects | Use `eq`/`ne` predicates or filter client-side until server-side extension ships | Planned extension of `IsValidOperator` | High |
| TypeScript `count()` dedicated endpoint adoption | TS `count()` uses `/query?limit=0` instead of `POST /query/count` | .NET `CountAsync` is correct; TS is functionally equivalent but incurs columnar decode overhead | TS client adoption | Medium |
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
- Decode pressure: `Perf.DecodeCount`, `Perf.DecodeMs`, `Perf.DecodedValues`.
- Partition pruning and hot-tier hits: `Perf.SegmentsPrunedByPartitionKey`, `Perf.HotSegmentHits` / `HotSegmentMisses`.
- ⚠️ **Counters of the deleted scans read 0 (**ColumnarRead, next train**):** `HotScanRows`, `ColdScanRows`,
  `DeltaRowsQueried`, `PagesPrunedByMinMax`, `PagesPrunedByJoint`, `PagesAfterPruning`, `PruningBytesSaved`,
  `SegmentsPrunedFully`, the bloom counters, `ParallelSegmentScans`, `ParallelScanMs`, `ParallelEarlyTerminations`. They
  stay in the CSV and in `/api/admin/metrics` (the `query` subsystem's `rowsScanned`, `hotScanRows`, `coldScanRows`,
  `hotAggregateOps`, `coldAggregateOps`, `parallelScans`, `vectorizedOps`, `pagesPrunedByMinMax`, `pagesAfterPruning`, `pruningBytesSaved`, `segmentsPrunedFully`)
  and no longer move. A query's own `stats` (`rowsScanned`, `executionMs`) are unaffected.

Quick-answer matrix:

| Question | Practical answer |
|---|---|
| Are queries CPU-bound on decode? | Check `DecodeMs`/`DecodeCount` against row volume. |
| Is pruning helping? | The min/max/joint/bloom prune counters read 0 since **ColumnarRead** (next train); compare `DecodedValues` with the rows the queries return. |
| Are we decoding unexpected cold volume? | Compare `DecodedValues` / `DecodeMs` trends (`ColdScanRows` reads 0 since **ColumnarRead**, next train). |
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
| Storage query engine batch/pruning/validity paths | `dotnet test tests/Aouda.Engine.Storage.Tests --no-build --filter "FullyQualifiedName~QueryEngineRowWindowBatchTests|FullyQualifiedName~QueryEnginePrunedExecutionTests|FullyQualifiedName~RowFilterEngineColdValidityTests" --verbosity minimal` | Pass | 2026-03-31 | Confirms row-window batch contract, pruning execution, cold validity behavior. Historical: these tests were deleted with their engines (**ColumnarRead, next train**). |
| TypeScript query builder contract | `npm test -- query-builder.test.ts` | Pass | 2026-03-31 | Confirms immutable builder behavior, operator/order/limit serialization, endpoint path usage. |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| HTTP query integration and error handling | `tests/Aouda.Server.Tests/QueryIntegrationTests.cs` | Pass | Strong | Exercises endpoint behavior and protocol responses. |
| Query translation/validation/defaults | `tests/Aouda.Server.Tests/QueryTranslatorTests.cs` | Pass | Strong | Validates translator rules and normalization. |
| One scan: pruning rules, top-K, aggregates, routing against a reference model (**ColumnarRead, next train**) | `tests/Aouda.Engine.Api.Tests/ColumnarRead/ReadRuleOracle*Tests.cs`, `ReadFuzzTests.cs` | — | Strong | Every pruning rule and route has an oracle case, rule on and off. Replaces the deleted `QueryEngineRowWindowBatchTests`, `QueryEnginePrunedExecutionTests` and `RowFilterEngineColdValidityTests` (their engines are gone). |
| TypeScript query payload mapping | `aouda-client-ts/tests/query-builder.test.ts` | Pass | Strong | Covers builder immutability, operators, order, pagination serialization. |
| Mixed-state correctness (hot/cold/unflushed) | `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`, `tests/Aouda.Engine.Api.Tests/C2ScenarioMirrorIntegrationTests.cs` | Not run in this pass | Medium | Evidence from prior report cycle; re-run recommended for release gates. |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| TypeScript `in`/`notIn`/`like` server-side wiring | TS client emits `in`/`nin`/`like` wire ops that the server `IsValidOperator` currently rejects; real gap between client behavior and server validation | Once server-side validator is extended, add integration tests round-tripping these operators end-to-end | High |
| Depth guardrail regression coverage | `MaxWhereClauseNestingDepth = 5` is implemented in `ProtocolConstants` and validated by `QueryTranslator`; resolved P14, BL-044 | Add regression tests that submit groups at depths 5 (allowed) and 6 (rejected) to confirm boundary is stable | Medium |
| Count endpoint efficiency baseline | Baseline large-table count latency vs full query | Add benchmark comparing `/query/count` vs materialized full query | Medium |
| Cross-partition query builder parity in TS | Missing fluent API increases accidental inconsistencies | Add TS builder API + integration tests for `crossPartitionAccess` request emission | Medium |
| Materialized query auto-routing explainability tests | Ensure routing decisions remain deterministic | Extend `MaterializedQueryAutoRoutingTests` with coverage of rejected matches and fallback path | Medium |

## 2.18 Known gaps and undone work

_Updated 2026-04-08 after P14, P15, P16 completion._

### Resolved gaps

- ~~`DISTINCT` returned a `NULL` and its type's default as one row~~ — ✅ **Resolved** (**ColumnarRead, next train**):
  `Distinct("Volume")` over rows holding both `NULL` and `0` (or `false`, or `""`) returned only one of them. A `NULL` is
  now a distinct value of its own. `DISTINCT` also reads constant pages and small value sets from their statistics.

- ~~Nested group construction is not first-class in current SDK query builders~~ — ✅ **Resolved (P14, BL-044)**: WhereClause.Groups adopted end-to-end across SDKs/helpers with nested group support.
- ~~No max-depth validation for deeply recursive `WhereClause.Groups`~~ — ✅ **Resolved (P14, BL-044)**: depth guardrails implemented.
- ~~TypeScript client count may still use full query~~ — ⚠️ **Partially resolved (P14, BL-026)**: server-side `POST .../query/count` endpoint is shipped and .NET `RemoteTableQuery.CountAsync` uses it. However, the TypeScript `count()` method in `query-builder.ts` still sends `POST .../query` with `limit=0` and reads `rowCount` from the response — it does **not** use the dedicated `/query/count` endpoint. The TS client adoption remains an open follow-up.
- ~~Fluent/public JOIN APIs remain unavailable~~ — ✅ **Resolved (P14 BL-009, P15)**: complete join engine with all five join types (INNER, LEFT, RIGHT, FULL OUTER, CROSS), post-join SELECT/WHERE/ORDER BY/LIMIT/aggregates, multi-column keys, chained joins (up to 8 tables), Grace hash join with spill-to-disk. Exposed in both .NET `TableQuery` and TypeScript `@aouda/client` query builders.
- ~~Bool predicate overload parity~~ — ✅ **Resolved (P14, BL-038)**: `ConstBool`, `ColumnRef.Eq/Ne(bool)` added.
- ~~Guid PK mixed-type comparison failure~~ — ✅ **Resolved (P14, BL-039)**: added `IsGuid`/`CompileGuid` path in `RowFilterEngine`.
- ~~Nullable timestamp update failure~~ — ✅ **Resolved (P14, BL-040)**: deletion mask applied to validity bitmap.
- ~~A filtered read of a cold segment returned type defaults instead of `NULL`~~ — ✅ **Resolved** (**BL-613, 0.1.35**): a query with a `where` clause against a segment that had aged out of memory read every nullable fixed-width column back as its type's default — `Guid` as all-zeros, `Int32`/`Int64`/`Date`/`Double`/`Decimal` as `0`, `Bool` as `false`, `Timestamp` as `0001-01-01`. The same rows read **without** a `where` clause were always correct, and `String` columns were never affected. Nothing was lost on disk: the affected rows return the correct `NULL` once you are on a build carrying this fix — no repair or reload is needed. ⚠️ **If you are on an earlier build and a query result looks like a missing foreign key rather than a null one**, this is the likeliest cause; it is invisible in `/health` and needs no restart to appear or disappear, because it follows whether the data happens to be resident in memory.
- ~~An `ORDER BY` + `LIMIT` query returned type defaults instead of `NULL`~~ — ✅ **Resolved** (**BL-615, 0.1.35**): a single-column `orderBy` with a `limit` read every nullable fixed-width column back as its type's default — the same symptom as the entry above, through a different query path. ⚠️ **This one did not depend on memory residency**: it was equally wrong on freshly-written data, so any ordered, limited page of a table with a nullable column was affected. Unaffected: the same query without a `limit`, and `String` columns. Nothing was lost on disk — affected rows return the correct `NULL` once you are on a build carrying this fix, with no repair or reload. Sort order itself is unchanged: a `NULL` in the *sort* column still orders as its type's default, which remains a separate question from how it is reported. (**BL-755, next train**: it no longer does — a `NULL` sort key orders last ascending and first descending, on every column type and every tier.)
- Cold-path pruning is restored with cross-column page pruning (`P7-BL025`); further tuning remains normal performance work, not a correctness blocker.

### New capabilities (P15/P16)

- **Extended filter operators (P16 H.2)**: TypeScript client now supports `in()`, `notIn()`, `like()`, `isNull()`, `isNotNull()`, `between()` in addition to the six comparison operators.
- **Aggregate query builder (P16 H.1)**: TypeScript client supports `sum()`, `min()`, `max()`, `count()`, `groupBy()`, `groupAggregate()`. ⚠️ Until **ColumnarRead S16 (next train)** the builder sent a field the server ignored, so these returned plain rows; they now send `aggregates` / `groupBy`.
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
- `src/Aouda.Engine.Storage/Query/Scan/TableScan.cs` (**ColumnarRead, next train**; `QueryEngine.cs`, `QueryBatch.cs`, `RowFilterEngine.cs` and `ParallelSegmentScanner.cs` are deleted)
- `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs`
- `src/Aouda.Engine.Core/Query/Scan/PredicateProgram.cs`
- `src/Aouda.Engine.Diagnostics/Perf.cs`
- `src/Aouda.Client/RemoteTableQuery.cs`
- `src/Aouda.Client/RemoteConditionBuilder.cs`
- `src/Aouda.Client/Internal/QueryMessageBuilder.cs`
- `aouda-client-ts/src/query-builder.ts`
- `aouda-client-ts/src/types.ts`
- `tests/Aouda.Server.Tests/QueryIntegrationTests.cs`
- `tests/Aouda.Server.Tests/QueryTranslatorTests.cs`
- `tests/Aouda.Engine.Api.Tests/ColumnarRead/` (`ReadRuleOracle*Tests`, `ReadFuzzTests`)
- `tests/Aouda.Engine.Api.Tests/QueryCorrectnessC2IntegrationTests.cs`
- `tests/Aouda.Engine.Api.Tests/C2ScenarioMirrorIntegrationTests.cs`
- `aouda-client-ts/tests/query-builder.test.ts`

## 2.20 What is missing from this document? (meta completeness)

- This document validates core query execution paths with targeted suites, but does not include a fresh full-suite run across all query-adjacent test projects in this pass.
- P14 query-related work is represented through protocol/code/backlog evidence (not a dedicated P14 query report in the audited set).
- Backlog contains some historical entries whose status may not reflect current shipped behavior (for example ORDER BY API exposure); backlog hygiene can be improved separately.
