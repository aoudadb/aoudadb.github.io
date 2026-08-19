---
title: "Client Integration"
nav_order: 3
parent: "Auth and Authorization"
---

# Auth Client Integration

> Part of the [Application Auth Guide](../getting-started/auth.md). Start there for an overview.
>
> **Notifications:** Password reset, invite email, and MFA SMS are configured on the **Aouda server** (`Aouda:Auth:Email`, `Aouda:Auth:Sms`), not in client SDK options. See [Email, SMS & Notifications](notifications.md).
>
> **BFF / gateway pattern:** If your backend proxies auth operations on behalf of browser users, see [§14 — BFF / Gateway Proxying Auth Endpoints](#14-bff--gateway-proxying-auth-endpoints). For **data**, prefer [named queries](../guides/named-queries.md) on the [data-plane listener](../guides/direct-client-access.md) instead of a reshaping gateway. Auth and data endpoints use different header conventions — mixing them is the most common integration mistake.

---

## 10. Integrating with the .NET Client

The .NET client supports the two-layer model: API key for connection (Layer 1), then optional user sign-in (Layer 2).

### AppAuthOptions vs ServerAuthOptions

The .NET client uses two separate options types — one per auth system:

| Property | `AppAuthOptions` | `ServerAuthOptions` |
|----------|:-:|:-:|
| `ApiKey` | Yes (`mk_anon_`, `mk_pub_`, `mk_svc_`, custom) | Yes (`mk_srv_`) |
| `Token` / `RefreshToken` | Yes | Yes |
| `Email` / `Password` | **Not available** — use `SignInAsync()` | Yes |
| `UserToken` | Yes (with service keys) | Yes (with `mk_srv_`) |

Use `AppAuth = new AppAuthOptions { ... }` for Application Auth (this document). Use `ServerAuth = new ServerAuthOptions { ... }` for [Server Auth](Getting-Started.md#8-server-authentication--securing-database-access). The two are mutually exclusive — setting both throws an `ArgumentException` at construction time.

### Backend: Service Key (Full Access)

```csharp
using Aouda.Client;
using Aouda.Client.Auth;

var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    AppAuth = new AppAuthOptions
    {
        ApiKey = Environment.GetEnvironmentVariable("AOUDA_SERVICE_KEY")  // mk_svc_...
    }
});

// Full database access — no user sign-in needed
var allOrders = await client.GetTable("orders").Limit(10).ToListAsync();

// Admin operations — the .NET AuthClient exposes user lifecycle methods only.
// High-level admin wrappers (list users, assign roles) are not yet in the .NET SDK.
// Use the HTTP admin endpoints directly:
//   GET /api/databases/{db}/auth/admin/users
//   PUT /api/databases/{db}/auth/admin/users/{id}/roles
```

### Backend: Service Key + User Context (PLS Enforcement)

```csharp
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    AppAuth = new AppAuthOptions
    {
        ApiKey = "mk_svc_x7y8z9...",
        UserToken = userJwtFromFrontend  // JWT from frontend request
    }
});

// Queries are PLS-scoped to the user identified by the JWT
var userOrders = await client.GetTable("orders").Limit(10).ToListAsync();
```

### Frontend: Anon Key + User Sign-In

```csharp
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    AppAuth = new AppAuthOptions
    {
        ApiKey = "mk_anon_a1b2c3..."
    }
});

// User signs in — separate step from creating the client
var result = await client.Auth.SignInAsync("alice@example.com", "SecurePass123!");
// Client stores JWT internally, uses it for subsequent requests
// Auto-refreshes before expiry, retries on 401

var orders = await client.GetTable("orders").Limit(10).ToListAsync();
// PLS-scoped to alice
```

### Pre-Obtained Token

```csharp
var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    AppAuth = new AppAuthOptions
    {
        Token = "eyJhbGciOiJSUzI1NiIs...",
        RefreshToken = "dGhpcyBp..."  // Optional — enables auto-refresh
    }
});
```

### Server Admin Access (Different Auth System)

To access the **server auth** system (e.g. creating databases, managing server users), use `ServerAuth = new ServerAuthOptions { ... }`. This routes the client to `/api/auth/...` endpoints instead of `/api/databases/{db}/auth/...`.

```csharp
var adminClient = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5433",
    DatabaseName = "myapp",
    ServerAuth = new ServerAuthOptions
    {
        Email = "admin@example.com",
        Password = "AdminPass123!"  // Email+Password only available in ServerAuthOptions
    }
});
```

---

## 11. Integrating with the TypeScript Client

The TypeScript client uses `appAuth` for Application Auth endpoints (`/api/databases/{db}/auth/...`) and `serverAuth` for Server Auth endpoints (`/api/auth/...`). The two are mutually exclusive. User sign-in is always explicit via `client.auth.signIn()` — there is no `email`/`password` option in the constructor.

### Backend: Service Key

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  appAuth: {
    apiKey: process.env.AOUDA_SERVICE_KEY,  // mk_svc_... — KEEP SECRET
  },
});

await client.connect();
const allOrders = await client.table("orders").limit(10).execute();
```

### Backend: Service Key + User Context

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  appAuth: {
    apiKey: process.env.AOUDA_SERVICE_KEY,
    userToken: req.headers["x-user-token"],  // JWT from frontend
  },
});
```

### Frontend: Anon Key + Sign-In

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
  appAuth: {
    apiKey: process.env.NEXT_PUBLIC_AOUDA_ANON_KEY,  // mk_anon_...
  },
});

await client.connect();
const session = await client.auth.signIn("alice@example.com", "SecurePass123!");
// Client switches to user JWT for all subsequent requests

const orders = await client.table("orders").limit(10).execute();
// PLS-scoped to alice
```

### Frontend Pattern (React / Next.js)

```typescript
// lib/aouda.ts — singleton client
import { createAoudaClient } from "@aouda/client";

export const aouda = createAoudaClient({
  serverUrl: process.env.NEXT_PUBLIC_AOUDA_URL ?? "http://localhost:5433",
  database: "myapp",
  appAuth: { apiKey: process.env.NEXT_PUBLIC_AOUDA_ANON_KEY },
});

// pages/signup.tsx
import { aouda } from "@/lib/aouda";

async function handleSignUp(email: string, password: string) {
  const { user } = await aouda.auth.signUp(email, password);
  // Client stores JWT — subsequent data queries use it
}

// components/OrderList.tsx
const orders = await aouda.table("orders")
  .where("status", "=", "pending")
  .execute();
// PLS scopes results to the signed-in user's partition
```

### Auth Operations (Both Languages)

```typescript
// Sign up
const result = await client.auth.signUp("newuser@example.com", "Password123!");

// Sign in
const session = await client.auth.signIn("alice@example.com", "SecurePass123!");

// Profile
const me = await client.auth.me();

// Change password
await client.auth.changePassword("OldPass123!", "NewPass456!");

// Sign out
await client.auth.signOut();
```

---

## 12. API Keys and Credential Types

Aouda has **four** API key types. Understanding when to use each is critical.

### The API Key Types

| Key Type | Prefix | Created By | Scope | Stored In | Use Case |
|----------|--------|-----------|-------|-----------|----------|
| **Server API key** | `mk_srv_` | Server admin (`/api/auth/admin/api-keys`) | One or more databases | `_serverauth` | Backend services, CI/CD, cross-database access |
| **App `anon` key** | `mk_anon_` | Auto-generated on `auth.enabled` | One database | `_auth` | Browser **auth only** — signup, signin, refresh, OIDC |
| **App `public` key** | `mk_pub_` | Auto-generated on `auth.enabled` | One database | `_auth` | Browser **data** — named queries, mutations, subscriptions (plus auth) |
| **App `service_role` key** | `mk_svc_` | Auto-generated on `auth.enabled` | One database | `_auth` | Per-database backend access, admin tools |

Additionally, **custom app API keys** (`mk_` prefix) can be created via the admin API for granular access control.

`mk_pub_` arrived with the data-plane listener in server `0.1.7`. `mk_anon_` is **denied on data routes** — if you are giving a frontend read access, that is `mk_pub_`, on the data-plane, through [named queries](../guides/named-queries.md). Full rules: [Direct client access](../guides/direct-client-access.md).

### When to Use Which Key

| Need | Best Key | Why |
|------|----------|-----|
| Frontend reading data directly | App `public` key (`mk_pub_`) | Safe to expose; named artifacts only; PLS/RLS enforced; data-plane only |
| Frontend that only signs users in (data goes through your backend) | App `anon` key (`mk_anon_`) | Safe to expose; auth endpoints only |
| Backend accessing one database (app auth enabled) | App `service_role` key (`mk_svc_`) | Full access to that database, PLS bypassed |
| Backend accessing multiple databases | Server API key (`mk_srv_`) | Can have roles across multiple databases |
| CI/CD pipeline | Server API key (`mk_srv_`) | Scoped to test databases |
| Admin tooling | Server admin JWT or server API key | Full control |

### Comparison: Server Keys vs App Keys

| | Server API Keys (`mk_srv_`) | App API Keys (`mk_anon_`, `mk_pub_`, `mk_svc_`) |
|---|---|---|
| **Created by** | Server admin | Auto-generated when app auth is enabled |
| **Stored in** | `_serverauth` database | `_auth` database (linked to the app) |
| **Scope** | One or more databases (via `databaseRoles`) | One specific database |
| **PLS** | Never enforced (server-level access) | `mk_anon_` / `mk_pub_`: enforced; `mk_svc_`: bypassed |
| **Listener** | Admin | `mk_pub_`: data-plane only (admin → `AUTH_KEY_LISTENER_MISMATCH`); others: either |
| **Use case** | Backend services, CI/CD, cross-database | Frontend clients, per-database backend access |

### Creating Server API Keys

```bash
curl -X POST http://localhost:5433/api/auth/admin/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "myapp-backend",
    "databaseRoles": {
      "myapp": ["db_writer"],
      "analytics": ["db_reader"]
    }
  }'
# Returns: { "key": "mk_srv_abc123...", ... }
```

### Creating Custom App API Keys

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "name": "analytics-pipeline", "roles": ["db_reader"] }'
# Returns: { "key": "mk_xyz789...", ... }
```

---

## 13. Backend User-Context: X-User-Token

When a backend uses a service key (`mk_svc_` or `mk_srv_`) but needs to enforce PLS on behalf of a specific user, it can pass the user's JWT in the `X-User-Token` header.

### How It Works

```
Authorization: Bearer mk_svc_xyz789...     ← Service key (connection auth)
X-User-Token: eyJhbGciOiJSUzI1NiIs...     ← User JWT (for PLS enforcement)
```

The middleware:
1. Validates the service key (Layer 1 — connection authorized).
2. Validates the user JWT from `X-User-Token`.
3. Applies PLS using the user JWT's claims (tenant_id, user_id).
4. RBAC still uses the service key's roles (full access).

### Rules

- `X-User-Token` is only accepted when the primary credential is a **service-level key** (`mk_svc_` or `mk_srv_`).
- If the primary credential is an `anon` key or a user JWT, `X-User-Token` is ignored.
- If `X-User-Token` is present but invalid (expired, revoked), the request returns 401 with a clear error about the user token.
- If `X-User-Token` is absent, the service key grants full access with PLS bypassed.

### Example: Backend Querying on Behalf of a User

```bash
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer mk_svc_xyz789..." \
  -H "X-User-Token: eyJhbGciOiJSUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{ "database": "myapp", "table": "orders", "limit": 10 }'
# Returns only orders in the user's partition
```

---

## 14. BFF / Gateway Proxying Auth Endpoints

When your application has a backend-for-frontend (BFF) or API gateway that sits between the browser and Aouda, the auth routing rules are different for **data endpoints** vs **auth endpoints**.

### The Two Patterns

| Operation | Correct pattern |
|-----------|----------------|
| **Data queries / mutations** | BFF uses service key (`mk_svc_`) + `X-User-Token: <userJwt>` — BFF authenticates itself, user context enforced via header |
| **Auth endpoints** (signin, me, signout, MFA) | BFF **forwards the user JWT directly** as `Authorization: Bearer <userJwt>` — the user's session is the primary credential |

> **Key rule:** `X-User-Token` is only processed when the primary credential is a service-level key (`mk_svc_` or `mk_srv_`). For auth endpoints, the server expects the user JWT as the primary `Authorization` credential. Sending `Authorization: Bearer mk_svc_...` + `X-User-Token: <userJwt>` to an auth endpoint will authenticate you as the service key, not as the user — which is wrong for `me`, `signout`, and `mfa/*`.

### What to Do in a BFF

```
┌─────────────┐      ┌─────────────────────┐      ┌────────────────┐
│  Browser     │      │  Your BFF            │      │  Aouda         │
│              │      │                      │      │                │
│  signin ──  ─┼─────►│  POST /login          │      │                │
│              │      │  Use mk_anon_ key  ──┼─────►│  auth/signin   │
│              │      │  ← aal1 JWT          │◄─────┤                │
│  ← JWT    ◄──┼──────┤  forward to browser  │      │                │
│              │      │                      │      │                │
│  mfa/challenge──────┼─►POST /mfa-challenge │      │                │
│  with aal1 JWT│     │  forward user JWT ──┼─────►│  auth/mfa/     │
│              │◄─────┼─ forward response    │◄─────┤  challenge     │
│              │      │                      │      │                │
│  data query ─┼─────►│  GET /api/orders     │      │                │
│  with aal2   │      │  mk_svc_ +          ─┼─────►│  query         │
│  JWT         │      │  X-User-Token: jwt   │◄─────┤                │
└─────────────┘      └─────────────────────┘      └────────────────┘
```

#### BFF sign-in endpoint (C# example)

```csharp
// BFF: POST /login — proxies to Aouda signin
app.MapPost("/login", async (HttpContext ctx, HttpClient aoudaHttp) =>
{
    var body = await ctx.Request.ReadFromJsonAsync<SigninRequest>();

    // Use anon key for signin — same as a direct browser call
    var request = new HttpRequestMessage(HttpMethod.Post,
        "http://localhost:5433/api/databases/myapp/auth/signin");
    request.Headers.Authorization =
        new AuthenticationHeaderValue("Bearer", _anonKey);
    request.Content = JsonContent.Create(body);

    var response = await aoudaHttp.SendAsync(request);
    var json = await response.Content.ReadAsStringAsync();

    // Forward the raw response (including accessToken, mfaRequired, mfaFactors) to the browser
    ctx.Response.StatusCode = (int)response.StatusCode;
    ctx.Response.ContentType = "application/json";
    await ctx.Response.WriteAsync(json);
});
```

#### BFF MFA challenge endpoint (C# example)

```csharp
// BFF: POST /mfa/challenge — forwards user JWT to Aouda
app.MapPost("/mfa/challenge", async (HttpContext ctx, HttpClient aoudaHttp) =>
{
    // The browser passes its aal1 JWT in Authorization
    var userJwt = ctx.Request.Headers.Authorization.ToString()
        .Replace("Bearer ", "", StringComparison.OrdinalIgnoreCase);

    var body = await ctx.Request.ReadFromJsonAsync<MfaChallengeRequest>();

    var request = new HttpRequestMessage(HttpMethod.Post,
        "http://localhost:5433/api/databases/myapp/auth/mfa/challenge");

    // Forward the user JWT directly — do NOT replace it with the service key
    request.Headers.Authorization =
        new AuthenticationHeaderValue("Bearer", userJwt);
    request.Content = JsonContent.Create(body);

    var response = await aoudaHttp.SendAsync(request);
    var json = await response.Content.ReadAsStringAsync();

    ctx.Response.StatusCode = (int)response.StatusCode;
    ctx.Response.ContentType = "application/json";
    await ctx.Response.WriteAsync(json);
});
```

#### Common mistakes

| Mistake | What happens | Fix |
|---------|-------------|-----|
| Send `Authorization: Bearer mk_svc_...` to `/auth/mfa/challenge` | Server authenticates as the service account, not the user — MFA factor lookup fails or returns wrong user | Forward the user JWT instead |
| Send `Authorization: Bearer mk_svc_...` + `X-User-Token: <userJwt>` to `/auth/mfa/challenge` | `X-User-Token` is ignored for auth endpoints; request fails as service account identity | Forward user JWT in Authorization directly |
| Use raw `HttpClient` with only the user JWT in Authorization for MFA | Works as intended for direct browser-to-Aouda calls, but may fail if the BFF constructs requests incorrectly | Verify the JWT is the sign-in `accessToken`, not an API key |
| Call `GET /mfa/factors` after sign-in to get the `factorId` | Unnecessary extra round-trip | Use `mfaFactors` from the sign-in response directly |

### Choosing the Right Client Mode (AoudaClient SDK)

For BFF code that proxies auth operations, prefer calling Aouda's HTTP endpoints directly over constructing an `AoudaClient` for each user session — the SDK's `AppAuthOptions` does not support a combination of API key + pre-obtained user token simultaneously.

| Scenario | Approach |
|----------|---------|
| Proxy signin/signout/me/mfa from browser → Aouda | Forward HTTP requests with user JWT in Authorization |
| Backend data queries scoped to user | Use `AoudaClient` with `AppAuthOptions { ApiKey = serviceKey, UserToken = userJwt }` |
| Backend admin operations | Use `AoudaClient` with `AppAuthOptions { ApiKey = serviceKey }` |
