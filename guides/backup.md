---
title: "Backup and Restore"
nav_order: 8
parent: "Guides"
---

# Aouda Functionality: Backup and Restore

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-09-01

Coverage phases: P4 (Epic D + Epic I), P7 follow-up, P16 (HTTP/SDK), P24-B (S3 provider), BL-186 (recoverable restore + PITR)
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P7/`, `docs/tasks/P24/`, `docs/tasks/BL/`
Primary ADRs: `docs/decisions/0010-cluster-membership-replication.md`, `docs/decisions/0016-wal-lifecycle-management.md`, `docs/decisions/0044-recoverable-restore-and-point-in-time-recovery.md`
Related docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Write-Path-Durability.md`

## Start Here

- Need practical usage now: `2.3`, `2.10`, `2.12`
- Need implementation status honesty: `2.4`, `2.5`, `2.6`, `2.11`, `2.18`
- Need architecture/code grounding: `2.8`, `2.8.1`, `2.15`, `2.16`

---

## 2.1 Why this functionality exists

Backup and restore exists to protect data with predictable recovery:
- Incremental backups reduce copy cost using SHA256 content-addressable blobs.
- Restore recovers exact backup state.
- Lifecycle management controls archive growth with safe retention + garbage collection.

**Point-in-time recovery (PITR) is implemented.** Restore a backup, then replay WAL to the last
transaction whose commit time is at or before a target instant. Reach it over HTTP
(`POST /admin/backup/restore` with `targetTime`), `Aouda.Client`, and `@aouda/client`. The local
window is a **write-volume bound** (`MaxSlotWalKeepBytes`, typically 128 MB–2 GB of WAL since the
last backup) — not a number of days. Retention past that bound requires `Archive.Enabled` and a
destination; the archive worker runs when those are set. Studio's backup page still restores exact
backup points only. See `2.4`.

Scope note: exact backup/restore and PITR are both implemented end to end, including the public
server and client APIs. The MCP `aouda_backup_restore` tool stays exact-restore-only.

## 2.2 Discovery and navigation map

| If you need... | Go to |
|---|---|
| Defaults and "what happens if I do nothing" | `2.3` |
| Implemented vs missing surfaces | `2.4`, `2.6`, `2.11`, `2.18` |
| Phase-by-phase delivery evidence | `2.5` |
| How backup/restore actually runs | `2.8`, `2.8.1` |
| Config and tunables | `2.10` |
| Operational metrics/health | `2.13` |
| Troubleshooting | `2.14` |

Primary evidence sources:
- Reports: P4 D.1-D.5, P4 I.5-I.6 in `docs/tasks/P4/*-Report.md`
- Code: `src/Aouda.Engine.Storage/Backup/*`, `src/Aouda.Engine.Storage/WalIntegration/Archive/*`, `src/Aouda.Engine.Wal/Retention/*`
- Server observability: `src/Aouda.Server/Metrics/*`, `src/Aouda.Server/Health/BackupHealthCheck.cs`
- Tests: `tests/Aouda.Engine.Storage.Tests/Backup/*`, server metrics/health tests
- Backlog: `docs/BACKLOG-ARCHIVE.md` (BL-186 closed); remaining follow-ups BL-332 (Studio PITR UI), BL-023 (harness)

## 2.3 Defaults and zero-config behavior

| Default | Value | Impact |
|---|---|---|
| `ArchiveConfig.Enabled` | `false` | Archiving off unless enabled |
| `ArchiveConfig.WalRetentionDays` | `7` | How long archived WAL is kept; consumed by the archive worker |
| `ArchiveConfig.RequireArchiveBeforeDelete` | `false` | If true, local WAL is not pruned until it has been archived (rejected at startup unless archive is enabled and destinationed) |
| `BackupOptions.Incremental` | `true` | Uses incremental chain by default |
| `BackupOptions.Parallelism` | `4` | Parallel uploads |
| `BackupOptions.ManifestFormat` | `Auto` | Auto flat/hierarchical |
| `RestoreOptions.VerifyIntegrity` | `true` | SHA verification on restore |
| `RestoreOptions.CleanTargetDirectory` | `true` | Clean restore target by default |
| `LifecycleOptions.Execute` | `false` | Dry-run by default |
| `RetentionPolicy.PreserveIncrementalChains` | `true` | Protects base chains |
| `HealthThresholds.BackupIntervalHours` | `24` | Backup health warning threshold |

Zero-config reality:
- No automatic public backup scheduling endpoint is exposed by server controllers.
- Engine APIs are available for embedded/hosted usage.
- Metrics/health endpoints are available for observability.

## 2.4 Availability status

### Implemented now
- `BackupManifest`/`BackupFile` + SHA256 dedup model.
- `IArchiveDestination` + `LocalArchiveDestination`.
- `S3ArchiveDestination` (AWS S3 and S3-compatible services, e.g. MinIO, LocalStack). ← **P24-B**
- `BackupEngine` incremental backup orchestration.
- `RestoreEngine` exact restore **and** point-in-time restore (transaction-commit granularity).
- `BackupLifecycleManager` retention + GC.
- WAL slot integration for backup, system, and archive consumers. Backup records a real per-database WAL position; a position of `0` means *unknown* and that backup is exact-restore-only.
- `WalArchiveWorker` runs when `Archive.Enabled` is true and a destination is set (standalone `Archive`, or a replica-set Backup node's `ThisNode.Archive`).
- Backup metrics, WAL/PITR counters on `GET /api/metrics`, `aouda db inspect` `earliestRecoverablePitrPosition`, and an archive-not-advancing health check.
- HTTP restore with optional `targetTime`; `GET /admin/backup/list` `pitrEligible`; both SDKs.

### Partial / host-only

- Engine-host direct APIs (`BackupEngine`, `RestoreEngine`, `BackupLifecycleManager`) are also available for embedded/custom host usage alongside the server REST API.
- Studio's backup page restores exact catalog points only — WAL-level PITR is HTTP/SDK, not this UI.
- The MCP `aouda_backup_restore` tool is exact-restore-only.

### Not implemented

- Azure Blob Storage and Google Cloud Storage archive destinations (`azure://` / `gcs://` throw `NotSupportedException`).
- `aouda backup create/list/restore` CLI subcommands.
- Branches: branch engines open with WAL off and sit outside backup/PITR.
- Sub-commit (row-level) PITR — the finest boundary is a transaction commit.

## 2.5 Phase coverage matrix

| Phase | Delivered | Evidence |
|---|---|---|
| P4 Epic D | Manifest, destination abstraction, backup engine, exact restore, lifecycle/GC; a PITR code path was also written (later made to work by BL-186) | D.1-D.5 reports + code/tests |
| P4 Epic I | Backup/system slot integration; archive-assisted PITR scaffolding (worker later started by BL-186 S05) | I.5 and I.6 reports + code/tests |
| P7 follow-up | Durability scenario identifies missing server backup API | `BL-023`, `BackupRestoreScenario.cs` |
| P16 | `/admin/backup/*` REST + both SDKs for exact restore | P16-SA4, P16-H6 |
| P24-B | S3 archive destination + `S3ArchiveDestination` + factory wiring | P24-B-S3BackupProvider.md |
| BL-186 | Recoverable exact restore (WAL root + catalog re-base); per-database backup WAL position; archive positions in bytes; running archive worker; PITR on the recovery path; HTTP/SDK `targetTime`; recoverable-window metrics; restore divergence handshake | [ADR 0044](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0044-recoverable-restore-and-point-in-time-recovery.md), `docs/tasks/BL/BL-186-BackupPitrAndRetention-Overview.md` |

Note: Some task spec status rows remain stale ("Planned") while report+code show completion.

## 2.6 Capability coverage matrix

| Capability | Status | Evidence |
|---|---|---|
| Incremental SHA256 backups | Implemented | `BackupManifestBuilder`, backup tests |
| Local archive destination | Implemented | `LocalArchiveDestination` |
| S3 archive destination | Implemented (P24-B) | `S3ArchiveDestination`, `ArchiveDestinationFactory` |
| Backup orchestration + progress | Implemented | `BackupEngine` |
| Exact restore + integrity verification | Implemented | `RestoreEngine`; exact restore re-bases the WAL root and the catalog directory |
| PITR with local WAL and archived WAL | Implemented | HTTP `targetTime`; recovery-path replay at transaction-commit granularity; archive worker when configured |
| Retention + GC | Implemented | `BackupLifecycleManager` |
| WAL slot safety integration | Implemented for backup/system/archive | Backup slot is per-database and monotonic; position `0` does not pin a slot |
| Server backup execution endpoint | Implemented (P16) | P16-SA4, `/admin/backup/` |
| PITR over HTTP + both SDKs | Implemented (BL-186 S07) | `targetTime`, `pitr`, `pitrEligible`; MCP tool stays exact-restore-only |
| TS/.NET client backup execution APIs | Implemented (P16; PITR overload BL-186 S07) | `client.admin.backup.*` / `BackupAdminApi` |
| Azure Blob / GCS destinations | Missing | — |

## 2.7 Core concepts and mental model

- **Manifest is truth**: backup identity and file hashes live in `BackupManifest`.
- **Dedup is hash-based**: archive blob key is SHA256; path/name changes do not force re-upload.
- **Incremental chain**: `BasedOn` links backup lineage.
- **PITR is base backup + WAL replay** to a transaction-commit boundary. The local window is write volume since the last backup, not a duration. Archive extends that window when configured.
- **Safety-first lifecycle**: default dry-run and chain preservation avoid accidental data loss.
- **WAL slot coordination**: backup, system, and (when archiving) archive slots protect needed WAL from premature pruning. The backup slot is never exempted from the write-volume ceiling.

## 2.8 How Aouda implements it

Core types:
- Backup: `BackupEngine`, `BackupOptions`, `BackupResult`, `BackupProgress`
- Restore: `RestoreEngine`, `RestoreOptions`, `RestoreResult`, `PitrWindowException`
- Lifecycle: `BackupLifecycleManager`, `RetentionPolicy`, `LifecycleOptions`, `LifecycleResult`
- Archive: `IArchiveDestination`, `LocalArchiveDestination`, `S3ArchiveDestination`, `ArchiveDestinationFactory`

`ArchiveDestinationFactory` uses an opt-in provider registration pattern so that the
`AWSSDK.S3` dependency is isolated to the `Aouda.Engine.Storage.S3` package and does not
affect `Aouda.Embedded` users. `S3ArchiveDestination` is **not** available by default — it
requires calling `S3ArchiveProvider.Register()` at startup (done automatically in
`Aouda.Server`) or by adding a reference to `Aouda.Engine.Storage.S3` and calling
`S3ArchiveProvider.Register()` in your own host. See `Getting-Started-Backup.md §S3` for
usage details.
- WAL integration: `WalArchiveWorker` (started by `AoudaEngine.OpenAsync` when an archive destination is supplied), `RetentionWorker`, `WalSlotManager`

High-level flow:
1. Backup: checkpoint -> manifest build -> upload new blobs -> write manifest -> update backup slot.
2. Restore: resolve backup -> download/materialize -> verify integrity -> optional WAL replay.
3. PITR: restore the backup, stage a WAL root + `PITR_TARGET`, reopen, replay through crash recovery to the last commit `<= targetTime`.
4. Lifecycle: analyze keep/delete -> optional verify -> GC unreferenced blobs -> delete manifests.

## 2.8.1 Critical path walk-throughs

### A) Create incremental backup
- `BackupEngine.CreateBackupAsync(...)`
- Computes hashes, marks `IsNew`, uploads only new blobs, writes manifest.
- Updates `backup` slot position on success.
- Counters: `BackupOperations*`, `BackupBlobs*`, `BackupBytesUploaded`, `BackupSlotUpdatesTotal`.

### B) Restore exact backup
- `RestoreEngine.RestoreAsync(...)` with `TargetTime = null`.
- Rehydrates files, verifies hashes (default), returns restore stats.
- Counters: `RestoreOperations*`, `RestoreBlobsDownloaded`, verification counters.

### C) PITR (HTTP or engine)
- HTTP: `POST /admin/backup/restore` with `{ "backupId", "targetTime" }`, or omit `backupId` to pick the newest run at or before that time. Pre-flight refusals (future target, target at or before the backup, WAL position `0`, no run before the time) return `4xx` without stopping engines. See [HTTP API](../reference/http-api.md#post-adminbackuprestoreid).
- Engine: `RestoreEngine.RestoreAsync` with `TargetTime` set **stages** the restore; replay happens on the next `AoudaEngine.OpenAsync`.
- Replay applies whole transactions only, through the crash-recovery path. Archived WAL is used when the local log no longer covers the window.
- Counters: `PitrSegmentsDownloaded`, `PitrFromArchiveTotal`, and the `pitr` block on the HTTP restore response.

### D) Retention + GC
- `BackupLifecycleManager.EnforceRetentionAsync(...)`.
- Builds keep/delete sets, computes referenced hashes, deletes unreferenced blobs/manifests when execute mode is on.
- Default mode is dry-run.

## 2.9 Why Aouda is different

| Area | Aouda approach | Impact |
|---|---|---|
| Incremental identity | SHA256 content addressing | Strong dedup and deterministic integrity |
| PITR architecture | Base backup + WAL replay to a transaction commit; local window is write volume | Shipped (BL-186); Studio UI is exact-restore-only |
| WAL deletion safety | Slot-managed boundaries | Lower risk of deleting required WAL |
| Manifest scalability | Flat + hierarchical formats | Handles larger backup catalogs |
| Lifecycle safety | Dry-run default + chain preservation | Safer operations |

## 2.10 Configuration and settings reference

Server/runtime:
- `AoudaServerOptions.Archive` (`ArchiveConfig`)
  - `Enabled` (default `false`)
  - `Destination` (required if enabled; `s3://bucket/prefix` or local path)
  - `WalRetentionDays` (default `7`) — archive retention; **not** the local PITR window
  - `RequireArchiveBeforeDelete` (default `false`) — only valid with enabled + destinationed archive
  - `S3` (`S3Config`) — optional, used when `Destination` is an `s3://` URI
    - `Region` — AWS region (e.g. `us-east-1`); optional when using custom `ServiceUrl`
    - `ServiceUrl` — override endpoint for S3-compatible services (MinIO, LocalStack, etc.)
    - `ForcePathStyle` — set `true` for MinIO and LocalStack (default `false`)
    - `AccessKeyId` / `SecretAccessKey` — explicit credentials; omit to use the standard AWS credential chain
- `AoudaServerOptionsValidator` validates archive settings when enabled.
- Backup health threshold: `HealthThresholds.BackupIntervalHours` (default `24`).

Engine operation options:
- Backup: `BackupOptions` (`Incremental`, `BaseBackupId`, `Parallelism`, `ManifestFormat`, `VerifyAfterUpload`)
- Restore: `RestoreOptions` (`BackupId`, `TargetTime`, `WalPath`, `Parallelism`, `VerifyIntegrity`, `CleanTargetDirectory`)
- Lifecycle: `RetentionPolicy` + `LifecycleOptions` (`Execute`, `VerifyBeforeDelete`, `OnlyDeleteBlobsOlderThan`)

WAL lifecycle defaults:
- `WalLifecycleOptions.Default` controls archive check interval, retention check interval, archive retention window, slot inactivity, and archive-before-delete behavior.

### ArchiveConfig activation and wiring examples

**These examples start a WAL archive worker** when `Enabled` is true and `Destination` is set.
`WalRetentionDays` is consumed. There is no `CheckpointIntervalHours` setting.

The local PITR window stays a write-volume bound even when archiving is off: it is
`MaxSlotWalKeepBytes` of WAL since the last backup, not a duration. Archiving extends recovery
beyond that bound.

The server binds `AoudaServerOptions` from `Aouda` config and validates archive settings during hosted service startup. In current startup wiring this happens through:
- `builder.Services.AddAoudaServer(builder.Configuration)`
- `builder.Services.AddOptions<AoudaServerOptions>().Bind(builder.Configuration.GetSection("Aouda"))`

#### Example A: standalone server with archive mode enabled (startup config — optional `appsettings.json` or `AOUDA_ARCHIVE__*` env vars)

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5000,
    "Archive": {
      "Enabled": true,
      "Destination": "C:\\aouda\\archive",
      "WalRetentionDays": 7
    }
  }
}
```

Behavior:
- Server runs in standalone mode when no replica set is configured.
- `AoudaServerOptionsValidator` fails startup if `Destination` is empty or retention values are invalid.
- `AoudaHostedService` stamps `DatabaseManager` with the effective archive config; each engine open starts a `WalArchiveWorker` next to `RetentionWorker`.

#### Example B: S3 archive destination — AWS credentials from standard chain

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5000,
    "Archive": {
      "Enabled": true,
      "Destination": "s3://my-aouda-backups/prod",
      "WalRetentionDays": 30,
      "S3": {
        "Region": "us-east-1"
      }
    }
  }
}
```

Credentials are resolved from the standard AWS chain (environment variables, `~/.aws/credentials`, EC2/ECS instance metadata). Passing `Region` is optional when the region is already set in the environment or credential profile.

#### Example C: S3-compatible service (MinIO / LocalStack)

```json
{
  "Aouda": {
    "Archive": {
      "Enabled": true,
      "Destination": "s3://my-bucket/aouda-archive",
      "S3": {
        "ServiceUrl": "http://localhost:9000",
        "ForcePathStyle": true,
        "AccessKeyId": "minioadmin",
        "SecretAccessKey": "minioadmin"
      }
    }
  }
}
```

`ForcePathStyle: true` is required for MinIO and LocalStack.

#### Example D: replica set backup node archive wiring (startup config)

```json
{
  "Aouda": {
    "ReplicaSet": {
      "Name": "prod-rs",
      "Members": [
        "aouda-a:5433",
        "aouda-b:5433",
        "aouda-dr:5433"
      ],
      "ThisNode": {
        "Address": "aouda-dr:5433",
        "Backup": true,
        "Archive": {
          "Enabled": true,
          "Destination": "s3://my-aouda-backups/prod-dr",
          "WalRetentionDays": 14,
          "S3": {
            "Region": "eu-west-1"
          }
        }
      }
    }
  }
}
```

Behavior:
- Node starts with backup role semantics (`ThisNode.Backup = true`).
- `ThisNode.Archive` is the effective archive config on a backup node and starts the same worker.

#### Example E: programmatic override at server creation time

```csharp
using Aouda.Engine.Replication;
using Aouda.Server.Configuration;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddAoudaServer(builder.Configuration);

// Optional runtime override (e.g., tests, dev host, one-off deployments)
builder.Services.Configure<AoudaServerOptions>(o =>
{
    o.Archive ??= new ArchiveConfig();
    o.Archive = new ArchiveConfig
    {
        Enabled = true,
        Destination = @"C:\aouda\archive",
        WalRetentionDays = 7
    };
});
```

This override path is the same pattern used by test/development hosts when they need to adjust `Aouda` options after base configuration binding.

## 2.11 API and CLI coverage reference

### Current public surfaces

- Server admin REST API (P16):
  - `POST /admin/backup/trigger` — trigger an immediate backup (returns 202 with result)
  - `GET /admin/backup/list` — list all available backups at the configured destination
  - `POST /admin/backup/restore/{id}` — exact restore by ID (optional `{ "targetTime" }` body for PITR)
  - `POST /admin/backup/restore` — body `{ "backupId"?, "targetTime"? }`; omit `backupId` with a `targetTime` to pick the newest run at or before that instant
  - `GET /admin/backup/schedule` — get the current backup schedule
  - `PUT /admin/backup/schedule` — set a backup schedule (5-field cron expression or `null` to disable)

- Observability HTTP:
  - `GET /api/admin/metrics`
  - `GET /api/admin/metrics/summary`
  - `GET /api/admin/metrics/{subsystem}`
  - `GET /health/detailed`

- Engine-host APIs (for embedded/custom host usage):
  - `BackupEngine.CreateBackupAsync/ListBackupsAsync/GetBackupAsync`
  - `RestoreEngine.RestoreAsync/ListBackupsAsync/FindBackupForPitrAsync/VerifyBackupAsync`
  - `BackupLifecycleManager.EnforceRetentionAsync/AnalyzeRetentionAsync/GarbageCollectAsync`

### .NET client (`client.Backup`)

Access via `AoudaClient.Backup` property.

```csharp
using Aouda.Client;
using Aouda.Client.Admin;

await using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5000",
    DatabaseName = "appdb",
    ServerAuth = new ServerAuthOptions { ApiKey = "mk_srv_..." }
});

// Trigger an immediate backup
var result = await client.Backup.TriggerAsync(new TriggerBackupRequest(Incremental: true));
Console.WriteLine($"Backup {result.BackupId}: {result.TotalBytes} total bytes, {result.NewBytes} new bytes");

// List all backups (newest first)
var list = await client.Backup.ListAsync();
foreach (var b in list.Backups)
    Console.WriteLine($"  {b.BackupId}  {b.CreatedUtc:u}  {b.TotalBytes / 1024} KB");

// Restore from a specific backup
var restoreResult = await client.Backup.RestoreAsync(list.Backups[0].BackupId);
Console.WriteLine($"Restored {restoreResult.FilesRestored} files, " +
                  $"integrity verified: {restoreResult.IntegrityVerified}");

// Point-in-time restore
await client.Backup.RestoreAsync(new RestoreBackupRequest(
    BackupId: list.Backups[0].BackupId,
    TargetTime: DateTimeOffset.Parse("2026-05-01T12:00:00Z")));

// Get and update the backup schedule
var schedule = await client.Backup.GetScheduleAsync();
// Set a daily schedule at 02:00 UTC; pass null CronExpression to disable
await client.Backup.SetScheduleAsync(schedule with { CronExpression = "0 2 * * *" });
```

### TypeScript client (`client.admin.backup`)

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
  serverAuth: { apiKey: "mk_srv_..." },
});

// Trigger backup
const result = await client.admin.backup.trigger({ incremental: true });
console.log(`Backup ${result.backupId}: ${result.newBytes} new bytes`);

// List backups
const list = await client.admin.backup.list();
for (const b of list.backups)
  console.log(`  ${b.backupId}  ${b.createdUtc}  ${b.totalBytes} bytes`);

// Restore exact backup
const restored = await client.admin.backup.restore(list.backups[0].backupId);
console.log(`Restored ${restored.filesRestored} files`);

// Point-in-time restore (last commit <= targetTime)
await client.admin.backup.restore({
  backupId: list.backups[0].backupId,
  targetTime: "2026-05-01T12:00:00Z",
});

// Schedule
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({ ...schedule, cronExpression: "0 2 * * *" });
```

### HTTP examples

```bash
# Trigger a backup (requires server-auth scope)
curl -s -X POST http://localhost:5000/admin/backup/trigger \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"incremental":true}'
# → 202 + TriggerBackupResponse

# List backups
curl -s http://localhost:5000/admin/backup/list \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "backups": [...] }

# Restore backup by id
curl -s -X POST "http://localhost:5000/admin/backup/restore/<backupId>" \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + RestoreBackupResponse

# Set a daily schedule at 02:00
curl -s -X PUT http://localhost:5000/admin/backup/schedule \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"cronExpression":"0 2 * * *","incremental":true}'
# → 200 + BackupSchedule
```

### Common error responses

| Status | Condition |
|--------|-----------|
| 202 | Trigger: backup completed |
| 400 | Trigger: invalid destination URI |
| 409 | Trigger or restore: a backup/restore is already in progress |
| 503 | Trigger or restore: archive not configured or engine not ready |
| 404 | Restore: backup ID not found |

### TypeScript observability example

```typescript
const snapshot = await client.admin.metrics.snapshot();
console.log(snapshot.backup.operationsCompleted);
const summary = await client.admin.metrics.summary();
console.log(summary.lastBackupHoursAgo);
```

### Missing / not yet implemented

| Intended capability | Status | Workaround |
|---------------------|--------|------------|
| `aouda backup create/list/restore` CLI subcommands | Not implemented | Use `curl` or client SDK against `/admin/backup/*` |
| Azure Blob Storage archive destination | Not implemented | Use `s3://` or local path |
| Google Cloud Storage archive destination | Not implemented | Use `s3://` or local path |

## 2.12 Scenario playbooks

### 1. Server-managed incremental backup via API

When using Aouda in server mode with the admin API:

```bash
# One-time: configure archive destination via env vars, optional appsettings, or Studio (see §2.10 and [Server configuration](server-configuration.md))
# Then trigger a backup via API
curl -s -X POST http://localhost:5000/admin/backup/trigger \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"incremental":true}'
# → 202 + { "backupId": "...", "totalBytes": ..., "newBytes": ..., ... }
```

Subsequent triggers with `"incremental":true` will only upload blobs that changed (SHA256 dedup). Monitor `newBytes` vs `totalBytes` to verify the incremental chain is working.

### 2. Embedded incremental backup (local)

In embedded/custom host scenarios, use `BackupEngine` directly:

```csharp
var destination = new LocalArchiveDestination("./archive");
var engine = new BackupEngine(aoudaEngine, destination);
var result = await engine.CreateBackupAsync(new BackupOptions());
Console.WriteLine($"Backup {result.BackupId}: {result.NewBytes} new bytes");
```

Repeat incremental backups and verify reduced `NewBytes` on each subsequent call.

### 3. Embedded incremental backup (S3)

```csharp
// Requires S3ArchiveProvider.Register() at startup (done automatically in Aouda.Server)
var destination = ArchiveDestinationFactory.Create("s3://my-bucket/my-db");
var engine = new BackupEngine(aoudaEngine, destination);
var result = await engine.CreateBackupAsync(new BackupOptions { Incremental = true });
```

### 4. Disaster restore to known backup (server API)

```bash
# List backups to find the ID
curl -s http://localhost:5000/admin/backup/list \
     -H "Authorization: Bearer mk_srv_..."

# Restore by ID
curl -s -X POST "http://localhost:5000/admin/backup/restore/<backupId>" \
     -H "Authorization: Bearer mk_srv_..."
# Server restarts the engine after a successful restore
```

### 5. Disaster restore to known backup (embedded)

```csharp
var result = await restoreEngine.RestoreAsync(new RestoreOptions
{
    BackupId = "<backupId>",
    VerifyIntegrity = true,   // default true — always verify on restore
    CleanTargetDirectory = true
});
Console.WriteLine($"Restored {result.FilesRestored} files, integrity verified: {result.IntegrityVerified}");
```

### 6. PITR restore (HTTP)

```bash
# Restore to a time (picks newest backup at or before the instant)
curl -s -X POST http://localhost:5000/admin/backup/restore \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"targetTime":"2026-05-01T12:00:00Z"}'
```

Or pass both `backupId` and `targetTime`. Replay stops at the last transaction commit `<= targetTime`.
A backup whose manifest recorded WAL position `0` is exact-restore-only (`400`). The response
includes a per-database `pitr` block. Studio's backup page does not offer this; use HTTP or an SDK.

Embedded equivalent: `RestoreOptions.TargetTime` set, then reopen the engine (replay is on open).
Do not pass a `WalPath` — it defaults to the database's own WAL root.

### 7. Retention policy rollout

```csharp
// Step 1: dry-run to see what will be deleted
var analysis = await lifecycleManager.AnalyzeRetentionAsync(retentionPolicy);
Console.WriteLine($"Would delete {analysis.ManifestsToDelete.Count} manifests");

// Step 2: execute with chain preservation safeguard
await lifecycleManager.EnforceRetentionAsync(retentionPolicy, new LifecycleOptions { Execute = true });
```

### 8. Scheduled backups via Studio

In the Studio backup management page (§7 of the Studio guide), you can set a cron schedule using the built-in cron builder. The schedule is persisted in `backup-config.json` and survives restarts.

## 2.13 Operations and observability

Key signals:
- Backup throughput/failures: `BackupOperations*`, `BackupBytesUploaded`
- Restore effectiveness: `RestoreOperations*`, verification counters
- PITR activity: `PitrSegmentsDownloaded`, `PitrFromArchiveTotal`; inspect `earliestRecoverablePitrPosition`
- Lifecycle reclamation: `LifecycleBytesReclaimed`, delete counters
- WAL archive health: `WalSegmentsArchivedTotal`, archive error counters

Health behavior:
- Backup component health is computed from backup perf counters and backup interval threshold.
- "not_configured" state is possible when no backup activity has started.

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | Resolution |
|---|---|---|
| `NotSupportedException` on `azure://` or `gcs://` URI | Azure/GCS not yet implemented | Use `s3://` or a local path |
| Missing blob during restore | Archive inconsistency or aggressive lifecycle policy | Run `VerifyBackupAsync`, review retention/GC decisions |
| `PitrWindowException` | Target time outside the local WAL window and the archive (or no PITR-eligible backup) | Take a newer backup, enable archiving, or pick a later `targetTime`. The local window is write volume since the last backup, not a duration |
| Health says stale backup | No recent successful backups | Ensure host invokes backups on schedule |
| Durability D.3 scenario skipped | Public backup endpoint absent | Expected until BL-023 is completed |
| S3 `AmazonServiceException` on first operation | Invalid bucket, region mismatch, or credential chain failure | Verify `Destination` URI, check IAM permissions, set `Region` or `ServiceUrl` explicitly |

## 2.15 Verification ledger

| Claim | Evidence |
|---|---|
| Incremental backup implemented | P4 D.3 report + `BackupEngine.cs` + backup tests |
| Exact restore and PITR implemented | P4 D.4/I.6 + BL-186 S03/S06/S07; `RestoreEngine`, HTTP `targetTime`, both SDKs |
| Lifecycle management implemented | P4 D.5 report + `BackupLifecycleManager.cs` + lifecycle tests |
| Slot integration implemented | P4 I.5 report + slot tests |
| Observability implemented | metrics/health code + server tests |
| S3 archive destination implemented | P24-B + `S3ArchiveDestination.cs` + unit/integration tests |
| Public backup execution API implemented | P16 SA4 + `/admin/backup/` controller + P16 tests |

## 2.16 Test coverage matrix

| Area | Test groups | Status |
|---|---|---|
| Manifest/build/serialization | backup manifest tests | Strong |
| Backup engine | engine/integration/parallel tests | Strong |
| Restore + replay | restore + replay tests | Strong |
| PITR (local WAL + archive) | `Bl186S06PitrRecoveryPathTests`, `Bl186S07PitrHttpTests`, `PitrFromArchivedWalTests` | Strong — production `HraRowBatch` WAL through recovery-path replay and HTTP |
| Lifecycle retention/GC | retention/lifecycle tests | Strong |
| S3 destination (unit) | `S3ArchiveDestinationTests` | Strong |
| S3 destination (integration/LocalStack) | `S3ArchiveDestinationIntegrationTests` | Skippable — requires `AOUDA_TEST_S3_URL` |
| Server observability | metrics + health tests | Moderate-Strong |

## 2.17 Testing gaps and proposed tests

- Add large-window PITR stress tests with many archived segments.
- Add Azure Blob / GCS fault-injection tests when those destinations ship.
- Add S3 end-to-end integration test: trigger → insert → S3 restore → query round-trip.

## 2.18 Known gaps and undone work

_Updated 2026-09-01 after BL-186 completion._

### Resolved gaps

- ~~BL-023: missing server backup/restore execution API~~ — ✅ **Resolved (P16 Epic A, task A.4)**: full REST API surface at `/admin/backup/` — trigger, list, restore, schedule (GET/PUT). Provider abstraction over `IArchiveDestination`. Scheduled backups via 5-field cron expressions. See `docs/tasks/P16/P16-SA4-Backup-Restore-APIs.md`.
- ~~No high-level backup/restore surface in `@aouda/client`~~ — ✅ **Resolved (P16 Epic H, task H.6)**: `client.admin.backup.trigger()`, `.list()`, `.restore(id)`, `.getSchedule()`, `.setSchedule()` — all typed.
- ~~Some task-spec status rows are stale~~ — ✅ **Resolved**: all P16 task specs updated to Complete status.
- ~~Cloud archive destinations (`s3://`, `azure://`, `gcs://`) pending~~ — ✅ **Partially resolved (P24-B)**: `S3ArchiveDestination` ships with full `IArchiveDestination` implementation, factory wiring, server config (`S3Config`), and unit + LocalStack integration tests. Azure Blob and GCS remain pending.

### New capabilities (P24-B)

- **S3 archive destination**: `s3://bucket/prefix` URIs accepted by `ArchiveDestinationFactory`.
- **S3-compatible services**: MinIO, LocalStack, and any S3-compatible endpoint via `ServiceUrl` + `ForcePathStyle`.
- **Standard AWS credential chain**: region/key/secret explicit config or environment/profile/instance-metadata chain.
- **Lazy client init**: factory `Create()` never throws on credential absence — client is created on first I/O call.

### Remaining gaps

- ~~Point-in-time recovery~~ — ✅ **Resolved (BL-186)**: PITR over HTTP and both SDKs; archive worker runs when configured; local window is write volume. See `2.4`.
- Azure Blob Storage and Google Cloud Storage archive destination implementations.
- `aouda backup create/list/restore` CLI subcommands (wrapping REST APIs) not yet implemented.
- Studio backup page has no PITR UI (exact restore only) — BL-332.
- Integration test: trigger → insert → S3 restore → query round-trip (deferred from P24-B).

## 2.20 HRA and mutable-tier table backup contract

_Added 2026-06-07 (MemTiering S12 — closes Gap C)._

### What is covered

An **exact backup** captures a point-in-time snapshot of every `DiskBacked` table that holds unbuffered rows in the Hot Row Accelerator (HRA). This means:

- **Never-sealing mutable-tier tables** (those with `MemoryIntent = Mutable` that never exceed the seal threshold) are **fully covered** by an exact backup. Their data lives entirely in HRA, and a `.hra` snapshot file is written for each such table at the backup checkpoint.
- **Partially-flushed tables** (HRA tail present alongside committed `.hot` segments) are also fully covered: the `.hot` segment files are captured by the standard filesystem scan, and the HRA tail is captured by the snapshot mechanism.
- `BackupFileType.HraSnapshot` manifest entries identify these files; they are content-addressed (SHA-256 + CRC-32) and deduplicated between incremental backup runs.

### What is exempt

- **`MemoryOnly` tables** produce no HRA snapshot. By design (ADR 0034), they write nothing to disk and lose their data on shutdown. They are invisible to backup and intentionally so.

### Exact restore

After blobs are downloaded, `RestoreEngine` writes a synthetic `clean_shutdown.marker` with `WalHeadPosition = 0` referencing the restored `.hra` files. When the engine opens the restored directory, `TryGracefulOpenAsync` detects the marker (both the marker's WAL head and the actual WAL head are 0 on a fresh restore) and loads the snapshots into HRA. The `.hra` files are consumed and deleted during open.

### PITR restore

For a `targetTime` restore, the HRA snapshot is the state at the backup WAL position — before the
target. `RestoreEngine` **deletes** the restored `.hra` files and stages a `PITR_TARGET`; the next
open replays `HraRowBatch` WAL through crash recovery to the last commit `<= targetTime`. No
`clean_shutdown.marker` is written for the PITR path. In-place restores carry live Hot segment
metadata the checkpoint cannot hold; a restore onto a foreign empty catalog does not (BL-334).

### Implementation reference

| Component | Role |
|---|---|
| `IHraSnapshotProvider` / `CompactionWorker` | Writes `.hra` snapshots at backup checkpoint; cleans them up afterward |
| `BackupEngine` | Calls `WriteBackupSnapshotsAsync` before WAL position is recorded; deletes snapshots in finally block |
| `BackupManifestBuilder` | Includes explicit `HraBackupSnapshotRef` entries as `HraSnapshot` manifest entries; does **not** scan the filesystem for stray `.hra` files |
| `RestoreEngine` | Exact restore: writes synthetic `clean_shutdown.marker`. PITR restore: deletes `.hra` files. |
| `AoudaEngine.TryGracefulOpenAsync` | Loads `.hra` snapshots on graceful-open path (unchanged; WAL head = 0 on fresh restore satisfies existing check) |

## 2.19 References

- `docs/dev/Functionality-Document-Template.md`
- `docs/dev/Functionality-HotCold-And-Memory.md`
- `docs/dev/Getting-Started-Backup.md` ← new practical how-to guide
- `docs/tasks/P4/P4-EpicD-Task1-BackupManifest-Report.md`
- `docs/tasks/P4/P4-EpicD-Task2-ArchiveDestinationAbstraction-Report.md`
- `docs/tasks/P4/P4-EpicD-Task3-IncrementalBackupEngine-Report.md`
- `docs/tasks/P4/P4-EpicD-Task4-PointInTimeRestore-Report.md`
- `docs/tasks/P4/P4-EpicD-Task5-BackupLifecycleManagement-Report.md`
- `docs/tasks/P4/P4-EpicI-Task5-BackupIntegration-Report.md`
- `docs/tasks/P4/P4-EpicI-Task6-PitrEnhancement-Report.md`
- `docs/tasks/P24/P24-B-S3BackupProvider.md` ← P24-B task spec
- `docs/BACKLOG-ARCHIVE.md` (BL-186)
- `src/Aouda.Engine.Storage/Backup/*`
- `src/Aouda.Engine.Storage/WalIntegration/Archive/*`
- `src/Aouda.Engine.Wal/Retention/*`
- `src/Aouda.Engine.Diagnostics/Perf.cs`
- `src/Aouda.Server/Metrics/*`
- `src/Aouda.Server/Health/BackupHealthCheck.cs`

## 2.20 What is missing from this document?

- ~~Final public backup/restore HTTP/SDK contract details~~ — ✅ Now implemented. See `docs/tasks/P16/P16-SA4-Backup-Restore-APIs.md` and `docs/dev/Functionality-Cloud-And-Hub.md` §1.5 for full API reference.
- Cloud archive operational runbooks (destination implementations not shipped).
- Production benchmark envelopes for very large backup catalogs and long PITR timelines.
- Studio backup UI documentation now in `docs/dev/Functionality-Studio.md` §7.
