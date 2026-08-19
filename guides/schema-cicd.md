---
title: "Schema CI/CD"
nav_order: 4
parent: "Guides"
---

# Schema CI/CD Guide — Automated Schema Deployment

This guide describes how to automate Aouda schema management in CI/CD: run **diff** on pull requests (e.g. as a PR comment), **apply** to staging on merge, and **apply** to production on release.

---

## Overview

| Trigger | Action | Purpose |
|--------|--------|--------|
| **Pull request** | Run `schema diff --access`, post plan as PR comment | Review schema **and** access-surface widening before merge |
| **Merge to main** | Run `schema apply` against **staging** | Keep staging in sync with repo |
| **Release / tag** | Run `schema apply` against **production** | Deploy schema to prod only on release |

You can implement this with **.NET** (`dotnet aouda`) or **TypeScript** (`npx @aouda/client`). Ready-to-use GitHub Actions workflows are in the engine repo under `examples/github-actions/`.

**Access-surface gate (P37):** `aouda schema diff --access` exits **1** when the branch widens what `mk_pub_*` or a fixture identity can read. Without `--access`, a successful plan still exits 0. The TypeScript CLI does not yet have `--access` — use the .NET tool in CI. Details: [Access-surface diff](access-surface.md). Named queries, named mutations, and materialized queries belong in `aouda.schema.json` (`namedQueries` / `namedMutations` / `materializedQueries`); identities stay in a **sibling** `aouda.identities.json`. Omitting `materializedQueries` does not drop live MQs; a present map (including `{}`) is desired state for the whole MQ set.

---

## Prerequisites

1. **Schema file in repo**  
   `aouda.schema.json` (and optional overlays like `aouda.schema.prod.json`) at the repo root or discoverable by walk-up from the workflow working directory.

2. **Aouda server endpoints**  
   Staging and production (or a single server with different databases) reachable from the runner. Use **secrets** for URLs and any auth (e.g. `AOUDA_STAGING_SERVER`, `AOUDA_PROD_SERVER`, `AOUDA_DATABASE`).

3. **CLI available in CI**  
   - **.NET**: Install `Aouda.Cli` as a .NET tool or use a step that runs `dotnet tool install Aouda.Cli` then `dotnet aouda`.
   - **TypeScript**: Use `npx @aouda/client` (Node.js job); no global install needed.

---

## GitHub Actions: .NET Variant

Use this if your repo is .NET or you prefer the `dotnet aouda` CLI.

- **On PR**: Run `dotnet aouda schema diff` against the PR branch’s schema file and the **staging** server (or a dedicated “plan” database). Capture the plan output and post it as a PR comment (e.g. with `peter-evans/create-or-update-comment` or similar).
- **On push to main**: Run `dotnet aouda schema apply` against **staging** so that staging always matches the schema in `main`.
- **On release**: Run `dotnet aouda schema apply` against **production** (and optionally `--env prod` if you use `aouda.schema.prod.json`).

### Workflow 1: PR diff comment (.NET)

Posts the schema plan as a PR comment so reviewers can see exactly what will change before merge.

```yaml
name: Schema — PR diff comment

on:
  pull_request:
    paths:
      - "aouda.schema*.json"

jobs:
  schema-diff:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.x"

      - name: Install Aouda CLI
        run: dotnet tool install Aouda.Cli -g

      - name: Run schema diff
        id: diff
        env:
          AOUDA_SERVER: ${{ secrets.AOUDA_STAGING_SERVER }}
          AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
        run: |
          PLAN=$(dotnet aouda schema diff --access 2>&1 || true)
          echo "plan<<EOF" >> "$GITHUB_OUTPUT"
          echo "$PLAN"    >> "$GITHUB_OUTPUT"
          echo "EOF"      >> "$GITHUB_OUTPUT"
        # Exit 1 from --access means hasWidening — fail the job:
        # run a second step `aouda schema diff --access` without swallowing the exit code.

      - name: Post diff as PR comment
        uses: peter-evans/create-or-update-comment@v4
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body: |
            ## Schema diff (staging)

            ```
            ${{ steps.diff.outputs.plan }}
            ```
```

### Workflow 2: Apply to staging on merge (.NET)

Runs `schema apply` against staging whenever `main` is updated, keeping staging in sync.

```yaml
name: Schema — Apply to staging

on:
  push:
    branches: [main]
    paths:
      - "aouda.schema*.json"

jobs:
  schema-apply-staging:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.x"

      - name: Install Aouda CLI
        run: dotnet tool install Aouda.Cli -g

      - name: Apply schema to staging
        env:
          AOUDA_SERVER: ${{ secrets.AOUDA_STAGING_SERVER }}
          AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
        run: dotnet aouda schema apply
```

### Workflow 3: Apply to production on release (.NET)

Runs `schema apply` against production when a GitHub release is published. Uses `--env prod` to merge the production overlay before applying.

```yaml
name: Schema — Apply to production

on:
  release:
    types: [published]

jobs:
  schema-apply-prod:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.x"

      - name: Install Aouda CLI
        run: dotnet tool install Aouda.Cli -g

      - name: Apply schema to production
        env:
          AOUDA_SERVER: ${{ secrets.AOUDA_PROD_SERVER }}
          AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
        run: dotnet aouda schema apply --env prod
```

Copy these three files into `.github/workflows/` in your repository, configure the secrets, and adjust the `paths` filter to match where your schema file lives. Full examples (with additional error-handling steps) are also under `examples/github-actions/schema-deploy-dotnet.yml` in the repository.

**Secrets to configure:**

- `AOUDA_STAGING_SERVER` — base URL of staging Aouda (e.g. `https://aouda-staging.example.com`).
- `AOUDA_PROD_SERVER` — base URL of production Aouda.
- `AOUDA_DATABASE` — database name (or use separate secrets per environment).

Use `AOUDA_SERVER` and `AOUDA_DATABASE` in the workflow so the CLI picks them up; the examples use env vars set from secrets.

---

## GitHub Actions: TypeScript Variant

Use this if your repo is Node/TypeScript or you prefer the `@aouda/client` CLI.

Same flow as .NET:

- **On PR**: `npx @aouda/client schema diff` and post the plan as a PR comment.
- **On push to main**: `npx @aouda/client schema apply` against staging.
- **On release**: `npx @aouda/client schema apply` against production (with `--env prod` if using overlays).

**Secrets**: Same as the .NET variant (`AOUDA_STAGING_SERVER`, `AOUDA_PROD_SERVER`, `AOUDA_DATABASE`).

### Workflow 1: PR diff comment (TypeScript)

```yaml
name: Schema — PR diff comment (TypeScript)

on:
  pull_request:
    paths:
      - "aouda.schema*.json"

jobs:
  schema-diff:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Run schema diff
        id: diff
        env:
          AOUDA_SERVER: ${{ secrets.AOUDA_STAGING_SERVER }}
          AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
        run: |
          PLAN=$(npx @aouda/client schema diff 2>&1 || true)
          echo "plan<<EOF" >> "$GITHUB_OUTPUT"
          echo "$PLAN"    >> "$GITHUB_OUTPUT"
          echo "EOF"      >> "$GITHUB_OUTPUT"

      - name: Post diff as PR comment
        uses: peter-evans/create-or-update-comment@v4
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body: |
            ## Schema diff (staging)

            ```
            ${{ steps.diff.outputs.plan }}
            ```
```

### Workflow 2: Apply to staging on merge (TypeScript)

```yaml
name: Schema — Apply to staging (TypeScript)

on:
  push:
    branches: [main]
    paths:
      - "aouda.schema*.json"

jobs:
  schema-apply-staging:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Apply schema to staging
        env:
          AOUDA_SERVER: ${{ secrets.AOUDA_STAGING_SERVER }}
          AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
        run: npx @aouda/client schema apply
```

### Workflow 3: Apply to production on release (TypeScript)

```yaml
name: Schema — Apply to production (TypeScript)

on:
  release:
    types: [published]

jobs:
  schema-apply-prod:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Apply schema to production
        env:
          AOUDA_SERVER: ${{ secrets.AOUDA_PROD_SERVER }}
          AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
        run: npx @aouda/client schema apply --env prod
```

Full examples are also under `examples/github-actions/schema-deploy-typescript.yml` in the repository.

---

## Safety and Options

- **Destructive changes**  
  By default, `schema apply` **refuses** destructive changes (e.g. drop table, drop column). To allow them (e.g. in a one-off release), pass `--allow-destructive`. Prefer doing this only in a controlled step (e.g. manual approval or a dedicated “destructive” workflow).

- **Dry run**  
  Use `schema apply --dry-run` to get the same plan as apply without executing. Useful for “would this change anything?” checks.

- **Validate in CI**  
  Use `schema validate` in a job that should **fail** if the server has drifted from the schema file (e.g. someone changed the DB by hand). Exit code 0 = in sync, 1 = drift.

- **Environment overlays**  
  Use `--env prod` when applying to production so the CLI merges `aouda.schema.prod.json` (replication factor, WAL, etc.) before sending to the server.

---

## Summary

| Goal | Command / step |
|------|-----------------|
| Preview changes on PR | `schema diff` → post output as PR comment |
| Apply to staging on merge | `schema apply` (staging server/database) |
| Apply to prod on release | `schema apply` (prod server/database, optional `--env prod`) |
| Fail CI if server drifted | `schema validate` (exit 1 if drift) |

Copy and customize the workflows under `examples/github-actions/` and set the required secrets. For a quick start with schema files and local CLI usage, see [Schema Management Guide](Schema-Management-Guide.md).
