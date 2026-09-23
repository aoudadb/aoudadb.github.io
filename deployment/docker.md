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

---

## The first admin

⚠️ **Not on the command line.** Bootstrap over standard input, or from a mounted file:

```bash
printf '%s' "$ADMIN_PASSWORD" | docker exec -i aouda \
  dotnet Aouda.Server.dll create-admin \
    --email admin@example.com --password-stdin --data /data
```

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

---

## Logs

The container logs to stdout, so `docker logs aouda` is all of it.

⚠️ **The default log level is `Warning`** for every category except startup narration. If a line the documentation mentions is not appearing, that is usually why — see [Defaults reference](../guides/defaults-reference.md#logging-defaults).

---

## Kubernetes

The chart is unchanged by any of the above and has its own page: [Kubernetes and Helm](kubernetes.md). The only thing to carry across is the image name — `ghcr.io/aoudadb/aouda-server`, with an `imagePullSecret`, because it is private.
