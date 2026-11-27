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
| A person's devices; end one | `GET …/auth/sessions`, `DELETE …/auth/sessions/{id}`, `POST …/auth/signout` | [Sessions are devices](../reference/http-api.md#sessions-are-devices) |
| Sign a native app in through the browser | `…/auth/admin/native-clients`, `POST …/auth/authorize`, `POST …/auth/token` | [Native sign-in](../reference/http-api.md#native-sign-in-through-the-browser) |
| Password and MFA | `…/auth/reset-password`, `…/auth/mfa/…`, `…/admin/users/{id}/…` | [Password and MFA](setup.md) |
| Read the declaration | `GET /api/admin/declaration` and `…/export` | [Declaration view](../reference/http-api.md#get-apiadmindeclaration) |
| Apply the declaration file to a running server | `POST /api/admin/reload`, `GET /api/admin/reload` | [Reload](../reference/http-api.md#post-apiadminreload) |

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

The codes of sessions, native sign-in and the rate limits are older than this model and carry `{ "error", "message", "requestId" }` and sometimes a `suggestion`, no `remedy`. Each one's meaning is in the [HTTP API](../reference/http-api.md#authentication-errors-4xx).

| Code | Status | Where |
|---|---|---|
| `AUTH_INVALID_CREDENTIALS` | 401 | Sign-in: wrong password or no such account |
| `AUTH_ACCOUNT_LOCKED` | 423 | Sign-in: 10 wrong passwords, locked 15 minutes. `Retry-After` |
| `AUTH_ACCOUNT_DISABLED` | 423 | A refresh, or a native `token`, of a principal an administrator disabled |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | A refresh token that is spent, expired or revoked |
| `AUTH_RATE_LIMITED` | 429 | [Rate limiting](#rate-limiting). `Retry-After` |
| `AUTH_SESSION_NOT_FOUND` | 404 | Ending a session that is not the caller's |
| `AUTH_DEVICE_INFO_TOO_LONG` | 400 | `deviceInfo` over 512 UTF-8 bytes |
| `AUTH_NATIVE_CLIENT_UNKNOWN`, `AUTH_REDIRECT_URI_INVALID`, `AUTH_REDIRECT_URI_NOT_REGISTERED` | 400 (`404` on delete) | Registering a native client, and `authorize` |
| `AUTH_PKCE_METHOD_UNSUPPORTED`, `AUTH_PKCE_CHALLENGE_INVALID` | 400 | `authorize` |
| `AUTH_UNSUPPORTED_GRANT_TYPE`, `AUTH_CODE_INVALID`, `AUTH_CODE_EXPIRED`, `AUTH_CODE_REUSED`, `AUTH_REDIRECT_URI_MISMATCH`, `AUTH_PKCE_VERIFIER_INVALID` | 400 | `token` |

## Keeping a key a secret

- A key is shown once, at mint. After that the server stores `aouda_<id>` and a SHA-256.
- Prefer `aouda keys new --key-file` and `aouda keys derive --key-file`. A key is never an argument.
- A derived key's root is `keyRoot: { "env" }` or `{ "file" }`. The root is never in the declaration as a value, and `whoami` does not return it.
- Do not put a key in a URL, a query string, or a log line you control. Both SDKs refuse a key-shaped string in a URL before the request is sent.
- Examples in this site use `aouda_exampleexampleex` or a placeholder that fails the checksum. A placeholder is not a credential.

## What a session token carries

`iss` (the auth database's issuer), `sub` (the principal id), `email`, `sid`, `aal`, `exp`, `iat`, `jti`, and `aud` taken from the session's limit. The library may also write `nbf`. It does not carry a role list, a permission list, or attributes. Those are read from the store on each request. Validate a token you received from Aouda against the auth database's JWKS; do not read an authorization decision out of the claims.

`aud` is the session's database limit, not the auth database name. A sign-in that omits `databases` (no limit) mints `aud: ["*"]`. A gateway or BFF that validates the JWT with a fixed audience such as `auth` or `_auth` will refuse every ordinary browser session. Match `ValidAudience` (or the equivalent) to `*`, or accept the claim values the token actually carries.

## Discovery endpoints

| Endpoint | URL |
|---|---|
| OIDC discovery | `GET /api/databases/{db}/auth/.well-known/openid-configuration` |
| JWKS (public keys) | `GET /api/databases/{db}/auth/.well-known/jwks.json` |

Both are public: no credential, on either listener. A database that does not exist, or whose auth is not an application auth database, is `404 DATABASE_NOT_FOUND`. The discovery document answers `Cache-Control: public, max-age=86400` and the JWKS `public, max-age=3600`. The document's `issuer` is the **auth database's** URL, `{base}/api/databases/{authDb}` (`{base}` is `Aouda:BaseUrl` when set), the `iss` of every session token that auth database mints, whichever linked database's path minted it: the document at a database linked to a separate auth database names that auth database. Its other members point at `{base}/api/databases/{db}/auth/`: `jwks_uri`, `token_endpoint` (`signin`), `registration_endpoint` (`signup`) and `revocation_endpoint` (`signout`). `code_challenge_methods_supported` is `["S256"]`, `id_token_signing_alg_values_supported` `["RS256"]`, and there is no `authorization_endpoint` (Aouda serves no login page) and no `userinfo_endpoint`.

> **Non-standard discovery path: read before using `AddJwtBearer`.** The document is served at `…/auth/.well-known/openid-configuration`, one path segment deeper than the OIDC convention `{issuer}/.well-known/openid-configuration`. A library that builds the metadata URL from `Authority` alone asks the wrong path and gets a `404`, so every request fails to validate. Set the metadata address yourself:
>
> ```csharp
> options.Authority       = "https://db.example.com/api/databases/myapp";
> options.MetadataAddress = "https://db.example.com/api/databases/myapp/auth/.well-known/openid-configuration";
> ```

The issuer of the **server** auth database's tokens (`/api/auth/signin`, setup) is the string `aouda`.

## Sessions are devices

(**NativeClients, 0.4.0**) A session is one sign-in on one device. Its refresh tokens are one family, and every access token it mints carries the family's id as `sid`. A refresh does not make a new session, so a principal with a laptop and a phone has two, and `GET …/auth/sessions` lists those two, with `deviceInfo` (what the client said, at most 512 UTF-8 bytes) and `userAgent` and `ipAddress` (what the server saw).

**Ending a session** revokes its refresh tokens and refuses its access tokens on the next request. It ends when it signs out (`POST …/auth/signout` ends **this** session; `{ "scope": "others" }` every other one; `{ "scope": "global" }` all), when the principal ends it from another device, when an operator ends it (`_serverauth` only), when a spent refresh token is presented again (read as theft, so the whole session ends, the access token it last issued included: a client keeps the refresh token each refresh returns, not the one it first stored), when the password changes or is reset, when an operator removes one of the principal's MFA factors, and when the principal is disabled or deleted.

An open realtime connection is held to the same rule: a WebSocket is closed within one heartbeat (20 seconds by default), and a long-poll session answers its next request `401`. [Realtime: a revoked or expired credential](../reference/http-api.md#realtime-revoked-credential) has the codes, the timing and what a write in flight may have done.

> **Signing out is per device.** A client that signs a principal out everywhere sends `{ "scope": "global" }`.

Routes, bodies, the list of what ends a session and the admin routes: [Sessions are devices](../reference/http-api.md#sessions-are-devices).

## The token allowance

(**BL-1018, 0.9.0**; a limit since **BL-1464, 0.16.0**) A session carries an **allowance**: the databases it may open. It is the session's limit: it narrows what the principal's statements allow, and never grants. `databases` on sign-in, on a password reset and on a native `authorize` sets it. Left out, the session has **no limit**, `aud: ["*"]`: nothing is derived from a role, because a role grants through statements and a token names no role. Given, each name must be the auth database itself or a database linked to it, at most 64 of them; anything else is `400 INVALID_REQUEST` and nothing is minted.

A session used on a database outside its allowance is `403 AUTH_POLICY_DENIED`, remedy `none`, `reason: credential-limit`. A refresh at a database outside it is refused before the refresh token is spent. A refresh and an MFA step-up keep the allowance and never widen it; sign-up gives the database signed up on. `AUTH_DATABASE_NOT_IN_ALLOWANCE` is not produced.

One sign-in that covers several applications is the allowance doing its job: name them in `databases`, or leave it out. A session with no limit can reach every database its auth database governs, so databases that share an auth database share their principals and their sign-in ([Auth databases](principals.md#auth-databases)). The rules in full: [The token allowance](../reference/http-api.md#the-token-allowance).

## Native sign-in through the browser

(**NativeClients, 0.4.0**) A native app (a desktop app, a phone app) signs a principal in by handing off to the browser, where your web front is already signed in, MFA included, and comes back with a session of its own at the same assurance level. Aouda serves no login page and no consent screen: your web front does the asking.

1. An operator registers the native client once, with `manage` on the auth database: `POST …/auth/admin/native-clients` `{ "name", "redirectUris" }`. A redirect URI is a loopback URL (`http://127.0.0.1/path`, registered without a port; any port matches), a reverse-DNS private-use scheme (`com.example.app:/oauth`) or a claimed `https` link.
2. The app makes a PKCE pair: a random `codeVerifier` (43 to 128 characters) and `codeChallenge`, the base64url of its SHA-256. It opens your web front in the browser with the challenge and its redirect URI.
3. The web front, signed in, **asks the person** ("Sign in to MyApp on this device?") and only on their click calls `POST …/auth/authorize`. It sends the browser to the `redirectTo` it gets back. The code is single use, valid for **60 seconds**, kept only as its hash, and carries the web session's `aal`, never more.
4. The app receives the code at its redirect URI and calls `POST …/auth/token` with the code, its verifier, the same `clientId` and `redirectUri` and its `deviceInfo`. It gets the usual token answer: a new session, listed under the principal's devices.

⚠️ **Do not let the web front approve without asking.** A page that calls `authorize` as soon as it loads hands a session, at `aal2` if the person did MFA, to whatever app opened it with its own challenge. On a phone another app can register the same private-use scheme (RFC 8252 §8.6), so prefer a claimed `https` link there.

A code is consumed before anything else is checked: a wrong verifier, client or redirect URI, or an expired code, each spends it, and the app starts again. Redeemed twice, it ends the session the first redemption opened. Both routes share the sign-in [rate limit](#rate-limiting). A code carries the allowance of the web session, or the part of it `authorize`'s `databases` names; redeemed on a database outside it, it is `403 AUTH_POLICY_DENIED` and is spent. The routes, the redirect rules and every code: [Native sign-in](../reference/http-api.md#native-sign-in-through-the-browser). Recipes for a desktop and a phone app: [Native apps](setup.md#native-apps-sign-in-through-the-browser).

## Rate limiting

| Limit | Default | Counted |
|---|---|---|
| Sign-up | 5 per minute | per client IP address |
| Sign-in, `request-password-reset`, `reset-password`, native `authorize` and `token`, OIDC exchange | 20 per minute | per client IP address |
| Account lockout | 10 wrong passwords, then 15 minutes | per account |
| `Aouda:Auth:FailedSigninCeiling` | **off**; `PermitLimit` 100 failed sign-ins per `WindowSeconds` 300 | per auth database, per server process |

Over a limit the answer is `429 AUTH_RATE_LIMITED` with `Retry-After`, or `423 AUTH_ACCOUNT_LOCKED` for a locked account. A client waits that long and tries again. The per-IP limits are fixed; behind a reverse proxy the IP is the client's only when the proxy is trusted ([reverse proxy](../deployment/reverse-proxy.md)).

The per-IP limits and the lockout cannot see a credential-stuffing campaign that tries one password against many accounts from many addresses: each account sees one failure and each IP one request. The **failed-sign-in ceiling** is the aggregate control for that shape. Failed sign-ins on one auth database are counted in a sliding window and a successful one does not consume the budget. When it is over, **every** sign-in on that auth database is `429`, the right password included, until the window drains. It is checked before the password is hashed, so a tripped ceiling cannot be used to drive accounts into lockout. That is a full login outage for the database, not degraded service: size the number with that in mind.

- Size it from observed *failed* sign-ins on that auth database, not from peak successful traffic: a few times the 95th percentile of failed sign-ins in 5 minutes on a quiet day, with headroom for a legitimate outage in which people retry. Too low is an outage; too high lets stuffing run longer.
- The first trip logs once at Warning and writes the audit row `signin_ceiling_tripped`. That signal is often more useful than the `429`.
- The counter is in memory in each server process. N processes mean N times the ceiling; divide your number by the process count, or treat the product as the budget. There is no shared store.
- It covers `POST …/auth/signin` and `POST /api/auth/signin`. Sign-up, refresh, password reset and MFA verification are not covered: sign-in is where credentials are guessed.

The data plane has its own quota per identity (`429 IDENTITY_QUOTA_EXCEEDED`); see [defaults](../guides/defaults-reference.md).

## Testing

`AoudaTestServer` takes a `Declaration` and a derived key. `CreateClient(db, key)` sends that key. `CreateAnonymousClient(db)` sends none, which on the data plane is the `anonymous` principal. A throwaway server on a laptop is `aouda start --dev-admin`; the one stdout line is `AOUDA-DEV-ADMIN email=… password=… key=…`. The `key=` value is a stored key of the dev-admin principal, in the current format. Do not copy it into a page.
