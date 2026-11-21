---
title: "Declared access"
nav_order: 2.65
parent: "Guides"
---

# Declared access: principals, roles and `signup` in `aouda.json` (**BL-1464, 0.16.0**)

The declaration file says **who may do what**, beside what exists. Per application auth database, `databases.<auth>` takes three
members — `signup`, `roles`, `principals` — and the server auth database's operators are declared once in `server.roles` and
`server.principals`. A wipe of the data directory followed by a plain start brings every declared principal and role back, with the
same ids. The exact JSON of each member is in [The declaration file](../reference/declaration.md#the-access-section-signup-roles-principals-bl-1464-0160).

## What a start and a reload do with it

1. **Check it, offline and in full.** [`aouda plan`](plan.md) and the start run the same checks: names (a slug or an email, compared
   without case), the built-in names (`admin`, `writer`, `reader` cannot be declared; `anonymous` is spelled `anonymous` and takes
   statements and attributes only), every statement read strictly, and the model's rules:
   - **One auth database governs each resource.** A statement of `auth` may name `auth` itself and the databases linked to it. A
     statement on a database linked to another auth database, on a database linked to none, or on `server` is
     `STATEMENT_NOT_GOVERNED`, naming the auth database that does govern it. `server.principals` and `server.roles` may name
     everything.
   - **Public reach.** When some statement restricts a table with a `where`, `anonymous`, `signup` and the roles they hold may not read
     it unconditionally: `AUTH_PUBLIC_UNRESTRICTED`, naming both statements. Mark the public statement `"unrestricted": true` when every
     row is meant to be public. `manage` is never public, `unrestricted` or not.
   - A table, named query or column that no declared schema has is a **warning** (`STATEMENT_RESOURCE_UNKNOWN`,
     `STATEMENT_COLUMN_UNKNOWN`): a statement may precede its table, and it grants nothing until the table exists.
2. **Check it against the server.** At start, and in a reload's dry run, the same rules run again against the principals and roles the
   server already has, and against its live catalog, so neither a runtime role nor the order of changes gets around them. A role a
   principal or `signup` names that does not exist is `PRINCIPAL_ROLE_UNKNOWN`.
3. **Converge.** The server creates, updates and removes what the file declares — roles, then `signup`, then principals and
   `anonymous`, removals last — and nothing else. Every change is one line of the plan (`principals  added auth/checkout (declared)`)
   and of the reload's answer (`changes.roles`, `changes.principals`, `changes.signup`); a statement's text is never printed.

A plan that is clean is a converge the server accepts: the plan runs the same rules over the same changes. Should a write be refused
anyway, the start or the reload stops at it (`ACCESS_CONVERGE_REFUSED`) — nothing after it is written.

## The file owns what it declares

- A declared principal or role is the file's, **whole**: change it in the file, not in Studio or through the API. (**BL-1463, 0.16.0**) The API refuses such a change with `409 DECLARED_IN_CONFIGURATION`, naming the file and the JSON pointer — a change to its
  statements, roles, attributes or description, a rename or a deletion, a stored key or an OIDC trust added for it, deleting one of its
  declared credentials, a change to the `signup` setting or `anonymous` of an auth database the file declares access for — and changes
  nothing. Two emergency actions stay allowed: setting the principal `disabled` (on its own) and revoking one of its credentials; both
  are reported `DECLARED_OBJECT_OVERRIDDEN` at every start and reload while the file disagrees. A declared principal may mint a limited
  key (it only narrows, and is never a declaration), and a runtime principal may hold a declared role. A principal removed from the file
  is deleted with its credentials, and its open sessions end at once.
- A principal or role made at runtime with the same name as a declared one is **refused**, not taken over
  (`PRINCIPAL_RUNTIME_CONFLICT`, `ROLE_RUNTIME_CONFLICT`): delete or rename the runtime one, then start or reload again.
- For every auth database the file declares access for, the file also owns `anonymous` and `signup`: an `anonymous` that is not
  declared holds nothing, and a `signup` that is not declared is off. Principals and roles made at runtime keep living beside the
  declared ones.

## The emergency action: `disabled`

An operator can **disable** a declared principal at runtime (an incident: a leaked credential, a misbehaving service). That stays: the
next start and reload do not re-enable it, and every plan, start and reload reports `DECLARED_OBJECT_OVERRIDDEN` naming the principal
until the file and the server agree — write `"disabled": true` in the file, or re-enable it at runtime. The file's own
`"disabled": true` disables the principal and ends its sessions; changing it back to `false` re-enables only what the file disabled.

## Who operates the server

A server must always keep an operator: a principal of the server auth database that holds `manage` on `server` (the built-in `admin`
role grants it) and has a credential. A start or reload that would leave none is refused (`SERVER_HAS_NO_OPERATOR`) and changes
nothing. A server that has never been set up and declares no operator starts in setup mode.

(**BL-1720, next train**) The rule counts the credentials the converge keeps, not the ones it is about to delete: removing the operator's last key from the file is refused (`SERVER_HAS_NO_OPERATOR`), as removing the operator is.

## After a backup restore

A restore brings back the auth database as it was when the backup was taken, and the node converges the declared access section onto it. When that converge is refused (a runtime principal or role holds a declared name, or a store rule refused a write), **what the file removed is still removed** where the node writes: the file's removals of a principal, a role or a credential are applied, and a disable or a narrowing waits for the next converge. `GET /ready` reports `access_converge_failed` (subject: the auth database) until a converge completes, which a reload does (**BL-1596, next train**). A removal that would leave the server auth database with no operator is left out whole, and a removal the store refuses is skipped while the rest go on.

## OIDC trusts and the issuer's key source

An issuer has one key source. When a declared OIDC trust names another key source than a runtime trust of the same issuer, the declared trust wins, and the plan, the start and the reload report the warning `OIDC_TRUST_JWKS_CONFLICT` (ADR 0071 `D-18`); delete the runtime trust, or declare the trust with the issuer's key source (**BL-1602, next train**).

## Replication

Only a node that accepts writes converges. A replica checks the section (an error still refuses its start) and writes nothing; a
reload on it answers `writes: skipped` with the changes it would make.

## Example: a shop

```json
{
  "version": 1,
  "databases": {
    "auth": {
      "kind": "auth",
      "signup": { "enabled": true, "roles": ["customer"], "statements": [] },
      "roles": {
        "customer": {
          "statements": [
            { "actions": ["read", "write"], "resources": ["shop/table/orders"],
              "where": { "and": [ { "column": "customer_id", "op": "eq", "principal": "id" } ] } }
          ]
        }
      },
      "principals": {
        "checkout": {
          "description": "The checkout service",
          "statements": [ { "actions": ["read", "write"], "resources": ["shop/table/orders"] } ]
        },
        "anonymous": {
          "statements": [ { "actions": ["execute"], "resources": ["shop/query/products.list"] } ]
        }
      }
    },
    "shop": { "kind": "data", "authDatabase": "auth", "schema": "schema/shop.aouda.schema.json" }
  }
}
```

A signed-up customer reads and writes only their own orders; the checkout service reads and writes every order; an unauthenticated
caller runs the product list and nothing else. `products.list` reads the `products` table: had it read `orders`, `anonymous`'s
`execute` would reach a table `customer` restricts, and the plan would refuse it (`AUTH_PUBLIC_UNRESTRICTED`).
