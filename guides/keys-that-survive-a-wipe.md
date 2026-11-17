---
title: "Keys that survive a wipe"
nav_order: 2.5
parent: "Guides"
---

# Keys that survive a wipe (**BL-1377, 0.10.0; reworked by BL-1378, 0.11.0, and by BL-1464, next train**)

A key Aouda mints is a random value generated **inside the data a wipe destroys**. Every wipe, fresh machine and CI run therefore
produces new credentials that must be carried to every client, and a sender nobody updated fails with `AUTH_API_KEY_INVALID`
until someone notices.

A **declared key** turns that around. You declare the credential in the declaration file, `aouda.json`, the way you declare a SQL
Server connection string: as a `credentials` member of a declared principal (**BL-1464, next train**). The start converges every
declared principal and its credentials into its auth database, at every start, after a wipe and after a restore. After a wipe nothing
needs to be re-imported, re-linked or re-minted: the declaration is read again and the principals come back with the same ids. Keys
Aouda mints still work, for throwaway cases and for anything created at runtime.

The databases a declared key belongs to can be declared too, so a wipe brings back the whole set: [Declared databases](declared-databases.md).

## Declared credentials in `aouda.json` (**BL-1464, next train**)

A principal declared in [`aouda.json`](declared-access.md) declares how it authenticates under `credentials`, and every form
survives a wipe without seeding:

- **A derived key**, `"derivedKey": { "version": 1 }`. The key is computed from the file's one **key root** (`"keyRoot": { "file": … }`
  or `{ "env": … }` at the top of the file, never a literal) and the principal's auth database, name and version: after a wipe, a fresh
  machine or a CI run the same root gives the same key, and nothing is stored to restore. `aouda keys derive` prints it once for the
  client's secret store. To rotate one principal's key, bump its `version` and reload: the old key is refused at once and its open
  sessions end. To rotate the root, declare the new one as `keyRoot` and the old one as `"previousKeyRoot"`: keys of both are accepted
  until you remove the previous one.
- **A stored key**, `"keys": [ { "id": "aouda_…", "sha256": "…" } ]`: the public id and the SHA-256 of a key generated elsewhere — never
  the key. A whole key written into `id` is refused ("this file now contains a secret: rotate the key").
- **An OIDC trust** (a CI job, a cluster's workload identity): `"oidc": [ { "issuer", "audience", "subject", "claims"? } ]`. One token
  must never match two principals: two trusts of different principals that one token could match are refused.
- **A password seed** for a person, `"password": { "file" | "env" | "hash" }` on a principal named by its email: it creates the
  password when the principal is created (after a wipe, again), with a forced change at the first sign-in, and is never applied again.

**Revoking a declared key** (an incident) works at runtime and stays: every start and reload warns `DECLARED_OBJECT_OVERRIDDEN`, and for a
derived key names the version to declare next. A wipe loses the revocation — the same root derives the same key again — so the lasting
fix is to bump the version in the file.

## The old settings are refused (**BL-1464, next train**)

The identities file and the bootstrap server key of 0.10.0 to 0.14.0 (**BL-1377**, **BL-1378**, **BL-1389**, **BL-1462**) are
**removed**, with the first admin's `Aouda:Auth:RootUser`. Each one set, from any configuration source, is a `SETTING_REMOVED`
finding: `aouda plan` reports it, and the start is refused before any database opens (exit status `78`). The message names the
replacement and never the value. An **empty** value (a compose `${VAR:-}` pass-through of a variable that is not set) counts as not
set and is not refused.

| Removed | Replacement |
|---|---|
| `Aouda:Auth:Keys:File` (the identities file, `aouda.identities.json`; env `AOUDA_AUTH__KEYS__FILE`) and every setting under `Aouda:Auth:Keys` | Declare each key's principal in the declaration file: `databases.<auth>.principals` or `server.principals`, with its `credentials` (a `derivedKey` from the file's `keyRoot`, or a stored key `{ "id", "sha256" }` under `keys`) |
| `Aouda:Auth:Bootstrap:ServerKey`, `Aouda:Auth:Bootstrap:ServerKeyFile` (env `AOUDA_AUTH__BOOTSTRAP__SERVERKEY` / `AOUDA_AUTH__BOOTSTRAP__SERVERKEYFILE`) and every setting under `Aouda:Auth:Bootstrap` | Declare the operator: a `server.principals` entry holding the role `admin`, with a `derivedKey` (from the file's `keyRoot`) or a stored key `{ "id", "sha256" }` |
| `Aouda:Auth:RootUser:Email` / `Password` (env `AOUDA_AUTH__ROOTUSER__EMAIL` / `AOUDA_AUTH__ROOTUSER__PASSWORD`) | Declare the first admin: a `server.principals` entry named by the email, holding the role `admin`, with a password seed `{ "file": "<path>" }` or `{ "env": "<NAME>" }` (or `{ "hash": ... }`) |
| The systemd credentials `aouda-server-key` and `aouda-admin-password` (present in `$CREDENTIALS_DIRECTORY`) | Remove the unit's `LoadCredential=` line and declare as above |

A key-only operator, its key root from a secret, so a fresh server is operated from its first start with no human admin:

```json
{ "version": 1, "keyRoot": { "env": "AOUDA_KEY_ROOT" },
  "server": { "principals": { "ops": { "roles": ["admin"], "credentials": { "derivedKey": { "version": 1 } } } } } }
```

There is no converter: move each identities-file entry to a principal of its auth database, with the statements or roles it needs
and a credential. A `{ "hash": "sha256:<hex>" }` secret has no direct counterpart, because a stored key is declared by its public
`aouda_` id and its hash; mint or derive a new key and move the client to it. `aouda reload` changes a declared principal or credential
without a restart ([Declared databases](declared-databases.md#changing-the-declaration-without-a-restart-bl-1427-0140)), and
`aouda plan` checks the file first ([Plan a declaration](plan.md)).

## Seeing and managing the keys

- A declared credential is revoked like any other, and the revocation stays (`DECLARED_OBJECT_OVERRIDDEN`, above). The identities
  file's rows with `source` `config` / `config-removed`, and `GET /api/auth/admin/configured-keys` that listed them, are gone with it
  (**BL-1464, next train**); `GET /api/auth/whoami` says which principal and credential a caller presented.
- `GET /api/server/metrics` carries `rejectedApiKeys`: how many API keys were refused since start, by kind only, and two splits of the same total
  (**BL-1428, BL-1430, 0.12.0**): `rejectedApiKeysByTransport`, `{ "http": n, "websocket": n, "longpoll": n }`, and `rejectedApiKeysByReason`,
  `{ "credential": n, "listener_mismatch": n, "route_mismatch": n }`. Each always lists all of its keys and sums to `rejectedApiKeys`. See
  [Counting refused keys](#counting-refused-keys).

### Counting refused keys (**BL-1428, BL-1430, 0.12.0**) {#counting-refused-keys}

`GET /api/server/metrics` answers (the fields this section is about; `databases` and `process` are as before):

```json
{
  "rejectedApiKeys": { "server_admin": 0, "scoped_service": 0, "service_role": 0, "auth_admin": 0, "public": 0, "anon": 0, "other": 0 },
  "rejectedApiKeysByTransport": { "http": 0, "websocket": 0, "longpoll": 0 },
  "rejectedApiKeysByReason": { "credential": 0, "listener_mismatch": 0, "route_mismatch": 0 }
}
```

- **Every transport counts.** 0.11.0 counted HTTP authentication only, so a feeder whose key was revoked or mistyped on its WebSocket `auth`
  message never moved the counter. Since 0.12.0 a key refused at the WebSocket `auth` or `re_auth` message, or at a long-poll connect, is
  counted too, once per refusal, in the same per-kind dictionary. A rising `websocket` with a flat `http` is the feeder-lockout signal.
- **`rejectedApiKeysByReason`** tells a dead key from a misrouted one. `credential` is a key the auth database refused (unknown, revoked,
  expired, linked user disabled). `listener_mismatch` is a valid `mk_pub_` key sent to the admin listener (`AUTH_KEY_LISTENER_MISMATCH`), and
  `route_mismatch` is an application key sent to a server catalog route such as `GET /api/databases` (`AUTH_KEY_ROUTE_MISMATCH`). The set is
  closed at three; the finer credential reasons (revoked, expired, unknown) stay in the log line, because one refusal can carry the text of two
  auth databases. Before 0.12.0 the two mismatch cases were not counted over HTTP at all (they were counted on WebSocket and long-poll only).
- **Labels are closed**: the key kinds are those of the known prefixes (an invented prefix is `other`), the transports are the three above,
  and a key is never in a label. A route mismatch is decided by the key's prefix alone, as the `403` already was, so an invented `mk_svc_` key
  on `GET /api/databases` counts as one `route_mismatch`.
- **Not counted**: a JWT (it is not a key), and a session that is already open. An API-key session is not re-checked mid-session (a key's
  revocation is read at connect and at `re_auth`), so a key revoked while its socket stays open is counted when it next authenticates.
- The log line for a refused key (caller address and the fingerprints of the keys refused since the last line, never a key) exists on the
  WebSocket and long-poll paths as well as HTTP.

## Secret files (**BL-1425, 0.12.0**) {#secret-files}

Every secret the server reads from a file goes through **one reader**, so the rules are the same wherever a file is named. Before 0.12.0
each setting had its own reader and they disagreed on variables, relative paths, encodings and wording.

| Setting | A relative path resolves against | Permission check |
|---|---|---|
| The declaration's `keyRoot` / `previousKeyRoot` `{ "file": PATH }` and a password seed `{ "file": PATH }` (**BL-1464, next train**) | the directory of the declaration file | none |
| The cluster key, `Aouda:ReplicaSet:KeyFile` | the process's working directory | none |
| `aouda create-admin --password-file`, `aouda init --admin-password-file` | not applicable: the shell expands the path | **refuses a file readable beyond its owner** (an operator-made file for one command; `--password-stdin` reads no file) |

(**BL-1464, next train**) The identities file's `{ "file" }` secrets, `Aouda:Auth:Bootstrap:ServerKeyFile` and the systemd credentials
`aouda-server-key` / `aouda-admin-password` were rows of this table; they are refused now ([above](#the-old-settings-are-refused-bl-1464-next-train)).

The rules, for the first two rows:

- **Path.** `$NAME` and `${NAME}` are expanded from the environment first. An unset or empty variable fails the start naming the variable; a `$` that
  starts no name is a literal. The expansion is never shown: messages quote the path as written, and a path containing `mk_` is shown as
  `<redacted>`.
- **Content.** Read as strict UTF-8. A UTF-8 byte-order mark is removed; a UTF-16 or UTF-32 file (what PowerShell's `Out-File` writes) is refused,
  never guessed at. **Exactly one** trailing newline (`\n`, `\r\n` or `\r`) is removed and nothing else is trimmed. Nothing left is an error.
- **No permission check.** Docker and Kubernetes mount a secret `0444`.
- **Messages.** `<setting> names secret file '<path>', which cannot be read (<ExceptionType>).` or `<setting> names secret file '<path>', which is empty.`
  The content is never in a message or a log line.

What changed for an existing deployment (0.11.0 to 0.12.0; history — the `ServerKeyFile`, systemd-credential, identities-file and
`RootUser` lines are about settings refused since **BL-1464, next train**):

- `ServerKeyFile` now expands `$NAME`/`${NAME}`, and a missing file reads `... which cannot be read (FileNotFoundException).`, where it read `does not exist`.
- A systemd credential that is not UTF-8 is refused (it used to guess UTF-16/32 from a byte-order mark), and an empty one reads
  `systemd credential '<name>' names secret file '...', which is empty.`
- The cluster `KeyFile` no longer trims surrounding whitespace (one trailing newline only), expands `$NAME`, and a missing file is a
  `SecretFileException`, not `FileNotFoundException`.
- An identities-file path defect reads `identity '<name>': the file path ...` (it was `has a 'file' secret whose path ...`).
- Not changed: `Aouda:Auth:RootUser:Password` is a value or the `aouda-admin-password` credential (there is no password-file setting), and
  `Aouda:Auth:Bootstrap:ServerKey` and an `{ "env": NAME }` secret are not files.

## Seeing which key is failing

Every rejected API key writes a warning line (throttled to one per window). It carries the caller address and a summary, bounded to
the 8 most frequent, of the **fingerprints** of the keys rejected since the previous line:

```
Auth failure: ApiKeyInvalid for credential 'mk_scp_' on POST /api/databases/deposit/tables/Quote/rows (auth database 'auth') from 10.0.4.17: Unknown API key [rejected key fingerprints since the last line: 3a1f9c02 x41, b77e0d11 x2]
```

Only a key refused as a credential is counted; a valid key refused for its route is not a failing sender. (The identities file's
`declared as '<entry>'` annotation on a fingerprint is gone with the file, **BL-1464, next train**.)

A fingerprint is the first 8 hex characters of the key's SHA-256. It is a log field. Hash the dead key a legacy sender still holds
to match it:

```bash
printf '%s' "$KEY" | aouda keys hash --key-stdin
# hash: sha256:<hex>
# fingerprint: 3a1f9c02     <- what the log line names
```

`aouda keys hash` reads the key from standard input only. There is no `--key` option, because a command line is readable by other
users on Linux and is kept by shell history and CI logs. There is no `keys generate`: `openssl rand -hex 32` is the generator.

⚠️ Eight hex characters of a hash of a **weak** key let someone who can read the log confirm guesses of it. That is why a key
generated by `openssl rand -hex 32` (or derived from a key root) is the only kind to use.

## Not in this release

An import API (`PUT` a supplied key into the database), `aouda keys import` and SDK methods; reloading the declaration when it
changes (a reload is run by hand: `aouda reload`); a runtime API that creates a declared key; a Prometheus endpoint (the counter
above is in the JSON metrics snapshot).

## Related

- [Defaults reference](defaults-reference.md#configured-api-keys) - the refused key settings and their replacements
- [Declared access](declared-access.md) and [The declaration file](../reference/declaration.md) - principals and `credentials`
- [HTTP API: credential types](../reference/http-api.md#credential-types)
- [Server configuration](server-configuration.md)
