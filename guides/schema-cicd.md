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
| **Pull request** | Run `schema diff`, post plan as PR comment | Review schema changes before merge |
| **Merge to main** | Run `schema apply` against **staging** | Keep staging in sync with repo |
| **Release / tag** | Run `schema apply` against **production** | Deploy schema to prod only on release |

You can implement this with **.NET** (`dotnet aouda`) or **TypeScript** (`npx @aouda/client`). Ready-to-use GitHub Actions workflows are in the repo under `examples/github-actions/`.

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

Example workflow files:

- `examples/github-actions/schema-deploy-dotnet.yml` — full example (PR diff comment, apply on merge, apply on release).
- `examples/github-actions/README.md` — how to copy and configure the workflows.

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

Example workflow:

- `examples/github-actions/schema-deploy-typescript.yml` — full example.

**Secrets**: Same as above (`AOUDA_STAGING_SERVER`, `AOUDA_PROD_SERVER`, `AOUDA_DATABASE`).

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
