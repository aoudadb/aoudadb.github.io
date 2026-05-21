---
title: "Timestamp Type"
nav_order: 2
parent: "Reference"
---

# DataType.Timestamp — Canonical representation

**Single source of truth** for how `DataType.Timestamp` is stored and converted across the engine, API, and any client adapters.

## Canonical storage: .NET DateTime.Ticks (UTC)

- **Storage type:** `Int64`
- **Meaning:** .NET `DateTime.Ticks` in UTC (same as `DateTime.UtcNow.Ticks` or `dateTime.ToUniversalTime().Ticks`).
- **Conversion:** Use `Aouda.Engine.Core.Util.TimestampConversion` so all components stay aligned:
  - `TimestampConversion.DateTimeToTicks(DateTime)` — for insert/serialization
  - `TimestampConversion.TicksToDateTime(long)` — for read/deserialization

## Why ticks (not Unix milliseconds)

The engine has always persisted Timestamp as ticks (see `AoudaEngine.ConvertToTimestampTicks` and HRA/TableAppender Int64 path). Schema comments previously said "unix millis"; that was incorrect and is fixed. Adopting Unix milliseconds would require a breaking storage migration.

## DateTimeOffset and “original” timezone offset (not stored)

Clients may send instants as `DateTimeOffset` or as ISO-8601 strings **with** an offset (e.g. `+05:00`). Aouda accepts those values and normalizes to **UTC ticks** for storage. **Only the instant in time is persisted.**

- **What is preserved:** The universal instant (same as converting to UTC and storing that moment).
- **What is not preserved:** The **offset** (or “which local representation was used at insert”) as metadata. That differs from SQL Server **`datetimeoffset`**, which stores offset as part of the type.
- **What callers get back:** Values map to **`DateTime` / `DateTimeOffset` in UTC** (e.g. `DateTimeOffset` with offset `+00:00`). To show another zone or offset in the UI, convert at display time or store a separate column (e.g. IANA zone id or a string) if you need the exact literal the user entered.

API and wire consumers should assume **Timestamp = UTC instant**, not “SQL Server–style datetimeoffset round-trip.”

## Where this is used

- **Engine.Api (AoudaEngine):** When converting row input to columnar values for insert, DateTime → long via ticks (using `TimestampConversion.DateTimeToTicks` or equivalent).
- **Engine.Api (ResultTransformer):** When building row results from columnar long[], long → DateTime via `TimestampConversion.TicksToDateTime`.
- **Wire/JSON:** If the server or client exposes a numeric timestamp over the wire, it must be defined in the wire protocol (e.g. "ticks" or "unix ms") and converted at the boundary using this contract so stored data remains ticks.

## References

- `docs/protocol/WIRE-PROTOCOL.md` — **Data Types** table and **Timestamp semantics** (API-facing summary)
- `src/Aouda.Engine.Core/Schema/Types.cs` — `DataType.Timestamp` and `EncoderPreference.Timestamp_Delta` comments
- `src/Aouda.Engine.Core/Util/TimestampConversion.cs` — shared conversion helpers
