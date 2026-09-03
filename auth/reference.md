---
title: "Reference"
nav_order: 6
parent: "Auth and Authorization"
---

# Auth Reference

> Part of the [Application Auth Guide](Getting-Started-Auth.md). Start there for an overview.

---

## 20. AI Agent Workflows

One of Aouda's key qualities is that AI agents can build and test complete application flows — from database setup to auth to data operations — with minimal friction.

### Level 0: Just a Database (Zero Auth)

```bash
aouda start --port 5433 --data-dir ./data
# Create database via API or appsettings — see setup.md

# Agent uses it immediately — zero setup
curl -X POST http://localhost:5433/api/databases/myapp/tables/orders/rows \
  -d '{ "rows": [{ "id": 1, "customer": "Acme", "total": 249.99 }] }'
```

### Level 1: Database with Auth (API setup)

```bash
aouda start --port 5433 --data-dir ./data
# Bootstrap server admin, then POST /api/databases with auth enabled — see setup.md §7
# Response includes: anonKey (mk_anon_...), publicKey (mk_pub_...), serviceRoleKey (mk_svc_...)
# mk_pub_* is data-plane only. OAuth code + PKCE is not shipped (BL-043).

# Agent captures keys and tests the complete flow:

# Sign up a user
curl -H "Authorization: Bearer mk_anon_a1b2c3..." \
  -X POST http://localhost:5433/api/databases/myapp/auth/signup \
  -d '{ "email": "testuser@example.com", "password": "Test123!" }'

# Use the returned JWT for data access
curl -X POST -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  http://localhost:5433/api/databases/myapp/query \
  -d '{ "database": "myapp", "table": "orders", "limit": 10 }'
```

### Level 2: Full Production Setup

```bash
# 1. Bootstrap server admin
curl -X POST http://localhost:5433/api/auth/setup \
  -d '{ "email": "admin@test.local", "password": "AdminPass123!" }'

# 2. Sign in
TOKEN=$(curl -s http://localhost:5433/api/auth/signin \
  -d '{ "email": "admin@test.local", "password": "AdminPass123!" }' | jq -r .accessToken)

# 3. Create auth-enabled database
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ "name": "myapp", "auth": { "enabled": true } }'

# 4. Create a scoped server API key
curl -X POST http://localhost:5433/api/auth/admin/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ "name": "myapp-backend", "databaseRoles": { "myapp": ["db_writer"] } }'

# 5. Test the complete flow
```

### Aouda as SaaS-Auth for AI Agent Apps

```bash
# Agent starts Aouda and enables auth on a database
aouda start --port 5433 --data-dir ./data
# Captures: ANON_KEY, SERVICE_KEY from POST /api/databases response

# Agent generates application code:
#   const db = createAoudaClient({
#     serverUrl: "http://localhost:5433",
#     database: "myapp",
#     appAuth: { apiKey: SERVICE_KEY }
#   });
#
#   app.post("/api/signup", async (req, res) => {
#     const result = await db.auth.signUp(req.body.email, req.body.password);
#     res.json(result);
#   });

# Agent tests end-to-end:
curl -X POST http://localhost:3000/api/signup \
  -d '{ "email": "alice@test.com", "password": "Test123!" }'
# → User created in Aouda, JWT returned

curl -X POST http://localhost:3000/api/login \
  -d '{ "email": "alice@test.com", "password": "Test123!" }'
# → JWT returned
```

Zero external dependencies, zero cloud signups, zero configuration files.

---

## 21. API Reference

> **OTP delivery:** Password reset, invite emails, and MFA SMS are sent by the **Aouda server** when notification providers are configured. See [Email, SMS & Notifications](notifications.md). Your consumer app only calls the HTTP endpoints below.

### Application Auth Endpoints

All endpoints under `/api/databases/{db}/auth/...`.

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `.../auth/signup` | POST | None (public POST; 403 `AUTH_SIGNUP_DISABLED` unless `allowSelfSignup`) | Register a new user |
| `.../auth/signin` | POST | API key (anon or higher) | Sign in, receive tokens |
| `.../auth/refresh` | POST | API key (anon or higher) | Refresh access token |
| `.../auth/signout` | POST | User JWT | Revoke session |
| `.../auth/me` | GET | User JWT | Get current user profile |
| `.../auth/me` | PATCH | User JWT | Update user metadata |
| `.../auth/password` | PUT | User JWT | Change password |
| `.../auth/request-password-reset` | POST | API key (anon or higher) | Request a 6-digit OTP emailed to the user; always returns 200 |
| `.../auth/reset-password` | POST | API key (anon or higher) | Submit OTP + new password; returns token pair on success |
| `.../auth/mfa/enroll` | POST | User JWT | Enrol a TOTP or phone MFA factor |
| `.../auth/mfa/challenge` | POST | User JWT | Create a challenge for an enrolled factor; sends SMS for phone factors |
| `.../auth/mfa/verify` | POST | User JWT | Submit OTP or TOTP code; returns new token pair with `aal2` on success |
| `.../auth/mfa/factors` | GET | User JWT | List enrolled MFA factors |
| `.../auth/mfa/factors/{id}` | DELETE | User JWT | Delete an enrolled MFA factor |

> **MFA endpoints require a user JWT** — the access token returned from sign-in. Send `Authorization: Bearer <accessToken>` directly; no API key is required or expected. If you are building a BFF that proxies MFA requests, forward the user JWT unchanged in `Authorization` — do not replace it with your service key. See [§14 — BFF / Gateway Proxying Auth Endpoints](client-integration.md#14-bff--gateway-proxying-auth-endpoints).

#### Optional Fields in `POST .../auth/signin` Response

The following fields are returned only when they apply. Consumers must handle their absence gracefully.

| Field | Type | When present | Notes |
|-------|------|-------------|-------|
| `requiresPasswordChange` | bool | Only when `true` | User must change their password before the app grants full access. User still receives a fully valid `aal1` JWT — the app is responsible for blocking access to protected areas until the password is changed. |
| `aal` | string | Only when user has enrolled MFA factors | `"aal1"` — password only. The full signin response also includes `mfaRequired` and `mfaFactors` when this field is present. |
| `mfaRequired` | bool | Only when user has enrolled active MFA factors | `true` — the app should prompt the user to complete an MFA challenge before granting access to sensitive areas. |
| `mfaFactors` | array | Only when user has enrolled active MFA factors | Short list of enrolled factors: `[{ "id": "...", "type": "totp"\|"phone", "phone": "+44***5678" (masked) }]`. **Use this list directly** — do not make a separate `GET .../auth/mfa/factors` call if `mfaFactors` is already present here. |

> **Consumers must handle missing fields gracefully.** When `requiresPasswordChange` is absent, the user's password status is normal. When `mfaRequired` is absent, the user has no enrolled MFA factors.
>
> **Do not call `GET .../auth/mfa/factors` after sign-in when `mfaFactors` is already present in the sign-in response.** The sign-in response is the canonical source — making an extra factors request is unnecessary and wastes a round-trip. The only time you need `GET .../auth/mfa/factors` is for factor management UIs (list/delete enrolled factors) outside of a sign-in flow.

Signin response with MFA factors enrolled:

```json
{
  "user": { "id": "550e8400-e29b-41d4-a716-446655440000", "email": "alice@example.com" },
  "accessToken":  "eyJ...",
  "refreshToken": "eyJ...",
  "expiresIn":    900,
  "aal":          "aal1",
  "mfaRequired":  true,
  "mfaFactors":   [{ "id": "a1b2c3d4-...", "type": "totp" }]
}
```

Signin response for a user with `forcePasswordChange` set:

```json
{
  "user": { "id": "550e8400-e29b-41d4-a716-446655440000", "email": "alice@example.com" },
  "accessToken":          "eyJ...",
  "refreshToken":         "eyJ...",
  "expiresIn":            900,
  "requiresPasswordChange": true
}
```

### Application Auth Admin Endpoints

All endpoints under `/api/databases/{db}/auth/admin/...`. Require `service_role` API key, `db_admin` user JWT, or server admin token.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `.../admin/users` | GET | List users (paginated, filterable) |
| `.../admin/users` | POST | Create a user — password optional; omit to create invite-pending account |
| `.../admin/users/{id}` | GET | Get user details |
| `.../admin/users/{id}` | PATCH | Update user |
| `.../admin/users/{id}` | DELETE | Delete user by id (204; 404 if missing). Cascades that user's roles, claims, grants, credentials, sessions, tokens, MFA, and API keys. Leaves `_audit_log`.|
| `.../admin/users/{id}/disable` | POST | Disable user |
| `.../admin/users/{id}/enable` | POST | Enable user |
| `.../admin/users/{id}/roles` | GET | List user's roles |
| `.../admin/users/{id}/roles` | PUT | Replace user's role assignments |
| `.../admin/users/{id}/claims` | GET | List custom claims minted onto the user's JWT |
| `.../admin/users/{id}/claims` | PUT | Replace custom claims (`{ "claims": { "tenant_id": "acme" } }`). Empty object clears. `AUTH_CLAIM_INVALID` on a blank key |
| `.../admin/roles` | GET | List roles |
| `.../admin/roles` | POST | Create custom role |
| `.../admin/roles/{id}` | PATCH | Update role |
| `.../admin/roles/{id}` | DELETE | Delete custom role |
| `.../admin/api-keys` | GET | List API keys |
| `.../admin/api-keys` | POST | Create custom API key |
| `.../admin/api-keys/{id}` | DELETE | Revoke API key |
| `.../admin/regenerate-keys` | POST | Regenerate auto-generated keys |
| `.../admin/signup-settings` | GET/PUT | Read/write self-service signup (`allowSelfSignup`, `selfSignupRole`; null role → `db_writer`) |
| `.../admin/users/{id}/password` | PUT | Admin override of a user's password — no current-password check; optionally set `forcePasswordChange` |
| `.../admin/users/{id}/invite` | POST | (Re-)send an invite email with OTP to set a password; invalidates previous unused tokens |
| `.../admin/users/{id}/mfa/enroll` | POST | Admin enrols a phone MFA factor on behalf of a user |

#### Response Bodies

**`GET .../admin/users`** — Query parameters: `limit` (default 20, max 100), `offset`, `email`, `status`.

```json
{
  "users": [
    {
      "id":        "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "email":     "alice@example.com",
      "status":    "active",
      "createdAt": "2026-01-15T10:30:00Z"
    }
  ],
  "totalCount": 42
}
```

Email is unique per auth database (normalized: trim + lower-case). Duplicate `_users` rows for the same email are an operator-repair case via `DELETE .../admin/users/{id}`, not a supported sign-in mode.

**`POST .../admin/users`** — Returns `201 Created` on success, `409 Conflict` if email already exists.

Request fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `email` | string | Yes | |
| `password` | string? | No | Omit to create an invite-pending account |
| `displayName` | string? | No | |
| `forcePasswordChange` | bool? | No | If `true`, user must change password before the app grants full access. Next signin returns `"requiresPasswordChange": true`. |
| `sendInviteEmail` | bool? | No | If `true`, generates a 6-digit OTP and emails it to the user so they can set their password via `POST .../auth/reset-password`. Requires a configured email provider on the server (`sendgrid` or `console`) — see [notifications.md](notifications.md). Independent of `password` — can be combined. |

Three user-creation patterns:

| Pattern | Request | When to use |
|---------|---------|-------------|
| **Invite-pending + email invite** (recommended) | `password` omitted (invite-pending); invite email sent automatically | User sets their own password by OTP. Cannot sign in until they do. Preferred for multi-tenant SaaS onboarding. Set `sendInviteEmail: false` to skip the email. |
| **Forced initial password** | `password: "<initial>", forcePasswordChange: true` | User can sign in once but immediately receives `"requiresPasswordChange": true`; app must redirect to change-password page before granting access. Use for batch migrations. |
| **Direct password set** | `password: "<value>"` (no flags) | User can sign in immediately. No email sent unless you also call `POST .../admin/users/{id}/invite`. Use for internal tooling and test accounts. |

> The `sendInviteEmail` and `forcePasswordChange` flags are independent. Combining both sends an invite email *and* marks the account to require a password change after the OTP flow completes — useful for deliberate forced-reset onboarding.

```json
{
  "id":          "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email":       "alice@example.com",
  "displayName": "Alice",
  "createdAt":   "2026-01-15T10:30:00Z",
  "passwordSet": false
}
```

**`GET .../admin/users/{id}`** — Returns full user details including current role assignments.

```json
{
  "id":        "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email":     "alice@example.com",
  "status":    "active",
  "createdAt": "2026-01-15T10:30:00Z",
  "updatedAt": "2026-01-15T10:30:00Z",
  "roles": [
    { "roleName": "derive_admin", "scope": null }
  ]
}
```

`PUT .../admin/users/{id}/roles` is a full-replacement operation. Send the complete desired role list using:
`{ "roles": [ { "roleName": "db_reader", "scope": "mydb" } ] }`.
To add a single role without dropping existing roles, first `GET` current roles, merge client-side, then `PUT` the merged list.
`POST .../admin/users/{id}/roles` is not supported and returns `405 Method Not Allowed`.

**`GET .../admin/users/{id}/roles`** — Returns current role assignments for the user.

```json
{
  "roles": [
    { "roleName": "derive_admin", "scope": null },
    { "roleName": "db_reader",    "scope": "analytics" }
  ]
}
```

`scope` is `null` for globally assigned roles (the common case), or an explicit string for scoped assignments.

**`GET`/`PUT .../admin/users/{id}/claims`** — Custom claims minted onto access tokens (and refresh). `PUT` is a full replacement: `{ "claims": { "tenant_id": "acme" } }`. `{}` clears. Invalid keys return `AUTH_CLAIM_INVALID`. Users cannot set claims on `PATCH /auth/me`.

**`GET .../admin/roles`** — Returns all roles defined for the database.

```json
{
  "roles": [
    {
      "id":          "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name":        "derive_admin",
      "description": null,
      "isSystem":    false,
      "createdAt":   "2026-01-15T10:30:00Z",
      "permissions": [
        { "resourceType": "table", "resourceName": "*", "actions": "read" }
      ]
    }
  ]
}
```

`actions` is a **comma-separated string** (`"read"`, `"read,write"`), not a JSON array.

**`POST .../admin/roles`** — Create a custom role. Returns `201 Created`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | **Yes** | Unique role name. |
| `description` | string | No | |
| `permissions` | array | No | Omit or `[]` creates a role that grants nothing. Each item: `resourceType` (default `"table"`), `resourceName` (default `"*"`), `actions` (**string**, e.g. `"read"` or `"read,write"`). |

```json
{
  "name": "order_processor",
  "description": "Read/write orders",
  "permissions": [
    { "resourceType": "table", "resourceName": "orders", "actions": "read,write" },
    { "resourceType": "table", "resourceName": "products", "actions": "read" }
  ]
}
```

**400 `INVALID_REQUEST`:** missing `name`, duplicate name, or malformed JSON. Body is `{ "error", "message", "suggestion", "requestId" }` — log it. `permissions` is not required.

**`GET .../admin/users/{id}/partition-grants`** — Returns ADRA partition grants for the user. Optional query parameter `?dimension=` filters by dimension name.

```json
{
  "grants": [
    {
      "id":           "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "userId":       "...",
      "dimension":    "client",
      "partitionKey": "123",
      "accessLevel":  "read",
      "grantedBy":    null,
      "validFrom":    null,
      "validTo":      null,
      "createdAt":    "2026-01-15T10:30:00Z"
    }
  ]
}
```

> **All list responses are wrapped objects, never bare arrays.** Every `GET` list endpoint returns `{ "<resource>": [...] }` or `{ "<resource>": [...], "totalCount": N }`. Deserializing a list response as a plain array will throw a `JsonException`.

### ADRA Admin Endpoints

All endpoints under `/api/databases/{db}/auth/admin/...`. Require `service_role` API key, `db_admin` user JWT, or server admin token.

**Partition Grants** — manage which partition keys a user is allowed to access in each dimension ([§19.8](Auth-Data-Authorization.md#198-admin-api-partition-grants)):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `.../admin/users/{userId}/partition-grants` | POST | Create a partition grant (returns 201) |
| `.../admin/users/{userId}/partition-grants` | GET | List grants for user; optional `?dimension=` filter |
| `.../admin/users/{userId}/partition-grants/{grantId}` | DELETE | Delete a grant (204 / 404) |

**RLS Resolvers** — define within-partition row filter rules ([§19.9](Auth-Data-Authorization.md#199-admin-api-rls-resolvers)):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `.../admin/rls-resolvers` | POST | Create a resolver with `rules` and optional `writeCheckRules` (returns 201). `valueConfig` is a string. Value sources: `UserId`, `Literal`, `PartitionGrant` |
| `.../admin/rls-resolvers` | GET | List resolvers; optional `?targetTable=` filter |
| `.../admin/rls-resolvers/{id}` | GET | Get resolver with full rules list |
| `.../admin/rls-resolvers/{id}` | PATCH | Update resolver description and/or replace rules |
| `.../admin/rls-resolvers/{id}` | DELETE | Delete resolver and all its rules (204 / 404) |

---

## 22. Error Handling

### Authentication & Token Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_TOKEN_MISSING` | 401 | No `Authorization` header on a protected endpoint | Add `Authorization: Bearer <token>` header |
| `AUTH_TOKEN_INVALID` | 401 | Token is malformed or has an invalid signature | Discard token; force re-sign-in |
| `AUTH_TOKEN_EXPIRED` | 401 | Access token has expired | Use refresh token to get a new access token |
| `AUTH_TOKEN_REVOKED` | 401 | Token was revoked (session signed out) | Redirect to sign-in |
| `AUTH_API_KEY_REQUIRED` | 401 | Historical: public app-auth POSTs required an API key. Those routes are now keyless and no longer return this code. If you still see it, you are talking to a pre-BL-355 server. Post-sign-in endpoints (`me`, `signout`, `mfa/*`, `password`) return `AUTH_TOKEN_MISSING` when no JWT is sent. |
| `AUTH_API_KEY_INVALID` | 401 | API key is invalid, revoked, or expired | Regenerate via the admin regenerate-keys endpoint |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | Refresh token is expired, revoked, or reused (theft detected) | Redirect to sign-in; entire token family is invalidated |
| `UNAUTHORIZED` | 401 | Unrecognised path when server auth is configured (deny-by-default) | Ensure request targets a valid path with a valid credential |

### Signup / Signin Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_INVALID_CREDENTIALS` | 401 | Wrong email or password | Show "Invalid credentials" |
| `AUTH_ACCOUNT_LOCKED` | 423 | Too many failed attempts (default: 10) | Wait for the lockout window (default: 15 min) or re-enable via admin |
| `AUTH_ACCOUNT_DISABLED` | 423 | Account disabled by an administrator | Re-enable via `POST .../admin/users/{id}/enable` |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | Email already registered | Show "Account exists" |
| `AUTH_SIGNUP_FAILED` | 400 | Signup could not be completed (generic; prevents info leakage) | Check server logs; try again |
| `AUTH_SIGNUP_DISABLED` | 403 | Self-service registration is off for this database | Enable via `PUT …/admin/signup-settings` |
| `AUTH_INVALID_EMAIL` | 400 | Email is blank or not a valid email format | Prompt the user to correct the email field |
| `AUTH_PASSWORD_TOO_WEAK` | 400 | Password does not meet the minimum policy (default: 8 chars) | Prompt the user to choose a stronger password |
| `AUTH_RATE_LIMITED` | 429 | Too many auth requests | Implement exponential backoff |

### Password Reset Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_RESET_TOKEN_INVALID` | 400 | OTP is wrong, email is not registered, or no valid reset token exists | Show a generic "Invalid or expired code" message; do not indicate whether the email exists |
| `AUTH_RESET_TOKEN_EXPIRED` | 400 | OTP was correct but the 15-minute window has passed | Ask the user to request a new reset code |
| `AUTH_RESET_TOKEN_EXHAUSTED` | 400 | Five consecutive wrong OTP attempts on the same token; token is now permanently invalid | Ask the user to request a new reset code |

### MFA Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_MFA_FACTOR_NOT_FOUND` | 404 | MFA factor ID does not exist or belongs to another user | Verify the `factorId`; re-fetch factor list via `GET .../auth/mfa/factors` |
| `AUTH_MFA_CHALLENGE_INVALID` | 400 | Code is wrong, challenge ID is not found, or challenge belongs to another user | Show "Invalid code"; prompt user to try again or re-request a challenge |
| `AUTH_MFA_CHALLENGE_EXPIRED` | 400 | Challenge window has passed (10 minutes for both TOTP and phone) | Call `POST .../auth/mfa/challenge` again to create a fresh challenge |
| `AUTH_MFA_CHALLENGE_EXHAUSTED` | 400 | Five consecutive wrong codes on the same challenge; challenge is permanently invalid | Call `POST .../auth/mfa/challenge` again to create a fresh challenge |

### Authorization Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTHORIZATION_DENIED` | 403 | Valid token but the caller has no role for this database | Check role assignments via admin API |
| `INSUFFICIENT_PERMISSIONS` | 403 | Valid token but the role does not grant this operation | Assign an appropriate role |
| `NOT_AUTHENTICATED` | 401 | No authenticated principal for a protected resource | Send a valid bearer token |

### Partition-Level Security (PLS) Errors

These are returned for `jwt-claim` and `auth-db-pls` table enforcement.

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_PLS_TENANT_CLAIM_MISSING` | 403 | JWT has no `tenant_id` claim for a `jwt-claim` PLS table | Ensure JWT includes the `tenant_id` claim |
| `AUTH_PLS_TENANT_CLAIM_MISMATCH` | 403 | Explicit partition filter does not match the JWT `tenant_id` | Match the filter to the user's `tenant_id` claim |
| `AUTH_PLS_WRITE_SCOPE_VIOLATION` | 403 | Write targets a partition outside the caller's `tenant_id` | Write to the caller's own partition only |
| `AUTH_PLS_GRANT_NOT_FOUND` | 403 | Partition not in the user's grant set (`auth-db-pls`) | Create a partition grant for the user via admin API |
| `AUTH_PLS_GRANT_INSUFFICIENT_ACCESS` | 403 | Partition is granted but `access_level` is `read` (write attempted) | Update the grant to `access_level: "write"` or `"admin"` |
| `AUTH_PLS_UNSUPPORTED_OR_SHAPE` | 403 | `Where.Or` predicate mixes partition and non-partition conditions in a fan-out query | Move non-partition conditions to `Where.And` |

### Row-Level Security (RLS) Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_RLS_INSERT_VIOLATION` | 403 | Inserted row does not satisfy the resolved RLS predicate | Insert a row whose fields fall within the user's RLS scope |
| `AUTH_RLS_UPDATE_SET_VIOLATION` | 403 | UPDATE `SET` values would move the row outside the RLS predicate scope | Update only fields that keep the row visible to the user |

### ADRA Partition Grant Admin Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_GRANT_NOT_FOUND` | 404 | Grant ID not found | Verify the `grantId` in the DELETE request |
| `AUTH_GRANT_DUPLICATE` | 409 | Grant already exists for this user/dimension/partition | Reuse the existing grant or delete and recreate |
| `AUTH_GRANT_INVALID` | 400 | Grant request has missing or invalid fields | Check that `dimension`, `partitionKey`, and `accessLevel` are all present |

### ADRA RLS Resolver Admin Errors

| Error Code | HTTP | Meaning | Action |
|------------|------|---------|--------|
| `AUTH_RESOLVER_NOT_FOUND` | 404 | Resolver ID not found | Verify the `resolverId` in the request |
| `AUTH_RESOLVER_NAME_CONFLICT` | 409 | A resolver with the same name already exists for the target table | Choose a unique resolver name |
| `AUTH_RESOLVER_INVALID` | 400 | Resolver request has missing or invalid fields | Check that `name`, `targetTable`, and `resolverType` are present |
| `AUTH_CLAIM_INVALID` | 400 | Custom claim key is blank or invalid | Use a non-empty claim name; `PUT …/users/{id}/claims` |

### Handle by Error Code

```typescript
try {
  await client.auth.signIn(email, password);
} catch (err) {
  if (err instanceof AoudaAuthenticationError) {
    switch (err.code) {
      case "AUTH_INVALID_CREDENTIALS":
        showError("Invalid email or password");
        break;
      case "AUTH_ACCOUNT_LOCKED":
        showError("Account locked. Try again later.");
        break;
      case "AUTH_API_KEY_REQUIRED":
        showError("Configuration error: API key missing");
        break;
      default:
        showError("Authentication failed");
    }
  }
}
```

---

## 23. Security Best Practices

### Password Security

- Aouda uses **Argon2id** for password hashing (OWASP recommended, NIST SP 800-63B compliant).
- Default minimum password length: 8 characters.
- Account lockout after 10 failed attempts (15-minute lockout).
- Passwords are never stored, logged, or returned in API responses.

### API Key Security

- **`anon` keys** (`mk_anon_`) are safe to embed in frontend code — they grant limited access only.
- **`service_role` keys** (`mk_svc_`) must be kept secret — they grant full database access.
- **Server keys** (`mk_srv_`) must be kept secret and stored in environment variables.
- Auto-generated keys are shown only once at creation time. Store them securely.
- Rotate keys periodically via the regeneration endpoint.

### Token Security

- Store access tokens in memory (not localStorage) when possible.
- Store refresh tokens in secure, httpOnly cookies or secure storage.
- Use short access token lifetimes (15 minutes default).

### Transport Security

- **Always use HTTPS** in production.
- HTTP is acceptable only in local development.

### Rate Limiting

Default rate limits for auth endpoints:
- Sign-in: 20 attempts per minute per IP
- Sign-up: 5 attempts per minute per IP

Those per-IP limits (and per-account lockout, 10 failures / 15 minutes) cannot see a credential-stuffing campaign that tries one password against many accounts from many addresses. Each account sees one failure; each IP sees one request; nothing reaches a threshold.

An optional **failed-signin ceiling** (`Aouda:Auth:FailedSigninCeiling`) is the aggregate control for that shape. It is **off by default**. When enabled, failed sign-ins against one auth database are counted in a sliding window; successful sign-ins do not consume the budget. When the ceiling is exceeded, further sign-in attempts against that database return **429** `AUTH_RATE_LIMITED` with `Retry-After` until the window drains — including before Argon2 runs, so a tripped ceiling cannot be used to drive accounts into lockout.

**A tripped ceiling blocks every sign-in on that database**, including callers who type the correct password, until the window drains. Successful logins stay free of the budget only *until* the trip point; after that the database is a full login outage, not degraded service. Size the number with that failure mode in mind.

| Setting | Default | Notes |
|---------|---------|-------|
| `Aouda:Auth:FailedSigninCeiling:Enabled` | `false` | Operator must opt in |
| `Aouda:Auth:FailedSigninCeiling:PermitLimit` | `100` | Failed attempts per window per auth database |
| `Aouda:Auth:FailedSigninCeiling:WindowSeconds` | `300` | 5 minutes |

**How to pick a number.** Size it from observed *failed* login volume on that auth database, not peak successful traffic. A starting point is a few times the 95th-percentile failed-signin count in a 5-minute window on a quiet day, with headroom for a legitimate outage (users retrying). Too low is a **full login outage** for that database (correct passwords included) until the window drains; too high lets stuffing run longer. The first trip logs once at Warning and writes `_audit_log` action `signin_ceiling_tripped` — that signal is often more useful than the 429 itself.

**Per process.** The counter is in-memory on each server process. N nodes means N × the ceiling. Divide your chosen number by the process count, or treat the product as the cluster-wide budget. There is no shared store.

Signup, refresh, password-reset, and MFA verification are not covered. Sign-in is where credentials are guessed.

### Audit Logging

All auth events are logged to the `_audit_log` table: sign-up, sign-in, sign-out, failed attempts, password changes, role changes, admin actions, and `signin_ceiling_tripped` when the optional failed-signin ceiling first fires.

---

## 24. Validating Aouda JWTs in Your Backend

Aouda Application Auth exposes standard OIDC Discovery and JWKS endpoints so any JWT validation library can verify Aouda-issued tokens with no manual key management — the same way you would configure Auth0, Keycloak, or Supabase. **One important difference:** the discovery document path is non-standard (see the note under Discovery Endpoints below). You must set `MetadataAddress` explicitly in any library that builds the discovery URL from an authority base.

> **Gateway / reverse proxy deployments** — In production, Aouda is often not exposed directly to the internet. It runs behind an API gateway or reverse proxy (nginx, Kong, ASP.NET Core gateway, etc.) that forwards requests to the internal Aouda server. In these deployments, consuming services point at the **gateway's public URL**, not the internal Aouda address.
>
> Set `Aouda:BaseUrl = "https://api.your-domain.com"` in server configuration. Aouda will use this value for the `iss` claim in all JWTs and for every URI in the OIDC discovery document. Consuming services then configure their JWT validation to point at `https://api.your-domain.com/api/databases/{db}` — they never need to know the internal Aouda address.
>
> In the examples below, `https://your-aouda-server.com` represents this public-facing base URL, whether it is Aouda directly or a gateway in front of it.

### Discovery Endpoints

| Endpoint | URL |
|----------|-----|
| OIDC Discovery | `GET /api/databases/{db}/auth/.well-known/openid-configuration` |
| JWKS (public keys) | `GET /api/databases/{db}/auth/.well-known/jwks.json` |

Both endpoints are **publicly accessible** — no API key or JWT required. The discovery document contains the `issuer` value, which matches the `iss` claim in all new JWTs for that database.

> **Non-standard discovery path — read before using `AddJwtBearer`.**
> The OIDC discovery document is served at `…/auth/.well-known/openid-configuration`, which is one path segment deeper than the OIDC convention of `{issuer}/.well-known/openid-configuration`. Because the `issuer` is `{base_url}/api/databases/{db}`, any library that auto-constructs the metadata URL from `Authority` alone will try the wrong path and get a 404, causing JWT validation to fail on every request.
>
> **Always set `MetadataAddress` explicitly** (see the code examples below). Do not rely on automatic URL derivation from `Authority`.

### JWT Claims

| Claim | Value |
|-------|-------|
| `iss` | `{base_url}/api/databases/{db}` |
| `aud` | auth database name |
| `sub` | user ID (UUID) |
| `email` | user email |
| `iat` | issued-at timestamp |
| `exp` | expiry timestamp |
| `db_roles` | Native JSON object — role map keyed by scope (see below) |
| `aal` | Authentication Assurance Level: `"aal1"` (password-only signin) or `"aal2"` (MFA-verified). Present on all tokens minted by Aouda AppAuth. |

### 24.1 — The `aal` Claim: Enforcing MFA Gates

`aal1` means the user authenticated with password only. `aal2` means the user completed a successful MFA challenge after signin. A user with enrolled MFA factors will always receive `aal1` at signin; they must call `POST .../auth/mfa/challenge` then `POST .../auth/mfa/verify` to receive an `aal2` token.

**MFA gate enforcement — ASP.NET Core (C#):**

```csharp
// Require aal2 for a sensitive endpoint (e.g. exporting all customer data)
app.MapGet("/api/sensitive-export", (ClaimsPrincipal user) =>
{
    var aal = user.FindFirstValue("aal");
    if (!string.Equals(aal, "aal2", StringComparison.Ordinal))
        return Results.Json(new { error = "MFA_REQUIRED" }, statusCode: 403);

    // ... handle sensitive operation
    return Results.Ok();
}).RequireAuthorization();
```

**MFA gate enforcement — TypeScript / Node.js (jose):**

```typescript
async function requireAal2(req: Request, res: Response, next: NextFunction) {
  const payload = await verifyAoudaToken(req.headers.authorization?.replace("Bearer ", "") ?? "");
  if (payload["aal"] !== "aal2") {
    return res.status(403).json({ error: "MFA_REQUIRED" });
  }
  next();
}

// Apply to sensitive routes:
router.get("/sensitive-export", requireAal2, handleSensitiveExport);
```

> **Do not store the `aal` claim in the database.** The `aal` claim is valid only for the lifetime of the access token (15 minutes). Do not cache it as a user property — always read it from the JWT on each request. `aal2` tokens are short-lived by design.

### The `db_roles` Claim

The `db_roles` claim is a **native JWT JSON object** — not a double-encoded string.
JWT libraries surface it as a typed object; no `JSON.parse()` call is needed.

The object is a map keyed by **scope**, with each value being an **array of role name strings**
(always an array, even for a single role):

| Key | When used |
|-----|-----------|
| Auth database name (e.g. `"_auth"`) | Roles assigned to the user **without** an explicit scope (the default). The key is the auth database name — it is environment-specific and **must not be hardcoded**. |
| Explicit scope string (e.g. `"derive"`) | Roles assigned with an explicit scope via the admin `PUT .../users/{id}/roles` endpoint. |
| `"*"` | Roles assigned with a wildcard scope (applies to all databases). |

**Canonical wire format** (database named `_auth`, role `derive_admin` assigned without scope;
role `app_derive_connect` assigned with explicit scope `"derive"`):

```json
{
  "db_roles": {
    "_auth": ["derive_admin"],
    "derive": ["app_derive_connect"]
  }
}
```

The `"_auth"` key is the **auth database name**, not the application database name. If your auth database is named `auth`, the key is `"auth"`. Check the name returned when you created the auth database (see [setup.md](setup.md) §7).

> Roles are always arrays. If a user has one role in a scope, the value is still `["role_name"]`.

**Reading roles — TypeScript / JavaScript:**

```typescript
// db_roles is a native object — no JSON.parse() needed.
interface DbRoles { [scope: string]: string[] }

function hasRole(payload: { db_roles?: DbRoles }, roleName: string): boolean {
  if (!payload.db_roles) return false;
  return Object.values(payload.db_roles).flat().some(r => r === roleName);
}

// Check a role in a specific scope:
function hasRoleInScope(payload: { db_roles?: DbRoles }, scope: string, roleName: string): boolean {
  return payload.db_roles?.[scope]?.includes(roleName) ?? false;
}
```

**Reading roles — C\# (via `ClaimsPrincipal`):**

When ASP.NET Core JWT Bearer middleware validates an Aouda token, it converts the native
JWT object claim to a JSON string stored in `Claim.Value`. Read it with `FindFirstValue` and
deserialize — no double-parsing required:

```csharp
bool HasRole(ClaimsPrincipal user, string roleName)
{
    var raw = user.FindFirstValue("db_roles"); // JSON string of the object
    if (string.IsNullOrEmpty(raw)) return false;
    try
    {
        var map = JsonSerializer.Deserialize<Dictionary<string, List<string>>>(raw);
        return map?.Values.SelectMany(v => v)
                   .Any(r => string.Equals(r, roleName, StringComparison.OrdinalIgnoreCase))
               ?? false;
    }
    catch (JsonException) { return false; }
}
```

To check a role in a **specific scope**:

```csharp
if (map.TryGetValue("derive", out var scopedRoles) && scopedRoles.Contains("app_derive_connect"))
    // ...
```

**Common mistakes:**

| Mistake | Why it fails |
|---------|-------------|
| `dbRoles?.derive` — hardcoded scope key | The null-scope key is the auth database name (e.g. `"_auth"`). Use an explicit scope (`PUT .../users/{id}/roles` with `"scope": "derive"`) to get a predictable key like `"derive"`. |
| Calling `JSON.parse(dbRoles)` | `db_roles` is already a native JSON object in the JWT — no extra parsing needed. Calling `JSON.parse()` on an object throws or returns unexpected results. |
| Expecting a string value per scope | Values are always arrays (`string[]`), even for a single role. |
| Checking only under the auth DB key | Scoped roles use a different key. Iterate all values for a flat role check. |

---

### ASP.NET Core

Use `AddJwtBearer` with the OIDC `Authority` and `MetadataAddress`. The middleware fetches the JWKS and validates signatures, issuer, and expiry.

> **`MetadataAddress` is required.** Aouda's discovery document is at `{authority}/auth/.well-known/openid-configuration`, not the conventional `{authority}/.well-known/openid-configuration`. If you set only `Authority`, ASP.NET Core constructs the wrong URL, the JWKS fetch fails silently at startup, and every request returns 401. Always provide `MetadataAddress` explicitly.

```csharp
builder.Services.AddAuthentication().AddJwtBearer(options =>
{
    var aoudaBase = "https://your-aouda-server.com";
    var db        = "mydb";  // the application database name
    var issuer    = $"{aoudaBase}/api/databases/{db}";

    // Required: discovery path has an extra /auth/ segment — auto-derivation from Authority is wrong.
    options.MetadataAddress = $"{issuer}/auth/.well-known/openid-configuration";

    // Authority is still used for issuer validation in incoming tokens.
    options.Authority = issuer;
    options.Audience  = "mydb_auth";  // the auth database name

    // If your Aouda server uses HTTP (local dev only):
    // options.RequireHttpsMetadata = false;
});
```

Then protect your endpoints normally:

```csharp
app.MapGet("/protected", (ClaimsPrincipal user) =>
    Results.Ok(new { email = user.FindFirst("email")?.Value }))
    .RequireAuthorization();
```

---

### Node.js / Express (jose)

```js
import { createRemoteJWKSet, jwtVerify } from 'jose';

const JWKS = createRemoteJWKSet(
    new URL('https://your-aouda-server.com/api/databases/mydb/auth/.well-known/jwks.json')
);

async function verifyAoudaToken(token) {
    const { payload } = await jwtVerify(token, JWKS, {
        issuer:   'https://your-aouda-server.com/api/databases/mydb',
        audience: 'mydb_auth',
    });
    // payload.db_roles is a native object: { "_auth": ["db_admin"], "derive": ["app_derive_connect"] }
    return payload;
}
```

---

### Spring Boot (Java)

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://your-aouda-server.com/api/databases/mydb
```

Spring Security auto-discovers the JWKS from the OIDC discovery endpoint.

---

### Go (golang-jwt + lestrrat-go/jwx)

```go
import (
    "github.com/lestrrat-go/jwx/v2/jwk"
    "github.com/lestrrat-go/jwx/v2/jwt"
)

cache := jwk.NewCache(ctx)
cache.Register("https://your-aouda-server.com/api/databases/mydb/auth/.well-known/jwks.json")

func verifyToken(tokenStr string) (jwt.Token, error) {
    keySet, _ := cache.Get(ctx, "https://your-aouda-server.com/api/databases/mydb/auth/.well-known/jwks.json")
    return jwt.Parse([]byte(tokenStr), jwt.WithKeySet(keySet),
        jwt.WithValidate(true),
        jwt.WithIssuer("https://your-aouda-server.com/api/databases/mydb"),
        jwt.WithAudience("mydb_auth"))
}
```

---

### Python (PyJWT + requests)

```python
import requests
import jwt
from jwt import PyJWKClient

JWKS_URL = "https://your-aouda-server.com/api/databases/mydb/auth/.well-known/jwks.json"
ISSUER   = "https://your-aouda-server.com/api/databases/mydb"
AUDIENCE = "mydb_auth"

jwks_client = PyJWKClient(JWKS_URL)

def verify_token(token: str) -> dict:
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=AUDIENCE,
        issuer=ISSUER,
    )
```

---

### Key Points

- **No shared secrets** — validation uses only the RSA public keys from the JWKS endpoint.
- **Key rotation is transparent** — the JWKS endpoint always returns all current and rotated keys. Old tokens remain valid until expiry.
- **JWKS is cached** — the response includes `Cache-Control: public, max-age=3600`. Most JWT libraries handle caching automatically.
- **Discovery is cached** — the OIDC configuration response includes `Cache-Control: public, max-age=86400`.

---

## 25. Testing Applications That Use Aouda Auth

Application Auth is implemented in the **Aouda HTTP server** — OIDC discovery, JWKS, signup, signin, and JWT issuance are not available through `Aouda.Embedded`. That means **integration tests** that exercise real auth flows need either a running server (`aouda start`) or an **in-process** server inside the test process (for example `Aouda.Testing` / `DevServerHost` in tests).

The **`Aouda.Testing`** NuGet package starts a full Aouda server backed by ASP.NET Core `TestHost` (no real ports, no external process). It exposes API keys, OIDC authority URLs, and fast engine-direct helpers (`CreateUserAsync`, `SignInAsync`) for test setup. See the full guide: **[Getting-Started-Testing.md](Getting-Started-Testing.md)** ([ADR 0024](../decisions/0024-testing-package.md)).

For **unit tests** of your own business logic, mocking auth clients or tokens remains appropriate — use `Aouda.Testing` when you need **end-to-end** behavior against the real Aouda auth stack.

---

## 26. Comparison with Other Auth Services

### 26.1 Auth Service Comparison

| Aspect | Firebase Auth | Supabase Auth | Auth0 / Clerk | **Aouda App Auth** |
|--------|-------------|---------------|---------------|-------------------|
| **Architecture** | Google-hosted | GoTrue + Postgres + Redis + Kong | External SaaS | Built into the database engine |
| **Session store** | Google infra | Redis (separate system) | External | In-memory session cache (no Redis needed) |
| **Self-hostable** | No | Yes (complex: 6+ services) | No | Yes (single binary) |
| **Setup** | Dashboard + SDK | Dashboard + RLS + SDK | Dashboard + SDK + webhooks | **One API call** |
| **Data co-location** | Outside your DB | Same Postgres | Outside your DB | **Same system, separate DB** |
| **Latency** | Network hop | Postgres + Redis | Network hop | **Memory-first** (~0.1ms) |
| **Vendor lock-in** | High | Medium | High | **None** (standard JWTs) |
| **AI agent setup** | 10+ steps | 5+ steps | 8+ steps | **1 command** |
| **Two-layer model** | API key + user JWT | anon/service_role + user JWT | N/A | **anon/service_role + user JWT** |

**Why Aouda's approach is different:** Traditional auth services create an architectural boundary between your data and your identity. Aouda eliminates this — identity and data live in the same engine (though in separate databases for clean lifecycle management). The session cache is in-memory, sessions don't need Redis, and the operational model is identical to managing any other database.

Like Supabase, auto-generated `anon` and `service_role` keys on database creation mean **the secure path is the default path**.

---

### 26.2 ADRA vs Supabase RLS — Performance and Architecture

Supabase Row-Level Security (RLS) uses PostgreSQL policy expressions evaluated **per-row at query time**. Aouda ADRA (`auth-db-rls`) resolves a predicate **once** and injects it as a WHERE clause. This difference in architecture leads to very different performance and operational characteristics.

#### The PostgreSQL Per-Row Model

```
Supabase RLS (PostgreSQL):

  Policy:  auth.uid() = owner_id

  Query:   SELECT * FROM sales WHERE company_id = 'acme'
           (returns 1,000,000 rows before policy filter)

  Evaluation: policy function called 1,000,000 times
              → even a simple uid() lookup is called per-row
              → overhead scales linearly with result set size
```

Because PostgreSQL is disk-based, there is a large latency gap between reading a JWT claim (~0.001ms) and querying a lookup table (~0.1–10ms, requiring disk I/O). This is why Supabase's documentation advises **embedding frequently-used claims in JWTs** — to avoid DB lookups during policy evaluation.

#### Aouda's Predicate Injection Model

```
Aouda ADRA (auth-db-rls):

  Resolver: owner_id = ? OR team_id IN (?)

  Resolution: predicate resolved once from session cache (~0.001ms)
              → owner_id = 'usr_alice' OR team_id IN ('team_west', 'team_global')

  Query:   SELECT * FROM sales
           WHERE company_id = 'acme'
             AND (owner_id = 'usr_alice' OR team_id IN ('team_west', 'team_global'))

  Evaluation: predicate evaluated by columnar scan engine
              → same cost as any other WHERE clause
              → zero additional overhead per row
```

The predicate is a SQL WHERE clause, not a function call. The columnar engine evaluates it once per column chunk, not once per row.

#### The Cost Comparison

| Operation | PostgreSQL | Aouda |
|-----------|-----------|-------|
| Read a JWT claim | ~0.001ms | ~0.001ms |
| Query auth DB lookup table | ~0.1–10ms (disk I/O) | ~0.01ms (memory-first) |
| Difference | 100–10,000× | ~10× |
| Resolution frequency | Per-row | Once per query |
| Overhead vs no-auth query | Scales with row count | Fixed ~0.001ms |

In Aouda, the traditional tradeoff between JWT-embedded claims (fast, stale) and dynamic DB lookups (flexible, slow) **does not apply**. The auth DB is always memory-first — lookup cost is ~0.01ms regardless of the complexity of the permission model.

#### What This Means for JWT Design

| Scenario | Supabase RLS | Aouda ADRA |
|---|---|---|
| User belongs to 5 teams | Embed `team_ids` in JWT claim | Resolve from `_user_partition_grants` at query time |
| User has 500 permission grants | JWT becomes multi-KB, impacts latency | JWT stays thin; grants in memory-first auth DB |
| Permission revoked | Effective at next JWT refresh (up to 15 min) | Effective on next request (permission version counter) |
| Policy requires DB lookup | Avoid — too slow per-row | Allowed — auth DB lookup costs ~0.01ms |

**Aouda enables thin JWTs for complex permission models** — something Supabase RLS cannot offer without accepting significant per-query overhead.

#### Operational Comparison

| | Supabase RLS | Aouda ADRA |
|---|---|---|
| Policy language | PostgreSQL SQL expressions | Declarative JSON resolver rules |
| Policy location | In the database as SQL objects | In auth DB (`_rls_resolvers` table) |
| Manage policies | SQL migrations or Supabase dashboard | Admin API (`PATCH /rls-resolvers/{id}`) |
| Test policies | Run SQL queries with `set local role` | Unit test resolver evaluation against mock auth DB |
| Admin bypass | `set local role service_role` | `PartitionGrant` with `{"role":"…","effect":"allow-all"}` |
| Compound predicates | Full SQL `OR`/`AND` | Composite resolver with `combinator: OR/AND` |

---

## 27. Local Developer Setup for Consumer Applications

This section is for developers building an application that uses Aouda Auth — not for working on Aouda itself. It covers everything you need to get from zero to a fully running local environment where you can develop and debug your application alongside a real Aouda auth server.

> **CLI note:** The shipped global tool command is **`aouda start`** (foreground server). Older docs referred to `aouda dev`; that subcommand is not exposed in the current CLI. Use `aouda start` with `--port` and `--data-dir`, enable auth via the HTTP API, and configure email/SMS in `appsettings.json` — see [notifications.md](notifications.md).

---

### 27.1 Install the Aouda CLI

Aouda ships as a **.NET Global Tool**. Install it once on your developer machine:

```powershell
dotnet tool install --global Aouda.Cli
```

After installation, the `aouda` command is available in any terminal:

```powershell
aouda --version
aouda start --help
```

**Updating:**
```powershell
dotnet tool update --global Aouda.Cli
```

**Uninstalling:**
```powershell
dotnet tool uninstall --global Aouda.Cli
```

> If `aouda` is not recognised after install, close and reopen your terminal. The dotnet tools path (`%USERPROFILE%\.dotnet\tools` on Windows) needs to be in `PATH`.

#### Installing from a Local .nupkg (Pre-NuGet-Release)

```powershell
dotnet tool install --global Aouda.Cli --add-source C:\path\to\aouda\nupkg

# Or run from source:
dotnet run --project C:\path\to\aouda\src\Aouda.Cli -- start --port 5433 --data-dir C:\dev\aouda-data\derive
```

---

### 27.2 Local server directory and persistent data

Create a **server working directory** outside your application repo (binary segment files accumulate here):

```
Windows:   C:\Users\<you>\AppData\Local\aouda\<app-name>
macOS:     ~/.local/share/aouda/<app-name>
Linux:     ~/.local/share/aouda/<app-name>
```

For local development you may add an **optional** `appsettings.json` in that directory, or pass everything via CLI flags (recommended). **Production Windows/Linux installs via Setup do not use appsettings** — see [Server configuration](../guides/server-configuration.md).

Example optional `appsettings.json` (auth email provider for local testing):

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5433,
    "Auth": {
      "Email": {
        "Provider": "console",
        "FromName": "Derive Dev",
        "InviteUrl": "http://localhost:3000/set-password",
        "PasswordResetUrl": "http://localhost:3000/reset-password"
      }
    }
  }
}
```

For production delivery, use `"Provider": "sendgrid"` with `ApiKey` and `FromAddress` instead of `console`.

Start the server:

```powershell
cd C:\Users\you\AppData\Local\aouda\derive
aouda start --port 5433 --data-dir .\data
```

CLI flags override config file values: `--port`, `--data-dir` (alias `--data-path`, `-d`), `--bind`, memory limits, etc. **Precedence:** CLI and `AOUDA_*` env vars win over `appsettings.json`.

> **Do NOT** put the data directory inside your application git repo.

**Password reset / invite emails:** Configure `Aouda:Auth:Email` as above. Use `Provider: console` for local testing (OTP in server logs); use `sendgrid` for real delivery. Without any provider, reset requests return `200` but no OTP is delivered. Full detail: [notifications.md](notifications.md).

---

### 27.3 Enable application auth and capture API keys

`aouda start` does not print anon/service keys automatically. Create an auth-enabled database via the HTTP API after bootstrapping a **server admin** (first run):

```bash
# One-time server admin (if no users exist)
curl -X POST http://localhost:5433/api/auth/setup \
  -H "Content-Type: application/json" \
  -d '{ "email": "admin@local.dev", "password": "AdminPass123!" }'

# Sign in → SERVER_JWT
curl -X POST http://localhost:5433/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{ "email": "admin@local.dev", "password": "AdminPass123!" }'

# Create app database with auth (standalone auth DB example)
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer <SERVER_JWT>" \
  -H "Content-Type: application/json" \
  -d '{ "name": "derive", "kind": "auth" }'
```

The response includes `auth.keys.anonKey` and `auth.keys.serviceRoleKey` — **copy both immediately** (shown once). See [setup.md](setup.md) §7 for linked-database patterns.

If keys are lost later:

```powershell
curl -X POST http://localhost:5433/api/databases/derive/auth/admin/regenerate-keys `
  -H "Authorization: Bearer mk_svc_..." `
  -H "Content-Type: application/json"
```

---

### 27.4 Store keys in appsettings.Development.json

Your application reads Aouda Auth configuration from `appsettings.json` / `appsettings.Development.json`. The recommended structure separates the OIDC Authority (for JWT validation) from the client connection details (for the Aouda client):

```json
// appsettings.Development.json  ← git-ignored, each developer maintains their own
{
  "AoudaAuth": {
    "Authority":    "http://localhost:5433/api/databases/derive",
    "Audience":     "_auth",
    "ServerUrl":    "http://localhost:5433",
    "DatabaseName": "derive",
    "AnonKey":      "mk_anon_a1b2c3d4e5f6...",
    "ServiceKey":   "mk_svc_x7y8z9e0f1a2..."
  }
}
```

| Key | Purpose | Where It Comes From |
|-----|---------|---------------------|
| `Authority` | Base URL for OIDC Discovery — used by `options.Authority` in `AddJwtBearer` | Constructed from server URL + database name |
| `Audience` | JWT `aud` claim — always the auth database name | Always `_auth` (unless you named it differently) |
| `ServerUrl` | Aouda server base URL — used to construct the `AoudaClient` | Your server address |
| `DatabaseName` | Which database the `AoudaClient` connects to | The `name` from `POST /api/databases` (e.g. `derive`) |
| `AnonKey` | `mk_anon_...` — public auth endpoints (signup, signin, password reset) | From create-database or regenerate-keys response |
| `ServiceKey` | `mk_svc_...` — admin auth endpoints (backend only) | Same response |

**In your application's `Program.cs`:**

```csharp
// JWT validation — uses OIDC Discovery to fetch the JWKS automatically.
// MetadataAddress is required: Aouda's discovery path has a non-standard /auth/ segment.
builder.Services.AddAuthentication()
    .AddJwtBearer(options =>
    {
        var authority = builder.Configuration["AoudaAuth:Authority"]!;

        // Required — do NOT rely only on Authority; the discovery URL won't be derived correctly.
        options.MetadataAddress      = $"{authority}/auth/.well-known/openid-configuration";
        options.Authority            = authority;
        options.Audience             = builder.Configuration["AoudaAuth:Audience"] ?? "_auth";
        options.RequireHttpsMetadata = false; // dev only — remove for production
    });

// Aouda client — for calling auth endpoints (signin, signup, etc.)
builder.Services.AddSingleton(_ => new AoudaClient(new AoudaClientOptions
{
    ServerUrl    = builder.Configuration["AoudaAuth:ServerUrl"]!,
    DatabaseName = builder.Configuration["AoudaAuth:DatabaseName"]!,
    AppAuth      = new AppAuthOptions { ApiKey = builder.Configuration["AoudaAuth:ServiceKey"]! }
}));
```

#### What to Commit vs What to Git-Ignore

```
# In .gitignore of your application repo:
appsettings.Development.json       ← contains real key — never commit
appsettings.*.json                 ← covers all environment-specific files (optional, broader)

# Commit a template file instead:
appsettings.Development.template.json   ← checked in, shows structure with placeholder values
```

`appsettings.Development.template.json` (safe to commit):

```json
{
  "AoudaAuth": {
    "Authority":    "http://localhost:5433/api/databases/derive",
    "Audience":     "_auth",
    "ServerUrl":    "http://localhost:5433",
    "DatabaseName": "derive",
    "AnonKey":      "REPLACE_WITH_MK_ANON_KEY",
    "ServiceKey":   "REPLACE_WITH_MK_SVC_KEY"
  }
}
```

New developers copy this to `appsettings.Development.json` and replace placeholders after creating the auth-enabled database (§27.3).

---

### 27.5 Daily Workflow — Running Both Together

Once set up, the daily workflow is two processes side by side.

#### Option A — Two Terminals (Simplest)

```
Terminal 1 — Aouda (server directory with appsettings.json):
  cd C:\Users\you\AppData\Local\aouda\derive
  aouda start --port 5433 --data-dir .\data

Terminal 2 — Your application (F5 in IDE, or):
  dotnet run --project src/Derive.Api
```

You can set breakpoints in your application code and step through calls to `AoudaAuthServiceClient`. Aouda itself runs as a black box — you trust it works, you're debugging your own integration code.

#### Option B — VS Code: Auto-Start Aouda with F5

Add to `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "start-aouda",
      "type": "shell",
      "command": "aouda start --port 5433 --data-dir ${env:USERPROFILE}/AppData/Local/aouda/derive/data",
      "options": { "cwd": "${env:USERPROFILE}/AppData/Local/aouda/derive" },
      "isBackground": true,
      "presentation": { "reveal": "always", "panel": "dedicated", "group": "aouda" },
      "problemMatcher": {
        "pattern": { "regexp": "." },
        "background": {
          "activeOnStart": true,
          "beginsPattern":  "Now listening on",
          "endsPattern":    "Application started"
        }
      }
    }
  ]
}
```

Add to `.vscode/launch.json`:

```json
{
  "configurations": [
    {
      "name": "Derive.Api",
      "type": "coreclr",
      "request": "launch",
      "preLaunchTask": "start-aouda",
      "program": "${workspaceFolder}/src/Derive.Api/bin/Debug/net8.0/Derive.Api.dll",
      "cwd": "${workspaceFolder}/src/Derive.Api",
      "env": { "ASPNETCORE_ENVIRONMENT": "Development" }
    }
  ]
}
```

Pressing **F5** now starts Aouda in a dedicated terminal panel, waits for it to be ready, then launches your application. A single keystroke runs the full stack.

> **Note on macOS/Linux:** Replace `${env:USERPROFILE}/AppData/Local/aouda/derive` with `${env:HOME}/.local/share/aouda/derive`.

#### Option C — Visual Studio: Launch Profile

In Visual Studio, add a launch profile to `Properties/launchSettings.json` in your API project:

```json
{
  "profiles": {
    "Derive.Api (with Aouda)": {
      "commandName": "Project",
      "dotnetRunMessages": true,
      "launchBrowser": true,
      "applicationUrl": "https://localhost:7001;http://localhost:5001",
      "environmentVariables": {
        "ASPNETCORE_ENVIRONMENT": "Development"
      }
    }
  }
}
```

For the Aouda process itself, use a pre-build event or a simple `start-aouda.ps1` script at the solution root:

```powershell
# start-aouda.ps1  — run this once before starting VS
Start-Process powershell -ArgumentList `
  "-NoExit -Command cd $env:USERPROFILE\AppData\Local\aouda\derive; aouda start --port 5433 --data-dir .\data"
```

#### Option D — .NET Aspire (Future-Proof)

If your solution adopts .NET Aspire, the AppHost project becomes the single F5 launch point for all services, including Aouda:

```csharp
// AppHost/Program.cs
var builder = DistributedApplication.CreateBuilder(args);

var aoudaData = Path.Combine(Environment.GetFolderPath(
    Environment.SpecialFolder.LocalApplicationData), "aouda", "derive");
var aouda = builder.AddExecutable(
    "aouda", "aouda", aoudaData,
    "start", "--port", "5433", "--data-dir", Path.Combine(aoudaData, "data"))
    .WithHttpEndpoint(port: 5433, name: "http");

builder.AddProject<Projects.Derive_Api>("derive-api")
    .WithEnvironment("AoudaAuth__Authority",
        $"{aouda.GetEndpoint("http")}/api/databases/derive")
    .WithEnvironment("AoudaAuth__ServerUrl",
        aouda.GetEndpoint("http").ToString())
    .WithReference(aouda);

builder.Build().Run();
```

F5 on the AppHost starts both Aouda and your API, wires the URLs automatically, and shows both in the Aspire dashboard with unified logs. Service discovery is handled for you — `appsettings.Development.json` no longer needs hard-coded ports.

---

### 27.6 Sharing Aouda with Your Team (Pre-NuGet)

Before Aouda is published to NuGet.org, share it as a local NuGet feed:

**Step 1 — Build the package** (run once after each Aouda update, from the Aouda repo):
```powershell
dotnet pack src/Aouda.Cli/Aouda.Cli.csproj -c Release -o ./nupkg
```

**Step 2 — Share the `nupkg` folder** via a network share, Git LFS, or a shared drive.

**Step 3 — Each developer installs from the local feed:**
```powershell
dotnet tool install --global Aouda.Cli --add-source \\shared-drive\aouda-tools
# or
dotnet tool install --global Aouda.Cli --add-source C:\path\to\nupkg
```

**Optional: Add a `nuget.config`** to your application repo so `dotnet tool restore` finds it automatically:

```xml
<!-- nuget.config at repo root — commit this -->
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <add key="nuget.org"    value="https://api.nuget.org/v3/index.json" />
    <add key="aouda-local"  value="\\shared-drive\aouda-tools" />
  </packageSources>
</configuration>
```

---

### 27.7 Developer Onboarding Checklist

Add this to your project's `README.md` or `docs/dev/Getting-Started.md`:

```markdown
## Aouda Auth Setup (one-time per developer machine)

### Prerequisites
- .NET 8 SDK
- Aouda CLI: `dotnet tool install --global Aouda.Cli`
  (or: `dotnet tool install --global Aouda.Cli --add-source \\shared-drive\aouda-tools`)

### First-time setup
1. Create server directory with `appsettings.json` (see auth/reference.md §27.2)
2. `aouda start --port 5433 --data-dir %USERPROFILE%\AppData\Local\aouda\derive\data`
3. `POST /api/auth/setup` then create auth DB — copy `mk_anon_` and `mk_svc_` from response
4. Configure email on server if testing password reset — `console` for local dev or `sendgrid` for production ([auth/notifications.md](notifications.md))
5. Copy `appsettings.Development.template.json` → `appsettings.Development.json` in your app
6. Paste keys; start your application

### Daily workflow
- Terminal 1: `aouda start` from server directory
- Terminal 2: F5 (or `dotnet run`)
```

---

### 27.8 Troubleshooting

**`aouda: command not found` after install**
Close and reopen your terminal. The dotnet tools directory (`%USERPROFILE%\.dotnet\tools`) was added to PATH by the .NET installer but the current session hasn't reloaded it.

**Port 5433 already in use**
Another process (often a previous `aouda start`, or PostgreSQL on 5433) holds the port. Use `aouda stop` or a different port:
```powershell
aouda start --port 5434 --data-dir ...
# Update AoudaAuth:Authority and AoudaAuth:ServerUrl in appsettings.Development.json to match
```

**Password reset returns 200 but no email arrives**
Email provider not configured on the **Aouda server**, or null provider active (OTP not logged). Set `Aouda:Auth:Email:Provider` to `console` for local testing or `sendgrid` for production — see [notifications.md](notifications.md). Log shows `NullEmailService: password reset email not sent`.

**`AoudaAuth:ServiceKey is not configured` error in application**
The application is starting before `appsettings.Development.json` has been populated. Check that:
1. The file exists (copy from `appsettings.Development.template.json`)
2. `ASPNETCORE_ENVIRONMENT` is set to `Development`
3. The `ServiceKey` value is not the placeholder string

**Keys shown as prefix only on startup (cannot see full key)**
Keys are stable for the lifetime of the `--data` directory. If you need to retrieve a key, regenerate it:
```powershell
curl -X POST http://localhost:5433/api/databases/derive/auth/admin/regenerate-keys `
  -H "Authorization: Bearer <your-current-mk_svc_prefix>..." `
  -H "Content-Type: application/json"
# Returns new keys — update appsettings.Development.json
```

**Application starts but JWT validation fails (401 on all requests)**
Confirm the OIDC Discovery endpoint is reachable:
```powershell
curl http://localhost:5433/api/databases/derive/auth/.well-known/openid-configuration
# Should return JSON with issuer, jwks_uri, etc.
# If this fails, Aouda is not running or the port/database name is wrong
```
Also verify that `AoudaAuth:Authority` in `appsettings.Development.json` exactly matches `http://localhost:<port>/api/databases/<database-name>` — no trailing slash.

**Data directory grows over time**
Aouda stores WAL segments and column files in the data directory. For development this is normal and manageable. If it grows large (gigabytes), the safest cleanup is:
```powershell
# Stop aouda start first, then:
Remove-Item -Recurse -Force C:\Users\you\AppData\Local\aouda\derive
# Next run will recreate everything — bootstrap admin and capture keys again
```

---

## See Also

- **[Email, SMS & Notifications](notifications.md)** — SendGrid, GatewayAPI, **console provider**, server configuration for OTP delivery

- **[Getting Started](Getting-Started.md)** — Core Aouda usage (embedded, server, data operations) and server authentication
- **[ADR 0023: Authentication and Authorization](../decisions/0023-authentication-and-authorization.md)** — P12 auth architecture, JWT structure, PLS model, RBAC
- **[ADR 0025: Auth-DB-Resolved Authorization (ADRA)](../decisions/0025-adra-auth-db-resolved-authorization.md)** — Full ADRA design rationale, auth modes, resolver model, performance analysis
- **[HTTP API](../reference/http-api.md)** — Wire contract including auth headers
- **[P12 Auth Tasks](../tasks/P12-Authentication-Authorization-Tasks.md)** — P12 implementation history
- **[P14 ADRA Tasks](../tasks/P14-ADRA-Tasks.md)** — P14 ADRA implementation overview
