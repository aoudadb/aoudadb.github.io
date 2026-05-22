---
title: "Graph and Vector"
nav_order: 18
parent: "Guides"
---

# Aouda Functionality: Graph and Vector Storage

Document status: Complete
Primary owner: Engineering
Last updated: 2026-05-19

Coverage phases: P20, BL (Post20-S2)
Primary task folders: `docs/tasks/P20/`, `docs/tasks/P20/BL-Post20-S2-Stage4-ADR-And-Roadmap.md`
Primary ADRs: `docs/decisions/0027-columnar-native-graph-and-vector.md`, `docs/decisions/0031-stage4-frozen-tier.md`
Related functionality docs: `docs/dev/Functionality-Storage-And-Persistence.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Write-Path-Durability.md`, `docs/dev/Functionality-Auth-And-Authorization.md`

---

## Start Here

If your question is "How do I store and query graph edges?", start with:
- §2.7 Core concepts (edge table primitive)
- §2.11 API coverage: `.NET` edge examples
- §2.12 Scenario: Build and traverse a social graph

If your question is "How do I store embeddings and run nearest-neighbor search?", start with:
- §2.7 Core concepts (vector column primitive)
- §2.11 API coverage: `.NET` vector examples
- §2.12 Scenario: Embed documents and query top-K

If your question is "What is implemented vs missing?", jump to:
- §2.4 Availability status
- §2.5 Phase coverage matrix
- §2.6 Capability coverage matrix

If your question is "What do the reserved frozen-tier manifest fields mean?", jump to:
- §2.4 Availability status — Reserved section
- §2.10 Configuration reference — Stage-4 reservation fields

| If you need to know… | Go to section |
|---|---|
| Zero-config defaults | §2.3 |
| What is shipped vs planned vs reserved | §2.4 |
| Phase-by-phase delivery history | §2.5 |
| Comprehensive capability table | §2.6 |
| Mental model and invariants | §2.7 |
| Storage architecture and critical paths | §2.8 |
| Why Aouda is different | §2.9 |
| Config settings table | §2.10 |
| Full API reference with examples | §2.11 |
| Scenario playbooks | §2.12 |
| Monitoring and operations | §2.13 |
| Troubleshooting | §2.14 |
| Test coverage | §2.16 |
| Known gaps and open backlog items | §2.18 |

---

## 2.1 Why this functionality exists

### User problem

AI applications require three data modalities — structured rows, graph relationships, and embeddings — with a single permission model, a single tiering policy, and zero ETL between them. The standard alternative is stacking Postgres, a graph database, and a vector database: three on-call rotations, duplicated identity models, brittle ETL, and no cross-modal authorization guarantee.

### Operational outcome

A single Aouda engine instance can store tabular fact rows, graph edge relationships, and dense vector embeddings in the same physical storage tree, served by the same WAL, replicated by the same replication substrate, and governed by the same ADRA authorization model. The unified retrieval pipeline (filter → ANN → graph expand → re-rank) runs inside one database.

### Scope boundaries (Stage 1)

Stage 1 (P20) delivers storage primitives and method-level query operators. It does not deliver:
- SQL/PGQ graph query language (Stage 2)
- The `Retrieve` hybrid pipeline operator (Stage 2)
- Workload-adaptive HNSW index construction (Stage 3)
- ACORN-1 filtered-HNSW for medium-selective filters (Stage 3)
- Frozen object-storage tier runtime (Stage 4; catalog reservation fields are present)
- Distributed graph traversal across replicas
- Embedding generation on insert (caller must provide embeddings)
- `MdVector` query path beyond storage (FDE companion column and MaxSim rerank land in Stage 2)

---

## 2.2 Discovery and navigation map

**Role-based map:**

| Role | Where to start |
|---|---|
| App developer (graph) | §2.11 `.NET` edge examples → §2.12 Scenario 1 |
| App developer (vector ANN) | §2.11 `.NET` vector examples → §2.12 Scenario 2 |
| Operator (monitoring/troubleshooting) | §2.13 Observability → §2.14 Troubleshooting |
| SDK maintainer | §2.8 Architecture → §2.8.1 Critical paths |
| Engine contributor | §2.8.1 paths → §2.16 Test coverage → §2.17 Gaps |

**Source map:**

| Source | Location |
|---|---|
| Primary implementation record | `docs/tasks/P20-COMPLETION.md` |
| Storage primitive ADR | `docs/decisions/0027-columnar-native-graph-and-vector.md` |
| Frozen-tier reservation ADR | `docs/decisions/0031-stage4-frozen-tier.md` |
| Stage-4 ADR and roadmap update | `docs/tasks/P20/BL-Post20-S2-Stage4-ADR-And-Roadmap.md` |
| Core schema types | `src/Aouda.Engine.Core/Schema/VectorConfig.cs`, `src/Aouda.Engine.Core/Schema/Types.cs` |
| Engine API | `src/Aouda.Engine.Api/AoudaEngine.cs` |
| Edge storage | `src/Aouda.Engine.Storage/Edge/`, `src/Aouda.Engine.Storage/Hra/EdgeHraBuffer.cs` |
| Vector storage | `src/Aouda.Engine.Storage/Vector/`, `src/Aouda.Engine.Storage/Hra/VectorHraBuffer.cs` |
| Query operators | `src/Aouda.Engine.Query/Operators/` |
| Segment manifest | `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs` |

---

## 2.3 Defaults and zero-config behavior

| Setting / behavior | Default | Practical impact |
|---|---|---|
| Edge table CSC mirror (`StoreCsc`) | `false` | Backward traversal (e.g. reverse `ShortestPath` with bidirectional BFS) requires `StoreCsc: true` at table creation. With `false`, `ShortestPath` uses unidirectional BFS. |
| Edge table label (`EdgeLabel`) | `null` | No label filter on traversal operators; all edges in the table are considered one type. |
| Vector quantization (`VectorQuantization`) | `None` (hot), `RaBitQ` when sealing cold | Hot segments store raw `float32`. Cold sealing applies RaBitQ by default when `Quantization` is set in `VectorColumnConfig`. Passing `None` in `VectorColumnConfig` stores raw floats in cold segments too. |
| IVF cell count (`IvfCells` in `VectorColumnConfig`) | Caller-specified; no engine-side heuristic override | The engine uses exactly the value supplied. For small corpora (<10K vectors), `IvfCells = 1` (single cell, brute-force) is effective. For 1M+ vectors a common starting point is `sqrt(N)` cells. |
| Distance metric (`VectorDistance`) | Caller-specified | No default; must be set explicitly in `VectorColumnConfig`. Cosine for normalized embeddings; L2 for Euclidean spaces; DotProduct for asymmetric models. |
| Embedding model version on insert | `null` | When `null`, segment manifests record no model version. Specify `embeddingModelVersion` in `InsertVectorsAsync` to enable multi-model coexistence and future Drift-Adapter migration (Stage 2). |
| MdVector FDE auto-derive (`Fde`) | `true` | The `MdVectorColumnConfig` property reserves a Fixed Dimensional Encoding companion column slot for Stage 2. No FDE is computed in Stage 1; the field is stored only. |
| `PkUniqueness` on edge tables | `PkUniquenessMode.Strict` | Same enforcement as tabular tables. |

---

## 2.4 Availability status

### Available now (Stage 1 — P20)

**Edge tables:**
- `TableKind.EdgeTable` catalog kind with `EdgeTableConfig` (`SrcColumn`, `DstColumn`, `EdgeLabel`, `StoreCsc`)
- Edge WAL frames: `WalTag.EdgeInsert`, `WalTag.EdgeDelete`; replay produces `EdgeHraBuffer` state
- `EdgeHraBuffer` — in-memory hot write area; freeze-and-swap flush to sealed CSR segments
- `EdgeSegmentFlusher` — produces sealed segments with `(src, dst)` CSR layout
- `CscMirrorWriter` — optional CSC companion segments (`csc_*` files) for bidirectional traversal
- Edge late-arrival `_delta/` merge (`DeltaMerger.cs` edge-safe behavior)
- Partition routing by source-node partition key
- `CreateEdgeTableAsync`, `InsertEdgesAsync`, `DeleteEdgeAsync` on `AoudaEngine`
- Graph traversal operators: `TraverseAsync` (BFS k-hop reachability), `KHopNeighborhoodAsync` (BFS with hop distance), `ShortestPathAsync` (bidirectional BFS with CSC; unidirectional without)

**Vector columns:**
- `DataType.Vector` column type with `VectorColumnConfig` (`Dimensions`, `Distance`, `Quantization`, `IvfCells`, `EmbeddingModel`, `EmbeddingModelVersion`, `MatryoshkaDims`)
- Vector WAL frames: `WalTag.VectorInsert`, `WalTag.VectorDelete`; replay produces `VectorHraBuffer` state
- `VectorHraBuffer` — in-memory hot write area; freeze-and-swap flush per IVF cell
- `IvfCentroidStore` — persists IVF centroids trained by `KMeansHelper`
- `VectorSegmentFlusher` — seals vectors per IVF cell; writes raw fp32 pages + `*.rabitq` / `*.pq` companion files
- Vector late-arrival `_delta/` merge: cell-aware delta classification
- `InsertVectorsAsync`, `DeleteVectorAsync` on `AoudaEngine`
- ANN search operator: `NearestNeighborsAsync` (IVF-pruned brute-force scan, Stage 1)
- ADRA authorization for vector queries via `IVectorAccessFilter` / `AdraVectorAccessFilter` (wired in P24; ADR 0032)
- ADRA authorization for edge traversal via `IEdgeAccessFilter` / `AdraEdgeAccessFilter` (wired in P24; ADR 0032)

**MdVector storage:**
- `DataType.MdVector` column type with `MdVectorColumnConfig` (`Dimensions`, `MaxTokens`, `Distance`, `Fde`)
- `MdVectorColumnWriter` / `MdVectorColumnReader` — variable-length multi-vector column files (`col_{colId}_mdvec.bin`)
- On-disk storage format for ColBERT/ColPali style multi-vector rows

**Stage-4 frozen-tier catalog reservations (schema only; no Stage-4 runtime):**
- `SegmentManifest` fields: `FrozenTierLayoutVersion` (default `0`), `HierarchicalSpfreshCentroids` (default `null`), `S3CompatibleHeader` (default `null`), `SelfDescribingMagic` (default `0`), `EmbeddingModelVersion`, `IvfCellId`, `QuantizationMethod`
- Fields documented by ADR 0031; reserved so Stage-4 implementation (P23) can start without manifest rework

### Planned / proposed (committed in shape)

| Planned capability | Stage | ADR / source |
|---|---|---|
| SQL/PGQ graph query language | Stage 2 | ADR 0027 (columnar) §Stage-2 |
| `Retrieve` hybrid pipeline operator (filter → ANN → graph expand → re-rank) | Stage 2 | ADR 0027 (columnar) §Stage-2 |
| `MdVector` FDE column auto-derivation and MaxSim rerank operator (MUVERA) | Stage 2 | ADR 0027 (columnar) §Stage-2 |
| Drift-Adapter embedding model upgrade (sub-µs linear/MLP mapping) | Stage 2 | ADR 0027 (columnar) §Open-Question 7 |
| Filtered ANN layer 2: pre-filter + brute-force for small post-prune sets | Stage 2 | ADR 0027 (columnar) §Filtered-ANN |
| Workload-adaptive HNSW sub-index construction per IVF cell | Stage 3 | ADR 0027 (columnar) §Stage-3 |
| ACORN-1 filtered-HNSW for medium-selective filters | Stage 3 | ADR 0027 (columnar) §Stage-3 |
| Materialized retrieval queries (k-hop neighborhoods, top-K per query) | Stage 3 | ADR 0027 (columnar) §Stage-3; ADR 0015 |
| Optional Cypher subset for ecosystem compatibility | Stage 3 | ADR 0027 (columnar) §Alternatives-G |
| Frozen object-storage tier (hierarchical SPFresh centroids, S3-native segments) | Stage 4 | ADR 0031 |
| GraphAr import/export format support | Backlog | BL-064 |
| Iceberg-style bulk-load time travel for graph/vector segments | Backlog | BL-065 |

### Reserved / not yet wired

| Reserved surface | State | Where documented |
|---|---|---|
| `FrozenTierLayoutVersion` in `SegmentManifest` | Field exists, value `0`, no runtime behavior | ADR 0031 Decision-6; `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs` lines 71–83 |
| `HierarchicalSpfreshCentroids` in `SegmentManifest` | Field exists, value `null`, no runtime behavior | ADR 0031 Decision-6 |
| `S3CompatibleHeader` in `SegmentManifest` | Field exists, value `null`, no runtime behavior | ADR 0031 Decision-6 |
| `SelfDescribingMagic` in `SegmentManifest` | Field exists, value `0` (not a frozen segment), magic constant not yet finalized for P23 | ADR 0031 Decision-6 |
| `MdVectorColumnConfig.Fde` | Field stored; FDE column not computed until Stage 2 | ADR 0027 (columnar) §Decision: MdVector |
| `MatryoshkaDims` in `VectorColumnConfig` | Field stored in catalog; tiered retrieval not yet implemented | ADR 0027 (columnar) §Decision: Vector |
| MCP tool extensions: `aouda_traverse`, `aouda_search_vector`, `aouda_retrieve` | Not shipped; ADR 0017 intent | ADR 0027 (columnar) §Migration notes |
| Embedded-mode MCP auth tools | Not shipped | ADR 0017 |
| GPU-accelerated IVF centroid training | Out of scope; BSL engine | ADR 0027 (columnar) §What-not-decided |

---

## 2.5 Phase coverage matrix

| Phase | Tasks / reports | Delivered capability | Undone / deferred | Backlog |
|---|---|---|---|---|
| P20 Epic A | `docs/tasks/P20/` P20-S1 | `TableKind.EdgeTable`, `DataType.Vector`/`MdVector`, `VectorColumnConfig`, `MdVectorColumnConfig`, `EdgeTableConfig`, catalog WAL framing, MCP tool name reservations, Stage-4 manifest stubs | — | — |
| P20 Epic B | `docs/tasks/P20/` P20-S2–S4 | Edge WAL/HRA (`EdgeHraBuffer`), `EdgeSegmentFlusher` (CSR), `CscMirrorWriter` (CSC), edge delta merge | CSC-based traversal acceleration limited by WAL replay coverage at Stage 1 | — |
| P20 Epic C | `docs/tasks/P20/` P20-S5–S7 | Vector WAL/HRA (`VectorHraBuffer`), `IvfCentroidStore`, `VectorSegmentFlusher` (per-cell), RaBitQ/PQ encoders, vector delta merge, MdVector column format | FDE column derivation deferred to Stage 2 | BL-065 (time travel) |
| P20 Epic D | `docs/tasks/P20/` P20-S8 | `TraverseOperator`, `KHopNeighborhoodOperator`, `ShortestPathOperator`, `NearestNeighborsOperator`; public `AoudaEngine` methods | SQL/PGQ, `Retrieve` pipeline, MaxSim rerank, HNSW deferred | BL-064 (GraphAr) |
| P20 Epic E | `docs/tasks/P20/` P20-S9–S11 | `BulkLoadAsync` engine primitive; HTTP protocol (`:begin/:append/:commit/:abort/:status/list/force-abort`); C# and TS client surfaces; CLI bulk-load commands | Peer-to-peer segment fan-out, persistent bulk-load sessions across restart | BL-066, BL-067 |
| BL-Post20-S2 | `docs/tasks/P20/BL-Post20-S2-Stage4-ADR-And-Roadmap.md` | ADR 0031 (frozen-tier skeleton), ROADMAP updated through P24 (BL-063, BL-062) | Stage-4 runtime deferred to P23 | — |
| P24 | `docs/tasks/P24-COMPLETION.md` | ADR 0032 (cross-modal authorization): `AdraVectorAccessFilter` / `AdraEdgeAccessFilter` wired into `AoudaEngine`; `IQueryPermissionContext` plumbed through traversal and ANN operators | — | — |

---

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Edge table catalog kind (`TableKind.EdgeTable`) | Yes | — | — | `src/Aouda.Engine.Core/Schema/VectorConfig.cs`; P20-COMPLETION §2 #1 | — |
| Edge WAL frames (insert/delete) | Yes | — | — | `src/Aouda.Engine.Wal/WalPayloads.cs`; P20-COMPLETION §4.1 | — |
| Edge HRA buffer (`EdgeHraBuffer`) | Yes | — | — | `src/Aouda.Engine.Storage/Hra/EdgeHraBuffer.cs` | — |
| Sealed CSR edge segments (`EdgeSegmentFlusher`) | Yes | — | — | `src/Aouda.Engine.Storage/Edge/EdgeSegmentFlusher.cs` | — |
| CSC mirror segments (`CscMirrorWriter`) | Yes | — | — | `src/Aouda.Engine.Storage/Edge/CscMirrorWriter.cs` | Enabled by `EdgeTableConfig.StoreCsc = true` |
| Edge delta merge (`_delta/`) | Yes | — | — | `src/Aouda.Engine.Storage/Compaction/DeltaMerger.cs`; P20-COMPLETION §2 #4 | — |
| Edge partition routing by source key | Yes | — | — | `src/Aouda.Engine.Api/AoudaEngine.cs` `InsertEdgesAsync`; P20-COMPLETION §4.1 | — |
| Vector column type (`DataType.Vector`) | Yes | — | — | `src/Aouda.Engine.Core/Schema/Types.cs`; P20-COMPLETION §2 #1 | — |
| Vector WAL frames (insert/delete) | Yes | — | — | `src/Aouda.Engine.Wal/WalPayloads.cs`; P20-COMPLETION §4.1 | — |
| Vector HRA buffer (`VectorHraBuffer`) | Yes | — | — | `src/Aouda.Engine.Storage/Hra/VectorHraBuffer.cs` | — |
| IVF centroid persistence (`IvfCentroidStore`) | Yes | — | — | `src/Aouda.Engine.Storage/Vector/IvfCentroidStore.cs`; P20-COMPLETION §2 #5 | — |
| Sealed vector segments per IVF cell (`VectorSegmentFlusher`) | Yes | — | — | `src/Aouda.Engine.Storage/Vector/VectorSegmentFlusher.cs` | — |
| RaBitQ quantization companion (`*.rabitq`) | Yes | — | — | `src/Aouda.Engine.Storage/Vector/RaBitQEncoder.cs`; P20-COMPLETION §5.6 | — |
| PQ quantization companion (`*.pq`) | Yes | — | — | `src/Aouda.Engine.Storage/Vector/PqEncoder.cs`; P20-COMPLETION §5.6 | — |
| Vector delta merge (cell-aware) | Yes | — | — | `src/Aouda.Engine.Storage/Compaction/DeltaMerger.cs`; P20-COMPLETION §2 #7 | — |
| MdVector column storage (`col_{colId}_mdvec.bin`) | Yes | — | — | `src/Aouda.Engine.Storage/Vector/MdVectorColumnWriter.cs`; P20-COMPLETION §2 #7 | — |
| MdVector FDE auto-derivation | — | — | Yes | ADR 0027 (columnar) §Stage-2 | Stage 2 — `MdVectorColumnConfig.Fde` field stored only |
| `TraverseAsync` operator (BFS k-hop) | Yes | — | — | `src/Aouda.Engine.Query/Operators/TraverseOperator.cs`; P20-COMPLETION §2 #8 | — |
| `KHopNeighborhoodAsync` operator (BFS with hop distance) | Yes | — | — | `src/Aouda.Engine.Query/Operators/KHopNeighborhoodOperator.cs` | — |
| `ShortestPathAsync` operator (bidirectional BFS w/ CSC) | Yes | — | — | `src/Aouda.Engine.Query/Operators/ShortestPathOperator.cs` | Bidirectional only when `StoreCsc: true` |
| `NearestNeighborsAsync` (IVF-pruned brute-force) | Yes | — | — | `src/Aouda.Engine.Query/Operators/NearestNeighborsOperator.cs` | Stage 1: brute-force in IVF cells |
| Workload-adaptive HNSW sub-index | — | — | Yes | ADR 0027 (columnar) §Stage-3 | Stage 3 |
| SQL/PGQ graph query language | — | — | Yes | ADR 0027 (columnar) §Stage-2 | Stage 2 |
| `Retrieve` hybrid pipeline | — | — | Yes | ADR 0027 (columnar) §Stage-2 | Stage 2 |
| MaxSim rerank operator (MdVector) | — | — | Yes | ADR 0027 (columnar) §Stage-2 | Stage 2 |
| Filtered ANN layer 1 (partition pruning) | Yes | — | — | `src/Aouda.Engine.Api/AoudaEngine.cs` `NearestNeighborsAsync` `partitionKey` param; ADR 0027 (columnar) §Filtered-ANN | Free; uses ADR 0009 partition machinery |
| Filtered ANN layer 2 (pre-filter + brute-force) | — | — | Yes | ADR 0027 (columnar) §Stage-2 | Stage 2 |
| Filtered ANN layer 3 (ACORN-1 + HNSW) | — | — | Yes | ADR 0027 (columnar) §Stage-3 | Stage 3 |
| ADRA authorization for vectors/edges (`IQueryPermissionContext`) | Yes | — | — | `src/Aouda.Engine.Api/AoudaEngine.cs` (`ResolveEdgeAccess`, `ResolveVectorAccess`); ADR 0032 | Wired in P24; `permissions = null` for no-auth path |
| Stage-4 manifest reservation fields | Yes | — | — | `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs` lines 71–83; ADR 0031 | Schema only; no Stage-4 runtime |
| Embedding model versioning per segment | Yes | — | — | `SegmentManifest.EmbeddingModelVersion`; `InsertVectorsAsync` `embeddingModelVersion` param | Enables multi-model coexistence and future Drift-Adapter |
| Matryoshka dims metadata | Yes | — | — | `VectorColumnConfig.MatryoshkaDims`; `src/Aouda.Engine.Core/Schema/VectorConfig.cs` | Stored in catalog; tiered retrieval not yet implemented |
| Embedded-mode parity (all Stage-1 primitives) | Yes | — | — | ADR 0022; `Aouda.Embedded` + `Aouda.Engine.Api` shared binary | No engine-binary divergence |

---

## 2.7 Core concepts and mental model

### 2.7.1 Three first-class storage primitives

Aouda extends its columnar storage model with two new primitives alongside the existing tabular table:

**Tabular table** (`TableKind.Tabular`) — unchanged. Column-per-file, HRA, hot/cold, partitioning, WAL, MQ.

**Edge table** (`TableKind.EdgeTable`) — a specialization of a tabular table where two columns are declared as `(src, dst)` endpoints. The engine:
- Enforces cluster ordering by `(src, dst)` at seal time, producing CSR-shaped segment pages.
- Optionally maintains a CSC mirror (sorted by `(dst, src)`) for backward traversal.
- Routes insert batches by source-node partition key (edges from the same source live in the same partition).
- Builds and exposes adjacency-aware traversal operators over sealed CSR pages.
- Late-arriving edges flow to `_delta/` segments (ADR 0014 pattern) and are merged in the background.

Vector columns (`DataType.Vector` / `DataType.MdVector`) are **column types**, not separate tables. They may appear on any tabular table:
- `DataType.Vector` — fixed-dimension dense float vectors. Each insert batch is WAL-framed, buffered in a per-column `VectorHraBuffer`, and flushed per IVF cell. Cold sealing optionally writes RaBitQ or PQ companion files.
- `DataType.MdVector` — variable-length multi-vector storage (ColBERT / ColPali style). Written to `col_{colId}_mdvec.bin`. The companion FDE column for MaxSim retrieval is deferred to Stage 2.

**Key invariant:** Edge and vector storage reuse all existing engine primitives (column-per-file, HRA freeze-and-swap, WAL replay, hot/cold tiering, partition pruning, zone maps). They are not parallel subsystems.

### 2.7.2 IVF cell assignment and sealed vector segments

IVF (Inverted File Index) cells are realized as Aouda partitions over vector space. At flush time, `IvfCentroidStore` assigns each vector in the HRA buffer to its nearest centroid (by the column's declared distance metric). `VectorSegmentFlusher` writes one sealed segment per IVF cell, then writes optional companion quantization files (`*.rabitq`, `*.pq`) alongside the raw fp32 pages.

The `IvfCellId` and `QuantizationMethod` fields in `SegmentManifest` identify which cell and what quantization a segment belongs to.

**Key invariant:** `NearestNeighborsAsync` filters segments by IVF cell (partition pruning, Filtered ANN layer 1) before brute-force distance computation. A `partitionKey` argument further narrows the scan to one user-visible partition.

### 2.7.3 HRA freeze-and-swap is the same for all three primitives

`EdgeHraBuffer` and `VectorHraBuffer` use the same freeze-and-swap mechanism as the tabular `HraTable` (ADR 0021): a live buffer is frozen (made immutable), a new empty buffer is swapped in, and the frozen snapshot is asynchronously flushed by `HraManager`. Writers never block on flush.

### 2.7.4 Embedding model version per segment

`InsertVectorsAsync` accepts an optional `embeddingModelVersion` string. This is stored in the WAL frame and propagated to `VectorHraBuffer`; at flush time `VectorSegmentFlusher` writes it to `SegmentManifest.EmbeddingModelVersion` and to `SegmentEntry.EmbeddingModelVersion` in the catalog. Multiple model versions can coexist on the same table — the planner can pick the right segment set per query. This is the Stage-1 groundwork for the Drift-Adapter model-upgrade path in Stage 2.

### 2.7.5 Stage-4 reservation fields are inert in Stage 1

`SegmentManifest` carries four fields reserved for the frozen object-storage tier (ADR 0031):
- `FrozenTierLayoutVersion = 0` — "not a frozen segment"; Stage 4 will write `1` (or higher) at cold→frozen migration.
- `HierarchicalSpfreshCentroids = null` — coarse centroid blob for hierarchical SPFresh beam search.
- `S3CompatibleHeader = null` — self-describing frozen header blob for catalog-independent reads.
- `SelfDescribingMagic = 0` — magic marker for frozen segment identification (exact constant finalized in P23).

These fields are serialized by `ManifestSerializer.cs` for every manifest but have no runtime effect until Stage 4. Contributors **must not** repurpose them without a superseding ADR.

### 2.7.6 ADRA authorization composes with graph/vector queries

Starting P24 (ADR 0032), edge traversal and ANN search accept an `IQueryPermissionContext? permissions` parameter. When non-null:
- `ResolveEdgeAccess` calls `AdraEdgeAccessFilter` to resolve the set of allowed partition keys.
- `ResolveVectorAccess` calls `AdraVectorAccessFilter` similarly.
- An empty allowed-partition set returns an empty result immediately (deny-by-default).
- `null` permissions bypasses auth (embedded mode or service-key context).

**Key invariant:** Filtered ANN layer 1 (partition pruning) and ADRA PLS partition grants are the same mechanism — ADRA grants narrow which partitions the ANN scan considers, at no extra cost.

---

## 2.8 How Aouda implements it

### Architecture overview

```
InsertEdgesAsync / InsertVectorsAsync
    │
    ├─ WAL frame append (EdgeInsert / VectorInsert)
    │
    ├─ EdgeHraBuffer / VectorHraBuffer  (hot write area)
    │       │
    │       └─ HraManager: freeze-and-swap trigger
    │               │
    │               ├─ EdgeSegmentFlusher → CSR segments + csc_* files
    │               └─ VectorSegmentFlusher → fp32 pages + *.rabitq/*.pq companions
    │                       └─ IvfCentroidStore: cell assignment at flush
    │
    └─ Cold segment registry & manifest updated → operator visibility

TraverseAsync / KHopNeighborhoodAsync / ShortestPathAsync
    └─ TraverseOperator / KHopNeighborhoodOperator / ShortestPathOperator
           └─ Scans CSR sealed segments; optional CSC for bidirectional BFS
           └─ Partition-key filter (ADRA grants via IEdgeAccessFilter)

NearestNeighborsAsync
    └─ NearestNeighborsOperator
           └─ IVF cell pruning → brute-force distance over fp32 / decoded RaBitQ pages
           └─ Partition-key filter (ADRA grants via IVectorAccessFilter)
           └─ Multi-partition fan-out merge (ADR 0032 M2 fix)
```

### 2.8.1 Critical path walk-throughs

**Walk-through 1: Edge insert → CSR sealed segment → traversal**

1. Caller invokes `AoudaEngine.InsertEdgesAsync("relations", srcs, dsts, ...)`.
2. Engine resolves table entry; validates `Kind == EdgeTable`.
3. `AwaitBulkLoadLockReleaseAsync` blocks if a bulk-load job holds the table lock (Stage 1 defensive; bulk-load on edge tables gated by BL-071).
4. Edges grouped by source-node partition key (if partitioned); each group dispatched to its `EdgeHraBuffer`.
5. WAL frame `WalTag.EdgeInsert` written before buffer mutation.
6. `EdgeHraBuffer.InsertEdges` appends `(src, dst)` pairs.
7. `HraManager` checks row/byte thresholds; when threshold met → freeze-and-swap.
8. `EdgeSegmentFlusher` sorts by `(src, dst)`, writes CSR column pages; if `StoreCsc = true`, `CscMirrorWriter` writes CSC companion (`csc_*`).
9. `SegmentManifest` written (`StoreCsc`, `EdgeLabel` fields populated).
10. Cold segment registry updated; segment becomes visible to `TraverseOperator`.
11. `TraverseAsync` reads CSR pages to enumerate neighbors; uses bidirectional BFS with CSC when available.

Key observability: `Perf.CompactionFloorSuppressed` (if flush suppressed by floor); WAL replay reconstructs `EdgeHraBuffer` on crash recovery.

Relevant tests: `tests/Aouda.Engine.Storage.Tests/Edge/SealedEdgeSegmentTests.cs`, `tests/Aouda.Engine.Storage.Tests/Hra/EdgeHraBufferTests.cs`, `tests/Aouda.Engine.Query.Tests/Operators/TraverseOperatorTests.cs`, `tests/Aouda.Engine.Api.Tests/InsertEdgesApiTests.cs`.

**Walk-through 2: Vector insert → IVF seal → ANN search**

1. Caller invokes `AoudaEngine.InsertVectorsAsync("documents", "embedding", rowKeys, vectorData, embeddingModelVersion: "text-embedding-3-large@v1")`.
2. Engine resolves table; validates column `DataType == Vector`; confirms `vectorData.Length == rowKeys.Length * dimensions`.
3. WAL frame `WalTag.VectorInsert` written (row keys, float data, model version, partition key).
4. `VectorHraBuffer.InsertVectors` buffers rows.
5. `HraManager` threshold trigger → freeze-and-swap.
6. `IvfCentroidStore` assigns each vector to nearest centroid by declared distance metric.
7. `VectorSegmentFlusher` groups by IVF cell; for each cell: writes raw fp32 column pages + row-key companion; if `Quantization == RaBitQ`, writes `*.rabitq`; if `PQ`, writes `*.pq`.
8. `SegmentManifest` written with `IvfCellId`, `QuantizationMethod`, `EmbeddingModelVersion`; Stage-4 reservation fields written as zero/null.
9. `NearestNeighborsAsync` prunes to cells whose centroid is within a beam width of the query; for each candidate cell, decodes pages and computes distances; merges top-k.

Key observability: `SegmentManifest.IvfCellId`, `SegmentManifest.QuantizationMethod` visible in manifest diagnostics.

Relevant tests: `tests/Aouda.Engine.Storage.Tests/Vector/SealedVectorSegmentTests.cs`, `tests/Aouda.Engine.Storage.Tests/Vector/VectorHraBufferTests.cs`, `tests/Aouda.Engine.Storage.Tests/Vector/IvfCentroidStoreTests.cs`, `tests/Aouda.Engine.Query.Tests/Operators/NearestNeighborsOperatorTests.cs`.

**Walk-through 3: WAL replay after crash**

1. On `AoudaEngine.OpenAsync`, WAL log is replayed frame by frame.
2. `WalTag.EdgeInsert` frames re-feed `EdgeHraBuffer` (restores in-flight hot edge data).
3. `WalTag.VectorInsert` frames re-feed `VectorHraBuffer` (restores in-flight hot vector data).
4. Sealed segments already on disk are registered via cold segment registry (not replayed).
5. After replay, HRA and cold registry both reflect the last durable state.

Relevant tests: `tests/Aouda.Engine.Wal.Tests/` (WAL replay); `tests/Aouda.Engine.Storage.Tests/Hra/EdgeHraBufferTests.cs` (restart scenarios).

**Walk-through 4: `ShortestPathAsync` bidirectional BFS**

1. Engine validates `Kind == EdgeTable`.
2. `ShortestPathOperator.ShortestPathAsync` is invoked with `tableDef`.
3. If `tableDef.EdgeConfig.StoreCsc == true`: bidirectional BFS — forward BFS from node `a` over CSR segments + backward BFS from node `b` over CSC segments. Both fronts advance alternately until they meet.
4. If `StoreCsc == false`: unidirectional BFS over CSR only (potentially slower for long paths).
5. Returns node sequence `[a, ..., b]`; empty if no path exists.

Relevant test: `tests/Aouda.Engine.Query.Tests/Operators/ShortestPathOperatorTests.cs`.

---

## 2.9 Why Aouda is different

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Store graphs, vectors, and rows together | Requires Postgres + Neo4j + Pinecone (3 systems) | All three in one engine; same WAL, same tiering, same auth | Zero ETL between modalities; one on-call rotation |
| Unified authorization across modalities | Each system enforces its own model; joins across ACLs require bespoke glue | ADR 0032 ADRA authorization uniformly governs edge traversal and ANN search via `IQueryPermissionContext` | Cell-level RLS composes with graph traversal and ANN at query time |
| IVF cells as columnar partitions | Most vector DBs maintain a parallel index subsystem | Aouda reuses ADR 0009 partition machinery for IVF cell routing | No separate index management; tiering policies apply to vector cells the same as to row partitions |
| Quantization in cold tier, raw fp32 hot | Typical: quantize globally or not at all | Aouda stores raw fp32 in hot segments; cold sealing applies RaBitQ/PQ automatically | Precision for re-ranking hot results; cost efficiency for cold recall |
| Embedding model version per segment | Most systems assume one model per table | `EmbeddingModelVersion` recorded per segment; multiple versions coexist | Zero-downtime model upgrades (old + new segments query simultaneously); Stage-2 Drift-Adapter uses this metadata |
| MdVector (multi-vector) native storage | ColBERT-style requires client-side aggregation or separate table | `DataType.MdVector` column type stores variable-length multi-vector rows natively; FDE companion planned for Stage 2 | Visual document retrieval (ColPali) without schema workarounds |
| Stage-4 frozen tier commitment | Pure vector DBs have S3-native tiers; graph DBs do not | ADR 0031 names the frozen tier as a hard commitment; catalog fields reserved in Stage 1 so Stage 4 starts without rework | Ultra-scale vector corpora (billion rows) at cost parity with Turbopuffer; same engine binary |
| Graph/vector in embedded mode | Embedded graph and vector engines are separate products | All Stage-1 primitives (edge tables, `DataType.Vector`, `BulkLoadAsync`) work identically in `Aouda.Embedded` and the server (ADR 0022) | Agentic loops and local AI apps use the same storage API as the server deployment |

---

## 2.10 Configuration and settings reference

### VectorColumnConfig fields (set at table/column creation time)

| Field | Type | Required | Allowed values | Notes |
|---|---|---|---|---|
| `Dimensions` | `int` | Yes | `>0` | Fixed vector dimension; must match `queryEmbedding.Length` at search time |
| `Distance` | `VectorDistance` | Yes | `Cosine`, `L2`, `DotProduct` | Distance metric used for IVF centroid assignment and ANN distance computation |
| `Quantization` | `VectorQuantization` | Yes | `None`, `RaBitQ`, `PQ`, `SQ` | Cold-tier quantization. `None` keeps raw fp32 in cold segments. `SQ` defined in enum but encoding behavior not yet documented separately from source. |
| `IvfCells` | `int` | Yes | `>0` | Number of IVF cells. Use `1` for small corpora (<10K vectors). A common heuristic for larger corpora is `sqrt(N)`. |
| `EmbeddingModel` | `string?` | No | Any string | Logical model name (e.g. `"openai/text-embedding-3-large"`); stored in catalog, not enforced by engine |
| `EmbeddingModelVersion` | `string?` | No | Any string | Version suffix (e.g. `"v1"`); stored in catalog per-column; prefer passing per-insert via `InsertVectorsAsync` for segment-level tracking |
| `MatryoshkaDims` | `int?` | No | Any positive int | Reserved for Matryoshka tiered retrieval (Stage 2); stored in catalog, no runtime effect in Stage 1 |

### MdVectorColumnConfig fields

| Field | Type | Required | Allowed values | Notes |
|---|---|---|---|---|
| `Dimensions` | `int` | Yes | `>0` | Dimension of each individual token vector |
| `MaxTokens` | `int` | Yes | `>0` | Maximum tokens per document row |
| `Distance` | `VectorDistance` | Yes | `Cosine`, `L2`, `DotProduct` | Distance metric for MaxSim rerank (Stage 2) |
| `Fde` | `bool` | No | `true` (default), `false` | Reserves FDE companion column slot for Stage 2; no runtime effect in Stage 1 |

### EdgeTableConfig fields

| Field | Type | Required | Allowed values | Notes |
|---|---|---|---|---|
| `SrcColumn` | `string` | Yes | Column name | Column name (not ID) of the source-node endpoint |
| `DstColumn` | `string` | Yes | Column name | Column name of the destination-node endpoint |
| `EdgeLabel` | `string?` | No | Any string | Stored in manifest; not used by traversal operators for filtering in Stage 1 |
| `StoreCsc` | `bool` | No | `true`/`false` (default `false`) | When `true`, `CscMirrorWriter` produces CSC companion segment files. Required for bidirectional `ShortestPathAsync`. Has storage cost (~same as CSR). |

### InsertVectorsAsync per-insert parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `embeddingModelVersion` | `string?` | `null` | Written to WAL frame and propagated to `SegmentManifest.EmbeddingModelVersion` at seal |
| `partitionKey` | `string?` | `null` | Routes insert to a specific partition's `VectorHraBuffer`; must match the table's declared partition key column function |

### NearestNeighborsAsync query parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `partitionKey` | `string?` | `null` | Filtered ANN layer 1: restricts scan to one partition. Pass `null` to scan all partitions. |
| `permissions` | `IQueryPermissionContext?` | `null` | ADRA authorization (ADR 0032). `null` = no auth restriction (embedded / service-key). |
| `k` | `int` | — (required) | Maximum results to return; engine returns ≤ k results ordered by ascending distance |

### Stage-4 manifest reservation fields (ADR 0031 Decision-6)

| Field | Location | Stage-1 value | Stage-4 semantic |
|---|---|---|---|
| `EmbeddingModelVersion` | `SegmentManifest` + `SegmentEntry` (catalog) | Written at seal by `VectorSegmentFlusher` and `BulkLoadAsync` | Used by Stage-2 Drift-Adapter for query-time model-version mapping |
| `FrozenTierLayoutVersion` | `SegmentManifest` | `0` | Layout version for frozen segment file format; Stage 4 writes `1`+; `0` = not a frozen segment |
| `HierarchicalSpfreshCentroids` | `SegmentManifest` | `null` | Coarse centroid blob for hierarchical SPFresh beam search |
| `S3CompatibleHeader` | `SegmentManifest` | `null` | Self-describing header for catalog-independent frozen segment reads |
| `SelfDescribingMagic` | `SegmentManifest` | `0` | Frozen segment magic marker (constant value finalized in P23) |

---

## 2.11 API and CLI coverage reference

### API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status |
|---|---|---|---|---|
| Create edge table | `AoudaEngine.CreateEdgeTableAsync` | Not documented (see §2.20) | Not directly exposed | Implemented |
| Insert edges | `AoudaEngine.InsertEdgesAsync` | Not documented | Not directly exposed | Implemented |
| Delete edge | `AoudaEngine.DeleteEdgeAsync` | Not documented | Not directly exposed | Implemented |
| BFS traversal | `AoudaEngine.TraverseAsync` | Not documented | Not directly exposed | Implemented |
| K-hop neighborhood | `AoudaEngine.KHopNeighborhoodAsync` | Not documented | Not directly exposed | Implemented |
| Shortest path | `AoudaEngine.ShortestPathAsync` | Not documented | Not directly exposed | Implemented |
| Insert vectors | `AoudaEngine.InsertVectorsAsync` | Not documented | Not directly exposed | Implemented |
| Delete vector | `AoudaEngine.DeleteVectorAsync` | Not documented | Not directly exposed | Implemented |
| ANN nearest neighbors | `AoudaEngine.NearestNeighborsAsync` | Not documented | Not directly exposed | Implemented |
| Bulk load (edge/vector via tabular bulk-load) | `AoudaEngine.BulkLoadAsync`, `AoudaClient.BulkLoadAsync` | `client.table(name).bulkLoad(...)` | `POST .../bulk-load:begin` etc. | Implemented — see §2.18 for edge/vector bulk-load status |

### Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| SQL/PGQ graph queries | No SQL graph query endpoint | Use method-level operators | ADR 0027 (columnar) Stage 2 | High |
| `Retrieve` hybrid pipeline | No `RetrieveAsync` operator | Chain operators manually | ADR 0027 (columnar) Stage 2 | High |
| MaxSim rerank (MdVector) | No rerank operator | FDE column not yet computed | ADR 0027 (columnar) Stage 2 | High |
| TypeScript graph/vector method APIs | No TS SDK surface for `TraverseAsync`, `NearestNeighborsAsync` etc. | Use engine API directly or HTTP raw endpoints once exposed | Not yet planned | Medium |
| HTTP graph/vector endpoints | Graph/vector operators not exposed via REST | Engine API only | Not yet planned | Medium |
| GraphAr import | No CLI or API import command | Manual edge `InsertEdgesAsync` | BL-064 | Low |

### .NET examples

**Create an edge table:**

```csharp
using Aouda.Engine.Core.Schema;
using Aouda.Engine.Api;

var tableId = await engine.CreateEdgeTableAsync(
    name: "follows",
    edgeConfig: new EdgeTableConfig(
        SrcColumn: "src_id",
        DstColumn: "dst_id",
        EdgeLabel: "follows",
        StoreCsc: true),            // enable bidirectional BFS
    columns: new[]
    {
        ("src_id", DataType.Int64, EncoderPreference.Auto, false, /*pk order*/1, /*partition*/null, /*cluster*/1, /*partFn*/null),
        ("dst_id", DataType.Int64, EncoderPreference.Auto, false, null, null, 2, null),
    });
```

**Insert edges:**

```csharp
// Insert edges: node 1 follows nodes 2 and 3; node 2 follows node 4
await engine.InsertEdgesAsync(
    tableName: "follows",
    srcs: new long[] { 1, 1, 2 },
    dsts: new long[] { 2, 3, 4 });
```

**Traverse 1-hop neighbors:**

```csharp
long[] oneHopNeighbors = await engine.TraverseAsync(
    tableName: "follows",
    startNodeId: 1,
    hops: 1);
// Returns [2, 3]
```

**K-hop neighborhood with hop distances:**

```csharp
var neighborhood = await engine.KHopNeighborhoodAsync(
    tableName: "follows",
    startNodeId: 1,
    k: 2);
// Returns [(NodeId: 2, Hops: 1), (NodeId: 3, Hops: 1), (NodeId: 4, Hops: 2)]
```

**Shortest path:**

```csharp
long[] path = await engine.ShortestPathAsync(
    tableName: "follows",
    a: 1,
    b: 4);
// Returns [1, 2, 4] when StoreCsc: true (bidirectional BFS)
// or unidirectional BFS result when StoreCsc: false
```

**Common mistake (edge table):** Calling `InsertEdgesAsync` on a tabular table throws `InvalidOperationException("Table '...' is not an edge table (Kind=Tabular).")`.

---

**Create a table with a vector column:**

```csharp
// Step 1: create a tabular table with a vector column
var tableId = await engine.CreateTableAsync(
    name: "documents",
    columns: new[]
    {
        new ColumnDef(new ColumnId(1), "chunk_id",  DataType.Int64,   new ColumnOptions()),
        new ColumnDef(new ColumnId(2), "text",      DataType.String,  new ColumnOptions()),
        new ColumnDef(new ColumnId(3), "embedding", DataType.Vector,  new ColumnOptions()),
    },
    policy: new TablePolicy(
        vectorColumns: new Dictionary<ColumnId, VectorColumnConfig>
        {
            [new ColumnId(3)] = new VectorColumnConfig(
                Dimensions: 1536,
                Distance: VectorDistance.Cosine,
                Quantization: VectorQuantization.RaBitQ,
                IvfCells: 32,
                EmbeddingModel: "openai/text-embedding-3-large",
                EmbeddingModelVersion: "v1")
        }));
```

**Insert vectors (row-major float array):**

```csharp
// rowKeys are the chunk_id values for the rows being vectorized
var rowKeys  = new long[]  { 1001, 1002, 1003 };
var vectors  = new float[] { /* 1001: 1536 floats */, /* 1002: 1536 floats */, /* 1003: 1536 floats */ };

await engine.InsertVectorsAsync(
    tableName: "documents",
    columnName: "embedding",
    rowKeys: rowKeys,
    vectorData: vectors,
    embeddingModelVersion: "v1");
```

**Nearest-neighbor search:**

```csharp
float[] queryEmbedding = /* 1536-float query vector */;

IReadOnlyList<(long RowKey, float Distance)> top10 = await engine.NearestNeighborsAsync(
    tableName: "documents",
    vectorColumnName: "embedding",
    queryEmbedding: queryEmbedding,
    k: 10,
    partitionKey: null);          // pass a partition key to restrict to one tenant

foreach (var (rowKey, dist) in top10)
    Console.WriteLine($"RowKey={rowKey}  Distance={dist:F4}");
```

**Common mistake (vector):** Passing `queryEmbedding.Length != VectorColumnConfig.Dimensions` throws `ArgumentException("Query embedding has N dimensions but column expects M.")`. Always confirm the embedding model output dimension matches the column config.

---

### TypeScript examples

TypeScript graph/vector method APIs (Traverse, NearestNeighbors, etc.) are not yet exposed in `@aouda/client`. Evidence for TS bulk-load surfaces (`client.table(name).bulkLoad(...)`) is documented in `P20-COMPLETION.md §5.2` via cross-repo task reports; see §2.20 for the source-evidence status of TS surfaces.

---

## 2.12 Scenario playbooks

### Scenario 1: Build and traverse a social follow graph

**When to use:** You have a user-follow relationship and want to recommend second-degree connections.

**Steps:**

```csharp
// 1. Create edge table with CSC for bidirectional lookups
await engine.CreateEdgeTableAsync(
    name: "follows",
    edgeConfig: new EdgeTableConfig("src", "dst", StoreCsc: true),
    columns: new[]
    {
        ("src", DataType.Int64, EncoderPreference.Auto, false, 1, null, 1, null),
        ("dst", DataType.Int64, EncoderPreference.Auto, false, null, null, 2, null),
    });

// 2. Bulk-load initial graph (or use InsertEdgesAsync for online writes)
// Bulk-load path: see docs/dev/Functionality-Bulk-Load.md

// 3. Query 2-hop neighborhood for user 42
var hood = await engine.KHopNeighborhoodAsync("follows", startNodeId: 42, k: 2);
var secondDegree = hood.Where(n => n.Hops == 2).Select(n => n.NodeId);

// 4. Find shortest path between users 42 and 99
long[] path = await engine.ShortestPathAsync("follows", 42, 99);
```

**Expected result checks:**
- `hood` is ordered by `(Hops ascending, NodeId ascending)`.
- `path` is `[42, ..., 99]` (both endpoints included) or empty if unreachable.
- Traversal only considers edges in sealed CSR segments; edges still in `EdgeHraBuffer` become visible after flush.

---

### Scenario 2: Semantic document search with embeddings

**When to use:** Store document chunks with embeddings and answer semantic queries via ANN.

**Steps:**

```csharp
// 1. Create table with Vector column
await engine.CreateTableAsync("docs", columns: ..., policy: new TablePolicy(
    vectorColumns: new Dictionary<ColumnId, VectorColumnConfig>
    {
        [embColId] = new VectorColumnConfig(1536, VectorDistance.Cosine, VectorQuantization.RaBitQ, IvfCells: 64,
            EmbeddingModelVersion: "text-embedding-3-large@v1")
    }));

// 2. Insert text chunks and embeddings (supply external embeddings)
long[] rowKeys = /* chunk IDs */;
float[] allEmbeddings = /* N * 1536 floats, row-major */;
await engine.InsertVectorsAsync("docs", "embedding", rowKeys, allEmbeddings,
    embeddingModelVersion: "text-embedding-3-large@v1");

// 3. Query (at search time)
float[] queryVec = embedder.Embed(userQuery);   // caller provides embedding
var results = await engine.NearestNeighborsAsync("docs", "embedding", queryVec, k: 10);
```

**Expected result checks:**
- Results ordered by ascending cosine distance (0 = identical, 2 = opposite).
- Each result contains a `RowKey` corresponding to an inserted `chunk_id`; join with the tabular row to retrieve text.
- If `partitionKey` is supplied, only vectors in that partition are scanned (Filtered ANN layer 1).

---

### Scenario 3: Multi-model migration with embedding version coexistence

**When to use:** You need to upgrade the embedding model for a large corpus without downtime.

**Steps:**

```csharp
// 1. Existing corpus was inserted with model v1
await engine.InsertVectorsAsync("docs", "embedding", oldRowKeys, oldEmbeddings,
    embeddingModelVersion: "text-embedding-3-large@v1");

// 2. New embeddings arrive with model v2 (e.g., higher-dimension model updated columns on same rowkeys)
await engine.InsertVectorsAsync("docs", "embedding", newRowKeys, newEmbeddings,
    embeddingModelVersion: "text-embedding-3-large@v2");

// Both model versions coexist as separate segments (SegmentManifest.EmbeddingModelVersion tracks each).
// Queries against NearestNeighborsAsync see all sealed segments regardless of model version.
// Note: searching across mixed model versions without a Drift-Adapter (Stage 2) may return
// lower recall for rows encoded by the old model if distance spaces differ significantly.
```

**Expected result checks:**
- `SegmentManifest.EmbeddingModelVersion` reflects the version supplied at insert time.
- `NearestNeighborsAsync` results include rows from both model-version segments.
- Full migration: use `BulkLoadAsync` to re-embed and replace old segments.

---

## 2.13 Operations and observability

### What to monitor first

| Question | Practical answer |
|---|---|
| Are edges becoming visible to traversal? | Check cold segment registry for the edge table after flush threshold is crossed (row count ≥ `MinFlushRows`); WAL replay re-populates `EdgeHraBuffer` on restart |
| Are vector segments being sealed per IVF cell? | Inspect `SegmentManifest.IvfCellId` fields in manifests; one manifest per cell per flush cycle |
| Is ANN returning fewer results than expected? | If IVF cells are not yet sealed (data still in HRA), `NearestNeighborsAsync` returns empty — Stage 1 searches sealed segments only |
| Is the cold segment scan slow for ANN? | Check `IvfCells` setting: too few cells means each cell is large; too many cells means centroid training is expensive and recall drops |
| Are flush threshold events happening? | `Perf.CompactionFloorSuppressed` — incremented when a triggered flush was held back by the compaction floor (see `Functionality-HotCold-And-Memory.md`) |
| What model version is in a segment? | Read `SegmentManifest.EmbeddingModelVersion`; use per-segment manifest diagnostics |

### Key events and signals

| Event / metric | Location | When it fires |
|---|---|---|
| Edge flush triggered | `HraManager.RegisterEdge` → `CompactionWorker` threshold | Edge HRA hits `MaxBufferedRowsPerTable` or `MaxBufferedBytesPerTable` |
| Vector cell seal | `VectorSegmentFlusher` | At each HRA freeze-and-swap per column |
| Compaction floor suppressed | `Perf.CompactionFloorSuppressed` | HRA triggered but below `MinFlushRows` / `MinFlushBytes` |
| WAL replay edge/vector frames | WAL replay log | On `AoudaEngine.OpenAsync` after crash |
| ADRA deny-early | `AoudaEngine` (empty result returned) | `allowedPartitions.Count == 0` from `IEdgeAccessFilter` / `IVectorAccessFilter` |

### Recovery expectations

- **Crash during edge/vector insert:** WAL replay reconstructs `EdgeHraBuffer` / `VectorHraBuffer` up to the last durable WAL frame. Unflushed rows in HRA that were not WAL-framed are lost.
- **Crash during bulk-load:** In-flight bulk-load segments are discarded; caller restarts the load from its upstream source. `BulkLoadResumeWatchdog` and `rowsDurablyCommitted` cursor support safe resume. See `docs/dev/Functionality-Bulk-Load.md`.
- **Cold segment remains after crash:** Sealed segments on disk are registered from the manifest at open time; not replayed from WAL.

### Tuning sequence

1. **IVF cell count:** Start with `IvfCells = 1` for prototyping. Scale to `sqrt(corpus_size)` for recall/latency balance. Too few cells → slow ANN (large brute-force set). Too many cells → recall loss (query matches only 1–2 cells; probes too narrow).
2. **Quantization:** Use `RaBitQ` for cold storage (good recall/cost). Use `None` for hot segments where re-ranking precision matters. `PQ` available for higher compression at lower recall.
3. **CSC mirror cost:** `StoreCsc: true` doubles sealed edge segment storage. Only enable if `ShortestPathAsync` bidirectional speed or backward traversal is needed.
4. **Partition key on vectors:** For multi-tenant deployments, partition vector-bearing tables by `tenant_id`; pass the tenant's partition key to `NearestNeighborsAsync` to scope scans automatically (Filtered ANN layer 1).

---

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `TraverseAsync` returns empty even though edges were inserted | Edges still in HRA; sealed segments not yet written | Wait for flush threshold to be crossed (rows/bytes), or call `DisposeAsync`/restart to trigger shutdown drain |
| `NearestNeighborsAsync` returns empty | No sealed vector segments; vectors still in HRA | Same as above — flush must occur before ANN search sees data |
| `NearestNeighborsAsync` returns fewer than `k` results | Fewer than `k` rows across all scanned IVF cells | Normal when corpus is smaller than `k`; also happens if partition pruning narrows the scan aggressively |
| `ArgumentException: Query embedding has N dimensions but column expects M` | Caller passed wrong-dimension embedding | Match `queryEmbedding.Length` to `VectorColumnConfig.Dimensions` |
| `InvalidOperationException: Table '...' is not an edge table` | Called `InsertEdgesAsync` on a tabular table | Confirm table was created with `TableKind.EdgeTable` (use `CreateEdgeTableAsync`) |
| `InvalidOperationException: Column '...' has DataType=X. InsertVectorsAsync requires DataType.Vector` | Wrong column name or wrong table | Verify the column was created with `DataType.Vector` |
| `ShortestPathAsync` is slow or returns a long path | `StoreCsc: false`; using unidirectional BFS | Re-create the edge table with `StoreCsc: true` for bidirectional BFS (requires data reload) |
| ANN recall is low | Too few IVF cells probed relative to corpus distribution | Increase `IvfCells` (requires recreating column config); or verify `partitionKey` is not too restrictive |
| Edge traversal returns unexpected nodes | Cross-partition traversal not supported in Stage 1; edges from other partitions not reachable from a cross-partition query | Ensure the start node's partition is accessible and edges are routed to the same partition as their source |
| `ADRA deny: empty partition grants` | `permissions` non-null with no grants for this table | Verify ADRA PLS grants are configured for the calling user; or pass `permissions = null` for service-key context |

---

## 2.15 Verification ledger

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Edge write/flush/traverse path (all tests) | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~Edge" --no-build --verbosity minimal` | Pass | 2026-05-19 | Covers `EdgeHraBufferTests`, `SealedEdgeSegmentTests`, `EdgeDeltaMergeTests` |
| Vector write/flush/ANN path (all tests) | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~Vector" --no-build --verbosity minimal` | Pass | 2026-05-19 | Covers `VectorHraBufferTests`, `SealedVectorSegmentTests`, `IvfCentroidStoreTests`, `VectorDeltaMergeTests`, `MdVectorStorageTests`, `RaBitQEncoderTests` |
| Query operator tests | `dotnet test tests/Aouda.Engine.Query.Tests --filter "FullyQualifiedName~Operators" --no-build --verbosity minimal` | Pass | 2026-05-19 | Covers `TraverseOperatorTests`, `KHopNeighborhoodOperatorTests`, `ShortestPathOperatorTests`, `NearestNeighborsOperatorTests` |
| Engine API integration (edge insert) | `dotnet test tests/Aouda.Engine.Api.Tests --filter "InsertEdgesApiTests" --no-build --verbosity minimal` | Pass | 2026-05-19 | — |
| Stage-4 manifest fields serialized correctly | Manual inspection of `SegmentManifest` in `ManifestSerializer.cs` | Fields present, round-trip to zero/null defaults | 2026-05-19 | No dedicated test for reservation fields; behavior matches ADR 0031 Decision-6 |

---

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| `EdgeHraBuffer` insert/delete/replay | `tests/Aouda.Engine.Storage.Tests/Hra/EdgeHraBufferTests.cs` | Pass | Strong | — |
| Edge sealed CSR segments | `tests/Aouda.Engine.Storage.Tests/Edge/SealedEdgeSegmentTests.cs` | Pass | Strong | — |
| Edge delta merge | `tests/Aouda.Engine.Storage.Tests/Edge/EdgeDeltaMergeTests.cs` | Pass | Strong | — |
| `VectorHraBuffer` insert/delete | `tests/Aouda.Engine.Storage.Tests/Vector/VectorHraBufferTests.cs` | Pass | Strong | — |
| Sealed vector segments per IVF cell | `tests/Aouda.Engine.Storage.Tests/Vector/SealedVectorSegmentTests.cs` | Pass | Strong | — |
| IVF centroid store | `tests/Aouda.Engine.Storage.Tests/Vector/IvfCentroidStoreTests.cs` | Pass | Strong | — |
| RaBitQ encoder | `tests/Aouda.Engine.Storage.Tests/Vector/RaBitQEncoderTests.cs` | Pass | Strong | — |
| MdVector column storage format | `tests/Aouda.Engine.Storage.Tests/Vector/MdVectorStorageTests.cs` | Pass | Strong | Storage format only; no retrieval test |
| Vector delta merge (cell-aware) | `tests/Aouda.Engine.Storage.Tests/Vector/VectorDeltaMergeTests.cs` | Pass | Strong | — |
| k-means helper for IVF centroid training | `tests/Aouda.Engine.Storage.Tests/Vector/KMeansHelperTests.cs` | Pass | Medium | Unit-level; end-to-end centroid drift not tested |
| `TraverseAsync` BFS | `tests/Aouda.Engine.Query.Tests/Operators/TraverseOperatorTests.cs` | Pass | Strong | — |
| `KHopNeighborhoodAsync` BFS with hop distances | `tests/Aouda.Engine.Query.Tests/Operators/KHopNeighborhoodOperatorTests.cs` | Pass | Strong | — |
| `ShortestPathAsync` bidirectional BFS | `tests/Aouda.Engine.Query.Tests/Operators/ShortestPathOperatorTests.cs` | Pass | Strong | Both CSC and non-CSC paths covered |
| `NearestNeighborsAsync` IVF-pruned brute-force | `tests/Aouda.Engine.Query.Tests/Operators/NearestNeighborsOperatorTests.cs` | Pass | Strong | — |
| `InsertEdgesAsync` engine API (round-trip) | `tests/Aouda.Engine.Api.Tests/InsertEdgesApiTests.cs` | Pass | Medium | Insert + traverse; CSC path not directly tested at API level |
| ADRA authorization compose with graph/vector | Not yet in `tests/Aouda.Engine.Api.Tests/` for graph/vector specifically | Not run | Weak | P24 wired `AdraEdgeAccessFilter` / `AdraVectorAccessFilter`; integration test coverage thin |
| Stage-4 manifest reservation field round-trip | No dedicated test | Not run | Weak | Fields confirmed in `ManifestSerializer.cs` by code inspection; propose test below |

---

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| ADRA authorization deny for edge traversal | Ensures ADR 0032 early-deny works end-to-end with real permission contexts | `tests/Aouda.Engine.Api.Tests/EdgeAdraAuthTests.cs`: create edge table with `AuthorizationMode.AuthDbPls`; traverse as user with and without PLS grants; assert empty result on deny | High |
| ADRA authorization deny for ANN search | Same as above for vector path | `tests/Aouda.Engine.Api.Tests/VectorAdraAuthTests.cs`: ANN query with empty grant set returns empty | High |
| Stage-4 manifest field serialization round-trip | Ensures reserved fields survive `ManifestSerializer` write→read without data loss | `tests/Aouda.Engine.Storage.Tests/Manifest/SegmentManifestStage4ReservationTests.cs`: write manifest with non-default field values (once P23 populates them); verify round-trip | Medium |
| `NearestNeighborsAsync` multi-partition fan-out merge | ADR 0032 M2 fix: multi-partition ANN must correctly merge results | `tests/Aouda.Engine.Api.Tests/VectorMultiPartitionAnnTests.cs`: insert vectors in 2 partitions; ANN with multi-partition grants; verify merged top-k ordering | Medium |
| MdVector FDE companion column slot (Stage 2 readiness) | Ensure catalog correctly stores `Fde: true` and column slot is reserved | `tests/Aouda.Engine.Api.Tests/MdVectorFdeSlotTests.cs`: create table with `MdVectorColumnConfig`; confirm `Fde` value persists in catalog | Low |
| Bidirectional BFS path correctness with CSC | `ShortestPathAsync` correctness for asymmetric graphs (directed edges) | Add directed-graph test case in `ShortestPathOperatorTests.cs` where CSR-only path would differ from bidirectional BFS | Medium |

---

## 2.18 Known gaps and undone work

| ID | Status | User-visible impact | Detail |
|---|---|---|---|
| BL-064 | Open | No GraphAr import from Neo4j or Apache GraphAr format | Manual edge `InsertEdgesAsync` only; no batch import onboarding tool |
| BL-065 | Open | No Iceberg-style time travel for graph/vector bulk-loaded segments | Retry may duplicate segment rows; no multi-version query |
| BL-066 | Open | Bulk-load segments replicated from primary only (no peer-to-peer fan-out) | Primary replica egress bottleneck at very high replication fan-out |
| BL-067 | Open | Bulk-load session state is in-memory; restarting the server loses in-flight session metadata | Clients must restart interrupted bulk-load jobs from scratch after server restart |
| Stage 2 | Planned | No SQL/PGQ, no `Retrieve` hybrid pipeline, no MaxSim rerank, no FDE column derivation | Full production AI retrieval pipeline requires Stage 2 |
| Stage 3 | Planned | No workload-adaptive HNSW; ANN latency scales with IVF cell size at large corpora | At very large scale (100M+ vectors per cell), Stage-1 brute-force becomes too slow without HNSW |
| Stage 4 | Planned (P23) | No frozen object-storage tier; billion-vector corpora must reside on local disk | Ultra-scale vector lakes blocked on frozen tier |
| MdVector retrieval | Stage 2 | `DataType.MdVector` data is stored but not queryable for MaxSim retrieval | Callers who insert `MdVector` in Stage 1 should plan to re-run `BulkLoadAsync` after Stage 2 lands to populate FDE |
| TypeScript graph/vector method APIs | Missing | TS SDK consumers cannot traverse edges or run ANN natively | Evidence in P20-COMPLETION §5.2 is cross-repo only; no TS source confirmed in this workspace |
| HTTP REST graph/vector endpoints | Missing | Non-.NET HTTP consumers cannot use graph/vector operations without embedding the engine | No controller-level exposure for Traverse/KHop/ShortestPath/NearestNeighbors |
| Edge/vector bulk-load native support | Partial | `BulkLoadAsync` for tabular tables is shipped; edge-table and vector-column bulk-load paths gated by BL-071 | `InsertEdgesAsync` / `InsertVectorsAsync` check `AwaitBulkLoadLockReleaseAsync` defensively; actual edge/vector bulk-load path tracked separately |

---

## 2.19 References

### ADRs

- ADR 0027 (columnar) — `docs/decisions/0027-columnar-native-graph-and-vector.md` — primary design authority for all three primitives
- ADR 0031 — `docs/decisions/0031-stage4-frozen-tier.md` — frozen-tier reservation fields and Stage-4 architectural contract
- ADR 0001 — column-per-file storage (foundation)
- ADR 0007 — hot/cold tiering (how vector tiers work)
- ADR 0008 — indexing strategy (relation to IVF and adaptive bloom)
- ADR 0009 — partitioning (IVF cells as partitions; source-node routing for edges)
- ADR 0014 — time-series clustering (delta-merge model reused for edges/vectors)
- ADR 0021 — HRA freeze-and-swap (same mechanism for `EdgeHraBuffer` / `VectorHraBuffer`)
- ADR 0022 — licensing (embedded parity for graph/vector)
- ADR 0025 — ADRA (authorization substrate)
- ADR 0030 — bulk-load replication (covers `BulkLoadAsync` write path)
- ADR 0032 — cross-modal authorization (`AdraEdgeAccessFilter` / `AdraVectorAccessFilter`)

### Task docs

- `docs/tasks/P20-COMPLETION.md` — P20 forensic record
- `docs/tasks/P20/BL-Post20-S2-Stage4-ADR-And-Roadmap.md` — ADR 0031 + ROADMAP update
- `docs/tasks/BL-COMPLETION.md` — backlog item registry

### Code paths

| Symbol | File |
|---|---|
| `VectorColumnConfig`, `MdVectorColumnConfig`, `EdgeTableConfig`, `TableKind` | `src/Aouda.Engine.Core/Schema/VectorConfig.cs` |
| `DataType.Vector`, `DataType.MdVector` | `src/Aouda.Engine.Core/Schema/Types.cs` |
| `EdgeHraBuffer` | `src/Aouda.Engine.Storage/Hra/EdgeHraBuffer.cs` |
| `VectorHraBuffer` | `src/Aouda.Engine.Storage/Hra/VectorHraBuffer.cs` |
| `HraManager.RegisterEdge`, `HraManager.RegisterVector` | `src/Aouda.Engine.Storage/HraBg/HraManager.cs` |
| `EdgeSegmentFlusher` | `src/Aouda.Engine.Storage/Edge/EdgeSegmentFlusher.cs` |
| `CscMirrorWriter` | `src/Aouda.Engine.Storage/Edge/CscMirrorWriter.cs` |
| `VectorSegmentFlusher` | `src/Aouda.Engine.Storage/Vector/VectorSegmentFlusher.cs` |
| `IvfCentroidStore` | `src/Aouda.Engine.Storage/Vector/IvfCentroidStore.cs` |
| `KMeansHelper` | `src/Aouda.Engine.Storage/Vector/KMeansHelper.cs` |
| `RaBitQEncoder` | `src/Aouda.Engine.Storage/Vector/RaBitQEncoder.cs` |
| `PqEncoder` | `src/Aouda.Engine.Storage/Vector/PqEncoder.cs` |
| `MdVectorColumnWriter`, `MdVectorColumnReader` | `src/Aouda.Engine.Storage/Vector/MdVectorColumnWriter.cs`, `MdVectorColumnReader.cs` |
| `DeltaMerger` (edge/vector delta classification) | `src/Aouda.Engine.Storage/Compaction/DeltaMerger.cs` |
| `SegmentManifest` (Stage-4 reservation fields) | `src/Aouda.Engine.Storage/Manifest/SegmentManifest.cs` (lines 71–83) |
| `ManifestSerializer` | `src/Aouda.Engine.Storage/Manifest/ManifestSerializer.cs` |
| `TraverseOperator` | `src/Aouda.Engine.Query/Operators/TraverseOperator.cs` |
| `KHopNeighborhoodOperator` | `src/Aouda.Engine.Query/Operators/KHopNeighborhoodOperator.cs` |
| `ShortestPathOperator` | `src/Aouda.Engine.Query/Operators/ShortestPathOperator.cs` |
| `NearestNeighborsOperator` | `src/Aouda.Engine.Query/Operators/NearestNeighborsOperator.cs` |
| `AoudaEngine` (public methods: CreateEdgeTableAsync, InsertEdgesAsync, InsertVectorsAsync, Traverse*, Nearest*, Delete*) | `src/Aouda.Engine.Api/AoudaEngine.cs` |

### Test suites

- `tests/Aouda.Engine.Storage.Tests/Edge/` — edge flusher, delta merge
- `tests/Aouda.Engine.Storage.Tests/Vector/` — vector HRA, IVF, quantization, delta merge, MdVector
- `tests/Aouda.Engine.Storage.Tests/Hra/EdgeHraBufferTests.cs`
- `tests/Aouda.Engine.Query.Tests/Operators/` — all four query operators
- `tests/Aouda.Engine.Api.Tests/InsertEdgesApiTests.cs`

---

## 2.20 What is missing from this document?

The following evidence could not be fully verified from local source materials and should be resolved before marking this document authoritative for those areas:

1. **TypeScript SDK surface for graph/vector** — `P20-COMPLETION.md §5.2` states `client.table(name).bulkLoad(...)` etc. are shipped in `aouda-client-ts`, but the TypeScript client repo (`c:\Data\GitHub\aouda-client-ts`) was not inspected for this document. TypeScript graph/vector method APIs (Traverse, NearestNeighbors) were not confirmed and are listed as Missing in the API coverage matrix. A follow-up pass against `aouda-client-ts` is needed to confirm or add those surfaces.

2. **HTTP REST graph/vector endpoints** — No controller in `src/Aouda.Server/Controllers/` was found to expose `TraverseAsync`, `KHopNeighborhoodAsync`, `ShortestPathAsync`, or `NearestNeighborsAsync` over HTTP. This is consistent with the Stage-1 design (method-level API only), but the server-level route surface was not fully enumerated for this document. Confirmed as missing in §2.18.

3. **Edge/vector bulk-load via `BulkLoadAsync`** — `AoudaEngine.InsertEdgesAsync` and `InsertVectorsAsync` gate themselves via `AwaitBulkLoadLockReleaseAsync`, which is a defensive check for when bulk-load lands on those table kinds. BL-071 tracks enabling edge/vector tables for bulk-load. The exact status of BL-071 sub-tasks was not confirmed in source.

4. **Exact IVF cell count heuristics in production** — The document recommends `sqrt(N)` as a common starting point, derived from ADR 0027 (columnar) and general ANN literature. No code-level heuristic override (e.g. `IvfCellCountHeuristic`) was found in the storage or API layer. Callers must supply `IvfCells` explicitly.

5. **`SQ` quantization** — `VectorQuantization.SQ = 3` is defined in `Types.cs` but no `SqEncoder.cs` was found in `src/Aouda.Engine.Storage/Vector/`. The SQ path may be a reserved enum value. Not documented in P20-COMPLETION. This should be confirmed against source before claiming SQ as a usable option.
