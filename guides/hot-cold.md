---
title: "Hot/Cold Storage"
nav_order: 5
parent: "Guides"
---

# Aouda Functionality: Hot/Cold Storage and Memory Control

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-08-13

Coverage phases: P3, P6, P7, P30, BL-091
Primary task folders: `docs/tasks/P3/`, `docs/tasks/P6/`, `docs/tasks/P7/`, `docs/tasks/P30/`
Primary ADRs: `docs/decisions/0007-hot-vs-cold-storage.md`, `docs/decisions/0011-memory-prioritization.md`, `docs/decisions/0012-memory-footprint-reduction.md`, `docs/decisions/0034-unified-in-memory-tiering.md`, `docs/decisions/0035-temperature-aware-replication-and-backup.md`
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
  - `src/Aouda.Engine.Core/Query/MemoryFilterGrammar.cs` (BL-091-S1)
  - `src/Aouda.Engine.Core/Query/MemoryFilterException.cs` (BL-091-S1)
  - `src/Aouda.Engine.Core/Query/Expr.cs` (BL-091-S1 — `Expr.CollectColumnIds`)
  - `src/Aouda.Engine.Catalog/CatalogApi.cs` (BL-091-S1 — `ValidateResidencyPolicy`)
  - `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
  - `src/Aouda.Engine.Storage/HotCold/MemoryFilterSegmentEvaluator.cs` (BL-091-S2)
  - `src/Aouda.Engine.Storage/HotCold/SegmentDemoter.cs` (BL-091-S2 — `DemotionReason.PolicyRowCapExceeded`)
  - `src/Aouda.Engine.Storage/HotColdInspector.cs` (BL-091-S3 — `GetSegmentResidencyExplanation`)
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
  - `tests/Aouda.Engine.Core.Tests/MemoryFilterGrammarTests.cs` (BL-091-S1)
  - `tests/Aouda.Engine.Catalog.Tests/MemoryFilterPolicyValidationTests.cs` (BL-091-S1)
  - `tests/Aouda.Engine.Storage.Tests/MemoryFilterSegmentEvaluatorTests.cs` (BL-091-S2)
  - `tests/Aouda.Engine.Storage.Tests/HotColdMaintenanceWorkerTests.cs` (BL-091-S2)
  - `tests/Aouda.Engine.Storage.Tests/HotColdObservabilityTests.cs` (BL-091-S3)
  - `tests/Aouda.Engine.Storage.Tests/HotToColdDemotionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/ColdToHotPromotionTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotColdManagementTests.cs`
  - `tests/Aouda.Engine.Api.Tests/PerDatabaseBudgetIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/TablesIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/ServerIntegrationTests.cs`
  - `../aouda-client-ts/tests/admin.test.ts`
  - `../aouda-client-ts/tests/tables.test.ts`
- BL-091 task specs:
  - `docs/tasks/BL/BL-091-Overview.md`
  - `docs/tasks/BL/BL-091-S1-FilterGrammarAndValidation.md`
  - `docs/tasks/BL/BL-091-S2-EngineEnforcement.md`
  - `docs/tasks/BL/BL-091-S3-Observability.md`
  - `docs/tasks/BL/BL-091-S4-ProtocolAndApi.md`

## 2.3 Defaults and zero-config behavior

If you do nothing beyond default server config:

- Table temperature policy defaults to `Auto`.
- New segments start `Hot`.
- Server memory defaults to:
  - `MaxTotalRamBytes` unset → about **70% of detected host or cgroup memory** (an RSS ceiling, not a 2 GiB constant)
  - `MaxHotBytes = 0` (effective fraction of the governed budget)
  - `MaxPageCacheBytes = 0` (effective fraction of the governed budget)
- Budget target defaults to a high fraction of the governed budget when unspecified.
- Over-budget ingest returns **HTTP 503** (`MEMORY_BUDGET_EXCEEDED`) with `Retry-After`; the process stays up.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| Table `StorageTemperaturePolicy` | `Auto` | Engine can demote/promote segments using maintenance and access signals |
| Segment temperature on creation | `Hot` | New data is queried on hot path first |
| `Aouda:Memory:MaxTotalRamBytes` | ~70% of detected RAM | Process RSS ceiling (set explicitly to pin a number) |
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
  - `StorageTemperaturePolicy` (`Auto`, `HotOnly`, `ColdPreferred`, `Mutable`)
  - `SegmentTemperature` (`Hot`, `Cold`)
  - `DataDurabilityMode` (`MemoryOnly`, `DiskBacked`) — fully enforced end-to-end (P30)
- Promotion/demotion lifecycle:
  - Hot->cold demotion pipeline with catalog durability updates and diagnostics.
  - Cold->hot promotion pipeline: **two intents** (P30):
    - `PromoteForQueryAsync` — cold → immutable columnar hot (query path)
    - `PromoteForUpdateAsync` — cold → mutable keyed tier (update/cache path), with two-phase dissolution for crash safety
- **Hot-first flush** (P30): Flush produces only an immutable hot segment (`.hot` file). Cold segments come exclusively from the demotion path. Prior to P30 this invariant was violated.
- **Mutable keyed tier** (P30): `MutableKeyedStore` provides in-place upsert by PK. Dead-row reclamation via lazy tombstone compaction. Bounded memory at keyspace size. Serves `LatestPerKey` and cache/UPSERT workloads.
- **Representation selector** (P30): `RepresentationSelector` routes incoming write streams by: intent hint (`Mutable` policy) → mutation rate (rolling writes/s) → segment size (below seal floor) → defaults to immutable hot.
- **Hot segment merge** (P30): `HotSegmentMergeWorker` coalesces small immutable hot segments and compacts mutable-tier tombstones.
- **Durability gating end-to-end** (P30): `DefaultPageStoreRouter` governs flush/persist path. `MemoryOnly` tables write nothing (no `.hot`, `.col`, `.hra`, WAL). `DiskBacked` tables persist per representation. The old bypass (hardcoded `FilePageStore`) was removed.
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
  - REST/Protocol support for `memoryFilter`, `memoryRowCap`, `targetMemoryBytes`, and `pinAllInMemory` — all readable and settable via the existing table create and update-policy endpoints (BL-091).
- Filter-based partial residency (BL-091):
  - `ResidencyPolicy.MemoryFilter` — JSON predicate grammar (segment-granularity). Validated at catalog write time; enforced during maintenance sweeps by preferring to demote segments provably unable to match the filter.
  - `ResidencyPolicy.MemoryRowCap` — per-table cap on resident (hot) row count. Enforced in the periodic maintenance sweep independently of the byte budget.
  - `ResidencyPolicy.TargetMemoryBytes` — per-table hot-byte budget wired to the existing `MemoryBudgetManager` per-table limit mechanism, overriding the global `AutoHotByteBudgetBytes` for that table.
  - `HotColdInspector.GetSegmentResidencyExplanation` — per-segment explain API (why is this segment hot or cold under the current policy?).
  - `Perf` counters: `MemoryFilterDemotionsPrioritized`, `RowCapDemotions`.

### Planned / proposed

From ADR intent and follow-up planning, not shipped as end-to-end behavior:

- Rich memory intent declarations from ADR 0011 (for example `HotRetention`, `HotRowLimit`, query memory protection). **Note: `LatestPerKey` is now served by the mutable keyed tier (P30).**
- Advanced hot footprint optimizations from ADR 0012 (for example hot encoding strategy tiers as productized table options). **Note: Frame-of-Reference Timestamp and normalized-scale Decimal hot representations are now shipped (P29).**
- Broader HTTP/SDK management APIs for explicit promote/demote operations.
- Dictionary-encoding strings in the mutable tier (ADR 0034 Open Question 2).
- Cross-tier distributed cache / replication-of-cache semantics.
- Filter-based partial residency — deferred v1 limitations (BL-091):
  - Row/page-granularity temperature (segment remains the enforcement unit; BL-125 for promotion-side filter awareness).
  - `LIKE`, `IN`, `IS NULL` operators in `MemoryFilter` (v1 supports `eq`/`ne`/`lt`/`lte`/`gt`/`gte` only).
  - Cross-table or database-wide row/byte caps.
  - `MemoryFilter`/`MemoryRowCap`/`TargetMemoryBytes` enforcement on `HotOnly`/`ColdPreferred` tables (fields are silently ignored on those policies today — BL-126 for a future validation/warning).
  - Reactive `MemoryBudgetManager` pressure path wired to `TargetMemoryBytes`/`MemoryRowCap` (BL-124 — today only the periodic maintenance sweep enforces these).
  - Studio UI for filter-based residency controls.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P3 | `P3-HotCold-Implementation-Tasks.md`, Task 4/5/8 reports | Temperature metadata, demotion/promotion pipelines, maintenance worker behavior, management and observability APIs | Advanced heuristics and richer productized memory-intent controls deferred | `docs/BACKLOG.md` (see BL-054 for residency filtering) |
| P6 | `P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md` | Per-database memory budgeting, server memory coordinator, `/api/server/memory`, health integration | Cross-database page-cache sharing and richer per-db metrics labeling deferred | `docs/BACKLOG.md` BL-001 marked complete; future enhancements tracked in later tasks |
| P7 | `C3-ColdAwareUpdateDelete-Report.md` + correctness reports | Cold-aware mutation correctness hardened via deletion masks across query paths | Further optimization of cold mutation paths may continue separately | No new hot/cold backlog item created by C3 report |
| P30 | `MemTiering-S1` through `MemTiering-S14`, Bug/Perf reports | Hot-first flush invariant enforced; `MemoryOnly`/`DiskBacked` end-to-end; mutable keyed tier; representation selector; hot segment merge; intent-aware promotion + two-phase dissolution; hot L2; replication Gap A; segment ship; catalog authority Gap B; backup Gap C; retention/durability hardening | Dictionary string encoding in mutable tier; cross-tier replication; mutation-rate hysteresis tuning | ADR 0034, ADR 0035 |
| BL-091 | `docs/tasks/BL/BL-091-S1` through `BL-091-S5` (all Reports) | Filter grammar + validation (`MemoryFilterGrammar`, `MemoryFilterParseException`); segment-level enforcement in `HotColdMaintenanceWorker` (filter ordering, row-cap, per-table byte target); `MemoryFilterSegmentEvaluator`; `DemotionReason.PolicyRowCapExceeded`; `HotColdInspector` extensions (`GetSegmentResidencyExplanation`, `TablePolicyInfo` fields); `Perf` counters (`MemoryFilterDemotionsPrioritized`, `RowCapDemotions`); HTTP exposure on existing create-table + update-policy endpoints; `PinAllInMemory` write path now enabled | Row/page-granularity; `LIKE`/`IN`/`IS NULL` operators; cross-table budgets; reactive pressure path (BL-124); promotion-side filter awareness (BL-125); `HotOnly`/`ColdPreferred` validation (BL-126); Studio UI | `docs/BACKLOG.md` BL-091 closed |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Table-level storage temperature (`Auto`/`HotOnly`/`ColdPreferred`) | Yes | No | No | P3 Task 1 report, `Policies.cs`, tables integration tests | Fully available across catalog + protocol + TS client |
| `Mutable` intent flag on `StorageTemperaturePolicy` | Yes | No | No | P30 S4, `RepresentationSelector.cs` | Routes write streams to mutable keyed tier instead of immutable hot |
| `MemoryOnly` durability enforcement (writes nothing) | Yes | No | No | P30 S2, `DefaultPageStoreRouter.cs`, storage tests | Fully enforced end-to-end — no `.hot`, `.col`, `.hra`, or WAL written |
| `DiskBacked` durability enforcement | Yes | No | No | P30 S2, `DefaultPageStoreRouter.cs` | Persists per representation; old bypass removed |
| Hot-first flush invariant | Yes | No | No | P30 S1, `HraCompactor.cs`, flush tests | Flush produces only immutable hot segment; cold segments come from demotion only |
| Mutable keyed tier (`MutableKeyedStore`) | Yes | No | No | P30 S3, `MutableKeyedStore.cs` | In-place upsert by PK; O(1) point lookup; dead-row reclamation |
| Representation selector | Yes | No | No | P30 S4, `RepresentationSelector.cs` | Routes by intent → mutation rate → size |
| Hot segment merge worker | Yes | No | No | P30 S5, `HotSegmentMergeWorker.cs` | Coalesces small hot segments; compacts tombstones |
| Segment temperature persistence (`Hot`/`Cold`) | Yes | No | No | P3 Task reports, `Policies.cs`, `HotColdMetadataTests` | Preserved through restart semantics |
| Hot->cold demotion | Yes | No | No | P3 Task 4 report, `SegmentDemoter`, demotion tests | Includes policy-driven demotion and diagnostics |
| Cold->hot promotion (for query) | Yes | No | No | P3 Task 5 / P30 S6, `SegmentPromoter.PromoteForQueryAsync` | Promotes cold → immutable columnar hot |
| Cold->mutable tier promotion (for update) | Yes | No | No | P30 S6/S7, `SegmentPromoter.PromoteForUpdateAsync` | Promotes cold → mutable keyed tier; two-phase dissolution for crash safety |
| Two-phase dissolution (Gap B crash safety) | Yes | No | No | P30 S7/S11, catalog + durable tombstone | Phase 1: dissolving; Phase 2: fsync + retire; tombstone prevents orphan resurrection |
| Maintenance worker policy automation | Yes | No | No | `HotColdMaintenanceWorker.cs`, P3 reports/tests | Auto/HotOnly/ColdPreferred/Mutable handled |
| Hot/cold management inspection surface | Yes | No | No | P3 Task 8 report, `HotColdInspector.cs` | Rich .NET surface, no equivalent first-class HTTP endpoints |
| Per-database memory budget coordination | Yes | No | No | P6 F1 report, `ServerMemoryBudgetManager.cs`, integration tests | Server-level cap + per-db snapshots |
| Table policy `PinAllInMemory` runtime handling | Yes | No | No | `Policies.cs`, `ResidencyManager.cs`, tests | Implemented in V1 residency manager |
| Filter-based partial residency (`MemoryFilter`, row cap, target bytes) | Yes | No | No | BL-091-S1–S5 Reports; `MemoryFilterGrammar.cs`, `HotColdMaintenanceWorker.cs`, `TableMessages.cs`, `TablesController.cs`, `HotColdInspector.cs` | Segment-granularity enforcement ("ordering not eligibility"); v1 operators: `eq`/`ne`/`lt`/`lte`/`gt`/`gte`. `HotOnly`/`ColdPreferred` tables ignore these fields in v1 (BL-126). Reactive pressure path not yet wired (BL-124). |
| Public API for explicit promote/demote operations | No | Yes | No | .NET engine APIs only | HTTP/TS SDK surface for explicit promote/demote not yet exposed |

## 2.7 Core concepts and mental model

**Two orthogonal axes (P30 / ADR 0034):**

- **Temperature axis** — controls data representation:
  - Mutable keyed tier: in-place upsert by PK; serves cache and UPSERT workloads
  - Immutable hot tier: append-optimised columnar; serves read-heavy workloads
  - Cold tier: encoded/compressed on disk; demoted from hot
- **Durability axis** — controls persistence:
  - `MemoryOnly`: writes nothing to disk; data lives only in the running process
  - `DiskBacked`: persists per representation (`.hot`, `.col`, `.hra`, WAL)

**Key types:**

- `StorageTemperaturePolicy`: Table-level intent for the temperature axis. Values: `Auto`, `HotOnly`, `ColdPreferred`, `Mutable` (P30).
- `DataDurabilityMode`: Table-level durability intent. Values: `MemoryOnly`, `DiskBacked`.
- `SegmentTemperature`: Actual per-segment state (`Hot`, `Cold`) used by execution and maintenance.
- `MutableKeyedStore`: In-place upsert by PK. Dead-row reclamation via tombstone compaction. Serves `LatestPerKey` and cache workloads.
- `RepresentationSelector`: Routes incoming write streams to the appropriate tier based on intent → mutation rate → segment size.

**Hot-first flush invariant (P30):**
- Flush always produces only an immutable `.hot` segment. Cold segments are **never** produced directly at flush — they come exclusively from the demotion path (`SegmentDemoter`). Pre-P30, `HraCompactor` violated this by writing both cold `.col` and hot segments at flush.

**Demotion vs Promotion:**
- Demotion: hot (immutable) → cold; catalog updated; hot handles unregistered.
- `PromoteForQueryAsync`: cold → immutable columnar hot (read acceleration).
- `PromoteForUpdateAsync`: cold → mutable keyed tier (write acceleration); uses two-phase dissolution to prevent double-counting on crash (Gap B).

**Memory governance layers:**
- Per-engine `MemoryBudgetManager` + server-level `ServerMemoryBudgetManager`.

**Filter-based partial residency (BL-091):**

`ResidencyPolicy` now has three active fields composable with `Auto` policy:

- **`MemoryFilter`** — a JSON predicate that controls demotion *ordering*. Segments that provably cannot contain matching rows (via zone-map pruning) are demoted before segments that might match. A segment holding even one potential matching row is protected — no partial-segment hot/cold split.
  - Grammar: `{"and": [...]}` or `{"or": [...]}`, where each condition is `{"column": "<name>", "op": "<op>", "value": <scalar>}`.
  - Supported operators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`.
  - Supported `DataType`s: `Int32`, `Int64`, `Byte`, `UInt16`, `UInt32`, `UInt64`, `Double`, `Float32`, `Decimal`, `Bool`, `String`, `Guid`. Filtering on `Int16`, `Timestamp`, `Date`, `Vector`, or `MdVector` columns is rejected at policy validation time.
  - Not supported in v1: `LIKE`, `IN`, `IS NULL`, nested groups (file a new BL item if needed).
  - `null` (unset) is always valid and means "no filter" — no ordering change.
  - Validated at catalog write time (`SetTablePolicyAsync`/`CreateTableAsync`); invalid filters are rejected with a descriptive `MemoryFilterParseException` message before any catalog mutation.

- **`MemoryRowCap`** (`long? > 0`) — per-table cap on hot resident row count. The maintenance sweep sums `HotSegmentInfo.RowCount` per table; when the sum exceeds the cap, segments are demoted (oldest-first, filter-ordered if a `MemoryFilter` is also set) until the row count settles at or below the cap.

- **`TargetMemoryBytes`** (`long? > 0`) — per-table hot-byte budget, overriding the global `AutoHotByteBudgetBytes` for that table. Wired to the existing `MemoryBudgetManager.SetTableHotLimit` mechanism.

**Key behavioral rules (BL-091):**

- "Ordering not eligibility": `MemoryFilter` never prevents a segment from being demoted if the table is genuinely over budget or row-cap. It only influences *which* segment gets picked first.
- OR semantics for dual caps: if both `MemoryRowCap` and `TargetMemoryBytes` are set, exceeding *either* triggers demotion; demotion continues until *both* are satisfied.
- Pinned segments (`PinAllInMemory`) are never demoted by filter/cap logic.
- `HotOnly` and `ColdPreferred` tables ignore these fields in v1; the fields persist in the catalog and are validated at write time, but enforcement only applies to `Auto`-policy tables.
- The periodic maintenance sweep is the only enforcement path. The reactive `MemoryBudgetManager` pressure path is not yet wired to per-table `TargetMemoryBytes`/`MemoryRowCap` (BL-124).
- A `MemoryFilter` parse failure at runtime (e.g. future grammar migration) is handled gracefully: the sweep falls back to `CreatedUtc`-only ordering for that table, never throws out of the sweep.

**Invariants:**

- Temperature is not inferred from file type; it is explicit in catalog metadata.
- Demotion/promotion are explicit transitions, not implicit process-lifecycle side effects.
- `MemoryOnly` tables produce zero disk writes. No `.hot`, `.col`, `.hra`, or WAL records.
- WAL records contain only concrete resolved values — never unevaluated expression ASTs.
- All three residency fields (`MemoryFilter`, `MemoryRowCap`, `TargetMemoryBytes`) are validated at catalog write time; unsupported operators or column names are rejected with a descriptive error before any mutation.

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
- Filter grammar (BL-091-S1):
  - `src/Aouda.Engine.Core/Query/MemoryFilterGrammar.cs` — `Parse(json, columnsByName)` / `TryParse(...)` → `Expr`
  - `src/Aouda.Engine.Core/Query/MemoryFilterException.cs` — `MemoryFilterParseException`
  - `src/Aouda.Engine.Core/Query/Expr.cs` — `Expr.CollectColumnIds(Expr?)` helper
  - `src/Aouda.Engine.Catalog/CatalogApi.cs` — `ValidateResidencyPolicy(residency, columns)` called before every catalog mutation that sets policy
- Temperature operations:
  - `src/Aouda.Engine.Storage/HotCold/SegmentDemoter.cs` — `DemotionReason` enum (includes `PolicyRowCapExceeded`, BL-091-S2)
  - `src/Aouda.Engine.Storage/HotCold/SegmentPromoter.cs`
  - `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
  - `src/Aouda.Engine.Storage/HotCold/MemoryFilterSegmentEvaluator.cs` — segment-level "could match filter" test via `PagePruner.CanSkipEntireSegment` (BL-091-S2)
- Diagnostics/ops:
  - `src/Aouda.Engine.Storage/HotColdInspector.cs` — `GetSegmentResidencyExplanation(...)`, extended `TablePolicyInfo`, extended `ListTablePolicies`, extended `GetTablePolicyReport` (BL-091-S3)
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

### Walk-through E: Filter/cap-aware maintenance sweep (BL-091)

1. `HotColdMaintenanceWorker.RunOnceAsync()` builds both `hotBytesByTable` and `hotRowsByTable` (summing `HotSegmentInfo.ApproximateBytes` and `.RowCount` per table respectively).
2. For each `Auto`-policy table:
   a. Per-table byte budget = `tableEntry.Policy.Residency.TargetMemoryBytes ?? globalAutoByteBudget`.
   b. Per-table row cap = `tableEntry.Policy.Residency.MemoryRowCap` (null = no row-cap enforcement).
   c. If `MemoryFilter` is non-null: parse once via `MemoryFilterGrammar.TryParse`. On failure, log and fall back to `CreatedUtc`-only ordering.
   d. For each sealed, unpinned, non-cooldown candidate segment: call `MemoryFilterSegmentEvaluator.CouldMatchAsync(...)`, which loads column page summaries and inverts `PagePruner.CanSkipEntireSegment`. Segments where `couldMatch = false` (provably non-matching) are sorted first; within each group, oldest `CreatedUtc` first.
   e. Walk the sorted candidates, demoting until both byte budget and row cap are satisfied. A `PolicyRowCapExceeded` `DemotionReason` is recorded for row-cap-triggered demotions; `PolicyAutoBudget` for byte-budget-triggered ones.
3. If the optional `FilePageStore` is absent (not supplied to the constructor), or if `MemoryFilter` is null, step d is skipped and ordering is plain `CreatedUtc`.

Primary code anchors:

- `src/Aouda.Engine.Storage/HotCold/HotColdMaintenanceWorker.cs`
- `src/Aouda.Engine.Storage/HotCold/MemoryFilterSegmentEvaluator.cs`
- `src/Aouda.Engine.Storage/HotCold/SegmentDemoter.cs`

Primary proving tests:

- `tests/Aouda.Engine.Storage.Tests/HotColdMaintenanceWorkerTests.cs` (`Auto_*` tests — AC1-AC10 from BL-091-S2)
- `tests/Aouda.Engine.Storage.Tests/MemoryFilterSegmentEvaluatorTests.cs`

### Walk-through F: Policy create/update with partial residency fields (BL-091)

1. Client sends `POST /api/databases/{db}/tables` (create) or `PUT /api/databases/{db}/tables/{name}/policy` (update) with a JSON body that may include any of `memoryFilter`, `memoryRowCap`, `targetMemoryBytes`, `pinAllInMemory`.
2. `TablesController` reads the new fields from `CreatePolicyRequest` or `UpdatePolicyRequest`.
   - For update-policy: sentinel convention distinguishes "omitted" (leave unchanged) from "explicit clear": `""` clears `memoryFilter`; `0` clears `memoryRowCap` or `targetMemoryBytes`. A positive value sets the field; null/omitted leaves the current value.
3. Controller calls `engine.Catalog.CreateTableAsync` or `SetTablePolicyAsync` with the constructed `TablePolicy` (including the updated `Residency`).
4. Inside `CatalogApi`, `ValidateResidencyPolicy(residency, columns)` runs before any snapshot mutation:
   - Parses `MemoryFilter` (if non-null) via `MemoryFilterGrammar.Parse(json, columnsByName)`. On failure, throws `MemoryFilterParseException`; the controller catches this (as `ArgumentException`, since `MemoryFilterParseException` derives from it) and returns `400 BadRequest` with `ErrorCodes.InvalidRequest` and the exception message.
   - Validates `MemoryRowCap > 0` and `TargetMemoryBytes > 0` (zero or negative → `ArgumentOutOfRangeException` → controller catches → `400`).
5. On success, the policy (including the three new fields) persists through `CatalogStore` like any other `TablePolicy` field. Round-trips across restart (serialised as part of `TableEntry`).
6. `MapToPolicyDetailResponse` includes the three new fields in `ResidencyDetailResponse` (`memoryFilter`, `memoryRowCap`, `targetMemoryBytes`) on all policy read paths.

Primary code anchors:

- `src/Aouda.Server/Controllers/TablesController.cs`
- `src/Aouda.Engine.Catalog/CatalogApi.cs` (`ValidateResidencyPolicy`)
- `src/Aouda.Protocol/Schema/TableMessages.cs` (`ResidencyDetailResponse`, `CreatePolicyRequest`, `UpdatePolicyRequest`)

Primary proving tests:

- `tests/Aouda.Server.Tests/TablesIntegrationTests.cs` (`CreateTable_WithResidencyPolicy_*`, `UpdatePolicy_*Residency*`, `UpdatePolicy_ExplicitClearSentinels_*`, `CreateTable_Invalid*_Returns400`, etc. — AC1-AC8 from BL-091-S4)

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Can I set explicit hot/cold table behavior? | Often indirect cache tuning only | First-class table temperature policy with explicit enum | More predictable behavior and clearer intent |
| Is temperature durable metadata? | Often inferred from storage format/cache state | Catalog stores segment and table temperature policy directly | Less ambiguity during restart and operations |
| Do I get built-in promotion/demotion management tools? | Often ad-hoc or internal-only | Built-in inspector, health checks, bulk demote/promote APIs in engine surface | Faster incident handling and diagnostics |
| Can I monitor server memory by database? | Often external tooling only | Native `/api/server/memory` and per-database budget coordination | Better multitenant capacity control |
| Are planned features clearly separated from shipped behavior? | Frequently unclear in docs | Reserved/planned surfaces explicitly split and backlog-linked | Lower implementation-risk assumptions |

## 2.10 Configuration and settings reference (complete surface)

{: .note }
**Precedence and restart:** [Server configuration](server-configuration.md). Memory limits can also be changed at runtime via `PATCH /admin/config` (in-memory until restart unless set in startup config).

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:Memory:MaxTotalRamBytes` | long | ~70% of detected RAM | `>= 1048576` | startup config / runtime resize | Process RSS ceiling; hot/cache thresholds derive from the governed budget |
| `Aouda:Memory:MaxHotBytes` | long | `0` | `>= 0` | startup config | `0` means 70% of total |
| `Aouda:Memory:MaxPageCacheBytes` | long | `0` | `>= 0` | startup config | `0` means 20% of total |
| `Aouda:Databases:{db}:MaxMemoryBytes` | long? | `null` | null or positive | startup config | Per-database cap when set |
| `Aouda:Databases:{db}:DefaultTemperature` | string | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` | startup config | Default for new tables in that DB |
| `CreateTableRequest.policy.storageTemperature` | string | `Auto` | `Auto`, `HotOnly`, `ColdPreferred` | HTTP create-table body | Per-table policy at creation |
| `UpdatePolicyRequest.storageTemperature` | string | none (required) | `Auto`, `HotOnly`, `ColdPreferred` | HTTP update-policy body | Per-table policy update |
| `ResidencyPolicy.PinAllInMemory` | bool | `false` | `true`/`false` | HTTP create-table body, HTTP update-policy body, Catalog/.NET | Settable and readable via HTTP (BL-091-S4). Pins hot segments; never demoted by filter/cap logic. |
| `ResidencyPolicy.MemoryFilter` | string? | `null` | JSON predicate or `null` | HTTP create-table body, HTTP update-policy body, Catalog/.NET | v1 grammar: `{"and":[…]}` or `{"or":[…]}`; operators: `eq`/`ne`/`lt`/`lte`/`gt`/`gte`. Validated at write time; unsupported operators or columns rejected. On update-policy: `""` = explicit clear. Null = no filter active. Affects demotion ordering only. |
| `ResidencyPolicy.MemoryRowCap` | long? | `null` | `> 0` or `null` | HTTP create-table body, HTTP update-policy body, Catalog/.NET | 0 or negative rejected at write time. On update-policy: `0` = explicit clear. Null = no row cap. Enforced in periodic maintenance sweep for `Auto`-policy tables. |
| `ResidencyPolicy.TargetMemoryBytes` | long? | `null` | `> 0` or `null` | HTTP create-table body, HTTP update-policy body, Catalog/.NET | 0 or negative rejected at write time. On update-policy: `0` = explicit clear. Null = use global `AutoHotByteBudgetBytes`. Enforced in periodic maintenance sweep for `Auto`-policy tables. |
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
- `MemoryFilter`/`MemoryRowCap`/`TargetMemoryBytes`:
  - All three are now active (BL-091). Validated at table create/policy update time. Enforced in the periodic maintenance sweep for `Auto`-policy tables.

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

Common mistake: omitting the sentinel convention for explicit clear on update-policy — `""` for `memoryFilter`, `0` for `memoryRowCap`/`targetMemoryBytes` (null/omitted means "leave unchanged", not "clear").

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

#### HTTP example — create table with filter-based partial residency (BL-091)

```http
POST /api/databases/appdb/tables
Content-Type: application/json

{
  "database": "appdb",
  "name": "events",
  "columns": [
    { "name": "id", "type": "Int64" },
    { "name": "status", "type": "String" },
    { "name": "amount", "type": "Double" }
  ],
  "policy": {
    "storageTemperature": "Auto",
    "memoryFilter": "{\"and\":[{\"column\":\"status\",\"op\":\"eq\",\"value\":\"active\"}]}",
    "memoryRowCap": 500000,
    "targetMemoryBytes": 1073741824
  }
}
```

Expected result: table created; filter validated against schema at create time; on subsequent maintenance sweeps, segments that cannot contain `status = 'active'` rows are demoted first, and the table's hot residency is capped at 500 K rows / 1 GiB.

Common mistakes:
- Referencing a column not in the table's schema — returns `400` naming the unknown column.
- Using `0` or a negative value for `memoryRowCap`/`targetMemoryBytes` — returns `400`.
- Using an unsupported operator (`like`, `in`, `is null`) — returns `400`.

#### HTTP example — update-policy: change filter + clear row cap (BL-091)

```http
PUT /api/databases/appdb/tables/events/policy
Content-Type: application/json

{
  "database": "appdb",
  "memoryFilter": "{\"or\":[{\"column\":\"status\",\"op\":\"eq\",\"value\":\"active\"},{\"column\":\"status\",\"op\":\"eq\",\"value\":\"pending\"}]}",
  "memoryRowCap": 0
}
```

Expected result: `memoryFilter` updated to the new value; `memoryRowCap` explicitly cleared (sentinel `0` = "remove cap"); `storageTemperature` and `targetMemoryBytes` are unchanged (omitted = leave as-is).

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Create table with storage temperature | `AoudaEngine.CreateTableAsync(..., policy)` | `client.tables.createTable({ policy: { storageTemperature } })` | `POST /api/databases/{db}/tables` | Implemented | Full path available |
| Update storage temperature policy | `Catalog.SetTablePolicyAsync(...)` via engine/catalog surface | `client.tables.updatePolicy(...)` | `PUT /api/databases/{db}/tables/{name}/policy` | Implemented | End-to-end shipped |
| Observe hot/cold state and bulk ops | `HotColdInspector.*` | No direct wrapper | No dedicated endpoint | Partial | Available in engine/.NET only |
| Read server + per-db memory budget usage | `ServerMemoryBudgetManager.GetServerUsage()` | `client.admin.server.memory()` | `GET /api/server/memory` | Implemented | Good operator surface |
| Configure advanced `MemoryBudgetOptions` fields | `new MemoryBudgetOptions(...)` in embedded/open APIs | No direct surface | Server config exposes only 3 core memory keys | Partial | Advanced fields are .NET-only currently |
| Configure filter-based partial residency (`memoryFilter`, `memoryRowCap`, `targetMemoryBytes`, `pinAllInMemory`) | `Catalog.SetTablePolicyAsync(...)` via engine/catalog | No direct TS SDK wrapper yet | `POST /api/databases/{db}/tables` + `PUT /api/databases/{db}/tables/{name}/policy` | Implemented (BL-091) | v1 operators: `eq`/`ne`/`lt`/`lte`/`gt`/`gte`. Sentinel clear convention on update-policy. `HotOnly`/`ColdPreferred` tables persist the fields but enforcement is `Auto`-only in v1. |
| Explain segment residency (why hot or cold) | `HotColdInspector.GetSegmentResidencyExplanation(...)` | Not available | No dedicated HTTP endpoint yet | Partial | .NET engine surface only. HTTP endpoint deferred (BL-091 Non-Scope). |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Segment residency explain HTTP endpoint | No public HTTP/TS route for `GetSegmentResidencyExplanation` | Use `.NET` inspector API in embedded contexts | BL-091 Non-Scope; file a new BL item to request HTTP exposure | Medium |
| Explicit promote/demote admin endpoints | No public HTTP/TS mutation endpoints for these operations | Use `.NET` inspector APIs in embedded/engine contexts | Follow-up tasks after P3 management APIs | Medium |
| Full server-config exposure for advanced memory action ladder knobs | No config keys for `EnableEmergencyDemotion`, `StrictMode`, etc. | Set in embedded `.NET` construction only | Future server configuration hardening tasks | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run baseline (defaults only)

When to use:
- New environment where you want safe default behavior first.

Steps:
1. Use default `Aouda:Memory` code defaults, or set limits via env/CLI/optional appsettings — see [Server configuration](server-configuration.md).
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

### Scenario 4: Keep only active data hot with MemoryFilter

When to use:
- A table has a high-cardinality column (e.g. `status`) where only a fraction of values are "active" and worth keeping hot.

Steps:
1. Create the table (or update policy on an existing one) with `memoryFilter`:
   ```http
   PUT /api/databases/appdb/tables/events/policy
   Content-Type: application/json

   {
     "database": "appdb",
     "memoryFilter": "{\"and\":[{\"column\":\"status\",\"op\":\"eq\",\"value\":\"active\"}]}"
   }
   ```
2. Ingest a mix of `status = 'active'` and `status = 'closed'` rows, enough to seal multiple segments.
3. Wait for maintenance sweep (default `SweepInterval = 5s`) or trigger it.
4. Query `HotColdInspector.GetSegmentResidencyExplanation(...)` for a known non-matching segment — `CouldMatchFilter` should be `false`, `Summary` should explain the filter eliminated it.

Expected result checks:
- Non-matching segments (provably `status` range does not overlap `'active'`) are demoted before matching segments when byte/row pressure exists.
- Total row count across hot + cold is unchanged (no data loss).
- If the table is under both byte and row-cap limits, no demotions occur regardless of filter — filter is an ordering signal, not a hard protection rule.

Common mistakes:
- Expecting the filter to prevent demotions entirely — it only changes ordering within the demotion sweep.
- Using `LIKE`/`IN` operators — these are not supported in v1; use `eq`/`ne`/`lt`/`lte`/`gt`/`gte`.

### Scenario 5: Cap table hot footprint with MemoryRowCap + TargetMemoryBytes

When to use:
- A table should not consume more than a fixed fraction of server hot memory, regardless of insertion rate.

Steps:
1. Create table or update policy with both caps:
   ```http
   PUT /api/databases/appdb/tables/events/policy
   Content-Type: application/json

   {
     "database": "appdb",
     "memoryRowCap": 1000000,
     "targetMemoryBytes": 536870912
   }
   ```
2. Ingest rows past both limits (ingest > 1 M rows and / or > 512 MiB of hot data).
3. Wait for the maintenance sweep.
4. Inspect hot residency:
   - Via `HotColdInspector.ListTablePolicies(catalog, hotRegistry, coldRegistry)` — `MemoryRowCapUsed` and hot bytes for the table should be at or below the configured limits.
   - Via `Perf` counters: `RowCapDemotions` should be non-zero if row cap drove the demotions; `MemoryFilterDemotionsPrioritized` remains 0 (no filter set).

Expected result checks:
- Hot row count ≤ `memoryRowCap` after the sweep.
- Hot byte total ≤ `targetMemoryBytes` after the sweep.
- Total row count across hot + cold equals the number of ingested rows (no data loss).
- Whichever cap is hit first triggers demotion; both must be satisfied before demotion stops.

Common mistakes:
- Setting `memoryRowCap = 0` or a negative value — returns `400` at policy write time.
- Expecting the caps to take effect immediately — enforcement happens on the next periodic sweep (default interval 5s).

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
- Filter/cap-aware demotion (BL-091, in `Perf.cs`):
  - `MemoryFilterDemotionsPrioritized` — count of successful demotions where `MemoryFilter` was active for the sweep **and** the demoted segment was in the "cannot match" partition (i.e. filter ordering was the deciding factor, not just `CreatedUtc`). A rising value confirms the filter is actively influencing demotion order.
  - `RowCapDemotions` — count of successful demotions whose `DemotionReason` was `PolicyRowCapExceeded`. Distinguishes row-cap-driven demotions from byte-budget-driven ones (`PolicyAutoBudget`).

Per-segment residency explain (BL-091):

- `HotColdInspector.GetSegmentResidencyExplanation(catalog, tableId, segmentId, hotRegistry, ...)` returns a `SegmentResidencyExplanation` record with:
  - `CurrentTemperature` — actual segment temperature from the catalog.
  - `CouldMatchFilter` — `bool?`: `null` = no filter configured; `true` = segment might match; `false` = segment provably cannot match (safe to demote first).
  - `RowCapExceeded` / `ByteTargetExceeded` — point-in-time flags from the registry snapshot.
  - `Summary` — human-readable string, e.g. `"Hot: matches MemoryFilter; table row count 4,200 / cap 5,000; byte target not set."`.
- Use `GetTablePolicyReport()` output for a tabular view across all tables showing `MemoryRowCapUsed`/`TargetMemoryBytes`/`HasMemoryFilter` alongside the existing hot/cold byte columns.

Recovery/restart expectations:

- Temperature metadata is persisted; restart should reload consistent state.
- Memory snapshots are runtime state and should be re-established by ongoing activity.
- `MemoryFilter`/`MemoryRowCap`/`TargetMemoryBytes` round-trip through `CatalogStore` across restart; enforcement resumes on the first maintenance sweep after restart.

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
| `MemoryFilter` is configured but demotion order is unchanged | Table may not be under byte/row-cap pressure (no demotions occur when under budget regardless of filter); or `FilePageStore` was not supplied to the maintenance worker in embedded mode (falls back to `CreatedUtc` ordering); or column zone-map ranges don't allow ruling out any segment (all segments "might match") | Verify table has enough hot data to exceed its budget; check `MemoryFilterDemotionsPrioritized` counter; inspect `GetSegmentResidencyExplanation` for each candidate segment |
| Policy update with `memoryFilter` returns `400` | Filter JSON is invalid; column name does not exist in table schema; operator is not in the v1 supported set (`eq`/`ne`/`lt`/`lte`/`gt`/`gte`); `DataType` not supported in v1 (`Int16`, `Timestamp`, `Date`, `Vector`, `MdVector`) | Read the error message — it names the bad column/operator; check table schema and use a supported operator |
| `memoryRowCap` or `targetMemoryBytes` set to `0` or negative returns `400` | Validation at catalog write time rejects non-positive values | Use a value `> 0`; send `0` on update-policy only if you want to **clear** an existing cap (sentinel convention) |
| Caps set on `HotOnly` or `ColdPreferred` table appear to do nothing | Fields persist and validate correctly, but enforcement in v1 applies only to `Auto`-policy tables | Switch to `Auto` policy to activate enforcement; file a new BL item if enforcement on other policies is needed (BL-126 tracks this) |
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
| Hot-first flush output shape + IPageStore routing | `Aouda.Engine.Storage.Tests` (P30 S1) | Pass | Strong | Verifies only `.hot` produced at flush; cold output absent |
| `MemoryOnly` writes nothing | `Aouda.Engine.Storage.Tests` (P30 S2) | Pass | Strong | No file written for MemoryOnly table |
| Mutable keyed store in-place upsert + reclaim | `Aouda.Engine.Storage.Tests` (P30 S3) | Pass | Strong | Upsert correctness + dead-row ratio trigger |
| Representation selector routing | `Aouda.Engine.Storage.Tests` (P30 S4) | Pass | Strong | Intent/rate/size routing decisions |
| Hot-segment merge coalescing | `Aouda.Engine.Storage.Tests` (P30 S5) | Pass | Strong | Merge worker behavior |
| Intent-aware promotion + two-phase dissolution | `Aouda.Engine.Storage.Tests` (P30 S6/S7) | Pass | Strong | PromoteForUpdate vs PromoteForQuery; Gap B crash safety |
| Durable retirement tombstone | `Aouda.Engine.Catalog.Tests` (P30 S11) | Pass | Strong | Orphaned-file prevention |
| Inspector and maintenance/ops reporting | `HotColdManagementTests.cs` | Pass | Strong | Includes health checks, reports, bulk promote/demote, JSON output, counters |
| Policy update HTTP path | `TablesIntegrationTests.cs` (`UpdatePolicy_*`) | Pass | Strong | Covers invalid enum, not found, valid update + readback |
| Server memory endpoint contract | `ServerIntegrationTests.cs` (`ServerMemory_*`) | Pass | Medium/Strong | Covers shape/content-type + DB visibility; limited negative-path assertions |
| Per-db budget integration | `PerDatabaseBudgetIntegrationTests.cs` | Pass | Medium/Strong | Validates coordinator snapshots and wiring with engines |
| TS client policy/admin bindings (cross-repo) | `../aouda-client-ts/tests/tables.test.ts`, `../aouda-client-ts/tests/admin.test.ts` | Pass | Medium | Confirms endpoint invocation/shape; not a full server E2E path |
| `PinAllInMemory` persistence | `TablesIntegrationTests.cs` (`CreateTable_PinAllInMemory_RoundTrips`, `UpdatePolicy_PinAllInMemory_RoundTrips`) | Pass | Strong | Settable and readable via HTTP (BL-091-S4) |
| Filter grammar parser | `tests/Aouda.Engine.Core.Tests/MemoryFilterGrammarTests.cs` (30 tests) | Pass | Strong | AC1-AC5, AC11 from BL-091-S1: all six ops, and/or composition, unknown column, type mismatch, malformed JSON, `CollectColumnIds` |
| Residency policy validation at catalog write | `tests/Aouda.Engine.Catalog.Tests/MemoryFilterPolicyValidationTests.cs` (17 tests) | Pass | Strong | AC6-AC9 from BL-091-S1: `SetTablePolicyAsync`/`CreateTableAsync` accept/reject; fail-closed ordering; table-id allocator not consumed on rejection |
| `MemoryFilterSegmentEvaluator` zone-map matching | `tests/Aouda.Engine.Storage.Tests/MemoryFilterSegmentEvaluatorTests.cs` (7 tests) | Pass | Strong | AC8 from BL-091-S2: outside range, overlapping, boundary, zero pages, multi-column And, unknown column, constant predicate |
| Filter/cap enforcement in maintenance sweep | `tests/Aouda.Engine.Storage.Tests/HotColdMaintenanceWorkerTests.cs` (18 tests) | Pass | Strong | AC1-AC10 from BL-091-S2: no-op regression, `TargetMemoryBytes` override, `MemoryRowCap`, dual-cap OR semantics, filter ordering, graceful degradation without `FilePageStore`, `DemotionReason` correctness |
| Observability: `TablePolicyInfo`, `GetSegmentResidencyExplanation`, perf counters | `tests/Aouda.Engine.Storage.Tests/HotColdObservabilityTests.cs` (21 tests) | Pass | Strong | AC1-AC7 from BL-091-S3: policy info fields, explain `bool?` semantics, CSV column order, counter increments gated on `Perf.Enable` |
| Residency fields on HTTP create/update-policy endpoints | `tests/Aouda.Server.Tests/TablesIntegrationTests.cs` (13 new tests) | Pass | Strong | AC1-AC8 from BL-091-S4: create/update round-trips, omit-preserves, explicit-clear sentinels, invalid filter/caps → 400, backward compatibility |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No explicit negative server tests for route/body DB mismatch on policy update | Critical validation path for multi-db safety should be explicit | Add `TablesIntegrationTests` case: route `db=A`, body `database=B` -> `400 InvalidRequest` | High |
| No explicit contract test for the update-policy sentinel clear convention (`""` / `0`) across a full restart cycle | Confirms cleared fields stay cleared after process restart, not just within the same session | Add integration test: set filter/cap → clear via sentinel → restart → verify fields are absent | Medium |
| No explicit cross-surface parity test (.NET policy set -> HTTP readback -> TS readback) | Confirms consistency across engine/server/SDK surfaces | Add integration scenario test spanning catalog update and API/SDK retrieval | Medium |
| No dedicated stress test for promotion/demotion under simultaneous server pressure + access-triggered promotions | Complex path where regressions are likely | Add deterministic stress/integration test with bounded workload and counter assertions | Medium |
| Verification ledger currently manual and doc-maintainer-driven | Risk of stale verification status over time | Add CI job artifact that emits latest hot/cold verification summary and link in doc | Medium |

## 2.18 Known gaps and undone work

- BL-091 (closed — filter-based partial residency fully implemented):
  - `MemoryFilter`/`MemoryRowCap`/`TargetMemoryBytes` are validated, enforced, and exposed via HTTP (BL-091-S1 through S5).
  - **Known v1 limitations filed as follow-up backlog items:**
    - BL-123 — `ValidateResidencyPolicy` not wired into `CreateTableFromEntriesAsync`'s auth-mode overload or `CreateEdgeTableAsync` (fix is mechanical; spelled out in the card).
    - BL-124 — `TargetMemoryBytes`/`MemoryRowCap` not wired into the reactive `MemoryBudgetManager` pressure path (only periodic sweep).
    - BL-125 — Promotion-side filter awareness deferred (v1 only affects demotion ordering; cold segments are not eagerly promoted because they match `MemoryFilter`).
    - BL-126 — No validation/warning when `MemoryFilter`/`MemoryRowCap`/`TargetMemoryBytes` are set on `HotOnly`/`ColdPreferred` tables (fields silently ignored at enforcement time in v1).
  - **Grammar limitations that are deliberate v1 scope cuts (not bugs):**
    - Operators not supported: `LIKE`, `IN`, `IS NULL`.
    - Column types not supported: `Int16`, `Timestamp`, `Date`, `Vector`, `MdVector`.
    - No nested `groups` (flat `and`/`or` lists only).
    - No cross-table or database-wide budgets.
- ADR 0011/0012 proposed surfaces:
  - Advanced memory-intent features (e.g. `HotRetention`, `HotRowLimit`, query memory protection) remain proposed, not shipped as public behavior.
  - **Note:** `LatestPerKey` workloads are now served by the mutable keyed tier (P30). Hot encoding strategy tiers (FOR Timestamp, normalized-scale Decimal) are now shipped (P29).
  - User impact: avoid assuming ADR sample APIs exist in current server/SDK surfaces.
- API parity gaps:
  - Promote/demote management is strong in .NET engine APIs but lacks first-class HTTP/TS mutation routes. The `PromoteForUpdateAsync` and `PromoteForQueryAsync` APIs are available at the engine level only.
- Deferred P30 items:
  - Dictionary-encoding strings in the mutable tier (ADR 0034 Open Question 2).
  - Cross-tier distributed cache / replication-of-cache semantics (separate ADR needed).
  - Mutation-rate hysteresis tuning — first working version shipped; calibration deferred.
  - HRA streaming snapshot (BL-105) — HRA backup coverage shipped (S12); streaming snapshot deferred.

## 2.19 References

- ADRs:
  - `docs/decisions/0007-hot-vs-cold-storage.md`
  - `docs/decisions/0011-memory-prioritization.md` (proposed)
  - `docs/decisions/0012-memory-footprint-reduction.md` (proposed)
  - `docs/decisions/0034-unified-in-memory-tiering.md` (P30 primary ADR)
  - `docs/decisions/0035-temperature-aware-replication-and-backup.md` (P30 replication/backup invariants)
- Tasks/reports:
  - `docs/tasks/P3/P3-HotCold-Implementation-Tasks.md`
  - `docs/tasks/P3/P3-Task4-HotToColdDemotion-Report.md`
  - `docs/tasks/P3/P3-Task5-ColdToHotPromotion-Report.md`
  - `docs/tasks/P3/P3-Task8-ManagementAndObservability-Report.md`
  - `docs/tasks/P6/P6-EpicF-Task1-PerDatabaseMemoryBudgets-Report.md`
  - `docs/tasks/P7/C3-ColdAwareUpdateDelete-Report.md`
- BL-091 task specs/reports:
  - `docs/tasks/BL/BL-091-Overview.md`
  - `docs/tasks/BL/BL-091-S1-FilterGrammarAndValidation.md` (Report: grammar API, exception contract, `ValidateResidencyPolicy` wiring, table-id allocator fix)
  - `docs/tasks/BL/BL-091-S2-EngineEnforcement.md` (Report: `MemoryFilterSegmentEvaluator`, dual-condition demotion, `DemotionReason.PolicyRowCapExceeded`)
  - `docs/tasks/BL/BL-091-S3-Observability.md` (Report: `GetSegmentResidencyExplanation`, `TablePolicyInfo` extensions, `MemoryFilterDemotionsPrioritized`/`RowCapDemotions` counters)
  - `docs/tasks/BL/BL-091-S4-ProtocolAndApi.md` (Report: `ResidencyDetailResponse`/`CreatePolicyRequest`/`UpdatePolicyRequest` extensions, sentinel convention, `PinAllInMemory` write path)
- Backlog:
  - `docs/BACKLOG.md` (BL-091 closed; BL-123, BL-124, BL-125, BL-126 filed as v1 follow-ups)
- Code paths:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Core/Query/MemoryFilterGrammar.cs`
  - `src/Aouda.Engine.Core/Query/MemoryFilterException.cs`
  - `src/Aouda.Engine.Core/Query/Expr.cs` (`Expr.CollectColumnIds`)
  - `src/Aouda.Engine.Catalog/CatalogApi.cs` (`ValidateResidencyPolicy`)
  - `src/Aouda.Engine.Storage/HotCold/MemoryFilterSegmentEvaluator.cs`
  - `src/Aouda.Engine.Storage/HotCold/SegmentDemoter.cs` (`DemotionReason.PolicyRowCapExceeded`)
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
  - `tests/Aouda.Engine.Core.Tests/MemoryFilterGrammarTests.cs`
  - `tests/Aouda.Engine.Catalog.Tests/MemoryFilterPolicyValidationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/MemoryFilterSegmentEvaluatorTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotColdMaintenanceWorkerTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/HotColdObservabilityTests.cs`
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
- Filter-based partial residency (BL-091) is now documented. If any of the following ship, the noted sections must be updated:
  - HTTP endpoint for `GetSegmentResidencyExplanation` → update §2.11 API coverage matrix, §2.12 scenario playbooks, §2.13 ops.
  - `LIKE`/`IN`/`IS NULL` operators in `MemoryFilter` grammar → update §2.7 grammar subsection, §2.10 config reference.
  - `TargetMemoryBytes`/`MemoryRowCap` wired into the reactive pressure path (BL-124) → update §2.7 behavioral rules, §2.8.1 Walk-through E, §2.10.
  - Enforcement on `HotOnly`/`ColdPreferred` tables (BL-126) → update §2.7, §2.14 troubleshooting.
  - `@aouda/client` TypeScript wrapper for the new residency fields → update §2.11 TypeScript example and coverage matrix.
- If new public endpoints for explicit promote/demote are added, §2.10 and §2.11 must be updated with new API matrix rows and scenario examples.

