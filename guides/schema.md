---
title: "Schema Lifecycle"
nav_order: 2
parent: "Guides"
---

# Aouda Functionality: Schema Lifecycle and Evolution

Document status: Approved baseline  
Primary owner: Aouda maintainers  
Last updated: 2026-05-22

Coverage phases: P4, P7, P8, P14  
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P7/`, `docs/tasks/P8/`, `docs/tasks/P14/`  
Primary ADRs: `docs/decisions/0018-alter-add-column-no-backfill.md`, `docs/decisions/0019-declarative-schema-management.md`, `docs/decisions/0025-adra-auth-db-resolved-authorization.md`  
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-HotCold-And-Memory.md`, `docs/dev/Functionality-RealTime-Streaming.md`

## Start Here

If your question is "How do I manage schema safely right now?":
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`

If your question is "What is shipped vs planned?":
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Schema lifecycle is where reliability breaks first in fast teams:

- Early development needs velocity (inference and low ceremony).
- Production needs repeatability (reviewed desired state and controlled apply).
- Large datasets need additive evolution without expensive global rewrites.
- Multi-env deployment needs explicit policy for destructive changes.

Aouda's schema lifecycle combines both worlds:

- Start fast with `InferenceMode: On`.
- Move to declarative desired-state with schema diff/apply workflows.
- Keep runtime truth in the server catalog.
- Apply destructive changes only by explicit opt-in.

---

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What defaults apply if I do nothing? | `2.3 Defaults and zero-config behavior` |
| What is actually available today? | `2.4 Availability status` |
| Which phase delivered what? | `2.5 Phase coverage matrix` |
| Which capabilities are full/partial/missing? | `2.6 Capability coverage matrix` |
| How schema changes execute internally | `2.8 How Aouda implements it` |
| Which configs, flags, and env vars exist | `2.10 Configuration and settings reference` |
| Full API surface and current gaps | `2.11 API and CLI coverage reference` |
| Practical rollout patterns | `2.12 Scenario playbooks` |
| What still needs work | `2.17 Testing gaps and proposed tests`, `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.3`, `2.11`, `2.12` |
| Operator / release engineer | `2.10`, `2.12`, `2.13`, `2.14` |
| SDK maintainer | `2.11`, `2.17`, `2.18` |
| Engine contributor | `2.5`, `2.8`, `2.16`, `2.19` |

### Source map

- Task/report evidence:
  - `docs/tasks/P4/P4-EpicA-Task3-SchemaManagementApi-Report.md`
  - `docs/tasks/P7/BL025-Fix2-AddColumnColdBackfill-Report.md`
  - `docs/tasks/P8/P8-DeclarativeSchemaManagement-Tasks.md`
  - `docs/tasks/P8/P8-EpicC-Task4-RestApiEndpoints-Report.md`
  - `docs/tasks/P8/P8-EpicF-Task2-CatalogLevelBranchIsolation-Report.md`
  - `docs/tasks/P8/P8-EpicF-Task3-BranchDiffAndMerge-Report.md`
  - `docs/tasks/P8/P8-EpicF-Task4-CopyOnWriteSegmentSharing-Report.md`
- Core code:
  - `src/Aouda.Server/Controllers/TablesController.cs`
  - `src/Aouda.Server/Controllers/SchemaController.cs`
  - `src/Aouda.Server/Controllers/BranchController.cs`
  - `src/Aouda.Server/Configuration/SchemaOptions.cs`
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.Cli/Commands/SchemaCommandHandler.cs`
  - `src/Aouda.Client/SchemaOperations.cs`
  - `src/Aouda.Engine.Schema/Diff/SchemaDiffEngine.cs`
  - `src/Aouda.Engine.Schema/Apply/SchemaApplyEngine.cs`
  - `src/Aouda.Engine.Schema/Export/SchemaExporter.cs`
- Test evidence:
  - `tests/Aouda.Server.Tests/SchemaControllerIntegrationTests.cs`
  - `tests/Aouda.Cli.Tests/SchemaCommandHandlerTests.cs`
  - `tests/Aouda.Client.Tests/Schema/SchemaApiTests.cs`
  - `tests/Aouda.Engine.Schema.Tests/Diff/SchemaDiffEngineTests.cs`
  - `tests/Aouda.Engine.Schema.Tests/Apply/SchemaApplyEngineTests.cs`
  - `tests/Aouda.Engine.Storage.Tests/ColdColumnBackfillTests.cs`
  - `tests/Aouda.Engine.Schema.Tests/Branching/BranchMergeTests.cs`

---

## 2.3 Defaults and zero-config behavior

If you do not configure schema management explicitly:

- Server schema inference defaults to `InferenceMode = On`.
- Inserts to missing tables can create schema (inference path) unless disabled.
- Runtime schema truth is always the server catalog, not a file.
- Declarative safety still defaults to non-destructive:
  - API apply defaults to `allowDestructive = false`.
  - CLI apply defaults to no `--allow-destructive`.

| Setting / behavior | Default | Allowed values | Practical impact |
|---|---|---|---|
| `Aouda:Schema:InferenceMode` | `On` | `Off`, `On`, `Extend` (planned — not yet wired) | Backward-compatible schema-on-write behavior enabled |
| `AOUDA_SCHEMA_INFERENCE_MODE` | unset | `Off`, `On`, `Extend`; or unset (no override) | No override unless explicitly set |
| Apply option `allowDestructive` | `false` | `true`, `false` | Drop operations are skipped unless explicitly allowed |
| Apply option `dryRun` | `false` | `true`, `false` | Apply executes unless dry-run requested |
| CLI `schema history` pagination | `limit=50`, `offset=0` | Any non-negative integer for `limit` and `offset` | Newest-first history default view |
| CLI output mode | human-readable | `human-readable` (default), `json` (via `--json` flag) | Use `--json` when machine parsing is needed |

---

## 2.4 Availability status (implementation honesty)

### Available now

- Imperative DDL API for table and column lifecycle (`/api/tables` surfaces).
- Declarative schema API:
  - `POST /schema/diff`
  - `POST /schema/apply`
  - `GET /schema/export`
  - `GET /schema/history`
- .NET client schema wrappers (`DiffAsync`, `ApplyAsync`, `ExportAsync`, `HistoryAsync`).
- .NET CLI schema commands:
  - `schema diff`, `apply`, `export`, `validate`, `history`.
- Add-column invariants from ADR 0018 + follow-up fixes:
  - no on-disk rewrite of historical column files,
  - query-time defaults for missing historical values,
  - cold-page aligned backfill support for new columns.
- Branch lifecycle with schema diff/merge and copy-on-write segment sharing (server-side branch endpoints and engine support).
- **`autoIncrement` toggle on existing columns** — the `UpdateColumnAutoIncrement` change type enables toggling `autoIncrement` on or off for any existing integer-type column via the declarative schema apply path or the Studio "Toggle AutoId" action. The counter recovers from the column's MAX existing value on first insert after enabling. Available via `POST /schema/apply`, Studio UI, and (Studio-internal) schema export→patch→apply pattern. Tracked in BL-126.

### Planned / proposed

- `InferenceMode: Extend` hybrid mode remains planned (tracked backlog item).
- Richer CI/CD experience around schema governance is documented, but not all convenience surfaces are first-class SDK calls.
- Broader branch ergonomics in client libraries are still expected evolution.

### Reserved / not yet wired

- .NET CLI `schema seed` command is still a stub even though server seed endpoint exists.
- First-class branch/seed wrappers on `ISchemaOperations` are not present.
- Dedicated "validate" HTTP endpoint is not present (CLI validate composes diff locally).

---

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P4 | `P4-EpicA-Task3-SchemaManagementApi-Report.md` | Core imperative table/column/policy HTTP management | Declarative desired-state not yet in this phase | N/A |
| P7 | `BL025-Fix2-AddColumnColdBackfill-Report.md` | Correct add-column behavior over cold segments with aligned backfill | Further performance tuning can continue | N/A |
| P8 | `P8-DeclarativeSchemaManagement-Tasks.md`, C.4 report, F.2/F.3/F.4 reports | Declarative schema diff/apply/export/history, migration history, CLI integration, branch isolation/merge/COW sharing | `InferenceMode: Extend` deferred; CLI seed command still stub on .NET tool | `docs/BACKLOG.md` (BL-022) |
| P14 | `P14-TaskC1-TableSchemaExtension.md` (implemented report included in file body) | Schema model/path now includes table auth metadata options (`authMode`, permission dimension, resolver name) | Wider auth behavior docs still broader than this domain | N/A |

---

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Inference-first schema lifecycle (`On`/`Off`) | Yes | No | No | `SchemaOptions.cs`, `TablesController.cs` | Default is `On`; `Off` blocks auto-create |
| Imperative table and column lifecycle APIs | Yes | No | No | `TablesController.cs`, P4 report | Mature and well-tested |
| Declarative schema diff/apply/export/history APIs | Yes | No | No | `SchemaController.cs`, P8 C.4 report | Includes markdown diff format |
| Destructive-change safety gates | Yes | No | No | `SchemaApplyEngine.cs`, `SchemaCommandHandler.cs` | Explicit opt-in required |
| CLI declarative workflow (.NET) | Yes | No | No | `Program.cs`, CLI tests | validate is diff-based check |
| C# client declarative wrappers | Yes | No | No | `ISchemaOperations.cs`, `SchemaOperations.cs` | Diff/apply/export/history available |
| Add-column no-rewrite semantics | Yes | No | No | ADR 0018, P7 fix2 report | Query-time defaults and alignment |
| Cold aligned backfill on add-column | Yes | No | No | P7 fix2 report, storage tests | Prevents cross-column alignment bugs |
| autoIncrement toggle on existing columns (`UpdateColumnAutoIncrement`) | Yes | No | No | BL-126, `AutoIncrementService.cs`, `SchemaDiffEngine.cs` | Integer columns only; counter resets from MAX on first insert after enable |
| Server seed endpoint | Yes | No | No | `SchemaController.cs` | Endpoint exists |
| .NET CLI seed command | No | Yes | No | `Program.cs` + `RunSeedStub` | Stubbed, intentionally not wired |
| Branch create/list/get/delete/diff/merge APIs | Yes | No | No | `BranchController.cs`, F.2/F.3 reports | Includes conflict handling |
| Copy-on-write branch data sharing | Yes | No | No | F.4 report, branch tests | Branch writes isolated from parent |
| `InferenceMode: Extend` | No | No | Yes | `SchemaOptionsValidator.cs`, P8 tasks | Explicitly deferred |

---

## 2.7 Core concepts and mental model

- **Intent truth**: `aouda.schema.json` in your app repo expresses desired state.
- **Runtime truth**: Aouda server catalog is authoritative at runtime.
- **Lifecycle pattern**: bootstrap -> stabilize -> evolve -> harden -> contract.
- **Safety boundary**:
  - Additive changes are normal path.
  - Destructive changes are explicit and separate.
- **Add-column invariant**:
  - old rows are not rewritten in-place,
  - defaults/nulls are synthesized or aligned via backfill path.
- **Branching model**:
  - branch catalogs diverge from parent,
  - data sharing uses copy-on-write semantics,
  - merges are schema-level with conflict detection.

---

## 2.8 How Aouda implements it

High-level flow:

1. Clients or CLI send desired schema to server diff/apply endpoints.
2. Server exports actual catalog state and computes changes (`SchemaDiffEngine`).
3. Apply engine executes safe changes and conditionally executes destructive changes.
4. Migration history records apply operations when effective changes occurred.
5. Table-level add-column operations preserve alignment invariants across hot/cold paths.
6. Branch manager can isolate schema evolution and merge back with conflict checks.

Key anchors:

- Diff/Apply/Export engine:
  - `src/Aouda.Engine.Schema/Diff/SchemaDiffEngine.cs`
  - `src/Aouda.Engine.Schema/Apply/SchemaApplyEngine.cs`
  - `src/Aouda.Engine.Schema/Export/SchemaExporter.cs`
- HTTP integration:
  - `src/Aouda.Server/Controllers/SchemaController.cs`
  - `src/Aouda.Server/Controllers/TablesController.cs`
- Client and CLI:
  - `src/Aouda.Client/SchemaOperations.cs`
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.Cli/Commands/SchemaCommandHandler.cs`
- Branching:
  - `src/Aouda.Server/Controllers/BranchController.cs`
  - `src/Aouda.Engine.Schema/Branching/BranchManager.cs`

---

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Declarative diff (CLI -> API -> plan)

1. `dotnet aouda schema diff` resolves server/database/file/env context.
2. CLI discovers and loads schema file (with optional env overlay).
3. Client posts desired schema to `POST /api/databases/{db}/schema/diff`.
4. Server exports actual catalog state, computes `SchemaDiffResult`.
5. Response is returned as JSON or markdown plan.

### Walk-through B: Declarative apply with destructive guard

1. CLI or client sends `{ schema, options }` to `/schema/apply`.
2. Server computes diff and executes via `SchemaApplyEngine`.
3. If `allowDestructive=false`, destructive changes are marked skipped.
4. If at least one change applied and not dry-run, history entry is recorded.
5. Caller receives `SchemaApplyResponse` with result summary and optional `historyId`.

### Walk-through C: Add-column on existing cold segments

1. Table column add request enters `TablesController`.
2. Catalog adds column metadata.
3. Engine triggers cold column backfill for aligned default pages where required.
4. Query paths preserve row alignment and return defaults for historical rows.
5. Existing rows remain immutable (no full historical rewrite).

### Walk-through D: Branch schema lifecycle

1. Create branch from parent catalog snapshot.
2. Apply schema changes in branch scope only.
3. Generate merge plan (three-way where base snapshot exists).
4. Conflicts return merge-plan response; `force` can override.
5. Merge execution applies branch changes to parent catalog and records history.

---

## 2.9 Why Aouda is different (differentiators)

- **Runtime/catalog separation is explicit**: schema file is deployment artifact, not runtime dependency.
- **Add-column design is scale-aware**: no historical rewrite + alignment-safe read/backfill behavior.
- **Destructive safety is first-class**: opt-in per apply operation, not hidden default.
- **Schema + branch model is unified**: schema lifecycle includes branch diff/merge with copy-on-write semantics.

---

## 2.10 Configuration and settings reference (complete surface)

### A) Server configuration

| Surface | Key | Default | Effect |
|---|---|---|---|
| startup config | `Aouda:Schema:InferenceMode` | `On` | Controls inference-only behavior (`Off` or `On`) |
| Env var | `AOUDA_SCHEMA_INFERENCE_MODE` | unset | Overrides server inference mode |

### B) CLI context resolution

| Input | Option | Env fallback | Used by |
|---|---|---|---|
| Server URL | `--server` | `AOUDA_SERVER` then `AOUDA_URL` | All schema CLI commands |
| Database name | `--database` | `AOUDA_DATABASE` | All schema CLI commands |
| Schema file path | `--file` | none | `diff/apply/validate/seed` |
| Overlay environment | `--env` | `AOUDA_ENVIRONMENT` | file overlay selection |
| Output format | `--json` | none | machine-readable output |

### C) Command-specific options

| Command | Options | Notes |
|---|---|---|
| `schema apply` | `--allow-destructive`, `--dry-run` | safety and planning controls |
| `schema export` | `--output` (required) | writes exported schema file |
| `schema history` | `--limit`, `--offset` | paged history view |

### D) Apply request options (API)

| Field | Default | Behavior |
|---|---|---|
| `options.allowDestructive` | `false` | skip destructive changes unless true |
| `options.dryRun` | `false` | plan only when true |

---

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (programmatic declarative flow)

```csharp
using Aouda.Abstractions.Schema;
using Aouda.Client;
using Aouda.Engine.Schema.Apply;

using var client = new AoudaClient("http://localhost:5433", "myapp");

var schema = SchemaFile.LoadWithOverlay("aouda.schema.json", "staging");
var diff = await client.Schema.DiffAsync(schema);
var apply = await client.Schema.ApplyAsync(
    schema,
    new ApplyOptions(AllowDestructive: false, DryRun: false));

var history = await client.Schema.HistoryAsync(limit: 20, offset: 0);
```

### TypeScript example (CLI-driven)

```bash
npx @aouda/client schema diff --server http://localhost:5433 --database myapp
npx @aouda/client schema apply --server http://localhost:5433 --database myapp
npx @aouda/client schema validate --server http://localhost:5433 --database myapp
npx @aouda/client schema history --server http://localhost:5433 --database myapp
```

### HTTP/protocol examples

```http
POST /api/databases/myapp/schema/diff
Content-Type: application/json

{ "database": "myapp", "tables": { } }
```

```http
POST /api/databases/myapp/schema/apply
Content-Type: application/json

{
  "schema": { "database": "myapp", "tables": { } },
  "options": { "allowDestructive": false, "dryRun": false }
}
```

```http
GET /api/databases/myapp/schema/export
GET /api/databases/myapp/schema/history?limit=50&offset=0
```

### Complete versioned schema examples (v1 -> v2 -> v3)

This is a full, versioned example set you can keep in git and run end-to-end.

#### v1 (baseline): `aouda.schema.v1.json`

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "commerce",
  "tables": {
    "customers": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "email": { "type": "String" },
        "name": { "type": "String", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "orders": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "status": { "type": "String" },
        "total_amount": { "type": "Decimal" },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    }
  },
  "settings": {
    "durability": {
      "walEnabled": true
    }
  }
}
```

#### v2 (expand release): `aouda.schema.v2.json`

Changes from v1:
- Adds nullable `priority` and `fulfilled_at` to `orders`.
- Adds new `payments` table.
- Keeps existing columns/tables for compatibility.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "commerce",
  "tables": {
    "customers": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "email": { "type": "String" },
        "name": { "type": "String", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "orders": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "status": { "type": "String" },
        "total_amount": { "type": "Decimal" },
        "priority": { "type": "Int32", "nullable": true },
        "fulfilled_at": { "type": "Timestamp", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "payments": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "order_id": { "type": "Int64", "references": "orders.id" },
        "provider": { "type": "String" },
        "status": { "type": "String" },
        "amount": { "type": "Decimal" },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    }
  },
  "settings": {
    "durability": {
      "walEnabled": true
    }
  }
}
```

#### v3 (contract release): `aouda.schema.v3.json`

Changes from v2:
- Drops `orders.status` after application migration is complete.
- Hardens policy for `payments` to `ColdPreferred`.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "commerce",
  "tables": {
    "customers": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "email": { "type": "String" },
        "name": { "type": "String", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "orders": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "total_amount": { "type": "Decimal" },
        "priority": { "type": "Int32", "nullable": true },
        "fulfilled_at": { "type": "Timestamp", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "payments": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "order_id": { "type": "Int64", "references": "orders.id" },
        "provider": { "type": "String" },
        "status": { "type": "String" },
        "amount": { "type": "Decimal" },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "ColdPreferred" },
      "durability": { "walEnabled": true },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    }
  },
  "settings": {
    "durability": {
      "walEnabled": true
    }
  }
}
```

#### Environment overlays (complete)

Base filename (checked in as current desired state): `aouda.schema.json`  
Overlay examples:

`aouda.schema.staging.json`:

```json
{
  "extends": "aouda.schema.json",
  "tables": {
    "payments": {
      "policy": { "storageTemperature": "Auto" }
    }
  },
  "settings": {
    "durability": {
      "walEnabled": true
    }
  }
}
```

`aouda.schema.prod.json`:

```json
{
  "extends": "aouda.schema.json",
  "tables": {
    "payments": {
      "policy": { "storageTemperature": "ColdPreferred" }
    }
  },
  "settings": {
    "durability": {
      "walEnabled": true
    }
  }
}
```

#### Versioned execution sequence

```bash
# v1 baseline
dotnet aouda schema diff --server http://localhost:5433 --database commerce --file aouda.schema.v1.json
dotnet aouda schema apply --server http://localhost:5433 --database commerce --file aouda.schema.v1.json

# v2 expand
dotnet aouda schema diff --server http://localhost:5433 --database commerce --file aouda.schema.v2.json
dotnet aouda schema apply --server http://localhost:5433 --database commerce --file aouda.schema.v2.json

# v3 contract (safe pass first, then destructive pass)
dotnet aouda schema diff --server http://localhost:5433 --database commerce --file aouda.schema.v3.json
dotnet aouda schema apply --server http://localhost:5433 --database commerce --file aouda.schema.v3.json
dotnet aouda schema apply --server http://localhost:5433 --database commerce --file aouda.schema.v3.json --allow-destructive
```

### A) API coverage matrix

| Surface | Capability | Status | Evidence |
|---|---|---|---|
| HTTP | `/schema/diff` | Available | `SchemaController.cs` + integration tests |
| HTTP | `/schema/apply` | Available | `SchemaController.cs` + integration tests |
| HTTP | `/schema/export` | Available | `SchemaController.cs` + integration tests |
| HTTP | `/schema/history` | Available | `SchemaController.cs` + integration tests |
| HTTP | `/schema/seed` | Available | `SchemaController.cs` |
| C# SDK | `DiffAsync/ApplyAsync/ExportAsync/HistoryAsync` | Available | `SchemaOperations.cs` + client tests |
| .NET CLI | diff/apply/export/validate/history | Available | `Program.cs` + CLI tests |
| HTTP | branch create/list/get/delete/diff/merge/query/insert | Available | `BranchController.cs` |

### B) Missing API matrix

| Missing / partial surface | Current state | Practical workaround |
|---|---|---|
| C# SDK seed wrapper | Missing on `ISchemaOperations` | call HTTP directly or server tooling path |
| C# SDK branch wrapper | Missing on `ISchemaOperations` | call branch HTTP endpoints directly |
| HTTP validate endpoint | Missing | CLI `schema validate` performs diff and exits by drift |
| .NET CLI `schema seed` | Stubbed | use seed endpoint via HTTP until CLI command is wired |
| `InferenceMode: Extend` | Deferred | use explicit transition `On` -> export -> `Off` |

### C) Aouda.Schema.Contract NuGet facade

`Aouda.Schema.Contract` is the thin NuGet package external users install to work with schema types in C#. It does not contain the full engine — it recompiles only the schema model and result types from `Aouda.Engine.Schema` under the same namespaces, so you get the exact same types without a dependency on the server-side engine.

When you add `Aouda.Schema.Contract` to your project, you get:

| Type | Namespace | Purpose |
|---|---|---|
| `SchemaDocument` | `Aouda.Engine.Schema.Models` | Root type for `aouda.schema.json`: `$schema`, `database`, `tables`, `settings`, `extends` |
| `TableDefinition` | `Aouda.Engine.Schema.Models` | Per-table structure: `columns`, `partitionKey`, `clusterColumns`, `policy`, `durability`, `partitionLevelSecurity`, `authMode`, `permissionDimension`, `rlsResolverName` |
| `ColumnDefinition` | `Aouda.Engine.Schema.Models` | Per-column: `type`, `primaryKey`, `autoIncrement`, `nullable`, `references` |
| `PartitionKeyEntry` | `Aouda.Engine.Schema.Models` | Partition key entry: `column`, `function` |
| `TablePolicyDto` | `Aouda.Engine.Schema.Models` | Table policy: `storageTemperature` |
| `TableDurabilityDto` | `Aouda.Engine.Schema.Models` | Table durability: `walEnabled`, `replicationFactor` |
| `SchemaSettings` | `Aouda.Engine.Schema.Models` | Database-level settings container |
| `SchemaSettingsDurability` | `Aouda.Engine.Schema.Models` | Database-level durability: `walEnabled`, `replicationFactor` |
| `ApplyOptions` | `Aouda.Engine.Schema.Apply` | Apply request options: `AllowDestructive`, `DryRun` |
| `ApplyStatus` | `Aouda.Engine.Schema.Apply` | Outcome of a single applied change (see section D below) |
| `ApplyResultEntry` | `Aouda.Engine.Schema.Apply` | Per-change apply outcome: `ChangeType`, `TableName`, `ColumnName`, `Status`, `Reason` |
| `ApplyResultSummary` | `Aouda.Engine.Schema.Apply` | Aggregate counts: `TotalChanges`, `Applied`, `Skipped`, `Failed`, `Planned` |
| `SchemaApplyResult` | `Aouda.Engine.Schema.Apply` | Full apply result: `Entries`, `Summary` |
| `SchemaDiffResult` | `Aouda.Engine.Schema.Diff` | Diff output: `Changes`, `Summary`, `Warnings` |
| `SchemaChangeType` | `Aouda.Engine.Schema.Diff` | Classification of a diff change (see section D below) |
| `SchemaChangeWarning` | `Aouda.Engine.Schema.Diff` | Warning for unsupported modification: `TableName`, `ColumnName`, `Property`, `ActualValue`, `DesiredValue`, `Message` |
| `DiffSummary` | `Aouda.Engine.Schema.Diff` | Diff aggregate counts |
| `MigrationHistoryEntry` | `Aouda.Engine.Schema.History` | History record: `Id`, `Timestamp`, `Source`, `SchemaHash`, `Changes`, `AppliedBy` |
| `MigrationSource` | `Aouda.Engine.Schema.History` | Who triggered an apply (see section D below) |

The `Aouda.Client` package depends on `Aouda.Schema.Contract` and re-exports these types through its own `ISchemaOperations` interface, so you do not need to install `Aouda.Schema.Contract` separately if you already have `Aouda.Client`.

Install:

```bash
dotnet add package Aouda.Schema.Contract
```

The namespaces match exactly what the engine uses internally, so code written against `Aouda.Schema.Contract` types is also valid in embedded-mode projects that reference the engine directly.

### D) Schema type reference (ApplyStatus, SchemaChangeType, MigrationSource, DiffSummary, Warnings)

#### ApplyStatus

`ApplyStatus` is the outcome of executing a single change from the diff:

| Value | Meaning |
|---|---|
| `Applied` | Change was successfully executed against the catalog. |
| `Skipped` | Change was skipped — most commonly because `AllowDestructive` is `false` and the change is destructive. Also skipped for `ReplicationFactor`-only durability changes (not yet representable in the engine policy). |
| `Failed` | Change execution threw an exception. The apply continues to the next change (continue-on-error). The `Reason` field on `ApplyResultEntry` contains the exception message. |
| `Planned` | Dry-run mode: the change would have been executed but was not. `DryRun = true` produces all entries with status `Planned`. |

#### SchemaChangeType

`SchemaChangeType` classifies what a diff change represents. The apply engine executes changes in the order listed below (creates first, drops last):

| Value | Destructive | Meaning |
|---|---|---|
| `CreateTable` | No | A table exists in desired but not in actual. |
| `AddColumn` | No | A column exists in desired table but not in actual. |
| `UpdatePolicy` | No | The `storageTemperature` in the table's `policy` changed. |
| `UpdateDurability` | No | The `walEnabled` (or `replicationFactor`) in the table's `durability` changed. |
| `UpdatePartitionLevelSecurity` | No | The `partitionLevelSecurity` flag on the table changed. |
| `UpdateAuthorizationOptions` | No | One or more of `authMode`, `permissionDimension`, or `rlsResolverName` changed. |
| `UpdateSettings` | No | The database-level `settings.durability` changed. |
| `UpdateColumnAutoIncrement` | No | The `autoIncrement` flag on an existing column changed between desired and actual. Only produced for integer column types (`Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`). Counted in `DiffSummary.ColumnsAltered`. |
| `DropColumn` | **Yes** | A column exists in actual but not in desired. Skipped unless `AllowDestructive = true`. |
| `DropTable` | **Yes** | A table exists in actual but not in desired. Skipped unless `AllowDestructive = true`. |

#### SchemaDiffResult.Warnings — unsupported modifications

The diff engine produces `Changes` for operations it can execute and `Warnings` for operations it detects but **cannot** execute. Warnings are returned alongside changes and do not become apply entries. They require manual intervention (e.g. drop and re-create the table or column).

Operations that produce warnings (not changes):

| Changed property | Warning message pattern | Action required |
|---|---|---|
| Column `type` | `"Column type change from '...' to '...' is not supported."` | Drop column, re-create with new type. |
| Column `primaryKey` | `"Primary key change ... is not supported."` | Drop table, re-create. |
| Column `nullable` | `"Nullable change ... is not supported."` | Drop column, re-create. |
| Column `references` | `"References change ... is not supported."` | Drop column, re-create. |
| Table `partitionKey` | `"Partition key change on table '...' is not supported."` | Drop table, re-create. |
| Table `clusterColumns` | `"Cluster columns change on table '...' is not supported."` | Drop table, re-create. |

> **Note:** Changing `autoIncrement` on an existing integer column is **no longer a warning** — it now generates an `UpdateColumnAutoIncrement` change that the apply engine executes directly. Non-integer columns (`String`, `Double`, etc.) with `autoIncrement: true` in the desired schema will still produce a warning because the server rejects non-integer auto-increment columns.

Always inspect `SchemaDiffResult.Warnings` after a diff, especially before significant schema migrations. Warnings indicate intent/reality gaps that the apply pass will silently skip.

```csharp
var diff = await client.Schema.DiffAsync(schema);

if (diff.Warnings is { Count: > 0 })
{
    foreach (var w in diff.Warnings)
        Console.WriteLine($"WARNING {w.TableName}.{w.ColumnName ?? "(table)"} [{w.Property}]: {w.Message}");

    // Decide: abort, or proceed with apply (warnings are not applied — only changes are)
}

Console.WriteLine($"Changes: {diff.Summary.TotalChanges} ({diff.Summary.SafeChanges} safe, {diff.Summary.DestructiveChanges} destructive)");
```

#### DiffSummary fields

`DiffSummary` is returned inside `SchemaDiffResult.Summary`:

| Field | Description |
|---|---|
| `TotalChanges` | `SafeChanges + DestructiveChanges` |
| `SafeChanges` | Non-destructive changes |
| `DestructiveChanges` | Destructive changes (DropColumn, DropTable) |
| `TablesCreated` | Count of `CreateTable` changes |
| `TablesDropped` | Count of `DropTable` changes |
| `ColumnsAdded` | Count of `AddColumn` changes |
| `ColumnsDropped` | Count of `DropColumn` changes |
| `ColumnsAltered` | Count of `UpdateColumnAutoIncrement` changes (and future column-level alteration types). Optional — `0` on servers that do not yet support this field. |
| `PoliciesUpdated` | Count of `UpdatePolicy` changes |
| `DurabilitiesUpdated` | Count of `UpdateDurability` changes |
| `OptionsUpdated` | Count of `UpdatePartitionLevelSecurity` + `UpdateAuthorizationOptions` changes |
| `SettingsUpdated` | Count of `UpdateSettings` changes |

#### MigrationSource

`MigrationSource` is stored in each `MigrationHistoryEntry` and identifies what triggered the apply:

| Value | Meaning |
|---|---|
| `ApiApply` | Schema apply via REST API (`POST /schema/apply`). Primary source under the current model. |
| `ManualDdl` | Change applied directly to the catalog outside of schema apply (e.g. via Studio or direct DDL endpoint). |
| `Inference` | Change applied by inference (auto-create on first insert, `InferenceMode = On`). |
| `BranchMerge` | Change applied by merging a branch into the parent catalog. |
| `StartupApply` | Retained for backward compatibility; not used for new entries. |

### E) Schema JSON field reference (complete)

This section documents every field available in `aouda.schema.json` by type. All fields are optional except `type` on `ColumnDefinition`.

#### SchemaDocument (root)

| Field | JSON key | Type | Required | Notes |
|---|---|---|---|---|
| `$schema` | `$schema` | `string` | No | JSON Schema URL for IDE validation. Use `"https://aouda.io/schema/v1.json"`. |
| `database` | `database` | `string` | Yes (for diff/apply) | Target database name. Must match the `--database` / `AOUDA_DATABASE` value. |
| `tables` | `tables` | `object` | No | Map of table name → `TableDefinition`. Omit tables to leave them untouched. |
| `settings` | `settings` | `SchemaSettings` | No | Database-level settings. |
| `extends` | `extends` | `string` | No (overlay only) | Used in overlay files to identify the base file by name (e.g. `"aouda.schema.json"`). |

#### TableDefinition (entry in `tables`)

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `columns` | `columns` | `object` | None | Map of column name → `ColumnDefinition`. Required when creating a table. |
| `partitionKey` | `partitionKey` | `PartitionKeyEntry[]` | None | Ordered list of partition key columns. Omit for non-partitioned tables. |
| `clusterColumns` | `clusterColumns` | `string[]` | None | Ordered list of clustering column names. |
| `policy` | `policy` | `TablePolicyDto` | None | Storage policy for this table. |
| `durability` | `durability` | `TableDurabilityDto` | None | WAL and replication settings for this table. |
| `partitionLevelSecurity` | `partitionLevelSecurity` | `bool` | `false` | Enable partition-level security (PLS) for this table. Only valid on partitioned tables. Allowed values: `true`, `false`. |
| `authMode` | `authMode` | `string` | `"jwt-claim"` | Authorization mode. Valid values: `"jwt-claim"`, `"auth-db-pls"`, `"auth-db-rls"`. |
| `permissionDimension` | `permissionDimension` | `string` | None | ADRA permission dimension name. Used with `"auth-db-pls"` mode. |
| `rlsResolverName` | `rlsResolverName` | `string` | None | RLS resolver name. Used with `"auth-db-rls"` mode. |

#### ColumnDefinition (entry in `columns`)

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `type` | `type` | `string` | **Required** | Column data type. See valid values below. |
| `primaryKey` | `primaryKey` | `int` | None | Ordinal position in composite primary key (1-based). Omit if not a PK column. |
| `autoIncrement` | `autoIncrement` | `bool` | `false` | Auto-increment identity column. Only valid on integer primary key columns. Allowed values: `true`, `false`. |
| `nullable` | `nullable` | `bool` | `false` | Whether the column accepts null values. Allowed values: `true`, `false`. |
| `references` | `references` | `string` | None | Foreign key reference in `"table.column"` format. |

Valid `type` values: `Int32`, `Int64`, `Int16`, `UInt16`, `UInt32`, `UInt64`, `Bool`, `Byte`, `Float32`, `Double`, `Decimal`, `String`, `Timestamp`, `Date`, `Guid`.

**Common mistake:** Using `"Integer"`, `"Long"`, `"Float"`, or `"DateTime"` as type names — these are not valid. Use `Int32`, `Int64`, `Float32`, and `Timestamp` respectively.

#### PartitionKeyEntry (entry in `partitionKey`)

| Field | JSON key | Type | Required | Notes |
|---|---|---|---|---|
| `column` | `column` | `string` | Yes | Name of the partition key column. Must match a column in `columns`. |
| `function` | `function` | `string` | No | Partition function to apply to the column value. See valid values below. |

Valid `function` values: `TruncateToDay`, `TruncateToHour`, `TruncateToMinute`, `TruncateToWeek`, `TruncateToMonth`, `TruncateToYear`. Omit the `function` field (or use `"None"`) to use the column value as-is for routing.

**Common mistake:** Using `"Hash"` as a partition function — this is not a valid schema-file `function` value. Partition hashing for storage routing (XxHash64) is applied internally by the storage engine when `partitionStorage = "Shared"` or `"Auto"`. You do not need to, and cannot, configure it via the schema file.

**Example — time-partitioned table (partition by day):**

```json
{
  "events": {
    "columns": {
      "id":         { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
      "ts":         { "type": "Timestamp" },
      "tenant_id":  { "type": "String" },
      "payload":    { "type": "String", "nullable": true }
    },
    "partitionKey": [
      { "column": "ts", "function": "TruncateToDay" }
    ],
    "clusterColumns": ["ts"],
    "policy": { "storageTemperature": "Auto" },
    "durability": { "walEnabled": true }
  }
}
```

**Example — tenant-partitioned table (string key, no function):**

```json
{
  "orders": {
    "columns": {
      "id":         { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
      "tenant_id":  { "type": "String" },
      "status":     { "type": "String" },
      "amount":     { "type": "Decimal" },
      "created_at": { "type": "Timestamp" }
    },
    "partitionKey": [
      { "column": "tenant_id" }
    ],
    "clusterColumns": ["created_at"],
    "policy": { "storageTemperature": "Auto" },
    "durability": { "walEnabled": true },
    "partitionLevelSecurity": true,
    "authMode": "jwt-claim"
  }
}
```

#### TablePolicyDto (value of `policy`)

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `storageTemperature` | `storageTemperature` | `string` | `"Auto"` | Storage temperature policy. Valid values: `"Auto"`, `"HotOnly"`, `"ColdPreferred"`. |

#### TableDurabilityDto (value of `durability`)

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `walEnabled` | `walEnabled` | `bool` | `null` (inherit) | Whether WAL is enabled for this table. Null = inherit database default. Allowed values: `true`, `false`, `null`. |
| `replicationFactor` | `replicationFactor` | `int` | `null` (inherit) | Replication factor. Note: changing this via schema apply is currently skipped by the apply engine (see `ApplyStatus.Skipped`). Allowed values: non-negative integer, or `null` (inherit database default). |

#### SchemaSettings (value of `settings`)

| Field | JSON key | Type | Notes |
|---|---|---|---|
| `durability` | `durability` | `SchemaSettingsDurability` | Database-level durability settings. |

#### SchemaSettingsDurability (value of `settings.durability`)

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `walEnabled` | `walEnabled` | `bool` | `null` (inherit) | Database-level WAL default. `true` maps to `DiskBacked` durability mode; `false` maps to `MemoryOnly`. Allowed values: `true`, `false`, `null`. |
| `replicationFactor` | `replicationFactor` | `int` | `null` (inherit) | Database-level replication factor. Informational in schema; not currently applied by the apply engine. Allowed values: non-negative integer, or `null` (inherit engine default). |

---

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: Inference-first prototype -> declarative baseline

1. Keep server `InferenceMode=On`.
2. Build and iterate with inferred table creation.
3. Export schema:
   - `dotnet aouda schema export --server http://localhost:5433 --database myapp --output aouda.schema.json`
4. Commit exported schema to git.
5. Switch production/shared environments to `InferenceMode=Off`.

Expected result:
- Teams keep prototyping speed early.
- Shared environments become controlled by reviewed schema intent.

### Scenario 2: Safe additive rollout

1. Add new table/column in `aouda.schema.json`.
2. Run `schema diff` and review plan in PR.
3. Apply without destructive flag.
4. Deploy app version using new schema.

Expected result:
- Additive changes apply with low risk.
- Existing binaries remain compatible during rollout window.

### Scenario 3: Expand -> deploy -> contract release

1. Keep old field/table in schema while adding new structure (expand).
2. Deploy application using new structure.
3. After old code is retired, remove legacy field/table.
4. First apply without destructive opt-in (expected skip), then approved apply with `--allow-destructive`.

Expected result:
- No accidental data-loss during mixed-version deployments.

### Scenario 5: Enable autoIncrement on an existing integer column

**Context:** You have a `customers` table where `id` was inserted manually. You want the server to manage auto-increment from now on without dropping and re-creating the column.

**Constraint:** Only integer types (`Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`) may have `autoIncrement: true`. The server enforces this; the Studio UI additionally hides the toggle for non-integer columns.

**Via schema file:**

1. In your `aouda.schema.json`, change the column from:
   ```json
   "id": { "type": "Int64", "primaryKey": 1 }
   ```
   to:
   ```json
   "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true }
   ```
2. Diff to verify the plan:
   ```bash
   dotnet aouda schema diff --server http://localhost:5433 --database commerce
   # Output: 1 column altered (UpdateColumnAutoIncrement: customers.id)
   ```
3. Apply (no `--allow-destructive` needed — this change is safe):
   ```bash
   dotnet aouda schema apply --server http://localhost:5433 --database commerce
   ```

**Via Studio UI:**

1. Open the table schema view for `customers`.
2. In the **Columns** table, click the `⋮` (actions menu) on the `id` row.
3. Click **Toggle AutoId**. The dialog shows the direction: "Manual → Auto".
4. Read the warning: "The counter will recover from the MAX existing value in this column on first insert."
5. Click **Apply**.

**Counter recovery behavior:**

The auto-increment counter does **not** start at 1. On first server-managed insert after enabling, `AutoIncrementService` reads the MAX existing value in the column and resumes from `MAX + 1`. This means existing manually-inserted IDs are never overwritten.

**Disabling autoIncrement:**

Set `autoIncrement: false` in the schema file and apply, or use the Studio toggle (direction will show "Auto → Manual"). After disabling, inserts must supply an explicit value for the column.

Expected result:
- `DiffSummary.ColumnsAltered === 1` in the apply response.
- Future inserts without an explicit `id` value use the server-managed counter.
- The `isAutoIncrement` badge appears on the column in Studio.

### Scenario 4: Branch-based schema experiment

1. Create branch in database.
2. Apply schema changes on branch only.
3. Run branch-scoped query/insert tests.
4. Generate merge plan and review conflicts.
5. Merge (or force merge if approved) and delete branch.

Expected result:
- Parent schema/data remains stable until merge decision.

---

## 2.13 Operations and observability

- Use `schema diff` as primary pre-apply control signal.
- Treat migration history as applied-state audit trail:
  - timestamp, source, hash, and change list.
- Prefer `dryRun=true` or CLI dry-run in higher-risk environments.
- For branch workflows:
  - monitor branch count and branch lifecycle cleanup,
  - verify branch deletion cleanup for catalog/tables/WAL branch paths.
- Key operational checks:
  - `InferenceMode` is set intentionally per environment,
  - destructive applies are gated by process, not ad-hoc CLI usage,
  - schema history is reviewed as part of release diagnostics.

---

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| Insert fails with "table does not exist... InferenceMode is Off" | Inference disabled on server | Create via schema apply or direct DDL endpoint |
| `schema apply` reports skipped operations | Destructive changes present without opt-in | Re-run only after approval with `--allow-destructive` |
| `schema validate` returns drift | Desired file and runtime catalog differ | Run `schema diff`, then apply or reconcile |
| CLI says no schema file found | discovery path mismatch | run from repo root or pass `--file` |
| Branch merge returns conflict | parent and branch changed overlapping schema | resolve plan, re-run merge, or use force only with review |
| New column reads appear misaligned in old datasets | stale build or regression around add-column fixes | verify P7 add-column backfill tests and runtime version |

---

## 2.15 Verification ledger

| Claim | Verification type | Evidence |
|---|---|---|
| Declarative diff/apply/export/history endpoints are shipped | Code + integration tests | `SchemaController.cs`, `SchemaControllerIntegrationTests.cs` |
| .NET CLI schema commands work for diff/apply/export/validate/history | Code + unit tests | `Program.cs`, `SchemaCommandHandlerTests.cs` |
| C# client wrappers exist for diff/apply/export/history | Code + unit tests | `ISchemaOperations.cs`, `SchemaOperations.cs`, `SchemaApiTests.cs` |
| Destructive guard defaults to opt-in behavior | Code | `SchemaApplyEngine.cs`, `SchemaCommandHandler.cs` |
| Add-column no-rewrite + alignment behavior is implemented | ADR + report + tests | ADR 0018, `BL025-Fix2-AddColumnColdBackfill-Report.md`, `ColdColumnBackfillTests.cs` |
| Branch schema lifecycle and COW sharing are implemented | Task reports + tests | F.2/F.3/F.4 reports, branch test suites |
| `UpdateColumnAutoIncrement` toggle is a first-class schema change | Code + tests | `AutoIncrementService.cs`, `SchemaDiffEngine.cs`, `SchemaDiffEngineTests.cs`, `AutoIncrementServiceTests.cs`, BL-126 |

---

## 2.16 Test coverage matrix

| Area | Tests | Coverage depth |
|---|---|---|
| Schema diff engine | `SchemaDiffEngineTests.cs` | change classification, summary, comparison behavior, `UpdateColumnAutoIncrement` detection |
| Schema apply engine | `SchemaApplyEngineTests.cs` | destructive handling, dry-run, execution outcomes |
| AutoIncrement toggle | `AutoIncrementServiceTests.cs` | counter invalidation on toggle, integer-type enforcement |
| Schema REST endpoints | `SchemaControllerIntegrationTests.cs` | 200/400/404 paths, apply/history behavior |
| C# schema API client | `SchemaApiTests.cs` | endpoint path mapping and response contracts |
| CLI schema command handling | `SchemaCommandHandlerTests.cs` | command behavior, exit semantics, output modes |
| Add-column cold backfill | `ColdColumnBackfillTests.cs` | aligned page creation, idempotence, recovery |
| Branch lifecycle | `BranchCatalogTests.cs`, `BranchMergeTests.cs`, `BranchSegmentSharingTests.cs` | branch create/diff/merge/isolation/COW/read-through |

---

## 2.17 Testing gaps and proposed tests

- Add explicit integration tests for schema apply + branch merge interaction in one workflow.
- Add end-to-end tests for auth metadata fields inside declarative schema apply/diff/export paths.
- Add regression test ensuring .NET CLI seed command remains intentionally stubbed until endpoint wiring lands (to avoid silent behavior changes).
- Add performance tests around large schema plans and large history pages.

---

## 2.18 Known gaps and undone work

- `InferenceMode: Extend` is still deferred.
- No HTTP `/schema/validate` endpoint (validate is currently a CLI composition over diff).
- .NET CLI `schema seed` remains stubbed while server `schema/seed` endpoint exists.
- C# high-level schema interface does not yet include seed and branch convenience wrappers.
- Some phase planning documents still contain stale "in progress" language despite completed reports; this document follows code/tests and completion reports as authority.
- WAL record for `UpdateColumnAutoIncrement` is not yet written (deferred from BL-126); the toggle is durable through the catalog but not replayed from WAL on recovery.
- IDENTITY seed configuration (starting value for the auto-increment counter) is not yet exposed; the counter always starts from `MAX(column) + 1` on first use.
- The TypeScript `SchemaChange.type` field is `string`, not a typed union; a union type for known change types is a separate polish task.

---

## 2.19 References

### ADRs

- `docs/decisions/0018-alter-add-column-no-backfill.md`
- `docs/decisions/0019-declarative-schema-management.md`
- `docs/decisions/0025-adra-auth-db-resolved-authorization.md`

### Task/report evidence

- `docs/tasks/P4/P4-EpicA-Task3-SchemaManagementApi-Report.md`
- `docs/tasks/P7/BL025-Fix2-AddColumnColdBackfill-Report.md`
- `docs/tasks/P8/P8-DeclarativeSchemaManagement-Tasks.md`
- `docs/tasks/P8/P8-EpicC-Task4-RestApiEndpoints-Report.md`
- `docs/tasks/P8/P8-EpicF-Task2-CatalogLevelBranchIsolation-Report.md`
- `docs/tasks/P8/P8-EpicF-Task3-BranchDiffAndMerge-Report.md`
- `docs/tasks/P8/P8-EpicF-Task4-CopyOnWriteSegmentSharing-Report.md`
- `docs/tasks/P14/P14-TaskC1-TableSchemaExtension.md`

### Core implementation and tests

- `src/Aouda.Server/Controllers/SchemaController.cs`
- `src/Aouda.Server/Controllers/TablesController.cs`
- `src/Aouda.Server/Controllers/BranchController.cs`
- `src/Aouda.Cli/Program.cs`
- `src/Aouda.Cli/Commands/SchemaCommandHandler.cs`
- `src/Aouda.Client/SchemaOperations.cs`
- `src/Aouda.Engine.Schema/Diff/SchemaDiffEngine.cs`
- `src/Aouda.Engine.Schema/Apply/SchemaApplyEngine.cs`
- `src/Aouda.Engine.Schema/Export/SchemaExporter.cs`
- `tests/Aouda.Server.Tests/SchemaControllerIntegrationTests.cs`
- `tests/Aouda.Cli.Tests/SchemaCommandHandlerTests.cs`
- `tests/Aouda.Client.Tests/Schema/SchemaApiTests.cs`
- `tests/Aouda.Engine.Storage.Tests/ColdColumnBackfillTests.cs`

---

## 2.20 What is missing from this document? (meta completeness)

- Full per-field schema JSON reference examples for every advanced table option are still split across ADR/task docs; a dedicated reference appendix could centralize these.
- TypeScript client library parity details live cross-repo and should be mirrored here once a unified capability table across repos is maintained.
- A dedicated "schema + auth lifecycle" deep-dive doc may be warranted as P14+ authorization workflows expand.

