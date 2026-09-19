---
title: "Market Data and Stock Quotes"
nav_order: 21
parent: "Guides"
---

# Market Data and Stock Quotes

Document status: Approved baseline  
Primary owner: Aouda maintainers  
Last updated: 2026-08-21

This guide walks through a complete financial market-data workload on Aouda: quote ticks, OHLC candles, a paged screener, and real-time ranking — all from a **browser-tier caller** holding only a `mk_pub_*` key on the data-plane listener. Every recipe in §§2–8 is executable against the published conformance fixture.

**Related guides:**

- [Named queries](named-queries.md) — `whenParamPresent`, `orderByChoices`, subscribe by name
- [Browser-tier read limits](browser-tier-read-limits.md) — partition-filter rule, what you can and cannot do
- [Materialized Queries](materialized.md) — MQ lifecycle, `latestPerKey`, `aggregate`, computed outputs
- [Partitioning and Multi-tenancy](partitioning.md) — partition filters, cross-partition opt-in
- [Insert-time transforms](insert-transforms.md) — replace a quote ingest worker with `route` / derived columns
- [Division of responsibility](division-of-responsibility.md) — what stays in a workflow service

**Conformance fixture:** `examples/p40-browser-tier/` in this repo — `aouda.schema.json`, `seed.json`, `expected.json`. Run the fixture against a live engine with `POST .../schema/apply` (see §3). CI exercises it in `P40BrowserTierConformanceTests`.

---

## 1. Audience and scope

**Browser-tier caller** (this guide's primary audience): a web app or mobile client holding a public `mk_pub_*` key on the data-plane. You can:

- Execute named queries (by name) and read columnar results.
- Subscribe to named queries over WebSocket for real-time updates.
- See only tables / MQ result tables that have `dataPlaneAccess: true` in the schema.

You cannot (data-plane restrictions):

- Call `POST .../query` ad-hoc — 404 on the data-plane.
- Create tables, MQs, or named queries via HTTP.
- Use `crossPartitionAccess` — that flag is not a named-query field.
- Select internal MQ accumulator columns (`_max_bid`, `_first_open_val`, …) — `outputName` aliases are the public surface.

**Admin / operator** paths (ingest servers, Studio, workflow services) are covered in the [Admin appendix](#admin-appendix) at the end of this guide.

---

## 2. One schema file

All tables, materialized queries, and named queries for the market-data fixture live in one declarative file. Apply it once; the engine maintains all MQs automatically.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "finance",
  "tables": {
    "quotes": {
      "columns": {
        "id":     { "type": "Int64",      "primaryKey": 1 },
        "ticker": { "type": "String" },
        "source": { "type": "String" },
        "time":   { "type": "Timestamp" },
        "bid":    { "type": "Decimal", "nullable": true },
        "ask":    { "type": "Decimal", "nullable": true }
      },
      "partitionKey":   [{ "column": "ticker" }, { "column": "source" }],
      "clusterColumns": ["time"],
      "dataPlaneAccess": true
    },
    "trades": {
      "columns": {
        "id":     { "type": "Int64",   "primaryKey": 1 },
        "ticker": { "type": "String" },
        "source": { "type": "String" },
        "time":   { "type": "Timestamp" },
        "price":  { "type": "Double" },
        "size":   { "type": "Int64" }
      },
      "partitionKey":   [{ "column": "ticker" }, { "column": "source" }],
      "clusterColumns": ["time"],
      "dataPlaneAccess": true
    },
    "listings": {
      "columns": {
        "ticker":   { "type": "String", "primaryKey": 1 },
        "currency": { "type": "String" },
        "sector":   { "type": "String" },
        "country":  { "type": "String" },
        "mcap":     { "type": "Int64" }
      },
      "dataPlaneAccess": true
    }
  },
  "materializedQueries": {
    "latest_quote": {
      "type":        "latestPerKey",
      "sourceTable": "quotes",
      "groupBy":     ["ticker", "source"],
      "orderBy":     "time",
      "descending":  true,
      "select":      ["ticker", "source", "bid", "ask", "time"],
      "updateMode":  "sync",
      "dataPlaneAccess": true,
      "storage":     { "storageTemperature": "HotOnly" }
    },
    "candles_bid_1h": {
      "type":        "aggregate",
      "sourceTable": "quotes",
      "groupBy": [
        { "column": "ticker" },
        { "column": "time", "function": "TruncateToHour", "outputName": "time" }
      ],
      "aggregates": [
        { "function": "max",   "outputName": "high",  "sourceColumn": "bid" },
        { "function": "min",   "outputName": "low",   "sourceColumn": "bid" },
        { "function": "first", "outputName": "open",  "sourceColumn": "bid", "orderByColumn": "time" },
        { "function": "last",  "outputName": "close", "sourceColumn": "bid", "orderByColumn": "time" }
      ],
      "updateMode": "sync",
      "dataPlaneAccess": true,
      "storage":    { "storageTemperature": "ColdPreferred" }
    },
    "bars_with_change": {
      "type":        "aggregate",
      "sourceTable": "trades",
      "groupBy":     [{ "column": "ticker" }],
      "aggregates": [
        { "function": "first", "outputName": "open",  "sourceColumn": "price", "orderByColumn": "time" },
        { "function": "last",  "outputName": "close", "sourceColumn": "price", "orderByColumn": "time" }
      ],
      "computed": [
        {
          "outputName": "changePct",
          "type": "Double",
          "expr": {
            "type": "arithmetic", "op": "/",
            "left":  { "type": "arithmetic", "op": "-",
                       "left":  { "type": "colRef", "col": "close" },
                       "right": { "type": "colRef", "col": "open" } },
            "right": { "type": "colRef", "col": "open" }
          }
        }
      ],
      "updateMode": "sync",
      "dataPlaneAccess": true,
      "storage":    { "storageTemperature": "HotOnly" }
    }
  },
  "namedQueries": {
    "quotes.watchlist": {
      "table":  "quotes",
      "select": ["ticker", "source", "time", "bid", "ask"],
      "where": {
        "and": [
          { "column": "ticker", "op": "in",  "param": "tickers" },
          { "column": "source", "op": "eq",  "param": "source"  }
        ]
      },
      "orderBy": [{ "column": "time", "descending": true }],
      "limit": 100,
      "count": true,
      "params": {
        "tickers": { "required": true, "maxItems": 64 },
        "source":  { "required": true, "maxLength": 32 }
      }
    },
    "quotes.lastPrice": {
      "table":  "latest_quote",
      "select": ["ticker", "source", "bid", "ask", "time"],
      "where": {
        "and": [
          { "column": "ticker", "op": "in", "param": "tickers" },
          { "column": "source", "op": "eq", "param": "source"  }
        ]
      },
      "limit": 32,
      "params": {
        "tickers": { "required": true, "maxItems": 64 },
        "source":  { "required": true, "maxLength": 32 }
      }
    },
    "candles.byTicker": {
      "table":  "candles_bid_1h",
      "select": ["ticker", "time", "open", "high", "low", "close"],
      "where": {
        "and": [
          { "column": "ticker", "op": "eq", "param": "ticker" }
        ]
      },
      "orderBy": [{ "column": "time", "descending": false }],
      "limit": 500,
      "params": {
        "ticker": { "required": true, "maxLength": 16 }
      }
    },
    "listings.screener": {
      "table":  "listings",
      "select": ["ticker", "currency", "sector", "country", "mcap"],
      "where": {
        "and": [
          { "column": "currency", "op": "in",  "param": "currency",  "whenParamPresent": true },
          { "column": "sector",   "op": "eq",  "param": "sector",    "whenParamPresent": true },
          { "column": "mcap",     "op": "gte", "param": "minMcap",   "whenParamPresent": true },
          { "column": "country",  "op": "eq",  "param": "country",   "whenParamPresent": true }
        ]
      },
      "orderBy": [{ "column": "ticker", "descending": false }],
      "limit":       25,
      "limitParam":  "pageSize",
      "offset":      1000,
      "offsetParam": "pageOffset",
      "count": true,
      "params": {
        "currency":   { "required": false },
        "sector":     { "required": false, "maxLength": 64 },
        "minMcap":    { "required": false },
        "country":    { "required": false, "maxLength": 8 },
        "pageSize":   { "required": false, "min": 1, "max": 25 },
        "pageOffset": { "required": false, "min": 0, "max": 1000 }
      }
    },
    "gainers.top": {
      "table":  "bars_with_change",
      "select": ["ticker", "open", "close", "changePct"],
      "orderBy": [{ "column": "changePct", "descending": true }],
      "orderByChoices": [
        [{ "column": "changePct", "descending": true  }],
        [{ "column": "ticker",    "descending": false }]
      ],
      "limit": 20,
      "params": {}
    }
  }
}
```

Key design decisions:

- **`bid`/`ask` as columns** — not a `price_type` partition key. One partition tree per `(ticker, source)` pair; simpler candle aggregation.
- **`listings` is unpartitioned** — `count: true` + optional facets (`whenParamPresent`) is legal only on tables where every predicate covers the partition key or the table has no partition key. An unpartitioned reference table is the right shape for a screener.
- **`dataPlaneAccess: true` on every MQ** — a missing flag means `POST .../named-queries/{name}/query` returns 404 on the data-plane. The schema file is the only place to set it; there is no table-options PATCH on the data-plane.

---

## 3. Apply, then ingest

Schema and data are separate steps. Schema objects enter only via `schema/apply`. Data enters via `POST .../rows`.

### Apply the schema

```http
POST /api/databases/finance/schema/apply
Content-Type: application/json
Authorization: Bearer <service-key>

{
  "schema": { ... },
  "options": { "allowDestructive": false, "dryRun": false }
}
```

One apply creates all three tables, all three MQs, and all five named queries in the right order (MQs at priority 8, named queries at priority 9 — so an NQ over an MQ result table applies in the same request).

### Ingest seed rows

```http
POST /api/databases/finance/tables/quotes/rows
Content-Type: application/json
Authorization: Bearer <service-key>

{
  "database": "finance",
  "table": "quotes",
  "rows": [
    { "id": 1, "ticker": "AAPL", "source": "nasdaq", "time": "2023-11-15T10:00:00Z", "bid": 150.0, "ask": 150.5 }
  ]
}
```

MQs with `updateMode: "sync"` update before each insert returns. For bulk loads, `updateMode: "async"` + an explicit refresh call after the load completes is more efficient (see [§11 — Bulk loading historical data](#bulk-loading-historical-data)).

---

## 4. Watchlist

`quotes.watchlist` accepts a list of tickers (`in`) and a required source (`eq`). Both predicates cover the composite partition key — the partition-filter rule is satisfied with one named query and one subscribe.

```json
{
  "args": {
    "tickers": ["AAPL", "MSFT"],
    "source": "nasdaq"
  }
}
```

**Execute (HTTP):**

```http
POST /api/databases/finance/named-queries/quotes.watchlist/query
Content-Type: application/json
Authorization: Bearer <mk_pub_key>

{ "args": { "tickers": ["AAPL", "MSFT"], "source": "nasdaq" } }
```

Response includes `totalMatches` (from `count: true`), `columns`, `rowCount`, and columnar `data`.

**Subscribe (WebSocket):**

```json
{ "type": "subscribe", "id": "wl", "name": "quotes.watchlist",
  "args": { "tickers": ["AAPL", "MSFT"], "source": "nasdaq" } }
```

The server sends snapshot rows then a `snapshot_complete` message, followed by incremental `change` events on tick inserts.

{: .note }
A prefix of the composite partition key is not sufficient. `ticker in ["AAPL"]` alone — without `source eq "nasdaq"` — is refused on the data-plane with a partition-filter error. Both columns must be covered. See [browser-tier read limits — partition filter rule](browser-tier-read-limits.md#partition-filter-rule).

---

## 5. Latest price that throttles

Default `conflate` does not throttle an insert-only tick table. When new ticks are inserted (not upserted), the conflict key is never matched — `CONFLATE_NOOP` on every tick. Two patterns provide real throttling:

### Pattern A — `latestPerKey` MQ + named-query subscribe (recommended)

Declare a `latestPerKey` MQ over `quotes`. The MQ maintains one row per `(ticker, source)` pair and emits `prev`/`next` on each upsert. Default `conflate` fires on the upsert event (not the raw tick), so the subscriber sees at most one update per new price, regardless of tick rate.

```json
"latest_quote": {
  "type":        "latestPerKey",
  "sourceTable": "quotes",
  "groupBy":     ["ticker", "source"],
  "orderBy":     "time",
  "descending":  true,
  "select":      ["ticker", "source", "bid", "ask", "time"],
  "updateMode":  "sync",
  "dataPlaneAccess": true
}
```

The named query `quotes.lastPrice` reads `latest_quote` by the same partition predicates. Subscribe to it for a conflated real-time price feed. The snapshot columns are public names (`bid`, `ask`, `time`) — not accumulator state names from the MQ internals.

### Pattern B — Insert-only ticks + `collapse_inserts: true`

When you cannot change to an MQ (legacy schema, or you specifically want raw ticks stored), opt in on the subscribe call:

```json
{
  "type": "subscribe", "id": "lp", "name": "quotes.lastPrice",
  "args": { "tickers": ["AAPL"], "source": "nasdaq" },
  "conflate": { "collapse_inserts": true }
}
```

With `collapse_inserts: true`, the server collapses multiple in-flight tick inserts into a single notification. Without it, default `conflate` on an insert-only table is a no-op. See [browser-tier read limits — conflate is a no-op on insert-only streams](browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

{: .warning }
Do **not** rely on default `conflate` (no `collapse_inserts`) for last-price on an insert-only tick table. Each tick insert will deliver its own notification.

---

## 6. Candle chart

Query or subscribe to `candles.byTicker` — a named query over the `candles_bid_1h` MQ result table. Columns are the declared `outputName`s (`open`, `high`, `low`, `close`). Internal accumulator names (`_max_bid`, `_first_open_val`) are not selectable and not exposed on the data-plane.

**Execute:**

```http
POST /api/databases/finance/named-queries/candles.byTicker/query
Content-Type: application/json
Authorization: Bearer <mk_pub_key>

{ "args": { "ticker": "AAPL" } }
```

Response columns: `["ticker", "time", "open", "high", "low", "close"]`. The `time` column contains the UTC **epoch-millisecond** start of each hour bucket — an Int64, not a formatted string. Candles are ordered ascending by time (as defined in the NQ).

{: .important }
**Ad-hoc `POST .../query` is 404 on the data-plane.** All browser-tier access goes through named-query names. Both the MQ (`candles_bid_1h`) and the named query (`candles.byTicker`) must be declared in the schema file; `dataPlaneAccess: true` must appear on the MQ entry, not patched in via table-options HTTP.

### Day and minute intervals

Add separate MQs:

```json
"candles_bid_1d": {
  "type": "aggregate",
  "sourceTable": "quotes",
  "groupBy": [
    { "column": "ticker" },
    { "column": "time", "function": "TruncateToDay", "outputName": "time" }
  ],
  "aggregates": [ ... ],
  "dataPlaneAccess": true,
  "storage": { "storageTemperature": "ColdPreferred" }
}
```

And separate named queries `candles.byTickerDay`, `candles.byTickerMinute`. Same select shape — only the MQ name and truncation function differ.

{: .warning }
**A minute-interval candle MQ is the one to think hardest about.** One row per `(ticker, minute)` is
1 440 rows per ticker per day — over 5 000 tickers, **7.2 million rows a day**, growing without
bound. Decide where that result table lives before deploying one: see the next section.

---

## Where each MQ result lives — RAM or disk {#mq-residency}

Every materialized query in this schema produces a **result table**, and a result table is an
ordinary table: it sits in the same hot tier, obeys the same `storageTemperature`, and is charged
against the same memory ceiling as `quotes` and `trades`. The `storage` lines in
[section 2](#2-one-schema-file) are not decoration — they are the difference between a market-data
database that fits on a 2 GB host and one that does not.

### The default is `Auto`, and for market data that is rarely the best answer

With no `storage` block a result table defaults to **`Auto`** — hot while the tier has room, cold
when it does not — for every query type. Residency is policy, not something inferred from whether
the query is a `latestPerKey` or an `aggregate`.

That is a safe default and a weak one here, because market-data results split cleanly into two very
different shapes. An `aggregate` keyed by a **time bucket** holds one row per group and grows
forever: a per-minute candle over a few thousand instruments is millions of groups within a day. A
`latestPerKey` keyed by **identity** holds one row per instrument and stops growing.

⚠️ **Declaring `HotOnly` is a charge, not a hint.** A pinned table's bytes are subtracted from the
ceiling everything else is admitted against, the table is skipped for demotion, and its cold segments
are re-promoted. Pin the candle series and you shrink the tier your *tick ingest* is admitted into —
and the symptom is a `503` on an `insert into quotes`, not on the candle table.

### What to declare, per query in this schema

| Query | Shape | Declare | Why |
|---|---|---|---|
| `latest_quote` | One row per `(ticker, source)` — bounded by your instrument count, read on every page load | **`HotOnly`** | A few thousand rows that back a live price feed. This is what a pin is *for*: small, hot, and now declared rather than assumed. |
| `candles_bid_1h` | One row per `(ticker, hour)` — grows forever | **`ColdPreferred`** | Historical and append-shaped. The recent end is served from the page cache; nothing needs the whole series resident. |
| `candles_bid_1d` | One row per `(ticker, day)` — grows forever, 24× slower | **`ColdPreferred`** | Same reasoning. Small enough that `Auto` is also defensible. |
| `candles_bid_1m` | One row per `(ticker, minute)` — millions per day | **`ColdPreferred`** | The one that will hurt. See the warning above. |
| `bars_with_change` | One row per ticker, current session | **`HotOnly`** | Bounded by instrument count and read by every screener call. |

🔎 **The rule of thumb: does the group key contain a time bucket?** If it does, the result grows
without bound and belongs on disk — `ColdPreferred`. If the group key is pure identity (ticker, user,
account), the result is bounded by your entity count and a pin is honest.

### Keeping the recent window hot without pinning the history

If you do want the last N candles resident — a chart that reloads constantly — use `Auto` plus a
**row cap** on the result table rather than a pin. The cap is set on the result table (the result
table's name is the query's name), not in the schema file:

```http
PUT /api/databases/finance/tables/candles_bid_1m/policy
Content-Type: application/json

{
  "storageTemperature": "Auto",
  "memoryRowCap": 50000
}
```

The hot/cold sweep demotes least-recently-accessed segments first, so the cap self-scales: you do not
have to know your tick rate, and the same number works for a 1 ms feed and a 1-minute candle.

🔎 **What makes the cap mean what you want is the ordering underneath.** A time-bucketed result
table is clustered by its leading time bucket, so "demote the least recently used segment" amounts
to "demote the oldest candles". Without that ordering one still-updating current-minute row would
keep its whole segment resident, buckets from months ago included.

⚠️ **A row cap does not survive a destructive schema replace.** Changing an MQ's definition at the
same name is a drop-then-create, and the new result table starts with default policy. `storage` in
the schema file *is* carried; a policy you set over HTTP is not.

🔎 **Why a row count and not "keep 24 hours".** A duration cannot be honoured without knowing the
arrival rate — at a busy feed's byte rate, "24 hours" can be over 100 GB, which would have to be
refused when you declared it. A count needs no such input.

### Checking what you actually have

```http
GET /api/server/memory
```

- **`pinnedHotBytes`** (per database) — bytes held by declared residency pins, including any
  result table you declared `HotOnly`. This is what your pins are costing the elastic tier.
- **`hotArrivalBytesPerSecond` vs `hotDrainBytesPerSecond`** — the gap, not either number, says
  whether the tier is filling faster than it empties.
- **`processHotCeilingBytes` / `processHotResidentBytes`** — the process-wide bound. A refusal while
  your own database's share still had room is read here.

Per query, `GET /api/databases/finance/materialized-queries/{name}` carries an `amplification` object
with `writeAmplification` (result rows written per source row ingested) and `readAmplification`. A
candle query whose `writeAmplification` sits well above `1.0` has a bucket too fine for its arrival
rate.

Full treatment: [Materialized queries §2.3.1](materialized.md#where-a-materialized-querys-result-lives)
and [Sizing](sizing.md#mq-result-residency).

---

## 7. Paged screener

`listings.screener` demonstrates the full optional-predicate + pagination pattern. It sits on the unpartitioned `listings` table so `count: true` is legal without required partition predicates.

**Four optional facets — one definition:**

```json
"where": {
  "and": [
    { "column": "currency", "op": "in",  "param": "currency",  "whenParamPresent": true },
    { "column": "sector",   "op": "eq",  "param": "sector",    "whenParamPresent": true },
    { "column": "mcap",     "op": "gte", "param": "minMcap",   "whenParamPresent": true },
    { "column": "country",  "op": "eq",  "param": "country",   "whenParamPresent": true }
  ]
}
```

`whenParamPresent: true` means: if the caller omits this arg, skip the predicate entirely. If the arg is supplied, apply it. An **unmarked** (`whenParamPresent` absent) required omission still throws `NAMED_QUERY_PARAM_REQUIRED`. A marked condition never counts as partition-key coverage for `count: true`.

**Execute with no filter (all listings, page 0):**

```json
{ "args": { "pageOffset": 0 } }
```

Response: `rowCount: 5`, `totalMatches: 5`.

**Execute with two facets:**

```json
{ "args": { "currency": ["USD"], "sector": "Tech", "pageOffset": 0 } }
```

Response: `rowCount: 3`, `totalMatches: 3`.

**Pagination:** `limitParam: "pageSize"` lets the caller override the limit (up to 25). `offsetParam: "pageOffset"` lets the caller skip rows (up to 1000). Omitting `pageOffset` (or sending null) binds skip **0** — first page. You do not have to send `0` to avoid an empty page; the cap is a maximum skip, not the default.

{: .note }
`count: true` on a **partitioned** table requires required `eq`/`in` on every partition-key column. A `whenParamPresent` condition never satisfies that requirement. Use an unpartitioned reference table (like `listings`) for optional-facet screeners, or require the partition key in the NQ params.

---

## 8. Top gainers

`gainers.top` selects from `bars_with_change` — an aggregate MQ over `trades` with a `computed` column:

```json
"computed": [
  {
    "outputName": "changePct",
    "type": "Double",
    "expr": {
      "type": "arithmetic", "op": "/",
      "left":  { "type": "arithmetic", "op": "-",
                 "left":  { "type": "colRef", "col": "close" },
                 "right": { "type": "colRef", "col": "open" } },
      "right": { "type": "colRef", "col": "open" }
    }
  }
]
```

The default sort is `changePct` descending. A caller can pick an alternative sort using `orderByIndex`:

**Default (changePct desc):**

```json
{ "args": {} }
```

**Alternative sort (ticker asc) — `orderByIndex: 1`:**

```json
{ "args": {}, "orderByIndex": 1 }
```

`orderByChoices` in the schema declares the allowed sort permutations (0-indexed). `orderByIndex` selects one. The engine rejects an index outside the declared list. Expression `orderBy` (arbitrary column not in `orderByChoices`) is not available on the data-plane (BL-183 — open backlog item).

{: .note }
The `derived` expression (base-table computed column) is a fallback for ranking on raw tables. `bars_with_change.changePct` uses the physical `computed` path — it is orderable and selectable as a first-class column.

---

## 9. Partition-level security

### Pattern 1 — `jwt-claim` (single ticker per user)

Each user's JWT carries a claim matching the partition key (for example ticker symbol). PLS validates or injects the filter automatically. Ideal for apps where each end user watches one symbol.

See [Auth — jwt-claim mode](../auth/authorization.md#193-mode-1-jwt-claim-default).

### Pattern 2 — `auth-db-pls` (multi-ticker watchlists)

When a user may access many tickers (watchlist, portfolio), store grants in the auth database. Fan-out: a named-query subscription automatically merges results from all granted tickers. Revoke access on the next request without re-issuing JWTs.

See [Auth — auth-db-pls](../auth/authorization.md#194-mode-2-auth-db-pls-enhanced-pls) and [Division of responsibility](division-of-responsibility.md).

---

## 10. Browser-tier checklist

| Step | Detail |
|------|--------|
| Schema file includes MQs | `materializedQueries` section in `aouda.schema.json` |
| `dataPlaneAccess: true` on every MQ the browser reads | Set in the schema file, not patched via table-options HTTP |
| Named queries select `outputName` columns | `open`, `high`, `low`, `close` — not `_max_bid` / `_first_open_val` |
| No `crossPartitionAccess` in NQ params | Not a named-query field |
| Watchlist: both partition keys required | `ticker in $tickers` + `source eq $source` (not just ticker) |
| Last-price: use `latestPerKey` MQ or `collapse_inserts` | Default `conflate` is a no-op on insert-only streams |
| Screener: `whenParamPresent` on optional facets | Unmarked optional omit throws `NAMED_QUERY_PARAM_REQUIRED` |
| Apply is the only DDL step | No `POST /tables`, no `POST /materialized-queries`, no table-options PATCH |

---

## Admin appendix

The following patterns require **admin / service-key** access on the admin listener. They are the correct path for ingest services, Studio operators, and CI pipelines — not for browser-tier app code.

### Imperative MQ creation (.NET)

```csharp
await engine.CreateAggregateQueryAsync(
    name: "candles_bid_1h",
    sourceTable: "quotes",
    groupByColumns: new GroupByExpression[]
    {
        "ticker",
        new GroupByExpression { Column = "time", Function = PartitionFunction.TruncateToHour }
    },
    aggregates: new[]
    {
        Aggregate.Max("bid", "high"),
        Aggregate.Min("bid", "low"),
        Aggregate.First("bid", "time", "open"),
        Aggregate.Last("bid", "time", "close")
    });
```

### Imperative MQ creation (HTTP)

```http
POST /api/databases/finance/materialized-queries
Content-Type: application/json
Authorization: Bearer <admin-token>

{
  "name": "candles_bid_1h",
  "sourceTable": "quotes",
  "type": 3,
  "configJson": "..."
}
```

### Cross-partition analytics (.NET — admin)

```csharp
await client.GetTable("quotes")
    .WithCrossPartitionAccess()
    .Where("time", "gte", startOfDay)
    .Aggregate("ticker", "count")
    .ToListAsync();
```

### Cross-partition analytics (TypeScript — admin listener)

```typescript
await client.table("quotes")
  .withCrossPartitionAccess()
  .where("time", ">=", startOfDay)
  .execute();
```

`.Aggregate(...)` and `.withCrossPartitionAccess()` are admin-listener APIs — not `QueryMessage` fields and not available on the data-plane.

### Ad-hoc query on a candle table (admin HTTP)

```http
POST /api/databases/finance/query
Content-Type: application/json
Authorization: Bearer <admin-token>

{
  "database": "finance",
  "table": "candles_bid_1h",
  "where": {
    "and": [
      { "column": "ticker", "op": "eq", "value": "AAPL" },
      { "column": "time",   "op": "gte", "value": 1748959200000 }
    ]
  }
}
```

### Bulk-loading historical data {#bulk-loading-historical-data}

Bulk-loaded rows bypass **incremental** MQ maintenance by design. What happens instead is decided by
`postLoadMqBehavior`, and the two settings want opposite follow-up calls.

**`auto` (the default) — accumulate during the load's own pass, publish at commit.** Wait for that
publication; **do not also call `:refresh`.** A `:refresh` queues behind the publication on the
server's per-name lock and then re-scans the whole source table, so it buys nothing and costs a
second full pass.

```csharp
var handle = await client.BulkLoadAsync("quotes", rows, new BulkLoadOptions
{
    PostLoadMqBehavior = ClientPostLoadMqBehavior.Auto   // default
});
// Wait on the load's own mqRebuildStatus / MqRebuildCompleted. No :refresh call.
```

```typescript
await client.bulkLoad("quotes", rows, { postLoadMqBehavior: "auto" });
// Poll the job's mqRebuildStatus. No refresh call.
```

**`skip` — no ingest-fed sinks and no rebuild.** Use it in a multi-step pipeline that loads several
tables and refreshes once at the end. Then, and only then, `:refresh` is the right call:

```http
POST /api/databases/finance/materialized-queries/candles_bid_1h:refresh
Content-Type: application/json

{ "await": true }
```

⚠️ **A `skip` load leaves the query durably stale until you refresh it.** It reports `isStale` with a
`staleReason`, and a server that restarts before the refresh rebuilds the query at startup rather
than reattaching an incomplete result. That is a correctness guard, not a bug — but it means a `skip`
you forgot to follow up costs a full rebuild at the next restart.

{: .note }
**Loading years of history is the case where result residency bites hardest.** A historical load of
`quotes` regenerates every candle bucket in the range at once. Under `Auto` that is a large burst of
hot admissions all at once; under a declared `HotOnly` none of it can be demoted at all. Declare
`storageTemperature: "ColdPreferred"` on historical candle MQs *before* the load, not after. See
[Where each MQ result lives](#mq-residency).

🔎 **Ordinary tabular bulk loads write cold only** and always have. It is the *materialized query
results* they feed that land hot, which is why the residency declaration is what matters here rather
than a bulk-load setting. (Graph and vector bulk loads are a separate case — those now default to
`Aouda:BulkLoad:Temperature: ColdDirect`.)

---

## References

- Conformance fixture: `examples/p40-browser-tier/` — `aouda.schema.json`, `seed.json`, `expected.json`
- ADRs: [0040 direct-client-access and trust boundary](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0040-direct-client-access-and-the-trust-boundary.md) (D-3, D-5, D-15, D-20, D-30–D-36), [0015 materialized queries](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0015-materialized-queries.md), [0009 partitioning](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0009-partitioning-multitenancy.md)
- Engine tests: `tests/Aouda.Server.Tests/P40/P40BrowserTierConformanceTests.cs`, `tests/Aouda.Server.Tests/P40/PartitionFilterRuleDataPlaneTests.cs`
- Memory and residency: [Materialized queries §2.3.1](materialized.md#where-a-materialized-querys-result-lives) (where a result lives), [§2.11d](materialized.md#amplification) (what a query costs), [Sizing](sizing.md#mq-result-residency) (the hot tier and the reclaim ladder), [Hot/Cold Storage](hot-cold.md) (per-table residency policy), [Defaults Reference](defaults-reference.md#hot-tier-and-ingest-admission) (every `Aouda:Memory:` key)
