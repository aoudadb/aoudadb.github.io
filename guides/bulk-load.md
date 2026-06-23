---
title: "Bulk Load"
nav_order: 17
parent: "Guides"
---

# Aouda Functionality: Bulk Load

Document status: Complete
Primary owner: Engineering
Last updated: 2026-06-23

Coverage phases: P20, BL (Post20-S1, Post20-S3), P31
Primary task folders: `docs/tasks/P20/`, `docs/tasks/BL-COMPLETION.md`, `docs/tasks/P31/`
Primary ADRs: `docs/decisions/0030-bulk-load-replication.md`, `docs/decisions/0036-bulk-load-mq-refresh.md`
Related functionality docs: `docs/dev/Functionality-Write-Path-Durability.md`, `docs/dev/Functionality-Replication-And-Clustering.md`, `docs/dev/Functionality-Server-And-Multi-Database.md`, `docs/dev/Functionality-TypeScript-Client.md`, `docs/dev/Functionality-Studio.md`, `docs/dev/Functionality-Graph-And-Vector.md`

---

## Start Here

If your question is "How do I bulk load data safely with commit semantics?", start with:
- `2.7` (mental model and invariants)
- `2.11` (`.NET` + HTTP + CLI surfaces)
- `2.12` (single-table and multi-table playbooks)

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
| Server `Aouda:BulkLoad:SessionRetentionMinutes` | `10` | Completed/failed/aborted sessions remain queryable for 10 minutes before sweep. |
| Server `Aouda:BulkLoad:IdempotencyWindowMinutes` | `10` | Idempotency-key reuse window in server options. |
| Server `Aouda:BulkLoad:AllowWritePermission` | `false` | Bulk load remains admin-only unless compatibility mode is enabled. |
| Cluster `Aouda:BulkLoad:ForceLogShipBulkLoad` | `false` | When true, non-log-ship replication modes are rejected. |
| Client `AppendBatchSize` | `50000` | Client sends up to 50K rows per append, then honors server lower cap if returned. |
| Client `WriteConcern` | `Acknowledged` | Maps to server `acknowledged` commit concern request. |

---

## 2.4 Availability status

### Available now

- Engine bulk-load entry point: `AoudaEngine.BulkLoadAsync` (streaming/list overloads), including multi-table discriminator handling and force-abort helper.
- Storage coordinator and lock manager: `BulkLoadCoordinator`, `TableLoadLockManager`, `BulkLoadCommitMarker`.
- WAL contract implemented with tags `60/61/62`: `BulkSegmentCommitted`, `BulkLoadCommitted`, `BulkLoadAborted`.
- Replica-side bulk-load state machine in replay path: `BulkLoadReplicaCoordinator` + `FrameApplier` handlers.
- Checkpoint protocol support for bulk segment fetch message types `0x20`/`0x21`.
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
- Typed client exception family for lock/cursor/discriminator/options/duplicate-PK failures.
- CLI shipped for both single and multi-table:
  - `aouda table bulk-load`
  - `aouda bulk-load`
- **Materialized Query auto-refresh after bulk-load (P31 / ADR 0036):**
  - `PostLoadMqBehavior` option on `BulkLoadOptions`: `Auto` (default) triggers MQ rebuild after `BulkLoadCommitted`; `Skip` preserves old behavior.
  - `BulkLoadJobHandle.MqRebuildStatus`: tracks rebuild state (`Pending / InProgress / Completed / Skipped / Error`).
  - `BulkLoadJobHandle.MqRebuildCompleted`: `Task` that resolves when all dependent MQ rebuilds finish.
  - Replica coordinator: `MqRebuildScheduler` delegate triggers rebuild after all segments fetched.
  - Explicit on-demand refresh: `engine.RefreshMaterializedQueryAsync(name, ct)` and `POST .../materialized-queries/{name}:refresh`.
  - C# client: `client.MaterializedQueries.RefreshAsync(name, awaitCompletion, ct)`.
  - TypeScript client: `client.materializedQueries.refresh(name, { await: true })`.
  - CLI: `aouda mq refresh <name> [--await]` and `--skip-mq-refresh` on `aouda table bulk-load`.
  - `mqRebuildStatus` field in bulk-load job status response.

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
| BL Post20-S1 | `docs/tasks/BL-COMPLETION.md` Post20-S1 | Replication completion: replay coordinator, checkpoint segment fetch protocol, force-log-ship cluster setting, watchdog lifecycle integration | Further replication scalability behaviors | `BL-066` |
| BL Post20-S3 | `docs/tasks/BL-COMPLETION.md` Post20-S3 | Admin list/force-abort routes and Studio-facing server support | Studio UX evolution sits outside this repo | (tracked in Studio/task stream) |
| P31 (S1+S2) | `docs/tasks/P31/` | Materialized Query auto-refresh after bulk-load: `PostLoadMqBehavior`, `BulkLoadJobHandle.MqRebuildStatus`/`MqRebuildCompleted`, `RefreshMaterializedQueryAsync`, replica scheduler, HTTP refresh endpoint, C# + TS clients, CLI | Incremental rebuild (full only); cross-MQ dependency ordering; WebSocket rebuild progress | ADR 0036 |

---

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Row-WAL bypass bulk ingest | Yes | No | No | `AoudaEngine.BulkLoad.cs`, `BulkLoadCoordinator.cs` | Segment/job frames carry durability contract. |
| Segment-level WAL frame (`BulkSegmentCommitted`) | Yes | No | No | `WalTag.cs`, `WalPayloads.Encode/TryDecodeBulkSegmentCommitted` | Includes per-file BLAKE3 bytes. |
| Closing-frame atomic commit (`BulkLoadCommitted`) | Yes | No | No | `WalPayloads.Encode/TryDecodeBulkLoadCommitted`, coordinator commit path | Job-level atomic close unit. |
| Abort frame (`BulkLoadAborted`) | Yes | No | No | `WalPayloads.Encode/TryDecodeBulkLoadAborted`, watchdog/force-abort paths | Used by watchdog and operator abort. |
| Multi-table atomic bulk load | Yes | No | No | `AoudaEngine.BulkLoadAsync` (`AdditionalTables`), controller `_table` checks | Requires `_table` discriminator in rows. |
| Lock conflict policy (`Block`/`FailFast`) | Yes | No | No | `BulkLoadOptions`, `TableLoadLockManager`, controller errors | Exposed to client/CLI. |
| Durable cursor contract (`rowsDurablyCommitted`) | Yes | Yes | No | Protocol DTOs + controller/client code | Server session cursor is updated at commit; append-time cursor granularity is incomplete in Stage 1. |
| Resume watchdog lifecycle | Yes | No | No | `BulkLoadResumeWatchdog`, lifecycle tests | Default resume window 5 minutes. |
| Replica apply state machine | Yes | No | No | `BulkLoadReplicaCoordinator`, `FrameApplier` handlers | Includes acquired/fetching/staged/committed/aborted. |
| Segment fetch protocol (`0x20`/`0x21`) | Yes | No | No | `CheckpointProtocol`, `CheckpointTransferServer`, `BulkSegmentFetcher` | File-level chunk transfer plus hash verification. |
| Cluster policy `ForceLogShipBulkLoad` | Yes | No | No | `BulkLoadClusterSettings`, coordinator/controller checks, tests | Rejects skip/snapshot modes when enabled. |
| HTTP admin list + force-abort | Yes | No | No | `BulkLoadController` routes + list-route tests | Powering Studio admin workflow. |
| .NET client API (`BulkLoadAsync`, `BulkLoadMultiTableAsync`) | Yes | No | No | `AoudaClient.cs`, `BulkLoadCoordinator.cs` | Includes progress + deferred work behavior. |
| Typed exception family | Yes | No | No | `src/Aouda.Client/Exceptions/BulkLoadExceptions.cs` | Lock, cursor mismatch, discriminator, duplicate PK, invalid options. |
| CLI bulk-load commands | Yes | No | No | `TableBulkLoadCommand.cs` | Supports single and multi-table commands. |
| Persistent server session recovery across restart | No | No | Yes | `BulkLoadSessionRegistry.AdoptInFlight` stub | Explicitly not implemented yet. |
| P2P replica fan-out | No | No | Yes | ADR 0030 open question, backlog | Primary-centric transfer today. |
| Segment dedup on retry | No | No | Yes | ADR 0030 open question, backlog | Retry may duplicate segment rows. |
| Materialized Query auto-rebuild after bulk-load | Yes | No | No | P31 ADR 0036, `BulkLoadJobHandle.MqRebuildStatus`, `AoudaEngine.MaterializedQuery.cs` | Default `Auto` mode; `Skip` available for multi-step pipelines. |
| Explicit on-demand MQ refresh | Yes | No | No | P31 `RefreshMaterializedQueryAsync`, `POST .../materialized-queries/{name}:refresh` | Shadow-build; result table readable throughout with stale data. |
| Replica MQ rebuild after bulk-load | Yes | No | No | P31 `BulkLoadReplicaCoordinator.MqRebuildScheduler` | Triggered after all segments fetched on replica. |

---

## 2.7 Core concepts and mental model

### Core concepts

- **Streaming phase vs commit phase:** rows are appended over NDJSON in chunks, then closed by a commit call.
- **Durability unit:** durability is represented by WAL-visible segment/job events, not by row-level WAL entries.
- **Job-level atomicity:** query visibility is tied to closing-frame commit completion.
- **Replica catch-up model:** replicas consume WAL events and fetch segment files out-of-band.

### Invariants

1. Bulk load bypasses per-row WAL framing by design; this is not optional.
2. A load that reaches `BulkLoadCommitted` has a single, explicit WAL position for commit.
3. Multi-table jobs require `_table` discriminator on append payload rows.
4. `ForceLogShipBulkLoad=true` disallows skip/snapshot replication modes.
5. Aborts are WAL-visible (`BulkLoadAborted`), from either watchdog timeout or operator force-abort.

---

## 2.8 How Aouda implements it

High-level architecture path:

1. **API entry** (`AoudaEngine.BulkLoadAsync`) validates options/tables and maps request options to storage-layer config.
2. **Storage coordinator** (`BulkLoadCoordinator`) acquires table locks, writes bulk segments and `.bulkload.commit` markers, emits WAL frames.
3. **HTTP session registry** (`BulkLoadSessionRegistry`) manages in-memory job state for begin/append/commit/status/list.
4. **Replay path** (`FrameApplier` + `BulkLoadReplicaCoordinator`) decodes tag 60/61/62 frames and drives segment fetch/apply state machine.
5. **Checkpoint transfer path** (`CheckpointProtocol` + `CheckpointTransferServer` + `BulkSegmentFetcher`) moves bulk segment file bytes over message types `0x20`/`0x21`.
6. **Client coordinator** (`Aouda.Client.Internal.BulkLoadCoordinator`) orchestrates begin/append/commit and maps failures to typed exceptions.

### 2.8.1 Critical path walk-throughs

#### Path A: HTTP begin -> append -> commit

1. Client calls `POST .../bulk-load:begin` with tables and optional options.
2. Controller validates database/table list/options and starts/returns session from `BulkLoadSessionRegistry`.
3. Client streams NDJSON batches to `POST .../{jobId}:append` (`application/x-ndjson`).
4. Rows are pushed into session channel; engine consumes channel via `AoudaEngine.BulkLoadAsync`.
5. Client calls `POST .../{jobId}:commit`; controller completes channel and awaits engine task.
6. Engine returns `BulkLoadJobHandle`; controller sets session completed and returns commit response.

Tests: `BulkLoadControllerBeginTests`, `BulkLoadControllerAppendTests`, `BulkLoadControllerCommitTests`, `BulkLoadEndToEndTests`.

#### Path B: Primary commit -> replica fetch/apply

1. Primary emits `BulkSegmentCommitted` frames as segments are sealed and persisted.
2. Replica replay (`FrameApplier`) dispatches tag 60 to `BulkLoadReplicaCoordinator`.
3. Coordinator tracks segment expectation and schedules fetch through `SegmentFetcher`.
4. On closing frame tag 61, coordinator transitions to staged/committed depending on fetched set completeness.
5. Tag 62 marks job aborted and replica state transitions accordingly.

Tests: `BulkLoadReplicaCoordinatorTests`, `BulkSegmentFetchTests`, `BulkLoadCompactionWatermarkTests`.

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
| `BulkLoadOptions.PkUniquenessOverride` | enum? | `null` | `Strict`, `Recent`, `BestEffort` | Engine/API/client | Falls back to table config when null. |
| `BulkLoadOptions.PrincipalId` | `Guid` | `Guid.Empty` | valid guid | Engine/API | Stamped into bulk-load WAL frames. |
| `BulkLoadOptions.LockAcquisitionTimeout` | `TimeSpan` | `30s` | positive duration | Engine/API | Lock wait bound. |
| `BulkLoadOptions.BulkLoadResumeWindow` | `TimeSpan?` | `null` (watchdog default) | positive duration | Engine/API | Per-job override for watchdog timeout. |
| `Aouda:BulkLoad:MaxRowsPerAppend` | int | `100000` | `>0` | Server config | Per-append HTTP cap. |
| `Aouda:BulkLoad:SessionRetentionMinutes` | int | `10` | `>=1` | Server config | Retention for terminal sessions. |
| `Aouda:BulkLoad:IdempotencyWindowMinutes` | int | `10` | `>=1` | Server config | Idempotency key window. |
| `Aouda:BulkLoad:AllowWritePermission` | bool | `false` | `true/false` | Server config | Compatibility gate for write-only principals. |
| `Aouda:BulkLoad:ForceLogShipBulkLoad` | bool | `false` | `true/false` | Cluster/server config | Rejects non-log-ship modes. |

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
| Append NDJSON chunk | Internal client coordinator (`PostRawAsync` with NDJSON) | Reported in completion docs | `POST .../{jobId}:append` | Implemented | Content type `application/x-ndjson`. |
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
```

```typescript
// TypeScript surface is reported by P20 completion docs (verify in aouda-client-ts when needed)
await client.table("orders").bulkLoad(rows, {
  idempotencyKey: "orders-2026-05-19-b1"
});
```

```http
POST /api/databases/main/bulk-load:begin
Content-Type: application/json

{
  "database": "main",
  "tables": ["orders"],
  "idempotencyKey": "orders-2026-05-19-b1",
  "options": {
    "replicationMode": "logShipSegments"
  }
}
```

Common mistakes:
- Sending rows above `MaxRowsPerAppend` in one append call.
- Omitting `_table` discriminator for multi-table append rows.
- Reusing idempotency keys across different databases.

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
2. Send NDJSON rows to `:append`, each row containing `_table`.
3. `POST ...:commit` with optional `waitForDeferredWork`.

Expected checks:
- Invalid row without `_table` is rejected with `BulkLoadMissingDiscriminator`.
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

---

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `BulkLoadInvalidOptions` on begin with `skipReplication` | Multi-node safety/policy check failed | Use `logShipSegments` or explicit bypass where allowed. |
| `BulkLoadMissingDiscriminator` during append | Multi-table load row missing `_table` | Add `_table` for each row and keep within declared table set. |
| `BulkLoadCursorMismatch` from client | Client send position diverges from server durable cursor expectations | Retry from returned durable cursor and keep same idempotency key. |
| `BulkLoadTableLocked` | Concurrent load holds table lock | Retry with same idempotency key or wait for lock release. |
| `AlreadyTerminal` on force-abort | Job already completed/aborted/failed | Treat as no-op; inspect job history instead. |
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
| Client protocol orchestration and error mapping | `tests/Aouda.Client.Tests/BulkLoad/BulkLoadCoordinatorTests.cs` | Not run in S2 session | Medium | Covers NDJSON type, cursor mismatch, deferred polling. |

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
- `src/Aouda.Engine.Replication/Checkpoint/BulkSegmentFetcher.cs`
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
