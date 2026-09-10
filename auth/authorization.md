---
title: "Data Authorization"
nav_order: 4
parent: "Auth and Authorization"
---

# Data Authorization: Three Modes

> Part of the [Application Auth Guide](Getting-Started-Auth.md). Start there for an overview.

---

Aouda supports three table-level authorization modes, each suited to a different complexity of access control. All existing tables default to `jwt-claim` — no migration is required unless you want advanced capabilities.

---

## 19.1 Mode Overview

| Mode | Partition routing | Row filtering | JWT requires | Auth DB queried |
|------|------------------|---------------|:---:|:---:|
| `jwt-claim` | Single partition from the bound claim (`plsClaimBinding`, default `tenant_id`) | No row filtering | Bound claim, or `sub` when binding is `subject` | No |
| `auth-db-pls` | All partitions granted in auth DB for the configured dimension | No row filtering (unless combined with RLS) | Identity only | Session cache (hot path) |
| `auth-db-rls` | No partition routing (uses existing PLS or jwt-claim) | Predicate from auth DB resolver injected as WHERE clause | Identity only | Session cache (hot path) |

Both `auth-db-pls` and `auth-db-rls` use a **session cache** as the hot path: resolved permissions are cached in the session record at sign-in. The vast majority of requests read from the session cache (~0.001ms), not the auth DB (~0.01ms). The auth DB itself is always memory-first — even the cold path is sub-millisecond.

---

## 19.2 Which Mode Should I Use?

```
Does your table need per-user data isolation?
  NO  → No auth mode needed. Use server-level access control only.

Is the access rule "one user, one tenant, one partition"?
  YES → jwt-claim (default)
        Simple SaaS. JWT carries tenant_id claim. No auth DB needed.

Does the user need access to MULTIPLE partitions simultaneously?
  (e.g. user is in 50 chat rooms, or has grants for 3 data providers)
  YES → auth-db-pls
        Partition grants stored in auth DB, resolved at query time.
        Fan-out: a single query returns data from ALL granted partitions.
        Write access levels: read / write / admin per grant.

Does the table need row-level filtering WITHIN a partition?
  (e.g. "user can only see their own records or their team's records")
  YES → auth-db-rls
        RLS resolver defines a WHERE predicate, injected before query execution.
        Admin pass-through: users with a specified role receive no predicate (full access).
        Compound predicates supported: owner_id = ? OR team_id IN (?).

Do you need BOTH partition routing AND row filtering on the same table?
  YES → Set **authMode: auth-db-pls** AND **rlsResolverName** together.
        PLS routes to granted partitions; RLS filters rows within each partition.
        The reverse (`auth-db-rls` + `permissionDimension`) is a **schema validation error**.
```

---

## 19.3 Mode 1: `jwt-claim` (Default)

This is the existing, default mode. A table with `authMode: jwt-claim` (or no `authMode` field at all) works exactly as before.

```bash
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "orders",
    "columns": [
      { "name": "id", "type": "Int64", "isPrimaryKey": true },
      { "name": "tenant_id", "type": "String", "isPartitionKey": true },
      { "name": "amount", "type": "Decimal" },
      { "name": "status", "type": "String" }
    ],
    "security": {
      "partitionLevelSecurity": true
    }
  }'
```

When a signed-in user queries `orders`, the middleware reads the **bound claim** from the JWT and routes all queries to that single partition. One user, one partition.

The default binding is `claim:tenant_id` (omit `plsClaimBinding` — same as today). Aouda's own sign-in JWT does **not** mint `tenant_id` unless an admin set it. Two ways to make `jwt-claim` work with built-in auth:

- **`plsClaimBinding: "subject"`** on the table — bind to JWT `sub` (`ClaimTypes.NameIdentifier`). Use this when the partition column is the user id.
- **Per-user custom claims** — `GET`/`PUT /api/databases/{db}/auth/admin/users/{id}/claims`. Keys become JWT claims at mint and refresh. Use this for a shared tenant id (`tenant_id: "acme"`) that is not the user id. Callers cannot set claims on `PATCH /auth/me`.

Unknown `plsClaimBinding` spellings fail schema apply (`SCHEMA_IDENTITY_COLUMN_NOT_BINDABLE` / identity-source parse). Valid: `subject`, `claim:<name>`.

| Credential | PLS Behavior |
|------------|-------------|
| User JWT with `tenant_id: "acme"` | Scoped to `acme` partition |
| User JWT without `tenant_id` | 403 — no partition access |
| `mk_anon_` API key | `anonymous` role — no data access by default |
| `mk_svc_` service key (no X-User-Token) | PLS **bypassed** — sees all partitions |
| `mk_svc_` + X-User-Token | PLS enforced using user JWT claims |
| `mk_srv_` server key | PLS **not enforced** (server-level access) |
| `db_admin` user JWT | Can use cross-partition access |

**When to use:** Simple SaaS where each user belongs to exactly one organization and should only see that organization's data.

---

## 19.4 Mode 2: `auth-db-pls` (Enhanced PLS)

Use `auth-db-pls` when a user needs access to **multiple partitions simultaneously** or when partition grants must change at runtime without re-issuing JWTs.

### 19.4.1 Setup

```bash
# Create a messages table with auth-db-pls
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "messages",
    "columns": [
      { "name": "id", "type": "Int64", "isPrimaryKey": true },
      { "name": "room_id", "type": "String", "isPartitionKey": true },
      { "name": "user_id", "type": "String" },
      { "name": "body", "type": "String" },
      { "name": "sent_at", "type": "Timestamp" }
    ],
    "security": {
      "partitionLevelSecurity": true,
      "authMode": "auth-db-pls",
      "permissionDimension": "chat_room"
    }
  }'
```

Then grant the user access to specific partitions:

```bash
# Grant Alice read+write access to chat room 42
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/usr_alice/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dimension": "chat_room",
    "partitionKey": "42",
    "accessLevel": "write"
  }'
```

### 19.4.2 Fan-Out Query (All Granted Partitions)

When Alice queries `messages` without specifying a `room_id` filter, Aouda automatically routes to **all** her granted partitions and merges the results:

```bash
# Returns messages from all rooms Alice has been granted access to
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "table": "messages", "orderBy": "sent_at", "limit": 50 }'
```

This is the **cross-partition fan-out** pattern — the most common query for chat, financial, and group-membership applications. Alice's granted partitions form the implicit filter. See [Cross-Partition Fan-Out Queries](#197-cross-partition-fan-out-queries) for more detail.

### 19.4.3 Targeted and Multi-Partition Queries

When Alice specifies a partition filter, Aouda validates that she has access to it:

```bash
# Returns messages from room 42 — Alice has a grant, succeeds
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -d '{ "table": "messages", "where": [{ "column": "room_id", "op": "=", "value": "42" }] }'

# Returns 403 — Alice has no grant for room 99
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -d '{ "table": "messages", "where": [{ "column": "room_id", "op": "=", "value": "99" }] }'
```

Multi-partition `IN` filter: Aouda intersects the requested set with Alice's grants and routes only to the allowed intersection:

```bash
# Rooms 42 and 55 are in Alice's grants; room 99 is not — only 42 and 55 are queried
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -d '{
    "table": "messages",
    "where": [{ "column": "room_id", "op": "in", "values": ["42", "55", "99"] }]
  }'
```

### 19.4.4 Write-Path Access Level Enforcement

`auth-db-pls` enforces **access levels** on writes. A user with `"accessLevel": "read"` can query but not insert, update, or delete.

| Access Level | Read | Insert | Update/Delete |
|---|:---:|:---:|:---:|
| `read` | ✅ | ❌ 403 | ❌ 403 |
| `write` | ✅ | ✅ | ✅ |
| `admin` | ✅ | ✅ | ✅ |

```bash
# Grant Bob read-only access to room 42 (he can view but not post)
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/usr_bob/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "dimension": "chat_room",
    "partitionKey": "42",
    "accessLevel": "read"
  }'
```

**Thin JWT benefit:** A user belonging to 500 chat rooms would add ~10 KB to a JWT if room memberships were embedded as claims. With `auth-db-pls`, the JWT carries only the user's identity; grants live in the auth DB and are resolved from the session cache at query time.

### 19.4.5 Durable Credentials for Non-Interactive Services

Every example above authenticates with `<alice-jwt>` — a 15-minute access token from a JWT session. That's the right shape for a human sitting in front of a browser, but it's the wrong shape for a backend service, a scheduled feeder job, or anything else that holds one static secret in a config file and never signs in interactively: it would have to implement OAuth-style refresh-token rotation just to stay authenticated.

For that case, link a `custom` API key to a user instead of minting sessions for it. The key is durable (no expiry unless you set one) and its principal resolves that user's `auth-db-pls` partition-grants through the **same** resolution path a JWT session for that user would use — there is no separate "API key scoping" mechanism to reason about, and no bypass.

```bash
# 1. Create a user to hold the service identity (it never signs in interactively)
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "email": "svc-quote-feeder@internal" }'
# → { "id": "usr_feeder", ... }

# 2. Grant it access to exactly the partitions it should touch (same endpoint as for a human user).
#    `dimension` must match the table permissionDimension byte-for-byte (case-sensitive).
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/usr_feeder/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "quote_source", "partitionKey": "oslo_bors", "accessLevel": "write" }'

# 3. Create a custom API key linked to that user
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "oslo-bors-feeder",
    "kind": "custom",
    "userId": "usr_feeder",
    "roles": [{ "role": "db_writer" }]
  }'
# → { "key": "mk_...", "userId": "usr_feeder", ... } — the key is shown once; store it like a password

# The feeder authenticates with that static key going forward:
curl -X POST http://localhost:5433/api/databases/finance/tables/quotes/rows \
  -H "Authorization: Bearer mk_..." \
  -d '{ "rows": [{ "id": 1, "quote_source": "oslo_bors", "instrument_id": "EQNR", "bid": 289.10, "ask": 289.30 }] }'
# → 200 — granted partition

curl -X POST http://localhost:5433/api/databases/finance/tables/quotes/rows \
  -H "Authorization: Bearer mk_..." \
  -d '{ "rows": [{ "id": 2, "quote_source": "bloomberg", "instrument_id": "EQNR", "bid": 289.10, "ask": 289.30 }] }'
# → 403 AUTH_PLS_GRANT_NOT_FOUND — not granted, exactly as it would be for a JWT session
```

**Do not** reach for `mk_svc_`/`mk_srv_` for this instead. Both are a full, audited bypass of PLS on every table (see the credential table in [§19.3](#193-mode-1-jwt-claim-default)) — appropriate when the caller is genuinely trusted with the whole database, not when it should be limited to `quote_source=oslo_bors`.

`userId` is only accepted on `kind: "custom"` keys — `anon`, `service_role`, `public`, and `server_admin` stay singleton, system-managed credentials and reject it with `400 INVALID_REQUEST`. Revoke the key (`DELETE .../admin/api-keys/{id}`) to cut the service off immediately, or delete the specific partition grant to narrow its access without rotating the credential.

---

## 19.5 Mode 3: `auth-db-rls` (Row-Level Security)

Use `auth-db-rls` when access must be determined at the **row level** within a partition — for example, "see only your own records, or records from your team."

Aouda RLS does **not** evaluate policies per-row at query time. Instead, it resolves the predicate once from the auth DB (session cache hot path) and **injects it as a WHERE clause** before the query executes. The columnar scan engine evaluates it like any other filter — once, not once per row. This eliminates per-row evaluation overhead entirely.

### 19.5.1 Setup: Define a Resolver

Resolvers are **admin API only** — they are not part of `schema apply`. Create them with `POST /api/databases/{db}/auth/admin/rls-resolvers` (service key or `db_admin`). `resolverType` is required on POST and stored; evaluation **ignores** it. Use `"ColumnMatch"`.

`valueConfig` on the wire is a **string**. Value sources are the code names (`UserId`, `Literal`, `PartitionGrant`). Older docs that said `auth-db-lookup` / `auth-db-grants` / `role-check` named things that were never in the evaluator.

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sales_access",
    "description": "Restricts sales rows to records owned by or shared with the user",
    "targetTable": "sales",
    "resolverType": "ColumnMatch",
    "rules": [
      {
        "ruleOrder": 0,
        "columnName": "owner_id",
        "operator": "Eq",
        "valueSource": "UserId",
        "valueConfig": "{}",
        "combinator": "Or"
      },
      {
        "ruleOrder": 1,
        "columnName": "team_id",
        "operator": "In",
        "valueSource": "PartitionGrant",
        "valueConfig": "{\"dimension\":\"team\"}",
        "combinator": null
      }
    ]
  }'
```

This resolver produces the compound predicate: `owner_id = '<userId>' OR team_id IN ('<team1>', '<team2>', ...)`.

**Literal comparison is a string.** A Bool column does **not** match Literal `"true"` (`true.ToString()` is `"True"`). Prefer a String column (`"true"` / `"false"`), as in the [write-side fixture](../examples/p43-write-side/).

### 19.5.2 Setup: Create the RLS Table

```bash
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sales",
    "columns": [
      { "name": "id", "type": "Int64", "isPrimaryKey": true },
      { "name": "company_id", "type": "String", "isPartitionKey": true },
      { "name": "owner_id", "type": "String" },
      { "name": "team_id", "type": "String" },
      { "name": "amount", "type": "Decimal" }
    ],
    "security": {
      "partitionLevelSecurity": true,
      "authMode": "auth-db-rls",
      "rlsResolverName": "sales_access"
    }
  }'
```

### 19.5.3 Admin Pass-Through

A `PartitionGrant` rule whose `valueConfig` JSON string has `"role"` and `"effect":"allow-all"` grants full access when the user holds that role — the resolver returns no predicate (`null`), and the query runs unfiltered within the partition. There is no `role-check` operator or value source.

```bash
# Update resolver to add admin pass-through as the first rule
curl -X PATCH http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/<resolverId> \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "ruleOrder": 0,
        "columnName": "id",
        "operator": "Eq",
        "valueSource": "PartitionGrant",
        "valueConfig": "{\"role\":\"company_admin\",\"effect\":\"allow-all\"}",
        "combinator": null
      },
      {
        "ruleOrder": 1,
        "columnName": "owner_id",
        "operator": "Eq",
        "valueSource": "UserId",
        "valueConfig": "{}",
        "combinator": "Or"
      },
      {
        "ruleOrder": 2,
        "columnName": "team_id",
        "operator": "In",
        "valueSource": "PartitionGrant",
        "valueConfig": "{\"dimension\":\"team\"}",
        "combinator": null
      }
    ]
  }'
```

When a `company_admin` user queries `sales`, the resolver sees the matching pass-through rule first and returns `null` — no predicate is injected, and the user sees all rows in the partition. Non-admin users hit the compound predicate path.

### 19.5.4 Write-Path Validation

For writes to `auth-db-rls` tables, Aouda evaluates a **write-check** predicate against the new or updated row. If the row would not be visible under that predicate, the write is rejected.

**Write-check replaces the read predicate** when `writeCheckRules` is present on the resolver. Absent `writeCheckRules` ⇒ write-check = the read rules (today's behavior). To require both membership and identity, put both rules in `writeCheckRules` — do not assume they are ANDed automatically.

The [write-side fixture](../examples/p43-write-side/) uses a SenderId-only write-check so a user can insert a stamped message into a private room they cannot **read**.

| Write Operation | Write-check matches row? | Result |
|---|:---:|:---:|
| INSERT | Yes | Allowed |
| INSERT | No | 403 |
| UPDATE → visible row | Yes | Allowed |
| UPDATE → invisible row | No | 403 |
| Admin (null predicate) | N/A | Always allowed |

---

## 19.6 Combined PLS + RLS

A table can use **both** partition routing and row filtering. The working configuration is **`authMode: auth-db-pls` plus `rlsResolverName`** (and `permissionDimension` for the PLS grants). Setting `auth-db-rls` together with `permissionDimension` is a **schema validation error** (fail-closed).

```bash
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "portfolio_data",
    "columns": [
      { "name": "id", "type": "Int64", "isPrimaryKey": true },
      { "name": "portfolio_group_id", "type": "String", "isPartitionKey": true },
      { "name": "owner_id", "type": "String" },
      { "name": "instrument", "type": "String" },
      { "name": "value", "type": "Decimal" }
    ],
    "security": {
      "partitionLevelSecurity": true,
      "authMode": "auth-db-pls",
      "permissionDimension": "portfolio_group",
      "rlsResolverName": "portfolio_access"
    }
  }'
```

**Enforcement sequence for a query:**
1. PLS resolves which partition groups the user is granted (`portfolio_group` dimension).
2. Fan-out routes the query to all granted partition groups.
3. RLS resolves the `portfolio_access` predicate and injects it as a WHERE clause into each partition sub-query.
4. Results are filtered and merged.

PLS and RLS are **conjunctive** (AND). There is no cross-layer OR.

---

## 19.7 Cross-Partition Fan-Out Queries

Fan-out is the **primary** `auth-db-pls` query pattern. When a user queries an `auth-db-pls` table without specifying a partition key filter, Aouda routes to **all** their granted partitions and merges the result set automatically:

```
User grants: { portfolio_group: ["grp_3", "grp_7", "grp_12"] }

Query:   SELECT * FROM portfolio_data ORDER BY value DESC LIMIT 100

ADRA enforcement:
  1. Resolve allowed partitions → ["grp_3", "grp_7", "grp_12"]
  2. Execute sub-query on each granted partition
  3. Merge results
  4. Apply ORDER BY + LIMIT across merged set

Result:  Top 100 rows by value, drawn from all three portfolio groups
```

This eliminates application-layer aggregation code. The query looks like a normal single-table query from the client's perspective — Aouda handles the routing and merging transparently.

**Common fan-out queries:**
- Chat: "Show my latest messages across all rooms" — fans out to all room partitions
- Financial: "Latest quotes for instrument AAPL across all my authorized sources"
- CRM: "All open deals I'm responsible for across all company partitions I manage"

---

## 19.8 Admin API: Partition Grants

Manage which partition keys a user is allowed to access in each dimension.

All endpoints are under `/api/databases/{db}/auth/admin/users/{userId}/partition-grants` and require a `service_role` key, `db_admin` user JWT, or server admin token.

### Create a Partition Grant

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dimension": "chat_room",
    "partitionKey": "42",
    "accessLevel": "write",
    "grantedBy": "usr_admin_123"
  }'
```

Response (201 Created):

```json
{
  "id": "grnt_xyz789",
  "userId": "usr_abc",
  "dimension": "chat_room",
  "partitionKey": "42",
  "accessLevel": "write",
  "grantedBy": "usr_admin_123",
  "createdAt": "2026-03-26T12:00:00Z"
}
```

`accessLevel` must be `"read"`, `"write"`, or `"admin"`. Missing or empty `dimension` / `partitionKey` returns 400 `AUTH_GRANT_INVALID`.

**`dimension` is case-sensitive.** It must match the table's `permissionDimension` **byte-for-byte** (`StringComparison.Ordinal` — `"source"` ≠ `"Source"`). Creation does **not** validate or normalize against any table: a grant with the wrong casing returns `201` and looks fine on read-back, then every insert/query against the table fails `403` (`Partition '…' is not in the user's grant set for dimension 'Source'`). Copy the `permissionDimension` string from the schema; do not lowercase it. Partition **keys** are also compared ordinal-case-sensitive (they are data). Engine work to case-fold or reject a casing mismatch at grant-create time is BL-430.

### List Partition Grants

```bash
# All grants for a user
curl http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/partition-grants \
  -H "Authorization: Bearer <admin-token>"

# Filtered by dimension
curl "http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/partition-grants?dimension=chat_room" \
  -H "Authorization: Bearer <admin-token>"
```

### Delete a Partition Grant

```bash
curl -X DELETE http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/partition-grants/grnt_xyz789 \
  -H "Authorization: Bearer <admin-token>"
# 204 No Content on success
# 404 AUTH_GRANT_NOT_FOUND if grant does not exist
```

---

## 19.9 Admin API: RLS Resolvers

Manage resolver definitions that determine the row-filter predicate injected for `auth-db-rls` tables.

All endpoints are under `/api/databases/{db}/auth/admin/rls-resolvers`.

### Create a Resolver

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_resolver",
    "description": "Filters rows by owner",
    "targetTable": "records",
    "resolverType": "ColumnMatch",
    "rules": [
      {
        "ruleOrder": 0,
        "columnName": "owner_id",
        "operator": "Eq",
        "valueSource": "UserId",
        "valueConfig": "{}",
        "combinator": null
      }
    ]
  }'
```

`resolverType` is required on create and stored; evaluation ignores it. Use `"ColumnMatch"`.

**Value sources (code names — these are the only ones `Evaluate` understands):**

| Value Source | `valueConfig` (string) | Description |
|---|---|---|
| `UserId` | `"{}"` (ignored) | Authenticated user's id |
| `Literal` | the comparison **string** (not an object) | Static value. Bool columns do not match `"true"` — use String |
| `PartitionGrant` | `{"dimension":"<name>"}` | User's granted partition keys for that dimension. Empty grants deny that arm |
| `PartitionGrant` (pass-through) | `{"role":"<name>","effect":"allow-all"}` | If the user has the role, resolver returns null (full access) |
| `Claim` | any | Deny sentinel (not implemented — BL-315). Do not use |

**Combinators:** `And` or `Or` on rule N — how N joins with N+1. Last rule has `combinator: null`. Default if omitted is `And`.

**`writeCheckRules`:** optional second rule list. Present ⇒ write-check **replaces** read. Absent ⇒ write-check = read.

### List Resolvers

```bash
# All resolvers
curl http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>"

# Filtered to a specific target table
curl "http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers?targetTable=sales" \
  -H "Authorization: Bearer <admin-token>"
```

### Get Resolver (with rules)

```bash
curl http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/rslvr_abc123 \
  -H "Authorization: Bearer <admin-token>"
```

Response includes the resolver metadata and its ordered rules array.

### Update Resolver

```bash
curl -X PATCH http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/rslvr_abc123 \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated description",
    "rules": [
      {
        "ruleOrder": 0,
        "columnName": "owner_id",
        "operator": "Eq",
        "valueSource": "UserId",
        "valueConfig": "{}",
        "combinator": null
      }
    ]
  }'
```

PATCH replaces the full rules list. The permission version counter is incremented automatically — session caches are refreshed on the next request.

### Delete Resolver

```bash
curl -X DELETE http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/rslvr_abc123 \
  -H "Authorization: Bearer <admin-token>"
# 204 No Content on success
# 404 AUTH_RESOLVER_NOT_FOUND if resolver does not exist
```

### Worked example — public OR member + identity stamp

Published fixture (byte-identical in the engine tree): [`examples/p43-write-side/`](../examples/p43-write-side/). Schema apply creates tables; [`auth-setup.json`](../examples/p43-write-side/auth-setup.json) is **admin HTTP** (users, roles, resolvers, grants) — proof that resolvers are not schema apply.

- `rooms` — `auth-db-rls`: `id In PartitionGrant{room_membership} Or IsPublic Eq Literal true`. Alice has zero grants and still sees the public room. `IsPublic` is **String**.
- `messages` — read membership; `writeCheckRules` is `SenderId Eq UserId` only. Alice can insert a stamped row into a private room she cannot read.
- `notes` — `plsClaimBinding: "subject"` + `"derived": { "identity": "subject" }` on `UserId`.

Use a user JWT on the **admin listener**. RLS/PLS need a principal; do not put these tables on `mk_pub_*` / data-plane.

---

## 19.10 Reference Use Cases

### Use Case 1 — Chat Application (`auth-db-pls`, hundreds of rooms)

{: .warning }
**Check the volume before copying this shape.** This use case partitions `messages` by `room_id`, and that
is only the right layout when **each room individually** holds on the order of a million rows. A typical
chat product does not: tens of thousands of rooms and a few thousand messages a day across the whole
product puts each room in the tens of rows — orders of magnitude below the line. Partitioning there
creates a directory per room holding almost nothing, and imposes `PARTITION_FILTER_REQUIRED` on every read
and every subscribe for the life of the table. See
[Should this table have a partition key?](../guides/partitioning.md#should-this-table-have-a-partition-key-p45),
then read [the unpartitioned variant](#the-unpartitioned-variant--same-grants-no-partition-key) below —
for most chat applications that is the one to build.

A user belongs to hundreds of chat rooms. In this use case the `messages` table is partitioned by `room_id` — assume it has cleared the rule above. The application grants partition access at room-join time, and revokes it when the user leaves.

```bash
# Grant Alice write access to 3 rooms (repeat at join time for each room)
curl -X POST http://localhost:5433/api/databases/chat/auth/admin/users/usr_alice/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "chat_room", "partitionKey": "room_42", "accessLevel": "write" }'

curl -X POST http://localhost:5433/api/databases/chat/auth/admin/users/usr_alice/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "chat_room", "partitionKey": "room_55", "accessLevel": "write" }'

curl -X POST http://localhost:5433/api/databases/chat/auth/admin/users/usr_alice/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "chat_room", "partitionKey": "room_99", "accessLevel": "read" }'

# Alice's "all my latest messages" query — fan-out across all her granted rooms
curl -X POST http://localhost:5433/api/databases/chat/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -d '{ "table": "messages", "orderBy": "sent_at", "limit": 50 }'
# → Returns 50 most recent messages drawn from room_42, room_55, and room_99

# Alice posts to room_42 (write access) — succeeds
curl -X POST http://localhost:5433/api/databases/chat/tables/messages/rows \
  -H "Authorization: Bearer <alice-jwt>" \
  -d '{ "rows": [{ "room_id": "room_42", "body": "Hello!", "user_id": "usr_alice" }] }'

# Alice tries to post to room_99 (read-only) — rejected
curl -X POST http://localhost:5433/api/databases/chat/tables/messages/rows \
  -H "Authorization: Bearer <alice-jwt>" \
  -d '{ "rows": [{ "room_id": "room_99", "body": "Hi there" }] }'
# → 403 AUTH_PLS_GRANT_INSUFFICIENT_ACCESS
```

**Why not embed room memberships in the JWT?** A user in 500 rooms would add ~10 KB to the JWT. With `auth-db-pls`, the JWT carries only Alice's identity; room grants live in the auth DB's `_user_partition_grants` table and are resolved from the in-memory session cache at query time. Granting or revoking room access takes effect on the next request — no token re-issuance required.

#### The unpartitioned variant — same grants, no partition key

**A partition grant does not require a partitioned table.** The `partitionKey` field on a grant is a key
*within the grant document*; it is not a claim about the table's physical layout. An `auth-db-rls` rule
with `valueSource: "PartitionGrant"` reads the caller's grants for a dimension and injects them as an
ordinary `IN` predicate on a named column — it never consults the partition router, so it behaves
identically whether or not the table is partitioned.

That is what lets a chat application keep everything the use case above buys — grants minted at join time,
revoked at leave time, resolved from the session cache, no memberships in the JWT — while dropping a
partition key its volume does not justify:

```jsonc
// aouda.schema.json — no partitionKey anywhere
{
  "tables": {
    "messages": {
      "clusterColumns": ["sent_at"],
      "authMode": "auth-db-rls",
      "rlsResolverName": "room_thread"
    }
  }
}
```

```bash
# The resolver is admin HTTP, not schema apply
curl -X POST http://localhost:5433/api/databases/chat/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "room_thread",
    "targetTable": "messages",
    "resolverType": "ColumnMatch",
    "rules": [
      { "ruleOrder": 0, "columnName": "room_id", "operator": "In",
        "valueSource": "PartitionGrant", "valueConfig": "{\"dimension\":\"chat_room\"}",
        "combinator": null }
    ],
    "writeCheckRules": [
      { "ruleOrder": 0, "columnName": "user_id", "operator": "Eq",
        "valueSource": "UserId", "valueConfig": "{}", "combinator": null }
    ]
  }'
```

The grant `curl`s from the use case above are **unchanged** — same dimension, same `partitionKey` values,
same admin endpoint.

| | Partitioned (`auth-db-pls`) | Unpartitioned (`auth-db-rls` + `PartitionGrant`) |
|---|---|---|
| Grants | Minted per room, resolved from session cache | Identical |
| Unentitled rows | Never routed to | Filtered by the injected predicate |
| Named query with `params: {}` | Fails `PARTITION_FILTER_REQUIRED` | Legal — RLS supplies the predicate |
| `subscribe` for a user token | Needs `permissionDimension` or a bound param | Works as-is |
| Write authorization | Grant `accessLevel` on the target partition | `writeCheckRules` (above), or grant-based rules |

Note that `permissionDimension` and `auth-db-rls` are **mutually exclusive**: declaring both fails apply
with *"authMode 'auth-db-rls' cannot be combined with permissionDimension."* Pick one mode per table.

#### Layout and authorization mode are independent choices

It is tempting to read the table above as "big rooms → `auth-db-pls`, small rooms → `auth-db-rls`". That
is not the rule, and getting it wrong is how a table ends up partitioned for a reason that was never a
partitioning reason.

There are two decisions, and they do not determine each other:

1. **Does the table get a `partitionKey`?** Decided purely by volume —
   [Should this table have a partition key?](../guides/partitioning.md#should-this-table-have-a-partition-key-p45).
   This is the decision that buys pruning.
2. **Which authorization mode?** Decided by the policy you need to express.

**RLS is not the slower option.** Both modes deposit an ordinary predicate into the same `Where` before
translation — PLS into `Where.And` / `Where.Or`, RLS into `Where.Groups` — and the planner sees one
predicate tree either way. So on a table that *is* partitioned, an RLS rule constraining the partition
key with `Eq` / `In` satisfies the partition-filter guard **and** drives the same exact partition and
bucket pruning that PLS does. Pinned by `RlsPartitionGuardAndPruningTests` in the engine repository,
which asserts the pruning counters, not just the row set.

What actually separates the two modes:

| | `auth-db-pls` (and `jwt-claim` PLS) | `auth-db-rls` |
|---|---|---|
| Needs a partition key | **Yes** — apply fails without one | No |
| Can constrain | Only the partition-key column | Any column, compound rules, admin pass-through |
| Predicate shapes | Equality, or OR-of-equality fan-out over grants | `Eq`, `In`, `Like`, `And`/`Or` combinations |
| Mixed `Where.Or` from the caller | Rejected — a leak guard | Allowed; RLS nests in its own group |
| Read cost, same predicate | — identical — | — identical — |
| Write cost | Grant `accessLevel` check | `UPDATE`/`DELETE` additionally **pre-read** matching rows to evaluate the write check |

So: choose the layout on volume, then choose the mode on policy. The only combination the engine forbids
is PLS without a partition key.

---

### Use Case 2 — CRM Application (`auth-db-rls`, admin pass-through + compound predicates)

Sales records are partitioned by `company_id`. Regular users see only their own sales or their team's sales. Company admins see everything in their company's partition.

```bash
# Create the resolver with admin pass-through + compound predicate
curl -X POST http://localhost:5433/api/databases/crm/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sales_access",
    "targetTable": "sales",
    "resolverType": "ColumnMatch",
    "rules": [
      {
        "ruleOrder": 0,
        "columnName": "id",
        "operator": "Eq",
        "valueSource": "PartitionGrant",
        "valueConfig": "{\"role\":\"company_admin\",\"effect\":\"allow-all\"}",
        "combinator": null
      },
      {
        "ruleOrder": 1,
        "columnName": "owner_id",
        "operator": "Eq",
        "valueSource": "UserId",
        "valueConfig": "{}",
        "combinator": "Or"
      },
      {
        "ruleOrder": 2,
        "columnName": "team_id",
        "operator": "In",
        "valueSource": "PartitionGrant",
        "valueConfig": "{\"dimension\":\"team\"}",
        "combinator": null
      }
    ]
  }'

# Regular user queries — injected predicate: owner_id = 'usr_alice' OR team_id IN ('team_west')
curl -X POST http://localhost:5433/api/databases/crm/query \
  -H "Authorization: Bearer <user-jwt>" \
  -d '{ "table": "sales", "where": [{ "column": "company_id", "op": "=", "value": "acme" }] }'
# → Returns only Alice's own sales or sales shared with her teams

# Company admin queries — no predicate injected (null = full partition access)
curl -X POST http://localhost:5433/api/databases/crm/query \
  -H "Authorization: Bearer <admin-jwt>" \
  -d '{ "table": "sales", "where": [{ "column": "company_id", "op": "=", "value": "acme" }] }'
# → Returns all sales records for acme

# Regular user tries to insert a record owned by someone else — rejected
curl -X POST http://localhost:5433/api/databases/crm/tables/sales/rows \
  -H "Authorization: Bearer <user-jwt>" \
  -d '{ "rows": [{ "company_id": "acme", "owner_id": "usr_other", "amount": 5000 }] }'
# → 403 AUTH_RLS_INSERT_VIOLATION (row would not be visible to the inserter)
```

---

### Use Case 3 — Financial Platform (`auth-db-pls`, billions of rows on disk)

A financial platform stores billions of security quotes partitioned by `quote_source`. Users are granted access to specific data providers. Most data resides on disk in a columnar store.

```bash
# Create the quotes table
curl -X POST http://localhost:5433/api/databases/finance/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "quotes",
    "columns": [
      { "name": "id", "type": "Int64", "isPrimaryKey": true },
      { "name": "quote_source", "type": "String", "isPartitionKey": true },
      { "name": "instrument_id", "type": "String" },
      { "name": "bid", "type": "Decimal" },
      { "name": "ask", "type": "Decimal" },
      { "name": "timestamp", "type": "Timestamp" }
    ],
    "security": {
      "partitionLevelSecurity": true,
      "authMode": "auth-db-pls",
      "permissionDimension": "quote_source"
    }
  }'

# Grant an analyst access to two data sources
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/usr_analyst/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "quote_source", "partitionKey": "oslo_bors", "accessLevel": "read" }'

curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/usr_analyst/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "dimension": "quote_source", "partitionKey": "nasdaq", "accessLevel": "read" }'

# Fan-out: latest AAPL quotes from all authorized sources
curl -X POST http://localhost:5433/api/databases/finance/query \
  -H "Authorization: Bearer <analyst-jwt>" \
  -d '{
    "table": "quotes",
    "where": [{ "column": "instrument_id", "op": "=", "value": "AAPL" }],
    "orderBy": "timestamp",
    "limit": 10
  }'
# → Returns AAPL quotes from oslo_bors and nasdaq only
# → Attempts to access bloomberg or other sources return 403

# Revoke access immediately — effective on the next request, no JWT re-issuance
curl -X DELETE http://localhost:5433/api/databases/finance/auth/admin/users/usr_analyst/partition-grants/grnt_oslo \
  -H "Authorization: Bearer <admin-token>"
```

**Performance note:** The `quotes` table holds billions of rows on disk in a columnar store — most data is never loaded into memory. Authorization resolution (~0.01ms from the memory-first auth DB) is negligible compared to the I/O cost of reading quote data. This is Aouda's key architectural advantage: even when data tables are on disk at petabyte scale, authorization stays sub-millisecond because it only queries the small, always-memory-first auth tables.
