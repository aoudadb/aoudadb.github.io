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

---

## ✅ P17 — Internal Database Catalog & Studio Routing (Completed)

**Date:** 2026-06-26
**Scope:** Hide internal infrastructure databases from the default catalog; fix Studio server-auth routing after fresh install.

### Server

- Added `IsInternal` to persisted `DatabaseOptions`; `_serverauth` and `_settings` are created with `IsInternal = true`.
- **Breaking:** default `GET /api/databases` returns operator-facing databases only (`IsInternal == false`). Use `?include=internal` for the full catalog.
- Response metadata on all database list/get/create paths: `isInternal`, `isAuthDatabase`, `authDatabaseKind` (`"none"` | `"server"` | `"application"`).
- Application auth databases remain in the default list for table inspection.

### `@aouda/client` `0.1.0`

- `DatabaseInfo` extended with catalog metadata fields.
- `databases.list({ includeInternal?: boolean })` appends `?include=internal` when true.

### Studio `0.0.2`

- Server auth admin (Settings → Auth, Admin → Connections) always uses `/api/auth/admin/...`.
- Database selector excludes internal DBs; empty state when none are listable.
- Admin → Databases shows internal rows with badges via `includeInternal: true`.
- Removed `_auth` / `_serverauth` routing sentinels.

### Compatibility

| Artifact | Minimum version |
|----------|-----------------|
| `@aouda/client` | `0.1.0` |
| Studio | `0.0.2` |

📄 *See also:* `aouda/docs/tasks/P17/P17-Auth-Database-Catalog-And-Studio-Routing.md`, [HTTP API § Database Catalog](reference/http-api.md), [SDK compatibility](clients/compatibility.md)

---

## ✅ BL-126 + BL-126b — autoIncrement Toggle (Completed)

**Date:** 2026-07-29
**Scope:** First-class support for toggling `autoIncrement` on and off for existing integer columns, surfaced through the engine, server, TypeScript client SDK, and Studio UI.

### Server / Engine (BL-126)

- New `SchemaChangeType.UpdateColumnAutoIncrement` — the diff engine now produces a proper change (not a warning) when the desired schema sets `autoIncrement: true/false` on an existing integer column.
- `AutoIncrementService.InvalidateCounter` — the apply engine calls this after each toggle; on the next server-managed insert, the counter recovers from `MAX(column) + 1` instead of starting at 1.
- Only integer types (`Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`) are eligible. The diff engine produces a warning for non-integer types rather than a change.
- `DiffSummary.ColumnsAltered` — new field counting `UpdateColumnAutoIncrement` (and future column-level alterations). Optional; older server responses omit it.
- `CatalogApi.SetColumnAutoIncrementAsync` — new catalog-level API wired into the apply engine.
- **Breaking (docs only):** the warning `"AutoIncrement change ... is not supported."` no longer appears for integer columns. Non-integer column autoIncrement changes still warn.

### `@aouda/client` `0.1.6` (BL-126b)

- `DiffSummary.columnsAltered?: number` — new optional field on the TypeScript `DiffSummary` interface. Undefined when the server does not return it (backward-compatible).
- `SchemaChange.type` remains `string` — the value `"UpdateColumnAutoIncrement"` passes through automatically; no breaking change.

### Studio `0.0.13` (BL-126b)

- **Toggle AutoId action** — "Toggle AutoId" appears in the column actions menu for integer-type columns. Clicking it opens the Toggle AutoId dialog.
- **Toggle AutoId dialog** — shows direction (Manual → Auto or Auto → Manual), table and column names, and a warning about counter recovery on the Manual → Auto path.
- **Schema Diff View improvements** — `UpdateColumnAutoIncrement` changes render in blue with the label "Toggle auto-increment" (not the raw type string); summary line includes `N column(s) altered` when `columnsAltered > 0`.
- `@aouda/client` dependency bumped from `0.1.5` to `0.1.6`.

### Counter recovery detail

When you enable autoIncrement on a column that already contains data, the engine sets the counter to `MAX(existing values) + 1` on first use. This prevents conflicts with existing manually-inserted IDs. If the table is empty, the counter starts at 1.

### Known limitations (deferred)

- WAL record for `UpdateColumnAutoIncrement` is not written — the toggle is durable through the catalog but not replayed from WAL on crash recovery. Tracked as a known gap.
- IDENTITY seed configuration (custom starting value) is not yet exposed.
- `SchemaChange.type` is `string`, not a typed union. A union type is a separate backlog item.

### Compatibility

| Artifact | Minimum version |
|----------|-----------------|
| `@aouda/client` | `0.1.6` (for `DiffSummary.columnsAltered`) — `0.1.5` still works, field is absent |
| Studio | `0.0.13` (for Toggle AutoId UI) |

📄 *See also:* [Schema Lifecycle guide §2.11](guides/schema.md), [Studio guide §5.5](guides/studio.md), [TypeScript client §8](clients/typescript.md), `aouda/docs/tasks/BL/BL-126-AutoIncrement-Toggle.md`, `aouda/docs/tasks/BL/BL-126b-AutoIncrement-Toggle-Client-And-Studio.md`

---

## ✅ BL-130 + BL-131 — Identity-insert (Completed)

**Date:** 2026-07-30 / 2026-07-31
**Scope:** Request-scoped (ordinary insert) and job-scoped (P20 bulk-load) identity-insert so clients can supply explicit values on `autoIncrement` columns — including literal `0` — without flipping catalog `autoIncrement` (BL-126). After a successful insert or bulk-load commit, the runtime counter advances to `max(inserted)` via `EnsureMinimumValue`. Equivalent to Bond `isAutoIncrementDisabled: true`.

### Ordinary insert (BL-130)

- Wire: optional `identityInsert` on `InsertMessage` / `POST …/tables/{name}/rows`.
- Engine: skip allocation; validate every autoIncrement column present/non-null; bump counter only after successful commit.
- C# / Embedded: `InsertAsync(..., identityInsert: true)` (single + batch).
- `@aouda/client`: `insert` / `insertMany` second-arg options `{ identityInsert?: boolean }`.
- Default path unchanged: without the flag, `0` still means auto-generate; explicit non-zero without the flag does not bump the counter.

### Bulk-load (BL-131)

- Wire: optional `options.identityInsert` on `POST …/bulk-load:begin`.
- Engine: stream wrap in `AoudaEngine.BulkLoadAsync`; `EnsureMinimumValue` only after successful `RunAsync` (abort/fail does not bump).
- C# / Embedded: `BulkLoadOptions.IdentityInsert`.
- `@aouda/client`: `bulkLoad(..., { identityInsert: true })`.
- Default bulk-load path unchanged (coerce-to-0 / no allocation / no counter bump from bulk-load alone).

### Contrast with BL-126

| Feature | Schema change? | Scope | Use when |
|---------|----------------|-------|----------|
| Identity-insert | No | One request or one bulk-load job | Seed/reseed reserved IDs |
| Toggle AutoId | Yes | All future writes | Permanently switch Auto ↔ Manual |

### Known limitations

- Studio has no identity-insert UI (API/SDK only).
- IDENTITY seed/increment configuration knobs remain unimplemented (ADR 0013).
- `@aouda/client` npm changeset/version bump for bulk-load options may ship on a separate client PR — confirm published version before depending on `bulkLoad({ identityInsert: true })` in production.

### Compatibility

| Artifact | Notes |
|----------|-------|
| Server / wire | Unreleased entry in `aouda/docs/CHANGELOG.md` — ships with next server train |
| C# `Aouda.Client` / Embedded | Co-release with server |
| `@aouda/client` | Patch proposed after maintainer confirmation (`0.1.6` → `0.1.7`) |

📄 *See also:* [HTTP API — insert & bulk-load](reference/http-api.md), [Bulk Load guide § Scenario 4](guides/bulk-load.md), [Getting Started — Seeding explicit IDs](getting-started/index.md), [TypeScript client §7](clients/typescript.md), [Schema Lifecycle § Scenario 6](guides/schema.md), `aouda/docs/tasks/BL/BL-130-Identity-Insert.md`, `aouda/docs/tasks/BL/BL-131-Identity-Insert-BulkLoad.md`
