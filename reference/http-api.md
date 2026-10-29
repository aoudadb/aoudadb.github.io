---
title: "HTTP API"
nav_order: 1
parent: "Reference"
---

# Aouda Wire Protocol v2

> **Canonical location.** This file is the public wire / HTTP API reference (formerly multi-repo `WIRE-PROTOCOL.md`). Prefer the client SDKs (`Aouda.Client`, `@aouda/client`) for application code; use this document for endpoint shapes and protocol details. Do not recreate `WIRE-PROTOCOL.md` copies in other Aouda repos.

This document specifies the JSON-based wire protocol for Aouda client-server communication.

## Overview

- **Transport**: HTTP/1.1 and HTTP/2
- **Format**: JSON for all messages
- **Rows on the wire**: column arrays — `columns` and `data`, one array per column — in every JSON result and every JSON write body (**Lead S12, 0.6.0**: the row-object forms, `format=rows` and `"rows": [{…}]` bodies, are gone); binary [column-batch frames](#the-column-batch-frame-acb2) on request
- **Content Type**: `application/json`

## Protocol Version

### Request Header
```
X-Aouda-Protocol-Version: 2
```

### Response Header
All responses include:
```
X-Aouda-Protocol-Version: 2
```

The server echoes the version it used. If the client sends an unsupported version, the server returns `400 Bad Request` with error code `UNSUPPORTED_VERSION`.

### Version Negotiation

| Client Sends | Server Behavior |
|--------------|-----------------|
| No header | Uses latest version (v2), echoes v2 |
| `1` | Uses v1, echoes v2 (v2 server); request bodies must still include `database` for database-scoped endpoints |
| `2` | Uses v2, echoes v2 |
| `99` (unsupported) | Returns 400 with `UNSUPPORTED_VERSION` |
| `abc` (invalid) | Returns 400 with `UNSUPPORTED_VERSION` |

### Database context (v2)

**Protocol v2** requires a **`database`** field in all request bodies that target a database (query, insert, update, delete, create table, and table/schema operations). The field must be a non-empty string and must match the database name in the URL path (e.g. `POST /api/databases/{db}/query` → body must include `"database": "{db}"`). Matching is **case-sensitive** (ordinal string comparison). Missing or empty `database` returns `400 Bad Request` with code `MISSING_DATABASE`. If `database` does not match the path, the server returns `400` with `INVALID_REQUEST` and may include `details` with `pathDatabase` and `bodyDatabase` for debugging.

## Standard Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes (for POST/PUT) | Must be `application/json` |
| `X-Aouda-Protocol-Version` | No | Protocol version (default: latest) |
| `X-Request-Id` | No | Correlation ID (echoed in response) |
| `X-Read-Preference` | No | Read preference for query routing |
| `X-Aouda-Token` | No | Consistency token (`AtLeast`). 42-character lowercase hex. Query `at_least` **wins** when both are sent. Empty value is `TOKEN_MALFORMED`. **Not** the fencing header `X-Aouda-Current-Token`. |
| `X-Aouda-Wait-Ms` | No | Freshness wait budget in milliseconds (query `waitMs` wins). Default 250 when a token or lag budget is in play. Cap 30 000. |
| `X-Aouda-On-Exceeded` | No | `wait` \| `fetchPrimary` \| `fail` (query `onExceeded` wins). Default is **role-aware** (BL-525): `wait` on `Primary`/`Standalone`, `fetchPrimary` on a secondary. An explicit value is never rewritten. |
| `Authorization` | **Required when the target database has auth enabled, except public app-auth POSTs** | `Bearer <token>` — JWT access token or API key (`mk_anon_...`, `mk_pub_...`, `mk_svc_...`, `mk_srv_...`, custom `mk_...`). `POST /api/databases/{db}/auth/{signup\|signin\|refresh\|request-password-reset\|reset-password}` are keyless (a present bearer is ignored). |
| `X-User-Token` | Conditional | Optional user JWT. Used only when `Authorization` is a service-level key (`mk_svc_...` or `mk_srv_...`) to enforce PLS/RBAC in user context. Ignored for `anon` keys and direct user JWT requests. The realtime transports take the same token as `user_token` on the WebSocket `auth` / `re_auth` message and `userToken` on the long-poll connect, with the same rules (**BL-1223, next train**). |

## Standard Response Headers

All API responses include:

| Header | Description |
|--------|-------------|
| `X-Aouda-Protocol-Version` | Protocol version used |
| `X-Served-By` | Address of the server that handled the request |
| `X-Server-Role` | Current role (Primary, Secondary, Hidden, Standalone) |
| `X-Request-Id` | Echoed from request if provided |
| `X-Auth-Database` | **On 401 auth errors only (optional).** Legacy/discovery hint. Clients should use the same auth context as the request: server auth → `POST /api/auth/signin`; app auth → `POST /api/databases/{db}/auth/signin`. Omitted when not applicable. |
| `X-Aouda-Token` | Observed consistency token (42-hex). Set on mutation and read success **and** on `TOKEN_*` errors. Same value as JSON `token`. Distinct from `X-Aouda-Current-Token` (integer fencing token on writes in a replica set). |

### Authentication and Authorization

Aouda has **two independent auth systems** that use the same HTTP headers but serve different purposes. Understanding which system applies depends on the endpoint and the credential type.

#### Credential Types

All credentials are sent as `Authorization: Bearer <credential>`. The server identifies the type by prefix:

| Prefix | Type | System | Description |
|--------|------|--------|-------------|
| `mk_anon_` | App anon key | Application Auth | Leftover public key. **Not required** for signup/signin/refresh/password-reset. Denied on data and admin routes. RBAC `anonymous` role has no data permissions. |
| `mk_pub_` | Browser-tier data key | Application Auth | Public/frontend key for the **data-plane listener**. Named query, named mutation, and subscribe only. Cannot compose an ad-hoc `QueryMessage`. Accepted **only** on the data-plane listener (`AUTH_KEY_LISTENER_MISMATCH` on admin). Role `public` has `read,write,delete` on `*`; the listener 404 and `dataPlaneAccess` are the real gates. |
| `mk_svc_` | App service key | Application Auth | Backend key for one database. PLS/RLS **audited bypass**, full access — the only credential with that bypass. Ad-hoc query is allowed on the **admin** listener. Does **not** list or create databases (`GET`/`POST /api/databases` → **403** `AUTH_KEY_ROUTE_MISMATCH`); use `GET /api/databases/{name}` to check existence. |
| `mk_srv_` | Server API key | Server Auth | Cross-database service key. Scoped roles per database. **PLS / RLS enforced** (**0.4.0**; up to 0.3.x bypassed): no user's grants, so a protected table shows it what a request with no user may see; `X-User-Token` applies a user's. |
| `mk_adm_` | Auth-admin key | Application Auth | User, grant, session, audit, and MFA administration on **one application auth database** (**BL-1032, 0.5.0**). Not `service_role`: PLS / RLS stay enforced, and it is not a data key. `X-User-Token` is ignored. |
| `mk_` (other) | Custom key | Either | Granular custom key. On application auth, linked to a user (`userId`), it gets that user's grants. A custom `mk_` minted on server auth is a scoped server key (BL-1017). PLS / RLS enforced. |
| `eyJ...` (JWT) | Access token | Either | JWT from signin. Claims determine which auth system issued it. Application end-user JWTs on the data-plane listener are browser-tier (named artifacts only). Operator JWTs via Studio use the admin listener (ad-hoc allowed). |

The server dispatches to the correct auth handler based on prefix — no configuration needed from the client.

**Named service keys and overlapping rotation (**BL-1032, 0.5.0**).** A server key (`mk_srv_`) mints extra service keys for a database that has a linked auth database:

| Method | Path | Body | Result |
|--------|------|------|--------|
| POST | `/api/databases/{db}/service-keys` | `{ "name", "expiresAt"? }` | `201` and the secret once: `{ name, key, keyPrefix, expiresAt, createdAt }` |
| GET | `/api/databases/{db}/service-keys` | | Live named keys: `{ keys: [{ name, keyPrefix, expiresAt, createdAt }] }`. No secret, and not the bootstrap system key |
| DELETE | `/api/databases/{db}/service-keys/{name}` | | `204`. Revokes every live row of that name, including one still inside an overlap |
| POST | `/api/databases/{db}/service-keys/{name}/rotate` | `{ "overlapSeconds" }` | `201` with the new secret and `validUntil` |

`name` is 1–64 characters, `[A-Za-z0-9][A-Za-z0-9._-]*`. A second live key of the same name is `409`. `overlapSeconds` omitted or `0` revokes the old secret before the response returns. A positive value (max 86400) sets the old row's `expires_at` and leaves it unrevoked until then, never later than an expiry it already had. A second rotate while two rows of that name are live is `409`. A `db_admin` user and a `service_role` key are `403`. A database with no linked auth database is `400`; use a scoped server key (`POST /api/auth/admin/api-keys`, BL-1017).

The same four routes under `/api/databases/{authDb}/auth-admin-keys` mint `mk_adm_` for an **application** auth database (not a data database, not server auth). That credential is accepted on that database's user, grant, session, audit, and MFA admin routes, and refused on role definitions, API-key minting, `regenerate-keys`, signup settings, RLS resolvers, and every data route.

`POST /api/databases/{db}/auth/admin/regenerate-keys` takes `{ "overlapSeconds"? }` the same way and returns `validUntil` (`null` when the previous system keys were revoked at once). Named keys are not swept.

`Aouda.Client` and `@aouda/client` refuse a prefix in the wrong setting: `AppAuth` / `appAuth` rejects `mk_srv_` and `mk_adm_`; `ServerAuth` / `serverAuth` rejects `mk_svc_`, `mk_anon_`, `mk_pub_`, and `mk_adm_`; `AuthAdmin` / `authAdmin` accepts only `mk_adm_`. A custom `mk_` stays legal on the app and server settings.

#### Listeners and profiles

A single Aouda process can expose **two Kestrel listeners**. The profile is a property of the **connection**, not of a request header (headers are forgeable).

| Listener | Bind | Who | Surface |
|----------|------|-----|---------|
| **Admin** (default) | `Aouda:Bind` / `Aouda:Port` (today’s single listen) | Studio operators, Hub, trusted services | Full API: ad-hoc query, schema apply, `admin/*`, `_studio/*`, named artifacts |
| **Data plane** (optional) | `Aouda:Listeners:DataPlane:Bind` (`host:port`) | Application end users, `mk_pub_*` | `{auth, named query, named mutation, subscribe}` only. Everything else is **404**, not 403 — the existence of an admin surface is itself information. |

Data-plane allowlist (deny-by-default):

- `GET /health`, `/ready`, `/startup` (not `/health/detailed`)
- App auth under `/api/databases/{db}/auth/*` **except** `/auth/admin/*`
- OIDC / JWKS discovery
- `POST /api/databases/{db}/named-queries/{name}/query`
- `POST /api/databases/{db}/named-queries/batch`
- `POST /api/databases/{db}/named-mutations/{name}/execute`
- WebSocket upgrade `/api/databases/{db}/ws`

Explicit 404s on the data-plane include `admin/*`, `_studio/*`, `POST /api/server/shutdown`, `POST …/schema/apply`, `POST …/query`, tables/MQ/graph/vector/jobs/branches/policy, write-stream, and `GET /api/databases`.

If `Aouda:Listeners:DataPlane:Bind` is unset, behaviour equals today: one admin listener, current CORS, no `mk_pub_*` acceptance.

**Credential × listener × surface** (❌ = rejected at the listener or at bind time, never reaching the engine):

| Credential | Listener | Ad-hoc `QueryMessage` | Named query / mutation | ADRA | Admin routes |
|---|---|---|---|---|---|
| `mk_pub_*` | Data plane only | ❌ | ✅ only path | ✅ enforced | ❌ 404 |
| User JWT (application end user) | Data plane | ❌ | ✅ only path | ✅ enforced | ❌ 404 |
| User JWT (Studio operator) | Admin | ✅ | ✅ | ✅ enforced | ✅ per RBAC |
| `mk_svc_*` | Either (key accepted); ad-hoc only on admin | ✅ on admin; 404 on data-plane `/query` | ✅ | Audited bypass | Per RBAC on admin for that database's routes. **Not** `GET`/`POST /api/databases` (server-auth catalog — **403** `AUTH_KEY_ROUTE_MISMATCH`) |
| `mk_anon_*` | Data plane (auth endpoints) | ❌ | ❌ | n/a | ❌ — auth endpoints only |

**Table opt-in.** Catalog field `dataPlaneAccess` defaults to **false**. On the data-plane listener, for `mk_pub_*` and user JWT (not service keys): every table touched by a named query, batch element, or named mutation must have `dataPlaneAccess: true`. Otherwise **404 `TABLE_NOT_FOUND`** (the table is invisible). Admin listener ignores the flag.

**Per-identity quotas** apply on the data-plane only (sliding window; default 60 permits / 60 s). Exceed → HTTP **429**, `Retry-After` (readable cross-origin since the **architecture review, 0.3.0**), code `IDENTITY_QUOTA_EXCEEDED`. One permit per named-query execute, per batch envelope, per named-mutation execute, and per WebSocket subscribe attempt.

**`Date`** is on every response and readable cross-origin (**NativeClients, 0.4.0**): a browser client can compare a
server-stamped time with the server's clock rather than its own.

See [Direct client access](../guides/direct-client-access.md) for configuration, CORS, and Studio/Hub URL rules.

#### Auth Enforcement Rules

| Target Endpoint | Auth Required? | Accepted Credentials |
|-----------------|:--------------:|----------------------|
| `/api/auth/setup` | No (setup mode only, localhost) | None |
| `/api/auth/signin`, `/api/auth/refresh` | No | None (these produce credentials) |
| `/api/auth/signout`, `/api/auth/me`, etc. | Yes | Server JWT |
| `/api/auth/admin/*` | Yes (`db_admin`) | Server JWT or `mk_srv_` with admin role |
| `/api/databases/{db}/auth/signup\|signin\|refresh\|request-password-reset\|reset-password` | No | None (public POST; bearer ignored) |
| `/api/databases/{db}/auth/me\|signout\|password` | Yes (Layer 1 + 2) | API key + user JWT in `X-User-Token`, or user JWT directly |
| `/api/databases/{db}/query\|tables\|rows\|...` | **Only if db has linked auth** | Any valid credential (see below) |
| `/api/databases/{db}/...` (no linked auth db), **server auth database exists**, admin listener | Yes (Layer 1 + 2) | Server JWT, `mk_srv_`, or a server key with a role on `{db}` — every route, `DELETE /api/databases/{db}`, WebSocket and long-poll included (**BL-1017, 0.4.0**) |
| `/api/databases/{db}/...` (no linked auth db), no server auth database, or the data-plane listener | No | None — open access |

#### How Data Endpoint Auth Works

When a request hits a database-scoped data endpoint (e.g. `/api/databases/{db}/query`):

```
1. Does the target database have a linked auth database (or is it one)?
   NO  → Does a server auth database exist, and is this the admin listener?
         NO  → Request proceeds without auth (open access)
         YES → The server auth database governs it (BL-1017, 0.4.0): steps 2–3 with
               server credentials only (server JWT, mk_srv_, a server key), authorized by
               the server auth database's grants; a database that does not exist answers
               401 too
   YES → Continue to step 2

2. Read Authorization header
   Missing → 401 AUTH_TOKEN_MISSING
     Exception (data-plane listener only): listed named-query execute / batch /
     named-mutation execute → 404 NAMED_QUERY_NOT_FOUND / NAMED_MUTATION_NOT_FOUND
     (same ProtocolError as an unknown name; not AuthErrorPayload). Admin listener
     keeps 401. Invalid/expired/revoked credentials stay 401 on both listeners.
   Present → Continue to step 3

3. Identify credential type by prefix
   mk_anon_ → Resolve as app anon key → anonymous role; **auth endpoints only**
   mk_pub_  → Resolve as browser-tier public key → data-plane listener only; named artifacts
   mk_svc_  → Resolve as app service key → full access, PLS bypassed (audited)
   mk_srv_  → Resolve as server API key → check db_roles claim for this database;
              PLS/RLS enforced, no bypass (0.4.0)
   mk_*     → Resolve as custom app key → check permissions
   eyJ*     → Validate JWT signature and claims → extract roles

4. Check X-User-Token header (optional; realtime: auth/re_auth user_token, long-poll userToken — BL-1223, next train)
   Present + credential is mk_svc_ or mk_srv_ → Apply user context (PLS/RBAC)
     Invalid, expired or revoked → 401 AUTH_TOKEN_INVALID (realtime: auth_error, socket closed)
   Present + credential is mk_anon_ or user JWT → Ignored
   Absent → Use credential's own identity

5. Check RBAC permissions
   Role has required operation (read/write/delete/admin) → Proceed
   Role lacks permission → 403 INSUFFICIENT_PERMISSIONS
   No role for this database → 403 AUTHORIZATION_DENIED
     Exception (data-plane listener only): listed named-artifact execute / batch
     maps unentitled (including mk_anon_*) to 404 NAMED_QUERY_NOT_FOUND /
     NAMED_MUTATION_NOT_FOUND so names are not enumerable via 403 vs 404.
     Admin listener keeps 403. Hidden tables stay 404 TABLE_NOT_FOUND.
```

#### X-User-Token Header

The `X-User-Token` header enables backends to act on behalf of a specific user while authenticating with a service-level key.

**When it applies:**
- `Authorization` contains a service-level key (`mk_svc_` or `mk_srv_`)
- `X-User-Token` contains a valid user JWT (from app auth signin)

**What it does:**
- The request authenticates as the service key (Layer 1 — connection identity)
- But data access uses the **user's** identity (Layer 2 — PLS partition scoping, RBAC role)
- This is how backends enforce per-user data isolation without exposing the service key to the frontend

**When it is ignored:**
- When `Authorization` is an `mk_anon_` key (anon keys already enforce PLS from the JWT)
- When `Authorization` is a direct user JWT (the user is already identified)

**Realtime** (**BL-1223, next train**): the same user token, with the same rules, is `user_token` on the WebSocket
`auth` and `re_auth` messages and `userToken` on the long-poll connect body. The session is then the
user's for its whole life — snapshot, change events, write streams, grant changes — and it ends when the user token expires or is
revoked. Before BL-1223 a realtime session ignored the user token and kept the service key's visibility.

**Example:**

```http
POST /api/databases/myapp/query HTTP/1.1
Authorization: Bearer mk_svc_abc123...
X-User-Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyIsInRlbmFudF9pZCI6InRlbmFudF9hYmMifQ...
Content-Type: application/json

{
  "database": "myapp",
  "table": "orders",
  "limit": 50
}
```

Result: The query authenticates via the service key but only returns rows where `tenant_id = "tenant_abc"` (from the user's JWT `tenant_id` claim), because PLS is enforced from the user token.

#### Server Auth Endpoints

Server auth endpoints live under `/api/auth/...` and manage server-level identities (admins, developers, service accounts). They resolve to the internal `_serverauth` database.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/setup` | POST | No (setup mode, localhost only) | Bootstrap first admin |
| `/api/auth/signin` | POST | No | Sign in → JWT + refresh token |
| `/api/auth/refresh` | POST | No | Exchange refresh token → new JWT |
| `/api/auth/signout` | POST | Bearer JWT | End this session; optional `{ "scope": "local" \| "others" \| "global" }` (**NativeClients, 0.4.0**) |
| `/api/auth/sessions` | GET | Bearer JWT | The caller's sessions, one per device (**NativeClients, 0.4.0**) |
| `/api/auth/sessions/{id}` | DELETE | Bearer JWT | End one of the caller's sessions; another user's: `404 AUTH_SESSION_NOT_FOUND` (**NativeClients, 0.4.0**) |
| `/api/auth/me` | GET | Bearer JWT | Current user profile |
| `/api/auth/me` | PATCH | Bearer JWT | Update profile metadata |
| `/api/auth/password` | PUT | Bearer JWT | Change password |
| `/api/auth/admin/users` | GET | Bearer JWT (`db_admin`) | List server users |
| `/api/auth/admin/users/{id}` | GET/PATCH/DELETE | Bearer JWT (`db_admin`) | Get/update/delete user (DELETE 204; 404 if missing; cascades related rows by id) |
| `/api/auth/admin/users/{id}/disable` | POST | Bearer JWT (`db_admin`) | Disable user |
| `/api/auth/admin/users/{id}/enable` | POST | Bearer JWT (`db_admin`) | Enable user |
| `/api/auth/admin/roles` | GET/POST | Bearer JWT (`db_admin`) | List/create roles |
| `/api/auth/admin/roles/{id}` | PATCH/DELETE | Bearer JWT (`db_admin`) | Update/delete role |
| `/api/auth/admin/users/{id}/roles` | GET/PUT | Bearer JWT (`db_admin`) | View/assign user roles |
| `/api/auth/admin/api-keys` | GET/POST | Bearer JWT (`db_admin`) | List/create server API keys |
| `/api/auth/admin/api-keys/{id}` | DELETE | Bearer JWT (`db_admin`) | Revoke server API key |

**Signin request:**

```json
{
  "email": "admin@example.com",
  "password": "..."
}
```

**Signin response:**

```json
{
  "user": { "id": "...", "email": "admin@example.com" },
  "accessToken": "eyJhbG...",
  "refreshToken": "dGhpcyBp...",
  "expiresIn": 900
}
```

**Server JWT claims:**

| Claim | Description |
|-------|-------------|
| `sub` | User ID |
| `email` | User email |
| `iss` | `"aouda"` (`TokenOptions.Issuer`) — the server auth database's issuer. Accepted where the server auth database authenticates: the server-scoped paths (`/admin`, `/api/admin`, `/api/server`, the `/api/databases` collection) and as the server credential on a database's paths |
| `aud` | Server auth database name (e.g. `"_serverauth"`) |
| `db_roles` | Native JSON object — role map keyed by scope, e.g. `{ "myapp": ["db_writer"], "analytics": ["db_reader"] }`. Read directly as an object; no `JSON.parse()` needed. |
| `is_admin` | `true` for server admins (implicit `db_admin` on all databases) |
| `iat`, `exp` | Issued-at and expiry timestamps |

#### Application Auth Endpoints

App auth endpoints live under `/api/databases/{db}/auth/...` and manage end-user identities for a specific database. They resolve to the database's linked auth database (typically `_auth`).

**All app auth endpoints require an API key in `Authorization`** (Layer 1). User endpoints additionally require a user JWT.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/databases/{db}/auth/signup` | POST | API key (Layer 1) | Register new user |
| `/api/databases/{db}/auth/signin` | POST | API key (Layer 1) | Sign in → JWT + refresh token |
| `/api/databases/{db}/auth/refresh` | POST | API key (Layer 1) | Exchange refresh token → new JWT |
| `/api/databases/{db}/auth/signout` | POST | API key + user JWT | End this session; optional `{ "scope": "local" \| "others" \| "global" }` (**NativeClients, 0.4.0**) |
| `/api/databases/{db}/auth/authorize` | POST | user JWT | Native sign-in: issue a single-use PKCE code for a registered native client (**NativeClients, 0.4.0**) |
| `/api/databases/{db}/auth/token` | POST | none | Native sign-in: redeem the code (`grantType: "authorization_code"`) for a new session (**NativeClients, 0.4.0**) |
| `/api/databases/{db}/auth/sessions` | GET | user JWT | The caller's sessions, one per device (**NativeClients, 0.4.0**) |
| `/api/databases/{db}/auth/sessions/{id}` | DELETE | user JWT | End one of the caller's sessions; another user's: `404 AUTH_SESSION_NOT_FOUND` (**NativeClients, 0.4.0**) |
| `/api/databases/{db}/auth/me` | GET | API key + user JWT | Current user profile |
| `/api/databases/{db}/auth/me` | PATCH | API key + user JWT | Update profile metadata |
| `/api/databases/{db}/auth/password` | PUT | API key + user JWT | Change own password (current password required) |
| `/api/databases/{db}/auth/request-password-reset` | POST | API key (Layer 1) | Request 6-digit OTP emailed to user; always 200 (anti-enumeration) |
| `/api/databases/{db}/auth/reset-password` | POST | API key (Layer 1) | Submit OTP + new password; returns token pair; also used for invite-pending first-time password set |
| `/api/databases/{db}/auth/mfa/enroll` | POST | User JWT | Enrol TOTP or phone MFA factor. Phone: 409 `AUTH_MFA_FACTOR_ALREADY_ENROLLED` if a phone factor already exists; delete existing factor then re-enroll to replace number. Needs an `aal2` token, else 403 `AUTH_MFA_STEP_UP_REQUIRED` (**BL-795, 0.3.0**) |
| `/api/databases/{db}/auth/mfa/challenge` | POST | User JWT | Create MFA challenge; sends SMS OTP for phone factors |
| `/api/databases/{db}/auth/mfa/verify` | POST | User JWT | Submit OTP/TOTP/backup code; returns `aal2` token pair on success |
| `/api/databases/{db}/auth/mfa/factors` | GET | User JWT | List enrolled MFA factors |
| `/api/databases/{db}/auth/mfa/factors/{id}` | DELETE | User JWT (`aal2`) | Delete an enrolled MFA factor. A token that is not `aal2` gets 403 `AUTH_MFA_STEP_UP_REQUIRED` (**BL-795, 0.3.0**); an operator uses the admin delete |
| `/api/databases/{db}/auth/admin/users` | GET | API key (`db_admin`) | List app users |
| `/api/databases/{db}/auth/admin/users` | POST | API key (`db_admin`) | Create user; supports `sendInviteEmail` + `forcePasswordChange` flags |
| `/api/databases/{db}/auth/admin/users/{id}` | GET/PATCH/DELETE | API key (`db_admin`) | Get/update/delete user (DELETE 204; 404 if missing; cascades related rows by id) |
| `/api/databases/{db}/auth/admin/users/{id}/password` | PUT | API key (`db_admin`) | Admin override of user's password (no current-password check); optional `forcePasswordChange` |
| `/api/databases/{db}/auth/admin/users/{id}/invite` | POST | API key (`db_admin`) | (Re-)send invite email with OTP; invalidates previous unused tokens |
| `/api/databases/{db}/auth/admin/users/{id}/mfa/factors` | GET | API key (`db_admin`) | List that user's MFA factors (active, pending, and any other stored status). Same body as the user list: `{ "factors": [ { "id", "type", "maskedPhone", "status", "createdAt" } ] }`. Phone is masked (`+***-***-` + last 4). Empty list is 200 `factors: []`. Unknown user is 404. |
| `/api/databases/{db}/auth/admin/users/{id}/mfa/factors/{factorId}` | DELETE | API key (`db_admin`) | Delete that user's factor and its challenges. 200 `{ "ok": true }`. 404 if the factor is missing or belongs to someone else. |
| `/api/databases/{db}/auth/admin/users/{id}/mfa/enroll` | POST | API key (`db_admin`) | Admin-enrol a phone MFA factor on behalf of a user. 409 `AUTH_MFA_FACTOR_ALREADY_ENROLLED` if a phone factor is already active or pending; existing factor id in `detail`. Does not overwrite the number — `DELETE …/admin/users/{id}/mfa/factors/{factorId}` first, then enroll again |
| `/api/databases/{db}/auth/admin/api-keys` | GET/POST | API key (`db_admin`) | List/create custom API keys; POST accepts an optional `userId` to link the key to a user's `auth-db-pls` grants — see [Auth Reference](../auth/reference.md) |
| `/api/databases/{db}/auth/admin/api-keys/{id}` | DELETE | API key (`db_admin`) | Revoke custom API key |
| `/api/databases/{db}/auth/admin/signup-settings` | GET/PUT | API key (`db_admin`) | Read/write `allowSelfSignup` and `selfSignupRole` (null → `db_writer`) |

**App auth signin request:**

```http
POST /api/databases/myapp/auth/signin HTTP/1.1
Authorization: Bearer mk_anon_abc123...
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "..."
}
```

**App auth signin response:**

```json
{
  "user": { "id": "...", "email": "user@example.com" },
  "accessToken": "eyJhbG...",
  "refreshToken": "dGhpcyBp...",
  "expiresIn": 900
}
```

**App user JWT claims:**

| Claim | Description |
|-------|-------------|
| `sub` | User ID |
| `email` | User email |
| `iss` | `{base_url}/api/databases/{db}` (`Aouda:BaseUrl`, else the request's scheme and host). (**BL-980, 0.4.0**) The only issuer accepted for this database's tokens (with, for a linked auth database, that database's URL issuer); up to 0.3.x `"aouda"` was accepted beside it, and a token carrying it is now `401` |
| `aud` | Auth database name (e.g. `"_auth"`) |
| `aal` | Authentication assurance level: `"aal1"` (password signin by a user who has an active MFA factor, not yet verified) or `"aal2"` (MFA verified, **or a password signin by a user with no active factor** — **BL-795, 0.3.0**) |
| `tenant_id` | Tenant ID for PLS partition scoping |
| `db_roles` | Native JSON object — role map keyed by scope, e.g. `{ "myapp": ["db_reader"] }`. Values are always arrays. Scope key for unscoped roles is the auth DB name (e.g. `"_auth"`). |
| `permissions` | Fine-grained table permissions (if custom role) |
| `iat`, `exp` | Issued-at and expiry timestamps |

#### Auth Error Responses

Auth errors (from the auth middleware and auth endpoints) use the `AuthErrorPayload` shape, which is **different from the general `ProtocolError` format** used by query/table endpoints:

```json
{
  "error": "AUTH_TOKEN_EXPIRED",
  "message": "Access token has expired.",
  "suggestion": "Refresh the token using the /refresh endpoint or re-authenticate.",
  "detail": "optional additional context",
  "requestId": "req_abc123"
}
```

Fields:

| Field | Type | Description |
|-------|------|-------------|
| `error` | string | Machine-readable error code (e.g. `AUTH_TOKEN_EXPIRED`). Use this for programmatic handling. |
| `message` | string | Human-readable description of the error. |
| `suggestion` | string? | Actionable advice for the caller. |
| `detail` | string? | Optional additional context (e.g. claim name, partition key). |
| `requestId` | string? | Correlation ID echoed from `X-Request-Id` header if provided. |

**Common mistake:** Auth errors do **not** have a separate `"code"` field — the `"error"` field itself is the machine-readable code. This is the opposite of `ProtocolError` (general query errors) where `"error"` is human-readable and `"code"` is the code.

**403 ADRA errors include structured detail strings:**

```json
{
  "error": "AUTH_PLS_GRANT_NOT_FOUND",
  "message": "Access denied for query on table 'orders'. The requested partition is not in the user's grant set.",
  "suggestion": "Request a partition grant for this dimension, or contact an administrator.",
  "detail": "dimension=org_id, partitionKey=org-xyz",
  "requestId": "req_abc123"
}
```

## Read Preferences

Read preferences control which replica serves a read request.

### Header
```
X-Read-Preference: Primary
```

### Query Parameter (takes precedence over header)
```
GET /api/query?readPreference=Secondary
```

### Valid Values

| Value | Description |
|-------|-------------|
| `Primary` | Read from primary only (**default** — unchanged) |
| `PrimaryPreferred` | Prefer primary, fall back to secondary |
| `Secondary` | Read from any secondary (not hidden) |
| `SecondaryPreferred` | Prefer secondary, fall back to primary |
| `Nearest` | Read from lowest-latency member |
| `Hidden` | Explicitly target hidden replica |
| `SecondaryWithMaxLag` | Secondary that also satisfies the lag budget (`maxLagBytes` / `maxLagSeconds` / `maxStalenessMs`). Enforced at **request time** on the receiving node. |

Lag query parameters (AND-ed when both byte and time bounds are set): `maxLagBytes`, `maxLagSeconds` (measured staleness of the last applied commit-class WAL frame — **not** lag-bytes ÷ 1 MB/s), `maxStalenessMs` (bound as `maxLagSeconds = maxStalenessMs / 1000.0`). `MaxLagBytes` is unchanged. See [Freshness](../guides/freshness.md).

### Behavior

- **Standalone mode**: Ignores read preference (serves all requests)
- **Hidden replicas**: Only serve `Hidden` preference, reject all others with `421 Misdirected Request` (`MISDIRECTED_REQUEST`) **before** any freshness wait
- **Invalid values**: Default to `Primary`
- **Lag / token gate**: when a consistency token or lag budget is presented, a behind node waits up to `waitMs` then applies `onExceeded`. Role mismatch stays `MISDIRECTED_REQUEST`. Freshness miss on a replica that *can* serve the role is `TOKEN_UNSATISFIED` / `TOKEN_FETCH_PRIMARY`.

---

## Consistency tokens and freshness

User guide: [Freshness and replica consistency](../guides/freshness.md).

The token is an opaque sortable **42-character lowercase hex** string. Semantics are `AtLeast` (lower bound), never point-in-time `AsOf`.

| Mechanism | Details |
|-----------|---------|
| Present | Request header `X-Aouda-Token` or query `at_least`. **Query wins.** Empty is `TOKEN_MALFORMED`. |
| Return | Response header `X-Aouda-Token` and JSON `token` on mutation/read success and on `TOKEN_*` errors |
| Current | `GET /api/databases/{db}/token` → `{ "database", "token" }` |
| Wait | `waitMs` / `X-Aouda-Wait-Ms` (default 250, cap 30 000) |
| Action | `onExceeded` / `X-Aouda-On-Exceeded`: `wait` → 409 `TOKEN_UNSATISFIED`; `fetchPrimary` → 421 `TOKEN_FETCH_PRIMARY` (server does **not** proxy); `fail` → 409 immediately. **Omitted default is role-aware** (BL-525): `wait` on `Primary`/`Standalone`, `fetchPrimary` on a secondary. Explicit `fetchPrimary` is still 421 on every role. |
| Named-query freshness | Declared on the named query, keyed by the path/batch/subscribe **name**. A name with no `freshness` block is fail-safe (primary-only + `readYourWrites`). Loosening is 400 `FRESHNESS_LOOSENED`. |
| Materialized query | (**WorkloadCore, 0.3.0**) A token-bearing read of a materialized query (`POST .../materialized-queries/{name}/query`, subscribe) is covered only when the query is **current** for that token by the one rule its status reports as `current`: no lost update, nothing queued or in flight for it or for the queries it is built on, no commit to its source still being routed, and its frontier at or past the token. Before, the frontier alone was compared, so a query that had lost an update, or whose bulk load or routed commit was not yet in its result, answered a token its frontier covered. |
| Bulk-load commit | Field is `token`, **not** `walPosition` |
| Streaming | Optional `token` on `snapshot`, `snapshot_complete`, `change`, `heartbeat` alongside `version`. `resume_from` remains the change-event sequence. Subscribe may send `at_least` / `wait_ms` / `on_exceeded`. Heartbeat `version` is **not** a WAL sequence. |

Admin replication `walPosition` on `GET /admin/replication/status` is lag observability, not this token.

MQ list/status and `POST …/materialized-queries/{name}/query` stamp `token` as the **maintenance watermark** (`D-9`), not a raw WAL offset. A token-bearing MQ read waits on that watermark.

`POST …/materialized-queries/{name}/query` reads the whole result, held to `Aouda:Query:MaxResultRows` and the read budget like every
materialising read (**BL-776, 0.3.0**): a result over the read budget is `503 MEMORY_BUDGET_EXCEEDED` with `Retry-After`; a
result over the row ceiling is `400 RESULT_TOO_LARGE` with no `Retry-After` (**release blockers, 0.3.0**; it was a `503`), because
retrying is refused the same way — read it with a filtered `POST …/tables/{result}/query` and a `limit`, or its aggregates.
(**BL-944, 0.4.0**) The same holds when the refusal or the ceiling arrives wrapped in another error: it is a `503` with
`Retry-After` (or `400 RESULT_TOO_LARGE`), where up to 0.3.x it answered `400 INVALID_REQUEST`.

Query parameter **wins** over the header when both are sent:

```http
POST /api/databases/appdb/query?at_least=01aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa HTTP/1.1
X-Aouda-Token: 01bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```

The gate uses the `at_least` value.

---

## Error Response Format

All errors return a JSON body with this structure:

```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": "Optional additional information",
  "requestId": "echoed-request-id"
}
```

### Error Codes

#### Request Validation Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Request body is malformed or missing required fields; or request body `database` does not match URL path |
| `INVALID_FORMAT` | 400 | (**Lead S12, 0.6.0**) The request names the `format` query parameter (`/query`, a named query's execute or batch). It is no longer read: every JSON result is column arrays (`columns`, `data`), and the binary form is asked for with `Accept: application/vnd.aouda.column-batch-v2`. Any value is refused, `columnar` included, so an old client asking for `rows` is told rather than handed a body it misreads. Drop the parameter |
| `ROW_OBJECTS_UNSUPPORTED` | 400 / 415 | (**Lead S12, 0.6.0**) A write body carries row objects (`rows`, or a named mutation's batch argument given as an array of objects), which no surface reads any more: `POST …/rows`, a branch insert, a named mutation's `batchParam`, the schema seed and `aouda.seed.json`, and a WebSocket `stream_rows` (as its `error` code). A bulk-load `:append` sent as NDJSON (`application/x-ndjson`) is refused the same way with `415`. Send [column arrays](#column-arrays-the-write-body) — `columns`, `data` and, for a cell that is not given, `absent` — or upgrade the client library. Nothing was written |
| `MISSING_TABLE` | 400 | Table name is missing from request |
| `MISSING_DATABASE` | 400 | Database name is missing or empty in request (v2: set the `database` field in the request body) |
| `INVALID_OPERATOR` | 400 | Invalid comparison operator in where clause |
| `INVALID_COLUMN` | 400 | Invalid column name or reference |
| `INVALID_VALUE` | 400 | Invalid value type or format |
| `FRAME_VERSION_UNSUPPORTED` | 415 | (**Lead S09, 0.6.0**) A column-batch body of a version this server no longer reads: an `ACB1` frame, or the retired media type `application/vnd.aouda.column-batch`. The message names the version found and the one expected (`ACB2`, `application/vnd.aouda.column-batch-v2`). Upgrade the client; nothing of the request was applied |
| `RESULT_TOO_LARGE` | 400 | (**release blockers, 0.3.0**) The query's result exceeds `Aouda:Query:MaxResultRows` (default 1 000 000): `/query`, a named query, or `POST …/materialized-queries/{name}/query`. The message names the row count, the ceiling and its key. No `Retry-After`: the same query is refused the same way. Narrow the query, page it (`limit` / `offset`), or have the operator raise the setting. It was `503 MEMORY_BUDGET_EXCEEDED` with a `Retry-After` a retry could not honour. (**LoadScan, 0.5.0**) A `/query` with no page that asks for column-batch frames is streamed, not held, and is never refused this way: ask for frames to export a whole table |

#### Resource Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TABLE_NOT_FOUND` | 404 | The specified table does not exist |
| `COLUMN_NOT_FOUND` | 404 | The specified column does not exist |
| `TABLE_EXISTS` | 409 | A table with the specified name already exists |
| `COLUMN_EXISTS` | 409 | A column with the specified name already exists |
| `DECLARATIVE_SCHEMA_DDL_FORBIDDEN` | 400 | HTTP DDL rejected because schema apply created the table. Change it through `POST …/schema/apply`. Applies in every `InferenceMode` (**BL-1177, 0.7.1**). Before, it applied only in `Extend`, and `On` / `Off` accepted the call |
| `DATABASE_NOT_FOUND` | 404 | The specified database does not exist |
| `DATABASE_EXISTS` | 409 | A database with the specified name already exists |
| `BRANCH_EXISTS` | 409 | A branch with the specified name already exists |
| `MERGE_CONFLICT` | 409 | Branch merge has conflicts that must be resolved or forced |
| `NOT_FOUND` | 404 | Generic not-found (used when a more specific code is not available) |
| `PARTITION_FILTER_REQUIRED` | 400 | Query on a partitioned table is missing the required partition key filter |
| `NAMED_QUERY_NOT_FOUND` | 404 | Named-query name is unknown. On the **data-plane listener**, unsigned or unentitled execute / batch / subscribe of a listed named query also uses this code (same `ProtocolError` envelope as unknown). Admin listener keeps 401/403 for those callers. |
| `NAMED_QUERY_BIND_FAILED` | 400 | Argument bind failed (type, constraint, or missing required param) |
| `NAMED_QUERY_PARAM_REQUIRED` | 400 | A required named-query parameter was omitted |
| `NAMED_QUERY_BATCH_EMPTY` | 400 | `queries` is missing or empty |
| `NAMED_QUERY_BATCH_TOO_LARGE` | 400 | Batch exceeds 32 elements (`ProtocolConstants.MaxNamedQueryBatchSize`) |
| `NAMED_QUERY_BATCH_MUTATION` | 400 | Batch included a named-mutation name (read-only envelope) |
| `NAMED_MUTATION_NOT_FOUND` | 404 | Named-mutation name is unknown. On the **data-plane listener**, unsigned or unentitled execute also uses this code. Admin listener keeps 401/403. |
| `NAMED_MUTATION_BIND_FAILED` | 400 | Named-mutation argument bind failed |
| `NAMED_MUTATION_RETURNING_OVERFLOW` | 400 | `RETURNING` would exceed `MaxReturningRows`; the call fails closed (no `rowsTruncated`) |
| `ACCESS_SURFACE_TOO_MANY_IDENTITIES` | 400 | Access-surface diff posted more than 32 fixture identities |
| `AUTH_IDENTITY_INVALID` | 400 | `aouda.identities.json` / posted identities document failed validation |
| `SNAPSHOT_TOO_LARGE` | 400 | Subscribe snapshot would exceed `MaxSnapshotRows` (default 100 000) |
| `SNAPSHOT_OVERFLOW` | 400 | Change-event buffer overflowed while paging the snapshot; subscribe fails (not a mid-snapshot `gap`) |
| `BULK_LOAD_TRANSFORM_INTENT_REQUIRED` | 400 | Bulk load into a table with derived columns, checks, or transforms without `applyTransforms` or `preTransformed` |
| `BULK_LOAD_TRANSFORM_INTENT_CONFLICT` | 400 | Both transform-intent flags set |
| `BULK_LOAD_SERVER_TIME_REQUIRES_TRANSFORMS` | 400 | `preTransformed` load into a table with a server-time column; use `applyTransforms` (**NativeClients, 0.4.0**) |

#### Authentication Errors (4xx)

Auth errors use the `AuthErrorPayload` shape (see [Auth Error Responses](#auth-error-responses) above) where the `"error"` field is the machine-readable code.

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_TOKEN_MISSING` | 401 | Missing or empty `Authorization: Bearer` header. Exception: data-plane listed named-artifact execute / batch is 404 `NAMED_QUERY_NOT_FOUND` / `NAMED_MUTATION_NOT_FOUND` instead (admin listener still 401). |
| `AUTH_TOKEN_INVALID` | 401 | Token malformed or signature invalid (also used for invalid `X-User-Token`). (**BL-944, 0.4.0**) Never for a check the server could not finish for capacity — reading the signing keys refused is `503` + `Retry-After`; keep the token and retry |
| `AUTH_TOKEN_EXPIRED` | 401 | Access token has expired |
| `AUTH_TOKEN_REVOKED` | 401 | Access token has been revoked |
| `AUTH_API_KEY_INVALID` | 401 | API key not recognized, revoked, or expired. Not returned for a live `mk_svc_` / `mk_adm_` on the database catalog — that is `AUTH_KEY_ROUTE_MISMATCH`. |
| `AUTH_API_KEY_REQUIRED` | 401 | Historical: public app-auth POSTs required an API key. Those routes are now keyless and no longer return this code. |
| `UNAUTHORIZED` | 401 | Deny-by-default: unrecognised path on a server where auth is configured |
| `NOT_AUTHENTICATED` | 401 | Authentication required (database has auth enabled but no valid token) |
| `AUTHORIZATION_DENIED` | 403 | Authenticated but no role for the target database |
| `INSUFFICIENT_PERMISSIONS` | 403 | Authenticated but role lacks required operation (e.g. read-only role attempting write) |
| `AUTH_KEY_ROUTE_MISMATCH` | 403 | A live application key (`mk_svc_` / `mk_adm_`) on a server-auth catalog route (`GET`/`POST /api/databases`). The key is recognized; the route is not for that kind (**BL-1128**). |
| `AUTH_INVALID_CREDENTIALS` | 401 | Signin credentials are invalid (wrong password or non-existent email) |
| `AUTH_ACCOUNT_LOCKED` | 423 | Account is temporarily locked due to too many failed attempts. `Retry-After` header is set. |
| `AUTH_ACCOUNT_DISABLED` | 401 | Account is disabled by an administrator |
| `AUTH_RATE_LIMITED` | 429 | Too many auth requests — rate limit exceeded. `Retry-After` header is set. |
| `MEMORY_BUDGET_EXCEEDED` | 503 | (**BL-850, 0.3.0**) Sign-in, sign-up, password set / change / reset and an admin's create-user: the password hash (Argon2id, 64 MiB while it runs) could not get its memory from the server's queue within 10 s. Nothing was changed; `Retry-After` is the queue's estimate. Hashes queue for memory rather than run unbounded, so a burst of sign-ins waits instead of exhausting the heap (it answered `500` before). An admin's user edit, API-key revoke or RLS-resolver create refused for capacity answers this (or `WAL_CAPACITY_EXCEEDED`) too, where it used to read as a 400 or a 409 "email exists" (WorkloadCore group 6 review). A token **refresh** refused for capacity answers this too (**BL-841, 0.3.0**; it was a `500`), and the refresh token stays live: retry with the same token. |
| `AUTH_SIGNUP_FAILED` | 400 | Signup could not be completed (generic message to prevent information leakage) |
| `AUTH_SIGNUP_DISABLED` | 403 | Self-service registration is disabled for this database (`allowSelfSignup` is false) |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | Refresh token is invalid, expired, or revoked. Also the losing call of two concurrent refreshes presenting one token (**BL-841, 0.3.0**): exactly one refresh succeeds, and the other revokes the token family — including the token the winner just received. Refresh a shared session from one place |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | Email is already registered in this auth database |
| `AUTH_PASSWORD_TOO_WEAK` | 400 | Password does not meet the minimum password policy |
| `AUTH_INVALID_EMAIL` | 400 | Email is blank or not a valid email format |
| `AUTH_PLS_TENANT_CLAIM_MISSING` | 403 | PLS: required tenant claim missing from the JWT for this table |
| `AUTH_PLS_TENANT_CLAIM_MISMATCH` | 403 | PLS: explicit partition filter does not match the token's tenant claim |
| `AUTH_PLS_WRITE_SCOPE_VIOLATION` | 403 | PLS: write request targets a partition outside the tenant scope |
| `AUTH_PLS_GRANT_NOT_FOUND` | 403 | PLS (auth-db-pls): requested partition is not in the user's grant set |
| `AUTH_PLS_GRANT_INSUFFICIENT_ACCESS` | 403 | PLS: partition is granted but access level is `read`, which does not allow writes |
| `AUTH_PLS_UNSUPPORTED_OR_SHAPE` | 403 | PLS: `Where.Or` predicate shape is incompatible with safe auth-db-pls partition enforcement |
| `AUTH_KEY_LISTENER_MISMATCH` | 401 | `mk_pub_*` presented on the admin listener (or a key used on a listener that does not accept it) |
| `IDENTITY_QUOTA_EXCEEDED` | 429 | Data-plane per-identity request quota exceeded. `Retry-After` is set. |
| `AUTH_GRANT_DIMENSION_CAP` | 400 | Creating a partition grant would exceed 1 000 grants on one dimension |
| `AUTH_GRANT_PRINCIPAL_CAP` | 400 | Creating a partition grant would exceed 5 000 grants for the principal |
| `AUTH_RESOLVER_INVALID` | 400 | RLS resolver cannot be persisted (e.g. zero rules — fail-closed) |
| `AUTH_CLAIM_INVALID` | 400 | Custom user claim key is blank or invalid |
| `IDENTITY_SOURCE_UNRESOLVABLE` | 400 | Identity derived source could not be resolved from the principal |
| `IDENTITY_STAMP_REQUIRED` | 400 | Service role omitted a required identity-stamped column |
| `SCHEMA_IDENTITY_COLUMN_NOT_BINDABLE` | 400 | `plsClaimBinding` / identity source is not a bindable spelling (`subject` or `claim:<name>`) |
| `SCHEMA_SERVER_TIME_COLUMN_NOT_BINDABLE` | 400 | A named mutation's `values` / `set` / `setExpr` names a server-time column (**NativeClients, 0.4.0**) |
| `TRANSFORM_DERIVED_READONLY` | 400 | Caller supplied a value for a derived column (including an identity or server-time stamp) |

#### State Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `MISDIRECTED_REQUEST` | 421 | Request sent to wrong server based on **role** (read preference). Distinct from `TOKEN_FETCH_PRIMARY`. |
| `WRITE_NOT_ALLOWED` | 403 | Write operations not allowed on this server |
| `NOT_PRIMARY` | 421 | Server is not the primary |
| `TOKEN_MALFORMED` | 400 | Consistency token undecodable, empty, or wrong version. Error body/header carry the node's observed token. |
| `TOKEN_FOREIGN_DATABASE` | 400 | Token issued for a different database. Do not retry the same string. |
| `TOKEN_EPOCH_SUPERSEDED` | 409 | Failover lost the write, or future term. **Never waited.** Do not retry the same token. |
| `TOKEN_UNSATISFIED` | 409 | Token or lag budget still unmet after `waitMs` (or immediately when `onExceeded=fail`). Never a stale answer. |
| `TOKEN_FETCH_PRIMARY` | 421 | Replica cannot satisfy the freshness contract; retry against the current primary (`GET /admin/replication/topology`). Server does not proxy. |
| `MQ_NOT_READY` | 409 | Token-bearing read or subscribe against a materialized query that is not `Ready` (building, rebuilding, or error). Distinct from `TOKEN_*`: retry with backoff; do not discard the token. |
| `FRESHNESS_CONTRACT_INVALID` | 400 | Unknown `onExceeded` (including `serveStaleAndRevalidate`), `waitMs` negative or above 30 000. |
| `FRESHNESS_LOOSENED` | 400 | Call site weaker than the named query’s declared budget, or non-`Primary` on fail-safe (name with no `freshness` block). |

#### Server Errors (5xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `SERVICE_UNAVAILABLE` | 503 | Service is temporarily unavailable. (**BL-944, 0.4.0**) Also the answer to a refusal no other code names: a request the server refused for capacity with no more specific code (`MEMORY_BUDGET_EXCEEDED`, `WAL_CAPACITY_EXCEEDED`, `WRITE_CONFLICT`) is `503 SERVICE_UNAVAILABLE` with `Retry-After: 10`, never a `500` — nothing was applied; retry after `Retry-After` |
| `SERVER_STARTING` | 503 | The server is still starting (replaying each database's log) and is not serving yet. (**BL-944, 0.4.0**) Carries `Retry-After: 5`; poll again after it (`GET /startup` is the probe for this) |
| `SETUP_REQUIRED` | 503 | The server has no admin yet and is in setup mode: only setup status and a local `POST /api/auth/setup` are served. **No `Retry-After`**, deliberately — an operator ends setup mode, not time; create the first admin |
| `SERVER_AUTH_NOT_CONFIGURED` | 503 | Server authentication is not configured (or its database is not open) for a server-admin route. **No `Retry-After`**, deliberately — an operator fixes it (`aouda setup` or `POST /api/auth/setup`) |
| `INTERNAL_ERROR` | 500 | An internal error occurred |
| `WRITE_APPLIED_RESPONSE_FAILED` | 500 | (**Lead group 3 review, 0.6.0**) The server **applied** the write — an insert, update, delete or upsert on a table's `rows`, a `rows/batch`, a named mutation, a branch insert — and then failed while answering it: waiting for the write concern, building the answer, or running out of heap on the way out. No `Retry-After`. **Do not re-send the request as-is**: it would apply the write again. Read the data to see its effect, and quote the `requestId` when reporting it. Such a failure used to be answered as a capacity refusal (`503 MEMORY_BUDGET_EXCEEDED` with `Retry-After`, "not applied"), which both SDKs re-send, so an insert could land twice |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The server could not fit the request in memory now: the memory budget's queue refused it (`Retry-After` is the queue's estimate), or the managed heap hit its hard limit while serving it (`Retry-After: 10`, one sampling tick). The request was not applied; retry after `Retry-After`. (**WorkloadCore S17, 0.3.0**) Never a constant `Retry-After: 1`: every memory refusal carries the governor's estimate for its bytes at the queue's measured service rate, or `10` (the memory broker's next look, `T6`) before any rate is measured or when it has no estimate. (**BL-956, 0.4.0**) The estimate is at most **30 s** (it was 300 s): ask again then, and the next answer carries a fresh estimate. (**WorkloadCore S07, 0.3.0**: a heap exhaustion inside any request, and a query the read path refused, answered `500 INTERNAL_ERROR` before.) A bulk load's `:commit` whose failure came **after** the load's commit point is never this code: see the bulk-load `:commit` errors. (**BL-921, 0.3.0**) **Every endpoint answers a capacity refusal this way** — this code, or `WAL_CAPACITY_EXCEEDED` for the WAL's — never as the client's mistake or a server failure: inserting edges or vectors, reordering a table's columns or seeding a schema while the WAL was full answered `400 INVALID_REQUEST`, and other endpoints' catch-alls `500`. |
| `WAL_CAPACITY_EXCEEDED` | 503 | The WAL is at its refusal line (`T27`): writes to source tables are refused until retention brings it back under `T26`. Nothing was applied; `Retry-After` is the server's estimate from the measured reclaim rate. Retry after it. (**BL-956, 0.4.0**) It is at most **30 s**, and `10` before any reclaim is measured (it was up to 300 s). (**BL-921, 0.3.0**) Answered as this on every endpoint, where some answered `400` or `500` before. |
| `BATCH_PARTIALLY_APPLIED` | 503 | (**Lead group 3 review, 0.6.0**) `POST …/tables/{name}/rows/batch` only: operation `k` (`k` ≥ 1) was refused for capacity. Operations `0` to `k − 1` **were applied**; operation `k` and the ones after it were not. `details` names `appliedOperations=k`, `totalOperations=n` and the refusal's own code. **No `Retry-After`**, deliberately: re-sending the whole batch would apply its first `k` operations twice. Re-send only the remaining operations (`operations[k..]`) as a new batch. A refusal of operation `0` is still the plain `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` with `Retry-After`: nothing was applied. It used to be that plain refusal whatever `k` was, which both SDKs re-send |
| `TIMEOUT` | 504 | Request timed out |
| `OVERLOADED` | 503 | Server is overloaded |

**`Retry-After` is readable from a browser (**architecture review, 0.3.0**).** Every CORS policy exposes it, so a
browser client can honour it on a 429 or 503 as a server-side client does — the back-off the ingest and capacity
design relies on. Before, it was not exposed and a browser read `null`.

#### Named-query, streaming, and data-plane errors

These also appear as WebSocket `error` `code` values where noted.

(**BL-944, 0.4.0**) **A refusal on a WebSocket is its own code.** A `stream_rows` write, a subscription's snapshot and a
subscription's permission read that the server refused for capacity answer `MEMORY_BUDGET_EXCEEDED` or `WAL_CAPACITY_EXCEEDED`
(message ending "retry after N s"), and a write conflict `WRITE_CONFLICT` — wherever the refusal arose. Before, a wrapped refusal
or a heap exhaustion was `INVALID_REQUEST`, a refused snapshot `SNAPSHOT_FAILED` and a refused permission read `PERMISSION_REVOKED`
(the subscription is still denied when its permissions cannot be read; only the code changed).

| Code | HTTP / WS | Description |
|------|-----------|-------------|
| `NAMED_QUERY_DEPRECATED` | 200 warning | Hash is deprecated; execute/subscribe still succeeds. `warnings[]` includes `hash` and optional `sunsetAt`. |
| `NAMED_MUTATION_DEPRECATED` | 200 warning | Same for named mutations |
| `NAMED_MUTATION_UNCAPPED_DELETE` | 400 (schema apply) | Named-mutation delete is missing a numeric `limit` cap |
| `NAMED_MUTATION_RETURNING_STAR` | 400 (schema apply) | Named-mutation `returning` contains `*` |
| `NAMED_MUTATION_VALUE_NODE_INVALID` | 400 (schema apply) | A `values` / `set` entry is an object node that is neither `{ "param": "<name>" }` nor `{ "value": <literal> }` |
| `NAMED_MUTATION_RETURNING_OVERFLOW` | 400 | `RETURNING` would exceed `MaxReturningRows` (execute-time; fail closed) |
| `DUPLICATE_PRIMARY_KEY` | 409 | *BL-636, 0.1.37.* An insert named a primary key a live row already holds. `details` carries the offending key. Use `op: "upsert"` (named mutation) or `mode: "upsert"` (write-stream) when the write is meant to replace. Previously surfaced as `500 INTERNAL_ERROR` |
| `WRITE_CONFLICT` | 409 | (**BL-881, 0.3.0**) A DELETE or UPDATE (table `PATCH` / `DELETE` rows, `rows/batch`, a named mutation) did not commit: it re-checks the rows it matched at its commit and runs again from its scan when another writer changed one, and another writer kept deleting or rewriting them through all 16 of its attempts. Nothing of it was applied (in `rows/batch`, the operations before it were). Retry the request with backoff. Previously surfaced as `500 INTERNAL_ERROR`. The C# SDK raises it as `AoudaRequestException` (`StatusCode` 409, `ErrorCode` `WRITE_CONFLICT`) and does not retry it itself. An admin auth write that keeps conflicting answers it in the auth payload shape |
| `NAMED_QUERY_IDENTIFIER_PARAM` | 400 (schema apply) | A parameter occupies an identifier position (table/column/operator/sort/projection) |
| `NAMED_QUERY_UNCAPPED_LIMIT` | 400 (schema apply) | Named query has no capped `limit` / `limitParam` |
| `NAMED_QUERY_COUNT_UNBOUNDED` | 400 (schema apply) | `count: true` but the definition is not cost-bounded (joins, `distinct`, or uncovered partition keys) |
| `NAMED_QUERY_IDENTITY_PARAM` | 400 (schema apply) | Parameter name collides with an identity-derived value |
| `NAMED_QUERY_PROJECTION_REQUIRED` | 400 (schema apply) | Named query omitted `select` / `selectExpr` |
| `NAMED_QUERY_PROJECTION_STAR` | 400 (schema apply) | `select: ["*"]` is refused |
| `NAMED_QUERY_TOO_MANY_JOINS` | 400 (schema apply) | Join count exceeds cap (default 3) |
| `NAMED_QUERY_COST_EXCEEDED` | 400 (schema apply) | Persist-time cost `1 + joins` exceeds cap (default 8) |
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` | WS error | Data-plane `subscribe` without a named-query `"name"` |
| `NAMED_QUERY_SUBSCRIBE_FILTER` | WS error | Subscribe-by-name also sent a client `filter` |
| `NAMED_QUERY_SUBSCRIBE_TARGET` | WS error | Subscribe-by-name `target` does not match the definition |
| `NAMED_QUERY_SUBSCRIBE_MUTATION` | WS error | Subscribe `"name"` addresses a named mutation |
| `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED` | WS error | Definition cannot be subscribed (e.g. unsupported shape) |
| `NAMED_QUERY_SERVER_TIME_NOT_SUBSCRIBABLE` | WS error | Definition has a `serverTime` parameter; only one-shot reads bind the server's clock (**NativeClients, 0.4.0**) |
| `NAMED_QUERY_SERVER_TIME_INVALID` | 400 | A `serverTime` parameter supplied in `args`, or (schema apply) declared where only a `Timestamp` comparison may use it (**NativeClients, 0.4.0**) |
| `DATA_PLANE_WRITE_STREAM` | WS error | Data-plane `stream_open` / `stream_rows` / `stream_close` |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | WS error | Per-connection (32) or per-identity (128) subscription cap |
| `DUPLICATE_SUBSCRIPTION_ID` | WS error | *Not emitted since BL-638, 0.1.37* — a `subscribe` for an id the connection holds now **replaces** it. Older servers send this; it is informational (the id is registered and delivering), not a reason to unsubscribe |
| `SLOW_CONSUMER` | WS close | Buffered-bytes high-water mark; reconnect and subscribe fresh (not a `gap`) |
| `CONFLATE_NOOP` | `snapshot_complete` warning | `conflate` is set without `collapse_inserts` and the key is not the table PK (insert-only no-op). Subscribe still registers. |
| `MQ_NOT_READY` | 409 / WS error | Materialized query is not `Ready`; watermark cannot satisfy a token. Retry; do not treat as a dead token. |

#### Protocol Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNSUPPORTED_VERSION` | 400 | Unsupported protocol version |
| `MALFORMED_REQUEST` | 400 | Request is malformed at the protocol level |

---

## Endpoints

### Database Catalog API

#### `GET /api/databases`

Lists databases visible to the caller.

**Credentials:** server auth only — a server admin key (`mk_srv_…`), a scoped server key (`mk_…` from `/api/auth/admin/api-keys`), or a server-auth user JWT with admin rights. An application service key (`mk_svc_`) or auth-admin key (`mk_adm_`) is refused with **403** `AUTH_KEY_ROUTE_MISMATCH` (the key is live; this route is not for it). Do not treat that as `AUTH_API_KEY_INVALID`.

**Query Parameters:**

| Param | Values | Description |
|-------|--------|-------------|
| `include` | _(omitted)_ | **Default.** Returns only operator-facing databases (`isInternal == false`). Hides internal infrastructure databases such as `_serverauth` and `_settings`. |
| `include` | `internal` | Returns **all** databases including internal infrastructure databases. Used by the Admin → Databases management view. |

**Response body** (`200 OK`):

```json
{
  "databases": [
    {
      "name": "myapp",
      "state": "Active",
      "createdAt": "2026-06-26T10:00:00.0000000Z",
      "options": {
        "maxMemoryShareBytes": null,
        "defaultTemperature": "Auto",
        "durability": "strict",
        "replicationMode": "Replicate"
      },
      "isInternal": false,
      "isAuthDatabase": false,
      "authDatabaseKind": "none",
      "auth": {
        "enabled": false,
        "database": null
      }
    }
  ],
  "count": 1
}
```

**Response metadata fields:**

| Field | Type | Description |
|-------|------|-------------|
| `isInternal` | `boolean` | `true` for Aouda-owned infrastructure databases (`_serverauth`, `_settings`). These are hidden from the default list and must not be used as data-explorer targets. |
| `isAuthDatabase` | `boolean` | `true` if this database contains auth system tables (`_users`, `_roles`, etc.). Application auth databases (`_auth`, `auth`, …) have `isInternal: false` and remain browsable in the data explorer. |
| `authDatabaseKind` | `"none"` \| `"server"` \| `"application"` | Identifies whether **this** database is an auth store. `"server"` is the server-level admin auth database (`/api/auth/admin/...`). `"application"` is an end-user auth database. `"none"` for regular data databases — this does **not** mean the data DB is unlinked. |
| `auth.enabled` | `boolean` | `true` when this database is linked to an auth database. Always present on list/get/create. |
| `auth.database` | `string` \| `null` | Linked auth database name, or `null` when unlinked. |
| `auth.keys` | object \| omitted | `anonKey` / `serviceRoleKey` / `publicKey` — **create and regenerate only**. GET and list omit `keys` and never re-emit `mk_*`. |

**Internal database definition:**

Aouda-owned infrastructure storage that is not an operator or application data target. Managed via dedicated admin APIs (`/api/auth/admin/...`, `/admin/config`, `/admin/notifications`), not the data-explorer dropdown.

| Database name | `isInternal` | `isAuthDatabase` | `authDatabaseKind` | Admin surface |
|---------------|:-----------:|:-----------------:|:-----------------:|---------------|
| `_serverauth` | `true` | `true` | `"server"` | `/api/auth/admin/...` |
| `_settings` | `true` | `false` | `"none"` | `/admin/config`, `/admin/cluster`, `/admin/notifications` |
| `myapp` (data) | `false` | `false` | `"none"` | Data explorer |
| `auth` (app auth) | `false` | `true` | `"application"` | Data explorer (tables) |

**Filtering rule:**

```
Default list: include iff isInternal == false
?include=internal: include all (no filter)
```

**Breaking change note:** Clients that previously listed `_serverauth` or `_settings` from the default `GET /api/databases` response will no longer see them. Use `?include=internal` to retrieve the full catalog.

---

#### `GET /api/databases/{name}`

Direct lookup of a specific database by name. Returns the database if it exists and is still serving, regardless of `isInternal`.

**Credentials:** a **read** credential for that database is enough — including the database's own application service key (`mk_svc_…`). A server credential also works. This is how a service process checks that its database exists; it does **not** need `GET /api/databases` (list).

**Metadata-only.** Capture `mk_*` keys from `POST /api/databases` (or regenerate). GET never re-emits keys. `auth` is always an object — `auth.enabled: false` means unlinked; do not treat a missing or null `auth` as the signal (older servers omitted it).

**Success (200):**

```json
{
  "name": "myapp",
  "state": "Active",
  "createdAt": "2026-06-26T10:00:00.0000000Z",
  "options": {
    "maxMemoryShareBytes": null,
    "defaultTemperature": "Auto",
    "durability": "strict",
    "replicationMode": "Replicate"
  },
  "auth": {
    "enabled": true,
    "database": "auth"
  },
  "isInternal": false,
  "isAuthDatabase": false,
  "authDatabaseKind": "none"
}
```

`options.durability` is the database's durability level — `strict`, `os`, `unlogged` or `memory` (**Lead S26, 0.6.0**; it replaces the boolean `options.enableWal`, which is gone). See [Write Path Durability](../guides/write-durability.md).

`authDatabaseKind: "none"` on this payload is expected for a **data** database. Linkage is `auth.enabled` / `auth.database`.

**Waiting for a database to be usable:** poll this endpoint until **200** and `state=Active` (or use `/ready` for process readiness, then this for the named DB). Do not wait on `GET /health`.

**Error responses:**

| Status | Code | Condition |
|--------|------|-----------|
| `404` | `DATABASE_NOT_FOUND` | Unknown name, already dropped, or `Dropping` (engine already unrouted). You cannot poll `state` on a dropping name — 404 means it is gone from serving. List may still show `Dropping` until background cleanup finishes. |
| `401` | `UNAUTHORIZED` | Missing or invalid credentials |

---

#### `GET /api/databases/{db}/token`

This node's current consistency token for the database (what a subsequent `AtLeast` read would wait for).

**Success (200):**

```http
HTTP/1.1 200 OK
X-Aouda-Token: 01a1b2c3d4e5f60708090a0b0c0d0e0f10111213
```

```json
{
  "database": "appdb",
  "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213"
}
```

Unknown database → 404 `DATABASE_NOT_FOUND`. Requires read authorization when the database has auth enabled.

---

#### `POST /api/databases`

Creates a new operator-facing database. The `isInternal` flag cannot be set by clients — it is always `false` for user-created databases. Internal databases are only created by Aouda bootstrap services.

**Credentials:** server auth only — same as [`GET /api/databases`](#get-apidatabases). A live `mk_svc_` / `mk_adm_` is **403** `AUTH_KEY_ROUTE_MISMATCH`. Schema apply (or an operator with a server key) creates databases for a service process; the service key itself does not.

**Request body:**

```json
{
  "name": "myapp",
  "durability": "strict",
  "replicationMode": "Replicate",
  "maxMemoryShareBytes": null,
  "defaultTemperature": "Auto",
  "kind": "data",
  "auth": { "enabled": true }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | Yes | Database name. |
| `durability` | string | No | The database's durability level (**Lead S26, 0.6.0**): `strict` (default — WAL written through before a write is visible), `os` (WAL written to the operating system, not forced to disk), `unlogged` (no WAL; (**Lead S26c, 0.6.0**) emptied by an open that does not follow a clean close if it was being changed), `memory` (no WAL, no data files). Lower case, exactly these four: anything else — `"Strict"`, `"MemoryOnly"`, `"everysec"` — is **400** `INVALID_REQUEST` naming the four levels. Read at every open; tables that name no level inherit it. See [Write Path Durability](../guides/write-durability.md#durability-levels-lead-s26-060). |
| `replicationMode` | string | No | `Replicate` (default) or `DoNotReplicate`. |
| `maxMemoryShareBytes` | number \| null | No | Cap on this database's share of the server's memory budget, in bytes (null: no cap). (**BL-980, 0.4.0:** renamed from `maxMemoryBytes`, which is now ignored — no cap; responses carry `options.maxMemoryShareBytes`.) |
| `defaultTemperature` | string | No | `Auto`, `HotOnly`, `ColdPreferred`. |
| `kind` | string | No | `"auth"` creates a standalone auth database. `"data"` or omit for a data database; both may include `auth`. `kind: "auth"` together with an `auth` object is rejected (400). |
| `allowSelfSignup` | bool | No | When `kind` is `"auth"`, whether self-service signup is enabled on the new database. Omitted: off. |
| `selfSignupRole` | string \| null | No | When `kind` is `"auth"`, role granted to self-service signups. Null or omitted: `db_writer`. |
| `auth.enabled` | bool | No | Shorthand: link to the single existing auth database (400 if none or more than one). |
| `auth.database` | string | No | Link to (or create) a named auth database. |
| `auth.allowSelfSignup` | bool | No | Whether self-service signup is enabled on the linked application database. Omitted: off. |
| `auth.selfSignupRole` | string \| null | No | Role granted to self-service signups on the linked application database. Null or omitted: `db_writer`. |

(**Lead S26, 0.6.0**) `enableWal` and `dataDurability` are gone, with no alias: a body carrying either is **400** `INVALID_REQUEST` naming `durability` (`enableWal: false` is `"unlogged"`, `dataDurability: "MemoryOnly"` is `"memory"`).

**Success (201):** same shape as GET, plus `auth.keys` when keys were generated (`anonKey`, `serviceRoleKey`, `publicKey`). **Save the keys now** — subsequent GET/list omit them.

```json
{
  "name": "myapp",
  "state": "Active",
  "auth": {
    "enabled": true,
    "database": "auth",
    "keys": {
      "anonKey": "mk_anon_...",
      "serviceRoleKey": "mk_svc_...",
      "publicKey": "mk_pub_..."
    }
  },
  "isInternal": false,
  "isAuthDatabase": false,
  "authDatabaseKind": "none"
}
```

Poll `GET /api/databases/{name}` until `state=Active` before schema apply.

---

#### `DELETE /api/databases/{db}`

Drops a database. Returns `204 No Content` immediately after the foreground switch. Needs `admin` on the database; for a
database with no linked auth database, once a server auth database exists, that is a server credential (the server admin,
`mk_srv_`), and an anonymous drop is `401` on the admin listener (**BL-1017, 0.4.0**; 0.3.0 dropped it).

**How it works (async, crash-safe):**

The endpoint performs a fast foreground switch, then returns `204`. All cleanup happens in the background via the persistent job queue:

1. **Foreground (synchronous, completes before 204):**
   - Verifies the database is in `Active` state (→ `404` if not found).
   - Removes the engine from query routing.
   - Persists `Dropping` state in `databases.json` (atomic write).
   - Writes a `DropDatabase` job record to `pending_jobs.json` (atomic write, crash-safe).
   - Returns `204 No Content`.

2. **Background (asynchronous, via `PendingOpsWorker` + `DropDatabaseJobHandler`):**
   - Phase 1: Engine `DropDisposeAsync` — drains WAL, disposes engine and branch engines; skips HRA snapshot (data is discarded, not persisted).
   - Phase 2: Directory delete — `Directory.Delete(path, recursive)` with exponential-backoff retry (1 s → 2 s → … → 30 s cap).
   - Phase 3: Registry completion — removes the database from `databases.json` entirely.

**Crash safety:** the job record in `pending_jobs.json` is written before `204` is returned. On any restart, `PendingOpsWorker.StartAsync` loads all `Running`/`Interrupted` jobs and re-executes them. On the recovery path, engine dispose (Phase 1) is skipped because the engine is no longer in memory; the worker proceeds directly to directory delete and registry completion.

**Idempotency:** Re-issuing `DELETE` while a drop is already in progress returns `204` without enqueuing a second job.

**Error responses:**

| Status | Code | Condition |
|--------|------|-----------|
| `404` | `DATABASE_NOT_FOUND` | Database does not exist or is already dropped |
| `401` | `UNAUTHORIZED` | Missing or invalid credentials |
| `403` | `FORBIDDEN` | Caller lacks permission to drop databases |

---



#### `POST /api/databases/{db}/query`

Execute a query against a table.

**Query Parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `format` | — | (**Lead S12, 0.6.0**) **Removed.** Any `format=` (even `columnar`) is refused `400 INVALID_FORMAT`; the JSON result is always column arrays (below), and frames are asked for with `Accept` |
| `readPreference` | `Primary` | Read preference (overrides header) |
| `at_least` | _(omitted)_ | Consistency token. Wins over `X-Aouda-Token`. |
| `waitMs` | 250 when gate active | Freshness wait; cap 30 000 |
| `onExceeded` | role-aware (`wait` on Primary/Standalone; `fetchPrimary` on a secondary) | `wait` \| `fetchPrimary` \| `fail` |
| `maxLagBytes` / `maxLagSeconds` / `maxStalenessMs` | unset | Lag budget (time is measured staleness) |
| `readYourWrites` | _(alias / fail-safe)_ | Call-site tighten only |

**Request Body:**

```json
{
  "database": "mydb",
  "table": "orders",
  "select": ["id", "customer", "total"],
  "where": {
    "and": [
      {"column": "total", "op": "gte", "value": 100},
      {"column": "status", "op": "eq", "value": "active"}
    ]
  },
  "orderBy": [
    {"column": "total", "descending": true},
    {"column": "customer", "descending": false}
  ],
  "offset": 0,
  "limit": 1000
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `table` | string | Yes | Table name to query |
| `select` | string[] | No | Columns to return (null = all) |
| `where` | object | No | Filter predicates |
| `orderBy` | object[] | No | Sort columns (see below) |
| `offset` | number | No | Rows to skip (default: 0) |
| `limit` | number | No | Max rows to return (default: 1000, max: 10000) |
| `crossPartitionAccess` | boolean | No | When `true`, queries on partitioned tables do not require a partition-key filter. Without this, queries on partitioned tables without a partition filter return `PARTITION_FILTER_REQUIRED`. Default: `false`. |
| `joins` | object[] | No | JOIN clauses to apply in order (see below). |
| `aggregates` | object[] | No | (**ColumnarRead S16, 0.3.0**) Aggregates to compute — see [Aggregates and GROUP BY](#aggregates-and-group-by). |
| `groupBy` | object[] | No | (**ColumnarRead S16, 0.3.0**) GROUP BY keys; requires `aggregates`. |
| `perKey` | object | No | `{ "keys": [...], "orderBy": "col", "latest": true }` — one row per distinct `keys` tuple, the one with the greatest (`latest: false`: least) `orderBy` value, ties to the lowest primary key. `select`, `orderBy` and the page apply to the collapsed rows; a `LatestPerKey` / `FirstPerKey` materialized query of the same shape answers it when current (`stats.routedTo`). Not with `aggregates`, `groupBy`, `distinct`, `selectExpr` or `joins` (400); `/query/count` refuses it (**BL-801, 0.3.0**). |

**Where Clause:**

```json
{
  "and": [{"column": "...", "op": "...", "value": ...}],
  "or": [{"column": "...", "op": "...", "value": ...}],
  "groups": [
    {
      "and": [{"column": "tenant_id", "op": "eq", "value": 42}]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `and` | Condition[] | All conditions must match (AND). |
| `or` | Condition[] | Any condition must match (OR). |
| `groups` | WhereClause[] | Nested sub-clauses. Each group is AND'd with the top-level conditions. Enables safe composition of independent filter layers (e.g., PLS partition scope + RLS row scope). Maximum nesting depth: **5** (`ProtocolConstants.MaxWhereClauseNestingDepth`). |

`groups` contains nested `WhereClause` objects that are AND-combined with the top-level `and`/`or`. Use `groups` to express nested boolean logic (e.g. `AND(OR(...))`). Each group can itself contain `and`, `or`, and nested `groups`.

**Operators:**

| Operator | Description | Example value |
|----------|-------------|---------------|
| `eq` | Equal | `"active"`, `true`, `42` |
| `ne` | Not equal | `"deleted"` |
| `gt` | Greater than | `100` |
| `gte` | Greater than or equal | `18` |
| `lt` | Less than | `65` |
| `lte` | Less than or equal | `1000.0` |
| `in` | Value in array (empty array is **400**) | `["admin", "owner"]` |
| `nin` | Value not in array (empty array is **400**) | `["deleted", "archived"]` |
| `like` | SQL LIKE pattern, **String columns only** | `"A%"`, `"%acme%"`, `"%985"` |

**Nulls (**BL-729, 0.2.0**):** a comparison with a null cell is never true, so `eq`, `ne`, `gt`, `gte`, `lt` and
`lte` all leave out rows whose column is null — `{"column": "qty", "op": "lt", "value": 5}` no longer returns rows with a
null `qty` (they compared as `0`), and `ne` does not return them either — nor does `nin` (**BL-734**), which
returned every null row. To select nulls, use `isNull`
(`{"op": "eq", "value": null}`, below), which is a null test rather than a comparison.

**Strings (**BL-750, 0.3.0**):** `gt`, `gte`, `lt` and `lte` accept a string value against a `String` column and
compare by **ordinal UTF-8 byte order** — Unicode code-point order, no locale collation, case-sensitive (`"Z"` sorts before
`"a"`, `"é"` after `"z"`). Before, the server rejected a string value for these operators (and in-process `ColumnRef.Gt(string)`
matched nothing). An `orderBy` on a `String` column sorts in the same order, with or without a `limit` and in joins too,
and so do `min` / `max` of one (**ColumnarRead, 0.3.0**); with a `limit` it followed the server's culture before, and
without one UTF-16 code units, which put a character at U+E000–U+FFFF after an emoji.

**Case-insensitive comparison (`ignoreCase`, server 0.1.24+):**

`eq`, `ne`, `in`, `nin`, and `like` accept an optional `"ignoreCase": true` alongside `column`/`op`/`value`, **String columns only**:

```json
{"column": "ticker", "op": "eq", "value": "nokr", "ignoreCase": true}
```

Default `false` — omitted, existing payloads and named-query hashes are unaffected. Matching then uses ordinal, case-insensitive comparison (`StringComparison.OrdinalIgnoreCase`), not a locale collation. Two things it deliberately does **not** change: primary-key/unique-column uniqueness stays always case-sensitive, so a case-insensitive `eq` against such a column can return more than one row if case-variant duplicates exist; and it never satisfies the [partition-filter rule](../guides/browser-tier-read-limits.md), the same treatment `like` already gets. A case-insensitive condition also skips zone-map/bloom-filter pruning for that predicate (full-page scan), same as `like`.

**`like` semantics:**
{: #like-semantics}

- `%` matches any sequence of characters, including none. `_` matches exactly one character.
- `\` escapes `%`, `_`, or `\` itself. A pattern that ends in a lone `\`, or escapes anything else, is
  rejected with `INVALID_REQUEST` (400) rather than treated as a literal.
- Matching is **ordinal and case-sensitive** by default, the same as `eq` on a String column — add
  `"ignoreCase": true` for a case-insensitive match (see above).
- A **null** column value never matches — not even `"%"` — following SQL's `NULL LIKE x` is unknown.
- The value is a *pattern*, not a comparand: a `like` condition against a non-String column is rejected
  (`INVALID_REQUEST`, 400), and a named query that declares one is rejected at `schema/apply` with
  `INVALID_OPERATOR`.
- `like` does **not** satisfy the [partition-filter rule](../guides/browser-tier-read-limits.md), even for
  a pure prefix pattern.
- There is no index acceleration: a `like` predicate is a scan of the column.

Encoding conventions:
- `isNull` — encode as `{ "op": "eq", "value": null }`
- `isNotNull` — encode as `{ "op": "ne", "value": null }`
- `between` — encode as two conditions: `{ "op": "gte", "value": lower }` + `{ "op": "lte", "value": upper }`
- Empty `in` / `nin` — **400** `INVALID_REQUEST` with `IN/NIN requires at least one value`. There is no empty-match 200.

Unknown operator strings return `INVALID_OPERATOR` (400). The same set applies to ad-hoc `/query` and to
`op` values inside a named-query definition; `schema/apply` rejects an unknown operator rather than
storing a definition that could never execute.

**Order By Clause:**

```json
[
  {"column": "columnName", "descending": false},
  {"column": "anotherColumn", "descending": true}
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `column` | string | Yes | Column name to sort by |
| `descending` | boolean | No | Sort direction: `false` (default) = ASC, `true` = DESC |

**Note:** Maximum 8 ORDER BY columns. First column is primary sort, subsequent columns are tie-breakers.

**Join Clause:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `table` | string | Yes | Right-side table name to join. |
| `type` | string | No | Join type: `"inner"` (default), `"left"`, `"right"`, `"full"`, `"cross"`. |
| `leftColumn` | string | No | Left key column for single-column joins. |
| `rightColumn` | string | No | Right key column for single-column joins. |
| `leftColumns` | string[] | No | Left key columns for multi-column joins. |
| `rightColumns` | string[] | No | Right key columns for multi-column joins. |
| `where` | object | No | A filter on the joined table, in the `where` format; its column names are that table's, and its values are read with that table's culture (a slash date on its `Date` column is read the way a `where` on that table reads it). It applies to the joined table's rows before they join (**BL-818, 0.3.0**). |

For single-column equality joins, use `leftColumn` + `rightColumn`. For multi-column equality joins, use `leftColumns` + `rightColumns` (same length). `"cross"` join requires neither.

**The query's `where` filters the base table; a join's `where` filters its joined table.** A joined row the join's `where`
rejects takes part in no match: an inner or cross join drops it, a left join answers the base row with `null` in that table's
columns.

**Row- and partition-level security on a joined table (BL-818, 0.3.0).** The caller's RLS and PLS for every joined
table are applied on that join's side, exactly as on a direct read of the table: a join onto a table the caller may read only
part of answers with that part. (From the 2026-10 architecture review until this change such a join was refused with `403`
`AUTHORIZATION_DENIED`.) An RLS rule that denies the caller the whole table joins against no rows of it. Still `403`: a
joined table the caller has no read grant on, a joined table whose partition-level security refuses the caller (no grant),
and a joined materialized-query result whose source security cannot be applied to it. The same holds for a named query that joins, single and batch,
and for `…/query/count`.

**Join example:**
```json
{
  "database": "mydb",
  "table": "orders",
  "select": ["orders.id", "customers.name", "orders.total"],
  "joins": [
    {
      "table": "customers",
      "type": "inner",
      "leftColumn": "customer_id",
      "rightColumn": "id"
    }
  ],
  "limit": 100
}
```

#### Aggregates and GROUP BY

(**ColumnarRead S16, 0.3.0.** Before this, `/query` had no aggregate except the `/query/count` route, and no GROUP BY.)

```json
{
  "database": "mydb",
  "table": "trades",
  "where": {"and": [{"column": "Ticker", "op": "eq", "value": "AAPL"}]},
  "groupBy": [
    {"column": "Source"},
    {"column": "DateTime", "bucket": "day", "alias": "d"}
  ],
  "aggregates": [
    {"func": "count"},
    {"func": "sum", "column": "Volume", "alias": "vol"},
    {"func": "min", "column": "Price"},
    {"func": "avg", "column": "Price"},
    {"func": "countDistinct", "column": "Venue"}
  ],
  "orderBy": [{"column": "vol", "descending": true}],
  "limit": 30
}
```

| Field | Values |
|---|---|
| `aggregates[].func` | `count` (no `column`: the rows; with a `column`: its non-null values), `sum`, `min`, `max`, `avg`, `countDistinct` (the distinct non-null values). Case-insensitive. Every function but `count` needs a `column`. |
| `aggregates[].alias` | The result column's name. Without it: `COUNT`, or `{FUNC}_{column}` — `COUNT_x`, `SUM_x`, `MIN_x`, `MAX_x`, `AVG_x`, `COUNT_DISTINCT_x`. |
| `groupBy[].column` | The column grouped by. |
| `groupBy[].bucket` | A time bucket of a `Timestamp` column: `minute`, `hour`, `day`, `week` (ISO, from Monday), `month`, `year`. The key is the bucket's start. |
| `groupBy[].alias` | The key column's name (the column's name otherwise). |

The answer is the ordinary query response (column arrays, or frames). It holds the group keys, then one column per
aggregate in the order asked; without `groupBy` it is **one row**. `where` selects the rows aggregated, and `orderBy` (over the
result's column names), `offset` and `limit` apply to the groups — **including `limit`'s default of 1000**, so a query that
can make more groups than that sets `limit` (up to 10,000) and pages with `offset`. Groups come in key order (ascending, nulls
last) unless `orderBy` says otherwise.

**Types:** `count` / `countDistinct` are `Int64`. `sum` is an exact `Int64` over integers (overflow is an error, not a wrapped
value), an exact `Decimal(18,s)` over a `Decimal(p,s)` column, and a `Double` over floating point. `min` / `max` keep the
column's type (exact at its scale). `avg` is a `Double` (**LoadSpeed S13, 0.4.0**: for a `Decimal(p,s)`, the exact sum
÷ 10^s ÷ count; it was divided in decimal first). (**LoadSpeed S13, 0.4.0**) A decimal `sum` of 18 digits or more is
refused as an overflow — *A Decimal sum does not fit Decimal(18,s).* — the same as in a materialized query. Over no row,
`count` is `0` and every other aggregate is `null`. A grouped query over no row answers no row.

**Refused (`400 INVALID_REQUEST`):**

- `groupBy` without `aggregates`;
- `select`, `selectExpr`, `distinct` or `joins` together with either;
- an unknown `func` or `bucket`, or a bucket of a non-`Timestamp` column;
- `sum` / `avg` of a column that is not a number, or any vector column;
- two result columns with the same name (give one an alias);
- an `orderBy` that names no result column;
- `/query/count` with either field.

An unknown column is `400 COLUMN_NOT_FOUND`. A caller denied the table gets the zero-row answer with the aggregate result's
columns. Named-query definitions do not carry these fields yet (**BL-796**): ⚠️ a definition that includes them is
accepted at `schema/apply` and the fields are dropped, so it answers plain rows.

**Response (column arrays):**

```json
{
  "columns": ["id", "customer", "total"],
  "types": ["Int64", "String", "Double"],
  "data": [
    [1, 2, 3],
    ["Alice", "Bob", "Charlie"],
    [100.50, 200.75, 150.00]
  ],
  "rowCount": 3,
  "stats": {
    "rowsScanned": 1000,
    "rowsReturned": 3,
    "segmentsAccessed": 5,
    "executionMs": 15
  }
}
```

`columns` names the result's columns, `types` their types, and `data` holds **one array per column**, in the order of
`columns`, all `rowCount` long: row *i* is index *i* of every array.

(**Lead S12, 0.6.0; breaking**) **This is the only JSON shape.** The row-object response (`format=rows`, `{"rows": [{…}]}`)
is gone, and with it the `format` parameter: a request that still sends `format=` — any value, `columnar` included — is refused
`400 INVALID_FORMAT`, so an old client is told instead of being handed a body it would misread. To get row objects, zip the
arrays on the client (both SDKs do this for you); for the binary form, ask for frames with `Accept` (below).

**`stats.routedTo` (**ColumnarRead S18, 0.3.0**):** the materialized query the answer was read from instead of the table,
when it was — rows, columns, `aggregates` / `groupBy` and `…/query/count` are all routed to a current result that holds the
answer ([routing](../guides/materialized.md#routing-a-read-to-a-maintained-result)); omitted when the table was read. The
answer is the same either way. It is in the frame response's end frame too (**Lead S09, 0.6.0**: it was the
`X-Aouda-Stats` header).

**`stats.windowCompletionRows` (**Horizon, 0.5.0**):** a read of a windowed materialized query's result that reached below
its horizon — the number of source rows read to compute that part with the query's own build code. Omitted when nothing was
computed. A read of a windowed result is complete for any range: groups at or after the horizon come from the result, the rest from
the source ([Materialized Queries](../guides/materialized.md)).

**JSON written from the columns (**ColumnarRead, 0.3.0**):** the JSON answer is now written straight from the
query's columns into the response and sent as they are written (chunked), instead of being built whole first. The bytes are
the same as before for every type. One case changes: a `Double` / `Float32` result cell that is `NaN` or infinite, which JSON
cannot represent, is now a clean `500 INTERNAL_ERROR` naming the column before anything is sent. Before, the response broke
after its headers. Ask for the frame response below, which carries these values.

**Column-batch frame response (**ColumnarRead, 0.3.0**; `ACB2` since **Lead S09, 0.6.0**):** a request whose `Accept`
header lists `application/vnd.aouda.column-batch-v2` gets the result as **column-batch frames**: the same binary format
`POST …/rows` and bulk-load `:append` accept, described under [the column-batch frame](#the-column-batch-frame-acb2). Both SDKs
ask for it by default. Send `Accept: application/vnd.aouda.column-batch-v2, application/json;q=0.5` and **branch on the
response's `Content-Type`**. A result the frame cannot carry answers JSON as before, and so does a request whose `Accept` names
only the retired `application/vnd.aouda.column-batch` (`ACB1`). A frame cannot carry a non-null vector cell, a computed or joined
column whose values are not its declared type, more than 4,096 columns, a column name it cannot hold (empty, or over 1,024 UTF-8
bytes), a single row that would decode past half the reader's 256 MB frame budget, or a string value over 16 MB of UTF-8. Errors
before the response starts are JSON `ProtocolError`s with their status. **An error after the response has started is the body's
end frame** (**Lead S09, 0.6.0**): `status: "error"` with the code, the message and the status the JSON error would have had,
after the frames already sent — which are not a result. Both SDKs drop those frames and raise the same typed error the JSON error
body raises, retried or not by its code as any error is (before, the server aborted the connection and both SDKs retried it as a
connection error, failing again at the same place). The request timeout (`Aouda:RequestTimeoutMs`, 30 s by default) still bounds a
streamed export: reached after the first frame, it is an error end frame `REQUEST_TIMEOUT` with status 504, as its JSON answer is.
Only a server that dies mid-body still cuts a response, and a body without its end frame is an error in both SDKs.
The same applies to `POST …/named-queries/{name}/query`; the named-query batch stays JSON.

- **Body:** data frames, each at most 65,536 rows — fewer for a wide result, so that no frame decodes past the reader's 256 MB a
  frame — then **one end frame** (**Lead S09, 0.6.0**). There is always at least one data frame: an empty result is one frame
  of 0 rows that still names every column. Every frame carries every column, in result order. A result that names a column twice
  is answered as JSON. The end frame's `rowCount` is the frames' rows, checked by the reader: a body cut anywhere — between two
  frames included — is an error, not a shorter answer.
- **One query exports every row (**LoadScan, 0.5.0**; streamed from its first row since **Lead S09, 0.6.0**).** A
  `POST …/query` asked for frames with **no page** (`limit: 0`, no `offset`) and no `orderBy`, `distinct`, grouping, aggregate,
  join or computed column is **streamed**: the server writes the frames while it reads the table, a batch at a time (tens of MB,
  sized to a quarter of the read path's memory ceiling), and states the row count and the statistics in the end frame. It no
  longer holds the first batch, or reads the table a second time to count it, before the first byte. Such a read is **not
  refused** at the read path's memory ceiling (`503 MEMORY_BUDGET_EXCEEDED`) or at `Aouda:Query:MaxResultRows`
  (`400 RESULT_TOO_LARGE`): both bound a result the server holds, and the same read answered as JSON — or as a named query — is
  still held whole and still refused there. A batch is sized from what the rows' frames actually cost — the first is one row
  group, so long strings are measured before they are batched — and the size only grows with what it meets: a table whose rows
  become much wider partway through can still pass the ceiling in one batch, and that read then ends with an error end frame
  (`MEMORY_BUDGET_EXCEEDED`). Its frames are cut per row group (at most 65,536 rows, never past half the reader's 256 MB frame
  budget) and come in the order the JSON answer's rows have. Its `stats.rowsScanned` is the rows the scan read (the rows of the row
  groups no statistic ruled out) and `executionMs` the time to the last frame (**Lead S09, 0.6.0**: before, `rowsScanned`
  repeated `rowsReturned` and `executionMs` was the time to the count). A string value over 16 MB fails a streamed read with an
  error end frame where a held read is answered as JSON.
- **Headers** carry only what is known before the first frame (**Lead S09, 0.6.0**); the rest of the JSON envelope is the
  end frame's:

| Header | Content |
|---|---|
| `X-Aouda-Column-Types` | JSON array of the logical type names, the JSON body's `types` (e.g. `["Int64","Decimal","Timestamp"]`) |
| `X-Aouda-Token` | The consistency token, as on every response |

| End frame field | Content |
|---|---|
| `rowCount` | Total rows across the data frames (the JSON body's `rowCount`) |
| `status` | `"ok"`, or `"error"` when the read failed after the response started |
| `error` | When `status` is `"error"`: `{ "code", "message", "status" }` — what the JSON error body would have said, and its HTTP status |
| `stats` | The JSON body's `stats` object, taken after the last frame |
| `totalMatches` | `totalMatches`, when the query asked for it (a named query with `count: true`) |
| `warnings` | The JSON body's `warnings` array, when there are any |

`X-Aouda-Row-Count`, `X-Aouda-Total-Matches`, `X-Aouda-Stats` and `X-Aouda-Warnings` are gone (**Lead S09, 0.6.0**).
Every CORS policy lists these headers in `Access-Control-Expose-Headers`, so a browser client reads them cross-origin —
together with `X-Request-Id`, `X-Aouda-Protocol-Version`, `Accept-Post` and `Retry-After` (**architecture review, next
train**: before, a browser read `Retry-After` as `null` on every 429 / 503).

- **Column kinds by logical type.** A null is the frame's null bit.

| Logical type | Frame kind | Value |
|---|---|---|
| `Int64`, `Int32`, `Int16`, `Byte`, `UInt16`, `UInt32` | `Int64` (1) | The value, widened |
| `UInt64` | `Int64` (1) | The value's 64 bits; read them as unsigned |
| `Double`, `Float32` | `Double` (2) | The value, widened (exact) |
| `Boolean` | `Bool` (3) | Bitmap |
| `String` | `String` (4) | A dictionary per frame |
| `Guid` | `String` (4) | The `D` form (`0f8fad5b-d9cb-469f-a165-70867728950e`) |
| `Timestamp` | `Timestamp` (5) | 100-ns ticks since the Unix epoch, UTC. The JSON body carries .NET ticks since `0001-01-01`, which is 621,355,968,000,000,000 more |
| `Date` | `Int64` (1) | Days since the Unix epoch, as in JSON |
| `Decimal` (`Decimal(p,s)`) | `ScaledDecimal` (8) | The unscaled value at the column's declared scale `s` |
| A column with no value of its own (e.g. a vector column, which a table query reads as null) | `Null` (0) | — |

(**LoadSpeed S13, 0.4.0**) A decimal column always goes out as `ScaledDecimal` at its declared scale; the 128-bit
`Decimal` kind (6) is retired and never sent. (A computed decimal column — a `selectExpr` — goes at its largest value's
scale; one whose values no 64-bit integer holds at one scale goes as JSON.) Up to 0.3.x a decimal column's kind was chosen from the values it held, and
an empty or all-null `Decimal(p,s)` column, or an undeclared `Decimal`, could come as kind 6.

`X-Aouda-Column-Types` tells a reader how to narrow a cell back to its type: `Int32`, `UInt64`, `Float32`, `Date`, `Guid`.
`GET /admin/capabilities` lists `queryColumnBatch: true`.

---

### Named queries

Named queries are **server-authored `QueryMessage` templates** identified by the unique schema name (`^[A-Za-z][A-Za-z0-9_.]*$`). Browser-tier callers (`mk_pub_*` and application user JWTs on the data-plane listener) **cannot compose a query** — they send the name plus arguments. Identity is injected from the validated principal; it is never an argument. The closed list of what that surface cannot do is [What a browser-tier read cannot do](../guides/browser-tier-read-limits.md).

There is **no HTTP route that registers a definition** and **no inventory list** besides `GET …/schema/export` (already name-keyed). Definitions deploy through declarative schema apply (`namedQueries` in `aouda.schema.json`). Clients send the name. Codegen (`npx @aouda/client generate` / `aouda generate`) is **optional** and emits Args/Row types only. See [Named queries](../guides/named-queries.md).

**Definition fields** (in `aouda.schema.json` `namedQueries` map) that this reference previously omitted:

| Field | Notes |
|---|---|
| `distinct` | Boolean. Subscribe refuses it (`NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`). A `distinct` over partition-key columns runs as a scan like any read (row groups the filter selects whole are answered from their statistics), so a deleted or truncated partition no longer appears; it was answered from the partition directories, which outlive their rows (**architecture review, 0.3.0**). The never-set `stats.distinctServedFromPartitionMetadata` flag is gone from the response (**ColumnarRead2 S04, 0.3.0**). |
| `count` | Boolean. When true, execute returns `totalMatches`; subscribe snapshot returns `total_matches`. Apply rejects unbounded count (`NAMED_QUERY_COUNT_UNBOUNDED`). |
| `freshness` | Declared on the named query: `readYourWrites`, `maxLagBytes`, `maxStalenessMs`, `waitMs`, `onExceeded`. See [Freshness](../guides/freshness.md). Budget-only edits do not fire `named_query_body_changed`. A name with no `freshness` block is fail-safe (primary-only + `readYourWrites`). |
| `aggregates` / `groupBy` | As on `/query`: the definition answers its keys and aggregates (no `select` then). Applied under `/query`'s rules — a shape `/query` would refuse, an unknown column, `sum` / `avg` of a non-number, a bucket of a non-`Timestamp`, or `count: true` beside them fails `schema/apply`. Until now these keys were silently dropped and the query answered plain rows (**BL-796, 0.3.0**). Subscribe refuses them. |
| `perKey` | As on `/query` (**BL-801, 0.3.0**). Subscribe refuses it. |
| `joins[i].where` | A filter on the joined table, with `{ "param": … }` values bound like the base `where` (**BL-818, 0.3.0**). |

There is no `?alias=` / `X-Aouda-Named-Query-Alias` / body `alias`. Freshness is keyed by the path, batch, or subscribe **name**.

Base path: `/api/databases/{db}/named-queries`

The execute and batch bodies are path-scoped. They do **not** require a `database` field (unlike ad-hoc `POST …/query`).

| Method | Path |
|--------|------|
| `POST` | `/api/databases/{db}/named-queries/{name}/query` |
| `POST` | `/api/databases/{db}/named-queries/batch` with `{ "name", "args" }` |
| `POST` | `/api/databases/{db}/named-mutations/{name}/execute` |

#### `POST /api/databases/{db}/named-queries/{name}/query`

Execute one named query by unique name.

**Request body:**

```json
{
  "args": {
    "ticker": "AAPL"
  }
}
```

`args` may be omitted or `{}` when the definition has no required parameters.

**Query parameters:** `readPreference` as on ad-hoc query. (**Lead S12, 0.6.0**) There is no `format` parameter any more: any `format=` is refused `400 INVALID_FORMAT`, and the result is always column arrays. Freshness: `at_least`, `waitMs`, `onExceeded`, `maxLagBytes`, `maxLagSeconds`, `maxStalenessMs`, `readYourWrites`. The named query’s declared `freshness` is keyed by `{name}`. A name with no `freshness` block is fail-safe: primary-only + `readYourWrites`. Loosening (call site weaker than the declared budget, or non-`Primary` on fail-safe) is 400 `FRESHNESS_LOOSENED`.

**Success (200):** same column-array shape as `POST …/query` (`columns`, `types`, `data`, `rowCount`, `stats`, **`token`**). When the definition declared `count: true`, `totalMatches` is present (total matching rows, ignoring limit/offset — counted by the same read as the page, over the same snapshot (**ColumnarRead, 0.3.0**)). When the name is deprecated, `warnings` is present:

```json
{
  "columns": ["ticker", "qty"],
  "types": ["String", "Int64"],
  "data": [["AAPL"], [10]],
  "rowCount": 1,
  "stats": { "rowsScanned": 2, "rowsReturned": 1, "segmentsAccessed": 1, "executionMs": 1 },
  "warnings": [
    { "code": "NAMED_QUERY_DEPRECATED", "name": "equity.quoteByTicker", "sunsetAt": "2026-12-01T00:00:00Z" }
  ]
}
```

**Errors:**

| Status | Code | When |
|--------|------|------|
| 404 | `NAMED_QUERY_NOT_FOUND` | Unknown name. Data-plane unsigned / unentitled (including `mk_anon_*`) also 404 with this code — not 401/403. Admin listener: missing token 401, unentitled 403. |
| 400 | `NAMED_QUERY_BIND_FAILED` / `NAMED_QUERY_PARAM_REQUIRED` | Bind-time type or constraint failure |
| 404 | `TABLE_NOT_FOUND` | Data-plane browser-tier and a touched table has `dataPlaneAccess: false` |
| 429 | `IDENTITY_QUOTA_EXCEEDED` | Data-plane quota |

Invoker ADRA always applies (PLS + RLS of the caller). There is no definer / `runAs` field. A definition that joins a
table the caller's PLS or RLS restricts is refused with `403 AUTHORIZATION_DENIED` naming the table, because a join
cannot carry that restriction ([joins and authorization](#post-apidatabasesdbquery); **architecture review, 0.3.0**).

#### `POST /api/databases/{db}/named-queries/batch`

Read-only batch envelope. Every element is evaluated against **one read snapshot**. HTTP **200 means the envelope was accepted** — a per-element ADRA deny or bind failure is a positional `{ code, error }` and does **not** fail the other slots.

**Request body:**

```json
{
  "queries": [
    { "name": "equity.quoteByTicker", "args": { "ticker": "AAPL" } },
    { "name": "equity.stockOverview", "args": { "accountId": 42 } }
  ]
}
```

**Cap:** 32 (`MaxNamedQueryBatchSize`). Named-mutation names are illegal in this envelope.

**Success (200)** — positional `results` (same length as `queries`):

```json
{
  "results": [
    {
      "columns": ["ticker", "qty"],
      "types": ["String", "Int64"],
      "data": [["AAPL"], [10]],
      "rowCount": 1,
      "stats": { "rowsScanned": 2, "rowsReturned": 1, "segmentsAccessed": 1, "executionMs": 1 }
    },
    {
      "code": "NAMED_QUERY_NOT_FOUND",
      "error": "Named query 'equity.unknown' was not found."
    }
  ]
}
```

**Envelope 400** (no `results`). Same `ProtocolError` shape as other HTTP errors (`code` + `error`):

Empty `queries`:

```http
POST /api/databases/trading/named-queries/batch
Content-Type: application/json

{ "queries": [] }
```

```json
{ "code": "NAMED_QUERY_BATCH_EMPTY", "error": "Named query batch requires a non-empty queries array." }
```

Over cap (33 names):

```json
{ "code": "NAMED_QUERY_BATCH_TOO_LARGE", "error": "Named query batch exceeds 32 elements." }
```

A named-mutation name in `queries`:

```json
{ "code": "NAMED_QUERY_BATCH_MUTATION", "error": "Named query batch must not include a named-mutation name." }
```

On the **data-plane listener**, unsigned or unentitled batch is **request-level 404** `NAMED_QUERY_NOT_FOUND` (not HTTP 200 with positional slots). Entitled callers still get HTTP 200 with positional `NAMED_QUERY_NOT_FOUND` for unknown names. The admin listener keeps 401/403 for unsigned/unentitled batch.

`INVALID_FORMAT` when the request names `?format=` at all (**Lead S12, 0.6.0**: every slot is column arrays; it used to choose `columnar` or `rows`).

Do **not** reuse `POST …/tables/{name}/rows/batch` (`BatchMutationMessage`) — that is ad-hoc update/delete on one table.

### Named mutations

Named mutations are the write-side mirror: name-addressed insert/update/delete templates over ADR 0037 expressions. **Invoker rights only.** They are **not** members of the read batch.

**`op`** is one of `insert`, `upsert` (**BL-637, 0.1.37**), `update`, `delete`.

**`insert` never overwrites.** An `op: "insert"` that names a primary key a live row already holds
answers **`409 DUPLICATE_PRIMARY_KEY`** (**BL-636, 0.1.37**; before that it arrived as
`500 INTERNAL_ERROR` with the real cause only in the server log). The `details` field carries the
engine's own sentence, including the offending key.

**`op: "upsert"`** (**BL-637, 0.1.37**) is write-or-replace by primary key: same `values` row
template as `insert`, same `batchParam` support, and a result carrying both `rowsInserted` and
`rowsUpdated`. It requires the table to declare a primary key — `upsert` on a keyless table is
refused at schema apply, since there would be nothing to match on. It is last-write-wins on the
whole row, not a partial merge. A key named twice in one batch is written once, holding the later
row's values (**ColumnarMerge S07, 0.2.0** — before it, a key new to the table and repeated in
one batch was stored twice). This is the op for a row written repeatedly under a key the caller
does not choose — a presence heartbeat or typing indicator keyed by
`derived: { "identity": "subject" }` — where `insert` succeeds exactly once and `update` never
succeeds at all. See [Named mutations § choosing
`op`](../guides/named-queries.md#choosing-op).


**What a `values` / `set` entry may be.** Exactly three forms:

| Form | Meaning |
|------|---------|
| `"Qty": 10`, `"Note": null`, `"Vec": [0.1, 0.2]` | A **bare literal** — any JSON value that is not an object. |
| `"Qty": { "param": "qty" }` | A **parameter hole**, filled from `args` at execute. |
| `"Qty": { "value": 10 }` | A **constant**, spelled explicitly. The wrapped value may be a scalar, `null`, or an array — but not an object. |

The object shape is reserved for those two one-key forms, because `{ "param": … }` already claims it: a bare object constant would be indistinguishable from a mistyped hole. Any other object node — an unknown key (`{ "valu": 0 }`), both keys at once, an empty object, or an object nested under `value` — fails **schema apply** with `NAMED_MUTATION_VALUE_NODE_INVALID`, naming the field (`values` / `set`), the column, and the keys it actually found. A definition stored before that check existed still loads, and its `execute` fails with `NAMED_MUTATION_BIND_FAILED` naming the column (BL-479 — previously such a node was carried into the row and surfaced as an untyped `INVALID_REQUEST` from deep in column conversion).

To store a JSON document in a `String` column, send it as a JSON **string** (`"Meta": "{\"a\":1}"`), not as a bare object.

**Batch insert (`batchParam`, BL-416).** An `op: "insert"` definition may declare `batchParam`, the name of a parameter carrying **many rows of arguments**, so one `execute` call inserts many rows. (**Lead S12, 0.6.0; breaking**) That argument is **column arrays**: `columns` names parameters, `data` holds one array per parameter (all the same length, one value per row), and the optional `absent` lists, per parameter, the rows that do not give it. Row *i*'s given cells fill that row's `{"param": …}` holes, overriding the top-level `args` of the same name, exactly as a row object's keys did before; a parameter a row does not give falls back to `args`. An **array of row objects is refused `400 ROW_OBJECTS_UNSUPPORTED`** (it was the only form before). `values` stays the per-row template. The batch parameter's `NamedQueryParamConstraint` **must** declare `maxItems` — schema apply rejects a `batchParam`-bearing definition without one (`NAMED_MUTATION_BATCH_MAX_ITEMS_REQUIRED`) and rejects `batchParam` on `update` / `delete` (`NAMED_MUTATION_BATCH_NON_INSERT` — `upsert` is allowed, being row-shaped; batching those is a separate, still-deferred predicate-shaped question — see [Named mutations](../guides/named-queries.md#named-mutations)). Bind is **all-or-nothing**: the cap (`maxItems` counts rows) and every row are checked before any row is inserted — one bad row fails the whole call and names its row index in `rowErrors`, the same shape as insert-transform per-row errors.

Definition:

```json
{
  "op": "insert",
  "table": "PriceTick",
  "values": {
    "ticker": { "param": "ticker" },
    "px": { "param": "px" }
  },
  "batchParam": "rows",
  "params": {
    "ticker": { "maxLength": 8 },
    "px": {},
    "rows": { "maxItems": 20000 }
  }
}
```

Execute:

```json
{
  "args": {
    "rows": {
      "columns": ["ticker", "px"],
      "data": [["AAPL", "MSFT"], [189.2, 402.1]]
    }
  }
}
```

A definition without `batchParam` is unaffected — `args` stays one flat object of parameter values, exactly as before.

**autoIncrement primary keys.** Omitting an `autoIncrement` column means the same as sending `0` — auto-generate — and `generatedValues` carries the allocated id either way. Any of the three entry forms works when you want to be explicit:

- `"Id": 0` — the shortest, when every call auto-generates.
- `"Id": { "value": 0 }` — the same constant, spelled explicitly.
- `"Id": { "param": "id" }` with `0` sent per row — when the caller decides.

⚠️ **Two boundaries did not change.** An explicit `null` is still not a request to generate — validation decides, and nothing new is claimed about nullability. And under `identityInsert: true`, omitting the column is **still an error**: you asked to control the identity and then did not supply one.

See [Insert rows](#post-apidatabasesdbtablesnamerows).

#### `POST /api/databases/{db}/named-mutations/{name}/execute`

**Request body:** `{ "args": { … } }`. For a `batchParam` definition, `args[batchParam]` is the rows as column arrays (`{columns, data, absent?}`, **Lead S12, 0.6.0**; it was an array of row objects, now refused `ROW_OBJECTS_UNSUPPORTED`); every other field is unchanged.

**Success (200):** the same mutation result the corresponding ad-hoc insert/update/delete returns (`rowsInserted` / `rowsUpdated` / `rowsDeleted`, optional `rows` for `RETURNING`), plus optional `warnings` (`NAMED_MUTATION_DEPRECATED`). A batch insert's `rowsInserted` is the number of batch rows bound. `insert` and `upsert` return `rows` too when the definition declares `returning` — the rows written, an upsert's one per key as stored (**NativeClients, 0.4.0**; BL-639).
(**Horizon, 0.5.0**) On a table with [retention](../guides/retention.md), `insert` and `upsert` results carry `expiredRows` —
rows whose time lies below the table's horizon or is an explicit `null` — omitted when 0. Such a row is left out before it is logged,
except an upsert row that replaces a key a read returns: it is logged and buffered, hidden by every read and dropped by the next
flush (the key disappears from reads), and counted in `rowsUpdated` **and** in `expiredRows`. The two counts overlap only for such a
row, so `rowsInserted + rowsUpdated + expiredRows` can exceed the rows sent.

**Errors:** `NAMED_MUTATION_NOT_FOUND` (404), `NAMED_MUTATION_BIND_FAILED` (400), `NAMED_QUERY_PARAM_REQUIRED` (400 — a required arg was omitted, including a missing `batchParam`), `NAMED_MUTATION_RETURNING_OVERFLOW` (400), `MEMORY_BUDGET_EXCEEDED` (503 + `Retry-After` — a DELETE / UPDATE whose matches do not fit the read budget, nothing changed; **BL-817, 0.3.0**), `WRITE_CONFLICT` (409 — a DELETE / UPDATE whose matched rows other writers kept changing through 16 attempts, nothing changed, retry; **BL-881, 0.3.0**), `TABLE_NOT_FOUND` (data-plane opt-in), `IDENTITY_QUOTA_EXCEEDED` (429). On the data-plane listener, unsigned or unentitled execute is 404 `NAMED_MUTATION_NOT_FOUND` (same envelope as unknown); admin listener keeps 401/403. A batch-element bind failure's 400 body includes `rowErrors: [{ "index", "code", "message" }]` naming the offending row index — the whole call fails, no row is inserted. `NAMED_MUTATION_BIND_FAILED` also covers a `values` / `set` entry that is an unrecognised object node, naming the column. Schema apply also rejects `NAMED_MUTATION_UNCAPPED_DELETE`, `NAMED_MUTATION_RETURNING_STAR`, `NAMED_MUTATION_VALUE_NODE_INVALID`, `NAMED_MUTATION_BATCH_NON_INSERT`, and `NAMED_MUTATION_BATCH_MAX_ITEMS_REQUIRED`.

### Access-surface diff

Schema branch review can report **widening** of what a principal class can read (tables, columns, named-query projections). Computation lives in the engine so CI can gate a merge without Studio. See [Access-surface diff](../guides/access-surface.md).

#### `POST /api/databases/{db}/schema/diff?access=true`

Without `?access=true` the body stays a raw `SchemaDocument` and `accessSurface` is omitted (byte-compatible with earlier clients).

With `?access=true`:

- Raw `SchemaDocument` body → `__public__` / `mk_pub_*` findings only.
- Wrapper (when identities or resolver overrides are sent):

```json
{
  "schema": { "tables": { }, "namedQueries": { } },
  "identities": { "$schema": "https://aouda.io/identities/v1.json", "identities": [ ] },
  "resolvers": [ ],
  "baseResolvers": [ ]
}
```

Posting identities requires **Admin**. `?access=true` without identities is **Read**.

**400:** `ACCESS_SURFACE_TOO_MANY_IDENTITIES` (more than 32 fixtures), `AUTH_IDENTITY_INVALID`.

#### `POST /api/databases/{db}/branches/{name}/diff`

Empty `{}` is structural-only. `{ "includeAccess": true, "identities"?: … }` attaches `accessSurface`. Studio always sends `includeAccess: true`.

#### `POST /api/databases/{db}/branches/{name}/insert`

Insert rows into a table on a branch; they are written to the branch's own segments only. The body is the table and the rows as
[column arrays](#column-arrays-the-write-body) (**Lead S12, 0.6.0; breaking**: it was `{"table", "rows": [{…}]}`, now refused
`400 ROW_OBJECTS_UNSUPPORTED`). The rows are inserted as `POST …/tables/{name}/rows` inserts them.

```json
{ "table": "orders", "columns": ["id", "status"], "data": [[1, 2], ["pending", "shipped"]] }
```

**Response:** `200` `{ "table": "orders", "rowsInserted": 2 }`. A body without `table` or without a row is `400 INVALID_REQUEST`.

---

### Materialized query endpoints

Base path: `/api/databases/{db}/materialized-queries`

| Method | Path | Auth (when DB auth enabled) | Description |
|--------|------|------------------------------|-------------|
| GET | `/` | Read | List all materialized queries (array of status objects). |
| GET | `/{name}` | Read | Status for one query; `404` if missing. |
| POST | `/` | Admin | Create a query. Body below. `204 No Content` on success. (**BL-884, 0.3.0**) A create whose first build is refused for capacity (memory, or a full WAL) still answers `204`: the definition is durable, the query exists **behind** (`current: false`) and is built once there is room. It used to answer `503` and leave the query in `Error`, so the retry was refused as "already exists". |
| DELETE | `/{name}` | Admin | Drop query and storage; `204` on success. |
| POST | `/{name}/query` | Read | Return the materialized rows as column arrays (see response; **Lead S12, 0.6.0**: they were row objects). |
| POST | `:refresh` | Admin | **Pooled refresh (BL-474)**: rebuild several queries, decoding each shared source table **once**. Select with `sourceTable` (optionally `staleOnly`) **or** `names` — exactly one of the two. Returns per-name outcomes; see below. |
| POST | `/{name}:refresh` | Admin | Trigger a full rebuild of the MQ result table (shadow-build pattern). `await: true` waits up to the server window (`Aouda:MaterializedQueries:RefreshAwaitTimeout`, default 120s — see below): **200** `{ "status": "complete" }` when the wait finishes, **202** `{ "status": "scheduled" }` on timeout (refresh **keeps running**). `await: false` is fire-and-forget **202** `scheduled`. Result table is readable with stale data throughout. A **202 never cancels the rebuild**, regardless of why the wait ended. |

> **BL-419 (0.1.22).** Before this fix, `:refresh` sat under the server's global 30s
> `Aouda:RequestTimeoutMs` default like every other endpoint, and that ambient deadline started
> *before* — and could preempt — the endpoint's own `RefreshAwaitTimeout` wait (30s at the time, so
> the two raced and the ambient one, being first in the pipeline, always won). The preempted
> response could come back with an empty body on a success status. `:refresh` now carries its own
> request-timeout policy derived from `RefreshAwaitTimeout` (`+30s` grace) so the ambient default
> can never again race it, and a success response always carries the body it advertises. If you see
> this failure mode against an older server, treat a `202` with an empty body as `"scheduled"` (see
> `clients/typescript.md` / the C# `Aouda.Client` release notes for the client-side workaround).
> The same train also raises `Aouda:MaterializedQueries:RefreshAwaitTimeout`'s default from 30s to
> **120s** — `202 scheduled` was the normal answer for any MQ worth materializing at 30s, which
> surprised every caller. Non-positive values still skip the wait and return `202` immediately (the
> rebuild still runs).

### Pooled refresh: `POST /api/databases/{db}/materialized-queries:refresh`

Queries over one source table are built from a **single traversal** of it, so three OHLC rollups over
`EquityTrade` decode it once between them rather than three times. Use this instead of calling
`{name}:refresh` once per query.

> With `postLoadMqBehavior: "auto"` (the default) a bulk load already brings its affected
> queries current — after its commit, in the background (**WorkloadCore S09, 0.3.0**) — do not refresh at all. Pooled refresh is for the case where you
> loaded with `"skip"` deliberately.

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sourceTable` | string? | one of | Refresh every materialized query over this table. |
| `names` | string[]? | one of | Explicit list. An unknown name is a `404`. |
| `staleOnly` | bool? | no | With `sourceTable`: restrict to queries a `postLoadMqBehavior: "skip"` load (or anything else) left stale. `400` without `sourceTable`. |
| `await` | bool? | no | Same semantics, same window and the same BL-419 guarantees as `{name}:refresh`. Default `false`. |

Supplying both `names` and `sourceTable`, or neither, is a `400` naming the conflict.

**Response** — `200` when an `await: true` wait completed, `202` when it is still running:

```json
{
  "status": "complete",
  "sourceGroups": 1,
  "results": [
    { "name": "EquityTradeOhlc1H", "state": 1 },
    { "name": "EquityTradeOhlc1M", "state": 3, "error": "Source table 'EquityTrade' column 'Px' was not found …" }
  ]
}
```

| Field | Description |
|-------|-------------|
| `status` | `complete` (200) or `scheduled` (202), same vocabulary as `{name}:refresh`. On `scheduled`, `results` lists what was scheduled, not outcomes. |
| `sourceGroups` | Source tables traversed. `results.length / sourceGroups` is what the pooled call saved over calling `{name}:refresh` per query. |
| `results[].state` | Raw `MaterializedQueryState`: `0` Building, `1` Ready, `2` Rebuilding, `3` Error — the same encoding `GET /{name}` uses. |
| `results[].error` | Why that query is not `Ready`; absent when it is. |

**A per-query failure is reported, not thrown.** One query that exceeded its memory budget appears as
`state: 3` with its message while its siblings appear as `state: 1`, and the response is still
`200`/`202` — the request was carried out. Check `results`, not the status code. A genuine capacity
refusal (the server could not start the work at all) is `503` with `Retry-After`, as elsewhere.

**Authorization** is `Alter`, as on `{name}:refresh`. With `sourceTable` the check is scoped to that
table, so a caller with no grant on it can neither refresh nor enumerate its materialized queries.

**Create body** (camelCase JSON):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique materialized query name. |
| `sourceTable` | string | Yes | Base table name. |
| `type` | number | Yes | `1` LatestPerKey, `2` FirstPerKey (MIN of `orderBy`, not arrival order), `3` Aggregate, `4` Filter, `5` TopNPerGroup (N rows per group; source must have a PK). |
| `configJson` | string | Yes* | Type-specific config JSON text (same as engine `MaterializedQueryDefinition.ConfigJson`). |
| `config` | object | Yes* | Alternative: embedded object; server serializes to JSON if `configJson` omitted. |
| `window` | object? | No | (**Horizon, 0.5.0**) `{ "keep": "7d", "column"? }`, beside `config`: keep only the result's groups whose window column lies within `keep` of the server's clock; older ones are computed from the source on read. Only an `aggregate` with a time bucket (`truncateToMinute` / `Hour` / `Day` / `Week`) or a `topNPerGroup` grouped by a time column takes one; `keep` is a whole number of `m` / `h` / `d` / `w` and a whole multiple of the bucket; `column` names the bucket's output when there is more than one, and is required on a `topNPerGroup`. Every other declaration — a `latestPerKey`, `firstPerKey` or `filter`, no bucket, a month or year bucket, a source with retention — is `400` naming its reason, and nothing is created. Omitted: an unbounded query. See [Materialized Queries](../guides/materialized.md). |
| `currency` | string? | No | (**Lead S27b, 0.6.0**) How the result is kept: `"current"` (omitted: the default — maintained off each commit) or `"rebuild"` — never maintained incrementally: a change to a source leaves it behind (`current: false`, `isStale: true`, never routed to) until it is rebuilt, once its sources have been quiet for a moment (2 s), after a bulk load into them, or on `:refresh`. Under a steady stream of writes a rebuild also starts 60 s after the first change, but a commit during it leaves the query behind again: a source written more often than a rebuild takes keeps it behind (BL-1149; **Lead group 6 review, 0.6.0**). A token read (`?at_least=`) waits for the rebuild — give it a `waitMs` above the quiet period. Part of the definition: a change of level is a drop and a create. Any other name is a `400` naming the two; `"rebuild"` with `updateMode` sync or `maxCoalesceMs` is a `400` (a rebuild query applies no incremental batch). |

`configJson` / `config` must provide valid **FilterConfig**, **LatestPerKeyConfig**, **AggregateConfig**, or **TopNPerGroupConfig** JSON for types `4`, `1`/`2`, `3`, and `5` respectively (see engine storage types under `Aouda.Engine.Storage.Materialized`). FirstPerKey uses LatestPerKeyConfig with `descending: false`. TopNPerGroupConfig adds required `n` (1..10000). AggregateConfig's `groupByColumns` entries are objects — `{ "column": "region" }`, or `{ "column": "time", "function": "TruncateToHour" }` for a time bucket. (**BL-980, 0.4.0**) The v1 plain-string form (`"groupByColumns": ["region"]`) is `400 INVALID_REQUEST`, and a stored definition in that form is refused when it is read; up to 0.3.x both were read.

**Query response** (`POST .../query`) — column arrays (**Lead S12, 0.6.0; breaking**: it was `"rows": [{…}]`, one object per
row):

```json
{
  "columns": ["col1", "col2"],
  "data": [[1, 2], ["a", "b"]],
  "rowCount": 2,
  "stats": {
    "rowsScanned": 2,
    "rowsReturned": 2,
    "executionMs": 0.42
  },
  "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213"
}
```

`data` holds one array per entry of `columns`, each `rowCount` long; row *i* is index *i* of every array. `columns` are the result
table's public columns in their declared order (its maintenance columns are never shown), and an empty result still names them.
Unlike `POST …/query` there is no `types` array.

`token` is the MQ **maintenance watermark** (the source position the MQ has incorporated), not this node's WAL offset. Token-bearing MQ reads wait on that watermark. GET list/status objects include the same field.

(**Horizon, 0.5.0**) On a windowed query, the answer is complete for any range, and `stats.windowCompletionRows` counts the
source rows read to compute the part below its horizon (omitted when nothing was computed), as on `POST …/query`.

### Status response: `GET /api/databases/{db}/materialized-queries/{name}`

The list route returns an array of the same object.

```json
{
  "name": "EquityTradeOhlc1M",
  "sourceTable": "EquityTrade",
  "type": 1,
  "state": 1,
  "rowCount": 41200,
  "createdUtc": "2026-09-19T08:14:02.0000000Z",
  "lastUpdatedUtc": "2026-09-19T09:41:55.0000000Z",
  "currentLag": "00:00:00.2500000",
  "rebuildProgress": null,
  "errorMessage": null,
  "isStale": false,
  "staleReason": null,
  "current": true,
  "amplification": {
    "sourceRowsIngested": 1000000,
    "keysPlanned": 1000000,
    "priorRowsRead": 958800,
    "applies": 512,
    "resultRowsUpserted": 1000000,
    "resultRowsDeleted": 0,
    "rebuildSourceRowsScanned": 0,
    "rebuildResultRowsWritten": 0,
    "sourceColumnsDecoded": 12000000,
    "sourceColumnsDeclared": 3000000,
    "resultRowsWritten": 1000000,
    "writeAmplification": 1.0,
    "readAmplification": 4.0,
    "isEmpty": false
  },
  "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | integer | Raw `MaterializedQueryType` enum value. **No `JsonStringEnumConverter` is registered anywhere in the server**, so this is an integer on every enum on every route. |
| `state` | integer | Raw `MaterializedQueryState` enum value (`Building`, `Ready`, `Rebuilding`, `Error`). |
| `rowCount` | integer | Rows currently in the result table. |
| `currentLag` | string? | **How long this query has been behind its source**, or `null` when it is not behind. `TimeSpan` in .NET constant format (`"00:01:30"`), not a number of milliseconds. See the honesty note below (**BL-642, 0.1.38**). |
| `rebuildProgress` | number? | `0.0`–`1.0` while `Rebuilding`; `null` otherwise. |
| `isStale` / `staleReason` | boolean / string? | **The result is readable but is not current.** Absent on servers that predate the field, which deserializes as `false`. See below. |
| `pendingDeferredJobs` | integer | (**BatchFirst S09, 0.1.40**) How many committed bulk loads this query has not yet incorporated because they are waiting for its table's deferred pass (an `"auto"` load folded by the pass — held while its table goes on loading, **LoadSpeed M.3, 0.4.0**; **WorkloadCore S10, 0.3.0**: every load but a `"skip"` one; until the 0.4.0 also a `"deferred"` load). `0` when none; absent on older servers. While it is above zero the query is also `isStale` (behind) and not `current`, with a `staleReason` like "2 bulk load(s) into its source are pending the table's pass…"; it is owed work, not holed, so `staleOnly` does not select it and `currentLag` counts from the oldest owed load's commit (**WorkloadCore S10**). `:refresh` of the query runs the table's pass at once. |
| `stalenessMs` | integer? | (**ColumnarMerge S01, 0.2.0**) **How old the oldest change this result does not yet reflect is**, in milliseconds: a queued insert or update, an unfinished bulk-load publish, a deferred load waiting for its pass, or the hole a lost update left. **Omitted** when the result reflects every commit it has been given (read absent as `0`, on older servers too). This is the number a freshness target means — see below. |
| `current` | boolean | (**WorkloadCore, 0.3.0**) **Whether the result is current for a reader starting now** — the one rule the server uses to route a source-table read to this result and to decide whether a consistency token is covered by it: no lost update (`isStale` for that reason), nothing queued or in flight for it or for a query it is built on (an incremental update, a bulk-load publish, a load past its commit point), no commit to its source still being routed, and its frontier (`token`) at the WAL head. `false` on older servers. |
| `frontierLagBytes` | integer? | (**WorkloadCore, 0.3.0**) How many WAL bytes the query's frontier is behind the head. **Omitted** when it is at the head. A size, not a position: positions are only ever on the wire as tokens. |
| `amplification` | object? | Per-query write- and read-amplification. **Omitted** when the query has neither ingested nor scanned anything — treat absent as "no data yet", not as zero. |
| `token` | string? | The query's **frontier** (**WorkloadCore, 0.3.0**; the maintenance watermark before): the WAL position its result incorporates, encoded as a consistency token. A position to wait for, not a claim that the result is current — `current` is the claim. |
| `window` | object? | (**Horizon, 0.5.0**) The query's window as declared — `{ "keep": "7d" }`, with `column` when one was named. Absent for an unbounded query. |
| `horizon` | string? | (**Horizon, 0.5.0**) The result's current horizon (UTC): groups at or after it are stored, older ones are computed from the source on read. It follows the server's clock minus `keep` on the query's bucket, is persisted before any reader sees it, and never moves back. Absent without a window. |
| `currency` | string | (**Lead S27b, 0.6.0**) The query's currency as declared: `"current"` or `"rebuild"`. Always present. A `rebuild` query a change has left behind reads `current: false` and `isStale: true`, with a `staleReason` that names its currency, until its rebuild publishes; a `:commit` that waits for its queries (`mqWaitMs`) does not wait for it. |

#### ⚠️ Is this query current? Read `isStale`, `staleReason` and `currentLag` — not `state`

**`state: Ready` means the query is *readable*. It does not mean it is *current*.** The two are
deliberately separate, and reading `state` alone is the mistake this section exists to prevent.

A materialized query that has fallen behind still holds real rows and still answers reads **by its
own name**. Making it unreadable would turn "slightly stale" into "unavailable", which is strictly
worse — so it stays `Ready`. What it no longer does (**ColumnarRead S18, 0.3.0**) is answer a
read of its **source table**: a query is routed to a result only while the result is current, and
otherwise the table answers, with the same rows as ever. Its currency is reported by these fields:

| Field | Meaning |
|---|---|
| `isStale` | `true` when the result is **not current**: an update was lost before it reached the maintainer, a maintenance apply failed part-way, or work is queued and unfinished. (**WorkloadCore S09, 0.3.0**) An update is lost only when its query's maintenance backlog is past its bound (64 MiB an update lane; `staleReason` begins "Maintenance backlog past its bound"), and the query is rebuilt; it used to be dropped after a 250 ms wait for a full queue (BL-427). (**BL-989, 0.4.0**) A query built on another query's result is also `isStale` while that query is behind — its `staleReason` names it ("The query it is built on, 'x', is behind…") and its own `pendingDeferredJobs` stays `0`; before, it read `isStale: false` with `current: false`. |
| `staleReason` | Why, in a sentence meant for a human. `null` unless `isStale`. |
| `currentLag` | How long the query has **been behind** without a break. `null` when it is not behind — including for a caught-up query that has been idle for days. |
| `stalenessMs` | (**ColumnarMerge S01, 0.2.0**) How **old** the oldest change the result does not reflect yet is. Omitted when current. |
| `current` | (**WorkloadCore, 0.3.0**) The server's own yes/no: current for a reader starting now. It is the answer routing and the token check use, so it can be `false` while `isStale` is `false` — for the moment a commit to the source is being routed, or a load is past its commit point and its maintenance has not finished. (A query behind only because the query it is built on is behind reports `isStale` too since **BL-989, 0.4.0**.) |

⚠️ **For "how fresh is this query", read `stalenessMs`, not `currentLag`.** Under a steady stream of
inserts that never lets a query's queue empty, `currentLag` grows for as long as the stream runs — it is
how long the query has been continuously behind — even when every insert is applied within a few hundred
milliseconds. `stalenessMs` stays at the age of the oldest change still owed. A query ingesting 50,000
rows a second and applying each batch promptly reports `currentLag` in minutes and `stalenessMs` in the
low hundreds.

⚠️ **`currentLag` is not "time since the result was last updated".** A caught-up idle query reports
`null`, not a number that grows forever. If you are computing freshness, `null` means *current*, not
*unknown*.

**This matters because the previous behaviour was silence (BL-642, 0.1.38).** Before it,
`currentLag` was `null` on every response — the field existed on the wire and was never populated.
On one production deployment, **twelve of thirteen materialized queries reported `state: Ready`,
`errorMessage: null`, `currentLag: null` while holding 1.7 % of their source rows.** Every consumer
read stale data as current. A client that polls `state` and nothing else will still do so.

**Recommended check:**

```jsonc
// current (WorkloadCore, 0.3.0: read `current`; older servers: `isStale: false` and `currentLag: null`)
{ "state": 1, "isStale": false, "currentLag": null, "current": true }

// readable, but behind — act on this (WorkloadCore S10, 0.3.0: a load's queries are owed the table's pass;
// before, this read "3 bulk-load publish(es) for this query have been queued and have not finished. …")
{ "state": 1, "isStale": true, "pendingDeferredJobs": 3, "current": false,
  "staleReason": "3 bulk load(s) into its source are pending the table's pass. The result is readable but is not current; refresh the query, or update the table, to bring it current now.",
  "currentLag": "00:00:12.4310000", "stalenessMs": 4120 }
```

> **Removed: `workingSetTruncated` (BL-583, 0.1.38).** It was hard-wired `false` from the train
> that removed the working set it described, and — being omitted from JSON when `false` — had
> already stopped appearing in every response, so no shipped server could send `true`. Read
> `isStale` / `staleReason` instead. ⚠️ `@aouda/client` (TypeScript) still carries the field; its
> removal rides that package's own bump.

#### The `amplification` object

| Field | Type | Description |
|---|---|---|
| `sourceRowsIngested` | integer | Source-row changes this query was asked to absorb, on either path. The denominator of `writeAmplification`. A batch dropped for backpressure is **not** counted — it is reported by `SubscriptionDroppedUpdates`, and counting it would make the ratio *fall* exactly when the engine loses data. |
| `keysPlanned` | integer | Result-table keys a maintainer asked to read back before computing its mutation. |
| `priorRowsRead` | integer | Prior result rows that read-back returned (≤ `keysPlanned`). |
| `applies` | integer | Calls into the result applier — batches, not rows. |
| `resultRowsUpserted` / `resultRowsDeleted` | integer | Result rows physically written / removed by incremental maintenance. |
| `rebuildSourceRowsScanned` / `rebuildResultRowsWritten` | integer | The same, for a **rebuild** rather than incremental maintenance. |
| `sourceColumnsDecoded` | integer | Source column *values* materialised on this query's behalf — rows scanned × the width the scan actually decodes. |
| `sourceColumnsDeclared` | integer | Column values the query's **declaration** says it needs, over the same rows. |
| `resultRowsWritten` | integer | `resultRowsUpserted + resultRowsDeleted + rebuildResultRowsWritten` — every result row this query caused to be written. A rebuild's writes are included on purpose: a numerator that excluded them would go *down* as the engine got worse. |
| `writeAmplification` | number? | `resultRowsWritten / sourceRowsIngested`. **`null`** while nothing has been ingested — a ratio over an empty denominator is not zero. |
| `readAmplification` | number? | `sourceColumnsDecoded / sourceColumnsDeclared`. `1.0` once the scan reads only what the query declared; greater while it reads every column. |
| `isEmpty` | boolean | `true` when nothing has been recorded. |

⚠️ **Per query, not per process.** An eight-query fan-out reports eight of these, and a process total
cannot be divided back out.

⚠️ **Since process start, never persisted.** A restart zeroes every counter, and the ratios are not
comparable across one. These are monotonic totals, not rates — poll and difference for a rate.

🔎 `readAmplification` above `1.0` is expected today: a materialized query's source scan decodes every
column of every row even when the query declared three. On a twelve-column table feeding a
three-column aggregate that is `4.0`. Nothing configurable changes it; the field exists so the cost
is a measurement rather than an inference.

See [Materialized queries §2.11d](../guides/materialized.md#amplification).

### Create body: result-table storage

The schema file's `materializedQueries` entries accept an optional `storage` object:

```json
{ "storage": { "storageTemperature": "ColdPreferred" } }
```

| Field | Values | Default |
|---|---|---|
| `storage.storageTemperature` | `Auto`, `HotOnly`, `ColdPreferred` | **Version-dependent — see below.** |

**The default is `Auto` for every query type** — `aggregate`, `latestPerKey`, `firstPerKey`,
`filter` and `topNPerGroup` alike. Residency is policy, not something inferred from the query type.
An unrecognised value fails **at schema apply**, not at query time:
`Invalid storageTemperature '…' on materialized query '…'`.

⚠️ **`storage` carries temperature only.** `residency` sub-fields (`memoryRowCap`,
`targetMemoryBytes`, `memoryFilter`, `hotOnlyBackstop`) are not accepted here — set them on the
result table via `PUT /api/databases/{db}/tables/{name}/policy` (the result table's name is the
query's name). They do not survive a destructive schema replace.

⚠️ **`storage` is a schema-file field, not an HTTP create field** (**BL-625, 0.1.37**).
This page previously said `POST /api/databases/{db}/materialized-queries` accepted it too. It does
not: `MaterializedQueryCreateBody` has no such property, so a `storage` key posted to that route is
deserialized away in silence and the result table is created with the engine default. Create the
query through `POST .../schema/apply`, or set the result table's policy afterwards with
`PUT /api/databases/{db}/tables/{name}/policy`.

---

### Schema seed

#### `POST /api/databases/{db}/schema/seed`

Apply idempotent seed data. Tables must already exist.

**Request:** seed document root — the same format as `aouda.seed.json`. Each table's rows are
[column arrays](#column-arrays-the-write-body) (**Lead S12, 0.6.0; breaking**: they were `"rows": [{…}]`, which is now refused
`400 ROW_OBJECTS_UNSUPPORTED`):

```json
{
  "tables": {
    "orders": {
      "columns": ["id", "status"],
      "data": [[1, 2], ["pending", "shipped"]]
    }
  }
}
```

A table may carry `absent` as any write body does; a cell left absent is not part of that row's seed.

**Response:** `200 OK` — `SeedApplyResult` with per-table `insertedCount` and `skippedCount` (existing primary keys skipped).

---

### Tables Endpoints

🔒 **A table that schema apply created refuses HTTP DDL in every `InferenceMode`** (**BL-1177, 0.7.1**; before, only in
`Extend`). `DELETE` and `PATCH` of the table, `PUT …/options`, add, alter, reorder or drop of a column, and a `PUT …/policy` that
changes `storageTemperature` or `retention` answer `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN`. A `PUT …/policy` that restates the current
temperature and changes only `memoryRowCap`, `targetMemoryBytes`, `memoryFilter` or `hotOnlyBackstop` is served, because the schema file
declares no residency. A table created by `POST …/tables` is not affected. `InferenceMode` decides only what an insert into a
missing table does: `Off` and `On` answer `404`, and `Extend` creates the table.

#### `GET /api/tables`

List all tables with statistics.

**Query Parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `includeSystemTables` | `false` | Include system tables (e.g., materialized query result tables) |

**Response:**

```json
{
  "tables": [
    {
      "name": "orders",
      "columnCount": 5,
      "rowCount": 12500,
      "createdAt": "2026-02-04T10:30:00.0000000Z",
      "lastModifiedAt": "2026-02-04T14:25:30.0000000Z",
      "sizeBytes": 1048576,
      "policy": {
        "storageTemperature": "Auto"
      }
    }
  ],
  "count": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Table name |
| `columnCount` | number | Number of columns |
| `rowCount` | number | Total row count across all segments — always the exact total. (**BL-980, 0.4.0**) `rowCountIsExact` is gone: a catalog segment entry without a row count (only an older build wrote one) is refused rather than counted as a lower bound, so the flag had nothing left to say. Both SDKs drop it (`TableSummary.rowCountIsExact` in `@aouda/client`). (**Horizon, 0.5.0**) It is the stored count: on a table with [retention](../guides/retention.md) it includes rows hidden below the horizon until they leave the table. |
| `createdAt` | string | ISO 8601 timestamp when table was created. (**BL-980, 0.4.0**) Always set — including for a table a replica or a point-in-time replay registered from the log, which carried none before |
| `lastModifiedAt` | string | ISO 8601 timestamp when table/data was last modified. (**BL-980, 0.4.0**) Always set, as `createdAt` |
| `sizeBytes` | number | Approximate size in bytes across all segments |
| `policy` | object | Storage policy |
| `keyMapResident` | boolean, optional | (**ColumnarMerge S05, 0.2.0**) `true` when the table's key map covers every tier, so an insert or upsert checks whether a key exists without reading a segment; `false` while it is still loading, when the server's memory governor refused it, or when it evicted part of the map to make room (**WorkloadCore, 0.3.0**) — existence is then checked by reading segments, correctly and more slowly. Absent for a table without a key map (no primary key, or a `pkUniqueness` other than `Strict`). |

#### `GET /api/tables/{name}`

Get table detail with columns.

**Response:**

```json
{
  "name": "orders",
  "columns": [
    {
      "name": "id",
      "type": "Int64",
      "isNullable": false,
      "isAutoIncrement": true,
      "primaryKeyOrder": 1
    },
    {
      "name": "customer_id",
      "type": "Int64",
      "isNullable": false,
      "reference": {
        "targetTable": "customers",
        "targetColumn": "id",
        "source": "declared"
      }
    },
    {
      "name": "total",
      "type": "Double",
      "isNullable": true
    }
  ],
  "policy": {
    "storageTemperature": "Auto",
    "residency": {
      "hotOnlyBackstop": "RefuseWrites"
    }
  },
  "durability": {
    "level": "strict",
    "source": "database"
  }
}
```

(**Lead S26, 0.6.0**) `durability` is the level the table's writes actually get — `strict`, `os`, `unlogged` or `memory` —
and `source` says where it came from: `table` when the table named its own level, `database` when it inherits the database's. It
is the effective level, not the requested one: a table that named `strict` in a database at `os` reads `os`. A table that inherits
from a database since reopened at `memory` reads `unlogged`. `policy.residency.dataDurability` is gone (its `MemoryOnly` is the
`memory` level). See [Write Path Durability](../guides/write-durability.md#durability-levels-lead-s26-060).

(**Horizon, 0.5.0**) A table with [retention](../guides/retention.md) reports `policy.retention` (`{ "keep": "90d" }`) and
`policy.horizon` — the instant (UTC) below which its rows are gone. Both are omitted for a table without retention.

**Column Detail Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Column name |
| `type` | string | Aouda data type |
| `isNullable` | boolean | Whether column allows null values |
| `isAutoIncrement` | boolean | Whether column has server-assigned auto-increment values |
| `primaryKeyOrder` | number? | Position in composite primary key (null if not PK) |
| `partitionKeyOrder` | number? | Position in composite partition key |
| `clusterOrder` | number? | Position in cluster columns for storage ordering |
| `partitionFunction` | string? | Function to derive partition key (TruncateToDay, TruncateToHour, etc.) |
| `reference` | object? | Reference to another table's column (see below) |
| `precision` / `scale` | number? | A `Decimal(p,s)` column's declaration; omitted for every other column (**ColumnarCore S13, 0.2.0**) |

**Reference Info:**

| Field | Type | Description |
|-------|------|-------------|
| `targetTable` | string | Name of the table this column references |
| `targetColumn` | string | Name of the column in the target table |
| `source` | string | `"declared"` (explicit) or `"inferred"` (from naming conventions) |

#### `GET /api/tables/{name}/schema`

Get enhanced schema introspection with aggregated key arrays and relationships.
This endpoint is optimized for schema exploration tools like Aouda Studio.

**Response:**

```json
{
  "name": "orders",
  "columns": [
    {
      "name": "id",
      "id": 1,
      "type": "Int64",
      "isNullable": false,
      "isAutoIncrement": true,
      "primaryKeyOrder": 1
    },
    {
      "name": "customer_id",
      "id": 2,
      "type": "Int64",
      "isNullable": false,
      "partitionKeyOrder": 1,
      "reference": {
        "targetTable": "customers",
        "targetColumn": "id",
        "source": "declared"
      }
    },
    {
      "name": "order_date",
      "id": 3,
      "type": "Timestamp",
      "isNullable": false,
      "clusterOrder": 1
    }
  ],
  "primaryKey": ["id"],
  "partitionKey": ["customer_id"],
  "clusterColumns": ["order_date"],
  "indexes": [],
  "relationships": [
    {
      "from": { "column": "customer_id" },
      "to": { "table": "customers", "column": "id" },
      "source": "declared",
      "cardinality": "many-to-one"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Table name |
| `columns` | array | Column definitions with full metadata |
| `primaryKey` | string[] | Column names forming the primary key, in order |
| `partitionKey` | string[] | Column names forming the partition key, in order |
| `clusterColumns` | string[] | Column names for cluster ordering, in order |
| `indexes` | array | Secondary indexes (placeholder for future) |
| `relationships` | array? | Relationships to other tables (both declared and inferred) |

**Column fields**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Column name — what request and response bodies use |
| `id` | number | **Catalog column id.** Stable for the life of the column, unique within the table, assigned in creation order and never reused after a drop. Absent on servers older than the release that added it (deserializes to `0`, never a valid id). |
| `type` | string | Aouda data type |
| `isNullable` | bool | Whether the column accepts null |
| `isAutoIncrement` | bool? | Omitted when false |
| `primaryKeyOrder` / `partitionKeyOrder` / `clusterOrder` | number? | 1-based position in the respective key; omitted when not part of it |
| `partitionFunction` | string? | Partition function, when the column is part of a partition key |
| `reference` | object? | Foreign-key target (`targetTable`, `targetColumn`, `source`) |
| `precision` / `scale` | number? | A `Decimal(p,s)` column's declaration; omitted for every other column (**ColumnarCore S13, 0.2.0**) |

**Why `id` matters.** Storage, the write-ahead log and engine diagnostics identify columns by id, not
by name — an engine message can name `id=34` where the schema shows only names. A column that is
dropped and re-added under the **same name** gets a **new** id, so `id` is what tells you whether the
column you are looking at is the same column the engine is talking about. Note that the response
carries names and keys but not the declarative `derived` expression or check constraints; for the
full declarative document use `GET /api/databases/{db}/schema/export` (see
[Schema management](../guides/schema.md)).

#### `GET /api/schema/relationships`

Get all tables and relationships for ERD visualization.

**Response:**

```json
{
  "tables": [
    {
      "name": "orders",
      "columns": [
        { "name": "id", "type": "Int64", "isPrimaryKey": true },
        { "name": "customer_id", "type": "Int64", "isReference": true },
        { "name": "total", "type": "Double" }
      ]
    },
    {
      "name": "customers",
      "columns": [
        { "name": "id", "type": "Int64", "isPrimaryKey": true },
        { "name": "name", "type": "String" }
      ]
    }
  ],
  "relationships": [
    {
      "from": { "table": "orders", "column": "customer_id" },
      "to": { "table": "customers", "column": "id" },
      "source": "declared",
      "cardinality": "many-to-one"
    }
  ]
}
```

**Relationship Info:**

| Field | Type | Description |
|-------|------|-------------|
| `from` | object | Source endpoint (`table` optional for single-table context, `column` required) |
| `to` | object | Target endpoint (`table` and `column` required) |
| `source` | string | `"declared"` or `"inferred"` |
| `cardinality` | string | `"many-to-one"`, `"one-to-one"`, or `"one-to-many"` |

#### `GET /api/schema/typescript`

Generate TypeScript interfaces for all tables.

**Query Parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `comments` | `true` | Include JSDoc comments in output |
| `schema` | `true` | Include Schema interface and TableName type |
| `namespace` | - | Optional namespace wrapper for generated types |

**Response:** `text/plain` with TypeScript code

```typescript
/**
 * Auto-generated TypeScript types from Aouda schema.
 * Generated at: 2026-02-05T10:30:00Z
 *
 * WARNING: Int64/UInt64 values exceeding 2^53 may lose precision in JavaScript.
 */

/** orders table */
export interface Orders {
  /** Primary key (auto-increment) */
  id: number;
  /** References customers.id */
  customer_id: number;
  total: number;
  created_at: Date;
}

/** customers table */
export interface Customers {
  /** Primary key (auto-increment) */
  id: number;
  name: string;
  email: string;
}

/** Type-safe table schemas for AoudaClient */
export interface Schema {
  tables: {
    orders: Orders;
    customers: Customers;
  };
}

/** Table names as a union type */
export type TableName = 'orders' | 'customers';
```

#### `POST /api/databases/{db}/tables`

Create a new table.

**Request:**

```json
{
  "database": "mydb",
  "name": "orders",
  "columns": [
    {
      "name": "id",
      "type": "Int64",
      "primaryKeyOrder": 1,
      "isAutoIncrement": true
    },
    {
      "name": "customer_id",
      "type": "Int64",
      "reference": {
        "targetTable": "customers",
        "targetColumn": "id"
      }
    },
    {
      "name": "total",
      "type": "Double"
    }
  ],
  "policy": {
    "storageTemperature": "Auto"
  }
}
```

A `Decimal` column carries `"precision"` and `"scale"` — `1 ≤ precision ≤ 18`, `0 ≤ scale ≤ precision` — to declare
`Decimal(p,s)` (**ColumnarCore S13, 0.2.0**; see [Data types](#data-types)). (**LoadSpeed S13, 0.4.0; breaking**)
Both are required: `"type": "Decimal"` without them is `400` — *A Decimal column declares its precision and scale
(Decimal(p,s), 1 ≤ p ≤ 18, 0 ≤ s ≤ p); the undeclared 128-bit Decimal is retired.* — and a precision above 18 is `400`
*Decimal precision above 18 is not supported (got N).* A `Decimal(p,s)` partition key is refused.

(**Horizon, 0.5.0**) `policy.retention` — `{ "keep": "90d" }`, a whole number of minutes, hours, days or weeks (`m` / `h` /
`d` / `w`) — declares [retention](../guides/retention.md): rows whose first cluster column is older than the server's clock minus
`keep` are not returned, not written (counted as `expiredRows`) and dropped by whole segments. The table's first cluster column
(lowest `clusterOrder`) must be a `Timestamp` or `Date`; it may be nullable. A refused declaration — no such column, a `keep` that is
not a duration, an edge table, a table with a vector column — is `400` naming its reason. The response's `policy` carries `retention` and `horizon`.

**Authorization fields** (top-level, beside `columns`): `partitionLevelSecurity`, `authMode` (`jwt-claim`, `auth-db-pls`,
`auth-db-rls`), `permissionDimension`, `permissionColumn`, `rlsResolverName`, `plsClaimBinding`. (**BL-1176, 0.7.0; breaking**)
`authMode: "auth-db-pls"` requires both `permissionDimension` — the grant namespace, an opaque name matched byte-for-byte against a
partition grant's `dimension` — and `permissionColumn`, the column the grant keys are compared with, which must name one of the
table's columns exactly. Neither is inferred: a dimension spelled like a column does not select it, and the partition key is not a
fallback. Missing or unmatched, the create is `400 INVALID_REQUEST` naming the field; `permissionColumn` with another `authMode` is
`400` too. `PUT /api/databases/{db}/tables/{name}/options` takes the same fields; an omitted `permissionColumn` is kept while the
table stays `auth-db-pls` and dropped when the request moves it to another mode. The table detail and `…/schema` responses carry
`permissionColumn`. See [Data Authorization §19.4](../auth/authorization.md#194-mode-2-auth-db-pls-enhanced-pls).

```json
{
  "database": "markets",
  "name": "SpotQuote",
  "columns": [
    { "name": "SecurityId", "type": "String", "primaryKeyOrder": 1, "partitionKeyOrder": 1 },
    { "name": "Source", "type": "String", "primaryKeyOrder": 2, "partitionKeyOrder": 2 },
    { "name": "Bid", "type": "Double", "isNullable": true }
  ],
  "authMode": "auth-db-pls",
  "permissionDimension": "fx_source",
  "permissionColumn": "Source"
}
```

**Response:** `201 Created` with table detail

#### `DELETE /api/databases/{db}/tables/{name}`

Delete a table. Refused `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN` on a table schema apply created (**BL-1177, 0.7.1**). To drop that
table, remove it from the schema file and apply with `allowDestructive: true`.

**Response:** `204 No Content`

#### `PATCH /api/databases/{db}/tables/{name}`

Rename a table.

**Request:**

```json
{
  "database": "mydb",
  "newName": "orders_archive"
}
```

**Response:** `200 OK` with table detail

#### `PUT /api/databases/{db}/tables/{name}/policy`

Update table storage policy and per-table residency. Works on **any** table, including a
materialized query's result table (whose name is the query's name). The one limit (**BL-1177, 0.7.1**): on a table schema apply
created, a request that **changes** `storageTemperature` or `retention` is refused `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN`, because the
schema file owns both. Restate them and change only the residency fields, or change them in the file.

**Request:**

```json
{
  "database": "mydb",
  "storageTemperature": "Auto",
  "memoryRowCap": 50000,
  "targetMemoryBytes": 536870912,
  "memoryFilter": "{\"and\":[{\"column\":\"status\",\"op\":\"eq\",\"value\":\"open\"}]}",
  "hotOnlyBackstop": "RefuseWrites"
}
```

| Field | Type | Description |
|---|---|---|
| `database` | string | Required. |
| `storageTemperature` | string | `Auto`, `HotOnly` or `ColdPreferred`. |
| `retention` | object? | (**Horizon, 0.5.0**) `{ "keep": "30d" }`: declares or changes the table's [retention](../guides/retention.md). Omitted = unchanged. A body that sets only `retention` may leave `storageTemperature` out (the temperature is kept). Once declared, retention **cannot be removed**: an omitted or `null` `retention` leaves it as it is (only the embedded `SetTablePolicyAsync` refuses a policy without it); a longer `keep` leaves the horizon where it is. Refused (`400`) on a table whose first cluster column is not a `Timestamp` or `Date`, on a table a windowed query completes from, and on a table a query reads that does not group by the retention column (BL-1060). |
| `memoryRowCap` | integer? | Cap on resident (hot) rows for this table. |
| `targetMemoryBytes` | integer? | Per-table hot-byte budget. On a `HotOnly` table this is the **pin's reservation size**; on an `Auto` table it is a demotion target. |
| `memoryFilter` | string? | JSON predicate naming which rows are preferred-hot. Operators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`. Affects demotion *ordering* only: a segment whose statistics rule out every row for the filter is demoted first. (**ColumnarRead S14, 0.3.0**: the server now applies it; before, the preference only ever took effect in the engine's tests.) |
| `hotOnlyBackstop` | string? | What happens when honouring a `HotOnly` pin would breach the ceiling: `RefuseWrites` (default) or `DemoteAnyway`. |
| `pinAllInMemory` | boolean? | ⚠️ **Retired — sending it is a `400`**, not a no-op. Use `storageTemperature: "HotOnly"`. |

⚠️ **Sentinel convention — omitted is not the same as cleared.** `null` / omitted means *leave
unchanged*. `0` **clears** a `memoryRowCap` or `targetMemoryBytes`; `""` clears a `memoryFilter`. A
`0` or negative value is rejected as a *setting* (`400`) precisely so it can be a safe clear
sentinel.

⚠️ **`memoryRowCap`, `targetMemoryBytes` and `memoryFilter` are enforced on `Auto` tables only.** On
a `HotOnly` or `ColdPreferred` table they validate and persist, and the maintenance sweep ignores
them — so a row cap set on a pinned table does nothing and reports no error. This catches people most
often on materialized query result tables, where the temperature was declared on the query rather
than here: see [Hot/Cold Storage](../guides/hot-cold.md#mq-result-tables).

🔎 **Enforcement is a convergence target reached by a periodic sweep, not an instantaneous ceiling**
— a burst can exceed the target between sweeps. The process ceiling is the hard one.

(**Horizon, 0.5.0**) The policy detail carries `retention` and `horizon` (the instant, UTC, below which the table's rows are
gone) when the table has retention; both are omitted otherwise.

**Response:** `200 OK` with policy detail

#### `POST /api/databases/{db}/tables/{name}/columns`

Add a column to a table.

**Request:**

```json
{
  "database": "mydb",
  "name": "total",
  "type": "Double"
}
```

`"precision"` / `"scale"` beside `"type": "Decimal"` add a `Decimal(p,s)` column, as on create (**ColumnarCore S13,
0.2.0**); (**LoadSpeed S13, 0.4.0**) they are required, and a `Decimal` without them is refused `400` as on create. A
column cannot be changed to or from `Decimal(p,s)`, or to another precision or scale: add a new column and copy.

**Response:** `201 Created` with column detail

#### `PATCH /api/databases/{db}/tables/{name}/columns/{columnName}`

Alter a column: `type`, `nullable`, `autoIncrement`, `references`, and/or `newName` (rename) — at least one, or `400`. The
`encoder` field is gone (**BL-768, 0.3.0**): it changed nothing since columns choose an encoding per vector, and a
request carrying only `encoder` is now refused as having nothing to alter. The example renames a column.

**Request:**

```json
{
  "database": "mydb",
  "newName": "total_amount"
}
```

**Response:** `200 OK` with column detail

#### `DELETE /api/databases/{db}/tables/{name}/columns/{columnName}`

Drop a column. Refused `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN` on a table schema apply created, in every `InferenceMode`
(**BL-1177, 0.7.1**). This is the call the C# client's default reconcile (`AutoReconcileSchema`, `Unsafe`) makes for each column
its model does not declare.

**Response:** `204 No Content`

---

### Data Mutation Endpoints

#### Column arrays: the write body

(**Lead S12, 0.6.0; breaking**) **Every JSON write body sends its rows as column arrays** — the shape a query result already
has. It is read the same way on every surface: `POST …/tables/{name}/rows`, a bulk-load [`:append`](#post-jobidappend) sent as JSON,
a WebSocket [`stream_rows`](#stream_rows), a [branch insert](#post-apidatabasesdbbranchesnameinsert), a named mutation's
[`batchParam`](#named-mutations) argument, and the [schema seed](#schema-seed) (`aouda.seed.json` too). Each surface keeps its own
fields beside these three:

```json
{
  "columns": ["id", "ts", "price"],
  "data": [
    [1, 2, null],
    ["2026-10-18T09:00:00Z", "2026-10-18T09:00:01Z", "2026-10-18T09:00:02Z"],
    [1.5, 2.5, 3.5]
  ],
  "absent": { "id": [2] }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `columns` | string[] | Yes | The column names: distinct, non-empty. |
| `data` | array[] | Yes | **One array per column**, in the order of `columns`, all the same length — that length is the row count. Row *i* is index *i* of every array. |
| `absent` | object? | No | Per column, the row indexes whose cell is **not given**: `{"<column>": [rowIndex, …]}`. The `data` slot of an absent cell must be `null`. |

**Absent is not null.** An absent cell is what a key left out of a row object used to be: an absent `autoIncrement` cell is
generated, and an absent column that has a default takes its default. An explicit `null` is a null — an `autoIncrement` cell sent as `null` is not generated. In the example,
rows 0 and 1 give their ids and row 2's is generated. A column absent in **every** row can simply be left out of `columns`; `absent`
is only needed when some rows give a column and others do not. ⚠️ **A bulk-load `:append` does not apply defaults:** an absent cell
there is stored as null (an absent `autoIncrement` cell is still generated), for a JSON body as for a frame (BL-1104).

**Values** are read as before: an integer is an integer, a fraction keeps the scale it is written with, a string is a string, and an
array or an object (a vector, a nested value) is converted the way the column's type takes it. A value is judged exactly as the same
cell sent in a [column-batch frame](#the-column-batch-frame-acb2) — the same conversions, the same errors.

**Refused (`400`, nothing written):** `columns` and `data` that do not match (a different number of arrays, arrays of different
lengths, a name given twice), an `absent` that names a column `columns` does not, a row past the body, a row twice, or a cell whose
`data` slot is not `null`. The message names the column and the row. **A body that still carries `rows`** — row objects, the shape
every write surface took up to this train — is refused **`400 ROW_OBJECTS_UNSUPPORTED`**, naming the shape to send. There is no
fallback: upgrade the client. The SDKs' insert helpers keep taking rows and pivot them for you — `Aouda.Client` from this train,
`@aouda/client` from **Lead S14** (the same train).

To turn row objects into this shape: collect every key any row has as `columns` (in first-seen order), give each column an array
with one slot per row, and put a row's value in its slot — or, when that row has no such key, `null` in the slot and the row's index
in `absent[column]`.

#### `POST /api/databases/{db}/tables/{name}/rows`

Insert one or more rows into a table.

**Request Body** (**Lead S12, 0.6.0**: [column arrays](#column-arrays-the-write-body); it was `"rows": [{…}]`, now refused
`400 ROW_OBJECTS_UNSUPPORTED`):

```json
{
  "database": "mydb",
  "table": "orders",
  "columns": ["status", "price"],
  "data": [["pending", "shipped"], [100.50, 200.00]],
  "writeConcern": "majority",
  "identityInsert": false
}
```

The `id` column (an `autoIncrement` key) is left out of `columns`, so both rows' ids are generated.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `table` | string | Yes | Table name (should match URL path `{name}`) |
| `columns` | string[] | Yes | (**Lead S12, 0.6.0**) The column names. See [column arrays](#column-arrays-the-write-body). |
| `data` | array[] | Yes | (**Lead S12, 0.6.0**) One array of values per column, all the same length. |
| `absent` | object? | No | (**Lead S12, 0.6.0**) Per column, the rows whose cell is not given (not null). |
| `writeConcern` | string? | No | Write-concern override for this request. Allowed: `"one"`, `"majority"`, `"all"`. Null/omitted = use table/database default. |
| `identityInsert` | bool? | No | When `true`, enable **identity-insert** for this request (SQL Server `IDENTITY_INSERT` / Bond `isAutoIncrementDisabled: true`). Every `autoIncrement` column must be given (not absent) and non-null on every row; values (including literal `0`) are stored as-is with **no** ID allocation; after a **successful** insert the runtime counter advances to `max(inserted)` per autoIncrement column so subsequent normal inserts do not collide. Null/`false` = default behavior: `0` means auto-generate and `generatedValues` returns the allocated id; **omitting** the column (leaving it out of `columns`, or listing the row in `absent`) means the same as `0`. An explicit non-zero id without the flag is stored, and the counter moves past it before the insert commits, so a later generated id cannot repeat it (**ColumnarMerge S02, 0.2.0**) — as a JSON integer, a numeric string (`"300"`) or an integral number (`5.0`, `1e2`) alike, each stored as that integer (**BL-703, 0.2.0**; a string id used to be stored without moving the counter, and a fractional form failed with a `500`). |

**Response:** `200 OK`

```json
{
  "rowsInserted": 2,
  "executionMs": 5,
  "generatedValues": {
    "columns": ["id"],
    "data": [[42, 43]]
  },
  "writeConcernStatus": {
    "requested": "majority",
    "achieved": "majority",
    "acksReceived": 2,
    "acksRequired": 2,
    "wasDegraded": false
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsInserted` | number | Number of rows successfully inserted |
| `executionMs` | number | Server-side execution time in milliseconds |
| `generatedValues` | object? | Generated values for auto-increment columns, as column arrays (**Lead S12, 0.6.0; breaking**: it was an object keyed by row index, `{"0": {"id": 42}}`): `columns` names the generated columns and `data` holds one array per column with **one cell per request row** — the value generated for that row, or `null` where the row gave its own value. Row *i* of the request is index *i*. Only present when the server allocated IDs — so not under `identityInsert: true`, where client-supplied values are stored as-is. |
| `writeConcernStatus` | object? | Write-concern acknowledgement details. Null when `writeConcern` is `"one"` (no replication wait). See `WriteConcernStatus` below. |
| `expiredRows` | number? | (**Horizon, 0.5.0**) Rows of the request accepted and left out because their time lay below the table's [retention](../guides/retention.md) horizon, or was an explicit `null` in a nullable time column — never stored, never returned, not in `rowsInserted`. A row that omits the column is not counted (it is stored, hidden by every read and dropped by the next flush). **Omitted when 0** (always, on a table without retention). Not reported by `POST …/rows/batch` or the WebSocket write stream. |

**Materialized queries follow the insert, off its commit (**WorkloadCore S09, 0.3.0**).** An insert hands its change batch to its
table's queries' maintainers at its commit, in the table's commit order and without waiting, and they apply it in the
background. The `200` does not wait for them, so right after it a query may be a moment behind: read with the insert's
consistency token (`token` / `X-Aouda-Token`) to wait for them, as for any other write. In 0.2.0 (**ColumnarMerge
S11**) an insert wrote its table's aggregate and latest / first-per-key queries inside its own commit, before the
`200`. See [Materialized queries](../guides/materialized.md#27-core-concepts-and-mental-model).

**Identity-insert (`identityInsert: true`):**

```json
{
  "database": "mydb",
  "table": "orders",
  "identityInsert": true,
  "columns": ["id", "status"],
  "data": [[1000, 0], ["seeded", "zero-is-literal"]]
}
```

- Stores client-supplied autoIncrement values as-is (including literal `0` — does **not** mean “please generate”).
- Requires every autoIncrement column on every row; missing, absent or `null` → `400` / clear error; no partial insert.
- After success, the next normal insert with `id: 0` receives `max(inserted) + 1`. Omitting the column is still `400` (BL-429).
- Does **not** flip catalog `autoIncrement` (use schema apply / Studio Toggle AutoId for that — BL-126).
- For large seed/reseed jobs, prefer bulk-load `options.identityInsert` (see [Bulk Load API](#bulk-load-api)).

**The column-batch frame body** (**BL-695 / ColumnarCore S06, 0.2.0**):

The same endpoint also accepts **one column-batch frame** — `Content-Type: application/vnd.aouda.column-batch-v2` (`ACB2`,
**Lead S09, 0.6.0**: one data frame, then the body's end frame), the binary layout bulk-load
[`:append`](#the-column-batch-frame-acb2) takes. An `ACB1` body or the retired `application/vnd.aouda.column-batch` type is
`415 FRAME_VERSION_UNSUPPORTED`, and nothing is inserted. The rows
insert exactly as the same rows sent as JSON would: the same values, defaults, generated ids, errors and messages. A
frame carries values, not JSON text, so where the text matters the server reads the frame's rows as JSON: a number sent
into a `String` column is stored as its JSON text (`2.50`, not a culture's `2,50`), whatever the server's culture.
(**LoadSpeed S13, 0.4.0**) A frame's decimal column has one scale, its largest, so such a number is stored at that
scale: `3` sent beside `2.50` is stored as `3.00`. A client
that writes its own frames should send a number whose JSON text uses an exponent (`1E+17`) as JSON instead: the frame
cannot say which text it had.

- A frame has no envelope: the **database and table are the URL's**, and `identityInsert` / `writeConcern` are query
  parameters — `POST /api/databases/mydb/tables/orders/rows?identityInsert=true&writeConcern=majority`. (On a JSON body
  those query parameters are ignored; the body's own fields apply.)
- **One data frame per request.** A body holding two is `400 INVALID_REQUEST`; so is a body that is not a valid `ACB2` body
  (no end frame, a frame out of sequence, an end frame that counts other rows).
- The response is the JSON above.

**How a client knows.** Every response the endpoint itself returns — success or error — carries
`Accept-Post: application/json, application/vnd.aouda.column-batch-v2` (a request refused before it, by authentication or an
unsupported `Content-Type`, gets none; browsers can read the header through CORS), and `GET /admin/capabilities` lists
`insertColumnBatch: true`. A server that predates this does not send the header, and answers a frame with
`415 Unsupported Media Type`. The official SDKs send JSON until they have seen the header (see [.NET](../clients/dotnet.md)
and [TypeScript](../clients/typescript.md)). `@aouda/client` goes back to JSON on a `415` and stays on JSON for **five
minutes**, whatever a later response advertises (**BL-716, 0.2.0**). (**BL-980, 0.4.0**) `Aouda.Client` no longer
does: a `415` on a frame is an error like any other — the fallback existed only for an older server behind the same address,
and pre-1.0 the client and server are upgraded together. The advertisement itself is unchanged.

**JSON is read into columns too.** A JSON body is not deserialized into one dictionary per row: the server reads each
array of `data` straight into the table's typed columns (**Lead S12, 0.6.0**: the arrays are the body's own, where it located
`rows` before), with the same conversions as before (a number in a `String` column is stored as its JSON text; `"12"` in an integer
column is parsed). It accepts `application/json`, `text/json` and `application/*+json`, with or without a UTF-8
byte-order mark. Two visible differences: a body that is not valid JSON is now a `ProtocolError` `400 INVALID_REQUEST`,
like every other error of this endpoint, and an empty body is `400 MISSING_DATABASE`.

**`WriteConcernStatus` object:**

| Field | Type | Description |
|-------|------|-------------|
| `requested` | string | The write concern level that was requested. |
| `achieved` | string | The write concern level that was actually achieved. |
| `acksReceived` | number | Number of secondary ACKs received. |
| `acksRequired` | number | Number of secondary ACKs required. |
| `wasDegraded` | boolean | Whether the write was degraded due to timeout. |

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `ROW_OBJECTS_UNSUPPORTED` | 400 | (**Lead S12, 0.6.0**) A JSON body with `rows` (row objects). Send [column arrays](#column-arrays-the-write-body). Nothing is inserted |
| `INVALID_REQUEST` | 400 | Missing `columns` / `data`, column arrays that do not match (see [column arrays](#column-arrays-the-write-body)), invalid column name, schema mismatch, `identityInsert: true` with a missing, absent or `null` autoIncrement column, a body that is not valid JSON, a frame body that is not one valid column-batch frame, a frame `Double` cell that is NaN or ±Infinity (**BL-716, 0.2.0** — JSON cannot carry them either), a string cell that is not valid UTF-8 (**BL-716, 0.2.0**), or a frame column of the retired 128-bit `Decimal` kind 6 (**LoadSpeed S13, 0.4.0**; see [the frame](#post-jobidappend)) |
| — | 415 | A `Content-Type` other than `application/json`, `text/json`, `application/*+json` or `application/vnd.aouda.column-batch-v2` |
| `FRAME_VERSION_UNSUPPORTED` | 415 | (**Lead S09, 0.6.0**) An `ACB1` frame body, or the retired `application/vnd.aouda.column-batch` type. The message names the version found and the one expected. Nothing is inserted |
| `INVALID_VALUE` | 400 | Value type does not match column type |

#### `PATCH /api/databases/{db}/tables/{name}/rows`

Update rows matching a WHERE filter.

**Request Body:**

```json
{
  "database": "mydb",
  "where": {
    "and": [
      { "column": "status", "op": "eq", "value": "pending" },
      { "column": "price", "op": "gt", "value": 100 }
    ]
  },
  "set": {
    "status": "shipped",
    "updated_at": "2026-02-06T12:00:00Z"
  },
  "writeConcern": "majority"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `where` | object | Yes | WHERE clause with at least one predicate. Uses same format as query endpoint. Server returns 400 if missing or empty. |
| `set` | object | Yes | Column values to update. Keys are column names, values are new values. Server returns 400 if missing or empty. Server validates column names exist in schema. |
| `writeConcern` | string? | No | Write-concern override. Allowed: `"one"`, `"majority"`, `"all"`. Null/omitted = use table/database default. |

**Response:** `200 OK`

```json
{
  "rowsUpdated": 3,
  "executionMs": 12,
  "writeConcernStatus": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsUpdated` | number | Number of rows affected by the update |
| `executionMs` | number | Server-side execution time in milliseconds |
| `writeConcernStatus` | object? | Write-concern acknowledgement details. Null when `writeConcern` is `"one"`. Same structure as in insert response. |

**Note:** `where` is the compare. Returns `rowsUpdated: 0` with 200 status when the predicates match no rows, on the first scan or on the scan the update runs again after another writer changed a matched row (**BL-1120, 0.6.0**). That 0 is not an error: this call leaves the row unchanged. A predicate that matches N rows updates those N rows in the one transaction and returns N.

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `INVALID_REQUEST` | 400 | Missing/empty WHERE, missing/empty SET, or invalid column name in SET |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The rows the WHERE matches do not fit the read budget, as the same `SELECT` would not (**BL-817, 0.3.0**). Nothing is changed; `Retry-After` is set. Narrow the predicate and mutate in pieces. |
| `WRITE_CONFLICT` | 409 | (**BL-881, 0.3.0**) Other writers kept changing the matched rows through all 16 attempts, and every attempt's scan still matched `where` (**BL-1120, 0.6.0** — a compare that has stopped matching is 200 with `rowsUpdated: 0`, not 409). Each attempt re-checks its matches at commit and rescans if one changed; (**BL-920, 0.4.0**) with a short pause between attempts — 1 ms doubling to 64 ms, jittered, under a second in all — so a large DELETE under a stream of writes no longer spends them in a burst. Nothing is changed; retry with backoff. See [`WRITE_CONFLICT`](#named-query-streaming-and-data-plane-errors). |

#### `DELETE /api/databases/{db}/tables/{name}/rows`

Delete rows matching a WHERE filter.

**Request Body (JSON body on DELETE):**

```json
{
  "database": "mydb",
  "where": {
    "and": [
      { "column": "status", "op": "eq", "value": "cancelled" },
      { "column": "created_at", "op": "lt", "value": "2025-01-01" }
    ]
  },
  "writeConcern": "majority"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `where` | object | Yes | WHERE clause with at least one predicate. Uses same format as query endpoint. Server returns 400 if missing or empty. |
| `writeConcern` | string? | No | Write-concern override. Allowed: `"one"`, `"majority"`, `"all"`. Null/omitted = use table/database default. |

**Response:** `200 OK`

```json
{
  "rowsDeleted": 5,
  "executionMs": 8,
  "writeConcernStatus": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsDeleted` | number | Number of rows deleted |
| `executionMs` | number | Server-side execution time in milliseconds |
| `writeConcernStatus` | object? | Write-concern acknowledgement details. Null when `writeConcern` is `"one"`. Same structure as in insert response. |

**Note:** Returns `rowsDeleted: 0` with 200 status when WHERE predicates match no rows. This is not an error.

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `INVALID_REQUEST` | 400 | Missing or empty WHERE clause |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The rows the WHERE matches do not fit the read budget, as the same `SELECT` would not (**BL-817, 0.3.0**). Nothing is changed; `Retry-After` is set. Narrow the predicate and mutate in pieces. |
| `WRITE_CONFLICT` | 409 | (**BL-881, 0.3.0**) Other writers kept changing the matched rows through all 16 attempts. Nothing is deleted; retry with backoff. |

**Concurrent writers (**BL-881, 0.3.0**).** A DELETE or UPDATE that overlaps another write to the same rows commits as if the
two ran one after the other: at its commit it re-checks every row it matched and, if one was deleted or rewritten meanwhile, runs
again from its scan. One answer changes with it: a DELETE whose `WHERE` a concurrent upsert moved a row out of (`WHERE k = 'a'`, the
upsert set `k = 'b'`) now **leaves that row**, where it used to delete it.

**Deleting everything before a time (**Horizon, 0.5.0**).** A `DELETE` whose whole `where` is one condition, `lt` or `lte`,
on the table's first cluster column (a `Timestamp` or `Date`) — with no `limit`, `orderBy` or `returning`, on a tabular table (an
edge table takes the row path) with no vector column that no foreign key references — does not delete row by row:

```json
{
  "database": "market",
  "where": { "and": [ { "column": "Ts", "op": "lt", "value": "2026-07-01T00:00:00Z" } ] }
}
```

- On a table **with retention** it is an *early expiry*: the table's horizon rises to the cutoff and the segments wholly below it are
  retired; one catalog record (`AdvanceTableHorizon`: the table and the cutoff, a few dozen bytes) is logged for replicas and
  point-in-time restore, no data byte is written, and a later write below the cutoff is counted as `expiredRows`. A cutoff past the
  server's clock takes the row path. While a rebuild of a materialized query over the table holds its horizon, the statement waits,
  and answers `409 WRITE_CONFLICT` after 30 s (BL-1072); retry it.
- On **any other table** it is a delete of the rows that exist when it runs: one log record, the segments wholly below the cutoff
  retired whole, mask bits for the matching rows of the segments that straddle it, the table's materialized queries rebuilt. It
  installs no horizon — a row written later with an older time is visible. A null time is not deleted.

For `lte` the cutoff is the successor of `value` (one tick for a `Timestamp`, one day for a `Date`). `rowsDeleted` is exact. Any other
shape — a second condition, a `limit` — runs as before. Subscribers receive one `horizon` or `range_delete` message, not a `change`
per row (see [`horizon`](#horizon) and [`range_delete`](#range_delete)). See [Retention](../guides/retention.md#deleting-everything-before-a-time).

#### `PATCH /api/databases/{db}/tables/{name}/rows` — Extended fields (P27)

The following optional fields extend the standard update request:

| Field | Type | Description |
|-------|------|-------------|
| `setExpr` | `object?` | Expression-based SET values. Keys are column names; values are expression nodes. Evaluated server-side per row. Can be combined with `set` — literal `set` wins on collision. |
| `returning` | `string[]?` | List of column names (or `["*"]` for all) to return after update. Returns post-update values in columnar format under `rows`. |

**Expression node format** — each value in `setExpr` is an expression node:

```json
{ "type": "arithmetic", "op": "+|-|*|/", "left": <node>, "right": <node> }
{ "type": "colRef", "col": "columnName" }
{ "type": "literal", "value": <any> }
{ "type": "coalesce", "args": [<node>, ...] }
{ "type": "conditional", "when": <predicate>, "then": <node>, "else": <node> }
```

**Extended response when `returning` is set:**

```json
{
  "rowsUpdated": 3,
  "executionMs": 9,
  "rows": {
    "columns": ["id", "status"],
    "types":   ["Int64", "String"],
    "data":    [[1, 2, 3], ["shipped", "shipped", "shipped"]],
    "rowCount": 3
  }
}
```

**Additional errors for extended fields:**

| Code | Status | When |
|------|--------|------|
| `COLUMN_NOT_FOUND` | 400 | A `colRef` column name in `setExpr` does not exist in the table schema |

---

#### `DELETE /api/databases/{db}/tables/{name}/rows` — Extended fields (P27)

The following optional fields extend the standard delete request:

| Field | Type | Description |
|-------|------|-------------|
| `limit` | `number?` | Maximum number of rows to delete. When set, engine selects the bounded row set first. |
| `orderBy` | `object[]?` | Same format as query `orderBy`. Controls which rows are selected for deletion when `limit` is set. Omitting `orderBy` with a `limit` selects an arbitrary subset and emits a warning. |
| `returning` | `string[]?` | List of column names (or `["*"]` for all) to return. Returns **pre-delete** values in columnar format under `rows`. |

**Extended request with limit, orderBy, and returning:**

```json
{
  "database": "appdb",
  "where": {
    "and": [{ "column": "createdAt", "op": "lt", "value": "2026-01-01T00:00:00Z" }]
  },
  "orderBy": [{ "column": "createdAt", "descending": false }],
  "limit": 1000,
  "returning": ["id", "userId"]
}
```

**Extended response:**

```json
{
  "rowsDeleted": 1000,
  "hasMore": true,
  "executionMs": 18,
  "rows": {
    "columns": ["id", "userId"],
    "types":   ["Int64", "String"],
    "data":    [[...], [...]],
    "rowCount": 1000
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsDeleted` | number | Number of rows deleted in this call |
| `hasMore` | boolean | `true` when `limit` was set and more matching rows remain |
| `executionMs` | number | Server-side execution time |
| `rows` | columnar? | Pre-delete values when `returning` was specified; null otherwise |

---

#### `POST /api/databases/{db}/tables/{name}/truncate`

Truncate (clear) all rows from a table. Schema is preserved. Requires the `Truncate`
authorization scope — `db_writer` alone is insufficient.

**Request Body:**

```json
{
  "database": "appdb",
  "writeConcern": "majority"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `writeConcern` | string? | No | Write-concern override. Null/omitted = use default. |

**Response:** `200 OK`

```json
{
  "rowsDeleted": 15000,
  "executionMs": 3
}
```

(**Horizon, 0.5.0**) A truncate retires the table's segments instead of writing a deletion mask over every row, so the disk
is freed at once; it is still one log record and atomic for readers. Subscribers are sent nothing — no `change` and no notice.

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `AUTHORIZATION_DENIED` | 403 | Caller lacks the `Truncate` authorization scope |

---

#### `POST /api/databases/{db}/tables/{name}/rows/batch`

Execute multiple update and/or delete operations against the same table in a single request.
All operations are applied sequentially in the order given. ⚠️ **A batch is not one transaction: each operation commits on its
own** (**BL-843**). When an operation fails, the operations before it have been applied and stay applied, so a retry of the
whole batch applies them again. Make operations that a retry may repeat idempotent (literal `set`, not `setExpr` arithmetic), or
retry from the failed operation. What each answer means for what was applied:

- **`400 INVALID_REQUEST` for the request's shape** (see Errors below) **and `403`** (RLS / PLS): nothing was applied — every
  operation is translated and checked against the caller's row and partition rules before the first one runs.
- **`503 MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`**, with `Retry-After`: the **first** operation was refused for capacity
  and nothing was applied. Retry the whole batch after `Retry-After` (**0.3.0**).
- **`503 BATCH_PARTIALLY_APPLIED`**, no `Retry-After`: operation `k` ≥ 1 was refused for capacity. Operations `0` to `k − 1` were
  applied, operation `k` and the later ones were not; `details` names `appliedOperations=k` and `totalOperations=n`. Re-send only
  `operations[k..]` (**Lead group 3 review, 0.6.0**; it was the plain capacity refusal, which re-sent the whole batch).
- **`409 WRITE_CONFLICT`** (**BL-881, 0.3.0**) and **`409 DUPLICATE_PRIMARY_KEY`**: the refused operation applied nothing, the
  operations before it stand and the ones after it did not run. The answer does not name the refused operation: read the data
  before retrying anything but idempotent operations.
- **`500 WRITE_APPLIED_RESPONSE_FAILED`**: every operation was applied and the server failed while answering. Do not re-send the
  batch (**Lead group 3 review, 0.6.0**). A `504 WRITE_CONCERN_TIMEOUT` likewise comes after every operation was applied.

**Request Body:**

```json
{
  "database": "appdb",
  "operations": [
    {
      "where": { "and": [{ "column": "status", "op": "eq", "value": "pending" }] },
      "set":   { "status": "processing" }
    },
    {
      "where": { "and": [{ "column": "status", "op": "eq", "value": "cancelled" }] },
      "delete": true
    },
    {
      "where": { "and": [{ "column": "attempts", "op": "gte", "value": 5 }] },
      "setExpr": {
        "attempts": { "type": "arithmetic", "op": "+", "left": { "type": "colRef", "col": "attempts" }, "right": { "type": "literal", "value": 1 } }
      }
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `operations` | object[] | Yes | Ordered list of mutation operations |
| `operations[].where` | object | Yes | WHERE clause for this operation |
| `operations[].set` | object? | No | Literal SET values (UPDATE operation) |
| `operations[].setExpr` | object? | No | Expression SET values (UPDATE operation) |
| `operations[].delete` | bool? | No | `true` for a DELETE operation |

Each operation must specify either (`set` or `setExpr`) or `delete: true`, not both.

**Response:** `200 OK`

```json
{
  "operationResults": [
    { "rowsAffected": 12 },
    { "rowsAffected": 3 },
    { "rowsAffected": 2 }
  ],
  "executionMs": 18
}
```

**Errors:**

| Code | Status | When |
|------|--------|------|
| `INVALID_REQUEST` | 400 | Empty operations list, or an operation missing both `set`/`setExpr` and `delete`, or missing WHERE |
| `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` | 503 | The first operation was refused for capacity; nothing was applied. `Retry-After` is set |
| `BATCH_PARTIALLY_APPLIED` | 503 | (**Lead group 3 review, 0.6.0**) Operation `k` ≥ 1 was refused for capacity; operations before it were applied. No `Retry-After`; re-send only the remaining operations. See [above](#post-apidatabasesdbtablesnamerowsbatch) |
| `WRITE_CONFLICT` | 409 | (**BL-881, 0.3.0**) One operation's matched rows kept changing; it and the later ones were not applied, the earlier ones were |
| `WRITE_APPLIED_RESPONSE_FAILED` | 500 | (**Lead group 3 review, 0.6.0**) The batch was applied; the answer failed. Do not re-send |

---

#### `POST /api/databases/{db}/query` — `selectExpr` extension (P27 S7)

The query endpoint accepts an optional `selectExpr` field alongside (or instead of) the
standard `select` field. Computed columns are evaluated server-side and appended to the
result — they are never stored.

| Field | Type | Description |
|-------|------|-------------|
| `selectExpr` | `ComputedColumnDef[]?` | List of computed column definitions. Each entry has `alias` (string) and `expr` (expression node). Max 20 entries. |

**`ComputedColumnDef` format:**

```json
{
  "alias": "discountedPrice",
  "expr": {
    "type": "arithmetic",
    "op": "*",
    "left":  { "type": "colRef", "col": "price" },
    "right": { "type": "literal", "value": 0.9 }
  }
}
```

**Extended query request:**

```json
{
  "database": "shop",
  "table":    "products",
  "select":   ["id", "name", "price"],
  "selectExpr": [
    {
      "alias": "discountedPrice",
      "expr": { "type": "arithmetic", "op": "*", "left": { "type": "colRef", "col": "price" }, "right": { "type": "literal", "value": 0.9 } }
    }
  ],
  "limit": 100
}
```

A `colRef` names its column exactly as the table does — case-sensitively, as `where` and `select` do. A mis-cased name is
`400 COLUMN_NOT_FOUND`; before, it read the column through the default (columnar) answer and `null` through `format=rows`
(**BL-799, 0.3.0**).

**Response** — computed columns appear at the end of `columns` and `types`:

```json
{
  "columns": ["id", "name", "price", "discountedPrice"],
  "types":   ["Int64", "String", "Decimal", "Decimal"],
  "data":    [[1], ["Widget"], [99.00], [89.100]],
  "rowCount": 1,
  "stats": { "executionMs": 4 }
}
```

With `price` a `Decimal(18,2)` column, `price * 0.9` is exact at scale 3, the sum of the two scales (**LoadSpeed S13, next
train**: a fractional JSON literal is a decimal at the scale it is written with, and a decimal expression is exact).

Computed column types are inferred where the expression permits (`"Unknown"` otherwise) and are always nullable. See [browser-tier read limits](../guides/browser-tier-read-limits.md#selectexpr-result-types).

**Errors for `selectExpr`:**

| Code | Status | When |
|------|--------|------|
| `COLUMN_NOT_FOUND` | 400 | A `colRef` column does not exist in the table schema |
| `INVALID_REQUEST` | 400 | Empty or null alias, alias collides with a physical column in `select`, duplicate alias, or more than 20 entries |

---

**Common Notes for All Mutation Endpoints:**

- All mutation endpoints require write permissions (`[RequireWritePermission]` on the server). Requests to non-primary replicas return `WRITE_NOT_ALLOWED` (403) or `NOT_PRIMARY` (421).
- All mutation endpoints use `encodeURIComponent()` for the table name in the URL path.
- Standard error codes (`INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`, etc.) apply as described in the Error Codes section above.
- For the full user guide with SDK examples and patterns, see [guides/bulk-mutations.md](../guides/bulk-mutations.md).

---

### Graph and vector endpoints

(**Pass-10**: these routes have existed since the graph and vector stage; this reference did not list them.) Edge tables and
vector columns are created, written and queried over REST under `/api/databases/{db}`. All bodies and answers are JSON. They are
admin-listener routes: on the data-plane listener they are `404`. Writes need write permission on the database; the four reads need
read permission and honour the [freshness parameters](#consistency-tokens-and-freshness) (`at_least`, `waitMs`, `onExceeded`, the
lag budgets) as `POST …/query` does. A caller's PLS / RLS applies to the reads ([graph and vector guide](../guides/graph-vector.md#276-adra-authorization-composes-with-graphvector-queries)).
Neither SDK wraps them yet.

| Method | Path | Body | Answer |
|---|---|---|---|
| `POST` | `/api/databases/{db}/edge-tables` | `{ name, srcColumn, dstColumn, edgeLabel?, storeCsc?, authMode?, permissionDimension?, srcIsPartitionKey?, rlsResolverName?, rlsColumn? }` | `201` `{ "name" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges` | `{ srcs, dsts, edgeLabels? }` | `200` `{ "edgesInserted", "token" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges:traverse` | `{ startNodeId, hops? }` | `200` `{ "neighborIds", "executionMs" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges:khop` | `{ startNodeId, k }` | `200` `{ "nodeIds", "hops", "executionMs" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges:shortest-path` | `{ a, b }` | `200` `{ "path", "executionMs" }` |
| `POST` | `/api/databases/{db}/tables/{name}:create-vector-column` | `{ columnName, dimensions, distance?, quantization?, ivfCells?, embeddingModel?, authMode?, permissionDimension?, permissionColumn?, rlsResolverName?, rlsColumn? }` | `201` `{ "columnName" }` |
| `POST` | `/api/databases/{db}/tables/{name}/vectors/{column}` | `{ rowKeys, vectorData, embeddingModelVersion?, partitionKey? }` | `200` `{ "rowsInserted", "token" }` |
| `POST` | `/api/databases/{db}/tables/{name}/vectors/{column}:nearest` | `{ queryEmbedding, k }` | `200` `{ "rowKeys", "distances", "executionMs", "token" }` |

#### `POST /api/databases/{db}/edge-tables`

Create an edge table: two `Int64` columns, the source and the destination node ids.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | The edge table's name. |
| `srcColumn` / `dstColumn` | string | Yes | The source and destination columns' names. |
| `edgeLabel` | string? | No | A label for the table's edges. |
| `storeCsc` | bool | No | Also keep the reverse (destination → source) index, which lets a shortest path search from both ends. Default `false`. |
| `authMode` | string? | No | `jwt-claim` (default), `auth-db-pls` or `auth-db-rls`. |
| `permissionDimension` | string? | With `auth-db-pls` | The grant dimension the caller's grants are matched on. An edge traversal is scoped by the grant set — at least one grant in the dimension — and takes no `permissionColumn`. |
| `srcIsPartitionKey` | bool | No | Make the source column the partition key. |
| `rlsResolverName` | string? | With `auth-db-rls` | The RLS resolver. |
| `rlsColumn` | string? | No | Adds a `String` column for grant-sourced RLS (for example `org`). |

`400 INVALID_REQUEST` for a missing field or an unknown `authMode`; `409 TABLE_EXISTS` when the name is taken.

```json
{ "name": "follows", "srcColumn": "src_id", "dstColumn": "dst_id", "edgeLabel": "follows", "storeCsc": true }
```

#### `POST /api/databases/{db}/tables/{name}/edges`

Insert edges: `srcs[i]` → `dsts[i]`. The two arrays must be non-empty and the same length (`400 INVALID_REQUEST` otherwise);
`edgeLabels`, when given, holds one label per edge. The answer carries the write's consistency `token`.

```json
{ "srcs": [1, 1, 2], "dsts": [2, 3, 3] }
```

```json
{ "edgesInserted": 3, "token": "…" }
```

#### `POST /api/databases/{db}/tables/{name}/edges:traverse`

Breadth-first traversal: every node reachable from `startNodeId` within `hops` hops (default `1`), each once, the start node not
included.

```json
{ "startNodeId": 1, "hops": 2 }
```

```json
{ "neighborIds": [2, 3], "executionMs": 1 }
```

#### `POST /api/databases/{db}/tables/{name}/edges:khop`

The k-hop neighbourhood: every node reachable from `startNodeId` within `k` hops (`k` > 0), with its smallest hop distance
(from 1; the start node not included), ordered by distance and then node id. The answer is column arrays: `nodeIds[i]` is at
`hops[i]` hops (**Lead S12, 0.6.0; breaking**: it was `"nodes": [{"nodeId", "hops"}]`, one object per node).

```json
{ "startNodeId": 1, "k": 2 }
```

```json
{ "nodeIds": [2, 3, 4], "hops": [1, 1, 2], "executionMs": 1 }
```

#### `POST /api/databases/{db}/tables/{name}/edges:shortest-path`

The shortest path from node `a` to node `b`: the node ids along it, both ends included, or `[]` when there is none. A table
created with `storeCsc: true` is searched from both ends.

```json
{ "a": 1, "b": 4 }
```

```json
{ "path": [1, 3, 4], "executionMs": 1 }
```

#### `POST /api/databases/{db}/tables/{name}:create-vector-column`

Create the table `{name}` with an `Int64` primary key `RowKey` and one vector column.

| Field | Type | Required | Description |
|---|---|---|---|
| `columnName` | string | Yes | The vector column's name. |
| `dimensions` | number | Yes | The vectors' length, > 0. |
| `distance` | string | No | `L2` (default), `Cosine` or `DotProduct`. |
| `quantization` | string | No | `None` (default), `RaBitQ`, `PQ` or `SQ`. |
| `ivfCells` | number | No | IVF cells per sealed segment. Default `1`. |
| `embeddingModel` | string? | No | The embedding model's name. |
| `authMode`, `permissionDimension`, `rlsResolverName`, `rlsColumn` | | No | As for an edge table. |
| `permissionColumn` | string? | With `auth-db-pls` | (**BL-1176, 0.7.0**) The column the grant keys are compared with — in practice the `rlsColumn`. The vector table is an ordinary table for its reads, so it declares the column like any `auth-db-pls` table. Sent with no `authMode` or with `jwt-claim` it is `400`, not ignored. |

`400 INVALID_REQUEST` for a missing name, `dimensions` ≤ 0, or an unknown `distance`, `quantization` or `authMode`;
`409 TABLE_EXISTS` when the table exists.

#### `POST /api/databases/{db}/tables/{name}/vectors/{column}`

Insert vectors for row keys. `vectorData` is **row-major**: the vectors one after another, `rowKeys.length × dimensions` numbers.
`embeddingModelVersion` records which model made them; `partitionKey` places them in a partition of a PLS table (the default
partition when omitted or null; an empty string names a partition of its own, **BL-1184, next train**). Empty `rowKeys` or `vectorData`, or a length that does not fit the column, is `400 INVALID_REQUEST`.

```json
{ "rowKeys": [1, 2], "vectorData": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "embeddingModelVersion": "v1" }
```

```json
{ "rowsInserted": 2, "token": "…" }
```

#### `POST /api/databases/{db}/tables/{name}/vectors/{column}:nearest`

Approximate nearest neighbours of `queryEmbedding` (its length is the column's `dimensions`): up to `k` (> 0) hits, nearest first.
The answer is column arrays: `rowKeys[i]` is at `distances[i]` (**Lead S12, 0.6.0; breaking**: it was
`"results": [{"rowKey", "distance"}]`, one object per hit). `token` is the cut the search read.

```json
{ "queryEmbedding": [0.1, 0.2, 0.3], "k": 2 }
```

```json
{ "rowKeys": [1, 2], "distances": [0.0, 0.52], "executionMs": 2, "token": "…" }
```

**Errors:** on the routes under `tables/{name}`, `404 TABLE_NOT_FOUND` for an unknown table or column and `400 INVALID_REQUEST` for
an operation the table does not support (for example a traversal of a table that is not an edge table); on every route, the
capacity refusals every endpoint answers (`503` + `Retry-After`).

---

### Health Endpoints

#### `GET /`

Service information.

**Response:**

```json
{
  "service": "Aouda Server",
  "version": "0.1.0",
  "status": "running",
  "tables": 5
}
```

#### `GET /health`

Liveness probe. **Always 200** if the process is running. Fast. Use as a Kubernetes `livenessProbe`.

This is **not** “ready for schema apply or traffic”. A database can be `Dropping` or `Creating` while `/health` returns 200.

**Response:**

```json
{
  "status": "healthy"
}
```

#### `GET /ready`

Readiness probe. 200 when `DatabaseManager` is initialized and **critical** components (catalog, WAL) are healthy. 503 otherwise (body includes `ready: false` and `reason`).

`/ready` does **not** fail because an operator database is `Creating` or `Dropping` — that would take the whole node out of a load balancer for a long drop. Per-database readiness is `GET /api/databases/{name}` (`state=Active`) and `/health/detailed`.

The `memory` component is critical too. Either of these makes `/ready` return 503: the managed heap at 75 % or more of its
limit, or a database holding more than 110 % of what it was granted. A database's grant is its **governed ceiling** — the
process's budget, or its hard cap where it has one — not its nominal share, so using room it was given never fails readiness
(**BL-788, 0.3.0**; WorkloadCore S06 deleted elastic lending and the "tightened" verdict). Before that, a database inside
its ceiling could hold `/ready` at 503 for as long as it used it. The `reason` names the database, its usage and its grant, and the `memory` component's details carry them as
`overBudgetDatabase`, `overBudgetUsedBytes` and `overBudgetGrantBytes`.

Use as a Kubernetes `readinessProbe`.

#### `GET /startup`

Startup probe. 200 when bootstrap is complete (`DatabaseManager` initialized). 503 while still starting. Use as a Kubernetes `startupProbe`; once it returns 200, switch to liveness + readiness.

#### `GET /health/detailed`

Component-by-component status (catalog, WAL, replication, backup, materialized queries, memory, per-database `state`). HTTP 200 for healthy/degraded, 503 for unhealthy (critical failure). Degraded responses include `X-Health-Status: degraded`. Admin listener only (404 on the data-plane).

The `memory` component's `hotBytesLimit` and `cacheBytesLimit` are the engine's own hot ceiling (`T10`, 0.45 × governed) and page-cache ceiling (`T12`, 0.10 × governed) (**WorkloadCore, 0.3.0** — they were 0.7× and 0.2× of `MaxTotalRamBytes` when unset, so the check could say healthy while hot admission refused). A full hot tier and a full page cache have no verdict (**WorkloadCore S03, 0.3.0**): a hot tier at its ceiling is back-pressure, not a threat to the process, and `hotPercent` reports how full it is. The `memory` component is critical, so `/ready` fails whenever it is **degraded or unhealthy**: the managed heap at 75 % of the GC limit or more, or a database holding more than 110 % of its ceiling. (**WorkloadCore S06, 0.3.0**: the budget is never tightened in-process any more, so there is no "tightening" verdict; a database's ceiling is the server's budget unless it has a hard cap.)

**Operator wait (create / schema apply):** wait for `GET /ready` 200 **and** `GET /api/databases/{name}` 200 with `state=Active`. After `DELETE`, GET `{name}` 404 means the database is gone from serving.

#### `GET /api/server/memory`

Server-wide memory usage with a per-database breakdown. Lightweight and safe to poll from a dashboard. Server-admin only, like the rest of `/api/server/*`.

The response is large and has grown with every memory-related release; this section documents the **hot-tier fields** added in P53. For what the rest of the fields mean and what to do about them, see [Sizing](../guides/sizing.md). All P53 fields are **additive**: no existing field changed meaning, and reading them changes no behaviour.

**Top level** (the process as a whole):

| Field | Type | Meaning |
|---|---|---|
| `hotArrivalBytesPerSecond` | number | Resident hot bytes **created** per second, summed across every database — flushes, promotions, segment loads. |
| `hotDrainBytesPerSecond` | number | Resident hot bytes **released** per second by hot→cold demotion, across every database. |
| `hotDrainStalled` | boolean | `true` when any database's drain **tried and failed** in the last sampling interval. |
| `processHotCeilingBytes` | integer | The hot ceiling across every open database. **Not** the sum of the per-database ceilings: each database's ceiling has a 32 MB floor, so that sum grows with the database count and can exceed what the runtime will commit. |
| `processHotResidentBytes` | integer | Resident hot bytes across every open database — the figure `processHotCeilingBytes` bounds. |
| `heapSustainedDegradation` | boolean | `true` when a **majority of a sliding window** of samples was above 90 % of the heap limit. |
| `heapDegradedSinceUtc` | string? | When that began (ISO 8601), or `null` while healthy. |
| `heapDegradedForSeconds` | number? | How long it has been true. **The field to alert on.** |

⚠️ **The three heap-degradation fields report; they never act.** Nothing here refuses, delays or
reroutes a write, and the termination watchdog's own rule (six consecutive samples above 98 % of the
heap limit) is untouched.

⚠️ **They exist because every other memory figure on this response is instantaneous.** An
instantaneous reading cannot distinguish a spike the next collection resolves from a process that has
been unable to make room for an hour — which is the state an observed incident sat in while
oscillating 91.5 → 98.8 → 91.6 %, resetting the consecutive counter every time. A window majority is
used precisely because oscillation is a *symptom* of the condition rather than evidence against it.

🔎 `heapSustainedDegradation` and `heapDegradedForSeconds` also appear in the `memory` health
component's `details`, so an orchestrator can key on them without polling this route.

**Per database** (each entry of `perDatabaseUsage`):

| Field | Type | Meaning |
|---|---|---|
| `hotArrivalBytesPerSecond` | number | Resident hot bytes created per second (exponentially weighted, 30-second half-life). |
| `hotDrainBytesPerSecond` | number | Resident hot bytes released per second by demotion (same weighting). |
| `hotDrainLatencyP50Ms` / `hotDrainLatencyP90Ms` | number | Median / 90th-percentile wall time of a demotion, in milliseconds. |
| `hotDrainAttempted` | integer | Demotions that spent real work. Excludes pinned, already-cold and merged-away segments. |
| `hotDrainSucceeded` | integer | Of those, the ones that released their segment. |
| `hotDrainStalled` | boolean | This database's drain tried and failed across the last sampling interval. |
| `totalHotBytesAdmitted` / `totalHotBytesDrained` | integer | The monotonic totals (since process start) behind the two rates. |
| `processHotCeilingShareBytes` | integer | This database's slice of `processHotCeilingBytes`. The ceiling it is actually bound by is the lower of its own derived ceiling and this — read both when a write is refused while this database's own share still had room. |
| `pinnedHotBytes` | integer | Bytes held by this database's declared residency pins (`residency` on a `HotOnly` table). **Subtracted** from the ceiling the elastic hot tier is admitted against: a pin shrinks the tier, and this is by how much. |

⚠️ **`hotDrainBytesPerSecond == 0` is not a problem on its own.** A server with nothing to demote drains nothing, which is the healthy resting state. The condition worth alerting on is `hotDrainStalled`: demotions were attempted across the interval and none released a segment. Sustained `hotArrivalBytesPerSecond` above `hotDrainBytesPerSecond` says the hot tier is being filled faster than it empties, while there is still headroom to act in.


**Provenance: where the budget came from** (**BL-611, 0.1.37**)

An additive block. It changes no threshold, default or byte count — it says where the numbers beside it came from.
(**WorkloadCore S17, 0.3.0**: its companion, the `headroom` block, is removed — below.)

`budgetDerivation` answers *"is this budget a grant or a guess?"*, the way the `cpu` block already
answers it for cores. It is `null` under embedded hosting, where nothing derived one.

| Field | Type | Meaning |
|---|---|---|
| `isDerived` | boolean | `false` when you pinned `Aouda:Memory:MaxTotalRamBytes`. The rest of the block then describes the host, not the decision. |
| `source` | string | `CgroupV2`, `CgroupV1`, `ProcMemInfo`, `WindowsGlobalMemoryStatus`, `GcMemoryInfo` or `Sentinel`. |
| `isCgroupBounded` | boolean | **The field that decides everything else.** A cgroup limit is a *promise*; anything else is an observation about a machine that may have other tenants on it. |
| `detectedTotalBytes` | integer | The cgroup limit, or the machine's physical RAM. |
| `availableBytes` | integer? | What was measurably free. `null` when the probe reports capacity only. |
| `fractionApplied` | number | `0.70` under a cgroup, `0.40` otherwise. |
| `totalAnchorBytes` | integer | `fractionApplied × detectedTotalBytes`, before any clamp. |
| `availabilityHeadroomFraction` | number | `0.70` of what is free — the ceiling on optimism. `0` on the cgroup path, where the clamp is not a term at all. |
| `availabilityBoundBytes` | integer? | What that term came to, or `null` when it did not apply. |
| `availabilityClampBound` | boolean | **The one field to alert on.** `true` means the budget was decided by a *moving measurement* rather than a grant. |
| `derivedBytes` | integer | What the derivation produced, before the floor and ceiling clamp. On the configured path (`isDerived: false`) this is **what you asked for**, before the host clamp — the only place that figure survives. |
| `effectiveBytes` | integer | `MaxTotalRamBytes` as **this decision** left it — the budget at startup. |
| `currentEffectiveBytes` | integer | The budget **in force now** — always equal to `serverMaxBytes`. |
| `isStillInForce` | boolean | `false` when a runtime resize has moved the budget since startup, so the block above no longer describes the budget you are running. |
| `floorBound` / `detectedCeilingBound` | boolean | Whether the 256 MB floor raised it, or the detected total capped it. |
| `settlingEvidence` | string? | How the availability figure was settled across several samples, when settling ran. `null` on a healthy host. |
| `derivedAtUtc` | string | When it was decided — **always startup**. Nothing re-derives it. |
| `explanation` | string | The whole derivation in one sentence, suitable for an alert body. |

⚠️ **`availabilityClampBound: true` is actionable and the remedy is one line.** It means Aouda is
sharing a host nobody promised it a share of, and sized itself from whatever happened to be free at
the instant it started. Set a container memory limit — `docker run -m 2g`, compose
`deploy.resources.limits.memory`, Kubernetes `resources.limits.memory` — and the budget derives from
a guaranteed grant instead. Aouda already logs this once at startup; the block is how you check it
afterwards, on a server whose startup logs have rotated.

⚠️ **A runtime resize does not re-derive the budget, and `isStillInForce` is how you see that.**
Resizing `MaxTotalRamBytes` — through the admin config route, or by restoring persisted settings at
startup — sets the budget directly, because you chose the number and there is nothing to derive from
the host. `budgetDerivation` keeps describing the **startup** decision, `currentEffectiveBytes`
carries the figure actually running, and `explanation` appends a `Superseded:` clause when the two
differ. If you are alerting on `availabilityClampBound`, gate it on `isStillInForce` as well:
a clamp that bound at startup says nothing about a budget you have since set by hand.

**Removed: the resource mode and its headroom** (**WorkloadCore S17, 0.3.0**). `resourceMode`, `headroomRatio`,
`resourceModeTransitions` and the whole `headroom` block (`ratio`, `scope`, `governedBytes`, `workingSetHighWaterBytes`,
`workingSetSource`, `mode`, `transitions` and the four entry / exit ratios) are gone, with the `Constrained` / `Balanced` /
`Abundant` classification they reported: the engine no longer sizes its pools from the process's measured headroom, and
`Abundant` no longer raises them. The transient pool, the per-table flush trigger and the per-table hot budget are one
formula in every deployment — see [Sizing](../guides/sizing.md#the-buffering-thresholds-are-one-formula-in-every-deployment-workloadcore-s17-030).
To see room the ledger does not hold, read `managedHeapBytes`, `ledgerBytes`, `untrackedHeadroomBytes` and `rssBytes`.

#### The ledger: leases and consumer charges (**WorkloadCore, 0.3.0**)

The governor's ledger covers every holder the engine keeps on purpose. Besides the reservations (`reservedBytes`, by category
in `reservedByCategory`), each database charges its caches, registries and queues to it as **consumers**: the page cache, the
bloom store, segment handles, cold segment metadata, catalog shards, flushed hot segments, change rings, materialized-query
update queues, the sparse primary-key index, the L3 key map, graph and vector buffers, and what a table keeps between merges.
Consumer charges are sampled on the governor's reconciliation tick (every 10 s) and on every pass of the memory broker.

Each consumer also reports what it could **release** on request — the page cache, bloom indexes, segment handles, cold segment
metadata, catalog shards and cold sparse-PK entries by dropping them (they are re-read from disk on next use), hot segments by
demoting them — and the broker frees those bytes, cheapest first, when a database's ledger passes its target, when the
process's does, or when the live heap passes 80 % of the GC hard limit. **A reservation is refused when
`reservedBytes + chargedBytes − releasableBytes` would pass the ceiling**: a full cache makes room instead of refusing work; a
full queue, which nothing can release, refuses it. Ordinary work meets the ceiling **less the held reserve** (below)
(**WorkloadCore S06, 0.3.0**: the budget is no longer tightened under host pressure, and `tighteningActive` is removed).

| Field | Where | Type | Meaning |
|---|---|---|---|
| `chargedBytes` | top level, per database | integer | Consumer charges at the last sample — at the top level, every database's. |
| `chargedByConsumer` | top level, per database | object | `chargedBytes` by consumer: `PageCache`, `BloomFilters`, `SegmentHandles`, `ColdMetadata`, `CatalogShards`, `HotSegments`, `ChangeRings`, `MqUpdateQueues`, `SparsePkIndex`, `L3KeyMap`, `GraphVectorBuffers`, `HraScratch`, `BulkLoadQueues` (bulk-load slices queued past a refused reservation), `PasswordHashing` (password hashes running now: Argon2id holds 64 MiB per sign-in or password set while it runs), `UnitWorkingMemory` (a unit of work's own working memory while it runs: a cold segment's keys read back to index it, an update's copy of the table's buffered rows; counted when a reservation is decided since **WorkloadCore S06**) (both **WorkloadCore, 0.3.0**). Zero entries are omitted. |
| `ledgerBytes` | top level, per database | integer | `reservedBytes + chargedBytes`: the whole ledger. |
| `releasableBytes` | top level, per database | integer | What the consumers could release now by dropping cached data or demoting (re-read from disk on next use), at the last sample. Part of `ledgerBytes` (it may cover a loaded hot segment's reservation). |
| `liveHeapAtLastGen2Bytes` | top level | integer | The live heap of the most recent gen-2 collection (below), recorded when it ended (**WorkloadCore, 0.3.0**). `0` before the first. |
| `ledgerAtLastGen2Bytes` | top level | integer | `ledgerBytes` as it stood when that collection ended, consumer charges sampled then. |
| `untrackedAtLastGen2Bytes` | top level | integer | `liveHeapAtLastGen2Bytes − ledgerAtLastGen2Bytes`, never negative: the live heap the ledger did not hold, both read at the same collection. |
| `lastGen2Index` | top level | integer | The collection's index (`runtime.lastGen2.index`), so a reader can keep one row per collection. |

#### Grants, the queue and the held reserve (**WorkloadCore S06, 0.3.0**)

Work asks for memory **before it starts**. A request that does not fit waits in its class's queue — first in, first out
within a class; `Interactive`, `Streaming`, `Ingest`, `Background`, `Maintenance` in that order — and is served the moment
memory frees. A client's insert or upsert is admitted this way **before it takes any lock**: one that does not fit waits up
to one sampling tick (10 s), and is then refused with **503 `MEMORY_BUDGET_EXCEEDED`** and a `Retry-After` the queue
estimates (the bytes ahead of it over the rate the queue has been served at, never less than it already waited) — never a
constant. (**WorkloadCore S17, 0.3.0**) The same holds for every other memory refusal — a read growing past its
budget, a write decided under a lock: its `Retry-After` is the queue's estimate for the refused bytes, or 10 s (the
broker's next look, `T6`) before any service rate has been measured or when the refusal has no estimate. None is a
constant 1 s any more. A write that runs under a lock (an update, a write inside a named-query batch) is decided at once and never waits.

The top `max(32 MB, 3 %)` of each database's and the server's budget (at most an eighth of it) is a **held reserve**: small
(≤ 64 KiB, `Aouda:Memory:SmallRequestBytes`) `Interactive` and `Ingest` writes, and any small request on the auth database,
are admitted from it when everything else is full. Nothing else draws on it, so the write and the token refresh that let a
client recover are admitted while the rest waits.

| Field | Where | Type | Meaning |
|---|---|---|---|
| `grants.waiting` | top level | object | Requests waiting for memory now, per class (non-zero only). |
| `grants.queuedBytes` | top level | object | The minimums they wait for, per class. |
| `grants.served` / `grants.timedOut` / `grants.revoked` | top level | integer | Since start: waiters served from the queue; refused after their wait (each a 503 with the queue's `Retry-After`); grants the memory broker took back because the heap was over its line. |
| `grants.serviceRateBytesPerSecond` | top level | number | The rate the queue has been served at recently — what its `Retry-After` estimates divide by. |
| `reserve.bytes` / `reserve.heldBytes` / `reserve.admissions` | top level | integer | The server's held reserve, what small writes hold from it now, and how many were admitted from it since start. |

**Removed** (**WorkloadCore S06, 0.3.0**): `tighteningActive`, `admissionDenials`, `admissionThrottles`,
`heapPressureDenials`, `ceilingCountedByClass`, and per database `elasticCeilingBytes`. A database's `governedCeilingBytes` is
the server's governed budget unless it has a hard cap (a budget it was registered with, or `MaxMemoryShare`);
`nominalShareBytes` is its weighted share, which is now the memory broker's weight — when the server needs memory back, it
is taken first from the database furthest over its share — and no longer a limit.

Two fields **changed meaning**:

- `managedHeapBytes` is the **live heap after the last gen-2 collection** — what that collection traced live, never more than
  the heap less its free space — the one reading memory decisions take, as of the last reconciliation (every 10 s). It used to
  be the heap after the most recent collection of any kind, which counted every object that died since the last gen-2 as
  live. A **background** gen-2's heap less free space also counts everything allocated while it ran, untraced; the traced
  figure leaves that out (**WorkloadCore, 0.3.0**). For a blocking gen-2 the two are equal.
- `untrackedHeadroomBytes` is `managedHeapBytes − ledgerBytes` (never negative): the live heap the ledger does not account
  for. It used to subtract `reservedBytes` only.

🔎 **The completeness of the ledger** is `untrackedAtLastGen2Bytes / liveHeapAtLastGen2Bytes`, taken at the collections with
the largest live heap. A large share is worth reporting: it is memory held outside anything the engine can release or refuse.
⚠️ Not `untrackedHeadroomBytes / managedHeapBytes`: that compares the heap at the last gen-2 with the ledger now. Under load
the gen-2 is usually a full collection forced at a peak, while work held its reservations, and seconds later the work has
released them; the difference reads two to three times the real gap (**WorkloadCore, 0.3.0**). Expect a share of
10–20 MB that no reservation can own on any server: the runtime, ASP.NET's caches and pooled buffers.

#### `runtime` — the process's own counters (**IngestAtSpeed S01, 0.1.40**)

Additive. Cumulative since process start, except the two heap figures. Take the difference between
two samples to measure a piece of work in units that do not depend on the host: CPU-seconds per
million rows, bytes allocated per row, share of wall time paused for GC.

| Field | Type | Meaning |
|---|---|---|
| `processCpuSeconds` | number | User + kernel CPU of every thread, garbage collection included. |
| `allocatedBytesTotal` | integer | Managed bytes allocated since start. |
| `gcPauseTotalMs` | number | Total time the runtime paused threads for garbage collection. |
| `gen0Collections` / `gen1Collections` / `gen2Collections` | integer | Collections of each generation since start. |
| `lastGen2LiveBytes` | integer | Live bytes after the most recent gen-2 collection (heap minus fragmentation), or `-1` before the first one. Read when the response is built; `managedHeapBytes` is the same reading as of the last reconciliation (**WorkloadCore, 0.3.0**: before, `managedHeapBytes` counted garbage not yet collected, and under a fast ingest the two differed by gigabytes). |
| `heapSizeBytes` | integer | Heap size as of the most recent collection of any generation. |
| `jitCompiledMethods` | integer | Methods the JIT has compiled since start, every tier and on-stack replacement included (**Lead group 2 review, 0.6.0**). A precompiled (ReadyToRun) method counts when it is recompiled at tier 1. Its difference across a piece of work says whether the process was still compiling: the benchmark's steady reads start where it stops growing. |
| `jitCompilationMs` | number | Time spent in the JIT since start, every thread (**Lead group 2 review, 0.6.0**). |
| `lastGen2` | object | The most recent gen-2 collection as the runtime reports it (**WorkloadCore, 0.3.0**): `index`, `kind` (`Background` or `FullBlocking`), `compacted`, `concurrent`, `heapSizeBytes`, `fragmentedBytes`, `promotedBytes` (what it traced live), `totalCommittedBytes`, `pinnedObjectsCount`, `finalizationPendingCount`, and per generation — 0, 1, 2, the large-object heap, the pinned-object heap — `generationSizeAfterBytes`, `generationFragmentationAfterBytes` and `generationSizeBeforeBytes`. `null` before the first. |

🔎 All six provenance fields also appear in the `memory` health component's `details` —
`budgetIsDerived`, `budgetSource`, `budgetIsCgroupBounded`, `budgetFractionApplied`,
`budgetAvailabilityClampBound`, `budgetStartupEffectiveBytes`, `budgetIsStillInForce` and
`budgetDerivation` — so an orchestrator can key on them without polling this route. (**WorkloadCore S17, 0.3.0**)
`resourceMode`, `headroomRatio`, `headroomGovernedBytes`, `workingSetHighWaterBytes` and `workingSetSource` are removed from
those details with the resource mode.

---

### Backup/Restore Endpoints

All endpoints live under `/admin/backup/`. Auth is enforced by the server auth middleware (same as all `/admin/*` routes) — no `[Authorize]` attributes on the controller.

#### Summary

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/backup/trigger` | Trigger an immediate backup |
| `GET` | `/admin/backup/list` | List available backups |
| `POST` | `/admin/backup/restore/{id}` | Restore from a specific backup |
| `GET` | `/admin/backup/schedule` | Get the current backup schedule |
| `PUT` | `/admin/backup/schedule` | Update the backup schedule |

#### `POST /admin/backup/trigger`

Trigger an immediate backup of all active databases. Runs concurrently across databases.

**Request body** (optional):
```json
{
  "destination": "./backups",
  "incremental": true,
  "baseBackupId": null
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `destination` | string? | null | Override backup destination; null = use configured default |
| `incremental` | bool | true | false = full backup |
| `baseBackupId` | string? | null | Specific base backup ID; null = most recent |

**Response** (`200 OK`):
```json
{
  "backupId": "backup-2026-01-28-143000",
  "createdUtc": "2026-01-28T14:30:00Z",
  "basedOn": null,
  "totalBytes": 104857600,
  "newBytes": 10485760,
  "fileCount": 150,
  "newFileCount": 15,
  "blobsUploaded": 15,
  "blobsSkipped": 135,
  "durationSeconds": 2.34
}
```

**Errors:**

| Status | When |
|--------|------|
| 409 Conflict | A backup or restore is already in progress |
| 503 Service Unavailable | Cloud destination not yet supported (S3/Azure/GCS), or engine not ready; (**BL-944, 0.4.0**) or the backup was refused for capacity (`MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`, with `Retry-After`) |
| 400 Bad Request | Destination path cannot be created or accessed |
| 500 Internal Server Error | (**BL-944, 0.4.0**) The backup failed for another reason (an I/O error in the checkpoint, say). Before, every failure was answered 400 as if the destination were wrong |

#### `GET /admin/backup/list`

List all backups at the configured destination, ordered newest-first.

**Response** (`200 OK`):
```json
{
  "backups": [
    {
      "backupId": "backup-2026-01-28-143000",
      "createdUtc": "2026-01-28T14:30:00Z",
      "basedOn": null,
      "totalBytes": 104857600,
      "newBytes": 10485760,
      "fileCount": 150,
      "newFileCount": 15,
      "pitrEligible": true
    }
  ],
  "warning": null
}
```

`warning` is non-null when no destination is configured or when the destination is unavailable.

`pitrEligible` is `true` when every contributing database's manifest recorded a WAL position greater than 0 and (**BL-980, 0.4.0**) the WAL-root incarnation (epoch and root id) a point-in-time restore needs. Position `0` means *unknown* (ADR 0044 D-2); a backup without the incarnation is one of a database without a WAL, or one taken by an older build. Either way the backup is exact-restore-only, and a point-in-time restore of it is refused.

#### `POST /admin/backup/restore/{id}`

Restore from the backup with the given ID. The server engine is stopped, restored, and restarted — this is a blocking, server-wide operation.

An optional JSON body may carry `targetTime` for point-in-time recovery (PITR). An absent or empty body is an **exact restore** of that backup: the response omits `targetTime` and `pitr`.

**Request body** (optional):
```json
{
  "targetTime": "2026-01-28T14:32:00Z"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `targetTime` | string? (ISO-8601) | null | Restore to the last transaction whose commit time is `<=` this instant. Null = exact restore. Compared in UTC. |

#### `POST /admin/backup/restore`

Same operation, with both fields in the body. Omitting `backupId` while supplying `targetTime` selects the newest backup run whose `createdUtc` is at or before that time.

**Request body**:
```json
{
  "backupId": "backup-2026-01-28-143000",
  "targetTime": "2026-01-28T14:32:00Z"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backupId` | string? | null | Backup to restore. Null with a `targetTime` selects the newest run at or before that time. |
| `targetTime` | string? (ISO-8601) | null | Point-in-time target. Null with a `backupId` is an exact restore. |

At least one of `backupId` or `targetTime` is required.

**Response** (`200 OK`) — exact restore (`targetTime` / `pitr` omitted):
```json
{
  "backupId": "backup-2026-01-28-143000",
  "restoredUtc": "2026-01-28T15:00:00Z",
  "filesRestored": 150,
  "bytesDownloaded": 104857600,
  "integrityVerified": true,
  "durationSeconds": 8.12
}
```

**Response** (`200 OK`) — point-in-time restore:
```json
{
  "backupId": "backup-2026-01-28-143000",
  "restoredUtc": "2026-01-28T15:00:00Z",
  "filesRestored": 150,
  "bytesDownloaded": 104857600,
  "integrityVerified": true,
  "durationSeconds": 8.12,
  "targetTime": "2026-01-28T14:32:00Z",
  "pitr": [
    {
      "database": "sales",
      "replayed": true,
      "transactionsReplayed": 4,
      "rowsReplayed": 120,
      "lastAppliedCommitUtc": "2026-01-28T14:31:58Z",
      "stoppedAtTarget": true
    }
  ]
}
```

PITR stops at the last transaction whose `TxCommit` is `<= targetTime` (ADR 0044 D-6). `lastAppliedCommitUtc` is that commit, in UTC.

**Errors:**

| Status | When |
|--------|------|
| 400 Bad Request | Neither field supplied; `targetTime` is in the future; `targetTime` is at or before the backup's `createdUtc`; or the backup recorded WAL position `0` (unknown — exact-restore-only, ADR 0044 D-2) |
| 404 Not Found | Backup ID does not exist at the destination, or no backup run exists at or before `targetTime` |
| 409 Conflict | A backup operation is already in progress |
| 500 Internal Server Error | Point-in-time staging or replay failed — (**BL-980, 0.4.0**) among them a backup that records no WAL-root incarnation, and a replay that meets a WAL frame or catalog-DDL record this build does not read. The body names the database and the error. A failed replay quarantines that database; retry via `POST /api/databases/{db}/unquarantine`. |
| 503 Service Unavailable | Engine not initialized |

#### `GET /admin/backup/schedule`

Get the current backup schedule.

**Response** (`200 OK`):
```json
{
  "cronExpression": "0 2 * * *",
  "destination": "./backups",
  "incremental": true
}
```

`cronExpression` is null when no schedule is set.

#### `PUT /admin/backup/schedule`

Update (or disable) the backup schedule. Saved to the server's `_settings` database before it is applied (**BL-1016, 0.4.0**): a refused save is `503` and nothing changes.

**Request body:**
```json
{
  "cronExpression": "0 2 * * *",
  "destination": "./backups",
  "incremental": true
}
```

Set `cronExpression` to null to disable scheduled backups.

**Response** (`200 OK`): Returns the updated schedule (same shape as GET).

**Errors:**

| Status | When |
|--------|------|
| 400 Bad Request | `cronExpression` is not a valid 5-field cron expression |
| 503 Service Unavailable | (**BL-1016, 0.4.0**) The save was refused (`WAL_CAPACITY_EXCEEDED`, `MEMORY_BUDGET_EXCEEDED`); `Retry-After` is set and the schedule is unchanged — retry. (0.3.0 answered `200` and the schedule reverted at the next start.) |

---

### Replication Endpoints

#### `GET /admin/replication/status`

Get replication status.

**Response:**

```json
{
  "role": "Secondary",
  "currentPrimary": "primary:5000",
  "walPosition": 12345,
  "lagBytes": 0,
  "fencingToken": 1,
  "canAcceptWrites": false,
  "perDatabaseLag": {
    "mydb": {
      "walPosition": 12345,
      "primaryPosition": 12345,
      "lagBytes": 0,
      "tokenCoveredPosition": 9999,
      "bulkLoadHold": { "jobId": "3f2a…", "position": 10000, "sinceUtc": "2026-10-19T20:01:02Z", "loadsHeld": 1 }
    }
  }
}
```

`perDatabaseLag` has one entry per database this node has a position for. (**Lead S18a, 0.6.0**) `tokenCoveredPosition` is
the position a consistency token for that database is covered at here: `walPosition`, or one below `bulkLoadHold.position` while a
replica has seen a bulk load committed and not fetched all of its segments (`jobId` empty when its closing frame could not be
decoded; `loadsHeld` counts every such load). `bulkLoadHold` is `null` when there is none. A read presenting a token at or past
the hold waits, then answers `TOKEN_UNSATISFIED` or `TOKEN_FETCH_PRIMARY` as for any lagging replica.

---

### Cluster Lifecycle Endpoints

All endpoints are under `/admin/cluster/`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/cluster/join` | Join a running cluster |
| `DELETE` | `/admin/cluster/leave` | Leave the current cluster (revert to standalone) |
| `POST` | `/admin/cluster/promote` | Promote this node to primary via election |
| `POST` | `/admin/cluster/failover` | Step down this primary and trigger a new election |
| `POST` | `/admin/cluster/drain/{nodeAddress}` | Mark a member as draining |
| `GET` | `/admin/cluster/config` | Get current cluster configuration |
| `PATCH` | `/admin/cluster/config` | Update mutable cluster configuration fields |

#### `POST /admin/cluster/join`

Join this node to a running replica set while the server is running.
Idempotent: repeating the same call returns 200 without restarting replication.

**Request body:**

```json
{
  "replicaSetName": "rs0",
  "primaryAddress": "primary:5000",
  "thisNodeAddress": "this:5001",
  "role": "secondary"
}
```

`role` is optional: `"secondary"` (default) or `"witness"` (arbiter — votes but stores no data).

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Joined successfully (or already a member of this cluster) |
| `409` | Node is already a member of a different cluster — call `DELETE /admin/cluster/leave` first |

**200 response:**

```json
{ "message": "Joined cluster successfully", "replicaSetName": "rs0" }
```

After a successful join, `cluster-state.json` is written to `{dataPath}/cluster-state.json`.
On the next server restart the node reconnects automatically without the `--join` flag.

---

#### `DELETE /admin/cluster/leave`

Remove this node from its cluster and revert to standalone mode.
Idempotent: safe to call when already standalone.

**Response (200):**

```json
{ "message": "Left cluster, now running as standalone" }
```

---

#### `POST /admin/cluster/promote`

Trigger an election to promote this node to primary.
Only meaningful on a secondary node.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Election started |
| `400` | Already primary, node is an arbiter, or node is not in a cluster |

---

#### `POST /admin/cluster/failover`

Step down this primary and trigger a new election among remaining members.
Only callable on the current primary.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Primary stepped down, election triggered |
| `400` | Node is not the current primary or not in a cluster |

---

#### `POST /admin/cluster/drain/{nodeAddress}`

Mark a member node as draining. The drain state is visible in `GET /admin/cluster/config`
and is reset on server restart (in-memory only — operational state, not persisted).

**Path parameter:** `nodeAddress` — host:port of the member to drain.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Node marked as draining |
| `404` | Unknown node address |

**200 response:**

```json
{ "nodeAddress": "node1:5000", "isDraining": true }
```

---

#### `GET /admin/cluster/config`

Get the current cluster configuration.

**Standalone response (200):**

```json
{ "mode": "standalone", "heartbeatIntervalMs": 0, "electionTimeoutMs": 0 }
```

**Cluster response (200):**

```json
{
  "mode": "cluster",
  "replicaSetName": "rs0",
  "members": [
    { "address": "node1:5000", "isDraining": false },
    { "address": "node2:5000", "isDraining": true }
  ],
  "thisNode": { "address": "node1:5000", "priority": 5, "arbiter": false },
  "heartbeatIntervalMs": 2000,
  "electionTimeoutMs": 10000
}
```

---

#### `PATCH /admin/cluster/config`

Update mutable cluster configuration fields without a restart.

**Mutable fields:** `heartbeatIntervalMs`, `electionTimeoutMs`

**Immutable fields (rejected with 400):** `replicaSetName`, `members`, `thisNode`

**Request body (all fields optional):**

```json
{ "heartbeatIntervalMs": 3000 }
```

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Updated; body is the new `ClusterConfigResponse` |
| `400` | Immutable field supplied (body lists mutable fields) or node is standalone |

---

### Runtime Config Endpoints

All endpoints are under `/admin/config`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/config` | Get current runtime mutable config |
| `PATCH` | `/admin/config` | Patch mutable runtime config fields |
| `GET` | `/admin/config/schema` | List mutable vs immutable fields |

#### `GET /admin/config`

Returns current runtime configuration snapshot.

**Response** (`200 OK`):

```json
{
  "memory": {
    "maxTotalRamBytes": 2147483648,
    "maxHotBytes": 0,
    "maxPageCacheBytes": 0
  },
  "backup": {
    "cronExpression": "0 2 * * *",
    "destination": "./backups",
    "incremental": true
  },
  "logging": {
    "level": "Information"
  }
}
```

#### `PATCH /admin/config`

Patch mutable runtime config values.

**Mutable field paths:**
- `memory.maxTotalRamBytes`
- `memory.maxHotBytes`
- `memory.maxPageCacheBytes`
- `backup.cronExpression`
- `backup.destination`
- `backup.incremental`
- `logging.level`

**Request body** (all fields optional):

```json
{
  "memory": {
    "maxTotalRamBytes": 1073741824
  },
  "logging": {
    "level": "Warning"
  }
}
```

**Response** (`200 OK`): updated config (same shape as `GET /admin/config`).

**Errors:**

| Status | When |
|--------|------|
| `400 Bad Request` | Unsupported/immutable fields, invalid values (e.g., non-positive memory cap), invalid log level |
| `503 Service Unavailable` | (**BL-1016, 0.4.0**) A save was refused (`WAL_CAPACITY_EXCEEDED`, `MEMORY_BUDGET_EXCEEDED`); `Retry-After` is set. Every section the request sets is saved before any is applied, and one saved before a later refusal is put back, so nothing changes — retry. (0.3.0 applied the change, answered `200` and lost it at the next start; a refused save of `memory.maxTotalRamBytes` was a `409`.) |

#### `GET /admin/config/schema`

Returns mutable and immutable config field paths.

**Response** (`200 OK`):

```json
{
  "mutableFields": [
    "memory.maxTotalRamBytes",
    "memory.maxHotBytes",
    "memory.maxPageCacheBytes",
    "backup.cronExpression",
    "backup.destination",
    "backup.incremental",
    "logging.level"
  ],
  "immutableFields": [
    "dataPath",
    "port",
    "bind",
    "replicaSet",
    "archive",
    "auth",
    "databases"
  ]
}
```

---

### Capability Discovery Endpoint

#### `GET /admin/capabilities`

Returns feature and provider capability metadata for Studio and MCP clients.

**Response** (`200 OK`):

```json
{
  "version": "0.1.0",
  "mode": "standalone",
  "backupProviders": ["local"],
  "features": {
    "clusterLifecycle": true,
    "backupManagement": true,
    "runtimeConfig": true,
    "capabilityDiscovery": true,
    "nodeInfo": true,
    "nodeLogs": true,
    "nodeLogStream": true,
    "insertColumnBatch": true,
    "queryColumnBatch": true
  }
}
```

`features.insertColumnBatch` (**ColumnarCore S06, 0.2.0**): `POST …/tables/{name}/rows` reads the column-batch
frame as well as JSON (see [`POST …/rows`](#post-apidatabasesdbtablesnamerows)). Absent on a server that predates it.

`features.queryColumnBatch` (**ColumnarRead S16, 0.3.0**): `POST …/query` and a named query's execute answer with
column-batch frames when the request's `Accept` lists them (see [`POST …/query`](#post-apidatabasesdbquery)). Absent on a
server that predates it.

---

### Node Info and Logs Endpoints

All endpoints are under `/admin/node`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/node` | Node identity and resource snapshot |
| `GET` | `/admin/node/logs` | Recent in-memory logs with filtering |
| `GET` | `/admin/node/logs/stream` | SSE stream of new log entries |

#### `GET /admin/node`

**Response** (`200 OK`):

```json
{
  "nodeId": "MYMACHINE-12345",
  "address": "localhost:5000",
  "role": "Standalone",
  "version": "0.1.0",
  "uptimeSeconds": 123,
  "processId": 12345,
  "machineName": "MYMACHINE",
  "osDescription": "Microsoft Windows 10.0.26200",
  "processorCount": 16,
  "workingSetBytes": 180000000,
  "gcHeapBytes": 42000000
}
```

#### `GET /admin/node/logs`

Query parameters:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | string | null | Minimum log level filter (`Trace`, `Debug`, `Information`, `Warning`, `Error`, `Critical`) |
| `contains` | string | null | Case-insensitive substring match against category/message |
| `limit` | int | 200 | Max entries returned (1..1000) |

**Response** (`200 OK`):

```json
{
  "entries": [
    {
      "timestampUtc": "2026-04-06T18:22:14.123Z",
      "level": "Warning",
      "category": "Aouda.Server.Startup.AoudaHostedService",
      "message": "Server memory budget: 2,147,483,648 bytes"
    }
  ]
}
```

#### `GET /admin/node/logs/stream`

Server-Sent Events endpoint (`text/event-stream`) that emits `log` events as new entries are written.

**Event shape:**

```text
event: log
data: {"timestampUtc":"...","level":"Information","category":"...","message":"..."}
```

---

#### `GET /admin/replication/topology`

Get cluster topology.

**Response:**

```json
{
  "replicaSetName": "my-cluster",
  "members": [
    {
      "address": "node1:5433",
      "role": "Primary",
      "isSelf": true,
      "temperatureProfile": "Balanced",
      "isHidden": false,
      "isReadCandidate": true
    }
  ],
  "readCandidates": ["node1:5433"],
  "primary": "node1:5433"
}
```

---

## Data Types

| Type | Description |
|------|-------------|
| `Bool` | Boolean (true/false) |
| `Byte` | 8-bit unsigned integer |
| `Int16` | 16-bit signed integer |
| `Int32` | 32-bit signed integer |
| `Int64` | 64-bit signed integer |
| `UInt16` | 16-bit unsigned integer |
| `UInt32` | 32-bit unsigned integer |
| `UInt64` | 64-bit unsigned integer |
| `Float32` | 32-bit floating point |
| `Double` | 64-bit floating point |
| `Decimal` with `precision` / `scale` | `Decimal(p,s)`, 1 ≤ p ≤ 18, 0 ≤ s ≤ p: a 64-bit integer scaled by 10^s (**ColumnarCore S13, 0.2.0**). Declared with `"precision"` and `"scale"` beside `"type": "Decimal"` in create-table / add-column bodies and schema documents; reported with the same two fields in column details. Where a type is a name alone (a computed output's `type`, `cast`'s target) it is spelled `"Decimal(18,6)"`. Values are written and read as decimal numbers with exactly `s` places; more places or more than `p − s` integer digits is a `400`; `sum` is an exact `Decimal(18,s)`; `avg` returns a `Double`. See the [schema guide](../guides/schema.md#decimalps-a-decimal-stored-as-a-scaled-integer-columnarcore-s13-020) |
| ~~`Decimal`~~ (undeclared) | (**LoadSpeed S13, 0.4.0; breaking**) Retired: the 128-bit `System.Decimal` of any scale. `"type": "Decimal"` without `precision` and `scale` is refused `400`, plain `"Decimal"` as a type name is refused, and a data directory holding a column of it (type 13) is refused at open, naming the column — export it with the build that wrote it |
| `String` | UTF-8 string |
| `Timestamp` | UTC instant (see note below) |
| `Date` | Date only |
| `Guid` | UUID/GUID |

### Timestamp semantics

`Timestamp` values are **UTC instants** stored as **Int64** (.NET UTC ticks). Insert payloads may use ISO-8601 strings or numeric forms accepted by the server; **the original timezone offset is not stored** and is **not** round-tripped on read (unlike SQL Server `datetimeoffset`). Clients should expect results in **UTC**. For full detail and CLR mapping notes, see [Timestamp Type](./timestamp.md) (corrected: it said Unix milliseconds — **BL-808, 0.3.0**). An **upsert** — `"op": "upsert"` on a named mutation, or an upsert on the write stream — accepts exactly the `Timestamp` and `Date` values an insert does, and refuses the ones an insert refuses (a boolean, a fractional number); a table's `culture` applies to a `Date` string on upsert as it does on insert (**BL-643, 0.1.38**).

---

## Known Limitations

The following features are not yet supported:

1. **NULLS FIRST/LAST**: Custom null ordering is not supported. Nulls sort last for ASC, first for DESC — for every column type (**BL-755, 0.3.0**: a null in a numeric, `Date` or `Timestamp` sort column of an `orderBy` with a `limit` sorted as its type's default, `0`, so ascending pages began with the null rows; **ColumnarRead, 0.3.0**: without a `limit`, the default columnar response put a numeric, `Timestamp` or `Bool` null first ascending too).
2. **Expression-based ORDER BY**: Only catalog column names of sortable types can be used for ordering, not expressions or `selectExpr` aliases. The sanctioned workaround is a stored [`derived`](../guides/insert-transforms.md#derived-columns) column. See [browser-tier read limits](../guides/browser-tier-read-limits.md#no-expression-orderby).

**Note — WhereClause nesting:** Earlier versions of this document stated that nested AND/OR was not supported. This is no longer accurate. The `groups` field in `WhereClause` supports up to **5** levels of nesting (`ProtocolConstants.MaxWhereClauseNestingDepth = 5`). Each group is AND'd with the top-level conditions, enabling safe composition of independent filter layers (e.g., partition scope + row scope). See the `groups` field description in the [`POST /api/databases/{db}/query`](#post-apidatabasesdbquery) section for details.

Remaining limitations are tracked in the backlog for future enhancement.

---

## Future Extensions

The following are candidates for future versions:

- Protobuf binary protocol support (MessagePack is already implemented — see [WebSocket Streaming Protocol](#websocket-streaming-protocol) below)
- Ad-hoc (client-composed) multi-query HTTP batch — independent **named** queries already batch via [Named queries](#named-queries) (`POST …/named-queries/batch`, cap 32, one snapshot)
- GraphQL endpoint

---

## WebSocket Streaming Protocol

Aouda provides a full-duplex WebSocket API for real-time table subscriptions and high-throughput streaming writes.

### Endpoint

```
ws://{host}/api/databases/{db}/ws
wss://{host}/api/databases/{db}/ws   (TLS)
```

The database name is in the **path**. The `auth` message still includes `database` and it must match the path (same rule as HTTP v2).

On the **data-plane** listener this upgrade is allowed; ad-hoc table `subscribe` (no `"name"`) returns `NAMED_QUERY_SUBSCRIBE_REQUIRED`. Write-stream messages return `DATA_PLANE_WRITE_STREAM`.

### Connection and Wire Modes

Upon connecting, the client **must** immediately send an `auth` message. All non-auth messages sent before authentication completes are rejected.

Messages default to JSON encoding. MessagePack binary encoding can be negotiated by setting `"wire_mode": "msgpack"` in the `auth` message. The server echoes the accepted mode in `auth_ok`. Once negotiated, all messages in both directions use the agreed wire mode.

**Serialization:** All field names on the wire are `snake_case` (e.g., `wire_mode`, `resume_from`, `stream_open`).

**Wire mode values:**

| Wire mode string | Description |
|---|---|
| `"json"` | JSON text (default) |
| `"msgpack"` | MessagePack binary |

### Type Discriminator

Every message is a JSON object (or MessagePack map) with a top-level `"type"` field. The receiver peeks `"type"` to dispatch to the correct deserializer. Unknown `type` values are silently discarded.

---

### Client → Server Messages

#### `auth`

Authenticate the connection and optionally negotiate wire mode.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"auth"` |
| `token` | string? | No | Bearer token. Required when server auth is enabled. |
| `database` | string | Yes | Database name this connection is scoped to. |
| `wire_mode` | string? | No | Requested encoding: `"json"` (default) or `"msgpack"`. |
| `user_token` | string? | No | A user JWT to act as, beside a service-level key (`mk_svc_`, `mk_srv_`) in `token` — the realtime `X-User-Token` (**BL-1223, next train**). The session is then that user's: PLS, RLS, grant changes, expiry and revocation, and the user's subscription cap. Ignored beside any other credential. Invalid, expired or revoked → `auth_error` `AUTH_TOKEN_INVALID`. |

**Example:**
```json
{
  "type": "auth",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "database": "my_db",
  "wire_mode": "json"
}
```

**A backend acting as a user** (**BL-1223, next train**):
```json
{ "type": "auth", "token": "mk_svc_xyz789...", "user_token": "eyJhbGciOiJSUzI1NiIs...", "database": "my_db" }
```

**Server responds with:** `auth_ok` or `auth_error`. With a `user_token`, `auth_ok.user_id` and `auth_ok.expires_at` are the user's.

---

#### `subscribe`

Subscribe to a table stream **or** to a named query (unique name). The server pages a consistent snapshot (`snapshot` pages sharing one `version`, then `snapshot_complete`), then streams `change` messages.

Until `snapshot_complete` arrives, the client **must not** treat accumulated snapshot rows as the full match.

The data-plane requires `"name"` (`NAMED_QUERY_SUBSCRIBE_REQUIRED`). The subscription pin is the bound `Where` + `Select`, not an identity string.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"subscribe"` |
| `id` | string | Yes | Client-assigned subscription ID, scoped to the connection. Re-sending it on the same connection **replaces** that subscription — see below. |
| `target` | string | Conditional | Table name. Required for ad-hoc subscribe (admin listener). On the data-plane, omit or match the named query's table when `name` is set. |
| `name` | string? | Conditional | Named-query unique name. **Required on the data-plane listener.** |
| `args` | object? | No | Bind arguments for `name` subscribe. Same shape as HTTP execute `args`. |
| `filter` | object? | No | Ad-hoc `WhereClause`. **Illegal** together with `name` (`NAMED_QUERY_SUBSCRIBE_FILTER`). |
| `resume_from` | number? | No | Resume from this **change-event sequence** version. Three outcomes (unchanged): at-current / buffer replay / expired → **fresh complete snapshot**. Feed `gap.last_seq` here after a `gap`. **Not** the consistency token. |
| `at_least` | string? | No | Consistency-token pin: snapshot at at least this token. Optional `wait_ms` / `on_exceeded` (same values as HTTP). Omitted `at_least` leaves `resume_from` byte-for-byte today's path. |
| `wait_ms` | number? | No | Subscribe freshness wait (with `at_least`). |
| `on_exceeded` | string? | No | `wait` \| `fetchPrimary` \| `fail`. |
| `conflate` | object? | No | Opt-in keyed conflation. Omitted = every visible event. See below. |

**`conflate`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string[]? | Conditional | Columns that form the conflation key. Default: table primary key. Required when the table has no PK. |
| `interval_ms` | number | Yes | Flush interval in milliseconds. Valid range 1…60_000. |
| `collapse_inserts` | bool | No | When true, matching in-scope inserts are held latest-wins per key. Default `false` (omitted on the wire). Delivered `op` stays `"insert"`. |

Default `conflate` holds only **value `update` events** where the row was visible both before and after. `insert`, `delete`, enter-scope, and leave-scope **flush** any pending update for that key and are delivered immediately. Therefore on an **insert-only** (append-only) stream default `conflate` reduces the event rate by zero and `values_skipped` never appears. That subscribe still registers; `snapshot_complete` includes a `CONFLATE_NOOP` warning when the conflate key is not the table PK. Set `collapse_inserts: true` to collapse matching inserts. A `latestPerKey` MQ result table (PK = group key) conflates via `prev` on `update` without the flag. Conflated `change` messages set `values_skipped` (count of dropped intermediate value events, including collapsed inserts). That marker is **intentional loss** and is not a `gap`. See [browser-tier read limits](../guides/browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

**Ad-hoc example (admin listener):**
```json
{
  "type": "subscribe",
  "id": "sub-orders-1",
  "target": "orders",
  "filter": {
    "and": [{"column": "status", "op": "eq", "value": "active"}]
  }
}
```

**Named-query example (required on the data-plane):**
```json
{
  "type": "subscribe",
  "id": "sub-quotes-1",
  "name": "equity.quoteByTicker",
  "args": { "ticker": "AAPL" },
  "conflate": { "key": ["ticker"], "interval_ms": 100 }
}
```

**Server responds with:** one or more `snapshot` pages (same `version`), then `snapshot_complete`, then `change` messages. Over `MaxSnapshotRows` (default 100 000) the subscribe fails with `SNAPSHOT_TOO_LARGE`. Overflow during paging fails with `SNAPSHOT_OVERFLOW` (not a `gap`).

**Limits:** per-connection 32 subscriptions, per-identity 128. Exceed → `SUBSCRIPTION_LIMIT_EXCEEDED`.

**The `id` contract, in full.** An `id` identifies a subscription **on one connection**; it is not
global, and it is not a resource the client has to garbage-collect.

- A `subscribe` naming an `id` the connection **already holds replaces** that subscription
  (**BL-638, 0.1.37**): the old registration is dropped and the new one answers with its own
  `snapshot` / `snapshot_complete`. This is the intended way to re-state a subscription after a
  `gap`, and it is harmless if the client sends one redundantly.
- The replace happens **after** every other check on the `subscribe` passes. A `subscribe` refused
  for any other reason — unknown `name`, `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED`, `PERMISSION_REVOKED`,
  a freshness shortfall — leaves the existing subscription of that `id` untouched and delivering.
  A client can therefore retry a `subscribe` without first proving it will succeed.
- Servers **before** BL-638 refused the second `subscribe` with `DUPLICATE_SUBSCRIPTION_ID`
  instead. That error is informational, not fatal: seeing it means the `id` is registered and
  delivering, so a client should keep the subscription rather than tearing it down. A client that
  treats every subscription `error` as fatal will strand a live view on a benign retry.
- After a **reconnect** the `id` is free again, because the previous connection's registrations
  died with it. Reuse the same `id` on the new socket with `resume_from`; there is no need to mint
  a fresh one, and nothing to clean up on the server.
- `unsubscribe` frees the `id` on that connection immediately and answers `unsubscribed`;
  unsubscribing an `id` the connection does not hold answers `SUBSCRIPTION_NOT_FOUND`.

> **One connection per client, please.** Subscriptions are multiplexed over a single WebSocket.
> Opening a socket per subscription gives you one server session per socket, each with its own
> `id` space and its own idle timeout, and makes the resubscribe behaviour above much harder to
> reason about. The official clients hold exactly one transport per `(server, database)` — see
> [TypeScript client](../clients/typescript.md).


---

#### `re_auth`

Re-authenticate an existing WebSocket session with a refreshed JWT (or API key) **without** tearing down subscriptions. Not valid as the first message — the first message remains `auth`.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"re_auth"` |
| `token` | string | Yes | Refreshed bearer JWT or API key |
| `user_token` | string? | No | The user token, as on `auth` (**BL-1223, next train**). A session opened with one must send one for the same user; a session opened without one cannot add one. Either is `AUTH_TOKEN_INVALID`. |

A **failed** `re_auth` still closes the session (fail-closed). A successful refresh does **not** re-snapshot. Without `re_auth`, JWT expiry closes the socket (`AUTH_TOKEN_EXPIRED`) and every browser re-snapshots.

```json
{ "type": "re_auth", "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." }
```

---

#### `unsubscribe`

Cancel an active subscription.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"unsubscribe"` |
| `id` | string | Yes | Subscription ID to cancel. |

**Example:**
```json
{"type": "unsubscribe", "id": "sub-orders-1"}
```

**Server responds with:** `unsubscribed`.

---

#### `stream_open`

Open a write stream to a table for continuous high-throughput inserts without per-batch HTTP round-trips.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"stream_open"` |
| `id` | string | Yes | Client-assigned stream ID. Must be unique per connection. |
| `table` | string | Yes | Target table name. |
| `mode` | string | Yes | Write mode. Currently only `"insert"` is defined. |

**Example:**
```json
{
  "type": "stream_open",
  "id": "stream-metrics-1",
  "table": "metrics",
  "mode": "insert"
}
```

**Server responds with:** `stream_ready`.

---

#### `stream_rows`

Send a batch of rows on an open write stream.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"stream_rows"` |
| `id` | string | Yes | Stream ID (must match a prior `stream_open`). |
| `seq` | number | Yes | Monotonically increasing sequence number for this batch. Must start at 1 and increment by 1 per batch. The server uses this to detect gaps and for acknowledgement. |
| `columns` | string[] | Yes | (**Lead S12, 0.6.0**) The column names. |
| `data` | array[] | Yes | (**Lead S12, 0.6.0**) One array of values per column, all the same length (at least one row). |
| `absent` | object? | No | (**Lead S12, 0.6.0**) Per column, the rows whose cell is not given (not null). |

The batch is [column arrays](#column-arrays-the-write-body), the same body the HTTP insert takes (**Lead S12, 0.6.0; breaking**:
it was `"rows": [{…}]`). A message that still carries `rows` gets an `error` with code `ROW_OBJECTS_UNSUPPORTED`; column arrays that
do not match get `INVALID_STREAM_ROWS`. Either way nothing of that batch is written. The long-poll fallback's `stream_rows` is read the same way. Rows are still applied and acknowledged one by
one (a `stream_ack` error's `index` is the row's index in the batch).

**Example:**
```json
{
  "type": "stream_rows",
  "id": "stream-metrics-1",
  "seq": 1,
  "columns": ["sensor_id", "value", "recorded_at"],
  "data": [
    [42, 42],
    [98.6, 99.1],
    ["2026-05-22T11:00:00Z", "2026-05-22T11:00:05Z"]
  ]
}
```

**Server responds with:** `stream_ack` after durable write, or `error` on failure.

---

#### `stream_close`

Signal end of a write stream. The client must not send further `stream_rows` on this ID after sending this message.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"stream_close"` |
| `id` | string | Yes | Stream ID to close. |

**Example:**
```json
{"type": "stream_close", "id": "stream-metrics-1"}
```

**Server responds with:** `stream_closed`.

---

#### `ping`

Liveness check. The server responds immediately with `pong`.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"ping"` |

**Example:**
```json
{"type": "ping"}
```

---

### Server → Client Messages

#### `auth_ok`

Successful authentication acknowledgement.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"auth_ok"` |
| `user_id` | string? | Authenticated user ID. Null for API key or unauthenticated connections. |
| `expires_at` | string? | ISO 8601 UTC token expiry. Null if the token does not expire. |
| `wire_mode` | string? | Negotiated wire mode: `"json"` or `"msgpack"`. Null means `"json"`. |

**Example:**
```json
{
  "type": "auth_ok",
  "user_id": "usr_abc123",
  "expires_at": "2026-05-23T11:00:00Z",
  "wire_mode": "json"
}
```

---

#### `auth_error`

Authentication failure. The server closes the connection after sending this message.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"auth_error"` |
| `code` | string | Error code (e.g., `AUTH_TOKEN_INVALID`, `AUTH_TOKEN_EXPIRED`). `AUTH_TOKEN_INVALID` also answers a `user_token` that is invalid, expired or revoked (**BL-1223, next train**). (**Next train**) A check the server refused for capacity — at the handshake or a `re_auth` — is the refusal's own code (`MEMORY_BUDGET_EXCEEDED`, `WAL_CAPACITY_EXCEEDED`, `SERVICE_UNAVAILABLE`): reconnect after a short wait with the same token; it is not invalid. 0.3.0 sent `AUTH_TOKEN_INVALID`. |
| `message` | string | Human-readable error description. |

**Example:**
```json
{
  "type": "auth_error",
  "code": "AUTH_TOKEN_EXPIRED",
  "message": "Token has expired"
}
```

---

#### `heartbeat`

Periodic liveness signal carrying the current **per-database change-event sequence** (`version`) and this node's consistency `token`. Clients **must not** infer a gap from `heartbeat.version` or from holes in `change.version` — the sequence is shared by all tables on the database, so a subscriber to table A legitimately sees holes from table B. Unintentional loss is a server-emitted `gap` message (below). `version` is **not** a WAL sequence; freshness for a later HTTP read is `token`.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"heartbeat"` |
| `version` | number | Current change-event sequence (monotonically increasing). |
| `token` | string? | This node's current C-1 consistency token (42-hex). |

**Example:**
```json
{"type": "heartbeat", "version": 100042, "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213"}
```

---

#### `error`

General error, optionally scoped to a subscription or stream ID.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"error"` |
| `id` | string? | Subscription or stream ID this error is scoped to. Null for connection-level errors. |
| `code` | string | Error code (see Error Codes section). |
| `message` | string | Human-readable error description. |

**Example:**
```json
{
  "type": "error",
  "id": "sub-orders-1",
  "code": "TABLE_NOT_FOUND",
  "message": "Table 'orders' does not exist"
}
```

---

#### `pong`

Liveness reply to a client `ping`.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"pong"` |

---

#### `snapshot`

One page of a subscription's current data. Pages share one pinned `version`. More pages may follow until `snapshot_complete`.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"snapshot"` |
| `id` | string | Subscription ID this snapshot belongs to. |
| `columns` | string[] | (**Lead S12, 0.6.0**) The page's column names. |
| `data` | array[] | (**Lead S12, 0.6.0**) The page's rows as column arrays: one array per column, one value per row. May be empty (a page of no rows may also name no columns). |
| `version` | number | Pinned snapshot **change-event** version. Store this; pass as `resume_from` on reconnect. |
| `token` | string? | Consistency token of the snapshot cut (same string on every page and `snapshot_complete`). |

**Example:**
```json
{
  "type": "snapshot",
  "id": "sub-orders-1",
  "columns": ["id", "status", "total"],
  "data": [
    [1, 2],
    ["active", "active"],
    [150.00, 99.99]
  ],
  "version": 100040
}
```

(**Lead S12, 0.6.0; breaking**) A page is column arrays, as a query result is; it was `"rows": [{…}]`, one object per row.
`snapshot_complete` and `change` are unchanged: a change event still carries one row.

---

#### `snapshot_complete`

Marks the end of the paged snapshot. Clients must not treat accumulated `snapshot` rows as the full match until this arrives. Change events are held until this message; overflow during paging fails the subscribe (`SNAPSHOT_OVERFLOW`), not a mid-snapshot `gap`.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"snapshot_complete"` |
| `id` | string | Subscription ID |
| `version` | number | Same pinned version as every preceding `snapshot` page |
| `row_count` | number | Total rows delivered across all snapshot pages |
| `total_matches` | number? | Present when the named query declared `count: true` — total matching rows, ignoring limit/offset |
| `warnings` | object[]? | Optional (e.g. `NAMED_QUERY_DEPRECATED` on hash subscribe; `CONFLATE_NOOP` when default `conflate` cannot collapse inserts) |
| `token` | string? | Same C-1 string as every preceding snapshot page |
| `horizon` | string? | (**Horizon, 0.5.0**) The subscribed table's horizon, ISO-8601 UTC with seven fractional digits (`"2026-10-11T12:34:00.0000000Z"`), when it has one — a windowed materialized query's result or a table with retention. It is read after the snapshot, so for a moment the snapshot can hold a row below it; a `horizon` message then follows. Apply it to the snapshot as to a notice: drop every row whose `horizon_column` lies below it or is null. Omitted for any other table. A windowed result's snapshot (and a named-query subscribe's `total_matches`) is its **stored** part: nothing below the horizon is computed for a subscription. |
| `horizon_column` | string? | (**Horizon, 0.5.0**) The column `horizon` applies to; present with it. |
| `horizon_column_type` | string? | (**Horizon, 0.5.0**) `"date"` when `horizon_column` is a `Date` column — its row values are day numbers (days since the Unix epoch), not Unix milliseconds. Omitted for a `Timestamp`. |

```json
{
  "type": "snapshot_complete",
  "id": "sub-orders-1",
  "version": 100040,
  "row_count": 2,
  "token": "01a1b2c3d4e5f60708090a0b0c0d0e0f10111213"
}
```

---

#### `gap`

Server-emitted per-subscription overflow signal. The sequence number is **per-database**, so the client cannot infer a gap from `seq > last + 1`. On the first drop after a clean period the server emits exactly one `gap` on the affected subscription and unregisters it. Other subscriptions on the same connection are unaffected.

Feed `last_seq` to a new `subscribe` as `resume_from` (existing three-outcome path). This is **unintentional** loss. Distinguish from `change.values_skipped` (intentional conflation).

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"gap"` |
| `id` | string | Subscription that overflowed (already unregistered) |
| `last_seq` | number | Last successfully delivered change version, or the snapshot version if none |
| `discarded` | number | Events dropped in this clean period |

```json
{
  "type": "gap",
  "id": "sub-orders-1",
  "last_seq": 100041,
  "discarded": 17
}
```

---

#### `change`

Incremental row change on an active subscription. Sent whenever a row matching the subscription filter is inserted, updated, or deleted. Named-query subscriptions project `row` / `prev` to the definition's `select`.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"change"` |
| `id` | string | Subscription ID this change belongs to. |
| `op` | string | Operation: `"insert"`, `"update"`, or `"delete"`. |
| `row` | object? | New row values. Present for `"insert"` and `"update"`. Null for `"delete"`. |
| `prev` | object? | Previous row values before update. Present for `"update"` only. |
| `key` | object? | Primary key of the affected row. Present for `"delete"`. |
| `version` | number | Per-database sequence version of this change. Do not infer gaps from holes. |
| `values_skipped` | number? | Present on conflated value updates: count of intermediate updates dropped. **Not** a `gap`. |
| `token` | string? | C-1 token of **this event's** WAL position. Hand to HTTP `?at_least=` to be sure the read sees this change. |

**Example — insert:**
```json
{
  "type": "change",
  "id": "sub-orders-1",
  "op": "insert",
  "row": {"id": 3, "status": "active", "total": 200.00},
  "version": 100041
}
```

**Example — update:**
```json
{
  "type": "change",
  "id": "sub-orders-1",
  "op": "update",
  "row":  {"id": 1, "status": "shipped", "total": 150.00},
  "prev": {"id": 1, "status": "active",  "total": 150.00},
  "version": 100042
}
```

**Example — delete:**
```json
{
  "type": "change",
  "id": "sub-orders-1",
  "op": "delete",
  "key": {"id": 2},
  "version": 100043
}
```

---

#### `horizon`

(**Horizon, 0.5.0**) The subscribed table's horizon rose — a windowed materialized query's result, or a table with retention
(the server's clock advanced, or a `DELETE` before a time expired rows early). Every row whose `column` lies below `horizon`, or is
null there, is gone: drop what you hold below it and keep no later row below it. No `change` is sent for those rows. One per published
advance.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"horizon"` |
| `id` | string | Subscription ID |
| `column` | string | The column the horizon applies to (a windowed result's window column; a table's first cluster column) |
| `horizon` | string | The new horizon, ISO-8601 UTC, seven fractional digits |
| `version` | number | Change-event sequence of the notice; resume from it as from a `change` |
| `token` | string? | Consistency token of the notice, when the server can encode one |
| `column_type` | string? | `"date"` when `column` is a `Date` column (its row values are day numbers); omitted for a `Timestamp` |

```json
{ "type": "horizon", "id": "sub-candles", "column": "Minute", "horizon": "2026-10-09T00:01:00.0000000Z", "version": 100057 }
```

---

#### `range_delete`

(**Horizon, 0.5.0**) On a table **without** retention, one `DELETE` whose whole predicate was `column lt X` (`before` = `X`) or
`column lte X` (`before` = the successor of `X` at the column's resolution) deleted every row whose `column` lay below `before`, at
this point of the stream. Drop what you hold below it; a row with a null time was not deleted. No horizon is installed: rows that
arrive after this message are live whatever their time. No per-row `change` is sent.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"range_delete"` |
| `id` | string | Subscription ID |
| `column` | string | The time column the statement compared |
| `before` | string | The exclusive cutoff, ISO-8601 UTC, seven fractional digits |
| `version` | number | Change-event sequence of the notice |
| `token` | string? | Consistency token of the notice, when the server can encode one |
| `column_type` | string? | `"date"` when `column` is a `Date` column (its row values are day numbers); omitted for a `Timestamp` |

```json
{ "type": "range_delete", "id": "sub-trades", "column": "Ts", "before": "2026-07-01T00:00:00.0000000Z", "version": 100060 }
```

**Both notices** are ordered in the table's change stream (a `range_delete` is emitted inside the statement's commit, so a row
inserted after it arrives after it), kept by the resume buffer and replayed on `resume_from`. They go to every subscriber of the table
that is not denied it: a notice names no row, so `filter`, a named query's bound `where` and RLS do not apply. A conflated
subscription sends what it holds first. A client that does not know these types ignores them ([Type Discriminator](#type-discriminator))
and keeps rows the server no longer returns until it subscribes again. See
[Real-time Streaming — Horizons and range deletes](../guides/real-time.md#horizons-and-range-deletes).

---

#### `unsubscribed`

Confirms a subscription has been cancelled.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"unsubscribed"` |
| `id` | string | Subscription ID that was cancelled. |

**Example:**
```json
{"type": "unsubscribed", "id": "sub-orders-1"}
```

---

#### `stream_ready`

Confirms a write stream is open and ready to receive rows.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"stream_ready"` |
| `id` | string | Stream ID that is ready. |

**Example:**
```json
{"type": "stream_ready", "id": "stream-metrics-1"}
```

---

#### `stream_ack`

Acknowledges durable receipt of rows through the given sequence number. May include per-row rejection details.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"stream_ack"` |
| `id` | string | Stream ID. |
| `through` | number | All rows in batches with `seq ≤ through` have been durably written. |
| `errors` | array? | Per-row rejection details. Null or absent when all rows were accepted. |

**Per-row error:**

| Field | Type | Description |
|---|---|---|
| `index` | number | 0-based row index within the rejected batch. |
| `code` | string | Error code. |
| `message` | string | Human-readable description. |

**Example — all rows accepted:**
```json
{"type": "stream_ack", "id": "stream-metrics-1", "through": 3}
```

**Example — partial rejection:**
```json
{
  "type": "stream_ack",
  "id": "stream-metrics-1",
  "through": 3,
  "errors": [
    {"index": 1, "code": "INVALID_VALUE", "message": "Column 'value': expected Double, got String"}
  ]
}
```

---

#### `stream_closed`

Confirms a write stream has been closed.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"stream_closed"` |
| `id` | string | Stream ID that was closed. |

**Example:**
```json
{"type": "stream_closed", "id": "stream-metrics-1"}
```

---

### WebSocket Session Lifecycle

**Subscription lifecycle:**
```
Client                                  Server
  ──── auth ──────────────────────────►
  ◄─── auth_ok ────────────────────────
  ──── subscribe (id="sub1") ──────────►
  ◄─── snapshot (id="sub1") ─────────── (current rows)
  ◄─── change   (id="sub1", op=insert)  (as rows change)
  ◄─── change   (id="sub1", op=update)
  ──── unsubscribe (id="sub1") ────────►
  ◄─── unsubscribed (id="sub1") ────────
```

**Write stream lifecycle:**
```
Client                                  Server
  ──── stream_open (id="s1") ──────────►
  ◄─── stream_ready (id="s1") ─────────
  ──── stream_rows (id="s1", seq=1) ───►
  ◄─── stream_ack  (id="s1", through=1)
  ──── stream_rows (id="s1", seq=2) ───►
  ──── stream_rows (id="s1", seq=3) ───►
  ◄─── stream_ack  (id="s1", through=3)
  ──── stream_close (id="s1") ─────────►
  ◄─── stream_closed (id="s1") ─────────
```

---

## Bulk Load API

The Bulk Load API provides high-throughput batch data ingestion with durability guarantees, idempotency, and optional replication barriers. It uses a begin/append/commit pattern over HTTP.

All bulk-load endpoints are under `/api/databases/{db}/bulk-load`. The `:append` request body is the binary column-batch frame (`application/vnd.aouda.column-batch-v2`) or one JSON body of [column arrays](#column-arrays-the-write-body) (`application/json`); see [`:append`](#post-jobidappend). (**Lead S12, 0.6.0; breaking**) NDJSON (`application/x-ndjson`) is no longer read: it is refused `415 ROW_OBJECTS_UNSUPPORTED`. All other bodies are JSON.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/databases/{db}/bulk-load:begin` | Begin a new session. Returns `jobId`. |
| `POST` | `/api/databases/{db}/bulk-load/{jobId}:append` | Append rows (column-batch frames, or JSON column arrays). |
| `POST` | `/api/databases/{db}/bulk-load/{jobId}:commit` | Commit the session. |
| `GET` | `/api/databases/{db}/bulk-load/{jobId}` | Get session status and progress. (Listed as `{jobId}:status` until **WorkloadCore, 0.3.0**; the route has always been `{jobId}`.) |
| `GET` | `/api/databases/{db}/bulk-load:list` | List all sessions for this database. |
| `POST` | `/api/databases/{db}/bulk-load:force-abort` | Operator abort; the job id is in the body. (Listed under `{jobId}` until **WorkloadCore, 0.3.0**; the route has always been this.) |

---

### `POST :begin`

Allocate a bulk-load session and acquire table locks. Returns a `jobId` that all subsequent requests must reference.

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `database` | string | Yes | Database name (must match `{db}` in path). |
| `tables` | string[] | Yes | Tables this load writes to. Index 0 is the primary table. Single-element array for single-table loads. When more than one table is listed, each row in `:append` calls must carry a `"_table"` discriminator field naming its destination. Empty array is rejected (400). |
| `options` | object? | No | Load options (see below). |
| `idempotencyKey` | string? | No | Client-supplied key. If the same key is received within the server's idempotency window (default 10 min) while the prior job is still in-flight, the same `jobId` is returned without re-acquiring the lock. |

**Load options:**

| Field | Type | Default | Allowed values | Description |
|---|---|---|---|---|
| `conflictPolicy` | string? | `"block"` | `"block"`, `"failFast"` | How to handle a conflicting in-flight job on the same table. `"block"` waits; `"failFast"` returns `BULK_LOAD_TABLE_LOCKED` immediately. Case-insensitive. |
| `afterJobId` | string? | null | a `jobId` a `:begin` returned | (**Lead S21b, 0.6.0**) The job this one follows: a job on the same tables, begun before it. This job takes its place in the tables' commit order after that one — it does not take the tables first, even if that job is still waiting for them behind another loader's job — and **commits only if that job committed**. If that job failed or was aborted, this job's commit is refused `409 BULK_LOAD_PREDECESSOR_NOT_COMMITTED` and none of its rows is loaded. A loader that sends job N+1 while job N commits names N here, so a failure in N leaves every later job uncommitted, and a sequence of jobs commits a prefix of them, in order. A job that follows a job on **other** tables waits, at its commit point, for that job's outcome (**Lead group 5 review, 0.6.0**: it read the outcome at once, and was refused or not by timing). A job that names itself is refused `400 BULK_LOAD_INVALID_OPTIONS`. Not a job id: `400 BULK_LOAD_INVALID_OPTIONS`. Both SDKs' multi-job loaders set it (`@aouda/client` from **Lead S22, 0.6.0**). |
| `validation` | string? | `"coerce"` | `"coerce"`, `"strict"` | (**Lead S27a, 0.6.0**) What the load checks ([Bulk Load — a load's validation](../guides/bulk-load.md#a-loads-validation-coerce-or-strict-lead-s27a-060)). `"coerce"`: a null or absent cell in a NOT NULL column is stored as the type's default (`0`, `""`) — **except in a primary-key column**, which is refused (see [`:append`](#post-jobidappend)); keys are not checked for uniqueness. `"strict"`: a null or absent cell in any NOT NULL column is refused the same way, and a primary key the job holds twice, or one the table already holds, fails the job at its commit (`409 BULK_LOAD_DUPLICATE_PK`, nothing committed). Every load refuses a column its table does not have. An auto-increment column is exempt (a missing value takes the next id). Refused `400 BULK_LOAD_INVALID_OPTIONS`: any other value (case-sensitive); `"strict"` on a table whose key mode (`pkUniqueness`) is not `Strict` — a job is never stricter than its table — or with `applyTransforms`. |
| `pkUniquenessOverride` | — | — | — | (**Lead S27a, 0.6.0; breaking**) Removed: no server ever applied it. Any value is refused `400 BULK_LOAD_INVALID_OPTIONS` with a message naming `validation`. |
| `replicationMode` | string? | `"logShipSegments"` | `"logShipSegments"`, `"skipReplication"`, `"markForSnapshot"` | Replication strategy. `"skipReplication"` on a multi-node cluster without `forceSingleNodeReplicationBypass: true` is rejected (400 `BULK_LOAD_INVALID_OPTIONS`). Case-insensitive. |
| `forceSingleNodeReplicationBypass` | bool? | `false` | `true`, `false`, null | Two-key safety valve: must be `true` to use `"skipReplication"` on a multi-node cluster. |
| `maxRowsPerSegment` | number? | null | Any positive integer | Override the maximum rows per sealed segment. Null = use server default. |
| `embeddingModelVersion` | string? | null | Any valid model version string | Embedding model version for vector-indexed tables. |
| `postLoadMqBehavior` | string? | `"auto"` | `"auto"`, `"skip"` (`"deferred"` until 0.3.x; refused `400` from the 0.4.0 — use `"auto"`) | Controls materialized-query handling after commit, for **all four** MQ types whose source tables are in this load. `"auto"` (default): the load's queries are brought current by the server, and you wait on `mqRebuildStatus` (below) — **do not** also call `POST .../materialized-queries/{name}:refresh` for these tables: it runs the table's pass that was starting anyway or, once that has run, re-scans the whole source table. (**WorkloadCore S10, 0.3.0**) `"auto"` records a pending job, as `"deferred"` did, and starts the table's **deferred pass** for each table it wrote right after the commit (multi-table and transform loads included): a fold of the load's segments for every query the fold can plan, the load's rows applied as inserts for any other query directly over the table, a rebuild for the rest (**WorkloadCore S17, 0.3.0**: by a background rebuild job after the pass, so the other queries on the table are not held behind one long rebuild), and the queries built on them caught up. The load does no materialized-query work while its rows stream and is not paced to a drain. Until the pass ends its queries read as behind (`isStale: true`, `pendingDeferredJobs` ≥ 1, `current: false`). Before S10, how `"auto"` did it depended on the table: a table of only `aggregate` and `latestPerKey`/`firstPerKey` queries was folded as the load wrote its segments and written by the table's pass after the commit; on any other table the queries accumulated during the load's own pass and published by shadow-swap after the commit (the ingest-fed path). (**WorkloadCore S09, 0.3.0**) Every `"auto"` load's maintenance runs after the commit point, in the background, and `:commit` waits for it only as long as `mqWaitMs` allows (below): on a table of only aggregates and latest / first per key the load used to write its queries before `:commit` returned, with `mqRebuildStatus: "completed"` (**ColumnarCore S12, 0.2.0**). `"skip"`: no pending job, no pass and no rebuild; use for multi-step pipelines that call `:refresh` explicitly themselves. (**LoadSpeed K31, 0.4.0**) `"deferred"` is refused `400 BULK_LOAD_INVALID_OPTIONS` with a message saying to use `"auto"`: it was folded into `"auto"`, which since M.3 leaves a loading table's pass to the quiet period as `"deferred"` did, and which with `mqWaitMs` 0 (the default) does not wait at `:commit`. Until then: `"deferred"` (**BatchFirst S08, 0.1.40**): the load writes only the table, marks its queries behind (`isStale: true`; **WorkloadCore S10, 0.3.0**: owed the pass, not marked stale as `"skip"` leaves them), and records a durable pending job; the table's deferred pass brings them current once bulk ingest into the table has been quiet for 2 s, or once the oldest pending job has waited 60 s, or at once on `:refresh` of any owed query — and an update, delete or upsert of the table brings its queries current before it applies. It was for very large or many back-to-back loads: many loads, one pass (a server before 0.1.40 refused it `400` too). See [Deferred loads](../guides/materialized.md#deferred-loads). |
| `identityInsert` | bool? | `false` | `true`, `false`, null | Job-scoped identity-insert (same semantics as ordinary insert `identityInsert`). When `true`, every autoIncrement column must be present/non-null on every appended row; values (including literal `0`) are stored as-is with **no** ID allocation; after a **successful job commit** the runtime counter advances to `max(inserted)` per `(table, column)`. Failed or aborted jobs do **not** bump the counter. Null/`false` = default bulk-load path (missing/null autoIncrement values coerce to `0`; bulk-load alone does not allocate IDs or bump the counter). Equivalent to Bond `isAutoIncrementDisabled: true` for large ingest. |
| `applyTransforms` | bool? | null | `true`, `false`, null | **Transform intent.** The server computes every write-time value (derived columns, expression defaults, checks) for the rows you append, and expands the lock set to the transform-graph closure. Mutually exclusive with `preTransformed`. |
| `preTransformed` | bool? | null | `true`, `false`, null | **Transform intent.** The rows are already materialized — every derived column is present in the payload — so the server writes the named tables as-is with no transform pipeline. Mutually exclusive with `applyTransforms`. |
| `durability` | string? | the database's level for a load: `"os"` in a database at `os`, else `"strict"` | `"strict"`, `"os"` | (**Lead S26c, 0.6.0**) The job's own durability. `"strict"`: every segment file, its directory and the job's commit record are fsynced before the job is visible, so it survives a power loss — what every load did before. `"os"`: the files are written and renamed and the commit record written, none of it fsynced: it survives a process crash, and after a power loss it is kept whole or dropped whole and reported `"lost"` ([`GET {jobId}`](#get-jobid)). The server syncs an `"os"` job in the background from its commit; until then every durable write on the database waits for it. An `"os"` load writes no WAL frame. A table's own level does not change the default: an `unlogged` table still gets `"strict"`. Refused `400 BULK_LOAD_INVALID_OPTIONS`, the message naming the level: any other value (`"unlogged"` and `"memory"` are table and database levels, not a load's; case-sensitive), `"strict"` in a database at `os` (its WAL is not written through), and `"os"` for a job of several tables, a table with vector columns, or an edge or vector table — so a multi-table load into an `os` database is refused. See [Bulk Load — a load's durability](../guides/bulk-load.md#a-loads-durability-strict-or-os-lead-s26c-060). |

**Transform intent is mandatory for a table with write-time compute.**

If any destination table has a derived column, an expression default, or a check constraint, `:begin`
requires **exactly one** of `applyTransforms` or `preTransformed`. Omitting both is
`BULK_LOAD_TRANSFORM_INTENT_REQUIRED` (400); setting both is `BULK_LOAD_TRANSFORM_INTENT_CONFLICT`
(400). Neither flag is a fallback for the other — the server will not guess whether the numbers you
sent are inputs or results, because both readings silently produce a loaded table.

Both are valid choices:

| | Send | Server does | Use when |
|---|---|---|---|
| `applyTransforms: true` | Only the source columns | Computes derived values, evaluates checks and expression defaults, locks the whole transform-graph closure | The computation belongs to the database — ongoing ingest, several writers, or a formula you do not want duplicated in a client |
| `preTransformed: true` | Every column, derived ones included | Writes the named tables as-is | A one-shot backfill or migration where you already have the values. Cheaper: no per-row planning, and a narrower lock set. You are asserting the values are correct — nothing recomputes them |

A table with no write-time compute needs neither flag.

**Deadlines and sizes.** These are server settings, not request fields.

> **Not in 0.1.20.** Every setting in this table ships in the **next** server train (BL-404 /
> BL-405). On 0.1.20 the `Aouda:BulkLoad:*` keys below are ignored, and `Aouda:MaxConnections: 0`
> is rejected at startup with `MaxConnections must be at least 1` — on that version the value
> must be a positive integer. Check your server version before changing any of them.


| Setting | Default | What it governs |
|---|---|---|
| `Aouda:BulkLoad:StreamingRequestTimeoutMs` | `600000` (10 min) | Request deadline for `:append` and `:commit` only. These two opt out of `Aouda:RequestTimeoutMs` (30 s), which still governs every other endpoint. `0` disables the deadline on them. |
| `Aouda:BulkLoad:SessionIdleTimeoutMinutes` | `10` | How long an in-flight session may make no progress before the sweeper aborts it and releases its table lock. This — not the request deadline — is what bounds a client that walked away. `0` disables idle aborts. |
| `Aouda:BulkLoad:MaxConcurrentStreamingRequests` | `4` | Size of the admission lane `:append` runs in. It does **not** draw on `Aouda:MaxConcurrentRequests` (50), because a multi-minute call would hold one of those permits for its whole duration. `0` = unlimited. (**Lead S18a, 0.6.0**) `:commit` is on no lane, so it never waits behind `:append`s gated on the job it would finish; keep the loaders into one table at or below this setting (**BL-1117**). (**Lead S21b, 0.6.0**) A body that commits its job keeps its permit until its commit answers; a pipelined loader has one job sending rows and one committing, and four such loaders into one table finish on the default lane while no job's queue fills. (**Lead S31, 0.6.0**) An `:append` waiting for room in its job's queue (`Aouda:BulkLoad:MaxQueuedAppendBytes`) keeps its permit, so with jobs larger than that queue three pipelined loaders into one table can starve the lock holder's next `:append`: keep it to half this setting's pipelined loaders a table (**BL-1117**). |
| `Aouda:BulkLoad:StreamingRequestQueueLimit` | `100` | How many streaming requests may wait for a lane slot. Beyond it, 503. Generous by design: a rejected `:append` must be recovered by its client (a keyed `:begin`, then the same body: see [the frame numbers](#a-jobs-frames-are-numbered-lead-s21a-060)), so a rejection costs the load a round of recovery or, in a client that does not recover, the load. |
| `Aouda:MaxConnections` | `0` (unlimited) as of **BL-419, 0.1.22** — was `100` through 0.1.21 | Kestrel's concurrent-connection ceiling. `0` (Kestrel's own default) means the request limiter (`MaxConcurrentRequests` + `RequestQueueLimit`) is the first thing an overloaded server hits, and it sheds with a retryable HTTP status; the old `100` default sat *below* that budget (150) on every stock deployment, so the connection ceiling — which Kestrel enforces by silently closing the socket with **no HTTP response** — bit first instead. If you do set a finite value, keep it above `MaxConcurrentRequests + RequestQueueLimit`. On 0.1.20 and earlier, `0` fails validation at startup (`MaxConnections must be at least 1`) — check your server version before relying on the unlimited default. |


**Response body:**

| Field | Type | Description |
|---|---|---|
| `jobId` | string | Server-assigned job identifier. Include in all subsequent requests for this load. |
| `tables` | string[] | Echo of the requested tables. |
| `acquiredAtUtc` | string | ISO 8601 UTC timestamp when table locks were acquired. |
| `maxRowsPerAppend` | number | The most rows **one frame** of an `:append` body carries (a JSON column-array body is one frame). A larger frame is refused whole. (**Lead S21a, 0.6.0**) It counted across all the frames of one `:append`; a body may now hold any number of frames under it. |
| `nextSequence` | number | (**Lead S21a, 0.6.0**) The number of the job's next frame: `0` for a new job; for a reconnect to a live job, the first frame it has not applied. A job's frames are [numbered across all its bodies](#a-jobs-frames-are-numbered-lead-s21a-060). Send from this frame. |
| `acceptedAppendFormats` | string[]? | (**IngestAtSpeed S09, 0.1.40**) The `:append` body formats this server decodes: `["column-batch-v2", "column-arrays"]` — frames, and one JSON column-array body (**Lead S12, 0.6.0**: it was `["ndjson", "column-batch-v2"]`; `"ndjson"` is gone, and `"column-batch"`, `ACB1`, went in **Lead S09**). Absent from older servers, which read NDJSON only. The SDKs send the frame only when it is listed. |
| `resumedFromDurableCursor` | object? | Present when this `:begin` resumed an in-flight job via idempotency-key match. Null for fresh jobs. Contains `rowsDurablyCommitted` (number), `segmentsCommitted` (number), `perTable` (object mapping table name to durable row count) and `rowsAppended` (number?). **Resume from `nextSequence`** (above): the frames below it are applied, buffered ones included, and `rowsAppended` is the rows they carry — a client that resumes by frames checks that the frames it skips carry exactly that many, so a client whose framing changed (another source, other body bounds) stops instead of loading rows twice or not at all. `rowsDurablyCommitted` counts only the durable rows and is not a position. (**Lead S21a, 0.6.0; breaking**) This replaces `resumeFromRow`, a row cursor, which is gone. ⚠️ No server rebuilds a cursor after a restart yet (BL-067): an open job does not survive one, and a `:begin` with its key afterwards starts a fresh job (`nextSequence: 0`), so the load is sent from its first frame. Both SDKs resume this way (`@aouda/client` from **Lead S22, 0.6.0**). |
| `alreadyCompleted` | bool | `true` when the idempotency key matched a job that already **committed** (within `Aouda:BulkLoad:IdempotencyWindowMinutes`): no session is opened, and `:append` / `:commit` on this `jobId` are refused `409 BULK_LOAD_INVALID_STATE`. Read the job's result from `rowsDurablyCommitted` and `token` below. `false` otherwise. |
| `rowsDurablyCommitted` | number? | With `alreadyCompleted`: the committed job's rows. |
| `durability` | string | (**Lead S26c, 0.6.0**) The level the job will commit at, `"strict"` or `"os"`; for a replayed completed job (`alreadyCompleted`), the level it committed at. |
| `validation` | string? | (**Lead S27a, 0.6.0**) The job's validation, `"coerce"` or `"strict"`. Omitted for a job answered from its commit record after a restart (the record does not keep it). |
| `token` | string? | With `alreadyCompleted`: the committed job's consistency token — the one its `:commit` returned. (**Lead S20a, 0.6.0**) A single-node job's too: it was `null` for a load that wrote no closing frame, so a client that lost the `:commit` response could not read its own write with a token. |

**Example:**
```
POST /api/databases/my_db/bulk-load:begin
Content-Type: application/json

{
  "database": "my_db",
  "tables": ["events"],
  "options": {"replicationMode": "logShipSegments"},
  "idempotencyKey": "load-2026-05-22-batch-001"
}

200 OK
{
  "jobId": "blj_abc123",
  "tables": ["events"],
  "acquiredAtUtc": "2026-05-22T09:00:00Z",
  "maxRowsPerAppend": 50000,
  "resumedFromDurableCursor": null
}
```

**Authorization (**BL-1031, 0.5.0**).** `:begin` returns `403` `AUTHORIZATION_DENIED` when any table the load will
write — the tables in the request, plus transform targets when `applyTransforms` is set — has partition-level or
row-level security, unless the caller is an app `service_role` key (`mk_svc_`). A user JWT, a server API key (`mk_srv_`),
and a `custom` key are refused, including one whose grants would allow an ordinary insert of the same rows. A table with
no PLS and no RLS policy is not affected. The refusal happens before a session exists; `:append` does not filter rows.

---

### `POST {jobId}:append`

Append frames of rows to an in-flight session.

**Each frame is checked against its table before any of it is applied** (**Lead S27a, 0.6.0**). A frame is refused
`400 INVALID_REQUEST` — none of its rows applied, the frames before it credited (`nextSequence` unchanged past them), the job still
open — when it carries:

- **a column the table does not have** (**BL-1130**: it used to be dropped without a word). Names are case-sensitive; the message
  names the column the table does have when only the case differs;
- **no value for a primary-key column** — a null or absent cell, or the column missing (**BL-1129**: it used to be stored as the
  type's zero, an `Int64` key as `0`). An auto-increment key is exempt: a missing value takes the next id;
- at `validation: "strict"`, **no value for any NOT NULL column**. At `"coerce"` (the default) such a cell is stored as the type's
  default (`0`, `""`).

The message names the column, the frame and the row (`details`: `frame=…, row=…, table=…, column=…`). A JSON column-array body is
checked the same way. Key uniqueness is checked at the commit, and only at `"strict"` (`409 BULK_LOAD_DUPLICATE_PK`).

#### A job's frames are numbered (**Lead S21a, 0.6.0**)

(**Lead S21a, 0.6.0; breaking**) A job's frames are numbered **across all its `:append` bodies**, from 0: a body's first frame
carries the job's next number, not 0 (a JSON column-array body is one frame and carries its number as `seq`). The server applies
the frame numbered `next`, and:

- **a frame below `next` is acknowledged and not applied again** — so a body sent again after its answer was lost, or after its
  connection dropped part-way, loads each row once. The response's `framesSkipped` counts them;
- **a frame above `next` is refused** `409 BULK_LOAD_CURSOR_MISMATCH` (*Frame 5 of bulk-load job '…' arrived where frame 3 is
  next …*), nothing of the body applied;
- **a frame is applied whole or not at all.** A frame over `maxRowsPerAppend` rows, or a multi-table frame with one row that cannot
  be routed, is refused with none of its rows queued (the frames before it in the body stay applied).

So `nextSequence` is always a frame boundary, and it is the resume point: in the `:begin` response (a reconnect with the job's
idempotency key, which also stops a stale `:append` still reading a cut body), in every `:append` response and refusal (`details:
nextSequence=N`), and in [`GET {jobId}`](#get-jobid). **To recover a failed `:append`**: `:begin` again with the same key, then send
the same body again — or only its frames from `nextSequence` on. The C# SDK does this itself (a bounded number of times), where it
used to give up and hand the caller the key; so does `@aouda/client` (**Lead S22, 0.6.0**), where it left the failure to the
caller. A `:commit` may name the frames it sent (`nextSequence`) and is then refused unless the
job applied exactly those. An end frame still takes the number after its body's last data frame, which is also the next body's
first.

#### A body that commits its job (**Lead S21b, 0.6.0**)

A column-batch body may end the job's rows and commit the job in one request: its **end frame carries `commit`**, an object of the
[`:commit`](#post-jobidcommit) options — `waitForDeferredWork`, `writeConcern`, `writeConcernTimeoutMs`, `mqWaitMs`, each optional
(`{}` takes every default):

```json
{"rowCount": 50000, "status": "ok", "commit": {"mqWaitMs": 0}}
```

Its frames are applied as any body's are, then the job commits, and **the response is the `:commit` response** — the same fields,
the same errors. The job's rows end the moment the body has been read, so its segments are finalized and synced while the client is
already sending its next job; only the commit point waits for the jobs before it on the same tables. Use it for the last body of
every job: it saves the `:commit` round trip and lets the next job overlap this one's commit. Three rules:

- **The end frame's number is the job's frame count.** If the job holds more frames than the body's end frame names (an older body
  sent again with `commit`), nothing is committed: `409 BULK_LOAD_CURSOR_MISMATCH`, `details` naming `nextSequence`. A body of only
  an end frame (`rowCount: 0`, numbered `nextSequence`) commits what the job holds.
- **A bad option commits nothing**: `400 BULK_LOAD_INVALID_OPTIONS`, the body's frames applied and the job still open.
- **Sent again after its answer was lost**, the body is safe: a frame below `nextSequence` is skipped, so if the job had not yet
  read the end frame it commits once with every row once; if it is committing, the body is refused `409 BULK_LOAD_INVALID_STATE`
  with `details: state=Committing` — wait and ask again; once it has committed, a `:begin` with the job's idempotency key replays it
  (`alreadyCompleted`, its `token`). A body refused `state=Deferred` (the job committed and its deferred work is running) or
  `state=Completed` is past its commit point too: its rows are durable — wait, then `:begin` with the key, exactly as for
  `Committing`; never treat it as a failure, and never `:abort` it (**Lead group 5 review, 0.6.0**). Both SDKs do all of this
  themselves (`@aouda/client` from **Lead S22, 0.6.0**).
- **A job still queued behind another load does not commit in its body** (**Lead group 5 review, 0.6.0**): if the job does
  not hold its tables yet — another job's rows are streaming into them, or it is waiting for the job it follows — the commit is
  declined `409 BULK_LOAD_COMMIT_QUEUED`, the body's frames applied (`details` name `nextSequence` and `rowsAppended`) and nothing
  committed. Send [`:commit`](#post-jobidcommit) for the job, and no row again. A commit in a body holds the body's `:append` lane
  permit until it answers; one that waited for another job's rows held a permit that job's next body needed, and four of them
  stalled every loader on the server until the lock timeout. A job just begun is given a moment (1 s) to take its tables before it
  is declined. Both SDKs send `:commit` themselves.

A JSON column-array body cannot commit its job: one that carries `commit` is refused `400 INVALID_REQUEST`, nothing appended; send
it, then `:commit`. A body that commits holds its place on the `:append` lane until its commit answers (see
`Aouda:BulkLoad:MaxConcurrentStreamingRequests`); it waits there only for the jobs before it that are past their rows' end, since a
job that does not hold its tables is declined (above).

**Content-Type:** `application/vnd.aouda.column-batch-v2` (column-batch frames, then an end frame; layout below), or
`application/json` — **one** body of [column arrays](#column-arrays-the-write-body), `{"columns": […], "data": [[…], …], "absent"?: {…}}`
(**Lead S12, 0.6.0**). The retired `application/vnd.aouda.column-batch` is refused `415 FRAME_VERSION_UNSUPPORTED` (**Lead S09,
0.6.0**).

(**Lead S12, 0.6.0; breaking**) **NDJSON is gone.** A body sent as `application/x-ndjson` (one row object per line) is refused
`415 ROW_OBJECTS_UNSUPPORTED` and nothing is appended. Send the same rows as one JSON column-array body instead: it carries what
only NDJSON could before — a vector, a nested value, a column whose rows disagree on type — and it is read by the same reader as every
other write body. A JSON body is one batch: it is decoded whole before any row of it is queued, so a body that is not valid column
arrays appends nothing (`400 INVALID_REQUEST`, or `400 ROW_OBJECTS_UNSUPPORTED` for a body with `rows`). `maxRowsPerAppend` counts
its rows. (**Lead S21a, 0.6.0; breaking**) It is one frame of its job and carries its number: `"seq": N` beside `columns`
and `data` (`0` for a job's first body). A body without `seq` is refused `400 INVALID_REQUEST` and nothing is appended.

When the session was begun with more than one table, each row must name its destination in a **`_table` column**: a
multi-table body carries `_table` in `columns`, with each row's table name in its slot. The `_table` column is stripped before
inserting. A row whose `_table` is missing (absent or `null`) or names a table outside the job is refused
`400 BULK_LOAD_MISSING_DISCRIMINATOR`: *Row {n} of frame {f} is missing the '_table' discriminator …* or *… references table
'{t}' which is not in this job's table set …*, with `details: frame={f}, row={n}, …` (the row 1-based within its frame). (**Lead
S21a, 0.6.0**) None of that frame's rows is applied — the rows before it in the frame were queued and credited until this
train — and the frames before it stay applied (**Lead S12, 0.6.0**: the message said "Row at line N", with `lineNumber=N`).

#### The column-batch frame (`ACB2`)

(**IngestAtSpeed S09, 0.1.40**; version 2, `ACB2`, since **Lead S09, 0.6.0**.) A binary, column-major body the SDKs send
when `:begin` lists `"column-batch-v2"`, and the body of [`POST …/rows`](#post-apidatabasesdbtablesnamerows)
and of a [frame query response](#post-apidatabasesdbquery). It carries the same rows, and the server loads the same values from
it, without parsing one JSON document per row. **A body is its data frames, then exactly one end frame.** All integers are
little-endian.

```
frame   := "ACB2" kind:u8 seq:u64 body
kind 0  := data   body := rowCount:u32 columnCount:u16 column*
kind 1  := end    body := length:u32 payload:utf8-json[length]   (at most 1 MiB)
column  := nameLen:u16 name:utf8 kind:u8 flags:u8 [nulls:bitmap] [absent:bitmap] values
flags   := bit 0: a null bitmap follows · bit 1: an absent bitmap follows
bitmap  := ceil(rowCount / 8) bytes, bit i = row i (least significant bit first)
kind    := 0 Null (no values) · 1 Int64 · 2 Double · 3 Bool · 4 String · 5 Timestamp · 8 ScaledDecimal   (6: retired, refused)
values  := Int64, Timestamp : rowCount × i64   (Timestamp: 100-ns ticks since 1970-01-01T00:00:00Z)
         | Double          : rowCount × f64
         | Bool            : bitmap
         | ScaledDecimal   : scale:u8 (≤ 18), then rowCount × i64 — each value v / 10^scale (ColumnarCore S13)
         | String          : dictCount:u32, then dictCount × (len:u32 utf8), then rowCount × u32 codes
```

- **The sequence and the end frame** (**Lead S09, 0.6.0**). Every frame carries `seq`, its number in the body: 0, 1, 2, …
  with no gap or repeat; the end frame takes the number after the last data frame. (**Lead S21a, 0.6.0**) In a bulk load the
  numbers run across the job's bodies, so a body starts at the job's next number ([above](#a-jobs-frames-are-numbered-lead-s21a-060));
  a gap or a repeat *inside* a body is still refused. The end frame's payload is a JSON object:
  `rowCount` (the data frames' rows, checked), `status` (`"ok"`, or `"error"` with `error: { code, message, status }`), and on a
  query response `stats`, `totalMatches` and `warnings`. A request body's end frame is `{"rowCount":N,"status":"ok"}`; a bulk load's
  may add `commit` (**Lead S21b, 0.6.0**: [a body that commits its job](#a-body-that-commits-its-job-lead-s21b-060)). A body that
  ends without an end frame, has bytes after it, carries a frame out of sequence, counts other rows than its frames, or holds an
  unknown frame kind is refused `400 INVALID_REQUEST`, naming what was wrong; so is a request body whose end frame reports an error.
  A body may hold no data frame — one end frame with `rowCount: 0`. ⚠️ **On `:append`, "refused" keeps the frames before the
  fault** (**Lead group 2 review, 0.6.0**: said so): each data frame is queued as it is read, and the rows queued before the
  error stay credited, as for every `:append` that ends in an error. The error's `details` name them (`rowsAppended=N,
  nextSequence=M`). (**Lead S21a, 0.6.0**) Sending the body again is safe — its frames below `nextSequence` are skipped — but
  a body refused for its own content is refused again: fix the frame first. `/rows` is all or nothing and inserts nothing from a
  refused body.
- **`ACB1` is refused by name** (**Lead S09, 0.6.0; breaking**). The version before (`"ACB1" rowCount:u32 columnCount:u16
  column*`, frames back to back, the body ending where the stream ended) and its media type `application/vnd.aouda.column-batch`
  are answered `415 FRAME_VERSION_UNSUPPORTED`: `ACB1 frames are no longer read; this server reads ACB2
  (application/vnd.aouda.column-batch-v2).` Nothing of the request is applied. The column layout inside a data frame is
  unchanged.
- **Absent is not null.** A row whose bit is set in the absent bitmap does not have the column at all,
  exactly like a row listed in a JSON body's `absent`: an absent auto-increment key is allocated. A row in the
  null bitmap has the column with a `null` value. Absent and null rows still occupy their slot.
- **Strings are dictionary-encoded per frame**: each distinct value once, then one code per row.
- **Limits:** 1,000,000 rows and 4,096 columns per frame; a name that is empty or longer than 1,024
  UTF-8 bytes; a string up to 16 MB; a timestamp outside what a `DateTime` holds; or a frame that would
  decode to more than 256 MB (a boolean column decodes to a byte per row) (**BatchFirst S03, 0.1.40**:
  the last two, and the C# SDK no longer writes a name or string the reader refuses).
  `maxRowsPerAppend` is the most rows of one frame (**Lead S21a, 0.6.0**: it applied across all the frames of one `:append`).
- A malformed frame is refused with `400` and code `INVALID_REQUEST`, naming what was wrong. Rows from
  earlier, well-formed frames in the same body are kept and counted, and `nextSequence` names the first frame not applied.
- (**LoadSpeed S13, 0.4.0; breaking**) **Kind 6, the 128-bit `Decimal`, is retired.** It was
  `rowCount × 4 × i32` in the .NET decimal layout. A frame that carries it — on `:append` or on
  `POST …/tables/{name}/rows` — is refused `400`: `Column '<name>': kind 6, the 128-bit Decimal, is retired
  (LoadSpeed S13); send a decimal as ScaledDecimal (kind 8).` Send decimals as `ScaledDecimal`: 64-bit
  unscaled integers and one scale per column.

**A frame loads the same values as the JSON column-array body of the same rows** (the NDJSON body, until **Lead S12, 0.6.0**). Decimals travel as the `ScaledDecimal` kind — what a `Decimal(p,s)` column stores (**ColumnarCore S13, 0.2.0**). (**LoadSpeed S13, 0.4.0**) It is the only decimal kind: up to 0.3.x a decimal could also travel as the 16-byte `Decimal` kind (6), which the C# SDK sent for a .NET `decimal`. Both SDKs send a decimal column that fits 64 bits at its largest scale as `ScaledDecimal`, and the C# SDK, like the server's JSON reader, reads a JSON fraction's text straight into that kind at the scale it is written with; a column that does not fit goes as JSON (NDJSON before **Lead S12**). A frame carries **one scale per decimal column**, its largest: a value at a smaller scale is scaled up exactly, and a value with more places than the target column's scale is refused, as in JSON. A number a frame sends into a `String` column is stored at that scale (`2.50` stays `2.50`; `3` beside `2.50` becomes `3.00`). A caller building a `ColumnBatch` can add a scaled column directly (`ColumnBatchBuilder.SetScaledDecimal`). The C# SDK sends frames to a server that advertises them and NDJSON otherwise; the TypeScript SDK does the same from its next release (earlier releases send NDJSON). (**Lead S12, 0.6.0**) Both SDKs of this train send what a frame cannot carry as a JSON column-array body instead of NDJSON (`@aouda/client` from **Lead S14**); an older client's NDJSON is refused by this server. The C# SDK gives every number the kind its JSON text would take on the server (an integral number is an integer, a fractional one a decimal, one past decimal's range a double), sends a `DateTime` that is not UTC and every `DateTimeOffset` as its JSON text, and sends a row as JSON (NDJSON before **Lead S12**) rather than put in a frame a value the frame would change (an integer past 2^53 in a column that has become double) (**BatchFirst S03, 0.1.40** — before, a double loaded into a decimal column rounded to 15 digits, a `float` was widened, and a timestamp loaded into a text column took the server's culture format). The TypeScript SDK's frame writer follows the same rule: a JavaScript number goes as the kind its JSON text takes (an integer as an integer, a fraction as a decimal, digit for digit), and a batch holding one it cannot write that way (exponent notation, an integer only an unsigned 64-bit value holds) goes as NDJSON — from **Lead S14, 0.6.0**, as a JSON column-array body, since a server of **Lead S12** onwards refuses NDJSON (**BL-704, 0.2.0** — before, a fraction went as a double, which a decimal column could store differently).

**JSON column arrays** are the body for curl and for any client without the frame (**Lead S12, 0.6.0**; NDJSON was, until
this train). The server decodes them straight into a column batch, as it does a frame. A column whose rows mix integers and
fractions is read as decimal for every row.

**Example (single table):**
```
POST /api/databases/my_db/bulk-load/blj_abc123:append
Content-Type: application/json

{
  "seq": 0,
  "columns": ["sensor_id", "value", "recorded_at"],
  "data": [
    [1, 2],
    [98.6, 72.1],
    ["2026-05-22T09:00:01Z", "2026-05-22T09:00:01Z"]
  ]
}
```

**Example (multi-table, a `_table` column required):** a column only one table has is `absent` in the other table's rows.
```
{
  "seq": 0,
  "columns": ["_table", "id", "type", "event_id", "browser"],
  "data": [
    ["events", "event_meta"],
    [1, null],
    ["click", null],
    [null, 1],
    [null, "Chrome"]
  ],
  "absent": { "id": [1], "type": [1], "event_id": [0], "browser": [0] }
}
```

**Response body:**

| Field | Type | Description |
|---|---|---|
| `rowsAppended` | number | Rows accepted in **this** append call. Not necessarily durable yet. |
| `framesSkipped` | number | (**Lead S21a, 0.6.0**) Frames of this body below the job's next number: applied by an earlier body, acknowledged and not applied again. |
| `nextSequence` | number | (**Lead S21a, 0.6.0**) The job's next frame once this body was read; every frame below it is applied. |
| `rowsAppendedToBuffer` | number | Cumulative rows accepted into the session buffer since `:begin`. Not necessarily durable (lost on server crash before sealing). |
| `rowsDurablyCommitted` | number | Cumulative rows sealed into segments so far in this session. **Not durable until `:commit` returns**: a server crash before the job commits discards the whole job, these rows included, and the job's idempotency key then loads afresh (**Lead S20b, 0.6.0**: this said "what a crash cannot take away", which no build has done). **Not the resume offset** (**Lead S14, 0.6.0**: this said it was): after a reconnect, send the same `:begin` with the same idempotency key and resume from its `nextSequence` (**Lead S21a, 0.6.0**; it was the cursor's `resumeFromRow`) — see the `:begin` response above. |
| `acceptedAtUtc` | string | ISO 8601 UTC timestamp. |
| `segmentsSealedSoFar` | number | Segments sealed across all tables in this job so far. |

**Errors:**

| Code | Status | When |
|---|---|---|
| `BULK_LOAD_JOB_NOT_FOUND` | 404 | `jobId` not found or session expired. |
| `BULK_LOAD_INVALID_STATE` | 409 | Job is not in `"appending"` state. |
| `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` | 503 | (**WorkloadCore S16, 0.3.0**) The job's load already failed for capacity — for example its memory wait ran out after `:begin` returned. `Retry-After` is set; it is what `:commit` would answer (it used to be a 409 asking for `:commit`). |
| `MEMORY_BUDGET_EXCEEDED` | 503 | (**BL-831, 0.3.0**) A column-batch body could not get the memory to decode its next frame: each column's array is asked of the memory queue before it is allocated, waiting at most one sampling tick. The session stays open and the frames queued before the refusal stay credited: wait `Retry-After` and resume as on any reconnect (the same `:begin`, from its `nextSequence` — **Lead S21a, 0.6.0**; it was `resumeFromRow`). It used to fail on the heap mid-frame and answer `500`. |
| `BULK_LOAD_MISSING_DISCRIMINATOR` | 400 | Multi-table job and a row is missing `_table`, or names a table outside the job; none of its frame's rows is applied (**Lead S21a, 0.6.0**). `details: frame={f}, row={n}, …` (**Lead S12, 0.6.0**: was `lineNumber=N`). |
| `ROW_OBJECTS_UNSUPPORTED` | 415 / 400 | (**Lead S12, 0.6.0**) `415`: an NDJSON body (`application/x-ndjson`), no longer read. `400`: a JSON body that carries `rows`. Nothing is appended. Send frames or [column arrays](#column-arrays-the-write-body). |
| `INVALID_REQUEST` | 400 | A JSON body that is not valid column arrays (it appends nothing), or a malformed frame (the frames before it stay credited). |
| `BULK_LOAD_CURSOR_MISMATCH` | 409 | (**Lead S21a, 0.6.0**) The body's first frame is above the job's next number: frames between them were never applied. Nothing of the body is applied; `details` name `nextSequence`. (It was documented as "resumed below `rowsDurablyCommitted`", which no server answered.) (**Lead S21b, 0.6.0**) Also a body whose end frame commits and names fewer frames than the job holds: nothing committed. |
| `BULK_LOAD_INVALID_STATE` | 409 | The job is committing, committed, aborted or failed. (**Lead S21b, 0.6.0**) `details` name the state (`state=Committing`, …): a body sent again while its own commit runs reads `Committing` — wait, then `:begin` with the job's key. |
| `BULK_LOAD_PREDECESSOR_NOT_COMMITTED` | 409 | (**Lead S21b, 0.6.0**) A body that commits a job begun with `afterJobId`: the job it follows failed or was aborted, so this one is not committed and none of its rows is loaded. `details` name `afterJobId`. Also answered by `:commit`. |
| `BULK_LOAD_COMMIT_QUEUED` | 409 | (**Lead group 5 review, 0.6.0**) A body whose end frame commits its job, for a job still queued behind another load on its tables: the body's frames were applied (`details`: `nextSequence`, `rowsAppended`), nothing was committed, and the job is open. Send `:commit`; send no row again. |
| `BULK_LOAD_LOST` | — | (**Lead S30, 0.6.0**) Not a response's status: the `errorCode` of a job `GET {jobId}` reports `"lost"` — answered `accepted` by `:commit` (`wait: "accepted"`), then lost before its commit point. Nothing of it is durable; load it again. (**Lead S26c, 0.6.0**) Also an `"os"` job dropped at the open after a power loss (`durability: "os"`): load it again with the same idempotency key. |
| `FRAME_VERSION_UNSUPPORTED` | 415 | (**Lead S09, 0.6.0**) An `ACB1` body, or the retired `application/vnd.aouda.column-batch` type. Nothing is queued. Upgrade the client. |

---

### `POST {jobId}:commit`

Commit the session. All sealed segments become queryable. (**Lead S21b, 0.6.0**) A job whose last body is column-batch frames
can [commit in that body's end frame](#a-body-that-commits-its-job-lead-s21b-060) instead, with the same options and the same
answer; `:commit` is for a job whose last rows went as JSON, a resumed job whose bodies the server already holds, or an empty job.
A job begun with `afterJobId` is refused here too, `409 BULK_LOAD_PREDECESSOR_NOT_COMMITTED`, if the job it follows did not commit.

(**Lead S30, 0.6.0**) **`wait: "accepted"` answers before the commit point.** By default `:commit` answers once the job is
committed. With `wait: "accepted"` it answers once the job's rows have ended and it holds its place in its tables' commit order — its
commit then runs on without the caller. That answer says `state: "accepted"`, and **the job is not durable yet and may be lost**: if
the server stops before the job's commit point, or its commit fails, nothing of it is kept. `accepted` never means committed:

- The answer carries the job's `rowsLoaded`, `tables` and a `token`. A read presenting that token **waits until the job is visible**
  (on the primary, for a materialized query over the loading tables, and on a replica), so a client that reads its own load with the
  token never reads it half there. `committedAtUtc` is `null`, `perTableRowCounts` is empty, `segmentsCreated` is `0`,
  `writeConcernAchieved` is `"none"` and `mqStatus` is `"behind"`.
- **The outcome comes from [`GET {jobId}`](#get-jobid)**: `state` is `"accepted"` while the commit runs, then `"completed"` (with the
  job's rows and commit `token`) or `"lost"` (`errorCode` `BULK_LOAD_LOST`) — or, for a `validation: "strict"` job whose commit
  found a duplicate key, `"failed"` with `errorCode` `BULK_LOAD_DUPLICATE_PK` (**BL-1163, 0.6.0**: it read `"lost"`). Ask with
  `waitMs` to be answered when it settles. After a
  restart that cut the job off, `GET {jobId}` answers `"lost"`; once the server's log has moved past the job (a checkpoint), it answers
  `404 BULK_LOAD_JOB_NOT_FOUND`, which for an accepted job means the same thing: nothing of it is durable, load it again. ⚠️ That
  holds only while the job is recent: the server keeps a committed job's record for at least an hour after its commit (or
  `Aouda:BulkLoad:IdempotencyWindowMinutes`, if longer), and may forget it after that, so a `404` asked later cannot tell a lost job
  from a committed one. Ask for the outcome as soon as you have the accepted answer; both SDKs ask when you first read it, so read
  it promptly. A job that passed its commit point is never answered `"lost"`, even when work after it failed (**Lead group 7
  review, 0.6.0**). Don't infer the outcome from the token: a lost job's token reads as covered once the log moves past it, and
  its rows are not there.
- **"Accepted" frees the loader, not the table.** A write into a table the job loads still waits for the job, as it does for any load.
- A job the server cannot accept — one that writes no closing log frame, or a database without a WAL — is answered when committed,
  `state: "committed"`: a stronger answer than asked for, never a weaker one.
- It is not combined with `waitForDeferredWork: true`, `mqWaitMs` above `0` or a `writeConcern` other than `"acknowledged"`, which
  each wait for the commit: those are refused `400 BULK_LOAD_INVALID_OPTIONS`, nothing committed. Both SDKs expose it
  (`BulkLoadOptions.CommitWait = Accepted` / `commitWait: "accepted"`): an accepted handle, and an outcome that completes at the
  job's outcome.

**Request body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `database` | string | Yes | — | Database name. |
| `jobId` | string | Yes | — | Job identifier (also in the path). |
| `nextSequence` | number? | No | — | (**Lead S21a, 0.6.0**) The frames this client sent (the number after its last). When given, the commit is refused `409 BULK_LOAD_CURSOR_MISMATCH` — nothing committed, the job still open — unless the job applied exactly these; `details` name the job's `nextSequence`. Omitted: the job commits what it applied. Both SDKs send it (`@aouda/client` from **Lead S22, 0.6.0**). |
| `waitForDeferredWork` | bool | No | `false` | If `true`, the response is held until all post-processing (PK index rebuild, CSC mirror, RaBitQ encodings) completes. |
| `writeConcern` | string? | No | `"acknowledged"` | Replication barrier. Allowed: `"acknowledged"`, `"majority"`, `"all"`. |
| `writeConcernTimeoutMs` | number? | No | `300000` (5 min) | Max wait for the write-concern barrier. On timeout, returns 200 OK with `writeConcernTimedOut: true`. The data is durable; replicas catch up at their own pace. |
| `mqWaitMs` | number? | No | `0` (**LoadSpeed M.2, 0.4.0**; `30000` in 0.3.0) | (**WorkloadCore S09, 0.3.0**) How long `:commit` waits, after the load is durable and its table locks are released, for every materialized query the load's rows reach to be current for the load. `0` = do not wait. `0`–`600000`; outside that, `400 BULK_LOAD_INVALID_OPTIONS`, checked before anything is committed. The answer is `mqStatus` below. |
| `wait` | string? | No | `"visible"` | (**Lead S30, 0.6.0**) `"visible"`: answered once the job is committed. `"accepted"`: answered once the job is accepted, before its commit point — not durable yet (see above). Any other value is refused `400 BULK_LOAD_INVALID_OPTIONS`. Also taken by a body's end frame that commits its job. |

**Response body:**

| Field | Type | Description |
|---|---|---|
| `jobId` | string | Echo of job ID. |
| `state` | string | (**Lead S30, 0.6.0**) `"committed"`: the job is committed, and the fields below are its result. `"accepted"` (only with `wait: "accepted"`): its rows have ended and its commit is running — **not durable yet**; its outcome comes from `GET {jobId}`. |
| `tables` | string[] | Tables involved in the load. |
| `rowsLoaded` | number | Total rows the job loaded across all tables: durably committed when `state` is `"committed"`. When it is `"accepted"` (**Lead S30, 0.6.0**), the rows the job took, **not durable yet**: its outcome (`GET {jobId}`) says whether they are. |
| `expiredRows` | number? | (**Horizon, 0.5.0**) Rows the load sent that were left out because their time lay below their table's [retention](../guides/retention.md) horizon, or was an explicit `null` — accepted, never written, never visible, not in `rowsLoaded`. **Omitted when 0.** Such a table is loaded one segment per time slice and never spilled ([Bulk Load](../guides/bulk-load.md#loading-a-table-with-retention)). |
| `perTableRowCounts` | object | Per-table row counts (`{ tableName: count }`). Always present. |
| `segmentsCreated` | number | Total segments created. |
| `committedAtUtc` | string? | ISO 8601 UTC commit timestamp; `null` in an `accepted` answer (**Lead S30, 0.6.0**). (**Lead S20a, 0.6.0**) The time of the job's commit record — its closing `BulkLoadCommitted` frame's when it wrote one, else the catalog record that published its segments — not the time the response was written. |
| `deferredWorkCompleted` | boolean | Whether deferred work completed before this response was sent. |
| `token` | string | Commit consistency token of the closing `BulkLoadCommitted` frame (42-hex). Replaces the former `walPosition` number. Replicas that have applied this token have the complete load (**Lead S18a, 0.6.0**: a replica now covers it only once every segment is fetched; see `bulkLoadHold` on [`GET /admin/replication/status`](#get-adminreplicationstatus)). (**WorkloadCore S09, 0.3.0**) On a single node, where a load writes no closing frame, it is the WAL head at the load's commit (it used to carry position 0): a read with it requires the load, and so waits for the load's materialized queries. (**Lead S20a, 0.6.0**) What the token names, exactly: a position at which this node already shows the load — the closing frame's when the load wrote one, else the WAL head read at the commit point, else position 0 on a database without a WAL (covered at once). It is kept in the job's commit record, so a replayed `:begin` returns the same token. |
| `durability` | string | (**Lead S26c, 0.6.0**) The job's level, `"strict"` or `"os"`. Always present, an `accepted` answer included. |
| `validation` | string? | (**Lead S27a, 0.6.0**) The validation the job was checked at, `"coerce"` or `"strict"`. |
| `writeConcernRequested` | string | Echo of `writeConcern` from request. |
| `writeConcernAchieved` | string | Strongest write concern achieved before return. May be weaker than `writeConcernRequested` if `writeConcernTimedOut`. |
| `writeConcernTimedOut` | boolean | `true` when requested write concern was not satisfied within the timeout. The load is still durable. |
| `progress` | object? | Present only when `waitForDeferredWork: true`. Fields: `ivfAssignmentsCompleted`, `ivfAssignmentsTotal`, `raBitQEncodingsCompleted`, `raBitQEncodingsTotal`, `cscMirrorsCompleted`, `cscMirrorsTotal`, `pkIndexRebuildCompleted`, `pkIndexRebuildTotal`. |
| `mqRebuildStatus` | string | **BL-419 (0.1.22).** Materialized Query rebuild status at the moment of commit — same allowed values and meaning as the `:status` field below. For an `"auto"` load that reaches any query it is `"pending"` or `"inProgress"`, never `"completed"` from the commit itself (**WorkloadCore S09, 0.3.0**); it was `"completed"` for an `"auto"` load whose queries were written in its own commit (**ColumnarCore S12, 0.2.0**). Poll `GET {jobId}:status` for this field rather than calling `:refresh`, which would queue behind the already-scheduled rebuild and then re-scan the whole source table a second time. |
| `mqStatus` | string | (**WorkloadCore S09, 0.3.0**) Whether the materialized queries the load's rows reach (over the loaded tables, and every query built on them) were current for the load when `:commit` returned: `"current"` all of them were, within `mqWaitMs`; `"behind"` the wait ended first, and their maintenance is still running — or (**WorkloadCore S16, 0.3.0**) one of them can only be brought current by a rebuild (it is holed, in `Error`, or its rebuild is waiting for memory), which `:commit` does not wait for: it answers `"behind"` as soon as the others are current — (**release blockers, 0.3.0**) and so is a query that is behind only because a query it is built on is being rebuilt; and if the wait itself fails (the heap, say) the commit is still answered as committed, `"behind"`; `"skipped"` a `"skip"` load — the queries are behind until refreshed; `"none"` no query reads the loaded tables. (`"deferred"`, for a `"deferred"` load, until the 0.4.0: **LoadSpeed K31** folded that option into `"auto"`.) |
| `mqFrontierToken` | string? | (**WorkloadCore S09, 0.3.0**) The lowest frontier among the load's queries when `:commit` returned, as a consistency token: a read of those queries with it is served at once. Absent when the load reaches no query. |
| `mqWaitedMs` | number | (**WorkloadCore S09, 0.3.0**) How long `:commit` waited for the load's queries, in milliseconds. |

**`:commit` waits for the load's queries, bounded** (**WorkloadCore S09, 0.3.0**). After the load is durable and its table locks are released,
`:commit` waits up to `mqWaitMs` for the load's materialized queries to be current for it, then answers either way.
(**LoadSpeed M.2, 0.4.0**) **By default it does not wait:** `mqWaitMs` omitted is `0`, so a load whose queries are still
catching up answers `mqStatus: "behind"` at once; send `mqWaitMs` to wait (it was 30 s by default in 0.3.0). The wait
holds no lock and refuses nothing: the load is durable whatever `mqStatus` says, and `"behind"` is not an error. To read the
queries current, read with the commit's `token` (which waits for them, as for any write), or wait on `mqRebuildStatus`.


**Errors** (**WorkloadCore, 0.3.0**):

| Code | Status | When |
|---|---|---|
| `BULK_LOAD_DUPLICATE_PK` | 409 | (**Lead S27a, 0.6.0**) A job at `validation: "strict"` holds a primary key twice, or one the table already holds. Nothing of it was committed; the message names the table and the key, and `details` is `{"table", "sampleKeys", "totalDuplicateCount", "withinJob"}` (the check stops at the first key). Deduplicate the source and load it again, load at `"coerce"`, or upsert the rows. The check waits for the writes that were in flight on the table when the job began to commit, so an insert racing the load and the load never both write one key. |
| `INVALID_REQUEST` | 400 | (**Lead S27a, 0.6.0**) A row the engine refused (a column the table does not have, a missing key): the same rule as `:append`'s frame check, for a row that reached the engine another way. Nothing committed. |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The engine refused memory for the load's commit; or (**WorkloadCore S07, 0.3.0**) the load waited its lock-acquisition timeout for its memory before it started — a load asks for its memory before it takes its tables' locks, so a load waiting for memory no longer holds up inserts into them; or the commit's segment write hit the managed heap's hard limit — (**BL-831 / BL-928, 0.3.0**) the spill merge included: a merge that runs out of memory is refused and nothing is applied, never published as a misaligned segment (it answered `500`). `Retry-After` is set. |
| `WAL_CAPACITY_EXCEEDED` | 503 | The WAL reached its refusal line (`T27`) during the commit. `Retry-After` is set — (**WorkloadCore S16, 0.3.0**) to the server's estimate of when the log will be back under `T26`, from the rate it has been freeing log (1–300 s), not a constant 1 s. (**BL-956, 0.4.0**) At most **30 s** (half of the 60 s a bulk-load request may be refused in a row), and `10` before any rate is measured — it was the time between periodic checkpoints, 300 s by default. |

The session is **failed** either way: the engine has aborted the load, and `GET {jobId}` shows `state: "failed"` with the
same `errorCode`. A repeated `:commit` of that job answers the same 503 rather than a 409. Wait `Retry-After`, then run the
load again from `:begin`. Before this change both refusals answered **500 `INTERNAL_ERROR`** with no `Retry-After`.

⚠️ **A failure after the load's commit point is never a 503** (**WorkloadCore, 0.3.0**). Once a load's rows are durable,
whatever fails after that — the managed heap included — answers **500 `INTERNAL_ERROR`** with the message *"Bulk-load committed,
but work after its commit point failed. The rows are durable: do not send the load again."* and no `Retry-After`. Do not run that
load again: its rows are in the table, and a second load would add them twice.

---

### `GET {jobId}`

_The route is `GET /api/databases/{db}/bulk-load/{jobId}` (no `:status` suffix)._

Get current session state and progress.

(**Lead S30, 0.6.0**) **Query parameter `waitMs`** (`0`–`60000`, default `0`; outside that `400 BULK_LOAD_INVALID_OPTIONS`):
for a job whose commit is running — `committing`, or `accepted` — the answer waits up to that long for the job to settle (committed,
failed, lost or aborted), then answers as it stands. This is how a client learns an accepted job's outcome without polling.

**Response body:**

| Field | Type | Description |
|---|---|---|
| `jobId` | string | Job identifier. |
| `tables` | string[] | Tables being loaded. |
| `state` | string | Current state. Allowed values: `"acquired"`, `"appending"`, `"committing"`, `"deferred"`, `"completed"`, `"failed"`, `"aborted"`; (**Lead S30, 0.6.0**) `"accepted"` — answered `accepted` by `:commit`, its commit running, not durable yet — and `"lost"` — accepted, then lost before its commit point (the server stopped, or its commit failed): nothing of it is durable, `errorCode` is `BULK_LOAD_LOST`. A restart that cut an accepted job off answers `"lost"` for it while the server's log still holds the job. (**Lead S26c, 0.6.0**) `"lost"` is also an `"os"` job dropped at the open after a power loss — its files did not match the length and xxHash128 its commit record names — answered with `durability: "os"`; its idempotency key no longer names a commit, so a `:begin` with the same key loads it again. |
| `durability` | string? | (**Lead S26c, 0.6.0**) The job's level, `"strict"` or `"os"`. Omitted when unknown — an accepted job lost before its commit point. |
| `validation` | string? | (**Lead S27a, 0.6.0**) The job's validation, `"coerce"` or `"strict"`. Omitted when the server no longer knows it (after a restart). |
| `token` | string? | (**Lead S30, 0.6.0**) The job's commit token once `"completed"` (from its commit record after a restart too); the `accepted` answer's token while `"accepted"`. Absent otherwise. |
| `rowsAppendedToBuffer` | number | Rows in buffer (not yet durable). |
| `nextSequence` | number | (**Lead S21a, 0.6.0**) The job's next frame; every frame below it is applied. |
| `rowsDurablyCommitted` | number | Durably committed rows. |
| `segmentsSealed` | number | Segments sealed so far. |
| `startedAtUtc` | string | ISO 8601 session start time. |
| `lastUpdatedUtc` | string | ISO 8601 last state update time. |
| `progress` | object? | Deferred work progress. Same structure as in commit response. Null if no deferred work is in progress. |
| `replicas` | array | Per-replica fetch progress. Empty on single-node deployments. Each element has `serverId` (string), `segmentsFetched` (number), `segmentsTotal` (number), `lagSeconds` (number). |
| `mqRebuildStatus` | string? | Materialized Query rebuild status after commit. One of `"pending"`, `"inProgress"`, `"completed"`, `"skipped"`, `"failed"`, `"unknown"` (and `"deferred"` until the 0.4.0). Present when the job has committed; null or absent while still in `"appending"` state. `"skipped"` means `postLoadMqBehavior` was `"skip"` or there are no dependent materialized queries. **`"deferred"` (BatchFirst, 0.1.40; gone in the 0.4.0, LoadSpeed K31)** meant the load was `postLoadMqBehavior: "deferred"` and its job was pending the table's deferred pass. An `"auto"` load whose table is still loading is `"pending"` until the catch-up has brought it in (**LoadSpeed M.3**), and `"failed"` if a pass after its commit leaves it owed only by queries in `error` (their rebuild failed; they are retried, or `:refresh` them). **`"unknown"` (BL-419, 0.1.22)** is the answer for a job whose in-memory session is gone (e.g. after a server restart) and is reconstructed from the WAL alone (**Lead S20a, 0.6.0**: from the job's commit record, which keeps its rows past any checkpoint; an aborted job reads as not found after a restart, as an unknown one does) — neither records rebuild progress, so this value is **terminal**: it will not transition to another value for this job. Treat it like `"skipped"`/`"completed"` for polling purposes (stop), not like `"pending"`/`"inProgress"` (keep waiting). |
| `error` | string? | Human-readable error message. Set when `state = "failed"` or `"lost"`. |
| `errorCode` | string? | Error code when `state = "failed"` — `BULK_LOAD_DUPLICATE_PK` for an accepted strict job its commit refused (**BL-1163, 0.6.0**) — or `BULK_LOAD_LOST` when `"lost"`. |

---

### `GET :list`

List all sessions for this database.

**Response body:**

| Field | Type | Description |
|---|---|---|
| `database` | string | Database name. |
| `jobs` | array | Array of status objects (same structure as `:status` response). |
| `snapshotUtc` | string | UTC timestamp of this snapshot. |

---

### `POST {jobId}:force-abort`

Operator abort of an in-flight session. Releases table locks and records the abort reason in the WAL.

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `database` | string? | No | Database name (may also be in path). |
| `jobId` | string? | No | Job identifier (may also be in path). |
| `reason` | string | Yes | Operator-supplied reason, recorded in the WAL frame. |

**Response:** `200 OK` (no body).

**Errors:**

| Code | Status | When |
|---|---|---|
| `BULK_LOAD_JOB_NOT_FOUND` | 404 | Job not found. |
| `ALREADY_TERMINAL` | 409 | Job is already in a terminal state (`completed`, `aborted`, `failed`). |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-11 | Initial release |
| 1.1 | 2026-02-05 | Enhanced TableSummary (rowCount, createdAt, lastModifiedAt, sizeBytes), schema introspection endpoint, relationships endpoint, TypeScript generation endpoint, reference metadata in columns |
| 1.2 | 2026-02-06 | Data mutation endpoints: insert (POST), update (PATCH), delete (DELETE) for /api/tables/{name}/rows |
| 1.3 | 2026-03-19 | Comprehensive authentication section: credential types, auth enforcement flow, X-User-Token, server and app auth endpoint reference |
| 2.0 | 2026-05-22 | WebSocket streaming protocol documented; Bulk Load API documented; `crossPartitionAccess`, `joins`, WhereClause `groups`; write concern on mutation messages; Known Limitations updated; Future Extensions corrected |
| 2.1 | 2026-06-23 | P27: `setExpr` expression SET, `TRUNCATE`, DELETE `limit`/`orderBy`, `RETURNING`, batch mutations (`/rows/batch`), expression SELECT (`selectExpr`). P28: `TruncateToMinute` partition function. P31: `postLoadMqBehavior` on bulk-load `:begin`; `mqRebuildStatus` in `:status` response; `POST .../materialized-queries/{name}:refresh`. P33: password reset endpoints, MFA enroll/challenge/verify/factors/delete, admin password override, invite resend, `requiresPasswordChange`/`mfaRequired`/`mfaFactors`/`aal` in signin response. |
| 2.2 | 2026-07-31 | BL-130: `identityInsert` on `POST …/tables/{name}/rows`. BL-131: `options.identityInsert` on bulk-load `:begin` (commit-only counter floor). |
| 2.2 | 2026-06-26 | **P17 (breaking):** `GET /api/databases` default response now excludes internal infrastructure databases (`_serverauth`, `_settings`). Use `?include=internal` to retrieve the full catalog. All database responses now include `isInternal` (bool), `isAuthDatabase` (bool), and `authDatabaseKind` (`"none"` \| `"server"` \| `"application"`) metadata fields. Application auth databases (`isInternal: false`) remain in the default list. |
| 2.3 | 2026-08-19 | **P37 / server 0.1.7:** named-query execute + read-only batch (cap 32, one snapshot, positional errors); named-mutation execute; `mk_pub_*` + data-plane listener (404 not 403); WebSocket path `/api/databases/{db}/ws`; `subscribe.hash` / `args` / `conflate`; `snapshot_complete`; server `gap` (`last_seq`, `discarded`); `change.values_skipped`; `re_auth`; access-surface `?access=true`. Additive on the wire. |
| 2.4 | 2026-08-21 | **P38:** consistency token (`X-Aouda-Token` / `?at_least=` / envelope `token` / `GET …/token`); named-query alias `freshness`; `TOKEN_*` / `FRESHNESS_*` errors; stream `token` alongside `version`; bulk-load commit `walPosition` → `token`. **Breaking:** `MaxLagSeconds` is measured staleness, not lag-bytes ÷ 1 MB/s. Default read preference remains `Primary`. |
| 2.5 | 2026-08-22 | **BL-188:** named-query identity is the unique schema name. **Breaking:** `{name}` routes and batch/subscribe/warning `"name"`; alias surface (`?alias=`, `X-Aouda-Named-Query-Alias`, body `alias`) and `NAMED_QUERY_ALIAS_MISMATCH` retired; omitting a name deletes the definition; codegen is types-only (optional Args/Row). Historical 2.3 / 2.4 shipped content-hash identity. |
| 2.6 | 2026-08-29 | **Catalog GET/list auth linkage:** `auth.enabled` / `auth.database` on every database response (never `mk_*` on GET). GET `{name}` documented as metadata-only; 404 while `Dropping`. Health probe split (`/health` liveness vs `/ready` / GET `state=Active`). Create-role `permissions` optional; 400 `INVALID_REQUEST` with `suggestion`. |
| 2.7 | 2026-09-07 | **BL-406 (documentation only, no wire change):** bulk-load `:begin` options table gains `applyTransforms` / `preTransformed`, with the rule that a table carrying any write-time compute requires exactly one of them, and guidance on which to pick. Adds the bulk-load deadline, append-size and admission-lane settings (`Aouda:BulkLoad:StreamingRequestTimeoutMs`, `SessionIdleTimeoutMinutes`, `MaxConcurrentStreamingRequests`, `StreamingRequestQueueLimit`, `Aouda:MaxConnections: 0`) — **not yet released**: BL-404 / BL-405 are on `Unreleased` and ship in the **next** server train, after 0.1.20. |
| 2.8 | 2026-09-30 (0.2.0) | **ColumnarCore S06 / S13, BL-716 (additive on the wire):** `POST …/tables/{name}/rows` also accepts one column-batch frame (`Content-Type: application/vnd.aouda.column-batch`; database and table from the URL, `identityInsert` / `writeConcern` as query parameters), advertised by `Accept-Post: application/json, application/vnd.aouda.column-batch` on the endpoint's responses and by `features.insertColumnBatch` in `GET /admin/capabilities`; an older server answers a frame with `415`. Column-batch frames gain the `ScaledDecimal` kind (`8`). `Decimal` columns may declare `precision` / `scale` (`Decimal(p,s)`, `1 ≤ p ≤ 18`, `0 ≤ s ≤ p`) on create-table, add-column and column details. Insert errors: a body that is not valid JSON is `400 INVALID_REQUEST` (was MVC's validation problem), an empty body is `400 MISSING_DATABASE`; a string cell that is not valid UTF-8, or a non-finite `Double` in a frame, is a `400`. |
| 2.9 | 0.3.0 (ColumnarRead) | **Architecture review:** a join (ad hoc, `…/query/count` or a named query) needs the base table's grant on every joined table, and one onto a table the caller's RLS / PLS restricts is answered with that security applied on the joined side, not refused (BL-818; it was `403 AUTHORIZATION_DENIED` until ColumnarRead2 S05), with `joins[i].where` to filter the joined table; `Retry-After` is CORS-exposed; `stats.distinctServedFromPartitionMetadata` is no longer set; the frame response's JSON fallbacks, its abort after the headers and the decimal kind's choice documented. **ColumnarRead S18 (additive):** query responses' `stats` gain `routedTo` (the materialized query a routed read was answered from; omitted otherwise); `/query` and `/query/count` route to current materialized results. **ColumnarRead S16 (additive on the wire):** `QueryMessage` gains `aggregates` (`count`, `sum`, `min`, `max`, `avg`, `countDistinct`) and `groupBy` (columns and `Timestamp` buckets), answered as an ordinary query response. `POST …/query` and `POST …/named-queries/{name}/query` answer with column-batch frames when `Accept` lists `application/vnd.aouda.column-batch` (the envelope in `X-Aouda-Column-Types`, `X-Aouda-Row-Count`, `X-Aouda-Total-Matches`, `X-Aouda-Stats`, `X-Aouda-Warnings`), advertised by `features.queryColumnBatch`; both SDKs ask for it by default. JSON query bodies are written from the columns and streamed, with the same bytes. A non-finite floating-point cell in a JSON answer is a `500` before the first byte. |
| 2.10 | 0.3.0 (WorkloadCore) | **WorkloadCore S09:** materialized-query maintenance is off the commit — an insert's `200` and an `"auto"` load's `:commit` no longer wait for their queries to be written. Bulk-load `:commit` gains `mqWaitMs` (a bounded wait for the load's queries, default 30000) and answers `mqStatus`, `mqFrontierToken` and `mqWaitedMs`; `mqRebuildStatus` is never `"completed"` from the commit itself; a single-node load's `token` is the WAL head at its commit. **WorkloadCore S10:** every load but a `"skip"` one is a pending job brought in by the table's pass (`"auto"` starts it at the commit); the ingest-fed path is gone; a query owing a load reports `isStale: true`, `pendingDeferredJobs` ≥ 1 and `current: false` with a new `staleReason` wording, and is not selected by `staleOnly`; a rebuild refused memory waits for room instead of being retried on timers. No field added or removed. **WorkloadCore S17:** `GET /api/server/memory` loses `resourceMode`, `headroomRatio`, `resourceModeTransitions` and the `headroom` block (the resource mode is deleted); a memory refusal's `Retry-After` is the queue's estimate, or 10 s, never a constant 1 s. **Release blockers:** every endpoint answers a capacity refusal `503` + `Retry-After` (`MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`) and a write conflict `409 WRITE_CONFLICT` — some answered `400`, `409` or `500` before (BL-921, BL-881); the result ceiling is `400 RESULT_TOO_LARGE` with no `Retry-After` (it was `503`); a token refresh refused for capacity is `503` and keeps its token, and of two concurrent refreshes with one token exactly one succeeds (BL-841); a materialized-query create whose first build is refused for capacity answers `204` with the query behind (BL-884); bulk-load `:append` is refused `503` before it decodes when memory is short (BL-831). No field added or removed. |
| 2.11 | 0.4.0 (LoadSpeed) | **LoadSpeed M.2:** bulk-load `:commit`'s `mqWaitMs` defaults to `0` (it was `30000`) — a commit with queries answers `mqStatus: "behind"` at once unless the request asks to wait. No field added or removed. **LoadSpeed K31 (breaking):** `postLoadMqBehavior: "deferred"` is refused `400 BULK_LOAD_INVALID_OPTIONS` (use `"auto"`); `mqStatus` and `mqRebuildStatus` lose `"deferred"`. **LoadSpeed K5 (BL-980, BL-944; breaking):** `GET /api/tables` drops `rowCountIsExact` (`rowCount` is always exact) and always carries `createdAt` / `lastModifiedAt`; an aggregate materialized query whose `groupByColumns` are plain strings is `400`; an application database accepts only its URL issuer on access tokens; a point-in-time restore of a backup without a WAL-root incarnation fails at staging. Refusals: a refusal no other code names is `503 SERVICE_UNAVAILABLE` + `Retry-After`, `SERVER_STARTING` carries `Retry-After: 5`, a refused notification-provider `DELETE` is `503`, and a wrapped refusal on `POST …/materialized-queries/{name}/query` is `503` (or `400 RESULT_TOO_LARGE`), not `400 INVALID_REQUEST`. **LoadSpeed S13 (breaking):** `Decimal(p,s)` is the only decimal type — `"type": "Decimal"` without `precision` / `scale` is `400`, as is a precision above 18; a computed output's `type` and `cast`'s target spell it `"Decimal(p,s)"`; the column-batch frame's 128-bit `Decimal` kind (6) is deleted and refused `400`, and query results send a decimal column as `ScaledDecimal` at its declared scale; a decimal `sum` past 18 digits is refused in a query as in a materialized query. |
| 2.12 | 0.5.0 (Horizon) | **Horizon (additive on the wire):** materialized-query create takes `window` (`{ keep, column? }`) and the status reports `window` and `horizon`; `stats.windowCompletionRows` on `/query` and the MQ query endpoint; table create and `PUT …/policy` take `policy.retention` (`{ keep }`; a retention-only `PUT` needs no `storageTemperature`; it cannot be removed — an omitted or `null` `retention` leaves it as it is), and the policy detail and table detail report `retention` and `horizon`; insert, named-mutation insert / upsert and bulk-load `:commit` responses carry `expiredRows` (omitted when 0); a `DELETE …/rows` whose whole `where` is the first cluster column `lt` / `lte` a time runs as an early expiry (with retention) or a range delete (without); `snapshot_complete` gains `horizon` / `horizon_column` / `horizon_column_type`, and two server messages are added, `horizon` and `range_delete` (each with `column_type` on a `Date` column). A windowed result's subscription snapshot is its stored part. |
| 2.13 | 0.6.0 (Lead) | **Lead S09 (breaking on the wire):** the column-batch frame is `ACB2` (`application/vnd.aouda.column-batch-v2`, `:begin`'s `"column-batch-v2"`): every frame carries a kind and a sequence number, and every body ends with one end frame. A frame query response's row count, `stats`, `totalMatches` and `warnings` move from the `X-Aouda-Row-Count` / `-Stats` / `-Total-Matches` / `-Warnings` headers into the end frame, and an error after the response started is an error end frame rather than a cut connection. `ACB1` bodies and the old media type are refused `415 FRAME_VERSION_UNSUPPORTED`; a query asking only for the old type gets JSON. |
| 2.14 | 0.6.0 (Lead) | **Lead S12 (breaking on the wire): the REST API as column arrays.** Every JSON write body sends its rows as [column arrays](#column-arrays-the-write-body) — `columns`, `data` (one array per column), optional `absent` (per column, the rows whose cell is not given, which is not null) — on `POST …/tables/{name}/rows`, a branch insert, WebSocket `stream_rows`, a named mutation's `batchParam` argument and the schema seed / `aouda.seed.json`; a body with `rows` (row objects) is refused `400 ROW_OBJECTS_UNSUPPORTED` (new code). Bulk-load `:append` takes frames or one JSON column-array body; NDJSON is refused `415 ROW_OBJECTS_UNSUPPORTED`, `:begin`'s `acceptedAppendFormats` is `["column-batch-v2", "column-arrays"]`, and an unroutable multi-table row is named "Row {n} of this :append" with `details: row={n}`. Reads: the `format` query parameter is removed from `/query` and the named-query execute and batch routes (any `format=` is `400 INVALID_FORMAT`; results are always `{columns, types, data, rowCount, …}`); the materialized-query `POST …/{name}/query` answers `{columns, data, rowCount, stats, token}`; `generatedValues` is `{columns, data}` with one cell per request row; a WebSocket `snapshot` page is `{type, id, columns, data, version, token?}` (`snapshot_complete` and `change` unchanged); vector `:nearest` answers `{rowKeys, distances, executionMs, token}` and graph `:khop` `{nodeIds, hops, executionMs}`; the policy inspector's table and materialized-query `sample` is `{columns, data}`. **Pass-10 (documentation only):** the [graph and vector endpoints](#graph-and-vector-endpoints) are documented. |
