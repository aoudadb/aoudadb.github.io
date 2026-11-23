---
title: "Credentials"
nav_order: 3
parent: "Auth and Authorization"
---

# Credentials (**BL-1464, 0.16.0**)

A credential proves which principal is acting. It does not grant. Four kinds: a **stored key**, a **derived key**, an **OIDC trust**, a **limited key**, and a **session** (from a password or from an OIDC exchange). The key format is the same for every key.

## Key format

```text
aouda_<id>_<secret><checksum>
```

72 characters.

| Part | What it is |
|---|---|
| `aouda_` | The prefix. Six characters. |
| `<id>` | 16 characters, lower-case base32 (`a-z`, `2-7`). The **public** id. `whoami`, audit rows and logs may show `aouda_<id>` and nothing after it. |
| `_` | A separator. |
| `<secret>` | 43 characters, base62 (`0-9A-Za-z`). |
| `<checksum>` | 6 characters, base62. The IEEE CRC-32 of the 66 characters before it, four big-endian bytes. |

A mistyped key is `401 AUTH_KEY_MALFORMED` **before any lookup**, with remedy `fix-key`. `reason` is `checksum` (the shape is right and the checksum is not), `shape` (not 72 characters, or a character outside its class), or `retired-format` (the key starts with the prefix 0.14 used). Nothing is logged of the value.

A placeholder in these docs, which fails the checksum and is not a key:

```text
aouda_exampleexampleex_PLACEHOLDERPLACEHOLDERPLACEHOLDERPLACEHOLDERPLACE
```

The public id alone, which is what a declaration stores beside a hash: `aouda_exampleexampleex`.

## Stored keys

`POST /api/auth/{authDatabase}/principals/{name}/keys` mints a stored key. The response shows the key **once**. The declaration records the public id and the SHA-256 of the whole key, never the key:

```json
{ "id": "aouda_exampleexampleex", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
```

`aouda keys new` prints the same pair, and can write the key to a new file (mode `0600`, never overwritten) so it is not on a stream.

Revoke with `DELETE /api/auth/{authDatabase}/principals/{name}/credentials/{id}`. Rotation is mint a new key, then delete the old one. Nothing is minted implicitly, and there is no overlap window.

A declared stored key is `409 DECLARED_IN_CONFIGURATION` if the API tries to delete it; change the file and reload. Revoking it (so it stops authenticating) is allowed.

## Derived keys

A derived key is computed, not stored. The inputs are the key root, the auth database, the principal's name and a version. The same inputs after a wipe produce the same key. Declare it as:

```json
"credentials": { "derivedKey": { "version": 1 } }
```

and the root once, for the file:

```json
"keyRoot": { "env": "AOUDA_KEY_ROOT" }
```

`previousKeyRoot` keeps the previous root's derived keys working until you remove it. A derived key has no row in the credential table. `aouda keys derive auth/<name>` computes it on the deploy host from the root the server reads. The root is never an argument and never printed.

A revoked derived key that the file still declares is warned at start and reload (`DECLARED_OBJECT_OVERRIDDEN`), and the export moves the declared version to the next one no revocation names.

## OIDC

An OIDC trust says which issuer, audience and subject map to a principal:

```json
{
 "issuer": "https://token.actions.githubusercontent.com",
 "audience": "aouda",
 "subject": "repo:example/rates:ref:refs/heads/main"
}
```

`POST /api/auth/oidc/token` exchanges an identity token for a session. A duplicate or an overlap with any trust on the server is `409 AUTH_OIDC_TRUST_OVERLAP`. Two trusts of one issuer must use the same key source (`409 AUTH_OIDC_JWKS_CONFLICT`).

`aouda login --oidc --server <url> --id-token-env <NAME>` is the command a GitHub Actions job or a Kubernetes workload runs. The token comes from the environment, a file, or stdin. It is never an argument. Recipes are on the [CLI reference](../reference/cli.md).

## Limited keys

`POST /api/auth/keys` mints a limited key from the caller's own credential. The body is a limit: a subset of actions, resources and an optional `where`, plus an expiry. The parent chain is at most 4 deep. The limit is the intersection with the parent: a limited key is never wider than the principal, and never wider than the key it was minted from. `aud` on the token is the limit, not a second policy.

A limited key is how a backend acts for one call without holding the user's password. It is not a second header beside the caller's key.

## Sessions

`POST /api/databases/{db}/auth/signin` and `POST /api/auth/signin` exchange a password for a session (access token and refresh token). `POST …/auth/refresh` rotates the refresh token and keeps the assurance level the session was minted with.

The sign-in body may include `databases`: the session is then limited to those databases, the same narrowing as a limited key. An omitted `databases` means **no limit**. It does not mean a default list derived from a role. No limit is written on the access token as `aud: ["*"]` (see [What a session token carries](reference.md#what-a-session-token-carries)).

A session's `whoami` credential is `type: session`, with `signedInWith` (`password` or `oidc`), `aal`, and for OIDC the `issuer` and `subject`.

## Revocation

Revocation reaches open sockets. What ends a socket, and a write stream, within one heartbeat (default 20 seconds):

| What happened | Socket | Write stream |
|---|---|---|
| The key is revoked or deleted on this node | Ended when the revoke answers (push), then closed | A frame that has not yet been persisted is dropped |
| The principal is disabled | The same | The same |
| The parent of a limited key ends | The same | The same |
| A session is signed out | Ended at the next heartbeat (a session has no push) | The same |
| The credential expires | At the next heartbeat, and at the next frame batch on a write stream | The frame batch is refused |
| The revoke was applied from replication | At the next heartbeat (the replica does not push) | The same |

The close reason is `AUTH_CREDENTIAL_REVOKED` (remedy `none`) or `AUTH_CREDENTIAL_EXPIRED` (remedy `renew`). A frame already persisted before the check commits; the client treats a missing acknowledgement as unknown and sends it again, idempotently.
