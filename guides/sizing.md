---
title: "Sizing memory and WAL"
nav_order: 7
parent: "Guides"
---

# Sizing the server budget

Aouda treats `MaxTotalRamBytes` as a **process RSS ceiling**, not an advisory subtotal. Leave it unset and the server derives it from detected host (or cgroup) memory: **70%** when detection found a real cgroup isolation boundary, **40%** when it fell back to physical RAM (a fallback result proves nothing about how much of the host Aouda actually owns). Set it explicitly when you need a pinned number. Resize live from Studio (Settings → Server), `PATCH /admin/config`, or `aouda budget`. See the [Defaults Reference](defaults-reference.md) for every downstream number this derives (governed budget, per-database shares, the L2 cache ceiling, the bulk-load ingest buffer budget) worked at several host sizes.

## Small hosts (under 1 GB)

Give the process only what remains after the OS. Flush and hot-tier thresholds scale with the budget, so many tables do not each assume a large in-memory buffer. Prefer `ColdPreferred` for archival tables. Ingest will throttle sooner than on a large box — that is the process staying up, not a crash.

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

## What headroom buys

Aouda measures its own headroom — governed budget against sustained working-set high water — and moves between three states: **`Constrained`**, **`Balanced`** and **`Abundant`**. A host with real headroom does not merely get a larger Aouda; several buffering thresholds move, so it gets a **faster** one. Measured on an 8 GB budget loading 1.2 M rows: the per-table flush trigger rose from 64 MB to 307 MB, the load produced 5 segments instead of 6, and wall clock fell from 5 496 ms to 4 630 ms — about 16%.

The state is reported as `resourceMode` on `GET /api/server/memory`, with the `headroomRatio` that produced it and a `resourceModeTransitions` count. Transitions require sustained agreement in both directions, so a burst does not move a threshold; if `resourceModeTransitions` is climbing, that is the signal to investigate rather than a normal reading.

### What `headroomRatio` is a ratio of (**BL-622, next train**)

```
headroom  =  the server's governed budget
             ───────────────────────────────────────────────
             a decayed maximum of the PROCESS's resident set
```

Since **BL-622** both operands are on the endpoint, as a `headroom` block beside `headroomRatio` —
`governedBytes`, `workingSetHighWaterBytes`, `workingSetSource` and `scope`, plus the four
thresholds the ratio is tested against.

⚠️ **Neither operand is a per-database quantity, and neither is the reservation ledger.** This is
the most common misdiagnosis of this number. A real example: a database granted a 2.3–2.4 GB
elastic ceiling, with a **~120 MB** reservation peak, zero heap reclaims and zero admission sheds —
every figure saying there was room — reported `headroom 1.45x` and ran a whole 15 M-row load in
`Constrained`, with its page cache off. All of those numbers were correct. The process's resident
set was ~1.9 GB against a 2.76 GB governed budget, and the ~1.78 GB between the ledger and RSS is
resident data that Aouda **reports but never reserves**: hot segments, HRA buffers, PK index caches
and materialized-query build state. It is kept out of the ledger on purpose, so that resident data
cannot make the governor refuse transient work that genuinely fits.

⚠️ **The mode is a property of the process, not of a database.** Two databases on one host are in
the same mode by definition. The startup log names a database only because the mode is applied to
each open database in turn.

**What to read together**, when the mode looks wrong for the room you think you have:
`headroom.workingSetHighWaterBytes` (the denominator), `rssBytes` (the instantaneous version of it),
`reservedBytes` (the ledger) and `untrackedHeadroomBytes` (the gap between them, which is usually
most of the answer).

### Where the budget itself came from (**BL-611, next train**)

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

A database picks the new thresholds up **live**, on the transition — it does not need a restart, and it does not need to have been opened while the host was roomy.

⚠️ **RSS on such a host is higher than it was at the same data volume.** That is the feature, it is still inside the ceiling by construction, and anyone alerting on absolute RSS rather than on RSS-versus-configured will see it. Alert on the ratio.

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
| **0 — drain harder** | Sweeps more often, demotes to a lower target | **None.** Disk I/O only | **on**, inert below 60 % | `Aouda:Memory:HotDrainAccelerationEnabled` |
| **0.5 — seal cold** | The flush writes a cold segment instead of a hot one | A read of those rows comes from disk | **on** | `Aouda:Memory:HotAdmissionEnabled` |
| **1 — pace the writer** | Delays the writer to a measured admissible rate | Latency, bounded | **off**, inert below 80 % | `Aouda:Memory:HotPacingEnabled` |
| **2 — refuse** | Typed retryable `503` with `Retry-After` | The write fails and must be retried | **on** | — |
| **3 — break a pin** | Demotes a `HotOnly` table's segments anyway | Only if you asked for it | per table | `residency.hotOnlyBackstop` |

Each rung is tried before the one below it, and a rung that is off is skipped rather than substituted
for — turning rung 1 off does not make rung 2 fire sooner, it means a tier that rung 0 cannot drain
fast enough reaches the ceiling and refuses instead of slowing down first.

Above **60 %** of a database's hot ceiling the engine simply drains harder: the hot/cold maintenance
sweep runs more often and demotes to a lower per-table target, and the reclaim ladder aims to bring
the tier back to that mark rather than merely under the ceiling. It spends disk I/O — which is rarely
the scarce resource — to buy back memory, which is. No write is delayed, refused or rerouted by it,
at any occupancy.

The response is **proportional**: exactly nothing happens at 60 %, and it rises smoothly to a
four-times-faster sweep with a halved target as the tier approaches its ceiling. It is bounded there,
so a busy server does not end up spending a core on maintenance.

`hotDrainAccelerationSweeps` and `hotDrainAccelerationDemotions` on the performance counters say how
often it engaged and how often it changed the outcome. The pair to watch on
`GET /api/server/memory` is still `hotArrivalBytesPerSecond` against `hotDrainBytesPerSecond`: if the
drain now keeps up where it previously did not, this is why.

Set `Aouda:Memory:HotDrainAccelerationWaterMark` to move the mark, or
`Aouda:Memory:HotDrainAccelerationEnabled=false` to restore the previous fixed-cadence sweep exactly.

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

## Pacing ingest against the drain (opt-in)

If accelerating the drain and sealing cold are not enough — a pinned table, a promotion-heavy
workload — Aouda can **pace the writer** above 80 % of a database's hot ceiling. It is **off by
default**: set `Aouda:Memory:HotPacingEnabled=true`.

The rate a writer is paced to is measured, not configured:

```
admissible arrival = drain rate + (hot ceiling − resident hot) / control horizon
```

*You may create hot bytes as fast as they are leaving, plus fast enough to consume the remaining
headroom over the horizon* (`Aouda:Memory:HotControlHorizon`, default 60 s). At the ceiling this
reduces to exactly the drain rate, so ingest settles on what the tier can actually absorb.

⚠️ **Below the 80 % mark nothing is paced — and that is structural, not a matter of the numbers
being large enough.** The controller does not compute a rate at all below the water mark, so a
healthy server cannot be slowed by it.

**Each database has its own bucket.** A busy database's backlog never delays a quiet one's writes.

If a bounded wait would not be enough, the write is refused with a retryable `503` that names the
arrival rate, the drain rate, the demotion latency, the resident hot bytes and the ceiling — and a
`Retry-After` derived from how long the drain actually needs. **If you see these, the number to
investigate is the drain**, not the ceiling: check `hotDrainStalled` and
`hotDrainLatencyP90Ms` on `GET /api/server/memory`.

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

## Auth databases are resident, and you size for them (**BL-614, next train**)

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

⚠️ **`Aouda:Memory:EnableEmergencyDemotion=true` does not reach an auth database.** That switch is a
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
cold segments are re-promoted — so rung 0 has nothing it is allowed to drain there. That is the
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

## What happens when the GC heap gets tight

Aouda watches the managed heap separately from its own memory ledger, because they are different
quantities: the ledger says what has been promised, the heap says what will actually throw. A process
can sit at 39 % of its ledger and at its heap limit simultaneously.

**With ingest pacing off (the default), sustained heap pressure refuses writes**, as it has since the
memory-ceiling work: a retryable `503` naming the heap figure and its limit, with a 30-second
`Retry-After`.

**With `Aouda:Memory:HotPacingEnabled=true`, it paces first.** The first sustained observation starts
a grace window — up to 60 seconds — in which the engine drains the hot tier harder and slows the
writer instead of refusing. If the heap recovers inside the window, no write is ever refused. If it
does not, the refusal happens exactly as before.

⚠️ **Except within 10 % of the heap hard limit, where no grace is granted at all.** Above **90 %** of
the hard limit the engine refuses straight away rather than spending the remaining room on a wait —
there is not enough headroom left for pacing to plausibly recover it, and a wait there buys a crash
instead of a `503`.

⚠️ **The grace is deliberately unavailable with pacing off.** Refusing is what stops a heap-exhausted
process dying, and it is only safe to defer while something else is bounding how fast memory arrives.

`heapPressureGraceExpired` on the performance counters is the number to watch: it counts the times
pacing was given its window and the heap stayed tight anyway.

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

Writes first delay, then return **HTTP 503** with `MEMORY_BUDGET_EXCEEDED` or `WAL_CAPACITY_EXCEEDED` and `Retry-After`. Retry; the process stays up. After flush and checkpoint, WAL segments below every consumer slot are deleted. The local point-in-time-recovery window is that same bound — **write volume** since the last backup (`MaxSlotWalKeepBytes`), not a number of days; enable WAL archiving to recover further back. Studio Inspect shows bytes on disk versus reclaimable, and `earliestRecoverablePitrPosition`. A database that cannot open (including leftover `insert.wal`) is **quarantined** — inspect or run `aouda wal convert`, then drop if you do not need it. The rest of the server keeps serving.
Refusals now name **which class of work** was refused and why. A `503` may say a class hit its own entitlement while the process as a whole still had room — that is a different problem from the process being full, and it names a different fix: run less of that kind of work concurrently, raise that class's entitlement, or set `Aouda:Memory:PerClassAdmissionEnabled=false` to admit against the process ceiling alone. `reservedByClass` on `GET /api/server/memory` says who was holding the budget when it happened.

Two refusals are new in this release and are worth knowing before you meet them. A query whose result exceeds `Aouda:Query:MaxResultRows` (default 1 000 000) is refused rather than materialised; and a `POST …/named-queries/batch` whose results genuinely exceed the class ceiling is refused, where it previously succeeded while holding far more memory than it had reserved. Both are the same typed retryable `503`.

## Which rungs are actually running

Every rung above has a config key, and the server prints the ladder **as it is actually in force** in
one startup line:

```
Memory ladder: admission=on, rung0=on (T42=60 %), rung1=off (T43=80 %, T44=00:01:00,
  T45=00:00:30), processHotCeiling=on, flushAlwaysHotFirst=off
```

⚠️ **Read the effective values here, not the ones you set.** Every non-boolean on this line
**self-clamps** — `T43` against `T42`, both durations against their own floors and ceilings — so a
value you configured can be silently replaced by a different one. That is exactly why the line prints
the effective number rather than the configured one.

⚠️ **On servers before this line existed, these settings were not merely off — they were
unreachable.** The engine held them, but nothing bound them from configuration, so a deployment ran
the whole ladder at its compiled-in defaults permanently. If you set one of these keys and the
behaviour did not change, check for this line before assuming the key is wrong.

Every key, with its default and what it restores, is in the
[Defaults Reference](defaults-reference.md#hot-tier-and-ingest-admission).

