---
title: "Studio"
nav_order: 15
parent: "Guides"
---

# Aouda Studio — Web Management Console

_Domain: Studio UI features, data explorer, cluster management, admin operations_
_Status: MVP Complete (2026-04-08)_
_Primary Phases: P5, P6, P9, P12, P16_
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
| Browse and query table data | §3 Data Explorer |
| Run join or aggregate queries | §4 Query Worksheet |
| Manage cluster nodes | §6 Cluster Management |
| View backups and restore | §7 Backup Management |
| Manage branches | §5 Branches |
| Connect Studio to servers | §9 Hub Integration |
| Deploy Studio | §10 Deployment |

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
| Direct | Set `NEXT_PUBLIC_AOUDA_URL` | Single server, no login required |
| Hub | Set `NEXT_PUBLIC_HUB_URL` | Login to Hub, browse org servers, switch between them |

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

## 10) Deployment

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

## 11) Admin Features

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

## 12) Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 14 (App Router) |
| UI Components | shadcn/ui |
| Styling | Tailwind CSS |
| Data Fetching | TanStack Query |
| Data Grid | TanStack Table |
| State (local) | React `useState` |
| State (global) | Zustand stores |
| State (server) | TanStack Query cache |
| Client SDK | `@aouda/client` |
| Testing | Vitest + React Testing Library |

---

## 13) Phase Coverage Matrix

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
