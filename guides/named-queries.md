---
title: "Named queries and mutations"
nav_order: 8
parent: "Guides"
---

# Named queries and mutations

Document status: Complete (P37, P40 S03)  
Last updated: 2026-08-20

A **named query** is a server-authored, versioned, parameterized query template. The client sends a **content hash** plus arguments. It cannot name tables, columns, or operators. Identity is injected from the validated principal — it is never an argument.

That is the BFF (backend-for-frontend) **minus the deployment unit**. A gateway that only shapes, filters, projects, and authorizes reads is a catalog entry reviewed like any other schema change.

Named **mutations** are the write-side mirror (insert / update / delete templates). They run with **invoker rights only** — there is no `SECURITY DEFINER` / `runAs`.

**Wire contract:** [HTTP API — Named queries](../reference/http-api.md#named-queries). **Limits:** [What a browser-tier read cannot do](browser-tier-read-limits.md).

---

## Start here

| I want to… | Go to |
|---|---|
| Author a named query in `aouda.schema.json` | [Schema](#schema) |
| Call it from TypeScript, C#, or curl | [Execute](#execute) |
| Collapse independent reads into one round trip | [Batch](#batch-one-snapshot) |
| Subscribe to live results | [Subscribe by hash](#subscribe-by-hash) |
| Pin hashes in CI / codegen | [Pin hashes](#pin-hashes-codegen) |
| Page with a total ("1–25 of 412") | [Paging, distinct, and count](#paging-distinct-and-count) |
| See what this surface cannot do | [Browser-tier read limits](browser-tier-read-limits.md) |
| Decide if this belongs in Aouda at all | [Division of responsibility](division-of-responsibility.md) |

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
| Identity of a definition | SHA-256 of canonical form | Immutable. Edit → new hash. Old hash keeps working until explicitly removed. |
| Names | Aliases (`name`, `name@version`) | Clients **pin hashes**, not names. |
| `select` / `selectExpr` | **Required** | `*` is refused (`NAMED_QUERY_PROJECTION_STAR`). |
| `limit` | Must be capped in the definition | Uncapped `$limit` fails schema apply. |
| Parameter in identifier position | Illegal | Table, column, operator, sort, projection. |
| Identity as a parameter | Illegal | `NAMED_QUERY_IDENTITY_PARAM` at apply. |
| Persist-time cost | `1 + joinCount` | Caps: 3 joins, cost 8 (`NAMED_QUERY_TOO_MANY_JOINS` / `NAMED_QUERY_COST_EXCEEDED`). |
| Batch size | 32 | Envelope 400 if empty, over cap, or includes a mutation hash. |
| Runtime registration | **Does not exist** | That is the GraphQL APQ trap. |

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

Apply:

```bash
aouda schema apply --file aouda.schema.json
```

Editing a definition produces a **new hash**. The old hash keeps working until you remove it (branch diff reports removal as breaking). Deprecate with `deprecatedAt` / `sunsetAt`; execute still returns 200 plus `warnings: [{ "code": "NAMED_QUERY_DEPRECATED", "hash": "…", "sunsetAt": "…" }]`.

---

## Pin hashes (codegen)

Clients pin hashes generated from the schema at **build time**.

```bash
# TypeScript — emits hashes + Args/Row types
npx @aouda/client generate

# From a running server
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:5433/api/databases/trading/schema/typescript

# C#
aouda generate csharp --file aouda.schema.json
```

There is **no** `POST /named-queries/register`. If build-time generation is painful, fix the tooling — do not add runtime registration.

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

## Execute

`POST /api/databases/{db}/named-queries/{hash}/query`

Body is `{ "args": { … } }` only. No `database` field (the path already has it).

### HTTP

```bash
# Data-plane listener (mk_pub_* or application user JWT). Admin :5433 rejects mk_pub_*
# with AUTH_KEY_LISTENER_MISMATCH.
curl -s -X POST \
  -H "Authorization: Bearer $MK_PUB_OR_JWT" \
  -H "Content-Type: application/json" \
  http://localhost:5434/api/databases/trading/named-queries/aaa…64hex…/query?format=columnar \
  -d '{"args":{"ticker":"AAPL"}}'
```

Columnar success looks like any other query result. Unknown hash → `404 NAMED_QUERY_NOT_FOUND`. Bind failure → `400 NAMED_QUERY_BIND_FAILED` (or `NAMED_QUERY_PARAM_REQUIRED`) **before** the engine runs.

### TypeScript (`@aouda/client`)

```typescript
import { AoudaClient } from "@aouda/client";
import { equityQuoteByTicker } from "./generated/named-queries"; // pinned hash + types

const client = new AoudaClient({
  serverUrl: "https://data.example.com", // data-plane listener
  database: "trading",
  appAuth: { apiKey: process.env.AOUDA_PUB_KEY! }, // mk_pub_…
});
await client.connect();
// after user sign-in, attach the user JWT — do not put identity in args

const { rows } = await client.namedQueries.execute(equityQuoteByTicker.hash, {
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
    EquityQuoteByTicker.Hash,
    new Dictionary<string, object?> { ["ticker"] = "AAPL" });
```

On the data-plane, `POST …/query` (ad-hoc) is **404** for every credential. Service keys that need ad-hoc use the admin listener.

---

## Batch (one snapshot)

`POST /api/databases/{db}/named-queries/batch`

A dashboard of independent panels should not issue N sequential executes. A batch of N hashes returns N **positional** results from **one** read snapshot. Cap **32**.

```json
{
  "queries": [
    { "hash": "<quote hash>", "args": { "ticker": "AAPL" } },
    { "hash": "<overview hash>", "args": { "accountId": 42 } }
  ]
}
```

HTTP **200** means the envelope was accepted. A missing hash or a bind/ADRA failure is:

```json
{
  "results": [
    { "columns": ["ticker", "bid"], "types": ["String", "Decimal"], "data": [["AAPL", 189.2]], "rowCount": 1 },
    { "code": "NAMED_QUERY_NOT_FOUND", "error": "Named query 'bbb…' was not found." }
  ]
}
```

Envelope **400** (no `results`): empty array, more than 32 elements, or a **named-mutation** hash (`NAMED_QUERY_BATCH_MUTATION`).

```typescript
const slots = await client.namedQueries.batch([
  { hash: equityQuoteByTicker.hash, args: { ticker: "AAPL" } },
  { hash: equityStockOverview.hash, args: { accountId: 42 } },
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
    new NamedQueryBatchInput(EquityQuoteByTicker.Hash, new Dictionary<string, object?> { ["ticker"] = "AAPL" }),
    new NamedQueryBatchInput(EquityStockOverview.Hash, new Dictionary<string, object?> { ["accountId"] = 42L }),
});
```

Two sequential single executes under a concurrent writer **may disagree**. The batch must not — that is the correctness upgrade, not only a latency one.

**Composition vs batch:** if panel B's filter is a column from panel A, write **one** named query with joins (composition). Use batch only for **independent** work.

---

## Subscribe by hash

On the data-plane, WebSocket `subscribe` **requires** `hash` (and optional `args`). Ad-hoc `target` + `filter` is `NAMED_QUERY_SUBSCRIBE_REQUIRED`.

```json
{
  "type": "subscribe",
  "id": "sub-1",
  "hash": "<quote hash>",
  "args": { "ticker": "AAPL" },
  "conflate": { "key": ["ticker"], "interval_ms": 100 }
}
```

`conflate` holds only a value `update` visible before **and** after. On an insert-only tick table it does not reduce the event rate. Last-price: a `latestPerKey` MQ, not `quotes` plus `conflate`. See [browser-tier read limits](browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

The server conjoins named-query ∧ PLS ∧ RLS into one effective predicate at subscribe time and **pins** that hash for the connection. Redeploying the alias does not change an in-flight subscription. A permission-version bump re-keys the fan-out bucket; revoked rows stop within one event.

Live `change` `row` / `prev` contain only the declared projection.

Endpoint: `wss://{host}/api/databases/{db}/ws`. Snapshot paging, `snapshot_complete`, `gap`, and `re_auth` are in the [HTTP API WebSocket section](../reference/http-api.md#websocket-streaming-protocol) and [Real-time streaming](real-time.md).

### From the SDKs

Both clients expose this directly — you do not hand-roll the frames. `namedQueries.subscribe` returns the **same** subscription object as table subscribe, so snapshot paging, `gap` → `resume_from`, reconnect, `re_auth`, and `SLOW_CONSUMER` recovery are the paths you already have. Every resend carries the same `hash` + `args`.

```typescript
import { equityQuotes } from "./generated/named-queries"; // pinned hash + types

const sub = client.namedQueries.subscribe(
  equityQuotes.hash,
  { tickers: ["AAPL", "MSFT"] },
  {
    conflate: { key: ["ticker"], intervalMs: 100 },
    onSnapshot: (rows, version) => grid.reset(rows, version),
    onChange: (event) => grid.apply(event),
    onError: (error) => console.error(error),
  }
);

// Or consume it as an async iterator, then:
await sub.unsubscribe();
```

```csharp
await foreach (var evt in client.NamedQueries.SubscribeAsync(
    EquityQueries.EquityQuotes.Hash,
    new Dictionary<string, object?> { ["tickers"] = new[] { "AAPL", "MSFT" } },
    new SubscribeOptions { Conflate = new ConflateOptions(["ticker"], TimeSpan.FromMilliseconds(100)) },
    ct))
{
    // snapshot pages, then snapshot_complete, then change events
}
```

Notes that bite:

- **Pass no `filter`.** The predicate is the definition plus your `args`; there is no client-side filter on a named subscription. `client.table(t).subscribe(…)` still sends `target` and still works on the **admin** listener — it is refused on the data-plane.
- An empty or whitespace `hash` throws before anything is sent.
- A deprecated hash still subscribes. It adds `NAMED_QUERY_DEPRECATED` to `snapshot_complete.warnings`, which raises the named-artifact warning sink **once** and still delivers the snapshot.
- Definitions using `joins`, `selectExpr`, `distinct`, or a non-zero offset are refused with `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`. HTTP execute of those still works — only the live path is restricted.
- `conflate` on an insert-only stream is a no-op (see above).
- Codegen emits one binding per query (`{ hash, name }` plus `Args` / `Row`); the same constant feeds `execute` and `subscribe`. There is no generated `subscribeFoo()` wrapper.

---

## Named mutations

```bash
# Browser-tier JWT on the data-plane. Service keys that mutate via named artifacts
# may use either listener; ad-hoc insert still requires admin.
curl -s -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  http://localhost:5434/api/databases/trading/named-mutations/<hash>/execute \
  -d '{"args":{"id":1,"qty":10}}'
```

```typescript
await client.namedMutations.execute(equityAdjustQty.hash, { id: 1, qty: 10 });
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
| `404 NAMED_QUERY_NOT_FOUND` | Hash not deployed, typo, or `sha256:` prefix mishandled | Apply schema; pin the hash from codegen; hashes are 64 hex |
| `404 TABLE_NOT_FOUND` on a table that exists | Data-plane + browser-tier + `dataPlaneAccess: false` | Set `dataPlaneAccess: true` on every touched table **and** MQ entry (including joins) |
| `400 NAMED_QUERY_BIND_FAILED` | Arg type/constraint | Check `params` (`maxLength`, `min`/`max`, `enum`, `maxItems`) |
| Schema apply `NAMED_QUERY_IDENTIFIER_PARAM` | `$table` / parameterized column | Rewrite; parameters are literals only |
| Schema apply `NAMED_QUERY_UNCAPPED_LIMIT` | Missing `limit` | Set a numeric cap (or a constrained `limitParam`) |
| Schema apply `NAMED_QUERY_COUNT_UNBOUNDED` | `count: true` on a join, `distinct`, or uncovered partition keys | Cover every partition key with required `eq`/`in`, or drop `count` |
| Schema apply `NAMED_QUERY_COST_EXCEEDED` | Too many joins | Split the query or drop a join (cap default 8 = `1 + joins`) |
| Batch HTTP 400 `NAMED_QUERY_BATCH_MUTATION` | Mutation hash in `queries` | Mutations have their own execute route |
| Batch HTTP 200 with a slot `code` | Per-element failure | Handle positional errors; do not retry the whole envelope unless you mean to |
| `NAMED_QUERY_DEPRECATED` warning | Hash sunset pending | Log it; migrate codegen to the new hash before `sunsetAt` |
| Data-plane `POST /query` 404 | Listener allowlist | Use named-query execute, or connect the service key to the **admin** listener |

---

## Not in this release

- SQL-ish authoring surface (definitions are JSON `QueryMessage` templates).
- Runtime registration of definitions.
- Named-mutation batching (the batch envelope is **read-only**).
- Static admissibility of client-composed queries (Firestore-style). Named queries are the browser-tier surface instead.
- Cross-server named-query sharing through Hub (use a shared schema fragment in git).
- OAuth 2.0 authorization code + PKCE — [not shipped](direct-client-access.md#authentication-that-exists).
- Optional predicates (`whenParamPresent`), bounded sort choice, expression `orderBy` — see [browser-tier read limits](browser-tier-read-limits.md). `count` / `totalMatches` **are** shipped (`count: true` on the definition).

---

## Related

- [Direct client access](direct-client-access.md) — listeners, `mk_pub_*`, quotas
- [What a browser-tier read cannot do](browser-tier-read-limits.md) — operators, allowlist, partition rule, conflation caveat
- [Division of responsibility](division-of-responsibility.md) — what belongs in a service
- [Adopting Aouda](adoption.md) — SDK coverage, capacity, and the order to migrate in
- [Access-surface diff](access-surface.md) — CI gate on widening
- [HTTP API](../reference/http-api.md)
- [TypeScript client](../clients/typescript.md)
