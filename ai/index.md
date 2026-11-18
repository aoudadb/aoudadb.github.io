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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Functionality-Auth-And-Authorization.md`, `docs/dev/Functionality-Schema-Lifecycle.md`

## Start Here

If your question is "How should an AI agent **build an application** on Aouda?", the answer is one page: **[How to build apps effortlessly with Aouda](../guides/build-apps.md)**, and specifically its [Rules for AI agents](../guides/build-apps.md#rules-for-ai-agents) section — reading order, hard do/never rules, the per-screen decision procedure, the structured error contract, and a self-verification checklist. Point your agent at that URL before it writes any code.

If your question is "How should an AI agent use Aouda today?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.11 API and CLI coverage reference`
- `2.12 Scenario playbooks`
- [Local CLI testing (agents)](local-cli-testing.md) for a throwaway `aouda start` (unused ports, temp data-dir) and the traps that waste a session (`start -h`, data-plane `/query`, CorsOrigins shape, schema `where` / keys)
- [Declare a server in one file](../guides/declaration.md) (**BL-1463, 0.16.0**) when the agent must produce a deployment (compose, principals, statements, schema files) that survives a wipe: one `aouda.json`, checked with `aouda plan`
- [Named queries](../guides/named-queries.md) for generated browser apps (string names; a browser holds no key — give `anonymous` the statements it may run)
- [Division of responsibility](../guides/division-of-responsibility.md) before moving logic into the schema

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
- Fast "first successful request" for local agents (`aouda start`, schema-on-write, simple HTTP/SDK paths).
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
  - `docs/tasks/P14/P14-TaskS6-TypeScriptClientWrappers.md`
  - `docs/tasks/P14/P14-TaskS7-GettingStartedAuthRewrite.md`
- Design references:
  - `docs/decisions/0017-ai-native-interface.md` (proposed; intent-level)
  - `docs/decisions/0022-licensing-and-distribution-strategy.md` (draft; supersedes ADR 0017 licensing section)
  - `docs/decisions/0023-authentication-and-authorization.md`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Core runtime/code evidence:
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Server/DevServer/DevServerOptions.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
  - `src/Aouda.Server/Auth/AuthErrorResponses.cs`
  - `src/Aouda.Protocol/ErrorCodes.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
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

- `aouda start` runs the foreground server (CLI flags `--port`, `--data-dir` override optional local `appsettings.json` — see [Server configuration](../guides/server-configuration.md)).
- App auth is enabled by **HTTP**: `POST /api/databases` with `{ "auth": { "enabled": true } }` or `kind: "auth"`. The response has no key. A principal and its key are declared, or minted on the principal. See [Access](auth/index.md) (**BL-1464, 0.16.0**).
- Password reset and invite emails require a **configured email provider** on the server (`Aouda:Auth:Email` — `console` for local dev, `sendgrid` for production) — see [auth/notifications.md](../auth/notifications.md).
- HTTP database creation with `{ "auth": { "enabled": true } }`:
  - links to existing single app auth DB, or
  - auto-creates default app auth DB if none exists, or
  - returns explicit error if multiple auth DBs exist and none is specified.

| Setting / behavior | Default | Practical impact |
|---|---|---|
| `DevServerOptions.Port` | `5433` | Predictable local endpoint for agent bootstrapping |
| `DevServerOptions.DatabaseName` | `default` | Immediate target DB without extra setup |
| `DevServerOptions.DataPath` | `null` | Ephemeral local run for quick experiments |
| `DevServerOptions.EnableAuth` | `false` | Links the dev database to app auth and prints its keys. Every dev server needs a first admin before any data call (**BL-1473, 0.13.1**), with or without this option: see the `Bind` row |
| `DevServerOptions.Bind` | `null` (**BL-1473, 0.13.1**) | The dev server listens on **loopback only**, on `Port`. To listen on other interfaces set an address in the form `aouda start --bind` takes: `host:port` or `host`, an IP literal (IPv6 in brackets, `[::1]:5433`), `0.0.0.0` or `*` for every interface, e.g. `0.0.0.0:5433`. **Do not bind it beyond loopback on a network you do not trust:** it speaks plain HTTP (tokens and passwords cross the network in clear), allows every browser origin (CORS), and has no rate limiting, request timeouts or forwarded-header handling; use `aouda start` for that. **First admin:** like `aouda start`, a server with no admin yet answers only the setup calls, and only from the machine it runs on (`503 SETUP_REQUIRED` otherwise); create the admin with `curl -X POST http://localhost:5433/api/auth/setup -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"..."}'`, or start with `ASPNETCORE_ENVIRONMENT=Development` and `AOUDA_DEV_ADMIN=true`, which creates a throwaway admin and prints one `AOUDA-DEV-ADMIN` line. The setup route refuses a request that carries an `Origin` header (`403 SETUP_FROM_BROWSER_REFUSED`): call it from curl, not from a web page. There is no `aouda dev` command; the dev server is `DevServerHost` in `Aouda.Server`, used by `Aouda.Testing`'s `AoudaTestServer` (in-memory, no port, no setup mode) and by hosts that call `DevServerHost.RunAsync` |
| `TokenOptions.AccessTokenLifetime` | `15m` | Short-lived user access tokens |
| `TokenOptions.RefreshTokenLifetime` | `30d` | Long-lived sessions for app flows |
| `TokenOptions.Issuer` | `"aouda"` | Issuer of the server auth database's tokens; an app database's tokens carry `{base}/api/databases/{db}`, and (**0.4.0**) only that issuer is accepted for them |
| `AuthenticationMiddlewareOptions.ValidationMode` | `Hybrid` | Signature + revocation checking by default |
| `PasswordPolicy` | Min `8`, Max `128` | NIST-aligned baseline policy |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

## 2.4 Availability status (implementation honesty)

### Available now

- Agent-friendly local bootstrap:
  - `aouda start` with HTTP database + auth setup; keys from create-database response.
- Auto-generated connection keys on auth-enabled DB creation:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Two-layer auth runtime:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
  - user JWT identity/session flow.
- Service-key user-context forwarding:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Structured auth errors with machine-usable fields:
  - `error`, `message`, `suggestion`, optional `detail`, optional `requestId`.

### Planned / proposed

- Full MCP server surface described in ADR 0017 (`aouda_create_database`, `aouda_query`, auth tools, schema resources).
- Natural-language query pipeline and validation/explain flow from ADR 0017.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Cloud ephemeral instance provisioning model in ADR 0017/ADR 0022 distribution direction.

### Reserved / not yet wired

- ADR 0017 `mcpTool` and `docs` fields in auth errors are not part of current runtime payload shape.
- Dedicated first-class MCP package/runtime is not present in this repository (`**/*mcp*` file search returns no implementation files).
- Natural-language query endpoint/tooling described in ADR 0017 is not wired as a public API in server/client code.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| ADR track (non-shipped intent) | ADR 0017 + ADR 0022 | Product direction for AI-native interface and distribution model | MCP server package, NL query, cloud ephemeral workflow not shipped in current codebase | `docs/BACKLOG.md` |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Local dev host (`DevServerHost`; no `aouda dev` command) | Yes | No | No | `DevServerHost.cs`, `DevServerIntegrationTests.cs` | Loopback by default; needs a first admin before any data call (**BL-1473, 0.13.1**); banner + schema-on-write mode |
| Auth-enabled local bootstrap (`EnableAuth`) | Yes | No | No | `DevServerHost.cs`, `DevServerOptions.cs`, CLI tests | Prints generated keys or key-prefix fallback guidance; the first admin still comes first |
| Auto-link/create auth DB during DB create | Yes | No | No | `DatabasesController.cs` | Handles 0/1/many auth DB shorthand rules |
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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
  - Layer 2: user JWT/session identity.
- Progressive authorization maturity:
  - start with `jwt-claim`,
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Agent-safe failure model:
  - stable error code + suggestion allow deterministic retries/fixes.
- SDK behavior:
  - auth handler starts with key/token, upgrades to user JWT after sign-in where applicable.

Invariants:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Missing/invalid policy context fails closed.

## 2.8 How Aouda implements it

High-level runtime path:

1. Bootstrap: `aouda start` (or HTTP DB create) starts DB and optional auth linkage.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
3. Middleware:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
4. Authorization:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
5. Response:
   - structured error payload on failure,
   - standard protocol payloads on success.

Implementation anchors:
- Bootstrap and key-print UX: `src/Aouda.Server/DevServer/DevServerHost.cs`
- Auth DB linking and generated keys: `src/Aouda.Server/Controllers/DatabasesController.cs`
- Auth scope and validation pipeline: `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- Error contract: `src/Aouda.Server/Auth/AuthErrorResponses.cs`, `src/Aouda.Protocol/ErrorCodes.cs`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- TS wrappers and options: `../aouda-client-ts/src/auth/auth-client.ts`, `../aouda-client-ts/src/auth/auth-types.ts`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Local agent bootstrap with auth

1. A host starts the dev server (`DevServerHost.RunAsync()`, loopback unless `Bind` says otherwise); the first admin is created at `POST /api/auth/setup` or by `AOUDA_DEV_ADMIN=true` (**BL-1473, 0.13.1**). With `aouda start` instead, the agent creates the auth-enabled DB via API and captures keys.
2. `DevServerHost.RunAsync()` starts app and calls `EnsureAppAuthEnabledAsync(...)`.
3. Host resolves/creates app auth DB and links app DB.
4. If keys are newly generated, host prints `Anon key` and `Service role key`; if not, prints key prefixes + regeneration hint.

Primary evidence:
- `src/Aouda.Server/DevServer/DevServerHost.cs`
- `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`

### Walk-through B: App auth public entry (keyless)

1. Request enters `AuthenticationMiddleware`.
2. `PublicRouteAllowlist.IsAppAuthPublicEntry` matches POST signup/signin/refresh/password-reset (segment-aware `{db}` parse).
3. Layer-1 is skipped — a missing, stale, or valid bearer does not change the outcome.
4. Unallowlisted `/auth/*` (e.g. `/me`, `/mfa/enroll`) is `AppAuthUser` and fails closed with `AUTH_TOKEN_MISSING` if no bearer.

Primary evidence:
- `src/Aouda.Server/Auth/PublicRouteAllowlist.cs`
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `tests/Aouda.Server.Tests/Auth/AppAuthPublicEntryTests.cs`

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

1. Primary bearer validates as service-level key.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
3. On success, middleware replaces principal and sets `EffectiveUserTokenItemKey` for downstream cache isolation.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Primary evidence:
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `tests/Aouda.Server.Tests/Auth/AuthenticationMiddlewareIntegrationTests.cs`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
3. Enforcer constrains query to granted partitions and blocks ungranted keys.
4. Result set contains only rows from authorized partitions.

Primary evidence:
- `src/Aouda.Protocol/Schema/TableMessages.cs`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| How quickly can an agent start a real DB? | Multi-step infra/bootstrap | `aouda start` + HTTP DB create and schema inference | Faster first successful action |
| How do auth defaults work for generated apps? | Inconsistent app-specific patterns | Built-in two-layer auth + generated anon/service keys | Lower security misconfiguration risk |
| Are errors machine-actionable? | Generic text-only failures | Stable error codes + suggestion + request id | Better agent retry/correction loops |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:Port` | int | `5000` (code); `5433` typical install | positive | CLI `--port` / `AOUDA_PORT` / optional appsettings | CLI wins |
| `Aouda:DataPath` | string | `./data` | path | CLI `--data-dir` / `AOUDA_DATAPATH` / optional appsettings | CLI wins |
| `Aouda:Auth:Email:*` | — | null | SendGrid or `console` settings | `AOUDA_*` env / optional server appsettings | Password reset + invite OTP email |
| `Aouda:Auth:Sms:*` | — | null | GatewayAPI settings | `AOUDA_*` env / optional server appsettings | MFA phone OTP SMS |
| `TokenOptions.AccessTokenLifetime` | timespan | `15m` | positive | Auth engine options | Access JWT lifetime |
| `TokenOptions.RefreshTokenLifetime` | timespan | `30d` | positive | Auth engine options | Refresh token lifetime |
| `TokenOptions.Issuer` | string | `"aouda"` | non-empty | Auth engine options | Issuer of the server auth database's tokens (app databases: their URL issuer) |
| `AuthenticationMiddlewareOptions.ValidationMode` | enum | `Hybrid` | `SignatureOnly`, `Hybrid`, `Stateful` | Middleware options | Signature-only vs revocation/session enforcement |
| `PasswordPolicy.MinLength` | int | `8` | `>=1` | Auth engine options | Password minimum length |
| `PasswordPolicy.MaxLength` | int | `128` | `>= MinLength` | Auth engine options | Password maximum length |
| `.NET AppAuthOptions.RefreshThreshold` | timespan | `2m` | positive | Client code | Proactive refresh threshold |
| `.NET ServerAuthOptions.RefreshThreshold` | timespan | `2m` | positive | Client code | Proactive refresh threshold |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Precedence and operational notes:
- Host config precedence: code defaults → optional appsettings → env → `AOUDA_*` → CLI (see [Server configuration](../guides/server-configuration.md)).
- App auth keys are returned when creating or linking an auth-enabled database via HTTP.
- Token validation mode changes are startup/middleware configuration behavior.
- Auth route/admin policy changes are runtime dynamic.
- Safety-gated behavior:
  - app auth routes reject missing API keys;
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
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
// WhoAmIAsync() — an aouda_ key (AoudaCredential.Key) or a session.
});

var auth = await client.Auth.SignInAsync("alice@example.com", "Pass123!");
var me = await client.Auth.MeAsync();
Console.WriteLine($"{me.Email} {auth.ExpiresInSeconds}");
```

Expected result: client signs in through app auth route and subsequent calls use user JWT context.

Common mistake: setting both `ApiKey` and `Token` in app auth options (validation throws).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
// client.whoami() — apiKey is an aouda_ key, or session, never both.
});

await client.auth.signIn("admin@myapp.com", "Pass123!");
await client.auth.createEntitlement("550e8400-e29b-41d4-a716-446655440000", {
  dimension: "org_id",
  key: "org-a",
  level: "write"
});
```

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

### HTTP/protocol examples

```http
POST /api/databases/myapp/auth/signin
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "Pass123!"
}
```

```http
# an aouda_ key or a session. GET /api/auth/whoami names the principal.
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "dimension": "org_id",
  "key": "org-a",
  "level": "write"
}
```

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Start local server | `aouda start` CLI | `aouda start` CLI | local HTTP service | Implemented | Auth via POST /api/databases |
| Create DB with auth and generated keys | HTTP call from .NET/transport | HTTP call from TS/transport | `POST /api/databases` with `auth.enabled` | Implemented | Returns keys only at creation/link time |
| App auth sign-up/sign-in/refresh/me/password | `.NET` auth client | `client.auth.*` | `/api/databases/{db}/auth/*` | Implemented | Two-layer flow |
| MCP auth tools | None | None | None | Missing | Planned in P12 Epic E / ADR 0017 intent |
| Natural-language query interface | None | None | None | Missing | ADR 0017 proposed only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| First-class MCP server package and tools | No `@aouda/mcp-server` implementation in repo | Use CLI + HTTP/SDK directly | ADR 0017 + future tasking | High |
| Natural-language query tool/API | No NL query endpoint/tool in server/client | Build queries through existing query APIs | ADR 0017 proposed component | High |
| AI-oriented error fields (`mcpTool`, `docs`) | Not emitted by current `AuthErrorPayload` | Use `error` + `suggestion` + `requestId` | P12 Epic E intent / future hardening | Medium |
| Cloud ephemeral provisioning endpoint | No public cloud provisioning API in repo | Run local dev server or self-hosted server | ADR 0017/0022 direction | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run AI local bootstrap

When to use:
- agent needs a working local database immediately.

Steps:
1. Run `aouda start`; create auth DB via API; configure email (`console` or `sendgrid`) if testing password reset.
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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Expected checks:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

When to use:
- user needs access to multiple partition keys and static claim model is insufficient.

Steps:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
3. Run fan-out query without explicit partition filter.
4. Validate only granted partitions are returned.

Expected checks:
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
  - grant-not-found and insufficient-access error patterns,
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- request-level diagnostics:
  - response `requestId`,
  - `X-Auth-Database` on relevant auth failures.

Recovery expectations:
- restart preserves auth metadata and policy state (auth DB tables persisted under normal server mode);
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- token revocation behavior depends on selected validation mode (`Hybrid`/`Stateful` stronger than `SignatureOnly`).

Recommended tuning sequence:
1. Keep default `Hybrid` validation in most app flows.
2. Keep short access tokens and rely on refresh workflow.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

| Question | Practical answer |
|---|---|
| What is the safest default for generated apps? | App auth with anon key + sign-in, middleware in `Hybrid` mode |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `AUTH_API_KEY_REQUIRED` on app auth route | Pre-BL-355 server, or a non-public `/auth/*` path | Public signup/signin/refresh are keyless. `/me` and `/mfa/*` need a user JWT. |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

## 2.15 Verification ledger

Last verification date (UTC): `2026-04-01`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Dev server auth output tests | `dotnet test tests/Aouda.Cli.Tests --no-build --filter "FullyQualifiedName~DevServerIntegrationTests" --verbosity minimal` | Pass (`2/2`) | 2026-04-01 | Verifies the dev-admin line |
| TypeScript auth client/handler/integration | `npm test -- tests/auth-client.test.ts tests/auth-handler.test.ts tests/auth-integration.test.ts` (in `../aouda-client-ts`) | Pass (`72/72`) | 2026-04-01 | Confirms app/server auth client lifecycle and transport behavior |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Dev bootstrap auth output UX | `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs` | Pass | Medium/Strong | Covers generated-key and existing-key output branches |
| TS auth client lifecycle and wrappers | `../aouda-client-ts/tests/auth-client.test.ts`, `auth-handler.test.ts`, `auth-integration.test.ts` | Pass | Medium/Strong | Covers token lifecycle and auth API usage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
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
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Cloud ephemeral provisioning path is not present in current server:
  - distribution direction exists in ADR 0022, not as shipped endpoint in this workspace.

## 2.19 References

- ADRs:
  - `docs/decisions/0017-ai-native-interface.md`
  - `docs/decisions/0022-licensing-and-distribution-strategy.md`
  - `docs/decisions/0023-authentication-and-authorization.md`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
- Tasks/reports:
  - `docs/tasks/P12/P12-TwoLayerAuth-Tasks.md`
  - `docs/tasks/P12/P12-TwoLayer-S1-ApiKeyInfrastructure-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S2-MiddlewareAndAuthorization-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S4-DocumentationAndDX-Report.md`
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
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
  - **Schema inference Extend mode (P14, BL-022)**: `InferenceMode: Extend` enables insert-time inference for new tables. Apply-managed tables are DDL-locked in every mode (**BL-1177, 0.7.1**; before, only in `Extend`). Critical for AI agent autonomy: agents can create new tables via insert without explicit DDL.
  - **WhereClause.Groups (P14, BL-044)**: nested boolean groups adopted end-to-end across SDKs, enabling AI agents to compose complex filter expressions naturally.
