---
title: "TypeScript Client"
nav_order: 1
parent: "Clients"
---

# Aouda TypeScript Client SDK (`@aouda/client`)

_Domain: TypeScript client library, CLI, MCP tools_
_Status: MVP Complete (2026-04-08)_
_Primary Phases: P5, P10, P12, P14, P15, P16_
_Repo: `aouda-client-ts`_

---

## 1) What This Covers

`@aouda/client` is the official TypeScript client library for Aouda. It provides:

- **Type-safe query builder** — fluent API for queries, joins, aggregates, filters
- **CRUD operations** — insert, update, delete with full type safety
- **Schema management** — create/alter tables, type generation CLI
- **Branch operations** — create, delete, diff, merge, branch-scoped queries
- **Real-time streaming** — WebSocket subscriptions for live data
- **Admin API coverage** — health, metrics, replication, cluster, backup, config, node
- **Authentication** — session auth, API key auth, token management
- **MCP tools** — AI-consumable tool definitions for cluster management
- **CLI** — type generation, schema seed, and more

---

## 2) Start Here

| I want to... | Go to |
|---|---|
| Install and connect | §3 Getting Started |
| Query data with filters | §4 Query Builder |
| Run joins across tables | §5 Joins |
| Run aggregate queries | §6 Aggregates |
| Insert/update/delete data | §7 CRUD |
| Manage schemas | §8 Schema |
| Work with branches | §9 Branches |
| Stream real-time changes | §10 Streaming |
| Manage cluster via API | §11 Admin APIs |
| Use MCP tools for AI | §12 MCP Tools |

---

## 3) Getting Started

### Installation

```bash
npm install @aouda/client
```

### Basic Connection

```typescript
import { AoudaClient } from '@aouda/client';

const client = new AoudaClient({
  url: 'http://localhost:5000',
  database: 'mydb',
});
```

### With Authentication

```typescript
// API key auth
const client = new AoudaClient({
  url: 'http://localhost:5000',
  database: 'mydb',
  apiKey: 'mk_app_abc123...',
});

// Session auth
const client = new AoudaClient({
  url: 'http://localhost:5000',
  database: 'mydb',
});
await client.auth.login({ email: 'user@example.com', password: 'secret' });
```

---

## 4) Query Builder

### Basic Query

```typescript
const users = await client.table('users')
  .where(w => w.field('active').eq(true))
  .orderBy('name', 'asc')
  .limit(10)
  .execute();
```

### Projection

```typescript
const names = await client.table('users')
  .select(['name', 'email'])
  .execute();
```

### Pagination

```typescript
const page2 = await client.table('users')
  .orderBy('id', 'asc')
  .limit(20)
  .offset(20)
  .execute();
```

### Count

```typescript
const count = await client.table('users')
  .where(w => w.field('active').eq(true))
  .count();
```

### All Filter Operators

```typescript
// Comparison
w.field('age').gt(18)
w.field('age').gte(18)
w.field('age').lt(65)
w.field('age').lte(65)
w.field('name').eq('Alice')
w.field('name').ne('Bob')

// Extended operators (P16)
w.field('role').in(['admin', 'owner'])
w.field('status').notIn(['deleted', 'archived'])
w.field('name').like('A%')
w.field('email').isNull()
w.field('email').isNotNull()
w.field('age').between(18, 65)
```

### Nested Groups

```typescript
const results = await client.table('users')
  .where(w => w
    .field('active').eq(true)
    .and(g => g
      .field('role').eq('admin')
      .or()
      .field('role').eq('owner')
    )
  )
  .execute();
```

---

## 5) Joins

All five join types are supported with full post-join operations.

### Inner Join

```typescript
const orders = await client.table('orders')
  .join('customers', { left: 'customerId', right: 'id' })
  .select(['orders.id', 'customers.name', 'orders.total'])
  .where(w => w.field('orders.total').gt(100))
  .orderBy('orders.total', 'desc')
  .limit(50)
  .execute();
```

### Left Join

```typescript
const all = await client.table('customers')
  .leftJoin('orders', { left: 'id', right: 'customerId' })
  .execute();
```

### Right Join

```typescript
const result = await client.table('orders')
  .rightJoin('products', { left: 'productId', right: 'id' })
  .execute();
```

### Full Outer Join

```typescript
const result = await client.table('students')
  .fullJoin('enrollments', { left: 'id', right: 'studentId' })
  .execute();
```

### Cross Join

```typescript
const result = await client.table('colors')
  .crossJoin('sizes')
  .execute();
```

### Multi-Column Join Keys

```typescript
const result = await client.table('orders')
  .join('shipments', [
    { left: 'orderId', right: 'orderId' },
    { left: 'warehouseId', right: 'warehouseId' },
  ])
  .execute();
```

### Chained Joins (up to 8 tables)

```typescript
const result = await client.table('orders')
  .join('customers', { left: 'customerId', right: 'id' })
  .join('products', { left: 'orders.productId', right: 'id' })
  .join('categories', { left: 'products.categoryId', right: 'id' })
  .select(['orders.id', 'customers.name', 'products.name', 'categories.name'])
  .execute();
```

### Post-Join Operations

All standard operations work after joins:
- `select([...])` — project specific columns
- `where(w => ...)` — filter on any column (use prefixed names)
- `orderBy(column, direction)` — sort on any column
- `limit(n)` / `offset(n)` — pagination
- Aggregates — sum, min, max, count, groupBy

---

## 6) Aggregates

### Simple Aggregates

```typescript
const total = await client.table('orders')
  .sum('amount')
  .execute();

const oldest = await client.table('users')
  .min('createdAt')
  .execute();

const maxPrice = await client.table('products')
  .max('price')
  .execute();
```

### Group By

```typescript
const salesByCustomer = await client.table('orders')
  .sum('amount')
  .groupBy('customerId')
  .execute();

const countByStatus = await client.table('tasks')
  .count()
  .groupBy('status', 'priority')
  .execute();
```

---

## 7) CRUD Operations

### Insert

```typescript
await client.table('users').insert({
  name: 'Alice',
  email: 'alice@example.com',
  active: true,
});

// Bulk insert
await client.table('events').insertMany([
  { type: 'click', timestamp: new Date() },
  { type: 'view', timestamp: new Date() },
]);
```

### Update

```typescript
await client.table('users')
  .where(w => w.field('id').eq(123))
  .update({ active: false });
```

### Delete

```typescript
await client.table('users')
  .where(w => w.field('id').eq(123))
  .delete();
```

---

## 8) Schema Management

### Table Operations

```typescript
// List tables
const tables = await client.tables.list();

// Create table
await client.tables.create({
  name: 'users',
  columns: [
    { name: 'id', type: 'int', isPrimaryKey: true },
    { name: 'name', type: 'string' },
    { name: 'email', type: 'string' },
  ],
});

// Alter table
await client.tables.alter('users', {
  addColumns: [{ name: 'phone', type: 'string' }],
});
```

### Type Generation CLI

```bash
npx @aouda/client generate --url http://localhost:5000 --database mydb --output ./types
```

Generates TypeScript interfaces from Aouda table schemas.

### Schema Seed CLI

```bash
npx @aouda/client schema seed --file seed.json --database mydb --url http://localhost:5000
```

---

## 9) Branches

```typescript
// List branches
const branches = await client.branches.list();

// Create branch
await client.branches.create('feature-x');

// Query on branch
const data = await client.table('users')
  .onBranch('feature-x')
  .execute();

// Insert on branch
await client.table('users')
  .onBranch('feature-x')
  .insert({ name: 'Test User' });

// Diff
const diff = await client.branches.diff('feature-x');

// Merge
await client.branches.merge('feature-x');

// Delete
await client.branches.delete('feature-x');
```

---

## 10) Real-Time Streaming

### WebSocket Subscriptions

```typescript
const subscription = await client.table('events')
  .subscribe({
    onInsert: (row) => console.log('New:', row),
    onUpdate: (row) => console.log('Updated:', row),
    onDelete: (row) => console.log('Deleted:', row),
  });

// Later: unsubscribe
subscription.unsubscribe();
```

---

## 11) Admin APIs

Full typed `client.admin.*` surface covering all server management operations.

### Health and Metrics

```typescript
const health = await client.admin.health();
const metrics = await client.admin.metrics();
const info = await client.admin.server.info();
```

### Replication

```typescript
const status = await client.admin.replication.status();
const topology = await client.admin.replication.topology();
const coverage = await client.admin.replication.coverage();
```

### Cluster Management (P16)

```typescript
// Join cluster
await client.admin.cluster.join({
  replicaSetName: 'my-cluster',
  primaryAddress: '192.168.1.10:5000',
  thisNodeAddress: '192.168.1.11:5001',
});

// Leave cluster
await client.admin.cluster.leave();

// Promote secondary
await client.admin.cluster.promote();

// Failover primary
await client.admin.cluster.failover();

// Drain node
await client.admin.cluster.drain('192.168.1.12:5002');

// Get/patch cluster config
const config = await client.admin.cluster.getConfig();
await client.admin.cluster.patchConfig({ heartbeatIntervalMs: 2000 });
```

### Backup Management (P16)

```typescript
// Trigger backup
await client.admin.backup.trigger({ incremental: true });

// List backups
const backups = await client.admin.backup.list();

// Restore
await client.admin.backup.restore(backupId);

// Schedule
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({ cron: '0 2 * * *' });
```

### Configuration (P16)

```typescript
const config = await client.admin.config.get();
await client.admin.config.patch({ memoryBudgetMb: 4096, loggingLevel: 'Warning' });
const schema = await client.admin.config.schema();
```

### Node Info (P16)

```typescript
const node = await client.admin.node.get();
const logs = await client.admin.node.logs({ level: 'Error', limit: 100 });

// Stream logs (SSE)
const stream = client.admin.node.streamLogs({ level: 'Warning' });
for await (const entry of stream) {
  console.log(entry);
}
```

### Capabilities (P16)

```typescript
const caps = await client.admin.capabilities();
// caps.mode: 'standalone' | 'clustered'
// caps.backupProviders: ['local']
// caps.version: '0.1.0'
```

---

## 12) MCP Tools for AI Agents

`@aouda/client` ships MCP-consumable tool definitions in `src/mcp/`. These are not a standalone MCP server — they are tool objects that hosts (Cursor, custom agents, Studio) can register with an MCP implementation.

### Available Tools

| Tool Name | Purpose |
|-----------|---------|
| `aouda_cluster_status` | Cluster health and topology |
| `aouda_cluster_nodes` | Per-node details |
| `aouda_backup_trigger` | Trigger backup |
| `aouda_backup_list` | List backups |
| `aouda_backup_restore` | Restore from backup |
| `aouda_cluster_add_node` | Join node to cluster |
| `aouda_cluster_remove_node` | Leave cluster |
| `aouda_cluster_promote` | Promote secondary |
| `aouda_cluster_failover` | Step down primary |

### Usage

```typescript
import { createAoudaClusterMcpToolSet } from '@aouda/client';

const tools = createAoudaClusterMcpToolSet(client);
// tools is an array of { name, description, inputSchema, execute } objects
// Register with your MCP host implementation
```

Each tool has:
- Stable name (e.g. `aouda_cluster_status`)
- JSON Schema `inputSchema`
- `execute(params)` handler calling typed `client.admin.*` methods

Documentation: `aouda-client-ts/docs/dev/MCP-Cluster-Tools.md`.

---

## 13) Materialized Queries

```typescript
// List materialized queries
const queries = await client.materializedQueries.list();

// Create
await client.materializedQueries.create({
  name: 'active_users_summary',
  sourceTable: 'users',
  query: { where: { active: true } },
});

// Check status
const status = await client.materializedQueries.status('active_users_summary');
// status.freshness: 'up-to-date' | 'stale' | 'processing'

// Query results
const results = await client.materializedQueries.query('active_users_summary', {
  limit: 100,
});

// Drop
await client.materializedQueries.drop('active_users_summary');
```

---

## 14) Columnar Output

For high-performance data processing, bypass row conversion:

```typescript
const columnar = await client.table('events')
  .select(['timestamp', 'value'])
  .limit(10000)
  .toColumnar();

// columnar.columns: ['timestamp', 'value']
// columnar.types: ['datetime', 'double']
// columnar.data: [[...timestamps], [...values]]
// columnar.rowCount: 10000
```

---

## 15) Phase Coverage Matrix

| Phase | Delivered | Key Capability |
|-------|----------|----------------|
| P5 | Core client, query builder, CRUD, schema, type generation CLI | Foundation |
| P6 | Multi-database support | `new AoudaClient({ database: 'db2' })` |
| P10 | WebSocket transport, streaming API | Real-time subscriptions |
| P12 | Session auth, API key auth | `client.auth.login()`, `apiKey` option |
| P14 | Server-side count, WhereClause groups | `count()`, nested `whereGroup` |
| P15 | All join types (inner/left/right/full/cross), chained joins, multi-column keys | `join()`, `leftJoin()`, `rightJoin()`, `fullJoin()`, `crossJoin()` |
| P16 H.1 | Aggregate query builder | `sum()`, `min()`, `max()`, `groupBy()` |
| P16 H.2 | Extended filter operators | `in()`, `notIn()`, `like()`, `isNull()`, `isNotNull()`, `between()` |
| P16 H.3 | Materialized queries client API | `client.materializedQueries.*` |
| P16 H.4 | Columnar output API | `.toColumnar()` |
| P16 H.5 | Schema seed CLI | `npx @aouda/client schema seed` |
| P16 H.6 | Admin API coverage (cluster, backup, config, node) | `client.admin.cluster.*`, `client.admin.backup.*`, etc. |
| P16 G.1–G.4 | MCP cluster tools + docs | `createAoudaClusterMcpToolSet()` |
