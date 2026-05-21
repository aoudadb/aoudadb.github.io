---
title: "Hot/Cold Storage"
nav_order: 5
parent: "Guides"
---

# Aouda Functionality: Hot/Cold Storage and Memory Control

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-03-31

Coverage phases: P3, P6, P7
Primary task folders: `docs/tasks/P3/`, `docs/tasks/P6/`, `docs/tasks/P7/`
Primary ADRs: `docs/decisions/0007-hot-vs-cold-storage.md`, `docs/decisions/0011-memory-prioritization.md`, `docs/decisions/0012-memory-footprint-reduction.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-RealTime-Streaming.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How do I use hot/cold and memory controls now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
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

Aouda treats data temperature and memory pressure as first-class behavior rather than hidden buffer-pool internals.

- User problem solved:
  - Keep active data fast without keeping all data uncompressed in RAM forever.
  - Make memory behavior explainable and tunable with explicit policy.
- Operational outcomes:
  - Predictable hot/cold transitions for sealed segments.
  - Better memory containment at table/database/server levels.
  - Production visibility through counters, inspectors, health checks, and server memory endpoint.
- Scope boundaries:
  - This domain covers storage temperature (`Auto`, `HotOnly`, `ColdPreferred`), promotion/demotion, and memory budgeting.
  - It does not include full ADR 0011/0012 advanced memory-intent features (for example `HotRetention`, `LatestPerKey`, hot encoding tiers) as shipped features.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What defaults apply if I do nothing? | `2.3 Defaults and zero-config behavior` |
| What is shipped vs planned vs reserved? | `2.4 Availability status` |
| Which phase delivered which capability? | `2.5 Phase coverage matrix` |
| End-to-end feature completeness | `2.6 Capability coverage matrix` |
| Runtime concepts and invariants | `2.7 Core concepts and mental model` |
| How it is implemented in engine/server | `2.8 How Aouda implements it` |
| Full config and where to set it | `2.10 Configuration and settings reference` |
| API coverage and missing surfaces | `2.11 API and CLI coverage reference` |
| Which paths are verified today | `2.15 Verification ledger`, `2.16 Test coverage matrix` |
| What remains undone | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.11 API and CLI coverage reference`, `2.12 Scenario playbooks` |
| Operator/SRE | `2.10 Configuration and settings reference`, `2.13 Operations and observability`, `2.14 Troubleshooting by symptom` |
| SDK maintainer | `2.11 API and CLI coverage reference`, `2.17 Testing gaps and proposed tests`, `2.18 Known gaps and undone work` |
| Engine contributor | `2.5 Phase coverage matrix`, `2.8 How Aouda implements it`, `2.16 Test coverage matrix`, `2.19 References` |

### Source map

- Task/report evidence:
  - `docs/tasks/P3/P3-HotCold-Implementation-Tasks.md`
  - `docs/tasks/P3/P3-Task4-HotToColdDemotion-Report.md`
  - `docs/tasks/P3/P3-Task5-ColdToHotPromotion-Report.md`
  - `docs/tasks/P3/P3-Task8-ManagementAndObservability-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md`
  - `docs/tasks/P7/C3-ColdAwareUpdateDelete-Report.md`
- Core code:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
  - `src/Aouda.Engine.Storage/Residency/ResidencyManager.cs`
  - `src/Aouda.Engine.Storage/Memory/MemoryBudgetOptions.cs`
  - `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Controllers/ServerController.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
- TypeScript client code (cross-repo):
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/tables.ts`
- Test evidence:
  - `tests/Aouda.Engine.Catalog.Tests/HotColdMetadataTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotToColdDemotionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/ColdToHotPromotionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotColdManagementTests.cs`
  - `tests/Aouda.Engine.Api.Tests/PerDatabaseBudgetIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/TablesIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/ServerIntegrationTests.cs`
  - `../aouda-client-ts/tests/admin.test.ts`
  - `../aouda-client-ts/tests/tables.test.ts`

## 2.3 Defaults and zero-config behavior

If you do nothing beyond default server config:

- Table temperature policy defaults to `Auto`.
- New segments start `Hot`.
- Server memory defaults to:
  - `MaxTotalRamBytes = 2147483648` (2 GiB)
  - `MaxHotBytes = 0` (effective 70% of total)
  - `MaxPageCacheBytes = 0` (effective 20% of total)
- Budget target defaults to 90% of total RAM when target is unspecified.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| Table `StorageTemperaturePolicy` | `Auto` | Engine can demote/promote segments using maintenance and access signals |
| Segment temperature on creation | `Hot` | New data is queried on hot path first |
| `Aouda:Memory:MaxTotalRamBytes` | `2 GiB` | Server-wide memory cap baseline |
| `Aouda:Memory:MaxHotBytes` | `0` | Auto-computes effective hot budget as 70% of max total |
| `Aouda:Memory:MaxPageCacheBytes` | `0` | Auto-computes effective cache budget as 20% of max total |
| `MemoryBudgetOptions.TargetRamBytes` | `0` | Effective target is 90% of max total |
| Database `DefaultTemperature` | `Auto` | New tables inherit `Auto` unless table policy overrides |
| `HotColdMaintenanceWorkerOptions` | `SweepInterval=5s`, `AutoHotByteBudgetBytes=64MiB`, `PromotionAccessThreshold=3` | Internal maintenance defaults when worker is active |
| Default compaction trigger | Size-driven only (`MaxBufferedRowsPerTable=200 K`, `MaxBufferedBytesPerTable=64 MB`); `CompactionInterval=0` | No wall-clock time trigger; data stays in HRA until a size threshold is crossed |
| `MinFlushRows` / `MinFlushBytes` floor | `1 000 rows` / `1 MB` | A compaction trigger that fires while data is below both floors is suppressed; the table stays hot. Bypassed by memory-pressure `FlushUrgent`, page-merge maintenance, and shutdown drain. |

## 2.4 Availability status (implementation honesty)

### Available now

- Temperature model:
  - `StorageTemperaturePolicy` (`Auto`, `HotOnly`, `ColdPreferred`)
  - `SegmentTemperature` (`Hot`, `Cold`)
- Promotion/demotion lifecycle:
  - Hot->cold demotion pipeline with catalog durability updates and diagnostics.
  - Cold->hot promotion pipeline with access-triggered and policy-triggered promotion.
- Query/read correctness over mixed hot/cold:
  - Query paths consult segment temperature and deletion-mask correctness fixes are in place.
- Management and observability:
  - `HotColdInspector` APIs for listing, health checks, bulk operations, JSON outputs.
  - Perf counters for hot/cold, promotion/demotion, and memory budget actions.
- Memory governance:
  - Per-engine `MemoryBudgetManager` wired to hot registry and table policy/name lookups.
  - Server-level coordination via `ServerMemoryBudgetManager` and `/api/server/memory`.
- Public policy APIs:
  - REST/Protocol + TypeScript client support table create/update for `storageTemperature`.

### Planned / proposed

From ADR intent and follow-up planning, not shipped as end-to-end behavior:

- Rich memory intent declarations from ADR 0011 (for example `HotRetention`, `HotRowLimit`, `LatestPerKey`, query memory protection).
- Advanced hot footprint optimizations from ADR 0012 (for example hot encoding strategy tiers as productized table options).
- Broader HTTP/SDK management APIs for explicit promote/demote and full residency policy shaping.

### Reserved / not yet wired

- `ResidencyPolicy.MemoryFilter`
- `ResidencyPolicy.MemoryRowCap`
- `ResidencyPolicy.TargetMemoryBytes`

These are defined in catalog policy types, but runtime enforcement and protocol/SDK write surfaces are not shipped. `ResidencyManagerV1` explicitly only honors `PinAllInMemory`.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P3 | `P3-HotCold-Implementation-Tasks.md`, Task 4/5/8 reports | Temperature metadata, demotion/promotion pipelines, maintenance worker behavior, management and observability APIs | Advanced heuristics and richer productized memory-intent controls deferred | `docs/BACKLOG.md` (see BL-054 for residency filtering) |
| P6 | `P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md` | Per-database memory budgeting, server memory coordinator, `/api/server/memory`, health integration | Cross-database page-cache sharing and richer per-db metrics labeling deferred | `docs/BACKLOG.md` BL-001 marked complete; future enhancements tracked in later tasks |
| P7 | `C3-ColdAwareUpdateDelete-Report.md` + correctness reports | Cold-aware mutation correctness hardened via deletion masks across query paths | Further optimization of cold mutation paths may continue separately | No new hot/cold backlog item created by C3 report |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Table-level storage temperature (`Auto`/`HotOnly`/`ColdPreferred`) | Yes | No | No | P3 Task 1 report, `Policies.cs`, tables integration tests | Fully available across catalog + protocol + TS client |
| Segment temperature persistence (`Hot`/`Cold`) | Yes | No | No | P3 Task reports, `Policies.cs`, `HotColdMetadataTests` | Preserved through restart semantics |
| Hot->cold demotion | Yes | No | No | P3 Task 4 report, `SegmentDemoter`, demotion tests | Includes policy-driven demotion and diagnostics |
| Cold->hot promotion | Yes | No | No | P3 Task 5 report, `SegmentPromoter`, promotion tests | Includes access-triggered promotion path |
| Maintenance worker policy automation | Yes | No | No | `HotColdMaintenanceWorker.cs`, P3 reports/tests | Auto/HotOnly/ColdPreferred handled |
| Hot/cold management inspection surface | Yes | No | No | P3 Task 8 report, `HotColdInspector.cs` | Rich .NET surface, no equivalent first-class HTTP endpoints |
| Per-database memory budget coordination | Yes | No | No | P6 F1 report, `ServerMemoryBudgetManager.cs`, integration tests | Server-level cap + per-db snapshots |
| Table policy `PinAllInMemory` runtime handling | Yes | No | No | `Policies.cs`, `ResidencyManager.cs`, tests | Implemented in V1 residency manager |
| Filter-based partial residency (`MemoryFilter`, row cap, target bytes) | No | No | Yes | `Policies.cs` + `ResidencyManagerV1` + BL-054 | Explicitly reserved, not wired end-to-end |
| Public API for explicit promote/demote operations | No | Yes | No | .NET inspector APIs only | Missing in protocol/HTTP and TS SDK |

## 2.7 Core concepts and mental model

- `StorageTemperaturePolicy`:
  - Table-level intent controlling default residency behavior.
- `SegmentTemperature`:
  - Actual per-segment state (`Hot` or `Cold`) used by execution and maintenance.
- Hot segment:
  - Raw vectors, lowest decode overhead, higher memory pressure risk.
- Cold segment:
  - Encoded/compressed representation, lower memory footprint, decode cost on access.
- Demotion:
  - Transition from hot to cold, catalog and storage metadata updated.
- Promotion:
  - Transition from cold to hot when policy/access conditions justify.
- Memory governance layers:
  - Per-engine `MemoryBudgetManager` + server-level `ServerMemoryBudgetManager`.

Invariants:

- Temperature is not inferred only from file type; it is explicit in catalog metadata.
- Demotion/promotion are explicit transitions, not implicit process-lifecycle side effects.
- Reserved residency fields must not be treated as available controls until engine + API support exists.

## 2.8 How Aouda implements it

High-level flow:

1. Writes enter HRA/WAL path and produce hot segments at flush.
2. Maintenance worker evaluates policy and budget state.
3. Demoter/promotion pipelines move sealed segments between representations.
4. Query paths choose hot vs cold execution path using catalog/registry state.
5. Memory managers track usage and trigger pressure actions.

Key implementation anchors:

- Catalog policy/types:
  - `src/Aouda.Engine.Catalog/Policies.cs`
- Temperature operations:
  - `src/Aouda.Engine.Storage/HotCold/SegmentDemoter.cs`
  - `src/Aouda.Engine.Storage/HotCold/SegmentPromoter.cs`
  - `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
- Diagnostics/ops:
  - `src/Aouda.Engine.Storage/HotColdInspector.cs`
  - `src/Aouda.Engine.Diagnostics/Perf.cs`
- Memory governance:
  - `src/Aouda.Engine.Storage/Memory/MemoryBudgetOptions.cs`
  - `src/Aouda.Engine.Storage/Memory/MemoryBudgetManager.cs`
  - `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs`
  - `src/Aouda.Server/Controllers/ServerController.cs`
- API surfaces:
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Hot -> Cold demotion path

1. `HotColdMaintenanceWorker.RunOnceAsync()` evaluates each table and applies policy/budget logic.
2. If `ColdPreferred` or budget pressure applies, it calls `SegmentDemoter.DemoteAsync(...)`.
3. `SegmentDemoter` validates segment eligibility:
   - segment exists,
   - segment is sealed,
   - segment is not already cold,
   - pinned segments require force.
4. It resolves/builds a cold manifest (`EnsureColdSegmentAsync`).
5. It updates catalog temperature to cold.
6. It unregisters hot segment handles and keeps/uses cold representation.
7. It records diagnostics/counters (`Perf.SegmentDemotions`, `Perf.SegmentDemotionBytes`).

Primary code anchors:

- `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
- `src/Aouda.Engine.Storage/HotCold/SegmentDemoter.cs`

Primary proving tests:

- `tests/Aouda.Engine.Storage.Tests/HotToColdDemotionTests.cs`
- `tests/Aouda.Engine.Storage.Tests/HotColdManagementTests.cs`

### Walk-through B: Cold -> Hot promotion path

1. Promotion can be triggered by:
   - `HotOnly` policy reconciliation,
   - access-threshold promotion in `Auto`,
   - manual inspector operations.
2. `SegmentPromoter.PromoteAsync(...)` checks:
   - already-hot short-circuit,
   - segment existence/sealed state,
   - table definition availability.
3. It resolves/rebuilds cold manifest if needed.
4. It decodes cold pages to typed column arrays (`DecodeColumnsAsync` / `DecodeColumnAsync`).
5. It registers hot segment handles.
6. It optionally updates catalog temperature (depending on call options).
7. It updates counters (`Perf.SegmentPromotions`, `Perf.SegmentPromotionBytes`, access-triggered counters).

Primary code anchors:

- `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
- `src/Aouda.Engine.Storage/HotCold/SegmentPromoter.cs`

Primary proving tests:

- `tests/Aouda.Engine.Storage.Tests/ColdToHotPromotionTests.cs`
- `tests/Aouda.Engine.Storage.Tests/HotColdManagementTests.cs`

### Walk-through C: Policy update API path (HTTP -> catalog)

1. `PUT /api/databases/{db}/tables/{name}/policy` enters `TablesController.UpdatePolicy(...)`.
2. Controller validates request-body `database` matches route database.
3. Controller validates `storageTemperature` enum string (`Auto`, `HotOnly`, `ColdPreferred`).
4. Engine is resolved for `{db}`.
5. Catalog `SetTablePolicyAsync(...)` applies policy update.
6. Response returns updated policy payload.

Primary code anchors:

- `src/Aouda.Server/Controllers/TablesController.cs`
- `src/Aouda.Engine.Catalog/CatalogApi.cs`
- `src/Aouda.Protocol/Schema/TableMessages.cs`

Primary proving tests:

- `tests/Aouda.Server.Tests/TablesIntegrationTests.cs` (`UpdatePolicy_*` tests)
- `../aouda-client-ts/tests/tables.test.ts` (client binding contract)

### Walk-through D: Server memory endpoint path

1. `GET /api/server/memory` enters `ServerController.GetMemoryUsage()`.
2. Controller pulls snapshot from `ServerMemoryBudgetManager.GetServerUsage()`.
3. Snapshot is transformed to protocol response DTO (`ServerMemoryResponse` + per-db records).
4. Response is returned as JSON to HTTP/SDK consumers.

Primary code anchors:

- `src/Aouda.Server/Controllers/ServerController.cs`
- `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs`
- `src/Aouda.Engine.Api/ServerMemoryUsageSnapshot.cs`

Primary proving tests:

- `tests/Aouda.Server.Tests/ServerIntegrationTests.cs` (`ServerMemory_*` tests)
- `../aouda-client-ts/tests/admin.test.ts` (`admin.server.memory()` path)

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Can I set explicit hot/cold table behavior? | Often indirect cache tuning only | First-class table temperature policy with explicit enum | More predictable behavior and clearer intent |
| Is temperature durable metadata? | Often inferred from storage format/cache state | Catalog stores segment and table temperature policy directly | Less ambiguity during restart and operations |
| Do I get built-in promotion/demotion management tools? | Often ad-hoc or internal-only | Built-in inspector, health checks, bulk demote/promote APIs in engine surface | Faster incident handling and diagnostics |
| Can I monitor server memory by database? | Often external tooling only | Native `/api/server/memory` and per-database budget coordination | Better multitenant capacity control |
| Are planned features clearly separated from shipped behavior? | Frequently unclear in docs | Reserved/planned surfaces explicitly split and backlog-linked | Lower implementation-risk assumptions |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:Memory:MaxTotalRamBytes` | long | `2147483648` | `>= 1048576` | `appsettings.json`, env, CLI | Server max RAM envelope |
| `Aouda:Memory:MaxHotBytes` | long | `0` | `>= 0` | `appsettings.json`, env, CLI | `0` means 70% of total |
| `Aouda:Memory:MaxPageCacheBytes` | long | `0` | `>= 0` | `appsettings.json`, env, CLI | `0` means 20% of total |
| `Aouda:Databases:{db}:MaxMemoryBytes` | long? | `null` | null or positive | `appsettings.json` | Per-database cap when set |
| `Aouda:Databases:{db}:DefaultTemperature` | string | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` | `appsettings.json` | Default for new tables in that DB |
| `CreateTableRequest.policy.storageTemperature` | string | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` | HTTP create-table body | Per-table policy at creation |
| `UpdatePolicyRequest.storageTemperature` | string | none (required) | `Auto`, `HotOnly`, `ColdPreferred` | HTTP update-policy body | Per-table policy update |
| `ResidencyPolicy.PinAllInMemory` | bool | `false` | `true/false` | Catalog/.NET policy surfaces | Implemented behavior in `ResidencyManagerV1` |
| `ResidencyPolicy.MemoryFilter` | string? | `null` | reserved | Catalog type only | Reserved v2, not wired |
| `ResidencyPolicy.MemoryRowCap` | long? | `null` | reserved | Catalog type only | Reserved v2, not wired |
| `ResidencyPolicy.TargetMemoryBytes` | long? | `null` | reserved | Catalog type only | Reserved v2, not wired |
| `MemoryBudgetOptions.TargetRamBytes` | long | `0` | `>= 0` | Embedded/.NET engine construction | `0` => 90% effective target |
| `MemoryBudgetOptions.EnableEmergencyDemotion` | bool | `false` | `true/false` | Embedded/.NET engine construction | Not exposed via server config keys |
| `MemoryBudgetOptions.StrictMode` | bool | `false` | `true/false` | Embedded/.NET engine construction | Not exposed via server config keys |
| `MemoryBudgetOptions.ActionStartLevel` | enum | `Medium` | pressure-level enum | Embedded/.NET engine construction | Not exposed via server config keys |
| `MemoryBudgetOptions.ActionCooldown` | timespan | `0` | timespan | Embedded/.NET engine construction | Effective default is 1 second |

Configuration precedence and operational notes:

- Precedence:
  - CLI switch mappings override config files.
  - `AOUDA_` environment variables bind into `Aouda` section.
- CLI mappings available for this domain:
  - `--max-memory`, `--max-hot-bytes`, `--max-cache-bytes`
  - short form `-m` for max total memory
- Dynamic vs restart-required:
  - Server memory section is read at startup; treat as restart-required.
  - Table policy via API is dynamic at runtime.
- Safety-gated:
  - Validator rejects invalid ranges and incompatible totals.
- Deprecated/reserved:
  - `MemoryFilter`, `MemoryRowCap`, `TargetMemoryBytes` are reserved and not active.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (embedded engine)

```csharp
var engine = await AoudaEngine.OpenAsync(
    basePath: "./data",
    enableWal: true,
    budgetOptions: new MemoryBudgetOptions(MaxTotalRamBytes: 4L * 1024 * 1024 * 1024));

await engine.CreateTableAsync(
    "orders",
    new[]
    {
        ("id", DataType.Int64, EncoderPreference.Auto, false)
    },
    policy: new TablePolicy { StorageTemperature = StorageTemperaturePolicy.ColdPreferred });
```

Expected result: table is created with `ColdPreferred` policy and engine budget manager enforces memory options.

Common mistake: assuming ADR 0011 memory-intent fields are available through this API path as shipped features.

### TypeScript example

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
});

await client.tables.updatePolicy("orders", {
  storageTemperature: "HotOnly",
});

const mem = await client.admin.server.memory();
console.log(mem.serverTotalBytes, mem.perDatabaseUsage["appdb"]?.pressure);
```

Expected result: table policy updates and server memory snapshot is returned.

Common mistake: expecting `updatePolicy()` to accept residency filter controls (`MemoryFilter`, row caps, target memory).

### HTTP/protocol examples

```http
PUT /api/databases/appdb/tables/orders/policy
Content-Type: application/json

{
  "database": "appdb",
  "storageTemperature": "ColdPreferred"
}
```

```http
GET /api/server/memory
```

Expected result: first call updates table storage temperature; second call returns server/per-db memory usage snapshot.

Common mistake: omitting `database` in request body or sending a body `database` that does not match route `{db}`.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Create table with storage temperature | `AoudaEngine.CreateTableAsync(..., policy)` | `client.tables.createTable({ policy: { storageTemperature } })` | `POST /api/databases/{db}/tables` | Implemented | Full path available |
| Update storage temperature policy | `Catalog.SetTablePolicyAsync(...)` via engine/catalog surface | `client.tables.updatePolicy(...)` | `PUT /api/databases/{db}/tables/{name}/policy` | Implemented | End-to-end shipped |
| Observe hot/cold state and bulk ops | `HotColdInspector.*` | No direct wrapper | No dedicated endpoint | Partial | Available in engine/.NET only |
| Read server + per-db memory budget usage | `ServerMemoryBudgetManager.GetServerUsage()` | `client.admin.server.memory()` | `GET /api/server/memory` | Implemented | Good operator surface |
| Configure advanced `MemoryBudgetOptions` fields | `new MemoryBudgetOptions(...)` in embedded/open APIs | No direct surface | Server config exposes only 3 core memory keys | Partial | Advanced fields are .NET-only currently |
| Configure filter-based partial residency | Type exists only (`ResidencyPolicy` fields reserved) | Not available | Not available in DTOs | Missing | Tracked by BL-054 |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Filter-based partial residency (`MemoryFilter`, row cap, target bytes) | No REST/Protocol/TS/.NET runtime enforcement path | Use coarse policy (`Auto`/`HotOnly`/`ColdPreferred`) and memory budgets | `docs/BACKLOG.md` BL-054 | High |
| Explicit promote/demote admin endpoints | No public HTTP/TS mutation endpoints for these operations | Use `.NET` inspector APIs in embedded/engine contexts | Follow-up tasks after P3 management APIs | Medium |
| Full server-config exposure for advanced memory action ladder knobs | No config keys for `EnableEmergencyDemotion`, `StrictMode`, etc. | Set in embedded `.NET` construction only | Future server configuration hardening tasks | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run baseline (defaults only)

When to use:
- New environment where you want safe default behavior first.

Steps:
1. Keep `Aouda:Memory` at defaults in `appsettings.json`.
2. Create table without explicit policy.
3. Insert workload and run representative reads.
4. Query `/api/server/memory`.

Expected result checks:
- Table policy resolves to `Auto`.
- Server memory endpoint returns non-zero totals as data grows.
- No manual tuning is required for initial correctness/performance baseline.

### Scenario 2: Production-safe policy rollout per table

When to use:
- One table has archival profile and should prefer cold representation.

Steps:
1. Update policy:
   - `PUT /api/databases/{db}/tables/{name}/policy` with `ColdPreferred`.
2. Continue traffic.
3. Monitor counters (`SegmentDemotions`, cold/hot bytes) and health status.

Expected result checks:
- Policy readback shows `ColdPreferred`.
- Over time, demotion counters increment and cold bytes increase.
- Query correctness remains unchanged.

### Scenario 3: Multi-database memory budget control

When to use:
- Shared server with multiple databases where one tenant risks memory starvation.

Steps:
1. Set per-database `MaxMemoryBytes` for key DBs under `Aouda:Databases`.
2. Restart server to apply config.
3. Drive load on multiple DBs.
4. Poll `GET /api/server/memory` and observe per-db pressure.

Expected result checks:
- `perDatabaseUsage` includes each DB with budget and pressure.
- `serverTotalBytes` and `sharedPool*` fields are populated.
- Over-budget conditions become visible and pressure handling counters move.

## 2.13 Operations and observability

Monitor first:

- Hot/cold residency:
  - `HotSegmentCount`, `HotSegmentBytes`, `ColdSegmentCount`, `ColdSegmentBytes`
- Transition activity:
  - `SegmentDemotions`, `SegmentDemotionBytes`, `PolicyDemotions`
  - `SegmentPromotions`, `SegmentPromotionBytes`, `AccessTriggeredPromotions`, `PromotionFailures`
- Budget behavior:
  - `MemoryBudgetTotalBytes`, `MemoryBudgetHotBytes`, `MemoryBudgetCacheBytes`
  - `MemoryBudgetEvictions`, `MemoryBudgetDemotions`, `MemoryBudgetThrottles`
  - `ServerPressureEvaluations`, `ServerPressureEvictionsTriggered`, `ServerPressureEvictionsSucceeded`

Recovery/restart expectations:

- Temperature metadata is persisted; restart should reload consistent state.
- Memory snapshots are runtime state and should be re-established by ongoing activity.

Suggested tuning sequence:
1. Keep table policy at `Auto` and validate workload profile.
2. Set per-database memory caps (`MaxMemoryBytes`) for fairness.
3. Use `ColdPreferred`/`HotOnly` only for tables with clear access patterns.

| Question | Practical answer |
|---|---|
| Which signal confirms migration to colder data is happening? | Rising `SegmentDemotions` and `ColdSegmentBytes` |
| Which API gives immediate server-level memory view? | `GET /api/server/memory` |
| How to avoid over-tuning too early? | Start with defaults and only adjust one control at a time |

For BL-058 troubleshooting, read `CompactionFloorSuppressed` together with adaptive counters: if suppressions rise while `AdaptivePressureFlushes` stays flat, the worker is intentionally keeping sub-floor tables hot under normal conditions. If pressure flushes rise at the same time, bypass paths (`FlushUrgent` / page-merge maintenance) are actively overriding the floor to protect memory or maintenance progress.

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Table policy update returns `400 InvalidRequest` | Invalid `storageTemperature` value or database mismatch between route/body | Use `Auto`, `HotOnly`, or `ColdPreferred`; ensure body `database` matches route |
| Memory appears unbounded for one database | Missing per-db cap (`MaxMemoryBytes` unset) | Add per-db memory cap in config and restart |
| Expected filter-based residency does nothing | Feature is reserved, not wired | Use current shipped controls; track BL-054 |
| Promotions happen but later demotions do not | Policy/budget combination does not force demotion path yet | Verify table policy, budget pressure, and counters; inspect maintenance state |
| Query behavior differs after cold mutations | Deletion-mask/cold mutation path issue | Validate with C3 regression tests and inspect cold segment deletion mask state |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Storage engine broad suite | `dotnet test tests/Aouda.Engine.Storage.Tests --verbosity minimal` | Pass (`2004/2004`) | 2026-03-31 | Includes hot/cold demotion, promotion, management, query-path, counters |
| Engine API broad suite | `dotnet test tests/Aouda.Engine.Api.Tests --no-build --verbosity minimal` | Fail (`1` unrelated failure) | 2026-03-31 | Failure in `MaterializedQueryFlushIntegrationTests`, outside hot/cold scope |
| Engine API targeted hot/cold-relevant budget suite | `dotnet test tests/Aouda.Engine.Api.Tests --no-build --filter "FullyQualifiedName~PerDatabaseBudgetIntegrationTests" --verbosity minimal` | Pass (`10/10`) | 2026-03-31 | Confirms per-db budget/server coordinator integration path |
| Server broad suite | `dotnet test tests/Aouda.Server.Tests --verbosity minimal` | Fail (`2` unrelated failures) | 2026-03-31 | Failures in insert/auth tests, outside hot/cold policy/memory endpoint scope |
| Server targeted policy endpoint | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~UpdatePolicy_" --verbosity minimal` | Pass (`4/4`) | 2026-03-31 | Confirms policy validation and update path |
| Server targeted memory endpoint | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~ServerMemory_" --verbosity minimal` | Pass (`3/3`) | 2026-03-31 | Confirms `/api/server/memory` contract path |
| TypeScript SDK policy/admin surface (cross-repo) | `npm test -- tests/admin.test.ts tests/tables.test.ts` (in `../aouda-client-ts`) | Pass (`68/68`) | 2026-03-31 | Confirms `tables.updatePolicy()` and `admin.server.memory()` client bindings |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Hot->cold demotion lifecycle | `HotToColdDemotionTests.cs` | Pass | Strong | Includes sealed checks, cold manifest rebuild, query fallback, restart semantics |
| Cold->hot promotion lifecycle | `ColdToHotPromotionTests.cs` | Pass | Strong | Includes access-threshold promotion, idempotency, restart persistence, counters |
| Inspector and maintenance/ops reporting | `HotColdManagementTests.cs` | Pass | Strong | Includes health checks, reports, bulk promote/demote, JSON output, counters |
| Policy update HTTP path | `TablesIntegrationTests.cs` (`UpdatePolicy_*`) | Pass | Strong | Covers invalid enum, not found, valid update + readback |
| Server memory endpoint contract | `ServerIntegrationTests.cs` (`ServerMemory_*`) | Pass | Medium/Strong | Covers shape/content-type + DB visibility; limited negative-path assertions |
| Per-db budget integration | `PerDatabaseBudgetIntegrationTests.cs` | Pass | Medium/Strong | Validates coordinator snapshots and wiring with engines |
| TS client policy/admin bindings (cross-repo) | `../aouda-client-ts/tests/tables.test.ts`, `../aouda-client-ts/tests/admin.test.ts` | Pass | Medium | Confirms endpoint invocation/shape; not a full server E2E path |
| Reserved residency fields not active | `ResidencyManagerTests.cs`, `SerializationTests.cs` | Pass | Medium | Positive test for `PinAllInMemory`; no activation tests for reserved fields by design |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No explicit negative server tests for route/body DB mismatch on policy update | Critical validation path for multi-db safety should be explicit | Add `TablesIntegrationTests` case: route `db=A`, body `database=B` -> `400 InvalidRequest` | High |
| No explicit contract test that reserved residency fields are rejected/ignored over HTTP | Prevents users from assuming `MemoryFilter`/row-cap are active | Add server API contract tests proving request payload cannot enable reserved fields | High |
| No explicit cross-surface parity test (.NET policy set -> HTTP readback -> TS readback) | Confirms consistency across engine/server/SDK surfaces | Add integration scenario test spanning catalog update and API/SDK retrieval | Medium |
| No dedicated stress test for promotion/demotion under simultaneous server pressure + access-triggered promotions | Complex path where regressions are likely | Add deterministic stress/integration test with bounded workload and counter assertions | Medium |
| Verification ledger currently manual and doc-maintainer-driven | Risk of stale verification status over time | Add CI job artifact that emits latest hot/cold verification summary and link in doc | Medium |

## 2.18 Known gaps and undone work

- BL-054 (open):
  - Filter-based partial residency (`MemoryFilter`, `MemoryRowCap`, `TargetMemoryBytes`) is not implemented end-to-end.
  - User impact: no row/filter-level residency intent controls yet; only coarse table policy and budget controls.
- ADR 0011/0012 proposed surfaces:
  - Advanced memory-intent and hot-encoding features remain proposed, not shipped as public behavior.
  - User impact: avoid assuming ADR sample APIs exist in current server/SDK surfaces.
- API parity gaps:
  - Promote/demote management is strong in .NET inspector APIs but lacks first-class HTTP/TS mutation routes.

## 2.19 References

- ADRs:
  - `docs/decisions/0007-hot-vs-cold-storage.md`
  - `docs/decisions/0011-memory-prioritization.md` (proposed)
  - `docs/decisions/0012-memory-footprint-reduction.md` (proposed)
- Tasks/reports:
  - `docs/tasks/P3/P3-HotCold-Implementation-Tasks.md`
  - `docs/tasks/P3/P3-Task4-HotToColdDemotion-Report.md`
  - `docs/tasks/P3/P3-Task5-ColdToHotPromotion-Report.md`
  - `docs/tasks/P3/P3-Task8-ManagementAndObservability-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md`
  - `docs/tasks/P7/C3-ColdAwareUpdateDelete-Report.md`
- Backlog:
  - `docs/BACKLOG.md` (BL-054)
- Code paths:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Storage/Residency/ResidencyManager.cs`
  - `src/Aouda.Engine.Storage/Memory/MemoryBudgetOptions.cs`
  - `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
  - `src/Aouda.Engine.Storage/HotColdInspector.cs`
  - `src/Aouda.Engine.Api/ServerMemoryBudgetManager.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Controllers/ServerController.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Configuration/CommandLineMappings.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptions.cs`
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/tables.ts`
- Tests:
  - `tests/Aouda.Engine.Catalog.Tests/HotColdMetadataTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotToColdDemotionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/ColdToHotPromotionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotColdManagementTests.cs`
  - `tests/Aouda.Engine.Api.Tests/PerDatabaseBudgetIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/TablesIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/ServerIntegrationTests.cs`
  - `../aouda-client-ts/tests/admin.test.ts`
  - `../aouda-client-ts/tests/tables.test.ts`

## 2.20 What is missing from this document? (meta completeness)

- This document includes critical path walk-throughs, but not full method-by-method pseudocode for every class in the hot/cold subsystem.
- No claim is made that ADR 0011/0012 sample APIs are shipped; they are intentionally documented here as proposed/reserved only.
- If new public endpoints for promote/demote or filter-based residency are added, sections `2.10` and `2.11` must be updated immediately with new config/API matrices and scenario updates.

