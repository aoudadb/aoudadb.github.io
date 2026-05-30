---
title: "Authentication Setup"
nav_order: 2
parent: "Getting Started"
---

# Aouda Application Auth Service — Complete Guide

> **This document covers using Aouda as an authentication service for your application's end users.** If you need to secure access to the Aouda server itself (database administrator logins, service accounts, CI/CD pipelines), see [Server Authentication in Getting-Started.md](Getting-Started.md#8-server-authentication--securing-database-access).

---

## Table of Contents

**This page (overview & concepts):**

1. [What is the Application Auth Service?](#1-what-is-the-application-auth-service)
2. [The Complete Aouda Auth Model](#2-the-complete-aouda-auth-model)
3. [Quick Start](#3-quick-start)
4. [The Two-Layer Model Explained](#4-the-two-layer-model-explained)

**Detailed guides (separate pages):**

- **[Architecture Patterns & Deployment](architecture.md)** — Four deployment patterns (backend-mediated, direct-to-database, standalone auth, hybrid) and six deployment scenarios
- **[Setup & User Flows](setup.md)** — Enabling auth on a database, signup/signin/signout flows, token lifecycle and refresh
- **[Email, SMS & Notifications](notifications.md)** — SendGrid, GatewayAPI, and server config for password reset and MFA OTP delivery
- **[Client Integration](client-integration.md)** — .NET and TypeScript client examples, API keys and credential types, X-User-Token for backend user context, **BFF/gateway proxying auth endpoints**
- **[Use Cases & User Management](use-cases.md)** — Standalone auth, shared auth (SSO), full-stack auth+data, admin user management, password reset, MFA
- **[Data Authorization: Three Modes](authorization.md)** — jwt-claim, auth-db-pls (enhanced PLS with fan-out), auth-db-rls (row-level security), combined PLS+RLS, reference use cases
- **[Reference](reference.md)** — AI agent workflows, API reference tables, error handling, security best practices, JWT validation (5 languages), testing, comparison with other auth services, local developer setup

---

## 1. What is the Application Auth Service?

Aouda includes a **built-in authentication service** that your application can use to handle user registration, login, sessions, and JWTs for your **end users**. This is the same kind of service provided by Firebase Authentication, Supabase Auth, Auth0, or Clerk.

The difference is that Aouda's auth service runs **inside the database engine** — there is no separate auth server, no Redis for session caching, no external dependency. User credentials, sessions, refresh tokens, roles, and audit logs are all stored in a Aouda database, benefiting from memory-first performance, WAL durability, and replication.

### What Does "Application Auth" Mean?

When you build a web or mobile application, your users need to create accounts and log in. You need to:

- Let users **sign up** with email and password
- Let users **sign in** and receive a token
- **Validate tokens** on your API endpoints
- **Refresh tokens** before they expire
- Let users **sign out** and invalidate sessions
- **Manage users** as an admin (disable accounts, replace role assignments)

This is what the Aouda Application Auth Service provides. It is a REST API and SDK feature that your application calls to handle these flows.

### What Application Auth Is NOT

- It is **NOT** database server access control. That is [Server Authentication](Getting-Started.md#8-server-authentication--securing-database-access), a completely separate system.
- It is **NOT** automatically enabled. You must explicitly enable it per database.
- It is **NOT** required to use Aouda. If your application handles auth through another service (Auth0, Clerk, your own implementation), you don't need this feature at all.
- It is **NOT** available in embedded mode. Application Auth requires the Aouda HTTP server.

---

## 2. The Complete Aouda Auth Model

Before diving into the Application Auth Service specifically, it's important to understand the **complete picture** of how authentication and authorization work across Aouda. This section explains the full hierarchy — from the server level down to individual data partitions.

### The Hierarchy

Aouda has a layered auth model that mirrors how traditional databases (PostgreSQL, SQL Server) work, but extends it with a Supabase-style application auth layer:

```
Aouda Server Instance
│
├─ Server Auth (_serverauth)
│  │  Controls: WHO can access the Aouda server and its databases
│  │  Users:    DBAs, developers, CI/CD pipelines, backend services
│  │  Analogy:  PostgreSQL roles, SQL Server logins
│  │
│  ├─ Server Admin (superuser)
│  │   Created via:  POST /api/auth/setup
│  │   Access:       ALL databases, ALL operations
│  │   Analogy:      PostgreSQL's `postgres` or SQL Server's `sa`
│  │
│  ├─ Server Users (database-scoped)
│  │   Created via:  POST /api/auth/admin/users
│  │   Access:       Only databases they have roles for
│  │   JWT claim:    db_roles: { "myapp": ["db_writer"], "analytics": ["db_reader"] }
│  │   Analogy:      PostgreSQL roles with per-database GRANT
│  │
│  └─ Server API Keys (database-scoped)
│      Created via:  POST /api/auth/admin/keys
│      Prefix:       mk_srv_
│      Access:       Only databases the key has roles for
│      Analogy:      Service accounts / connection strings
│
├─ Database: "myapp"
│  │  Auth:      App Auth enabled (linked to _auth)
│  │
│  ├─ Server-level gate:
│  │     Server users/keys need a db_* role for "myapp" to access it
│  │
│  ├─ App Auth (linked to _auth database)
│  │  │  Controls: WHO can use your application (end users)
│  │  │  Users:    Your app's customers, employees, visitors
│  │  │  Analogy:  Supabase Auth, Firebase Auth, Auth0
│  │  │
│  │  ├─ Auto-generated API keys (Layer 1 — connection gate):
│  │  │   mk_anon_...  → anonymous role (for frontends, pre-auth)
│  │  │   mk_svc_...   → db_admin role (for backends, THIS database only)
│  │  │
│  │  └─ App Users (Layer 2 — user identity):
│  │      Sign up via:  POST /api/databases/myapp/auth/signup
│  │      JWT claim:    db_roles: { "myapp": ["db_reader"] }
│  │      PLS:          Enforced (scoped to user's partition)
│  │
│  └─ Data: orders, products, ...
│
├─ Database: "analytics"
│  │  Auth:      Server auth only (no app auth)
│  │  Access:    Server users/keys with a role for "analytics"
│  └─ Data: events, metrics, ...
│
└─ Database: "cache"
   │  Auth:      None (open access)
   │  Access:    Anyone who can reach the server
   └─ Data: fx_quotes, ...
```

### Three Authentication States for a Database

Every database on a Aouda server falls into one of three states:

| State | How Data Is Protected | When to Use |
|-------|----------------------|-------------|
| **No auth** | Open — anyone on the network can read/write | Caches, development, low-sensitivity data |
| **Server auth only** | Server users/keys must have a role for this database | Internal databases, analytics, services without end-user access |
| **Server auth + App auth** | Server auth gates admin access; App auth gates end-user access via API keys + user JWTs | User-facing applications, SaaS, mobile apps |

### How Server Auth and App Auth Interact on the Same Database

When a request arrives for a database that has **both** server auth and app auth enabled, the middleware resolves the credential:

```
Request arrives at: POST /api/databases/myapp/query  (with "table": "orders" in body)

Who is making the request?

Case A: Server credential (from _serverauth)
  → JWT or mk_srv_ API key from the _serverauth database
  → db_roles checked for "myapp"
  → Full access at the granted role level
  → No PLS enforcement (server credentials see all data)
  → Used by: DBAs, CI/CD, cross-database backend services

Case B: App API key (from _auth, auto-generated)
  → mk_anon_... → maps to anonymous role, PLS enforced
  → mk_svc_... → maps to db_admin role, PLS bypassed
  → Used by: Frontend clients, per-database backend services

Case C: App user JWT (from _auth, obtained via signin)
  → JWT validated against the linked _auth database
  → db_roles checked for "myapp"
  → PLS enforced based on JWT claims (tenant_id, user_id)
  → Used by: End users of your application
```

The middleware tries the server auth database (`_serverauth`) first, then falls back to the app auth database (`_auth`). A valid credential from **either** database grants access at the permission level of that credential.

### Two Independent Auth Systems — Summary

| | Server Authentication | Application Auth Service |
|---|---|---|
| **What it protects** | The Aouda server and its databases | Your application's user-facing features |
| **Equivalent to** | PostgreSQL roles, SQL Server logins | Firebase Auth, Supabase Auth, Auth0, Clerk |
| **Who are the users?** | DBAs, developers, CI/CD, backend services | Your app's end users (customers, employees) |
| **Can users self-register?** | No — admins create accounts | Yes — end users sign up themselves |
| **How many users?** | A handful (your team + services) | Thousands to millions (your customer base) |
| **API routes** | `/api/auth/...` | `/api/databases/{db}/auth/...` |
| **Internal database** | `_serverauth` | `_auth` (or custom name) |
| **Required for embedded mode?** | No | No (server-mode feature) |
| **Can you use one without the other?** | Yes | Yes |

---

## 3. Quick Start

### Option A: Local Server Init + Explicit App Auth Databases (Recommended)

Start the server, initialize the server admin, then create the auth and app databases explicitly:

```bash
# 1. Start local server
aouda start --port 5433

# 2. Initialize server admin only
aouda init \
  --admin-email admin@example.com \
  --admin-password "AdminPass123!" \
  --server http://localhost:5433 \
  --json

# 3. Create auth database (returns anon + service keys once)
aouda databases create --name auth --kind auth --server http://localhost:5433 --token <admin-token>

# 4. Create app database linked to auth
aouda databases create --name myapp --auth-enabled --auth-database auth --server http://localhost:5433 --token <admin-token>
```

`aouda init` does **not** start the server and does **not** create databases. It only bootstraps or verifies the server admin setup. Create as many auth, app, analytics, cache, or other databases as your application needs with `aouda databases create`.

### Option B: Local Explicit Setup

Start server first, then create auth and app databases explicitly:

```bash
# 1. Start local server
aouda start --port 5433

# 2. Create auth database (returns anon + service keys once)
aouda databases create --name auth --kind auth

# 3. Create app database linked to auth
aouda databases create --name myapp --auth-enabled --auth-database auth
```

This explicit flow matches production behavior and avoids hidden auto-provisioning.

What this does, step by step:

1. `aouda start` launches the server only (no implicit databases).
2. Creating `auth` with `--kind auth` provisions the auth authority database and key material.
3. Creating `myapp` with `--auth-enabled --auth-database auth` links application auth routes under `myapp` to that auth authority.

After this setup:

- End-user signup/signin happens on `myapp` routes (`/api/databases/myapp/auth/...`).
- The auth authority remains centralized in the `auth` database.
- You can add additional app databases and link them to the same auth authority when needed.

Quick verification:

```bash
curl -X POST http://localhost:5433/api/databases/myapp/auth/signup \
  -H "Authorization: Bearer <mk_anon_...>" \
  -H "Content-Type: application/json" \
  -d '{ "email": "user@example.com", "password": "Pass123!" }'
```

> **For teams using Aouda Hub:** Hub provides centralized account management, organization membership, and server registry. Team members authenticate through Hub rather than directly against the Aouda server. See the [Hub documentation](https://github.com/aouda/aouda-hub) for the Hub auth flow.

### Option C: Production Setup (Full control)

```bash
# 1. Bootstrap the server admin
curl -X POST http://localhost:5433/api/auth/setup \
  -H "Content-Type: application/json" \
  -d '{ "email": "admin@example.com", "password": "AdminPass123!" }'

# 2. Sign in as server admin
TOKEN=$(curl -s -X POST http://localhost:5433/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{ "email": "admin@example.com", "password": "AdminPass123!" }' | jq -r .accessToken)

# 3. Create the auth database first (explicit)
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "name": "auth", "kind": "auth" }'

# Response:
# {
#   "name": "auth",
#   "auth": {
#     "enabled": true,
#     "database": "auth",
#     "keys": {
#       "anonKey": "mk_anon_...",        ← Give to frontend developers
#       "serviceRoleKey": "mk_svc_..."   ← Keep secret — backend only
#     }
#   }
# }

# 4. Link data databases to it (saves the returned app keys)
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "name": "myapp", "auth": { "enabled": true } }'

# 5. Test: sign up a user using the anon key
curl -X POST http://localhost:5433/api/databases/myapp/auth/signup \
  -H "Authorization: Bearer mk_anon_..." \
  -H "Content-Type: application/json" \
  -d '{ "email": "alice@example.com", "password": "SecurePass123!" }'
```

---

### Server Admin API Key Workflow

For production deployments where you want a **long-lived, non-expiring credential** to manage databases and their auth keys, use a server admin API key instead of a password-based token:

```bash
# 1. Bootstrap the server admin and sign in (see Getting-Started.md §8)
TOKEN=$(curl -s -X POST http://localhost:5433/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"AdminPass123!"}' | jq -r .accessToken)

# 2. Create a server admin API key (mk_srv_ prefix, never expires)
curl -X POST http://localhost:5433/api/auth/admin/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ci-deploy",
    "databaseRoles": {
      "myapp": ["db_admin"]
    }
  }'
# → { "key": "mk_srv_abc123...", "name": "ci-deploy" }

# 3. Use the key directly — no refresh needed
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer mk_srv_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"name":"myapp","auth":{"enabled":true}}'
```

Server admin API keys are database-scoped — specify `databaseRoles` to control exactly which databases the key can access and at what permission level. See [Getting-Started.md §8](Getting-Started.md#8-server-authentication--securing-database-access) for the full server auth reference.

---

## 4. The Two-Layer Model Explained

Like Supabase and Firebase, Aouda uses a **two-layer authentication model** for Application Auth:

| Layer | Question It Answers | Credential | Who Provides It |
|-------|-------------------|------------|-----------------|
| **Layer 1: Connection** | "What application is accessing this database?" | API key (`anon` or `service_role`) | Developer (from database creation response) |
| **Layer 2: User Identity** | "Which user is making this request?" | User JWT (from signin) | End user (via signup/signin flow) |

### Layer 1: API Keys (Connection Gate)

When you create a database with auth enabled, Aouda auto-generates two API keys:

| Key | Prefix | Role | PLS | Use Case | Safety |
|-----|--------|------|-----|----------|--------|
| **`anon`** | `mk_anon_` | `anonymous` (no data access by default) | Enforced | Frontend, mobile, public clients | Safe to embed in client-side code |
| **`service_role`** | `mk_svc_` | `db_admin` (full access) | **Bypassed** | Backend servers, admin tools | **Must keep secret** |

The API key is the **gate** that controls which applications can talk to the database. Without a valid API key, even the auth endpoints (signup, signin) are inaccessible:

```bash
# Without API key → 401 AUTH_API_KEY_REQUIRED
curl -X POST http://localhost:5433/api/databases/myapp/auth/signup \
  -d '{ "email": "user@example.com", "password": "Pass123!" }'

# With anon key → success
curl -X POST http://localhost:5433/api/databases/myapp/auth/signup \
  -H "Authorization: Bearer mk_anon_..." \
  -d '{ "email": "user@example.com", "password": "Pass123!" }'
```

### Layer 2: User JWTs (Identity)

After a user signs in, they receive a JWT that contains their identity, roles, and tenant information. The client sends this JWT as the `Authorization: Bearer` header for data operations:

```
1. Client created:    Authorization: Bearer mk_anon_...
                      ↑ API key identifies the APPLICATION

2. Before sign-in:   Requests use the anonymous role
                     PLS allows only public data (none by default)

3. User signs in:    POST /databases/myapp/auth/signin
                     → Aouda returns a user JWT

4. After sign-in:    Authorization: Bearer eyJhbG...
                     ↑ User JWT replaces the API key
                     PLS evaluates JWT claims (tenant_id, user_id, roles)

5. Backend access:   Authorization: Bearer mk_svc_...
                     → Service key bypasses PLS, grants full access
```

### How the Middleware Distinguishes Keys from JWTs

The middleware detects the credential type by prefix:

- Starts with `mk_` → **API key** → validate against `_api_keys` table
- Anything else → **JWT** → validate signature against auth database keys

After a successful sign-in, the user JWT replaces the API key in the `Authorization` header. The client SDK handles this transition automatically.

---

## Pattern E: Standalone Auth Service

Use this pattern when you want a **dedicated auth microservice** that is separate from your data databases — for example, a gateway that validates user identity for multiple services.

```
                 ┌─────────────────────────┐
                 │   Aouda Server          │
                 │                         │
  Auth only ──►  │  Database: "auth"       │  ◄── POST /api/databases/auth/auth/signup
                 │  (kind: "auth")         │  ◄── POST /api/databases/auth/auth/signin
                 │                         │      GET  /api/databases/auth/auth/.well-known/openid-configuration
                 └─────────────────────────┘
                            │
                            │  JWT issued by "auth"
                            ▼
                   Other services validate
                   JWT against OIDC discovery
```

**Create the standalone auth database:**

```bash
curl -X POST http://localhost:5433/api/databases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "name": "auth", "kind": "auth" }'
```

The auth database can be used directly as the `{db}` segment in all auth endpoints — no separate proxy database is needed. The response includes `anonKey` and `serviceRoleKey` immediately.

**.NET configuration using Aouda as an OIDC provider:**

```json
{
  "AoudaAuth": {
    "Authority":    "http://localhost:5433/api/databases/auth",
    "Audience":     "auth",
    "DatabaseName": "auth",
    "ServiceKey":   "mk_svc_..."
  }
}
```

JWT claims issued for standalone auth: `iss = http://localhost:5433/api/databases/auth`, `aud = auth`.

See **[Architecture Patterns & Deployment — Pattern E](Auth-Architecture.md)** for the full deployment diagram and multi-service gateway example.

---

## Next Steps

- **[Architecture Patterns & Deployment](Auth-Architecture.md)** — Choose a deployment pattern for your application
- **[Setup & User Flows](Auth-Setup-And-Flows.md)** — Enable auth and implement signup/signin
- **[Client Integration](Auth-Client-Integration.md)** — Connect from .NET or TypeScript
- **[Data Authorization](Auth-Data-Authorization.md)** — Configure partition-level and row-level security
- **[Reference](Auth-Reference.md)** — API tables, error codes, JWT validation, security best practices
