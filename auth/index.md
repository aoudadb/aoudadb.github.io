---
title: "Auth and Authorization"
nav_order: 3
has_children: true
---

# Aouda Functionality: Auth And Authorization

Document status: Approved baseline
Primary owner: Aouda maintainers
Last updated: 2026-05-22

Coverage phases: P12, P14
Primary task folders: `docs/tasks/P12/`, `docs/tasks/P14/`
Primary ADRs: `docs/decisions/0023-authentication-and-authorization.md`, `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
Related functionality docs: `docs/dev/Functionality-Overview.md`, `docs/dev/Getting-Started.md`, `docs/dev/Getting-Started-Auth.md`

## Start Here

**User guides (this site):**

- [Setup & flows](setup.md) — enable auth, API keys, signup/signin
- [Email, SMS & notifications](notifications.md) — SendGrid, GatewayAPI, password reset / MFA OTP
- [Use cases](use-cases.md) — onboarding, password reset, MFA
- [Reference](reference.md) — endpoints, errors, local developer setup (§27)

If your question is "How do I use auth in Aouda right now?", start with:
- `2.3 Defaults and zero-config behavior`
- `2.10 Configuration and settings reference`
- `2.11 API and CLI coverage reference`

If your question is "What is shipped vs partial vs missing?", jump to:
- `2.4 Availability status`
- `2.5 Phase coverage matrix`
- `2.6 Capability coverage matrix`
- `2.11 API and CLI coverage reference` (including missing API matrix)
- `2.18 Known gaps and undone work`

---

## 2.1 Why this functionality exists

Aouda authentication and authorization exists to solve two separate security problems with one coherent model:

- connection security: who is allowed to talk to the database endpoint at all;
- user identity and data security: which user is acting, and exactly what data they can read or mutate.

User and operational outcomes:

- A backend/service can connect with explicit machine credentials (API keys).
- End users can authenticate with standard signup/signin + JWT token lifecycle.
- Authorization can evolve dynamically without forcing "fat JWT" claim payloads.
- Multi-tenant isolation can run at partition level (PLS) and row level (RLS) with policy resolved from the auth database.
- Permission revocation can take effect near-immediately through permission-version invalidation.

Scope boundaries:

- This document covers server auth, app auth, RBAC, API key model, PLS, ADRA (`auth-db-pls`), and RLS (`auth-db-rls`).
- It does not claim OAuth/OIDC full provider parity; OIDC discovery/JWKS support is present for app auth metadata discovery.
- It does not claim external IdP federation or enterprise SSO flows as shipped features.

## 2.2 Discovery and navigation map

### Question -> section map

| If you need to know... | Go to section |
|---|---|
| What are auth defaults if I do nothing? | `2.3 Defaults and zero-config behavior` |
| What is available now vs planned vs reserved? | `2.4 Availability status` |
| Which phase delivered which part? | `2.5 Phase coverage matrix` |
| Full capability completeness and edges | `2.6 Capability coverage matrix` |
| Mental model for two-layer auth and ADRA | `2.7 Core concepts and mental model` |
| Runtime implementation path | `2.8 How Aouda implements it` |
| Every config knob and where set | `2.10 Configuration and settings reference`, [notifications.md](notifications.md) (email/SMS) |
| Password reset / invite / MFA OTP delivery | [notifications.md](notifications.md) |
| API/SDK coverage and missing surfaces | `2.11 API and CLI coverage reference` |
| Operational checks and incident handling | `2.13 Operations and observability`, `2.14 Troubleshooting by symptom` |
| Explicit undone work | `2.18 Known gaps and undone work` |

### Role-based map

| Role | Start with |
|---|---|
| App developer | `2.3`, `2.11`, `2.12` |
| Platform operator / DBA | `2.10`, `2.13`, `2.14`, `2.18` |
| SDK maintainer (.NET/TS) | `2.11`, `2.16`, `2.17` |
| Engine contributor | `2.5`, `2.6`, `2.8`, `2.19` |

### Source map

- Phase/task/report evidence:
  - `docs/tasks/P12-Authentication-Authorization-Tasks.md`
  - `docs/tasks/P12-AuthModel-TwoLayerAuth-Report.md`
  - `docs/tasks/P12-AuthCleanup-SeparateServerAndAppAuth-Report.md`
  - `docs/tasks/P12-TwoLayer-S1-ApiKeyInfrastructure-Report.md`
  - `docs/tasks/P12-TwoLayer-S2-MiddlewareAndAuthorization-Report.md`
  - `docs/tasks/P12-TwoLayer-S4-DocumentationAndDX-Report.md`
  - `docs/tasks/P14-ADRA-Tasks.md`
  - `docs/tasks/P14-TaskS1-AuthDbPermissionSchema.md`
  - `docs/tasks/P14-TaskS3-ADRA-Resolution-Layer-Report.md`
  - `docs/tasks/P14-TaskS4-EnhancedPLS.md`
  - `docs/tasks/P14-TaskS5-RowLevelSecurity.md`
  - `docs/tasks/P14-TaskS6-TypeScriptClientWrappers.md`
  - `docs/tasks/P14-TaskS7-GettingStartedAuthRewrite.md`
- Design references:
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
- Core code:
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
  - `src/Aouda.Server/Auth/AppAuthController.cs`
  - `src/Aouda.Server/Auth/AppAdminController.cs`
  - `src/Aouda.Server/Auth/ServerAuthController.cs`
  - `src/Aouda.Server/Auth/ServerAdminController.cs`
  - `src/Aouda.Engine.Auth/AuthDatabaseSchema.cs`
  - `src/Aouda.Engine.Auth/Adra/AdraResolutionService.cs`
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsResolverEvaluator.cs`
  - `src/Aouda.Engine.Auth/Permissions/PermissionVersionService.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
- Client surfaces:
  - `.NET`: `src/Aouda.Client/Auth/AuthClient.cs`, `src/Aouda.Client/Auth/AppAuthOptions.cs`, `src/Aouda.Client/Auth/ServerAuthOptions.cs`
  - TypeScript: `../aouda-client-ts/src/client.ts`, `../aouda-client-ts/src/auth/auth-client.ts`, `../aouda-client-ts/src/types.ts`
- Primary tests:
  - `tests/Aouda.Server.Tests/AuthenticationMiddlewareTests.cs`
  - `tests/Aouda.Server.Tests/AuthenticationMiddlewareIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/AuthEndpointContractIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/PermissionVersionServiceTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/RlsResolverEvaluatorTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/RlsWriteValidatorTests.cs`
  - `../aouda-client-ts/tests/auth.test.ts`
  - `../aouda-client-ts/tests/tables.auth-mode.test.ts`

## 2.3 Defaults and zero-config behavior

If you enable auth and keep defaults:

- access token lifetime defaults to 15 minutes;
- refresh token lifetime defaults to 30 days;
- JWT issuer defaults to `"aouda"` unless base URL/issuer override path sets a different runtime issuer context;
- token validation mode defaults to `Hybrid` in server middleware;
- password policy defaults to min length 8, max length 128;
- user lockout threshold defaults to 10 failed attempts with 15-minute lockout;
- app auth database creation defaults to `AuthDatabaseKind.Application`;
- default system roles are seeded: `db_admin`, `db_writer`, `db_reader`, `anonymous`;
- enabling app auth generates system anon/service keys (`mk_anon_...`, `mk_svc_...`) and keeps server key model (`mk_srv_...`) for server-side credentials.

| Setting / behavior | Default | Allowed values | Practical impact |
|---|---|---|---|
| `TokenOptions.AccessTokenLifetime` | `15 minutes` | Any positive `TimeSpan` | Short-lived bearer tokens reduce exposure window |
| `TokenOptions.RefreshTokenLifetime` | `30 days` | Any positive `TimeSpan` | Long-lived session continuity with rotation |
| `TokenOptions.Issuer` | `"aouda"` | Any non-empty string | Default `iss` when explicit issuer context not overridden |
| `AuthenticationMiddlewareOptions.ValidationMode` | `Hybrid` | `SignatureOnly`, `Hybrid`, `Stateful` | Signature + revocation checks by default |
| `PasswordPolicy.MinLength` | `8` | Integer ≥ 1 | Minimum user password length |
| `PasswordPolicy.MaxLength` | `128` | Integer ≥ `MinLength` | Upper bound for password size |
| `UserService.LockoutThreshold` | `10` | Positive integer | Locks after repeated bad credentials |
| `UserService.LockoutDuration` | `15 minutes` | Any positive `TimeSpan` | Temporary lockout cooldown window |
| `AuthDatabaseOptions.Kind` | `Application` | `Application`, `Server` | Explicit auth DB creation defaults to app auth kind |
| Default roles | `db_admin`, `db_writer`, `db_reader`, `anonymous` | Fixed (not configurable) | Baseline RBAC scaffolding seeded at auth DB creation |
| App auth API key gate | API key required on app auth routes | Fixed (not configurable) | Prevents direct JWT-only calling of signup/signin/refresh endpoints |

## 2.4 Availability status (implementation honesty)

### Available now

- Two-layer model:
  - Layer 1 connection gate via API key or bearer token evaluation in `AuthenticationMiddleware`.
  - Layer 2 user identity via JWT and session/revocation checks.
- Separate server and application auth planes:
  - server auth routes under `/api/auth/...`;
  - app auth routes under `/api/databases/{db}/auth/...`;
  - distinct server-auth database support (`AuthDatabaseKind.Server`).
- App auth user lifecycle:
  - signup, signin, signout, refresh, me, password change.
- Admin auth APIs:
  - server/admin user-role-key management;
  - app/admin user-role-key management plus ADRA partition grants and RLS resolvers.
- API key model:
  - reserved key kinds for system-managed anon/service-role keys;
  - role-scoped key grants and revocation model.
- RBAC:
  - default system roles + custom role CRUD + user-role assignment.
- PLS modes:
  - `jwt-claim` baseline mode;
  - `auth-db-pls` multi-valued grant resolution for fan-out and write checks.
- RLS mode:
  - `auth-db-rls` resolver/rule model with injected predicates and write-path validation.
- ADRA resolution + cache:
  - permission set resolution and per-session permission cache;
  - permission version invalidation via `_permission_version`.
- OIDC metadata:
  - app auth OIDC discovery and JWKS endpoints.
- Client integration:
  - .NET and TypeScript auth client flows;
  - TypeScript wrappers for ADRA admin APIs;
  - table schema/auth-mode type exposure (`authMode`, `permissionDimension`, `rlsResolverName`).

### Planned / proposed

- Additional AI-first auth tooling beyond current P12/P14 set (tracked in future backlog/tasks).
- Broader client parity for all admin/auth surfaces across all languages (today strongest ADRA wrapper coverage is TypeScript-side for P14 additions).
- Expanded docs/UX around enterprise-style identity provider integrations.

### Reserved / not yet wired

- Full OIDC/OAuth provider feature set is not wired; current implementation provides discovery/JWKS endpoints for app auth metadata and key publication.
- No claim of external federation workflows (for example social login or external IdP managed token exchange) as a shipped built-in Aouda capability.

## 2.5 Phase coverage matrix

| Phase | Tasks/Reports | Delivered capability | Undone/deferred | Backlog link |
|---|---|---|---|---|
| P12 | `P12-Authentication-Authorization-Tasks.md`, two-layer reports (S1/S2/S4), auth model and cleanup reports | Core auth engine, server/app auth split, API key gate, default anon/service key generation, app auth endpoints, .NET/TS client auth wiring, `aouda start` + API auth setup | Later fine-grained authorization model (ADRA deepening) deferred to P14 | `docs/BACKLOG.md` |
| P14 | `P14-ADRA-Tasks.md`, S1/S3/S4/S5/S6/S7 reports | Auth DB permission schema additions, ADRA resolution layer and cache, enhanced PLS (`auth-db-pls`), RLS (`auth-db-rls`), TypeScript ADRA wrappers, auth guide rewrite | Broader cross-SDK parity and future resolver extensions | `docs/BACKLOG.md` |

## 2.6 Capability coverage matrix

| Capability | Implemented | Partial | Missing | Primary evidence | Notes |
|---|---|---|---|---|---|
| Two-layer auth (connection key + user JWT) | Yes | No | No | P12 two-layer reports + `AuthenticationMiddleware.cs` | App auth endpoints enforce API key gate |
| Separate server auth vs app auth route planes | Yes | No | No | P12 auth cleanup report + `ServerAuthController.cs` / `AppAuthController.cs` | Distinct route scopes and auth DB resolution paths |
| System API key generation for app auth (`anon`, `service_role`) | Yes | No | No | P12 S1 report + `AuthDatabaseManager.cs` + `ApiKeyService.cs` | Uses reserved key kinds and prefixes |
| RBAC default roles and role CRUD | Yes | No | No | `DefaultRoleSeeder.cs`, `DefaultRoles.cs`, admin controllers | Includes user-role assignment APIs |
| App auth user lifecycle (signup/signin/refresh/signout/me/password) | Yes | No | No | `AppAuthController.cs` + integration tests | Includes lockout, revocation, audit writes |
| Server auth user lifecycle | Yes | No | No | `ServerAuthController.cs` | Mirrors app auth endpoints for server auth plane |
| JWT validation modes (SignatureOnly/Hybrid/Stateful) | Yes | No | No | `AuthenticationMiddleware.cs` | Default is `Hybrid` |
| `X-User-Token` impersonation with service keys | Yes | No | No | P12 S2 report + middleware + integration tests | Rejects invalid/revoked user token |
| PLS `jwt-claim` single-dimension behavior | Yes | No | No | ADR 0023 + enforcer/tests | Baseline mode |
| ADRA `auth-db-pls` multi-valued grants | Yes | No | No | P14 S4 + schema + enforcer | Supports fan-out and write-level grant checks |
| ADRA `auth-db-rls` resolver-based RLS | Yes | No | No | P14 S5 + RLS evaluator/injector/validator | Includes group-aware predicate composition |
| Permission version invalidation (`_permission_version`) | Yes | No | No | P14 S1 + `PermissionVersionService.cs` | Supports fast permission refresh behavior |
| OIDC discovery + JWKS | Yes | No | No | `OidcDiscoveryController.cs` | Public app-auth well-known endpoints |
| TypeScript ADRA admin wrappers | Yes | No | No | P14 S6 + `auth-client.ts` | Partition grants + RLS resolver wrappers present |
| .NET SDK wrappers for ADRA admin APIs | No | Yes | No | .NET `AuthClient` vs app admin endpoints | Current .NET auth client focuses user auth lifecycle |

## 2.7 Core concepts and mental model

- Layer 1 (connection auth):
  - evaluates bearer value as API key or JWT;
  - gates whether request may enter protected data/auth APIs.
- Layer 2 (user identity):
  - app or server user JWT identifies user principal for role and policy evaluation.
- Auth database kinds:
  - application auth database (`AuthDatabaseKind.Application`) for app user auth;
  - server auth database (`AuthDatabaseKind.Server`) for server-admin plane.
- API key kinds:
  - `anon`, `service_role`, and custom.
  - system-managed keys reserve key kinds for default app connection models.
- RBAC:
  - role memberships + permission rows define baseline operation rights.
- PLS:
  - partition-level security at table dimension boundary.
- ADRA:
  - resolves dynamic permission state from auth database (not only token claims).
- RLS:
  - row-level predicate rules resolved and injected into query/update/delete paths.
- Permission version:
  - global auth DB counter for revocation freshness.

Invariants:

- App auth endpoints require API key when app auth database is linked.
- `auth-db-pls` requires `permissionDimension`; `auth-db-rls` requires `rlsResolverName`.
- Service-key + `X-User-Token` impersonation flow must still validate/revocation-check user token.
- Empty or unsupported complex resolver shapes fail closed instead of broadening access.

## 2.8 How Aouda implements it

High-level runtime pipeline:

1. Request enters `AuthenticationMiddleware`.
2. Request scope resolved (`ServerAuth`, `AppAuth`, `AppAdmin`, `Data`).
3. Bearer inspected:
   - API key path: validates key hash/roles;
   - JWT path: validates signature and mode-dependent session/revocation.
4. For service-key + `X-User-Token`, effective user token is validated and promoted to context.
5. Auth DB name is attached to request context (`Aouda.AuthDatabase` item).
6. For data paths in ADRA-enabled tables:
   - middleware + resolution services build `PermissionContext`;
   - PLS/RLS enforcers inject/validate query/write constraints.
7. Controllers execute using resolved principal and auth DB context.

Key modules:

- Request auth and token mode control:
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- User auth endpoints:
  - `src/Aouda.Server/Auth/AppAuthController.cs`
  - `src/Aouda.Server/Auth/ServerAuthController.cs`
- Admin/authz endpoints:
  - `src/Aouda.Server/Auth/AppAdminController.cs`
  - `src/Aouda.Server/Auth/ServerAdminController.cs`
- Auth schema and bootstrap:
  - `src/Aouda.Engine.Auth/AuthDatabaseSchema.cs`
  - `src/Aouda.Engine.Auth/AuthDatabaseManager.cs`
  - `src/Aouda.Engine.Auth/Bootstrap/DefaultRoleSeeder.cs`
- ADRA + RLS:
  - `src/Aouda.Engine.Auth/Adra/AdraResolutionService.cs`
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsResolverEvaluator.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsPredicateInjector.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsWriteValidator.cs`
- Permission invalidation:
  - `src/Aouda.Engine.Auth/Permissions/PermissionVersionService.cs`

## 2.8.1 Critical path walk-throughs (implementation-level)

### Walk-through A: App user sign-in with two-layer gate

1. Client calls `POST /api/databases/{db}/auth/signin` with `Authorization: Bearer <api_key>`.
2. `AuthenticationMiddleware` identifies `AppAuth` scope and enforces API key bearer shape.
3. `AppAuthController.Signin` validates body and resolves linked app auth engine.
4. `UserService.VerifyCredentialAsync` validates password and lockout state.
5. `TokenService.MintTokenPairAsync` creates access/refresh tokens.
6. `SessionService.CreateSessionAsync` persists token hash session.
7. `WarmAdraPermissionCacheAsync` kicks off permission cache warmup for this token hash.
8. Response returns user + tokens.

Primary evidence:
- `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
- `src/Aouda.Server/Auth/AppAuthController.cs`
- `tests/Aouda.Server.Tests/AuthenticationMiddlewareIntegrationTests.cs`

### Walk-through B: Data query on `auth-db-pls` table

1. Request reaches auth middleware and user principal is resolved.
2. ADRA resolution service computes allowed partitions for user/dimension.
3. `PartitionSecurityEnforcer` checks table `AuthorizationMode`.
4. For `auth-db-pls`, enforcer validates query partition predicates against allowed grants.
5. For fan-out allowed keys, enforcer composes safe `Where.Or` shape.
6. Query executes against constrained partition set.

Primary evidence:
- `src/Aouda.Engine.Auth/Adra/AdraResolutionService.cs`
- `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
- `docs/tasks/P14-TaskS4-EnhancedPLS.md`
- `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`

### Walk-through C: RLS resolver enforcement on update/delete

1. Table configured with `authMode` and `rlsResolverName`.
2. Request principal resolves to `PermissionContext`.
3. `RlsResolverEvaluator` builds row predicate (or null for admin pass-through).
4. `RlsPredicateInjector` merges predicate groups into request `WhereClause`.
5. `RlsWriteValidator` validates write row/set against evaluator semantics.
6. Controller proceeds only if resulting constrained operation remains authorized.

Primary evidence:
- `src/Aouda.Engine.Auth/Rls/RlsResolverEvaluator.cs`
- `src/Aouda.Engine.Auth/Rls/RlsPredicateInjector.cs`
- `src/Aouda.Engine.Auth/Rls/RlsWriteValidator.cs`
- `docs/tasks/P14-TaskS5-RowLevelSecurity.md`

### Walk-through D: Permission change and near-instant revocation

1. Admin updates grants/roles/resolvers via app admin endpoints.
2. Permission-layer service increments `_permission_version`.
3. Next request for affected session compares cached version vs current.
4. Cache refresh path resolves updated permission set from auth DB.
5. Query/write authorization now reflects latest permission state.

Primary evidence:
- `src/Aouda.Engine.Auth/Permissions/PermissionVersionService.cs`
- `src/Aouda.Server/Auth/AppAdminController.cs`
- `docs/tasks/P14-TaskS1-AuthDbPermissionSchema.md`
- `docs/tasks/P14-TaskS3-ADRA-Resolution-Layer-Report.md`

## 2.9 Why Aouda is different (differentiators)

| Capability question | Typical systems | Aouda approach | User impact |
|---|---|---|---|
| Connection credential vs user credential separation | Often conflated or app-managed manually | Two-layer model built into server middleware and client SDKs | Clear threat boundaries and safer defaults |
| Dynamic authorization freshness | JWT claim refresh latency often minutes+ | ADRA auth-DB resolution + permission-version invalidation | Fast permission propagation without full re-login |
| Multi-partition authorization | Often custom logic outside DB | `auth-db-pls` dimension grants with fan-out enforcement | Native multi-tenant/multi-region permission routing |
| Row-level constraints | Heavy policy engines or per-row external lookups | In-memory resolver rules injected into query predicates | Fine-grained control with low latency cost |
| AI-agent onboarding | Multi-step auth setup friction | `aouda start` + API database create, generated anon/service keys, explicit error hints | Faster "auth-on" path for generated apps and tooling |
| Password reset / invite OTP delivery | External email service required per app | Server-level SendGrid integration (`Aouda:Auth:Email`) | One provider config for all app auth DBs on the server |
| MFA phone OTP | External SMS per app | Server-level GatewayAPI integration (`Aouda:Auth:Sms`) | Same as email — shared infrastructure |

## 2.10 Configuration and settings reference (complete surface)

| Setting | Type | Default | Allowed values | Where set | Notes |
|---|---|---|---|---|---|
| `Aouda:Auth:RootUser:Email` | string? | `null` | valid email | `appsettings.json` / env | Optional root bootstrap user email |
| `Aouda:Auth:RootUser:Password` | string? | `null` | non-empty string | `appsettings.json` / env | Plaintext bootstrap only; remove after first setup |
| `Aouda:Auth:Email:Provider` | string? | `null` | `sendgrid` enables SendGrid; otherwise null (no send) | `appsettings.json` / `Aouda__Auth__Email__*` env | Password reset + invite emails; see [notifications.md](notifications.md) |
| `Aouda:Auth:Email:SendGridApiKey` | string? | `null` | SendGrid API key | same | Bearer token for `api.sendgrid.com` |
| `Aouda:Auth:Email:FromAddress` | string? | `null` | verified sender email | same | Required for delivery |
| `Aouda:Auth:Email:FromName` | string? | `"Aouda"` | display name | same | From header display name |
| `Aouda:Auth:Sms:Provider` | string? | `null` | `gatewayapi` enables GatewayAPI; otherwise null | `appsettings.json` / `Aouda__Auth__Sms__*` env | MFA phone OTP only; see [notifications.md](notifications.md) |
| `Aouda:Auth:Sms:ApiKey` | string? | `null` | GatewayAPI token | same | `Authorization: Token` header |
| `Aouda:Auth:Sms:Sender` | string? | `"Aouda"` | sender label | same | Shown on SMS |
| `Aouda:BaseUrl` | string? | `null` | URL | server config | Used for app auth issuer/discovery URL construction |
| `AuthenticationMiddlewareOptions.ValidationMode` | enum | `Hybrid` | `SignatureOnly`, `Hybrid`, `Stateful` | middleware options | Token validation strictness |
| `TokenOptions.AccessTokenLifetime` | timespan | `15m` | positive timespan | auth engine service config | Access token expiry window |
| `TokenOptions.RefreshTokenLifetime` | timespan | `30d` | positive timespan | auth engine service config | Refresh token validity window |
| `TokenOptions.Issuer` | string | `"aouda"` | non-empty | auth engine service config | JWT issuer claim default |
| `PasswordPolicy.MinLength` | int | `8` | >= 1 | auth engine service config | Password policy minimum |
| `PasswordPolicy.MaxLength` | int | `128` | >= MinLength | auth engine service config | Password policy maximum |
| `UserService.LockoutThreshold` | int | `10` | positive | auth engine code-level options | Failed-attempt lockout trigger |
| `UserService.LockoutDuration` | timespan | `15m` | positive | auth engine code-level options | Account lock interval |
| `AuthDatabaseOptions.Kind` | enum | `Application` | `Application`, `Server` | auth DB create APIs | Distinguishes `_auth`-style vs `_serverauth` style DBs |
| Table `authMode` | string | `jwt-claim` | `jwt-claim`, `auth-db-pls`, `auth-db-rls` | table create/update payload | Authorization mode per table |
| Table `permissionDimension` | string? | `null` | non-empty when needed | table payload | Required for `auth-db-pls` |
| Table `rlsResolverName` | string? | `null` | existing resolver name | table payload | Required for `auth-db-rls` |

Precedence and operational notes:

- Server config precedence follows standard `appsettings` + env + CLI binding in host setup.
- Root user bootstrap is startup-time behavior; treat config updates as restart-required.
- Auth/admin endpoint changes (users, roles, grants, resolvers) are dynamic at runtime.
- Safety-gated behavior:
  - app auth endpoints reject missing API key in app-auth scope (`AUTH_API_KEY_REQUIRED`);
  - reserved system key kinds (`anon`, `service_role`) are blocked from generic custom key creation APIs.
- Reserved/deferred:
  - no public claim that external IdP federation knobs are active in server config as a shipped feature.

## 2.11 API and CLI coverage reference (complete + gap-aware)

### .NET example (application auth flow)

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5000",
    DatabaseName = "appdb",
    AppAuth = new AppAuthOptions
    {
        ApiKey = "mk_anon_...",
    }
});

var auth = await client.Auth.SignInAsync("user@site.com", "correct horse battery staple");
var me = await client.Auth.MeAsync();
Console.WriteLine($"{me.Email} {auth.ExpiresIn}");
```

Expected result: sign-in returns access/refresh tokens, and subsequent calls use the authenticated user context.

Common mistake: providing both `ApiKey` and `Token` in `AppAuthOptions` (validation rejects mutually exclusive setup).

### TypeScript example (app auth + ADRA admin wrapper)

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
  appAuth: { apiKey: "mk_svc_..." }
});

await client.auth.signIn("admin@app.com", "p@ssword123");
const resolvers = await client.auth.listRlsResolvers({ targetTable: "orders" });
console.log(resolvers.length);
```

Expected result: authenticated session and successful RLS resolver query via `/auth/admin` wrapper path.

Common mistake: using `client.auth` without configuring `serverAuth` or `appAuth`.

### HTTP/protocol examples

```http
POST /api/databases/appdb/auth/signin
Authorization: Bearer mk_anon_xxxxx
Content-Type: application/json

{
  "email": "user@app.com",
  "password": "p@ssword123"
}
```

```http
POST /api/databases/appdb/auth/admin/users/{userId}/partition-grants
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "dimension": "tenant_id",
  "partitionKey": "tenant-a",
  "accessLevel": "write"
}
```

Expected result: first call mints tokens, second call creates ADRA partition grant for user.

Common mistake: trying to call app auth endpoints with a JWT-only bearer and no API key in app-auth scope.

### A) API coverage matrix

| Capability | .NET API | TypeScript API | HTTP/Protocol | Status | Notes |
|---|---|---|---|---|---|
| App signup/signin/signout/refresh/me/password | `Aouda.Client.Auth.AuthClient` | `client.auth.signUp/signIn/signOut/refresh/me/changePassword` | `/api/databases/{db}/auth/*` | Implemented | End-to-end user flow available |
| Server auth signin/signout/refresh/me/password | .NET `ServerAuthOptions` + auth pipeline | TS supports `serverAuth` option pathing | `/api/auth/*` | Implemented | Server admin auth plane |
| Role/user/admin management (server) | HTTP-first; .NET client can call raw admin endpoints | HTTP-first | `/api/auth/admin/*` | Partial | No first-class high-level SDK convenience wrapper parity |
| Role/user/key management (app admin) | HTTP-first; can be called from .NET transport | TS includes auth admin wrappers for P14 additions | `/api/databases/{db}/auth/admin/*` | Partial | Strong TS wrapper coverage for partition grants + RLS resolvers |
| Partition grant admin APIs | No dedicated typed wrapper in .NET auth client | `create/list/deletePartitionGrant` | `.../admin/users/{id}/partition-grants` | Partial | Transport-level .NET possible, dedicated helper absent |
| RLS resolver admin APIs | No dedicated typed wrapper in .NET auth client | `create/list/get/update/deleteRlsResolver` | `.../admin/rls-resolvers` | Partial | TS wrappers added in P14 S6 |
| Table auth mode config (`jwt-claim` / `auth-db-pls` / `auth-db-rls`) | Table create/update DTOs | `CreateTableRequest.authMode` and related fields | table create/update policy payloads | Implemented | Validation enforced in server/catalog |
| OIDC discovery / JWKS | HTTP consumption | HTTP consumption | `/.well-known/openid-configuration`, `/.well-known/jwks.json` | Implemented | Public app-auth metadata endpoints |

### B) Missing API matrix

| Intended capability | Missing API surface | Current workaround | Planned source | Priority |
|---|---|---|---|---|
| Dedicated .NET wrappers for ADRA admin endpoints (partition grants + RLS resolvers) | High-level `Aouda.Client.Auth` methods analogous to TS wrappers | Call HTTP admin endpoints directly via transport/client internals | Follow-up SDK parity tasks after P14 | High |
| Unified SDK parity for all server/admin auth operations | Full strongly-typed convenience APIs in both .NET and TS for all admin endpoints | Use HTTP endpoints directly where wrapper absent | Future auth SDK hardening work | Medium |
| External IdP/federated auth integration APIs | Provider config/metadata management APIs | Use native Aouda auth flows today | Future architecture/tasking (not P12/P14 shipped scope) | Medium |

## 2.12 Scenario playbooks (minimum three)

### Scenario 1: First-run local app auth enablement

When to use:
- starting a new local app and you want auth enabled with minimum setup.

Steps:
1. Start server (`aouda start`), create auth-enabled database via API, configure email if testing password reset ([notifications.md](notifications.md)).
2. Confirm generated auth summary includes auth DB and anon/service key hints.
3. Use anon key to call `POST /api/databases/{db}/auth/signup`.
4. Sign in and store returned tokens in client.

Expected result checks:
- app database is linked to an auth database;
- signup/signin succeed with API key + credentials;
- authenticated reads/writes work according to assigned roles.

### Scenario 2: Production-safe migration from `jwt-claim` to `auth-db-pls`

When to use:
- users require access to multiple partitions (multi-tenant operator, region fan-out).

Steps:
1. Define table `authMode = auth-db-pls` with `permissionDimension`.
2. Create partition grants for pilot users through app admin API.
3. Validate read fan-out and write access-level enforcement on non-prod traffic.
4. Roll out grant migration user cohort by user cohort.

Expected result checks:
- users only access granted partition keys;
- unauthorized partition writes fail with explicit auth errors;
- cross-partition behavior matches grants, not stale token claims.

### Scenario 3: Introduce row-level resolver policy

When to use:
- partition isolation is not enough; row-level ownership/attribute constraints are required.

Steps:
1. Create RLS resolver and ordered rules in app admin API.
2. Set table `authMode = auth-db-rls` and `rlsResolverName`.
3. Execute controlled read/update/delete operations as target user and admin user.
4. Confirm denied writes and constrained reads for non-admins.

Expected result checks:
- non-admin user sees only rows matching resolver predicate;
- admin pass-through path remains unrestricted where intended;
- write validation blocks out-of-policy updates/inserts.

## 2.13 Operations and observability

Monitor first:

- auth failures by type:
  - invalid token,
  - revoked token,
  - API key required/invalid,
  - account locked.
- auth DB health and availability:
  - linked auth DB resolution success,
  - auth table integrity (`_sessions`, `_revoked_tokens`, `_permission_version`).
- permission refresh indicators:
  - permission-version increments after grant/role/resolver changes,
  - cache refresh behavior during next requests.
- incident-level auth clues:
  - `X-Auth-Database` response headers on auth failures where provided,
  - request id in auth error payloads for trace correlation.

Recovery expectations:

- Token/session revocations are immediate for stateful checks and near-immediate under hybrid mode with revocation table checks.
- Permission updates apply on next request via permission version refresh path.
- Restart preserves auth DB state because sessions/revocations and auth metadata are persisted in auth tables.

Recommended tuning/operation sequence:

1. Keep token validation in `Hybrid` unless strict stateful constraints are required.
2. Use short access token lifetime and rely on refresh path.
3. Roll out ADRA grants/resolvers incrementally with test users before broad enablement.

| Question | Practical answer |
|---|---|
| Which auth mode should I start with? | Start with `jwt-claim`, then move to `auth-db-pls` / `auth-db-rls` when dynamic permissions are needed |
| How do I force quick permission propagation? | Use ADRA permission changes that increment `_permission_version` and rely on next-request refresh |
| How do I debug "why was this denied"? | Inspect auth error code + request id + relevant grant/resolver rows in auth DB |

## 2.14 Troubleshooting by symptom

| Symptom | Likely cause | What to do |
|---|---|---|
| `AUTH_API_KEY_REQUIRED` on app auth endpoint | Request in app-auth scope did not use API key bearer | Send anon/service API key in `Authorization: Bearer` for app auth routes |
| Sign-in keeps failing then returns account locked | Exceeded lockout threshold | Wait lockout duration or re-enable user via admin API |
| User has new grants but behavior still old briefly | Cached permission context not yet refreshed for session | Trigger next request and verify `_permission_version` increment happened |
| `auth-db-pls` table rejects write unexpectedly | Grant exists but `access_level` is read-only or partition key not granted | Update partition grant to proper key and `write` access level |
| RLS seems ignored for a table | Resolver not attached or table mode misconfigured | Verify `rlsResolverName` and `authMode` in table schema, then retest with non-admin user |
| Service key + `X-User-Token` request returns 401 | User token invalid/revoked/expired | Refresh user token and retry; ensure service key kind supports impersonation flow |

## 2.15 Verification ledger

Last verification date (UTC): `2026-03-31`.

| Verification scope | Command | Result | Date (UTC) | Notes |
|---|---|---|---|---|
| Documentation/code alignment review for auth defaults/routes | N/A (code-audit pass over auth/server/client files) | Pass | 2026-03-31 | Confirmed defaults and route shapes from current source |
| Middleware gate and token mode behavior | N/A (test evidence referenced) | Not run in this doc pass | 2026-03-31 | Covered by `AuthenticationMiddleware*` test suites listed in section 2.16 |
| ADRA PLS/RLS path behavior | N/A (test evidence referenced) | Not run in this doc pass | 2026-03-31 | Covered by P14-era tests listed in section 2.16 |

## 2.16 Test coverage matrix

| Capability | Test files / suites | Current status | Coverage strength | Notes |
|---|---|---|---|---|
| App auth API key gate enforcement and scope detection | `tests/Aouda.Server.Tests/AuthenticationMiddlewareTests.cs` | Pass (historically in phase reports) | Strong | Includes app auth protected-path classification updates |
| Middleware integration incl. `X-User-Token` and revoked token behavior | `tests/Aouda.Server.Tests/AuthenticationMiddlewareIntegrationTests.cs` | Pass (historically in phase reports) | Strong | Includes revoked `X-User-Token` regression test |
| Auth endpoint contract behavior with/without linked auth DB | `tests/Aouda.Server.Tests/AuthEndpointContractIntegrationTests.cs` | Pass (historically in phase reports) | Medium/Strong | Clarifies pass-through behavior when auth DB not linked |
| PLS enforcement and service-key bypass auditing | `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs` | Pass (historically in phase reports) | Strong | Includes cross-partition requirement nuance |
| Permission version increment/read semantics | `tests/Aouda.Engine.Auth.Tests/PermissionVersionServiceTests.cs` | Pass | Medium/Strong | Validates `_permission_version` contract |
| RLS resolver composition and edge-shape handling | `tests/Aouda.Engine.Auth.Tests/RlsResolverEvaluatorTests.cs` | Pass | Strong | Includes regression paths from P14 S5 review fixes |
| RLS write-path enforcement semantics | `tests/Aouda.Engine.Auth.Tests/RlsWriteValidatorTests.cs` | Pass | Strong | Covers write-authorization checks |
| TypeScript auth lifecycle + wrapper behavior | `../aouda-client-ts/tests/auth.test.ts` and P14 wrapper tests | Pass (historically in phase reports) | Medium | Confirms SDK-level call mapping and token handling |

## 2.17 Testing gaps and proposed tests

| Gap | Why it matters | Proposed test | Priority |
|---|---|---|---|
| No single end-to-end suite exercising full two-layer flow + ADRA + RLS in one scenario | Cross-layer regressions can slip between isolated test suites | Add integrated scenario: signup/signin -> grant changes -> RLS update -> read/write assertions | High |
| Limited explicit parity tests across .NET and TS clients for same admin auth operations | SDK divergence risk for auth/admin behavior | Add shared contract tests that run identical admin grant/resolver sequences from both SDKs | High |
| OIDC discovery/JWKS contract tests not highlighted in broad auth matrix | Public metadata endpoints are critical for integrations | Add dedicated server contract tests for issuer/base-url and key rotation visibility | Medium |
| Verification ledger is documentation-maintainer driven | Risk of stale verification status | Add CI-produced auth verification artifact and link in this section | Medium |

## 2.18 Known gaps and undone work

_Updated 2026-04-08 after P14/P16 completion._

### Resolved gaps

- ~~Service key PLS bypass audit logging for DML~~ — ✅ **Resolved (P14, BL-041)**: `TablesController` emits service-key PLS bypass audit entries for insert/update/delete.
- ~~WebSocket CORS enforcement~~ — ✅ **Resolved (P14, BL-050)**: WebSocket `Origin` validated against CORS policy.
- ~~No server admin key management API~~ — ✅ **Resolved (P16, SA3b)**: `ServerAdminKeysController` at `/api/auth/admin/keys` — create (`mk_srv_` prefix), list, revoke. Unified auth middleware covers all `/admin/*`, `/api/admin/*`, `/api/server/*` paths.
- ~~Hub authentication~~ — ✅ **Resolved (P16 Epic B)**: Aouda Hub provides user accounts (email/password, JWT), organizations with role-based access (owner/admin/member/viewer), and credential vault for server API keys. Studio Hub integration supports two-backend auth flow. See `docs/dev/Functionality-Cloud-And-Hub.md` §6.
- ~~Studio admin key management UI~~ — ✅ **Resolved (P16, D.17)**: view, create, revoke server admin API keys from Studio settings.

### Remaining gaps

- SDK parity gap:
  - .NET auth client has user lifecycle methods but no first-class ADRA admin wrappers equivalent to TypeScript's `create/list/deletePartitionGrant` and RLS resolver methods.
  - user impact: .NET consumers may rely on raw HTTP/admin transport for advanced authz configuration.
- Federation/enterprise auth gap:
  - external IdP federation workflows are not documented as shipped first-class Aouda functionality. BL-043 (OAuth PKCE) and BL-042 (token introspection) explicitly deferred until needed.
  - user impact: teams needing external identity federation must build integration patterns around current primitives.
- Continued auth DX hardening:
  - P12/P14 delivered core model and ADRA depth, but broader admin API ergonomics and advanced guidance remain future improvements.

## 2.19 References

- ADRs:
  - `docs/decisions/0023-authentication-and-authorization.md`
  - `docs/decisions/0025-adra-auth-db-resolved-authorization.md`
- Task docs/reports:
  - `docs/tasks/P12-Authentication-Authorization-Tasks.md`
  - `docs/tasks/P12-AuthModel-TwoLayerAuth-Report.md`
  - `docs/tasks/P12-AuthCleanup-SeparateServerAndAppAuth-Report.md`
  - `docs/tasks/P12-TwoLayer-S1-ApiKeyInfrastructure-Report.md`
  - `docs/tasks/P12-TwoLayer-S2-MiddlewareAndAuthorization-Report.md`
  - `docs/tasks/P12-TwoLayer-S4-DocumentationAndDX-Report.md`
  - `docs/tasks/P14-ADRA-Tasks.md`
  - `docs/tasks/P14-TaskS1-AuthDbPermissionSchema.md`
  - `docs/tasks/P14-TaskS3-ADRA-Resolution-Layer-Report.md`
  - `docs/tasks/P14-TaskS4-EnhancedPLS.md`
  - `docs/tasks/P14-TaskS5-RowLevelSecurity.md`
  - `docs/tasks/P14-TaskS6-TypeScriptClientWrappers.md`
  - `docs/tasks/P14-TaskS7-GettingStartedAuthRewrite.md`
- Related docs:
  - `docs/dev/Functionality-Overview.md`
  - `docs/dev/Getting-Started.md`
  - `docs/dev/Getting-Started-Auth.md`
- Server/engine code:
  - `src/Aouda.Server/Auth/AuthenticationMiddleware.cs`
  - `src/Aouda.Server/Auth/AppAuthController.cs`
  - `src/Aouda.Server/Auth/AppAdminController.cs`
  - `src/Aouda.Server/Auth/ServerAuthController.cs`
  - `src/Aouda.Server/Auth/ServerAdminController.cs`
  - `src/Aouda.Server/Auth/OidcDiscoveryController.cs`
  - `src/Aouda.Engine.Auth/AuthDatabaseSchema.cs`
  - `src/Aouda.Engine.Auth/AuthDatabaseManager.cs`
  - `src/Aouda.Engine.Auth/ApiKeys/ApiKeyService.cs`
  - `src/Aouda.Engine.Auth/Adra/AdraResolutionService.cs`
  - `src/Aouda.Engine.Auth/PLS/PartitionSecurityEnforcer.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsResolverEvaluator.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsPredicateInjector.cs`
  - `src/Aouda.Engine.Auth/Rls/RlsWriteValidator.cs`
  - `src/Aouda.Engine.Auth/Permissions/PermissionVersionService.cs`
  - `src/Aouda.Engine.Auth/Models/TokenOptions.cs`
  - `src/Aouda.Engine.Auth/Models/PasswordPolicy.cs`
  - `src/Aouda.Server/Configuration/AuthOptions.cs`
  - `src/Aouda.Server/Configuration/AoudaServerOptions.cs`
  - `src/Aouda.Protocol/Schema/TableMessages.cs`
- SDK code:
  - `src/Aouda.Client/Auth/AuthClient.cs`
  - `src/Aouda.Client/Auth/AppAuthOptions.cs`
  - `src/Aouda.Client/Auth/ServerAuthOptions.cs`
  - `../aouda-client-ts/src/client.ts`
  - `../aouda-client-ts/src/auth/auth-client.ts`
  - `../aouda-client-ts/src/types.ts`
- Tests:
  - `tests/Aouda.Server.Tests/AuthenticationMiddlewareTests.cs`
  - `tests/Aouda.Server.Tests/AuthenticationMiddlewareIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/AuthEndpointContractIntegrationTests.cs`
  - `tests/Aouda.Server.Tests/PartitionLevelSecurityEnforcementIntegrationTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/PermissionVersionServiceTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/RlsResolverEvaluatorTests.cs`
  - `tests/Aouda.Engine.Auth.Tests/RlsWriteValidatorTests.cs`
  - `../aouda-client-ts/tests/auth.test.ts`
  - `../aouda-client-ts/tests/tables.auth-mode.test.ts`

## 2.20 What is missing from this document? (meta completeness)

- This document maps complete domain-level functionality and major call paths, but it does not include per-method API contract listings for every admin DTO field.
- Verification ledger is evidence-referenced rather than fresh command execution in this doc-writing pass; next revision should include CI-backed command rows where available.
- If additional auth admin wrappers are added to .NET SDK, section `2.11` and the missing API matrix must be updated immediately.
