---
title: "Write Path Durability"
nav_order: 6
parent: "Guides"
---

# Aouda Functionality: Write Path Durability

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-03-31

Coverage phases: P0, P1, P6, P7
Primary task folders: `docs/tasks/P6/`, `docs/tasks/P7/`
Primary ADRs: `docs/decisions/0003-write-ahead-log.md`, `docs/decisions/0005-persistence-policies.md`, `docs/decisions/0010-cluster-membership-replication.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-RealTime-Streaming.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Auth-And-Authorization.md`

## Start Here

If your question is "How durable are writes by default, and how do I change behavior?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`

If your question is "What is implemented vs missing right now?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.15 Verification ledger`
- `2.16 Test coverage matrix`

---

## 2.1 Why this functionality exists

Aouda durability makes write outcomes explicit instead of implicit.

- User problem solved:
  - "My process died; do I lose acknowledged writes?"
  - "Can I trade latency for stronger durability only when needed?"
  - "Can primary writes wait for replica acknowledgement?"
- Core outcomes:
  - Local crash durability with write-ahead logging (WAL).
  - Replay-driven recovery after kill/restart.
  - Replication-aware write concern (`One`, `Majority`, `All`) with timeout policy.
  - Table-level and database-level durability policy layering.
- Non-goals (current implementation):
  - WAL-backed delete mutations (delete `WalPosition` stays `-1`).
  - Full API surface for per-table durability controls via REST/SDKs.

## 2.2 Discovery and navigation map

### Question -> section map

- "What are defaults?" -> `2.3`
- "What is available today?" -> `2.4`, `2.5`, `2.6`
- "How does the write path work end-to-end?" -> `2.8`, `2.8.1`
- "How do I configure server/db/table/per-write durability?" -> `2.10`
- "Which API/client surfaces are wired or missing?" -> `2.11`
- "How do I run this operationally?" -> `2.12`, `2.13`, `2.14`
- "What tests prove this behavior?" -> `2.15`, `2.16`, `2.17`

### Role-based map

- Platform engineer:
  - `2.8`, `2.8.1`, `2.10`, `2.13`
- App developer:
  - `2.3`, `2.10`, `2.11`, `2.12`
- SRE/operations:
  - `2.13`, `2.14`, `2.15`
- Reviewer/auditor:
  - `2.4`, `2.5`, `2.6`, `2.16`, `2.18`

### Source map

- WAL and replay core:
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Wal/WalFlushQueue.cs`
  - `src/Aouda.Engine.Wal/WalSegmentWriter.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalReplayDriver.cs`
  - `src/Aouda.Engine.Wal/WalCheckpointManager.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalCheckpointer.cs`
- Engine write-path integration:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
  - `src/Aouda.Engine.Storage/Ingest/TableAppender.cs`
  - `src/Aouda.Engine.Api/Results/EngineInsertResult.cs`
  - `src/Aouda.Engine.Api/Results/EngineUpdateResult.cs`
  - `src/Aouda.Engine.Api/Results/EngineDeleteResult.cs`
- Durability policy models:
  - `src/Aouda.Engine.Storage/Registry/DatabaseOptions.cs`
  - `src/Aouda.Engine.Catalog/Policies.cs`
- Replication/write concern:
  - `src/Aouda.Engine.Core/Replication/WriteConcern.cs`
  - `src/Aouda.Engine.Core/Replication/TimeoutBehavior.cs`
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Engine.Replication/Streaming/PendingWriteTracker.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamServer.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamClient.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamProtocol.cs`
- Server API and config:
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigSection.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigConversion.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptionsValidator.cs`
- Protocol and clients:
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/types.ts`
  - `../aouda-client-ts/src/databases.ts`

## 2.3 Defaults and zero-config behavior

When you do not set durability knobs explicitly:

- WAL:
  - Database default `EnableWal = true` (`DatabaseOptions`).
  - Table-level `Durability.EnableWal` is nullable; null inherits database default.
- Replication mode:
  - Database default `ReplicationMode = Sync`.
- Write concern:
  - Database default `WriteConcern = Majority`.
  - Database default `WriteConcernTimeoutMs = 5000`.
  - Database default timeout behavior `OnWriteConcernTimeout = Fail`.
  - Per-write override can be sent on DML protocol payloads.
- Effective resolution precedence:
  1. Per-write override (`Insert/Update/Delete` request field)
  2. Table durability override (`TableDurabilityOptions`)
  3. Database options defaults
- Guardrail:
  - Table `EnableWal = true` is rejected if database `EnableWal = false`.

## 2.4 Availability status (implementation honesty)

### Available now

- Local durability via WAL append path for insert/update.
- WAL replay and crash-safe recovery paths, including torn-tail repair.
- WAL checkpoints for replay fast-forward.
- Streaming replication over WAL frames (multi-database aware protocol versions).
- Write concern wait pipeline with quorum + timeout policies.
- Per-database durability configuration via server config + database API.
- Table durability policy model in engine/catalog with inheritance and validation.
- Health and metrics endpoints that expose key operational durability indicators.

### Planned / proposed

- REST and SDK exposure for full per-table durability controls (`EnableWal`, `EnableReplication`, `WriteConcern`, `WriteConcernTimeoutMs`, `OnWriteConcernTimeout`).
- Client SDK mutation APIs exposing `WriteConcern` and result `WriteConcernStatus`.
- Full D.3 backup/restore durability scenario once the API surface exists.

### Reserved / not yet wired

- WAL-backed delete path (delete currently returns `WalPosition = -1`).
- Per-database checkpoint synchronization in replication.

## 2.5 Phase coverage matrix

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| P0 | Durability bootstrap skeleton | Implemented | `docs/ROADMAP.md` |
| P1 | WAL and recovery baseline | Implemented | `docs/ROADMAP.md`, WAL/replay test files |
| P6 | Per-db and per-table durability controls, replication protocol, write concern | Partially implemented (API gaps remain) | `docs/tasks/P6/P6-EpicA-Task5-PerTableWalAndReplicationControl-Report.md`, `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`, `docs/tasks/P6/P6-EpicE-Task3-WriteConcernSynchronousReplication-Report.md` |
| P7 | Durability scenarios in harness | Implemented with one scenario deferred | `docs/tasks/P7/P7-Task6-DurabilityScenarios-Report.md` |

## 2.6 Capability coverage matrix

| Capability | Status | Notes |
|---|---|---|
| WAL append and fsync path | Implemented | `WalWriter.AppendAsync` and `WalFlushQueue` integrate with engine writes. |
| Insert/update WAL tagging with commit frame | Implemented | `TableAppender` emits begin/append/commit tags. |
| Delete WAL durability | Missing | Delete path is in-memory tombstoning; `EngineDeleteResult.WalPosition = -1`. |
| Crash recovery via WAL replay | Implemented | `WalReplayDriver` + storage tests/harness scenarios. |
| Checkpoint-assisted replay | Implemented | `WalCheckpointer` + `WalCheckpointManager`. |
| Per-database durability config | Implemented | `DatabaseOptions`, config conversion/validation, create-database API. |
| Per-table durability model | Implemented (engine/catalog) | Present in `TableDurabilityOptions`; API exposure is incomplete. |
| Per-write write concern override | Implemented at protocol/server | `Messages.cs` fields + `TablesController` + `WriteConcernService`. |
| C# SDK write concern mutation API | Missing | `RemoteTableQuery` does not expose write concern argument. |
| TypeScript SDK write concern mutation API | Missing | `query-builder.ts` does not expose `writeConcern`. |
| TypeScript mutation `writeConcernStatus` | Missing | `types.ts` lacks status field present in protocol/server results. |
| Multi-database replication stream filtering | Implemented | v2/v3 protocol and per-database subscriptions. |
| Per-table replication filtering in stream | Implemented at protocol level | v3 table subscription filters and server-side filtering counters. |
| Per-database checkpoint sync for replication | Deferred | Explicitly deferred in P6 Epic E Task 1 report. |

## 2.7 Core concepts and mental model

- WAL frame pipeline:
  - Mutations are encoded as WAL frames and flushed before write results are considered durable.
- WAL position as durability token:
  - Insert/update return a WAL position used by write concern tracking.
- Write concern:
  - Defines how many acknowledgements are required before operation success is returned.
- Timeout behavior:
  - Defines fail/degrade semantics when quorum is not met within timeout.
- Policy inheritance:
  - Durability can be set at db level, optionally overridden at table level, optionally overridden per write.
- Recovery:
  - On restart, WAL is replayed and can be fast-forwarded by checkpoints.

## 2.8 How Aouda implements it

The write durability path is a composition of engine, WAL, replication, and server orchestration:

1. Write operation enters engine path (`AoudaEngine.InsertRowsAsync`, `UpdateRowsAsync`).
2. `TableAppender` writes begin/page/commit WAL tags when a resolved `WalWriter` exists.
3. `WalWriter` appends and flushes, updates `Position`, and emits `OnFrameAppended`.
4. Replication broadcaster forwards frames to subscribers (`WalStreamServer`).
5. Server DML controller receives engine result and registers pending write wait by WAL position.
6. `WriteConcernService` resolves effective concern (request -> table -> database), computes required ACKs, and awaits `PendingWriteTracker`.
7. ACKs are consumed from stream client/server protocol and complete pending waiters.
8. On restart, `WalReplayDriver` rehydrates in-memory state and uses checkpoint metadata to avoid replaying already durable sections.

Design characteristics:
- The durability coordination boundary is WAL position, not mutation payload.
- Write concern waiting is async and timeout-driven.
- Protocol versions support cross-database durability in a single stream connection.

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Insert with WAL enabled and database-default write concern

1. Client sends insert request with no explicit write concern.
2. Engine resolves table WAL policy via `ResolveWalWriter(tableEntry)`.
3. `TableAppender.SealAndWriteAsync` emits begin + append + commit frames.
4. `WalWriter` flushes frames; insert result carries `WalPosition`.
5. `TablesController.InsertRows` resolves effective write concern (table/database defaults).
6. `WriteConcernService` computes required ACK count and waits on `PendingWriteTracker`.
7. Once ACK threshold is met (or immediate local path satisfies `One`), response returns with write concern status.

### Walk-through B: Update with explicit per-write concern and timeout degradation

1. Client sends update with `writeConcern` override and strict timeout.
2. Update path writes WAL and captures commit position.
3. `WriteConcernService` uses request override over table/db defaults.
4. `PendingWriteTracker` waits for ACK quorum until timeout.
5. If timeout occurs and behavior is `Degrade` or `DegradeAndLog`, operation can return success with degraded status.
6. Metrics counters increment for waits, timeout, degradation/failure.

### Walk-through C: Crash and restart recovery

1. Process is terminated after durable and non-durable writes are interleaved.
2. On startup, storage initializes and WAL replay is invoked.
3. Replay reads segments, validates frames (CRC), trims torn tail if present, and reapplies durable frames.
4. Checkpoint manager provides last-known replay checkpoint to fast-forward.
5. Queries after startup observe replayed state; scenario tests validate expected rows.

### Walk-through D: Replication ACK path for write concern

1. Primary appends WAL frame, and stream server broadcasts per subscribed database.
2. Secondary stream client receives frame and sends ACK.
3. Commit frames trigger immediate ACK optimization path.
4. `WalStreamServer` processes ACKs and forwards to `PendingWriteTracker`.
5. Waiting DML operation is completed when configured quorum is reached.

## 2.9 Why Aouda is different (differentiators)

- Durability policy is part of table/database metadata model (not only server-global knobs).
- Write concern is integrated into DML response semantics, not a side channel.
- Multi-database-aware WAL stream protocol supports database and table filtering.
- Checkpoint and replay logic are integrated with storage lifecycle for recovery speed.
- Health + metrics + scenario harness provide implementation-level observability and evidence.

## 2.10 Configuration and settings reference (complete surface)

### Server configuration (`appsettings.json` -> `DatabaseConfigSection`)

| Setting | Scope | Type | Default | Notes |
|---|---|---|---|---|
| `EnableWal` | Database default | bool | `true` | Can be overridden by table durability when API wired. |
| `ReplicationMode` | Database default | enum string | `Sync` | Parsed via `DatabaseConfigConversion`. |
| `WriteConcern` | Database default | enum string | `Majority` | Validated by options validator. |
| `WriteConcernTimeoutMs` | Database default | int | `5000` | Validator enforces minimum (100ms). |
| `OnWriteConcernTimeout` | Database default | enum string | `Fail` | `Fail`, `Degrade`, `DegradeAndLog`. |

### Engine/catalog durability model (`TableDurabilityOptions`)

| Property | Type | Nullable | Meaning |
|---|---|---|---|
| `EnableWal` | bool | yes | Table WAL override; null inherits db setting. |
| `EnableReplication` | bool | yes | Table replication participation override. |
| `WriteConcern` | enum | yes | Table default write concern override. |
| `WriteConcernTimeoutMs` | int | yes | Table default timeout override. |
| `OnWriteConcernTimeout` | enum | yes | Table default timeout behavior override. |

Validation and invariants:
- Table `EnableWal = true` is invalid when database `EnableWal = false`.
- Effective write concern configuration resolves per write, then table, then database.

### Per-write request knobs

- Protocol mutation requests include optional `WriteConcern` field:
  - `InsertMessage.WriteConcern`
  - `UpdateMessage.WriteConcern`
  - `DeleteMessage.WriteConcern`
- Server enforces parsed/validated values and applies timeout behavior policies.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (server API + current client constraints)

```csharp
using Aouda.Client;
using Aouda.Client.Databases;
using Aouda.Protocol;

var client = new AoudaClient("http://localhost:5000");

// Database-level durability knobs are available in the .NET API.
await client.Databases.CreateAsync(new CreateDatabaseRequest
{
    Name = "orders",
    EnableWal = true,
    ReplicationMode = "Sync"
});

// NOTE: Current RemoteTableQuery insert/update/delete APIs do not yet expose
// a writeConcern parameter directly.
await client.Table("orders", "events").InsertAsync(new[]
{
    new Dictionary<string, object?> { ["orderId"] = 123, ["status"] = "created" }
});
```

### TypeScript example (database knobs available, write concern mutation gap)

```ts
import { AoudaClient } from "@aouda/client";

const client = new AoudaClient("http://localhost:5000");

await client.databases.create("orders", {
  enableWal: true,
  replicationMode: "sync"
});

// Current query builder does not expose writeConcern on insert/update/delete.
await client.table("orders", "events").insert([
  { orderId: 123, status: "created" }
]);
```

### HTTP/protocol examples

```http
POST /api/databases
Content-Type: application/json

{
  "name": "orders",
  "enableWal": true,
  "replicationMode": "Sync"
}
```

```http
POST /api/tables/orders/events/rows/insert
Content-Type: application/json

{
  "rows": [
    { "orderId": 123, "status": "created" }
  ],
  "writeConcern": "Majority"
}
```

```json
{
  "rowsInserted": 1,
  "writeConcernStatus": {
    "requested": "Majority",
    "requiredAcks": 2,
    "receivedAcks": 2,
    "timedOut": false,
    "degraded": false
  }
}
```

### A) API coverage matrix

| Surface | Capability | Status | Notes |
|---|---|---|---|
| `POST /api/databases` | Set `EnableWal`, `ReplicationMode` | Implemented | Wired in `DatabasesController` request model. |
| Server config (`DatabaseConfigSection`) | Set db write concern defaults | Implemented | Parsed + validated at startup. |
| DML HTTP/protocol (`Insert/Update/Delete`) | Per-write `WriteConcern` | Implemented | Field exists in protocol messages. |
| DML results (`Insert/Update/Delete`) | `WriteConcernStatus` | Implemented server/protocol | Returned by server for concern-tracked writes. |
| Engine/catalog operations | Table durability overrides model | Implemented | `TableDurabilityOptions` + alter durability path. |
| Replication stream protocol | Per-db and per-table filtering | Implemented | v2/v3 handshake and frame/ack payloads. |

### B) Missing API matrix

| Missing surface | Where missing | Impact |
|---|---|---|
| REST create/update table durability payload | `TableMessages.cs` / table controller API contract | Cannot configure full per-table durability via public HTTP contract yet. |
| C# client write concern args | `RemoteTableQuery.cs` | App code cannot request per-write concern via high-level SDK without bypass. |
| TypeScript client write concern args | `query-builder.ts` | Same gap for TS apps. |
| TypeScript `writeConcernStatus` result typing | `types.ts` | Clients cannot type-check status details even though server can return them. |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: Baseline durable writes with defaults

1. Create database with defaults (or omit durability knobs).
2. Insert rows via API.
3. Stop server ungracefully and restart.
4. Validate rows are present post-recovery.
5. Confirm health and metrics remain healthy.

Expected result:
- Inserted rows survive restart due to WAL + replay.

### Scenario 2: Strong replication-aware writes

1. Configure primary + secondaries with WAL streaming.
2. Use `writeConcern = Majority` for inserts/updates.
3. Observe successful writes only after required ACK threshold.
4. Simulate delayed ACKs and inspect timeout behavior.

Expected result:
- Concern waits are enforced; timeout behavior follows `Fail/Degrade/DegradeAndLog`.

### Scenario 3: Table-level durability inheritance validation

1. Set db `EnableWal = true`.
2. Configure table durability override (engine/catalog path).
3. Validate inherited fields when table options are null.
4. Attempt invalid config (`table.EnableWal = true` while db WAL disabled).

Expected result:
- Valid overrides apply; invalid override is rejected.
- For current public APIs, this may require non-REST test harness coverage.

## 2.13 Operations and observability

Primary operational surfaces:
- Health:
  - `WalHealthCheck` evaluates queue pressure against configured thresholds.
  - `HealthController` exposes summary/details.
- Metrics:
  - `MetricsController` exposes snapshots from `MetricsCollector`.
  - Raw counters come from `Perf`.

Durability-related counters available in `Perf` include:
- WAL queue and batching:
  - `WalQueueDepth`, `WalQueueHighWater`, `WalBatchCount`, `WalBatchRecords`, `WalBatchBytes`, `WalBatchFlushMs`
- Table/database filtering:
  - `WalWritesSkippedTableDisabled`, `ReplicationFramesFilteredTable`, `ReplicationFramesFilteredDatabase`, `ReplicationFramesBroadcastedPerDb`
- Write concern behavior:
  - `WriteConcernWaitsTotal`, `WriteConcernWaitMs`, `WriteConcernTimeouts`, `WriteConcernDegradations`, `WriteConcernFailures`, `WriteConcernSuccessful`
- Replication topology health:
  - `ReplicationDatabaseSubscriptions`

Operational guidance:
- Alert on sustained WAL queue growth and high queue high-water marks.
- Track write concern timeout/degradation trends alongside replication lag.
- Validate expected per-db/per-table replication filtering counters when scoped replication is enabled.

## 2.14 Troubleshooting by symptom

- "Writes acknowledged but missing after crash"
  - Check WAL enabled status at effective table/database level.
  - Check replay logs and crash safety tests for torn-tail repair behavior.
- "High write latency on primary"
  - Inspect write concern level and timeout policy.
  - Review replication lag and ACK paths.
- "Unexpected write concern failures/timeouts"
  - Validate secondary count/availability and configured concern level.
  - Inspect `WriteConcernTimeoutMs` and timeout behavior policy.
- "Cannot configure per-table durability from REST"
  - This is a known API gap; engine/catalog support exists but public API is incomplete.

## 2.15 Verification ledger

| Item | Type | Verified | Evidence |
|---|---|---|---|
| WAL write path + flush integration | Code audit | 2026-03-31 | `WalWriter.cs`, `WalFlushQueue.cs`, `TableAppender.cs`, `AoudaEngine.cs` |
| Write concern resolution hierarchy | Code audit | 2026-03-31 | `WriteConcernService.cs`, `PendingWriteTracker.cs`, `TablesController.cs` |
| Delete WAL/write concern limitation | Code audit | 2026-03-31 | `EngineDeleteResult.cs`, `AoudaEngine.DeleteRowsAsync` path |
| Protocol support for write concern/status | Code audit | 2026-03-31 | `Aouda.Protocol/Messages.cs` |
| C#/TS client write concern gaps | Code audit | 2026-03-31 | `RemoteTableQuery.cs`, `../aouda-client-ts/src/query-builder.ts`, `../aouda-client-ts/src/types.ts` |
| Write concern unit tests | Executed | 2026-03-31 | `dotnet test tests/Aouda.Server.Tests --filter "FullyQualifiedName~WriteConcernServiceTests" --no-build` |
| Pending write tracker tests | Executed | 2026-03-31 | `dotnet test tests/Aouda.Engine.Replication.Tests --filter "FullyQualifiedName~PendingWriteTrackerTests" --no-build` |
| WAL recovery/crash tests | Executed | 2026-03-31 | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~WalIntegrationTests|FullyQualifiedName~CrashSafetyTests|FullyQualifiedName~EndToEndRestartTests" --no-build` |
| Harness durability scenarios | Task report audit | 2026-03-31 | `docs/tasks/P7/P7-Task6-DurabilityScenarios-Report.md` |

## 2.16 Test coverage matrix

| Area | Test file(s) | Coverage status | Notes |
|---|---|---|---|
| Write concern resolution and parsing | `tests/Aouda.Server.Tests/Services/WriteConcernServiceTests.cs` | Covered | Includes hierarchy and required ACK logic. |
| Pending write waiting and timeout behavior | `tests/Aouda.Engine.Replication.Tests/Streaming/PendingWriteTrackerTests.cs` | Covered | Includes quorum, timeout, degrade/fail behavior. |
| WAL integration and replay robustness | `tests/Aouda.Engine.Storage.Tests/WalIntegrationTests.cs` | Covered | Includes torn-tail repair and replay correctness. |
| Crash safety and restart behavior | `tests/Aouda.Engine.Storage.Tests/CrashSafetyTests.cs`, `EndToEndRestartTests.cs` | Covered | Restart correctness validated. |
| Durability E2E scenarios | `src/Aouda.TestHarness/Scenarios/Durability/*.cs` | Partially covered | D.1 and D.4 implemented; D.3 deferred. |
| Per-table durability via REST | N/A | Not covered (surface missing) | Model exists but API contract is incomplete. |

## 2.17 Testing gaps and proposed tests

- Add server API integration tests once per-table durability payload is exposed on create/update table endpoints.
- Add SDK tests for C# and TS mutation write concern arguments once client surface is implemented.
- Add TS client type tests for `writeConcernStatus` in mutation results.
- Add delete durability tests once WAL-backed delete path is implemented.
- Add per-database checkpoint sync tests when replication checkpoint synchronization ships.

## 2.18 Known gaps and undone work

- Public REST/SDK surface for table durability controls is incomplete.
- C# and TypeScript clients do not yet expose per-write write concern arguments.
- TypeScript client types do not include write concern status in mutation results.
- Delete operations are not WAL-backed, so delete write concern is effectively non-durable.
- Backup/restore D.3 scenario remains deferred pending API support.
- Per-database checkpoint sync in replication is deferred.

## 2.19 References

- Roadmap and backlog:
  - `docs/ROADMAP.md`
  - `docs/BACKLOG.md`
- Durability-related task reports:
  - `docs/tasks/P6/P6-EpicA-Task5-PerTableWalAndReplicationControl-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task3-WriteConcernSynchronousReplication-Report.md`
  - `docs/tasks/P7/P7-Task6-DurabilityScenarios-Report.md`
- Engine/server code:
  - `src/Aouda.Engine.Api/AoudaEngine.cs`
  - `src/Aouda.Engine.Storage/Ingest/TableAppender.cs`
  - `src/Aouda.Engine.Wal/WalWriter.cs`
  - `src/Aouda.Engine.Wal/WalFlushQueue.cs`
  - `src/Aouda.Engine.Wal/WalSegmentWriter.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalReplayDriver.cs`
  - `src/Aouda.Engine.Storage/WalIntegration/WalCheckpointer.cs`
  - `src/Aouda.Engine.Wal/WalCheckpointManager.cs`
  - `src/Aouda.Engine.Storage/Registry/DatabaseOptions.cs`
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Core/Replication/WriteConcern.cs`
  - `src/Aouda.Engine.Core/Replication/TimeoutBehavior.cs`
  - `src/Aouda.Engine.Replication/Streaming/PendingWriteTracker.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamServer.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamClient.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamProtocol.cs`
  - `src/Aouda.Engine.Diagnostics/Perf.cs`
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Health/WalHealthCheck.cs`
  - `src/Aouda.Server/Controllers/HealthController.cs`
  - `src/Aouda.Server/Controllers/MetricsController.cs`
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
- Clients:
  - `src/Aouda.Client/Databases/AoudaDatabasesApi.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `../aouda-client-ts/src/databases.ts`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/types.ts`
- Tests/harness:
  - `tests/Aouda.Server.Tests/Services/WriteConcernServiceTests.cs`
  - `tests/Aouda.Engine.Replication.Tests/Streaming/PendingWriteTrackerTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/WalIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/CrashSafetyTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/EndToEndRestartTests.cs`
  - `src/Aouda.TestHarness/Scenarios/Durability/WalRecoveryScenario.cs`
  - `src/Aouda.TestHarness/Scenarios/Durability/ServerRestartScenario.cs`
  - `src/Aouda.TestHarness/Scenarios/MultiDatabase/PerTableDurabilityOverridesScenario.cs`

## 2.20 What is missing from this document? (meta completeness)

- Full API payload examples for per-table durability create/update endpoints are intentionally absent because those endpoints are not fully exposed yet.
- End-to-end SDK examples with explicit per-write concern are intentionally constrained to current shipped client APIs.
- Per-database checkpoint sync operational guidance is deferred until implementation lands.
