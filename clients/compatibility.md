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
