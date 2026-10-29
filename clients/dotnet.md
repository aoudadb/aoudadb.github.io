---
title: ".NET Client"
nav_order: 2
parent: "Clients"
---

# Aouda .NET Client SDK (`Aouda.Client`)

_Domain: .NET client library for a remote Aouda server_
_Package: `Aouda.Client` on NuGet (targets `net10.0`)_
_Repo: `aouda` (`src/Aouda.Client/`)_

---

## 1) What This Covers

`Aouda.Client` is the official .NET client for an Aouda server. It provides:

- **Queries**: a fluent query builder over `client.GetTable(name)` (untyped) and `client.GetTable<T>()` (typed)
- **Inserts**: single rows, lists of rows, typed objects, batched writers, and column batches (**Lead S13, 0.6.0**)
- **Bulk load**: the `:begin` / `:append` / `:commit` protocol behind one call, from rows or from column batches
  (**Lead S13, 0.6.0**), with resume after a failure
- **Schema, materialized queries, named queries and mutations, streaming, backup and admin APIs**
- **Resilience**: retries that never duplicate a write (**Lead S02, 0.6.0**), and a circuit breaker
- **Authentication**: server auth and application auth

For the same API in-process, without a server, use `Aouda.Embedded` (see
[Getting Started](../getting-started/index.md#3-embedded-mode--in-process-database)). Both implement `IAoudaContext`.

---

## 2) Start Here

| I want to... | Go to |
|---|---|
| Install and connect | §3 Install and connect |
| Query data | §4 Queries |
| Insert rows or objects | §5 Inserts |
| Insert data I already hold as columns | §5 Inserts, §6 Building column batches |
| Load millions of rows | §7 Bulk load |
| Know what is retried after a failure | §8 What the SDK re-sends |
| Handle errors | §9 Errors |
| Authenticate | [Getting Started: SDK usage with server auth](../getting-started/index.md#sdk-usage-with-server-auth) |
| See the wire format | [HTTP API reference](../reference/http-api.md) |

---

## 3) Install and connect

```bash
dotnet add package Aouda.Client
```

The package targets **`net10.0`** (from 0.2.0, **BL-739**); a `net8.0` application stays on 0.1.40 until it
retargets. See [SDK Compatibility](./compatibility.md) for which client goes with which server.

```csharp
using Aouda.Client;

// Server URL and database
using var client = new AoudaClient("http://localhost:5433", "myapp");
```

`AoudaClient` has three constructors:

| Constructor | Use it when |
|---|---|
| `new AoudaClient(string serverUrl, string databaseName)` | You need nothing but the address and the database. |
| `new AoudaClient(AoudaClientOptions options)` | You set options: auth, timeouts, retries. The full auth pipeline (a `401` refreshes the token and retries) is available only here. |
| `new AoudaClient(HttpClient httpClient, AoudaClientOptions? options = null)` | You supply the `HttpClient` (a test server, a custom handler). Its `BaseAddress` is used when `ServerUrl` is not set. Auth is a static header on this client: no refresh on `401`. |

The client is `IDisposable` and `IAsyncDisposable`. Create one per server and database and keep it for the life of the
application.

### Options that matter

| `AoudaClientOptions` property | Default | What it does |
|---|---|---|
| `ServerUrl` | (required) | The server's base URL. |
| `DatabaseName` | (required) | Every data and schema call is scoped to this database. |
| `Timeout` | 30 s | Deadline for one request. Bulk load uses its own, `BulkLoadOptions.RequestTimeout` (§7). |
| `RetryPolicy` | `RetryPolicy.Default` (3 retries, exponential backoff; `Aouda.Client.Resilience`) | Retries of transient failures; see §8 for what a write may and may not repeat. `RetryPolicy.None` turns retries off. |
| `CircuitBreakerPolicy` | `CircuitBreakerPolicy.Default` (opens after 5 failures in 30 s) | While open, calls fail at once with `CircuitBreakerOpenException`. `CircuitBreakerPolicy.Disabled` turns it off. |
| `ServerAuth` / `AppAuth` | none | Server auth (`ServerAuthOptions`: `ApiKey`, `Email` + `Password`, or `Token` + `RefreshToken`) or application auth (`AppAuthOptions`). Mutually exclusive. See [Getting Started](../getting-started/index.md#sdk-usage-with-server-auth). |
| `AutoCreateSchema` | `false` | Typed inserts create a missing table from the type. |
| `AutoReconcileSchema` | `true` | Before the first typed write to a table, compare it with the type and change the table to match (see `ReconcilePolicy`). ⚠️ Set `false` for tables from `aouda.schema.json`: since **BL-1177 (next train)** the server refuses DDL on them, and the write fails with `AoudaSchemaException`. |
| `ReconcilePolicy` | `Unsafe` | `Unsafe` adds missing columns **and drops every column the type does not declare**, including derived and server-stamped columns. `Safe` only adds. Bulk load never reconciles. See [Schema § what `InferenceMode` decides](../guides/schema.md#what-inferencemode-decides-and-what-it-does-not). |
| `TreatMissingAsEmpty` | `false` | A query on a missing table returns no rows instead of an error. |
| `ConsistencyTokenStore` | in-memory, per client | Holds the read-your-writes token. Share one store between clients that must see each other's writes. See [Freshness](../guides/freshness.md). |

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "https://db.example.com",
    DatabaseName = "myapp",
    ServerAuth = new ServerAuthOptions { ApiKey = "mk_srv_..." },
    Timeout = TimeSpan.FromSeconds(30),
});
```

---

## 4) Queries

`GetTable(name)` returns a `RemoteTableQuery`, a fluent builder; `ToListAsync()` runs it and returns
`List<Dictionary<string, object?>>`.

```csharp
var cheap = await client.GetTable("products")
    .Where("price", "lt", 25)
    .Select("id", "name", "price")
    .OrderBy("price")
    .Limit(50)
    .ToListAsync();

long open = await client.GetTable("orders").Where("status", "eq", "open").CountAsync();
```

`GetTable<T>()` (table name from the type, or `[AoudaTable("orders")]` from `Aouda.Abstractions.Attributes`) returns an
`AoudaTable<T>`: the same filters, ordering and paging (`Where`, `Select`, `OrderBy`, `Skip`, `Limit`, `ToListAsync`,
`CountAsync`) with typed results, but no aggregates. Aggregates (`GroupBy`, `GroupByBucket`, `Count`, `Sum`, `Min`, `Max`,
`Avg`, `CountDistinct`, run by `AggregateAsync()`) are on the untyped builder that `GetTable(name)` returns
(**ColumnarRead S16, 0.3.0**):

```csharp
ClientColumnarResult perCustomer = await client.GetTable("orders")
    .Where("status", "eq", "open")
    .GroupBy("customer")
    .Count()
    .Sum("total")
    .AggregateAsync();
// Columns: customer, COUNT, SUM_total — one row per group (perCustomer.ToRows(), or GetColumn<T>(name))
```

Query results arrive as column-batch frames and are read into typed columns; the values are the ones the JSON answer would
give.

Predicates, operators and pagination: [Getting Started: Working with data](../getting-started/index.md#5-working-with-data)
and the [Query guide](../guides/query.md). Named queries: [Named queries](../guides/named-queries.md).

---

## 5) Inserts

### Rows and objects

```csharp
var orders = client.GetTable("orders");

// One row
await orders.InsertAsync(new Dictionary<string, object?> { ["id"] = 1L, ["customer"] = "Acme", ["total"] = 249.99m });

// Many rows: returns the number inserted
int n = await orders.InsertAsync(new List<Dictionary<string, object?>>
{
    new() { ["id"] = 2L, ["customer"] = "Globex", ["total"] = 500m },
    new() { ["id"] = 3L, ["customer"] = "Initech", ["total"] = 75m },
});

// A typed object: [AutoIncrement] properties are filled in from the server's generated values
await client.GetTable<Order>().InsertAsync(new Order { Customer = "Acme", Total = 99.99m });
```

Every `InsertAsync` takes `identityInsert: true` to store explicit `autoIncrement` values as they are (see
[Seeding explicit IDs](../getting-started/index.md#seeding-explicit-ids-identity-insert)). A key left out of a dictionary is
**absent**, which is not `null`: an absent `autoIncrement` cell is generated, an absent column with a default takes its
default, and an explicit `null` is stored as null.

Rows go to the server as one binary column-batch frame once the server has advertised that it reads one, and as JSON column
arrays before that (see [the insert endpoint](../reference/http-api.md#post-apidatabasesdbtablesnamerows)). Nothing about the call
changes.

For rows that arrive one at a time, `orders.CreateBatchWriter()` buffers them and sends them as batched inserts (by default
every 1,000 rows or 20 ms). Its `AddAsync` returns once the row is buffered; a failure surfaces on a later call, on
`FlushAsync`, or on disposal.

### Column batches (**Lead S13, 0.6.0**)

When your data is already in columns (read from Parquet or Arrow, a data frame, another database's export), insert it as a
`ColumnBatch` and skip building a dictionary per row:

```csharp
using Aouda.Client;
using Aouda.Protocol;
using Aouda.Protocol.BulkLoad;

var batch = ColumnBatch.Of(
    ColumnBatchColumn.FromStrings("customer", new[] { "Acme", "Globex", "Initech" }),
    ColumnBatchColumn.FromDecimals("total", new[] { 249.99m, 500m, 75.5m }, scale: 2),
    ColumnBatchColumn.FromTimestamps("placedAt", new DateTime?[] { DateTime.UtcNow, null, DateTime.UtcNow }));

InsertResult result = await client.GetTable("orders").InsertAsync(batch);
// result.RowsInserted == 3
```

`RemoteTableQuery.InsertAsync(ColumnBatch batch, CancellationToken ct = default, bool identityInsert = false)` returns the
server's `InsertResult`:

- `RowsInserted`: the rows inserted.
- `GeneratedValues`: the values the server generated, as column arrays. `Columns` names the generated columns and `Data`
  holds one array per column with one cell per row of the batch, `null` where the row gave its own value. Read one row with
  `ForRow(row)` (a dictionary, or `null` when that row generated nothing) or one value with `TryGet(row, column, out value)`.
  Cells arrive as JSON values (`JsonElement`). `GeneratedValues` is `null` when nothing was generated.

In the example the table's `autoIncrement` key `id` is not in the batch, so every row's id is generated:

```csharp
using System.Text.Json;

if (result.GeneratedValues is { } generated && generated.TryGet(0, "id", out var value))
{
    long firstId = value is JsonElement e ? e.GetInt64() : Convert.ToInt64(value);
}
```

**Absent is not null in a batch either.** A cell marked absent (the column's absent bitmap, §6), or a column the batch does
not carry at all, is generated if it is an `autoIncrement` column and takes its default if the column has one. A cell marked
null is stored as null, and a null `autoIncrement` cell is not generated.

How it is sent: as **one column-batch frame**, written straight from the batch's arrays, once the server has advertised frames
(the `Accept-Post` header on any earlier response from a `/rows` endpoint); as **JSON column arrays** of the same rows before
that, for a batch that holds a column no frame can carry, and for one over 1,000,000 rows or 4,096 columns. Either way the
table ends up with the same values, with one exception: a `NaN` or `±Infinity` in a double column has no JSON form, so the
JSON path throws `ArgumentException` for it before sending anything, while a frame writes it. On a new client the first
column-batch insert goes as JSON (nothing has advertised frames yet), so a batch holding one fails there. The batch is
checked before anything is sent (`ColumnBatch.Validate()`, §6), so a malformed batch throws `ArgumentException` naming the
column and row, and nothing is inserted. An empty batch sends nothing.

Like every insert, a column-batch insert is re-sent only after a failure that proves the server applied nothing (§8).

---

## 6) Building column batches (**Lead S13, 0.6.0**)

A `ColumnBatch` (namespace `Aouda.Protocol.BulkLoad`) is a set of named columns of the same length. Build each column with a
static factory on `ColumnBatchColumn`, then the batch with `ColumnBatch.Of(...)`.

### The factories

| Factory | Values | Sent as |
|---|---|---|
| `FromInt64s(name, long[] values, byte[]? nullBits = null, byte[]? absentBits = null)` | 64-bit integers | `Int64` |
| `FromDoubles(name, double[] values, nullBits, absentBits)` | doubles | `Double` |
| `FromBools(name, bool[] values, nullBits, absentBits)` | booleans | `Bool` |
| `FromTimestamps(name, DateTime[] values, nullBits, absentBits)` | instants. A `DateTimeKind.Local` value is converted to UTC; an `Unspecified` one is taken as UTC. | `Timestamp` |
| `FromTimestampTicks(name, long[] unixTicks, nullBits, absentBits)` | instants as 100-nanosecond ticks since the Unix epoch, UTC (`ColumnBatchTime.ToUnixTicks` converts a `DateTime` or `DateTimeOffset`) | `Timestamp` |
| `FromDecimals(name, decimal[] values, byte scale, nullBits, absentBits)` | decimals at one scale (0–18), each sent as its unscaled 64-bit integer (`123.45` at scale 2 is `12345`). A value with more decimal places than `scale`, or one whose unscaled value does not fit a `long`, throws `ArgumentException` naming the column and row; nothing is rounded. | `ScaledDecimal` |
| `FromScaledDecimals(name, long[] unscaled, byte scale, nullBits, absentBits)` | unscaled values you already have (`12345` at scale 2 is `123.45`) | `ScaledDecimal` |
| `FromStrings(name, string?[] values, byte[]? absentBits = null)` | strings, dictionary-encoded for you (each distinct value stored once); a `null` element is a null row | `String` |
| `FromDictionary(name, string[] dictionary, int[] codes, nullBits, absentBits)` | a string column you already hold encoded (a Parquet or Arrow dictionary column): the distinct values and one index per row. A null or absent row's code is ignored, and the dictionary may hold values no row uses. | `String` |
| `FromNulls(name, int rows, byte[]? absentBits = null)` | a column whose every row is null (or, with `absentBits`, absent) | `Null` |

A `Decimal(p,s)` column stores a scaled 64-bit integer, so `FromDecimals` at the column's scale (or `FromScaledDecimals`) sends
exactly what it stores. See [`Decimal(p,s)`](../guides/schema.md#decimalps-a-decimal-stored-as-a-scaled-integer-columnarcore-s13-020).

**Nullable overloads.** `FromInt64s`, `FromDoubles`, `FromBools`, `FromTimestamps` and `FromDecimals` also take a nullable array
(`long?[]`, `double?[]`, `bool?[]`, `DateTime?[]`, `decimal?[]`, plus `scale` for decimals, then an optional `absentBits`). A
`null` element is a null row and the null bitmap is built for you:

```csharp
var qty = ColumnBatchColumn.FromInt64s("qty", new long?[] { 10, null, 30 });
```

### Null and absent bitmaps

Every factory takes optional bitmaps: **bit *i* is row *i***, least significant bit first, at least `ceil(rows / 8)` bytes.

- **`nullBits`**: the row is null. Its value in the array is ignored.
- **`absentBits`**: the row does not carry this column at all. On an insert, an absent `autoIncrement` cell is generated and an
  absent cell of a column with a default takes the default. ⚠️ A **bulk load** does not apply defaults: there an absent cell is
  stored as null (an absent `autoIncrement` cell is still generated), **BL-1104**.

```csharp
static byte[] Bits(int rows, Func<int, bool> isSet)
{
    var bits = new byte[(rows + 7) / 8];
    for (int i = 0; i < rows; i++)
        if (isSet(i)) bits[i >> 3] |= (byte)(1 << (i & 7));
    return bits;
}

// Rows 0 and 2 take the column's default; row 1 gives "rush".
var note = ColumnBatchColumn.FromStrings("note", new string?[] { null, "rush", null }, absentBits: Bits(3, i => i != 1));
```

### Making the batch

- **`ColumnBatch.Of(params ColumnBatchColumn[] columns)`** takes its row count from the columns, which must agree; a
  `FromNulls` column counts as its `rows`. It throws `ArgumentException` when the lengths differ or there is no column.
- **`new ColumnBatch(int rowCount, IReadOnlyList<ColumnBatchColumn> columns)`** sets the row count yourself. Arrays longer than
  `rowCount` are allowed and the rows past it are not sent, so you can refill the same large arrays and send a shorter batch.
- **`ColumnBatchBuilder`** builds a batch row by row when your data arrives as rows but you still want to hand the SDK batches:

```csharp
var builder = new ColumnBatchBuilder();
foreach (var trade in trades)
{
    builder.BeginRow();
    builder.Column("symbol").SetString(trade.Symbol);
    builder.Column("price").SetDecimal(trade.Price);
    builder.Column("ts").SetTimestampTicks(ColumnBatchTime.ToUnixTicks(trade.Time));
    builder.EndRow();   // a column this row did not set is absent in it
}
ColumnBatch batch = builder.Build();   // the builder is reset for the next batch
```

  The builder decides each column's kind from its values: an integer column that meets a fraction becomes a decimal at the
  largest scale it meets. Values that disagree otherwise, and `SetObject`, make an object column, which no frame can carry: a
  batch with one is sent as JSON column arrays instead (§7).

### Checking a batch

`batch.Validate()` checks the batch the way the server's frame reader would and throws `ArgumentException` naming the column (and
row) of the first problem: an empty or repeated column name, a value array or bitmap shorter than the rows, a string code
outside its dictionary or pointing at a `null` dictionary entry on a row that is neither null nor absent, a timestamp a
`DateTime` cannot hold, a scale above 18. The SDK calls it before sending any batch; call it yourself to fail earlier.

### The arrays are not copied

A factory keeps your array as it is. The arrays are read when the batch is sent: by the time `InsertAsync` returns, or, in a
bulk load, once the SDK asks your source for the next batch. Until then, do not change them. After that you may reuse them.
`FromTimestamps`, `FromDecimals`, `FromStrings` and the nullable overloads convert into new arrays, so those inputs are free at
once.

---

### Array columns (**BL-035, next train**) {#array-columns}

(**BL-035, next train**) The six [array column types](../guides/array-columns.md) read and write as CLR arrays, on every read surface (frames and
JSON, queries, named queries, subscriptions, typed and untyped) and both wires:

| Server type | CLR type |
|---|---|
| `Double[]` (**BL-035, next train**) | `double[]` |
| `Float32[]` (**BL-035, next train**) | `float[]` |
| `Int32[]` (**BL-035, next train**) | `int[]` |
| `Int64[]` (**BL-035, next train**) | `long[]` |
| `Byte[]` (**BL-035, next train**) | `byte[]` |
| `String[]` (**BL-035, next train**) | `string[]` |

A null cell is `null` and an empty array is empty. The `byte[]` of a `Byte[]` column is told from a scalar `Byte` by the column's
type, never by the value's shape: sent to a scalar `Byte` column the server refuses it.

```csharp
var samples = client.GetTable("Samples");

// a dictionary row with CLR arrays (sent as JSON)
await samples.InsertAsync(new Dictionary<string, object?>
{
    ["Id"] = 300L,
    ["D"] = new[] { 1.5, -0.0, 5e-324 },
    ["F"] = new[] { 0.1f },
    ["I"] = new[] { 1, 2, 3 },
    ["L"] = new[] { 9007199254740993L },
    ["B"] = new byte[] { 1, 2, 3 },
    ["S"] = new[] { "a", "日本語" },
});

var rows = await samples.Where("Id", "eq", 300L).ToListAsync();
// rows[0]["D"] is a double[] { 1.5, -0.0, 5E-324 } — the bits of -0 are kept (8000000000000000);
// rows[0]["F"] is a float[], ["L"] a long[], ["B"] a byte[], ["S"] a string[]
```

- **The arrays in a result are shared, not copied per read: do not change them.** Copy one (`(double[])value.Clone()`) before
  you do.
- **A value the SDK cannot read as its column's type throws** (`InvalidDataException`); nothing maps to a default. Mapping to an
  object is **exact**: `ToObjects<T>` assigns a property whose type is assignable from the CLR type above (`double[]`,
  `IReadOnlyList<double>`, `object`) and throws `InvalidCastException` otherwise — a `double[]` property for a `Float32[]` column
  throws, no element is converted. Typed subscriptions keep System.Text.Json's mapping, exact for the property types above.
  `ToDataTable` columns have the array type.
- **Writes** take the same arrays: dictionary rows (as JSON, never a frame), `UpdateAsync`, named-mutation arguments and
  `batchParam` rows. A NaN or infinity element is refused by the server (`AoudaRequestException`, status 400), and locally
  (`ArgumentException`, before sending) in a `batchParam` row and on the write stream:

  ```text
  AoudaRequestException: Column 'D': Element 0 of the Double[] value is NaN; array elements must be finite numbers (NaN and ±Infinity are refused).
  AoudaRequestException: ARRAY_COLUMN_UNSUPPORTED: column 'Samples.D' is Double[]; an array column cannot be used in a where …
  ```

  The client does not check the limits itself; the server's refusal comes back as the typed exception.
- **A column batch** takes the factories `ColumnBatchColumn.FromDoubleArrays`, `FromFloat32Arrays`, `FromInt32Arrays`,
  `FromInt64Arrays`, `FromByteArrays` and `FromStringArrays(name, T[]?[] rows, absentBits)`: a `null` row is a null cell, and the
  rows are **copied** into the column (unlike the scalar factories). `Validate()` checks the limits before a send.

  ```csharp
  var batch = ColumnBatch.Of(
      ColumnBatchColumn.FromInt64s("Id", new[] { 301L, 302L }),
      ColumnBatchColumn.FromDoubleArrays("D", new double[]?[] { new[] { 1.0, 2.0 }, null }),
      ColumnBatchColumn.FromStringArrays("S", new string[]?[] { new string[0], new[] { "x" } }));
  await samples.InsertAsync(batch);   // 301: D=[1,2] S=[]   302: D=null S=[x]
  ```
- **POCO schema inference and POCO writes with an array property are refused** (`NotSupportedException`) until Embedded maps CLR
  array properties (BL-1213). Reading into a POCO with an array property works.
- **The write stream** (`stream_rows`) holds at most `Aouda:WebSocket:StreamingWrites:MaxBatchBytes` (1 MiB by default) of JSON a
  message, so one large array row is refused there (`INVALID_STREAM_ROWS`); use an insert or a named mutation.
- **The C# named-client generator** (`aouda generate csharp`, [Build apps](../guides/build-apps.md)) writes `double[]`, `float[]`, `int[]`, `long[]`, `byte[]` and `string[]` for
  array columns and parameters (a required parameter defaults to `System.Array.Empty<T>()`).

## 7) Bulk load

Bulk load is the high-throughput path: rows are streamed in `:append` calls into one session and become visible together at
`:commit`. The SDK runs the whole protocol in one call and returns a `BulkLoadJobHandle` once the load is durable. The protocol,
its guarantees and its sizing advice are in the [Bulk Load guide](../guides/bulk-load.md).

### From rows

```csharp
IAsyncEnumerable<IReadOnlyDictionary<string, object?>> rows = ReadRowsAsync();

BulkLoadJobHandle handle = await client.BulkLoadAsync("orders", rows, new BulkLoadOptions
{
    IdempotencyKey = "orders-2026-10-18",
});
Console.WriteLine($"{handle.RowsLoaded} rows, job {handle.JobId}");
```

Overloads take an `IAsyncEnumerable<IReadOnlyDictionary<string, object?>>` or an
`IReadOnlyList<IReadOnlyDictionary<string, object?>>`. The same calls exist on a table (`client.GetTable("orders").BulkLoadAsync(rows)`)
and a typed table loads objects (`client.GetTable<Order>().BulkLoadAsync(orders)`, from an `IEnumerable<T>` or
`IAsyncEnumerable<T>`). The SDK packs the rows into column-batch frames itself.

### From column batches (**Lead S13, 0.6.0**)

The fast path for columnar data: each batch is written to the server as frames **straight from its arrays**, with no row objects
in between.

```csharp
using Aouda.Client;
using Aouda.Protocol.BulkLoad;

async IAsyncEnumerable<ColumnBatch> ReadBatchesAsync()
{
    await foreach (var group in ReadRowGroupsAsync())   // e.g. one Parquet row group at a time
    {
        yield return ColumnBatch.Of(
            ColumnBatchColumn.FromInt64s("id", group.Ids),
            ColumnBatchColumn.FromDictionary("symbol", group.SymbolDictionary, group.SymbolCodes),
            ColumnBatchColumn.FromScaledDecimals("price", group.PriceUnscaled, scale: 4),
            ColumnBatchColumn.FromTimestampTicks("ts", group.UnixTicks));
    }
}

var handle = await client.BulkLoadAsync("trades", ReadBatchesAsync(), new BulkLoadOptions
{
    IdempotencyKey = "trades-2026-10-18",
});
```

| Method | Batches |
|---|---|
| `AoudaClient.BulkLoadAsync(string tableName, IAsyncEnumerable<ColumnBatch> batches, BulkLoadOptions? options = null, CancellationToken ct = default)` | a stream |
| `AoudaClient.BulkLoadAsync(string tableName, IReadOnlyList<ColumnBatch> batches, …)` | a list |
| `AoudaClient.BulkLoadAsync(string tableName, ColumnBatch batch, …)` | one batch |
| `AoudaClient.BulkLoadMultiTableAsync(IReadOnlyList<string> tables, IAsyncEnumerable<ColumnBatch> batches, …)` | several tables in one atomic job: every batch carries a `_table` string column naming each row's table |
| `RemoteTableQuery.BulkLoadAsync(IAsyncEnumerable<ColumnBatch>` / `IReadOnlyList<ColumnBatch>` / `ColumnBatch, …)` | the same three, on `client.GetTable("trades")` |

**How batches become `:append` bodies.** A body holds up to `AppendBatchSize` rows (lowered to the server's `maxRowsPerAppend`
when that is smaller) and about `MaxAppendBytes` bytes, as consecutive frames, numbered across the job's bodies (**Lead S21a, next
train**). Several small batches share one body, one frame each; a large batch is cut across several bodies. Batches of a few thousand rows or more load fastest, since each batch is at
least one frame. Your source is read on a thread-pool thread, one batch at a time and at most one body ahead of what the server
has accepted: the next body is built while the previous one is in flight.

**Each batch is checked before any of it is sent** (`Validate()`, §6). A malformed batch throws `ArgumentException` naming its
column, and the load is not committed. The rows of earlier batches that were already appended stay in the open session, which the
server reclaims when it has been idle long enough. Until then it holds the table's bulk-load lock, so a new load into that
table without the same `IdempotencyKey` waits (or fails with `ConflictPolicy = BulkLoadConflictPolicy.FailFast`). To avoid that
when batches come from a pipeline you do not control, call `Validate()` as you build them.

**The JSON fallback.** A batch with a column no frame can carry (an object column from a `ColumnBatchBuilder`) is sent as JSON
column arrays of the same rows, after the frames before it. The same happens to every batch when the server does not accept
frames. The table ends up with the same values either way — except that a `NaN` or `±Infinity` in a double column has no
JSON form and makes such a batch throw `ArgumentException` — and it is still one load with one resume cursor.

**Resume works inside a batch.** If a load fails part-way (§8), run it again with the same `IdempotencyKey` and the same batches
from the start: the server says which row it needs next, and the SDK skips everything before it, even when that row is in the
middle of a batch. **Cancelling a load is not a failure to resume from:** when its `CancellationToken` fires, the SDK aborts the
job (a best-effort `:abort`), and a re-run with the same key starts a fresh job and sends every row again. So does a re-run
after a server restart, which an open job does not survive.

### Several jobs into one table (**Lead S18b, 0.6.0**)

A load that arrives as several jobs — a file per day, a batch per hour — goes through `BulkLoadJobsAsync`, not a loop of
`BulkLoadAsync` calls. It sends job N+1's `:begin` and `:append`s while job N commits (the server queues them behind the
table's bulk-load lock), so a commit overlaps the next job's sending instead of adding to it, and it yields each job's handle in
job order, as its commit returns. (**Lead S21b, 0.6.0**) A job's last column-batch body commits it in its end frame — no
`:commit` request — and job N+1 is begun once that body of job N is written, so N's finalize and commit overlap N+1's rows too:

```csharp
IEnumerable<IReadOnlyList<ColumnBatch>> days = ReadDays();   // or IAsyncEnumerable<ColumnBatch> per job, or row streams

await foreach (var handle in client.BulkLoadJobsAsync("trades", days, new BulkLoadOptions { IdempotencyKey = "trades-2026-10" }))
    Console.WriteLine($"{handle.JobId}: {handle.RowsLoaded} rows, token {handle.Token}");
```

| Method | Each job is |
|---|---|
| `AoudaClient.BulkLoadJobsAsync(string tableName, IEnumerable<IAsyncEnumerable<ColumnBatch>> jobs, BulkLoadOptions? options = null, CancellationToken ct = default)` | a stream of batches |
| `AoudaClient.BulkLoadJobsAsync(string tableName, IEnumerable<IReadOnlyList<ColumnBatch>> jobs, …)` | a list of batches |
| `AoudaClient.BulkLoadJobsAsync(string tableName, IEnumerable<IAsyncEnumerable<IReadOnlyDictionary<string, object?>>> jobs, …)` | a stream of row objects |

- **Each job is a job of its own**: committed, visible and answered on its own, in order. Its handle is exactly what
  `BulkLoadAsync` would have returned for it.
- **One job sending and one committing** (**Lead S21b, 0.6.0**; it was "one `:append` and one `:commit` in flight"). Job
  N+2 is begun only after job N's handle. The next job is asked of `jobs` once the previous job's rows are all sent.
- **The first failure ends the sequence**, after every earlier job's handle, and no later job commits: (**Lead S21b, next
  train**) each job is begun naming the one before it (`afterJobId`), and the server refuses the commit of a job whose predecessor
  did not commit. The job in flight when you stop reading (`break`) early is aborted — unless its commit point had passed, in which
  case it is committed (its handle is not yielded).
- **`IdempotencyKey` keys each job**: job `i` is keyed `{key}.{i}`. Repeating the call with the same key and the same jobs replays
  the jobs that committed (their handles say `WasResumed`) and resumes the first that did not.
- **`ConflictPolicy = FailFast` runs the jobs one at a time**: a job queued behind the lock would be refused.
- `Progress` may be called from two jobs at once.
- Each commit still drains its job into segments of its own: prefer one long job where you can
  ([Sizing a session](../guides/bulk-load.md#sizing-a-session-fewer-longer-one-commit)). Jobs are for loads that arrive as several.

### Options that matter

`BulkLoadOptions` is a record; set what you need with an object initializer.

| `BulkLoadOptions` property | Default | What it does |
|---|---|---|
| `IdempotencyKey` | a new GUID | Names the job. Use a stable key in production: re-running a load with the same key resumes it, and re-running one that already committed returns its handle without sending a row. |
| `AppendBatchSize` | 50,000 | Most rows in one `:append` body. Lowered to the server's `maxRowsPerAppend` (100,000 by default) when that is smaller. |
| `MaxAppendBytes` | 8 MiB | Most bytes in one `:append` body; a body closes at whichever limit it reaches first. `0` disables the byte bound. |
| `RequestTimeout` | 10 minutes | Deadline for each bulk-load HTTP call (not for the job, and not `AoudaClientOptions.Timeout`). A caller-supplied `HttpClient`'s own `Timeout` still caps it. |
| `WaitForDeferredWork` | `false` | `true` waits for deferred work (CSC mirror, RaBitQ, PK reconcile) before returning; otherwise watch `handle.DeferredWorkCompletion`. |
| `MqWait` | `null` (no wait) | How long `:commit` waits for the materialized queries the load reaches to be current; at most 10 minutes. The answer is `handle.MqStatus`. Keep `RequestTimeout` above it. |
| `PostLoadMqBehavior` | `ClientPostLoadMqBehavior.Auto` | `Skip` leaves the load's materialized queries behind until you refresh them. |
| `WriteConcern` / `WriteConcernTimeout` | `Acknowledged` / 5 minutes | Replica acknowledgement at commit. |
| `IdentityInsert` | `false` | Store explicit `autoIncrement` values as they are; every row must give them. |
| `Durability` | `null` (the database's level for a load) | (**Lead S26c, 0.6.0**) `BulkLoadDurability.Strict` or `Os`. `null` is `Os` in a database at `os`, `Strict` everywhere else. `Os` skips the fsync before the commit: a power loss before the server has synced the job drops it whole, and its status reads `lost`. See [A load's durability](../guides/bulk-load.md#a-loads-durability-strict-or-os-lead-s26c-060). |
| `ApplyTransforms` / `PreTransformed` | `false` / `false` | A table with derived columns, checks or transforms needs exactly one of them. |
| `ConflictPolicy` | `BulkLoadConflictPolicy.Block` | `FailFast` fails at once when another load holds the table. |
| `Progress` | none | An `IProgress<BulkLoadProgress>` called after each `:append` and at commit. `BulkLoadProgress` carries deferred-work counters, not rows: the per-`:append` report is empty, so count rows in your source. |

The handle reports `RowsLoaded`, `PerTableRowCounts`, `SegmentsCreated`, `ExpiredRows`, `WasResumed`, `Token` (the commit's
consistency token), `Durability` (the job's level; **Lead S26c, 0.6.0**), `MqStatus` / `MqFrontierToken`, and offers
`WaitForMaterializedQueriesAsync()` and `GetProgressAsync()`.
A handle returned for a key whose job had already committed (nothing sent) has the job's `RowsLoaded` and `Token`, but an empty
`PerTableRowCounts` and `SegmentsCreated` 0.

---

## 8) What the SDK re-sends, and what it does not

`RetryPolicy` retries transient failures (a connection that failed, a timeout, a `503`) for reads and for writes a repeat
cannot change, at most `MaxRetries` times (3 by default: four attempts in all), with exponential backoff. A **capacity
refusal** — `503 MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` or `429 SERVER_AT_CAPACITY` (`AoudaCapacityException`) —
is waited out: a `Retry-After` in seconds is the least the SDK waits before the next attempt; without one (or with an HTTP
date, which is not read) the backoff applies. A write whose repeat is **not** a no-op is treated differently
(**Lead S02, 0.6.0**; before, a timed-out insert was re-sent and could insert its rows twice), because re-sending one the
server already applied would apply it twice:

- **Inserts** (rows, typed objects, column batches), updates, deletes, named mutations and a bulk-load `:commit` are re-sent
  **only after a failure that proves the server applied nothing**: a connection that was never opened (refused, unreachable,
  or a host name that did not resolve), a TLS handshake that failed before the request was sent, or a capacity refusal, which
  the server answers only for a request it did not apply. Any other `503`, a `504`, a **timeout or a lost answer** proves
  nothing — the server may have committed — so the error reaches you instead of a second copy of the rows. Check before you
  insert again. (**Lead group 3 review, 0.6.0**) A failure after a write was applied is never answered as a capacity
  refusal.
- **A `:commit` refused for capacity has failed its job.** The server answers every repeat of it with the same `503`, so the
  SDK's re-sends end in `AoudaCapacityException`. Wait its `RetryAfter`, then run the load again: it starts a fresh job and
  sends every row (the key is free again).
- **A bulk-load `:append` is re-sent only by the SDK, after asking where the job is** (**Lead S21a, 0.6.0**). A job's frames
  are numbered and the server applies each number once, so a body sent again loads none of its rows twice. An `:append` that
  fails in transit (a connection error, a timeout, a `503`) is answered by a `:begin` with the job's key — which stops the
  server's stale request and answers the job's `nextSequence` — and then the same body again, up to four attempts with a short
  back-off (a `503`'s `Retry-After` when it gives one). Only then does it throw `BulkLoadAppendFailedException`, carrying the
  `IdempotencyKey`, `RowsSent` and `RowsDurablyCommitted`. Recover by running the same load again with the same `IdempotencyKey`,
  the same source and the same body bounds: the SDK sends `:begin` with that key, the server answers with the job's next frame,
  and the SDK sends nothing below it — and throws `BulkLoadCursorMismatchException`, sending nothing, if the frames it skips do
  not carry the rows the server holds (until Lead S21a it resumed by rows, from `resumeFromRow`, and threw on the first failed
  `:append`). Do not add a retry of your own around `:append`. A `:commit` names the frames the SDK sent, and the server commits
  nothing unless it applied exactly those. (**Lead S21b, 0.6.0**) The body that commits a job is recovered the same way, with
  two more outcomes: if the job committed before the answer was lost, the keyed `:begin` replays it and the SDK returns its handle
  (`WasResumed`); if its commit is still running, the server says so and the SDK waits (not counted as an attempt, up to
  `RequestTimeout`), then asks again.
- **Other `:append` failures are not wrapped.** A `500`, a `413` or another `4xx` surfaces as the exception for its status
  (§9: `AoudaException`, `AoudaRequestException`, …), and three codes as their own exceptions: `BULK_LOAD_INVALID_STATE` (the job is no longer
  open) as `BulkLoadAbortedException`, `BULK_LOAD_MISSING_DISCRIMINATOR` as `BulkLoadMissingDiscriminatorException` and
  `BULK_LOAD_CURSOR_MISMATCH` as `BulkLoadCursorMismatchException` (its `NextSequence`, `ServerRows` and `ClientRows` say where
  the job and the load disagree). A `400` for the body's rows leaves the job open, so the same key resumes it from the frame the
  server needs next — and fails there again until the source is fixed.
- **Set your own `IdempotencyKey` if you may need to resume.** (**Lead group 3 review, 0.6.0**) A failed load whose key
  the SDK generated is aborted (a best-effort `:abort`), since nobody else knows the key — with two exceptions. A transient
  `:append` failure keeps the job: its `BulkLoadAppendFailedException` hands you the generated key in `IdempotencyKey`, and
  running the load again with that key resumes it. And once `:commit` has been sent the job is not aborted: the server's
  commit decides it. A job under your own key is never aborted for a failure, only for a cancellation (§7).
- `:begin` carries the idempotency key, so a repeat of it finds the same job.

A `CreateBatchWriter` writer inherits the insert rule: a batch whose answer was lost surfaces as an error, never silently.

---

## 9) Errors

Server errors are `AoudaException` (namespace `Aouda.Abstractions`) or a subclass, with `ErrorCode`, `StatusCode`, `RequestId`
and `Details`; the error codes are listed in the [HTTP API reference](../reference/http-api.md). The ones a client most often
handles (namespace `Aouda.Client` unless noted):

| Exception | When |
|---|---|
| `AoudaRequestException` (`Aouda.Abstractions`) | The server refused the request: `400`, `403` or `409`; `ErrorCode` says why. `400 PARTITION_FILTER_REQUIRED` is its subclass `AoudaPartitionFilterRequiredException`. |
| `AoudaAuthenticationException` / `AoudaNotFoundException` (`Aouda.Abstractions`) / `AoudaMisdirectedRequestException` | `401` / `404` / `421`. |
| `AoudaCapacityException` | The server is short of capacity (`503 MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`, `429 SERVER_AT_CAPACITY`); `RetryAfter` says when to come back. Retried by the policy first (§8). A subclass of `AoudaServiceUnavailableException`, which is any other `503`. |
| `AoudaConnectionException` / `AoudaTimeoutException` | The connection failed, or the request timed out (a `504` too). For an insert, the rows may or may not have been written (§8). |
| `AoudaException` | Any other status — a `500`, a `413`, a `429` other than `SERVER_AT_CAPACITY` — with `StatusCode` set. |
| `CircuitBreakerOpenException` | The circuit breaker is open; the call was not attempted. |
| `ArgumentException` | A column batch failed `Validate()` (§6), or a factory refused its input (a decimal with too many places, a bitmap too short). Nothing was sent for that batch. |

Bulk load adds its own (namespace `Aouda.Client.Exceptions`):

| Exception | When |
|---|---|
| `BulkLoadAppendFailedException` | An `:append` failed in transit (a connection error, a timeout, a `503`). Resume with its `IdempotencyKey` (§8). |
| `BulkLoadTableLockedException` | Another load holds a table and `ConflictPolicy` is `FailFast`. `Tables`, `ActiveJobId`. |
| `BulkLoadDuplicatePkException` | Duplicate primary keys under `PkUniquenessMode.Strict`; nothing is committed. |
| `BulkLoadAbortedException` | The job is no longer open (`409 BULK_LOAD_INVALID_STATE` on `:append`): an operator force-aborted it, it failed, or a reconnect with the same key superseded this call. |
| `BulkLoadMissingDiscriminatorException` | A multi-table load's row has no `_table`. |
| `BulkLoadCursorMismatchException` | The server's durable cursor disagrees with what the client sent. |
| `BulkLoadProtocolException` | The server's answer to a phase was unusable (an empty body). Carries `Phase`, `JobId` and the cursors. |
| `InvalidBulkLoadOptionsException` | The options are invalid or do not fit the server (e.g. `SkipReplication` on a cluster). |

---

## 10) Related

- [Getting Started](../getting-started/index.md): server mode, embedded mode, schema, auth
- [Bulk Load guide](../guides/bulk-load.md): sessions, sizing, materialized queries, recovery
- [HTTP API reference](../reference/http-api.md): the wire contract, [column arrays](../reference/http-api.md#column-arrays-the-write-body)
  and [the column-batch frame](../reference/http-api.md#the-column-batch-frame-acb2)
- [TypeScript Client](./typescript.md): the same server from TypeScript
- [SDK Compatibility](./compatibility.md): which client goes with which server
