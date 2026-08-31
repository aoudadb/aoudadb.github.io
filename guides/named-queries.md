---
title: "Named queries and mutations"
nav_order: 8
parent: "Guides"
---

# Named queries and mutations

Document status: Complete (BL-188 S09)  
Last updated: 2026-08-22

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
| `select` / `selectExpr` | **Required** | `*` is refused (`NAMED_QUERY_PROJECTION_STAR`). |
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
        "bid": { "type": "Decimal" },
        "ask": { "type": "Decimal" },
        "internalSpread": { "type": "Decimal" },
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
- `dataPlaneAccess: true` is required for browser-tier callers on **every table the definition touches**, including join tables **and** a materialized-query result table. On an MQ, set it on the `materializedQueries` entry (default `false`) — do not PATCH table-options. Independent of ADRA: RLS/PLS still filter rows.

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

## Paging, distinct, and count

These fields exist on the definition. They were missing from this page.

**`limit` / `limitParam`.** Every named query needs a numeric `limit` cap (`NAMED_QUERY_UNCAPPED_LIMIT` at apply). `limitParam` is the **name** of a parameter the caller may send to choose a smaller page size; it does not replace the cap.

**`offset` / `offsetParam`.** Same pattern for offset. `offsetParam` requires a positive offset cap. A non-zero offset (literal or bound param) **disqualifies subscribe** (`NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`). HTTP execute still pages.

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

**`count: true`.** The response includes `totalMatches` (HTTP; omitted when the definition has no `count`) so a footer can render "1–25 of 412" from one round trip. Subscribe snapshots set `total_matches` on `snapshot_complete`. Count **ignores** limit/offset. Apply rejects a count whose cost is not bounded (`NAMED_QUERY_COUNT_UNBOUNDED`) — joins, `distinct`, or a partitioned table whose WHERE does not cover every partition key with a **required** `eq`/`in`. `POST …/query/count` stays **404** on the data plane.

**`distinct: true`.** Exists. Subscribe refuses it. When every distinct column is a raw partition key, the predicate touches only partition keys, at least one partition key is constrained by `eq`/`in`, and the partition directory is complete and under 10 000 tuples, the engine answers from directory metadata with **zero segment scan**. `stats.distinctServedFromPartitionMetadata` is `true` on that path (omitted when false). That is the "which sources exist for this ticker?" query. Full rule: [browser-tier read limits](browser-tier-read-limits.md#partition-filter-rule).

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
  http://localhost:5434/api/databases/trading/named-queries/equity.quoteByTicker/query?format=columnar \
  -d '{"args":{"ticker":"AAPL"}}'
```

Columnar success looks like any other query result. Unknown name → `404 NAMED_QUERY_NOT_FOUND`. On the **data-plane listener**, a missing token or an unentitled caller (`mk_anon_*`, user JWT without `db_reader`) is the **same** 404 — not 401/403 — so names are not enumerable. The **admin listener** still returns 401 (`AUTH_TOKEN_MISSING`) / 403 (`AUTHORIZATION_DENIED`). Bind failure → `400 NAMED_QUERY_BIND_FAILED` (or `NAMED_QUERY_PARAM_REQUIRED`) **before** the engine runs.

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
    { "columns": ["ticker", "bid"], "types": ["String", "Decimal"], "data": [["AAPL", 189.2]], "rowCount": 1 },
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
- Definitions using `joins`, `selectExpr`, `distinct`, or a non-zero offset are refused with `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`. HTTP execute of those still works — only the live path is restricted.
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

---

## Authorization (always underneath)

Every named-query execute, batch element, mutation, and subscribe applies **the caller's** PLS and RLS. A bug in a named query cannot leak across a tenant boundary **if ADRA is intact** — which is why fail-closed resolvers and the [access-surface diff](access-surface.md) exist.

Service keys (`mk_svc_*`) keep the audited bypass. They are for backends, not browsers.

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
| Batch HTTP 200 with a slot `code` | Per-element failure | Handle positional errors; do not retry the whole envelope unless you mean to |
| `NAMED_QUERY_DEPRECATED` warning | Name sunset pending | Log it; migrate callers to the replacement name before `sunsetAt` |
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` | Data-plane subscribe without `"name"` | Call `subscribe(name, args)` |
| Data-plane `POST /query` 404 | Listener allowlist | Use named-query execute, or connect the service key to the **admin** listener |

---

## Not in this release

- SQL-ish authoring surface (definitions are JSON `QueryMessage` templates).
- Runtime registration of definitions.
- Named-mutation batching (the batch envelope is **read-only**).
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
