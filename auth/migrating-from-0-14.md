---
title: "Moving from 0.14"
nav_order: 12
parent: "Auth and Authorization"
---

# Moving from 0.14 to the principals release (**BL-1464, 0.16.0**)

0.14 is the last release of the old access model. This release refuses that model. It does not read it and it does not convert it. Export what you can with the 0.14 build, wipe the data directory, start this build, and declare principals.

The names below appear on this page because they are what a 0.14 configuration contains. No other page teaches them.

## What breaks, in one list

Each row is the exact thing the old input now gets.

| Old input | What this build does |
|---|---|
| A format-18 data directory | Refused at start. The line is `DATA_DIRECTORY_FORMAT_REFUSED: found=18 expected=19 path=<catalog root file>`. |
| Any key whose text starts with `mk_` | `401 AUTH_KEY_MALFORMED`, remedy `fix-key`, `reason: retired-format`. The message is: `This key is in the retired mk_ format. Create a key in the current format (aouda keys new, or a stored key on a principal) or ask an administrator for one.` No lookup. |
| A non-empty `X-User-Token` header, a realtime `user_token`, or a long-poll `userToken` | `400 INVALID_REQUEST`. The message is: `X-User-Token is no longer supported. Send the user's own token as the credential, or mint a limited key (POST /api/auth/keys).` The value is not read. |
| `Aouda:Auth:Keys:File` (the identities file, often `aouda.identities.json`) | `SETTING_REMOVED` at plan and start, naming principals in `aouda.json` as the replacement. The value is never read. |
| `Aouda:Auth:Bootstrap:ServerKey` and `ServerKeyFile` | `SETTING_REMOVED`, naming a `server.principals` entry. |
| `Aouda:Auth:RootUser:Email` and `Password` | `SETTING_REMOVED`, naming a `server.principals` entry with a password seed. |
| `allowSelfSignup`, `selfSignupRole` on a create or link body | `400 INVALID_REQUEST`, naming `PUT /api/auth/{authDatabase}/signup`. |
| A schema file or table body carrying `partitionLevelSecurity`, `authMode`, `plsClaimBinding`, `permissionDimension`, `permissionColumn`, `rlsResolverName` | `400 SCHEMA_UNKNOWN_MEMBER`, naming the member. A table carries no security. |
| `dataPlaneAccess` on a table or a materialized query | `400 SCHEMA_UNKNOWN_MEMBER`. Reach is a statement on `anonymous`. |
| `aouda create-admin` | Unknown command, exit 64. The first operator is `aouda init`, setup mode, the declaration, or `--dev-admin`. |
| `aouda policy inspect`, `POST …/policy/inspect` | Unknown command, exit 64. The route is `404`. The replacement is `aouda policy explain`. |
| `GET …/auth/me`, `GET …/access-grants`, `GET …/configured-keys` | `404`. The replacement is `GET /api/auth/whoami`. |
| SDK options `appAuth`, `serverAuth`, `authAdmin`, `userToken` | Refused at construction, naming the one credential option. |
| Error codes `AUTH_TOKEN_MISSING`, `AUTH_TOKEN_INVALID`, `AUTH_TOKEN_EXPIRED`, `AUTH_TOKEN_REVOKED`, `AUTH_API_KEY_INVALID`, `AUTHORIZATION_DENIED`, `INSUFFICIENT_PERMISSIONS` | Not produced. The codes of this release are [whoami](whoami.md#remedy). |

## The inventory

54 concepts in 0.14. After this release a reader meets 18, listed on [Access](index.md#the-18-concepts). Of the 54: 21 deleted, 24 become one of the 18, 8 kept, 1 left to BL-1462 (`RequireFirstAdmin`, already removed from the server by that work). Rows 30–48 and 51 were completed by the schema cut: the fate below is the fate that shipped, which matches the decision.

| # | Concept in 0.14 | Fate | Replacement |
|---|---|---|---|
| 1 | `mk_anon_` | **Deleted** | the `anonymous` principal. [principals.md](principals.md#anonymous) |
| 2 | `mk_pub_` | **Deleted** | `anonymous`'s statements. [principals.md](principals.md#anonymous) |
| 3 | `mk_svc_` / `service_role` | **Becomes** | a principal with the statements it needs, and a key. [credentials.md](credentials.md#stored-keys) |
| 4 | `mk_srv_` / `server_admin` | **Becomes** | a `_serverauth` principal with role `admin`. [principals.md](principals.md#roles) |
| 5 | `mk_adm_` | **Becomes** | a principal with `manage` on principals and roles. [authorization.md](authorization.md#actions) |
| 6 | `mk_scp_` / `scoped_service` | **Becomes** | a principal with roles. [principals.md](principals.md#roles) |
| 7 | a custom `mk_` key | **Becomes** | a stored key on a principal. [credentials.md](credentials.md#stored-keys) |
| 8 | key prefixes as a type, `KeyKindHints` | **Deleted** | one format, `whoami`, `remedy`. [credentials.md](credentials.md#key-format) |
| 9 | `regenerate-keys`, keys minted at link time | **Deleted** | mint a new key, then delete the old one. [credentials.md](credentials.md#stored-keys) |
| 10 | a supplied-key shape rule | **Becomes** | the one key format. [credentials.md](credentials.md#key-format) |
| 11 | `Aouda:Auth:Keys:File`, `aouda.identities.json` | **Becomes** | principals in `aouda.json`. [migrating-from-0-14.md](migrating-from-0-14.md#step-by-step) |
| 12 | `Bootstrap:ServerKey`, `ServerKeyFile` | **Deleted** | a declared `_serverauth` principal. [../getting-started/auth.md](../getting-started/auth.md) |
| 13 | `GET configured-keys`, key `source` | **Becomes** | principal `source`. [principals.md](principals.md#declared-and-runtime) |
| 14 | the six mint routes | **Becomes** | `POST …/principals/{name}/keys` and `POST /api/auth/keys`. [credentials.md](credentials.md#stored-keys) |
| 15 | `X-User-Token`, `user_token`, `userToken` | **Deleted** | the caller's own credential, or a limited key. [credentials.md](credentials.md#limited-keys) |
| 16 | a service-level key class | **Deleted** | the `set-identity` action; quotas per principal. [authorization.md](authorization.md#actions) |
| 17 | per-prefix listener rules | **Deleted** | no credential on the admin listener is `401`. [index.md](index.md#the-two-listeners) |
| 18 | server users | **Becomes** | `_serverauth` principals. [principals.md](principals.md#principals) |
| 19 | application users | **Becomes** | principals (`runtime` or `signup`). [principals.md](principals.md#principals) |
| 20 | auth database kinds and the link | **Kept** | governance by that link; no two-step fallback. [principals.md](principals.md#auth-databases) |
| 21 | setup mode | **Kept** | only while no principal holds `manage` on `server`. [principals.md](principals.md#setup-mode) |
| 22 | `Aouda:Auth:RootUser` | **Deleted** | a declared principal with a password seed. [../getting-started/auth.md](../getting-started/auth.md) |
| 23 | `DevAdmin` | **Kept** | prints `key=` in the current format. [../getting-started/auth.md](../getting-started/auth.md) |
| 24 | `RequireFirstAdmin` | **Left** | left to BL-1462; the setting is already gone. [principals.md](principals.md#setup-mode) |
| 25 | `aouda create-admin` | **Deleted** | `aouda init`, the declaration, or `--dev-admin`. [../reference/cli.md](../reference/cli.md) |
| 26 | `allowSelfSignup`, `selfSignupRole` | **Becomes** | `signup`, default nothing. [principals.md](principals.md#signup) |
| 27 | custom claims | **Becomes** | attributes. [principals.md](principals.md#attributes) |
| 28 | the sign-in allowance | **Becomes** | a session's `databases` limit; omitted means no limit. [credentials.md](credentials.md#sessions) |
| 29 | sessions, refresh, MFA, password reset | **Kept** | the same routes. [setup.md](setup.md) |
| 30 | custom roles | **Kept** | named bundles of statements. [principals.md](principals.md#roles) |
| 31 | `db_admin`, `db_operator`, `db_writer`, `db_reader`, `public`, `anonymous`, `auth_admin` | **Becomes** | three read-only roles: `admin`, `writer`, `reader`. [principals.md](principals.md#roles) |
| 32 | a role assignment's scope | **Deleted** | the resource path says where. [authorization.md](authorization.md#resources) |
| 33 | `db_roles` and `permissions` claims | **Deleted** | a session carries identity only. [reference.md](reference.md#what-a-session-token-carries) |
| 34 | seven table actions | **Becomes** | six actions. [authorization.md](authorization.md#actions) |
| 35 | `all-partitions` | **Deleted** | a statement with no `where`. [authorization.md](authorization.md#row-conditions) |
| 36 | `all-rows` | **Deleted** | a statement with no `where`. [authorization.md](authorization.md#row-conditions) |
| 37 | grant levels `read` / `write` / `admin` | **Deleted** | actions. [authorization.md](authorization.md#actions) |
| 38 | implied grants | **Deleted** | nothing is implied. [index.md](index.md) |
| 39 | an `embargo` grant | **Becomes** | `embargoSeconds` on a `read` or `execute`. [authorization.md](authorization.md#embargo) |
| 40 | `execute` on a named artifact | **Kept** | the `execute` action. [authorization.md](authorization.md#execute) |
| 41 | entitlements | **Becomes** | attributes plus `where`. [principals.md](principals.md#attributes) |
| 42 | `partitionLevelSecurity`, `authMode` `jwt-claim`, `plsClaimBinding` | **Deleted** | a `where` on an attribute or `principal.id`. [authorization.md](authorization.md#row-conditions) |
| 43 | `authMode` `auth-db-entitlement`, `permissionDimension`, `permissionColumn` | **Deleted** | `where` … `in` `attributes.<x>`. [authorization.md](authorization.md#row-conditions) |
| 44 | `authMode` `auth-db-rls` and resolvers | **Deleted** | a `where` per statement. [authorization.md](authorization.md#row-conditions) |
| 45 | a resolver pass-through | **Deleted** | an unconditional statement on that role. [authorization.md](authorization.md#statements) |
| 46 | a privileged-admin gate | **Becomes** | grant only what you hold. [authorization.md](authorization.md#grant-only-what-you-hold) |
| 47 | a whole-table write gate; the DDL gate is deleted | **Becomes** | an unconditional statement, and a table carries no security for DDL to change. [authorization.md](authorization.md#audit) |
| 48 | `dataPlaneAccess` | **Deleted** | a statement on `anonymous`. [principals.md](principals.md#anonymous) |
| 49 | `crossPartitionAccess` | **Kept** | still a cost waiver, not security. [authorization.md](authorization.md#actions) |
| 50 | `GET …/auth/me`, `access-grants` | **Becomes** | `GET /api/auth/whoami`. [whoami.md](whoami.md#whoami) |
| 51 | `policy inspect`, `policy/inspect`, the test-identities file | **Becomes** | `aouda policy explain`. [../reference/cli.md](../reference/cli.md) |
| 52 | declared roles under `Aouda:Databases` | **Becomes** | `roles` in `aouda.json`. [../guides/declared-access.md](../guides/declared-access.md) |
| 53 | `_permission_version` | **Kept** | unchanged; a policy change still re-keys. [whoami.md](whoami.md#whoami) |
| 54 | `access_grant_used` | **Becomes** | `unconditional_access`. [authorization.md](authorization.md#audit) |

## Step by step

1. On the **0.14** build, export the rows you need and note every key's purpose (which database, which job). This build will not read those keys.
2. Stop the server. Move the data directory aside. A format-18 directory is refused, not migrated.
3. Write `aouda.json` (below). Put the key root in the environment, not in the file.
4. `aouda plan --declaration aouda.json --skip-secrets` while the secrets are absent, then again without `--skip-secrets` on the host that has them.
5. `aouda keys new-root` on that host, and `aouda keys derive auth/<name>` for each derived principal. `aouda keys new` for a stored key, once; put only `id` and `sha256` in the file.
6. `aouda start --declaration aouda.json`.
7. `aouda whoami` with the operator's credential. `aouda policy explain` for a feeder write.

### The worked example

Thirteen databases (one auth database, eleven data databases linked to it, one unlinked `lab`), eleven schema files, four roles, twenty principals plus `anonymous`, two secret references (`AOUDA_KEY_ROOT` and `AOUDA_OPS_PASSWORD`). The stored-key `sha256` is sixty-four `a` characters, a placeholder, not a hash of a key you can send.

<!-- declaration-example -->
```json
{
 "version": 1,
 "keyRoot": {
 "env": "AOUDA_KEY_ROOT"
 },
 "server": {
 "principals": {
 "ops@example.com": {
 "roles": [
 "admin"
 ],
 "credentials": {
 "password": {
 "env": "AOUDA_OPS_PASSWORD"
 }
 }
 }
 }
 },
 "databases": {
 "auth": {
 "kind": "auth",
 "signup": {
 "enabled": false,
 "roles":,
 "statements":
 },
 "roles": {
 "rates-feeder": {
 "statements": [
 {
 "actions": [
 "write"
 ],
 "resources": [
 "rates/table/DepositQuote"
 ],
 "where": {
 "column": "source",
 "op": "in",
 "value": [
 "tullett"
 ]
 }
 }
 ]
 },
 "browser": {
 "statements": [
 {
 "actions": [
 "execute"
 ],
 "resources": [
 "market/query/latest"
 ]
 }
 ]
 },
 "ops-read": {
 "statements": [
 {
 "actions": [
 "read"
 ],
 "resources": [
 "*/table/*"
 ]
 }
 ]
 },
 "credit-writer": {
 "statements": [
 {
 "actions": [
 "write"
 ],
 "resources": [
 "credit/table/Limit"
 ],
 "where": {
 "column": "book",
 "op": "eq",
 "value": "flow"
 }
 }
 ]
 }
 },
 "principals": {
 "anonymous": {
 "statements": [
 {
 "actions": [
 "execute"
 ],
 "resources": [
 "market/query/latest"
 ]
 }
 ]
 },
 "rates-feeder": {
 "roles": [
 "rates-feeder"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "orders-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "positions-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "refdata-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "limits-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "calendar-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "fx-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "credit-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "research-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "market-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "audit-feeder": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "browser-backend": {
 "roles": [
 "writer"
 ],
 "credentials": {
 "keys": [
 {
 "id": "aouda_exampleexampleex",
 "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
 }
 ]
 }
 },
 "shop-backend": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "ops-reader": {
 "roles": [
 "ops-read"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "credit-writer-job": {
 "roles": [
 "credit-writer"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "nightly": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "reconciler": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "publisher": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "archive": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 },
 "support": {
 "roles": [
 "reader"
 ],
 "credentials": {
 "derivedKey": {
 "version": 1
 }
 }
 }
 }
 },
 "rates": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/rates.aouda.schema.json"
 },
 "orders": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/orders.aouda.schema.json"
 },
 "positions": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/positions.aouda.schema.json"
 },
 "refdata": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/refdata.aouda.schema.json"
 },
 "limits": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/limits.aouda.schema.json"
 },
 "calendar": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/calendar.aouda.schema.json"
 },
 "fx": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/fx.aouda.schema.json"
 },
 "credit": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/credit.aouda.schema.json"
 },
 "research": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/research.aouda.schema.json"
 },
 "auditlog": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/auditlog.aouda.schema.json"
 },
 "market": {
 "kind": "data",
 "authDatabase": "auth",
 "schema": "schema/market.aouda.schema.json"
 },
 "lab": {
 "kind": "data"
 }
 }
}
```

```text
aouda keys new-root --root-file key-root.txt
aouda keys derive auth/rates-feeder --declaration aouda.json --root-file key-root.txt --key-file rates-feeder.key
aouda plan --declaration aouda.json
aouda start --declaration aouda.json
aouda whoami --server http://127.0.0.1:5000 --json
aouda policy explain --declaration aouda.json --as auth/rates-feeder --action write --resource rates/table/DepositQuote --row "{ \"source\": \"other\" }"
```

The explain exits `2`. The answer is `403` worth of policy: `row.admitted` is false, and a live write of that row is `403 AUTH_ROW_DENIED`.

## By who is reading

**An application developer.** One credential option: a key or a session. Delete `appAuth`, `serverAuth`, `userToken`. Call `whoami`. Read `remedy` on a refusal. A browser deletes its key.

**An operator.** Settings that named a file or a root password become entries in `aouda.json`. `aouda plan` is the check the start will run. `aouda reload` applies a file change that is not a listener or a memory change.

**A browser app.** Delete the key. Call the data-plane listener with no credential. Give `anonymous` the `execute` statements the page needs.

**An agent.** `aouda start --dev-admin`, read `key=` from the one stdout line, `aouda whoami`, then `aouda policy explain` against the declaration. Do not invent a 0.14 key.

## What did not change

Sign-up, sign-in, refresh, sign-out, password reset and MFA use the same routes. `crossPartitionAccess` is still only a cost waiver. The data-plane listener still serves named artifacts, auth routes and the realtime socket, and still answers `404` for ad-hoc query. Probes, backups and the schema file's non-security members are unchanged. A session token is still a JWT; it carries less (see [the claims](reference.md#what-a-session-token-carries)).
