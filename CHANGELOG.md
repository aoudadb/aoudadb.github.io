---
title: "Changelog"
nav_order: 9
---

# Aouda Changelog

Public, user-facing release notes. Engine phase status lives in the server
[CHANGELOG](https://github.com/aoudadb/aouda/blob/main/docs/CHANGELOG.md) and
[ROADMAP](https://github.com/aoudadb/aouda/blob/main/docs/ROADMAP.md) (P0–P37 complete).

---

## Unreleased

## 0.1.8 — 2026-08-19

**Three adoption gaps closed.** Server **0.1.8**, `@aouda/client` **0.1.12**, `Aouda.Client` **0.1.8**, Studio **0.0.17** (pin unchanged). See [Compatibility](clients/compatibility.md).

- **Typed subscribe-by-hash (BL-173).** `client.namedQueries.subscribe(hash, args, { conflate })` and `NamedQueries.SubscribeAsync(hash, args, options)` — the data-plane's only streaming path no longer requires hand-rolled WebSocket frames. Returns the same subscription object as table subscribe, so `gap` resume, reconnect, `re_auth`, and `SLOW_CONSUMER` recovery are unchanged. [Named queries](guides/named-queries.md#subscribe-by-hash).
- **Materialized queries in `aouda.schema.json` (BL-174).** Top-level `materializedQueries` map (`latestPerKey`, `aggregate`, `filter`) managed by `schema diff` / `apply` / `export`. **A present map is desired state and drops anything not listed; omitting it leaves MQs unmanaged.** [Schema management](guides/schema-management.md#materialized-queries-in-the-schema-file).
- **String and rounding functions (BL-175).** `ScalarExprNode` gains `type: "call"` with a closed allowlist — `upper`, `lower`, `trim`, `concat`, `substring`, `round`, `roundTo`, `cast` — plus `$upper` … `$cast` operators in the TypeScript `.update()` builder. Normalization can now move out of an ingest service. [Insert-time transforms](guides/insert-transforms.md#call--string-and-rounding-functions), [Bulk mutations](guides/bulk-mutations.md#string-and-rounding-operators).

**New:** [Adopting Aouda in an existing application](guides/adoption.md) — the P37 target architecture for an app that already has a frontend, a gateway, and services: which hops stop earning their keep, an honest SDK coverage table, what direct access does to subscription and quota capacity, and the order to migrate in.

**Corrected:** [Auth architecture](auth/architecture.md) Pattern B described the pre-P37 model — a browser holding `mk_anon_*` and running ad-hoc `table().execute()`. Both are now refused. It documents `mk_pub_*`, the data-plane listener, and named queries.

**Added:** `policy inspect` in [Access-surface diff](guides/access-surface.md) ("what would this user see?"), with a corrected `aouda.identities.json` example — `identities` is an object keyed by name, and grants require `dimension` + `partitionKey` + `accessLevel`. [Insert-time transforms](guides/insert-transforms.md) gains failure semantics: a failed check or unmatched `route` fails **the whole batch**, `route` must be exhaustive, and quarantine is a table plus a catch-all route rather than a built-in dead-letter path. [Client integration](auth/client-integration.md) key tables now list `mk_pub_`.

## 0.1.7 — 2026-08-19

Public docs for **P37 Direct Client Access**: named queries (execute, batch, subscribe-by-hash, codegen), data-plane listener and `mk_pub_*`, insert-time transforms, access-surface diff (`aouda schema diff --access`), and the division-of-responsibility guide. HTTP API v2.3 documents `snapshot_complete`, `gap`, `re_auth`, `values_skipped`, and the credential/listener matrix. OAuth authorization-code + PKCE is **not** documented as available.

Guides: [Named queries](guides/named-queries.md), [Direct client access](guides/direct-client-access.md), [Division of responsibility](guides/division-of-responsibility.md), [Insert-time transforms](guides/insert-transforms.md), [Access-surface diff](guides/access-surface.md), [HTTP API](reference/http-api.md). Server **0.1.7**, `@aouda/client` **0.1.11**, Studio **0.0.17**. See [Compatibility](clients/compatibility.md).

---

## 0.1.6 — 2026-08-13

Server **0.1.6** treats `MaxTotalRamBytes` as a process RSS ceiling (default ~70% of detected RAM), keeps the write-ahead log bounded, and refuses over-budget ingest with HTTP 503 + `Retry-After`. Studio **0.0.16** shows RSS vs governed budget, reclaimable WAL, and quarantined databases. See [Sizing](guides/sizing.md), [Write durability](guides/write-durability.md), and [Compatibility](clients/compatibility.md).

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

## Historical notes

Versioned releases above are the public record. Engine phases P0–P37 are complete;
see the engine [ROADMAP](https://github.com/aoudadb/aouda/blob/main/docs/ROADMAP.md)
and [CHANGELOG](https://github.com/aoudadb/aouda/blob/main/docs/CHANGELOG.md).
The 2025 P0–P4 “in progress / planned” narrative that used to live here is not current.

