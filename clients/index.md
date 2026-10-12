---
title: "Clients"
nav_order: 4
has_children: true
---

# Clients

Aouda provides official clients for .NET and TypeScript, plus a raw HTTP/REST API.

| Client | Package | Use case |
|---|---|---|
| **.NET** | `Aouda.Client` (NuGet) | Server mode — connect from any .NET app. Inserts (`InsertAsync`, typed and dictionary) travel as a binary column-batch frame once the server advertises it, JSON otherwise (**ColumnarCore S06, 0.2.0**; [HTTP API insert](../reference/http-api.md#post-apidatabasesdbtablesnamerows)); (**BL-980, next train**) a `415` on a frame is an error (`AoudaException`), not a JSON re-send — up to 0.3.x it re-sent as JSON and stayed on JSON for five minutes (**BL-716, 0.2.0**). A write stream survives a reconnect (**BL-987, next train**): a write or close during the reconnect waits for the stream to be re-opened on the new connection, and a write already sent when the connection dropped fails with `AoudaConnectionException` — its rows may or may not have been written — while the stream carries on. A .NET `decimal` goes as the frame's `ScaledDecimal` kind, what a `Decimal(p,s)` column stores (**LoadSpeed S13, next train** — up to 0.3.x it went as the retired 16-byte kind; `ColumnBatchBuilder.SetScaledDecimal` writes the kind directly, **ColumnarCore S13, 0.2.0**), and a `decimal` property declares its column with `[AoudaDecimal(p, s)]` (`Aouda.Abstractions.Attributes`), e.g. `[AoudaDecimal(18, 6)] public decimal Price { get; set; }` — without it `CreateTableAsync<T>()` and the embedded engine refuse the type, naming the property (**LoadSpeed S13, next train**; see [`Decimal(p,s)`](../guides/schema.md#decimalps-a-decimal-stored-as-a-scaled-integer-columnarcore-s13-020)). Query results come back as column-batch frames too: every table query and named-query execute asks for them, reads them into typed columns, and falls back to JSON from an older server; `GetRow`, `ToListAsync`, `ToObjects<T>` and `GetColumn<T>` give the values the JSON answer gives. `RemoteTableQuery` gains `GroupBy` / `GroupByBucket`, `Sum`, `Min`, `Max`, `Avg`, `CountDistinct` and `AggregateAsync()` (**ColumnarRead S16, 0.3.0**; [HTTP API query](../reference/http-api.md#post-apidatabasesdbquery)) |
| **.NET Embedded** | `Aouda.Embedded` (NuGet) | In-process database, no server needed |
| **TypeScript** | `@aouda/client` (npm) | Server mode — connect from Node.js, browser, or edge |
| **HTTP/REST** | Built into every Aouda server | Any language, direct API calls |

The .NET and TypeScript clients expose matching APIs where practical. See [Getting Started](../getting-started/index.md) for connection and first-query examples across all three.

⚠️ **The .NET packages target `net10.0` from 0.2.0** (**BL-739**) — `Aouda.Client`, `Aouda.Abstractions`, `Aouda.Embedded`, `Aouda.Testing` and the `Aouda.Cli` tool. A `net8.0` application cannot restore them: it stays on 0.1.40 until it retargets. .NET 8 leaves support on 2026-11-10.

For version compatibility across server, SDKs, and Studio, see [SDK Compatibility](./compatibility.md).

## Bulk load from a client

> **Version note.** The two options in this section ship in the **next** client release; they are
> not in `Aouda.Client` 0.1.20 / `@aouda/client` 0.1.19.

Both official clients expose bulk load, and both apply their own deadline to it rather than the
general-purpose request timeout — a `:commit` that seals a million rows cannot honestly finish
inside a deadline chosen for a key lookup.

| Option | Default | Why it exists |
|---|---|---|
| `BulkLoadOptions.RequestTimeout` | 10 minutes | Deadline for each individual bulk-load HTTP call, not for the job. The client-wide `Timeout` (30 s) is sized for point operations. If you pass your own `HttpClient`, its `HttpClient.Timeout` still caps this. |
| `BulkLoadOptions.MaxAppendBytes` | 8 MiB | Maximum serialized size of one `:append` body. Row-count batching alone leaves payload size at the mercy of the row shape; a wide row at the server's advertised 100 000 rows per append crosses ASP.NET's 30 MB body limit, which answers with a body-less `413`. |

**`:append` is not idempotent.** The server writes each accepted row into the session's row
channel before responding, so replaying an append whose response was lost duplicates every row
the first attempt landed. The clients deliberately exclude `:append` from their retry policy;
do not add one of your own. Resume from the durable cursor with the same idempotency key
instead.

**Tables with derived columns need a transform intent.** Pass exactly one of `applyTransforms`
or `preTransformed`. See [HTTP API — Bulk Load](../reference/http-api.md#bulk-load-api) and the
[bulk-load guide](../guides/bulk-load.md).
