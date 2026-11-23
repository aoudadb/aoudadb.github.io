---
title: "Principals"
nav_order: 1
parent: "Auth and Authorization"
---

# Principals (**BL-1464, 0.16.0**)

## Principals

A principal is who is acting. There is no type field. A person is a principal whose credential is a password (the name is an email). A service is a principal whose credential is a key (the name is a slug). Outside its auth database a principal is written `<authDatabase>/<name>`, for example `auth/rates-feeder` or `_serverauth/ops@example.com`.

| Field | Meaning | Default |
|---|---|---|
| `id` | Stable for the principal's life. A declared principal's id is the first 16 bytes of `SHA-256("aouda-principal\0" + authDatabase + "\0" + name)`, so a wipe recreates the same id. | Assigned |
| `name` | Unique in the auth database, compared without regard to case. A slug `^[a-z][a-z0-9-]{0,62}$`, or an email. A runtime rename keeps the `id`. | Required |
| `description` | Free text. | Empty |
| `roles` | Names of roles of the same auth database. | None |
| `statements` | Inline statements. | None |
| `attributes` | Named values a `where` can read. | None |
| `credentials` | How it proves who it is. See [Credentials](credentials.md). | None |
| `disabled` | `true` refuses every credential. Open sessions end. | `false` |
| `source` | `declared` (owned by `aouda.json`), `runtime` (created through the API), `signup` (self-signup), or `builtin` (`anonymous`). | Set by how it was created |

## Auth databases

Each auth database holds one list of principals and one set of roles. The server auth database is `_serverauth`. An application auth database is one you declare with `"kind": "auth"`.

A data database is **governed** by the auth database it links to (`authDatabase` in the declaration). A data database linked to none is governed by `_serverauth`.

Two rules, and nothing else:

1. A principal of an application auth database may hold statements on the databases that auth database governs, on the auth database itself, and on its own principals and roles. Nothing on another auth database's databases. Nothing on `server`.
2. A principal of `_serverauth` may hold statements on every database and on `server`. That is the operator tier.

A statement that names a resource its auth database does not govern is refused when it is written (`STATEMENT_NOT_GOVERNED` in a plan, `400 AUTH_POLICY_INVALID` on the API), and the auth database that does govern it is named. A credential resolves to exactly one principal. There is no second try against another auth database: a valid credential of the wrong one is `403 AUTH_WRONG_AUTH_DATABASE`, with remedy `use-credential-of` naming the auth database that governs the target.

`_serverauth` takes no signup. Enabling signup creates an application auth database and links the data database to it.

## Anonymous

Every auth database has one built-in principal named `anonymous`. It has no credentials, and one cannot be added. A request with **no credential** on the **data-plane listener** acts as the `anonymous` principal of the target database's governing auth database. Its policy is empty until a declaration or the API gives it statements.

A request with no credential on the **admin listener** is `401 AUTH_CREDENTIAL_MISSING`. Anonymous is a browser-tier principal. A browser needs no key: the data-plane URL and the database name.

An unlinked database's anonymous visitor is `_serverauth/anonymous`, whose policy is empty.

## Signup

Self-signup creates a principal in the governing auth database (`source: signup`, named by the email, credential: the password). What it may do is that auth database's `signup` setting:

```json
{ "enabled": false, "roles":, "statements": }
```

That is the default. **A signed-up principal can do nothing until the application says what.** Closing signup stops new signups. It does not revoke principals that already signed up; disable those principals, or take the statements away.

`signup` is one setting per auth database, read and written at `GET` / `PUT /api/auth/{authDatabase}/signup`. A change applies to every signup principal at its next request: the roles and statements are resolved, not copied. `POST /api/databases/{db}/auth/signup` reads the **governing** auth database's setting. Closed is `403 AUTH_SIGNUP_DISABLED`.

## Attributes

An attribute is a named list of values on a principal. A statement's `where` reads it as `attributes.<name>`. Values are strings, numbers or booleans. Caps are enforced when the attribute is written (`400 AUTH_ATTRIBUTE_CAP`).

A missing attribute, a value that cannot be bound, or several values under a scalar operator match **no row**. They do not match every row.

## Roles

A role is a named bundle of statements in one auth database. Names are unique without regard to case. Three roles are built in, read-only, in every auth database:

| Role | Statements |
|---|---|
| `admin` | `{ "actions": ["*"], "resources": ["*"] }` — every action on everything the auth database governs |
| `writer` | `read`, `write` and `delete` on `*/table/*`; `execute` on `*/query/*` and `*/mutation/*` |
| `reader` | `read` on `*/table/*`; `execute` on `*/query/*` |

A role you declare is `source: declared` and is edited in `aouda.json`. A role created through the API is `source: runtime`. The built-in names cannot be declared again (`409 AUTH_BUILTIN_READ_ONLY` on a write).

## Declared and runtime

| `source` | Who may change it |
|---|---|
| `declared` | The declaration file, then `aouda reload`. The API refuses with `409 DECLARED_IN_CONFIGURATION`. `disabled` may still be set at runtime. |
| `runtime` | The access API, by a principal that holds `manage` on it and covers the statements it grants. |
| `signup` | Created by signup. Its policy is the auth database's `signup` setting, not a copy. |
| `builtin` | `anonymous`, and the three roles. Statements and attributes on `anonymous` are the only writes it takes. |

A declared principal's id survives a wipe. A runtime principal does not: the export will tell you so (`EXPORT_RUNTIME_NOT_ADOPTED`).

## Setup mode

Setup mode is how the first operator is created on a data directory that has never been set up. It ends as soon as a principal holds `manage` on `server`: a declared `_serverauth` principal, or the principal `--dev-admin` prints. A data directory that has been set up never re-enters setup mode. With no such principal and nothing declared, the start is refused (`SERVER_HAS_NO_OPERATOR`).

`POST /api/auth/setup` is the first-run call, from the machine that holds the data directory. Two concurrent calls: the one that waited is `403 ALREADY_CONFIGURED`.

## Password

Password, reset and MFA mechanics are in [Setup and flows](setup.md). The admin routes that still say `users/{id}` in the path take the principal's id. The actor is a principal.
