---
title: "Timestamp Type"
nav_order: 2
parent: "Reference"
---

# DataType.Timestamp — Canonical representation

**Single source of truth** for how `DataType.Timestamp` is stored and converted across the engine, API, and any client adapters.

> ⚠️ **Under review (BL-808).** The [wire section](#usage-in-the-wire-protocol) below is correct: the wire carries ticks.
> What this page says about **storage** — Unix milliseconds and `TimestampUnit` since P29 / ADR 0008 — disagrees with the
> wire reference and the engine's readers and tests, which build `Timestamp` values from `DateTime.Ticks`. Which half of
> ADR 0008 is current is open; until BL-808 settles it, rely on the wire section, not on the storage unit below.

> **Breaking change notice (P29, June 2026):** Prior to P29, `DataType.Timestamp` was stored as .NET `DateTime.Ticks` (100 ns units). P29 migrated all internal storage to **Unix milliseconds**. All existing persisted timestamp data must be re-ingested. There is no in-place migration path. This is an explicit, accepted breaking change — see [ADR 0008](../decisions/0008-timestamp-unit.md).

---

## Canonical storage: Unix milliseconds (UTC)

- **Storage type:** `Int64`
- **Meaning:** Unix epoch milliseconds in UTC. `1000` = one second after `1970-01-01T00:00:00.000Z`.
- **Precision:** Milliseconds by default. Microsecond and nanosecond units are also supported (see §TimestampUnit below).
- **Conversion:** Use `Aouda.Engine.Core.Util.TimestampConversion` so all engine components stay aligned:
  - `TimestampConversion.DateTimeToUnixUnits(DateTime, TimestampUnit)` — for insert/serialization
  - `TimestampConversion.UnixUnitsToDateTime(long, TimestampUnit)` — for read/deserialization

---

## TimestampUnit enum

Each `Timestamp` column carries a `TimestampUnit` property that governs how the stored `Int64` is interpreted:

| Enum value | Stored unit | Practical range per segment |
|------------|-------------|------------------------------|
| `Milliseconds` (default) | Unix ms | ~24.8 days delta in hot FOR encoding (virtually all intraday workloads) |
| `Microseconds` | Unix μs | ~35 minutes delta in hot FOR encoding |
| `Nanoseconds` | Unix ns | ~2.1 seconds delta in hot FOR encoding |

The `TimestampUnit` defaults to `Milliseconds` if not specified at column creation. Existing tables without the field also default to `Milliseconds`.

> **Nanoseconds precision note:** The .NET `DateTime` type has 100 ns resolution (ticks). When `TimestampUnit = Nanoseconds`, the engine stores `ticks × 100` — which gives 100 ns resolution, not true hardware nanosecond precision. True hardware-ns precision requires a dedicated `Int64` column storing raw nanosecond values.

---

## Hot-tier compact encoding

The engine exploits the unix-ms representation for efficient hot-segment storage:

**Frame-of-Reference (FOR) Timestamp encoding:** At hot segment build time, if `(max - min) ≤ int.MaxValue`, the engine stores a `(long base, int[] deltas)` pair instead of `long[]`. This reduces storage to 4 bytes/value (vs 8 bytes for raw `long[]`). For millisecond-unit segments, the FOR range covers ~24.8 days — virtually all intraday segments benefit. Microsecond segments: ~35 minutes. Nanosecond segments: ~2.1 seconds.

The query layer sees no difference — `HotColumnSegment` reconstructs values as `base + (long)deltas[i]`.

---

## DateTimeOffset and timezone offset (not stored)

Clients may send instants as `DateTimeOffset` or as ISO-8601 strings **with** an offset (e.g. `+05:00`). Aouda accepts those values and normalizes to **UTC unix milliseconds** for storage. **Only the instant in time is persisted.**

- **What is preserved:** The universal instant (same as converting to UTC and storing that moment).
- **What is not preserved:** The offset (or "which local representation was used at insert") as metadata. That differs from SQL Server `datetimeoffset`, which stores offset as part of the type.
- **What callers get back:** Values map to `DateTime` / `DateTimeOffset` in UTC (e.g. `DateTimeOffset` with offset `+00:00`). To show another zone or offset in the UI, convert at display time or store a separate column (e.g. IANA zone ID or a string) if you need the exact literal the user entered.

API and wire consumers should assume **Timestamp = UTC instant**, not "SQL Server–style datetimeoffset round-trip."

---

## Predicate pruning and precision

Prior to P29, `SegmentPruner` converted Int64/Timestamp cluster keys to `double` for window extraction. Values above 2^53 lose precision as a `double`, causing incorrect segment pruning for unix-millisecond timestamps (which are well above 2^53 for any post-1970 date). P29 fixed this by switching Int64/Timestamp to a dedicated `LongWindows` path that avoids any floating-point conversion. Since **ColumnarRead** (next train) `SegmentPruner` is deleted: pruning is the scan's `RowGroupClassifier` over each row group's statistics, which compares integers and timestamps exactly, as `Int64`.

---

## Usage in the wire protocol

The wire carries `Timestamp` as **ticks** (100 ns units, UTC), not Unix milliseconds (**corrected, architecture review, next
train** — this section said milliseconds; the server sends and reads ticks):

- **JSON:** an `Int64` of .NET ticks since `0001-01-01T00:00:00Z` (`DateTime.Ticks`).
- **Column-batch frames** (an insert body and a query response): an `Int64` of ticks since the Unix epoch — the JSON value
  minus 621,355,968,000,000,000. See [HTTP API — column kinds](http-api.md#post-apidatabasesdbquery).
- **Insert:** Pass an ISO-8601 string (`"2026-06-23T14:00:00Z"`) or, in JSON, a number, which is read as .NET ticks.
- **Query filter value:** Pass either ISO-8601 or a number of .NET ticks. `QueryTranslator.NormalizeFilterValue` handles both.
- **Result value:** .NET ticks in JSON results. The .NET SDK gives a UTC `DateTime`; the TypeScript SDK gives a row value as an
  ISO 8601 string, and its `toColumnar().data` keeps the ticks (see [TypeScript](../clients/typescript.md)).

---

## Where this is used

- **Engine.Api (`AoudaEngine`):** `TimestampConversion.DateTimeToUnixUnits` converts `DateTime → Int64` at insert time.
- **Engine.Api (`ResultTransformer`):** `TimestampConversion.UnixUnitsToDateTime` converts `Int64 → DateTime` in query results.
- **Engine.Storage (hot segment builder):** Frame-of-Reference encoding computed from unix-ms deltas.
- **Engine.Storage (`RowGroupClassifier`):** exact `Int64` comparison for timestamp range pruning (no double cast). `SegmentPruner` and its `LongWindows` path are deleted (**ColumnarRead, next train**).
- **Catalog:** `TimestampUnit` persisted per column in `CatalogCheckpoint` (v4+). Tables without the field default to `Milliseconds`.
- **Wire/JSON:** `Int64` .NET ticks over HTTP JSON, ticks since the Unix epoch in column-batch frames; ISO-8601 strings accepted on input and normalized (see [above](#usage-in-the-wire-protocol)).
- **Market data:** The unix-ms unit is the standard for financial timestamps; used by Aggregate MQ time-bucket functions (`TruncateToHour`, `TruncateToMinute`, etc.) which operate on unix-ms values and return bucket values as `Int64` unix-ms.

---

## Column definition example

```json
{
  "name": "eventTime",
  "type": "Timestamp",
  "timestampUnit": "Milliseconds"
}
```

For microsecond financial data:

```json
{
  "name": "tradeTime",
  "type": "Timestamp",
  "timestampUnit": "Microseconds"
}
```

---

## References

- `docs/decisions/0008-timestamp-unit.md` — ADR documenting the migration from ticks to unix ms
- `src/Aouda.Engine.Core/Schema/Types.cs` — `DataType.Timestamp`, `TimestampUnit` enum
- `src/Aouda.Engine.Core/Util/TimestampConversion.cs` — shared conversion helpers (`DateTimeToUnixUnits`, `UnixUnitsToDateTime`)
- `src/Aouda.Engine.Storage/Hot/HotSegmentBuilder.cs` — FOR Timestamp encoding
- `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs` — exact timestamp range pruning (**ColumnarRead, next train**; `SegmentPruner.cs` is deleted)
- `guides/market-data.md` — Stock-quote schema design using Timestamp columns
- `guides/time-series.md` — Time-series clustering and range queries
