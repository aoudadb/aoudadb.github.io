---
title: "CLI"
nav_order: 3
parent: "Reference"
---

# CLI (**BL-1464, next train**)

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
