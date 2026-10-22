---
title: "Write Path Durability"
nav_order: 6
parent: "Guides"
---

# Aouda Functionality: Write Path Durability

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-10-22

Coverage phases: P0, P1, P6, P7
Primary task folders: `docs/tasks/P6/`, `docs/tasks/P7/`
Primary ADRs: `docs/decisions/0066-guarantee-levels-durability-validation-currency.md`, `docs/decisions/0003-write-ahead-log.md`, `docs/decisions/0005-persistence-policies.md`, `docs/decisions/0010-cluster-membership-replication.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-RealTime-Streaming.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Auth-And-Authorization.md`

## Start Here

If your question is "How durable are writes by default, and how do I change behavior?", start with:
- [Durability levels](#durability-levels-lead-s26-next-train) — `strict`, `os`, `unlogged`, `memory`, and what each survives
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`

If your question is "What is implemented vs missing right now?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.15 Verification ledger`
- `2.16 Test coverage matrix`

---

## Durability levels (**Lead S26, next train**)

One word, `durability`, says what a write survives. It replaces the database's `enableWal` switch, the memory-only mode
(`dataDurability: MemoryOnly`), the per-table `EnableWal` and the declarative schema's `durability.walEnabled` — all four are gone,
with no alias (see [Refusals](#refusals-of-the-retired-names)). There are four levels, strongest first:

| Level | An insert / upsert / delete | Survives a process crash | Survives a power loss |
|---|---|---|---|
| `strict` (**default**, server and embedded alike) | WAL frames written through (fsync) before the rows are visible and acknowledged | Yes | Yes |
| `os` | WAL frames written to the operating system, not forced to disk, before the rows are visible | Yes | No |
| `unlogged` | No WAL: visible at once, durable when flushed to segments (a graceful shutdown flushes) | No — unflushed rows are lost | No |
| `memory` | No WAL and no data files (a memory-only table) | No | No — lost on any shutdown |

`memory` is what used to be `MemoryOnly`; `unlogged` is what used to be `EnableWal = false`.

### The database's level

A database's level is set where the database is created, and is read again at **every open**:

| Surface | How |
|---|---|
| HTTP | `POST /api/databases` body field `durability` (omitted → `strict`). See [HTTP API](../reference/http-api.md#post-apidatabases). |
| Server config | `Aouda:Databases:<db>:Durability` |
| Embedded | `AoudaEmbeddedOptions.Durability` (string, default `"strict"`) or config `Aouda:Durability` |
| CLI | `aouda databases create --durability <level>` |
| C# SDK | `CreateDatabaseOptions.Durability` (`client.Databases.CreateAsync(name, options)`) |
| TypeScript SDK | `client.databases.create(name, { durability })` (`DurabilityLevel` type) |

A database at `strict` or `os` has a WAL; one at `unlogged` or `memory` has none. `os` is a whole-database choice: the database
has one WAL file, and it is written through or not as a whole.

⚠️ **A database that has a WAL cannot be reopened at `unlogged` or `memory`.** That open is refused with an error, because it would
ignore the writes the WAL holds. Moving a database from a level with a WAL to one without has no path yet (BL-1145).

`GET /api/databases/{db}` reports the level as `options.durability` (a string; the boolean `options.enableWal` is gone).

### A table's level

A table may name its own level, or inherit the database's:

- Declarative schema: `"durability": { "level": "unlogged" }` on the table ([Schema](schema.md)). Engine API:
  `TableDurabilityOptions.Level`. Omitted → the table inherits the database's level.
- A table may name `strict`, `unlogged` or `memory`. **`os` is a database level only** — a table naming it is refused.
- **`strict` on a table needs a database at `strict`**; it is refused in an `os`, `unlogged` or `memory` database.
- **A table's storage is fixed when it is made.** Changing a table to or from `memory` after creation is refused; `strict` ↔
  `unlogged` may be altered.
- A table created while its database is at `memory` is a memory table — it records `memory`. A table that inherits from a database
  later reopened at `memory` reads as `unlogged`.

`GET /api/databases/{db}/tables/{table}` reports `durability: { "level": "...", "source": "table" | "database" }`: the level the
table's writes actually get, and where it came from. It is the effective level — a table that named `strict` in an `os` database reads
`os`. `policy.residency.dataDurability` is gone.

### Replication

A table at `unlogged` or `memory` writes no WAL frames, so **a replica receives none of its inserts**; asking for per-table
replication (`EnableReplication = true`) on such a table is refused. `strict` and `os` replicate as before — the level is the
primary's promise to the writer, not the replica's.

### Bulk loads

Unchanged: a bulk load is fsynced as today, whatever the table's level. A bulk load into a `memory` table is refused, naming the
level — a load writes segment files, which a memory table never has. See [Bulk Load](bulk-load.md).

### Refusals of the retired names

There is no alias and no shim; each old name is refused where it would have been read, and the error names its replacement:

| Old | Where | Now |
|---|---|---|
| `enableWal`, `dataDurability` | `POST /api/databases` body | **400** `INVALID_REQUEST` naming `durability` |
| An unknown level — including `"Strict"` (capitalised), `"MemoryOnly"`, `"everysec"` | `POST /api/databases` `durability` | **400** naming the four levels |
| `EnableWal`, `DataDurability` | `Aouda:Databases:<db>` server config | Startup validation fails, naming `Durability` |
| `EnableWal` (in code, or config `Aouda:EnableWal`) | Embedded | The open throws, naming `Durability` |
| `durability.walEnabled` on a table | Declarative schema | Validation error naming `durability.level` |
| `durability.walEnabled` in `settings` | Declarative schema | Validation error: the database's level is set where the database is created (`settings.durability` now carries only `replicationFactor`) |
| `--enable-wal` | CLI `aouda databases create` | Error naming `--durability` |

### Persisted formats

The catalog format is now **12** and the database registry format **3**. A data directory written by an earlier build is refused at
open, naming the version found and the version expected. Aouda is pre-1.0: there is no migration.

---

## 2.1 Why this functionality exists

Aouda durability makes write outcomes explicit instead of implicit.

- User problem solved:
  - "My process died; do I lose acknowledged writes?"
  - "Can I trade latency for stronger durability only when needed?"
  - "Can primary writes wait for replica acknowledgement?"
- Core outcomes:
  - Local crash durability with write-ahead logging (WAL).
  - Replay-driven recovery after kill/restart.
  - Replication-aware write concern (`One`, `Majority`, `All`) with timeout policy.
  - Table-level and database-level durability policy layering — one level per database, optionally narrowed per table
    (**Lead S26, next train**; [Durability levels](#durability-levels-lead-s26-next-train)).
- Non-goals (current implementation):
  - Full API surface for per-table write concern and replication controls via REST/SDKs.

## 2.2 Discovery and navigation map

### Question -> section map

- "What does each durability level survive?" -> [Durability levels](#durability-levels-lead-s26-next-train)
- "What are defaults?" -> `2.3`
- "What is available today?" -> `2.4`, `2.5`, `2.6`
- "How does the write path work end-to-end?" -> `2.8`, `2.8.1`
- "How do I configure server/db/table/per-write durability?" -> `2.10`
- "Which API/client surfaces are wired or missing?" -> `2.11`
- "How do I run this operationally?" -> `2.12`, `2.13`, `2.14`
- "What tests prove this behavior?" -> `2.15`, `2.16`, `2.17`

### Role-based map

- Platform engineer:
  - `2.8`, `2.8.1`, `2.10`, `2.13`
- App developer:
  - `2.3`, `2.10`, `2.11`, `2.12`
- SRE/operations:
  - `2.13`, `2.14`, `2.15`
- Reviewer/auditor:
  - `2.4`, `2.5`, `2.6`, `2.16`, `2.18`

### Source map

- WAL and replay core:
  - `src/Aouda.Engine.Wal/WalSegmentedLog.cs` (production writer: `{db}/wal/wal_%09d.log`)
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Wal/WalFlushQueue.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalReplayDriver.cs`
  - `src/Aouda.Engine.Wal/WalCheckpointControlFile.cs` (`{db}/wal/CHECKPOINT`)
  - `src/Aouda.Engine.Storage/WalIntegration/WalCheckpointer.cs`
- Engine write-path integration:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
  - `src/Aouda.Engine.Storage/Ingest/TableAppender.cs`
  - `src/Aouda.Engine.Api/Results/EngineInsertResult.cs`
  - `src/Aouda.Engine.Api/Results/EngineUpdateResult.cs`
  - `src/Aouda.Engine.Api/Results/EngineDeleteResult.cs`
- Durability policy models:
  - `src/Aouda.Engine.Storage/Registry/DatabaseOptions.cs`
  - `src/Aouda.Engine.Catalog/Policies.cs`
- Replication/write concern:
  - `src/Aouda.Engine.Core/Replication/WriteConcern.cs`
  - `src/Aouda.Engine.Core/Replication/TimeoutBehavior.cs`
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Engine.Replication/Streaming/PendingWriteTracker.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamServer.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamClient.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamProtocol.cs`
- Server API and config:
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigSection.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigConversion.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptionsValidator.cs`
- Protocol and clients:
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/types.ts`
  - `../aouda-client-ts/src/databases.ts`

## 2.3 Defaults and zero-config behavior

When you do not set durability knobs explicitly:

- Durability level (**Lead S26, next train**):
  - Database default `Durability = strict` (`DatabaseOptions`), server and embedded alike: WAL frames written through before a
    write is visible.
  - Table-level `Durability.Level` is nullable; null inherits the database's level.
  - On disk: segmented `{db}/wal/wal_%09d.log`. Crash recovery fast-forwards from `{db}/wal/CHECKPOINT`. A leftover monolithic `insert.wal` is refused at open (**BL-934, 0.4.0**: `aouda wal convert` is removed — restore from a backup taken by this version, or delete the file to discard its unreplayed writes).
  - (**BL-980, 0.4.0**) A log holding a frame of the retired page-append family (`Begin` / `Commit` / `Abort` / `InsertBatch` / `SealSegment`, which no current build writes) is refused when it is replayed — at open or by a point-in-time restore — with an error naming the frame; so is a `wal.manifest.json` without a WAL-root id. Neither is converted: restore from a backup taken by this version.
- Replication mode:
  - Database default `ReplicationMode = Replicate`.
- Write concern:
  - Database default `WriteConcern = One`.
  - Database default `WriteConcernTimeoutMs = 5000`.
  - Database default timeout behavior `OnWriteConcernTimeout = DegradeAndLog`.
  - Per-write override can be sent on DML protocol payloads.
- Effective resolution precedence:
  1. Per-write override (`Insert/Update/Delete` request field)
  2. Table durability override (`TableDurabilityOptions`)
  3. Database options defaults
- Guardrails (**Lead S26, next train**):
  - A table naming `os` is refused (a database level only); a table naming `strict` is refused unless the database is at `strict`.
  - A change to or from `memory` after a table is created is refused.
  - A database with a WAL cannot be reopened at `unlogged` or `memory` (BL-1145 for a path).

## 2.4 Availability status (implementation honesty)

### Available now

- Local durability via WAL append path for insert, update, and delete.
- WAL replay and crash-safe recovery paths, including torn-tail repair.
- Durable WAL checkpoints (`{db}/wal/CHECKPOINT`) that skip whole segment files below the redo horizon.
- Streaming replication over WAL frames (multi-database aware protocol versions).
- Write concern wait pipeline with quorum + timeout policies.
- Per-database durability level (`strict` / `os` / `unlogged` / `memory`) via server config, database API, embedded options, CLI
  and both SDKs (**Lead S26, next train**).
- Per-table durability level (`strict` / `unlogged` / `memory`) via the declarative schema and the engine/catalog model, with
  inheritance and validation; reported by `GET .../tables/{table}` as `durability` (**Lead S26, next train**).
- Health and metrics endpoints that expose key operational durability indicators.

### Planned / proposed

- REST and SDK exposure for the remaining per-table durability controls (`EnableReplication`, `WriteConcern`, `WriteConcernTimeoutMs`, `OnWriteConcernTimeout`).
- A path from a database level with a WAL (`strict`, `os`) to one without (`unlogged`, `memory`) — BL-1145.
- Client SDK mutation APIs exposing `WriteConcern` and result `WriteConcernStatus`.
- Full D.3 backup/restore durability scenario once the API surface exists.

### Reserved / not yet wired

- Per-database checkpoint synchronization in replication.

## 2.5 Phase coverage matrix

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| P0 | Durability bootstrap skeleton | Implemented | `docs/ROADMAP.md` |
| P1 | WAL and recovery baseline | Implemented | `docs/ROADMAP.md`, WAL/replay test files |
| P6 | Per-db and per-table durability controls, replication protocol, write concern | Partially implemented (API gaps remain) | `docs/tasks/P6/P6-EpicA-Task5-PerTableWalAndReplicationControl-Report.md`, `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`, `docs/tasks/P6/P6-EpicE-Task3-WriteConcernSynchronousReplication-Report.md` |
| P7 | Durability scenarios in harness | Implemented with one scenario deferred | `docs/tasks/P7/P7-Task6-DurabilityScenarios-Report.md` |

## 2.6 Capability coverage matrix

| Capability | Status | Notes |
|---|---|---|
| WAL append and fsync path | Implemented | Production writer is `WalSegmentedLog` (`wal_%09d.log`). |
| Insert/update WAL tagging with commit frame | Implemented | `TableAppender` emits begin/append/commit tags. |
| Delete WAL durability | Implemented | Deletes are WAL-backed (BL-054). |
| Crash recovery via WAL replay | Implemented | `WalReplayDriver` + storage tests/harness scenarios. |
| Checkpoint-assisted replay | Implemented | `{db}/wal/CHECKPOINT` + skip of whole segments below `redoStartPosition`. |
| Per-database durability level | Implemented (**Lead S26, next train**) | `DatabaseOptions.Durability`, config conversion/validation, create-database API, embedded, CLI, SDKs. |
| Per-table durability level | Implemented (**Lead S26, next train**) | `TableDurabilityOptions.Level`, declarative schema `durability.level`; reported on table GET. Other per-table controls: engine/catalog only. |
| Per-write write concern override | Implemented at protocol/server | `Messages.cs` fields + `TablesController` + `WriteConcernService`. |
| C# SDK write concern mutation API | Missing | `RemoteTableQuery` does not expose write concern argument. |
| TypeScript SDK write concern mutation API | Missing | `query-builder.ts` does not expose `writeConcern`. |
| TypeScript mutation `writeConcernStatus` | Missing | `types.ts` lacks status field present in protocol/server results. |
| Multi-database replication stream filtering | Implemented | v2/v3 protocol and per-database subscriptions. |
| Per-table replication filtering in stream | Implemented at protocol level | v3 table subscription filters and server-side filtering counters. |
| Per-database checkpoint sync for replication | Deferred | Explicitly deferred in P6 Epic E Task 1 report. |

## 2.7 Core concepts and mental model

- Durability level (**Lead S26, next train**):
  - What a write survives is the table's effective level — `strict`, `os`, `unlogged` or `memory`
    ([Durability levels](#durability-levels-lead-s26-next-train)). The WAL bullets below describe `strict` and `os`; `unlogged`
    and `memory` write no WAL frames.
- WAL frame pipeline:
  - Mutations are encoded as WAL frames and flushed before write results are considered durable (at `strict`; at `os` they are
    written to the operating system and not forced to disk).
  - **A commit is one durable write, and concurrent commits share one (**ColumnarCore S07, 0.2.0**).** A
    transaction's frames (`TxBegin`, its rows, `TxCommit`) are written back to back in one write and one flush, and
    commits that arrive while a write is on disk share the next one — group commit without a timer: a lone commit is
    written at once. The frames are unchanged byte for byte, only now contiguous, so old logs replay and replicas read
    new ones; a transaction aborted before its commit writes nothing. (Before, an insert made three write-through
    writes, an upsert four.) Measured: 200 commits to eight tables in flight together took 73 durable writes.
  - ⚠️ **Downgrades (**ColumnarMerge S07, 0.2.0**).** Keyed writes (upserts) log a new frame kind, `MergeBatch`,
    which an older server cannot replay: do not downgrade a database that has taken upserts without a clean shutdown
    first.
- WAL position as durability token:
  - Insert/update return a WAL position used by write concern tracking.
- Write concern:
  - Defines how many acknowledgements are required before operation success is returned.
- Timeout behavior:
  - Defines fail/degrade semantics when quorum is not met within timeout.
- Policy inheritance:
  - Durability can be set at db level, optionally overridden at table level, optionally overridden per write (write concern). The
    durability level has two of those layers: database and table.
- Recovery:
  - On restart, WAL is replayed from `{db}/wal/CHECKPOINT` (`redoStartPosition`); whole `wal_%09d.log` files below that horizon are skipped.
- A bulk load answered `accepted` is not durable yet (**Lead S30, next train**):
  - A bulk load's commit may ask to be answered before its commit point (`wait: "accepted"`, [Bulk Load](bulk-load.md#answered-before-the-commit-accepted-lead-s30-next-train)).
    Such a job is **not durable until its commit point**, whatever its durability level: a crash before it loses the job whole, and
    its outcome (`GET .../bulk-load/{jobId}`) says `lost`. It is opt-in per job and reported as its own state, so a `strict` load's
    acknowledgement never means less than it did: `strict` + `accepted` means "durable once committed; the answer did not wait for it".
  - Its token is a visible watermark: a read presenting it waits until the job is visible, on the primary, for materialized queries
    and on replicas. After a crash, recovery records each accepted job with no commit point lost and writes its abort to the log, so a
    replica stops holding its tokens at it.

## 2.8 How Aouda implements it

The write durability path is a composition of engine, WAL, replication, and server orchestration:

1. Write operation enters engine path (`AoudaEngine.InsertRowsAsync`, `UpdateRowsAsync`).
2. `TableAppender` writes begin/page/commit WAL tags when a resolved `WalWriter` exists — that is, when the table's effective level is `strict` or `os` (**Lead S26, next train**).
3. `WalSegmentedLog` appends frames into `wal_%09d.log`, flushes, updates `Position`, and emits `OnFrameAppended`.
4. Replication broadcaster forwards frames to subscribers (`WalStreamServer`).
5. Server DML controller receives engine result and registers pending write wait by WAL position.
6. `WriteConcernService` resolves effective concern (request -> table -> database), computes required ACKs, and awaits `PendingWriteTracker`.
7. ACKs are consumed from stream client/server protocol and complete pending waiters.
8. On restart, `WalReplayDriver` rehydrates in-memory state and starts at `{db}/wal/CHECKPOINT`, skipping whole segment files below the redo horizon.

Design characteristics:
- The durability coordination boundary is WAL position, not mutation payload.
- Write concern waiting is async and timeout-driven.
- Protocol versions support cross-database durability in a single stream connection.

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Insert at `strict` with database-default write concern

1. Client sends insert request with no explicit write concern.
2. Engine resolves table WAL policy via `ResolveWalWriter(tableEntry)`.
3. `TableAppender.SealAndWriteAsync` emits begin + append + commit frames.
4. `WalWriter` flushes frames — the whole transaction in one write, shared with commits queued behind it (**ColumnarCore S07, 0.2.0**); insert result carries `WalPosition`.
5. `TablesController.InsertRows` resolves effective write concern (table/database defaults).
6. `WriteConcernService` computes required ACK count and waits on `PendingWriteTracker`.
7. Once ACK threshold is met (or immediate local path satisfies `One`), response returns with write concern status.

### Walk-through B: Update with explicit per-write concern and timeout degradation

1. Client sends update with `writeConcern` override and strict timeout.
2. Update path writes WAL and captures commit position.
3. `WriteConcernService` uses request override over table/db defaults.
4. `PendingWriteTracker` waits for ACK quorum until timeout.
5. If timeout occurs and behavior is `Degrade` or `DegradeAndLog`, operation can return success with degraded status.
6. Metrics counters increment for waits, timeout, degradation/failure.

### Walk-through C: Crash and restart recovery

1. Process is terminated after durable and non-durable writes are interleaved.
2. On startup, storage initializes and WAL replay is invoked.
3. Replay reads segments, validates frames (CRC), trims torn tail if present, and reapplies durable frames. Reopening the log for writing also checks each frame's CRC and clears what a torn write left, so new commits are not appended behind the tear (**ColumnarCore S07 review, 0.2.0**).
4. `{db}/wal/CHECKPOINT` supplies `redoStartPosition`; segments whose end is at or below that horizon are not opened.
5. Queries after startup observe replayed state; scenario tests validate expected rows.

### Walk-through D: Replication ACK path for write concern

1. Primary appends WAL frame, and stream server broadcasts per subscribed database.
2. Secondary stream client receives frame and sends ACK.
3. Commit frames trigger immediate ACK optimization path.
4. `WalStreamServer` processes ACKs and forwards to `PendingWriteTracker`.
5. Waiting DML operation is completed when configured quorum is reached.

## 2.9 Why Aouda is different (differentiators)

- Durability policy is part of table/database metadata model (not only server-global knobs).
- Write concern is integrated into DML response semantics, not a side channel.
- Multi-database-aware WAL stream protocol supports database and table filtering.
- Checkpoint and replay logic are integrated with storage lifecycle for recovery speed.
- Health + metrics + scenario harness provide implementation-level observability and evidence.

## 2.10 Configuration and settings reference (complete surface)

### Server configuration (`appsettings.json` -> `DatabaseConfigSection`)

| Setting | Scope | Type | Default | Allowed values | Notes |
|---|---|---|---|---|---|
| `Durability` | Database | string | `strict` | `strict`, `os`, `unlogged`, `memory` | (**Lead S26, next train**) The database's durability level, read at every open. A database with a WAL cannot be reopened at `unlogged` or `memory`. `EnableWal` and `DataDurability` are refused at startup, naming `Durability`. |
| `ReplicationMode` | Database default | enum string | `Replicate` | `Replicate`, `DoNotReplicate` | Whether this database participates in WAL streaming replication. |
| `WriteConcern` | Database default | enum string | `One` | `One`, `Majority`, `All` | `One` = primary ACK only (async replication); `Majority` = quorum of replicas; `All` = every configured replica must ACK. |
| `WriteConcernTimeoutMs` | Database default | int | `5000` | `>=100` | Milliseconds to wait for replica ACKs before applying the timeout behavior. Validator enforces minimum of 100ms. |
| `OnWriteConcernTimeout` | Database default | enum string | `DegradeAndLog` | `Fail`, `Degrade`, `DegradeAndLog` | `Fail` = return an error to the caller; `Degrade` = return success without full ACKs; `DegradeAndLog` = same as `Degrade` but also writes a server warning log. |

### Engine/catalog durability model (`TableDurabilityOptions`)

| Property | Type | Nullable | Allowed values | Meaning |
|---|---|---|---|---|
| `Level` | enum | yes | `Strict`, `Unlogged`, `Memory`, `null` | (**Lead S26, next train**) This table's durability level. `null` inherits the database's. `Os` is refused (a database level only); `Strict` needs a database at `strict`; a change to or from `Memory` after creation is refused. |
| `EnableReplication` | bool | yes | `true`, `false`, `null` | Whether this table's WAL frames are included in the replication stream. `null` inherits the database default. `true` is refused when the database has no WAL or the table's level is `Unlogged` or `Memory` (no frames to stream). |
| `WriteConcern` | enum | yes | `One`, `Majority`, `All`, `null` | Write concern override for this table. `null` inherits the database default. Same semantics as the database-level setting. |
| `WriteConcernTimeoutMs` | int | yes | `>=100`, `null` | Timeout override in milliseconds. `null` inherits the database default. |
| `OnWriteConcernTimeout` | enum | yes | `Fail`, `Degrade`, `DegradeAndLog`, `null` | Timeout behavior override. `null` inherits the database default. Same semantics as the database-level setting. |

Validation and invariants:
- Table `Level = Strict` is invalid unless the database is at `strict`; `Level = Os` is always invalid (**Lead S26, next train**).
- Effective write concern configuration resolves per write, then table, then database.

### Per-write request knobs

- Protocol mutation requests include optional `WriteConcern` field:
  - `InsertMessage.WriteConcern`
  - `UpdateMessage.WriteConcern`
  - `DeleteMessage.WriteConcern`
- Protocol insert requests also include optional `InsertMessage.IdentityInsert` (BL-130): when `true`, client-supplied autoIncrement values are stored as-is and the runtime counter floor advances after a successful insert. Bulk-load uses the same idea as job-scoped `BulkLoadOptions.IdentityInsert` (BL-131). See [HTTP API](../reference/http-api.md) and [Getting Started](../getting-started/index.md).
- Server enforces parsed/validated values and applies timeout behavior policies.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (server API + current client constraints)

```csharp
using Aouda.Client;
using Aouda.Client.Databases;
using Aouda.Protocol;

var client = new AoudaClient("http://localhost:5000");

// Database-level durability knobs are available in the .NET API.
// Durability (Lead S26, next train): "strict" (default), "os", "unlogged" or "memory".
await client.Databases.CreateAsync("orders", new CreateDatabaseOptions
{
    Durability = "strict",
    ReplicationMode = "Replicate"
});

// NOTE: Current RemoteTableQuery insert/update/delete APIs do not yet expose
// a writeConcern parameter directly.
await client.Table("orders", "events").InsertAsync(new[]
{
    new Dictionary<string, object?> { ["orderId"] = 123, ["status"] = "created" }
});
```

### TypeScript example (database knobs available, write concern mutation gap)

```ts
import { AoudaClient } from "@aouda/client";

const client = new AoudaClient("http://localhost:5000");

// durability (Lead S26, next train): "strict" (default), "os", "unlogged" or "memory".
await client.databases.create("orders", {
  durability: "strict",
  replicationMode: "Replicate"
});

// Current query builder does not expose writeConcern on insert/update/delete.
await client.table("orders", "events").insert([
  { orderId: 123, status: "created" }
]);
```

### HTTP/protocol examples

```http
POST /api/databases
Content-Type: application/json

{
  "name": "orders",
  "durability": "strict",
  "replicationMode": "Replicate"
}
```

```http
POST /api/databases/orders/tables/events/rows
Content-Type: application/json

{
  "database": "orders",
  "columns": ["orderId", "status"],
  "data": [[123], ["created"]],
  "writeConcern": "Majority"
}
```

```json
{
  "rowsInserted": 1,
  "writeConcernStatus": {
    "requested": "Majority",
    "requiredAcks": 2,
    "receivedAcks": 2,
    "timedOut": false,
    "degraded": false
  }
}
```

### A) API coverage matrix

| Surface | Capability | Status | Notes |
|---|---|---|---|
| `POST /api/databases` | Set `durability`, `replicationMode` | Implemented | Wired in `DatabasesController` request model. `durability` replaces `enableWal` / `dataDurability` (**Lead S26, next train**). |
| `GET /api/databases/{db}/tables/{table}` | Report a table's effective durability | Implemented (**Lead S26, next train**) | `durability: { level, source }`. |
| Declarative schema | Set a table's durability level | Implemented (**Lead S26, next train**) | `"durability": { "level": "strict" \| "unlogged" \| "memory" }`. |
| Server config (`DatabaseConfigSection`) | Set db write concern defaults | Implemented | Parsed + validated at startup. |
| DML HTTP/protocol (`Insert/Update/Delete`) | Per-write `WriteConcern` | Implemented | Field exists in protocol messages. |
| DML results (`Insert/Update/Delete`) | `WriteConcernStatus` | Implemented server/protocol | Returned by server for concern-tracked writes. |
| Engine/catalog operations | Table durability overrides model | Implemented | `TableDurabilityOptions` + alter durability path. |
| Replication stream protocol | Per-db and per-table filtering | Implemented | v2/v3 handshake and frame/ack payloads. |

### B) Missing API matrix

| Missing surface | Where missing | Impact |
|---|---|---|
| REST create/update table durability payload | `TableMessages.cs` / table controller API contract | A table's level is set through the declarative schema; its replication and write concern overrides have no public HTTP contract yet. |
| C# client write concern args | `RemoteTableQuery.cs` | App code cannot request per-write concern via high-level SDK without bypass. |
| TypeScript client write concern args | `query-builder.ts` | Same gap for TS apps. |
| TypeScript `writeConcernStatus` result typing | `types.ts` | Clients cannot type-check status details even though server can return them. |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: Baseline durable writes with defaults

1. Create database with defaults (or omit durability knobs).
2. Insert rows via API.
3. Stop server ungracefully and restart.
4. Validate rows are present post-recovery.
5. Confirm health and metrics remain healthy.

Expected result:
- Inserted rows survive restart due to WAL + replay.

### Scenario 2: Strong replication-aware writes

1. Configure primary + secondaries with WAL streaming.
2. Use `writeConcern = Majority` for inserts/updates.
3. Observe successful writes only after required ACK threshold.
4. Simulate delayed ACKs and inspect timeout behavior.

Expected result:
- Concern waits are enforced; timeout behavior follows `Fail/Degrade/DegradeAndLog`.

### Scenario 3: Table-level durability inheritance validation

1. Create the database at `durability: "os"`.
2. Give one table `"durability": { "level": "unlogged" }` in the declarative schema; leave another without a level.
3. `GET .../tables/{table}`: the first reads `{ "level": "unlogged", "source": "table" }`, the second `{ "level": "os", "source": "database" }`.
4. Attempt invalid config: a table naming `strict` (needs a `strict` database) or `os` (a database level only).

Expected result:
- Valid overrides apply; invalid override is rejected.
- For current public APIs, this may require non-REST test harness coverage.

## 2.13 Operations and observability

Primary operational surfaces:
- Health:
  - `WalHealthCheck` evaluates queue pressure against configured thresholds.
  - `HealthController` exposes summary/details.
- Metrics:
  - `MetricsController` exposes snapshots from `MetricsCollector`.
  - Raw counters come from `Perf`.

Durability-related counters available in `Perf` include:
- WAL queue and batching:
  - `WalQueueDepth`, `WalQueueHighWater`, `WalBatchCount`, `WalBatchRecords`, `WalBatchBytes`, `WalBatchFlushMs`
- Table/database filtering:
  - `WalWritesSkippedTableDisabled`, `ReplicationFramesFilteredTable`, `ReplicationFramesFilteredDatabase`, `ReplicationFramesBroadcastedPerDb`
- Write concern behavior:
  - `WriteConcernWaitsTotal`, `WriteConcernWaitMs`, `WriteConcernTimeouts`, `WriteConcernDegradations`, `WriteConcernFailures`, `WriteConcernSuccessful`
- Replication topology health:
  - `ReplicationDatabaseSubscriptions`

Operational guidance:
- Alert on sustained WAL queue growth and high queue high-water marks.
- Track write concern timeout/degradation trends alongside replication lag.
- Validate expected per-db/per-table replication filtering counters when scoped replication is enabled.

## 2.14 Troubleshooting by symptom

- "Writes acknowledged but missing after crash"
  - Check the table's effective level (`GET .../tables/{table}` → `durability.level`). Only `strict` survives a power loss; `os`
    survives a process crash; `unlogged` loses rows not yet flushed; `memory` loses everything (**Lead S26, next train**).
  - Check replay logs and crash safety tests for torn-tail repair behavior.
- "High write latency on primary"
  - Inspect write concern level and timeout policy.
  - Review replication lag and ACK paths.
- "Unexpected write concern failures/timeouts"
  - Validate secondary count/availability and configured concern level.
  - Inspect `WriteConcernTimeoutMs` and timeout behavior policy.
- "Cannot configure per-table durability from REST"
  - A table's level goes in the declarative schema (`durability.level`). Replication and write concern overrides per table are a
    known API gap; engine/catalog support exists but public API is incomplete.
- "A database refuses to open after I set `unlogged` or `memory`"
  - It has a WAL (it was at `strict` or `os`); reopening it without one would ignore the writes the WAL holds. There is no path
    yet (BL-1145) — open it at `strict` or `os`.
- "`400 INVALID_REQUEST` naming `durability` on database create"
  - The body sends `enableWal` or `dataDurability`, or a level spelled differently from `strict` / `os` / `unlogged` / `memory`
    (lower case).

## 2.15 Verification ledger

| Item | Type | Verified | Evidence |
|---|---|---|---|
| WAL write path + flush integration | Code audit | 2026-03-31 | `WalWriter.cs`, `WalFlushQueue.cs`, `TableAppender.cs`, `AoudaEngine.cs` |
| Write concern resolution hierarchy | Code audit | 2026-03-31 | `WriteConcernService.cs`, `PendingWriteTracker.cs`, `TablesController.cs` |
| Delete WAL/write concern limitation | Code audit | 2026-03-31 | `EngineDeleteResult.cs`, `AoudaEngine.DeleteRowsAsync` path |
| Protocol support for write concern/status | Code audit | 2026-03-31 | `Aouda.Protocol/Messages.cs` |
| C#/TS client write concern gaps | Code audit | 2026-03-31 | `RemoteTableQuery.cs`, `../aouda-client-ts/src/query-builder.ts`, `../aouda-client-ts/src/types.ts` |
| Write concern unit tests | Executed | 2026-03-31 | `dotnet test tests/Aouda.Server.Tests --filter "FullyQualifiedName~WriteConcernServiceTests" --no-build` |
| Pending write tracker tests | Executed | 2026-03-31 | `dotnet test tests/Aouda.Engine.Replication.Tests --filter "FullyQualifiedName~PendingWriteTrackerTests" --no-build` |
| WAL recovery/crash tests | Executed | 2026-03-31 | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~WalIntegrationTests|FullyQualifiedName~CrashSafetyTests|FullyQualifiedName~EndToEndRestartTests" --no-build` |
| Harness durability scenarios | Task report audit | 2026-03-31 | `docs/tasks/P7/P7-Task6-DurabilityScenarios-Report.md` |

## 2.16 Test coverage matrix

| Area | Test file(s) | Coverage status | Notes |
|---|---|---|---|
| Write concern resolution and parsing | `tests/Aouda.Server.Tests/Services/WriteConcernServiceTests.cs` | Covered | Includes hierarchy and required ACK logic. |
| Pending write waiting and timeout behavior | `tests/Aouda.Engine.Replication.Tests/Streaming/PendingWriteTrackerTests.cs` | Covered | Includes quorum, timeout, degrade/fail behavior. |
| WAL integration and replay robustness | `tests/Aouda.Engine.Storage.Tests/WalIntegrationTests.cs` | Covered | Includes torn-tail repair and replay correctness. |
| Crash safety and restart behavior | `tests/Aouda.Engine.Storage.Tests/CrashSafetyTests.cs`, `EndToEndRestartTests.cs` | Covered | Restart correctness validated. |
| Durability E2E scenarios | `src/Aouda.TestHarness/Scenarios/Durability/*.cs` | Partially covered | D.1 and D.4 implemented; D.3 deferred. |
| Durability levels (database, table, inheritance, refusals) | `tests/Aouda.Engine.Api.Tests/Lead/S26DurabilityLevelTests.cs`, `tests/Aouda.Server.Tests/Lead/S26DurabilityWireTests.cs`, `tests/Aouda.Embedded.Tests/S26EmbeddedDurabilityTests.cs`, `tests/Aouda.Engine.Schema.Tests/S26RetiredDurabilityFieldTests.cs` | Covered (**Lead S26, next train**) | |
| Per-table replication / write concern via REST | N/A | Not covered (surface missing) | Model exists but API contract is incomplete. |

## 2.17 Testing gaps and proposed tests

- Add server API integration tests once per-table durability payload is exposed on create/update table endpoints.
- Add SDK tests for C# and TS mutation write concern arguments once client surface is implemented.
- Add TS client type tests for `writeConcernStatus` in mutation results.
- Add per-database checkpoint sync tests when replication checkpoint synchronization ships.

## 2.18 Known gaps and undone work

- Public REST/SDK surface for table replication and write concern controls is incomplete (a table's level is in the declarative schema).
- No path from a database level with a WAL to one without (BL-1145).
- C# and TypeScript clients do not yet expose per-write write concern arguments.
- TypeScript client types do not include write concern status in mutation results.
- Backup/restore D.3 scenario remains deferred pending API support.
- Per-database checkpoint sync in replication is deferred.

## 2.19 References

- Roadmap and backlog:
  - `docs/ROADMAP.md`
  - `docs/BACKLOG.md`
- Durability-related task reports:
  - `docs/tasks/P6/P6-EpicA-Task5-PerTableWalAndReplicationControl-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task3-WriteConcernSynchronousReplication-Report.md`
  - `docs/tasks/P7/P7-Task6-DurabilityScenarios-Report.md`
- Engine/server code:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
  - `src/Aouda.Engine.Storage/Ingest/TableAppender.cs`
  - `src/Aouda.Engine.Wal/WalSegmentedLog.cs`
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Wal/WalFlushQueue.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalReplayDriver.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalCheckpointer.cs`
  - `src/Aouda.Engine.Wal/WalCheckpointControlFile.cs`
  - `src/Aouda.Engine.Storage/Registry/DatabaseOptions.cs`
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Core/Replication/WriteConcern.cs`
  - `src/Aouda.Engine.Core/Replication/TimeoutBehavior.cs`
  - `src/Aouda.Engine.Replication/Streaming/PendingWriteTracker.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamServer.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamClient.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamProtocol.cs`
  - `src/Aouda.Engine.Diagnostics/Perf.cs`
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Health/WalHealthCheck.cs`
  - `src/Aouda.Server/Controllers/HealthController.cs`
  - `src/Aouda.Server/Controllers/MetricsController.cs`
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
- Clients:
  - `src/Aouda.Client/Databases/AoudaDatabasesApi.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `../aouda-client-ts/src/databases.ts`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/types.ts`
- Tests/harness:
  - `tests/Aouda.Server.Tests/Services/WriteConcernServiceTests.cs`
  - `tests/Aouda.Engine.Replication.Tests/Streaming/PendingWriteTrackerTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/CrashSafetyTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/EndToEndRestartTests.cs`
  - `src/Aouda.TestHarness/Scenarios/Durability/WalRecoveryScenario.cs`
  - `src/Aouda.TestHarness/Scenarios/Durability/ServerRestartScenario.cs`
  - `src/Aouda.TestHarness/Scenarios/MultiDatabase/PerTableDurabilityOverridesScenario.cs`

## 2.20 What is missing from this document? (meta completeness)

- Full API payload examples for per-table replication / write concern create/update endpoints are intentionally absent because those endpoints are not fully exposed yet.
- End-to-end SDK examples with explicit per-write concern are intentionally constrained to current shipped client APIs.
- Per-database checkpoint sync operational guidance is deferred until implementation lands.
