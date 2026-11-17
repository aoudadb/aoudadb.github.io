---
title: "Setup and flows"
nav_order: 5
parent: "Auth and Authorization"
---

# Setup and flows (**BL-1464, next train**)

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

`POST /api/databases/{db}/auth/signout` revokes the session. `POST …/auth/refresh` remints the access token at the same assurance level the session was minted with. It does not drop `aal2` to `aal1`.

A session token carries the session. It does not carry a role list or a permission list. The server reads statements on each request.

`POST /api/auth/signin` is the same call for a `_serverauth` principal (an operator).

## Password reset

`POST /api/databases/{db}/auth/request-password-reset` with `{ "email" }` always returns `{ "ok": true }`. `POST …/auth/reset-password` with `{ "email", "otp", "newPassword" }` sets the password, revokes sessions, and returns a token pair.

| Code | When |
|---|---|
| `AUTH_RESET_TOKEN_INVALID` | The OTP does not match. |
| `AUTH_RESET_TOKEN_EXPIRED` | The latest token has expired. |
| `AUTH_RESET_TOKEN_EXHAUSTED` | Too many attempts (default 5). |

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
| `AUTH_MFA_CHALLENGE_EXHAUSTED` | Too many attempts. |

An operator enrolls a phone factor with `POST …/admin/users/{id}/mfa/enroll`.

Delivery of the OTP is [Notifications](notifications.md).

## Token lifetime

Access tokens are short. Refresh tokens rotate. Revocation of the session, the key, or the principal ends open sockets within one heartbeat. The matrix is [Revocation](credentials.md#revocation).

## What this page does not do

It does not mint a key. Rotation is [Stored keys](credentials.md#stored-keys): mint a new key, then delete the old one. It does not take a second token beside the bearer.
