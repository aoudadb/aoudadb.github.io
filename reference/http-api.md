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
| `Authorization` | On the admin listener, yes. On the data-plane listener, no: no credential acts as `anonymous`. (**BL-1464, 0.16.0**) | `Bearer` one key (`aouda_<id>_<secret>`) or one session token. Sign-up, sign-in, refresh and password reset take no credential; a bearer on those routes is ignored. |

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

### Access: principals, credentials and policy (**BL-1464, 0.16.0**)

A request is decided in one way. The credential resolves to one principal. The principal's statements decide. The route's action and resource are the table below. A credential never grants; it can only narrow.

<a id="credentials-in-a-request"></a>

#### Credentials in a request

| Header | Required | Value |
|---|---|---|
| `Authorization` | On the admin listener, yes. On the data-plane listener, no: a request with no credential acts as `anonymous`. | `Bearer` followed by one key or one session token. |

There is no second credential header. Sign-up, sign-in, refresh, password-reset request and password reset take no credential; a bearer on those routes is ignored.

A key is `aouda_<id>_<secret><checksum>`, 72 characters. `<id>` is 16 lower-case base32 characters and is public. The secret is 43 base62 characters. The checksum is 6 base62 characters, the IEEE CRC-32 of the first 66. A value that is not a key is `401 AUTH_KEY_MALFORMED` before any lookup. `remedy` is `fix-key` with `reason` `shape`, `checksum`, or `retired-format`.

<a id="listeners"></a>

#### Listeners

One process, up to two listeners. The listener is a property of the connection.

| Listener | Bind | No credential | Surface |
|---|---|---|---|
| Admin | `Aouda:Bind` / `Aouda:Port` | `401 AUTH_CREDENTIAL_MISSING` | The full API |
| Data plane | `Aouda:Listeners:DataPlane:Bind` (`host:port`). Unset: there is no data-plane listener. | The `anonymous` principal of the database's governing auth database | Named queries and mutations, auth routes except `auth/admin`, the realtime socket, the probes. Everything else is `404`. |

An unlinked database on the data plane is governed by `_serverauth`. Its anonymous principal is `_serverauth/anonymous`, which holds nothing until a statement is given to it. A credential of an auth database that does not govern the target is `403 AUTH_WRONG_AUTH_DATABASE`.

<a id="get-apiauthwhoami"></a>

#### `GET /api/auth/whoami`

Both listeners. Never `403`. Optional query `database` keeps statements whose resource is `*`, names that database, or begins with it. `server` is not filtered out by a database name.

No credential on the admin listener: `401 AUTH_CREDENTIAL_MISSING` with remedy `sign-in`. No credential on the data plane with `?database=`: `200` as that database's `anonymous`, `"credential": null`, and **no** `remedy` member. No credential on the data plane without `database`: `400 INVALID_REQUEST`.

```json
{
  "principal": {
    "name": "rates-feeder",
    "authDatabase": "auth",
    "id": "00000000-0000-0000-0000-000000000000",
    "source": "declared",
    "disabled": false
  },
  "credential": { "type": "derived-key", "id": "aouda_exampleexampleex" },
  "database": null,
  "listener": "admin",
  "policy": {
    "roles": ["rates-feeder"],
    "attributes": {},
    "statements": [
      {
        "actions": ["write"],
        "resources": ["rates/table/DepositQuote"],
        "where": { "column": "source", "op": "in", "value": ["tullett"] },
        "from": "role:rates-feeder"
      }
    ]
  },
  "permissionVersion": 1
}
```

`credential.type` is `key`, `derived-key`, `limited-key`, or `session`. A session adds `signedInWith` (`password` or `oidc`), `aal`, and for `oidc` also `issuer` and `subject`. `from` is `principal`, `role:<name>`, or `signup`. A stored key's `id` is the public id. Nothing in the body is a secret.

<a id="access-routes"></a>

#### Access routes

Prefix `/api/auth/{authDatabase}` on the admin listener. `{authDatabase}` is compared without regard to case. Every write goes through the store rules: the caller must hold `manage` on the object and must cover every statement it grants. A declared object is `409 DECLARED_IN_CONFIGURATION` (below) after `manage` is checked and before the body is judged. Order: `401`, then `403`, then `409`, then `400`, then the store's other refusals.

| Method | Path | Asks | Body | Result |
|---|---|---|---|---|
| `GET` | `…/principals` | `manage` on `<auth>/principal/*` | | The list |
| `POST` | `…/principals` | `manage` on `<auth>/principal/*` | `{ "name", "description"?, "roles"?, "statements"?, "attributes"?, "password"? }` | `201`. `password` only when `name` is an email. `description` is a string or null. `roles` is an array of names or null. |
| `GET` | `…/principals/{name}` | `manage` on `<auth>/principal/<name>` | | The principal |
| `PATCH` | `…/principals/{name}` | the same | The members it names, replaced | A rename keeps the id. A refused rename writes nothing. `anonymous` takes `statements` and `attributes` only. |
| `DELETE` | `…/principals/{name}` | the same | | `204` |
| `GET` | `…/principals/{name}/credentials` | `manage` on the principal | | `{ id, type, name, source, createdAt, createdBy, expiresAt, parent, revoked, revokedAt }`. A password is `{ "type": "password", "set": true }`. No hash, no key, no root. |
| `POST` | `…/principals/{name}/oidc` | `manage` on the principal; a `jwks.file` also needs `manage` on `server` | `{ "issuer", "audience", "subject", "claims"?, "jwks"? }` | `201`, or `409 AUTH_OIDC_TRUST_OVERLAP`, or `409 AUTH_OIDC_JWKS_CONFLICT` |
| `DELETE` | `…/credentials/{id}` | `manage` on the owner and coverage, or the caller's own credential | | `aouda_<id>` or `oidc_<guid>`. A declared credential or a derived key is `409`. |
| `GET` | `…/roles` | `manage` on `<auth>/role/*` | | Built-ins included, `source: builtin`, read-only |
| `POST` | `…/roles` | the same | `{ "name", "description"?, "statements" }` | `201` |
| `GET` | `…/roles/{name}` | `manage` on `<auth>/role/<name>` | | |
| `PATCH` | `…/roles/{name}` | the same | members replaced | A `name` that is not a string is `400`. A rename is one write. |
| `DELETE` | `…/roles/{name}` | the same | | Built-ins are `409 AUTH_BUILTIN_READ_ONLY` |
| `GET` | `…/signup` | `manage` on `<auth>` | | `{ "enabled": false, "roles": [], "statements": [] }` is the default |
| `PUT` | `…/signup` | the same | `{ "enabled", "roles"?, "statements"? }` | The whole setting. `enabled` is required. |

Store refusals: `403 AUTH_POLICY_DENIED` when `manage` or coverage fails; `400 AUTH_PUBLIC_UNRESTRICTED` for public reach; `400 AUTH_POLICY_INVALID` for a strict-reader problem, the governance rule, or an unknown role; `400 AUTH_ATTRIBUTE_CAP` for an attribute cap; `409 AUTH_NAME_TAKEN` when the name is taken without regard to case; `404 AUTH_PRINCIPAL_NOT_FOUND`, `AUTH_ROLE_NOT_FOUND`, or `AUTH_CREDENTIAL_NOT_FOUND`. A path segment that fails its grammar is `400` and is not echoed. A `2xx` that wrote a statement naming a column its table lacks carries `warnings: [{ "code": "AUTH_STATEMENT_COLUMN_UNKNOWN" | "AUTH_STATEMENT_ARRAY_COLUMN", "pointer", "message" }]`.

<a id="stored-keys"></a>

#### Stored keys

`POST /api/auth/{authDatabase}/principals/{name}/keys`

Asks `manage` on the principal and coverage of its whole policy. Body `{ "name"?, "expiresAt"? }`. `201` `{ "key", "id", "principal", "name", "createdAt", "expiresAt" }`, `Cache-Control: no-store`. The key is in this response once. `anonymous` is `400`. A declared principal is `409`. A past `expiresAt` is `400`. Unknown principal is `404`.

The declaration records `{ "id": "aouda_exampleexampleex", "sha256": "<64 hex>" }`, never the key.

<a id="limited-keys"></a>

#### Limited keys

`POST /api/auth/keys`

Any authenticated principal, on itself. Body:

```json
{ "name": "one-call", "expiresIn": "PT2H", "limit": { "statements": [ { "actions": ["read"], "resources": ["shop/table/orders"] } ] } }
```

`expiresIn` is required, at most `Aouda:Auth:LimitedKeys:MaxLifetime` (default `PT24H`) and not longer than the parent has left. The chain is at most 4 limited keys deep. `201` `{ "key", "id", "principal", "expiresAt", "limit", "parent" }`. `parent` is the key presented or `session:<sid>`. The effective policy is the principal's policy intersected with the limit and every ancestor's limit, on every request and every row.

<a id="revoke"></a>

#### Revoke

`POST /api/auth/{authDatabase}/credentials/{id}/revoke`

`manage` on the owner and coverage, or the caller's own credential. `200` `{ "id", "principal", "revokedAt", "warnings" }`. A derived key's warning names the next version to declare. An id that is not shaped like an id is `400` and is not echoed.

Open sockets end as [Revocation](../auth/credentials.md#revocation) describes: on this node, when the revoke answers; elsewhere, within one heartbeat (default 20 seconds).

<a id="oidc-exchange"></a>

#### OIDC exchange

`POST /api/auth/oidc/token` on both listeners, rate-limited as a sign-in. No credential. Body `{ "token": "<the issuer's JWT>" }`. `200` `{ "accessToken", "expiresAt", "principal" }`. The session lasts until the token's `exp`, at most one hour, and has no refresh token. Every refusal is `401` with a fixed message that does not quote the token. A trust that matches two principals is refused.

<a id="sessions"></a>

#### Sessions

| Method | Path | Body | Result |
|---|---|---|---|
| `POST` | `/api/databases/{db}/auth/signup` | `{ "email", "password" }` | Creates a `source: signup` principal. Closed: `403 AUTH_SIGNUP_DISABLED`. |
| `POST` | `/api/databases/{db}/auth/signin` | `{ "email", "password", "databases"? }` | A token pair. Omitted `databases` means the session has no database limit. |
| `POST` | `/api/auth/signin` | the same | A `_serverauth` principal. |
| `POST` | `…/auth/refresh` | the refresh token | A new pair at the same `aal`. |
| `POST` | `…/auth/signout` | | Revokes the session. |

A session token carries `iss`, `sub` (the principal id), `email`, `sid`, `aal`, `exp`, `iat`, `jti`, and `aud` from its limit. The library may also write `nbf`. It does not carry a role list or a permission list.

Password reset and MFA stay on the routes in [Setup and flows](../auth/setup.md). The admin path segment `users/{id}` takes the principal's id.

<a id="auth-error-envelope"></a>

#### The auth error envelope

Every code in this table uses one body. Null members are omitted. `suggestion`, `detail` and `details` are not written.

```json
{
  "error": "AUTH_POLICY_DENIED",
  "message": "auth/rates-feeder may not write rates/table/DepositQuote.",
  "requestId": "00000000000000000000000000000000",
  "remedy": {
    "kind": "grant",
    "principal": "auth/rates-feeder",
    "statement": { "actions": ["write"], "resources": ["rates/table/DepositQuote"] },
    "owner": "declaration"
  }
}
```

| Status | Code | When | `remedy.kind` |
|---|---|---|---|
| 401 | `AUTH_CREDENTIAL_MISSING` | No credential. The data plane omits `remedy`. | `sign-in` |
| 401 | `AUTH_KEY_MALFORMED` | Not a key: `shape`, `checksum`, or `retired-format`. | `fix-key` |
| 401 | `AUTH_CREDENTIAL_INVALID` | Unknown id, secret mismatch, bad session signature, issuer or audience. | `fix-key` |
| 401 | `AUTH_CREDENTIAL_EXPIRED` | Key or session past `exp`. | `renew` |
| 401 | `AUTH_CREDENTIAL_REVOKED` | Revoked, disabled, ended parent, signed out. | `none` |
| 403 | `AUTH_WRONG_AUTH_DATABASE` | Credential is valid and governs a different database. | `use-credential-of` |
| 403 | `AUTH_POLICY_DENIED` | The statements do not allow it. | `grant` |
| 403 | `AUTH_POLICY_DENIED` | The statements allow it and the credential's limit does not. | `none`, `reason: credential-limit` |
| 403 | `AUTH_ROW_DENIED` | A written row the `where` does not admit. | `grant` or `none` |
| 403 | `AUTH_EMBARGO_UNSUPPORTED` | The surface cannot honour `embargoSeconds`. | `none` |
| 400 | `AUTH_PUBLIC_UNRESTRICTED` | Public reach refused the policy write. | `add-where` or `none` |

A `403` is logged once at Information with the code, the principal, the action, the resource and the remedy. Values in a `where` are not logged. A string shaped like a key is logged as `<redacted>`.

On the data plane, a named artifact the caller may not `execute` is `404` `NAMED_QUERY_NOT_FOUND` or `NAMED_MUTATION_NOT_FOUND`. That `404` is logged as the refusal.

<a id="audit"></a>

#### Audit: `unconditional_access`

A statement with no `where` on a table that another statement restricts writes an audit row of kind `unconditional_access` when it is used. The detail names the principal, the action and the resource. It is a record of a wide statement, not a second grant.

<a id="row-rules-on-data-routes"></a>

#### Row rules on data routes

A `read` is filtered by the caller's `read` statements. A row the `where` does not admit is absent from the response. It is not a `403`.

A `write` or `delete` of a row the `write` statement's `where` does not admit is `403 AUTH_ROW_DENIED`. An update's scope is that `where` alone. `returning` includes only rows the caller's `read` admits.

`embargoSeconds` applies to `read` and `execute`. It does not refuse a write.

`set-identity` is its own action. No other action implies it.

#### The declaration view and its export

(**BL-1463, 0.16.0**) Two reads, `manage` on `server` (an operator), on the admin listener,
answered `Cache-Control: no-store`; neither writes anything, takes the reload's gate or is rate limited:

| Method | Path | Result |
|--------|------|--------|
| GET | `/api/admin/declaration` | The declaration the server runs on: `source` (`file`, `code` for databases an embedding host set in code, `none`), `file`, `overlay`, `environment`, `planHash` (the same as `aouda plan` prints for the same files), `declaration` (the canonical document the plan hash is the hash of: a credential by its public id, a password seed only as set, never a key, hash, root or secret), `databases` (`name`, `kind`, `authDatabase`, `declaresSchema`, `pointer`), and `last` — the last start or reload: `origin` (`start` or `reload`), `at`, `outcome`, `applied`, `summary`, and every `finding` in the plan's shape |
| GET | `/api/admin/declaration/export` | The server's state as declaration text: `{ "declaration": "<aouda.json>", "schemaFiles": { "schema/<db>.aouda.schema.json": "<text>" }, "origins": { "<pointer>": "declared" \| "runtime" }, "notes": [ { "code", "pointer", "message" } ] }` |

`last` moves only when the declaration does: a reload that writes replaces it (and `declaration` and `planHash`); a dry run, a reload
refused for an error and a reload on a node that does not accept writes leave it as it was. At start it holds the offline plan's
findings and those of the start's own check of the access section (a runtime override of a declared principal,
`DECLARED_OBJECT_OVERRIDDEN`, is there).

The export is **everything the server has**, declared and runtime: every database (its `kind`, `authDatabase` and each per-database
field that differs from its default), each data database's live schema (tables, named queries and mutations, materialized queries) as a
schema file, and per auth database its `signup`, roles and principals with their credentials — a stored key as `{ "id", "sha256" }`, a
derived key as `{ "derivedKey": { "version" } }`, an OIDC trust as is — the server auth database's as `server`, and the running
declaration's `keyRoot` by reference (a variable name or a path). `origins` says which object the running declaration already declares.
**The stored keys' `sha256` are the only secret-class values in the answer** (a SHA-256 of a 256-bit key is no key, and the file needs
them); each export is recorded as one `declaration_exported` audit row with counts only, so a node that does not accept writes (a secondary) answers `503 READ_ONLY`: export from the primary. Never exported, each named in `notes`: a password,
its hash or a seed reference (`EXPORT_PASSWORDS_OMITTED`), a revoked key (`EXPORT_REVOKED_KEYS_OMITTED`), a limited key
(`EXPORT_LIMITED_KEYS_OMITTED`), a key with an expiry — the file's keys have none, so it would outlive it (`EXPORT_EXPIRING_KEYS_OMITTED`),
a principal that signed itself up (`EXPORT_SIGNUP_PRINCIPALS_OMITTED`), a session, and the key root (`EXPORT_KEY_ROOT_NEEDED` when a
derived key needs a `keyRoot` the running declaration does not name). Written to a directory and planned against the same server
(`aouda plan --server`), the databases, schemas and declared objects have no changes; a principal or role created at runtime is
`PRINCIPAL_RUNTIME_CONFLICT` / `ROLE_RUNTIME_CONFLICT` there, because a declaration never adopts a runtime object of the same name
(`EXPORT_RUNTIME_NOT_ADOPTED` says so): start a new server from the files, or delete the runtime objects and reload.

#### One writer per declared object

(**BL-1463, 0.16.0**) What the declaration file declares is changed by changing the file and
running `aouda reload` — not through the API. A call that would change a declared object is refused **`409 DECLARED_IN_CONFIGURATION`**
before anything is written, with the message *"{Kind} '{name}' is declared in {file} at {pointer}; change the declaration, then run
`aouda reload`."* (the name as the server spells it, the file and the JSON pointer of the member; the code is in `code` on the data and
admin routes and in `error` on the `/api/auth/...` routes; there is no `remedy` object):

| Declared object | Refused | Still allowed |
|---|---|---|
| A database the file declares | `DELETE /api/databases/{db}`; `POST /api/databases` with its name (in any case) | quarantine, unquarantine, backup, restore; rows |
| The schema of a database whose declaration names a `schema` | `POST .../schema/apply` (unless `options.dryRun: true`), every table, column, edge-table, vector-column and materialized-query create, change or drop, `POST .../branches/{name}/merge` with `execute: true`, and a row insert into a missing table that `Aouda:Schema:InferenceMode = Extend` would create | a dry-run apply, `schema/diff`, `schema/seed`, a merge plan, row writes, truncate, `:refresh` |
| A declared principal (and `anonymous`, when the file declares it) | any member but `disabled` (statements, roles, attributes, description, a rename), its deletion, a key minted or an OIDC trust added for it, deleting one of its declared credentials | `disabled` on its own (the emergency action; clearing it is refused when the file itself declares `"disabled": true`), revoking a credential (`POST .../credentials/{id}/revoke`), a limited key it mints, a person's own password change (a declared password is a seed) |
| A declared role | its change, rename and deletion; creating its name | giving it to a runtime principal |
| The `signup` setting the file declares | `PUT /api/auth/{authDatabase}/signup` | — |

A caller that may not change the object gets `403` first and never learns that it is declared; on a declared object the `409` comes
before the body is judged. A database an embedding host declares in code (an in-process test server, the dev server) is not declared in
a file and keeps every route. The emergency actions are reported as `DECLARED_OBJECT_OVERRIDDEN` at every start and reload while the
file disagrees.


#### Route actions

The route table is the action and resource each route asks. A principal is allowed when one of its statements covers that pair. Reads of rows then apply the `where`. The [policy page](../auth/authorization.md#actions) is the meaning of each action.

| Route family | Action | Resource |
|---|---|---|
| `GET` rows, query, count, aggregate, export, subscribe, graph read, vector read | `read` | `<db>/table/<table>` |
| `POST` rows, update, upsert, bulk load | `write` | `<db>/table/<table>` |
| `DELETE` rows | `delete` | `<db>/table/<table>` |
| Named query, including batch slots and subscribe-by-name | `execute` | `<db>/query/<name>` |
| Named mutation | `execute` | `<db>/mutation/<name>` |
| `/admin/*`, `/api/admin/*`, `/api/server/*`, `POST /api/databases` | `manage` | `server` |
| Principals and roles | `manage` | `<auth>/principal/…`, `<auth>/role/…` |
| A column the table stamps from the caller | `set-identity` | the table |

`GET /api/auth/whoami` is `[AuthorizedInHandler]`: it answers for any resolved credential, including one whose policy is empty.

#### A missing database answers 401

On `/api/databases/{db}/…`, a request whose credential is not one the target accepts is `401` — and **a database that does not exist is
one of those cases**, for a `mk_svc_` key as for any other credential. This is deliberate: a `404` for a missing database and a `401` for
a present one would tell anyone holding any key which database names exist. The response is the same for both and says nothing about the
database (**BL-1585**, documented; the public answer is unchanged).

To tell a bad key from a missing database, use what only the operator can see:

- the server log's `Auth failure` warning for the request now ends with *the database in the path does not exist on this server: not
  created yet, still starting, or misspelt; see /ready* when it is the database (**BL-1585, 0.16.0**); the same line without that
  note means the key;
- `GET /ready` lists `database_pending` (declared in `Aouda:Databases`, not created yet) and `database_not_open` (registered, not
  open) with the database as `subject`, and answers `503` until they are gone;
- `GET /api/databases` with a server credential lists the databases that exist.

A start-up script should wait for `/ready` to be `200` before it uses a service key, and treat a `401` after that as the key.

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
| Formula table | (**ADR 0072, 0.14.0**) A token on any read of a table that has an `Expression` column (`/query`, `/query/count`, a join side, a named query, subscribe) — input rows included — is judged by the **formula maintainer's progress**: it is covered once every commit up to the token has been recomputed, and a commit that left a value unchanged covers it. A lapse is `409 TOKEN_UNSATISFIED` whatever `onExceeded` says (`fetchPrimary` does not turn it into a `421`; `fail` answers `409` at once). A replica answers `421 FORMULA_TOKEN_REQUIRES_PRIMARY`; a node whose maintainer is not running, `503 FORMULA_NOT_MAINTAINED`. A read joining a formula table and a materialized query's result is covered as far as both are; a materialized query built over a formula table is not yet judged by the formula maintainer (BL-1486). A snapshot's token and a change event's token are covers (keep the highest), a notice's is not. See [Formulas](../guides/formulas.md#when-values-change-eventual-consistency-and-tokens). |
| Bulk-load commit | Field is `token`, **not** `walPosition` |
| Streaming | Optional `token` on `snapshot`, `snapshot_complete`, `change`, `heartbeat` alongside `version`. `resume_from` remains the change-event sequence. Subscribe may send `at_least` / `wait_ms` / `on_exceeded`. Heartbeat `version` is **not** a WAL sequence. |

Admin replication `walPosition` on `GET /admin/replication/status` is lag observability, not this token.

MQ list/status and `POST …/materialized-queries/{name}/query` stamp `token` as the **maintenance watermark** (`D-9`), not a raw WAL offset. A token-bearing MQ read waits on that watermark.

`POST …/materialized-queries/{name}/query` reads the whole result, held to `Aouda:Query:MaxResultRows` and the read budget like every
materialising read (**BL-776, 0.3.0**): a result over the read budget is `503 MEMORY_BUDGET_EXCEEDED` with `Retry-After` —
or, (**BL-1033, next train**) when the result alone exceeds the most the read path may ever hold on the database, `400 STATEMENT_TOO_LARGE`
with no `Retry-After`; a result over the row ceiling is `400 RESULT_TOO_LARGE` with no `Retry-After` (**release blockers, 0.3.0**; it was a `503`), because
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
| `INVALID_REQUEST` | 400 | Request body is malformed or missing required fields; or request body `database` does not match URL path; or a `where` (or a group inside it, or a `joins[].where`) holds no condition (**BL-1036, next train**; see [Where Clause](#where-clause)) |
| `INVALID_FORMAT` | 400 | (**Lead S12, 0.6.0**) The request names the `format` query parameter (`/query`, a named query's execute or batch). It is no longer read: every JSON result is column arrays (`columns`, `data`), and the binary form is asked for with `Accept: application/vnd.aouda.column-batch-v2`. Any value is refused, `columnar` included, so an old client asking for `rows` is told rather than handed a body it misreads. Drop the parameter |
| `ROW_OBJECTS_UNSUPPORTED` | 400 / 415 | (**Lead S12, 0.6.0**) A write body carries row objects (`rows`, or a named mutation's batch argument given as an array of objects), which no surface reads any more: `POST …/rows`, a branch insert, a named mutation's `batchParam`, the schema seed and `aouda.seed.json`, and a WebSocket `stream_rows` (as its `error` code). A bulk-load `:append` sent as NDJSON (`application/x-ndjson`) is refused the same way with `415`. Send [column arrays](#column-arrays-the-write-body) — `columns`, `data` and, for a cell that is not given, `absent` — or upgrade the client library. Nothing was written |
| `MISSING_TABLE` | 400 | Table name is missing from request |
| `MISSING_DATABASE` | 400 | Database name is missing or empty in request (v2: set the `database` field in the request body) |
| `INVALID_OPERATOR` | 400 | Invalid comparison operator in where clause |
| `INVALID_COLUMN` | 400 | Invalid column name or reference |
| `INVALID_VALUE` | 400 | Invalid value type or format |
| `FRAME_VERSION_UNSUPPORTED` | 415 | (**Lead S09, 0.6.0**) A column-batch body of a version this server no longer reads: an `ACB1` frame, or the retired media type `application/vnd.aouda.column-batch`. The message names the version found and the one expected (`ACB2`, `application/vnd.aouda.column-batch-v2`). Upgrade the client; nothing of the request was applied |
| `RESULT_TOO_LARGE` | 400 | (**release blockers, 0.3.0**) The query's result exceeds `Aouda:Query:MaxResultRows` (default 1 000 000): `/query`, a named query, or `POST …/materialized-queries/{name}/query`. The message names the row count, the ceiling and its key. No `Retry-After`: the same query is refused the same way. Narrow the query, page it (`limit` / `offset`), or have the operator raise the setting. It was `503 MEMORY_BUDGET_EXCEEDED` with a `Retry-After` a retry could not honour. (**LoadScan, 0.5.0**) A `/query` with no page that asks for column-batch frames is streamed, not held, and is never refused this way: ask for frames to export a whole table |
| `STATEMENT_TOO_LARGE` | 400 | (**BL-1033, next train**) The statement **alone** needs more memory than the read path may ever hold on this database — its transient budget (`T15`, a fraction of the database's governed share), the ceiling a read has when no other work is running. A `DELETE` or `UPDATE` (on `…/rows`, in a `rows/batch` — as its first operation — or as a named mutation) whose matched rows, or a read (`/query`, a named query, a branch query, `POST …/materialized-queries/{name}/query`, a subscription's snapshot) whose held result, cannot fit it. **No `Retry-After`: the same statement is refused the same way on an idle server.** Nothing was applied. The message names the bytes the statement needs and the ceiling; `details` says what to do: narrow the statement (a tighter `where`, a `limit`, a `DELETE` in pieces) or have the operator raise the database's share. On a WebSocket it is the `error` frame's `code`, its message ending with that remedy instead of "retry after N s"; in a column-batch frame response it is the error end frame's `code` with `status` 400; an auth endpoint (sign-in, sign-up, refresh, MFA) answers it `400` in the auth error payload, `error: STATEMENT_TOO_LARGE`. Before, it was `503 MEMORY_BUDGET_EXCEEDED` with a `Retry-After`, every time, and a client that honoured it (both SDKs do) retried to its own bound. A statement that fits alone and was refused because other work held the memory is still `MEMORY_BUDGET_EXCEEDED` |
| `ARRAY_COLUMN_UNSUPPORTED` | 400 | (**BL-035, 0.9.0**) An [array column](../guides/array-columns.md) is used where it cannot be: in a primary key, `unique`, `references`, partition or cluster column, `autoIncrement`, a `default` given as text, `derived`, a check, a transform predicate, the permission column or a `memoryFilter`; in a query's `where` (a null test included), `orderBy`, `groupBy`, aggregate (`count(col)` included), `distinct`, `selectExpr` input, join key or `perKey` key; in a `setExpr`, a named mutation's `where` or `orderBy`, or a `min` / `max` / `maxLength` / `enum` constraint on a parameter it is written from; in an row conditions rule (on `/query` and a join side, a named query, `POST …/materialized-queries/{name}/query`, at subscribe, and on an update or delete: `PATCH` / `DELETE …/rows`, `POST …/rows/batch`, a named mutation's `update` or `delete` — an insert checked against such a rule is denied with `403`); in a `DELETE …/rows` or `rows/batch` delete's `orderBy`; in a subscription `filter` or `conflate.key` (an `error` message with this code); in a bulk-load route or tee under `applyTransforms` that copies it into a column of another type or a scalar into it; or as an edge table's source, destination or label column (**BL-1249, next train**: an array **property**
of an edge table is accepted at create and at `POST …/tables/{name}/columns` — it was refused, with the clause "a column of an edge
table", since 0.9.0). The `error` names the column, its type and the clause: `ARRAY_COLUMN_UNSUPPORTED: column 'Samples.D' is Double[]; an array column cannot be used in a where (an array column can only be selected — ADR 0067 D-5).` In a named query or materialized definition applied with `schema apply`, the entry is `Failed` and its reason starts with the code, instead of a `400`. A bad **value** (a non-finite or null element, an over-limit array) is not this code: it is the surface's own invalid-value code, `NAMED_QUERY_BIND_FAILED`, `NAMED_MUTATION_BIND_FAILED` or `INVALID_REQUEST` |

#### Resource Errors (4xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TABLE_NOT_FOUND` | 404 | The specified table does not exist |
| `COLUMN_NOT_FOUND` | 404 | The specified column does not exist |
| `TABLE_EXISTS` | 409 | A table with the specified name already exists |
| `COLUMN_EXISTS` | 409 | A column with the specified name already exists |
| `DECLARATIVE_SCHEMA_DDL_FORBIDDEN` | 400 | HTTP DDL rejected because schema apply created the table. Change it through `POST …/schema/apply`. Applies in every `InferenceMode` (**BL-1177, 0.7.1**). Before, it applied only in `Extend`, and `On` / `Off` accepted the call |
| `PARTITION_KEY_FIXED` | 400 | (**BL-1199, 0.9.0**) A table's partition key is fixed when the table is created. Refused: dropping (`DELETE …/columns/{c}`) or renaming (`PATCH …/columns/{c}` with `newName`) a partition-key column, and a schema document (`POST …/schema/apply`, its dry run, or a branch merge) that changes a table's `partitionKey` or a column's `partitionFunction`, or drops, renames or adds a key column. The message names every reason; nothing was applied. Drop and re-create the table to change its key. Before, schema apply ran the column changes and returned a warning beside the result, and the column routes applied them |
| `DATABASE_NOT_FOUND` | 404 | The specified database does not exist |
| `DATABASE_EXISTS` | 409 | A database with the specified name already exists |
| `BRANCH_EXISTS` | 409 | A branch with the specified name already exists |
| `MERGE_CONFLICT` | 409 | Branch merge has conflicts that must be resolved or forced |
| `NOT_FOUND` | 404 | Generic not-found (used when a more specific code is not available) |
| `PARTITION_FILTER_REQUIRED` | 400 | Query on a partitioned table is missing the required partition key filter. `crossPartitionAccess` waives it and nothing else; on the data-plane listener it is not accepted and the guard decides (**BL-1227, 0.9.0**) |
| `NAMED_QUERY_NOT_FOUND` | 404 | Named-query name is unknown. On the **data-plane listener**, a caller who may not `execute` it (no credential included) also uses this code (same `ProtocolError` envelope as unknown). On the admin listener that refusal is `403 AUTH_POLICY_DENIED`; no credential there is `401 AUTH_CREDENTIAL_MISSING`. A table `read` does not `execute` the artifact (**BL-1464, 0.16.0**). A batch slot the caller may not execute is this code in that slot, on both listeners. |
| `NAMED_QUERY_BIND_FAILED` | 400 | Argument bind failed (type, constraint, or missing required param) |
| `NAMED_QUERY_PARAM_REQUIRED` | 400 | A required named-query parameter was omitted |
| `NAMED_QUERY_BATCH_EMPTY` | 400 | `queries` is missing or empty |
| `NAMED_QUERY_BATCH_TOO_LARGE` | 400 | Batch exceeds 32 elements (`ProtocolConstants.MaxNamedQueryBatchSize`) |
| `NAMED_QUERY_BATCH_MUTATION` | 400 | Batch included a named-mutation name (read-only envelope) |
| `NAMED_MUTATION_NOT_FOUND` | 404 | Named-mutation name is unknown. On the **data-plane listener**, a caller who may not `execute` it also uses this code. On the admin listener that refusal is `403 AUTH_POLICY_DENIED`; no credential there is `401 AUTH_CREDENTIAL_MISSING`. A table `write` does not `execute` the artifact (**BL-1464, 0.16.0**). |
| `NAMED_MUTATION_BIND_FAILED` | 400 | Named-mutation argument bind failed |
| `NAMED_MUTATION_RETURNING_OVERFLOW` | 400 | `RETURNING` would exceed `MaxReturningRows`; the call fails closed (no `rowsTruncated`) |
| `ACCESS_SURFACE_TOO_MANY_IDENTITIES` | 400 | Access-surface diff posted more than 32 fixture identities |
| `AUTH_IDENTITY_INVALID` | 400 | ``aouda.json`` / posted identities document failed validation |
| `SNAPSHOT_TOO_LARGE` | 400 | Subscribe snapshot would exceed `MaxSnapshotRows` (default 100 000) |
| `SNAPSHOT_OVERFLOW` | 400 | Change-event buffer overflowed while paging the snapshot; subscribe fails (not a mid-snapshot `gap`) |
| `BULK_LOAD_TRANSFORM_INTENT_REQUIRED` | 400 | Bulk load into a table with derived columns, checks, or transforms without `applyTransforms` or `preTransformed` |
| `BULK_LOAD_TRANSFORM_INTENT_CONFLICT` | 400 | Both transform-intent flags set |
| `BULK_LOAD_SERVER_TIME_REQUIRES_TRANSFORMS` | 400 | `preTransformed` load into a table with a server-time column; use `applyTransforms` (**NativeClients, 0.4.0**) |
| `BULK_LOAD_IDENTITY_REQUIRES_TRANSFORMS` | 400 | `preTransformed` load into a table with an identity column; use `applyTransforms` (**BL-1278, BL-1170, 0.9.0**) |

#### Authentication Errors (4xx)

Auth errors use the `AuthErrorPayload` shape (see [Auth Error Responses](#auth-error-responses) above) where the `"error"` field is the machine-readable code.

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_TOKEN_MISSING` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_TOKEN_INVALID` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_TOKEN_EXPIRED` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_DATABASE_NOT_IN_ALLOWANCE` | — | Not produced (**BL-1464, 0.16.0**). A session used outside its allowance is `403 AUTH_POLICY_DENIED` with remedy `none` and `reason: credential-limit`. See [the auth error envelope](#auth-error-envelope) |
| `AUTH_TOKEN_REVOKED` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_API_KEY_INVALID` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_API_KEY_REQUIRED` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `UNAUTHORIZED` | 401 | Not produced (**BL-1464, 0.16.0**). No credential on the admin listener is `AUTH_CREDENTIAL_MISSING` |
| `NOT_AUTHENTICATED` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTHORIZATION_DENIED` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `INSUFFICIENT_PERMISSIONS` | 403 | Not produced (**BL-1464, 0.16.0**). A refused action is `AUTH_POLICY_DENIED`. |
| `AUTH_KEY_ROUTE_MISMATCH` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_INVALID_CREDENTIALS` | 401 | Signin credentials are invalid (wrong password or non-existent email) |
| `AUTH_ACCOUNT_LOCKED` | 423 | Account is temporarily locked due to too many failed attempts. `Retry-After` header is set. |
| `AUTH_ACCOUNT_DISABLED` | 423 | A refresh presented for a principal an administrator disabled. The body is the auth payload and includes `suggestion` (not the remedy envelope). That principal's access token is `401 AUTH_CREDENTIAL_REVOKED`. Disabling the principal ends its open sessions |
| `AUTH_RATE_LIMITED` | 429 | Too many auth requests — rate limit exceeded. `Retry-After` header is set. |
| `RELOAD_REFUSED` | 422 | (**BL-1427, 0.14.0**) `POST /api/admin/reload`: the declaration has an `error` finding (what the next start would refuse); nothing was changed. The body is the plan with every finding |
| `RELOAD_PARTIAL` | 207 | (**BL-1427, 0.14.0**) A reload stopped part-way (`failedStep`); the steps before it are applied, `/ready` says `reload_failed`. Reload again |
| `RELOAD_IN_PROGRESS` | 409 | (**BL-1427, 0.14.0**) A reload or a restore is reconciling the declaration; not queued. `Retry-After` is set |
| `RELOAD_RATE_LIMITED` | 429 | (**BL-1427, 0.14.0**) One reload per 5 s, one dry run per 1 s. `Retry-After` is set |
| `RELOAD_CANDIDATE_NOT_APPLIED` | 400 | (**BL-1463, 0.14.0**) `POST /api/admin/reload` with a body and without `dryRun=true`: a posted declaration is only ever planned. The body is not read and nothing changes. Add `dryRun=true` to plan it, or reload without a body to apply the server's own files |
| `MEMORY_BUDGET_EXCEEDED` | 503 | (**BL-850, 0.3.0**) Sign-in, sign-up, password set / change / reset and an admin's create-user: the password hash (Argon2id, 64 MiB while it runs) could not get its memory from the server's queue within 10 s. Nothing was changed; `Retry-After` is the queue's estimate. Hashes queue for memory rather than run unbounded, so a burst of sign-ins waits instead of exhausting the heap (it answered `500` before). An admin's user edit, API-key revoke or row conditions-statements create refused for capacity answers this (or `WAL_CAPACITY_EXCEEDED`) too, where it used to read as a 400 or a 409 "email exists" (WorkloadCore group 6 review). A token **refresh** refused for capacity answers this too (**BL-841, 0.3.0**; it was a `500`), and the refresh token stays live: retry with the same token. |
| `AUTH_SIGNUP_FAILED` | 400 | Signup could not be completed (generic message to prevent information leakage) |
| `AUTH_SIGNUP_DISABLED` | 403 | Self-service registration is disabled for this database (``signup.enabled`` is false) |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | Refresh token is invalid, expired, or revoked. Also the losing call of two concurrent refreshes presenting one token (**BL-841, 0.3.0**): exactly one refresh succeeds, and the other revokes the token family — including the token the winner just received. Refresh a shared session from one place |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | Email is already registered in this auth database |
| `AUTH_PASSWORD_TOO_WEAK` | 400 | Password does not meet the minimum password policy |
| `AUTH_INVALID_EMAIL` | 400 | Email is blank or not a valid email format |
| `AUTH_PLS_TENANT_CLAIM_MISSING` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_PLS_TENANT_CLAIM_MISMATCH` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_PLS_WRITE_SCOPE_VIOLATION` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_ENTITLEMENT_NOT_FOUND` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_ENTITLEMENT_INSUFFICIENT_ACCESS` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_PLS_UNSUPPORTED_OR_SHAPE` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_KEY_LISTENER_MISMATCH` | 401 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `CLIENT_CONSUMER_OVERFLOW` | none (client side) | Never on the wire: `Aouda.Client` ends one subscription consumer that left more than `SubscriptionConsumerQueueCapacity` (default 10 000) events unread, as an `AoudaRequestException` with this `ErrorCode` (**BL-1421, 0.12.0**). Only that consumer ends; there is no resume, subscribe again for a fresh snapshot. The raising options are `AoudaClientOptions.SubscriptionConsumerQueueCapacity` and `SubscribeOptions.ConsumerQueueCapacity`; see the [.NET client](../clients/dotnet.md). `@aouda/client` has the same code in its next release (not yet published) |
| `IDENTITY_QUOTA_EXCEEDED` | 429 | Data-plane per-identity request quota exceeded. `Retry-After` is set. |
| `CONNECTION_LIMIT_EXCEEDED` | WS `error` frame before auth / 429 | The server's global connection pool (`Aouda:WebSocket:MaxConnections`) is full. Retry later. |
| `IDENTITY_CONNECTION_LIMIT_EXCEEDED` | WS `auth_error` / 429 | (**BL-1383, 0.11.0**) The identity already holds `MaxConnectionsPerIdentity` (default 16) connections, WebSocket and long-poll together. Sent inside the handshake, after identity resolution and before `auth_ok`; long-poll `connect` answers 429. A client must not reconnect in a loop. |
| `SUBSCRIBE_RATE_EXCEEDED` | WS error | (**BL-1383, 0.11.0**) The identity's subscribe token bucket is empty (an attempt refused for another reason still costs a token). The frame carries `retry_after_ms`; a long-poll `/send` also sets `Retry-After`. |
| `AUTH_GRANT_INVALID` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_GRANT_TABLE_NOT_FOUND` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_GRANT_NOT_APPLICABLE` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_EMBARGO_UNSUPPORTED` | 403 / WS error | The caller holds an embargo on the table and the surface cannot apply its cutoff: a write (insert, update, delete, upsert, truncate, `rows/batch`, a named mutation, bulk-load `:begin` and every `:append`, a write stream's `stream_rows`), a materialized query (its query endpoint, a `/query` or named query that reads it, a subscription to it), graph traversal, or vector `:nearest`. A branch query of a base table applies the cutoff; a branch query of a materialized result over an embargoed source is refused (**BL-1161, BL-1298, 0.9.0**). A write that names no table (a schema seed, a branch insert) is refused for any embargo holder. Not retryable with the same credential (**BL-418, 0.9.0**) |
| `AUTH_GRANT_DIMENSION_CAP` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_GRANT_PRINCIPAL_CAP` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_RESOLVER_INVALID` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `AUTH_CLAIM_INVALID` | 400 | Custom user claim key is blank or invalid |
| `IDENTITY_SOURCE_UNRESOLVABLE` | 400 | Identity derived source could not be resolved from the principal |
| `IDENTITY_STAMP_REQUIRED` | 400 | Service role omitted a required identity-stamped column |
| `SCHEMA_IDENTITY_COLUMN_NOT_BINDABLE` | 400 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `SCHEMA_SERVER_TIME_COLUMN_NOT_BINDABLE` | 400 | A named mutation's `values` / `set` / `setExpr` names a server-time column (**NativeClients, 0.4.0**) |
| `SCHEMA_UNKNOWN_MEMBER` | 400 | (**BL-1460, 0.14.0**) A schema document (`schema/apply`, `schema/diff`, their request bodies, a schema file read by the CLI or at start, an `--env` overlay) has a member the format does not have, or a known member in another case: member names are case-sensitive. Nothing is applied. `error` names every such member with its JSON pointer and, when one is close, the member meant: `unknown member 'nulable' at /tables/orders/columns/status; did you mean 'nullable'?`. At most 20 are listed, then `and N more.`; a name over 64 characters is cut to 64 plus `…` and gets no suggestion. Fix: rename or remove the member. Before, it was dropped without a word |
| `SCHEMA_OVERLAY_MEMBER_NOT_ALLOWED` | — | (**BL-1460, 0.14.0**) An environment overlay (`<base>.<env>.json`) carries a member the merge does not apply: anything but `$schema`, `extends`, `settings.durability` and an existing table's `policy` and `durability`. Raised where an overlay is read (`aouda plan`, the CLI's `--env`, the start's `SchemaEnvironment`), not by an HTTP endpoint; `aouda plan` and the start report it as the finding `SCHEMA_OVERLAY_INVALID` ([Declaration Finding Codes](plan-codes.md)). Fix: move the member to the base file. Before, it was dropped |
| `EXPRESSION_OVERFLOW` | 400 | (**BL-1481, 0.15.0**) A `setExpr`, or a derived column's expression, overflowed 64-bit integer or 18-digit decimal arithmetic for a row; nothing written |
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
| `TOKEN_UNSATISFIED` | 409 | Token or lag budget still unmet after `waitMs` (or immediately when `onExceeded=fail`). Never a stale answer. (**ADR 0072, 0.14.0**) On a read of a table with an `Expression` column the wait is for the formula maintainer to recompute every commit up to the token, and it is `TOKEN_UNSATISFIED` whatever `onExceeded` says. |
| `TOKEN_FETCH_PRIMARY` | 421 | Replica cannot satisfy the freshness contract; retry against the current primary (`GET /admin/replication/topology`). Server does not proxy. |
| `FORMULA_TOKEN_REQUIRES_PRIMARY` | 421 | (**ADR 0072, 0.14.0**) A consistency token on a read or subscribe of a table with an `Expression` column reached a replica, which computes no formulas and cannot judge it. Send the read to the primary, or read without a token. |
| `FORMULA_NOT_MAINTAINED` | 503 | (**ADR 0072, 0.14.0**) This node's formula maintainer is not running (a branch, a server whose replication role is not resolved yet, a promoted node until BL-1441 is fixed), so it cannot wait for the formulas. Read here; wait on the primary. Not a sign of overload: the SDKs do not retry it. `explain` is refused too on a node that serves a replica's rows — a replica, or a promoted node until BL-1441 is fixed (**BL-1511, 0.15.0**). Explain on the primary. |
| `EXPR_CELLREF_NOT_ALLOWED` | 400 | (**ADR 0072, 0.14.0**) A `cellRef` node outside a formula (the value of an `Expression` column): in a `setExpr`, a derived column, a named query or mutation, a `selectExpr` or a materialized query's output. |
| `FORMULA_COLUMN_INVALID` | 400 | (**ADR 0072, 0.14.0**) An `Expression` column's declaration, or a later change to its table, breaks a rule of the column type (the Expression column nullable and plain; its driven column a nullable scalar of the same table that nothing else computes or drives; the table with a strict primary key, an ordinary table). The message names the table, the column and the rule; nothing was changed. See [Formulas](../guides/formulas.md#the-column). |
| `FORMULA_INVALID` | 400 | (**ADR 0072, 0.14.0**) A formula is not one valid expression: it does not parse, uses a `param`, an unknown function or operator, a type its driven column cannot hold without loss (the message says what to write, e.g. `round(x, 2)`), is computed by a `setExpr`, or arrives through a transform. The message names the row; nothing was written. |
| `FORMULA_REFERENCE_INVALID` | 400 | (**ADR 0072, 0.14.0**) A formula's `cellRef` names a table that does not exist or a formula may not read (an edge table, an engine table, a materialized query's result over a formula table), a column that does not exist or is an `Expression` column, or a key value no row can hold. |
| `FORMULA_REFERENCE_NOT_PRIMARY_KEY` | 400 | (**ADR 0072, 0.14.0**) A `cellRef`'s key, after the shorthands are resolved against the formula's own row, is not exactly its table's full strict primary key; the message names the key. |
| `FORMULA_CYCLE` | 400 | (**ADR 0072, 0.14.0**) The formulas would read each other in a cycle; the message names its members in order. |
| `FORMULA_DEPTH_EXCEEDED` | 400 | (**ADR 0072, 0.14.0**) A chain of formulas, each reading the next, would be longer than 16; the message names it. |
| `FORMULA_LIMIT_EXCEEDED` | 400 | (**ADR 0072, 0.14.0**) The database would hold more than 100 000 formula cells. Remove formulas, or keep inputs as plain values. |
| `FORMULA_REFERENCE_NOT_READABLE` | 403 | (**ADR 0072, 0.14.0**) A formula reads a row its writer may not read (no read access to the table, a row outside the writer's row or partition conditions, or a row that does not exist and cannot be judged on its key); also a server write that set a formula with no caller to check. The message names the formula row and the reference, never whether the row exists; nothing was written. |
| `FORMULA_VALUE_WRITE_REFUSED` | 409 | (**ADR 0072, 0.14.0**) A write sets the driven column of a row whose formula is set after the write (a formula row's value is computed), or gives a formula and a value in one row. The whole statement is refused, naming the row. Write the formula as null in the same write to make the row an input. |
| `FORMULA_TABLE_REFERENCED` | 409 | (**ADR 0072, 0.14.0**) A DDL would break a formula's reference — drop or rename a table a formula reads, drop, rename or retype a column one reads, change such a table's primary key or loosen its uniqueness, change a formula table's key while it has formula cells, add an Expression column to a source table of a materialized query whose result a formula reads (any table on the query's chain, its upstream queries' sources included) — or change a driven column's type so a formula no longer fits. The message names the cells (through the table routes and `schema/apply`, where it is a failed entry). `TRUNCATE` is allowed. |
| `DECLARED_IN_CONFIGURATION` | 409 | (**BL-1463, 0.16.0**) The call would change an object the declaration file declares — a declared database, the schema of a database that declares one, a declared principal, role, credential or `signup` setting. Nothing was changed; the message names the file and the JSON pointer. Change the declaration, then run `aouda reload`. See [One writer per declared object](#one-writer-per-declared-object) |
| `MQ_NOT_READY` | 409 | Token-bearing read or subscribe against a materialized query that is not `Ready` (building, rebuilding, or error). Distinct from `TOKEN_*`: retry with backoff; do not discard the token. |
| `FRESHNESS_CONTRACT_INVALID` | 400 | Unknown `onExceeded` (including `serveStaleAndRevalidate`), `waitMs` negative or above 30 000. |
| `FRESHNESS_LOOSENED` | 400 | Call site weaker than the named query’s declared budget, or non-`Primary` on fail-safe (name with no `freshness` block). |

#### Server Errors (5xx)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `SERVICE_UNAVAILABLE` | 503 | Service is temporarily unavailable. (**BL-944, 0.4.0**) Also the answer to a refusal no other code names: a request the server refused for capacity with no more specific code (`MEMORY_BUDGET_EXCEEDED`, `WAL_CAPACITY_EXCEEDED`, `WRITE_CONFLICT`) is `503 SERVICE_UNAVAILABLE` with `Retry-After: 10`, never a `500` — nothing was applied; retry after `Retry-After` |
| `SERVER_STARTING` | 503 | The server is still starting (replaying each database's log, then the auth bootstrap, the declared schema files, roles, keys and replication) and is not serving yet. (**BL-944, 0.4.0**) Carries `Retry-After: 5`; poll again after it (`GET /startup` is the probe for this). (**BL-1462, 0.14.0**) The port is open for the whole start, and this answers every caller but the health probes, loopback included |
| `SETUP_REQUIRED` | 503 | The server's data directory has never been set up and nothing is declared (no server key, no `a declared principal`), so it is in setup mode: only setup status, a local `POST /api/auth/setup` and the health endpoints (**BL-1462, 0.14.0**) are served. **No `Retry-After`**, deliberately — an operator ends setup mode, not time; create the first admin |
| `SERVER_AUTH_NOT_CONFIGURED` | 503 | Server authentication is not configured (or its database is not open) for a server-admin route. **No `Retry-After`**, deliberately — an operator fixes it (`aouda setup` or `POST /api/auth/setup`) |
| `INTERNAL_ERROR` | 500 | An internal error occurred |
| `WRITE_APPLIED_RESPONSE_FAILED` | 500 | (**Lead group 3 review, 0.6.0**) The server **applied** the write — an insert, update, delete or upsert on a table's `rows`, a `rows/batch`, a named mutation, a branch insert — and then failed while answering it: waiting for the write concern, building the answer, or running out of heap on the way out. No `Retry-After`. **Do not re-send the request as-is**: it would apply the write again. Read the data to see its effect, and quote the `requestId` when reporting it. Such a failure used to be answered as a capacity refusal (`503 MEMORY_BUDGET_EXCEEDED` with `Retry-After`, "not applied"), which both SDKs re-send, so an insert could land twice. (**BL-1034, next train**) Also the answer when the request timeout fires after the write was applied — a `504 REQUEST_TIMEOUT` there said "not applied" — including a `rows/batch` whose timeout fired after some of its operations were applied (read the data to see which), and an edge or vector insert (`…/edges`, `…/vectors/{column}`), which this code now covers too |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The server could not fit the request in memory now: the memory budget's queue refused it (`Retry-After` is the queue's estimate), or the managed heap hit its hard limit while serving it (`Retry-After: 10`, one sampling tick). The request was not applied; retry after `Retry-After`. (**WorkloadCore S17, 0.3.0**) Never a constant `Retry-After: 1`: every memory refusal carries the governor's estimate for its bytes at the queue's measured service rate, or `10` (the memory broker's next look, `T6`) before any rate is measured or when it has no estimate. (**BL-956, 0.4.0**) The estimate is at most **30 s** (it was 300 s): ask again then, and the next answer carries a fresh estimate. (**WorkloadCore S07, 0.3.0**: a heap exhaustion inside any request, and a query the read path refused, answered `500 INTERNAL_ERROR` before.) A bulk load's `:commit` whose failure came **after** the load's commit point is never this code: see the bulk-load `:commit` errors. (**BL-921, 0.3.0**) **Every endpoint answers a capacity refusal this way** — this code, or `WAL_CAPACITY_EXCEEDED` for the WAL's — never as the client's mistake or a server failure: inserting edges or vectors, reordering a table's columns or seeding a schema while the WAL was full answered `400 INVALID_REQUEST`, and other endpoints' catch-alls `500`. (**BL-1033, next train**) A statement that alone exceeds the read path's ceiling — one no retry can satisfy — is `400 STATEMENT_TOO_LARGE` instead, with no `Retry-After`; this code is the transient refusal, which a retry can satisfy once other work releases its memory. |
| `WAL_CAPACITY_EXCEEDED` | 503 | The WAL is at its refusal line (`T27`): writes to source tables are refused until retention brings it back under `T26`. Nothing was applied; `Retry-After` is the server's estimate from the measured reclaim rate. Retry after it. (**BL-956, 0.4.0**) It is at most **30 s**, and `10` before any reclaim is measured (it was up to 300 s). (**BL-921, 0.3.0**) Answered as this on every endpoint, where some answered `400` or `500` before. |
| `BATCH_PARTIALLY_APPLIED` | 503 | (**Lead group 3 review, 0.6.0**) `POST …/tables/{name}/rows/batch` only: operation `k` (`k` ≥ 1) was refused for capacity. Operations `0` to `k − 1` **were applied**; operation `k` and the ones after it were not. `details` names `appliedOperations=k`, `totalOperations=n` and the refusal's own code. **No `Retry-After`**, deliberately: re-sending the whole batch would apply its first `k` operations twice. Re-send only the remaining operations (`operations[k..]`) as a new batch. A refusal of operation `0` is still the plain `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` with `Retry-After`: nothing was applied. It used to be that plain refusal whatever `k` was, which both SDKs re-send |
| `BATCH_RLS_PREFIX_APPLIED` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `REQUEST_TIMEOUT` | 504 | The request ran past the server's request timeout (`Aouda:RequestTimeoutMs`, 30 s by default; the bulk-load `:append` / `:commit` and `:refresh` endpoints have their own). (**BL-1034, next train**) A data write answered `504` — an insert, update, delete or upsert on a table's `rows`, a `rows/batch`, a named mutation, a branch insert, an edge or vector insert — **applied nothing**: the timeout is honoured only before the write's commit point, so it is safe to retry. A write the server had already applied when the timeout fired is answered `500 WRITE_APPLIED_RESPONSE_FAILED` instead (do not re-send it). Before, a timeout inside a table, branch, database, graph, vector or query endpoint was answered `500 INTERNAL_ERROR` "Failed to …", which a client could not tell from a bug, and an applied write that then timed out was answered `504`. (This row used to name the code `TIMEOUT`; the server has always sent `REQUEST_TIMEOUT`.) |
| `OVERLOADED` | 503 | Server is overloaded |

**`Retry-After` is readable from a browser (**architecture review, 0.3.0**).** Every CORS policy exposes it, so a
browser client can honour it on a 429 or 503 as a server-side client does — the back-off the ingest and capacity
design relies on. Before, it was not exposed and a browser read `null`.

#### Named-query, streaming, and data-plane errors

These also appear as WebSocket `error` `code` values where noted.

(**BL-944, 0.4.0**) **A refusal on a WebSocket is its own code.** A `stream_rows` write, a subscription's snapshot and a
subscription's permission read that the server refused for capacity answer `MEMORY_BUDGET_EXCEEDED` or `WAL_CAPACITY_EXCEEDED`
(message ending "retry after N s"), and a write conflict `WRITE_CONFLICT` — wherever the refusal arose. (**BL-1033, next train**) A snapshot or a
`stream_rows` statement that alone exceeds the read path's ceiling answers `STATEMENT_TOO_LARGE`, its message ending with the remedy
and no "retry after". Before, a wrapped refusal
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
| `NAMED_QUERY_OPTIONAL_PREDICATE_INVALID` | 400 (schema apply) | `whenParamPresent` is invalid: no param, literal-only, used on `or`, or the named param is still required. **`params.<name>.required` defaults to `true` when omitted** — set `"required": false` explicitly. |
| `NAMED_QUERY_IDENTITY_PARAM` | 400 (schema apply) | Parameter name collides with an identity-derived value |
| `NAMED_QUERY_PROJECTION_REQUIRED` | 400 (schema apply) | Named query omitted `select` / `selectExpr` |
| `NAMED_QUERY_PROJECTION_STAR` | 400 (schema apply) | `select: ["*"]` is refused |
| `NAMED_QUERY_TOO_MANY_JOINS` | 400 (schema apply) | Join count exceeds cap (default 3) |
| `NAMED_QUERY_COST_EXCEEDED` | 400 (schema apply) | Persist-time cost `1 + joins` exceeds cap (default 8) |
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` | WS error | Data-plane `subscribe` without a named-query `"name"`. By design: the data-plane cannot compose a query (ADR 0040 C-2). Subscribe by name, or send the table subscription (`target` + `filter`) to the **admin** listener with a credential whose statements allow it |
| `NAMED_QUERY_SUBSCRIBE_FILTER` | WS error | Subscribe-by-name also sent a client `filter` |
| `INVALID_SUBSCRIPTION_FILTER` | WS error | A table `subscribe`'s `filter` cannot be used: not an object, a shorthand entry that is not one operator object, a member a where clause or a condition does not have, a shorthand column mixed into the structured form, no condition at all (`{}` included), a `null` list entry, or over the rewrite's bound. The subscription is not created. (**BL-1036, next train**) Up to 0.16.0 a member the types lack and a mixed filter were parsed with the member dropped, and a filter with no condition as "no filter" — the subscription received rows its filter did not select; a `null` entry failed the subscribe without this code |
| `NAMED_QUERY_SUBSCRIBE_TARGET` | WS error | Subscribe-by-name `target` does not match the definition |
| `NAMED_QUERY_SUBSCRIBE_MUTATION` | WS error | Subscribe `"name"` addresses a named mutation |
| `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED` | WS error | Definition cannot be subscribed (e.g. unsupported shape) |
| `NAMED_QUERY_SERVER_TIME_NOT_SUBSCRIBABLE` | WS error | Definition has a `serverTime` parameter; only one-shot reads bind the server's clock (**NativeClients, 0.4.0**) |
| `NAMED_QUERY_SERVER_TIME_INVALID` | 400 | A `serverTime` parameter supplied in `args`, or (schema apply) declared where only a `Timestamp` comparison may use it (**NativeClients, 0.4.0**) |
| `DATA_PLANE_WRITE_STREAM` | WS error | Data-plane `stream_open` / `stream_rows` / `stream_close` |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | WS error | Per-connection 32, per-identity 128, the same cap for every principal (**BL-1464, 0.16.0**; the numbers are **BL-1383, 0.11.0**). There is no larger cap for one kind of credential. The message names the cap, the count and the setting. A `subscribe` that re-sends a held `id` replaces it and is never refused by the cap (**BL-1383, 0.11.0**) |
| `SUBSCRIPTION_EMBARGO_RESET` | WS error | (**BL-418, 0.9.0**) An embargoed subscription ended and was removed: more changes were held back than `Aouda:Streaming:EmbargoHoldMaxEvents` (default 100 000) — at subscribe, the rows still inside the embargo already exceed it (narrow the filter) — or the caller's embargo on the table changed. Subscribe again, fresh (no `resume_from`); `@aouda/client` does this once per snapshot it receives |
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

**Credentials:** `manage` on `server`. No credential on the admin listener is `401 AUTH_CREDENTIAL_MISSING`. A credential whose statements do not include that `manage` is `403 AUTH_POLICY_DENIED`. `AUTH_KEY_ROUTE_MISMATCH` is not produced.

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
| `auth.keys` | omitted | Create, get and list omit `keys`. Linking a database mints no key (**BL-1464, 0.16.0**). A key is minted on a principal. |

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

**Credentials:** `read` on every table of that database. Listing databases is a different ask (`manage` on `server`). No credential on the admin listener is `401 AUTH_CREDENTIAL_MISSING`.

**Metadata-only.** `auth` is always an object — `enabled` and `database`. `keys` is omitted. `auth.enabled: false` means unlinked; do not treat a missing or null `auth` as the signal (older servers omitted it).

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
| `401` | `AUTH_CREDENTIAL_MISSING` | No credential on the admin listener. A bad credential is `AUTH_KEY_MALFORMED` or `AUTH_CREDENTIAL_INVALID`. `UNAUTHORIZED` is not produced |

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

**Credentials:** `manage` on `server`, the same ask as [`GET /api/databases`](#get-apidatabases). A credential without it is `403 AUTH_POLICY_DENIED`. `AUTH_KEY_ROUTE_MISMATCH` is not produced. Declaring the database in `aouda.json` is how a process creates one without this call.

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
| `auth.enabled` | bool | No | Shorthand: link to the single existing auth database (400 if none or more than one). |
| `auth.database` | string | No | Link to (or create) a named auth database. |

(**Lead S26, 0.6.0**) `enableWal` and `dataDurability` are gone, with no alias: a body carrying either is **400** `INVALID_REQUEST` naming `durability` (`enableWal: false` is `"unlogged"`, `dataDurability: "MemoryOnly"` is `"memory"`).

Sign-up is not a member of this body. Set it with `PUT /api/auth/{authDatabase}/signup`. A body that still sends a retired signup member is **400** `INVALID_REQUEST`, and the message names that route. Create mints no key (**BL-1464, 0.16.0**).

**Success (201):** the same shape as GET. `auth` is `{ "enabled", "database" }` and has no `keys` member.

```json
{
  "name": "myapp",
  "state": "Active",
  "auth": {
    "enabled": true,
    "database": "auth"
  },
  "isInternal": false,
  "isAuthDatabase": false,
  "authDatabaseKind": "none"
}
```

Poll `GET /api/databases/{name}` until `state=Active` before schema apply.

---

#### `DELETE /api/databases/{db}`

Drops a database. Returns `204 No Content` immediately after the foreground switch. Needs `manage` on that database. No credential on the admin listener is `401 AUTH_CREDENTIAL_MISSING`. A credential without that `manage` is `403 AUTH_POLICY_DENIED`.

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
| `401` | `AUTH_CREDENTIAL_MISSING` | No credential on the admin listener. A bad credential is `AUTH_KEY_MALFORMED` or `AUTH_CREDENTIAL_INVALID`. `UNAUTHORIZED` is not produced |
| `403` | `AUTH_POLICY_DENIED` | The credential's statements do not `manage` this database. `FORBIDDEN` is not produced |

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
| A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost. | | | |
| `joins` | object[] | No | JOIN clauses to apply in order (see below). |
| `aggregates` | object[] | No | (**ColumnarRead S16, 0.3.0**) Aggregates to compute — see [Aggregates and GROUP BY](#aggregates-and-group-by). |
| `groupBy` | object[] | No | (**ColumnarRead S16, 0.3.0**) GROUP BY keys; requires `aggregates`. |
| `perKey` | object | No | `{ "keys": [...], "orderBy": "col", "latest": true }` — one row per distinct `keys` tuple, the one with the greatest (`latest: false`: least) `orderBy` value, ties to the lowest primary key. `select`, `orderBy` and the page apply to the collapsed rows; a `LatestPerKey` / `FirstPerKey` materialized query of the same shape answers it when current (`stats.routedTo`). Not with `aggregates`, `groupBy`, `distinct`, `selectExpr` or `joins` (400); `/query/count` refuses it (**BL-801, 0.3.0**). |

**Where Clause:**
{: #where-clause}

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
| `groups` | WhereClause[] | Nested sub-clauses. Each group is AND'd with the top-level conditions. Enables safe composition of independent filter layers (e.g., row conditions partition scope + row conditions row scope). Maximum nesting depth: **5** (`ProtocolConstants.MaxWhereClauseNestingDepth`). |

`groups` contains nested `WhereClause` objects that are AND-combined with the top-level `and`/`or`. Use `groups` to express nested boolean logic (e.g. `AND(OR(...))`). Each group can itself contain `and`, `or`, and nested `groups`.

**A `where` is read strictly (**BL-1036, next train**).** The two rules below hold wherever a where clause is accepted: `POST …/query`
and `…/query/count` (with `aggregates` and `groupBy` too), each `joins[].where`, a `setExpr` `conditional`'s `when`, `PATCH` and
`DELETE …/tables/{name}/rows`, `POST …/rows/batch`, and a WebSocket or long-poll `subscribe` `filter` (below). Up to 0.16.0 a where the
server could not read was not refused: it filtered less, or nothing.

- **A member a where clause or a condition does not have is `400`.** A where clause has only `and`, `or` and `groups`; a condition has
  only `column`, `op`, `value`, `param`, `whenParamPresent` and `ignoreCase`. A condition written at the top level
  (`"where": {"column": "v", "op": "gte", "value": 3}` instead of `"where": {"and": [{…}]}`), a misspelt list (`"ors"`) or a misspelt
  member (`"vlaue"`, `"values"`, `"ignore_case"`) is refused before the request runs, and nothing is read or written. The body is the
  framework's validation body (it has no `code`); `errors` is keyed by the member's JSON path and the message names the member:

  ```json
  {
    "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
    "title": "One or more validation errors occurred.",
    "status": 400,
    "errors": {
      "$.where.column": ["The JSON property 'column' could not be mapped to any .NET member contained in type 'Aouda.Protocol.WhereClause'."]
    },
    "traceId": "00-…"
  }
  ```

  `errors` may also hold a `"request"` entry (*"The request field is required."*): the body as a whole could not be read. Up to 0.16.0
  the member was dropped. A condition at the top level left an empty where clause, and the read answered **every row**; a stray list
  beside a valid one dropped those conditions, which widened what an update or a delete touched.
- **A where clause with no condition is `400 INVALID_REQUEST`** — `{}`, `{"and": []}`, `{"or": []}`, `{"groups": []}`, and any group
  inside it or a join's `where` that holds none (`{"and": [{…}], "groups": [{}]}`). The `error` names where it is: *The where clause has
  no condition at 'where.groups[0]': give at least one condition in "and", "or" or "groups", or omit "where" to read every row.* (the
  path is `joins[0].where` for a join's). To read every row, omit `where` (or send `null`). Up to 0.16.0 an empty clause read every row
  and an empty group was skipped. On `PATCH` / `DELETE …/rows` and `rows/batch`, an empty top-level `where` keeps its refusal
  (*WHERE clause is required and must contain at least one condition.*, prefixed `Operation[i]` in a batch); an empty group inside a
  mutation's `where` is now refused with the message above, where before it was skipped and the write ran on the other conditions.
- **A `null` entry in a list is `400 INVALID_REQUEST`** (`"and": [null]`, `"groups": [null]`), naming where it is: *The where clause
  holds a null at 'where.and[0]': …*; a subscription `filter` with one is `INVALID_SUBSCRIPTION_FILTER`. Up to 0.16.0 it answered
  `500 INTERNAL_ERROR`.
- A **named query**'s definition already refused an unknown member at `schema/apply` (`SCHEMA_UNKNOWN_MEMBER`). A named query whose
  conditions are all `whenParamPresent` and whose arguments are all absent still reads every row: the rule is about what a client
  sends, not about a definition's bound clause.

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

**Row- and partition-level security on a joined table (BL-818, 0.3.0).** The caller's row conditions and row conditions for every joined
table are applied on that join's side, exactly as on a direct read of the table: a join onto a table the caller may read only
part of answers with that part. (From the 2026-10 architecture review until this change such a join was refused with `403`
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
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

(**BL-035, 0.9.0**) **An [array column](../guides/array-columns.md)** is named in `types` by its array type (`"Double[]"`), and
its cell in `data` is a JSON array, `null` for a null cell and `[]` for an empty one (a `Byte[]` cell is a base64 string, `""` when
empty). Numbers are written in the shortest form that reads back to the same value; `-0` is written `-0`; an `Int64[]` element is a
JSON integer (above 2^53 a plain `JSON.parse` loses digits, as it does for a scalar `Int64`); a **`Float32[]` element is written as
the shortest text of the value widened to `double`** (`0.1f` is `0.10000000149011612`), which a JavaScript reader turns back into
the same float:

```json
{
  "columns": ["CurveId", "Tenors", "Rates", "Residuals"],
  "types": ["Int32", "Int32[]", "Double[]", "Float32[]"],
  "data": [
    [1, 2],
    [[90, 180, 365, 730], []],
    [[0.0412, 0.0398, 0.0377, 0.0361], [-0, 5E-324, 1.7976931348623157E+308, 0.1]],
    [[0.10000000149011612, -0.25, 0, 0.5], null]
  ],
  "rowCount": 2
}
```

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
bytes), a single row that would decode past half the reader's 256 MB frame budget, or a string value over 16 MB of UTF-8. (**BL-035, 0.9.0**) An array column **is** carried, as kind 9. A stored non-finite array element (reachable only through a defect) answers `500` before the first byte, or an error end frame on a streamed export. Errors
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
  refused** at the read path's memory ceiling (`503 MEMORY_BUDGET_EXCEEDED`, or `400 STATEMENT_TOO_LARGE` for a result that alone
  exceeds it, (**BL-1033, next train**)) or at `Aouda:Query:MaxResultRows`
  (`400 RESULT_TOO_LARGE`): both bound a result the server holds, and the same read answered as JSON — or as a named query — is
  still held whole and still refused there. A batch is sized from what the rows' frames actually cost — the first is one row
  group, so long strings are measured before they are batched — and the size only grows with what it meets: a table whose rows
  become much wider partway through can still pass the ceiling in one batch, and that read then ends with an error end frame
  (`STATEMENT_TOO_LARGE`, status 400, when that batch alone exceeds the ceiling — the same read meets it again — **BL-1033, next
  train**; `MEMORY_BUDGET_EXCEEDED`, status 503, when other work held the memory). Its frames are cut per row group (at most 65,536 rows, never past half the reader's 256 MB frame
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
| `Double[]`, `Float32[]`, `Int32[]`, `Int64[]`, `Byte[]`, `String[]` (**BL-035, 0.9.0**) | `Array` (9) | The array, with the column's own element kind; **elements are not widened** |
| A column with no value of its own (e.g. a vector column, which a table query reads as null) | `Null` (0) | — |

(**LoadSpeed S13, 0.4.0**) A decimal column always goes out as `ScaledDecimal` at its declared scale; the 128-bit
`Decimal` kind (6) is retired and never sent. (A computed decimal column — a `selectExpr` — goes at its largest value's
scale; one whose values no 64-bit integer holds at one scale goes as JSON.) Up to 0.3.x a decimal column's kind was chosen from the values it held, and
an empty or all-null `Decimal(p,s)` column, or an undeclared `Decimal`, could come as kind 6.

`X-Aouda-Column-Types` tells a reader how to narrow a cell back to its type: `Int32`, `UInt64`, `Float32`, `Date`, `Guid`. (**BL-035, 0.9.0**) It names an array column by its array type (`["Int64","Double[]","String[]"]`).
`GET /admin/capabilities` lists `queryColumnBatch: true`.

---

### Named queries

Named queries are **server-authored `QueryMessage` templates** identified by the unique schema name (`^[A-Za-z][A-Za-z0-9_.]*$`). Browser-tier callers on the data-plane listener **cannot compose a query** — they send the name plus arguments. Identity is injected from the validated principal; it is never an argument. The closed list of what that surface cannot do is [What a browser-tier read cannot do](../guides/browser-tier-read-limits.md).

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
| `params` | Per-argument constraints (`required`, `min` / `max`, `enum`, `maxLength`, `maxItems`, optional `serverTime`). **`required` defaults to `true` when omitted** — `"status": { "enum": […] }` alone is still required. Write `"required": false` for optional args. |
| `whenParamPresent` | On a `where` (or join `where`) condition: skip the predicate when that param is absent. Requires `params.<name>.required: false`; omit or `true` fails apply with `NAMED_QUERY_OPTIONAL_PREDICATE_INVALID`. `and`-clause only. See [Optional predicates](../guides/named-queries.md#optional-predicates-whenparampresent). |

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

**`crossPartitionAccess`** (boolean, optional, camelCase, omit when `false`; **BL-1227, 0.9.0**). A named query whose definition binds no partition key on a partitioned table is refused `PARTITION_FILTER_REQUIRED` (the message ends `Named query '<name>' binds no partition key: pass crossPartitionAccess with the call, or bind the partition key in the definition's where clause. The flag waives this guard only — the rows are still the credential's grants.`). Send `"crossPartitionAccess": true` in the body of the call to waive that guard. It is per call: a definition cannot set it. It waives the guard only, so the rows are still the credential's access grants. It is honoured on the **admin listener only**; the data-plane listener ignores it and the guard decides ([the browser tier's rule](../guides/browser-tier-read-limits.md#crosspartitionaccess-on-the-data-plane-listener)).

```json
{ "args": { "ticker": "AAPL" }, "crossPartitionAccess": true }
```

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
| 404 | `NAMED_QUERY_NOT_FOUND` | No such named query, or the caller may not `execute` it on the data plane (the same answer). |
| 400 | `NAMED_QUERY_BIND_FAILED` / `NAMED_QUERY_PARAM_REQUIRED` | Bind-time type or constraint failure |
| 404 | `TABLE_NOT_FOUND` | Data-plane browser-tier and a touched table has `a statement on `anonymous`: false` |
| 429 | `IDENTITY_QUOTA_EXCEEDED` | Data-plane quota |

Invoker policy always applies (row conditions + row conditions of the caller). There is no definer / `runAs` field. A definition that joins a
table the caller's row conditions or row conditions restricts is answered with that security applied on the joined side, exactly as a direct read of
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
AUTHORIZATION_DENIED` naming the table: a joined materialized-query result whose source security cannot be applied to it, and a
joined table whose partition-level security refuses the caller ([joins and authorization](#post-apidatabasesdbquery); **BL-818, 0.3.0**).

#### `POST /api/databases/{db}/named-queries/batch`

Read-only batch envelope. Every element is evaluated against **one read snapshot**. HTTP **200 means the envelope was accepted** — a per-element policy deny or bind failure is a positional `{ code, error }` and does **not** fail the other slots.

**Request body:**

```json
{
  "queries": [
    { "name": "equity.quoteByTicker", "args": { "ticker": "AAPL" } },
    { "name": "equity.stockOverview", "args": { "accountId": 42 } }
  ]
}
```

Each element may also carry **`crossPartitionAccess`** (boolean, camelCase, omit when `false`; **BL-1227, 0.9.0**), with the same meaning as on a single call: it waives `PARTITION_FILTER_REQUIRED` for that element only, never widens what the credential sees, is honoured on the admin listener only, and is ignored on the data-plane listener. There is no flag on the envelope: set it on each element that needs it.

```json
{ "queries": [ { "name": "equity.allQuotes", "args": {}, "crossPartitionAccess": true } ] }
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

(**BL-1417, 0.12.0**) The route needs an authenticated caller and nothing else; each slot is authorised separately, and a slot the caller may not execute (no `named-query` `execute` row for its name) is that slot's `NAMED_QUERY_NOT_FOUND` on both listeners, the same as an unknown name. A caller who may execute none gets HTTP 200 with every slot masked, not a 403. An unsigned data-plane caller keeps the **request-level 404** `NAMED_QUERY_NOT_FOUND`, and the admin listener keeps 401 for it. (**BL-1417 review, 0.13.0**) When no slot is admitted the response is `{ "results": [ …NAMED_QUERY_NOT_FOUND slots… ], "token": "" }`; a slot naming a mutation is `NAMED_QUERY_BATCH_MUTATION` only for a caller that may execute that mutation, and an unknown slot for anyone else.

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

(**BL-1227, 0.9.0**) On a table with row conditions or row conditions, an upsert that finds a row under the key replaces it only if the caller may
write **that** row — on row conditions its partition, on row conditions the update scope and the write check — else `403 AUTHORIZATION_DENIED` and no row of
the call is written. The message names the key, not the stored row's partition. A holder of the lifting grant(s) at `write` is not
checked. See [Authorization §19.4.4](../auth/authorization.md#1944-write-path-access-level-enforcement).


**What a `values` / `set` entry may be.** Exactly three forms:

| Form | Meaning |
|------|---------|
| `"Qty": 10`, `"Note": null`, `"Vec": [0.1, 0.2]` | A **bare literal** — any JSON value that is not an object. |
| `"Qty": { "param": "qty" }` | A **parameter hole**, filled from `args` at execute. |
| `"Qty": { "value": 10 }` | A **constant**, spelled explicitly. The wrapped value may be a scalar, `null`, or an array — but not an object. |

The object shape is reserved for those two one-key forms, because `{ "param": … }` already claims it: a bare object constant would be indistinguishable from a mistyped hole. Any other object node — an unknown key (`{ "valu": 0 }`), both keys at once, an empty object, or an object nested under `value` — fails **schema apply** with `NAMED_MUTATION_VALUE_NODE_INVALID`, naming the field (`values` / `set`), the column, and the keys it actually found. A definition stored before that check existed still loads, and its `execute` fails with `NAMED_MUTATION_BIND_FAILED` naming the column (BL-479 — previously such a node was carried into the row and surfaced as an untyped `INVALID_REQUEST` from deep in column conversion).

(**BL-035, 0.9.0**) **A parameter or a literal bound to an [array column](../guides/array-columns.md)** takes the column's JSON
form: an array (`"Rates": { "param": "rates" }` with `"rates": [0.0412, 0.0398]`, or the literal `"Tenors": [30, 90, 180]`), a base64
string for a `Byte[]`, `null` for a null cell. A bad value is refused `400 NAMED_QUERY_BIND_FAILED` for a parameter and
`NAMED_MUTATION_BIND_FAILED` for a literal, naming the parameter, the column and the element (*"Parameter 'd' (Double[] column 'D'):
Element 0 of the Double[] value is NaN; array elements must be finite numbers (NaN and ±Infinity are refused)."*). `upsert` and
`update … set` write the whole array. Refused when the definition is applied (that entry is `Failed`, reason starting
`ARRAY_COLUMN_UNSUPPORTED:`): a `setExpr` that targets or reads an array column, an `orderBy` on one, and a `min` / `max` /
`maxLength` / `enum` constraint on a parameter written to one. A `batchParam` row's array is one JSON array in the parameter's slot
of the column arrays.

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

**Errors:** `NAMED_MUTATION_NOT_FOUND` (404), `NAMED_MUTATION_BIND_FAILED` (400), `NAMED_QUERY_PARAM_REQUIRED` (400 — a required arg was omitted, including a missing `batchParam`), `NAMED_MUTATION_RETURNING_OVERFLOW` (400), `MEMORY_BUDGET_EXCEEDED` (503 + `Retry-After` — a DELETE / UPDATE whose matches do not fit the read budget now, nothing changed; **BL-817, 0.3.0**), `STATEMENT_TOO_LARGE` (400, no `Retry-After` — a DELETE / UPDATE whose matches alone exceed the read path's ceiling, which no retry can satisfy; nothing changed; narrow the statement; **BL-1033, next train**), `WRITE_CONFLICT` (409 — a DELETE / UPDATE whose matched rows other writers kept changing through 16 attempts, nothing changed, retry; **BL-881, 0.3.0**), `TABLE_NOT_FOUND` (data-plane opt-in), `IDENTITY_QUOTA_EXCEEDED` (429). On the data-plane listener, unsigned or unentitled execute is 404 `NAMED_MUTATION_NOT_FOUND` (same envelope as unknown); admin listener keeps 401/403. A batch-element bind failure's 400 body includes `rowErrors: [{ "index", "code", "message" }]` naming the offending row index — the whole call fails, no row is inserted. `NAMED_MUTATION_BIND_FAILED` also covers a `values` / `set` entry that is an unrecognised object node, naming the column. Schema apply also rejects `NAMED_MUTATION_UNCAPPED_DELETE`, `NAMED_MUTATION_RETURNING_STAR`, `NAMED_MUTATION_VALUE_NODE_INVALID`, `NAMED_MUTATION_BATCH_NON_INSERT`, and `NAMED_MUTATION_BATCH_MAX_ITEMS_REQUIRED`.

### Explain a formula cell

(**ADR 0072, 0.14.0**) `POST /api/databases/{db}/tables/{table}/explain` says why a [formula](../guides/formulas.md) cell has the
value it has. It evaluates the cell **again now** and answers its formula, every reference with its resolved key and current value, the
value or the reason it has none, the value the row stores, and the formula cells that read it. It writes nothing, but it reads this
node's own tables, so a node that serves a replica's rows — a replica, or a promoted node until BL-1441 is fixed — refuses it with
`503 FORMULA_NOT_MAINTAINED` (**BL-1511, 0.15.0**); explain on the primary. A primary, a standalone node and a branch answer it.
It needs read access to the table.

```json
{ "key": { "dept": "Online", "line": "Margin", "year": 2028 }, "column": "amount" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | object | Yes | The row's **full** primary key, column → value (typed as a `/query` filter value is). |
| `column` | string | Yes | The driven column, or the `Expression` column that drives it. |

**Response:** `200`

```json
{
  "table": "pnl",
  "key": { "dept": "Online", "line": "Margin", "year": 2028 },
  "column": "amount",
  "expressionColumn": "formula",
  "kind": "formula",
  "formula": { "type": "call", "fn": "round", "args": [ … ] },
  "references": [
    { "table": "pnl", "key": { "dept": "Online", "line": "Revenue", "year": 2028 }, "column": "amount",
      "readable": true, "value": 0.00, "isFormulaCell": false, "error": null },
    { "table": "pnl", "key": { "dept": "Online", "line": "EBIT", "year": 2028 }, "column": "amount",
      "readable": true, "value": -830.00, "isFormulaCell": true, "error": null }
  ],
  "value": null,
  "reason": "division by zero.",
  "storedValue": null,
  "readBy": [
    { "table": "pnl", "key": { "dept": "Online", "line": "MarginGap", "year": 2028 }, "column": "amount" },
    { "table": "pnl", "key": { "dept": "Online", "line": "Tax", "year": 2028 }, "column": "amount" }
  ]
}
```

| Field | Description |
|-------|-------------|
| `table`, `key`, `column`, `expressionColumn` | The cell: its row's key, its driven column and the Expression column that drives it. |
| `kind` | `formula` (the row carries a formula), `input` (its formula is null: `value` is the stored input, `references` is empty) or `noRow`. |
| `formula` | The row's formula as a JSON object; `null` for an input or no row. |
| `references` | Each cell the formula reads: `table`, the **resolved** `key` (the shorthands filled in from the row), `column`; `readable`; and, when readable, its current `value`, `isFormulaCell` and `error` (why it could not be read, else `null`). |
| `value` | The value the formula computes now, as the driven column holds it; `null` when it has none. |
| `reason` | Why there is no value — a division by zero, an overflow, a value the column cannot hold, a value a check refused (the one the last write met), a broken reference — or `null`. When any reference is not `readable` and there is a reason, it is `"withheld: the formula reads a row you may not read."` instead: the reason can print a value it read. |
| `storedValue` | The value the row stores now. |
| `readBy` | The formula cells that read this one. |

**What the caller sees** is what it may read, by the same rule as a `/query` of each table: a row it may not read answers exactly as a key
with no row (`kind: "noRow"`); a reference to a row it may not read keeps its `table`, `key` and `column` with `readable: false`, and its
`value`, `isFormulaCell` and `error` are `null`, and a `reason` is withheld (above); readers it may not read are left out. The cell's own value is shown to whoever may read its row.
`explain` takes no consistency token (`at_least` is not read) and stamps none: `value` is computed now, and `storedValue` may not yet show a
write the caller just made.

**Refusals.** `400 INVALID_REQUEST` when `key` or `column` is missing, the key is not the table's full primary key or holds a value its
column cannot, or `column` is neither an Expression column nor a column one drives; `404 TABLE_NOT_FOUND` / `DATABASE_NOT_FOUND`;
`503 FORMULA_NOT_MAINTAINED` — on a node that serves a replica's rows (**BL-1511, 0.15.0**). Not retried by the SDKs; no
`Retry-After`.

The SDKs: `ExplainAsync` (C#) and `table.explain(key, column)` (TypeScript).

---

### Materialized query endpoints

Base path: `/api/databases/{db}/materialized-queries`

| Method | Path | Auth (when DB auth enabled) | Description |
|--------|------|------------------------------|-------------|
| GET | `/` | Read | List all materialized queries (array of status objects). |
| GET | `/{name}` | Read | Status for one query; `404` if missing. |
| POST | `/` | Admin | Create a query. Body below. `204 No Content` on success. (**BL-884, 0.3.0**) A create whose first build is refused for capacity (memory, or a full WAL) still answers `204`: the definition is durable, the query exists **behind** (`current: false`) and is built once there is room. It used to answer `503` and leave the query in `Error`, so the retry was refused as "already exists". |
| DELETE | `/{name}` | Admin | Drop query and storage; `204` on success. |
| POST | `/{name}/query` | Read | Return the materialized rows as column arrays (see response; **Lead S12, 0.6.0**: they were row objects). (**BL-035, 0.9.0**) A result that carries an [array column](../guides/array-columns.md) adds **`columnTypes`** to the body, a map from each array column's name to its type (`{"Tenors":"Int32[]","Rates":"Double[]"}`); it is absent when the result has none, and the body has no `types`. (**BL-1402, 0.11.0**) It also names each `Timestamp` column (`"Timestamp"`, .NET ticks) and each `Date` column (`"Date"`, days since the Unix epoch), spelled as a snapshot's `column_types`, and is absent only when the result has none of the three kinds; every `latestPerKey` result carries its ordering `Timestamp`, so it is present on those. A body with no rows (a denied read, an unresolved source chain) names the result table's types as well. A client treats a column that is not named there as a scalar. |
| POST | `:refresh` | Admin | **Pooled refresh (BL-474)**: rebuild several queries, decoding each shared source table **once**. Select with `sourceTable` (optionally `staleOnly`) **or** `names` — exactly one of the two. Returns per-name outcomes; see below. |
| POST | `/{name}:refresh` | Admin | Trigger a full rebuild of the MQ result table (shadow-build pattern). `await: true` waits up to the server window (`Aouda:MaterializedQueries:RefreshAwaitTimeout`, default 120s — see below): **200** `{ "status": "complete" }` when the wait finishes, **202** `{ "status": "scheduled" }` on timeout (refresh **keeps running**). `await: false` is fire-and-forget **202** `scheduled`. Result table is readable with stale data throughout. A **202 never cancels the rebuild**, regardless of why the wait ended. |

A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

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
| `name` | string | Yes | Unique materialized query name. It is the result table's name, so it follows the [table-name rule](#table-names), and it may not start with `_` or exceed 100 characters. A name that breaks either is `400 INVALID_REQUEST` and nothing is created; a retry answers the same (**BL-1468, 0.14.0; breaking**: before, a name such as `a:b` or `x.` left the query registered in `Error` with no result table, and a retry answered that it already existed). |
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

Apply idempotent seed data. Tables must already exist. A row whose primary key already exists in any tier — the write buffer, a
hot segment or a cold one — is skipped and counted as `skipped` (**BL-1489, 0.15.0**).

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

**Authorization.** Database-level `write`. (**BL-1227, 0.9.0**) Tables the document names stay on the whole-table grant: a seed of
those tables is not a per-user write — their rows pass no row conditions or row conditions check — so every named table that has partition- or row-level
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
keys, a `role `admin`` user or a role. Otherwise the answer is `403 AUTHORIZATION_DENIED` naming every refused table and the grant
it lacks, and nothing from the document is written. A table that does not exist is left to the apply's own `400 TABLE_NOT_FOUND`. A
holder's seed writes one ``unconditional_access`` row per table and grant (operation `seed`) before the first row. (**BL-1304, 0.9.0**)
A transform that lands on any other table is the caller's per-row insert check, on the target row after derived columns. Seed does
not stamp identity, so a stamp column is not filled before that check. A refusal is the same `403` and code as
`POST …/tables/{target}/rows` of that row, and that landing is not written when it is refused.

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
| `includeSystemTables` | `false` | Include system tables (e.g., materialized query result tables). A materialized query's build table (`__mqbuild_<query>_<id>`, present while it rebuilds) is never listed, with either value (**BL-1468, 0.14.0**) |

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

#### `GET /api/databases/{db}/schema/typescript`

Generate TypeScript interfaces for all tables. (**BL-035, 0.9.0**: the route was written here as `GET /api/schema/typescript`,
which the server never served — it answers `401` without a database in the path.)

**Query Parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `comments` | `true` | Include JSDoc comments in output |
| `schema` | `true` | Include Schema interface and TableName type |
| `namespace` | - | Optional namespace wrapper for generated types |

**Response:** `text/plain` with TypeScript code. (**BL-035, 0.9.0**) An [array column](../guides/array-columns.md) is typed
`Float64Array` (`Double[]`), `Float32Array`, `Int32Array`, `BigInt64Array` (`Int64[]`), `Uint8Array` (`Byte[]`) or `string[]` in a table
interface and a named query's row, and a named mutation's argument takes `Float64Array | number[]`, `Float32Array | number[]`,
`Int32Array | number[]`, `BigInt64Array | bigint[] | number[]`, `Uint8Array` or `string[]`. (**BL-1496, 0.15.0**) A row type is the union of
what every path that reads or writes a row gives, so no read needs a cast it cannot make: a `Timestamp` column is `string | Date` (ISO text
in a query result, a `Date` in a subscription row), a `Date` column `number | Date` (its day number in a query result), a decimal
`string | number` (a number in a query result). A named query's argument keeps the one value it takes: `Date` for a `Timestamp` or a `Date` column.

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
  created_at: string | Date;
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

(**ADR 0072, 0.14.0**) **An `Expression` column** holds a [formula](../guides/formulas.md) per row and names the column it drives:
`{ "name": "formula", "type": "Expression", "drives": "amount" }`. It is nullable whether or not `isNullable` says so (a row with no formula
is an input), and the response, the column listing and `…/schema` show it with `"type": "Expression"` and `drives`. The table must have a
`Strict` primary key and be an ordinary table; the Expression column is not a key, partition or cluster column and has no default,
`unique`, reference, check or derivation; the driven column is a nullable scalar of the same table that is not a key, partition or cluster
column, not derived, identity, server time or auto-increment, not a vector or an array, and driven by no other Expression column. A
violation is `400 FORMULA_COLUMN_INVALID` naming the rule. A query answers the column's type as `"Expression"` and each row's formula as a
JSON object (`null` for an input row). (**BL-1512, 0.15.0**) (**BL-1491, 0.15.0**) So does every other JSON body that carries rows
of the table: the `returning` rows of a `PATCH` or `DELETE` of its rows and of a named mutation (insert,
upsert, update and delete) — which wrote the canonical text as a string of escaped JSON until this train — a named query's body and a
policy-inspect sample. Two reads keep the stored text, on purpose: a **group-by** whose key is the Expression column answers the key as a
`String` (`"types": ["String", …]`), as a grouped value and not a table row; and a **materialized query** over the table copies the column
into its result as a plain `String` column (a result is an ordinary table, never an Expression column), so its body holds the text.

(**Horizon, 0.5.0**) `policy.retention` — `{ "keep": "90d" }`, a whole number of minutes, hours, days or weeks (`m` / `h` /
`d` / `w`) — declares [retention](../guides/retention.md): rows whose first cluster column is older than the server's clock minus
`keep` are not returned, not written (counted as `expiredRows`) and dropped by whole segments. The table's first cluster column
(lowest `clusterOrder`) must be a `Timestamp` or `Date`; it may be nullable. A refused declaration — no such column, a `keep` that is
not a duration, an edge table, a table with a vector column — is `400` naming its reason. The response's `policy` carries `retention` and `horizon`.

**A table carries no security (**BL-1464, 0.16.0**).** `POST …/tables`, `PUT …/tables/{name}/options`, edge-table create, vector-column create and materialized-query create refuse a body that sends a security member with `400 SCHEMA_UNKNOWN_MEMBER`, naming the member. `PUT …/options` sets `culture` only. Who may read or write the table is a statement. See [Policy](../auth/authorization.md).

```json
{
  "database": "markets",
  "name": "SpotQuote",
  "columns": [
    { "name": "SecurityId", "type": "String", "primaryKeyOrder": 1, "partitionKeyOrder": 1 },
    { "name": "Source", "type": "String", "primaryKeyOrder": 2, "partitionKeyOrder": 2 },
    { "name": "Bid", "type": "Double", "isNullable": true }
  ],
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
  "an attribute": "fx_source",
  "the column in the `where`": "Source"
}
```

**Response:** `201 Created` with table detail

<a id="table-names"></a>**Table names** (**BL-1468, 0.14.0; breaking**). One rule for every way a table gets a name: this
create, the rename below, `POST …/edge-tables`, `…:create-vector-column`, the embedded API, every table a schema file declares, and
every materialized query (over HTTP or in a schema file's `materializedQueries`), whose name is its result table's.
A table name:

- is not empty and not whitespace only, and is not `.` or `..`;
- contains none of `/ \ : * ? " < > |`;
- does not start or end with a period (`.`) or a space;
- does not start with `__mqbuild_`, which is reserved for the engine's own materialized-query build tables.

Anything else (letters, digits, `_`, `-`, other Unicode) is allowed. Matching is exact (`orders` and `Orders` are two tables). A
name that breaks the rule is `400 INVALID_REQUEST` and the message names the rule it broke, for example *Table name cannot start or
end with a period or space (invalid for directory names).* Before, only the embedded create applied this rule; the HTTP create and
rename, the graph and vector creates and the schema apply accepted any name.

#### `DELETE /api/databases/{db}/tables/{name}`

Delete a table. A `__mqbuild_*` name is `404 TABLE_NOT_FOUND` (**BL-1468, 0.14.0**): a materialized query's build table is not
addressable. Refused `400 DECLARATIVE_SCHEMA_DDL_FORBIDDEN` on a table schema apply created (**BL-1177, 0.7.1**). To drop that
table, remove it from the schema file and apply with `allowDestructive: true`. (**BL-1296, 0.9.0**) A table that already has
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
where row conditions applies. statements `drop` is still required and is not enough. A table with neither restriction is unchanged.

**Response:** `204 No Content`

#### `PATCH /api/databases/{db}/tables/{name}`

Rename a table. `newName` follows the [table-name rule](#table-names): breaking it is `400 INVALID_REQUEST` (**BL-1468, next
train**). A `__mqbuild_*` `{name}` is `404 TABLE_NOT_FOUND`.

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

(**ADR 0072, 0.14.0**) `"type": "Expression"` with `"drives": "<column>"` adds an [Expression column](#post-apidatabasesdbtables), by the
same rules as on create. No column becomes or stops being an Expression column, and an Expression column does not change what it drives:
add a new one and drop the old. Dropping an Expression column leaves its driven column's values as inputs; a driven column cannot be
dropped while it is driven. Adding an Expression column to a source table of a materialized query whose result a formula reads (any table on the query's chain,
its upstream queries' sources included) is
`409 FORMULA_TABLE_REFERENCED`, naming those formula cells: a formula may not read a query over a formula table (the dependency cannot be
followed through the query), so the table may not become one under such a reader. The same holds for a schema document's added Expression
column (a failed entry) and a branch merge.

**Response:** `201 Created` with column detail

#### `PATCH /api/databases/{db}/tables/{name}/columns/{columnName}`

Alter a column: `type`, `nullable`, `autoIncrement`, `references`, and/or `newName` (rename) — at least one, or `400`. The
`encoder` field is gone (**BL-768, 0.3.0**): it changed nothing since columns choose an encoding per vector, and a
request carrying only `encoder` is now refused as having nothing to alter. The example renames a column.

(**BL-1199, 0.9.0**) A partition-key column is not renamed: `newName` on one is refused `400 PARTITION_KEY_FIXED`, before
any other field of the request is applied (it was renamed; on a composite key a rename to or from `tenant_id` changed which column,
and which JWT claim, partition-level security filters on).

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
(**BL-1177, 0.7.1**). An explicit `Unsafe` insert reconcile (`AutoReconcileSchema` + `ReconcilePolicy = Unsafe`) issues this
DELETE for each non-key column its row type omits. A typed update does not reconcile, so it does not issue this DELETE.
(**BL-1178, 0.9.0**)

(**BL-1178, 0.9.0**) Dropping the last column is `400 INVALID_REQUEST`. The message names the table and the column
(`Dropping column 'n' would leave table 't' with no columns.`), and the column stays. A primary key is dropped when another
column remains (`204`). A partition-key column stays `400 PARTITION_KEY_FIXED`, including when it is the only column.

(**BL-1199, 0.9.0**) A partition-key column is not dropped: refused `400 PARTITION_KEY_FIXED` (it was dropped, leaving the
table's stored partitions keyed by a column it no longer had). Drop and re-create the table to change its key. (**BL-1296, 0.9.0**)
Dropping the `the column in the `where`` of a table that already has row conditions is `403 AUTHORIZATION_DENIED` unless the caller holds, at `admin`,
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
`400 PARTITION_KEY_FIXED`, and the table is unchanged.

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
is only needed when some rows give a column and others do not. (**BL-1104, next train**) **A bulk-load `:append` applies defaults
too**, for a JSON body as for a frame and at either `validation` level: an absent cell takes its column's default, and an absent
`autoIncrement` cell is generated. Until then a bulk load stored an absent cell as null (a NOT NULL column: the type's default, `""`
or `0`).

**Values** are read as before: an integer is an integer, a fraction keeps the scale it is written with, a string is a string, and an
array (a vector, an array column's value) is converted the way the column's type takes it. A value is judged exactly as the same
cell sent in a [column-batch frame](#the-column-batch-frame-acb2) — the same conversions, the same errors.

(**BL-1108, BL-1250, BL-1220, next train**) **One rule per value, on every write surface** — `POST …/rows`, a branch insert, the
`set` of `PATCH …/rows` and `rows/batch`, `stream_rows`, `:append`, a named mutation's parameter, literal and `batchParam` rows, a
seed, and the embedded engine:

- **A number written to a `String` column is stored as its text as sent**: `2.50` is `"2.50"`, `1E+17` is `"1E+17"`, and `1`
  beside `2.5` in one column is `"1"`. Until then the text was rebuilt from the number's value (`"1.0"`, `"100000000000000000"`,
  `"2.5"`, depending on the surface). A seed keeps refusing a number for a `String` column (*"expected string for type String, got
  number"*).
- **A JSON array or object written to a scalar column is refused** — a `String` column included; an array column and a vector take
  an array. It is `400 INVALID_REQUEST` naming the column (and the row, where the body has rows): *"Column 'note': a JSON array is
  not a String value — send text as a JSON string (an array goes in an array column)."*; on a named mutation it is
  `400 NAMED_QUERY_BIND_FAILED` naming the parameter (*"Parameter 'v' expected a scalar value for its String column, got Array
  …"*); on `stream_rows`, an `error` naming the row and the column. Until then a `String` column stored the value's JSON text or a
  type name (`System.Collections.Generic.List`1[System.Object]`), and `PATCH` of an array into a number column answered
  `500 INTERNAL_ERROR`. A read filter follows the same rule: a JSON array as the operand of `eq`, `ne` or a range operator on a
  `String` column is `400 INVALID_REQUEST` naming the column (it was compared with that type name, so `ne` matched every row);
  `in` / `nin` take their list as before. (A JSON object there is still compared as its JSON text, BL-1643.)
- **A scalar `-0` is stored as `0`** in a `Double` and a `Float32` column, whatever carried it: a JSON body always stored `0`; a
  frame's cell, a named mutation's parameter, literal or `setExpr`, a seed and the embedded engine kept the sign. An
  [array column](../guides/array-columns.md)'s element keeps its `-0`.
- **A numeric string written to an integer column stays accepted** (`"0012"` is `12`), except for a named mutation's integer
  parameter, which refuses a string (*"Parameter 'id' expected integer, got String"*).

(**BL-035, 0.9.0**) **An [array column](../guides/array-columns.md)'s slot holds one JSON array per row** (the data is nested
twice), `null` for a null cell, `[]` for an empty one, and a `Byte[]` cell is a base64 string. Numbers are read from their text
(`-0` is kept; a `Float32` is rounded to a float once); an `Int32[]` / `Int64[]` element is an integral number in any notation
(`2.0`, `1e3`), never a fraction or a string; NaN, ±Infinity and the strings `"NaN"` / `"Infinity"` are refused, and so are a null
element, a nested array and a number out of the type's range. At most 65,536 elements and 1,048,576 bytes of elements a value. A
bad value is `400 INVALID_REQUEST` naming the column (`Column 'D': Element 0 of the Double[] value is NaN; …`), or on a named
mutation `NAMED_QUERY_BIND_FAILED` naming the parameter:

```json
{
  "database": "acdocs",
  "columns": ["Id", "D", "B", "S"],
  "data": [
    [100, 101],
    [[1.5, 2.5], null],
    ["AQID", ""],
    [["x", "y"], []]
  ]
}
```

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
cannot say which text it had. A JSON body keeps each number's text as sent (**BL-1108, next train**): `3` beside `2.50` is
stored `"3"` there (see [values](#column-arrays-the-write-body)).

- (**BL-035, 0.9.0**) **An array column's frame column (kind 9) must carry the column's own element kind**: nothing is widened
  (an `Int32` run for a `Double[]` column, or an array column sent to a scalar column, is `400 INVALID_REQUEST` naming the column —
  *"Column 'D' is Double[]; the frame sends Int32 elements (an array column's frame carries its own element kind, Double; nothing is
  widened)."*). The JSON body is more forgiving: an integral number is accepted in a `Double[]` column.
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
| `INVALID_REQUEST` | 400 | Missing `columns` / `data`, column arrays that do not match (see [column arrays](#column-arrays-the-write-body)), invalid column name, schema mismatch, `identityInsert: true` with a missing, absent or `null` autoIncrement column, a body that is not valid JSON, a frame body that is not one valid column-batch frame, a frame `Double` cell that is NaN or ±Infinity (**BL-716, 0.2.0** — JSON cannot carry them either), a string cell that is not valid UTF-8 (**BL-716, 0.2.0**), a JSON array or object for a scalar column (**BL-1250, next train**; see [values](#column-arrays-the-write-body)), or a frame column of the retired 128-bit `Decimal` kind 6 (**LoadSpeed S13, 0.4.0**; see [the frame](#post-jobidappend)) |
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
| `INVALID_REQUEST` | 400 | Missing/empty WHERE, or a group inside it with no condition (**BL-1036, next train**), missing/empty SET, or invalid column name in SET; a JSON array or object in SET for a scalar column (**BL-1250, next train** — for a number column it was `500 INTERNAL_ERROR`, a `String` column stored it as a type name) |
| `AUTH_ENTITLEMENT_NOT_FOUND`, `AUTH_ENTITLEMENT_INSUFFICIENT_ACCESS`, `AUTH_PLS_WRITE_SCOPE_VIOLATION` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The rows the WHERE matches do not fit the read budget now, as the same `SELECT` would not (**BL-817, 0.3.0**) — other work holds the memory they need. Nothing is changed; `Retry-After` is set. |
| `STATEMENT_TOO_LARGE` | 400 | (**BL-1033, next train**) The rows the WHERE matches alone exceed the most the read path may hold on this database, so no retry can satisfy it (it was this `503` with a `Retry-After`, every time). Nothing is changed; no `Retry-After`. Narrow the predicate and mutate in pieces. |
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
| `INVALID_REQUEST` | 400 | Missing or empty WHERE clause, or a group inside it with no condition (**BL-1036, next train**) |
| `MEMORY_BUDGET_EXCEEDED` | 503 | The rows the WHERE matches do not fit the read budget now, as the same `SELECT` would not (**BL-817, 0.3.0**) — other work holds the memory they need. Nothing is changed; `Retry-After` is set. |
| `STATEMENT_TOO_LARGE` | 400 | (**BL-1033, next train**) The rows the WHERE matches alone exceed the most the read path may hold on this database, so no retry can satisfy it (it was this `503` with a `Retry-After`, every time). Nothing is changed; no `Retry-After`. Narrow the predicate and mutate in pieces. |
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

An expression whose 64-bit integer or 18-digit decimal arithmetic overflows for any matched row refuses the whole update with
`EXPRESSION_OVERFLOW` (**BL-1481, 0.15.0**); `POST …/rows/batch` answers it, and `TRANSFORM_DERIVED_READONLY`, as a 400 (it
answered 500).

#### Expression node format

Each value in `setExpr` is an expression node:

```json
{ "type": "arithmetic", "op": "+|-|*|/", "left": <node>, "right": <node> }
{ "type": "colRef", "col": "columnName" }
{ "type": "literal", "value": <any> }
{ "type": "coalesce", "args": [<node>, ...] }
{ "type": "conditional", "when": <predicate>, "then": <node>, "else": <node> }
{ "type": "call", "fn": "<name>", "args": [<node>, ...] }
{ "type": "cellRef", "table": "t", "key": { "col": { "type": "literal", "value": <v> }, ... }, "column": "c" }
```

(**ADR 0072, 0.14.0**) `cellRef` reads one value: the `column` of the row of `table` whose full strict primary key is `key` (literal values only). It is valid only in a [formula](../guides/formulas.md#references), the value of an `Expression` column; in a `setExpr`, a derived column, a named query or mutation, a `selectExpr` or a materialized query's output it is `400 EXPR_CELLREF_NOT_ALLOWED`, well-formed or not; in a formula, a malformed one is `400 FORMULA_REFERENCE_INVALID`. In a formula, `table` may be left out (or `""`: the formula's own table), a key column may be left out (the formula row's own primary-key value of that name), and a `colRef` reads a column of the formula's own row. (**ADR 0072, 0.14.0**) `call` also takes `min`, `max`, `abs`, `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `if`, `and`, `or`, `not` (listed in [Formulas](../guides/formulas.md#what-a-formula-may-contain)) beside `upper`, `lower`, `trim`, `concat`, `substring`, `round`, `roundTo`, `cast`. `if`, `and` and `or` evaluate only the operands they need.
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
authorization scope — `role `writer`` alone is insufficient.

A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
else holds them only through a role. Without them the answer is `403 AUTHORIZATION_DENIED` naming the table and the grant it lacks,
and nothing is truncated; delete the rows you may write with a `WHERE` instead. A holder's truncate writes one ``unconditional_access``
row per grant (operation `truncate`) before the table is emptied. See [Authorization](../auth/authorization.md#bulk-load-is-not-a-per-user-write-bl-1031-050).

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
| `AUTHORIZATION_DENIED` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |

---

#### `POST /api/databases/{db}/tables/{name}/rows/batch`

Execute multiple update and/or delete operations against the same table in a single request.
All operations are applied sequentially in the order given. ⚠️ **A batch is not one transaction: each operation commits on its
own** (**BL-843**). When an operation fails, the operations before it have been applied and stay applied, so a retry of the
whole batch applies them again. Make operations that a retry may repeat idempotent (literal `set`, not `setExpr` arithmetic), or
retry from the failed operation. What each answer means for what was applied:

- **`400 INVALID_REQUEST` for the request's shape** (see Errors below), a row conditions `403`, an row conditions deny-all, and an row conditions write-check
  refusal of operation 0 (`403 AUTH_RLS_UPDATE_SET_VIOLATION`): nothing was applied. Those checks run before the first operation
  commits. (**BL-1303, 0.9.0**)
- **`403 BATCH_RLS_PREFIX_APPLIED`**, no `Retry-After`: the row conditions write check refused operation `k` ≥ 1. Operations `0` to `k − 1`
  were applied, operation `k` and the later ones were not, and the row that check refused was not written. `details` names
  `appliedOperations` and `totalOperations` (and `refusalCode=AUTH_RLS_UPDATE_SET_VIOLATION`). **Do not re-send the batch as-is.**
  Each update is checked against the rows the earlier operations of this batch left. (**BL-1303, 0.9.0**)
- **`503 MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`**, with `Retry-After`: the **first** operation was refused for capacity
  and nothing was applied. Retry the whole batch after `Retry-After` (**0.3.0**).
- **`400 STATEMENT_TOO_LARGE`**, no `Retry-After` (**BL-1033, next train**): the **first** operation's matches alone exceed the read path's ceiling,
  so no retry can satisfy it; nothing was applied. Narrow that operation's `where` or split it. (Operation `k` ≥ 1 refused this way is
  `503 BATCH_PARTIALLY_APPLIED` with `refusalCode=STATEMENT_TOO_LARGE` in `details`.)
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
| `INVALID_REQUEST` | 400 | Empty operations list, or an operation missing both `set`/`setExpr` and `delete`, or missing WHERE, or a group inside one with no condition (**BL-1036, next train**); a JSON array or object in a `set` for a scalar column (**BL-1250, next train**) |
| `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` | 503 | The first operation was refused for capacity; nothing was applied. `Retry-After` is set |
| `STATEMENT_TOO_LARGE` | 400 | (**BL-1033, next train**) The first operation's matches alone exceed the read path's ceiling; nothing was applied. No `Retry-After`: narrow or split the operation. See [`STATEMENT_TOO_LARGE`](#request-validation-errors-4xx) |
| `BATCH_PARTIALLY_APPLIED` | 503 | (**Lead group 3 review, 0.6.0**) Operation `k` ≥ 1 was refused for capacity; operations before it were applied. No `Retry-After`; re-send only the remaining operations. See [above](#post-apidatabasesdbtablesnamerowsbatch) |
| `BATCH_RLS_PREFIX_APPLIED` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
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
admin-listener routes: on the data-plane listener they are `404`. A write needs `write` on the table. A read needs `read` and is filtered by the caller's `read` statements ([graph and vector](../guides/graph-vector.md)). The reads honour the [freshness parameters](#consistency-tokens-and-freshness). An unconditional `read` is audited as `unconditional_access` (**BL-1464, 0.16.0**).

| Method | Path | Body | Answer |
|---|---|---|---|
| A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost. | | | |
| `POST` | `/api/databases/{db}/tables/{name}/edges` | `{ srcs, dsts, edgeLabels? }` | `200` `{ "edgesInserted", "token" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges:traverse` | `{ startNodeId, hops? }` | `200` `{ "neighborIds", "executionMs" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges:khop` | `{ startNodeId, k }` | `200` `{ "nodeIds", "hops", "executionMs" }` |
| `POST` | `/api/databases/{db}/tables/{name}/edges:shortest-path` | `{ a, b }` | `200` `{ "path", "executionMs" }` |
| A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost. | | | |
| `POST` | `/api/databases/{db}/tables/{name}/vectors/{column}` | `{ rowKeys, vectorData, embeddingModelVersion?, partitionKey? }` | `200` `{ "rowsInserted", "token" }` |
| `POST` | `/api/databases/{db}/tables/{name}/vectors/{column}:nearest` | `{ queryEmbedding, k }` | `200` `{ "rowKeys", "distances", "executionMs", "token" }` |

#### `POST /api/databases/{db}/edge-tables`

Create an edge table: two `Int64` columns, the source and the destination node ids (and the `rlsColumn`, when given). An edge
table stores every column it has (ADR 0027): add **property** columns with `POST …/tables/{name}/columns` — a scalar or, (**BL-1249,
next train**), an array — and write them with the [bulk load](../guides/bulk-load.md) or `POST …/tables/{name}/rows`. What each
write path stores in them is under [`POST …/edges`](#post-apidatabasesdbtablesnameedges) below.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | The edge table's name. |
| `srcColumn` / `dstColumn` | string | Yes | The source and destination columns' names. |
| `edgeLabel` | string? | No | A label for the table's edges. |
| `storeCsc` | bool | No | Also keep the reverse (destination → source) index, which lets a shortest path search from both ends. Default `false`. |
| A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost. | | | |
| `srcIsPartitionKey` | bool | No | Make the source column the partition key. |
| A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost. | | | |
| `rlsColumn` | string? | No | Adds a `String` column for grant-sourced row conditions (for example `org`). |

A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

```json
{ "name": "follows", "srcColumn": "src_id", "dstColumn": "dst_id", "edgeLabel": "follows", "storeCsc": true }
```

#### `POST /api/databases/{db}/tables/{name}/edges`

Insert edges: `srcs[i]` → `dsts[i]`. The two arrays must be non-empty and the same length (`400 INVALID_REQUEST` otherwise);
`edgeLabels`, when given, holds one label per edge. The answer carries the write's consistency `token`.

This route carries the source, the destination and the label, and nothing else. (**BL-1249, next train**) A **property** column — any
other column of the table — reads **`null`** in an edge inserted here, buffered and after the flush. A property that cannot read
`null` — `NOT NULL`, with a `default`, or computed on write (`derived`, an identity, a server-time stamp, `autoIncrement`) — makes
the route refuse the whole call before anything is written: `400 INVALID_REQUEST`, the message naming the columns:
`Edge table 'follows' has column(s) 'weight' that an edge insert (POST …/edges) cannot fill: NOT NULL, with a default, or computed on
write. Insert these edges through POST …/rows, which takes every column.` Write such edges with `POST …/tables/{name}/rows` (or a
bulk load), which take every column. Before, this route stored the column type's default — `0`, `false`, an empty GUID — in every
property, `null` only in a string. The `rlsColumn` of `POST …/edge-tables` is nullable with no default, so it reads `null` and is
never refused.

```json
{ "srcs": [1, 1, 2], "dsts": [2, 3, 3] }
```

```json
{ "edgesInserted": 3, "token": "…" }
```

A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

#### `POST /api/databases/{db}/tables/{name}/edges:traverse`

Breadth-first traversal: every node reachable from `startNodeId` within `hops` hops (default `1`), each once, the start node not
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
(**BL-1279, 0.9.0**)

```json
{ "startNodeId": 1, "hops": 2 }
```

```json
{ "neighborIds": [2, 3], "executionMs": 1 }
```

#### `POST /api/databases/{db}/tables/{name}/edges:khop`

The k-hop neighbourhood: every node reachable from `startNodeId` within `k` hops (`k` > 0), with its smallest hop distance
(from 1; the start node not included), ordered by distance and then node id. The answer is column arrays: `nodeIds[i]` is at
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
table with partition-level security, the caller sees only the bound claim's partition. A missing, empty, or white-space claim
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

```json
{ "startNodeId": 1, "k": 2 }
```

```json
{ "nodeIds": [2, 3, 4], "hops": [1, 1, 2], "executionMs": 1 }
```

#### `POST /api/databases/{db}/tables/{name}/edges:shortest-path`

The shortest path from node `a` to node `b`: the node ids along it, both ends included, or `[]` when there is none. A table
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
only the bound claim's partition. A missing, empty, or white-space claim is `403 AUTH_PLS_TENANT_CLAIM_MISSING`.
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

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
| A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost. | | | |

A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

#### `POST /api/databases/{db}/tables/{name}/vectors/{column}`

Insert vectors for row keys. `vectorData` is **row-major**: the vectors one after another, `rowKeys.length × dimensions` numbers.
`embeddingModelVersion` records which model made them; `partitionKey` places them in a partition of a row conditions table (the default
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.

```json
{ "rowKeys": [1, 2], "vectorData": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "embeddingModelVersion": "v1" }
```

```json
{ "rowsInserted": 2, "token": "…" }
```

#### `POST /api/databases/{db}/tables/{name}/vectors/{column}:nearest`

Approximate nearest neighbours of `queryEmbedding` (its length is the column's `dimensions`): up to `k` (> 0) hits, nearest first.
The answer is column arrays: `rowKeys[i]` is at `distances[i]` (**Lead S12, 0.6.0; breaking**: it was
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
partition-level security, the caller sees only the bound claim's partition, not another tenant's and not vectors stored with no
A table carries no security member (**BL-1464, 0.16.0**). Access is the caller's statements: a read is filtered, a write outside the `where` is `403 AUTH_ROW_DENIED`. `crossPartitionAccess` only waives the partition-filter cost.
every partition, including unpartitioned vectors. (**BL-1279, 0.9.0**)

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

#### The probes: one meaning each

(**BL-1462, 0.14.0**) Three probes, each answering one question, to **every caller** (no credential, loopback or not) in
every state the process can answer in. None of them is gated by setup mode.

**The port opens before the start sequence runs.** The listener comes up first, and WAL replay, the auth bootstrap, the declared
schema files, roles, keys and replication run behind it, so the probes can watch the start. Every other request, loopback
included, is `503 SERVER_STARTING` with `Retry-After: 5` until the start has finished. (Before, the port stayed closed until the
whole start was over, so a caller saw connection refused and then the final state.)

| Probe | Question | Use it for |
|---|---|---|
| `GET /health` | Is the process alive? | Kubernetes `livenessProbe`. Never a deploy gate. |
| `GET /startup` | Has the start sequence finished? | Kubernetes `startupProbe`. |
| `GET /ready` | Can the server serve application traffic? | Kubernetes `readinessProbe`, a load balancer, a deploy gate, a Docker `HEALTHCHECK`, and therefore Compose `depends_on: condition: service_healthy`. |

What each answers, by state:

| State | `/health` | `/startup` | `/ready` |
|---|---|---|---|
| Opening databases (WAL replay) | `200` `{"status":"healthy"}` | `503` `{"status":"starting","reason":"The engine has not finished opening its databases."}` | `503`, `not_initialized` |
| Start sequence running (auth, declared schema files, roles, grants, keys) | `200` | `503` `{"status":"starting","reason":"The start sequence has not finished ..."}` | `503`, `server_starting`; during the schema apply also `schema_applying` (with `progress`) and `schema_pending` |
| Setup mode (a data directory never set up, nothing declared) | `200` | `200` `{"status":"started","reason":null}` | `503`, `setup_required` |
| Serving | `200` | `200` | `200` `{"ready":true,"reasons":[]}` |
| Serving, a critical component unhealthy | `200` | `200` | `503`, `component_unhealthy` |
| Shutting down | The listener closes first: new connections are refused and requests already in flight finish. There is no "draining" answer. | | |

**Docker Compose.** `depends_on: condition: service_healthy` waits for the dependency's healthcheck, so that healthcheck must
be `/ready`: the dependent service then starts once the server can serve it (started, not in setup mode, declared schemas
applied). The image's `HEALTHCHECK` and the repository's `docker-compose.yml` use `/ready`. A service that must start while the
server is still in setup mode (a tool that creates the first admin) uses `condition: service_started` and polls `/startup`.

Before this, `/health` answered `503 SETUP_REQUIRED` to a caller off the server's host while the server was in setup mode, and
`/startup` answered `503` for as long as setup mode lasted, so a Kubernetes `startupProbe` restarted a server that had finished
starting, every five minutes, for ever. `/startup` also turned `200` as soon as the databases were open, before the declared
schema files were applied; it now waits for the whole start sequence.

#### `GET /health`

Liveness probe. **Always 200** if the process is running, to every caller, in setup mode too (**BL-1462, 0.14.0**). Fast, no
I/O. Use as a Kubernetes `livenessProbe`.

This is **not** “ready for schema apply or traffic”. A database can be `Dropping` or `Creating` while `/health` returns 200.

**Response:**

```json
{
  "status": "healthy"
}
```

#### `GET /ready`

Readiness probe: 200 when nothing is missing, 503 with **everything** that is still missing (**BL-1393, 0.11.0**). No credential is needed, and the route is answered in setup mode and while the server is starting, to any caller (not only loopback).

```json
{
  "ready": false,
  "reasons": [
    { "code": "setup_required", "message": "The server is in setup mode: nothing is declared and no admin account exists. ..." },
    { "code": "database_pending", "message": "Declared database 'ledger' (declaration file) does not exist yet.", "subject": "ledger" }
  ]
}
```

During a start-time schema apply (**BL-1462, 0.14.0**):

```json
{
  "ready": false,
  "reasons": [
    { "code": "server_starting", "message": "The server is still starting: the auth bootstrap has not completed." },
    { "code": "schema_applying", "message": "Applying the schema file of declared database 'orders' (declaration file): 4 of 11 done.", "subject": "orders", "progress": { "done": 4, "total": 11 } },
    { "code": "schema_pending", "message": "Declared database 'reports' (declaration file) has a schema file that has not been applied yet.", "subject": "reports" }
  ]
}
```

`reasons` is always present, and empty when `ready` is `true`. Switch on `code`; `message` is a sentence for a person and may be reworded. `subject` names the database, configured key or component the reason is about, and is absent when it is about the server. `progress` (`done`, `total`, integers) is present only on `schema_applying` (**BL-1462, 0.14.0**).

| `code` | Meaning | `subject` |
|---|---|---|
| `not_initialized` | The engine has not finished opening its databases. | none |
| `server_starting` | The auth bootstrap has not completed, so the server is not accepting requests yet. | none |
| `startup_delay` | `Aouda:Health:StartupDelaySeconds` has not elapsed. | none |
| `setup_required` | The server is in setup mode: nothing is declared and no admin account exists. Create the first admin with `POST /api/auth/setup` from the server's own host, or declare an operator in `server.principals` (the role `admin` and a credential) and restart. A declared operator alone is not setup mode, and a data directory that has been set up never re-enters it (**BL-1462, 0.14.0**). | none |
| `root_user_unusable` | Not produced (**BL-1464, 0.16.0**). The setting it described is refused at start. | none |
| `database_pending` | A database in the declaration file (`aouda.json`) does not exist yet. | the database |
| `database_not_open` | A database in the declaration file is registered and not open (failed to open, or quarantined by something other than an operator). | the database |
| `database_reconcile_failed` | The reconcile of the declared databases after a restore was refused; the server keeps running. | the database, when one is named |
| `reload_failed` | (**BL-1427, 0.14.0**) The last `POST /api/admin/reload` stopped part-way; the steps before it are applied. Cleared by the next reload that completes; a refused reload adds none. | the entry (a database, role or key name), when one is named |
| `schema_pending` | A declared database's `SchemaFile` has not been applied yet (**BL-1406, 0.11.0**). | the database |
| `schema_applying` | (**BL-1462, 0.14.0**) The start-time apply is applying this declared database's `SchemaFile` now. `progress.done` is the declared databases with a schema file whose apply has finished, `progress.total` all of them; the ones not reached yet are each `schema_pending`. Databases are applied one at a time, in name order. | the database |
| `schema_drift` | The start-time apply of a declared `SchemaFile` refused a change (a destructive one without `SchemaAllowDestructive`, or one the engine does not apply), so the catalog is not what the file says; the start went on. `503` until you allow the change or update the file, and restart. A failed apply fails the start instead, so there is no `/ready` to ask (**BL-1406, 0.11.0**). | the database |
| `configured_key_inactive` | Not produced (**BL-1464, 0.16.0**). | none |
| `component_unhealthy` | A critical component (catalog, WAL, memory, ...) is not healthy; every such component is listed. The message is generic (it names the component, never an exception's text); `/health/detailed` and the server log have the detail. | the component |

A database an operator quarantined, or listed in `Aouda:SkipDatabases`, is a decision and is not listed. A reason never contains a key, a hash or fingerprint of one, a password, or an exception message; the server log has the detail. The single `reason` string of earlier versions is gone. A deploy script waits for `200`, and prints `reasons` when it gives up. `aouda status` prints every reason.

`/ready` does **not** fail because an operator database is `Creating` or `Dropping` — that would take the whole node out of a load balancer for a long drop. Per-database readiness is `GET /api/databases/{name}` (`state=Active`) and `/health/detailed`.

The `memory` component is critical too. Either of these makes `/ready` return 503: the managed heap at 75 % or more of its
limit, or a database holding more than 110 % of what it was granted. A database's grant is its **governed ceiling** — the
process's budget, or its hard cap where it has one — not its nominal share, so using room it was given never fails readiness
(**BL-788, 0.3.0**; WorkloadCore S06 deleted elastic lending and the "tightened" verdict). Before that, a database inside
its ceiling could hold `/ready` at 503 for as long as it used it. The reason (`component_unhealthy`, subject `memory`) names the database, its usage and its grant, and the `memory` component's details carry them as
`overBudgetDatabase`, `overBudgetUsedBytes` and `overBudgetGrantBytes`.

Use as a Kubernetes `readinessProbe`.

#### `GET /startup`

Startup probe. `200` `{"status":"started","reason":null}` once the whole start sequence has finished: databases opened, then
the auth bootstrap, the declared schema files, roles, grants and keys. **Setup mode included**: a server waiting for its first
admin has finished starting, and restarting it changes nothing (**BL-1462, 0.14.0**; before, it was `200` as soon as the
databases were open, and `503` for as long as setup mode lasted). `503` `{"status":"starting","reason":"..."}` before that; `GET
/ready` says which step. Use as a Kubernetes `startupProbe`, with a `failureThreshold` × `periodSeconds` that covers WAL recovery
plus any start-time schema apply; once it returns 200, switch to liveness + readiness.

#### `GET /health/detailed`

Component-by-component status (catalog, WAL, replication, backup, materialized queries, memory, per-database `state`). HTTP 200 for healthy/degraded, 503 for unhealthy (critical failure). Degraded responses include `X-Health-Status: degraded`. Admin listener only (404 on the data-plane). Answered in setup mode to every caller, like the three probes (**BL-1462, 0.14.0**).

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

All endpoints live under `/admin/backup/`. Like every `/admin/*` route they need `admin` on the server auth database (**BL-1466, 0.13.1**; see [Auth Enforcement Rules](#auth-enforcement-rules)).

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

`declarationConflict` (**BL-1379, 0.11.0**) is present only when the restored catalog conflicts with the databases declared in `aouda.json` (for example a declared link that differs from the recorded one): the restore succeeded and the engines are open, and the next process start fails on the same conflict until the declaration or the catalog is changed. See [Declared databases](../guides/defaults-reference.md#declared-databases).

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

(**BL-1466, 0.13.1**) `members` is the topology's member list with what the anonymous topology no longer carries: each
member's `perDatabaseStatus` (`{ "<database>": { "walPosition", "lagBytes" } }`) and, for a connected secondary, its `subscriptions`
(`[{ "database", "filterMode", "tableNames" }]`; `null` otherwise). On a standalone node it holds the node itself.

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

**`memory.maxHotBytes` and `memory.maxPageCacheBytes` govern** (**BL-1099, next train**). They are the same server-wide caps as
`Aouda:Memory:MaxHotBytes` (`T10`) and `Aouda:Memory:MaxPageCacheBytes` (`T12`): a PATCH takes effect at once on every database,
each getting its share of the figure as the configuration keys do (the slices add up to the value you set), and on every database
opened later. `0` means "derived" (45 % of the governed budget for the hot tier, 10 % of each database's share for the page cache).
They are saved and apply again after a restart; a saved `0` is "not set", so the startup configuration's value stands — a PATCH of
`0` returns a cap to derived until the next restart, and to the configuration file's value after it. A PATCH of
`memory.maxTotalRamBytes` alone saves no cap. If the PATCH also resizes `memory.maxTotalRamBytes` and the resize is rejected, the
caps are put back too. Before, both were validated, saved and echoed by `GET /admin/config`, and changed nothing.

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

(**BL-1001, 0.14.0**) A stream opened with an keys ends when the key stops authenticating: at once when the key is revoked on this node, otherwise within one `Aouda:WebSocket:HeartbeatInterval` (default 20 s; an expiry, or a linked user disabled). Its last event is `auth_error`, with the codes of [Realtime authorization](#realtime-revoked-credential), and the response then ends:

```text
event: auth_error
data: {"code":"AUTH_TOKEN_REVOKED","message":"keys has been revoked"}
```

Up to 0.13.0 a revoked key's stream stayed open. A stream opened with a JWT is not re-checked.

**Event shape:**

```text
event: log
data: {"timestampUtc":"...","level":"Information","category":"...","message":"..."}
```

---

#### `GET /admin/replication/topology`

Get cluster topology: the replica set's name, its members (address, role, temperature profile, hidden, read candidate), the
read candidates and the primary. No credential is needed — a node joining with `--join` reads it before it has one — so it names no
database and carries no WAL position or table subscription (**BL-1466, 0.13.1**: each member's `perDatabaseStatus` is now `{}`
and `subscriptions` `null` here; they are on the admin-only [`GET /admin/replication/status`](#get-adminreplicationstatus) as
`members`).

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
| `Timestamp` | UTC instant; text with no offset is UTC (see note below) |
| `Date` | A calendar day (days since the Unix epoch). The day written is the day stored: an offset or a `Z` on the text is not applied (**BL-1225, 0.9.0**) |
| `Guid` | UUID/GUID |
| `Double[]` (**BL-035, 0.9.0**) | An [array column](../guides/array-columns.md): one whole array of finite 64-bit floats per row. JSON: an array of numbers; C# `double[]`, TypeScript `Float64Array` |
| `Float32[]` (**BL-035, 0.9.0**) | One array of finite 32-bit floats per row. JSON: an array of numbers (written as the value widened to `double`); `float[]`, `Float32Array` |
| `Int32[]` (**BL-035, 0.9.0**) | One array of 32-bit integers per row. JSON: an array of integers; `int[]`, `Int32Array` |
| `Int64[]` (**BL-035, 0.9.0**) | One array of 64-bit integers per row. JSON: an array of integers; `long[]`, `BigInt64Array` |
| `Byte[]` (**BL-035, 0.9.0**) | One byte string per row. JSON: **one base64 string**, not an array of numbers; `byte[]`, `Uint8Array` |
| `String[]` (**BL-035, 0.9.0**) | One array of strings per row (an element is never null, and must be valid Unicode). JSON: an array of strings; `string[]`, `string[]` |
| `Expression` with `drives` (**ADR 0072, 0.14.0**) | A [formula](../guides/formulas.md) per row, driving another column of the same table; stored as the formula's text. JSON: the formula's object (`null` for an input row); in a column-batch frame, its canonical text. The SDKs write a `Formula` and read either form (`Formula.FromValue` / `Formula.fromValue`). See [create table](#post-apidatabasesdbtables) |

(**BL-035, 0.9.0**) The six array names are matched exactly (`"double[]"`, `"Double []"`, `"Double[][]"`, `"DoubleArray"` and the
type's number are refused). An array value holds at most **65,536 elements** and **1,048,576 bytes of elements** (so a `Byte[]` is at
most 64 KiB, `Float32[]` / `Int32[]` 256 KiB, `Double[]` / `Int64[]` 512 KiB), a nullable column keeps `null` and `[]` apart, and an
element is never null, NaN or infinite. An array column can only be selected: see `ARRAY_COLUMN_UNSUPPORTED`. A non-nullable array
column is allowed at create; one added with `POST …/columns` is always added nullable. A type change into or out of an array type
is refused by `PATCH …/columns/{name}` (`400 INVALID_REQUEST`, *"Changing a column to or from an array type is not supported; add a new
column and copy the values."*); a `schema apply` that asks for it answers `200` with that sentence as a warning, and the column keeps its type. Details: [Array columns](../guides/array-columns.md).

### Timestamp semantics

`Timestamp` values are **UTC instants** stored as **Int64** (.NET UTC ticks). Insert payloads may use ISO-8601 strings or numeric forms accepted by the server; **text with no offset is read as UTC, never in the time zone of the server or the client, and a time of day with no date (`"10:30"`) is refused (BL-1225, 0.9.0)**; **the original timezone offset is not stored** and is **not** round-tripped on read (unlike SQL Server `datetimeoffset`). Clients should expect results in **UTC**. **On a JSON read a `Timestamp` is a number, not text** (**IR quote report, 0.10.0**): .NET ticks — 100 ns units since `0001-01-01T00:00:00Z`, always UTC — in a `/query` columnar `data` array, a subscription `snapshot` page or `change` row, a materialized query's body and a named query's rows alike (`639298350326250000` is `2026-11-09T15:30:32.625Z`; subtract `621355968000000000` for Unix ticks, divide by `10000` for Unix milliseconds). A column the schema declares `String` is text, whatever it holds, so two feeds can differ in shape because their tables differ in column type, not because the server formats them differently. The type is named, so no client has to guess: a columnar response's `types`, the `X-Aouda-Column-Types` header, and a subscription `snapshot`'s `column_types` (`{"DateTime":"Timestamp"}`) all say `Timestamp`. The `@aouda/client` TypeScript SDK reads such a subscription column as a `Date`. A `Date` column is named the same way (`"Date"`, **BL-1391, 0.11.0**; its value is a number of days since the Unix epoch, unchanged on the wire), so a client can tell a day from an `Int32`; `Aouda.Client` then hands a UTC `DateTime` at midnight and `@aouda/client` a JavaScript `Date` at 00:00:00 UTC of that day in a subscription (a query result's `Date` column stays the day number in TypeScript). For full detail and CLR mapping notes, see [Timestamp Type](./timestamp.md) (corrected: it said Unix milliseconds — **BL-808, 0.3.0**). An **upsert** — `"op": "upsert"` on a named mutation, or an upsert on the write stream — accepts exactly the `Timestamp` and `Date` values an insert does, and refuses the ones an insert refuses (a boolean, a fractional number); a table's `culture` applies to a `Date` string on upsert as it does on insert (**BL-643, 0.1.38**).

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
| `token` | string | Yes | The caller's own credential: one key or one session token. A second credential field is `400 INVALID_REQUEST` and the value is not read. |
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

A second credential field is `400 INVALID_REQUEST`. To act as another principal, send that principal's own credential, or a limited key minted from it (`POST /api/auth/keys`).

**Server responds with:** `auth_ok` or `auth_error`.

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
| `filter` | object? | No | Ad-hoc `WhereClause`, or the shorthand `{"column": {"op": value}}`. The operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `nin` and `like`, on the column types the query path accepts them for (no ordering on `Bool` or `Guid`; `like` on `String`). `in` / `nin` take a non-empty array of non-null members of the column's type (**BL-1226, 0.9.0**; up to 0.8.0 they were refused `INVALID_SUBSCRIPTION_FILTER`). The snapshot and the live events select the same rows, a nullable column included: a null never matches `ne`, `nin`, `lt` or `lte` (`eq null` and `ne null` test for null), as in a query. To state that for live events the server adds an `IS NOT NULL` beside each such condition, and an `or` list needs a copy of itself per alternative, so the cost is bounded (**BL-1226, 0.9.0**): one `or` list may hold at most 6 conditions with `ne`, `nin`, `lt` or `lte`, the rewrite may add at most 256 groups and 2048 conditions to one filter, and it may not nest groups past the depth limit of 5. A filter over a bound is refused `INVALID_SUBSCRIPTION_FILTER` before a snapshot. Fold several `ne` on one column that mean "none of these" into one `nin` (`ne` conditions in an `and` list cost one `IS NOT NULL` per column, which no honest filter reaches the bound with), or split the subscription. Up to 0.8.0 a live event with a null matched those four while the snapshot held none, and a `Bool` column's `eq`, `ne`, `in` and `nin` never matched a live event. The user-filter rewrite is unchanged. The same null rule now holds for an row conditions predicate and for a named query's bound clause on the live path, without that rewrite (**BL-1251, 0.9.0**). **Illegal** together with `name` (`NAMED_QUERY_SUBSCRIBE_FILTER`). (**BL-1036, next train**) Read as strictly as a query's `where`: an object with an `and`, `or` or `groups` member is the structured form and may hold nothing else — a shorthand column beside them (`{"v": {"gte": 3}, "and": […]}`) or a member a condition does not have is refused `INVALID_SUBSCRIPTION_FILTER` naming it — and a filter with no condition (`{}`, `{"and": []}`, `{"groups": [{}]}`) is refused too: omit `filter` to subscribe to every row. Up to 0.16.0 the member was dropped (the shorthand half of a mixed filter was lost) and `{}` subscribed to every row. |
| `resume_from` | number? | No | Resume from this **change-event sequence** version. Three outcomes (unchanged): at-current / buffer replay / expired → **fresh complete snapshot**. Feed `gap.last_seq` here after a `gap`. **Not** the consistency token. |
| `at_least` | string? | No | Consistency-token pin: snapshot at at least this token. Optional `wait_ms` / `on_exceeded` (same values as HTTP). Omitted `at_least` leaves `resume_from` byte-for-byte today's path. |
| `wait_ms` | number? | No | Subscribe freshness wait (with `at_least`). |
| `on_exceeded` | string? | No | `wait` \| `fetchPrimary` \| `fail`. |
| `conflate` | object? | No | Opt-in keyed conflation. Omitted = every visible event. See below. |
| `cross_partition_access` | boolean? | No | Waives the `PARTITION_FILTER_REQUIRED` guard for the snapshot of a subscription with no partition filter on a partitioned table (and a named query's count); a named-query subscribe whose definition binds no partition key needs it too. Omitted when `false`. It waives that guard only: the snapshot and every live event are what the credential's access grants allow, no more. Not accepted on the data-plane listener, where the guard decides. The long-poll transport takes it on the same `subscribe` message sent to `…/stream/longpoll/{sessionId}/send` (**BL-1227, 0.9.0**). |

**`conflate`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string[]? | Conditional | Columns that form the conflation key. Default: table primary key. Required when the table has no PK. |
| `interval_ms` | number | Yes | Flush interval in milliseconds. Valid range 1…60_000. |
| `collapse_inserts` | bool | No | When true, matching in-scope inserts are held latest-wins per key. Default `false` (omitted on the wire). Delivered `op` stays `"insert"`. |

(**BL-035, 0.9.0**) A `filter` or a `conflate.key` that names an [array column](../guides/array-columns.md) is refused with an `error` message, code `ARRAY_COLUMN_UNSUPPORTED` (*"… an array column cannot be used in a subscription filter …"*, *"… cannot be a conflation key (conflate.key) …"*); the subscription is not created. Selecting one is fine.

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

(**ADR 0072, 0.14.0**) **A formula table** is subscribed to like any table, filtered on its own columns:

```json
{
  "type": "subscribe",
  "id": "retail-2026",
  "target": "pnl",
  "filter": { "and": [ {"column": "dept", "op": "eq", "value": "Retail"}, {"column": "year", "op": "eq", "value": 2026} ] }
}
```

After an input edit the subscription receives the input's `change` and then each formula row that changed, once, at its final value; an
unchanged recompute sends nothing. An `Expression` column's value is the formula's JSON object in a snapshot page's `data` and in a
change's `row` and `prev` (a map in MessagePack); (**BL-1495, 0.15.0**) a snapshot's `column_types` names it `"Expression"`, as it
names a `Timestamp`, so a typed client can read the object as a formula. `at_least`, `wait_ms` and `on_exceeded` are judged by the
formula maintainer's progress, as on a read. See [Formulas](../guides/formulas.md#live-subscriptions).

**Server responds with:** one or more `snapshot` pages (same `version`), then `snapshot_complete`, then `change` messages. Over `MaxSnapshotRows` (default 100 000) the subscribe fails with `SNAPSHOT_TOO_LARGE`. Overflow during paging fails with `SNAPSHOT_OVERFLOW` (not a `gap`).

**Limits:** per-connection 32 subscriptions, per-identity 128, the same cap for every principal (**BL-1464, 0.16.0**; the numbers are **BL-1383, 0.11.0**). There is no larger cap for one kind of credential. Exceed → `SUBSCRIPTION_LIMIT_EXCEEDED`. A re-sent `id` replaces and never trips the cap. The limits that apply to the connection (`limits`: `max_subscriptions_per_connection`, `max_subscriptions_per_identity`, `max_connections_per_identity`, `subscribe_burst`, `subscribe_refill_per_second`) and the server's `protocol` (`version`, `capabilities`) arrive in `auth_ok` (**BL-1383, 0.11.0**). A subscribe is also bounded per identity by a token bucket: over it, `SUBSCRIBE_RATE_EXCEEDED` with `retry_after_ms`.

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

Re-authenticate an existing WebSocket session with a refreshed JWT (or keys) **without** tearing down subscriptions. Not valid as the first message — the first message remains `auth`.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Always `"re_auth"` |
| `token` | string | Yes | Refreshed bearer JWT or keys |
| `token` | string | Yes | The caller's own credential. A second credential field is `400 INVALID_REQUEST`. |

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

**Authorization** (**BL-1227, 0.9.0**). `stream_open` needs the `write` role permission on the table, as `POST …/tables/{name}/rows` does; the check runs before the table is looked up, so a credential without it learns nothing about which tables exist. A refusal is an `error` message for the stream `id` with HTTP's code (`INSUFFICIENT_PERMISSIONS`, `AUTHORIZATION_DENIED` or `AUTH_TOKEN_MISSING`). Up to 0.8.0 a write stream checked no role. On a table with row conditions or row conditions the rows are then written under the same write rules as HTTP, with the access grants of the credential (a grant at `write` or `admin` lifts the write side); a grant that decides a stream is audited once per stream, with the first batch of rows it decides, and again only when the grants that decide it change (a `re_auth`, or a role change that re-keys the session) ([Audit](#audit-`unconditional_access`)).

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
| `user_id` | string? | Authenticated user ID. Null for keys or unauthenticated connections. |
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
| `code` | string | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
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
| `column_types` | object? | (**BL-035, 0.9.0**) A map from column name to type name (`{"Rates":"Double[]"}`) for each [array column](../guides/array-columns.md) of the snapshot, the same on every page (a page with no rows may name array columns it does not hold). (**IR quote report, 0.10.0**) It also names each `Timestamp` column, as `"Timestamp"` (`{"DateTime":"Timestamp"}`): the cells are .NET ticks, see [Timestamp semantics](#timestamp-semantics). (**BL-1391, 0.11.0**) And each `Date` column, as `"Date"` (`{"day":"Date"}`): the cells are a number of days since the Unix epoch. On **every** page, an empty snapshot's and a subscriber denied by an embargo included. **Omitted when the snapshot has none of them.** A column named with an array type holds an array of that type; a column named `Timestamp` holds ticks; a column named `Date` holds days; a column that is not named holds another scalar. (**BL-1495, 0.15.0**) And each `Expression` column, as `"Expression"` (`{"formula":"Expression"}`): the cell is the formula's JSON object, on every page, a denied subscriber's empty page included. A `change` does not repeat a `Timestamp`, `Date` or `Expression` column's name — a client keeps the snapshot's. `Aouda.Client` and `@aouda/client` convert it (a `Date` becomes a UTC `DateTime` at midnight in C#, a JavaScript `Date` at 00:00:00 UTC in TypeScript; see [Timestamp semantics](#timestamp-semantics)). |

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
| `column_types` | object? | (**BL-035, 0.9.0**) As on `snapshot`: the array columns `row` / `prev` carry, name to type name; omitted when there is none. |

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
that is not denied it: a notice names no row, so `filter`, a named query's bound `where` and row conditions do not apply. A conflated
subscription sends what it holds first. An embargoed subscription's notice goes through its embargo hold (**BL-1317, next train**):
a held change the notice covers is never released after it, the notice's time (`horizon` / `before`) is at most the subscriber's
cutoff — `now − embargoSeconds` plus one tick, for a `Date` column the next day at midnight UTC — and a subscription whose embargo
releases nothing gets none. A client that does not know these types ignores them ([Type Discriminator](#type-discriminator))
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

`FORBIDDEN_WRITE` at an index is a row row conditions or row conditions refused; the frame's other rows are written. (**BL-1227, 0.9.0**) With
`mode: "upsert"` that includes a row whose key names a stored row the caller may not write (another partition, another row conditions
owner): an upsert may replace only a row the caller may write.

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
| `POST` | `/api/databases/{db}/bulk-load/{jobId}:abort` | Abort the session. The beginning credential only (**BL-1278, BL-1170, 0.9.0**). |
| `GET` | `/api/databases/{db}/bulk-load:list` | List the sessions this credential began (**BL-1278, BL-1170, 0.9.0**). |
| `POST` | `/api/databases/{db}/bulk-load:force-abort` | Operator abort; the job id is in the body. The beginning credential, or a database admin who also holds `bulkload` (**BL-1278, BL-1170, 0.9.0**). (Listed under `{jobId}` until **WorkloadCore, 0.3.0**; the route has always been this.) |

---

### `POST :begin`

Allocate a bulk-load session and acquire table locks. Returns a `jobId` that all subsequent requests must reference.

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `database` | string | Yes | Database name (must match `{db}` in path). |
| `tables` | string[] | Yes | Tables this load writes to. Index 0 is the primary table. Single-element array for single-table loads. When more than one table is listed, each row in `:append` calls must carry a `"_table"` discriminator field naming its destination. Empty array is rejected (400). |
| `options` | object? | No | Load options (see below). |
| `idempotencyKey` | string? | No | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |

**Load options:**

| Field | Type | Default | Allowed values | Description |
|---|---|---|---|---|
| `conflictPolicy` | string? | `"block"` | `"block"`, `"failFast"` | How to handle a conflicting in-flight job on the same table. `"block"` waits; `"failFast"` returns `BULK_LOAD_TABLE_LOCKED` immediately. Case-insensitive. |
| `afterJobId` | string? | null | a `jobId` a `:begin` returned | (**Lead S21b, 0.6.0**) The job this one follows: a job on the same tables, begun before it. This job takes its place in the tables' commit order after that one — it does not take the tables first, even if that job is still waiting for them behind another loader's job — and **commits only if that job committed**. If that job failed or was aborted, this job's commit is refused `409 BULK_LOAD_PREDECESSOR_NOT_COMMITTED` and none of its rows is loaded. A loader that sends job N+1 while job N commits names N here, so a failure in N leaves every later job uncommitted, and a sequence of jobs commits a prefix of them, in order. A job that follows a job on **other** tables waits, at its commit point, for that job's outcome (**Lead group 5 review, 0.6.0**: it read the outcome at once, and was refused or not by timing). A job that names itself is refused `400 BULK_LOAD_INVALID_OPTIONS`. Not a job id: `400 BULK_LOAD_INVALID_OPTIONS`. Both SDKs' multi-job loaders set it (`@aouda/client` from **Lead S22, 0.6.0**). |
| `validation` | string? | `"coerce"` | `"coerce"`, `"strict"` | (**Lead S27a, 0.6.0**) What the load checks ([Bulk Load — a load's validation](../guides/bulk-load.md#a-loads-validation-coerce-or-strict-lead-s27a-060)). `"coerce"`: a null or absent cell in a NOT NULL column is stored as the type's default (`0`, `""`) — **except in a primary-key column**, which is refused (see [`:append`](#post-jobidappend)); keys are not checked for uniqueness — except a formula table's (a table with an Expression column), whose keys are checked at
every level, as at `"strict"` (**BL-1488, 0.15.0**). (**BL-035, 0.9.0**) **An [array column](../guides/array-columns.md) has no default, so a NOT NULL array column refuses a null or missing cell at every level, `coerce` included.** `"strict"`: a null or absent cell in any NOT NULL column is refused the same way — (**BL-1104, next train**) except an absent cell of a column with a default, which takes the default at either level (only a null is refused there) — and a primary key the job holds twice, or one the table already holds, fails the job at its commit (`409 BULK_LOAD_DUPLICATE_PK`, nothing committed). Every load refuses a column its table does not have. An auto-increment column is exempt (a missing value takes the next id). Refused `400 BULK_LOAD_INVALID_OPTIONS`: any other value (case-sensitive); `"strict"` on a table whose key mode (`pkUniqueness`) is not `Strict` — a job is never stricter than its table — or with `applyTransforms`. |
| `pkUniquenessOverride` | — | — | — | (**Lead S27a, 0.6.0; breaking**) Removed: no server ever applied it. Any value is refused `400 BULK_LOAD_INVALID_OPTIONS` with a message naming `validation`. |
| `replicationMode` | string? | `"logShipSegments"` | `"logShipSegments"`, `"skipReplication"`, `"markForSnapshot"` | Replication strategy. `"skipReplication"` on a multi-node cluster without `forceSingleNodeReplicationBypass: true` is rejected (400 `BULK_LOAD_INVALID_OPTIONS`). Case-insensitive. |
| `forceSingleNodeReplicationBypass` | bool? | `false` | `true`, `false`, null | Two-key safety valve: must be `true` to use `"skipReplication"` on a multi-node cluster. |
| `maxRowsPerSegment` | number? | null | Any positive integer | Override the maximum rows per sealed segment. Null = use server default. |
| `embeddingModelVersion` | string? | null | Any valid model version string | Embedding model version for vector-indexed tables. **Required** when a table of the job has a vector column: (**BL-1248, next train**) its absence is refused at `:begin` with `400 BULK_LOAD_INVALID_OPTIONS` (`EmbeddingModelVersion is required for vector-bearing tables.`); it was accepted there and failed the job at its first `:append` (`409`) and `:commit` (`500 INTERNAL_ERROR`). |
| `postLoadMqBehavior` | string? | `"auto"` | `"auto"`, `"skip"` (`"deferred"` until 0.3.x; refused `400` from the 0.4.0 — use `"auto"`) | Controls materialized-query handling after commit, for **all four** MQ types whose source tables are in this load. `"auto"` (default): the load's queries are brought current by the server, and you wait on `mqRebuildStatus` (below) — **do not** also call `POST .../materialized-queries/{name}:refresh` for these tables: it runs the table's pass that was starting anyway or, once that has run, re-scans the whole source table. (**WorkloadCore S10, 0.3.0**) `"auto"` records a pending job, as `"deferred"` did, and starts the table's **deferred pass** for each table it wrote right after the commit (multi-table and transform loads included): a fold of the load's segments for every query the fold can plan, the load's rows applied as inserts for any other query directly over the table, a rebuild for the rest (**WorkloadCore S17, 0.3.0**: by a background rebuild job after the pass, so the other queries on the table are not held behind one long rebuild), and the queries built on them caught up. The load does no materialized-query work while its rows stream and is not paced to a drain. Until the pass ends its queries read as behind (`isStale: true`, `pendingDeferredJobs` ≥ 1, `current: false`). Before S10, how `"auto"` did it depended on the table: a table of only `aggregate` and `latestPerKey`/`firstPerKey` queries was folded as the load wrote its segments and written by the table's pass after the commit; on any other table the queries accumulated during the load's own pass and published by shadow-swap after the commit (the ingest-fed path). (**WorkloadCore S09, 0.3.0**) Every `"auto"` load's maintenance runs after the commit point, in the background, and `:commit` waits for it only as long as `mqWaitMs` allows (below): on a table of only aggregates and latest / first per key the load used to write its queries before `:commit` returned, with `mqRebuildStatus: "completed"` (**ColumnarCore S12, 0.2.0**). `"skip"`: no pending job, no pass and no rebuild; use for multi-step pipelines that call `:refresh` explicitly themselves. (**LoadSpeed K31, 0.4.0**) `"deferred"` is refused `400 BULK_LOAD_INVALID_OPTIONS` with a message saying to use `"auto"`: it was folded into `"auto"`, which since M.3 leaves a loading table's pass to the quiet period as `"deferred"` did, and which with `mqWaitMs` 0 (the default) does not wait at `:commit`. Until then: `"deferred"` (**BatchFirst S08, 0.1.40**): the load writes only the table, marks its queries behind (`isStale: true`; **WorkloadCore S10, 0.3.0**: owed the pass, not marked stale as `"skip"` leaves them), and records a durable pending job; the table's deferred pass brings them current once bulk ingest into the table has been quiet for 2 s, or once the oldest pending job has waited 60 s, or at once on `:refresh` of any owed query — and an update, delete or upsert of the table brings its queries current before it applies. It was for very large or many back-to-back loads: many loads, one pass (a server before 0.1.40 refused it `400` too). See [Deferred loads](../guides/materialized.md#deferred-loads). |
| `identityInsert` | bool? | `false` | `true`, `false`, null | Job-scoped identity-insert (same semantics as ordinary insert `identityInsert`). When `true`, every autoIncrement column must be present/non-null on every appended row; values (including literal `0`) are stored as-is with **no** ID allocation; after a **successful job commit** the runtime counter advances to `max(inserted)` per `(table, column)`. Failed or aborted jobs do **not** bump the counter. Null/`false` = default bulk-load path (missing/null autoIncrement values coerce to `0`; bulk-load alone does not allocate IDs or bump the counter). Equivalent to Bond `isAutoIncrementDisabled: true` for large ingest. |
| `applyTransforms` | bool? | null | `true`, `false`, null | **Transform intent.** The server computes every write-time value (derived columns, expression defaults, checks) for the rows you append, and expands the lock set to the transform-graph closure. Mutually exclusive with `preTransformed`. |
| `preTransformed` | bool? | null | `true`, `false`, null | **Transform intent.** The rows are already materialized — every derived column is present in the payload — so the server writes the named tables as-is with no transform pipeline. Mutually exclusive with `applyTransforms`. An identity column is refused `400 BULK_LOAD_IDENTITY_REQUIRES_TRANSFORMS`, the same as a server-time column: use `applyTransforms` (**BL-1278, BL-1170, 0.9.0**). |
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

**Authorization (**BL-1464, 0.16.0**).** `:begin`, every `:append` and `:commit` require an unconditional `write` (a statement with no `where`) on every table the load writes — the tables in the request, plus transform targets when `applyTransforms` is set. A statement with a `where` admits none of the load: no row check sees the rows. The refusal is `403 AUTH_POLICY_DENIED`, naming each refused table, with remedy `grant` of that unconditional statement (`none` when a credential limit refused it). `AUTHORIZATION_DENIED` is not produced. A table that is gone is `404 TABLE_NOT_FOUND`. A statement with no `where` on a table another statement restricts is audited as [unconditional access](#audit).

---

### `POST {jobId}:append`

Append frames of rows to an in-flight session. The beginning credential only: another credential is `403 AUTH_POLICY_DENIED` with remedy `none`, and nothing is appended (**BL-1278, BL-1170, 0.9.0**; the code is `AUTH_POLICY_DENIED` since **BL-1464, 0.16.0**).

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
checked the same way. Key uniqueness is checked at the commit, and only at `"strict"` — and, at every level, in a formula table
(**BL-1488, 0.15.0**) (`409 BULK_LOAD_DUPLICATE_PK`).

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
kind    := 0 Null (no values) · 1 Int64 · 2 Double · 3 Bool · 4 String · 5 Timestamp · 8 ScaledDecimal · 9 Array   (6: retired, refused)
values  := Int64, Timestamp : rowCount × i64   (Timestamp: 100-ns ticks since 1970-01-01T00:00:00Z)
         | Double          : rowCount × f64
         | Bool            : bitmap
         | ScaledDecimal   : scale:u8 (≤ 18), then rowCount × i64 — each value v / 10^scale (ColumnarCore S13)
         | String          : dictCount:u32, then dictCount × (len:u32 utf8), then rowCount × u32 codes
         | Array           : elementKind:u8  offsets:(rowCount + 1) × u32  elements        (BL-035, 0.9.0)
```

(**BL-035, 0.9.0**) **Kind 9, `Array`**, carries an [array column](../guides/array-columns.md): one whole array per row.

```
Array   := elementKind:u8  offsets:(rowCount + 1) × u32  elements
elementKind := 1 Int32 · 2 Int64 · 3 Float32 · 4 Double · 5 Byte · 6 String            (0 and anything above 6: refused, naming the number)
offsets     := offsets[0] = 0, never decreasing; row i holds offsets[i+1] − offsets[i] elements
elements    := Int32: total × i32 | Int64: total × i64 | Float32: total × f32 | Double: total × f64 | Byte: total × u8
             | String: byteOffsets:(total + 1) × u32  utf8[byteOffsets[total]]            (total = offsets[rowCount])
```

- **Little-endian, not widened, no padding.** `Float32` elements are 4 bytes each and `Int32` elements 4 (they are not widened to 8
  as the scalar kinds are); `elements` follows `offsets` with no padding. A `String` element `j` is the UTF-8 in
  `byteOffsets[j]` … `byteOffsets[j+1]`.
- **Null, absent and empty.** A null or absent row has count 0 (the bitmaps tell it apart from an empty array, as for every kind); a
  reader refuses a null row whose count is not 0.
- **The reader is strict.** It refuses an element kind of 0 or above 6, offsets that do not start at 0 or that decrease, a `String` element that is not valid UTF-8, a value over 65,536 elements or 1,048,576 bytes of elements, and a `Double` or
  `Float32` element that is NaN or ±Infinity.
- **On insert the element kind must be the column's own** (see `POST …/rows`); a query response carries the element kind of the
  column's type.
- **A reader that does not know kind 9** fails: the C# reader with *"Column '…': unknown kind 9."*, the TypeScript reader with
  *"Malformed column-batch frame: column '…' has unknown kind 9."*.
- The decoded size of a column is charged to the reader's 256 MB budget before its elements are read.

A `Double[]` column of two rows `[1.5, 2.5]` and `null`, and a `String[]` column `["x","y"]` and `[]`, as one data frame (an
excerpt of a real response, kind 9 columns only; the first row's `D` has two elements, the null bitmap `02` marks row 1):

```
D:  09 01 02   04   00000000 02000000 02000000   000000000000f83f 0000000000000440
    kind flags nulls elementKind offsets (0, 2, 2)   1.5   2.5
S:  09 00      06   00000000 02000000 02000000   00000000 01000000 02000000   78 79
    kind flags elementKind offsets (0, 2, 2)     byteOffsets (0, 1, 2)       "x" "y"
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
fractions is read as decimal for every row — except in a `String` column, whose numbers keep their text as sent (**BL-1108, next
train**; see [values](#column-arrays-the-write-body)).

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
| `AUTHORIZATION_DENIED` | 403 | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| `BULK_LOAD_INVALID_STATE` | 409 | Job is not in `"appending"` state. |
| `MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED` | 503 | (**WorkloadCore S16, 0.3.0**) The job's load already failed for capacity — for example its memory wait ran out after `:begin` returned. `Retry-After` is set; it is what `:commit` would answer (it used to be a 409 asking for `:commit`). |
| `MEMORY_BUDGET_EXCEEDED` | 503 | (**BL-831, 0.3.0**) A column-batch body could not get the memory to decode its next frame: each column's array is asked of the memory queue before it is allocated, waiting at most one sampling tick. The session stays open and the frames queued before the refusal stay credited: wait `Retry-After` and resume as on any reconnect (the same `:begin`, from its `nextSequence` — **Lead S21a, 0.6.0**; it was `resumeFromRow`). It used to fail on the heap mid-frame and answer `500`. |
| `BULK_LOAD_MISSING_DISCRIMINATOR` | 400 | Multi-table job and a row is missing `_table`, or names a table outside the job; none of its frame's rows is applied (**Lead S21a, 0.6.0**). `details: frame={f}, row={n}, …` (**Lead S12, 0.6.0**: was `lineNumber=N`). |
| `ROW_OBJECTS_UNSUPPORTED` | 415 / 400 | (**Lead S12, 0.6.0**) `415`: an NDJSON body (`application/x-ndjson`), no longer read. `400`: a JSON body that carries `rows`. Nothing is appended. Send frames or [column arrays](#column-arrays-the-write-body). |
| `INVALID_REQUEST` | 400 | A JSON body that is not valid column arrays (it appends nothing), or a malformed frame (the frames before it stay credited). (**BL-1110, next train**) A frame `Double` cell that is NaN or ±Infinity, as `POST …/rows` refuses it: *"Column 'px' row 2 of frame 0 is NaN: a Double cell must be finite (JSON cannot carry NaN or Infinity). None of the frame's rows was applied."* — it was stored. (**BL-1250, next train**) A JSON array or object for a scalar column, naming the column and the row. |
| `BULK_LOAD_CURSOR_MISMATCH` | 409 | (**Lead S21a, 0.6.0**) The body's first frame is above the job's next number: frames between them were never applied. Nothing of the body is applied; `details` name `nextSequence`. (It was documented as "resumed below `rowsDurablyCommitted`", which no server answered.) (**Lead S21b, 0.6.0**) Also a body whose end frame commits and names fewer frames than the job holds: nothing committed. |
| `BULK_LOAD_INVALID_STATE` | 409 | The job is committing, committed, aborted or failed. (**Lead S21b, 0.6.0**) `details` name the state (`state=Committing`, …): a body sent again while its own commit runs reads `Committing` — wait, then `:begin` with the job's key. |
| `BULK_LOAD_PREDECESSOR_NOT_COMMITTED` | 409 | (**Lead S21b, 0.6.0**) A body that commits a job begun with `afterJobId`: the job it follows failed or was aborted, so this one is not committed and none of its rows is loaded. `details` name `afterJobId`. Also answered by `:commit`. |
| `BULK_LOAD_COMMIT_QUEUED` | 409 | (**Lead group 5 review, 0.6.0**) A body whose end frame commits its job, for a job still queued behind another load on its tables: the body's frames were applied (`details`: `nextSequence`, `rowsAppended`), nothing was committed, and the job is open. Send `:commit`; send no row again. |
| `BULK_LOAD_LOST` | — | (**Lead S30, 0.6.0**) Not a response's status: the `errorCode` of a job `GET {jobId}` reports `"lost"` — answered `accepted` by `:commit` (`wait: "accepted"`), then lost before its commit point. Nothing of it is durable; load it again. (**Lead S26c, 0.6.0**) Also an `"os"` job dropped at the open after a power loss (`durability: "os"`): load it again with the same idempotency key. |
| `FRAME_VERSION_UNSUPPORTED` | 415 | (**Lead S09, 0.6.0**) An `ACB1` body, or the retired `application/vnd.aouda.column-batch` type. Nothing is queued. Upgrade the client. |

---

### `POST {jobId}:commit`

Commit the session. The beginning credential only: another credential is `403 AUTHORIZATION_DENIED` and nothing is committed (**BL-1278, BL-1170, 0.9.0**). All sealed segments become queryable. (**Lead S21b, 0.6.0**) A job whose last body is column-batch frames
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
  `waitMs` to be answered when it settles. Both SDKs ask as soon as the accepted answer arrives (**BL-1140, 0.9.0**). After a
  restart that cut the job off, `GET {jobId}` answers `"lost"` (`200`, `errorCode` `BULK_LOAD_LOST`): load it again. Once the server's
  log has moved past the job (a checkpoint), it answers `404 BULK_LOAD_JOB_NOT_FOUND`. A `404` before one hour from the accepted answer is
  still lost: nothing of it is durable, load it again. A `404` at or after that hour is unknown: it cannot tell a lost job from a
  committed one the server has forgotten, and that tick is the first on which a committed header may be forgotten. Both SDKs reject it
  as unknown rather than lost (**BL-1140, 0.9.0**). The server keeps a committed job's
  record for at least an hour after its commit (or `Aouda:BulkLoad:IdempotencyWindowMinutes`, if longer). A `200` `state: "lost"` with
  `BULK_LOAD_LOST` is unchanged: load it again. A job that passed its commit point is never answered `"lost"`, even when work after it
  failed (**Lead group 7 review, 0.6.0**). Don't infer the outcome from the token: a lost job's token reads as covered once the log
  moves past it, and its rows are not there.
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
| `BULK_LOAD_DUPLICATE_PK` | 409 | (**Lead S27a, 0.6.0**) A job at `validation: "strict"` — or any job, in a table with an Expression column (**BL-1488, 0.15.0**) — holds a primary key twice, or one the table already holds. Nothing of it was committed; the message names the table and the key, and `details` is `{"table", "sampleKeys", "totalDuplicateCount", "withinJob"}` (the check stops at the first key). Deduplicate the source and load it again, load at `"coerce"`, or upsert the rows. The check waits for the writes that were in flight on the table when the job began to commit, so an insert racing the load and the load never both write one key. |
| `INVALID_REQUEST` | 400 | (**Lead S27a, 0.6.0**) A row the engine refused (a column the table does not have, a missing key): the same rule as `:append`'s frame check, for a row that reached the engine another way. Nothing committed. |
| `IDENTITY_STAMP_REQUIRED` and the other insert-transform codes | 400 | (**BL-1277, 0.9.0**) `:commit` of a row the insert transform refuses. The code is the one a REST insert already returns for that row (`IDENTITY_STAMP_REQUIRED`, `TRANSFORM_DERIVED_READONLY`, `CONSTRAINT_CHECK_VIOLATION`, `TRANSFORM_ROUTE_UNMATCHED`, `TRANSFORM_ROUTE_AMBIGUOUS`, and the other codes the exception carries), with `rowErrors`. `GET {jobId}` shows `state: "failed"` and that `errorCode`. Nothing was committed. Fix the row and run the load again from `:begin`. A failure after the commit point is still the 500 below and must not be sent again. |
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

Get current session state and progress. The beginning credential only: another credential is `403 AUTHORIZATION_DENIED` and the body has no `token`, including a committed job whose session is gone (**BL-1278, BL-1170, 0.9.0**).

(**Lead S30, 0.6.0**) **Query parameter `waitMs`** (`0`–`60000`, default `0`; outside that `400 BULK_LOAD_INVALID_OPTIONS`):
for a job whose commit is running — `committing`, or `accepted` — the answer waits up to that long for the job to settle (committed,
failed, lost or aborted), then answers as it stands. This is how a client learns an accepted job's outcome without polling.

A `404 BULK_LOAD_JOB_NOT_FOUND` before one hour from an accepted answer is still lost: nothing of the job is durable, so load it
again. A `404` at or after that hour is unknown. It cannot tell a lost job from a committed one the server has forgotten, and that
tick is the first on which a committed header may be forgotten. Both SDKs treat it as unknown rather than lost (**BL-1140, 0.9.0**).
The server keeps a committed job's record for at least an hour after its commit (or `Aouda:BulkLoad:IdempotencyWindowMinutes`, if longer).

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

List the sessions this credential began. Another credential's job is omitted, not a 403 for the list (**BL-1278, BL-1170, 0.9.0**).

**Response body:**

| Field | Type | Description |
|---|---|---|
| `database` | string | Database name. |
| `jobs` | array | Array of status objects (same structure as `:status` response). |
| `snapshotUtc` | string | UTC timestamp of this snapshot. |

---

### `POST {jobId}:abort`

Abort an in-flight session. The beginning credential only: another credential is `403 AUTHORIZATION_DENIED` and the job is not aborted (**BL-1278, BL-1170, 0.9.0**). A missing job is `404 BULK_LOAD_JOB_NOT_FOUND`.

### `POST {jobId}:force-abort`

Operator abort of an in-flight session. The beginning credential, or a database admin who also holds `bulkload`. Anyone else is `403 AUTHORIZATION_DENIED` and the job is not aborted (**BL-1278, BL-1170, 0.9.0**). Releases table locks and records the abort reason in the WAL.

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
| 1.3 | 2026-03-19 | Comprehensive authentication section: credential types, auth enforcement flow, a second header, server and app auth endpoint reference |
| 2.0 | 2026-05-22 | WebSocket streaming protocol documented; Bulk Load API documented; `crossPartitionAccess`, `joins`, WhereClause `groups`; write concern on mutation messages; Known Limitations updated; Future Extensions corrected |
| 2.1 | 2026-06-23 | P27: `setExpr` expression SET, `TRUNCATE`, DELETE `limit`/`orderBy`, `RETURNING`, batch mutations (`/rows/batch`), expression SELECT (`selectExpr`). P28: `TruncateToMinute` partition function. P31: `postLoadMqBehavior` on bulk-load `:begin`; `mqRebuildStatus` in `:status` response; `POST .../materialized-queries/{name}:refresh`. P33: password reset endpoints, MFA enroll/challenge/verify/factors/delete, admin password override, invite resend, `requiresPasswordChange`/`mfaRequired`/`mfaFactors`/`aal` in signin response. |
| 2.2 | 2026-07-31 | BL-130: `identityInsert` on `POST …/tables/{name}/rows`. BL-131: `options.identityInsert` on bulk-load `:begin` (commit-only counter floor). |
| 2.2 | 2026-06-26 | **P17 (breaking):** `GET /api/databases` default response now excludes internal infrastructure databases (`_serverauth`, `_settings`). Use `?include=internal` to retrieve the full catalog. All database responses now include `isInternal` (bool), `isAuthDatabase` (bool), and `authDatabaseKind` (`"none"` \| `"server"` \| `"application"`) metadata fields. Application auth databases (`isInternal: false`) remain in the default list. |
| 2.3 | 2026-08-19 | **P37 / server 0.1.7:** named-query execute + read-only batch (cap 32, one snapshot, positional errors); named-mutation execute; a key*` + data-plane listener (404 not 403); WebSocket path `/api/databases/{db}/ws`; `subscribe.hash` / `args` / `conflate`; `snapshot_complete`; server `gap` (`last_seq`, `discarded`); `change.values_skipped`; `re_auth`; access-surface `?access=true`. Additive on the wire. |
| 2.4 | 2026-08-21 | **P38:** consistency token (`X-Aouda-Token` / `?at_least=` / envelope `token` / `GET …/token`); named-query alias `freshness`; `TOKEN_*` / `FRESHNESS_*` errors; stream `token` alongside `version`; bulk-load commit `walPosition` → `token`. **Breaking:** `MaxLagSeconds` is measured staleness, not lag-bytes ÷ 1 MB/s. Default read preference remains `Primary`. |
| 2.5 | 2026-08-22 | **BL-188:** named-query identity is the unique schema name. **Breaking:** `{name}` routes and batch/subscribe/warning `"name"`; alias surface (`?alias=`, `X-Aouda-Named-Query-Alias`, body `alias`) and `NAMED_QUERY_ALIAS_MISMATCH` retired; omitting a name deletes the definition; codegen is types-only (optional Args/Row). Historical 2.3 / 2.4 shipped content-hash identity. |
| 2.6 | 2026-08-29 | **Catalog GET/list auth linkage:** `auth.enabled` / `auth.database` on every database response (never a key*` on GET). GET `{name}` documented as metadata-only; 404 while `Dropping`. Health probe split (`/health` liveness vs `/ready` / GET `state=Active`). Create-role `permissions` optional; 400 `INVALID_REQUEST` with `suggestion`. |
| 2.7 | 2026-09-07 | **BL-406 (documentation only, no wire change):** bulk-load `:begin` options table gains `applyTransforms` / `preTransformed`, with the rule that a table carrying any write-time compute requires exactly one of them, and guidance on which to pick. Adds the bulk-load deadline, append-size and admission-lane settings (`Aouda:BulkLoad:StreamingRequestTimeoutMs`, `SessionIdleTimeoutMinutes`, `MaxConcurrentStreamingRequests`, `StreamingRequestQueueLimit`, `Aouda:MaxConnections: 0`) — **not yet released**: BL-404 / BL-405 are on `Unreleased` and ship in the **next** server train, after 0.1.20. |
| 2.8 | 2026-09-30 (0.2.0) | **ColumnarCore S06 / S13, BL-716 (additive on the wire):** `POST …/tables/{name}/rows` also accepts one column-batch frame (`Content-Type: application/vnd.aouda.column-batch`; database and table from the URL, `identityInsert` / `writeConcern` as query parameters), advertised by `Accept-Post: application/json, application/vnd.aouda.column-batch` on the endpoint's responses and by `features.insertColumnBatch` in `GET /admin/capabilities`; an older server answers a frame with `415`. Column-batch frames gain the `ScaledDecimal` kind (`8`). `Decimal` columns may declare `precision` / `scale` (`Decimal(p,s)`, `1 ≤ p ≤ 18`, `0 ≤ s ≤ p`) on create-table, add-column and column details. Insert errors: a body that is not valid JSON is `400 INVALID_REQUEST` (was MVC's validation problem), an empty body is `400 MISSING_DATABASE`; a string cell that is not valid UTF-8, or a non-finite `Double` in a frame, is a `400`. |
| 2.9 | 0.3.0 (ColumnarRead) | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| 2.10 | 0.3.0 (WorkloadCore) | **WorkloadCore S09:** materialized-query maintenance is off the commit — an insert's `200` and an `"auto"` load's `:commit` no longer wait for their queries to be written. Bulk-load `:commit` gains `mqWaitMs` (a bounded wait for the load's queries, default 30000) and answers `mqStatus`, `mqFrontierToken` and `mqWaitedMs`; `mqRebuildStatus` is never `"completed"` from the commit itself; a single-node load's `token` is the WAL head at its commit. **WorkloadCore S10:** every load but a `"skip"` one is a pending job brought in by the table's pass (`"auto"` starts it at the commit); the ingest-fed path is gone; a query owing a load reports `isStale: true`, `pendingDeferredJobs` ≥ 1 and `current: false` with a new `staleReason` wording, and is not selected by `staleOnly`; a rebuild refused memory waits for room instead of being retried on timers. No field added or removed. **WorkloadCore S17:** `GET /api/server/memory` loses `resourceMode`, `headroomRatio`, `resourceModeTransitions` and the `headroom` block (the resource mode is deleted); a memory refusal's `Retry-After` is the queue's estimate, or 10 s, never a constant 1 s. **Release blockers:** every endpoint answers a capacity refusal `503` + `Retry-After` (`MEMORY_BUDGET_EXCEEDED` / `WAL_CAPACITY_EXCEEDED`) and a write conflict `409 WRITE_CONFLICT` — some answered `400`, `409` or `500` before (BL-921, BL-881); the result ceiling is `400 RESULT_TOO_LARGE` with no `Retry-After` (it was `503`); a token refresh refused for capacity is `503` and keeps its token, and of two concurrent refreshes with one token exactly one succeeds (BL-841); a materialized-query create whose first build is refused for capacity answers `204` with the query behind (BL-884); bulk-load `:append` is refused `503` before it decodes when memory is short (BL-831). No field added or removed. |
| 2.11 | 0.4.0 (LoadSpeed) | **LoadSpeed M.2:** bulk-load `:commit`'s `mqWaitMs` defaults to `0` (it was `30000`) — a commit with queries answers `mqStatus: "behind"` at once unless the request asks to wait. No field added or removed. **LoadSpeed K31 (breaking):** `postLoadMqBehavior: "deferred"` is refused `400 BULK_LOAD_INVALID_OPTIONS` (use `"auto"`); `mqStatus` and `mqRebuildStatus` lose `"deferred"`. **LoadSpeed K5 (BL-980, BL-944; breaking):** `GET /api/tables` drops `rowCountIsExact` (`rowCount` is always exact) and always carries `createdAt` / `lastModifiedAt`; an aggregate materialized query whose `groupByColumns` are plain strings is `400`; an application database accepts only its URL issuer on access tokens; a point-in-time restore of a backup without a WAL-root incarnation fails at staging. Refusals: a refusal no other code names is `503 SERVICE_UNAVAILABLE` + `Retry-After`, `SERVER_STARTING` carries `Retry-After: 5`, a refused notification-provider `DELETE` is `503`, and a wrapped refusal on `POST …/materialized-queries/{name}/query` is `503` (or `400 RESULT_TOO_LARGE`), not `400 INVALID_REQUEST`. **LoadSpeed S13 (breaking):** `Decimal(p,s)` is the only decimal type — `"type": "Decimal"` without `precision` / `scale` is `400`, as is a precision above 18; a computed output's `type` and `cast`'s target spell it `"Decimal(p,s)"`; the column-batch frame's 128-bit `Decimal` kind (6) is deleted and refused `400`, and query results send a decimal column as `ScaledDecimal` at its declared scale; a decimal `sum` past 18 digits is refused in a query as in a materialized query. |
| 2.12 | 0.5.0 (Horizon) | **Horizon (additive on the wire):** materialized-query create takes `window` (`{ keep, column? }`) and the status reports `window` and `horizon`; `stats.windowCompletionRows` on `/query` and the MQ query endpoint; table create and `PUT …/policy` take `policy.retention` (`{ keep }`; a retention-only `PUT` needs no `storageTemperature`; it cannot be removed — an omitted or `null` `retention` leaves it as it is), and the policy detail and table detail report `retention` and `horizon`; insert, named-mutation insert / upsert and bulk-load `:commit` responses carry `expiredRows` (omitted when 0); a `DELETE …/rows` whose whole `where` is the first cluster column `lt` / `lte` a time runs as an early expiry (with retention) or a range delete (without); `snapshot_complete` gains `horizon` / `horizon_column` / `horizon_column_type`, and two server messages are added, `horizon` and `range_delete` (each with `column_type` on a `Date` column). A windowed result's subscription snapshot is its stored part. |
| 2.13 | 0.6.0 (Lead) | **Lead S09 (breaking on the wire):** the column-batch frame is `ACB2` (`application/vnd.aouda.column-batch-v2`, `:begin`'s `"column-batch-v2"`): every frame carries a kind and a sequence number, and every body ends with one end frame. A frame query response's row count, `stats`, `totalMatches` and `warnings` move from the `X-Aouda-Row-Count` / `-Stats` / `-Total-Matches` / `-Warnings` headers into the end frame, and an error after the response started is an error end frame rather than a cut connection. `ACB1` bodies and the old media type are refused `415 FRAME_VERSION_UNSUPPORTED`; a query asking only for the old type gets JSON. |
| 2.14 | 0.6.0 (Lead) | **Lead S12 (breaking on the wire): the REST API as column arrays.** Every JSON write body sends its rows as [column arrays](#column-arrays-the-write-body) — `columns`, `data` (one array per column), optional `absent` (per column, the rows whose cell is not given, which is not null) — on `POST …/tables/{name}/rows`, a branch insert, WebSocket `stream_rows`, a named mutation's `batchParam` argument and the schema seed / `aouda.seed.json`; a body with `rows` (row objects) is refused `400 ROW_OBJECTS_UNSUPPORTED` (new code). Bulk-load `:append` takes frames or one JSON column-array body; NDJSON is refused `415 ROW_OBJECTS_UNSUPPORTED`, `:begin`'s `acceptedAppendFormats` is `["column-batch-v2", "column-arrays"]`, and an unroutable multi-table row is named "Row {n} of this :append" with `details: row={n}`. Reads: the `format` query parameter is removed from `/query` and the named-query execute and batch routes (any `format=` is `400 INVALID_FORMAT`; results are always `{columns, types, data, rowCount, …}`); the materialized-query `POST …/{name}/query` answers `{columns, data, rowCount, stats, token}`; `generatedValues` is `{columns, data}` with one cell per request row; a WebSocket `snapshot` page is `{type, id, columns, data, version, token?}` (`snapshot_complete` and `change` unchanged); vector `:nearest` answers `{rowKeys, distances, executionMs, token}` and graph `:khop` `{nodeIds, hops, executionMs}`; the policy inspector's table and materialized-query `sample` is `{columns, data}`. **Pass-10 (documentation only):** the [graph and vector endpoints](#graph-and-vector-endpoints) are documented. |
| 2.15 | 0.9.0 (ArrayColumns, BL-035) | **ArrayColumns (BL-035, 0.9.0; additive on the wire):** six [array column](../guides/array-columns.md) types in schema and on every surface — `Double[]`, `Float32[]`, `Int32[]`, `Int64[]`, `Byte[]`, `String[]` (JSON: an array, a base64 string for `Byte[]`; `types` and `X-Aouda-Column-Types` name them); one new error code, `ARRAY_COLUMN_UNSUPPORTED` (400), for an array column used where it cannot be; a new frame column kind, **9 `Array`** (an older client reading it fails with its *"unknown kind 9"* error; a query response with an array column is a frame when the client accepts frames; an older TypeScript client reading arrays from JSON — subscriptions, the materialized query endpoint, `returning` — does not fail, and gives plain arrays, a `Byte[]` as base64 text and `Int64[]` elements past 2^53 rounded); `column_types` on subscription `snapshot` and `change` messages and `columnTypes` on the materialized query endpoint's body; the generator route is `GET /api/databases/{db}/schema/typescript`. A server binary from before this train that opens a data directory holding an array column refuses it by the type's number (*"has type 514, which this build does not define"*). `X-Aouda-Protocol-Version` stays `2`. |
| 2.16 | 0.9.0 (Grants) | Not produced (**BL-1464, 0.16.0**). See [the auth error envelope](#auth-error-envelope). |
| 2.17 | 0.9.0 (Hardening, BL-418) | **Embargo (additive on the wire):** role permissions take `resourceType` `embargo` (`resourceName` one table with a row time, `actions` whole seconds 1–2678400). A holder's reads see only rows whose row time is at least that old at the server's clock; its table subscriptions deliver each change when it comes of age; writes, materialized queries, graph traversal and vector search on the table are refused `403 AUTH_EMBARGO_UNSUPPORTED` (new code). A branch query of a base table applies the cutoff; a branch query of a materialized result over an embargoed source is refused the same way (**BL-1161, BL-1298, 0.9.0**). An embargoed subscription can end with the new WebSocket error `SUBSCRIPTION_EMBARGO_RESET`. `GET …/users/{id}/`whoami`` gains `embargoes`. New setting `Aouda:Streaming:EmbargoHoldMaxEvents`. `X-Aouda-Protocol-Version` stays `2`. |
| 2.18 | 0.9.0 (Hardening, BL-1018) | **Token allowance (breaking on the wire):** an application access token's `iss` is its auth database's URL on every linked database, and `aud` is an array — the [allowance](#the-token-allowance), the databases the token may open (it was the auth database's name). Sign-in and password reset give the databases on which the user holds a role (none: `403`); their new optional `databases` field, and native `authorize`'s, narrows it (`400 INVALID_REQUEST` for anything but a non-empty subset). A token, refresh or native code used outside its allowance is `401 AUTH_DATABASE_NOT_IN_ALLOWANCE` (new code). The OIDC discovery document at a linked database names the auth database's issuer. Server-auth tokens are unchanged. `X-Aouda-Protocol-Version` stays `2`. |
| 2.19 | 0.14.0 (ADR 0072) | **Formulas (additive on the wire):** the column type `Expression` with `drives` (create table, add column, the column listing, `…/schema`, schema documents); a formula is the column's value, a JSON object in JSON rows (the canonical text in column-batch frames); the `cellRef` expression node (valid only in a formula, with its shorthands) and thirteen new functions; [`POST …/tables/{table}/explain`](#explain-a-formula-cell); a token read of a table with an `Expression` column judged by the formula maintainer's progress; new codes `FORMULA_COLUMN_INVALID`, `FORMULA_INVALID`, `FORMULA_REFERENCE_INVALID`, `FORMULA_REFERENCE_NOT_PRIMARY_KEY`, `FORMULA_CYCLE`, `FORMULA_DEPTH_EXCEEDED`, `FORMULA_LIMIT_EXCEEDED` (400), `FORMULA_REFERENCE_NOT_READABLE` (403), `FORMULA_VALUE_WRITE_REFUSED`, `FORMULA_TABLE_REFERENCED` (409), `FORMULA_TOKEN_REQUIRES_PRIMARY` (421), `FORMULA_NOT_MAINTAINED` (503), `EXPR_CELLREF_NOT_ALLOWED`, `EXPR_CELLREF_INVALID`. `X-Aouda-Protocol-Version` stays `2`. A server of an earlier train refuses the `Expression` type and has no `explain` route (`404`). |

