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
