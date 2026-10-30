---
title: "Schema Management"
nav_order: 3
parent: "Guides"
---

# Schema Management Guide

This guide explains how to add declarative schema management to your project and how to move from inference-based schema to a file-based workflow.

---

## NuGet package: Aouda.Schema.Contract

When writing C# code that works with schema types (`SchemaDocument`, `ApplyOptions`, `SchemaDiffResult`, etc.), install `Aouda.Schema.Contract`:

```bash
dotnet add package Aouda.Schema.Contract
```

This is a thin facade package that exposes only the schema model types and result types — not the full server engine. If you already have `Aouda.Client` installed, you do not need `Aouda.Schema.Contract` separately; `Aouda.Client` depends on it and re-exports its types through `ISchemaOperations`. For a full type reference, see the [Schema Lifecycle guide](schema.md).

---

## Quick Start: Add Schema Management in 5 Minutes

You can get schema management working with a single JSON file and one of two CLIs: **.NET** (`dotnet aouda`) or **TypeScript** (`npx @aouda/client`).

### 1. Create a schema file

In your project root, create `aouda.schema.json`:

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "myapp",
  "tables": {
    "users": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "name": { "type": "String" },
        "created_at": { "type": "Timestamp" }
      }
    }
  },
  "settings": {
    "durability": { "replicationFactor": 1 }
  }
}
```

(**Lead S26, 0.6.0**) `settings.durability` carries only `replicationFactor`. A database's durability level (`strict`, `os`,
`unlogged` or `memory`) is set where the database is created, not in the schema; a table may name its own with
`"durability": { "level": "unlogged" }` (`strict`, `unlogged` or `memory`). The retired `walEnabled` is a validation error. See
[Write Path Durability](write-durability.md#durability-levels-lead-s26-060).

Set `database` to the database name your Aouda server uses. Your IDE can validate and autocomplete if `$schema` points to the JSON Schema (see [ADR 0019](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0019-declarative-schema-management.md)).

### 2. Choose your CLI

#### Option A: .NET (C# / F# / VB projects)

Install the Aouda CLI as a global or local tool:

```bash
dotnet tool install Aouda.Cli -g
```

From your repo root (where `aouda.schema.json` lives):

```bash
# Preview what would change (no writes)
dotnet aouda schema diff --server http://localhost:5433 --database myapp

# Apply schema to the server
dotnet aouda schema apply --server http://localhost:5433 --database myapp
```

If you omit `--server` and `--database`, the CLI uses `AOUDA_SERVER` and `AOUDA_DATABASE` environment variables.

**Against an auth-enabled database, pass a token** (**BL-464, 0.1.37**). Every `schema`
subcommand — `diff`, `apply`, `export`, `validate`, `history`, `seed` — takes `--token` / `-t`, and
falls back to the `AOUDA_TOKEN` environment variable when the flag is omitted, the same way
`--server` falls back to `AOUDA_SERVER`:

```bash
export AOUDA_SERVER=http://localhost:5433
export AOUDA_DATABASE=myapp
export AOUDA_TOKEN=mk_srv_...          # server admin key, or a bearer token

dotnet aouda schema diff                # no flags needed
dotnet aouda schema apply --token mk_srv_...   # or pass it explicitly
```

Without one, these commands exit `2` with `AUTH_TOKEN_MISSING`. Against a database with auth
disabled, omit the token entirely — no `Authorization` header is sent.

#### Option B: TypeScript / JavaScript / Node

No install required; use npx:

```bash
npx @aouda/client schema diff --server http://localhost:5433 --database myapp
npx @aouda/client schema apply --server http://localhost:5433 --database myapp
```

Config and env vars (e.g. `AOUDA_SERVER`, `AOUDA_DATABASE`) work the same way as in the .NET CLI.

### 3. Verify

- **Diff**: Shows a human-readable plan (add table, add column, etc.). Use it on every PR to review schema changes. Add `--access` to fail the job when the branch **widens** what `mk_pub_*` or `aouda.identities.json` principals can read ([Access-surface diff](access-surface.md)). Named queries live under `namedQueries` in the same file ([Named queries](named-queries.md)); optional `freshness` on the named query is keyed by name ([Freshness](freshness.md)). Omitting a name deletes the definition (there is no `dropNamedQueries`). Materialized queries live under [`materializedQueries`](#materialized-queries-in-the-schema-file).
- **Apply**: Sends the desired schema to the server; the server computes and applies the necessary DDL. Destructive changes (drop table/column) are **refused by default**; use `--allow-destructive` only when intentional.
- **Validate**: Use `schema validate` in CI — it exits 0 if the server matches the file, 1 if there is drift.

### Diff warnings vs applyable column changes

**Column evolution (P36):** changing a column's `type`, `nullable`, `primaryKey`, `references`, `default`, `description`, rename, or reorder is now an applyable **change** (not a warning). Safe type widening (e.g. `Int32` → `Int64`) is an instant metadata flip with read-time coercion; lossy conversions validate all values first, then flip and rewrite column files in the background (`GET …/jobs`).

**Still warnings only:** changing table `clusterColumns` (and Vector/MdVector type changes). Those require dropping and re-creating the table (or a future migration phase).

**Refused, not warned past** (**BL-1199, next train**): a table's partition key is fixed when the table is created. A document that
changes a table's `partitionKey` or a column's `partitionFunction`, or drops, renames or adds a partition-key column, is refused
whole — `schema apply` (and `--dry-run`) fails with `400 PARTITION_KEY_FIXED` naming every reason, and nothing in the document is
applied. `schema diff` still shows the change as a `partitionKey` / `partitionFunction` warning. Until this release the apply ran the
column changes such a document implied (the key column was dropped, renamed or added) and printed the warning beside the result. To
change a key, drop and re-create the table.

Always inspect warnings before applying — a warning means the diff cannot close that gap automatically:

```bash
# View warnings in human-readable diff output
dotnet aouda schema diff --server http://localhost:5433 --database myapp

# View warnings in JSON format (top-level "warnings" array)
dotnet aouda schema diff --server http://localhost:5433 --database myapp --json
```

See the [Schema Lifecycle guide](schema.md) §2.6 / §2.11 for the full capability and change-type matrices.

That’s it. Your schema is now in code, and you can run diff/apply in CI/CD. See [Schema CI/CD Guide](schema-cicd.md) for GitHub Actions and automation.

---

## Materialized queries in the schema file

Materialized queries are declared under a top-level `materializedQueries` map, keyed by name. The name **is** the identity, and it is also the result table you query.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "trading",
  "tables": { },
  "materializedQueries": {
    "latest_quote": {
      "type": "latestPerKey",
      "sourceTable": "EquityQuote",
      "dataPlaneAccess": true,
      "groupBy": ["ticker"],
      "orderBy": "ts",
      "descending": true,
      "select": ["ticker", "price", "ts"]
    },
    "ohlc_1m": {
      "type": "aggregate",
      "sourceTable": "EquityQuote",
      "dataPlaneAccess": true,
      "groupBy": [
        "ticker",
        { "column": "ts", "function": "TruncateToMinute", "outputName": "bucket" }
      ],
      "aggregates": [
        { "function": "first", "sourceColumn": "price", "outputName": "open",  "orderByColumn": "ts" },
        { "function": "max",   "sourceColumn": "price", "outputName": "high" },
        { "function": "min",   "sourceColumn": "price", "outputName": "low" },
        { "function": "last",  "sourceColumn": "price", "outputName": "close", "orderByColumn": "ts" },
        { "function": "count",                          "outputName": "ticks" }
      ],
      "updateMode": "async"
    }
  }
}
```

Five shapes, discriminated by `type`:

| `type` | Required | Use for |
|---|---|---|
| `latestPerKey` | `sourceTable`, `groupBy`, `orderBy` | Current-value tables — latest quote per ticker |
| `firstPerKey` | `sourceTable`, `groupBy`, `orderBy` | One row per group: **MIN** of `orderBy`, not the first row that arrived. `descending: true` is rejected — use `latestPerKey` |
| `aggregate` | `sourceTable`, `groupBy`, `aggregates` | Rollups — OHLC candles, per-tenant counts |
| `filter` | `sourceTable`, `predicate` | A maintained subset of a table |
| `topNPerGroup` | `sourceTable`, `orderBy`, `n` (`groupBy` optional) | At most **N rows per group** (or global top N when `groupBy` is omitted). Result PK is the source PK |

`aggregate` functions are `count`, `sum`, `min`, `max`, `average`, `first`, `last`; `first` / `last` take an `orderByColumn`. A `groupBy` term is a column name, or an object with a `function` for time bucketing (`TruncateToMinute` / `Hour` / `Day` / `Week` / `Month` / `Year`) plus an `outputName`. All five shapes accept `updateMode` (`async` | `sync`), **`maxCoalesceMs`** (the freshness knob, 0–60000 ms, default 0: how long an `async` query's batches may coalesce before one apply — **ColumnarMerge S10, 0.2.0**; changing it replaces the query), `storage.storageTemperature`, and **`dataPlaneAccess`** (default `false`) — set it on the MQ entry so a `mk_pub_*` named query can read the result table without an imperative table-options PATCH.

**`window`** (**Horizon, 0.5.0**) — `"window": { "keep": "7d" }` (plus `"column"` where it must be named) on an `aggregate` with a `TruncateToMinute` / `Hour` / `Day` / `Week` bucket, or on a `topNPerGroup` grouped by a time column: the result keeps only its groups at or after the horizon (the server's clock minus `keep`), and a read of anything older is computed from the source, so the answer does not change. Every other declaration is refused at apply with its reason — the full list is in [Materialized queries — what is refused](materialized.md#window-refusals). `schema export` writes it, and changing it replaces the query.

**`currency`** (**Lead S27b, 0.6.0**) — `"currency": "rebuild"` on any materialized query: never maintained incrementally; a change to its source leaves it behind (not routed to) until it is rebuilt, once the source is quiet, after a load, or on `:refresh`. Omitted is `"current"` (maintained off each commit). Not with `"updateMode": "sync"` or `maxCoalesceMs`. Part of the query's body, so changing it replaces the query. See [Materialized queries](materialized.md#27-core-concepts-and-mental-model).

**Public aggregate columns are the declared `outputName`s** (plus group keys), on every read path — `engine.Table(mq)`, `POST /tables/{mq}/query`, named query, subscribe. Physical state columns (`_count`, `_max_bid`, `_first_open_val`, …) are not selectable. A named query over `ohlc_1m` selects `high` / `open`, not `_max_price`.

`firstPerKey` is MIN of the order column (the same maintainer as `latestPerKey` with `descending: false`). It is **not** chronological first-arrival. `topNPerGroup` keeps a working set of every observed source row in process memory so ranks can demote without a refresh; point it at a compact per-key table (`latestPerKey` or `aggregate` result), not a million-row fact table. Result-table commits on that source MQ feed the Top-N maintainer incrementally. Query / subscribe the result table by name — the planner does not auto-route Top-N. The source table must have a primary key. Changing `n` or `orderBy` is a Replace (drop+create).

### The map is desired state — and omitting it is not the same as emptying it

This is the one behaviour to get right before you add the map to an existing project:

| In the file | Effect on apply |
|---|---|
| `materializedQueries` **omitted** (or null) | Live MQs are left **unmanaged** — nothing is created, changed, or dropped |
| `"materializedQueries": { … }` | Desired state. Anything live and not listed is **dropped** |
| `"materializedQueries": {}` | **Drops every MQ** in the database |

So the safe first step on an existing database is `schema export`, which now writes live MQs into the map (an empty catalog exports as `{}`), rather than hand-adding a partial map and discovering the rest were dropped.

**Changing a definition is a replace, and a replace is drop + create.** It therefore requires `--allow-destructive`, and the result table is rebuilt from the source rather than migrated. Renaming an MQ is a drop and a create for the same reason — the name is the identity.

The admin HTTP create endpoint still exists and still works; the schema file is now the recommended path because it puts MQ definitions under the same review, diff, and CI gate as everything else.

---

## Moving from Inference to Declarative Schema

Aouda can create tables automatically when you insert data (**inference mode**). For production and team workflows, we recommend moving to **declarative schema**: a single `aouda.schema.json` in git, applied via CLI or CI.

### What changes when you switch?

| Aspect | Inference (before) | Declarative (after) |
|--------|-------------------|----------------------|
| **Source of truth** | Server infers from first inserts | `aouda.schema.json` in your repo |
| **New tables** | Created on first insert | Created by `schema apply` (or DDL) |
| **Schema changes** | Add column by inserting with new column | Edit JSON, run `schema apply` |
| **Review** | No built-in review | PR = diff of schema file; CI can post plan as comment |
| **Environments** | Same or manual | One file + overlays (e.g. `aouda.schema.prod.json`) |

### Step 1: Export current schema (optional)

If you already have tables created by inference or by hand, export the server’s current schema into a file:

**.NET:**

```bash
dotnet aouda schema export --server http://localhost:5433 --database myapp --output aouda.schema.json
```

**TypeScript:**

```bash
npx @aouda/client schema export --server http://localhost:5433 --database myapp --output aouda.schema.json
```

Then add `"$schema": "https://aouda.io/schema/v1.json"` at the top and set `database` to your database name. Commit this file; it becomes your desired state.

### Step 2: Choose `InferenceMode`, and turn off client reconcile

`InferenceMode` decides one thing: what an insert into a missing table does. See [the mode table](schema.md#what-inferencemode-decides-and-what-it-does-not)
and [ADR 0019](https://github.com/aoudadb/aouda/blob/main/docs/decisions/0019-declarative-schema-management.md). With **`Off`** or
**`On`** (the default):

- Inserts to a **non-existent table** return `404`.
- **New tables** must be created by running `schema apply` (or by direct DDL).
- Your schema file is the single place you define tables and columns.

**`Extend`** creates a missing table from the first insert's rows. That helps in development. It does not suit an environment whose
tables the file owns.

**A table that `schema apply` created is locked against HTTP DDL in every mode** (**BL-1177, 0.7.1**). Dropping or renaming the
table, changing its options, its policy's temperature or retention, and adding, altering, reordering or dropping a column are all
answered `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN`. Residency tuning (`memoryRowCap` and the rest) is not in the file, and it stays
open. Before this change only `Extend` refused, so in `On` a client could delete a column from a table
the file had just applied. `Off` stops inference. It is not the lock.

> **⚠️ Set `AutoReconcileSchema = false` on every C# client that writes to these tables.** `Aouda.Client` defaults to
> `AutoReconcileSchema = true` with `ReconcilePolicy = Unsafe`. Its first typed write to a table drops every column the model does not
> declare: a derived `SearchText`, a server stamp, any column left off the row type. Since BL-1177 that write fails with
> `AoudaSchemaException` on a schema-applied table instead of deleting the column. On 0.7.0 and earlier, the column was deleted and
> the write succeeded. Bulk load does not reconcile, so a bulk-loaded table and a typed-insert table can end up with different columns.

### Step 3: Use the file for all changes

From here on:

1. Edit `aouda.schema.json` (and overlays like `aouda.schema.prod.json` if you use them).
2. Run `schema diff` to preview changes.
3. Run `schema apply` to apply them (in CI or by hand).
4. Use `schema validate` in CI to fail if someone changed the server without updating the file.

### Environment overlays

Use overlays to keep one schema definition and vary only settings (e.g. replication, a table's durability level) per environment:

- `aouda.schema.json` — base (dev defaults).
- `aouda.schema.staging.json` — staging overrides.
- `aouda.schema.prod.json` — production overrides.

Overlays can only change **database-level settings** (`settings.durability`) and **per-table policy and durability** (`policy`, `durability`). They may not add or remove tables, and may not specify columns, partition keys, or cluster columns. The structural definition (columns, partitionKey, clusterColumns) always comes from the base file. Select overlay with `--env staging` or `AOUDA_ENVIRONMENT=prod`. See ADR 0019 for the exact merge rules.

### Summary

- **Quick start**: Add `aouda.schema.json`, run `schema diff` / `schema apply` with either `dotnet aouda` or `npx @aouda/client`.
- **Migration**: Export existing schema → optionally set InferenceMode to Off → set `AutoReconcileSchema = false` on C# clients → do all changes via the file and `schema apply`.
- **CI/CD**: See [Schema CI/CD Guide](schema-cicd.md) for workflows (PR diff comment, apply on merge/release).
