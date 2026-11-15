---
title: "Upgrading and the data-directory format"
nav_order: 2.8
parent: "Guides"
---

# Upgrading and the data-directory format

Aouda is 0.x and keeps **no backward compatibility** between releases. A data directory carries one **catalog format version**; a build that
reads another version refuses the **whole directory** at start, older and newer alike, and there is no migration. This page lists every format
bump and the exact line a build prints when it meets the previous one, so a deploy script or an operator can recognise it. Source: the Aouda
repository's `docs/dev/Upgrade-Notes.md`.

To keep the data across a bump: **export it with the build that wrote it, delete the data directory, start the new build fresh, load the export.**

Status: the refusal code described here is shipped in **0.12.0** (**BL-1420**). The format version is **17** in 0.11.0 and 0.12.0, so a 0.11.0
directory starts on 0.12.0 unchanged. Server **0.13.0** writes format **18** (**BL-1418, 0.13.0**) and refuses a 17 directory: see [Upgrading to entitlements](#upgrading-to-entitlements-bl-1418-0130). Server **0.14.0** does **not** bump the format (it stays **18**): a 0.13.x data directory starts on 0.14.0, but the declaration and the probes changed, see [Upgrading from 0.13 to 0.14](#upgrading-from-013-to-014-0140).

## Detecting a refusal: `DATA_DIRECTORY_FORMAT_REFUSED`

When the catalog root declares another format version, the refusal starts with a fixed first line, then the prose:

```text
DATA_DIRECTORY_FORMAT_REFUSED: found=<n> expected=<m> path=<catalog root file>
<path>: catalog root declares format version <n>; this build reads format version <m> only. ...
```

- `found` is the version the directory declares, `expected` the version this build reads, `path` the catalog root that declared it (it runs to
  the end of the line).
- The server also logs the whole message at **critical** level before the start fails, so the code is the first token of that log line, and the
  exception that stops the host starts with the same line.
- (**BL-1461, BL-1463, 0.14.0**) `aouda start` exits with status **78** (`EX_CONFIG`), the status of a start refused for its
  configuration ([exit statuses](../deployment/linux.md#when-the-start-is-refused)), and prints the refusal as a finding on standard error
  (`error    DATA_DIRECTORY_FORMAT_REFUSED`, then the line above); the systemd unit does not restart it. Until then there was no distinct
  exit status (the process aborted), so match the code in the output with 0.13.0 and earlier. `aouda doctor` and `aouda status` never
  load the catalog and do not report it.
- A shard or journal that disagrees with its root, a root that is not JSON, and a format-1 flat catalog are different refusals (corruption or a
  very old directory) and carry **no code**.
- Builds released before the code existed (0.11.0 and earlier) print the prose only; its first sentence is `<path>: catalog root declares format
  version <n-1>; this build reads format version <n> only.`, with the same version numbers.

For a directory written by 0.9.x or 0.10.0 and opened by 0.11.0 or later, the first line is:

```text
DATA_DIRECTORY_FORMAT_REFUSED: found=16 expected=17 path=<data>/Databases/<db>/catalog/catalog.json
```

## The bumps

The last column is the first line a server that **reads that version and carries the code** prints when it meets the previous version.

| Format | First written by | What changed | First line for the previous version |
|---|---|---|---|
| 6 | 0.3.0 | every other version refused at open, a clean cut | `DATA_DIRECTORY_FORMAT_REFUSED: found=5 expected=6 path=<root file>` |
| 7 | 0.4.0 | auth tables 0.3.0 lacks | `DATA_DIRECTORY_FORMAT_REFUSED: found=6 expected=7 path=<root file>` |
| 8 | development builds only | windowed result's persisted horizon | `found=7 expected=8` |
| 9 | development builds only | `TableEntry.RowIdFloor` | `found=8 expected=9` |
| 10 | 0.5.0 | `TablePolicy.Retention` | `found=9 expected=10` |
| 11 | development builds only | bulk load commit record (journal kind 8) | `found=10 expected=11` |
| 12 | development builds only | per-table `durability` level | `found=11 expected=12` |
| 13 | 0.6.0 and 0.7.x | bulk load commit header names its level; settle record (journal kind 9) | `found=12 expected=13` |
| 14 | 0.8.0 | one encoding for a partition key | `found=13 expected=14` |
| 15 | development builds only | allowance on `_refresh_tokens` and `_authorization_codes` | `found=14 expected=15` |
| 16 | 0.9.x and 0.10.0 | bulk-load commit header carries the beginning principal | `found=15 expected=16` |
| 17 | 0.11.0 (and 0.12.0) | `source` on `_api_keys` and the per-user permission table | `DATA_DIRECTORY_FORMAT_REFUSED: found=16 expected=17 path=<root file>` |
| 18 | 0.13.0 (**BL-1418**) | the per-user permission table is `_user_entitlements` (`entitlement_key`, `level`); RLS resolver value source `Entitlement` | `DATA_DIRECTORY_FORMAT_REFUSED: found=17 expected=18 path=<root file>` |

In the shortened rows the line is the same as in the first two, with `path=<root file>`. Formats 1 to 5 (0.2.x and earlier) are not listed: a build
with the code refuses a root declaring 2 to 5 under the same line with that `found`, and the format-1 flat catalog and an interrupted format-1
migration marker are refused by name without a code. Formats 8, 9, 11, 12 and 15 were only ever written by development builds.

## Upgrading to entitlements (**BL-1418, 0.13.0**)

Server 0.13.0 renames the per-user permission rows `(user, dimension, key, level)` that an `auth-db-entitlement` table checks. This is a clean cut
(pre-1.0): **no alias, no migration, no reader of the old shapes.** One wipe, then edit your schema files, scripts and clients.

**What an old data directory gets.** Format 17 (written by 0.11.0 and 0.12.0) is refused whole, every database in the directory, with the first line

```text
DATA_DIRECTORY_FORMAT_REFUSED: found=17 expected=18 path=<catalog root file>
```

Export what you need with the build that wrote it, delete the data directory, start the new build, load the export, and create the entitlements again.
A replica refuses a primary of the other format the same way.

| What | Before | Now | What the old form gets |
|---|---|---|---|
| Table `authMode` | `auth-db-pls` | `auth-db-entitlement` (`jwt-claim` and `auth-db-rls` unchanged) | `400 Invalid authMode. Valid values: jwt-claim, auth-db-entitlement, auth-db-rls.`; a schema file fails `aouda plan`, `schema apply` and a declared-schema start with `Unsupported authMode 'auth-db-pls'. Valid values: jwt-claim, auth-db-entitlement, auth-db-rls.` |
| Create | `POST /api/databases/{db}/auth/admin/users/{id}/partition-grants` | `POST …/users/{id}/entitlements` | `404` |
| List | `GET …/partition-grants[?dimension=]` returning `{ "grants": [...] }` | `GET …/entitlements[?dimension=]` returning `{ "entitlements": [...] }` | `404`; a client reading `grants` from the new route finds nothing |
| Delete | `DELETE …/partition-grants/{grantId}` | `DELETE …/entitlements/{entitlementId}` | `404` |
| Body and item fields | `partitionKey`, `accessLevel` | `key`, `level` (`dimension`, `grantedBy`, `validFrom`, `validTo`, `id`, `userId`, `createdAt` unchanged) | the old names are not read: `key` missing is `400 AUTH_GRANT_INVALID` |
| Error codes | `AUTH_PLS_GRANT_NOT_FOUND`, `AUTH_PLS_GRANT_INSUFFICIENT_ACCESS` | `AUTH_ENTITLEMENT_NOT_FOUND`, `AUTH_ENTITLEMENT_INSUFFICIENT_ACCESS` (both `403`) | code that matches the old strings never fires. The `AUTH_PLS_TENANT_*`, `AUTH_PLS_WRITE_SCOPE_VIOLATION`, `AUTH_PLS_UNSUPPORTED_OR_SHAPE` and `AUTH_GRANT_*` codes are unchanged |
| RLS resolver rule `valueSource` | `PartitionGrant` | `Entitlement` (`UserId`, `Literal`, `Claim` unchanged) | not a known source: an unknown source denies every row (fail closed) |
| `policy inspect` test identity, and the identity fixture file | `grants[]` of `{ dimension, partitionKey, accessLevel }` | `entitlements[]` of `{ dimension, key, level }` | an old `grants` member is not read: the identity holds no entitlements and an entitlement table denies it |
| Auth database storage | table `_user_partition_grants`, columns `partition_key`, `access_level` | table `_user_entitlements`, columns `entitlement_key`, `level` | refused by the format check above |
| `@aouda/client` | `createPartitionGrant`, `listPartitionGrants`, `deletePartitionGrant`, `CreatePartitionGrantRequest`, `PartitionGrant`, `PartitionGrantsListResponse`, `authMode: 'auth-db-pls'` | `createEntitlement`, `listEntitlements`, `deleteEntitlement`, `CreateEntitlementRequest`, `Entitlement`, `EntitlementsListResponse`, `authMode: 'auth-db-entitlement'` (with the next `@aouda/client` release) | a client built against the old names fails loudly: `404` on the route, `400` on the mode |
| `Aouda.Client` (.NET) | no typed wrapper | no typed wrapper (the public API names nothing from this list) | none |

**Unchanged on purpose:** the role permission types `all-partitions` and `all-rows`, `permissionDimension`, `permissionColumn`, `partitionLevelSecurity`,
`plsClaimBinding`, jwt-claim PLS and its `AUTH_PLS_TENANT_*` codes, a table's own `partitionKey` (storage), the `access-grants` endpoints and `Aouda:Adra:GrantCaps`.
Roles live in the auth database, so after the wipe declare them again as before.

## Upgrading from 0.13 to 0.14 (**0.14.0**)

No data-directory format change (the format stays **18**), so no export and no wipe. The breaking items are in what a start accepts, what it answers while it starts, and
the commands and codes around it. Each row says what the old form gets now. Source: the server changelog, section 0.14.0.

**Read this first if you deploy with a health check.** (**BL-1462**) **`GET /health` answers `200` to every caller in every state**, setup mode included. In 0.13.x it answered
`503 SETUP_REQUIRED` to a caller off the server's host while the server was in setup mode, so a deploy script or an orchestrator that waited for `/health` to turn `200`
**now passes at once**, before the start has finished. The probes now mean one thing each:

| Probe | 0.13.x | 0.14.0 | Use it for |
|---|---|---|---|
| `GET /health` | `200`, but `503 SETUP_REQUIRED` off the host in setup mode | `200` to every caller in every state | the process is alive (a liveness probe) |
| `GET /startup` | `503` for as long as setup mode lasted (the Helm chart's startupProbe restarted the pod every five minutes) | `503` while the start sequence runs (databases, auth, declared schema files, roles, grants, keys, replication), `200` once all of it has run, setup mode included | the start has finished |
| `GET /ready` | `503 setup_required` in setup mode, else the component checks | unchanged meaning; new reasons `schema_applying` (with `progress: { "done": 4, "total": 11 }`), `not_initialized`, `server_starting`, `root_user_unusable` | the server can serve application traffic |

**Change a deploy gate that waited on `/health` to wait on `/ready`** (and a Docker `HEALTHCHECK` or a compose `depends_on: condition: service_healthy` already does: the image's
healthcheck is `/ready`). Full table: [HTTP API: the probes](../reference/http-api.md#the-probes-one-meaning-each), [Docker](../deployment/docker.md#health-checks).

| Area | 0.13.x | 0.14.0 | What the old form gets |
|---|---|---|---|
| Overlay file name (**BL-1460**) | `aouda.schema.<env>.json` for every file in one directory | `<file without .json>.<env>.json` beside the file: `aouda.schema.json` + `prod` reads `aouda.schema.prod.json`; `rates.aouda.schema.json` + `prod` reads `rates.aouda.schema.prod.json` | the old name is not read: with several schema files in one directory each now needs its own overlay. An overlay that exists but cannot be read, or is empty, fails the start naming the file (it was skipped) |
| Strict members (**BL-1460**) | an unknown member in a schema file, an overlay or a `schema/apply` / `schema/diff` body was dropped; names were read without case | refused with `400 SCHEMA_UNKNOWN_MEMBER`, every one named with its JSON pointer and the member meant; member names are case-sensitive; an `aouda plan` reports it as an error and the start fails | a file that "worked" because a slip was dropped now fails. Also refused in 0.14.0: a table's `description` (**accepted again from the next train**: documentation in the file only, see below), and on a materialized query **four** members, `authMode`, `permissionDimension`, `permissionColumn` and `rlsResolverName` (never read: a materialized query's result is always filtered by its **source table's** partition-level and row-level security, ADR 0040 D-9; the 0.14.0 changelog names the first three, `rlsResolverName` is refused too). **Delete the four members; to secure a result, set security on the source table.** From the next train the refusal's message says this |
| Overlay content (**BL-1460**) | any member was accepted and most were dropped | only `$schema`, `extends`, `settings.durability` and an existing table's `policy` and `durability` | `SCHEMA_OVERLAY_MEMBER_NOT_ALLOWED` (reported by a plan and a start as `SCHEMA_OVERLAY_INVALID`): move the member to the base file |
| `clusterColumns` (**BL-1460**) | an entry naming no column was dropped | refused: `Cluster column 'nope' in table 'orders' is not a column of the table.` | the schema file or the apply is refused |
| Schema apply (**BL-1460**) | a document-level error applied the valid tables and reported the bad one as a failed entry | `POST …/schema/apply` and `…/schema/diff` run the document-level checks first: one error is `400` and **nothing is applied** | a client that read a partial apply must read the `400` |
| Table names (**BL-1468**) | `POST …/tables`, rename, graph and vector creates, the catalog API and the schema apply accepted any name | no `/ \ : * ? " < > \|`, no leading or trailing period or space, not empty, `.` or `..`, no `__mqbuild_` prefix: `400 INVALID_REQUEST` naming the rule; `DELETE` / `PATCH` of a `__mqbuild_*` name is `404 TABLE_NOT_FOUND` | **a schema file that declares such a table now fails `aouda plan` and the start.** The remedy is a clean cut: read the rows out, give the table a legal name in the file, start once with `SchemaAllowDestructive: true` (or on a fresh data directory), then load the rows into the new table |
| Finding codes (**BL-1463**) | one coded line: `CONFIGURED_KEYS_INVALID`, `DECLARED_DATABASES_REFUSED`, `DECLARED_SCHEMA_REFUSED`, `DECLARED_ROLES_REFUSED` | those four are **gone**; a start prints every finding with its per-problem code (`KEY_SECRET_SHARED`, `SCHEMA_INVALID`, `ROLE_SYSTEM_NAME`, ...) on standard error, one `error    <CODE>  <setting or file>` line each. `CONFIGURATION_INVALID`, `DEV_ADMIN_REFUSED`, `SERVER_HAS_NO_OPERATOR` and `DATA_DIRECTORY_FORMAT_REFUSED` stay | a script that matched a removed code matches nothing: see [Declaration finding codes](../reference/plan-codes.md) |
| `aouda keys check`, `aouda schema check` (**BL-1463**) | the offline checks | **deleted**: unknown subcommands, exit `64`, no alias | use `aouda plan` ([the table](plan.md#replacing-aouda-keys-check-and-aouda-schema-check)); a schema that is not declared is checked with `aouda schema diff`. Their exit `2` ("could not check") is gone |
| Exit status of a refused start (**BL-1461**) | an unhandled exception: stack trace, SIGABRT, exit `134` | exit **78** (`EX_CONFIG`) and the findings on standard error; a start that only could not read a file (a volume not yet mounted) exits `1` | a supervisor that treated `134` as "refused" must treat `78` so. Docker's `restart:` policies cannot exempt a status: a refused container still restarts, and `docker compose logs` names the setting |
| Exit status of `aouda service` (**BL-1461**) | `78` for a service-manager failure | **71** (`78` now means a configuration refusal) | a script that branches on the service commands' `78` must read `71`. The unit `aouda service install` writes gains `RestartPreventExitStatus=78`: re-run the install on an existing host |
| Setup mode (**BL-1462**) | a declared server key was inert until a human created an admin | a declared server key (`Aouda:Auth:Bootstrap:ServerKey`, `ServerKeyFile`, the credential `aouda-server-key`, or a `server_admin` identity) **ends setup mode**: `_serverauth` is created with no user and the key operates the server. Setup mode exists only for a data directory never set up that declares nothing | a deploy that created an admin to get past setup mode needs no admin now. A data directory that has been set up **never re-enters setup mode**: with no user, no active server key and nothing declared the start is refused, `SERVER_HAS_NO_OPERATOR` (exit 78) |
| `Aouda:Auth:RequireFirstAdmin` (**BL-1462**) | failed the start of a server with no admin | **removed**; `AOUDA_AUTH__REQUIREFIRSTADMIN` is ignored | nothing: delete it from your compose file. `docker-compose.yml` passes `AOUDA_SERVER_KEY` through and no longer defaults the root email |
| The start window (**BL-1462**) | the port opened only after every start step, so callers met a closed port (71 s on an 11-file declaration) | the port opens first; the health endpoints answer and **every other request, loopback included, is `503 SERVER_STARTING` with `Retry-After: 5`** until the start has finished | a client that treated a refused connection as "not up yet" now sees `503`: retry on it and honour `Retry-After` |
| `aouda create-admin` (**BL-1462**) | wrote to the data directory of a running server, which stayed in setup mode until a restart | refuses a data directory a running server holds (exit `1`, naming the remedy): call `POST /api/auth/setup` from the server's host, or stop the server first | a script that ran `create-admin` against a live container: stop the container, or use the setup route ([Docker](../deployment/docker.md#the-first-admin)) |
| `POST /api/admin/reload` with a body (**BL-1463**) | `400 INVALID_REQUEST` | without `dryRun=true`: `400 RELOAD_CANDIDATE_NOT_APPLIED` (a posted declaration is only ever planned); a `dryRun` other than `true` / `false` is `400 INVALID_REQUEST` | a client that matched the old code |
| Realtime sessions (**BL-1001**) | an open WebSocket or long-poll session was never re-checked for an API key | ends when the key is revoked, expires or is retracted (`AUTH_TOKEN_REVOKED`) | a service that kept a stream open on a revoked key must reconnect with a live one |

**After 0.14.0: on `main`, not yet released** (**next train**). Nothing here is breaking.

- **A table's `description` is accepted** in a schema file (documentation in the file only; not stored, not diffed, not exported; a change is never drift and needs no migration). An overlay file still refuses it. A column's `description` is unchanged.
- **The four materialized-query security members** are still refused; the message now says they were never read and what to do (above).
- **A declaration file**, `/etc/aouda/aouda.json`, `AOUDA_CONFIG_FILE` or `--config`, so that `aouda reload` works in a container: [Server configuration §4a](server-configuration.md#declaration-file). If you declared `Aouda:Databases` through environment variables to follow the 0.14.0 Docker docs, `aouda plan` now tells you (the info `SOURCE_FIXED_AT_START`) that a reload will not see a change to it; moving it into the file is optional.
- **Helm:** `declaration.config`, `declaration.restartOnChange`, `extraEnv`, `extraEnvFrom`, `extraVolumes`, `extraVolumeMounts` ([Kubernetes and Helm](../deployment/kubernetes.md#declaring-databases-keys-and-schema-files)).
- **.NET client:** `WaitUntilReadyAsync`, `GetReadinessAsync`, the package `Aouda.Client.Extensions.DependencyInjection` with `AddAouda`, and `AoudaClientOptions.ApiKey` now trims surrounding white space (in 0.14.0 and earlier a key read from a file with a trailing newline made every request throw `FormatException`). A server that is still starting, `503 SERVER_STARTING`, no longer opens the circuit breaker or trips `AuthFailurePolicy.FailFast`: [.NET client](../clients/dotnet.md#waiting-for-the-server-to-start).

**In-process hosts only** (tests, an embedding): `ConfiguredKeyStore` is no longer a DI service; resolve `ConfiguredKeyStoreHolder` and read `Current`. Nothing changes for an HTTP or SDK client.

**New and not breaking:** `aouda plan` ([Plan a declaration](plan.md)) and `aouda reload` ([Keys that survive a wipe](keys-that-survive-a-wipe.md)), which re-reads the identities file,
`Aouda:Databases`, schema files and roles of a running server without a restart; the `Expression` column type ([Formulas](formulas.md)). The complete list is the [changelog](../CHANGELOG.md).

**A checklist for a compose deployment:** (1) wait on `/ready`, not `/health`; (2) rename each schema overlay to `<file>.<env>.json`; (3) run `aouda plan` on every schema file and fix every
`SCHEMA_UNKNOWN_MEMBER`, table-name and `description` finding; (4) retry on `503 SERVER_STARTING`; (5) replace `aouda keys check` / `aouda schema check` with `aouda plan`; (6) drop `AOUDA_AUTH__REQUIREFIRSTADMIN`;
(7) match exit status `78`, not `134`, for a refused start.

## What every release's notes carry

Each changelog entry that bumps the format quotes the line a server prints when it meets the previous version, with the real numbers, says what
an old directory now gets, and says the data must be exported with the build that wrote it. If a release's notes do not quote the line, the
format did not change.

## See also

- [Storage and persistence](storage.md) and [Backup and restore](backup.md).
- [Declared databases](declared-databases.md): after a wipe, a plain start recreates the declared set, empty of data.
