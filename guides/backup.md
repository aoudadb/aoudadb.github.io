---
title: "Backup and Restore"
nav_order: 8
parent: "Guides"
---

# Backup and Restore

Last updated: 2026-11-21 (Durability-1)

A backup is a copy of every database of the server in a destination you choose — a directory or an S3 bucket. A restore puts the
copy back, **exactly** as it was at the backup, or **to a point in time** after it by replaying the write-ahead log (WAL). This page
says what a backup holds, what a restore returns, what happens to retention, and what is not there.

- **Take a backup, test a restore on a second host, and set a retention policy.** The runbook for the second host is
  [Restore to a new host](restore-to-a-new-host.md).
- **A dump is not a backup.** [`aouda dump` / `aouda load`](dump-load.md) moves data across a format bump; it has no point in time.
- Durability levels and what each loses in a crash: [Write durability](write-durability.md).

## 1. What is and is not available

| Capability | Status |
|---|---|
| Incremental backups of every database of the server as one **set**, with an S3 or local destination | Available |
| Backup while the server takes writes (no quiesce) | Available (**BL-337, next train**) |
| Exact restore, against the server or offline into an empty directory | Available |
| Point-in-time restore (PITR) to a commit boundary, from the local WAL or the WAL archive | Available |
| Restore onto a new host from the destination alone | Available (**BL-334, next train**) |
| Schedule (cron) | Available |
| Retention policy (`keepLast`, `keepDays`, `pitrWindow`) and `aouda backup prune` | Available; **none by default** (**BL-1635, next train**) |
| `aouda backup` command line | Available (**Durability-1 S12, next train**) |
| Branches in a backup and in an exact restore | Available (**BL-335, next train**); a PITR drops them |
| Encryption of a backup | Not provided: it is the destination's (§9) |
| Azure Blob Storage and Google Cloud Storage destinations | Not supported (`azure://`, `gcs://` are refused) |
| Restore of one table, or to a time inside a transaction | Not supported: the finest point is a transaction's commit |
| One consistent cut across all databases of a server | Not supported: each database has its own cut |

## 2. What a backup is

- **One set per backup.** `aouda backup create` (or `POST /admin/backup/trigger`) backs up every database of the server — the auth
  database first — and writes the **set record** last. A set is **complete** only when its record is there; a set that one database
  failed is listed as incomplete and **refused** by a restore, never restored in part (**BL-1637, next train**). A set from a build
  before this release has no record and is listed incomplete.
- **No cross-database consistency.** Every database has its own cut. A write to two databases is not a unit across them.
- **Incremental by default.** Files are stored by SHA-256, so an unchanged file is stored once. An incremental backup records its base;
  `--full` uploads everything again. If the newest base is of an older backup format, the backup is taken in full.
- **It needs no quiesced database.** A backup under write load restores exactly. It takes one **fence** — a cut that a transaction in
  its commit section finishes before — and writers wait for it; they are never failed by it. The fence waits at most **5 seconds** for the commits in flight and is then held
  at most another 5 seconds while the cut is taken, so a writer waits at most about 10 seconds (**BL-337, next train**). The hold grows with
  the buffered rows to capture; it has not been measured at production scale (BL-1642). A backup that cannot take or hold the fence in
  time fails with `BACKUP_FENCE_TIMEOUT` (HTTP 503); retry it, and if it keeps failing, look for a long write that holds a commit section.
- **Rows in a write buffer are in the backup.** A row that was only in memory (the table's write buffer, or an edge or vector buffer)
  at the cut is written into the backup, and a point-in-time restore replays the log **from the redo-start position**, an earlier position than
  the cut, so that row comes back too (**BL-1440, next train**). Before this release a PITR dropped those rows.
- **Branches** are backed up with their parent and come back with an exact restore (§5.3).
- **What it holds.** Every column value of every table, and in an auth database the credential hashes. A backup is as sensitive as the
  data (§9).

## 3. Restore

There are two kinds.

**Exact restore** returns the database as of the backup's cut. Over HTTP `POST /admin/backup/restore/{id}` (or
`aouda backup restore <id>`) stops the engines, puts the files back, verifies their hashes and restarts. Offline,
`aouda backup restore <id> --to <empty directory> --from <destination>` writes a data directory with no server running; start the
server on it with `aouda start --data-path <dir>`.

- **A restored database keeps its durability level.** The level travels with the backup and a restore registers and opens the database at
  it; a declaration still wins (**BL-1168, next train**).
- **The first open after an exact restore takes longer**: it flushes the restored write buffers so the restored rows are durable
  (**BL-1625, next train**). A crash before it finishes loses nothing; the next open does it again.
- **A restore syncs what it wrote** before it reports success (**BL-1687, next train**).
- A restore **refuses** a set that is not complete, a set record or manifest of another format, a target time it cannot serve, a backup it
  cannot read and a point-in-time restore outside its archive window (§4.1), before it stops anything — a refused window changes nothing
  (**BL-1740, next train**).
- **Every blob is checked against its key as it is read** — its SHA-256 and its length, before the file gets its name: a backed-up file,
  the catalog, an archived WAL segment, a branch's files. A blob that does not match refuses the restore with `BACKUP_BLOB_DAMAGED` (409),
  naming the file and the set (**BL-1739, next train**); nothing is written under that file's name. `integrityVerified` in a successful
  response is therefore always `true`.
- **A restore that stops part-way leaves a database that refuses to open.** From its first change to its last step a restore marks the
  database `restore.incomplete`; a database that holds it is not opened (`RESTORE_INCOMPLETE`) — the server keeps it quarantined, an
  embedded open throws — until a restore of it completes (**BL-1739, BL-1740, next train**). A refused blob, a cancellation or a crash
  part-way therefore never leaves the old database's catalog over the backup's files: run the restore again, or restore another set.

**Point-in-time restore** — see §4.

### 3.1 What a restore does not bring back

- Anything outside the data directory: the declaration file (`aouda.json`) and keys set in the environment. Carry them as you do for
  any server.
- A database the set did not contain.

After a restore the server reconciles declared databases as it does at any start.

## 4. What a point-in-time restore returns

A point-in-time restore takes a backup, then replays the WAL to the **last transaction whose commit is at or before the target
instant** (`targetTime`).

- **Commit boundaries.** The log carries the time a transaction committed, nothing finer. A restore never lands in the middle of a
  transaction.
- **Rows buffered at the backup come back** (§2), and so do the buffered rows of tables created after it (**BL-1440, next train**).
- **Tables created after the backup come back** through any route — REST, a table an insert inferred, an edge table or a vector column,
  schema apply, Embedded — with one row per key; a materialized query defined after the backup comes back, rebuilt. Before this release a
  PITR across a created table could show two versions of an updated row, and a [formula](formulas.md) database then refused to open
  (**BL-1485, next train**).
- **A crash after a PITR** neither revives what the restore excluded nor loses later writes, and a later PITR honours the exclusion of
  the first (**BL-1626, next train**). Concurrent policy changes restore to the last (**BL-1524, next train**). A bulk load committed after the
  target is not committed after the restore (**BL-1168, next train**).
- **Bulk loads.** A `strict` load committed before the target is restored from the bulk-load store or from the archive; if its
  files are not there the restore is refused, naming the job (`PITR_BULK_LOAD_UNAVAILABLE`, HTTP 409) (**BL-1653, BL-1654, next train**).
  An `os` load made after the backup is **not** restored (BL-1717).
- **A table without a primary key** is exact up to the first delete or update, after the backup, of a row that the table flushed, bulk-loaded or
  merged after the backup. Past that instant the restore is refused with `PITR_KEYLESS_DELETE_UNRESOLVED`, naming the table and the instant, and
  the database stays quarantined until a new restore — to an earlier target or from a later backup. Give the table a primary key and every
  target is exact (**BL-1624, next train**).
- **Edge and vector writes** made after the target and before the next row commit are restored (a known limit, BL-1726).
- **A target at or before the backup** is refused (`BACKUP_TARGET_TIME_INVALID`, 400), naming both instants; so is a target in the future,
  and a set that is exact-restore-only (§4.1).
- **Without a `backupId`** the newest complete set that lies wholly at or before the target is chosen; `404` when there is none. If that set
  is exact-restore-only the restore is refused; an older set is not tried.

### 4.1 What a PITR needs

- **A PITR-eligible backup**: its manifest records a WAL root. A database at `unlogged` or `memory` has no WAL, so its backups are
  exact-restore-only (`pitrEligible: false`). A backup of a database that has a WAL root is eligible even at WAL position 0
  (**BL-1010, next train**).
- **WAL that covers the window.** The local WAL since the backup — bounded by write volume, not by days (`MaxSlotWalKeepBytes`) — or,
  past that, the **WAL archive** (`Aouda:Archive`, §6). A restore whose archive does not reach back to the backup's replay position is
  refused with `PITR_WINDOW_UNAVAILABLE` (409), never restored short (**BL-334, next train**). Every database's window is checked before
  any engine stops or any file changes, so a refused window leaves every database as it was (**BL-1740, next train**).
- **The WAL-root incarnation the backup was taken in.** An exact restore starts a new incarnation, so a PITR from a backup that
  predates it needs the archive, or a backup taken after the restore.
- **The archive's RPO for a host loss** is `Aouda:Archive:MaxUnarchivedSeconds` (default 60 seconds) plus one archive check (a minute):
  the active WAL segment is sealed and shipped when its oldest frame is that old (**BL-1657, next train**).
- **A level change that retires the WAL ends the window** at the change; see [Write durability](write-durability.md#changing-a-level).

### 4.2 Branches and a PITR

A point-in-time restore **drops every branch** of the databases it restores and names each one in the response (`droppedBranches`).
Restore exactly to keep them; a per-branch point in time is not available (**BL-335, next train**).

### 4.3 Onto another host

A PITR and an exact restore onto another host from the destination alone are supported: segment ids are not reissued and `.hot` rows come
back (**BL-334, next train**). A restored copy must archive to **its own** destination while its source still runs: two databases
archiving to one destination at the same time lose each other's archive-manifest entries. The runbook is
[Restore to a new host](restore-to-a-new-host.md).

## 5. Retention

Backups and the archive grow until you prune them. **There is no default policy: nothing is pruned** until you save one
(**BL-1635, next train**).

| Term | Keeps |
|---|---|
| `keepLast` | the newest N sets |
| `keepDays` | the sets of the last N days |
| `pitrWindow` | one base for a PITR to any instant of the window: the newest complete set at or before `now − window`. The sets after it are kept only if another term or the floor keeps them; the archive keeps the WAL from the base's redo-start |

- **The unit is the set**: a set is kept or deleted whole, and a kept set keeps its incremental bases.
- **The floor**: the newest complete, restorable set is always kept, whatever the policy says.
- **When it runs**: after every successful scheduled backup, and when you run `aouda backup prune` (or `POST /admin/backup/prune`).
  `--dry-run` prints the plan — each set, kept or deleted, with the rules that decided it — and deletes nothing.
- **An unreadable kept manifest withholds blob collection** in that database's destination for the pass; the plan says why.
- **The WAL archive is kept from the oldest listed backup's redo-start** (**BL-1636, next train**), so retention never prunes the log a
  listed backup's PITR needs. `Aouda:Archive:WalRetentionDays` (default 7) bounds archived WAL that no listed backup needs.

```bash
aouda backup retention --keep-last 5 --pitr-window 7d     # the whole policy: a term not given is not kept
aouda backup prune --dry-run
```

## 6. Configuration

Archive and the backup destination are server settings (`Aouda:Archive:*`; environment variables `AOUDA_ARCHIVE__*`; see
[Server configuration](server-configuration.md)).

| Setting | Default | Meaning |
|---|---|---|
| `Aouda:Archive:Enabled` | `false` | Runs the WAL archive worker. Needed for a PITR beyond the local WAL, and for restoring a PITR on a new host |
| `Aouda:Archive:Destination` | none | A local path or `s3://bucket/prefix`. Required when enabled; also the backups' destination unless the schedule names another. With none set at all, backups go to `<data path>/backups` — on the disk they protect, so not a backup against losing it |
| `Aouda:Archive:WalRetentionDays` | `7` | How long archived WAL is kept; not the local PITR window |
| `Aouda:Archive:MaxUnarchivedSeconds` | `60` | How old a WAL frame may get before its segment is sealed and shipped |
| `Aouda:Archive:RequireArchiveBeforeDelete` | `false` | Local WAL is not pruned until archived (needs `Enabled` and a destination) |
| `Aouda:Wal:Lifecycle:ArchiveCheckInterval` | 1 minute | How often the archive worker runs |
| `Aouda:Wal:Lifecycle:ReplicationSlotMaxInactivity` | 7 days | A slot unused this long logs a warning |
| `Aouda:Wal:Lifecycle:SlotPersistInterval` | 30 seconds | How often slot positions are saved |
| `Aouda:Wal:Lifecycle:EnablePruning` | `true` | Local WAL that every slot has passed is deleted |
| Retention | none | §5 |

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Archive": { "Enabled": true, "Destination": "/var/aouda/archive", "WalRetentionDays": 7 }
  }
}
```

S3 destination, credentials from the standard AWS chain (environment, `~/.aws/credentials`, instance metadata):

```json
{
  "Aouda": {
    "Archive": { "Enabled": true, "Destination": "s3://my-aouda-backups/prod", "S3": { "Region": "us-east-1" } }
  }
}
```

An S3-compatible service (MinIO, LocalStack) needs `ServiceUrl` and `ForcePathStyle`. The keys below are the defaults of a **throwaway
container**; never write a real credential into a file:

```json
{
  "Aouda": {
    "Archive": {
      "Enabled": true,
      "Destination": "s3://my-bucket/aouda-archive",
      "S3": { "ServiceUrl": "http://localhost:9000", "ForcePathStyle": true, "AccessKeyId": "minioadmin", "SecretAccessKey": "minioadmin" }
    }
  }
}
```

### 6.1 Schedule

`PUT /admin/backup/schedule` sets a five-field cron expression (`null` disables); Studio's backup page sets the same. The schedule and the
retention policy are saved in the server's settings and survive a restart.

```bash
curl -s -X PUT http://localhost:5000/admin/backup/schedule -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"cronExpression":"0 2 * * *","incremental":true}'
# → 200 {"cronExpression":"0 2 * * *","destination":"/var/aouda/archive","incremental":true}
```

## 7. The command line and the API

`aouda backup` takes the server from `--server` / `AOUDA_SERVER` and an operator key from `AOUDA_TOKEN` (or `--token`; an argument shows in the process list) (**Durability-1 S12, next train**).
Exit statuses: 0 done, 1 refused or failed, 64 misuse, 69 server unreachable or 5xx, 77 key refused, 78 (offline restore) the directory is not empty.

```bash
aouda backup create                    # one set, every database; --full for a full backup
aouda backup list                      # complete? PITR-eligible? which databases
aouda backup show <id>                 # per database: cut, redo-start, manifest version, branches
aouda backup restore <id>              # exact
aouda backup restore --target-time 2026-11-21T15:03:16Z                 # PITR; the newest set at or before the target
aouda backup restore <id> --to /srv/aouda-data --from /backups/aouda    # offline, into an empty directory
aouda backup prune --dry-run
aouda backup retention --keep-last 5 --pitr-window 7d
```

Every verb takes `--json`, and `--timeout` (default one hour for `create`, `restore` and `prune`, 30 seconds otherwise). The full option
list is in the [CLI reference](../reference/cli.md#backup). The routes, fields and error codes are in the
[HTTP API](../reference/http-api.md#backup-and-restore-admin-routes).

### HTTP

```bash
# Trigger a backup (an operator key; GET /api/auth/whoami names the principal)
curl -s -X POST http://localhost:5000/admin/backup/trigger -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"incremental":true}'
# → 202 {"backupId":"backup-2026-11-21-150259-e1638d21","totalBytes":87871,"newBytes":87871,...}

curl -s http://localhost:5000/admin/backup/list -H "Authorization: Bearer $KEY"        # → 200 {"backups":[...]}
curl -s http://localhost:5000/admin/backup/<backupId> -H "Authorization: Bearer $KEY"  # → 200, one set

# Exact restore
curl -s -X POST http://localhost:5000/admin/backup/restore/<backupId> -H "Authorization: Bearer $KEY"

# Point-in-time restore: the newest complete set at or before the target
curl -s -X POST http://localhost:5000/admin/backup/restore -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"targetTime":"2026-11-21T15:03:16Z"}'
```

### SDKs

```csharp
await using var client = new AoudaClient(new AoudaClientOptions { ServerUrl = "http://localhost:5000", DatabaseName = "appdb" });

var result = await client.Backup.TriggerAsync(new TriggerBackupRequest(Incremental: true));
var list = await client.Backup.ListAsync();
await client.Backup.RestoreAsync(new RestoreBackupRequest(
    BackupId: list.Backups[0].BackupId,
    TargetTime: DateTimeOffset.Parse("2026-11-21T15:03:16Z")));
```

```typescript
import { createAoudaClient } from "@aouda/client";
const client = createAoudaClient({ serverUrl: "http://localhost:5000", database: "appdb" });

const result = await client.admin.backup.trigger({ incremental: true });
const list = await client.admin.backup.list();
await client.admin.backup.restore({ backupId: list.backups[0].backupId, targetTime: "2026-11-21T15:03:16Z" });
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({ ...schedule, cronExpression: "0 2 * * *" });
```

The MCP `aouda_backup_restore` tool restores exactly only. Studio's backup page restores exact points; from the Studio release after 0.16.0 it also
restores to a point in time, edits retention, previews a prune, labels an incomplete set and shows each error with its remedy (**BL-332, next train**).
Point-in-time restore is available over HTTP, the CLI and both SDKs.

## 8. Operations

- **Metrics**: `GET /api/admin/metrics` carries backup counters, the `wal` block (`archiveSegmentsArchivedTotal`, `archiveErrorsTotal`,
  `pitrFromArchiveTotal`, and per database `wal.databases[]` with `slotMinPosition` and `slotMaxLagBytes`; the process-wide
  `slotMinPosition` is gone, **BL-329, next train**). `GET /api/admin/metrics/summary` has `lastBackupHoursAgo`.
- **Health**: `GET /health/detailed` reports a backup component (stale if no recent success; `not_configured` before any backup) and an archive
  that is not advancing.

## 9. Encryption, and who can read a backup

**Aouda does not encrypt a backup, the archive or a dump.** Encryption is the destination's: S3 server-side encryption, an encrypted volume.
A backup holds every column value and, in an auth database, credential hashes; protect the destination like the data. The server never
shows an S3 credential in a log, an error or a CLI line, and a database name that looks like a key is redacted in them (**BL-1607, next train**).

## 10. Errors

Every error the backup routes raise is a JSON body with `error` (the message), `code` and a string `remedy` (**BL-1637, next train**); a
refused key (401 / 403) has the authentication envelope instead. The ones you will meet:

| Symptom | Code and status | What to do |
|---|---|---|
| A backup, restore or prune is already running | `BACKUP_IN_PROGRESS` 409 | Wait, then retry |
| The backup could not take its fence | `BACKUP_FENCE_TIMEOUT` 503 | Retry; a less loaded server takes it |
| A buffer could not be sealed for the backup | `BACKUP_BUFFERS_UNSEALED` 503 | Retry |
| A branch could not be captured | `BACKUP_BRANCH_UNAVAILABLE` 409 | Repair or delete the branch the message names, retry |
| Restore of a set taken before this release | `BACKUP_SET_INCOMPLETE` 409: the set has no completion record | Restore it with the build that took it, or take a new backup after the upgrade |
| A set whose manifest is of another version | `BACKUP_MANIFEST_REFUSED` 400, `found=<n> expected=4 backup=<id> path=<manifest>` | Restore it with the build that took it |
| Restore of a set one database failed | `BACKUP_SET_INCOMPLETE` 409 | Restore another set; a prune removes it |
| A set record of another version | `BACKUP_SET_REFUSED` 400 | Restore with the build that took it |
| A target at or before the backup, or in the future; or a PITR of an exact-restore-only set | `BACKUP_TARGET_TIME_INVALID` 400 | Pick a target after the set's last cut, or restore the set exactly |
| The archive does not cover the window | `PITR_WINDOW_UNAVAILABLE` 409 | Nothing was changed (**BL-1740, next train**): pick a target inside the window, restore exactly, or point `--archive` at the archive's destination |
| A bulk load committed before the target is not in the store | `PITR_BULK_LOAD_UNAVAILABLE` 409 | Restore before the load's commit (the message names the job) or from a later backup |
| A keyless delete the restore cannot apply | `PITR_KEYLESS_DELETE_UNRESOLVED` 409 | Restore to before the instant named, or from a later backup |
| A damaged pending restore (`PITR_TARGET`) | `PITR_TARGET_REFUSED` | Run the restore again |
| A damaged log manifest | `WAL_MANIFEST_REFUSED` | The file and both versions are named; restore from a backup |
| A damaged versioned file | `FILE_FORMAT_REFUSED`, start exits 78 | The file is named; restore from a backup |
| A damaged WAL frame that is not a crash's torn tail, or a missing WAL segment | `FILE_FORMAT_REFUSED: kind=wal-segment`; the database stays quarantined, the server and its other databases run (**BL-1741, next train**) | The segment and the position are named; restore from a backup, or `unquarantine?salvagePastCorruptWal=true` to skip the frame and lose its writes |
| A read meets a cold segment whose column file is missing or short | `COLD_SEGMENT_UNREADABLE`, HTTP 500, logged | The read is refused, not answered with nulls; restore from a backup |
| `azure://` or `gcs://` | `BACKUP_DESTINATION_UNAVAILABLE` 503 | Use `s3://` or a path |
| A restore failed part-way over several databases | the message ends `Databases already restored: …` | Restore again once the cause is fixed; those databases are already at the restore |
| A blob of the set or the WAL archive does not match its key | `BACKUP_BLOB_DAMAGED` 409, naming the file and the set | Restore another set: the destination's copy is damaged. The database the restore stopped in refuses to open until a restore of it completes (**BL-1739, next train**) |
| A database whose restore did not complete | `RESTORE_INCOMPLETE`: the database is quarantined (an embedded open throws; an unquarantine answers 503 `RESTORE_INCOMPLETE`) | Run the restore again, or restore another set; a restore that completes clears it (**BL-1739, BL-1740, next train**) |
| An S3 error on first use | `AmazonServiceException` in the log | Check the bucket, the region and the credential chain |

## 11. Formats and upgrading

A backup carries its own format (`manifest.json`, version **4**). A build reads one version: a version-3 backup is **listed**
(`pitrEligible: false`, `complete: false`) but cannot be restored by a version-4 build — a set taken before this release has no set
record, so a restore answers `BACKUP_SET_INCOMPLETE` (409) — and there is no converter. Restore it with the build that took it, or take
a new backup after upgrading; the first incremental backup after an upgrade is taken full. A data-directory format bump is crossed with
`aouda dump` and `aouda load`: [Upgrading](upgrading.md). A backup from 0.2.x or earlier (format 1 or 2) is refused the same way.

## 12. Implementation notes

**Exact restore.** After the files are written, a synthetic `clean_shutdown.marker` with WAL head 0 points at the restored `.hra`
snapshots; the first open loads them into the write buffers and flushes them (§3). **Point-in-time restore.** The restore deletes the restored
snapshots, stages a WAL root and a `PITR_TARGET` file (version 2: the backup's redo-start and cut positions), and the next open replays whole
transactions from the redo-start through the crash-recovery path to the last commit at or before the target.

**Order inside a backup**: the fence, then the buffer snapshots, then the redo-start and WAL positions, then the manifest — so the snapshots
serve the exact restore and the redo-start serves the PITR.

**Hot and mutable-tier tables.** A table with data files and a write buffer is backed up with its `.hra` snapshot beside its segments; a
never-sealing mutable table is covered entirely by the snapshot. `memory` tables write nothing to disk and are not in a backup.

## 13. Scenarios

**Server-managed incremental backup**: set the archive (§6), `aouda backup create` (twice: the second shows `newBytes` below `totalBytes`).

**Disaster restore**: `aouda backup list` → `aouda backup restore <id>`; the engines restart. On a new host: [Restore to a new host](restore-to-a-new-host.md).

**A mistake at 15:03**: `aouda backup restore --target-time 2026-11-21T15:03:00Z`. The response lists, per database, the transactions and rows replayed.

**Embedded**: `BackupEngine.CreateBackupAsync`, `RestoreEngine.RestoreAsync` (set `TargetTime`, then reopen — the replay happens on open) and
`BackupLifecycleManager` are available to a host that embeds the engine.
