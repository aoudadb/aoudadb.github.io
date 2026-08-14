---
title: "Insert-time transforms"
nav_order: 11
parent: "Guides"
---

# Insert-time transforms and constraints

Document status: Complete (P37)  
Last updated: 2026-08-14

Tier 1 transforms are **declarative**. They run on REST insert/update/upsert and on the WebSocket write-stream path. No user code, no loops, no HTTP calls.

If a hop only normalizes, validates, derives, or routes rows, it belongs here — [division of responsibility](division-of-responsibility.md). If it resolves an ISIN or quarantines a failed lookup, it does not.

---

## Start here

| I want to… | Go to |
|---|---|
| Compute a column at write time | [Derived columns](#derived-columns) |
| Reject bad rows | [Checks](#check-constraints) |
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

`derived` is an expression evaluated at write time. The result is stored and queryable. Expressions reuse the bulk-mutation `SetExprNode` substrate (no second language).

Expressions are `ScalarExprNode` (same substrate as bulk-mutation `setExpr`). The JSON type discriminator is `"type"`: `literal`, `colRef`, `arithmetic` (`+`, `-`, `*`, `/`), `coalesce`, `conditional`, `param`. There is no `round` op in this release — scale in the client or keep the stored value as-is.

```json
{
  "columns": {
    "id": { "type": "Int64", "primaryKey": 1 },
    "qty": { "type": "Int64" },
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

Insert a `kind=quote` row into `Ingest`: it is stored on `TradeQuote` only; subscribers to `Ingest` do not see it; subscribers to `TradeQuote` see one insert event.

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

---

## Not in this release

- Loops, branch trees, or calls out of process (embedded functions / Tier 3).
- Transforms that fire on bulk load without an explicit intent flag (deliberately loud).
- Mixing named mutations into a transform graph.

---

## Related

- [Division of responsibility](division-of-responsibility.md)
- [Bulk load](bulk-load.md)
- [Bulk mutations](bulk-mutations.md) (expression substrate)
- [HTTP API](../reference/http-api.md)
