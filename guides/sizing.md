---
title: "Sizing memory and WAL"
nav_order: 7
parent: "Guides"
---

# Sizing the server budget

Aouda treats `MaxTotalRamBytes` as a **process RSS ceiling**, not an advisory subtotal. Leave it unset and the server uses about **70% of detected host (or cgroup) memory**. Set it explicitly when you need a pinned number. Resize live from Studio (Settings → Server), `PATCH /admin/config`, or `aouda budget`.

## Small hosts (under 1 GB)

Give the process only what remains after the OS. Flush and hot-tier thresholds scale with the budget, so many tables do not each assume a large in-memory buffer. Prefer `ColdPreferred` for archival tables. Ingest will throttle sooner than on a large box — that is the process staying up, not a crash.

## Typical (~2 GB)

A 2 GiB cap is a reasonable **explicit** choice, not a hidden default. Hot data stays in RAM; colder segments demote. Watch RSS versus the governed budget in Studio Settings and Monitoring.

## Large hosts

Set an explicit ceiling so Aouda does not grow into all remaining RAM. Per-database `maxMemoryBytes` on HTTP create (config: `MaxMemoryShareBytes`) is a **cap on that database's share** of the one server budget, not a second independent heap.

## When ingest outruns flush

Writes first delay, then return **HTTP 503** with `MEMORY_BUDGET_EXCEEDED` or `WAL_CAPACITY_EXCEEDED` and `Retry-After`. Retry; the process stays up. After flush and checkpoint, WAL segments below every consumer slot are deleted. The local point-in-time-recovery window is that same bound — **write volume** since the last backup (`MaxSlotWalKeepBytes`), not a number of days; enable WAL archiving to recover further back. Studio Inspect shows bytes on disk versus reclaimable, and `earliestRecoverablePitrPosition`. A database that cannot open (including leftover `insert.wal`) is **quarantined** — inspect or run `aouda wal convert`, then drop if you do not need it. The rest of the server keeps serving.
