---
title: "Auth and Authorization"
nav_order: 3
has_children: true
---

# Access: principals, policy and credentials (**BL-1464, next train**)

Three concepts decide every request.

A **principal** is who is acting: a person, a service, a CI job, an AI agent, or an anonymous browser. One kind, one list per auth database. A person is a principal with a password. A service is a principal with a key.

A **policy** is what that principal may do. It is statements of an action, a resource and an optional row condition, attached to the principal or to a **role** (a named bundle of statements). Nothing else grants anything. Nothing is implied.

A **credential** proves which principal is acting. It never decides what the principal may do. It can only narrow it. Every key has one format, `aouda_<id>_<secret>`.

Principals, roles and statements live in one place: [`aouda.json`](../guides/declaration.md), or the access API. [`GET /api/auth/whoami`](whoami.md#whoami) says, for any credential, who it is and what it may do. Every refusal names its remedy.

## The 18 concepts

| Concept | What it is | Where it is taught |
|---|---|---|
| Principal | Who is acting. One list per auth database. | [Principals](principals.md#principals) |
| Auth database | That list, and the link that says which data databases it governs. | [Auth databases](principals.md#auth-databases) |
| `anonymous` | The principal a data-plane request with no credential acts as. | [Anonymous](principals.md#anonymous) |
| `signup` | What a principal that signs itself up is allowed to do. Default: nothing. | [Signup](principals.md#signup) |
| Role | A named bundle of statements. Three are built in: `admin`, `writer`, `reader`. | [Roles](principals.md#roles) |
| Statement | `actions`, `resources`, and an optional `where`. | [Statements](authorization.md#statements) |
| Attribute | A named value on a principal that a `where` can read. | [Attributes](principals.md#attributes) |
| `embargoSeconds` | How long a `read` or `execute` waits before a new row is visible. | [Embargo](authorization.md#embargo) |
| Actions | `read`, `write`, `delete`, `execute`, `manage`, `set-identity`. | [Actions](authorization.md#actions) |
| Key format and stored keys | `aouda_<id>_<secret>`, shown once, declared as `{ "id", "sha256" }`. | [Key format](credentials.md#key-format), [stored keys](credentials.md#stored-keys) |
| Derived keys and the key root | The same key after a wipe, computed from `keyRoot`. | [Derived keys](credentials.md#derived-keys) |
| OIDC trust | A workload's identity token, exchanged for a session. | [OIDC](credentials.md#oidc) |
| Limited key | A key that can only narrow the parent's policy. | [Limited keys](credentials.md#limited-keys) |
| Password and sessions | Sign-in, refresh, and the sign-in allowance as a limit. | [Sessions](credentials.md#sessions) |
| Setup mode | Open only while no principal holds `manage` on `server`. | [Setup mode](principals.md#setup-mode) |
| Dev admin | `aouda start --dev-admin` prints one throwaway principal. | [Quick start](../getting-started/auth.md) |
| `crossPartitionAccess` | A cost waiver on a query. Not security. | [Actions](authorization.md#actions) |
| `whoami` and `policy explain` | What this credential may do, and why a call was refused. | [whoami](whoami.md#whoami), [CLI](../reference/cli.md) |

## Start here

| You are building | Do this |
|---|---|
| A browser app | No key. Point it at the data-plane listener. Give `anonymous` the statements the browser may run. [Direct client access](../guides/direct-client-access.md). |
| A backend | One principal, one stored or derived key, statements for the routes it calls. [Credentials](credentials.md#stored-keys). |
| A feeder | A declared principal with a derived key and a `where` on the rows it may write. [Declared access](../guides/declared-access.md). |
| A CI job | `aouda login --oidc` exchanges the job's identity token for a session. [OIDC](credentials.md#oidc). |
| An AI agent | `aouda start --dev-admin`, then `whoami`, then `policy explain`. [Local CLI testing](../ai/local-cli-testing.md). |
| Moving from 0.14 | [Moving from 0.14](migrating-from-0-14.md). |

## The two listeners

| Listener | A request with no credential |
|---|---|
| Admin | `401 AUTH_CREDENTIAL_MISSING` |
| Data plane | The `anonymous` principal of the database's governing auth database |

A credential is a bearer token: a key or a session. There is no second header.

## Defaults

| Setting | Default |
|---|---|
| `signup` | `{ "enabled": false, "roles": [], "statements": [] }` — a signed-up principal can do nothing until the application says what |
| `anonymous` | No statements. A browser can do nothing until you give it some. |
| Setup mode | Only while no principal holds `manage` on `server`. A declaration or `--dev-admin` ends it. |

## What is not built

- **Capability tokens.** A credential names a principal. It does not carry a capability.
- **A hosted OAuth authorization server.** Workload identity is an OIDC trust and `aouda login --oidc`. Browser sign-in is Aouda's own password (and MFA). There is no authorization-code server to point a third-party login at.
- **End-user sign-in through an external provider.** A person signs up and signs in with a password on the auth database. Signing end users in through an external identity provider is not built.

Each of those is absent on purpose. This page does not promise a date.
