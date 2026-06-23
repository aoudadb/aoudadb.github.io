---
title: "Bulk Mutations"
nav_order: 16
parent: "Guides"
---

# Bulk Mutations — UPDATE, DELETE, TRUNCATE, RETURNING, and Computed Columns

_Status: Shipped (P27 — S1 through S7)_
_Primary phases: P27_
_Primary task folder: `docs/tasks/BulkMutations-*.md`_
_ADR: `docs/decisions/0037-bulk-mutation-expressions.md`_

---

## Start Here

| If you want to... | Go to |
|---|---|
| Set `col = col + 1` without reading first | §3 Expression SET values |
| Delete all rows from a table | §4 TRUNCATE |
| Delete at most N rows safely | §5 DELETE with LIMIT |
| Know which rows changed after an update/delete | §6 RETURNING |
| Send multiple updates in one round-trip | §7 Batch mutation |
| Compute columns server-side without storing them | §8 Expression SELECT |
| Run bulk mutations from Studio | §9 Studio bulk mutation panel |
| See working code for common scenarios | §10 Common patterns |
| See all endpoints and client methods | §11 API coverage matrix |
| Diagnose an error | §12 Troubleshooting |

---

## 1. What Bulk Mutations Are (and Why They Exist)

A **bulk mutation** changes zero or more rows that match a WHERE predicate in a single server-
side operation. Aouda has supported WHERE-based `UPDATE` and `DELETE` since its initial
release — this guide covers the extended surfaces added in P27:

| Gap before P27 | P27 solution |
|---|---|
| `SET col = col + 1` required read → compute → write (two round-trips) | Expression SET: `col = col + 1` evaluated server-side |
| Could not `DELETE` more than N rows safely without looping in application code | `LIMIT` on DELETE with `hasMore` sentinel |
| No way to clear a table without a WHERE clause (safety guard blocked it) | Explicit `TRUNCATE` with its own authorization scope |
| No way to see which rows changed without a follow-up query | `RETURNING` clause: returns affected rows in the mutation response |
| Multiple update/delete calls → multiple round-trips | Batch mutation: multiple operations in one HTTP call |
| `SELECT price * 0.9 AS discounted` required client-side math | Expression SELECT: computed columns evaluated server-side |

All mutations go through Aouda's write-ahead log (WAL) and are fully crash-safe and
replication-aware. Expression SET values are resolved to concrete values before the WAL record
is written — no expression AST is ever stored in WAL.

---

## 2. Safety Guardrails

### WHERE is required by default

`UPDATE` and `DELETE` require at least one WHERE predicate. A request with no WHERE clause
returns `400 INVALID_REQUEST`. This guard is enforced at both the client and server.

`TRUNCATE` is the intentional escape hatch for table-wide clears and has its own distinct
authorization scope to prevent accidental use.

### Authorization

- `UPDATE` and `DELETE` require the standard **write permission** (`db_writer` or above).
- `TRUNCATE` requires the additional **`Truncate`** scope — `db_admin` or a role with explicit
  truncate permission. A `db_writer` role without truncate permission receives 403.

### Row-Level Security (RLS) and Partition-Level Security (PLS)

- **RLS write validation** runs on every mutation, including expression SET values. If the
  target column is restricted by a write policy for the caller's role, the mutation returns
  403 regardless of the expression type.
- **PLS** enforces the caller's partition scope on the WHERE clause. Expression SET values
  cannot reference columns outside the caller's authorized partition boundary.

---

## 3. Expression SET Values

### What it does

Instead of reading a value, modifying it on the client, and writing it back, expression SET
lets the server evaluate the mutation in place:

```sql
-- Classic two-round-trip pattern (before P27):
-- 1. SELECT price FROM orders WHERE status = 'active'
-- 2. UPDATE orders SET price = <client-computed> WHERE status = 'active'

-- P27 single-round-trip:
UPDATE orders SET price = price * 0.9 WHERE status = 'active'
```

### Operator map

| Operator | Meaning | Wire representation |
|---|---|---|
| `$inc` | Add a literal to the column | `{ "$inc": N }` |
| `$dec` | Subtract a literal from the column | `{ "$dec": N }` |
| `$mul` | Multiply the column by a literal | `{ "$mul": N }` |
| `$div` | Divide the column by a literal | `{ "$div": N }` |
| `$col` | Copy the value from another column | `{ "$col": "colName" }` |
| `$ifNull` | Return first non-null value (COALESCE) | `{ "$ifNull": ["$colName", fallback] }` |

Operators can be combined with literal values in the same `.update()` call. Literal values
(unchanged keys) continue to use the existing `set` wire field and are unaffected by the new
expression path.

### TypeScript client

```ts
import { createAoudaClient } from '@aouda/client';

const client = createAoudaClient({ serverUrl: 'http://localhost:5433', database: 'shop' });

// Apply 10% discount to all active products
await client.table('products')
  .where('status', '=', 'active')
  .update({
    price:     { $mul: 0.9 },           // price * 0.9
    discount:  { $inc: 10 },            // discount + 10
    updatedAt: new Date(),              // literal — unchanged path
    note:      { $ifNull: ['$note', 'Price adjusted'] }, // COALESCE(note, 'Price adjusted')
  });

// Increment attempts counter and copy lastError from prevError
await client.table('jobQueue')
  .where('status', '=', 'retrying')
  .update({
    attempts: { $inc: 1 },
    lastError: { $col: 'prevError' },   // lastError = prevError
  });
```

### .NET client

```csharp
using Aouda.Client;

var client = new AoudaClient("http://localhost:5433", "shop");

// Fluent expression builder — SetExprBuilder
await client.Table("products")
    .Where("status", "eq", "active")
    .UpdateAsync(set => set
        .Set("price",     s => s.Multiply(s.Col("price"), 0.9))
        .Set("discount",  s => s.Add(s.Col("discount"), 10))
        .Set("updatedAt", DateTime.UtcNow)            // literal is still fine
        .Set("note",      s => s.Coalesce(s.Col("note"), "Price adjusted")));

// Or pass a dictionary for pure literal updates (unchanged API):
await client.Table("orders")
    .Where("id", "gt", 10)
    .UpdateAsync(new Dictionary<string, object?> { ["status"] = "shipped" });
```

### HTTP

The `PATCH /api/databases/{db}/tables/{name}/rows` endpoint now accepts an optional `setExpr`
field alongside the existing `set` field.

```http
PATCH /api/databases/shop/tables/products/rows HTTP/1.1
Content-Type: application/json

{
  "database": "shop",
  "where": {
    "and": [{ "column": "status", "op": "eq", "value": "active" }]
  },
  "set": {
    "updatedAt": "2026-06-23T12:00:00Z"
  },
  "setExpr": {
    "price":    { "type": "arithmetic", "op": "*", "left": { "type": "colRef", "col": "price" },    "right": { "type": "literal", "value": 0.9 } },
    "discount": { "type": "arithmetic", "op": "+", "left": { "type": "colRef", "col": "discount" }, "right": { "type": "literal", "value": 10 } },
    "note":     { "type": "coalesce", "args": [{ "type": "colRef", "col": "note" }, { "type": "literal", "value": "Price adjusted" }] }
  }
}
```

**Response:**

```json
{
  "rowsUpdated": 47,
  "executionMs": 14
}
```

When both `set` and `setExpr` target the same column, the literal `set` value wins.

### How it works internally

1. The server deserializes `setExpr` nodes and validates that all `$col` / `ColRef` references
   name columns that exist in the table schema. Unknown column names → 400.
2. For each matching row, the engine evaluates each expression node against the current row
   snapshot, producing a concrete value.
3. The concrete values are written to the HRA and WAL — no expression AST is stored in the
   WAL. Crash recovery and replication replay see only resolved values.
4. RLS write validation runs on the resolved column name, the same as for literal SET values.

### Limitations

- Division by zero in an expression returns `null` for that row's column value (no exception).
- `$col` can only reference columns in the same row — no subqueries or cross-table references.
- `LIMIT` on `UPDATE` is not supported in v1 (only `DELETE` supports `LIMIT`).

---

## 4. TRUNCATE

### What it does

`TRUNCATE` clears all rows from a table in a single atomic operation, leaving the table schema
intact. It is faster than `DELETE … WHERE 1=1` because it does not evaluate a predicate and
does not log individual row deletions.

```ts
// TypeScript
await client.table('auditLog').truncate();
```

```csharp
// .NET
await client.Table("auditLog").TruncateAsync();
```

```http
POST /api/databases/appdb/tables/auditLog/truncate HTTP/1.1
Content-Type: application/json

{
  "database": "appdb"
}
```

**Response:**

```json
{
  "rowsDeleted": 15000,
  "executionMs": 3
}
```

### Authorization requirement

`TRUNCATE` requires the `Truncate` authorization scope. A `db_writer` role without explicit
truncate permission receives `403 AUTHORIZATION_DENIED`. Grant truncate permission explicitly
or use a `db_admin` credential.

```bash
# Attempt with insufficient permissions → 403
curl -X POST http://localhost:5433/api/databases/appdb/tables/auditLog/truncate \
  -H "Authorization: Bearer <db_writer_token>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "appdb" }'
# → 403 AUTHORIZATION_DENIED
```

### Durability and crash safety

`TRUNCATE` is fully durable. It emits a single WAL record inside a mini-transaction envelope.
If the server crashes immediately after `TRUNCATE` completes, the table will be empty on
restart — the schema is intact and data loss is intentional. Replication propagates the
truncate to all replicas.

Tables with no primary key are correctly truncated. The WAL record is table-wide and does not
depend on primary key values.

### ⚠ Irreversibility warning

`TRUNCATE` is not undoable. There is no `ROLLBACK`. Studio prompts for explicit confirmation.
Use branches if you need a safety net:

```ts
// Create a branch before truncating in production
await client.branches.create({ name: 'pre-truncate-backup', parentBranch: 'main' });
await client.table('auditLog').truncate();
```

### TRUNCATE vs DELETE … WHERE

| Aspect | TRUNCATE | DELETE … WHERE |
|---|---|---|
| Requires WHERE | No | Yes |
| Authorization | `Truncate` scope | Write permission |
| Speed | O(1) | O(rows scanned) |
| Selective deletion | No — always all rows | Yes |
| Schema preserved | Yes | Yes |
| Crash-safe | Yes | Yes |
| WAL records | 1 (table-wide) | 1 per deleted row |
| `hasMore` sentinel | N/A | Yes (when LIMIT used) |

---

## 5. DELETE with LIMIT (Safe Rolling Delete)

### What it does

Adding `.limit(N)` to a `.delete()` call instructs the server to delete at most `N` rows. The
`response.hasMore` field indicates whether additional matching rows remain.

This enables **safe rolling deletes** — a common pattern for archiving or purging large
datasets without overwhelming the WAL or blocking other writes.

### TypeScript client

```ts
const cutoff = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000); // 30 days ago

let hasMore = true;
while (hasMore) {
  const result = await client.table('auditLog')
    .where('createdAt', '<', cutoff)
    .orderBy('createdAt', 'asc')   // deterministic order
    .limit(1000)
    .delete();

  console.log(`Deleted ${result.rowsDeleted} rows`);
  hasMore = result.hasMore;

  if (hasMore) {
    await new Promise(r => setTimeout(r, 100)); // brief pause between chunks
  }
}
```

### .NET client

```csharp
var cutoff = DateTime.UtcNow.AddDays(-30);
bool hasMore = true;

while (hasMore)
{
    var result = await client.Table("auditLog")
        .Where("createdAt", "lt", cutoff)
        .OrderBy("createdAt")
        .Limit(1000)
        .DeleteAsync();

    Console.WriteLine($"Deleted {result.RowsDeleted} rows");
    hasMore = result.HasMore;

    if (hasMore)
        await Task.Delay(100);
}
```

### HTTP

```http
DELETE /api/databases/appdb/tables/auditLog/rows HTTP/1.1
Content-Type: application/json

{
  "database": "appdb",
  "where": {
    "and": [{ "column": "createdAt", "op": "lt", "value": "2026-01-01T00:00:00Z" }]
  },
  "orderBy": [{ "column": "createdAt", "descending": false }],
  "limit": 1000
}
```

**Response:**

```json
{
  "rowsDeleted": 1000,
  "hasMore": true,
  "executionMs": 22
}
```

When `hasMore` is `false`, no more rows match the predicate.

### Ordering and determinism

- When `orderBy` is provided, the engine identifies the lowest-N matching row IDs by ordered
  scan, then deletes exactly those rows. The `limit` count guarantee is strict — never more
  than `limit` rows are deleted.
- When `orderBy` is **omitted**, the engine deletes an arbitrary subset of matching rows. This
  is non-deterministic but still bounded by `limit`. The server emits a warning in this case.
  **Always provide `orderBy` for production rolling-delete loops.**

---

## 6. RETURNING Clause

### What it does

`RETURNING` returns data about the rows that were affected by an `UPDATE` or `DELETE`, in the
same response that reports the mutation result. This avoids a follow-up `SELECT` when you need
to know what changed.

### Semantics

| Operation | RETURNING returns |
|---|---|
| `UPDATE` | **Post-update** values (the new values after the SET is applied) |
| `DELETE` | **Pre-delete** values (the values that existed before deletion) |

### TypeScript client

```ts
// Update sessions and get back which user IDs were affected
const result = await client.table('sessions')
  .where('expiresAt', '<', new Date())
  .update(
    { status: 'expired' },
    { returning: ['id', 'userId', 'expiresAt'] }
  );

for (const row of result.rows) {
  console.log(`Expired session ${row.id} for user ${row.userId}`);
}
console.log(`Total expired: ${result.rowsUpdated}`);
```

```ts
// Delete and capture what was removed
const result = await client.table('sessions')
  .where('expiresAt', '<', new Date())
  .delete({ returning: ['id', 'userId'] });

for (const row of result.rows) {
  await auditLog.record('session_deleted', row);
}
```

### .NET client

```csharp
// Update and capture affected rows
var result = await client.Table("sessions")
    .Where("expiresAt", "lt", DateTime.UtcNow)
    .UpdateAsync(
        new Dictionary<string, object?> { ["status"] = "expired" },
        returning: ["id", "userId", "expiresAt"]);

foreach (var row in result.Rows)
    Console.WriteLine($"Expired session {row["id"]} for user {row["userId"]}");

// Delete with RETURNING
var deleted = await client.Table("sessions")
    .Where("expiresAt", "lt", DateTime.UtcNow)
    .DeleteAsync(returning: ["id", "userId"]);
```

### HTTP

```http
PATCH /api/databases/appdb/tables/sessions/rows HTTP/1.1
Content-Type: application/json

{
  "database": "appdb",
  "where": {
    "and": [{ "column": "expiresAt", "op": "lt", "value": "2026-06-23T12:00:00Z" }]
  },
  "set": { "status": "expired" },
  "returning": ["id", "userId", "expiresAt"]
}
```

**Response:**

```json
{
  "rowsUpdated": 3,
  "executionMs": 9,
  "rows": {
    "columns": ["id", "userId", "expiresAt"],
    "types":   ["Int64", "String", "Timestamp"],
    "data":    [[101, 102, 103], ["u1", "u2", "u3"], ["2026-06-23T11:00:00Z", "...", "..."]],
    "rowCount": 3
  }
}
```

RETURNING responses use the same columnar format as query results. Specify `["*"]` to return
all columns:

```json
{ "returning": ["*"] }
```

### When RETURNING returns 0 rows

When the WHERE predicate matches no rows, `rowsUpdated` / `rowsDeleted` is `0` and `rows` is
an empty columnar result (with the correct column schema but zero rows). This is not an error.

### Performance note

RETURNING uses a secondary scan of the affected row IDs after the mutation. For result sets up
to 10,000 rows, the overhead is typically less than 2× the base mutation time. For very large
RETURNING sets, consider whether a follow-up `SELECT` with the same WHERE clause would be more
appropriate.

---

## 7. Batch Mutation

### What it does

Batch mutation executes multiple update/delete operations against the same table in a single
HTTP round-trip. All operations are applied sequentially in the order given and committed in a
single WAL transaction. Each operation can have its own WHERE predicate and SET values.

This is useful when different subsets of rows need different transformations:

```ts
// Apply different discounts to different customer tiers — one round-trip
await client.table('products')
  .batch([
    {
      where: { column: 'tier', op: 'eq', value: 'gold' },
      update: { price: { $mul: 0.8 } },       // 20% off for gold tier
    },
    {
      where: { column: 'tier', op: 'eq', value: 'silver' },
      update: { price: { $mul: 0.9 } },       // 10% off for silver tier
    },
    {
      where: { column: 'expiresAt', op: 'lt', value: new Date().toISOString() },
      delete: true,                            // purge expired products
    },
  ]);
```

### TypeScript client

```ts
const result = await client.table('orders')
  .batch([
    {
      where: { column: 'status', op: 'eq', value: 'pending' },
      update: { status: 'processing', processedAt: new Date().toISOString() },
    },
    {
      where: { column: 'status', op: 'eq', value: 'processing' },
      update: { attempts: { $inc: 1 } },
    },
  ]);

// result.operationResults[0].rowsAffected — rows updated by operation 0
// result.operationResults[1].rowsAffected — rows updated by operation 1
console.log(result.executionMs);
```

### .NET client

```csharp
var result = await client.Table("orders").BatchAsync(new[]
{
    new BatchOperation
    {
        Where = w => w.Where("status", "eq", "pending"),
        Set = new Dictionary<string, object?> { ["status"] = "processing" }
    },
    new BatchOperation
    {
        Where = w => w.Where("status", "eq", "processing"),
        SetExpr = set => set.Set("attempts", s => s.Add(s.Col("attempts"), 1))
    }
});

foreach (var op in result.OperationResults)
    Console.WriteLine($"Affected: {op.RowsAffected}");
```

### HTTP

```http
POST /api/databases/appdb/tables/orders/rows/batch HTTP/1.1
Content-Type: application/json

{
  "database": "appdb",
  "operations": [
    {
      "where": { "and": [{ "column": "status", "op": "eq", "value": "pending" }] },
      "set":   { "status": "processing" }
    },
    {
      "where": { "and": [{ "column": "status", "op": "eq", "value": "processing" }] },
      "setExpr": {
        "attempts": { "type": "arithmetic", "op": "+", "left": { "type": "colRef", "col": "attempts" }, "right": { "type": "literal", "value": 1 } }
      }
    }
  ]
}
```

**Response:**

```json
{
  "operationResults": [
    { "rowsAffected": 12 },
    { "rowsAffected": 5 }
  ],
  "executionMs": 18
}
```

### When to use batch vs multiple calls

| Prefer batch when... | Prefer individual calls when... |
|---|---|
| Multiple WHERE groups get different SET values (e.g. tier pricing) | Simple single-predicate mutations |
| You need all operations to commit atomically (one WAL transaction) | You need the result of one mutation to inform the next |
| Minimizing round-trips matters (high-latency network, tight SLA) | Operations span different tables |

---

## 8. Expression SELECT — Computed Columns

### What it does

`selectExpr` adds computed columns to a query result — columns that are calculated server-side
from expressions over physical column values, without being stored. This avoids client-side
post-processing for common projection math:

```ts
// Without selectExpr: client computes discounted price
const rows = await client.table('products').execute();
const result = rows.map(r => ({ ...r, discountedPrice: r.price * 0.9 }));

// With selectExpr: server computes it
const result = await client.table('products')
  .selectExpr({
    discountedPrice: { $mul: { $col: 'price' }, 0.9 },
  })
  .execute();
// result.rows[0].discountedPrice is already computed
```

### Operator map

| Operator | Meaning | Example |
|---|---|---|
| `$mul` | Multiply | `{ $mul: [{ $col: "price" }, 0.9] }` |
| `$add` | Add | `{ $add: [{ $col: "qty" }, 1] }` |
| `$sub` | Subtract | `{ $sub: [{ $col: "total" }, { $col: "refund" }] }` |
| `$div` | Divide | `{ $div: [{ $col: "revenue" }, { $col: "units" }] }` |
| `$col` | Column reference | `{ $col: "colName" }` |
| `$ifNull` | COALESCE: first non-null | `{ $ifNull: [{ $col: "note" }, "default"] }` |
| Conditional | CASE WHEN | `{ $cond: { when: <predicate>, then: <expr>, else: <expr> } }` |

### TypeScript client

```ts
// Arithmetic: discounted price + tier label
const result = await client.table('products')
  .where('status', '=', 'active')
  .select('id', 'name', 'price')        // physical columns
  .selectExpr({
    discountedPrice: {
      type: 'arithmetic', op: '*',
      left:  { type: 'colRef', col: 'price' },
      right: { type: 'literal', value: 0.9 }
    },
    tier: {
      type: 'conditional',
      when: { column: 'price', op: 'gt', value: 100 },
      then: { type: 'literal', value: 'premium' },
      else: { type: 'literal', value: 'standard' }
    }
  })
  .execute();

// result.rows[0].id, .name, .price   — physical columns
// result.rows[0].discountedPrice     — computed column
// result.rows[0].tier                — computed column
```

```ts
// COALESCE: safe display name
const result = await client.table('users')
  .selectExpr({
    displayName: {
      type: 'coalesce',
      args: [
        { type: 'colRef', col: 'displayName' },
        { type: 'colRef', col: 'email' }
      ]
    }
  })
  .execute();
```

### .NET client

```csharp
using Aouda.Protocol; // ScalarExprNode lives in Aouda.Protocol

var result = await client.Table("products")
    .Where("status", "eq", "active")
    .Select("id", "name", "price")
    .SelectExpr(
        ("discountedPrice", new ArithmeticScalarExpr(
            "*",
            new ColRefScalarExpr("price"),
            new LiteralScalarExpr(0.9))),
        ("tier", new ConditionalScalarExpr(
            when:  new ColumnPredicate("price", "gt", 100),
            then:  new LiteralScalarExpr("premium"),
            @else: new LiteralScalarExpr("standard"))))
    .ToListAsync();

// Each row dictionary contains "id", "name", "price", "discountedPrice", "tier"
```

### HTTP

Add `selectExpr` alongside (or instead of) the regular `select` field in the query body:

```http
POST /api/databases/shop/query HTTP/1.1
Content-Type: application/json

{
  "database": "shop",
  "table": "products",
  "select": ["id", "name", "price"],
  "selectExpr": [
    {
      "alias": "discountedPrice",
      "expr": {
        "type": "arithmetic",
        "op": "*",
        "left":  { "type": "colRef", "col": "price" },
        "right": { "type": "literal", "value": 0.9 }
      }
    },
    {
      "alias": "tier",
      "expr": {
        "type": "conditional",
        "when": { "column": "price", "op": "gt", "value": 100 },
        "then": { "type": "literal", "value": "premium" },
        "else": { "type": "literal", "value": "standard" }
      }
    }
  ],
  "limit": 100
}
```

**Response** (columnar format):

```json
{
  "columns": ["id", "name", "price", "discountedPrice", "tier"],
  "types":   ["Int64", "String", "Decimal", "Unknown", "Unknown"],
  "data":    [[1, 2], ["Widget", "Gadget"], [99.0, 149.0], [89.1, 134.1], ["standard", "premium"]],
  "rowCount": 2,
  "stats": { "executionMs": 5 }
}
```

### How Expression SELECT works

1. The server validates all column references against the table schema — unknown column names
   return `400 COLUMN_NOT_FOUND`.
2. The engine executes the physical query normally (predicate filtering, physical column
   projection, ordering).
3. After the physical projection step, each `selectExpr` entry is evaluated per row using the
   full row snapshot (even columns not in the physical `select` list are available for
   expression evaluation).
4. Computed column values are appended to the columnar output.
5. Physical columns not in `select` are stripped from the final output after expression
   evaluation.

### Limitations

| Limitation | Notes |
|---|---|
| Result type is `"Unknown"` | No static type inference for computed columns in v1; clients read the runtime type from the value |
| Maximum 20 `selectExpr` entries per query | Guard against accidental abuse; returns 400 if exceeded |
| Cannot `ORDER BY` a computed alias | e.g. `.orderBy('discountedPrice')` is not yet supported (deferred) |
| Not supported in JOIN queries | Expression SELECT applies to single-table queries only (deferred for JOIN paths) |
| Aggregation over computed columns not supported | e.g. `SUM(price * 0.9)` is deferred |
| Division by zero returns `null` | No exception — the row's computed column value is `null` for that row |
| Alias must not collide with a physical column name | Returns 400; computed column aliases must be distinct from all physical columns in `select` |
| Duplicate aliases rejected | Two `selectExpr` entries with the same alias → 400 |

---

## 9. Studio Bulk Mutation Panel

### Data Explorer — Bulk Mutation tab

In the table data view, click the **Bulk Mutation** tab in the toolbar. The panel provides a
guided flow:

1. **WHERE predicate builder** — same visual builder used for read queries; all engine
   operators are available. A preview row count is displayed before executing.
2. **Operation selector** — choose UPDATE, DELETE, or TRUNCATE.
3. **SET editor (UPDATE only)** — per-column editor. Each column toggles between:
   - **Literal mode** — type a value directly.
   - **Expression mode** — select an operator from a dropdown (`$inc`, `$mul`, `$dec`, `$div`,
     `$col`, `$ifNull`) and enter the operand(s).
4. **RETURNING selector** — multi-select column checklist to include in the response.
5. **LIMIT (DELETE only)** — optional; enables the rolling-delete `hasMore` loop pattern.
6. **Preview count** — click **Preview** to execute `COUNT(*) WHERE …` and show how many rows
   will be affected before committing.
7. **Confirm and execute** — prominent confirmation dialog: _"You are about to UPDATE / DELETE
   N rows. This cannot be undone."_ Optional sample of first 5 affected rows (read query).

After execution, the panel shows `rowsUpdated / rowsDeleted`, `executionMs`, and the
RETURNING rows (if requested) in a compact data grid.

### Query Worksheet — Expression SELECT

In the Query Worksheet, the **Projection** section now offers a computed column editor
alongside physical column selection:

1. Click **+ Computed column**.
2. Enter an alias.
3. Build the expression using the expression dropdown (arithmetic, coalesce, conditional).
4. Run the query — computed columns appear as additional columns in the result grid.

---

## 10. Common Patterns

### Pattern 1: Increment a counter atomically

```ts
// Increment view count for a page without read → compute → write
await client.table('pageViews')
  .where('pageId', '=', pageId)
  .update({ viewCount: { $inc: 1 }, lastViewedAt: new Date().toISOString() });
```

No race condition: the increment is evaluated server-side as an atomic read-modify-write on
each matching row.

### Pattern 2: Expire sessions with audit trail

```ts
// Mark expired sessions and capture which ones were affected
const now = new Date();
const result = await client.table('sessions')
  .where('expiresAt', '<', now)
  .update(
    { status: 'expired', expiredAt: now.toISOString() },
    { returning: ['id', 'userId', 'createdAt'] }
  );

// Write audit records from the RETURNING rows
for (const session of result.rows) {
  await auditLog.insert({ event: 'session_expired', sessionId: session.id, userId: session.userId });
}
```

### Pattern 3: Tiered price adjustment in one round-trip

```ts
// Apply different discount rates to different customer segments — one batch call
await client.table('prices')
  .batch([
    {
      where: { column: 'segment', op: 'eq', value: 'vip' },
      update: { price: { $mul: 0.70 }, updated: new Date().toISOString() },  // 30% off
    },
    {
      where: { column: 'segment', op: 'eq', value: 'loyal' },
      update: { price: { $mul: 0.85 }, updated: new Date().toISOString() },  // 15% off
    },
    {
      where: { column: 'segment', op: 'eq', value: 'new' },
      update: { price: { $mul: 0.95 }, updated: new Date().toISOString() },  // 5% off
    },
  ]);
```

### Pattern 4: Rolling delete of old audit logs

```ts
const retentionCutoff = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000); // 90 days
let totalDeleted = 0;
let hasMore = true;

while (hasMore) {
  const result = await client.table('auditLogs')
    .where('createdAt', '<', retentionCutoff)
    .orderBy('createdAt', 'asc')
    .limit(5000)
    .delete();

  totalDeleted += result.rowsDeleted;
  hasMore = result.hasMore;

  if (hasMore) {
    await new Promise(r => setTimeout(r, 200)); // yield between chunks
  }
}

console.log(`Deleted ${totalDeleted} audit log entries older than 90 days`);
```

### Pattern 5: Computed reporting column

```ts
// Add gross margin as a computed column without storing it
const report = await client.table('sales')
  .where('month', '=', '2026-06')
  .select('product', 'revenue', 'cost')
  .selectExpr({
    margin: {
      type: 'arithmetic', op: '-',
      left:  { type: 'colRef', col: 'revenue' },
      right: { type: 'colRef', col: 'cost' }
    },
    marginPct: {
      type: 'arithmetic', op: '/',
      left:  {
        type: 'arithmetic', op: '-',
        left:  { type: 'colRef', col: 'revenue' },
        right: { type: 'colRef', col: 'cost' }
      },
      right: { type: 'colRef', col: 'revenue' }
    }
  })
  .execute();
```

### Pattern 6: Safe table reset in CI/CD

```ts
// In tests or staging: reset a table between runs
// Branch first for safety, then truncate
await client.branches.create({ name: `backup-${Date.now()}`, parentBranch: 'main' });

await client.table('testEvents').truncate(); // requires Truncate scope

// After test run, optionally restore from branch or delete branch
await client.branches.delete(`backup-${Date.now()}`);
```

---

## 11. API Coverage Matrix

| Capability | .NET API | TypeScript API | HTTP endpoint | Studio |
|---|---|---|---|---|
| Literal UPDATE (basic) | `.UpdateAsync(dict)` | `.update(values)` | `PATCH .../rows` (`set`) | Bulk Mutation → SET editor → Literal mode |
| Expression SET | `.UpdateAsync(setBuilder)` | `.update({ col: { $inc: 1 } })` | `PATCH .../rows` (`setExpr`) | Bulk Mutation → SET editor → Expression mode |
| TRUNCATE | `.TruncateAsync()` | `.truncate()` | `POST .../truncate` | Bulk Mutation → TRUNCATE operation |
| DELETE with LIMIT | `.DeleteAsync()` + `.Limit()` + `.OrderBy()` | `.delete()` + `.limit()` + `.orderBy()` | `DELETE .../rows` (`limit`, `orderBy`) | Bulk Mutation → DELETE + LIMIT field |
| RETURNING on UPDATE | `.UpdateAsync(..., returning: [...])` | `.update(values, { returning: [...] })` | `PATCH .../rows` (`returning`) | Bulk Mutation → RETURNING selector |
| RETURNING on DELETE | `.DeleteAsync(returning: [...])` | `.delete({ returning: [...] })` | `DELETE .../rows` (`returning`) | Bulk Mutation → RETURNING selector |
| Batch mutation | `.BatchAsync([...])` | `.batch([...])` | `POST .../rows/batch` | Not yet in Studio UI |
| Expression SELECT (computed columns) | `.SelectExpr((alias, expr), ...)` | `.selectExpr({ alias: expr, ... })` | `POST .../query` (`selectExpr`) | Query Worksheet → + Computed column |

### Missing API surface

| Capability | Status | Notes |
|---|---|---|
| LIMIT on UPDATE | Not supported | Only DELETE supports LIMIT in v1 |
| ORDER BY computed column alias | Deferred | `ORDER BY discountedPrice` is not yet wired |
| Expression SELECT in JOIN queries | Deferred | Computed columns are single-table only |
| Aggregation over computed columns | Deferred | `SUM(price * 0.9)` is not yet supported |
| Type inference for computed columns | Deferred | Returns `"Unknown"` for all computed columns in v1 |
| Studio batch mutation UI | Deferred | Batch mutations are available over HTTP and SDK only |

---

## 12. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `400 INVALID_REQUEST` on UPDATE | Missing or empty `where` — safety guard enforced | Add at least one WHERE predicate; if intentional table-wide update, loop with batches |
| `400 INVALID_REQUEST` on `set` / `setExpr` | `set` is empty, or `setExpr` references an unknown column | Check that SET contains at least one key; verify column names exist in table schema |
| `400 COLUMN_NOT_FOUND` on expression | A `$col` / `colRef` name in `setExpr` or `selectExpr` does not exist in the schema | Correct the column name; use `GET /api/databases/{db}/tables/{name}` to inspect the schema |
| `400 INVALID_REQUEST` on `selectExpr` | Alias collides with a physical column name, duplicate alias, empty alias, or more than 20 expressions | Rename the alias; remove duplicates; stay under the 20-expression limit |
| `403 AUTHORIZATION_DENIED` on TRUNCATE | Caller has `db_writer` but not the `Truncate` scope | Use a `db_admin` credential or a role with explicit truncate permission |
| `403` on expression SET | RLS write policy restricts the target column | Check column-level write policies; use a role with write permission on that column |
| `hasMore: true` loop never terminates | ORDER BY column is not the same column as the WHERE filter | Ensure `orderBy` targets a column with monotonically increasing or decreasing values relative to the predicate; add a time-based cutoff |
| RETURNING returns unexpected columns | `["*"]` was used and the schema has more columns than expected | Enumerate explicit column names instead of `"*"` |
| Computed column value is `null` | Division by zero in the expression for that row | Guard with `$ifNull` or check denominator values before querying; this is intentional behavior |
| Expression SELECT result type shows `"Unknown"` | Expected behavior in v1 | Computed column types are not statically inferred; read the runtime type from the value itself |
| Batch operation fails partway through | One operation in the batch returned an error | All operations up to (but not including) the failing one may have been applied; the WAL transaction was rolled back for the failing operation only if the error occurred before commit |

---

## 13. Phase Coverage Matrix

| Session | Tasks | Delivered capability | Status |
|---|---|---|---|
| S1 | A.1–A.4 | Expression SET values — Protocol (`SetExprNode`), engine evaluator (`ExpressionSetEvaluator`), server validation, C# client `SetExprBuilder`, TS client `$`-operator map | Complete |
| S2 | B.1–B.3 | TRUNCATE — `POST .../truncate`, `DatabaseOperation.Truncate` scope, C# `TruncateAsync()`, TS `.truncate()`; DELETE with LIMIT — `limit`/`orderBy` on `DeleteMessage`, `hasMore` response, C# `.Limit().DeleteAsync()`, TS `.limit().delete()` | Complete |
| BL-106 | — | First-class TRUNCATE WAL frame (`WalTag.TruncateTable = 24`); crash recovery and replica replay; O(1) WAL records regardless of row count; no-PK table durability fix | Complete |
| S3 | C.1–C.3 | RETURNING clause — `returning` field on `UpdateMessage`/`DeleteMessage`, secondary scan after mutation, post-update / pre-delete semantics, columnar response, C# `returning:` param, TS `{ returning: [...] }` option | Complete |
| S4 | D.1 | Batch mutation — `POST .../rows/batch`, sequential execution, single WAL commit, `operationResults` response, C# `.BatchAsync()`, TS `.batch()` | Complete |
| S5 | E.1–E.3 | Studio bulk mutation panel — predicate builder, SET editor (literal + expression modes), preview count, confirm dialog, RETURNING selector, LIMIT field, result display | Complete |
| S6 | F.1–F.2 | User documentation — this guide; cross-links in `query.md`, `getting-started/index.md`, `http-api.md`, `studio.md` | Complete |
| S7 | BL-080 | Expression SELECT projections — `ComputedColumnDef`, `QueryMessage.selectExpr`, post-projection in `ToColumnarAsync`/`ToResultAsync`, server schema validation (unknown ColRef, alias collision, >20 limit), C# `ITableOperations.SelectExpr()`, TS `.selectExpr()` | Complete |

---

## 14. References

- `docs/decisions/0037-bulk-mutation-expressions.md` — primary ADR for bulk mutation design
- `docs/dev/BulkMutations-Developer-Guide.md` — engine-level implementation guide
- `docs/tasks/BulkMutations-Overview.md` — phase overview and session index
- `docs/tasks/BulkMutations-S1-Expression-SET.md`
- `docs/tasks/BulkMutations-S2-Truncate-And-Limit.md`
- `docs/tasks/BulkMutations-S3-Returning.md`
- `docs/tasks/BulkMutations-S4-Batch-Mutation.md`
- `docs/tasks/BulkMutations-S5-Studio.md`
- `docs/tasks/BulkMutations-S7-Expression-SELECT.md`
- `docs/tasks/BL/BL-106-TruncateWalFrameAndReplay.md`
- `src/Aouda.Protocol/Messages.cs` — `UpdateMessage`, `DeleteMessage`, `TruncateMessage`, `SetExprNode`, `ComputedColumnDef`, `QueryMessage`
- `src/Aouda.Engine.Api/TableQuery.cs` — `SelectExpr()` and post-projection step
- `src/Aouda.Engine.Api/Internal/ExpressionSetEvaluator.cs` — shared evaluator for SET and SELECT paths
- `guides/query.md` — query execution guide (SELECT, WHERE, ORDER BY)
- `guides/studio.md` — Studio management console guide
- `reference/http-api.md` — complete HTTP endpoint reference
