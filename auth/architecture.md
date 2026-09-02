---
title: "Architecture"
nav_order: 1
parent: "Auth and Authorization"
---

# Auth Architecture Patterns & Deployment Scenarios

> Part of the [Application Auth Guide](Getting-Started-Auth.md). Start there for an overview.

---

## 5. Architecture Patterns

Aouda Application Auth supports five deployment patterns. Choose based on your application architecture.

### Pattern A: Backend-Mediated (Traditional)

Your backend is the only component that talks to Aouda. End users never connect directly.

```
┌──────────────┐     ┌────────────────────┐     ┌──────────────────┐
│  Frontend     │     │  Your Backend       │     │  Aouda            │
│  (React, etc.)│────→│  (Node.js, .NET)    │────→│                  │
│               │     │                    │     │  Auth: mk_svc_... │
│  Login form   │     │  POST /api/login    │     │  Data: orders,    │
│  API calls    │     │  Validate user...   │     │        products   │
│               │     │  Query Aouda        │     │                  │
└──────────────┘     └────────────────────┘     └──────────────────┘
```

**How it works:**
1. Backend connects to Aouda with the `service_role` key (`mk_svc_...`).
2. Frontend sends login requests to your backend.
3. Backend calls Aouda's auth endpoints to verify credentials.
4. Backend returns a JWT or session cookie to the frontend.
5. Backend queries Aouda for data, optionally with user context for PLS.

**When to use:** Most applications. This is the standard pattern — your backend controls all database access.

```typescript
// Backend: service key for full access
const db = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  appAuth: { apiKey: process.env.AOUDA_SERVICE_KEY },  // mk_svc_...
});

// Handle login from your frontend
app.post("/api/login", async (req, res) => {
  const result = await db.auth.signIn(req.body.email, req.body.password);
  res.json({ token: result.accessToken });
});

// Query data — full access (no PLS)
app.get("/api/admin/orders", async (req, res) => {
  const all = await db.table("orders").execute();
  res.json(all.rows);
});

// Query data — with user context (PLS enforced)
// Create a per-request client that forwards the user JWT via X-User-Token.
// There is no .withUserContext() method — PLS user context is set at client construction.
app.get("/api/my-orders", async (req, res) => {
  const userJwt = req.headers.authorization?.replace("Bearer ", "");
  const userScopedClient = createAoudaClient({
    serverUrl: "http://localhost:5433",
    database: "myapp",
    appAuth: {
      apiKey: process.env.AOUDA_SERVICE_KEY,  // mk_svc_... (service key)
      userToken: userJwt,                     // JWT from frontend → sent as X-User-Token
    },
  });
  const orders = await userScopedClient.table("orders").execute();
  res.json(orders.rows);
});
```

### Pattern B: Direct-to-Database (data-plane listener)

Frontend or mobile app talks directly to Aouda — through the **data-plane listener**, using **named queries**. No backend required for reads and simple writes.

> **Changed in P37 (server `0.1.7`).** Earlier versions of this page showed a browser holding `mk_anon_*` and calling `client.table("orders").execute()`. That is no longer the model, and it no longer works: `mk_anon_*` is denied on data routes, and ad-hoc `POST …/query` returns **404** on the data-plane for every credential. Browser-tier callers use `mk_pub_*` and name-identified named artifacts. See [Direct client access](../guides/direct-client-access.md).

```
┌──────────────────┐   TLS/WAF edge    ┌────────────────────────────┐
│  Frontend         │                   │  Aouda DATA-PLANE :5434    │
│  (React, mobile)  │───── directly ───→│  auth · named query ·      │
│                   │                   │  named mutation · ws       │
│  1. mk_pub_ key   │                   │  everything else → 404     │
│  2. User signin   │                   │  PLS/RLS: enforced         │
│  3. User JWT      │                   └────────────────────────────┘
└──────────────────┘                    ┌────────────────────────────┐
                                        │  ADMIN :5433 — not public  │
                                        └────────────────────────────┘
```

**How it works:**
1. Operators author queries in `aouda.schema.json` and `schema apply` them on the **admin** listener. Each definition's identity is its unique name; the frontend calls that string. Codegen of Args/Row types is optional.
2. Frontend connects to the **data-plane** URL with `mk_pub_*` (data + auth) or `mk_anon_*` (auth only). Both are safe to embed.
3. User signs up or signs in; the client switches to the user JWT.
4. Reads go through `namedQueries.execute` / `.batch`, writes through `namedMutations.execute`, live data through `subscribe` **by name**. PLS and RLS are applied underneath every one of them, with the caller's identity injected — never passed as an argument.

**When to use:** Mobile apps and SPAs where the read shapes are known and reviewable. It is a good default for product frontends; it is not a fit when the client genuinely needs to compose arbitrary queries — that surface stays on the admin listener for operators.

**Prerequisites:** the data-plane listener is configured, every table the frontend touches (including join tables) has `dataPlaneAccess: true`, and a thin edge terminates TLS in front of it.

```typescript
import { AoudaClient } from "@aouda/client";

// Frontend: publishable key (safe to expose), data-plane URL
const client = new AoudaClient({
  serverUrl: "https://data.example.com", // the data-plane listener behind TLS
  database: "myapp",
  appAuth: { apiKey: import.meta.env.VITE_AOUDA_PUB_KEY }, // mk_pub_...
});

await client.connect();

// User signs in — client stores the JWT internally
await client.auth.signIn("alice@example.com", "SecurePass123!");

// Reads — named query by name, PLS/RLS enforced, only alice's rows
const { rows } = await client.namedQueries.execute("orders.pending", {
  status: "pending",
});
```

**Not available to this pattern:** ad-hoc `table().execute()`, `admin/*`, `schema/apply`, and the write-stream — all **404** on the data-plane. `X-User-Token` stays a service-key feature. OAuth/PKCE is not shipped, so the sign-in above (email/password, optionally with MFA) is the supported browser login.

### Pattern C: Standalone Auth Service (Auth0/Clerk Replacement)

Use Aouda purely as an authentication service. No data tables — only the auth system.

```
┌──────────────────┐     ┌──────────────────┐
│  Your Backend     │────→│  Aouda            │
│  (handles data)   │     │  (auth only)      │
│                   │     │  mk_svc_...       │
│  Your own DB      │     │  No data tables   │
│  (Postgres, etc.) │     │                  │
└──────────────────┘     └──────────────────┘
```

**How it works:**
1. Your backend connects to Aouda with the service key.
2. Backend delegates signup/signin to Aouda's auth endpoints.
3. Aouda returns JWTs that your backend validates (standard RS256).
4. Your data lives elsewhere — Aouda is the identity provider only.

**When to use:** When you have an existing data layer but need self-hosted auth with in-memory performance.

```csharp
// Backend: use Aouda as auth service only
var authClient = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    AppAuth = new AppAuthOptions { ApiKey = "mk_svc_xyz789..." }
});

// Sign up users
var result = await authClient.Auth.SignUpAsync("new@example.com", "Pass123!");

// List and manage users — the .NET AuthClient exposes user lifecycle methods
// (SignUpAsync, SignInAsync, MeAsync, ChangePasswordAsync, etc.).
// Admin operations (list users, assign roles) are not yet wrapped as high-level
// methods in the .NET SDK (see known gaps). Use the HTTP admin endpoints directly:
//
//   POST  /api/databases/{db}/auth/admin/users
//   GET   /api/databases/{db}/auth/admin/users
//   PUT   /api/databases/{db}/auth/admin/users/{id}/roles
//
// Example via HttpClient or a raw transport call:
//   var response = await httpClient.GetAsync(
//       "http://localhost:5433/api/databases/myapp/auth/admin/users");
//   var users = await response.Content.ReadFromJsonAsync<...>();
```

### Pattern D: Hybrid (Frontend Auth + Backend Data)

Frontend handles auth flows directly with Aouda; backend handles data operations.

```
┌──────────────┐  auth ────→ ┌──────────────┐
│  Frontend     │             │  Aouda        │
│  (URL + db)   │             │  (keyless     │
│               │             │   signup/     │
│               │  JWT ─────→ │   signin)     │
│               │             │               │
│               │  data ────→ │  Your Backend │──→ Aouda (mk_svc_...)
└──────────────┘             └──────────────┘
```

**How it works:**
1. Frontend constructs `new AoudaClient({ serverUrl, database })` — no `mk_anon_*`. CORS on the data-plane listener is the browser origin control.
2. Frontend calls signup/signin directly. Self-registration is **off until enabled** (`allowSelfSignup`); enabled signups grant `db_writer` unless `selfSignupRole` is set (BL-357). Password reset can trigger outbound email at 20/min/IP.
3. After signin, the frontend sends the JWT to your backend.
4. Backend uses the service key + the user's JWT (`X-User-Token`) for PLS-scoped data queries. Pre-auth named queries still need `mk_pub_*` (BL-356).

**When to use:** When you want the auth UI to interact with Aouda directly but want your backend to control data access. Do not bake `mk_anon_*` / `NEXT_PUBLIC_AOUDA_ANON_KEY` into the SPA.

### Pattern E: Standalone Auth Service (Microservice Gateway)

Use a single dedicated auth database to issue and validate JWTs for multiple downstream services. The auth database is accessed directly — no proxy application database is needed.

```
                   ┌─────────────────────────────────────────┐
                   │            Aouda Server                  │
                   │                                          │
  Auth only ────►  │   Database: "auth"  (kind: "auth")       │
                   │   Endpoints: /api/databases/auth/auth/.. │
                   └──────────────────────┬───────────────────┘
                                          │
                          JWT (RS256, iss=.../auth, aud=auth)
                                          │
              ┌───────────────────────────┼──────────────────────────┐
              ▼                           ▼                          ▼
     Service A (orders)         Service B (payments)       Service C (notifications)
     Validates JWT via          Validates JWT via           Validates JWT via
     OIDC discovery             OIDC discovery              OIDC discovery
```

**How it works:**
1. Create one `auth` database with `kind: "auth"`. No other databases needed.
2. Auth endpoints are available at `/api/databases/auth/auth/...` — the `{db}` segment equals the auth database name.
3. After signup/signin, JWTs are issued with `iss = {server}/api/databases/auth` and `aud = auth`.
4. Any downstream service validates the JWT against the OIDC discovery endpoint.

**When to use:** Microservice architectures where auth is a separate concern; Auth0/Clerk replacement with self-hosted performance; organizations that want a single identity provider for multiple independent data services.

**Setup:**

```bash
# Create the standalone auth database
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "name": "auth", "kind": "auth" }'
# → Returns anonKey + serviceRoleKey. No second database is created.
```

**OIDC discovery:**

```
GET http://localhost:5433/api/databases/auth/auth/.well-known/openid-configuration
```

**.NET configuration in a downstream service (JWT Bearer):**

```csharp
// Program.cs — downstream service consuming Aouda auth JWTs
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = "http://localhost:5433/api/databases/auth";
        options.Audience  = "auth";
        options.RequireHttpsMetadata = false; // development only
    });
```

Or via `appsettings.json`:

```json
{
  "AoudaAuth": {
    "Authority":    "http://localhost:5433/api/databases/auth",
    "Audience":     "auth",
    "DatabaseName": "auth",
    "ServiceKey":   "mk_svc_..."
  }
}
```

---

### Choosing a Pattern

| Factor | Pattern A (Backend) | Pattern B (Direct) | Pattern C (Auth Only) | Pattern D (Hybrid) | Pattern E (Gateway) |
|--------|:---:|:---:|:---:|:---:|:---:|
| Backend required | Yes | No | Yes | Yes | Yes |
| Frontend touches Aouda | No | Yes | No | Auth only | No |
| Listener the client uses | Admin (internal) | **Data-plane** | Admin (internal) | Data-plane (auth) | Admin (internal) |
| Credential | `mk_svc_` | `mk_pub_` → user JWT | `mk_svc_` | `mk_anon_` → user JWT | `mk_svc_` |
| Query style | Ad-hoc or named | **Named only** (name identity) | N/A | Named for the client | Ad-hoc or named |
| PLS sufficient for security | N/A | Must be | N/A | Partially | N/A |
| Existing data layer | Optional | No | Yes | Optional | Yes (multiple services) |
| Best for | Most apps | Mobile, SPAs | Legacy apps | Complex apps | Microservices |

Patterns A and B are not exclusive, and the common end state is both: the frontend reads and subscribes on the data-plane through named artifacts, while a service holds a `mk_svc_` key on the admin listener for ingestion, scheduled work, and anything that legitimately needs to cross partitions. What that split should look like — and which of your existing hops stop earning their keep once B is available — is worked through in [Division of responsibility](../guides/division-of-responsibility.md) and [Adopting Aouda](../guides/adoption.md).

---

## 6. Deployment Scenarios

Aouda supports many different deployment configurations. This section maps each scenario to the right auth setup.

### Deployment Matrix

| Scenario | Server Auth | App Auth | API Keys | How to Set Up |
|----------|:-----------:|:--------:|:--------:|---------------|
| **Embedded mode** (in-process) | No | No | N/A | `AoudaEmbedded.OpenDatabaseAsync()` |
| **Local server** (prototyping) | Optional | No | N/A | `aouda start`; create DB via API (or declare in optional startup config) |
| **Local server with app auth** (testing auth flows) | Optional | Yes | `mk_anon_`, `mk_svc_` | `aouda start` + `POST /api/databases` with `auth.enabled` — see [setup.md](setup.md) |
| **Production — cache/internal** | Optional | No | `mk_srv_` if server auth | Create DB without `auth.enabled` |
| **Production — server auth only** | Yes | No | `mk_srv_` | Bootstrap admin, create DB, create server API keys |
| **Production — full stack** | Yes | Yes | `mk_srv_`, `mk_anon_`, `mk_svc_` | Bootstrap admin, create DB with `auth.enabled` |
| **AI agent development** | Optional | Optional | From create-database response | `aouda start` + create auth-enabled DB via API |

### Scenario 1: Embedded Mode (Zero Auth)

Your application embeds the Aouda engine in-process. No network, no server, no auth needed.

```csharp
await using var db = await AoudaEmbedded.OpenDatabaseAsync();
await db.GetTable("orders").InsertAsync(new { id = 1, total = 99.99 });
```

**Auth status:** Not applicable. Your process owns the database directly.

### Scenario 2: Local Server Without App Auth (Prototyping)

Start Aouda and create a database without `auth.enabled`. Good for prototyping data models and queries.

```bash
aouda start --port 5433 --data-dir ./data
# Create database via POST /api/databases (with server admin JWT if server auth is bootstrapped)
```

```bash
curl -X POST http://localhost:5433/api/databases/myapp/tables/orders/rows \
  -d '{ "rows": [{ "id": 1, "total": 99.99 }] }'
```

**Auth status:** No application auth. Protect with server auth in production.

### Scenario 3: Local Server With App Auth (Testing Auth Flows)

```bash
aouda start --port 5433 --data-dir ./data
# POST /api/databases with auth enabled — response includes mk_anon_ / mk_svc_ keys (once)
```

Configure [email/SMS on the server](notifications.md) when testing password reset or phone MFA. Use `Provider: console` locally when you do not have SendGrid/GatewayAPI credentials.

**Auth status:** App auth enabled. API keys come from the create-database response, not from CLI stdout.

### Scenario 4: Production — Internal/Cache Database

Databases for internal services, caching, or analytics that don't need end-user auth.

```bash
# With server auth (recommended for production)
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{ "name": "cache" }'

# Create a server API key for your service
curl -X POST http://localhost:5433/api/auth/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "name": "cache-service",
    "databaseRoles": { "cache": ["db_writer"] }
  }'
```

**Auth status:** Server auth protects access. No end-user auth needed.

### Scenario 5: Production — Full Stack (Server Auth + App Auth)

The complete setup for user-facing applications in production.

```bash
# 1. Bootstrap server admin (one-time)
curl -X POST http://localhost:5433/api/auth/setup \
  -d '{ "email": "admin@company.com", "password": "AdminPass123!" }'

# 2. Create database with app auth
TOKEN=$(curl -s http://localhost:5433/api/auth/signin \
  -d '{ "email": "admin@company.com", "password": "AdminPass123!" }' | jq -r .accessToken)

curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ "name": "production", "auth": { "enabled": true } }'
# → Returns anonKey + serviceRoleKey

# 3. Create a server API key for CI/CD or cross-database services
curl -X POST http://localhost:5433/api/auth/admin/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "ci-pipeline",
    "databaseRoles": { "production": ["db_admin"] }
  }'
```

**Auth status:** Server auth for infrastructure; App auth for end users. Both active simultaneously.

### Scenario 6: AI Agent Development

AI agents need zero-friction database setup. Aouda provides multiple friction levels:

**Level 0 — Just a database (zero app auth):**
```bash
aouda start --data-dir ./data
# Create DB via API — agent uses data endpoints immediately
```

**Level 1 — Database with app auth:**
```bash
aouda start --data-dir ./data
# POST /api/databases with auth → capture anon/service keys from JSON response
# For password reset testing, configure email on server — console or sendgrid (notifications.md)
```

**Level 2 — Full production simulation:**
```bash
# Agent bootstraps server admin, creates auth-enabled DB, creates server API keys
# Tests the complete production flow
```
