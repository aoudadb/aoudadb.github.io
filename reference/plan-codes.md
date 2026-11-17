---
title: "Declaration Finding Codes"
nav_order: 3
parent: "Reference"
---

# Declaration finding codes (**BL-1463, 0.14.0**)

`aouda start` validates the whole declaration — the settings, the declaration file (`Aouda:Declaration`, **BL-1463, next train**), the identities file and every secret and schema file it names — before it opens anything. Every problem is a **finding** with a stable code, the stage that found it, where it is (a setting and the configuration source that supplied it, or a file and a JSON pointer) and what to do. A finding of severity `error` is exactly a refusal of the start; a `warning` is accepted and logged once; `info` is context. A refused start prints every finding at once on standard error and creates nothing.

`aouda plan` runs the **offline** half of every stage without starting anything and reports the same findings with the same codes (see [Plan a declaration](../guides/plan.md)). Six codes are emitted only by a plan: `SOURCE_FIXED_AT_START` (info: `Aouda:Databases` or the identities file's path comes from environment variables or the command line, which a reload never re-reads), `SECRET_NOT_READ` (`--skip-secrets` did not read the secrets it counts), with `--server`, `PLAN_TARGET_UNREACHABLE` and `PLAN_TARGET_REFUSED`, and with `--data-dir`, `PLAN_DATA_DIRECTORY_IN_USE` and `PLAN_DATA_DIRECTORY_NEEDS_RECOVERY` (**BL-1463, next train**).

## Exit status of a refused start

- **78** (`EX_CONFIG`): the declaration is refused. Restarting with the same configuration fails the same way; the systemd unit does not restart it (`RestartPreventExitStatus=78`).
- **1**: every error is a file that could not be read for an I/O reason (`DECLARATION_UNREADABLE`, `SECRET_UNREADABLE`, `SCHEMA_FILE_UNREADABLE`, `OVERLAY_UNREADABLE` with a missing, denied or unreadable file, and `CONFIGURATION_INVALID` for a configuration file that exists and cannot be read). The start may succeed once the file can be read (a volume not yet mounted), so a supervisor may restart it. One such error beside any other error is 78.

## Stages

The stages run in the order of the start: `read`, `settings`, `principals` (the configured keys), `databases`, `bootstrap`, `schema`, `roles`, `principalRows` (the key rows). The **offline** half of every stage runs before anything opens; the **state** half of a stage runs at its step of the start, against the data directory, before that step changes anything. A stage whose input could not be read reports that one finding; every other stage still runs, so a broken schema file does not hide a duplicate key secret.

## Codes

The `PRINCIPAL_*`, `ROLE_BUILTIN_NAME`, `STATEMENT_*`, `AUTH_PUBLIC_UNRESTRICTED`, `ROLE_RUNTIME_CONFLICT`, `DECLARED_OBJECT_OVERRIDDEN`, `PUBLIC_REACH_INERT` and `ACCESS_CONVERGE_REFUSED` codes check the declared access section of `aouda.json` (principals, roles, `signup`; see [Declared access](../guides/declared-access.md)) (**BL-1464, next train**). The role codes of the old `permissions` grammar are gone with it.

| Code | Severity | Stage | Half | Exit status | What to do |
|---|---|---|---|---|---|
| `CONFIGURATION_INVALID` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Fix the configuration file or the AOUDA_ variable named above so that it can be read. |
| `DECLARATION_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Make the setting named above (Aouda:Declaration, Aouda:Auth:Keys:File) name a readable file (a volume not yet mounted clears when it is). |
| `DECLARATION_INVALID_JSON` | error | `read` | offline | 78 | Fix the JSON at the line named above. |
| `DECLARATION_VERSION_UNSUPPORTED` | error | `read` | offline | 78 | Set "version": 1 at the top of the declaration file: it is the only version this server reads. |
| `DECLARATION_OVERLAY_INVALID` | error | `read` | offline | 78 | Remove the member from the overlay: the version is the base file's. |
| `DECLARATION_SHAPE_INVALID` | error | `read` | offline | 78 | Give the identities file the shape { "identities": [ { ... } ] }, each entry an object and each field a string. |
| `DECLARATION_UNKNOWN_MEMBER` | error | `read` | offline | 78 | Remove the member, or correct its spelling: the identities file takes only the members it documents. |
| `SECRET_BY_VALUE` | error | `read` | offline | 78 | Remove the plaintext key from the file and give it by reference: { "env": "NAME" }, { "file": "path" } or { "hash": "sha256:<hex>" }. |
| `SECRET_REFERENCE_INVALID` | error | `read` | offline | 78 | Give the secret as exactly one of { "env": "NAME" }, { "file": "path" } or { "hash": "sha256:<64 hex>" }. |
| `SECRET_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Set the variable, or make the secret file readable and non-empty where the server runs. |
| `OVERLAY_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Make the overlay readable and a JSON object (at least { "extends": "<base file name>" }), or remove it. |
| `SOURCE_NOT_RELOADABLE` | info | `read` | reload | — | Set it in appsettings.json to change it by reload; environment variables and the command line are read once, at start. |
| `SOURCE_FIXED_AT_START` | info | `read` | offline | — | Nothing to do if you deploy by restarting. To change it with `aouda reload`, set it in appsettings.json instead. |
| `OVERLAY_ABSENT` | info | `read` | offline | — | Nothing to do if the environment needs no overlay; otherwise create the file named above. |
| `SECRET_NOT_READ` | info | `read` | offline | — | Run `aouda plan` without --skip-secrets where the secrets are mounted (the deploy host, with the start's own mounts). |
| `DATA_DIRECTORY_FORMAT_REFUSED` | error | `read` | state | 78 | Point the server at a data directory of this format (start from an empty one and restore a backup, see the upgrade notes). |
| `SETTING_INVALID` | error | `settings` | offline | 78 | Set the setting named above to a value the server accepts. |
| `SETTING_REMOVED` | error | `settings` | offline | 78 | Remove the setting and use the one the message names instead. |
| `DEV_ADMIN_REFUSED` | error | `settings` | offline | 78 | Remove Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN), or remove what the message names. |
| `KEY_NAME_INVALID` | error | `principals` | offline | 78 | Give the entry a 'name' of 1-64 letters, digits, '.', '_' and '-'. |
| `KEY_NAME_DUPLICATE` | error | `principals` | offline | 78 | Give every entry of one auth database its own name (names are compared without regard to case). |
| `KEY_NAME_RESERVED` | error | `principals` | offline | 78 | Rename the entry: 'bootstrap-server-key' is the name of the key Aouda:Auth:Bootstrap declares. |
| `KEY_KIND_INVALID` | error | `principals` | offline | 78 | Set 'kind' to one of server_admin, scoped_service, service_role, public, anon. |
| `KEY_FIELD_NOT_FOR_KIND` | error | `principals` | offline | 78 | Remove the field the entry's kind does not take, or move the entry to the auth database its kind belongs to. |
| `KEY_FIELD_REQUIRED` | error | `principals` | offline | 78 | Add the field the entry's kind requires. |
| `KEY_ROLE_INVALID` | error | `principals` | offline | 78 | List plain role names (no control characters, at most 128 characters). |
| `KEY_ROLE_RESERVED` | error | `principals` | offline | 78 | Give the scoped key a custom role: db_admin, db_operator, anonymous and public cannot be given to one. |
| `KEY_SHAPE_INVALID` | error | `principals` | offline | 78 | Generate a key of the entry's kind (aouda keys generate), with its prefix and length. |
| `KEY_SECRET_SHARED` | error | `principals` | offline | 78 | Declare each secret once: remove one of the two declarations named above, or give one of them a different secret. |
| `KEY_SYSTEM_KIND_DUPLICATE` | error | `principals` | offline | 78 | Declare one service_role, public or anon key per database: remove one of the two entries. |
| `SERVER_KEY_BLANK` | error | `principals` | offline | 78 | Set the server key setting to a key, or remove it (an empty value counts as not set). |
| `SERVER_KEY_SOURCES_CONFLICT` | error | `principals` | offline | 78 | Declare the server key in one place: Aouda:Auth:Bootstrap:ServerKey, ServerKeyFile or the aouda-server-key credential. |
| `SERVER_KEY_DEV_ADMIN_CONFLICT` | error | `principals` | offline | 78 | Remove Aouda:Auth:DevAdmin:Enabled, or remove the declared server key: a development flag must not coexist with a real credential. |
| `DATABASE_NAME_INVALID` | error | `databases` | offline | 78 | Rename the database to a valid database name. |
| `DATABASE_NAME_DUPLICATE` | error | `databases` | offline | 78 | Declare the database once: names that differ only by case are one database. |
| `DATABASE_NAME_RESERVED` | error | `databases` | offline | 78 | Rename the database: _serverauth, _auth and _settings belong to the server bootstrap. |
| `DATABASE_KIND_INVALID` | error | `databases` | offline | 78 | Set Kind to data or auth. |
| `DATABASE_FIELD_INVALID` | error | `databases` | offline | 78 | Set the field named above to one of the values the message lists. |
| `DATABASE_FIELD_NOT_FOR_KIND` | error | `databases` | offline | 78 | Remove the field, or declare the database with the kind that takes it. |
| `DATABASE_AUTH_NOT_STRICT` | error | `databases` | offline | 78 | Remove Durability from the auth database, or set it to "strict". |
| `DATABASE_LINK_INVALID` | error | `databases` | offline | 78 | Make AuthDatabase name an application auth database other than the database itself, or remove it. |
| `DATABASE_LINK_NOT_AUTH` | error | `databases` | offline | 78 | Declare the link target with Kind 'auth', or link to an application auth database. |
| `DATABASE_LINK_UNDECLARED` | warning | `databases` | offline | — | Declare the auth database with Kind 'auth', or make sure it exists in the data directory: the start refuses the link otherwise. |
| `DATABASE_NOT_OPEN` | error | `databases` | state | 78 | Repair the database, quarantine it as an operator, or list it in Aouda:SkipDatabases to start without it. |
| `DATABASE_KIND_CONFLICT` | error | `databases` | state | 78 | Declare the database with the kind it has in the data directory, or declare another name. |
| `DATABASE_LINK_TARGET_ABSENT` | error | `databases` | state | 78 | Declare the auth database with Kind 'auth', or create it first: a declaration never creates an auth database it does not name. |
| `DATABASE_LINK_TARGET_NOT_OPEN` | error | `databases` | state | 78 | Open the auth database (repair it, or remove it from Aouda:SkipDatabases or its operator quarantine), or remove the link. |
| `DATABASE_LINK_TARGET_NOT_AUTH` | error | `databases` | state | 78 | Link to an application auth database. |
| `DATABASE_LINK_CONFLICT` | error | `databases` | state | 78 | Make the declaration match the catalog's link, or unlink the database first. |
| `PRINCIPAL_NAME_INVALID` | error | `principals` | offline | 78 | Name the principal by a slug (^[a-z][a-z0-9-]{0,62}$) or an email address (ADR 0071 D-2). |
| `PRINCIPAL_NAME_DUPLICATE` | error | `principals` | offline | 78 | Declare the principal once: names are compared without regard to case. |
| `PRINCIPAL_BUILTIN` | error | `principals` | offline | 78 | Declare only statements and attributes for anonymous, spelled 'anonymous': it is built in, has no credential and cannot be disabled. |
| `PRINCIPAL_ATTRIBUTE_INVALID` | error | `principals` | offline | 78 | Give the attribute a valid name and values of one type, within the caps (1 000 values per attribute, 5 000 per principal). |
| `SETUP_MODE_EXPECTED` | warning | `bootstrap` | offline | — | Nothing to do for an interactive first run; otherwise declare an operator in server.principals (a principal holding manage on server, with a credential), a server key or Aouda:Auth:RootUser. |
| `SERVER_HAS_NO_OPERATOR` | error | `bootstrap` | state | 78 | Declare an operator: a server key (Aouda:Auth:Bootstrap:ServerKey, ServerKeyFile, the aouda-server-key credential or a server_admin entry), or Aouda:Auth:RootUser. |
| `ROOT_USER_INVALID` | error | `bootstrap` | state | 78 | Give Aouda:Auth:RootUser a password the password policy accepts. |
| `SCHEMA_FILE_UNREADABLE` | error | `schema` | offline | 1 when the file cannot be read (I/O), else 78 | Make the schema file readable where the server runs (a volume not yet mounted clears when it is), or fix SchemaFile. |
| `SCHEMA_INVALID` | error | `schema` | offline | 78 | Fix the schema file at the pointer named above. |
| `SCHEMA_UNKNOWN_MEMBER` | error | `schema` | offline | 78 | Remove the member, or correct its spelling: a schema file takes only the members the schema format defines. |
| `SCHEMA_OVERLAY_INVALID` | error | `schema` | offline | 78 | Make the overlay extend its base file by name and change only what an overlay may change. |
| `SCHEMA_LIMIT_EXCEEDED` | error | `schema` | offline | 78 | Simplify the named query, or raise Aouda:NamedQuery:MaxJoins / MaxCost. |
| `SCHEMA_DATABASE_MISMATCH` | warning | `schema` | offline | — | Make the file's 'database' member name the database that declares it, or remove the member: the start applies the file to the declaring database. |
| `SCHEMA_DATABASE_NOT_OPEN` | error | `schema` | state | 78 | Open the database (repair it), or list it in Aouda:SkipDatabases to start without it. |
| `SCHEMA_CHANGE_REFUSED` | error | `schema` | state | 78 | Change the schema file so that the engine can apply it (a partition key is fixed once set; a table keeps at least one column). |
| `SCHEMA_DESTRUCTIVE_REFUSED` | warning | `schema` | state | — | Set SchemaAllowDestructive for the database to apply the destructive change, or make the file match the catalog. |
| `ROLE_NAME_INVALID` | error | `roles` | offline | 78 | Give the role a name. |
| `ROLE_NAME_DUPLICATE` | error | `roles` | offline | 78 | Declare the role once: role names are compared without regard to case. |
| `ROLE_SYSTEM_NAME` | error | `roles` | offline and state | 78 | Declare a custom role and assign it: a system role cannot be declared. |
| `ROLE_AUTH_DATABASE_NOT_OPEN` | error | `roles` | state | 78 | Open the auth database (repair it), or list it in Aouda:SkipDatabases to start without it. |
| `ROLE_BUILTIN_NAME` | error | `roles` | offline | 78 | Name the role something else, or assign the built-in role to the principal: admin, writer and reader are built in and cannot be declared. |
| `STATEMENT_NOT_GOVERNED` | error | `roles` | offline and state | 78 | Give the statement to a principal or role of the auth database that governs the resource (the message names it), or link the database to this auth database. |
| `STATEMENT_RESOURCE_UNKNOWN` | warning | `roles` | offline | — | Check the name against the declared schema files. A table created at runtime is not visible offline; a statement may precede its table. |
| `STATEMENT_COLUMN_UNKNOWN` | warning | `roles` | offline | — | Check the column against the table's declared schema: a condition on a column the table does not have matches no row (ADR 0071 D-9). |
| `AUTH_PUBLIC_UNRESTRICTED` | error | `roles` | offline and state | 78 | Give the public statement the same row condition, or mark it "unrestricted": true if every row is meant to be public; manage is never public (ADR 0071 C-11). |
| `PRINCIPAL_ROLE_UNKNOWN` | error | `principalRows` | state | 78 | Declare the role in the same auth database's roles, or create it before the reload: a principal holds only roles that exist. |
| `PRINCIPAL_RUNTIME_CONFLICT` | error | `principalRows` | state | 78 | Delete or rename the runtime principal, then start or reload again: a declared principal is owned by the file, whole. |
| `ROLE_RUNTIME_CONFLICT` | error | `principalRows` | state | 78 | Delete or rename the runtime role, then start or reload again: a declared role is owned by the file, whole. |
| `DECLARED_OBJECT_OVERRIDDEN` | warning | `principalRows` | state | — | Make the file say what the server does (disabled: true, or a new key version), or undo the runtime action: until then every start and reload warns. |
| `PUBLIC_REACH_INERT` | warning | `principalRows` | state | — | Give the public statement the restricting statement's row condition, or mark it unrestricted: until then it grants nothing on that table. |
| `ACCESS_CONVERGE_REFUSED` | error | `principalRows` | state | 78 | Change the declaration as the message says; the start and the reload stop at the first write the principal store refuses. |
| `KEY_TARGET_PENDING` | warning | `principalRows` | offline | — | Declare the auth database (Kind 'auth'), or make sure it exists: until it does the key has no row and is refused. |
| `KEY_ROLE_UNDECLARED` | warning | `principalRows` | offline | — | Declare the role in the auth database's Roles, or make sure it exists: a key whose role is missing is denied. |
| `KEY_DATABASE_NOT_LINKED` | warning | `principalRows` | offline | — | Check that the database exists and is linked to the key's auth database. |
| `KEY_AUTH_DATABASE_NOT_OPEN` | error | `principalRows` | state | 78 | Repair or restore the auth database (or remove its key declarations) and start again. |
| `KEY_SECRET_HELD_BY_OTHER_ROW` | error | `principalRows` | state | 78 | A secret is one row: revoke and delete the key that holds it, or declare a different secret. |
| `KEY_REVOKED_BY_OPERATOR` | warning | `principalRows` | state | — | Remove the key from the declaration to make the revocation permanent; a wipe of the data returns it. |
| `PLAN_TARGET_UNREACHABLE` | error | `target` | target | — (`aouda plan` exits 69) | Check that the server is running this release or later, reachable at the URL given, and ready; retry after the delay it named. |
| `PLAN_TARGET_REFUSED` | error | `target` | target | — (`aouda plan` exits 77) | Give a server key (mk_srv_) of that server with --key-file PATH or --key-env NAME. |
| `PLAN_DATA_DIRECTORY_IN_USE` | error | `target` | target | — (`aouda plan` exits 69) | Plan the running server with --server URL --key-file PATH, or stop it and plan again: two processes on one data directory are not safe. |
| `PLAN_DATA_DIRECTORY_NEEDS_RECOVERY` | error | `target` | target | — (`aouda plan` exits 69) | Start the server once on this directory (it removes interrupted creations and drops), then plan again; a plan does not simulate the recovery. |

A code whose half is **reload** is emitted only by `aouda reload` (`POST /api/admin/reload`), never by the start (**BL-1427, 0.14.0**); a reload runs every other code as the start does and is refused by every `error`.

A code whose half is **target** is emitted only by `aouda plan --server` or `aouda plan --data-dir`, about the target it plans against: the server could not be reached or did not answer with a plan, or the data directory does not exist or cannot be listed (`PLAN_TARGET_UNREACHABLE`, exit 69); the server refused the key (`PLAN_TARGET_REFUSED`, exit 77); another Aouda process holds the data directory (`PLAN_DATA_DIRECTORY_IN_USE`, exit 69); or a crash left a database half-created or half-dropped and only a start recovers it (`PLAN_DATA_DIRECTORY_NEEDS_RECOVERY`, exit 69). None is a finding about the declaration, and no start or reload emits them (**BL-1463, next train**). Stage `target` is not a stage of the start.

`SERVER_HAS_NO_OPERATOR` is one rule checked at two moments of the start: before the schema step (stage `bootstrap`) and after the key rows are reconciled (stage `principalRows`).

A message never contains a key, a hash or a secret file's content; a path that contains a key is shown as `<redacted>`. A fingerprint (the first eight hex characters of a key's SHA-256, as `aouda keys hash` prints it) is the only value derived from a secret that may appear.
