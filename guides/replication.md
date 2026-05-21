---
title: "Replication and Clustering"
nav_order: 9
parent: "Guides"
---

# Aouda Functionality: Replication and Cluster Behavior

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-03-31

Coverage phases: P4, P6, P7
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P6/`, `docs/tasks/P7/`
Primary ADRs: `docs/decisions/0010-cluster-membership-replication.md`, `docs/decisions/0016-wal-lifecycle-management.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Write-Path-Durability.md`, `docs/dev/Functionality-Backup-And-Restore.md`

## Start Here

If your question is "How do I use replication and clustering now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.10.1 Minimal cluster setup quickstart`
- `2.11 API and CLI coverage reference`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.15 Verification ledger`
- `2.16 Test coverage matrix`

---

## 2.1 Why this functionality exists

Replication and clustering exist so Aouda can provide high availability, failover, read scaling, and stronger durability options without changing the core write path model.

- User problem solved:
  - Keep data available when a node fails.
  - Scale reads to secondaries and hidden replicas.
  - Choose durability guarantees (`w:1`, `w:majority`, `w:all`) per workload.
- Operational outcomes:
  - Automatic heartbeat/election and role transition behavior.
  - Explicit node roles (`Primary`, `Secondary`, `Hidden`, `Backup`, `Arbiter`, `Standalone`) with safety guards.
  - Observable replication health, lag, topology, and subscription coverage through admin APIs.
- Scope boundaries:
  - This doc covers replica set behavior, WAL streaming, leader election, read preferences, per-database/per-table replication routing, and write concern.
  - This doc does not claim cloud control plane orchestration, dynamic membership reconfiguration, mTLS transport auth, or full client-side smart replica routing as shipped.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What happens with no replica set config? | `2.3 Defaults and zero-config behavior` |
| Which replication pieces are shipped today? | `2.4 Availability status` |
| Which phases delivered what? | `2.5 Phase coverage matrix` |
| Which capabilities are complete vs partial? | `2.6 Capability coverage matrix` |
| How runtime flow works internally | `2.8 How Aouda implements it` |
| Full replication config and defaults | `2.10 Configuration and settings reference` |
| How to stand up a working replica set | `2.10.1 Minimal cluster setup quickstart` |
| .NET / TypeScript / HTTP surface and gaps | `2.11 API and CLI coverage reference` |
| How to roll out safely in production | `2.12 Scenario playbooks` |
| What to monitor and tune | `2.13 Operations and observability` |
| How to debug failures quickly | `2.14 Troubleshooting by symptom` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.11 API and CLI coverage reference`, `2.12 Scenario playbooks` |
| Operator/SRE | `2.10 Configuration and settings reference`, `2.13 Operations and observability`, `2.14 Troubleshooting by symptom` |
| SDK maintainer | `2.11 API and CLI coverage reference`, `2.17 Testing gaps and proposed tests`, `2.18 Known gaps and undone work` |
| Engine contributor | `2.5 Phase coverage matrix`, `2.8 How Aouda implements it`, `2.16 Test coverage matrix`, `2.19 References` |

### Source map

- Task/report evidence:
  - `docs/tasks/P4/P4-EpicE-Task0-ClusterFoundation-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task1-WalStreamingProtocol-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task2-CheckpointSync-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task3-ReplicaStateMachine-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task4-HeartbeatLeaderElection-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task5-WorkloadSpecializedReplicas-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task6-HiddenReplicasReadPreferences-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task4-ReplicationIntegration-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task2-ClusterTopologyDatabaseAwareness-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task3-WriteConcernSynchronousReplication-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task4-PerTableReplicationRouting-Report.md`
  - `docs/tasks/P7/P7-Task7-ReplicationScenarios-Report.md`
- Core code:
  - `src/Aouda.Engine.Replication/`
  - `src/Aouda.Server/Startup/ReplicationHostedService.cs`
  - `src/Aouda.Server/Controllers/ReplicationController.cs`
  - `src/Aouda.Server/Controllers/QueryController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Server/Middleware/WriteGuardFilter.cs`
  - `src/Aouda.Engine.Wal/Slots/`
- Client and protocol surfaces:
  - `src/Aouda.Client/AoudaClient.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/ProtocolConstants.cs`
  - `../aouda-client-ts/src/admin/replication.ts`
  - `../aouda-client-ts/src/admin/replication-types.ts`
- Test evidence:
  - `tests/Aouda.Engine.Replication.Tests/`
  - `tests/Aouda.Server.Tests/ReplicationIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/QueryReadPreferenceTests.cs`
  - `tests/Aouda.Server.Tests/HiddenReplicaQueryTests.cs`
  - `tests/Aouda.Server.Tests/ReplicationControllerTests.cs`
  - `../aouda-client-ts/tests/admin.test.ts`

## 2.3 Defaults and zero-config behavior

If you do nothing:

- Server runs as `Standalone` (`Aouda:ReplicaSet` unset).
- No cross-node replication traffic is started.
- Query reads are accepted locally; read preference is effectively ignored in standalone mode.
- Database replication mode defaults to `Replicate` (relevant only when clustering is enabled).
- Database write concern defaults to `One` with timeout policy present but unused for `w:1`.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `Aouda:ReplicaSet` | `null` | Server starts in `Standalone` role |
| `ReplicaSet.HeartbeatIntervalMs` | `2000` | Heartbeats every 2s when clustered |
| `ReplicaSet.ElectionTimeoutMs` | `10000` | Primary failure detection threshold |
| `ReplicaSet.ReplicationPort` | `5433` | WAL streaming port; election uses `+1` offset |
| `NodeConfig.Priority` | `5` | Eligible default election weight |
| `NodeConfig.Hidden` | `false` | Node is visible/read-candidate unless role says otherwise |
| `NodeConfig.Backup` | `false` | No backup-node behavior unless explicitly set |
| `NodeConfig.TemperatureProfile` | `Balanced` | Neutral hot/cold hinting |
| `NodeConfig.Subscriptions` | empty list | Subscribe to all databases and all tables |
| `ArchiveConfig.Enabled` | `false` | No standalone archive mode unless enabled |
| `Databases:{db}:ReplicationMode` | `Replicate` | DB participates in replication by default |
| `Databases:{db}:WriteConcern` | `One` | No ACK wait on writes by default |
| `Databases:{db}:WriteConcernTimeoutMs` | `5000` | Timeout used when concern > `One` |
| `Databases:{db}:OnWriteConcernTimeout` | `DegradeAndLog` | Timeout degrades by default when concern > `One` |
| Query read preference | `Primary` | Query parameter/header defaults to primary semantics |
| Health threshold `ReplicationLagDegradedSeconds` | `10` | Degraded health threshold for replication lag |
| Health threshold `ReplicationLagUnhealthySeconds` | `60` | Unhealthy health threshold for replication lag |

## 2.4 Availability status (implementation honesty)

### Available now

- Replica set foundation and role model:
  - `Standalone`, `Primary`, `Secondary`, `Hidden`, `Backup`, `Arbiter`.
  - Role-aware write blocking and fencing-token validation for write endpoints.
- WAL streaming and catch-up:
  - Streaming protocol v1/v2/v3 with HMAC and CRC.
  - Checkpoint transfer bootstrap for too-far-behind replicas.
  - Replica state machine applying WAL frames with transaction ordering safeguards.
- Election and failover mechanics:
  - Heartbeat protocol and failure detection.
  - Priority-based election with quorum and fencing token step-down.
  - Role transition wiring in server startup service.
- Routing controls:
  - Query endpoint supports `readPreference` query parameter and `X-Read-Preference` header.
  - Hidden replica behavior enforced (`421 Misdirected Request` when preference cannot be served).
  - Topology endpoint exposes `ReadCandidates` and hidden flags.
- Per-database and per-table replication:
  - Per-database broadcasters, subscriptions, and per-database ACKs.
  - Per-table subscription filtering (`All`, `Include`, `Exclude`) with coverage endpoint.
  - Per-database lag tracking in status/topology and health checks.
- Write concern:
  - Database-level defaults + table-level durability overrides + per-request override.
  - `w:1`, `w:majority`, `w:all` with timeout behavior (`Fail`, `Degrade`, `DegradeAndLog`).
  - `writeConcernStatus` surfaced in write responses when concern > `w:1`.
- WAL retention integration:
  - Replication slot creation/update on stream connections and ACKs.
  - Slot reconnect behavior preserves slots across disconnect/reconnect.

### Planned / proposed

- mTLS for inter-node auth (ADR direction; keyfile/HMAC is current implementation).
- Dynamic cluster membership changes without restart.
- Cloud control plane orchestration (layered model in ADR, not server-shipped).
- Temperature-aware read routing as end-to-end server/client behavior.
- Client-side topology caching and automated replica routing decisions.
- Explicit named-replica targeting (`Specific`) from ADR intent.

### Reserved / not yet wired

- Full per-database checkpoint sync (current checkpoint path uses first available DB engine).
- Public admin API for WAL slot inspection/listing (proposed in task follow-up notes).
- Per-replica slot-lag metrics endpoint (proposed in task follow-up notes).
- TS/.NET first-class write concern request API (protocol field exists; SDK convenience surface incomplete).
- TS read preference query API (no equivalent to `.WithReadPreference()`).
- Lag-threshold input path for `SecondaryWithMaxLag` at query endpoint (enum exists, but endpoint currently only parses preference string).

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P4 (Epic E) | Task0-Task6 reports | Cluster config/roles, write guard, WAL streaming, checkpoint sync, replica state machine, election/fencing, hidden/read preferences, temperature hints in heartbeat/topology | Dynamic membership, mTLS, cloud plane, temperature-aware routing remain deferred | ADR 0010 + task-level deferred sections |
| P4 (Epic I) | Task1/3/4/5 reports | Slot infrastructure, retention worker, replication slot integration, backup/system slot updates | Archive worker task not covered here; slot admin/lag endpoints not shipped | `docs/tasks/P4/P4-EpicI-Task4-ReplicationIntegration-Report.md` follow-up notes |
| P6 (Epic E) | Task1-Task4 reports | Per-database WAL replication, topology DB awareness, write concern, per-table subscriptions + coverage API | Full per-db checkpoint transfer deferred; client API parity for write concern/subscriptions deferred | Task reports (deferred sections) |
| P7 | `P7-Task7-ReplicationScenarios-Report.md` | Harness-level replication scenario framework (`ReplicationServerGroup`, `ReplicationVerifier`) | Scenarios still skip in harness flow due test setup assumptions and stale capability assumptions | `docs/BACKLOG.md` BL-024 (stale relative to current server capabilities) |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Replica set roles and write gating | Yes | No | No | P4 E0 report + `WriteGuardFilter` + server tests | Secondary/hidden/backup reject writes |
| Heartbeat, election, fencing failover loop | Yes | No | No | P4 E4 report + election tests | Election port is replication port + 1 |
| WAL stream replication (steady-state) | Yes | No | No | P4 E1 report + streaming tests | HMAC + CRC + ACK paths |
| Too-far-behind checkpoint bootstrap | Yes | Yes | No | P4 E2 report + checkpoint tests | Per-db checkpoint still partial |
| Replica WAL replay into storage/catalog | Yes | No | No | P4 E3 report + replica state machine code/tests | Includes DDL and Tx frame handling |
| Hidden replica read preference behavior | Yes | No | No | P4 E6 report + `HiddenReplicaQueryTests` | Non-hidden cannot serve `Hidden` preference |
| Per-database replication subscriptions | Yes | No | No | P6 E1 report + multi-db tests | v1/v2 protocol compatibility retained |
| Per-table subscription routing | Yes | No | No | P6 E4 report + table filter tests | O(1) table-id filtering at server |
| Per-database lag/topology visibility | Yes | No | No | P6 E2 report + admin endpoints | Status + topology + health check |
| Write concern wait/degrade/fail behavior | Yes | No | No | P6 E3 report + tracker/service tests | Hierarchy: request -> table -> DB |
| SDK read preference parity (.NET + TS) | No | Yes | No | `.NET` `RemoteTableQuery.WithReadPreference`, TS no equivalent | TS gap |
| SDK write concern request parity (.NET + TS) | No | Yes | No | Protocol field exists, SDK APIs do not expose typed option | Raw HTTP workaround |
| Slot observability API | No | No | Yes | P4 I4 report follow-up items | No `/admin/replication/slots` endpoint |
| Full process-level failover E2E scenarios | No | Yes | No | P7 Task7 report + BL-024 | Harness exists; server-process scenario remains incomplete |

## 2.7 Core concepts and mental model

- Replica set:
  - A statically configured member list plus local `ThisNode` behavior.
- Server role:
  - Runtime state (`Primary`/`Secondary`/etc.) that determines write acceptance and read eligibility.
- WAL replication:
  - Aouda replicates WAL frames, not reconstructed table state snapshots.
- Fencing token:
  - Monotonic token used to prevent stale-primary writes in split-brain-like conditions.
- Read preference:
  - Query-time routing intent (`Primary`, `Secondary`, `Hidden`, etc.) validated by serving node role.
- Write concern:
  - Write durability target based on secondary ACK counts (`One`, `Majority`, `All`).
- Database subscriptions:
  - Secondary can choose which databases and tables it receives.
- Replication slots:
  - Retention cursors that keep WAL segments until consumers have acknowledged positions.

Invariants:

- Non-primary roles do not accept writes (`RequireWritePermission`).
- Hidden members do not serve default reads; they require explicit `Hidden` preference.
- `w:1` does not register pending tracker waits.
- ACK position updates advance slot positions; disconnect does not auto-delete replication slots.
- In standalone mode, read preference checks are bypassed by design.

## 2.8 How Aouda implements it

High-level architecture path:

1. Server startup (`ReplicationHostedService`) decides initial role from `ReplicaSetConfig`.
2. Election subsystem (`ClusterHeartbeat`, `ElectionManager`, `FailureDetector`, `FencingGuard`) starts for clustered nodes.
3. Primary nodes create per-database WAL broadcasters and run `WalStreamServer`.
4. Secondary/hidden/backup nodes start `WalStreamClient` and apply received frames through `ReplicaStateMachine`.
5. Query and write endpoints consult `ReplicationState` for role/read/write rules.
6. Slot integration updates retention positions from ACK flow, linking replication to WAL lifecycle.

Key implementation anchors:

- Replication core:
  - `src/Aouda.Engine.Replication/ReplicationState.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamServer.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamClient.cs`
  - `src/Aouda.Engine.Replication/Replay/ReplicaStateMachine.cs`
  - `src/Aouda.Engine.Replication/Election/`
- Server orchestration:
  - `src/Aouda.Server/Startup/ReplicationHostedService.cs`
  - `src/Aouda.Server/Controllers/ReplicationController.cs`
  - `src/Aouda.Server/Controllers/QueryController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
- Durability and retention:
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Engine.Replication/Streaming/PendingWriteTracker.cs`
  - `src/Aouda.Engine.Wal/Slots/WalSlotManager.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Secondary bootstrap when too far behind

1. Entry point:
   - Secondary `WalStreamClient` handshake to primary `WalStreamServer`.
2. Key decisions:
   - Server compares requested position with minimum streamable WAL position.
   - If too far behind, server responds with `TooFarBehind`.
3. State mutations and persistence:
   - Secondary requests checkpoint transfer and stages files.
   - `CheckpointApplier` verifies CRC and atomically swaps staged files.
   - Secondary reconnects to continue WAL tail streaming from checkpoint position.
4. Observability:
   - Checkpoint transfer logs and replication lag position transitions.
5. Proving tests:
   - `CheckpointTransferTests`
   - `CheckpointProtocolTests`

### Walk-through B: Primary write with `w:majority`

1. Entry point:
   - HTTP write endpoint in `TablesController` (`insert/update/delete`) with optional `writeConcern`.
2. Key decisions:
   - Resolve effective concern in `WriteConcernService` using precedence:
     - per-request override -> table durability -> database options -> `One`.
   - If concern is `One` or WAL position invalid, skip wait.
3. State mutations and persistence:
   - Engine commit writes WAL and returns WAL position.
   - Pending write is registered in `PendingWriteTracker`.
   - ACKs from secondaries flow through `WalStreamServer.ReadAcks*` and notify tracker.
   - Tracker resolves success, degradation, or throws timeout exception.
4. Observability:
   - `WriteConcernWaitsTotal`, `WriteConcernSuccessful`, `WriteConcernTimeouts`, `WriteConcernDegradations`.
5. Proving tests:
   - `PendingWriteTrackerTests`
   - `WriteConcernServiceTests`
   - `WriteConcernConfigTests`

### Walk-through C: Query with read preference on hidden node

1. Entry point:
   - `POST /api/databases/{db}/query` with `readPreference` query param or `X-Read-Preference` header.
2. Key decisions:
   - Query parameter wins over header.
   - Server computes `isHidden` from `ReplicaSet.ThisNode.Hidden`.
   - `ReadPreferenceExtensions.CanServe` validates `(preference, role, hidden)`.
3. State mutations and persistence:
   - No replication state mutation on this path; request is either rejected (`421`) or executed.
4. Observability:
   - Error payload includes role and hidden state for misdirected requests.
   - Response headers include serving metadata (`X-Served-By`, `X-Server-Role`).
5. Proving tests:
   - `QueryReadPreferenceTests`
   - `HiddenReplicaQueryTests`

### Walk-through D: Admin topology and coverage inspection

1. Entry point:
   - `GET /admin/replication/topology` and `GET /admin/replication/coverage`.
2. Key decisions:
   - Standalone mode returns single-member topology with no primary.
   - Cluster mode combines static config with heartbeat/stream runtime state.
   - Coverage computes per-table subscribers and warns on replicated tables with zero subscribers.
3. State mutations and persistence:
   - Read-only path; snapshots derived from `ReplicationState`, `ClusterHeartbeatAccessor`, and `ReplicationStreamAccessor`.
4. Observability:
   - Topology includes read candidates, hidden flags, per-database positions, and subscriptions.
5. Proving tests:
   - `ReplicationControllerTests`
   - `ReplicationIntegrationTests`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| How is replication state transferred? | Mix of snapshot/state shipping and log paths | WAL-first replication model plus checkpoint bootstrap fallback | Clearer durability model and predictable catch-up path |
| Can workload-specialized replicas be represented directly? | Usually external routing metadata only | `TemperatureProfile` and `HotTableHints` embedded in node config + heartbeat/topology | Better placement signals for future smart routing |
| Are subscriptions coarse or fine-grained? | Often DB-level only | Per-database + per-table filtering with v3 handshake and coverage API | Reduce replica traffic and tailor read replicas |
| Is write concern integrated with server config hierarchy? | Often request-only or static-only | Request -> table -> database hierarchy with timeout behavior and explicit status response | Stronger durability control per workload without full cluster-wide defaults |
| Is replication observability first-class? | External tooling required for many details | Built-in `status`, `topology`, `coverage`, health thresholds, and counters | Faster diagnosis and safer operations |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:ReplicaSet:Name` | string | `""` | non-empty for cluster mode | appsettings/env | Empty/null means standalone |
| `Aouda:ReplicaSet:Members` | string[] | `[]` | `host:port` entries | appsettings/env | Static membership list |
| `Aouda:ReplicaSet:ThisNode:ServerId` | Guid? | `null` | valid GUID | appsettings/env | Auto-generated if unset |
| `Aouda:ReplicaSet:ThisNode:Address` | string? | `null` | `host:port` | appsettings/env | Should match member list entry |
| `Aouda:ReplicaSet:ThisNode:Priority` | int | `5` | `0..100` | appsettings/env | Higher number is more preferred for primary election; `0` means never candidate |
| `Aouda:ReplicaSet:ThisNode:Hidden` | bool | `false` | true/false | appsettings/env | Hidden cannot serve default reads |
| `Aouda:ReplicaSet:ThisNode:Backup` | bool | `false` | true/false | appsettings/env | Backup role startup behavior |
| `Aouda:ReplicaSet:ThisNode:TemperatureProfile` | enum/string | `Balanced` | `Balanced`, `OLTP`, `OLAP`, `Custom` | appsettings/env | Unknown values parse to `Balanced` |
| `Aouda:ReplicaSet:ThisNode:HotTableHints` | string[] | `[]` | table names | appsettings/env | Hinting signal only |
| `Aouda:ReplicaSet:ThisNode:Subscriptions` | list | empty | per-db filter list | appsettings/env | Empty means all DBs/tables |
| `...Subscriptions[*].DatabaseName` | string | n/a | existing DB names | appsettings/env | Secondary subscription scope |
| `...Subscriptions[*].Tables.Mode` | enum | `All` | `All`, `Include`, `Exclude` | appsettings/env | Include/Exclude require names |
| `...Subscriptions[*].Tables.TableNames` | string[] | `[]` | non-empty for Include/Exclude | appsettings/env | Resolved to `TableId` at connect |
| `Aouda:ReplicaSet:ThisNode:Archive:*` | object | n/a | see archive fields | appsettings/env | Required for backup-node archive behavior |
| `Aouda:ReplicaSet:KeyFile` | string? | `null` | file path | appsettings/env | HMAC keyfile auth when set |
| `Aouda:ReplicaSet:HeartbeatIntervalMs` | int | `2000` | positive | appsettings/env | Heartbeat period |
| `Aouda:ReplicaSet:ElectionTimeoutMs` | int | `10000` | positive | appsettings/env | Failure/election threshold |
| `Aouda:ReplicaSet:ReplicationPort` | int | `5433` | `1..65535` | appsettings/env | WAL stream port; election uses `+1` |
| `Aouda:Archive:Enabled` | bool | `false` | true/false | appsettings/env | Standalone archive mode switch |
| `Aouda:Archive:Destination` | string | `""` | URI/path | appsettings/env | Required when archive enabled |
| `Aouda:Archive:CheckpointIntervalHours` | int | `24` | `>=1` | appsettings/env | Archive cadence |
| `Aouda:Archive:WalRetentionDays` | int | `7` | `>=1` | appsettings/env | Retention window |
| `Aouda:Databases:{db}:ReplicationMode` | string | `Replicate` | `Replicate`, `DoNotReplicate` | appsettings/env | Source-side DB replication switch |
| `Aouda:Databases:{db}:WriteConcern` | string | `One` | `One`, `Majority`, `All` | appsettings/env | DB write concern default |
| `Aouda:Databases:{db}:WriteConcernTimeoutMs` | int | `5000` | `>=100` | appsettings/env | Used for concern > `One` |
| `Aouda:Databases:{db}:OnWriteConcernTimeout` | string | `DegradeAndLog` | `Fail`, `Degrade`, `DegradeAndLog` | appsettings/env | Timeout behavior |
| `Aouda:Health:Thresholds:ReplicationLagDegradedSeconds` | int | `10` | positive | appsettings/env | Health degraded threshold |
| `Aouda:Health:Thresholds:ReplicationLagUnhealthySeconds` | int | `60` | positive | appsettings/env | Health unhealthy threshold |
| Query parameter `readPreference` | string | `Primary` behavior | known preference names | per request | Overrides header when both set |
| Header `X-Read-Preference` | string | unset | known preference names | per request | Used when query param absent |
| Header `X-Aouda-Fencing-Token` | int string | unset | integer token | per request | Validated on write endpoints |

Configuration precedence and operational notes:

- Read preference precedence:
  - query parameter `readPreference` -> header `X-Read-Preference` -> implicit `Primary`.
- Write concern precedence:
  - request body `writeConcern` -> table durability override -> database config -> `One`.
- Dynamic vs restart-required:
  - `ReplicaSet` and node-role settings are startup-bound (restart required).
  - Per-request read preference/write concern are dynamic.
  - Database write concern defaults are currently startup config behavior.
- Safety-gated validation:
  - `AoudaServerOptionsValidator` enforces enum validity and range constraints.
- Deprecated/reserved:
  - No deprecated replication config keys are currently marked; several planned capabilities remain unexposed.

Election priority rule:

- Primary preference is **higher numeric priority** (for example `10` is preferred over `5`).
- `Priority = 0` means the node is not eligible to become primary.
- Tie-break and safety rule: WAL freshness can override priority; a more up-to-date lower-priority candidate can still win to avoid electing a stale primary.

### 2.10.1 Minimal cluster setup quickstart

This is a concrete 3-node local setup to get replication communication working.

#### Step 1: create a shared keyfile

Use the same keyfile on all nodes.

```powershell
# Windows PowerShell
[Convert]::ToBase64String((1..64 | ForEach-Object {Get-Random -Max 256})) | Set-Content cluster.key
```

```bash
# Linux/macOS
openssl rand -base64 64 > cluster.key
```

#### Step 2: create per-node configs

Node 1 (`appsettings.node1.json`, preferred primary):

```json
{
  "Aouda": {
    "Port": 5001,
    "DataPath": "./data-node1",
    "ReplicaSet": {
      "Name": "local-rs",
      "Members": [
        "127.0.0.1:5001",
        "127.0.0.1:5002",
        "127.0.0.1:5003"
      ],
      "KeyFile": "./cluster.key",
      "ReplicationPort": 5433,
      "HeartbeatIntervalMs": 2000,
      "ElectionTimeoutMs": 10000,
      "ThisNode": {
        "Address": "127.0.0.1:5001",
        "Priority": 10,
        "Hidden": false,
        "Backup": false
      }
    }
  }
}
```

Node 2 (`appsettings.node2.json`, secondary):

```json
{
  "Aouda": {
    "Port": 5002,
    "DataPath": "./data-node2",
    "ReplicaSet": {
      "Name": "local-rs",
      "Members": [
        "127.0.0.1:5001",
        "127.0.0.1:5002",
        "127.0.0.1:5003"
      ],
      "KeyFile": "./cluster.key",
      "ReplicationPort": 5434,
      "HeartbeatIntervalMs": 2000,
      "ElectionTimeoutMs": 10000,
      "ThisNode": {
        "Address": "127.0.0.1:5002",
        "Priority": 5,
        "Hidden": false,
        "Backup": false
      }
    }
  }
}
```

Node 3 (`appsettings.node3.json`, secondary):

```json
{
  "Aouda": {
    "Port": 5003,
    "DataPath": "./data-node3",
    "ReplicaSet": {
      "Name": "local-rs",
      "Members": [
        "127.0.0.1:5001",
        "127.0.0.1:5002",
        "127.0.0.1:5003"
      ],
      "KeyFile": "./cluster.key",
      "ReplicationPort": 5435,
      "HeartbeatIntervalMs": 2000,
      "ElectionTimeoutMs": 10000,
      "ThisNode": {
        "Address": "127.0.0.1:5003",
        "Priority": 5,
        "Hidden": false,
        "Backup": false
      }
    }
  }
}
```

#### Step 3: start each node

Start each server with its node-specific config using your normal server start command.
Example pattern:

```powershell
dotnet run --project src/Aouda.Server -- --config appsettings.node1.json
dotnet run --project src/Aouda.Server -- --config appsettings.node2.json
dotnet run --project src/Aouda.Server -- --config appsettings.node3.json
```

#### Step 4: verify cluster election and communication

1. Confirm topology from any node:

```http
GET http://127.0.0.1:5001/admin/replication/topology
```

Expected:
- `replicaSetName = "local-rs"`
- exactly one member with `role = "Primary"`
- secondaries present in `members`.

2. Write to primary:

```http
POST http://127.0.0.1:5001/api/databases/appdb/tables/orders/rows
Content-Type: application/json

{
  "database": "appdb",
  "table": "orders",
  "rows": [{ "id": 1, "total": 100.0 }]
}
```

3. Read from secondary explicitly:

```http
POST http://127.0.0.1:5002/api/databases/appdb/query?readPreference=Secondary
Content-Type: application/json

{
  "database": "appdb",
  "table": "orders",
  "select": ["id", "total"],
  "limit": 10
}
```

Expected:
- write succeeds on primary,
- read succeeds on secondary and returns inserted row,
- `GET /admin/replication/status` on secondary shows non-negative lag and `canAcceptWrites=false`.

Common setup mistakes:
- `ThisNode.Address` does not match the exact entry in `Members`.
- Different `KeyFile` content across nodes.
- Mismatched `ReplicaSet.Name`.
- Reused `DataPath` between nodes.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example

```csharp
using Aouda.Client;
using Aouda.Protocol;

await using var client = new AoudaClient("http://localhost:5000", "appdb");

var topology = await client.GetTopologyAsync();
Console.WriteLine($"Primary: {topology?.Primary}");

var status = await client.GetReplicationStatusAsync();
Console.WriteLine($"Role={status?.Role}, LagBytes={status?.LagBytes}");

var rows = await client.GetTable("orders")
    .WithReadPreference(ReadPreference.Secondary)
    .Limit(10)
    .ToListAsync();
```

Expected result: topology/status calls return admin replication information; query includes read preference header and is accepted only if serving node can satisfy the requested preference.

Common mistake: assuming `ReadPreference.SecondaryWithMaxLag` exists in `.NET` protocol enum; it currently does not.

### TypeScript example

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
});

const status = await client.admin.replication.status();
const topology = await client.admin.replication.topology();
const coverage = await client.admin.replication.coverage();

console.log(status.role, topology.primary, Object.keys(coverage.databases));
```

Expected result: TS client fetches status/topology/coverage through `admin.replication`.

Common mistake: expecting TS query builder to expose read preference or write concern options; those are currently missing in TS client APIs.

### HTTP/protocol examples

```http
POST /api/databases/appdb/query?readPreference=Secondary
Content-Type: application/json

{
  "database": "appdb",
  "table": "orders",
  "select": ["id", "total"],
  "limit": 20
}
```

```http
POST /api/databases/appdb/tables/orders/rows
Content-Type: application/json

{
  "database": "appdb",
  "table": "orders",
  "rows": [{ "id": 101, "total": 42.5 }],
  "writeConcern": "majority"
}
```

Expected result: first request is validated against node role/read preference; second request waits for majority ACK (or degrades/fails by timeout policy) and may return `writeConcernStatus`.

Common mistake: passing invalid writeConcern strings (for example `w:majority`) instead of accepted values (`one`, `majority`, `all`).

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Replication status | `AoudaClient.GetReplicationStatusAsync()` | `client.admin.replication.status()` | `GET /admin/replication/status` | Implemented | Surface parity |
| Topology discovery | `AoudaClient.GetTopologyAsync()` | `client.admin.replication.topology()` | `GET /admin/replication/topology` | Implemented | Surface parity |
| Coverage discovery | No first-class method | `client.admin.replication.coverage()` | `GET /admin/replication/coverage` | Partial | .NET gap |
| Query read preference | `RemoteTableQuery.WithReadPreference(...)` | No first-class support | `readPreference` param / `X-Read-Preference` header | Partial | TS gap; server supports HTTP path |
| Hidden replica targeting | `ReadPreference.Hidden` | No first-class support | `readPreference=Hidden` | Partial | TS gap |
| Per-request write concern | No first-class support | No first-class support | `Insert/Update/Delete` `writeConcern` field | Partial | Protocol supports, SDKs lag |
| Write concern result visibility | Raw response DTO only via direct protocol use | Raw transport only | `writeConcernStatus` in mutation responses | Partial | No SDK convenience model |
| Automatic client-side replica routing | Manual preference usage | Manual endpoint usage | n/a | Missing | Planned but unshipped |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| TS query read preferences | TS table/query API option for read preference | Use direct HTTP/transport with query/header | Follow-up after P4 E6 | High |
| SDK write concern options | `.NET`/TS mutation API option for write concern | Use raw HTTP payload with `writeConcern` | Follow-up after P6 E3 | High |
| `.NET` coverage endpoint wrapper | `AoudaClient.GetReplicationCoverageAsync()` | Call raw transport to `/admin/replication/coverage` | Client enhancement task (not yet created) | Medium |
| Lag-threshold read preference inputs | Public request shape for `MaxLagBytes`/`MaxLagSeconds` | Not available; `SecondaryWithMaxLag` acts as role-only check today | Follow-up from P6 E2 | Medium |
| Slot diagnostics endpoint | `/admin/replication/slots` and per-slot lag metrics | Infer indirectly from logs/counters | P4 I4 follow-up notes | Medium |
| Specific named-replica targeting | `Specific` read preference + target member input | Route request directly to chosen node URL | ADR 0010 future scope | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First clustered rollout (3-node baseline)

When to use:
- Initial production deployment of basic primary/secondary replication.

Steps:
1. Configure the same `ReplicaSet.Name` and full `Members` list on all nodes.
2. Set each node `ThisNode.Address`; keep one node with highest `Priority`.
3. Configure `KeyFile` on all nodes.
4. Start servers and call:
   - `GET /admin/replication/topology`
   - `GET /admin/replication/status` on each node.

Expected result checks:
- Exactly one primary appears in topology.
- Secondary nodes report non-negative lag and `CanAcceptWrites=false`.
- Read candidates exclude hidden/backup members.

### Scenario 2: Hidden analytics replica

When to use:
- Dedicated analytics/reporting node should not receive default read traffic.

Steps:
1. Set analytics node config:
   - `ThisNode.Hidden=true`
   - `ThisNode.Priority=0`
2. Restart that node.
3. Validate:
   - `GET /admin/replication/topology` shows `isHidden=true`.
4. Query that node:
   - once with default read preference,
   - once with `readPreference=Hidden`.

Expected result checks:
- Default read returns `421 Misdirected Request`.
- Explicit `Hidden` preference succeeds.
- Hidden node is absent from `ReadCandidates`.

### Scenario 3: Write concern hardening for critical tables

When to use:
- A subset of writes requires stronger cross-node durability guarantees.

Steps:
1. Set DB default write concern to `Majority` for critical DB.
2. Optionally set table durability overrides for specific hot-path tables.
3. For selected requests, send per-write override (`writeConcern=all`) via HTTP.
4. Monitor timeout/degradation counters and API response `writeConcernStatus`.

Expected result checks:
- `writeConcernStatus` appears for concern > `one`.
- Under healthy conditions, `acksReceived >= acksRequired`.
- Timeout behavior matches config (`Fail` or degrade mode).

### Scenario 4: Subscription-based replica traffic reduction

When to use:
- Replicas should consume only selected DB/table subsets.

Steps:
1. Set `ThisNode.Subscriptions` for secondaries using `All`/`Include`/`Exclude`.
2. Restart secondary to apply subscription changes.
3. Inspect `GET /admin/replication/coverage`.

Expected result checks:
- Coverage table subscriber counts match subscription intent.
- Warnings appear for replicated tables with zero subscribers.
- Replication traffic counters reflect filtered frames.

## 2.13 Operations and observability

Monitor first:

- Topology and role health:
  - `GET /admin/replication/topology`
  - `GET /admin/replication/status`
  - Health endpoint replication component status
- Lag and stream behavior:
  - `SubscriptionLagMs`
  - `ReplicationPerDbLagMaxBytes`
  - `ReplicationHeartbeatsWithDbPositions`
- Subscription and filtering:
  - `ReplicationDatabaseSubscriptions`
  - `ReplicationFramesFilteredDatabase`
  - `ReplicationFramesFilteredTableSubscription`
- Write concern outcomes:
  - `WriteConcernWaitsTotal`
  - `WriteConcernSuccessful`
  - `WriteConcernTimeouts`
  - `WriteConcernDegradations`
  - `WriteConcernFailures`
- WAL lifecycle and retention interaction:
  - `ReplicationSlotsCreatedTotal`
  - `ReplicationSlotUpdatesTotal`
  - `ReplicationSlotReconnectsTotal`
  - `WalSlotMinPosition`

Recovery/restart expectations:

- Replica set config changes require restart.
- Secondary reconnect should resume from retained slot position when possible.
- If WAL history is unavailable, checkpoint bootstrap path is used.

Suggested tuning sequence:
1. Stabilize replica set membership, keyfile auth, and role behavior first.
2. Tune write concern defaults (`One` -> `Majority`) for critical DBs.
3. Apply per-table subscriptions to reduce unnecessary replica traffic.
4. Tune health thresholds for operational alerting sensitivity.

| Question | Practical answer |
|---|---|
| Which endpoint tells me who can serve reads? | `GET /admin/replication/topology` (`readCandidates`) |
| How do I check if secondaries are behind per database? | `GET /admin/replication/status` (`perDatabaseLag`) |
| Why is write latency suddenly higher? | Check write concern level and `WriteConcernWait*` counters |
| How do I detect stale-primary write attempts? | Look for fencing token conflicts (`409 STALE_FENCING_TOKEN`) |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Writes return `503 READ_ONLY` | Request hit non-primary node | Route writes to current primary; inspect topology |
| Writes return `409 STALE_FENCING_TOKEN` | Client token is stale after failover | Refresh token/state and target current primary |
| Query returns `421 Misdirected Request` | Requested read preference not satisfiable on node | Use topology read candidates or adjust preference |
| Hidden node does not serve default reads | Expected behavior (`Hidden` requires explicit preference) | Query with `readPreference=Hidden` only for hidden workloads |
| `writeConcern=majority` frequently degrades | Insufficient ACK quorum or timeout too short | Check subscriber counts, lag, timeout config |
| Secondary repeatedly reboots/catches up via checkpoint | WAL retention boundary too aggressive or prolonged disconnect | Inspect slots/retention settings and replica stability |
| Coverage warns "replicated but no subscriber" | Table is replicated but all secondaries filtered it out | Adjust `Subscriptions` include/exclude rules |
| Health endpoint marks replication degraded | Lag exceeds configured threshold | Check per-db lag, network path, and replica load |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Engine replication suite | `dotnet test tests/Aouda.Engine.Replication.Tests --no-build --verbosity minimal` | Pass (`586/586`) | 2026-03-31 | Includes streaming, election, replay, write concern, per-db/per-table routing |
| Server replication/read-preference suite | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~ReplicationIntegrationTests|FullyQualifiedName~QueryReadPreferenceTests|FullyQualifiedName~HiddenReplicaQueryTests|FullyQualifiedName~ReplicationControllerTests" --verbosity minimal` | Pass (`39/39`) | 2026-03-31 | Validates admin APIs, role behavior, read preference enforcement |
| TypeScript admin replication bindings | `npm test -- tests/admin.test.ts` (in `../aouda-client-ts`) | Pass (`20/20`) | 2026-03-31 | Validates TS `admin.replication` client contract |
| Historical harness replication scenarios | `P7-Task7-ReplicationScenarios-Report.md` results | Skip-by-design (historical) | 2026-03-31 review | Reported skips are now partially stale versus current server capabilities |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| WAL streaming protocol and transport behavior | `WalStreamProtocolTests.cs`, `WalStreamIntegrationTests.cs`, `WalStreamProtocolV2Tests.cs`, `WalStreamProtocolV3Tests.cs` | Pass | Strong | Covers v1/v2/v3 encode/decode, auth, CRC, integration |
| Checkpoint bootstrap flow | `CheckpointProtocolTests.cs`, `CheckpointCoordinatorTests.cs`, `CheckpointTransferTests.cs` | Pass | Strong | Includes atomic apply and corruption checks |
| Election and failover mechanics | `ElectionManagerTests.cs`, `ClusterIntegrationTests.cs`, `FailureDetectorTests.cs`, `FencingGuardTests.cs` | Pass | Strong | Priority, quorum, fencing, transitions |
| Replica replay and ordering correctness | `ReplicaStateMachine*` tests | Pass | Medium/Strong | Includes out-of-order and transaction frame handling |
| Read preference and hidden behavior | `QueryReadPreferenceTests.cs`, `HiddenReplicaQueryTests.cs` | Pass | Strong | Includes 421 paths and hidden explicit reads |
| Admin status/topology/coverage endpoints | `ReplicationIntegrationTests.cs`, `ReplicationControllerTests.cs` | Pass | Medium/Strong | Contract and wiring behavior covered |
| Write concern waiting and timeout behavior | `PendingWriteTrackerTests.cs`, `WriteConcernServiceTests.cs`, `WriteConcernConfigTests.cs` | Pass | Strong | Quorum math, timeout behavior, config validation |
| TS admin replication client surface | `../aouda-client-ts/tests/admin.test.ts` | Pass | Medium | Contract-level tests, not server E2E |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| Multi-process failover scenario still not validated end-to-end in harness style | Most realistic operator scenario (kill primary, promote, continue writes) | Add process-level integration test that boots 3 servers with real `ReplicaSet` config and validates failover continuity | High |
| No dedicated API test for slot inspection endpoints (because endpoint is absent) | Operators cannot audit slot lag/positions directly | Add `/admin/replication/slots` endpoint + controller tests + TS client tests | High |
| TS client lacks read preference query support tests (feature absent) | Causes API parity drift and manual HTTP workarounds | Add TS query API option + integration tests against read preference behavior | High |
| SDK write concern request/response model not covered (feature absent in SDK APIs) | Limits adoption of durable writes from SDK workflows | Add typed SDK writeConcern options and response mapping tests in `.NET` and TS clients | High |
| `SecondaryWithMaxLag` endpoint behavior not threshold-validated | Feature appears available by enum but threshold path is not externally usable | Add explicit server tests for lag-threshold request shape after API is introduced | Medium |

## 2.18 Known gaps and undone work

_Updated 2026-04-08 after P16 completion._

### Resolved gaps

- ~~Dynamic cluster membership~~ — ✅ **Resolved (P16 Epic A, task A.3)**: full cluster lifecycle REST APIs at `/admin/cluster/` — join, leave, promote, failover, drain, config. Runtime cluster state persists to `cluster-state.json`. Join-on-startup via `--join` CLI flag. See `docs/tasks/P16/P16-SA3-Cluster-Lifecycle-APIs-And-Witness.md`.
- ~~Witness/arbiter node role~~ — ✅ **Resolved (P16 Epic A, task A.8)**: `NodeConfig.Arbiter = true`, participates in elections but stores no data. CLI: `--role witness`. Enables 1+1+witness automatic failover.
- ~~Cloud control plane orchestration~~ — ✅ **Resolved (P16 Epics F)**: Hub control plane with `IClusterProvisioner`, K8s operator reconciling `AoudaCluster` CRD objects. See `docs/tasks/P16/P16-Completion-Report.md` §7.
- ~~No first-class cluster management from Studio~~ — ✅ **Resolved (P16 Epic C)**: Studio cluster ops (add/remove node, promote, failover), topology visualization, node detail views.
- ~~No Kubernetes deployment~~ — ✅ **Resolved (P16 Epic E)**: Helm chart (`charts/aouda-cluster/`) with StatefulSet, automatic replication bootstrap, witness support. See `docs/dev/Functionality-Cloud-And-Hub.md` §5.

### Remaining gaps

- BL-024 is stale relative to current server capabilities: treat as harness/process-testing debt.
- Per-database checkpoint sync remains partial (first available engine for checkpoint transfer).
- API parity gaps:
  - TS query read preference support missing.
  - `.NET`/TS write concern request ergonomics missing.
- Slot observability gaps: no first-class endpoint to inspect slot positions and lag.
- Planned architecture items from ADR 0010 that remain unshipped:
  - mTLS, named replica targeting, temperature-aware read routing.

## 2.19 References

- ADRs:
  - `docs/decisions/0010-cluster-membership-replication.md`
  - `docs/decisions/0016-wal-lifecycle-management.md`
- Tasks/reports:
  - `docs/tasks/P4/P4-EpicE-Task0-ClusterFoundation-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task1-WalStreamingProtocol-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task2-CheckpointSync-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task3-ReplicaStateMachine-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task4-HeartbeatLeaderElection-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task5-WorkloadSpecializedReplicas-Report.md`
  - `docs/tasks/P4/P4-EpicE-Task6-HiddenReplicasReadPreferences-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task1-WalSlotInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task3-RetentionWorker-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task4-ReplicationIntegration-Report.md`
  - `docs/tasks/P4/P4-EpicI-Task5-BackupIntegration-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task1-PerDatabaseWalReplication-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task2-ClusterTopologyDatabaseAwareness-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task3-WriteConcernSynchronousReplication-Report.md`
  - `docs/tasks/P6/P6-EpicE-Task4-PerTableReplicationRouting-Report.md`
  - `docs/tasks/P7/P7-Task7-ReplicationScenarios-Report.md`
- Backlog:
  - `docs/BACKLOG.md` (BL-024)
- Code paths:
  - `src/Aouda.Engine.Replication/ReplicaSetConfig.cs`
  - `src/Aouda.Engine.Replication/NodeConfig.cs`
  - `src/Aouda.Engine.Replication/ReadPreference.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamServer.cs`
  - `src/Aouda.Engine.Replication/Streaming/WalStreamClient.cs`
  - `src/Aouda.Engine.Replication/Replay/ReplicaStateMachine.cs`
  - `src/Aouda.Server/Startup/ReplicationHostedService.cs`
  - `src/Aouda.Server/Controllers/ReplicationController.cs`
  - `src/Aouda.Server/Controllers/QueryController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Services/WriteConcernService.cs`
  - `src/Aouda.Server/Middleware/WriteGuardFilter.cs`
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/ProtocolConstants.cs`
  - `src/Aouda.Client/AoudaClient.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `../aouda-client-ts/src/admin/replication.ts`
  - `../aouda-client-ts/src/admin/replication-types.ts`
- Tests:
  - `tests/Aouda.Engine.Replication.Tests/`
  - `tests/Aouda.Server.Tests/ReplicationIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/QueryReadPreferenceTests.cs`
  - `tests/Aouda.Server.Tests/HiddenReplicaQueryTests.cs`
  - `tests/Aouda.Server.Tests/ReplicationControllerTests.cs`
  - `../aouda-client-ts/tests/admin.test.ts`

## 2.20 What is missing from this document? (meta completeness)

- This document does not include complete multi-node deployment manifests (container/Kubernetes examples); it focuses on implementation behavior and API/config truth.
- This document calls out stale backlog drift (BL-024) but does not update backlog entries itself.
- Client ergonomics for write concern and lag-aware read preference thresholds are documented as missing; once SDK/API surfaces land, sections `2.10` and `2.11` should be updated immediately.
