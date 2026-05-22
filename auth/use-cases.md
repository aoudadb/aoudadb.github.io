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
