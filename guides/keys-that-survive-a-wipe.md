---
title: "Keys that survive a wipe"
nav_order: 2.5
parent: "Guides"
---

# Keys that survive a wipe (**BL-1377, 0.10.0**)

A key Aouda mints is a random value generated **inside the data a wipe destroys**. Every wipe, fresh machine and CI run therefore
produces new credentials that must be carried to every client, and a sender nobody updated fails with `AUTH_API_KEY_INVALID`
until someone notices.

A **configured key** turns that around. You declare the credential in configuration, the way you declare a SQL Server connection
string, and Aouda honours it from the first request. It is not stored in the database, so a wipe cannot lose it and nothing needs
to be re-imported, re-linked or re-minted. Keys Aouda mints still work, for throwaway cases and for anything created at runtime.

## The two pieces

| Piece | What it gives you |
|---|---|
| `Aouda:Auth:Bootstrap:ServerKey` (with `Aouda:Auth:RootUser`) | A working `mk_srv_` server key on a fresh server, with no sign-in or mint call |
| `Aouda:Auth:Keys:File` | An optional identities file declaring further keys: their kind, roles and secrets |

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

⚠️ **The key is inert until the server auth database exists, and that is until the first admin does.** Until then the server is in
setup mode and answers `503` to everything except the first-run setup routes, so a server key alone is not enough: set
`Aouda:Auth:RootUser` as well. If you set only the key, the server logs a warning that it takes effect after the first admin
exists. A configured key never widens the first-run setup window: that route is exactly as open, or closed, with or without it.

### Further keys: the identities file

```json
{ "identities": [
  { "name": "tullett-feeder", "kind": "scoped_service", "database": "deposit",   // authDatabase defaults to "auth"
    "roles": ["quote_writer"],
    "secrets": [ { "env": "TULLETT_KEY" }, { "hash": "sha256:<64 hex>" } ] } ] }
```

| Field | Meaning |
|---|---|
| `name` | Unique within the auth database; 1-64 characters of letters, digits, `.`, `_` and `-`. It is the key's name in logs and claims |
| `kind` | `server_admin` (global `db_admin`, on the server auth database; an `authDatabase` naming any other is refused) or `scoped_service` (the listed roles, scoped to `database`, on an application auth database) |
| `authDatabase` | Which auth database the key authenticates against. Defaults to `auth` for a scoped key |
| `database`, `roles` | Scoped keys only. The roles `db_admin`, `db_operator`, `anonymous` and `public` are refused, as they are for a minted scoped key |
| `secrets` | A list. `{ "env": NAME }` reads the plaintext key from that environment variable when the server starts. `{ "hash": "sha256:<hex>" }` is the hash of a key you hold elsewhere |

A literal plaintext `key` in the file is **refused**: a credential never sits in a file that is committed, copied and attached to
tickets. Other kinds (`service_role`, `auth_admin`, public keys, user-linked keys) are not configurable in this release.

**Every listed secret is live.** To rotate, add the new secret, deploy and restart, move the clients, then remove the old
one and restart again. Removing a secret or an entry retires it at the next restart. A running WebSocket or long-poll session
authenticated with a removed secret lives until it ends.

A change to the file or to the server key takes a **restart**. An invalid file, a missing environment variable or an unreadable path
**fails the start** with a message naming the entry (never a secret).

### What a key must look like

The kind's prefix (`mk_srv_` for `server_admin`, `mk_scp_` for `scoped_service`), then at least **32** characters from
`A-Z a-z 0-9 _ -`, not one repeated character and no run of more than 8 equal characters. That is a floor, not a proof of entropy:
generate keys with `openssl rand -hex 32` and put the prefix in front.

The declared `kind` must match the prefix wherever the server can see the plaintext (an `env` secret or the server key). For a
`hash` secret it cannot, and a mismatch there changes only the credential-kind label in the failure log, never the privilege.

## Roles, wipes and ordering

A configured `scoped_service` key holds the roles its entry names. Roles live in the auth database, so a wipe deletes them, and
the order of recovery does not matter: a key whose role does not exist yet is **denied** (`403`, not `401`) and starts working the
moment the role is created. Re-create the auth database, link it, re-create the roles, and the key works. No mint, import or
link-the-key step exists.

Creating a role that a configured key names **bumps the permission version**, so a cached denial is rebuilt at once. A feeder that
holds one WebSocket open for hours needs no reconnect: a write stream it opens after the role exists is allowed. A role that arrives
by a path that does not bump (a restore, a direct insert) is found within about 5 seconds: until then the key's denial is cached for
that long, so a typo in a role name costs one rebuild per window, not one per request.

Removing a secret from the file takes effect at the next restart, and a connection already authenticated with it lives until it ends.

A configured hit wins over a `_api_keys` row with the same hash, so a revoked or retired copy cannot shadow it. The usual way to
retire a configured key is to remove it from the file.

## Seeing which key is failing

Every rejected API key writes a warning line (throttled to one per window, as before). It now carries the caller address and a
summary, bounded to the 8 most frequent, of the **fingerprints** of the keys rejected since the previous line:

```
Auth failure: ApiKeyInvalid for credential 'mk_scp_' on POST /api/databases/deposit/tables/Quote/rows (auth database 'auth') from 10.0.4.17: Unknown API key [rejected key fingerprints since the last line: 3a1f9c02 x41, b77e0d11 x2]
```

When a rejected key is one you declared, but for a different auth database than the one it was presented to (the commonest cause is a
typo in `authDatabase`), its fingerprint is followed by the entry's name and the auth database it is declared for, so the cause is on
the line: `3a1f9c02 x41 (declared as 'tullett-feeder' for auth database 'aut', not 'auth')`. Only a key refused as a credential is
counted; a valid key refused for its route is not a failing sender.

A fingerprint is the first 8 hex characters of the key's SHA-256. It is a log field only. Match it to a declared key in the startup
log, which lists each configured key by name, kind, auth database, fingerprint and source (`env`, `hash` or `bootstrap`), or hash
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
in the file; reloading the file without a restart; `service_role` keys; listing configured keys through the admin API (the startup
log and `aouda keys hash` are the visibility).

## Related

- [Defaults reference](defaults-reference.md#configured-api-keys) - the configuration keys
- [HTTP API: credential types](../reference/http-api.md#credential-types)
- [Server configuration](server-configuration.md)
