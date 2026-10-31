---
title: "Named queries and mutations"
nav_order: 8
parent: "Guides"
---

# Named queries and mutations

Document status: Complete (BL-188 S09)  
Last updated: 2026-09-08

A **named query** is a server-authored, parameterized query template. The client sends a **name** plus arguments. It cannot name tables, columns, or operators. Identity is injected from the validated principal — it is never an argument.

That is the BFF (backend-for-frontend) **minus the deployment unit**. A gateway that only shapes, filters, projects, and authorizes reads is a catalog entry reviewed like any other schema change.

Named **mutations** are the write-side mirror (insert / update / delete templates). They run with **invoker rights only** — there is no `SECURITY DEFINER` / `runAs`.

**Wire contract:** [HTTP API — Named queries](../reference/http-api.md#named-queries) (v2.5). **Limits:** [What a browser-tier read cannot do](browser-tier-read-limits.md).

---

## Start here

| I want to… | Go to |
|---|---|
| Author a named query in `aouda.schema.json` | [Schema](#schema) |
| Call it from TypeScript, C#, or curl | [Execute](#execute) |
| Collapse independent reads into one round trip | [Batch](#batch-one-snapshot) |
| Insert many rows in one call | [Batch insert (`batchParam`)](#batch-insert-batchparam) |
| Subscribe to live results | [Subscribe by name](#subscribe-by-name) |
| Optional Args/Row types | [Types (optional codegen)](#types-optional-codegen) |
| Page with a total ("1–25 of 412") | [Paging, distinct, and count](#paging-distinct-and-count) |
| See what this surface cannot do | [Browser-tier read limits](browser-tier-read-limits.md) |
| Decide if this belongs in Aouda at all | [Division of responsibility](division-of-responsibility.md) |

<!-- #subscribe-by-hash and #pin-hashes-codegen redirected: subscribe is by name; codegen is optional types. -->

---

## Why this exists

An untrusted caller (a browser, a mobile app) must not compose an arbitrary `QueryMessage`:

1. **Cost** — a five-way join or an unfiltered scan is unbounded.
2. **Schema coupling** — the UI is welded to physical column names (the PostgREST failure).
3. **Column exposure** — ADRA is row- and partition-scoped. The named query's `select` is the only column-level control.
4. **Review** — a query that can leak a tenant is a schema change, not a string in a SPA.

Trusted callers (Studio operators, `mk_svc_*` on the **admin** listener) still have the ad-hoc query surface. Named queries are **required** on the [data-plane listener](direct-client-access.md).

### Performance: what is actually true

An extra hop inside a datacenter is sub-millisecond. **Do not adopt named queries to save that hop.**

The strong arguments:

| Argument | What it buys |
|---|---|
| **Composition** | A portfolio → positions → quotes waterfall becomes **one** named query with joins. |
| **Batch** | Independent panels (ten unrelated named queries) share **one HTTP request and one read snapshot**. |
| **Deployment** | Adding a field is a schema apply, not a redeploy of a 5 800-line gateway. |
| **Streaming** | Fan-out, gap signalling, and conflation live in the engine. A relay that copies every tick three times is pure loss **after** those features shipped. |

---

## Defaults

| Setting | Default | Notes |
|---|---|---|
| Identity of a definition | Unique name in `aouda.schema.json` | `^[A-Za-z][A-Za-z0-9_.]*$`. Same string on the wire, on disk, and in export. |
| Versioning | Explicit names | `quoteByTicker` and `quoteByTickerV2` are two entries. |
| Removal | Omit the name | Destructive `RemoveNamedQuery`. There is no `dropNamedQueries`. |
| `select` / `selectExpr` | **Required** — except beside `aggregates` | `*` is refused (`NAMED_QUERY_PROJECTION_STAR`). A definition with `aggregates` / `groupBy` answers its keys and aggregates and takes no `select` (**BL-796, 0.3.0**). |
| `aggregates` / `groupBy` / `perKey` | Optional | As on `/query`, checked at apply under its rules; subscribe refuses them ([HTTP API, named-query definition](../reference/http-api.md)) (**BL-796, BL-801, 0.3.0**). |
| `joins[i].where` | Optional | A filter on the joined table, ANDed with the caller's row security there (**BL-818, 0.3.0**). |
| `limit` | Must be capped in the definition | Uncapped `$limit` fails schema apply. |
| Parameter in identifier position | Illegal | Table, column, operator, sort, projection. |
| Identity as a parameter | Illegal | `NAMED_QUERY_IDENTITY_PARAM` at apply. |
| Persist-time cost | `1 + joinCount` | Caps: 3 joins, cost 8 (`NAMED_QUERY_TOO_MANY_JOINS` / `NAMED_QUERY_COST_EXCEEDED`). |
| Batch size | 32 | Envelope 400 if empty, over cap, or includes a mutation **name**. |
| Runtime registration | **Does not exist** | That is the GraphQL APQ trap. |
| Fail-safe freshness | Name has no `freshness` block | Primary-only + `readYourWrites`. See [Declared freshness](#declared-freshness). |

### Trade-away

Editing the body under the same name changes behaviour for every deployed frontend at apply time. That is deliberate — a consumer of "the current version" should get the current version. Coexistence, when you need it, is **two names** (`quoteByTicker` + `quoteByTickerV2`).

The mitigation is not a compatibility shim. It is a **review-time signal**: the access-surface diff reports `named_query_body_changed` (`widen`) when the body under a name changes, plus the `V2` pattern. See [Access-surface diff](access-surface.md).

---

## Declared freshness

Optional `freshness` lives on the **named query**. Budget-only edits do not fire `named_query_body_changed`. Fail-safe (primary-only + `readYourWrites`) applies when that **name** has no `freshness` block.

Call sites may **tighten** (`?maxStalenessMs=500` on a 2 s named query). Loosening is 400 `FRESHNESS_LOOSENED`. A branch that loosens a budget is `freshness` / `widen` on `aouda schema diff --access` and fails CI; a tightening is `narrow` and does not.

There is no `?alias=` / header / body `alias`. Full contract, caveats, and SDK examples: [Freshness and replica consistency](freshness.md).

---

## Schema

Named queries live in `aouda.schema.json` next to tables. They are **per-database catalog objects**. Hub does not distribute them.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "trading",
  "tables": {
    "EquityQuote": {
      "dataPlaneAccess": true,
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1 },
        "ticker": { "type": "String" },
        "bid": { "type": "Decimal", "precision": 18, "scale": 2 },
        "ask": { "type": "Decimal", "precision": 18, "scale": 2 },
        "internalSpread": { "type": "Decimal", "precision": 18, "scale": 2 },
        "asOf": { "type": "Timestamp" }
      }
    },
    "Position": {
      "dataPlaneAccess": true,
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1 },
        "accountId": { "type": "Int64" },
        "ticker": { "type": "String" },
        "qty": { "type": "Int64" }
      }
    }
  },
  "namedQueries": {
    "equity.quoteByTicker": {
      "table": "EquityQuote",
      "select": ["ticker", "bid", "ask", "asOf"],
      "limit": 1,
      "where": {
        "and": [{ "column": "ticker", "op": "eq", "param": "ticker" }]
      },
      "params": {
        "ticker": { "required": true, "maxLength": 8 }
      },
      "version": "v1"
    },
    "equity.stockOverview": {
      "table": "Position",
      "select": ["ticker", "qty", "bid", "ask"],
      "limit": 500,
      "joins": [
        {
          "table": "EquityQuote",
          "type": "inner",
          "on": { "and": [{ "column": "ticker", "op": "eq", "right": "ticker" }] }
        }
      ],
      "where": {
        "and": [{ "column": "accountId", "op": "eq", "param": "accountId" }]
      },
      "params": {
        "accountId": { "required": true }
      },
      "version": "v1"
    }
  },
  "namedMutations": {
    "equity.adjustQty": {
      "op": "update",
      "table": "Position",
      "limit": 1,
      "where": {
        "and": [
          { "column": "id", "op": "eq", "param": "id" }
        ]
      },
      "set": { "qty": { "param": "qty" } },
      "returning": ["id", "qty"],
      "params": {
        "id": { "required": true },
        "qty": { "required": true, "min": 0 }
      },
      "version": "v1"
    }
  }
}
```

Notes:

- `equity.stockOverview` does **not** select `internalSpread`. Column exposure is the projection. A later commit that adds `internalSpread` to `select` is an access-surface **widening** — [CI will fail `--access`](access-surface.md).
- Parameter types are inherited from the compared column. Declare `min` / `max` / `enum` / `maxLength` / `maxItems` / `required` on top.
- `dataPlaneAccess: true` is required for browser-tier callers on **every table the definition touches**, including join tables **and** a materialized-query result table. On an MQ, set it on the `materializedQueries` entry (default `false`) — do not PATCH table-options. Independent of ADRA: RLS/PLS still filter rows of the base table.
- **A joined table is scoped as a direct read of it would be** (**BL-818, 0.3.0**; **BL-1227, next train**). The caller's RLS and PLS for every joined table are applied on that join's side, so an execute whose definition joins a table the caller may read only part of is answered with that part, and every joined table also needs the caller's grant. A holder of `all-partitions` or `all-rows` is lifted on the joined side as on a direct read; `crossPartitionAccess` is not carried to a joined table. Still `403 AUTHORIZATION_DENIED`, naming the table: a joined table whose partition-level security refuses the caller, and a joined materialized-query result whose source security cannot be applied.

### Legal `where` operators

The `op` of a condition is an **identifier**, fixed in the definition. It is never a parameter —
`{ "op": { "param": "cmp" } }` fails apply with `NAMED_QUERY_IDENTIFIER_PARAM`. These are the values it
may take; anything else is refused at `schema/apply` with `INVALID_OPERATOR`, so a definition that could
not execute is never stored.

| `op` | Meaning | `param` / `value` shape |
|------|---------|--------------------------|
| `eq` | Equal | Scalar. A **null** bound value means IS NULL. |
| `ne` | Not equal | Scalar. A **null** bound value means IS NOT NULL. |
| `gt` / `gte` / `lt` / `lte` | Ordering comparison | Scalar. A null bound value throws `NAMED_QUERY_PARAM_REQUIRED`. |
| `in` / `nin` | Membership | Array, non-empty; bounded by `maxItems`. |
| `like` | SQL `LIKE` pattern, **String columns only** | String pattern, bounded by `maxLength`. Null throws `NAMED_QUERY_PARAM_REQUIRED`. |

`isNull`, `isNotNull`, and `between` are **not** wire operators — they are spellings the SDKs desugar for
you (`eq null`, `ne null`, and `gte` + `lte`). Write those encodings directly in a definition.

**`like` semantics.** `%` matches any sequence of characters including none; `_` matches exactly one;
`\` escapes `%`, `_`, or `\`. Matching is **ordinal and case-sensitive** — the same collation as `eq` on a
String column — so upper- or lower-case both sides yourself if you need a case-insensitive search. A null
column value never matches, not even `"%"`. A malformed pattern (a trailing lone `\`, or an escape of
anything else) is a `400`. A `like` condition on a non-String column is refused at apply. `like` does
**not** satisfy the [partition-filter rule](browser-tier-read-limits.md), and it is a scan — there is no
index acceleration for patterns.

The caller supplies the pattern, so wrap it on the way in and strip user-supplied wildcards if the search
box should not expose them:

```json
{ "column": "searchText", "op": "like", "param": "keywords", "whenParamPresent": true }
```

```ts
// The caller decides the pattern shape; the definition fixes the column and the operator.
await client.namedQueries.execute("equity.stocks.screener", {
  keywords: `%${userInput.replace(/[%_\\]/g, "")}%`,
});
```

Apply:

```bash
aouda schema apply --file aouda.schema.json
```

Editing a definition **under the same name** changes behaviour for every caller at apply time (see [Trade-away](#trade-away)). Deprecate with `deprecatedAt` / `sunsetAt`; execute still returns 200 plus `warnings: [{ "code": "NAMED_QUERY_DEPRECATED", "name": "…", "sunsetAt": "…" }]`.

---

## Types (optional codegen)

`npx @aouda/client generate` and `aouda generate` emit `Args` / `Row` types only. They do **not** emit name const maps. A frontend that ignores codegen is fully functional — the identity is a string literal from the schema.

```ts
const { rows } = await client.namedQueries.execute("equity.quoteByTicker", { ticker: "AAPL" });
```

```csharp
await client.NamedQueries.ExecuteAsync("equity.quoteByTicker", args);
```

There is **no** `POST /named-queries/register`. Inventory is `GET …/schema/export`.

---

## Array columns (**BL-035, next train**)

(**BL-035, next train**) A named query may **select** an [array column](array-columns.md) (`"select": ["CurveId", "Rates"]`); the
result gives the array whole, in `types` as `"Double[]"`. It may not use one in `where`, `orderBy`, a group,
an aggregate (`count(col)` included), `distinct`, a `selectExpr`, a join key or a `perKey` key or order: that definition is **refused at `schema apply`** —
its entry is `Failed` with a reason starting `ARRAY_COLUMN_UNSUPPORTED:` — and the other definitions in the document still apply.
A named mutation may write an array column from a parameter or a literal (`upsert` and `update … set` replace the whole array), but
may not use one in its `where`, a `setExpr` or an `orderBy`, or give its parameter a `min` / `max` / `maxLength` / `enum`. See
[Array columns — what is refused](array-columns.md#what-is-refused-and-where).

## Paging, distinct, and count

These fields exist on the definition. They were missing from this page.

**`limit` / `limitParam`.** Every named query needs a numeric `limit` cap (`NAMED_QUERY_UNCAPPED_LIMIT` at apply). `limitParam` is the **name** of a parameter the caller may send to choose a smaller page size; it does not replace the cap.

**`offset` / `offsetParam`.** Same pattern for the **max-skip cap**. `offsetParam` requires a positive offset cap at apply. When the caller **omits** `offsetParam` (or sends JSON/CLR null), bind skip is **0** (first page) — not the cap. A present argument is clamped to `[0, offset]`; over-cap is `NAMED_QUERY_BIND_FAILED`. A non-zero offset (literal or bound param) **disqualifies subscribe** (`NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`). HTTP execute still pages. Omitted `limitParam` still uses the cap as the page size.

```json
"equity.quotesPage": {
  "table": "EquityQuote",
  "select": ["ticker", "bid", "ask", "asOf"],
  "where": { "and": [{ "column": "ticker", "op": "in", "param": "tickers" }] },
  "orderBy": [{ "column": "ticker", "descending": false }],
  "limit": 25,
  "limitParam": "pageSize",
  "offset": 10000,
  "offsetParam": "pageOffset",
  "count": true,
  "params": {
    "tickers": { "required": true, "maxItems": 32 },
    "pageSize": { "min": 1, "max": 25 },
    "pageOffset": { "min": 0, "max": 10000 }
  }
}
```

**`count: true`.** The response includes `totalMatches` (HTTP; omitted when the definition has no `count`) so a footer can render "1–25 of 412" from one round trip. Subscribe snapshots set `total_matches` on `snapshot_complete`. Count **ignores** limit/offset, and it is taken by the same read as the page, over the same snapshot, so the total and the rows always agree (**ColumnarRead, 0.3.0** — it used to be a second `COUNT` query). Apply rejects a count whose cost is not bounded (`NAMED_QUERY_COUNT_UNBOUNDED`) — joins, `distinct`, or a partitioned table whose WHERE does not cover every partition key with a **required** `eq`/`in`. `POST …/query/count` stays **404** on the data plane.

**`distinct: true`.** Exists. Subscribe refuses it. When every distinct column is a raw partition key and the predicate touches only partition keys, one partition key constrained by `eq`/`in` is enough to pass the partition-filter rule — that is the "which sources exist for this ticker?" query. It is answered on the scan, pruned to the constrained keys, which skips row groups from their statistics and answers those the filter selects whole from them (**architecture review, ColumnarRead2 S04, 0.3.0**). The partition-directory answer is retired: a directory outlives the rows deleted or truncated from it, so such a partition kept appearing. With it go the `stats.distinctServedFromPartitionMetadata` flag and the refusals for directory residue or more than 10 000 tuples. Full rule: [browser-tier read limits](browser-tier-read-limits.md#partition-filter-rule).

---

## Optional predicates (`whenParamPresent`)

Mark a `where` condition with `"whenParamPresent": true` to make it **skip entirely** when the caller omits that argument. Without the marker, an omitted required param throws `NAMED_QUERY_PARAM_REQUIRED`; an omitted optional param becomes `null` (`IS NULL` for `eq`/`ne`; throws for range/`in`).

```json
"listings.screener": {
  "table": "listings",
  "select": ["ticker", "currency", "sector", "mcap"],
  "where": {
    "and": [
      { "column": "currency", "op": "in",  "param": "currency", "whenParamPresent": true },
      { "column": "sector",   "op": "eq",  "param": "sector",   "whenParamPresent": true },
      { "column": "mcap",     "op": "gte", "param": "minMcap",  "whenParamPresent": true }
    ]
  },
  "orderBy": [{ "column": "ticker", "descending": false }],
  "limit": 25, "limitParam": "pageSize",
  "count": true,
  "params": {
    "currency":  { "required": false },
    "sector":    { "required": false, "maxLength": 64 },
    "minMcap":   { "required": false },
    "pageSize":  { "required": false, "min": 1, "max": 25 }
  }
}
```

Calling with `{}` returns all rows (no predicate applied). Calling with `{ "sector": "Tech" }` applies only the sector filter.

Constraints:

- Only valid on `and`-clause conditions. An `or` condition with `whenParamPresent` fails apply.
- A marked condition **never** counts as partition-key coverage for `count: true`. The table must be unpartitioned, or all required partition predicates must be separately covered by non-marked conditions.
- Params that control `whenParamPresent` conditions should declare `"required": false` (the engine defaults to `required: true` when the field is absent).

---

## Server-time bounds (`serverTime` parameters)

(**NativeClients, 0.4.0**)

A parameter declared `{ "serverTime": { "offsetSeconds": <n> } }` is bound **by the server**, at execute, to its own UTC
clock plus `n` seconds. It is how a read asks "seen in the last 75 seconds" against one clock — the server's — instead of
each device's:

```json
"connect.presence.online": {
  "table": "Presence",
  "select": ["UserId", "State", "LastHeartbeat"],
  "where": { "and": [{ "column": "LastHeartbeat", "op": "gt", "param": "leaseStart" }] },
  "params": { "leaseStart": { "serverTime": { "offsetSeconds": -75 } } },
  "limit": 500
}
```

- **One-shot reads only**: execute, batch, `count` and aggregate definitions. **Subscribe refuses** the query with
  `NAMED_QUERY_SERVER_TIME_NOT_SUBSCRIBABLE` — a row would leave the result because time passed, with no write to
  report, which is a timer, not a predicate. Subscribe to the table's query without the bound and judge the lease on the
  client (below), or execute the bounded query on an interval. A materialized query cannot declare one (its predicate takes
  literal values).
- **The caller cannot supply it.** Naming it in `args` fails with `NAMED_QUERY_SERVER_TIME_INVALID` (400); omit it.
  Generated typed clients leave it out of the arguments.
- **Where it may stand** (checked at apply, `NAMED_QUERY_SERVER_TIME_INVALID`): an `eq` / `ne` / `gt` / `gte` / `lt` / `lte`
  condition on a `Timestamp` column, in the base `where` or a join's. Not `in` / `like`, not `whenParamPresent`, not a
  `limitParam` / `offsetParam`, not in `selectExpr`, and with no other constraint (`required`, `min`, …). Named mutations
  cannot declare one. `offsetSeconds` is within ±10 years.
- **Whose clock.** The node that answers the read binds the bound, and stamps are the primary's clock — a read served by a
  secondary compares the secondary's clock with the primary's stamps, so their skew shifts the lease window. Read leases from the
  primary, or allow for the skew.
- **Pairs with a server-time stamp.** With `LastHeartbeat` declared `derived: { "serverTime": "write" }`
  ([insert transforms](insert-transforms.md#server-time-stamp-servertime)), both
  sides of the comparison are the server's clock.

**Judging a lease on the client.** A subscription delivers the rows; whether a lease has lapsed is a comparison with now.
Use the server's now: every HTTP response carries a `Date` header, readable cross-origin, and both SDKs keep the offset —
`client.serverClockOffsetMs` / `client.serverNow()` in TypeScript, `ServerClockOffset` / `ServerNow()` in C# — good to
about a second.

## Bounded sort choices (`orderByChoices` / `orderByIndex`)

Declare a list of allowed sort permutations in the definition. The caller picks one by index in the execute or subscribe request.

```json
"gainers.top": {
  "table": "bars_with_change",
  "select": ["ticker", "open", "close", "changePct"],
  "orderBy": [{ "column": "changePct", "descending": true }],
  "orderByChoices": [
    [{ "column": "changePct", "descending": true  }],
    [{ "column": "ticker",    "descending": false }]
  ],
  "limit": 20,
  "params": {}
}
```

**Execute with the second sort (index 1):**

```json
{ "args": {}, "orderByIndex": 1 }
```

The engine rejects an index outside `[0, len(orderByChoices) - 1]`. Omitting `orderByIndex` uses the definition's `orderBy` default (index 0). `orderByIndex` works the same way in the batch envelope and in subscribe.

Expression `orderBy` on an arbitrary runtime column is **not** offered (BL-183). Sort keys must be declared at apply time.

---

## Execute

`POST /api/databases/{db}/named-queries/{name}/query`

Body is `{ "args": { … } }` only. No `database` field (the path already has it).

### HTTP

```bash
# Data-plane listener (mk_pub_* or application user JWT). Admin :5433 rejects mk_pub_*
# with AUTH_KEY_LISTENER_MISMATCH.
curl -s -X POST \
  -H "Authorization: Bearer $MK_PUB_OR_JWT" \
  -H "Content-Type: application/json" \
  http://localhost:5434/api/databases/trading/named-queries/equity.quoteByTicker/query \
  -d '{"args":{"ticker":"AAPL"}}'
```

Success looks like any other query result: column arrays (`columns`, `types`, `data`, `rowCount`). (**Lead S12, 0.6.0**) There is no `format` parameter any more; `?format=` is refused `400 INVALID_FORMAT`. Unknown name → `404 NAMED_QUERY_NOT_FOUND`. On the **data-plane listener**, a missing token or an unentitled caller (`mk_anon_*`, user JWT without `db_reader`) is the **same** 404 — not 401/403 — so names are not enumerable. The **admin listener** still returns 401 (`AUTH_TOKEN_MISSING`) / 403 (`AUTHORIZATION_DENIED`). Bind failure → `400 NAMED_QUERY_BIND_FAILED` (or `NAMED_QUERY_PARAM_REQUIRED`) **before** the engine runs.

### TypeScript (`@aouda/client`)

```typescript
import { AoudaClient } from "@aouda/client";

const client = new AoudaClient({
  serverUrl: "https://data.example.com", // data-plane listener
  database: "trading",
  appAuth: { apiKey: process.env.AOUDA_PUB_KEY! }, // mk_pub_…
});
await client.connect();
// after user sign-in, attach the user JWT — do not put identity in args

const { rows } = await client.namedQueries.execute("equity.quoteByTicker", {
  ticker: "AAPL",
});
```

### C# (`Aouda.Client`)

```csharp
var client = new AoudaClient("https://data.example.com", "trading")
{
    // configure mk_pub_ / user JWT on the options you already use
};

var result = await client.NamedQueries.ExecuteAsync(
    "equity.quoteByTicker",
    new Dictionary<string, object?> { ["ticker"] = "AAPL" });
```

Empty or whitespace name throws locally on both SDKs.

On the data-plane, `POST …/query` (ad-hoc) is **404** for every credential. Service keys that need ad-hoc use the admin listener.

---

## Batch (one snapshot)

`POST /api/databases/{db}/named-queries/batch`

A dashboard of independent panels should not issue N sequential executes. A batch of N **names** returns N **positional** results from **one** read snapshot. Cap **32**.

```json
{
  "queries": [
    { "name": "equity.quoteByTicker", "args": { "ticker": "AAPL" } },
    { "name": "equity.stockOverview", "args": { "accountId": 42 } }
  ]
}
```

HTTP **200** means the envelope was accepted. A missing name or a bind/ADRA failure is:

```json
{
  "results": [
    { "columns": ["ticker", "bid"], "types": ["String", "Decimal"], "data": [["AAPL"], [189.200000]], "rowCount": 1 },
    { "code": "NAMED_QUERY_NOT_FOUND", "error": "Named query 'equity.unknown' was not found." }
  ]
}
```

Envelope **400** (no `results`): empty array, more than 32 elements, or a **named-mutation** name (`NAMED_QUERY_BATCH_MUTATION`).

```typescript
const slots = await client.namedQueries.batch([
  { name: "equity.quoteByTicker", args: { ticker: "AAPL" } },
  { name: "equity.stockOverview", args: { accountId: 42 } },
]);

for (const slot of slots) {
  if (slot.isError) {
    console.error(slot.code, slot.error);
    continue;
  }
  console.log(slot.result!.rows);
}
```

```csharp
var slots = await client.NamedQueries.BatchAsync(new[]
{
    new NamedQueryBatchInput("equity.quoteByTicker", new Dictionary<string, object?> { ["ticker"] = "AAPL" }),
    new NamedQueryBatchInput("equity.stockOverview", new Dictionary<string, object?> { ["accountId"] = 42L }),
});
```

Two sequential single executes under a concurrent writer **may disagree**. The batch must not — that is the correctness upgrade, not only a latency one.

**Composition vs batch:** if panel B's filter is a column from panel A, write **one** named query with joins (composition). Use batch only for **independent** work.

---

## Subscribe by name

On the data-plane, WebSocket `subscribe` **requires** `"name"` (and optional `args`). Ad-hoc `target` + `filter` is `NAMED_QUERY_SUBSCRIBE_REQUIRED`.

The server conjoins named-query ∧ PLS ∧ RLS into one effective predicate at subscribe time and **pins** that hash for the connection. Redeploying the alias does not change an in-flight subscription. A permission-version bump re-keys the fan-out bucket; revoked rows stop within one event.

Live `change` `row` / `prev` contain only the declared projection.

Use the SDK — gap resume, reconnect, `re_auth`, snapshot paging, and conflation stay on the existing transport:

```typescript
const sub = client.namedQueries.subscribe<ByTickerRow>(
  namedQueries.byTicker.hash,
  { ticker: "AAPL" },
  {
    conflate: { key: ["ticker"], interval_ms: 100 },
    onSnapshot: (rows) => { /* current match */ },
    onChange: (evt) => { /* insert | update | delete */ },
  }
);
// later
await sub.unsubscribe();
```

```csharp
await foreach (var evt in client.NamedQueries.SubscribeAsync(
    NamedQueries.ByTicker,
    new Dictionary<string, object?> { ["ticker"] = "AAPL" },
    new SubscribeOptions { Conflate = new ConflateOptions(["ticker"], 100) },
    ct))
{
    if (evt.IsSnapshot) { /* current match */ }
    else { /* insert | update | delete */ }
}
```

Endpoint: `wss://{host}/api/databases/{db}/ws`. Snapshot paging, `snapshot_complete`, `gap`, and `re_auth` are in the [HTTP API WebSocket section](../reference/http-api.md#websocket-streaming-protocol) and [Real-time streaming](real-time.md). The wire envelope is unchanged if you must send frames yourself:

```json
{
  "type": "subscribe",
  "id": "sub-1",
  "name": "equity.quoteByTicker",
  "args": { "ticker": "AAPL" },
  "conflate": { "key": ["ticker"], "interval_ms": 100 }
}
```

`conflate` holds only a value `update` visible before **and** after. On an insert-only tick table it does **not** reduce the event rate — set `"collapse_inserts": true` in the conflate object to hold latest-wins inserts, or point at a `latestPerKey` MQ instead. See [browser-tier read limits](browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

```json
{ "type": "subscribe", "id": "lp", "name": "quotes.lastPrice",
  "args": { "tickers": ["AAPL"], "source": "nasdaq" },
  "conflate": { "collapse_inserts": true } }
```

The server conjoins named-query ∧ PLS ∧ RLS into one effective predicate at subscribe time and **pins** the bound `Where` + `Select` for the connection. Editing the named query does not change an in-flight subscription. A permission-version bump re-keys the fan-out bucket; revoked rows stop within one event.

Live `change` `row` / `prev` contain only the declared projection.

Endpoint: `wss://{host}/api/databases/{db}/ws`. Snapshot paging, `snapshot_complete`, `gap`, and `re_auth` are in the [HTTP API WebSocket section](../reference/http-api.md#websocket-streaming-protocol) and [Real-time streaming](real-time.md).

### From the SDKs

Both clients expose this directly — you do not hand-roll the frames. `namedQueries.subscribe` returns the **same** subscription object as table subscribe, so snapshot paging, `gap` → `resume_from`, reconnect, `re_auth`, and `SLOW_CONSUMER` recovery are the paths you already have. Every resend carries the same `name` + `args`.

```typescript
const sub = client.namedQueries.subscribe(
  "equity.quoteByTicker",
  { ticker: "AAPL" },
  {
    conflate: { key: ["ticker"], interval_ms: 100 },
    onSnapshot: (rows, version) => grid.reset(rows, version),
    onChange: (event) => grid.apply(event),
    onError: (error) => console.error(error),
  }
);

await sub.unsubscribe();
```

```csharp
await foreach (var evt in client.NamedQueries.SubscribeAsync(
    "equity.quoteByTicker",
    new Dictionary<string, object?> { ["ticker"] = "AAPL" },
    new SubscribeOptions { Conflate = new ConflateOptions(["ticker"], TimeSpan.FromMilliseconds(100)) },
    ct))
{
    // snapshot pages, then snapshot_complete, then change events
}
```

Notes that bite:

- **Pass no `filter`.** The predicate is the definition plus your `args`; there is no client-side filter on a named subscription. `client.table(t).subscribe(…)` still sends `target` and still works on the **admin** listener — it is refused on the data-plane.
- An empty or whitespace name throws before anything is sent.
- A deprecated name still subscribes. It adds `NAMED_QUERY_DEPRECATED` to `snapshot_complete.warnings`, which raises the named-artifact warning sink **once** and still delivers the snapshot.
- Definitions using `joins`, `selectExpr`, `distinct`, `aggregates` / `groupBy`, `perKey` (**0.3.0**), or a non-zero offset are refused with `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`. HTTP execute of those still works — only the live path is restricted.
- `conflate` on an insert-only stream is a no-op (see above).

---

## Named mutations

```bash
# Browser-tier JWT on the data-plane. Service keys that mutate via named artifacts
# may use either listener; ad-hoc insert still requires admin.
curl -s -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  http://localhost:5434/api/databases/trading/named-mutations/equity.adjustQty/execute \
  -d '{"args":{"id":1,"qty":10}}'
```

```typescript
await client.namedMutations.execute("equity.adjustQty", { id: 1, qty: 10 });
```

Response uses the existing mutation counts (`rowsInserted` / `rowsUpdated` / `rowsDeleted`) plus optional `RETURNING` rows. Mutations are **not** allowed in the read batch.

**`returning` on `insert` and `upsert`** (**NativeClients, 0.4.0**; BL-639 — accepted and ignored before). The declared
columns of the rows **written**, under `rows`, as `update` / `delete` return them: an insert's rows in request order, with
their server-computed values (stamps, derived columns, generated ids); an upsert's **one row per key** — the row that won
(the batch's last row for a repeated key), as stored, so an `insert` stamp of an existing key is the stored one, not this
write's. A write that would return more than `MaxReturningRows` rows fails before writing with
`NAMED_MUTATION_RETURNING_OVERFLOW`.

### Choosing `op`

| `op` | Shape | Requires | Result fields |
|---|---|---|---|
| `insert` | row template in `values` | — | `rowsInserted`, `generatedValues`, `RETURNING` rows (**NativeClients, 0.4.0**) |
| `upsert` *(**BL-637, 0.1.37**)* | row template in `values` | the table declares a **primary key** | `rowsInserted`, `rowsUpdated`, `generatedValues`, `RETURNING` rows (**NativeClients, 0.4.0**) |
| `update` | `where` + `set` / `setExpr` | non-empty `where` | `rowsUpdated`, `RETURNING` rows |
| `delete` | `where` | explicit `limit` cap | `rowsDeleted`, `RETURNING` rows |

> **`insert` will not overwrite. For one row per key, use `upsert`.**
>
> An `op: "insert"` that names a primary key a live row already holds fails with **`409
> DUPLICATE_PRIMARY_KEY`**. It does not update, and there is no "insert if absent" mode of
> `insert`.
>
> This matters most for the shape it is easiest to get wrong: **one row per identity, written on
> a timer** — a presence heartbeat, a typing indicator, a last-seen roster. The primary key is
> `derived: { "identity": "subject" }`, so the caller never supplies it and the first call looks
> like it works. Every call after that names the same key. Declared `insert` it succeeds exactly
> once per user and then fails forever; declared `update` it never succeeds at all, because on
> the first call there is no row to match.
>
> ```json
> "Presence": {
>   "columns": {
>     "UserId":        { "type": "String", "primaryKey": 1, "derived": { "identity": "subject" } },
>     "State":         { "type": "String" },
>     "LastHeartbeat": { "type": "Timestamp", "derived": { "serverTime": "write" } }
>   }
> }
> ```
>
> ```json
> "connect.presence.heartbeat": {
>   "op": "upsert",
>   "table": "Presence",
>   "values": { "State": { "param": "state" } },
>   "params": { "state": { "required": true } }
> }
> ```
>
> The server stamps `LastHeartbeat` with its own clock on every heartbeat (a
> [server-time stamp](insert-transforms.md#server-time-stamp-servertime),
> **NativeClients, 0.4.0**), so a lease is judged against one clock, not each device's. The
> mutation does not, and cannot, send it.
>
> ```text
> first call                every call after
> { "rowsInserted": 1,      { "rowsInserted": 0,
>   "rowsUpdated": 0 }        "rowsUpdated": 1 }
> ```
>
> The split is the point of the two counters: an upsert whose `rowsInserted` stays at zero is a
> heartbeat working correctly, and one that *only* ever inserts is a key that is not matching.
>
> **What `upsert` costs.** Matching by key means the target is kept resident as a mutable keyed
> tier, so lookups stay O(1) and an updated key never seals into a hot copy the write path would
> have to tombstone. That is the right trade for a **bounded** keyspace — one row per user, per
> device, per session — and the wrong one for an unbounded stream of new keys, which should stay
> `insert`. The same mechanism backs the upsert write-stream
> ([HTTP API `stream_open`](../reference/http-api.md#stream_open)).
>
> **Apply-time checks.** `upsert` on a table with no primary key is refused at schema apply —
> there would be nothing to match on and every call would silently append.
>
> `upsert` is last-write-wins: the whole row in `values` replaces the stored row. It is not a
> partial merge, so a column you omit from `values` is written as its default, not preserved.
> When you need to change some columns and keep the rest, that is `op: "update"`.


### Writing `values` and `set`

Each entry maps a **column** to one of three things — a literal, a parameter hole, or an explicit constant:

```json
"message.send": {
  "op": "insert",
  "table": "Messages",
  "values": {
    "ConversationId": { "param": "conversationId" },
    "Content":        { "param": "content" },
    "Source":         "web",
    "Id":             { "value": 0 }
  },
  "params": { "conversationId": {}, "content": { "maxLength": 4000 } }
}
```

- **Literal** — any JSON value that is not an object (`"web"`, `0`, `null`, `[0.1, 0.2]`). Stored as written, on every call.
- **`{ "param": "<name>" }`** — filled from the caller's `args`, validated against that parameter's `params` entry.
- **`{ "value": <literal> }`** — the same thing a bare literal does, said out loud. Useful where a constant reads better next to the holes around it, as `"Id"` does above.

The object shape belongs to those two one-key forms and nothing else, because `{ "param": … }` already owns it — a bare object constant would be indistinguishable from a mistyped hole. So a typo is caught at **schema apply**, not on the thousandth execute:

```json
{ "Id": { "valu": 0 } }
```

```text
NAMED_MUTATION_VALUE_NODE_INVALID: Named mutation values column 'Id' is an object node
with key(s) 'valu'; expected a literal, a { "param": "<name>" } hole, or a
{ "value": <literal> } constant.
```

The same goes for `{ "value": 0, "param": "id" }`, `{}`, and an object nested under `value`. A definition deployed before this check existed still loads; its `execute` fails with `NAMED_MUTATION_BIND_FAILED` naming the column (BL-479 — such a node used to be carried into the row and die much later as an untyped `INVALID_REQUEST` from column conversion, naming neither the column nor the mutation).

To put a JSON document in a `String` column, send it as a JSON **string** — `"Meta": "{\"a\":1}"` — not as a bare object.

Identity columns are the one thing `values` may **not** name: a column with `derived: { "identity": "subject" }` is stamped by the engine from the caller's token, and naming it fails apply with `SCHEMA_IDENTITY_COLUMN_NOT_BINDABLE`. Leave it out; it is filled in for you.

### Batch insert (`batchParam`)

An `op: "insert"` definition can accept **many rows in one execute call** instead of a single row. Declare `batchParam` with the name of a parameter that will carry them; `values` stays the per-row template.

(**Lead S12, 0.6.0; breaking**) The batch argument is **column arrays**, like every write body
([HTTP reference](../reference/http-api.md#column-arrays-the-write-body)): `columns` names the parameters, `data` holds one array per
parameter with one value per row, and the optional `absent` lists, per parameter, the rows that do not give it. Row *i*'s values fill
that row's `{ "param": … }` holes, overriding a top-level `args` value of the same name; a parameter a row does not give falls back to
`args`. An array of row objects — the only form before this train — is refused `400 ROW_OBJECTS_UNSUPPORTED`.

```json
"tick.record": {
  "op": "insert",
  "table": "PriceTick",
  "values": {
    "ticker": { "param": "ticker" },
    "px": { "param": "px" }
  },
  "batchParam": "rows",
  "params": {
    "ticker": { "maxLength": 8 },
    "px": {},
    "rows": { "maxItems": 20000 }
  }
}
```

```bash
curl -s -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  http://localhost:5434/api/databases/trading/named-mutations/tick.record/execute \
  -d '{"args":{"rows":{"columns":["ticker","px"],"data":[["AAPL","MSFT"],[189.2,402.1]]}}}'
```

```typescript
// The SDK sends a batch argument given as rows as column arrays (Lead S14, 0.6.0) — the type the generated client
// declares for it (`Array<{…}>`). A ColumnBatch works too.
await client.namedMutations.execute("tick.record", {
  rows: ticks.map((t) => ({ ticker: t.ticker, px: t.px })),
});
```

`maxItems` on the batch parameter is **required** (it counts rows) — schema apply fails without it (`NAMED_MUTATION_BATCH_MAX_ITEMS_REQUIRED`), the same mechanism that bounds an `in`/`nin` list. `batchParam` is legal on the row-shaped ops, `op: "insert"` and (**BL-637, 0.1.37**) `op: "upsert"`; setting it on `update`/`delete` fails apply (`NAMED_MUTATION_BATCH_NON_INSERT`) — batching those is a separate, still-deferred predicate-shaped question (which row does which predicate identify?).

**autoIncrement primary keys.** The `tick.record` example above has no surrogate PK. If the target table has an `autoIncrement` primary key (e.g. `"Id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true }`), a `values` template that leaves it out gets a generated id on every row, as an insert that leaves the column out does (BL-429; before 0.1.33 that was `400 INVALID_REQUEST`, `Missing required column 'Id'`). To say so explicitly, the constant form states it once in the definition and keeps it out of every call's `args`:

```json
"values": {
  "Id": { "value": 0 },
  "ticker": { "param": "ticker" },
  "px": { "param": "px" }
}
```

For a batch insert where some callers choose the id, bind it instead and send `0` in each row that wants one generated:

```json
"values": {
  "Id": { "param": "id" },
  "ticker": { "param": "ticker" },
  "px": { "param": "px" }
}
```

```json
{ "args": { "rows": { "columns": ["id", "ticker", "px"], "data": [[0], ["AAPL"], [189.2]] } } }
```

`0` still means auto-generate. Leaving the **column** out of the template means the same as `0` — so the constant form is a convenience rather than a requirement — but leaving a bound **parameter** out of a row does not: a required parameter (the default) refuses the call with `400 NAMED_QUERY_PARAM_REQUIRED`, and one declared optional binds `null`, which is not a request for an id. Send `0`. `generatedValues` in the mutation result carries the allocated id (**Lead S12, 0.6.0**: as column arrays, `{ "columns": ["Id"], "data": [[…]] }`, one cell per row). The same rule applies to plain `POST …/tables/{t}/rows`. Under `identityInsert: true`, omitting the column is still an error: you asked to control the identity and then did not supply one.

Bind is **all-or-nothing**, matching the plain multi-row insert path: the cap is checked, then every row is bound, before any row reaches the engine. One malformed row fails the whole call — no partial insert — and the `400` response names the offending row index:

```json
{
  "error": "Required parameter 'px' was not supplied. (batch index 1)",
  "code": "NAMED_QUERY_PARAM_REQUIRED",
  "rowErrors": [{ "index": 1, "code": "NAMED_QUERY_PARAM_REQUIRED", "message": "Required parameter 'px' was not supplied. (batch index 1)" }]
}
```

This is the recommended path for a bounded, continuous-trickle insert feed (e.g. a ~10s-cadence ingest worker) through the data-plane listener, without reaching for the admin-only, exclusive-lock [Bulk Load](bulk-load.md) path. A definition without `batchParam` is unaffected — `args` stays one flat object, exactly as before.

---

## Authorization (always underneath)

Every named-query execute, batch element, mutation, and subscribe applies **the caller's** PLS and RLS. A bug in a named query cannot leak across a tenant boundary **if ADRA is intact** — which is why fail-closed resolvers and the [access-surface diff](access-surface.md) exist.

Visibility is **granted**, never implied by the kind of key. A service key (`mk_svc_*`) holds `all-partitions` and `all-rows` on its database, and a user with a `db_admin` role assignment on the database holds the same (a token that only *claims* `db_admin` holds nothing), so a named query run by either sees what a direct read would see. Any other credential sees its partition grants or tenant, or holds the grant through a role. Service keys are for backends, not browsers. A call that a grant decided is audited like any read: one `access_grant_used` row per table and grant per request, and a batch whose slots read one table writes one row per grant, not one per slot. See [Visibility is granted](../auth/authorization.md#visibility-is-granted-all-partitions-and-all-rows). (**BL-1227, next train**)

### `crossPartitionAccess` per call

A named-query call on the **admin** listener can send `crossPartitionAccess: true` (an execute body, or one item of a batch; `cross_partition_access` on a [subscribe](#subscribe-by-name)). It waives the partition-filter guard when the query's `where` binds no partition key, and nothing else: the rows stay the caller's grants: a credential without `all-partitions` reads only its partition grants (or its tenant), and one with no grant at all on a PLS table is still refused. A definition cannot set it, and the data-plane listener ignores it. A browser binds the key in the definition instead; see [`crossPartitionAccess` on the data-plane listener](browser-tier-read-limits.md#crosspartitionaccess-on-the-data-plane-listener). (**BL-1227, next train**)

There is no catalog field, header, or option that runs a named query as someone else.

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `404 NAMED_QUERY_NOT_FOUND` | Name not deployed or typo | Apply schema; use the schema key as a string literal |
| Data-plane execute 404 (no 401/403) | Missing token or `mk_anon_*` / unentitled JWT on a listed named-query route | Expected on the data-plane. Use `mk_pub_*`, an entitled user JWT, or a service key. Admin listener still 401/403. |
| `404 TABLE_NOT_FOUND` on a table that exists | Data-plane + browser-tier + `dataPlaneAccess: false` | Set `dataPlaneAccess: true` on every touched table **and** MQ entry (including joins) |
| `400 NAMED_QUERY_BIND_FAILED` | Arg type/constraint | Check `params` (`maxLength`, `min`/`max`, `enum`, `maxItems`) |
| Schema apply `NAMED_QUERY_IDENTIFIER_PARAM` | `$table` / parameterized column | Rewrite; parameters are literals only |
| Schema apply `NAMED_QUERY_UNCAPPED_LIMIT` | Missing `limit` | Set a numeric cap (or a constrained `limitParam`) |
| Schema apply `NAMED_QUERY_COUNT_UNBOUNDED` | `count: true` on a join, `distinct`, or uncovered partition keys | Cover every partition key with required `eq`/`in`, or drop `count` |
| Schema apply `NAMED_QUERY_COST_EXCEEDED` | Too many joins | Split the query or drop a join (cap default 8 = `1 + joins`) |
| Batch HTTP 400 `NAMED_QUERY_BATCH_MUTATION` | Mutation name in `queries` | Mutations have their own execute route |
| Schema apply `NAMED_MUTATION_BATCH_MAX_ITEMS_REQUIRED` | `batchParam` set without `maxItems` on that parameter | Declare `"maxItems"` on the batch parameter's `params` entry |
| Schema apply `NAMED_MUTATION_BATCH_NON_INSERT` | `batchParam` set on `op: "update"` / `"delete"` | Row-shaped ops only (`insert`, `upsert`); update/delete batching is not shipped |
| Execute `409 DUPLICATE_PRIMARY_KEY` *(**BL-636, 0.1.37**)* | An `op: "insert"` named a primary key a live row already holds — most often a per-identity row written on a timer | Switch the definition to [`op: "upsert"`](#choosing-op). Before BL-636 this arrived as `500 INTERNAL_ERROR` with the cause only in the server log |
| Schema apply, `upsert` refused for want of a primary key *(**BL-637, 0.1.37**)* | `op: "upsert"` on a table with no `primaryKey` column | Upsert matches on the key; declare one, or use `op: "insert"` |
| Batch insert HTTP 400 with `rowErrors` | One array element failed to bind | Fix the element at `rowErrors[0].index`; the whole call was rejected, nothing was inserted |
| Insert / named-mutation execute `400` `Missing required column 'Id'` | A non-`autoIncrement` required column is missing, or `identityInsert: true` with the `autoIncrement` column omitted | Supply the column. An **omitted `autoIncrement`** column is not this error — it means `0` (auto-generate) |
| Schema apply `NAMED_MUTATION_VALUE_NODE_INVALID` | A `values` / `set` entry is an object that is neither `{ "param": … }` nor `{ "value": … }` — usually a typo, or a bare object meant as a constant | Use one of the [three entry forms](#writing-values-and-set). A JSON document for a `String` column goes in as a JSON string |
| Execute `400` `NAMED_MUTATION_BIND_FAILED` naming a column | Same bad node, in a definition deployed before apply validated it | Re-apply the schema with a valid node; the error names the column |
| Batch HTTP 200 with a slot `code` | Per-element failure | Handle positional errors; do not retry the whole envelope unless you mean to |
| `NAMED_QUERY_DEPRECATED` warning | Name sunset pending | Log it; migrate callers to the replacement name before `sunsetAt` |
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` | Data-plane subscribe without `"name"` | Call `subscribe(name, args)` |
| Data-plane `POST /query` 404 | Listener allowlist | Use named-query execute, or connect the service key to the **admin** listener |

---

## Not in this release

- SQL-ish authoring surface (definitions are JSON `QueryMessage` templates).
- Runtime registration of definitions.
- Named-mutation **update/delete** batching — a separate, predicate-shaped design question (which row does which predicate identify?). Insert batching exists via [`batchParam`](#batch-insert-batchparam). The read [batch envelope](#batch-one-snapshot) stays read-only either way — a named-mutation name is always illegal there.
- Static admissibility of client-composed queries (Firestore-style). Named queries are the browser-tier surface instead.
- Cross-server named-query sharing through Hub (use a shared schema fragment in git).
- OAuth 2.0 authorization code + PKCE — [not shipped](direct-client-access.md#authentication-that-exists).
- Expression `orderBy` on runtime columns (BL-183) — sort keys must be declared in `orderByChoices` at apply time.
- Cursor paging (BL-182) — use `limitParam` / `offsetParam` for page-by-offset today.

---

## Related

- [How to build apps effortlessly with Aouda](build-apps.md) — where named queries fit in the whole build path
- [Direct client access](direct-client-access.md) — listeners, `mk_pub_*`, quotas
- [What a browser-tier read cannot do](browser-tier-read-limits.md) — operators, allowlist, partition rule, conflation caveat
- [Division of responsibility](division-of-responsibility.md) — what belongs in a service
- [Adopting Aouda](adoption.md) — SDK coverage, capacity, and the order to migrate in
- [Access-surface diff](access-surface.md) — CI gate on widening (including `named_query_body_changed` and `freshness` loosen)
- [Freshness and replica consistency](freshness.md) — token, `AtLeast`, named-query `freshness`, caveats
- [HTTP API](../reference/http-api.md)
- [TypeScript client](../clients/typescript.md)
