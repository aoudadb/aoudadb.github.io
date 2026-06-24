---
title: "Server configuration"
parent: Guides
nav_order: 2
---

# Server configuration

This page is the **canonical reference** for how the Aouda server loads settings, what overrides what, and what survives a process restart.

{: .important }
**End users installing via `Aouda.Setup` or `install-aouda.ps1` do not need `appsettings.json`.** Install tools register the Windows Service or systemd unit with `--data-path` and `--port` on the command line. Operational tuning is done in Studio or via the `/admin/config` API.

---

## 1) Configuration layers

Aouda settings come from several layers. Think of them as separate concerns:

| Layer | Purpose | Typical audience | Shipped in release zip? |
| --- | --- | --- | --- |
| **Code defaults** | Safe baseline when nothing else is set (`AoudaServerOptions` in source) | Everyone (implicit) | N/A (compiled in) |
| **Install bootstrap** | Where data lives and which port to listen on | Setup / install scripts | Written into the **service command line**, not a config file |
| **Optional operator config** | `appsettings.json`, `appsettings.{Environment}.json` | Developers, Docker/K8s operators | **No** — not included in Windows release publish |
| **Environment variables** | `AOUDA_*` overrides for containers and CI | DevOps | Set on the service, container, or pod |
| **CLI flags** | `--data-path`, `--port`, `--join`, etc. | Install scripts, manual starts, service `binPath` | Highest precedence at startup |
| **Data-directory files** | `backup-config.json`, `cluster-state.json` | Runtime / API / Studio | Created under `{DataPath}` when changed |
| **Runtime API** (`PATCH /admin/config`) | Memory budgets, backup schedule, log level | Studio, automation | See §4 — not all fields persist |

**Install directory vs data directory:** users may copy binaries to any folder (`C:\Program Files\Aouda`, `D:\Apps\Aouda`, `/opt/aouda`, …). That choice does **not** determine where databases live. The **data directory** (chosen at install) holds all persistent engine state.

---

## 2) Startup binding priority (lowest → highest)

When the server process starts, `AoudaServerOptions` and related host settings are built from ASP.NET Core configuration sources in this order. **Later sources override earlier ones:**

```
1. C# property defaults (AoudaServerOptions)
2. appsettings.json          (optional; content root — see §3)
3. appsettings.{Environment}.json   (optional; e.g. Production)
4. User secrets                (Development only)
5. Environment variables       (unprefixed ASP.NET / hosting vars)
6. Command-line arguments      (generic host args from CreateBuilder)
7. AOUDA_* environment variables   (mapped into Aouda: section — see §2.1)
8. Mapped CLI flags              (--data-path, --port, --bind, --join, …)
```

**Practical rule:** for production service installs, bootstrap values come from the **service command line** (layer 8). For Docker/Kubernetes, use **`AOUDA_*` env vars** (layer 7) — see §2.1 for naming rules. For local `dotnet run` / `aouda start` from a dev tree, an optional **`appsettings.json` beside the project** (layers 2–3) is convenient.

Default listen port in **code** is `5000`. **Install tools default to `5433`** to avoid clashing with other local dev servers — that value is passed via `--port` on the registered service, not via a shipped config file.

---

## 2.1) Environment variable naming (`AOUDA_*`)

All server settings exposed through `AoudaServerOptions` can be set with environment variables prefixed **`AOUDA_`**. The server maps them into the `Aouda:` configuration section (same keys as `appsettings.json` and CLI flags).

### Rules

| Rule | Example |
| --- | --- |
| **Prefix** | Every server config var starts with `AOUDA_` |
| **Top-level keys** | Flat name after the prefix — no extra underscores in the property name | `AOUDA_PORT`, `AOUDA_DATAPATH`, `AOUDA_BIND` |
| **Nested keys** | Use **`__` (double underscore)** between each level | `AOUDA_MEMORY__MAXTOTALRAMBYTES`, `AOUDA_ARCHIVE__DESTINATION` |
| **Single `_` is not nesting** | `AOUDA_MEMORY_MAXHOTBYTES` does **not** map to `Memory:MaxHotBytes` — use `AOUDA_MEMORY__MAXHOTBYTES` | |
| **Case** | Names are case-insensitive; values bind case-insensitively | `AOUDA_port=5433` works |
| **CLI wins** | Env vars override appsettings; CLI flags override env vars | |

### Mapping examples

| Environment variable | Config key | Notes |
| --- | --- | --- |
| `AOUDA_PORT` | `Aouda:Port` | |
| `AOUDA_DATAPATH` | `Aouda:DataPath` | **Canonical** name in server docs |
| `AOUDA_DATA_PATH` | `Aouda:DataPath` | **Alias** — used by Docker, Kubernetes, and embedded client |
| `AOUDA_BIND` | `Aouda:Bind` | e.g. `0.0.0.0:5433` |
| `AOUDA_MEMORY__MAXTOTALRAMBYTES` | `Aouda:Memory:MaxTotalRamBytes` | |
| `AOUDA_MEMORY__MAXHOTBYTES` | `Aouda:Memory:MaxHotBytes` | |
| `AOUDA_ARCHIVE__ENABLED` | `Aouda:Archive:Enabled` | |
| `AOUDA_ARCHIVE__DESTINATION` | `Aouda:Archive:Destination` | |
| `AOUDA_REPLICASET__NAME` | `Aouda:ReplicaSet:Name` | |
| `AOUDA_REPLICASET__MEMBERS__0` | `Aouda:ReplicaSet:Members:0` | Array index |
| `AOUDA_AUTH__EMAIL__PROVIDER` | `Aouda:Auth:Email:Provider` | e.g. `sendgrid`, `console` |

```bash
# Docker / Kubernetes — typical bootstrap
AOUDA_DATA_PATH=/data          # alias; same as AOUDA_DATAPATH
AOUDA_PORT=5433

# Nested settings — note double underscore between levels
AOUDA_MEMORY__MAXTOTALRAMBYTES=8589934592
AOUDA_ARCHIVE__DESTINATION=s3://bucket/backups
```

### Variables handled outside `AoudaServerOptions`

Some `AOUDA_*` variables are read by **custom code**, not through the main options binder:

| Variable | Purpose | Read by |
| --- | --- | --- |
| `AOUDA_CORS_ORIGINS` | Replace default CORS origin list | `ServerHostRunner` |
| `AOUDA_STUDIO_ORIGIN` | Append one CORS origin to defaults | `ServerHostRunner` |
| `AOUDA_SCHEMA_INFERENCE_MODE` | Schema inference mode override | `SchemaOptionsEnvOverlay` |

### Variables for other components (not server config)

These use the `AOUDA_` prefix but are **not** `AoudaServerOptions`:

| Variable | Component |
| --- | --- |
| `AOUDA_SERVER`, `AOUDA_URL`, `AOUDA_DATABASE`, `AOUDA_ENVIRONMENT` | `aouda` CLI |
| `AOUDA_DATA_PATH`, `AOUDA_DATABASE` | Embedded client (`AoudaEmbedded`) — `AOUDA_DATA_PATH` is also accepted by the server as an alias |
| `AOUDA_HUB_*` | Aouda Hub |
| `AOUDA_STUDIO_*` | Aouda Studio |
| `AOUDA_TEST_*` | Integration tests only |

CLI flag mappings include:

| Flag | Config key |
| --- | --- |
| `--data-path` / `--data-dir` / `-d` | `Aouda:DataPath` |
| `--port` / `-p` | `Aouda:Port` |
| `--bind` | `Aouda:Bind` |
| `--join` | `Aouda:Join` |
| `--max-memory` / `-m` | `Aouda:Memory:MaxTotalRamBytes` |

---

## 3) Install bootstrap (Setup and install scripts)

`Aouda.Setup` and `scripts/install-aouda.ps1` / `install-aouda.sh` do **not** write `appsettings.json`.

They:

1. Copy **binaries only** to the install directory (any path the operator chooses).
2. Create the **data directory** (default `C:\ProgramData\Aouda\data` on Windows, `/var/lib/aouda` on Linux).
3. Bootstrap the first admin into the data directory (`create-admin`).
4. Register the OS service with bootstrap flags embedded in the service definition.

**Windows Service** (`binPath` / `BinaryPathName`):

```text
"C:\Program Files\Aouda\Aouda.Server.exe" --data-path "C:\ProgramData\Aouda\data" --port 5433
```

**Linux systemd** (`ExecStart`):

```text
/opt/aouda/Aouda.Server --data-path /var/lib/aouda --port 5433
```

**Manual / on-demand mode** (Setup option `[2]`): the completion banner prints the same flags for a foreground start — no config file required.

To change data path or port after install, update the **service command line** (Services.msc, `sc.exe config`, or edit the systemd unit) and restart the service. You do not need to edit a JSON file.

---

## 4) What survives a restart?

| Setting | How it is set | Survives process restart? | Survives binary upgrade? |
| --- | --- | --- | --- |
| **Data path** | Service CLI / env / optional appsettings | Yes (service definition or env) | Yes (data dir unchanged) |
| **Listen port** | Service CLI / env / optional appsettings | Yes | Yes |
| **Memory budgets** | `PATCH /admin/config` | **No** — in-memory only; reverts to startup-bound values | Reverts unless set in env/CLI/appsettings |
| **Log level** (`/admin/config`) | `PATCH /admin/config` | **No** — in-memory only | Reverts |
| **Backup schedule** | `PATCH /admin/config` or `/admin/backup` | **Yes** — persisted to `{DataPath}/backup-config.json` | Yes |
| **Cluster topology** | `POST /admin/cluster/join` etc. | **Yes** — `{DataPath}/cluster-state.json` | Yes |
| **Drain flags** | `PATCH /admin/cluster/...` | **No** — in-memory only | Lost on restart |
| **Database data, WAL, catalogs** | Engine | Yes (under `{DataPath}`) | Yes |
| **Auth users, API keys** | Engine (in data dir) | Yes | Yes |
| **Env vars / CLI on service** | OS service, container, K8s manifest | Yes | Yes until manifest changed |
| **Optional appsettings.json** | Operator-placed file | Yes (re-read each start) | Yes if file kept outside binary folder |

{: .note }
Runtime config from `PATCH /admin/config` is **not** written back to `appsettings.json` or environment variables. Only backup schedule changes that go through `RuntimeBackupConfig` are persisted to disk automatically.

---

## 5) Cluster configuration overlay

Replica-set membership follows a **separate** priority chain at startup (see `ReplicationHostedService`):

```
1. In-memory ActiveConfig     (same process — restart API)
2. {DataPath}/cluster-state.json   (API join / cluster lifecycle — wins over static config)
3. --join CLI flag            (first boot; may write cluster-state.json)
4. Aouda:ReplicaSet in startup config (appsettings / env / CLI — static operator config)
5. Standalone mode            (no replica set)
```

If `cluster-state.json` exists, it **overrides** static `Aouda:ReplicaSet` from appsettings or env on every restart until deleted via the cluster API.

---

## 6) Backup destination resolution

When a backup runs, destination resolution order is:

```
1. Explicit destination on the backup request
2. {DataPath}/backup-config.json  (from API / Studio / PATCH /admin/config)
3. Aouda:Archive:Destination from startup config (env / appsettings / CLI)
4. {DataPath}/backups             (implicit local fallback for on-demand triggers)
```

---

## 7) When to use `appsettings.json`

| Scenario | Recommendation |
| --- | --- |
| **Windows release install (Setup / PS1)** | Do not use — service CLI flags only |
| **Local development (`aouda start`, `dotnet run`)** | Optional `appsettings.json` in the working directory is fine |
| **Docker / Kubernetes** | Prefer `AOUDA_*` env vars in the manifest |
| **Replication static config** | Env vars or operator-managed `appsettings.json` mounted beside the binary |
| **Auth notification providers (SendGrid, etc.)** | Env vars or appsettings on the **server** host |
| **Your ASP.NET application's JWT settings** | Your app's `appsettings.Development.json` — **not** the Aouda server config |

The Windows **release publish output does not include** `appsettings.json`. Defaults are in code; install tools pass bootstrap flags on the service command line.

---

## 8) Quick reference by role

| Role | What to configure | Where |
| --- | --- | --- |
| **End user (Setup installer)** | Port, data folder, admin account | Interactive prompts only |
| **App developer** | API URL, API keys, auth DB | Your application config + Studio |
| **Operator** | Memory, backups, cluster | Studio or `/admin/*` APIs |
| **DevOps / CI** | Image env vars, Helm values, service `binPath` | `AOUDA_*`, CLI flags, K8s manifests |
| **Engine contributor** | Full surface while hacking | Repo `src/Aouda.Server/appsettings.json` (dev only) |

---

## Related docs

- [Server multi-database](server-multi-database.md) — per-database config keys and API surface
- [Studio guide — Aouda.Setup](studio.md#12-aoudasetup-installer) — interactive install sequence
- [Deployment](../deployment/) — Docker, Kubernetes, Windows Service
- [Replication](replication.md) — replica set and archive settings
- [Backup](backup.md) — archive and scheduled backup configuration
