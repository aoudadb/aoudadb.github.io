---
title: "Primary Key Indexing and Memory"
nav_order: 19
parent: "Guides"
---

# Aouda Functionality: Primary-Key Indexing and Memory

Document status: Complete
Primary owner: Engineering
Last updated: 2026-05-19

Coverage phases: PreP4, P17, P18
Primary task folders: `docs/tasks/PreP4-COMPLETION.md`, `docs/tasks/P17-COMPLETION.md`, `docs/tasks/P18-COMPLETION.md`
Primary ADRs: `docs/decisions/0028-pk-indexing-memory-model.md`, `docs/decisions/0008-indexing-strategy.md`, `docs/decisions/0021-hra-flush-freeze-and-swap.md`
Related functionality docs: `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-Storage-And-Persistence.md`, `docs/dev/Functionality-Write-Path-Durability.md`

---

## Start Here

If your question is "How does Aouda enforce PK uniqueness?", start with:
- 2.7 Core concepts and mental model
- 2.8.1 Critical path walk-throughs (insert-path enforcement)
- 2.11 API coverage matrix and `.NET` examples

If your question is "What gets stored on disk for PK lookup?", start with:
- 2.8 Architecture overview
- 2.10 Configuration and settings reference
- 2.19 References (code paths)

If your question is "What is implemented vs missing?", jump to:
- 2.4 Availability status
- 2.5 Phase coverage matrix
- 2.6 Capability coverage matrix

| If you need to know... | Go to section |
|---|---|
| Default PK behavior | 2.3 |
| Shipped vs planned vs reserved | 2.4 |
| Phase-by-phase delivery | 2.5 |
| Complete capability inventory | 2.6 |
| Runtime model and invariants | 2.7 |
| Implementation details and call paths | 2.8 |
| Why Aouda is different | 2.9 |
| Tuning knobs and bounds | 2.10 |
| Public API and gaps | 2.11 |
| Operational playbooks | 2.12 |
| Monitoring and diagnostics | 2.13 |
| Symptom-based troubleshooting | 2.14 |
| Verification and test coverage | 2.15, 2.16 |
| Known gaps and backlog pointers | 2.18 |

---

## 2.1 Why this functionality exists

Primary-key uniqueness at billion-row scale cannot rely on a dense, always-resident in-memory map. Aouda needs strict-by-default PK guarantees while still supporting hot/cold storage, freeze windows, and large cold tiers without unbounded RAM growth.

This functionality delivers:
- Cross-tier uniqueness enforcement (`HRA`, frozen prefix, hot sealed, cold sealed).
- A layered PK structure model (`L0` to `L4`) with explicit memory budgets.
- Persistent sealed-segment structures for fast startup and deterministic behavior (`pk_index.spr`, `pk_keymap.dat/.idx`).
- Operator diagnostics for policy, RAM footprint, structure presence, and latent duplicates.

Out of scope for this functionality:
- SQL index DDL and user-managed index tuning APIs.
- A separate distributed uniqueness coordinator.
- Automatic data cleanup for historical duplicates (operator workflow exists; auto-remediation does not).

---

## 2.2 Discovery and navigation map

| Role | Where to start |
|---|---|
| Application developer | 2.11 API coverage and policy examples |
| Operator | 2.10 configuration + 2.13 observability |
| Storage contributor | 2.8 architecture + 2.8.1 critical paths |
| Reliability reviewer | 2.5 phase matrix + 2.16 test matrix + 2.18 known gaps |

| Source area | Location |
|---|---|
| Completion evidence | `docs/tasks/P18-COMPLETION.md`, `docs/tasks/P17-COMPLETION.md`, `docs/tasks/PreP4-COMPLETION.md` |
| Design authority | `docs/decisions/0028-pk-indexing-memory-model.md` |
| Operator migration workflow | `docs/dev/PkUniqueness-Migration-Playbook.md` |
| Insert-path enforcement | `src/Aouda.Engine.Api/AoudaEngine.cs` |
| L2 cache / key encoding | `src/Aouda.Engine.Storage/Index/L2KeyCache.cs`, `src/Aouda.Engine.Storage/Index/KeyStruct.cs` |
| L1 sparse index | `src/Aouda.Engine.Storage/Index/SparsePkIndex.cs`, `SparsePkIndexFile.cs` |
| L3 keymap | `src/Aouda.Engine.Storage/Index/L3KeyMap.cs`, `L3KeyMapFile.cs` |
| Seal-time build pipeline | `src/Aouda.Engine.Storage/Hra/HraCompactor.cs` |
| Diagnostics shape | `src/Aouda.Engine.Storage/Index/PkStructuresDiagnostics.cs` |

---

## 2.3 Defaults and zero-config behavior

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `TableOptions.PkUniqueness` | `Strict` | Insert path checks `L2 -> L1 -> L0 -> (L3 or fallback decode)` across tiers; duplicates are enforced when strict gate is enabled. |
| `_strictEnforcementEnabled` gate | `true` | Duplicate detection throws immediately. When disabled (phase-1 migration mode), duplicates increment latent counter and write succeeds. |
| `MemoryBudgetOptions.MaxHotKeyCacheFraction` | `0.05` | L2 hot-key cache budget is 5% of `MaxTotalRamBytes`. |
| `MemoryBudgetOptions.MaxSparsePkIndexFraction` | `0.001` | L1 sparse index budget is 0.1% of `MaxTotalRamBytes`. |
| L1 write behavior | Always on for PK tables at seal | `pk_index.spr` is created for non-delta sealed segments with PK columns. |
| L3 write behavior | Strict tables only | `pk_keymap.dat/.idx` is created for strict PK tables (unless explicitly suppressed internally). |
| Preload behavior at `OpenAsync` | Enabled for PK tables | Key index rebuild and L1/L3 loading happen at open instead of first-write spike. |

---

## 2.4 Availability status

### Available now

- `PkUniquenessMode` with `Strict`, `Recent`, `BestEffort` (`src/Aouda.Engine.Core/Schema/Types.cs`).
- Typed key model (`KeyStruct`, `PkKeyEncoder`) with culture-invariant encoding.
- L2 partitioned key cache with frozen-prefix support and batch pin/unpin (`L2KeyCache`).
- L1 sparse index build/read, including Elias-Fano support and backward-compatible lazy build from zone maps (`SparsePkIndex*`).
- L3 on-disk keymap files + block-directory lookups (`L3KeyMap*`).
- Insert-path policy-aware uniqueness enforcement in `AoudaEngine.EnforcePrimaryKeyUniquenessAsync`.
- Open-path preload for PK structures (`AoudaEngine.PreloadPrimaryKeyIndexes`).
- Diagnostics API `GetPkStructuresDiagnosticsAsync`.
- Seal-time monotonic trigger evaluation and L4-aware decisions in `HraCompactor`.

### Planned / proposed

| Planned capability | Source |
|---|---|
| Further L3/L1 memory and lookup micro-optimizations | ADR 0028 consequence notes |
| Additional automation around migration gates and remediation | `docs/dev/PkUniqueness-Migration-Playbook.md` (operator-run today) |

### Reserved / not yet wired

| Reserved surface | Current state |
|---|---|
| User-facing PK index DDL or index knobs | Intentionally absent (ADR 0008 model). |
| Automatic duplicate-remediation engine workflow | Not implemented; operator playbook only. |

---

## 2.5 Phase coverage matrix

| Phase | Tasks / reports | Delivered capability | Undone / deferred | Backlog link |
|---|---|---|---|---|
| PreP4 | `docs/tasks/PreP4-COMPLETION.md` | `MemoryBudgetOptions` base surface including PK fractions | PK tier model not yet wired | N/A |
| P17 | `docs/tasks/P17-COMPLETION.md` | `PreloadPrimaryKeyIndexes` moved rebuild to open path | Disk-persisted PK structures not yet present | N/A |
| P18 | `docs/tasks/P18-COMPLETION.md` | Full layered PK model (L0-L4), policy modes, L1/L3 persistence, diagnostics, migration gates | No user-facing index DDL | `BL-061` resolved (see P18 completion) |

---

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Policy enum (`Strict/Recent/BestEffort`) | Yes | No | No | `Types.cs`, P18 §5.1 | Default is strict. |
| Typed PK key encoding (`KeyStruct`) | Yes | No | No | `KeyStruct.cs`, P18 §2 #1 | Culture-invariant encoding. |
| L2 partitioned cache with frozen partition | Yes | No | No | `L2KeyCache.cs`, P18 §2 #2 | Includes `FrozenSentinel`. |
| Within-batch duplicate rejection for all policies | Yes | No | No | `AoudaEngine.EnforcePrimaryKeyUniquenessAsync`, Pk tests | BestEffort still rejects in-batch duplicates. |
| Strict sealed-segment lookup path | Yes | No | No | `LookupKeyInSealedSegmentsAsync`, P18 §3.3 | Uses L1/L0/L3/fallback. |
| L1 sparse index persistence (`pk_index.spr`) | Yes | No | No | `SparsePkIndexFile.cs`, `HraCompactor.cs` | v1 and v2 readable. |
| Elias-Fano L1 encoding for L4-active segments | Yes | No | No | `SparsePkIndex.cs`, `HraCompactor.EvaluateL4Trigger` | Falls back to flat if invalid input. |
| L3 keymap persistence (`pk_keymap.dat/.idx`) | Yes | No | No | `L3KeyMapFile.cs`, `HraCompactor.cs` | Strict policy build path. |
| L3 startup preload | Yes | No | No | `AoudaEngine.PreloadPrimaryKeyIndexes` | Strict tables only. |
| Latent duplicate counter for phase-1 gate | Yes | No | No | `_pkLatentDuplicates`, `HandleDuplicate`, playbook | Exposed in diagnostics. |
| Open-path preload to avoid first-write rebuild | Yes | No | No | P17 completion, `PreloadPrimaryKeyIndexes` | Extended by P18 with L1/L3 load. |
| User-level automated duplicate remediation | No | No | Yes | Playbook only | Operator-driven process. |

---

## 2.7 Core concepts and mental model

- **L2 (hot cache):** Fast in-memory key lookup across HRA, frozen prefix, and hot segments.
- **L1 (sparse index):** One entry per sealed page to locate candidate page offsets quickly.
- **L0 (bloom + zone-map):** Page-level pruning to avoid expensive verification reads.
- **L3 (on-disk keymap):** Exact lookup for strict policy in sealed segments.
- **L4 (monotonic shortcut):** Monotonic clustered segments use optimized L1 encoding and suppress unnecessary work.

Invariants:
- PK checks are always policy-aware, but within-batch duplicates are always rejected.
- Strict policy checks both mutable and sealed data tiers.
- BestEffort disables cross-tier checks, but does not disable in-batch duplicate detection.
- Preload runs before first insert after open to reduce first-write latency spikes.

---

## 2.8 How Aouda implements it

High-level runtime flow:

1. `InsertRowsAsync` resolves table and obtains HRA table.
2. `EnsureKeyIndex` initializes key index state if needed.
3. `EnforcePrimaryKeyUniquenessAsync` computes PK keys for incoming rows.
4. Policy path:
   - `BestEffort`: only in-batch check.
   - `Recent`: `L2` check.
   - `Strict`: `L2` + sealed-segment path (`L1 -> L0 -> L3/fallback`).
5. On duplicate:
   - strict gate on: throw.
   - strict gate off: increment latent counter and continue.
6. On commit, key entries are inserted into L2.

Seal/open path:

- `HraCompactor` writes `pk_index.spr` for PK tables on non-delta seals.
- Strict PK tables additionally write `pk_keymap.dat/.idx`.
- `OpenAsync` calls `PreloadPrimaryKeyIndexes`, which:
  - rebuilds key index for HRA rows,
  - loads `pk_index.spr` if present, otherwise lazy-builds from zone maps,
  - loads `pk_keymap` indexes for strict tables when files exist.

### 2.8.1 Critical path walk-throughs

**Path A: Strict insert duplicate detection (sealed duplicate)**
1. Entry: `AoudaEngine.InsertRowsAsync`.
2. Keys generated via `HraTable.BuildKeyStruct`.
3. L2 check via `LookupKeyLocation`.
4. If not in L2, strict path calls `LookupKeyInSealedSegmentsAsync`.
5. Candidate page chosen by L1; L0 bloom/zone filtering applied.
6. L3 exact lookup (`LookupBlockAsync`) or fallback decode confirms existence.
7. `HandleDuplicate` throws or increments latent counter based on strict gate.

**Path B: Freeze-window key continuity**
1. `HraTable.FreezeForFlush` moves prefix into frozen partition.
2. L2 keeps frozen partition entries addressable via `FrozenSentinel`.
3. Insert in freeze window still sees those keys via `LookupKeyLocation`.
4. `CompleteFreezeFlush` clears frozen partition after persistence/registration.

**Path C: Startup preload**
1. `AoudaEngine.OpenAsync` obtains snapshot.
2. `PreloadPrimaryKeyIndexes` traverses PK tables and known segments.
3. Loads `pk_index.spr` and optional `pk_keymap` index files.
4. Registers L1/L3 structures to avoid first-write rebuild overhead.

---

## 2.9 Why Aouda is different

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Enforce PK uniqueness with hot/cold tiers | Often no strict cross-tier guarantee in columnar systems | Policy-driven layered pipeline with strict default | Safer defaults without forcing dense all-row RAM index |
| Keep PK lookup memory bounded | Dense hash maps grow linearly with rows | L1 sparse + bounded L2 fractions | Predictable memory planning |
| Handle freeze-window correctness | Freeze windows can cause blind spots in naive caches | Frozen-prefix partition stays key-visible | No silent duplicate holes during flush |
| Expose structure health | Minimal visibility into index internals | `GetPkStructuresDiagnosticsAsync` with L0/L1/L2/L3 + latent duplicates | Operators can verify rollout and migration state |

---

## 2.10 Configuration and settings reference

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `TableOptions.PkUniqueness` | enum | `Strict` | `Strict`, `Recent`, `BestEffort` | Table creation/options | Controls cross-tier enforcement level. |
| `MemoryBudgetOptions.MaxHotKeyCacheFraction` | `double` | `0.05` | `0..1` | Engine open budget options | Caps L2 cache bytes by fraction of total RAM budget. |
| `MemoryBudgetOptions.MaxSparsePkIndexFraction` | `double` | `0.001` | `0..1` | Engine open budget options | Caps L1 sparse bytes by fraction of total RAM budget. |
| `_strictEnforcementEnabled` | static runtime flag | `true` | `true/false` | Engine runtime (internal) | Migration gate: throw vs log-and-warn on strict duplicates. |

Precedence notes:
- Table `PkUniqueness` determines algorithmic path.
- Runtime strict gate controls throw behavior after detection.
- Memory fractions derive effective byte caps from `MaxTotalRamBytes`.

---

## 2.11 API and CLI coverage reference

### API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Configure PK uniqueness policy | `TableOptions.PkUniqueness`, `CreateTableAsync(... pkUniqueness)` | Not exposed in this repo | Not direct | Implemented | Set at table creation. |
| Insert with policy checks | `InsertRowsAsync` | Indirect client behavior | `/api/databases/{db}/tables/{table}/rows:insert` path uses server engine | Implemented | Enforced in engine API. |
| Preload PK structures on startup | `OpenAsync` internal path | N/A | N/A | Implemented | Automatic for PK tables. |
| Observe structure diagnostics | `GetPkStructuresDiagnosticsAsync(tableName)` | Not exposed in this repo | Not direct | Implemented | Returns stable shape across policies. |

### Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Automated duplicate remediation command | No built-in API command | Use operator playbook and explicit update/delete workflows | `docs/dev/PkUniqueness-Migration-Playbook.md` | Medium |
| Public admin endpoint for PK diagnostics | No dedicated HTTP route documented here | Call engine API directly in host process | Not documented | Medium |

### `.NET` examples

```csharp
await engine.CreateTableAsync(
    "events",
    new[]
    {
        ("id", DataType.Int64, EncoderPreference.Auto, false, 1, (int?)null, (int?)null, (PartitionFunction?)null),
        ("v", DataType.String, EncoderPreference.Auto, false, (int?)null, (int?)null, (int?)null, (PartitionFunction?)null),
    },
    pkUniqueness: PkUniquenessMode.Strict);

await engine.InsertRowsAsync("events", new[]
{
    new Dictionary<string, object?> { ["id"] = 1L, ["v"] = "first" }
});

var pkDiag = await engine.GetPkStructuresDiagnosticsAsync("events");
Console.WriteLine($"{pkDiag.PkUniqueness} L1={pkDiag.L1Sparse.RamBytes} L2={pkDiag.L2HotCache.Entries}");
```

Common mistake: setting `BestEffort` expecting within-batch duplicates to be allowed; they still throw by design.

---

## 2.12 Scenario playbooks

### Scenario 1: Strict-by-default production table

When to use: primary OLTP/time-series table where duplicate PKs are always invalid.

Steps:
1. Create table with default strict policy.
2. Insert baseline data.
3. Validate diagnostics and monitor latent duplicates.

Expected checks:
- `PkUniqueness` is `Strict`.
- `L1Sparse.AlwaysOn` is true.
- Latent duplicates remain zero when no duplicates are inserted.

### Scenario 2: Ingestion staging table with relaxed policy

When to use: ingestion buffer where dedup is performed upstream.

Steps:
1. Create table with `PkUniquenessMode.BestEffort`.
2. Insert high-volume data.
3. Validate no strict duplicate exceptions for cross-tier duplicates.

Expected checks:
- Cross-tier duplicate inserts can succeed.
- In-batch duplicate rows still throw.
- Diagnostics report `PkUniqueness = BestEffort`.

### Scenario 3: Migration gate rollout (phase-1 to strict reject)

When to use: existing dataset may contain latent duplicates.

Steps:
1. Run with strict detection in log-and-warn mode.
2. Inspect `LatentDuplicates` and investigate duplicate keys.
3. Remediate using playbook.
4. Re-enable strict reject and validate insert behavior.

Expected checks:
- Latent duplicates stabilize at zero before strict reject.
- Duplicate insert attempts throw when strict enforcement is enabled.

---

## 2.13 Operations and observability

| Question | Practical answer |
|---|---|
| Is strict policy active for this table? | `GetPkStructuresDiagnosticsAsync(...).PkUniqueness`. |
| Are sealed PK structures loaded? | Check `L1Sparse` bytes/counts and `L3Keymap.Built`. |
| Are duplicates being detected but not rejected? | Non-zero `LatentDuplicates` with strict enforcement gate disabled. |
| Is L2 growing unexpectedly? | Watch `L2HotCache.Entries` and memory fraction settings. |

Key counters/signals:
- `Perf.KeyIndexLookups`, `Perf.KeyIndexHits`, `Perf.KeyIndexRebuilds`.
- `PkDiagnosticsResult.LatentDuplicates`.
- L1 encoding distribution (`EliasFanoSegmentCount` vs `FlatSegmentCount`).

Recovery expectations:
- L1/L3 files are loaded at open when present.
- Missing/corrupt files are warning-logged; lookup falls back where possible.

---

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Duplicate insert unexpectedly succeeds | Strict gate disabled (phase-1 log-and-warn) or non-strict policy | Confirm `_strictEnforcementEnabled` and table policy. |
| First insert after restart is slow | Preload rebuilding key index for large PK table | Expected one-time open-path cost; monitor `KeyIndexRebuilds`. |
| Strict table has `L3Keymap.Built = false` | No sealed segments yet, or keymap load/build failed | Flush data, verify `pk_keymap.dat/.idx` files, inspect warnings. |
| Large RAM use in PK structures | L2/L1 fractions too high for deployment budget | Tune `MaxHotKeyCacheFraction` / `MaxSparsePkIndexFraction`. |
| Unexpected in-batch duplicate exception in BestEffort | BestEffort does not bypass within-batch duplicate check | Deduplicate batch before insert. |

---

## 2.15 Verification ledger

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Pk uniqueness engine integration | `dotnet test tests/Aouda.Engine.Api.Tests --filter "FullyQualifiedName~PkUniquenessIntegrationTests" --verbosity minimal` | Pass | 2026-05-19 | Policy behavior and diagnostics shape. |
| Migration gate behavior | `dotnet test tests/Aouda.Engine.Api.Tests --filter "FullyQualifiedName~PkUniquenessMigrationGateTests" --verbosity minimal` | Pass | 2026-05-19 | Phase gate strict/log behavior. |
| L3 keymap storage/index behavior | `dotnet test tests/Aouda.Engine.Storage.Tests --filter "FullyQualifiedName~L3KeyMapTests" --verbosity minimal` | Pass | 2026-05-19 | File format, lookup behavior, seal policy. |

---

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Policy enforcement paths | `tests/Aouda.Engine.Api.Tests/PkUniquenessIntegrationTests.cs` | Pass | Strong | Covers strict/recent/best-effort behavior. |
| Migration strict gate behavior | `tests/Aouda.Engine.Api.Tests/PkUniquenessMigrationGateTests.cs` | Pass | Strong | Covers phase gate semantics. |
| L2 frozen/batch pin semantics | `tests/Aouda.Engine.Storage.Tests/Index/PkUniquenessRegressionTests.cs` | Pass | Strong | Freeze-window and eviction safety behavior. |
| L1 sparse index including EF | `tests/Aouda.Engine.Storage.Tests/Index/SparsePkIndexTests.cs`, `SparsePkIndexEliasFanoTests.cs` | Pass | Strong | Includes v1/v2 file compatibility. |
| L3 keymap files and lookup | `tests/Aouda.Engine.Storage.Tests/Index/L3KeyMapTests.cs` | Pass | Strong | Includes corruption and truncation guards. |

---

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| End-to-end HTTP/admin diagnostics path | PK diagnostics are engine-level; operational users often consume HTTP | Add server integration tests once diagnostics endpoint is defined | Medium |
| Large-scale preload latency characterization | Startup behavior at very large PK tables needs explicit SLA evidence | Add benchmark/integration test for preload time and memory at target scales | Medium |

---

## 2.18 Known gaps and undone work

| Gap | Impact | Source |
|---|---|---|
| Automatic duplicate-remediation workflow is not built-in | Operators must execute remediation manually | `docs/dev/PkUniqueness-Migration-Playbook.md` |
| Public HTTP surface for PK diagnostics is not documented in this functionality | Operational access pattern outside embedded/host usage is unclear | Source materials in this session |
| Additional optimization/backfill tooling for old segments remains outside current baseline | Some large historical datasets may rely on fallback/rebuild paths | ADR 0028 consequence notes |

Backlog status note:
- P18 source indicates `BL-061` is complete; no unresolved P18-specific backlog item is documented in source materials used for this doc.

---

## 2.19 References

### ADRs and docs
- `docs/decisions/0028-pk-indexing-memory-model.md`
- `docs/tasks/P18-COMPLETION.md`
- `docs/tasks/P17-COMPLETION.md`
- `docs/tasks/PreP4-COMPLETION.md`
- `docs/dev/PkUniqueness-Migration-Playbook.md`

### Code paths
- `src/Aouda.Engine.Core/Schema/Types.cs`
- `src/Aouda.Engine.Storage/Memory/MemoryBudgetOptions.cs`
- `src/Aouda.Engine.Storage/Index/KeyStruct.cs`
- `src/Aouda.Engine.Storage/Index/L2KeyCache.cs`
- `src/Aouda.Engine.Storage/Index/SparsePkIndex.cs`
- `src/Aouda.Engine.Storage/Index/SparsePkIndexFile.cs`
- `src/Aouda.Engine.Storage/Index/L3KeyMap.cs`
- `src/Aouda.Engine.Storage/Index/L3KeyMapFile.cs`
- `src/Aouda.Engine.Storage/Index/PkStructuresDiagnostics.cs`
- `src/Aouda.Engine.Storage/Hra/HraCompactor.cs`
- `src/Aouda.Engine.Api/AoudaEngine.cs`
- `src/Aouda.Engine.Diagnostics/Perf.cs`

### Test paths
- `tests/Aouda.Engine.Api.Tests/PkUniquenessIntegrationTests.cs`
- `tests/Aouda.Engine.Api.Tests/PkUniquenessMigrationGateTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Index/PkUniquenessRegressionTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Index/SparsePkIndexTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Index/SparsePkIndexEliasFanoTests.cs`
- `tests/Aouda.Engine.Storage.Tests/Index/L3KeyMapTests.cs`

---

## 2.20 What is missing from this document?

1. The source materials in this session do not provide a confirmed public HTTP endpoint for `GetPkStructuresDiagnosticsAsync`; the functionality is verified at engine API level.
2. This document does not include measured latency/throughput numbers for billion-row datasets; ADR 0028 provides modeling and qualitative bounds, but not benchmark artifacts in the current sources.
