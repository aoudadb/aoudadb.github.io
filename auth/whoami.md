---
title: "whoami and remedy"
nav_order: 4
parent: "Auth and Authorization"
---

# whoami and remedy (**BL-1464, 0.16.0**)

## whoami

`GET /api/auth/whoami` answers on both listeners. It says who the credential is and what that principal may do. It never returns `403`. A principal with no statements is `200` with `statements: []`. Nothing in the body is a secret: a key appears as its public id.

Query parameter `database` keeps a statement whose resource is `*`, names that database, or has that database as its first segment. `server` is not filtered that way. With no `database`, the whole policy is returned.

No credential:

| Listener | Answer |
|---|---|
| Admin | `401 AUTH_CREDENTIAL_MISSING`, with a `remedy` of `sign-in` |
| Data plane, `?database=` set | `200` as that database's `anonymous` principal. `credential` is `null`. |
| Data plane, no `database` | `400 INVALID_REQUEST` |

A data-plane caller that sent no credential gets **no** `remedy` member. An authenticated data-plane caller does.

The body, for a stored or derived key (ids and the hash are placeholders):

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
        "where": { "and": [ { "column": "source", "op": "in", "value": ["tullett"] } ] },
        "from": "role:rates-feeder"
      }
    ]
  },
  "permissionVersion": 1
}
```

`credential.type` is `key` (stored), `derived-key`, `limited-key`, or `session`. A session adds `signedInWith`, `aal`, and for an OIDC session `issuer` and `subject`. Anonymous sends `"credential": null`. `from` on a statement is `principal`, `role:<name>`, or `signup`.

`aouda whoami --server <url> --json` prints this body. Exit `0` on success, `77` when the credential is refused, `69` when the server cannot be reached.

## Remedy

Every refusal of this model has one body, whatever the status:

```json
{
  "error": "AUTH_POLICY_DENIED",
  "message": "auth/rates-feeder may not write rates/table/DepositQuote.",
  "requestId": "00000000000000000000000000000000",
  "remedy": { "kind": "grant", "principal": "auth/rates-feeder", "statement": { "actions": ["write"], "resources": ["rates/table/DepositQuote"] }, "owner": "declaration" }
}
```

`suggestion`, `detail` and `details` are not written. Null members are omitted. `X-Auth-Database` stays on a `401`.

| Status | Code | When | Remedy |
|---|---|---|---|
| 401 | `AUTH_CREDENTIAL_MISSING` | No credential. On the data plane the `remedy` member is omitted. | `sign-in` `{ authDatabase }` — the governing one; `_serverauth` for a server path |
| 401 | `AUTH_KEY_MALFORMED` | The value is not a key: `shape`, `checksum`, or `retired-format`. | `fix-key` `{ reason }` |
| 401 | `AUTH_CREDENTIAL_INVALID` | Unknown id, a secret that does not match, an ambiguous id, a session token whose signature, issuer or audience is wrong. | `fix-key` `{ reason }` — `unknown-id`, `secret-mismatch`, or `signature` |
| 401 | `AUTH_CREDENTIAL_EXPIRED` | The key or the session has expired. | `renew` `{ expiredAt }` when the expiry is known |
| 401 | `AUTH_CREDENTIAL_REVOKED` | Revoked key, disabled principal, ended parent, signed-out session. | `none` `{ revokedAt }` when the store holds it |
| 403 | `AUTH_WRONG_AUTH_DATABASE` | A valid credential of an auth database that does not govern the target. | `use-credential-of` `{ authDatabase }` |
| 403 | `AUTH_POLICY_DENIED` | The policy does not allow the action. The message is `"<authdb>/<name> may not <action> <resources>."` | `grant` `{ principal, statement, owner }` — one action, only the refused targets, no `where` |
| 403 | `AUTH_POLICY_DENIED` | The principal's policy allows it and the credential's limit does not. | `none` `{ reason: "credential-limit" }` |
| 403 | `AUTH_ROW_DENIED` | A written row the `where` does not admit. | `grant` whose `where` is `eq` on each column the caller sent. Key-shaped values are `<redacted>`. `none` when nothing sent is left to name. |
| 403 | `AUTH_EMBARGO_UNSUPPORTED` | A surface that cannot honour `embargoSeconds`. | `none` |
| 400 | `AUTH_PUBLIC_UNRESTRICTED` | A policy write would let `anonymous` or `signup` read a restricted table with no `where`, or would make `manage` public. | `add-where` `{ statement, exposes }`. `none` when the action is `manage`. |

Other auth errors (sign-in, signup, MFA, rate limits) keep their own bodies. Signup closed is `403 AUTH_SIGNUP_DISABLED`.

## Refusals

A refusal is logged once at Information: the code, the principal, the action, the resource and the remedy. A `where` keeps its columns and loses every value. A string shaped like a key is `<redacted>`.

On the data plane, a named artifact the caller may not execute stays the unknown-name `404`. That `404` is still logged as the refusal.

The loop an agent runs when a call is refused:

1. `whoami` — is this the principal you think it is, and does the policy contain the statement?
2. Read the refusal's `remedy`.
3. `aouda policy explain` — the same answer, offline, from `aouda.json`, for a declared principal.
4. Change the declaration (or ask the owner the `remedy` names) and reload.

`policy explain` does not know a runtime principal, a credential's limit, or a clock other than now. For those, the server's refusal is the answer.
