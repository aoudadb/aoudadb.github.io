---
title: "Partitioning and Multi-tenancy"
nav_order: 10
parent: "Guides"
---

# Aouda Functionality: Partitioning and Multitenancy

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

Coverage phases: P4, P6, P7, P12, P14
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P6/`, `docs/tasks/P7/`, `docs/tasks/P12/`, `docs/tasks/P14/`
Primary ADRs: `docs/decisions/0009-partitioning-multitenancy.md`, `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Auth-And-Authorization.md`, `docs/dev/Functionality-Storage-And-Persistence.md`

## Start Here

If your question is "How do I use partitioning and multitenancy right now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Partitioning and multitenancy exist to make a single Aouda deployment practical for many independent workloads without giving up correctness or operational control.

- User problem solved:
  - Isolate tenant/workload data with partition keys and explicit query scoping rules.
  - Host multiple logical databases under one server process while preserving isolation.
  - Keep read/write APIs explicit about the database boundary (no accidental cross-database routing).
- Operational outcomes:
  - Better storage layout for skewed tenant distributions (`Auto`, `Shared`, `Dedicated`).
  - Per-database lifecycle, memory budgets, health, and metrics.
  - Clear security envelope: database-level routing plus PLS/ADRA controls for partition access.
- Scope boundaries:
  - This document covers partition key modeling, partition storage/routing/enforcement, database isolation/routing, and partition-level authorization interactions.
  - It does not claim fully shipped "all-language parity" for every advanced admin/security surface.
  - It does not claim all retrospective-partitioning phase-2 strategies are production-wired.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What defaults apply if I do nothing? | `2.3 Defaults and zero-config behavior` |
| What is shipped vs planned vs reserved? | `2.4 Availability status` |
| Which phase delivered which capability? | `2.5 Phase coverage matrix` |
| Overall feature completeness | `2.6 Capability coverage matrix` |
| How partitioning and multidb fit together conceptually | `2.7 Core concepts and mental model` |
| Runtime implementation paths | `2.8 How Aouda implements it` |
| Full setting and option surface | `2.10 Configuration and settings reference` |
| .NET / TypeScript / HTTP coverage | `2.11 API and CLI coverage reference` |
| Operator guidance and diagnostics | `2.13 Operations and observability`, `2.14 Troubleshooting by symptom` |
| Explicit undone work | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.3`, `2.11`, `2.12` |
| Platform operator / DBA | `2.10`, `2.13`, `2.14`, `2.18` |
| SDK maintainer (.NET/TS) | `2.11`, `2.16`, `2.17` |
| Engine contributor | `2.5`, `2.6`, `2.8`, `2.19` |

### Source map

- Task/report evidence:
  - `docs/tasks/P4/P4-EpicF-Task1-PartitionStorageInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicF-Task2-PartitionQueryEnforcement-Report.md`
  - `docs/tasks/P4/P4-EpicF-Task3-AutoPromotionSharedPartitions-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL005-RetrospectivePartitioning-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task2-DatabaseRegistryAndMetadata-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task3-DatabaseManager-Report.md`
  - `docs/tasks/P6/P6-EpicB-Task1-ServerStartupAndDatabaseScopedRoutes-Report.md`
  - `docs/tasks/P6/P6-EpicB-Task3-ServerConfigurationForMultipleDatabases-Report.md`
  - `docs/tasks/P6/P6-EpicC-Task1-WireProtocolDatabaseField-Report.md`
  - `docs/tasks/P6/P6-EpicC-Task2-CSharpClientMultiDatabase-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task2-PerDatabaseMonitoringAndMetrics-Report.md`
  - `docs/tasks/P7/P7-Task8-MultiDatabaseScenarios-Report.md`
  - `docs/tasks/P12/P12-TaskG1-PLSFlagAndConfiguration-Report.md`
  - `docs/tasks/P12/P12-TaskG2-PlsEnforcement-TokenClaimToPartitionRouting-Report.md`
  - `docs/tasks/P12/P12-TaskG3-PlsCrossPartitionAccessControl-Report.md`
  - `docs/tasks/P12/P12-TaskG4-PlsCrossPartitionRateLimiting-Report.md`
  - `docs/tasks/P14/P14-TaskS4-EnhancedPLS.md`
  - `docs/tasks/P14/P14-ADRA-Tasks.md`
- Design references:
  - `docs/decisions/0009-partitioning-multitenancy.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
- Core code:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Catalog/CatalogModels.cs`
  - `src/Aouda.Engine.Api/Query/PartitionEnforcer.cs`
  - `src/Aouda.Engine.Api/Query/PartitionKeyExtractor.cs`
  - `src/Aouda.Engine.Api/TableQuery.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionRouter.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionVolumeTracker.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionPromoter.cs`
  - `src/Aouda.Engine.Storage/Registry/DatabaseRegistry.cs`
  - `src/Aouda.Engine.Api/DatabaseManager.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/QueryController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptions.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigSection.cs`
- Client code:
  - `.NET`: `src/Aouda.Client/RemoteTableQuery.cs`
  - TypeScript: `../aouda-client-ts/src/client.ts`, `../aouda-client-ts/src/query-builder.ts`, `../aouda-client-ts/src/tables.ts`, `../aouda-client-ts/src/databases.ts`
- Test evidence:
  - `tests/Aouda.Engine.Api.Tests/TableQueryPartitionTests.cs`
  - `tests/Aouda.Server.Tests/PartitionEnforcementIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/NestedPartitionIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/PLS/PartitionSecurityEnforcerTests.cs`
  - `tests/Aouda.Testing.Tests/AoudaTestServer_MultiDatabase.cs`

## 2.3 Defaults and zero-config behavior

If you create a table/database without tuning partition or multidb options:

- Partitioning:
  - No partition key means standard non-partitioned storage path.
  - If partitioned, `PartitionOptions` defaults are active (`StorageMode = Auto`, `RequirePartitionFilter = true`, promotion thresholds enabled, late-arrival defaults set).
- Query safety:
  - Partition-filter enforcement is on by default for partitioned tables unless explicitly disabled.
  - Cross-partition reads require explicit opt-in (`crossPartitionAccess` / `.WithCrossPartitionAccess()` in supported clients).
- Multitenancy:
  - Database-scoped HTTP routes are the default API shape.
  - Database creation defaults to WAL enabled, replication mode `Replicate`, default temperature `Auto`.
  - Per-database memory cap is unlimited unless configured (`MaxMemoryBytes = null`).

| Setting / behavior | Default | Allowed values | Practical impact |
|---|---|---|---|
| `PartitionOptions.StorageMode` | `Auto` | `Auto`, `Dedicated`, `Shared` | Starts shared, can promote heavy partitions to dedicated paths |
| `PartitionOptions.RequirePartitionFilter` | `true` | `true`, `false` | Safer and usually faster partitioned-table queries by default |
| `PartitionOptions.PromotionRowThreshold` | `10_000_000` | Non-negative integer | Auto-promotion can trigger at high row volume |
| `PartitionOptions.PromotionByteThreshold` | `1_000_000_000` | Non-negative integer (bytes) | Auto-promotion can trigger at high byte volume |
| `PartitionOptions.InitialBucketCount` | `16` | Integer ≥ 1 | Shared-partition hashing starts with 16 buckets |
| `PartitionOptions.LateArrivalPolicy` | `Delta` | `Delta`, `Reject`, `Inline` | Late-arriving rows are routed to delta path |
| `PartitionOptions.LateArrivalThreshold` | `1 hour` | Any positive `TimeSpan` | Defines "late" cutoff when policy needs it |
| `MigrationOptions.Strategy` | `None` | `None`, `Background`, `Eager`, `Blocking` | Retrospective migration is off unless configured |
| `DatabaseOptions.DefaultTemperature` | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` | New tables in that DB inherit auto temperature |
| `DatabaseOptions.EnableWal` | `true` | `true`, `false` | DB has WAL enabled unless explicitly disabled |
| `DatabaseOptions.ReplicationMode` | `Replicate` | `Replicate`, `DoNotReplicate` | DB participates in replication by default |
| `DatabaseOptions.MaxMemoryBytes` | `null` | `null` (no cap); or any non-negative `long` (bytes) | No explicit per-database cap unless set |
| `PlsCrossPartitionRateLimitOptions.Enabled` | `false` | `true`, `false` | Cross-partition bypass rate limiting is opt-in |
| `PlsCrossPartitionRateLimitOptions.PermitLimit` | `60` | Positive integer | Effective only when limiter is enabled |
| `PlsCrossPartitionRateLimitOptions.WindowSeconds` | `60` | Positive integer (seconds) | Effective only when limiter is enabled |

## 2.4 Availability status (implementation honesty)

### Available now

- Partition key model:
  - Composite partition keys via `PartitionKeyOrder`.
  - Partition metadata persisted in catalog models.
- Partition storage/routing:
  - `PartitionStorage` modes (`Auto`, `Dedicated`, `Shared`).
  - Nested partition directory routing and shared-bucket hashing (`XxHash64`).
  - Auto-promotion pipeline with queue/in-progress tracking and WAL hooks.
- Partition query enforcement:
  - Partition-filter required by default for partitioned tables.
  - Explicit cross-partition bypass flag in protocol and .NET fluent APIs.
- Multi-database architecture:
  - `DatabaseRegistry` persisted metadata under server scope.
  - `DatabaseManager` runtime engine-per-database orchestration.
  - Database-scoped server routes (`/api/databases/{db}/...`) for data and schema operations.
  - Required `database` field in database-scoped protocol messages.
- Per-database operations:
  - Per-db options (`MaxMemoryBytes`, temperature default, WAL, replication mode) through startup config and create-db API.
  - Per-db memory coordination and server memory view.
  - Per-db monitoring/health surfaces from P6.
- PLS interaction:
  - `partitionLevelSecurity` table option and validation.
  - `jwt-claim` mode enforcement and controlled bypasses.
  - Cross-partition bypass rate limiter (configurable).
  - Query-level audit logging for cross-partition and service-key bypass events.
- ADRA bridge behavior:
  - Unified enforcer dispatches by `AuthorizationMode`.
  - `auth-db-pls` query/write enforcement paths are implemented for permission-context-driven partition grants.

### Planned / proposed

- Full ADRA/RLS deepening beyond current shipped baseline is still tracked under P14 follow-ups.
- Broader SDK parity for advanced partition-security admin and complex query-shape helpers remains iterative.
- Additional ergonomics around retrospective partition migration operations are expected after initial BL-005 delivery.

### Reserved / not yet wired

- `MigrationStrategy.Eager` and `MigrationStrategy.Blocking` are defined as phase-2 strategy intents in policy types but not claimed as fully wired end-to-end production behavior.
- `MigrationOptions.MaxParallelism` and `MigrationOptions.BlockingTimeout` are explicitly marked phase-2 properties.
- TypeScript fluent query builder currently has no first-class cross-partition toggle method; it cannot set `crossPartitionAccess` directly even though protocol and server support it.
- PLS helper awareness for `WhereClause.Groups` is still backlog-tracked (`BL-044`), not complete.
- Service-key PLS bypass audit logging for DML (insert/update/delete) is implemented in `TablesController` (BL-041, 2026-04-04).

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P4 | Epic F Task1/2/3 reports, Epic G BL005 report | Partition metadata model, storage router, query enforcement, auto-promotion, retrospective partitioning baseline | Advanced retrospective migration strategy wiring (phase-2 strategy intents) | `docs/BACKLOG.md` (retrospective follow-up context + BL-044 related helper scope) |
| P6 | Epic A/B/C/F reports | Multi-database registry/manager/routes, database field in protocol, client multidb wiring, per-db config/memory/metrics | Further API ergonomics and parity surfaces continue in follow-up work | `docs/BACKLOG.md` |
| P7 | `P7-Task8-MultiDatabaseScenarios-Report.md` | Scenario validation of multi-db lifecycle, isolation, WAL recovery, memory budget, route behavior | Some scenario breadth noted as partial in report (table durability override limitations) | `docs/BACKLOG.md` |
| P12 | Task G1/G2/G3/G4 reports | PLS flag + jwt-claim enforcement, admin cross-partition bypass, bypass rate limiting and query audit path | DML service-key bypass audit delivered in P14 BL-041 | `docs/tasks/P14/BL-041-ServiceKeyPlsBypassAudit-DML.md` |
| P14 | `P14-ADRA-Tasks.md`, `P14-TaskS4-EnhancedPLS.md` | Unified enforcer dispatch and auth-db-pls permission-context path, safer OR/fan-out handling model | Ongoing ADRA hardening and full ecosystem parity | `docs/BACKLOG.md` BL-044 (+ future ADRA tasks) |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Composite partition key declaration (`PartitionKeyOrder`) | Yes | No | No | P4 F1 report + `CatalogModels.cs` + schema DTOs | Works for single and multi-column partition keys |
| Partition storage modes (`Auto`/`Dedicated`/`Shared`) | Yes | No | No | P4 F1 report + `Policies.cs` + `PartitionRouter.cs` | Publicly configurable in create-table protocol field |
| Shared-bucket routing + nested dedicated paths | Yes | No | No | `PartitionRouter.cs` + P4 F1 report | Dedicated path supports multi-level directories |
| Auto-promotion shared -> dedicated | Yes | No | No | P4 F3 report + `PartitionVolumeTracker.cs` + `PartitionPromoter.cs` | Queue/in-progress/wal-callback flow implemented |
| Partition-filter-required query guard | Yes | No | No | P4 F2 report + `PartitionEnforcer.cs` + `TableQuery.cs` | Default safety on partitioned tables |
| Explicit cross-partition query opt-in | Yes | No | No | `QueryMessage.CrossPartitionAccess`, `.WithCrossPartitionAccess()` in engine/.NET client | TypeScript fluent surface gap remains |
| Retrospective partitioning baseline | Yes | Yes | No | P4 BL005 report + policy model | Strategy surface exists; some strategy fields remain phase-2 intent |
| Multi-database registry and lifecycle state machine | Yes | No | No | P6 A2 report + `DatabaseRegistry.cs` | Persistent registry with create/drop transitions |
| Multi-engine routing per database | Yes | No | No | P6 A3 report + `DatabaseManager.cs` | One active engine per active database |
| Database-scoped HTTP routes | Yes | No | No | P6 B1 report + server controllers | Flat pre-P6 routes removed from primary path |
| Required `database` field in protocol requests | Yes | No | No | P6 C1 report + `Messages.cs` + `TableMessages.cs` | Guarded by route/body consistency checks |
| Per-db config and startup auto-provisioning | Yes | No | No | P6 B3 report + `AoudaServerOptions.cs` + `DatabaseConfigSection.cs` | Supports memory/temp/WAL/replication config keys |
| Per-db memory budget coordination | Yes | No | No | P6 F1 report + server memory manager wiring | Works with server-wide cap model |
| Partition-level security (`partitionLevelSecurity`) | Yes | No | No | P12 G1 report + schema/model fields | Valid only for partitioned tables |
| jwt-claim PLS enforcement | Yes | No | No | P12 G2 report + `PartitionSecurityEnforcer.cs` | Injects/validates partition scope from claim |
| Admin cross-partition bypass + query audit | Yes | No | No | P12 G3 report + `QueryController.cs` | Includes query-level audit action |
| Cross-partition bypass rate limiting | Yes | No | No | P12 G4 report + limiter classes | Per identity + database sliding-window limiter |
| auth-db-pls enforcement path | Yes | No | No | P14 S4 task + `PartitionSecurityEnforcer.cs` | PermissionContext-driven grant routing |
| DML service-key bypass audit logging | Yes | No | No | `PartitionSecurityEnforcer.cs` + `QueryController.cs` + `TablesController.cs` + BL-041 task | Query and DML paths emit `service_key_pls_bypass` when applicable |
| PLS helper support for `WhereClause.Groups` | No | Yes | No | `Messages.cs` + `PartitionSecurityEnforcer.cs` + BL-044 | Server has groups in protocol; helper logic not fully groups-aware |
| TypeScript fluent cross-partition toggle | No | No | Yes | `../aouda-client-ts/src/query-builder.ts` | No `withCrossPartitionAccess()` in current TS query builder |

## 2.7 Core concepts and mental model

- Database boundary:
  - A Aouda server hosts multiple named databases; each database has its own catalog/tables/WAL area and runtime engine instance.
- Partition boundary:
  - A partitioned table groups rows by one or more partition key columns (`PartitionKeyOrder`).
- Storage mode:
  - `Dedicated`: each partition gets its own directory.
  - `Shared`: partitions hash to shared buckets.
  - `Auto`: starts shared and promotes high-volume partitions to dedicated.
- Query safety boundary:
  - Partitioned-table queries usually must include full partition-key equality filters unless explicit cross-partition access is requested.
- Security boundary:
  - PLS adds identity-derived partition scoping on top of query enforcement.
  - ADRA (`auth-db-pls`) extends this from single-claim matching to permission-context grant sets.
- Runtime invariants:
  - Route database must match body database for scoped request DTOs.
  - Partition enforcement decisions occur before table query execution.
  - Cross-partition bypasses are explicit and observable (audit/rate-limiter paths).

## 2.8 How Aouda implements it

High-level architecture path:

1. Server route resolves `{db}` and validates protocol body `database`.
2. `DatabaseManager` resolves the target engine for that database.
3. Query/mutation paths use catalog metadata (`TableEntry`, partition options, auth mode).
4. Partition enforcement runs (query-level and, for PLS, auth-level scope checks/injection).
5. Storage routing resolves physical partition paths (`PartitionRouter`) and promotion workflow (`PartitionPromoter`) as data volume evolves.

Core modules:

- Partition metadata and defaults:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Catalog/CatalogModels.cs`
- Query enforcement:
  - `src/Aouda.Engine.Api/Query/PartitionEnforcer.cs`
  - `src/Aouda.Engine.Api/Query/PartitionKeyExtractor.cs`
  - `src/Aouda.Engine.Api/TableQuery.cs`
- Partition storage/autopromotion:
  - `src/Aouda.Engine.Storage/Partition/PartitionRouter.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionVolumeTracker.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionPromoter.cs`
- Multidb engine orchestration:
  - `src/Aouda.Engine.Storage/Registry/DatabaseRegistry.cs`
  - `src/Aouda.Engine.Api/DatabaseManager.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
- Security and query endpoint integration:
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
  - `src/Aouda.Server/Controllers/QueryController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
- Protocol/DTO contracts:
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Partitioned query enforcement path

1. Entry point: `TableQuery.ToResultAsync()` / `ToColumnarAsync()` / `AggregateAsync()`.
2. `ValidatePartitionEnforcement()` resolves predicate and calls `PartitionEnforcer.Validate(...)`.
3. Decision branches:
   - Not partitioned -> valid.
   - `RequirePartitionFilter == false` -> valid.
   - `crossPartitionAccess == true` -> valid cross-partition.
   - Otherwise requires equality filters for all partition key columns.
4. Failure path throws `PartitionFilterRequiredException`.
5. Observability: cross-partition executions increment `Perf.CrossPartitionQueries`.
6. Test anchors: `tests/Aouda.Engine.Api.Tests/TableQueryPartitionTests.cs`, `tests/Aouda.Server.Tests/PartitionEnforcementIntegrationTests.cs`.

### Walk-through B: Shared partition auto-promotion to dedicated storage

1. Entry path: writes/query signals are recorded in `PartitionVolumeTracker`.
2. `PartitionPromoter.ShouldPromote(...)` evaluates row/byte thresholds when storage mode is `Auto`.
3. Promotion is queued; `BeginPromotionAsync(...)` transitions state:
   - removes queue entry,
   - creates dedicated directory path,
   - records in-progress state,
   - calls `OnBeginPromotion` WAL callback when configured.
4. `CompletePromotionAsync(...)` persists completion via callback and updates counters.
5. State mutation outcome: partition can be treated as dedicated in catalog/router.
6. Test anchors: partition promotion behavior covered by P4 Task3 report and storage/path integration tests including `tests/Aouda.Server.Tests/NestedPartitionIntegrationTests.cs`.

### Walk-through C: Database-scoped query HTTP path with PLS controls

1. Entry point: `POST /api/databases/{db}/query` in `QueryController.ExecuteQuery`.
2. Controller validates request shape:
   - body `database` required,
   - body `database` must match route `{db}`.
3. Engine resolution: `DatabaseManager` resolves `{db}` engine.
4. Security scope:
   - `PartitionSecurityEnforcer.EnforceQueryScope(...)` applies jwt-claim or auth-db-pls mode.
   - `RlsPredicateInjector` can add row-level predicates for auth-db-rls mode tables.
5. Cross-partition bypass path:
   - if bypass used, optional rate limiter is applied,
   - audit record is written for cross-partition query or service-key bypass.
6. Query translation and execution proceeds through `TableQuery`.
7. Test anchors: `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`, `tests/Aouda.Engine.Auth.Tests/PLS/PartitionSecurityEnforcerTests.cs`.

### Walk-through D: Database create + engine bootstrap path

1. Entry point: `POST /api/databases` in `DatabasesController.CreateDatabase`.
2. Request validation parses replication mode, default temperature, memory constraints.
3. `DatabaseManager.CreateDatabaseAsync(...)` runs lifecycle under mutation lock:
   - registry create (`Creating -> Active`) with persisted metadata,
   - directory layout creation,
   - engine open using derived budget options,
   - engine registration in manager and server budget coordinator.
4. Optional auth-linking path can bind application DB to auth DB.
5. Response returns database metadata and options.
6. Test anchors: `tests/Aouda.Testing.Tests/AoudaTestServer_MultiDatabase.cs`, P6/P7 reports.

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Is partition safety "best effort" or enforced by default? | Often advisory patterns or optional optimizer hints | Default partition-filter enforcement (`RequirePartitionFilter = true`) with explicit bypass | Fewer accidental full-partition scans; safer multi-tenant access patterns |
| Can one server host many isolated DBs without hidden global coupling? | Varies; some systems are single-db engines with external orchestration | First-class `DatabaseRegistry` + `DatabaseManager` with per-db engines and routes | Cleaner tenant/workload isolation inside one Aouda server |
| How explicit is database routing in API contracts? | Some APIs infer db from connection/session context | Database-scoped routes plus required body `database` fields | Lower risk of wrong-db writes/queries |
| How does partition storage adapt to skew? | Static partition strategy is common | `Auto` mode with tracked volume thresholds and promotion to dedicated storage | Better balance for mixed-size tenant populations |
| Is partition auth only token-claim matching? | Frequently app-layer only | Unified PLS enforcer supports jwt claim and auth-db grant resolution | Built-in upgrade path from basic to dynamic partition authorization |

## 2.10 Configuration and settings reference (complete surface)

{: .note }
**Precedence:** [Server configuration](server-configuration.md) — startup config (code defaults, optional appsettings, `AOUDA_*`, CLI).

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `CreateColumnRequest.partitionKeyOrder` | int? | `null` | positive ordinal | table create payload | Declares column as partition key and order in composite key |
| `CreateTableRequest.partitionStorage` | string? | `null` (engine uses `Auto`) | `Auto`, `Dedicated`, `Shared` | table create payload | Controls partition storage mode |
| `PartitionOptions.StorageMode` | enum | `Auto` | `Auto`, `Dedicated`, `Shared` | catalog policy | Core partition routing mode |
| `PartitionOptions.RequirePartitionFilter` | bool | `true` | `true/false` | catalog policy | Query guard for partitioned tables |
| `PartitionOptions.PromotionRowThreshold` | long | `10_000_000` | `>= 0` | catalog policy | Auto-promotion row trigger |
| `PartitionOptions.PromotionByteThreshold` | long | `1_000_000_000` | `>= 0` | catalog policy | Auto-promotion byte trigger |
| `PartitionOptions.InitialBucketCount` | int | `16` | `>= 1` | catalog policy | Shared mode initial bucket fanout |
| `PartitionOptions.LateArrivalPolicy` | enum | `Delta` | `Delta`, `Reject`, `Inline` | catalog policy | Late-arrival strategy |
| `PartitionOptions.LateArrivalThreshold` | `TimeSpan` | `1h` | positive | catalog policy | Late-arrival time boundary |
| `PartitionOptions.Migration` | `MigrationOptions?` | `null` | object/null | catalog policy | Retrospective partition migration config |
| `MigrationOptions.Strategy` | enum | `None` | `None`, `Background`, `Eager`, `Blocking` | migration config | `Eager`/`Blocking` are phase-2 strategy intents |
| `MigrationOptions.BatchSize` | int | `100_000` | positive | migration config | Background migration batch size |
| `MigrationOptions.BatchDelay` | `TimeSpan` | `10s` | non-negative | migration config | Delay between background batches |
| `MigrationOptions.MaxIoBandwidthPercent` | int | `15` | positive | migration config | Background migration IO pressure cap |
| `MigrationOptions.MaxParallelism` | int | `2` | positive | migration config | Marked phase-2 only |
| `MigrationOptions.BlockingTimeout` | `TimeSpan` | `1h` | positive | migration config | Marked phase-2 only |
| `Aouda:Databases:{db}:MaxMemoryBytes` | long? | `null` | null or non-negative | startup config | Per-db memory cap |
| `Aouda:Databases:{db}:DefaultTemperature` | string | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` | startup config | Default table temperature in DB |
| `Aouda:Databases:{db}:EnableWal` | bool | `true` | `true/false` | startup config | Per-db WAL default |
| `Aouda:Databases:{db}:ReplicationMode` | string | `Replicate` | `Replicate`, `DoNotReplicate` | startup config | Per-db replication mode |
| `Aouda:Databases:{db}:WriteConcern` | string | `One` | `One`, `Majority`, `All` | startup config | Per-db write concern |
| `Aouda:Databases:{db}:WriteConcernTimeoutMs` | int | `5000` | positive | startup config | Per-db write concern timeout |
| `Aouda:Databases:{db}:OnWriteConcernTimeout` | string | `DegradeAndLog` | `Fail`, `Degrade`, `DegradeAndLog` | startup config | Per-db timeout behavior |
| `CreateDatabaseRequest.enableWal` | bool | `true` | `true/false` | create-db API | DB create-time operational setting |
| `CreateDatabaseRequest.replicationMode` | string | `Replicate` | `Replicate`, `DoNotReplicate` | create-db API | DB create-time operational setting |
| `CreateDatabaseRequest.maxMemoryBytes` | long? | `null` | null or non-negative | create-db API | DB create-time memory cap |
| `CreateDatabaseRequest.defaultTemperature` | string? | `null` (`Auto` in options) | `Auto`, `HotOnly`, `ColdPreferred` | create-db API | DB create-time default table temp |
| `Aouda:PlsCrossPartitionRateLimit:Enabled` | bool | `false` | `true/false` | server config | Enables limiter for bypassed cross-partition queries |
| `Aouda:PlsCrossPartitionRateLimit:PermitLimit` | int | `60` | positive | server config | Max requests/window per (identity, db) |
| `Aouda:PlsCrossPartitionRateLimit:WindowSeconds` | int | `60` | positive | server config | Limiter window size |

Precedence and operational notes:

- Precedence:
  - Route `{db}` plus required body `database` define request scope at runtime.
  - Table-level partition settings override database defaults for table behavior.
  - Request-level `crossPartitionAccess` can only bypass query partition-filter requirement; it does not bypass authorization unless allowed by auth mode/rules.
- Dynamic vs restart-required:
  - `Aouda:Databases` and limiter config are startup-loaded server configuration (treat as restart-required).
  - Table partition options and table auth mode updates are runtime API operations.
- Safety-gated settings:
  - Database name validation rejects invalid/reserved names.
  - Route/body database mismatch is rejected.
  - Partitioned query without required filter is rejected unless explicit bypass.
- Deprecated/reserved:
  - Migration phase-2 fields (`MaxParallelism`, `BlockingTimeout`) are defined but not fully wired behavior.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (database-scoped query with explicit cross-partition access)

```csharp
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5000",
    DatabaseName = "appdb",
});

var rows = await client
    .GetTable("orders")
    .WithCrossPartitionAccess()
    .Where("status", "eq", "open")
    .ToListAsync();
```

Expected result: query can run on a partitioned table without explicit partition key filter because cross-partition access is explicitly requested.

Common mistake: using cross-partition access for all app traffic; this should stay an admin/analytics exception path.

### TypeScript example (multidb + partitioned query)

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
});

await client.databases.create("tenantdb", { maxMemoryBytes: 536870912 });

const orders = await client
  .table("orders")
  .where("tenant_id", "=", "tenant-a")
  .where("status", "=", "open")
  .execute();
```

Expected result: request is sent to `/api/databases/appdb/query` with explicit `database` in body and partition-safe filter.

Common mistake: expecting a TS fluent `withCrossPartitionAccess()` helper; current TS query builder does not expose this toggle.

### HTTP/protocol examples

```http
POST /api/databases/appdb/tables
Content-Type: application/json

{
  "database": "appdb",
  "name": "orders",
  "columns": [
    { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
    { "name": "tenant_id", "type": "String", "partitionKeyOrder": 1 },
    { "name": "status", "type": "String" }
  ],
  "partitionStorage": "Auto",
  "partitionLevelSecurity": true,
  "authMode": "jwt-claim"
}
```

```http
POST /api/databases/appdb/query
Content-Type: application/json

{
  "database": "appdb",
  "table": "orders",
  "where": {
    "and": [
      { "column": "tenant_id", "op": "eq", "value": "tenant-a" }
    ]
  }
}
```

Expected result: table is created with partition + PLS settings, and query executes within partition scope.

Common mistake: omitting `database` in request body or mismatching route/body database.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Create partitioned table (partition key + storage mode) | Table create DTOs / schema APIs | `tables.createTable(...)` with partition fields | `POST /api/databases/{db}/tables` | Implemented | End-to-end available |
| Query partitioned table with required filters | Fluent query APIs | `table(...).where(...).execute()` | `POST /api/databases/{db}/query` | Implemented | Guarded by server/engine partition enforcement |
| Explicit cross-partition query opt-in | `.WithCrossPartitionAccess()` (`RemoteTableQuery`, `TableQuery`) | No dedicated fluent method | `QueryMessage.crossPartitionAccess = true` | Partial | TS surface gap |
| Database CRUD | `.Databases` client surface (P6 C2) | `client.databases.list/create/get/drop` | `/api/databases` endpoints | Implemented | Database-scoped operations shipped |
| Database-scoped data/schema routes | .NET client routes with `DatabaseName` | Client paths built from configured `database` | `/api/databases/{db}/...` | Implemented | Flat route era replaced |
| PLS table configuration | table options DTOs | table create/update payload fields supported | table create/update options endpoints | Implemented | Includes `partitionLevelSecurity`, `authMode`, etc. |
| auth-db-pls runtime enforcement | server/engine internal | server/engine internal | query path enforcement in controller/enforcer | Implemented | Requires PermissionContext path |
| Cross-partition bypass rate limiting | server internal | server internal | 429 from query endpoint when limited | Implemented | Config gated (`Enabled=false` by default) |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| TypeScript fluent cross-partition toggle | `table(...).withCrossPartitionAccess()` equivalent | Use partition filters; no direct TS fluent bypass support today | Future TS SDK parity work | High |
| Full PLS helper support for `WhereClause.Groups` | Enforcer helper extraction methods ignore groups | Keep top-level `and`/`or` for partition conditions | `docs/BACKLOG.md` BL-044 | Medium |
| Full retrospective migration strategy parity | `Eager`/`Blocking` strategy intent fields not fully wired as shipped behavior | Use `None`/`Background` baseline behavior | P4 BL005 phase-2 follow-up work | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run partitioned table with safety defaults

When to use:
- new table in a multitenant app where accidental broad scans must be prevented.

Steps:
1. Create table with `partitionKeyOrder` on `tenant_id`, no explicit partition options.
2. Insert rows for two tenants.
3. Run query without tenant filter.
4. Run query with tenant filter.

Expected result checks:
- Unfiltered query is rejected with partition-filter-required error.
- Filtered query succeeds and returns only requested partition rows.

### Scenario 2: Create and route multiple databases safely

When to use:
- one server hosts multiple isolated app environments or tenants.

Steps:
1. `POST /api/databases` for `app_a` and `app_b`.
2. Create same table name in both databases.
3. Insert distinct rows per database.
4. Query each database route independently.

Expected result checks:
- Data does not bleed across databases.
- Route/body database mismatch requests are rejected.
- Database list endpoint reports both as active.

### Scenario 3: Controlled cross-partition admin query with limiter

When to use:
- admin analytics requires temporary fan-out reads across many partitions.

Steps:
1. Enable `Aouda:PlsCrossPartitionRateLimit` in config (`Enabled=true`).
2. Send query with `crossPartitionAccess=true` as authorized admin.
3. Repeat rapidly above permit threshold.

Expected result checks:
- Initial requests succeed.
- Excess requests return 429 with retry-after semantics.
- Audit entries are written for cross-partition bypass actions.

## 2.13 Operations and observability

Monitor first:

- Database lifecycle and routing:
  - DB create/drop success/failure rates
  - database resolution errors (`DatabaseNotFound`/mismatch paths)
- Partitioning behavior:
  - partition promotion queue depth / in-progress counts
  - dedicated partition growth and promotion byte counters
- Query enforcement and bypass:
  - partition-filter-required rejections
  - cross-partition bypass counts
  - 429 rate-limiter events for bypass traffic
- Security-audit signals:
  - `query_cross_partition` and `service_key_pls_bypass` actions in auth audit table (query and DML `TablesController` paths)
- Per-database resource signals:
  - server memory endpoint per-db snapshots
  - per-db metrics/health endpoints from P6 monitoring work

Recovery expectations:

- Database registry state is persisted; startup rehydrates active DBs and performs creating-state cleanup.
- Partition layout metadata persists through catalog and partition registry paths.
- In-progress promotion paths use callback hooks designed for WAL recording/recovery workflows.

Suggested tuning sequence:

1. Start with partition filter requirement enabled and explicit tenant filters in app queries.
2. Choose `Auto` partition storage first unless workload shape is clearly known.
3. Add per-db memory caps when multiple high-volume databases share one server.
4. Enable cross-partition limiter before granting broad admin bypass usage.

| Question | Practical answer |
|---|---|
| How do I quickly confirm DB isolation? | Create same table name in two DBs and verify query results differ per route |
| How do I confirm partition query safety is active? | Run an unfiltered query on a partitioned table and verify it is rejected |
| What should I monitor before enabling cross-partition admin analytics? | Bypass audit volume and limiter hit rate per identity/database |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `400` saying body database must match path database | Route/body mismatch | Ensure request body `database` equals `/api/databases/{db}` segment |
| Query on partitioned table fails with partition filter required | Missing full partition-key equality filters and no bypass | Add required partition key filters or use explicit cross-partition access where allowed |
| Cross-partition admin queries suddenly return 429 | Rate limiter enabled and threshold exceeded | Reduce request rate, widen window/permit settings, or retry after suggested delay |
| Service key writes bypass PLS but no corresponding audit entries | Should not occur after BL-041 | Confirm `_audit_log` contains `service_key_pls_bypass` for the database/table; see integration tests in `PartitionLevelSecurityEnforcementIntegrationTests` |
| PLS behavior seems odd with nested/grouped filter shapes | `WhereClause.Groups` helper adoption gap | Keep partition conditions in top-level `and`/`or` until BL-044 work lands |
| TypeScript app cannot request explicit cross-partition query | TS fluent SDK missing toggle | Use partition filters; track SDK parity enhancement |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Documentation/code alignment audit for partition + multidb + PLS sources | N/A (source and report audit pass) | Pass | 2026-03-31 | Validated defaults, route shapes, protocol fields, and enforcer paths against current code |
| Partition query enforcement behavior | N/A (test evidence referenced) | Not run in this doc pass | 2026-03-31 | Covered by `TableQueryPartitionTests` and `PartitionEnforcementIntegrationTests` |
| PLS bypass/rate-limit/audit behavior | N/A (test evidence referenced) | Not run in this doc pass | 2026-03-31 | Covered by P12 reports and enforcement tests listed in section 2.16 |
| Multi-database lifecycle/isolation scenarios | N/A (test evidence referenced) | Not run in this doc pass | 2026-03-31 | Covered by P7 scenario report and multi-db testing suites |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Partition key filter enforcement and bypass | `tests/Aouda.Engine.Api.Tests/TableQueryPartitionTests.cs`, `tests/Aouda.Server.Tests/PartitionEnforcementIntegrationTests.cs` | Pass (historical/phase evidence) | Strong | Covers required-filter and cross-partition execution paths |
| Partition storage path behavior (including nested paths) | `tests/Aouda.Server.Tests/NestedPartitionIntegrationTests.cs` | Pass (historical/phase evidence) | Medium/Strong | Validates nested partition routing semantics |
| PLS query and bypass enforcement | `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`, `tests/Aouda.Engine.Auth.Tests/PLS/PartitionSecurityEnforcerTests.cs` | Pass (historical/phase evidence) | Strong | Includes jwt-claim and auth-db-pls logic branches |
| Multi-database lifecycle and isolation scenarios | `tests/Aouda.Testing.Tests/AoudaTestServer_MultiDatabase.cs` + P7 scenario report | Pass (historical/phase evidence) | Medium/Strong | Covers create/list/drop/isolation/recovery classes of behavior |
| Protocol serialization for database-scoped messages | `tests/Aouda.Protocol.Tests/SerializationTests.cs` | Pass (historical/phase evidence) | Medium | Verifies DTO field serialization contracts |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No explicit TS client test for cross-partition flag because fluent API is missing | SDK parity and documentation correctness risk | Add TS API once implemented, then contract test for emitted `crossPartitionAccess` | High |
| Limited explicit tests for `WhereClause.Groups` with PLS helper extraction | Complex query-shape correctness risk | Add group-aware PLS helper tests as part of BL-044 | Medium |
| Retrospective migration phase-2 strategy behavior not covered end-to-end | Operators may assume Eager/Blocking are fully active | Add strategy-specific integration tests once those paths are fully wired | Medium |

## 2.18 Known gaps and undone work

- BL-044 (open):
  - `WhereClause.Groups` adoption is incomplete across clients and PLS helper extraction logic.
  - User impact: complex grouped predicates can hit unsupported/less ergonomic partition-security behavior.
- TypeScript fluent parity gap:
  - TS query builder currently lacks explicit cross-partition toggle method.
  - User impact: TS consumers must stay with partition filters and cannot explicitly request cross-partition query bypass in fluent API.
- Retrospective partitioning phase-2 strategy gap:
  - `Eager`/`Blocking` strategy fields are defined but not documented as fully shipped behavior.
  - User impact: treat these as reserved/planned rather than production-ready guarantees.

## 2.19 References

- ADRs:
  - `docs/decisions/0009-partitioning-multitenancy.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
- Task docs/reports:
  - `docs/tasks/P4/P4-EpicF-Task1-PartitionStorageInfrastructure.md`
  - `docs/tasks/P4/P4-EpicF-Task1-PartitionStorageInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicF-Task2-PartitionQueryEnforcement.md`
  - `docs/tasks/P4/P4-EpicF-Task2-PartitionQueryEnforcement-Report.md`
  - `docs/tasks/P4/P4-EpicF-Task3-AutoPromotionSharedPartitions.md`
  - `docs/tasks/P4/P4-EpicF-Task3-AutoPromotionSharedPartitions-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL005-RetrospectivePartitioning.md`
  - `docs/tasks/P4/P4-EpicG-BL005-RetrospectivePartitioning-Report.md`
  - `docs/tasks/P6/P6-MultiDatabase-Analysis-And-Tasks.md`
  - `docs/tasks/P6/P6-EpicA-Task2-DatabaseRegistryAndMetadata-Report.md`
  - `docs/tasks/P6/P6-EpicA-Task3-DatabaseManager-Report.md`
  - `docs/tasks/P6/P6-EpicB-Task1-ServerStartupAndDatabaseScopedRoutes-Report.md`
  - `docs/tasks/P6/P6-EpicB-Task3-ServerConfigurationForMultipleDatabases-Report.md`
  - `docs/tasks/P6/P6-EpicC-Task1-WireProtocolDatabaseField-Report.md`
  - `docs/tasks/P6/P6-EpicC-Task2-CSharpClientMultiDatabase-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task2-PerDatabaseMonitoringAndMetrics-Report.md`
  - `docs/tasks/P7/P7-Task8-MultiDatabaseScenarios-Report.md`
  - `docs/tasks/P12/P12-TaskG1-PLSFlagAndConfiguration-Report.md`
  - `docs/tasks/P12/P12-TaskG2-PlsEnforcement-TokenClaimToPartitionRouting-Report.md`
  - `docs/tasks/P12/P12-TaskG3-PlsCrossPartitionAccessControl-Report.md`
  - `docs/tasks/P12/P12-TaskG4-PlsCrossPartitionRateLimiting-Report.md`
  - `docs/tasks/P14/P14-ADRA-Tasks.md`
  - `docs/tasks/P14/P14-TaskS4-EnhancedPLS.md`
- Backlog:
  - `docs/BACKLOG.md` (`BL-044`)
  - `docs/tasks/P14/BL-041-ServiceKeyPlsBypassAudit-DML.md`
- Code:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Catalog/CatalogModels.cs`
  - `src/Aouda.Engine.Api/Query/PartitionEnforcer.cs`
  - `src/Aouda.Engine.Api/Query/PartitionKeyExtractor.cs`
  - `src/Aouda.Engine.Api/TableQuery.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionRouter.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionVolumeTracker.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionPromoter.cs`
  - `src/Aouda.Engine.Storage/Registry/DatabaseRegistry.cs`
  - `src/Aouda.Engine.Api/DatabaseManager.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Controllers/QueryController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
  - `src/Aouda.Protocol/Messages.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptions.cs`
  - `src/Aouda.Server/Configuration/DatabaseConfigSection.cs`
  - `src/Aouda.Server/Configuration/PlsCrossPartitionRateLimitOptions.cs`
  - `src/Aouda.Server/Auth/PlsCrossPartitionRateLimiter.cs`
  - `src/Aouda.Client/RemoteTableQuery.cs`
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/query-builder.ts`
  - `../aouda-client-ts/src/tables.ts`
  - `../aouda-client-ts/src/databases.ts`
- Tests:
  - `tests/Aouda.Engine.Api.Tests/TableQueryPartitionTests.cs`
  - `tests/Aouda.Server.Tests/PartitionEnforcementIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/NestedPartitionIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/PLS/PartitionSecurityEnforcerTests.cs`
  - `tests/Aouda.Protocol.Tests/SerializationTests.cs`
  - `tests/Aouda.Testing.Tests/AoudaTestServer_MultiDatabase.cs`

## 2.20 What is missing from this document? (meta completeness)

- This document is capability-complete at feature level, but it does not enumerate every DTO property for every server/client method.
- Verification ledger is evidence-referenced rather than fresh command execution in this doc-writing pass.
- If TypeScript adds explicit cross-partition query support, section `2.11` and the missing API matrix must be updated immediately.
- If BL-044 is completed, sections `2.4`, `2.17`, and `2.18` should be updated in the same PR as the code changes. (BL-041 updates landed 2026-04-04.)
