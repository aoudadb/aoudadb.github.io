---
title: "Declared databases"
nav_order: 2.6
parent: "Guides"
---

# Declared databases: `databases` in `aouda.json` (**BL-1379, 0.11.0**; in the declaration file since **BL-1463, next train**)

A database created through `POST /api/databases` lives in the data directory, so a wipe of that directory takes it away, and
whoever wiped it has to create it again, link it to its auth database and re-apply its schema. The `databases` of the
[declaration file](declaration.md) states the set instead: **a wipe followed by a plain start brings back the same databases, the same links, the same schema and
the same roles, empty of data.** Nothing is declared by default; a server without `Aouda:Declaration` behaves as it always did.

(**BL-1463, next train**) The set used to be `Aouda:Databases`, a section of `appsettings.json` or of the environment. **That is no longer read**: a server that finds one of its settings refuses to start (`SETTING_REMOVED`) and the message names the member of `aouda.json` that replaces it. The mapping is in [Declare a server in one file](declaration.md#from-aoudadatabases).

This page is the reference for the section and the walkthrough of a wipe. The keys that go with it are in
[Keys that survive a wipe](keys-that-survive-a-wipe.md); the other startup settings are in
[Server configuration](server-configuration.md) and [Defaults reference](defaults-reference.md#declared-databases).

---

## One entry, every member

(**BL-1463, next train**) An entry is `databases.<name>` in `aouda.json`; the member name is the database's name. Names follow the
rules of database names and are compared without case, so declaring `Ledger` and `ledger` is refused. The exact JSON of every
member, with its type, is the [reference](../reference/declaration.md#databasesname); in short:

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `kind` | string | none, **required** | `"data"` (an ordinary database) or `"auth"` (an application auth database). Not case-sensitive; anything else, or none, fails the start |
| `authDatabase` | string | none | Only with `"kind": "data"`. The application auth database to link this one to |
| `schema` | string | none | Only with `"kind": "data"`. Path of a schema file applied at start. Absolute, or relative to the directory of `aouda.json` |
| `schemaAllowDestructive` | boolean | `false` | Needs `schema`. Lets the start-time apply drop a table or a column. When `false` such a change is refused, logged, and the start goes on |
| `roles` | object | none | Only with `"kind": "auth"`. Custom roles of this auth database, keyed by role name: `description`, and `permissions` (a list of `resourceType`, `resourceName`, `actions`) |
| `durability` | string | `"strict"` | `"strict"`, `"os"`, `"unlogged"` or `"memory"` ([levels](write-durability.md#durability-levels-lead-s26-060)). On `"kind": "auth"` it must be absent or `"strict"` |
| `maxMemoryShareBytes` | integer | none | Cap on this database's share of the memory budget; none, or not negative |
| `memoryWeight` | number | `1` | Relative weight when the budget is divided; positive |
| `defaultTemperature` | string | `"Auto"` | `"Auto"`, `"HotOnly"` or `"ColdPreferred"` for new tables |
| `replicationMode` | string | `"Replicate"` | `"Replicate"` or `"DoNotReplicate"` |
| `writeConcern` | string | `"One"` | `"One"`, `"Majority"` or `"All"` |
| `writeConcernTimeoutMs` | integer | `5000` | How long to wait for acknowledgements; at least `100` |
| `onWriteConcernTimeout` | string | `"DegradeAndLog"` | `"Fail"`, `"Degrade"` or `"DegradeAndLog"` |

The environment that selects a schema file's overlay is no longer a member of the entry: it is the process setting
`Aouda:Environment` (`--env`, `AOUDA_ENVIRONMENT`), one for the whole server. The old `MaxMemoryBytes`, `EnableWal` and
`DataDurability` stay refused; the message names `maxMemoryShareBytes` and `memoryWeight`, or `durability`.

### Who owns what

The declaration owns the **operational fields** of a database it declares: `maxMemoryShareBytes`, `memoryWeight`,
`defaultTemperature`, `durability`, `replicationMode`, `writeConcern`, `writeConcernTimeoutMs` and `onWriteConcernTimeout`. They are
re-applied at every start, so a change in the file wins over a change made through the API. (**BL-1427, 0.14.0**) A reload does
not re-apply them: a change to an operational field of a database that exists takes a restart (`aouda reload` lists it under
`restartRequired`). The catalog owns **everything else**,
including a database's signup settings (which are not declarable: a change made through `signup-settings` survives every
restart). A declaration creates what is missing, converges what it owns, and refuses what it cannot reconcile; it never
overwrites a field it does not name.

### How a declared database links to its auth database

`authDatabase` on a data database names an auth database, and the server records that link in the catalog. The auth database is
either declared in the same file with `"kind": "auth"`, or already in the catalog; it is **never created for you**. The passes run in
a fixed order whatever the order in the file: auth databases, then data databases, then links.

A declarative link sets the link and nothing else: it mints **no API key** and sets no signup field. A key minted at start would
have no reader, so it would be an orphan `db_admin` credential. The `anon`, `service_role` and `public` keys of a linked
database therefore do not exist after a wipe until an operator calls `regenerate-keys` (which returns them once); a
`POST /api/databases` that links still returns them as before. For keys that survive a wipe, declare them in the identities file
([Keys that survive a wipe](keys-that-survive-a-wipe.md)).

The start fails, naming the entry and changing nothing, when:

- an entry has an invalid or no `kind`, or a `durability` other than `strict` on a `"kind": "auth"` entry;
- `authDatabase` is set on a `"kind": "auth"` entry, names the database itself, names a server bootstrap database (`_serverauth`, `_auth`, `_settings`) or names an entry declared with `"kind": "data"`;
- the named auth database is neither declared nor in the catalog, or is registered but not open, or is not an application auth database;
- the catalog already links the database to a **different** auth database;
- a declared `auth` entry is a data database in the catalog, or the reverse;
- the name is `_serverauth`, `_auth` or `_settings`, which the server owns.

A declared database that is registered but not open also fails the start. List it in `Aouda:SkipDatabases` to start without it
(a link to a skipped database fails the start). A database an **operator quarantined** (`aouda databases quarantine`) is skipped
with a warning, as quarantine is a deliberate isolation; a link to it still fails.

### Why `roles` is only on an auth database

A role is a row of an application auth database: it names permissions that users and keys of every database linked to that
auth database receive. A `roles` member on a `"kind": "data"` entry therefore has no place to live and fails the start
(`Roles can only be declared on a Kind 'auth' database`). Declare the roles on the auth database the data databases link to.

- Each role is created when missing and converged to the declared description and permissions when it exists. A role that is not declared is never touched, so roles made through the API stay.
- A `permissions` item is `resourceType` (`table`, the default; or `all-partitions`, `all-rows`, `embargo`; and, **BL-1417, 0.12.0**, `named-mutation` or `named-query`), `resourceName` (a table name, or `*`; for a named artifact its exact name or `*`) and `actions` (for a `table` item a comma-separated list, default `read`; for an all-* grant exactly one level; for a named artifact exactly `execute`), the same fields as `POST .../roles`. The same validator runs, so a `resourceName` with a `*` that is not alone (`quote*`) fails the start (**BL-1415, 0.12.0**), as does an `execute` item with other `actions`.
- Running a named query or mutation needs an `execute` item (**BL-1417, 0.12.0**): `{ "resourceType": "named-mutation", "resourceName": "insert_quote", "actions": "execute" }`. The `quote_writer` role in the example below, which holds only a table `write`, does **not** run named mutations. At start the server logs one Warning per auth database naming the custom roles that hold table `read` / `write` and no execute row. See [Data Authorization §19.0](../auth/authorization.md#190-rbac-is-a-separate-gate-from-plsrls).
- A role name is compared without case: declaring one twice is refused. A role with no body is refused; write `{}` for a role with no description and no permissions.
- Roles are applied **after** the schema, so a permission may name a table the schema file creates.
- A system role cannot be declared, and the signup role of a database cannot carry an `all-partitions` or `all-rows` grant. Both fail the start.

Users are not declared. After a wipe an operator still creates the first users (the admin comes back from `Aouda:Auth:RootUser`).

---

## A full worked example

Two data databases share one application auth database. `ledger` has a schema file; `reports` is declared for its settings only.
The server is started with `Aouda__Declaration=/etc/aouda/aouda.json` and `AOUDA_ENVIRONMENT=prod` (settings: they name the file,
they are not in it).

`/etc/aouda/aouda.json`:

```jsonc
{
  "$schema": "https://aoudadb.github.io/schemas/aouda-declaration.v1.json",
  "version": 1,
  "databases": {
    "derive_auth": {
      "kind": "auth",
      "roles": {
        "quote_writer": {
          "description": "Writes quotes, reads nothing else",
          "permissions": [
            { "resourceType": "table", "resourceName": "quotes", "actions": "write" }
          ]
        },
        "analyst": {
          "description": "Reads every table",
          "permissions": [ { "resourceName": "*", "actions": "read" } ]
        }
      }
    },
    "ledger": {
      "kind": "data",
      "authDatabase": "derive_auth",
      "schema": "schemas/ledger.json",       // relative to /etc/aouda; its prod overlay is schemas/ledger.prod.json
      "schemaAllowDestructive": false,
      "memoryWeight": 2
    },
    "reports": {
      "kind": "data",
      "authDatabase": "derive_auth",
      "durability": "os",
      "defaultTemperature": "ColdPreferred"
    }
  }
}
```

The first admin and the server key are not in this file yet: they are `Aouda:Auth:RootUser` and `Aouda:Auth:Bootstrap:ServerKeyFile`
in `appsettings.json` or the environment, as before.

The schema file is the same `aouda.schema.json` the CLI applies, and `aouda plan --declaration /etc/aouda/aouda.json --env prod` validates it offline (**BL-1463, 0.14.0**; it replaced `aouda schema check`, **BL-1419, 0.12.0**; [Plan a declaration](plan.md)); the start runs the same checks on every file before it changes any database; see
[Schema management](schema-management.md#let-the-server-apply-it-at-start). `quote_writer` names the table `quotes`, which the
schema file creates, which is why the roles are applied after it.

---

## Wipe and start

Delete the data directory and start the server with the declaration above. What is lost and what comes back:

| | After a wipe and a plain start |
|---|---|
| The databases `derive_auth`, `ledger`, `reports` | **Recreated**, empty |
| Their operational fields (memory, durability, replication, write concern) | **Recreated** from the entries |
| The links `ledger` and `reports` to `derive_auth` | **Recreated** |
| The first admin | **Recreated** from `Aouda:Auth:RootUser` |
| The tables of `ledger` | **Recreated** from `schema`; empty |
| The roles `quote_writer` and `analyst` | **Recreated** from `roles` |
| Keys declared in configuration | **Recreated** as rows, with the same secrets ([keys](keys-that-survive-a-wipe.md)) |
| Every row of data | **Lost** |
| Users, sessions and refresh tokens of an application auth database | **Lost** |
| Signup settings of a database | **Lost** (catalog-owned; set them again) |
| Keys the server minted (`anon`, `service_role`, `public`, keys made through the API) | **Lost**; a new set exists only after `regenerate-keys` |
| Tables, roles and settings made only through the API | **Lost** |

### The order a start follows

(**BL-1463, 0.14.0**) **Before any of these steps, the start checks the whole declaration** — the settings, the declaration file (**BL-1463, next train**),
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
4. **Declared schema files**: every file was read and validated before step 1 (**BL-1463, 0.14.0**: before any database is created), then applied in the server with its own privileges, with no API key. A table it creates refuses HTTP DDL, as one made by `schema apply`. A change the file asks for and the server **refuses** (a drop without `schemaAllowDestructive`) does not fail the start; it is logged, and `/ready` reports `schema_drift`.
5. **Declared roles**, in their auth databases.
6. **Configured key rows**, in their auth databases.
7. The server is marked ready.

Re-running a converged start is a no-op: the schema diff is empty and nothing is written. The diff compares the file with the
database's tables as `aouda schema export` shows them, which never includes the engine's own scratch tables: a materialized
query's build table, `__mqbuild_<query>_<id>`, which exists while the query rebuilds. A restart rebuilds, in the background and
while step 4 runs, every materialized query whose result it cannot restore exactly (after an unclean stop, for example), so
those tables are routinely there; they are not drift, and the apply neither reports nor drops them (**BL-1468, 0.14.0**). On
0.13.0 it did: `/ready` answered `503` `schema_drift` with one `refused: DropTable __mqbuild_…: Destructive change requires
AllowDestructive: true` per query, and with `SchemaAllowDestructive: true` it dropped them under the running rebuilds, which left
each of those queries in `Error` (its query answers `400`, not ready) until a `:refresh`. No data was lost either way. Do not set
`schemaAllowDestructive` to get past it.

**Table names in a schema file** follow the one [table-name rule](../reference/http-api.md#table-names): no `/ \ : * ? " < > |`,
no leading or trailing period or space, not empty, `.` or `..`, and no `__mqbuild_` prefix (**BL-1468, 0.14.0; breaking**).
Before, the schema apply created such a table; now a file that declares one fails `aouda plan` and **fails the start**,
naming the database, the file and the rule — also for a table the database already has. A schema file has no rename and HTTP DDL
on a declared table is refused, so the way out is a clean cut: read the table's rows out (for example with `POST …/query`), give
the table a legal name in the file, start once with `"schemaAllowDestructive": true` (the apply creates the new table and drops the
old one) or on a fresh data directory, set `schemaAllowDestructive` back, and load the rows into the new table.

Deleting a declared database through
the API is undone by the next start, which creates it again, empty. A database you remove from the file is left alone; a
declaration cannot say "must not exist".

### Changing the declaration without a restart (**BL-1427, 0.14.0**)

`aouda reload` (or `POST /api/admin/reload`, a server key only) re-reads the declaration of a running server, validates it as a start
would, and converges it in the order above: steps 2, 4, 5 and 6 (`_serverauth`, the root user and setup mode are the start's). What
a reload applies:

- (**BL-1463, next train**) the declaration file itself and its overlay: they are read again, from the path the running server was
  started with, at every reload;
- a **new** `databases` entry (created, and linked to its auth database);
- a declared database's `schema` (and its overlay) — the file is read again and applied **non-destructively** whatever
  `schemaAllowDestructive` says (a destructive change is the warning `SCHEMA_DESTRUCTIVE_REFUSED`, and `/ready` keeps `schema_drift`);
- the `roles` of a declared auth database;
- the `authDatabase` of a database that has **no link yet**.

What it does not: a database's operational fields, `schemaAllowDestructive`, `Aouda:SkipDatabases` and every other setting are
`restartRequired` (listed, not applied; the rest proceeds). A changed `Aouda:Declaration` or `Aouda:Environment` is `restartRequired`
too and is **not followed**: the reload reads the file the server started with. A `kind` change and a change of an existing link are
**errors** — the next start refuses them, so the reload does too, and changes nothing. A database you remove from the file is
reported as `orphaned` and left alone. A declaration file that has disappeared, or cannot be read, refuses the reload and changes
nothing (it is not read as an empty declaration that retracts every database).
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
| `setup_required` | Nothing is declared (no server key, no `RootUser`) and no admin exists | `RootUser` created it at start, or `POST /api/auth/setup` did; a declared server key means no setup mode at all (**BL-1462, 0.14.0**) |
| `root_user_unusable` | `RootUser` is set but its password cannot be used | You fix the password |
| `schema_pending` (the database) | Its `schema` file has not been applied yet | Step 4 applied it |
| `schema_applying` (the database) | Step 4 is applying its `schema` file now; `progress` is `{ "done": n, "total": m }` over the declared schema files (**BL-1462, 0.14.0**) | Step 4 finished it |
| `schema_drift` (the database) | The apply refused a change; the catalog is not what the file says | You allow the change or update the file, and restart (a reload never applies a destructive change) |
| `reload_failed` (the entry, when one is named) | (**BL-1427, 0.14.0**) The last reload stopped part-way; the steps before it are applied | The next reload that completes |
| `configured_key_inactive` (the key's name) | A configured key cannot authenticate yet | Its auth database and database are open. A server key no longer waits for a first admin (**BL-1462, 0.14.0**) |
| `database_reconcile_failed` (the database) | Only after a backup restore: the reconcile of the declared databases was refused. The server keeps running | You fix the declaration or the catalog; the next process start fails on it until then |
| `component_unhealthy` (the component) | A critical component is not healthy | It recovers |

A deploy script waits for `200` and prints `reasons` if it gives up. A database in `Aouda:SkipDatabases`, or one an operator
quarantined, is a decision and is not listed. `aouda status` prints every reason.

---

## Related

- [Declare a server in one file](declaration.md) and its [reference](../reference/declaration.md): the file, where it is found, overlays
- [Keys that survive a wipe](keys-that-survive-a-wipe.md): declaring keys in configuration
- [Plan a declaration](plan.md) and [Upgrading and the data-directory format](upgrading.md)
- [Schema management: let the server apply it at start](schema-management.md#let-the-server-apply-it-at-start)
- [Server and multi-database](server-multi-database.md#per-database-settings-databases-in-aoudajson)
- [Defaults reference: declared databases](defaults-reference.md#declared-databases)
- [HTTP API: `GET /ready`](../reference/http-api.md#get-ready)
