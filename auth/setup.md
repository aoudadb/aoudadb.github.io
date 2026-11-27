---
title: "Setup and flows"
nav_order: 5
parent: "Auth and Authorization"
---

# Setup and flows (**BL-1464, 0.16.0**)

Sign-up, sign-in, sign-out, password reset and MFA. The model they sit on is [Principals](principals.md) and [Credentials](credentials.md). Creating the auth database and the link is [Declared databases](../guides/declared-databases.md).

## Enabling auth on a database

An application auth database is a database with `"kind": "auth"` in `aouda.json`. A data database names it with `"authDatabase": "<name>"`. That link is governance: the data database's principals are the auth database's principals. See [Auth databases](principals.md#auth-databases).

A data database with no link is governed by `_serverauth`. There is no second auth system beside that.

<!-- declaration-example -->
```json
{
  "version": 1,
  "databases": {
    "auth": { "kind": "auth", "signup": { "enabled": false } },
    "shop": { "kind": "data", "authDatabase": "auth", "schema": "schema/shop.aouda.schema.json" }
  }
}
```

## Sign-up

`POST /api/databases/{db}/auth/signup` with `{ "email", "password" }`. The governing auth database's `signup` must be enabled (`403 AUTH_SIGNUP_DISABLED` when it is not). The principal is created with `source: signup` and **no role of its own**. Its policy is the `signup` setting, resolved on each request.

Closing signup is not revoking. Principals that already exist keep the policy until you change `signup` or disable them.

## Sign-in and sign-out

`POST /api/databases/{db}/auth/signin` with `{ "email", "password" }`. Optional `databases`: a list that limits the session. Omit it and the session has no database limit.

The response is a token pair. When the principal has an active MFA factor the pair is `aal1` and the body includes `mfaRequired: true` and `mfaFactors`. With no active factor the pair is `aal2`. `requiresPasswordChange: true` is included only when it is true.

`POST /api/databases/{db}/auth/signout` ends **this** session: its refresh token and its access token stop working, and the principal's other devices stay signed in (**NativeClients, 0.4.0**). `{ "scope": "global" }` signs out everywhere (send `Content-Type: application/json`); `{ "scope": "others" }` signs every other device out and keeps this one. A principal lists its devices with `GET …/auth/sessions` and ends one with `DELETE …/auth/sessions/{id}`: [Sessions are devices](reference.md#sessions-are-devices). `POST …/auth/refresh` remints the access token at the same assurance level the session was minted with. It does not drop `aal2` to `aal1`.

A session token carries the session (`aud` is the database limit; omit `databases` on sign-in and it is `["*"]`). It does not carry a role list or a permission list. The server reads statements on each request.

`POST /api/auth/signin` is the same call for a `_serverauth` principal (an operator).

## Native apps: sign in through the browser

(**NativeClients, 0.4.0**) A desktop or phone app can sign its person in through the browser, where your web front is already signed in, MFA included, and get a session of its own at the same assurance level. Aouda serves no login page: your web front does the asking, Aouda issues a single-use code, and the app redeems it with a PKCE verifier. The routes, the redirect rules and every error code: [Native sign-in through the browser](reference.md#native-sign-in-through-the-browser).

**Once: register the app.** The caller is a key or session of a principal that holds `manage` on the auth database:

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/native-clients \
  -H "Authorization: Bearer $AOUDA_KEY" -H "Content-Type: application/json" \
  -d '{"name":"MyApp desktop","redirectUris":["http://127.0.0.1/callback","com.example.myapp:/oauth"]}'
```

The answer is `201` with the client's `id`: that is the `clientId` below.

**Desktop app: loopback redirect** (RFC 8252 §7.3). The app listens on `127.0.0.1` on any free port; the registered `http://127.0.0.1/callback` matches every port.

```typescript
import { AoudaClient, createPkcePair } from "@aouda/client";

// 1. In the desktop app: a PKCE pair, a loopback listener, and the browser opened on your web front.
const { codeVerifier, codeChallenge } = await createPkcePair();
const redirectUri = `http://127.0.0.1:${port}/callback`;
openBrowser(`https://app.example.com/native-sign-in?challenge=${codeChallenge}&redirect=${encodeURIComponent(redirectUri)}&state=${state}`);

// 2. In the web front (signed in): ask the person first (Aouda shows no consent screen, so this is where they see it),
//    then ask for the code and send the browser on.
if (!(await confirmDialog(`Sign in to MyApp on this device as ${user.email}?`))) return;
const { redirectTo } = await web.auth.createAuthorizationCode({ clientId, redirectUri, codeChallenge, state });
window.location.assign(redirectTo);   // -> http://127.0.0.1:<port>/callback?code=...&state=...

// 3. Back in the desktop app's listener: check `state`, then redeem within 60 seconds.
const app = new AoudaClient({ serverUrl, database: "myapp" });
app.auth.onTokensChanged((t) => secureStore.save(t));             // keep the rotated refresh token
await app.auth.exchangeCode({ code, codeVerifier, clientId, redirectUri, deviceInfo: "MyApp desktop on Ann's laptop" });
```

**Phone app: private-use scheme or claimed link** (RFC 8252 §7.1 and §7.2). Register `com.example.myapp:/oauth` (a reverse-DNS scheme the app owns) or an `https://` link the OS routes to the app (Universal Links, App Links). The flow is the same; the browser lands on the app instead of a loopback port. **A claimed `https` link is the stronger choice:** another app on the phone can register the same private-use scheme and receive the code, and with its own PKCE pair it could redeem it (RFC 8252 §8.6), while a claimed link reaches only your app. Either way the web front must ask the person before it calls `createAuthorizationCode` (step 2). On React Native, import `react-native-get-random-values` before `@aouda/client` so `createPkcePair()` has a random source ([React Native](../clients/typescript.md#react-native-nativeclients-040)).

C#: `Pkce.CreatePair()`, `client.Auth.CreateAuthorizationCodeAsync(...)`, `client.Auth.ExchangeCodeAsync(...)`.

The code is single use, valid for 60 seconds, bound to the client and the redirect URI, and dies with the web session that issued it. A second redemption is treated as theft: it is refused and the session the first redemption opened is ended. The new session has the web session's `aal` and its allowance, or the part of it `databases` names in the `createAuthorizationCode` request ([The token allowance](reference.md#the-token-allowance)).

## Password reset

`POST /api/databases/{db}/auth/request-password-reset` with `{ "email" }` always returns `{ "ok": true }`. `POST …/auth/reset-password` with `{ "email", "otp", "newPassword" }` sets the password, revokes sessions, and returns a token pair.

| Code | When |
|---|---|
| `AUTH_RESET_TOKEN_INVALID` | The OTP does not match. |
| `AUTH_RESET_TOKEN_EXPIRED` | The latest token has expired. |
| `AUTH_RESET_TOKEN_EXHAUSTED` | Too many attempts (default 5). At most five codes are compared, however many requests are in flight; a request that cannot reserve an attempt is answered EXHAUSTED or `409 WRITE_CONFLICT` and compared nothing, and a refused (`503`) use of a right code gives its attempt back. |

An operator sets a password with `PUT /api/databases/{db}/admin/users/{id}/password` (`{ "password", "forcePasswordChange"? }`), which is `204` and revokes that principal's sessions. `{id}` is the principal's id. `POST …/admin/users/{id}/invite` sends the reset OTP.

## MFA

| Method | Path | Who |
|---|---|---|
| `POST` | `/api/databases/{db}/auth/mfa/enroll` | The signed-in principal. Requires `aal2`, else `403 AUTH_MFA_STEP_UP_REQUIRED`. |
| `POST` | `…/mfa/challenge` | Starts a challenge. |
| `POST` | `…/mfa/verify` | On success, a new token pair at `aal2`. |
| `GET` | `…/mfa/factors` | The principal's factors. |
| `DELETE` | `…/mfa/factors/{id}` | Requires `aal2`. |

`aal2` means every second factor the principal has enrolled was completed. A principal with no factor is `aal2` at password sign-in, because there was nothing further to complete.

| Code | When |
|---|---|
| `AUTH_MFA_FACTOR_NOT_FOUND` | No such factor. |
| `AUTH_MFA_STEP_UP_REQUIRED` | Enroll or delete without `aal2`. |
| `AUTH_MFA_FACTOR_ALREADY_ENROLLED` | A phone factor already exists. |
| `AUTH_MFA_CHALLENGE_INVALID` | Wrong code. |
| `AUTH_MFA_CHALLENGE_EXPIRED` | The challenge expired. |
| `AUTH_MFA_CHALLENGE_EXHAUSTED` | Too many attempts, counted as for the reset token above. |

An operator enrolls a phone factor with `POST …/admin/users/{id}/mfa/enroll`.

Delivery of the OTP is [Notifications](notifications.md).

## Token lifetime

An access token lives 15 minutes and a refresh token 30 days. Refresh tokens rotate: a spent one presented again ends the whole session. Revocation of the session, the key, or the principal ends open sockets within one heartbeat. The matrix is [Revocation](credentials.md#revocation); the codes and timing are [Realtime: a revoked or expired credential](../reference/http-api.md#realtime-revoked-credential).

## What this page does not do

It does not mint a key. Rotation is [Stored keys](credentials.md#stored-keys): mint a new key, then delete the old one. It does not take a second token beside the bearer.
