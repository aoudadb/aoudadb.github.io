---
title: "Materialized Values"
nav_order: 12.5
parent: "Guides"
---

# Materialized Values (**BL-1434, next train**)

Document status: written for the next train. Everything on this page is **new** and marked **(BL-1434, next train)**; none of it is in a released build.

A **materialized value** is one named, computed item (a number, a text, a flag, a date) whose formula reads cells of ordinary tables and other materialized values. Aouda keeps it current as the inputs change. It is the building block for a live model: a profit-and-loss statement, a budget, a pricing sheet. You write inputs as ordinary rows, you define the formula cells once, and you read, wait for or subscribe to the results.

**On this page:** [What it is](#what-it-is) · [Inputs](#inputs-are-ordinary-rows) · [Defining a model](#defining-a-model) · [Value types](#value-types) · [Reading](#reading-a-value) · [Eventual consistency and `waitFor`](#eventual-consistency-and-waitfor) · [Live](#live-subscribe-to-a-cell-or-a-model) · [Security](#security) · [Restart, replicas, backup](#restart-replicas-and-backup) · [Limits](#limits-and-what-is-not-there) · [Troubleshooting](#troubleshooting)

Related: [Materialized Queries](materialized.md) (set-based: rows in, rows out) · [Freshness and replica consistency](freshness.md) · [Real-time streaming](real-time.md) · [HTTP API: materialized value endpoints](../reference/http-api.md#materialized-value-endpoints) · [.NET client](../clients/dotnet.md) · [TypeScript client](../clients/typescript.md).

---

## What it is

(**BL-1434, next train**) Three parts, nothing else:

| Part | What it is | How you touch it |
|------|-----------|------------------|
| **Inputs** | Rows of your own ordinary tables, for example `inputs (Field, Year, Value)` | The ordinary insert, update and delete. There is no special input API. |
| **Definitions** | A cell's name, its declared type and its formula, kept in the table `_mv_definitions` | The definition endpoints, or the `MaterializedValues` API of an SDK |
| **Values** | What each formula currently gives, kept in the table `_mv_values` | Read with the ordinary query, wait for with `waitFor`, or subscribe to |

`_mv_definitions` and `_mv_values` are two ordinary tables with a reserved prefix, `_mv_`. Only the engine writes them. An ordinary write or DDL on either is refused with `403 SYSTEM_TABLE_WRITE_REFUSED`, and no table you create may start with `_mv_` (any case).

A cell is named by a **model** (a namespace such as `pnl`) and a **name** (`Revenue`, `Profit`). A model is not an object of its own: it is the first half of a cell's name, and the unit you read, subscribe to and grant access to.

A small P&L, four of the cells the SDKs' shared test model defines:

```
inputs row  (Field=Revenue, Year=2026)   Value = 1000.00
inputs row  (Field=Cost,    Year=2026)   Value =  400.00

Revenue = the Value of inputs (Revenue, 2026)           ->  1000.00
Cost    = the Value of inputs (Cost, 2026)              ->   400.00
Profit  = Revenue - Cost                                 ->   600.00
Tax     = if(Profit > 0, round(Profit * 0.22, 2), 0)     ->   132.00
```

Edit the `Revenue` input row and `Profit` and `Tax` follow. A cell whose value did not change publishes nothing.

**Materialized value or materialized query?** A [materialized query](materialized.md) maintains a **set of rows** from a query (joins, groups, aggregates). A materialized value maintains **one cell** from a formula. They compose in one direction: a cell may read a row of a materialized query's result, which is how a `SUM` over many rows becomes the input of a cell. A materialized query may be built over `_mv_values`, but no cell may read its result: a `cellRef` to a materialized query whose source chain reaches an `_mv_` table is refused with `400 MV_REFERENCE_INVALID`. A query or filter over `_mv_values.value` sees the value as **text**, so a numeric `ORDER BY` or `SUM` over it is not numeric.

---

## Inputs are ordinary rows

(**BL-1434, next train**) A cell reads one row of a table **by its full strict primary key**. That rule makes a read a point lookup instead of a scan, and it has consequences:

- The table needs a **natural primary key** with `Strict` uniqueness. A table whose primary key is a surrogate `Id` cannot be read by `(Field, Year)`; the definition is refused with `MV_REFERENCE_NOT_PRIMARY_KEY`, and the message names the table's key.
- A reference must name **every** key column (a partial key is refused), each as a literal value.
- Model your input tables with the key you read by: `(Field, Year)` for a long layout (a row per line item and year), or `(Year)` for a wide one (a row per year, a column per line item). Both SDKs have a helper that creates such a table.
- Changing an input is an ordinary update or upsert. The cell follows after the commit; see [Eventual consistency](#eventual-consistency-and-waitfor).

A cell can also read a row of a materialized query's result (a table with a primary key). It cannot read a materialized query built over `_mv_values`.

---

## Defining a model

(**BL-1434, next train**) One request defines any number of cells, **all or none**: if one is invalid, nothing is written and the answer names every fault (a cycle or a chain that is too deep is reported once the other faults are fixed). A request holds at most 10 000 definitions; more is `400 INVALID_REQUEST`.

Defining needs a **definer** credential; see [Security](#security) for which one, because on a server with a server auth database the server key `mk_srv_` is **not** one.

`POST /api/databases/{db}/materialized-values` (the full contract is in the [HTTP reference](../reference/http-api.md#materialized-value-endpoints)). These are the first four of the ten definitions in the C# and TypeScript SDKs' shared test model:

```json
{
  "definitions": [
    {
      "model": "pnl",
      "name": "Revenue",
      "valueType": "Decimal(18,2)",
      "expression": {
        "type": "cellRef",
        "table": "inputs",
        "key": {
          "Field": {
            "type": "literal",
            "value": "Revenue"
          },
          "Year": {
            "type": "literal",
            "value": 2026
          }
        },
        "column": "Value"
      }
    },
    {
      "model": "pnl",
      "name": "Cost",
      "valueType": "Decimal(18,2)",
      "expression": {
        "type": "cellRef",
        "table": "inputs",
        "key": {
          "Field": {
            "type": "literal",
            "value": "Cost"
          },
          "Year": {
            "type": "literal",
            "value": 2026
          }
        },
        "column": "Value"
      }
    },
    {
      "model": "pnl",
      "name": "Profit",
      "valueType": "Decimal(18,2)",
      "expression": {
        "type": "arithmetic",
        "op": "-",
        "left": {
          "type": "cellRef",
          "table": "_mv_values",
          "key": {
            "model": {
              "type": "literal",
              "value": "pnl"
            },
            "name": {
              "type": "literal",
              "value": "Revenue"
            }
          },
          "column": "value"
        },
        "right": {
          "type": "cellRef",
          "table": "_mv_values",
          "key": {
            "model": {
              "type": "literal",
              "value": "pnl"
            },
            "name": {
              "type": "literal",
              "value": "Cost"
            }
          },
          "column": "value"
        }
      }
    },
    {
      "model": "pnl",
      "name": "Tax",
      "valueType": "Decimal(18,2)",
      "expression": {
        "type": "call",
        "fn": "if",
        "args": [
          {
            "type": "call",
            "fn": "gt",
            "args": [
              {
                "type": "cellRef",
                "table": "_mv_values",
                "key": {
                  "model": {
                    "type": "literal",
                    "value": "pnl"
                  },
                  "name": {
                    "type": "literal",
                    "value": "Profit"
                  }
                },
                "column": "value"
              },
              {
                "type": "literal",
                "value": 0
              }
            ]
          },
          {
            "type": "call",
            "fn": "round",
            "args": [
              {
                "type": "arithmetic",
                "op": "*",
                "left": {
                  "type": "cellRef",
                  "table": "_mv_values",
                  "key": {
                    "model": {
                      "type": "literal",
                      "value": "pnl"
                    },
                    "name": {
                      "type": "literal",
                      "value": "Profit"
                    }
                  },
                  "column": "value"
                },
                "right": {
                  "type": "literal",
                  "value": 0.22
                }
              },
              {
                "type": "literal",
                "value": 2
              }
            ]
          },
          {
            "type": "literal",
            "value": 0
          }
        ]
      }
    }
  ]
}
```

Each definition has four fields:

| Field | Meaning |
|-------|---------|
| `model`, `name` | The cell's identity. Case-exact, non-empty, at most 200 characters each, no leading or trailing white space and no control characters. |
| `valueType` | The type the cell holds. **Required.** `Decimal(18,2)`, `Int64`, `String`, ... See [Value types](#value-types). |
| `expression` | The formula, an [expression tree](../reference/http-api.md#expression-node-format). |

### What a formula may contain

| Node | Use |
|------|-----|
| `literal` | A constant. |
| `arithmetic` | `+ - * /` over other nodes. |
| `coalesce` | The first non-null argument. |
| `call` | A function: the existing `round`, `roundTo`, `concat`, `cast`, `upper`, `lower`, `trim`, `substring` (see [Insert transforms](insert-transforms.md)) and the thirteen below. |
| `cellRef` | **Reads a cell.** `{"type":"cellRef","table":"inputs","key":{"Field":{"type":"literal","value":"Revenue"},"Year":{"type":"literal","value":2026}},"column":"Value"}`. The key holds **literal** values only, one for every key column. |

A formula **cannot** contain `colRef` (there is no current row), `param`, or a `conditional` (its `when` always names a column, so it reads a row: use `if`). A `cellRef` anywhere else (a `setExpr`, a derived column, a named query or mutation, a `selectExpr`, a materialized query's output) is refused with `400 EXPR_CELLREF_NOT_ALLOWED`; a malformed one with `400 EXPR_CELLREF_INVALID`.

**Reading another cell** is a `cellRef` to `_mv_values` with the model and the name as the key and `value` as the column: `{"type":"cellRef","table":"_mv_values","key":{"model":{"type":"literal","value":"pnl"},"name":{"type":"literal","value":"Revenue"}},"column":"value"}`. Only the `value` column of another cell may be read, and its type is that cell's declared type.

### The thirteen functions

(**BL-1434, next train**) Beside the existing eight:

| Function | Arguments | Result |
|----------|-----------|--------|
| `min`, `max` | two or more numbers | The smallest or largest. |
| `abs` | one number | The absolute value. `abs` of the smallest `Int64` overflows, which makes an error cell. |
| `eq`, `ne` | two values | Bool. |
| `gt`, `gte`, `lt`, `lte` | two numbers, or two strings | Bool. |
| `if` | condition, then, else | The chosen branch. |
| `and`, `or` | two or more Bool | Bool; evaluation stops at the first operand that decides it. |
| `not` | one Bool | Bool. |

Only numbers, strings and bools compare (`gt`, `gte`, `lt` and `lte` take numbers or strings, not bools). Comparing two `Date`, `Timestamp` or `Guid` cells, with `eq` and `ne` too, is a run-time error, and so an error cell. A literal of the wrong kind in a call (`eq("a", 1)`) is refused when you define. A null operand makes a comparison null; `if` with a null condition takes the `else` branch.

### What is refused when you define

| You send | You get |
|----------|---------|
| A bad name, a `colRef`, a `param`, a result type a cell cannot hold, a type the formula does not fit | `400 MV_DEFINITION_INVALID`; nothing written |
| A `cellRef` to a table, column or cell that does not exist, or a key literal of the wrong type | `400 MV_REFERENCE_INVALID` |
| A key that is not the table's full strict primary key | `400 MV_REFERENCE_NOT_PRIMARY_KEY`, naming the key |
| Cells that read each other in a loop | `400 MV_CYCLE`, naming the members in order |
| A chain of more than **16** cells, each reading the next | `400 MV_DEPTH_EXCEEDED` |
| A cell that already exists (use alter) | `409 MV_DEFINITION_EXISTS` |
| A delete of a cell other cells read, or an alter of its type that they would no longer accept | `409 MV_DEFINITION_IN_USE`, naming the readers |
| A drop or rename of a table a cell reads; any change to its primary key (a key column, read or not, or a looser uniqueness); a drop, rename or type change of a column a cell reads; a drop of a materialized query whose result a cell reads | `409 MV_TABLE_REFERENCED`, naming the cells, through the table routes **and** `schema/apply` (where it is a failed entry in a `200`) |
| An unknown cell on alter, delete, get or explain | `404 MV_DEFINITION_NOT_FOUND` |

`TRUNCATE` of an input table is allowed: the cells recompute from the empty table. Deleting an input **row** that a cell reads is allowed too, and the cells that depend on it go null.

---

## Value types

(**BL-1434, next train**) Every cell declares its type, and the stored `value` is that type's **canonical text**, in the single `value` column of `_mv_values`. The spelling is exact: `Decimal(18,2)`, not `decimal(18, 2)`.

| `valueType` | Canonical text | SDK value (C# / TypeScript) |
|-------------|----------------|-----------------------------|
| `Bool` | `true`, `false` | `bool` / `boolean` |
| `Byte`, `Int16`, `Int32`, `UInt16`, `UInt32` | digits, with a leading `-` when negative; no `+`, no leading zero, no `-0` | `byte`, `short`, `int`, `ushort`, `uint` / `number` |
| `Int64` | the same: `-42`, `9007199254740993` | `long` / `bigint` |
| `UInt64` | digits | `ulong` / `bigint` |
| `Decimal(p,s)` | exactly `s` digits after the point: `1.50`, `0.00`, `-0.05`. `1 <= p <= 18`, `0 <= s <= p` | `decimal` / the canonical `string` |
| `Float32`, `Double` | the shortest text that reads back to the same number, in exponent form for large or small magnitudes (`1E+20`, `5E-324`); `-0` is `0`; no `NaN` or infinity | `float`, `double` / `number` |
| `String` | unchanged | `string` / `string` |
| `Guid` | lower-case, hyphenated | `Guid` / `string` |
| `Date` | `yyyy-MM-dd` | `DateOnly` / `Date` |
| `Timestamp` | `yyyy-MM-ddTHH:mm:ss.fffffffZ` (UTC, seven fractional digits) | `DateTime` / `Date` (millisecond precision; the SDK's `text` keeps the exact form) |

**Nothing is ever rounded for you.** The declared type is checked twice:

1. **When you define**, against the type the formula computes. A type that would lose something is refused with a message that says what to write instead: a `Decimal(18,6)` result into a `Decimal(18,2)` cell tells you to use `round(x, 2)`; an exact number into a floating cell, or back, tells you to use `cast`.
2. **At run time**, against the actual number. A value that does not fit (an `Int16` cell that computes 40000, a decimal with more digits than the cell can hold) is an [error cell](#error-cells), never a rounded or clamped value.

If you want a rounded value, write `round` in the formula. A cell's type is one scalar: arrays and vectors are refused.

---

## Reading a value

(**BL-1434, next train**) A value is a row of `_mv_values`. Three ways to read one:

1. **A query.** The ordinary `POST /api/databases/{db}/query` on `_mv_values`, filtered on `model` and `name`. `/query/count`, a named query and a join side work too.
2. **An SDK call**: `GetAsync` (C#) or `get` (TypeScript), which decodes the text by the cell's type.
3. **A [subscription](#live-subscribe-to-a-cell-or-a-model).**

A value row has these columns:

| Column | Meaning |
|--------|---------|
| `model`, `name` | The cell. |
| `valueType` | The cell's declared type. |
| `value` | The canonical text. Null when the value is null or the cell is an error. |
| `error` | Null, or a text of at most 1000 characters saying why the cell could not be computed. |
| `computedAtPosition` | The log position the maintainer read **before** it looked up the inputs. The value reflects the commits up to there **at least**. |
| `computedAtTerm` | The replication term the value was computed in. |

A cell that has not been computed yet and one that is not defined both read as **no row**; the SDKs return `null` for both (C# `GetAsync<T>` with a non-nullable `T` returns `default(T)` instead, BL-1451: ask for `decimal?` to tell a missing cell from `0`). A cell in a model the caller holds no entitlement for is **not** no row: the read is refused `403 AUTH_ENTITLEMENT_NOT_FOUND` (see [Security](#security)), and the SDKs raise their not-granted error.

There is no route that writes a value and none that reads one: **an input is an ordinary upsert, and a value is read with the ordinary query.**

### Error cells

A formula that cannot be computed (a division by zero, an overflow, a value the declared type does not hold, a comparison of two dates) does not fail the pass. The cell holds `value` null and `error` set to the text, and every other cell still settles. A cell that reads an error cell reads it as **null** and is not itself an error. The `error` clears the next time the cell computes.

In the SDKs an error cell is a value with `IsError` set and the text in `Error`; asking for it as a typed value (`GetAsync<decimal>`) raises a cell error instead of returning a number that is not there.

---

## Eventual consistency and `waitFor`

(**BL-1434, next train**) **A value is written after the commit that changed its input, in a separate step.** Your commit never waits for the model. So:

> **There is no atomic read of an input and the value derived from it.** A read right after a write can return the old value. The window is usually short, and it is not a promise.

To read your own write, wait for it:

1. Every write (an ordinary insert, update or upsert, or an SDK `Set`) returns a **consistency token**: the `X-Aouda-Token` response header, or `token` in the body. A definition call returns it in the header only. The SDKs remember the tokens they have seen.
2. Read `_mv_values` with that token: `POST /query?at_least=<token>&waitMs=3000`. The server answers once the maintainer has **at least** recomputed every commit up to the token. A commit that left the cell unchanged still satisfies it, because the wait is judged by the maintainer's progress, not by the row's position.
3. If the maintainer has not caught up within `waitMs`, the answer is `409 TOKEN_UNSATISFIED`, never an old value. Retry. It is `409` **whatever `onExceeded` says**: `fetchPrimary` does not turn it into a `421`, and `fail` answers `409` at once, without waiting.

`waitMs` defaults to 250 and is capped at 30 000. The SDKs wait up to **5 seconds** by default and accept 0 to 30 seconds. See also [Freshness](freshness.md).

Which tokens are a valid cover for a `waitFor`:

| Token | A cover? |
|-------|----------|
| The token a write returns | Yes |
| The token a definition route returns | Yes |
| The token on a query response | Yes |
| A subscription **snapshot**'s token | Yes. It is the maintainer's progress when the snapshot was read. |
| A subscription **change** event's token on `_mv_values` | Yes. It can lag its own pass, and tokens are not ordered across events: **keep the highest token you have seen.** |
| A notice's token (`horizon`, `range_delete`) | **No** |

A token read on a **replica** (with a read preference that lets a replica serve, such as `readPreference=secondary`) is refused with `421 MV_TOKEN_REQUIRES_PRIMARY`: send it to the primary, or read without a token.

What the maintainer does promise: one pass computes every woken cell once, in dependency order, from its own results. A cell is never computed from a stale operand of the same pass, and no change event carries one. That is a statement about the values among themselves, **not** an atomic read across the input row.

---

## Live: subscribe to a cell or a model

(**BL-1434, next train**) No new message: the ordinary table `subscribe` on `_mv_values` with a filter.

```json
{ "type": "subscribe", "id": "tax", "target": "_mv_values",
  "filter": { "and": [ { "column": "model", "op": "eq", "value": "pnl" },
                       { "column": "name",  "op": "eq", "value": "Tax" } ] } }
```

Leave out the `name` clause to watch the whole model. A change event's row carries `valueType`, `value` (text), `error`, `computedAtPosition` and `computedAtTerm`, and, for an update, `prev`.

- A settle delivers each changed cell **once**, at its final value. A recompute that left the value unchanged sends nothing. A value published before you subscribed is in the first snapshot.
- Events are ordered by `version` **within one subscription**. Nothing is promised between two subscriptions, so sort by `version` if you merge them. A value event's `version` is above every input event it reflects, but an input event with a lower `version` is not necessarily reflected in a later value event: `computedAtPosition` says what a value reflects.
- A grant added while you are subscribed widens the live feed but sends no snapshot of the newly granted model: resubscribe to get it whole.
- Model and cell names in a filter are case-exact.
- `at_least` and `wait_ms` on a subscribe are judged by the maintainer's progress exactly as on a read, with the same `409 TOKEN_UNSATISFIED` and `421 MV_TOKEN_REQUIRES_PRIMARY`.
- Cost, measured: a viewer watching a cell costs one filter evaluation per value event, shared by everyone watching the same cell; a viewer granted a model pays nothing for other models' events; an admin watching N cells costs N evaluations per event; the unfiltered whole-table subscription costs none.

See [Real-time streaming](real-time.md) for the protocol.

---

## Security

(**BL-1434, next train**)

**Which databases are governed.** A database is governed when it is linked to an auth database, when it is one, or, once the server has a **server auth database** (a server started with a root user or with `AOUDA_DEV_ADMIN`), when it is linked to none: the server auth database then governs it. Only a database on a server with no auth at all is open.

**Who may define.** On a governed database, only a caller who holds `db_admin`'s implied access to every row of the database:

- a user holding `db_admin` on the database (on a database the server auth database governs: a server user with `db_admin` on it, such as the server admin, signed in with `POST /api/auth/signin`);
- or the database's own `mk_svc_` service key (a database linked to an auth database has one).

Everyone else gets `403 INSUFFICIENT_PERMISSIONS` (a `ProtocolError`: the code is in `"code"`): a `db_operator`, a reader, a scoped key, an anon key, and **the server key `mk_srv_`**, which is not a definer. A request with no credential is `401`. On an open database the routes are open, as every admin route is. Every definition, alter and delete writes one audit row per cell: `materialized_value_defined`, `materialized_value_altered` or `materialized_value_deleted`.

**Who may read, by default.** On a governed database the first definition creates `_mv_values` and `_mv_definitions` with `auth-db-entitlement` security on the `model` column, with the dimensions `mv_value_model` and `mv_definition_model` and data-plane access off. So:

- A definer (above) reads every model. The server key `mk_srv_` does **not**: without an entitlement it is refused like any reader.
- Anyone else reads **only the models they have been granted**. The owner grants a model with an [entitlement](../auth/authorization.md) on the dimension `mv_value_model` (the key is the model name). A second entitlement, on `mv_definition_model`, shows the formulas in `_mv_definitions`. The existing entitlement routes do it; there is no grant specific to materialized values.
- A reader with no entitlement is refused `403 AUTH_ENTITLEMENT_NOT_FOUND`, as on any `auth-db-entitlement` table, and so is a query whose `where` names a model the reader holds none for. This is an auth error, so the code is in `"error"`, not in `"code"`: `{"error":"AUTH_ENTITLEMENT_NOT_FOUND","message":"Access denied for query on table '_mv_values'. ...","suggestion":"...","detail":"..."}`.
- A later definition never resets what the owner set. The owner can change the tables' security with the ordinary table-options routes. On an open database the tables are plain.

Granting a reader the model `pnl` on a database linked to an auth database, with a definer's credential (the user needs a role on the database, such as `db_reader`, as for any read):

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/<userId>/entitlements \
  -H "Authorization: Bearer <service key or db_admin token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "mv_value_model", "key": "pnl", "level": "read" }'
```

The reader's next query of `_mv_values` filtered on `model = "pnl"` answers `200`. The same call with `"dimension": "mv_definition_model"` lets them read the model's rows of `_mv_definitions`.

**On a database the server auth database governs** (no auth database of its own, the usual development setup) (**BL-1434, next train**). Its readers are server users, so the grant goes through the server auth admin API, `POST /api/auth/admin/users/{userId}/entitlements`, with the same body; `…/auth/admin/users/{id}/entitlements` under `/api/databases/{db}` answers `400` there ("does not have application auth enabled"). Create the server user, give them a role on the database (such as `db_reader`, scoped to it), then grant the model:

```bash
curl -X POST http://localhost:5433/api/auth/admin/users/<serverUserId>/entitlements   -H "Authorization: Bearer <server key mk_srv_, or a server user's token with db_admin on the server auth database>"   -H "Content-Type: application/json"   -d '{ "dimension": "mv_value_model", "key": "pnl", "level": "read" }'
```

- **Who may grant:** a server key (`mk_srv_`), or a server user with `db_admin` scoped `*` (or to the server auth database itself). A server user whose `db_admin` covers only some databases is refused `403 AUTHORIZATION_DENIED`, and nothing is written.
- **The grant applies on every database the server auth database governs**, not only on the one you were thinking of: the server auth database stores a user's entitlements, like their claims, without a database. A model name used on two such databases is granted on both by one entitlement. Use model names that are unique across them, or link a database to its own auth database to keep its grants apart.
- `GET /api/auth/admin/users/{userId}/entitlements` lists a user's entitlements; `DELETE /api/auth/admin/users/{userId}/entitlements/{entitlementId}` revokes one. A revoke ends the user's live subscriptions on the model with `PERMISSION_REVOKED`, and their next read is refused.

**What a value reveals.** A formula reads its inputs **as the database**, not as the viewer. A viewer who may see a value may therefore see a number derived from rows they cannot read. Grant a model to the people who may see its numbers.

---

## Restart, replicas and backup

(**BL-1434, next train**)

- **Every open recomputes every cell**: a clean restart, a crash, an exact restore and a point-in-time restore. Until it has finished, a `waitFor` read waits (and answers `409 TOKEN_UNSATISFIED` if the wait runs out). A value row never claims a position from a different log history: a row stamped with another term, or with a position the log has not reached, is rewritten.
- A **replica** serves `_mv_values` as the primary's replicated rows and runs no maintainer, so it cannot judge a token. A read that a replica may serve (a read preference such as `readPreference=secondary`; with the default `Primary` a replica answers every read `421 MISDIRECTED_REQUEST`) is served without a token and refused `421 MV_TOKEN_REQUIRES_PRIMARY` with one. A definition change on a replica is `503 READ_ONLY` (its write guard). A replica configured with a list of replicated tables must include `_mv_values` to serve values.
- A node that does not maintain values and is not a replica (a branch, a server whose replication role is not yet resolved, or a promoted node, below) refuses `waitFor` and definition changes with `503 MV_NOT_MAINTAINED`. Either way: define and wait on the primary, read anywhere. A standalone server's first values appear a moment after the start, once its role is resolved. The SDKs do not retry a `MV_NOT_MAINTAINED`: it is the node's state, not overload.
- A **branch** serves its parent's flushed values and maintains none.
- Demotion stops the maintainer. **Known limit (BL-1441):** after a promotion, reads on the promoted node still go through the replica overlay (the old primary's rows) and the node's own writes stay hidden. This affects every table, not only `_mv_values`, and is not fixed in this train. Until it is, a promoted node keeps the maintainer suspended: it serves the last replicated values and refuses `waitFor` and definition changes with `503 MV_NOT_MAINTAINED`. Do not rely on a failover to a replica for live values.

---

## Limits, and what is not there

(**BL-1434, next train**)

| Limit | Value |
|-------|-------|
| Cells in a chain, each reading the next | 16 (`MV_DEPTH_EXCEEDED`) |
| Definitions in one request | 10 000 |
| Model or cell name | 200 characters |
| `error` text | 1000 characters |
| Wait | `waitMs` default 250 ms on HTTP, 5 s default in the SDKs, 30 s cap |
| Reference to an input row | The full strict primary key only. A declared unique key is not served (BL-1405). |

There is no configuration key for any of this.

**Not there, and not planned in this release:** a grid or spreadsheet UI; scenarios; ranges or aggregation across rows in a formula (a `SUM` over rows is a [materialized query](materialized.md) whose result row is a cell's input); Excel-style addressing; per-viewer values; partitioning of `_mv_values`; a cost limiter; role-based definers (only the admin and the service key define).

**Known issues** that touch this feature:

- **BL-1441**: promotion, above.
- **BL-1449**: in the TypeScript client, two first `subscribe` calls on a fresh client can race the WebSocket opening, and the second fails with a connection error. Wait for the first subscription's snapshot before starting the second.
- **BL-1405**: a cell reads an input by its full primary key only.
- **BL-1451**: in the C# SDK `GetAsync<T>` with a non-nullable `T` returns `default(T)` for a missing cell.
- **BL-1447**: in the C# SDK a `waitFor` of nearly the client's own request timeout (30 s by default) can race it: the read times out client-side as `AoudaTimeoutException` (not `MaterializedValueNotCaughtUpException`) and is retried up to 3 times, each counted against the circuit breaker. Keep waits well under `AoudaClientOptions.Timeout`. The TypeScript client raises the request timeout above the wait.
- **BL-1450**: in the TypeScript client every HTTP request leaves an `abort` listener on the client's lifetime signal, so a long-lived client's memory grows per request and Node warns `MaxListenersExceededWarning` after 11 requests. A dashboard that polls `get` on one client for hours is the case it hurts.

---

## Troubleshooting

(**BL-1434, next train**)

| You see | Why | What to do |
|---------|-----|------------|
| `400 MV_DEFINITION_INVALID` | Bad name, a row-reading node, an unsupported type, or a type the formula does not fit | Read the message: it names every fault of the batch and what to write instead |
| `400 MV_REFERENCE_INVALID` | A `cellRef` names something missing, hidden or of the wrong key type | Fix the reference |
| `400 MV_REFERENCE_NOT_PRIMARY_KEY` | The key is not the table's whole strict primary key | Reference every key column, or model the table with the natural key |
| `400 MV_CYCLE` | Cells read each other in a loop | Break the loop |
| `400 MV_DEPTH_EXCEEDED` | A chain longer than 16 | Shorten it |
| `404 MV_DEFINITION_NOT_FOUND` | No such cell | Check the model and the name (case-exact) |
| `409 MV_DEFINITION_EXISTS` | The cell exists | Alter it |
| `409 MV_DEFINITION_IN_USE` | Other cells read it | Change or delete the readers first |
| `409 MV_TABLE_REFERENCED` | DDL on a table or column a cell reads | Delete or change the definitions first (`TRUNCATE` is allowed) |
| `409 TOKEN_UNSATISFIED` | The maintainer did not reach your token within `waitMs` | Retry, with a longer wait if the model is large |
| `421 MV_TOKEN_REQUIRES_PRIMARY` | A token read went to a replica | Send it to the primary, or read without a token |
| `503 MV_NOT_MAINTAINED` | This node maintains no values (a branch, a role not yet resolved, a promoted node: BL-1441) | Define and wait on the primary |
| `503 READ_ONLY` on a definition route | The node is a replica | Define on the primary |
| `403 SYSTEM_TABLE_WRITE_REFUSED` | An ordinary write or DDL on `_mv_*` | Set inputs on your own tables; define through the endpoints |
| `400 EXPR_CELLREF_NOT_ALLOWED`, `EXPR_CELLREF_INVALID` | A `cellRef` outside a definition, or a malformed one | Move it into a definition; give literal keys |
| `403 INSUFFICIENT_PERMISSIONS` on a definition route | The caller is not a definer (the server key `mk_srv_` is not one) | Use a `db_admin` user or the database's `mk_svc_` service key; on a database the server auth database governs, a server user with `db_admin` on it |
| `403 AUTH_ENTITLEMENT_NOT_FOUND` reading `_mv_values` (code in `"error"`) | No entitlement on that model (the server key holds none) | The owner grants the model |
