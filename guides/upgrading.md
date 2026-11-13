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
directory starts on 0.12.0 unchanged. Server **0.13.0** writes format **18** (**BL-1418, 0.13.0**) and refuses a 17 directory: see [Upgrading to entitlements](#upgrading-to-entitlements-bl-1418-0130).

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
- (**BL-1463, next train**) `aouda start` exits with status **78** (`EX_CONFIG`) and prints the refusal as a finding on standard error
  (`error    DATA_DIRECTORY_FORMAT_REFUSED`, then the line above); the systemd unit does not restart it. `aouda doctor` and
  `aouda status` never load the catalog and do not report it.
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
| Table `authMode` | `auth-db-pls` | `auth-db-entitlement` (`jwt-claim` and `auth-db-rls` unchanged) | `400 Invalid authMode. Valid values: jwt-claim, auth-db-entitlement, auth-db-rls.`; a schema file fails `aouda schema check`, `schema apply` and a declared-schema start with `Unsupported authMode 'auth-db-pls'. Valid values: jwt-claim, auth-db-entitlement, auth-db-rls.` |
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

## What every release's notes carry

Each changelog entry that bumps the format quotes the line a server prints when it meets the previous version, with the real numbers, says what
an old directory now gets, and says the data must be exported with the build that wrote it. If a release's notes do not quote the line, the
format did not change.

## See also

- [Storage and persistence](storage.md) and [Backup and restore](backup.md).
- [Declared databases](declared-databases.md): after a wipe, a plain start recreates the declared set, empty of data.
