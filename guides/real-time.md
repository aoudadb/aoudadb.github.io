---
title: "Real-time Streaming"
nav_order: 7
parent: "Guides"
---

# Aouda Functionality: Real-Time Streaming

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-03-31

Coverage phases: P10 (with integration dependencies on P12/P14 auth and ADRA behavior)
Primary task folders: `docs/tasks/P10/`
Primary ADRs: `docs/decisions/0020-real-time-streaming.md`, `docs/decisions/0023-authentication-and-authorization.md`, `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How do I use streaming now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`

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
  - `tests/Aouda.Client.Tests/HotCache/HotCacheTests.cs`
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
| Server `Aouda:WebSocket:HeartbeatInterval` | `20s` | Server heartbeat cadence |
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
| TypeScript `streaming.enableCompression` | `true` | Enables compression option on Node transport path |
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
  - ADRA-aware event filtering (PLS/RLS) and permission refresh on resume paths.
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
- C# hot cache/live:
  - Hot cache settings, WebSocket sync, and `Live()` collection pattern.

### Planned / proposed

Documented intent that is not currently fully productized:

- Cross-database subscription surfaces.
- Exactly-once delivery model and consumer-group semantics.
- Broker-style stream partition management semantics.
- Full auth-db integration test infrastructure for all PLS/RLS streaming combinations is still maturing (unit coverage exists; some full integration scenarios remain deferred in P10 report backlog notes).

### Reserved / not yet wired

- Dedicated error code for "materialized query exists but not yet ready" is not wired as a separate protocol code path (tracked as BL-053 in task report context).
- Legacy SSE hot-segment endpoint remains present (`SubscriptionController`), but it is not the P10 real-time streaming contract and should be considered legacy/parallel functionality rather than the primary streaming surface.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P10 S1-S5 | `P10-S1-ChangeEventFoundation.md`, `P10-S3-WebSocketInfrastructure.md`, `P10-S4-ADRAFilteredSubscriptions.md`, `P10-S5-ServerSideSubscriptionFilters.md` | Change emitter foundation, WS infra, subscription manager, ADRA filters, user filters, snapshot-first streaming | Full auth-db integration harness breadth still partial in integration form | Deferred auth-db integration scenarios noted in S4 report |
| P10 S7 | `P10-S7-StreamingWrites.md` | Write stream open/rows/close, insert/upsert, acks, backpressure thresholds, per-row auth rejections | None explicitly listed in S7 report | None |
| P10 S9-S13 | `P10-S9-CSharpClientStreamingAPI.md`, `P10-S10-MaterializedQuerySubscriptions.md`, `P10-S11-HotCacheAndLiveCollection.md`, `P10-S12-TypeScriptWebSocketTransport.md`, `P10-S13-TypeScriptClientStreamingAPI.md` | .NET and TypeScript streaming APIs, typed subscribe, write streams, MQ subscription behavior, hot cache + Live() | No major functional deferment documented here | BL-053 introduced from S10 context |
| P10 S14 I3/I4 | `P10-S14-I3-MessagePackWireMode.md`, `P10-S14-I4-HttpLongPollFallback.md` | MessagePack negotiation + binary mode; long-poll fallback endpoint and client fallback transport | None called out in I3/I4 reports | None |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| WebSocket endpoint + auth handshake | Yes | No | No | `WebSocketHandler.cs`, S3 report, server WS integration tests | Supports JWT/API key/no-auth DB paths |
| Snapshot + incremental table subscriptions | Yes | No | No | `SubscriptionHandler.cs`, S4 report/tests | Snapshot-first ordering with version |
| Server-side user filters | Yes | No | No | `SubscriptionFilterEvaluator.cs`, S5 report/tests | Filter normalized against table schema |
| ADRA PLS/RLS filtering on streamed events | Yes | No | No | `StreamingSubscriptionManager` + S4 tests | Includes update old/new row semantics |
| Resume from version (`resume_from`) | Yes | Yes | No | `SubscriptionHandler.cs` resume paths | Implemented in code; dedicated S6 task report template remains unfilled but behavior is present |
| Streaming writes (`insert`/`upsert`) | Yes | No | No | `WriteStreamHandler.cs`, S7 report/tests | Includes per-row rejection reporting |
| Write-stream backpressure and ack cadence | Yes | No | No | `StreamingWriteOptions.cs`, `WriteStreamBackpressure.cs` | Soft reject/hard close thresholds |
| .NET streaming API surface | Yes | No | No | `ITableOperations` + client streaming classes + S9 tests | Embedded mode intentionally throws not-supported |
| TypeScript streaming API surface | Yes | No | No | `query-builder.ts`, streaming modules, S12/S13 tests | Callback + async iteration + write stream |
| MessagePack streaming wire mode | Yes | No | No | `WireMode.cs`, serializer, WS transports, I3 tests | Long-poll remains JSON-only |
| HTTP long-poll fallback transport | Yes | No | No | `LongPollStreamController.cs`, client transports, I4 tests | Fallback selected on WS connect failure |
| Hot cache sync + C# `Live()` collection | Yes | No | No | S11 report + `WebSocketHotCacheSync.cs`/`LiveCollection.cs` | Client-side C# pattern |
| Exactly-once delivery semantics | No | No | Yes | ADR scope and protocol behavior | At-least-once with version dedup model |
| Cross-database streaming subscription | No | No | Yes | P10 scope notes | One database per streaming connection path |

## 2.7 Core concepts and mental model

- `snapshot`:
  - Initial full result set for a subscription target at a specific version.
- `change`:
  - Incremental event with operation (`insert`, `update`, `delete`, `upsert`) and monotonic version.
- `resume_from`:
  - Client-provided last seen version used to recover after reconnect.
- `at-least-once`:
  - Clients may see replayed events; version-based dedup is required for idempotent reducers.
- Subscription filtering layers:
  - user filter (from subscribe request),
  - partition-level and row-level authorization filters,
  - target-table match.
- Write stream lifecycle:
  - open -> rows (sequence increasing) -> ack progression -> close.
- Transport strategy:
  - primary WebSocket, optional long-poll fallback for restricted environments.

Invariants:

- Snapshot-first contract is preserved before incremental delivery.
- Sequence/version continuity is monotonic and is the basis for resume and dedup.
- Authorization filtering is enforced in subscription delivery and write validation paths.
- Long-poll transport negotiates JSON wire mode only.

## 2.8 How Aouda implements it

High-level runtime flow:

1. Engine emits `TableChangeEvent` into change emitter/buffer.
2. Subscription manager fans out events to per-subscription channels.
3. Subscription handler combines user filter + ADRA checks and sends `snapshot`/`change`.
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
3. Handler captures current change sequence and executes snapshot query with ADRA predicates applied.
4. Server sends `snapshot` message.
5. Registration snapshot version is set; consumer unblocks and emits live `change` events with higher sequence only.

Primary anchors:

- `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
- `src/Aouda.Server/WebSocket/StreamingSubscriptionManager.cs`

Primary proving tests:

- `tests/Aouda.Server.Tests/WebSocket/SubscriptionHandlerIntegrationTests.cs`
- `tests/Aouda.Server.Tests/WebSocket/StreamingSubscriptionManagerTests.cs`

### Walk-through B: Resume from reconnect (`resume_from`)

1. Re-subscribe includes `resume_from`.
2. Handler optionally refreshes ADRA permission context if permission version changed.
3. Handler compares resume version with current sequence:
   - at-current -> attach to live only,
   - replay available -> deliver buffer events and continue live,
   - replay expired -> send fresh snapshot fallback.
4. Consumer continues with sequence gate to avoid duplicates across boundary.

Primary anchors:

- `src/Aouda.Server/WebSocket/Handlers/SubscriptionHandler.cs`
- `src/Aouda.Engine.Storage/Streaming/ChangeEventEmitter.cs`

Primary proving tests:

- Resume and reconnect behavior coverage in `tests/Aouda.Client.Tests/Streaming/SubscriptionApiTests.cs`
- Gap-safety coverage in `tests/Aouda.Server.Tests/WebSocket/SubscriptionHandlerIntegrationTests.cs`

### Walk-through C: Streaming write frame processing

1. Client opens stream (`stream_open`) with mode (`insert`/`upsert`).
2. `WriteStreamHandler.HandleOpenAsync(...)` validates stream ID and target table.
3. Each `stream_rows` frame enforces:
   - batch limits and payload limits,
   - sequence continuity,
   - backpressure decision (accept/reject/close),
   - per-row PLS/RLS write validation.
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
| Can auth and row/partition policy be enforced on streamed changes? | Sometimes only request-time auth or coarse channel ACL | Streaming pipeline applies ADRA permission context for delivery and writes | Security semantics match normal query/write semantics |
| How does reconnect continuity work? | Often opaque reconnect, app-level patching required | Versioned events + `resume_from` + buffer replay/fallback snapshot | Predictable client recovery model |
| Is multi-transport support built in? | Usually WebSocket only or external gateway needed | WebSocket primary with built-in long-poll fallback and MessagePack mode | More deployment compatibility with constrained networks |
| Are client SDKs symmetric for streaming primitives? | Often one SDK gets full support first | .NET and TypeScript both expose subscribe + write stream with reconnect support | Easier multi-platform app parity |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:WebSocket:EnableCompression` | bool | `true` | `true/false` | server config | Enables compressed WS accept context |
| `Aouda:WebSocket:EnableMessagePack` | bool | `true` | `true/false` | server config | If `false`, `wire_mode=msgpack` auth is rejected |
| `Aouda:WebSocket:MaxConnections` | int | `10000` | `>=1` | server config | Global connection cap |
| `Aouda:WebSocket:HeartbeatInterval` | timespan | `00:00:20` | positive | server config | Server heartbeat emit interval |
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
| `TS streaming.enableCompression` | bool | `true` | `true/false` | `AoudaClientOptions.streaming` | Node transport option |
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

Expected result: callback receives snapshot and subsequent changes; write stream returns ack progression via `lastAcknowledgedSeq`.

Common mistake: expecting exactly-once semantics and not deduping by version after reconnect.

### HTTP/protocol examples

```http
GET /api/databases/appdb/ws
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <key>
```

```json
{"type":"auth","token":"<jwt-or-api-key>","database":"appdb","wire_mode":"json"}
```

```json
{"type":"subscribe","id":"sub-orders","target":"orders","resume_from":123}
```

```http
POST /api/databases/appdb/stream/longpoll/connect
Content-Type: application/json

{"token":"<jwt-or-api-key>","wireMode":"json"}
```

Expected result: `auth_ok` is returned for valid auth, then `snapshot`/`change` messages flow over the chosen transport.

Common mistake: sending `wireMode: "msgpack"` on long-poll; long-poll supports JSON mode only.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Subscribe to table changes | `ITableOperations.SubscribeAsync()` | `TableQuery.subscribe()` | `subscribe` message over WS/long-poll | Implemented | Snapshot then incremental |
| Typed subscriptions | `ITableOperations<T>.SubscribeAsync()` | Generic `TableQuery<T>.subscribe()` typing | Same protocol payload, typed client mapping only | Implemented | Type mapping is client-side |
| Resume from version | Automatic in subscription implementation | Automatic re-subscribe with `resume_from` | `resume_from` field in subscribe message | Implemented | At-least-once replay semantics |
| Open write stream | `OpenWriteStreamAsync(mode)` | `openWriteStream({ mode })` | `stream_open`, `stream_rows`, `stream_ack`, `stream_close` | Implemented | Insert/upsert supported |
| MessagePack wire mode | `.NET WireMode.MessagePack` | `streaming.wireMode = "msgpack"` | auth `wire_mode` negotiation | Implemented | Long-poll is JSON-only |
| Long-poll fallback | `.NET EnableLongPollFallback` | `streaming.enableLongPollFallback` | `/stream/longpoll/connect|send|poll|{id}` | Implemented | Fallback used when WS connect fails |
| Hot cache live mirror (C#) | `HotCacheSettings` + `Live()` | No equivalent SDK pattern | n/a | Partial | C# only feature pattern today |
| Embedded streaming support | Not supported (throws) | n/a | n/a | Partial | Server mode only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Exactly-once stream processing contract | No exactly-once mode in server/protocol/SDKs | Use version-based dedup and idempotent reducers | Future architecture decision; not in current P10 scope | Medium |
| Cross-database subscriptions on single connection | No cross-db subscription targeting in protocol path | Open separate client/connection per database | Future clustering/distribution roadmap work | Medium |
| Distinct MQ "not ready" error code | No dedicated protocol error; currently generic not-found style | Treat missing/not-ready uniformly and retry after MQ setup | BL-053 from S10 report context | Low/Medium |
| TS equivalent of C# `Live()` hot collection abstraction | No dedicated TS `Live()` API | Use `subscribe()` and local reducer state in app layer | Future TS client ergonomics task (not in current P10 scope) | Low |

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
- Reconnect path uses `resume_from`.
- Either missed buffered changes replay or fresh snapshot fallback occurs.
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
- Resume behavior depends on post-restart change-buffer availability for each table.

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
| Snapshot arrives but no changes | No matching writes or filters/ADRA exclude all changes | Validate write activity, user filter, and PLS/RLS permission context |
| Duplicate-looking changes after reconnect | At-least-once replay path | Deduplicate by event version in client reducer |
| Resume returns fresh snapshot | Buffer replay expired for requested version | Accept snapshot fallback or increase practical reconnect cadence |
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
| WebSocket handshake, auth, heartbeat | `WebSocketHandlerIntegrationTests.cs` | Pass | Strong | Covers JWT/API key/no-auth, wire mode, ping/pong |
| Subscription snapshot/change lifecycle | `SubscriptionHandlerIntegrationTests.cs` | Pass | Strong | Includes empty/populated snapshot and CRUD change flow |
| ADRA filtering logic | `StreamingSubscriptionManagerTests.cs` | Pass | Strong | Unit coverage across PLS/RLS combinations and update semantics |
| Server-side user filter behavior | `SubscriptionFilterEvaluatorTests.cs` + subscription integration tests | Pass | Strong | Includes normalization and update enter/leave scope behavior |
| Write-stream lifecycle + backpressure | `WriteStreamHandlerIntegrationTests.cs` | Pass | Strong | Mode validation, sequence, ack, pressure, row-level errors |
| .NET streaming API behavior | `SubscriptionApiTests.cs`, `WriteStreamApiTests.cs` | Pass | Strong | Reconnect, resume, typed mapping, close/dispose behavior |
| Materialized query streaming | `MaterializedQuerySubscriptionApiTests.cs` | Pass | Medium/Strong | Subscribing to MQ result tables and change propagation |
| .NET fallback lifecycle | `StreamingFallbackLifecycleTests.cs` | Pass | Medium/Strong | Long-poll lifecycle and reconnect scenarios |
| TypeScript streaming transport and API | `websocket-transport.test.ts`, `subscription.test.ts`, `write-stream.test.ts`, `longpoll-transport.test.ts` | Pass | Strong | Callback/iterator/write/fallback/wire-mode coverage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| Full auth-db integration tests for all subscription PLS/RLS combinations remain partially unit-biased | End-to-end auth database wiring under real token flows is high-risk | Add full `AoudaTestServer` auth-db integration suites covering snapshot+change in all ADRA modes | High |
| Resume path dedicated server integration suite is less explicit than core subscribe suite | Resume correctness is critical under production reconnect churn | Add focused server integration tests for at-current/replay/expired resume triad with concurrent writes | High |
| Long-duration pressure soak for write streams not explicit in current suite | Sustained throughput can reveal backpressure oscillation bugs | Add deterministic soak test with threshold tuning and expected ack/close behavior assertions | Medium |
| Cross-SDK parity assertions for messagepack plus fallback combinations | Prevents subtle behavior divergence between .NET and TS | Add contract parity matrix tests shared via protocol fixture payload sets | Medium |

## 2.18 Known gaps and undone work

- Cross-database subscriptions are not a shipped streaming feature.
  - User impact: multi-database consumers must maintain separate subscriptions/connections per database.
- Exactly-once semantics are not provided.
  - User impact: applications must implement version-based dedup/idempotent state transitions.
- Distinct materialized-query "not ready" error code is not yet surfaced as a dedicated protocol contract.
  - User impact: client error handling for MQ-not-ready vs not-found remains coarse.
- Legacy SSE subscription endpoint remains in server code.
  - User impact: avoid mixing legacy SSE semantics with P10 streaming expectations.

## 2.19 References

- ADRs:
  - `docs/decisions/0020-real-time-streaming.md`
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
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

