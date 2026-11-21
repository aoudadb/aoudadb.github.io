---
title: "Backup and Restore"
nav_order: 4
parent: "Getting Started"
---

# Getting Started: Backup and Restore

This guide shows how to configure and use Aouda's backup and restore capabilities. It covers both local filesystem destinations and cloud storage via AWS S3 (including S3-compatible services such as MinIO and LocalStack).

For what a backup holds, what a restore returns, retention and the error codes, see [Backup and Restore](../guides/backup.md). To bring data back on another host, see [Restore to a new host](../guides/restore-to-a-new-host.md). A dump is not a backup: [Dump and load](../guides/dump-load.md).

---

## How backups work

Aouda uses **incremental, content-addressable backups**:

1. The server takes one **fence** — a cut that a transaction in its commit section finishes before. Writers wait for it (at most 5 seconds) and are never failed by it, so **a backup needs no quiesced database** (**BL-337, next train**).
2. For every database, a manifest is built — it lists every file and its SHA256 hash — and only blobs whose hash has not been uploaded before are written to the destination.
3. The manifests are written per database and a **set record** is written last: a backup is one set of every database, and a set is complete only when its record is there.
4. Restore verifies SHA256 hashes by default. A restore returns the backup exactly, or — with a `targetTime` — the last transaction that committed at or before that instant. Rows that were only in a write buffer when the backup ran come back too (**BL-1440, next train**).

The same model works for both local and S3 destinations — only the destination implementation changes.

---

## Quick start: local backup

For local development, enable archiving in an optional `appsettings.json` or via environment variables (`AOUDA_ARCHIVE__ENABLED`, `AOUDA_ARCHIVE__DESTINATION`, … — nested keys use `__`). Production installs typically use Studio, `/admin/config`, or env vars — see [Server configuration](../guides/server-configuration.md#21-environment-variable-naming-aouda_).

`appsettings.json` example (local dev):

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Archive": {
      "Enabled": true,
      "Destination": "C:\\aouda\\archive",
      "WalRetentionDays": 7
    }
  }
}
```

That is all that is needed for local backup. **`Enabled = true` with a `Destination` starts the WAL
archive worker.** Archived WAL extends point-in-time recovery beyond the local write-volume window.
`WalRetentionDays` is how long archived WAL is kept — it is not the local PITR window (that is
write volume since the last backup). Exact restore and PITR over HTTP/SDK both work — see
[Backup and Restore](../guides/backup.md#1-what-is-and-is-not-available).

---

## Quick start: S3 backup

### AWS S3 with standard credential chain

```json
{
  "Aouda": {
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

Credentials are resolved from the standard AWS chain in order:

1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`).
2. `~/.aws/credentials` profile.
3. EC2/ECS instance metadata (IAM role attached to the host or task).

`Region` is optional when already set in the environment or credential profile, but setting it explicitly avoids region-detection latency.

### S3-compatible services (MinIO, LocalStack)

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

The `minioadmin` keys are the defaults of a **throwaway MinIO or LocalStack container**; never write a real credential into a file (use the credential chain or an environment variable).

`ForcePathStyle: true` is required for MinIO and LocalStack — they use path-style URLs (`http://host:port/bucket/key`) rather than virtual-hosted URLs (`http://bucket.host:port/key`).

---

## S3 configuration reference

| Field | Type | Default | Allowed values | Description |
|---|---|---|---|---|
| `Region` | `string?` | `null` | `null` (resolve from environment); or any AWS region code string (e.g. `us-east-1`, `eu-west-1`) | AWS region. Optional when using a custom `ServiceUrl` or when already set in the environment. |
| `ServiceUrl` | `string?` | `null` | `null` (use standard AWS endpoint); or any valid HTTP/HTTPS URL string | Override endpoint for S3-compatible services. |
| `ForcePathStyle` | `bool` | `false` | `true`, `false` | Use path-style URLs. Required for MinIO and LocalStack. |
| `AccessKeyId` | `string?` | `null` | `null` (use credential chain); or any AWS access key ID string | Explicit access key. Omit to use the standard AWS credential chain. |
| `SecretAccessKey` | `string?` | `null` | `null` (use credential chain); or any AWS secret key string | Explicit secret key. Omit to use the standard AWS credential chain. |

---

## URI format

```
s3://bucket-name
s3://bucket-name/optional/key/prefix
```

- The bucket must already exist.
- The key prefix is optional. Multiple databases can share a bucket by using different prefixes.
- All comparisons are case-insensitive: `S3://` and `s3://` are equivalent.

---

## Triggering backup programmatically (hosted usage)

When you host Aouda inside your own ASP.NET Core application using `AddAoudaServer()` (see
[Getting Started: Option C — hosting in your own app](index.md#option-c-hosting-in-your-own-aspnet-application)),
you can trigger backups directly through the DI container instead of going over HTTP.

Resolve `IBackupManagementService` from the application's DI container and call `TriggerBackupAsync`:

```csharp
using Aouda.Server.Models;
using Aouda.Server.Services;

// Resolve the backup service from DI (e.g. from a controller, minimal-API handler, or hosted service)
var backupService = app.Services.GetRequiredService<IBackupManagementService>();

var result = await backupService.TriggerBackupAsync(
    new TriggerBackupRequest(
        Destination: null,    // null = use configured destination from appsettings
        Incremental: true,
        BaseBackupId: null),
    cancellationToken);

switch (result)
{
    case TriggerBackupResult.Success s:
        Console.WriteLine($"Backup {s.Response.BackupId}: {s.Response.NewBytes} new bytes uploaded");
        break;
    case TriggerBackupResult.Conflict c:
        Console.WriteLine($"Backup skipped — already in progress: {c.Message}");
        break;
    case TriggerBackupResult.InvalidDestination e:
        Console.WriteLine($"Destination error: {e.Message}");
        break;
}
```

`IBackupManagementService` is registered by `AddAoudaServer()`. It handles concurrency control (prevents
two simultaneous backups), resolves the configured destination, and calls the underlying engine. The
result is a discriminated union — handle all cases so your code does not silently swallow errors.

For server mode (running Aouda standalone or via Docker), use the REST API or TypeScript client shown
above — you do not need to host Aouda inside your own process.

To list backups and restore from a specific snapshot, use `ListBackupsAsync` and `RestoreAsync`:

```csharp
// List backups — returns { Backups: BackupSummaryDto[], Warning?: string }
var list = await backupService.ListBackupsAsync(cancellationToken);
foreach (var backup in list.Backups)
{
    Console.WriteLine($"{backup.BackupId}  created {backup.CreatedUtc:u}  {backup.TotalBytes / 1024 / 1024} MB");
}

// Restore from a specific backup ID
var restoreResult = await backupService.RestoreAsync(list.Backups[0].BackupId, cancellationToken);
if (restoreResult is RestoreBackupResult.Success s)
    Console.WriteLine($"Restored {s.Response.FilesRestored} files in {s.Response.DurationSeconds:F1}s");
```

> **Point-in-time recovery.** Pass `targetTime` on restore (HTTP body, `RestoreBackupRequest`,
> `@aouda/client` `restore({ backupId, targetTime })`, or `aouda backup restore --target-time`). Replay stops at the last transaction commit
> at or before that instant — a commit boundary, nothing finer. The local window is write volume since the last backup, not a number
> of days — enable `Archive` to keep WAL beyond that. A backup of a database without a WAL (`unlogged`, `memory`) is
> exact-restore-only. The MCP `aouda_backup_restore` tool restores exactly only. See
> [Backup and Restore](../guides/backup.md#4-what-a-point-in-time-restore-returns)
> and [HTTP API](../reference/http-api.md#post-adminbackuprestoreid).

> **Restore with the build that took the backup.** A backup carries its own format (version 4 now). A build restores one version: a backup of
> another version is listed but refused at restore, naming both versions
> (`BACKUP_MANIFEST_REFUSED: found=3 expected=4 backup=<id> path=<manifest>`), before anything is written. Restore it with the build that took it, or take a
> new backup after the upgrade. See [Backup and Restore](../guides/backup.md#11-formats-and-upgrading).

---

## Backup REST API (server mode)

When running in server mode, trigger backups via the REST API:

```bash
# Trigger a backup
curl -X POST http://localhost:5000/admin/backup/trigger \
  -H "Authorization: Bearer <admin-token>"

# List backups
curl http://localhost:5000/admin/backup/list \
  -H "Authorization: Bearer <admin-token>"

# Restore a specific backup (exact)
curl -X POST http://localhost:5000/admin/backup/restore/<backup-id> \
  -H "Authorization: Bearer <admin-token>"

# Point-in-time restore (newest backup at or before the instant)
curl -X POST http://localhost:5000/admin/backup/restore \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"targetTime":"2026-05-01T12:00:00Z"}'

# One set: each database's cut, redo-start position and branches
curl http://localhost:5000/admin/backup/<backup-id> \
  -H "Authorization: Bearer <admin-token>"

# Retention (none by default), then a dry run of what it would delete
curl -X PUT http://localhost:5000/admin/backup/retention \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "keepLast": 5, "pitrWindow": "7.00:00:00" }'
curl -X POST http://localhost:5000/admin/backup/prune \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "execute": false }'

# Get or update backup schedule
curl http://localhost:5000/admin/backup/schedule \
  -H "Authorization: Bearer <admin-token>"

curl -X PUT http://localhost:5000/admin/backup/schedule \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "cronExpression": "0 2 * * *", "incremental": true }'
```

### Command line

```bash
export AOUDA_SERVER=http://localhost:5000 AOUDA_TOKEN=<admin-token>
aouda backup create                                   # one set, every database
aouda backup list
aouda backup show <backup-id>
aouda backup restore <backup-id>                      # exact
aouda backup restore --target-time 2026-05-01T12:00:00Z   # point in time: the newest set at or before it
aouda backup retention --keep-last 5 --pitr-window 7d     # none by default
aouda backup prune --dry-run
```

See the [CLI reference](../reference/cli.md#backup).

### TypeScript client

```typescript
// Trigger
await client.admin.backup.trigger();

// List — returns { backups: BackupSummary[], warning?: string }
const response = await client.admin.backup.list();
const backups = response.backups;

// Restore — pass backupId (string), not a numeric index
await client.admin.backup.restore(backups[0].backupId);

// Point-in-time restore
await client.admin.backup.restore({
  backupId: backups[0].backupId,
  targetTime: "2026-05-01T12:00:00Z",
});

// Schedule — uses cronExpression, not cron; incremental is a required boolean
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({
  cronExpression: "0 2 * * *",
  incremental: true,
});
```

---

## Running LocalStack integration tests

The `S3ArchiveDestinationIntegrationTests` suite tests the S3 implementation against a real (LocalStack) endpoint. The tests are skipped when `AOUDA_TEST_S3_URL` is not set.

### Start LocalStack

```bash
docker run --rm -p 4566:4566 localstack/localstack
```

### Run the integration tests

```bash
$env:AOUDA_TEST_S3_URL = "http://localhost:4566"
dotnet test tests/Aouda.Engine.Storage.Tests --filter "S3ArchiveDestinationIntegrationTests"
```

On Linux/macOS:

```bash
AOUDA_TEST_S3_URL=http://localhost:4566 \
  dotnet test tests/Aouda.Engine.Storage.Tests \
  --filter "S3ArchiveDestinationIntegrationTests"
```

The test suite creates a fresh bucket per test run, exercises the full `IArchiveDestination` contract (write, read, idempotency, delete, list, statistics, manifests), and tears everything down automatically.

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| `AmazonServiceException` on first S3 operation | Invalid bucket, wrong region, or missing credentials | Verify bucket name and `Region`; check IAM permissions; set `AccessKeyId` / `SecretAccessKey` for explicit credentials |
| `NoSuchBucket` | Bucket does not exist | Create the bucket first; Aouda does not create buckets automatically |
| Timeout connecting to MinIO | Wrong `ServiceUrl` or container not running | Check `ServiceUrl` and `ForcePathStyle: true` |
| Restore hash mismatch | Corrupted blob in S3 | Run `RestoreEngine.VerifyBackupAsync`; re-run backup to upload a fresh set |
| `PITR_WINDOW_UNAVAILABLE` (409) | The local WAL and the archive do not reach back to the backup's replay position, or the backup predates an exact restore and the archive has no WAL for it | Pick a target inside the window, take a newer backup, enable archiving, or restore exactly (no `targetTime`) |
| `BACKUP_MANIFEST_REFUSED` (400) | The backup is of another format (3, not 4) | Restore it with the build that took it, or take a new backup |
| `BACKUP_DESTINATION_UNAVAILABLE` (503) for `azure://` or `gcs://` | Azure and Google Cloud Storage are not supported | Use `s3://` or a local path |

---

## What's next

- [Functionality-Backup-And-Restore.md](../guides/backup.md) — full architecture, gap tracking, and test ledger.
- [Getting-Started.md](index.md) — general Aouda getting-started guide.
- [P24-B task spec](https://github.com/aoudadb/aouda/blob/main/docs/tasks/P24/P24-B-S3BackupProvider.md) — full S3 provider implementation spec.
