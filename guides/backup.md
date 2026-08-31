---
title: "Backup and Restore"
nav_order: 8
parent: "Guides"
---

# Aouda Functionality: Backup and Restore

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

Coverage phases: P4 (Epic D + Epic I), P7 follow-up, P24-B (S3 provider)
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P7/`, `docs/tasks/P24/`
Primary ADRs: `docs/decisions/0010-cluster-membership-replication.md`, `docs/decisions/0016-wal-lifecycle-management.md`
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

**Point-in-time recovery (PITR) is not implemented today.** The WAL archive worker that a working
PITR would depend on is never started by `Aouda.Server` or `Aouda.Embedded`, and no server, .NET,
or TypeScript API accepts a restore target time. See `2.4` and BL-186 in `docs/BACKLOG.md` (this
repo's engine tracker) for the defect cluster and the plan to ship it. Everything else in this doc
that mentions PITR describes the unfinished code surface, not a working capability — read `2.4`
before trusting any PITR claim further down.

Scope note: exact backup/restore is implemented end to end, including the public server/client
execution APIs. PITR is not.

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
- Backlog: `docs/BACKLOG.md` (BL-023)

## 2.3 Defaults and zero-config behavior

| Default | Value | Impact |
|---|---|---|
| `ArchiveConfig.Enabled` | `false` | Archiving off unless enabled |
| `ArchiveConfig.CheckpointIntervalHours` | `24` | Daily checkpoint cadence intent |
| `ArchiveConfig.WalRetentionDays` | `7` | Validated at startup; not consumed by anything today — the archive worker it would configure never runs (see `2.4`) |
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
- `RestoreEngine` exact restore.
- `BackupLifecycleManager` retention + GC.
- WAL slot integration for the backup and system consumers. (The archive slot exists in the model
  but is never created in production — see below.)
- Backup metrics and health exposure.

### Partial / host-only

- Engine-host direct APIs (`BackupEngine`, `RestoreEngine`, `BackupLifecycleManager`) are also available for embedded/custom host usage alongside the server REST API.

### Not implemented — despite code that suggests otherwise

- **Point-in-time recovery (PITR).** `RestoreEngine` and `WalReplayEngine` contain a PITR code
  path (`RestoreOptions.TargetTime`), but it cannot execute correctly in any deployment today:
  - **The WAL archive worker never runs.** `WalArchiveWorker` is constructed only in its own unit
    test — nothing in `Aouda.Server` or `Aouda.Embedded` starts one. Setting `Archive.Enabled = true`
    reaches a single log line and nothing else. No WAL segment is ever archived.
  - **No server or client API accepts a restore target time.** `POST /admin/backup/restore/{id}`
    takes only a backup ID. Neither the .NET client, the TypeScript client, nor the CLI can request
    PITR — see `2.11`.
  - **The local-WAL replay path does not find or apply production WAL.** Even bypassing the two
    gaps above via direct engine calls, WAL discovery expects a pre-segmentation file layout and
    the replay engine applies a WAL frame type production stopped writing years ago; it applies
    zero rows against real WAL.
  - Tracked as BL-186 in this repo's engine tracker (`docs/BACKLOG.md`), ratified to ship — see
    [ADR 0044](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0044-recoverable-restore-and-point-in-time-recovery.md).
    Until it ships, treat every PITR-shaped code path in this document as unfinished, not usable.
- Azure Blob Storage and Google Cloud Storage archive destinations.
- `aouda backup create/list/restore` CLI subcommands.

## 2.5 Phase coverage matrix

| Phase | Delivered | Evidence |
|---|---|---|
| P4 Epic D | Manifest, destination abstraction, backup engine, exact restore, lifecycle/GC; a PITR code path was also written but does not work (see `2.4`) | D.1-D.5 reports + code/tests |
| P4 Epic I | Backup/system slot integration; an archive-assisted PITR code path was also written but the archive worker it depends on is never started (see `2.4`) | I.5 and I.6 reports + code/tests |
| P7 follow-up | Durability scenario identifies missing server backup API | `BL-023`, `BackupRestoreScenario.cs` |
| P24-B | S3 archive destination + `S3ArchiveDestination` + factory wiring | P24-B-S3BackupProvider.md |

Note: Some task spec status rows remain stale ("Planned") while report+code show completion.

## 2.6 Capability coverage matrix

| Capability | Status | Evidence |
|---|---|---|
| Incremental SHA256 backups | Implemented | `BackupManifestBuilder`, backup tests |
| Local archive destination | Implemented | `LocalArchiveDestination` |
| S3 archive destination | Implemented (P24-B) | `S3ArchiveDestination`, `ArchiveDestinationFactory` |
| Backup orchestration + progress | Implemented | `BackupEngine` |
| Exact restore + integrity verification | Implemented | `RestoreEngine`, restore tests |
| PITR with archived WAL | **Not implemented** — code path exists, cannot execute (see `2.4`) | BL-186 analysis; `PitrFromArchivedWalTests` exercises hand-built fixtures, not the production path (see `2.16`) |
| Retention + GC | Implemented | `BackupLifecycleManager` |
| WAL slot safety integration | Implemented for backup/system; archive slot is never created in production | I.5 report, slot tests |
| Server backup execution endpoint | Implemented (P16) | P16-SA4, `/admin/backup/` |
| TS/.NET client backup execution APIs | Implemented (P16) | P16-H6, `client.admin.backup.*` |
| Azure Blob / GCS destinations | Missing | — |

## 2.7 Core concepts and mental model

- **Manifest is truth**: backup identity and file hashes live in `BackupManifest`.
- **Dedup is hash-based**: archive blob key is SHA256; path/name changes do not force re-upload.
- **Incremental chain**: `BasedOn` links backup lineage.
- **PITR is designed as base backup + WAL replay**, but is not implemented — see `2.4`.
- **Safety-first lifecycle**: default dry-run and chain preservation avoid accidental data loss.
- **WAL slot coordination**: the backup and system slots protect needed WAL from premature pruning
  today; the archive slot is part of the same model but is never created in production, so it
  protects nothing yet.

## 2.8 How Aouda implements it

Core types:
- Backup: `BackupEngine`, `BackupOptions`, `BackupResult`, `BackupProgress`
- Restore: `RestoreEngine`, `RestoreOptions`, `RestoreResult`, `WalReplayEngine`, `PitrWindowException`
- Lifecycle: `BackupLifecycleManager`, `RetentionPolicy`, `LifecycleOptions`, `LifecycleResult`
- Archive: `IArchiveDestination`, `LocalArchiveDestination`, `S3ArchiveDestination`, `ArchiveDestinationFactory`

`ArchiveDestinationFactory` uses an opt-in provider registration pattern so that the
`AWSSDK.S3` dependency is isolated to the `Aouda.Engine.Storage.S3` package and does not
affect `Aouda.Embedded` users. `S3ArchiveDestination` is **not** available by default — it
requires calling `S3ArchiveProvider.Register()` at startup (done automatically in
`Aouda.Server`) or by adding a reference to `Aouda.Engine.Storage.S3` and calling
`S3ArchiveProvider.Register()` in your own host. See `Getting-Started-Backup.md §S3` for
usage details.
- WAL integration: `WalArchiveWorker` (code exists; never constructed by `Aouda.Server` or
  `Aouda.Embedded` — see `2.4`), `RetentionWorker`, `WalSlotManager`

High-level flow:
1. Backup: checkpoint -> manifest build -> upload new blobs -> write manifest -> update backup slot.
2. Restore: resolve backup -> download/materialize -> verify integrity -> optional WAL replay.
3. PITR archive path (not functional — see `2.4`): validate archive window -> download/decompress segments -> replay to target.
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

### C) PITR using archive — not functional today (see `2.4`)
- `RestoreEngine.RestoreAsync(...)` with `TargetTime` is the intended call shape.
- In production this fails before it can help: there is no archived WAL to validate a window
  against (the archive worker never ran), and the WAL replay path underneath it does not apply
  real production WAL frames even when driven directly.
- Counters `PitrSegmentsDownloaded`, `PitrBytesDownloaded`, `WalReplay*` exist but stay at zero.

### D) Retention + GC
- `BackupLifecycleManager.EnforceRetentionAsync(...)`.
- Builds keep/delete sets, computes referenced hashes, deletes unreferenced blobs/manifests when execute mode is on.
- Default mode is dry-run.

## 2.9 Why Aouda is different

| Area | Aouda approach | Impact |
|---|---|---|
| Incremental identity | SHA256 content addressing | Strong dedup and deterministic integrity |
| PITR architecture | Designed as built-in backup + archived WAL replay | **Not shipped yet** — see `2.4` |
| WAL deletion safety | Slot-managed boundaries | Lower risk of deleting required WAL |
| Manifest scalability | Flat + hierarchical formats | Handles larger backup catalogs |
| Lifecycle safety | Dry-run default + chain preservation | Safer operations |

## 2.10 Configuration and settings reference

Server/runtime:
- `AoudaServerOptions.Archive` (`ArchiveConfig`)
  - `Enabled` (default `false`)
  - `Destination` (required if enabled; `s3://bucket/prefix` or local path)
  - `CheckpointIntervalHours` (default `24`)
  - `WalRetentionDays` (default `7`)
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

**These examples configure a WAL archive worker that does not exist yet.** `Archive.Enabled = true`
passes startup validation and is logged, but no `WalArchiveWorker` is started, so nothing is
uploaded and no PITR window opens. The examples below are accurate about *validated configuration
shape*; do not read them as evidence that archiving activates. See `2.4`.

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
      "CheckpointIntervalHours": 24,
      "WalRetentionDays": 7
    }
  }
}
```

Behavior:
- Server runs in standalone mode when no replica set is configured.
- `AoudaServerOptionsValidator` fails startup if `Destination` is empty or interval/retention values are invalid.
- **`ReplicationHostedService` does not start an archive worker.** Its standalone-archive branch
  only logs `"Archive mode enabled. Destination: {Destination}"` and returns. No WAL segment is
  ever uploaded to `Destination` under any of the examples on this page.

#### Example B: S3 archive destination — AWS credentials from standard chain

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5000,
    "Archive": {
      "Enabled": true,
      "Destination": "s3://my-aouda-backups/prod",
      "CheckpointIntervalHours": 24,
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
          "CheckpointIntervalHours": 24,
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
- `ThisNode.Archive` is validated but, same as standalone, no archive worker is started from it.

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
        CheckpointIntervalHours = 12,
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
  - `POST /admin/backup/restore/{id}` — restore from a backup by ID; restarts engine after restore
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

// Restore
const restored = await client.admin.backup.restore(list.backups[0].backupId);
console.log(`Restored ${restored.filesRestored} files`);

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

### 6. PITR restore with archived WAL (embedded) — not functional today

```csharp
var result = await restoreEngine.RestoreAsync(new RestoreOptions
{
    TargetTime = DateTimeOffset.Parse("2026-05-01T12:00:00Z"),
    WalPath = "./data/wal",
    VerifyIntegrity = true
});
```

This is the intended call shape for PITR, not a working recipe — do not copy it into production
code expecting it to succeed. In every current deployment this either throws `PitrWindowException`
immediately (no archive exists, because the archive worker never ran — see `2.4`) or, if pointed at
a real local WAL directory instead, silently applies zero rows. Tracked as BL-186; see
[ADR 0044](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0044-recoverable-restore-and-point-in-time-recovery.md).

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
- PITR activity: `Pitr*`, `WalReplay*` — currently stay at zero; PITR is not implemented (`2.4`)
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
| `PitrWindowException` | Best case: target time outside available archive range. Worse and more likely: no archive exists at all, because `WalArchiveWorker` is never started in this release — this exception is not a sign that PITR is otherwise close to working (see `2.4`) | Not currently resolvable; track BL-186 |
| Health says stale backup | No recent successful backups | Ensure host invokes backups on schedule |
| Durability D.3 scenario skipped | Public backup endpoint absent | Expected until BL-023 is completed |
| S3 `AmazonServiceException` on first operation | Invalid bucket, region mismatch, or credential chain failure | Verify `Destination` URI, check IAM permissions, set `Region` or `ServiceUrl` explicitly |

## 2.15 Verification ledger

| Claim | Evidence |
|---|---|
| Incremental backup implemented | P4 D.3 report + `BackupEngine.cs` + backup tests |
| Exact restore implemented; PITR is not | P4 D.4/I.6 reports + `RestoreEngine.cs` (exact restore); BL-186 analysis (why PITR does not work despite the code path existing) |
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
| PITR archive | `PitrFromArchivedWalTests` and related fixtures | **Green but not meaningful** — they hand-build archive manifests and download synthetic blobs rather than driving `WalArchiveWorker` or real production WAL; the suite does not detect that PITR cannot run in production (BL-186 finding F-11) |
| Lifecycle retention/GC | retention/lifecycle tests | Strong |
| S3 destination (unit) | `S3ArchiveDestinationTests` | Strong |
| S3 destination (integration/LocalStack) | `S3ArchiveDestinationIntegrationTests` | Skippable — requires `AOUDA_TEST_S3_URL` |
| Server observability | metrics + health tests | Moderate-Strong |

## 2.17 Testing gaps and proposed tests

- Add server API contract tests once backup/restore execution endpoints exist.
- Add large-window PITR stress tests with many archived segments.
- Add Azure Blob / GCS fault-injection tests when those destinations ship.
- Add explicit deployment-mode tests for archive/retention worker wiring.
- Add S3 end-to-end integration test: trigger → insert → S3 restore → query round-trip.

## 2.18 Known gaps and undone work

_Updated 2026-05-18 after P24-B completion._

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

- **Point-in-time recovery does not work in any deployment**, despite a PITR code path existing in
  `RestoreEngine`/`WalReplayEngine` since P4. The WAL archive worker is never started, no API
  accepts a restore target time, and the local-WAL replay path applies a frame type production no
  longer writes. Tracked as BL-186 (`docs/BACKLOG.md`, this repo's engine tracker); ratified to
  ship — see [ADR 0044](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0044-recoverable-restore-and-point-in-time-recovery.md).
- Azure Blob Storage and Google Cloud Storage archive destination implementations.
- `aouda backup create/list/restore` CLI subcommands (wrapping REST APIs) not yet implemented.
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

This describes what the `TargetTime`-set code path is *designed* to do, not observed behavior —
PITR does not work end to end today (`2.4`). For PITR restores, the HRA snapshot represents the
state at the backup WAL position — before the target time. `RestoreEngine` **deletes** the restored
`.hra` files before WAL replay begins; a working WAL replay would then need to drive HRA state at
the target time from the `HraRowBatch` frames in the WAL. No `clean_shutdown.marker` is written.
The replay step is exactly what does not currently function (see `2.4`).

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
- `docs/BACKLOG.md` (BL-023)
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
