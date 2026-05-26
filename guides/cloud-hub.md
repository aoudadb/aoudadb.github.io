---
title: "Cloud and Hub"
nav_order: 14
parent: "Guides"
---

# Aouda Cloud, Hub, and Deployment

_Domain: Server CLI, Docker, Kubernetes, Aouda Hub, Managed Cloud_
_Status: MVP Complete (2026-04-08)_
_Primary Phases: P16_
_Repos: `aouda` (server), `aouda-hub` (Hub backend), `aouda-studio` (web console)_

---

## 1) What This Covers

This document describes how Aouda is deployed, distributed, and managed at the infrastructure level:

- **Server CLI** — how to start and configure Aouda from the command line
- **Docker** — official container images and Compose configurations
- **Kubernetes** — Helm chart for production clusters
- **Aouda Hub** — central management platform (accounts, orgs, server registry)
- **Managed Cloud** — control plane and K8s operator for automated cluster lifecycle

---

## 2) Start Here

| I want to... | Go to |
|---|---|
| Run Aouda locally for development | §3 Server CLI — `aouda start` |
| Run Aouda in Docker | §4 Docker |
| Deploy a production cluster | §5 Kubernetes Helm Chart |
| Manage servers across a team | §6 Aouda Hub |
| Provision managed clusters | §7 Managed Cloud |

---

## 3) Server CLI

The Aouda server binary is a single executable supporting subcommand dispatch.

### Commands

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `aouda start` | Production server with persistent storage | `--data-dir <path>`, `--bind <ip:port>`, `--port <port>`, `--join <primary:port>`, `--role <role>` |
| `aouda stop` | Gracefully stop a locally-running server | `--server <url>`, `--force` |
| `aouda version` | Print version and exit | — |
| `aouda databases <subcommand>` | Database administration | `list`, `get`, `create`, `drop` (each with `--server`, `--name`, `--token`) |
| `aouda schema <subcommand>` | Schema management | `diff`, `apply`, `export`, `validate`, `history` |
| `aouda init` | First-run server admin bootstrap | `--server <url>`, `--admin-email`, `--admin-password` |
| `aouda create-admin` | Create first admin user directly to engine (no HTTP) | `--email`, `--password`, `--data`, `--auth-database` |
| `aouda bulk-load` | Bulk-load rows into multiple tables atomically | `--tables <list>`, `--file <path>`, `--server`, `--database` |
| `aouda table bulk-load` | Bulk-load rows into a single table | `<table>`, `--file <path>`, `--server`, `--database` |

### Production Mode (`aouda start`)

```bash
aouda start --data-dir ./data --bind 0.0.0.0:5000
```

- Persistent storage to `--data-dir` (default: current directory)
- Bind address supports IP literals only (e.g. `0.0.0.0:5000`, `127.0.0.1:5000`)
- Configuration via environment variables (`AOUDA_*`) or config files
- `--port` forwarded to existing ASP.NET Core configuration system

### Development Mode

`aouda dev` is not a shipped command. For local development with ephemeral data, use `aouda start` with a temporary directory:

```bash
aouda start --data-dir /tmp/aouda-dev --bind 127.0.0.1:5000
```

This gives fast startup with persistent-across-restarts behavior. For a fully ephemeral (no retained files) experience, delete the data directory between runs.

### CLI-to-Config Mapping

| CLI Flag | Config Key | Environment Variable |
|----------|-----------|---------------------|
| `--data-dir` | `Aouda:DataPath` | `AOUDA_DATAPATH` |
| `--bind` | `Aouda:Bind` | `AOUDA_BIND` |
| `--port` | `Aouda:Port` | `AOUDA_PORT` |
| `--role` | `Aouda:Role` | `AOUDA_ROLE` |
| `--join` | `Aouda:Join` | `AOUDA_JOIN` |

### Cluster Bootstrap via CLI

```bash
# Start primary
aouda start --data-dir ./node1 --bind 0.0.0.0:5000

# Join as secondary
aouda start --data-dir ./node2 --bind 0.0.0.0:5001 --join 192.168.1.10:5000

# Join as witness (arbiter)
aouda start --data-dir ./node3 --bind 0.0.0.0:5002 --join 192.168.1.10:5000 --role witness
```

---

## 4) Docker

### Server Image

```bash
docker run -p 5000:5000 -v aouda-data:/data aouda/server
```

- Base: `mcr.microsoft.com/dotnet/aspnet:8.0-alpine`
- Exposes port 5000
- Data volume at `/data`
- Environment variable `AOUDA_DATA_PATH=/data` set by default

### Studio Image

```bash
docker run -p 3000:3000 -e AOUDA_STUDIO_DEFAULT_SERVER=http://aouda:5000 aouda/studio
```

- Base: Node 20 Alpine with Next.js standalone build
- No external CDN dependencies (fully self-contained)
- Configurable via environment variables

### Studio Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AOUDA_STUDIO_DEFAULT_SERVER` | Default Aouda server URL | — |
| `AOUDA_STUDIO_HUB_URL` | Hub API URL (enables Hub mode) | — |
| `AOUDA_STUDIO_THEME` | UI theme | `system` |
| `AOUDA_STUDIO_CONFIG_PATH` | Path to `aouda-studio.config.json` | `./aouda-studio.config.json` |

### Docker Compose — Single Node

`docker-compose.yml` provides Aouda server + Studio:

```bash
docker compose up
```

- Aouda at `http://localhost:5000`
- Studio at `http://localhost:3000`
- Named volume for persistent data

### Docker Compose — Cluster

`docker-compose.cluster.yml` provides 3-node cluster + witness + Studio:

```bash
docker compose -f docker-compose.cluster.yml up
```

- Primary + 2 replicas + witness
- Automatic replication bootstrap via environment variables
- Studio pre-configured to connect to primary

---

## 5) Kubernetes Helm Chart

### Quick Start

```bash
helm install aouda charts/aouda-cluster
```

### Chart: `charts/aouda-cluster/`

| Resource | Purpose |
|----------|---------|
| StatefulSet | Aouda data nodes with stable DNS names |
| Headless Service | Stable pod DNS for inter-node communication |
| Client Service | External access to Aouda |
| ConfigMap | Shared configuration |
| PVCs | Per-node persistent storage |

### Standalone Mode (1 Node)

```yaml
# values.yaml
replicaCount: 1
```

No replication environment variables set. Single-node standalone operation.

### Cluster Mode (3+ Nodes)

```yaml
# values.yaml
replicaCount: 3
```

Automatic replication bootstrap:
- `AOUDA_REPLICASET__NAME` set from chart
- `AOUDA_REPLICASET__MEMBERS__0..N-1` enumerated for all pods
- `AOUDA_REPLICASET__THISNODE__ADDRESS` uses `$(POD_NAME)` downward-API substitution
- `AOUDA_REPLICASET__REPLICATIONPORT` configured per chart values

### Witness Node

```yaml
# values.yaml
witness:
  enabled: true
```

Creates a separate Deployment (not StatefulSet — no persistent data) with dedicated ClusterIP Service. Configured with `AOUDA_REPLICASET__THISNODE__ARBITER=true`.

### Studio in Helm

```yaml
# values.yaml
studio:
  enabled: true
```

Creates Studio Deployment + Service. Auto-configured `AOUDA_STUDIO_DEFAULT_SERVER` pointing to Aouda headless service.

### Probes

| Probe | Path | Purpose |
|-------|------|---------|
| Startup | `/startup` | 200 when initialization complete, 503 during startup |
| Liveness | `/health` | 200 when process is running |
| Readiness | `/ready` | 200 when engine is accepting queries |

### Key `values.yaml` Settings

| Key | Default | Purpose |
|-----|---------|---------|
| `replicaCount` | 1 | Number of data nodes |
| `image.repository` | `aouda/server` | Server image |
| `persistence.size` | `10Gi` | PVC size per node |
| `resources.limits.memory` | `2Gi` | Memory limit |
| `witness.enabled` | `false` | Enable witness node |
| `studio.enabled` | `false` | Enable Studio deployment |
| `probes.readiness.failureThreshold` | `3` | Readiness probe tolerance |

### CI Validation

`.github/workflows/helm-chart-validation.yml` validates lint + template rendering for default/studio/witness/both scenarios.

Full documentation: `docs/dev/Kubernetes-Helm-Deployment-Guide.md`.

---

## 6) Aouda Hub

### What Hub Provides

Aouda Hub (`hub.aouda.dev`) is a central management platform for teams:

- **User accounts**: email/password registration, JWT authentication
- **Organizations**: team management with roles (owner, admin, member, viewer)
- **Server registry**: register Aouda servers, connection testing, credential vault
- **Cloud projects**: managed cluster provisioning (see §7)

### Architecture

Hub uses Aouda as its own database (self-hosting). It is an ASP.NET Core web API.

**Browser-direct architecture**: Studio SPA runs in the user's browser and connects directly to Aouda servers for data operations. Hub serves metadata only (accounts, server list). Hub never stores or proxies customer data.

### Hub API Surface

| Area | Endpoints | Purpose |
|------|-----------|---------|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`, `POST /api/auth/logout` | User authentication |
| Organizations | `POST /api/organizations`, `GET /api/organizations`, `POST /api/organizations/{id}/members` | Org management |
| Servers | `POST /api/servers`, `GET /api/servers`, `GET /api/servers/{id}/credential`, `PUT /api/servers/{id}/credential` | Server registry + credential vault |
| Cloud | `POST /api/projects`, `GET /api/projects`, `POST /api/projects/{id}/clusters`, etc. | Managed clusters (§7) |

### Studio Integration Modes

| Mode | Configuration | Behavior |
|------|--------------|----------|
| Direct | `NEXT_PUBLIC_AOUDA_URL=http://localhost:5000` | Connects to single server, no Hub needed |
| Hub | `NEXT_PUBLIC_HUB_URL=https://hub.aouda.dev` | Login to Hub, browse registered servers, switch between them |

### Credential Vault

Server credentials (API keys, passwords) stored encrypted in Hub, accessible only to org members. Credential flow:
1. User selects server in Studio
2. Studio checks server health and detects auth requirement
3. If stored credential exists in vault → auto-apply
4. If not → prompt user, offer "Save to Hub" option

### Offline/Air-gapped Operation

- `aouda-studio.config.json` provides server connections when Hub is unreachable
- Studio Docker image works fully offline (no external resource loading)
- Aouda servers function fully when Hub is unreachable (Hub is management plane, not data path)

### Hub Configuration

Environment variables with `AOUDA_HUB_` prefix:
- `AOUDA_HUB_AOUDA_URL` — backing Aouda instance URL
- `AOUDA_HUB_AOUDA_SERVICE_KEY` — service key for backing Aouda
- `AOUDA_HUB_K8S_ENABLED` — enable K8s provisioner (default: false)

---

## 7) Managed Cloud Foundation

### Control Plane

The control plane is a module within Hub that manages cloud project and cluster lifecycle:

- **Projects**: scoped to organizations, CRUD with membership authorization
- **Managed clusters**: async provisioning state machine

### Cluster Lifecycle States

```
pending → provisioning → running → scaling → deprovisioning → deleted
```

All mutating cluster operations return HTTP 202 (accepted, async). Cluster events are recorded with timestamps.

### AoudaCluster CRD

Kubernetes Custom Resource Definition (`aouda.dev/v1/AoudaCluster`):

```yaml
apiVersion: aouda.dev/v1
kind: AoudaCluster
metadata:
  name: my-cluster
spec:
  nodes: 3
  storageSizeGb: 50
  memoryBudgetGb: 4
  witness:
    enabled: true
  image:
    tag: "latest"
```

Status subresource reports phase, ready replicas, endpoint, and observed generation.

### K8s Operator

Go-based controller-runtime operator that reconciles `AoudaCluster` CRD objects:

- Creates/manages StatefulSet, headless Service, client Service
- Owner references with `BlockOwnerDeletion` for garbage collection
- Finalizer lifecycle for clean deletion
- Witness Deployment management (add/remove on spec changes)
- Standalone mode detection (1 node = no replication env vars)
- Status phase transitions (Provisioning → Running)

### Hub K8s Provisioner

`IClusterProvisioner` interface with two implementations:
- `StubClusterProvisioner` — development/testing (instant transitions)
- `KubernetesClusterProvisioner` — creates/updates/deletes AoudaCluster CRD objects via `KubernetesClient`

Conditional registration: `AOUDA_HUB_K8S_ENABLED=true` enables the K8s provisioner.

---

## 8) Server Admin APIs

All management APIs are under the `/admin/` prefix, separated from data APIs under `/api/`.

### API Summary

| Area | Prefix | Endpoints |
|------|--------|-----------|
| Cluster | `/admin/cluster/` | `POST join`, `DELETE leave`, `POST promote`, `POST failover`, `POST drain/{nodeAddress}`, `GET config`, `PATCH config` |
| Backup | `/admin/backup/` | `POST trigger`, `GET list`, `POST restore/{id}`, `GET schedule`, `PUT schedule` |
| Config | `/admin/config` | get, patch, schema |
| Capabilities | `/admin/capabilities` | server capabilities discovery |
| Node | `/admin/node` | node info, logs, log streaming (SSE) |

### Authentication

When a server auth database is configured, all admin endpoints require a bearer token (server auth scope). When no auth database is configured, admin endpoints pass through (same graceful behavior as all other endpoints).

Server admin API keys (`mk_srv_` prefix) can be created, listed, and revoked via `/api/auth/admin/keys`.

### Cluster API Examples

```bash
# Join a node to a cluster
curl -s -X POST http://localhost:5000/admin/cluster/join \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"primaryAddress":"192.168.1.10:5000","replicaSetName":"prod-rs"}'
# → 200 + { "message": "Joined cluster successfully", "replicaSetName": "prod-rs" }

# Get cluster config
curl -s http://localhost:5000/admin/cluster/config \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "mode": "cluster", "replicaSetName": "prod-rs", ... }

# Patch mutable cluster config (heartbeatIntervalMs, electionTimeoutMs)
curl -s -X PATCH http://localhost:5000/admin/cluster/config \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"heartbeatIntervalMs":3000}'
# → 200 + updated config

# Trigger failover (primary steps down)
curl -s -X POST http://localhost:5000/admin/cluster/failover \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "message": "Primary stepped down; election triggered" }

# Leave cluster (revert to standalone)
curl -s -X DELETE http://localhost:5000/admin/cluster/leave \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "message": "Left cluster, now running as standalone" }
```

### Backup API Examples

```bash
# Trigger an immediate backup
curl -s -X POST http://localhost:5000/admin/backup/trigger \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"incremental":true}'
# → 202 + { "backupId": "...", "totalBytes": 1048576, "newBytes": 65536, ... }

# List available backups
curl -s http://localhost:5000/admin/backup/list \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "backups": [ { "backupId": "...", "createdUtc": "...", ... } ] }

# Restore from a backup
curl -s -X POST http://localhost:5000/admin/backup/restore/<backupId> \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "backupId": "...", "filesRestored": 42, "integrityVerified": true, ... }

# Get backup schedule
curl -s http://localhost:5000/admin/backup/schedule \
     -H "Authorization: Bearer mk_srv_..."
# → 200 + { "cronExpression": null, "incremental": true }

# Set backup schedule (daily at 02:00)
curl -s -X PUT http://localhost:5000/admin/backup/schedule \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mk_srv_..." \
     -d '{"cronExpression":"0 2 * * *","incremental":true}'
```

TypeScript client examples:

```typescript
import { createAoudaClient } from "@aouda/client";

const client = createAoudaClient({
  serverUrl: "http://localhost:5000",
  database: "appdb",
  serverAuth: { apiKey: "mk_srv_..." },
});

// Cluster management
await client.admin.cluster.join({ primaryAddress: "192.168.1.10:5000", replicaSetName: "prod-rs" });
const config = await client.admin.cluster.getConfig();
await client.admin.cluster.patchConfig({ heartbeatIntervalMs: 3000 });
await client.admin.cluster.failover();
await client.admin.cluster.leave();

// Backup management
const result = await client.admin.backup.trigger({ incremental: true });
const list = await client.admin.backup.list();
const restored = await client.admin.backup.restore(list.backups[0].backupId);
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({ cronExpression: "0 2 * * *", incremental: true });
```

.NET client examples:

```csharp
using Aouda.Client;
using Aouda.Client.Admin;

await using var client = new AoudaClient(new AoudaClientOptions
{
    ServerUrl = "http://localhost:5000",
    DatabaseName = "appdb",
    ServerAuth = new ServerAuthOptions { ApiKey = "mk_srv_..." }
});

// Backup management
var result = await client.Backup.TriggerAsync(new TriggerBackupRequest(Incremental: true));
Console.WriteLine($"Backup {result.BackupId}: {result.NewBytes} new bytes");

var list = await client.Backup.ListAsync();
foreach (var b in list.Backups)
    Console.WriteLine($"  {b.BackupId}  {b.CreatedUtc:u}  {b.TotalBytes / 1024} KB");

var restored = await client.Backup.RestoreAsync(list.Backups[0].BackupId);
Console.WriteLine($"Restored {restored.FilesRestored} files in {restored.DurationSeconds:F1}s");

var schedule = await client.Backup.GetScheduleAsync();
await client.Backup.SetScheduleAsync(schedule with { CronExpression = "0 2 * * *" });
```

### CORS

Default policy allows `https://hub.aouda.dev` and `http://localhost:3000`. Override via `AOUDA_CORS_ORIGINS` environment variable.

---

## 9) Defaults and Zero-Config Behavior

| Scenario | What Happens |
|----------|-------------|
| `docker run aouda/server` | Single-node server, port 5000, data at `/data`, no auth, CORS allows Hub + localhost |
| `aouda start` (temp data dir) | Ephemeral data path, schema inference, auth via API |
| `aouda start` | Persistent storage in current directory, port 5000 |
| Hub unreachable | Servers continue operating normally, Studio direct-mode works |
| No backup schedule | No scheduled backups; manual trigger via API/Studio available |
| Single replica in Helm | Standalone mode, no replication env vars |
| 3 replicas in Helm | Automatic cluster bootstrap with replication |

---

## 10) Differentiators

| Capability | Aouda | Traditional |
|------------|-------|-------------|
| Single binary | `aouda start` in one binary | Separate CLI tools, agents, config generators |
| Self-hosting Hub | Hub uses Aouda as its own database | Separate management database required |
| Browser-direct | Studio connects directly to servers; Hub never proxies data | Management plane often proxies all traffic |
| Zero-config cluster | Docker Compose or Helm, automatic replication bootstrap | Manual replica set initialization required |
| AI-manageable | All admin APIs idempotent, JSON schema documented, MCP tool definitions shipped in client SDK | Manual runbooks, ad-hoc scripts |

---

## 11) Phase Coverage Matrix

| Phase | Delivered | Evidence |
|-------|----------|---------|
| P16 Epic A | CLI, Docker, cluster APIs, backup APIs, config APIs, capabilities, node info, witness, CORS, status page, server admin keys | `docs/tasks/P16/P16-SA1-CLI-Command-Layer.md` through `P16-SA5-Config-Capabilities-Node-Info.md`, `P16-SA3b-Server-Admin-Auth.md` |
| P16 Epic B | Hub backend, auth, orgs, server registry, Studio Hub integration, Docker images, deployment | `aouda-hub/docs/tasks/P16-SB1-Hub-Backend-And-Auth.md` through `P16-SB5-Deploy-Hub-And-License-Tracking.md`; `aouda-studio/docs/tasks/P16-SB3-Studio-Hub-Integration.md`, `P16-SB4-Studio-Docker-Config-Offline.md` |
| P16 Epic E | Helm chart, probes, Studio Helm, K8s docs, witness in Helm | `docs/tasks/P16/P16-SE1-Helm-Chart-And-Probes.md`, `P16-SE2-Helm-Studio-Docs-And-Witness.md` |
| P16 Epic F | Control plane, CRD, operator, K8s provisioner | `aouda-hub/docs/tasks/P16-SF1-Control-Plane-Service.md`, `P16-SF2-CRD-And-Operator.md`, `P16-SF3-Provider-Studio-Backup-And-Upgrade.md` |

---

## 12) Deferred Items

| Item | When to Implement |
|------|-------------------|
| Windows installer / MSI | When Windows-native deployment demand exists |
| Billing/payment integration | When commercial offering launches |
| Multi-cloud provider interface beyond K8s | When non-K8s deployment targets emerge |
| S3/Azure/GCS backup providers (full implementation) | Seam exists; implement when cloud storage integration needed |
| `aouda backup create/list/restore` CLI subcommands | CLI wrapping of backup REST APIs |
