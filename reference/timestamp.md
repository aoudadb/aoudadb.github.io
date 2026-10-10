---
title: "Timestamp Type"
nav_order: 2
parent: "Reference"
---

# DataType.Timestamp — Canonical representation

**Single source of truth** for how `DataType.Timestamp` is stored, sent and read across the engine, the HTTP API and the client
SDKs.

> **Corrected (BL-808, 0.3.0):** earlier versions of this page said that `Timestamp` was migrated to **Unix
> milliseconds** in P29, with a per-column `TimestampUnit`, and cited an ADR "0008-timestamp-unit". None of that is or was
> the engine's behaviour, and that ADR does not exist: a `Timestamp` is, and has always been, **.NET UTC ticks** — as the
> [HTTP API reference](./http-api.md) says. There is no `timestampUnit` column property.

---

## Canonical storage: .NET ticks (UTC)

- **Storage type:** `Int64`
- **Meaning:** .NET `DateTime.Ticks` of the UTC instant — 100-nanosecond intervals since `0001-01-01T00:00:00Z`.
  `621355968000000000` is `1970-01-01T00:00:00Z`; one second is `10000000`.
- **Precision:** 100 ns (one tick). Finer source precision (true nanoseconds) needs its own `Int64` column.
- **Range:** `0001-01-01` to `9999-12-31`, the range of .NET `DateTime`.
- **Conversion in the engine:** `Aouda.Engine.Core.Util.TimestampConversion` (`DateTimeToTicks`, `TicksToDateTime`,
  `TryParseToTicks`), so every component reads and writes the same unit.

Converting to and from Unix time, when a client needs it:

```text
unixMilliseconds = (ticks - 621355968000000000) / 10000
ticks            = unixMilliseconds * 10000 + 621355968000000000
```

---

## DateTimeOffset and timezone offset (not stored)

Clients may send instants as `DateTimeOffset` or as ISO-8601 strings **with** an offset (e.g. `+05:00`). Aouda accepts them
and stores the **UTC instant**. **Only the instant in time is persisted.**

- **What is preserved:** the universal instant (the same as converting to UTC and storing that moment).
- **What is not preserved:** the offset, or which local representation was used at insert. That differs from SQL Server
  `datetimeoffset`, which stores the offset as part of the type.
- **What callers get back:** UTC values — `DateTime` with `DateTimeKind.Utc` in the C# SDK, an ISO-8601 UTC string in the
  TypeScript SDK's rows. To
  show another zone, convert at display time, or store a separate column (an IANA zone id, or the literal entered) when the
  original offset matters.

API and wire consumers should assume **Timestamp = UTC instant**, not a SQL Server–style `datetimeoffset` round-trip.

---

## On the wire

- **Insert / upsert:** an ISO-8601 string (`"2026-06-23T14:00:00Z"`, with or without an offset) or an `Int64` **ticks**
  number. Both are accepted; a string is converted to UTC ticks before storage. A boolean or a fractional number is refused.
- **Filter value:** an ISO-8601 string or an `Int64` ticks number, as on insert (`QueryTranslator.NormalizeFilterValue`
  handles both).
- **JSON result:** the `Int64` ticks value. The SDKs convert it: a UTC `DateTime` in C# (`ClientColumnarResult.Data`,
  `GetRow`, `Rows`, `ToObjects<T>`), an ISO-8601 UTC string in the TypeScript SDK's rows; the TypeScript SDK's
  `toColumnar().data` keeps the ticks (see [TypeScript](../clients/typescript.md)).
- **Column-batch frames:** a `Timestamp` column is 100-ns ticks counted from the **Unix epoch** (`1970-01-01T00:00:00Z`) —
  the JSON value minus `621355968000000000`. Both SDKs read it into the same values as from JSON. See
  [HTTP API — column kinds](http-api.md#post-apidatabasesdbquery).
- **GROUP BY a time bucket** (`minute` … `year`): the key is the bucket's start, a `Timestamp` — ticks on the wire like any
  other.

---

## Storage and pruning

A `Timestamp` column is stored as its `Int64` ticks and encoded like any 64-bit integer column (per-vector constant,
frame-of-reference, delta or run-length encoding, whichever is smallest). Its statistics (minimum, maximum, null count) are
ticks too, and range predicates are compared as exact 64-bit integers — never through a `double`, which cannot tell two
ticks apart above 2^53. Pruning is the scan's `RowGroupClassifier` over each row group's statistics; `SegmentPruner` and its
`LongWindows` path are deleted (**ColumnarRead, 0.3.0**).

---

## Column definition example

```json
{
  "name": "eventTime",
  "type": "Timestamp"
}
```

---

## References

- [HTTP API reference](./http-api.md) — the wire forms of every type.
- `src/Aouda.Engine.Core/Schema/Types.cs` — `DataType.Timestamp` (`Int64` = .NET `DateTime.Ticks`, UTC).
- `src/Aouda.Engine.Core/Util/TimestampConversion.cs` — the shared conversion helpers.
- `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs` — exact timestamp range pruning (**ColumnarRead, 0.3.0**;
  `SegmentPruner.cs` is deleted).
- `guides/market-data.md` — stock-quote schema design using `Timestamp` columns.
- `guides/time-series.md` — time-series clustering and range queries.
