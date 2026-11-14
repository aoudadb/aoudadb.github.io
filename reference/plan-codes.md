---
title: "Declaration Finding Codes"
nav_order: 3
parent: "Reference"
---

# Declaration finding codes (**BL-1463, next train**)

`aouda start` validates the whole declaration — the settings, `Aouda:Databases`, the identities file and every secret and schema file it names — before it opens anything. Every problem is a **finding** with a stable code, the stage that found it, where it is (a setting and the configuration source that supplied it, or a file and a JSON pointer) and what to do. A finding of severity `error` is exactly a refusal of the start; a `warning` is accepted and logged once; `info` is context. A refused start prints every finding at once on standard error and creates nothing.

`aouda plan` runs the **offline** half of every stage without starting anything and reports the same findings with the same codes (see [Plan a declaration](../guides/plan.md)). One code is emitted only by a plan, `SECRET_NOT_READ`: `--skip-secrets` did not read the secrets it counts.

## Exit status of a refused start

- **78** (`EX_CONFIG`): the declaration is refused. Restarting with the same configuration fails the same way; the systemd unit does not restart it (`RestartPreventExitStatus=78`).
- **1**: every error is a file that could not be read for an I/O reason (`DECLARATION_UNREADABLE`, `SECRET_UNREADABLE`, `SCHEMA_FILE_UNREADABLE`, `OVERLAY_UNREADABLE` with a missing, denied or unreadable file). The start may succeed once the file can be read (a volume not yet mounted), so a supervisor may restart it. One such error beside any other error is 78.

## Stages

The stages run in the order of the start: `read`, `settings`, `principals` (the configured keys), `databases`, `bootstrap`, `schema`, `roles`, `principalRows` (the key rows). The **offline** half of every stage runs before anything opens; the **state** half of a stage runs at its step of the start, against the data directory, before that step changes anything. A stage whose input could not be read reports that one finding; every other stage still runs, so a broken schema file does not hide a duplicate key secret.

## Codes

| Code | Severity | Stage | Half | Exit status | What to do |
|---|---|---|---|---|---|
| `CONFIGURATION_INVALID` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Fix the configuration file or the AOUDA_ variable named above so that it can be read. |
| `DECLARATION_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Make Aouda:Auth:Keys:File name a readable file (a volume not yet mounted clears when it is). |
| `DECLARATION_INVALID_JSON` | error | `read` | offline | 78 | Fix the JSON at the line named above. |
| `DECLARATION_SHAPE_INVALID` | error | `read` | offline | 78 | Give the identities file the shape { "identities": [ { ... } ] }, each entry an object and each field a string. |
| `DECLARATION_UNKNOWN_MEMBER` | error | `read` | offline | 78 | Remove the member, or correct its spelling: the identities file takes only the members it documents. |
| `SECRET_BY_VALUE` | error | `read` | offline | 78 | Remove the plaintext key from the file and give it by reference: { "env": "NAME" }, { "file": "path" } or { "hash": "sha256:<hex>" }. |
| `SECRET_REFERENCE_INVALID` | error | `read` | offline | 78 | Give the secret as exactly one of { "env": "NAME" }, { "file": "path" } or { "hash": "sha256:<64 hex>" }. |
| `SECRET_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Set the variable, or make the secret file readable and non-empty where the server runs. |
| `OVERLAY_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Make the overlay readable and a JSON object (at least { "extends": "<base file name>" }), or remove it. |
| `SOURCE_NOT_RELOADABLE` | info | `read` | reload | — | Move the setting to a configuration file to change it by reload; environment variables and the command line are read once, at start. |
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
| `SETUP_MODE_EXPECTED` | warning | `bootstrap` | offline | — | Nothing to do for an interactive first run; otherwise declare a server key or Aouda:Auth:RootUser. |
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
| `ROLE_BODY_EMPTY` | error | `roles` | offline | 78 | Give the role a body, at least {}. |
| `ROLE_SYSTEM_NAME` | error | `roles` | offline and state | 78 | Declare a custom role and assign it: a system role cannot be declared. |
| `ROLE_PERMISSION_INVALID` | error | `roles` | offline | 78 | Fix the permission as the message says. |
| `ROLE_TABLE_NOT_DECLARED` | warning | `roles` | offline | — | Check the table name against the declared schema files, or remove the permission. A table created at runtime is not visible offline. |
| `ROLE_NAMED_ARTIFACT_NOT_DECLARED` | warning | `roles` | offline | — | Check the name against the declared schema files, or remove the permission. A named query or mutation created at runtime is not visible offline. |
| `ROLE_AUTH_DATABASE_NOT_OPEN` | error | `roles` | state | 78 | Open the auth database (repair it), or list it in Aouda:SkipDatabases to start without it. |
| `AUTH_GRANT_TABLE_NOT_FOUND` | error | `roles` | state | 78 | Create the table (declare it in a schema file of a linked database), or remove the permission. |
| `AUTH_GRANT_NOT_APPLICABLE` | error | `roles` | state | 78 | Change the permission so that it applies to the table as it is (e.g. all-partitions needs a partitioned table). |
| `ROLE_SIGNUP_ALL_GRANT` | error | `roles` | state | 78 | Use another role for the all-partitions or all-rows grant, or change the database's SelfSignupRole first. |
| `KEY_TARGET_PENDING` | warning | `principalRows` | offline | — | Declare the auth database (Kind 'auth'), or make sure it exists: until it does the key has no row and is refused. |
| `KEY_ROLE_UNDECLARED` | warning | `principalRows` | offline | — | Declare the role in the auth database's Roles, or make sure it exists: a key whose role is missing is denied. |
| `KEY_DATABASE_NOT_LINKED` | warning | `principalRows` | offline | — | Check that the database exists and is linked to the key's auth database. |
| `KEY_AUTH_DATABASE_NOT_OPEN` | error | `principalRows` | state | 78 | Repair or restore the auth database (or remove its key declarations) and start again. |
| `KEY_SECRET_HELD_BY_OTHER_ROW` | error | `principalRows` | state | 78 | A secret is one row: revoke and delete the key that holds it, or declare a different secret. |
| `KEY_REVOKED_BY_OPERATOR` | warning | `principalRows` | state | — | Remove the key from the declaration to make the revocation permanent; a wipe of the data returns it. |

A code whose half is **reload** is emitted only by `aouda reload` (`POST /api/admin/reload`), never by the start (**BL-1427, next train**); a reload runs every other code as the start does and is refused by every `error`.

`SERVER_HAS_NO_OPERATOR` is one rule checked at two moments of the start: before the schema step (stage `bootstrap`) and after the key rows are reconciled (stage `principalRows`).

A message never contains a key, a hash or a secret file's content; a path that contains a key is shown as `<redacted>`. A fingerprint (the first eight hex characters of a key's SHA-256, as `aouda keys hash` prints it) is the only value derived from a secret that may appear.
