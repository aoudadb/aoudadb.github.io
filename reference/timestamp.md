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
and stores the **UTC instant**. **Only the instant in time is persisted.** (Text with no offset is UTC:
[time zones](#which-instant-which-day-time-zones-bl-1225-next-train).)

- **What is preserved:** the universal instant (the same as converting to UTC and storing that moment).
- **What is not preserved:** the offset, or which local representation was used at insert. That differs from SQL Server
  `datetimeoffset`, which stores the offset as part of the type.
- **What callers get back:** UTC values — `DateTime` with `DateTimeKind.Utc` in the C# SDK, an ISO-8601 UTC string in the
  TypeScript SDK's rows. To
  show another zone, convert at display time, or store a separate column (an IANA zone id, or the literal entered) when the
  original offset matters.

API and wire consumers should assume **Timestamp = UTC instant**, not a SQL Server–style `datetimeoffset` round-trip.

---

## Which instant, which day: time zones (**BL-1225, next train**)

What the server stores for a `Timestamp` or a `Date` never depends on the time zone of the client machine, of the server, or of
the machine a data directory is restored on. Until this change, text with no offset and a `DateTime` of kind `Unspecified` were read in the
**server's** local zone, and a `Date` was the **UTC** day of the value, so `DateTime.Today` written on a +01:00 machine was stored
as the day before.

| You send | A `Timestamp` column stores | A `Date` column stores |
|---|---|---|
| `"2026-03-01T00:00:00Z"` | that instant | `2026-03-01` |
| `"2026-03-01T00:00:00+01:00"` | the instant, `2026-02-28T23:00:00Z` | `2026-03-01` (the offset is not applied) |
| `"2026-03-01T00:00:00"` or `"2026-03-01 00:00:00"` (no offset) | **UTC**: `2026-03-01T00:00:00Z` | `2026-03-01` |
| `"2026-03-01"` | midnight UTC | `2026-03-01` |
| C# `DateTime` of kind `Utc` | that instant | its date |
| C# `DateTime` of kind `Local` (`DateTime.Now`, `DateTime.Today`) | the instant it names (the client writes the machine's offset) | **its date**: `DateTime.Today` is today |
| C# `DateTime` of kind `Unspecified` (`new DateTime(2026, 3, 1)`, `default`) | **UTC** | its date |
| C# `DateTimeOffset` | its instant | the date on its own clock |
| C# `DateOnly` | (a `Date` column) | `2026-03-01` |

- **An instant needs an offset to mean anything beyond UTC.** Text with no offset is UTC, not "local to whoever sent it". Aouda
  does not refuse it, because `"2026-03-01"` is the commonest value a person writes and every `Unspecified` `DateTime` would be refused
  with it, but a client in another zone that means *its* midnight must send the offset, or a `DateTime` that carries one (kind `Local` or `Utc`).
- **A `Date` is a calendar day.** It has no instant, so no offset or kind is applied: the day on the value is the day stored. Send a
  `DateOnly` or `"yyyy-MM-dd"` when you can. A TypeScript `Date` is an instant, so `new Date(2026, 2, 1)` — local midnight — is
  written as the previous day's `…23:00:00.000Z`, and a `Date` column will store the day *in that text*: send the string `"2026-03-01"`
  for a `Date` column from TypeScript.
- **Reading back.** A `Timestamp` is returned as UTC (`DateTimeKind.Utc`). To show it in the client's zone call `.ToLocalTime()`; printing
  `.Date` of the UTC value shows the previous day for a local midnight east of UTC. A `Date` is returned as midnight UTC of its day,
  and its `.Date` is the day.
- **A column-type change from `Timestamp` to `Date`** stores the **UTC** day of each instant: an instant has no day without a zone, and
  UTC is the stored one.
- Values a server in a non-UTC zone stored from text with no offset before this change are not rewritten.

---

## On the wire

- **Insert / upsert:** an ISO-8601 string (`"2026-06-23T14:00:00Z"`, with an offset, or without one — which is **UTC**,
  see [time zones](#which-instant-which-day-time-zones-bl-1225-next-train)) or an `Int64` **ticks**
  number. Both are accepted; a string is converted to UTC ticks before storage. A boolean or a fractional number is refused.
- **Filter value:** an ISO-8601 string or an `Int64` ticks number, read exactly as on insert (`QueryTranslator.NormalizeFilterValue`
  handles both): `where ts eq "2026-03-01T00:00:00"` is `2026-03-01T00:00:00Z`.
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

## Server-stamped columns (**NativeClients, 0.4.0**)

A `Timestamp` column declared `derived: { "serverTime": "insert" | "write" }` is stamped by the primary with its own UTC
clock (full tick precision, one reading per write request) and refuses any caller value. See
[Insert transforms — server-time stamp](../guides/insert-transforms.md#server-time-stamp-servertime).

## References

- [HTTP API reference](./http-api.md) — the wire forms of every type.
- `src/Aouda.Engine.Core/Schema/Types.cs` — `DataType.Timestamp` (`Int64` = .NET `DateTime.Ticks`, UTC).
- `src/Aouda.Engine.Core/Util/TimestampConversion.cs` — the shared conversion helpers.
- `src/Aouda.Engine.Core/Util/DateConversion.cs` — the same for a `Date` (the day on the value, **BL-1225**).
- `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs` — exact timestamp range pruning (**ColumnarRead, 0.3.0**;
  `SegmentPruner.cs` is deleted).
- `guides/market-data.md` — stock-quote schema design using `Timestamp` columns.
- `guides/time-series.md` — time-series clustering and range queries.
