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
- **P37:** [Named queries](named-queries.md) (`namedQueries` / `namedMutations` in the schema file), [Insert-time transforms](insert-transforms.md) (`derived`, `checks`, `transforms`, `dataPlaneAccess`), [Access-surface diff](access-surface.md) (`aouda schema diff --access`).

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

- Start fast with HTTP DDL, the C# client's `AutoCreateSchema`, or `InferenceMode: Extend` (an insert creates a missing table).
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

- Server `InferenceMode` defaults to `On`, which answers `404` to an insert into a missing table. Only `Extend` creates a table on
  insert.
- A table that schema apply created refuses HTTP DDL in every mode (**BL-1177, next train**). See the table below.
- The C# client reconciles a typed model on its first write by default and **drops the columns the model omits**. See the
  warning below.
- Runtime schema truth is always the server catalog, not a file.
- Declarative safety still defaults to non-destructive:
  - API apply defaults to `allowDestructive = false`.
  - CLI apply defaults to no `--allow-destructive`.

| Setting / behavior | Default | Allowed values | Practical impact |
|---|---|---|---|
| `Aouda:Schema:InferenceMode` | `On` | `Off`, `On`, `Extend` | What an insert into a missing table does: `Off` and `On` answer `404`, `Extend` creates the table. It does not decide the declarative DDL lock |
| `AOUDA_SCHEMA_INFERENCE_MODE` | unset | `Off`, `On`, `Extend`; or unset (no override) | No override unless explicitly set |
| Apply option `allowDestructive` | `false` | `true`, `false` | Drop operations are skipped unless explicitly allowed |
| Apply option `dryRun` | `false` | `true`, `false` | Apply executes unless dry-run requested |
| CLI `schema history` pagination | `limit=50`, `offset=0` | Any non-negative integer for `limit` and `offset` | Newest-first history default view |
| CLI output mode | human-readable | `human-readable` (default), `json` (via `--json` flag) | Use `--json` when machine parsing is needed |
| C# `AutoReconcileSchema` / `ReconcilePolicy` | `true` / `Unsafe` | `true`, `false` / `Safe`, `Unsafe` | The first typed write adds missing columns **and drops the columns the model omits**. Set `false` for declarative tables |

### What `InferenceMode` decides, and what it does not

| Mode | Insert into a missing table | HTTP DDL on a table schema apply created | HTTP DDL on any other table |
|---|---|---|---|
| `Off` | `404`; the message names `InferenceMode is Off` | refused, `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN` (**BL-1177, next train**) | allowed |
| `On` (default) | `404` | refused, `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN` (**BL-1177, next train**) | allowed |
| `Extend` | the table is inferred from the rows and created | refused, `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN` | allowed |

- **`InferenceMode` decides only what an insert into a missing table does.** `On` does not create a missing table; only `Extend`
  does. `Off` and `On` differ only in the `404`'s message.
- **The declarative lock belongs to the table, not the mode.** A table that schema apply *created* refuses HTTP DDL in every mode:
  drop or rename the table, its options, add, alter, reorder or drop a column, and a policy change to `storageTemperature` or
  `retention`. Change these through `schema apply`. The residency knobs (`memoryRowCap`, `targetMemoryBytes`, `memoryFilter`,
  `hotOnlyBackstop`) have no place in the file, so `PUT …/policy` that restates the current temperature and changes only them is
  still served. (**BL-1177, next train**: before this, only `Extend` refused. In `On` and `Off`, HTTP DDL stayed open on a table the
  file had just applied, including `DELETE` of a column.) `Off` stops inference. It was never the lock.
- A table that HTTP DDL created stays open to HTTP DDL in every mode, even after an apply later extends it. Only a table the apply
  created is locked.
- The lock is logged with the table's create, so a replica, the primary it is promoted to, and a point-in-time restore hold it too
  (**BL-1177, next train**; before, all three held the table open, even in `Extend`).

> **⚠️ The C# client's default reconcile drops every column your model does not declare.**
>
> `Aouda.Client` defaults to `AutoReconcileSchema = true` with `ReconcilePolicy = Unsafe`. Before the first typed write to a table, the
> client compares the table with the model. It adds the columns the model has and the table lacks, and it **drops every column the
> table has and the model does not declare**. That includes a derived column (`SearchText`), a server-stamped column, and any column
> you left off the row type on purpose.
>
> **Set `AutoReconcileSchema = false` on every client that writes to tables from `aouda.schema.json`.** From the next train
> (**BL-1177**), the server refuses that drop on a schema-applied table, so a default client fails its first typed write with
> `AoudaSchemaException` and the column survives. On 0.7.0 and earlier, in `On` or `Off`, the drop succeeded and the write reported
> success. That is how a green apply lost its derived columns at the first service start.
>
> **Bulk load does not reconcile.** The two write paths therefore disagree. On a table HTTP DDL created, where the drop is still
> allowed, a bulk-loaded table keeps a column that a typed insert of the same model removes. `ReconcilePolicy = Safe` only adds
> columns and never drops one. It is still no fix for a declarative table: an add is refused there too, so a class with a property
> the table lacks still makes the first write throw. Turn reconcile off.

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
- `InferenceMode: Extend`: an insert into a missing table infers and creates it (BL-022).
- The declarative DDL lock: a table schema apply created refuses HTTP DDL in every `InferenceMode` (**BL-1177, next train**; before, only in `Extend`).
- **`autoIncrement` toggle on existing columns** — the `UpdateColumnAutoIncrement` change type enables toggling `autoIncrement` on or off for any existing integer-type column via the declarative schema apply path or the Studio "Toggle AutoId" action. The counter recovers from the column's MAX existing value on first insert after enabling. Available via `POST /schema/apply`, Studio UI, and (Studio-internal) schema export→patch→apply pattern. Tracked in BL-126.
- **Identity-insert (request-scoped / job-scoped)** — supply explicit IDs on an `autoIncrement` column **without** flipping the schema flag. Ordinary insert: `identityInsert: true` on `POST …/rows` (BL-130). Large ingest: `options.identityInsert: true` on bulk-load `:begin` (BL-131). Complementary to BL-126 (toggle = permanent Auto↔Manual; identity-insert = one request/job). See [Getting Started](../getting-started/index.md), [HTTP API](../reference/http-api.md), [Bulk Load](../guides/bulk-load.md).

### Planned / proposed

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
| Insert-time table creation (`Extend`) | Yes | No | No | `SchemaOptions.cs`, `TablesController.cs` | Default is `On`, which, like `Off`, answers `404` to an insert into a missing table |
| Declarative DDL lock | Yes | No | No | `TablesController.RejectIfDeclarativeSchemaDdlForbidden` | Every mode (**BL-1177, next train**); only tables apply created |
| Imperative table and column lifecycle APIs | Yes | No | No | `TablesController.cs`, P4 report | Mature and well-tested |
| Declarative schema diff/apply/export/history APIs | Yes | No | No | `SchemaController.cs`, P8 C.4 report | Includes markdown diff format |
| Destructive-change safety gates | Yes | No | No | `SchemaApplyEngine.cs`, `SchemaCommandHandler.cs` | Explicit opt-in required |
| CLI declarative workflow (.NET) | Yes | No | No | `Program.cs`, CLI tests | validate is diff-based check |
| C# client declarative wrappers | Yes | No | No | `ISchemaOperations.cs`, `SchemaOperations.cs` | Diff/apply/export/history available |
| Add-column no-rewrite semantics | Yes | No | No | ADR 0018, P7 fix2 report | Query-time defaults and alignment |
| Cold aligned backfill on add-column | Yes | No | No | P7 fix2 report, storage tests | Prevents cross-column alignment bugs |
| autoIncrement toggle on existing columns (`UpdateColumnAutoIncrement`) | Yes | No | No | BL-126 / P36, `SchemaDiffEngine.cs`, `PATCH …/columns/{c}` | Integer columns only; counter resets from MAX on first insert after enable |
| Column type change (Tier 1 widen / Tier 2 validated) | Yes | No | No | P36 S03–S08, `TypePromotionMatrix`, `ColumnRewrite` jobs | Tier 1 instant metadata + coercion; Tier 2 validate-then-flip + background rewrite |
| Column nullable / rename / references | Yes | No | No | P36 S08–S10, S12 | Imperative PATCH + declarative apply |
| Column default + description | Yes | No | No | P36 S11 | Declarative + catalog; default does not rewrite existing pages |
| Primary key membership change | Yes | No | No | P36 S15 | Uniqueness scan + PK index rebuild; no `col_*.seg` rewrite |
| Durable catalog DDL (WAL envelope, replica-consumed, PITR-replayed) | Yes | No | No | P36 S01–S02, BL-186 S06 | Generic `CatalogDdl` WAL tag; crash recovery still ignores it (catalog comes from the checkpoint) but point-in-time recovery replays it — see [Backup and restore](backup.md#24-availability-status) |
| Pending jobs HTTP (`GET …/jobs`) | Yes | No | No | P36 S12 | Projects `ColumnRewrite` / `PkIndexRebuild` |
| Studio column alter UI | Yes | No | No | P36 S14 | Alter / PK / reorder / default-description dialogs |
| Identity-insert (ordinary insert + bulk-load) | Yes | No | No | BL-130, BL-131 — see HTTP API / Bulk Load / Getting Started | Request/job-scoped; does not flip schema `autoIncrement` |
| Server seed endpoint | Yes | No | No | `SchemaController.cs` | Endpoint exists |
| .NET CLI seed command | No | Yes | No | `Program.cs` + `RunSeedStub` | Stubbed, intentionally not wired |
| Branch create/list/get/delete/diff/merge APIs | Yes | No | No | `BranchController.cs`, F.2/F.3 reports | Includes conflict handling |
| Copy-on-write branch data sharing | Yes | No | No | F.4 report, branch tests | Branch writes isolated from parent |
| `partitionKey` / `clusterColumns` / `partitionFunction` evolution | No | No | Yes | P36 overview §12 → BACKLOG | Cross-partition / full re-sort — post-P36 |

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

> **A declarative apply drops by omission.** The diff is computed against the *whole* catalog, so any
> column the table currently has and your `aouda.schema.json` does not list is planned as a
> **`DropColumn`** — and executed when `allowDestructive: true`. Nobody has to ask for a drop: deleting
> a field from the schema file, renaming it in a way the differ does not recognise as a rename, or
> applying an **older** copy of the file (a rollback, a stale artifact baked into a deploy image, a
> second service applying its own version) is enough. The same holds for whole tables.
>
> This matters most in pipelines that hard-set `allowDestructive: true` for an environment. Two
> habits make it safe:
>
> - Run `POST …/schema/diff` (or `dryRun: true`) first and read the plan. `DropColumn` / `DropTable`
>   entries are listed explicitly.
> - Apply exactly one version of a file per database. If two things apply schemas to the same
>   database, an older one will silently undo the newer one's columns.
>
> A dropped column's data is not recoverable from the catalog: re-adding a column of the same name
> creates a **new** column (new `id`, see [`GET …/tables/{name}/schema`](../reference/http-api.md)),
> backfilled with its default for existing rows.

### Walk-through C: Add-column on existing cold segments

1. Table column add request enters `TablesController`.
2. Catalog adds column metadata.
3. Engine triggers cold column backfill for aligned default pages where required.
4. Query paths preserve row alignment and return defaults for historical rows.
5. Existing rows remain immutable (no full historical rewrite).

### Walk-through D: Branch schema lifecycle

1. Create branch from parent catalog snapshot.
2. Apply schema changes in branch scope only.
3. Generate a three-way merge plan from the branch's base snapshot (`base-catalog.json`, written when the branch is created). (**BL-980, 0.4.0**) A branch without one — made by a build before F.3 — is refused at merge and at delete, before anything is deleted; up to 0.3.x a merge fell back to a two-way plan.
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
| startup config | `Aouda:Schema:InferenceMode` | `On` | What an insert into a missing table does (`Off`, `On`, `Extend`). The declarative DDL lock does not depend on it (**BL-1177, next train**) |
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

```http
PATCH /api/databases/myapp/tables/orders/columns/amount
Content-Type: application/json

{ "database": "myapp", "type": "Int64", "nullable": false }
```

```http
PUT /api/databases/myapp/tables/orders/columns:order
Content-Type: application/json

{ "database": "myapp", "columns": ["id", "amount", "created_at"] }
```

```http
GET /api/databases/myapp/jobs
GET /api/databases/myapp/jobs/{jobId}
```

C# / TypeScript clients expose `AlterColumnAsync` / `alterColumn`, `ReorderColumnsAsync` / `reorderColumns`, and pending-jobs list/get (`ISchemaOperations` / `client.jobs`).

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
      "durability": { "level": "strict" },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "orders": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "status": { "type": "String" },
        "total_amount": { "type": "Decimal", "precision": 18, "scale": 2 },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "level": "strict" },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
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
      "durability": { "level": "strict" },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "orders": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "status": { "type": "String" },
        "total_amount": { "type": "Decimal", "precision": 18, "scale": 2 },
        "priority": { "type": "Int32", "nullable": true },
        "fulfilled_at": { "type": "Timestamp", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "level": "strict" },
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
        "amount": { "type": "Decimal", "precision": 18, "scale": 2 },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "level": "strict" },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
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
      "durability": { "level": "strict" },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
    },
    "orders": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "tenant_id": { "type": "String" },
        "customer_id": { "type": "Int64", "references": "customers.id" },
        "total_amount": { "type": "Decimal", "precision": 18, "scale": 2 },
        "priority": { "type": "Int32", "nullable": true },
        "fulfilled_at": { "type": "Timestamp", "nullable": true },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "Auto" },
      "durability": { "level": "strict" },
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
        "amount": { "type": "Decimal", "precision": 18, "scale": 2 },
        "created_at": { "type": "Timestamp" }
      },
      "partitionKey": [
        { "column": "tenant_id" }
      ],
      "clusterColumns": ["created_at"],
      "policy": { "storageTemperature": "ColdPreferred" },
      "durability": { "level": "strict" },
      "partitionLevelSecurity": false,
      "authMode": "jwt-claim"
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
| HTTP | `PATCH …/tables/{t}/columns/{c}` (ALTER COLUMN) | Available | P36 S12 — type/nullable/autoIncrement/references/rename |
| HTTP | `PUT …/tables/{t}/columns:order` | Available | P36 S12 |
| HTTP | `GET …/jobs` (+ `/{id}`) | Available | P36 S12 — `ColumnRewrite`, `PkIndexRebuild` |
| C# SDK | `DiffAsync/ApplyAsync/ExportAsync/HistoryAsync` | Available | `SchemaOperations.cs` + client tests |
| C# SDK | `AlterColumnAsync` / `ReorderColumnsAsync` / pending jobs | Available | P36 S13 |
| TS SDK | `alterColumn` / `reorderColumns` / `client.jobs` / typed `SchemaChangeType` | Available | P36 S13 |
| .NET CLI | diff/apply/export/validate/history | Available | `Program.cs` + CLI tests |
| HTTP | branch create/list/get/delete/diff/merge/query/insert | Available | `BranchController.cs` |
| Studio | Schema view alter / PK / reorder / metadata dialogs | Available | P36 S14 |

### B) Missing API matrix

| Missing / partial surface | Current state | Practical workaround |
|---|---|---|
| C# SDK seed wrapper | Missing on `ISchemaOperations` | call HTTP directly or server tooling path |
| C# SDK branch wrapper | Missing on `ISchemaOperations` | call branch HTTP endpoints directly |
| HTTP validate endpoint | Missing | CLI `schema validate` performs diff and exits by drift |
| .NET CLI `schema seed` | Stubbed | use seed endpoint via HTTP until CLI command is wired |
| PATCH fields for default/description/PK | Not on AlterColumnRequest | Declarative apply or Studio metadata/PK dialogs |

### C) Aouda.Schema.Contract NuGet facade

`Aouda.Schema.Contract` is the thin NuGet package external users install to work with schema types in C#. It does not contain the full engine — it recompiles only the schema model and result types from `Aouda.Engine.Schema` under the same namespaces, so you get the exact same types without a dependency on the server-side engine.

When you add `Aouda.Schema.Contract` to your project, you get:

| Type | Namespace | Purpose |
|---|---|---|
| `SchemaDocument` | `Aouda.Engine.Schema.Models` | Root type for `aouda.schema.json`: `$schema`, `database`, `tables`, `settings`, `extends` |
| `TableDefinition` | `Aouda.Engine.Schema.Models` | Per-table structure: `columns`, `partitionKey`, `clusterColumns`, `policy`, `durability`, `partitionLevelSecurity`, `authMode`, `permissionDimension`, `permissionColumn`, `rlsResolverName` |
| `ColumnDefinition` | `Aouda.Engine.Schema.Models` | Per-column: `type`, `primaryKey`, `autoIncrement`, `nullable`, `references`, `default`, `description` |
| `PartitionKeyEntry` | `Aouda.Engine.Schema.Models` | Partition key entry: `column`, `function` |
| `TablePolicyDto` | `Aouda.Engine.Schema.Models` | Table policy: `storageTemperature` |
| `TableDurabilityDto` | `Aouda.Engine.Schema.Models` | Table durability: `level`, `replicationFactor` (**Lead S26, 0.6.0**: `level` replaces `walEnabled`) |
| `SchemaSettings` | `Aouda.Engine.Schema.Models` | Database-level settings container |
| `SchemaSettingsDurability` | `Aouda.Engine.Schema.Models` | Database-level durability: `replicationFactor` (**Lead S26, 0.6.0**: no level — a database's level is set where the database is created) |
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
| `UpdateDurability` | No | The `level` (or `replicationFactor`) in the table's `durability` changed (**Lead S26, 0.6.0**: `level` replaces `walEnabled`). A change to or from `memory` is refused — a table's storage is fixed when it is made; `strict` ↔ `unlogged` applies. |
| `UpdatePartitionLevelSecurity` | No | The `partitionLevelSecurity` flag on the table changed. |
| `UpdateAuthorizationOptions` | No | One or more of `authMode`, `permissionDimension`, `permissionColumn`, `rlsResolverName` or `plsClaimBinding` changed. |
| `UpdateSettings` | No | The database-level `settings.durability` (its `replicationFactor`) changed. |
| `UpdateColumnAutoIncrement` | No | The `autoIncrement` flag on an existing integer column changed. Counted in `DiffSummary.ColumnsAltered`. |
| `UpdateColumnType` | No | Logical type change (Tier 1 instant widen or Tier 2 validated conversion). May schedule a background `ColumnRewrite` job. |
| `UpdateColumnNullable` | No | Nullability flip; nullable→non-null validates that no nulls exist. |
| `RenameColumn` | No | Rename by `ColumnId` — metadata only, no segment I/O. |
| `ReorderColumns` | No | Catalog display order change — metadata only. |
| `UpdateColumnReferences` | No | FK target (`table.column`) set/clear. |
| `UpdateColumnDefault` | No | Configured default literal (metadata; does not rewrite existing pages). |
| `UpdateColumnDescription` | No | Column description metadata. |
| `UpdateTablePrimaryKey` | No | PK membership change; uniqueness scan + PK index rebuild. |
| `UpdateTableCulture` | No | Table culture for locale-aware parsing. |
| `DropColumn` | **Yes** | A column exists in actual but not in desired. Skipped unless `AllowDestructive = true`. |
| `DropTable` | **Yes** | A table exists in actual but not in desired. Skipped unless `AllowDestructive = true`. |

#### SchemaDiffResult.Warnings — unsupported modifications

The diff engine produces `Changes` for operations it can execute and `Warnings` for operations it detects but **cannot** execute. Warnings are returned alongside changes and do not become apply entries.

Operations that still produce warnings (not changes) in v1:

| Changed property | Warning message pattern | Action required |
|---|---|---|
| Table `partitionKey` | `"Partition key change on table '...' is not supported."` | Drop table, re-create (or wait for post-P36 migration). |
| Table `clusterColumns` | `"Cluster columns change on table '...' is not supported."` | Drop table, re-create. |
| Column type involving Vector / MdVector | Tier 3 blocked | Not supported in v1. |
| Type change on a partition-key column | Tier 3 blocked | Would reroute rows across partitions. |

> **Note (P36):** Column `type`, `nullable`, `primaryKey`, `references`, rename, default, and description are first-class applyable changes. Imperative parity: `PATCH /api/databases/{db}/tables/{t}/columns/{c}` (type/nullable/autoIncrement/references/rename), `PUT …/columns:order`, and declarative apply for default/description/PK/culture. Non-integer `autoIncrement: true` still warns.

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
| `ColumnsAltered` | Count of column-level alteration types (`UpdateColumnAutoIncrement`, type/nullable/references/default/description, rename, reorder, PK, …). |
| `PoliciesUpdated` | Count of `UpdatePolicy` changes |
| `DurabilitiesUpdated` | Count of `UpdateDurability` changes |
| `OptionsUpdated` | Count of `UpdatePartitionLevelSecurity` + `UpdateAuthorizationOptions` changes |
| `SettingsUpdated` | Count of `UpdateSettings` changes |

#### MigrationSource

`MigrationSource` is stored in each `MigrationHistoryEntry` and identifies what triggered the apply. (**BL-980, 0.4.0**) These four are the only values: `StartupApply` is gone, and a migration history naming it — or any other unknown source, or a number — is refused when it is read.

| Value | Meaning |
|---|---|
| `ApiApply` | Schema apply via REST API (`POST /schema/apply`). Primary source under the current model. |
| `ManualDdl` | Change applied directly to the catalog outside of schema apply (e.g. via Studio or direct DDL endpoint). |
| `Inference` | Change applied by inference (auto-create on first insert, `InferenceMode = Extend`). |
| `BranchMerge` | Change applied by merging a branch into the parent catalog. |

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
| `durability` | `durability` | `TableDurabilityDto` | None | Durability level (**Lead S26, 0.6.0**) and replication settings for this table. |
| `partitionLevelSecurity` | `partitionLevelSecurity` | `bool` | `false` | Enable partition-level security (PLS) for this table. Only valid on partitioned tables. Allowed values: `true`, `false`. |
| `authMode` | `authMode` | `string` | `"jwt-claim"` | Authorization mode. Valid values: `"jwt-claim"`, `"auth-db-pls"`, `"auth-db-rls"`. `auth-db-pls` implies partition-level security even when `partitionLevelSecurity` is omitted, and requires `permissionDimension` and `permissionColumn`; it does not require a partition key (**BL-1176, 0.7.0** — up to 0.6.0 schema apply required one). |
| `permissionDimension` | `permissionDimension` | `string` | None | The grant namespace for `"auth-db-pls"`: an opaque entitlement name in the auth database (for example `fx_source`). Partition-grant `dimension` must match this string **byte-for-byte** (case-sensitive). It **selects no column** — `permissionColumn` does (**BL-1176, 0.7.0**). See [Data Authorization §19.4](../auth/authorization.md#194-mode-2-auth-db-pls-enhanced-pls) and [§19.8](../auth/authorization.md#198-admin-api-partition-grants). |
| `permissionColumn` | `permissionColumn` | `string` | None | (**BL-1176, 0.7.0**) The column the grant keys of `permissionDimension` are compared with. **Required** with `"auth-db-pls"`, and must name a column of the table exactly; refused with any other `authMode`. Never inferred: a dimension spelled like a column does not select it, and neither does partition-key order. The column cannot be dropped while it is declared; a rename carries it. |
| `rlsResolverName` | `rlsResolverName` | `string` | None | RLS resolver name. Used with `"auth-db-rls"` mode. The resolver itself is created via the admin API, not schema apply. |
| `plsClaimBinding` | `plsClaimBinding` | `string` | `claim:tenant_id` | jwt-claim PLS source. `"subject"` or `"claim:<name>"`. Omit keeps `tenant_id`. |
| `culture` | `culture` | `string` | None | IETF culture tag for locale-aware parsing (e.g. `"en-US"`). Null/omit = ISO defaults. |

#### ColumnDefinition (entry in `columns`)

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `type` | `type` | `string` | **Required** | Column data type. See valid values below. May be changed in place (P36): Tier 1 widens instantly; Tier 2 validates then rewrites. |
| `primaryKey` | `primaryKey` | `int` | None | Ordinal position in composite primary key (1-based). Omit if not a PK column. Membership is changeable via apply. |
| `autoIncrement` | `autoIncrement` | `bool` | `false` | Auto-increment identity column. Only valid on integer columns. Allowed values: `true`, `false`. On ordinary insert, `0` or an absent cell (the column left out of the row) auto-generates (**Lead S12, 0.6.0**; it was `400 Missing required column`, BL-429); a named-mutation `values` template may leave it out too, but a bound parameter left out of a call is not a request — see [Named queries](named-queries.md#batch-insert-batchparam) and [HTTP API insert](../reference/http-api.md#post-apidatabasesdbtablesnamerows). |
| `nullable` | `nullable` | `bool` | `false` | Whether the column accepts null values. Allowed values: `true`, `false`. |
| `references` | `references` | `string` | None | Foreign key reference in `"table.column"` format. |
| ~~`encoder`~~ | — | — | — | Removed (**BL-768, 0.3.0**): it named an encoder preference that changed nothing once columns chose an encoding per vector. A schema file that still carries it applies; the key is ignored, as any unknown key is. |
| `default` | `default` | `string` | None | Invariant string literal default for the column type. Does not rewrite already-written pages when changed. |
| `description` | `description` | `string` | None | Human-readable column description (metadata only). |
| `derived` | `derived` | object | None | Write-time compute: a `ScalarExprNode` **or** `{ "identity": "subject" }` (P43). Identity columns may be PK / partition key / unique. They cannot be named-mutation `values` / `set` targets. User JWT omit stamps; user JWT supply → `TRANSFORM_DERIVED_READONLY`; service omit → `IDENTITY_STAMP_REQUIRED`. |
| `precision` | `precision` | `int` | None | With `scale`, on `"type": "Decimal"` only: declares `Decimal(p,s)`, stored as a scaled 64-bit integer (1–18). See below (**ColumnarCore S13, 0.2.0**). (**LoadSpeed S13, 0.4.0**) Required on every `Decimal` column. |
| `scale` | `scale` | `int` | None | Digits after the decimal point of a `Decimal(p,s)` column (0–`precision`). |

Valid `type` values: `Int32`, `Int64`, `Int16`, `UInt16`, `UInt32`, `UInt64`, `Bool`, `Byte`, `Float32`, `Double`, `Decimal`, `String`, `Timestamp`, `Date`, `Guid`.

#### `Decimal(p,s)`: a decimal stored as a scaled integer (**ColumnarCore S13, 0.2.0**)

A `Decimal` column declares `precision` (total digits, 1–18) and `scale` (digits after the point, 0–`precision`):

```json
"Price": { "type": "Decimal", "precision": 18, "scale": 2 }
```

A declared decimal is stored, logged, compared, aggregated and encoded as a **64-bit integer scaled by 10^scale**
(`123.45` is stored as `12345`) — as ClickHouse's and DuckDB's `Decimal(18,2)` are. It is 8 bytes instead of 16, its
pages encode like an `Int64`, and filters, sorts, keys, `min` / `max` / `sum` run as integer operations.

**`Decimal(p,s)` is the only decimal type** (**LoadSpeed S13, 0.4.0; breaking**). Up to 0.3.x a `Decimal` column
could leave out `precision` and `scale` and was then a 128-bit `System.Decimal` with any scale per value; that type is
retired:

- `"type": "Decimal"` without `precision` and `scale` — in a schema document, `POST …/tables` or
  `POST …/tables/{t}/columns` — is refused with `400`: *A Decimal column declares its precision and scale (Decimal(p,s),
  1 ≤ p ≤ 18, 0 ≤ s ≤ p); the undeclared 128-bit Decimal is retired.* A precision above 18 is refused: *Decimal precision
  above 18 is not supported (got N).* A value that needs more than 18 digits belongs in a `Double` or a `String` column.
- Where a type is named by a string alone, with no `precision` / `scale` beside it — a materialized query's computed
  output `type` and `cast(x, …)`'s target type — spell it `"Decimal(p,s)"`, e.g. `"Decimal(18,6)"`. Plain `"Decimal"`
  there is refused the same way.
- A C# `decimal` property declares its column with `[AoudaDecimal(p, s)]` (namespace `Aouda.Abstractions.Attributes`),
  e.g. `[AoudaDecimal(18, 6)] public decimal Price { get; set; }`. Without it, `CreateTableAsync<T>()` and the embedded
  engine refuse the type with a message naming the property. A table created implicitly from its first inserted row no
  longer infers a column from a C# `decimal` value: create the table with a `Decimal(p,s)` column first. (A JSON number
  with a fraction already inferred `Double` there.)
- A data directory whose catalog names a column of the old type (type 13), or that holds a segment, WAL record or cold
  page of it, is refused when the database opens, naming the column: *… has type 13, the undeclared 128-bit Decimal
  retired by LoadSpeed S13; this build has no reader for it … Export the data with the build that wrote it.* There is no
  migration: export with the old build, declare the column `Decimal(p,s)`, and load it into a new database.

| | Declared `Decimal(p,s)` |
|---|---|
| Writing `10` | means `10.00` (every value is its decimal value, whatever JSON or frame kind carries it) |
| More decimal places than `scale` | refused (`400`), except trailing zeros: `1.50` into scale 1 is `1.5` |
| More than `p − s` integer digits | refused (`400`) |
| Derived columns / computed outputs | computed as decimals, then rounded half away from zero to the scale |
| Reading | a decimal with exactly `scale` places (`10.50`, not `10.5`); type reported `Decimal` with `precision` / `scale` |
| Filters | exact: `> 10.555` on scale 2 is `> 10.55`, `= 10.555` matches nothing |
| `sum`, `min`, `max`, `first`, `last` | `Decimal(18,s)`, exact; a sum of 18 digits or more (an absolute value of 10^18 or more, scaled) is an error — *A Decimal sum does not fit Decimal(18,s).* — never a wrap, the same in a query and a materialized query (**LoadSpeed S13, 0.4.0**: a query's sum was bounded by `Int64` instead) |
| `avg` | `Double` (the sum ÷ 10^scale ÷ count) |

A column cannot be changed to or from `Decimal(p,s)`, nor to another precision or scale, in place: add a new column and
copy. A `Decimal(p,s)` column cannot be a partition key. Schema export writes the declaration back, so an exported
schema diffs to nothing.

**Expressions over decimals are exact** (**LoadSpeed S13, 0.4.0**) — in a derived column, a materialized query's
computed output, a `SET` expression and a `selectExpr`:

| Expression | Result |
|---|---|
| `a + b`, `a - b` | at the larger of the two scales |
| `a * b` | at the sum of the scales; above 18 places, rounded half away from zero to 18 |
| `a / b` | at scale max(6, scale of `a`, scale of `b`), rounded half away from zero |
| A fractional literal | keeps the scale it is written with: `0.005` is scale 3 |
| `round(x, n)` | scale `n` |
| `roundTo(x, step)` | the larger of the two scales |
| `cast(x, "Decimal(p,s)")` | rounded half away from zero to scale `s` |
| An integer `SUM / COUNT` in a computed output | 6 places |
| Any of these with a `Double` or `Float32` operand | `Double` — `round` / `roundTo` of a `Double` stay `Double` |

A result past 18 digits is an error, never a wrapped value and never a silent `Double`. A computed value stored in a
`Decimal(p,s)` column is then rounded half away from zero to that column's scale (table above).

**Common mistake:** Using `"Integer"`, `"Long"`, `"Float"`, or `"DateTime"` as type names — these are not valid. Use `Int32`, `Int64`, `Float32`, and `Timestamp` respectively.

**Declaring the column for a C# enum.** A C# enum binds to its **underlying** integral type, which
is `Int32` unless the enum says otherwise — so `enum RoomType { Direct, Group, Public }` needs
`"type": "Int32"`, not `"Byte"`, however small its values are. Declaring `Byte` there leaves the
schema and the model permanently disagreeing: the C# client's `AutoReconcileSchema` refuses the
write with `AoudaSchemaException` rather than silently narrowing, and will not migrate the column
on its own. Either declare `Int32`, or give the enum a `: byte` base. Full mapping table and the
reasoning: [Getting started § how a C# property becomes a column
type](../getting-started/index.md#how-a-c-property-becomes-a-column-type).


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
    "durability": { "level": "strict" }
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
      "amount":     { "type": "Decimal", "precision": 18, "scale": 2 },
      "created_at": { "type": "Timestamp" }
    },
    "partitionKey": [
      { "column": "tenant_id" }
    ],
    "clusterColumns": ["created_at"],
    "policy": { "storageTemperature": "Auto" },
    "durability": { "level": "strict" },
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
| `level` | `level` | `string` | `null` (inherit) | (**Lead S26, 0.6.0**) The table's durability level: `"strict"`, `"unlogged"` or `"memory"`; omitted or `null` = inherit the database's level. `"os"` is refused (a database level only); `"strict"` is refused unless the database is at `strict`; a change to or from `"memory"` after the table exists is refused. A table created while its database is at `memory` records `memory`. See [Write Path Durability](write-durability.md#durability-levels-lead-s26-060). The retired `walEnabled` is a validation error naming `durability.level`. |
| `replicationFactor` | `replicationFactor` | `int` | `null` (inherit) | Replication factor. Note: changing this via schema apply is currently skipped by the apply engine (see `ApplyStatus.Skipped`). Allowed values: non-negative integer, or `null` (inherit database default). |

#### SchemaSettings (value of `settings`)

| Field | JSON key | Type | Notes |
|---|---|---|---|
| `durability` | `durability` | `SchemaSettingsDurability` | Database-level durability settings. |

#### SchemaSettingsDurability (value of `settings.durability`)

(**Lead S26, 0.6.0**) No durability level here: a database's level is set where the database is created (`durability` on
`POST /api/databases`, `Aouda:Databases:<db>:Durability`, the embedded options) and read at every open. A `walEnabled` in
`settings.durability` is a schema validation error saying so. Export no longer writes `settings`.

| Field | JSON key | Type | Default | Notes |
|---|---|---|---|---|
| `replicationFactor` | `replicationFactor` | `int` | `null` (inherit) | Database-level replication factor. Informational in schema; not currently applied by the apply engine. Allowed values: non-negative integer, or `null` (inherit engine default). |

---

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: Inference-first prototype -> declarative baseline

1. Use server `InferenceMode=Extend` in development (or HTTP DDL, or the C# client's `AutoCreateSchema`).
2. Build and iterate with inferred table creation.
3. Export schema:
   - `dotnet aouda schema export --server http://localhost:5433 --database myapp --output aouda.schema.json`
4. Commit exported schema to git.
5. Switch production/shared environments to `InferenceMode=Off` (or `On`), apply the file there, and set
   `AutoReconcileSchema = false` on C# service clients (see [what `InferenceMode` decides](#what-inferencemode-decides-and-what-it-does-not)).

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

**When not to use the toggle:** for one-shot seed/reseed of reserved IDs while keeping the column autoIncrement, use **identity-insert** instead (`identityInsert: true` on insert or bulk-load) — see Scenario 6.

### Scenario 6: Seed reserved IDs without disabling autoIncrement

**Context:** `orders.id` is `autoIncrement: true`. You need to load historical rows with their original IDs (including `0`) and then continue generating new IDs above the seeded max — without flipping the column to Manual.

**Ordinary insert (small batches):**

```http
POST /api/databases/commerce/tables/orders/rows
Content-Type: application/json

{
  "database": "commerce",
  "table": "orders",
  "identityInsert": true,
  "columns": ["id", "status"],
  "data": [[1000, 0], ["seeded", "literal-zero"]]
}
```

The rows are column arrays (**Lead S12, 0.6.0**: `"rows": [{…}]` is refused `400 ROW_OBJECTS_UNSUPPORTED`; see the
[HTTP reference](../reference/http-api.md#column-arrays-the-write-body)).

**Bulk-load (large jobs):** set `options.identityInsert: true` on `:begin` and give every autoIncrement column on every appended row (not absent, not `null`). The counter advances only after a successful commit.

**Contrast with Scenario 5:**
| Approach | Schema change? | Counter bump | Best for |
|----------|----------------|--------------|----------|
| Identity-insert (BL-130/131) | No | After successful insert/commit to `max(inserted)` | Temporary seed/reseed |
| Toggle Auto→Manual (BL-126) | Yes | N/A (column no longer auto-generates) | Permanent manual ID ownership |

**Not the same as IDENTITY seed configuration:** custom *starting* counter values (seed/increment knobs) remain unimplemented (ADR 0013 — runtime MAX only). Identity-insert supplies *row values*; it does not configure a persistent seed.

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
| `DECLARATIVE_SCHEMA_DDL_FORBIDDEN` on a table or column call | Schema apply created the table, and HTTP DDL is refused there in every mode (**BL-1177, next train**) | Change the schema file and re-apply |
| `AoudaSchemaException: … under declarative schema management. Automatic reconciliation cannot drop column …` on the first typed write | The C# client's default reconcile tried to drop a column the model does not declare, such as a derived or server-stamped column | Set `AutoReconcileSchema = false` on that client |
| A derived or server-stamped column vanished after the first typed insert (0.7.0 and earlier) | Default reconcile (`Unsafe`) dropped it, and `On` / `Off` did not lock the table | Re-apply the schema, and set `AutoReconcileSchema = false` |
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

- The declarative DDL lock covers only tables that schema apply created. A table HTTP DDL created and an apply later extended stays
  open to HTTP DDL.
- No HTTP `/schema/validate` endpoint (validate is currently a CLI composition over diff).
- .NET CLI `schema seed` remains stubbed while server `schema/seed` endpoint exists.
- C# high-level schema interface does not yet include seed and branch convenience wrappers.
- IDENTITY seed configuration (starting value / increment knobs for the auto-increment counter) is not yet exposed; the counter always recovers from `MAX(column) + 1` on first use (ADR 0013). **Supplying explicit IDs** without a schema flip is available via identity-insert (BL-130 ordinary insert; BL-131 bulk-load) — do not confuse that with IDENTITY seed configuration.
- Table `partitionKey` / `clusterColumns` / column `partitionFunction` evolution, non-PK `unique` constraints, declarative `PkUniquenessMode`, and Vector/MdVector type changes remain out of scope (see engine `docs/BACKLOG.md` BL-148+ / P36 overview §12).
- Imperative `PATCH …/columns/{c}` does not yet carry `default` / `description` / PK (use declarative apply or Studio’s schema-apply dialogs).

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

