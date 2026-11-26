---
title: "Real-time Streaming"
nav_order: 7
parent: "Guides"
---

# Aouda Functionality: Real-Time Streaming

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

Coverage phases: P10
Primary task folders: `docs/tasks/P10/`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How do I use streaming now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`
- **P37 (current):** [HTTP API WebSocket](../reference/http-api.md#websocket-streaming-protocol) — path is `/api/databases/{db}/ws`; snapshots page then `snapshot_complete`; overflow is a server `gap` (`last_seq`, `discarded`), not client `seq > last + 1`; opt-in `conflate` sets `values_skipped` (distinct from `gap`) **on value updates only** — it is a no-op on insert-only streams; `re_auth` keeps subscriptions through token refresh. Browser-tier callers subscribe **by named-query name**. See [Named queries](named-queries.md#subscribe-by-name), [Direct client access](direct-client-access.md), and [browser-tier read limits](browser-tier-read-limits.md).

(**ADR 0072, 0.14.0**) **Subscribing to a formula table.** A table with a [formula column](formulas.md#live-subscriptions) is subscribed to like any table, filtered on its own columns: no new message. After an input edit the subscription receives the input's change and then each formula row that changed, once, at its final value; a recompute that left a value unchanged sends nothing. A row's formula is its JSON object in `row`, `prev` and a snapshot page (a map in MessagePack). A change event's `token` never claims an input the event's values do not reflect; tokens are not ordered across events, so keep the highest. A subscribe with `at_least` on a formula table waits for the formulas, as a read does.

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Aouda streaming exists to make data movement and data observation first-class primitives, rather than requiring polling loops and per-request write overhead.

- User problem solved:
  - Clients need live table updates without periodic `query` polling.
  - High-throughput writes should avoid per-request HTTP round-trips.
  - Reconnects should recover continuity without forcing full refresh every time.
- Operational outcomes:
  - Snapshot plus incremental `change` event model for subscribers.
  - Bidirectional stream path for `insert` and `upsert` ingest.
  - Auth-aware event delivery and write validation in the streaming path.
  - Optional fallback transport (long-poll) when WebSocket is blocked.
- Scope boundaries:
  - This domain covers database-scoped table subscriptions, write streams, reconnect/resume, MessagePack wire mode, and long-poll fallback.
  - It does not provide broker-style consumer groups, exactly-once guarantees, cross-database subscriptions, or transaction-scoped streaming writes.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What happens by default with no tuning? | `2.3 Defaults and zero-config behavior` |
| What is shipped vs planned vs reserved? | `2.4 Availability status` |
| Which P10 sessions delivered which behavior? | `2.5 Phase coverage matrix` |
| End-to-end feature completeness | `2.6 Capability coverage matrix` |
| Protocol and semantics mental model | `2.7 Core concepts and mental model` |
| How snapshot/resume/write internals work | `2.8 How Aouda implements it` and `2.8.1 Critical path walk-throughs` |
| All knobs and defaults | `2.10 Configuration and settings reference` |
| .NET, TypeScript, and HTTP/protocol mapping | `2.11 API and CLI coverage reference` |
| Ops checks and incident response | `2.13 Operations and observability`, `2.14 Troubleshooting by symptom` |
| What remains incomplete | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.11 API and CLI coverage reference`, `2.12 Scenario playbooks` |
| Operator/SRE | `2.10 Configuration and settings reference`, `2.13 Operations and observability`, `2.14 Troubleshooting by symptom` |
| SDK maintainer | `2.11 API and CLI coverage reference`, `2.16 Test coverage matrix`, `2.17 Testing gaps and proposed tests` |
| Engine/server contributor | `2.5 Phase coverage matrix`, `2.8 How Aouda implements it`, `2.8.1 Critical path walk-throughs`, `2.19 References` |

### Source map

- Task/report evidence:
  - `docs/tasks/P10/P10-S1-ChangeEventFoundation.md`
  - `docs/tasks/P10/P10-S3-WebSocketInfrastructure.md`
  - `docs/tasks/P10/P10-S4-ADRAFilteredSubscriptions.md`
  - `docs/tasks/P10/P10-S5-ServerSideSubscriptionFilters.md`
  - `docs/tasks/P10/P10-S7-StreamingWrites.md`
  - `docs/tasks/P10/P10-S9-CSharpClientStreamingAPI.md`
  - `docs/tasks/P10/P10-S10-MaterializedQuerySubscriptions.md`
  - `docs/tasks/P10/P10-S11-HotCacheAndLiveCollection.md`
  - `docs/tasks/P10/P10-S12-TypeScriptWebSocketTransport.md`
  - `docs/tasks/P10/P10-S13-TypeScriptClientStreamingAPI.md`
  - `docs/tasks/P10/P10-S14-I3-MessagePackWireMode.md`
  - `docs/tasks/P10/P10-S14-I4-HttpLongPollFallback.md`
- Core server/engine code:
  - `src/Aouda.Engine.Storage/Streaming/ChangeEventEmitter.cs`
  - `src/Aouda.Server/WebSocket/WebSocketHandler.cs`
  - `src/Aouda.Server/WebSocket/MessageRouter.cs`
  - `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
  - `src/Aouda.Server/WebSocket/Handlers/WriteStreamHandler.cs`
  - `src/Aouda.Server/Controllers/LongPollStreamController.cs`
  - `src/Aouda.Server/WebSocket/WebSocketOptions.cs`
  - `src/Aouda.Server/WebSocket/StreamingWriteOptions.cs`
- .NET client code:
  - `src/Aouda.Client/AoudaClient.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `src/Aouda.Client/Internal/WebSocketTransport.cs`
  - `src/Aouda.Client/Internal/LongPollTransport.cs`
  - `src/Aouda.Client/Streaming/SubscriptionAsyncEnumerable.cs`
  - `src/Aouda.Client/Streaming/WriteStream.cs`
- TypeScript client code (cross-repo):
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/streaming/websocket-transport.ts`
  - `../aouda-client-ts/src/streaming/longpoll-transport.ts`
  - `../aouda-client-ts/src/streaming/subscription.ts`
  - `../aouda-client-ts/src/streaming/write-stream.ts`
- Test evidence:
  - `tests/Aouda.Server.Tests/WebSocket/WebSocketHandlerIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/WebSocket/SubscriptionHandlerIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/WebSocket/WriteStreamHandlerIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/WebSocket/StreamingSubscriptionManagerTests.cs`
  - `tests/Aouda.Protocol.Tests/Streaming/MessageSerializerTests.cs`
  - `tests/Aouda.Client.Tests/Streaming/SubscriptionApiTests.cs`
  - `tests/Aouda.Client.Tests/Streaming/WriteStreamApiTests.cs`
  - `tests/Aouda.Client.Tests/Streaming/StreamingFallbackLifecycleTests.cs`
  - `tests/Aouda.Client.Tests/Streaming/MaterializedQuerySubscriptionApiTests.cs`
  - `../aouda-client-ts/tests/streaming/websocket-transport.test.ts`
  - `../aouda-client-ts/tests/streaming/subscription.test.ts`
  - `../aouda-client-ts/tests/streaming/write-stream.test.ts`
  - `../aouda-client-ts/tests/streaming/longpoll-transport.test.ts`

## 2.3 Defaults and zero-config behavior

If you do nothing:

- No streaming connection is created; normal request/response APIs work as usual.
- If you call streaming APIs on server mode clients, transport defaults to WebSocket JSON mode with reconnect behavior.
- If WebSocket connect fails, both .NET and TypeScript clients default to enabling long-poll fallback.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| Server `Aouda:WebSocket:EnableCompression` | `true` | Accepts permessage-deflate on WebSocket upgrades |
| Server `Aouda:WebSocket:EnableMessagePack` | `true` | Allows auth-time `wire_mode=msgpack` negotiation |
| Server `Aouda:WebSocket:MaxConnections` | `10000` | Global concurrent streaming connection cap |
| Server `Aouda:WebSocket:HeartbeatInterval` | `20s` | Server heartbeat cadence; also the longest an open session outlives a credential that expired or whose user was disabled (a key revoked on the node ends its sessions there at once; **BL-1001, 0.14.0**, see [Realtime authorization](../reference/http-api.md#realtime-revoked-credential)) |
| Server `Aouda:WebSocket:IdleTimeout` | `5m` | Idle WebSocket auto-close threshold |
| Server `Aouda:WebSocket:LongPollWaitTimeout` | `25s` | Default long-poll wait horizon |
| Server `Aouda:WebSocket:LongPollSessionIdleTimeout` | `2m` | Long-poll session expiry window |
| Server `Aouda:WebSocket:LongPollMaxQueuedMessages` | `1000` | Queue bound per long-poll session |
| Server `Aouda:WebSocket:LongPollMaxBatchSize` | `128` | Max messages returned per long-poll poll response |
| Server `Aouda:WebSocket:StreamingWrites:AckInterval` | `500ms` | Periodic write-stream ack cadence |
| Server `Aouda:WebSocket:StreamingWrites:SoftPendingRows` | `5000` | Above this threshold, rows can be rejected as `STREAM_PAUSED` |
| Server `Aouda:WebSocket:StreamingWrites:HardPendingRows` | `10000` | Above this threshold, stream is closed |
| .NET `WebSocketTransportOptions.WireMode` | `Json` | Starts in text JSON unless negotiated otherwise |
| .NET `WebSocketTransportOptions.EnableCompression` | `true` | Enables client-side compression when supported |
| .NET `WebSocketTransportOptions.EnableLongPollFallback` | `true` | Automatic fallback to long-poll on WebSocket connect failure |
| .NET `WebSocketTransportOptions.ReconnectBaseDelay` | `1s` | Reconnect exponential backoff base |
| .NET `WebSocketTransportOptions.ReconnectMaxDelay` | `30s` | Reconnect backoff cap |
| TypeScript `streaming.wireMode` | `"json"` | Uses JSON frames unless MessagePack is selected |
| TypeScript `streaming.wsFactory` | the platform `WebSocket` | Makes the socket; compression is the socket's own (**NativeClients, 0.4.0**: replaces `streaming.enableCompression`, which reached only the `ws` package) |
| TypeScript `streaming.enableLongPollFallback` | `true` | Uses fallback transport wrapper by default |
| TypeScript `streaming.longPollWaitMs` | `25000` | Long-poll wait on TS fallback transport |

## 2.4 Availability status (implementation honesty)

### Available now

- Streaming foundation:
  - Structured engine change events and sequence tracking.
  - Protocol message contracts and serializer support for JSON and MessagePack modes.
- Server WebSocket path:
  - `/api/databases/{db}/ws` endpoint with auth handshake and heartbeat.
  - Connection manager/session state with per-connection subscriptions and write streams.
- Subscription behavior:
  - Snapshot + incremental delivery.
  - User filter evaluation.
  - Row filtering of snapshots and events by the caller's `read` statements, and a re-read of the statements on every subscribe and resume (**BL-1227, 0.9.0**: see [Who may subscribe, and what a subscription sees](#who-may-subscribe-and-what-a-subscription-sees)).
  - Resume semantics with `resume_from` and change-buffer replay/fallback.
- Write-stream behavior:
  - `stream_open`, `stream_rows`, `stream_ack`, `stream_close`.
  - `insert` and `upsert` modes.
  - Backpressure thresholds, per-row authorization errors in `stream_ack.errors`.
- Client surfaces:
  - .NET: `SubscribeAsync`, typed `SubscribeAsync`, `OpenWriteStreamAsync`, shared streaming transport.
  - TypeScript: `table(...).subscribe(...)`, async iteration, `openWriteStream(...)`.
- Extended transport:
  - MessagePack wire-mode negotiation and binary framing support.
  - HTTP long-poll fallback server endpoint plus .NET/TypeScript fallback transports.
- Materialized query streaming:
  - Subscribe via table path to result tables with incremental updates.
- Horizon notices (**Horizon, 0.5.0**):
  - `snapshot_complete` carries `horizon` / `horizon_column` for a windowed result or a table with retention; `horizon` and
    `range_delete` messages tell a client what to drop. See [Horizons and range deletes](#horizons-and-range-deletes).

### Planned / proposed

Documented intent that is not currently fully productized:

- Cross-database subscription surfaces.
- Exactly-once delivery model and consumer-group semantics.
- Broker-style stream partition management semantics.

### Reserved / not yet wired

- Dedicated error code for "materialized query exists but not yet ready" is not wired as a separate protocol code path (tracked as BL-053 in task report context).
- Client-side hot cache / `Live()` / SSE `SubscriptionController` withdrawn (BL-162, 2026-08-13). Local materialization returns on named queries (BL-164).

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P10 S7 | `P10-S7-StreamingWrites.md` | Write stream open/rows/close, insert/upsert, acks, backpressure thresholds, per-row auth rejections | None explicitly listed in S7 report | None |
| P10 S9-S13 | `P10-S9-CSharpClientStreamingAPI.md`, `P10-S10-MaterializedQuerySubscriptions.md`, `P10-S11-HotCacheAndLiveCollection.md`, `P10-S12-TypeScriptWebSocketTransport.md`, `P10-S13-TypeScriptClientStreamingAPI.md` | .NET and TypeScript streaming APIs, typed subscribe, write streams, MQ subscription behavior | Hot cache + `Live()` withdrawn BL-162 | BL-053 (S10); BL-162 (S11) |
| P10 S14 I3/I4 | `P10-S14-I3-MessagePackWireMode.md`, `P10-S14-I4-HttpLongPollFallback.md` | MessagePack negotiation + binary mode; long-poll fallback endpoint and client fallback transport | None called out in I3/I4 reports | None |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Snapshot + incremental table subscriptions | Yes | No | No | `SubscriptionHandler.cs`, S4 report/tests | Snapshot-first ordering with version |
| Server-side user filters | Yes | No | No | `SubscriptionFilterEvaluator.cs`, S5 report/tests | Filter normalized against table schema |
| Resume from version (`resume_from`) | Yes | Yes | No | `SubscriptionHandler.cs` resume paths | Implemented in code; dedicated S6 task report template remains unfilled but behavior is present |
| Streaming writes (`insert`/`upsert`) | Yes | No | No | `WriteStreamHandler.cs`, S7 report/tests | Includes per-row rejection reporting |
| Write-stream backpressure and ack cadence | Yes | No | No | `StreamingWriteOptions.cs`, `WriteStreamBackpressure.cs` | Soft reject/hard close thresholds |
| .NET streaming API surface | Yes | No | No | `ITableOperations` + client streaming classes + S9 tests | Embedded mode intentionally throws not-supported |
| TypeScript streaming API surface | Yes | No | No | `query-builder.ts`, streaming modules, S12/S13 tests | Callback + async iteration + write stream |
| MessagePack streaming wire mode | Yes | No | No | `WireMode.cs`, serializer, WS transports, I3 tests | Long-poll remains JSON-only |
| HTTP long-poll fallback transport | Yes | No | No | `LongPollStreamController.cs`, client transports, I4 tests | Fallback selected on WS connect failure |
| Hot cache sync + C# `Live()` collection | No | No | Yes | withdrawn BL-162 | Rebuild on named queries (BL-164) |
| Exactly-once delivery semantics | No | No | Yes | ADR scope and protocol behavior | At-least-once with version dedup model |
| Cross-database streaming subscription | No | No | Yes | P10 scope notes | One database per streaming connection path |

## 2.7 Core concepts and mental model

- `snapshot`:
  - Initial full result set for a subscription target at a specific version.
- `change`:
  - Incremental event with operation (`insert`, `update`, `delete`, `upsert`) and monotonic version.
- `resume_from`:
  - Client-provided last seen **change-event sequence** used to recover after reconnect. Unchanged by P38.
- `stream` / `resume_stream` (**BL-1823, next train**):
  - A version is a number of **one** change stream, which the server starts again at every open of the database's engine (a restart, a
    restore, an unquarantine, a drop and create, a replica's checkpoint). `snapshot_complete.stream` names it (opaque); a resume sends it
    back as `resume_stream` beside `resume_from`. A resume of another stream — or a `resume_from` with no `resume_stream` — is answered
    with a fresh snapshot, never an error.
- `token` (P38):
  - Optional 42-hex consistency token on `snapshot` / `snapshot_complete` / `change` / heartbeat, **alongside** `version`. Hand it to HTTP `?at_least=` or subscribe `at_least`. Heartbeat `version` is **not** a WAL sequence. See [Freshness](freshness.md).
- `at-least-once`:
  - Clients may see replayed events; version-based dedup is required for idempotent reducers.
- Subscription filtering layers:
  - user filter (from subscribe request),
  - partition-level and row-level authorization filters,
  - target-table match.
- Write stream lifecycle:
  - open -> rows (sequence increasing) -> ack progression -> close.
  - (.NET, **BL-987, 0.4.0**) On a reconnect `Aouda.Client` re-opens each write stream before anything else is sent on it:
    a `WriteAsync` or `CloseAsync` during the reconnect waits for the re-open (a stream being closed is re-opened too, so its
    close is delivered). A write already sent when the connection dropped fails with `AoudaConnectionException` — its rows may
    or may not have been written, so check before re-sending them — and the stream carries on on the new connection. Up to
    0.3.x such a write could race the re-open and fail the stream for good ("No open stream with id …"), or hang.
  - (TypeScript, **BL-1776, BL-1834, next train**) `@aouda/client` pipelines: `write()` resolves when the frame was sent, and `close()` only when
    the server acknowledged every frame. A refusal, a refused row (`stream_ack` with `errors`) or a connection lost with a frame
    unacknowledged **ends the stream** with an `AoudaWriteStreamError`, which the next `write()` and every `close()` reject with; no
    frame is sent again. With every frame acknowledged the stream re-opens on the new connection and goes on. See
    [write streams](../clients/typescript.md#write-streams).
  - (**BL-1850, next train**) A frame the server wrote part of and could not finish is answered with an `error` frame
    `WRITE_APPLIED_RESPONSE_FAILED`, never a capacity code with "retry after": a row refused for capacity after earlier rows of the
    frame were written (a frame refused for row security is written one row at a time, so its other rows are stored), or an insert
    transform's copy that failed after the frame's rows were committed. **Do not re-send the frame**: read the table to see what was written.
- Transport strategy:
  - primary WebSocket, optional long-poll fallback for restricted environments. Over the fallback `@aouda/client` sends one stream's
    frames, and one subscription id's `subscribe` and `unsubscribe`, one after another in the order they were made, so they reach the
    server in order (**BL-1627, next train**); everything else is sent at once. A client that calls `/send` itself must do the same:
    the server handles one stream's frames in the order their requests arrive.
- Bulk loads (**Lead S27b, 0.6.0**: documented; the behaviour is not new):
  - **A bulk load emits no change events on the table it loads.** Its rows become visible at the job's commit, but a
    subscriber to that table receives no `change` event for them, and no other signal: no gap, no notice. A client that
    must see them re-reads the table (or re-subscribes for a fresh snapshot) after the load's `:commit` answers. Inserts,
    updates, deletes, upserts and merges are announced as before.
  - A subscriber to a **materialized query's result** does see a load's effect: when the load's pass folds it in, or a
    rebuild publishes, the result's changed groups arrive as ordinary `change` events (a rebuild announces the difference
    between the old result and the new one).

Invariants:

- Snapshot-first contract is preserved before incremental delivery.
- Sequence/version continuity is monotonic and is the basis for resume and dedup.
- Authorization filtering is enforced in subscription delivery and write validation paths.
- Long-poll transport negotiates JSON wire mode only.

### Many readers of one subscription (**BL-1384, 0.11.0**)

The official SDKs share identical subscriptions on one client: every subscribe with the same name, canonical arguments and options
(`conflate`, `orderByIndex`, `atLeast` / `waitMs` / `onExceeded`, `crossPartitionAccess`) reads one server subscription, and the last
reader to leave closes it. The server sees one subscription, so the per-connection and per-identity caps count distinct
feeds, not widgets. A subscribe with `resume_from` never shares, and sharing does not merge subscriptions whose arguments differ. See
[C#](../clients/dotnet.md) and [TypeScript](../clients/typescript.md) for the details (late joiners, per-consumer queues).

### Who may subscribe, and what a subscription sees

A subscription is a read, and it is held to the rules of the HTTP read it mirrors (**BL-1227, 0.9.0**):

- **The same check.** `subscribe` is authorized as `POST /query` is: the principal needs a `read` statement on the table, and for a
  named-query subscription an `execute` statement on **the named query**. A refusal is the code HTTP answers (`AUTH_POLICY_DENIED`,
  `AUTH_CREDENTIAL_MISSING`), sent as an `error` frame for that subscription.
  A write stream (`stream_open`) needs `write` on the table. Up to 0.8.0 a subscribe and a `stream_open` asked nothing of the
  kind, so a credential HTTP refused (a keyless caller, a user who may read nothing) could read, and write, a table over the socket.
- **The same rows.** A subscription's snapshot returns what an HTTP query by the same credential returns — the rows its `read`
  statements' `where`s admit, with its `filter` — and its change events are judged by the same compiled condition the snapshot
  scans with, so a live event is delivered exactly when the snapshot would have returned its row (up to
  0.16.0 live events were judged by a separate evaluator, which could answer differently from the query on a typed comparison). A
  statement whose condition the server cannot evaluate at all admits no row, live as in the snapshot. A live event the server
  cannot judge ends that subscription with an `error` frame `INTERNAL_ERROR` (it was dropped for every subscriber of the table).
  Access is described in [Authorization](../auth/authorization.md).
- **Permissions are re-read on every `subscribe`**, a first subscribe included. A subscribe whose permissions cannot be read is
  **refused** (`PERMISSION_REVOKED`), or refused with a retryable capacity code (`SERVICE_UNAVAILABLE`, `MEMORY_BUDGET_EXCEEDED`, …)
  when the read is refused for capacity — never admitted on a stale answer.
- **A policy change reaches an open subscription on the next event.** After a statement, role or attribute changes, the next event on any table the
  session subscribes to (or its next `subscribe` or `re_auth`) re-keys all of that session's subscriptions before the event is
  delivered: a narrowed one stops receiving what it may no longer see, and one narrowed to nothing, or that no longer passes the
  check, ends with an `error` frame `PERMISSION_REVOKED`. A subscription that is **widened** (a statement added) is
  **not re-snapshotted**: rows that became visible are not pushed, only events from the re-key on. Resubscribe to read the rows
  that were already there.
- **A resume whose policy admits no row is an open stream.** A `subscribe` with `resume_from` whose statements admit no row of the
  table is not refused: it continues offered no event, as a fresh `subscribe` with the same statements gets an empty snapshot and
  stays open, and it widens when the statements do (up to 0.16.0 it ended with `PERMISSION_REVOKED`).
  `PERMISSION_REVOKED` ends a stream when a re-key takes away the rows it admitted — a resumed stream included. The server keeps
  nothing of a closed connection, so a stream whose rows were taken away while it was disconnected resumes open and is offered no
  row, like one that never had any.
- **Audit.** When an unconditional statement decides what a subscription or a write stream reaches, on a table that another statement
  restricts with a `where`, one `unconditional_access` row is written: once per subscribe or resume (operation `subscribe`), once per write stream
  (operation `insert`, on the first batch the statement decides, and again if the deciding statements change), and once for a re-key that newly uses one (operation `rekey`) — **never one per
  event**. The `cross_partition_access` flag alone writes nothing. See [Audit](../auth/authorization.md#audit).

A subscription on a partitioned table needs the same partition filter as a read, or the `cross_partition_access` flag on the
`subscribe` message (see the HTTP/protocol examples below, and
[a subscription that spans partitions](partitioning.md#a-subscription-that-spans-partitions)).

### When the user changes

A realtime connection belongs to the principal that opened it: what is subscribed on it was read as that principal, and the server refuses
another's `re_auth`. In the TypeScript client (**BL-1854, next train**) a sign-in as another user, or a sign-out, therefore ends every subscription
and write stream with `AUTH_SESSION_REPLACED`, and what is made after it is on a new connection; a new token of the same user re-authenticates
the connection, on both transports (**BL-1858, next train**). See
[When the user changes](../clients/typescript.md#with-authentication). The .NET client does the same (**BL-1856, next train**): its
subscriptions and write streams end with `AoudaSessionReplacedException` (`AUTH_SESSION_REPLACED`) — see
[When the user changes](../clients/dotnet.md#when-the-user-changes-bl-1856-next-train).

### When the database is replaced (**BL-1818, next train**)

A subscription belongs to the database as it was when it subscribed. When the server replaces that database's engine while it runs, the
subscription ends with an `error` frame naming it, on the open connection: the connection, its other subscriptions and its write streams
stay open, and the subscription's slot under the connection and identity limits is free again. Over WebSocket and long-poll alike.

| What happened to the database | The code | Sent |
|---|---|---|
| A set restore (`POST /admin/backup/restore/{id}`), and the database is open after it | `SUBSCRIPTION_DATABASE_REPLACED` | when the restore has finished — the databases reopened, the restored members registered, the declared access converged — so a subscribe sent at once is admitted. A restore that failed or was cancelled after it stopped the engines ends them too |
| A restore after which the database did not open (it is quarantined) | `DATABASE_QUARANTINED` | when the restore has finished |
| Quarantined (`POST /api/databases/{db}/quarantine`) | `DATABASE_QUARANTINED` | at the quarantine; an unquarantine does not bring the subscription back |
| Dropped (and perhaps created again) | `DATABASE_NOT_FOUND` | at the drop |
| A replica's checkpoint install | `SUBSCRIPTION_DATABASE_REPLACED` | when the database opens again; `DATABASE_NOT_FOUND` if it has not 60 seconds after it closed |

The code is the database's state when the end is sent, not the operation's name: a quarantine followed at once by an unquarantine, or a
drop followed at once by a create, can end the subscription with `SUBSCRIPTION_DATABASE_REPLACED`, because the database is open again by
then. Handle all three codes at any point of a subscription's life.

- **Once per subscription, after the last snapshot page it was sent.** A subscription still receiving its snapshot gets the end instead
  of `snapshot_complete` — or right after it, when the replacement came while `snapshot_complete` was being sent; the snapshot it
  completed is the replaced engine's, so treat the two alike. One caught before it was registered gets the end instead of its snapshot.
  Nothing of the replaced engine follows it.
- **On `SUBSCRIPTION_DATABASE_REPLACED`, subscribe again with no `resume_from`**: a fresh snapshot of the new engine. Its versions may be
  lower than the ones you held — a version belongs to one engine's stream — so do not drop a snapshot or a change for a lower version.
  Both SDKs do this by themselves: [`@aouda/client`](../clients/typescript.md#when-the-database-is-replaced-bl-1818-next-train) and
  [`Aouda.Client`](../clients/dotnet.md#limits-refusals-and-reconnects-bl-1383-0110).
- **On `DATABASE_QUARANTINED` or `DATABASE_NOT_FOUND`** the database has no engine any more: whether and when it comes back is the
  operator's. Both SDKs end the subscription with the code.
- **A subscription opened after the replacement hears every change.** Up to 0.17.1 every subscription of a database whose engine was
  replaced — and every one opened on it afterwards — got its snapshot and then no change until the server restarted, and one open across
  the replacement stayed open and silent.
- **A resume names its stream** (**BL-1823, next train**). A `resume_from` with the `resume_stream` of an engine closed since — a
  replaced one, or one reopened by a server restart — is answered with a **fresh snapshot** of what the database holds now, under the new
  stream; it is never told "current" any more. Up to 0.17.1 a bare `resume_from` into such an engine was answered as current or as an
  empty replay, so what the client missed was lost and rows a restore removed were kept. Both SDKs keep and send the stream by themselves.
- **A subscription ends with its table** (**BL-1824, next train**). A `DROP TABLE`, a rename (the old name) and a materialized query's
  drop end every subscription of the name — the table's, a named query's on it, the result's — with `TABLE_NOT_FOUND`, once, after
  the last snapshot page; the connection stays open. A table made again under the name is another table: subscribe to it again. A
  materialized result's **publication** ends nothing. Up to 0.17.1 a subscription received the recreated table's rows (judged by the
  dropped table's policy), and a renamed table's subscription went silent. `TRUNCATE` does not end a subscription (BL-1066).

### Horizons and range deletes

(**Horizon, 0.5.0**) Some tables drop old rows without a row event per row: a **windowed materialized query's result**
(its window, see [Materialized Queries](materialized.md)) and a **table with retention** ([Retention](retention.md)). Each has a
**horizon** — an instant below which its rows are gone — and it only rises. And a `DELETE` before a time on a table **without**
retention deletes a whole range in one statement. A subscriber learns about all three from **notices**: messages that name a
column and a time, not rows.

**The snapshot carries its horizon.** When the subscribed table has a horizon, `snapshot_complete` gains `horizon` (ISO-8601 UTC,
seven fractional digits) and `horizon_column`. The horizon is read after the snapshot, so for a moment the snapshot can hold a row
below it; a `horizon` message then follows. Apply the snapshot's horizon to its rows as you would a notice — drop every row whose
column lies below it or is null. Both fields are omitted for any other table.

```json
{
  "type": "snapshot_complete",
  "id": "sub-candles",
  "version": 100040,
  "row_count": 2880,
  "stream": "7d0c3f5e9a2b4c61b8e0f1a2d3c4b5a6",
  "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213",
  "horizon": "2026-10-09T00:00:00.0000000Z",
  "horizon_column": "Minute"
}
```

**A windowed result's snapshot is its stored part** — the rows at or after its horizon. Nothing below the horizon is computed for a
subscription: no change event would ever maintain it (maintenance builds nothing below the horizon), and computing it was unbounded
at subscribe. A named-query subscription's `total_matches` counts the same stored part. An HTTP read of the result is still complete:
the part below the horizon is computed from the source there (`stats.windowCompletionRows`).

**`horizon` — the floor rose.** Sent once per published advance of the table's horizon: a windowed result's clock advance, a
retention table's clock advance, or a `DELETE` before a time on a table with retention (an early expiry).

```json
{ "type": "horizon", "id": "sub-candles", "column": "Minute", "horizon": "2026-10-09T00:01:00.0000000Z", "version": 100057 }
```

Drop every held row whose `column` is below `horizon` **or is null**, and keep no later row below it. No row event is sent for the
expired rows.

**`range_delete` — rows below a time were deleted.** Sent once for a `DELETE` whose whole predicate was `column lt X` (`before` is
`X`) or `column lte X` (`before` is the successor of `X` at the column's resolution — one tick for a `Timestamp`, one day for a
`Date`) on a table **without** retention.

```json
{ "type": "range_delete", "id": "sub-trades", "column": "Ts", "before": "2026-07-01T00:00:00.0000000Z", "version": 100060 }
```

Drop every held row whose `column` is below `before`. A row with a null time was **not** deleted — keep it. No horizon is installed:
rows that arrive after the notice are live whatever their time, so do not filter later rows by it. No per-row delete event is sent.

**Ordering and resume.** Both notices take a change-event sequence number (`version`) and are ordered in the table's change stream
like any `change`: a `range_delete` is emitted inside the statement's commit, so a row inserted after the statement — even with a time
below `before` — arrives after the notice. Both carry `token` when the server can encode one. Both are kept by the resume buffer and
replayed in order on `resume_from`; a resume that falls back to a fresh snapshot gets one that carries the current horizon.

**Who receives them.** Every subscriber of the table that is not denied it. A notice names no row, so the subscription's `filter`, a
named query's bound `where` and row-level security do not apply to it.

**Conflation.** A conflated subscription sends what it holds before it sends a notice, so a held change from before a range delete
never arrives after it.

**Embargo.** A subscription read through an embargoed statement (`embargoSeconds`, see
[Authorization](../auth/authorization.md#embargo)) holds each change until its row time is old enough, and its notices go through the
same hold. A held change the notice covers is never released after it: a held insert is dropped, and a held
change to a row you hold is dropped when the notice covers your copy too, or becomes a `delete` of your copy when the statement removed
the row. The notice's time is never inside the embargo window: when it is later than your cutoff — `now − embargoSeconds` plus one
tick at the send (for a `Date` column, the next day at midnight UTC) — it is sent with the cutoff instead. Every row you were given
lies below the cutoff, so you drop exactly the rows the statement's time would have dropped. A subscription whose embargo releases
nothing (a table with no row time) gets no notice. Up to 0.16.0 the notice was sent at once with the statement's time, and a held row
it covered could arrive after it — a row the server no longer had.

**Times.** The notices carry ISO strings; rows on the JSON wire carry a `Timestamp` as .NET ticks (an `Int64`, 100 ns since
0001-01-01 UTC) and a `Date` as its day number (days since the Unix epoch). Compare them as the same instant, at full precision — the
SDK helpers below do. So that a client can tell a day number from a time, a notice on a `Date` column carries
`"column_type": "date"` (and `snapshot_complete` `"horizon_column_type": "date"`); both are omitted for a `Timestamp`.

**Dropping rows in the client.** `Aouda.Client`: a `SubscriptionEvent` has `Type` `"horizon"` or `"range_delete"` (`IsHorizon`,
`IsRangeDelete`), `Horizon` (a snapshot's, or a `horizon` event's), `Before` (a `range_delete`'s), `Column` and `ColumnType`
(`"date"` on a `Date` column); `evt.Removes(row)` says whether a held row goes, reading a `Date` row's day number as days. The typed `SubscriptionEvent<T>` carries the same, with `Removes(row, r => r.Ts)`.

```csharp
await foreach (var evt in client.GetTable("trades").SubscribeAsync())
{
    if (evt.IsSnapshot)
        held = evt.Rows!.Where(row => !evt.Removes(row)).ToList();   // drop what lies below evt.Horizon, when the table has one
    else if (evt.IsHorizon || evt.IsRangeDelete)
        held.RemoveAll(row => evt.Removes(row));
    else
        Apply(held, evt);                         // insert / update / delete, as before
}
```

`@aouda/client`: the `subscribe` options take `onHorizon(event)` and `onRangeDelete(event)` (`SubscriptionHorizonEvent`,
`SubscriptionRangeDeleteEvent`); the async iterator yields the same events (`type: "horizon"` / `"range_delete"`), and its snapshot
event carries `horizon` and `horizonColumn` (and `horizonColumnType: "date"` on a `Date` column; the notices carry `columnType`).
`applyNotice(rows, event)` returns the rows a notice keeps; `noticeRemoves(row, event)` answers for one row. Apply it to the
snapshot too (`applyNotice(rows, snapshotEvent)` in the async iterator). In the callback style the fourth argument of `onSnapshot(rows, version, totalMatches, snapshot)` is that snapshot event, with `horizon`,
`horizonColumn` and `horizonColumnType` (**BL-1068, next train**; before it the callback received no horizon, and a callback-only client
dropped those rows at the next `horizon` message instead).

```typescript
import { applyNotice } from "@aouda/client";

let rows: Trade[] = [];
const sub = client.table<Trade>("trades").subscribe({
  onSnapshot: (snapshot, _version, _total, event) => { rows = applyNotice(snapshot, event); },
  onChange: (event) => { /* insert / update / delete, as before */ },
  onHorizon: (event) => { rows = applyNotice(rows, event); },
  onRangeDelete: (event) => { rows = applyNotice(rows, event); },
});
```

**An older client** ignores both messages (both SDKs drop a `type` they do not know), so its cache keeps rows the server no longer
returns until it subscribes again. There is no compatibility shim: upgrade the client with the server.

**`TRUNCATE` sends no notice** — and no row events — today. A client holding a truncated table's rows keeps them until it subscribes
again.

### Timestamp columns in a subscription (**IR quote report, 0.10.0**)

A `Timestamp` column arrives as a JSON **number**: .NET ticks since `0001-01-01T00:00:00Z`, UTC (`639298350326250000` is
`2026-11-09T15:30:32.625Z`). The `snapshot` names the column in `column_types` (`{"DateTime":"Timestamp"}`), and so does every
`change` that carries it (**BL-1866, next train**; up to 0.17.1 a change named its array columns only, and a client had to keep the
snapshot's names — which a resume with no snapshot, or a column made again in another type, read wrongly). Read each message by its own
`column_types`. `@aouda/client` hands a `Date`; elsewhere, Unix milliseconds are
`(ticks − 621355968000000000) / 10000`. A column declared `String` is text. Details: [Timestamp semantics](../reference/http-api.md#timestamp-semantics).

(**BL-1391, 0.11.0**) A `Date` column is a JSON number too, a count of days since the Unix epoch, and the `snapshot` now names it as `"Date"` in `column_types` (`{"day":"Date"}`), on every page, so a client can tell it from an `Int32`. The value on the wire is unchanged; a `change` names it too (**BL-1866, next train**). `Aouda.Client` reads it: a `Date` cell is a UTC `DateTime` at midnight (as a query result's is) in the snapshot, in a change's `Row` and `PreviousRow` and in a delete's `Key`, and a typed `DateOnly`, `DateOnly?` or `DateTime` property gets the day; a day count a `DateTime` cannot hold ends the subscription naming the column. `@aouda/client` hands a JavaScript `Date` at **00:00:00 UTC** of that day for it, in the snapshot and in every later change's `row` and `prev` (**breaking** for a caller that read the day number itself): read the calendar date with `getUTCFullYear()` / `getUTCMonth()` / `getUTCDate()` or `toISOString().slice(0, 10)`, never the local-time getters. A query result's `Date` column is unchanged, still the day number.

(**BL-1381, 0.11.0**) The C# SDK (`Aouda.Client`) hands a `DateTime` of kind `Utc`, 100 ns tick kept, in the snapshot and in every
change: `Row`, `PreviousRow` and a delete's `Key` (a `Timestamp` primary key) — also after a reconnect, a gap resume or a
`SLOW_CONSUMER` fresh subscribe, and on a named-query subscription. It remembers the names the latest snapshot gave; a fresh snapshot
replaces them. A typed subscription (`GetTable<T>().SubscribeAsync()`) fills a `DateTime`, `DateTime?` or `DateTimeOffset` property
(offset zero); a `long` property for a `Timestamp` column no longer reads. Until this train, `Aouda.Client` 0.10.0 typed the snapshot
only, and the first change delivered the raw tick number (an untyped `JsonElement`; a typed subscription threw). `@aouda/client` leaves a
delete's `key` as the server sent it (ticks).

### Array columns in a subscription (**BL-035, 0.9.0**)

(**BL-035, 0.9.0**) A table or named-query subscription delivers an [array column](array-columns.md) as an array, a `Byte[]` as base64
text (MessagePack and long-poll alike) and **tells the client which columns are arrays**: every `snapshot` and `change` message that holds an array
column carries `column_types`, a map from the column's name to its type (`{"Rates":"Double[]"}`). **A column named there holds an
array of that type; a column not named holds a scalar.** A message without an array column has no `column_types`, so a table
without arrays is unchanged. A subscription `filter` or a `conflate.key` on an array column is refused with an `error` message,
code `ARRAY_COLUMN_UNSUPPORTED`. The SDKs read `column_types` and give typed arrays (`Float64Array`, `double[]`, …). Details:
[Array columns — reading](array-columns.md#subscriptions-long-poll-and-materialized-queries).

## 2.8 How Aouda implements it

High-level runtime flow:

1. Each commit publishes **one change batch** to the change emitter (`EmitCommit`, its only entry point); the table's
   resume buffer keeps whole batches, and per-row `TableChangeEvent`s are built from a batch only when a listener or a
   resume reads them — the events a subscriber receives are unchanged (**ColumnarCore S09, 0.2.0**; the older
   per-event entry points are removed).
2. Subscription manager fans out events to per-subscription channels.
3. Subscription handler combines the user filter with the caller's row conditions and sends `snapshot`/`change`.
4. Write stream handler validates mode/sequence/security, writes rows, emits `stream_ack`.
5. Client transports maintain reconnect behavior and re-subscribe/re-open flows.

Key implementation anchors:

- Engine events and buffering:
  - `src/Aouda.Engine.Storage/Streaming/ChangeEventEmitter.cs`
- Server connection and routing:
  - `src/Aouda.Server/WebSocket/WebSocketHandler.cs`
  - `src/Aouda.Server/WebSocket/MessageRouter.cs`
  - `src/Aouda.Server/WebSocket/ConnectionSession.cs`
- Subscription path:
  - `src/Aouda.Server/WebSocket/StreamingSubscriptionManager.cs`
  - `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
  - `src/Aouda.Server/WebSocket/SubscriptionFilterEvaluator.cs`
- Write path:
  - `src/Aouda.Server/WebSocket/Handlers/WriteStreamHandler.cs`
  - `src/Aouda.Server/WebSocket/WriteStreamBackpressure.cs`
  - `src/Aouda.Server/WebSocket/StreamingWriteOptions.cs`
- Protocol:
  - `src/Aouda.Protocol/Streaming/Messages/ClientMessages.cs`
  - `src/Aouda.Protocol/Streaming/Messages/ServerMessages.cs`
  - `src/Aouda.Protocol/Streaming/MessageSerializer.cs`
- Fallback transport:
  - `src/Aouda.Server/Controllers/LongPollStreamController.cs`
  - `src/Aouda.Client/Internal/LongPollTransport.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Subscribe with snapshot then live changes

1. Client sends `subscribe` message with `id`, `target`, optional filter.
2. `SubscriptionHandler.HandleSubscribeAsync(...)` validates table/filter and registers subscription first (gap-safety ordering).
3. Handler captures current change sequence and executes the snapshot query with the caller's row conditions applied.
4. Server sends `snapshot` message.
5. Registration snapshot version is set; consumer unblocks and emits live `change` events with higher sequence only.

Primary anchors:

- `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
- `src/Aouda.Server/WebSocket/StreamingSubscriptionManager.cs`

Primary proving tests:

- `tests/Aouda.Server.Tests/WebSocket/SubscriptionHandlerIntegrationTests.cs`
- `tests/Aouda.Server.Tests/WebSocket/StreamingSubscriptionManagerTests.cs`

### Walk-through B: Resume from reconnect (`resume_from`)

1. Re-subscribe includes `resume_from` and `resume_stream` (the `stream` of the last `snapshot_complete`).
2. Handler re-reads the caller's statements if the permission version changed.
3. (**BL-1823, next train**) A `resume_stream` that is not the engine's stream now, or none, is a fresh subscribe: the snapshot below.
   So is a `resume_from` below the table's history floor — the stream's opening sequence, or where a drop of the name forgot its ring.
4. Handler compares resume version with current sequence:
   - at-current -> attach to live only,
   - replay available -> deliver buffer events and continue live,
   - replay expired -> send fresh snapshot fallback.
     A server keeps a table's changes for replay only once a subscription on that server has watched the table;
     writes before that are not retained, so a `resume_from` older than them is expired and gets the snapshot
     rather than an empty replay (**ColumnarCore S09, 0.2.0**); on an embedded engine the same holds until an
     `OnTableChange` handler (or `NoteExternalChangeListener`) listens to the table. A single write larger than the replay buffer's
     capacity is not retained either: a `resume_from` from before its end gets the snapshot (**BL-723, 0.2.0**).
5. Consumer continues with sequence gate to avoid duplicates across boundary — within one stream: a fresh snapshot of another stream
   has lower numbers, and is never dropped for them.

Primary anchors:

- `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
- `src/Aouda.Engine.Storage/Streaming/ChangeEventEmitter.cs`

Primary proving tests:

- Resume and reconnect behavior coverage in `tests/Aouda.Client.Tests/Streaming/SubscriptionApiTests.cs`
- Gap-safety coverage in `tests/Aouda.Server.Tests/WebSocket/SubscriptionHandlerIntegrationTests.cs`

### Walk-through C: Streaming write frame processing

1. Client opens stream (`stream_open`) with mode (`insert`/`upsert`).
2. `WriteStreamHandler.HandleOpenAsync(...)` validates stream ID and target table.
3. Each `stream_rows` frame is read as column arrays (**Lead S12, 0.6.0**; a frame with `rows` is refused `ROW_OBJECTS_UNSUPPORTED`) and enforces:
   - batch limits and payload limits,
   - sequence continuity,
   - backpressure decision (accept/reject/close),
   - the `write` statements' row conditions, on every row.
4. Accepted rows are inserted/upserted; server emits `stream_ack` with `through` and optional row errors.
5. `stream_close` closes and removes state, sending `stream_closed`.

Primary anchors:

- `src/Aouda.Server/WebSocket/Handlers/WriteStreamHandler.cs`
- `src/Aouda.Server/WebSocket/WriteStreamBackpressure.cs`

Primary proving tests:

- `tests/Aouda.Server.Tests/WebSocket/WriteStreamHandlerIntegrationTests.cs`
- `tests/Aouda.Client.Tests/Streaming/WriteStreamApiTests.cs`

### Walk-through D: Long-poll fallback connect/send/poll loop

1. Client fallback transport calls `POST /api/databases/{db}/stream/longpoll/connect`.
2. Server authenticates similarly to WebSocket handshake and creates long-poll session.
3. Client sends streaming messages to `/send`; server routes via same message router.
4. Client polls `/poll` to receive batched server messages or heartbeat.
5. On disconnect/expiry, session is removed and reconnect logic re-establishes transport.

Primary anchors:

- `src/Aouda.Server/Controllers/LongPollStreamController.cs`
- `src/Aouda.Client/Internal/LongPollTransport.cs`
- `../aouda-client-ts/src/streaming/longpoll-transport.ts`

Primary proving tests:

- `tests/Aouda.Client.Tests/Streaming/StreamingFallbackLifecycleTests.cs`
- `../aouda-client-ts/tests/streaming/longpoll-transport.test.ts`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Is live data push a first-class query/write path? | Often separate event bus or polling add-on | Built-in bidirectional streaming protocol tied to table operations | Fewer moving parts for app-level real-time behavior |
| How does reconnect continuity work? | Often opaque reconnect, app-level patching required | Versioned events + `resume_from` + buffer replay/fallback snapshot | Predictable client recovery model |
| Is multi-transport support built in? | Usually WebSocket only or external gateway needed | WebSocket primary with built-in long-poll fallback and MessagePack mode | More deployment compatibility with constrained networks |
| Are client SDKs symmetric for streaming primitives? | Often one SDK gets full support first | .NET and TypeScript both expose subscribe + write stream with reconnect support | Easier multi-platform app parity |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:WebSocket:EnableCompression` | bool | `true` | `true/false` | server config | Enables compressed WS accept context |
| `Aouda:WebSocket:EnableMessagePack` | bool | `true` | `true/false` | server config | If `false`, `wire_mode=msgpack` auth is rejected |
| `Aouda:WebSocket:MaxConnections` | int | `10000` | `>=1` | server config | Global connection cap (`CONNECTION_LIMIT_EXCEEDED`, a plain `error` frame before authentication; long-poll `connect` 429) |
| `Aouda:WebSocket:MaxConnectionsPerIdentity` (**BL-1383, 0.11.0**) | int | `16` | `>=1` | server config | Live connections (WebSocket and long-poll) per identity; enforced in the handshake, after identity resolution and before `auth_ok`, as an `auth_error` with `IDENTITY_CONNECTION_LIMIT_EXCEEDED` (long-poll `connect`: 429, same code). A public-key identity includes the remote address; a no-auth database has no limit |
| `Aouda:WebSocket:SubscribeRate:Burst` / `RefillPerSecond` (**BL-1383, 0.11.0**) | int / number | `512` / `32` | `>=1` / `>=0` | server config | Per-identity token bucket on subscribe attempts (one refused for another reason still costs a token); both listeners and long-poll `/send`; independent of `IdentityQuota:Enabled`. Over it: `SUBSCRIBE_RATE_EXCEEDED` with `retry_after_ms` |
| `Aouda:WebSocket:IdleTimeout` | timespan | `00:05:00` | positive | server config | Idle close threshold |
| `Aouda:WebSocket:LongPollWaitTimeout` | timespan | `00:00:25` | positive | server config | Max long-poll block |
| `Aouda:WebSocket:LongPollSessionIdleTimeout` | timespan | `00:02:00` | positive | server config | Session expiry threshold |
| `Aouda:WebSocket:LongPollMaxQueuedMessages` | int | `1000` | `>=1` | server config | Queue size per long-poll session |
| `Aouda:WebSocket:LongPollMaxBatchSize` | int | `128` | `>=1` | server config | Max messages per poll response |
| `Aouda:WebSocket:StreamingWrites:SoftPendingRows` | int | `5000` | positive | server config | Soft row backpressure threshold |
| `Aouda:WebSocket:StreamingWrites:ResumePendingRows` | int | `2500` | positive | server config | Unpause row threshold |
| `Aouda:WebSocket:StreamingWrites:HardPendingRows` | int | `10000` | positive | server config | Hard stream close threshold |
| `Aouda:WebSocket:StreamingWrites:SoftPendingBytes` | int | `4194304` | positive | server config | Soft byte backpressure threshold |
| `Aouda:WebSocket:StreamingWrites:ResumePendingBytes` | int | `2097152` | positive | server config | Unpause byte threshold |
| `Aouda:WebSocket:StreamingWrites:HardPendingBytes` | int | `8388608` | positive | server config | Hard byte close threshold |
| `Aouda:WebSocket:StreamingWrites:MaxBatchRows` | int | `1000` | positive | server config | Max rows per `stream_rows` |
| `Aouda:WebSocket:StreamingWrites:MaxBatchBytes` | int | `1048576` | positive | server config | Max payload bytes per `stream_rows` |
| `Aouda:WebSocket:StreamingWrites:AckInterval` | timespan | `00:00:00.500` | positive | server config | Ack interval |
| `.NET WebSocketTransportOptions.WireMode` | enum | `Json` | `Json`,`MessagePack` | client options | Preferred mode in auth handshake |
| `.NET WebSocketTransportOptions.EnableCompression` | bool | `true` | `true/false` | client options | Client compression request behavior |
| `.NET WebSocketTransportOptions.EnableLongPollFallback` | bool | `true` | `true/false` | client options | Fallback enabled |
| `.NET WebSocketTransportOptions.ReconnectBaseDelay` | timespan | `1s` | positive | client options | Reconnect backoff base |
| `.NET WebSocketTransportOptions.ReconnectMaxDelay` | timespan | `30s` | positive | client options | Reconnect delay cap |
| `.NET WebSocketTransportOptions.ReconnectMaxAttempts` | int | `0` | `0` or positive | client options | `0` means unlimited |
| `.NET WebSocketTransportOptions.KeepAliveInterval` | timespan | `30s` | positive | client options | Client WS keepalive |
| `.NET WebSocketTransportOptions.ReceiveBufferSize` | int | `65536` | positive | client options | Receive buffer |
| `.NET WebSocketTransportOptions.LongPollWaitTimeout` | timespan | `25s` | positive | client options | Long-poll wait in fallback |
| `TS streaming.wsFactory` | function | platform `WebSocket` | `(url) => WebSocket` | `AoudaClientOptions.streaming` | Makes the socket (**NativeClients, 0.4.0**; `enableCompression` removed) |
| `TS streaming.wireMode` | string | `"json"` | `"json"`, `"msgpack"` | `AoudaClientOptions.streaming` | WS wire mode |
| `TS streaming.enableLongPollFallback` | bool | `true` | `true/false` | `AoudaClientOptions.streaming` | Enables fallback wrapper |
| `TS streaming.longPollWaitMs` | number | `25000` | positive | `AoudaClientOptions.streaming` | TS long-poll wait |

Configuration precedence and operational notes:

- Server:
  - Bound from `Aouda:WebSocket` and `Aouda:WebSocket:StreamingWrites` config sections.
  - Treated as startup configuration for server processes.
- Client:
  - .NET options set via `AoudaClientOptions.WebSocketTransportOptions`.
  - TypeScript options set via `AoudaClientOptions.streaming`.
- Dynamic vs restart-required:
  - Server config is effectively restart-required.
  - Per-subscription user filter and resume values are dynamic request-level values.
- Safety-gated:
  - Unsupported wire modes are rejected at auth handshake.
  - Batch size/bytes and sequence continuity are validated per frame.
- Deprecated/reserved:
  - None flagged as deprecated in current code for streaming options.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example

```csharp
using Aouda.Client;
using Aouda.Abstractions.Streaming;

await using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5000",
    DatabaseName = "appdb",
    WebSocketTransportOptions = new WebSocketTransportOptions
    {
        WireMode = Aouda.Protocol.Streaming.WireMode.Json
    }
});

await foreach (var evt in client.GetTable("orders").SubscribeAsync())
{
    if (evt.IsSnapshot)
        Console.WriteLine($"snapshot version={evt.Version} rows={evt.Rows.Count}");
    else
        Console.WriteLine($"{evt.Type} version={evt.Version}");
    break;
}

await using var ws = await client.GetTable("orders")
    .OpenWriteStreamAsync(WriteMode.Upsert);
await ws.WriteAsync(new Dictionary<string, object?> { ["id"] = 1, ["status"] = "open" });
await ws.CloseAsync();
```

Expected result: snapshot event is delivered, then write stream accepts rows and acknowledges progression.

Common mistake: calling streaming APIs from embedded tables; embedded streaming intentionally throws not-supported.

### TypeScript example

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
  streaming: {
    wireMode: "json",
    enableLongPollFallback: true,
  },
});

const sub = client.table("orders").subscribe({
  onSnapshot: (rows, version) => console.log("snapshot", version, rows.length),
  onChange: (evt) => console.log(evt.type, evt.version),
  onError: (err) => console.error(err),
});

const stream = await client.table("orders").openWriteStream({ mode: "upsert" });
await stream.write({ id: 1, status: "open" });
await stream.close();
await sub.unsubscribe();
```

Expected result: callback receives snapshot and subsequent changes; write stream returns ack progression via `lastAcknowledgedSeq`, and
`close()` resolves once every frame is acknowledged.

Common mistake: expecting exactly-once semantics and not deduping by version after reconnect.

### HTTP/protocol examples

```http
GET /api/databases/appdb/ws
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <key>
```

**Step 1 — authenticate (client → server):**

```json
{"type":"auth","token":"<key-or-session-token>","database":"appdb","wire_mode":"json"}
```

**Step 1 response — `auth_ok` (server → client on success):**

```json
{"type":"auth_ok","user_id":"user-123","expires_at":"2026-06-01T00:00:00Z","wire_mode":"json"}
```

Fields: `user_id` (null for a key), `expires_at` (null when no expiry), `wire_mode` (the negotiated wire mode).

**Which credentials the socket accepts** (**BL-1464, 0.16.0**). The ones an HTTP request to that database accepts: a key or a session of
a principal of the auth database that governs the database, or of `_serverauth`. A credential resolves by itself to one principal (a key by
its id, a session by its issuer); a valid credential of another auth database is refused `AUTH_WRONG_AUTH_DATABASE`. A socket and a
long-poll connect need a credential on both listeners: an empty `token` is refused `AUTH_CREDENTIAL_MISSING`, so `anonymous` runs named
queries over HTTP and does not subscribe. `re_auth`, sign-out and revocation reach the open
socket ([Revocation](../auth/credentials.md#revocation)). The handshake proves who; what the session may do is asked at each `subscribe` and
`stream_open`, from the principal's statements, so a socket opens for a principal that may read nothing.

**Step 1 response — `auth_error` (server → client on failure):**

```json
{"type":"auth_error","code":"AUTH_CREDENTIAL_INVALID","message":"..."}
```

**Step 2 — subscribe (client → server):**

```json
{"type":"subscribe","id":"sub-orders","target":"orders","resume_from":123,"resume_stream":"7d0c3f5e9a2b4c61b8e0f1a2d3c4b5a6"}
```

`resume_from` is optional. Omit it on a fresh subscription; include the last seen version on reconnect, with `resume_stream`, the
`stream` of the last `snapshot_complete` (**BL-1823, next train**). Without `resume_stream`, or with another stream's, the server answers
a fresh snapshot.

**`cross_partition_access`** (optional boolean, sent only when `true`) (**BL-1227, 0.9.0**) waives the partition-filter guard
for a subscription that names no partition: a table `subscribe`, or a named-query `subscribe` (`name`, `args`) whose query binds no
partition key, on a partitioned table that requires a partition filter. Without it that subscribe is refused
`PARTITION_FILTER_REQUIRED`. It is a **cost waiver, not a grant**: the snapshot and every later event are still what the
caller's `read` statements admit: one whose `where` names the partition column receives only the partitions it admits, and a caller with
no `read` statement on the table is refused as before.
The data-plane listener (the browser tier) ignores the flag, so a browser still binds the partition key in a named query. An
older server ignores the field and answers `PARTITION_FILTER_REQUIRED`.

```json
{"type":"subscribe","id":"sub-orders","target":"orders","cross_partition_access":true}
```

**A subscription that spans partitions.** A subscription with no partition filter would read every partition of the table, so a
partitioned table's guard refuses it unless the flag is set; a caller whose `read` statement has no `where` then receives the events of
**every** partition, including partitions created after it subscribed, while one whose `where` names the partition column receives
only those it admits. The rule, and the choice between a per-partition filter, a named query
and the flag, are in
[A subscription that spans partitions](partitioning.md#a-subscription-that-spans-partitions).

**Step 2 response — `snapshot` then `change` (server → client):**

```json
{"type":"snapshot","id":"sub-orders","columns":["id","status"],"data":[[1],["open"]],"version":456}
```

(**Lead S12, 0.6.0; breaking**) A `snapshot` page is column arrays — `columns`, and `data` with one array per column — as a
query result is; it was `"rows": [{…}]`. A `change` still carries one row, as an object.

```json
{"type":"change","id":"sub-orders","op":"insert","row":{"id":2,"status":"pending"},"prev":null,"key":null,"version":457}
```

`op` values: `"insert"`, `"update"`, `"delete"`. For `update`, `prev` carries the previous row state. For `delete`, `key` carries the primary-key payload and `row` is null.

**Unsubscribe (client → server) and confirmation (server → client):**

```json
{"type":"unsubscribe","id":"sub-orders"}
```

```json
{"type":"unsubscribed","id":"sub-orders"}
```

**Write stream lifecycle:**

```json
{"type":"stream_open","id":"stream-1","table":"orders","mode":"upsert"}
```

Server acknowledges with `stream_ready` before the client may send rows:

```json
{"type":"stream_ready","id":"stream-1"}
```

```json
{"type":"stream_rows","id":"stream-1","seq":1,"columns":["id","status"],"data":[[1],["open"]]}
```

(**Lead S12, 0.6.0; breaking**) A `stream_rows` batch is column arrays (`columns`, `data`, and `absent` for a cell that is not
given), the same body as an HTTP insert; it was `"rows": [{…}]`, which is now answered with an `error` coded
`ROW_OBJECTS_UNSUPPORTED`. See the [HTTP reference](../reference/http-api.md#column-arrays-the-write-body).

```json
{"type":"stream_ack","id":"stream-1","through":1,"errors":null}
```

`through` is the highest sequence number durably acknowledged. `errors` is null or a list of `{index, code, message}` objects for per-row rejections.

```json
{"type":"stream_close","id":"stream-1"}
```

```json
{"type":"stream_closed","id":"stream-1"}
```

**Heartbeat (server → client, periodic):**

```json
{"type":"heartbeat","version":460}
```

`version` carries the current global change sequence. Clients can use this to detect lag.

**Ping / pong (client liveness check):**

```json
{"type":"ping"}
```

```json
{"type":"pong"}
```

**Long-poll connect:**

```http
POST /api/databases/appdb/stream/longpoll/connect
Content-Type: application/json

{"token":"<key-or-session-token>","wireMode":"json"}
```

There is one credential and no second token: a body that carries the old second-token member is `400 INVALID_REQUEST`. To act as a user, send that user's
session, or a [limited key](../auth/credentials.md#limited-keys) minted from it. A refused credential answers `401` with `{ "code", "message" }` (`AUTH_KEY_MALFORMED`,
`AUTH_CREDENTIAL_INVALID`, `AUTH_CREDENTIAL_EXPIRED`, `AUTH_CREDENTIAL_REVOKED`); `500` with `AUTH_DB_UNAVAILABLE` means the auth database could not be read or the
session's permissions could not be resolved — no session is created, and it is **retryable** (**BL-1223, 0.9.0**).

Expected result: `auth_ok` is returned for valid auth, then `snapshot`/`change` messages flow over the chosen transport.

Common mistake: sending `wireMode: "msgpack"` on long-poll; long-poll supports JSON mode only.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Subscribe to table changes | `ITableOperations.SubscribeAsync()` | `TableQuery.subscribe()` | `subscribe` message over WS/long-poll | Implemented | Snapshot then incremental |
| Typed subscriptions | `ITableOperations<T>.SubscribeAsync()` | Generic `TableQuery<T>.subscribe()` typing | Same protocol payload, typed client mapping only | Implemented | Type mapping is client-side |
| Resume from version | Automatic in subscription implementation | Automatic re-subscribe with `resume_from` | `resume_from` field in subscribe message | Implemented | At-least-once replay semantics |
| Subscribe across partitions (waive `PARTITION_FILTER_REQUIRED`) | `WithCrossPartitionAccess()` or `SubscribeOptions.CrossPartitionAccess` | `withCrossPartitionAccess()` or `SubscribeOptions.crossPartitionAccess`; named queries: `NamedQuerySubscribeOptions.crossPartitionAccess` | `cross_partition_access` field in subscribe message | Implemented (**BL-1227, 0.9.0**) | A cost waiver, not a grant; ignored on the data-plane listener |
| Open write stream | `OpenWriteStreamAsync(mode)` | `openWriteStream({ mode })` | `stream_open`, `stream_rows`, `stream_ack`, `stream_close` | Implemented | Insert/upsert supported |
| MessagePack wire mode | `.NET WireMode.MessagePack` | `streaming.wireMode = "msgpack"` | auth `wire_mode` negotiation | Implemented | Long-poll is JSON-only |
| Long-poll fallback | `.NET EnableLongPollFallback` | `streaming.enableLongPollFallback` | `/stream/longpoll/connect|send|poll|{id}` | Implemented | Fallback used when WS connect fails |
| Embedded streaming support | Not supported (throws) | n/a | n/a | Partial | Server mode only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Exactly-once stream processing contract | No exactly-once mode in server/protocol/SDKs | Use version-based dedup and idempotent reducers | Future architecture decision; not in current P10 scope | Medium |
| Cross-database subscriptions on single connection | No cross-db subscription targeting in protocol path | Open separate client/connection per database | Future clustering/distribution roadmap work | Medium |
| Distinct MQ "not ready" error code | No dedicated protocol error; currently generic not-found style | Treat missing/not-ready uniformly and retry after MQ setup | BL-053 from S10 report context | Low/Medium |
| TS equivalent of C# `Live()` hot collection abstraction | Withdrawn with C# `Live()` (BL-162) | Use `subscribe()` and local reducer state in app layer | BL-164 named-query materialization | — |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First production subscription rollout

When to use:
- You are enabling real-time reads for an existing table-first application.

Steps:
1. Keep default WebSocket/server streaming config.
2. Add one table subscription in .NET or TS and log snapshot version plus change versions.
3. Perform known inserts/updates/deletes through normal APIs.
4. Verify events and version progression.

Expected result checks:
- First event is snapshot.
- Changes arrive in version order after snapshot.
- No auth bypass occurs for unauthorized principals.

### Scenario 2: Reconnect and resume validation

When to use:
- You need confidence that reconnects do not silently lose events.

Steps:
1. Start a subscription and record last seen version.
2. Force transport drop (network interruption or test harness socket abort).
3. Continue writes while disconnected.
4. Let client reconnect and observe resume behavior.

Expected result checks:
- Reconnect path uses `resume_from` with `resume_stream`.
- Either missed buffered changes replay or fresh snapshot fallback occurs; after a server restart it is always the snapshot (a new
  stream, **BL-1823, next train**).
- Client reducer remains consistent via version-based dedup.

### Scenario 3: WebSocket-restricted environment fallback

When to use:
- Corporate proxy/network blocks WebSocket upgrade.

Steps:
1. Keep client `EnableLongPollFallback` / `enableLongPollFallback` enabled.
2. Block or fail WebSocket connection path.
3. Re-run subscription and write-stream operations.
4. Observe long-poll connect/send/poll traffic.

Expected result checks:
- Streaming functions continue over long-poll.
- Snapshot/change and write ack semantics remain consistent.
- Long-poll session expiry and reconnect behavior are observable and recoverable.

## 2.13 Operations and observability

Monitor first:

- Protocol/session health:
  - connection count vs `MaxConnections`,
  - auth error rates (`AUTH_*` codes),
  - stream error codes (`INVALID_STREAM_SEQUENCE`, `STREAM_PAUSED`, `STREAM_BACKPRESSURE_LIMIT_EXCEEDED`).
- Subscription/write throughput and pressure:
  - `Perf.SubscriptionUpdatesEnqueued`,
  - `Perf.SubscriptionUpdatesProcessed`,
  - `Perf.SubscriptionDroppedUpdates`,
  - `Perf.SubscriptionQueueDepth`,
  - `Perf.SubscriptionLagMs`.
- Storage impact signals during streaming traffic:
  - query rows scanned/returned and page-cache hit/miss metrics in server metrics endpoints.

Recovery/restart expectations:

- Active WS/long-poll sessions are runtime state and are not persisted across restart.
- Clients should reconnect and re-subscribe after restart.
- A `resume_from` after a restart can be answered as current or as an empty replay — changes made while the client was away are not
  delivered (**BL-1823**, open; [When the database is replaced](#when-the-database-is-replaced-bl-1818-next-train)). Subscribe fresh after
  a restart.
- A restore, a quarantine, a drop or a replica's checkpoint ends each subscription of the database by name, on the open connection
  (**BL-1818, next train**): `SUBSCRIPTION_DATABASE_REPLACED` (subscribe again, fresh), `DATABASE_QUARANTINED` or `DATABASE_NOT_FOUND`.

Suggested tuning sequence:

1. Keep defaults and measure baseline event throughput, lag, and error codes.
2. Tune write-stream backpressure thresholds only when sustained `STREAM_PAUSED` or hard-limit closures occur.
3. Adjust transport mode/compression settings for network constraints (including long-poll fallback).

| Question | Practical answer |
|---|---|
| Which metric best indicates subscriber pressure? | `Perf.SubscriptionQueueDepth` and `Perf.SubscriptionDroppedUpdates` |
| How do I confirm stream continuity after reconnect? | Compare version progression and observe `resume_from` behavior in client logs/tests |
| Which fallback keeps streaming alive when WS is blocked? | HTTP long-poll fallback (`/stream/longpoll/...`) |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| First subscription message gets `AUTH_REQUIRED`/`AUTH_TIMEOUT` | Auth-required DB without valid first `auth` message | Send valid `auth` message as first frame with matching database |
| `AUTH_DATABASE_MISMATCH` on auth | Auth payload database does not match route DB | Align `auth.database` with `/api/databases/{db}/ws` |
| Duplicate-looking changes after reconnect | At-least-once replay path | Deduplicate by event version in client reducer |
| Resume returns fresh snapshot | Buffer replay expired for requested version | Accept snapshot fallback or increase practical reconnect cadence |
| `SUBSCRIPTION_DATABASE_REPLACED` (**BL-1818, next train**) | The database was restored, unquarantined, dropped and created, or replaced by a replica's checkpoint | Subscribe again with no `resume_from`; the SDKs do it. See [When the database is replaced](#when-the-database-is-replaced-bl-1818-next-train) |
| `INVALID_STREAM_SEQUENCE` during writes | Client sequence gap/out-of-order `stream_rows` frames | Ensure contiguous per-stream sequence numbers |
| Stream closes with backpressure limit code | Pending rows/bytes exceeded hard limit | Reduce batch rate/size; tune streaming write thresholds |
| Long-poll connect rejects `msgpack` | Long-poll supports JSON mode only | Use `wireMode: "json"` for long-poll |

## 2.15 Verification ledger

Last verification context date (UTC): `2026-03-31` (from P10 session reports and associated test commands).

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Protocol streaming serializer (I3) | `dotnet test tests/Aouda.Protocol.Tests --verbosity minimal --filter "FullyQualifiedName~MessageSerializerTests"` | Pass (`28/28`) | 2026-03-31 | Includes JSON + MessagePack paths |
| Server WS handler integration (I3) | `dotnet test tests/Aouda.Server.Tests --verbosity minimal --filter "FullyQualifiedName~WebSocketHandlerIntegrationTests"` | Pass (`19/19`) | 2026-03-31 | Auth handshake + wire mode negotiation paths |
| .NET WS transport integration (I3) | `dotnet test tests/Aouda.Client.Tests --verbosity minimal --filter "FullyQualifiedName~WebSocketTransportTests"` | Pass (`13/13`) | 2026-03-31 | Reconnect and message handling |
| .NET fallback lifecycle (I4) | `dotnet test tests/Aouda.Client.Tests --verbosity minimal --filter "FullyQualifiedName~SubscriptionApiTests|FullyQualifiedName~WriteStreamApiTests|FullyQualifiedName~WebSocketTransportTests|FullyQualifiedName~StreamingFallbackLifecycleTests"` | Pass | 2026-03-31 | Fallback and lifecycle coverage |
| TypeScript streaming transport/tests (I3/I4) | `npm run test -- tests/streaming/fallback-streaming-transport.test.ts tests/streaming/longpoll-transport.test.ts tests/streaming/websocket-transport.test.ts` | Pass | 2026-03-31 | Covers WS + fallback transports |
| TypeScript streaming API/tests (S13) | `npm run test -- tests/streaming/subscription.test.ts tests/streaming/write-stream.test.ts` | Pass (`10/10`) | 2026-03-31 | Subscribe + write stream APIs |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Subscription snapshot/change lifecycle | `SubscriptionHandlerIntegrationTests.cs` | Pass | Strong | Includes empty/populated snapshot and CRUD change flow |
| Server-side user filter behavior | `SubscriptionFilterEvaluatorTests.cs` + subscription integration tests | Pass | Strong | Includes normalization and update enter/leave scope behavior |
| Write-stream lifecycle + backpressure | `WriteStreamHandlerIntegrationTests.cs` | Pass | Strong | Mode validation, sequence, ack, pressure, row-level errors |
| .NET streaming API behavior | `SubscriptionApiTests.cs`, `WriteStreamApiTests.cs` | Pass | Strong | Reconnect, resume, typed mapping, close/dispose behavior |
| Materialized query streaming | `MaterializedQuerySubscriptionApiTests.cs` | Pass | Medium/Strong | Subscribing to MQ result tables and change propagation |
| .NET fallback lifecycle | `StreamingFallbackLifecycleTests.cs` | Pass | Medium/Strong | Long-poll lifecycle and reconnect scenarios |
| TypeScript streaming transport and API | `websocket-transport.test.ts`, `subscription.test.ts`, `write-stream.test.ts`, `longpoll-transport.test.ts` | Pass | Strong | Callback/iterator/write/fallback/wire-mode coverage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| Resume path dedicated server integration suite is less explicit than core subscribe suite | Resume correctness is critical under production reconnect churn | Add focused server integration tests for at-current/replay/expired resume triad with concurrent writes | High |
| Long-duration pressure soak for write streams not explicit in current suite | Sustained throughput can reveal backpressure oscillation bugs | Add deterministic soak test with threshold tuning and expected ack/close behavior assertions | Medium |
| Cross-SDK parity assertions for messagepack plus fallback combinations | Prevents subtle behavior divergence between .NET and TS | Add contract parity matrix tests shared via protocol fixture payload sets | Medium |

## 2.18 Known gaps and undone work

**Closed in P37 (do not treat as current):** silent `DropOldest` without a wire signal; subscription snapshots silently capped at `DefaultLimit` (1 000) with no truncation flag; client-side gap inference from a per-database sequence (impossible — the server now emits `gap`). Durable subscriber cursors beyond the 60 s / 10 000-event buffer remain ADR 0027 / P25.

- Cross-database subscriptions are not a shipped streaming feature.
  - User impact: multi-database consumers must maintain separate subscriptions/connections per database.
- Exactly-once semantics are not provided.
  - User impact: applications must implement version-based dedup/idempotent state transitions.
- Distinct materialized-query "not ready" error code is not yet surfaced as a dedicated protocol contract.
  - User impact: client error handling for MQ-not-ready vs not-found remains coarse.
- Long-poll fallback still uses a bounded outbox; WebSocket overflow is `gap` then unregister (or `SLOW_CONSUMER` on the send-path HWM).
- A `TRUNCATE` sends subscribers nothing — no notice and no row events (pre-existing; the horizon notices do not cover it).
  - User impact: a client cache keeps a truncated table's rows until it subscribes again.

## 2.19 References

- ADRs:
  - `docs/decisions/0020-real-time-streaming.md`
  - `docs/decisions/0023-authentication-and-authorization.md`
- Tasks/reports:
  - `docs/tasks/P10/P10-RealTimeStreaming-Tasks.md`
  - `docs/tasks/P10/P10-S1-ChangeEventFoundation.md`
  - `docs/tasks/P10/P10-S3-WebSocketInfrastructure.md`
  - `docs/tasks/P10/P10-S4-ADRAFilteredSubscriptions.md`
  - `docs/tasks/P10/P10-S5-ServerSideSubscriptionFilters.md`
  - `docs/tasks/P10/P10-S7-StreamingWrites.md`
  - `docs/tasks/P10/P10-S9-CSharpClientStreamingAPI.md`
  - `docs/tasks/P10/P10-S10-MaterializedQuerySubscriptions.md`
  - `docs/tasks/P10/P10-S11-HotCacheAndLiveCollection.md`
  - `docs/tasks/P10/P10-S12-TypeScriptWebSocketTransport.md`
  - `docs/tasks/P10/P10-S13-TypeScriptClientStreamingAPI.md`
  - `docs/tasks/P10/P10-S14-I3-MessagePackWireMode.md`
  - `docs/tasks/P10/P10-S14-I4-HttpLongPollFallback.md`
- Backlog:
  - `docs/BACKLOG.md` (BL-053 in P10 S10 report context)
- Key code paths:
  - `src/Aouda.Server/WebSocket/WebSocketHandler.cs`
  - `src/Aouda.Server/WebSocket/MessageRouter.cs`
  - `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
  - `src/Aouda.Server/WebSocket/Handlers/WriteStreamHandler.cs`
  - `src/Aouda.Server/Controllers/LongPollStreamController.cs`
  - `src/Aouda.Client/AoudaClient.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `src/Aouda.Client/Internal/WebSocketTransport.cs`
  - `src/Aouda.Client/Internal/LongPollTransport.cs`
  - `src/Aouda.Protocol/Streaming/MessageSerializer.cs`
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/streaming/websocket-transport.ts`
  - `../aouda-client-ts/src/streaming/longpoll-transport.ts`
- Related docs:
  - `docs/dev/Functionality-Overview.md`
  - `docs/dev/Functionality-HotCold-And-Memory.md`

## 2.20 What is missing from this document? (meta completeness)

- This document is phase-audit and code-path grounded, but does not include exhaustive per-message JSON and MessagePack schema examples for every protocol message type.
- Verification ledger entries are sourced from P10 report command evidence; this rewrite did not re-run all suites in this session.
- If new streaming transports or public streaming admin endpoints are added, sections `2.10`, `2.11`, and `2.18` must be updated immediately to preserve implementation honesty.

