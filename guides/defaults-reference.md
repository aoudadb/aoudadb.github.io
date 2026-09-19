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
| Bulk-load ingest buffer budget | `max(0.04 × yourDatabaseShare, 8 MB)`, growing with headroom in the server's shared memory governor instead of stopping at a fixed number (P45) | `Aouda:BulkLoad:IngestBufferBudgetFraction`, or `Aouda:BulkLoad:MaxIngestBufferBudgetBytes` to pin an explicit ceiling (`268435456` reproduces the old fixed-256 MB behavior) |

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

**The ingest-buffer-budget row above is unaffected at all three host sizes in the table.** P45 removed
the old fixed 256 MB ceiling, but every figure in the row (8–195 MB) was already well under it — the
change only matters once `0.04 × yourDatabaseShare` itself exceeds 256 MB, which needs a considerably
larger governed budget than 32 GB affords at these weights.

---

## Hot tier and ingest admission

The reclaim ladder from [Sizing](sizing.md#what-happens-when-the-hot-tier-fills), key by key. The
server prints the ladder **as it is actually in force** in one startup line — read that rather than
your own configuration, because every non-boolean here self-clamps.

| Setting | Default | Config key | Notes |
|---|---|---|---|
| Hot admission seam | `true` | `Aouda:Memory:HotAdmissionEnabled` | Whether a flush asks the ceiling before creating a hot segment. `false` stops consulting it altogether — every flush writes hot first, as it did before P53. |
| Rung 0 — drain acceleration | `true` | `Aouda:Memory:HotDrainAccelerationEnabled` | Sweeps more often and demotes to a lower target above the water mark. Costs disk I/O only; **no writer is ever delayed by it**. `false` restores the previous fixed-cadence sweep exactly. |
| `T42` — rung 0 water mark | `0.60` | `Aouda:Memory:HotDrainAccelerationWaterMark` | Hot-occupancy fraction at which rung 0 begins. `0` means the default. The response is proportional: nothing at all at the mark, rising to a 4× sweep with a halved target near the ceiling. |
| Rung 1 — ingest pacing | **`false`** | `Aouda:Memory:HotPacingEnabled` | ⚠️ **Ships off.** See the note below. |
| `T43` — rung 1 water mark | `0.80` | `Aouda:Memory:HotPacingWaterMark` | `0` means the default. **Clamped to `[T42, 1.0]` by the engine**, so you cannot invert the ladder and make pacing the first answer to pressure. |
| `T44` — control horizon | `60 s` | `Aouda:Memory:HotControlHorizon` | The horizon the admissible arrival rate is computed over: *drain rate + (ceiling − resident) / T44*. Unset means the default. |
| `T45` — rate EWMA half-life | `30 s` | `Aouda:Memory:HotRateEwmaHalfLife` | Half-life of the arrival- and drain-rate averages. A time constant, not a share — every database samples on the same tick and must decay on the same half-life, or two databases' rates are not comparable. |
| `T41` — process hot ceiling | `true` | `Aouda:Memory:ProcessHotCeilingEnabled` | Bounds the **sum** of every database's hot tier, not only each one. Inert wherever the per-database ceilings already sum correctly; binds only where the 32 MB per-database floor has broken the sum. `false` bounds each database by its own ceiling alone. |
| Legacy hot-first flush | `false` | `Aouda:Memory:FlushAlwaysHotFirst` | `true` restores the pre-P53 flush whole, including hot-first flush for `ColdPreferred` tables. Measured on a 400 000-row load against a 2 MB hot ceiling: default produced 3 segments holding **0 B** resident hot; this flag produced 3 segments holding **17 700 000 B** — 8.8× the ceiling, unbudgeted. |
| Graph / vector bulk-load temperature | `ColdDirect` | `Aouda:BulkLoad:Temperature` | An edge or vector bulk load writes cold only. `HotAndCold` restores the previous behaviour, in which both built a hot segment for every segment written without consulting the ceiling. Ordinary **tabular** bulk loads were always cold-only and are unaffected. |

⚠️ **`T41` itself, and each database's share of it, are not configurable — only the switch is.** Both
are computed by the server's budget manager from the governed budget; an operator setting them by
hand could contradict the arithmetic the ceiling exists to enforce.

⚠️ **Rung 1 ships off, and that is a decision rather than an oversight.** It is the first rung that
can make a *healthy* workload slower if a constant is wrong, and two of its three constants (`T43`,
`T44`) are carried from Apache Kudu rather than derived from Aouda's own arithmetic. The safety case
is made — it cannot engage below `T43` **by construction** (the controller returns before the rate is
computed), and a healthy server ingesting 300 000 rows in 1.4 s with the flag on took **0 delays and
0 refusals**. The sizing case is not: nothing in the engine's own suites derives `T43` or `T44` from a
sustained production ingest. Turn it on deliberately if your drain is not keeping up; leave it off if
you have not measured.

🔎 **Two keys are absent on purpose**, not missing: `ProcessHotCeilingAggregateBytes` and
`ProcessHotCeilingShareBytes`, for the reason in the first warning above.

---

## Bulk load

| Setting | Default | Config key | Notes |
|---|---|---|---|
| Segment seal size | 64 MB | `Aouda:BulkLoad:TargetSegmentBytes` | Fixed — matches every other segment the engine writes. Not derived from host size. |
| Concurrent segment-write I/O budget | `1` | `Aouda:BulkLoad:FlushConcurrency` | A **fixed constant**, not core-scaled. Measured: a higher value buys commit latency the phase does not need, at the expense of concurrent-query p95 during the load. |
| Single-node WAL frame emission | `false` (elided) | `Aouda:BulkLoad:EmitFramesOnSingleNode` | On a detected single-node topology, `LogShipSegments` no longer re-reads/hashes segment files or appends a WAL frame. See [Single-Node Deployment](single-node-deployment.md). |
| Job-shape warning — segment count | `64` | `Aouda:BulkLoad:JobShapeWarnSegmentThreshold` | Advisory only, never blocks a commit. See [Bulk Load — Reading `:commit completed`](bulk-load.md#reading-commit-completed-and-the-job-shape-warning). |
| Job-shape warning — median rows/segment | `1000` | `Aouda:BulkLoad:JobShapeWarnMedianRowsPerSegmentThreshold` | Same. |
| Post-load Materialized Query | `Auto` | `BulkLoadOptions.PostLoadMqBehavior` | `Auto` accumulates affected MQs of all four types during the load and publishes at commit. Wait on `mqRebuildStatus` / `MqRebuildCompleted`; do not also `:refresh`. Set `Skip` to defer in a multi-step pipeline. |
| Ingest-fed MQ reservation floor | 1 MB | `Aouda:BulkLoad:MqIngestReservationFloorBytes` | Opening `Transient` reservation per destination table, and the size growth doubles from. Unconfigured = the S04 constant. |
| Ingest-fed MQ reservation ceiling | `0` (no dedicated cap) | `Aouda:BulkLoad:MqIngestReservationCeilingBytes` | `0` = the `Transient` governor is the bound. A positive value that live accumulator bytes would exceed falls those queries back to a scan-fed rebuild; the load still commits. |

---

## Partitioning

| Setting | Default | Config key | Notes |
|---|---|---|---|
| `PartitionOptions.StorageMode` | `Auto` | `partitionStorage` in the table's schema | Starts every partition key in a shared bucket; promotes a key to its own dedicated directory only if it individually crosses the thresholds below. |
| **Legacy-table exception** | implicit `Dedicated` | — | Applies only to a table created **before** the `Auto` default was introduced. Nothing migrates it automatically today — no automated tool exists yet. The supported route is manual: export, drop, re-create under a **different name** with the desired mode, reload. See [Bulk Load — Choosing partition storage mode](bulk-load.md#choosing-partition-storage-mode). |
| `PromotionRowThreshold` | 10,000,000 rows | `PartitionOptions.PromotionRowThreshold` | Auto-promotion trigger, per key. |
| `PromotionByteThreshold` | 1 GB | `PartitionOptions.PromotionByteThreshold` | Auto-promotion trigger, per key. |
| `InitialBucketCount` | `16` if the partition key is time-bounded, `128` otherwise (P45) | `PartitionOptions.InitialBucketCount` / schema `initialBucketCount` | Number of shared buckets `Auto`/`Shared` routing starts with. Fixed for the life of the table. See [Partitioning and Multi-tenancy](partitioning.md#choosing-initialbucketcount-at-scale-p45) for the full rule. |

See [Partitioning and Multi-tenancy](partitioning.md) for the full storage-mode and promotion reference.

---

## Class entitlements

Every memory reservation carries a work class, and each class has a share of the transient budget. The fractions differ by resource mode because `Abundant` puts the extra where headroom buys speed — buffering.

| Class | `Constrained` / `Balanced` | `Abundant` | What it covers |
|---|---|---|---|
| `Interactive` | 0.35 | 0.30 | Query result materialisation, grouped-aggregate state, sort buffers |
| `Streaming` | 0.05 | 0.05 | Fan-out projections. High preference, low entitlement |
| `Ingest` | 0.25 | 0.30 | Bulk-load and insert buffering |
| `Background` | 0.25 | 0.25 | Materialized-query rebuilds, index rebuilds |
| `Maintenance` | 0.10 | 0.10 | Compaction and cold-merge buffers |

Each column sums to 1.00, which is a contract rather than a coincidence: a table summing to less silently strands budget, and one summing to more silently over-commits.

**A class may borrow idle headroom.** A sole claimant's ceiling is the whole governed budget, so nothing is stranded when only one kind of work is running. From the second claimant onward each borrower takes at most half the idle remainder, so a second borrower can always start and no claimant faces a cliff on its first byte.

## Related docs

- [Sizing memory and WAL](sizing.md) — the mental model this page's numbers plug into
- [Materialized queries](materialized.md#where-a-materialized-querys-result-lives) — where a query's result table lives, and why the default changed
- [Server configuration](server-configuration.md) — where each of these keys is set (`appsettings.json`, `AOUDA_*` env vars, CLI flags) and what survives a restart
- [Bulk Load](bulk-load.md) — sizing a session, choosing partition storage mode, reading `:commit completed`
- [Single-Node Deployment](single-node-deployment.md) — the one setting that changes bulk load's WAL-frame default, and what changes when a second node joins
- [Partitioning and Multi-tenancy](partitioning.md) — the full `PartitionOptions` reference
