---
title: "AI Agents"
nav_order: 6
has_children: true
---

# Aouda Functionality: AI-Native Usage Model

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-04-08

Coverage phases: P12, P14
Primary task folders: `docs/tasks/P12/`, `docs/tasks/P14/`
Primary ADRs: `docs/decisions/0017-ai-native-interface.md`, `docs/decisions/0022-licensing-and-distribution-strategy.md`, `docs/decisions/0023-authentication-and-authorization.md`, `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Auth-And-Authorization.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How should an AI agent use Aouda today?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`

If your question is "What is implemented vs planned?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

The AI-native usage model exists to make Aouda practical for agent-driven software work, where an AI assistant needs to:
- stand up a working database quickly,
- connect safely without DBA-level setup,
- infer or read schema with minimal friction,
- recover from errors using machine-readable hints,
- evolve to stricter authorization without changing every app path.

User outcomes:
- Fast "first successful request" for local agents (`aouda dev`, schema-on-write, simple HTTP/SDK paths).
- Explicit connection and identity model for AI-generated apps (API key gate + user JWT).
- Strong authorization modes (`jwt-claim`, `auth-db-pls`, `auth-db-rls`) that can be introduced incrementally.
- Predictable error contracts (`error`, `message`, `suggestion`, `requestId`) suitable for retry/fix loops.

Scope boundaries:
- This document describes shipped AI-relevant usage surfaces in Aouda server/SDK/CLI.
- It does not treat ADR 0017 intent (full MCP server + natural-language query stack) as shipped unless code/tests exist.
- It does not claim managed cloud ephemeral provisioning as currently available in this repository.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What happens with zero setup? | `2.3 Defaults and zero-config behavior` |
| What is available now vs planned/reserved? | `2.4 Availability status` |
| Which phases delivered current AI-native surfaces? | `2.5 Phase coverage matrix` |
| Which capabilities are complete, partial, or missing? | `2.6 Capability coverage matrix` |
| Core mental model for agent usage | `2.7 Core concepts and mental model` |
| Runtime flow and enforcement internals | `2.8 How Aouda implements it` |
| Full settings/config surface | `2.10 Configuration and settings reference` |
| API surface and explicit gaps | `2.11 API and CLI coverage reference` |
| Practical rollout recipes | `2.12 Scenario playbooks` |
| Operational monitoring and incident handling | `2.13`, `2.14` |
| What remains undone | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| AI app builder | `2.3`, `2.11`, `2.12` |
| Backend/platform engineer | `2.7`, `2.8`, `2.10`, `2.13` |
| SDK maintainer | `2.11`, `2.16`, `2.17` |
| Engine/security maintainer | `2.5`, `2.6`, `2.8.1`, `2.19` |

### Source map

- Phase/task/report evidence:
  - `docs/tasks/P12/P12-TwoLayerAuth-Tasks.md`
  - `docs/tasks/P12/P12-TwoLayer-S1-ApiKeyInfrastructure-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S2-MiddlewareAndAuthorization-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S4-DocumentationAndDX-Report.md`
  - `docs/tasks/P14/P14-ADRA-Tasks.md`
  - `docs/tasks/P14/P14-TaskS6-TypeScriptClientWrappers.md`
  - `docs/tasks/P14/P14-TaskS7-GettingStartedAuthRewrite.md`
- Design references:
  - `docs/decisions/0017-ai-native-interface.md` (proposed; intent-level)
  - `docs/decisions/0022-licensing-and-distribution-strategy.md` (draft; supersedes ADR 0017 licensing section)
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
- Core runtime/code evidence:
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Server/DevServer/DevServerOptions.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
  - `src/Aouda.Server/Auth/AuthErrorResponses.cs`
  - `src/Aouda.Protocol/ErrorCodes.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Engine.Auth/Adra/AdraResolutionService.cs`
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
- SDK evidence:
  - `.NET`: `src/Aouda.Client/Auth/AppAuthOptions.cs`, `src/Aouda.Client/Auth/ServerAuthOptions.cs`
  - TypeScript: `../aouda-client-ts/src/client.ts`, `../aouda-client-ts/src/auth/auth-types.ts`, `../aouda-client-ts/src/auth/auth-client.ts`, `../aouda-client-ts/src/types.ts`
- Test evidence:
  - `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`
  - `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`
  - `../aouda-client-ts/tests/auth-client.test.ts`
  - `../aouda-client-ts/tests/auth-handler.test.ts`
  - `../aouda-client-ts/tests/auth-integration.test.ts`

## 2.3 Defaults and zero-config behavior

If you do nothing beyond starting local dev:

- `aouda dev` starts with:
  - port `5433`,
  - database `default`,
  - ephemeral mode when `DataPath` is omitted,
  - schema inference enabled.
- `aouda dev --auth` keeps the same defaults and additionally:
  - ensures app auth is enabled,
  - links/creates app auth DB,
  - prints generated `anon` and `service_role` keys on first creation.
- HTTP database creation with `{ "auth": { "enabled": true } }`:
  - links to existing single app auth DB, or
  - auto-creates default app auth DB if none exists, or
  - returns explicit error if multiple auth DBs exist and none is specified.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `DevServerOptions.Port` | `5433` | Predictable local endpoint for agent bootstrapping |
| `DevServerOptions.DatabaseName` | `default` | Immediate target DB without extra setup |
| `DevServerOptions.DataPath` | `null` | Ephemeral local run for quick experiments |
| `DevServerOptions.EnableAuth` | `false` | Auth is opt-in in dev mode unless explicitly enabled |
| `TokenOptions.AccessTokenLifetime` | `15m` | Short-lived user access tokens |
| `TokenOptions.RefreshTokenLifetime` | `30d` | Long-lived sessions for app flows |
| `TokenOptions.Issuer` | `"aouda"` | Default JWT issuer baseline |
| `AuthenticationMiddlewareOptions.ValidationMode` | `Hybrid` | Signature + revocation checking by default |
| `PasswordPolicy` | Min `8`, Max `128` | NIST-aligned baseline policy |
| App auth endpoint gate | API key required | Prevents unauthenticated direct auth route calls |
| Table `authMode` | `jwt-claim` | Existing behavior unless advanced modes are enabled |

## 2.4 Availability status (implementation honesty)

### Available now

- Agent-friendly local bootstrap:
  - `aouda dev` and `aouda dev --auth` with parseable key output and quick-start hints.
- Auto-generated connection keys on auth-enabled DB creation:
  - `anon` and `service_role` keys returned once.
- Two-layer auth runtime:
  - API key connection gate for app auth endpoints,
  - user JWT identity/session flow.
- Service-key user-context forwarding:
  - `X-User-Token` support with strict validation/revocation checks.
- ADRA authorization modes in table metadata and enforcement:
  - `jwt-claim`, `auth-db-pls`, `auth-db-rls`.
- TypeScript client wrappers for ADRA admin operations:
  - partition grants and RLS resolver CRUD wrappers.
- Structured auth errors with machine-usable fields:
  - `error`, `message`, `suggestion`, optional `detail`, optional `requestId`.

### Planned / proposed

- Full MCP server surface described in ADR 0017 (`aouda_create_database`, `aouda_query`, auth tools, schema resources).
- Natural-language query pipeline and validation/explain flow from ADR 0017.
- Broader cross-SDK parity for all auth/admin helper wrappers (especially .NET convenience wrappers for ADRA admin surfaces).
- Cloud ephemeral instance provisioning model in ADR 0017/ADR 0022 distribution direction.

### Reserved / not yet wired

- ADR 0017 `mcpTool` and `docs` fields in auth errors are not part of current runtime payload shape.
- Dedicated first-class MCP package/runtime is not present in this repository (`**/*mcp*` file search returns no implementation files).
- Natural-language query endpoint/tooling described in ADR 0017 is not wired as a public API in server/client code.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P12 | `P12-TwoLayerAuth-Tasks.md`, S1/S2/S4 reports | Two-layer auth model, API key gate, `X-User-Token`, generated app auth keys, `aouda dev --auth` UX, auth docs/protocol updates | MCP auth tools and richer AI error payload fields were tracked but not delivered as first-class runtime surfaces | `docs/BACKLOG.md` |
| P14 | `P14-ADRA-Tasks.md`, S6/S7 task docs, ADR 0025 | ADRA table auth modes, dynamic grant/resolver model, TS client wrappers for partition grants + RLS resolvers, usage guidance updates | Wider SDK helper parity and extended enterprise identity scenarios remain future work | `docs/BACKLOG.md` |
| ADR track (non-shipped intent) | ADR 0017 + ADR 0022 | Product direction for AI-native interface and distribution model | MCP server package, NL query, cloud ephemeral workflow not shipped in current codebase | `docs/BACKLOG.md` |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| One-command local dev bootstrap | Yes | No | No | `DevServerHost.cs`, `DevServerIntegrationTests.cs` | Includes banner + schema-on-write mode |
| Auth-enabled local bootstrap (`--auth`) | Yes | No | No | `DevServerHost.cs`, `DevServerOptions.cs`, CLI tests | Prints generated keys or key-prefix fallback guidance |
| Auto-link/create auth DB during DB create | Yes | No | No | `DatabasesController.cs` | Handles 0/1/many auth DB shorthand rules |
| Two-layer app auth gate | Yes | No | No | `AuthenticationMiddleware.cs`, middleware integration tests | App auth endpoints require API key layer |
| Service key + `X-User-Token` user-context | Yes | No | No | `AuthenticationMiddleware.cs`, integration tests | Validates JWT and revocation; non-service keys ignore header |
| ADRA auth modes in table schema | Yes | No | No | `TableMessages.cs`, PLS integration tests | `authMode`, `permissionDimension`, `rlsResolverName` exposed |
| TypeScript ADRA admin wrappers | Yes | No | No | `auth-client.ts`, TS auth tests | Partition grants and resolver wrappers available |
| .NET ADRA admin convenience wrappers | No | Yes | No | `.NET` auth option/client surfaces | HTTP path possible; typed helpers not equivalent to TS |
| MCP server/tooling package | No | No | Yes | `docs/decisions/0017-ai-native-interface.md`, code search | Direction documented; implementation absent |
| Natural-language query surface | No | No | Yes | ADR 0017 intent; no runtime endpoints | Requires translation + validation pipeline not present |
| AI-enriched error payload (`mcpTool`, `docs`) | No | Yes | No | `AuthErrorResponses.cs` | `suggestion` exists; `mcpTool/docs` fields not emitted |

## 2.7 Core concepts and mental model

- AI-native in current Aouda means "low-friction operational surfaces" rather than "LLM magic endpoint":
  - fast bootstrap,
  - explicit auth defaults,
  - machine-readable errors,
  - predictable schema and policy APIs.
- Layered auth model for generated apps:
  - Layer 1: API key (connection gate),
  - Layer 2: user JWT/session identity.
- Progressive authorization maturity:
  - start with `jwt-claim`,
  - move to `auth-db-pls` for dynamic partition grants,
  - move to `auth-db-rls` for row-level policy.
- Agent-safe failure model:
  - stable error code + suggestion allow deterministic retries/fixes.
- SDK behavior:
  - auth handler starts with key/token, upgrades to user JWT after sign-in where applicable.

Invariants:
- App auth routes do not accept missing API key in app-auth scope.
- `X-User-Token` only affects service-key requests.
- ADRA metadata fields must satisfy mode-specific requirements.
- Missing/invalid policy context fails closed.

## 2.8 How Aouda implements it

High-level runtime path:

1. Bootstrap: `aouda dev` (or HTTP DB create) starts DB and optional auth linkage.
2. Connection: client sends bearer (API key or JWT) to middleware.
3. Middleware:
   - determines scope (`ServerAuth`, `AppAuth`, `AppAdmin`, `Data`),
   - enforces app-auth API key rule,
   - validates API key/JWT and revocation/session mode,
   - handles service-key impersonation via `X-User-Token`.
4. Authorization:
   - table mode determines claim-based or ADRA-resolved policy path.
5. Response:
   - structured error payload on failure,
   - standard protocol payloads on success.

Implementation anchors:
- Bootstrap and key-print UX: `src/Aouda.Server/DevServer/DevServerHost.cs`
- Auth DB linking and generated keys: `src/Aouda.Server/Controllers/DatabasesController.cs`
- Auth scope and validation pipeline: `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- Error contract: `src/Aouda.Server/Auth/AuthErrorResponses.cs`, `src/Aouda.Protocol/ErrorCodes.cs`
- ADRA mode metadata and DTOs: `src/Aouda.Protocol/Schema/TableMessages.cs`
- TS wrappers and options: `../aouda-client-ts/src/auth/auth-client.ts`, `../aouda-client-ts/src/auth/auth-types.ts`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Local agent bootstrap with auth

1. Agent runs `aouda dev --auth`.
2. `DevServerHost.RunAsync()` starts app and calls `EnsureAppAuthEnabledAsync(...)`.
3. Host resolves/creates app auth DB and links app DB.
4. If keys are newly generated, host prints `Anon key` and `Service role key`; if not, prints key prefixes + regeneration hint.

Primary evidence:
- `src/Aouda.Server/DevServer/DevServerHost.cs`
- `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`

### Walk-through B: App auth endpoint guard path

1. Request enters `AuthenticationMiddleware`.
2. Scope resolves to `AppAuth` for `/api/databases/{db}/auth/*`.
3. Middleware requires bearer API key shape (`mk_...`) before allowing route.
4. Missing bearer or JWT bearer yields `AUTH_API_KEY_REQUIRED` with remediation suggestion.

Primary evidence:
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `src/Aouda.Server/Auth/AuthErrorResponses.cs`
- `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs`

### Walk-through C: Service key with `X-User-Token`

1. Primary bearer validates as service-level key.
2. Middleware checks `X-User-Token`; if present, validates it as JWT in linked auth DB.
3. On success, middleware replaces principal and sets `EffectiveUserTokenItemKey` for downstream cache isolation.
4. On failure, middleware returns 401 with explicit `X-User-Token` guidance.

Primary evidence:
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs`
- `tests/Aouda.Engine.Auth.Tests/Adra/AdraPermissionMiddlewareTests.cs`

### Walk-through D: ADRA fan-out query on `auth-db-pls`

1. Table includes `authMode = auth-db-pls` and `permissionDimension`.
2. Request principal resolves grants for the dimension.
3. Enforcer constrains query to granted partitions and blocks ungranted keys.
4. Result set contains only rows from authorized partitions.

Primary evidence:
- `src/Aouda.Protocol/Schema/TableMessages.cs`
- `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
- `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| How quickly can an agent start a real DB? | Multi-step infra/bootstrap | `aouda dev` with default DB and schema inference | Faster first successful action |
| How do auth defaults work for generated apps? | Inconsistent app-specific patterns | Built-in two-layer auth + generated anon/service keys | Lower security misconfiguration risk |
| Can service backends keep user-context enforcement? | Often custom proxy logic | Native service key + `X-User-Token` flow | Easier secure backend mediation |
| Can authorization evolve beyond fixed JWT claims? | Usually requires external policy service | ADRA (`auth-db-pls` + `auth-db-rls`) in-engine | Dynamic permissions without fat JWTs |
| Are errors machine-actionable? | Generic text-only failures | Stable error codes + suggestion + request id | Better agent retry/correction loops |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `DevServerOptions.Port` | int | `5433` | positive | CLI `aouda dev` | Local dev endpoint |
| `DevServerOptions.DataPath` | string? | `null` | path or null | CLI `aouda dev --data` | `null` => ephemeral |
| `DevServerOptions.DatabaseName` | string | `default` | non-empty | CLI `aouda dev --database` | Auto-created DB |
| `DevServerOptions.EnableAuth` | bool | `false` | `true/false` | CLI `aouda dev --auth` | Enables app-auth bootstrap and key guidance |
| `TokenOptions.AccessTokenLifetime` | timespan | `15m` | positive | Auth engine options | Access JWT lifetime |
| `TokenOptions.RefreshTokenLifetime` | timespan | `30d` | positive | Auth engine options | Refresh token lifetime |
| `TokenOptions.Issuer` | string | `"aouda"` | non-empty | Auth engine options | JWT issuer |
| `AuthenticationMiddlewareOptions.ValidationMode` | enum | `Hybrid` | `SignatureOnly`, `Hybrid`, `Stateful` | Middleware options | Signature-only vs revocation/session enforcement |
| `PasswordPolicy.MinLength` | int | `8` | `>=1` | Auth engine options | Password minimum length |
| `PasswordPolicy.MaxLength` | int | `128` | `>= MinLength` | Auth engine options | Password maximum length |
| `.NET AppAuthOptions.RefreshThreshold` | timespan | `2m` | positive | Client code | Proactive refresh threshold |
| `.NET ServerAuthOptions.RefreshThreshold` | timespan | `2m` | positive | Client code | Proactive refresh threshold |
| TS `appAuth.refreshThresholdMs` | number | `120000` | positive | `@aouda/client` | Proactive refresh threshold |
| TS `serverAuth.refreshThresholdMs` | number | `120000` | positive | `@aouda/client` | Proactive refresh threshold |
| Table `authMode` | string | `jwt-claim` | `jwt-claim`, `auth-db-pls`, `auth-db-rls` | Table create/update payload | Per-table auth mode |
| Table `permissionDimension` | string? | `null` | required for `auth-db-pls` | Table create/update payload | ADRA PLS dimension |
| Table `rlsResolverName` | string? | `null` | required for `auth-db-rls` | Table create/update payload | ADRA RLS resolver |

Precedence and operational notes:
- Host config precedence is standard server binding (`appsettings`/env/CLI).
- `aouda dev --auth` is dynamic at dev startup; key generation occurs when linking app auth DB.
- Token validation mode changes are startup/middleware configuration behavior.
- Auth route/admin policy changes are runtime dynamic.
- Safety-gated behavior:
  - app auth routes reject missing API keys;
  - invalid `X-User-Token` is rejected even when service key itself is valid.
- Reserved/deferred:
  - no runtime config surface for MCP server tooling or NL query engine in this repo.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (two-layer app flow)

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    AppAuth = new AppAuthOptions
    {
        ApiKey = "mk_anon_..."
    }
});

var auth = await client.Auth.SignInAsync("alice@example.com", "Pass123!");
var me = await client.Auth.MeAsync();
Console.WriteLine($"{me.Email} {auth.ExpiresInSeconds}");
```

Expected result: client signs in through app auth route and subsequent calls use user JWT context.

Common mistake: setting both `ApiKey` and `Token` in app auth options (validation throws).

### TypeScript example (service key + ADRA admin wrappers)

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  appAuth: { apiKey: "mk_svc_..." }
});

await client.auth.signIn("admin@myapp.com", "Pass123!");
await client.auth.createPartitionGrant("usr_123", {
  dimension: "org_id",
  partitionKey: "org-a",
  accessLevel: "write"
});
```

Expected result: authenticated admin creates partition grant through app admin API wrapper.

Common mistake: using `client.auth` without `serverAuth` or `appAuth` configured in client options.

### HTTP/protocol examples

```http
POST /api/databases/myapp/auth/signin
Authorization: Bearer mk_anon_...
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "Pass123!"
}
```

```http
POST /api/databases/myapp/auth/admin/users/usr_123/partition-grants
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "dimension": "org_id",
  "partitionKey": "org-a",
  "accessLevel": "write"
}
```

Expected result: first call returns token pair; second call creates ADRA grant for user.

Common mistake: calling app auth endpoints with JWT bearer only and no API key at the app-auth gate.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Start local AI-friendly dev server | `aouda dev` CLI | `aouda dev` CLI | local HTTP service | Implemented | `--auth` prints setup guidance |
| Create DB with auth and generated keys | HTTP call from .NET/transport | HTTP call from TS/transport | `POST /api/databases` with `auth.enabled` | Implemented | Returns keys only at creation/link time |
| App auth sign-up/sign-in/refresh/me/password | `.NET` auth client | `client.auth.*` | `/api/databases/{db}/auth/*` | Implemented | Two-layer flow |
| Service key user-context forwarding | `UserToken` option | `userToken` option | `X-User-Token` header | Implemented | Effective only for service-level API keys |
| ADRA table mode metadata | Table request DTOs | `CreateTableRequest` fields in TS types | table create/update payloads | Implemented | `authMode`, `permissionDimension`, `rlsResolverName` |
| ADRA admin partition grant wrappers | No first-class helper | `create/list/deletePartitionGrant` | app admin endpoints | Partial | .NET uses raw HTTP path today |
| ADRA admin resolver wrappers | No first-class helper | `create/list/get/update/deleteRlsResolver` | app admin endpoints | Partial | TS wrapper parity is stronger |
| MCP auth tools | None | None | None | Missing | Planned in P12 Epic E / ADR 0017 intent |
| Natural-language query interface | None | None | None | Missing | ADR 0017 proposed only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| First-class MCP server package and tools | No `@aouda/mcp-server` implementation in repo | Use CLI + HTTP/SDK directly | ADR 0017 + future tasking | High |
| Natural-language query tool/API | No NL query endpoint/tool in server/client | Build queries through existing query APIs | ADR 0017 proposed component | High |
| .NET typed wrappers for ADRA admin endpoints | No parity convenience methods in `.NET` auth client | Use raw HTTP/admin transport from .NET | P14 follow-up parity tasks | High |
| AI-oriented error fields (`mcpTool`, `docs`) | Not emitted by current `AuthErrorPayload` | Use `error` + `suggestion` + `requestId` | P12 Epic E intent / future hardening | Medium |
| Cloud ephemeral provisioning endpoint | No public cloud provisioning API in repo | Run local dev server or self-hosted server | ADR 0017/0022 direction | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run AI local bootstrap

When to use:
- agent needs a working local database immediately.

Steps:
1. Run `aouda dev --auth`.
2. Capture `Anon key` from startup output.
3. Call app signup/signin via `/api/databases/{db}/auth/*`.
4. Create table and insert/query data via HTTP or SDK.

Expected checks:
- startup output contains auth summary and quick-start route hints;
- app auth endpoint rejects missing key and accepts anon key;
- data operations succeed with authenticated user token.

### Scenario 2: Backend mediation with user-context enforcement

When to use:
- backend service performs operations for user while preserving row/partition controls.

Steps:
1. Connect backend with `service_role` key.
2. Attach user JWT as `X-User-Token`.
3. Execute data query/write on PLS/RLS-enabled tables.
4. Verify results are scoped to user policy, not unrestricted service key access.

Expected checks:
- service key alone can bypass PLS where allowed;
- service key + valid `X-User-Token` applies user-context enforcement;
- invalid/revoked `X-User-Token` yields 401 with explicit guidance.

### Scenario 3: Evolve from static claim to ADRA grant-based access

When to use:
- user needs access to multiple partition keys and static claim model is insufficient.

Steps:
1. Update table to `authMode = auth-db-pls` with `permissionDimension`.
2. Create partition grants for target users.
3. Run fan-out query without explicit partition filter.
4. Validate only granted partitions are returned.

Expected checks:
- table metadata reflects ADRA mode fields;
- fan-out query returns only granted partitions;
- writes without proper access-level grant fail with specific error code.

## 2.13 Operations and observability

Monitor first:
- auth gate failures:
  - `AUTH_API_KEY_REQUIRED`,
  - `AUTH_API_KEY_INVALID`,
  - `AUTH_TOKEN_INVALID`,
  - `AUTH_TOKEN_EXPIRED`,
  - `AUTH_TOKEN_REVOKED`.
- dev bootstrap behavior:
  - key generation vs existing-key prefix branch in startup output.
- ADRA enforcement health:
  - grant-not-found and insufficient-access error patterns,
  - RLS validation failures.
- request-level diagnostics:
  - response `requestId`,
  - `X-Auth-Database` on relevant auth failures.

Recovery expectations:
- restart preserves auth metadata and policy state (auth DB tables persisted under normal server mode);
- permission changes propagate on subsequent requests through version-aware ADRA flow;
- token revocation behavior depends on selected validation mode (`Hybrid`/`Stateful` stronger than `SignatureOnly`).

Recommended tuning sequence:
1. Keep default `Hybrid` validation in most app flows.
2. Keep short access tokens and rely on refresh workflow.
3. Introduce ADRA modes incrementally per table/user cohort.

| Question | Practical answer |
|---|---|
| What is the safest default for generated apps? | App auth with anon key + sign-in, middleware in `Hybrid` mode |
| How do I preserve user-level enforcement from backend jobs? | Service key plus `X-User-Token` |
| How do I debug denied operations quickly? | Start with error code + suggestion, then inspect grants/resolver bindings |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `AUTH_API_KEY_REQUIRED` on app auth route | Missing/incorrect layer-1 key | Send `Authorization: Bearer mk_anon_...` or `mk_svc_...` |
| Service key request fails with `X-User-Token` error | User token expired/revoked/invalid | Refresh/reissue user token, retry |
| Fan-out query returns too few rows | Missing partition grants for dimension | Add grants for missing partition keys |
| Write denied on granted partition | Grant is `read` level only | Promote to `write`/`admin` access level |
| RLS seems not applied | Table mode/resolver binding mismatch | Verify `authMode` and `rlsResolverName` on table |
| No keys shown on repeated `aouda dev --auth` run | Keys already existed and are one-time display | Use regenerate endpoint or existing prefixes to locate keys |

## 2.15 Verification ledger

Last verification date (UTC): `2026-04-01`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Middleware auth integration suite | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~AuthenticationMiddlewareIntegrationTests" --verbosity minimal` | Pass (`37/37`) | 2026-04-01 | Covers API key gate, token modes, `X-User-Token`, linked/unlinked DB behavior |
| Dev server auth output tests | `dotnet test tests/Aouda.Cli.Tests --no-build --filter "FullyQualifiedName~DevServerIntegrationTests.AuthMode_" --verbosity minimal` | Pass (`2/2`) | 2026-04-01 | Verifies key output and existing-key prefix guidance |
| ADRA fan-out integration path | `dotnet test tests/Aouda.Server.Tests --no-build --filter "FullyQualifiedName~PartitionLevelSecurityEnforcementIntegrationTests.Query_AuthDbPlsTable_FanOut_ReturnsRowsFromAllGrantedPartitionsOnly" --verbosity minimal` | Pass (`1/1`) | 2026-04-01 | Confirms auth-db-pls grant-constrained fan-out behavior |
| TypeScript auth client/handler/integration | `npm test -- tests/auth-client.test.ts tests/auth-handler.test.ts tests/auth-integration.test.ts` (in `../aouda-client-ts`) | Pass (`72/72`) | 2026-04-01 | Confirms app/server auth client lifecycle and transport behavior |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| App auth API key gate + scope handling | `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs` | Pass | Strong | Includes no-token and JWT-instead-of-key rejection paths |
| Service key + `X-User-Token` flow | `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs` | Pass | Strong | Includes valid, invalid, expired, revoked, and ignored-header cases |
| Dev bootstrap auth output UX | `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs` | Pass | Medium/Strong | Covers generated-key and existing-key output branches |
| ADRA partition fan-out enforcement | `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs` | Pass | Strong | Includes grant-constrained fan-out and write checks |
| ADRA table metadata serialization | `tests/Aouda.Protocol.Tests/SerializationTests.cs` | Pass (existing suite) | Medium | Confirms `authMode` DTO round-trip |
| TS auth client lifecycle and wrappers | `../aouda-client-ts/tests/auth-client.test.ts`, `auth-handler.test.ts`, `auth-integration.test.ts` | Pass | Medium/Strong | Covers token lifecycle and auth API usage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No end-to-end agent flow test chaining CLI output -> signup -> ADRA grant -> scoped query in one script | Cross-surface regressions can hide between suites | Add scenario test that parses `aouda dev --auth` output and executes full bootstrap flow | High |
| Limited explicit tests for error payload contract stability as an AI interface | Agents rely on stable fields for remediation loops | Add contract tests for `error/message/suggestion/requestId` across auth failure types | High |
| No tests for future MCP compatibility adapters | Migration to MCP surface risks drift | Add adapter-contract tests once MCP layer exists | Medium |
| No dedicated test asserting absence/presence of `mcpTool`/`docs` fields by version | Prevents accidental undocumented contract changes | Add explicit payload schema version tests | Medium |

## 2.18 Known gaps and undone work

- MCP and NL query surfaces are still intent-level:
  - ADR 0017 defines these capabilities, but no runtime package/endpoints are shipped in this repo.
  - User impact: agents must use CLI/HTTP/SDK directly today.
- AI-friendly error payload is useful but incomplete relative to P12 Epic E intent:
  - current payload has `error/message/suggestion/detail/requestId`,
  - fields like `mcpTool` and `docs` are not emitted.
- Cross-SDK ADRA helper parity:
  - TS includes ADRA admin wrappers; .NET still relies on lower-level HTTP paths for those operations.
- Cloud ephemeral provisioning path is not present in current server:
  - distribution direction exists in ADR 0022, not as shipped endpoint in this workspace.

## 2.19 References

- ADRs:
  - `docs/decisions/0017-ai-native-interface.md`
  - `docs/decisions/0022-licensing-and-distribution-strategy.md`
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
- Tasks/reports:
  - `docs/tasks/P12/P12-TwoLayerAuth-Tasks.md`
  - `docs/tasks/P12/P12-TwoLayer-S1-ApiKeyInfrastructure-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S2-MiddlewareAndAuthorization-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S4-DocumentationAndDX-Report.md`
  - `docs/tasks/P14/P14-ADRA-Tasks.md`
  - `docs/tasks/P14/P14-TaskS6-TypeScriptClientWrappers.md`
  - `docs/tasks/P14/P14-TaskS7-GettingStartedAuthRewrite.md`
- Code:
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Server/DevServer/DevServerOptions.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
  - `src/Aouda.Server/Auth/AuthErrorResponses.cs`
  - `src/Aouda.Protocol/ErrorCodes.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Client/Auth/AppAuthOptions.cs`
  - `src/Aouda.Client/Auth/ServerAuthOptions.cs`
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/auth/auth-types.ts`
  - `../aouda-client-ts/src/auth/auth-client.ts`
  - `../aouda-client-ts/src/types.ts`
- Tests:
  - `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`
  - `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`
  - `../aouda-client-ts/tests/auth-client.test.ts`
  - `../aouda-client-ts/tests/auth-handler.test.ts`
  - `../aouda-client-ts/tests/auth-integration.test.ts`

## 2.20 What is missing from this document? (meta completeness)

_Updated 2026-04-08 after P14/P16 completion._

- This document covers runtime behavior and API surfaces, but does not include full per-endpoint OpenAPI-style field catalogs.
- ~~MCP and natural-language query sections are intentionally marked as planned/missing~~ — ✅ **Partially resolved (P16)**:
  - **MCP cluster tools** now ship from `@aouda/client` (`src/mcp/`): `createAoudaClusterMcpToolSet()` provides stable tool names, JSON Schema `inputSchema`, and `execute` handlers for cluster status, backup, scaling, add/remove node, promote, failover. Hosts (Cursor, custom agents, Studio) register these with an MCP implementation. Documentation: `aouda-client-ts/docs/dev/MCP-Cluster-Tools.md`. Full reference: `docs/dev/Functionality-TypeScript-Client.md` §12.
  - **Natural language cluster operations** implemented in Studio (P16 G.5): AI-powered cluster management via Studio chat interface translating natural language to cluster operations using MCP tool definitions.
  - **Schema inference Extend mode (P14, BL-022)**: `InferenceMode: Extend` enables insert-time inference for new tables while protecting apply-managed tables with DDL lock. Critical for AI agent autonomy: agents can create new tables via insert without explicit DDL.
  - **WhereClause.Groups (P14, BL-044)**: nested boolean groups adopted end-to-end across SDKs, enabling AI agents to compose complex filter expressions naturally.
