---
title: "Single-Node Deployment"
nav_order: 20.5
parent: "Guides"
---

# Single-node deployment

{:.warning }
**Replication is not supported in any release of Aouda yet.** A replica cannot catch up after a disconnect, keeps streamed rows only in memory, and a primary's election and failover are not proven; run one node per database and protect data with [backups](backup.md). This page describes the code as it stands.

Aouda works out of the box on one node — most deployments start here, and many stay here. This page
covers the one setting that makes a single node a **supported** profile rather than an accident of which
flags you happened not to set, what it changes today, and exactly what changes the day you add a second
node.

---

## The one setting

A single-node deployment is one where a database's replication mode is set to **do not replicate**:

```json
"databases": { "<name>": { "kind": "data", "replicationMode": "DoNotReplicate" } }
```

in `aouda.json`. An `os` load, and a load into a database without a WAL, write none |
| Replication streaming | Runs for this database | Not started for this database |
| Per-table replication override | May be enabled | Rejected — a table cannot opt into replication while its database has it disabled |

A database's `MaxTotalRamBytes`/governed-budget derivation is identical in both columns; see the
[Defaults Reference](defaults-reference.md) for those numbers.

### Point-in-time recovery and bulk loads

Every `strict` bulk load writes its closing WAL frame and keeps its files in the database's bulk-load store (`{db}/bulk-wal/`), and the WAL archive holds
them with the log segment. A point-in-time restore therefore brings back a `strict` load that committed before its target —
or refuses, naming the job (`PITR_BULK_LOAD_UNAVAILABLE`), when its files are gone. It does not depend on the replication mode.

- An **`os` load** made after the backup is **not** restored by a point-in-time restore (BL-1717); an exact restore of a backup taken after it is.
- **The cost is disk.** The store holds hard links (no extra bytes while a segment lives); a compacted load's bytes are kept until its WAL is reclaimed, and the archive
 grows by each load's size ([Sizing](sizing.md)).
- A frameless multi-table load no longer exists: a load of several tables is all-or-nothing, and one a crash cut part-way is dropped whole at the next open and reported
 `lost`; load it again with the same idempotency key.

---

## Backups on a single node

With no replica, backups are how you protect data, so set them up before you need them:

- **Schedule backups:** `PUT /admin/backup/schedule`. With no schedule, nothing is backed up unless you trigger it.
- **Set a retention policy:** `PUT /admin/backup/retention`. There is none by default, so backups accumulate until you remove them.
- **Test a restore on a second host** before you rely on it: [Restore to a new host](restore-to-a-new-host.md).
- **A crash is recovered by restarting the node.** The server replays its write-ahead log at start; see [Write durability](write-durability.md).

---

## What changes when a second node joins

Replication is not supported, so this is a description of the code, not a step to take; see the note at the top of this page
and of [Replication and Clustering](replication.md). The steps are:

1. Configure `Aouda:ReplicaSet` with the joining node(s) — see [Replication and Clustering](replication.md)
 for cluster setup. This is independent of the setting below.
2. Set `ReplicationMode: Replicate` for the database — `PATCH` its options, or update config and restart.
3. The change takes effect on the **next time the database's engine opens** — not live. A running server
 picks it up the same way it picks up a restore: close and reopen that database, or restart the
 process.
4. After reopen: replication streaming starts for that database.

There is no data migration step — this is a configuration change, not a schema or storage change.
Existing data is unaffected either way.

---

## What this profile does not change

- No new config section, CLI flag, or detection heuristic — `ReplicationMode` is the one setting.
- Memory-budget derivation, bulk-load segment sizing (`TargetSegmentBytes`, the ingest buffer budget),
 and partition storage mode are all unaffected — see the [Defaults Reference](defaults-reference.md) and
 [Bulk Load](bulk-load.md).
- `BulkLoadCoordinator`'s frame-emission gate itself is unchanged — this profile only supplies the
 topology signal that gate already reads correctly.

---

## Related docs

- [Defaults Reference](defaults-reference.md) — every derived default, worked at several host sizes
- [Bulk Load](bulk-load.md) — sizing a session, choosing partition storage mode, single-node frame elision in context
- [Replication and Clustering](replication.md) — cluster lifecycle, adding a node, replica-set configuration
- [Write Path Durability](write-durability.md) — the WAL model this trade-off is built on
- [Backup and Restore](backup.md) — exact restore vs. PITR, and the local recovery window
