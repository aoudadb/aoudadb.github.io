---
title: "Sizing memory and WAL"
nav_order: 7
parent: "Guides"
---

# Sizing the server budget

Aouda treats `MaxTotalRamBytes` as a **process RSS ceiling**, not an advisory subtotal. Leave it unset and the server derives it from detected host (or cgroup) memory: **70%** when detection found a real cgroup isolation boundary, **40%** when it fell back to physical RAM (a fallback result proves nothing about how much of the host Aouda actually owns). Set it explicitly when you need a pinned number. Resize live from Studio (Settings → Server), `PATCH /admin/config`, or `aouda budget`. See the [Defaults Reference](defaults-reference.md) for every downstream number this derives (governed budget, per-database shares, the L2 cache ceiling, the bulk-load ingest buffer budget) worked at several host sizes.

## Small hosts (under 1 GB)

Give the process only what remains after the OS. Flush and hot-tier thresholds scale with the budget, so many tables do not each assume a large in-memory buffer. Prefer `ColdPreferred` for archival tables. Ingest will throttle sooner than on a large box — that is the process staying up, not a crash.

Two costs do not scale with the budget (**WorkloadCore, next train**). The server itself — the runtime, ASP.NET, pooled buffers —
holds 10–20 MB of managed heap that no reservation covers. And **every sign-in or password change holds 64 MiB while its
password hash runs** (Argon2id, a few hundred milliseconds): a burst of sign-ins on a 512 MB container is a real share of its
heap. Both are visible on `GET /api/server/memory` (`chargedByConsumer.PasswordHashing`; the rest of the gap in
`untrackedAtLastGen2Bytes`). Token refreshes do not hash.

## Typical (~2 GB)

A 2 GiB cap is a reasonable **explicit** choice, not a hidden default. Hot data stays in RAM; colder segments demote. Watch RSS versus the governed budget in Studio Settings and Monitoring.

## Large hosts

Set an explicit ceiling so Aouda does not grow into all remaining RAM. Per-database `maxMemoryBytes` on HTTP create (config: `MaxMemoryShareBytes`) is a **cap on that database's share** of the one server budget, not a second independent heap.

## Sizing CPU

Aouda sizes its query parallelism from the cores it believes it has, and **a container with CPU shares but no CPU limit does not have the cores it appears to have.** With no quota to read, the process falls back to the machine's core count — which on a shared node describes the node, not your share. Every scan then plans for hardware you do not own, and the symptom is latency under co-tenancy rather than an error, which is why it is easy to miss.

Set a limit: Kubernetes `resources.limits.cpu`, `docker --cpus`, or `Aouda:Cpu:ConfiguredCores` if neither is available. The server states what it found in one startup line:

```
CPU budget derivation: machine=28, quota=none, configured=none, schedulable=28,
  source=ProcessorCount — no CPU quota found; sizing from the machine's cores.
  Set a CPU limit or Aouda:Cpu:ConfiguredCores if this process is co-tenanted.
```

`GET /api/server/memory` carries the same facts under `cpu`, with `source` naming where `schedulableCores` came from: `Configured`, `CgroupV2`, `CgroupV1` or `ProcessorCount`. **`source` is the field to read** — a core count alone cannot tell a real 8-core allocation from 8 cores you are sharing with twenty-eight other containers.

Aouda's Helm chart sets `limits.cpu` and is therefore safe by default; `docker-compose` sets nothing, so a compose deployment on a shared host should set `--cpus` or `ConfiguredCores`.

**Materialized-query maintenance follows the same budget (**ColumnarCore S15, 0.2.0**).** The deferred pass's
workers (and its fold chunks) come from this CPU budget (**WorkloadCore S09, next train**: an insert no longer writes
queries side by side — its queries are maintained in the background, after its commit) —
`Aouda:Cpu:ConfiguredCores` or the probed quota, read when the work starts — instead of the machine's core count capped
at 16 / 8. A server given four cores no longer schedules sixteen workers on them, and one given sixteen of twenty uses
them.

**Background work shares one scheduler per server, and takes its share of that budget, not all of it (**WorkloadCore S15,
next train**).** Flushes, cold merges, the hot tier's demotion, WAL and result checkpoints, WAL retention and archiving, the
segment scrubber, and every materialized-query pass and rebuild run as jobs of one scheduler per server process — shared by
all its databases — in six classes, each with half the CPU budget's cores (at least two) as concurrent slots. A running job
holds a degree of parallelism from the same CPU admission queries use, so a deferred pass no longer takes every core of the
budget: an `Auto` load's pass, which the client's `:commit` waits on, gets ingest's share (half the cores); a pass nobody
waits on gets background's (three quarters of the cores when the server is otherwise idle, one while client requests are
running). Background work yields to client requests in proportion to its own cost, and work that frees memory or log —
flushes, demotion, checkpoints — is never slowed by memory pressure. Cold merges and WAL archiving run in the housekeeping
class, so a long merge or upload on one database never holds up another database's flushes or checkpoints, and a checkpoint
waits only for flushes already running (**WorkloadCore group 5 review, next train**). Many databases on one server therefore no longer each
run their own background loops at full width; nothing needs configuring.

### Garbage collection (**ColumnarCore S14, 0.2.0**)

The server runs .NET's **Server GC with DATAS** (dynamic adaptation) and a heap hard limit of 85 % of the memory it may
use; that is in its `runtimeconfig`, so nothing needs setting. Measured on 4 pinned cores with the write paths now
allocating about 0.4–2.4 KB per row: GC pauses stay under 5 % of wall time on bulk loads, inserts and inserts with nine
materialized queries (0.9–4.9 %). Workstation GC, Server GC without DATAS and a larger gen-0 budget
(`DOTNET_GCgen0size`) were measured beside it and none was consistently cheaper, so the default stands.

**If you embed the engine in your own process** (the embedded package, or `AoudaEngine` directly), your application's
GC settings apply, and .NET's default is Workstation GC. Turn Server GC on (`<ServerGarbageCollection>true</ServerGarbageCollection>`
in the project, or `DOTNET_gcServer=1`): an in-process insert of 2,000-row batches measured 1.8 CPU-s per million rows
with it and 2.5 without, with GC pauses at 0 % instead of 4 %.

## Open files (**IngestAtSpeed S02, 0.1.40**)

Aouda keeps a file per column per segment, plus the WAL, key maps and spill runs, so a large load
can reach the common soft limit of **1024 open files**. The symptom is `No file descriptors
available` on whatever file came next. On Derive's lab it was a `pk_keymap.dat`, just before the
process ran out of memory.

At startup the server raises its own soft `RLIMIT_NOFILE` to the hard limit (capped at 1,048,576)
and logs one line:

```
Open-file limit: soft 1024 -> 1048576 (hard 1048576).
```

**The hard limit is yours to set.** A process cannot raise its hard limit. For a container, pass
`--ulimit nofile=1048576:1048576` (Docker) or set it in the runtime. A systemd install already sets
`LimitNOFILE`. If the log line reports a hard limit near 1024, raise it there.

`GET /api/server/metrics` reports current usage under `process`: `openHandles`,
`fileDescriptorSoftLimit` and `fileDescriptorHardLimit`. The two limits are `-1` on Windows, which
has no such limit.

## Inserts and their materialized queries (**BatchFirst S13, 0.1.40**)

An insert is cheap; what it costs you is the materialized queries over its table, which are brought
up to date with every commit. Size for the queries, not for the insert.

Measured on the reference benchmark — four cores, insert-many into a trade table in batches of 2,000,
nine queries over it (six aggregates, a latest-per-key, two top-Ns over an aggregate's result):

| Offered rate | Held | CPU per million rows | Query lag / staleness p99 |
|---|---|---|---|
| 10,000 rows/s | yes | ~80 CPU-s | < 0.1 s |
| 50,000 rows/s | in one of two runs (~40,000 rows/s achieved otherwise) | 67–73 CPU-s | ~0.1 s |

The 50,000 rows/s row is **ColumnarMerge S11 / S11b (0.2.0)**; before it, the same rate was accepted while the
queries fell ~34 s behind during the burst. (**WorkloadCore S09, next train**) Both rows were measured with the insert maintaining its queries
inside its own commit, which is removed (next bullet).

- **The queries follow the insert, off its commit (**WorkloadCore S09, next train**).** An insert hands its change batch to its
  queries' maintainers at the commit and returns; they apply it in the background, so right after an insert its
  queries may be a moment behind (read with its consistency token to wait for them). A rate above what the queries
  can keep up with shows up as lag and as a maintenance backlog charged on the memory budget; past the backlog's
  bound (64 MiB an update lane) a query is marked stale and rebuilt. In 0.2.0 (**ColumnarMerge S11**) an insert
  maintained its table's aggregates and latest / first-per-key queries inside its own commit: they were current when
  it returned, and a rate above what the writer plus its queries could do showed up as a lower achieved rate. Watch
  `stalenessMs` on `GET /api/databases/{db}/materialized-queries/{name}` — how old the oldest change the query does
  not yet reflect is (**ColumnarMerge S01, 0.2.0**); `currentLag` is how long it has been behind without a
  break, which under a steady stream grows however promptly each commit is applied.
- **Batch.** 1,000–5,000 rows per call. Each commit is maintained as one batch per query, so small
  commits pay the per-commit cost many times over.
- **Fewer, narrower queries are cheaper than a bigger machine.** Cost is per query per commit; a query
  nobody reads still costs its share.
- **A load, not a stream, is better done as a bulk load.** Bulk loads fold their rows into the queries
  in one pass (see [bulk load](bulk-load.md)); at the same four cores that is ~50k
  rows/s end to end *with the queries current*. (**WorkloadCore S10, next train**) An `Auto` load's queries are brought
  current by the table's pass, started at the commit — the load itself does no materialized-query work while it
  streams — and `:commit` waits for them up to `mqWaitMs` (30 s by default); in 0.2.0 (**ColumnarCore S12**) the load
  folded them while it wrote its segments and returned with them written. A query the pass cannot fold or replay is
  rebuilt by a background job after the pass (**WorkloadCore S17, next train**).
- A table keyed by an increasing id (an `autoIncrement` column, a sequence) no longer pays a
  uniqueness probe per stored segment per row: since BatchFirst S13 a batch's key range is checked
  against each segment once. (**ColumnarMerge S02, 0.2.0**) An id the engine allocates is not
  probed at all: it is unique by construction.

### Auto-increment ids on time series (**ColumnarMerge S02, 0.2.0**)

An `autoIncrement` id costs almost nothing on write: ids are allocated as one range per batch and
stored delta-bit-packed, about 2 bits a row. On a bulk load of column batches it is written as a column;
before this train it cost ~0.7–1 CPU-second per million rows. It is still a column: it takes storage and
a primary-key index, and on a time series it is rarely what anyone reads by. **Where the data has a
natural key — `(series, time)` — prefer it as the primary key.** Keep the id where you need one (many
setups default to it; it is fully supported).

An **explicit** value in an `autoIncrement` column now moves the column's counter before it is stored,
so the engine never allocates it again (an explicit `100` followed by an automatic id gives `101`). An
explicit value at or below the counter — reusing a freed id — makes that table's automatic inserts
probe for uniqueness again until the next restart.

### The key map: RAM for keyed writes (**ColumnarMerge S05, 0.2.0**)

A table with a primary key and `pkUniqueness: Strict` (the default) keeps its keys in memory across every
tier, so an insert, upsert or materialized-query update learns whether a key exists without reading a
segment. Budget **60–110 bytes per key** of the table's cold data — about 60 when the map's dictionary is full, up to
~110 right after it doubles (1 million keys ≈ 60–110 MB; the write buffer and hot segments were already covered).
The map is charged what it actually holds, its dictionary's capacity included (**WorkloadCore, next train**; it was charged a
flat 64 bytes per key, which a heap census measured at 84 on a working load). The memory comes from the same governed budget as the rest
of the key index, and more RAM means more tables answered from memory: when the governor refuses, a table
simply keeps checking keys by reading its segments — correct, and slower — and `keyMapResident: false` on
`GET /api/tables` says so. The map is rebuilt in the background after a restart; nothing is stored on disk.

The map is also memory the server takes back when something else needs it (**WorkloadCore, next train**): under
pressure it evicts the map's partitions — one per cold segment — **least recently used first, across every table of the
database**, after the page cache, bloom filters and metadata and before demoting hot segments (which writes data); a
background load stops when that happens rather than evict what it has just loaded. A key in an evicted segment
is checked by reading that segment, as before the map covered it, and the next check schedules the segment's partition to
load again; `keyMapResident` reads `false` meanwhile. An upsert or a materialized-query update that meets one decodes the
segment's key columns and covers it before it writes — a one-off cost per segment, much less than checking key by key.
The old limit that stopped a map growing once key maps and resident query state held 40 % of the database's budget is
gone: what bounds the map is the memory budget itself.

### Declared decimals are half the size (**ColumnarCore S13, 0.2.0**)

An undeclared `Decimal` costs 16 bytes per value in the write buffer, the hot tier and every materialized result
that carries it, and compresses poorly on disk. A `Decimal(p,s)` column (`"precision"` / `"scale"`, p ≤ 18 — see the
[schema guide](schema.md)) is a scaled 64-bit integer: 8 bytes in memory, and encoded like an `Int64` in
segments — frame-of-reference or delta bit-packing chosen per 2,048-row vector (**ColumnarRead, next train**) (a price column of cents typically takes 2–3 bytes per value on disk). Declare prices, amounts and rates
that have a fixed number of places this way; keep the undeclared `Decimal` for values that need more than 18 digits.

## The buffering thresholds are one formula in every deployment (**WorkloadCore S17, next train**)

A server's buffering is sized by the same formulas on every host:

| Threshold | Formula |
|---|---|
| `T15` — the transient pool | `clamp(0.04 × governed, 4 MB, T9)` |
| `T16` — a table's flush trigger | `clamp(T11 / max(n, 4), min(1 MB, T11 / n), 64 MB)` |
| `T18` — a table's hot budget | `clamp(T10 / max(n, 4), min(8 MB, T10 / n), 1 GB)` |

`n` is the number of tables sharing the budget, `T9` the target RAM (90 % of the governed budget), `T10` the hot ceiling
(45 %) and `T11` the write buffer's ceiling (15 %).

Until this change Aouda measured its own headroom — the governed budget over a decayed maximum of the process's resident
set — and moved between three **resource modes**, `Constrained`, `Balanced` and `Abundant`; `Abundant` raised the transient
pool to 15 % of the governed budget, the flush trigger's ceiling to 1 GB and a table's hot budget's to 16 GB. That
second, host-driven sizing is **deleted**: the grants work asks for and the memory broker's weights size memory now (see
*Memory is granted before work starts* below), and a host with headroom no longer gets larger buffers. Gone from `GET /api/server/memory` with it: `resourceMode`, `headroomRatio`, `resourceModeTransitions` and the
whole `headroom` block; from the `memory` health component's details: `resourceMode`, `headroomRatio`,
`headroomGovernedBytes`, `workingSetHighWaterBytes` and `workingSetSource`; and the `Aouda:Memory:ResourceMode` key, which
pinned the mode. A dashboard or alert reading any of them reads nothing now.

🔎 **What to read instead**, when the server seems to have more room than it is using: `reservedBytes` and `ledgerBytes`
(what the ledger holds), `managedHeapBytes` and `untrackedHeadroomBytes` (the live heap, and what of it the ledger does not
hold), `rssBytes`, and `grants` (what is waiting for memory).

## Where the budget itself came from (**BL-611, 0.1.37**)

`GET /api/server/memory` now carries a `budgetDerivation` block recording how `MaxTotalRamBytes` was
arrived at: `source`, `isCgroupBounded`, the `fractionApplied`, both host readings, whether the
availability clamp bound, and a one-sentence `explanation`. The same facts appear in the `memory`
health component's `details`.

⚠️ **`availabilityClampBound: true` is the one worth alerting on.** It means the budget was
decided by what happened to be free at the instant the process started — a moving measurement —
rather than by a grant. Aouda says so once, in a startup warning; the block is how you check it on a
server whose startup logs have long since rotated. The remedy is a container memory limit, after
which Aouda derives **70 % of a number nobody else can spend** instead of 40 % of a machine it
shares.

⚠️ **Nothing re-derives the budget.** `derivedAtUtc` is always startup. On an unbounded host that
means the ceiling is fixed from a reading that has since moved; restart to re-derive it.

⚠️ **A grant is a deployment requirement for `BackPressure`** (**WorkloadCore, next train**; ADR 0060 `D-6`). Production
enforcement needs either a container memory limit or `Aouda:Memory:MaxTotalRamBytes`. Without one, the budget is the
boot's sample — `min(0.40 × total, 0.70 × available)` — **every boot logs one warning** saying so and naming both remedies,
and nothing is remembered across boots: a restart while a neighbour is busy can derive a smaller budget. That is the honest
consequence of running without a grant, and the warning is there so it is not a hidden one. An over-committed host stays a
refusal inside Aouda rather than a kernel OOM kill. `Advisory` enforcement (embedded, `aouda dev`) enforces nothing and does
not warn.

⚠️ **If you resize `MaxTotalRamBytes` at runtime, the block keeps describing startup.** That is
deliberate — you chose the new number, so there is no host derivation to record — but it means
`effectiveBytes` (the startup decision) and `currentEffectiveBytes` (the budget running now) can
differ. `isStillInForce` is `false` when they do, and the `explanation` says `Superseded:`. Gate any
alert on `availabilityClampBound` behind `isStillInForce`, or you will keep alerting on how a
budget was sized before you replaced it.

## Is the hot tier filling faster than it empties?

`GET /api/server/memory` reports two rates, per database and for the process as a whole:

| Field | What it is |
|---|---|
| `hotArrivalBytesPerSecond` | resident hot bytes being **created** — flushes, promotions, segment loads |
| `hotDrainBytesPerSecond` | resident hot bytes being **released** by hot→cold demotion |
| `hotDrainLatencyP50Ms` / `hotDrainLatencyP90Ms` | how long a demotion takes |
| `hotDrainAttempted` / `hotDrainSucceeded` | demotions that spent real work, and the ones that freed a segment |
| `hotDrainStalled` | the drain **tried and failed** in the last sampling interval |

Both rates are exponentially weighted with a 30-second half-life, sampled on the server's existing
five-second evaluation tick. `totalHotBytesAdmitted` and `totalHotBytesDrained` are the monotonic
totals behind them.

**The number to watch is the difference.** A level — how many hot bytes are resident right now —
cannot distinguish a tier that is full and stable from one that is filling. Sustained
`hotArrivalBytesPerSecond` above `hotDrainBytesPerSecond` says the hot tier is being filled faster
than it empties, and says it while there is still headroom to act in.

⚠️ **`hotDrainBytesPerSecond == 0` is not a problem on its own.** A server with nothing to demote
drains nothing, which is the healthy resting state. The condition worth alerting on is
`hotDrainStalled`: the engine attempted demotions across the interval and none of them released a
segment. The two readings look similar and have opposite remedies, which is why they are separate
fields rather than one.

## What happens when the hot tier fills

Aouda answers hot-tier pressure in cost order, and **the first answer costs the writer nothing**.

| Rung | What it does | Cost to the writer | Default | Key |
|---|---|---|---|---|
| ~~**0 — drain harder**~~ | (**WorkloadCore S17, next train**) **Removed** — see below | — | — | ~~`Aouda:Memory:HotDrainAccelerationEnabled`~~ |
| **0.5 — seal cold** | The flush writes a cold segment instead of a hot one | A read of those rows comes from disk | **on** | `Aouda:Memory:HotAdmissionEnabled` |
| **1 — pace the writer** | (**WorkloadCore S16, next train**) The ingest stall curve: hot bytes past 80 % of the ceiling are one of its debts | Latency, bounded (≤ 10 s a write; never for a write of 64 KiB or less) | **on**, inert below 80 % | `Aouda:Memory:HotPacingWaterMark` |
| **2 — refuse** | Typed retryable `503` with `Retry-After` | The write fails and must be retried | **on** | — |
| **3 — break a pin** | Demotes a `HotOnly` table's segments anyway | Only if you asked for it | per table | `residency.hotOnlyBackstop` |

Each rung is tried before the one below it, and a rung that is off is skipped rather than substituted
for. (Rung 1 can no longer be turned off (**WorkloadCore S16, next train**); it is inert below its line.)

(**WorkloadCore S17, next train**) **Rung 0, drain acceleration, is deleted.** Above 60 % of a database's hot ceiling
(`T42`) it ran the hot/cold maintenance sweep up to four times as often and demoted to a lower per-table target. The hot
tier is now drained by two things only: the **memory broker**, which demotes hot segments when the database's ledger, the
process's, or the live heap is over its line, and the **demotion sweep** at its plain interval. What slows a writer while
the tier is filling is rung 1's `hot` signal, from `HotPacingWaterMark` (`T43`, 80 %). Its keys
`Aouda:Memory:HotDrainAccelerationEnabled` and `Aouda:Memory:HotDrainAccelerationWaterMark`, and the
`hotDrainAccelerationSweeps` / `hotDrainAccelerationDemotions` counters, are gone; a server still configured with either
key logs a warning for it at boot (see [Defaults Reference](defaults-reference.md#hot-tier-and-ingest-admission)). The
pair to watch is still `hotArrivalBytesPerSecond` against `hotDrainBytesPerSecond`, and `hotDrainStalled`.

## Where flushed rows go

A flush writes **one** representation — hot or cold — and decides which at flush time.

| Table policy | What a flush writes |
|---|---|
| `ColdPreferred` | **Always cold.** No hot segment is ever created, at any ceiling. |
| `Auto` (the default) | Hot while the tier has room; **cold when it does not**. |
| `HotOnly` | **Always hot.** A declared pin is never re-routed behind your back; `residency.hotOnlyBackstop` governs what happens when it cannot be honoured. |

⚠️ **`ColdPreferred` now does what its name says.** Until this release the flush built a hot segment
regardless of the policy and left a background sweep to undo it, so choosing `ColdPreferred` on a
small host bought a *deferred* cost rather than an avoided one. If you set it on archival tables
because the sizing guidance told you to, that advice is now true.

**A flush is never refused.** Under pressure it changes representation; it does not decline, because
the flush is what empties the write buffer and declining it would turn a memory problem into a
durability one.

**The trade, stated plainly:** rows that flush cold are on disk rather than in RAM, so the first read
of very recent data may be slower. The page cache is the tier for exactly that, and the condition
only arises when the alternative was approaching the hot ceiling.

Promotions and restart-time segment loads ask the same question. A promotion that would not fit is
simply not made — the rows are already readable from cold, so nothing is lost but the speed-up.

Set `Aouda:Memory:FlushAlwaysHotFirst=true` to restore the previous unconditional hot-first flush, or
`Aouda:Memory:HotAdmissionEnabled=false` to stop consulting the ceiling altogether.

### Bulk loads into graph and vector tables

`Aouda:BulkLoad:Temperature` now defaults to `ColdDirect`: an edge or vector bulk load writes cold
only. Previously both built a hot segment for every segment written, without consulting the hot
ceiling — one of the ways a large historical load could fill RAM. Set `HotAndCold` to restore the
previous behaviour; the bytes are still checked against the ceiling.

🔎 Ordinary **tabular** bulk loads were always cold-only and are unaffected.

## Debt slows the writer: the ingest stall curve (**WorkloadCore S16, next train**)

Four kinds of **debt** can build up behind a fast writer, and each used to be answered on its own or
not at all. Each database now has **one stall curve** fed by all four, each with a soft and a hard line:

| Debt | Soft line | Hard line | What lies past the hard line |
|---|---|---|---|
| **WAL fill** — the database's log on disk | 70 % of `MaxWalBytes` (a checkpoint is forced) | 95 % | writes refused, `WAL_CAPACITY_EXCEEDED` |
| **Maintenance lag** — the fullest materialized-query maintenance lane's backlog | half the backlog bound (32 MiB) | the bound (64 MiB) | a query marked behind, rebuilt from its source |
| **Flush debt** — the write buffer's unflushed bytes | `T11` (15 % of the database's budget) | 2 × `T11` | the memory budget's queue |
| **Hot bytes** — the hot tier | 80 % of the hot ceiling (`HotPacingWaterMark`) | the ceiling | flushes seal cold |

Below every soft line **nothing is paced**: the curve does not compute a rate there. Past one, client
writes — inserts, upserts, and each batch of a bulk load's `:append` — are admitted
through a per-database token bucket whose rate starts at the writer's own recent rate and falls toward
zero as the worst debt approaches its hard line (never below what would carry the debt from soft to
hard line over `Aouda:Memory:IngestStallHorizon`, 60 s). Ingest then settles at the rate the debt
drains, between the lines, instead of running into the refusal or the rebuild behind the hard line.

- **The wait happens before the write takes any lock**, so a paced write never holds up another writer
  of the same table. (The WAL's old 85 % throttle was a fixed delay *inside* the commit.)
- **One write waits at most 10 s** and is never refused by the curve.
- **An `UPDATE` or `DELETE` is not paced** (**WorkloadCore group 5 review, next train**) — the curve does not see a statement's size before
  it scans, so a very large update still runs into the WAL's refusal line rather than slowing (BL-904).
- **A write of 64 KiB or less is never paced** — the small writes and auth requests the held reserve
  keeps admitted.
- **Every batch of a bulk load's `:append` is paced whatever its size** (**WorkloadCore group 5 review, next train**): the 64 KiB exemption is
  for single small writes, and a load sent as small frames was never slowed.
- **Maintenance, flushes and rebuilds are never paced**: they are what clears the debt.

`GET /api/server/memory` shows each database's curve under `ingestStall`: `engaged`, `pressure` (0 below
every soft line, 1 at a hard line), `binding` (which debt), `rateBytesPerSecond`, `waits`, `waitedMs`,
and every signal with its `value`, `soft` and `hard`. A curve that stays engaged on `wal` means the log
is not being freed — look at the slots holding it; on `maintenance`, materialized queries are not keeping
up with ingest; on `hot`, the drain (`hotDrainStalled`, `hotDrainLatencyP90Ms`).

Removed with it: `Aouda:Memory:HotPacingEnabled` and the hot-only pacer it switched, its "Hot ingest rate
exceeded" refusal, and a bulk load's fixed 10 ms pause per 10,000 rows under heap pressure.

## The hot tier is bounded across databases, not only within one

Each database has its own hot ceiling, derived from its share of the memory budget. **On a small
host with many databases those ceilings used to sum to more than the process could hold.**

The per-database ceiling has a 32 MB floor, so a database with a small share still gets a workable
hot tier. That floor was not capped: at a 256 MB budget with thirteen databases the per-database
ceilings summed to **416 MB against a 208 MB heap limit** — 2.7× what the runtime will commit.

Aouda now also bounds the **sum**. `processHotCeilingBytes` on `GET /api/server/memory` is that
bound, and `processHotResidentBytes` is what is resident against it. Each database is limited by
whichever is smaller: its own ceiling, or its share of the aggregate
(`processHotCeilingShareBytes`).

⚠️ **If a write is refused while your database's own share still had room, these are the fields to
read.** The process was full; your database was simply not the one holding most of it.

**A refusal names which ceiling bound it, because the two have opposite fixes.** Bound by the
database's **own** ceiling, that database wants a larger share of the budget or a faster drain. Bound
by the **process aggregate**, it is already inside its own share and is being held down by what the
other databases hold — giving it a bigger share alone would change nothing, and the fix is to reclaim
elsewhere.

🔎 **On a healthy server this changes nothing**, and that is by construction rather than by
tuning: the aggregate is the same fraction the per-database ceilings are derived from, so the two
agree exactly wherever no floor is binding. It is the small-host, many-database case — where the
floor *is* binding — that it exists for. Counter-intuitively that is the smallest deployments, not
the largest: the floor binds from three databases at 256 MB and from ninety-eight at 8 GB.

Set `Aouda:Memory:ProcessHotCeilingEnabled=false` to bound each database only by its own ceiling.

## Pinning a table in memory has a price, and you pay it

A `HotOnly` table is pinned: the engine will not demote it to make room. **That pin is now a
reservation rather than a preference**, and three things follow.

**It shrinks the elastic tier.** The hot bytes your pin holds come off the ceiling everything else
is admitted against. `pinnedHotBytes` on `GET /api/server/memory` is how much, per database.

**It is refused on its own budget.** A pinned table's writes are refused when *its own* reservation
is exhausted — never because another database filled the process. Declare the size with
`residency.targetMemoryBytes`:

```json
{
  "storageTemperature": "HotOnly",
  "residency": { "targetMemoryBytes": 268435456, "hotOnlyBackstop": "RefuseWrites" }
}
```

⚠️ **Until this release that field was rejected on a `HotOnly` table.** It is the pin's reservation
size; on an ordinary `Auto` table the same field remains a demotion target.

**Over-subscription is caught when you declare it.** If your declared pins together exceed what the
process can hold hot, the policy write fails immediately and names both figures — rather than
succeeding and surfacing hours later as a refusal on an unrelated table.

A `HotOnly` table with no `targetMemoryBytes` still works: it declares intent without a number, does
not participate in the over-subscription check, and is bounded by the hot tier it lives in.
`hotOnlyBackstop: "DemoteAnyway"` is unchanged — such a table yields its segments under pressure
instead of refusing writes.

## Auth databases are resident, and you size for them (**BL-614, 0.1.35**)

An **auth database is a system tier**: every table it holds except `_audit_log` is pinned `HotOnly`,
so an authenticated request never waits on disk for a credential, a role, a permission or a signing
key. This applies to the server auth database (`_serverauth`) and to every application auth database.

**Budget for it.** The resident cost is bounded by identity volume, not by data volume — users,
roles, permissions, grants, API keys, plus the live sessions and unexpired tokens. It is small on any
realistic deployment and it is **not elastic**: those bytes are charged to `pinnedHotBytes` and come
off the ceiling the rest of the hot tier is admitted against, exactly as the section above describes
for any declared pin. On a small host, an auth database with a large user table is one of the few
things that can meaningfully narrow the elastic tier.

`_audit_log` is deliberately **not** pinned. It is never read to authorize a request, it is the
fastest-growing table in the database, and it pages to disk like ordinary data.

⚠️ **The embedded engine's `EnableEmergencyDemotion` option does not reach an auth database.** (A server
has no such key: `Aouda:Memory:EnableEmergencyDemotion` is not read, and is warned about at boot as an
unknown key (**WorkloadCore S17, next train**); use a table's `hotOnlyBackstop` instead.) That switch is a
process-wide answer to heap pressure; applying it to credential tables trades an out-of-memory risk
for a cluster-wide loss of authentication, which is not a trade an operator is making knowingly when
they set it. There is no setting that turns the auth rule off. A per-table
`hotOnlyBackstop: DemoteAnyway` still overrides the pin, because that names one table explicitly.

⚠️ **Auth databases created before this change are not migrated.** The pins are applied when the
database is created, so an older auth database keeps demotable credential tables. Check with
`GET /api/databases/{db}/tables/{name}/policy`, and fix one in place with:

```http
PUT /api/databases/{db}/tables/_users/policy
{ "storageTemperature": "HotOnly" }
```

The hot/cold maintenance worker promotes that table's already-cold segments back on its next sweep.
⚠️ It **skips promotions while the server is under memory back-pressure**, which is usually the state
a server in this condition is in — so expect the promotion to lag the policy change, and re-check
rather than assuming the write took effect immediately.

## Materialized query results live in this tier too {#mq-result-residency}

A materialized query's result is an **ordinary table** with the query's name. It is in the same hot
tier, obeys the same `storageTemperature`, is demoted and promoted by the same sweep, and is charged
against the same per-database and process-wide ceilings as the tables you declared yourself.

**With no declaration it defaults to `Auto`** — for every query type. Residency is policy, not
something inferred from the query's shape.

⚠️ **`Auto` is the right answer when you do not know; it is rarely the best one when you do.** An
`aggregate` result holds **one row per group** and a `latestPerKey` result **one row per key**, so
both grow with the source's cardinality — a measured eight-query fan-out held **2 199 815 groups**,
and per-minute candles over a few thousand instruments is an ordinary shape, not a pathological one.
A result table you never thought about is a common reason a hot tier is fuller than its owner
expects.

⚠️ **A pin here costs what any pin costs.** If you declare `HotOnly` on a result table, its bytes
come off the ceiling everything else is admitted against, the table is skipped for demotion, and its
cold segments are re-promoted — so the drain has nothing it is allowed to demote there. That is the
bargain a declared pin makes, and it is worth making deliberately on a small result and not by
accident on a large one.

### Declaring a temperature

`storage.storageTemperature` on the query's schema entry:

```json
"candles_bid_1m": {
  "type": "aggregate",
  "sourceTable": "quotes",
  "groupBy": [ { "column": "ticker" },
               { "column": "time", "function": "TruncateToMinute", "outputName": "time" } ],
  "aggregates": [ /* … */ ],
  "storage": { "storageTemperature": "ColdPreferred" }
}
```

| Your result is… | Declare | Why |
|---|---|---|
| Large, historical, append-shaped — candles, rollups, anything keyed by a time bucket | **`ColdPreferred`** | It never creates a hot segment at all, at any ceiling. The bytes stay on disk and the page cache serves the recent end. |
| Genuinely small and read on every request — a few thousand keys at most | **`HotOnly` + `residency.targetMemoryBytes`** | A stated reservation, refused on its own budget, and caught at declaration time if your pins over-subscribe. |
| Somewhere in between, or you want *recent hot, historical cold* | **`Auto` + `residency.memoryRowCap`** | The sweep demotes least-recently-accessed segments first, so a row cap self-scales without your knowing the arrival rate. |

🔎 **What makes the third row work is the ordering underneath.** A time-bucketed `aggregate` result
table is clustered by its leading derived time bucket, and the sweep demotes the
least-recently-accessed segment first — so on time-ordered data that is a good proxy for *keep recent
buckets resident, send historical ones to cold*. Measured: 400 minute-buckets under a 50-row cap stay
queryable, complete and gap-free while the resident footprint stays bounded.

🔎 **`memoryRowCap` is the answer to "keep the last 24 hours hot", and it is a better one than a time
window.** A *duration* cannot be honoured without knowing the arrival rate — at 1.25 MB/s, "24 h" is
108 GB, which would have to be refused when you declared it. A *count* bound needs no such input and
self-scales across a 1 ms feed and a 1-minute candle alike.

⚠️ **`residency` is not declarable next to the query** — `storage` carries `storageTemperature` only.
Set `memoryRowCap` / `targetMemoryBytes` on the result table via
`PUT /api/databases/{db}/tables/{name}/policy`, and re-apply after a destructive schema replace.

Full treatment, including the amplification counters that say what a query costs:
[Materialized queries](materialized.md#where-a-materialized-querys-result-lives).

## Memory is granted before work starts, and small writes have a reserve (**WorkloadCore S06, next train**)

Work asks for memory before it starts — at least what it needs, at most what it can use — and waits in its class's queue if it
does not fit, instead of being refused part-way. A client's insert or upsert waits at most one 10-second sampling tick, and
then is refused with a `Retry-After` that the queue estimates. `grants` on `GET /api/server/memory` shows what is waiting.
(**WorkloadCore S17, next train**) **A memory refusal's `Retry-After` is never a constant 1 s**, wherever it is raised —
a read growing past its budget, a write decided under a lock, a heap exhausted mid-request included: it is the queue's
estimate for the refused bytes at its measured service rate, or **10 s** (the memory broker's next look, `T6`) before any
rate has been measured or when the refusal carries no estimate.

The top **`max(32 MB, 3 %)` of the budget** (at most an eighth of it) is **held** for small writes (≤ 64 KiB) and sign-ins.
Everything else is admitted against the budget less that reserve, so a budget of 512 MB gives ordinary work 480 MB. Size for
it: on a 256 MB budget the reserve is 32 MB.

**A database is no longer held to its share.** Each database's ceiling is the server's budget unless you capped it (a
database budget, or `MaxMemoryShare`); its weighted share (`MemoryWeight`) decides who gives memory back first when the server
needs it — the database furthest over its share. Elastic share lending, and `Aouda:Memory:ElasticShares` /
`ElasticShareActivityWeighted`, are removed.

(**WorkloadCore S07, next train**) **The big consumers ask too.** A bulk load asks for its memory before it takes its tables'
locks and waits there (up to its lock-acquisition timeout, 30 s by default), so a load waiting for memory does not stall the
inserts into its tables. Once work is running, its next step — a load's buffer doubling, a read growing past 1 MiB, a
materialized-query build's accumulators, a deferred pass's wave — is taken only if nothing of the same or a higher class is
waiting: a load spills sooner, a build spills, a pass takes smaller waves, a read is refused with the queue's `Retry-After`.
A bulk load's segment writes take their working memory (about twice the bucket being written) from the load's memory and
run one at a time when it has no more, and a flush charges the page builders it encodes with — both used to be invisible to
the budget. Recovery after a crash waits up to 10 s for its replay window rather than quarantining the database at once.

(**WorkloadCore S09, next train**) **Materialized-query maintenance asks too** (BL-859). Each maintenance unit — a queued apply, an ingest-fed
drain (gone in **WorkloadCore S10**: a load's maintenance is its table's pass), a deferred pass — asks for its grant before it takes its queries' locks, and waits in the queue (a queued apply in the
`Streaming` class, ahead of waiting loads whose memory its backlog holds; a load's drain or pass in `Background`);
it is never refused part-way through an apply. A load's maintenance that cannot get memory within 30 s is refused before it
starts, and its queries are left behind and rebuilt. A query's update backlog (up to 64 MiB an update lane) is charged on
the budget as memory already held.

**The budget is the deployment's.** It is never lowered in-process any more: a host running short of memory, RSS above the
budget or a full heap do not shrink it (the 512 MB host-availability floor and "tightening" are gone). Give the server a
container memory limit and it derives its budget from that grant.

## What happens when the GC heap gets tight

Aouda watches the managed heap separately from its own memory ledger, because they are different
quantities: the ledger says what has been promised, the heap says what will actually throw. A process
can sit at 39 % of its ledger and at its heap limit simultaneously.

(**IngestAtSpeed S08, 0.1.40**) The heap figure is the heap **in use after the most recent
collection**, not the heap the GC has committed. A fast load produces garbage in gigabytes, and the GC
keeps most of that memory committed after sweeping it. Read as pressure, it throttled the pipeline for
being fast: on an 8 GB box with ~800 MB live, admission refused a 64 KB rebuild for minutes. The
`lastGen2LiveBytes` field on `GET /api/server/metrics` is the closest external reading.

(**WorkloadCore S06, next train**) **Heap pressure no longer refuses writes.** When the live heap passes 80 % of the GC hard
limit, the memory broker is woken and frees memory — caches first, then hot segments, then, if nothing else is left, it takes
back memory granted to background work that can checkpoint and resume. Writes are not refused for the heap: the 503 with a
30-second `Retry-After`, the 60-second grace window it had under `HotPacingEnabled`, and `heapPressureGraceExpired` are gone.
Sustained heap pressure (90 % for three samples) still slows a bulk load's row loop and holds back a post-load rebuild, as
before. The exhaustion watchdog's last line (98 %) is unchanged.

### The state between "within budget" and "terminate"

A heap can be tight for hours without ever satisfying the termination rule. The watchdog arms
termination on six **consecutive** samples above 98 % of the heap limit — but a process fighting its
collector oscillates (one observed incident ran 91.5 → 98.8 → 91.6 %), so the consecutive counter
reset every time and the process sat alive-but-wedged: refusing writes, collecting continuously,
neither recovering nor dying.

Three fields on `GET /api/server/memory` report that state, and two of them also appear in the
`memory` health component's details:

| Field | What it is |
|---|---|
| `heapSustainedDegradation` | `true` when a **majority of a sliding window** of samples was above 90 % of the heap limit |
| `heapDegradedSinceUtc` | when that began; `null` while healthy |
| `heapDegradedForSeconds` | how long it has been true — the number to alert on |

⚠️ **This reports; it never acts.** Termination's own rule is untouched, and nothing here refuses,
delays or reroutes a write.

⚠️ **A window majority rather than a consecutive run, deliberately.** Oscillation is a *symptom* of
the condition, not evidence against it — a consecutive rule gets harder to trip the harder the
collector is fighting, which is precisely backwards.

🔎 **Why a field and not just a log line.** Every other memory figure on these surfaces is
instantaneous, and an instantaneous reading cannot tell a spike the next collection resolves from a
process that has been unable to make room for an hour. Alert on `heapDegradedForSeconds` crossing a
threshold you choose; a log line is gone from a polling system the moment it scrolls past.

## When ingest outruns flush

Writes that do not fit **wait** for memory — before they take any lock, for up to one 10-second sampling tick — and then return **HTTP 503** with `MEMORY_BUDGET_EXCEEDED` and a `Retry-After` estimated from the queue they waited in (**WorkloadCore S06, next train**), or `WAL_CAPACITY_EXCEEDED` and `Retry-After` from the WAL. Retry; the process stays up. Small writes (≤ 64 KiB) and sign-ins are admitted from a held reserve whatever else holds the memory. After flush and checkpoint, WAL segments below every consumer slot are deleted. The local point-in-time-recovery window is that same bound — **write volume** since the last backup (`MaxSlotWalKeepBytes`), not a number of days; enable WAL archiving to recover further back. Studio Inspect shows bytes on disk versus reclaimable, and `earliestRecoverablePitrPosition`. A database that cannot open (including leftover `insert.wal`) is **quarantined** — inspect or run `aouda wal convert`, then drop if you do not need it. The rest of the server keeps serving.
(**WorkloadCore S06, next train**) A refusal no longer names a **class** that hit its own entitlement: the per-class ceilings and `Aouda:Memory:PerClassAdmissionEnabled` are removed. A refusal now says how long the request waited, what was queued ahead of it, and the budget less the held reserve it was measured against. `reservedByClass` on `GET /api/server/memory` still says who was holding the budget, and `grants` what was waiting.

Two refusals are new in this release and are worth knowing before you meet them. A query whose result exceeds `Aouda:Query:MaxResultRows` (default 1 000 000) is refused rather than materialised; and a `POST …/named-queries/batch` whose results genuinely exceed its read budget (the transient pool `T15`, less what other reads hold — the class ceiling it was measured against is gone, **WorkloadCore S06, next train**) is refused, where it previously succeeded while holding far more memory than it had reserved. Both are the same typed retryable `503`.
(**ColumnarRead, next train**) A large scan's decode buffers and a GROUP BY's, top-K's or `DISTINCT`'s growing state are now
charged to the query's read budget as they grow, so a GROUP BY with more groups than its budget holds fails with the typed
retryable error while it grows, rather than after.

## Which rungs are actually running

Every rung above has a config key, and the server prints the ladder **as it is actually in force** in
one startup line:

```
Memory ladder: admission=on, stall curve (T43=80 %, T44=00:01:00, T45=00:00:30),
  processHotCeiling=on, flushAlwaysHotFirst=off
```

(**WorkloadCore S17, next train**: `rung0=…` and `T42` are gone with rung 0, and the stall curve is always on, so it has
no on/off.)

⚠️ **Read the effective values here, not the ones you set.** Every non-boolean on this line
**self-clamps** — `T43` to `[0.10, 1.0]` (**WorkloadCore S17, next train**; it was `[T42, 1.0]`), both durations against
their own floors and ceilings — so a
value you configured can be silently replaced by a different one. That is exactly why the line prints
the effective number rather than the configured one.

⚠️ **On servers before this line existed, these settings were not merely off — they were
unreachable.** The engine held them, but nothing bound them from configuration, so a deployment ran
the whole ladder at its compiled-in defaults permanently. If you set one of these keys and the
behaviour did not change, check for this line before assuming the key is wrong.

Every key, with its default and what it restores, is in the
[Defaults Reference](defaults-reference.md#hot-tier-and-ingest-admission).

