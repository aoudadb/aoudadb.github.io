---
title: "Time-series and Clustering"
nav_order: 11
parent: "Guides"
---

# Aouda Functionality: Time-series and Clustering

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-10-04

Coverage phases: P4, P8, P28
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P8/`, `docs/tasks/P28/`
Primary ADRs: `docs/decisions/0014-time-series-clustering-optimization.md`, `docs/decisions/0009-partitioning-multitenancy.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Partitioning-And-Multitenancy.md`, `docs/dev/Functionality-Query-Execution.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How do I use time-series clustering now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.7 Core concepts and mental model`
- `2.11 API and CLI coverage reference`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Aouda time-series clustering exists to keep append-heavy workloads fast without forcing a full "sort-on-insert plus background rewrite" architecture.

**Clustering is not partitioning, and does not require it.** `clusterColumns` orders rows physically
within a segment and records per-segment min/max statistics, so a range or last-N read on the clustered
column skips segments that cannot match — on a partitioned *or* an unpartitioned table. It carries none of
partitioning's query-shape obligations: no `RequirePartitionFilter`, so no `PARTITION_FILTER_REQUIRED`.
For a table too small to justify a partition key — the common case, see
[Should this table have a partition key?](partitioning.md#should-this-table-have-a-partition-key-p45) —
`clusterColumns` on the time column is the whole layout decision.

- User problem solved:
  - Keep range query pruning effective on very large time-oriented tables.
  - Accept out-of-order arrivals with no configuration: a late row is flushed like any other and is visible at once.
  - Partition directly from timestamp semantics without redundant bucket columns.
- Operational outcomes:
  - Better segment and page pruning from cluster-aware metadata.
  - Better write/read balance via bounded sort-on-seal.
  - Scalable startup through per-segment manifest metadata.
- Scope boundaries:
  - This document focuses on cluster declaration, partition functions, manifests, segment pruning, sort-on-seal, out-of-order data, and metadata caching tiers.
  - It does not cover replication cluster topology (that is a separate domain).
  - It does not claim all ADR examples are public API today.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What happens by default for clustered time-series tables? | `2.3 Defaults and zero-config behavior` |
| What is shipped versus proposed/reserved? | `2.4 Availability status` |
| Which phase delivered each capability? | `2.5 Phase coverage matrix` |
| End-to-end completeness by capability | `2.6 Capability coverage matrix` |
| Key architecture/runtime paths | `2.8 How Aouda implements it` |
| Full settings and defaults surface | `2.10 Configuration and settings reference` |
| .NET, TypeScript, and HTTP coverage gaps | `2.11 API and CLI coverage reference` |
| Operational tuning and diagnostics | `2.13 Operations and observability` |
| Current limitations and deferred work | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.3`, `2.11`, `2.12` |
| Platform operator | `2.10`, `2.13`, `2.14` |
| SDK maintainer | `2.11`, `2.17`, `2.18` |
| Engine contributor | `2.5`, `2.6`, `2.8`, `2.16` |

### Source map

- Task/report evidence:
  - `docs/tasks/P4/P4-EpicG-TimeSeriesClustering-Tasks.md`
  - `docs/tasks/P4/P4-EpicG-Task1-ClusterColumnDeclaration-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task2-PartitionFunctions-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task3-NestedDirectoryStorage-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task4a-SegmentManifestInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task4b-SegmentLevelClusterStatistics-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task5-SortOnSeal-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL004-MetadataCachingTiers-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL005-RetrospectivePartitioning-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL005b-EagerBlockingMigration-Report.md`
  - `docs/tasks/P8/P8-DeclarativeSchemaManagement-Tasks.md`
- Design references:
  - `docs/decisions/0014-time-series-clustering-optimization.md`
  - `docs/decisions/0009-partitioning-multitenancy.md`
  - `docs/decisions/0019-declarative-schema-management.md`
- Core code:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Catalog/CatalogApi.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionKeyExtractor.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionRouter.cs`
  - `src/Aouda.Engine.Storage/Sorting/ClusterSorter.cs`
  - `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs`
  - `src/Aouda.Engine.Storage/Manifest/ManifestSerializer.cs`
  - `src/Aouda.Engine.Storage/Manifest/SegmentSummaryCache.cs`
  - `src/Aouda.Engine.Storage/Manifest/PageSummaryCache.cs`
  - `src/Aouda.Engine.Storage/Query/Scan/TableScan.cs`
  - `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs`
  - `src/Aouda.Engine.Storage/Query/SegmentDiscoveryService.cs`
  - `src/Aouda.Engine.Storage/Compaction/KWayMergeExecutor.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
- TypeScript client code:
  - `../aouda-client-ts/src/types.ts`
  - `../aouda-client-ts/src/tables.ts`
- Test evidence:
  - `tests/Aouda.Server.Tests/ClusterColumnIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionFunctionIntegrationTests.cs`
  - `tests/Aouda.Engine.Catalog.Tests/PartitionFunctionTests.cs`
  - `tests/Aouda.Engine.Catalog.Tests/ClusterColumnTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Sorting/ClusterSorterTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Sorting/SortOnSealIntegrationTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/Manifest/ManifestSerializerTests.cs`
  - `tests/Aouda.Engine.Schema.Tests/Apply/SchemaApplyEngineTests.cs`

## 2.3 Defaults and zero-config behavior

If you create a partitioned time-series table and do not set advanced controls:

- Cluster declaration is opt-in (`clusterOrder` must be explicitly declared).
- Sort-on-seal is enabled by default in runtime table options (`SortOnSeal = true`), but only applies when cluster columns exist.
- Partition function default is `None` (raw partition value unless function declared).
- `PartitionOptions` defaults apply:
  - `StorageMode = Auto`
  - `RequirePartitionFilter = true`
- Late (out-of-order) rows need no configuration: they are buffered and flushed like any other row and are visible to queries as soon as they are inserted. Heavily out-of-order data only widens segment statistics (min/max), which costs pruning, never correctness. (`LateArrivalPolicy` / `LateArrivalThreshold` are deleted (**BL-762, next train**); they never changed behaviour.)
- Metadata caching policy defaults to `Auto` at table policy level.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `ColumnEntry.ClusterOrder` | `null` | No clustering unless explicitly declared |
| `ColumnEntry.PartitionFunction` | `null` / `None` | Partition routing uses raw key values |
| `TableOptions.SortOnSeal` | `true` | Clustered writes are sorted on seal by default |
| `PartitionOptions.StorageMode` | `Auto` | Shared buckets first, with possible dedicated promotion |
| `PartitionOptions.RequirePartitionFilter` | `true` | Partitioned queries require key filters unless bypassed |
| `TablePolicy.MetadataCaching` | `Auto` | Segment summaries resident; page summaries policy-driven |

## 2.4 Availability status (implementation honesty)

### Available now

- Cluster declaration via `clusterOrder` on create-table columns.
- Partition functions for key derivation:
  - `None`, `TruncateToDay`, `TruncateToHour`, `TruncateToMinute`, `TruncateToWeek`, `TruncateToMonth`, `TruncateToYear`.
- Nested partition paths under `partitions/` with shared bucket support.
- Segment manifest persistence with cluster stats and per-page metadata.
- Statistics-based skipping on every read: the one scan (`TableScan`) skips row groups whose min/max statistics rule the predicate out (`RowGroupClassifier`).
- Sort-on-seal behavior in storage pipeline for clustered data.
- Out-of-order rows with no special path: flushed like any other row, query-visible at once.
- Tiered metadata caching (`SegmentSummaryCache` and `PageSummaryCache`) with pressure-aware eviction.
- Schema file support for partition functions and cluster column lists (`partitionKey.function`, `clusterColumns`).

### Planned / proposed

- Broader end-user API knobs for clustering internals (for example full metadata cache controls and merge/size policies) are not exposed on HTTP/TypeScript surfaces yet.
- Additional ergonomics for retrospective partition migration operations remain iterative.
- ADR-level performance comparisons and guidance remain directional; production tuning still depends on workload-specific testing.

### Reserved / not yet wired

- ADR examples using integer divide partition functions (`DivideBy*`) are not present in the current `PartitionFunction` enum/runtime.
- `MigrationStrategy.Eager` and `MigrationStrategy.Blocking` are defined but marked phase-2 intent in policy comments.
- `MigrationOptions.MaxParallelism` and `MigrationOptions.BlockingTimeout` are defined but phase-2 only.
- Public HTTP/TS API does not currently expose `SortOnSeal`, `Migration`, or `MetadataCaching`.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P4 | Epic G tasks (G.1-G.5) + reports | Cluster declaration, partition functions, nested paths, manifests, segment stats pruning, sort-on-seal | Extended API surfacing for many advanced knobs | `docs/BACKLOG.md` (BL-004/005 completion notes) |
| P4 follow-ups | BL-004/005/005b reports | Metadata caching tiers, retrospective partitioning framework | Some migration strategy paths remain phase-2 scoped | `docs/BACKLOG.md` BL-005 phase-2 notes |
| P8 | Declarative schema management tasks | Schema format carries `partitionKey.function` and `clusterColumns`; apply/export/diff paths include these fields | Schema apply set no part of the partition options block at P8. Since P45 it sets `partitionStorage`, `initialBucketCount`, `promotionRowThreshold`, `promotionByteThreshold` and `pkUniqueness` — migration options are still not declarable. See [Partitioning `2.10`](partitioning.md#210-configuration-and-settings-reference-complete-surface) | `docs/tasks/P8/P8-DeclarativeSchemaManagement-Tasks.md`, `docs/tasks/P45/` |
| P28 (S1) | `docs/tasks/P28/` | `TruncateToMinute` partition function (`PartitionFunction = 6`); minute-level time partitioning; TypeScript `partitionFunction` string union extended | None | P28-COMPLETION |
| ColumnarRead / ColumnarRead2 | ColumnarRead S07, S14; ColumnarRead2 S04 | Removed: P4's late-arrival delta segments (G.6, BL-006/007/008) — the catalog is the only visibility authority and late rows flush like any other (S07); the old read engines — every read runs on one scan (S14); `LateArrivalPolicy` / `LateArrivalThreshold` (**BL-762, next train**) | None | — |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Declare cluster columns (`clusterOrder`) | Yes | No | No | G.1 report + `TableMessages.cs` + cluster integration tests | Consecutive ordering validation enforced |
| Declare partition key function per key column | Yes | No | No | G.2 report + `PartitionKeyExtractor.cs` + partition function tests | Type compatibility enforced in controller |
| `TruncateToMinute` partition function | Yes | No | No | P28 S1, `PartitionFunction = 6`, `PartitionKeyExtractor.TruncateToMinute` | Produces `YYYY-MM-DD-HH-mm` partition key; TypeScript union includes `"TruncateToMinute"` |
| Nested partition directory structure | Yes | No | No | G.3 report + `PartitionRouter.cs` + nested partition tests | Dedicated paths nested under `partitions/` |
| Segment manifest persistence at seal | Yes | No | No | G.4a report + `SegmentManifest.cs` + serializer tests | Fallback compatibility behavior preserved |
| Segment / row-group skipping via statistics | Yes | No | No | G.4b report + `RowGroupClassifier.cs` + read oracle tests | One classifier for every read; counter `SegmentsPrunedFully` updates |
| Sort-on-seal for clustered pages | Yes | No | No | G.5 report + `ClusterSorter.cs` + sort tests | Runtime default is on; effect only with cluster columns |
| Out-of-order (late) rows | Yes | No | No | ColumnarRead S07 | No special path or setting: flushed like any other row, visible at once |
| Metadata caching tiers | Yes | No | No | BL-004 report + summary/page caches | `Auto`, `InMemory`, `OnDemand` policy model |
| Retrospective partitioning strategies | No | Yes | No | BL-005/005b reports + `Policies.cs` | Foundation shipped; phase-2 strategy caveats remain |
| Public API control for sort-on-seal | No | No | Yes | `TableMessages.cs` + `types.ts` + controller create path | Not exposed in HTTP DTOs/TS typed API |

## 2.7 Core concepts and mental model

- Cluster columns:
  - Ordered storage hint (`clusterOrder`) for intra-segment/page ordering and pruning behavior.
- Partition function:
  - Transformation from source column value to partition key component.
- Segment manifest:
  - Per-segment persisted metadata: row bounds, per-column/page summaries, optional cluster stats.
- Segment pruning hierarchy:
  - Partition prune -> segment prune (`ClusterStats`) -> page prune -> row evaluation.
- Sort-on-seal:
  - Bounded sorting at seal/flush stages, not full historical re-sorting.
- Out-of-order (late) rows:
  - Not a separate path. A late row sits in the write buffer, then in a segment, like any other row, and queries see it as soon as it is inserted. The catalog is the only visibility authority. Out-of-order data can widen a segment's min/max statistics, which only costs pruning.
- Metadata caching tiers:
  - Segment summaries always lightweight and resident; page summaries are policy/pressure managed.

### A materialized query's result table clusters too, and you do not declare it {#mq-result-clustering}

A time-bucketed `aggregate` materialized query produces a result table you never wrote a
`clusterColumns` list for. **Its leading derived time bucket is the cluster column**
(`TruncateToMinute`, `TruncateToHour`, `TruncateToDay` …), chosen by the engine.

🔎 **What that buys is residency, not read speed.** The hot/cold sweep demotes the
least-recently-accessed segment first, which on time-ordered data is a good proxy for *keep recent
buckets resident, send historical ones to cold* — so a `residency.memoryRowCap` on a candle result
bounds what stays resident without your knowing the arrival rate. Without the ordering the proxy
would break: one still-updating current-bucket row would keep its whole segment hot, year-old buckets
included. See [Materialized queries §2.3.1](materialized.md#where-a-materialized-querys-result-lives).

**Only the leading time bucket clusters.** A plain group-by (ticker, user, account) carries no
temporal order, so clustering on it would cost a sort on every seal and buy nothing; a second bucket
over the same column is already ordered by the first. `filter`, `latestPerKey`, `firstPerKey` and
`topNPerGroup` results are untouched — they are keyed by identity, not by time.

Invariants:

- Cluster order and partition key order are validated as consecutive sequences starting at 1.
- Partition functions are only valid on partition key columns and must be type-compatible.
- Segment-level pruning is conservative: missing stats means include segment.
- No public API claim is made for controls that are only internal/runtime types.

## 2.8 How Aouda implements it

High-level runtime flow:

1. Table creation captures cluster/partition metadata in catalog.
2. Partition key extraction applies declared partition functions for routing.
3. Writes are flushed/sealed; clustered batches are sorted on seal.
4. Segment manifests are persisted with page metadata and optional cluster stats.
5. Every read takes the table's segments from the catalog and runs on one scan (`TableScan`), which skips segments and row groups whose statistics rule the predicate out (`RowGroupClassifier`).
6. Metadata caches accelerate repeated prune paths under bounded memory.

Key implementation anchors:

- Policy and defaults:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Catalog/CatalogApi.cs`
- API validation and mapping:
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
- Routing and extraction:
  - `src/Aouda.Engine.Storage/Partition/PartitionKeyExtractor.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionRouter.cs`
- Pruning and discovery:
  - `src/Aouda.Engine.Storage/Query/Scan/TableScan.cs`
  - `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs`
  - `src/Aouda.Engine.Storage/Query/SegmentDiscoveryService.cs`
- Manifest and caching:
  - `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs`
  - `src/Aouda.Engine.Storage/Manifest/ManifestSerializer.cs`
  - `src/Aouda.Engine.Storage/Manifest/SegmentSummaryCache.cs`
  - `src/Aouda.Engine.Storage/Manifest/PageSummaryCache.cs`
- Merge and compaction:
  - `src/Aouda.Engine.Storage/Compaction/KWayMergeExecutor.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Table create with cluster and partition function

1. `POST /api/databases/{db}/tables` enters `TablesController.CreateTable(...)`.
2. Controller validates:
   - `clusterOrder` sequence continuity.
   - `partitionKeyOrder` continuity.
   - `partitionFunction` enum + type compatibility (`PartitionKeyExtractor.IsCompatible`).
3. Controller creates `PartitionOptions` from `partitionStorage` or defaults.
4. Table entry is persisted with cluster/partition metadata.

Primary tests:

- `tests/Aouda.Server.Tests/ClusterColumnIntegrationTests.cs`
- `tests/Aouda.Server.Tests/PartitionFunctionIntegrationTests.cs`
- `tests/Aouda.Engine.Catalog.Tests/PartitionFunctionTests.cs`

### Walk-through B: Segment seal with sort-on-seal and manifest write

1. Flush/compaction builds a row batch for segment/page write.
2. `ClusterSorter.ShouldSort(...)` checks runtime options and cluster column presence.
3. Batch is reordered by cluster keys when sorting applies.
4. Segment persists and manifest is written with per-column/page metadata and cluster stats.
5. Manifest becomes startup/query metadata source, reducing header-scan overhead.

Primary tests:

- `tests/Aouda.Engine.Storage.Tests/Sorting/SortOnSealIntegrationTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Sorting/ClusterSorterTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Manifest/ManifestSerializerTests.cs`

### Walk-through C: Query with segment and row-group skipping

1. The read takes the table's segments from the catalog (`SegmentDiscoveryService.FromCatalog(...)`); no directory is listed, so a segment the catalog does not name is never read.
2. Every read runs on one scan (`TableScan`) with one predicate evaluator.
3. `RowGroupClassifier` decides each segment / row group from its min/max statistics: none can match (skipped), all match, or some (decoded and evaluated). Missing statistics mean "some", so skipping is always conservative.
4. Rows still in the write buffer are read in the same pass, so a just-inserted row (late or not) is visible at once.

Primary tests:

- `tests/Aouda.Engine.Api.Tests/ColumnarRead/ReadRuleOracle*Tests.cs`
- `tests/Aouda.Engine.Storage.Tests/HotSegmentClusterStatsTests.cs`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Must users add redundant time bucket columns? | Common in many setups | Partition functions derive bucket keys from original columns | Cleaner schemas and less duplicate write logic |
| Is clustering always full-table sort/merge heavy? | Often yes for maximal ordering | Bounded sort-on-seal plus manifest-aware pruning | Lower write amplification with strong pruning gains |
| Are late arrivals "invisible until compaction"? | Sometimes delayed | Late rows take the normal write path and are query-visible as soon as they are inserted | Better freshness for out-of-order event streams, with nothing to configure |
| Is startup metadata loading page-scan heavy? | Can be expensive at scale | Segment manifest metadata with tiered caching | Faster startup and better memory control |
| Is feature intent and implementation split explicit? | Often mixed in docs | This doc separates shipped/proposed/reserved with code-backed claims | Safer operational and product decisions |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `CreateColumnRequest.clusterOrder` | int? | `null` | `1..N` consecutive | HTTP create-table body | Cluster declaration only |
| `CreateColumnRequest.partitionFunction` | string? | `null` | `None`, `TruncateToDay`, `TruncateToHour`, `TruncateToMinute`, `TruncateToWeek`, `TruncateToMonth`, `TruncateToYear` | HTTP create-table body | Must be on partition key columns |
| `CreateTableRequest.partitionStorage` | string? | `Auto` (if partition key present) | `Auto`, `Dedicated`, `Shared` | HTTP create-table body | Maps to `PartitionOptions.StorageMode` |
| `PartitionOptions.RequirePartitionFilter` | bool | `true` | `true/false` | .NET engine/catalog | No direct HTTP/TS field today |
| `PartitionOptions.PromotionRowThreshold` | long | `10000000` | `>=0` | .NET engine/catalog | Auto-promotion tuning |
| `PartitionOptions.PromotionByteThreshold` | long | `1000000000` | `>=0` | .NET engine/catalog | Auto-promotion tuning |
| `PartitionOptions.InitialBucketCount` | int | `16` | `>=1` | .NET engine/catalog | Shared bucket count |
| ~~`PartitionOptions.LateArrivalPolicy` / `LateArrivalThreshold`~~ | — | — | — | — | Deleted (**BL-762, next train**): `Delta` behaved as `Inline` and `Reject` was never enforced. A late row is flushed like any other. |
| `PartitionOptions.Migration` | object? | `null` | `MigrationOptions` | .NET engine/catalog | Retrospective partition migration controls |
| `MigrationOptions.Strategy` | enum | `None` | `None`, `Background`, `Eager`, `Blocking` | .NET engine/catalog | `Eager`/`Blocking` marked phase-2 |
| `MigrationOptions.BatchSize` | int | `100000` | `>0` | .NET engine/catalog | Background migration chunking |
| `MigrationOptions.BatchDelay` | `TimeSpan` | `10s` | Positive duration | .NET engine/catalog | Background migration pacing |
| `MigrationOptions.MaxIoBandwidthPercent` | int | `15` | `1..100` | .NET engine/catalog | Migration pressure cap |
| `MigrationOptions.MaxParallelism` | int | `2` | `>=1` | .NET engine/catalog | Phase-2 property |
| `MigrationOptions.BlockingTimeout` | `TimeSpan` | `1h` | Positive duration | .NET engine/catalog | Phase-2 property |
| `TableOptions.SortOnSeal` | bool | `true` | `true/false` | Core runtime option | No HTTP/TS toggle today |
| `TablePolicy.MetadataCaching` | enum | `Auto` | `Auto`, `InMemory`, `OnDemand` | .NET/catalog policy | No HTTP/TS create-table field today |

Configuration precedence and operational notes:

- Precedence:
  - Request-level table creation fields map first into catalog metadata.
  - Internal defaults apply for omitted partition and runtime options.
- Dynamic vs restart-required:
  - Table create metadata is dynamic at runtime.
  - Manifest/cache behavior is runtime and adapts during normal execution.
- Safety-gated:
  - Invalid cluster/partition order and incompatible partition functions are rejected at API boundary.
- Deprecated/reserved:
  - Migration phase-2 properties are intentionally documented but not promoted as fully wired behavior.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (engine create with partition function + clustering)

```csharp
var tableId = await engine.CreateTableAsync(
    "metrics",
    new[]
    {
        ("sensor_id", DataType.String, EncoderPreference.Auto, false, (int?)null, 1, (int?)null, (PartitionFunction?)null),
        ("ts", DataType.Timestamp, EncoderPreference.Auto, false, (int?)null, 2, 1, PartitionFunction.TruncateToDay),
        ("value", DataType.Double, EncoderPreference.Auto, false, (int?)null, (int?)null, (int?)null, (PartitionFunction?)null)
    },
    partitionOptions: new PartitionOptions
    {
        StorageMode = PartitionStorage.Auto
    });
```

Expected result: table metadata includes cluster order and partition function; inserts route by derived day partition. Late rows need no option.

Common mistake: assuming these advanced partition options are available through current HTTP create-table DTO.

### TypeScript example (cluster and partition function in create-table request)

```typescript
await client.tables.createTable({
  database: "appdb",
  name: "metrics",
  columns: [
    { name: "sensor_id", type: "String", partitionKeyOrder: 1 },
    { name: "ts", type: "Timestamp", partitionKeyOrder: 2, partitionFunction: "TruncateToDay", clusterOrder: 1 },
    { name: "value", type: "Double" }
  ],
  policy: { storageTemperature: "Auto" }
});
```

Expected result: cluster and partition function are sent and persisted.

Common mistake: expecting TypeScript typed API to expose `partitionStorage` or `sortOnSeal` fields.

### HTTP/protocol example

```http
POST /api/databases/appdb/tables
Content-Type: application/json

{
  "database": "appdb",
  "name": "metrics",
  "partitionStorage": "Auto",
  "columns": [
    { "name": "sensor_id", "type": "String", "partitionKeyOrder": 1 },
    { "name": "ts", "type": "Timestamp", "partitionKeyOrder": 2, "partitionFunction": "TruncateToDay", "clusterOrder": 1 },
    { "name": "value", "type": "Double" }
  ]
}
```

Expected result: table is created with partition and cluster metadata.

Common mistake: sending unsupported fields like `sortOnSeal` and expecting server-side binding in this endpoint.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Declare `clusterOrder` | Engine create table tuple | `CreateColumnRequest.clusterOrder` | `POST /api/databases/{db}/tables` columns | Implemented | End-to-end |
| Declare `partitionFunction` | Engine create table tuple (`PartitionFunction`) | `CreateColumnRequest.partitionFunction` | Same create-table endpoint | Implemented | End-to-end |
| Set partition storage mode | `PartitionOptions.StorageMode` | No typed field | `partitionStorage` field on create table | Partial | TS type gap |
| Set sort-on-seal | Core `TableOptions.SortOnSeal` | No typed field | No field | Partial | Runtime default applies |
| Set metadata cache policy | `TablePolicy.MetadataCaching` | No typed field | No field | Partial | Internal/.NET policy surface |
| Query sees late rows at once | Engine query path | Indirect (normal query APIs) | Query endpoints unchanged | Implemented | Transparent to callers; nothing to configure |
| Schema carries cluster columns and partition functions | Schema models/export/apply | Schema CLI paths | `/api/.../schema` introspection | Implemented | Partition options not carried in schema apply create path |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Set `partitionStorage` from TS typed `createTable` | Missing property in TS `CreateTableRequest` type | Use untyped extension cast or .NET/HTTP | Follow-up TS client parity work | Medium |
| Configure `SortOnSeal` over HTTP/TS | No DTO fields | Runtime default currently on | Future protocol/SDK expansion | Medium |
| Configure metadata cache policy over HTTP/TS | No public API field | Internal policy defaults / .NET policy path | Follow-up API surfacing | Medium |
| Expose migration strategy controls in HTTP/TS | No create/update endpoint fields | .NET internal configuration path | Future admin/schema API work | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run time-series baseline

When to use:
- New time-series table where you want safe defaults plus basic clustering.

Steps:
1. Create table with one cluster column and one partition function (`TruncateToDay`).
2. Insert mostly ordered time data.
3. Run narrow timestamp-range queries.

Expected result checks:
- Table schema readback includes `clusterOrder` and `partitionFunction`.
- Query stats show bounded segment/page scanning for narrow ranges.
- No additional tuning needed for initial correctness path.

### Scenario 2: Out-of-order ingestion with immediate query visibility

When to use:
- Backfill/replay events arrive after their primary historical window.

Steps:
1. Nothing to configure: late rows take the normal write path.
2. Insert on-time rows, then insert late rows with older timestamps.
3. Query the historical range straight away.

Expected result checks:
- Late rows are visible in query results immediately (from the write buffer, then from a segment).
- If the stream is heavily out of order, segments' min/max ranges widen and range queries skip fewer segments; results stay correct.

### Scenario 3: Scale read path with manifest and metadata caches

When to use:
- Many-segment tables where startup and first-query latency matter.

Steps:
1. Verify manifests exist for sealed segments.
2. Execute repeated range queries on clustered columns.
3. Observe cache metrics/counters for segment/page summary usage and evictions.

Expected result checks:
- Segment-level pruning counter increases.
- Page summary cache hit rate improves on repeated range queries.
- Memory pressure triggers controlled LRU eviction rather than unbounded growth.

## 2.13 Operations and observability

Monitor first:

- Pruning effectiveness:
  - `SegmentsPrunedFully` (segments the scan skipped entirely from their statistics)
- Sort-on-seal:
  - `PagesSortedOnSeal`
- Manifests:
  - `manifestsRead` — the only field left in the metrics endpoint's `timeSeries` object (`deltaSegmentsCreated` and `lateArrivalsRouted` were removed with the features they counted).
- Metadata cache health:
  - Segment/page summary cache hits, misses, bytes, evictions, manifest loads

Recovery/restart expectations:

- Segment manifests are persisted and reused on restart.
- Missing manifests fall back to compatible behavior.
- Cache state is runtime-only and warms with access patterns.

Suggested tuning sequence:
1. Start with cluster + partition function declarations only.
2. Observe pruning counters.
3. Tune partition storage mode in .NET paths if needed.
4. Adjust migration and caching policy only after baseline behavior is stable.

| Question | Practical answer |
|---|---|
| What confirms segment-level pruning is active? | `SegmentsPrunedFully` rising on range queries |
| How can I tell late data is not lost? | Query its time range: a late row is visible as soon as its insert returns; there is no separate late path to lose it on |
| How do I detect cache pressure? | Rising page summary evictions and pressure eviction counters |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `400` on create-table with cluster columns | Non-consecutive `clusterOrder` values | Use contiguous order (`1,2,3...`) |
| `400` for partition function | Unsupported function name or incompatible type | Use valid enum values and compatible timestamp/date/int type |
| Code setting `LateArrivalPolicy` / `LateArrivalThreshold` no longer compiles | Both options are deleted (**BL-762, next train**); they never changed behaviour | Remove them: late rows need no configuration and are flushed like any other row |
| Range query scans too much | Missing/weak clustering metadata, broad predicate, or heavily out-of-order data widening segment min/max | Validate cluster declaration and predicate shape; inspect prune counters |
| TS createTable cannot set partition storage | Type surface gap | Use HTTP or .NET path for now; track parity follow-up |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Server API cluster and partition function integration | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~ClusterColumnIntegrationTests|FullyQualifiedName~PartitionFunctionIntegrationTests" --verbosity minimal` | Pass (`40/40`) | 2026-03-31 | Covers create-table validation and protocol path |
| Storage engine clustering/time-series core | `dotnet test tests/Aouda.Engine.Storage.Tests --no-build --filter "FullyQualifiedName~ClusterSorterTests|FullyQualifiedName~SortOnSealIntegrationTests|FullyQualifiedName~ManifestSerializerTests|FullyQualifiedName~RetrospectivePartitioningTests" --verbosity minimal` | Pass (2026-03-31 run, which also included since-deleted delta/routing suites) | 2026-03-31 | Covers sorter, manifests, migration |
| Engine API partition query integration | `dotnet test tests/Aouda.Engine.Api.Tests --no-build --filter "FullyQualifiedName~PartitionKeyExtractorTests|FullyQualifiedName~TableQueryPartitionTests" --verbosity minimal` | Pass (2026-03-31 run, which also included since-deleted delta/flush-routing suites) | 2026-03-31 | Covers partition key extraction and partitioned queries |
| Catalog persistence for cluster/function metadata | `dotnet test tests/Aouda.Engine.Catalog.Tests --no-build --filter "FullyQualifiedName~CatalogPersistenceTests|FullyQualifiedName~PartitionFunctionTests|FullyQualifiedName~ClusterColumnTests" --verbosity minimal` | Pass (`43/43`) | 2026-03-31 | Ensures persisted metadata survives read/write cycle |
| TypeScript client table/schema surface | `npm test -- tests/tables.test.ts tests/schema/snapshots.test.ts` (in `../aouda-client-ts`) | Pass (`48/48`) | 2026-03-31 | Confirms TS table API and schema snapshots |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Cluster order declaration and validation | `ClusterColumnIntegrationTests.cs`, `ClusterColumnTests.cs` | Pass | Strong | Covers schema and API validation paths |
| Partition function extraction/compatibility | `PartitionFunctionIntegrationTests.cs`, `PartitionFunctionTests.cs`, `PartitionKeyExtractorTests.cs` | Pass | Strong | Covers function parsing and key generation |
| Sort-on-seal behavior | `SortOnSealIntegrationTests.cs`, `ClusterSorterTests.cs` | Pass | Strong | Includes row reordering and conditions |
| Segment manifest serialization | `ManifestSerializerTests.cs`, `CatalogPersistenceTests.cs` | Pass | Medium/Strong | Focused on metadata correctness and compatibility |
| Segment / row-group skipping from statistics | `ColumnarRead/ReadRuleOracle*Tests.cs`, `ColumnarRead/ReadFuzzTests.cs`, `HotSegmentClusterStatsTests.cs` | Pass (existing) | Strong | Every skipping rule has an oracle case against an unpruned read |
| Retrospective partition migration behavior | `RetrospectivePartitioningTests.cs`, `EagerBlockingMigrationTests.cs` | Pass | Medium | Includes strategy behavior and constraints |
| Schema apply/export handling for cluster/partition functions | `SchemaApplyEngineTests.cs`, `SchemaExporterTests.cs`, `SchemaDiffEngineTests.cs` | Pass (existing) | Medium | Confirms schema model handling boundaries |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No end-to-end HTTP contract test for advanced partition options absence | Prevents accidental assumption that sort/cache/migration knobs are public | Add server contract test asserting unknown fields are ignored/rejected as intended | High |
| Limited explicit tests around metadata cache policy switching by table policy | Cache policy drift can impact performance and memory | Add integration test toggling `MetadataCaching` and asserting cache behavior counters | Medium |
| Missing cross-surface parity test (.NET create with advanced options -> API readback expectations) | Users need clarity on what is and is not visible through API | Add parity test verifying advanced options behavior while API omits unsupported fields | Medium |

## 2.18 Known gaps and undone work

- Public surface gaps:
  - HTTP/TypeScript create-table does not expose sort-on-seal, metadata cache policy, or migration options.
  - User impact: advanced behavior remains mostly .NET/internal configuration.
- TypeScript parity gap:
  - TS `CreateTableRequest` type does not include `partitionStorage` even though server endpoint supports it.
  - User impact: typed client cannot express storage mode directly without workaround.
- Partition function scope gap:
  - ADR examples mention `DivideBy*` variants; current runtime enum does not include these values.
  - User impact: integer bucketing options are narrower than ADR narrative examples.
- Migration strategy caveat:
  - `Eager`/`Blocking` strategy members and associated options are documented as phase-2 in policy comments.
  - User impact: treat these as limited/conditional rather than universally available production defaults.

## 2.19 References

- ADRs:
  - `docs/decisions/0014-time-series-clustering-optimization.md`
  - `docs/decisions/0009-partitioning-multitenancy.md`
  - `docs/decisions/0019-declarative-schema-management.md`
- Tasks/reports:
  - `docs/tasks/P4/P4-EpicG-TimeSeriesClustering-Tasks.md`
  - `docs/tasks/P4/P4-EpicG-Task1-ClusterColumnDeclaration-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task2-PartitionFunctions-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task3-NestedDirectoryStorage-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task4a-SegmentManifestInfrastructure-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task4b-SegmentLevelClusterStatistics-Report.md`
  - `docs/tasks/P4/P4-EpicG-Task5-SortOnSeal-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL004-MetadataCachingTiers-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL005-RetrospectivePartitioning-Report.md`
  - `docs/tasks/P4/P4-EpicG-BL005b-EagerBlockingMigration-Report.md`
  - `docs/tasks/P8/P8-DeclarativeSchemaManagement-Tasks.md`
- Backlog:
  - `docs/BACKLOG.md` (BL-004, BL-005 status context)
- Key code paths:
  - `src/Aouda.Engine.Catalog/Policies.cs`
  - `src/Aouda.Engine.Catalog/CatalogApi.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionKeyExtractor.cs`
  - `src/Aouda.Engine.Storage/Partition/PartitionRouter.cs`
  - `src/Aouda.Engine.Storage/Sorting/ClusterSorter.cs`
  - `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs`
  - `src/Aouda.Engine.Storage/Manifest/ManifestSerializer.cs`
  - `src/Aouda.Engine.Storage/Manifest/SegmentSummaryCache.cs`
  - `src/Aouda.Engine.Storage/Manifest/PageSummaryCache.cs`
  - `src/Aouda.Engine.Storage/Query/Scan/TableScan.cs`
  - `src/Aouda.Engine.Storage/Query/Scan/RowGroupClassifier.cs`
  - `src/Aouda.Engine.Storage/Query/SegmentDiscoveryService.cs`
  - `src/Aouda.Engine.Storage/Compaction/KWayMergeExecutor.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `../aouda-client-ts/src/types.ts`
  - `../aouda-client-ts/src/tables.ts`
- Related functionality docs:
  - `docs/dev/Functionality-Partitioning-And-Multitenancy.md`
  - `docs/dev/Functionality-Query-Execution.md`
  - `docs/dev/Functionality-Schema-Lifecycle.md`

## 2.20 What is missing from this document? (meta completeness)

- This document does not include full line-by-line pseudocode for scan and flush internals.
- The verification ledger is targeted to this domain and does not claim full-repo green status.
- If public API surface expands for advanced partition/cluster controls, sections `2.10` and `2.11` must be updated immediately.
