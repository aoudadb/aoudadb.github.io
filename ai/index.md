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
- Explicit connection and identity model for AI-generated apps (one credential: a key or a session).
- One policy language that can be tightened incrementally: a principal's statements, each with an optional row condition.
- Predictable error contracts (`error`, `message`, `requestId`, and `remedy` on an access refusal) suitable for retry/fix loops.

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
  - `docs/tasks/P14/P14-TaskS6-TypeScriptClientWrappers.md`
  - `docs/tasks/P14/P14-TaskS7-GettingStartedAuthRewrite.md`
- Design references:
  - `docs/decisions/0017-ai-native-interface.md` (proposed; intent-level)
  - `docs/decisions/0022-licensing-and-distribution-strategy.md` (draft; supersedes ADR 0017 licensing section)
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0071-principals-one-policy-language-one-key-format.md`
- Core runtime/code evidence:
  - `src/Aouda.Server/DevServer/DevServerHost.cs`
  - `src/Aouda.Server/DevServer/DevServerOptions.cs`
  - `src/Aouda.Server/Controllers/DatabasesController.cs`
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
  - `src/Aouda.Server/Auth/AuthErrorResponses.cs`
  - `src/Aouda.Protocol/ErrorCodes.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
  - `src/Aouda.Server/Auth/Policy/PolicyAuthorizer.cs`
- SDK evidence:
  - `.NET`: `src/Aouda.Client/Auth/AoudaCredential.cs`, `src/Aouda.Client/Access/AccessAdminApi.cs`
  - TypeScript: `../aouda-client-ts/src/client.ts`, `../aouda-client-ts/src/auth/auth-types.ts`, `../aouda-client-ts/src/auth/auth-client.ts`, `../aouda-client-ts/src/types.ts`
- Test evidence:
  - `tests/Aouda.Server.Tests/Authorization/Principals/`
  - `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`
  - `../aouda-client-ts/tests/auth-client.test.ts`
  - `../aouda-client-ts/tests/auth-handler.test.ts`
  - `../aouda-client-ts/tests/auth-integration.test.ts`

## 2.3 Defaults and zero-config behavior

If you do nothing beyond starting local dev:

- `aouda start` runs the foreground server (CLI flags `--port`, `--data-dir` override optional local `appsettings.json` — see [Server configuration](../guides/server-configuration.md)).
- App auth is enabled by **HTTP**: `POST /api/databases` with `{ "auth": { "enabled": true } }` or `kind: "auth"`. The response has no key. A principal and its key are declared, or minted on the principal. See [Access](../auth/index.md) (**BL-1464, 0.16.0**).
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
| `DevServerOptions.EnableAuth` | `false` | Links the dev database to app auth and prints the auth database's name. Every dev server needs a first admin before any data call (**BL-1473, 0.13.1**), with or without this option: see the `Bind` row |
| `DevServerOptions.Bind` | `null` (**BL-1473, 0.13.1**) | The dev server listens on **loopback only**, on `Port`. To listen on other interfaces set an address in the form `aouda start --bind` takes: `host:port` or `host`, an IP literal (IPv6 in brackets, `[::1]:5433`), `0.0.0.0` or `*` for every interface, e.g. `0.0.0.0:5433`. **Do not bind it beyond loopback on a network you do not trust:** it speaks plain HTTP (tokens and passwords cross the network in clear), allows every browser origin (CORS), and has no rate limiting, request timeouts or forwarded-header handling; use `aouda start` for that. **First admin:** like `aouda start`, a server with no admin yet answers only the setup calls, and only from the machine it runs on (`503 SETUP_REQUIRED` otherwise); create the admin with `curl -X POST http://localhost:5433/api/auth/setup -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"..."}'`, or start with `ASPNETCORE_ENVIRONMENT=Development` and `AOUDA_DEV_ADMIN=true`, which creates a throwaway admin and prints one `AOUDA-DEV-ADMIN` line. The setup route refuses a request that carries an `Origin` header (`403 SETUP_FROM_BROWSER_REFUSED`): call it from curl, not from a web page. There is no `aouda dev` command; the dev server is `DevServerHost` in `Aouda.Server`, used by `Aouda.Testing`'s `AoudaTestServer` (in-memory, no port, no setup mode) and by hosts that call `DevServerHost.RunAsync` |
| `TokenOptions.AccessTokenLifetime` | `15m` | Short-lived user access tokens |
| `TokenOptions.RefreshTokenLifetime` | `30d` | Long-lived sessions for app flows |
| `TokenOptions.Issuer` | `"aouda"` | Issuer of the server auth database's tokens; an app database's tokens carry `{base}/api/databases/{db}`, and (**0.4.0**) only that issuer is accepted for them |
| `AuthenticationMiddlewareOptions.ValidationMode` | `Hybrid` | Signature + revocation checking by default |
| `PasswordPolicy` | Min `8`, Max `128` | NIST-aligned baseline policy |
| App auth public routes (sign-up, sign-in, refresh, password reset) | No credential | A browser calls them with no key; `signup` is closed until `signup.enabled` |
| `anonymous` and signed-up principals | No statements | They can do nothing until the application says what |

## 2.4 Availability status (implementation honesty)

### Available now

- Agent-friendly local bootstrap:
  - `aouda start --dev-admin`: one printed line with a throwaway admin's email, password and key.
- One access model:
  - a principal, its statements, and one credential (a key or a session),
  - end users as principals of an application auth database, with the JWT session flow.
- Acting for a user from a backend:
  - the user's own session as the only credential, or a limited key minted from it.
- Row conditions:
  - a statement's `where`: a literal, `principal.id` / `principal.name`, or an attribute's values.
- Typed access clients:
  - `client.access` (TypeScript) and `client.Access` (.NET) for principals, roles, `signup` and credentials.
- Structured auth errors with machine-usable fields:
  - `error`, `message`, `requestId`, and `remedy`: what to do about it.
- Access an agent can check before it calls: `GET /api/auth/whoami`, and `aouda policy explain` offline.

### Planned / proposed

- Full MCP server surface described in ADR 0017 (`aouda_create_database`, `aouda_query`, auth tools, schema resources).
- Natural-language query pipeline and validation/explain flow from ADR 0017.
- Broader cross-SDK parity for auth helpers (password reset and MFA have no SDK wrapper).
- Cloud ephemeral instance provisioning model in ADR 0017/ADR 0022 distribution direction.

### Reserved / not yet wired

- ADR 0017 `mcpTool` and `docs` fields in auth errors are not part of current runtime payload shape.
- Dedicated first-class MCP package/runtime is not present in this repository (`**/*mcp*` file search returns no implementation files).
- Natural-language query endpoint/tooling described in ADR 0017 is not wired as a public API in server/client code.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| Principals | ADR 0071, the Principals phase | Principals, statements, one key format, `whoami`, `remedy`, declared access, typed access clients | Capability tokens, a hosted OAuth server and end-user sign-in through an external provider are not built | `docs/BACKLOG.md` |
| ADR track (non-shipped intent) | ADR 0017 + ADR 0022 | Product direction for AI-native interface and distribution model | MCP server package, NL query, cloud ephemeral workflow not shipped in current codebase | `docs/BACKLOG.md` |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Local dev host (`DevServerHost`; no `aouda dev` command) | Yes | No | No | `DevServerHost.cs`, `DevServerIntegrationTests.cs` | Loopback by default; needs a first admin before any data call (**BL-1473, 0.13.1**); banner + schema-on-write mode |
| Auth-enabled local bootstrap (`EnableAuth`) | Yes | No | No | `DevServerHost.cs`, `DevServerOptions.cs`, CLI tests | Prints the auth database's name and where a key comes from; the first admin still comes first |
| Auto-link/create auth DB during DB create | Yes | No | No | `DatabasesController.cs` | Handles 0/1/many auth DB shorthand rules |
| Keyless sign-up and sign-in from a browser | Yes | No | No | `PublicRouteAllowlist.cs`, `AppAuthPublicEntryTests.cs` | `signup` must be enabled |
| One credential per request, resolved to one principal | Yes | No | No | `CredentialResolver.cs` | A second credential header is refused `400` |
| Row conditions on statements | Yes | No | No | `PolicyAuthorizer.cs`, `ReadRowPolicy.cs`, `WriteRowPolicy.cs` | Reads are filtered; a write outside the condition is `403 AUTH_ROW_DENIED` |
| Access administration from code | Yes | No | No | `AccessAdminApi.cs`, `client.access` | Principals, roles, `signup`, credentials |
| MCP server/tooling package | No | No | Yes | `docs/decisions/0017-ai-native-interface.md`, code search | Direction documented; implementation absent |
| Natural-language query surface | No | No | Yes | ADR 0017 intent; no runtime endpoints | Requires translation + validation pipeline not present |
| AI-enriched error payload (`mcpTool`, `docs`) | No | Yes | No | `AuthErrorResponses.cs` | `remedy` is emitted; `mcpTool/docs` fields are not |

## 2.7 Core concepts and mental model

- AI-native in current Aouda means "low-friction operational surfaces" rather than "LLM magic endpoint":
  - fast bootstrap,
  - explicit auth defaults,
  - machine-readable errors,
  - predictable schema and policy APIs.
- One access model for generated apps:
  - who: a principal, proved by a key or a session,
  - what: its statements.
- Progressive authorization maturity:
  - start with a built-in role (`reader`, `writer`),
  - write statements that name the tables and named queries,
  - add a `where` for tenants, owners and lists of partitions.
- Agent-safe failure model:
  - stable error code + `remedy` allow deterministic retries/fixes.
- SDK behavior:
  - one credential per client: a key, or a session the client refreshes; `signIn` on a keyless client makes the session.

Invariants:
- The public app auth routes need no credential; every other route asks the principal's statements.
- A request carries one credential. A retired second one is refused, not ignored.
- A statement on a resource its auth database does not govern is refused when it is written.
- Missing/invalid policy context fails closed.

## 2.8 How Aouda implements it

High-level runtime path:

1. Bootstrap: `aouda start` (or HTTP DB create) starts DB and optional auth linkage.
2. Connection: client sends a bearer (a key or a session token), or nothing on the data-plane listener.
3. Middleware:
   - passes the public auth routes,
   - resolves the credential to one principal (a key by its id, a session by its issuer),
   - checks revocation, expiry and `disabled`.
4. Authorization:
   - the principal's statements (its own, its roles', `signup`'s) decide the action on the resource; their `where`s become one row predicate.
5. Response:
   - structured error payload on failure,
   - standard protocol payloads on success.

Implementation anchors:
- Bootstrap and key-print UX: `src/Aouda.Server/DevServer/DevServerHost.cs`
- Auth DB linking: `src/Aouda.Server/Controllers/DatabasesController.cs`
- Credentials and authorization: `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`, `src/Aouda.Server/Auth/Policy/PolicyAuthorizer.cs`
- Error contract: `src/Aouda.Server/Auth/AuthErrorResponses.cs`, `src/Aouda.Protocol/ErrorCodes.cs`
- Statements: `src/Aouda.Engine.Auth/Policy/Statement.cs`, `src/Aouda.Engine.Auth/Policy/PolicyEvaluator.cs`
- TS wrappers and options: `../aouda-client-ts/src/auth/auth-client.ts`, `../aouda-client-ts/src/auth/auth-types.ts`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: Local agent bootstrap with auth

1. A host starts the dev server (`DevServerHost.RunAsync()`, loopback unless `Bind` says otherwise); the first admin is created at `POST /api/auth/setup` or by `AOUDA_DEV_ADMIN=true` (**BL-1473, 0.13.1**). With `aouda start` instead, the agent creates the auth-enabled DB via API and captures keys.
2. `DevServerHost.RunAsync()` starts app and calls `EnsureAppAuthEnabledAsync(...)`.
3. Host resolves/creates app auth DB and links app DB.
4. Host prints the auth database's name and that a credential is a key of a principal (`aouda keys new`, or minted on the principal). It prints no key.

Primary evidence:
- `src/Aouda.Server/DevServer/DevServerHost.cs`
- `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs`

### Walk-through B: App auth public entry (keyless)

1. Request enters `AuthenticationMiddleware`.
2. `PublicRouteAllowlist.IsAppAuthPublicEntry` matches POST signup/signin/refresh/password-reset (segment-aware `{db}` parse).
3. Credential resolution is skipped — a missing, stale, or valid bearer does not change the outcome.
4. Other `/auth/*` routes (e.g. `/mfa/enroll`, `/password`) need the principal's own session and fail closed with `AUTH_CREDENTIAL_MISSING` if no bearer.

Primary evidence:
- `src/Aouda.Server/Auth/PublicRouteAllowlist.cs`
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `tests/Aouda.Server.Tests/Auth/AppAuthPublicEntryTests.cs`

### Walk-through C: A backend acts for a user

1. The backend holds the user's session (it signed the user in, or the user's client sent it).
2. It sends that session as the only bearer, or mints a limited key from it (`POST /api/auth/keys`) and sends the key.
3. The server resolves either to the user's principal; a limited key's limit is intersected with the principal's policy on every row.
4. A request that also carries the old second-token header is refused `400 INVALID_REQUEST`; its value is not read.

Primary evidence:
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `src/Aouda.Server/Auth/Policy/CredentialLimits.cs`

### Walk-through D: A query over the partitions an attribute lists

1. A statement's `where` is `{ "column": "room", "op": "in", "principal": "attributes.rooms" }`.
2. The request's principal has the attribute `rooms`; its values are bound into the condition.
3. The condition joins the query's own predicate, so it satisfies the partition filter and prunes to the listed partitions.
4. Result set contains only rows from those partitions. A missing attribute matches no row.

Primary evidence:
- `src/Aouda.Server/Auth/Policy/ReadRowPolicy.cs`
- `tests/Aouda.Server.Tests/Authorization/Principals/PrincipalsS04ReadTests.cs`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| How quickly can an agent start a real DB? | Multi-step infra/bootstrap | `aouda start` + HTTP DB create and schema inference | Faster first successful action |
| How do auth defaults work for generated apps? | Inconsistent app-specific patterns | Built-in sign-up and sign-in; nothing is allowed until a statement says so | Lower security misconfiguration risk |
| Can a service act for a user? | Often custom proxy logic | The user's session, or a limited key minted from it, as the one credential | Easier secure backend mediation |
| Can authorization evolve beyond fixed JWT claims? | Usually requires external policy service | Attributes and row conditions, read from the store on each request | Dynamic permissions without fat JWTs |
| Are errors machine-actionable? | Generic text-only failures | Stable error codes + `remedy` + request id | Better agent retry/correction loops |

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
| `.NET AoudaCredential.Session(..., refreshThreshold)` | timespan | `2m` | positive | Client code | Proactive refresh threshold |
| TS `session.refreshThresholdMs` | number | `120000` | positive | `@aouda/client` | Proactive refresh threshold |
| `databases.<auth>.signup` | object | `{ "enabled": false, "roles": [], "statements": [] }` | ADR 0071 statements | `aouda.json` or `PUT /api/auth/{authDatabase}/signup` | What a signed-up principal may do |
| A statement's `where` | object | none (every row) | the `where` grammar, plus `"principal"` | `aouda.json` or the access routes | [Row conditions](../auth/authorization.md#row-conditions) |

Precedence and operational notes:
- Host config precedence: code defaults → optional appsettings → env → `AOUDA_*` → CLI (see [Server configuration](../guides/server-configuration.md)).
- Creating or linking an auth-enabled database mints no key.
- Token validation mode changes are startup/middleware configuration behavior.
- Auth route/admin policy changes are runtime dynamic.
- Safety-gated behavior:
  - a key or a session that does not resolve is refused (`401`), also on a route `anonymous` could have called;
  - a second credential on the request is refused `400`.
- Reserved/deferred:
  - no runtime config surface for MCP server tooling or NL query engine in this repo.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (a user signs in)

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    Credential = AoudaCredential.SignIn("alice@example.com", "Pass123!"),
});

var me = await client.WhoAmIAsync();
Console.WriteLine($"{me.Principal.Name} holds {me.Policy.Statements.Count} statements");
```

Expected result: the client signs in on the first request, and every call carries that user's session.

Common mistake: looking for a second option beside `Credential`. There is one: `Key`, `Session`, `SignIn` or `OidcExchange`.

### TypeScript example (an operator gives a user rows)

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  apiKey: process.env.AOUDA_OPERATOR_KEY,
});

const access = client.access.authDatabase("auth");
await access.principals.update("alice@example.com", {
  attributes: { orgs: ["org-a"] },
});
```

Expected result: the principal's attribute is replaced; statements whose `where` reads `attributes.orgs` admit those rows from Alice's next request.

Common mistake: providing both `apiKey` and `session.token` (a key and a signed-in session are two credentials; the constructor refuses). Browser login needs neither.

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
PATCH /api/auth/auth/principals/alice@example.com
Authorization: Bearer <an operator's key or session>
Content-Type: application/json

{
  "attributes": { "orgs": ["org-a"] }
}
```

Expected result: the first call returns a token pair; the second replaces Alice's attribute and needs `manage` on `auth/principal/alice@example.com`.

Common mistake: sending an application user's session to an operator's route. It is refused `403 AUTH_POLICY_DENIED` with the statement to grant as its `remedy`.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| Start local server | `aouda start` CLI | `aouda start` CLI | local HTTP service | Implemented | Auth via POST /api/databases |
| Create DB linked to an auth database | HTTP call from .NET/transport | `client.databases.create` | `POST /api/databases` with `auth.enabled` | Implemented | Mints no key |
| App auth sign-up/sign-in/refresh/password | `.NET` auth client | `client.auth.*` | `/api/databases/{db}/auth/*` | Implemented | Keyless public routes |
| Act for a user | The user's session, or `client.Auth.CreateLimitedKeyAsync` | The user's session, or `client.auth.createLimitedKey` | `POST /api/auth/keys` | Implemented | One credential per request |
| Principals, roles, `signup`, credentials | `client.Access` | `client.access.authDatabase(name)` | `/api/auth/{authDatabase}/…` | Implemented | [Access routes](../reference/http-api.md#access-routes) |
| Who am I, what may I do | `client.WhoAmIAsync()` | `client.whoami()` | `GET /api/auth/whoami` | Implemented | Both listeners |
| MCP auth tools | None | None | None | Missing | Planned in P12 Epic E / ADR 0017 intent |
| Natural-language query interface | None | None | None | Missing | ADR 0017 proposed only |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| First-class MCP server package and tools | No `@aouda/mcp-server` implementation in repo | Use CLI + HTTP/SDK directly | ADR 0017 + future tasking | High |
| Natural-language query tool/API | No NL query endpoint/tool in server/client | Build queries through existing query APIs | ADR 0017 proposed component | High |
| AI-oriented error fields (`mcpTool`, `docs`) | Not emitted by current `AuthErrorPayload` | Use `error` + `remedy` + `requestId` | P12 Epic E intent / future hardening | Medium |
| Cloud ephemeral provisioning endpoint | No public cloud provisioning API in repo | Run local dev server or self-hosted server | ADR 0017/0022 direction | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run AI local bootstrap

When to use:
- agent needs a working local database immediately.

Steps:
1. Run `aouda start --dev-admin` with `ASPNETCORE_ENVIRONMENT=Development`; read `key=` from the one printed line; configure email (`console` or `sendgrid`) if testing password reset.
2. Create the auth database and the data database (`POST /api/databases`), or declare both in `aouda.json`; enable `signup` with the statements a user needs.
3. Call app signup/signin via `/api/databases/{db}/auth/*`, with no credential.
4. Create table and insert/query data via HTTP or SDK, with the dev admin's key.

Expected checks:
- stdout contains the `AOUDA-DEV-ADMIN` line;
- sign-up answers a token pair, and `whoami` with it shows `source: signup`;
- data operations succeed with the key, and with the user's session where a statement allows them.

### Scenario 2: Backend mediation with user-context enforcement

When to use:
- backend service performs operations for user while preserving row/partition controls.

Steps:
1. Sign the user in (or receive the user's session), and connect a client that holds that session.
2. For one narrow call, mint a limited key from it instead (`createLimitedKey`).
3. Execute data query/write on tables whose statements have a `where`.
4. Verify results are scoped to the user's statements, not the backend's own.

Expected checks:
- the backend's own key sees what its own statements admit (with an unconditional `read`, every row);
- the user's session or a limited key minted from it sees only the user's rows;
- a revoked session yields `401 AUTH_CREDENTIAL_REVOKED`, and a limited key ends with its parent.

### Scenario 3: Evolve from a single value to a list

When to use:
- user needs access to multiple partition keys and one attribute value is insufficient.

Steps:
1. Change the statement's `where` from `"op": "eq"` to `"op": "in"` on the same attribute.
2. Set each user's attribute to the list.
3. Run the query without explicit partition filter.
4. Validate only listed partitions are returned.

Expected checks:
- `whoami` shows the statement with its `where` and the principal's attribute;
- fan-out query returns only granted partitions;
- a write outside the condition fails with `403 AUTH_ROW_DENIED`.

## 2.13 Operations and observability

Monitor first:
- auth gate failures:
  - `AUTH_CREDENTIAL_MISSING`,
  - `AUTH_KEY_MALFORMED`,
  - `AUTH_CREDENTIAL_INVALID`,
  - `AUTH_CREDENTIAL_EXPIRED`,
  - `AUTH_CREDENTIAL_REVOKED`.
- dev bootstrap behavior:
  - the `AOUDA-DEV-ADMIN` line on stdout (development only).
- policy health:
  - `AUTH_POLICY_DENIED` and `AUTH_ROW_DENIED` in the server log (each `403` is logged once with its remedy),
  - `STATEMENT_RESOURCE_UNKNOWN` and `STATEMENT_COLUMN_UNKNOWN` warnings from `aouda plan`.
- request-level diagnostics:
  - response `requestId`,
  - `X-Auth-Database` on relevant auth failures.

Recovery expectations:
- restart preserves auth metadata and policy state (auth DB tables persisted under normal server mode);
- policy changes propagate on subsequent requests (the auth database's permission version);
- token revocation behavior depends on selected validation mode (`Hybrid`/`Stateful` stronger than `SignatureOnly`).

Recommended tuning sequence:
1. Keep default `Hybrid` validation in most app flows.
2. Keep short access tokens and rely on refresh workflow.
3. Start from a built-in role and narrow it to statements per table and principal.

| Question | Practical answer |
|---|---|
| What is the safest default for generated apps? | No key in the browser; sign-in; `signup` statements with a `where`; middleware in `Hybrid` mode |
| How do I preserve user-level enforcement from backend jobs? | Send the user's session, or a limited key minted from it |
| How do I debug denied operations quickly? | Read the refusal's `remedy`, then `whoami`, then `aouda policy explain` |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `AUTH_CREDENTIAL_MISSING` on an app auth route | A non-public `/auth/*` path | Public signup/signin/refresh are keyless. `/password` and `/mfa/*` need a user's session. |
| `400 INVALID_REQUEST`: the header is no longer supported | A second credential on the request | Send the user's own token as the credential, or mint a limited key |
| A query returns too few rows | The statement's `where` admits fewer, or the attribute lacks a value | `whoami` shows both; add the value to the principal's attribute |
| Write denied on a row the caller can read | The `read` and `write` statements differ | Add a `write` statement with the `where`; the refusal's `remedy` is that statement |
| A row condition seems not applied | Another statement of the principal has no `where` (statements are a union), or the call is a named query, which reads its `execute` statement | `whoami` lists every statement with its origin (`from`) |
| Where is the key of the database I created? | Creating a database mints none | Mint one on a principal: `POST /api/auth/{authDatabase}/principals/{name}/keys` |

## 2.15 Verification ledger

Last verification date (UTC): `2026-04-01`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Dev server auth output tests | `dotnet test tests/Aouda.Cli.Tests --no-build --filter "FullyQualifiedName~DevServerIntegrationTests" --verbosity minimal` | Pass (`2/2`) | 2026-04-01 | Verifies the dev-admin line |
| TypeScript auth client/handler/integration | `npm test -- tests/auth-client.test.ts tests/auth-handler.test.ts tests/auth-integration.test.ts` (in `../aouda-client-ts`) | Pass (`72/72`) | 2026-04-01 | Confirms app/server auth client lifecycle and transport behavior |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| Dev bootstrap auth output UX | `tests/Aouda.Cli.Tests/DevServerIntegrationTests.cs` | Pass | Medium/Strong | Covers the dev-admin line |
| Public auth routes and statements | `tests/Aouda.Server.Tests/Auth/AppAuthPublicEntryTests.cs`, `tests/Aouda.Server.Tests/Authorization/Principals/` | Pass | Strong | Reads, writes, named artifacts, realtime |
| TS auth client lifecycle and wrappers | `../aouda-client-ts/tests/auth-client.test.ts`, `auth-handler.test.ts`, `auth-integration.test.ts` | Pass | Medium/Strong | Covers token lifecycle and auth API usage |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No end-to-end agent flow test chaining sign-up -> attribute -> scoped query in one script | Cross-surface regressions can hide between suites | Add a scenario test that declares an auth database and executes the full bootstrap flow | High |
| Limited explicit tests for error payload contract stability as an AI interface | Agents rely on stable fields for remediation loops | Add contract tests for `error/message/remedy/requestId` across auth failure types | High |
| No tests for future MCP compatibility adapters | Migration to MCP surface risks drift | Add adapter-contract tests once MCP layer exists | Medium |
| No dedicated test asserting absence/presence of `mcpTool`/`docs` fields by version | Prevents accidental undocumented contract changes | Add explicit payload schema version tests | Medium |

## 2.18 Known gaps and undone work

- MCP and NL query surfaces are still intent-level:
  - ADR 0017 defines these capabilities, but no runtime package/endpoints are shipped in this repo.
  - User impact: agents must use CLI/HTTP/SDK directly today.
- AI-friendly error payload is useful but incomplete relative to P12 Epic E intent:
  - current payload has `error/message/requestId/remedy`,
  - fields like `mcpTool` and `docs` are not emitted.
- Cloud ephemeral provisioning path is not present in current server:
  - distribution direction exists in ADR 0022, not as shipped endpoint in this workspace.

## 2.19 References

- ADRs:
  - `docs/decisions/0017-ai-native-interface.md`
  - `docs/decisions/0022-licensing-and-distribution-strategy.md`
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0071-principals-one-policy-language-one-key-format.md`
- Tasks/reports:
  - `docs/tasks/P12/P12-TwoLayerAuth-Tasks.md`
  - `docs/tasks/P12/P12-TwoLayer-S1-ApiKeyInfrastructure-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S2-MiddlewareAndAuthorization-Report.md`
  - `docs/tasks/P12/P12-TwoLayer-S4-DocumentationAndDX-Report.md`
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
  - `src/Aouda.Client/Auth/AoudaCredential.cs`
  - `src/Aouda.Client/Access/AccessAdminApi.cs`
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/auth/auth-types.ts`
  - `../aouda-client-ts/src/auth/auth-client.ts`
  - `../aouda-client-ts/src/types.ts`
- Tests:
  - `tests/Aouda.Server.Tests/Authorization/Principals/`
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
