---
title: "Array columns"
nav_order: 22
parent: "Guides"
---

# Array columns: one whole array per row

(**BL-035, next train**) Everything on this page is new in the next server train, and nothing here exists in the current release.

An **array column** holds one whole array per row: a curve's 400 forward points, a fit's 100 residuals, a feature vector's
history. You write the array whole, read it whole, and never ask the engine about a single element. There are six types, one per
element type, and every surface carries them: schema, named queries and mutations, `/query`, `/rows`, bulk load, subscriptions,
materialized queries, frames, both SDKs and Studio.

Related: [Schema lifecycle](schema.md) (declaring and changing columns), [Named queries](named-queries.md),
[Materialized queries](materialized.md), [Bulk load](bulk-load.md), [Sizing](sizing.md#array-columns-what-a-value-costs),
[Real-time streaming](real-time.md), [HTTP API](../reference/http-api.md#data-types), [Vector columns](graph-vector.md) (similarity
search, a different thing).

---

## Start Here

| If you need to know... | Go to |
|---|---|
| Whether an array column fits what I store | [What it is, and when not to use it](#what-it-is-and-when-not-to-use-it) |
| The six type names and the JSON form of each | [The six types](#the-six-types) |
| How to declare one, and what is refused | [Declaring an array column](#declaring-an-array-column) |
| What a value may hold (null, empty, `-0`, NaN) | [Values](#values) |
| How big a value can be | [Limits](#limits) |
| How to write arrays | [Writing](#writing) |
| How to read them, on every surface | [Reading](#reading) |
| What you cannot do with an array column | [What is refused, and where](#what-is-refused-and-where) |
| What it costs in memory and on disk | [Tiers, retention and cost](#tiers-retention-and-cost) |
| What is not built | [Known limitations](#known-limitations) |
| An error you do not understand | [Troubleshooting by symptom](#troubleshooting-by-symptom) |

---

## What it is, and when not to use it

(**BL-035, next train**) An array column stores the same kind of value a spreadsheet cell would if it could hold a list: a
`Double[]` column holds `[0.0412, 0.0398, 0.0377, 0.0361]` in one row and `[0.0415, 0.0399]` in the next. The rows can differ in
length. The array is the value: you replace it whole (an `upsert` or an `update … set` writes a whole new array) and the engine
compares it as bytes.

The running example on this page is an interest-rate curve, one row per published fit:

```json
{
  "tables": {
    "RateCurves": {
      "columns": {
        "CurveId":   { "type": "Int32", "primaryKey": 1 },
        "AsOf":      { "type": "Timestamp", "primaryKey": 2 },
        "Tenors":    { "type": "Int32[]",   "nullable": true },
        "Rates":     { "type": "Double[]",  "nullable": true },
        "Residuals": { "type": "Float32[]", "nullable": true }
      },
      "clusterColumns": ["AsOf"]
    }
  }
}
```

**Use an array column when** the array is written whole, read whole, and you do not filter, sort, group or aggregate on its
elements.

**Do not use one when** you ask questions of a single element ("every curve whose 10-year rate is above 4 %"). There is no
element selection and no element predicate (see [Known limitations](#known-limitations)): that shape is still one row per
element, with the point's index as a key column. For **similarity search** over a fixed-length vector of floats use a
[`Vector` column](graph-vector.md), which has an index and distance functions that an array column does not.

---

## The six types

(**BL-035, next train**) The names are matched **exactly**: ordinal, case-sensitive, no spaces, no alias.

| Type | Element | JSON form of a value | C# | TypeScript |
|---|---|---|---|---|
| `Double[]` (**BL-035, next train**) | 64-bit float | array of numbers | `double[]` | `Float64Array` |
| `Float32[]` (**BL-035, next train**) | 32-bit float | array of numbers | `float[]` | `Float32Array` |
| `Int32[]` (**BL-035, next train**) | 32-bit signed integer | array of integers | `int[]` | `Int32Array` |
| `Int64[]` (**BL-035, next train**) | 64-bit signed integer | array of integers | `long[]` | `BigInt64Array` |
| `Byte[]` (**BL-035, next train**) | unsigned byte | **one base64 string** (not an array of numbers) | `byte[]` | `Uint8Array` |
| `String[]` (**BL-035, next train**) | text | array of strings | `string[]` | `string[]` |

The same type comes back on every surface and in both SDKs: a query result, a frame, a subscription message and a long-poll all
give a `Float64Array` in TypeScript for a `Double[]` column.

**A `Byte[]` column is not a column of `Byte`.** A scalar `Byte` column holds one byte per row; a `Byte[]` column holds a whole
byte string per row, and travels as base64 in JSON. In C# the `byte[]` you pass is a `Byte[]` value only when the **column** is
`Byte[]`. It travels as its base64 text, so sent to a scalar `Byte` column it is refused as not a number, with one
exception: a base64 text made only of digits (the three bytes `D3 4D 76` are `"0012"`) is read as that number (BL-1265).
Do not send a `byte[]` to a `Byte` column.

---

## Declaring an array column

(**BL-035, next train**) Use the type name wherever a column's type is named: a schema document, `POST …/tables`,
`POST …/tables/{name}/columns`, a schema export, the `aouda-schema.v1.json` editor schema, and table describe.

```json
{ "Rates": { "type": "Double[]", "nullable": true } }
```

- **A non-nullable array column is allowed at create.** Every row must then give a value: an array column has **no default**, so
  a row that omits it is refused (a null or absent cell, at any bulk-load validation level, `coerce` included).
- **An array column added to an existing table is nullable.** `POST …/columns` adds it nullable whatever the request says. A
  schema apply that adds a non-nullable array column to a table that already exists reports that entry as failed: *"Add-column of
  array column 'Fit' (Double[]) on table 'RateCurves' requires nullable: true; the rows that predate it read null."* Rows that
  were there before read `null`.
- **`precision` / `scale` are refused** on an array type (they belong to `Decimal`).
- **The spellings that are not accepted**: `"double[]"` (wrong case), `"Double []"`, `"Double[][]"` (no nested arrays),
  `"DoubleArray"`, and the type's number. Each is refused as an invalid column type, and the message lists the valid names:

  ```text
  400 INVALID_REQUEST
  Invalid schema: Invalid column type 'double[]' in table 'T', column 'V'. Valid types: Bool, Byte, Byte[], Date, Decimal, Double,
  Double[], Float32, Float32[], Guid, Int16, Int32, Int32[], Int64, Int64[], String, String[], Timestamp, UInt16, UInt32, UInt64.
  ```

  (`POST …/tables` also names `Vector` and `MdVector` in its list, and is case-insensitive for the scalar names; the array names
  are exact there too.)
- **A column's type never changes into or out of an array type.** `PATCH …/columns/{name}` with a new type answers `400
  INVALID_REQUEST`: *"Changing a column to or from an array type is not supported; add a new column and copy the values."* A
  schema apply that changes the type is **not applied**: the column keeps its type and the response carries a warning with that
  sentence.
- **An array column is never a key, an index or a rule.** See [What is refused, and where](#what-is-refused-and-where).

The generators know the types: `GET /api/databases/{db}/schema/typescript` writes `Float64Array`, `Float32Array`, `Int32Array`,
`BigInt64Array`, `Uint8Array` and `string[]` for the row types, and for a named mutation's arguments a union that also takes a
plain array (`Float64Array | number[]`, `BigInt64Array | bigint[] | number[]`); the C# named-client generator writes `double[]`,
`float[]`, `int[]`, `long[]`, `byte[]` and `string[]`.

---

## Values

(**BL-035, next train**)

- **Null is not empty.** The column may be null (a nullable column); `[]` is an empty array, a value. They read back as `null`
  and `[]`, on every surface. For a `Byte[]` the empty array is the empty string `""`.
- **An element is never null.** `[1.0, null]` and `["a", null]` are refused.
- **Only finite numbers.** NaN and ±Infinity are refused, and so are the strings `"NaN"`, `"Infinity"` and `"-Infinity"` as
  elements, and a number past the type's range (`1e999` for a `Double[]`, `3.4e39` for a `Float32[]`, `2147483648` for an
  `Int32[]`).
- **`-0` and subnormals survive.** An element is stored bit for bit: `-0.0` reads back as `-0` (bits `8000000000000000`), `5e-324`
  as `5E-324`, ±`Double.MaxValue` and ±epsilon as they were. This is the array's rule; a scalar `Double` column is unchanged.
- **A `Float32[]` element is rounded to a float once**, from the text you write, and nothing else touches it.
- **An `Int32[]` / `Int64[]` element is an integer.** `2.0` and `1e3` are accepted (they are integers); `1.5` is not, and neither
  is a numeric string.
- **A `String[]` element must be valid text.** An unpaired surrogate (`"\ud800"`) is refused: UTF-8 cannot hold it.
- **Equality is by bytes.** `[-0.0]` is not `[0.0]`, and `[]` is not null.

The refusals are the ones in [Writing](#writing).

---

## Limits

(**BL-035, next train**) The same limits apply on every surface and there is no setting for them.

| Limit | Value |
|---|---|
| Elements in one value (**BL-035, next train**) | **65,536** |
| Bytes of elements in one value (**BL-035, next train**) | **1,048,576** (1 MiB): `count × width` for the numeric types, the sum of the strings' UTF-8 lengths for `String[]` |

A value **at** a limit is accepted; one over is refused. Because the element limit is reached first for the fixed-width types, the
largest value of each is:

| Type | Largest value |
|---|---|
| `Byte[]` (**BL-035, next train**) | 65,536 elements = 64 KiB |
| `Float32[]`, `Int32[]` (**BL-035, next train**) | 65,536 elements = 256 KiB |
| `Double[]`, `Int64[]` (**BL-035, next train**) | 65,536 elements = 512 KiB |
| `String[]` (**BL-035, next train**) | 65,536 elements **and** 1 MiB of UTF-8, whichever is reached first |

The element count is checked before the elements are read. The refusal names the limit and what it saw:

```text
Parameter 'b' (Byte[] column 'B'): An array value holds at most 65,536 elements (got 65,537).
Parameter 's' (String[] column 'S'): An array value holds at most 1,048,576 bytes of elements (1 MiB; got 1,048,577).
```

**Limits that stand next to these**, and were not changed:

- a JSON request body is limited to 30,000,000 bytes (a body over it answers `413`); a `Double[]` of 65,536 numbers written in
  full precision is about 1.2 MB of JSON, so a batch of about 25 such rows reaches it;
- a frame carries at most 1,000,000 rows and 4,096 columns, a string up to 16 MiB, and decodes to no more than 256 MiB;
- one transaction's rows must fit one WAL segment. The segment size follows the disk's free space when the database opens:
  64 MiB with about 10 GiB free or more, as little as 16 MiB on a small disk. A transaction over it is refused before anything
  is written, and the table is untouched, but over HTTP the refusal is a `500 INTERNAL_ERROR` (BL-1264). An HTTP insert usually
  meets the request-body limit first; on a small disk it can meet this one. Split it.
- a WebSocket `stream_rows` message holds at most `Aouda:WebSocket:StreamingWrites:MaxBatchBytes` (1 MiB by default) of JSON, so
  one large array row can be refused there (`INVALID_STREAM_ROWS`); write it with an insert or a named mutation instead.

---

## Writing

(**BL-035, next train**) A refused value stores nothing from that request.

### Named mutations

A parameter bound to an array column takes a JSON array (`Byte[]`: a base64 string). The definition is an ordinary `insert`:

```json
{
  "recordCurve": {
    "op": "insert",
    "table": "RateCurves",
    "values": {
      "CurveId": { "param": "curveId" },
      "AsOf": { "param": "asOf" },
      "Tenors": { "param": "tenors" },
      "Rates": { "param": "rates" },
      "Residuals": { "param": "residuals" }
    },
    "params": { "curveId": {}, "asOf": {}, "tenors": {}, "rates": {}, "residuals": {} }
  }
}
```

```text
POST /api/databases/acdocs/named-mutations/recordCurve/execute
{"args":{"curveId":1,"asOf":"2026-10-29T09:00:00Z","tenors":[90,180,365,730],"rates":[0.0412,0.0398,0.0377,0.0361],"residuals":[0.1,-0.25,0.0,0.5]}}

200  {"rowsInserted":1,"executionMs":0,"token":"012dfade35739a4d620000000000000000000004d3"}
```

A **literal** array works as a `values` entry too (`"Tenors": [30, 90, 180]`). `insert` with a `batchParam` takes one array per row
inside the column arrays of the batch (`"data": [[10, 11], ["2026-10-29T09:00:00Z", "2026-10-29T09:00:00Z"], [[0.01, 0.02], [0.03]]]`).
**`upsert` and `update … set` replace the whole array**; there is no way to change one element.

A bad value answers `400 NAMED_QUERY_BIND_FAILED`, naming the parameter, the column and the element:

```text
400 NAMED_QUERY_BIND_FAILED
Parameter 'd' (Double[] column 'D'): Element 0 of the Double[] value is NaN; array elements must be finite numbers (NaN and ±Infinity are refused).
```

### `POST …/rows` and the other write bodies

The write body is [column arrays](../reference/http-api.md#column-arrays-the-write-body): one array per column. An array column's
slot holds **one JSON array per row**, so the data is nested twice:

```text
POST /api/databases/acdocs/tables/Samples/rows
{"database":"acdocs","columns":["Id","D","B","S"],
 "data":[[100,101],[[1.5,2.5],null],["AQID",""],[["x","y"],[]]]}

200  {"rowsInserted":2,"executionMs":30,"token":"…"}
```

Row 100 holds `D = [1.5, 2.5]`, `B = AQID` (the bytes `1, 2, 3`), `S = ["x", "y"]`; row 101 holds `D = null`, an empty `Byte[]` and an
empty `String[]`. The same shape is read by a branch insert, a WebSocket `stream_rows`, the schema seed and a bulk-load `:append`.
An ad-hoc `PATCH …/rows` takes a whole array in `set` (`{"set":{"Rates":[1.25,2.5]}}`).

A bad value answers `400 INVALID_REQUEST`, naming the column:

```text
400 INVALID_REQUEST   Column 'D': A Double[] value is a JSON array (got a JSON number).
400 INVALID_REQUEST   Column 'B': A Byte[] value is a base64 string (got a JSON array).
400 INVALID_REQUEST   Column 'B': An array value holds at most 65,536 elements (got 65,537).
```

### Frames

An `ACB2` frame carries an array column as [kind 9](../reference/http-api.md#the-column-batch-frame-acb2). **The frame's element
kind must be the column's own**: nothing is widened. An `Int32` run sent to a `Double[]` column, or an array sent to a scalar
column, answers `400 INVALID_REQUEST`:

```text
Column 'D' is Double[]; the frame sends Int32 elements (an array column's frame carries its own element kind, Double; nothing is widened).
Column 'CurveId' is Int32; the frame sends an array of Int32 elements to it.
```

JSON is more forgiving than a frame: an integral number (`1`) in a `Double[]` column is accepted in JSON.

### Bulk load

`:append` takes array columns as JSON column arrays or as frames, on every path a load takes. A bad value is refused **at
`:append`** with `400 INVALID_REQUEST` naming the table, column, frame and row, and none of that frame's rows is applied. See
[Bulk load](bulk-load.md#array-columns).

### The SDKs

Both SDKs take the same arrays they return: [C#](../clients/dotnet.md#array-columns) and
[TypeScript](../clients/typescript.md#array-columns). **The server validates; neither SDK repeats the limits for a dictionary or
row-object insert**, so a refusal arrives as the server's error.

---

## Reading

(**BL-035, next train**) Every read surface gives the array whole.

### JSON

An array cell is a JSON array. `types` names the array type of the column:

```text
POST /api/databases/acdocs/named-queries/curveHistory/query   Accept: application/json
{"args":{"curve":1}}

200  {"columns":["CurveId","Tenors","Rates","Residuals"],
      "types":["Int32","Int32[]","Double[]","Float32[]"],
      "data":[[1],[[90,180,365,730]],[[0.0412,0.0398,0.0377,0.0361]],[[0.10000000149011612,-0.25,0,0.5]]],
      "rowCount":1, … }
```

- Numbers are written in the shortest form that reads back to the same value; `-0` is written `-0`; an exponent is written as
  `5E-324` and `1.7976931348623157E+308`.
- **A `Float32[]` element is written as the shortest text of the value widened to `double`**: `0.1f` is `0.10000000149011612`.
  That is the text a JavaScript reader turns back into the same float with `Float32Array.from` (the shorter `0.1` is not
  always safe for it). A reader that parses to `float` directly gets the same float.
- **An `Int64[]` element is a JSON integer.** Above 2^53 a plain `JSON.parse` loses digits, exactly as a scalar `Int64` does; the
  TypeScript SDK reads them exactly into a `BigInt64Array`.
- A `Byte[]` is a base64 string (`"AAEC/w=="`), empty `""`; a null cell is `null`; an empty array is `[]`.

### Frames

A query response with an array column is a frame when the client accepts frames. `X-Aouda-Column-Types`
names the array types: `["Int64","Double[]","Float32[]","Int32[]","Int64[]","Byte[]","String[]"]`. The grammar is in the
[HTTP API reference](../reference/http-api.md#the-column-batch-frame-acb2).

### Subscriptions, long-poll and materialized queries

A subscription's `snapshot` and `change` messages carry a **`column_types`** object naming the array columns the message holds:

```json
{"type":"change","id":"s1","op":"insert",
 "row":{"CurveId":77,"Tenors":[30,90],"Rates":[0.0125,0],"Residuals":[0.10000000149011612]},
 "column_types":{"Tenors":"Int32[]","Rates":"Double[]","Residuals":"Float32[]"}, … }
```

**The rule for a client: a column named in `column_types` holds an array of that type; a column not named holds a scalar.**
`column_types` is left out when the message holds no array column, so a table without arrays is unchanged. The materialized
query endpoint (`POST …/materialized-queries/{name}/query`) answers `columnTypes` the same way. MessagePack keeps `-0`; long-poll
carries the same fields. A `latestPerKey` subscription delivers array payload columns like any other.

### The data-plane listener

A named query or mutation on the data-plane listener reads and writes arrays with no encoding of its own, and the allowlist is
unchanged.

---

## What is refused, and where

(**BL-035, next train**) An array column can only be **selected**. It is refused, at the earliest point, with
`400 ARRAY_COLUMN_UNSUPPORTED` and a message that names the column, its type and the clause:

```text
ARRAY_COLUMN_UNSUPPORTED: column 'Samples.D' is Double[]; an array column cannot be used in a where (an array column can only be selected — ADR 0067 D-5).
```

| Where the array column is used | When it is refused | How it shows |
|---|---|---|
| primary key, `unique`, cluster column, `autoIncrement`, `default`, `derived`, partition key, `references` (either side), checks, transform predicates, the permission column (**BL-035, next train**) | the **schema document** is refused whole | `400 ARRAY_COLUMN_UNSUPPORTED`, nothing applied |
| the same, in `POST …/tables`; `autoIncrement` or `references` in `PATCH …/columns/{name}` (**BL-035, next train**) | the request | `400 ARRAY_COLUMN_UNSUPPORTED` |
| a table policy's `memoryFilter`, in `POST …/tables` or `PUT …/tables/{name}/policy` (**BL-035, next train**) | the request | `400 ARRAY_COLUMN_UNSUPPORTED` |
| a named query's `where`, `orderBy`, `groupBy`, aggregate (`count(col)` included), `distinct`, `selectExpr` input, join key, per-key key or order (**BL-035, next train**) | `schema apply` | that entry is `Failed`, its reason starts `ARRAY_COLUMN_UNSUPPORTED:`; the rest of the document applies |
| a materialized query's filter, group, order or aggregate on an array column (**BL-035, next train**) | `schema apply`, or `POST …/materialized-queries` | that entry is `Failed`; the endpoint answers `400 ARRAY_COLUMN_UNSUPPORTED` |
| a named mutation's `where`, a `setExpr` that targets or reads one, its `orderBy`, a `min` / `max` / `maxLength` / `enum` on a parameter bound to one (**BL-035, next train**) | `schema apply` | that entry is `Failed` |
| `/query` and `/query/count`: `where` (**`IS NULL` included**), `orderBy`, `groupBy`, an aggregate, `distinct`, a join key, a `perKey` key (**BL-035, next train**) | the request | `400 ARRAY_COLUMN_UNSUPPORTED` |
| an ad-hoc `PATCH …/rows` with a `setExpr` on one; a `DELETE …/rows` or a `POST …/rows/batch` delete with an `orderBy` on one (**BL-035, next train**) | the request | `400 ARRAY_COLUMN_UNSUPPORTED`, nothing deleted |
| a subscription `filter`, or a `conflate.key` (**BL-035, next train**) | `subscribe` | an `error` message with code `ARRAY_COLUMN_UNSUPPORTED` |
| an RLS rule on an array column (**BL-035, next train**) | a read (a query, a join side, a named query, the materialized query endpoint, a subscribe), an update or a delete (`PATCH` / `DELETE …/rows`, `POST …/rows/batch`, a named mutation's `update` or `delete`) | `400 ARRAY_COLUMN_UNSUPPORTED` (an `error` message at subscribe), nothing changed; an **insert** checked against such a rule is denied (`403`), and a change event checked against it is not delivered |
| a route or tee under `applyTransforms` that copies an array column into a column of another type, or a scalar into an array column (**BL-035, next train**) | bulk-load `:begin` | `400 ARRAY_COLUMN_UNSUPPORTED` |
| a column of an **edge table** (an edge table stores only its source, destination and label) (**BL-035, next train**) | `POST …/tables/{name}/columns` on an edge table (and the engine's `CreateEdgeTableAsync`) | `400 ARRAY_COLUMN_UNSUPPORTED`, nothing added |
| a `filter` materialized query over a table **without a primary key**, selecting an array column (**BL-035, next train**) | `schema apply` | that entry is `Failed` |

A `default` given as text is refused with `ARRAY_COLUMN_UNSUPPORTED`; one given as a JSON array (`"default": [1.0]`) is not a valid
`default` at all and is refused as an invalid schema (`400 INVALID_REQUEST`).

`count(*)` is fine: it counts rows. Selecting an array column is fine everywhere.

**A value that is invalid** (non-finite, a null element, over a limit) is not `ARRAY_COLUMN_UNSUPPORTED`: it is the surface's own
invalid-value code, [above](#writing).

---

## Tiers, retention and cost

(**BL-035, next train**) An array column follows its table's temperature like any column: it is written to the write buffer and the
WAL, flushed to hot and cold segments, merged and compacted, and read through the same scan. Retention on the table's time
column drops whole segments of an array table as it does any other; `latestPerKey` over a table with retention is still
refused (see [Materialized queries](materialized.md#array-columns-in-a-materialized-result)).

What it costs, in memory and on disk, is on the [sizing page](sizing.md#array-columns-what-a-value-costs). In short: size memory
for the raw bytes of the arrays plus 32 bytes a value. On disk it depends on the data: in the measured reference table a smooth
curve took 0.55–0.62 × its raw size, a column that repeats from row to row almost nothing, a column of full-precision differences its
full size; the whole table took 0.46 ×.

---

## Known limitations

(**BL-035, next train**) Not supported; there is no date.

- **Element selection and element predicates.** No `Rates[10]`, no `any element > x`, no `array_length`. The array is a value.
- **Sorting, grouping, aggregating, joining or keying on an array column.** See the table above.
- **An array column on an edge table.** Refused (see the table above): an edge table stores only its source, destination and
  label.
- **Embedded and POCO mapping.** `Aouda.Embedded` refuses the six names (BL-1213), and the C# client refuses POCO schema
  inference and POCO writes (`InsertAsync(entity)`) with an array property (`NotSupportedException`). Reading into a POCO with an
  array property works. Write dictionaries or column batches.
- **Studio can read an array column but not edit one**: no edit, no add-row field, no filter, sort, group or join on it.
- **The cold encoding is not configurable.** The cold tier chooses how to store an array column's pages; the column takes `Auto` only.

---

## Troubleshooting by symptom

| Symptom | Cause |
|---|---|
| `ARRAY_COLUMN_UNSUPPORTED` on `schema apply` or a query | the column is used in a clause an array cannot be used in; the message names the clause ([table](#what-is-refused-and-where)) |
| `Invalid column type 'double[]'` | the type name is exact: `Double[]` |
| A `Float32[]` reads `0.10000000149011612` in JavaScript | that is the float's exact value; `Math.fround(0.1)` prints the same. The text is chosen so a `Float32Array` reads it back exactly |
| `-0` came back as `0` (TypeScript) | a plain `number[]` is written by `JSON.stringify`, which writes `-0` as `0`. Write a `Float64Array` / `Float32Array` to keep it |
| `Column '…': unknown kind 9.` (C#) or `Malformed column-batch frame: column '…' has unknown kind 9.` (TypeScript) | an older SDK reading a frame with an array column; upgrade the SDK |
| An older TypeScript SDK returns a `Double[]` as a plain `number[]`, a `Byte[]` as a base64 string, or rounds an `Int64[]` | it reads JSON results (subscriptions, materialized queries, `returning`) without knowing the array types, and does not fail; upgrade the SDK |
| `…has type 514, which this build does not define.` | an older server binary meeting an array column's type number; arrays need this train's server |
| `Element 0 … is NaN; array elements must be finite numbers` | NaN, ±Infinity and their string forms are refused |
| `… is not an integer (1.5)` / `… is a string; a Double[] element is a JSON number` | an `Int32[]` / `Int64[]` element must be an integer; no element is a string except in a `String[]` |
| `A Byte[] value is a base64 string (got a JSON array)` | send a `Byte[]` as base64, not as an array of numbers |
| `Column 'x' … is not nullable, and row N … has no value for it (an array column takes no default …)` | a NOT NULL array column needs a value in every row, even under `coerce` |
