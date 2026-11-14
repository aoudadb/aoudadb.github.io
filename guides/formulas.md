---
title: "Formulas"
nav_order: 12.5
parent: "Guides"
---

# Formulas: computed cells in ordinary tables (**ADR 0072, next train**)

Document status: written for the next train. Everything on this page is **new** and marked **(ADR 0072, next train)**; none of it is in a
released build.

A table may declare an **`Expression` column** that drives another column of the same table. In a row whose formula is null the driven
column is an ordinary **input**, written like any value. In a row with a **formula** — an expression that may read other rows, of this
table or of others — the database computes the driven column and keeps it current whenever a row the formula reads changes. A P&L, a
budget, a pricing sheet: inputs and formulas live together, one number per row, in a table you own, query, secure and subscribe to like
any other.

**On this page:** [The model](#the-model-on-one-screen) · [The column](#the-column) · [Input and formula rows](#input-rows-and-formula-rows) ·
[Writing a formula](#writing-a-formula) · [References](#references) · [What a formula may contain](#what-a-formula-may-contain) ·
[Types](#types-the-driven-column-decides) · [When values change](#when-values-change-eventual-consistency-and-tokens) ·
[Null and explain](#a-cell-that-cannot-be-computed-null-and-explain) · [Live](#live-subscriptions) · [Security](#security) ·
[DDL](#changing-the-schema) · [Restart, replicas, branches, backup](#restart-replicas-branches-and-backup) ·
[Limits](#limits-and-what-is-not-there) · [Known issues](#known-issues) · [Troubleshooting](#troubleshooting)

Related: [Build a live financial model](financial-model.md) (a walk-through of everything here) ·
[HTTP API: explain](../reference/http-api.md#explain-a-formula-cell) · [Expression nodes](../reference/http-api.md#expression-node-format) ·
[Freshness](freshness.md) · [Real-time streaming](real-time.md) · [Materialized queries](materialized.md) · [.NET client](../clients/dotnet.md#8c-formula-tables-adr-0072-next-train) ·
[TypeScript client](../clients/typescript.md#13a-formula-tables-adr-0072-next-train).

---

## The model on one screen

(**ADR 0072, next train**)

```json
"pnl": {
  "columns": {
    "Field":   { "type": "String",     "primaryKey": 1 },
    "Period":  { "type": "Int32",      "primaryKey": 2 },
    "value":   { "type": "Decimal", "precision": 18, "scale": 2, "nullable": true },
    "formula": { "type": "Expression", "nullable": true, "drives": "value" }
  }
}
```

| Field | Period | value | formula |
|---|---|---|---|
| Revenue | 2026 | 1000.00 | |
| Cost | 2026 | 600.00 | |
| Profit | 2026 | 400.00 | `Revenue − Cost` |
| Tax | 2026 | 88.00 | `round(Profit × 0.22, 2)` |

- **Revenue and Cost are input rows** (no formula). Typing 1000 into Revenue is an ordinary update of `value`.
- **Profit and Tax are formula rows.** The database keeps their `value` current; a hand-written value there is refused.
- **Everything else is the table's**: read it, query it, join it, subscribe to it, put a row condition on `Field` or `Period`, grant it,
  back it up, build a materialized query over it, reference it from another table's formula.

(`Revenue − Cost` is notation for this page. On the wire a formula is [expression JSON](#what-a-formula-may-contain); the SDKs have
builders that write it.)

**Formula or materialized query?** A [materialized query](materialized.md) maintains a **set of rows** from a query (joins, groups,
aggregates). A formula maintains **one value in one row** from other values. They compose: a formula may read a row of a materialized
query's result — that is how a `SUM` over many rows becomes a formula's input — unless that query is built over a formula table (below).

---

## The column

(**ADR 0072, next train**) Declare an Expression column with `"type": "Expression"` and the column it drives in `drives`. Over HTTP
(`POST …/tables`, `POST …/tables/{name}/columns`):

```json
{ "name": "formula", "type": "Expression", "drives": "value" }
```

In a [schema document](schema.md#columndefinition-entry-in-columns) the same column is
`"formula": { "type": "Expression", "nullable": true, "drives": "value" }` — a document must say `nullable: true` (it is compared with the
server's export, which says it); over HTTP and in the SDKs an Expression column is nullable whether or not you say so. A column listing,
a table's `…/schema` and a schema export show `"type": "Expression"` with `drives`.

A formula is stored as text in the column; to you it is a type. Its rules, each refused with **`400 FORMULA_COLUMN_INVALID`** naming the
rule, when you declare it or later change the table:

| Of | Rule |
|---|---|
| The table | Has a primary key with `Strict` uniqueness (a formula addresses a row by its key), and is an ordinary table: not a materialized query's result, not an edge table. While it has an Expression column its key is not loosened. |
| The Expression column | Nullable; not a primary-key, partition or cluster column; not derived, identity or server time; no default, `unique`, reference or check. |
| The driven column | A nullable scalar column of the same table; not a key, partition or cluster column; not derived, identity or server time; not auto-increment; not a vector or an array; driven by no other Expression column. |

A table may have several Expression columns, each driving its own column (a wide layout: `Year`, `Revenue`, `Cost`, `Profit` with
`ProfitFormula`). A column never **becomes** or **stops being** an Expression column, and an Expression column does not change what it
drives: add a new one and drop the old. A driven column cannot be dropped while it is driven. **Dropping an Expression column** is allowed:
its driven column keeps its last values, now as inputs.

---

## Input rows and formula rows

(**ADR 0072, next train**) Each row is one or the other, by its own Expression value, per Expression column:

- **Formula null — an input row.** The driven column is written like any column, by any write.
- **Formula set — a formula row.** The database computes the driven column. A write that would set the driven column of a row whose
  formula is set **after** the write is refused whole with **`409 FORMULA_VALUE_WRITE_REFUSED`**, naming the row: an update's `set` of the
  value (null included), and an insert, upsert, bulk load or seed row that gives both a formula and a non-null value.
- **A new formula row's value is null until it is first computed**, a moment after the commit.
- **A formula becomes an input** when you write its Expression column to null. The same write may set the value
  (`"set": { "formula": null, "value": 250.00 }`); without one, the row **keeps its last computed value** as its input.
- **An input becomes a formula** when you write a formula into it. Its value is computed again by the next pass.
- **An upsert replaces the whole row**, so an upsert of a formula row leaves its value null until the database computes it again.
- **Deleting a row is ordinary**, input or formula. A formula that read it now reads null. Nothing is "in use": a formula reads a key, not
  a row that must exist.

---

## Writing a formula

(**ADR 0072, next train**) A formula is written by an ordinary write — insert, upsert, update by `where` or by key, a named mutation, a
WebSocket write stream, a bulk load, a schema seed — as the value of the Expression column. In a JSON body it is the expression's JSON
**object**; a string holding that JSON is accepted too.

```json
{
  "database": "finance",
  "columns": ["Field", "Period", "formula"],
  "data": [ ["Profit"], [2026],
            [ { "type": "arithmetic", "op": "-",
                "left":  { "type": "cellRef", "key": { "Field": { "type": "literal", "value": "Revenue" } }, "column": "value" },
                "right": { "type": "cellRef", "key": { "Field": { "type": "literal", "value": "Cost" } },    "column": "value" } } ] ]
}
```

Every write that changes a formula **validates it before it commits**, and a refusal refuses the whole write, naming the row and the rule:

| Check | Refused with |
|---|---|
| It is one valid expression: known nodes and functions, the right number of arguments, no `param`, an arithmetic `op` of `+ - * /` | `400 FORMULA_INVALID` |
| Every reference names a table that exists and may be read by a formula, a column that exists and is not an Expression column, and a key value of the key column's type | `400 FORMULA_REFERENCE_INVALID` |
| Every reference gives the table's **full** primary key (after the [shorthands](#references)), no other column | `400 FORMULA_REFERENCE_NOT_PRIMARY_KEY`, naming the key |
| The type it computes fits the driven column ([Types](#types-the-driven-column-decides)) | `400 FORMULA_INVALID`, saying what to write instead |
| Over every formula in the database, across tables: no cycle | `400 FORMULA_CYCLE`, naming its members in order |
| No chain of formulas, each reading the next, longer than 16 | `400 FORMULA_DEPTH_EXCEEDED` |
| The database holds at most 100 000 formula cells | `400 FORMULA_LIMIT_EXCEEDED` |
| Over HTTP: the writer may read every row the formula reads ([Security](#security)) | `403 FORMULA_REFERENCE_NOT_READABLE` |

**A batch is validated as a whole.** One insert, one bulk load or one seed may add every edge of a cycle at once; it is refused as a whole.
Formula writes are serialized database-wide, so two concurrent writes cannot each add half of a cycle. A write that changes no formula —
an input edit — is not serialized, except an update that changes a formula table's primary-key columns (it moves formulas) and a bulk load
into a formula table (below).

**A formula is a value, never a computation.** A `setExpr` that names an Expression column is `400 FORMULA_INVALID` (write the formula with
`set`). A formula is never written through a [transform](insert-transforms.md) — a route or tee hop, a transform backfill, a bulk load's
transform landing: refused. And a `cellRef` is valid only inside a formula: in a `setExpr`, a derived column, a named query or mutation, a
`selectExpr` or a materialized query's output it is `400 EXPR_CELLREF_NOT_ALLOWED`, well-formed or not. Inside a formula a malformed one
(no column, a key part that is not a non-null literal, a key column named twice) is `400 FORMULA_REFERENCE_INVALID`.

**Bulk load.** A bulk load into a formula table loads that table alone (a multi-table load that includes one is refused) and checks its
formulas as one batch at `:commit`, under the database's formula lock, which it takes only then; a load refused there ends `failed` with the
rule's code. While it streams, the rest of the database's formulas are computed as usual; writes into the table being loaded wait for the
load, as for any table, and so do the formula cells of that table: one woken meanwhile gets its new value once the load commits or is
aborted, and until then a token read past the edit that woke it waits — of any formula table, the maintainer's progress being one number
per database (BL-1505). Keep loads into a formula table short. See [Known issues](#known-issues) for BL-1488.

---

## References

(**ADR 0072, next train**) A formula reads another value with a `cellRef`: a `table`, a `key` of literal values by key column, and a
`column`.

```json
{ "type": "cellRef", "table": "pnl",
  "key": { "Field": { "type": "literal", "value": "Revenue" }, "Period": { "type": "literal", "value": 2026 } },
  "column": "value" }
```

**The key is the table's full strict primary key.** That makes every read a point lookup, never a scan. A table whose key is a surrogate
`Id` cannot be read by `(Field, Period)`: declare the columns you look up by as the primary key. A declared unique key is not served yet
(BL-1405). A key column the table does not have is `400 FORMULA_REFERENCE_NOT_PRIMARY_KEY`. **A row that does not exist reads as null**;
the formula computes again when it appears.

Three **shorthands** keep formulas short, resolved against the formula's own row:

| Shorthand | Means | Example on the row `(Profit, 2027)` |
|---|---|---|
| `table` left out | The formula's own table | `{ "type": "cellRef", "key": {…}, "column": "value" }` |
| A key column left out | The formula row's **own primary-key value** of the column of that name — *relative* | `"key": { "Field": … "Revenue" }` reads `(Revenue, 2027)` |
| `colRef` | The same row's column: `{ "type": "colRef", "col": "Revenue" }` | in a wide layout, `Revenue − Cost` of the same year |

A relative key part comes **only** from the formula row's primary key, matched by column name, also across tables: a `balance` row
`(Retail, RetainedEarnings, 2027)` reading `pnl` with `"key": { "line": … "NetIncome" }` reads `pnl (Retail, NetIncome, 2027)`. So a
formula copied to the next period's row is the same JSON. The stored formula keeps the shorthand as written (a read shows an omitted table
as `"table": ""`); it is resolved again when the row's key changes.

- **A formula reads values, not formulas.** A reference to an Expression column is `400 FORMULA_REFERENCE_INVALID`. A reference to a driven
  column reads its current value — an input, or a value the database computed.
- **What a formula may read:** an ordinary table with a strict primary key, a formula table, or the result of a [materialized query](materialized.md)
  that is **not** built over a formula table (one whose source chain holds a formula table is refused: the dependency between them cannot be
  followed through the query). Not an edge table, not an engine-owned table.
- **A `conditional`'s `when`** reads columns of the formula's own row, as `colRef` does.

---

## What a formula may contain

(**ADR 0072, next train**) The [expression nodes](../reference/http-api.md#expression-node-format) of `setExpr`, with `cellRef`:

| Node | Use |
|---|---|
| `literal` | A constant: `{ "type": "literal", "value": 0.22 }`. |
| `cellRef` | A value of a row, by key ([References](#references)). |
| `colRef` | A column of the formula's own row: `{ "type": "colRef", "col": "Revenue" }`. |
| `arithmetic` | `+ - * /` over two nodes: `{ "type": "arithmetic", "op": "-", "left": …, "right": … }`. |
| `coalesce` | The first non-null argument. |
| `conditional` | `{ "when": <predicate on the row's columns>, "then": …, "else": … }`. |
| `call` | A function, below. |

Not `param`: a formula has no parameters (`400 FORMULA_INVALID`).

**Functions** (`call`): `round(x, digits)`, `roundTo`, `cast(x, type)`, `concat`, `upper`, `lower`, `trim`, `substring` (see
[Insert transforms](insert-transforms.md#call--string-and-rounding-functions)) and these thirteen:

| Function | Arguments | Result |
|---|---|---|
| `min`, `max` | two or more numbers | The smallest or largest. |
| `abs` | one number | The absolute value. |
| `eq`, `ne` | two values | Bool. |
| `gt`, `gte`, `lt`, `lte` | two numbers, or two strings | Bool. |
| `if` | condition, then, else | The chosen branch; only it is evaluated. A null condition takes the `else` branch. |
| `and`, `or` | two or more Bool | Bool; evaluation stops at the first operand that decides it. |
| `not` | one Bool | Bool. |

A null operand makes arithmetic and a comparison null. Comparing two `Date`, `Timestamp` or `Guid` values is an error (the cell is null);
a literal of the wrong kind in a call (`eq("a", 1)`) is refused when the formula is written.

The SDKs build these: C# `FormulaExpr` (`CellHere`, `Cell`, `Col`, `Add`, `Sub`, …) and TypeScript `fx` (`fx.cellHere`, `fx.cell`,
`fx.col`, `fx.add`, …); see the [.NET](../clients/dotnet.md#8c-formula-tables-adr-0072-next-train) and
[TypeScript](../clients/typescript.md#13a-formula-tables-adr-0072-next-train) client pages.

---

## Types: the driven column decides

(**ADR 0072, next train**) The driven column's type is the formula's type. **Nothing is ever rounded for you**, and the type is checked
twice:

1. **When the formula is written**, against the type the formula computes. It must fit without loss: no narrower scale, no fraction into an
   integer, no exact number into a floating column or back, no change of kind. The refusal (`400 FORMULA_INVALID`) says what to write: a
   division of two `Decimal(18,2)` values computes `Decimal(·,6)`, so into a `Decimal(18,2)` column write `round(x, 2)`; a product of two
   of them computes `Decimal(·,4)`; an exact number into a `Double` column, or back, needs `cast`.
2. **When the value is computed**, against the actual number. A value the column cannot hold **unchanged** — too many integer digits, or a
   number outside an integer type's range — makes the cell [null](#a-cell-that-cannot-be-computed-null-and-explain), never a rounded or clamped
   value.

⚠️ **An `Int64` overflow wraps today (BL-1481).** `+`, `-` and `*` on two `Int64` values are not checked: a sum past the largest `Int64`
comes out as a large negative number, not null. Until that is fixed, keep an `Int64` formula well inside the range, or use a `Decimal`
column, whose overflow makes the cell null as it should.

One type per driven column: a different type is a different driven column (or table).

---

## When values change: eventual consistency and tokens

(**ADR 0072, next train**) **A formula's value is written after the commit that changed what it reads, in a separate step**, by the
database's formula maintainer. Your commit never waits for it.

> **There is no atomic read of an input and the values computed from it.** A read right after a write can show the old value (or null, for
> a formula row just written). The window is usually short, and it is not a promise.

What the maintainer does promise:

- **Every formula woken by a commit is computed once**, in dependency order, from the other formulas' new values: a value read in a
  "diamond" (a cell reached two ways) is computed once, never from a stale operand. A value that did not change is not written, and
  publishes nothing.
- A formula is woken by **any** change to a row it reads — an input, another formula's new value, a row created or deleted, in any table —
  and by a write to its own row.
- A **derived column over a driven value** recomputes with it; the table's **checks** apply to the computed value (see [below](#a-cell-that-cannot-be-computed-null-and-explain)).
- A **concurrent write** to another column of a formula row is never lost; a formula changed while its value was being computed gets no value
  from the old formula.

**To read your own write, read with its token.** Every write answers a consistency token (`X-Aouda-Token`, or `token` in the body). A read
of a table that has an Expression column with `at_least=<token>` is answered once the maintainer has **recomputed every commit up to the
token** — this holds for every read of such a table, input rows included: an input edit's token waits until the formulas over it have
caught up. A commit that left a value unchanged satisfies it too.

- The wait is `waitMs` (default 250 ms, at most 30 000). Past it the answer is `409 TOKEN_UNSATISFIED`, never an old value: read again.
- The SDKs send their last write's token on a read by themselves and use the server's default wait; neither retries a `409
  TOKEN_UNSATISFIED`, so read again in a short bounded loop (the [guide](financial-model.md#step-4-read-the-statement) shows one).
- A read with a token on a **replica** is refused `421 FORMULA_TOKEN_REQUIRES_PRIMARY`: a replica computes no formulas, so it cannot judge
  the token. Send it to the primary, or read without a token.
- A read joining a formula table and a [materialized query](materialized.md)'s result is covered only as far as both are. A materialized
  query **built over** a formula table, read with a token, is not yet judged by the formula maintainer (BL-1486).
- A token read of a formula table whose formulas read a materialized query's result waits until the query has applied the write the token
  names and those formulas are recomputed. While a query a formula reads cannot catch up (rebuilding, stale, in error), token reads of
  **every** formula table in the database wait (BL-1505).

See [Freshness](freshness.md#formula-tables).

---

## A cell that cannot be computed: null, and `explain`

(**ADR 0072, next train**) A formula that cannot be computed does not fail anything. Its value is **null**, the other formulas still
settle, and the cell computes again when what it reads changes. There is no error column. The reasons:

- a division by zero;
- a value the driven column cannot hold unchanged (too many digits, out of an integer type's range — but see BL-1481 for `Int64`);
- a check of the table that refuses the value (a check, a unique key or a foreign key);
- a comparison of two dates, timestamps or Guids;
- a reference whose table or column is gone;
- any other error while computing it (a failed `cast`, `abs` of the smallest `Int64`).

A formula reading a null value computes with null (arithmetic over a null is null; `if` takes the `else` branch; `coalesce` skips it).

⚠️ **A check on a driven column should admit null.** A check that refuses null as well as the bad value (`value gte 0` refuses null) cannot
make the cell null; the cell then **keeps its stored value**, and `explain` says why. The check also refuses a new formula row, whose value is
null until it is first computed. Write such a check as "null, or ≥ 0".

**`explain`** says why a cell has the value it has. It evaluates the formula again now and answers its formula, every reference with its
**resolved** key and current value, the value computed now or the **reason** it has none, the stored value, and the formula cells that read
this one:

```bash
curl -s -X POST "$AOUDA/api/databases/finance/tables/pnl/explain" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{ "key": { "dept": "Online", "line": "Margin", "year": 2028 }, "column": "amount" }'
# {"kind":"formula","formula":{…},"references":[{…"value":0.00…},{…"value":-830.00…}],"value":null,"reason":"division by zero.",
#  "storedValue":null,"readBy":[…]}
```

`column` names the driven column or its Expression column. `kind` is `formula`, `input` (the row has no formula) or `noRow`. It needs read
access to the table and shows only what the caller may read: a row the caller may not read answers `noRow`, exactly like a key with no row; a
reference to a row the caller may not read keeps its address and `readable: false`, with `value`, `isFormulaCell` and `error` null; readers
the caller may not read are left out. `explain` takes no consistency token: `value` is computed now, and `storedValue` may not yet show a
write you just made. The full contract is in the [HTTP reference](../reference/http-api.md#explain-a-formula-cell); the SDKs have `ExplainAsync`
(C#) and `table.explain(key, column)` (TypeScript). A grid that wants Excel's `#DIV/0!` calls `explain` for a null formula cell.

---

## Live subscriptions

(**ADR 0072, next train**) A formula table is subscribed to like any table, by its own columns:

```json
{ "type": "subscribe", "id": "retail-2026", "target": "pnl",
  "filter": { "and": [ { "column": "dept", "op": "eq", "value": "Retail" },
                       { "column": "year", "op": "eq", "value": 2026 } ] } }
```

- After an input edit the subscription receives the input's change, then **each formula row that changed, once**, at its final value. A
  recompute that left a value unchanged sends nothing. A value computed before you subscribed is in the snapshot.
- A row's formula is its JSON object in a snapshot page's `data` and in a change's `row` and `prev` (a map in MessagePack).
- A change event's `token` is a valid cover for a later token read: it never claims an input the event's values do not reflect. Tokens are
  not ordered across events: **keep the highest you have seen.** A notice's token (`horizon`, `range_delete`) is not a cover.
- `at_least` on a subscribe of a formula table waits for the maintainer exactly as a read does, with the same `409 TOKEN_UNSATISFIED` and
  `421 FORMULA_TOKEN_REQUIRES_PRIMARY`.

See [Real-time streaming](real-time.md) for the protocol.

---

## Security

(**ADR 0072, next train**) **A formula table's security is the table's own**, set by its owner like any table's: who may read, write and
subscribe, which rows (a row condition, partition-level security, entitlements), the data-plane setting. There is no special grant, role
or default. The [guide](financial-model.md#step-9-who-may-see-and-write-what) puts a department row condition on two formula tables.

One rule is added:

> **Whoever writes a formula must be allowed to read every row it reads.** Without it, a user who may write one table could read any row
> of any table by writing a formula over it and reading its value. With it, a formula discloses only what its writer could have copied by
> hand.

- The server checks it **when the formula is written**, as the writing caller, for every row the formula reads: the caller's read access to
  the table, its row and partition conditions, a materialized query result's source security — exactly what a `/query` of that table by the
  same caller with `where <primary key> = <key>` would return. A refusal is **`403 FORMULA_REFERENCE_NOT_READABLE`**, naming the formula
  row and the reference, never whether the referenced row exists.
- **A row that does not exist yet** is judged on its key when the conditions name only key columns, and refused otherwise.
- **A row the same write gives whole** (an insert's other rows, a bulk load's formula rows) is the writer's own. An update never counts as
  giving a row whole, and a seed's rows count only to the formula each carries.
- What is checked is every formula the write sets or moves: a new or changed formula, one an upsert writes again, a formula row whose key
  change moves its references. An input edit or a removal checks nothing.
- **The embedded engine** has no caller and is trusted, as for every embedded call.

What follows from security being the table's:

- **A formula is visible to whoever may read its row.** There are no private formulas.
- **A value is computed as the database**, once, and shared with everyone who may read its row — even when it reads rows a viewer cannot,
  exactly as a number the writer had copied by hand. **A writer who later loses access** to a row a formula reads does not invalidate the
  formula, as a copied number is not recalled.

---

## Changing the schema

(**ADR 0072, next train**) A DDL that would break a formula's reference is refused with **`409 FORMULA_TABLE_REFERENCED`**, naming the
cells (through the table routes and `schema/apply`, where it is a failed entry):

- dropping or renaming a table a formula reads — or a source table of a materialized query whose result a formula reads. A formula
  table that only its own formulas read, each leaving the `table` out, may be renamed: those formulas follow the rename;
- dropping, renaming or changing the type of a column a formula reads — the driven column included, when formulas read it;
- any change to the primary key of a table a formula reads, or a looser uniqueness; a formula table's own key does not change while it has
  formula cells;
- changing a driven column's type so a formula in it, or one reading it, would no longer [fit](#types-the-driven-column-decides).

Allowed: `TRUNCATE` (formulas reading the table compute from the empty table; a truncated formula table's formulas are gone), deleting rows,
dropping an Expression column (its values stay, as inputs), adding columns.

---

## Restart, replicas, branches and backup

(**ADR 0072, next train**)

- **Every open recomputes every formula**: a restart, a crash recovery, an exact restore. Until that has finished a token read waits (and
  answers `409 TOKEN_UNSATISFIED` if the wait runs out); a read without a token may still show a value from before. At 100 000 formula
  cells the open takes several seconds longer — 7 to 21 s measured on 8 vCPUs, plus about 5 s of recompute (see [Sizing](sizing.md#formula-tables-what-they-cost)).
- A **replica** applies the primary's computed values as ordinary rows and computes none. It serves reads without a token; a token read of a
  formula table is refused `421 FORMULA_TOKEN_REQUIRES_PRIMARY`.
- A node whose formula maintainer is not running refuses a wait for it with **`503 FORMULA_NOT_MAINTAINED`**: a branch, a server in the
  moment before its replication role is resolved, and a promoted node until BL-1441 is fixed. Read there; wait on the primary. The SDKs do
  not retry it: it is the node's state, not overload.
- A **branch** validates formulas written on it like the main database (its index of formulas is built when it opens) but computes none: it
  shows the values it inherited, and a formula written on the branch has a null value (BL-1436).
- **Point-in-time restore**: see BL-1485 under [Known issues](#known-issues) before restoring a database that has formula tables to a point in
  time.

---

## Limits, and what is not there

(**ADR 0072, next train**)

| Limit | Value |
|---|---|
| Formula cells per database | 100 000 (`FORMULA_LIMIT_EXCEEDED`); a write that does not add cells past it is allowed |
| A chain of formulas, each reading the next | 16 (`FORMULA_DEPTH_EXCEEDED`) |
| A reference's key | The full strict primary key. A declared unique key is not served (BL-1405). |
| Token wait | `waitMs` default 250 ms, at most 30 000 ms |

There is no configuration key for any of this.

**Not there, by decision:** a text formula syntax (`= Revenue - Cost`: the SDK builders write the JSON); history of values or formulas;
column-level security (private formulas); a variant type (one type per driven column); ranges or aggregation across rows in a formula (a
`SUM` is a [materialized query](materialized.md) whose result row a formula reads); scenarios; Excel compatibility or `A1` addressing; a
grid or UI component; values computed per viewer.

---

## Known issues

(**ADR 0072, next train**)

- **BL-1481** — `Int64` arithmetic in a formula wraps on overflow instead of making the cell null ([Types](#types-the-driven-column-decides)).
  The same is true of `setExpr` and transforms today.
- **BL-1485** — a point-in-time restore whose target is after a table was created (the table did not exist at the backup) can keep both
  versions of a row updated before the target. On a formula table the database then meets two formulas for one cell and **refuses to open**
  rather than pick one. Restore such a database exactly, or to a point before its formula tables were created, until this is fixed.
- **BL-1441** — after a promotion the promoted node keeps reading through the replica overlay, so it keeps its formula maintainer stopped
  (`503 FORMULA_NOT_MAINTAINED`). Do not rely on a failover for live values.
- **BL-1436** — a branch computes no formulas.
- **BL-1486** — a token read of a materialized query built over a formula table is not judged by the formula maintainer and may answer
  before the formulas have caught up.
- **BL-1482** — a derived-column or server-time DDL on a formula table is not checked for a cycle through the driven value, and does not
  wake the formulas over it.
- **BL-1505** — the formula maintainer's progress is one number per database: while a materialized query that some formula reads cannot
  catch up (rebuilding, stale, in error), token reads of every formula table wait and answer `409 TOKEN_UNSATISFIED`, also of tables whose
  formulas read no query. Read without a token meanwhile, or fix the query.
- **BL-1488** — a bulk load in the default `coerce` validation that names an existing formula row's key can leave a second formula row for
  the cell.
- **BL-1492** — in the C# SDK a typed (POCO) read gives a non-nullable property its type's default for a null: map a driven column as
  `decimal?`, or a null formula cell reads as `0`.
- **BL-1449**, **BL-1450** — in the TypeScript client: two first `subscribe` calls on a fresh client can race the WebSocket opening (wait for
  the first one's snapshot); every HTTP request leaves an `abort` listener on a long-lived client.

---

## Troubleshooting

(**ADR 0072, next train**)

| You see | Why | What to do |
|---|---|---|
| `400 FORMULA_COLUMN_INVALID` | An Expression column's declaration, or a change to its table, breaks a rule of [the column](#the-column) | Read the message: it names the rule |
| `400 FORMULA_INVALID` | Not one valid expression; a `param`; a type the driven column cannot hold without loss; a `setExpr` on an Expression column; a formula through a transform | Fix the formula; for a type, the message says what to write (`round(x, 2)`, `cast`) |
| `400 FORMULA_REFERENCE_INVALID` | A reference names a missing or unreadable table or column, an Expression column, or a key value of the wrong type | Fix the reference; read the driven column, not the formula |
| `400 FORMULA_REFERENCE_NOT_PRIMARY_KEY` | A key that is not the table's full strict primary key | Give every key column (or leave it out to take the row's own), or declare the lookup columns as the key |
| `400 FORMULA_CYCLE` | Formulas would read each other in a loop | Break the loop; the message lists it |
| `400 FORMULA_DEPTH_EXCEEDED` | A chain longer than 16 | Shorten it |
| `400 FORMULA_LIMIT_EXCEEDED` | More than 100 000 formula cells in the database | Remove formulas, or keep inputs as plain values |
| `403 FORMULA_REFERENCE_NOT_READABLE` | The formula reads a row its writer may not read | Reference rows the writer can read, or have a writer who can read them write it |
| `409 FORMULA_VALUE_WRITE_REFUSED` | A hand-written value in a formula row, or a formula and its value in one row | Write the formula as null in the same write to make the row an input |
| `409 FORMULA_TABLE_REFERENCED` | DDL on a table or column a formula reads | Change those formulas first (`TRUNCATE` is allowed) |
| `409 TOKEN_UNSATISFIED` on a read | The formulas did not catch up with your token within `waitMs` — or a materialized query a formula reads cannot catch up (BL-1505) | Read again, with a longer wait for a large model; check the queries your formulas read |
| `421 FORMULA_TOKEN_REQUIRES_PRIMARY` | A token read of a formula table went to a replica | Send it to the primary, or read without a token |
| `503 FORMULA_NOT_MAINTAINED` | This node's formula maintainer is not running (a branch, a role not resolved yet, a promoted node: BL-1441) | Wait on the primary |
| `400 EXPR_CELLREF_NOT_ALLOWED` | A `cellRef` outside a formula | Move it into a formula |
| A formula cell is null | It cannot be computed | `explain` it |
| A formula cell keeps an old value | A check on the driven column refuses null as well as the new value | `explain` it; let the check admit null |
