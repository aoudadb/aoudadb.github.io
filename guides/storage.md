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
| `ArchiveConfig.CheckpointIntervalHours` | `24` | Daily checkpoint cadence when archive enabled |
| `ArchiveConfig.WalRetentionDays` | `7` | 7-day archive retention target when enabled |

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
  - Archive worker and retention worker infrastructure implemented.
- Backup/restore engines:
  - `BackupEngine`, `RestoreEngine`, and `BackupLifecycleManager` implemented and tested in storage layer.
  - PITR from archived WAL implemented at engine layer.

### Planned / proposed

- Full managed backup operations as primary server/admin API workflows:
  - Architecture is present in engine/storage, but API-host integration is comparatively thin.
- Broader cloud destination operationalization:
  - Archive destination abstraction exists; production hardening for specific providers is task-driven.
- Per-database checkpoint synchronization in replication:
  - Current replication hosted service explicitly documents first-database checkpoint limitation.

### Reserved / not yet wired

- No first-class public REST backup/restore job endpoints are exposed in server controllers.
- WAL archive mode has config/validation shape, but full hosted orchestration parity with replication-hosted paths remains partial.
- Some persistence-policy ADR concepts (`DiskOnly`, full policy matrix) are not exposed as explicit end-user policy enums in current HTTP/TS surfaces.

> **Note (P30):** `MemoryOnly` durability mode is now fully enforced end-to-end (P30 S2). `MemoryOnly` tables write nothing to disk — no `.hot`, `.col`, `.hra`, or WAL records. This is no longer a "reserved" surface. See `guides/hot-cold.md §2.4`.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P3 | `P3-Task7-HotSegmentPersistence-Report.md`, `P3-BugFix-HotSegmentPersistence-AllDataTypes-Report.md` | Hot segment file persistence, restart survival semantics, integrity checks, all core data types for hot persistence | Further file-format enhancements (for example mmap/compression tiers) out of scope | No dedicated open backlog item from these reports |
| P4 | `P4-EpicD-Task1/3/5-*Report.md`, `P4-EpicI-Task2/5-*Report.md` | Backup manifest/hash infra, incremental backup engine, lifecycle retention/GC, WAL archive worker, slot integration | Server-level backup/restore operation surfaces and scheduling are still not comprehensive API workflows | No explicit BL entry dedicated to backup API parity |
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
| WAL slot lifecycle management (`system/replication/backup/archive`) | Yes | No | No | ADR 0016 + P4 Epic I reports + slot code | Retention boundaries consumer-aware |
| Backup manifest + incremental dedup engine | Yes | No | No | P4 EpicD Task1/3 reports, backup engine tests | Engine-level implementation complete |
| Restore engine + PITR replay from archive | Yes | No | No | `RestoreEngine.cs`, PITR tests/reports | Engine-level implementation complete |
| Backup lifecycle retention and blob GC | Yes | No | No | Task D5 report, `BackupLifecycleManager.cs` | Dry-run default safety model |
| HRA snapshot (`.hra`) included in backup | Yes | No | No | P30 S12, `BackupManifestBuilder.cs` | Closes Gap C — rows written since last shutdown are now backed up |
| Mutable keyed tier (`.mkt`) included in backup | Yes | No | No | P30 S12, `BackupManifestBuilder.cs` | Cache/UPSERT tier rows covered in backup and restore |
| Public REST backup/restore operations | No | No | Yes | Server controllers + TS client surfaces | No dedicated backup/restore endpoints |
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
- **Table segment layout**
  - Table path is name-based.
  - Default non-partitioned path uses `data/seg_*`.
  - Delta path uses `_delta` under parent data scope.
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
7. Backup/restore engines use catalog checkpoint + file hashing + WAL position semantics.

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
2. Engine writes catalog checkpoint first, then captures WAL position/fencing token.
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

### Walk-through D: WAL archive cycle + retention boundary safety

1. `WalArchiveWorker.RunOnceAsync()` loads local WAL manifest and archive manifest.
2. It archives completed (non-active) segments with compression and content-addressable upload.
3. Archive slot is advanced after successful archive writes.
4. Cleanup path removes archived entries older than retention while respecting oldest backup WAL boundary.
5. Retention worker/manager can prune local WAL segments under safe slot boundary.

State/persistence effects:
- Archived WAL allows PITR beyond local retention.
- Consumer-aware boundary preserves replication/backup safety.

Observability:
- Archive cycle, bytes, ratio, and error counters.

Primary tests:
- `tests/Aouda.Engine.Storage.Tests/WalIntegration/WalArchiveWorkerTests.cs`
- `tests/Aouda.Engine.Storage.Tests/WalRetentionTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Backup/PitrFromArchivedWalTests.cs`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Is storage layout explicit and code-governed? | Often implicit/internal conventions | First-class layout classes and constants define server/db/table paths | Easier ops debugging and safer refactors |
| Can table-level durability diverge from DB defaults? | Often coarse DB-instance toggles | Per-table `TableDurabilityOptions` with validation against DB constraints | Fine-grained durability/cost control |
| Is WAL retention consumer-aware by design? | Manual purge policies are common | Slot-based boundary across system/replication/backup/archive consumers | Lower risk of destructive WAL pruning |
| Are backup/restore/PITR engines integrated with WAL semantics? | Often external tooling or loose scripts | Backup engine records WAL boundary, restore supports WAL replay/PITR paths | Better consistency model for engine-level restores |
| Is implementation honesty documented as surface parity (engine vs server API)? | Docs often blur internal vs public surface | Explicit split: engine-complete backup classes vs partial public API orchestration | Fewer false assumptions for SDK/operator teams |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:DataPath` | string | `./data` | non-empty path | `appsettings`, env, CLI | Server root path |
| `Aouda:Port` | int | `5000` | 1..65535 | `appsettings`, env, CLI | HTTP port |
| `Aouda:Databases:{db}:EnableWal` | bool | `true` | true/false | `appsettings` | DB-level WAL switch |
| `Aouda:Databases:{db}:ReplicationMode` | string | `Replicate` | `Replicate`, `DoNotReplicate` | `appsettings` | DB replication participation |
| `Aouda:Databases:{db}:DefaultTemperature` | string | `Auto` | `Auto`,`HotOnly`,`ColdPreferred` | `appsettings` | Default table policy |
| `Aouda:Databases:{db}:MaxMemoryBytes` | long? | `null` | null or non-negative | `appsettings` | Per-db memory cap |
| `Aouda:Databases:{db}:WriteConcern` | string | `One` | `One`,`Majority`,`All` | `appsettings` | ACK semantics |
| `Aouda:Databases:{db}:WriteConcernTimeoutMs` | int | `5000` | >=100 | `appsettings` | Timeout for higher write concerns |
| `Aouda:Databases:{db}:OnWriteConcernTimeout` | string | `DegradeAndLog` | `Fail`,`Degrade`,`DegradeAndLog` | `appsettings` | Timeout policy |
| `CreateDatabaseRequest.enableWal` | bool | `true` | true/false | HTTP create-db payload | API default |
| `CreateDatabaseRequest.replicationMode` | string | `Replicate` | `Replicate`,`DoNotReplicate` | HTTP create-db payload | API default |
| `CreateDatabaseRequest.defaultTemperature` | string? | null -> `Auto` | valid temperature enum | HTTP create-db payload | Optional |
| `CreateDatabaseRequest.maxMemoryBytes` | long? | null | null or non-negative | HTTP create-db payload | Optional |
| `Archive.Enabled` | bool | `false` | true/false | `appsettings` | Standalone archive mode gate |
| `Archive.Destination` | string | empty | URI/path | `appsettings` | Required when archive enabled |
| `Archive.CheckpointIntervalHours` | int | `24` | >=1 | `appsettings` | Archive/checkpoint cadence |
| `Archive.WalRetentionDays` | int | `7` | >=1 | `appsettings` | Archive retention window |
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
  - Backup/restore knobs are rich in engine APIs but not exposed as first-class server-admin configuration workflows.

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
| Execute backup/restore lifecycle | `BackupEngine`, `RestoreEngine`, `BackupLifecycleManager` | Not exposed | No dedicated endpoints | Missing | Engine/library-complete but API-surface gap |
| Archive worker lifecycle controls | `WalArchiveWorker` (engine code) | Not exposed | No explicit archive admin routes | Missing | Partial host/config exposure only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Trigger/list backup operations over server API | HTTP admin backup endpoints + TS SDK wrappers | Use engine-level APIs in embedded/service code | P4 backup integration follow-up tasks | High |
| Trigger restore/PITR over server API | Restore/PITR REST + TS SDK wrappers | Use `RestoreEngine` in operator-controlled code paths | P4 backup/restore follow-up hardening | High |
| Manage archive worker lifecycle (start/stop/state) via API | Archive admin endpoints | Inspect metrics and server logs; custom host wiring | P4/P6 operationalization follow-up | Medium |
| Table durability endpoint parity | REST/TS update path for table `EnableWal`/`EnableReplication` | Use .NET engine/catalog API | P6 + API parity follow-up | Medium |
| Per-database checkpoint sync controls in replication API | Explicit API/status for each DB checkpoint sync state | Current first-database checkpoint behavior | P6 replication checkpoint follow-up | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run durable baseline

When to use:
- New single-node deployment where you want standard durability defaults.

Steps:
1. Keep default `appsettings.json` for `Aouda`.
2. Start server with default data path.
3. Create a database using `POST /api/databases` (or `client.databases.create`).
4. Create one table and insert sample data.
5. Restart server and query table again.

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

### Scenario 3: Engine-level backup + restore + PITR validation

When to use:
- Pre-production operator validation of backup chain correctness.

Steps:
1. Use `BackupEngine.CreateBackupAsync(...)` for full backup.
2. Apply additional writes and run incremental backup.
3. Optionally run `WalArchiveWorker.RunOnceAsync()` to archive WAL segments.
4. Use `RestoreEngine.RestoreAsync(...)` to restore latest or PITR target.

Expected result checks:
- Incremental manifest marks unchanged files as not new.
- Backup slot advances after successful backup.
- Restore integrity verification passes and recovered data reflects selected backup/PITR target.

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
| Do backup counters mean backup APIs exist? | No; counters indicate engine/host activity, not necessarily public backup-control endpoints |
| What protects WAL from unsafe deletion? | Slot-based minimum consumer boundary with lifecycle coordinator/retention logic |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Data path exists but DB cannot open | Invalid/partial directory state or config mismatch | Check server startup logs, validate `DataPath`, verify required DB subdirectories |
| Table create fails for valid schema but path error appears | Table name rejected by `TablePathValidator` constraints | Use directory-safe table name (no separators/reserved chars) |
| WAL file not growing for a table | Effective table durability has WAL disabled or DB WAL disabled | Check DB `enableWal` and table durability overrides |
| Replication lag remains high on one DB | Secondary subscription/filter or checkpoint limitations | Inspect `/admin/replication/topology` and `/admin/replication/coverage` |
| Cannot perform backup via HTTP | Backup/restore endpoints not exposed as public API | Use engine-level backup/restore APIs in controlled host/embedded workflows |
| PITR target fails despite backups existing | Archived WAL segments do not cover target window | Verify archive retention window and segment availability for backup WAL position |

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
| Restore + PITR | `RestoreIntegrationTests.cs`, `PitrFromArchivedWalTests.cs` | Pass | Medium/Strong | Restore and archive-assisted replay |
| Backup lifecycle retention/GC | `LifecycleIntegrationTests.cs`, `BackupLifecycleManagerTests.cs` | Pass | Strong | Chain-preservation and dry-run safety |
| Server persistence config path | `ConfigurationIntegrationTests.cs` | Pass | Medium | Validation and startup config behavior |
| TS persistence-adjacent API contracts | `../aouda-client-ts/tests/databases.test.ts`, `../aouda-client-ts/tests/admin.test.ts` | Pass | Medium | Client HTTP contract coverage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No first-class server integration tests for backup job endpoints | Public surface may be assumed by users but is absent | Add explicit server contract tests asserting backup routes are absent or gated until implemented | High |
| Limited cross-surface test: engine backup completion reflected through server metrics in realistic host wiring | Confirms observability parity and avoids stale assumptions | Add integration harness that runs backup engine in host context and asserts `/api/admin/metrics` backup counters | Medium |
| Per-database checkpoint sync limitation not guarded by dedicated regression test | Future changes could silently regress or mislead | Add replication integration test documenting and asserting current first-db checkpoint behavior until upgraded | Medium |
| No TS SDK tests for table durability override APIs (because surface missing) | API parity gap can drift unnoticed | Add TODO contract tests when table durability endpoints are introduced | Medium |
| No doc-driven automated verification artifact for this domain | Manual ledger can become stale | Add CI job summary artifact for storage/persistence verification suites | Medium |

## 2.18 Known gaps and undone work

- Public backup/restore orchestration surface:
  - Engine-level capabilities are mature, but server-level admin APIs for running/managing backup and restore are not first-class.
  - User impact: operators must use embedded/service code paths rather than standard HTTP admin contracts.
- Archive operationalization parity:
  - Archive config and worker exist, but integrated host lifecycle and operational surface are less complete than replication-hosted orchestration.
  - User impact: configuration may imply more turnkey behavior than current API/operator tooling exposes.
- Replication checkpoint sync:
  - `ReplicationHostedService` checkpoint path still uses first available database (deferred per-db checkpoint coverage).
  - User impact: multi-database checkpoint behavior requires careful operational expectations.
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

