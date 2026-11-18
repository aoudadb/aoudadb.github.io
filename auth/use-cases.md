---
title: "Use cases"
nav_order: 8
parent: "Auth and Authorization"
---

# Use cases (**BL-1464, next train**)

The routes below are the ones the server still has. A person in these flows is a principal; the admin path segment is `users/{id}` and `{id}` is the principal's id.

## Administer principals and roles

Use the access routes, not a second user directory. The caller needs `manage` on `<auth>/principal/*` or `<auth>/role/*`, and must cover every statement it grants. See [Grant only what you hold](authorization.md#grant-only-what-you-hold).

| You want | Call |
|---|---|
| Create a principal | `POST /api/auth/{authDatabase}/principals` `{ name, description?, roles?, statements?, attributes?, password? }` → `201`. `password` only when `name` is an email. |
| Change one | `PATCH …/principals/{name}`. A rename keeps the id. A refused rename changes nothing. |
| Disable one | `PATCH` with `{ "disabled": true }`. Open sessions end. |
| See its credentials | `GET …/principals/{name}/credentials`. No hash, no key, no root. |
| Give it a key | `POST …/principals/{name}/keys`. The key is in the response once. |
| Create a role | `POST …/roles`. The names `admin`, `writer` and `reader` are the built-ins and are read-only. |

The three built-ins, and what each holds, are [Roles](principals.md#roles). Prefer a role you declare when the built-in is wider than the caller needs.

Declared objects answer `409 DECLARED_IN_CONFIGURATION`. Change `aouda.json` and `aouda reload`.

## Password

The mechanics and the error codes are [Setup and flows](setup.md#password-reset). Short version, for a principal that forgot a password:

1. `POST /api/databases/{db}/auth/request-password-reset` `{ "email" }` → `{ "ok": true }` always.
2. The person submits the OTP to `POST …/auth/reset-password`.
3. Sessions minted before the reset no longer work.

An operator who already holds `manage` on that principal can `PUT /api/databases/{db}/admin/users/{id}/password` instead. That is the route whose path says `users`.

## Onboarding

1. Declare the auth database, the link, `signup` and the roles in `aouda.json`. Leave `signup.enabled` false until the statements are the ones you mean.
2. `aouda plan`, then start, or reload.
3. For a person an operator creates: `POST …/principals` with the email and `sendInvite` is not a field on that body. Set a password or call `POST …/admin/users/{id}/invite` so the reset OTP goes out.
4. The person signs in. `whoami` shows `source: runtime` or `signup`, and the statements `signup` or the roles resolve to.

## MFA

Enroll, challenge, verify, list, delete: [Setup and flows](setup.md#mfa). Enroll and delete need a session that is already `aal2` (`403 AUTH_MFA_STEP_UP_REQUIRED` otherwise). An operator turns MFA off for a principal by deleting the factor on `…/admin/users/{id}/mfa/factors/{factorId}`, which is how a test principal gets back to a password-only sign-in.
