---
title: "What a browser-tier read cannot do"
nav_order: 8.5
parent: "Guides"
---

# What a browser-tier read cannot do

Document status: Complete (P40 S03)  
Last updated: 2026-08-20

A **browser-tier** caller is `mk_pub_*` or an end-user JWT on the **data-plane listener**. It cannot compose an ad-hoc `QueryMessage`. It sends a named-query **hash** plus arguments. This page is the list that page should have been: what that surface refuses, why, and what to do instead.

Enumerable tables below are generated from the validators that enforce them. If a table and the engine disagree, the engine wins and this page is stale — pinned by `BrowserTierReadLimitsDocsTests`.

**Related:** [How to build apps effortlessly with Aouda](build-apps.md) · [Named queries](named-queries.md) · [Direct client access](direct-client-access.md) · [Partitioning](partitioning.md) · [Access-surface diff](access-surface.md)

---

## Start here

| I want to… | Go to |
|---|---|
| See the allowed operators / routes / subscribe refusals | [Generated tables](#generated-from-the-validators) |
| Know why my watchlist `in` filter is legal | [Partition-filter rule](#partition-filter-rule) |
| Know why `crossPartitionAccess` is not on a named query | [No cross-partition on the data plane](#no-crosspartitionaccess-on-a-named-query) |
| Page a list with "1–25 of 412" | [What you can do](#what-you-can-do) (`count` / `totalMatches`) |
| Sort by a computed value | [Stored `derived` columns](#no-expression-orderby) |
| Last-price at ~10 Hz | [Conflation](#conflate-is-a-no-op-on-insert-only-streams) |

---

## Generated from the validators

Hand-written rationale is in the sections after this block. Do not edit the tables by hand.

<!-- BEGIN GENERATED BROWSER-TIER-LIMITS -->

### Filter operators (`WhereClause.op`)

| `op` |
|------|
| `eq` |
| `ne` |
| `gt` |
| `gte` |
| `lt` |
| `lte` |
| `in` |
| `nin` |

### `orderBy` targets (sortable catalog column types)

| `DataType` |
|------------|
| `Int16` |
| `Int32` |
| `Int64` |
| `UInt16` |
| `UInt32` |
| `UInt64` |
| `Double` |
| `Decimal` |
| `Timestamp` |
| `Date` |
| `String` |

### Named-query subscribe restrictions

| Feature |
|---------|
| `joins` |
| `selectExpr` |
| `distinct` |
| `offset` |

### Data-plane route allowlist

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe |
| `GET` | `/startup` | Startup probe |
| `GET` | `/api/databases/{db}/auth/.well-known/openid-configuration` | OIDC discovery |
| `GET` | `/api/databases/{db}/auth/.well-known/jwks.json` | JWKS |
| `*` | `/api/databases/{db}/auth` | App-auth root; any HTTP method |
| `*` | `/api/databases/{db}/auth/*` | App auth except /auth/admin and /auth/admin/*; any HTTP method |
| `POST` | `/api/databases/{db}/named-queries/{hash}/query` | Named-query execute |
| `POST` | `/api/databases/{db}/named-queries/batch` | Named-query batch |
| `POST` | `/api/databases/{db}/named-mutations/{hash}/execute` | Named-mutation execute |
| `*` | `/api/databases/{db}/ws` | WebSocket (subscribe by hash); method not checked |

<!-- END GENERATED BROWSER-TIER-LIMITS -->

`orderBy` takes **catalog column names** of those types. A `selectExpr` alias is not a sort key. `Bool`, `Guid`, and `Float32` are valid column types and are **not** sortable.

Subscribe refusals return `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`. HTTP execute of the same hash still works.

`POST /api/databases/{db}/query` and `POST /api/databases/{db}/query/count` are **not** on the allowlist. On the data-plane they are **404**.

---

## Partition-filter rule

**Rule.** On a partitioned table (`RequirePartitionFilter` defaults **on**, including tables created by `schema/apply` with a `partitionKey`), a query must include `eq` or `in` on **every** partition-key column. `in` lowers to OR-of-equality and **does** satisfy the guard.

**Watchlist.** `Ticker in [~30 tickers] AND Source eq 'nasdaq'` is **one** named query / **one** subscription when `Ticker` and `Source` are the partition keys. The 32-per-connection cap is not an entitlement problem for that shape.

**Does not satisfy the guard:** `nin`, ranges (`gt` / `lt` / `gte` / `lte`), `between` (which is `gte ∧ lte`), `like` (not a wire operator). A **prefix** of a composite key on a query that **reads rows** is refused — there is no prefix exception for scans.

**Directory-answerable DISTINCT** (the bounded exception): projection and predicate on partition-key columns only, at least one partition key constrained by `eq`/`in`, a complete partition directory (no `data/` residue, no `_shared/` bucket), and at most 10 000 tuples. That is the path for "which sources exist for this ticker?" It reads **no** row data. If the directory is incomplete or over cap, the result is `PARTITION_FILTER_REQUIRED` — the engine does not fall through to a scan.

Pinned by `PartitionFilterRuleTests` (engine, per operator, including the watchlist `in`+`eq` shape) and `PartitionFilterRuleDataPlaneTests` (named query HTTP + subscribe on the data-plane with `mk_pub_*`).

**Why.** The guard is an access gate, not a pruner. Segment discovery is not partition-pruned, so a prefix on a row scan is `crossPartitionAccess` by another name.

**Instead of a prefix on a row query:** enumerate the free key with directory-answerable DISTINCT, then pass it as an `in` parameter; or auth-db-pls fan-out; or an MQ keyed the other way.

---

## No `crossPartitionAccess` on a named query

**Rule.** `crossPartitionAccess` is not a named-query field. The binder never sets it. Browser-tier credentials cannot reach the flag: data-plane `/query` and `/query/count` are 404; `mk_pub_*` on the admin listener is 401; ad-hoc WS `target` subscribe is `NAMED_QUERY_SUBSCRIBE_REQUIRED`.

**Why.** A definition that granted an unbounded scan would not be reviewable at persist time (`D-20`). On PLS tables the flag is `db_admin` only. On non-PLS partitioned tables it is a **cost guard on the admin tier**, not a confidentiality boundary — and it is unreachable from the browser.

**Instead:** auth-db-pls fan-out (the server injects the caller's grants); an aggregate / latest-per-key MQ over the universe with `dataPlaneAccess: true`; or `in` covering every partition key.

Admin analytics still use `.WithCrossPartitionAccess()` / `crossPartitionAccess: true` on the **admin** listener. That is not a browser-tier recipe.

---

## No parameter in identifier position

**Rule.** Table, column, operator, sort direction, and function names are fixed at definition time (`D-3`). `{ "op": { "param": "cmp" } }` fails apply (`NAMED_QUERY_IDENTIFIER_PARAM`).

**Why.** The hash is reviewable and the cost is boundable only if identifiers are static.

**Instead:** one definition per shape (new hash). Bounded sort choice (pick by index over a declared list) is S06 and is **not** shipped yet.

---

## No `groupBy` / ad-hoc aggregates on the data plane

**Rule.** A named query is a parameterized `QueryMessage`. There is no `groupBy` field on that template. `.Aggregate(...)` on the fluent client is an **engine / admin** API.

**Why.** Unbounded cost. Pre-aggregation belongs on a materialized query (`D-24`).

**Instead:** an `aggregate` MQ whose public columns are the declared `outputName`s, then a named query over that result table. For a **count of matches** on a paged list, set `count: true` on the named query and read `totalMatches` (see below) — that is a count, not a `groupBy` DSL.

---

## Optional predicates are not conditional yet

**Rule.** An omitted optional param becomes `Value = null`. For `eq`/`ne` that is `IS NULL`. For `gt`/`lt`/`in` it **throws**. There is no "match all" sentinel and no `whenParamPresent` (S06).

**Why.** Existing definitions that use optional params mean IS NULL today. Changing that without a marker would change hashes' meaning.

**Instead:** send the full `in` list on every request, or ship one definition per facet combination.

---

## No expression `orderBy`

**Rule.** `orderBy` is catalog column names of sortable types (table above). Sorting runs before computed projection, so a `selectExpr` alias cannot be a sort key. Expression `orderBy` is S07 (spike).

**Why.** Pipeline order, not a missing function name.

**Instead:** a stored [`derived`](insert-transforms.md#derived-columns) column — write-time, physically stored, therefore a catalog column and **orderable**. Prefer this for anything you need to ship before S07.

---

## `selectExpr` result types are `Unknown`

**Rule.** Computed columns report `"Unknown"`, nullable (S08 will infer where the expression permits).

**Instead:** stored `derived` columns, which have a declared type.

A definition using `selectExpr` also cannot be subscribed (table above). HTTP execute still works.

---

## `conflate` is a no-op on insert-only streams

**Rule.** Default conflation holds only a value `update` visible **before and after**. `insert`, `delete`, enter-scope, and leave-scope flush immediately (`D-15`). On an append-only tick table, default `conflate` (no `collapse_inserts`) reduces the event rate by **zero** and `values_skipped` never fires. The subscribe still registers; `snapshot_complete` includes a `CONFLATE_NOOP` warning when the conflate key is not the table PK.

**Why.** A client that misses an enter- or leave-scope event has a permanently wrong grid. That rule is not relaxed.

**Instead:**

- Set `collapse_inserts: true` on the same `conflate` object. Matching inserts are held latest-wins per declared key; delivered `op` stays `"insert"`; `values_skipped` counts collapsed inserts. Transitions still flush.
- Or declare a `latestPerKey` materialized query (no imperative HTTP create) with `dataPlaneAccess: true`, and subscribe to a named query over that result table. Upserts carry `prev`, so a pinned-predicate subscribe conflates without `collapse_inserts`.

Do not point a 10 Hz last-price grid at an insert-only table plus default `conflate` and expect throttling.

---

## `topNPerGroup` / `firstPerKey` are not implemented

**Rule.** Valid declarable MQ types: `latestPerKey`, `aggregate`, `filter`. `firstPerKey` and `topNPerGroup` are rejected at schema apply; HTTP create returns **501**. `TopNPerGroup` has no maintainer.

**Instead:** `latestPerKey` for current value; `aggregate` for OHLC / rollups.

---

## `schema diff --access` is C# CLI only (BL-176)

**Rule.** The access-surface CI gate (`aouda schema diff --access`) exists on the **.NET** CLI and as `POST …/schema/diff?access=true` on the **admin** listener. `npx @aouda/client schema diff --access` is **not shipped**.

**Why.** The computation lives in the engine. The TypeScript CLI has `diff` / `apply` / `export` without `--access`.

**Instead:** `dotnet tool install --global Aouda.Cli` in CI (any pipeline that already restores `Aouda.*` from the aoudadb feed), or the admin HTTP call. Do not skip the gate because the TS CLI cannot run it. See [Access-surface diff](access-surface.md#ci-gate).

---

## What you can do

These are true on the current train (P40 S01 / S02 / S05). They were missing from docs, not from the engine.

| Capability | How |
|---|---|
| Watchlist `in` on a partition key | `Ticker in $tickers AND Source eq $source` — one hash, one subscribe |
| `latestPerKey` without an imperative create | `materializedQueries` map, `type: "latestPerKey"` |
| Browser-tier read of an MQ result table | `"dataPlaneAccess": true` on the **MQ entry** (default `false`). No table-options PATCH |
| Candle columns named `high` / `open` | Aggregate MQ public shape is `outputName` on every read path (`D-31`) |
| Distinct source list, sub-millisecond | `distinct: true` over partition-key columns meeting the directory-answerable conditions. When it hits, `stats.distinctServedFromPartitionMetadata` is `true` (omitted when false) |
| Paging | `limit` (required cap) + `limitParam` / `offsetParam` (param names; still need a numeric cap). Non-zero offset **disqualifies subscribe** |
| "1–25 of 412" | `"count": true` on the definition → `totalMatches` on HTTP (omitted when false) and `total_matches` on `snapshot_complete`. Unbounded count fails apply (`NAMED_QUERY_COUNT_UNBOUNDED`). Ad-hoc `/query/count` stays 404 on the data plane |

---

## BL-146 — ColdPreferred `rowCount: 0` after partitioned bulk

**Fixed in 0.1.5** (2026-08-10). Not an open engine item. If a pre-0.1.5 database still shows `rowCount: 0` on the base table after partitioned historical bulk into `ColdPreferred` while MQs have data, run `AoudaEngine.SealOrphanedDeltaSegmentsAsync` — it is a recovery, not a temperature change. See [Hot/cold](hot-cold.md#bl-146--coldpreferred-rowcount-0-after-partitioned-bulk).
