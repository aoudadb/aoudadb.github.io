---
title: "Freshness and replica consistency"
nav_order: 8.5
parent: "Guides"
---

# Freshness and replica consistency

Document status: Complete (P38 S07)
Last updated: 2026-08-21

Aouda issues **one** consistency token on every write, returns it on every read, and accepts it on every read. A node that has not applied that position does not answer — it waits, forwards, or returns a typed error. Freshness is also a **declared** property of a named-query alias, reviewable in `aouda schema diff --access`.

**Wire contract:** [HTTP API — Consistency tokens](../reference/http-api.md#consistency-tokens-and-freshness). **ADR:** [0042](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0042-freshness-and-replica-consistency.md).

This is a **lower bound** (`AtLeast`), not a point-in-time pin. Aouda retains no row versions. Cross-read consistency is the named-query [batch envelope](named-queries.md#batch-one-snapshot).

---

## Start here

| I want to… | Go to |
|---|---|
| Understand the token | [The one token](#the-one-token) |
| Read from a regional replica without losing my write | [Managed regional replica](#managed-regional-replica) |
| Declare a per-query staleness budget | [Declared freshness](#declared-freshness-on-the-alias) |
| Carry the token in TypeScript or C# | [SDKs](#sdks) |
| See what can still go wrong | [Caveats](#caveats) |
| Map an error code | [Troubleshooting](#troubleshooting) |

---

## The one token

The token is an opaque, sortable, 42-character lowercase hex string. Callers compare tokens for ordering and never parse them. Internally it carries a database fingerprint, a replication **epoch**, and the WAL byte offset.

| Surface | How |
|---|---|
| Write response | JSON `token` + header `X-Aouda-Token` |
| Read response | Same (the position the node had applied when it read) |
| Next read | Header `X-Aouda-Token` or query `?at_least=` (query **wins** if both are sent) |
| Fetch current | `GET /api/databases/{db}/token` |

```http
POST /api/databases/appdb/tables/orders/rows HTTP/1.1
Content-Type: application/json

{ "database": "appdb", "rows": [{ "id": 1, "status": "open" }] }
```

```http
HTTP/1.1 200 OK
X-Aouda-Token: 01a1b2c3d4e5f60708090a0b0c0d0e0f10111213

{ "rowsInserted": 1, "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213" }
```

```http
POST /api/databases/appdb/query?at_least=01a1b2c3d4e5f60708090a0b0c0d0e0f10111213 HTTP/1.1
Content-Type: application/json

{ "database": "appdb", "table": "orders" }
```

Empty `at_least` or `X-Aouda-Token` is `TOKEN_MALFORMED`. This is **not** the fencing header `X-Aouda-Current-Token` (an integer on writes in a replica set).

Default read preference remains **`Primary`**. Replica reads are *safe when you present a token*; they are not turned on for existing traffic.

---

## Managed regional replica

Pointing reads at a nearby secondary used to trade latency for a silent bug: the user's own write could be invisible. With the token, that read either sees the write, waits up to `waitMs` (default **250 ms**), or returns a typed error. It never returns the pre-write state.

The gate on the receiving node, in order:

1. **Caller token** — if presented and not yet applied, wait then `onExceeded`. Honoured regardless of the staleness budget.
2. **Budget** — `maxLagBytes` / `maxStalenessMs` (`MaxLagSeconds`) on a non-primary.
3. **Answer**, stamping the observed token.

`onExceeded`:

| Value | After the wait |
|---|---|
| `wait` (then timeout) | HTTP 409 `TOKEN_UNSATISFIED` |
| `fetchPrimary` (default) | HTTP 421 `TOKEN_FETCH_PRIMARY` — **the server does not proxy**; the client retries against the current primary from topology |
| `fail` | HTTP 409 immediately (no wait) |

On the **primary** a token that is already covered is a no-op. `Standalone` serves every preference.

---

## Declared freshness on the alias

The budget lives on the named-query **alias**, outside the content hash. Changing it does not break a client pinned to the hash. Two aliases may share one hash with different budgets (dashboard vs order entry).

```json
"namedQueries": {
  "portfolio.positionsWithQuotes": {
    "table": "Position",
    "where": { "and": [{ "column": "accountId", "op": "eq", "param": "accountId" }] },
    "select": ["symbol", "quantity", "lastPrice"],
    "limit": 500,
    "freshness": {
      "readYourWrites": true,
      "maxLagBytes": 4194304,
      "maxStalenessMs": 2000,
      "waitMs": 250,
      "onExceeded": "fetchPrimary"
    }
  }
}
```

| Rule | Behaviour |
|---|---|
| Bare hash (no `alias`) | Fail-safe: `readYourWrites: true`, primary-only. `X-Read-Preference: Secondary` is 400 `FRESHNESS_LOOSENED` |
| Call site | May **tighten** (`?maxStalenessMs=500` on a 2 s alias). May **not** loosen (400 `FRESHNESS_LOOSENED`) |
| `alias` / hash mismatch | 400 `NAMED_QUERY_ALIAS_MISMATCH` |
| `serveStaleAndRevalidate` | Schema-apply and request 400 `FRESHNESS_CONTRACT_INVALID` (no local copy yet) |
| Omitted `waitMs` | 250. Cap 30 000; over-cap is `FRESHNESS_CONTRACT_INVALID` |
| Loosen in a branch | `aouda schema diff --access` reports `freshness` / `widen` and exits 1. A tightening is `narrow` and does not fail CI |

Pass the alias as `?alias=`, header `X-Aouda-Named-Query-Alias`, or body `alias` (query wins).

---

## SDKs

Both `Aouda.Client` and `@aouda/client` capture `X-Aouda-Token` after every data-plane response and present the last-observed value on the next request. The store is **injectable**. The default is in-memory **per client instance**.

### TypeScript

```ts
import { AoudaClient, MemoryConsistencyTokenStore } from "@aouda/client";

const store = new MemoryConsistencyTokenStore(); // share this across instances

const client = new AoudaClient({
  serverUrl: "http://localhost:5433",
  database: "appdb",
  consistencyTokenStore: store,
});
await client.connect();

await client.table("orders").insert({ id: 1, status: "open" });
// subsequent reads send X-Aouda-Token automatically

const pinned = await client.table("orders").atLeast(store.get("appdb")!).execute();
const current = await client.getConsistencyToken();
```

### C#

```csharp
using Aouda.Client;
using Aouda.Client.Consistency;

var store = new MemoryConsistencyTokenStore();
await using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "appdb",
    ConsistencyTokenStore = store,
});

await client.GetTable("orders").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1L, ["status"] = "open"
});

var rows = await client.GetTable("orders")
    .AtLeast(client.GetObservedConsistencyToken()!)
    .ToListAsync();

var current = await client.GetConsistencyTokenAsync();
```

Subscribe `snapshot` / `change` / heartbeat carry the same `token` string. Hand it to an HTTP read or to `at_least` on subscribe. `resume_from` stays the change-event sequence.

---

## Caveats

These are load-bearing. Do not treat replica reads as "always current" because a token exists.

### Scale-out — the default store is not enough

The default in-memory store is **insufficient for a horizontally scaled application tier**. Recreating the client (new process, new pod, new tab) **loses** read-your-writes unless you inject a **shared** store (Redis, a cookie you round-trip, an Aouda table — application-owned). Aouda does **not** ship a Redis adapter. A test asserts the recreate-without-shared-store failure ([gate 13](https://github.com/aoudadb/aouda/blob/main/docs/dev/P38-Phase-Acceptance.md)).

The **application** holds the token, not the engine. For a BFF: inject one store (or put the string on a cookie/header you name). For a browser talking to the data plane: persist `get()` after writes and `observe()` on load. The SDK **never** sets `Set-Cookie`.

### Clock skew — seconds are measured, not magic

`maxStalenessMs` / `MaxLagSeconds` compare the replica's clock to `commitUtcTicks` in the log. Time sync is an **operator requirement**. Observed skew is a metric. **Time is never the read-your-writes gate** — that is the token.

### `MaxLagSeconds` changed meaning

It used to be lag-bytes ÷ 1 MB/s (so `MaxLagSeconds = 5` meant "lag below 5 MB"). It is now measured staleness. If you tuned the old knob as a byte bound, set `MaxLagBytes` instead.

### `w:1` failover is loud

A write acknowledged with default write concern can be lost if the primary dies before replicating. Presenting that token after promotion returns **`TOKEN_EPOCH_SUPERSEDED` (409)**. It does not wait forever, and it is not satisfied because the new primary's byte offset later grew past that number. Strengthen write concern if the caller must read the write after a failover.

### MQ watermark

A node can be fully caught up while a materialized query has not incorporated the write. A token-bearing MQ read waits on the **MQ's** watermark, not the node's.

### Token leak

The 42-hex string encodes epoch and position. Write volume is visible to anyone who sees the token. A coarsened encoding is **not scheduled**.

### A read can block

When a token or lag budget is in play, the read may wait up to `waitMs` (default 250 ms) before `onExceeded`. Existing traffic with neither is unchanged.

### Hub cannot provision the replica yet

This engine work makes a regional replica *safe*. Hub region-aware scheduling (`CP-B4`) is a commercial dependency, not shipped here.

---

## Not in this release

- Local materialization tier (BL-164)
- `serveStaleAndRevalidate` as a real `onExceeded` action
- MVCC / true `AsOf` point-in-time reads
- A packaged distributed token store
- Re-keying `resume_from` onto the token (BL-169)

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| 400 `TOKEN_MALFORMED` | Corrupt, empty, or wrong-version string | Obtain a new token from a write or `GET …/token`. Do not retry the junk |
| 400 `TOKEN_FOREIGN_DATABASE` | Token issued for another database | Same; tokens are per database |
| 409 `TOKEN_EPOCH_SUPERSEDED` | Failover lost the write, or future term | Do not retry the same token; write again or fetch `GET …/token` |
| 409 `TOKEN_UNSATISFIED` | Token or budget unmet after `waitMs` (or `onExceeded=fail`) | Retry later, or use `fetchPrimary`, or read the primary |
| 421 `TOKEN_FETCH_PRIMARY` | Replica declared `fetchPrimary` | Retry against the current primary (`GET /admin/replication/topology`). Distinct from 421 `MISDIRECTED_REQUEST` (wrong **role**) |
| 400 `FRESHNESS_LOOSENED` | Call site weaker than the alias, or Secondary on a bare hash | Drop the looser param, or pass `alias`, or use Primary |
| 400 `FRESHNESS_CONTRACT_INVALID` | Unknown `onExceeded`, `waitMs` out of range, `serveStaleAndRevalidate` | Fix the contract. Default wait is 250; cap is 30 000 |
| 400 `NAMED_QUERY_ALIAS_MISMATCH` | `alias` does not resolve to the path hash | Send the alias that belongs to that hash |
| Recreated client "forgets" the write | Default in-memory store | Share the store or persist the string ([scale-out](#scale-out--the-default-store-is-not-enough)) |
| Replica read "about 5 seconds stale" but rows are huge | Old `MaxLagSeconds` was a byte threshold | Re-tune; use `MaxLagBytes` if you meant bytes |
| MQ read misses a write the node has | MQ maintenance lag | Wait or refresh; the MQ `token` is the watermark |
