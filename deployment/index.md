---
title: "Deployment"
nav_order: 5
has_children: true
---

# Deployment

Aouda runs from **one binary**. `aouda` and `Aouda.Server` are two names for the same executable, and every mode below is that executable under a different supervisor.

| Mode | Best for | Guide |
|---|---|---|
| **CLI** (`aouda start`) | Local development, quick demos, agent workflows | [Getting started](../getting-started/) |
| **Linux / systemd** | On-premise or cloud Linux servers | [Linux (systemd)](linux.md) |
| **Windows Service** | On-premise Windows servers | [Windows Service](windows.md) |
| **Docker** | Containerised environments, single-node production | [Docker](docker.md) |
| **Docker Compose** | Server + Studio together, local multi-service setup | [Docker](docker.md#shutdown-grace) |
| **Kubernetes / Helm** | Production clusters, multi-node replication, managed rollouts | [Kubernetes and Helm](kubernetes.md) |

---

## ⚠️ Artefacts are private

Aouda's server artefacts — the per-platform archives and the container image — are published to the **private** `aoudadb` organisation. There is:

- **no public download** and no `curl … | sh`;
- **no anonymous `docker pull`** — the image is `ghcr.io/aoudadb/aouda-server` and needs a token;
- **no nuget.org package** — the `aouda` tool comes from the private feed, with `--add-source`.

Every install page below says where its artefact comes from and what credential it needs. If you are reading an instruction that does not, it is out of date.

> **`image: aouda/server` does not exist.** It appeared in older examples and was never published under that name. The real name is `ghcr.io/aoudadb/aouda-server`.

---

## Two settings decide whether it behaves under load

They are the same two on every platform, and both pages repeat them because both are easy to leave out:

**A memory limit does more than cap memory.** It creates a cgroup boundary, and Aouda takes **70 %** of a limit it was given against **40 %** of a host it merely measured — a host's total RAM says nothing about how much of it Aouda owns. Without one, a server both under-uses its machine *and* can claim memory nobody promised it.

**A CPU *share* is not a CPU *limit*.** A share carries no core count, so the kernel exposes no quota and Aouda sizes scan parallelism from the whole node.

Both are covered per platform: [systemd](linux.md#the-memory-limit-and-why-it-does-more-than-you-think), [Docker](docker.md#-m-is-the-single-most-valuable-flag-in-that-command), and — ⚠️ with an important difference — [Windows](windows.md#-where-windows-differs-from-linux-there-is-no-memory-limit), which has no equivalent of either.

---

## Shutdown budget

`Aouda:ShutdownTimeout` defaults to **120 s**. The orchestrator grace (`stop_grace_period` / `terminationGracePeriodSeconds`) must be **greater than** that plus a margin — the reference compose files use **130 s**. A 10 s grace against a 120 s host timeout is how a `SIGKILL` lands mid-shutdown.

Worked example and the slow-open / `OpenKilled` recovery command: [Server configuration §8](../guides/server-configuration.md#8-startup-shutdown-and-slow-opens).

---

## Whatever you deploy

- **Configuration:** [Server configuration](../guides/server-configuration.md) — precedence among install bootstrap, environment variables, CLI flags, optional appsettings, the runtime API, and what survives a restart.
- **TLS:** Aouda does not terminate it. If an Ingress, a `LoadBalancer` Service or any other reverse proxy sits in front, configure trusted proxies or **per-IP rate limits, lockout attribution and audit-log client IPs will all be wrong** — [Behind a reverse proxy](reverse-proxy.md).
- **Probes:** use **`/ready`**, never `/health`. `/health` answers `200` whenever the process is running, including while every write is failing.
- **Ask the server what it is doing:** `aouda status` and `aouda doctor`, both with `--output json`. `doctor` reports findings with a remedy attached, and is meant to be pasted into a support thread.
