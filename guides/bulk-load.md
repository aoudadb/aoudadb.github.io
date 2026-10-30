---
title: "Bulk Load"
nav_order: 17
parent: "Guides"
---

# Aouda Functionality: Bulk Load

Document status: Complete
Primary owner: Engineering
Last updated: 2026-10-22

Coverage phases: P20, BL (Post20-S1, Post20-S3), P31, P46
Primary task folders: `docs/tasks/P20/`, `docs/tasks/BL-COMPLETION.md`, `docs/tasks/P31/`, `docs/tasks/P46/`
Primary ADRs: `docs/decisions/0030-bulk-load-replication.md`, `docs/decisions/0036-bulk-load-mq-refresh.md`
Related functionality docs: `docs/dev/Functionality-Write-Path-Durability.md`, `docs/dev/Functionality-Replication-And-Clustering.md`, `docs/dev/Functionality-Server-And-Multi-Database.md`, `docs/dev/Functionality-TypeScript-Client.md`, `docs/dev/Functionality-Studio.md`, `docs/dev/Functionality-Graph-And-Vector.md`

---

## Start Here

If your question is "How do I bulk load data safely with commit semantics?", start with:
- `2.7` (mental model and invariants)
- `2.11` (`.NET` + HTTP + CLI surfaces)
- `2.12` (single-table, multi-table, and identity-insert seed playbooks)

If your question is "What is implemented vs incomplete?", jump to:
- `2.4` (availability status)
- `2.5` (phase coverage matrix)
- `2.6` (capability coverage matrix)

If your question is "How replication behaves for bulk load?", jump to:
- `2.8.1` path B (primary commit to replica fetch/apply)
- `2.13` (operability and metrics)
- `2.18` (known limitations)

| If you need to know... | Go to section |
|---|---|
| Zero-config defaults | `2.3` |
| Config keys and allowed values | `2.10` |
| API/CLI and protocol coverage | `2.11` |
| Operational checks and recovery | `2.13` |
| Troubleshooting by symptom | `2.14` |
| Verification/test evidence | `2.15`, `2.16` |
| Known gaps and backlog links | `2.18` |

---

## 2.1 Why this functionality exists

Bulk load exists to ingest large row streams without paying per-row WAL overhead while preserving atomic job semantics, replication visibility, and operational control.

Operationally, this gives Aouda one ingest primitive that can be used by:
- backfills,
- CDC replay,
- AI corpus loads,
- graph/vector population workflows (via the same commit model).

Scope boundaries:
- Bulk load optimizes the ingest path; it is not a replacement for normal row-level write APIs.
- A table with partition or row security is not a per-user bulk-load target. For each such table the load locks, the caller must hold, at `write`, the grant that lifts each restriction the table has: `all-partitions` where it has PLS, `all-rows` where it has RLS. `:begin` and every `:append` refuse otherwise (`403 AUTHORIZATION_DENIED`). An app `service_role` key (`mk_svc_`) and a `db_admin` user hold both on their database (a custom key linked to a user holds that user's); a role assigned to a user can grant them to others, and a holder of `all-rows` alone can load a table that has RLS only. A grant that would allow an ordinary insert does not. A table with no PLS and no RLS policy is unchanged. Every bulk-load route also needs the `bulkload` permission on the database first (`db_admin` has it; `db_writer` does not). (**BL-1031, 0.5.0; BL-1227, next train**) See [Visibility is granted](../auth/authorization.md#visibility-is-granted-all-partitions-and-all-rows).
- It guarantees atomic commit at the job boundary (`BulkLoadCommitted`), not partial "progressively visible" reads.
- It currently does not provide persistent server session reconstruction across restarts (see `2.18`, `BL-067`).

---

## 2.2 Discovery and navigation map

**Role-based map**

| Role | Start here |
|---|---|
| App developer (.NET) | `2.11` `.NET` surface + `2.12` Scenario 1 |
| App developer (HTTP/non-.NET) | `2.11` HTTP protocol + `2.12` Scenario 2 |
| Operator/SRE | `2.10` config + `2.13` observability + `2.14` troubleshooting |
| Replication maintainer | `2.8.1` path B + `2.16` replication tests |
| CLI user | `2.11` CLI + `2.12` Scenario 3 |

**Source map**

| Source type | Evidence |
|---|---|
| Primary completion source | `docs/tasks/P20-COMPLETION.md` (`3.3`, `5`) |
| ADR authority | `docs/decisions/0030-bulk-load-replication.md` |
| Cross-phase closure source | `docs/tasks/BL-COMPLETION.md` (Post20-S1, Post20-S3) |
| Engine/storage implementation | `src/Aouda.Engine.Api/AoudaEngine.BulkLoad.cs`, `src/Aouda.Engine.Storage/BulkLoad/` |
| Replication replay/apply | `src/Aouda.Engine.Replication/Replay/`, `src/Aouda.Engine.Replication/Checkpoint/` |
| HTTP protocol/server behavior | `src/Aouda.Server/Controllers/BulkLoadController.cs`, `src/Aouda.Server/Services/BulkLoadSessionRegistry.cs` |
| .NET client surface | `src/Aouda.Client/AoudaClient.cs`, `src/Aouda.Client/Internal/BulkLoadCoordinator.cs`, `src/Aouda.Client/Exceptions/BulkLoadExceptions.cs` |
| CLI surface | `src/Aouda.Cli/Commands/TableBulkLoadCommand.cs` |
| Representative tests | `tests/Aouda.Engine.Api.Tests/BulkLoad/*`, `tests/Aouda.Server.Tests/BulkLoad/*`, `tests/Aouda.Engine.Replication.Tests/*BulkLoad*`, `tests/Aouda.Client.Tests/BulkLoad/*` |

---

## 2.3 Defaults and zero-config behavior

| Setting / behavior | Default | Practical impact |
|---|---|---|
| Engine `ReplicationMode` | `LogShipSegments` | Emits per-segment (`BulkSegmentCommitted`) and closing (`BulkLoadCommitted`) WAL frames. |
| Engine `WriteConcern` | `WriteConcern.One` | Commit returns after primary durability; multi-replica barriers are not fully wired in engine path yet. |
| Engine `WriteConcernTimeout` | `5m` | Timeout marks concern failure; committed data is not rolled back. |
| Engine `ConflictPolicy` | `Block` | Concurrent writes wait on bulk-load table lock instead of immediate failure. |
| Engine `DeferIndexBuild` | `true` | Deferred CSC/quantization/PK reconcile work can continue after row-stream commit. |
| Engine `LockAcquisitionTimeout` | `30s` | Table-lock wait before conflict behavior applies. |
| Engine `BulkLoadResumeWindow` | `null` -> watchdog default `5m` | In-flight jobs are aborted by watchdog after window expiry. |
| Server `Aouda:BulkLoad:MaxRowsPerAppend` | `100000` | Hard cap per `:append` call. |
| Server `Aouda:BulkLoad:MaxQueuedAppendBytes` | `67108864` (64 MB) | (**IngestAtSpeed S10, 0.1.40**) How many bytes of decoded rows a job may hold for the engine before an `:append` waits (TCP backpressure follows). The queued rows are charged to the memory governor. One batch always fits an empty queue. Before this, the queue was bounded at `4 × MaxRowsPerAppend` rows, whatever their width, and charged nothing. |
| Server `Aouda:BulkLoad:SessionRetentionMinutes` | `10` | Completed/failed/aborted sessions remain queryable for 10 minutes before sweep. Idempotency does not depend on this (see the next row). |
| Server `Aouda:BulkLoad:IdempotencyWindowMinutes` | `10` | How long after **commit** a `:begin` with the same idempotency key answers with the committed job (`alreadyCompleted: true`) instead of loading again. This holds after the session has been swept and after a server restart, because committed keys are journalled per database (`bulk-load-idempotency.log`; **Lead S20a, 0.6.0**: the key is in the job's commit record itself — the catalog record that publishes its segments — so nothing is written after the commit and a crash right after it cannot lose the key; the side file is gone, and a data directory written before this release is refused at open, catalog format 11). (**IngestAtSpeed S02, 0.1.40.** Before this, the setting was read nowhere: a key stopped matching once `SessionRetentionMinutes` swept its session, and at any restart. A retried `:begin` then committed the whole window a second time.) |
| Server `Aouda:BulkLoad:AllowWritePermission` | `false` | Bulk load remains admin-only unless compatibility mode is enabled. |
| Cluster `Aouda:BulkLoad:ForceLogShipBulkLoad` | `false` | When true, non-log-ship replication modes are rejected. |
| Client `AppendBatchSize` | `50000` | Client sends up to 50K rows per append, then honors server lower cap if returned. |
| Client `WriteConcern` | `Acknowledged` | Maps to server `acknowledged` commit concern request. |
| Engine / client `IdentityInsert` | `false` | Default bulk-load path **allocates** autoIncrement IDs: a missing, `null` or `0` value gets the next id from the column's counter, as an ordinary insert does, and an explicit non-zero value is stored as given (**IngestAtSpeed S02, 0.1.40**; before, such rows were stored as `0`). Set `true` for seed/reseed with explicit IDs (including `0`); the counter advances only after a successful commit. |
| Server `Aouda:BulkLoad:TargetSegmentBytes` | `67108864` (64 MB) | Accrued bytes at which a bucket seals into a segment — matches every other segment the engine writes. |
| Server `Aouda:BulkLoad:IngestBufferBudgetFraction` | `0.04` | Fraction of the governed memory budget one job's ingest buffers may hold, floored at 8 MB. As of P45, the ceiling is no longer a fixed 256 MB — it grows with the server's own memory governor (shared with other concurrent loads and background work), so a well-provisioned host's fraction actually means something. Nothing changes on a small host, where `0.04 × governed` was already under 256 MB. |
| Server `Aouda:BulkLoad:MaxIngestBufferBudgetBytes` | `0` (derive, per above) | Set to a specific byte count to pin the ceiling explicitly — `268435456` reproduces the pre-P45 fixed 256 MB behavior exactly. |
| Server `Aouda:BulkLoad:FlushConcurrency` | `1` | Server-wide bound on concurrent bulk-load segment-write I/O, shared across every in-flight job. Fixed by measurement, not core count — a higher value buys commit latency the phase does not need, at the expense of concurrent-query p95. (**LoadScan, 0.5.0**) It bounds how many segment writes run at once; inside one, the segment's columns are encoded and written in parallel on up to the load's CPU share — a bulk load is `Ingest` work, half the schedulable cores — for a segment of four or more pages. |
| Cluster `Aouda:BulkLoad:EmitFramesOnSingleNode` | `false` | On a database whose `ReplicationMode` is `DoNotReplicate`, a single-table `LogShipSegments` load writes no `BulkSegmentCommitted`/`BulkLoadCommitted` WAL frames — no per-segment re-read/hash. `true` restores frames there. ⚠️ (**BL-1118**) It is the **database's replication mode**, not the server's topology, that decides: a database left at the default `Replicate` writes frames for every load even when the server has no replica. A multi-table load always writes them (one commit point across its tables), and an `os` load never does. |
| Cluster `Aouda:BulkLoad:JobShapeWarnSegmentThreshold` | `64` | Segment count above which, combined with a low median rows/segment, a job's commit logs one advisory warning. See `2.13`. |
| Cluster `Aouda:BulkLoad:JobShapeWarnMedianRowsPerSegmentThreshold` | `1000` | Median rows/segment below which the same warning can fire. |

---

## 2.4 Availability status

### Available now

- Engine bulk-load entry point: `AoudaEngine.BulkLoadAsync` (streaming/list overloads), including multi-table discriminator handling and force-abort helper.
- Storage coordinator and lock manager: `BulkLoadCoordinator`, `TableLoadLockManager`, `BulkLoadCommitMarker`.
- WAL contract implemented with tags `60/61/62`: `BulkSegmentCommitted`, `BulkLoadCommitted`, `BulkLoadAborted`.
- Replica-side bulk-load state machine in replay path: `BulkLoadReplicaCoordinator` + `FrameApplier` handlers.
- HTTP endpoints shipped:
  - `POST /api/databases/{db}/bulk-load:begin`
  - `POST /api/databases/{db}/bulk-load/{jobId}:append`
  - `POST /api/databases/{db}/bulk-load/{jobId}:commit`
  - `POST /api/databases/{db}/bulk-load/{jobId}:abort`
  - `GET /api/databases/{db}/bulk-load/{jobId}`
  - `GET /api/databases/{db}/bulk-load:list`
  - `POST /api/databases/{db}/bulk-load:force-abort`
- Operator watchdog path: `BulkLoadResumeWatchdog` lifecycle integration at engine open/dispose.
- .NET client surfaces:
  - `AoudaClient.BulkLoadAsync`
  - `AoudaClient.BulkLoadMultiTableAsync`
  - `RemoteTableQuery.BulkLoadAsync`
  - `AoudaTable<T>.BulkLoadAsync`
  - (**Lead S13, 0.6.0**) `AoudaClient.BulkLoadAsync` / `RemoteTableQuery.BulkLoadAsync` over `ColumnBatch`es (a stream, a list
    or one batch) and `AoudaClient.BulkLoadMultiTableAsync` over a stream of them; see
    [Column batches (C#)](#column-batches-c-lead-s13-060).
- Typed client exception family for lock/cursor/discriminator/options/duplicate-PK failures.
- CLI shipped for both single and multi-table:
  - `aouda table bulk-load`
  - `aouda bulk-load`
- **Materialized Query auto-refresh after bulk-load (P31 / ADR 0036, ingest-fed path P46):**
  - `PostLoadMqBehavior` option on `BulkLoadOptions`: `Auto` (default) accumulated, until **WorkloadCore S10** (next bullet), every affected MQ of all four types **during** the load's own pass and published at commit — except (**BatchFirst S12, 0.1.40**) when every query over the table is an `Aggregate` or `LatestPerKey`/`FirstPerKey` the engine can fold: then the load writes only the table, and the table's pass (the one a `Deferred` load waits for) starts at the commit and folds the load into every query at once. (**ColumnarCore S12, 0.2.0**) Such a load was maintained **in its own commit**: its queries, and the queries built on them, were written before the load returned, with `mqRebuildStatus` already `completed`. (**WorkloadCore S09, 0.3.0**) That is gone: the load still folded its rows as its segments were written, but the table's pass wrote its queries from that fold **after** the commit, in the background, as for every other `Auto` load (**WorkloadCore S10, 0.3.0**: the load no longer folds anything; see the next bullet). What you see: the handle (and the `:commit` response) comes back with `mqRebuildStatus` `pending` or `inProgress`; the server's `:commit` waits for the queries up to `mqWaitMs` (`MqWait` in `Aouda.Client`; default 30 s in 0.3.0, **0 — no wait — from the 0.4.0**, LoadSpeed M.2) and says in `mqStatus` whether they were current by then. `MqRebuildCompleted` still resolves only when the queries **and the queries built on them** are current; until then each reports `isStale`, a reason naming the pending load, `currentLag` and `pendingDeferredJobs`. Loads that commit while a pass runs are taken together by the next one. A table with any other query (a filter, a direct top-N) kept the accumulate-during-the-load path until **WorkloadCore S10** (next bullet); `Skip` creates no sinks and leaves existing results as they were — and marks every affected query **stale**, so `staleOnly` finds them and a restart before you refresh rebuilds them rather than reattaching a result missing this load's rows (BL-474). See [What a `Skip` load leaves behind](materialized.md#what-a-skip-load-leaves-behind). `Deferred` (**BatchFirst S08, 0.1.40**) is `Skip` with a record: the load writes only the table, the queries are marked behind, and the job is kept as pending so the engine can bring every query on the table current in one pass over the load's segments — see [Deferred loads and the table's pass](#deferred-loads-and-the-tables-pass) below and [Deferred loads](materialized.md#deferred-loads). (**LoadSpeed K31, 0.4.0**) `Deferred` is gone: folded into `Auto`, which now leaves a loading table's pass to the quiet period the same way; `"deferred"` is refused `400`.
  - (**WorkloadCore S10, 0.3.0**) **One maintenance path.** Every load into a table with materialized queries, except a `Skip` load, records a pending job, and the table's pass is its maintenance: a fold of the job's segments for every query the fold can plan, the job's rows applied as inserts for any other query directly over the table, a rebuild for the rest (**WorkloadCore S17, 0.3.0**: by a background rebuild job after the pass, so the table's other queries are not held behind it). `Auto` starts each written table's pass as soon as the load commits — multi-table and transform loads included — and `:commit` waits for it up to `mqWaitMs` and answers `mqStatus` as before; `Deferred` leaves the pass to the quiet period (2 s quiet, at most 60 s) — until **LoadSpeed K31** (0.4.0), which folds it into `Auto`. A load does no materialized-query work while its rows stream, so its segment writes cost what they cost on a table without queries, and it is no longer paced to a materialized-query drain. The accumulate-during-the-load ("ingest-fed") path is gone, and with it the fold built inside the load's segment writes, the merging of waiting publishes, the heap-pressure deferral and the drain pacer. `:refresh`, restore and a fallback rebuild read the table, as before. Until its pass has run, a query the load reaches is readable and behind — `isStale: true`, `pendingDeferredJobs` ≥ 1, `current: false` — but not marked stale: the load owes it work, it does not leave a hole.
  - (**Lead S27b, 0.6.0**) A query whose `currency` is `rebuild` is never folded or replayed into: the load's pass rebuilds it (one scan of the table with the table's other rebuilds). And a load emits **no change events** on the table it loads — a subscriber to the table sees none of its rows (see [Real-time](real-time.md#27-core-concepts-and-mental-model)); a subscriber to a query's result sees the result's changes.
    (**BL-980, 0.4.0**) A pending-job record without its commit time (only an older build wrote one) is set aside as
    corrupt when the database opens, and every materialized query of the database is rebuilt rather than caught up from it.
  - (**LoadSpeed M.3, 0.4.0**) **`auto` coalesces while a table is loading.** An `auto` load whose table is busy — another load
    in flight on it, an earlier load's job on it still pending, or a load into it committed in the last 2 s — does not start the
    table's pass at its commit: its job waits with the others, and the table is caught up in **one** pass (a fold of every waiting
    job's segments, in waves of bounded memory) once loading into it has been **quiet for 2 s**, or once its oldest waiting job has
    waited **60 s** while loads keep coming. The 60 s count from the oldest load no pass has taken in yet, not from the last pass, so
    however long a migration runs, its last loads are caught up 2 s after it stops. Meanwhile the queries are readable and report
    behind (`isStale`, `pendingDeferredJobs`, `current: false`; `:commit` answers `mqStatus: "behind"`), and `MqRebuildCompleted`
    resolves when the catch-up has brought the load in. If a query the load reaches is in `error` — its rebuild failed — it cannot take
    the load in: once a pass after the commit has left the load owed only by queries in `error`, the load's `mqRebuildStatus` becomes
    `failed` (as a load maintained at its commit always reported), and those queries go on being retried, or are brought back by
    `:refresh`. A load into a quiet table still starts its pass at its commit, as before. Measured on a 2 GB server (15.3 M trades and
    30 M quotes, 13 queries): the trade load ran at **253 k rows/s** (67 k on 0.3.0; 266 k with no queries), at **37.4 CPU-s per
    million rows** (48.2), and all 13 queries were current **440.5 s** after the load started (650 s on 0.3.0) — the time of the
    `skip` + pooled-refresh recipe below (441.5 s), with identical results.
- **A table with retention, or a windowed result, is loaded one segment per time slice and never spilled; rows below its horizon
  are counted in `:commit`'s `expiredRows`, not written** (**Horizon, 0.5.0**). See
  [Loading a table with retention](#loading-a-table-with-retention).
- **Identity-insert on bulk-load (BL-131):**
  - `BulkLoadOptions.IdentityInsert` / wire `options.identityInsert` on `:begin`.
  - When `true`: validate every autoIncrement column on every row; store values as-is (including `0`); no ID allocation; `EnsureMinimumValue` only after successful `RunAsync` / commit.
  - Default path (**IngestAtSpeed S02, 0.1.40**): a missing, `null` or `0` autoIncrement value is **allocated** the next id, exactly as on insert; explicit non-zero ids are kept. Ids are reserved in blocks of 4,096, so an aborted load or the tail of the last block leaves a gap in the sequence, never a reissued id. Before this release the default path stored those rows as `0` and allocated nothing, so a bulk-loaded table's primary key was not a key.
  - Ordinary insert identity-insert is documented in [HTTP API insert](../reference/http-api.md) and [Getting Started](../getting-started/index.md) (BL-130).
  - `BulkLoadJobHandle.MqRebuildStatus`: tracks rebuild state (`Pending / InProgress / Completed / Skipped / Failed`; C#/TS clients also expose `Unknown` — see below, **BL-419, 0.1.22**).
  - `BulkLoadJobHandle.MqRebuildCompleted`: `Task` that resolves when all dependent MQ rebuilds finish.
  - (**WorkloadCore S09, 0.3.0**) `:commit`'s bounded wait for the load's queries: `BulkLoadOptions.MqWait` (`TimeSpan?`; null = the server's default: 30 s in 0.3.0, no wait (**LoadSpeed M.2, 0.4.0**)) / wire `mqWaitMs`, and `BulkLoadJobHandle.MqStatus` (`MqCommitStatus`: `Unknown`, `None`, `Current`, `Behind`, `Skipped`; `Deferred` until the 0.4.0, **LoadSpeed K31**) and `MqFrontierToken` in `Aouda.Client`; `mqWaitMs`, `handle.mqStatus`, `handle.mqFrontierToken` and `handle.mqWaitedMs` in `@aouda/client`. `Unknown` is an older server's answer. See [HTTP API — `:commit`](../reference/http-api.md#post-jobidcommit).
  - (**LoadSpeed M.2, 0.4.0**) **`mqWaitMs` defaults to `0`**: `:commit` answers as soon as the load is durable and does not wait for its queries unless the request says how long (it waited up to 30 s). A load whose queries are still catching up answers `mqStatus: "behind"` with `mqFrontierToken`; that is not an error. To go on only once they are current, send `mqWaitMs` (up to `600000`), or read with the commit's `token`, which waits for them.
  - (**WorkloadCore S16, 0.3.0**) The wait does not wait for a query only a rebuild can bring current (holed, in `Error`, or waiting for memory to rebuild): `mqStatus` is `"behind"` as soon as the others are current, instead of after the whole `mqWaitMs`.
  - (**WorkloadCore S16, 0.3.0**) **`:append` can be paced.** When the database's debt — WAL fill, materialized-query maintenance lag, unflushed rows or hot bytes — is past its soft line, each batch of an `:append` waits (at most 10 s) before it is queued — whatever the batch's size (**WorkloadCore group 5 review, 0.3.0**) — so the load settles at the rate the debt drains; see the sizing guide, *Debt slows the writer*. An `:append` whose load already failed for capacity answers `503` with `Retry-After`, as `:commit` does, rather than `409`. A load's buffer growth refused for a moment's queue no longer caps the buffer for the rest of the load.
  - (**BL-831, 0.3.0**) **A column-batch `:append` asks for its memory before it decodes.** Each column's array is a grant from the memory queue first (waiting at most one sampling tick), so when memory is short the `:append` is refused `503 MEMORY_BUDGET_EXCEEDED` with `Retry-After` **before** the frame is decoded, instead of failing on the heap part-way through it (`500`). The session stays open and the rows queued before the refusal stay credited: wait `Retry-After` and resume with the same idempotency key from the frame `:begin` answers (`nextSequence`, **Lead S21a, 0.6.0**: it was `resumeFromRow`, else `rowsDurablyCommitted`). JSON column-array bodies (NDJSON bodies, until **Lead S12, 0.6.0**) take no such grant.
  - (**BL-831, BL-928, 0.3.0**) **A `:commit` that runs out of memory is a `503`, never a `500` or a damaged segment.** A commit whose spill merge meets the managed heap's hard limit answers `503` with `Retry-After` (it answered `500 INTERNAL_ERROR`), and a merge that runs out of memory part-way through a row is refused with nothing published — it used to seal a segment whose columns held different row counts. As for every refused `:commit`, the session is failed and nothing was applied: run the load again from `:begin`.
  - (**release blockers, 0.3.0**) `mqWaitMs` does not wait on a query that is behind only because a query it is built on (its upstream) is being rebuilt — waiting cannot bring it in, so `mqStatus` is `"behind"` as soon as the others are current. And a wait that itself fails (the heap, say) answers the commit as committed with `mqStatus: "behind"`: the load is durable, so it must not be sent again (it was answered `503` "not applied", and a client that resent it loaded the rows twice).
  - Replica coordinator: `MqRebuildScheduler` delegate triggers rebuild after all segments fetched.
  - Explicit on-demand refresh: `engine.RefreshMaterializedQueryAsync(name, ct)` and `POST .../materialized-queries/{name}:refresh`.
  - **After a `Skip` load, refresh once — pooled, not per query (BL-474).** Queries over one source table are rebuilt from a single traversal of it, so `POST .../materialized-queries:refresh` with `{ "sourceTable": "EquityTrade", "staleOnly": true }` decodes `EquityTrade` once for all of its rollups instead of once each. `staleOnly` selects exactly what the `Skip` load left behind. See [Materialized queries — pooled refresh](materialized.md#211a-refreshing-several-queries-at-once-pooled-refresh).
  - C# client: `client.MaterializedQueries.RefreshAsync(name, awaitCompletion, ct)`.
  - TypeScript client: `client.materializedQueries.refresh(name, { await: true })`.
  - CLI: `aouda mq refresh <name> [--await]` and `--skip-mq-refresh` on `aouda table bulk-load`.
  - `mqRebuildStatus` field in bulk-load job status response, and (**BL-419, 0.1.22**) in the `:commit` response too.

> **Do not hand-refresh an MQ after a Bulk Load.** With `postLoadMqBehavior: "auto"` (the default),
> affected materialized queries are brought current after the commit, in the background, by the
> table's pass, which starts at the commit — or, while the table is loading, once it has gone quiet (**LoadSpeed M.3, next
> train**) (**WorkloadCore S10, 0.3.0**; until S10 most were
> accumulated during the load's own pass and published, and in 0.2.0 a table of aggregates and
> latest / first-per-key queries was written before the load returned, **ColumnarCore S12**) — there is nothing left to trigger. `:commit` waits for them up to `mqWaitMs`
> (by default not at all, **LoadSpeed M.2, 0.4.0**) and says in `mqStatus` whether they were current; read with the commit's `token` to wait for them. Calling `POST .../materialized-queries/{name}:refresh` yourself
> for a just-loaded table either runs the pass the query is owed (which was starting anyway) or, once
> it has run, re-scans the whole source table. The wait after commit is usually short. Wait on `mqRebuildStatus` instead — the C# client's
> `BulkLoadJobHandle.WaitForMaterializedQueriesAsync()` and the TypeScript client's
> `handle.waitForMaterializedQueries()` (both **BL-419, 0.1.22**) do this polling for you; both
> return (rather than spin) on the terminal `"unknown"` value a job with no live session (e.g. after
> a server restart) reports, since the WAL alone cannot say more. Some queries are rebuilt rather
> than folded or applied (a query the fold cannot plan, or one already behind for another reason) —
> (**WorkloadCore S17, 0.3.0**) by a background rebuild job the pass starts once it has finished,
> and `MqRebuildCompleted` waits for it; that rebuild is still the load's own, not a reason to call `:refresh`.
>
> **`postLoadMqBehavior: "skip"` opts out of this entirely, not partially.** With `skip`, the load
> records no pending job and its tables get no pass — every affected MQ is left stale, stamped
> `MqRebuildStatus.Skipped`, until you refresh it. Refresh **once per source table, pooled**, at the end —
> `POST .../materialized-queries:refresh` with `{ "sourceTable": "…", "staleOnly": true }` — not once per query and
> not after every load: each refresh rebuilds from a scan of the **entire** source table, not just the newly loaded
> rows. That is the right trade for a migration or an initial load (see
> [Loading a lot of data into tables with queries](#loading-a-lot-of-data-into-tables-with-queries) below) and the
> wrong one for a table you load into every few minutes, which should stay on `auto`.
> (Corrected, **0.4.0** docs.) Earlier versions of this page said such a refresh had no memory governor bound
> and could exhaust server memory on a fine-grained aggregate. That has not been true since 0.3.0: a refresh, single
> or pooled, takes a memory grant before it starts (it can grow to a quarter of the database's budget), spills an
> aggregate's groups to disk when the grant is full, and is refused `503` with `Retry-After` — the queries left
> readable and behind — when memory is short at the start.

### Deferred loads and the table's pass

(**LoadSpeed K31, 0.4.0**) **`postLoadMqBehavior: "deferred"` is gone — use `"auto"`.** Since `auto` coalesces while a table
is loading (below) and `:commit` no longer waits by default (`mqWaitMs` 0), `deferred` differed from `auto` in only two things: its
`:commit` never waited, even when `mqWaitMs` asked it to, and a load into a quiet table did not start its pass until the table had
been quiet for 2 s. A server from the 0.4.0 refuses `"deferred"` at `:begin` with `400 BULK_LOAD_INVALID_OPTIONS` ("use
'auto'"), and `:commit` never answers `mqStatus: "deferred"` or `mqRebuildStatus: "deferred"`. Everything below about the pending
job and the table's pass is how an `auto` load is maintained; read "a deferred load" as "a load whose pass has not run yet". To have
`:commit` return without waiting, leave `mqWaitMs` at its default, 0.

**BatchFirst, 0.1.40.** `postLoadMqBehavior: "deferred"` (`PostLoadMqBehavior.Deferred`) was for
loads large enough — or frequent enough — that paying for the materialized queries once per load
is the wrong trade. The load writes only the table (the fastest path the engine has) and records a
**pending job**: which segments it wrote and which queries owe them. Its queries stay readable and
say they are behind: `isStale: true` with a reason, `pendingDeferredJobs` above zero.
(**WorkloadCore S10, 0.3.0**) Every load but a `skip` one now records such a job; `deferred` differed from
`auto` only in when its pass started. The queries it reaches are not marked stale: they are owed work, not holed,
so `current` is `false` and the reason reads "N bulk load(s) into its source are pending the table's pass…"
(before: "a bulk load committed with PostLoadMqBehavior.Deferred; its rows are pending the deferred pass…"), and
`staleOnly` on a pooled refresh no longer selects them. While they are
behind, a read of the table is not routed to them — the table answers, with the loaded rows
(**ColumnarRead S18, 0.3.0**; a `skip` load's queries likewise).

The table's **deferred pass** then brings them current: one read of every pending job's segments,
every foldable query (`aggregate`, `latestPerKey`/`firstPerKey`) folded in the same read and written
onto its result, a filter or direct `topNPerGroup` given the jobs' rows as inserts, any other query
rebuilt (**WorkloadCore S17, 0.3.0**: by a background rebuild job after the pass, not inside it — the table's
other queries are current without waiting for it), and queries cascaded from them (a `topNPerGroup` over a rollup) caught up. A pass that does not start at a load's commit runs
(an `auto` load's starts at its commit, **WorkloadCore S10, 0.3.0** — while its table is quiet; while it is loading, an `auto`
load's pass waits like this, **LoadSpeed M.3, 0.4.0**, as a `deferred` load's always did until the 0.4.0):

- once bulk ingest into the table has been **quiet for 2 s**, or the oldest pending job has waited
  **60 s**, whichever comes first — many back-to-back loads, one pass;
- at once when you `:refresh` any query that owes a pending job;
- at once before an **update, delete or upsert** of the table — a change to a row a pending load
  wrote cannot go down the incremental path until the query holds that row. The first such change
  after a deferred load therefore waits for the pass. Plain inserts are not delayed.

Every row is incorporated exactly once: never twice by two passes, never by both a pass and a
refresh, and not lost across compaction (a pending job's segments are not merged until it is
incorporated) or a restart (pending jobs are durable; a query that still owes one has no ready
marker, so the restart rebuilds it).

**When it was the choice** (0.1.40 to 0.3.x; refused `400` from the 0.4.0 — use `auto`). `auto` kept queries current as each
load committed; `deferred` was for loading a lot at once (an initial import, a backfill, a nightly batch) and letting the queries
catch up a few seconds after the last load. (**LoadSpeed M.3 / K31, 0.4.0**: `auto` makes that choice per table as it loads — a
stream of loads is caught up once, a single load at its commit — so there is nothing left to choose.) Both ran the same pass over the same segments
(**WorkloadCore S10, 0.3.0**: `auto` starts it at each commit; before S10, `auto` folded a table of aggregates and
latest-per-key queries as its segments were written, and accumulated other queries during the load), so the
difference is *when* the work is paid — per load, or once for many — not how much there is.

### Planned / proposed

| Capability | Evidence | Current state |
|---|---|---|
| Full server-side in-flight session reconstruction after restart | `BulkLoadSessionRegistry.AdoptInFlight` comment + `BL-067` | Not implemented (returns `null`) |
| Complete multi-node write-concern barrier in engine path | `AoudaEngine.BulkLoadAsync` comment around `WriteConcern` handling | Partial (throws timeout for non-`One` on multi-node) |
| Accurate topology-based skip-replication guard in HTTP layer | `BulkLoadController.IsMultiNodeCluster` stub | Not implemented (currently hardcoded single-node) |
| P2P replica segment fan-out | ADR 0030 open questions, `BL-066` | Not implemented |
| Segment-level dedup on retried loads | ADR 0030 open questions, `BL-069` | Not implemented |

### Reserved / not yet wired

| Surface | Status | Evidence |
|---|---|---|
| `ReplicationMode.MarkForSnapshot` | Enum/API value exists; operationally reserved path | `src/Aouda.Engine.Api/BulkLoadOptions.cs` |
| `BulkLoadInFlightSnapshot`/`ResumedFromDurableCursor` restart adoption path | DTO and model exist, but no reconstruction path | `BulkLoadSessionRegistry.AdoptInFlight` |
| Cluster-wide in-flight admin endpoint from ADR ops section | ADR intent exists; not present in controller routes listed above | ADR 0030 operational changes vs current `BulkLoadController` |

---

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P20 (`3.3`, `5`) | `docs/tasks/P20-COMPLETION.md` | Core bulk-load primitive, WAL frame model, HTTP `begin/append/commit/abort/status`, .NET client + CLI surface | Multi-node durability polish, restart reconstruction maturity | `BL-066`, `BL-067`, `BL-069` |
| BL Post20-S1 | `docs/tasks/BL-COMPLETION.md` Post20-S1 | Replication completion: replay coordinator, checkpoint segment fetch protocol (removed, **BL-1193, next train**: nothing used it), force-log-ship cluster setting, watchdog lifecycle integration | Further replication scalability behaviors | `BL-066` |
| BL Post20-S3 | `docs/tasks/BL-COMPLETION.md` Post20-S3 | Admin list/force-abort routes and Studio-facing server support | Studio UX evolution sits outside this repo | (tracked in Studio/task stream) |
| P31 (S1+S2) | `docs/tasks/P31/` | Materialized Query auto-refresh after bulk-load: `PostLoadMqBehavior`, `BulkLoadJobHandle.MqRebuildStatus`/`MqRebuildCompleted`, `RefreshMaterializedQueryAsync`, replica scheduler, HTTP refresh endpoint, C# + TS clients, CLI | Cross-MQ dependency ordering; WebSocket rebuild progress | ADR 0036 |
| P46 | `docs/tasks/P46/` | Ingest-fed materialization: `Auto` loads accumulate affected MQs during the load's own pass (all four types); scan-fed path retained for `:refresh`, fallback, restore (**WorkloadCore S10, 0.3.0**: replaced by the table's pass) | Incremental maintenance from cold-segment arrival outside a bulk load; cross-MQ dependency ordering | ADR 0036 D-9…D-15 |

---

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Row-WAL bypass bulk ingest | Yes | No | No | `AoudaEngine.BulkLoad.cs`, `BulkLoadCoordinator.cs` | Segment/job frames carry durability contract. |
| Segment-level WAL frame (`BulkSegmentCommitted`) | Yes | No | No | `WalTag.cs`, `WalPayloads.Encode/TryDecodeBulkSegmentCommitted` | Includes per-file BLAKE3 bytes. |
| Closing-frame atomic commit (`BulkLoadCommitted`) | Yes | No | No | `WalPayloads.Encode/TryDecodeBulkLoadCommitted`, coordinator commit path | Job-level atomic close unit. |
| Abort frame (`BulkLoadAborted`) | Yes | No | No | `WalPayloads.Encode/TryDecodeBulkLoadAborted`, watchdog/force-abort paths | Used by watchdog and operator abort. |
| Multi-table atomic bulk load | Yes | No | No | `AoudaEngine.BulkLoadAsync` (`AdditionalTables`), controller `_table` checks | Requires a `_table` discriminator column in the append body. |
| Lock conflict policy (`Block`/`FailFast`) | Yes | No | No | `BulkLoadOptions`, `TableLoadLockManager`, controller errors | Exposed to client/CLI. |
| Durable cursor contract (`rowsDurablyCommitted`) | Yes | Yes | No | Protocol DTOs + controller/client code | Server session cursor is updated at commit; append-time cursor granularity is incomplete in Stage 1. |
| Resume watchdog lifecycle | Yes | No | No | `BulkLoadResumeWatchdog`, lifecycle tests | Default resume window 5 minutes. |
| Replica apply state machine | Yes | No | No | `BulkLoadReplicaCoordinator`, `FrameApplier` handlers | Includes acquired/fetching/staged/committed/aborted. |
| Replica segment fetch | No | No | Yes | — | (**BL-1193, next train**) The checkpoint protocol's unused `0x20`/`0x21` messages and `BulkSegmentFetcher` were removed; a replica's fetch of a load's segments is **BL-1116**. |
| Cluster policy `ForceLogShipBulkLoad` | Yes | No | No | `BulkLoadClusterSettings`, coordinator/controller checks, tests | Rejects skip/snapshot modes when enabled. |
| HTTP admin list + force-abort | Yes | No | No | `BulkLoadController` routes + list-route tests | Powering Studio admin workflow. |
| .NET client API (`BulkLoadAsync`, `BulkLoadMultiTableAsync`) | Yes | No | No | `AoudaClient.cs`, `BulkLoadCoordinator.cs` | Includes progress + deferred work behavior. |
| Typed exception family | Yes | No | No | `src/Aouda.Client/Exceptions/BulkLoadExceptions.cs` | Lock, cursor mismatch, discriminator, duplicate PK, invalid options. |
| CLI bulk-load commands | Yes | No | No | `TableBulkLoadCommand.cs` | Supports single and multi-table commands. |
| Persistent server session recovery across restart | No | No | Yes | `BulkLoadSessionRegistry.AdoptInFlight` stub | Explicitly not implemented yet. |
| P2P replica fan-out | No | No | Yes | ADR 0030 open question, backlog | Primary-centric transfer today. |
| Segment dedup on retry | No | No | Yes | ADR 0030 open question, backlog | Retry may duplicate segment rows. |
| Materialized Query auto-rebuild after bulk-load | Yes | No | No | P31 + P46 ADR 0036, the table's pass (WorkloadCore S10), `BulkLoadJobHandle.MqRebuildStatus` | Default `Auto` starts the table's pass at the commit (all four types; **WorkloadCore S10, 0.3.0** — it accumulated during the load before); `Skip` for multi-step pipelines; queries the pass cannot fold or apply are rebuilt. |
| Explicit on-demand MQ refresh | Yes | No | No | P31 `RefreshMaterializedQueryAsync`, `POST .../materialized-queries/{name}:refresh` | Shadow-build; result table readable throughout with stale data. |
| Replica MQ rebuild after bulk-load | Yes | No | No | P31 `BulkLoadReplicaCoordinator.MqRebuildScheduler` | Triggered after all segments fetched on replica. |
| Identity-insert (`IdentityInsert`) | Yes | No | No | BL-131, `AoudaEngine.BulkLoadAsync`, `BulkLoadOptionsDto.IdentityInsert` | Job-scoped; counter bump only after successful commit; Studio UI out of scope. |

---

## 2.7 Core concepts and mental model

### Core concepts

- **Streaming phase vs commit phase:** rows are appended in chunks — column-batch frames, or JSON column arrays (**Lead S12, 0.6.0**: NDJSON is no longer read) — then closed by a commit call.
- **Durability unit:** durability is represented by WAL-visible segment/job events, not by row-level WAL entries.
- **Durability level** (**Lead S26, 0.6.0**): the target table's
  [durability level](write-durability.md#durability-levels-lead-s26-060) does not change how it is loaded — `strict`,
  `os` and `unlogged` tables load alike. (**Lead S26c, 0.6.0**) A load has a level of its own, `strict` or `os`, which
  follows the database's level, not the table's: see [A load's durability](#a-loads-durability-strict-or-os-lead-s26c-060).
  A bulk load into a table at `memory` (the old `MemoryOnly`) is refused, naming the level: "Bulk load is not supported for table
  '…' at durability 'memory'" — a load writes segment files, which a memory table never has.
- **Job-level atomicity:** query visibility is tied to closing-frame commit completion.
- **Replica catch-up model:** replicas consume WAL events and fetch segment files out-of-band. ⚠️ (**Lead S18a, 0.6.0**) A replica that has not fetched every segment of a committed load does not cover that load's token, or any later one, until it has: a read presenting the token waits or is answered `TOKEN_UNSATISFIED` / `TOKEN_FETCH_PRIMARY`, and `GET /admin/replication/status` names the load (`bulkLoadHold`). Today no server wires the replica-side fetch (**BL-1116**), so a replicated database's bulk loads are on its replicas only after a checkpoint re-bootstrap — read them with a token, which sends the read to the primary, or from the primary. ⚠️ (**Lead S20, 0.6.0**) **Bulk-loaded rows are not yet replicated** (**BL-1116**): a replica does not receive a load's segments as it is committed. Load into the primary and read the loaded rows there until this is done.

### Invariants

1. Bulk load bypasses per-row WAL framing by design; this is not optional.
2. A load that reaches `BulkLoadCommitted` has a single, explicit WAL position for commit.
3. Multi-table jobs require a `_table` discriminator column in every append body: each row names its table.
4. `ForceLogShipBulkLoad=true` disallows skip/snapshot replication modes.
5. Aborts are WAL-visible (`BulkLoadAborted`), from either watchdog timeout or operator force-abort.
6. A `strict` load's segment files are fsynced before its commit point — the closing frame, or on a single node the commit record —
   so a committed load survives a power loss (an `os` load's are not: [A load's durability](#a-loads-durability-strict-or-os-lead-s26c-060),
   **Lead S26c, 0.6.0**). The files of a job's segments sync in parallel while the job runs, and the commit waits
   for them (**Lead S20b, 0.6.0**: each segment was synced before its own frame). If the catalog
   registration after the commit point still fails after its retries, the commit call returns an error but the load is **not**
   lost: its rows become visible at the next restart, which catalogues it (`BulkLoadCommittedUncataloguedPinsHeld` counts such
   jobs). Do not re-run such a load blindly: check `:status`, or use an idempotency key. Before this, such a load could be swept
   at the next open. (**BL-765, BL-771, 0.3.0**)
7. A key bulk loaded **after** its delete survives a crash, on every table type (**BL-924, BL-823, 0.3.0**). A load records
   where it committed in the log, and crash recovery re-applies a `Strict` table's delete (logged by key) only to the bulk segments
   loaded before it; on `Recent` / `BestEffort` tables a delete is replayed onto exactly the copies it matched. Before, deleting a
   key, bulk loading it again and crashing before the next checkpoint removed the loaded row.
8. A load into a table with PLS or RLS is refused at `:begin`, and at every `:append`, unless the caller holds at `write` the
   grant for each restriction the table has: `all-partitions` for PLS, `all-rows` for RLS. An app `service_role` key
   (`mk_svc_`) and a `db_admin` user hold both on their database. A server key (`mk_srv_`), a `custom` key not linked to a holder, and a plain
   user are refused, including a caller who holds a partition write grant, and a `db_admin` that is only in the token's claims. The
   refusal names each refused table and the grant it lacks, and starts no session. A job over such a table writes its
   `access_grant_used` audit rows once per credential: at `:begin` (with the `jobId`), and at the first `:append` of another
   credential that appends to the job; never per `:append` after that. (**BL-1031, 0.5.0; BL-1227, next train**)

### What a frame carries is what JSON carries

The C# SDK appends column-batch frames where the server accepts them, and JSON column arrays where a
batch holds something a frame cannot carry (a nested value, a list) (**Lead S12, 0.6.0**: it was
NDJSON, which the server no longer reads). Either way the table ends up with the same values: a frame
gives each number the kind its JSON text would have, a `DateTime` that is not UTC and a
`DateTimeOffset` travel as their JSON text, and a value a frame would have to change is sent as JSON
instead (**BatchFirst S03, 0.1.40**). A load that mixes the two formats mid-stream is still one load,
with one resume cursor.

### Column batches (C#) (**Lead S13, 0.6.0**)

When the data is already columnar (Parquet or Arrow row groups, a data frame, another database's export), `Aouda.Client` loads
it as `ColumnBatch`es (namespace `Aouda.Protocol.BulkLoad`) and skips building a dictionary per row. This is the fast path: each
batch is written to the `:append` body as column-batch frames **straight from its arrays**.

```csharp
using Aouda.Client;
using Aouda.Protocol.BulkLoad;

var batch = ColumnBatch.Of(
    ColumnBatchColumn.FromInt64s("id", ids),                         // long[]
    ColumnBatchColumn.FromStrings("symbol", symbols),                // string?[]: a null element is a null row
    ColumnBatchColumn.FromDecimals("price", prices, scale: 4),       // decimal[] or decimal?[], at the column's scale
    ColumnBatchColumn.FromTimestamps("ts", times));                  // DateTime[] or DateTime?[]

var handle = await client.BulkLoadAsync("trades", batches,          // IAsyncEnumerable<ColumnBatch>, a list, or one batch
    new BulkLoadOptions
    {
        IdempotencyKey = "trades-2026-10-18",
        // The default validation is Coerce: a null in a NOT NULL column that is not a key is stored as the type's default
        // (0, ""), as ClickHouse does. Validation = BulkLoadValidation.Strict refuses the job instead, naming the column and row.
    });
```

**A load coerces by default** (**Lead S27a, 0.6.0**). Unless the load asks for `validation: strict`, a null sent for a NOT
NULL column that is not part of the key is stored as the type's default, not refused — what an insert through `/rows` would refuse.
A key is never coerced, and a column the table does not have is refused at either level. See
[A load's validation](#a-loads-validation-coerce-or-strict-lead-s27a-060).

The factories, the null and absent bitmaps, `ColumnBatchBuilder` and `ColumnBatch.Validate()` are described on the
[.NET Client page](../clients/dotnet.md#6-building-column-batches-lead-s13-060). A multi-table load
(`BulkLoadMultiTableAsync`) takes batches that carry a `_table` string column.

- **How batches map to `:append` bodies.** A body holds up to `AppendBatchSize` rows (capped by the server's `maxRowsPerAppend`)
  and about `MaxAppendBytes` bytes, as consecutive frames closed by the body's end frame. (**Lead S21a, 0.6.0**) The frames
  are numbered across the job's bodies, from 0, so the server applies each one once. Several small
  batches share one body, a frame each; a large batch is cut across several bodies. Batches of a few thousand rows or more load
  fastest, since each batch is at least one frame. Sizing the session itself is unchanged: see
  [Sizing a session](#sizing-a-session-fewer-longer-one-commit).
- **Checked before it is sent.** Each batch is validated before any of it is written: a malformed batch throws `ArgumentException`
  naming the column and row, and the load is not committed. Rows from earlier batches already appended stay in the open session
  until the server reclaims it.
- **A failed load with your own key keeps its table locked until you resume it or abort it.** When you pass an
  `IdempotencyKey`, both SDKs leave a load that fails part-way (a bad batch, a source that throws, an `:append` that fails four
  times) **open**, so that the same call with the same key resumes it. Until then the job holds the table's load lock: other loads
  into the table, and writes queued behind them, wait — for up to `Aouda:BulkLoad:SessionIdleTimeoutMinutes` (**10 minutes** by
  default), after which the sweeper aborts the session and releases the lock. Resume the load, or abort it by its job id
  (`POST /api/databases/{db}/bulk-load/{jobId}:abort`), rather than leaving it for the sweeper. With no key of your own, the SDK
  aborts the job itself — nothing could resume it — except once its commit has been sent, and in C# after an `:append` that failed
  for a transient reason, where `BulkLoadAppendFailedException` hands you the key it used.
- **A failed `:append` is re-sent by the SDK** (**Lead S21a, 0.6.0**). A job's frames are numbered and the server applies each
  number once, so after a connection that dropped, a timeout or a `503`, the SDK sends a `:begin` with the job's key (which stops
  the server's stale request and answers the job's `nextSequence`) and then the same body again; the frames the server already
  applied are skipped, not loaded twice. Only after four attempts does it throw `BulkLoadAppendFailedException` (it used to throw
  on the first failure).
- **Resume by frames.** Run the same load again with the same `IdempotencyKey`, the same batches from the start and the same body
  bounds: `:begin` answers with the job's next frame, and the SDK does not send the bodies below it (a body that straddles it goes
  whole, and the server skips its prefix). It checks that the frames it skips carry the rows the server holds, and throws
  `BulkLoadCursorMismatchException` — sending nothing — when they do not (another source, or another `AppendBatchSize` /
  `MaxAppendBytes`). Until **Lead S21a** it resumed by rows, from `resumeFromRow`.
- **The JSON fallback.** A batch with a column no frame can carry (an object column from `ColumnBatchBuilder`) is sent as a JSON
  column-array body of the same rows, after the frames before it. So is every batch when `:begin` does not list
  `column-batch-v2` in `acceptedAppendFormats`. The values loaded are the same either way.
- **Absent is not null, and a bulk load applies no defaults.** A cell marked absent is stored as null, except that an absent
  `autoIncrement` cell is generated (BL-1104, as for any `:append`). An insert (`InsertAsync(ColumnBatch)`) does apply defaults.
- **A bulk load refuses a column its table does not have and a missing key** (**Lead S27a, 0.6.0**; BL-1130, BL-1129: the
  column used to be dropped, the key stored as `0`). A null in another NOT NULL column is stored as the type's default unless the
  load asks for `Validation = BulkLoadValidation.Strict`; see [A load's validation](#a-loads-validation-coerce-or-strict-lead-s27a-060).
- **The arrays are not copied.** A batch's arrays are read while its rows are written, which happens before the SDK asks your
  source for the next batch; reuse them from then on.

The row and object overloads of `BulkLoadAsync` are unchanged and remain the convenient path; they are sent as frames too.

### Column batches (TypeScript) (**Lead S14, 0.6.0**)

`@aouda/client` takes the same thing as `ColumnBatch`es built from typed arrays — `bulkLoad(table, batches)` and
`insert(batch)` — packed into bodies the same way (up to `appendBatchSize` rows, about `maxAppendBytes`, consecutive frames,
a large batch cut across bodies):

```typescript
import { ColumnBatch, column } from '@aouda/client';

const batch = ColumnBatch.of(
  column.int64('id', ids),                // BigInt64Array (or a Float64Array of safe integers)
  column.string('symbol', symbols),       // (string | null)[]
  column.scaledDecimal('price', unscaled, 4),
  column.timestampTicks('ts', ticks),     // BigInt64Array of 100-ns ticks since the Unix epoch; column.timestamp takes Dates
).validate();
const handle = await client.bulkLoad('trades', batchesOf(source), {
  idempotencyKey: 'trades-2026-10-19',
  // validation: 'coerce' is the default — a null in a NOT NULL column that is not a key is stored as 0 / ''; 'strict' refuses the job.
});
```

The factories and `validate()` are on the [TypeScript Client page](../clients/typescript.md#column-batches-lead-s14-060).
What it shares with C#, and what changed for it in the same session:

- **A transport policy never re-sends an `:append`** (until Lead S14 a `retryPolicy` re-sent it — a duplicate-rows hazard). Since
  **Lead S22, 0.6.0**, the SDK's own recovery does, safely: after a lost connection, a timeout or a `503` it asks the server
  where the job is (a `:begin` with the job's key) and sends the same body again, up to 4 times; the server skips the frames it
  holds, so a body sent twice is applied once — as the C# SDK has done since Lead S21a.
- **A failed load leaves the job open; the same call with the same `idempotencyKey` resumes it** from `:begin`'s `nextSequence`
  (**Lead S22, 0.6.0**; it was `resumeFromRow`, gone): the bodies the server holds are not sent, and the rows of the frames
  skipped are checked against the server's count, so a load framed differently is refused `BULK_LOAD_CURSOR_MISMATCH` instead of
  loading rows twice. A job that already holds every frame is committed with `:commit` (**Lead group 5 review, 0.6.0**).
  Only a cancellation aborts — and (**Lead group 3 review, 0.6.0**) a failed load whose `idempotencyKey` the SDK generated,
  which nobody else could resume: pass your own key. Neither SDK aborts a job whose commit may be running (a lost answer, a
  "committing" refusal), except on a cancellation: the server's commit decides it.
- **A key whose job already committed returns that job** (`alreadyCompleted: true`, `rowsLoaded`, `token`) and sends nothing;
  it used to fail `409 BULK_LOAD_INVALID_STATE`.
- **No NDJSON**: rows no frame carries, and every body to a server that does not advertise frames, go as JSON column arrays.

### Several jobs into one table, pipelined (**Lead S18b, 0.6.0**)

A load that arrives as several jobs — a file per day, a batch per hour — should not wait for each job's `:commit` before
beginning the next. The server already lets a second job's `:begin` and `:append`s in while the first commits: the second job's
rows decode and queue (up to `Aouda:BulkLoad:MaxQueuedAppendBytes`, 64 MB) behind the table's bulk-load lock, and its row loop starts when
the first job's rows end — (**Lead S19, 0.6.0**) the lock passes to the next job as soon as the first job's `:commit` has
closed its rows, so the second job's rows load while the first one writes and commits. Both SDKs do this for you:

```csharp
await foreach (var handle in client.BulkLoadJobsAsync("trades", days))   // C#: each job a list or stream of ColumnBatch, or rows
    Console.WriteLine($"{handle.JobId}: {handle.RowsLoaded}");
```

```typescript
for await (const handle of client.bulkLoadJobs('trades', days)) console.log(handle.jobId, handle.rowsLoaded);
```

- **Nothing about a job changes.** Each is committed, visible and answered on its own, in job order; a later job is never visible
  before an earlier one: (**Lead S19, 0.6.0**) commits on a table are first in, first out — a job that took the table's lock
  later reaches its commit point only after every earlier job is committed (or aborted). A `:commit` therefore still returns after
  its own job is durable and visible, as before; `commitWaitMs` on the server's commit line says how long it waited for the job
  ahead of it. An update, delete or other write to the table waits for every load that was in flight when it arrived — loading or
  committing — and not for loads that start after it.
- (**Lead S21b, 0.6.0**) **A job's last body commits it.** The C# SDK puts the commit in the end frame of a job's last
  column-batch body ([HTTP API](../reference/http-api.md#a-body-that-commits-its-job-lead-s21b-060)), so a job needs no
  `:commit` round trip, and it begins job N+1 as soon as job N's last body is written: N's rows end on the server the moment the
  body is read, its segments are finalized and synced while N+1's rows arrive, and only N's commit point waits for the jobs before
  it. `@aouda/client` does the same (**Lead S22, 0.6.0**) where its `fetch` streams a request body (Node's); with one that
  cannot say when a body was written (a browser's, or a `fetch` passed in the options) it commits each job by `:commit`, still
  naming the job before as `afterJobId`, while the next job's rows are sent.
- **One job sending and one committing per loader** (**Lead S21b, 0.6.0**; it was "one `:append` and one `:commit` in
  flight"). That is what keeps the server's `:append` lane (4 requests at once by default,
  `Aouda:BulkLoad:MaxConcurrentStreamingRequests`) from starving: up to four loaders into one table finish while no job's queue
  fills. A body that commits keeps its place on the lane until its commit answers (with `commitWait` accepted, until its job is
  accepted); a separate `:commit` runs on no lane at all. (**Lead S31, 0.6.0**) A job queued behind another loader's job holds
  its `:append`'s place on the lane while that `:append` waits for room in the job's queue (`Aouda:BulkLoad:MaxQueuedAppendBytes`,
  64 MB of decoded rows), and a pipelined loader has two `:append`s on the lane — so once jobs are larger than that queue, **three
  pipelined loaders into one table can starve the lock holder's next `:append`** until the others time out on the lock (30 s).
  Keep it to **two pipelined loaders a table** on the default lane (half its permits), or to as many unpipelined loaders as it has
  permits (**BL-1117**).
- **The first failure ends the sequence** after every earlier job's handle, and **no job after the failed one commits**: (**Lead
  S21b, 0.6.0**) each job names the one before it as the job it follows (`afterJobId`), so the server takes them in order and
  refuses the commit of a job whose predecessor did not commit — even one whose commit was already on its way. A caller who stops
  reading early gets the job sent behind the last handle aborted, unless its commit point had already passed. A caller's
  idempotency key keys job `i` as `{key}.{i}`, so a repeated call replays what committed and resumes the rest.
- **`FailFast` runs the jobs one at a time**: a job queued behind the lock would be refused.
- What overlaps is a commit with the next job's begin, send, decode and (**Lead S19, 0.6.0**) row loop: the next job's rows
  are accrued while the earlier job drains, writes and commits. Two jobs' ingest buffers are then held at once, each under its own
  memory grant. Raw HTTP clients can pipeline the same way (**Lead S21b, 0.6.0**): begin job N+1 with `afterJobId` set to N's
  `jobId` once N's last body (committing in its end frame) is written, and send N+1's bodies, its last one committing too; N+1
  commits after N, and not at all if N fails. Without `afterJobId`, send N+1's commit only after N's returned.

### Answered before the commit: `accepted` (**Lead S30, 0.6.0**)

By default a job's commit answers once the job is committed. A loader that has more to send, and learns the outcome later, can ask
to be answered sooner: with `wait: "accepted"` ([HTTP API](../reference/http-api.md#post-jobidcommit)) the commit answers once the
job's rows have ended and it holds its place in its tables' commit order, and the job commits on without the caller.

```csharp
var handle = await client.BulkLoadAsync("trades", batches, new BulkLoadOptions { CommitWait = BulkLoadCommitWait.Accepted });
// handle.State == BulkLoadCommitState.Accepted: not durable yet
var outcome = await handle.Outcome;   // Committed (rows, commit token) or Lost
```

```typescript
const handle = await client.table('trades').bulkLoad(batches, { commitWait: 'accepted' });
const outcome = await handle.outcome;   // { state: 'committed' | 'lost', ... }
```

- ⚠️ **An accepted job is not durable and may be lost.** If the server stops before the job's commit point, or its commit fails,
  nothing of it is kept, and the job's outcome says `lost`. "Accepted" is never reported as committed: the handle claims no durable
  rows (`RowsDurablyCommitted` / `rowsDurablyCommitted` 0, no commit time) until its outcome says so. The default (`visible`) is
  unchanged, and so is what a committed job promises under `strict` durability.
- **A read with the handle's token waits until the job is visible** — on the primary, for the materialized queries over the loading
  tables, and on a replica — so reading your own load with the token never shows it half there. Do not read the outcome off the
  token: a lost job's token reads as covered once the log moves past it.
- **The outcome comes from `GET {jobId}`**, which both SDKs ask with `waitMs` so they are answered when the job settles. After a
  restart that cut the job off, the server answers it `lost`; once its log has moved past the job, `404` — the same answer for an
  accepted job: load it again. ⚠️ Read the outcome promptly: a committed job's record is kept for at least an hour after its commit
  (or `Aouda:BulkLoad:IdempotencyWindowMinutes`, if longer), and a `404` asked after that cannot tell a lost job from a committed one
  the server has forgotten. A job whose commit point passed is never `lost`, even if work after it failed: like any such load, it is
  committed and its rows become visible at the next restart (note 6 below; **Lead group 7 review, 0.6.0**).
- **A `validation: "strict"` job's key check runs at its commit point, after the accepted answer**, so a key it holds twice or one the
  table already holds is its outcome: `GET {jobId}` answers `state: "failed"`, `errorCode: "BULK_LOAD_DUPLICATE_PK"`, and the SDKs
  raise what they raise for the same load without the accepted wait (`BulkLoadDuplicatePkException`; an `AoudaApiError` coded
  `BULK_LOAD_DUPLICATE_PK`), ending a pipelined sequence. Nothing of the job is kept; do not load it again unchanged. After a restart
  that cut the job's session off, it reads `lost` (**BL-1163, 0.6.0**).
- **It frees the loader, not the table.** A write into a table the job loads still waits for the job.
- With `BulkLoadJobsAsync` / `bulkLoadJobs`, each handle is yielded once its job is accepted. A loader keeps at most **two** accepted
  jobs before it waits for the oldest one's outcome (an accepted job still holds its buffers on the server until it commits), and a
  lost one ends the sequence (`BulkLoadLostException` / `BulkLoadLostError`): the jobs after it follow it, so none of them commits.
  The sequence ends only once every job it accepted has settled, so a normal end means every job committed (**Lead group 7 review,
  0.6.0**: the last jobs' outcomes were not awaited, and a lost one among them ended the sequence normally).
- A job the server cannot accept — a load that writes no closing log frame, or a database without a WAL (durability `unlogged` or `memory`) — is answered committed.
  `wait: "accepted"` is refused with `waitForDeferredWork`, `mqWaitMs` above 0 or a write concern above `acknowledged`, which each
  wait for the commit.

### A load's durability: `strict` or `os` (**Lead S26c, 0.6.0**)

A load names its own level in `:begin`'s `options.durability` ([HTTP API](../reference/http-api.md#post-begin)):

| Level | Before the job is visible | After a process crash | After a power loss |
|---|---|---|---|
| `strict` | Every segment file, its directory and the job's commit record are fsynced | Committed | Committed |
| `os` | The files are written and renamed, and the commit record written, without fsync | Committed | Kept whole, or dropped whole and reported `lost` — never half |

Omitted, a load takes its database's level for a load: `os` in a database at `os`, `strict` everywhere else. A table's own level
does not change it — an `unlogged` table still gets a `strict` load. `strict` is what every load did before.

```csharp
var handle = await client.BulkLoadAsync("trades", batches, new BulkLoadOptions { Durability = BulkLoadDurability.Os });
// handle.Durability: the level the job committed at
```

```typescript
const handle = await client.table('trades').bulkLoad(batches, { durability: 'os' });
// handle.durability: the level the job committed at
```

In `Aouda.Client`, `BulkLoadOptions.Durability` is a `BulkLoadDurability?` (`Strict`, `Os`; `null` = the database's level) and
`BulkLoadJobHandle.Durability` reports it. In `@aouda/client` the option is `durability?: 'strict' | 'os'` and the handle's
`durability` reports it. The CLI's `aouda table bulk-load` and `aouda bulk-load` take
`--durability strict|os`, and their summary and `--json` output name the level.

- **What `os` buys is the commit's sync wait, at most.** Choose it for data you can load again.
- ⚠️ **After a power loss an `os` job is kept whole or dropped whole, never half.** At the next open the server checks every file
  of every `os` job it had not yet synced against the length and xxHash128 its commit record names. A job that does not match is
  dropped entirely and reported **lost**: `GET .../bulk-load/{jobId}` answers `state: "lost"`, `errorCode: "BULK_LOAD_LOST"`,
  `durability: "os"`. Its idempotency key no longer names a commit, so **load it again with the same key** — the `:begin` starts a
  fresh job instead of answering `alreadyCompleted`.
- **Until it is synced, an `os` load holds up its database's durable writes.** The server syncs ("promotes") an `os` job in the
  background, starting at its commit. Until then every durable write on that database waits for it: inserts, updates and deletes
  that write the WAL, catalog segment changes such as merges and compaction, materialized-query passes and result checkpoints, a
  branch's creation, a backup and a replica's checkpoint image, a rewrite of a derived column's stored values, and the commit of a
  job that follows it (`afterJobId`; **Lead group 6 review and whole-branch review, 0.6.0** — so a power loss never keeps a
  copy or a follower of a job it drops, and a process crash never drops it). The wait is at most about the fsync time a `strict`
  load pays up front.
- ⚠️ **If the background sync fails, the database stops taking durable writes.** Every later insert, update, delete, merge, pass and
  checkpoint on it is refused, naming the job, until the server is restarted; the restart verifies the job and keeps it whole or
  reports it lost. Meanwhile `:status` still answers the job committed at `os`.
- **An `os` load writes no WAL frame.** Bulk loads are not replicated anyway (**BL-1116**), and on a replica an `os` load's
  consistency token can read as covered without its rows (**BL-1162**): read an `os` load's rows on the primary.
- **Refused at `:begin`**, `400 BULK_LOAD_INVALID_OPTIONS`, the message naming the level:
  - any other value — `unlogged` and `memory` are table and database levels, not a load's, and names are case-sensitive;
  - `strict` in a database at `os` (its WAL is not written through);
  - `os` for a job of several tables, or for a table with vector columns, or an edge or vector table.

  So a multi-table load into an `os` database is refused whatever it asks for, and so is a load into a table with vector columns,
  or an edge or vector table, there.
- **Reported:** `:begin` answers `durability`, the level the job will commit at (for a replayed completed job, the level it
  committed at); `:commit` always answers it, an `accepted` answer included; `GET {jobId}` and `:list` give each job's, omitted
  when it is unknown — an accepted job lost before its commit point.

### A load's validation: `coerce` or `strict` (**Lead S27a, 0.6.0**)

A load names what it checks in `:begin`'s `options.validation` ([HTTP API](../reference/http-api.md#post-begin)):

| Level | A null or absent cell in a NOT NULL column | A primary key the job holds twice, or the table already holds |
|---|---|---|
| `coerce` (default) | Stored as the type's default (`0`, `""`) — **refused in a primary-key column** | Loaded as a second row (not checked) |
| `strict` | Refused | The job fails at its commit, nothing committed |

Every load, at either level, **refuses a column its table does not have** (names are case-sensitive) — in a multi-table job, a value
in a column the row's own table (`_table`) does not have, even when another table of the job has it (**Lead group 6 review, next
train**; a null there carries nothing and passes). The server checks each
`:append` frame before any of it is applied: a frame it refuses answers `400 INVALID_REQUEST` naming the column, the frame and the
row, with none of that frame's rows applied and the frames before it kept, so the job stays open. An auto-increment column is exempt
from the null check — a missing value takes the next id.

```csharp
var handle = await client.BulkLoadAsync("trades", batches,
    new BulkLoadOptions { Validation = BulkLoadValidation.Strict });
// handle.Validation: the level the job was checked at
```

```typescript
const handle = await client.table('trades').bulkLoad(batches, { validation: 'strict' });
// handle.validation: the level the job was checked at
```

- **`coerce` is ClickHouse's default** (`input_format_null_as_default`); **`strict` is DuckDB's constraints**. A key is never
  coerced: a load that would store a key nobody sent is refused at either level.
- **`strict` needs a table that checks its keys**: on a table whose key mode (`pkUniqueness`) is `Recent` or `BestEffort`, a strict
  load is refused at `:begin` (`400 BULK_LOAD_INVALID_OPTIONS`) — a job is never stricter than its table. So is a strict load with
  `applyTransforms`.
- **A strict job's keys are checked at its commit**, after every earlier job on the table has committed, against the table and
  against each other: a duplicate answers `409 BULK_LOAD_DUPLICATE_PK` (C#: `BulkLoadDuplicatePkException`, its `SampleKeys` naming
  the key; the CLI exits 5) and nothing of the job is committed. The check waits for the inserts, upserts and updates that were in
  flight on the table when the job began, so a load and a racing insert never both write one key; writes that arrive after the job
  began wait for the job, as they always did.
- **What `strict` costs:** it keeps every row's key until the commit and probes the table for each, as an insert does — memory and
  time in proportion to the rows. `coerce` costs nothing beyond the frame check.
- **Reported:** `:begin`, `:commit` and `GET {jobId}` answer `validation`; `BulkLoadJobHandle.Validation` (C#) and
  `handle.validation` (TypeScript) name it. A job answered from its commit record after a restart has none on the wire (the SDKs
  report the level they asked for).
- `pkUniquenessOverride` is gone (**breaking**): no server applied it, and a `:begin` that sends it is refused naming `validation`.
  The CLI's `--pk-uniqueness` is refused the same way; use `--validation coerce|strict`.

### Sizing a session: fewer, longer, one commit

> **Fewer, longer sessions produce well-sized segments. Many short sessions do not.**

The `:commit` boundary does not decide segment size by itself — the engine seals a bucket into a segment on its own triggers (`MaxRowsPerSegment`, `TargetSegmentBytes`, or the job's ingest buffer budget), and the end-of-job drain writes whatever remains, however small. A client that batches every 10 000 rows across 250 partitions and commits after each batch forces a full drain every time, producing 250 segments of ~40 rows each — every commit, forever. The batching a client chooses still sets the ceiling: **a session cannot produce a segment larger than the rows it was given.**

**Do this:**
- Open **one** session (`:begin`), stream the whole migration through repeated `:append` calls, and `:commit` **once** at the end.
- Size `:append` batches for the network, not for segment size — 10 000–100 000 rows per call is fine.
- Track your upstream cursor at the commit: a job's rows are durable only once `:commit` answers (**Lead S20b, 0.6.0**:
  `rowsDurablyCommitted` mid-job counts what segments have sealed, which are not durable until the commit and are not a resume
  offset). To resume an open job, use `:begin`'s `nextSequence` with the same idempotency key.

**Not this:**
- One `:begin` / `:append` / `:commit` cycle per batch. Each commit forces a full drain, so this is the shape that produces tiny segments regardless of anything the engine does.

Segment size is bounded from above by roughly:

```
min(TargetSegmentBytes, IngestBufferBudgetBytes / activeBuckets)
```

so a table with hundreds of live partition-key directories cannot produce large segments under any buffer budget a server can afford — see [Choosing partition storage mode](#choosing-partition-storage-mode) below. Partition storage mode is a **prerequisite** for good segment sizing, not an optimization layered on top of it.

The worked example (a table partitioned on two columns with ~250 distinct value pairs):

| Shape | Segments per job | Median rows/segment |
|---|---|---|
| Commit every 10 k rows, `Dedicated` storage | ~250 | ~40 |
| One session, `Auto` storage, key bounded by a time function (16 shared buckets) | ≤ 16 | ~625 |
| One session, `Auto` storage, high-cardinality key (**ColumnarMerge S03, 0.2.0**) | 1 | 10 000 |
| One session, 1 000 000 rows | 22 | 54 000 |

**A high-cardinality `Auto` key coalesces** (**ColumnarMerge S03, 0.2.0**). When at least one
partition-key column has no time function — `(Ticker, Source)`, a tenant id — a bulk load writes every key
that has not been promoted to its own directory into **one** segment per job (cut at `TargetSegmentBytes`),
sorted by the partition key and then the cluster columns, instead of one segment per hash bucket the job
touches. A 170 000-row Equity job that used to write 60 segments of ~2 000 rows now writes one. Rows you
insert (rather than bulk-load) flush the same way (**ColumnarCore S08, 0.2.0**): each flush of such a table writes
one segment of everything it holds, in the same order, where it used to write one small segment per bucket the
buffer touched. A key bounded by a time function (`truncateToDay` and the like) keeps its buckets for both. Reads return the same rows either way: a read filtered on
the partition key skips a job's segment by its zone maps on the key (**ColumnarMerge S06, 0.2.0**),
where it used to skip it by bucket. Hot segments are narrowed the same way: a hot segment answers its partition-key
columns' range (computed once and kept with the segment), so a one-series read of a hot-first coalescing table opens
only the hot segments that can hold the series, not all of them (**BL-714, 0.2.0**). A **time window** over bulk-loaded
history no longer reads every row group either (**ADR 0061, 0.3.0**): a segment in `(partition key, time)` order records,
for each series, its time at every 64th row, so a filter that bounds the cluster's time column (`DateTime >= a AND DateTime < b`)
reads only the few dozen rows of each series that can fall in the window. On 1 M Equity trades a two-hour window's count and sum
reads in ~1.4 ms instead of ~2.3 ms, and a day's top 10 by volume in ~2.3 ms instead of 4–6 ms. It needs the bounds as top-level `AND` conditions on the time
column; a window inside an `OR` reads as before. A keyed table's bulk-loaded segments also get their primary-key
sidecars — the index and keymap other writers already built — shortly after the commit, so a uniqueness
check that has to consult one stays cheap.

On top of segment shape, this engine also removes a per-segment fixed cost that shape alone cannot: on a database that does not replicate (`ReplicationMode: DoNotReplicate`, the [single-node profile](single-node-deployment.md)), `LogShipSegments`'s default no longer re-reads and BLAKE3-hashes every written segment file or appends a WAL frame for it. ⚠️ (**BL-1118**) A database left at the default `Replicate` still writes the frames on a server with no replica — the switch is the database's replication mode, not a detected topology — and a multi-table load writes them everywhere; the frames cost about 4 ms a job (Lead `S20b`). Measured on the first worked row above collapsed to `Auto`/16 buckets (250 partitions × 40 rows, 16 sealed segments): `finalizeMs` dropped from 13 ms to 0 ms and `walMs` from 2 ms to 0 ms (`walPosition` becomes `-1` — the same shape `SkipReplication` already used). See [Single-Node Deployment](single-node-deployment.md) for the durability trade-off that default makes.

For the engineering detail behind these triggers and the ingest buffer budget's own formula, see the private companion guide `docs/dev/BulkLoad-Ingest-Sizing-Guide.md` in the engine repository.

**This page is about bulk load specifically — the ordinary (row-by-row) insert path has its own shape
story.** As of P45, a table fed continuous streaming writes no longer accumulates small segments forever:
a background process merges and re-clusters small cold segments as steady-state maintenance, not as an
occasional repair. See [Partitioning and Multi-tenancy](partitioning.md#choosing-initialbucketcount-at-scale-p45)
for how segment shape and bucket count interact for that path.

### Loading a lot of data into tables with queries

(**LoadSpeed M.1, 0.4.0** — guidance from measurements on 0.3.0; the numbers below are from one 16-vCPU machine with the
server on 4 CPUs, so read them as ratios, not as what your hardware will do.)

Most of what a load into a table with materialized queries costs is the queries' maintenance, not the load. On a
2 GB server loading 15.3 M trades and 30 M quotes with 13 queries over them, `postLoadMqBehavior: "auto"` took the trade load
from 266 k rows/s (no queries) to 67 k rows/s and the CPU per million rows from 7.6 to 48.2 CPU-seconds. Most of that is memory
pressure: when the results do not fit in memory, groups a later job touches again are written again. The same load at 8 GB
cost 34 % more CPU than with no queries, not 6.3× more. Three rules follow.

**1. A migration or an initial load: `auto` is now as fast; `skip` + one pooled refresh when you want maintenance off.**
(**LoadSpeed M.3, 0.4.0**) `auto` coalesces while a table loads (above), and on the load below it had all 13 queries current
**440.5 s** after the load started — the recipe's time (441.5 s) — with the load at 253 k rows/s. So the recipe is no longer needed
for speed. It is still the way to turn maintenance **off** for the whole load, and it costs less CPU (28.1 against 37.4 CPU-s per
million rows: it rebuilds once, after everything, where `auto` catches up while the other tables still load). The rest of this rule
describes 0.3.0, where it was the faster path. Load every job with `postLoadMqBehavior: "skip"`, and when the last one has
committed, refresh each source table once:

```http
POST /api/databases/{db}/materialized-queries:refresh
{ "sourceTable": "EquityTrade", "staleOnly": true }
```

On the load above, that had all 13 queries current **441 s** after the load started, against **650 s** with `auto`; it used
42 % less CPU (28.1 against 48.2 CPU-s per million rows) and wrote 42 % fewer bytes; the load itself ran at the no-query rate
(265 k rows/s); and the results were identical (0 mismatches over 9.9 M rows compared). The pooled refresh reads each source
table **once** for all of its queries (see [pooled refresh](materialized.md#211a-refreshing-several-queries-at-once-pooled-refresh)).
Until it has run, the queries are readable and **stale**, and a read of the table does not route to them — so do it before you
open the database to readers, and, if the server may restart in between, before the restart (a stale query is rebuilt at
startup otherwise). For a table you keep loading into, stay on `auto`: it keeps the queries current as you go, and a refresh
re-reads the whole table each time.

**2. Bulk load at 10 000 rows per job or more.** A job has a fixed cost — about 20–30 ms per `:begin` … `:commit` with no
queries, about 90 ms with 13 — so tiny jobs are expensive. Measured on 2 M rows, one job per batch: at 100 rows per job a bulk load
costs 681 CPU-s per million rows with 13 queries; at 10 000 rows, 41; at 200 000 rows, 25. The crossover with `InsertMany` is a
batch of about **10 000 rows**, with or without queries: from there bulk load is faster (1.2× with no queries, 1.9–3.6× with 13).
Better still, one long session (see [Sizing a session](#sizing-a-session-fewer-longer-one-commit)).

**3. Day-to-day trickles below ~2 000 rows per call: `InsertMany`** (`POST /api/databases/{db}/tables/{table}/rows`). Below 2 000
rows per call it is faster than a bulk-load job (6× at 100 rows with no queries). Between 2 000 and 10 000 the two are close;
measure your own shape. One limit to know: with queries over the table, the insert path's maintenance kept the queries current at
**17–23 k rows/s at most**, whatever the batch size. Inserts are acknowledged faster than that (up to 82 k rows/s), the queries fall
behind, and at 100- and 500-row batches they never caught up within the run. A loader that writes more than that into a table with
queries should use bulk load, which keeps them current at its own rate and costs 2–4× less CPU per row from 2 000 rows per job up.

**And `:commit` no longer waits for the queries by default** (**LoadSpeed M.2, 0.4.0**): `mqWaitMs` defaults to `0`. A
loader that needs the queries current before its next step sends `mqWaitMs`, or reads with the commit's `token`.

### Loading a table with retention

(**Horizon, 0.5.0**) A table that declares [retention](retention.md) — and a windowed materialized query's result — has a
time-slice rule: no segment may span two slices of its time column (the largest of hour / day / week / month that is at most
`keep / 4`), so that expiry can drop whole segments. The bulk load follows it:

- **One segment per time slice.** Each bucket of the load is written as one segment per slice its rows fall in, with the run
  directory and granule marks built inside each segment as before, so a series' rows stay in order within a slice. A three-year
  history loaded into a table with a one-year `keep` lands as one segment per month and leaves a month at a time; the segments that
  remain are never rewritten.
- **Never spilled.** A bucket of such a table that must leave memory is flushed, one segment per slice, instead of spilling to a run
  that the commit merges (a spill merge cuts by bytes, not by time). Under a tight budget that means more, smaller segments; the
  coalescers merge them within their slices.
- **Rows below the horizon are counted, not written.** A row whose time lies below the table's horizon — or is an explicit `null`, in a
  nullable time column — is left out, and the `:commit` response reports how many in `expiredRows` (omitted when 0; not in `rowsLoaded`).
  `BulkLoadJobHandle.ExpiredRows` in `Aouda.Client`, `handle.expiredRows` in `@aouda/client`. See
  [HTTP API — `:commit`](../reference/http-api.md#post-jobidcommit).

A table without retention is loaded exactly as before.

### Choosing partition storage mode

**This section assumes the table should be partitioned at all.** That is a separate and earlier question,
and it is about the table's total size, not the rows in one key: partition when total rows divided by
one full segment — around a million rows — is comfortably more than one. A table whose quotient is a
handful wants no `partitionKey`, and none of the choices below apply to it. A key that itself holds about
a million rows is the later choice of `Dedicated`, not this one. See
[Should this table have a partition key?](partitioning.md#should-this-table-have-a-partition-key-p45).

Given a table that clears it, ask one more question: **will any single partition key, on its own, plausibly reach 10 million rows or 1 GB?** — the *promotion* thresholds, not the partition-or-not line above.

- **No** (the common case — a few hundred to a few thousand distinct key values, each holding a modest share of the table): leave `partitionStorage` unset. A declaratively-managed table defaults to `Auto`, which starts every key in a shared bucket and promotes an individual key to its own dedicated directory only if it actually crosses that threshold. The starting bucket count is `16` when every partition-key column carries a bounded time-truncation `partitionFunction` and `128` otherwise (P45) — see [Choosing `initialBucketCount` at scale](partitioning.md#choosing-initialbucketcount-at-scale-p45), and note it is fixed for the life of the table.
- **Yes** (a small number of keys, each independently huge — e.g. partitioning by tenant for a handful of enterprise tenants who each hold the whole table's data): declare `partitionStorage: "Dedicated"` explicitly. Starting such a key in a shared bucket only to have it promote out immediately is pure overhead.

**The legacy-table exception.** `Auto` is the default only for a table created (or re-applied) through declarative schema apply after this default was introduced. A table that predates it keeps its original, implicit `Dedicated` storage — nothing changes it automatically, and there is no automated migration tool yet. If a table stuck in `Dedicated` is producing the tiny-segment shape above, the supported route today is manual: export the table's data, drop it, re-create it **under a different name** with the desired `partitionStorage`, and reload. See the private engineering guide's own migration-route section for the exact steps and a known caveat about reusing the dropped table's name.

See [Partitioning and Multi-tenancy](partitioning.md) for the full storage-mode reference (`Auto`/`Dedicated`/`Shared`, promotion thresholds, routing).

---

## 2.8 How Aouda implements it

High-level architecture path:

1. **API entry** (`AoudaEngine.BulkLoadAsync`) validates options/tables and maps request options to storage-layer config.
2. **Storage coordinator** (`BulkLoadCoordinator`) acquires table locks, writes bulk segments (each with its manifest), emits WAL frames. (**BL-980, 0.4.0**) The pre-P41 `.bulkload.commit` marker is no longer written or read: recovery discards a partial bulk write that has no manifest, whatever lies beside it.
3. **HTTP session registry** (`BulkLoadSessionRegistry`) manages in-memory job state for begin/append/commit/status/list.
4. **Replay path** (`FrameApplier` + `BulkLoadReplicaCoordinator`) decodes tag 60/61/62 frames and drives segment fetch/apply state machine.
5. **Segment fetch to a replica:** none yet (**BL-1116**). (**BL-1193, next train**) The checkpoint protocol's `0x20`/`0x21` messages and `BulkSegmentFetcher`, which no server used, were removed; a primary's checkpoint session now ends on a message type it does not know.
6. **Client coordinator** (`Aouda.Client.Internal.BulkLoadCoordinator`) orchestrates begin/append/commit and maps failures to typed exceptions.

### 2.8.1 Critical path walk-throughs

#### Path A: HTTP begin -> append -> commit

1. Client calls `POST .../bulk-load:begin` with tables and optional options.
2. Controller validates database/table list/options and starts/returns session from `BulkLoadSessionRegistry`.
3. Client streams batches to `POST .../{jobId}:append`: column-batch frames (`application/vnd.aouda.column-batch-v2`) or one JSON column-array body per call (`application/json`) (**Lead S12, 0.6.0**: NDJSON, `application/x-ndjson`, is refused `415 ROW_OBJECTS_UNSUPPORTED`).
4. Rows are pushed into session channel; engine consumes channel via `AoudaEngine.BulkLoadAsync`.
5. Client calls `POST .../{jobId}:commit`; controller completes channel and awaits engine task.
6. Engine returns `BulkLoadJobHandle`; controller sets session completed and returns commit response.

Tests: `BulkLoadControllerBeginTests`, `BulkLoadControllerAppendTests`, `BulkLoadControllerCommitTests`, `BulkLoadEndToEndTests`.

#### Path B: Primary commit -> replica fetch/apply

1. Primary emits `BulkSegmentCommitted` frames as segments are sealed and persisted.
2. Replica replay (`FrameApplier`) dispatches tag 60 to `BulkLoadReplicaCoordinator`.
3. Coordinator tracks segment expectation and schedules fetch through `SegmentFetcher`.
4. On closing frame tag 61, coordinator transitions to staged/committed depending on fetched set completeness. (**Lead S18a, 0.6.0**) The replica's tokens stop below that frame until it is committed there (ADR 0065 `D-5`); later frames still apply. ⚠️ No server constructs the coordinator or the fetcher yet (**BL-1116**): the steps above run in tests only.
5. Tag 62 marks job aborted and replica state transitions accordingly.

Tests: `BulkLoadReplicaCoordinatorTests`, `BulkLoadCompactionWatermarkTests`.

#### Path C: Watchdog timeout / force-abort

1. Engine registers in-flight job in `BulkLoadResumeWatchdog` when bulk load starts.
2. If job exceeds resume window without successful close, watchdog emits `BulkLoadAborted`.
3. Operator can force abort via `POST .../bulk-load:force-abort`, which also emits abort frame.
4. Registry marks session aborted after durable WAL abort emission.

Tests: `BulkLoadWatchdogLifecycleTests`, `BulkLoadListRouteTests` (`force-abort` cases).

---

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| How is high-throughput ingest replicated? | Either row-log every row or re-snapshot large tables | Segment/job WAL frames + out-of-band segment ship | Lower WAL amplification while retaining replication observability |
| Is multi-table ingest atomic? | Often per-table or app-coordinated two-phase logic | Single job with closing frame and per-table summaries | One commit boundary for normalized multi-table loads |
| Can operators see and control in-flight jobs? | Limited visibility without custom tooling | Native status/list/force-abort routes + session model | Faster incident handling and safer stuck-job recovery |
| Can same ingest surface be used by engine, server, client, CLI? | Often fragmented ingestion stacks | Shared contract across engine API, HTTP, .NET client, CLI | Fewer semantic mismatches between pathways |

---

## 2.10 Configuration and settings reference

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `BulkLoadOptions.ReplicationMode` | enum | `LogShipSegments` | `LogShipSegments`, `SkipReplication`, `MarkForSnapshot` | Engine API / HTTP begin options / client | Cluster policy can override by rejection. |
| `BulkLoadOptions.ForceSingleNodeReplicationBypass` | bool | `false` | `true/false` | Engine/API/client | Safety key for skip-replication mode. |
| `BulkLoadOptions.WriteConcern` | enum | `One` | `One`, `Majority`, `All` | Engine API (and HTTP commit request) | Engine multi-node barrier path is incomplete today. |
| `BulkLoadOptions.WriteConcernTimeout` | `TimeSpan` | `5m` | positive duration | Engine/API/client | Timeout does not roll back committed load. |
| `BulkLoadOptions.AdditionalTables` | list | `null` | table names | Engine/API/client | Enables multi-table atomic load. |
| `BulkLoadOptions.DeferIndexBuild` | bool | `true` | `true/false` | Engine/API/client | Deferred work reported in progress DTO. |
| `BulkLoadOptions.EmbeddingModelVersion` | string? | `null` | any non-empty string for vector tables | Engine/API/client | Required for vector-bearing tables. |
| `BulkLoadOptions.MaxRowsPerSegment` | int? | `TargetRowsPerPage * 16` | positive int | Engine/API/client | Segment sizing knob. |
| `BulkLoadOptions.ConflictPolicy` | enum | `Block` | `Block`, `FailFast` | Engine/API/client | Controls behavior for concurrent regular writes. |
| `BulkLoadOptions.Validation` / `options.validation` | `BulkLoadValidation` / string | `Coerce` / `"coerce"` | `Coerce`, `Strict` / `"coerce"`, `"strict"` | Engine/API/client / HTTP `:begin` options / CLI `--validation` | (**Lead S27a, 0.6.0**) What the load checks; see [A load's validation](#a-loads-validation-coerce-or-strict-lead-s27a-060). Replaces `PkUniquenessOverride`, which nothing applied and the server now refuses. |
| `BulkLoadOptions.PrincipalId` | `Guid` | `Guid.Empty` | valid guid | Engine/API | Stamped into bulk-load WAL frames. |
| `BulkLoadOptions.LockAcquisitionTimeout` | `TimeSpan` | `30s` | positive duration | Engine/API | Lock wait bound. |
| `BulkLoadOptions.BulkLoadResumeWindow` | `TimeSpan?` | `null` (watchdog default) | positive duration | Engine/API | Per-job override for watchdog timeout. |
| `BulkLoadOptions.IdentityInsert` | bool | `false` | `true/false` | Engine/API/client / HTTP `:begin` options | When `true`, identity-insert for the whole job (Bond `isAutoIncrementDisabled: true`). Counter floor applied only after successful commit. |
| `BulkLoadOptions.Durability` / `options.durability` | `BulkLoadDurability?` / string | `null`: the database's level for a load (`os` in an `os` database, else `strict`) | `Strict`, `Os` / `"strict"`, `"os"` | Client / HTTP `:begin` options / CLI `--durability` | (**Lead S26c, 0.6.0**) The load's own level; see [A load's durability](#a-loads-durability-strict-or-os-lead-s26c-060). `strict` in an `os` database, and `os` for a multi-table job, a table with vector columns, or an edge or vector table, are refused `400 BULK_LOAD_INVALID_OPTIONS`. |
| `applyTransforms` / `preTransformed` | bool | unset | exactly one when the table has derived columns, checks, or transforms | HTTP `:begin` / client / CLI | Neither flag → `BULK_LOAD_TRANSFORM_INTENT_REQUIRED`. A table with a server-time column takes **only** `applyTransforms` (`preTransformed` → `BULK_LOAD_SERVER_TIME_REQUIRES_TRANSFORMS`), and the whole job — every `:append` of the session — is stamped with **one** reading taken when the job starts (**NativeClients, 0.4.0**). See [Insert-time transforms](insert-transforms.md#bulk-load-is-loud) and [server-time stamps](insert-transforms.md#server-time-stamp-servertime). |
| `Aouda:BulkLoad:MaxRowsPerAppend` | int | `100000` | `>0` | Server config | Per-append HTTP cap. |
| `Aouda:BulkLoad:MaxQueuedAppendBytes` | long | `67108864` | `>0` | Server config | Byte bound on a job's queue of decoded rows, charged to the governor (**IngestAtSpeed S10, 0.1.40**). |
| `Aouda:BulkLoad:SessionRetentionMinutes` | int | `10` | `>=1` | Server config | Retention for terminal sessions. |
| `Aouda:BulkLoad:IdempotencyWindowMinutes` | int | `10` | `>=1` | Server config | How long after commit an idempotency key replays its committed job, across session sweeps and restarts (**IngestAtSpeed S02, 0.1.40**). |
| `Aouda:BulkLoad:AllowWritePermission` | bool | `false` | `true/false` | Server config | Compatibility gate for write-only principals. |
| `Aouda:BulkLoad:ForceLogShipBulkLoad` | bool | `false` | `true/false` | Cluster/server config | Rejects non-log-ship modes. |
| `BulkLoadOptions.RequestTimeout` — *since 0.1.22* | `TimeSpan` | `10m` | positive duration | Client | Deadline for each individual bulk-load HTTP call. Deliberately not `AoudaClientOptions.Timeout` (30 s), which is sized for point operations and cannot cover a `:commit` that seals a million rows. Governs one call, not the job. A caller-supplied `HttpClient` keeps its own `HttpClient.Timeout`, which caps this. |
| `BulkLoadOptions.MaxAppendBytes` — *since 0.1.22* | int | `8 MiB` | `>=0` (`0` disables) | Client | Maximum serialized size of one `:append` body. A chunk closes at this bound or `AppendBatchSize` rows, whichever comes first. Raising `AppendBatchSize` alone does not send larger appends — this is the bound that governs, and it is what keeps a wide row under ASP.NET's 30 MB request-body limit (which answers with a body-less `413`). (**LoadScan, 0.5.0**) The C# client builds the next `:append` body while the previous one is in flight — still one `:append` at a time, in order — so your row source is read at most one body ahead of what the server has accepted, and two bodies may be held at once. Your source is read on a thread-pool thread, by one call at a time. A load that fails or is cancelled stops reading your rows before it returns — and waits for the row your source is producing to do so: an iterator that waits for its rows (a feed) should honour its cancellation token (`[EnumeratorCancellation]`), or a failed load returns only when the feed's next row arrives. |
| `Aouda:BulkLoad:StreamingRequestTimeoutMs` — *since 0.1.22* | int | `600000` | `>=0` (`0` disables) | Server config | Request deadline for `:append` and `:commit` only. These two opt out of `Aouda:RequestTimeoutMs` (30 s), which still governs every other endpoint. Not the bound on an abandoned session — `SessionIdleTimeoutMinutes` is. |
| `Aouda:BulkLoad:SessionIdleTimeoutMinutes` | int | `10` | `>=0` (`0` disables) | Server config | How long an in-flight session may make no progress before the sweeper aborts it and releases its table lock and ingest budget. |
| `Aouda:BulkLoad:MaxConcurrentStreamingRequests` — *since 0.1.22* | int | `4` | `>=0` (`0` = unlimited) | Server config | Size of the admission lane `:append` runs in. It does not draw on `Aouda:MaxConcurrentRequests` (50), because a multi-minute call would hold one of those permits for its whole duration. (**Lead S18a, 0.6.0**) `:commit` is on no lane: it waits for its table lock and the engine (whose segment I/O is bounded server-wide), and on the lane four `:append`s gated behind an earlier job could hold every permit while that job's `:commit` waited for one. Run no more loaders into one table at once than this setting — (**Lead S31, 0.6.0**) and, once jobs are larger than `Aouda:BulkLoad:MaxQueuedAppendBytes`, no more than half as many pipelined loaders (two `:append`s each) (**BL-1117**). |
| `Aouda:BulkLoad:StreamingRequestQueueLimit` — *since 0.1.22* | int | `100` | `>=0` | Server config | How many streaming requests may wait for a lane slot; beyond it, 503. Generous by design: a rejected `:append` must be recovered by its client (a keyed `:begin`, then the same body — **Lead S21a, 0.6.0**), so a rejection costs the load a round of recovery or, in a client that does not recover, the load. |
| `Aouda:MaxConnections` | int | `0` | `>=0` (`0` = unlimited). On 0.1.20 and earlier the default was `100` and `0` failed startup | Server config | Kestrel's concurrent-connection ceiling. `0` (unlimited) is the default from 0.1.22. A finite value must stay above `MaxConcurrentRequests + RequestQueueLimit`, or Kestrel closes sockets with no HTTP response. |

**`:append` is not retried blindly.** (**Lead S21a, 0.6.0**) A job's frames are numbered across its bodies and the server
applies each number once — a frame below the job's `nextSequence` is acknowledged and skipped — so sending a body again after its
answer was lost no longer duplicates its rows. The recovery is still not a blind re-post: a stale request may still be reading the
cut body, so first send `:begin` with the job's idempotency key (it stops that request and answers `nextSequence`), then send the
body again, or its frames from `nextSequence` on. The C# SDK does exactly that, a bounded number of times, and so does
`@aouda/client` (**Lead S22, 0.6.0**: 4 attempts; until then it left a failed `:append` to the caller). Neither SDK's retry
policy re-sends an `:append` on its own. Before Lead S21a the server applied every frame it was sent, and a replayed
`:append` duplicated every row the first attempt landed — silently (see the [HTTP reference](../reference/http-api.md#a-jobs-frames-are-numbered-lead-s21a-060)).

Precedence notes:
- Begin-time options (`BulkLoadOptionsDto`) set per-job ingest and replication behavior.
- Commit-time body carries write-concern request (`BulkLoadCommitRequest.WriteConcern`).
- Cluster policy (`ForceLogShipBulkLoad`) can invalidate request-level replication mode.

---

## 2.11 API and CLI coverage reference

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Begin bulk-load session | Client coordinator via `BulkLoadAsync`/`BulkLoadMultiTableAsync` | Reported in P20 completion (`client.table(...).bulkLoad`, `bulkLoadMultiTable`) | `POST .../bulk-load:begin` | Implemented | TS evidence is completion-doc based in this repo. |
| Append a chunk | Internal client coordinator (frames, or JSON column arrays) | Reported in completion docs | `POST .../{jobId}:append` | Implemented | `application/vnd.aouda.column-batch-v2` or `application/json` column arrays (**Lead S12, 0.6.0**; `application/x-ndjson` is refused `415 ROW_OBJECTS_UNSUPPORTED`). |
| Commit load | `BulkLoadAsync` returns `BulkLoadJobHandle` | Reported in completion docs | `POST .../{jobId}:commit` | Implemented | Includes write-concern fields. |
| Abort load | Best-effort abort in coordinator cancellation path | Reported in completion docs | `POST .../{jobId}:abort` | Implemented | Explicit operator abort route also exists. |
| Get status/progress | `BulkLoadJobHandle.GetProgressAsync` via status polling path | Reported in completion docs | `GET .../{jobId}` | Implemented | Deferred work + replica progress DTOs. |
| List in-flight/history jobs | No public .NET client helper found in this repo | Reported Studio/admin helper mention in completion docs | `GET .../bulk-load:list` | Partial | Server route shipped; .NET convenience API missing in current source snapshot. |
| Force abort job | No public .NET client helper found in this repo | Reported Studio/admin helper mention in completion docs | `POST .../bulk-load:force-abort` | Partial | Server route shipped; client helper not in current source snapshot. |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Strongly typed .NET admin list/force-abort helpers | Public `AoudaClient` methods for list/force-abort | Call HTTP routes directly | Post20-S3 follow-up area | Medium |
| Persistent resume after server restart | Server-side adopted in-flight session API | Re-`begin` with same idempotency key; restart from durable offset contract | `BL-067` | High |
| Fully wired multi-node concern barrier | Engine-level replica ACK wait path | Use `One/Acknowledged` and external lag monitoring | BL follow-up (replication) | High |

Examples:

```csharp
// .NET single-table bulk load
var handle = await client.BulkLoadAsync(
    "orders",
    rows,
    new BulkLoadOptions
    {
        IdempotencyKey = "orders-2026-05-19-b1",
        WriteConcern = WriteConcern.Majority,
        ReplicationMode = BulkLoadReplicationMode.LogShipSegments
    },
    ct);

// (Lead S13, 0.6.0) Columnar data: ColumnBatch streams, written as frames straight from their arrays
var batchHandle = await client.BulkLoadAsync(
    "orders",
    batches, // IAsyncEnumerable<ColumnBatch>, IReadOnlyList<ColumnBatch> or one ColumnBatch
    new BulkLoadOptions { IdempotencyKey = "orders-2026-10-18-b1" },
    ct);

// Seed reserved autoIncrement IDs (BL-131) — Bond isAutoIncrementDisabled: true
var seedHandle = await client.BulkLoadAsync(
    "orders",
    seedRows, // each row must include every autoIncrement column (0 is a real value)
    new BulkLoadOptions
    {
        IdentityInsert = true,
        IdempotencyKey = "orders-reseed-2026-07-31",
        ForceSingleNodeReplicationBypass = true
    },
    ct);
```

```typescript
// TypeScript surface (aouda-client-ts)
await client.table("orders").bulkLoad(rows, {
  idempotencyKey: "orders-2026-05-19-b1"
});

await client.table("orders").bulkLoad(
  [{ id: 1000, status: "seeded" }, { id: 0, status: "literal-zero" }],
  { identityInsert: true, idempotencyKey: "orders-reseed-2026-07-31" }
);
```

```http
POST /api/databases/main/bulk-load:begin
Content-Type: application/json

{
  "database": "main",
  "tables": ["orders"],
  "idempotencyKey": "orders-reseed-2026-07-31",
  "options": {
    "replicationMode": "logShipSegments",
    "identityInsert": true
  }
}
```

Common mistakes:
- Sending rows above `MaxRowsPerAppend` in one append call.
- Omitting `_table` discriminator for multi-table append rows.
- Reusing idempotency keys across different databases.
- Using `identityInsert: true` without supplying every autoIncrement column on every row (including literal `0` when you mean zero).
- Expecting a failed/aborted identity-insert job to advance the autoIncrement counter (it does not).

---

## 2.12 Scenario playbooks

### Scenario 1: Single-table production load with durable resume key

When to use: high-volume ingest into one table with retry safety.

Steps:
1. Choose stable idempotency key (`dataset-batch-id`).
2. Run `.NET` `BulkLoadAsync` with `ReplicationMode=LogShipSegments`.
3. Monitor returned `BulkLoadJobHandle` and, if deferred work is not awaited, poll progress.

Expected checks:
- Commit returns `jobId`, `rowsLoaded`, `walPosition`.
- `WriteConcernTimedOut` is `false` or explicitly handled.
- `GET .../{jobId}` eventually reports terminal state.

### Scenario 2: Multi-table atomic load over HTTP

When to use: normalized imports where rows for multiple tables must commit together.

Steps:
1. `POST .../bulk-load:begin` with `tables: ["runs","steps","messages"]`.
2. Send rows to `:append` with a `_table` column naming each row's table (**Lead S12, 0.6.0**: column arrays, where it was NDJSON rows each carrying `_table`; see the [HTTP reference](../reference/http-api.md#post-jobidappend)).
3. `POST ...:commit` with optional `waitForDeferredWork` and `mqWaitMs` (**WorkloadCore S09, 0.3.0**).

Expected checks:
- A row without `_table` is rejected with `BULK_LOAD_MISSING_DISCRIMINATOR`: *Row {n} of this :append …*, `details: row={n}` (1-based; **Lead S12, 0.6.0**: it said "Row at line N"). The rows before it stay credited.
- Commit response includes `perTableRowCounts`.
- Any abort leaves session in `aborted` and no successful commit response.

### Scenario 3: Operator force-abort of stuck job

When to use: in-flight job is blocked and client path is no longer trusted.

Steps:
1. Call `GET .../bulk-load:list` and identify active `jobId`.
2. Call `POST .../bulk-load:force-abort` with `jobId` and reason.
3. Confirm `GET .../{jobId}` returns `aborted`.

Expected checks:
- Force-abort returns `{ jobId, aborted: true }`.
- Further append/commit attempts for that job are rejected by state checks.

### Scenario 4: Seed reserved autoIncrement IDs (identity-insert)

When to use: large seed/reseed/ingestion where you must preserve upstream IDs (including `0`) and keep the table's `autoIncrement` schema flag on. Prefer this over flipping the column to manual (BL-126) for a one-shot load.

Steps:
1. `POST .../bulk-load:begin` with `options: { "identityInsert": true }` (or C#/TS `IdentityInsert` / `identityInsert: true`).
2. Append rows that give every autoIncrement column on every row — not absent, not `null` (frames or JSON column arrays; **Lead S12, 0.6.0**: NDJSON is refused).
3. Commit successfully — only then does the server call `EnsureMinimumValue` to `max(inserted)` per column.
4. Verify a subsequent ordinary insert with `id: 0` returns `max + 1`.

Expected checks:
- Missing/`null` autoIncrement column fails the job; counter unchanged.
- Abort or stream failure before successful commit does **not** bump the counter.
- Multi-table jobs track maxes per destination table (`_table` discriminator).

See also: ordinary multi-row insert `identityInsert` in [HTTP API](../reference/http-api.md) (BL-130) when the dataset fits a single `POST …/rows` request.

---

## 2.13 Operations and observability

What to monitor first:
- In-flight jobs (`bulk-load:list`).
- Job state transitions (`acquired`, `appending`, `committing`, `deferred`, `completed`, `failed`, `aborted`).
- Replication fetch pressure and lag counters for bulk load.
- Cluster policy violations (`Perf.BulkLoadReplicationModeOverriddenTotal`).

Recovery expectations:
- Failed/aborted sessions remain in registry until sweeper retention expires.
- Watchdog emits abort frames for expired in-flight jobs.
- Operator force-abort is available without waiting for session retention timeout.

Quick-answer matrix:

| Question | Practical answer |
|---|---|
| Why does append return 400 for valid JSON rows? | Usually `MaxRowsPerAppend` cap or missing `_table` in multi-table jobs. |
| Why did commit return concern timeout but still load data? | Concern barrier timed out; primary durability may still be complete. |
| Why is resumed cursor not advancing during append? | Current server session cursor update is commit-centric in Stage 1. |
| Why was replication mode rejected? | Cluster has `ForceLogShipBulkLoad=true`. |

### Reading `:commit completed` and the job-shape warning

Every `:commit` logs a `BulkLoad :commit completed …` line carrying: `commitMs`, `lockHoldMs`, `mqPublishBacklog`, `segments`, `partitions`, `segmentWriteMs`, `finalizeMs`, `walMs`, `catalogSaveMs`, `medianRowsPerSegment`, `p95RowsPerSegment`, `minRowsPerSegment`, and `bufferHighWaterRows`; (**WorkloadCore S09, 0.3.0**) it ends with `postCommitMs`, `mqWaitMs` and `mqStatus`. If a table's segment shape quietly regresses, `medianRowsPerSegment` and `bufferHighWaterRows` are where it shows first.

⚠️ **If you are on a release before this line's own log category shipped (**BL-632, 0.1.37**), you will not see it at all.** The server's default log level is `Warning`, and until BL-632 this line had no carve-out — so on a container with no `appsettings.json` and no `Logging__LogLevel__*` environment variable it was filtered out, and a bulk load that spent minutes in `:commit` left no server-side trace of where the time went. From that release it is emitted by default under the category `Aouda.Server.Observability.BulkLoadCommitLog`. To silence it, or to turn it back up on an older build:

```bash
# turn it off
Logging__LogLevel__Aouda.Server.Observability.BulkLoadCommitLog=Warning
# turn it on (any release)
Logging__LogLevel__Default=Warning
Logging__LogLevel__Aouda=Information
```

**(**BL-632, 0.1.37**) Read `commitMs` first — it is the total the rest of the line has to add up to.**

| Field | What it tells you |
|---|---|
| `commitMs` | How long the `:commit` call itself took, measured server-side across the whole request. This is the number a client experiences. (**WorkloadCore S09, 0.3.0**) It is the commit itself, to durable: it no longer includes the wait for the load's materialized queries, which follows it as `mqWaitMs`. |
| `lockHoldMs` | How long the exclusive table lock was held — the **whole session**, from `:begin`; (**Lead S19, 0.6.0**) until the job's rows ended, when the lock passes to the next job queued on the table. `lockHoldMs` far exceeding `commitMs` means the session was long, which is the recommended shape. Another writer to those tables waits for the lock and for the commit after it. |
| `mqPublishBacklog` | Materialized-query publishes outstanding on this database once this job queued its own, **including this one**, so `1` is the normal value for a load with a query attached. A figure that climbs job over job means the loader is committing faster than its materialized queries can publish. (**WorkloadCore S10, 0.3.0**) It counts the database's pending bulk-load jobs — loads whose table's pass has not yet run, this one included. See [Materialized queries](materialized.md). |
| `mqKeyedLive`, `mqKeyedAbsent`, `mqKeyedUnresolved`, `mqKeyedLocated` | (**BL-662 / BL-664, 0.1.39**) — appended at the end of the line. How this database's materialized-query publishes found the existing result row for each group they touched, counted since the server opened the database:<br>• `live`: found in memory by primary key.<br>• `absent`: proven not to exist anywhere, cold storage included (**BL-663**).<br>• `unresolved`: neither, so the result table was read for it.<br>• `located`: the part of `unresolved` that exists in a segment, so its row had to be read. The rest of `unresolved` is keys nothing could decide.<br>They count lookups, not distinct rows. Read them as a ratio, and as the difference between two lines: a publish runs after its own commit, so each line includes every publish that has finished so far. A growing share of undecided keys (`unresolved` minus `located`) means publishes are searching again. |
| `rowLoopMs`, `rowWaitMs`, ~~`mqFeedMs`, `mqDrainMs`, `mqStageWaitMs`~~ | (**WorkloadCore S10, 0.3.0**) `mqFeedMs`, `mqDrainMs` and `mqStageWaitMs` are removed: a load does no materialized-query work while it streams, so there is no stage to report. (**IngestAtSpeed S01 / S13, 0.1.40**) — appended at the end of the line. Where the session's row loop spent its time. `rowLoopMs` is the loop's wall time across the **whole session**, every `:append` included, so it can exceed `commitMs`. `rowWaitMs` is the part spent waiting for your client's next row (the append channel empty): it is your loader's time, not the server's. The materialized-query work runs on a stage beside the loop (**S13**): `mqFeedMs` is the stage's per-row feed, `mqDrainMs` its spill and build-buffer work, and both overlap `rowLoopMs` rather than adding to it. `mqStageWaitMs` is how long the loop waited for that stage; a large share of `rowLoopMs − rowWaitMs` there means the materialized queries, not the table write, set the ingest rate. (`mqInlineDrainMs`, from S01, is gone: the drains are no longer inline.) |
| `commitWaitMs` | (**Lead S19, 0.6.0**) — appended at the end of the line. The part of `commitMs` this job's commit point waited for an earlier job on the same table to commit: commits on a table are first in, first out. `0` unless jobs were pipelined into one table. |
| `postCommitMs`, `mqWaitMs`, `mqStatus` | (**WorkloadCore S09, 0.3.0**) — appended at the end of the line. `postCommitMs` is the time the engine spent after the load's commit point, outside the table lock: since the queries' maintenance no longer runs there, the hand-off of that maintenance. `mqWaitMs` is how long `:commit` then waited for the load's queries (the response's `mqWaitedMs`), and `mqStatus` how that ended (as in the response). BL-789's `mqPassWaitMs` and `mqPassMs` are gone with the pass that ran inside `:commit`. |

⚠️ **The phase fields do not have to sum to `commitMs`, and the gap is the point.** `segmentWriteMs`, `finalizeMs`, `walMs` and `catalogSaveMs` cover the coordinator's own work. Anything left over — buffer drain, spill merge waits, admission — is time nobody has attributed yet. Before `commitMs` existed there was no way to notice that there was a remainder at all.

**Each materialized-query publish also logged one line at `Warning`** (**IngestAtSpeed S01, 0.1.40**; **WorkloadCore S10, 0.3.0**: gone with the ingest-fed publish it described — a load's queries are brought in by the table's pass) — `Warning` so the default log level keeps it:

```
[AoudaEngine] MQ publish source=EquityTrade queries=6 lockWaitMs=0 totalMs=412 perQuery=[EquityTradeChange1D:maintained:38ms:live=120:absent=0:unresolved=0, ...]
```

`lockWaitMs` is how long the publish waited for its queries' locks, which is time spent behind another publish or a refresh. For each query, the line gives how it was published (`maintained`, `built`, `fallback` to a rebuild by scan, `failed`, `deferred`), how long that took, and how its keyed reads were resolved. It is the line that tells you *which* query holds the drain back. The post-load coalescing line, which says how many rebuild scans were avoided, is now `Warning` too.

⚠️ **One remainder is attributed: the publish-backlog wait.** From **0.1.38**, a load on a table
with materialized queries can wait *after* its rows are durable, until the memory budget has room
for another queued publish (BL-641). A `commitMs` of about **60 s** that barely changes with row
count is that wait running to its limit. In 0.1.38 it did so on every job whenever the publish queue
had stopped draining. From (**BL-661, 0.1.39**) a load waits only while publishes are still
settling: the first load to meet a stalled queue waits at most 10 s, and later loads do not wait.
The rows are committed either way. A `mqPublishBacklog` that climbs by one per job and never falls
means the queue has stalled, and the server logs one Warning per stall.

(**IngestAtSpeed S10, 0.1.40**) **Batches all the way to the ingest buffer.** The rows of an
`:append` stay in the column batches they were decoded into (from either format) until they reach
the ingest buffer. Auto-increment ids are written into the batch rather than into a copy of each row,
partition keys are computed once per distinct value in a batch, and typed values are copied without
boxing. What is loaded does not change. The queue between `:append` and the engine is now bounded in
bytes and charged to the memory governor (`MaxQueuedAppendBytes` above).

(**IngestAtSpeed S09, 0.1.40**) **The SDKs send rows column by column.** Against a server that
advertises it in `:begin` (`acceptedAppendFormats`), `Aouda.Client` and `@aouda/client` send each
`:append` as a binary column-batch frame (`ACB2`, advertised as `"column-batch-v2"` since **Lead S09, next
train**; an `ACB1` body is refused `415 FRAME_VERSION_UNSUPPORTED`): typed values, each distinct string once per
batch, no JSON per row. Nothing changes in how you call `BulkLoadAsync` / `bulkLoad`, in what is loaded,
or in the resume cursor. A batch holding something the frame cannot carry (a nested object, an array, a
column whose rows disagree on type) is sent as NDJSON, and so is every batch to an older server. NDJSON
remained the format for curl and hand-written clients; the server decoded it without building a
dictionary per row. (**Lead S12, 0.6.0; breaking**) NDJSON is gone: `:begin` advertises
`["column-batch-v2", "column-arrays"]`, and what a frame cannot carry — and anything curl or a hand-written client sends — is one
JSON column-array body (`application/json`, `{ "columns", "data", "absent"? }`) per `:append`. An NDJSON body is refused
`415 ROW_OBJECTS_UNSUPPORTED`. Both SDKs of this train send column arrays (`@aouda/client` from **Lead S14**). The format is specified in the [HTTP API reference](../reference/http-api.md).
On the 1 M-trade benchmark the load ran 10–25 % faster, with about 10 % less CPU per row while loading.

(**IngestAtSpeed S07, 0.1.40**) **The post-commit wait is gone.** A committed load hands its
publish off at once, so `commitMs` no longer carries a wait. Instead, a load into a table that feeds
materialized queries is **paced while its rows arrive** (`:append` accepts them more slowly).
(**WorkloadCore S10, 0.3.0**) That pacing is removed with the ingest-fed publishes it measured: a load is no
longer paced to a materialized-query drain, and what follows in this paragraph describes 0.1.40–0.2.x. Pacing
happens only when the queries are falling behind: the rows committed but not yet published exceed what
the drain can clear in **60 s**, at the drain rate measured over the last minute. Below that,
and before any publish has completed, nothing is paced. A load is never refused for this and never
stopped: at worst it is admitted at a tenth of the fastest drain the database has shown. A load into a
table no materialized query reads from is never paced. The stall Warning and its `commitMs` signature
no longer exist.

Why it stalled, and what changes (**BL-662, 0.1.39**): a publish into a query that already has
rows reads back and rewrites every group the job touched. Until now both halves scanned the whole
result table once per 64 groups, so one publish cost *groups touched × result size*. On a
per-security trade load the largest result is a minute-bucket OHLC query, and one publish could
outlast the next dozen jobs, with every later publish queued behind it. From 0.1.39 both
halves use the result table's primary-key index wherever it is authoritative, so a publish costs
roughly what the job touched, whatever the result's size. (**BL-663, 0.1.39**) This includes a
result table the server has demoted to cold storage. A group that does not exist yet is proven new
from the segments' own indexes, without a scan: a new security, or buckets later than anything
stored. `MqRebuildCompleted` still means "published, and its dependants caught up". More precisely
(**BL-665, 0.1.40**): it completes once the load is published and every change admitted before the
publish finished has reached the dependants. Writes that arrive later are applied as usual and are
not waited for, so a steady writer on another client can no longer keep it from completing.

(**IngestAtSpeed S05, 0.1.40**; **WorkloadCore S10, 0.3.0**: a load's queries are now written by the table's pass) Each materialized query on the table publishes in its own lane,
so a slow query (a minute-bar OHLC over millions of groups, say) no longer delays the others. A
query still publishes one load at a time, in order. `lockWaitMs` on the server's publish line is the
longest any single query waited, and each `perQuery` entry reports its own `wait=`.

(**IngestAtSpeed S06, 0.1.40**; **WorkloadCore S10, 0.3.0**: replaced by the table's pass, which takes every
pending job on the table in one read) When loads commit faster than a query can publish, the waiting
loads no longer queue one publish each. A load whose `aggregate` or `latestPerKey` delta would wait
behind another load's still-waiting publish is merged into it, so the work waiting grows with the
groups touched rather than with the number of jobs. Its `MqRebuildCompleted` still resolves only once
its rows are in the result. On the publish line a merged load reports `name:merged->maintained`, and the
publish that absorbed it reports `merged=N`. `mqPublishBacklog` still counts loads whose publish has not
completed, merged or not.

⚠️ **A rising `mqPublishBacklog` and a directory full of spill files are the same symptom.** A queued publish keeps its build spill on disk until it runs, so a backlog looks exactly like a leak from the filesystem. Check this number before concluding anything from a file count.

**(P45)** Six fields are appended after the ones above — `SpillRunsCreated`, `SpillRunsMerged`,
`SpillWriteMs`, `SpillMergeMs`, `SpillRunBytesWritten`, `SpillBytesWritten` — reporting the job's
spill-and-merge activity when its ingest buffer budget was exceeded (see [Choosing partition storage
mode](#choosing-partition-storage-mode) and the budget formula above). The ten original fields listed
above are unchanged in name, order and meaning. A job that never reaches its ingest-buffer budget writes
no runs and pays no merge cost, so all six spill fields are zero — the common case on a well-provisioned
host.

A job whose segment count is high and whose median rows/segment is low also logs one additional, advisory `Warning` — never more than one per job, and it never blocks or delays the commit (a storage-mode consequence is never a hard failure). It names one of two likely causes:

- A destination table in `Dedicated` partition storage with many live partition keys — see [Choosing partition storage mode](#choosing-partition-storage-mode).
- Many short `:begin`/`:append`/`:commit` cycles instead of one long session — see [Sizing a session](#sizing-a-session-fewer-longer-one-commit).

Both thresholds are configurable (`Aouda:BulkLoad:JobShapeWarnSegmentThreshold`, default `64` segments; `Aouda:BulkLoad:JobShapeWarnMedianRowsPerSegmentThreshold`, default `1000` rows) — see `2.3`.

---

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `403 AUTHORIZATION_DENIED` on `:begin` or `:append` (**BL-1031, 0.5.0; BL-1227, next train**) | A table in the load has PLS or RLS, and the caller lacks, at `write`, the grant for a restriction it has (the message names the table and `all-partitions` / `all-rows`) | Load with that database's `mk_svc_` key or as a `db_admin` user, or have a role grant the missing grant at `write`. Ordinary inserts remain the per-user write path. |
| "Bulk load is not supported for table '…' at durability 'memory'" (**Lead S26, 0.6.0**) | The table's durability level is `memory` (no data files) — `MemoryOnly` before | Load into a table at another level; a table cannot be altered to or from `memory` after it is created. |
| `400 BULK_LOAD_INVALID_OPTIONS` on `:begin`, the message naming a durability level (**Lead S26c, 0.6.0**) | The level is not `strict` or `os` (lower case); `strict` in a database at `os`; or `os` for a multi-table job, a table with vector columns, or an edge or vector table | Send `strict` or `os`, or omit it. A multi-table load, or a load into a table with vector columns or an edge or vector table, has no level it may use in an `os` database. |
| `GET {jobId}` answers `lost` with `durability: "os"` (**Lead S26c, 0.6.0**) | The server lost power before it had synced the job; at the next open its files did not match its commit record, so it was dropped whole | Load it again with the same idempotency key: it no longer names a commit. |
| `BulkLoadInvalidOptions` on begin with `skipReplication` | Multi-node safety/policy check failed | Use `logShipSegments` or explicit bypass where allowed. |
| `BulkLoadMissingDiscriminator` during append | Multi-table load row missing `_table` | Give every row a `_table` value within the declared table set. |
| `415 ROW_OBJECTS_UNSUPPORTED` on append | The body is NDJSON (`application/x-ndjson`), no longer read (**Lead S12, 0.6.0**) | Send column-batch frames, or the rows as one JSON column-array body (`application/json`); upgrade the client library. |
| `BulkLoadCursorMismatch` from client | Client send position diverges from server durable cursor expectations | Retry from returned durable cursor and keep same idempotency key. |
| `BulkLoadTableLocked` | Concurrent load holds table lock | Retry with same idempotency key or wait for lock release. |
| `AlreadyTerminal` on force-abort | Job already completed/aborted/failed | Treat as no-op; inspect job history instead. |
| `503 MEMORY_BUDGET_EXCEEDED` on a column-batch `:append` (**BL-831, 0.3.0**) | Memory is short; the frame was refused before it was decoded | Wait `Retry-After` and resume with the same idempotency key from `:begin`'s `nextSequence` (**Lead S21a, 0.6.0**); the session is still open. Both SDKs do it themselves. |
| `409 BULK_LOAD_COMMIT_QUEUED` on a committing `:append` (**Lead group 5 review, 0.6.0**) | The job is still queued behind another load on its tables; the body's frames were applied | Send `:commit` for the job; send no row again. Both SDKs do it themselves. |
| `503` on `:commit` (`MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`) | The commit was refused for capacity — (**BL-831, BL-928, 0.3.0**) its spill merge running out of heap included; nothing was applied | Wait `Retry-After`, then run the load again from `:begin`. A `500` that says the load committed is the opposite case: do not resend. |
| Commit reports timed-out write concern | Replica barrier not achieved in timeout window | Inspect replica lag, then decide retry/read policy. |

---

## 2.15 Verification ledger

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Engine force-log policy | `dotnet test tests/Aouda.Engine.Api.Tests --filter BulkLoadForceLogShipTests` | Not run in S2 session | 2026-05-19 | Source evidence reviewed from test file. |
| Watchdog lifecycle | `dotnet test tests/Aouda.Engine.Api.Tests --filter BulkLoadWatchdogLifecycleTests` | Not run in S2 session | 2026-05-19 | Source evidence reviewed from test file. |
| HTTP begin/commit/list/force-abort | `dotnet test tests/Aouda.Server.Tests --filter "BulkLoadControllerBeginTests|BulkLoadControllerCommitTests|BulkLoadListRouteTests"` | Not run in S2 session | 2026-05-19 | Integration tests exist and were inspected. |
| Replica coordinator state machine | `dotnet test tests/Aouda.Engine.Replication.Tests --filter BulkLoadReplicaCoordinatorTests` | Not run in S2 session | 2026-05-19 | Concurrency and cancellation behavior covered. |

---

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| HTTP begin validation and idempotency | `tests/Aouda.Server.Tests/BulkLoad/BulkLoadControllerBeginTests.cs` | Not run in S2 session | Strong | Covers empty tables, duplicates, idempotency, mode validation. |
| HTTP commit semantics | `tests/Aouda.Server.Tests/BulkLoad/BulkLoadControllerCommitTests.cs` | Not run in S2 session | Strong | Covers success, duplicate commit, invalid write concern, jobId mismatch. |
| Admin list and force-abort routes | `tests/Aouda.Server.Tests/BulkLoad/BulkLoadListRouteTests.cs` | Not run in S2 session | Strong | Covers list snapshots and terminal-state force-abort behavior. |
| Replica state machine and fetch concurrency | `tests/Aouda.Engine.Replication.Tests/Replay/BulkLoadReplicaCoordinatorTests.cs` | Not run in S2 session | Strong | Covers staged/committed transitions, concurrency, dedup, cancellation. |
| Cluster force-log policy | `tests/Aouda.Engine.Api.Tests/BulkLoad/BulkLoadForceLogShipTests.cs` | Not run in S2 session | Medium | Confirms policy rejection and perf counter increments. |
| Watchdog lifecycle integration | `tests/Aouda.Engine.Api.Tests/BulkLoad/BulkLoadWatchdogLifecycleTests.cs` | Not run in S2 session | Medium | Verifies registration/clear/dispose paths. |
| Client protocol orchestration and error mapping | `tests/Aouda.Client.Tests/BulkLoad/BulkLoadCoordinatorTests.cs` | Not run in S2 session | Medium | Covers the append content type, cursor mismatch, deferred polling. |

---

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| Server append-time durable cursor progression | Cursor contract is currently commit-centric in session registry | End-to-end test asserting non-zero `rowsDurablyCommitted` progression during append | High |
| HTTP topology safety gate | `IsMultiNodeCluster` is stubbed false | Server integration test with injected multi-node topology stub expecting skip-replication rejection | High |
| Admin .NET convenience surface | Routes exist but public client helper not evident | Client API tests for typed list/force-abort helper methods once added | Medium |
| Restart resume adoption flow | `AdoptInFlight` not implemented | Crash/restart integration test for idempotency resume from WAL-reconstructed in-flight job | High |

---

## 2.18 Known gaps and undone work

- **Persistent bulk-load sessions across restart are not implemented** (`BL-067`); current registry is in-memory.
- **P2P bulk segment fan-out is not implemented** (`BL-066`); primary-centric segment serving remains default.
- **Segment-level dedup across retried loads is not implemented** (`BL-069`).
- **HTTP multi-node safety gate is currently stubbed** (`IsMultiNodeCluster` returns false in controller helper), so strict runtime topology rejection is incomplete.
- **Engine write concern beyond primary on multi-node is partial**; current path throws timeout for non-`One` in multi-node mode.
- **TypeScript and Studio bulk-load admin surfaces are referenced by completion docs but not source-verified in this repository snapshot.**

---

## 2.19 References

- `docs/tasks/P20-COMPLETION.md`
- `docs/tasks/BL-COMPLETION.md`
- `docs/decisions/0030-bulk-load-replication.md`
- `docs/dev/BulkLoad-Ingest-Sizing-Guide.md` (engine repo — engineering-detail companion to `2.7`'s sizing subsections)
- `docs/tasks/BL/OutOfTheBox-Ingest-Overview.md`, `docs/tasks/BL/OutOfTheBox-Ingest-S05-Commit-Cost.md`, `docs/tasks/BL/OutOfTheBox-Ingest-S06-Fanout-Guardrails.md` (engine repo — single-node frame elision and job-shape guardrail sessions)
- `src/Aouda.Engine.Api/AoudaEngine.BulkLoad.cs`
- `src/Aouda.Engine.Api/BulkLoadOptions.cs`
- `src/Aouda.Engine.Storage/BulkLoad/BulkLoadCoordinator.cs`
- `src/Aouda.Engine.Storage/BulkLoad/BulkLoadResumeWatchdog.cs`
- `src/Aouda.Engine.Storage/BulkLoad/BulkLoadClusterSettings.cs`
- `src/Aouda.Engine.Wal/WalTag.cs`
- `src/Aouda.Engine.Wal/WalPayloads.cs`
- `src/Aouda.Engine.Replication/Replay/FrameApplier.cs`
- `src/Aouda.Engine.Replication/Replay/BulkLoadReplicaCoordinator.cs`
- `src/Aouda.Engine.Replication/Checkpoint/CheckpointProtocol.cs`
- `src/Aouda.Engine.Replication/Checkpoint/CheckpointTransferServer.cs`
- `src/Aouda.Server/Controllers/BulkLoadController.cs`
- `src/Aouda.Server/Services/BulkLoadSessionRegistry.cs`
- `src/Aouda.Server/Services/BulkLoadSessionSweeper.cs`
- `src/Aouda.Client/AoudaClient.cs`
- `src/Aouda.Client/Internal/BulkLoadCoordinator.cs`
- `src/Aouda.Client/Exceptions/BulkLoadExceptions.cs`
- `src/Aouda.Cli/Commands/TableBulkLoadCommand.cs`
- `tests/Aouda.Engine.Api.Tests/BulkLoad/BulkLoadForceLogShipTests.cs`
- `tests/Aouda.Engine.Api.Tests/BulkLoad/BulkLoadWatchdogLifecycleTests.cs`
- `tests/Aouda.Engine.Replication.Tests/Replay/BulkLoadReplicaCoordinatorTests.cs`
- `tests/Aouda.Server.Tests/BulkLoad/BulkLoadControllerBeginTests.cs`
- `tests/Aouda.Server.Tests/BulkLoad/BulkLoadControllerCommitTests.cs`
- `tests/Aouda.Server.Tests/BulkLoad/BulkLoadListRouteTests.cs`
- `tests/Aouda.Client.Tests/BulkLoad/BulkLoadCoordinatorTests.cs`

---

## 2.20 What is missing from this document?

- This doc does not include line-by-line verification from `aouda-client-ts` or `aouda-studio`; TS/Studio claims are anchored to completion docs and should be cross-reconciled in S10 updates.
- Runtime benchmark numbers (throughput/lag SLO values) are not present in primary sources used for S2 and are intentionally omitted here.
- Some ADR 0030 operational endpoint suggestions are not implemented in current server code; this doc reports shipped behavior, not ADR intent-only surfaces.
