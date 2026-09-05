---
title: "Single-Node Deployment"
nav_order: 20.5
parent: "Guides"
---

# Single-node deployment

Aouda works out of the box on one node — most deployments start here, and many stay here. This page
covers the one setting that makes a single node a **supported** profile rather than an accident of which
flags you happened not to set, what it changes today, and exactly what changes the day you add a second
node.

---

## The one setting

A single-node deployment is one where a database's replication mode is set to **do not replicate**:

```
Aouda:Databases:<name>:ReplicationMode = DoNotReplicate
```

The default is `Replicate`. That single key is the entire profile — there is no separate "single-node
mode" flag, config section, or CLI switch to discover. Set it per database (`PATCH` the database's
options, or configure it before first open) when that database has no replica today.

Memory budgeting needs **no setting either way**: the server's `MaxTotalRamBytes` default already derives
a safe fraction from detected host memory whether or not you have replicas — see the
[Defaults Reference](defaults-reference.md). `ReplicationMode` does not affect it.

---

## What the profile changes today

| Concern | `Replicate` (default) | `DoNotReplicate` (single-node profile) |
|---|---|---|
| Bulk-load `LogShipSegments` WAL frames | Emitted for every segment | Elided by default — no per-segment re-read/hash, no fsync'd WAL frame. The job's commit point becomes its durable catalog registration instead. Override with `Aouda:BulkLoad:EmitFramesOnSingleNode=true` to keep a WAL trail ready ahead of a later join (see below). |
| Replication streaming | Runs for this database | Not started for this database |
| Per-table replication override | May be enabled | Rejected — a table cannot opt into replication while its database has it disabled |

A database's `MaxTotalRamBytes`/governed-budget derivation is identical in both columns; see the
[Defaults Reference](defaults-reference.md) for those numbers.

### The trade-off: point-in-time recovery

**A frameless bulk load's rows do not participate in point-in-time recovery (PITR).** PITR works by
restoring a base backup, then replaying WAL forward through the same crash-recovery path the server uses
after an unclean shutdown, up to the requested target time (see [Backup and Restore](backup.md)). That
replay can only reconstruct what the WAL actually recorded. A `LogShipSegments` bulk load on a
`DoNotReplicate` database (or with `EmitFramesOnSingleNode` left at its default) commits **without**
writing the `BulkSegmentCommitted`/`BulkLoadCommitted` WAL frames a replicated load writes — its rows
become durable and query-visible through the job's catalog registration instead. There is nothing in the
WAL for a PITR replay to find, so those specific rows are not recoverable by restoring to **any** target
time through PITR, not merely a target time inside some window.

This is not a bug — it is the same trade-off `ReplicationMode.SkipReplication` has always made, now also
the *default* shape for a single-node bulk load. An **exact** backup or restore taken after the load is
unaffected: it captures the segment files that already exist on disk, regardless of whether a WAL frame
was ever written for them. Only a **PITR** restore targeting a time during or after a frameless load is
where the gap shows.

If you take regular backups and might need PITR back through a bulk-load window, set
`Aouda:BulkLoad:EmitFramesOnSingleNode=true` before that load — it restores per-segment WAL frames on a
single node at the cost this whole family of pages exists to let you avoid paying by default (a
per-segment re-read and hash, and a fsync per segment). Choose it deliberately, for the loads where it
matters, rather than leaving it on everywhere.

---

## What changes when a second node joins

1. Configure `Aouda:ReplicaSet` with the joining node(s) — see [Replication and Clustering](replication.md)
   for cluster setup. This is independent of the setting below.
2. Set `ReplicationMode: Replicate` for the database — `PATCH` its options, or update config and restart.
3. The change takes effect on the **next time the database's engine opens** — not live. A running server
   picks it up the same way it picks up a restore: close and reopen that database, or restart the
   process.
4. After reopen: `LogShipSegments` bulk loads resume emitting WAL frames, and replication streaming
   starts for that database.

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
