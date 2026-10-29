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

The .NET client supports keyless browser login: URL + database is enough, then `SignInAsync`. Backends still pass `ApiKey` (`mk_svc_*`).

### AppAuthOptions vs ServerAuthOptions

The .NET client uses two separate options types — one per auth system:

| Property | `AppAuthOptions` | `ServerAuthOptions` |
|----------|:-:|:-:|
| `ApiKey` | Optional (`mk_svc_*` for backends; not required for browser login) | Yes (`mk_srv_`) |
| `Token` / `RefreshToken` | Yes | Yes |
| `Email` / `Password` | **Not available** — use `SignInAsync()` | Yes |
| `UserToken` | Yes (with service keys) | Yes (with `mk_srv_`) |

Use `AppAuth = new AppAuthOptions { ... }` for Application Auth (this document). Use `ServerAuth = new ServerAuthOptions { ... }` for [Server Auth](../getting-started/index.md#8-server-authentication--securing-database-access). The two are mutually exclusive — setting both throws an `ArgumentException` at construction time.

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
// So are subscriptions (BL-1223, next train): the socket carries the user token too
```

### Frontend: URL + database + Sign-In

```csharp
var client = new AoudaClient("http://localhost:5433", "myapp");

var result = await client.Auth.SignInAsync("alice@example.com", "SecurePass123!");
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

### Frontend: URL + database + Sign-In

```typescript
const client = new AoudaClient({
  serverUrl: "http://localhost:5433",
  database: "myapp",
});

await client.connect();
const session = await client.auth.signIn("alice@example.com", "SecurePass123!");
```

### Frontend Pattern (React / Next.js)

```typescript
// lib/aouda.ts — singleton client
import { createAoudaClient } from "@aouda/client";

export const aouda = createAoudaClient({
  serverUrl: process.env.NEXT_PUBLIC_AOUDA_URL ?? "http://localhost:5433",
  database: "myapp",
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

// Sign in — deviceInfo names this device in the user's session list (NativeClients, 0.4.0)
const session = await client.auth.signIn("alice@example.com", "SecurePass123!", { deviceInfo: "Alice's iPhone — MyApp 2.1" });

// Profile
const me = await client.auth.me();

// Change password
await client.auth.changePassword("OldPass123!", "NewPass456!");

// Sign out — this device only (NativeClients, 0.4.0; before, every session of the user)
await client.auth.signOut();
// … or every other device (this one stays signed in), or everywhere
await client.auth.signOut({ scope: "others" });
await client.auth.signOut({ scope: "global" });

// The user's devices, and signing one of them out
const sessions = await client.auth.listSessions();   // [{ id, deviceInfo, userAgent, ipAddress, createdAt, lastSeenAt, aal, current }]
await client.auth.revokeSession(sessions.find((s) => !s.current)!.id);
```

C#: `SignInAsync(email, password, deviceInfo)`, `SignOutAsync(SignOutScope.Others)`, `ListSessionsAsync()`, `RevokeSessionAsync(id)`.
What a session is, and what ends one: [Sessions are devices](reference.md#sessions-are-devices).

### Keeping tokens across restarts (**NativeClients, 0.4.0**)

Each refresh **rotates** the refresh token, and presenting a spent one again ends the whole session (it is treated as stolen). An
app that persists only the token it got at sign-in therefore signs the user out on its first restart after a refresh. Persist the
pair on every change — both SDKs tell you each one (sign-in, every refresh including the automatic ones, sign-out) — and seed the
restarted client from what you stored:

```typescript
const stop = client.auth.onTokensChanged(({ accessToken, refreshToken, reason }) => {
  if (reason === "signedOut") secureStore.delete("aouda");
  else secureStore.set("aouda", JSON.stringify({ accessToken, refreshToken }));
});

// On the next start
const saved = JSON.parse(secureStore.get("aouda"));
const client = new AoudaClient({ serverUrl, database, appAuth: { token: saved.accessToken, refreshToken: saved.refreshToken } });
```

```csharp
client.Auth.TokensChanged += (_, e) => store.Save(e.AccessToken, e.RefreshToken);   // e.Reason: SignedIn, Refreshed, SignedOut
var restarted = new AoudaClient(new AoudaClientOptions { ServerUrl = url, DatabaseName = db,
    AppAuth = new AppAuthOptions { Token = saved.AccessToken, RefreshToken = saved.RefreshToken } });
```

When a refresh is refused because the session is over — `AUTH_REFRESH_TOKEN_INVALID` (ended, or a reused token) or
`AUTH_ACCOUNT_DISABLED` — the SDKs clear their tokens and report `signedOut` / `SignedOut`, so the app deletes what it stored rather than
re-seeding a dead pair on every start. An explicit `refresh()` / `RefreshAsync()` rejects with that code; a transient refusal (`503`)
keeps the tokens for a retry. Sign-out refreshes an expired access token first; `signOut({ scope: "others" | "global" })` rejects
when the server ended nothing, while a plain `signOut()` stays best-effort.

Listeners run synchronously, before the new tokens are used; any number may subscribe (`onTokensChanged` returns the
unsubscribe). A listener that throws is ignored — store failures are the app's to handle — and a listener must not refresh.
Where to keep them is the app's choice (Keychain, Android Keystore / SecureStore, DPAPI); never `localStorage` for a native app.

---

## 12. API Keys and Credential Types

Aouda has **four** API key types. Understanding when to use each is critical.

### The API Key Types

| Key Type | Prefix | Created By | Scope | Stored In | Use Case |
|----------|--------|-----------|-------|-----------|----------|
| **Server API key** | `mk_srv_` | Server admin (`/api/auth/admin/api-keys`) | One or more databases | `_serverauth` | Backend services, CI/CD, cross-database access |
| **App `anon` key** | `mk_anon_` | Auto-generated on `auth.enabled` | One database | `_auth` | **Not required for login.** Leftover; denied on data/admin |
| **App `public` key** | `mk_pub_` | Auto-generated on `auth.enabled` | One database | `_auth` | Browser **data** — named queries, mutations, subscriptions (plus auth) |
| **App `service_role` key** | `mk_svc_` | Auto-generated on `auth.enabled` | One database | `_auth` | Per-database backend access, admin tools |

Additionally, **custom app API keys** (`mk_` prefix) can be created via the admin API for granular access control. A `custom` key can optionally be **linked to a user** (`userId` at creation) — the key then inherits that user's `auth-db-pls` partition-grants and RBAC roles, giving a non-interactive service a durable credential scoped to exactly the partitions it needs, without the full-database bypass of `mk_svc_`. See [Data Authorization §19.4.5](authorization.md#1945-durable-credentials-for-non-interactive-services) and the [`POST .../admin/api-keys` reference](reference.md).

`mk_pub_` arrived with the data-plane listener in server `0.1.7`. Signup/signin/refresh/password-reset are **keyless**. `mk_anon_` is **denied on data routes** — if you are giving a frontend read access before login, that is `mk_pub_`, on the data-plane, through [named queries](../guides/named-queries.md). Full rules: [Direct client access](../guides/direct-client-access.md).

Enabling auth on a database does **not** open public self-registration. Set `allowSelfSignup: true` (create-database, or `PUT …/auth/admin/signup-settings`) to allow `POST …/auth/signup`. Enabled signups grant `db_writer` unless `selfSignupRole` names another existing role. CORS on the data-plane is the browser origin control; `CorsOrigins: "*"` lets any origin call those POSTs. Password reset can send email unauthenticated at 20/min/IP (`request-password-reset` does not disclose whether the account exists).

### When to Use Which Key

| Need | Best Key | Why |
|------|----------|-----|
| Frontend reading data directly | App `public` key (`mk_pub_`) | Safe to expose; named artifacts only; PLS/RLS enforced; data-plane only |
| Frontend that only signs users in (data goes through your backend) | None — `new AoudaClient({ serverUrl, database })` | Signup/signin are public POSTs |
| Backend accessing one database (app auth enabled) | App `service_role` key (`mk_svc_`) | Full access to that database, PLS bypassed |
| Non-interactive service that should see only specific partitions (a feeder job, a scoped integration) | `custom` key linked to a user (`userId`) | Durable like `mk_svc_`, but genuinely scoped via `auth-db-pls` partition-grants — not a bypass |
| Backend accessing multiple databases | Server API key (`mk_srv_`) | Can have roles across multiple databases; from 0.4.0 PLS / RLS apply to it (send `X-User-Token`, or use each database's `mk_svc_`, to read protected tables) |
| CI/CD pipeline | Server API key (`mk_srv_`) | Scoped to test databases |
| Admin tooling | Server admin JWT or server API key | Full control |

### Comparison: Server Keys vs App Keys

| | Server API Keys (`mk_srv_` admin, `mk_` scoped) | App API Keys (`mk_anon_`, `mk_pub_`, `mk_svc_`) |
|---|---|---|
| **Created by** | Server admin | Auto-generated when app auth is enabled |
| **Stored in** | `_serverauth` database | `_auth` database (linked to the app) |
| **Scope** | `mk_srv_` (`/api/auth/admin/keys`): every database, always `db_admin`; scoped `mk_` (`/api/auth/admin/api-keys`): each role's `scope` | One specific database |
| **PLS / RLS** | **Enforced** from 0.4.0 (**0.4.0**); up to 0.3.x never enforced | `mk_anon_` / `mk_pub_` / `custom`: enforced; `mk_svc_`: bypassed |
| **Listener** | Admin | `mk_pub_`: data-plane only (admin → `AUTH_KEY_LISTENER_MISMATCH`); others: either |
| **Use case** | Backend services, CI/CD, cross-database | Frontend clients, per-database backend access |

**What changed in 0.4.0** (**0.4.0**). Only an app's service key (`mk_svc_`) bypasses partition- and row-level security.
A server API key (`mk_srv_`) did too up to 0.3.x; it now gets its role's grants and, on a protected table, only what a request
with no user may see — with the usual RLS rules, no row; on a PLS table `403`, unless its role is `db_admin` and the read asks
for `"crossPartitionAccess": true` (audited). For a whole database use that database's `mk_svc_` key; for one user's data send
`X-User-Token` with either key. Details: [what changed](authorization.md#what-changed-in-040-only-a-service-key-bypasses-pls-and-rls-040).

### Creating Server API Keys

```bash
curl -X POST http://localhost:5433/api/auth/admin/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "myapp-backend",
    "roles": [
      { "role": "db_writer", "scope": "myapp" },
      { "role": "db_reader", "scope": "analytics" }
    ]
  }'
# Returns: { "key": "mk_abc123...", "kind": "custom", "roles": [ … ], … }
# POST /api/auth/admin/keys instead creates a global db_admin key (mk_srv_…) and takes only name / expiresAt.
```

### Creating Custom App API Keys

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "name": "analytics-pipeline", "roles": [{ "role": "db_reader" }] }'
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
3. Replaces the request's identity with the user's: PLS, RLS and RBAC all use the user — the user's partition grants, claims
   (tenant_id, user_id) and roles. The service key's own roles and its PLS / RLS bypass do not apply to the request.

### Rules

- `X-User-Token` is only accepted when the primary credential is a **service-level key** (`mk_svc_` or `mk_srv_`).
- If the primary credential is an `anon` key or a user JWT, `X-User-Token` is ignored.
- If `X-User-Token` is present but invalid (expired, revoked), the request returns 401 with a clear error about the user token.
- If `X-User-Token` is absent, an app service key (`mk_svc_`) grants full access with PLS / RLS bypassed. A server API key
  (`mk_srv_`) gets its role's grants with PLS / RLS enforced (**0.4.0**; up to 0.3.x it bypassed them too).
- The user token applies to **every transport** (**BL-1223, next train**): `X-User-Token` on HTTP, `user_token` on the WebSocket
  `auth` and `re_auth` messages, `userToken` on the long-poll connect. The rules are the same on each: honoured only beside a
  service-level key, ignored beside any other credential, and an invalid, expired or revoked one fails with `AUTH_TOKEN_INVALID`
  (on a socket, `auth_error` and the socket closes). A realtime session opened with a service key and a user token **is** that
  user's session: its snapshot, its change events and its write streams see what the user may see, and it follows the user's
  grant changes while it is open. `Aouda.Client` (`UserToken`) and `@aouda/client` (`userToken`) send it wherever they send the
  header; an older client, or an older server, leaves a realtime session with the service key's visibility.
- A realtime session with a user token **ends when the user token expires** (`AUTH_TOKEN_EXPIRED`) or is revoked
  (`AUTH_TOKEN_REVOKED`), as a user's own session does. Reconnect with a fresh user token, or send `re_auth` with the service key
  and the fresh user token. A session cannot add, drop or switch its user token on `re_auth` (`AUTH_TOKEN_INVALID`).
- A realtime session opened with a service key and **no** user token sees every partition its filter or named query names, with
  PLS / RLS bypassed — in its snapshot and in its change events (**BL-1219, next train**).

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
