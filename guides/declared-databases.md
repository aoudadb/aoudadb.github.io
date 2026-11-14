---
title: "Declared databases"
nav_order: 2.6
parent: "Guides"
---

# Declared databases: `Aouda:Databases` (**BL-1379, 0.11.0**)

A database created through `POST /api/databases` lives in the data directory, so a wipe of that directory takes it away, and
whoever wiped it has to create it again, link it to its auth database and re-apply its schema. `Aouda:Databases` states the set
in configuration instead: **a wipe followed by a plain start brings back the same databases, the same links, the same schema and
the same roles, empty of data.** Nothing is declared by default; a server without `Aouda:Databases` behaves as it always did.

This page is the reference for the section and the walkthrough of a wipe. The keys that go with it are in
[Keys that survive a wipe](keys-that-survive-a-wipe.md); the other startup settings are in
[Server configuration](server-configuration.md) and [Defaults reference](defaults-reference.md#declared-databases).

---

## One entry, every key

An entry is `Aouda:Databases:<name>`. In `appsettings.json` it is a property of `Aouda.Databases`; in the environment it is
`Aouda__Databases__<name>__<Key>` (for example `Aouda__Databases__ledger__AuthDatabase=derive_auth`). Names follow the rules of
database names and are compared without case, so declaring `Ledger` and `ledger` is refused.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `Kind` | `string` | `data` | `data` (an ordinary database) or `auth` (an application auth database). Not case-sensitive; blank means `data`; anything else fails the start |
| `AuthDatabase` | `string?` | none | Only with `Kind: data`. The application auth database to link this one to |
| `SchemaFile` | `string?` | none | Only with `Kind: data`. Path of a schema file applied at start. Absolute, or relative to the server's working directory |
| `SchemaEnvironment` | `string?` | none | Needs `SchemaFile`. The overlay, as the CLI's `--env`: `aouda.schema.<env>.json` next to the file is merged over it when it exists |
| `SchemaAllowDestructive` | `bool` | `false` | Needs `SchemaFile`. Lets the start-time apply drop a table or a column. When `false` such a change is refused, logged, and the start goes on |
| `Roles:<role>` | object | none | Only with `Kind: auth`. A custom role of this auth database: `Description`, and `Permissions` (a list of `ResourceType`, `ResourceName`, `Actions`) |
| `Durability` | `string?` | `strict` | `strict`, `os`, `unlogged` or `memory` ([levels](write-durability.md#durability-levels-lead-s26-060)). On `Kind: auth` it must be absent or `strict` |
| `MaxMemoryShareBytes` | `long?` | none | Cap on this database's share of the memory budget; none or positive |
| `MemoryWeight` | `double` | `1.0` | Relative weight when the budget is divided; positive |
| `DefaultTemperature` | `string` | `Auto` | `Auto`, `HotOnly` or `ColdPreferred` for new tables |
| `ReplicationMode` | `string` | `Replicate` | `Replicate` or `DoNotReplicate` |
| `WriteConcern` | `string` | `One` | `One`, `Majority` or `All` |
| `WriteConcernTimeoutMs` | `int` | `5000` | How long to wait for acknowledgements; at least `100` |
| `OnWriteConcernTimeout` | `string` | `DegradeAndLog` | `Fail`, `Degrade` or `DegradeAndLog` |

`MaxMemoryBytes`, `EnableWal` and `DataDurability` were removed; any of them in an entry fails the start and the message names
the key that replaces it (`MaxMemoryShareBytes` and `MemoryWeight`, or `Durability`).

### Who owns what

Configuration owns the **operational fields** of a database it declares: `MaxMemoryShareBytes`, `MemoryWeight`,
`DefaultTemperature`, `Durability`, `ReplicationMode`, `WriteConcern`, `WriteConcernTimeoutMs` and `OnWriteConcernTimeout`. They are
re-applied at every start, so a change in the file wins over a change made through the API. (**BL-1427, next train**) A reload does
not re-apply them: a change to an operational field of a database that exists takes a restart (`aouda reload` lists it under
`restartRequired`). The catalog owns **everything else**,
including a database's signup settings (which are not declarable: a change made through `signup-settings` survives every
restart). A declaration creates what is missing, converges what it owns, and refuses what it cannot reconcile; it never
overwrites a field it does not name.

### How a declared database links to its auth database

`AuthDatabase` on a data database names an auth database, and the server records that link in the catalog. The auth database is
either declared in the same file with `Kind: auth`, or already in the catalog; it is **never created for you**. The passes run in
a fixed order whatever the order in the file: auth databases, then data databases, then links.

A declarative link sets the link and nothing else: it mints **no API key** and sets no signup field. A key minted at start would
have no reader, so it would be an orphan `db_admin` credential. The `anon`, `service_role` and `public` keys of a linked
database therefore do not exist after a wipe until an operator calls `regenerate-keys` (which returns them once); a
`POST /api/databases` that links still returns them as before. For keys that survive a wipe, declare them in the identities file
([Keys that survive a wipe](keys-that-survive-a-wipe.md)).

The start fails, naming the entry and changing nothing, when:

- an entry has an invalid `Kind`, or `Durability` other than `strict` on a `Kind: auth` entry;
- `AuthDatabase` is set on a `Kind: auth` entry, names the database itself, names a server bootstrap database (`_serverauth`, `_auth`, `_settings`) or names an entry declared with `Kind: data`;
- the named auth database is neither declared nor in the catalog, or is registered but not open, or is not an application auth database;
- the catalog already links the database to a **different** auth database;
- a declared `auth` entry is a data database in the catalog, or the reverse;
- the name is `_serverauth`, `_auth` or `_settings`, which the server owns.

A declared database that is registered but not open also fails the start. List it in `Aouda:SkipDatabases` to start without it
(a link to a skipped database fails the start). A database an **operator quarantined** (`aouda databases quarantine`) is skipped
with a warning, as quarantine is a deliberate isolation; a link to it still fails.

### Why `Roles` is only on an auth database

A role is a row of an application auth database: it names permissions that users and keys of every database linked to that
auth database receive. A `Roles` block on a `Kind: data` entry therefore has no place to live and fails the start
(`Roles can only be declared on a Kind 'auth' database`). Declare the roles on the auth database the data databases link to.

- Each role is created when missing and converged to the declared description and permissions when it exists. A role that is not declared is never touched, so roles made through the API stay.
- A `Permissions` item is `ResourceType` (`table`, the default; or `all-partitions`, `all-rows`, `embargo`; and, **BL-1417, 0.12.0**, `named-mutation` or `named-query`), `ResourceName` (a table name, or `*`; for a named artifact its exact name or `*`) and `Actions` (for a `table` item a comma-separated list, default `read`; for an all-* grant exactly one level; for a named artifact exactly `execute`), the same fields as `POST .../roles`. The same validator runs, so a `ResourceName` with a `*` that is not alone (`quote*`) fails the start (**BL-1415, 0.12.0**), as does an `execute` item with another `Actions`.
- Running a named query or mutation needs an `execute` item (**BL-1417, 0.12.0**): `{ "ResourceType": "named-mutation", "ResourceName": "insert_quote", "Actions": "execute" }`. The `quote_writer` role in the example below, which holds only a table `write`, does **not** run named mutations. At start the server logs one Warning per auth database naming the custom roles that hold table `read` / `write` and no execute row. See [Data Authorization §19.0](../auth/authorization.md#190-rbac-is-a-separate-gate-from-plsrls).
- A role name is compared without case: declaring one twice is refused. A role with no body is refused; write `{}` for a role with no description and no permissions.
- Roles are applied **after** the schema, so a permission may name a table the schema file creates.
- A system role cannot be declared, and the signup role of a database cannot carry an `all-partitions` or `all-rows` grant. Both fail the start.

Users are not declared. After a wipe an operator still creates the first users (the admin comes back from `Aouda:Auth:RootUser`).

---

## A full worked example

Two data databases share one application auth database. `ledger` has a schema file; `reports` is declared for its settings only.

```json
{
  "Aouda": {
    "Auth": {
      "RootUser": { "Email": "admin@example.com", "Password": "<from a secret>" },
      "Bootstrap": { "ServerKeyFile": "/run/secrets/aouda-server-key" }
    },
    "Databases": {
      "derive_auth": {
        "Kind": "auth",
        "Roles": {
          "quote_writer": {
            "Description": "Writes quotes, reads nothing else",
            "Permissions": [
              { "ResourceType": "table", "ResourceName": "quotes", "Actions": "write" }
            ]
          },
          "analyst": {
            "Description": "Reads every table",
            "Permissions": [ { "ResourceName": "*", "Actions": "read" } ]
          }
        }
      },
      "ledger": {
        "AuthDatabase": "derive_auth",
        "SchemaFile": "/etc/aouda/schemas/ledger.json",
        "SchemaEnvironment": "prod",
        "SchemaAllowDestructive": false,
        "MemoryWeight": 2.0
      },
      "reports": {
        "AuthDatabase": "derive_auth",
        "Durability": "os",
        "DefaultTemperature": "ColdPreferred"
      }
    }
  }
}
```

The same in the environment:

```bash
Aouda__Databases__derive_auth__Kind=auth
Aouda__Databases__ledger__AuthDatabase=derive_auth
Aouda__Databases__ledger__SchemaFile=/etc/aouda/schemas/ledger.json
Aouda__Databases__reports__AuthDatabase=derive_auth
Aouda__Databases__reports__Durability=os
```

(`Roles` are easier to keep in a file than in variables.) The schema file is the same `aouda.schema.json` the CLI applies, and `aouda schema check` validates it offline (**BL-1419, 0.12.0**; [Check a schema file offline](schema-check.md)); the start runs the same checks on every file before it changes any database; see
[Schema management](schema-management.md#let-the-server-apply-it-at-start). `quote_writer` names the table `quotes`, which the
schema file creates, which is why the roles are applied after it.

---

## Wipe and start

Delete the data directory and start the server with the configuration above. What is lost and what comes back:

| | After a wipe and a plain start |
|---|---|
| The databases `derive_auth`, `ledger`, `reports` | **Recreated**, empty |
| Their operational fields (memory, durability, replication, write concern) | **Recreated** from the entries |
| The links `ledger` and `reports` to `derive_auth` | **Recreated** |
| The first admin | **Recreated** from `Aouda:Auth:RootUser` |
| The tables of `ledger` | **Recreated** from `SchemaFile`; empty |
| The roles `quote_writer` and `analyst` | **Recreated** from `Roles` |
| Keys declared in configuration | **Recreated** as rows, with the same secrets ([keys](keys-that-survive-a-wipe.md)) |
| Every row of data | **Lost** |
| Users, sessions and refresh tokens of an application auth database | **Lost** |
| Signup settings of a database | **Lost** (catalog-owned; set them again) |
| Keys the server minted (`anon`, `service_role`, `public`, keys made through the API) | **Lost**; a new set exists only after `regenerate-keys` |
| Tables, roles and settings made only through the API | **Lost** |

### The order a start follows

(**BL-1463, next train**) **Before any of these steps, the start checks the whole declaration** — the settings, `Aouda:Databases`,
the identities file and every secret and schema file it names — and **creates nothing when one is refused**. It reports every
problem at once, each as a finding with a stable code (`KEY_SECRET_SHARED`, `SCHEMA_INVALID`, `ROLE_SYSTEM_NAME`, ...), where it is
(a setting and the source that set it, or a file and a JSON pointer) and what to do, then exits with status 78 (or 1 when the only
problem is a file that could not be read yet). Each step below then checks what it needs from the data directory before it changes
anything. The codes are listed in [Declaration Finding Codes](../reference/plan-codes.md).

After a wipe a plain start does these steps in this order, and a failure in any of them fails the start (the process exits, and
there is no `/ready` to ask):

1. **Configured keys are listed** (`Aouda:Auth:Bootstrap:ServerKey`, `Keys:File`). A bad declaration fails here, before any database opens. Nothing is authenticated yet.
2. **Declared databases**: auth databases, then data databases, then the links.
3. **`_serverauth` and `Aouda:Auth:RootUser`**: the first admin. Without a `RootUser` the server stays in setup mode.
4. **Declared schema files**: every file was read and validated before step 1 (**BL-1463, next train**: before any database is created), then applied in the server with its own privileges, with no API key. A table it creates refuses HTTP DDL, as one made by `schema apply`. A change the file asks for and the server **refuses** (a drop without `SchemaAllowDestructive`) does not fail the start; it is logged, and `/ready` reports `schema_drift`.
5. **Declared roles**, in their auth databases.
6. **Configured key rows**, in their auth databases.
7. The server is marked ready.

Re-running a converged start is a no-op: the schema diff is empty and nothing is written. Deleting a declared database through
the API is undone by the next start, which creates it again, empty. A database you remove from the file is left alone; a
declaration cannot say "must not exist".

### Changing the declaration without a restart (**BL-1427, next train**)

`aouda reload` (or `POST /api/admin/reload`, a server key only) re-reads the declaration of a running server, validates it as a start
would, and converges it in the order above: steps 2, 4, 5 and 6 (`_serverauth`, the root user and setup mode are the start's). What
a reload applies:

- a **new** `Aouda:Databases` entry (created, and linked to its auth database);
- a declared database's `SchemaFile` and `SchemaEnvironment` — the file is read again and applied **non-destructively** whatever
  `SchemaAllowDestructive` says (a destructive change is the warning `SCHEMA_DESTRUCTIVE_REFUSED`, and `/ready` keeps `schema_drift`);
- the `Roles` of a declared auth database;
- the `AuthDatabase` of a database that has **no link yet**.

What it does not: a database's operational fields, `SchemaAllowDestructive`, `Aouda:SkipDatabases` and every other setting are
`restartRequired` (listed, not applied; the rest proceeds). A `Kind` change and a change of an existing link are **errors** — the next
start refuses them, so the reload does too, and changes nothing. A database you remove from the file is reported as `orphaned` and
left alone. `Aouda:Databases` set by environment variables or the command line cannot change by reload (`SOURCE_NOT_RELOADABLE`).
`POST /api/admin/reload?dryRun=true` answers the same plan and changes nothing.

### What `/ready` says while it starts

`GET /ready` needs no credential and answers `503` with every reason that still holds, or `200` with `"reasons": []`
([reference](../reference/http-api.md#get-ready)). Over the course of the wipe-and-start above you can see:

| `code` (`subject`) | When | Ends when |
|---|---|---|
| `not_initialized` | The engine is still opening databases | They are open |
| `startup_delay` | `Aouda:Health:StartupDelaySeconds` has not passed | It has |
| `database_pending` (the database) | A declared database does not exist yet | Step 2 created it |
| `database_not_open` (the database) | A declared database is registered but failed to open, or is quarantined by something other than an operator | It opens; otherwise it stays, and so does the 503 |
| `server_starting` | The auth bootstrap has not finished | Step 7 |
| `setup_required` | No admin exists | `RootUser` or a `create-admin` created it |
| `root_user_unusable` | `RootUser` is set but its password cannot be used | You fix the password |
| `schema_pending` (the database) | Its `SchemaFile` has not been applied yet | Step 4 applied it |
| `schema_drift` (the database) | The apply refused a change; the catalog is not what the file says | You allow the change or update the file, and restart (a reload never applies a destructive change) |
| `reload_failed` (the entry, when one is named) | (**BL-1427, next train**) The last reload stopped part-way; the steps before it are applied | The next reload that completes |
| `configured_key_inactive` (the key's name) | A configured key cannot authenticate yet | A server key waits for the first admin, a scoped key for its auth database and database to be open |
| `database_reconcile_failed` (the database) | Only after a backup restore: the reconcile of `Aouda:Databases` was refused. The server keeps running | You fix the declaration or the catalog; the next process start fails on it until then |
| `component_unhealthy` (the component) | A critical component is not healthy | It recovers |

A deploy script waits for `200` and prints `reasons` if it gives up. A database in `Aouda:SkipDatabases`, or one an operator
quarantined, is a decision and is not listed. `aouda status` prints every reason.

---

## Related

- [Keys that survive a wipe](keys-that-survive-a-wipe.md): declaring keys in configuration
- [Check a schema file offline](schema-check.md) and [Upgrading and the data-directory format](upgrading.md)
- [Schema management: let the server apply it at start](schema-management.md#let-the-server-apply-it-at-start)
- [Server and multi-database](server-multi-database.md#per-database-settings-aoudadatabasesname)
- [Defaults reference: declared databases](defaults-reference.md#declared-databases)
- [HTTP API: `GET /ready`](../reference/http-api.md#get-ready)
