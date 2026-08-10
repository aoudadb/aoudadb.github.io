---
title: "SDK Compatibility"
nav_order: 3
parent: "Clients"
---

# SDK Compatibility Matrix

Aouda ships multiple artifacts from separate repositories. They do **not** share a single version number. Use this matrix to pick compatible combinations.

---

## Versioning model

| Artifact | Package / image | Repo | Version scheme |
|----------|-----------------|------|----------------|
| Aouda server | `aouda/server` (Docker), `Aouda.Server` (binary) | `aouda` | Release train (not npm SemVer) |
| TypeScript client | `@aouda/client` (npm) | `aouda-client-ts` | SemVer |
| .NET client | `Aouda.Client` (NuGet) | `aouda` | SemVer |
| Studio | `aouda/studio` (Docker), hosted app | `aouda-studio` | App version |

**Release order** when APIs change: server → SDKs → Studio → docs.

---

## Compatibility matrix

Update this table when shipping breaking server, client, or Studio changes.

| Server (approx.) | Wire protocol | `@aouda/client` | `Aouda.Client` (NuGet) | Studio (approx.) | Notes |
|------------------|---------------|-----------------|------------------------|------------------|-------|
| `0.1.5` | `1` | `≥ 0.1.8` (P36 `alterColumn` / `reorderColumns` / `jobs` / typed `SchemaChangeType`) | `≥ 0.1.5` | `≥ 0.0.15` | P36 Column Evolution train: ALTER COLUMN HTTP + clients + Studio schema UI. Studio pin `@aouda/client` `0.1.8`. |
| `0.1.4` | `1` | `≥ 0.1.7` (BL-132 outbox + `acknowledgeDevCapture`; BL-130/131 `identityInsert`) | `≥ 0.1.4` | `≥ 0.0.14` | Patch train: capture notification outbox, identity-insert (row + bulk-load). Studio notifications UI uses outbox via admin HTTP; pin `@aouda/client` `0.1.7`. |
| `0.1.3` | `1` | `≥ 0.1.6` (BL-126 `columnsAltered`; residency filter fields still HTTP-raw) | `≥ 0.1.3` | `≥ 0.0.13` | Patch train: BL-091 residency HTTP, BL-126 autoIncrement toggle, async durable DB drop, partition routing, freeze/abort correctness. |
| `0.1.2` / earlier | `1` | `≥ 0.0.1` (`0.0.3`+ LNA; `0.1.0`+ P17 database catalog) | `≥ 0.1.0` | `≥ 0.0.2` | P17: internal DB filtering + catalog metadata — Studio `0.0.2` pins `@aouda/client` `0.1.0`. Hosted Studio → localhost needs client `≥ 0.0.3`. |

### Reading the matrix

- **Wire protocol** — HTTP header `X-Aouda-Protocol-Version`. Server and clients must agree on supported protocol versions.
- **`@aouda/client`** — Minimum npm version for a server generation. Studio may pin a specific patch (see `aouda-studio/package.json`).
- **`Aouda.Client`** — NuGet version for .NET apps and Hub; tracks API parity with the TS client but versions independently.
- **Studio** — Requires a server reachable at runtime; build-time dependency is only `@aouda/client`.

---

## Pre-1.0 guidance

While `@aouda/client` is `0.x`:

- Pin **exact** versions in production (`"0.0.1"`, not `"^0.0.1"`).
- Prefer **patch** releases for additive API while on the `0.0.x` line (`0.0.3` → `0.0.4`). A Changesets **minor** bump advances the middle digit (`0.0.3` → `0.1.0`).
- Regenerate TypeScript schema types after server schema changes: `npx @aouda/client generate`.

---

## Release documentation

| Topic | Location |
|-------|----------|
| **Cross-repo bump procedure (agents)** | Shared docs repo: `Cross-Repo-Release-And-Version-Bump.md` (`D:\GitHub\docs\` or `C:\Data\GitHub\docs\`) |
| npm Changesets + publish | [aouda-client-ts `docs/dev/Release-Process.md`](https://github.com/aouda/aouda-client-ts/blob/main/docs/dev/Release-Process.md) |
| Studio pin + local link | [aouda-studio `docs/dev/Dependency-Policy.md`](https://github.com/aouda/aouda-studio/blob/main/docs/dev/Dependency-Policy.md) |
| TypeScript client API | [TypeScript Client](./typescript.md) |

Dependency bumps are **manual**. Agents follow the cross-repo release doc after each `@aouda/client` publish.
