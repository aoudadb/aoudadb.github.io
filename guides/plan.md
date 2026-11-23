---
title: "Plan a declaration"
nav_order: 4.5
parent: "Guides"
---

# Plan a declaration: `aouda plan` (**BL-1463, 0.14.0**)

`aouda plan` answers one question **before** anything starts: *would `aouda start` refuse this declaration, and for which reasons — all at once?*
It reads the configuration the same way `aouda start` does, runs the same checks, prints every finding and exits `0` or `1`. It needs **no server
and no data directory**, opens no port and writes nothing, so it runs in CI before a deploy and on a laptop before a commit.

It replaces `aouda keys check` and `aouda schema check`, which are gone ([below](#replacing-aouda-keys-check-and-aouda-schema-check)).

```bash
aouda plan --declaration aouda.json --env prod # the declaration file, its prod overlay and the settings this directory would start with (BL-1463, 0.16.0)
aouda plan # the settings only: with no `Aouda:Declaration`, nothing is declared (`declaration: none`)
aouda plan --declaration /etc/aouda/aouda.json --skip-secrets # where the key root and the password seeds are not mounted
aouda plan --json # one JSON object on standard output
aouda plan --server https://aouda.internal:5000 --key-file server.key # what a deploy would change on a running server (BL-1463, 0.14.0)
```

With `--server` it also asks a running server what the declaration would change there, and exits `2` when it would change something
([Against a running server](#against-a-running-server---server-bl-1463-0140)).

**Which file it reads.** The plan reads the declaration the start reads: the file `Aouda:Declaration` names (`--declaration`, `AOUDA_DECLARATION`). There is no default path. With the setting unset, nothing is declared (`declaration: none`). A path that is set and cannot be read is `DECLARATION_UNREADABLE`. `Aouda:Databases`, `AOUDA_CONFIG_FILE` and `--config` are not how this server finds the file ([Declare a server in one file](declaration.md)).

## What it checks

The stages of the start, in the order of the start, each on what it can read without a data directory:

1. **read** — every file the declaration names is read: the declaration file `aouda.json` named by `Aouda:Declaration` and its overlay (**BL-1463, 0.16.0**; [the file](declaration.md)), the secret files and environment variables it points at (`keyRoot`, `previousKeyRoot`, the password seeds; **BL-1464, 0.16.0**), every schema file and its overlay. A file that cannot be read is one finding, not a crash.
2. **settings** — the process settings (`Aouda:Port`, the memory limits, `Aouda:NamedQuery:*`,...), the removed keys and the dev-admin guards. A removed setting is `SETTING_REMOVED`, naming its replacement: `Aouda:Databases` (a `databases` entry in `aouda.json`), and (**BL-1464, 0.16.0**) `Aouda:Auth:Keys:*`, `Aouda:Auth:RootUser`, `Aouda:Auth:Bootstrap` and the identities file (a principal and its credential in the declaration). A value a setting's type cannot hold is a `CONFIGURATION_INVALID` finding in every `Aouda:*` section the server binds, `Aouda:BulkLoad`, `Aouda:Streaming`, `Aouda:Adra:GrantCaps` and `Aouda:WebSocket:StreamingWrites` included (**BL-1504, 0.15.0**). An empty value counts as not set.
3. **principals** — the declared principals' names, `anonymous`'s members and the attributes (**BL-1464, 0.16.0**; [Declared access](declared-access.md)); the credentials' forms, the dev admin beside a credential declared in `server.principals` (`SERVER_KEY_DEV_ADMIN_CONFLICT`), and the conflicts between declared credentials (`KEY_ID_DUPLICATE`, the OIDC trusts).
4. **databases** — the `databases` of `aouda.json` (**BL-1463, 0.16.0**; before, `Aouda:Databases`, which is now refused as `SETTING_REMOVED`): names, kinds, links and per-kind fields.
5. **bootstrap** — an operator in `server.principals` (a principal holding `manage` on `server`, with a credential), or a data directory that starts in setup mode (`SETUP_MODE_EXPECTED` offline, `SERVER_HAS_NO_OPERATOR` against the data directory).
6. **schema** — every declared schema file, read with the server's own reader (a misspelt member is refused with its JSON pointer), the overlay merge, and the apply-time rules that need no tables.
7. **roles** — the declared access section's rules (**BL-1464, 0.16.0**): role names, which auth database governs what a statement names (`STATEMENT_NOT_GOVERNED`), public reach (`AUTH_PUBLIC_UNRESTRICTED`), and the tables, named queries and columns no declared schema has (warnings).
8. **principalRows** — against a running server: what the converge would write (principals, roles, `signup`; ownership conflicts, unknown roles, the emergency actions the file disagrees with) and their credentials.

Every stage runs on what it can check, so a broken schema file does not hide a duplicate key. Every finding has a **severity**, a stable **code** ([Declaration finding codes](../reference/plan-codes.md)),
a **location** (a file and a JSON pointer, or a setting and the configuration source that supplied it), a message and what to do. `error` is exactly a refusal of the start;
a `warning` is accepted and logged once; `info` is context.

## The command

`aouda plan` takes **the arguments `aouda start` takes**: the same `--Aouda:Section:Key=value` settings, `--declaration PATH` and `--env NAME` (**BL-1463, 0.16.0**: the two settings that name the declaration file and its environment, [Declare a server in one file](declaration.md)), `--port`, `--data-dir`, `--dev-admin`, the same environment variables
(`Aouda__Declaration` and the `AOUDA_` spelling), the `appsettings*.json` of the working directory, and `$CREDENTIALS_DIRECTORY` (where the removed `aouda-server-key` and `aouda-admin-password` credentials are refused, **BL-1464, 0.16.0**). There is no separate input to
learn and no `--` separator. Whatever you give `aouda start`, give `aouda plan`.

| Option | Meaning |
|---|---|
| `--skip-secrets` | Do not read secrets: check everything that does not need their content. See [below](#when-the-secrets-are-not-there). |
| `--json` | Print one JSON object instead of text. `--output json` does the same. |

Giving either a value (`--json=false`) is a usage error.

**A declaration too long for a command line (**BL-1586, 0.16.0**).** Every `aouda` command replaces an argument `@file` with the lines of that
file, one argument per line (blank lines and lines starting with `#` are skipped; a line is taken as written, so no quoting; a file's own `@`
lines are not expanded again; `@@x` is the text `@x`). A Windows command line through a shim is limited to 8191 characters, which a whole
declaration given as `--Aouda:…` settings exceeds:

```
# plan.args
--declaration C:\etc\aouda\aouda.json
--env prod
--skip-secrets
```

```powershell
aouda plan @plan.args --skip-secrets
```

A file that cannot be read is exit `64` naming it. Settings in `appsettings*.json` and the environment need none of this.

### Output

The whole plan goes to **standard output**, in both formats; standard error carries only a usage error.

```text
aouda plan: declaration /etc/aouda/aouda.json (environment prod), 13 databases, 11 schema files

error KEY_ID_DUPLICATE /etc/aouda/aouda.json /databases/app_auth/principals/two/credentials/keys/0
 Key aouda_aaaaaaaaaaaaaaaa is declared twice (also at /databases/app_auth/principals/one/credentials/keys/0): a key id is one credential of one principal.
 also: /etc/aouda/aouda.json /databases/app_auth/principals/one/credentials/keys/0
 fix: Give each principal its own key: a key id is one credential of one principal.

stages read ok, settings ok, principals 1 error, databases ok, bootstrap ok, schema ok, roles ok, principalRows ok
not checked the data directory and every existing database, table, key row and role (no --server)
 the environment the server will start in (hosting environment here: Production; variables an orchestrator sets at start)

1 error, 0 warnings: `aouda start` would refuse this declaration.
```

With `--json` the object has `format` (`aouda-plan/1`), `aoudaVersion`, `declaration` (the declaration file and its overlay, the environment — **`Aouda:Environment`, or `null`** since **BL-1463, 0.16.0**, not the host's environment —, the number of schema files and a `planHash`), `target`
(`{ "kind": "offline" }`), `outcome` (`clean` or `errors`), `summary`, `stages` (each `passed`, `warnings`, `failed` or `skipped`, with `skippedBecause` naming the code that blocked it),
`findings`, `changes` (always `null` offline) and `notChecked`. The same input gives the same bytes. A path that holds a key (a key pasted where a path belongs) is shown as `<redacted>`; a plan
never contains a key, a hash of one or the content of a secret file.

The `planHash` is the SHA-256 of the declaration with every secret replaced by its fingerprint: two plans of one declaration have one hash, **whichever directory the file is in** (a schema file's path is hashed as written in the declaration, its content as read; **BL-1463, 0.16.0**). A `--skip-secrets` plan hashes the references it did not
read, so its hash differs from a full plan's.

### Exit status

| Code | Outcome | Meaning |
|---|---|---|
| `0` | `clean` | no `error` finding: `aouda start` would not refuse this declaration (warnings and info never change the code) |
| `1` | `errors` | at least one `error` finding. When every error is a file that could not be read, the last line says the start "would fail here (a file could not be read) and may succeed once it can be" |
| `64` | — | misuse: a switch given a value, or `aouda keys check` / `aouda schema check`, which no longer exist |

There is no "could not check" status and no `--strict`: a warning that should block is an error the start should refuse. Exit codes `2`, `69` and `77` belong to plans against a running server (below), which an offline plan never exits with.

## Against a running server: `--server` (**BL-1463, 0.14.0**)

An offline plan cannot see the data directory. `--server` asks a **running** server what this declaration would change, before you deploy it:

```bash
aouda plan --server https://aouda.internal:5000 --key-file /run/secrets/aouda_server_key
```

The plan first reads the declaration and runs every offline check exactly as without `--server`. **If that finds an error, the server is not contacted**: the plan
exits `1` (errors win), says `target.contacted: false`, and sends nothing. Otherwise it sends the server a **candidate** (`POST /api/admin/reload?dryRun=true` with a
body, see the [HTTP API](../reference/http-api.md)), and the server runs the same validator as a reload's first phase over it — every offline check again under its own
settings, then every check that needs the data directory against a planned view — writes nothing, and answers with the plan. The plan you see is the local findings
(with their files and lines), the server's findings the local run could not make (the existing tables, key rows and roles), and any finding the server made that the
local run did not (a different named-query limit on the server, a version difference) — shown, never hidden. A `changes` block lists what a deploy of this declaration
would change, before the stages:

```text
aouda plan: declaration /etc/aouda/aouda.json, 3 databases, 2 schema files, against https://aouda.internal:5000

changes
 schema rates: 1 change (AddColumn SwapQuote.Venue)
a principal, its statements, and an aouda_ key or a session (GET /api/auth/whoami)

warning SCHEMA_DESTRUCTIVE_REFUSED /etc/aouda/bond.schema.json
 Database 'bond': schema file '/etc/aouda/bond.schema.json' differs from the catalog; refused (a reload never applies a destructive change): DropColumn BondQuote.LegacyId
 fix:...

stages read ok, settings ok, principals ok, databases ok, bootstrap ok, schema 1 warning, roles ok, principalRows ok
not checked...

no problems; 3 changes (see above).
```

In the JSON (`--json`), `target` is `{ "kind": "server", "url", "contacted", "role", "writes" }`, `changes` is the server's, `declaration.planHash` is the hash of what
the **server** planned and `declaration.localPlanHash` the plan's own (they differ when the two machines' settings differ: the server validates under its own).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
`--key-env NAME`, holding one key on one line (a line break, a space or a non-ASCII character is exit `64`, naming the file or the variable). There is no `--key`: a key on the command line stays in the shell's history and the process list, so `--key` is refused (exit `64`) without the value
being repeated. `--server` is never taken from `AOUDA_SERVER` / `AOUDA_URL`, and the key never from `AOUDA_TOKEN`: an environment left in a CI job must not turn an
offline plan into a call to a server. The key is sent only as the bearer to the URL you named — **a redirect is not followed** (it would be the easiest way to send a
server key elsewhere) — and is printed nowhere. The URL is an absolute `http://` or `https://` URL with no user name, query or fragment; there is no `--insecure`.

**What is sent, and what is not.** The candidate carries every declared database entry, the access section as written (`server` and each auth database's
`signup`, `roles` and `principals`, a stored key as the id and SHA-256 the file declares, a password seed as the marker `{ "seeded": true }` and nothing else — no reference, path or value; **BL-1464, 0.16.0**,), every
schema file as its **merged document** (the overlay applied where the plan ran), and the paths of the declaration and schema files as **labels** for the findings
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
is `400` (an unknown member). It never carries a key, a password, a secret file's content or path, or an environment variable's name. The server opens
no path the body names, re-reads none of its own configuration, and validates under its **own** process settings (named-query limits, `SkipDatabases`, the dev-admin
flag, the hosting environment), which a body cannot set. A key's hash is in every row of the auth database already; the bearer key is the more sensitive value either way:
**use `https`** anywhere beyond a private network.

**`--skip-secrets` against a server.** The candidate carries no secret either way, so the flag changes only the local checks: the key root and the password
seeds are not read, and the derived keys are not checked. A stored key's `id` and `sha256` are not secrets and are checked. Every other check still runs. The posted access section is checked against the file's own grammar, from its root: an unknown member, or a `databases` or root that is not an object, is refused (`400`), not dropped. A finding about a posted candidate stays located at `Aouda:Declaration`, with the pointer into the candidate in its message.

### Exit status against a server

| Code | Outcome | Meaning |
|---|---|---|
| `0` | `clean` | no error, and nothing to change |
| `1` | `errors` | an `error` finding — from the offline run (the server was not contacted) or from the server (its state, or its own settings) |
| `2` | `changes` | no error, and a deploy of this declaration would change something (listed under `changes`) |
| `64` | — | misuse: `--key`, no key source or both, `--key-file` / `--key-env` without `--server`, an unset variable, a missing or empty key file, a key source that holds more than one key on one line, a URL that is not plain `http(s)` |
| `69` | `incomplete` | the server could not be planned against: not reachable, a timeout, a TLS failure, a redirect, `404` (a server older than this release), `409` (a reload is running), `429` (one plan per second; `Retry-After` is printed), `503` (still starting), any other answer that is not a plan (`PLAN_TARGET_UNREACHABLE`) |
| `77` | `incomplete` | the server refused the key (`401` / `403`): `plan --server` needs that server's server key (`PLAN_TARGET_REFUSED`) |

An `incomplete` plan prints the offline plan it has and ends `incomplete: <reason>.`

**Before a deploy**, on the deploy host with the start's own mounts:

```bash
docker compose run --rm --no-deps --entrypoint aouda aouda plan --server http://aouda:5000 --key-file /run/secrets/aouda_server_key
case $? in 0) echo "nothing to change" ;; 2) echo "changes: review the plan above" ;; *) exit 1 ;; esac
```

The image listens on port **5000** (not 8080), and Docker Compose mounts a service's `secrets:` at **`/run/secrets/<secret name>`**, so `aouda_server_key` here is the name of the secret in your compose file. The key file must be mounted in the container that runs the plan, which a service that lists the secret under `secrets:` has. The URL names the service on the compose network (`aouda`); from the host use whatever address you publish, for example `http://127.0.0.1:5000`.

```bash
aouda plan --declaration deploy/aouda.json --skip-secrets \
 --server https://aouda.internal:5000 --key-env AOUDA_PLAN_KEY
```

**In CI**, see [A CI job](#a-ci-job-aouda-plan-on-every-pull-request) below: the operator key goes in as a separate CI secret.

## What `aouda plan` cannot know

A green plan is not more than it says. Every offline plan lists what it did not check under `notChecked`, and these are the limits:

1. **Without a target** (offline): anything in the data directory. Which databases exist and with which kind and link, the tables (so no schema diff and no destructive change), the key rows (a secret another row holds, an operator's revocation), roles created through the API, the data-directory format, whether `_serverauth` already has an admin.
2. **Secrets in another environment.** The plan reads `env` and `file` secrets where it runs. A CI runner with no secrets, or a host path that differs from the container's, makes those checks unknowable (`--skip-secrets`). The reliable gate is the plan run with the same mounts and environment as the start (`docker compose run --rm --no-deps --entrypoint aouda aouda plan`).
3. **The process environment at start.** Variables an orchestrator injects at start and that are absent where the plan ran.
4. **Apply failures that depend on row values,** even with a target, unless the engine's dry run checks them (a `NOT NULL` column on a table with rows, a `unique` flag on a column with duplicates, a narrowing type change). With `--server` (**BL-1463, 0.14.0**), the engine's dry run checks what needs no rows: a destructive change (reported as `SCHEMA_DESTRUCTIVE_REFUSED`, never applied by a reload), a changed partition key, a table left with no column, an added identity column without `nullable` or a static default, an added server-time or array column that is not nullable, and the apply's own authorization. It does **not** check what depends on the rows or on another executor's rules (a non-nullable column without a default added to a table with rows, a `unique` flag over duplicates, a narrowing type change, and other refusals only the apply makes): a plan can say valid where the apply then refuses (tracked as BL-1494).
5. **Resources and the host:** free ports, memory, disk, file permissions for the server's user (the plan may run as another user), the clock, whether the email or SMS provider answers.
6. **A node's replication role:** whether a follower would write is not planned.
7. **Races:** anything that changes between the plan and the start or reload. `planHash` shows which declaration was planned; it is not a lock.
8. **How long the start will take:** not estimated.

One consequence worth stating: a data directory that has been set up and has nobody who can manage the server refuses to start with `SERVER_HAS_NO_OPERATOR`. An offline plan cannot see the
data directory, so for a declaration that declares no first administrator it exits `0` with the warning `SETUP_MODE_EXPECTED`. That is the one place the start refuses for a reason a plan cannot see.

## When the secrets are not there

A CI runner usually has the declaration and the schema files (they are in the repository) but not the secrets they point at. `--skip-secrets` checks everything that does not need their content:

```bash
aouda plan --declaration deploy/aouda.json --skip-secrets
```

With the flag (**BL-1464, 0.16.0**), **nothing secret is read or looked for**: not the `keyRoot` or `previousKeyRoot`, not a password seed's `file` or `env`, no systemd credential (so whether a
credential exists is unknown). Still read: the configuration, the declaration file and its overlay, every schema file and overlay. Still checked, from form alone: a literal key root
(`SECRET_BY_VALUE`), a stored key's `id` and `sha256` (`KEY_DECLARATION_INVALID`, `KEY_ID_DUPLICATE`), a password seed on a principal not named by an email, and every name, role and statement rule
that does not touch a secret. What cannot be checked is skipped: an unreadable secret, a key root too short (`KEY_ROOT_INVALID`), and the derived keys.

The plan says what it skipped: one `info` finding, `SECRET_NOT_READ`, per reference it did not read, at its JSON pointer (`/keyRoot`, a principal's `credentials/password`; never a value), and
`notChecked` gives their count (`the contents of 2 secret references (--skip-secrets)`).

**A `keyRoot` `{ "file" }` path is the path inside the container, not on the runner.** `--skip-secrets` is how CI checks the declaration without that file. The root is never an argument.

## Recipes

**CI, before a deploy** — the declaration and the schema files are in the repository, the secrets are not:

```bash
aouda plan --declaration deploy/aouda.json --env prod --skip-secrets
```

**On the deploy host, with the start's own mounts** — the strongest offline gate, because it reads what the start will read:

```bash
docker compose run --rm --no-deps --entrypoint aouda aouda plan
```

(The image's entrypoint is `aouda start`, hence `--entrypoint aouda` for any other command.)

**A schema file that is declared nowhere else** is checked by declaring it to the plan, as above (`databases.<name>.schema` in `aouda.json`, and `--env` to merge its overlay; **BL-1463, 0.16.0**; before, `Aouda:Databases:<name>:SchemaFile` and `SchemaEnvironment`, which are refused now). A schema that is applied through
the API instead of declared is checked against a server with `aouda schema diff`.

## From a running server to a file: the export (**BL-1463, 0.16.0**)

A setup clicked together in Studio, or made through the API, becomes the file a deployment owns without re-typing it:
`GET /api/admin/declaration/export` (an operator's key) answers `{ "declaration", "schemaFiles", "origins", "notes" }`. Write
`declaration` as `aouda.json` and each `schemaFiles` entry at its relative path beside it, then plan the files:

```sh
curl -s -H "Authorization: Bearer $AOUDA_KEY" http://localhost:5000/api/admin/declaration/export > export.json
jq -r '.declaration' export.json > deploy/aouda.json
jq -r '.schemaFiles | to_entries | "\(.key)\t\(.value)"' export.json | while IFS=$'\t' read -r path text; do
 mkdir -p "deploy/$(dirname "$path")"; printf '%s' "$text" > "deploy/$path"; done
aouda plan --declaration deploy/aouda.json
```

The export is the server's whole state, declared and runtime — databases with their non-default fields, each data database's live
schema, roles, principals (stored keys as `{ "id", "sha256" }`, derived keys by version, OIDC trusts) — and `origins` says which part
the running declaration already declares. **It never carries a password or a key root**: `notes` names what was left out (passwords, a
revoked, limited or expiring key, self-signed-up principals) and what to add (`EXPORT_KEY_ROOT_NEEDED`: a `keyRoot` for derived keys).
Planned against the **same** server, databases, schemas and declared objects have no changes, but each principal or role made at runtime
is `PRINCIPAL_RUNTIME_CONFLICT` / `ROLE_RUNTIME_CONFLICT` — a declaration never adopts a runtime object of the same name — so start the
new deployment from the files (or delete the runtime objects on this server and reload). From then on the file is the one writer of what
it declares: the API refuses changes to it with `409 DECLARED_IN_CONFIGURATION` ([Declared databases](declared-databases.md)).
`GET /api/admin/declaration` shows the declaration a server runs on, with the findings of its last start or reload
([HTTP API](../reference/http-api.md#one-writer-per-declared-object)).

## A CI job: `aouda plan` on every pull request

What the job needs, each of which a first attempt gets wrong:

1. **The CLI, at the server's version.** `aouda plan` runs the checks of the version it is, so a CLI older or newer than the server you deploy plans a different declaration (a member one version refuses, the other drops). Install the version you deploy: `dotnet tool install -g Aouda.Cli --version <the server version>`, on a runner with the **.NET 10 SDK** (`Aouda.Cli` 0.2.0 and later). The package comes from the NuGet feed your pipeline already restores `Aouda.*` from (the same one as `Aouda.Client`); add `--add-source <feed>` or a committed `nuget.config` when it is not nuget.org. Without a CLI on the runner, the server image is the same code at the same version: `docker run --rm --entrypoint aouda ghcr.io/aoudadb/aouda-server:<version> plan...`, which needs a login first (below).
2. **A private registry login, if you use the image.** The image is private ([Docker](../deployment/docker.md)): `echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin` with a token that has `read:packages`, kept as a CI secret.
3. **The declaration file.** `aouda plan` reads the file `--declaration` names (`Aouda:Declaration`). Commit `deploy/aouda.json` — the databases, the schema paths, the roles and the principals — and plan that file. `Aouda:Databases` and an identities file are refused (`SETTING_REMOVED`).
4. **No secrets on the runner**, so `--skip-secrets`. An offline plan then checks form, names, conflicts and every schema file, not the content of a `keyRoot` or a password seed.
5. **The operator key is its own CI secret**, only for `--server`. It is a key of the server you plan against (a principal with `manage` on `server`), not a key from your declaration: give it through `--key-env` (a variable the step sets from the secret), never as an argument.

```yaml
name: aouda-plan
on: [pull_request]

jobs:
 plan:
 runs-on: ubuntu-latest
 steps:
 - uses: actions/checkout@v4

 - uses: actions/setup-dotnet@v4
 with:
 dotnet-version: "10.x"

 - name: Install the CLI at the server's version
 run: dotnet tool install -g Aouda.Cli --version "${{ vars.AOUDA_VERSION }}"

 - name: Plan offline (no secrets, no server)
 run: aouda plan --declaration deploy/aouda.json --skip-secrets

 - name: Plan against the running server
 env:
 AOUDA_PLAN_KEY: ${{ secrets.AOUDA_STAGING_KEY }}
 run: |
 code=0
 aouda plan --declaration deploy/aouda.json --skip-secrets --server "${{ vars.AOUDA_STAGING_URL }}" --key-env AOUDA_PLAN_KEY || code=$?
 # 0 nothing to change, 2 changes to review; anything else fails the job (1 errors, 64 misuse, 69 unreachable, 77 key refused)
 if [ "$code" -ne 0 ] && [ "$code" -ne 2 ]; then exit "$code"; fi
```

The same job with the image, for a runner that has Docker and no.NET:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
docker run --rm --entrypoint aouda -v "$PWD/deploy:/deploy:ro" \
 ghcr.io/aoudadb/aouda-server:"$AOUDA_VERSION" plan --skip-secrets \
 --declaration /deploy/aouda.json
```

## Replacing `aouda keys check` and `aouda schema check`

`aouda keys check` and `aouda schema check` are deleted — no alias, no "did you mean": they are unknown subcommands and exit `64`. The key commands are `aouda keys new`, `aouda keys new-root` and `aouda keys derive` ([CLI](../reference/cli.md)). `aouda schema validate`, `diff`, `apply` and `export` stay.

| Before | Now |
|---|---|
| `aouda keys check -- --dev-admin` | `aouda plan --dev-admin` (no separator) |
| `aouda schema check --file F --env E` | a declaration file with `{ "version": 1, "databases": { "app": { "kind": "data", "schema": "F" } } }`, then `aouda plan --declaration aouda.json --env E` (**BL-1463, 0.16.0**; in 0.14.0 it was `aouda plan --Aouda:Databases:app:Kind=data --Aouda:Databases:app:SchemaFile=F --Aouda:Databases:app:SchemaEnvironment=E`, which is refused now) |
| `aouda schema check` for a schema that is not declared | `aouda schema diff` against a server |
| exit `2` from either command | exit `1` (or `64` for misuse); `2` no longer means "could not check" |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

The `schema check` page's two lessons still hold. **`plan` and `schema validate` are different:** `plan` asks whether the declaration is acceptable on its own, with no server; `schema validate` asks whether
a live database matches a file (drift), and needs one. And **the start runs the same checks:** a declared database's schema file is checked before the start changes any database, with that server's own
named-query ceilings, so a file the plan passes cannot fail the start for a reason that sits in the document alone.

## See also

- [Declaration finding codes](../reference/plan-codes.md): every code, its stage and its remedy.
- [Keys that survive a wipe](keys-that-survive-a-wipe.md) and [Declared databases](declared-databases.md): what is declared.
- [Schema CI/CD](schema-cicd.md) and [Schema management](schema-management.md).
