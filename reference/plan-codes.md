---
title: "Declaration Finding Codes"
nav_order: 3
parent: "Reference"
---

# Declaration finding codes (**BL-1463, 0.14.0**)

`aouda start` validates the whole declaration — the settings, the declaration file (`Aouda:Declaration`, **BL-1463, 0.16.0**) and every secret and schema file it names — before it opens anything. Every problem is a **finding** with a stable code, the stage that found it, where it is (a setting and the configuration source that supplied it, or a file and a JSON pointer) and what to do. A finding of severity `error` is exactly a refusal of the start; a `warning` is accepted and logged once; `info` is context. A refused start prints every finding at once on standard error and creates nothing.

`aouda plan` runs the **offline** half of every stage without starting anything and reports the same findings with the same codes (see [Plan a declaration](../guides/plan.md)). Five codes are emitted only by a plan: `SECRET_NOT_READ` (`--skip-secrets` did not read the secrets it counts), with `--server`, `PLAN_TARGET_UNREACHABLE` and `PLAN_TARGET_REFUSED`, and with `--data-dir`, `PLAN_DATA_DIRECTORY_IN_USE` and `PLAN_DATA_DIRECTORY_NEEDS_RECOVERY` (**BL-1463, 0.16.0**).

## Exit status of a refused start

- **78** (`EX_CONFIG`): the declaration is refused. Restarting with the same configuration fails the same way; the systemd unit does not restart it (`RestartPreventExitStatus=78`).
- **1**: every error is a file that could not be read for an I/O reason (`DECLARATION_UNREADABLE`, `SECRET_UNREADABLE`, `SCHEMA_FILE_UNREADABLE`, `OVERLAY_UNREADABLE` with a missing, denied or unreadable file, and `CONFIGURATION_INVALID` for a configuration file that exists and cannot be read). The start may succeed once the file can be read (a volume not yet mounted), so a supervisor may restart it. One such error beside any other error is 78.

## Stages

The stages run in the order of the start: `read`, `settings`, `principals` (the declared credentials), `databases`, `bootstrap`, `schema`, `roles`, `principalRows` (the declared access section's converge). The **offline** half of every stage runs before anything opens; the **state** half of a stage runs at its step of the start, against the data directory, before that step changes anything. A stage whose input could not be read reports that one finding; every other stage still runs, so a broken schema file does not hide a key declared twice.

## Codes

The `PRINCIPAL_*`, `KEY_ROOT_*`, `KEY_DECLARATION_INVALID`, `KEY_ID_DUPLICATE`, `OIDC_TRUST_*`, `PASSWORD_SEED_*`, `ROLE_BUILTIN_NAME`, `STATEMENT_*`, `AUTH_PUBLIC_UNRESTRICTED`, `ROLE_RUNTIME_CONFLICT`, `DECLARED_OBJECT_OVERRIDDEN`, `PUBLIC_REACH_INERT` and `ACCESS_CONVERGE_REFUSED` codes check the declared access section of `aouda.json` (principals and their credentials, roles, `signup`, the key root; see [Declared access](../guides/declared-access.md)) (**BL-1464, 0.16.0**). The role codes of the old `permissions` grammar are gone with it, and so are the codes of the identities file and the bootstrap operator settings, which are refused as `SETTING_REMOVED` (**BL-1464, 0.16.0**).

| Code | Severity | Stage | Half | Exit status | What to do |
|---|---|---|---|---|---|
| `CONFIGURATION_INVALID` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Fix the configuration file or the AOUDA_ variable named above so that it can be read. |
| `DECLARATION_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Make the setting named above (Aouda:Declaration) name a readable file (a volume not yet mounted clears when it is). |
| `DECLARATION_INVALID_JSON` | error | `read` | offline | 78 | Fix the JSON at the line named above. |
| `DECLARATION_VERSION_UNSUPPORTED` | error | `read` | offline | 78 | Set "version": 1 at the top of the declaration file: it is the only version this server reads. |
| `DECLARATION_OVERLAY_INVALID` | error | `read` | offline | 78 | Remove the member from the overlay: the version is the base file's. |
| `DECLARATION_SHAPE_INVALID` | error | `read` | offline | 78 | Give the member the shape the declaration file's reference documents (an object where an object is expected, a string where a string is). |
| `DECLARATION_UNKNOWN_MEMBER` | error | `read` | offline | 78 | Remove the member, or correct its spelling: the declaration file takes only the members it documents. |
| `SECRET_BY_VALUE` | error | `read` | offline | 78 | Remove the secret from the file and give it by reference: { "env": "NAME" } or { "file": "path" } (a password seed may also be { "hash": "<the server's password hash>" }). |
| `SECRET_REFERENCE_INVALID` | error | `read` | offline | 78 | Give the secret as exactly one of { "env": "NAME" } or { "file": "path" } (a password seed may also be { "hash": "<the server's password hash>" }). |
| `SECRET_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Set the variable, or make the secret file readable and non-empty where the server runs. |
| `OVERLAY_UNREADABLE` | error | `read` | offline | 1 when the file cannot be read (I/O), else 78 | Make the overlay readable and a JSON object (at least { "extends": "<base file name>" }), or remove it. |
| `OVERLAY_ABSENT` | info | `read` | offline | — | Nothing to do if the environment needs no overlay; otherwise create the file named above. |
| `SECRET_NOT_READ` | info | `read` | offline | — | Run `aouda plan` without --skip-secrets where the secrets are mounted (the deploy host, with the start's own mounts). |
| `DATA_DIRECTORY_FORMAT_REFUSED` | error | `read` | state | 78 | Point the server at a data directory of this format (start from an empty one and restore a backup, see the upgrade notes). It is also the first line when any other versioned file of the directory — a WAL manifest, a checkpoint, a pending restore — is damaged or of another version: a second line names the file (`FILE_FORMAT_REFUSED: kind=… found=… expected=… path=…`, or `WAL_MANIFEST_REFUSED: …` / `PITR_TARGET_REFUSED: …` for those two files), and nothing is quarantined. A key sidecar that is refused does not stop the start: the segment is read without it, and the log says so. |
| `SETTING_INVALID` | error | `settings` | offline | 78 | Set the setting named above to a value the server accepts. |
| `SETTING_REMOVED` | error | `settings` | offline | 78 | Remove the setting and use the one the message names instead. |
| `DEV_ADMIN_REFUSED` | error | `settings` | offline | 78 | Remove Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN), or remove what the message names. |
| `SERVER_KEY_DEV_ADMIN_CONFLICT` | error | `principals` | offline | 78 | Remove Aouda:Auth:DevAdmin:Enabled, or remove the credentials declared for server.principals: a development flag must not coexist with a real credential. |
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
| `KEY_ROOT_MISSING` | error | `principals` | offline | 78 | Declare "keyRoot": { "env": NAME } or { "file": path } at the top of the file, or remove the derivedKey credentials. |
| `KEY_ROOT_INVALID` | error | `principals` | offline | 78 | Generate a key root (aouda keys new-root) and give it by reference; a previous root is declared beside a different current one. |
| `KEY_DECLARATION_INVALID` | error | `principals` | offline and state | 78 | Declare a stored key as { "id": "aouda_<16>", "sha256": "<64 hex>" } and a derived key's version as a whole number from 1; never the key itself. |
| `KEY_ID_DUPLICATE` | error | `principals` | offline | 78 | Give each principal its own key: a key id is one credential of one principal. |
| `OIDC_TRUST_INVALID` | error | `principals` | offline | 78 | Give the trust an absolute https issuer, a non-empty audience and subject, and values without surrounding blanks. |
| `OIDC_TRUST_DUPLICATE` | error | `principals` | offline and state | 78 | Declare the trust on one principal: a token that matches two principals' trusts is refused. |
| `OIDC_TRUST_OVERLAP` | error | `principals` | offline and state | 78 | Add a claim that tells the two principals' tokens apart (or remove one trust): an overlap is refused, never resolved by order. |
| `OIDC_TRUST_JWKS_CONFLICT` | warning | `principals` | state | — | Delete the runtime trust, or declare the trust with the issuer's key source: an issuer has one key source, and a declared trust wins (ADR 0071 D-18). |
| `OIDC_TRUST_REDUNDANT` | warning | `principals` | offline | — | Remove the narrower trust: the wider one already matches every token it matches. |
| `PASSWORD_SEED_INVALID` | error | `principals` | offline and state | 78 | Give the seed by reference ({ "file" }, { "env" }, or { "hash" } with the server's password-hasher output), meeting the password policy. |
| `PASSWORD_SEED_NEEDS_EMAIL` | error | `principals` | offline | 78 | Name the principal by its email address (a person signs in with it), or give it a key instead of a password. |
| `SETUP_MODE_EXPECTED` | warning | `bootstrap` | offline | — | Nothing to do for an interactive first run; otherwise declare an operator in server.principals: a principal holding manage on server (the role admin), with a credential. |
| `SERVER_HAS_NO_OPERATOR` | error | `bootstrap` | state | 78 | Declare an operator in server.principals: a principal holding manage on server (the role admin), with a credential (a derived key, a stored key { id, sha256 } or a password seed). |
| `SCHEMA_FILE_UNREADABLE` | error | `schema` | offline | 1 when the file cannot be read (I/O), else 78 | Make the schema file readable where the server runs (a volume not yet mounted clears when it is), or fix SchemaFile. |
| `SCHEMA_INVALID` | error | `schema` | offline | 78 | Fix the schema file at the pointer named above. |
| `SCHEMA_UNKNOWN_MEMBER` | error | `schema` | offline | 78 | Remove the member, or correct its spelling: a schema file takes only the members the schema format defines. |
| `SCHEMA_OVERLAY_INVALID` | error | `schema` | offline | 78 | Make the overlay extend its base file by name and change only what an overlay may change: `$schema`, `extends`, `settings.durability` and an existing table's `policy` and `durability`. A member outside that list is the HTTP-reference error `SCHEMA_OVERLAY_MEMBER_NOT_ALLOWED` (**BL-1460, 0.14.0**); a plan and a start report it under this code, naming the member and its JSON pointer. Move the member to the base file. |
| `SCHEMA_LIMIT_EXCEEDED` | error | `schema` | offline | 78 | Simplify the named query, or raise Aouda:NamedQuery:MaxJoins / MaxCost. |
| `SCHEMA_DATABASE_MISMATCH` | warning | `schema` | offline | — | Make the file's 'database' member name the database that declares it, or remove the member: the start applies the file to the declaring database. |
| `SCHEMA_DATABASE_NOT_OPEN` | error | `schema` | state | 78 | Open the database (repair it), or list it in Aouda:SkipDatabases to start without it. |
| `SCHEMA_CHANGE_REFUSED` | error | `schema` | state | 78 | Change the schema file so that the engine can apply it (a partition key is fixed once set; a table keeps at least one column). |
| `SCHEMA_DESTRUCTIVE_REFUSED` | warning | `schema` | state | — | Set SchemaAllowDestructive for the database to apply the destructive change, or make the file match the catalog. |
| `ROLE_NAME_INVALID` | error | `roles` | offline | 78 | Give the role a name. |
| `ROLE_NAME_DUPLICATE` | error | `roles` | offline | 78 | Declare the role once: role names are compared without regard to case. |
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
| `PLAN_TARGET_UNREACHABLE` | error | `target` | target | — (`aouda plan` exits 69) | Check that the server is running this release or later, reachable at the URL given, and ready; retry after the delay it named. |
| `PLAN_TARGET_REFUSED` | error | `target` | target | — (`aouda plan` exits 77) | Give an operator key of that server with --key-file PATH or --key-env NAME. |
| `PLAN_DATA_DIRECTORY_IN_USE` | error | `target` | target | — (`aouda plan` exits 69) | Plan the running server with --server URL --key-file PATH, or stop it and plan again: two processes on one data directory are not safe. |
| `PLAN_DATA_DIRECTORY_NEEDS_RECOVERY` | error | `target` | target | — (`aouda plan` exits 69) | Start the server once on this directory (it removes interrupted creations and drops), then plan again; a plan does not simulate the recovery. |

A code whose half is **target** is emitted only by `aouda plan --server` or `aouda plan --data-dir`, about the target it plans against: the server could not be reached or did not answer with a plan, or the data directory does not exist or cannot be listed (`PLAN_TARGET_UNREACHABLE`, exit 69); the server refused the key (`PLAN_TARGET_REFUSED`, exit 77); another Aouda process holds the data directory (`PLAN_DATA_DIRECTORY_IN_USE`, exit 69); or a crash left a database half-created or half-dropped and only a start recovers it (`PLAN_DATA_DIRECTORY_NEEDS_RECOVERY`, exit 69). None is a finding about the declaration, and no start or reload emits them (**BL-1463, 0.16.0**). Stage `target` is not a stage of the start.

`SERVER_HAS_NO_OPERATOR` is one rule checked at two moments of the start: before the schema step (stage `bootstrap`) and after the declared access section is converged (stage `principalRows`).

A message never contains a key, a hash or a secret file's content; a path that contains a key is shown as `<redacted>`. `aouda keys new` prints the `sha256` you put beside a stored key's id. `aouda keys new-root` and `aouda keys derive` write a root or a key to a file.
