---
title: "Distribution and Licensing"
nav_order: 2
parent: "Clients"
---

# Aouda Functionality: Distribution and Licensing

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-04-08

Coverage phases: P4, P8, P11, P13
Primary task folders: `docs/tasks/P4/`, `docs/tasks/P8/`, `docs/tasks/P11/`, `docs/tasks/P13/`
Primary ADRs: `docs/decisions/0022-licensing-and-distribution-strategy.md`, `docs/decisions/0024-testing-package.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Testing-And-DX.md`, `docs/dev/Functionality-Auth-And-Authorization.md`

## Start Here

If your question is "How do I install and run Aouda artifacts now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`

If your question is "What is shipped vs not shipped in distribution and licensing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)

---

## 2.1 Why this functionality exists

Distribution and licensing in Aouda are product behavior, not packaging trivia.

- User problem solved:
  - Developers need one-command or one-package adoption paths across embedded, server, and client usage.
  - Teams need clear legal boundaries for what is free to use, what is restricted, and where MIT vs BSL applies.
- Operational/business outcomes:
  - Consistent artifact model for NuGet, npm, and dotnet global tool flows.
  - Explicit protection against third-party "managed Aouda" reselling while keeping client/tooling low-friction.
  - Repeatable local and CI packaging/consumption patterns.
- Scope boundaries:
  - This doc covers current artifacts, package metadata, licensing surfaces, and runtime distribution entry points.
  - It does not define cloud billing, commercial terms, or legal contract negotiation process.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| Which artifacts exist today | `2.4 Availability status` |
| Which phase delivered what | `2.5 Phase coverage matrix` |
| Full capability completeness | `2.6 Capability coverage matrix` |
| Current package/license metadata | `2.10 Configuration and settings reference` |
| Install/run examples across SDKs and CLI | `2.11 API and CLI coverage reference`, `2.12 Scenario playbooks` |
| Operational checks for packaging/distribution | `2.13 Operations and observability`, `2.15 Verification ledger` |
| Known release/licensing gaps | `2.17 Testing gaps and proposed tests`, `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer (.NET) | `2.3`, `2.10`, `2.11`, `2.12` |
| SDK maintainer | `2.6`, `2.10`, `2.11`, `2.16`, `2.17` |
| Operator / platform engineer | `2.10`, `2.12`, `2.13`, `2.14` |
| Legal/compliance reviewer | `2.4`, `2.9`, `2.10`, `2.18` |
| Engine/server contributor | `2.5`, `2.8`, `2.8.1`, `2.19` |

### Source map

- Task/report evidence:
  - `docs/tasks/P4/P4-Integration-Distribution-Tasks.md`
  - `docs/tasks/P8/BL031-AoudaClient-NuGetPackage-And-Docs.md`
  - `docs/tasks/P11/P11-UnifiedDistribution-Tasks.md`
  - `docs/tasks/P11/P11-EpicC-Task1-BSL-License-And-Repository-Setup-Report.md`
  - `docs/tasks/P11/P11-EpicC-Task2-MIT-License-Client-Packages-Report.md`
  - `docs/tasks/P11/P11-EpicE-E1-E2-Report.md`
  - `docs/tasks/P13/P13-Testing-Package-Tasks.md`
- ADR evidence:
  - `docs/decisions/0022-licensing-and-distribution-strategy.md`
  - `docs/decisions/0024-testing-package.md`
- Code/package evidence:
  - `LICENSE`, `LICENSE-MIT`
  - `src/Aouda.Embedded/Aouda.Embedded.csproj`
  - `src/Aouda.Embedded.Hot/Aouda.Embedded.Hot.csproj`
  - `src/Aouda.Abstractions/Aouda.Abstractions.csproj`
  - `src/Aouda.Client/Aouda.Client.csproj`
  - `src/Aouda.Cli/Aouda.Cli.csproj`
  - `src/Aouda.Server/Aouda.Server.csproj`
  - `src/Aouda.Testing/Aouda.Testing.csproj`
  - `aouda-client-ts/package.json`
- Runtime entry points:
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Embedded/AoudaEmbedded.cs`
  - `src/Aouda.Embedded/Configuration/AoudaOptionsEnvOverlay.cs`

## 2.3 Defaults and zero-config behavior

If you do nothing except install artifacts:

- `Aouda.Embedded` defaults to ephemeral temp-path operation when `DataPath` is not set.
- `aouda start` is the shipped CLI server entry point (`aouda dev` was planned but is not exposed in the current CLI; use `aouda start` with `--port` and `--data-dir`). Typical local defaults when using appsettings:
  - `--port 5433`
  - `--database default`
  - ephemeral data path (temp folder, deleted on shutdown)
  - `--auth` disabled
- `Aouda.Testing` defaults to MIT-licensed in-process test-server packaging.
- TypeScript client package defaults to MIT license and Node `>=20` engine requirement.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `Aouda.Embedded` data location | Temp directory when `DataPath` null | Zero-setup embedded trial path; data lost after dispose |
| `Aouda.Embedded` WAL | `EnableWal = true` in embedded options | Durable writes when using persistent path |
| `aouda start --port` | `5433` (from config) | Predictable local URL (`http://localhost:5433`) |
| Database name | from API / config | Create via `POST /api/databases` or appsettings `Databases` |
| `aouda start --data-dir` | `./data` typical | Persistent server data |
| App auth | via HTTP API | Enable with `auth.enabled` on create-database; keys in response |
| `Aouda.Abstractions` package version | `0.1.0` (current csproj) | Stable explicit package identity while pre-1.0 |
| `@aouda/client` license | `MIT` | No extra licensing friction for npm consumption |

## 2.4 Availability status (implementation honesty)

### Available now

- BSL + MIT base files exist at repository root (`LICENSE`, `LICENSE-MIT`).
- Package-level licensing metadata is wired in current packable projects:
  - BSL-style package license file usage in `Aouda.Embedded` and `Aouda.Embedded.Hot`.
  - MIT license expression usage in `Aouda.Abstractions`, `Aouda.Client`, `Aouda.Cli`, `Aouda.Testing`.
  - TypeScript package declares `"license": "MIT"`.
- Multi-artifact distribution paths are implemented:
  - NuGet packages: `Aouda.Embedded`, `Aouda.Embedded.Hot`, `Aouda.Abstractions`, `Aouda.Client`, `Aouda.Testing`.
  - dotnet global tool: `Aouda.Cli` with `ToolCommandName=aouda`.
  - npm package: `@aouda/client`.
- Runtime distribution entry points are implemented:
  - Embedded open/create via `AoudaEmbedded`.
  - `aouda dev` command with port/data/database/auth options.
  - Dev server host in `Aouda.Server.DevServer`.

### Planned / proposed

- ADR 0022 phase-3/phase-4 vision remains planned from this snapshot:
  - Cloud ephemeral provisioning path.
  - Hybrid unified auto mode (`embedded/server/cloud`) as a stable public API contract.
- Distribution simplification work is planned:
  - BL-032 to remove engine DLL exposure from `Aouda.Abstractions` package.
- Broader publish automation and release governance are still mostly process-level, not productized pipeline APIs.

### Reserved / not yet wired

- Current code snapshot does not expose a public `Aouda.CreateClient()` + `AoudaMode` auto-resolver surface in `src/Aouda.Embedded`.
- No Docker image distribution flow is implemented in this repo snapshot.
- No first-class HTTP API for artifact publishing/release management exists.

Implementation drift note:
- Several P11 report docs describe B.3/D.2 outcomes, but code symbols in this snapshot are authoritative and do not contain those public surfaces. This document follows code-and-tests truth per documentation policy.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P4 | `P4-Integration-Distribution-Tasks.md` (Epic A/B core complete) | Server distribution path, client tiering direction, CLI/server integration baseline | Some P4-era distribution assumptions superseded by later packaging split and naming | Ongoing via P8/P11 follow-ups |
| P8 | `BL031-AoudaClient-NuGetPackage-And-Docs.md` | Single-package NuGet strategy for Abstractions + packaging/readme approach | Task doc marked "implementation not started" in file header, later effectively executed via subsequent phases | BL-031 remains in backlog index history |
| P11 | `P11-UnifiedDistribution-Tasks.md` + Epic C/E reports | BSL/MIT foundation files and package metadata wiring; package README improvements; `aouda dev` command and dev host path | Unified auto client mode and auto-start behavior not visible in current code snapshot | BL-032 (BL-033 closed 2026-04-03) |
| P13 | `P13-Testing-Package-Tasks.md` | `Aouda.Testing` as MIT package for consumer integration testing distribution | Additional DX refinements remain future work | P13 follow-up items in phase docs |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Root license artifacts (`LICENSE`, `LICENSE-MIT`) | Yes | No | No | Root license files + P11 C1 report | Canonical legal text exists in-repo |
| BSL metadata for engine-side distributables | Yes | No | No | `Aouda.Embedded.csproj`, `Aouda.Embedded.Hot.csproj`, `Aouda.Server.csproj` | Uses package license file wiring pattern |
| MIT metadata for client/tooling packages | Yes | No | No | `Aouda.Abstractions.csproj`, `Aouda.Client.csproj`, `Aouda.Cli.csproj`, `Aouda.Testing.csproj`, `aouda-client-ts/package.json` | Mixed NuGet license expression + npm license field |
| NuGet package distribution for embedded/server clients | Yes | No | No | csproj `PackageId` + README docs + task reports | Pre-release versioning, packaging operationally present |
| dotnet global tool distribution (`aouda`) | Yes | No | No | `Aouda.Cli.csproj`, `Program.cs` | `PackAsTool=true`, `ToolCommandName=aouda` |
| npm distribution for TypeScript client | Yes | No | No | `aouda-client-ts/package.json` | Build outputs mapped through `dist` exports |
| `aouda dev` runtime distribution entry point | Yes | No | No | `Program.cs`, `DevCommand.cs`, `DevServerHost.cs`, CLI tests | Provides local server for polyglot use |
| Embedded zero-setup open/create distribution path | Yes | No | No | `AoudaEmbedded.cs`, embedded tests | Supports ephemeral + persistent open patterns |
| Unified auto mode (`CreateClient`, `AoudaMode`, auto-start dev server) | No | No | Yes | Symbol absence in `src/Aouda.Embedded` | Docs/reports reference exists, code path not present now |
| Clean client package without engine DLL payload | No | Yes | No | `Aouda.Abstractions.csproj` embeds engine DLLs + BL-032 | Shipped but intentionally marked for follow-up |
| Container image distribution | No | No | Yes | No Dockerfile/image flow in repo | Planned/possible future route, not shipped |

## 2.7 Core concepts and mental model

- Artifact class:
  - **Engine-inclusive** package/tool: ships runtime engine behavior (`Aouda.Embedded`, `Aouda.Embedded.Hot`, server-hosted flows).
  - **Thin client/tooling** package: API/transport/testing convenience (`Aouda.Abstractions`, `Aouda.Client`, `@aouda/client`, `Aouda.Testing`, `Aouda.Cli`).
- License posture:
  - **BSL-oriented** for core engine/server surfaces.
  - **MIT** for client/tooling adoption surfaces.
- Distribution layer:
  - **Build artifact metadata** in project/package manifests.
  - **Runtime bootstrap surfaces** (embedded open/create, `aouda dev`, SDK constructors).
- Packaging contract:
  - Metadata fields (`PackageId`, `Version`, `PackageLicense*`, readme, tool command).
  - Included files (`README`, license files, DLL payloads).
  - Consumer expectations (single package vs transitive dependencies).

Invariants:
- Licensing intent must map to actual package metadata, not only ADR prose.
- Runtime entry points (`AoudaEmbedded`, `aouda dev`, SDK constructors) are part of distribution quality.
- Code/test evidence overrides stale or aspirational status claims in planning/report docs.

## 2.8 How Aouda implements it

High-level implementation path:

1. ADR and phase tasks define distribution/licensing intent.
2. Root license files provide canonical legal text.
3. Project files encode package/tool metadata and payload behavior.
4. CLI and embedded entry points expose runnable distribution channels.
5. Tests validate core install/run contracts for key flows.

Key implementation anchors:

- Licensing and package metadata:
  - `src/Aouda.Embedded/Aouda.Embedded.csproj`
  - `src/Aouda.Embedded.Hot/Aouda.Embedded.Hot.csproj`
  - `src/Aouda.Abstractions/Aouda.Abstractions.csproj`
  - `src/Aouda.Client/Aouda.Client.csproj`
  - `src/Aouda.Cli/Aouda.Cli.csproj`
  - `src/Aouda.Testing/Aouda.Testing.csproj`
  - `aouda-client-ts/package.json`
- Runtime entry points:
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.Cli/Commands/DevCommand.cs`
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Embedded/AoudaEmbedded.cs`
  - `src/Aouda.Embedded/Configuration/AoudaOptionsEnvOverlay.cs`
- Maintainer packaging guide:
  - `docs/dev/Client-NuGet-Packaging.md`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: BSL pack metadata for `Aouda.Embedded`

1. `Aouda.Embedded.csproj` sets package identity (`PackageId`, `Version`, tags, readme, license file).
2. Build target copies root `LICENSE` into local `LICENSE-Pack.txt` before pack.
3. Pack item includes `LICENSE-Pack.txt` and `README.md` at package root.
4. Pack target embeds engine/protocol DLLs into `lib/net8.0/`.
5. Resulting nupkg carries both legal metadata and runtime payload in one artifact.

Primary anchors:
- `src/Aouda.Embedded/Aouda.Embedded.csproj`
- `LICENSE`

Primary proving tests/evidence:
- P11 C1 report verification commands.

### Walk-through B: `aouda dev` command to active HTTP server

1. CLI parses `dev` subcommand and options (`--port`, `--data`, `--database`, `--auth`) in `Program.cs`.
2. CLI constructs `DevServerOptions` and dispatches to `DevCommand.RunAsync`.
3. `DevCommand` forwards to `DevServerHost.RunAsync`.
4. `DevServerHost` builds ASP.NET app, registers Aouda server services, applies dev overrides:
   - temp or persistent path
   - DB creation seed
   - CORS allow-all
5. App starts, optional auth bootstrap runs, startup banner prints, then waits for shutdown.

Primary anchors:
- `src/Aouda.Cli/Program.cs`
- `src/Aouda.Cli/Commands/DevCommand.cs`
- `src/Aouda.Server/DevServer/DevServerHost.cs`

Primary proving tests:
- `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`

### Walk-through C: Embedded open with env overlay

1. Caller invokes `AoudaEmbedded.OpenDatabaseAsync()` with no options.
2. Method creates default `AoudaEmbeddedOptions`.
3. `AoudaOptionsEnvOverlay` applies `AOUDA_DATABASE` and `AOUDA_DATA_PATH`.
4. `AoudaEmbedded` maps to low-level `EmbeddedOptions` and calls `CreateAsync`.
5. `CreateAsync` chooses temp path when no data path was provided and opens engine.
6. Returned `IAoudaDatabase` gives stable in-process API surface.

Primary anchors:
- `src/Aouda.Embedded/AoudaEmbedded.cs`
- `src/Aouda.Embedded/AoudaEmbeddedOptions.cs`
- `src/Aouda.Embedded/Configuration/AoudaOptionsEnvOverlay.cs`

Primary proving tests:
- `tests/Aouda.Embedded.Tests/OpenDatabaseTests.cs`
- `tests/Aouda.Embedded.Tests/AoudaFactoryTests.cs`

### Walk-through D: TypeScript package consumption contract

1. Consumer installs `@aouda/client` from npm.
2. Node resolves package entry points from `package.json` `exports`.
3. Client is created via `createAoudaClient({ serverUrl, database })`.
4. Query/table/admin APIs execute against Aouda HTTP server.

Primary anchors:
- `aouda-client-ts/package.json`
- `aouda-client-ts/README.md`

Primary proving tests:
- `aouda-client-ts/tests/*` (cross-repo evidence from existing task/docs).

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Can core engine be protected while clients stay frictionless? | Often all-MIT or fully proprietary split | BSL-oriented engine/server + MIT clients/tooling strategy | Better balance of adoption and commercial protection |
| Is local server bootstrap a first-class developer path? | Often requires docker-compose or full deployment stack | `aouda dev` as packaged dotnet tool path | Faster local onboarding and AI-agent ergonomics |
| Is embedded + server + client distribution documented together? | Usually fragmented by repo/package | Single domain doc spanning runtime + legal + artifact matrices | Less confusion during architecture and compliance review |
| Can test-server tooling be consumed as package, not ad-hoc scripts? | Often internal-only test host setup | `Aouda.Testing` package with framework adapters | Better CI ergonomics for consumer app teams |
| Are known packaging debts explicitly tracked? | Frequently hidden until migration pain | BL-032 linked; BL-033 closed (embedded re-open persistence) | Safer planning for dependency footprint and persistence expectations |

## 2.10 Configuration and settings reference (complete surface)

This section includes both runtime distribution settings and package/build metadata settings that define distributed behavior.

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `PackageId` | string | per project | non-empty | packable `.csproj` | Artifact identity on NuGet |
| `Version` | string | `0.1.0` (current) | semver-like | packable `.csproj` | Overridable at pack time |
| `PackageLicenseExpression` | string | varies | SPDX expression | `.csproj` | Used by MIT packages (`Aouda.Abstractions`, `Aouda.Client`, `Aouda.Cli`, `Aouda.Testing`) |
| `PackageLicenseFile` | string | varies | package-relative file | `.csproj` | Used by BSL-oriented packages (`Aouda.Embedded`, `Aouda.Embedded.Hot`, server metadata) |
| `PackageReadmeFile` | string | varies | package-relative file | `.csproj` | Enables NuGet package README |
| `PackAsTool` | bool | `true` only in CLI | true/false | `Aouda.Cli.csproj` | Marks package as dotnet global tool |
| `ToolCommandName` | string | `aouda` | command name | `Aouda.Cli.csproj` | Runtime command exposed to users |
| `AOUDA_DATA_PATH` | string | unset | path | env vars (embedded) | Drives embedded persistence path for no-args open |
| `AOUDA_DATABASE` | string | `"default"` logical fallback | non-empty | env vars (embedded + CLI schema flows) | DB naming overlay |
| `AOUDA_SERVER` / `AOUDA_URL` | string | unset | URL | CLI schema flows | Used by schema command context |
| `aouda start --port` | int | `5433` | valid port | CLI args | Server listen port |
| `aouda start --data-dir` | string? | from config | path | CLI args | Persistent data directory |
| App auth | HTTP | — | create-database API | Not CLI | `mk_anon_` / `mk_svc_` in response |
| npm `license` | string | `"MIT"` | SPDX | `aouda-client-ts/package.json` | Package-level legal declaration |
| npm `engines.node` | string | `>=20` | semver range | `aouda-client-ts/package.json` | Distribution runtime constraint |

Configuration precedence and operational notes:

- Embedded open precedence:
  - Explicit `AoudaEmbeddedOptions` argument wins.
  - No-args open applies environment overlay (`AOUDA_*`).
- CLI dev precedence:
  - Command-line options define runtime for each invocation.
- Packaging metadata precedence:
  - `.csproj` values are baseline.
  - CI/release command-line pack properties can override version and related fields.
- Dynamic vs restart-required:
  - Package metadata is build-time only.
  - `aouda dev` runtime options are process-start scoped (restart to change).
- Deprecated/reserved:
  - Legacy "single package hides all engine internals from clients" is not yet true for Abstractions; BL-032 tracks cleanup.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET examples

```csharp
// Embedded package (in-process)
await using IAoudaDatabase db = await AoudaEmbedded.OpenDatabaseAsync(new AoudaEmbeddedOptions
{
    DataPath = "./data",
    EnableWal = true
});

await db.GetTable("orders").InsertAsync(new Dictionary<string, object?>
{
    ["id"] = 1L,
    ["total"] = 99.5
});
```

Expected result: database opens locally and writes are persisted when `DataPath` is set.

Common mistake: assuming a unified `Aouda.CreateClient()` symbol exists in this snapshot; use `AoudaEmbedded` or `AoudaClient` directly.

```csharp
// Remote .NET client package
using var client = new AoudaClient("http://localhost:5433", "default");
var rows = await client.GetTable("orders").Where("total", "gte", 50).ToListAsync();
```

Expected result: remote query executes through server HTTP API.

Common mistake: using `Aouda.Abstractions` directly in app code instead of installing `Aouda.Client` or `Aouda.Embedded`.

### TypeScript example

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "default",
});

const result = await client.table("orders")
  .where("total", ">", 50)
  .limit(10)
  .execute();
```

Expected result: `result.rows` returns matching rows from server.

Common mistake: expecting embedded in-process mode from TypeScript package (current TS package is server-client only).

### HTTP / CLI examples

```bash
# Install and run CLI tool
dotnet tool install -g Aouda.Cli
aouda start --port 5433 --data-dir "./data"
```

```http
GET /health
```

Expected result: dev server prints banner and health endpoint returns `200`.

Common mistake: assuming schema commands can run without server/database context.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Install embedded package | NuGet (`Aouda.Embedded`) + `AoudaEmbedded` | N/A | N/A | Implemented | In-process only |
| Install remote .NET client | NuGet (`Aouda.Client`) + `AoudaClient` | N/A | N/A | Implemented | Depends on server URL availability |
| Install TS client package | N/A | npm `@aouda/client` + `createAoudaClient` | N/A | Implemented | Node 20+ |
| Start local server | `aouda` tool command path from .NET ecosystem | via process execution | Server HTTP endpoints | Implemented | `aouda start` |
| In-process test server package | `Aouda.Testing` (`AoudaTestServer`) | N/A | Test-hosted HTTP | Implemented | MIT tool package |
| Unified auto client mode selection | No stable public API in current snapshot | N/A | N/A | Missing | Reports mention prior work, symbols absent now |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Unified `CreateClient` auto mode | No public `Aouda.CreateClient` + mode enum in current `src/Aouda.Embedded` | Use explicit `AoudaEmbedded` or `AoudaClient` constructors | P11 follow-up / reconciliation work | High |
| Lightweight client package without engine internals | `Aouda.Abstractions` currently embeds multiple engine DLLs | Accept current package, monitor footprint | `docs/BACKLOG.md` BL-032 | High |
| First-class Docker distribution | No Docker image/build pipeline | Run via dotnet CLI or server project | Future distribution tasks | Medium |
| Formal release/publish automation contract | No documented canonical CI publish workflow in this functionality doc yet | Manual `dotnet pack` / `dotnet nuget push` / npm publish practices | Future release engineering tasks | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run local development (server + polyglot clients)

When to use:
- You need a local HTTP Aouda endpoint for .NET and TypeScript clients.

Steps:
1. Install CLI tool: `dotnet tool install -g Aouda.Cli`
2. Start server: `aouda start --port 5433 --data-dir "./data"`
3. Run either .NET `AoudaClient` or TS `createAoudaClient` against `http://localhost:5433`.

Expected result checks:
- `GET /health` returns `200`.
- CLI banner shows URL/database/mode.
- Test insert/query succeeds from at least one SDK.

### Scenario 2: Packaging and local NuGet feed consumption

When to use:
- You need to validate package shape before publishing.

Steps:
1. Pack Abstractions: `dotnet pack src/Aouda.Abstractions/Aouda.Abstractions.csproj -c Release`
2. (Optional) Pack Client similarly.
3. Copy nupkg files to a local folder feed.
4. Add source: `dotnet nuget add source <path> --name LocalAouda`
5. Reference package in scratch project and run basic client calls.

Expected result checks:
- nupkg exists with expected version.
- Package README and XML docs are included.
- App builds/runs without missing assembly errors.

### Scenario 3: Auth-enabled local dev bootstrap for app workflows

When to use:
- You need development-time app-auth keys from startup.

Steps:
1. Run: `aouda start`; create auth-enabled database via API (see auth/setup.md)
2. Capture printed key guidance from startup output.
3. Use keys in client auth options or HTTP headers.
4. Execute signup/signin or protected route checks.

Expected result checks:
- Auth summary appears in console.
- OIDC/auth routes for database are reachable.
- Client operations succeed with proper auth credentials.

### Scenario 4: Testing-package integration in consumer app tests

When to use:
- You need in-process Aouda server lifecycle inside test runner.

Steps:
1. Add package: `Aouda.Testing`.
2. Start `AoudaTestServer` in test fixture.
3. Create SDK clients from fixture and execute integration assertions.
4. Dispose fixture and verify temp data cleanup.

Expected result checks:
- Tests run with only `dotnet test`.
- No external aouda process is required.
- Fixture cleanup succeeds.

## 2.13 Operations and observability

What to monitor first:

- Artifact integrity:
  - Pack success, manifest correctness, dependency graph shape.
- Runtime bootstrap health:
  - `aouda dev` startup success and health endpoint response.
- License metadata consistency:
  - package metadata matches intended license posture.

Recovery and restart expectations:

- CLI dev ephemeral mode uses temp path and should clean up on stop.
- Persistent dev mode retains data path across restarts.
- Package build failures are deterministic and usually metadata/path related.

Suggested tuning sequence:
1. Validate runtime entry (`aouda dev`, embedded open).
2. Validate package metadata and payload.
3. Validate consumer install and minimal query path.
4. Then optimize package footprint and publish automation.

| Question | Practical answer |
|---|---|
| How do I quickly validate local runtime distribution? | Start `aouda start` and check `GET /health` |
| Where do I verify legal metadata first? | `*.csproj` package license fields + root license files |
| Why does client package feel "too heavy"? | `Aouda.Abstractions` currently embeds engine DLLs; tracked by BL-032 |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `aouda` command not found | CLI tool not installed or tool path not on `PATH` | Install/update `Aouda.Cli` tool and verify global tools path |
| Data disappears after stop | No persistent `--data-dir` | Set explicit `--data-dir` path |
| NuGet pack license warning/error | Mismatch between `PackageLicense*` and packaged file path | Verify `PackageLicenseFile` and packed file existence |
| Local package consume fails missing dependencies | Feed missing transitive package or payload assumptions incorrect | Ensure required packages are in same feed; inspect nupkg contents |
| Expecting unified auto client API but symbol missing | Code snapshot lacks `CreateClient` surface | Use explicit `AoudaEmbedded` / `AoudaClient` paths; track follow-up |

## 2.15 Verification ledger

Last verification date (UTC): `2026-04-01` (documentation evidence audit), with implementation command evidence from phase reports (`2026-03-22` to `2026-03-31`).

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Embedded package packability and metadata | `dotnet pack src/Aouda.Embedded/Aouda.Embedded.csproj -c Release` | Pass (report evidence) | 2026-03-22 | P11 A/C reports include artifact verification |
| CLI dev command integration behavior | `dotnet test tests/Aouda.Cli.Tests --verbosity minimal` | Pass (report evidence) | 2026-03-22 | Includes `DevServerIntegrationTests` |
| Server compatibility after DevServerHost move | `dotnet test tests/Aouda.Server.Tests --verbosity minimal` | Pass (report evidence) | 2026-03-22 | Referenced in P13 report block |
| Testing package build/distribution baseline | `dotnet build src/Aouda.Testing/Aouda.Testing.csproj` | Pass (report evidence) | 2026-03-22 | P13 report indicates clean build |
| TypeScript package buildability | `npm run build` (in `aouda-client-ts`) | Pass (report evidence) | 2026-03-22 | From MIT licensing task report |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| CLI dev distribution path | `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs` | Pass (historical report evidence) | Strong | Covers startup, API access, options, banner |
| Embedded distribution open/create path | `tests/Aouda.Embedded.Tests/OpenDatabaseTests.cs`, `AoudaFactoryTests.cs`, `EmbeddedLifecycleTests.cs` | Pass with known skips in persistence area | Medium/Strong | Good for startup/runtime, persistence gap tracked |
| Package metadata stability (C# artifacts) | Build/pack command evidence in P11 reports | Pass | Medium | Mostly command-level verification rather than manifest diff tests |
| Testing package consumption | `tests/Aouda.Testing.Tests/*` | Pass (report evidence) | Medium/Strong | Validates in-process server test ergonomics |
| TypeScript package baseline | `aouda-client-ts/tests/*` + build scripts | Pass (report evidence) | Medium | Strong functional tests in TS repo, no publish-contract test matrix yet |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No automated test asserting package license metadata parity against policy matrix | Prevents silent license drift across artifacts | Add metadata snapshot test that parses generated nuspec/package.json and compares expected license mode per artifact | High |
| No CI assertion for "unified auto client mode intentionally absent/present" | Avoids doc/code drift around B.3/D.2 capability | Add symbol-presence contract test on `Aouda.Embedded` public API and fail on unexpected disappearance/appearance without doc update | Medium |
| No packaged-footprint regression test for Abstractions | BL-032 is high-impact for dependency hygiene | Add nupkg content test to track size and DLL inventory; gate on expected minimal set after BL-032 | High |
| No end-to-end release rehearsal test across NuGet + npm + tool | Distribution failures often cross artifact boundaries | Add release-candidate pipeline that packs all artifacts and runs smoke install in sample apps | Medium |

## 2.18 Known gaps and undone work

_Updated 2026-04-08 after P14/P16 completion._

### Resolved gaps

- ~~BL-032~~ — ✅ **Resolved (P14)**: extracted `Aouda.Schema.Contract` assembly; `Aouda.Abstractions` package no longer ships engine DLLs.
- ~~BL-033~~ — ✅ **Resolved (P14)**: embedded persistent-path re-open verified via `EmbeddedPersistenceTests`; shutdown flush in `CompactionWorker`.
- ~~No Docker image distribution~~ — ✅ **Resolved (P16)**: official `Dockerfile` (Alpine-based), `docker-compose.yml` (single node + Studio), `docker-compose.cluster.yml` (3-node cluster + witness + Studio). See `docs/dev/Functionality-Cloud-And-Hub.md` §4.
- ~~No CLI distribution~~ — ✅ **Resolved (P16)**: `aouda start`, `aouda stop`, schema/database subcommands. See `guides/cloud-hub.md` §3.
- ~~No Kubernetes deployment~~ — ✅ **Resolved (P16)**: Helm chart (`charts/aouda-cluster/`) with StatefulSet, headless Service, PVCs, ConfigMap. Studio and witness optional. See `docs/dev/Functionality-Cloud-And-Hub.md` §5.
- ~~Cloud/distribution phase intent from ADR 0022 partially unimplemented~~ — ✅ **Partially resolved (P16)**: Hub control plane with cloud project/cluster lifecycle, K8s operator reconciling `AoudaCluster` CRD objects. Billing/payment deferred.
- ~~TypeScript client SDK packaging~~ — ✅ **Resolved (P16 Epic H)**: `@aouda/client` now has full feature parity including aggregates, extended operators, materialized queries, columnar output, admin APIs, and MCP tools. See `docs/dev/Functionality-TypeScript-Client.md`.

### Remaining gaps

- Unified auto mode gaps:
  - Public `CreateClient`/`AoudaMode` auto-resolution surface is not visible in current code snapshot.
  - User impact: users must choose explicit embedded or server client constructors.
- Cloud billing/payment integration: deferred until commercial offering launches.
- Windows installer / MSI packaging: Docker is the primary distribution mechanism.
- `aouda backup create/list/restore` CLI subcommands: backup APIs exist but CLI wrappers not yet built.

## 2.19 References

- ADRs:
  - `docs/decisions/0022-licensing-and-distribution-strategy.md`
  - `docs/decisions/0024-testing-package.md`
- Tasks/reports:
  - `docs/tasks/P4/P4-Integration-Distribution-Tasks.md`
  - `docs/tasks/P8/BL031-AoudaClient-NuGetPackage-And-Docs.md`
  - `docs/tasks/P11/P11-UnifiedDistribution-Tasks.md`
  - `docs/tasks/P11/P11-EpicC-Task1-BSL-License-And-Repository-Setup-Report.md`
  - `docs/tasks/P11/P11-EpicC-Task2-MIT-License-Client-Packages-Report.md`
  - `docs/tasks/P11/P11-EpicE-E1-E2-Report.md`
  - `docs/tasks/P11/P11-EpicD-Task1-AoudaDev-Server-Command-Report.md`
  - `docs/tasks/P13/P13-Testing-Package-Tasks.md`
- Backlog:
  - `docs/BACKLOG.md` (BL-031, BL-032); BL-033 closed — see `docs/tasks/P14/BL-033-Embedded-Persistence-Across-Reopen.md`
- Code paths:
  - `LICENSE`, `LICENSE-MIT`
  - `src/Aouda.Embedded/Aouda.Embedded.csproj`
  - `src/Aouda.Embedded.Hot/Aouda.Embedded.Hot.csproj`
  - `src/Aouda.Abstractions/Aouda.Abstractions.csproj`
  - `src/Aouda.Client/Aouda.Client.csproj`
  - `src/Aouda.Cli/Aouda.Cli.csproj`
  - `src/Aouda.Server/Aouda.Server.csproj`
  - `src/Aouda.Testing/Aouda.Testing.csproj`
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.Cli/Commands/DevCommand.cs`
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Embedded/AoudaEmbedded.cs`
  - `src/Aouda.Embedded/Configuration/AoudaOptionsEnvOverlay.cs`
  - `aouda-client-ts/package.json`
  - `docs/dev/Client-NuGet-Packaging.md`
- Tests:
  - `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`
  - `tests/Aouda.Embedded.Tests/OpenDatabaseTests.cs`
  - `tests/Aouda.Embedded.Tests/AoudaFactoryTests.cs`
  - `tests/Aouda.Testing.Tests/*`
  - `aouda-client-ts/tests/*`

## 2.20 What is missing from this document? (meta completeness)

- This document does not include legal counsel interpretation of BSL wording; it documents implementation and declared metadata only.
- Verification ledger primarily uses command evidence from existing phase reports; this pass did not re-run all full suites in-session.
- Cross-repository publish automation (NuGet + npm release choreography) is described conceptually, not yet backed by a single canonical CI workflow document in this file.
- If/when unified auto client mode is reintroduced or finalized, sections `2.4`, `2.6`, and `2.11` require immediate update.

