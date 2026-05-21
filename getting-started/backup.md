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

Enable archiving in `appsettings.json`:

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

That is all that is needed for local backup. The server starts the archive worker automatically when `Enabled = true`.

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

| Field | Type | Default | Description |
|---|---|---|---|
| `Region` | `string?` | `null` | AWS region (e.g. `us-east-1`). Optional when using a custom `ServiceUrl` or when already set in the environment. |
| `ServiceUrl` | `string?` | `null` | Override endpoint for S3-compatible services. |
| `ForcePathStyle` | `bool` | `false` | Use path-style URLs. Required for MinIO and LocalStack. |
| `AccessKeyId` | `string?` | `null` | Explicit access key. Omit to use the standard AWS credential chain. |
| `SecretAccessKey` | `string?` | `null` | Explicit secret key. Omit to use the standard AWS credential chain. |

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

## Using the backup API directly (embedded / hosted usage)

When hosting Aouda in your own process, you can call backup and restore APIs directly:

```csharp
using Aouda.Engine.Storage.Backup;
using Aouda.Engine.Replication;

// Create the destination
await using var destination = ArchiveDestinationFactory.Create(
    "s3://my-aouda-backups/prod",
    new S3ArchiveOptions
    {
        Region = "us-east-1"
    });

// Run an incremental backup
var engine = new BackupEngine(destination);
var result = await engine.CreateBackupAsync(
    dataPath: "./data",
    new BackupOptions
    {
        Incremental = true,
        Parallelism = 4
    });

Console.WriteLine($"Backup {result.BackupId}: {result.NewBytes} new bytes uploaded");
```

### Restore from S3

```csharp
await using var destination = ArchiveDestinationFactory.Create(
    "s3://my-aouda-backups/prod",
    new S3ArchiveOptions { Region = "us-east-1" });

var restoreEngine = new RestoreEngine(destination);
var result = await restoreEngine.RestoreAsync(
    targetPath: "./data-restored",
    new RestoreOptions
    {
        BackupId = result.BackupId,
        VerifyIntegrity = true,
        CleanTargetDirectory = true
    });
```

### Point-in-time restore (PITR)

```csharp
var result = await restoreEngine.RestoreAsync(
    targetPath: "./data-pitr",
    new RestoreOptions
    {
        TargetTime = DateTime.UtcNow.AddHours(-2),
        WalPath = "./data/wal"
    });
```

---

## Backup REST API (server mode)

When running in server mode, trigger backups via the REST API (implemented in P16):

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
  -d '{ "cron": "0 2 * * *", "enabled": true }'
```

### TypeScript client

```typescript
// Trigger
await client.admin.backup.trigger();

// List
const backups = await client.admin.backup.list();

// Restore
await client.admin.backup.restore(backups[0].id);

// Schedule
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({ cron: "0 2 * * *", enabled: true });
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
| `PitrWindowException` | Target time outside the WAL retention window | Choose a target within `WalRetentionDays` or extend retention |
| `NotSupportedException` for `azure://` or `gcs://` | Azure/GCS not yet implemented | Use `s3://` or a local path |

---

## What's next

- [Functionality-Backup-And-Restore.md](Functionality-Backup-And-Restore.md) — full architecture, gap tracking, and test ledger.
- [Getting-Started.md](Getting-Started.md) — general Aouda getting-started guide.
- [P24-B task spec](../tasks/P24/P24-B-S3BackupProvider.md) — full S3 provider implementation spec.
