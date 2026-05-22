---
title: "Client Integration"
nav_order: 3
parent: "Auth and Authorization"
---

# Auth Client Integration

> Part of the [Application Auth Guide](Getting-Started-Auth.md). Start there for an overview.

---

## 10. Integrating with the .NET Client

The .NET client supports the two-layer model: API key for connection (Layer 1), then optional user sign-in (Layer 2).

### AppAuthOptions vs ServerAuthOptions

The .NET client uses two separate options types — one per auth system:

| Property | `AppAuthOptions` | `ServerAuthOptions` |
|----------|:-:|:-:|
| `ApiKey` | Yes (`mk_anon_`, `mk_svc_`, custom) | Yes (`mk_srv_`) |
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

Aouda has **three distinct types** of API keys. Understanding when to use each is critical.

### The Three API Key Types

| Key Type | Prefix | Created By | Scope | Stored In | Use Case |
|----------|--------|-----------|-------|-----------|----------|
| **Server API key** | `mk_srv_` | Server admin (`/api/auth/admin/api-keys`) | One or more databases | `_serverauth` | Backend services, CI/CD, cross-database access |
| **App `anon` key** | `mk_anon_` | Auto-generated on `auth.enabled` | One database | `_auth` | Frontend clients, pre-auth access |
| **App `service_role` key** | `mk_svc_` | Auto-generated on `auth.enabled` | One database | `_auth` | Per-database backend access, admin tools |

Additionally, **custom app API keys** (`mk_` prefix) can be created via the admin API for granular access control.

### When to Use Which Key

| Need | Best Key | Why |
|------|----------|-----|
| Frontend app accessing one database | App `anon` key (`mk_anon_`) | Safe to expose, limited access, PLS enforced |
| Backend accessing one database (app auth enabled) | App `service_role` key (`mk_svc_`) | Full access to that database, PLS bypassed |
| Backend accessing multiple databases | Server API key (`mk_srv_`) | Can have roles across multiple databases |
| CI/CD pipeline | Server API key (`mk_srv_`) | Scoped to test databases |
| Admin tooling | Server admin JWT or server API key | Full control |

### Comparison: Server Keys vs App Keys

| | Server API Keys (`mk_srv_`) | App API Keys (`mk_anon_`, `mk_svc_`) |
|---|---|---|
| **Created by** | Server admin | Auto-generated when app auth is enabled |
| **Stored in** | `_serverauth` database | `_auth` database (linked to the app) |
| **Scope** | One or more databases (via `databaseRoles`) | One specific database |
| **PLS** | Never enforced (server-level access) | `mk_anon_`: enforced; `mk_svc_`: bypassed |
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
