---
title: "Backup and Restore"
nav_order: 4
parent: "Getting Started"
---

# Getting Started: Backup and Restore

This guide shows how to configure and use Aouda's backup and restore capabilities. It covers both local filesystem destinations and cloud storage via AWS S3 (including S3-compatible services such as MinIO and LocalStack).

For the full backup subsystem reference — architecture, acceptance criteria, gap tracking, and test ledger — see [Functionality-Backup-And-Restore.md](Functionality-Backup-And-Restore.md).

---

## How backups work

Aouda uses **incremental, content-addressable backups**:

1. A checkpoint is taken and a manifest is built — it lists every file and its SHA256 hash.
2. Only blobs whose hash has not been uploaded before are written to the destination.
3. The manifest is written last; it is the single source of truth for a backup.
4. Restore verifies SHA256 hashes by default (configurable).

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
      "CheckpointIntervalHours": 24,
      "WalRetentionDays": 7
    }
  }
}
```

That is all that is needed for local backup. **`Enabled = true` does not start a WAL archive
worker** — nothing in the current release constructs one, so no WAL segment is ever uploaded to
`Destination` regardless of this setting. `CheckpointIntervalHours` and `WalRetentionDays` are
validated but not consumed by anything today. Exact backup/restore works independently of this
setting; point-in-time restore does not work in this release — see
[Backup and Restore](../guides/backup.md#24-availability-status).

---

## Quick start: S3 backup

### AWS S3 with standard credential chain

```json
{
  "Aouda": {
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

`ForcePathStyle: true` is required for MinIO and LocalStack — they use path-style URLs (`http://host:port/bucket/key`) rather than virtual-hosted URLs (`http://bucket.host:port/key`).

### Replica set backup node on S3

```json
{
  "Aouda": {
    "ReplicaSet": {
      "Name": "prod-rs",
      "Members": ["aouda-a:5433", "aouda-b:5433", "aouda-dr:5433"],
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
[Getting Started: Option C — hosting in your own app](Getting-Started.md#option-c-hosting-in-your-own-aspnet-application)),
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

> **Note on PITR: not implemented in this release.** Point-in-time restore requires replaying WAL
> records after loading a backup, but the WAL archive worker that would keep archived WAL around
> for replay is never started, no server or client API accepts a restore target time, and the
> local-WAL replay path does not apply real production WAL frames correctly. `WalRetentionDays`
> is validated but has no effect on anything today. Track BL-186 (this repo's engine tracker) and
> [ADR 0044](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0044-recoverable-restore-and-point-in-time-recovery.md)
> for the plan to ship it. Exact restore (below) is unaffected and works today.

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

# Restore a specific backup
curl -X POST http://localhost:5000/admin/backup/restore/<backup-id> \
  -H "Authorization: Bearer <admin-token>"

# Get or update backup schedule
curl http://localhost:5000/admin/backup/schedule \
  -H "Authorization: Bearer <admin-token>"

curl -X PUT http://localhost:5000/admin/backup/schedule \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "cronExpression": "0 2 * * *", "incremental": true }'
```

### TypeScript client

```typescript
// Trigger
await client.admin.backup.trigger();

// List — returns { backups: BackupSummary[], warning?: string }
const response = await client.admin.backup.list();
const backups = response.backups;

// Restore — pass backupId (string), not a numeric index
await client.admin.backup.restore(backups[0].backupId);

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
| `PitrWindowException` | PITR is not implemented in this release (see the note above) — this is the *best*-case failure; more commonly no archive exists at all because the archive worker never runs | Not currently resolvable; track BL-186 |
| `NotSupportedException` for `azure://` or `gcs://` | Azure/GCS not yet implemented | Use `s3://` or a local path |

---

## What's next

- [Functionality-Backup-And-Restore.md](Functionality-Backup-And-Restore.md) — full architecture, gap tracking, and test ledger.
- [Getting-Started.md](Getting-Started.md) — general Aouda getting-started guide.
- [P24-B task spec](../tasks/P24/P24-B-S3BackupProvider.md) — full S3 provider implementation spec.
