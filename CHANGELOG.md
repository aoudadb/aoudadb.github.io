---
title: "Changelog"
nav_order: 9
---

# Aouda Changelog

Public, user-facing release notes. Engine phase status lives in the server
[CHANGELOG](https://github.com/aoudadb/aouda/blob/main/docs/CHANGELOG.md) and
[ROADMAP](https://github.com/aoudadb/aouda/blob/main/docs/ROADMAP.md) (P0–P43 complete).

---

## Unreleased

## 0.1.19 — 2026-09-04

**Memory governor, Timestamp MQ, table row counts, phone MFA.** Server **0.1.19**, `Aouda.Client` **0.1.19**, `@aouda/client` **0.1.18** (unchanged), Studio **0.0.23**. See [Compatibility](clients/compatibility.md).

- **Per-database memory accounting (BL-366).** PK-cache reservations no longer leak into the governed ceiling; `MEMORY_BUDGET_EXCEEDED` names the database and reservation categories; `GET /api/server/memory` gains `reservedBytes` / `governedCeilingBytes` / `reservedByCategory`.
- **Timestamp Materialized Query build (BL-373).** MQ build/rebuild over `Timestamp` columns no longer throws; `Date`/`Timestamp` key encoding is canonicalised.
- **Bulk-load table row counts (BL-374).** `GET …/tables` `rowCount` is catalog-backed (not residency-dependent); responses gain `rowCountIsExact`.
- **Phone MFA enroll is idempotent (BL-363).** A second phone enroll for the same user returns 409 `AUTH_MFA_FACTOR_ALREADY_ENROLLED` instead of creating a duplicate `_mfa_factors` row. Existing factor id in `detail`. Replace a number with `DELETE .../mfa/factors/{id}` then re-enroll.

## 0.1.18 — 2026-09-02

**BL-362 auth identity integrity.** Server **0.1.18**, `Aouda.Client` **0.1.18**, `@aouda/client` **0.1.18** (unchanged), Studio **0.0.23**. See [Compatibility](clients/compatibility.md).

- **Unique email + id-keyed admin mutations.** `_users.email` is unique on new auth databases (backfilled when duplicate-free). Admin password/disable/enable/PATCH update by user id; DELETE revokes JWTs then cascades by id. Duplicate-email sign-in verifies every matching hash. [Auth reference](auth/reference.md), [HTTP API](reference/http-api.md).

## 0.1.17 — 2026-09-02

**Keyless browser app-auth + auth hardening.** Server **0.1.17**, `Aouda.Client` **0.1.17**, `@aouda/client` **0.1.18**, Studio **0.0.23** (pin `@aouda/client` **0.1.18**). See [Compatibility](clients/compatibility.md).

- **Keyless browser login (BL-355, breaking).** Public app-auth POSTs (signup, signin, refresh, password-reset) no longer require `mk_anon_*`. Construct `@aouda/client` / `Aouda.Client` with the data-plane URL and database name only. Self-registration is **opt-in** (`AllowSelfSignup`, default off — BL-357) and grants `db_writer` unless `selfSignupRole` is set. CORS `*` on the data-plane lets any origin call those routes. `mk_pub_*` is still required for pre-auth named queries (BL-356). [Auth](getting-started/auth.md), [HTTP API](reference/http-api.md), [Direct client access](guides/direct-client-access.md).
- **Self-service signup switch (BL-357, breaking).** Signup is off until an operator enables it (`PUT …/auth/admin/signup-settings` or create-database `allowSelfSignup`). Disabled signup is **403** `AUTH_SIGNUP_DISABLED`. [Auth](getting-started/auth.md), [HTTP API](reference/http-api.md).
- **Trusted-proxy client IP (BL-359).** Per-IP rate limits, lockout attribution, and `_audit_log` client IPs are the proxy's address until you set `Aouda:ForwardedHeaders`. Off by default; enabling with no trust list is a startup error. [Behind a reverse proxy](deployment/reverse-proxy.md).
- **Failed-signin ceiling (BL-360).** Optional `Aouda:Auth:FailedSigninCeiling` (off by default) caps failed sign-ins per auth database — the credential-stuffing shape that per-IP limits and lockout cannot see. Per process; successful logins do not count until the ceiling trips, after which every sign-in on that database is 429 until the window drains. [Auth reference](auth/reference.md#rate-limiting).
- **Data-plane CORS startup warnings (BL-358).** Bound data-plane with `CorsOrigins` `*` or unset logs a warning; policy unchanged.

## 0.1.16 — 2026-09-02

**BL-186 complete — point-in-time recovery is shipped.** Server **0.1.16**, `Aouda.Client` **0.1.16**, `@aouda/client` **0.1.17**, Studio **0.0.22** (pin `@aouda/client` **0.1.17**). See [Compatibility](clients/compatibility.md).

- **PITR over HTTP and both SDKs.** `POST /admin/backup/restore` accepts `targetTime`; list responses gain `pitrEligible`; restore responses gain `targetTime` / `pitr`. Exact restore unchanged. Studio backup UI stays exact-restore-only. [Backup and restore](guides/backup.md), [HTTP API](reference/http-api.md), [TypeScript client](clients/typescript.md).
- **BL-343.** Unfiltered `POST /query` no longer 500s when the catalog is wider than a segment (derived / never-written columns synthesize defaults).

## 0.1.15 — 2026-09-01

**BL-319 Derive pilot gap close + BL-312 + BL-186 progress (mid-stream).** Server **0.1.15**, `Aouda.Client` **0.1.15**, `@aouda/client` **0.1.16** (unchanged), Studio **0.0.21**. See [Compatibility](clients/compatibility.md).

- **Derive pilot fixes (BL-319).** C# fluent `In`/`Nin`; omitted named-query `offsetParam` binds skip **0**; data-plane named-query / named-mutation execute returns `404` (not existence-leaking 401/403); App Auth GET user/roles no longer 500 on empty roles; CLI `start -h` does not boot; MQ `:refresh?await=true` can return 200; creator `db_admin` on new data DBs. [Named queries](guides/named-queries.md), [HTTP API](reference/http-api.md), [Direct client access](guides/direct-client-access.md).
- **Sealed-segment backups (BL-312).** Backups now capture `segment.manifest`; restored cold/sealed data returns rows again.
- **Backup / restore / archive (BL-186 partial).** Exact restore re-bases WAL + catalog; backup WAL position is per-database; archive positions are byte offsets and `WalArchiveWorker` runs when archive is configured; restore divergence handshake (v4). **PITR over HTTP/SDK is still not shipped** — no restore target-time API yet. [Backup and restore](guides/backup.md), [Storage](guides/storage.md).

## 0.1.14 — 2026-08-29

**P41 ingest remainder, P42 metadata at scale, P43 write-side authorization.** Server **0.1.14**, `@aouda/client` **0.1.16**, `Aouda.Client` **0.1.14**, Studio **0.0.21** (pin `@aouda/client` **0.1.16** after npm). See [Compatibility](clients/compatibility.md).

- **Catalog GET is metadata-only; linkage is no longer omitted.** `GET`/`list` `/api/databases` now document `auth.enabled` / `auth.database` (never `mk_*`). `authDatabaseKind: "none"` on a data DB does not mean unlinked. HTTP API v2.6. [HTTP API](reference/http-api.md#get-apidatabasesname).
- **Create role contract.** `POST …/auth/admin/roles` requires `name`; `permissions` is optional (empty grants nothing). `actions` is a string, not an array. 400 bodies include `error` / `suggestion`. [Auth reference](auth/reference.md), [Use cases](auth/use-cases.md).
- **Health vs ready.** Wait on `GET /ready` and `GET /api/databases/{name}` `state=Active` before schema apply; `/health` is liveness only. [`/ready` is unchanged](reference/http-api.md#get-health) for a `Dropping` sibling database.
- **P43 write-side authorization (docs).** Public pages now name the code's RLS value sources (`UserId`, `Literal`, `PartitionGrant`), admin-API resolver authoring, identity stamp (`"derived": { "identity": "subject" }`), `plsClaimBinding`, `writeCheckRules`, and per-user claims. Conformance fixture: [`examples/p43-write-side/`](examples/p43-write-side/).
- **P42 catalog directory (operators).** Live catalog is `catalog.root.json` plus per-table shards. Opening a pre-P42 database migrates forward; there is no downgrade. Lazy catalog residency is the shipped default. [Storage](guides/storage.md).

## 0.1.10 — 2026-08-23

**BL-188 complete — named-query name identity.** Server **0.1.10**, `@aouda/client` **0.1.15**, `Aouda.Client` **0.1.10**, Studio **0.0.20** (pin `@aouda/client` **0.1.15**). See [Compatibility](clients/compatibility.md).

- **Breaking — named-query name identity (BL-188).** The unique schema name is the only identity across HTTP, WebSocket, both SDKs, Studio, and these docs. Execute/batch/subscribe send the name; omitting a name deletes the definition; codegen is types-only (optional Args/Row). Alias surface and `NAMED_QUERY_ALIAS_MISMATCH` are retired. [Named queries](guides/named-queries.md), [HTTP API v2.5](reference/http-api.md).
- **`firstPerKey` / `topNPerGroup` materialized queries (BL-187).** Schema apply and HTTP create. `firstPerKey` is MIN of `orderBy`, not arrival order. `topNPerGroup` maintains at most N rows per group; working set is in-memory (use a compact per-key source). A Top-N whose `sourceTable` is another materialized query (for example `latestPerKey`) follows that source incrementally. Query the result table by name. [Schema management](guides/schema-management.md#materialized-queries-in-the-schema-file), [Materialized queries](guides/materialized.md).
- **P38 — Freshness and replica consistency.** New [Freshness](guides/freshness.md) guide: one 42-hex consistency token (`AtLeast`, not `AsOf`), `GET /api/databases/{db}/token`, named-query alias `freshness`, SDK store (`consistencyTokenStore` / `IConsistencyTokenStore`). HTTP API v2.4: `X-Aouda-Token` / `?at_least=` (query wins), `TOKEN_*` / `FRESHNESS_*` errors, stream `token` alongside `version`, bulk-load commit field `walPosition` → `token`. **Breaking:** `MaxLagSeconds` is measured staleness, not lag-bytes ÷ 1 MB/s. Caveats are first-class: scale-out in-memory store (gate 13), clock skew, `w:1` → `TOKEN_EPOCH_SUPERSEDED`, MQ watermark, token volume leak, blocking `waitMs` (default 250), Hub CP-B4 not shipped. Default read preference remains `Primary`.
- **Local CLI testing for agents.** New [Local CLI testing (agents)](ai/local-cli-testing.md): throwaway `aouda start` recipe (unused ports, temp `--data-dir`, pin CLI, stop with `-s`), plus engine/CLI traps — `aouda start -h` boots on `:5000` into `./data`; data-plane executes named-query **names** (not `POST /query`); `CorsOrigins` is one string; schema `partitionKey` / `where.and` / `offset` cap; columnar bodies; keys returned once. [Direct client access](guides/direct-client-access.md) CORS example corrected from a JSON array to a string. Linked from [llms.txt](llms.txt), [AI quick start](ai/quick-start.md), and [AI Agents](ai/index.md).

## 0.1.8 — 2026-08-19

**Three adoption gaps closed.** Server **0.1.8**, `@aouda/client` **0.1.12**, `Aouda.Client` **0.1.8**, Studio **0.0.17** (pin unchanged). See [Compatibility](clients/compatibility.md).

- **Typed subscribe-by-hash (BL-173).** `client.namedQueries.subscribe(hash, args, { conflate })` and `NamedQueries.SubscribeAsync(hash, args, options)` — the data-plane's only streaming path no longer requires hand-rolled WebSocket frames. Returns the same subscription object as table subscribe, so `gap` resume, reconnect, `re_auth`, and `SLOW_CONSUMER` recovery are unchanged. [Named queries](guides/named-queries.md#subscribe-by-name).
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

