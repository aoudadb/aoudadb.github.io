---
title: "Market Data and Stock Quotes"
nav_order: 21
parent: "Guides"
---

# Market Data and Stock Quotes

Document status: Approved baseline  
Primary owner: Aouda maintainers  
Last updated: 2026-06-04

This guide walks through a complete financial market-data workload on Aouda: quote ticks, OHLC candles, time-series partitioning, and per-ticker security. It is written for teams building apps like **Derive** (multi-source stock quotes) but applies to any tick stream where you need fast latest reads, interval candles, and tenant-scoped access.

**Related guides (read these for depth):**

- [Time-series and Clustering](time-series.md) — partition functions, `clusterOrder`, sort-on-seal, delta segments
- [Partitioning and Multi-tenancy](partitioning.md) — partition filters, cross-partition opt-in, storage modes
- [Materialized Queries](materialized.md) — MQ lifecycle, incremental maintenance, result-table queries
- [Auth — Data Authorization](../auth/authorization.md) — `jwt-claim`, `auth-db-pls`, fan-out queries

---

## 1. Schema design

### Quote ticks: Bid and Ask as columns

Store **Bid** and **Ask** as separate nullable `Decimal` columns on a single quote table. Do **not** use a `price_type` partition key to distinguish bid from ask — that forces two partition trees for the same instrument and complicates candle aggregation.

```json
{
  "name": "quotes",
  "columns": [
    { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
    { "name": "ticker", "type": "String", "partitionKeyOrder": 1 },
    { "name": "source", "type": "String", "partitionKeyOrder": 2 },
    { "name": "time", "type": "Timestamp", "clusterOrder": 1 },
    { "name": "bid", "type": "Decimal", "nullable": true },
    { "name": "ask", "type": "Decimal", "nullable": true }
  ],
  "partitionStorage": "Auto"
}
```

**Why nullable Decimal?** Feeds often send bid-only or ask-only updates. Nullable columns let you insert partial quotes without sentinel values.

**Why `Timestamp` for time?** Aouda stores timestamps as Int64 epoch milliseconds internally. Clustering and MQ time buckets operate on the same representation.

### Trades table for Last price

**Last** (trade price) comes from a different event stream than bid/ask quotes. Use a separate `trades` table rather than overloading the quote schema:

```json
{
  "name": "trades",
  "columns": [
    { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
    { "name": "ticker", "type": "String", "partitionKeyOrder": 1 },
    { "name": "source", "type": "String", "partitionKeyOrder": 2 },
    { "name": "time", "type": "Timestamp", "clusterOrder": 1 },
    { "name": "price", "type": "Decimal" },
    { "name": "size", "type": "Int64" }
  ]
}
```

Build **Last** candles from `trades` with the same Aggregate MQ pattern as bid/ask OHLC (see §4).

---

## 2. Partitioning strategy

Composite partition key: **`ticker` + `source`**. Each `(ticker, source)` pair is an independent partition — ideal for PLS (one user sees `AAPL/nasdaq`, another sees `AAPL/oslo_bors`).

### Option A — Ticker + source, cluster by time (recommended default)

- Partition keys: `ticker`, `source`
- Cluster column: `time` (`clusterOrder: 1`)
- No partition function on `time`

**Best for:** High-cardinality tick streams where each symbol/source pair gets its own directory tree and range queries on `time` prune segments via cluster metadata.

```
partitions/
  AAPL/
    nasdaq/
      data/...
  MSFT/
    nasdaq/
      data/...
```

### Option B — Add `TruncateToDay` on time (third partition key)

Add `time` as partition key order 3 with `partitionFunction: "TruncateToDay"`.

**Best for:** Very large single-ticker histories where day-level directory boundaries help retention, archival, or per-day compaction. Trade-off: more partition directories and you must include the day key (or use cross-partition access) in queries.

```json
{
  "name": "time",
  "type": "Timestamp",
  "partitionKeyOrder": 3,
  "partitionFunction": "TruncateToDay",
  "clusterOrder": 1
}
```

Partition directory names use human-readable day strings (for example `2026-06-03`). **Do not confuse this with MQ candle bucket values** — candle result tables store buckets as **Int64 epoch milliseconds** (§4).

| Strategy | Partition keys | When to use |
|----------|----------------|-------------|
| **Option A** | `ticker`, `source` | Default; simpler queries; one partition per symbol/source |
| **Option B** | `ticker`, `source`, `TruncateToDay(time)` | Huge per-symbol history; day-scoped lifecycle ops |

See [Partitioning and Multi-tenancy](partitioning.md) for `Auto` / `Dedicated` / `Shared` storage modes and auto-promotion.

---

## 3. Time clustering and query pruning

With `clusterOrder` on `time`:

1. **Sort-on-seal** (default) orders rows within segments by `time` at flush — no full-table sort.
2. **Segment manifests** record min/max `time` per segment.
3. **Range queries** on `time` skip segments outside the predicate window.

Example — latest quotes for one symbol today (.NET):

```csharp
var todayStart = DateTimeOffset.UtcNow.Date.ToUnixTimeMilliseconds();

var rows = await client
    .GetTable("quotes")
    .Where("ticker", "eq", "AAPL")
    .Where("source", "eq", "nasdaq")
    .Where("time", "gte", todayStart)
    .OrderBy("time", descending: true)
    .Limit(100)
    .ToListAsync();
```

Always filter on **all partition key columns** unless you explicitly opt into cross-partition access (§5).

---

## 4. OHLC candle materialized queries

Aouda maintains live candle tables with **Aggregate materialized queries**. Each candle row is keyed by `(ticker, time_bucket)` with **Open / High / Low / Close** computed incrementally as ticks arrive.

### Capabilities used

| Function | MQ aggregate | Candle field |
|----------|--------------|--------------|
| `first` | Ordered by `time` | **Open** |
| `last` | Ordered by `time` | **Close** |
| `max` | On price column | **High** |
| `min` | On price column | **Low** |

**Derived time buckets:** `groupByColumns` accepts expressions like `{ "column": "time", "function": "truncateToHour" }`. The result table stores the bucket as **`Int64` epoch milliseconds** (start of the UTC hour/day/minute), not a formatted string. This keeps candle tables first-class time-series tables you can range-query and re-partition.

Supported truncation functions for buckets: `truncateToDay`, `truncateToHour`, `truncateToMinute`, plus week/month/year for longer intervals.

### Hourly bid OHLC (.NET)

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

After ticks are inserted into `quotes`, query the result table directly:

```csharp
var candles = await engine.QueryMaterializedAsync("candles_bid_1h");
```

### Day and minute intervals

Use the same pattern; change only the truncation function:

| Candle table | `function` value |
|--------------|------------------|
| Daily | `truncateToDay` |
| Hourly | `truncateToHour` |
| Minute | `truncateToMinute` |

Example names: `candles_bid_1d`, `candles_bid_1h`, `candles_bid_1m`. Create separate MQs for **ask** side (`Aggregate.*("ask", ...)`) or run both bid and ask OHLC in one MQ with distinct output names (`bid_open`, `ask_open`, …).

### HTTP — create hourly candle MQ

```http
POST /api/databases/finance/materialized-queries
Content-Type: application/json
Authorization: Bearer <admin-token>

{
  "name": "candles_bid_1h",
  "sourceTable": "quotes",
  "type": 3,
  "configJson": "{\"version\":2,\"groupByColumns\":[{\"column\":\"ticker\"},{\"column\":\"time\",\"function\":\"truncateToHour\"}],\"aggregates\":[{\"outputName\":\"high\",\"function\":\"max\",\"sourceColumn\":\"bid\"},{\"outputName\":\"low\",\"function\":\"min\",\"sourceColumn\":\"bid\"},{\"outputName\":\"open\",\"function\":\"first\",\"sourceColumn\":\"bid\",\"orderByColumn\":\"time\"},{\"outputName\":\"close\",\"function\":\"last\",\"sourceColumn\":\"bid\",\"orderByColumn\":\"time\"}]}"
}
```

`type: 3` is Aggregate. Check status with `GET /api/databases/finance/materialized-queries/candles_bid_1h` until `state` is `1` (Ready).

### TypeScript — create and query

```typescript
import { createAoudaClient, MaterializedQueryType } from "@aouda/client";

const client = createAoudaClient({ serverUrl: "http://localhost:5433", database: "finance" });

await client.materializedQueries.create({
  name: "candles_bid_1h",
  sourceTable: "quotes",
  type: MaterializedQueryType.Aggregate,
  config: {
    version: 2,
    groupByColumns: [
      { column: "ticker" },
      { column: "time", function: "truncateToHour" },
    ],
    aggregates: [
      { outputName: "high", function: "max", sourceColumn: "bid" },
      { outputName: "low", function: "min", sourceColumn: "bid" },
      { outputName: "open", function: "first", sourceColumn: "bid", orderByColumn: "time" },
      { outputName: "close", function: "last", sourceColumn: "bid", orderByColumn: "time" },
    ],
  },
});

const rows = await client.table("candles_bid_1h")
  .where("ticker", "=", "AAPL")
  .execute();
```

Subscribe to live candle updates via the normal table streaming path: `client.table("candles_bid_1h").subscribe({ ... })`. See [Materialized Queries](materialized.md) §2.12 Scenario 3.

### Incremental correctness

When a new tick arrives with an **earlier** timestamp than the current Open, the `first` aggregate updates. `last` updates when a later tick arrives. `min`/`max` follow standard incremental semantics. Result tables use `HotOnly` temperature by default for fast reads.

---

## 5. Query patterns

### Latest-day quotes (single partition)

Filter all partition keys plus a time range — the normal safe path:

```typescript
const startOfDay = Date.UTC(2026, 5, 3); // 2026-06-03 UTC

await client.table("quotes")
  .where("ticker", "=", "AAPL")
  .where("source", "=", "nasdaq")
  .where("time", ">=", startOfDay)
  .orderBy("time", "desc")
  .limit(50)
  .execute();
```

### Cross-partition analytics (admin / batch)

Partitioned tables **require** full partition-key equality filters by default. For analytics across many tickers or sources, opt in explicitly:

**.NET**

```csharp
await client.GetTable("quotes")
    .WithCrossPartitionAccess()
    .Where("time", "gte", startOfDay)
    .Aggregate("ticker", "count")
    .ToListAsync();
```

**TypeScript**

```typescript
await client.table("quotes")
  .withCrossPartitionAccess()
  .where("time", ">=", startOfDay)
  .execute();
```

**HTTP**

```json
{
  "database": "finance",
  "table": "quotes",
  "crossPartitionAccess": true,
  "where": {
    "and": [
      { "column": "time", "op": "gte", "value": 1748908800000 }
    ]
  }
}
```

Cross-partition access bypasses the partition-filter guard only. **PLS and auth-db-pls still restrict which partitions the caller may see.** Use this for authorized admin analytics, not routine app queries.

### Querying candle tables

Candle tables are normal catalog tables. Filter by `ticker` and `time` (Int64 bucket):

```http
POST /api/databases/finance/query
Content-Type: application/json

{
  "database": "finance",
  "table": "candles_bid_1h",
  "where": {
    "and": [
      { "column": "ticker", "op": "eq", "value": "AAPL" },
      { "column": "time", "op": "gte", "value": 1748959200000 }
    ]
  }
}
```

Auto-routing: a compatible query against `quotes` may be served from an MQ result table when one matches. Query `candles_bid_1h` directly when you want the pre-aggregated path.

---

## 6. Partition-level security

Market-data apps typically isolate users by **ticker** (or by data **source**). Aouda supports two common patterns.

### Pattern 1 — `jwt-claim` (single ticker per user)

Each user's JWT carries a `tenant_id` claim matching the partition key (for example ticker symbol). Enable PLS on the table:

```json
{
  "name": "quotes",
  "partitionLevelSecurity": true,
  "authMode": "jwt-claim",
  "columns": [
    { "name": "ticker", "type": "String", "partitionKeyOrder": 1 }
  ]
}
```

The server injects or validates that queries only touch the user's ticker. Ideal for **Derive**-style apps where each end user watches one symbol.

See [Auth — jwt-claim mode](../auth/authorization.md#193-mode-1-jwt-claim-default).

### Pattern 2 — `auth-db-pls` (multi-ticker watchlists)

When a user may access **many tickers** (watchlist, portfolio), store grants in the auth database and set:

```json
{
  "partitionLevelSecurity": true,
  "authMode": "auth-db-pls",
  "permissionDimension": "ticker"
}
```

Grant partitions via the admin API:

```bash
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/usr_alice/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "ticker", "partitionKey": "AAPL", "accessLevel": "read" }'
```

**Fan-out:** A query without a ticker filter automatically merges results from all granted tickers — the primary pattern for multi-symbol dashboards. Revoke access on the next request without re-issuing JWTs.

For composite keys (`ticker` + `source`), use a dimension that matches your partition model or split tables by security boundary. See [Auth — auth-db-pls](../auth/authorization.md#194-mode-2-auth-db-pls-enhanced-pls) and Use Case 3 (financial platform).

---

## 7. Storage layout on disk

### Partition directories

Under `Auto` storage, each `(ticker, source)` partition gets a dedicated path once volume thresholds are met; smaller partitions may share hashed buckets first. Column data lives in **column-per-file** segments under `data/` (ADR 0001).

### String partition keys (ticker)

Ticker values use **`String_Dict`** encoding in column files. Repeating the same ticker string millions of times per partition costs little — dictionary encoding stores one copy of `"AAPL"` per segment.

### Virtual partition key columns (optional optimization)

For partition key columns whose value is **constant within a partition directory** (for example `ticker` under `partitions/AAPL/...`), you may mark the column as a **virtual partition key** at table creation. Aouda skips writing redundant `.col` files and reconstructs the value from the partition path at read time. Old segments with physical column files remain readable.

This is a storage optimization, not required for correctness. See engine catalog flag `isVirtualPartitionKey` on partition key columns (no `partitionFunction` on virtual keys).

---

## 8. End-to-end checklist

1. Create `quotes` (and optionally `trades`) with `ticker` + `source` partition keys and `time` clustered.
2. Enable PLS (`jwt-claim` or `auth-db-pls`) before production traffic.
3. Create Aggregate MQs for `candles_bid_1d`, `candles_bid_1h`, `candles_bid_1m` (and ask/trades variants as needed).
4. App queries: partition-filtered reads for user-scoped latest quotes; query candle tables for charts.
5. Admin analytics: `withCrossPartitionAccess()` / `crossPartitionAccess: true` with rate limiting enabled on the server.

---

## 9. Bulk-loading historical data

When you use `bulk-load`, rows bypass incremental MQ maintenance by design.  
After the load commits, trigger or await a materialized-query refresh before reading candle tables.

### Recommended flow

1. Bulk-load historical `quotes` rows.
2. Wait for MQ refresh completion (automatic when not skipped, or explicit refresh call).
3. Query `candles_bid_*` tables.

### HTTP

```http
POST /api/databases/finance/materialized-queries/candles_bid_1h:refresh
Content-Type: application/json

{ "await": true }
```

Use `{ "await": false }` to schedule and continue immediately.

### .NET client

```csharp
var handle = await client.BulkLoadAsync("quotes", rows, new BulkLoadOptions
{
    // Default is Auto (refresh after commit). Set Skip for multi-step pipelines.
    PostLoadMqBehavior = ClientPostLoadMqBehavior.Auto
});

// Optional explicit refresh (useful when PostLoadMqBehavior=Skip)
await client.MaterializedQueries.RefreshAsync("candles_bid_1h", awaitCompletion: true);
```

### TypeScript client

```typescript
await client.bulkLoad("quotes", rows, {
  // default: "auto"
  postLoadMqBehavior: "auto",
});

await client.materializedQueries.refresh("candles_bid_1h", { await: true });
```

### CLI

```bash
# default: auto refresh after bulk-load commit
aouda table bulk-load quotes --file ./quotes-history.jsonl

# skip refresh now, refresh explicitly later
aouda table bulk-load quotes --file ./quotes-history.jsonl --skip-mq-refresh
aouda mq refresh candles_bid_1h --await
```

Use `--skip-mq-refresh` when you intentionally load multiple related tables first and refresh once at the end.

---

## 10. References

- MarketData-Gaps implementation: `TruncateToMinute`, FIRST/LAST aggregates, derived MQ group-by, TS cross-partition toggle
- ADRs: [0014 time-series clustering](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0014-time-series-clustering-optimization.md), [0015 materialized queries](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0015-materialized-queries.md), [0009 partitioning](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0009-partitioning-multitenancy.md)
- Engine tests: `tests/Aouda.Engine.Api.Tests/AggregateApiTests.cs` (`Engine_OhlcCandle_WithDerivedTimeBucket_ProducesCorrectCandles`)
