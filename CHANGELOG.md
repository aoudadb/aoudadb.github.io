---
title: "Changelog"
nav_order: 9
---

# Aouda Changelog

This changelog follows the **P-series roadmap (P0–P4)** and records major architectural and feature-level progress.  
It is intended for internal developers to track system evolution and understand where each subsystem was introduced.

Each phase corresponds to a major functional checkpoint.  
Minor patch releases and experimental branches are recorded inline under their respective phases.

---

## ✅ P0 — Core Bootstrap (Completed)

**Date:** 2025-Q1  
**Scope:** Engine foundations, encoding, and columnar persistence.

### Highlights
- Introduced **typed identifiers**: `TableId`, `ColumnId`, `SegmentId`, `RowId`, `CommitId`.
- Implemented **encoder framework** (`IEncoder`, `IStringEncoder`) with versioning.
- Added numeric encoders:
  - `Int32DeltaBitpackEncoder`
  - `Int64DeltaBitpackEncoder`
  - `GorillaDoubleEncoder`
- Added `StringDictEncoder` with dictionary compression and varint encoding.
- Created **Page system** (`PageMeta`, `PageStats`, `PageAddress`) with CRC validation.
- Built **FilePageStore** with append-only persistence and page indexing.
- Implemented **QueryEngine v0** (projection, filter, aggregation primitives).
- Established **TableDef**, **ColumnDef**, and schema catalog foundations.

### Result
Aouda became capable of ingesting, encoding, and reading columnar pages fully in-memory and on-disk.

📄 *See also:* [P0-COMPLETION.md](./P0-COMPLETION.md)

---

## ✅ P1 — Durability & Recovery (Completed)

**Date:** 2025-Q3  
**Scope:** Write-ahead logging, hybrid row buffering, compaction, and crash recovery.

### Highlights
- Added **Write-Ahead Log (WAL)** with frame-based append and CRC validation.
- Implemented **WalSegmentWriter** and **WalReplayer** for safe crash recovery.
- Introduced **Hybrid Row Area (HRA)** for in-memory, row-oriented buffering.
- Integrated **HRA snapshotting** into QueryEngine to unify query visibility across memory and disk.
- Added **CompactionWorker** and **RetentionManager** for background flushing and pruning.
- Introduced **Checkpoint system** ensuring consistency between WAL and column pages.
- All major recovery and durability tests now pass, including torn WAL detection.

### Result
Aouda now provides full **durable write semantics** — all data survives process restarts, and WAL replay guarantees correctness.

📄 *See also:* [P1-COMPLETION.md](./P1-COMPLETION.md)

---

## 🧩 P2 — Query Layer & Transactions (In Progress)

**Date:** Planned 2025-Q4  
**Scope:** Predicate engine, indexing, and atomic mini-transaction model.

### Planned Additions
- Expression-based predicate filters and vectorized evaluation.
- Index extensions (secondary or bloom-based).
- Lightweight transactional layer (per-table sequence isolation).
- Parallel segment scanning and streaming aggregations.
- Optional JSON or LINQ-based query interface for embedded deployments.

📍 *Tracking in:* [ROADMAP.md](./ROADMAP.md)

---

## 🧩 P3 — Performance & IO Optimization (Planned)

**Date:** 2026-Q1  
**Scope:** Async I/O, adaptive compaction, caching, and performance profiling.

### Planned Additions
- Asynchronous I/O scheduling with batching and prefetch.
- Adaptive compaction thresholds and page merging.
- Hot-page memory cache and configurable eviction policy.
- SIMD-based decoding and filtering.

---

## 🧩 P4 — Integration & Distributed Extensions (Planned)

**Date:** 2026-Q2  
**Scope:** API surface, replication, and distributed query capabilities.

### Planned Additions
- Embeddable API and FFI bindings.
- WAL-based replication and checkpoint synchronization.
- Distributed query coordination with consistency protocol.
- Monitoring and telemetry exports (Prometheus, tracing).

---

## 🔧 Internal Improvements (Ongoing)

| Area | Description |
|-------|-------------|
| **Testing** | 100% coverage for core, WAL, and compaction layers |
| **Docs** | Unified documentation style (Architecture, Roadmap, Completion) |
| **Tooling** | Benchmark suite under `/bench` |
| **Error Handling** | Structured logging and exception hierarchy |
| **Performance** | Continuous profiling on large synthetic workloads |

---

## 🧭 Document Index

| Document | Description |
|-----------|-------------|
| [Architecture.md](./Architecture.md) | Current technical architecture |
| [ROADMAP.md](./ROADMAP.md) | Forward-looking plan (P0–P4) |
| [P0-COMPLETION.md](./P0-COMPLETION.md) | Detailed summary for bootstrap phase |
| [P1-COMPLETION.md](./P1-COMPLETION.md) | Detailed summary for durability phase |

---

## Summary

The changelog now aligns 1:1 with the roadmap and architecture documents.  
Each future P-phase will append a self-contained section following this structure, ensuring consistency between documentation and implementation.

Aouda’s codebase is now mature, modular, and internally consistent — forming the foundation for higher-level analytical and transactional functionality in P2 and beyond.

### 2025-11-15 — Hot/cold persistence semantics documented
- Clarified separation between in-memory storage temperature and on-disk persistence format.
- Documented that shutdown does not implicitly compress hot segments; restart restores segment temperature.
- Updated `ARCHITECTURE.md`, ADR 0007, hot/cold developer guide, and P3 tasks to reflect these invariants.

### 2025-11-15 — P3 roadmap updated to include hot/cold docs and original P3 tasks
- Updated Phase P3 in `ROADMAP.md` to explicitly reference hot/cold ADR, developer guide, and P3 task breakdown.
- Preserved original P3 performance/IO tasks (async IO, adaptive compaction, cache layer, parallel execution) under a new Epic C in the P3 section.

---

## ✅ P34 — Studio Distribution and Server Access (Completed)

**Date:** 2026-06-23  
**Scope:** First-user distribution milestone — publicly hosted Studio, runtime server connection, interactive installer.

### Highlights

- **Hosted Studio at `studio.aouda.com`** — Next.js app deployed to Vercel; any Chrome/Edge user can open it and connect to any Aouda server without installing anything.
- **Connect-to-Server dialog** — runtime server URL + API key input in Studio; persisted in `localStorage`; survives page reload; first-run detection auto-opens the dialog on `studio.aouda.com` with no stored URL.
- **Server switcher** — interactive "Change" button in the top nav (direct mode) opens the Connect dialog at any time.
- **CORS updated** — default allowed origins changed from `hub.aouda.dev + localhost:3000` to `hub.aouda.dev + studio.aouda.com`. New `AOUDA_STUDIO_ORIGIN` env var appends one extra origin without replacing defaults.
- **`GET /_studio/config`** — new public endpoint returning `{ "serverUrl": "/", "theme": "system" }`; used by P35+ embedded Studio.
- **Vercel build compatibility** — `next.config.mjs` conditionally sets `output: "standalone"` only when `NEXT_STANDALONE_OUTPUT=true`; Docker builds set this flag; Vercel builds omit it.
- **`Aouda.Setup` cross-platform installer** — zero-dependency .NET 8 console app; double-click on Windows, `sudo ./aouda-setup` on Linux; interactive prompts; installs Windows Service or systemd unit; creates Start Menu / `.desktop` shortcut; prints server URL and API key.

### Security model documented

The P34 security model covers: IP allowlisting (same model as PostgreSQL/SQL Server exposure), TLS via reverse proxy (Caddy/nginx/Traefik), API key auth, and the browser compatibility matrix (Chrome/Edge work for localhost; Firefox/Safari blocked by mixed-content policy).

### CORS breaking change for operators

`http://localhost:3000` is no longer in the CORS defaults after P34. Operators who connect local Studio or other local clients must add localhost explicitly via `AOUDA_CORS_ORIGINS` or `AOUDA_STUDIO_ORIGIN`. See [Studio guide §10.5](guides/studio.md#105-cors-configuration) and [Cloud and Hub guide §8](guides/cloud-hub.md#cors).

### Result

Aouda is now distributable to first-time users with zero CLI knowledge:
- `studio.aouda.com` is accessible to any Chrome/Edge user.
- `Aouda.Setup.exe` / `aouda-setup` replaces the PowerShell/bash install scripts for interactive installs.
- The existing scripts remain for CI/CD and automation.

📄 *See also:* `aouda/docs/tasks/P34-COMPLETION.md`
