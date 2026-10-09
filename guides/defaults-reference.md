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
| `MaxTotalRamBytes` (fallback) | `min(0.40 × detected, 0.70 × available)` at this boot, floor 256 MB. No grant: every boot under `BackPressure` logs one warning, and nothing is remembered across boots (**WorkloadCore, next train**) | same — or a container memory limit, which makes it the cgroup row |
| `RuntimeOverheadReserve` | `0.15 × configured`, floor `min(192 MB, 0.40 × configured)`, ceiling 4 GB | derived, not directly settable |
| Governed budget | `configured − RuntimeOverheadReserve` | derived |
| Per-database share (`T19`) | `governed × yourWeight / Σ everyone's weight` | `Aouda:Databases:<name>:MemoryWeight` (default `1.0`) |
| Page cache (`T12`) | `0.10 ×` each database's own share, floor 8 MB. **On** (**ColumnarRead, next train** — it was off in `Constrained`, the resource mode a database started in; the modes are deleted, **WorkloadCore S17, next train**) | `Aouda:Memory:PageCacheEnabled = false` turns the cache off |
| L2 hot-key cache ceiling (`T13`) | `0.05 × governed`, floor 4 MB, enforced as one **aggregate** across every keyed table in the database | derived — raise the database's share (above) or its `MemoryWeight` |
| Transient pool (`T15`) | `clamp(0.04 × governed, 4 MB, T9)`, `T9` being 90 % of the governed budget. One formula on every host (**WorkloadCore S17, next train** — `Abundant` raised the fraction to 0.15) | derived |
| Per-table flush trigger (`T16`) | `clamp(T11 / max(n, 4), min(1 MB, T11 / n), 64 MB)` — `T11` the write buffer's ceiling (15 % of governed, floor 16 MB), `n` the tables sharing it (**WorkloadCore S17, next train** — `Abundant` raised the ceiling to 1 GB) | derived |
| Per-table hot budget (`T18`) | `clamp(T10 / max(n, 4), min(8 MB, T10 / n), 1 GB)` — `T10` the hot ceiling (45 % of governed, floor 32 MB) (**WorkloadCore S17, next train** — `Abundant` raised the ceiling to 16 GB) | `Aouda:Memory:MaxHotBytes` sets `T10` |
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

(**BL-914, next train**) The memory broker frees memory when the live heap passes **0.80 × the heap limit (`T4`)** — and now
also when what the GC has committed after a compacting full collection passes **0.90 × `T4`**. Neither is configurable, and
neither refuses a write: both evict (key maps first). See [Sizing — when the GC heap gets tight](sizing.md#what-happens-when-the-gc-heap-gets-tight).

The reclaim ladder from [Sizing](sizing.md#what-happens-when-the-hot-tier-fills), key by key. The
server prints the ladder **as it is actually in force** in one startup line — read that rather than
your own configuration, because every non-boolean here self-clamps.

| Setting | Default | Config key | Notes |
|---|---|---|---|
| Hot admission seam | `true` | `Aouda:Memory:HotAdmissionEnabled` | Whether a flush asks the ceiling before creating a hot segment. `false` stops consulting it altogether — every flush writes hot first, as it did before P53. |
| ~~Rung 0 — drain acceleration~~ | — | ~~`Aouda:Memory:HotDrainAccelerationEnabled`~~ | **Removed (WorkloadCore S17, next train)** with rung 0: the hot tier is drained by the memory broker's hot-segment demotion under pressure and the demotion sweep at its plain interval. It ran the sweep up to 4× as often, to a lower target, above `T42`. |
| ~~`T42` — rung 0 water mark~~ | — | ~~`Aouda:Memory:HotDrainAccelerationWaterMark`~~ | **Removed (WorkloadCore S17, next train)** with rung 0. It was `0.60`. |
| `T43` — hot debt's soft line | `0.80` | `Aouda:Memory:HotPacingWaterMark` | (**WorkloadCore S16, next train**) The fraction of the hot ceiling above which hot bytes count as debt for the ingest stall curve (its hard line is the ceiling). `0` means the default. **Clamped to `[0.10, 1.0]` by the engine** (**WorkloadCore S17, next train**; it was `[T42, 1.0]`). |
| `T44` — stall horizon | `60 s` | `Aouda:Memory:IngestStallHorizon` | (**WorkloadCore S16, next train**) The ingest stall curve's horizon: a paced writer is never held below *(hard line − soft line) / T44*. Was `Aouda:Memory:HotControlHorizon`. Unset means the default. |
| `T45` — rate EWMA half-life | `30 s` | `Aouda:Memory:HotRateEwmaHalfLife` | Half-life of the arrival- and drain-rate averages. A time constant, not a share — every database samples on the same tick and must decay on the same half-life, or two databases' rates are not comparable. |
| `T41` — process hot ceiling | `true` | `Aouda:Memory:ProcessHotCeilingEnabled` | Bounds the **sum** of every database's hot tier, not only each one. Inert wherever the per-database ceilings already sum correctly; binds only where the 32 MB per-database floor has broken the sum. `false` bounds each database by its own ceiling alone. |
| Legacy hot-first flush | `false` | `Aouda:Memory:FlushAlwaysHotFirst` | `true` restores the pre-P53 flush whole, including hot-first flush for `ColdPreferred` tables. Measured on a 400 000-row load against a 2 MB hot ceiling: default produced 3 segments holding **0 B** resident hot; this flag produced 3 segments holding **17 700 000 B** — 8.8× the ceiling, unbudgeted. |
| Graph / vector bulk-load temperature | `ColdDirect` | `Aouda:BulkLoad:Temperature` | An edge or vector bulk load writes cold only. `HotAndCold` restores the previous behaviour, in which both built a hot segment for every segment written without consulting the ceiling. Ordinary **tabular** bulk loads were always cold-only and are unaffected. |

⚠️ **`T41` itself, and each database's share of it, are not configurable — only the switch is.** Both
are computed by the server's budget manager from the governed budget; an operator setting them by
hand could contradict the arithmetic the ceiling exists to enforce.

(**WorkloadCore S16, next train**) **`Aouda:Memory:HotPacingEnabled` is gone**, with the hot-only pacer it switched: the ingest
stall curve (sizing guide, *Debt slows the writer*) paces on hot bytes and on three other debts, is
always on, and is inert below every soft line — nothing is computed there, so a healthy server is never
slowed by it (300 000 rows on a healthy server: **0 waits**).

🔎 **Two keys are absent on purpose**, not missing: `ProcessHotCeilingAggregateBytes` and
`ProcessHotCeilingShareBytes`, for the reason in the first warning above.

⚠️ **An unknown key under `Aouda:Memory` is logged at boot** (**WorkloadCore S17, next train**). The configuration binder
ignores a key nothing reads, so a deployment still carrying a removed key — `HotDrainAccelerationEnabled`,
`HotDrainAccelerationWaterMark`, `ResourceMode`, `HotPacingEnabled`, `HotControlHorizon`, `PerClassAdmissionEnabled`,
`ElasticShares` — or a misspelt one would believe it governed something. The server now logs one warning per such key,
naming its full path (`Aouda:Memory:HotDrainAccelerationEnabled is not a known setting and is ignored: nothing reads it. …`).
The server starts as before; remove the key.

---

## WAL size ladder

Per WAL root, derived — none of these is a configuration key. See [Sizing — the WAL's cap](sizing.md#the-wals-cap-follows-the-disk-and-the-workload-bl-787-next-train)
and [Storage](storage.md) (walk-through D).

| Value | Formula | Notes |
|---|---|---|
| `MaxWalBytes` (`T23`) at open | `clamp(free / 10, min(256 MB, free / 4), 4 GiB)`, `free` the WAL volume's free bytes (256 MB when it cannot be read) | The opening cap. |
| `MaxWalBytes` (`T23`) after a reclaim | `max(clamp(A / 10, min(256 MB, A / 4), 4 GiB), min(2 × W, A / 2))`, `A` = free bytes + the WAL's own, `W` = the largest log size seen when retention reclaimed | (**BL-787, next train**) Recomputed at most once a minute, applied when it moves more than 5 %, and logged (`[WAL] MaxWalBytes … -> …`). Before, the open's value held for the life of the process. |
| `T24` — segment size | `clamp(T23 / 16, 8 MB, 64 MB)` | Fixed at open. |
| `T25` — force checkpoint | `0.70 × T23` | Also the WAL debt's soft line for the ingest stall curve. Moves with `T23`. |
| `T26` — run retention now | `0.85 × T23` | Moves with `T23`. |
| `T27` — refuse source writes | `0.95 × T23` | `503 WAL_CAPACITY_EXCEEDED` + `Retry-After` from the measured reclaim rate. Moves with `T23`. |
| `T28` — `MaxSlotWalKeepBytes` | `clamp(T23 / 2, 128 MB, 2 GiB)` | Fixed at open: a slot lagging further behind the head is invalidated. |

(**BL-787, next train**) Each crossing of `T25`, `T26` and `T27`, in either direction, and the end of a refuse episode (its
length and how many writes it refused) is one line in the server log, prefixed `[WAL]`.

---

## Bulk load

| Setting | Default | Config key | Notes |
|---|---|---|---|
| Segment seal size | 64 MB | `Aouda:BulkLoad:TargetSegmentBytes` | Fixed — matches every other segment the engine writes. Not derived from host size. |
| Concurrent segment-write I/O budget | `1` | `Aouda:BulkLoad:FlushConcurrency` | A **fixed constant**, not core-scaled. Measured: a higher value buys commit latency the phase does not need, at the expense of concurrent-query p95 during the load. |
| Single-node WAL frame emission | `false` (elided) | `Aouda:BulkLoad:EmitFramesOnSingleNode` | On a detected single-node topology, `LogShipSegments` no longer re-reads/hashes segment files or appends a WAL frame. See [Single-Node Deployment](single-node-deployment.md). |
| Job-shape warning — segment count | `64` | `Aouda:BulkLoad:JobShapeWarnSegmentThreshold` | Advisory only, never blocks a commit. See [Bulk Load — Reading `:commit completed`](bulk-load.md#reading-commit-completed-and-the-job-shape-warning). |
| Job-shape warning — median rows/segment | `1000` | `Aouda:BulkLoad:JobShapeWarnMedianRowsPerSegmentThreshold` | Same. |
| Post-load Materialized Query | `Auto` | `BulkLoadOptions.PostLoadMqBehavior` | (**WorkloadCore S10, next train**) Every load but a `Skip` one records a pending job, and the table's pass brings its queries current: `Auto` starts it at the commit (multi-table and transform loads included), `Deferred` after the quiet period (2 s quiet, at most 60 s). A load does no materialized-query work while it streams. Before S10, `Auto` accumulated affected MQs of all four types during the load and published after the commit, or, for a table whose every query is an aggregate or latest / first per key, the table's pass wrote them from a fold the load built (**WorkloadCore S09**); in 0.2.0 they were written in the load's own commit, before it returned (**ColumnarCore S12**). Wait on `mqRebuildStatus` / `MqRebuildCompleted`, or read with the commit's `token`; do not also `:refresh`. Set `Skip` to defer in a multi-step pipeline. |
| `:commit`'s wait for the load's queries | `30000` ms | `mqWaitMs` on `:commit` (`BulkLoadOptions.MqWait` in `Aouda.Client`) | (**WorkloadCore S09, next train**) How long `:commit` waits, after the load is durable and its locks are released, for the load's materialized queries to be current; `0` does not wait, at most `600000`. Holds no lock and refuses nothing; the response's `mqStatus` says whether they were current. |
| ~~Ingest-fed MQ reservation floor~~ | — | ~~`Aouda:BulkLoad:MqIngestReservationFloorBytes`~~ | **Removed (WorkloadCore S10, next train)** with the ingest-fed feed: a load's queries are brought current by the table's pass, which reserves its own waves. It was the opening `Transient` reservation per destination table (1 MB). |
| ~~Ingest-fed MQ reservation ceiling~~ | — | ~~`Aouda:BulkLoad:MqIngestReservationCeilingBytes`~~ | **Removed (WorkloadCore S10, next train)** with the ingest-fed feed. It capped the feed's live accumulator bytes (`0` = no dedicated cap). |
| ~~Ingest-fed MQ accumulator budget~~ | — | ~~`Aouda:Memory:MqIngestAccumulatorBytes`~~ | **Removed (WorkloadCore S10, next train)** with the ingest-fed feed; it was meaningful only to the feed's accumulators. |

---

## Materialized-query maintenance

| Setting | Default | Config key | Notes |
|---|---|---|---|
| ~~In-commit maintenance of an insert~~ | — | — | **Removed (WorkloadCore S09, next train)**: every commit hands its batch to its queries' maintainers and they apply it in the background; read with the write's consistency token to wait for them. In 0.2.0 (**ColumnarMerge S11**) an insert wrote its table's aggregate and latest / first-per-key queries before it returned. |
| Maintenance backlog bound | 64 MiB per update lane | — (`SubscriptionManagerOptions.MaintenanceBacklogMaxBytes`, engine wiring) | (**WorkloadCore S09, next train**) A lagging query's batches wait in a backlog charged on the memory budget, never dropped below this bound; past it the query is marked stale (`Maintenance backlog past its bound …`) and rebuilt. Replaces the 250 ms wait and drop at a full queue (BL-427). |
| Freshness window | `0` ms | `maxCoalesceMs` on the query (`aouda.schema.json`) | 0–60000. How long an `Async` query's batches may wait to be applied together (**ColumnarMerge S10, 0.2.0**). See [Materialized queries](materialized.md#27-core-concepts-and-mental-model). |
| Resident result rows | 262,144 keys per query | — | An aggregate's or latest / first-per-key query's rows kept in RAM between commits, charged to the memory governor, least recently touched evicted (**ColumnarMerge S10, 0.2.0**). |
| Result checkpoint | every 15 s, and at clean shutdown | — | What a restart restores a current result from (**ColumnarMerge S08, 0.2.0**). |
| Rebuild grant | 1 MB to start, doubling to at most ¼ of the database's governed budget | `Aouda:MaterializedQueries:Rebuild:ReservationFloorBytes` (the start) | (**WorkloadCore S12, next train**) A rebuild's memory; past it the build splits into `Aouda:MaterializedQueries:Rebuild:MaxPartitions` (64) partitions and spills. `ReservationCeilingBytes`, `SpillEnabled` and `PartitioningEnabled` are removed. See [Materialized queries](materialized.md#211b-what-a-rebuild-costs-and-what-bounds-it). |
| Deferred-pass quiet window | 2 s with no load in flight or committed; 60 s bound | — | (**ColumnarMerge S01, 0.2.0** — a load still streaming no longer counts as quiet.) |
| Deferred-pass workers | the CPU budget | `Aouda:Cpu:ConfiguredCores` (or the probed quota) | Read when the work starts (**ColumnarCore S15, 0.2.0**); was the machine's core count capped at 16 / 8. An insert no longer writes queries side by side: in-commit maintenance is deleted (**WorkloadCore S09, next train**). See [Sizing CPU](sizing.md#sizing-cpu). |

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

## Work classes

Every memory reservation carries a work class — `Interactive`, `Streaming`, `Ingest`, `Background`, `Maintenance` — and
that is the order the memory grant queue serves them in: first in, first out within a class, and a running unit's next step
is taken only if nothing of the same or a higher class is waiting — a read's only if nothing of a higher class is, and a
request blocked by its own database's cap holds back only that database (**BL-861, WorkloadCore S18, next train**; see
[Sizing](sizing.md#memory-is-granted-before-work-starts-and-small-writes-have-a-reserve-workloadcore-s06-next-train)).

(**WorkloadCore S06, next train**) **Classes no longer have entitlements.** The per-class shares of the transient budget
(`Interactive` 0.35, `Streaming` 0.05, `Ingest` 0.25, `Background` 0.25, `Maintenance` 0.10, with different fractions in
the `Abundant` resource mode), borrowing of idle headroom between classes, and `Aouda:Memory:PerClassAdmissionEnabled` are
removed; a class orders the queue and does not cap what it may hold. The resource modes those fractions differed by are
deleted too (**WorkloadCore S17, next train**).

## Background page scrubber

The cold-page CRC scrubber (**BL-815, next train**) is maintenance work: it takes the `Maintenance` class above and yields while queries are waiting. Not configurable. See [Storage](storage.md#213-operations-and-observability) for what it reports.

| Setting | Default | What it means |
|---|---|---|
| First pass | 15 minutes after the database opens | Open and recovery are left alone, and a short-lived process does no scrubbing |
| Pass interval | 24 hours, start to start | Each pass reads every cold page of the tables currently loaded |
| Read rate | at most 64 MiB/s | A 100 GB database is checked in about half an hour |

## Logging defaults

⚠️ **Aouda's default log level is `Warning`.** Nothing below that is emitted unless you ask for it — so on a server with no `appsettings.json` and no `Logging__LogLevel__*` environment variable, `Information` and `Debug` lines simply are not there.

That is worth stating plainly, because **a line the documentation says exists and that you cannot see is far more likely to mean "filtered out" than "it did not happen"**.

| Category | Default level | Why |
|---|---|---|
| Everything, unless listed below | `Warning` | A production server should be quiet. A chatty default costs disk and buries the lines that matter |
| Startup narration (`Aouda.Server.Startup.*`) | `Information` | The memory and CPU budget derivations, the database inventory, and the readiness transition. You cannot diagnose a sizing problem from a log that does not say what was derived |
| The bulk-load commit line | `Information` | `BulkLoad :commit completed …` is how a loader confirms a session landed, and it is documented as such in [Bulk Load](bulk-load.md) |

### Turning it up

Standard ASP.NET Core configuration — no Aouda-specific mechanism:

```bash
# Everything at Information
AOUDA__LOGGING__LOGLEVEL__DEFAULT=Information

# Or one category, which is usually what you want
Logging__LogLevel__Aouda.Engine.Storage=Debug
```

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Warning",
      "Aouda.Server.Startup": "Information"
    }
  }
}
```

⚠️ **Turn one category up, not `Default`.** `Default=Debug` on a busy server produces a volume that is hard to read and expensive to keep, and the line you are looking for is usually in one namespace.

### Where the lines go

Aouda logs to the console, structured as JSON. Under systemd that is `journalctl -u aouda`; under Docker it is `docker logs`; under the Windows SCM it is the service's stdout. There is no file sink by default and no log rotation to configure, because there is no file.

## Related docs

- [Sizing memory and WAL](sizing.md) — the mental model this page's numbers plug into
- [Materialized queries](materialized.md#where-a-materialized-querys-result-lives) — where a query's result table lives, and why the default changed
- [Server configuration](server-configuration.md) — where each of these keys is set (`appsettings.json`, `AOUDA_*` env vars, CLI flags) and what survives a restart
- [Bulk Load](bulk-load.md) — sizing a session, choosing partition storage mode, reading `:commit completed`
- [Single-Node Deployment](single-node-deployment.md) — the one setting that changes bulk load's WAL-frame default, and what changes when a second node joins
- [Partitioning and Multi-tenancy](partitioning.md) — the full `PartitionOptions` reference
