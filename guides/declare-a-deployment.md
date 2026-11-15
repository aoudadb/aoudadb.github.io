---
title: "Declare a deployment"
nav_order: 2.4
parent: "Guides"
---

# Declare a deployment: one complete, working set (**next train**)

This page is the end-to-end path for a multi-service deployment that is **declared** instead of scripted: two data databases and
one auth database, the keys and roles every service needs, a compose file, a plan before the deploy, a wipe-and-start, and a
reload. Every file below is one set. The files were run through `aouda plan` (exit `0`, 0 errors, 0 warnings, with and without
`--skip-secrets`) and through a real `aouda start` and `aouda reload` before they were written here; copy them together.

It stitches together pages that each explain one piece: [Declared databases](declared-databases.md) (every `Aouda:Databases` key),
[Keys that survive a wipe](keys-that-survive-a-wipe.md) (every identities-file field), [Plan a declaration](plan.md) (every
finding and exit status), [Docker](../deployment/docker.md) (the image, memory, probes) and the
[reload / restart table](server-configuration.md#reload-or-restart). Read those for the rules; read this for the working whole.

Not declarable today: users, user-linked keys, entitlements, RLS resolvers and signup settings. Keep a short seed step for them
([What a wipe still loses](#what-a-wipe-still-loses)).

## The set

Five things, in one directory next to the compose file:

```text
compose.yaml
declaration/              mounted read-only at /etc/aouda in the container
  aouda.json              Aouda:Databases, the roles, and where the other files are
  identities.json         the keys
  deposit.schema.json     tables and named mutations of the deposit database
  ledger.schema.json      tables of the ledger database
secrets/                  one file per key, never committed
  aouda_server_key  deposit_service_key  ledger_service_key  deposit_public_key  tullett_feeder_key
```

| Piece | Kind | What it is |
|---|---|---|
| `derive_auth` | auth database | Holds the roles and the key rows of both data databases. Named explicitly on every key and database below |
| `deposit` | data database | The quote store. A table `quotes` and the named mutation `insert_quote` |
| `ledger` | data database | A second database with its own table and its own `service_role` key |
| `operator` | `server_admin` key | **The server key.** Operates the server and runs `aouda reload`. Declaring it ends setup mode: no first-admin password is needed |
| `deposit-service`, `ledger-service` | `service_role` keys | One backend key per data database (`mk_svc_`) |
| `deposit-public` | `public` key | The browser-tier key of `deposit` (`mk_pub_`) |
| `tullett-feeder` | `scoped_service` key | An external feeder that may run `insert_quote` and nothing else (`mk_scp_`) |

### `declaration/aouda.json`

The file has the shape of `appsettings.json`: one top-level `Aouda` object. The server reads `/etc/aouda/aouda.json` by itself when
it exists, with no setting (**next train**; see [The declaration file](server-configuration.md#declaration-file)).

```json
{
  "Aouda": {
    "Auth": {
      "Keys": { "File": "/etc/aouda/identities.json" }
    },
    "Databases": {
      "derive_auth": {
        "Kind": "auth",
        "Roles": {
          "quote_writer": {
            "Description": "Feeds quotes into deposit through insert_quote, and reads them back",
            "Permissions": [
              { "ResourceType": "named-mutation", "ResourceName": "insert_quote", "Actions": "execute" },
              { "ResourceType": "table", "ResourceName": "quotes", "Actions": "read" }
            ]
          }
        }
      },
      "deposit": {
        "AuthDatabase": "derive_auth",
        "SchemaFile": "/etc/aouda/deposit.schema.json"
      },
      "ledger": {
        "AuthDatabase": "derive_auth",
        "SchemaFile": "/etc/aouda/ledger.schema.json"
      }
    }
  }
}
```

- **`Kind`** is `auth` or `data` (the default). **`AuthDatabase`** links a data database to its auth database; the auth database is never
  created for you, so it is declared here with `Kind: auth`.
- A role is declared on the **auth** database (a `Roles` block on a data database fails the start) and applied **after** the schema,
  so it may name the table `quotes` and the mutation `insert_quote` that `deposit.schema.json` creates.
- **The role holds two items, and the mutation one is the one that matters.** Running a named mutation needs an `execute` item on it
  and **no table right**. A table `write` does not run mutations. The table `read` item lets the feeder read back what it wrote.
- Paths are the container's: the directory is mounted at `/etc/aouda`.

### `declaration/identities.json`

```json
{
  // One entry per credential. Comments and trailing commas are allowed; a top-level "$schema" is not.
  "identities": [
    {
      "name": "operator", "kind": "server_admin",
      "secrets": [ { "file": "/run/secrets/aouda_server_key" } ],
    },
    {
      "name": "deposit-service", "kind": "service_role",
      "authDatabase": "derive_auth", "database": "deposit",
      "secrets": [ { "file": "/run/secrets/deposit_service_key" } ],
    },
    {
      "name": "ledger-service", "kind": "service_role",
      "authDatabase": "derive_auth", "database": "ledger",
      "secrets": [ { "file": "/run/secrets/ledger_service_key" } ],
    },
    {
      "name": "deposit-public", "kind": "public",
      "authDatabase": "derive_auth", "database": "deposit",
      "secrets": [ { "file": "/run/secrets/deposit_public_key" } ],
    },
    {
      "name": "tullett-feeder", "kind": "scoped_service",
      "authDatabase": "derive_auth", "database": "deposit",
      "roles": ["quote_writer"],
      "secrets": [ { "file": "/run/secrets/tullett_feeder_key" } ],
    },
  ],
}
```

Five things about this file that cost a first attempt time:

1. **Set `authDatabase` on every key except `server_admin`.** An omitted `authDatabase` silently means a database called `auth`. If none
   of that name exists, `aouda plan` exits `0` with only the warning `KEY_TARGET_PENDING`, the key gets no row, and every request with it is `401`.
2. **`server_admin` lives on the server auth database**, so it has no `authDatabase` and no `database`.
3. **`roles` is for `scoped_service` only**, and each role must be declared on that auth database (`KEY_ROLE_UNDECLARED` otherwise) and
   `database` must be linked to it (`KEY_DATABASE_NOT_LINKED` otherwise). A system kind (`service_role`, `public`, `anon`) takes no `roles`.
4. **The file takes comments and trailing commas, and rejects a top-level `$schema`** (`DECLARATION_UNKNOWN_MEMBER`). There is no JSON
   Schema for this file: `schemas/aouda-identities.v1.json` describes a different file, the test-identities fixture.
5. **A secret is exactly one of `file`, `env` or `hash`.** `file` reads the key from a file (a Docker secret mounts at `/run/secrets/<name>`);
   one trailing newline is ignored. Only `file` and `hash` secrets can change by [reload](#change-it-without-a-restart); an `env` secret keeps the value the process started with.

### `declaration/deposit.schema.json` and `declaration/ledger.schema.json`

```json
{
  "tables": {
    "quotes": {
      "description": "Latest quote per ticker, written by the feeders through insert_quote",
      "columns": {
        "ticker": { "type": "String", "primaryKey": 1 },
        "px": { "type": "Double" }
      }
    }
  },
  "namedMutations": {
    "insert_quote": {
      "op": "insert",
      "table": "quotes",
      "values": { "ticker": { "param": "ticker" }, "px": { "param": "px" } },
      "params": { "ticker": { "maxLength": 8 }, "px": {} },
      "version": "v1"
    }
  }
}
```

```json
{
  "tables": {
    "entries": {
      "columns": {
        "id": { "type": "Int64", "primaryKey": 1 },
        "account": { "type": "String" },
        "amount": { "type": "Double" }
      }
    }
  }
}
```

The table `description` is documentation in the file only (**next train**; [Schema reference](schema.md#tabledefinition-entry-in-tables)). Schema
files are strict: a member that is not in the reference is `SCHEMA_UNKNOWN_MEMBER`, and plan lists every one.

### `compose.yaml` {#compose-yaml}

```yaml
services:
  aouda:
    image: ghcr.io/aoudadb/aouda-server:<version>
    stop_grace_period: 130s
    mem_limit: 2g
    cpus: 4
    ports:
      - "127.0.0.1:5000:5000"
    volumes:
      - aouda-data:/data
      # A directory, not a single file: see "Mount the directory" below.
      - ./declaration:/etc/aouda:ro
    secrets:
      - aouda_server_key
      - deposit_service_key
      - ledger_service_key
      - deposit_public_key
      - tullett_feeder_key

secrets:
  aouda_server_key:
    file: ./secrets/aouda_server_key
  deposit_service_key:
    file: ./secrets/deposit_service_key
  ledger_service_key:
    file: ./secrets/ledger_service_key
  deposit_public_key:
    file: ./secrets/deposit_public_key
  tullett_feeder_key:
    file: ./secrets/tullett_feeder_key

volumes:
  aouda-data:
```

(`docker compose config` accepts it. The image is private: log in first, [Docker](../deployment/docker.md).)

**Mount the directory, not the file** (**next train**). A compose line `./aouda.json:/etc/aouda/aouda.json:ro` binds one *file*,
and Docker pins that file's inode: an editor that saves by writing a new file and renaming it over the old one (most do), a
`git checkout` and `mv` all replace the inode, and the container keeps reading the old content for the life of the container. Tested
with Docker 29: after a rename-over on the host the container still showed the old text, and even a later in-place write was not
seen. A **directory** mount follows the name, so a replaced file shows at once. The reload reads the path every time, with no
file watcher, so a directory mount is all it needs.

`/etc/aouda/aouda.json` is the file the server reads when no setting names another; nothing in the compose file tells it. To put the
file elsewhere, set `AOUDA_CONFIG_FILE=/path` in `environment:` (or pass `--config /path`).

## Make the secrets

One file per key. The shape rule is the prefix of the kind, then at least 32 characters from `A-Z a-z 0-9 _ -`; `openssl rand -hex 32`
is the generator (there is no `aouda keys generate`).

```bash
mkdir -p secrets && chmod 700 secrets && umask 077
printf 'mk_srv_%s' "$(openssl rand -hex 32)" > secrets/aouda_server_key
printf 'mk_svc_%s' "$(openssl rand -hex 32)" > secrets/deposit_service_key
printf 'mk_svc_%s' "$(openssl rand -hex 32)" > secrets/ledger_service_key
printf 'mk_pub_%s' "$(openssl rand -hex 32)" > secrets/deposit_public_key
printf 'mk_scp_%s' "$(openssl rand -hex 32)" > secrets/tullett_feeder_key
chmod 0444 secrets/*        # see below: the container's user is not you
```

**The container reads these files as uid 1654, not as you.** Compose bind-mounts a `file:` secret with the host file's owner and mode (tested with
Compose 2.40: a `0600` file owned by uid 1000 showed up in the container as `-rw------- 1000 1000` and `cat` failed with `Permission denied`). Left at
`0600`, every secret is `SECRET_UNREADABLE` at start (exit `1`, a restart loop). The `chmod 0444` makes the file readable by the container; the `700`
directory keeps every other user of the host out.

| Kind | Prefix |
|---|---|
| `server_admin` | `mk_srv_` |
| `service_role` | `mk_svc_` |
| `scoped_service` | `mk_scp_` |
| `public` | `mk_pub_` |
| `anon` | `mk_anon_` |

Put each key in your secret store as well; the services read theirs from there, and a wipe does not change any of them: the same
files declare the same keys again.

## Plan it before you start it

`aouda plan` runs the start's own checks over this directory and prints every problem at once. It needs no server and no data directory.

**On the deploy host, with the start's own mounts** (the strongest check, because it reads what the start will read):

```bash
docker compose run --rm --no-deps --entrypoint aouda aouda plan
```

Output for the files above, secrets present (run with the same files at other paths; the paths below are the container's):

```text
aouda plan: settings + /etc/aouda/identities.json (environment Production, config file /etc/aouda/aouda.json), 3 databases, 2 schema files

stages   read ok, settings ok, principals ok, databases ok, bootstrap ok, schema ok, roles ok, principalRows ok
not checked  the data directory and every existing database, table, key row and role (no --server)
             the environment the server will start in (hosting environment here: Production; variables an orchestrator sets at start)

0 errors, 0 warnings: `aouda start` would not refuse this declaration (see not checked).
```

Exit status `0`. The header names `config file <path>` (or `config file none`): which file was read (**next train**). `1` means the start would
refuse, `64` is misuse, and `2`, `69` and `77` belong to `--server` below. Read the **warnings** as well as the exit status: `KEY_TARGET_PENDING`,
`KEY_ROLE_UNDECLARED` and `KEY_DATABASE_NOT_LINKED` are warnings, and each leaves a key that answers `401`.

**On a CI runner**, with no secrets and no container: the file names container paths (`/etc/aouda/...`), so give the runner a copy
whose paths are the checkout's, and `--skip-secrets`:

```bash
dotnet tool install -g Aouda.Cli --version "$AOUDA_VERSION"    # the version you deploy
sed -e 's#/etc/aouda/#declaration/#g' declaration/aouda.json > "$RUNNER_TEMP/aouda.ci.json"
aouda plan --config "$RUNNER_TEMP/aouda.ci.json" --skip-secrets
```

`--config PATH` makes the plan read the file the start would read (**next train**); relative paths are resolved from the working directory
(run it from the checkout's root) and a relative secret path from the identities file's directory. With `--skip-secrets` the plan
checks form, names, conflicts and every schema file but reads no key. A fuller CI job, the CLI install and the `--server` key are in
[Plan a declaration](plan.md#a-ci-job-aouda-plan-on-every-pull-request).

**Against the running server** (what a deploy would change, `2` when it would change something):

```bash
aouda plan --config "$RUNNER_TEMP/aouda.ci.json" --skip-secrets \
  --server https://aouda.internal:5000 --key-env AOUDA_PLAN_KEY
```

`--key-env` names a variable holding the **target server's** `mk_srv_` key. It is its own CI secret, not a key of this declaration.

## Wipe and start

```bash
docker compose down -v          # removes the data volume: every database, row, user and minted key is gone
docker compose up -d
until curl -fsS http://127.0.0.1:5000/ready >/dev/null; do sleep 2; done; echo ready
```

`/ready` answers `503` with the reasons that still hold while the server opens its databases, applies the schema files, creates the roles
and writes the key rows (`database_pending`, `schema_applying`, `configured_key_inactive`, ...); the list is in
[Declared databases](declared-databases.md#what-ready-says-while-it-starts). **Wait on `/ready`, never on `/health`**: `/health` is `200` in
every state, including while the start is still running. When the loop ends:

- the three databases exist, `deposit` and `ledger` linked to `derive_auth`;
- `quotes` and `entries` exist, empty, and `insert_quote` is registered;
- the role `quote_writer` exists with its two permissions;
- the five keys exist as rows, with the secrets in `secrets/`;
- no admin user exists and none is needed: the key `operator` operates the server (no setup mode).

A start that refuses its declaration prints every finding on standard error and **exits `78`**; under `restart: unless-stopped` that is a
restart loop, so read the container's output: [A container that keeps restarting](../deployment/docker.md#a-container-that-keeps-restarting).

## The feeder pattern, end to end

A feeder is an external sender that must be able to **write one kind of row and do nothing else**, with a credential that survives a wipe.
The supported pattern is three declarations that name each other:

| Where | What it says | In the set above |
|---|---|---|
| The schema file | The write is a **named mutation**: a fixed insert with typed parameters | `insert_quote` in `deposit.schema.json` |
| The role (on the auth database) | `execute` on that mutation, and only what else the feeder may read | `quote_writer` in `aouda.json` |
| The identities file | A `scoped_service` key (`mk_scp_`) holding that role on one database | `tullett-feeder` in `identities.json` |

Run it with the feeder's key:

```bash
curl -s -X POST http://127.0.0.1:5000/api/databases/deposit/named-mutations/insert_quote/execute \
  -H "Authorization: Bearer $(cat secrets/tullett_feeder_key)" -H 'Content-Type: application/json' \
  -d '{"args":{"ticker":"EQNR","px":301.5}}'
```

```json
{"rowsInserted":1,"executionMs":0,"token":"01c3b9fb78a452ce2f0000000000000000000001a8"}
```

The same key is refused everywhere else: a direct write to `quotes` is `INSUFFICIENT_PERMISSIONS` (`currentRoles=[quote_writer]`), and a read of
another database (`ledger`) is `AUTHORIZATION_DENIED`, because a `mk_scp_` key reaches only the databases and tables its roles name.
The body of the request is `{ "args": { ... } }`; a parameter the mutation requires and the body omits is `NAMED_QUERY_PARAM_REQUIRED`.

**What this does not give you, and what to use instead of a user-linked key.** A *user-linked* `custom` key (a key made through the API with a
`userId`) can carry per-partition entitlements, but it **cannot be declared**: it lives in the data directory, so a wipe loses it and a new
deploy has to mint it again and hand the new value to the sender. Use the declared `scoped_service` key above for a feeder that must survive
a wipe.

The limit, plainly: **a declared key holds roles only.** Entitlements cannot be declared on a scoped key yet, so you cannot
say "this feeder may write only the rows of its own source" and have the server enforce it per source. Every feeder holding
`quote_writer` can run `insert_quote` for any ticker. Where that matters, give each feeder its own role and mutation (for example a mutation that
fixes the `source` column to a constant), or put the per-source check in the service that fronts the feeder. This page promises no date for entitlements on a declared key.

## Change it without a restart

A key change is not a deploy. Edit the files in `declaration/` and ask the running server to re-read them:

```bash
docker compose exec aouda aouda reload --server http://localhost:5000 --key-file /run/secrets/aouda_server_key
```

- **`--server` is required** (the image listens on port 5000), and so is exactly one of `--key-file PATH` or `--key-env NAME`. There is no `--key`:
  a command line is kept in the process list and in shell history.
- **The key file must exist inside the container the command runs in.** Here the compose service lists the secret, so Compose mounts it
  at `/run/secrets/aouda_server_key`. A file that exists only on the host is not there, and the command exits `64`. The command can instead
  run on the host against the published port: `aouda reload --server http://127.0.0.1:5000 --key-file ./secrets/aouda_server_key`.
- Dry run first: `aouda plan --server http://localhost:5000 --key-file ... ` lists what a reload would change and writes nothing.

Output of a reload that added a fourth database (`reports`, linked to `derive_auth`) to `aouda.json`, shortened:

```text
aouda reload: http://localhost:5000 (standalone)

applied: 2 changes.
```

(A reload also prints one `restart` line for each setting it lists under `restartRequired`: settings it cannot apply; see the [table](server-configuration.md#reload-or-restart).) Exit status `0` means
nothing to change, `2` applied, `1` refused or stopped part-way, `64` usage, `69` unreachable, busy, rate-limited (one reload per 5 s) or still starting,
`77` the key was refused. A second reload with nothing changed answers `nothing to change.` and exits `0`.

**What a reload does and does not re-read** (**next train** for the first row):

| Edited | A reload |
|---|---|
| `declaration/aouda.json`: a new database, a database's `SchemaFile` or `Roles`, a first `AuthDatabase` link | Applies it |
| `declaration/identities.json`: add, remove or rotate a key | Applies it. Removing an entry revokes its row |
| A schema file | Applies it, non-destructively (a drop is the warning `SCHEMA_DESTRUCTIVE_REFUSED` and `/ready` says `schema_drift`) |
| A key file (`{ "file": ... }` secret) | Re-read on every reload: replace the file's content, or add a second secret and remove the first later |
| An `{ "env": ... }` secret | **Not changed**: a running process cannot change its own environment. Restart |
| The server key's path, `Aouda:Auth:Keys:File`'s path, the port, memory, a database's operational fields | Listed as `restartRequired`; restart |
| `Aouda:Databases` or the identities path set by **environment variables or the command line** | Not seen (`SOURCE_NOT_RELOADABLE`): they are fixed for the life of the process. Put them in `aouda.json` |

An **empty** `aouda.json`, a malformed one or a missing one refuses the reload (`422 RELOAD_REFUSED` with the finding `CONFIGURATION_INVALID`) and
changes nothing. Write `{}` to declare nothing: it is read as "no change", not as "retract everything" (a database you remove from the file is
only reported as `orphaned`, and with no key source nothing is retracted).

## What a wipe still loses

| Not declarable | Do this |
|---|---|
| Users, sessions, refresh tokens | Create them again after the start (or from a seed step that runs once `/ready` is `200`) |
| User-linked keys, entitlements | Create them again; they cannot be declared (see the feeder section) |
| RLS resolvers | Create them again over HTTP, with the server key |
| Signup settings | Set them again |
| Every row | Reload your data |

## When the plan or the start says no

| You see | It means | Fix |
|---|---|---|
| `KEY_TARGET_PENDING` (warning), requests `401` | The key's `authDatabase` (or the omitted default `auth`) does not exist | Name `derive_auth` on the entry |
| `KEY_ROLE_UNDECLARED` / `KEY_DATABASE_NOT_LINKED` (warning) | The role is not declared on that auth database, or `database` is not linked to it | Declare the role in `aouda.json`; set `AuthDatabase` on the database |
| `DECLARATION_UNKNOWN_MEMBER` at `/$schema` | A top-level `$schema` in the identities file | Remove it |
| `KEY_SHAPE_INVALID` | A key is not the kind's prefix plus 32 or more characters | Make it with `openssl rand -hex 32` |
| `KEY_SECRET_SHARED` | Two entries (or an entry and the server key) share a file or variable | One secret per key |
| `SECRET_UNREADABLE` in a plan on a runner | The secret file is a container path | Use `--skip-secrets` there; plan on the host for the strongest check |
| `CONFIGURATION_INVALID` naming `aouda.json` | Missing (named by `--config` / `AOUDA_CONFIG_FILE`), empty, a directory, or not valid JSON | Fix the file; `{}` is the empty declaration |
| A container that restarts, status `78` | The start refused the declaration | `docker compose logs --no-log-prefix aouda` names every finding |
| `aouda reload` exits `64` | The `--key-file` path does not exist where the command runs (a file that is only on the host) | Mount the secret into the container, or run the command on the host |

The complete list of codes, with the stage that emits each and its exit status, is [Declaration finding codes](../reference/plan-codes.md).

## Related

- [Declared databases](declared-databases.md), [Keys that survive a wipe](keys-that-survive-a-wipe.md), [Plan a declaration](plan.md)
- [Docker](../deployment/docker.md), [Kubernetes and Helm](../deployment/kubernetes.md#declaring-databases-keys-and-schema-files), [Server configuration](server-configuration.md)
- [Getting started: Auth](../getting-started/auth.md), [Client integration: when to use which key](../auth/client-integration.md)
