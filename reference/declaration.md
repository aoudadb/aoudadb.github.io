---
title: "The declaration file (aouda.json)"
nav_order: 3.5
parent: "Reference"
---

# The declaration file: `aouda.json` (**BL-1463, 0.16.0**)

`aouda.json` is the one file that says which databases a server has. This page is the grammar, member by member: the exact JSON, the
default of every member and the code of every refusal. How to use the file (where it is found, overlays, a deploy) is in
[Declare a server in one file](../guides/declaration.md). The published JSON schema, for an editor, is
[`schemas/aouda-declaration.v1.json`](../schemas/aouda-declaration.v1.json); the codes are in
[Declaration Finding Codes](plan-codes.md).

The file holds **what exists**: databases, their schema files, and who may do what (roles, principals, `signup`; **BL-1464, 0.16.0**). **How the server runs** (ports, memory, paths, the
`Aouda:Declaration` setting itself) stays in settings: `appsettings.json`, environment variables and command-line switches.

---

## The file

- **JSON with comments.** UTF-8, an optional byte-order mark, `//` and `/* */` comments and trailing commas allowed. Nothing else
  that is not JSON is read. A duplicate member is `DECLARATION_INVALID_JSON` (the last would win and hide the first). An empty file is
  refused: the smallest file is `{ "version": 1 }`.
- **Names are case-sensitive.** A member spelled in another case (`"Kind"`) is `DECLARATION_UNKNOWN_MEMBER` and the message names the right spelling.
- **Strict.** A member that is not in this page is `DECLARATION_UNKNOWN_MEMBER`, with the JSON pointer of the member. A member of the
  wrong JSON type is `DECLARATION_SHAPE_INVALID`. `null` is not a value: write the member or leave it out.
- **No finding quotes the file's text** (a password typed without quotes is not echoed back), and a value that looks like a key is
  shown as `<redacted>`.

## The root

| Member | JSON type | Required | Meaning |
|---|---|---|---|
| `$schema` | string | no | The JSON schema of the file, for an editor: `"https://aoudadb.github.io/schemas/aouda-declaration.v1.json"`. The server ignores it and never fetches it |
| `version` | integer | **yes** | `1`. Anything else (absent, `2`, `"1"`, `1.5`) is `DECLARATION_VERSION_UNSUPPORTED` with `found=<value or missing> expected=1`, and nothing else in the file is read |
| `databases` | object | no | The declared databases, keyed by database name. Absent or `{}`: nothing is declared |
| `server` | object | no | Who operates the server: the server auth database's `roles` and `principals` (below) (**BL-1464, 0.16.0**). It takes no `signup` |
| `keyRoot` | object | no | The root declared principals' derived keys are computed from: `{ "env": NAME }` or `{ "file": path }` (relative to this file's directory). A literal is `SECRET_BY_VALUE`; a root shorter than 32 bytes or one repeated character is `KEY_ROOT_INVALID` (**BL-1464, 0.16.0**) |
| `previousKeyRoot` | object | no | The root before a rotation, in the same form: its derived keys are still accepted beside `keyRoot`'s until it is removed |

```json
{
  "$schema": "https://aoudadb.github.io/schemas/aouda-declaration.v1.json",
  "version": 1,
  "databases": {}
}
```

## `databases.<name>`

The member name is the database's name. It follows the rules of database names and is compared without case, so declaring `Ledger`
and `ledger` is refused. `_serverauth`, `_auth` and `_settings` belong to the server and are refused.

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `kind` | string | none, **required** | `"data"` (an ordinary database) or `"auth"` (an application auth database). Absent is `DATABASE_KIND_INVALID` at `/databases/<name>/kind`: an empty entry declares nothing. The value is not case-sensitive; any other value is `DATABASE_KIND_INVALID`. A blank string (`""`) also reads as `data`: write `"data"` |
| `authDatabase` | string | none | `data` only: the application auth database this database is linked to. Declared in the same file with `"kind": "auth"`, or already in the catalog; it is never created for you |
| `schema` | string | none | `data` only: the path of a schema file applied at start. Absolute, or **relative to the directory of `aouda.json`** (not to the working directory). Its overlay is `<stem>.<env>.json` beside it, for the process's `Aouda:Environment` |
| `schemaAllowDestructive` | boolean | `false` | Needs `schema`. `true` lets the start-time apply drop a table or a column. A reload never applies a destructive change |
| `durability` | string | `"strict"` | `"strict"`, `"os"`, `"unlogged"` or `"memory"` ([levels](../guides/write-durability.md#durability-levels-lead-s26-060)). An `auth` database is always `strict`; another value is refused |
| `replicationMode` | string | `"Replicate"` | `"Replicate"` or `"DoNotReplicate"` |
| `writeConcern` | string | `"One"` | `"One"`, `"Majority"` or `"All"` |
| `writeConcernTimeoutMs` | integer | `5000` | Milliseconds to wait for the write concern's acknowledgements; at least `100` |
| `onWriteConcernTimeout` | string | `"DegradeAndLog"` | `"Fail"`, `"Degrade"` or `"DegradeAndLog"` |
| `defaultTemperature` | string | `"Auto"` | `"Auto"`, `"HotOnly"` or `"ColdPreferred"`, for new tables |
| `memoryWeight` | number | `1` | Relative weight of this database's memory share; positive |
| `maxMemoryShareBytes` | integer | none | Cap on the computed memory share, in bytes; not negative. `0` is no cap, as when it is absent |
| `signup` | object | none | `auth` only: self-signup, `{ "enabled", "roles"?, "statements"? }` (below) (**BL-1464, 0.16.0**) |
| `roles` | object | none | `auth` only: the auth database's roles, keyed by role name (below). On a `data` database it is refused (`DATABASE_FIELD_NOT_FOR_KIND`) |
| `principals` | object | none | `auth` only: the auth database's principals, keyed by name (below) (**BL-1464, 0.16.0**) |

The value rules (which `durability` an `auth` database may have, which `authDatabase` is a valid link, which combination of members
a kind allows) are those of the `databases` stage and its codes, unchanged; they are listed with the codes in
[Declaration Finding Codes](plan-codes.md) and explained in [Declared databases](../guides/declared-databases.md).

An integer member given a number it cannot hold (`1.5`, or beyond the range) is `DECLARATION_SHAPE_INVALID`.

## The access section: `signup`, `roles`, `principals` (**BL-1464, 0.16.0**)

An application auth database (`databases.<auth>`) declares who may do what in three members; the server auth database declares its
operators in `server.roles` and `server.principals`. What they mean — statements, resources, `where`, attributes, the built-in roles,
`anonymous`, `signup` — is the access model's ([Declared access](../guides/declared-access.md)); this page gives the exact JSON.

- **The file owns what it declares, whole.** Every start and reload converges it: a declared role or principal is created, updated
  member by member, and removed when the file no longer names it. A role or principal made at runtime (Studio, the API) with the same
  name is **refused** (`ROLE_RUNTIME_CONFLICT`, `PRINCIPAL_RUNTIME_CONFLICT`): delete or rename it, then start or reload again.
- For every auth database the file declares access for, the file also owns `anonymous` and `signup`: an `anonymous` that is not
  declared holds nothing, and a `signup` that is not declared is off. An auth database the file declares nothing for is left as it is.
- A server with no declaration file converges nothing.

### `databases.<auth>.signup`

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | **required** | Whether a person may sign themselves up on this auth database |
| `roles` | array of strings | `[]` | The roles a signed-up principal holds: declared, built-in or runtime roles of this auth database |
| `statements` | array | `[]` | Statements every signed-up principal holds |

`oidc` is refused (`DECLARATION_UNKNOWN_MEMBER`): external identity providers for end users are reserved and not built yet. The
old signup flag and signup-role members are refused naming `signup`.

### `roles.<role>`

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `description` | string | none | The role's description |
| `statements` | array | **required** | What the role grants: a non-empty list of statements |

A role's name is non-empty, without `/`, `*` or surrounding blanks, compared without case (`ROLE_NAME_DUPLICATE` names both). The
built-in `admin`, `writer` and `reader` cannot be declared (`ROLE_BUILTIN_NAME`). The old `permissions` member is refused naming
`statements` (`DECLARATION_UNKNOWN_MEMBER`).

### `principals.<name>`

The member name is the principal's name: a slug (`^[a-z][a-z0-9-]{0,62}$`) or an email address, compared without case. A name that
carries a key or a key's hash is refused and never shown (`PRINCIPAL_NAME_INVALID`).

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `description` | string | none | Free text |
| `roles` | array of strings | `[]` | The roles it holds |
| `statements` | array | `[]` | Its own statements (an empty list is allowed) |
| `attributes` | object | `{}` | `name → [values]` (strings, numbers or booleans); a `where` reads them as `principal.<name>`. At most 1 000 values per attribute and 5 000 per principal (`PRINCIPAL_ATTRIBUTE_INVALID`) |
| `credentials` | object | none | How it authenticates (below); not for `anonymous` |
| `disabled` | boolean | `false` | `true` refuses every credential of it and ends its open sessions. `false` re-enables only what the file disabled: a principal disabled at runtime stays disabled, and every plan, start and reload warns `DECLARED_OBJECT_OVERRIDDEN` |

`credentials`:

| Member | JSON type | Meaning |
|---|---|---|
| `derivedKey` | object | `{ "version": n }` (n ≥ 1): a key derived from `keyRoot` (`KEY_ROOT_MISSING` without one). Bump `version` to rotate it |
| `keys` | array | `{ "id": "aouda_<16>", "sha256": "<64 hex>" }` each: a stored key, by its public id and hash. A whole key in `id`, a bad hash or an id declared twice is refused without echoing it (`KEY_DECLARATION_INVALID`, `KEY_ID_DUPLICATE`) |
| `oidc` | array | `{ "issuer", "audience", "subject", "claims"?, "jwks"? }` each. Two principals' trusts that one token could match are `OIDC_TRUST_DUPLICATE` / `OIDC_TRUST_OVERLAP`; two of one principal `OIDC_TRUST_REDUNDANT` (a warning). Nothing is fetched at plan time |
| `password` | object | `{ "file" }`, `{ "env" }` or `{ "hash": <the server's password-hasher output> }`, on a principal named by an email (`PASSWORD_SEED_NEEDS_EMAIL`): applied only when the principal is created, with a forced change at the first sign-in |

`anonymous` is declared under `principals` with `statements` and `attributes` only, spelled exactly `anonymous`
(`PRINCIPAL_BUILTIN` otherwise). `authDatabase` and `type` are refused naming what replaces them.

### A statement

| Member | JSON type | Default | Meaning |
|---|---|---|---|
| `actions` | array of strings | **required** | `read`, `write`, `delete`, `execute`, `manage`, `set-identity`, or `*` |
| `resources` | array of strings | **required** | `<db>`, `<db>/table/<t>`, `<db>/query/<q>`, `<db>/mutation/<m>`, `<auth>/principal/<p>`, `<auth>/role/<r>`, `server`; `*` allowed |
| `where` | object | none | A row condition: `{ "and" \| "or": [ { "column", "op", "value" \| "principal", "ignoreCase"? } ] }`, or `groups` of them |
| `embargoSeconds` | integer | none | With `actions` `["read"]` or `["execute"]`: rows newer than this are not read |
| `unrestricted` | boolean | `false` | Lets `anonymous` or `signup` read a row-scoped table without a condition, on purpose |

A statement of an application auth database names only what that auth database governs: itself and the databases linked to it
(`STATEMENT_NOT_GOVERNED` names the auth database that does). `server.principals` and `server.roles` may name every database and
`server`.

```json
{
  "version": 1,
  "server": {
    "principals": { "ops@example.com": { "roles": ["admin"] } }
  },
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

---

## The overlay

With the process setting `Aouda:Environment` set to `E`, the server also reads `aouda.E.json` **in the same directory** and merges it
over the file before anything else is checked. The merge is [RFC 7396](https://www.rfc-editor.org/rfc/rfc7396) exactly:

| In the overlay | Result |
|---|---|
| an object member | merged into the file's member, recursively |
| a string, number or boolean | replaces the file's value |
| **an array** | **replaces the file's array whole** (it is not merged item by item) |
| `null` | removes the member |
| a member the file does not have | added |

The overlay may not carry `version` (`DECLARATION_OVERLAY_INVALID`; the version is the file's). An overlay that exists and cannot be
read or is not a JSON object is `OVERLAY_UNREADABLE` (an error; the file is **not** read alone instead); one that does not exist is
`OVERLAY_ABSENT` (info) and the file is read alone. A finding about a value the overlay supplied names the overlay file.

`Aouda:Environment` is a name, not a path: letters, digits, `_`, `.` and `-`, not starting with `.`, at most 64 characters. Anything
else (`..`, `a/b`, a space) is `SETTING_INVALID` and no file is looked for.

## The process settings

These are read from **settings**, never from the file:

| Setting | Switch | Environment variable | Meaning |
|---|---|---|---|
| `Aouda:Declaration` | `--declaration PATH` (`aouda start`, `aouda plan`) | `AOUDA_DECLARATION`, `Aouda__Declaration` | The path of `aouda.json`. Absolute, or relative to the working directory. **No default**: unset, nothing is declared (`declaration: none` in the log and the plan). An empty value counts as unset (a compose pass-through of a variable that is not set). Set to a file that is missing, a directory or empty is a refusal (`DECLARATION_UNREADABLE`, or `CONFIGURATION_INVALID` for a value of only whitespace); a missing file is a fault of the environment (exit 1: a volume not yet mounted clears when it is) |
| `Aouda:Environment` | `--env NAME` | `AOUDA_ENVIRONMENT`, `Aouda__Environment` | The environment whose overlay is read (above); one per process. Unset: no overlay is looked for |

A reload (`aouda reload`) reads the file and its overlay again from the path the running server was started with. A changed
`Aouda:Declaration` or `Aouda:Environment` is reported `restartRequired` and is not followed; a file that disappears or cannot be read
refuses the reload and changes nothing.

## The old settings are refused

`Aouda:Databases` is **no longer read** from any configuration source (`appsettings.json`, the environment, a switch). A start or a
plan that finds one refuses it with `SETTING_REMOVED`, one finding per database and member, naming the member of `aouda.json` that
replaces it and never showing the value. Beyond 50 findings one more says how many were left out. This is the whole mapping:

| Removed setting | Replacement |
|---|---|
| `Aouda:Databases:<db>:Kind` | `databases.<db>.kind` |
| `Aouda:Databases:<db>:AuthDatabase` | `databases.<db>.authDatabase` |
| `Aouda:Databases:<db>:SchemaFile` | `databases.<db>.schema` |
| `Aouda:Databases:<db>:SchemaEnvironment` | the process setting `Aouda:Environment` (`--env`, `AOUDA_ENVIRONMENT`) |
| `Aouda:Databases:<db>:SchemaAllowDestructive` | `databases.<db>.schemaAllowDestructive` |
| `Aouda:Databases:<db>:Durability` | `databases.<db>.durability` |
| `Aouda:Databases:<db>:ReplicationMode` | `databases.<db>.replicationMode` |
| `Aouda:Databases:<db>:WriteConcern` | `databases.<db>.writeConcern` |
| `Aouda:Databases:<db>:WriteConcernTimeoutMs` | `databases.<db>.writeConcernTimeoutMs` |
| `Aouda:Databases:<db>:OnWriteConcernTimeout` | `databases.<db>.onWriteConcernTimeout` |
| `Aouda:Databases:<db>:DefaultTemperature` | `databases.<db>.defaultTemperature` |
| `Aouda:Databases:<db>:MemoryWeight` | `databases.<db>.memoryWeight` |
| `Aouda:Databases:<db>:MaxMemoryShareBytes` | `databases.<db>.maxMemoryShareBytes` |
| `Aouda:Databases:<auth>:Roles` | `databases.<auth>.roles`, each role `{ "statements": [...] }` |
| `Aouda:Databases:<db>:MaxMemoryBytes` (refused before this, too) | `databases.<db>.maxMemoryShareBytes` and `databases.<db>.memoryWeight` |
| `Aouda:Databases:<db>:EnableWal`, `DataDurability` (refused before this, too) | `databases.<db>.durability` |

Setting `Aouda:Declaration` and `Aouda:Databases` together is the same refusal: the two are never merged.

(**BL-1464, 0.16.0**) The old ways of declaring operators and keys are refused the same way, every setting under the three
sections (a misspelt member too) and the two systemd credentials when present, before any database opens. An empty value (a compose
`${VAR:-}` pass-through of an unset variable) is not set and is not refused:

| Removed | Replacement |
|---|---|
| `Aouda:Auth:Keys` (the identities file) and anything under it | each key's principal in `databases.<auth>.principals` or `server.principals`, with its `credentials`: a `derivedKey` from the file's `keyRoot`, or a stored key `{ "id", "sha256" }` |
| `Aouda:Auth:Bootstrap` and the systemd credential `aouda-server-key` | a `server.principals` entry holding the role `admin`, with a `derivedKey` or a stored key |
| The first-operator email and password settings, and the systemd credential `aouda-admin-password` | a `server.principals` entry named by the email, holding `admin`, with a password seed `{ "file" }` or `{ "env" }` (applied once, at creation, with a forced change) |

The embedded engine (`Aouda.Testing`, the dev server's own primary database) is not a configuration source and is not refused: it
declares its databases in code.

## Codes

| Code | Severity | Meaning |
|---|---|---|
| `DECLARATION_UNREADABLE` | error | The file named by `Aouda:Declaration` is missing, a directory or cannot be read |
| `DECLARATION_INVALID_JSON` | error | Not JSON (the line and position, never the text), or a duplicate member |
| `DECLARATION_SHAPE_INVALID` | error | A member of the wrong JSON type, or a value its member cannot hold |
| `DECLARATION_UNKNOWN_MEMBER` | error | A member the grammar does not have, or spelled in another case |
| `DECLARATION_VERSION_UNSUPPORTED` | error | `version` is absent or is not `1` |
| `DECLARATION_OVERLAY_INVALID` | error | The overlay carries `version` |
| `OVERLAY_ABSENT` | info | No overlay for the environment; the file is read alone |
| `OVERLAY_UNREADABLE` | error | The overlay exists and cannot be read, is empty or is not a JSON object |
| `DATABASE_KIND_INVALID` | error | A database has no `kind`, or one other than `data` and `auth` |
| `SETTING_REMOVED` | error | An `Aouda:Databases` setting, or (**BL-1464, 0.16.0**) an `Aouda:Auth:Keys` / `Bootstrap` / first-operator setting or the `aouda-server-key` / `aouda-admin-password` credential; names what replaces it |
| `DATABASE_FIELD_INVALID`, `DATABASE_FIELD_NOT_FOR_KIND`, `DATABASE_NAME_INVALID`, `DATABASE_NAME_DUPLICATE`, `DATABASE_NAME_RESERVED`, `DATABASE_AUTH_NOT_STRICT`, `DATABASE_LINK_INVALID`, `DATABASE_LINK_NOT_AUTH` | error | The value rules of a database entry (a value out of range, a member the kind does not take, a name the server refuses, a durability other than `strict` on an `auth` database, a link that cannot be); unchanged by the file |
| `DATABASE_LINK_UNDECLARED` | warning | `authDatabase` names a database the file does not declare: the start links to it only if the data directory has it as an application auth database |
| `SETTING_INVALID` | error | `Aouda:Environment` is not a name |
| `CONFIGURATION_INVALID` | error | `Aouda:Declaration` is set to only whitespace, or a value that is not a path |

Every code with its stage, its exit status and its remedy is in [Declaration Finding Codes](plan-codes.md).
