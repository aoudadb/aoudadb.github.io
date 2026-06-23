---
title: "HTTP API"
nav_order: 1
parent: "Reference"
---

# Aouda Wire Protocol v2

This document specifies the JSON-based wire protocol for Aouda client-server communication.

## Overview

- **Transport**: HTTP/1.1 and HTTP/2
- **Format**: JSON for all messages
- **Default Response Format**: Columnar JSON (50% smaller than row-based)
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
| `Authorization` | **Required when the target database has auth enabled** | `Bearer <token>` — JWT access token or API key (`mk_anon_...`, `mk_svc_...`, `mk_srv_...`, custom `mk_...`). App auth endpoints (`/api/databases/{db}/auth/signup|signin|refresh`) require at least an API key (`anon` or higher). |
| `X-User-Token` | Conditional | Optional user JWT. Used only when `Authorization` is a service-level key (`mk_svc_...` or `mk_srv_...`) to enforce PLS/RBAC in user context. Ignored for `anon` keys and direct user JWT requests. |

## Standard Response Headers

All API responses include:

| Header | Description |
|--------|-------------|
| `X-Aouda-Protocol-Version` | Protocol version used |
| `X-Served-By` | Address of the server that handled the request |
| `X-Server-Role` | Current role (Primary, Secondary, Hidden, Standalone) |
| `X-Request-Id` | Echoed from request if provided |
| `X-Auth-Database` | **On 401 auth errors only (optional).** Legacy/discovery hint. Clients should use the same auth context as the request: server auth → `POST /api/auth/signin`; app auth → `POST /api/databases/{db}/auth/signin`. Omitted when not applicable. |

### Authentication and Authorization

Aouda has **two independent auth systems** that use the same HTTP headers but serve different purposes. Understanding which system applies depends on the endpoint and the credential type.

#### Credential Types

All credentials are sent as `Authorization: Bearer <credential>`. The server identifies the type by prefix:

| Prefix | Type | System | Description |
|--------|------|--------|-------------|
| `mk_anon_` | App anon key | Application Auth | Public/frontend key. PLS enforced, RBAC `anonymous` role. |
| `mk_svc_` | App service key | Application Auth | Backend key for one database. PLS bypassed, full access. |
| `mk_srv_` | Server API key | Server Auth | Cross-database service key. Scoped roles per database. |
| `mk_` (other) | Custom app key | Application Auth | Granular custom key created via admin API. |
| `eyJ...` (JWT) | Access token | Either | JWT from signin. Claims determine which auth system issued it. |

The server dispatches to the correct auth handler based on prefix — no configuration needed from the client.

#### Auth Enforcement Rules

| Target Endpoint | Auth Required? | Accepted Credentials |
|-----------------|:--------------:|----------------------|
| `/api/auth/setup` | No (setup mode only, localhost) | None |
| `/api/auth/signin`, `/api/auth/refresh` | No | None (these produce credentials) |
| `/api/auth/signout`, `/api/auth/me`, etc. | Yes | Server JWT |
| `/api/auth/admin/*` | Yes (`db_admin`) | Server JWT or `mk_srv_` with admin role |
| `/api/databases/{db}/auth/signup\|signin\|refresh` | Yes (Layer 1) | Any app API key (`mk_anon_`, `mk_svc_`, `mk_`, custom) |
| `/api/databases/{db}/auth/me\|signout\|password` | Yes (Layer 1 + 2) | API key + user JWT in `X-User-Token`, or user JWT directly |
| `/api/databases/{db}/query\|tables\|rows\|...` | **Only if db has linked auth** | Any valid credential (see below) |
| `/api/databases/{db}/query\|...` (no auth db) | No | None — open access |

#### How Data Endpoint Auth Works

When a request hits a database-scoped data endpoint (e.g. `/api/databases/{db}/query`):

```
1. Does the target database have a linked auth database?
   NO  → Request proceeds without auth (open access)
   YES → Continue to step 2

2. Read Authorization header
   Missing → 401 AUTH_TOKEN_MISSING
   Present → Continue to step 3

3. Identify credential type by prefix
   mk_anon_ → Resolve as app anon key → anonymous role, PLS enforced
   mk_svc_  → Resolve as app service key → full access, PLS bypassed
   mk_srv_  → Resolve as server API key → check db_roles claim for this database
   mk_*     → Resolve as custom app key → check permissions
   eyJ*     → Validate JWT signature and claims → extract roles

4. Check X-User-Token header (optional)
   Present + credential is mk_svc_ or mk_srv_ → Apply user context (PLS/RBAC)
   Present + credential is mk_anon_ or user JWT → Ignored
   Absent → Use credential's own identity

5. Check RBAC permissions
   Role has required operation (read/write/delete/admin) → Proceed
   Role lacks permission → 403 INSUFFICIENT_PERMISSIONS
   No role for this database → 403 AUTHORIZATION_DENIED
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
| `/api/auth/signout` | POST | Bearer JWT | Revoke session |
| `/api/auth/me` | GET | Bearer JWT | Current user profile |
| `/api/auth/me` | PATCH | Bearer JWT | Update profile metadata |
| `/api/auth/password` | PUT | Bearer JWT | Change password |
| `/api/auth/admin/users` | GET | Bearer JWT (`db_admin`) | List server users |
| `/api/auth/admin/users/{id}` | GET/PATCH | Bearer JWT (`db_admin`) | Get/update user |
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
| `iss` | `{base_url}/api/auth` |
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
| `/api/databases/{db}/auth/signout` | POST | API key + user JWT | Revoke session |
| `/api/databases/{db}/auth/me` | GET | API key + user JWT | Current user profile |
| `/api/databases/{db}/auth/me` | PATCH | API key + user JWT | Update profile metadata |
| `/api/databases/{db}/auth/password` | PUT | API key + user JWT | Change own password (current password required) |
| `/api/databases/{db}/auth/request-password-reset` | POST | API key (Layer 1) | Request 6-digit OTP emailed to user; always 200 (anti-enumeration) |
| `/api/databases/{db}/auth/reset-password` | POST | API key (Layer 1) | Submit OTP + new password; returns token pair; also used for invite-pending first-time password set |
| `/api/databases/{db}/auth/mfa/enroll` | POST | User JWT | Enrol TOTP or phone MFA factor |
| `/api/databases/{db}/auth/mfa/challenge` | POST | User JWT | Create MFA challenge; sends SMS OTP for phone factors |
| `/api/databases/{db}/auth/mfa/verify` | POST | User JWT | Submit OTP/TOTP/backup code; returns `aal2` token pair on success |
| `/api/databases/{db}/auth/mfa/factors` | GET | User JWT | List enrolled MFA factors |
| `/api/databases/{db}/auth/mfa/factors/{id}` | DELETE | User JWT | Delete an enrolled MFA factor |
| `/api/databases/{db}/auth/admin/users` | GET | API key (`db_admin`) | List app users |
| `/api/databases/{db}/auth/admin/users` | POST | API key (`db_admin`) | Create user; supports `sendInviteEmail` + `forcePasswordChange` flags |
| `/api/databases/{db}/auth/admin/users/{id}` | GET/PATCH | API key (`db_admin`) | Get/update user |
| `/api/databases/{db}/auth/admin/users/{id}/password` | PUT | API key (`db_admin`) | Admin override of user's password (no current-password check); optional `forcePasswordChange` |
| `/api/databases/{db}/auth/admin/users/{id}/invite` | POST | API key (`db_admin`) | (Re-)send invite email with OTP; invalidates previous unused tokens |
| `/api/databases/{db}/auth/admin/users/{id}/mfa/enroll` | POST | API key (`db_admin`) | Admin-enrol a phone MFA factor on behalf of a user |
| `/api/databases/{db}/auth/admin/api-keys` | GET/POST | API key (`db_admin`) | List/create custom API keys |
| `/api/databases/{db}/auth/admin/api-keys/{id}` | DELETE | API key (`db_admin`) | Revoke custom API key |

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
| `iss` | `{base_url}/api/databases/{db}` |
| `aud` | Auth database name (e.g. `"_auth"`) |
| `aal` | Authentication assurance level: `"aal1"` (password only) or `"aal2"` (MFA verified) |
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
| `Primary` | Read from primary only (default) |
| `PrimaryPreferred` | Prefer primary, fall back to secondary |
| `Secondary` | Read from any secondary (not hidden) |
| `SecondaryPreferred` | Prefer secondary, fall back to primary |
| `Nearest` | Read from lowest-latency member |
| `Hidden` | Explicitly target hidden replica |

### Behavior

- **Standalone mode**: Ignores read preference (serves all requests)
- **Hidden replicas**: Only serve `Hidden` preference, reject all others with `421 Misdirected Request`
- **Invalid values**: Default to `Primary`

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
| `INVALID_FORMAT` | 400 | Invalid format parameter value |
| `MISSING_TABLE` | 400 | Table name is missing from request |
| `MISSING_DATABASE` | 400 | Database name is missing or empty in request (v2: set the `database` field in the request body) |
| `INVALID_OPERATOR` | 400 | Invalid comparison operator in where clause |
| `INVALID_COLUMN` | 400 | Invalid column name or reference |
| `INVALID_VALUE` | 400 | Invalid value type or format |

#### Resource Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TABLE_NOT_FOUND` | 404 | The specified table does not exist |
| `COLUMN_NOT_FOUND` | 404 | The specified column does not exist |
| `TABLE_EXISTS` | 409 | A table with the specified name already exists |
| `COLUMN_EXISTS` | 409 | A column with the specified name already exists |
| `DECLARATIVE_SCHEMA_DDL_FORBIDDEN` | 409 | HTTP DDL rejected because the table is managed by declarative schema apply (`InferenceMode: Extend`) |
| `DATABASE_NOT_FOUND` | 404 | The specified database does not exist |
| `DATABASE_EXISTS` | 409 | A database with the specified name already exists |
| `BRANCH_EXISTS` | 409 | A branch with the specified name already exists |
| `MERGE_CONFLICT` | 409 | Branch merge has conflicts that must be resolved or forced |
| `NOT_FOUND` | 404 | Generic not-found (used when a more specific code is not available) |
| `PARTITION_FILTER_REQUIRED` | 400 | Query on a partitioned table is missing the required partition key filter |

#### Authentication Errors (4xx)

Auth errors use the `AuthErrorPayload` shape (see [Auth Error Responses](#auth-error-responses) above) where the `"error"` field is the machine-readable code.

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_TOKEN_MISSING` | 401 | Missing or empty `Authorization: Bearer` header |
| `AUTH_TOKEN_INVALID` | 401 | Token malformed or signature invalid (also used for invalid `X-User-Token`) |
| `AUTH_TOKEN_EXPIRED` | 401 | Access token has expired |
| `AUTH_TOKEN_REVOKED` | 401 | Access token has been revoked |
| `AUTH_API_KEY_INVALID` | 401 | API key invalid, revoked, or expired |
| `AUTH_API_KEY_REQUIRED` | 401 | App auth endpoint requires an API key (`anon` or higher) but none was provided |
| `UNAUTHORIZED` | 401 | Deny-by-default: unrecognised path on a server where auth is configured |
| `NOT_AUTHENTICATED` | 401 | Authentication required (database has auth enabled but no valid token) |
| `AUTHORIZATION_DENIED` | 403 | Authenticated but no role for the target database |
| `INSUFFICIENT_PERMISSIONS` | 403 | Authenticated but role lacks required operation (e.g. read-only role attempting write) |
| `AUTH_INVALID_CREDENTIALS` | 401 | Signin credentials are invalid (wrong password or non-existent email) |
| `AUTH_ACCOUNT_LOCKED` | 423 | Account is temporarily locked due to too many failed attempts. `Retry-After` header is set. |
| `AUTH_ACCOUNT_DISABLED` | 401 | Account is disabled by an administrator |
| `AUTH_RATE_LIMITED` | 429 | Too many auth requests — rate limit exceeded. `Retry-After` header is set. |
| `AUTH_SIGNUP_FAILED` | 400 | Signup could not be completed (generic message to prevent information leakage) |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | Refresh token is invalid, expired, or revoked |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | Email is already registered in this auth database |
| `AUTH_PASSWORD_TOO_WEAK` | 400 | Password does not meet the minimum password policy |
| `AUTH_INVALID_EMAIL` | 400 | Email is blank or not a valid email format |
| `AUTH_PLS_TENANT_CLAIM_MISSING` | 403 | PLS: required tenant claim missing from the JWT for this table |
| `AUTH_PLS_TENANT_CLAIM_MISMATCH` | 403 | PLS: explicit partition filter does not match the token's tenant claim |
| `AUTH_PLS_WRITE_SCOPE_VIOLATION` | 403 | PLS: write request targets a partition outside the tenant scope |
| `AUTH_PLS_GRANT_NOT_FOUND` | 403 | PLS (auth-db-pls): requested partition is not in the user's grant set |
| `AUTH_PLS_GRANT_INSUFFICIENT_ACCESS` | 403 | PLS: partition is granted but access level is `read`, which does not allow writes |
| `AUTH_PLS_UNSUPPORTED_OR_SHAPE` | 403 | PLS: `Where.Or` predicate shape is incompatible with safe auth-db-pls partition enforcement |

#### State Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `MISDIRECTED_REQUEST` | 421 | Request sent to wrong server based on read preference |
| `WRITE_NOT_ALLOWED` | 403 | Write operations not allowed on this server |
| `NOT_PRIMARY` | 421 | Server is not the primary |

#### Server Errors (5xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `SERVICE_UNAVAILABLE` | 503 | Service is temporarily unavailable |
| `INTERNAL_ERROR` | 500 | An internal error occurred |
| `TIMEOUT` | 504 | Request timed out |
| `OVERLOADED` | 503 | Server is overloaded |

#### Protocol Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNSUPPORTED_VERSION` | 400 | Unsupported protocol version |
| `MALFORMED_REQUEST` | 400 | Request is malformed at the protocol level |

---

## Endpoints

### Query Endpoint

#### `POST /api/databases/{db}/query`

Execute a query against a table.

**Query Parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `format` | `columnar` | Response format: `columnar` or `rows` |
| `readPreference` | `Primary` | Read preference (overrides header) |

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
| `in` | Value in array | `["admin", "owner"]` |
| `nin` | Value not in array | `["deleted", "archived"]` |
| `like` | SQL LIKE pattern | `"A%"` |

Encoding conventions:
- `isNull` — encode as `{ "op": "eq", "value": null }`
- `isNotNull` — encode as `{ "op": "ne", "value": null }`
- `between` — encode as two conditions: `{ "op": "gte", "value": lower }` + `{ "op": "lte", "value": upper }`

Unknown operator strings return `INVALID_OPERATOR` (400).

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

For single-column equality joins, use `leftColumn` + `rightColumn`. For multi-column equality joins, use `leftColumns` + `rightColumns` (same length). `"cross"` join requires neither.

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

**Columnar Response (default):**

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

**Row Response (`format=rows`):**

```json
{
  "rows": [
    {"id": 1, "customer": "Alice", "total": 100.50},
    {"id": 2, "customer": "Bob", "total": 200.75}
  ],
  "stats": {
    "rowsScanned": 1000,
    "rowsReturned": 2,
    "segmentsAccessed": 5,
    "executionMs": 12
  }
}
```

---

### Materialized query endpoints

Base path: `/api/databases/{db}/materialized-queries`

| Method | Path | Auth (when DB auth enabled) | Description |
|--------|------|------------------------------|-------------|
| GET | `/` | Read | List all materialized queries (array of status objects). |
| GET | `/{name}` | Read | Status for one query; `404` if missing. |
| POST | `/` | Admin | Create a query. Body below. `204 No Content` on success. |
| DELETE | `/{name}` | Admin | Drop query and storage; `204` on success. |
| POST | `/{name}/query` | Read | Return materialized rows as JSON objects (see response). |
| POST | `/{name}:refresh` | Admin | Trigger a full rebuild of the MQ result table (shadow-build pattern). Accepts `?await=true` to wait for completion or `?await=false` for fire-and-forget. Result table is readable with stale data throughout. |

**Create body** (camelCase JSON):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique materialized query name. |
| `sourceTable` | string | Yes | Base table name. |
| `type` | number | Yes | `1` LatestPerKey, `2` FirstPerKey (HTTP create not supported), `3` Aggregate, `4` Filter, `5` TopNPerGroup (HTTP create not supported). |
| `configJson` | string | Yes* | Type-specific config JSON text (same as engine `MaterializedQueryDefinition.ConfigJson`). |
| `config` | object | Yes* | Alternative: embedded object; server serializes to JSON if `configJson` omitted. |

`configJson` / `config` must provide valid **FilterConfig**, **LatestPerKeyConfig**, or **AggregateConfig** JSON for types `4`, `1`, and `3` respectively (see engine storage types under `Aouda.Engine.Storage.Materialized`).

**Query response** (`POST .../query`):

```json
{
  "rows": [ { "col1": 1, "col2": "a" } ],
  "stats": {
    "rowsScanned": 1,
    "rowsReturned": 1,
    "executionMs": 0.42
  }
}
```

---

### Schema seed

#### `POST /api/databases/{db}/schema/seed`

Apply idempotent seed data. Tables must already exist.

**Request:** seed document root:

```json
{
  "tables": {
    "orders": {
      "rows": [
        { "id": 1, "status": "pending" }
      ]
    }
  }
}
```

**Response:** `200 OK` — `SeedApplyResult` with per-table `insertedCount` and `skippedCount` (existing primary keys skipped).

---

### Tables Endpoints

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
| `rowCount` | number | Total row count across all segments |
| `createdAt` | string | ISO 8601 timestamp when table was created (empty for legacy tables) |
| `lastModifiedAt` | string | ISO 8601 timestamp when table/data was last modified (empty for legacy tables) |
| `sizeBytes` | number | Approximate size in bytes across all segments |
| `policy` | object | Storage policy |

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
      "dataDurability": "DiskAndRam",
      "pinAllInMemory": false
    }
  }
}
```

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
      "type": "Int64",
      "isNullable": false,
      "isAutoIncrement": true,
      "primaryKeyOrder": 1
    },
    {
      "name": "customer_id",
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

**Response:** `201 Created` with table detail

#### `DELETE /api/tables/{name}`

Delete a table.

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

Update table storage policy.

**Request:**

```json
{
  "database": "mydb",
  "storageTemperature": "HotOnly"
}
```

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

**Response:** `201 Created` with column detail

#### `PATCH /api/databases/{db}/tables/{name}/columns/{columnName}`

Rename a column.

**Request:**

```json
{
  "database": "mydb",
  "newName": "total_amount"
}
```

**Response:** `200 OK` with column detail

#### `DELETE /api/tables/{name}/columns/{columnName}`

Drop a column.

**Response:** `204 No Content`

---

### Data Mutation Endpoints

#### `POST /api/databases/{db}/tables/{name}/rows`

Insert one or more rows into a table.

**Request Body:**

```json
{
  "database": "mydb",
  "table": "orders",
  "rows": [
    { "status": "pending", "price": 100.50 },
    { "status": "shipped", "price": 200.00 }
  ],
  "writeConcern": "majority"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `rows` | object[] | Yes | Array of row objects to insert. Each key is a column name. |
| `writeConcern` | string? | No | Write-concern override for this request. Allowed: `"one"`, `"majority"`, `"all"`. Null/omitted = use table/database default. |

**Response:** `200 OK`

```json
{
  "rowsInserted": 2,
  "executionMs": 5,
  "generatedValues": {
    "0": { "id": 42 },
    "1": { "id": 43 }
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
| `generatedValues` | object? | Generated values for auto-increment columns. Keys are row indices (as strings), values are objects mapping column names to generated values. Only present when auto-increment columns exist. |
| `writeConcernStatus` | object? | Write-concern acknowledgement details. Null when `writeConcern` is `"one"` (no replication wait). See `WriteConcernStatus` below. |

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
| `INVALID_REQUEST` | 400 | Missing rows, invalid column name, or schema mismatch |
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

**Note:** Returns `rowsUpdated: 0` with 200 status when WHERE predicates match no rows. This is not an error.

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `INVALID_REQUEST` | 400 | Missing/empty WHERE, missing/empty SET, or invalid column name in SET |

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

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `AUTHORIZATION_DENIED` | 403 | Caller lacks the `Truncate` authorization scope |

---

#### `POST /api/databases/{db}/tables/{name}/rows/batch`

Execute multiple update and/or delete operations against the same table in a single request.
All operations are applied sequentially in the order given and committed in a single WAL
transaction.

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

**Response** — computed columns appear at the end of `columns` and `types`:

```json
{
  "columns": ["id", "name", "price", "discountedPrice"],
  "types":   ["Int64", "String", "Decimal", "Unknown"],
  "data":    [[1], ["Widget"], [99.0], [89.1]],
  "rowCount": 1,
  "stats": { "executionMs": 4 }
}
```

Computed column result type is always `"Unknown"` in v1 (no static type inference).

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

Basic liveness probe.

**Response:**

```json
{
  "status": "healthy"
}
```

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
| 503 Service Unavailable | Cloud destination not yet supported (S3/Azure/GCS), or engine not ready |
| 400 Bad Request | Destination path cannot be created or accessed |

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
      "newFileCount": 15
    }
  ],
  "warning": null
}
```

`warning` is non-null when no destination is configured or when the destination is unavailable.

#### `POST /admin/backup/restore/{id}`

Restore from the backup with the given ID. The server engine is stopped, restored, and restarted — this is a blocking operation.

**No request body.**

**Response** (`200 OK`):
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

**Errors:**

| Status | When |
|--------|------|
| 404 Not Found | Backup ID does not exist at the destination |
| 409 Conflict | A backup operation is already in progress |
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

Update (or disable) the backup schedule. Persisted to `{DataPath}/backup-config.json`.

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

---

### Replication Endpoints

#### `GET /admin/replication/status`

Get replication status.

**Response:**

```json
{
  "role": "Standalone",
  "currentPrimary": null,
  "walPosition": 12345,
  "lagBytes": 0,
  "fencingToken": 1,
  "canAcceptWrites": true
}
```

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
    "nodeLogStream": true
  }
}
```

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
| `Decimal` | 128-bit decimal |
| `String` | UTF-8 string |
| `Timestamp` | UTC instant (see note below) |
| `Date` | Date only |
| `Guid` | UUID/GUID |

### Timestamp semantics

`Timestamp` values are **UTC instants** stored as **Int64** (.NET UTC ticks). Insert payloads may use ISO-8601 strings or numeric forms accepted by the server; **the original timezone offset is not stored** and is **not** round-tripped on read (unlike SQL Server `datetimeoffset`). Clients should expect results in **UTC**. For full detail and CLR mapping notes, see [`docs/dev/Timestamp-Type.md`](../dev/Timestamp-Type.md).

---

## Known Limitations

The following features are not yet supported:

1. **NULLS FIRST/LAST**: Custom null ordering is not supported. Nulls sort last for ASC, first for DESC.
2. **Expression-based ORDER BY**: Only column names can be used for ordering, not expressions.

**Note — WhereClause nesting:** Earlier versions of this document stated that nested AND/OR was not supported. This is no longer accurate. The `groups` field in `WhereClause` supports up to **5** levels of nesting (`ProtocolConstants.MaxWhereClauseNestingDepth = 5`). Each group is AND'd with the top-level conditions, enabling safe composition of independent filter layers (e.g., partition scope + row scope). See the `groups` field description in the [Query Endpoint](#query-endpoint) section for details.

Remaining limitations are tracked in the backlog for future enhancement.

---

## Future Extensions

The following are candidates for future versions:

- Protobuf binary protocol support (MessagePack is already implemented — see [WebSocket Streaming Protocol](#websocket-streaming-protocol) below)
- Batch HTTP query endpoint (multiple queries in a single request)
- GraphQL endpoint

---

## WebSocket Streaming Protocol

Aouda provides a full-duplex WebSocket API for real-time table subscriptions and high-throughput streaming writes.

### Endpoint

```
ws://{host}/api/ws
wss://{host}/api/ws   (TLS)
```

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

**Example:**
```json
{
  "type": "auth",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "database": "my_db",
  "wire_mode": "json"
}
```

**Server responds with:** `auth_ok` or `auth_error`.

---

#### `subscribe`

Subscribe to a table stream. The server immediately sends a `snapshot` of current matching rows, then streams `change` messages as rows are inserted, updated, or deleted.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"subscribe"` |
| `id` | string | Yes | Client-assigned subscription ID. Must be unique per connection. Used to correlate `snapshot`, `change`, and `error` messages. |
| `target` | string | Yes | Table name to subscribe to. |
| `filter` | object? | No | Optional filter predicate (same `WhereClause` format as the query endpoint). Only matching rows appear in the snapshot and change stream. |
| `resume_from` | number? | No | Resume from this global sequence version. When provided, the server replays changes from that point instead of sending a full snapshot. Use the `version` from a prior `snapshot` or `change` message. |

**Example:**
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

**Server responds with:** `snapshot` (initial data), then `change` messages as data changes.

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
| `rows` | array | Yes | Array of row objects to insert. Same format as the HTTP insert endpoint. |

**Example:**
```json
{
  "type": "stream_rows",
  "id": "stream-metrics-1",
  "seq": 1,
  "rows": [
    {"sensor_id": 42, "value": 98.6, "recorded_at": "2026-05-22T11:00:00Z"},
    {"sensor_id": 42, "value": 99.1, "recorded_at": "2026-05-22T11:00:05Z"}
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
| `code` | string | Error code (e.g., `AUTH_TOKEN_INVALID`, `AUTH_TOKEN_EXPIRED`). |
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

Periodic liveness signal carrying the current global sequence version. Clients can detect change-stream gaps by comparing consecutive `version` values.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"heartbeat"` |
| `version` | number | Current global sequence version (monotonically increasing). |

**Example:**
```json
{"type": "heartbeat", "version": 100042}
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

Initial snapshot of a subscription's current data. Sent immediately after a successful `subscribe` (when `resume_from` is not provided or points to before the current snapshot).

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"snapshot"` |
| `id` | string | Subscription ID this snapshot belongs to. |
| `rows` | object[] | Current rows matching the subscription filter. Each element is a row object (`{ columnName: value, ... }`). |
| `version` | number | Global sequence version at which this snapshot was taken. Store this value and pass it as `resume_from` on reconnect to avoid re-receiving the full snapshot. |

**Example:**
```json
{
  "type": "snapshot",
  "id": "sub-orders-1",
  "rows": [
    {"id": 1, "status": "active", "total": 150.00},
    {"id": 2, "status": "active", "total": 99.99}
  ],
  "version": 100040
}
```

---

#### `change`

Incremental row change on an active subscription. Sent whenever a row matching the subscription filter is inserted, updated, or deleted.

| Field | Type | Description |
|---|---|---|
| `type` | string | Always `"change"` |
| `id` | string | Subscription ID this change belongs to. |
| `op` | string | Operation: `"insert"`, `"update"`, or `"delete"`. |
| `row` | object? | New row values. Present for `"insert"` and `"update"`. Null for `"delete"`. |
| `prev` | object? | Previous row values before update. Present for `"update"` only. |
| `key` | object? | Primary key of the affected row. Present for `"delete"`. |
| `version` | number | Global sequence version of this change. |

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

All bulk-load endpoints are under `/api/databases/{db}/bulk-load`. The `:append` request body is NDJSON (`application/x-ndjson`); all other bodies are JSON.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/databases/{db}/bulk-load:begin` | Begin a new session. Returns `jobId`. |
| `POST` | `/api/databases/{db}/bulk-load/{jobId}:append` | Append rows (NDJSON body). |
| `POST` | `/api/databases/{db}/bulk-load/{jobId}:commit` | Commit the session. |
| `GET` | `/api/databases/{db}/bulk-load/{jobId}:status` | Get session status and progress. |
| `GET` | `/api/databases/{db}/bulk-load:list` | List all sessions for this database. |
| `POST` | `/api/databases/{db}/bulk-load/{jobId}:force-abort` | Operator abort. |

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
| `pkUniquenessOverride` | string? | null | `"strict"`, `"recent"`, `"bestEffort"`, null | Override primary-key uniqueness enforcement for this load. Null = use table default. |
| `replicationMode` | string? | `"logShipSegments"` | `"logShipSegments"`, `"skipReplication"`, `"markForSnapshot"` | Replication strategy. `"skipReplication"` on a multi-node cluster without `forceSingleNodeReplicationBypass: true` is rejected (400 `BULK_LOAD_INVALID_OPTIONS`). Case-insensitive. |
| `forceSingleNodeReplicationBypass` | bool? | `false` | `true`, `false`, null | Two-key safety valve: must be `true` to use `"skipReplication"` on a multi-node cluster. |
| `maxRowsPerSegment` | number? | null | Any positive integer | Override the maximum rows per sealed segment. Null = use server default. |
| `embeddingModelVersion` | string? | null | Any valid model version string | Embedding model version for vector-indexed tables. |
| `postLoadMqBehavior` | string? | `"auto"` | `"auto"`, `"skip"` | Controls Aggregate MQ rebuild after commit. `"auto"` (default): all Aggregate MQs whose source tables are in this load are automatically rebuilt after `BulkLoadCommitted`. `"skip"`: no MQ rebuild; use for multi-step pipelines where you call `POST .../materialized-queries/{name}:refresh` explicitly. |

**Response body:**

| Field | Type | Description |
|---|---|---|
| `jobId` | string | Server-assigned job identifier. Include in all subsequent requests for this load. |
| `tables` | string[] | Echo of the requested tables. |
| `acquiredAtUtc` | string | ISO 8601 UTC timestamp when table locks were acquired. |
| `maxRowsPerAppend` | number | Maximum rows allowed per single `:append` call. Clients must chunk larger payloads. |
| `resumedFromDurableCursor` | object? | Present when this `:begin` resumed an in-flight job via idempotency-key match. Null for fresh jobs. Contains `rowsDurablyCommitted` (number), `segmentsCommitted` (number), `perTable` (object mapping table name to durable row count). |

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

---

### `POST {jobId}:append`

Append a chunk of rows to an in-flight session.

**Content-Type:** `application/x-ndjson` (JSON Lines — one row object per line).

When the session was begun with more than one table, each row must include a `"_table"` field naming its destination. The `"_table"` field is stripped before inserting.

**Example (single table):**
```
POST /api/databases/my_db/bulk-load/blj_abc123:append
Content-Type: application/x-ndjson

{"sensor_id": 1, "value": 98.6, "recorded_at": "2026-05-22T09:00:01Z"}
{"sensor_id": 2, "value": 72.1, "recorded_at": "2026-05-22T09:00:01Z"}
```

**Example (multi-table, `"_table"` discriminator required):**
```
{"_table": "events",     "id": 1, "type": "click"}
{"_table": "event_meta", "event_id": 1, "browser": "Chrome"}
```

**Response body:**

| Field | Type | Description |
|---|---|---|
| `rowsAppended` | number | Rows accepted in **this** append call. Not necessarily durable yet. |
| `rowsAppendedToBuffer` | number | Cumulative rows accepted into the session buffer since `:begin`. Not necessarily durable (lost on server crash before sealing). |
| `rowsDurablyCommitted` | number | Cumulative rows in sealed segments with commit markers that have been fsync'd to WAL. Use this as the upstream offset for resume on reconnect. |
| `acceptedAtUtc` | string | ISO 8601 UTC timestamp. |
| `segmentsSealedSoFar` | number | Segments sealed across all tables in this job so far. |

**Errors:**

| Code | Status | When |
|---|---|---|
| `BULK_LOAD_JOB_NOT_FOUND` | 404 | `jobId` not found or session expired. |
| `BULK_LOAD_INVALID_STATE` | 409 | Job is not in `"appending"` state. |
| `BULK_LOAD_MISSING_DISCRIMINATOR` | 400 | Multi-table job and a row is missing `"_table"`. |
| `BULK_LOAD_CURSOR_MISMATCH` | 409 | Client resumed from an incorrect cursor (sent rows below `rowsDurablyCommitted`). |

---

### `POST {jobId}:commit`

Commit the session. All sealed segments become queryable.

**Request body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `database` | string | Yes | — | Database name. |
| `jobId` | string | Yes | — | Job identifier (also in the path). |
| `waitForDeferredWork` | bool | No | `false` | If `true`, the response is held until all post-processing (PK index rebuild, CSC mirror, RaBitQ encodings) completes. |
| `writeConcern` | string? | No | `"acknowledged"` | Replication barrier. Allowed: `"acknowledged"`, `"majority"`, `"all"`. |
| `writeConcernTimeoutMs` | number? | No | `300000` (5 min) | Max wait for the write-concern barrier. On timeout, returns 200 OK with `writeConcernTimedOut: true`. The data is durable; replicas catch up at their own pace. |

**Response body:**

| Field | Type | Description |
|---|---|---|
| `jobId` | string | Echo of job ID. |
| `tables` | string[] | Tables involved in the load. |
| `rowsLoaded` | number | Total rows durably committed across all tables. |
| `perTableRowCounts` | object | Per-table row counts (`{ tableName: count }`). Always present. |
| `segmentsCreated` | number | Total segments created. |
| `committedAtUtc` | string | ISO 8601 UTC commit timestamp. |
| `deferredWorkCompleted` | boolean | Whether deferred work completed before this response was sent. |
| `walPosition` | number | WAL position of the closing `BulkLoadCommitted` frame. Replicas that have applied this position have the complete load. |
| `writeConcernRequested` | string | Echo of `writeConcern` from request. |
| `writeConcernAchieved` | string | Strongest write concern achieved before return. May be weaker than `writeConcernRequested` if `writeConcernTimedOut`. |
| `writeConcernTimedOut` | boolean | `true` when requested write concern was not satisfied within the timeout. The load is still durable. |
| `progress` | object? | Present only when `waitForDeferredWork: true`. Fields: `ivfAssignmentsCompleted`, `ivfAssignmentsTotal`, `raBitQEncodingsCompleted`, `raBitQEncodingsTotal`, `cscMirrorsCompleted`, `cscMirrorsTotal`, `pkIndexRebuildCompleted`, `pkIndexRebuildTotal`. |

---

### `GET {jobId}:status`

Get current session state and progress.

**Response body:**

| Field | Type | Description |
|---|---|---|
| `jobId` | string | Job identifier. |
| `tables` | string[] | Tables being loaded. |
| `state` | string | Current state. Allowed values: `"acquired"`, `"appending"`, `"committing"`, `"deferred"`, `"completed"`, `"failed"`, `"aborted"`. |
| `rowsAppendedToBuffer` | number | Rows in buffer (not yet durable). |
| `rowsDurablyCommitted` | number | Durably committed rows. |
| `segmentsSealed` | number | Segments sealed so far. |
| `startedAtUtc` | string | ISO 8601 session start time. |
| `lastUpdatedUtc` | string | ISO 8601 last state update time. |
| `progress` | object? | Deferred work progress. Same structure as in commit response. Null if no deferred work is in progress. |
| `replicas` | array | Per-replica fetch progress. Empty on single-node deployments. Each element has `serverId` (string), `segmentsFetched` (number), `segmentsTotal` (number), `lagSeconds` (number). |
| `mqRebuildStatus` | string? | Materialized Query rebuild status after commit. One of `"pending"`, `"inProgress"`, `"completed"`, `"skipped"`, `"error"`. Present when the job has committed; null or absent while still in `"appending"` state. `"skipped"` means `postLoadMqBehavior` was `"skip"` or there are no dependent Aggregate MQs. |
| `error` | string? | Human-readable error message. Set when `state = "failed"`. |
| `errorCode` | string? | Error code when `state = "failed"`. |

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
