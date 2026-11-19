---
title: "Auth reference"
nav_order: 9
parent: "Auth and Authorization"
---

# Auth reference (**BL-1464, 0.16.0**)

Exact request and response JSON, status codes and defaults are in the [HTTP API](../reference/http-api.md#access-principals-credentials-and-policy). This page is the index of those routes, the error codes, and the habits that keep a key out of a log. It is not a second copy of the bodies.

## Routes

| You are doing | Method and path | The HTTP API section |
|---|---|---|
| Who is this credential? | `GET /api/auth/whoami` | [whoami](../reference/http-api.md#get-apiauthwhoami) |
| Principals, roles, signup, credentials | `/api/auth/{authDatabase}/…` | [Access routes](../reference/http-api.md#access-routes) |
| Mint a stored key | `POST …/principals/{name}/keys` | [Stored keys](../reference/http-api.md#stored-keys) |
| Mint a limited key | `POST /api/auth/keys` | [Limited keys](../reference/http-api.md#limited-keys) |
| Exchange an OIDC token | `POST /api/auth/oidc/token` | [OIDC exchange](../reference/http-api.md#oidc-exchange) |
| Sign in, refresh, sign out | `POST /api/databases/{db}/auth/signin` and the siblings | [Sessions](../reference/http-api.md#sessions) |
| Password and MFA | `…/auth/reset-password`, `…/auth/mfa/…`, `…/admin/users/{id}/…` | [Password and MFA](setup.md) |
| Read the declaration | `GET /api/admin/declaration` and `…/export` | [Declaration view](../reference/http-api.md#get-apiadmindeclaration) |

The `{id}` on `…/admin/users/{id}` is the principal's id. The path segment is the route the server has.

## Errors

One row per code of this model. The body is `{ "error", "message", "requestId", "remedy" }`. Status and remedy kinds are [Remedy](whoami.md#remedy).

| Code | Status |
|---|---|
| `AUTH_CREDENTIAL_MISSING` | 401 |
| `AUTH_KEY_MALFORMED` | 401 |
| `AUTH_CREDENTIAL_INVALID` | 401 |
| `AUTH_CREDENTIAL_EXPIRED` | 401 |
| `AUTH_CREDENTIAL_REVOKED` | 401 |
| `AUTH_WRONG_AUTH_DATABASE` | 403 |
| `AUTH_POLICY_DENIED` | 403 |
| `AUTH_ROW_DENIED` | 403 |
| `AUTH_EMBARGO_UNSUPPORTED` | 403 |
| `AUTH_PUBLIC_UNRESTRICTED` | 400 |
| `AUTH_POLICY_INVALID` | 400 |
| `AUTH_ATTRIBUTE_CAP` | 400 |
| `AUTH_SIGNUP_DISABLED` | 403 |
| `AUTH_OIDC_TRUST_OVERLAP` | 409 |
| `AUTH_OIDC_JWKS_CONFLICT` | 409 |
| `AUTH_BUILTIN_READ_ONLY` | 409 |
| `AUTH_NAME_TAKEN` | 409 |
| `AUTH_PRINCIPAL_NOT_FOUND` | 404 |
| `AUTH_ROLE_NOT_FOUND` | 404 |
| `AUTH_CREDENTIAL_NOT_FOUND` | 404 |
| `DECLARED_IN_CONFIGURATION` | 409 |

Password-reset and MFA codes (`AUTH_RESET_*`, `AUTH_MFA_*`) are [Setup and flows](setup.md).

## Keeping a key a secret

- A key is shown once, at mint. After that the server stores `aouda_<id>` and a SHA-256.
- Prefer `aouda keys new --key-file` and `aouda keys derive --key-file`. A key is never an argument.
- A derived key's root is `keyRoot: { "env" }` or `{ "file" }`. The root is never in the declaration as a value, and `whoami` does not return it.
- Do not put a key in a URL, a query string, or a log line you control. Both SDKs refuse a key-shaped string in a URL before the request is sent.
- Examples in this site use `aouda_exampleexampleex` or a placeholder that fails the checksum. A placeholder is not a credential.

## What a session token carries

`iss` (the auth database's issuer), `sub` (the principal id), `email`, `sid`, `aal`, `exp`, `iat`, `jti`, and `aud` taken from the session's limit. The library may also write `nbf`. It does not carry a role list, a permission list, or attributes. Those are read from the store on each request. Validate a token you received from Aouda against the auth database's JWKS; do not read an authorization decision out of the claims.

`aud` is the session's database limit, not the auth database name. A sign-in that omits `databases` (no limit) mints `aud: ["*"]`. A gateway or BFF that validates the JWT with a fixed audience such as `auth` or `_auth` will refuse every ordinary browser session. Match `ValidAudience` (or the equivalent) to `*`, or accept the claim values the token actually carries.

## Testing

`AoudaTestServer` takes a `Declaration` and a derived key. `CreateClient(db, key)` sends that key. `CreateAnonymousClient(db)` sends none, which on the data plane is the `anonymous` principal. A throwaway server on a laptop is `aouda start --dev-admin`; the one stdout line is `AOUDA-DEV-ADMIN email=… password=… key=…`. The `key=` value is a stored key of the dev-admin principal, in the current format. Do not copy it into a page.
