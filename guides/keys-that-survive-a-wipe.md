---
title: "Keys that survive a wipe"
nav_order: 2.5
parent: "Guides"
---

# Keys that survive a wipe (**BL-1377, 0.10.0; reworked by BL-1378, next train**)

A key Aouda mints is a random value generated **inside the data a wipe destroys**. Every wipe, fresh machine and CI run therefore
produces new credentials that must be carried to every client, and a sender nobody updated fails with `AUTH_API_KEY_INVALID`
until someone notices.

A **declared key** turns that around. You declare the credential in configuration, the way you declare a SQL Server connection
string. Aouda turns each declared secret into a **real row of the auth database** (`source = config`) when that database is
created, at every start, and after a restore. After a wipe nothing needs to be re-imported, re-linked or re-minted: the declaration
is read again and the rows come back with the auth database. Keys Aouda mints still work, for throwaway cases and for anything
created at runtime.

(**BL-1378, next train**) **0.10.0 authenticated a declared key from memory:** no row, no listing, no revoke. That is gone. A declared
key is a row, so it is listed, queried, revoked and retracted through the same flows as a minted one. If you relied on a declared
key being invisible to the key listings, it no longer is.

## Declaration is intent, the row is state

| | Written by | What it covers |
|---|---|---|
| The **declaration** (the server key setting and the identities file) | You, in configuration | That the key exists, its `name`, its `roles`, and whether it is still wanted |
| The **row** in `_api_keys` | Aouda, from the declaration | The key itself: what authenticates. **Authentication reads only the row and never writes it** |
| **Revocation** | You, through the API | Whether the key is switched off. Configuration never switches it back on |

Three rules follow, and they are all the operator needs to know:

1. **A declared key with no row is `401 Unknown API key`**, like any key the database does not hold. Rows are made when the auth
   database is created, at start (after the first admin, before the server answers) and after a restore, never on a request. A row
   that cannot be made fails the start (or abandons the creation of the auth database) rather than leaving a key half there.
2. **Revoking is the normal flow, and it is sticky.** `DELETE` the key and the next request is `401 API key has been revoked`, also
   after a restart: the row stays revoked and the declaration does not undo it. The start logs a warning that the key is declared
   but revoked ("remove it from the declaration to make that permanent"); it does **not** fail the start, so an emergency revoke
   followed by a restart is not an outage.
3. **Removing a declaration retracts its row, reversibly.** At start, a configured row that no declaration lists is revoked and
   marked `config-removed`, with one warning per row (name, kind, auth database, fingerprint). Declare it again and the same row
   is revived. A row **you** revoked is never revived by a declaration, and a minted row is never touched.

⚠️ **A wipe resets revocation.** Revocation is state, and a wipe destroys state; the declaration survives. A key you revoked but
left in the file therefore **returns after a wipe**. To retract a key for good, remove it from the file (and revoke it if the
server is running).

With **no declaration source configured** (no `ServerKey`, `ServerKeyFile` or `Keys:File`) nothing is retracted and an information
line says that configured rows were left as they are, so a dropped setting cannot retract every key. An identities file that
declares nothing is a source: an empty file retracts them all.

## The supported unattended setup

Three settings give a fresh server working credentials with no sign-in, mint or import call:

| Piece | What it gives you |
|---|---|
| `Aouda:Auth:RootUser` | The first admin, and with it the server auth database (`_serverauth`) |
| `Aouda:Auth:Bootstrap:ServerKey` | A working `mk_srv_` server key, a row of `_serverauth` from the moment it exists |
| `Aouda:Auth:Keys:File` | The identities file declaring further keys: kind, roles, secrets |

### The server key

```bash
# generate once, keep it in your secret store
printf 'mk_srv_%s' "$(openssl rand -hex 32)"

# give it to the server, with the first admin
Aouda__Auth__Bootstrap__ServerKey=mk_srv_...            # or ServerKeyFile=/run/secrets/aouda-server-key
Aouda__Auth__RootUser__Email=admin@example.com
Aouda__Auth__RootUser__Password=...
```

The key comes from one of: `Aouda:Auth:Bootstrap:ServerKey`, a file named by `Aouda:Auth:Bootstrap:ServerKeyFile` (readable only
by its owner, as `--password-file` is), or the systemd credential `aouda-server-key` (`LoadCredential=`). Set at most one.

⚠️ **The key's row is made when the server auth database is, and that is when the first admin exists.** Until then the server is in
setup mode and answers `503` to everything except the first-run setup routes, so a server key alone is not enough: set
`Aouda:Auth:RootUser` as well. If you set only the key, the server logs a warning that it takes effect after the first admin
exists. A declared key never widens the first-run setup window: that route is exactly as open, or closed, with or without it.

### Further keys: the identities file

```json
{ "identities": [
  { "name": "tullett-feeder", "kind": "scoped_service", "database": "deposit",   // authDatabase defaults to "auth"
    "roles": ["quote_writer"],
    "secrets": [ { "env": "TULLETT_KEY" }, { "hash": "sha256:<64 hex>" } ] },
  { "name": "deposit-anon", "kind": "anon", "database": "deposit",
    "secrets": [ { "env": "DEPOSIT_ANON_KEY" } ] } ] }
```

| Field | Meaning |
|---|---|
| `name` | Unique within the auth database; 1-64 characters of letters, digits, `.`, `_` and `-`. It is the row's `name`; changing it while keeping the secret renames the row |
| `kind` | `server_admin` (global `db_admin`, on the server auth database), `scoped_service` (the listed roles, scoped to `database`), or one of the three system kinds below |
| `authDatabase` | Which auth database the key lives in. Defaults to `auth` for every kind but `server_admin` |
| `database` | Every kind but `server_admin`: the application database the key's roles are scoped to |
| `roles` | `scoped_service` only. The roles `db_admin`, `db_operator`, `anonymous` and `public` are refused, as they are for a minted scoped key. A system kind takes **no** `roles` |
| `secrets` | A list. `{ "env": NAME }` reads the plaintext key from that environment variable when the server starts. `{ "hash": "sha256:<hex>" }` is the hash of a key you hold elsewhere |

A literal plaintext `key` in the file is **refused**: a credential never sits in a file that is committed, copied and attached to
tickets. `auth_admin` and user-linked keys are not declarable.

#### The three system kinds (**BL-1378, next train**)

| `kind` | Prefix | Holds | Take the place of |
|---|---|---|---|
| `service_role` | `mk_svc_` | `db_admin` scoped to `database` | The `service_role` key a link or `regenerate-keys` generates |
| `public` | `mk_pub_` | `public` scoped to `database` | The `public` key it generates |
| `anon` | `mk_anon_` | `anonymous` scoped to `database` | The `anon` key it generates |

Their rows are `is_system`, as generated ones are. Declare **exactly one** per (auth database, database, kind) or the start fails
naming both entries. `database` is compared exactly as the catalog spells it: `Deposit` and `deposit` are two databases, so a
difference in case declares a second key.

A declared system key is **the** key of its kind. Linking a database generates and returns only the kinds you did **not** declare
(declare all three and nothing is generated or printed), and `regenerate-keys` leaves declared rows live, with the same ids, and
mints only the others. In the response of a create-with-auth, a link or a regenerate, `anonKey`, `serviceRoleKey` and `publicKey`
are therefore **absent** for a declared kind. Revoking a declared system key (by id) retracts it, and nothing replaces it.

**Every listed secret is live, and each is its own row.** To rotate a declared key, add the new secret, deploy and restart, move
the clients, then remove the old secret and restart again (its row is retracted at that start). Removing a secret or an entry never
disturbs the other secrets' rows. A running WebSocket or long-poll session authenticated with a removed secret lives until it ends.

**A declared key is revoked, never rotated.** `POST .../scoped-service-keys/{name}/rotate` on a declared key is `409`
("declared in configuration; change the declaration"); a minted scoped key rotates as before.

A change to the file or to the server key takes a **restart**. An invalid file, a missing environment variable or an unreadable
path **fails the start** with a message naming the entry (never a secret).

### What a key must look like

The kind's prefix (`mk_srv_`, `mk_scp_`, `mk_svc_`, `mk_pub_` or `mk_anon_`), then at least **32** characters from
`A-Z a-z 0-9 _ -`, not one repeated character and no run of more than 8 equal characters. That is a floor, not a proof of entropy:
generate keys with `openssl rand -hex 32` and put the prefix in front.

The declared `kind` must match the prefix wherever the server can see the plaintext (an `env` secret or the server key). For a
`hash` secret it cannot, and a mismatch there changes only the credential-kind label in the failure log, never the privilege.

### Check the file before you deploy

```bash
aouda keys check --file identities.json
# ok: 3 declaration(s), 4 secret(s)
#   tullett-feeder  scoped_service  auth/deposit  fingerprint 3a1f9c02 (env), 91c0aa17 (hash)
```

(**BL-1378, next train**) It loads the file with the environment of the process that runs it, exactly as the server does, prints each
declaration (name, kind, auth database, database, the fingerprint and source of each secret) and never a secret or a hash. It exits
`1` naming the entry on the first error, and warns when a scoped entry names a database that no `service_role`, `public` or `anon`
declaration mentions. It needs no server and no data directory, so it runs in CI.

## Seeing and managing the keys

- Every key listing carries `source`: `minted`, `config`, or `config-removed`. A declared key is listed like any other and is
  revoked like any other (`DELETE .../api-keys/{id}`, or by name for a scoped key).
- `GET /api/auth/admin/configured-keys` (a server key) lists every declaration with the state of its row in each auth database:
  `materialised`, `revoked`, or `pending` (the auth database does not exist yet). It names the entry, kind, auth database,
  database, fingerprint and where the secret comes from; it never carries a secret or a hash.
- `GET /api/server/metrics` carries `rejectedApiKeys`: how many API keys were refused as a credential since start, by kind only.

## Roles, wipes and ordering

A declared `scoped_service` key holds the roles its row names. Roles live in the auth database, so a wipe deletes them, and the
order of recovery does not matter: a key whose role does not exist yet is **denied** (`403`, not `401`) and starts working the
moment the role is created. Re-create the auth database (its declared rows are made with it), link it, re-create the roles, and
the key works. No mint, import or link-the-key step exists.

Creating a role that a declaration names **bumps the permission version**, so a cached denial is rebuilt at once. A feeder that
holds one WebSocket open for hours needs no reconnect: a write stream it opens after the role exists is allowed. A role that arrives
by a path that does not bump (a restore, a direct insert) is found within about 5 seconds: until then the key's denial is cached for
that long, so a typo in a role name costs one rebuild per window, not one per request. That window now applies to every scoped key,
declared or minted.

## Seeing which key is failing

Every rejected API key writes a warning line (throttled to one per window). It carries the caller address and a summary, bounded to
the 8 most frequent, of the **fingerprints** of the keys rejected since the previous line:

```
Auth failure: ApiKeyInvalid for credential 'mk_scp_' on POST /api/databases/deposit/tables/Quote/rows (auth database 'auth') from 10.0.4.17: Unknown API key [rejected key fingerprints since the last line: 3a1f9c02 x41, b77e0d11 x2]
```

When a rejected key is one you declared, its fingerprint is followed by the entry's name and why it was refused:
`3a1f9c02 x41 (declared as 'tullett-feeder' for auth database 'aut', not 'auth')` when it was presented to a different auth
database than the one it is declared for (the commonest cause is a typo in `authDatabase`), and
`3a1f9c02 x3 (declared as 'tullett-feeder'; its row is revoked)` when its row is revoked. Only a key refused as a credential is
counted; a valid key refused for its route is not a failing sender.

A fingerprint is the first 8 hex characters of the key's SHA-256. It is a log field only. Match it to a declared key in the startup
log, which lists each declared key by name, kind, auth database, fingerprint and source (`env`, `hash` or `bootstrap`), or hash
the dead key a legacy sender still holds:

```bash
printf '%s' "$KEY" | aouda keys hash --key-stdin
# hash: sha256:<hex>        <- the form the identities file takes
# fingerprint: 3a1f9c02     <- what the log line names
```

`aouda keys hash` reads the key from standard input only. There is no `--key` option, because a command line is readable by other
users on Linux and is kept by shell history and CI logs. There is no `keys generate`: `openssl rand -hex 32` is the generator.

⚠️ Eight hex characters of a hash of a **weak** key let someone who can read the log confirm guesses of it. That is one more reason the
shape rule exists, and why a key generated by `openssl rand -hex 32` is the only kind to use.

## Not in this release

An import API (`PUT` a supplied key into the database), `aouda keys import` and SDK methods; users, partition grants and custom roles
in the file; reloading the file without a restart; a runtime API that creates a declared key; expiry in the file; a Prometheus
endpoint (the counter above is in the JSON metrics snapshot).

## Related

- [Defaults reference](defaults-reference.md#configured-api-keys) - the configuration keys
- [HTTP API: credential types](../reference/http-api.md#credential-types)
- [Server configuration](server-configuration.md)
