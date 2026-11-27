---
title: "Keys that survive a wipe"
nav_order: 2.5
parent: "Guides"
---

# Keys that survive a wipe (**BL-1377, 0.10.0; reworked by BL-1378, 0.11.0, and by BL-1464, 0.16.0**)

A key Aouda mints is a random value generated **inside the data a wipe destroys**. Every wipe, fresh machine and CI run therefore
produces new credentials that must be carried to every client, and a sender nobody updated fails with `AUTH_API_KEY_INVALID`
until someone notices.

A **declared key** turns that around. You declare the credential in the declaration file, `aouda.json`, the way you declare a SQL
Server connection string: as a `credentials` member of a declared principal (**BL-1464, 0.16.0**). The start converges every
declared principal and its credentials into its auth database, at every start, after a wipe and after a restore. After a wipe nothing
needs to be re-imported, re-linked or re-minted: the declaration is read again and the principals come back with the same ids. Keys
Aouda mints still work, for throwaway cases and for anything created at runtime.

The databases a declared key belongs to can be declared too, so a wipe brings back the whole set: [Declared databases](declared-databases.md).

## Declared credentials in `aouda.json` (**BL-1464, 0.16.0**)

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

## The old settings are refused (**BL-1464, 0.16.0**)

The identities file, `Aouda:Auth:Bootstrap:ServerKey`, `ServerKeyFile`, `Aouda:Auth:RootUser` and the systemd credentials `aouda-server-key` and `aouda-admin-password` are refused (`SETTING_REMOVED`). `aouda plan` reports each one, and the start exits `78` before any database opens. The message names the replacement and never the value. An empty value (a compose `${VAR:-}` of a variable that is not set) counts as not set.

| Removed | Replacement |
|---|---|
| Identities file (`Aouda:Auth:Keys:File`) | A principal of that auth database, with statements or a role, and a credential |
| Bootstrap server key | `server.principals`: a principal with role `admin` and a derived or stored key |
| `aouda-server-key` and `aouda-admin-password` | Remove the unit's `LoadCredential=` line and declare as above |

```json
{ "version": 1, "keyRoot": { "env": "AOUDA_KEY_ROOT" },
  "server": { "principals": { "ops": { "roles": ["admin"], "credentials": { "derivedKey": { "version": 1 } } } } } }
```

There is no converter. A `{ "hash": "sha256:<hex>" }` secret has no counterpart: a stored key is `{ "id": "aouda_…", "sha256": "…" }` from `aouda keys new`, or a derived key from `aouda keys derive`. `aouda reload` applies a changed principal without a restart.

## Seeing which credential is failing

`GET /api/auth/whoami` with the credential says which principal it is and which statements it holds. A refusal is logged once, with the code, the principal, the action, the resource and the remedy — never the key. The key commands are `aouda keys new`, `aouda keys new-root` and `aouda keys derive`.

### Counting refused keys (**BL-1428, BL-1430, 0.12.0**) {#counting-refused-keys}

`aouda.auth.rejected_keys_total` on [`GET /api/admin/metrics`](../reference/http-api.md#admin-metrics-bl-851-next-train) (`manage` on `server`) counts the credentials refused since the server
started, once per refusal, by `transport` (`http`, `websocket`, `longpoll`) and `reason` (`credential`, `malformed`, `retired_format`): nine
points, always all of them (**BL-851, next train**: it was `rejectedApiKeysByTransport` and `rejectedApiKeysByReason` on `GET /api/server/metrics`,
which is gone; **BL-1464, 0.16.0**: the reasons; there is no count by kind of key).

- **Every transport counts**: HTTP, the WebSocket `auth` or `re_auth` message, and a long-poll connect. A rising `websocket` with a flat `http` is
  the signal of a feeder locked out.
- `credential` is a key or a session the auth database refused (unknown, revoked, expired, of another auth database); `malformed` a value whose
  shape or checksum is wrong; `retired_format` a key of 0.14.
- The warning in the log names the 8 most frequent **fingerprints** of the keys refused since the previous line: the first 8 hex characters of a
  key's SHA-256, never the key.

## Secret files (**BL-1425, 0.12.0**) {#secret-files}

Every secret the server reads from a file goes through one reader.

| Setting | A relative path resolves against | Permission check |
|---|---|---|
| `keyRoot`, `previousKeyRoot` and a password seed `{ "file": PATH }` | the directory of `aouda.json` | none |
| `Aouda:ReplicaSet:KeyFile` | the process's working directory | none |

- **Path.** `$NAME` and `${NAME}` expand from the environment. An unset variable fails the start naming the variable. A path that contains a key is shown as `<redacted>`.
- **Content.** Strict UTF-8. A UTF-8 byte-order mark is removed. UTF-16 (what PowerShell's `Out-File` writes) is refused. Exactly one trailing newline is removed. Nothing left is an error.
- **No permission check** on a declaration secret, so a Docker secret mounted `0444` is readable. The file must still be readable by the server's user.
- **Messages** name the setting and the path, never the content.

## Not in this release

An import API that accepts a key you supply, and a runtime API that adds a credential to a declared principal (change the file and reload). A limited key is allowed: it only narrows.

## Related

- [Defaults reference](defaults-reference.md#configured-api-keys) - the refused key settings and their replacements
- [Declared access](declared-access.md) and [The declaration file](../reference/declaration.md) - principals and `credentials`
- [HTTP API: credential types](../reference/http-api.md#credential-types)
- [Server configuration](server-configuration.md)
