---
title: "Docker"
nav_order: 5
parent: "Deployment"
---

# Running Aouda in Docker

A single-node Aouda server in a container, with the two limits that decide whether it behaves under load.

---

## ⚠️ The image is private

Aouda's server image is published to **`ghcr.io/aoudadb/aouda-server`**, and the repository it is built from is private — so **the image is private too**. There is no anonymous `docker pull`.

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin
docker pull ghcr.io/aoudadb/aouda-server:<version>
```

You need a token with `read:packages` on the `aoudadb` organisation.

> **If you have seen `image: aouda/server` in older documentation, that image does not exist.** It was never published under that name, and any compose file or chart still naming it will fail to pull.

---

## Run it

```bash
docker run -d --name aouda \
  -m 2g --cpus 4 \
  -p 127.0.0.1:5000:5000 \
  -v aouda-data:/data \
  ghcr.io/aoudadb/aouda-server:<version>
```

The image's entry point is `dotnet Aouda.Server.dll start`, the data directory is `/data`, and it listens on port 5000.

**The server in the image is precompiled (ReadyToRun)** (**Lead S06, 0.6.0**). A fresh container starts and answers its first
queries with code compiled at build time instead of compiling it on the way: on the project's 4-core test machine, a restart is ready
in ~2.2 s instead of ~2.7 and answers its first aggregate ~1 s sooner, and a first query of a kind takes a third less (an
aggregate over 1 M rows: 0.26 s instead of 0.41). Hot code is still recompiled by the runtime as it runs, so steady query speed does not change. The image is ~30 MB larger (250 MB unpacked).
Nothing to configure. The image is still `linux/amd64` on `aspnet:10.0-alpine`, with the runtime in its base layer.

⚠️ **Mounting somewhere other than `/data`?** Override the data path with **one** setting — `AOUDA_DATA_PATH` (the env var this image already sets), `Aouda__DataPath`, or `--data-dir`/`--data-path`/`-d` on the command line. All five are the same setting under the hood; setting more than one is redundant, not additive. There is no `AOUDA_DATA` (without `_PATH`) — that name is not read, and a container relying on it silently falls back to the built-in `/data` default, which then fails to create `{path}/Server` if nothing is actually mounted or writable there.

⚠️ **The container's user is uid/gid 1654** (matching `$APP_UID`, the uid Microsoft's aspnet images standardize on since .NET 8). A bind-mounted host directory must be `chown`ed to `1654:1654` — or writable by it — before the container starts, or directory creation under the data path fails and the process exits immediately. A named volume (as in the example above) does not have this problem: Docker initializes it from the image's own ownership on first use.

⚠️ **`-p 127.0.0.1:5000:5000`, not `-p 5000:5000`.** The second form publishes the admin API on every interface of the host, which is almost never what you want for a server whose first user was created a minute ago. Put a reverse proxy in front and read [Behind a reverse proxy](reverse-proxy.md).

---

## `-m` is the single most valuable flag in that command

**Not because it caps memory — because it changes how Aouda sizes itself.**

A container memory limit creates a cgroup boundary, and Aouda takes:

| What Aouda finds | Budget it takes |
|---|---|
| A cgroup limit — an explicit grant | **70 %** of the limit |
| No cgroup limit; it can only see the host's RAM | **40 %** of that |

The fallback is conservative on purpose: a host's total memory says nothing about how much of it this container owns.

⚠️ **Without a limit this is what happens, and it is not hypothetical.** On 2026-09-11 a 7.6 GB host running 29 containers gave Aouda a 3.04 GiB budget derived from the *host's* memory. Aouda bound that to the CLR as a GC heap hard limit and filled it, while the host had under 200 MB free. Every allocation then failed — bulk-load append and commit, compaction, unrelated read queries, and finally the connection-accept loop — after which the process was alive and permanently unreachable.

With a limit, Aouda derives 70 % of a number nobody else can spend, and sheds load with `503` and `Retry-After` instead of dying.

| Runtime | How |
|---|---|
| `docker run` | `-m 2g` |
| Compose v2 | `mem_limit: 2g` |
| Compose v3 | `deploy.resources.limits.memory: 2g` |
| Kubernetes | `resources.limits.memory: 2Gi` — ⚠️ a pod without one has exactly the same problem |

**Check it took.** The startup log prints its own derivation:

```
Memory budget derivation: detected=… available=… source=… cgroupBounded=… governed=…
```

`cgroupBounded=false` means the limit did not take effect.

---

## `--cpus` matters for the same reason

Aouda sizes every scan's parallelism — and the runtime sizes its GC heap count — from the cores they believe they have.

⚠️ **A CPU *share* or *weight* is not a limit.** `--cpu-shares`, or Kubernetes `resources.requests` without `limits`, is a relative claim against siblings and carries no absolute core count, so the kernel exposes no quota and `Environment.ProcessorCount` reports the **node's** cores. On a 64-core node, a container promised a tenth of the machine will still try to scan 64 ways.

Where a quota is genuinely impossible, set `AOUDA__CPU__CONFIGUREDCORES` instead. The startup log's `CPU budget derivation` line says which of the three it used.

---

## Shutdown grace

`Aouda:ShutdownTimeout` defaults to **120 s**, and the orchestrator's grace period must be **greater** than that plus a margin — the reference compose files use **130 s**.

⚠️ A 10 s grace against a 120 s host timeout is how a `SIGKILL` lands in the middle of a shutdown. See [Server configuration §8](../guides/server-configuration.md#8-startup-shutdown-and-slow-opens).

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
    environment:
      AOUDA_DATA_PATH: /data
      AOUDA_SHUTDOWNTIMEOUT: "00:02:00"
volumes:
  aouda-data:
```

---

## Health checks

Use **`/ready`**, not `/health`.

⚠️ `/health` answers `200` whenever the process is running — **including while every write is failing**. `/ready` checks the components that make the node usable, which since P48 includes the memory check. A probe pointed at `/health` reports a wedged server as healthy, which is precisely the failure mode described above.

The image ships a healthcheck already:

```
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=6
  CMD wget -qO- http://localhost:5000/ready || exit 1
```

⚠️ **`--start-period=60s` is doing real work**: WAL recovery on a large database can legitimately take minutes, and a probe that starts immediately will kill a server that is recovering correctly.

**Which probe for what** (**BL-1462, 0.14.0**; the full table is in the [HTTP API reference](../reference/http-api.md#the-probes-one-meaning-each)):

| Probe | Answers | `200` when |
|---|---|---|
| `/health` | Is the process alive? | Always, to every caller, setup mode included |
| `/startup` | Has the start sequence finished? | Databases open, auth, declared schema files, roles, grants and keys done; setup mode included |
| `/ready` | Can it serve application traffic? | Started, not in setup mode, nothing missing, not shutting down |

**Compose `depends_on`.** `condition: service_healthy` waits for the healthcheck, and the healthcheck is `/ready`, so a dependent
service starts once the server can serve it. That is what the repository's `docker-compose.yml` does for Studio. A service that
must start while the server is still in setup mode (one that creates the first admin) uses `condition: service_started` and polls
`/startup` itself.

⚠️ **A new container with nothing declared is `unhealthy` until it has a first admin.** A server whose data volume has never been
set up, with no declared server key or first admin, is in setup mode and serves no application traffic, so `/ready` answers `503` and lists the reason `setup_required` (since
0.11.0, BL-1393). That is the probe telling the truth, not a fault. `/health` and `/startup` answer `200` meanwhile (**BL-1462,
0.14.0**). Anything that waits on the healthcheck (`depends_on: condition: service_healthy`, a deploy gate) waits for setup
too.

To see why, read the body from outside the container: `curl -s http://localhost:5000/ready` (`/ready` needs no credential). The image's own `wget` does not print the body of a `503`, so `docker exec aouda wget -qO- http://localhost:5000/ready` shows nothing.

### Setup mode only when nothing is declared

(**BL-1462, 0.14.0**) Declare how the server is operated and it starts ready. Setup mode, the interactive first run, exists
only for a data volume that has **never been set up** (no server auth database) and a server that declares none of these:

| You declare | What happens at start |
|---|---|
| A server key: `AOUDA_AUTH__BOOTSTRAP__SERVERKEY`, `AOUDA_AUTH__BOOTSTRAP__SERVERKEYFILE`, the systemd credential `aouda-server-key`, or a `server_admin` entry in the identities file | No setup mode. The server auth database is created with **no user**, and the key operates the server from the first start: create databases, keys and users with it. No human admin is needed |
| A first admin: `AOUDA_AUTH__ROOTUSER__EMAIL` and `AOUDA_AUTH__ROOTUSER__PASSWORD` (or the systemd credential `aouda-admin-password`) | The admin is created once; no setup mode. An email with no password is listed by `/ready` as `root_user_unusable` |
| `AOUDA_DEV_ADMIN=true` | Development and tests only: a throwaway admin and server key, printed once. See [Development admin](../guides/development-admin.md) |
| none of them, on a new volume | **Setup mode**: `/startup` 200, `/ready` 503 `setup_required`, every other route `503 SETUP_REQUIRED` off the server's host |
| none of them, on a volume set up before that still has a user or an active server key (minted or once declared) | Starts normally, operated by them. **Never setup mode again**: a set-up server back in setup mode could be claimed by any loopback caller |
| none of them, on a volume set up before that has no user and no active server key (a restore, every key revoked) | **The start is refused**: `SERVER_HAS_NO_OPERATOR: this data directory has been set up before ...`, naming the ways out (declare a server key, set `RootUser`, or `--dev-admin` for development). Declare one and restart |
| none of them, on a volume that already holds an admin | Starts normally |

Before this, a declared server key did **not** end setup mode: it was inert until a human created an admin, so a fully
declarative deployment still needed an admin password, and a compose file gated on `/ready` sat in setup mode after a wipe.

### Compose

(**BL-1407, 0.12.0**; **BL-1423, 0.12.0**; **BL-1462, 0.14.0**) `docker-compose.yml` passes three things through from a
`.env` file next to it (or your environment); none has a default, because port 5000 is published and a known default would be a
known credential. Set one:

| You set | What happens |
|---|---|
| `AOUDA_SERVER_KEY=mk_srv_<64 hex characters>` (make one with `echo "mk_srv_$(openssl rand -hex 32)"`) | Declarative: the key operates the server, no admin is created |
| `AOUDA_ROOT_EMAIL` and `AOUDA_ROOT_PASSWORD` | The first admin is created at start. Neither has a default. Put both in a `.env` file next to the compose file or export them; remove them afterwards if you like: the admin lives in the data volume |
| `AOUDA_DEV_ADMIN=true` | Development and tests only. The server makes a random throwaway admin and server key at every start and prints one line, `AOUDA-DEV-ADMIN email=... password=... server_key=...`, to the container's standard output: `AOUDA_DEV_ADMIN=true docker compose up -d`, then read `docker compose logs aouda` for the `AOUDA-DEV-ADMIN` line. Compose runs the container in the Development environment for that. Refused next to `AOUDA_ROOT_PASSWORD` or a server key. See [Development admin](../guides/development-admin.md) |
| none, on a new volume | Setup mode, as above; Studio waits (`service_healthy`) until the first admin exists |
| none, on a volume that was set up but now has no user, no active server key and nothing declared | The start is refused: the line starts `SERVER_HAS_NO_OPERATOR: ` and names the ways out, and the exit status is `78` (**BL-1461**, **BL-1462**, 0.14.0) |
| none, on a volume that holds an admin or an active server key | Starts normally |

⚠️ **`Aouda:Auth:RequireFirstAdmin` is gone** (**BL-1462, 0.14.0**). It made a server with no admin and no declared admin
fail the start, which under `restart: unless-stopped` was a restart loop. A server with nothing declared now waits in setup mode
and `/ready` says so; a server that declares a server key needs no admin at all. A leftover `AOUDA_AUTH__REQUIREFIRSTADMIN` is
ignored.

⚠️ **Leave `AOUDA_DEV_ADMIN` unset unless you mean it.** Any non-empty value, `false` included, switches the container to the Development environment (an empty value is treated as Production, where the flag is refused).

---

## The first admin

**On a running server in setup mode**, create it through the setup route. Setup is loopback-only, so call it from inside the
container:

```bash
printf '{"email":"%s","password":"%s"}' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" |
  docker exec -i aouda wget -qO- --header 'Content-Type: application/json' \
    --post-file=/dev/stdin http://localhost:5000/api/auth/setup
```

The password goes on standard input, never on a command line (a command line is readable in `/proc/<pid>/cmdline` and kept by
shell history); `printf` is a shell builtin, so it appears in no process's arguments. Escape a `"` or `\` in the password for
JSON.

The answer carries an access and a refresh token, and the server leaves setup mode at once (`/ready` turns `200` with nothing
else missing).

⚠️ **`aouda create-admin` refuses while the server runs** (**BL-1462, 0.14.0**). The server holds its data directory (an
exclusive lock on `/data/Server/aouda.lock`), and `create-admin` opens the directory itself, so next to a running server it exits
`1` with:

```
The data directory '/data' is in use by another Aouda process (it holds Server/aouda.lock). Two processes on one data directory are not safe, so nothing was opened. To create the first admin on a running server in setup mode, call POST /api/auth/setup from the server's own host; otherwise stop the server and run this command again.
```

Before, it succeeded: a second process wrote to the live data directory, and the running server stayed in setup mode until a
restart. With the server stopped, `create-admin` works as before, over standard input or from a mounted file (never on the
command line):

```bash
docker compose stop aouda
printf '%s' "$ADMIN_PASSWORD" | docker compose run --rm -T --entrypoint aouda aouda \
  create-admin --email admin@example.com --password-stdin --data /data
docker compose start aouda
```

The image carries an `aouda` command on `PATH` (a thin wrapper around `dotnet Aouda.Server.dll`); the image's entrypoint is
`dotnet Aouda.Server.dll start`, hence `--entrypoint aouda` for a one-off command.

Or with Docker secrets, which is the better answer for anything long-lived:

```yaml
services:
  aouda:
    secrets: [aouda_admin_password]
secrets:
  aouda_admin_password:
    file: ./admin-password
```

then `--password-file /run/secrets/aouda_admin_password`.

**API keys from secrets (BL-1389, 0.11.0).** A key declared in the identities file (`Aouda:Auth:Keys:File`) can be read from a secret file, so it never passes through an environment variable:

```json
{ "identities": [ { "name": "feeder", "kind": "scoped_service",
    "authDatabase": "derive_auth", "database": "deposit",
    "roles": ["quote_writer"], "secrets": [ { "file": "/run/secrets/feeder_key" } ] } ] }
```

That entry is only valid next to the declarations it names: the auth database `derive_auth` (`authDatabase`: **leave it out and the key targets a database called `auth`**, which here does not exist, so `aouda plan` exits `0` with the warning `KEY_TARGET_PENDING` and every request with the key is `401`), the role `quote_writer` declared on it, and the application database `deposit`, linked to it. A complete set that `aouda plan` accepts, as a configuration file in the shape of `appsettings.json` (the image ships none: mount it as the [declaration file](#the-declaration-file-one-mounted-file-makes-reload-work-next-train); `Aouda:Auth:Keys:File` points at the identities file above):

```json
{
  "Aouda": {
    "Auth": { "Keys": { "File": "/etc/aouda/aouda.identities.json" } },
    "Databases": {
      "derive_auth": {
        "Kind": "auth",
        "Roles": {
          "quote_writer": {
            "Description": "Runs insert_quote on deposit",
            "Permissions": [
              { "ResourceType": "named-mutation", "ResourceName": "insert_quote", "Actions": "execute" }
            ]
          }
        }
      },
      "deposit": { "AuthDatabase": "derive_auth", "SchemaFile": "/etc/aouda/deposit.schema.json" }
    }
  }
}
```

and `deposit.schema.json`, which creates the table and the named mutation the role names (a role is applied after the schema, so it may name them):

```json
{
  "tables": {
    "quotes": {
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

The role holds only `execute` on the mutation: running a named mutation needs that row and no table right ([Declared databases](../guides/declared-databases.md#why-roles-is-only-on-an-auth-database)), so a feeder that only calls `insert_quote` needs nothing else. A role that needs direct table writes adds `{ "ResourceType": "table", "ResourceName": "quotes", "Actions": "write" }`, which does not run mutations. Run `aouda plan` on these files before you start: the identities file and the role are cross-checked by it (`KEY_ROLE_UNDECLARED`, `KEY_DATABASE_NOT_LINKED`). The same set with two data databases, every key kind, a compose file, a plan step, a wipe-and-start and a reload is on [Declare a deployment](../guides/declare-a-deployment.md).

The file holds the key and nothing else (one trailing newline is ignored). A relative path is read from the identities file's directory, and `$NAME` / `${NAME}` in the path are expanded from the environment (systemd's `$CREDENTIALS_DIRECTORY/feeder` works as written). The file is read at start and again at every `aouda reload` (never between them), as UTF-8 (a UTF-8 byte-order mark is ignored, a UTF-16 file such as PowerShell's `Out-File` writes is refused); a missing, unreadable or empty file stops the server. This source makes no mode check. Compose bind-mounts a `file:` secret with the **host file's** owner and mode, and the image runs as uid 1654, so give the host file mode `0444` (in a directory only you can enter); a `0600` file owned by someone else is unreadable and stops the server (tested with Compose 2.40). See [Keys that survive a wipe](../guides/keys-that-survive-a-wipe.md).

---

## Reload without a restart

(**BL-1427, 0.14.0**) `aouda reload` asks the running server to re-read its declaration (the identities file's content, a new `Aouda:Databases` entry, a declared database's schema file and roles, a first auth-database link) and converge it. The CLI only carries a **server key** to `POST /api/admin/reload`; the server re-reads **its own** files. In a container that means three things:

1. **Run the command where it can reach the server and read the key.** From inside the server's container:

   ```bash
   docker compose exec aouda aouda reload --server http://localhost:5000 --key-file /run/secrets/aouda_server_key
   ```

   `--server` is required (the image listens on port **5000**), and so is exactly one of `--key-file PATH` or `--key-env NAME`: there is no `--key`, because a command line is kept in the process list and in shell history. **The key file must be mounted in the container the command runs in**: here the compose service lists the secret (`secrets: [aouda_server_key]`) so Compose mounts it at `/run/secrets/aouda_server_key`. A key file that exists only on the host is not there inside the container, and the command exits `64`. The command can instead run on the host against the published port (`--server http://127.0.0.1:5000 --key-file ./aouda_server_key`), or in any other container that can reach the server and holds the key. Add `--json` for one JSON object.
2. **The changed declaration must be in the running container's files.** A bind-mounted identities file or schema file that you edited on the host is what the server re-reads (mount the **directory** that holds them: a single-file bind mount keeps the old inode when the host file is replaced, see below); an image rebuilt or a file copied in at build time is not there until the container is replaced. An identities file's `{ "file": PATH }` secrets are re-read too.
3. **Settings from environment variables cannot be reloaded.** `Aouda:Databases` given as `Aouda__Databases__<name>__<Key>` variables is reported as the info `SOURCE_NOT_RELOADABLE` by a reload (and `SOURCE_FIXED_AT_START` by `aouda plan`), and a secret declared `{ "env": NAME }` keeps the value the process started with (a running process cannot change its own environment). The image ships no `appsettings*.json`, so declare them in the **declaration file** below. To reload a rotated key, declare it as `file` or `hash`.

### The declaration file: one mounted file makes reload work (**next train**)

Mount **one JSON file** at **`/etc/aouda/aouda.json`**. The server reads it by itself when it exists (nothing to set), and it holds `Aouda:Databases`, `Aouda:Auth:Keys:File` and the other declaration settings in the shape of `appsettings.json`. Another path: `AOUDA_CONFIG_FILE=/path` or `aouda start --config /path` (the switch wins; an empty variable counts as unset). An environment variable or a command-line argument still overrides a scalar the file sets, but `Aouda:Databases` and the identities path set that way are fixed for the life of the process. A reload re-reads the file at its path every time, with no watcher.

```yaml
services:
  aouda:
    image: ghcr.io/aoudadb/aouda-server:<version>
    volumes:
      - aouda-data:/data
      - ./declaration:/etc/aouda:ro        # holds aouda.json, identities.json and the schema files
    secrets: [aouda_server_key]            # and one per key the identities file names
```

⚠️ **Mount the directory, not the file.** `./aouda.json:/etc/aouda/aouda.json:ro` binds one file and Docker pins its inode: an editor that saves by renaming a new file over the old one, a `git checkout` or a `mv` leaves the container reading the **old content**, and a reload then changes nothing (tested with Docker 29). A directory mount follows the name. **The host file must exist before `up`**: if it does not, Docker creates a *directory* at that path, and the server refuses to start with `CONFIGURATION_INVALID` (exit `78`, "is a directory, not a file"). Do not mount anything else at `/etc/aouda` on a Kubernetes pod that uses the chart's `declaration.config`; see [Kubernetes and Helm](kubernetes.md#declaring-databases-keys-and-schema-files).

| The file is | The start | A reload |
|---|---|---|
| Absent, at the well-known path | Skipped, silently | n/a |
| Named by `--config` / `AOUDA_CONFIG_FILE` and absent | `CONFIGURATION_INVALID`, exit `78` | `422 RELOAD_REFUSED` (finding `CONFIGURATION_INVALID`); nothing changes |
| Empty (also at the well-known path), a directory, or not valid JSON | `CONFIGURATION_INVALID`, exit `78`, naming the file and the line and position, never the contents | The same refusal; nothing changes |
| Unreadable: permissions, an I/O error, a volume not mounted yet | Exit `1` (a supervisor may retry) | Refused |
| Present and read, then gone at the next reload | n/a | Refused: not read as "no databases" |

**Write `{}` to declare nothing**: an empty file is an error, because a half-written mount must not be taken for "no declaration". A complete working set (two data databases, an auth database, keys, a role, a mutation) is on [Declare a deployment](../guides/declare-a-deployment.md); what a reload can and cannot change is [one table](../guides/server-configuration.md#reload-or-restart).

It exits `0` (nothing to change), `2` (applied), `1` (refused or stopped part-way), `64` (usage), `69` (unreachable, busy or starting) and `77` (the key was refused). `aouda plan --server` is the dry run ([Plan a declaration](../guides/plan.md)). The server key (`Aouda:Auth:Bootstrap:*`), the identities file's **path**, the listener, memory and a database's operational fields still take a restart: a reload lists them under `restartRequired` and applies the rest.

---

## A container that keeps restarting

(**BL-1461, BL-1463, 0.14.0**) A start refused for its configuration (a bad key declaration, a declared database whose `AuthDatabase`
does not exist, a set-up server left with no operator, a data directory in another format) exits with status **78** and prints every
finding on standard error, each as a line `error    <CODE>  <setting or file>` followed by the message and the fix, then a last line
naming the exit status. The codes are in [Declaration Finding Codes](../reference/plan-codes.md), the format in
[the exit status table](linux.md#when-the-start-is-refused).

⚠️ **Docker's `restart:` policies cannot exempt an exit status.** `unless-stopped`, `always` and `on-failure` all restart a container
that exited 78, so a refused configuration is a restart loop, and the loop itself tells you nothing: **the container's output is what
names the setting.** (systemd can stop on it, with `RestartPreventExitStatus=78`; Docker has no equivalent.)

```bash
docker compose logs --no-log-prefix aouda | grep -E '^error +[A-Z_]+' | tail -5   # e.g. error    KEY_SECRET_SHARED  Aouda:Auth:...
docker compose ps -a aouda                                                        # STATUS: Restarting (78) ...
```

Check the declaration before you deploy, in the container you deploy, with its environment, secrets and mounts:

```bash
docker compose run --rm --no-deps --entrypoint aouda aouda plan
```

It runs the start's own checks over the configuration the server will read, prints every finding the start would print, and exits `1`
when the start would refuse. See [Plan a declaration](../guides/plan.md).

---

## Logs

The container logs to stdout, so `docker logs aouda` is all of it. (**BL-1461, 0.14.0**) The one exception is a refused start's two
lines, which go to standard error; `docker logs` shows both streams.

⚠️ **The default log level is `Warning`** for every category except startup narration. If a line the documentation mentions is not appearing, that is usually why — see [Defaults reference](../guides/defaults-reference.md#logging-defaults).

---

## Kubernetes

The chart is unchanged by any of the above and has its own page: [Kubernetes and Helm](kubernetes.md). The only thing to carry across is the image name — `ghcr.io/aoudadb/aouda-server`, with an `imagePullSecret`, because it is private.
