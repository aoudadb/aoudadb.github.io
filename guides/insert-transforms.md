---
title: "Insert-time transforms"
nav_order: 11
parent: "Guides"
---

# Insert-time transforms and constraints

Document status: Complete (P37)  
Last updated: 2026-08-19

Tier 1 transforms are **declarative**. They run on REST insert/update/upsert and on the WebSocket write-stream path. No user code, no loops, no HTTP calls.

If a hop only normalizes, validates, derives, or routes rows, it belongs here — [division of responsibility](division-of-responsibility.md). If it resolves an ISIN or quarantines a failed lookup, it does not.

---

## Start here

| I want to… | Go to |
|---|---|
| Compute a column at write time | [Derived columns](#derived-columns) |
| Uppercase, trim, concat, round a value | [`call` functions](#call--string-and-rounding-functions) |
| Reject bad rows | [Checks](#check-constraints) |
| Know what happens to the batch when one row fails | [Failure semantics](#failure-semantics-the-batch-fails-the-row-does-not-skip) |
| Send a row to another table | [`route` and `tee`](#route-and-tee) |
| Bulk-load a transformed table | [Bulk load](#bulk-load-is-loud) |
| Enforce unique / FK | [Constraints](#unique-and-references) |
| Delete an ingest service | [Worked example](#worked-example-replace-an-ingest-service) |

---

## Defaults

| Setting | Default |
|---|---|
| Derived / checks / transforms | Absent — existing tables unchanged |
| Mix `route` and `tee` on one table | Schema-apply error |
| Cycles (`A → B → A`) | Schema-apply error (`SCHEMA_TRANSFORM_CYCLE`) |
| Bulk load into a compute-bearing table | **Rejected** unless `applyTransforms` or `preTransformed` |
| Unique / `references` | Opt-in per column; enforced on REST, write-stream, and embedded |

**Invariant (I4):** one committed physical row produces exactly one change event, on the table that now contains it.

- **`route`** — the row lands in **one** target. One row stored, one event (on the target). The source does not keep it.
- **`tee`** — the row lands in the source **and** each matching target. Two (or more) rows stored, two (or more) events.

The change stream describes **storage**, not the request. Materialized-query maintenance and WebSocket subscribers both observe this.

---

## Derived columns

`derived` is an expression evaluated at write time. The result is stored and queryable. Expressions reuse the bulk-mutation `SetExprNode` substrate (no second language). Because the value is a physical catalog column, it **is** a legal `orderBy` target — that is the sanctioned computed-sort path until expression `orderBy` exists. See [browser-tier read limits](browser-tier-read-limits.md#no-expression-orderby).

Expressions are `ScalarExprNode` (same substrate as bulk-mutation `setExpr`). The JSON type discriminator is `"type"`: `literal`, `colRef`, `arithmetic` (`+`, `-`, `*`, `/`), `coalesce`, `conditional`, `param`, and `call`.

```json
{
  "columns": {
    "id": { "type": "Int64", "primaryKey": 1 },
    "qty": { "type": "Int64" },
    "rawTicker": { "type": "String" },
    "ticker": {
      "type": "String",
      "derived": {
        "type": "call",
        "fn": "upper",
        "args": [
          {
            "type": "call",
            "fn": "trim",
            "args": [{ "type": "colRef", "col": "rawTicker" }]
          }
        ]
      }
    },
    "qtyCopy": {
      "type": "Int64",
      "derived": { "type": "colRef", "col": "qty" }
    },
    "qtyPlusTen": {
      "type": "Int64",
      "derived": {
        "type": "arithmetic",
        "op": "+",
        "left": { "type": "colRef", "col": "qty" },
        "right": { "type": "literal", "value": 10 }
      }
    }
  }
}
```

Apply rejects unknown ops and caller-supplied values for derived columns (`TRANSFORM_DERIVED_READONLY`). Derived columns re-evaluate on update/upsert of their inputs.

### Identity stamp (`{ "identity": "subject" }`)

`derived` is either a `ScalarExprNode` **or** `{ "identity": "subject" }` — a sibling, not `type: "identity"`. The engine stamps the validated principal (`ClaimTypes.NameIdentifier` / JWT `sub`) on insert/upsert/bulk-load `applyTransforms`.

| Caller | Omits the column | Supplies the column |
|---|---|---|
| User JWT | Stamped as that user | `TRANSFORM_DERIVED_READONLY` (400) |
| Service key | `IDENTITY_STAMP_REQUIRED` (400) | Stored as supplied |

Unknown sources (`claim:…` on a derived identity column that is not bindable, or a misspelled source) fail apply or write with `IDENTITY_SOURCE_UNRESOLVABLE` / `SCHEMA_IDENTITY_COLUMN_NOT_BINDABLE`. Identity in `update` `set` / `setExpr` is not supported.

Worked schema: [write-side fixture](../examples/p43-write-side/aouda.schema.json). Authorization for that stamp: [Data authorization](../auth/authorization.md#worked-example--public-or-member--identity-stamp).

### `call` — string and rounding functions

`type: "call"` invokes a function from a **closed allowlist**. Names are lowercase and case-sensitive — `Upper` is unknown, `upper` is the function.

| `fn` | Args | Result |
|---|---|---|
| `upper` / `lower` | 1 | Case-folded with **invariant** culture, not the table's `culture` |
| `trim` | 1 | Leading and trailing whitespace removed |
| `concat` | 1 or more | Arguments stringified and joined |
| `substring` | 2 or 3 | `substring(s, start[, length])`. **`start` is 1-based** and must be ≥ 1; `length` must be ≥ 0. A `start` past the end yields `""` rather than an error |
| `round` | 2 | `round(value, digits)`, `digits` 0–28, **away from zero** (not banker's rounding) |
| `roundTo` | 2 | `roundTo(value, step)`, `step` > 0, away from zero — this is the one for tick sizes and price increments |
| `cast` | 2 | `cast(value, "TypeName")`; the type must be a **string literal** |

```json
{
  "ticker": {
    "type": "String",
    "derived": {
      "type": "call",
      "fn": "upper",
      "args": [{ "type": "call", "fn": "trim", "args": [{ "type": "colRef", "col": "rawTicker" }] }]
    }
  },
  "priceAtTick": {
    "type": "Decimal",
    "derived": {
      "type": "call",
      "fn": "roundTo",
      "args": [{ "type": "colRef", "col": "rawPrice" }, { "type": "literal", "value": 0.05 }]
    }
  }
}
```

Rules worth knowing before you design around it:

- **Null propagates.** If *any* argument evaluates to null, the whole call returns null — it does not throw and does not substitute a default. Wrap in `coalesce` if you want one.
- `cast` accepts only `Int32`, `Int64`, `Int16`, `Byte`, `UInt16`, `UInt32`, `UInt64`, `Double`, `Float32`, `Decimal`, `String`. **`Timestamp`, `Date`, `Guid`, `Bool`, and vector types are not castable.** Float→integer casts truncate toward zero, and a finite value outside the target range is an error rather than a silent wrap.
- There is **no timestamp truncation function**. Bucketing a timestamp to a day or an hour is a partition-key function (`TruncateToDay` and friends) or a materialized-query `groupBy` term, not a derived column.
- Unknown `fn`, wrong arity, or a non-literal `cast` type fails **schema apply** with `SCHEMA_EXPR_UNKNOWN_FUNCTION` — not at insert time. The same validation runs on `namedQueries[].selectExpr` and `namedMutations[].setExpr`.

This is deliberately not a general expression language. It covers normalization — the tidying an ingest hop does — so that hop can be deleted. It does not cover lookups, I/O, or cross-row state; those are still [a service's job](division-of-responsibility.md).

---

## Check constraints

Named predicates. An empty `WhereClause` is rejected at apply. Failure → typed error; the row is not stored.

```json
{
  "checks": {
    "ticker_present": {
      "and": [{ "column": "ticker", "op": "neq", "value": "" }]
    }
  }
}
```

---

## `route` and `tee`

```json
{
  "tables": {
    "Ingest": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1 },
        "kind": { "type": "String" },
        "ticker": { "type": "String" },
        "payload": { "type": "String" }
      },
      "transforms": [
        {
          "name": "to_quotes",
          "kind": "route",
          "when": { "and": [{ "column": "kind", "op": "eq", "value": "quote" }] },
          "to": "TradeQuote"
        },
        {
          "name": "to_trades",
          "kind": "route",
          "when": { "and": [{ "column": "kind", "op": "eq", "value": "trade" }] },
          "to": "Trade"
        }
      ]
    },
    "TradeQuote": { "columns": { } },
    "Trade": { "columns": { } }
  }
}
```

All `transforms` on one table must share one `kind`. `A → B → A` fails at **schema apply**, not as a runtime loop on the commit thread.

Insert a `kind=quote` row into `Ingest`: it is stored on `TradeQuote` only; subscribers to `Ingest` do not see it; subscribers to `TradeQuote` see one insert event. `tee` differs: the ingress row **is** stored, and copies go to every matching target.

`route` predicates must be both **disjoint** and **exhaustive**:

| Rows matched by `when` | Result |
|---|---|
| Exactly one | Routed to that target |
| More than one | `TRANSFORM_ROUTE_AMBIGUOUS` |
| None | `TRANSFORM_ROUTE_UNMATCHED` |

An unmatched row is an **error**, not a fallback — it does not stay on the ingress table. If you want a catch-all, declare it: a last route whose `when` is a condition that always holds, pointing at a quarantine table. `tee` has no such rule; a `tee` that matches nothing simply produces no copy, because the ingress row was stored anyway.

---

## Failure semantics: the batch fails, the row does not skip

This is the operational difference between a transform and the application code it replaces, and it is the thing to design for before you move logic in.

**Transforms are evaluated for the whole batch before anything is written.** The order is derived → checks → route/tee, recursively through hops. The first row that fails any stage throws, and **nothing in the batch is stored** — not the failing row, and not the rows around it. There is no partial success and no per-row skip.

| Error | Raised when | HTTP |
|---|---|---|
| `CONSTRAINT_CHECK_VIOLATION` | A check predicate is false for a row | 400 |
| `TRANSFORM_DERIVED_READONLY` | Caller supplied a value for a derived column | 400 |
| `TRANSFORM_ROUTE_UNMATCHED` | No `route` matched a row | 400 |
| `TRANSFORM_ROUTE_AMBIGUOUS` | More than one `route` matched a row | 400 |
| `SCHEMA_EXPR_UNKNOWN_FUNCTION` | Schema apply: unknown `call` `fn`, bad arity, or invalid `cast` type literal | 400 |

The error names the **table and the check or transform**, not the row index. With a 5 000-row batch, "check `price_positive` on `TradeQuote` rejected the row" does not tell you which one.

Two consequences worth planning around:

- **A service that used to filter rows now has a batch that fails.** Code that quietly dropped a malformed tick and carried on becomes an ingest that rejects 5 000 good ticks because of one. Decide deliberately: keep the permissive filter in the producer and use checks as an assertion about data that should never occur, or move the strictness in and accept that the feeder must handle a 400 by splitting and retrying.
- **Route exhaustiveness is a schema obligation.** A vendor adding a new `kind` value takes ingestion down at the next batch. A declared catch-all route to a quarantine table turns that into rows you can inspect.

There is no dead-letter mechanism inside Aouda. Quarantine is something you build out of an ordinary table plus a catch-all route.

---

## Bulk load is loud

Bulk load **bypasses** the normal commit path (segment ship). Per-row transforms on that path are a throughput disaster, and silently skipping them is worse.

A table with derived columns, checks, or transforms **rejects** `:begin` unless the caller declares intent:

| Flag | Meaning |
|---|---|
| `applyTransforms: true` | Accept the per-row slow path. Post-load MQ rebuild is the **landing-table** set (transitive closure of the transform graph). |
| `preTransformed: true` | Data already matches the target shape. Rebuild MQs for the **loaded** table only. |

Both flags → `BULK_LOAD_TRANSFORM_INTENT_CONFLICT`. Neither → `BULK_LOAD_TRANSFORM_INTENT_REQUIRED`.

HTTP `:begin` body includes the same flags as the C# client and CLI.

**Backfill** is a separate chunked operation (`aouda table backfill`): create the transform first so live writes are captured, then backfill closed partitions, retryable per chunk. Never ClickHouse-`POPULATE`-shaped.

### Write amplification

Transforms are not free. Small batches pay more; large batches amortize. Treat **batch size as a tuning parameter** (the 2 000-row ingest chunk is in the amortized region). Measure before you put a hot path through three `tee`s.

---

## Unique and `references`

```json
{
  "columns": {
    "email": { "type": "String", "unique": true },
    "orgId": { "type": "Int64", "references": "Org.id" }
  }
}
```

Duplicates on a unique non-PK column are rejected across HRA, hot, and cold. `references` is **runtime** RESTRICT validation (not catalog decoration). Enforced on REST, write-stream, and embedded insert/update/upsert. Cost is opt-in per column.

---

## Worked example: replace an ingest service

**Before:** a .NET worker reads a vendor file, drops empty tickers, keeps `quote` and `trade`, copies timestamps, and inserts in 2 000-row chunks.

**After** (derived uses `ScalarExprNode`; `ne` not `neq`; landing tables declare the same columns):

```json
{
  "tables": {
    "VendorTick": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "kind": { "type": "String" },
        "ticker": { "type": "String" },
        "ts": { "type": "Timestamp" },
        "tsUtc": { "type": "Timestamp", "derived": { "type": "colRef", "col": "ts" } },
        "volumeRaw": { "type": "Int64" },
        "volume": {
          "type": "Int64",
          "derived": { "type": "colRef", "col": "volumeRaw" }
        }
      },
      "checks": {
        "ticker_nonempty": {
          "and": [{ "column": "ticker", "op": "ne", "value": "" }]
        }
      },
      "transforms": [
        {
          "name": "quotes",
          "kind": "route",
          "when": { "and": [{ "column": "kind", "op": "eq", "value": "quote" }] },
          "to": "EquityQuote"
        },
        {
          "name": "trades",
          "kind": "route",
          "when": { "and": [{ "column": "kind", "op": "eq", "value": "trade" }] },
          "to": "EquityTrade"
        }
      ]
    },
    "EquityQuote": {
      "dataPlaneAccess": true,
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1 },
        "kind": { "type": "String" },
        "ticker": { "type": "String" },
        "ts": { "type": "Timestamp" },
        "tsUtc": { "type": "Timestamp" },
        "volumeRaw": { "type": "Int64" },
        "volume": { "type": "Int64" }
      }
    },
    "EquityTrade": {
      "dataPlaneAccess": true,
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1 },
        "kind": { "type": "String" },
        "ticker": { "type": "String" },
        "ts": { "type": "Timestamp" },
        "tsUtc": { "type": "Timestamp" },
        "volumeRaw": { "type": "Int64" },
        "volume": { "type": "Int64" }
      }
    }
  }
}
```

The worker becomes: parse the file, `InsertAsync` (or write-stream) in 2 000-row batches. Empty tickers fail the check. Other `kind` values stay on `VendorTick` or fail a tighter check — declare that explicitly. Named queries over `EquityQuote` never see ingest leftovers.

HTTP insert (service key, **admin** listener):

```bash
curl -X POST http://localhost:5433/api/databases/trading/tables/VendorTick/rows \
  -H "Authorization: Bearer $MK_SVC" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "trading",
    "table": "VendorTick",
    "rows": [
      { "kind": "quote", "ticker": "AAPL", "ts": "2026-08-14T12:00:00Z", "volumeRaw": 100 }
    ]
  }'
```

Assert: `GET`/`query` on `VendorTick` does not contain that row; `EquityQuote` does; one change event on `EquityQuote`.

C# (`Aouda.Client`, admin / service key — this is ingest, not a browser):

```csharp
await client.GetTable("VendorTick").InsertAsync(
[
    new Dictionary<string, object?>
    {
        ["kind"] = "quote",
        ["ticker"] = "AAPL",
        ["ts"] = "2026-08-14T12:00:00Z",
        ["volumeRaw"] = 100L,
    }
]);

Assert.Equal(0, await client.GetTable("VendorTick").CountAsync());
Assert.Equal(1, await client.GetTable("EquityQuote").CountAsync());
```

TypeScript (same contract):

```typescript
await client.table("VendorTick").insertMany([
  { kind: "quote", ticker: "AAPL", ts: "2026-08-14T12:00:00Z", volumeRaw: 100 },
]);
```

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Schema apply `SCHEMA_TRANSFORM_CYCLE` | `A → B → A` | Break the cycle; use `tee` only when you mean two stored rows |
| Mix of `route` and `tee` rejected | One kind per table | Split tables or pick one kind |
| Bulk load `BULK_LOAD_TRANSFORM_INTENT_REQUIRED` | Compute-bearing table, no flag | Pass exactly one of `applyTransforms` / `preTransformed` |
| MQ over source empty after adding `route` | Events follow storage | Query/subscribe the **target**, or use `tee` |
| Unique violation on upsert | Existing row counted | Upsert excludes the existing PK from the unique check; a **different** row colliding still fails |
| Slow 100-row ingest | Write amplification | Increase batch size; avoid stacking `tee`s on the hot path |
| `SCHEMA_EXPR_UNKNOWN_FUNCTION` on apply | Unknown `fn`, wrong arity, or a `cast` type that is not a string literal | Check the [allowlist](#call--string-and-rounding-functions); names are lowercase (`upper`, not `Upper`) |
| A derived `call` column is unexpectedly null | Any argument was null; calls propagate null | Wrap the argument in `coalesce` |
| Rounded price is off by one at `.5` | `round` / `roundTo` are away-from-zero, not banker's | Expected; adjust the check or the expectation |
| Whole batch rejected for one bad row | Transforms are all-or-nothing per batch | [Failure semantics](#failure-semantics-the-batch-fails-the-row-does-not-skip) — split and retry, or add a catch-all route |

---

## Not in this release

- Loops, branch trees, or calls out of process (embedded functions / Tier 3).
- Transforms that fire on bulk load without an explicit intent flag (deliberately loud).
- Mixing named mutations into a transform graph.
- Timestamp truncation as a derived `call` — use a partition-key function or a materialized-query `groupBy` term.
- `cast` to `Timestamp`, `Date`, `Guid`, `Bool`, or a vector type.
- A built-in dead-letter queue. Quarantine is a table plus a catch-all `route`.

---

## Related

- [Division of responsibility](division-of-responsibility.md)
- [Adopting Aouda](adoption.md) — where moving ingest logic sits in a migration
- [Bulk load](bulk-load.md)
- [Bulk mutations](bulk-mutations.md) (expression substrate)
- [HTTP API](../reference/http-api.md)
