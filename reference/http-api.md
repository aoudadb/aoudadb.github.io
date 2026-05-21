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
| `iss` | `aouda-server` |
| `aud` | `aouda` |
| `db_roles` | `{ "myapp": ["db_writer"], "analytics": ["db_reader"] }` |
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
| `/api/databases/{db}/auth/password` | PUT | API key + user JWT | Change password |
| `/api/databases/{db}/auth/admin/users` | GET | API key (`db_admin`) | List app users |
| `/api/databases/{db}/auth/admin/users/{id}` | GET/PATCH | API key (`db_admin`) | Get/update user |
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
| `iss` | `aouda-app` |
| `aud` | Database name (e.g. `myapp`) |
| `tenant_id` | Tenant ID for PLS partition scoping |
| `db_roles` | `{ "myapp": ["db_reader"] }` |
| `permissions` | Fine-grained table permissions (if custom role) |
| `iat`, `exp` | Issued-at and expiry timestamps |

#### Auth Error Responses

All auth errors follow the standard error format with additional fields for programmatic handling:

```json
{
  "error": "Access token has expired",
  "code": "AUTH_TOKEN_EXPIRED",
  "message": "The access token in the Authorization header has expired.",
  "suggestion": "Use POST /api/auth/refresh with your refresh token to obtain a new access token.",
  "docs": "https://docs.aouda.io/auth/token-refresh"
}
```

**403 errors include structured details:**

```json
{
  "error": "Insufficient permissions",
  "code": "INSUFFICIENT_PERMISSIONS",
  "details": {
    "requiredOperation": "write",
    "database": "myapp",
    "table": "orders",
    "currentRoles": ["db_reader"]
  }
}
```

## Read Preferences

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

#### Authentication Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_TOKEN_MISSING` | 401 | Missing or empty `Authorization: Bearer` header |
| `AUTH_TOKEN_INVALID` | 401 | Token malformed or signature invalid |
| `AUTH_TOKEN_EXPIRED` | 401 | Access token has expired |
| `AUTH_TOKEN_REVOKED` | 401 | Access token has been revoked |
| `AUTH_API_KEY_INVALID` | 401 | API key invalid, revoked, or expired |
| `AUTH_API_KEY_REQUIRED` | 401 | App auth endpoint requires an API key (`anon` or higher) but none was provided |
| `NOT_AUTHENTICATED` | 401 | Authentication required (e.g. database has auth enabled but no valid token) |
| `AUTHORIZATION_DENIED` | 403 | Authenticated but no role for the target database |
| `INSUFFICIENT_PERMISSIONS` | 403 | Authenticated but role lacks required operation (e.g. read-only role attempting write) |

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

**Where Clause:**

```json
{
  "and": [{"column": "...", "op": "...", "value": ...}],
  "or": [{"column": "...", "op": "...", "value": ...}]
}
```

**Operators:** `eq`, `ne`, `gt`, `gte`, `lt`, `lte`

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
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `rows` | object[] | Yes | Array of row objects to insert. Each key is a column name. |

**Response:** `200 OK`

```json
{
  "rowsInserted": 2,
  "executionMs": 5,
  "generatedValues": {
    "0": { "id": 42 },
    "1": { "id": 43 }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsInserted` | number | Number of rows successfully inserted |
| `executionMs` | number | Server-side execution time in milliseconds |
| `generatedValues` | object? | Generated values for auto-increment columns. Keys are row indices (as strings), values are objects mapping column names to generated values. Only present when auto-increment columns exist. |

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
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes (v2) | Database name; must match URL path `{db}` |
| `where` | object | Yes | WHERE clause with at least one predicate. Uses same format as query endpoint. Server returns 400 if missing or empty. |
| `set` | object | Yes | Column values to update. Keys are column names, values are new values. Server returns 400 if missing or empty. Server validates column names exist in schema. |

**Response:** `200 OK`

```json
{
  "rowsUpdated": 3,
  "executionMs": 12
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsUpdated` | number | Number of rows affected by the update |
| `executionMs` | number | Server-side execution time in milliseconds |

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
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `where` | object | Yes | WHERE clause with at least one predicate. Uses same format as query endpoint. Server returns 400 if missing or empty. |

**Response:** `200 OK`

```json
{
  "rowsDeleted": 5,
  "executionMs": 8
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rowsDeleted` | number | Number of rows deleted |
| `executionMs` | number | Server-side execution time in milliseconds |

**Note:** Returns `rowsDeleted: 0` with 200 status when WHERE predicates match no rows. This is not an error.

**Errors:**

| Code | Status | When |
|------|--------|------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist |
| `INVALID_REQUEST` | 400 | Missing or empty WHERE clause |

**Common Notes for All Mutation Endpoints:**

- All three endpoints require write permissions (`[RequireWritePermission]` on the server). Requests to non-primary replicas return `WRITE_NOT_ALLOWED` (403) or `NOT_PRIMARY` (421).
- All three endpoints use `encodeURIComponent()` for the table name in the URL path.
- Standard error codes (`INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`, etc.) apply as described in the Error Codes section above.

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

1. **Nested AND/OR**: Only one level of AND and OR is supported. Nested predicates (e.g., `AND(OR(...))`) are not supported.
2. **NULLS FIRST/LAST**: Custom null ordering is not supported. Nulls sort last for ASC, first for DESC.
3. **Expression-based ORDER BY**: Only column names can be used for ordering, not expressions.

These limitations are tracked in the backlog for future enhancement.

---

## Future Extensions

The following are not part of v1 but may be added in future versions:

- Binary protocol support (MessagePack, Protobuf)
- WebSocket streaming for large result sets
- Batch query endpoint
- GraphQL endpoint

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-11 | Initial release |
| 1.1 | 2026-02-05 | Enhanced TableSummary (rowCount, createdAt, lastModifiedAt, sizeBytes), schema introspection endpoint, relationships endpoint, TypeScript generation endpoint, reference metadata in columns |
| 1.2 | 2026-02-06 | Data mutation endpoints: insert (POST), update (PATCH), delete (DELETE) for /api/tables/{name}/rows |
| 1.3 | 2026-03-19 | Comprehensive authentication section: credential types, auth enforcement flow, X-User-Token, server and app auth endpoint reference |
