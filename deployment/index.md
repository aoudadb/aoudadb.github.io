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

The guide below covers Kubernetes and Helm in depth.
