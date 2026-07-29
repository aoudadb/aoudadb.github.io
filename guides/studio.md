---
title: "Studio"
nav_order: 15
parent: "Guides"
---

# Aouda Studio — Web Management Console

_Domain: Studio UI features, data explorer, cluster management, admin operations_
_Status: MVP Complete + Distribution (2026-06-23)_
_Primary Phases: P5, P6, P9, P12, P16, P34_
_Repo: `aouda-studio` (Next.js / React)_

---

## 1) What This Covers

Aouda Studio is the web management console for Aouda. It provides:

- **Data Explorer** — browse, query, filter, edit, and navigate data
- **Schema Management** — view/edit tables, columns, ERD diagrams
- **Cluster Management** — node operations, topology, backup, configuration
- **Admin Console** — monitoring, logs, alerts, settings
- **Hub Integration** — team server management, authentication, multi-server switching
- **AI Integration** — natural language cluster operations

---

## 2) Start Here

| I want to... | Go to |
|---|---|
| Access Studio instantly (no install) | §10 Hosted Studio at `studio.aouda.com` |
| Connect to a server from Studio | §10.1 Connect-to-Server Dialog |
| Browse and query table data | §3 Data Explorer |
| Run join or aggregate queries | §4 Query Worksheet |
| Manage cluster nodes | §6 Cluster Management |
| View backups and restore | §7 Backup Management |
| Manage table schemas and columns | §5.5 Schema Management |
| Toggle auto-increment on a column | §5.5 Toggle AutoId |
| Manage branches | §5 Branches |
| Connect Studio to servers | §9 Hub Integration |
| Deploy Studio (self-hosted / Docker) | §11 Deployment |
| Install Aouda interactively (Aouda.Setup) | §12 Aouda.Setup Installer |

---

## 3) Data Explorer

### Table Browser

- Left sidebar: database selector, table list with row counts
- Main area: paginated data grid with virtual scrolling
- Cell editing: click to edit, inline validation, save on blur
- Row operations: insert, duplicate, delete with confirmation

### Filter Builder

Visual filter builder with all engine operators:

| Operator | UI | Wire Format |
|----------|----|-------------|
| `=`, `!=`, `>`, `>=`, `<`, `<=` | Value input | Standard comparison |
| `IN` / `NOT IN` | Multi-value chip input | Array values |
| `LIKE` | Pattern input with `%` wildcard | String pattern |
| `IS NULL` / `IS NOT NULL` | Toggle (no value input) | Null check |
| `BETWEEN` | Two value inputs (low/high) | Range check |

Filters sync bidirectionally between the visual builder and the query bar text representation.

### Sorting and Pagination

- Click column header to sort (ascending → descending → none)
- `ORDER BY` in query bar
- `LIMIT` / `OFFSET` with page navigation
- Server-side count via `POST .../query/count` (safe for large tables)

### Bulk Mutation Panel

In the table data view, the **Bulk Mutation** tab provides a guided multi-step flow for
running WHERE-based updates, deletes, and truncations from the browser:

| Step | What you do |
|------|-------------|
| 1. Operation | Choose UPDATE, DELETE, or TRUNCATE |
| 2. WHERE builder | Build a predicate using the visual filter builder (same as the read query builder) |
| 3. SET editor (UPDATE) | Per-column literal or expression (`$inc`, `$mul`, `$dec`, `$div`, `$col`, `$ifNull`) |
| 4. LIMIT (DELETE) | Optional — enables bounded rolling deletes with `hasMore` |
| 5. RETURNING | Multi-select column checklist for the response payload |
| 6. Preview | Runs `COUNT(*) WHERE …` and shows how many rows will be affected |
| 7. Confirm | Confirmation dialog: _"You are about to UPDATE/DELETE N rows. This cannot be undone."_ |
| 8. Results | Shows `rowsUpdated`/`rowsDeleted`, execution time, and RETURNING rows |

TRUNCATE requires the `Truncate` authorization scope — Studio shows a role-based warning if the
current credential lacks this scope.

See [Bulk Mutations guide](bulk-mutations.md) for the full API reference.

### Relationship Navigation

- Foreign key columns are clickable links
- Navigate to related record detail view
- Breadcrumb trail for navigation history

### Entity Detail View

Per-record detail page with:
- All fields displayed and editable
- Related records listed by foreign key
- Delete with confirmation

---

## 4) Query Worksheet

Multi-purpose query workspace for advanced operations.

### Join Query Builder

Build multi-table joins visually:
- Pick join type: INNER, LEFT, RIGHT, FULL OUTER, CROSS
- Select join key columns (supports multi-column keys)
- Post-join filters on prefixed column names (`Table.Column`)
- Chained joins (up to 8 tables)
- Results in data grid with prefixed column headers

### Aggregate Query Builder

- Aggregate functions: SUM, MIN, MAX, COUNT
- GROUP BY column selection
- Combined with WHERE filters
- Results as grouped data grid

### Expression SELECT (Computed Columns)

In the Projection section of the Query Worksheet, click **+ Computed column** to add a
server-side computed column:

1. Enter an alias name.
2. Select an expression type from the dropdown (arithmetic, coalesce, conditional).
3. Configure the operands (column references or literal values).
4. Run the query — computed columns appear as additional columns in the result grid.

Computed columns are evaluated server-side per row; they are not stored. See
[Bulk Mutations guide §8](bulk-mutations.md#8-expression-select--computed-columns).

### Free-Form Queries

Query bar accepts structured query syntax that maps directly to `@aouda/client` query builder methods. Supports all filter operators, sorting, pagination, projection.

---

## 5) Branches

Full branch management interface:

| Operation | UI |
|-----------|-----|
| List branches | Table view with name, creation date, status |
| Create branch | Dialog with name input |
| Delete branch | Confirmation dialog |
| Diff | Side-by-side view of changes between branch and main |
| Merge | Merge dialog with conflict indication |
| Branch-scoped query | Select branch context, then use data explorer normally |
| Branch-scoped insert | Insert data on a specific branch |

---

## 5.5) Schema Management

Studio's schema management surface lets you inspect and evolve table schemas entirely from the browser — no CLI or schema file required.

### Accessing the Schema View

Navigate to a table, then open the **Schema** tab. The schema view has three panels:

1. **Columns table** — all columns with type, nullability, key role, reference, and auto-increment status.
2. **Storage Policy** — per-table temperature policy (`Auto`, `HotOnly`, `ColdPreferred`).
3. **Auth Options** — authorization mode, partition-level security flag.

### The Columns Table

Each row in the columns table shows:

| Column | Description |
|--------|-------------|
| **Name** | Column name |
| **Type** | Aouda data type (e.g. `Int64`, `String`, `Timestamp`) |
| **Nullable** | Yes / No |
| **Key** | `PK (1)` for primary key with ordinal, `Partition`, `Cluster`, or `—` |
| **Reference** | Foreign key target in `→ table.column` format, or `—` |
| **Auto-increment** | `Yes` badge when `isAutoIncrement = true`, otherwise `—` |
| **Actions** | Per-row menu (see below) — shown only when the schema view is editable |

### Column Actions Menu

Click the `⋮` icon on any column row to open the actions dropdown. Available actions depend on the column:

| Action | Availability | What it does |
|--------|-------------|--------------|
| **Rename** | All columns | Opens a dialog to enter a new column name and apply it via the schema engine |
| **Toggle AutoId** | Integer columns only (`Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`) | Toggles `autoIncrement` on or off — see below |
| **Delete** | All columns | Opens a confirmation dialog and drops the column (destructive — cannot be undone) |

### Toggle AutoId — Enabling or Disabling Auto-Increment

The **Toggle AutoId** action changes the `autoIncrement` flag on an existing integer column. This avoids the "drop column and re-create" pattern that was previously required.

**How it works internally:**

Studio uses the schema export → patch → apply pattern:
1. Exports the full current schema document.
2. Flips `autoIncrement: true/false` on the target column in the document.
3. Calls `POST /api/databases/{db}/schema/apply` with the patched document (no `allowDestructive` flag — this change is never destructive).

**The Toggle AutoId dialog:**

When you click **Toggle AutoId**, a confirmation dialog opens showing:

- The target column and table names.
- The direction of the change:
  - **Manual → Auto** — the server will manage future inserts for this column.
  - **Auto → Manual** — you must supply explicit values for this column going forward.
- A yellow warning note when enabling auto-increment: _"The counter will recover from the MAX existing value in this column on first insert."_ This means the counter does not start at 1 — it starts at `MAX(existing values) + 1`, so manually-inserted IDs are never overwritten.

Click **Apply** to confirm, or **Cancel** to close without any change.

**After a successful toggle:**

- The **Auto-increment** column in the columns table updates immediately (the `Yes` badge appears or disappears).
- Studio invalidates and refetches the schema from the server so the displayed state is always current.

**Errors:**

If the apply fails (e.g. the server rejects a non-integer column, or the server has `WRITE_NOT_ALLOWED`), the error message appears inside the dialog. The dialog stays open so you can read the error and decide how to proceed. Your schema is never left in a partial or corrupted state — the apply is atomic.

**What columns are eligible?**

Only columns whose type is one of: `Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`. The "Toggle AutoId" menu item does not appear for `String`, `Double`, `Timestamp`, `Decimal`, `Guid`, or any other non-integer type. The server enforces the same constraint as an additional guard.

### Adding a Column

Click **Add column** above the columns table to open the Add Column dialog. Fill in:
- Column name
- Type (dropdown)
- Nullable flag
- Optional: primary key order, auto-increment, references

### Renaming a Column

Click `⋮` → **Rename** on the column row. Enter the new name and click Rename. The server applies the rename via the catalog.

### Deleting a Column

Click `⋮` → **Delete** on the column row. Confirm by typing the column name in the confirmation dialog. **This operation is permanent and cannot be undone.** All data in that column is lost.

### Table-Level Actions

Above the columns table, three table-level action buttons are available:

| Button | What it does |
|--------|-------------|
| **Add column** | Open the Add Column dialog |
| **Rename table** | Rename the table across the catalog |
| **Delete table** | Drop the table and all its data (confirmation required) |
| **Generate Types** | Generate TypeScript type definitions from the current schema |
| **Ask AI** | Open the AI schema assistant (requires an AI API key in Studio preferences) |

### Storage Policy

The Storage Policy card shows the current `storageTemperature` for the table:

| Value | Meaning |
|-------|---------|
| `Auto` | Engine decides hot vs. cold based on access recency and memory budget |
| `HotOnly` | Segments always stay in memory |
| `ColdPreferred` | Segments move to disk as soon as possible |

Change the value in the dropdown and click **Save** to apply the policy change. This calls `POST /api/databases/{db}/tables/{table}/policy` directly (imperative DDL, not via the declarative schema apply path).

### Schema Diff View (Migrations Page)

When you apply a schema change from the **Migrations** tab (Settings → Schema → Migrations), Studio shows a **Schema Diff View** before applying. Each planned change is color-coded:

| Color | Meaning |
|-------|---------|
| Green | Additive — safe change (e.g. `Add column`, `Add table`) |
| Red | Destructive — requires `allowDestructive` opt-in (e.g. `Drop column`, `Drop table`) |
| Blue | Alteration — safe column-level modification (e.g. `Toggle auto-increment`) |
| Muted grey | Other safe change (e.g. `Update policy`, `Update durability`) |

When the diff includes `UpdateColumnAutoIncrement` changes, the summary line shows `N column(s) altered` alongside the total change count.

---

## 6) Cluster Management

### Cluster Operations

| Operation | UI | Server API |
|-----------|-----|------------|
| Add node | Dialog: enter node address → join | `POST /admin/cluster/join` |
| Remove node | Confirmation dialog → leave | `DELETE /admin/cluster/leave` |
| Promote | Button on secondary node → trigger election | `POST /admin/cluster/promote` |
| Failover | Button on primary → step down | `POST /admin/cluster/failover` |
| Drain | Mark node as draining | `POST /admin/cluster/drain/{addr}` |

### Cluster Topology Visualization

Visual diagram showing:
- Primary, secondary, and witness nodes with role badges
- Replication lag indicators
- Status indicators (healthy, lagging, disconnected)
- Connection lines between nodes

### Node Detail View

Per-node detail page (clickable from topology):
- Version, uptime, role
- WAL position
- Memory and disk usage
- Real-time metric refresh

---

## 7) Backup Management

| Feature | UI |
|---------|-----|
| Trigger backup | Button: full or incremental |
| List backups | Table with ID, type, timestamp, size, status |
| Restore | Select backup → confirmation → progress indicator |
| Schedule | Cron builder with human-readable preview |
| Destination config | Local / S3 / Azure Blob / GCS selector |
| PITR timeline | Visual timeline of backups with restore points |

---

## 8) Configuration Editors

### Memory Budget Editor

Visual gauge showing current usage vs. budget. Slider or numeric input for immediate adjustment. Changes take effect without server restart.

### Cluster Configuration

- Replica set name
- Failover policies
- Read preference defaults

### Hot/Cold Policy Editor

Per-table storage temperature policy editor. Controls when data migrates between hot (in-memory) and cold (on-disk) storage.

### Database Options

- Max memory per database
- Replication mode
- Default policies

### Server Configuration View

Read-only display of all server configuration. Mutable settings are editable inline.

### Replication Settings

- Replication modes
- Read preference defaults

---

## 9) Hub Integration

### Two Operating Modes

| Mode | How to Activate | Behavior |
|------|----------------|----------|
| Direct | Set `NEXT_PUBLIC_AOUDA_URL` (build-time) or `AOUDA_STUDIO_DEFAULT_SERVER` (runtime) | Single server, no login required |
| Hub | Set `NEXT_PUBLIC_HUB_URL` (build-time) | Login to Hub, browse org servers, switch between them |

### Environment Variables

Studio uses two categories of environment variables:

**Build-time variables** (`NEXT_PUBLIC_*`) — baked into the JavaScript bundle at `next build`. Must be set before building the Docker image or running `npm run build`.

| Variable | Purpose | Default |
|----------|---------|---------|
| `NEXT_PUBLIC_AOUDA_URL` | Default server URL (fallback when `AOUDA_STUDIO_DEFAULT_SERVER` is not set at runtime) | `http://localhost:5000` |
| `NEXT_PUBLIC_HUB_URL` | Hub API URL; when non-empty, enables Hub login mode | `""` (disabled) |

**Runtime variables** — read by the Next.js server process at startup. Can be set on the Docker container without rebuilding the image.

| Variable | Purpose | Default |
|----------|---------|---------|
| `AOUDA_STUDIO_DEFAULT_SERVER` | Default Aouda server URL (takes precedence over `NEXT_PUBLIC_AOUDA_URL`) | — |
| `AOUDA_STUDIO_HUB_URL` | Hub API URL at runtime | — |
| `AOUDA_STUDIO_THEME` | UI theme: `system`, `light`, or `dark` | `system` |
| `AOUDA_STUDIO_CONFIG_PATH` | Path to `aouda-studio.config.json` | `./aouda-studio.config.json` |

**Resolution order** for `defaultServer`:
1. `AOUDA_STUDIO_DEFAULT_SERVER` (runtime env)
2. `defaultServer` field in `aouda-studio.config.json`
3. `NEXT_PUBLIC_AOUDA_URL` (build-time env)
4. Hard-coded default: `http://localhost:5000`

### Server Switcher

Top bar component that:
1. Shows current connected server
2. In Hub mode: dropdown with org selector and server list
3. Health check on server selection
4. Auto-applies stored vault credentials
5. Prompts for credentials when none stored

### Authentication Flow

1. Hub login (email/password → JWT tokens)
2. Server selection from registry
3. Server auth detection (health check)
4. Credential lookup in Hub vault
5. If no credential → auth dialog (API key or email/password)
6. Optional "Save to Hub" for credential vault storage

---

## 10) Hosted Studio at `studio.aouda.com`

`https://studio.aouda.com` is the publicly-hosted deployment of Aouda Studio on Vercel. It requires no installation — open it in Chrome or Edge and connect to any Aouda server running anywhere.

### 10.1 Connect-to-Server Dialog

The first time you visit `studio.aouda.com`, a **Connect to Server** dialog opens automatically. Enter the URL of your Aouda server and, if the server has authentication enabled, your API key.

| Field | Description |
|-------|-------------|
| Server URL | Full URL of the Aouda server, e.g. `http://localhost:5000` or `https://my-server.example.com` |
| API key | Server API key (`mk_srv_...`) — leave blank for unauthenticated servers |
| Remember key | Checked by default — persists the URL and key in browser `localStorage` |

Once connected, the server URL appears in the top navigation bar. Click it at any time to open the Connect dialog again and switch to a different server.

The chosen server URL and API key survive page reloads (stored in `localStorage`). They can be cleared by opening the dialog and connecting with no values, or by clearing browser storage.

### 10.2 Server URL Resolution Priority

When Studio initializes, the server URL is resolved in this order:

1. `localStorage` (set by the Connect dialog — highest priority)
2. `window.__AOUDA_STUDIO_CONFIG__.defaultServer` (runtime config from `/_studio/config`)
3. `NEXT_PUBLIC_AOUDA_URL` build-time env var
4. Hard-coded fallback: `http://localhost:5000`

This means the Connect dialog always overrides any build-time or runtime default.

### 10.3 Browser Compatibility for `localhost` Access

When using `studio.aouda.com` (HTTPS) to connect to `http://localhost:5000` (HTTP), browsers have different mixed-content policies:

| Browser | Works? | Notes |
|---------|--------|-------|
| **Chrome / Edge** | ✅ Yes | Special localhost exception for mixed content — works out of the box |
| **Firefox** | ❌ No (default) | Blocks HTTP requests from HTTPS pages; toggle `security.mixed_content.block_active_content` to override |
| **Safari** | ❌ No | Same block as Firefox |

**Recommendation:** Use Chrome or Edge for local development with `studio.aouda.com`. For Firefox/Safari localhost support, see P35+ Embedded Studio (served from the same origin, no mixed-content issue).

### 10.4 Security Model for Remote Server Access

When exposing an Aouda server over the network (to reach it from `studio.aouda.com`), use a layered approach:

**Layer 1 — Network: IP Allowlisting (recommended first line of defence)**

Restrict which IPs can reach the Aouda port. Since `studio.aouda.com` sends requests *from your browser* (not from Vercel), the source IP is your own home/office IP — the same one you would allowlist for SSH or PostgreSQL.

```bash
# Linux (ufw)
ufw allow from <your-ip> to any port 5000

# Windows Defender Firewall — inbound rule, port 5000, source = your IP
# Cloud — AWS Security Group / Azure NSG / GCP Firewall: source = your IP
```

**Layer 2 — Transport: TLS via Reverse Proxy**

Aouda.Server speaks plain HTTP. For remote access, put it behind a TLS-terminating reverse proxy:

- **Caddy** (simplest — automatic Let's Encrypt): `reverse_proxy localhost:5000`
- **nginx / Traefik**: standard proxy configs

Aouda does not manage TLS certificates. The reverse proxy is the TLS boundary.

**Layer 3 — Application: API Key Authentication**

All API endpoints require authentication when server auth is configured. Use a server API key (`mk_srv_...`) with the Connect dialog.

**Layer 4 — Optional: VPN / Zero-Trust**

For high-security environments, expose Aouda only inside a VPN (Tailscale, WireGuard, etc.) — `studio.aouda.com` works identically through a VPN tunnel.

### 10.5 CORS Configuration

Aouda.Server must allow `https://studio.aouda.com` as a browser origin. The defaults already include it:

| Config state | Allowed browser origins |
|---|---|
| Nothing set (defaults) | `https://hub.aouda.dev`, `https://studio.aouda.com`, plus optional `AOUDA_STUDIO_ORIGIN` |
| `AOUDA_CORS_ORIGINS` set | **Only** the comma-separated list — defaults NOT merged in |
| `AOUDA_STUDIO_ORIGIN` set (no `CorsOrigins`) | Defaults **plus** the custom origin appended |

**Important pitfall:** If you set `AOUDA_CORS_ORIGINS` and omit `https://studio.aouda.com`, browsers at `studio.aouda.com` cannot call your server (CORS preflight fails).

```bash
# Correct: include all origins you need
AOUDA_CORS_ORIGINS=https://studio.aouda.com,https://hub.aouda.dev,http://localhost:3000

# Alternative: add one extra origin without replacing defaults
AOUDA_STUDIO_ORIGIN=http://localhost:3000
```

For local development with a custom Studio port, use `AOUDA_STUDIO_ORIGIN` to keep `studio.aouda.com` in the defaults while adding localhost.

### 10.6 `GET /_studio/config` Endpoint

A public (no auth required) endpoint returns static bootstrap metadata:

```json
{ "serverUrl": "/", "theme": "system" }
```

This is used by the future embedded Studio (P35+) to configure itself when served from the same origin as the server. In P34 it establishes the routing and public-route plumbing. It is always safe to expose; it reveals no data or configuration beyond the JSON above.

---

## 11) Deployment

### Docker

```bash
docker run -p 3000:3000 \
  -e AOUDA_STUDIO_DEFAULT_SERVER=http://aouda:5000 \
  aouda/studio
```

Fully self-contained: no external CDN, font, or icon dependencies. Works air-gapped.

### Docker Compose

Included in Aouda server's `docker-compose.yml` and `docker-compose.cluster.yml`.

### Kubernetes Helm

Enable in Helm chart: `studio.enabled=true`. Auto-configured to connect to the Aouda headless service.

### Vercel (studio.aouda.com)

The `aouda-studio` repository is configured for Vercel deployment:

- `vercel.json` configures the install command to resolve `@aouda/client` from npm (not from the local `file:` path used in development).
- `NEXT_STANDALONE_OUTPUT` is not set on Vercel (uses Vercel's Next.js runtime instead of standalone Docker output).
- No `NEXT_PUBLIC_AOUDA_URL` is set on Vercel — users connect at runtime via the Connect dialog.

Environment variables for the Vercel project:

| Variable | Required | Description |
|----------|----------|-------------|
| `AOUDA_CLIENT_PACKAGE` | Optional | npm version of `@aouda/client` to use (default: `latest`) |
| `NEXT_PUBLIC_HUB_URL` | No | Leave empty for direct mode at `studio.aouda.com` |

Manual ops required once per deployment: create the Vercel project, attach the `studio.aouda.com` custom domain, and set `AOUDA_CLIENT_PACKAGE` if pinning a version.

### Local Config File

`aouda-studio.config.json` provides server connections when Hub is unavailable:
```json
{
  "servers": [
    { "name": "Local", "url": "http://localhost:5000" }
  ]
}
```

---

## 12) Aouda.Setup Installer

`Aouda.Setup` is a zero-dependency .NET 8 console app (published as a single self-contained binary) that replaces the manual PowerShell/bash install scripts with an interactive, double-click experience.

### When to Use Aouda.Setup vs. Install Scripts

| Scenario | Use |
|----------|-----|
| First-time install by a developer or end user | `Aouda.Setup.exe` / `aouda-setup` |
| CI/CD automation, scripted deploy pipelines | `scripts/install-aouda.ps1` / `install-aouda.sh` (unchanged) |
| Container / Kubernetes deployment | Docker / Helm (no install script needed) |

### Interactive Prompt Sequence

Double-click `Aouda.Setup.exe` (Windows) or run `./aouda-setup` (Linux). The app walks you through five prompts with sensible defaults:

```
Welcome to Aouda Setup
======================
Install mode:
  [1] Windows Service / systemd (recommended — starts automatically with OS)
  [2] Manual / on-demand (run with: Aouda.Server start)
> 1

Port [5433]:
> 

Install directory [C:\Program Files\Aouda]:
> 

Data directory [C:\ProgramData\Aouda\data]:
> 

Admin email:
> admin@example.com

Admin password (input hidden):
> 
```

Press Enter to accept defaults. The setup app then:
1. Copies binaries to the install directory (skips any `appsettings*.json` in the release zip)
2. Bootstraps the first admin account (`Aouda.Server create-admin` into the data directory)
3. Registers and starts the Windows Service (or systemd unit) with `--data-path` and `--port` on the command line
4. Creates Start Menu shortcut (Windows) or `.desktop` shortcut (Linux)
5. Prints the completion banner

No `appsettings.json` is created. End users do not need to know about ASP.NET configuration files. See [Server configuration](server-configuration.md).

### Completion Banner

```
=============================================
Aouda is running!

Server URL : http://localhost:5433
Studio     : http://localhost:5433  (future embedded mode)
Cloud      : https://studio.aouda.com → connect to http://localhost:5433
API key    : aouda_sk_xxxxxxxxxxxx

Recommended browser for localhost: Chrome or Edge
Store your API key in a secret manager now.
=============================================
```

The API key is a long-lived server admin key (`mk_srv_...`). Copy it to a secret manager immediately — it is not stored anywhere after the banner is dismissed.

### Service Registration Details

**Windows (Windows Service via `sc.exe`):**
- Service name: `Aouda`
- Start type: automatic
- Binary path: `"C:\Program Files\Aouda\Aouda.Server.exe" --data-path "C:\ProgramData\Aouda\data" --port 5433`
- If the service already exists, `sc.exe config` updates the binary path before starting

**Linux (systemd):**
- Unit file: `/etc/systemd/system/aouda.service`
- `WorkingDirectory`: install directory
- `ExecStart`: `/opt/aouda/Aouda.Server --data-path /var/lib/aouda --port 5433`
- `User=aouda`, `Group=aouda`
- Data/log directories created with correct ownership (`chown -R aouda:aouda`)
- `systemctl daemon-reload && systemctl enable aouda && systemctl restart aouda`

Requires elevation: run as Administrator on Windows, `sudo` on Linux.

### Shortcut Details

| Platform | Shortcut location | Target URL |
|----------|-------------------|------------|
| Windows | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Aouda Studio.url` | `http://localhost:<port>` |
| Linux | `~/.local/share/applications/aouda.desktop` | `xdg-open http://localhost:<port>` |

The shortcut points to the **local server URL** (not `studio.aouda.com`). In direct-mode Docker or future embedded Studio, the same URL serves Studio. For the hosted Studio, visit `studio.aouda.com` and use the Connect dialog.

### Manual / On-Demand Install Mode

If you select mode `[2]` (manual), `Aouda.Setup` skips service registration and instead prints how to start the server manually:

```
Aouda installed (manual / on-demand mode).

To start the server:
  Windows: "C:\Program Files\Aouda\Aouda.Server.exe" --data-path "C:\ProgramData\Aouda\data" --port 5433
  Linux:   /opt/aouda/Aouda.Server --data-path /var/lib/aouda --port 5433

Server URL : http://localhost:5433  (once running)
Cloud      : https://studio.aouda.com → connect to http://localhost:5433
```

### Admin Bootstrap Logic

`Aouda.Setup` bootstraps the admin account using this sequence:

1. Invokes `Aouda.Server create-admin --email ... --password ... --data ...` as a subprocess (no HTTP required — writes directly to the data directory).
2. Waits for `GET /health` to return 200 (up to 30 retries × 2 seconds = 60 seconds).
3. Calls `POST /api/auth/setup` with email + password. If the server returns 403 `ALREADY_CONFIGURED` (admin already exists), falls back to `POST /api/auth/signin`.
4. Uses the returned token to call `POST /api/auth/admin/keys` and obtain a server admin API key.

### Existing Install Scripts (Preserved)

`scripts/install-aouda.ps1` (Windows) and `scripts/install-aouda.sh` (Linux) are unchanged. They remain the preferred tool for CI/CD pipelines and scripted deployments where non-interactive, parameter-driven installs are needed.

---

## 13) Admin Features

### Log Viewer

- Server log viewer with level filtering (Debug, Info, Warning, Error)
- Real-time streaming via SSE
- Searchable log history

### Slow Query Log

View slow queries with timing information and query details.

### Alert Configuration

- Define alerts on metrics thresholds
- Alert history with timestamps and resolution status

### Connection Monitor

Active connections and their status.

### Multi-Server Dashboard

In Hub mode: aggregate health overview across all registered servers.

### Role-Based UI Visibility

Navigation items and features gated by user role (owner/admin/member/viewer).

### API Key Authentication

Connect to password-protected servers using API keys from Studio settings.

### Server Admin Key Management

View, create, and revoke server admin API keys from Studio settings/auth page.

### Materialized Queries Browser

- List materialized queries with freshness status (up-to-date, stale, processing)
- Query materialized query results directly
- Drop materialized queries

---

## 14) Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 14 (App Router) |
| UI Components | shadcn/ui |
| Styling | Tailwind CSS |
| Data Fetching | TanStack Query |
| Data Grid | Glide Data Grid (`@glideapps/glide-data-grid`) |
| State (local) | React `useState` |
| State (global) | Zustand stores |
| State (server) | TanStack Query cache |
| Client SDK | `@aouda/client` |
| Testing | Vitest + React Testing Library |

---

## 15) Phase Coverage Matrix

| Phase | Delivered | Key Task Docs |
|-------|----------|---------------|
| P5 | App shell, data grid, filter builder, cell editing, row ops, relationship nav, entity detail, schema views, ERD, dashboard | `aouda-studio/docs/tasks/P5-*` |
| P6 | Multi-database support, database management UI | `aouda-studio/docs/tasks/P6-*` |
| P9 | Server settings, database settings, table policy editor, enhanced dashboard, monitoring, cluster/replication pages, auth placeholders, backup placeholder | `aouda-studio/docs/tasks/P9-*` |
| P12 | Users panel, roles/permissions panel, sessions/audit log panel | `aouda-studio/docs/tasks/P12-*` |
| P16 Epic B | Hub integration, server switcher, connection auth, Docker image, config file, offline mode, env vars | `aouda-studio/docs/tasks/P16-SB3-*`, `P16-SB4-*` |
| P16 Epic C | Cluster ops (add/remove/promote/failover), node detail, backup management, memory editor, topology viz, all config editors | `aouda-studio/docs/tasks/P16-SC1-*` through `P16-SC3-*` |
| P16 Epic D | Log viewer, query worksheet, role-based UI, API key auth, settings, alerts, slow query, PITR, join UI, aggregate UI, branches UI, advanced filters, materialized queries, admin keys | `aouda-studio/docs/tasks/P16-SD1-*` through `P16-SD5-*` |
| P16 Epic F | Studio cloud integration (projects, clusters) | `aouda-studio/docs/tasks/P16-SF3-*` |
| P16 Epic G | Natural language cluster operations | `aouda-studio/docs/tasks/P16-SG2-*` |
|| P34 | Hosted Studio at `studio.aouda.com` (Vercel), Connect-to-Server dialog, localStorage persistence, first-run detection, CORS for `studio.aouda.com`, `/_studio/config` endpoint, `Aouda.Setup` cross-platform installer | `aouda/docs/tasks/P34/StudioDist-*` |
