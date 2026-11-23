---
title: "CLI"
nav_order: 3
parent: "Reference"
---

# CLI (**BL-1464, 0.16.0**)

`aouda` is the server and the admin tool. `aouda --help` lists the commands below. An argument `@file` is replaced by the lines of that file. No option takes a secret: a key, a key root or an identity token is a file or an environment variable, never an argument. A refusal names the variable or the path, never the value. Nothing here prints a key root or a hash of a key except `keys new`, which prints the hash you put in the declaration.

Exit `64` is misuse on every command (unknown command, unknown flag, a missing required argument).

## `start`

`aouda start` runs the server in the foreground.

| Flag | Meaning |
|---|---|
| `--port` | Listen port. Code default `5000`. |
| `--data-dir` | Data directory. |
| `--declaration` | `aouda.json`. Also `AOUDA_DECLARATION` and `Aouda:Declaration`. |
| `--env` | Overlay `aouda.<env>.json`. Also `AOUDA_ENVIRONMENT`. |
| `--dev-admin` | Development only. Prints one line, `AOUDA-DEV-ADMIN email=… password=… key=…`. |

A start the declaration refuses exits `78`, or `1` when every error is a file that could not be read yet. A second start on a directory another process holds exits `1`.

## `plan`

`aouda plan` reads what `start` would read and reports every problem. It writes nothing.

| Exit | Meaning |
|---|---|
| `0` | Start would not refuse. |
| `1` | Start would refuse. |
| `2` | With `--server` or `--data-dir`: a reload or a start would change something. |
| `64` | Misuse. |
| `69` | The server could not be planned against, or the data directory is unreadable, held by another process, or needs a start to recover it. |
| `77` | With `--server`: the key was refused. |

| Flag | Meaning |
|---|---|
| `--skip-secrets` | Do not read secret files or variables. |
| `--server URL` | Also ask that server (`POST /api/admin/reload?dryRun=true`). Needs `--key-file` or `--key-env`: the operator's key. |
| `--data-dir PATH` | Plan against a stopped data directory. Probes the lock and creates nothing. Rows and runtime principals need `--server`. |
| `--json` | Machine-readable output. |

`--key` is not a flag. The key is never printed.

## `reload`

`aouda reload` asks a running server to re-read its declaration and converge it. Exit `0` nothing to change, `2` applied, `1` refused or partial. The key is `--key-file` or `--key-env`.

## `keys`

Offline. Nothing is stored or sent.

### `keys new`

Prints a stored key once and the declaration line `{ "id", "sha256" }`.

| Flag | Meaning |
|---|---|
| `--key-file PATH` | Write the key to a new file, mode `0600`, never overwritten, and not to a stream. |
| `--json` | `{ "key", "id", "sha256", "declaration" }` when the key is printed. |

Exit `0`, `1` (the file cannot be created), `64`.

### `keys new-root`

32 random bytes, base64url, 43 characters. Declare it as `keyRoot: { "env": "NAME" }` or `{ "file": "PATH" }`, never by value.

| Flag | Meaning |
|---|---|
| `--root-file PATH` | Write the root to a new `0600` file instead of printing it. |
| `--json` | Machine-readable output. |

Exit `0`, `1`, `64`. The root is not a key and is not a hash.

### `keys derive <authDatabase>/<name>`

The derived key of a declared principal, from the root the server reads.

| Flag | Meaning |
|---|---|
| `--declaration PATH` | `aouda.json`. The principal must declare `derivedKey`. The version is the declared one. |
| `--env NAME` | Overlay. |
| `--version N` | Required when there is no declaration. With a declaration it must be the declared version. |
| `--root-env NAME` / `--root-file PATH` | The root. Otherwise the declaration's `keyRoot`. |
| `--previous` | Use `previousKeyRoot`. |
| `--key-file PATH` | Write the key to a new `0600` file. |
| `--json` | Machine-readable output. |

Exit `0`, `1` (undeclared principal or version, no root, a root that does not read), `64`.

## `whoami`

`aouda whoami` calls `GET /api/auth/whoami`.

| Flag | Meaning |
|---|---|
| `--server URL` | Also `AOUDA_SERVER` / `AOUDA_URL`. |
| `--database NAME` | Only that database's statements. With no credential on the data plane, that database's `anonymous`. |
| `--token TOKEN` | A key or a session. Also `AOUDA_TOKEN`. Prefer a file mode the shell does not keep; the flag exists and the value is not echoed on failure. |
| `--json` | The server's body, unchanged. |

Exit `0`, `77` (the credential was refused: the code, message and remedy are printed), `69` (unreachable or `5xx`), `1`, `64`. A body that is not the refusal payload is not echoed.

## `login --oidc`

Exchanges an identity token for a session. `aouda login --oidc` is the only login.

| Flag | Meaning |
|---|---|
| `--server URL` | Required. |
| `--id-token-env NAME` | The variable holding the identity token. |
| `--id-token-file PATH` | A file, for example a projected service-account token. |
| `--id-token-stdin` | Read the token from stdin. |
| `--json` | `{ "accessToken", "expiresAt", "principal" }`. |

Text output prints the access token alone on stdout and `expires` / `principal` on stderr. The command stores nothing. A value that is itself a key is refused before any request. `--id-token <value>` is not a flag.

Exit `0`, `77`, `69`, `1`, `64`.

**GitHub Actions.** The job's `id-token: write` permission, then:

```text
aouda login --oidc --server "$AOUDA_URL" --id-token-env ACTIONS_ID_TOKEN_REQUEST_TOKEN
```

The trust on the principal is `issuer: https://token.actions.githubusercontent.com`, `audience` the audience the workflow requested, `subject` the `repo:owner/name:ref:…` string. The workflow fetches the token into the variable the flag names; the command never sees it as an argument.

**Kubernetes.** Project the service-account token and:

```text
aouda login --oidc --server "$AOUDA_URL" --id-token-file /var/run/secrets/tokens/aouda
```

The trust's `issuer` is the cluster's, `subject` is `system:serviceaccount:<namespace>:<name>`. An issuer the server cannot fetch uses `jwks.file` in the declaration.

## `policy explain`

Offline, from `aouda.json` only. It runs `plan`'s checks first and explains nothing when they refuse.

| Flag | Meaning |
|---|---|
| `--declaration PATH` | Required in practice. Also `AOUDA_DECLARATION`. |
| `--env NAME` | Overlays. |
| `--as <auth>/<name>` | A declared principal, or `<auth>/anonymous`. |
| `--as-signup <auth>` | Instead of `--as`: a principal that signs up there. |
| `--action` | `read`, `write`, `delete`, `execute`, `set-identity`, `manage`. |
| `--resource` | One resource: `<db>/table/<name>`, `<db>/query/<name>`, `<db>/mutation/<name>`, `<db>`, `server`, `<auth>/principal/<name>`, `<auth>/role/<name>`. |
| `--row JSON` | With `read`, `write` or `delete`: one row. |
| `--json` | The answer object. |

| Exit | Meaning |
|---|---|
| `0` | Allowed. With `--row`, the row is admitted. |
| `2` | The policy refuses. The answer is printed. |
| `1` | The declaration is refused, or the principal or resource is not in it, or the principal is declared `"disabled": true`. |
| `64` | Misuse: unknown action, a wildcard resource, an action the resource does not take, `--row` with `execute`, `set-identity` or `manage`, both or neither of `--as` / `--as-signup`. |

It does not know a runtime principal (it names `aouda whoami` and `aouda plan --server`), a credential's limit, or a clock other than now. `--json` includes `principal`, `action`, `resource`, `allowed`, `decidedBy`, and when the target has rows `rows` (`none`, `all`, `filter`, `unresolved`). `row` is present only with `--row`. A refusal includes `remedy`.

## `schema`

`schema diff`, `apply`, `export`, `validate`, `history`, `seed`, under `schema`. `validate` needs a running server (exit `0` in sync, `1` drift, `2` error). A check with no server is `plan`. `schema diff --access` is not a flag.

## `init`

`aouda init` talks to a running server in setup mode and creates the first operator (`POST /api/auth/setup`). The password is read from stdin.

## `backup` `aouda backup` takes, lists, shows, restores and prunes the server's backup sets and reads or sets the retention policy. It
calls the admin API ([HTTP API](http-api.md#backup-and-restore-admin-routes)) with an operator key; `restore --to` needs no server. Concepts:
[Backup and restore](../guides/backup.md).

| Exit | Meaning |
|---|---|
| `0` | Done. |
| `1` | Refused or failed (the server's code and its `remedy` are printed). |
| `64` | Misuse. |
| `69` | The server is unreachable, or answered 5xx. |
| `77` | The key was refused. |
| `78` | With `restore --to`: the directory is not empty or is in use. |

Every verb takes `-s, --server <url>` (default `AOUDA_SERVER` / `AOUDA_URL`), `-t, --token <key>` (default `AOUDA_TOKEN`; prefer the variable, an argument shows in the process list), `--json`, and
`--timeout <duration>` (`7d`, `12h`, `30m`, `90s`; default 1 hour for `create`, `restore` and `prune`, 30 seconds otherwise).

| Verb | What it does |
|---|---|
| `backup create [--full]` | Back up every database as one set (auth databases first); the set record written last commits it. Incremental against the newest set unless `--full`. |
| `backup list` | The sets: `ID CREATED COMPLETE PITR BYTES DATABASES`. |
| `backup show <id>` | One set: `complete`, the times, and per database its cut, WAL position, redo-start, manifest version, point-in-time eligibility, files, bytes and branches. |
| `backup restore [<id>] [--target-time <instant>]` | Restore the set exactly, or to the last commit at or before the ISO 8601 instant (UTC when it has no offset). Without `<id>`, the newest complete set at or before `--target-time`. The server's engines stop for the restore. |
| `backup restore <id> --to <dir> --from <destination>` | Restore into a new or empty data directory with **no server running**; start it with `aouda start --data-path <dir>`. `--from` is a path or `s3://bucket/prefix` (AWS credential chain). |
| `backup prune [--dry-run]` | Apply the retention policy: prints each set, kept (with the rules that kept it) or deleted, then carries it out. `--dry-run` deletes nothing. With no policy saved: exit 1, `BACKUP_RETENTION_INVALID`. |
| `backup retention [--keep-last N] [--keep-days N] [--pitr-window <duration>]` | Show the policy, or set it. Setting saves the **whole** policy: a term not given is not kept. No policy means nothing is pruned. |

`restore --to` also takes `--archive <destination>` (with `--target-time`: the WAL archive's destination when it is not `--from`),
`--s3-endpoint <url>` (an S3-compatible endpoint, path-style) and `--s3-region <region>`.

A restore checks every blob against its key as it reads it: a blob that does not match refuses it with `BACKUP_BLOB_DAMAGED` (exit 1),
naming the file and the set, and `verified yes` on a restore that completed means every blob matched. With
`--target-time`, every database's archive window is checked before anything is written: `PITR_WINDOW_UNAVAILABLE` leaves `--to` as it was. A restore that stops part-way leaves the database it stopped in refusing to open (`RESTORE_INCOMPLETE`) — delete
the directory and restore again.

```text
$ aouda backup list
ID CREATED COMPLETE PITR BYTES DATABASES
backup-2026-11-21-150851-4bccdc05 2026-11-21T15:08:51.8031954+00:00 yes yes 87867 _serverauth, _settings, shop

$ aouda backup restore backup-2026-11-21-150851-4bccdc05 --target-time 2026-11-21T15:09:01Z
restored backup set backup-2026-11-21-150851-4bccdc05 to 2026-11-21T15:09:01+00:00
files 53 (87867 bytes read)
verified yes
pitr _serverauth: 11 transactions, 13 rows replayed, last commit 2026-11-21T15:08:46.8577356+00:00
pitr _settings: 0 transactions, 0 rows replayed
pitr shop: 3 transactions, 3 rows replayed, last commit 2026-11-21T15:08:52.6389213+00:00

$ aouda backup restore backup-2026-11-21-150851-4bccdc05 --target-time 2026-11-21T15:09:01Z --to /srv/aouda-data --from /backups/aouda
restored backup set backup-2026-11-21-150851-4bccdc05 into /srv/aouda-data, staged to 2026-11-21T15:09:01.0000000+00:00 (replayed when the directory is first started)
files 53 (87867 bytes read)
verified yes
database _serverauth (Strict, auth)
database _settings (Strict)
database shop (Strict)
start it with: aouda start --data-path /srv/aouda-data
```

## `dump` `aouda dump` writes a server's data databases to a directory in a format that no data-directory format version
touches; [`aouda load`](#load) reads it. A dump is **not a backup** and holds secret-class values: [Dump and load](../guides/dump-load.md).

| Exit | Meaning |
|---|---|
| `0` | The dump is complete. |
| `1` | Refused or failed; the directory has no `dump.json`, so `load` refuses it. |
| `64` | Misuse. |
| `69` | The server is unreachable, or failing. |
| `77` | The key was refused. |

| Flag | Meaning |
|---|---|
| `-s, --server URL` | The server. Default `AOUDA_SERVER`, then `AOUDA_URL`. |
| `--key-file FILE` / `--key-env NAME` | An operator key from a file or an environment variable. `--key` is not a flag. |
| `-o, --out DIR` | The directory to write: new, or empty. |
| `--database NAME` | Dump only this database (repeatable). Default: every data database. |
| `--tables DB.TABLE,…` | Dump only these tables (repeatable). |
| `--allow-writes` | Finish a dump whose database was written while it was dumped (recorded as not consistent). |
| `--json` | Machine-readable output. |

## `load` `aouda load` loads a directory `aouda dump` wrote into a server of this or another version: databases, schema, rows
(each table verified by row count and digest), materialized queries, then the dump's declaration planned against the server. Run it again to resume:
a table already loaded is skipped. Exit `0` done, `2` done with the declaration left to adopt, `1` refused or failed, `64` misuse, `69` unreachable, `77` the key
refused (and a table with a stamp column needs the server operator's key, `LOAD_RESTORE_REQUIRES_OPERATOR`). When the data is loaded and only the
declaration's plan fails, `load` ends with the plan's own status (`1`, `69` or `77`) after the line `the data is loaded; …`: read that line before
concluding nothing was written.

| Flag | Meaning |
|---|---|
| `-s, --server URL`, `--key-file`, `--key-env` | As for `dump`. |
| `-i, --in DIR` | The directory `aouda dump` wrote. |
| `--database NAME`, `--tables DB.TABLE,…` | Load only these (repeatable). |
| `--no-verify` | Skip the re-read of each loaded table. |
| `--mq-timeout DURATION` | How long the materialized queries may take to be `Ready`. Default 30 minutes. |
| `--no-declaration` | Do not plan the dump's declaration against the server. |
| `--json` | Machine-readable output. |

## Other commands

| Command | What it does |
|---|---|
| `stop` | Stop the local server recorded in the state directory. |
| `status` | Is it running, where, which version, what memory budget. |
| `doctor` | Findings for an install that will not start. |
| `service install` / `uninstall` | Register with systemd or the Windows service manager. The data directory is not touched on uninstall. |
| `databases` (`db`) | `list`, `get`, `create`, `drop`, `quarantine`, `unquarantine`, `inspect`. |
| `table backfill` | Offline backfill. Takes the data-directory lock. |
| `table bulk-load` | Load one table from JSONL. |
| `bulk-load` | Load several tables from JSONL, one commit. |
| `mq refresh` | Refresh a materialized query. |
| `budget get` / `set` | The process memory budget. |
| `generate <language>` | Client bindings from a schema file, with pinned named-artifact hashes. |

The first operator is `init`, the declaration, or `--dev-admin`.

## A deploy, in order

```text
aouda keys new-root --root-file key-root.txt
aouda keys derive auth/rates-feeder --declaration aouda.json --root-file key-root.txt --key-file rates-feeder.key
aouda plan --declaration aouda.json
aouda start --declaration aouda.json
aouda whoami --server http://127.0.0.1:5000 --token-file is not a flag; pass the key by AOUDA_TOKEN
aouda policy explain --declaration aouda.json --as auth/rates-feeder --action write --resource rates/table/DepositQuote --row "{\"source\":\"other\"}"
```

The explain exits `2` when that row is outside the feeder's `where`. A live write of the same row is `403 AUTH_ROW_DENIED`.
