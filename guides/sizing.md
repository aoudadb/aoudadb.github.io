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

A database picks the new thresholds up **live**, on the transition — it does not need a restart, and it does not need to have been opened while the host was roomy.

⚠️ **RSS on such a host is higher than it was at the same data volume.** That is the feature, it is still inside the ceiling by construction, and anyone alerting on absolute RSS rather than on RSS-versus-configured will see it. Alert on the ratio.

## When ingest outruns flush

Writes first delay, then return **HTTP 503** with `MEMORY_BUDGET_EXCEEDED` or `WAL_CAPACITY_EXCEEDED` and `Retry-After`. Retry; the process stays up. After flush and checkpoint, WAL segments below every consumer slot are deleted. The local point-in-time-recovery window is that same bound — **write volume** since the last backup (`MaxSlotWalKeepBytes`), not a number of days; enable WAL archiving to recover further back. Studio Inspect shows bytes on disk versus reclaimable, and `earliestRecoverablePitrPosition`. A database that cannot open (including leftover `insert.wal`) is **quarantined** — inspect or run `aouda wal convert`, then drop if you do not need it. The rest of the server keeps serving.
Refusals now name **which class of work** was refused and why. A `503` may say a class hit its own entitlement while the process as a whole still had room — that is a different problem from the process being full, and it names a different fix: run less of that kind of work concurrently, raise that class's entitlement, or set `Aouda:Memory:PerClassAdmissionEnabled=false` to admit against the process ceiling alone. `reservedByClass` on `GET /api/server/memory` says who was holding the budget when it happened.

Two refusals are new in this release and are worth knowing before you meet them. A query whose result exceeds `Aouda:Query:MaxResultRows` (default 1 000 000) is refused rather than materialised; and a `POST …/named-queries/batch` whose results genuinely exceed the class ceiling is refused, where it previously succeeded while holding far more memory than it had reserved. Both are the same typed retryable `503`.

## Where flushed rows go, and the two rates that say whether the hot tier is coping

Aouda keeps recently written rows in a **hot** tier in RAM and moves them to **cold** storage on disk as
they age. Two things changed here, and both are visible on `GET /api/server/memory`.

**A flush now writes exactly one representation.** It used to build the in-RAM copy first and produce
the on-disk one only later, on demotion — for every table, whatever its policy. Now the decision is
made when the rows are flushed: hot when the tier can afford them, cold when it cannot, and **cold
unconditionally for a `ColdPreferred` table**. Three consequences worth knowing before you meet them:

- **`ColdPreferred` finally does what it says.** Such a table creates no hot segment at all. If you
  followed the advice above to prefer it for archival tables, you now get an avoided cost rather than
  a deferred one.
- **A bulk load into an edge or vector table writes cold by default.** Set
  `Aouda:BulkLoad:Temperature` to `HotAndCold` to restore the previous behaviour per job or per
  server.
- **Rows flushed cold under pressure read from disk, not RAM.** Read-after-write on those rows is
  slower. This only happens when the alternative was approaching the hot ceiling, and the page cache
  is the tier that exists for it — but it is a real change and it is why it is named here.

Set `Aouda:Memory:FlushAlwaysHotFirst=true` to restore the previous flush for every table.

**The two numbers to watch** are `hotArrivalBytesPerSecond` and `hotDrainBytesPerSecond`, reported per
database and for the process. Arrival is resident hot bytes created per second; drain is bytes
released per second by hot→cold demotion. A tier that is coping has arrival at or below drain over
time. A tier that is filling has arrival above drain, and the gap — not either number alone — is the
thing to alert on.

⚠️ **`hotDrainStalled` is not the same as a drain of zero.** Zero drain is normal on an idle server
and needs nothing. `hotDrainStalled` means the drain **tried and failed** in the last sampling
interval, which is a different condition with the opposite remedy: look at `hotDrainLatencyP90Ms` and
at the `hotDrainAttempted` / `hotDrainSucceeded` split, and check the logs for demotion failures.

Also reported: `totalHotBytesAdmitted` / `totalHotBytesDrained` (monotonic since process start),
`pinnedHotBytes` (what this database's `HotOnly` tables hold — see below), and, for the process,
`processHotCeilingBytes` with `processHotResidentBytes`.

## The hot tier is bounded across databases, not only within one

Each database has its own hot ceiling, and there is now a **process-wide** one as well. The
per-database ceiling carries a 32 MB floor, so on a small host with many databases those floors could
sum to more than the process would ever commit — at a 256 MB budget with thirteen databases they sum
to 416 MB against a 208 MB heap limit. The aggregate ceiling closes that.

It is **inert wherever the per-database ceilings already sum correctly**, which is every host with a
few databases or a budget above about 2 GB. It binds only where the floor has broken the sum, which
is exactly the small-host, many-database shape it exists to protect. Turn it off with
`Aouda:Memory:ProcessHotCeilingEnabled=false`.

⚠️ **A refusal names which ceiling bound it**, because the two have opposite fixes. Bound by the
database's own ceiling, that database wants more of the budget or a faster drain. Bound by the
process aggregate, it is inside its own share and is being held down by what the other databases
hold — giving it a bigger share alone would change nothing.

## A residency pin is a reservation with a price

A `HotOnly` table's segments are pinned in RAM. That pin is now **charged**: its bytes come off the
ceiling the rest of the hot tier is admitted against, so declaring one visibly shrinks the elastic
tier rather than competing with it. `pinnedHotBytes` on `GET /api/server/memory` is how much.

Two changes follow:

- **A pinned table under `hotOnlyBackstop: RefuseWrites` is refused on its own exhausted
  reservation** — `residency.targetMemoryBytes` when you declared one, otherwise the database's hot
  ceiling. It is **no longer refused because an unrelated database filled the process**, which is
  what used to happen and which told the operator nothing useful.
- **Pins that together exceed the process hot ceiling are refused when they are declared**, naming
  both numbers, rather than discovered at 98 % of heap.

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

## Backpressure on ingest, and what it costs

Under sustained pressure the engine answers in cost order, cheapest first: it drains harder (more
I/O, **no writer is delayed**), then paces the writer against a measured admissible rate, then
refuses with a typed retryable `503`, and only then touches a declared pin.

Draining harder is on by default and is inert below 60 % hot occupancy —
`Aouda:Memory:HotDrainAccelerationEnabled=false` turns it off.

⚠️ **Writer pacing ships disabled.** It is the first response that can make a healthy workload slower
if a constant is wrong, and two of its constants are carried from another system rather than derived
from Aouda's own arithmetic. Enable it with `Aouda:Memory:HotPacingEnabled=true`. Below the pacing
water mark it cannot delay anything by construction, so turning it on does not put a cost on a server
whose drain is keeping up. Enabling it also allows sustained heap pressure a bounded window to pace
and drain before it refuses — except within 10 % of the heap hard limit, where the engine refuses
straight away rather than spending the remaining room on a wait.
