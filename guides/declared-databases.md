---
title: "Declared databases"
nav_order: 2.6
parent: "Guides"
---

# Declared databases: `databases` in `aouda.json` (**BL-1379, 0.11.0**; in the declaration file since **BL-1463, 0.16.0**)

A database created through `POST /api/databases` lives in the data directory, so a wipe of that directory takes it away, and
whoever wiped it has to create it again, link it to its auth database and re-apply its schema. The `databases` of the
[declaration file](declaration.md) states the set instead: **a wipe followed by a plain start brings back the same databases, the same links, the same schema and
the same roles, empty of data.** Nothing is declared by default; a server without `Aouda:Declaration` behaves as it always did.

(**BL-1463, 0.16.0**) The set used to be `Aouda:Databases`, a section of `appsettings.json` or of the environment. **That is no longer read**: a server that finds one of its settings refuses to start (`SETTING_REMOVED`) and the message names the member of `aouda.json` that replaces it. The mapping is in [Declare a server in one file](declaration.md#from-aoudadatabases).

This page is the reference for the section and the walkthrough of a wipe. The keys that go with it are in
[Keys that survive a wipe](keys-that-survive-a-wipe.md); the other startup settings are in
[Server configuration](server-configuration.md) and [Defaults reference](defaults-reference.md#declared-databases).

---

## One entry, every member

(**BL-1463, 0.16.0**) An entry is `databases.<name>` in `aouda.json`; the member name is the database's name. Names follow the
rules of database names and are compared without case, so declaring `Ledger` and `ledger` is refused. The exact JSON of every
member, with its type, is the [reference](../reference/declaration.md#databasesname); in short:

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `kind` | string | none, **required** | `"data"` (an ordinary database) or `"auth"` (an application auth database). Not case-sensitive; anything else, or none, fails the start |
| `authDatabase` | string | none | Only with `"kind": "data"`. The application auth database to link this one to |
| `schema` | string | none | Only with `"kind": "data"`. Path of a schema file applied at start. Absolute, or relative to the directory of `aouda.json` |
| `schemaAllowDestructive` | boolean | `false` | Needs `schema`. Lets the start-time apply drop a table or a column. When `false` such a change is refused, logged, and the start goes on |
| `roles` | object | none | Only with `"kind": "auth"`. The roles of this auth database, keyed by role name: `description` and `statements` (**BL-1464, 0.16.0**: the `permissions` list is refused naming `statements`; see [Declared access](declared-access.md)) |
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

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
`POST /api/databases` that links still returns them as before. For keys that survive a wipe, declare their principals with
`credentials` in the same file (**BL-1464, 0.16.0**; [Keys that survive a wipe](keys-that-survive-a-wipe.md)).

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

A role belongs to an application auth database: the principals of that auth database hold it, on the databases linked to it. A `roles`
member on a `"kind": "data"` entry therefore has no place to live and fails the start (`DATABASE_FIELD_NOT_FOR_KIND`). Declare the
roles on the auth database the data databases link to.

**BL-1464, 0.16.0:** a declared role is `{ "description"?, "statements": [ … ] }` — the access model's statements, not the old
`permissions` list — and it is the file's, whole: created, converged and removed by every start and reload, with `signup` and the
auth database's principals beside it. A runtime role of the same name is refused rather than taken over. Roles are converged after
the schema, so a statement may name a table the schema file creates. See [Declared access](declared-access.md) for the rules, the
ownership and the emergency action, and [The declaration file](../reference/declaration.md) for the exact JSON.

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
          "statements": [
            { "actions": ["write"], "resources": ["ledger/table/quotes"] }
          ]
        },
        "analyst": {
          "description": "Reads every table",
          "statements": [ { "actions": ["read"], "resources": ["ledger/table/*", "reports/table/*"] } ]
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

The first admin and the operator's key are in this file too (**BL-1464, 0.16.0**): a `server.principals` entry holding the role
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

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
| The first admin and the declared operators | **Recreated** from `server.principals` (a password seed is applied again, as to a new principal) |
| The tables of `ledger` | **Recreated** from `schema`; empty |
| The roles `quote_writer` and `analyst` | **Recreated** from `roles` |
| Declared principals and their credentials | **Recreated**, with the same ids; a derived key is the same key, a stored key the same id and hash ([keys](keys-that-survive-a-wipe.md)) |
| Every row of data | **Lost** |
| Users, sessions and refresh tokens of an application auth database | **Lost** |
| Signup settings of a database | **Lost** (catalog-owned; set them again) |
| Tables, roles and settings made only through the API | **Lost** |

### The order a start follows

(**BL-1463, 0.14.0**) **Before any of these steps, the start checks the whole declaration** — the settings, the declaration file (**BL-1463, 0.16.0**),
every secret and schema file it names — and **creates nothing when one is refused**. It reports every
problem at once, each as a finding with a stable code (`SETTING_REMOVED`, `KEY_ID_DUPLICATE`, `SCHEMA_INVALID`, ...), where it is
(a setting and the source that set it, or a file and a JSON pointer) and what to do, then exits with status 78 (or 1 when the only
problem is a file that could not be read yet). Each step below then checks what it needs from the data directory before it changes
anything. The codes are listed in [Declaration Finding Codes](../reference/plan-codes.md).

After a wipe a plain start does these steps in this order, and a failure in any of them fails the start (the process exits, and
there is no `/ready` to ask):

1. **Declared databases**: auth databases, then data databases, then the links.
2. **`_serverauth`**: created for an operator declared in `server.principals` (**BL-1464, 0.16.0**). With none declared and no admin, the server stays in setup mode.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
4. **Declared access** (**BL-1464, 0.16.0**): roles, `signup`, principals and their credentials, in their auth databases ([Declared access](declared-access.md)). It replaces the configured key rows, which came last.
5. The server is marked ready.

Re-running a converged start is a no-op: the schema diff is empty and nothing is written. The diff compares the file with the
database's tables as `aouda schema export` shows them, which never includes the engine's own scratch tables: a materialized
query's build table, `__mqbuild_<query>_<id>`, which exists while the query rebuilds. A restart rebuilds, in the background and
while step 3 runs, every materialized query whose result it cannot restore exactly (after an unclean stop, for example), so
those tables are routinely there; they are not drift, and the apply neither reports nor drops them (**BL-1468, 0.14.0**). On
0.13.0 it did: `/ready` answered `503` `schema_drift` with one `refused: DropTable __mqbuild_…: Destructive change requires
AllowDestructive: true` per query, and with `SchemaAllowDestructive: true` it dropped them under the running rebuilds, which left
each of those queries in `Error` (its query answers `400`, not ready) until a `:refresh`. No data was lost either way. Do not set
`schemaAllowDestructive` to get past it.

**Table names in a schema file** follow the one [table-name rule](../reference/http-api.md#table-names): no `/ \ : * ? " < > |`,
no leading or trailing period or space, not empty, `.` or `..`, and no `__mqbuild_` prefix (**BL-1468, 0.14.0; breaking**).
Before, the schema apply created such a table; now a file that declares one fails `aouda plan` and **fails the start**,
naming the database, the file and the rule — also for a table the database already has. A schema file has no rename and HTTP DDL
on a declared schema is refused (`409 DECLARED_IN_CONFIGURATION`, **BL-1463, 0.16.0**), so the way out is a clean cut: read the table's rows out (for example with `POST …/query`), give
the table a legal name in the file, start once with `"schemaAllowDestructive": true` (the apply creates the new table and drops the
old one) or on a fresh data directory, set `schemaAllowDestructive` back, and load the rows into the new table.

**Declared objects are read-only through the API (**BL-1463, 0.16.0**).** What the file declares has one writer, the file:
deleting a declared database, creating a database with a declared name, and changing the schema of a database whose entry names a
`schema` — `schema/apply`, every table, column and materialized-query route, a branch merge that applies — are refused `409
DECLARED_IN_CONFIGURATION`, naming the file and the JSON pointer of the entry; nothing is changed. Change the file, then `aouda reload`.
A dry-run `schema/apply`, `schema/diff`, `schema/seed`, a merge plan and every row write still work, and a declared database with no
`schema` keeps every schema route. Declared principals and roles follow the same rule ([Declared access](declared-access.md)); the
whole list is in the [HTTP API reference](../reference/http-api.md#one-writer-per-declared-object). A database you remove from the
file is left alone (and the API may drop it from then on); a declaration cannot say "must not exist". Databases an embedding host sets
in code (an in-process test server) are not declared in a file and keep every route.

### Changing the declaration without a restart (**BL-1427, 0.14.0**)

`aouda reload` (or `POST /api/admin/reload`, a server operator's key only) re-reads the declaration of a running server, validates it as a start
would, and converges it in the order above: steps 1, 3 and 4, named `databases`, `schema` and `roles` in its answer (`_serverauth` and
setup mode are the start's; **BL-1464, 0.16.0**: the `keyStore` and `principalRows` steps are gone). What
a reload applies:

- (**BL-1463, 0.16.0**) the declaration file itself and its overlay: they are read again, from the path the running server was
  started with, at every reload;
- a **new** `databases` entry (created, and linked to its auth database);
- a declared database's `schema` (and its overlay) — the file is read again and applied **non-destructively** whatever
  `schemaAllowDestructive` says (a destructive change is the warning `SCHEMA_DESTRUCTIVE_REFUSED`, and `/ready` keeps `schema_drift`);
- the `roles` of a declared auth database, and (**BL-1464, 0.16.0**) the rest of the access section: `signup`, `principals`
  and their credentials, `server.roles` and `server.principals` ([Declared access](declared-access.md));
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
| `database_pending` (the database) | A declared database does not exist yet | Step 1 created it |
| `database_not_open` (the database) | A declared database is registered but failed to open, or is quarantined by something other than an operator | It opens; otherwise it stays, and so does the 503 |
| `server_starting` | The auth bootstrap has not finished | Step 5 |
| `setup_required` | No operator is declared in `server.principals` and no admin exists | `POST /api/auth/setup` created the first admin; a declared operator means no setup mode at all (**BL-1462, 0.14.0**; **BL-1464, 0.16.0**: declared in the declaration file) |
| `schema_pending` (the database) | Its `schema` file has not been applied yet | Step 3 applied it |
| `schema_applying` (the database) | Step 3 is applying its `schema` file now; `progress` is `{ "done": n, "total": m }` over the declared schema files (**BL-1462, 0.14.0**) | Step 3 finished it |
| `schema_drift` (the database) | The apply refused a change; the catalog is not what the file says | You allow the change or update the file, and restart (a reload never applies a destructive change) |
| `reload_failed` (the entry, when one is named) | (**BL-1427, 0.14.0**) The last reload stopped part-way; the steps before it are applied | The next reload that completes |
| `database_reconcile_failed` (the database) | Only after a backup restore: the reconcile of the declared databases was refused. The server keeps running | You fix the declaration or the catalog; the next process start fails on it until then |
| `access_converge_failed` (the auth database) | Only after a backup restore: the declared access section could not be converged. What the file removed is removed where the node writes; the rest waits. The server keeps running | The next converge that completes (a reload, a restore) |
| `component_unhealthy` (the component) | A critical component is not healthy | It recovers |

(**BL-1464, 0.16.0**) `root_user_unusable` and `configured_key_inactive` are gone with the settings they reported on.
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
