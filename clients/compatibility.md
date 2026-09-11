---
title: "SDK Compatibility"
nav_order: 3
parent: "Clients"
---

# SDK Compatibility Matrix

Aouda ships multiple artifacts from separate repositories. They do **not** share a single version number. Use this matrix to pick compatible combinations.

---

## Versioning model

| Artifact | Package / image | Repo | Version scheme |
|----------|-----------------|------|----------------|
| Aouda server | `aouda/server` (Docker), `Aouda.Server` (binary) | `aouda` | Release train (not npm SemVer) |
| TypeScript client | `@aouda/client` (npm) | `aouda-client-ts` | SemVer |
| .NET client | `Aouda.Client` (NuGet) | `aouda` | SemVer |
| Studio | `aouda/studio` (Docker), hosted app | `aouda-studio` | App version |

**Release order** when APIs change: server → SDKs → Studio → docs.

---

## Compatibility matrix

Update this table when shipping breaking server, client, or Studio changes.

| Server (approx.) | Wire protocol | `@aouda/client` | `Aouda.Client` (NuGet) | Studio (approx.) | Notes |
|------------------|---------------|-----------------|------------------------|------------------|-------|
| `0.1.25` | `2` | `≥ 0.1.22` (no TS surface for this train's server-only work) | `≥ 0.1.25` | `≥ 0.0.26` | **P48 MemoryCeilingHonesty** — the Derive lab OOM-cascade incident: host memory ceiling now reflects real availability (not total RAM) on non-cgroup-bounded hosts; admission also refuses on real CLR heap pressure; a `HeapExhaustionWatchdog` exits a truly heap-dead process so an orchestrator can restart it; new `/api/server/memory` fields, Docker/Helm packaging, [sizing guide](../guides/server-configuration.md). **BL-474** — scan-fed materialized-query rebuild (`:refresh`, restart, schema-change) now accounts its memory honestly instead of risking an OOM, can spill an over-budget accumulator to its shadow table (~3× more groups), and gains a bulk-refresh surface: `POST /api/databases/{db}/materialized-queries:refresh` (`sourceTable`/`staleOnly`/`names`), SDK `RefreshTableAsync`/`RefreshManyAsync`, CLI `--source-table`/`--stale-only`. **BL-470/471/472** and a segment-pin/deletion race (ADR 0047 D-5/D-6) — correctness fixes for a hot segment that could get stuck unable to demote, a cold-merge cohort that could stall forever, and a tier move that could resurrect a duplicate catalog entry after a concurrent merge. |
| `0.1.24` | `2` | `≥ 0.1.22` (pin after npm — published line still `0.1.21`) | `≥ 0.1.24` | `≥ 0.0.25` | **BL-461** opt-in case-insensitive string comparison (`ignoreCase` on `eq`/`ne`/`in`/`nin`/`like`, String columns; see [HTTP API](../reference/http-api.md#like-semantics)); a run of concurrency/correctness fixes (**BL-441/446/447/448/449/460/396**: stale segment views under concurrent coalesce, segment-discovery-cache poisoning, WAL manifest rename retries, freeze/abort races, materialized-query routing soundness, nullable top-k, segment reference lifetime); **BL-468/469** malformed PK literal / RLS deny-clause type fixes; named-artifact least-privilege authorization scope; deploy-time 429 on catalog reads; long-poll admin-trust, concurrent-poll, and JWT-expiry hardening plus diagnosability (404 masking now logs its real reason). |
| `0.1.23` | `2` | `≥ 0.1.21` | `≥ 0.1.23` | `≥ 0.0.25` | WebSocket subscribe no longer self-killed by the server's own snapshot high-water mark; long-poll streaming reachable on the data-plane listener (previously a bodyless 404); streaming transports (`/ws`, long-poll) exempted from the general concurrency lane; two stream-auth paths fail closed instead of granting a service-key-level RLS/partition bypass. |
| `0.1.22` | `1` | `≥ 0.1.21` (MQ wait APIs / `mqRebuildStatus`; `isStale` / `staleReason`) | `≥ 0.1.22` | `≥ 0.0.25` (pin `@aouda/client` **0.1.21**) | **BL-432** derived-column predicate cold/hot scan gap; **BL-424** hot coalesce row tear; **BL-427** MQ queue-drop staleness (`isStale` / `staleReason`; health Degraded); **BL-419** MQ refresh await + client wait APIs, `MaxConnections` default `0`, `RefreshAwaitTimeout` 120s; **P46** single-pass bulk-load MQ materialization; **BL-423** bounded startup/shutdown; WS auth handshake harden. |
| `0.1.21` | `1` | `≥ 0.1.20` (`batchParam` on named-mutation insert) | `≥ 0.1.21` | `≥ 0.0.24` | **BL-416** named-mutation batch insert; **BL-417** user-linked custom API keys; **BL-404/405** bulk-load admission lane + empty-response / append-retry fixes; **BL-411–414** PK scan / hot ALTER gaps. Studio pin stays `@aouda/client` **0.1.19** until the next npm cut. |
| `0.1.20` | `1` | `≥ 0.1.19` (column `id`; `rowCountIsExact`; elastic memory fields) | `≥ 0.1.20` | `≥ 0.0.24` (pin `@aouda/client` **0.1.19** after npm) | **P45 S06–S08** spill/merge + page sizing; **OutOfTheBox-Ingest** elastic shares / single-node profile; **BL-382** column DDL + schema `id`; **BL-378/379** hot validity; **BL-398/395** table data-directory identity; Bool/coalesce/merge fixes. |
| `0.1.19` | `1` | `≥ 0.1.18` | `≥ 0.1.19` | `≥ 0.0.23` | **BL-366** per-database memory governor accounting + richer `GET /api/server/memory`. **BL-373** Timestamp MQ / Date key encoding. **BL-374** catalog `rowCount` + `rowCountIsExact`. **BL-363** idempotent phone MFA enroll. No TS/Studio pin change. |
| `0.1.18` | `1` | `≥ 0.1.18` | `≥ 0.1.18` | `≥ 0.0.23` | **BL-362** auth identity integrity (unique email, id-keyed admin mutations, DELETE revoke+cascade). No TS/Studio pin change. |
| `0.1.17` | `1` | `≥ 0.1.18` (keyless `client.auth` without `appAuth.apiKey`) | `≥ 0.1.17` | `≥ 0.0.23` (pin `@aouda/client` **0.1.18**) | **BL-355** keyless browser app-auth (breaking: no API key on public auth POSTs). **BL-357** self-signup opt-in (default off). **BL-358** CORS startup warnings. **BL-359** trusted-proxy client IP. **BL-360** failed-signin ceiling. |
| `0.1.16` | `1` | `≥ 0.1.17` (`restore({ backupId, targetTime })`; `pitrEligible`) | `≥ 0.1.16` (`RestoreAsync(RestoreBackupRequest)`) | `≥ 0.0.22` (pin `@aouda/client` **0.1.17**) | **BL-186 complete.** PITR on recovery path; recoverable-window metrics/`db inspect`; PITR over HTTP and both SDKs; final docs. **BL-343** derived-column row-window synthesis. Studio backup UI stays exact-restore-only. |
| `0.1.15` | `1` | `≥ 0.1.16` | `≥ 0.1.15` (C# fluent `In`/`Nin`; BL-319 pilot fixes) | `≥ 0.0.21` | **BL-319** Derive pilot gap close (fluent `In`/`Nin`, omitted `offsetParam` → 0, data-plane named-query 404, App Auth empty-roles). **BL-312** sealed-segment `segment.manifest` in backups. **BL-186** partial: backup WAL position, exact restore WAL/catalog re-base, archive position units + worker wiring, restore divergence handshake (S02–S05, S10). PITR HTTP/SDK not in this train. Studio pin stays `@aouda/client` **0.1.16**. |
| `0.1.14` | `1` | `≥ 0.1.16` (`DatabaseAuthInfo`; P43 `derived.identity` / `plsClaimBinding`; BL-180 MQ schema fields; BL-185 `rowErrors`) | `≥ 0.1.14` | `≥ 0.0.21` | **P42** catalog directory + lazy residency default (forward-only formats 2→3→4; no downgrade). **P43** identity stamp, PLS claim binding, write-check, claims at mint. Catalog GET/list `auth.enabled` / `auth.database` (HTTP API v2.6). P41 ingest remainder. Studio **0.0.21** pins `@aouda/client` **0.1.16** after npm. |
| `0.1.10` | `1` | `≥ 0.1.15` (name identity; consistency token store; stream `token`) | `≥ 0.1.10` | `≥ 0.0.20` | BL-188 name-only named queries/mutations (breaking wire); BL-187 `firstPerKey` / `topNPerGroup`; P38 freshness (`AtLeast`, `TOKEN_*` / `FRESHNESS_*`, bulk-load `token`). Studio **0.0.20** pins `@aouda/client` **0.1.15** and drops hash UI. |
| `0.1.9` | `1` | `≥ 0.1.14` (`totalMatches`; `orderByIndex` / `whenParamPresent` / `orderByChoices` / `count`; `collapse_inserts`) | `≥ 0.1.9` | `≥ 0.0.19` | P40 data-plane completeness: MQ `dataPlaneAccess` + `outputName` vocabulary (`D-31` break); named-query count / optional predicates / bounded sort; conflation that conflates; computed MQ ranking; row-index diagnostics. Studio **0.0.19** pins `@aouda/client` **0.1.14**. |
| `0.1.8` | `1` | `≥ 0.1.12` (`namedQueries.subscribe`; `$upper`…`$cast` call operators) | `≥ 0.1.8` | `≥ 0.0.18` | BL-173 typed subscribe-by-hash; BL-174 `materializedQueries` in `aouda.schema.json`; BL-175 `call` string/rounding functions; BL-171/172 bulk-load Timestamp ISO-8601 and NULL validity. Studio **0.0.18** (P39) pins `@aouda/client` **0.1.13** and calls subscribe-by-hash, named-artifact execute, policy inspect, and schema-file MQ maps. |
| `0.1.7` | `1` | `≥ 0.1.11` (named-query execute/batch/mutate; snapshot paging / `gap` resume; `re_auth`; conflate) | `≥ 0.1.7` | `≥ 0.0.17` | P37 Direct Client Access: fail-closed ADRA, named queries, data-plane listener + `mk_pub_*`, access-surface diff. Studio pin `@aouda/client` `0.1.11` after that npm version is published. Breaking: ADRA fail-closed configs, bulk-load transform intent flags, `Live()` / `HotCacheSettings` removed (BL-162). |
| `0.1.6` | `1` | `≥ 0.1.9` (503 `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` retry; additive RSS/WAL/quarantine metrics types) | `≥ 0.1.6` | `≥ 0.0.16` | Bounded durability: process RSS ceiling, bounded WAL, retryable back-pressure, quarantine inspect. Studio pin `@aouda/client` `0.1.9` after that npm version is published. |
| `0.1.5` | `1` | `≥ 0.1.8` (P36 `alterColumn` / `reorderColumns` / `jobs` / typed `SchemaChangeType`) | `≥ 0.1.5` | `≥ 0.0.15` | P36 Column Evolution train: ALTER COLUMN HTTP + clients + Studio schema UI. Studio pin `@aouda/client` `0.1.8`. |
| `0.1.4` | `1` | `≥ 0.1.7` (BL-132 outbox + `acknowledgeDevCapture`; BL-130/131 `identityInsert`) | `≥ 0.1.4` | `≥ 0.0.14` | Patch train: capture notification outbox, identity-insert (row + bulk-load). Studio notifications UI uses outbox via admin HTTP; pin `@aouda/client` `0.1.7`. |
| `0.1.3` | `1` | `≥ 0.1.6` (BL-126 `columnsAltered`; residency filter fields still HTTP-raw) | `≥ 0.1.3` | `≥ 0.0.13` | Patch train: BL-091 residency HTTP, BL-126 autoIncrement toggle, async durable DB drop, partition routing, freeze/abort correctness. |
| `0.1.2` / earlier | `1` | `≥ 0.0.1` (`0.0.3`+ LNA; `0.1.0`+ P17 database catalog) | `≥ 0.1.0` | `≥ 0.0.2` | P17: internal DB filtering + catalog metadata — Studio `0.0.2` pins `@aouda/client` `0.1.0`. Hosted Studio → localhost needs client `≥ 0.0.3`. |

### Reading the matrix

- **Wire protocol** — HTTP header `X-Aouda-Protocol-Version`. Server and clients must agree on supported protocol versions.
- **`@aouda/client`** — Minimum npm version for a server generation. Studio may pin a specific patch (see `aouda-studio/package.json`).
- **`Aouda.Client`** — NuGet version for .NET apps and Hub; tracks API parity with the TS client but versions independently.
- **Studio** — Requires a server reachable at runtime; build-time dependency is only `@aouda/client`.

---

## Pre-1.0 guidance

While `@aouda/client` is `0.x`:

- Pin **exact** versions in production (`"0.0.1"`, not `"^0.0.1"`).
- Prefer **patch** releases for additive API while on the `0.0.x` line (`0.0.3` → `0.0.4`). A Changesets **minor** bump advances the middle digit (`0.0.3` → `0.1.0`).
- Regenerate TypeScript schema types after server schema changes: `npx @aouda/client generate`.

---

## Release documentation

| Topic | Location |
|-------|----------|
| **Cross-repo bump procedure (agents)** | Shared docs repo: `Cross-Repo-Release-And-Version-Bump.md` (chain map). **This repo:** [`dev/Release-And-Version-Bump.md`](../dev/Release-And-Version-Bump.md). Server: `aouda/docs/dev/Release-And-Version-Bump.md`. |
| npm Changesets + publish | [aouda-client-ts `docs/dev/Release-Process.md`](https://github.com/aouda/aouda-client-ts/blob/main/docs/dev/Release-Process.md) |
| Studio pin + local link | [aouda-studio `docs/dev/Dependency-Policy.md`](https://github.com/aouda/aouda-studio/blob/main/docs/dev/Dependency-Policy.md) |
| TypeScript client API | [TypeScript Client](./typescript.md) |

Dependency bumps are **manual**. Agents follow the cross-repo release doc after each `@aouda/client` publish.
