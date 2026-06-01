---
title: "Use Cases"
nav_order: 5
parent: "Auth and Authorization"
---

# Auth Use Cases & User Management

> Part of the [Application Auth Guide](Getting-Started-Auth.md). Start there for an overview.

---

## 14. User Profile and Password Management

### Get Current User Profile

```bash
curl http://localhost:5433/api/databases/myapp/auth/me \
  -H "Authorization: Bearer <user-access-token>"
```

### Update Profile Metadata

```bash
curl -X PATCH http://localhost:5433/api/databases/myapp/auth/me \
  -H "Authorization: Bearer <user-access-token>" \
  -d '{ "metadata": { "displayName": "Alice Johnson" } }'
```

### Change Password

```bash
curl -X PUT http://localhost:5433/api/databases/myapp/auth/password \
  -H "Authorization: Bearer <user-access-token>" \
  -d '{ "currentPassword": "OldPass123!", "newPassword": "NewPass456!" }'
```

Changing the password revokes all existing sessions (forces re-login).

---

## 15. Use Case: Standalone Auth Service (Auth0/Clerk Replacement)

Aouda as a standalone identity provider. No data tables — only auth.

### Setup

```bash
# Create auth-enabled database (the database holds no user data)
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer <admin-token>" \
  -d '{ "name": "myapp", "auth": { "enabled": true } }'
```

### Integration

```
┌───────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  Frontend      │     │  Your Backend          │     │  Aouda            │
│  (React)       │     │  (Node.js)             │     │  (Auth only)      │
│                │     │                        │     │                  │
│  Signup form ──┼────►│  POST /signup           │     │                  │
│                │     │  → mk_svc_ auth         │────►│  auth/signup     │
│                │     │  ← JWT                  │◄────┤                  │
│  Login form  ──┼────►│  POST /login            │────►│  auth/signin     │
│                │◄────┤  ← JWT to frontend      │◄────┤  → JWT           │
│  API calls   ──┼────►│  Validate JWT locally   │     │                  │
│  (with JWT)    │     │  (RS256 signature check)│     │                  │
└───────────────┘     └──────────────────────────┘     └──────────────────┘
```

The backend validates JWTs locally using the public key from Aouda's JWKS endpoint. No round-trip to Aouda for data requests — only for auth operations.

---

## 16. Use Case: Shared Auth Across Multiple Databases (SSO)

Multiple databases sharing one auth database = single sign-on.

```bash
# All auto-link to the same _auth database
curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "orders-service", "auth": { "enabled": true } }'

curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "products-service", "auth": { "enabled": true } }'
```

User signs up via one service, can sign in via any linked service. JWT contains database-scoped roles:

```json
{
  "sub": "usr_abc123",
  "db_roles": {
    "orders-service": ["db_writer"],
    "products-service": ["db_reader"]
  }
}
```

For separate user pools, create separate auth databases:

```bash
curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "product-a", "auth": { "database": "product_a_auth" } }'
curl -X POST http://localhost:5433/api/databases \
  -d '{ "name": "product-b", "auth": { "database": "product_b_auth" } }'
```

---

## 17. Use Case: Auth and Data Together (Full-Stack)

The most common use case: Aouda handles both auth and data.

### Frontend (Direct-to-Database)

```typescript
const client = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "taskapp",
  appAuth: { apiKey: "mk_anon_..." },
});

await client.connect();

// Sign up (Layer 2)
const { user } = await client.auth.signUp("alice@example.com", "Pass123!");

// Insert data — PLS scoped to alice
await client.table("tasks").insert({
  id: 1, title: "Write docs", status: "in_progress",
});

// Query data — only alice's tasks
const tasks = await client.table("tasks")
  .where("status", "!=", "done")
  .execute();
```

### Backend (Traditional)

```typescript
const db = createAoudaClient({
  serverUrl: "http://localhost:5433",
  database: "taskapp",
  appAuth: { apiKey: process.env.AOUDA_SERVICE_KEY },
});

app.post("/api/signup", async (req, res) => {
  const result = await db.auth.signUp(req.body.email, req.body.password);
  res.json(result);
});

app.get("/api/tasks", async (req, res) => {
  const userJwt = req.headers.authorization?.replace("Bearer ", "");
  // PLS user context is set at client construction, not per-query.
  // Create a per-request client that forwards the user JWT via X-User-Token.
  const userScopedClient = createAoudaClient({
    serverUrl: "http://localhost:5433",
    database: "taskapp",
    appAuth: {
      apiKey: process.env.AOUDA_SERVICE_KEY,
      userToken: userJwt,  // forwarded as X-User-Token — PLS scoped to this user
    },
  });
  const tasks = await userScopedClient.table("tasks").execute();
  res.json(tasks.rows);
});

// Admin: sees all tasks (no PLS) — service key only, no userToken
app.get("/api/admin/tasks", async (req, res) => {
  const all = await db.table("tasks").execute();
  res.json(all.rows);
});
```

---

## 18. Admin Management of Application Users

Admin endpoints are under `/api/databases/{db}/auth/admin/...` and require the `service_role` API key, a `db_admin` user JWT, or a server admin token.

### Create User (Admin)

Use this endpoint to create user accounts programmatically — without routing through the self-service `/signup` endpoint. Requires `service_role` API key, `db_admin` user JWT, or server admin token.

**With password (account immediately signable):**

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "SecurePass123!",
    "displayName": "Alice Smith"
  }'
```

**Without password (invite-pending — sign-in refused until password is set):**

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "displayName": "Alice Smith"
  }'
```

**Response (201 Created):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "alice@example.com",
  "displayName": "Alice Smith",
  "createdAt": "2026-05-10T07:00:00Z",
  "passwordSet": false
}
```

The `id` returned is the canonical user ID. Store it — it is used as `ExternalId` in downstream services and can immediately be passed to `GET /admin/users/{id}` or `PUT /admin/users/{id}/roles`.

Invite-pending users have `passwordSet: false`. Sign-in is refused until a password is set via a future reset flow. Admin-created users with `passwordSet: true` can sign in immediately.

### List Users

```bash
curl http://localhost:5433/api/databases/myapp/auth/admin/users \
  -H "Authorization: Bearer <admin-token>"
```

### Disable/Enable a User

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/disable \
  -H "Authorization: Bearer <admin-token>"
```

### Manage Roles

```bash
# List roles
curl http://localhost:5433/api/databases/myapp/auth/admin/roles \
  -H "Authorization: Bearer <admin-token>"

# Create custom role
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/roles \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "order_processor",
    "permissions": [
      { "resourceType": "table", "resourceName": "orders", "actions": ["read", "write"] },
      { "resourceType": "table", "resourceName": "products", "actions": ["read"] }
    ]
  }'

# Replace user role assignments
curl -X PUT http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/roles \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "roles": [
      { "roleName": "order_processor", "scope": "myapp" }
    ]
  }'

# Add one role safely:
# 1) GET existing roles
# 2) merge with new role
# 3) PUT merged list

# Note: POST on this route is not supported and returns 405.
# curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/usr_abc/roles
```

### Default Roles

| Role | Permissions |
|------|------------|
| `db_admin` | Full access — read, write, delete, create/alter/drop tables, manage users |
| `db_writer` | Read, write, and delete data in all tables |
| `db_reader` | Read-only access to all tables |
| `anonymous` | No data access (can call auth endpoints only). Customizable by admins. |

---

## 19. Use Case: Admin-Managed User Onboarding

Admin-created users bypass the self-service `/signup` flow. Use admin user creation when you need to provision accounts programmatically — for example, during team onboarding, batch migrations, or multi-tenant SaaS provisioning where you control who can create accounts.

### Pattern 1 — Invite-Pending + Email Invite (Recommended)

Requires SendGrid (or configured email provider) on the Aouda server — [notifications.md](notifications.md).

Create the account without a password and send the user an email with a 6-digit OTP. The user visits your password-setup page, enters the OTP, and calls `POST .../auth/reset-password` to set their password.

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "email":           "alice@example.com",
    "displayName":     "Alice Smith",
    "sendInviteEmail": true
  }'
# → 201 { "id": "550e8400-e29b-41d4-a716-446655440000", ..., "passwordSet": false }
```

The user cannot sign in until they complete the OTP flow via `POST .../auth/reset-password`. This is the preferred pattern for multi-tenant SaaS onboarding — the user owns their password from day one.

### Pattern 2 — Forced Initial Password

Create the account with an initial password and require the user to change it on first sign-in.

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "email":               "bob@example.com",
    "password":            "TempPass789!",
    "forcePasswordChange": true
  }'
# → 201 { "id": "550e8400-e29b-41d4-a716-446655440001", ..., "passwordSet": true }
```

On first sign-in, the response includes `"requiresPasswordChange": true`:

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/signin \
  -H "Authorization: Bearer <anon-or-service-key>" \
  -H "Content-Type: application/json" \
  -d '{ "email": "bob@example.com", "password": "TempPass789!" }'
```

```json
{
  "user":                   { "id": "550e8400-e29b-41d4-a716-446655440001", "email": "bob@example.com" },
  "accessToken":            "eyJ...",
  "refreshToken":           "eyJ...",
  "expiresIn":              900,
  "requiresPasswordChange": true
}
```

The user receives a valid `aal1` JWT but the app must redirect them to a change-password page and block access to protected areas until they change their password. Use this pattern for batch migrations. After a successful password change, subsequent signins no longer include `requiresPasswordChange`.

### Pattern 3 — Direct Password Set (Admin Override)

Call `PUT /admin/users/{id}/password` to set or override a user's password at any time — no current-password check is performed. All prior sessions and refresh tokens are revoked immediately.

```bash
curl -X PUT http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/password \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{ "password": "NewSecure456!" }'
# → 204 No Content
```

This endpoint is also useful after creating an invite-pending account (`password: null`) when you want to set the password programmatically rather than sending an email.

### Resending Invite / Resending OTP

If the user did not receive the invite email, or the OTP expired, resend a fresh one:

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/invite \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json"
# → 200 { "ok": true }
```

The previous unused OTP is invalidated and a new one is emailed to the user.

---

## 20. Use Case: Self-Service Password Reset

The password reset flow covers two scenarios: a user who forgot their password, and an invite-pending user setting their password for the first time after receiving an invite email. Both cases use the same two endpoints.

**Prerequisites:** The Aouda server must have **email delivery configured** (SendGrid). Without it, `request-password-reset` returns `200` but no OTP is sent. See [Email, SMS & Notifications](notifications.md). Your app calls these endpoints with the **anon API key** (`mk_anon_...`) on public routes, same as signup/signin.

### Step 1 — User Requests a Reset

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/request-password-reset \
  -H "Authorization: Bearer <anon-or-service-key>" \
  -H "Content-Type: application/json" \
  -d '{ "email": "alice@example.com" }'
# → 200 { "ok": true }  (always — does not reveal whether email exists)
```

A 6-digit OTP is emailed to the user. The endpoint always returns `200` regardless of whether the email address is registered — this prevents user enumeration by a third party.

### Step 2 — User Submits OTP + New Password

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/reset-password \
  -H "Authorization: Bearer <anon-or-service-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "email":       "alice@example.com",
    "otp":         "482391",
    "newPassword": "NewSecure456!"
  }'
```

On success, returns a full token pair — the user is signed in immediately:

```json
{
  "user":         { "id": "550e8400-e29b-41d4-a716-446655440000", "email": "alice@example.com" },
  "accessToken":  "eyJ...",
  "refreshToken": "eyJ...",
  "expiresIn":    900
}
```

**OTP security notes:**

- The OTP is 6 digits and expires in 15 minutes.
- After 5 consecutive wrong attempts, the token is permanently invalidated — the user must request a new one.
- Use the error codes `AUTH_RESET_TOKEN_INVALID`, `AUTH_RESET_TOKEN_EXPIRED`, and `AUTH_RESET_TOKEN_EXHAUSTED` to show appropriate UI copy (see §22).

**Invite-pending first-time password set:** The same `POST .../auth/reset-password` endpoint works identically for invite-pending users setting their password for the first time. The OTP was generated when `sendInviteEmail: true` was passed at user creation (or `POST .../admin/users/{id}/invite` was called). After a successful reset, the user can sign in normally and `requiresPasswordChange` is absent from the signin response.

---

## 21. Use Case: Two-Factor Authentication (MFA)

MFA adds a second verification step after password signin. Aouda supports TOTP (e.g. Google Authenticator, Authy) and SMS phone OTP. After a successful MFA verify the user receives an `aal2` JWT; apps can enforce `aal2` on sensitive endpoints (see §24.1).

**SMS prerequisite:** Phone-factor challenges require **GatewayAPI** (or another configured SMS provider) on the Aouda server. TOTP and recovery codes do not. See [Email, SMS & Notifications](notifications.md).

### 21.1 — Enrolling TOTP (Authenticator App)

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/mfa/enroll \
  -H "Authorization: Bearer <user-access-token>" \
  -H "Content-Type: application/json" \
  -d '{ "type": "totp" }'
```

```json
{
  "factorId":      "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "type":          "totp",
  "totpUri":       "otpauth://totp/myapp:alice%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=myapp",
  "secret":        "JBSWY3DPEHPK3PXP",
  "recoveryCodes": [
    "A1B2C3D4E5F6", "G7H8I9J0K1L2", "M3N4O5P6Q7R8",
    "S9T0U1V2W3X4", "Y5Z6A7B8C9D0", "E1F2G3H4I5J6",
    "K7L8M9N0O1P2", "Q3R4S5T6U7V8"
  ]
}
```

> **Save recovery codes now.** They are shown only once. Any one code can substitute for a TOTP code if you lose access to your authenticator app.

Scan `totpUri` with any TOTP app (Google Authenticator, Authy, 1Password, etc.) to add the account. The factor is in `pending` status until the first successful verify.

### 21.2 — Enrolling a Phone Factor

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/mfa/enroll \
  -H "Authorization: Bearer <user-access-token>" \
  -H "Content-Type: application/json" \
  -d '{ "type": "phone", "phone": "+447700900123" }'
```

```json
{ "factorId": "b2c3d4e5-f6a7-8901-bcde-f23456789012", "type": "phone", "phone": "+44***0123" }
```

The phone factor is active immediately — no verify step is needed at enrolment.

### 21.3 — The MFA Sign-In Flow (Challenge → Verify)

After a user with enrolled MFA signs in, the signin response includes `"mfaRequired": true` **and `"mfaFactors": [...]`**. The app must then initiate a challenge and prompt the user for their code.

> **Use the `factorId` from the sign-in response directly.** The sign-in response already includes `mfaFactors` — do not make a separate `GET .../auth/mfa/factors` call just to get the factor ID. That call requires the same credentials and is an unnecessary round-trip. Only call `GET /mfa/factors` for factor management UIs (list/delete enrolled factors) outside of a sign-in flow.

**Step 1 — Create challenge:**

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/mfa/challenge \
  -H "Authorization: Bearer <user-access-token>" \
  -H "Content-Type: application/json" \
  -d '{ "factorId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }'
```

```json
{ "challengeId": "c3d4e5f6-a7b8-9012-cdef-345678901234", "type": "totp", "expiresAt": "2026-05-25T17:37:00Z" }
```

For phone factors, the OTP is sent by SMS at this point.

**Step 2 — Verify code (TOTP):**

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/mfa/verify \
  -H "Authorization: Bearer <user-access-token>" \
  -H "Content-Type: application/json" \
  -d '{ "challengeId": "c3d4e5f6-a7b8-9012-cdef-345678901234", "code": "123456" }'
```

Success — **new token pair with `aal2`**:

```json
{
  "user":         { "id": "550e8400-e29b-41d4-a716-446655440000", "email": "alice@example.com" },
  "accessToken":  "eyJ...",
  "refreshToken": "eyJ...",
  "expiresIn":    900,
  "aal":          "aal2"
}
```

Discard the old `aal1` tokens and use the new pair for all subsequent requests.

**Step 2 variant — Verify SMS OTP (phone factor):** same endpoint and same request body; the OTP was sent by SMS when you created the challenge.

**Step 2 variant — Use a recovery code:** same endpoint; pass one of the 8 recovery codes as `"code"` instead of a TOTP code. The code is consumed and cannot be reused.

> **`Authorization: Bearer <user-access-token>`** is the session JWT returned by `POST .../auth/signin`. It is **not** the API key. Pass the full JWT string — the one beginning with `eyJ...` that was returned in `accessToken`. The MFA endpoints identify the user from this JWT.
>
> **Route behavior:** post-sign-in routes (`/auth/me`, `/auth/signout`, `/auth/mfa/*`, `PUT /auth/password`) are user-JWT routes. If these calls fail with 401 after a successful signin, inspect the `Authorization` header first — the request is usually sending an API key (`mk_*`) or no bearer instead of the signin `accessToken`.

### 21.3.1 — MFA 401 Troubleshooting (Challenge/Verify)

Use this checklist when `POST .../auth/mfa/challenge` or `POST .../auth/mfa/verify` returns 401:

| Symptom | Typical Cause | Fix |
|---------|---------------|-----|
| 401 on `/auth/mfa/challenge` immediately after a successful signin | `Authorization` header still contains `mk_anon_...` or `mk_svc_...` (API key), not the user JWT from signin | Send `Authorization: Bearer <signin accessToken>` |
| 401 with `AUTH_TOKEN_MISSING` | No `Authorization` header reached Aouda (proxy/BFF dropped it) | Forward `Authorization` unchanged from browser/BFF to Aouda |
| 401 with `AUTH_TOKEN_INVALID` | Wrong token type or malformed token (service key, stale token, copied value with missing characters) | Use the raw `accessToken` string from signin response (`eyJ...`) |
| 401 only in BFF flow, direct browser call works | BFF replaced user JWT with service key for auth endpoints | For auth endpoints, forward user JWT directly; reserve `mk_svc_ + X-User-Token` for data endpoints only |
| Intermittent 401 after delay | Access token expired before challenge/verify call | Refresh or re-signin, then retry challenge/verify with a fresh JWT |

### 21.4 — Enforcing MFA Gates in Your Backend

See §24.1 for the `aal` enforcement code examples (C# and TypeScript).

> The `aal2` token is a standard JWT — validate it the same way as any Aouda JWT. The only difference is that `aal` is `"aal2"`. Do not implement a separate validation path; simply read the `aal` claim after standard signature validation.

### 21.5 — Managing Enrolled Factors

```bash
# List factors — use for factor management UIs, NOT during a sign-in flow
# (the sign-in response already includes mfaFactors — no need to call this endpoint after signin)
curl http://localhost:5433/api/databases/myapp/auth/mfa/factors \
  -H "Authorization: Bearer <user-access-token>"
# → { "factors": [{ "id": "a1b2c3d4-...", "type": "totp", "status": "active", "createdAt": "2026-05-25T10:00:00Z" }] }

# Delete a factor
curl -X DELETE http://localhost:5433/api/databases/myapp/auth/mfa/factors/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <user-access-token>"
# → 200 { "ok": true }
```

### 21.6 — Admin Enrolling a Phone Factor on Behalf of a User

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/admin/users/550e8400-e29b-41d4-a716-446655440000/mfa/enroll \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{ "type": "phone", "phone": "+447700900123" }'
# → 200 { "factorId": "d4e5f6a7-b8c9-0123-def0-456789012345", "type": "phone" }
```

Use case: pre-enrol a phone factor during a migration or onboarding flow where the admin knows the user's phone number. The user's next signin will return `"mfaRequired": true` and they will be prompted to verify via SMS.
