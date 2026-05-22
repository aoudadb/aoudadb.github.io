---
title: "Setup and Flows"
nav_order: 2
parent: "Auth and Authorization"
---

# Auth Setup & User Flows

> Part of the [Application Auth Guide](Getting-Started-Auth.md). Start there for an overview.

---

## 7. Enabling Auth on a Database

Application Auth is enabled **per database**. Aouda supports two approaches depending on your architecture.

### Creating a Standalone Auth Database

Use `kind: "auth"` to create a dedicated auth database. Auth endpoints are then served directly at `/api/databases/{auth-db}/auth/...` — no separate application database is required.

```bash
curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <server-admin-token>" \
  -d '{ "name": "auth", "kind": "auth" }'
```

Response:

```json
{
  "name": "auth",
  "auth": {
    "enabled": true,
    "database": "auth",
    "keys": {
      "anonKey": "mk_anon_a1b2c3d4e5f6...",
      "serviceRoleKey": "mk_svc_x7y8z9e0f1a2..."
    }
  }
}
```

The response includes `anonKey` and `serviceRoleKey` immediately. No second database is created. Auth endpoints are available at `/api/databases/auth/auth/...`.

**Save the API keys immediately.** They are shown only once. Use the regeneration endpoint if they are lost.

For .NET applications using Aouda as an OIDC provider:

```json
// appsettings.json
"AoudaAuth": {
  "Authority":    "http://localhost:5433/api/databases/auth",
  "Audience":     "auth",
  "DatabaseName": "auth",
  "ServiceKey":   "mk_svc_..."
}
```

### Linking a Data Database to an Auth Database

Once an auth database exists, create data databases and link them to it:

```bash
# Shorthand — links to the one existing auth database
curl -X POST http://localhost:5433/api/databases \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <server-admin-token>" \
  -d '{
    "name": "myapp",
    "auth": { "enabled": true }
  }'
```

Response:

```json
{
  "name": "myapp",
  "auth": {
    "enabled": true,
    "database": "auth",
    "keys": {
      "anonKey": "mk_anon_...",
      "serviceRoleKey": "mk_svc_..."
    }
  }
}
```

Auth endpoints for `myapp` are now available at `/api/databases/myapp/auth/...`.

**Save the API keys immediately.** They are shown only once. If you lose them, use the regeneration endpoint.

### How Auth Database Resolution Works

| Auth DBs on Server | What `"auth": { "enabled": true }` Does |
|---------------------|------------------------------------------|
| **0 auth DBs** | **Returns 400** — create one first: `kind: "auth"` |
| **1 auth DB** | Links to that existing auth DB |
| **2+ auth DBs** | **Fails** — you must specify which one: `"auth": { "database": "name" }` |

For multiple auth databases (separate user pools for different products):

```bash
curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "product-a", "auth": { "database": "product_a_auth" } }'

curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "product-b", "auth": { "database": "product_b_auth" } }'
```

### Key Regeneration

If you lose the API keys:

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/regenerate-keys \
  -H "Authorization: Bearer <admin-token>"
```

This revokes the old auto-generated keys and creates new ones.

---

## 8. End User Flows: Signup, Signin, Signout

All Application Auth endpoints are scoped by database:

```
/api/databases/{db}/auth/{action}
```

**All auth endpoints require at least the `anon` API key** in the `Authorization` header. This is the Layer 1 gate.

### Sign Up (Create Account)

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/signup \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_anon_a1b2c3d4e5f6..." \
  -d '{
    "email": "alice@example.com",
    "password": "SecurePass123!"
  }'
```

Response:

```json
{
  "user": {
    "id": "usr_abc123",
    "email": "alice@example.com",
    "createdAt": "2026-03-18T12:00:00Z"
  },
  "accessToken": "eyJhbGciOiJSUzI1NiIs...",
  "refreshToken": "dGhpcyBpcyBhIHJlZnJl...",
  "expiresIn": 900
}
```

The user is signed in immediately after signup.

### Sign In (Login)

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/signin \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_anon_a1b2c3d4e5f6..." \
  -d '{
    "email": "alice@example.com",
    "password": "SecurePass123!"
  }'
```

After sign-in, use the `accessToken` (user JWT) as the `Authorization: Bearer` header for all data requests.

### Sign Out (Logout)

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/signout \
  -H "Authorization: Bearer <user-access-token>"
```

Revokes the session and invalidates the refresh token.

---

## 9. Token Lifecycle: Access Tokens and Refresh Tokens

### How Tokens Work

| Token | Lifetime | Purpose |
|-------|----------|---------|
| **Access Token** (JWT) | 15 minutes (default) | Included in `Authorization: Bearer` on every API request |
| **Refresh Token** | 30 days (default) | Used to get a new access token when the old one expires |

### Typical Flow

```
1. User signs in        → receives accessToken + refreshToken
2. App stores tokens    → in-memory, secure storage, or cookie
3. App sends accessToken → on every API call (Authorization: Bearer)
4. Token expires (15 min) → App calls /refresh with refreshToken
5. Aouda returns         → new accessToken + new refreshToken (rotation)
6. User signs out       → App calls /signout, discards tokens
```

### Refreshing the Access Token

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/refresh \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_anon_a1b2c3d4e5f6..." \
  -d '{ "refreshToken": "dGhpcyBpcyBhIHJlZnJl..." }'
```

Each refresh rotates the refresh token. The old one is immediately invalidated. If a revoked refresh token is reused, the entire token family is invalidated (theft detection).

### Session Validation Modes

| Mode | How It Works | Revocation | Best For |
|------|-------------|------------|----------|
| **SignatureOnly** | JWT signature check only | Wait for expiry | High-throughput APIs |
| **Hybrid** (default) | Signature + in-memory revocation check | Near-instant | Most applications |
| **Stateful** | Every request checked against session store | Instant | Security-critical apps |

All three modes are sub-millisecond because Aouda's in-memory architecture eliminates the need for Redis.
