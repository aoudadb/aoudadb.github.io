---
title: "Schema Lifecycle"
nav_order: 2
parent: "Guides"
---

# Aouda Functionality: Schema Lifecycle and Evolution

Document status: Approved baseline  
Primary owner: Aouda maintainers  
Last updated: 2026-03-31

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

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `Aouda:Schema:InferenceMode` | `On` | Backward-compatible schema-on-write behavior enabled |
| `AOUDA_SCHEMA_INFERENCE_MODE` | unset | No override unless explicitly set |
| Apply option `allowDestructive` | `false` | Drop operations are skipped unless explicitly allowed |
| Apply option `dryRun` | `false` | Apply executes unless dry-run requested |
| CLI `schema history` pagination | `limit=50`, `offset=0` | Newest-first history default view |
| CLI output mode | human-readable | Use `--json` when machine parsing is needed |

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
| `appsettings` | `Aouda:Schema:InferenceMode` | `On` | Controls inference-only behavior (`Off` or `On`) |
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "email": { "type": "String" },
        "name": { "type": "String", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "status": { "type": "String" },
        "total_amount": { "type": "Decimal" },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "email": { "type": "String" },
        "name": { "type": "String", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "status": { "type": "String" },
        "total_amount": { "type": "Decimal" },
        "priority": { "type": "Int32", "nullable": true },
        "fulfilled_at": { "type": "Timestamp", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "order_id": { "type": "Int64", "references": "orders.id" },
        "provider": { "type": "String" },
        "status": { "type": "String" },
        "amount": { "type": "Decimal" },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "email": { "type": "String" },
        "name": { "type": "String", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "total_amount": { "type": "Decimal" },
        "priority": { "type": "Int32", "nullable": true },
        "fulfilled_at": { "type": "Timestamp", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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
        "tenant_id": { "type": "String", "partitionFunction": "Hash" },
        "order_id": { "type": "Int64", "references": "orders.id" },
        "provider": { "type": "String" },
        "status": { "type": "String" },
        "amount": { "type": "Decimal" },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id", "function": "Hash" }
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

---

## 2.16 Test coverage matrix

| Area | Tests | Coverage depth |
|---|---|---|
| Schema diff engine | `SchemaDiffEngineTests.cs` | change classification, summary, comparison behavior |
| Schema apply engine | `SchemaApplyEngineTests.cs` | destructive handling, dry-run, execution outcomes |
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

