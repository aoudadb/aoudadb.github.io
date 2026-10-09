---
title: "Storage and Persistence"
nav_order: 13
parent: "Guides"
---

# Aouda Functionality: Storage and Persistence

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-06-23

Coverage phases: P3, P4, P6, P11, P30
Primary task folders: `docs/tasks/P3/`, `docs/tasks/P4/`, `docs/tasks/P6/`, `docs/tasks/P11/`, `docs/tasks/P30/`
Primary ADRs: `docs/decisions/0001-column-per-file.md`, `docs/decisions/0002-json-catalog-persistence.md`, `docs/decisions/0003-write-ahead-log.md`, `docs/decisions/0005-persistence-policies.md`, `docs/decisions/0016-wal-lifecycle-management.md`, `docs/decisions/0035-temperature-aware-replication-and-backup.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How does Aouda persist data and recover after restart?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.7 Core concepts and mental model`
- `2.8 How Aouda implements it`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference`
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Aouda is in-memory-first at execution time, but production use requires durable state, restart recovery, and retention boundaries that are operationally predictable.

- User problem solved:
  - Keep table/catalog state durable across process restart and node failover.
  - Replay committed changes safely after crash without full rebuild.
  - Bound WAL growth while preserving replication and recovery safety.
- Operational outcomes:
  - Deterministic on-disk layout for databases, tables, WAL, and metadata.
  - Restart semantics that combine catalog + segment files + WAL replay.
  - Backup/archive building blocks for long-term restore and PITR.
- Scope boundaries:
  - This doc covers storage layout, catalog persistence, WAL durability/replay/lifecycle, and backup/archive/restore implementation state.
  - It does not duplicate deep hot/cold policy behavior (covered in `Functionality-HotCold-And-Memory.md`) or full cluster behavior details.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| Where files live on disk | `2.7 Core concepts and mental model` + `2.8 How Aouda implements it` |
| Default persistence behavior | `2.3 Defaults and zero-config behavior` |
| What is shipped vs planned vs reserved | `2.4 Availability status` |
| Which phase delivered what | `2.5 Phase coverage matrix` |
| End-to-end capability truth | `2.6 Capability coverage matrix` |
| Full config settings and defaults | `2.10 Configuration and settings reference` |
| HTTP/.NET/TypeScript coverage | `2.11 API and CLI coverage reference` |
| Ops and incident response signals | `2.13 Operations and observability` |
| Known missing surfaces | `2.11` (missing API matrix) + `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.3`, `2.11`, `2.12` |
| Operator/SRE | `2.10`, `2.13`, `2.14` |
| SDK maintainer | `2.11`, `2.17`, `2.18` |
| Engine contributor | `2.5`, `2.8`, `2.16`, `2.19` |

### Source map

- Task/report evidence:
  - `docs/tasks/P3/P3-Task7-HotSegmentPersistence-Report.md`
  - `docs/tasks/P3/P3-BugFix-HotSegmentPersistence-AllDataTypes-Report.md`
  - `docs/tasks/P4/P4-EpicD-Task1-BackupManifest-Report.md`
  - `docs/tasks/P4/P4-EpicD-Task3-IncrementalBackupEngine-Report.md`
  - `docs/tasks/P4/P4-EpicD-Task5-BackupLifecycleManagement-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task2-WalArchiveWorker-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task5-BackupIntegration-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task4-TableNameBasedDirectoryStorage-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task5-PerTableWalAndReplicationControl-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`
- Core code:
  - `src/Aouda.Engine.Storage/StorageConstants.cs`
  - `src/Aouda.Engine.Storage/Layout/ServerDirectoryLayout.cs`
  - `src/Aouda.Engine.Storage/Layout/DatabaseDirectoryLayout.cs`
  - `src/Aouda.Engine.Catalog/CatalogStore.cs`
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Storage/Bootstrap/StorageBootstrap.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalReplayDriver.cs`
  - `src/Aouda.Engine.Storage/Backup/BackupEngine.cs`
  - `src/Aouda.Engine.Storage/Backup/RestoreEngine.cs`
  - `src/Aouda.Engine.Storage/Backup/BackupLifecycleManager.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/Archive/WalArchiveWorker.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptions.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigSection.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/ReplicationController.cs`
  - `src/Aouda.Server/Controllers/MetricsController.cs`
- TypeScript client code (cross-repo):
  - `../aouda-client-ts/src/databases.ts`
  - `../aouda-client-ts/src/admin/server.ts`
  - `../aouda-client-ts/src/types.ts`
- Tests:
  - `tests/Aouda.Engine.Catalog.Tests/CatalogPersistenceTests.cs`
  - `tests/Aouda.Engine.Catalog.Tests/CatalogWalTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/EndToEndRestartTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalReplayDriverTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalCheckpointIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalFastForwardRestartTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalRetentionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/BackupEngineIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/RestoreIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/LifecycleIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/PitrFromArchivedWalTests.cs`
  - `tests/Aouda.Server.Tests/ConfigurationIntegrationTests.cs`
  - `../aouda-client-ts/tests/databases.test.ts`

## 2.3 Defaults and zero-config behavior

If you run server defaults and do not set per-database overrides:

- Data path is `./data`.
- Server uses `Databases/{db}` database roots and `tables/{tableName}` table roots.
- WAL is enabled for newly created databases by default.
- Database replication mode defaults to `Replicate`.
- Database default table temperature is `Auto`.
- Write concern defaults to `One` with timeout `5000 ms`.
- Archive mode is disabled unless explicitly configured.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `Aouda:DataPath` | `./data` | Persistent root for all server databases |
| `CreateDatabaseRequest.enableWal` | `true` | New DB writes are WAL-backed by default |
| `DatabaseConfigSection.EnableWal` | `true` | Config-defined DBs default to WAL on |
| `DatabaseConfigSection.ReplicationMode` | `Replicate` | DB participates in replication unless overridden |
| `DatabaseConfigSection.DefaultTemperature` | `Auto` | New tables default to temperature automation |
| `DatabaseConfigSection.WriteConcern` | `One` | Primary ACK semantics by default |
| `DatabaseConfigSection.WriteConcernTimeoutMs` | `5000` | 5s timeout for stronger concerns |
| `DatabaseConfigSection.OnWriteConcernTimeout` | `DegradeAndLog` | Timeout degrades instead of hard fail by default |
| `ArchiveConfig.Enabled` | `false` | No standalone WAL archive worker by default |
| `ArchiveConfig.WalRetentionDays` | `7` | 7-day archive retention when enabled (not the local PITR window) |
| `ArchiveConfig.RequireArchiveBeforeDelete` | `false` | Local WAL may prune without waiting for archive unless set |

## 2.4 Availability status (implementation honesty)

### Available now

- Durable directory model:
  - Server root: `Server/` metadata + `Databases/` directories.
  - Per-database layout: `catalog/`, `wal/`, `tables/`, `materialized/`.
  - Table directories are table-name based (`tables/{tableName}/...`).
- Catalog durability:
  - `CatalogStore` JSON snapshot persistence (`catalog/catalog.json`) with atomic temp-write + move.
  - Additional catalog WAL/checkpoint classes (`FileCatalog`, `CatalogWal`, `CatalogCheckpoint`) are implemented in catalog layer.
- WAL durability and replay:
  - Append-only WAL frame writes (`WalWriter`), replay on restart (`WalReplayDriver`, `WalReplayer` paths), segment rolling and retention components.
  - Per-table durability override model (`TableDurabilityOptions`) is implemented.
- Restart semantics:
  - Storage bootstrap can load persisted segment state and replay WAL.
  - Hot segment persistence/reload and fallback behavior are implemented (P3 Task 7 + fix).
- WAL lifecycle safety:
  - Slot-based retention boundary model (system/replication/backup/archive slots) implemented.
    All four slot types are live when the corresponding consumer exists (archive slot when
    `Archive.Enabled` + destination).
  - Retention worker infrastructure implemented and running. **Archive worker runs** when archive
    is configured — see `2.8.1` Walk-through D and
    [Backup and restore §2.4](backup.md#24-availability-status).
- Backup/restore engines:
  - `BackupEngine`, `RestoreEngine`, and `BackupLifecycleManager` implemented and tested, for **exact** restore and **PITR**.
  - **Point-in-time recovery (PITR) is implemented.** Replay is the crash-recovery path, at
    transaction-commit granularity, reachable over HTTP and both SDKs. The local window is a
    write-volume bound (`MaxSlotWalKeepBytes`), not a duration. See
    [Backup and restore §2.4](backup.md#24-availability-status).

### Planned / proposed

- Broader cloud destination operationalization:
  - Archive destination abstraction exists; Azure/GCS still throw `NotSupportedException`.
- Per-database checkpoint synchronization in replication:
  - Current replication hosted service explicitly documents first-database checkpoint limitation.

### Reserved / not yet wired

- Some persistence-policy ADR concepts (`DiskOnly`, full policy matrix) are not exposed as explicit end-user policy enums in current HTTP/TS surfaces.

> **Note (P30):** `MemoryOnly` durability mode is now fully enforced end-to-end (P30 S2). `MemoryOnly` tables write nothing to disk — no `.hot`, `.col`, `.hra`, or WAL records. This is no longer a "reserved" surface. See `guides/hot-cold.md §2.4`.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P3 | `P3-Task7-HotSegmentPersistence-Report.md`, `P3-BugFix-HotSegmentPersistence-AllDataTypes-Report.md` | Hot segment file persistence, restart survival semantics, integrity checks, all core data types for hot persistence | Further file-format enhancements (for example mmap/compression tiers) out of scope | No dedicated open backlog item from these reports |
| P4 | `P4-EpicD-Task1/3/5-*Report.md`, `P4-EpicI-Task2/5-*Report.md` | Backup manifest/hash infra, incremental backup engine, lifecycle retention/GC, slot integration; WAL archive worker class | Server HTTP backup/restore later shipped in P16; worker started in BL-186 S05 | BL-186 (closed) |
| P6 | `P6-EpicA-Task4-*Report.md`, `P6-EpicA-Task5-*Report.md`, `P6-EpicE-Task1-*Report.md` | Table-name directory storage, per-table WAL/replication controls, per-database replication WAL multiplexing | Per-database checkpoint sync still deferred | Not mapped to explicit BL item in `docs/BACKLOG.md` |
| P11 | `P11-Fix-WalRoundtripTests-UniqueTempPath-Report.md` | WAL test reliability hardening in persistence test paths | No new feature surface; test stability work only | N/A |
| P30 | `MemTiering-S12-Backup-HRA-Coverage.md` | Backup now includes HRA snapshot (`.hra`) and mutable keyed tier (`.mkt`) files — **Gap C closed**. Both added to backup manifest and restore path. Full row coverage for all durability modes. | Streaming HRA snapshot (BL-105) deferred | ADR 0035 |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Stable server/database/table storage layout | Yes | No | No | `StorageConstants.cs`, layout classes, P6 Task4 report | Table-name path model is active |
| Catalog snapshot durability (`catalog.json`) | Yes | No | No | `CatalogStore.cs`, catalog tests | Atomic temp-write + move |
| WAL append durability and replay | Yes | No | No | `WalWriter.cs`, replay/bootstrap paths, restart tests | Core durability path shipped |
| Per-table WAL enable/disable overrides | Yes | No | No | P6 Task5 report, `AoudaEngine` durability resolution | Table override cannot enable WAL if DB WAL off |
| Per-database WAL replication framing | Yes | No | No | P6 EpicE Task1 report, replication streaming code | v2 frame model with DB tagging |
| Hot segment file persistence and restart hot-load | Yes | No | No | P3 Task7 report + bugfix report, hot persistence tests | Type-complete persistence added |
| WAL slot lifecycle management (`system/replication/backup/archive`) | Yes | No | No | ADR 0016 + P4 Epic I + BL-186 S05 | Retention boundaries consumer-aware. Archive slot is created when archiving is configured |
| Backup manifest + incremental dedup engine | Yes | No | No | P4 EpicD Task1/3 reports, backup engine tests | Engine-level implementation complete |
| Restore engine, exact restore | Yes | No | No | `RestoreEngine.cs`, restore tests; BL-186 S03 | Re-bases WAL root and catalog directory |
| PITR replay (local WAL + archive) | Yes | No | No | BL-186 S06/S07; recovery-path replay, HTTP `targetTime` | Transaction-commit granularity; local window is write volume |
| Backup lifecycle retention and blob GC | Yes | No | No | Task D5 report, `BackupLifecycleManager.cs` | Dry-run default safety model |
| HRA snapshot (`.hra`) included in backup | Yes | No | No | P30 S12, `BackupManifestBuilder.cs` | Closes Gap C — rows written since last shutdown are now backed up |
| Mutable keyed tier (`.mkt`) included in backup | Yes | No | No | P30 S12, `BackupManifestBuilder.cs` | Cache/UPSERT tier rows covered in backup and restore |
| Public REST backup/restore operations | Yes | No | No | P16 SA4, `/admin/backup/*`, both SDKs | Exact restore + PITR `targetTime` (BL-186 S07). Studio UI is exact-restore-only |
| Per-database checkpoint sync in replication host | No | Yes | No | `ReplicationHostedService.cs` limitation note | Uses first available DB for checkpoint today |

## 2.7 Core concepts and mental model

- **Server root layout**
  - `Server/` holds server-level metadata (including DB registry).
  - `Databases/{db}/` is each logical database root.
- **Database persistence planes**
  - `catalog/` for schema/policy snapshot.
  - `wal/` for write-ahead durability and replay.
  - `tables/` for table segment files.
  - `materialized/` for materialized definition/state files.
- **Table segment file types** (P30 additions):
  - `.col` — cold column segment file (always produced by the demotion path)
  - `.hot` — immutable hot segment file (produced at flush; P30 hot-first invariant)
  - `.hra` — HRA snapshot on graceful shutdown; included in backup since P30 (Gap C)
  - `.mkt` — mutable keyed tier serialisation; included in backup since P30 (Gap C)
  - `.spr` — sparse PK index for cold segments
  - `.tombstone` — durable retirement tombstone preventing orphaned cold file resurrection after crash (P30 S11)
  - `_deleted.pages` — a segment's deletion mask. (**ColumnarCore S12, 0.2.0**) A merge that tombstones rows now
    appends a small record (each with its own CRC; a torn one is ignored) instead of rewriting the whole mask: the file
    is the whole bitmap followed by those records, rewritten whole when the records outgrow the bitmap. That is its only
    layout. A mask that exists but cannot be read fails the read, naming the table and segment, instead of being taken
    as nothing deleted (**BL-725, 0.2.0**). Its header records how many rows the bitmap deletes, and a mask whose
    count disagrees with its bitmap is unreadable (**ColumnarRead, next train**).
  - `segment.manifest` — a cold segment's footer (**ColumnarRead, next train**): every page's location and statistics
    (min / max, null count, sortedness, run count, first / last value, sums, small value sets), the first and last
    sort-key value of each 8,192-row group, each series' row range, and the primary-key range. CRC-checked; a footer
    written by an earlier build is refused.
- **Table segment layout**
  - Table path is name-based.
  - Default non-partitioned path uses `data/seg_*`.
  - No `_delta` path: late-arriving rows are flushed inline, and `_delta` is neither written nor read (**ColumnarRead, next train**).
  - A table's segments are the ones its catalog names; no read lists a directory, and a segment directory the
    catalog does not name is litter for the open-time sweep, never data (**ColumnarRead, next train**).
- **Upgrading from 0.2.x: export and reload** (**architecture review, next train**)
  - The catalog format is **5**. A data directory written by 0.2.x (catalog format 4) is **refused at open** with
    `CatalogFormatException`, saying so: export the data with the 0.2.x build that wrote it and load it into a fresh
    data directory with this build. There is no in-place upgrade — this build cannot read 0.2.x cold pages, footers or
    `.hot` files. Before, the catalog version had not moved, so a 0.2.x directory opened and its cold segments read as
    **zero rows, with no error**. The reverse holds too: a 0.2.x build refuses a directory this build wrote ("newer than
    this build supports").
  - A cold segment whose footer is another version fails the read that reaches it with
    `SegmentFormatUnsupportedException`, naming the table, the segment and the version — never an empty read. That is
    what a 0.2.x **backup** restored into this build does: it opens, and its segments fail by name when read
    ([Backup](backup.md#214-troubleshooting-by-symptom)).
  - Rows a 0.2.x or older build left under a table's `data/_delta/` are not read by this build (above) — the export
    taken with the older build is what carries them over.
  - A primary and its replicas must run the same build ([Replication](replication.md#27-core-concepts-and-mental-model)).
- **Durability layering**
  - Catalog snapshot durability and WAL durability are complementary, not alternatives.
  - WAL allows replay of committed deltas between snapshots/checkpoints.
- **Slot-governed WAL lifecycle**
  - Retention delete boundary is controlled by minimum active consumer position.
  - Consumers include replication, backup, and archive paths.
- **Engine vs server integration**
  - Backup/archive/restore engines are feature-rich in storage layer.
  - Public server APIs today expose replication/admin metrics, but not full backup orchestration operations.

Invariants:

- Persisted paths are deterministic from layout classes and storage constants.
- Table directory name validity is enforced (invalid names rejected; no path sanitization tricks).
- WAL replay never requires table directory guessing; resolver maps `TableId` to table directory.
- Slot safety boundaries prevent WAL truncation ahead of active consumers.

## 2.8 How Aouda implements it

High-level path:

1. Server startup builds server/database layouts and database registry.
2. Database manager opens each database engine with catalog + WAL + storage roots.
3. Writes append WAL frames (if effective WAL enabled for that table).
4. Flush/compaction persists table segments and updates catalog state.
5. Restart path loads catalog/segments and replays WAL deltas.
6. WAL lifecycle workers and slot manager coordinate retention/archive safety.
7. Backup/restore engines use an image of the catalog store (**BL-840, next train**; a catalog checkpoint before) + file hashing + WAL position semantics.

Key implementation anchors:

- Layout and pathing:
  - `src/Aouda.Engine.Storage/StorageConstants.cs`
  - `src/Aouda.Engine.Storage/Layout/ServerDirectoryLayout.cs`
  - `src/Aouda.Engine.Storage/Layout/DatabaseDirectoryLayout.cs`
- Registry/catalog:
  - `src/Aouda.Engine.Storage/Registry/DatabaseRegistryStore.cs`
  - `src/Aouda.Engine.Catalog/CatalogStore.cs`
  - `src/Aouda.Engine.Catalog/CatalogApi.cs`
- WAL/recovery:
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Storage/Bootstrap/StorageBootstrap.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalReplayDriver.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalCheckpointer.cs`
- Backup/archive/restore:
  - `src/Aouda.Engine.Storage/Backup/BackupEngine.cs`
  - `src/Aouda.Engine.Storage/Backup/RestoreEngine.cs`
  - `src/Aouda.Engine.Storage/Backup/BackupLifecycleManager.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/Archive/WalArchiveWorker.cs`
- Server wiring:
  - `src/Aouda.Server/Startup/AoudaHostedService.cs`
  - `src/Aouda.Server/Startup/ReplicationHostedService.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/ReplicationController.cs`
  - `src/Aouda.Server/Controllers/MetricsController.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Startup/open database -> durable layout + WAL-ready engine

1. `AoudaHostedService.StartAsync()` creates `ServerDirectoryLayout` for configured data root.
2. It initializes `DatabaseRegistry`/`DatabaseManager` from persisted registry snapshot.
3. For each database, manager opens engine through `AoudaEngine.OpenAsync(...)`.
4. `OpenAsync` ensures database directories, loads catalog snapshot, creates `FilePageStore`, conditionally creates `WalWriter`.
5. Engine starts compaction worker and initializes materialized/query subsystems.

State/persistence effects:
- Missing directories are created.
- Catalog snapshot is loaded from disk.
- WAL file is opened/appended if WAL enabled.

Observability:
- Server startup logs database load and memory budget registration.

Primary tests:
- `tests/Aouda.Server.Tests/ConfigurationIntegrationTests.cs`
- `tests/Aouda.Engine.Storage.Tests/EndToEndRestartTests.cs`

### Walk-through B: Insert/update write path -> WAL append -> later replay

1. Write enters engine mutation path (`InsertRowsAsync`/update path).
2. `ResolveWalWriter(tableEntry)` decides effective writer:
   - Database WAL disabled -> no writer.
   - Table durability override can disable WAL even when DB WAL on.
3. If writer exists, `WalWriter.AppendAsync(...)` writes framed WAL record and flushes.
4. On restart, `StorageBootstrap` + `WalReplayDriver` consume checkpoint boundaries and replay frames into HRA/storage state.

State/persistence effects:
- Durable WAL frame persisted before relying on replay semantics.
- Replay reconstructs committed changes after restart/crash.

Observability:
- WAL skip and replication filter counters for per-table durability behavior.

Primary tests:
- `tests/Aouda.Engine.Storage.Tests/WalReplayDriverTests.cs`
- `tests/Aouda.Engine.Storage.Tests/WalCheckpointIntegrationTests.cs`
- `tests/Aouda.Engine.Api.Tests/TableDurabilityTests.cs`

### Walk-through C: Backup engine full/incremental backup flow

1. Caller invokes `BackupEngine.CreateBackupAsync(...)`.
2. Engine takes one image of the catalog store — every table and segment entry, with keys, partitioning, cluster order,
   nullability and policies — pins the segments it names until they are uploaded, then captures WAL position/fencing token
   (**BL-840, next train**; it wrote a catalog checkpoint, `catalog.chk`, which held only column ids, names, types and encoders).
   The backup format is 3; a restore puts the catalog store back as it was and refuses an older format before it touches the
   target.
3. Manifest builder computes SHA256 across eligible files and compares against base manifest for incremental mode.
4. New blobs are uploaded (parallelism-limited), dedup by content hash.
5. Manifest/index is written.
6. Backup slot is updated to manifest WAL position.

State/persistence effects:
- Backup chain records precise WAL boundary.
- Content-addressable archive avoids re-upload of unchanged files.
- Slot update protects required WAL history from premature purge.

Observability:
- Backup operation counters and slot update counters.

Primary tests:
- `tests/Aouda.Engine.Storage.Tests/Backup/BackupEngineIntegrationTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Backup/BackupEngineParallelTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Backup/BackupEngineSlotTests.cs`

### Walk-through D: WAL lifecycle — physical layout, retention, and the archive cycle that does not run

This walk-through covers two different things, and they must not be read as one. The physical
layout and retention model below (bytes 1–6) are **sound, load-bearing, and unaffected by any
known defect** — this is the part of the WAL subsystem that keeps a running server's disk bounded
today. The archive cycle after it (byte 7) is **code that exists but that no shipped host ever
runs.** This document previously described the archive cycle as if it were both correct and live;
it is neither, and the sections were never separated. They are now.

#### D.1 — The sound part: physical layout, positions, and reclamation

1. **Physical layout.** The production WAL is a segmented log under `{db}/wal/`: segments named
   `wal_%09d.log` (`WalSegmentNamer`), a manifest `wal.manifest.json`, a crash-recovery control
   file `CHECKPOINT`, and a portioned-recovery resume sidecar `RECOVERY`. Segment size is
   `clamp(MaxWalBytes / 16, 8 MB, 64 MB)`. A leftover monolithic `insert.wal` from before
   segmentation is refused at open until `aouda wal convert` runs.
2. **Position model.** Every WAL position — in a slot, in the checkpoint, on the ladder below — is
   a **cumulative byte offset into a virtual, infinite log** (the PostgreSQL LSN model), not a row
   count and not a file offset. `WalManifest` tracks a pruned base offset so absolute positions
   survive segment deletion. Any WAL-related number that is not in this unit is a bug.
3. **Reclamation boundary.** `WalSlotManager.GetSafeDeleteBoundary()` returns the **minimum**
   `LastConsumedPosition` across every active slot (`system`, `backup`, `replication` per
   subscriber, and `archive` when one exists — see D.2). WAL is never deleted past the slowest
   consumer, by construction.
4. **Checkpoint horizon (the `system` slot).** On each flush and periodically, the engine computes
   a watermark from the compaction state and the WAL's own safe-redo position, writes an
   `HraCheckpoint` frame per table, and rewrites `{db}/wal/CHECKPOINT` with that watermark as the
   redo start position. This horizon lets crash recovery **fast-forward** past already-flushed WAL
   — it never by itself authorizes **deletion**; deletion is always `MIN(all slots)` (previous
   point), a distinction that matters because it is easy to conflate the two.
5. **Retention worker cycle** — (**WorkloadCore S16, next train**) on demand: when the log crosses 85 % of `MaxWalBytes`
   (`T26`), when an append is refused at 95 %, and after every checkpoint; it used to run every
   `RetentionCheckInterval` (5 minutes), which is gone. It computes the safe
   delete boundary; applies an archive-before-delete constraint if configured; invalidates (deletes)
   any slot but `system` whose lag from the current WAL head exceeds `MaxSlotWalKeepBytes`; recompute
   the boundary; prune whole segment files below it, always keeping the active segment; publish the
   reduced manifest before deleting files (a crash between the two leaves unmanifested files, which
   open reconciles); update WAL-on-disk / WAL-reclaimable inventory metrics.
6. **The size ladder** (`WalSizeGovernor`, one per WAL root) is the backstop: `MaxWalBytes` derived
   from free disk space, a force-checkpoint rung at 70% of it, a run-retention-now rung at 85% (**WorkloadCore S16, next train**)
   (it was an insert-throttle rung: a fixed delay inside the commit; the writer is now slowed before
   it takes any lock, by the ingest stall curve — see the sizing guide), an
   insert-refusal rung (`WAL_CAPACITY_EXCEEDED`, HTTP 503 + a `Retry-After` estimated from the rate
   retention frees log) at 95%, and a
   slot-keep-bytes rung (`MaxSlotWalKeepBytes`, roughly half of `MaxWalBytes`, clamped to 128 MB–2
   GB) — the **only** mechanism that ever forces a slot to give up WAL it has not consumed. This is
   also the local PITR window's true shape: a bound on **write volume since the
   last backup**, never a duration and never unbounded, because exempting the backup slot from this
   ladder would reintroduce the unbounded-WAL-growth failure it exists to prevent.

Net effect today: a server that never takes a backup and never archives keeps WAL bounded purely by
the ladder in point 6. A server that takes backups keeps the backup slot's WAL around until the
next backup or until the ladder invalidates it — whichever comes first.

#### D.2 — The WAL archive cycle

`WalArchiveWorker` is constructed and started by `AoudaEngine.OpenAsync` whenever the host supplies
an archive destination. `Aouda.Server` does this when `Archive.Enabled` is true and `Destination`
is set (standalone `Aouda:Archive`, or a replica-set Backup node's `ThisNode.Archive`).

1. `WalArchiveWorker.RunOnceAsync()` loads the local WAL manifest and the archive manifest.
2. It archives completed (non-active) segments with compression and content-addressable upload.
3. Archive slot is advanced after successful archive writes (positions are cumulative byte offsets).
4. Cleanup path removes archived entries older than `WalRetentionDays` while respecting the oldest backup's
   WAL boundary.

`RequireArchiveBeforeDelete = true` is rejected at startup unless archive is enabled and destinationed.

The local PITR window remains write volume even when archiving is off. Archiving extends recovery
beyond that bound. See [Backup and restore §2.4](backup.md#24-availability-status).

Observability: archive cycle, bytes, and error counters are on `GET /api/metrics` (`WalMetrics`);
`WalArchiveHealthCheck` degrades when archiving is configured but the worker has not completed a cycle.

Primary tests:
- `tests/Aouda.Engine.Storage.Tests/WalIntegration/WalArchiveWorkerTests.cs`
- `tests/Aouda.Engine.Api.Tests/Bl186S05ArchiveWorkerLifecycleTests.cs`
- `tests/Aouda.Server.Tests/Startup/Bl186S05ArchiveWorkerWiringTests.cs`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Is storage layout explicit and code-governed? | Often implicit/internal conventions | First-class layout classes and constants define server/db/table paths | Easier ops debugging and safer refactors |
| Can table-level durability diverge from DB defaults? | Often coarse DB-instance toggles | Per-table `TableDurabilityOptions` with validation against DB constraints | Fine-grained durability/cost control |
| Is WAL retention consumer-aware by design? | Manual purge policies are common | Slot-based boundary across system/replication/backup/archive consumers | Lower risk of destructive WAL pruning |
| Are backup/restore engines integrated with WAL semantics? | Often external tooling or loose scripts | Backup engine records a WAL boundary as a slot; exact restore re-bases the WAL root; PITR replays through crash recovery | Recoverable exact restore and commit-granular PITR |
| Is implementation honesty documented as surface parity (engine vs server API)? | Docs often blur internal vs public surface | Explicit split: engine-complete backup classes vs partial public API orchestration | Fewer false assumptions for SDK/operator teams |

## 2.10 Configuration and settings reference (complete surface)

{: .note }
**Precedence and restart:** [Server configuration](server-configuration.md). Startup keys bind from code defaults, optional `appsettings.json`, `AOUDA_*` env, or CLI (CLI highest). Release installs use service `--data-path` / `--port` only.

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:DataPath` | string | `./data` | non-empty path | startup config | Server root path |
| `Aouda:Port` | int | `5000` | 1..65535 | startup config | HTTP port |
| `Aouda:Databases:{db}:EnableWal` | bool | `true` | true/false | startup config | DB-level WAL switch |
| `Aouda:Databases:{db}:ReplicationMode` | string | `Replicate` | `Replicate`, `DoNotReplicate` | startup config | DB replication participation |
| `Aouda:Databases:{db}:DefaultTemperature` | string | `Auto` | `Auto`,`HotOnly`,`ColdPreferred` | startup config | Default table policy |
| `Aouda:Databases:{db}:MaxMemoryBytes` | long? | `null` | null or non-negative | startup config | Per-db memory cap |
| `Aouda:Databases:{db}:WriteConcern` | string | `One` | `One`,`Majority`,`All` | startup config | ACK semantics |
| `Aouda:Databases:{db}:WriteConcernTimeoutMs` | int | `5000` | >=100 | startup config | Timeout for higher write concerns |
| `Aouda:Databases:{db}:OnWriteConcernTimeout` | string | `DegradeAndLog` | `Fail`,`Degrade`,`DegradeAndLog` | startup config | Timeout policy |
| `CreateDatabaseRequest.enableWal` | bool | `true` | true/false | HTTP create-db payload | API default |
| `CreateDatabaseRequest.replicationMode` | string | `Replicate` | `Replicate`,`DoNotReplicate` | HTTP create-db payload | API default |
| `CreateDatabaseRequest.defaultTemperature` | string? | null -> `Auto` | valid temperature enum | HTTP create-db payload | Optional |
| `CreateDatabaseRequest.maxMemoryBytes` | long? | null | null or non-negative | HTTP create-db payload | Optional |
| `Archive.Enabled` | bool | `false` | true/false | startup config | Starts `WalArchiveWorker` when a destination is also set |
| `Archive.Destination` | string | empty | URI/path | startup config | Required when archive enabled |
| `Archive.WalRetentionDays` | int | `7` | >=1 | startup config | Archive retention (not the local PITR window) |
| `Archive.RequireArchiveBeforeDelete` | bool | `false` | true/false | startup config | Rejected at startup unless archive is enabled + destinationed |
| `BackupOptions.Parallelism` | int | engine default | >=1 | .NET engine call | Backup engine only, not server API config |
| `RestoreOptions.Parallelism` | int | engine default | >=1 | .NET engine call | Restore engine only |
| `RestoreOptions.TargetTime` | datetime? | null | any valid timestamp | .NET engine call | Enables PITR flow |

Configuration precedence and behavior notes:

- CLI mappings available for core server settings:
  - `--data-path`, `--port`, `--max-memory`, `--max-hot-bytes`, `--max-cache-bytes`
  - short aliases include `-d`, `-p`, `-m`
- Startup validation rejects invalid server/database/archive settings (`AoudaServerOptionsValidator`).
- Dynamic vs restart-required:
  - `DatabasesController.CreateDatabase` can add DBs dynamically.
  - WAL enablement changes for existing DBs are effectively restart-sensitive (host warns when reconciled config differs from opened engine).
- Safety-gated:
  - Invalid database names and invalid enum values are rejected.
  - Table-level durability cannot override disabled database WAL/replication to `true`.
- Reserved/partial:
  - Backup/restore knobs are rich in engine APIs; HTTP restore accepts `targetTime`. Studio has no PITR control.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (embedded/server-side engine)

```csharp
var engine = await AoudaEngine.OpenAsync(
    dataPath: "./data/Databases/appdb",
    enableWal: true,
    enableReplication: true);

await engine.CreateTableAsync(
    "orders",
    new[] { ("id", DataType.Int64, EncoderPreference.Auto, false) });
```

Expected result: engine opens persistent layout, WAL enabled, and table is created under table-name-based storage paths.

Common mistake: assuming `AoudaEngine` backup/restore APIs are automatically exposed as server HTTP admin endpoints.

### TypeScript example

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
});

await client.databases.create("analytics", {
  enableWal: true,
  replicationMode: "Replicate",
  defaultTemperature: "Auto",
});

const dbs = await client.databases.list();
console.log(dbs.map((d) => d.name));
```

Expected result: database created with requested persistence defaults and visible through server-level list.

Common mistake: expecting `client.admin` or `client.databases` to expose backup/restore execution endpoints.

### HTTP/protocol examples

```http
POST /api/databases
Content-Type: application/json

{
  "name": "appdb",
  "enableWal": true,
  "replicationMode": "Replicate",
  "defaultTemperature": "Auto"
}
```

```http
GET /admin/replication/status
```

Expected result: create-db returns DB options snapshot; replication status returns per-database WAL lag telemetry when replication is configured.

Common mistake: using `/api/admin/metrics` backup counters as if they are backup job controls (they are observability outputs).

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Open durable engine with WAL | `AoudaEngine.OpenAsync(enableWal: ...)` | N/A (server concern) | DB create `enableWal` sets DB-level behavior | Implemented | DB-level and table-level durability both available |
| Create DB with persistence options | `DatabaseManager.CreateDatabaseAsync` (server-side) | `client.databases.create(...)` | `POST /api/databases` | Implemented | Good parity for core options |
| Per-table durability overrides | `CreateTableAsync(... durability)` / `AlterTableDurabilityAsync` | No first-class model | No dedicated table durability endpoint | Partial | Engine implemented; not fully surfaced in HTTP/TS |
| Replication persistence status | `ReplicationState`/host services | `client.admin.replication.status/topology/coverage` | `/admin/replication/*` | Implemented | Monitoring and topology surface available |
| Backup metrics visibility | Perf + metrics collector | `client.admin.metrics.*` | `GET /api/admin/metrics*` | Implemented | Observability only |
| Execute backup/restore lifecycle | `BackupEngine`, `RestoreEngine`, `BackupLifecycleManager` | `client.admin.backup.*` | `/admin/backup/*` | Implemented | P16 SA4; PITR via `targetTime` (BL-186 S07) |
| Archive worker lifecycle controls | `WalArchiveWorker` (started with the engine) | Not exposed | No explicit archive admin routes | Partial | Worker runs when configured; no start/stop HTTP API. Health check covers "configured but not cycling." |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Trigger/list backup operations over server API | — | — | Shipped (P16 SA4) | — |
| Trigger restore over server API | REST + TS SDK wrappers | — | Shipped (P16 SA4) | — |
| Trigger PITR over HTTP/SDK | — | Studio UI and MCP tool stay exact-restore-only | Shipped (BL-186 S07) | — |
| Manage archive worker lifecycle (start/stop/state) via API | Archive admin endpoints | Inspect metrics and server logs; custom host wiring | P4/P6 operationalization follow-up | Medium |
| Table durability endpoint parity | REST/TS update path for table `EnableWal`/`EnableReplication` | Use .NET engine/catalog API | P6 + API parity follow-up | Medium |
| Per-database checkpoint sync controls in replication API | Explicit API/status for each DB checkpoint sync state | Current first-database checkpoint behavior | P6 replication checkpoint follow-up | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run durable baseline

When to use:
- New single-node deployment where you want standard durability defaults.

Steps:
1. Start server with `aouda start --data-dir ./data --port 5433` (or optional local `appsettings.json` — see [Server configuration](server-configuration.md)).
2. Create a database using `POST /api/databases` (or `client.databases.create`).
3. Create one table and insert sample data.
4. Restart server and query table again.

Expected result checks:
- Data and schema survive restart.
- Database appears under `Databases/{db}` with `catalog/`, `wal/`, and `tables/`.
- Query results after restart match pre-restart state.

### Scenario 2: Controlled WAL policy for mixed-cost databases

When to use:
- Multi-database server where one DB needs WAL disabled for ephemeral workloads.

Steps:
1. Create two DBs:
   - `durable_db` with `enableWal=true`
   - `ephemeral_db` with `enableWal=false`
2. Write similar traffic to both.
3. Inspect behavior via logs/metrics and WAL file presence per DB.
4. Validate per-table durability override constraints in durable DB (optional).

Expected result checks:
- `durable_db` emits WAL writes; `ephemeral_db` does not.
- Attempting table durability `EnableWal=true` where DB WAL is disabled is rejected.
- Replication filtering follows effective table/database durability settings.

### Scenario 3: Engine-level backup + exact restore validation

When to use:
- Pre-production operator validation of backup chain correctness.

Steps:
1. Use `BackupEngine.CreateBackupAsync(...)` for full backup.
2. Apply additional writes and run incremental backup.
3. Use `RestoreEngine.RestoreAsync(...)` (or `POST /admin/backup/restore/{id}`) for an exact restore,
   or pass `targetTime` for PITR (see [Backup and restore](backup.md#24-availability-status)).

Expected result checks:
- Incremental manifest marks unchanged files as not new.
- Backup slot advances after successful backup (a real per-database WAL position, not `0`).
- Restore integrity verification passes and recovered data reflects the selected backup.
- A `targetTime` restore keeps writes committed at or before the target and drops later ones.

## 2.13 Operations and observability

Monitor first:

- Storage/recovery path:
  - Restart/replay errors and checkpoint/replay duration metrics.
- WAL lifecycle:
  - Slot positions (system/replication/backup/archive), retention prune counters.
- Backup/archive:
  - Backup operation counters, upload bytes, failure counters.
  - Archive cycles, archived segments, compression ratio, archive errors.
- API-level posture:
  - Replication status endpoints for lag and per-db positions.
  - Admin metrics backup subsystem for operational signals.

Cold-page integrity (**BL-815, next train**):

- Every cold page carries a CRC. A reader checks it the first time it reads the page, and a **background scrubber** checks
  every cold page again against the disk: the first pass 15 minutes after the database opens, then one every 24 hours, under
  64 MiB/s of disk reads, yielding while queries are waiting. It covers the tables currently loaded (a table not yet touched since
  open is checked by its first read instead).
- A page whose CRC no longer matches is **reported** — an `Error` log line naming the table, segment, column and offset, repeated
  on every pass until the segment is replaced — and is **never returned as data**: reads that need that page fail with a
  corruption error, while the rest of the table reads normally. The scrubber does not repair; restore the table from a backup or
  re-sync it from a replica.
- Between two passes, a page corrupted after its first read can still be read from disk unchecked. Checking every read from disk
  instead costs 51–75 % of the read, which is why it is not done.

Recovery/restart expectations:

- Restart should reload catalog and segment state and replay WAL deltas.
- If WAL is disabled for a DB/table, those writes are not WAL-durable by design.
- Backup/restore engine flows are deterministic when using verified manifests and available WAL archives.

Suggested tuning sequence:
1. Validate layout and defaults first (no advanced tuning).
2. Set explicit per-database WAL/replication and write concern policies.
3. Add archive mode and retention policies only after baseline durability is stable.

| Question | Practical answer |
|---|---|
| How do I know replay is required after restart? | WAL and checkpoint state diverge; replay driver engages during startup paths |
| Where do I inspect per-db replication lag? | `GET /admin/replication/status` |
| Do backup counters mean backup APIs exist? | Yes — `/admin/backup/*` shipped in P16; counters also reflect engine/host activity |
| What protects WAL from unsafe deletion? | Slot-based minimum consumer boundary with lifecycle coordinator/retention logic |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Data path exists but DB cannot open | Invalid/partial directory state or config mismatch | Check server startup logs, validate `DataPath`, verify required DB subdirectories |
| `CatalogFormatException` at open: "catalog root declares format version 4" | The directory was written by 0.2.x or earlier (**architecture review, next train**) | Export with the build that wrote it and load into a fresh data directory with this build; see [Upgrading from 0.2.x](#27-core-concepts-and-mental-model) |
| A read fails with `SegmentFormatUnsupportedException` naming a segment | That segment was written by another build — typically a 0.2.x backup restored into this one | Restore the backup with the build that wrote it, export, and reload |
| Table create fails for valid schema but path error appears | Table name rejected by `TablePathValidator` constraints | Use directory-safe table name (no separators/reserved chars) |
| WAL file not growing for a table | Effective table durability has WAL disabled or DB WAL disabled | Check DB `enableWal` and table durability overrides |
| Replication lag remains high on one DB | Secondary subscription/filter or checkpoint limitations | Inspect `/admin/replication/topology` and `/admin/replication/coverage` |
| Cannot perform backup via HTTP | Destination not configured, or not authorized | Configure `Archive.Destination` (or per-request destination); call `POST /admin/backup/trigger` |
| An `Error` log line `[SegmentScrubber] corrupt page: table …, segment …, column …`, and reads of that table failing with a corruption error (**BL-815, next train**) | A cold page changed on disk after it was written (a media error, or something other than Aouda wrote to the data directory) | Check the disk. Restore the table from a backup or re-sync it from a replica. The line repeats every 24 hours until the segment is replaced |
| Restore refused: "backup format version N; this build restores format version 3 only" (**BL-840, next train**) | The backup was taken by an older build (format 1 or 2), whose catalog copy lacks keys, partitioning and nullability. Nothing was restored | Restore it with the build that took it; then take a new backup with this build. See [Backup](backup.md#b-restore-exact-backup) |
| Open refused: "WAL frame … (… format 1) at position …: this build replays … in format 2 … only" (**BL-823, BL-837, BL-923, next train**) | The log holds, past its checkpoint, a frame an older build wrote and this build no longer replays: an edge insert (`EdgeInsert`, tag 40 → `EdgeInsertV2`), a vector insert (`VectorInsert` → `VectorInsertV2`), or a keyed delete / merge / delete by identity (`HraRowDelete` 23 → 70, `MergeBatch` 66 → 71, `HraRowDeleteById` 67 → 72). It happens only when the older build stopped **without** a clean close while such writes were not yet checkpointed | Open the database once with the build that wrote it and close it cleanly — its rows, edges and vectors are then in segments and the frame is not replayed — then open it with this build. Or restore from a backup taken by this build. A cleanly closed database is unaffected |
| Open refused with a `JsonException` loading an empty `wal/slots.json` after a clean close, or over an empty materialized-query `definition.json` after two coalescing-window changes at once or a cancelled one | Fixed (**BL-933, BL-935, next train**): two writers' saves of one file could overlap through a shared temp file and leave it empty. Every file an open reads is now written whole (its own temp file, fsync, rename, directory fsync), one writer at a time | Upgrade. A database already left that way: restore from a backup. An empty or unreadable slot file is still refused at open — it is a bug if it happens, not a state to tolerate |
| PITR target fails | Window closed (write volume since last backup, or archive gap); backup not PITR-eligible (`walPosition` 0); or target at/before backup `createdUtc` | Take a newer backup, enable archiving, or pick a later `targetTime`. Exact restore (no `targetTime`) is unaffected |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31` (doc synthesis pass uses task-report command evidence plus code/test cross-check).

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Hot segment persistence + restart semantics | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~HotSegmentPersistenceTests" --verbosity minimal` | Pass (per P3 Task7 report) | 2026-01-xx | Covers restart + file integrity path |
| Backup manifest engine package | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~BackupManifest" --verbosity minimal` | Pass (per Task D1 report) | 2026-01-28 | Manifest/hash coverage |
| Incremental backup orchestration | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~BackupEngine" --verbosity minimal` | Pass (35 tests in report) | 2026-01-29 | Includes parallel and integration paths |
| Backup lifecycle retention/GC | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~Lifecycle" --verbosity minimal` | Pass (42 tests in report) | 2026-01-29 | Dry-run/execute + safety checks |
| WAL archive worker | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~WalArchiveWorker" --verbosity minimal` | Pass (report indicates 66+ coverage) | 2026-02-02 | Archive cycle, cleanup, slot update |
| Per-database WAL replication | `dotnet test tests/Aouda.Engine.Replication.Tests --verbosity minimal` | Pass (`497/497` per report) | 2026-02-17 | Includes v2 per-db protocol tests |
| Server config + DB create options | `dotnet test tests/Aouda.Server.Tests --filter "FullyQualifiedName~ConfigurationIntegrationTests" --verbosity minimal` | Pass (suite targeted in phase work) | 2026-02-xx | Confirms config binding/validation paths |
| TS database API bindings | `npm test -- tests/databases.test.ts` (in `../aouda-client-ts`) | Pass (phase-level client coverage) | 2026-02-xx | Confirms create/list/get/drop API contracts |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Catalog persistence round-trip | `CatalogPersistenceTests.cs`, `CatalogWalTests.cs` | Pass | Strong | Snapshot + catalog WAL paths |
| Restart + WAL replay correctness | `EndToEndRestartTests.cs`, `WalReplayDriverTests.cs`, `WalCheckpointIntegrationTests.cs` | Pass | Strong | Core durability behavior |
| WAL retention and lifecycle | `WalRetentionTests.cs`, slot/lifecycle tests from P4/P6 packages | Pass | Medium/Strong | Good functional coverage |
| Table-name directory storage | P6 Task4 report-linked tests + `TablePathValidatorTests.cs` | Pass | Strong | Path validation and resolver wiring |
| Per-table durability control | `TableDurabilityTests.cs`, `TableDurabilityPersistenceTests.cs` | Pass | Strong | Override + inheritance + persistence |
| Backup engine | `BackupEngineTests.cs`, `BackupEngineParallelTests.cs`, `BackupEngineIntegrationTests.cs`, `BackupEngineSlotTests.cs` | Pass | Strong | Full/incremental/slot semantics |
| Restore + PITR | `RestoreIntegrationTests.cs`, `Bl186S06PitrRecoveryPathTests.cs`, `Bl186S07PitrHttpTests.cs` | Pass | Strong | Exact restore + recovery-path PITR over HTTP |
| Backup lifecycle retention/GC | `LifecycleIntegrationTests.cs`, `BackupLifecycleManagerTests.cs` | Pass | Strong | Chain-preservation and dry-run safety |
| Server persistence config path | `ConfigurationIntegrationTests.cs` | Pass | Medium | Validation and startup config behavior |
| TS persistence-adjacent API contracts | `../aouda-client-ts/tests/databases.test.ts`, `../aouda-client-ts/tests/admin.test.ts` | Pass | Medium | Client HTTP contract coverage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| Limited cross-surface test: engine backup completion reflected through server metrics in realistic host wiring | Confirms observability parity and avoids stale assumptions | Add integration harness that runs backup engine in host context and asserts `/api/admin/metrics` backup counters | Medium |
| Per-database checkpoint sync limitation not guarded by dedicated regression test | Future changes could silently regress or mislead | Add replication integration test documenting and asserting current first-db checkpoint behavior until upgraded | Medium |
| No TS SDK tests for table durability override APIs (because surface missing) | API parity gap can drift unnoticed | Add TODO contract tests when table durability endpoints are introduced | Medium |
| No doc-driven automated verification artifact for this domain | Manual ledger can become stale | Add CI job summary artifact for storage/persistence verification suites | Medium |

## 2.18 Known gaps and undone work

- Public backup/restore orchestration surface:
  - HTTP `/admin/backup/*` and both SDKs ship exact restore and PITR (`targetTime`). Studio UI is exact-restore-only (BL-332).
- Archive destinations:
  - Local and S3 ship; Azure/GCS throw `NotSupportedException`.
- Replication checkpoint sync:
  - `ReplicationHostedService` checkpoint path still uses first available database; atomic apply of replica catch-up is BL-328.
- Persistence-policy ADR breadth:
  - ADR 0005 policy language (`MemoryOnly`, `DiskOnly`, `Hybrid`) is broader than currently explicit HTTP/TS policy modeling.
  - User impact: policy intent should be mapped to actual shipped knobs (`enableWal`, table/db options), not ADR labels alone.

## 2.19 References

- ADRs:
  - `docs/decisions/0001-column-per-file.md`
  - `docs/decisions/0002-json-catalog-persistence.md`
  - `docs/decisions/0003-write-ahead-log.md`
  - `docs/decisions/0005-persistence-policies.md`
  - `docs/decisions/0016-wal-lifecycle-management.md`
- Task docs/reports:
  - `docs/tasks/P3/P3-Task7-HotSegmentPersistence-Report.md`
  - `docs/tasks/P3/P3-BugFix-HotSegmentPersistence-AllDataTypes-Report.md`
  - `docs/tasks/P4/P4-EpicD-Task1-BackupManifest-Report.md`
  - `docs/tasks/P4/P4-EpicD-Task3-IncrementalBackupEngine-Report.md`
  - `docs/tasks/P4/P4-EpicD-Task5-BackupLifecycleManagement-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task2-WalArchiveWorker-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task5-BackupIntegration-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task4-TableNameBasedDirectoryStorage-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task5-PerTableWalAndReplicationControl-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`
- Code paths:
  - `src/Aouda.Engine.Storage/StorageConstants.cs`
  - `src/Aouda.Engine.Storage/Layout/ServerDirectoryLayout.cs`
  - `src/Aouda.Engine.Storage/Layout/DatabaseDirectoryLayout.cs`
  - `src/Aouda.Engine.Storage/Registry/DatabaseRegistryStore.cs`
  - `src/Aouda.Engine.Catalog/CatalogStore.cs`
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Storage/Bootstrap/StorageBootstrap.cs`
  - `src/Aouda.Engine.Storage/Backup/BackupEngine.cs`
  - `src/Aouda.Engine.Storage/Backup/RestoreEngine.cs`
  - `src/Aouda.Engine.Storage/Backup/BackupLifecycleManager.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/Archive/WalArchiveWorker.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptions.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigSection.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/ReplicationController.cs`
  - `src/Aouda.Server/Controllers/MetricsController.cs`
  - `../aouda-client-ts/src/databases.ts`
  - `../aouda-client-ts/src/admin/server.ts`
- Test files:
  - `tests/Aouda.Engine.Catalog.Tests/CatalogPersistenceTests.cs`
  - `tests/Aouda.Engine.Catalog.Tests/CatalogWalTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/EndToEndRestartTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalReplayDriverTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalCheckpointIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/BackupEngineIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/RestoreIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/LifecycleIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Backup/PitrFromArchivedWalTests.cs`
  - `tests/Aouda.Server.Tests/ConfigurationIntegrationTests.cs`
  - `../aouda-client-ts/tests/databases.test.ts`
  - `../aouda-client-ts/tests/admin.test.ts`

## 2.20 What is missing from this document? (meta completeness)

- This doc intentionally avoids claiming complete server-admin backup orchestration because controller-level surfaces are not yet first-class.
- Verification ledger entries are sourced from phase report command evidence plus code/test audit in this pass; they should be refreshed with live reruns when formalizing release docs.
- If backup/restore HTTP APIs are introduced, sections `2.10`, `2.11`, `2.12`, and `2.14` must be updated immediately to remove current API-gap warnings.

