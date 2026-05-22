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

- **Diff**: Shows a human-readable plan (add table, add column, etc.). Use it on every PR to review schema changes.
- **Apply**: Sends the desired schema to the server; the server computes and applies the necessary DDL. Destructive changes (drop table/column) are **refused by default**; use `--allow-destructive` only when intentional.
- **Validate**: Use `schema validate` in CI — it exits 0 if the server matches the file, 1 if there is drift.

### Diff warnings: unsupported changes

Some schema changes cannot be executed by the apply engine — for example, changing a column's type, changing `primaryKey`, `autoIncrement`, or `nullable` on an existing column, or changing partition keys or cluster columns. The diff engine reports these as **warnings** (not changes). Warnings appear in the diff output but are never applied; they always require manual intervention such as dropping and re-creating the column or table.

Always inspect warnings before applying. A warning means the diff cannot close the gap between your desired schema and the running catalog automatically:

```bash
# View warnings in human-readable diff output
dotnet aouda schema diff --server http://localhost:5433 --database myapp

# View warnings in JSON format (top-level "warnings" array)
dotnet aouda schema diff --server http://localhost:5433 --database myapp --json
```

Example warning: `Column type change from 'Int32' to 'Int64' is not supported. Drop and re-create the column manually.`

See the [Schema Lifecycle guide](schema.md) for a full list of operations that produce warnings vs. changes.

That’s it. Your schema is now in code, and you can run diff/apply in CI/CD. See [Schema CI/CD Guide](Schema-CI-CD-Guide.md) for GitHub Actions and automation.

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
