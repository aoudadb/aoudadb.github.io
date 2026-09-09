---
title: "Deployment"
nav_order: 5
has_children: true
---

# Deployment

Aouda can be deployed in multiple ways depending on your infrastructure.

| Mode | Best for |
|---|---|
| **CLI** (`aouda start`) | Local development, quick demos, agent workflows |
| **Docker** | Containerized environments, simple single-node production |
| **Docker Compose** | Server + Studio together, local multi-service setup |
| **Kubernetes / Helm** | Production clusters, multi-node replication, managed rollouts |
| **Windows Service** | On-premise Windows servers | Service registered with `--data-path` and `--port` — see [Server configuration](../guides/server-configuration.md) |
| **systemd** | On-premise Linux servers |

See [Getting Started — Server Mode](../getting-started/#4-server-mode--standalone-database-server) for Docker and CLI quick-start options.

**Configuration:** [Server configuration](../guides/server-configuration.md) — precedence among install bootstrap, env vars, CLI flags, optional appsettings, runtime API, and what survives restart.

**Shutdown budget:** `Aouda:ShutdownTimeout` defaults to **120 s**. The orchestrator grace (`stop_grace_period` / `terminationGracePeriodSeconds`) must be **greater than** that plus a margin (the reference compose files use **130 s**). A 10 s grace against a 120 s host timeout is how a SIGKILL lands mid-shutdown. Worked example and the slow-open / `OpenKilled` recovery command: [Server configuration §8](../guides/server-configuration.md#8-startup-shutdown-and-slow-opens).

```yaml
services:
  aouda:
    image: aouda/server
    stop_grace_period: 130s
    environment:
      AOUDA_DATA_PATH: /data
      AOUDA_SHUTDOWNTIMEOUT: "00:02:00"
```

The guide below covers Kubernetes and Helm in depth. If an Ingress, Service `LoadBalancer`, or other reverse proxy terminates TLS in front of the chart, configure trusted proxies or **per-IP rate limits, lockout attribution, and audit-log client IPs are wrong** — [Behind a reverse proxy](reverse-proxy.md).
