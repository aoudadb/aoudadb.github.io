---
title: "Defaults Reference"
nav_order: 7.5
parent: "Guides"
---

# Defaults reference

Aouda ships with **zero required configuration** — this page is the two-minute answer to "what did the
server just decide for me, and how do I change it?" Every number below is generated from, or checked
against, `docs/decisions/0039-bounded-durability-and-memory-ceilings.md` (memory) and
`docs/decisions/0009-partitioning-multitenancy.md` (partitioning) in the engine repository, or the
config source itself. If a number here and the running server ever disagree, `GET /api/server/memory`
and the server's own startup log line are authoritative — this page explains what produced them.

---

## Memory: `MaxTotalRamBytes` and what it splits into

The server's memory budget is a fraction of **detected** host (or cgroup) memory, then split into a
governed budget, a per-database share, and per-category ceilings within that share. Two things move the
fraction: whether detection found a **real isolation boundary** (a cgroup v2/v1 limit — you were
explicitly granted this many bytes) or **fell back** (`GCMemoryInfo` or physical RAM — the host merely
*has* this much memory; nothing says you own it alone).

| Value | Formula | Restoring key |
|---|---|---|
| `MaxTotalRamBytes` (cgroup-bounded) | `0.70 × detected`, floor 256 MB | `Aouda:Memory:MaxTotalRamBytes` (set explicitly to skip detection) |
| `MaxTotalRamBytes` (fallback) | `0.40 × detected`, floor 256 MB | same |
| `RuntimeOverheadReserve` | `0.15 × configured`, floor `min(192 MB, 0.40 × configured)`, ceiling 4 GB | derived, not directly settable |
| Governed budget | `configured − RuntimeOverheadReserve` | derived |
| Per-database share (`T19`) | `governed × yourWeight / Σ everyone's weight` | `Aouda:Databases:<name>:MemoryWeight` (default `1.0`) |
| L2 hot-key cache ceiling (`T13`) | `0.05 × governed`, floor 4 MB, enforced as one **aggregate** across every keyed table in the database | derived — raise the database's share (above) or its `MemoryWeight` |
| Bulk-load ingest buffer budget | `clamp(0.04 × yourDatabaseShare, 8 MB, 256 MB)` | `Aouda:BulkLoad:IngestBufferBudgetFraction` |

Worked at three detected host sizes, both branches (all figures in MB unless marked GB; rounded to the
nearest whole MB):

| Detected host | 2 GB | 8 GB | 32 GB |
|---|---|---|---|
| `MaxTotalRamBytes` — cgroup-bounded (`0.70×`) | 1434 | 5734 | 22938 (22.4 GB) |
| `MaxTotalRamBytes` — fallback (`0.40×`) | 819 | 3277 | 13107 (12.8 GB) |
| `RuntimeOverheadReserve` — cgroup-bounded | 215 | 860 | 3441 |
| `RuntimeOverheadReserve` — fallback | 192 (floor binds) | 492 | 1966 |
| Governed budget — cgroup-bounded | 1219 | 4874 | 19497 (19.0 GB) |
| Governed budget — fallback | 627 | 2785 | 11141 (10.9 GB) |
| `T13` (L2 cache ceiling) — cgroup-bounded | 61 | 244 | 975 |
| `T13` — fallback | 31 | 139 | 557 |
| Per-DB share at 4 equal-weight databases — cgroup-bounded | 305 | 1219 | 4874 (4.8 GB) |
| Per-DB share at 4 equal-weight databases — fallback | 157 | 696 | 2785 (2.7 GB) |
| Ingest buffer budget — cgroup-bounded | 12 | 49 | 195 |
| Ingest buffer budget — fallback | 8 (floor binds) | 28 | 111 |

The per-database-share and ingest-buffer-budget rows assume four equal-weight databases on the server,
matching the worked-example convention in ADR 0039 §4 itself — with a different database count or
`MemoryWeight` set, the share scales accordingly (`GET /api/server/memory` reports the real number for
your actual registration, per database, alongside `memoryWeight` and `l2KeyCacheCeilingBytes`).

**Why the floor binds more often on the fallback branch.** A fallback-detected host derives a smaller
`configured` value for the same detected memory, so downstream floors (`RuntimeOverheadReserve`'s
192 MB, the ingest buffer budget's 8 MB) are reached at a larger detected-host size than on the
cgroup-bounded branch. This is expected, not a bug — the smaller fraction is the point.

---

## Bulk load

| Setting | Default | Config key | Notes |
|---|---|---|---|
| Segment seal size | 64 MB | `Aouda:BulkLoad:TargetSegmentBytes` | Fixed — matches every other segment the engine writes. Not derived from host size. |
| Concurrent segment-write I/O budget | `1` | `Aouda:BulkLoad:FlushConcurrency` | A **fixed constant**, not core-scaled. Measured: a higher value buys commit latency the phase does not need, at the expense of concurrent-query p95 during the load. |
| Single-node WAL frame emission | `false` (elided) | `Aouda:BulkLoad:EmitFramesOnSingleNode` | On a detected single-node topology, `LogShipSegments` no longer re-reads/hashes segment files or appends a WAL frame. See [Single-Node Deployment](single-node-deployment.md). |
| Job-shape warning — segment count | `64` | `Aouda:BulkLoad:JobShapeWarnSegmentThreshold` | Advisory only, never blocks a commit. See [Bulk Load — Reading `:commit completed`](bulk-load.md#reading-commit-completed-and-the-job-shape-warning). |
| Job-shape warning — median rows/segment | `1000` | `Aouda:BulkLoad:JobShapeWarnMedianRowsPerSegmentThreshold` | Same. |
| Post-load Materialized Query refresh | `Auto` | `BulkLoadOptions.PostLoadMqBehavior` | Triggers a dependent MQ rebuild after `BulkLoadCommitted`. Set `Skip` to defer refresh in a multi-step pipeline. |

---

## Partitioning

| Setting | Default | Config key | Notes |
|---|---|---|---|
| `PartitionOptions.StorageMode` | `Auto` | `partitionStorage` in the table's schema | Starts every partition key in a shared bucket; promotes a key to its own dedicated directory only if it individually crosses the thresholds below. |
| **Legacy-table exception** | implicit `Dedicated` | — | Applies only to a table created **before** the `Auto` default was introduced. Nothing migrates it automatically today — no automated tool exists yet. The supported route is manual: export, drop, re-create under a **different name** with the desired mode, reload. See [Bulk Load — Choosing partition storage mode](bulk-load.md#choosing-partition-storage-mode). |
| `PromotionRowThreshold` | 10,000,000 rows | `PartitionOptions.PromotionRowThreshold` | Auto-promotion trigger, per key. |
| `PromotionByteThreshold` | 1 GB | `PartitionOptions.PromotionByteThreshold` | Auto-promotion trigger, per key. |
| `InitialBucketCount` | `16` | `PartitionOptions.InitialBucketCount` | Number of shared buckets `Auto`/`Shared` routing starts with. |

See [Partitioning and Multi-tenancy](partitioning.md) for the full storage-mode and promotion reference.

---

## Related docs

- [Sizing memory and WAL](sizing.md) — the mental model this page's numbers plug into
- [Server configuration](server-configuration.md) — where each of these keys is set (`appsettings.json`, `AOUDA_*` env vars, CLI flags) and what survives a restart
- [Bulk Load](bulk-load.md) — sizing a session, choosing partition storage mode, reading `:commit completed`
- [Single-Node Deployment](single-node-deployment.md) — the one setting that changes bulk load's WAL-frame default, and what changes when a second node joins
- [Partitioning and Multi-tenancy](partitioning.md) — the full `PartitionOptions` reference
