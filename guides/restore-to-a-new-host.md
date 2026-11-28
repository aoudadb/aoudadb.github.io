---
title: "Restore to a New Host"
nav_order: 8
parent: "Guides"
---

# Restore to a new host

The host that ran Aouda is gone — a failed disk, a lost virtual machine — and the backups are in a
destination you can still reach: a directory or an S3 bucket. This page brings the data back on another host. Run it once, on a
spare host, **before** you need it: an untested restore is a hope.

What you need:

- **The destination** (the backup destination, and the WAL archive's if it is a different one) readable from the new host.
- **The same build that took the backup, or a newer one that reads the same backup format.** A backup carries its own format version
  (the current one is 4). A build that reads another version refuses the backup before it writes anything: a set taken before this
  release has no set record (`BACKUP_SET_INCOMPLETE`), and a manifest of another version is `BACKUP_MANIFEST_REFUSED`, naming both
  versions. Restore that backup with the build that took it.
- **What is not in a backup**: the declaration file (`aouda.json`) and keys set in the environment. Carry them separately; the data
  directory does not hold them. See [Backup and restore](backup.md#31-what-a-restore-does-not-bring-back).
- **An empty data directory** on the new host.

## Choose: exact or point in time

- **Exact** returns every database as it was at the backup's cut. Use it when the newest backup is good enough.
- **Point in time** (`--target-time`) returns the last transaction that committed at or before an instant after the backup. It needs the
  WAL archive (`Aouda:Archive`) that the lost host was writing to; the log in the archive is at most about a minute plus one archive check
  behind the lost host (`Aouda:Archive:MaxUnarchivedSeconds`, default 60). Without an archive there is no point in time on a new host.

## Path A — a fresh server pointed at the destination

1. Start a server on an empty data directory, with the archive settings of the lost host (the destination, and for S3 the credential chain
   or `ServiceUrl`). The new server finds the sets in that destination and, once the restore has run, archives to it. **If the lost host
   might still be running, use Path B instead** and start the copy with its own destination (below):

   ```bash
   export AOUDA_ARCHIVE__ENABLED=true AOUDA_ARCHIVE__DESTINATION=/mnt/backups/aouda
   aouda start --data-path /srv/aouda-new
   ```

2. Find the set, then restore it:

   ```bash
   export AOUDA_SERVER=http://localhost:5000 AOUDA_TOKEN=<an operator key>
   aouda backup list
   aouda backup restore backup-2026-11-21-150851-4bccdc05                              # exact
   aouda backup restore --target-time 2026-11-21T15:09:01Z                             # point in time: the newest set at or before it
   ```

   The server stops its engines for the restore and restarts them; a point-in-time restore replays the log at the restore.
   **The restore replaces the new server's own auth database** with the restored one: the operator key the new server started with
   (a `--dev-admin` key, a bootstrap key) stops working, and the keys and principals of the lost host work. Keep a **live** operator key of
   the lost host ready — not revoked, not expired since the backup — or the declaration that creates one. A set in which nobody can sign in
   and operate the server is refused `RESTORE_LEAVES_NO_OPERATOR` with nothing changed, and the new server's own key keeps working
   (**BL-1711, next train**): declare an operator in `server.principals` of the new server and restart it, then restore again.

## Path B — offline, into a directory, with no server running

```bash
aouda backup restore backup-2026-11-21-150851-4bccdc05 --to /srv/aouda-new --from /mnt/backups/aouda --target-time 2026-11-21T15:09:01Z
# restored backup set backup-2026-11-21-150851-4bccdc05 into /srv/aouda-new, staged to 2026-11-21T15:09:01.0000000+00:00 (replayed when the directory is first started)
# files        53 (87867 bytes read)
# database     shop (Strict)
# start it with: aouda start --data-path /srv/aouda-new
aouda start --data-path /srv/aouda-new
```

- `--from` is the backup destination (a path, or `s3://bucket/prefix` with the AWS credential chain; `--s3-endpoint` and `--s3-region` for
  an S3-compatible service). `--archive` names the WAL archive's destination when it is not `--from`.
- The target directory must be new or empty. A directory that is not empty is refused and nothing is written (exit 78).
- A point-in-time restore is staged and **replays when the directory is first started**.
- Leave out `--target-time` for an exact restore.

## Check it

```bash
aouda backup list                                  # the sets the new server can see
curl -s -X POST http://localhost:5000/api/databases/shop/query -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"database":"shop","table":"orders","select":["id","item"]}'        # a row count you know
aouda db inspect --name shop
```

The first open after an **exact** restore flushes the restored write buffers, so it takes longer than a normal start; a crash during it
loses nothing and the next start does it again. A restored database keeps the durability level it had.
Principals and keys of the auth database come back with it (they are the lost host's, not the new server's own); the declaration file you carried is read at start.
An offline restore judges nobody: the **first start** does. A directory whose server auth database has no enabled principal that holds
`manage` on `server` refuses to start (`SERVER_HAS_NO_OPERATOR`) unless the declaration declares an operator in `server.principals`; one
whose operators hold `manage` but none of them a credential that signs in by itself (a key revoked, or expired since the backup) starts,
and logs a warning saying so (**BL-1711, next train**) — declare an operator and restart.

## When it refuses

| You see | Meaning | Do |
|---|---|---|
| `BACKUP_MANIFEST_REFUSED: found=<n> expected=4 …` | A member's manifest is of another format | Restore it with the build that took it, or restore a newer backup |
| `BACKUP_SET_INCOMPLETE` | A database of the set has no manifest, or the set has no completion record (every set taken before this release) | Restore another set |
| `PITR_WINDOW_UNAVAILABLE` | The archive does not cover the time between the backup and the target. Checked for every database before anything is written: nothing was written under `--to` | A later target is not better: pick one inside the window, restore exactly, or point `--archive` at the archive's destination |
| `PITR_BULK_LOAD_UNAVAILABLE` | A bulk load committed before the target has no files in the store or the archive | Restore to before the load's commit (the message names the job), or from a later backup |
| `BACKUP_TARGET_TIME_INVALID` | The target is at or before the backup, or in the future; or the set is exact-restore-only (a database without a WAL) | Pick a target after the set's cut, or restore exactly |
| exit 78 | The `--to` directory is not empty | Use an empty one |
| `RESTORE_LEAVES_NO_OPERATOR` (Path A, **BL-1711, next train**) | The set's server auth database holds nobody who can sign in and operate the server (no enabled principal with `manage` on `server`, or none with a live key, a password or an OIDC trust). Nothing was changed; the new server's key still signs in | Declare an operator in the new server's `server.principals` and restart, then restore again; or restore another set; or use Path B and start the directory with that declaration |
| `BACKUP_BLOB_DAMAGED` | A blob of the set or the WAL archive does not match its key (the message names the file and the set); nothing was written under its name, and the database the restore stopped in, if the restore had started writing it, refuses to open (`RESTORE_INCOMPLETE`; the message says so) | Delete the directory and restore another set |

Over HTTP each refusal carries a one-line `remedy` field beside the message; the CLI prints it after the message. A directory a failed offline restore left behind holds a partial
restore and **no registry**: nothing in it is opened by a start, and the database the restore stopped in holds `restore.incomplete`, so it
refuses to open (`RESTORE_INCOMPLETE`) whatever opens it. Delete it and restore again.

## What not to do

- **Do not restore over a running server's data directory.** Use `aouda backup restore <id>` against the server, or an empty directory.
- **Do not let two servers archive to one destination at the same time.** A restored copy that runs while its source is still up must use
  its **own** destination: the two servers' retention policies would prune each other's backups, and retention compares WAL positions
  across them. (Their archived WAL itself is kept apart — one record per WAL root, **BL-1672, next train**.)
- **Do not expect branches back from a point-in-time restore.** An exact restore brings them back; a point-in-time restore drops them and names each
  ([Backup and restore](backup.md#42-branches-and-a-pitr)).
- **Do not rely on a set you have not restored.** Restore the newest set to a spare host and check a row count, on a schedule.
