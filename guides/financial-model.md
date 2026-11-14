---
title: "Build a live financial model"
nav_order: 12.6
parent: "Guides"
---

# Build a live financial model (**ADR 0072, next train**)

Document status: written for the next train. Everything on this page is **new** and marked **(ADR 0072, next train)**; none of it is in a
released build.

This guide builds a small but complete live model: a three-year profit-and-loss statement for two departments, a balance-sheet line that
reads it, a department-scoped row condition, and a live view that moves when someone types a number. It uses nothing but ordinary tables
with a [formula column](formulas.md). Every step is shown three ways — raw HTTP, C# and TypeScript — and each was run end to end against a
real server, with the values shown here.

**On this page:** [What you build](#what-you-build) · [Before you start](#before-you-start) · [1. The tables](#step-1-two-tables-with-a-formula-column) ·
[2. Inputs](#step-2-the-inputs) · [3. Formulas](#step-3-the-formulas-one-per-line) · [4. Read](#step-4-read-the-statement) ·
[5. Edit and watch](#step-5-change-an-input-and-watch-it-settle) · [6. A failed cell](#step-6-a-cell-that-cannot-be-computed-and-why) ·
[7. A second table](#step-7-a-second-table-the-balance-sheet) · [8. Refusals](#step-8-what-the-database-refuses) ·
[9. Security](#step-9-who-may-see-and-write-what) · [Next](#where-to-go-next)

Related: [Formulas](formulas.md) (the reference for everything used here) · [Real-time streaming](real-time.md) ·
[Freshness](freshness.md) · [Data authorization](../auth/authorization.md) · [HTTP API](../reference/http-api.md#explain-a-formula-cell).

---

## What you build

(**ADR 0072, next train**) One table, `pnl`, keyed `(dept, line, year)`. Each row holds one number in `amount`. A row whose `formula` is
null is an **input** you type; a row with a formula is computed by the database:

| `line` | Kind | Formula |
|---|---|---|
| `Revenue`, `COGS`, `Opex` | input | — |
| `TaxRate` | input | — (`0.22` is 22 %) |
| `GrossProfit` | formula | `Revenue − COGS` |
| `EBIT` | formula | `GrossProfit − Opex` |
| `Margin` | formula | `round(EBIT × 100 / Revenue, 2)` — EBIT margin in percent |
| `Tax` | formula | `if(Margin > 0, round(EBIT × TaxRate, 2), 0)` |
| `NetIncome` | formula | `EBIT − Tax` |
| `MarginGap` | formula | `Margin − 15` — a KPI: how far the margin is above a 15 % target |

Every formula names only the `line` it reads. The department and the year come from the formula's own row, so **one formula serves every
department and every year**: copying the model to a new year is copying rows. `Margin` reads `Revenue` both directly and through `EBIT`,
and feeds both `Tax` and `MarginGap` — a diamond. When `Revenue` changes, the database computes `GrossProfit`, `EBIT`, `Margin`, `Tax`,
`NetIncome` and `MarginGap` once each, in that order, from each other's new values.

A second table, `balance`, carries `RetainedEarnings = Opening + pnl.NetIncome` per department and year, with each year's `Opening` the
year before's `RetainedEarnings`. A row condition lets each user see only their departments' rows, in both tables.

---

## Before you start

(**ADR 0072, next train**) A server with a database `finance` linked to an auth database, and that database's service key. On a
development machine:

```bash
ASPNETCORE_ENVIRONMENT=Development AOUDA_DEV_ADMIN=true aouda start --port 5433 --data-dir "$TMPDIR/aouda-finance"
# prints one line: AOUDA-DEV-ADMIN email=… password=… server_key=mk_srv_…
export AOUDA=http://localhost:5433
export SK=mk_srv_…                 # the server_key from that line
H=(-H "Content-Type: application/json")

curl -s -X POST "$AOUDA/api/databases" -H "Authorization: Bearer $SK" "${H[@]}" -d '{ "name": "auth", "kind": "auth" }'
curl -s -X POST "$AOUDA/api/databases" -H "Authorization: Bearer $SK" "${H[@]}" -d '{ "name": "finance", "auth": { "database": "auth" } }'
# the answer carries auth.keys.serviceRoleKey (mk_svc_…) once: keep it
export SVC=mk_svc_…
A=(-H "Authorization: Bearer $SVC" -H "Content-Type: application/json")
```

See [Development admin](development-admin.md) and [Auth setup](../auth/setup.md#linking-a-data-database-to-an-auth-database). The HTTP
steps below use `curl` and [`jq`](https://jqlang.org/). The C# steps use the `Aouda.Client` package and the TypeScript steps
`@aouda/client`; both connect with the same service key:

```csharp
using Aouda.Abstractions;                  // AoudaRequestException
using Aouda.Client;
using Aouda.Client.Formulas;               // Formula
using Aouda.Protocol;                      // ErrorCodes
using Aouda.Protocol.Schema;               // CreateTableRequest
using static Aouda.Client.Formulas.FormulaExpr;

using var client = new AoudaClient(new AoudaClientOptions { ServerUrl = url, DatabaseName = "finance", ApiKey = serviceKey });
```

```typescript
import { AoudaClient, AoudaConflictError, Formula, FormulaConflictError, FormulaReferenceNotReadableError, fx } from "@aouda/client";

const database = "finance";
const client = new AoudaClient({ serverUrl, database, apiKey: serviceKey });
```

---

## Step 1: two tables with a formula column

(**ADR 0072, next train**) The row condition is a resolver in the auth database: a row is visible to a user when its `dept` is one of
the user's entitlements in the dimension `dept`. Create it once, over HTTP (it is an auth-admin call in every client):

```bash
curl -s -X POST "$AOUDA/api/databases/finance/auth/admin/rls-resolvers" "${A[@]}" -d '{
  "name": "by_dept",
  "resolverType": "ColumnMatch",
  "rules": [ { "ruleOrder": 0, "columnName": "dept", "operator": "In",
               "valueSource": "Entitlement", "valueConfig": "{\"dimension\":\"dept\"}" } ]
}'
```

Then the two tables. They have the same shape: the key, an ordinary `Decimal(18,2)` value column, and an `Expression` column that
**drives** it.

**HTTP** — once with `"name": "pnl"` and once with `"name": "balance"`:

```bash
curl -s -X POST "$AOUDA/api/databases/finance/tables" "${A[@]}" -d '{
  "database": "finance",
  "name": "pnl",
  "columns": [
    { "name": "dept",    "type": "String", "primaryKeyOrder": 1 },
    { "name": "line",    "type": "String", "primaryKeyOrder": 2 },
    { "name": "year",    "type": "Int32",  "primaryKeyOrder": 3 },
    { "name": "amount",  "type": "Decimal", "precision": 18, "scale": 2, "isNullable": true },
    { "name": "formula", "type": "Expression", "drives": "amount" }
  ],
  "authMode": "auth-db-rls",
  "rlsResolverName": "by_dept"
}'
```

The answer lists the formula column as `{"name":"formula","type":"Expression","isNullable":true,"id":5,"drives":"amount"}`: an Expression
column is always nullable, because a row with no formula is an input.

**C#**

```csharp
foreach (var name in new[] { "pnl", "balance" })
{
    await client.Schema.CreateTableAsync(new CreateTableRequest
    {
        Database = "finance",
        Name = name,
        Columns =
        [
            new() { Name = "dept", Type = "String", PrimaryKeyOrder = 1 },
            new() { Name = "line", Type = "String", PrimaryKeyOrder = 2 },
            new() { Name = "year", Type = "Int32", PrimaryKeyOrder = 3 },
            new() { Name = "amount", Type = "Decimal", Precision = 18, Scale = 2, IsNullable = true },
            new() { Name = "formula", Type = "Expression", Drives = "amount" },
        ],
        AuthMode = "auth-db-rls",
        RlsResolverName = "by_dept",
    });
}
```

**TypeScript**

```typescript
for (const name of ["pnl", "balance"]) {
  await client.tables.createTable({
    database,
    name,
    columns: [
      { name: "dept", type: "String", primaryKeyOrder: 1 },
      { name: "line", type: "String", primaryKeyOrder: 2 },
      { name: "year", type: "Int32", primaryKeyOrder: 3 },
      { name: "amount", type: "Decimal", precision: 18, scale: 2, isNullable: true },
      { name: "formula", type: "Expression", drives: "amount" },
    ],
    authMode: "auth-db-rls",
    rlsResolverName: "by_dept",
  });
}
```

A table with a formula column needs a primary key (a formula addresses a row by it) and is otherwise an ordinary table. The rules of the
declaration are in [Formulas: the column](formulas.md#the-column).

---

## Step 2: the inputs

(**ADR 0072, next train**) Inputs are ordinary rows with no formula: an ordinary insert.

| | Retail 2026 | 2027 | 2028 | Online 2026 | 2027 | 2028 |
|---|---|---|---|---|---|---|
| `Revenue` | 1200.00 | 1380.00 | 1500.00 | 800.00 | 960.00 | 1100.00 |
| `COGS` | 720.00 | 800.00 | 840.00 | 400.00 | 470.00 | 530.00 |
| `Opex` | 280.00 | 320.00 | 340.00 | 260.00 | 280.00 | 300.00 |
| `TaxRate` | 0.22 | 0.22 | 0.24 | 0.22 | 0.22 | 0.24 |

**HTTP** — a write body is [column arrays](../reference/http-api.md#column-arrays-the-write-body): one array per column.

```bash
curl -s -X POST "$AOUDA/api/databases/finance/tables/pnl/rows" "${A[@]}" -d '{
  "database": "finance",
  "columns": ["dept", "line", "year", "amount"],
  "data": [
    ["Retail", "Retail", "Retail", "Retail", "Retail", "Retail", "Retail", "Retail", "Retail", "Retail", "Retail", "Retail",
     "Online", "Online", "Online", "Online", "Online", "Online", "Online", "Online", "Online", "Online", "Online", "Online"],
    ["Revenue", "COGS", "Opex", "TaxRate", "Revenue", "COGS", "Opex", "TaxRate", "Revenue", "COGS", "Opex", "TaxRate",
     "Revenue", "COGS", "Opex", "TaxRate", "Revenue", "COGS", "Opex", "TaxRate", "Revenue", "COGS", "Opex", "TaxRate"],
    [2026, 2026, 2026, 2026, 2027, 2027, 2027, 2027, 2028, 2028, 2028, 2028,
     2026, 2026, 2026, 2026, 2027, 2027, 2027, 2027, 2028, 2028, 2028, 2028],
    [1200.00, 720.00, 280.00, 0.22, 1380.00, 800.00, 320.00, 0.22, 1500.00, 840.00, 340.00, 0.24,
      800.00, 400.00, 260.00, 0.22,  960.00, 470.00, 280.00, 0.22, 1100.00, 530.00, 300.00, 0.24]
  ]
}'
# {"rowsInserted":24,"executionMs":…,"token":"01…"}
```

**C#**

```csharp
var pnl = client.GetTable("pnl");
var inputs = new (string Dept, int Year, decimal Revenue, decimal Cogs, decimal Opex, decimal TaxRate)[]
{
    ("Retail", 2026, 1200m, 720m, 280m, 0.22m), ("Retail", 2027, 1380m, 800m, 320m, 0.22m), ("Retail", 2028, 1500m, 840m, 340m, 0.24m),
    ("Online", 2026,  800m, 400m, 260m, 0.22m), ("Online", 2027,  960m, 470m, 280m, 0.22m), ("Online", 2028, 1100m, 530m, 300m, 0.24m),
};
await pnl.InsertAsync(inputs.SelectMany(i => new[]
{
    Input(i.Dept, "Revenue", i.Year, i.Revenue), Input(i.Dept, "COGS", i.Year, i.Cogs),
    Input(i.Dept, "Opex", i.Year, i.Opex), Input(i.Dept, "TaxRate", i.Year, i.TaxRate),
}).ToList());

static Dictionary<string, object?> Input(string dept, string line, int year, decimal amount)
    => new() { ["dept"] = dept, ["line"] = line, ["year"] = year, ["amount"] = amount };
```

**TypeScript**

```typescript
const inputs: [string, number, number, number, number, number][] = [
  ["Retail", 2026, 1200, 720, 280, 0.22], ["Retail", 2027, 1380, 800, 320, 0.22], ["Retail", 2028, 1500, 840, 340, 0.24],
  ["Online", 2026, 800, 400, 260, 0.22], ["Online", 2027, 960, 470, 280, 0.22], ["Online", 2028, 1100, 530, 300, 0.24],
];
await client.table("pnl").insertMany(
  inputs.flatMap(([dept, year, revenue, cogs, opex, taxRate]) => [
    { dept, line: "Revenue", year, amount: revenue },
    { dept, line: "COGS", year, amount: cogs },
    { dept, line: "Opex", year, amount: opex },
    { dept, line: "TaxRate", year, amount: taxRate },
  ]),
);
```

---

## Step 3: the formulas, one per line

(**ADR 0072, next train**) A formula is the [expression JSON](../reference/http-api.md#expression-node-format) of the value it
computes. It reads another row with a `cellRef`: a `key` and a `column`. Here every `cellRef` leaves out the `table` (it reads its own
table) and gives only `line`; the key columns it leaves out — `dept` and `year` — are taken from the formula's own row. So `GrossProfit`
on the row `(Online, GrossProfit, 2027)` reads `(Online, Revenue, 2027)` and `(Online, COGS, 2027)`.

**HTTP** — the six formulas as files, then one insert per line that writes the same formula into all six `(dept, year)` rows:

```bash
mkdir -p fx
cat > fx/GrossProfit.json <<'EOF'
{ "type": "arithmetic", "op": "-",
  "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Revenue" } }, "column": "amount" },
  "right": { "type": "cellRef", "key": { "line": { "type": "literal", "value": "COGS" } },    "column": "amount" } }
EOF
cat > fx/EBIT.json <<'EOF'
{ "type": "arithmetic", "op": "-",
  "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "GrossProfit" } }, "column": "amount" },
  "right": { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Opex" } },        "column": "amount" } }
EOF
cat > fx/Margin.json <<'EOF'
{ "type": "call", "fn": "round", "args": [
  { "type": "arithmetic", "op": "/",
    "left": { "type": "arithmetic", "op": "*",
              "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "EBIT" } }, "column": "amount" },
              "right": { "type": "literal", "value": 100 } },
    "right": { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Revenue" } }, "column": "amount" } },
  { "type": "literal", "value": 2 } ] }
EOF
cat > fx/Tax.json <<'EOF'
{ "type": "call", "fn": "if", "args": [
  { "type": "call", "fn": "gt", "args": [
    { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Margin" } }, "column": "amount" },
    { "type": "literal", "value": 0 } ] },
  { "type": "call", "fn": "round", "args": [
    { "type": "arithmetic", "op": "*",
      "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "EBIT" } },    "column": "amount" },
      "right": { "type": "cellRef", "key": { "line": { "type": "literal", "value": "TaxRate" } }, "column": "amount" } },
    { "type": "literal", "value": 2 } ] },
  { "type": "literal", "value": 0 } ] }
EOF
cat > fx/NetIncome.json <<'EOF'
{ "type": "arithmetic", "op": "-",
  "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "EBIT" } }, "column": "amount" },
  "right": { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Tax" } },  "column": "amount" } }
EOF
cat > fx/MarginGap.json <<'EOF'
{ "type": "arithmetic", "op": "-",
  "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Margin" } }, "column": "amount" },
  "right": { "type": "literal", "value": 15 } }
EOF

for line in GrossProfit EBIT Margin Tax NetIncome MarginGap; do
  jq -n --arg line "$line" --slurpfile fx "fx/$line.json" '{
    database: "finance",
    columns: ["dept", "line", "year", "formula"],
    data: [ ["Retail", "Retail", "Retail", "Online", "Online", "Online"],
            [range(6) | $line],
            [2026, 2027, 2028, 2026, 2027, 2028],
            [range(6) | $fx[0]] ] }' |
  curl -s -X POST "$AOUDA/api/databases/finance/tables/pnl/rows" "${A[@]}" -d @-
done
# each: {"rowsInserted":6,…,"token":"01…"} — keep the last token for step 4
```

The formula is sent as a JSON **object** in the row, not as a string. A formula row gives no `amount`: its value is computed.

**C#** — `FormulaExpr` builds the same JSON, and `Formula.From` makes it the value of the Expression column:

```csharp
// A key column a reference leaves out (dept, year) is the formula row's own: one formula serves every department and year.
static ScalarExprNode Line(string line) => CellHere("amount", ("line", line));

var formulas = new Dictionary<string, ScalarExprNode>
{
    ["GrossProfit"] = Sub(Line("Revenue"), Line("COGS")),
    ["EBIT"] = Sub(Line("GrossProfit"), Line("Opex")),
    ["Margin"] = Round(Div(Mul(Line("EBIT"), Lit(100)), Line("Revenue")), 2),
    ["Tax"] = If(Gt(Line("Margin"), Lit(0)), Round(Mul(Line("EBIT"), Line("TaxRate")), 2), Lit(0)),
    ["NetIncome"] = Sub(Line("EBIT"), Line("Tax")),
    ["MarginGap"] = Sub(Line("Margin"), Lit(15)),
};
await pnl.InsertAsync((
    from dept in new[] { "Retail", "Online" }
    from year in new[] { 2026, 2027, 2028 }
    from f in formulas
    select new Dictionary<string, object?> { ["dept"] = dept, ["line"] = f.Key, ["year"] = year, ["formula"] = Formula.From(f.Value) }
).ToList());
```

**TypeScript** — `fx` builds the same JSON, and `Formula.from` makes it the value of the Expression column:

```typescript
// A key column a reference leaves out (dept, year) is the formula row's own: one formula serves every department and year.
const line = (name: string) => fx.cellHere("amount", { line: name });
const formulas = {
  GrossProfit: fx.sub(line("Revenue"), line("COGS")),
  EBIT: fx.sub(line("GrossProfit"), line("Opex")),
  Margin: fx.round(fx.div(fx.mul(line("EBIT"), fx.lit(100)), line("Revenue")), 2),
  Tax: fx.if(fx.gt(line("Margin"), fx.lit(0)), fx.round(fx.mul(line("EBIT"), line("TaxRate")), 2), fx.lit(0)),
  NetIncome: fx.sub(line("EBIT"), line("Tax")),
  MarginGap: fx.sub(line("Margin"), fx.lit(15)),
};
await client.table("pnl").insertMany(
  ["Retail", "Online"].flatMap((dept) =>
    [2026, 2027, 2028].flatMap((year) =>
      Object.entries(formulas).map(([name, node]) => ({ dept, line: name, year, formula: Formula.from(node) })),
    ),
  ),
);
```

**Why `round` in `Margin` and `Tax`.** A formula is checked when it is written against the type of the column it drives. A division of
two `Decimal(18,2)` values computes six decimal places, and `EBIT × TaxRate` four; neither fits `Decimal(18,2)` without loss, so the
write is refused with `400 FORMULA_INVALID` and a message that says what to write (`round it to the column's scale (round(x, 2))`). The
database never rounds for you. See [Types](formulas.md#types-the-driven-column-decides).

---

## Step 4: read the statement

(**ADR 0072, next train**) A formula row's value is computed **after** the commit that wrote it, by the database's formula maintainer, a
moment later. Your write never waits for it. To read the values your write produced, read with the write's **consistency token**: a
token read of a table with a formula column waits until the formulas have caught up with it.

**HTTP** — the token from the last insert of step 3 in `at_least`, and how long to wait in `waitMs`:

```bash
curl -s -X POST "$AOUDA/api/databases/finance/query?at_least=$TOKEN&waitMs=5000" "${A[@]}" -d '{
  "database": "finance",
  "table": "pnl",
  "select": ["line", "amount"],
  "where": { "and": [ { "column": "dept", "op": "eq", "value": "Retail" },
                      { "column": "year", "op": "eq", "value": 2026 } ] }
}'
```

| `line` | Retail 2026 | 2027 | 2028 | Online 2026 | 2027 | 2028 |
|---|---|---|---|---|---|---|
| `GrossProfit` | 480.00 | 580.00 | 660.00 | 400.00 | 490.00 | 570.00 |
| `EBIT` | 200.00 | 260.00 | 320.00 | 140.00 | 210.00 | 270.00 |
| `Margin` | 16.67 | 18.84 | 21.33 | 17.50 | 21.88 | 24.55 |
| `Tax` | 44.00 | 57.20 | 76.80 | 30.80 | 46.20 | 64.80 |
| `NetIncome` | 156.00 | 202.80 | 243.20 | 109.20 | 163.80 | 205.20 |
| `MarginGap` | 1.67 | 3.84 | 6.33 | 2.50 | 6.88 | 9.55 |

Without a token a read answers at once, and a value may still be the one from before your write (null, for a formula row written a moment
ago). If the formulas are not caught up within `waitMs` the answer is `409 TOKEN_UNSATISFIED`, never an old value: read again. A JSON
read carries each row's formula as an object (`"table": ""` where the formula left the table out) and `null` for an input.

**C#** — the client sends its last write's token by itself, and the server waits its default 250 ms; past that it answers
`409 TOKEN_UNSATISFIED`, which the client does not retry. Read again:

```csharp
static async Task<Dictionary<string, decimal?>> ReadAsync(AoudaClient client, string table, string dept, int year)
{
    for (var attempt = 0; ; attempt++)
    {
        try
        {
            var rows = await client.GetTable(table).Where("dept", "eq", dept).Where("year", "eq", year).ToListAsync();
            return rows.ToDictionary(r => (string)r["line"]!, r => r["amount"] is null ? (decimal?)null : Convert.ToDecimal(r["amount"]));
        }
        catch (AoudaRequestException e) when (e.ErrorCode == ErrorCodes.TokenUnsatisfied && attempt < 40)
        {
            await Task.Delay(250);
        }
    }
}

var retail2026 = await ReadAsync(client, "pnl", "Retail", 2026);   // GrossProfit 480.00, EBIT 200.00, Margin 16.67, …
```

**TypeScript** — the same: the client sends its token, and a `409 TOKEN_UNSATISFIED` (`AoudaConflictError`) is read again:

```typescript
async function read(table: string, dept: string, year: number): Promise<Record<string, unknown>> {
  for (let attempt = 0; ; attempt++) {
    try {
      const { rows } = await client.table(table).where("dept", "=", dept).where("year", "=", year).execute();
      return Object.fromEntries(rows.map((r) => [r.line as string, r.amount]));
    } catch (e) {
      if (!(e instanceof AoudaConflictError && e.code === "TOKEN_UNSATISFIED") || attempt >= 40) throw e;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
}

const retail2026 = await read("pnl", "Retail", 2026);   // { GrossProfit: 480, EBIT: 200, Margin: 16.67, … }
```

The SDK reads come back in column-batch frames: a C# row's `formula` is the formula's canonical text, a TypeScript row's a `Formula`
(`null` for an input), and a TypeScript `Decimal` is a `number`. `Formula.FromValue` / `Formula.fromValue` read either form.

---

## Step 5: change an input and watch it settle

(**ADR 0072, next train**) Subscribe to Retail's 2026 rows, then raise Retail's 2026 revenue to 1250.00. The subscription receives the
input's change and then **each formula row that changed, once**, at its final value — never an intermediate one:

```
update Revenue:     1200.00 -> 1250.00
update GrossProfit:  480.00 ->  530.00
update EBIT:         200.00 ->  250.00
update Margin:        16.67 ->   20.00
update Tax:           44.00 ->   55.00
update NetIncome:    156.00 ->  195.00
update MarginGap:      1.67 ->    5.00
```

`Margin` is computed once even though `Revenue` reaches it two ways. A formula whose value did not change sends nothing.

**HTTP** — the edit is an ordinary update; the subscription is the ordinary [WebSocket](../reference/http-api.md#websocket-streaming-protocol)
`subscribe` on `ws://localhost:5433/api/databases/finance/ws`:

```json
{ "type": "auth", "token": "mk_svc_…", "database": "finance" }
{ "type": "subscribe", "id": "retail-2026", "target": "pnl",
  "filter": { "and": [ { "column": "dept", "op": "eq", "value": "Retail" },
                       { "column": "year", "op": "eq", "value": 2026 } ] } }
```

```bash
curl -s -X PATCH "$AOUDA/api/databases/finance/tables/pnl/rows" "${A[@]}" -d '{
  "database": "finance",
  "where": { "and": [ { "column": "dept", "op": "eq", "value": "Retail" },
                      { "column": "line", "op": "eq", "value": "Revenue" },
                      { "column": "year", "op": "eq", "value": 2026 } ] },
  "set": { "amount": 1250.00 }
}'
```

Each `change` message carries the row and, for an update, `prev`; its `formula` is the JSON object:

```json
{ "type": "change", "id": "retail-2026", "op": "update",
  "row":  { "dept": "Retail", "line": "Margin", "year": 2026, "amount": 20,    "formula": { "type": "call", "fn": "round", … } },
  "prev": { "dept": "Retail", "line": "Margin", "year": 2026, "amount": 16.67, "formula": { "type": "call", "fn": "round", … } },
  "version": 142, "token": "01…" }
```

**C#**

```csharp
await foreach (var e in client.GetTable("pnl").Where("dept", "eq", "Retail").Where("year", "eq", 2026).SubscribeAsync(ct))
{
    if (e.IsSnapshot) continue;   // the first event: the rows as they are now
    Console.WriteLine($"{e.Type} {e.Row!["line"]}: {e.PreviousRow?["amount"]} -> {e.Row["amount"]}");
}

// elsewhere, after the snapshot has arrived:
await client.GetTable("pnl").Where("dept", "eq", "Retail").Where("line", "eq", "Revenue").Where("year", "eq", 2026)
    .UpdateAsync(new Dictionary<string, object?> { ["amount"] = 1250m });
```

**TypeScript**

```typescript
const sub = client.table("pnl").where("dept", "=", "Retail").where("year", "=", 2026).subscribe({
  onSnapshot: (rows) => render(rows),
  onChange: (event) => console.log(`${event.op} ${event.row?.line}: ${event.prev?.amount} -> ${event.row?.amount}`),
});

await client.table("pnl").where("dept", "=", "Retail").where("line", "=", "Revenue").where("year", "=", 2026)
  .update({ amount: 1250 });
```

A change event's `token` is a valid cover for a later token read; tokens are not ordered across events, so keep the highest you have
seen. See [Formulas: live](formulas.md#live-subscriptions).

---

## Step 6: a cell that cannot be computed, and why

(**ADR 0072, next train**) Set Online's 2028 revenue to 0. `Margin` divides by revenue, so it has no value: it is **null**. There is no
error column and no failed write; the other cells still settle:

| Online 2028 | before | after |
|---|---|---|
| `Revenue` | 1100.00 | 0.00 |
| `EBIT` | 270.00 | -830.00 |
| `Margin` | 24.55 | **null** |
| `Tax` | 64.80 | 0.00 — `if` with a null condition takes the `else` branch |
| `NetIncome` | 205.20 | -830.00 |
| `MarginGap` | 9.55 | **null** — arithmetic over a null is null |

To learn why a cell is null, ask the database to **explain** it. `explain` evaluates the cell again now and answers its formula, every
cell it reads with that cell's current value, the value or the reason it has none, and the formula cells that read it.

**HTTP**

```bash
curl -s -X PATCH "$AOUDA/api/databases/finance/tables/pnl/rows" "${A[@]}" -d '{
  "database": "finance",
  "where": { "and": [ { "column": "dept", "op": "eq", "value": "Online" },
                      { "column": "line", "op": "eq", "value": "Revenue" },
                      { "column": "year", "op": "eq", "value": 2028 } ] },
  "set": { "amount": 0 }
}'
curl -s -X POST "$AOUDA/api/databases/finance/tables/pnl/explain" "${A[@]}" -d '{
  "key": { "dept": "Online", "line": "Margin", "year": 2028 },
  "column": "amount"
}'
```

```json
{
  "table": "pnl",
  "key": { "dept": "Online", "line": "Margin", "year": 2028 },
  "column": "amount",
  "expressionColumn": "formula",
  "kind": "formula",
  "formula": { "type": "call", "fn": "round", "args": [ … ] },
  "references": [
    { "table": "pnl", "key": { "dept": "Online", "line": "Revenue", "year": 2028 }, "column": "amount",
      "readable": true, "value": 0.00, "isFormulaCell": false, "error": null },
    { "table": "pnl", "key": { "dept": "Online", "line": "EBIT", "year": 2028 }, "column": "amount",
      "readable": true, "value": -830.00, "isFormulaCell": true, "error": null }
  ],
  "value": null,
  "reason": "division by zero.",
  "storedValue": null,
  "readBy": [
    { "table": "pnl", "key": { "dept": "Online", "line": "MarginGap", "year": 2028 }, "column": "amount" },
    { "table": "pnl", "key": { "dept": "Online", "line": "Tax", "year": 2028 }, "column": "amount" }
  ]
}
```

Note that each reference's `key` is the **resolved** key: the `dept` and `year` the formula left out are filled in from the row.

**C#**

```csharp
await client.GetTable("pnl").Where("dept", "eq", "Online").Where("line", "eq", "Revenue").Where("year", "eq", 2028)
    .UpdateAsync(new Dictionary<string, object?> { ["amount"] = 0m });

var why = await pnl.ExplainAsync("amount", ("dept", "Online"), ("line", "Margin"), ("year", 2028));
Console.WriteLine($"{why.Kind}: {why.Value ?? "null"} because {why.Reason}");   // formula: null because division by zero.
foreach (var r in why.References)
    Console.WriteLine($"  reads {r.Table}[{string.Join(", ", r.Key.Values)}].{r.Column} = {r.Value}");
```

**TypeScript**

```typescript
await client.table("pnl").where("dept", "=", "Online").where("line", "=", "Revenue").where("year", "=", 2028)
  .update({ amount: 0 });

const why = await client.table("pnl").explain({ dept: "Online", line: "Margin", year: 2028 }, "amount");
console.log(`${why.kind}: ${why.value} because ${why.reason}`);   // formula: null because division by zero.
for (const r of why.references) console.log(`  reads ${r.table}[${Object.values(r.key).join(", ")}].${r.column} = ${r.value}`);
```

A grid that wants to show `#DIV/0!` calls `explain` for a null formula cell. Set the revenue back and the cells compute again.

---

## Step 7: a second table: the balance sheet

(**ADR 0072, next train**) `balance` has the same shape. Its `RetainedEarnings` reads its own `Opening` row and `pnl`'s `NetIncome` — a
`cellRef` that names a `table` — and each year's `Opening` (but the first) is the year before's `RetainedEarnings`, named with an
explicit `year`. The `dept` stays relative throughout.

| `balance` | Kind | Formula |
|---|---|---|
| `Opening` 2026 | input | Retail 500.00, Online 300.00 |
| `Opening` 2027 | formula | `RetainedEarnings` of 2026 |
| `Opening` 2028 | formula | `RetainedEarnings` of 2027 |
| `RetainedEarnings` (every year) | formula | `Opening + pnl.NetIncome` |

**HTTP** — inputs and formulas can share one insert; an input row's `formula` is null, a formula row's `amount` is null:

```bash
OPEN_2027='{ "type": "cellRef", "key": { "line": { "type": "literal", "value": "RetainedEarnings" }, "year": { "type": "literal", "value": 2026 } }, "column": "amount" }'
OPEN_2028='{ "type": "cellRef", "key": { "line": { "type": "literal", "value": "RetainedEarnings" }, "year": { "type": "literal", "value": 2027 } }, "column": "amount" }'
RETAINED='{ "type": "arithmetic", "op": "+",
  "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Opening" } }, "column": "amount" },
  "right": { "type": "cellRef", "table": "pnl", "key": { "line": { "type": "literal", "value": "NetIncome" } }, "column": "amount" } }'
curl -s -X POST "$AOUDA/api/databases/finance/tables/balance/rows" "${A[@]}" -d "{
  \"database\": \"finance\",
  \"columns\": [\"dept\", \"line\", \"year\", \"amount\", \"formula\"],
  \"data\": [
    [\"Retail\", \"Retail\", \"Retail\", \"Retail\", \"Retail\", \"Retail\",
     \"Online\", \"Online\", \"Online\", \"Online\", \"Online\", \"Online\"],
    [\"Opening\", \"Opening\", \"Opening\", \"RetainedEarnings\", \"RetainedEarnings\", \"RetainedEarnings\",
     \"Opening\", \"Opening\", \"Opening\", \"RetainedEarnings\", \"RetainedEarnings\", \"RetainedEarnings\"],
    [2026, 2027, 2028, 2026, 2027, 2028, 2026, 2027, 2028, 2026, 2027, 2028],
    [500.00, null, null, null, null, null, 300.00, null, null, null, null, null],
    [null, $OPEN_2027, $OPEN_2028, $RETAINED, $RETAINED, $RETAINED,
     null, $OPEN_2027, $OPEN_2028, $RETAINED, $RETAINED, $RETAINED]
  ]
}"
```

**C#**

```csharp
var balance = client.GetTable("balance");
var retained = Add(CellHere("amount", ("line", "Opening")), Cell("pnl", "amount", ("line", "NetIncome")));
await balance.InsertAsync((
    from dept in new[] { "Retail", "Online" }
    from row in new (string Line, int Year, object? Amount, ScalarExprNode? Formula)[]
    {
        ("Opening", 2026, dept == "Retail" ? 500m : 300m, null),
        ("Opening", 2027, null, CellHere("amount", ("line", "RetainedEarnings"), ("year", 2026))),
        ("Opening", 2028, null, CellHere("amount", ("line", "RetainedEarnings"), ("year", 2027))),
        ("RetainedEarnings", 2026, null, retained),
        ("RetainedEarnings", 2027, null, retained),
        ("RetainedEarnings", 2028, null, retained),
    }
    select new Dictionary<string, object?>
    {
        ["dept"] = dept, ["line"] = row.Line, ["year"] = row.Year,
        ["amount"] = row.Amount, ["formula"] = row.Formula is null ? null : Formula.From(row.Formula),
    }
).ToList());
```

**TypeScript**

```typescript
const retained = fx.add(fx.cellHere("amount", { line: "Opening" }), fx.cell("pnl", "amount", { line: "NetIncome" }));
await client.table("balance").insertMany(
  ["Retail", "Online"].flatMap((dept) => [
    { dept, line: "Opening", year: 2026, amount: dept === "Retail" ? 500 : 300 },
    { dept, line: "Opening", year: 2027, formula: Formula.from(fx.cellHere("amount", { line: "RetainedEarnings", year: 2026 })) },
    { dept, line: "Opening", year: 2028, formula: Formula.from(fx.cellHere("amount", { line: "RetainedEarnings", year: 2027 })) },
    ...[2026, 2027, 2028].map((year) => ({ dept, line: "RetainedEarnings", year, formula: Formula.from(retained) })),
  ]),
);
```

With the edits of steps 5 and 6:

| `balance` | Retail 2026 | 2027 | 2028 | Online 2026 | 2027 | 2028 |
|---|---|---|---|---|---|---|
| `Opening` | 500.00 | 695.00 | 897.80 | 300.00 | 409.20 | 573.00 |
| `RetainedEarnings` | 695.00 | 897.80 | 1141.00 | 409.20 | 573.00 | -257.00 |

An edit to any input of `pnl` now reaches `balance` too: a formula is woken by a change to any row it reads, in any table.

---

## Step 8: what the database refuses

(**ADR 0072, next train**) Each of these is refused whole — nothing of the write is applied — with a code and a message that names the
row and the rule:

| You try | You get |
|---|---|
| To set `amount` of a formula row (`Tax`, 2026) | `409 FORMULA_VALUE_WRITE_REFUSED`: "the row has a formula in 'formula', so its 'amount' is computed and cannot be set (set 'formula' to null in the same update to make the row an input)" |
| A `GrossProfit / Revenue` formula into `Decimal(18,2)` | `400 FORMULA_INVALID`: "the formula computes Decimal(·,6), which its driven column (Decimal(·,2)) cannot hold without loss; round it to the column's scale (round(x, 2))…" |
| To make `Opex` read `NetIncome`, which reads `Opex` through `EBIT` | `400 FORMULA_CYCLE`, naming the cycle: `pnl[Retail, EBIT, 2026].amount → pnl[Retail, Opex, 2026].amount → pnl[Retail, NetIncome, 2026].amount → …` |
| To drop `pnl`, which `balance` reads | `409 FORMULA_TABLE_REFERENCED`, naming the cells that read it |

**HTTP** — the first one:

```bash
curl -s -X PATCH "$AOUDA/api/databases/finance/tables/pnl/rows" "${A[@]}" -d '{
  "database": "finance",
  "where": { "and": [ { "column": "dept", "op": "eq", "value": "Retail" },
                      { "column": "line", "op": "eq", "value": "Tax" },
                      { "column": "year", "op": "eq", "value": 2026 } ] },
  "set": { "amount": 0 }
}'
# 409 {"error":"pnl[Retail, Tax, 2026]: the row has a formula in 'formula', …","code":"FORMULA_VALUE_WRITE_REFUSED",…}
```

**C#** — a formula refusal is an `AoudaFormulaRefusedException` with a `Kind`:

```csharp
try
{
    await client.GetTable("pnl").Where("dept", "eq", "Retail").Where("line", "eq", "Tax").Where("year", "eq", 2026)
        .UpdateAsync(new Dictionary<string, object?> { ["amount"] = 0m });
}
catch (AoudaFormulaRefusedException e) when (e.Kind == FormulaErrorKind.ValueWriteRefused)
{
    Console.WriteLine($"{e.StatusCode} {e.ErrorCode}: {e.Message}");   // 409 FORMULA_VALUE_WRITE_REFUSED: …
}
```

**TypeScript** — a `FormulaConflictError` with a `kind`:

```typescript
try {
  await client.table("pnl").where("dept", "=", "Retail").where("line", "=", "Tax").where("year", "=", 2026)
    .update({ amount: 0 });
} catch (e) {
  if (!(e instanceof FormulaConflictError && e.kind === "valueWriteRefused")) throw e;
  console.log(`${e.statusCode} ${e.code}: ${e.message}`);   // 409 FORMULA_VALUE_WRITE_REFUSED: …
}
```

To type a number over a computed one, make the row an input in the same write: `"set": { "formula": null, "amount": 250.00 }`. Setting
only `"formula": null` keeps the last computed value as the input.

---

## Step 9: who may see and write what

(**ADR 0072, next train**) A formula table's security is the table's own, set like any table's. Two people:

- a **viewer** who may read both tables, for the Retail department only;
- a **planner** who may read and write both tables, for Retail only.

**HTTP** — two roles, two users, and an entitlement `dept = Retail` for each (an auth-admin task, with the service key):

```bash
curl -s -X POST "$AOUDA/api/databases/finance/auth/admin/roles" "${A[@]}" -d '{ "name": "viewer", "permissions": [
  { "resourceType": "table", "resourceName": "pnl",     "actions": "read" },
  { "resourceType": "table", "resourceName": "balance", "actions": "read" } ] }'
curl -s -X POST "$AOUDA/api/databases/finance/auth/admin/roles" "${A[@]}" -d '{ "name": "planner", "permissions": [
  { "resourceType": "table", "resourceName": "pnl",     "actions": "read,write" },
  { "resourceType": "table", "resourceName": "balance", "actions": "read,write" } ] }'

for who in viewer planner; do
  uid=$(curl -s -X POST "$AOUDA/api/databases/finance/auth/admin/users" "${A[@]}" \
          -d "{ \"email\": \"$who@example.com\", \"password\": \"Correct-Horse-42!\" }" | jq -r .id)
  curl -s -X PUT "$AOUDA/api/databases/finance/auth/admin/users/$uid/roles" "${A[@]}" \
       -d "{ \"roles\": [ { \"roleName\": \"$who\", \"scope\": \"finance\" } ] }"
  curl -s -X POST "$AOUDA/api/databases/finance/auth/admin/users/$uid/entitlements" "${A[@]}" \
       -d '{ "dimension": "dept", "key": "Retail", "level": "read" }'
done

VIEWER=$(curl -s -X POST "$AOUDA/api/databases/finance/auth/signin" "${H[@]}" \
           -d '{ "email": "viewer@example.com", "password": "Correct-Horse-42!" }' | jq -r .accessToken)
PLANNER=$(curl -s -X POST "$AOUDA/api/databases/finance/auth/signin" "${H[@]}" \
           -d '{ "email": "planner@example.com", "password": "Correct-Horse-42!" }' | jq -r .accessToken)
```

What each of them gets:

| Who | Does | Gets |
|---|---|---|
| viewer | reads `pnl` where `line = NetIncome` | only Retail's rows: 195.00, 202.80, 243.20 |
| viewer | updates any row | `403 INSUFFICIENT_PERMISSIONS` |
| viewer | `explain`s Online's `Margin` | `kind: "noRow"` — exactly what a key with no row answers |
| planner | updates Retail's `Opex` | `200` |
| planner | writes a Retail formula that reads **Online**'s revenue | `403 FORMULA_REFERENCE_NOT_READABLE` |
| planner | writes a Retail formula that reads only Retail rows | `200` |

**A formula may read only rows its writer can read.** Without that rule anyone who may write `pnl` could read any row of any table by
writing a formula over it and reading its value. The check is made when the formula is written, as the writer, for every row the
formula reads; a value is then computed for everyone who may read the formula's row. The planner's refused write:

```bash
curl -s -X POST "$AOUDA/api/databases/finance/tables/pnl/rows" -H "Authorization: Bearer $PLANNER" "${H[@]}" -d '{
  "database": "finance",
  "columns": ["dept", "line", "year", "formula"],
  "data": [ ["Retail"], ["RevenueVsOnline"], [2026],
            [ { "type": "arithmetic", "op": "-",
                "left":  { "type": "cellRef", "key": { "line": { "type": "literal", "value": "Revenue" } }, "column": "amount" },
                "right": { "type": "cellRef", "key": { "dept": { "type": "literal", "value": "Online" },
                                                       "line": { "type": "literal", "value": "Revenue" } }, "column": "amount" } } ] ]
}'
# 403 {"error":"pnl[Retail, RevenueVsOnline, 2026]: column 'amount': the formula reads pnl[Online, Revenue, 2026].amount,
#      a row its writer may not read; …","code":"FORMULA_REFERENCE_NOT_READABLE",…}
```

**C#** — a backend acting for the signed-in planner sends its service key and the planner's token:

```csharp
using var asPlanner = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = url, DatabaseName = "finance", ApiKey = serviceKey, UserToken = plannerJwt,
});
try
{
    await asPlanner.GetTable("pnl").InsertAsync(new Dictionary<string, object?>
    {
        ["dept"] = "Retail", ["line"] = "RevenueVsOnline", ["year"] = 2026,
        ["formula"] = Formula.From(Sub(Line("Revenue"), CellHere("amount", ("dept", "Online"), ("line", "Revenue")))),
    });
}
catch (AoudaFormulaRefusedException e) when (e.Kind == FormulaErrorKind.ReferenceNotReadable)
{
    Console.WriteLine($"{e.StatusCode} {e.ErrorCode}: {e.Message}");   // 403 FORMULA_REFERENCE_NOT_READABLE: …
}
```

**TypeScript**

```typescript
const asPlanner = new AoudaClient({ serverUrl, database, apiKey: serviceKey, userToken: plannerJwt });
try {
  await asPlanner.table("pnl").insert({
    dept: "Retail", line: "RevenueVsOnline", year: 2026,
    formula: Formula.from(fx.sub(line("Revenue"), fx.cellHere("amount", { dept: "Online", line: "Revenue" }))),
  });
} catch (e) {
  if (!(e instanceof FormulaReferenceNotReadableError)) throw e;
  console.log(`${e.statusCode} ${e.code}: ${e.message}`);   // 403 FORMULA_REFERENCE_NOT_READABLE: …
}
```

Two things follow from security being the table's:

- **A formula is visible to whoever may read its row.** There are no private formulas; hide a model by its rows or its table.
- **A value is computed as the database**, once, and shared. A viewer who may read a formula's row sees its value even when the value
  reads rows the viewer cannot read — exactly as if the writer had copied the number by hand. A writer who later loses access to a row
  their formula reads does not invalidate the formula, as a copied number is not recalled.

---

## Where to go next

- [Formulas](formulas.md) — every rule this guide used, the functions, the limits and what is deliberately not there.
- [Freshness](freshness.md) — tokens, and why a token read of a formula table on a replica is refused.
- [Real-time streaming](real-time.md) — subscriptions, resuming, and the `change` message.
- [Data authorization](../auth/authorization.md) — row conditions and entitlements beyond one dimension.
