---
title: "Write Path Durability"
nav_order: 6
parent: "Guides"
---

# Aouda Functionality: Write Path Durability

Last updated: 2026-11-21 (Durability-1)

## Start Here

- "What does each level survive, and what does it lose?" — [Durability levels](#durability-levels-lead-s26-060) and
  [What each level loses](#what-each-level-loses)
- "How do I change a level?" — [Changing a level](#changing-a-level)
- "How do I get data back?" — [Backup and restore](backup.md)
- "What is available, and what is not?" — `2.4 Availability status`
- Defaults, configuration and troubleshooting — `2.3`, `2.10`, `2.14`

---

## Durability levels (**Lead S26, 0.6.0**)

One word, `durability`, says what a write survives. It replaces the database's `enableWal` switch, the memory-only mode
(`dataDurability: MemoryOnly`), the per-table `EnableWal` and the declarative schema's `durability.walEnabled` — all four are gone,
with no alias (see [Refusals](#refusals-of-the-retired-names)). There are four levels, strongest first:

| Level | An insert / upsert / delete | Survives a process crash | Survives a power loss |
|---|---|---|---|
| `strict` (**default**, server and embedded alike) | WAL frames written through (fsync) before the rows are visible and acknowledged | Yes | Yes |
| `os` | WAL frames written to the operating system, not forced to disk, before the rows are visible | Yes | No |
| `unlogged` | No WAL: visible at once. A clean close keeps the table whole; after any other stop it keeps its flushed rows, or is emptied if it was being changed (**Lead S26c, 0.6.0**; [below](#unlogged-after-a-crash-lead-s26c-060)) | Flushed rows, or emptied — see below | No |
| `memory` | No WAL and no data files (a memory-only table) | No | No — lost on any shutdown |

`memory` is what used to be `MemoryOnly`; `unlogged` is what used to be `EnableWal = false`.

### What each level loses

What an operator can plan with. "Acknowledged" means the write was answered successfully. A cell says **what is lost**; where it says
nothing is lost, a named test in the repository proves it.

| Level | A process crash or `kill -9` | A power loss or a kernel crash | A lost disk |
|---|---|---|---|
| `strict` | **Nothing acknowledged is lost.** | **Nothing acknowledged is lost**: the frames are on disk before the write is visible or answered. | See below: the last backup, plus the WAL archive |
| `os` | **Nothing acknowledged is lost**: the frames are in the operating system before the write is visible, and it keeps them when the process dies. | **Writes acknowledged in the last moments may be lost; what is left is a prefix of what was acknowledged** — never a later write without an earlier one, never half a statement, a bulk load kept whole or dropped whole and reported `lost`. How much is lost is the operating system's write-back, which Aouda does not bound. A `strict` table in an `os` database bounds it for itself: its acknowledgement syncs the log up to it, so every write acknowledged before it survives too. | See below |
| `unlogged` | A table that was not being changed keeps its flushed rows; rows only in memory are lost, whole statements at a time. A table that was part-way through an UPDATE, DELETE, MERGE or TRUNCATE is **emptied** ([below](#unlogged-after-a-crash-lead-s26c-060)). | Not stated beyond: the table may come back holding part of a statement. | Everything since the last backup; no point-in-time restore (there is no WAL) |
| `memory` | Everything | Everything | Nothing was ever written; nothing is in a backup |

- **A lost disk.** Restore the last backup ([Backup and restore](backup.md)). What you lose is everything since it — unless the **WAL archive**
  is on and you restore to a point in time, when the newest commits missing are at most
  `Aouda:Archive:MaxUnarchivedSeconds` (default 60 seconds) plus one archive check (one minute). A database at `unlogged` or `memory` has no WAL, so
  it has no point in time.
- **A damaged control file is refused, not read partly.** A log manifest, a pending restore's control file, a write-buffer snapshot, the
  clean-shutdown marker or another versioned file that is damaged or of another version is **refused** with a coded error that names the file
  and both versions (`FILE_FORMAT_REFUSED`, `WAL_MANIFEST_REFUSED`; a start exits 78) — no missing field is defaulted.
- **A torn tail is trimmed; a damaged WAL frame anywhere else refuses the open**. A write cut off by a crash or
  a power loss (the torn tail of the log's last write) is trimmed and everything before it is kept, as before. Any other frame that fails
  its check — in a segment the log has already closed, or in the segment being written with frames written after it — is damage, not a
  crash: the database **does not open** and nothing in the log is changed. The refusal is
  `FILE_FORMAT_REFUSED: kind=wal-segment found=<checksum mismatch | length mismatch | truncated> …` and names the segment file, its
  sequence number and the frame's position. A segment the log manifest names but that is missing (`found=missing`), or whose header
  does not match the manifest, is refused the same way. A server keeps that database quarantined with the refusal as its message and
  opens the others. Two ways on: restore the database from a backup, or open it past the damaged frame with
  `POST /api/databases/{db}/unquarantine?salvagePastCorruptWal=true` (or `aouda databases unquarantine --salvage-corrupt-wal`), which
  skips the frame and applies the frames after it — the writes of the skipped frame are lost, and the open logs it. The salvaged open
  closes the damaged segment at its next write; until a checkpoint moves the replay's start past the damaged frame (the rows after it
  written out of the write buffer), a later open — after a crash, or after a clean close that wrote nothing out — can refuse the
  database again: salvage it again. Limits of the check: a damaged frame followed by a whole 512-byte block of zeros reads as a torn
  tail and is trimmed, as before, with a warning in the log; damage in the very last frame written, or a length prefix damaged in more
  than one bit so that the frame seems to run past the last written byte, is trimmed as a torn tail too.
- **The `os` power-loss statement is proved against a model of power loss**, not on a real disk. On a real disk the kernel can write some files
  back out of order; one such case (an `os` mark or a load file reaching the disk ahead of the log) is an open card (BL-1705): it can keep
  an UPDATE's delete of the old row and lose the new row — half a statement, which the model does not show. If you cannot lose
  an acknowledged write, use `strict`.
- **Not stated.** No number of seconds or bytes is given for `os` after a power loss, and none for a lost disk without the archive: there is no bound to quote.

### The database's level

A database's level is set where the database is created, and is read again at **every open**:

| Surface | How |
|---|---|
| HTTP | `POST /api/databases` body field `durability` (omitted → `strict`). See [HTTP API](../reference/http-api.md#post-apidatabases). |
| Server config | `databases.<db>.durability` in `aouda.json` (**BL-1463, 0.16.0**; it was `Aouda:Databases:<db>:Durability`, now refused) |
| Embedded | `AoudaEmbeddedOptions.Durability` (string, default `"strict"`) or config `Aouda:Durability` |
| CLI | `aouda databases create --durability <level>` |
| C# SDK | `CreateDatabaseOptions.Durability` (`client.Databases.CreateAsync(name, options)`) |
| TypeScript SDK | `client.databases.create(name, { durability })` (`DurabilityLevel` type) |

A database at `strict` or `os` has a WAL; one at `unlogged` or `memory` has none. `os` is a whole-database choice: the database
has one WAL file, and it is written through or not as a whole.

A database moves from a level with a WAL to one without at its next open, which retires the WAL: see [Changing a level](#changing-a-level).

`GET /api/databases/{db}` reports the level as `options.durability` (a string; the boolean `options.enableWal` is gone).

### A table's level

A table may name its own level, or inherit the database's:

- Declarative schema: `"durability": { "level": "unlogged" }` on the table ([Schema](schema.md)). Engine API:
  `TableDurabilityOptions.Level`. Omitted → the table inherits the database's level.
- A table may name `strict`, `unlogged` or `memory`. **`os` is a database level only** — a table naming it is refused.
- **`strict` on a table is allowed in a database at `strict` or `os`** and refused in an `unlogged` or `memory` database. In an
  `os` database a `strict` acknowledgement is an `fsync` of the WAL up to that write's frame, shared by every write that commits at the same moment, so a `strict`
  table keeps every acknowledged write through a power loss — and so does every `os` write acknowledged before it. It costs one `fsync` per commit group. An
  `os` database syncs each 64 MB WAL segment once when it rotates away from it, and every segment once at open.
- **A table's storage is fixed when it is made.** Changing a table to or from `memory` after creation is refused; `strict` ↔
  `unlogged` may be altered.
- A table created while its database is at `memory` is a memory table — it records `memory`. A table that inherits from a database
  later reopened at `memory` reads as `unlogged`.

`GET /api/databases/{db}/tables/{table}` reports `durability: { "level": "...", "source": "table" | "database" }`: the level the
table's writes actually get, and where it came from. It is the effective level — a table that names `strict` in an `os` database reads
`strict`, and a table that inherits an `os` database's level reads `os`. `policy.residency.dataDurability` is gone.

### `unlogged` after a crash (**Lead S26c, 0.6.0**)

An `unlogged` table — or every table of an `unlogged` database — writes no WAL, and after a crash its segments could hold part
of one statement: an UPDATE's deletions reach the segments when it commits but its new row versions only
at the next flush, so a crash could keep the deletes and lose the rows; a large INSERT can be cut by a flush; a DELETE's marks are
written segment by segment.

So the server keeps a mark on disk while an `unlogged` table may hold part of a statement: from the start of an UPDATE, DELETE,
MERGE or TRUNCATE until its deletion marks are written and its new rows flushed, and from a flush that leaves rows in memory until
a flush empties it. **An open that does not follow a clean close** — after a crash, a kill, a close whose snapshot failed, or a
restore — **empties every `unlogged` table that carries the mark**, as PostgreSQL truncates unlogged tables after a crash, and logs
a warning naming each table and its row count. A table without the mark keeps its flushed rows; rows that were only in memory are
lost, whole statements at a time. A clean close snapshots the table's in-memory rows, and the open after it keeps the table whole.
Keep only data you can load again in an `unlogged` table. (Earlier versions of this page said flushed `unlogged` rows survive a
crash. They could survive as part of a statement — an UPDATE's deletions without its new rows — which is why a table that was
being changed is now emptied instead.) A `memory` table is empty after any restart, as it always was. The rule holds whatever
level the table reads at the open (an `unlogged` database reopened at `strict` after a crash empties its flagged tables), and **a branch's `unlogged` tables
follow it too** — a branch is at its parent's level.

The mark is not forced to disk, so the rule holds for a process crash or a kill, **not for a power loss**: after a power loss an
`unlogged` table may come back holding part of a statement. And the rule is about the table, not about who wrote to it: a bulk load
into an `unlogged` table is `strict`, but if the table carries the mark at a crash — another statement was changing it — the open
empties it, the load's rows with it, although the load answered committed.

### Changing a level

A database's level is read at **every open**. A declared database changes level at its restart.

- **From `strict` or `os` to `unlogged` or `memory`.** The open at the new level replays the WAL it finds, flushes every row into segments, closes
  cleanly and **retires the WAL**; nothing the old level acknowledged is lost, and a later `strict` open does not replay it a second time. A
  retirement cut by a crash is finished by the next open, at any level. A branch reopened this way retires its own WAL the same way.
- **What a retirement ends.** The database's **point-in-time window** ends at the change: a backup taken before it restores exactly, but not to a time after it. A database
  that archives its WAL archives every written segment before the WAL is deleted, so a time before the change stays reachable. Replication history ends too (a replica sees a new epoch), and the database's materialized queries are rebuilt once.
- **It is refused** (`WAL_RETIREMENT_REFUSED`, the WAL kept; the next open tries again) when the flush cannot finish in time (5 minutes), when an
  `os` load has not been promoted, when the close after the flush still owes the WAL something (a bulk load not catalogued, an edge or vector
  buffer), when the WAL archive cannot take every frame (an unreachable destination), or when the database requires every WAL segment
  archived before deletion (`RequireArchiveBeforeDelete`).
- **A table's level.** `ALTER` between `unlogged` and a WAL level waits for the table's writes to settle (up to 60 seconds), flushes it, then changes; if it
  cannot, the change is refused as a retryable write conflict naming the table, with the table unchanged. In a
  schema apply that change is reported `Failed` in the apply's result (the request itself answers 200); retry the apply. A table never moves to or from `memory`.

### Replication

**Replication is not supported in any release of Aouda yet** ([Replication](replication.md)). A table at `unlogged` or `memory` writes no WAL
frames, so a replica would receive none of its inserts; asking for per-table replication (`EnableReplication = true`) on such a table is
refused. The level is the primary's promise to the writer: nothing here says a replica keeps what the primary does.

### Bulk loads

A bulk load writes segment files — a `strict` load in a database with a WAL also logs its commit in WAL frames, an `os` load does not — and
has a level of its own: `strict` or `os` (**Lead S26c, 0.6.0**), `:begin`'s `options.durability`. Omitted, it takes the database's level for
a load — `os` in a database at `os` (`strict` when every table of the job names `strict`, below), `strict` everywhere else; a
table's own level does not change it, so an `unlogged` table still gets a `strict` load.

| Load level | Before the job is visible | Survives a process crash | Survives a power loss |
|---|---|---|---|
| `strict` (default; what every load did before) | Every segment file, its directory and the job's commit record fsynced | Yes | Yes |
| `os` | Files written and renamed, the commit record written, none of it fsynced | Yes | Kept whole, or dropped whole and reported `lost` — never half |

Until the server has synced an `os` load in the background, every durable write on its database waits for it — and so does a job
that follows it (`afterJobId`) at its commit, and the creation of a branch (**Lead group 6 review, 0.6.0**): neither may outlive
a power loss that drops the load. **If that background sync fails**, every later durable write on the database is refused, naming the
job, until the server is restarted; the restart verifies the job and keeps it whole or reports it lost. `strict` is **allowed** in a database at `os` — a `strict` load there syncs the WAL up to its position before its commit record, so what a power loss leaves
is a prefix of what was acknowledged. An omitted level in an `os` database is `strict` when every table of the job names
`strict`, else `os`. `os` is refused for a multi-table job, a table with vector columns, or an edge or vector table: the refusal says to name
`durability: "strict"`. If an `os` load's background promotion fails, later loads are refused naming the job until a restart. A bulk load into a `memory` table is refused, naming the level — a load writes segment files, which a memory table never has. See
[Bulk Load — a load's durability](bulk-load.md#a-loads-durability-strict-or-os-lead-s26c-060).

### Refusals of the retired names

There is no alias and no shim; each old name is refused where it would have been read, and the error names its replacement:

| Old | Where | Now |
|---|---|---|
| `enableWal`, `dataDurability` | `POST /api/databases` body | **400** `INVALID_REQUEST` naming `durability` |
| An unknown level — including `"Strict"` (capitalised), `"MemoryOnly"`, `"everysec"` | `POST /api/databases` `durability` | **400** naming the four levels |
| `EnableWal`, `DataDurability` | `Aouda:Databases:<db>` server config | Startup is refused (`SETTING_REMOVED`), naming `databases.<db>.durability` of `aouda.json` (**BL-1463, 0.16.0**; before, startup validation failed naming `Durability`) |
| `EnableWal` (in code, or config `Aouda:EnableWal`) | Embedded | The open throws, naming `Durability` |
| `durability.walEnabled` on a table | Declarative schema | Validation error naming `durability.level` |
| `durability.walEnabled` in `settings` | Declarative schema | Validation error: the database's level is set where the database is created (`settings.durability` now carries only `replicationFactor`) |
| `--enable-wal` | CLI `aouda databases create` | Error naming `--durability` |

### Persisted formats

A data directory, a backup or a WAL file written by another format is **refused** at open, naming the file and both the version found and the
version expected; there is no migration and no fallback reader. The current numbers and the exact lines a server prints are in
[Upgrading](upgrading.md); to keep data across a format change, [`aouda dump` and `aouda load`](dump-load.md).

---

## 2.1 Why this functionality exists

Aouda durability makes write outcomes explicit instead of implicit.

- User problem solved:
  - "My process died; do I lose acknowledged writes?"
  - "Can I trade latency for stronger durability only when needed?"
- Core outcomes:
  - Local crash durability with write-ahead logging (WAL).
  - Replay-driven recovery after kill/restart.
  - Write concern (`One`, `Majority`, `All`) with timeout policy. Only `One` is meaningful on a single node: replication is not supported, so
    there is no replica to wait for.
  - Table-level and database-level durability policy layering — one level per database, optionally narrowed per table
    (**Lead S26, 0.6.0**; [Durability levels](#durability-levels-lead-s26-060)).
- Non-goals (current implementation):
  - Full API surface for per-table write concern and replication controls via REST/SDKs.

## 2.2 Discovery and navigation map

### Question -> section map

- "What does each durability level survive?" -> [Durability levels](#durability-levels-lead-s26-060)
- "What does each level lose?" -> [What each level loses](#what-each-level-loses)
- "What are defaults?" -> `2.3`
- "What is available today?" -> `2.4`
- "How does the write path work end-to-end?" -> `2.8`, `2.8.1`
- "How do I configure server/db/table/per-write durability?" -> `2.10`
- "Which API/client surfaces are wired or missing?" -> `2.11`
- "How do I run this operationally?" -> `2.12`, `2.13`, `2.14`

### Role-based map

- Platform engineer:
  - `2.8`, `2.8.1`, `2.10`, `2.13`
- App developer:
  - `2.3`, `2.10`, `2.11`, `2.12`
- SRE/operations:
  - `2.13`, `2.14`
- Reviewer/auditor:
  - `2.4`, `2.18`

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

- Durability level (**Lead S26, 0.6.0**):
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
- Guardrails (**Lead S26, 0.6.0**):
  - A table naming `os` is refused (a database level only); a table naming `strict` is refused in an `unlogged` or `memory` database and allowed in an `os` one.
  - A change to or from `memory` after a table is created is refused.
  - A database with a WAL reopened at `unlogged` or `memory` retires its WAL at that open ([Changing a level](#changing-a-level)).

## 2.4 Availability status (implementation honesty)

### Available now

- Local durability via WAL append path for insert, update, and delete.
- WAL replay and crash-safe recovery paths, including torn-tail repair.
- Durable WAL checkpoints (`{db}/wal/CHECKPOINT`) that skip whole segment files below the redo horizon.
- Write concern wait pipeline with quorum + timeout policies. (Replication is not supported, so there is no quorum beyond the node itself.)
- Per-database durability level (`strict` / `os` / `unlogged` / `memory`) via server config, database API, embedded options, CLI
  and both SDKs (**Lead S26, 0.6.0**).
- Per-table durability level (`strict` / `unlogged` / `memory`) via the declarative schema and the engine/catalog model, with
  inheritance and validation; reported by `GET .../tables/{table}` as `durability` (**Lead S26, 0.6.0**).
- A bulk load's own level (`strict` / `os`) via `:begin`'s `options.durability`, both SDKs and the CLI (**Lead S26c, 0.6.0**).
- `strict` tables and loads inside an `os` database, and a level change from a WAL level to `unlogged` / `memory` ([Changing a level](#changing-a-level)).
- An `unlogged` table that was being changed emptied by an open that does not follow a clean close (**Lead S26c, 0.6.0**).
- Health and metrics endpoints that expose key operational durability indicators.

### Planned / proposed

- REST and SDK exposure for the remaining per-table durability controls (`EnableReplication`, `WriteConcern`, `WriteConcernTimeoutMs`, `OnWriteConcernTimeout`).
- Client SDK mutation APIs exposing `WriteConcern` and result `WriteConcernStatus`.

### Not supported

- Replication ([Replication](replication.md)).

## 2.7 Core concepts and mental model

- Durability level (**Lead S26, 0.6.0**):
  - What a write survives is the table's effective level — `strict`, `os`, `unlogged` or `memory`
    ([Durability levels](#durability-levels-lead-s26-060)). The WAL bullets below describe `strict` and `os`; `unlogged`
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
- A bulk load answered `accepted` is not durable yet (**Lead S30, 0.6.0**):
  - A bulk load's commit may ask to be answered before its commit point (`wait: "accepted"`, [Bulk Load](bulk-load.md#answered-before-the-commit-accepted-lead-s30-060)).
    Such a job is **not durable until its commit point**, whatever its durability level: a crash before it loses the job whole, and
    its outcome (`GET .../bulk-load/{jobId}`) says `lost`. It is opt-in per job and reported as its own state, so a `strict` load's
    acknowledgement never means less than it did: `strict` + `accepted` means "durable once committed; the answer did not wait for it".
  - Its token is a visible watermark: a read presenting it waits until the job is visible, on the primary, for materialized queries
    and on replicas. After a crash, recovery records each accepted job with no commit point lost and writes its abort to the log, so a
    replica stops holding its tokens at it.

## 2.8 How Aouda implements it

The write durability path is a composition of engine, WAL, replication, and server orchestration:

1. Write operation enters engine path (`AoudaEngine.InsertRowsAsync`, `UpdateRowsAsync`).
2. `TableAppender` writes begin/page/commit WAL tags when a resolved `WalWriter` exists — that is, when the table's effective level is `strict` or `os` (**Lead S26, 0.6.0**).
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
3. Replay reads segments, validates frames (CRC), trims torn tail if present, and reapplies durable frames. Reopening the log for writing also checks each frame's CRC and clears what a torn write left, so new commits are not appended behind the tear (**ColumnarCore S07 review, 0.2.0**). A frame that fails its check and is not the torn tail of the last write refuses the open instead (`FILE_FORMAT_REFUSED`, kind `wal-segment`).
4. `{db}/wal/CHECKPOINT` supplies `redoStartPosition`; segments whose end is at or below that horizon are not opened.
5. Queries after startup observe replayed state; scenario tests validate expected rows.

### Walk-through D: Replication ACK path for write concern

_Replication is not supported in any release yet; this describes the code as it stands._

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
| `Durability` | Database | string | `strict` | `strict`, `os`, `unlogged`, `memory` | (**Lead S26, 0.6.0**) The database's durability level, read at every open. A database with a WAL reopened at `unlogged` or `memory` retires its WAL at that open ([Changing a level](#changing-a-level)). `EnableWal` and `DataDurability` are refused at startup, naming `Durability`. |
| `ReplicationMode` | Database default | enum string | `Replicate` | `Replicate`, `DoNotReplicate` | Whether this database participates in WAL streaming replication. |
| `WriteConcern` | Database default | enum string | `One` | `One`, `Majority`, `All` | `One` = primary ACK only (async replication); `Majority` = quorum of replicas; `All` = every configured replica must ACK. |
| `WriteConcernTimeoutMs` | Database default | int | `5000` | `>=100` | Milliseconds to wait for replica ACKs before applying the timeout behavior. Validator enforces minimum of 100ms. |
| `OnWriteConcernTimeout` | Database default | enum string | `DegradeAndLog` | `Fail`, `Degrade`, `DegradeAndLog` | `Fail` = return an error to the caller; `Degrade` = return success without full ACKs; `DegradeAndLog` = same as `Degrade` but also writes a server warning log. |

### Engine/catalog durability model (`TableDurabilityOptions`)

| Property | Type | Nullable | Allowed values | Meaning |
|---|---|---|---|---|
| `Level` | enum | yes | `Strict`, `Unlogged`, `Memory`, `null` | (**Lead S26, 0.6.0**) This table's durability level. `null` inherits the database's. `Os` is refused (a database level only); `Strict` needs a database with a WAL (`strict` or `os`); a change to or from `Memory` after creation is refused. |
| `EnableReplication` | bool | yes | `true`, `false`, `null` | Whether this table's WAL frames are included in the replication stream. `null` inherits the database default. `true` is refused when the database has no WAL or the table's level is `Unlogged` or `Memory` (no frames to stream). |
| `WriteConcern` | enum | yes | `One`, `Majority`, `All`, `null` | Write concern override for this table. `null` inherits the database default. Same semantics as the database-level setting. |
| `WriteConcernTimeoutMs` | int | yes | `>=100`, `null` | Timeout override in milliseconds. `null` inherits the database default. |
| `OnWriteConcernTimeout` | enum | yes | `Fail`, `Degrade`, `DegradeAndLog`, `null` | Timeout behavior override. `null` inherits the database default. Same semantics as the database-level setting. |

Validation and invariants:
- Table `Level = Strict` is invalid unless the database has a WAL (`strict` or `os`); `Level = Os` is always invalid (**Lead S26, 0.6.0**).
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
// Durability (Lead S26, 0.6.0): "strict" (default), "os", "unlogged" or "memory".
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

// durability (Lead S26, 0.6.0): "strict" (default), "os", "unlogged" or "memory".
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
| `POST /api/databases` | Set `durability`, `replicationMode` | Implemented | Wired in `DatabasesController` request model. `durability` replaces `enableWal` / `dataDurability` (**Lead S26, 0.6.0**). |
| `GET /api/databases/{db}/tables/{table}` | Report a table's effective durability | Implemented (**Lead S26, 0.6.0**) | `durability: { level, source }`. |
| Declarative schema | Set a table's durability level | Implemented (**Lead S26, 0.6.0**) | `"durability": { "level": "strict" \| "unlogged" \| "memory" }`. |
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

_Replication is not supported in any release yet: on a single node only `One` can be satisfied. This scenario shows the shape of the request._

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
4. Attempt invalid config: a table naming `strict` (needs a database with a WAL — `strict` or `os`) or `os` (a database level only).

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
  - Check the table's effective level (`GET .../tables/{table}` → `durability.level`) against [What each level loses](#what-each-level-loses):
    `strict` loses nothing acknowledged; `os` loses nothing to a process crash and may lose its last acknowledged writes to a power loss;
    `unlogged` keeps its flushed rows after a crash, or is emptied if it was being changed; `memory` loses everything.
  - Check the server log of the open for a torn-tail repair, a refusal (`FILE_FORMAT_REFUSED`, `WAL_MANIFEST_REFUSED`) or a retirement.
- "A database is quarantined with `FILE_FORMAT_REFUSED: kind=wal-segment`"
  - A frame of its WAL is damaged where no crash can leave one (the message names the segment, the sequence number and the position).
    Restore the database from a backup, or accept the loss of that frame's writes with
    `POST /api/databases/{db}/unquarantine?salvagePastCorruptWal=true`. Check the disk: a damaged log file is usually a failing device.
- "An `unlogged` table is empty after a restart" (**Lead S26c, 0.6.0**)
  - The open did not follow a clean close (a crash, a kill, a close whose snapshot failed, a restore) and the table was being
    changed at the time, so the server emptied it and logged a warning naming it and its row count. That is the level's contract
    ([`unlogged` after a crash](#unlogged-after-a-crash-lead-s26c-060)): load the table again from its source.
- "`GET .../bulk-load/{jobId}` answers `lost` for an `os` load" (**Lead S26c, 0.6.0**)
  - The server lost power before it had synced the job; at the next open its files did not match its commit record, so it was
    dropped whole. Load it again with the same idempotency key.
- "High write latency on primary"
  - Inspect write concern level and timeout policy.
  - Review replication lag and ACK paths.
- "Unexpected write concern failures/timeouts"
  - Validate secondary count/availability and configured concern level.
  - Inspect `WriteConcernTimeoutMs` and timeout behavior policy.
- "Cannot configure per-table durability from REST"
  - A table's level goes in the declarative schema (`durability.level`). Replication and write concern overrides per table are a
    known API gap; engine/catalog support exists but public API is incomplete.
- "A database refused to open after I set `unlogged` or `memory`" (`WAL_RETIREMENT_REFUSED`)
  - The open retires the WAL it finds, and refused: its flush could not finish in 5 minutes, an `os` load is not promoted yet, or the database
    requires its WAL archived before deletion. The WAL is kept; fix the cause and open again, or open it at `strict` or `os` ([Changing a level](#changing-a-level)).
- "`400 INVALID_REQUEST` naming `durability` on database create"
  - The body sends `enableWal` or `dataDurability`, or a level spelled differently from `strict` / `os` / `unlogged` / `memory`
    (lower case).

## 2.18 Known gaps and undone work

- Public REST/SDK surface for table replication and write concern controls is incomplete (a table's level is in the declarative schema).
- C# and TypeScript clients do not yet expose per-write write concern arguments.
- TypeScript client types do not include write concern status in mutation results.
- Replication is not supported.

## 2.19 References

- Roadmap and backlog:
  - [Backup and restore](backup.md), [Replication](replication.md), [Upgrading](upgrading.md)
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
