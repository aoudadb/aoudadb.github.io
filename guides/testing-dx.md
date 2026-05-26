---
title: "Testing and DX"
nav_order: 16
parent: "Guides"
---

# Aouda Functionality: Testing and Developer Experience

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

Coverage phases: P7, P11, P12, P13
Primary task folders: `docs/tasks/P7/`, `docs/tasks/P11/`, `docs/tasks/P12/`, `docs/tasks/P13/`
Primary ADRs: `docs/decisions/0024-testing-package.md`, `docs/decisions/0023-authentication-and-authorization.md`, `docs/decisions/0022-licensing-and-distribution-strategy.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Auth-And-Authorization.md`, `docs/dev/Functionality-Write-Path-Durability.md`

## Start Here

If your question is "How do I test my app with Aouda now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`

If your question is "What is implemented vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.15 Verification ledger`
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Aouda treats developer testing flow as product surface, not only internal engineering process.

- User problem solved:
  - Run realistic integration tests with Aouda Auth in `dotnet test` without managing a separate `aouda start` process.
  - Keep local developer setup low-friction (embedded mode, `aouda start`, schema tooling, TypeScript/.NET SDK test flows).
  - Provide repeatable stress and benchmark infrastructure for server-level confidence.
- Operational outcomes:
  - Cleaner consumer-app CI pipelines.
  - Better parity between local test behavior and real Aouda server behavior.
  - Stronger regression signal through dedicated harness scenarios and benchmark baselines.
- Scope boundaries:
  - This domain covers testing package (`Aouda.Testing`), test harness (`aouda-test`), developer entry flows (`aouda start`, SDK/client test ergonomics), and known testing gaps.
  - It does not claim that all durability/replication scenario dependencies are fully available in server API surfaces today.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What happens with defaults in test setup? | `2.3 Defaults and zero-config behavior` |
| Which parts are shipped vs planned? | `2.4 Availability status` |
| Which phase delivered testing/DX capabilities? | `2.5 Phase coverage matrix` |
| Full capability inventory | `2.6 Capability coverage matrix` |
| How in-process test server works internally | `2.8 How Aouda implements it` |
| Every option/setting and where set | `2.10 Configuration and settings reference` |
| API and CLI surfaces (and gaps) | `2.11 API and CLI coverage reference` |
| Practical workflows | `2.12 Scenario playbooks` |
| What was actually verified recently | `2.15 Verification ledger` |
| Current limitations and deferred work | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer (.NET) | `2.11 API and CLI coverage reference`, `2.12 Scenario playbooks` |
| App developer (TypeScript) | `2.11 API and CLI coverage reference`, `2.17 Testing gaps and proposed tests` |
| CI/operator | `2.10 Configuration and settings reference`, `2.13 Operations and observability` |
| Engine contributor | `2.5 Phase coverage matrix`, `2.8 How Aouda implements it`, `2.16 Test coverage matrix` |
| SDK maintainer | `2.6 Capability coverage matrix`, `2.11 API and CLI coverage reference`, `2.18 Known gaps and undone work` |

### Source map

- Task/report evidence:
  - `docs/tasks/P13/P13-Testing-Package-Tasks.md`
  - `docs/tasks/P13/P13-Task-A1-Testing-Package.md`
  - `docs/tasks/P7/P7-StressTest-Integration-Testing-Overview.md`
  - `docs/tasks/P11/P11-Failing-Tests-Overview.md`
  - `docs/tasks/P12/P12-PreExisting-Integration-Test-Failures-Fix.md`
- Core code:
  - `src/Aouda.Testing/AoudaTestServer.cs`
  - `src/Aouda.Testing/AoudaTestServerOptions.cs`
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Server/Bootstrap/DisabledSetupModeState.cs`
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.TestHarness/Program.cs`
  - `src/Aouda.TestHarness/Configuration/TestRunConfig.cs`
- Test evidence:
  - `tests/Aouda.Testing.Tests/*`
  - `tests/Aouda.TestHarness.Tests/*`
  - `../aouda-client-ts/tests/*.test.ts`

## 2.3 Defaults and zero-config behavior

If you do nothing beyond basic package install and default options:

- `AoudaTestServer.StartAsync()` creates one database named `default`, no auth, ephemeral temp data path.
- `AoudaTestServerOptions.Port` defaults to `5433`, but this is informational under `TestServer` (no real socket binding).
- `AoudaTestServer` auto-applies disabled setup-mode state so integration tests can hit normal API routes.
- `aouda-test` defaults to running all scenario categories with `300s` duration and `10` concurrency.
- TypeScript client tests default to mocked `fetch` style in-package unit tests; no dedicated TypeScript in-process Aouda test server package exists.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `AoudaTestServerOptions.Databases` | `[new TestDatabase("default")]` | You get a ready single DB with no extra setup |
| `TestDatabase.EnableAuth` | `false` | `ServiceKey`/`AnonKey` unavailable unless explicitly enabled |
| `AoudaTestServerOptions.DataPath` | `null` | Temp directory is auto-created and deleted on dispose |
| `AoudaTestServerOptions.Port` | `5433` | Document-only under TestHost (useful for parity/config readability) |
| `AoudaTestServerOptions.ConfigureServices` | `null` | No service overrides unless caller opts in |
| `AoudaTestServerOptions.CorsAllowedOrigins` | `null` | CORS policy not injected; cross-origin requests fail |
| `aouda-test --scenario` | `all` | Full scenario category set runs by default |
| `aouda-test --duration` | `300` | Global max runtime cap in seconds |
| `aouda-test --concurrency` | `10` | Shared default client parallelism |
| `aouda-test --seed` | `42` | Deterministic baseline seed unless overridden |
| `aouda-test --baseline-file` | `baseline.json` | Standard benchmark baseline location |
| `aouda-test --report-dir` | `./reports` | Reports emitted automatically unless disabled |

## 2.4 Availability status (implementation honesty)

### Available now

- Consumer testing package:
  - `Aouda.Testing` NuGet project exists and ships in-repo API (`AoudaTestServer`, options, adapters).
  - Auth test helpers (`CreateUserAsync`, `SignInAsync`, `CreateUserHttpClientAsync`) are implemented engine-direct.
- In-process HTTP testing behavior:
  - `DevServerHost.Build(..., UseTestServer())` path is reusable and active.
  - Setup mode is bypassable for integration testing through shared `AddDisabledSetupModeForIntegrationTests()`.
- Framework adapters:
  - xUnit base fixture, NUnit fixture, MSTest helper fixture are implemented.
- End-to-end test harness:
  - `aouda-test` project exists with correctness, benchmark, stress, durability, replication, multi-db, and soak categories.
- Developer getting-started coverage:
  - `Getting-Started-Testing.md` and cross-links from `Getting-Started.md` are present.

### Planned / proposed

- ADR 0024 is still marked `Proposed` even though core P13 implementation exists.
- Broader first-class cross-language testing parity (especially TypeScript-specific in-process server utilities) remains incomplete.
- Some stress/durability scenario ambitions depend on server capabilities not fully exposed in stable public API endpoints.

### Reserved / not yet wired

- No TypeScript equivalent package to `Aouda.Testing` for one-command in-process server lifecycle in JS/TS tests.
- No dedicated public HTTP endpoint to "spawn disposable test server instances"; current model is in-process .NET host composition.
- `Aouda.TestHarness` has known scenario limitations where server features are absent (tracked in backlog).

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P7 | `P7-StressTest-Integration-Testing-Overview.md` + scenario catalog/docs | Standalone `aouda-test` harness model, scenario taxonomy, benchmark baseline model, CI reporting strategy | Some scenarios documented against not-yet-available server APIs (backup/replication variants) | `docs/BACKLOG.md` BL-023, BL-024, BL-028 |
| P11 | `P11-Failing-Tests-Overview.md` + fix reports | Broader test suite hardening and flaky/failure fixes for storage and TestHarness tests | Some residual engine-level failures remained outside narrow fix scope | Task-level follow-up docs under `docs/tasks/P11/` |
| P12 | `P12-PreExisting-Integration-Test-Failures-Fix.md` | Setup-mode integration test strategy stabilized via disabled setup-mode service replacement | Additional setup/auth interactions in external harnesses still need ongoing attention | Referenced by P12 task docs; no dedicated BL id created in this task doc |
| P13 | `P13-Testing-Package-Tasks.md`, `P13-Task-A1-Testing-Package.md`, session reports | `Aouda.Testing` package delivered (in-process server, auth helpers, adapters, tests, docs) | TS parity package and richer convenience APIs remain future work | No numbered BL created for TS parity in current backlog |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| In-process Aouda server for consumer integration tests | Yes | No | No | `AoudaTestServer.cs`, P13 task docs, `Aouda.Testing.Tests` | Core shipped |
| Auth-enabled per-database test bootstrap and keys | Yes | No | No | `AoudaTestServer.StartAsync`, auth tests | Service/anon keys + OIDC authority available |
| Fast engine-direct auth setup helpers | Yes | No | No | `CreateUserAsync`, `SignInAsync` code + tests | Avoids HTTP setup overhead |
| xUnit / NUnit / MSTest helper fixtures | Yes | No | No | Adapter source files | xUnit requires concrete class to also implement `IAsyncLifetime` |
| Setup-mode bypass for integration testing | Yes | No | No | `DisabledSetupModeState.cs`, P12 setup fix task | Shared strategy used by testing surfaces |
| Standalone stress/benchmark harness (`aouda-test`) | Yes | No | No | `src/Aouda.TestHarness/*`, P7 docs | Broad scenario catalog implemented |
| Built-in benchmark baseline compare/save workflow | Yes | No | No | `Program.cs`, benchmark classes | Exit code integration for CI |
| TypeScript in-process test server package parity | No | No | Yes | No equivalent project in `aouda-client-ts` | Current TS tests use mocked transport/unit style |
| Public promote/test-server orchestration HTTP API | No | Yes | No | No server endpoint; .NET in-process path exists | Current workaround: embed in .NET test host |
| Fully stable all-green harness test suite in current branch snapshot | No | Yes | No | Recent run shows setup-required failures in harness tests | Implementation exists; branch state can still regress |

## 2.7 Core concepts and mental model

- `Aouda.Testing`:
  - Consumer-facing .NET test utility package for in-process server lifecycle.
- `AoudaTestServer`:
  - Primary abstraction wrapping startup, auth bootstrap, clients, helpers, and teardown.
- `TestServer`:
  - ASP.NET in-memory hosting path (`UseTestServer`), no network socket requirement.
- Setup mode bypass:
  - Integration test-only DI override to avoid first-run setup middleware blocking non-setup routes.
- `Aouda.TestHarness` (`aouda-test`):
  - Externalized black-box scenario runner for stress/perf/durability categories.

Invariants:

- In-process testing server should isolate ephemeral state by default (`DataPath == temp` + cleanup on dispose).
- Auth helpers should not require bootstrapping through HTTP for setup operations.
- Test harness scenarios should execute against HTTP server behavior, not direct internal engine calls, for system-level fidelity.

## 2.8 How Aouda implements it

High-level architecture path:

1. `AoudaTestServer.StartAsync` composes `DevServerHost.Build` with `UseTestServer`.
2. Builder config applies disabled setup-mode override for integration workflows.
3. Optional per-database auth bootstrap runs and stores generated keys.
4. Test consumers use raw `HttpClient`, pre-authed `AoudaClient`, or per-user authed client helpers.
5. Disposal stops host, disposes resources, and removes ephemeral data path.

Parallel test/DX path:

1. `aouda-test` parses CLI into `TestRunConfig`.
2. Scenario registry loads category scenarios.
3. `ScenarioRunner` coordinates setup/run/cleanup and reporting.
4. Baseline store/compare emits benchmark regression outcomes for CI integration.

Key implementation anchors:

- `src/Aouda.Testing/AoudaTestServer.cs`
- `src/Aouda.Server/DevServer/DevServerHost.cs`
- `src/Aouda.Server/Bootstrap/DisabledSetupModeState.cs`
- `src/Aouda.Cli/Program.cs`
- `src/Aouda.TestHarness/Program.cs`
- `src/Aouda.TestHarness/Infrastructure/ScenarioRunner.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: `AoudaTestServer.StartAsync` end-to-end

1. Entry point: `AoudaTestServer.StartAsync(options, ct)`.
2. Validation:
   - Throws if `Databases` is empty.
   - Resolves ephemeral vs persistent data path.
3. Builder composition:
   - Calls `DevServerHost.Build(...)`.
   - Injects `UseTestServer()`.
   - Injects `AddDisabledSetupModeForIntegrationTests()`.
   - Applies optional caller `ConfigureServices`.
4. State mutations:
   - Starts app host.
   - Creates test `HttpClient`.
   - For each auth-enabled DB, links auth DB and generates/retrieves keys.
5. Observability:
   - Directly visible through returned API (key accessors, URL, `DataPath`), not via perf counters.
6. Proving tests:
   - `AoudaTestServer_BasicLifecycle.cs`
   - `AoudaTestServer_AuthEnabled.cs`
   - `AoudaTestServer_MultiDatabase.cs`

### Walk-through B: Auth helper token path (`CreateUserAsync` + `SignInAsync`)

1. Entry points:
   - `CreateUserAsync(databaseName, email, password)`
   - `SignInAsync(databaseName, email, password)`
2. Validation:
   - Resolves auth DB mapping for app DB.
   - Throws clear exception when auth is not enabled.
3. State mutations:
   - `CreateUserAsync` persists user via `UserService`.
   - `SignInAsync` verifies credentials, mints JWT with issuer from `OidcAuthority(...)`.
4. Observability:
   - Consumer sees explicit exceptions on invalid credentials or missing auth.
   - JWT shape/endpoint acceptance proven by tests.
5. Proving tests:
   - `AoudaTestServer_AuthHelpers.cs`
   - `CreateUserHttpClientAsync_TokenAcceptedByAuthProtectedEndpoint`

### Walk-through C: `aouda-test` CLI run to report artifacts

1. Entry point: `Program.Main(args)` in `src/Aouda.TestHarness/Program.cs`.
2. Validation/branching:
   - Parses scenario, duration, concurrency, baseline flags, report directory.
   - Registers scenario categories.
3. Runtime mutations:
   - Runs scenarios through `ScenarioRunner`.
   - Optionally saves baseline.
   - Optionally compares baseline; can fail with exit code `1`.
   - Writes report artifacts (`report.json`, `report.md`, `metrics.jsonl`, baseline comparison summary).
4. Observability:
   - Console summary and exit codes (`0`, `1`, `2`).
5. Proving tests:
   - `tests/Aouda.TestHarness.Tests` CLI and runner tests (current branch currently showing setup-mode-related failures in verification run).

### Walk-through D: Integration test setup-mode bypass

1. Entry point:
   - Test host builder calls `AddDisabledSetupModeForIntegrationTests()`.
2. Behavior:
   - Registers `ISetupModeState` singleton that always returns not-in-setup mode.
3. Result:
   - Middleware path that would enforce setup bootstrapping is bypassed for integration suites not testing setup flow.
4. Proving evidence:
   - P12 pre-existing integration failure fix task documentation and integration test infrastructure usage.

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Can app developers run auth integration tests without external infra? | Usually requires docker/service process wiring | `Aouda.Testing` in-process server with auth bootstrap | `dotnet test` can be self-sufficient |
| Are testing hooks separate from production host behavior? | Often separate mock server implementation | Reuses real server wiring via `DevServerHost` + TestServer | Better behavior fidelity in integration tests |
| Is setup-mode friction addressed for integration suites? | Often ad-hoc test hacks per suite | Shared setup-mode override strategy in server bootstrap namespace | Lower maintenance for integration tests |
| Is there a first-class stress/benchmark harness? | Frequently ad-hoc scripts | Dedicated `aouda-test` with scenario categories and baseline compare | Repeatable regression and reliability workflows |
| Is local DX documented across embedded/server/auth/testing in one ecosystem? | Docs often fragmented | Getting-started docs explicitly cross-link embedded, auth, testing, server CLI flows | Faster onboarding and fewer hidden assumptions |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `AoudaTestServerOptions.Databases` | `IReadOnlyList<TestDatabase>` | `[default]` | non-empty list | .NET test code | Empty list throws |
| `TestDatabase.Name` | `string` | required | non-empty expected | .NET test code | Used as app DB name |
| `TestDatabase.EnableAuth` | `bool` | `false` | `true/false` | .NET test code | Enables key generation + auth DB linkage |
| `AoudaTestServerOptions.DataPath` | `string?` | `null` | null or valid path | .NET test code | Null => ephemeral with auto-delete |
| `AoudaTestServerOptions.Port` | `int` | `5433` | int | .NET test code | Informational in TestServer mode |
| `AoudaTestServerOptions.ConfigureServices` | `Action<IServiceCollection>?` | `null` | callback or null | .NET test code | Allows service overrides in tests |
| `AoudaTestServerOptions.CorsAllowedOrigins` | `IReadOnlyList<string>?` | `null` | list of origin strings or null | .NET test code | Null disables CORS policy injection; set to allow cross-origin requests in test scenarios (e.g. `["http://localhost:3000"]`) |
| `aouda start --port` | int | `5433` | positive int | CLI | Kestrel/TestServer parity option |
| `aouda start --data` | string? | `null` | path or null | CLI | Null => ephemeral dev mode |
| `aouda start --database` | string | `default` | string | CLI | Initial dev DB |
| App auth setup | HTTP API | — | `POST /api/databases` with `auth.enabled` | Not a CLI flag | Keys returned in create-database response |
| `aouda-test --scenario` | string | `all` | category/filter | CLI | `all`, `correctness`, `benchmark`, etc. |
| `aouda-test --duration` | int | `300` | positive int | CLI | Max scenario duration seconds |
| `aouda-test --concurrency` | int | `10` | positive int | CLI | Client parallelism |
| `aouda-test --seed` | int | `42` | int | CLI | Reproducibility seed |
| `aouda-test --server-port` | int | `0` | int | CLI | `0` auto-select |
| `aouda-test --server-path` | string? | `null` | path | CLI | Server executable/dll path |
| `aouda-test --data-dir` | string? | `null` | path | CLI | Null uses temp |
| `aouda-test --verbose` | bool | `false` | flag | CLI | Verbose logging |
| `aouda-test --save-baseline` | bool | `false` | flag | CLI | Save benchmark baseline |
| `aouda-test --compare-baseline` | bool | `false` | flag | CLI | Enforce benchmark regressions |
| `aouda-test --baseline-file` | string | `baseline.json` | path | CLI | Baseline file path |
| `aouda-test --no-cleanup` | bool | `false` | flag | CLI | Keep data directory |
| `aouda-test --server-memory` | long | `0` | bytes | CLI | Server memory limit override |
| `aouda-test --report-dir` | string | `./reports` | path | CLI | Report artifact output |

Configuration precedence and operational notes:

- For test package:
  - Explicit `AoudaTestServerOptions` values override all defaults.
  - `ConfigureServices` callback runs after base service configuration and can override options/services.
- For CLI flows:
  - Command-line flags are explicit runtime truth.
  - `aouda` schema subcommands also support environment-influenced context (`--server`, `--database`, `--env`) but this is schema tooling, not test lifecycle itself.
- Dynamic vs restart-required:
  - `AoudaTestServerOptions` are applied at startup for each instance; new instance required for changes.
  - `aouda-test` flags apply per run.
- Safety-gated:
  - Setup mode exists as security default in normal server startup; test bypass requires explicit integration-testing override.
- Deprecated/reserved:
  - No deprecated test-package options currently identified.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (`Aouda.Testing`)

```csharp
await using var server = await AoudaTestServer.StartAsync(new AoudaTestServerOptions
{
    Databases = [new TestDatabase("myapp", EnableAuth: true)]
});

await server.CreateUserAsync("myapp", "alice@test.com", "Pass123!");
var token = await server.SignInAsync("myapp", "alice@test.com", "Pass123!");
var userClient = await server.CreateUserHttpClientAsync("myapp", "alice@test.com", "Pass123!");
var response = await userClient.GetAsync("/api/databases/myapp/auth/me");
response.EnsureSuccessStatusCode();
```

Expected result: user is created, valid JWT is minted, and auth-protected endpoint accepts token.

Common mistake: calling `ServiceKey()`/`CreateClient()` on a database that was not created with `EnableAuth: true`.

### TypeScript example (`@aouda/client` test-style usage)

```typescript
import { AoudaClient } from "@aouda/client";

const client = new AoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  serverAuth: { apiKey: "mk_srv_example" },
});

const mem = await client.admin.server.memory();
const tables = await client.tables.list();
await client.tables.updatePolicy("orders", { storageTemperature: "HotOnly" });
```

Expected result: server/admin and table APIs are callable from TypeScript client against running server.

Common mistake: expecting a TypeScript equivalent of `AoudaTestServer.StartAsync()`; current TS flow assumes an already-running server endpoint.

### HTTP example

```http
POST /api/auth/setup
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "ChangeMeNow!"
}
```

```http
POST /api/databases
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "name": "myapp",
  "auth": { "enabled": true }
}
```

Expected result: setup and DB creation/auth bootstrap flows become available for server-backed test/dev scenarios.

Common mistake: not accounting for setup mode; non-setup routes can return `SETUP_REQUIRED` until bootstrap or test override is applied.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Start in-process Aouda server for tests | `AoudaTestServer.StartAsync` | Missing | N/A | Implemented (.NET only) | `Aouda.Testing` package |
| Get service/anon keys for auth-enabled test DB | `ServiceKey`, `AnonKey` | Missing | N/A | Implemented (.NET only) | Works after `EnableAuth: true` |
| Create test users and JWTs quickly | `CreateUserAsync`, `SignInAsync`, `CreateUserHttpClientAsync` | Missing | Equivalent HTTP exists but slower for setup | Implemented (.NET helper path) | Engine-direct helper strategy |
| xUnit/NUnit/MSTest fixture helpers | `AoudaTestFixture`, `AoudaNUnitFixture`, `AoudaMSTestFixture` | Missing | N/A | Implemented (.NET only) | TS has normal Vitest patterns, no Aouda-specific fixture package |
| Local server dev workflow | `aouda start` CLI (.NET tool) | Consumes resulting server | Server endpoints exposed | Implemented | Supports `--auth` shortcut |
| Stress/benchmark scenario orchestration | `aouda-test` CLI | No direct TS equivalent harness | Uses Aouda HTTP APIs | Implemented (.NET harness) | TS parity not shipped |
| Client-side admin/schema testing APIs | `Aouda.Client` + .NET tests | `@aouda/client` APIs + Vitest tests | Underlying server endpoints | Implemented | Good transport/unit test coverage in TS repo |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| TypeScript in-process integration server lifecycle | No TS package equivalent to `Aouda.Testing` | Run `aouda start` externally in test scripts or call .NET helper harness | Not yet tracked as dedicated task ID | High |
| Unified cross-language fixture abstraction | No language-neutral fixture contract package | Per-language custom setup | Future DX tasks (not yet formalized) | Medium |
| Public disposable test-server orchestration endpoint | No HTTP API for creating isolated test hosts | In-process .NET composition only | Not currently planned in ADR 0024 | Low/Medium |
| Some harness scenario dependencies (backup/replication workflows) | Server endpoints/features absent for complete scenario assertions | Skip/conditional handling in scenarios | `docs/BACKLOG.md` BL-023, BL-024 | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: Fast auth integration tests in .NET (`dotnet test` only)

When to use:
- You need application-auth integration tests (OIDC/JWT/user endpoints) without external server process management.

Steps:
1. Add package reference to test project:
   - `<PackageReference Include="Aouda.Testing" Version="0.1.0" />`
2. Start server in fixture:
   - `AoudaTestServer.StartAsync(new() { Databases = [new("myapp", EnableAuth: true)] })`
3. Create user and acquire user-authenticated client with helper.
4. Run endpoint assertions against your app or Aouda routes.
5. Dispose server at fixture teardown.

Expected result checks:
- `/health` is reachable.
- `ServiceKey("myapp")` starts with `mk_svc_`.
- `CreateUserHttpClientAsync(...).GetAsync("/api/databases/myapp/auth/me")` returns `200`.

### Scenario 2: Developer local workflow (`aouda start` + SDKs)

When to use:
- Daily app development requiring a persistent local Aouda server.

Steps:
1. Start local dev server:
   - `aouda start --port 5433 --database myapp --data <persistent-path>`
2. Optionally enable auth in dev:
   - add `--auth` and capture printed keys.
3. Run .NET or TypeScript app with configured URL and credentials.
4. Validate via admin endpoints (`/health`, `/ready`, `/api/server/memory`).

Expected result checks:
- Server responds on configured port.
- SDKs can list/create/query tables.
- With auth enabled, generated keys authenticate expected endpoints.

### Scenario 3: Regression/benchmark run with `aouda-test`

When to use:
- CI/nightly reliability and performance checks across scenario categories.

Steps:
1. Baseline establishment:
   - `aouda-test --scenario benchmark --save-baseline --baseline-file baseline.json`
2. Compare run:
   - `aouda-test --scenario benchmark --compare-baseline --baseline-file baseline.json`
3. Broader functional check:
   - `aouda-test --scenario correctness,stress --duration 300 --concurrency 10`
4. Collect artifacts from report directory.

Expected result checks:
- Exit code `0` for pass.
- `report.json`, `report.md`, and `metrics.jsonl` generated.
- Baseline comparison emits no regression failures.

## 2.13 Operations and observability

What to monitor first:

- For `Aouda.Testing` suites:
  - Startup success/failure exceptions (`SETUP_REQUIRED`, auth not enabled, invalid credentials).
  - Ephemeral directory creation/cleanup behavior.
- For `aouda-test`:
  - Exit code (`0`/`1`/`2`) for CI gating.
  - Scenario pass/fail counts and failure reasons.
  - Generated report artifacts for run diagnostics.

Recovery/restart expectations:

- `AoudaTestServer` ephemeral mode should always start from clean state; persistent mode should preserve caller path.
- `aouda-test` should be rerunnable with deterministic seed and baseline file for reproducible comparisons.

Suggested tuning sequence:

1. Start with default test options and a narrow scenario category.
2. Increase concurrency and duration once baseline behavior is stable.
3. Enable baseline comparisons only after first stable benchmark capture.
4. For auth/setup issues, verify setup-mode path and test override wiring first.

| Question | Practical answer |
|---|---|
| Which single signal should CI trust first? | Process exit code from `aouda-test` or `dotnet test` |
| How to inspect scenario-level detail quickly? | `report.md` and failure reasons in JSON report |
| What indicates setup-mode interference? | `SETUP_REQUIRED` errors on non-setup endpoints |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `SETUP_REQUIRED` in integration tests | Setup mode active, override not applied | Apply `AddDisabledSetupModeForIntegrationTests()` in test host composition |
| `ServiceKey()` throws for DB | DB was started without `EnableAuth: true` | Use auth-enabled `TestDatabase` entry |
| OIDC discovery check fails | Wrong authority path assumption | Use `{OidcAuthority}/auth/.well-known/openid-configuration` |
| `aouda-test` exits `2` | Infrastructure/startup error | Validate server path/port/data dir, then rerun with `--verbose` |
| Benchmark compare fails unexpectedly | Baseline stale or different machine profile | Rebaseline intentionally and keep environment consistent |
| TS tests cannot spin in-process Aouda server | No TS equivalent of `Aouda.Testing` | Use external `aouda start` in test lifecycle or .NET bridge harness |

## 2.15 Verification ledger

Last verification date (UTC): `2026-04-01` (package tests); supplementary source audit `2026-05-22`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| `Aouda.Testing` package suite | `dotnet test tests/Aouda.Testing.Tests/Aouda.Testing.Tests.csproj --no-build --verbosity minimal` | Pass (`31/31`) | 2026-04-01 | Confirms lifecycle, auth, ephemerality, fixture paths |
| `Aouda.TestHarness` suite | `dotnet test tests/Aouda.TestHarness.Tests/Aouda.TestHarness.Tests.csproj --no-build --verbosity minimal` | Fail (multiple) | 2026-04-01 | Repeated `SETUP_REQUIRED` and CLI/assert failures in current branch; run eventually hung after failures |
| TypeScript client package test surface (documentation/code evidence) | `npm run test` (repo command; not rerun in this verification pass) | Not run in this pass | 2026-04-01 | Existing tests in `aouda-client-ts/tests/*.test.ts` provide broad API contract coverage |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| In-process server lifecycle and health | `tests/Aouda.Testing.Tests/AoudaTestServer_BasicLifecycle.cs` | Pass | Strong | Includes start/stop, base URL, zero-db validation |
| Auth bootstrap keys and OIDC authority | `AoudaTestServer_AuthEnabled.cs` | Pass | Strong | Includes success and error paths |
| Engine-direct auth helper correctness | `AoudaTestServer_AuthHelpers.cs` | Pass | Strong | Includes invalid credential and protected endpoint acceptance |
| Ephemeral/persistent data path semantics | `AoudaTestServer_Ephemerality.cs` | Pass | Strong | Confirms auto-delete and persistent-path retention |
| Multi-database test server behavior | `AoudaTestServer_MultiDatabase.cs` | Pass | Medium/Strong | Includes mixed auth/no-auth paths |
| xUnit fixture adapter contract | `AoudaTestFixture_xUnit.cs` | Pass | Medium | Validates inherited lifecycle pattern |
| Harness CLI/run orchestration | `tests/Aouda.TestHarness.Tests/*` | Failing in current run | Medium | Substantial test set exists; branch currently has setup-mode related failures |
| TS client admin/table contract calls | `../aouda-client-ts/tests/admin.test.ts`, `tables.test.ts`, others | Not run in this pass | Medium/Strong | Extensive mocked transport contract tests |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No TypeScript equivalent integration helper for in-process Aouda server | Limits parity for TS-first apps; extra CI friction | Create TS test utility package or documented harness script wrapper around `aouda start` with auto lifecycle | High |
| Harness suite currently sensitive to setup-mode state in branch validation runs | Can hide true regressions behind infra/auth gating noise | Add explicit setup-mode fixture bootstrap in harness tests and dedicated guard test asserting non-setup mode before scenario run | High |
| No explicit cross-SDK end-to-end test using same live server fixture (.NET + TS) | Protocol parity drift can go unnoticed | Add CI scenario: start server once, run targeted .NET and TS API smoke tests against same DB | Medium |
| Fixture adapter surface lacks direct compile-time xUnit interface implementation in base package | New users can misread pattern and misconfigure fixtures | Add analyzer/doc test that enforces "derived fixture must implement `IAsyncLifetime`" with sample package template | Medium |
| Verification ledger partly manual and branch-dependent | Risk of stale docs and false confidence | Add scripted doc-verification command set and CI artifact publication | Medium |

## 2.18 Known gaps and undone work

- TypeScript parity gap:
  - No TS package equivalent to `Aouda.Testing` in-process lifecycle helpers.
  - User impact: TS integration tests usually require external server process orchestration.
- Harness dependency gaps from backlog:
  - BL-023 (`BackupRestoreScenario` full API-driven path pending server backup endpoints).
  - BL-024 (replication scenario full enablement tied to server replication support parity).
  - BL-028 (graceful shutdown reliability affects some durability scenario confidence).
- Branch-state test instability:
  - Current verification run showed `SETUP_REQUIRED` failures in harness tests; indicates integration assumptions can regress and require ongoing hardening.
- ADR status mismatch:
  - ADR 0024 remains `Proposed` while significant implementation is shipped; status alignment/document governance still pending.

## 2.19 References

- ADRs:
  - `docs/decisions/0024-testing-package.md`
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0022-licensing-and-distribution-strategy.md`
  - `docs/decisions/INDEX.md`
- Task docs and reports:
  - `docs/tasks/P13/P13-Testing-Package-Tasks.md`
  - `docs/tasks/P13/P13-Task-A1-Testing-Package.md`
  - `docs/tasks/P7/P7-StressTest-Integration-Testing-Overview.md`
  - `docs/tasks/P7/P7-Scenario-Catalog.md`
  - `docs/tasks/P11/P11-Failing-Tests-Overview.md`
  - `docs/tasks/P12/P12-PreExisting-Integration-Test-Failures-Fix.md`
- Core code:
  - `src/Aouda.Testing/AoudaTestServer.cs`
  - `src/Aouda.Testing/AoudaTestServerOptions.cs`
  - `src/Aouda.Testing/TestDatabase.cs`
  - `src/Aouda.Testing/Adapters/xUnit/AoudaTestFixture.cs`
  - `src/Aouda.Testing/Adapters/NUnit/AoudaNUnitFixture.cs`
  - `src/Aouda.Testing/Adapters/MSTest/AoudaMSTestFixture.cs`
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Server/DevServer/DevServerOptions.cs`
  - `src/Aouda.Server/Bootstrap/DisabledSetupModeState.cs`
  - `src/Aouda.Cli/Program.cs`
  - `src/Aouda.TestHarness/Program.cs`
  - `src/Aouda.TestHarness/Configuration/TestRunConfig.cs`
  - `src/Aouda.TestHarness/README.md`
- Test code:
  - `tests/Aouda.Testing.Tests/*.cs`
  - `tests/Aouda.TestHarness.Tests/*.cs`
  - `../aouda-client-ts/tests/*.test.ts`
- Related docs:
  - `docs/dev/Getting-Started.md`
  - `docs/dev/Getting-Started-Testing.md`
  - `docs/dev/Getting-Started-Auth.md`
  - `docs/dev/Functionality-Overview.md`
  - `docs/BACKLOG.md`

## 2.20 What is missing from this document? (meta completeness)

- This document does not include a full per-scenario benchmark number catalog from historical runs; it focuses on capability and current verification evidence.
- TypeScript-side live integration verification commands were not executed in this update pass; TS coverage references are based on repo tests and scripts.
- If a TS in-process testing package is introduced, sections `2.10`, `2.11`, `2.12`, and `2.18` must be updated immediately.
