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
    "durability": { "walEnabled": true, "replicationFactor": 1 }
  }
}
```

Set `database` to the database name your Aouda server uses. Your IDE can validate and autocomplete if `$schema` points to the JSON Schema (see [ADR 0019](../decisions/0019-declarative-schema-management.md)).

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

#### Option B: TypeScript / JavaScript / Node

No install required; use npx:

```bash
npx @aouda/client schema diff --server http://localhost:5433 --database myapp
npx @aouda/client schema apply --server http://localhost:5433 --database myapp
```

Config and env vars (e.g. `AOUDA_SERVER`, `AOUDA_DATABASE`) work the same way as in the .NET CLI.

### 3. Verify

- **Diff**: Shows a human-readable plan (add table, add column, etc.). Use it on every PR to review schema changes. Add `--access` to fail the job when the branch **widens** what `mk_pub_*` or `aouda.identities.json` principals can read ([Access-surface diff](access-surface.md)). Named queries live under `namedQueries` in the same file ([Named queries](named-queries.md)); optional `freshness` on an alias is out-of-hash ([Freshness](freshness.md)). Materialized queries live under [`materializedQueries`](#materialized-queries-in-the-schema-file).
- **Apply**: Sends the desired schema to the server; the server computes and applies the necessary DDL. Destructive changes (drop table/column) are **refused by default**; use `--allow-destructive` only when intentional.
- **Validate**: Use `schema validate` in CI — it exits 0 if the server matches the file, 1 if there is drift.

### Diff warnings vs applyable column changes

**Column evolution (P36):** changing a column's `type`, `nullable`, `primaryKey`, `references`, `encoder`, `default`, `description`, rename, or reorder is now an applyable **change** (not a warning). Safe type widening (e.g. `Int32` → `Int64`) is an instant metadata flip with read-time coercion; lossy conversions validate all values first, then flip and rewrite column files in the background (`GET …/jobs`).

**Still warnings only:** changing table `partitionKey` or `clusterColumns` (and Vector/MdVector type changes). Those require dropping and re-creating the table (or a future migration phase).

Always inspect warnings before applying — a warning means the diff cannot close that gap automatically:

```bash
# View warnings in human-readable diff output
dotnet aouda schema diff --server http://localhost:5433 --database myapp

# View warnings in JSON format (top-level "warnings" array)
dotnet aouda schema diff --server http://localhost:5433 --database myapp --json
```

See the [Schema Lifecycle guide](schema.md) §2.6 / §2.11 for the full capability and change-type matrices.

That’s it. Your schema is now in code, and you can run diff/apply in CI/CD. See [Schema CI/CD Guide](Schema-CI-CD-Guide.md) for GitHub Actions and automation.

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

`aggregate` functions are `count`, `sum`, `min`, `max`, `average`, `first`, `last`; `first` / `last` take an `orderByColumn`. A `groupBy` term is a column name, or an object with a `function` for time bucketing (`TruncateToMinute` / `Hour` / `Day` / `Week` / `Month` / `Year`) plus an `outputName`. All five shapes accept `updateMode` (`async` | `sync`), `storage.storageTemperature`, and **`dataPlaneAccess`** (default `false`) — set it on the MQ entry so a `mk_pub_*` named query can read the result table without an imperative table-options PATCH.

**Public aggregate columns are the declared `outputName`s** (plus group keys), on every read path — `engine.Table(mq)`, `POST /tables/{mq}/query`, named query, subscribe. Physical state columns (`_count`, `_max_bid`, `_first_open_val`, …) are not selectable. A named query over `ohlc_1m` selects `high` / `open`, not `_max_price`.

`firstPerKey` is MIN of the order column (the same maintainer as `latestPerKey` with `descending: false`). It is **not** chronological first-arrival. `topNPerGroup` keeps a working set of every observed source row in process memory so ranks can demote without a refresh; point it at a compact per-key table (`latestPerKey` or `aggregate` result), not a million-row fact table. Query / subscribe the result table by name — the planner does not auto-route Top-N. The source table must have a primary key. Changing `n` or `orderBy` is a Replace (drop+create).

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

### Step 2: Turn off inference (recommended for production)

To avoid accidental new tables, configure the server so that tables are only created via schema apply or explicit DDL. Set **InferenceMode: Off** for the database (see server configuration and [ADR 0019](../decisions/0019-declarative-schema-management.md)). With inference off:

- Inserts to a **non-existent table** return an error.
- **New tables** must be created by running `schema apply` (or by direct DDL).
- Your schema file is the single place you define tables and columns.

You can keep **InferenceMode: On** in dev while you adopt the file; for staging and production, turning it off keeps the catalog aligned with the file.

### Step 3: Use the file for all changes

From here on:

1. Edit `aouda.schema.json` (and overlays like `aouda.schema.prod.json` if you use them).
2. Run `schema diff` to preview changes.
3. Run `schema apply` to apply them (in CI or by hand).
4. Use `schema validate` in CI to fail if someone changed the server without updating the file.

### Environment overlays

Use overlays to keep one schema definition and vary only settings (e.g. replication, WAL) per environment:

- `aouda.schema.json` — base (dev defaults).
- `aouda.schema.staging.json` — staging overrides.
- `aouda.schema.prod.json` — production overrides.

Overlays can only change **database-level settings** (`settings.durability`) and **per-table policy and durability** (`policy`, `durability`). They may not add or remove tables, and may not specify columns, partition keys, or cluster columns. The structural definition (columns, partitionKey, clusterColumns) always comes from the base file. Select overlay with `--env staging` or `AOUDA_ENVIRONMENT=prod`. See ADR 0019 for the exact merge rules.

### Summary

- **Quick start**: Add `aouda.schema.json`, run `schema diff` / `schema apply` with either `dotnet aouda` or `npx @aouda/client`.
- **Migration**: Export existing schema → optionally set InferenceMode to Off → do all changes via the file and `schema apply`.
- **CI/CD**: See [Schema CI/CD Guide](Schema-CI-CD-Guide.md) for workflows (PR diff comment, apply on merge/release).
