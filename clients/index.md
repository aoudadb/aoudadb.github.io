---
title: "Clients"
nav_order: 4
has_children: true
---

# Clients

Aouda provides official clients for .NET and TypeScript, plus a raw HTTP/REST API.

| Client | Package | Use case |
|---|---|---|
| **.NET** | `Aouda.Client` (NuGet) | Server mode — connect from any .NET app |
| **.NET Embedded** | `Aouda.Embedded` (NuGet) | In-process database, no server needed |
| **TypeScript** | `@aouda/client` (npm) | Server mode — connect from Node.js, browser, or edge |
| **HTTP/REST** | Built into every Aouda server | Any language, direct API calls |

The .NET and TypeScript clients expose matching APIs where practical. See [Getting Started](../getting-started/) for connection and first-query examples across all three.

For version compatibility across server, SDKs, and Studio, see [SDK Compatibility](./compatibility.md).

## Bulk load from a client

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
