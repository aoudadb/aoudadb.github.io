---
title: "Policy"
nav_order: 2
parent: "Auth and Authorization"
---

# Policy: statements, actions and row conditions (**BL-1464, 0.16.0**)

Nothing grants access except a statement. A credential does not. A role name does not, except as a bundle of statements. A table carries no security of its own.

## Statements

One JSON shape, in the declaration, the API, `whoami` and a refusal's remedy:

<!-- declaration-example -->
```json
{
 "version": 1,
 "databases": {
 "auth": {
 "kind": "auth",
 "roles": {
 "rates-feeder": {
 "description": "Writes the rows its source may publish.",
 "statements": [
 {
 "actions": ["write"],
 "resources": ["rates/table/DepositQuote"],
 "where": { "column": "source", "op": "in", "value": ["tullett"] }
 }
 ]
 }
 }
 }
 }
}
```

`actions` and `resources` are required. `where`, `embargoSeconds` and `unrestricted` are optional. A principal's policy is its own statements plus the statements of its roles, plus the `signup` statements when `source` is `signup`.

## Actions

Six actions. `*` means all six.

| Action | What it allows |
|---|---|
| `read` | Read rows of a table resource. A read the `where` does not admit is **filtered out**, not refused. |
| `write` | Insert and update rows. A row the `where` does not admit is `403 AUTH_ROW_DENIED`. |
| `delete` | Delete rows, under the same row rule as `write`. |
| `execute` | Run a named query or named mutation. See [Execute](#execute). |
| `manage` | Administer the resource: a database, a principal, a role, or `server`. |
| `set-identity` | Supply the caller identity on a column the table stamps. Not implied by any other action. |

`crossPartitionAccess` on a query waives the cost of reading across partitions. It does not show a row the caller's `read` statements do not admit.

## Resources

A resource is a path.

| Path | What it is |
|---|---|
| `<db>` | The database |
| `<db>/table/<table>` | A table. `*` is every table. |
| `<db>/query/<name>` | A named query |
| `<db>/mutation/<name>` | A named mutation |
| `<auth>/principal/<name>` | A principal |
| `<auth>/role/<name>` | A role |
| `server` | The server itself (`manage` here is an operator) |
| `*` | Everything the principal's auth database may govern |

**Case.** Tables and named artifacts are compared ordinally: `DepositQuote` is not `depositquote`. Principals, roles and databases are compared without regard to case; the stored spelling is what answers.

A statement on a resource the principal's auth database does not govern is refused at write time. See [Auth databases](principals.md#auth-databases).

## Row conditions

`where` is the row condition. The grammar the server accepts:

- a comparison: `{ "column", "op", "value" }` with `op` one of `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `nin`
- a hole: `{ "column", "op": "eq", "principal": "id" }` or `"principal": "name"`, or `{ "column", "op": "in", "principal": "attributes.<name>" }`
- `ignoreCase` on a string comparison
- a group: `{ "and": [... ] }`, `{ "or": [... ] }`

A missing attribute, a value that cannot be bound, or several values under a scalar operator match no row. A `write` statement's `where` is decided on the row **as stored** — after defaults are filled and a derived `Decimal` is rounded — and an upsert that replaces a row is decided on the row it commits, under the commit, so a concurrent writer cannot slip a replaced row past it. A **formula row** (an `Expression` column's row) is admitted only by a statement whose `where` does not name the column it computes from; every refusal is `403 AUTH_ROW_DENIED` with remedy `none`. A multi-row upsert refused under a concurrent writer may have written its other rows (BL-1716).

An update's scope is the `write` statement's `where` alone. `returning` shows only rows the caller's `read` admits: a row the write touched and the read does not admit is omitted from the response, not returned under another principal's eyes.

## Embargo

`embargoSeconds` on a `read` or `execute` statement hides rows newer than that many seconds. It does not ban a write. A load, an insert and an update are the `write` statement's question, not the embargo's. A surface that cannot honour an embargo is `403 AUTH_EMBARGO_UNSUPPORTED` with remedy `none`.

## Execute

`execute` on a named query or named mutation runs that artifact. The artifact's own `where` scopes its primary table. Joins inside the artifact are unrestricted: the artifact author decided them, and `execute` is the grant to run that decision. A table `read` does not run an artifact, and `execute` does not grant the table API.

On the data plane, a named artifact the caller may not execute is the unknown-name `404` (`NAMED_QUERY_NOT_FOUND` or `NAMED_MUTATION_NOT_FOUND`), the same answer as an artifact that does not exist.

## Public reach

When any statement restricts a table with a `where`, `anonymous` and `signup` (and the roles they hold) may not read that table with no `where`. The refusal is `400 AUTH_PUBLIC_UNRESTRICTED`, remedy `add-where`, naming the table and the statement that restricts it. Mark the public statement `"unrestricted": true` when every row is meant to be public.

No publicly reachable statement may `manage`. `unrestricted` does not make `manage` public.

Write the restricting statement and the public statement in an order the check can see: a plan reports `AUTH_PUBLIC_UNRESTRICTED` against the declaration as a whole, so both statements are visible together.

## Grant only what you hold

A principal may grant a statement only when its own policy covers that statement: the same action and resource, and a `where` at least as narrow. Granting another principal a credential is the same rule — you cannot hand out a key for a policy you do not yourself hold.

A `where` that reads `principal.id` or `principal.name` covers only its own holder. Resetting another principal's password, or editing that principal's statements, needs those rows unconditionally.

Deleting a role, renaming it, or removing a statement from it changes every holder, so the writer must cover each holder's whole policy. A disabled principal holds nothing, whatever its policy says.

The remedy when this fails is `403 AUTH_POLICY_DENIED` with `grant`.

## Audit

A statement with no `where` on a table that other statements restrict is unconditional access. Each use writes an audit row of kind `unconditional_access`. The detail names the principal, the action and the resource. It is the record that a wide statement was used, not a second grant.

## Worked examples

**A rates feeder.** The fragment at the top of this page. The feeder's key is derived; the principal is `auth/rates-feeder`. A write whose `source` is not `tullett` is `403 AUTH_ROW_DENIED`.

```text
aouda policy explain --declaration aouda.json --as auth/rates-feeder ^
 --action write --resource rates/table/DepositQuote ^
 --row "{\"source\":\"other\"}"
```

Exit `2`. The answer's `remedy.kind` is `grant` and `row.admitted` is `false`.

**A multi-tenant application.** Each tenant is an attribute, not a database.

<!-- declaration-example -->
```json
{
 "version": 1,
 "databases": {
 "auth": {
 "kind": "auth",
 "principals": {
 "shop-backend": {
 "attributes": { "tenant": ["acme"] },
 "statements": [
 {
 "actions": ["read", "write", "delete"],
 "resources": ["shop/table/orders"],
 "where": { "column": "tenant", "op": "in", "principal": "attributes.tenant" }
 }
 ]
 }
 }
 }
 }
}
```

**A browser-tier read-only app.** No key. `anonymous` may execute one named query.

<!-- declaration-example -->
```json
{
 "version": 1,
 "databases": {
 "auth": {
 "kind": "auth",
 "principals": {
 "anonymous": {
 "statements": [
 { "actions": ["execute"], "resources": ["shop/query/public-catalog"] }
 ]
 }
 }
 }
 }
}
```

**An embargoed reader.** Fifteen minutes.

<!-- declaration-example -->
```json
{
 "version": 1,
 "databases": {
 "auth": {
 "kind": "auth",
 "roles": {
 "delayed-reader": {
 "statements": [
 {
 "actions": ["read"],
 "resources": ["rates/table/DepositQuote"],
 "embargoSeconds": 900
 }
 ]
 }
 }
 }
 }
}
```
