---
title: "Plan a declaration"
nav_order: 4.5
parent: "Guides"
---

# Plan a declaration: `aouda plan` (**BL-1463, next train**)

`aouda plan` answers one question **before** anything starts: *would `aouda start` refuse this declaration, and for which reasons — all at once?*
It reads the configuration the same way `aouda start` does, runs the same checks, prints every finding and exits `0` or `1`. It needs **no server
and no data directory**, opens no port and writes nothing, so it runs in CI before a deploy and on a laptop before a commit.

It replaces `aouda keys check` and `aouda schema check`, which are gone ([below](#replacing-aouda-keys-check-and-aouda-schema-check)).

```bash
aouda plan                                      # the configuration this directory and environment would start with
aouda plan --Aouda:Auth:Keys:File=/etc/aouda/aouda.identities.json --skip-secrets
aouda plan --json                               # one JSON object on standard output
```

## What it checks

The stages of the start, in the order of the start, each on what it can read without a data directory:

1. **read** — every file the declaration names is read: the identities file, the secret files and environment variables it points at, the server key's file or
   credential, every schema file and its overlay. A file that cannot be read is one finding, not a crash.
2. **settings** — the process settings (`Aouda:Port`, the memory limits, `Aouda:NamedQuery:*`, ...), the removed keys and the dev-admin guards.
3. **principals** — the identities file's entries, the key shapes, the server key's one source, the dev admin beside a server key, and the conflicts between declared keys.
4. **databases** — `Aouda:Databases`: names, kinds, links and per-kind fields.
5. **bootstrap** — the first administrator: a server key, `Aouda:Auth:RootUser`, or a data directory that starts in setup mode.
6. **schema** — every declared schema file, read with the server's own reader (a misspelt member is refused with its JSON pointer), the overlay merge, and the apply-time rules that need no tables.
7. **roles** — declared roles: names, the grammar of their permissions, the tables and named artifacts they name.
8. **principalRows** — what the key declarations would write.

Every stage runs on what it can check, so a broken schema file does not hide a duplicate key secret. Every finding has a **severity**, a stable **code** ([Declaration finding codes](../reference/plan-codes.md)),
a **location** (a file and a JSON pointer, or a setting and the configuration source that supplied it), a message and what to do. `error` is exactly a refusal of the start;
a `warning` is accepted and logged once; `info` is context.

## The command

`aouda plan` takes **the arguments `aouda start` takes**: the same `--Aouda:Section:Key=value` settings, `--port`, `--data-dir`, `--dev-admin`, the same environment variables
(`Aouda__Auth__Keys__File` and the `AOUDA_` spelling), the `appsettings*.json` of the working directory, and the systemd credentials in `$CREDENTIALS_DIRECTORY`. There is no separate input to
learn and no `--` separator. Whatever you give `aouda start`, give `aouda plan`.

| Option | Meaning |
|---|---|
| `--skip-secrets` | Do not read secrets: check everything that does not need their content. See [below](#when-the-secrets-are-not-there). |
| `--json` | Print one JSON object instead of text. `--output json` does the same. |

Giving either a value (`--json=false`) is a usage error.

### Output

The whole plan goes to **standard output**, in both formats; standard error carries only a usage error.

```text
aouda plan: settings + /etc/aouda/aouda.identities.json (environment Production), 13 databases, 11 schema files

error    KEY_SECRET_SHARED  Aouda:Auth:Bootstrap:ServerKeyFile  (environment variable Aouda__Auth__Bootstrap__ServerKeyFile)
         Configured keys 'bootstrap-server-key' and 'server' share one secret.
         also: /etc/aouda/aouda.identities.json  /identities/0/secrets/0
         fix:  Declare the server key once: keep Aouda:Auth:Bootstrap:ServerKeyFile and remove the 'server' entry's secret from the identities file.

stages   read ok, settings ok, principals 1 error, databases ok, bootstrap ok, schema ok, roles ok, principalRows ok
not checked  the data directory and every existing database, table, key row and role (no --server or --data-dir)
             the environment the server will start in (hosting environment here: Production; variables an orchestrator sets at start)

1 error, 0 warnings: `aouda start` would refuse this declaration.
```

With `--json` the object has `format` (`aouda-plan/1`), `aoudaVersion`, `declaration` (the identities file, the environment, the number of schema files and a `planHash`), `target`
(`{ "kind": "offline" }`), `outcome` (`clean` or `errors`), `summary`, `stages` (each `passed`, `warnings`, `failed` or `skipped`, with `skippedBecause` naming the code that blocked it),
`findings`, `changes` (always `null` offline) and `notChecked`. The same input gives the same bytes. A path that holds a key (a key pasted where a path belongs) is shown as `<redacted>`; a plan
never contains a key, a hash of one or the content of a secret file.

The `planHash` is the SHA-256 of the declaration with every secret replaced by its fingerprint: two plans of one declaration have one hash. A `--skip-secrets` plan hashes the references it did not
read, so its hash differs from a full plan's.

### Exit status

| Code | Outcome | Meaning |
|---|---|---|
| `0` | `clean` | no `error` finding: `aouda start` would not refuse this declaration (warnings and info never change the code) |
| `1` | `errors` | at least one `error` finding. When every error is a file that could not be read, the last line says the start "would fail here (a file could not be read) and may succeed once it can be" |
| `64` | — | misuse: a switch given a value, or `aouda keys check` / `aouda schema check`, which no longer exist |

There is no "could not check" status and no `--strict`: a warning that should block is an error the start should refuse. Other exit codes belong to plans against a running server and a data directory, which an offline plan never exits with.

## What `aouda plan` cannot know

A green plan is not more than it says. Every offline plan lists what it did not check under `notChecked`, and these are the limits:

1. **Without a target:** anything in the data directory. Which databases exist and with which kind and link, the tables (so no schema diff and no destructive change), the key rows (a secret another row holds, an operator's revocation), roles created through the API, the data-directory format, whether `_serverauth` already has an admin.
2. **Secrets in another environment.** The plan reads `env` and `file` secrets where it runs. A CI runner with no secrets, or a host path that differs from the container's, makes those checks unknowable (`--skip-secrets`). The reliable gate is the plan run with the same mounts and environment as the start (`docker compose run --rm --no-deps aouda plan`).
3. **The process environment at start.** Variables an orchestrator injects at start and that are absent where the plan ran.
4. **Apply failures that depend on row values,** even with a target, unless the engine's dry run checks them (a `NOT NULL` column on a table with rows, a `unique` flag on a column with duplicates, a narrowing type change).
5. **Resources and the host:** free ports, memory, disk, file permissions for the server's user (the plan may run as another user), the clock, whether the email or SMS provider answers.
6. **A node's replication role:** whether a follower would write is not planned.
7. **Races:** anything that changes between the plan and the start or reload. `planHash` shows which declaration was planned; it is not a lock.
8. **How long the start will take:** not estimated.

One consequence worth stating: a data directory that has been set up and has no user and no active server key refuses to start with `SERVER_HAS_NO_OPERATOR`. An offline plan cannot see the
data directory, so for a declaration that declares no first administrator it exits `0` with the warning `SETUP_MODE_EXPECTED`. That is the one place the start refuses for a reason a plan cannot see.

## When the secrets are not there

A CI runner usually has the identities file and the schema files (they are in the repository) but not the secrets they point at. `--skip-secrets` checks everything that does not need their content:

```bash
aouda plan --Aouda:Auth:Keys:File=deploy/aouda.identities.json --skip-secrets
```

With the flag, **nothing secret is read or looked for**: no `env` variable, no `file` secret, no `ServerKeyFile`, no systemd credential (so whether a credential exists is unknown). Still read: the configuration, the
identities file itself, every schema file and overlay, and a server key given as a literal in configuration. Still checked, from form alone: exactly one source per secret, a well-formed `hash`, a literal
`key` (`SECRET_BY_VALUE`), a present `env` name and `file` path, `ServerKey` together with `ServerKeyFile`, and every name, kind, database and role rule that does not touch a secret.

Two declarations that name the **same** `env` variable or the **same** file path (as written, a relative path resolved against the identities file) are `KEY_SECRET_SHARED` exactly as when the secrets are
read. What cannot be checked is skipped: an unreadable secret, the shape or prefix of a secret that was not read, a credential beside `ServerKeyFile`, and a secret shared by *content*.

The plan says what it skipped: one `info` finding, `SECRET_NOT_READ`, carries the **count** of references it did not read (never a variable name or a path), and `notChecked` says so too.

## Recipes

**CI, before a deploy** — the identities file and the schema files are in the repository, the secrets are not:

```bash
aouda plan --Aouda:Auth:Keys:File=deploy/aouda.identities.json \
           --Aouda:Databases:app:Kind=data \
           --Aouda:Databases:app:SchemaFile=deploy/aouda.schema.json --skip-secrets
```

**On the deploy host, with the start's own mounts** — the strongest offline gate, because it reads what the start will read:

```bash
docker compose run --rm --no-deps aouda plan
```

**A schema file that is declared nowhere else** is checked by declaring it to the plan, as above (`Aouda:Databases:<name>:SchemaFile`, and `SchemaEnvironment` to merge its overlay). A schema that is applied through
the API instead of declared is checked against a server with `aouda schema diff`.

## Replacing `aouda keys check` and `aouda schema check`

Both commands are deleted — no alias, no "did you mean": `aouda keys check` and `aouda schema check` are unknown subcommands and exit `64`. `aouda keys hash` stays, and so do `aouda schema validate`,
`diff`, `apply` and `export`.

| Before | Now |
|---|---|
| `aouda keys check --file X` | `aouda plan --Aouda:Auth:Keys:File=X` (add `--skip-secrets` where the secrets are absent) |
| `aouda keys check -- --dev-admin` | `aouda plan --dev-admin` (no separator) |
| `aouda schema check --file F --env E` | `aouda plan --Aouda:Databases:app:Kind=data --Aouda:Databases:app:SchemaFile=F --Aouda:Databases:app:SchemaEnvironment=E` |
| `aouda schema check` for a schema that is not declared | `aouda schema diff` against a server |
| exit `2` from either command | exit `1` (or `64` for misuse); `2` no longer means "could not check" |
| the declaration listing `keys check` printed | not printed; `GET /api/auth/admin/configured-keys` lists a running server's declarations |

The `schema check` page's two lessons still hold. **`plan` and `schema validate` are different:** `plan` asks whether the declaration is acceptable on its own, with no server; `schema validate` asks whether
a live database matches a file (drift), and needs one. And **the start runs the same checks:** a declared database's schema file is checked before the start changes any database, with that server's own
named-query ceilings, so a file the plan passes cannot fail the start for a reason that sits in the document alone.

## See also

- [Declaration finding codes](../reference/plan-codes.md): every code, its stage and its remedy.
- [Keys that survive a wipe](keys-that-survive-a-wipe.md) and [Declared databases](declared-databases.md): what is declared.
- [Schema CI/CD](schema-cicd.md) and [Schema management](schema-management.md).
