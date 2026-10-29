---
title: "Data Authorization"
nav_order: 4
parent: "Auth and Authorization"
---

# Data Authorization: Three Modes

> Part of the [Application Auth Guide](../getting-started/auth.md). Start there for an overview.

---

Aouda supports three table-level authorization modes, each suited to a different complexity of access control. All existing tables default to `jwt-claim` — no migration is required unless you want advanced capabilities.

---

## 19.0 RBAC is a separate gate from PLS/RLS

Everything else on this page — `jwt-claim`, `auth-db-pls`, `auth-db-rls` — decides **which rows** an already-authorized caller may see or write. It has nothing to do with whether the caller may invoke the artifact at all. That's a coarser, separate gate: **RBAC role membership, scoped per database**, and it is what actually authorizes named-query and named-mutation **execute**.

- A role assignment's `scope` is a database name (or `null`/`"*"` for all databases) — never a table, a named query, or a named mutation. See [Auth reference — Application Auth Admin Endpoints](reference.md#application-auth-admin-endpoints) for the wire shape (`{ "roleName": "db_reader", "scope": "mydb" }`).
- Named-mutation execute needs the caller's role to carry `write` (or better) on that database; named-query execute needs `read`. This check runs **before** PLS/RLS: an authenticated JWT with a perfectly good partition grant or RLS predicate is still denied here first if it's holding the wrong database-scoped role.
- On the [data-plane listener](../guides/direct-client-access.md), denial at this gate is **not** `403 INSUFFICIENT_PERMISSIONS`. It is the same masked `404 NAMED_QUERY_NOT_FOUND` / `NAMED_MUTATION_NOT_FOUND` used for an unknown artifact name or an unsigned caller ([wire reference](../reference/http-api.md#error-codes)) — so a 404 on a name you know is right does not necessarily mean the name is wrong.

| Caller | Result |
|---|---|
| No token / `mk_anon_*` | 404 `NAMED_QUERY_NOT_FOUND` / `NAMED_MUTATION_NOT_FOUND` |
| Valid JWT, role has the needed scope | 200 |
| Valid JWT, real user, but role lacks `write` on this database (e.g. `db_reader` calling a named mutation) | **Same 404** — not 403 |

If a named-mutation call 404s and the name is definitely right, check the caller's `db_roles` scope for that database next — before suspecting PLS/RLS. PLS/RLS denials that *do* pass the RBAC gate surface their own codes (`AUTH_PLS_GRANT_NOT_FOUND`, `AUTH_RLS_INSERT_VIOLATION`, etc. — see [§19.3](#193-mode-1-jwt-claim-default) onward), not this masked 404.

---

## 19.1 Mode Overview

| Mode | Partition routing | Row filtering | JWT requires | Auth DB queried |
|------|------------------|---------------|:---:|:---:|
| `jwt-claim` | Single partition from the bound claim (`plsClaimBinding`, default `tenant_id`) | No row filtering | Bound claim, or `sub` when binding is `subject` | No |
| `auth-db-pls` | All partitions granted in auth DB for the configured dimension | No row filtering (unless combined with RLS) | Identity only | Session cache (hot path) |
| `auth-db-rls` | No partition routing (uses existing PLS or jwt-claim) | Predicate from auth DB resolver injected as WHERE clause | Identity only | Session cache (hot path) |

Both `auth-db-pls` and `auth-db-rls` use a **session cache** as the hot path: resolved permissions are cached in the session record at sign-in. The vast majority of requests read from the session cache (~0.001ms), not the auth DB (~0.01ms). The auth DB itself is always memory-first — even the cold path is sub-millisecond.

**No resolved permissions means no access** (**BL-950, 0.3.0**). An `auth-db-pls` or `auth-db-rls` table is enforced
from the caller's resolved permissions, and a request that has none is denied, never let through: an anonymous caller, a
database with **no linked auth database**, and a permission lookup that failed all read no row of such a table and may
write none (a PLS table answers `403 AUTH_PLS_GRANT_NOT_FOUND`; an RLS table answers an empty result and refuses writes).
That holds over HTTP, WebSocket and long-poll, and for graph and vector queries. Only a service key bypasses it. So link
the auth database before you give a table an `auth-db-*` mode: unlinking one makes its tables unreadable, not open.

### What changed in 0.4.0: only a service key bypasses PLS and RLS (**0.4.0**)

Up to 0.3.x a **server API key** (`mk_srv_…`) was treated as a service key: on every database it could reach, it read and
wrote past partition-level security (`jwt-claim` and `auth-db-pls`) and row-level security (`auth-db-rls`). From 0.4.0
**only an app's service key (`mk_svc_…`, kind `service_role`) bypasses them**, over HTTP, WebSocket and long-poll alike.

**Which keys lost the bypass.** Server API keys (`mk_srv_…`, kind `server_admin`). The same rule now covers every other
credential without a user — `custom` keys not linked to a user, `anon` and `public` keys: those already got no bypass from the
keys the server issues, and the rule is now one rule rather than a list of exceptions.

**What such a request gets now.** Its role's grants (RBAC is unchanged: a server key's `db_admin` still lets it create tables,
apply schema and manage the database), and on a protected table only what a request with **no user** may see:

| Table | A key without a user (not a service key) |
|---|---|
| `auth-db-rls` | Only rows the table's RLS rule shows to a request with no user — with `UserId` or `PartitionGrant` rules, **none**. Writes are refused. |
| `auth-db-pls` | `403 AUTH_PLS_GRANT_NOT_FOUND`. A key whose role is `db_admin` on the database may still **read** across partitions by asking for it (`"crossPartitionAccess": true`), which is audited. |
| `jwt-claim` | `403` — the key carries no partition claim. The same `db_admin` + `crossPartitionAccess` read applies. |
| No auth mode | Unchanged: its role's grants. |

The server-admin endpoints (`/api/auth/admin/*`, database management, backups) are unchanged: they answer from the key's role.

**What to use instead.**

- **Server-side code that must see a whole database:** that database's service key (`mk_svc_…`, returned once when the
  database is created with auth enabled). Keep it on the server.
- **Access on behalf of one user:** the user's own JWT (sign them in), or a service key **or server API key** with
  `X-User-Token: <the user's JWT>` — the request then gets that user's grants ([client integration §13](client-integration.md#13-backend-user-context-x-user-token)).
- **A service limited to some partitions:** a `custom` key linked to a user ([§19.4.5](#1945-durable-credentials-for-non-interactive-services)).
- **An operator's cross-partition read:** a `db_admin` key or JWT with `"crossPartitionAccess": true` (`auth-db-pls`, `jwt-claim`).

### Bulk load is not a per-user write (**BL-1031, 0.5.0**)

`POST …/bulk-load:begin` on a table with PLS or RLS returns `403` `AUTHORIZATION_DENIED` unless the caller is that
database's `service_role` key (`mk_svc_`). A `db_admin` user, a server key (`mk_srv_`), and a `custom` key are refused,
including a caller whose partition grant would allow an ordinary insert of the same rows, and a user JWT that carries
`api_key_kind=service_role`. That name is not a custom claim: storing it is `AUTH_CLAIM_INVALID`. Bulk load does not filter
rows down to the caller's scope: it is a migration, and the session is not started. A table with no PLS and no RLS
policy is unchanged. See [Bulk load](../guides/bulk-load.md).

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
    "database": "myapp",
    "name": "orders",
    "columns": [
      { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
      { "name": "tenant_id", "type": "String", "partitionKeyOrder": 1 },
      { "name": "amount", "type": "Decimal", "precision": 18, "scale": 2 },
      { "name": "status", "type": "String" }
    ],
    "partitionLevelSecurity": true
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
| User JWT without `tenant_id`, or with an empty or white-space one | 403 `AUTH_PLS_TENANT_CLAIM_MISSING` — no partition access |
| `mk_anon_` API key | `anonymous` role — no data access by default |
| `mk_svc_` service key (no X-User-Token) | PLS **bypassed** — sees all partitions |
| `mk_svc_` + X-User-Token | PLS enforced using user JWT claims — on HTTP, and on WebSocket / long-poll as `user_token` / `userToken` (**BL-1223, next train**) |
| `mk_srv_` server key | PLS **enforced** (**0.4.0**; [what changed](#what-changed-in-040-only-a-service-key-bypasses-pls-and-rls-040)): `403` without the claim; a `db_admin` key may read with `crossPartitionAccess` (audited). Up to 0.3.x: not enforced |
| `db_admin` user JWT | Can use cross-partition access |

**When to use:** Simple SaaS where each user belongs to exactly one organization and should only see that organization's data.

---

## 19.4 Mode 2: `auth-db-pls` (Enhanced PLS)

Use `auth-db-pls` when a user needs access to **multiple partitions simultaneously** or when partition grants must change at runtime without re-issuing JWTs.

**A table names two things, and neither is inferred** (**BL-1176, 0.7.0**):

- **`permissionDimension`** is the grant namespace. A partition grant in the auth database is only *(user, dimension, key,
  access level)*: it names no database, table or column, because the auth database is a standalone identity provider and Aouda
  is one of its consumers. The dimension is an opaque entitlement name such as `fx_source`. It is matched against the grant
  byte-for-byte, and it selects no column.
- **`permissionColumn`** is the column the grant keys are compared with, declared beside the dimension. It must name a column of
  the table (exact name).

Both are **required** for `auth-db-pls` on a table, and the table is refused when either is missing or the column names no column.
A dimension spelled like a column (`permissionDimension: "Source"`) does **not** select that column, and partition-key order does not
select one either. Up to 0.6.0 the engine inferred the column: a column named like the dimension (ignoring case), else a `tenant_id`
partition column, else the first partition-key column. A table persisted that way now **denies** every per-user read and write
until it declares `permissionColumn` — re-apply its schema or set it through the table's options.

So one key can be scoped per product. An fx table declares `permissionDimension: "fx_source"`, `permissionColumn: "Source"`; a rates
table declares `"rates_source"` and the same column. A grant `fx_source` / `MORN` admits the fx table's `Source = 'MORN'` rows and
nothing in the rates table; the stored value stays `MORN` and the column stays `Source`. The column is not tied to the partition
key: it can be the second partition-key column (`SecurityId`, then `Source`) or no partition-key column at all. Dropping the declared
column is refused; renaming it carries the binding.

The other direction works the same way: **one grant, differently named columns.** Each table names its own column, so a grant
`quote_source` / `MORN` reaches both of these tables, compared with `Source` in one and `QuoteSource` in the other:

```jsonc
{
  "tables": {
    "SpotQuote":   { "authMode": "auth-db-pls", "permissionDimension": "quote_source", "permissionColumn": "Source" /* … */ },
    "VendorQuote": { "authMode": "auth-db-pls", "permissionDimension": "quote_source", "permissionColumn": "QuoteSource" /* … */ }
  }
}
```

A grant whose dimension no table declares is simply not read by Aouda; it is still a valid entitlement for any other consumer of
the auth database.

Edge tables and vector search keep scoping by the grant set — an edge traversal or a nearest-neighbour search needs at least one grant
in the dimension and declares no column (an edge table refuses one). A vector-column table is an ordinary table for its reads, so
`POST …:create-vector-column` with `auth-db-pls` takes a `permissionColumn` too, and refuses one without `auth-db-pls`.

### 19.4.1 Setup

```bash
# Create a messages table with auth-db-pls
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "myapp",
    "name": "messages",
    "columns": [
      { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
      { "name": "room_id", "type": "String", "partitionKeyOrder": 1 },
      { "name": "user_id", "type": "String" },
      { "name": "body", "type": "String" },
      { "name": "sent_at", "type": "Timestamp" }
    ],
    "authMode": "auth-db-pls",
    "permissionDimension": "chat_room",
    "permissionColumn": "room_id"
  }'
```

Then grant the user access to specific partitions:

```bash
# Grant Alice read+write access to chat room 42. The path takes her user id, a GUID: the `id` that
# POST …/auth/admin/users returned for her (a name or email in its place is a 404).
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants \
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
  -d '{ "database": "myapp", "table": "messages", "orderBy": [{ "column": "sent_at", "descending": true }], "limit": 50 }'
```

This is the **cross-partition fan-out** pattern — the most common query for chat, financial, and group-membership applications. Alice's granted partitions form the implicit filter. See [Cross-Partition Fan-Out Queries](#197-cross-partition-fan-out-queries) for more detail.

### 19.4.3 Targeted and Multi-Partition Queries

When Alice specifies a partition filter, Aouda validates that she has access to it:

```bash
# Returns messages from room 42 — Alice has a grant, succeeds
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "myapp", "table": "messages", "where": { "and": [{ "column": "room_id", "op": "eq", "value": "42" }] } }'

# Returns 403 — Alice has no grant for room 99
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "myapp", "table": "messages", "where": { "and": [{ "column": "room_id", "op": "eq", "value": "99" }] } }'
```

Multi-partition `IN` filter: Aouda intersects the requested set with Alice's grants and routes only to the allowed intersection:

```bash
# Rooms 42 and 55 are in Alice's grants; room 99 is not — only 42 and 55 are queried
curl -X POST http://localhost:5433/api/databases/myapp/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "myapp",
    "table": "messages",
    "where": { "and": [{ "column": "room_id", "op": "in", "value": ["42", "55", "99"] }] }
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
# Grant Bob (user id 550e8400-…-446655440001) read-only access to room 42 (he can view but not post)
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440001/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
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
  -H "Content-Type: application/json" \
  -d '{ "email": "svc-quote-feeder@internal" }'
# → { "id": "550e8400-e29b-41d4-a716-446655440002", ... }

# 2. Grant it access to exactly the partitions it should touch (same endpoint as for a human user).
#    `dimension` is the table's permissionDimension (`quote_source`), byte-for-byte (case-sensitive). The grant names no
#    column: the table's permissionColumn (`Source`) is what the key is compared with.
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/550e8400-e29b-41d4-a716-446655440002/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "quote_source", "partitionKey": "oslo_bors", "accessLevel": "write" }'

# 3. Create a custom API key linked to that user
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "oslo-bors-feeder",
    "kind": "custom",
    "userId": "550e8400-e29b-41d4-a716-446655440002",
    "roles": [{ "role": "db_writer" }]
  }'
# → { "key": "mk_...", "userId": "550e8400-e29b-41d4-a716-446655440002", ... } — the key is shown once; store it like a password

# The feeder authenticates with that static key going forward (rows as column arrays: Lead S12, 0.6.0):
curl -X POST http://localhost:5433/api/databases/finance/tables/quotes/rows \
  -H "Authorization: Bearer mk_..." \
  -H "Content-Type: application/json" \
  -d '{ "database": "finance", "columns": ["id", "Source", "instrument_id", "bid", "ask"], "data": [[1], ["oslo_bors"], ["EQNR"], [289.10], [289.30]] }'
# → 200 — granted partition

curl -X POST http://localhost:5433/api/databases/finance/tables/quotes/rows \
  -H "Authorization: Bearer mk_..." \
  -H "Content-Type: application/json" \
  -d '{ "database": "finance", "columns": ["id", "Source", "instrument_id", "bid", "ask"], "data": [[2], ["bloomberg"], ["EQNR"], [289.10], [289.30]] }'
# → 403 AUTH_PLS_GRANT_NOT_FOUND — not granted, exactly as it would be for a JWT session
```

**Do not** reach for `mk_svc_` for this instead. It is a full, audited bypass of PLS and RLS on every table of its database (see the credential table in [§19.3](#193-mode-1-jwt-claim-default)) — appropriate when the caller is genuinely trusted with the whole database, not when it should be limited to the `oslo_bors` grant in `quote_source`.

`userId` is only accepted on `kind: "custom"` keys — `anon`, `service_role`, `public`, and `server_admin` stay singleton, system-managed credentials and reject it with `400 INVALID_REQUEST`. Revoke the key (`DELETE .../admin/api-keys/{id}`) to cut the service off immediately, or delete the specific partition grant to narrow its access without rotating the credential.

---

## 19.5 Mode 3: `auth-db-rls` (Row-Level Security)

Use `auth-db-rls` when access must be determined at the **row level** within a partition — for example, "see only your own records, or records from your team."

Aouda RLS does **not** evaluate policies per-row at query time. Instead, it resolves the predicate once from the auth DB (session cache hot path) and **injects it as a WHERE clause** before the query executes. The columnar scan engine evaluates it like any other filter — once, not once per row. This eliminates per-row evaluation overhead entirely.

### 19.5.1 Setup: Define a Resolver

Resolvers are **admin API only** — they are not part of `schema apply`. Create them with `POST /api/databases/{db}/auth/admin/rls-resolvers` (service key or `db_admin`). `resolverType` is required on POST and stored; evaluation **ignores** it. Use `"ColumnMatch"`.

**A resolver names no table** (**BL-1176, 0.7.0**). It is a named policy in the auth database: rules over attribute names, with
values from the user id, a literal or a grant dimension. A table binds it with `rlsResolverName`, and that is the only binding: one
resolver can serve several tables, in any database linked to the auth database, as long as each has the columns its rules name. A
resolver **name is unique** in its auth database — a second create with the same name is refused with `AUTH_RESOLVER_NAME_CONFLICT`.
Up to 0.6.0 a resolver carried a `targetTable`: it bound nothing, and two resolvers with one name but different `targetTable`s were
both accepted, after which every table naming that resolver got whichever loaded first. The field is gone from the create body, the
response and the list filter. An auth database created before this change still has the column and refuses resolver creates with a
message naming the one-time fix (drop `_rls_resolvers.target_table` with the server admin token).

`valueConfig` on the wire is a **string**. Value sources are the code names (`UserId`, `Literal`, `PartitionGrant`). Older docs that said `auth-db-lookup` / `auth-db-grants` / `role-check` named things that were never in the evaluator.

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sales_access",
    "description": "Restricts sales rows to records owned by or shared with the user",
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

**A literal is bound to its column's type** (**BL-1015, 0.4.0**). `valueConfig` is a string, and the rule's value is read as the column's type wherever the rule is applied — a query, a subscription's change events, a materialized query's rows and the write check alike: `"true"` matches a `Bool` column's `true`, `"05"` an integer 5, `"2026-10-12T21:00:00Z"` a `Timestamp`, `"2026-10-12"` a `Date`, `"10.5"` a `Decimal(p,s)` 10.50, a `Guid` in either case. A literal that does not convert to the column's type (`"yes"` for a `Bool`) denies — the rule matches nothing, for `ne` too. (0.3.0 compared a literal with a row as text outside the query path, so a `Bool` column never matched `"true"` there, and a subscriber could receive events its rule hid from a query; the [write-side fixture](https://github.com/aoudadb/aoudadb.github.io/tree/main/examples/p43-write-side) uses a `String` column, which works either way.)

### 19.5.2 Setup: Create the RLS Table

```bash
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "myapp",
    "name": "sales",
    "columns": [
      { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
      { "name": "company_id", "type": "String", "partitionKeyOrder": 1 },
      { "name": "owner_id", "type": "String" },
      { "name": "team_id", "type": "String" },
      { "name": "amount", "type": "Decimal", "precision": 18, "scale": 2 }
    ],
    "partitionLevelSecurity": true,
    "authMode": "auth-db-rls",
    "rlsResolverName": "sales_access"
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

The [write-side fixture](https://github.com/aoudadb/aoudadb.github.io/tree/main/examples/p43-write-side) uses a SenderId-only write-check so a user can insert a stamped message into a private room they cannot **read**.

| Write Operation | Write-check matches row? | Result |
|---|:---:|:---:|
| INSERT | Yes | Allowed |
| INSERT | No | 403 |
| UPDATE → visible row | Yes | Allowed |
| UPDATE → invisible row | No | 403 |
| Admin (null predicate) | N/A | Always allowed |

---

## 19.6 Combined PLS + RLS

A table can use **both** partition routing and row filtering. The working configuration is **`authMode: auth-db-pls` plus `rlsResolverName`** (and `permissionDimension` plus `permissionColumn` for the PLS grants). Setting `auth-db-rls` together with `permissionDimension` is a **schema validation error** (fail-closed).

```bash
curl -X POST http://localhost:5433/api/databases/myapp/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "myapp",
    "name": "portfolio_data",
    "columns": [
      { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
      { "name": "portfolio_group_id", "type": "String", "partitionKeyOrder": 1 },
      { "name": "owner_id", "type": "String" },
      { "name": "instrument", "type": "String" },
      { "name": "value", "type": "Decimal", "precision": 18, "scale": 2 }
    ],
    "partitionLevelSecurity": true,
    "authMode": "auth-db-pls",
    "permissionDimension": "portfolio_group",
    "permissionColumn": "portfolio_group_id",
    "rlsResolverName": "portfolio_access"
  }'
```

**Enforcement sequence for a query:**
1. PLS resolves which partition groups the user is granted (`portfolio_group` dimension).
2. Fan-out routes the query to all granted partition groups.
3. RLS resolves the `portfolio_access` predicate and injects it as a WHERE clause into each partition sub-query.
4. Results are filtered and merged.

PLS and RLS are **conjunctive** (AND). There is no cross-layer OR.

**Joins onto a restricted table are refused** (**architecture review, 0.3.0**). PLS and RLS are applied as predicates
on the queried (base) table, and a join reads its targets unfiltered — so a query or named query that joins a table the
caller's PLS or RLS would filter (or that the caller may read nothing of) is refused with `403 AUTHORIZATION_DENIED`,
naming the table. A join is allowed only onto tables the caller may read without restriction (an RLS rule that adds no
predicate for this caller, such as an admin pass-through, counts as unrestricted), and every joined table needs the same
grant as the base table. Query the restricted table directly instead. Before, a join read such a table whole. **BL-818**
tracks carrying the restriction onto the join side. See [HTTP API — joins and authorization](../reference/http-api.md#post-apidatabasesdbquery).

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

All endpoints are under `/api/databases/{db}/auth/admin/users/{userId}/partition-grants` and require a `service_role` key, `db_admin` user JWT, or server admin token. `{userId}` is the user's id and `{grantId}` the grant's, both GUIDs — the `id` their create call returned; anything else in their place is a `404`. `grantedBy`, when given, is a user id too.

### Create a Partition Grant

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dimension": "chat_room",
    "partitionKey": "42",
    "accessLevel": "write",
    "grantedBy": "550e8400-e29b-41d4-a716-446655440009"
  }'
```

Response (201 Created):

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "userId": "550e8400-e29b-41d4-a716-446655440000",
  "dimension": "chat_room",
  "partitionKey": "42",
  "accessLevel": "write",
  "grantedBy": "550e8400-e29b-41d4-a716-446655440009",
  "createdAt": "2026-03-26T12:00:00Z"
}
```

`accessLevel` must be `"read"`, `"write"`, or `"admin"`. A missing or empty `dimension`, or a missing or `null` `partitionKey`,
returns 400 `AUTH_GRANT_INVALID`.

**`partitionKey` is taken verbatim** (**BL-1192, next train**). It is the partition's value, stored, listed and compared exactly
as sent: `""` grants the empty-string partition, `" "` a different one, and `" a"` is not `"a"` — every partition a write can create
can be granted. Nothing is trimmed. Up to 0.8.0 the endpoint refused an empty or white-space key and trimmed the others, so
`" a"` was stored as `"a"` and opened the `a` partition; send the key you mean.

On a `jwt-claim` table the key is the caller's tenant claim, not a grant, and an empty or white-space claim is treated as **no
claim** (`403 AUTH_PLS_TENANT_CLAIM_MISSING`): an identity provider's "unset" must not read the `""` partition. To give users the
`""` partition, use `auth-db-pls` and grant it.

**`dimension` is an opaque entitlement name, and it is case-sensitive** (**BL-1176, 0.7.0**). A grant names a dimension and a key,
nothing else: no database, no table, no column. Every `auth-db-pls` table whose `permissionDimension` is that string honours it, in
every database linked to this auth database, and compares the key with the column that table declares as `permissionColumn`. The
dimension does not have to look like a column name, and spelling it like one selects nothing: `fx_source` for the fx tables and
`rates_source` for the rates tables keeps one `MORN` grant from reaching both, though both compare it with a column named `Source`.

The match is **byte-for-byte** (`StringComparison.Ordinal` — `"fx_source"` ≠ `"FX_Source"`). Creation does **not** validate or
normalize against any table: a grant with the wrong casing returns `201` and looks fine on read-back, then every insert/query against
the table fails `403` (`Partition '…' is not in the user's grant set for dimension 'fx_source'`). Copy the `permissionDimension`
string from the schema; do not lowercase it. Partition **keys** are also compared ordinal-case-sensitive (they are data). Engine work
to case-fold or reject a casing mismatch at grant-create time is BL-430.

### List Partition Grants

```bash
# All grants for a user
curl http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants \
  -H "Authorization: Bearer <admin-token>"

# Filtered by dimension
curl "http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants?dimension=chat_room" \
  -H "Authorization: Bearer <admin-token>"
```

### Delete a Partition Grant

```bash
curl -X DELETE http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants/7c9e6679-7425-40de-944b-e07fc1f90ae7 \
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

`resolverType` is required on create and stored; evaluation ignores it. Use `"ColumnMatch"`. A resolver names no table (it is bound by a
table's `rlsResolverName`) and its `name` is unique in the auth database (**BL-1176, 0.7.0**; `targetTable` is gone).

**Value sources (code names — these are the only ones `Evaluate` understands):**

| Value Source | `valueConfig` (string) | Description |
|---|---|---|
| `UserId` | `"{}"` (ignored) | Authenticated user's id |
| `Literal` | the comparison **string** (not an object) | Static value. Bool columns do not match `"true"` — use String |
| `PartitionGrant` | `{"dimension":"<name>"}` | User's granted partition keys for that dimension. Empty grants deny that arm. The dimension must be named: a bare `"team"`, `"{}"` or an object without `dimension` is refused at create and PATCH (`AUTH_RESOLVER_INVALID`) and a stored one denies (**BL-1176, 0.7.0**; up to 0.6.0 a bare string was read as the dimension) |
| `PartitionGrant` (pass-through) | `{"role":"<name>","effect":"allow-all"}` | If the user has the role, resolver returns null (full access) |
| `Claim` | any | Deny sentinel (not implemented — BL-315). Do not use |

**Combinators:** `And` or `Or` on rule N — how N joins with N+1. Last rule has `combinator: null`. Default if omitted is `And`.

**`writeCheckRules`:** optional second rule list. Present ⇒ write-check **replaces** read. Absent ⇒ write-check = read.

**A stored rule is either a read rule or a write-check rule** — the admin API records which list it came from. A rule with no
kind, or a kind the server does not know, **denies** reads and writes (fail closed). (**BL-980, 0.4.0**) Up to 0.3.x a
rule stored with no kind — only an auth database from before write-check rules had them — was read as a read rule; such a
database is not upgraded any more (see [defaults](index.md#23-defaults-and-zero-config-behavior)), so re-create its resolvers.

### List Resolvers

```bash
# All resolvers, with their rules (a resolver names no table, so there is no table filter — BL-1176, 0.7.0)
curl http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers \
  -H "Authorization: Bearer <admin-token>"
```

### Get Resolver (with rules)

`{resolverId}` is a GUID: the `id` the create call returned (or the list shows).

```bash
curl http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/9b2d6c1e-4f3a-4e8b-a5d7-2c1f0e9a8b7c \
  -H "Authorization: Bearer <admin-token>"
```

Response includes the resolver metadata and its ordered rules array.

### Update Resolver

```bash
curl -X PATCH http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/9b2d6c1e-4f3a-4e8b-a5d7-2c1f0e9a8b7c \
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
curl -X DELETE http://localhost:5433/api/databases/myapp/auth/admin/rls-resolvers/9b2d6c1e-4f3a-4e8b-a5d7-2c1f0e9a8b7c \
  -H "Authorization: Bearer <admin-token>"
# 204 No Content on success
# 404 AUTH_RESOLVER_NOT_FOUND if resolver does not exist
```

### Worked example — public OR member + identity stamp

Published fixture (byte-identical in the engine tree): [`examples/p43-write-side/`](https://github.com/aoudadb/aoudadb.github.io/tree/main/examples/p43-write-side). Schema apply creates tables; [`auth-setup.json`](https://github.com/aoudadb/aoudadb.github.io/blob/main/examples/p43-write-side/auth-setup.json) is **admin HTTP** (users, roles, resolvers, grants) — proof that resolvers are not schema apply.

- `rooms` — `auth-db-rls`: `id In PartitionGrant{room_membership} Or IsPublic Eq Literal true`. Alice has zero grants and still sees the public room. `IsPublic` is **String**.
- `messages` — read membership; `writeCheckRules` is `SenderId Eq UserId` only. Alice can insert a stamped row into a private room she cannot read.
- `notes` — `plsClaimBinding: "subject"` + `"derived": { "identity": "subject" }` on `UserId`.

Use a user JWT on the **admin listener**. RLS/PLS need a principal; do not put these tables on `mk_pub_*` / data-plane.

---

## 19.10 Reference Use Cases

### Use Case 1 — Chat Application (`auth-db-pls`, hundreds of rooms)

{: .warning }
**Check the volume before copying this shape.** This use case partitions `messages` by `room_id`, and that
is only the right layout when the **table** will hold many full segments (a segment is ~1 000 000 rows)
and reads name the room. A typical chat product does not: tens of thousands of rooms and a few thousand
messages a day across the whole product is about a million messages a year, which is one segment, so
there is no bucket for those rooms to share. A directory per room (`Dedicated`) would be a small segment
per room on top of that. Either way the layout imposes `PARTITION_FILTER_REQUIRED` on every read and
every subscribe for the life of the table. See
[Should this table have a partition key?](../guides/partitioning.md#should-this-table-have-a-partition-key-p45),
then read [the unpartitioned variant](#the-unpartitioned-variant--same-grants-no-partition-key) below —
for most chat applications that is the one to build.

A user belongs to hundreds of chat rooms. In this use case the `messages` table is partitioned by `room_id` — assume it has cleared the rule above. The application grants partition access at room-join time, and revokes it when the user leaves.

```bash
# Grant Alice (user id 550e8400-…-446655440000) write access to 3 rooms (repeat at join time for each room)
curl -X POST http://localhost:5433/api/databases/chat/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "chat_room", "partitionKey": "room_42", "accessLevel": "write" }'

curl -X POST http://localhost:5433/api/databases/chat/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "chat_room", "partitionKey": "room_55", "accessLevel": "write" }'

curl -X POST http://localhost:5433/api/databases/chat/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "chat_room", "partitionKey": "room_99", "accessLevel": "read" }'

# Alice's "all my latest messages" query — fan-out across all her granted rooms
curl -X POST http://localhost:5433/api/databases/chat/query \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "chat", "table": "messages", "orderBy": [{ "column": "sent_at", "descending": true }], "limit": 50 }'
# → Returns 50 most recent messages drawn from room_42, room_55, and room_99

# Alice posts to room_42 (write access) — succeeds
curl -X POST http://localhost:5433/api/databases/chat/tables/messages/rows \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "chat", "columns": ["room_id", "body", "user_id"], "data": [["room_42"], ["Hello!"], ["550e8400-e29b-41d4-a716-446655440000"]] }'

# Alice tries to post to room_99 (read-only) — rejected
curl -X POST http://localhost:5433/api/databases/chat/tables/messages/rows \
  -H "Authorization: Bearer <alice-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "chat", "columns": ["room_id", "body"], "data": [["room_99"], ["Hi there"]] }'
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

# Regular user queries — injected predicate: owner_id = '550e8400-e29b-41d4-a716-446655440000' OR team_id IN ('team_west')
curl -X POST http://localhost:5433/api/databases/crm/query \
  -H "Authorization: Bearer <user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "crm", "table": "sales", "where": { "and": [{ "column": "company_id", "op": "eq", "value": "acme" }] } }'
# → Returns only Alice's own sales or sales shared with her teams

# Company admin queries — no predicate injected (null = full partition access)
curl -X POST http://localhost:5433/api/databases/crm/query \
  -H "Authorization: Bearer <admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "crm", "table": "sales", "where": { "and": [{ "column": "company_id", "op": "eq", "value": "acme" }] } }'
# → Returns all sales records for acme

# Regular user tries to insert a record owned by someone else — rejected
curl -X POST http://localhost:5433/api/databases/crm/tables/sales/rows \
  -H "Authorization: Bearer <user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{ "database": "crm", "columns": ["company_id", "owner_id", "amount"], "data": [["acme"], ["550e8400-e29b-41d4-a716-446655440004"], [5000]] }'
# → 403 AUTH_RLS_INSERT_VIOLATION (row would not be visible to the inserter)
```

---

### Use Case 3 — Financial Platform (`auth-db-pls`, billions of rows on disk)

A financial platform stores billions of security quotes partitioned by their `Source`; grants for it live in the dimension `quote_source`. Users are granted access to specific data providers. Most data resides on disk in a columnar store.

```bash
# Create the quotes table
curl -X POST http://localhost:5433/api/databases/finance/tables \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "finance",
    "name": "quotes",
    "columns": [
      { "name": "id", "type": "Int64", "primaryKeyOrder": 1 },
      { "name": "Source", "type": "String", "partitionKeyOrder": 1 },
      { "name": "instrument_id", "type": "String" },
      { "name": "bid", "type": "Decimal", "precision": 18, "scale": 6 },
      { "name": "ask", "type": "Decimal", "precision": 18, "scale": 6 },
      { "name": "timestamp", "type": "Timestamp" }
    ],
    "authMode": "auth-db-pls",
    "permissionDimension": "quote_source",
    "permissionColumn": "Source"
  }'

# Grant an analyst (user id 550e8400-…-446655440003) access to two data sources
curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/550e8400-e29b-41d4-a716-446655440003/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "quote_source", "partitionKey": "oslo_bors", "accessLevel": "read" }'

curl -X POST http://localhost:5433/api/databases/finance/auth/admin/users/550e8400-e29b-41d4-a716-446655440003/partition-grants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{ "dimension": "quote_source", "partitionKey": "nasdaq", "accessLevel": "read" }'

# Fan-out: latest AAPL quotes from all authorized sources
curl -X POST http://localhost:5433/api/databases/finance/query \
  -H "Authorization: Bearer <analyst-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "database": "finance",
    "table": "quotes",
    "where": { "and": [{ "column": "instrument_id", "op": "eq", "value": "AAPL" }] },
    "orderBy": [{ "column": "timestamp", "descending": true }],
    "limit": 10
  }'
# → Returns AAPL quotes from oslo_bors and nasdaq only
# → Attempts to access bloomberg or other sources return 403

# Revoke access immediately — effective on the next request, no JWT re-issuance. The last segment is the oslo_bors
# grant's id: the `id` its create returned, or GET …/partition-grants lists it.
curl -X DELETE http://localhost:5433/api/databases/finance/auth/admin/users/550e8400-e29b-41d4-a716-446655440003/partition-grants/7c9e6679-7425-40de-944b-e07fc1f90ae8 \
  -H "Authorization: Bearer <admin-token>"
```

**Performance note:** The `quotes` table holds billions of rows on disk in a columnar store — most data is never loaded into memory. Authorization resolution (~0.01ms from the memory-first auth DB) is negligible compared to the I/O cost of reading quote data. This is Aouda's key architectural advantage: even when data tables are on disk at petabyte scale, authorization stays sub-millisecond because it only queries the small, always-memory-first auth tables.
