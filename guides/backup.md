---
title: "Backup and Restore"
nav_order: 8
parent: "Guides"
---

# Backup and Restore

Last updated: 2026-11-26 (Durability-1)

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
| Backup while the server takes writes (no quiesce) | Available |
| Exact restore, against the server or offline into an empty directory | Available |
| Point-in-time restore (PITR) to a commit boundary, from the local WAL or the WAL archive | Available |
| Restore onto a new host from the destination alone | Available |
| Schedule (cron) | Available |
| Retention policy (`keepLast`, `keepDays`, `pitrWindow`) and `aouda backup prune` | Available; **none by default** |
| `aouda backup` command line | Available |
| Branches in a backup and in an exact restore | Available; a PITR drops them |
| Encryption of a backup | Not provided: it is the destination's (§9) |
| Azure Blob Storage and Google Cloud Storage destinations | Not supported (`azure://`, `gcs://` are refused) |
| Restore of one table, or to a time inside a transaction | Not supported: the finest point is a transaction's commit |
| One consistent cut across all databases of a server | Not supported: each database has its own cut |

## 2. What a backup is

- **One set per backup.** `aouda backup create` (or `POST /admin/backup/trigger`) backs up every database of the server — the auth
  database first — and writes the **set record** last. A set is **complete** only when its record is there; a set that one database
  failed is listed as incomplete and **refused** by a restore, never restored in part. A set from a build
  before this release has no record and is listed incomplete.
- **No cross-database consistency.** Every database has its own cut. A write to two databases is not a unit across them.
- **Incremental by default.** Files are stored by SHA-256, so an unchanged file is stored once. An incremental backup records its base;
  `--full` uploads everything again. If the newest base is of an older backup format, the backup is taken in full.
- **It needs no quiesced database.** A backup under write load restores exactly. It takes one **fence** — a cut that a transaction in
  its commit section finishes before — and writers wait for it; they are never failed by it. The fence waits at most **5 seconds** for the commits in flight and is then held
  at most another 5 seconds while the cut is taken, so a writer waits at most about 10 seconds. The hold grows with
  the buffered rows to capture; it has not been measured at production scale (BL-1642). A backup that cannot take or hold the fence in
  time fails with `BACKUP_FENCE_TIMEOUT` (HTTP 503); retry it, and if it keeps failing, look for a long write that holds a commit section.
- **Rows in a write buffer are in the backup.** A row that was only in memory (the table's write buffer, or an edge or vector buffer)
  at the cut is written into the backup, and a point-in-time restore replays the log **from the redo-start position**, an earlier position than
  the cut, so that row comes back too. Before this release a PITR dropped those rows.
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
  it; a declaration still wins.
- **The first open after an exact restore takes longer**: it flushes the restored write buffers so the restored rows are durable. A crash before it finishes loses nothing; the next open does it again.
- **A restore syncs what it wrote** before it reports success.
- A restore **refuses** a set that is not complete, a set record or manifest of another format, a target time it cannot serve, a backup it
  cannot read and a point-in-time restore outside its archive window (§4.1), before it stops anything — a refused window changes nothing.
- **Every blob is checked against its key as it is read** — its SHA-256 and its length, before the file gets its name: a backed-up file,
  the catalog, an archived WAL segment, a branch's files. A blob that does not match refuses the restore with `BACKUP_BLOB_DAMAGED` (409),
  naming the file and the set; nothing is written under that file's name. A successful restore is therefore a verified one, and its
  answer says nothing more about it (**BL-1748, next train**: the `integrityVerified` it carried, always `true`, is gone).
- **A restore that stops part-way leaves a database that refuses to open.** From its first change to its last step a restore marks the
  database `restore.incomplete`; a database that holds it is not opened (`RESTORE_INCOMPLETE`) — the server keeps it quarantined, an
  embedded open throws — until a restore of it completes. A refused blob, a cancellation or a crash
  part-way therefore never leaves the old database's catalog over the backup's files: run the restore again, or restore another set.

- **A failed restore does not take the operator's sign-in.** The server's auth database (`_serverauth`, and every other auth database in
  the set) is restored into a copy beside it, and swapped in by rename, **last**, only once every other member has restored. The copies are
  restored and opened **first**, before any other member is touched (**BL-1711, next train**), so a refusal of an auth database — its replay,
  or a set that leaves nobody able to operate the server (below) — changes nothing at all. A restore
  that fails — a full disk, a damaged blob, in any member or in the auth database itself — leaves it as it was: the operator's key still
  signs in, a restart opens it, and the restore can be run again. The data member a failed restore stopped in still refuses to open
  until a restore of it completes (above). A crash during the swap is finished by the next start: the old auth database before the
  swap's commit, the restored one from it — never neither. The copy is **opened before the swap** — a
  point-in-time restore's replay, an exact restore's first open — so a replay that is refused there (`PITR_KEYLESS_DELETE_UNRESOLVED`,
  a damaged archived frame) fails the restore with its own code and leaves the working auth database in place, signing the operator
  in; it used to run after the swap and quarantine the only auth database left.
- **A restore never leaves the server with nobody who can operate it** (**BL-1711, next train**). The copy of the server auth database is
  judged on the open copy — replayed, so at a point-in-time restore's target — before anything is swapped: it must hold an enabled
  principal that holds `manage` on `server` **and** has a credential that signs in by itself — a stored key that is neither revoked nor
  expired, a password, or an OIDC trust. A limited key does not count (it lives with its parent), nor does a derived key (it signs in only
  where the declaration holds its key root). A set that holds nobody like that — its last operator was deleted, disabled or left with a
  revoked key before a scheduled backup took it, or its key expired since — is refused `409 RESTORE_LEAVES_NO_OPERATOR`, naming the set
  and counting what it found: nothing was changed, and the operator who ran it is still signed in. It used to answer `200`, after which
  every key, the old host's and the new host's, was refused. A server whose declaration declares an operator in `server.principals`
  (manage on server, with a credential) is not refused: the converge after the restore writes that operator. The ways out: declare an
  operator in `server.principals` and restart, then restore again; restore another set or target; or restore offline (`--to`) and start
  that directory with such a declaration.
- **A member that does not open fails the restore.** A restore answers success only when every member it restored is open: one whose
  files were restored and that does not open (a database this server knows, at the reopen; one it did not know, at its registration)
  is quarantined with the cause, and the restore answers `500 BACKUP_RESTORE_FAILED` (a point-in-time restore: `PITR_FAILED`) naming it
  and its cause, and the members that did open. It used to answer success while the member's failure was only in the server log. A cancelled restore returns only once every download it started has finished.
  The same holds for a database **outside the set** (**BL-1821, next train**): a restore stops and reopens every engine, so a database that
  was open before it and does not reopen fails the restore the same way, its message naming it after `Not in the set, and did not
  reopen:` with its state and cause. A database that was not open before the restore — quarantined by the operator or by an earlier
  failure, or listed in `Aouda:SkipDatabases` — is not named: the restore did not close it.
- **A restore checks the space first.** Before anything stops, it compares what it will write — every member's backed-up files, the copy
  each auth database is restored into, the WAL a point-in-time restore stages — plus a margin of 16 MiB and 5 % with the free space of
  the data directory's volume, and refuses `507 DISK_FULL` (with `Retry-After`) naming both numbers when it does not fit; nothing is
  changed. The offline `aouda backup restore --to` asks the same before it creates the directory (`DISK_FULL`, exit 1). What an in-place
  restore deletes first is **not** counted: a disk with less free space than the backup needs space freed first, or an offline restore
  onto another volume.

- **A restore ends the live subscriptions of the databases it replaced** (**BL-1818, next train**), by name, once it has finished —
  succeeded, failed or cancelled: `SUBSCRIPTION_DATABASE_REPLACED` (subscribe again with no `resume_from`; both SDKs do), or
  `DATABASE_QUARANTINED` for a database that did not open. Up to 0.17.1 they stayed open and silent. See
  [When the database is replaced](real-time.md#when-the-database-is-replaced-bl-1818-next-train).
- **After a restore, who may sign in and what they may do are the restored auth database's at once** (**BL-1819, BL-1820, next
  train**). The server caches access decisions, keyed by each auth database's permission version; a restore puts another history under
  the name, whose version can equal the cached one. Up to 0.17.1 that cache could answer from the database the restore replaced: a
  principal whose role the restore took away was still admitted for up to 30 seconds, an OIDC trust of the restored auth database was
  refused ("The token's issuer is not trusted.") until a permission change or a restart, a realtime session open across the restore
  was not re-keyed by a policy change until the restored version passed the old one, and a key revoked in the restored auth database
  ended such a session only at its next periodic check, not at once. Every such cache now also holds the database it
  read from, so nothing decided under the replaced database is used again.

**Point-in-time restore** — see §4.

### 3.1 What a restore does not bring back

- Anything outside the data directory: the declaration file (`aouda.json`) and keys set in the environment. Carry them as you do for
  any server.
- A database the set did not contain.

After a restore the server reconciles declared databases as it does at any start.

## 4. What a point-in-time restore returns

A point-in-time restore takes a backup, then replays the WAL to the **last commit at or before the target
instant** (`targetTime`).

- **Commit boundaries.** The log carries the time each commit happened, nothing finer: a transaction, a bulk load, a schema change, or
  an edge or vector write is each its own commit. A restore never lands in the middle of one, and a schema change is restored exactly
  when it was acknowledged at or before the target (**Durability-1, next train**).
- **Rows buffered at the backup come back** (§2), and so do the buffered rows of tables created after it.
- **Tables created after the backup come back** through any route — REST, a table an insert inferred, an edge table or a vector column,
  schema apply, Embedded — with one row per key; a materialized query defined after the backup comes back, rebuilt. Before this release a
  PITR across a created table could show two versions of an updated row, and a [formula](formulas.md) database then refused to open.
- **A crash after a PITR** neither revives what the restore excluded nor loses later writes, and a later PITR honours the exclusion of
  the first. Concurrent policy changes restore to the last. A bulk load committed after the
  target is not committed after the restore.
- **Bulk loads.** A `strict` load committed before the target is restored from the bulk-load store or from the archive; if its
  files are not there the restore is refused, naming the job (`PITR_BULK_LOAD_UNAVAILABLE`, HTTP 409).
  An `os` load made after the backup is **not** restored (BL-1717).
- **A table without a primary key** is exact up to the first delete or update, after the backup, of a row that the table flushed, bulk-loaded or
  merged after the backup. Past that instant the restore is refused with `PITR_KEYLESS_DELETE_UNRESOLVED`, naming the table and the instant, and
  the database stays quarantined until a new restore — to an earlier target or from a later backup. Give the table a primary key and every
  target is exact.
- **Edge and vector writes** made after the target are not restored: each carries its own commit time, and the replay stops at the first
  one past the target (**BL-1726, next train**).
- **A table that changed inside the window comes back as it was at the target** (**Durability-1, next train**): a column added or made
  nullable, a primary-key change, a widened column type, a dropped column and a derived column each apply at their own place in the log,
  as they did live. Before this release a restore across a column made nullable brought nulls back as zeros, one across a key change
  (or a widened key column) brought deleted rows back, and a widened or dropped column refused the restore — a primary-key column
  widened from `Int32` to `Int64` too, once a row after the widening had a key that did not fit `Int32` (`PITR_FAILED`, and the
  database quarantined; BL-1900).
  **Known limit:** a derived column whose expression was set and then cleared inside the window leaves the rows before it
  unrewritten (BL-1895).
- **A point-in-time restore that did not finish is resumed** (**Durability-1, next train**). The replay runs at the database's next
  open. When that open is cut short — a crash, a kill, a flush that fails at its end — the next open continues from where the replay
  stopped (it saves its progress with each schema change it applies), and nothing needs to be run again: the database stays out of
  service until the replay is done. The one state it cannot resume is a table without a primary key whose rows an earlier, interrupted
  open had already flushed while their deletes were still unread: the open is refused with *The point-in-time restore cannot be
  resumed … Run the restore again; it starts from the backup.* A restore killed in its last steps is repeated exactly: its control
  file (`PITR_TARGET`) is deleted durably, or the open is refused.
- **A target at or before the backup** is refused (`BACKUP_TARGET_TIME_INVALID`, 400), naming both instants; so is a target in the future,
  and a set that is exact-restore-only (§4.1).
- **Without a `backupId`** the newest complete set that lies wholly at or before the target is chosen; `404` when there is none. If that set
  is exact-restore-only the restore is refused; an older set is not tried.

### 4.1 What a PITR needs

- **A PITR-eligible backup**: its manifest records a WAL root. A database at `unlogged` or `memory` has no WAL, so its backups are
  exact-restore-only (`pitrEligible: false`). A backup of a database that has a WAL root is eligible even at WAL position 0.
- **WAL that covers the window.** The local WAL since the backup — bounded by write volume, not by days (`MaxSlotWalKeepBytes`) — or,
  past that, the **WAL archive** (`Aouda:Archive`, §6). A restore whose archive does not reach back to the backup's replay position is
  refused with `PITR_WINDOW_UNAVAILABLE` (409), never restored short. So is a restore whose archive holds a segment of the window that
  is **not the whole segment** its manifest entry spans — cut short, damaged or longer (**Durability-1, next train**): the archive
  worker proves a sealed segment whole before it uploads it and does not publish one that is not (nor anything after it, nor a record
  of the log as quiet past it), and the restore proves every archived segment of the window again as it stages it, the last included.
  Every database's window is checked before any engine stops or any file changes, so a refused window leaves every database as it
  was — with one exception: a segment that can only be read when it is staged is found after that database's backup files were
  restored, and the answer says so (§10).
- **The WAL-root incarnation the backup was taken in.** An exact restore starts a new incarnation, so a PITR from a backup that
  predates it needs the archive, or a backup taken after the restore.
- **A backup's history ends at a later restore in place** (**BL-1631, next train**). After the database was restored in place (a PITR
  or an exact restore), a PITR of a backup taken *before* that restore, to a target *after* it, is refused with
  `PITR_WINDOW_UNAVAILABLE` (409): the log that backup belongs to ends where the restore cut it. After a **PITR** in place the message
  says so — *this backup's history ends there: the database was restored in place after it, and its log continues as incarnation <n>* —
  and names what to do: restore from a backup taken after that restore, or choose a target before the instant it names; it never says
  to wait. An **exact** restore starts a new WAL root, which the old backup's record does not name, so after one the message says to wait
  only when the backup's database still runs on the same WAL root — it does not: restore from a backup taken after the restore, or
  choose an earlier target.
- **The archive's RPO for a host loss** is `Aouda:Archive:MaxUnarchivedSeconds` (default 60 seconds) plus one archive check (a minute):
  the active WAL segment is sealed and shipped when its oldest frame is that old.
- **A level change that retires the WAL ends the window** at the change; see [Write durability](write-durability.md#changing-a-level).

### 4.2 Branches and a PITR

A point-in-time restore **drops every branch** of the databases it restores and names each one in the response (`droppedBranches`).
Restore exactly to keep them; a per-branch point in time is not available.

### 4.3 Onto another host

A PITR and an exact restore onto another host from the destination alone are supported: segment ids are not reissued and `.hot` rows come
back. A restored copy must archive to **its own** destination while its source still runs: the two servers' retention policies would
prune each other's backups. (The archive keeps one record per WAL root, written by that root's server alone, so two servers archiving
to one destination no longer lose each other's archived WAL — **BL-1672, next train**.) The runbook is
[Restore to a new host](restore-to-a-new-host.md).

## 5. Retention

Backups and the archive grow until you prune them. **There is no default policy: nothing is pruned** until you save one.

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
- **The WAL archive is kept from the oldest listed backup's redo-start**, so retention never prunes the log a
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

`aouda backup` takes the server from `--server` / `AOUDA_SERVER` and an operator key from `AOUDA_TOKEN` (or `--token`; an argument shows in the process list).
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

**After a restore, a client's consistency tokens are ahead of the node.** A read that carries one answers `409 TOKEN_UNSATISFIED` until it is
discarded. `@aouda/client` clears the tokens of the client that ran a successful restore, for every database, and has
`client.forgetConsistencyTokens()` for a client that did not (**BL-1731, next train**); `Aouda.Client` has no such call yet — discard its
store, or use a new client.

## 8. Operations

- **Metrics** (**BL-851, next train**): `GET /api/admin/metrics` has `aouda.backup.last_success_age_ms` — the last backup set that succeeded on
  this server, by hand or by the schedule, **kept over a restart**, and no point when none is known — `last_failure_age_ms`,
  `last_duration_ms`, `runs_total` (`succeeded`, `failed`, `skipped`), `restores_total`, `uploaded_bytes_total`, and the log's
  `aouda.wal.archived_bytes_total`, `archive_errors_total` and, per database, `aouda.wal.slots_count` and `slot_lag_bytes` (the log's
  position minus its lowest slot). Alert on `last_success_age_ms`. `lastBackupHoursAgo` is gone with `GET /api/admin/metrics/summary`: it
  was always `-1` (BL-1841).
- **Health**: `GET /health/detailed` reports a backup component (stale if no recent success; `not_configured` before any backup) and an archive
  that is not advancing.
- **A WAL segment that is not whole stops the archive in front of it** (**Durability-1, next train**). A sealed segment that is short,
  damaged or longer than its manifest entry is not archived, and nothing after it is; each pass tries again and reports it in the server
  log, in `archiveErrorsTotal` and in the archive slot's lag, which grows. The `archive` health component does **not** reliably show it
  (BL-1896: it judges counters shared by every database, and another database's clean pass hides one that fails). The window then stops
  growing for that database until the segment is whole again, or the log's slot limit drops the segment, or an exact restore starts a new
  log (BL-1889). A target past the damage is refused (`PITR_WINDOW_UNAVAILABLE`), never restored short; a move to a level without a WAL
  is refused while the archive holds a short copy of the log it would delete.

## 9. Encryption, and who can read a backup

**Aouda does not encrypt a backup, the archive or a dump.** Encryption is the destination's: S3 server-side encryption, an encrypted volume.
A backup holds every column value and, in an auth database, credential hashes; protect the destination like the data. The server never
shows an S3 credential in a log, an error or a CLI line, and a database name that looks like a key is redacted in them.

## 10. Errors

Every error the backup routes raise is a JSON body with `error` (the message), `code` and a string `remedy`; a
refused key (401 / 403) has the authentication envelope instead, and a `507 DISK_FULL` (a backup's or a restore's) the capacity envelope:
`error`, `code` and `details`, with `Retry-After`. The ones you will meet:

| Symptom | Code and status | What to do |
|---|---|---|
| A backup, restore or prune is already running | `BACKUP_IN_PROGRESS` 409 | Wait, then retry |
| The backup could not take its fence | `BACKUP_FENCE_TIMEOUT` 503 | Retry; a less loaded server takes it |
| A buffer could not be sealed for the backup | `BACKUP_BUFFERS_UNSEALED` 503 | Retry |
| A branch could not be captured | `BACKUP_BRANCH_UNAVAILABLE` 409 | Repair or delete the branch the message names, retry |
| A registered database is not open (listed in `Aouda:SkipDatabases`, or quarantined) | `BACKUP_DATABASE_NOT_OPEN` 409, naming it and why; no set is taken (**BL-1953, next train**; it was `400 BACKUP_DESTINATION_UNAVAILABLE`) | Open it — take it out of `Aouda:SkipDatabases` and restart, or resolve its quarantine — or drop it, then retry |
| Restore of a set taken before this release | `BACKUP_SET_INCOMPLETE` 409: the set has no completion record | Restore it with the build that took it, or take a new backup after the upgrade |
| A set whose manifest is of another version | `BACKUP_MANIFEST_REFUSED` 400, `found=<n> expected=4 backup=<id> path=<manifest>` | Restore it with the build that took it |
| Restore of a set one database failed | `BACKUP_SET_INCOMPLETE` 409 | Restore another set; a prune removes it |
| A set record of another version | `BACKUP_SET_REFUSED` 400 | Restore with the build that took it |
| A target at or before the backup, or in the future; or a PITR of an exact-restore-only set | `BACKUP_TARGET_TIME_INVALID` 400 | Pick a target after the set's last cut, or restore the set exactly |
| The archive does not cover the window, or an archived segment of it is not the whole segment its entry spans (the message names the segment's seq and what was found) | `PITR_WINDOW_UNAVAILABLE` 409 | Pick a target before the segment, restore exactly, or point `--archive` at the archive's destination. Nothing was changed — unless the message ends *The database '…' refuses to open (RESTORE_INCOMPLETE) until a restore of it completes*: the staging found the segment after the database's backup files were restored. Restore it again (to an earlier target, exactly, or once the archive is whole) |
| A point-in-time restore that cannot be resumed (a keyless table whose rows an interrupted open flushed before their deletes were read) | the open is refused: *The point-in-time restore cannot be resumed … Run the restore again; it starts from the backup.* | Run the restore again. Any other interrupted point-in-time restore is resumed by the next open, with no action |
| A schema change that cannot fit in one WAL segment | no code of its own: the route's error, a table create `500`, with *A catalog change of N bytes (F frames) cannot fit in a B-byte segment: a change is logged in one, which holds M bytes of it. Nothing was changed.* | Nothing was changed: the table, column or rule was not saved and nothing was logged. No route can reach this limit with the default 64 MB segment |
| A bulk load committed before the target is not in the store | `PITR_BULK_LOAD_UNAVAILABLE` 409 | Restore before the load's commit (the message names the job) or from a later backup |
| A keyless delete the restore cannot apply | `PITR_KEYLESS_DELETE_UNRESOLVED` 409 | Restore to before the instant named, or from a later backup |
| A damaged pending restore (`PITR_TARGET`) | `PITR_TARGET_REFUSED` | Run the restore again |
| A damaged log manifest | `WAL_MANIFEST_REFUSED` | The file and both versions are named; restore from a backup |
| A damaged versioned file | `FILE_FORMAT_REFUSED`, start exits 78 | The file is named; restore from a backup |
| A damaged WAL frame that is not a crash's torn tail, or a missing WAL segment | `FILE_FORMAT_REFUSED: kind=wal-segment`; the database stays quarantined, the server and its other databases run | The segment and the position are named; restore from a backup, or `unquarantine?salvagePastCorruptWal=true` to skip the frame and lose its writes |
| A read meets a cold segment whose column file is missing or short | `COLD_SEGMENT_UNREADABLE`, HTTP 500, logged | The read is refused, not answered with nulls; restore from a backup |
| `azure://` or `gcs://` | `BACKUP_DESTINATION_UNAVAILABLE` 503 | Use `s3://` or a path |
| A restore failed part-way over several databases | the message ends `Databases already restored: …`, and says the auth databases were not changed | Restore again once the cause is fixed; those databases are already at the restore, and the operator is still signed in |
| A set restore would leave nobody able to operate the server (**BL-1711, next train**) | `RESTORE_LEAVES_NO_OPERATOR` 409, naming the set and the server auth database, counting its server managers and how many can sign in | Nothing was changed. Declare an operator in `server.principals` and restart, then restore again; or restore another set or target; or restore offline (`--to`) and start it with that declaration |
| A database outside the set did not reopen after the restore (**BL-1821, next train**) | `BACKUP_RESTORE_FAILED` 500 (a point-in-time restore: `PITR_FAILED` 500), `Not in the set, and did not reopen: '<db>': <state>: <cause>` | The members are restored; fix the cause named and unquarantine that database |
| A restored member did not open | `BACKUP_RESTORE_FAILED` 500 (a point-in-time restore: `PITR_FAILED` 500), the message naming each member that did not open, its quarantine and its cause, and `Restored and open: …` | Fix the cause named, then restore the set again (it clears the quarantine), or unquarantine the member |
| The data volume cannot hold the restore | `DISK_FULL` 507 + `Retry-After`, naming the bytes needed and free; offline, `DISK_FULL` and exit 1 | Nothing was changed: free space (or restore offline onto a larger volume) and retry |
| A blob of the set or the WAL archive does not match its key | `BACKUP_BLOB_DAMAGED` 409, naming the file and the set | Restore another set: the destination's copy is damaged. The database the restore stopped in refuses to open until a restore of it completes |
| A database whose restore did not complete | `RESTORE_INCOMPLETE`: the database is quarantined (an embedded open throws; an unquarantine answers 503 `RESTORE_INCOMPLETE`) | Run the restore again, or restore another set; a restore that completes clears it |
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
