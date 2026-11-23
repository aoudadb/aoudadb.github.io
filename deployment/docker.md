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

⚠️ **The container's user is uid/gid 1654** (matching `$APP_UID`, the uid Microsoft's aspnet images standardize on since.NET 8). A bind-mounted host directory must be `chown`ed to `1654:1654` — or writable by it — before the container starts, or directory creation under the data path fails and the process exits immediately. A named volume (as in the example above) does not have this problem: Docker initializes it from the image's own ownership on first use.

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
set up, with no operator declared in the declaration file, is in setup mode and serves no application traffic, so `/ready` answers `503` and lists the reason `setup_required` (since
0.11.0, BL-1393). That is the probe telling the truth, not a fault. `/health` and `/startup` answer `200` meanwhile (**BL-1462,
0.14.0**). Anything that waits on the healthcheck (`depends_on: condition: service_healthy`, a deploy gate) waits for setup
too.

To see why, read the body from outside the container: `curl -s http://localhost:5000/ready` (`/ready` needs no credential). The image's own `wget` does not print the body of a `503`, so `docker exec aouda wget -qO- http://localhost:5000/ready` shows nothing.

### Setup mode only when nothing is declared

(**BL-1462, 0.14.0**) Declare how the server is operated and it starts ready. Setup mode, the interactive first run, exists
only for a data volume that has **never been set up** (no server auth database) and a server that declares none of these:

| You declare | What happens at start |
|---|---|
| A key-only operator (**BL-1464, 0.16.0**): a `server.principals` entry in the declaration file holding the role `admin`, with a `derivedKey` (from the file's `keyRoot`) or a stored key `{ "id", "sha256" }` under `credentials.keys` | No setup mode. The server auth database is created with the principal and its key, and the key operates the server from the first start: create databases, principals and keys with it. No human admin is needed |
| A first admin (**BL-1464, 0.16.0**): a `server.principals` entry named by the email, holding the role `admin`, with a password seed `{ "file": "<path>" }`, `{ "env": "<NAME>" }` or `{ "hash":... }` | The admin is created once, with a forced password change at the first sign-in; no setup mode. The seed is applied only when the principal is created, never again |
| `AOUDA_DEV_ADMIN=true` | Development and tests only: a throwaway admin and its key, printed once. Refused next to a declared server operator's credentials (`SERVER_KEY_DEV_ADMIN_CONFLICT`). See [Development admin](../guides/development-admin.md) |
| none of them, on a new volume | **Setup mode**: `/startup` 200, `/ready` 503 `setup_required`, every other route `503 SETUP_REQUIRED` off the server's host |
| none of them, on a volume set up before that still has an operator (an admin, or a principal holding `admin` with an active key) | Starts normally, operated by them. **Never setup mode again**: a set-up server back in setup mode could be claimed by any loopback caller |
| none of them, on a volume set up before that has nobody who can manage the server (a restore, every key revoked) | **The start is refused**: `SERVER_HAS_NO_OPERATOR: this data directory has been set up before...`, naming the ways out (declare an operator in the declaration file's `server.principals`, or `--dev-admin` for development). Declare one and restart |

The declaration file is named by `Aouda__Declaration` (or `aouda start --declaration <path>`); there is no default path. Example, a
first admin by password seed:

```json
{ "version": 1, "server": { "principals": { "you@example.com": { "roles": ["admin"],
 "credentials": { "password": { "env": "AOUDA_ADMIN_PASSWORD" } } } } } }
```

and a key-only operator, its key root from a secret:

```json
{ "version": 1, "keyRoot": { "env": "AOUDA_KEY_ROOT" },
 "server": { "principals": { "ops": { "roles": ["admin"], "credentials": { "derivedKey": { "version": 1 } } } } } }
```

**The old operator settings are refused** (**BL-1464, 0.16.0**). Each one set is a `SETTING_REMOVED` finding at start, before any
database opens, and the start exits `78`; the message names the replacement and never the value. An **empty** value (a compose
`${VAR:-}` pass-through of a variable that is not set) counts as not set and is not refused.

| Removed | Declare instead |
|---|---|
| The systemd credentials `aouda-server-key`, `aouda-admin-password` | Remove the `LoadCredential=` line and declare as above |

Before 0.14.0 a declared server key did **not** end setup mode: it was inert until a human created an admin, so a fully
declarative deployment still needed an admin password, and a compose file gated on `/ready` sat in setup mode after a wipe.

### Compose

(**BL-1407, 0.12.0**; **BL-1423, 0.12.0**; **BL-1462, 0.14.0**; **BL-1464, 0.16.0**) `docker-compose.yml` passes three
things through from a `.env` file next to it (or your environment); none has a default, because port 5000 is published and a known
default would be a known credential:

```yaml
 environment:
 Aouda__Declaration: ${AOUDA_DECLARATION:-}
 AOUDA_ADMIN_PASSWORD: ${AOUDA_ADMIN_PASSWORD:-}
 AOUDA_DEV_ADMIN: ${AOUDA_DEV_ADMIN:-}
 volumes:
 - aouda_data:/data
 # -./aouda.json:/etc/aouda/aouda.json:ro
```

| You set | What happens |
|---|---|
| A declared operator: write `aouda.json` next to the compose file (the first-admin example above declares `you@example.com` with `{ "password": { "env": "AOUDA_ADMIN_PASSWORD" } }`), uncomment its volume line, and set `AOUDA_DECLARATION=/etc/aouda/aouda.json` and `AOUDA_ADMIN_PASSWORD=<something long>` in `.env` | The first admin is created at start, with a forced password change at the first sign-in. The password seeds the admin once, when it is created; remove it from `.env` afterwards if you like: the admin lives in the data volume. A key-only operator is declared the same way, its key root passed through instead of the password |
| `AOUDA_DEV_ADMIN=true` | Development and tests only. The server makes a random throwaway admin and its key at every start and prints one line, `AOUDA-DEV-ADMIN email=... password=... key=...`, to the container's standard output: `AOUDA_DEV_ADMIN=true docker compose up -d`, then read `docker compose logs aouda` for the `AOUDA-DEV-ADMIN` line. Compose runs the container in the Development environment for that. Refused next to a declared server operator's credentials (`SERVER_KEY_DEV_ADMIN_CONFLICT`). See [Development admin](../guides/development-admin.md) |
| none, on a new volume | Setup mode, as above; Studio waits (`service_healthy`) until the first admin exists |
| none, on a volume that was set up but now has nobody who can manage the server and nothing declared | The start is refused: the line starts `SERVER_HAS_NO_OPERATOR: ` and names the ways out, and the exit status is `78` (**BL-1461**, **BL-1462**, 0.14.0) |
| none, on a volume that holds an operator | Starts normally |

The compose file no longer passes `AOUDA_SERVER_KEY`, `AOUDA_ROOT_EMAIL` or `AOUDA_ROOT_PASSWORD` (**BL-1464, 0.16.0**): a `.env`
that still sets them sets nothing, and the server would start in setup mode. Move them into the declaration as above.

⚠️ **`Aouda:Auth:RequireFirstAdmin` is gone** (**BL-1462, 0.14.0**). It made a server with no admin and no declared admin
fail the start, which under `restart: unless-stopped` was a restart loop. A server with nothing declared now waits in setup mode
and `/ready` says so; a server that declares a key-only operator needs no admin at all. A leftover `AOUDA_AUTH__REQUIREFIRSTADMIN` is
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

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
`1` with:

```
The data directory '/data' is in use by another Aouda process (it holds Server/aouda.lock). Two processes on one data directory are not safe, so nothing was opened. To create the first admin on a running server in setup mode, call POST /api/auth/setup from the server's own host; otherwise stop the server and run this command again.
```

Before, it succeeded: a second process wrote to the live data directory, and the running server stayed in setup mode until a
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).
command line):

```bash
docker compose stop aouda
printf '%s' "$ADMIN_PASSWORD" | docker compose run --rm -T --entrypoint aouda aouda \
# an aouda_ key or a session. GET /api/auth/whoami names the principal.
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
 file:./admin-password
```

then `--password-file /run/secrets/aouda_admin_password`.

**Secrets of the declaration from Docker secrets** (**BL-1464, 0.16.0**). The declaration's key root and a password seed can be
read from a secret file, so they never pass through an environment variable: `"keyRoot": { "file": "/run/secrets/aouda_key_root" }`,
or `"password": { "file": "/run/secrets/aouda_admin_password" }` on the first admin. A relative path is read from the declaration
file's directory, and `$NAME` / `${NAME}` in the path are expanded from the environment. The file is read as UTF-8 (a UTF-8
byte-order mark is ignored, a UTF-16 file such as PowerShell's `Out-File` writes is refused) with one trailing newline ignored; a
missing, unreadable or empty file stops the start. Docker mounts file-based secrets as `0444` by default, and this source does not
refuse that. See [Keys that survive a wipe](../guides/keys-that-survive-a-wipe.md#secret-files). The identities file's
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

---

## Declare the databases: `aouda.json` (**BL-1463, 0.16.0**)

The databases, their schema files and their roles are one file, `aouda.json`, that you mount and **name**: the server reads the
declaration from the path in `Aouda:Declaration` and from no other (there is no default path; with nothing set, nothing is declared).
Mount the **directory** that holds it, read-only, and set the one variable:

```yaml
 environment:
 Aouda__Declaration: /etc/aouda/aouda.json
 AOUDA_ENVIRONMENT: prod # optional: also reads /etc/aouda/aouda.prod.json over it
 volumes:
 -./aouda:/etc/aouda:ro # aouda.json, aouda.prod.json, schema/shop.aouda.schema.json
```

```json
{ "version": 1, "databases": { "auth": { "kind": "auth" }, "shop": { "kind": "data", "authDatabase": "auth", "schema": "schema/shop.aouda.schema.json" } } }
```

A relative `schema` path is relative to the directory of `aouda.json`, so the same file works from the container, a unit and a
shell. A variable that is **set** to a path with no file behind it (a mount that was not made, a bind mount of a file that did not
exist, which Docker creates as a directory) refuses the start naming the file and exits `1`, so a restart policy retries it; a
variable that is set to nothing (a compose pass-through of an unset variable) is read as not set. `Aouda__Databases__*` variables
are **refused** (`SETTING_REMOVED`, naming the member of `aouda.json`). The whole file is in
[Declare a server in one file](../guides/declaration.md).

---

## A container that keeps restarting

(**BL-1461, BL-1463, 0.14.0**) A start refused for its configuration (a bad key declaration, a declared database whose `authDatabase`
does not exist, a set-up server left with no operator, a data directory in another format) exits with status **78** and prints every
finding on standard error, each as a line `error <CODE> <setting or file>` followed by the message and the fix, then a last line
naming the exit status. The codes are in [Declaration Finding Codes](../reference/plan-codes.md), the format in
[the exit status table](linux.md#when-the-start-is-refused).

⚠️ **Docker's `restart:` policies cannot exempt an exit status.** `unless-stopped`, `always` and `on-failure` all restart a container
that exited 78, so a refused configuration is a restart loop, and the loop itself tells you nothing: **the container's output is what
names the setting.** (systemd can stop on it, with `RestartPreventExitStatus=78`; Docker has no equivalent.)

```bash
docker compose logs --no-log-prefix aouda | grep -E '^error +[A-Z_]+' | tail -5 # e.g. error KEY_SECRET_SHARED Aouda:Auth:...
docker compose ps -a aouda # STATUS: Restarting (78)...
```

Check the declaration before you deploy, in the container you deploy, with its environment, secrets and mounts:

```bash
docker compose run --rm --no-deps --entrypoint aouda aouda plan
```

It runs the start's own checks over the configuration the server will read (with `Aouda__Declaration` set in the container's environment it reads the same `aouda.json`, and its overlay for `AOUDA_ENVIRONMENT`), prints every finding the start would print, and exits `1`
when the start would refuse. See [Plan a declaration](../guides/plan.md).

---

## Logs

The container logs to stdout, so `docker logs aouda` is all of it. (**BL-1461, 0.14.0**) The one exception is a refused start's two
lines, which go to standard error; `docker logs` shows both streams.

⚠️ **The default log level is `Warning`** for every category except startup narration. If a line the documentation mentions is not appearing, that is usually why — see [Defaults reference](../guides/defaults-reference.md#logging-defaults).

---

## Kubernetes

The chart is unchanged by any of the above and has its own page: [Kubernetes and Helm](kubernetes.md). The only thing to carry across is the image name — `ghcr.io/aoudadb/aouda-server`, with an `imagePullSecret`, because it is private.
