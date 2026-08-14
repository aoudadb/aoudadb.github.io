---
title: "Division of responsibility"
nav_order: 10
parent: "Guides"
---

# What belongs in Aouda vs a service

Document status: Complete (P37)  
Last updated: 2026-08-14

This page is the published form of ADR 0040 §5. Adopting teams draw service boundaries against it. The failure mode it exists to prevent is **not** a security bug — it is absorbing domain workflow into a schema that Aouda cannot express and should not own.

**Principle:** a network hop earns its existence only if it **changes the data** or **changes the trust**. Relay hops are deleted. Fan-out hops are deleted only after the engine absorbs the amplification (it has: gap, dispatch, conflation, `re_auth`). Domain hops are **split**.

---

## Start here

| I want to… | Go to |
|---|---|
| Run the decision test on a piece of logic | [The test](#the-test-when-it-is-not-obvious) |
| See what moved into Aouda in P37 | [What moves into Aouda](#what-moves-into-aouda) |
| See what must stay in a service | [What stays in application services](#what-stays-in-application-services) |
| Walk a capital-markets example | [Worked examples](#worked-examples) |
| Understand the latency pitch | [Honest caveat](#honest-caveat-about-latency) |

---

## What moves into Aouda

| Work | Mechanism | Why it belongs here |
|---|---|---|
| Shaping, filtering, projecting, authorizing reads for a frontend | [Named query](named-queries.md) | Declarative contract, not a process. It **is** the BFF. |
| Row- and partition-level visibility | ADRA (PLS / RLS) | Enforcement at storage. Doing it in a service re-opens the gap. |
| Column exposure | Named-query `select` | ADRA has no column-level security. |
| Insert-time normalization, validation, derivation, routing | [Transforms](insert-transforms.md) | Data-shaped and declarative. No language, no loop, no network call. |
| Unique, check, referential validation | Engine constraints | When the database is the trust boundary, "the service validates it" is not a control. |
| Fan-out, conflation, delivery guarantees | Streaming (`gap`, `snapshot_complete`, `values_skipped`, `re_auth`) | Amplification absorption. No app service does this better. |
| Simple expression-shaped writes | Named mutations | Already expressible without a general-purpose language. |

---

## What stays in application services

| Work | Example | Why it stays |
|---|---|---|
| Multi-step workflow with compensation | Import → resolve identifier → quarantine unmapped → notify | Orchestration, retries, human-facing state. Not data-shaped. |
| Domain policy that names external concepts | ISIN resolution, instrument mastering, settlement rules | The engine has no model of those systems. |
| Integration with third parties | Market-data vendors, payment providers, email/SMS | Network egress, vendor credentials, vendor failure semantics. |
| Anything requiring a loop, a branch tree, or a call | Iterative reconciliation, pricing models | Embedded functions are deferred. If a named query grows conditionals, **stop**. |
| Cross-service coordination | Sagas, outbox, event choreography | Orchestration stays in services. |

---

## The test (when it is not obvious)

> Can the rule be written as a **predicate**, a **projection**, an **expression over columns of the row being written**, or a **routing decision based on those columns** — with **no loop**, **no branch tree**, **no external call**, and **no state outside the row and the schema**?

- **Yes** → it can move into Aouda.
- **No** → it stays in a service.
- **When in doubt, it stays in a service.** The cost of a hop that should have been deleted is one round trip. The cost of domain logic wrongly absorbed into a schema is a rewrite.

---

## Worked examples

### Yes — delete the equity ingest service

A service that only: drops empty tickers, keeps two of N row kinds, parses an enum, routes two kinds to two tables, normalizes timestamps to UTC, rounds volume, chunks inserts.

| Step | Aouda mechanism |
|---|---|
| Drop empty ticker | Check constraint |
| Keep two kinds | `route` `when` predicate |
| Enum parse | Typed column (invalid insert fails) |
| Route to two tables | `route` / `tee` |
| UTC timestamp | Derived column |
| Round volume | Derived column |
| Chunk 2 000 | Client batch size (tuning parameter of write amplification) |

Full schema: [Insert-time transforms](insert-transforms.md#worked-example-replace-an-ingest-service).

### Yes — delete the quote BFF

A gateway that fans out `GET /positions` then N `GET /quotes/{ticker}` and shapes a portfolio view.

| Step | Aouda mechanism |
|---|---|
| Join positions to quotes | One named query with a join |
| Hide `internalSpread` | Omit it from `select` |
| Authorize the caller | ADRA underneath (invoker rights) |
| Ten unrelated dashboard panels | [Named-query batch](named-queries.md#batch-one-snapshot) (one snapshot) |
| Live last-price at ~10 Hz | Subscribe by hash + `conflate` |

### No — bond-trade import

Resolve ISINs against a mastering service, default publication times from a calendar, quarantine unmapped identifiers, notify operations.

That names **external systems**, has a **workflow** (quarantine + notify), and needs **compensation**. Keep the service. Use named mutations for the final "write the accepted row" step if you want a stable contract; do not try to express ISIN resolution as a derived column.

### No — "just add a loop"

A named query that starts accumulating `CASE` trees to encode a pricing model is the signal to **design an application service** (or wait for embedded functions), not to grow the DSL.

---

## What this means for a service that adopts the model

- A frontend gateway shrinks to an **edge** (TLS, WAF, CDN) — [Direct client access](direct-client-access.md#topology-a-thin-edge) — and stops being a deployment unit that must redeploy when a field is added.
- A streaming relay can be **retired** (gap, complete snapshots, dispatch off the commit lock, conflation, `re_auth` all shipped). Do not retire it by pointing browsers at an engine that still silently dropped events — that era is over, but verify you are on a build that includes P37 S03–S05.
- An ingest service that only normalizes and routes **disappears**.
- A service that owns a workflow **keeps owning it**, and gets shorter because its reads and writes become named artifacts instead of hand-rolled query construction.

---

## Honest caveat about latency

The latency argument for **request/response reads** is weak. An intra-datacenter hop is sub-millisecond. Selling "talk to Aouda directly and save 600 µs" is the wrong pitch.

The argument is strong for:

1. **Streaming** — 3× bandwidth on every tick plus two serialization passes and two queues, if a relay sits in the middle.
2. **Deployment coupling** — thousands of lines redeployed for a field addition.
3. **Round-trip elimination** — composition (one named query with joins) plus the **batch envelope** (independent hashes, one snapshot). Field numbers from pipeline-mode literature (100 statements at 300 ms RTT: 30 s → 0.3 s) are a **client-side** change, not a topology change.

Adopt named queries for (2) and (3), and for the security properties (bounded cost, projection, reviewable artifact). Use the batch API when a view would otherwise issue N independent named-query HTTP calls.

---

## Defaults

| Setting | Default |
|---|---|
| Decision when the test is ambiguous | Stays in a service |
| Named-query identity | Invoker ADRA (no definer / `runAs`) |
| Intra-DC hop as the value case | **Not** the argument — see [latency caveat](#honest-caveat-about-latency) |
| Streaming relay | Retire only on a P37 build (gap, complete snapshots, conflation, `re_auth`) |

---

## Copy-paste: the BFF that becomes a named query

Schema (admin apply) — pin the hash via codegen, then call from the **data-plane**:

```json
{
  "namedQueries": {
    "equityQuoteByTicker": {
      "table": "EquityQuote",
      "limit": 1,
      "select": ["ticker", "bid", "ask"],
      "where": { "and": [{ "column": "ticker", "op": "eq", "param": "ticker" }] },
      "params": { "ticker": { "maxLength": 8 } }
    }
  }
}
```

HTTP (data-plane):

```bash
curl -s -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  http://localhost:5434/api/databases/trading/named-queries/<hash>/query \
  -d '{"args":{"ticker":"AAPL"}}'
```

TypeScript:

```typescript
const quote = await client.namedQueries.execute(equityQuoteByTicker.hash, { ticker: "AAPL" });
```

C#:

```csharp
var quote = await client.NamedQueries.ExecuteAsync(
    EquityQuoteByTicker.Hash,
    new Dictionary<string, object?> { ["ticker"] = "AAPL" });
```

The ingest-service deletion (checks + `route`) is the other copy-paste: [Insert-time transforms](insert-transforms.md#worked-example-replace-an-ingest-service).

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Named query growing `CASE` / loops | Domain logic in the DSL | Stop; put it in a service (or wait for embedded functions) |
| Ten HTTP named-query calls for one view | Independent panels | Use [batch](named-queries.md#batch-one-snapshot), or compose joins if they share a filter |
| Ingest worker still exists for empty-ticker / kind routing | Logic is data-shaped | Move to checks + `route` ([transforms](insert-transforms.md)) |
| ISIN / vendor HTTP inside a derived column | External call | Keep the service; named-mutate the accepted row |
| Selling “saved 600 µs” to the architecture board | Wrong latency pitch | Use deployment decoupling + round-trip elimination |

---

## Not in this release

- Static admissibility of client-composed queries (D-23).
- SQL-ish authoring for named queries (D-24).
- Tier 3 embedded functions (loops, branch trees, outbound HTTP).
- Named-mutation batching (D-28 is read-only).

---

## Related

- [Named queries](named-queries.md)
- [Insert-time transforms](insert-transforms.md)
- [Direct client access](direct-client-access.md)
- [HTTP API](../reference/http-api.md)
