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
| Subscribe to a table or a named query, and know which listener takes which | §8a Subscriptions |
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
| `ApiKey` (**BL-1385, 0.11.0**) | none | An Aouda API key of any kind: `mk_svc_`, `mk_scp_`, `mk_srv_`, `mk_adm_`, `mk_anon_`, `mk_pub_` or a custom `mk_` key. Sent as `Authorization: Bearer`; the server resolves the kind. A value without the `mk_` prefix is refused at construction. Replaces `AppAuth.ApiKey`, `ServerAuth.ApiKey` and `AuthAdmin`, which are removed. `Databases.ListAsync` / `CreateAsync` need a `mk_srv_` key here. |
| `UserToken` (**BL-1385, 0.11.0**) | none | A user's JWT sent as `X-User-Token` beside the key; needs a `mk_svc_` or `mk_srv_` `ApiKey`. Moved here from `AppAuthOptions` / `ServerAuthOptions`. |
| `ServerAuth` / `AppAuth` | none | A signed-in session, not a key: server auth (`ServerAuthOptions`: `Email` + `Password`, or `Token` + `RefreshToken`) or application auth (`AppAuthOptions`: `Token` + `RefreshToken`). Mutually exclusive with each other, and with `ApiKey` (a key and a session are two credentials). See [Getting Started](../getting-started/index.md#sdk-usage-with-server-auth). |
| `AuthFailurePolicy` (**BL-1386, 0.11.0**) | nothing happens | Opt-in: `FailFast` throws `AoudaAuthenticationFatalException` for a rejected key instead of a failure a caller may retry later; `OnSustained` is called once after `SustainedAfter` (default 3) failures in a row. See [Getting Started](../getting-started/index.md#a-rejected-key-is-not-a-retry-bl-1386-0110). |
| `SubscriptionConsumerQueueCapacity` (**BL-1421, 0.12.0**) | `10_000` | The unread-event bound of every subscription consumer on this client (table and named-query subscribes, typed tables too). Validated `>= 1` when the client is built (`ArgumentOutOfRangeException`-style refusal at construction). `SubscribeOptions.ConsumerQueueCapacity` overrides it for one subscription. See §8a. |
| `AutoCreateSchema` | `false` | Typed inserts create a missing table from the type. |
| `AutoReconcileSchema` | `true` | Before the first typed insert to a table, compare it with the type and change the table to match (see `ReconcilePolicy`). A typed update does not reconcile. (**BL-1178, 0.9.0**) ⚠️ Set `false` for tables from `aouda.schema.json`: since **BL-1177 (0.9.0)** the server refuses DDL on them, and an insert that needs to add or drop a column fails with `AoudaSchemaException`. |
| `ReconcilePolicy` | `Safe` | Default `Safe` only adds columns the row type has and the table lacks. `Unsafe` is opt-in and drops non-key columns a row type omits; a primary-key column stays. A typed update does not reconcile. (**BL-1178, 0.9.0**) Bulk load never reconciles. See [Schema § what `InferenceMode` decides](../guides/schema.md#what-inferencemode-decides-and-what-it-does-not). |
| `TreatMissingAsEmpty` | `false` | A query on a missing table returns no rows instead of an error. |
| `ConsistencyTokenStore` | in-memory, per client | Holds the read-your-writes token. Share one store between clients that must see each other's writes. See [Freshness](../guides/freshness.md). |

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "https://db.example.com",
    DatabaseName = "myapp",
    ApiKey = "mk_srv_...",
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

A row type may be a positional record or any type with a single public constructor and no parameterless one: each constructor
parameter is bound to the column of the same name (**BL-1390, 0.11.0**; see [Getting Started](../getting-started/index.md)).

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

### Array columns (**BL-035, 0.9.0**) {#array-columns}

(**BL-035, 0.9.0**) The six [array column types](../guides/array-columns.md) read and write as CLR arrays, on every read surface (frames and
JSON, queries, named queries, subscriptions, typed and untyped) and both WebSocket wires (JSON and MessagePack):

| Server type | CLR type |
|---|---|
| `Double[]` (**BL-035, 0.9.0**) | `double[]` |
| `Float32[]` (**BL-035, 0.9.0**) | `float[]` |
| `Int32[]` (**BL-035, 0.9.0**) | `int[]` |
| `Int64[]` (**BL-035, 0.9.0**) | `long[]` |
| `Byte[]` (**BL-035, 0.9.0**) | `byte[]` |
| `String[]` (**BL-035, 0.9.0**) | `string[]` |

A null cell is `null` and an empty array is empty. The `byte[]` of a `Byte[]` column is told from a scalar `Byte` by the column's
type, never by the value's shape: sent to a scalar `Byte` column it travels as base64 text and is refused as not a number —
except a base64 text made only of digits, which is read as that number (BL-1265). Do not send a `byte[]` to a `Byte` column.

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
  throws, no element is converted. Typed subscriptions are **not** exact: they go through System.Text.Json, so an `int[]` column fills a `double[]` property and a
  `float[]` property is filled from the widened text, an `object` property gets a `JsonElement`, and a failure arrives as an
  `InvalidOperationException` (BL-1245). Give a typed subscription the exact CLR type above.
  A `Timestamp` column fills a `DateTime`, `DateTime?` or `DateTimeOffset` property in the snapshot **and in every change**
  (**BL-1381, 0.11.0**; 0.10.0 did it for the snapshot only and a change threw); a `long` property does not read.
  `ToDataTable` columns have the array type.
- **A POCO with array properties writes and creates its columns** (**BL-1374, 0.9.1**). `double[]`, `float[]`, `int[]`, `long[]`,
  `byte[]` and `string[]` properties map to `Double[]`, `Float32[]`, `Int32[]`, `Int64[]`, `Byte[]` and `String[]` (nullable
  columns; a `byte[]` is the `Byte[]` column, a scalar `byte` stays `Byte`). `GetTable<T>().InsertAsync` / `InsertManyAsync` /
  `BulkLoadAsync`, `GetTable(name).InsertAsync(entity)`, `UpdateAsync(new { … })`, `AutoCreateSchema` and the default reconcile all
  take them. The match is on the exact CLR type: `uint[]`, `short[]`, `bool[]`, `decimal[]`, `int?[]`, jagged arrays and
  `List<T>` / `IReadOnlyList<T>` properties are refused (`NotSupportedException` naming the property) before anything is sent;
  mark them `[AoudaIgnore]`. In 0.9.0 every typed write of such a POCO threw `unsupported type 'Int32[]'`.
- **Writes** take the same arrays: dictionary rows (as JSON; a row whose only array values are `byte[]` may go in a frame, as base64 text, with the same result), `UpdateAsync`, named-mutation arguments and
  `batchParam` rows. A NaN or infinity element is refused by the server (`AoudaRequestException`, status 400), and locally
  (`ArgumentException`, before sending) in a `batchParam` row and on the write stream:

  ```text
  AoudaRequestException: Column 'D': Element 0 of the Double[] value is NaN; array elements must be finite numbers (NaN and ±Infinity are refused).
  AoudaRequestException: ARRAY_COLUMN_UNSUPPORTED: column 'Samples.D' is Double[]; an array column cannot be used in a where …
  ```

  The client does not check the limits itself; the server's refusal comes back as the typed exception.
- **A column batch** takes the factories `ColumnBatchColumn.FromDoubleArrays`, `FromFloat32Arrays`, `FromInt32Arrays`,
  `FromInt64Arrays`, `FromByteArrays` and `FromStringArrays`, each `(string name, T[]?[] values, byte[]? absentBits = null)`: a
  `null` row is a null cell, and the rows are **copied** into the column (as the nullable scalar factories copy; the non-nullable
  ones keep your array). `Validate()` checks the limits and finiteness, and every send calls it, so a bad batch throws
  `ArgumentException` before anything is sent.

  ```csharp
  var batch = ColumnBatch.Of(
      ColumnBatchColumn.FromInt64s("Id", new[] { 301L, 302L }),
      ColumnBatchColumn.FromDoubleArrays("D", new double[]?[] { new[] { 1.0, 2.0 }, null }),
      ColumnBatchColumn.FromStringArrays("S", new string[]?[] { new string[0], new[] { "x" } }));
  await samples.InsertAsync(batch);   // 301: D=[1,2] S=[]   302: D=null S=[x]
  ```
- **POCO schema inference and POCO writes with an array property are refused** (`NotSupportedException`) until Embedded maps CLR
  array properties (BL-1213). Reading into a POCO with an array property works with `ToObjects<T>()`, `ToListAsync<T>()` or
  `GetTable<T>(tableName)`; `GetTable<T>()` without a name infers the type's schema and throws `NotSupportedException`.
- **The write stream** (`stream_rows`) holds at most `Aouda:WebSocket:StreamingWrites:MaxBatchBytes` (1 MiB by default) of JSON a
  message, so one large array row is refused there (`INVALID_STREAM_ROWS`); use an insert or a named mutation.
- **The C# named-client generator** (`aouda generate csharp`, [Build apps](../guides/build-apps.md)) writes `double[]`, `float[]`, `int[]`, `long[]`, `byte[]` and `string[]` for
  array columns and parameters (a non-optional property defaults to `System.Array.Empty<T>()`).

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

## 8a) Subscriptions: which listener takes which

`client.GetTable(name).SubscribeAsync()` sends a **table subscription**: a `target` table and an optional filter (`Where(...)`, including
`In` / `Nin`; a server up to 0.8.0 refuses those two on a subscription with `INVALID_SUBSCRIPTION_FILTER`, **BL-1226, 0.9.0**). The server accepts it on the **admin listener** only. A client that builds the query on the caller's behalf is composing
a query, and the **data-plane listener** (the one browsers and `mk_pub_*` reach) refuses that by design: its callers send a named-query
name and arguments, nothing else ([Direct client access](../guides/direct-client-access.md); ADR 0040 C-2).

| You are | Subscribe with | Listener |
|---|---|---|
| A trusted backend with a service key (`mk_svc_`) | `client.GetTable(t).Where(...).SubscribeAsync()`, or a named query | **Admin**, or either with a named query |
| An application end user (user JWT or `mk_pub_*`) | `client.NamedQueries.SubscribeAsync(name, args)` | **Data-plane** |

A table subscription sent to the data-plane listener fails with `NAMED_QUERY_SUBSCRIBE_REQUIRED`
(`AoudaRequestException.ErrorCode`). The fix is not a different filter: subscribe **by name** (see
[Named queries](../guides/named-queries.md#subscribe-by-name)), or point a trusted backend at the admin listener with its service key.
The wire contract is in the [HTTP API reference](../reference/http-api.md#websocket-streaming-protocol).

**What a subscription sees** (**BL-1227, 0.9.0**). A subscription's snapshot and events follow the same grants as an HTTP query by
the same credential; `SubscribeAsync` is authorized by the same role check (`read` on the table, and for a named query every table it
touches), and the server re-reads the credential's permissions on every subscribe. A server API key (`mk_srv_`) that works over HTTP
on a linked application database opens its socket too. Details: [Real-time Streaming](../guides/real-time.md#who-may-subscribe-and-what-a-subscription-sees).

### Timestamp columns in a subscription

(**BL-1381, 0.11.0**) A `Timestamp` cell is a `DateTime` of kind `Utc` on every subscription surface (table, named query, typed),
with the 100 ns tick kept, in the snapshot rows and in each change's `Row`, `PreviousRow` and `Key`. The server names a `Timestamp`
column in the snapshot only; the SDK keeps those names for the life of the subscription (across a reconnect, a gap resume and a
`SLOW_CONSUMER` fresh subscribe) and replaces them when a new snapshot arrives; a resumed stream that sends no snapshot keeps the old names. A null stays null; a value that is not a tick count ends
the subscription with an `InvalidDataException` naming the column. No converter or option is needed. Wire detail:
[Real-time Streaming](../guides/real-time.md) (Timestamp columns in a subscription).

### Subscribing across partitions

On a partitioned table that requires a partition filter, a subscription that names no partition is refused with
`PARTITION_FILTER_REQUIRED`. `RemoteTableQuery.WithCrossPartitionAccess()` reaches
`SubscribeAsync` as well as the query methods (**BL-1227, 0.9.0**; until this train a subscription had no way to send it), and
`SubscribeOptions.CrossPartitionAccess` asks for the same. Either asks; **neither cancels the other**. The client sends
`cross_partition_access: true` on the `subscribe` message only when asked, and sends it again on every resubscribe after a reconnect.

```csharp
using Aouda.Abstractions.Streaming;
using Aouda.Client;

// On the query builder
await foreach (var evt in client.GetTable("orders")
    .WithCrossPartitionAccess()
    .SubscribeAsync(ct))
{
    Console.WriteLine($"{evt.Type} v{evt.Version}");
}

// Or in the options
var options = new SubscribeOptions { CrossPartitionAccess = true };
await foreach (var evt in client.GetTable("orders")
    .Where("status", "eq", "open")
    .SubscribeAsync(options, ct))
{
    Console.WriteLine(evt.Type);
}
```

**It is a cost waiver, not a grant.** It waives `PARTITION_FILTER_REQUIRED` and nothing else: the snapshot and every event are what the
credential's grants allow (a service key, or a user with the `all-partitions` grant, receives every partition, those created later
too; a user with partition grants receives only its own). The data-plane listener ignores it. An older server ignores the field and
answers `PARTITION_FILTER_REQUIRED` ([compatibility](compatibility.md)). The flag itself writes nothing to the audit log; a grant that
decides what a subscription sees is audited once per subscription
([Authorization](../auth/authorization.md#visibility-is-granted-all-partitions-and-all-rows)).

### Named queries and the flag

A named query that binds no partition key on a partitioned table is refused the same way, and takes the flag **per call**
(**BL-1227, 0.9.0**): `NamedQueriesApi.ExecuteAsync(…, crossPartitionAccess: true)`,
`new NamedQueryBatchInput(…, crossPartitionAccess: true)` for one batch item, and `SubscribeOptions.CrossPartitionAccess` on
`NamedQueriesApi.SubscribeAsync`. A definition cannot set it, and a batch has no batch-wide switch.

```csharp
var args = new Dictionary<string, object?> { ["status"] = "open" };

// ExecuteAsync(name, args, ct, orderByIndex, atLeast, crossPartitionAccess)
var open = await client.NamedQueries.ExecuteAsync(
    "orders_by_status", args, ct, crossPartitionAccess: true);

// BatchAsync: the flag is on the item
var slots = await client.NamedQueries.BatchAsync(
    new[]
    {
        new NamedQueryBatchInput("orders_by_status", args, crossPartitionAccess: true),
        new NamedQueryBatchInput("customer_card", new Dictionary<string, object?> { ["id"] = 7 }),
    },
    ct);

// SubscribeAsync: the flag is in the options
await foreach (var evt in client.NamedQueries.SubscribeAsync(
    "orders_by_status", args, new SubscribeOptions { CrossPartitionAccess = true }, ct))
{
    Console.WriteLine(evt.Type);
}
```

The rows are the credential's grants, flag or not. The alternative is to bind the partition key in the definition's `where` clause: it
needs no flag and works on the data-plane listener, where the flag is ignored
([`crossPartitionAccess` on the data-plane listener](../guides/browser-tier-read-limits.md#crosspartitionaccess-on-the-data-plane-listener)).

### Many subscribers of one query share one subscription (**BL-1384, 0.11.0**)

Every `SubscribeAsync` on one `AoudaClient` shares by **(name, canonical arguments, options)**: the first opens the server subscription,
the next ones read the same stream, and the last one disposed closes it (one `unsubscribe`). A table subscribe shares by its canonical
filter (the same `Where` in another property order is the same filter). The options are part of the identity: `Conflate`,
`OrderByIndex`, `AtLeast` / `WaitMs` / `OnExceeded` and `CrossPartitionAccess`. There is **no opt-out**; for an independent stream, build
another `AoudaClient`. A subscribe with an explicit `SubscribeOptions.ResumeFrom` never shares.

```csharp
// Twenty widgets, one server subscription. Each consumer is attached once it has received its first
// event (its snapshot), so the counts are read only after all twenty have one.
var firstEvents = 0;
var allAttached = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
var widgets = Enumerable.Range(0, 20).Select(_ => Task.Run(async () =>
{
    var first = true;
    await foreach (var evt in client.NamedQueries.SubscribeAsync("quotes_by_ticker", args, null, ct))
    {
        if (first)
        {
            first = false;
            if (Interlocked.Increment(ref firstEvents) == 20) allAttached.TrySetResult();
        }
        Render(evt);
    }
})).ToArray();

await allAttached.Task;
Console.WriteLine($"{client.ActiveConsumers} consumers on {client.ActiveServerSubscriptions} server subscription(s)");
// prints: 20 consumers on 1 server subscription(s)
```

- **Each consumer has its own snapshot.** A subscriber that joins a subscription already open is handed the rows it holds as one
  synthetic `Snapshot` event (current version and token), then the live events. One that joins while the first snapshot is still arriving
  waits for it; one that joins while the connection is down waits until the resubscribe is sent. Events are shared **by reference**:
  rows are not copied per consumer, so do not mutate them.
- **One slow consumer does not slow the rest — and no consumer may stall without limit.** Each enumerator has a queue of 10 000
  events by default; (**BL-1421, 0.12.0**) `AoudaClientOptions.SubscriptionConsumerQueueCapacity` (default `10_000`, validated `>= 1` when the
  client is built) sets it for every subscription on the client, and `SubscribeOptions.ConsumerQueueCapacity` overrides it for one subscription
  (also validated `>= 1`). The capacity is **not part of the sharing identity**: subscribes that differ only in it still share one server
  subscription, each with its own queue. One that falls further behind (a long pause, a slow handler through a burst) ends with an `AoudaRequestException` whose
  `ErrorCode` is `CLIENT_CONSUMER_OVERFLOW` and leaves; the others and the server subscription go on. **This holds for a subscription
  nobody shares as well**: before this train the client buffered without limit, now a single consumer that cannot keep up is ended with
  that error (no resume: subscribe again for a new snapshot), and the server subscription is closed when it was the last. Catch it
  where you read the stream if a burst of more than the capacity between two reads is possible. (**BL-1421, 0.12.0**) The message says what happened
  and the recovery: `The subscription consumer fell behind: <capacity> events were queued unread. It was removed from the shared subscription; the
  other consumers are unaffected. There is no resume: subscribe again to get a fresh snapshot. To tolerate a longer stall, raise
  AoudaClientOptions.SubscriptionConsumerQueueCapacity (client-wide) or SubscribeOptions.ConsumerQueueCapacity (this subscription); or read faster.`
- **A joiner may get a subscription of its own.** The shared subscription keeps at most 100 000 rows (a fixed SDK limit that equals the server's default `MaxSnapshotRows`; changing the server key does not change it) to
  seed joiners. Beyond that, or when it cannot keep them exact (the SDK learns the key columns from the first `delete` it receives, so a
  projection that leaves out the primary key, a table without one, rows equal in every column, an `upsert` before any delete (the
  server sends no previous row with one), or a change it cannot match, cannot be kept), a later subscriber opens its own server
  subscription instead; later subscribers may share that one in turn, so for such a table the sharing ratio stays near 1. Nothing is
  lost: the subscribers already reading are unaffected.
- **Snapshot warnings are raised once per server snapshot** (to the client's `NamedArtifactWarning` sink), not once per consumer: a
  subscriber that joins later is not told again.
- **Resuming from a sequence you hold.** `SubscribeOptions.ResumeFrom` (the `Version` of the last event you saw) sends `resume_from`
  on the first subscribe, so the stream continues from there (the server answers with a snapshot when it cannot resume; the first
  event is then a snapshot, otherwise a change). A subscribe with a `ResumeFrom` never shares a server subscription: it continues its
  own stream, and one reconnect before its first event resumes from the same point.
- **A reconnect resubscribes once per shared subscription** (with `resume_from`), however many consumers it has, over the WebSocket and
  the long-poll transport alike. A server error, a refused subscribe included, reaches every consumer of that subscription.
- `AoudaClient.ActiveConsumers` and `AoudaClient.ActiveServerSubscriptions` give the sharing ratio.

### Limits, refusals and reconnects (**BL-1383, 0.11.0**)

- **The identity's connection limit is terminal.** A streaming connection refused because the identity already holds
  `Aouda:WebSocket:MaxConnectionsPerIdentity` connections (`IDENTITY_CONNECTION_LIMIT_EXCEEDED`: an `auth_error` on the WebSocket, HTTP 429
  on long-poll `connect`) throws `AoudaConnectionLimitException`. The SDK does not retry in a loop and does not fall back to long-poll
  (its sessions count too). If a connection that was up is refused on its reconnect, every consumer of every subscription on it ends
  with that exception. Close a connection the identity no longer needs, or share one `AoudaClient`, then subscribe again. The global
  pool's `CONNECTION_LIMIT_EXCEEDED` is not this: it is retried.
- **Reconnects back off.** The delay between reconnects grows (from 1 second, doubling, capped at 30 seconds; not configurable through the public API) and starts
  over only after a connection has stayed up for 10 seconds, so a server that authenticates and then closes is not hammered.
- **A rate-limited subscribe is retried.** When the per-identity subscribe-rate bound refuses a subscribe (`SUBSCRIBE_RATE_EXCEEDED`),
  the SDK waits the server's `retry_after_ms` and sends it again, at most three times, then ends every consumer of that subscription with
  `AoudaSubscribeRateLimitException` (`RetryAfter` holds the last wait). A reconnect that resubscribes many shared subscriptions is
  spaced (the first 100 at once, then 28 a second).
- **`client.ServerLimits`** holds what the server sent in `auth_ok`: `MaxSubscriptionsPerConnection`, `MaxSubscriptionsPerIdentity`,
  `MaxConnectionsPerIdentity`, `SubscribeBurst`, `SubscribeRefillPerSecond`, `ProtocolVersion` and `Capabilities`. It is `null` before the
  first WebSocket connection, over long-poll, and against a server that does not send them. `SUBSCRIPTION_LIMIT_EXCEEDED` reaches you
  as an `AoudaSubscriptionLimitException` (an `AoudaRequestException`, not a connection error) with the server's message, which names the cap
  and what raises it.

---

## 8b) Which databases a sign-in opens (**BL-1018, 0.9.0**)

An application sign-in gives a token that opens only its **allowance**: the databases of the auth database on which the user holds
a role. `SignInAsync(email, password, deviceInfo, databases)` narrows it to the databases you name — never wider; a name the user
holds no role on, or an empty list, is refused (`AoudaRequestException`, `400 INVALID_REQUEST`). Native sign-in narrows the same way
with `AuthorizationCodeRequest.Databases`. The token's `aud` lists the allowance and its `iss` is the auth database's URL.

```csharp
// One sign-in for the two apps this front end serves
await client.Auth.SignInAsync("alice@example.com", password, deviceInfo: "Alice's laptop",
    databases: new[] { "orders", "reports" });
```

A token used at a database outside its allowance is `401 AUTH_DATABASE_NOT_IN_ALLOWANCE`. A **refresh** refused with that code ends
the client's session like `AUTH_REFRESH_TOKEN_INVALID`: the SDK clears its tokens and raises `TokensChanged` with `SignedOut`, and the
realtime transports stop reconnecting — sign in again for that database. See
[the token allowance](../auth/reference.md#the-token-allowance).

---

## 8c) Materialized values (**BL-1434, next train**)

A [materialized value](../guides/materialized-values.md) is a named, computed cell: a formula over rows of ordinary tables and other cells, kept current by the server. `client.MaterializedValues` (namespace `Aouda.Client.MaterializedValues`; the value types `MvValueType` and `MvScalarType` are in `Aouda.Protocol.MaterializedValues`, `ScalarExprNode` in `Aouda.Protocol`) defines, sets inputs of, reads, waits for, subscribes to and explains them. It is on `AoudaClient`, not on `IAoudaClient`. The definition calls need a **definer**: a `db_admin` user or the database's `mk_svc_` service key; on a database the server auth database governs, a server user with `db_admin` on it. The server key `mk_srv_` is **not** a definer, and reads no values without an entitlement ([Security](../guides/materialized-values.md#security)).

```csharp
using Aouda.Client;
using Aouda.Client.MaterializedValues;
using Aouda.Protocol;                      // ScalarExprNode
using Aouda.Protocol.MaterializedValues;   // MvValueType, MvScalarType

// A definer: here the database's service key.
using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433", DatabaseName = "myapp", ApiKey = "mk_svc_...",
});
var model = client.MaterializedValues.Model("pnl");

// An input table with the natural composite key a cell read needs.
await client.MaterializedValues.CreateInputTableAsync(
    "inputs",
    [new MvKeyColumn("Field", MvValueType.Of(MvScalarType.String)), new MvKeyColumn("Year", MvValueType.Of(MvScalarType.Int64))],
    [new MvColumn("Value", MvValueType.Decimal(18, 2)), new MvColumn("Label", MvValueType.Of(MvScalarType.String))]);

// One request, all or none; each cell declares its type.
static ScalarExprNode Input(string field, string column) => MvExpr.Cell("inputs", column, ("Field", field), ("Year", 2026L));
var dec2 = MvValueType.Decimal(18, 2);
await model.DefineAsync(
[
    new("Revenue", dec2, Input("Revenue", "Value")),
    new("Cost", dec2, Input("Cost", "Value")),
    new("Profit", dec2, MvExpr.Sub(MvExpr.Ref("pnl", "Revenue"), MvExpr.Ref("pnl", "Cost"))),
    new("Tax", dec2, MvExpr.If(MvExpr.Gt(MvExpr.Ref("pnl", "Profit"), MvExpr.Lit(0m)),
                               MvExpr.Round(MvExpr.Mul(MvExpr.Ref("pnl", "Profit"), MvExpr.Lit(0.22m)), 2), MvExpr.Lit(0m))),
]);

// Set inputs (ordinary writes), then wait for the value they produce.
await model.SetAsync(MvInputCell.Of("inputs", "Value", ("Field", "Revenue"), ("Year", 2026L)), 1000m);
var token = (await model.SetAsync(MvInputCell.Of("inputs", "Value", ("Field", "Cost"), ("Year", 2026L)), 400m)).Token!;
decimal? tax = await model.GetAsync<decimal?>("Tax", new MvGetOptions { WaitFor = MvWaitFor.AtLeast(token, TimeSpan.FromSeconds(10)) });   // 132.00
```

- **Members.** `DefineAsync` (one cell or many) / `AlterAsync` / `DeleteAsync` / `GetDefinitionAsync` / `ListAsync`; `SetAsync`; `GetAsync` (an `MvValue`) and `GetAsync<T>`; `SubscribeAsync(cell, options)` / `SubscribeAsync(options)` (an `IAsyncEnumerable<MvValueEvent>`); `ExplainAsync`. The expression builder is `MvExpr`: `Lit`, `Cell`, `Ref`, `Add` `Sub` `Mul` `Div`, `Min` `Max` `Abs`, `Eq` `Ne` `Gt` `Gte` `Lt` `Lte`, `If`, `And` `Or` `Not`, `Round`, `Coalesce`, `Concat`, `Cast`. At most `MaterializedValuesApi.MaxDefinitionsPerRequest` cells per `DefineAsync` call (10 000).
- **`SetAsync` is two ordinary writes**, not one atomic upsert: an update, and when no row matched an insert. Two concurrent first writes of one new key race; the loser's insert is refused as a duplicate and its update is retried once, so both succeed and the last one wins. It returns the write's consistency token.
- **`GetAsync` returns `null`** for a cell that has not been computed or is not defined. A cell in a model the caller holds no entitlement for raises `MaterializedValueNotGrantedException`. A cell that could not be computed is an `MvValue` with `IsError` and the text in `Error`. An `MvValue` carries `Value` (decoded by the cell's `valueType`), `Text` (the canonical text), `Error`, `ComputedAtPosition`, `ComputedAtTerm` and `Token`.
- **`GetAsync<T>` never converts.** `T` must be the decoded type of the cell (`decimal` for `Decimal(p,s)`, `long` for `Int64`, `DateOnly` for `Date`, ...), its `Nullable<T>`, or `object`. An error cell raises `MaterializedValueCellErrorException`; a mismatch, or a null **value** into a non-nullable `T`, raises `MaterializedValueTypeException`. A **missing** cell (not computed, not defined) returns `default(T)` for a non-nullable `T`, so `GetAsync<decimal>` answers `0m` (BL-1451): ask for `decimal?` to tell a missing cell from zero.
- **`MvWaitFor`.** `MvWaitFor.AtLeast(token, timeout)` waits for a token; `MvWaitFor.Observed(timeout)` waits for the client's own stored token (read-your-writes). The default is `Observed(5 s)`; `0 <= timeout <= 30 s`. A commit that left the cell unchanged satisfies it. A lapse is `MaterializedValueNotCaughtUpException`, never a stale value. The value is eventually consistent with its inputs: there is no atomic read of an input and the value derived from it, and `ComputedAtPosition` is an "at least".
- **Subscribing** is an ordinary table subscribe on `_mv_values` filtered on `model` (and `name`), case-exact; it resumes after a reconnect from the last version seen. `MvValueEvent.CoverToken` is a snapshot's token and an insert, update or delete's token, and is `null` for a notice (`horizon`, `range_delete`): keep the highest cover seen and pass it to `MvWaitFor.AtLeast`. A revoked entitlement ends the feed with `MaterializedValueGrantRevokedException`.
- **`ExplainAsync`** returns a cell, its formula, the input rows it reads, the cells it reads and is read by, and the maintainer's watermark. Positions are "at least".

**Typed errors.** Every refusal is an instance of the exception its status already maps to, with the materialized-value type on top (namespace `Aouda.Client.Exceptions`):

| Code (status) | Exception |
|---|---|
| `MV_DEFINITION_INVALID`, `MV_REFERENCE_INVALID`, `MV_REFERENCE_NOT_PRIMARY_KEY`, `MV_CYCLE`, `MV_DEPTH_EXCEEDED` (400); `MV_DEFINITION_EXISTS`, `MV_DEFINITION_IN_USE`, `MV_TABLE_REFERENCED` (409) | `MaterializedValueDefinitionException`, with a `Kind` |
| `MV_DEFINITION_NOT_FOUND` (404) | `MaterializedValueNotFoundException` |
| `INSUFFICIENT_PERMISSIONS` (403) on a definition call | `MaterializedValueNotDefinerException` |
| `AUTH_ENTITLEMENT_NOT_FOUND` (403) on a value read | `MaterializedValueNotGrantedException` |
| `TOKEN_UNSATISFIED` (409) on a value read | `MaterializedValueNotCaughtUpException` |
| `MV_TOKEN_REQUIRES_PRIMARY` (421) | `MaterializedValueReplicaException` |
| `MV_NOT_MAINTAINED` (503) | `MaterializedValueNotMaintainedException`: **not retried** by the client and not counted against its circuit breaker; it is the node's state, not overload |
| `PERMISSION_REVOKED` on a subscription | `MaterializedValueGrantRevokedException` |
| (SDK-side) a row the SDK cannot decode; a type mismatch; an error cell asked for as a value | `MaterializedValueDecodeException`, `MaterializedValueTypeException`, `MaterializedValueCellErrorException` |

**Value mapping.** `Bool` is `bool`; `Byte`, `Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64` are `byte`, `short`, `int`, `long`, `ushort`, `uint`, `ulong`; `Decimal(p,s)` is `decimal` and keeps its scale (`1.50`); `Float32`, `Double` are `float`, `double`; `String` is `string`; `Guid` is `Guid`; `Date` is `DateOnly`; `Timestamp` is `DateTime` (UTC). The canonical text of each is in [Materialized Values: value types](../guides/materialized-values.md#value-types).

**Known issue (BL-1447).** A `waitFor` of nearly the client's own request timeout (`AoudaClientOptions.Timeout`, 30 s by default) can race it: the read times out client-side as `AoudaTimeoutException` (not `MaterializedValueNotCaughtUpException`) and is retried up to 3 times, each counted against the circuit breaker. Keep waits well under the timeout.

## 9) Errors

Server errors are `AoudaException` (namespace `Aouda.Abstractions`) or a subclass, with `ErrorCode`, `StatusCode`, `RequestId`
and `Details`; the error codes are listed in the [HTTP API reference](../reference/http-api.md). The ones a client most often
handles (namespace `Aouda.Client` unless noted):

| Exception | When |
|---|---|
| `AoudaRequestException` (`Aouda.Abstractions`) | The server refused the request: `400`, `403` or `409`; `ErrorCode` says why. `400 PARTITION_FILTER_REQUIRED` is its subclass `AoudaPartitionFilterRequiredException`. |
| `AoudaAuthenticationException` / `AoudaNotFoundException` (`Aouda.Abstractions`) / `AoudaMisdirectedRequestException` | `401` / `404` / `421`. (**BL-1422, 0.12.0**) The `Message` of every HTTP `401` and `403` refusal now carries the server's `suggestion` (which names the key kind and prefix the route takes) and the option to set (`AoudaClientOptions.ApiKey`, `ServerAuth`, `AppAuth` or `ServerUrl`), with the kind of credential this client was sending (for example `a service key (mk_svc_) set as AoudaClientOptions.ApiKey`). The key itself is never in the message. `ErrorCode`, `StatusCode`, `RequestId` and `Details` are unchanged; only `Message` is longer, so match on `ErrorCode`, not on the text. WebSocket and long-poll auth frames carry the server's message only; the option hint is added on HTTP. |
| `AoudaAuthenticationFatalException` | A subtype of `AoudaAuthenticationException`, thrown only with `AuthFailurePolicy.FailFast` (**BL-1386, 0.11.0**): a `401`, or a `403` that refuses the credential itself. The original failure is the `InnerException`. A batch writer faults on it even with `ContinueOnError`. |
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
