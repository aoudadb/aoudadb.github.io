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
- **Branch operations** — create, delete, diff, merge via `client.branches.*`
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
| Execute named queries / batch | [Named queries](../guides/named-queries.md) — `client.namedQueries.execute(hash, args)`, `.batch([{ hash, args }])` |
| Execute named mutations | [Named queries](../guides/named-queries.md#named-mutations) — `client.namedMutations.execute(hash, args)` |
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
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
});
await client.connect();
```

### Consistency token (read-your-writes)

The client captures `X-Aouda-Token` after every data-plane response and presents it on the next request. The default store is **in-memory per instance**. Recreating the client without sharing `consistencyTokenStore` **loses** read-your-writes. Pin a token with `.atLeast(token)`; fetch this node's current token with `getConsistencyToken()`. Full caveats: [Freshness](../guides/freshness.md).

```typescript
import { AoudaClient, MemoryConsistencyTokenStore } from '@aouda/client';

const store = new MemoryConsistencyTokenStore(); // share across instances / tabs
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  consistencyTokenStore: store,
});
await client.connect();

await client.table('orders').insert({ id: 1, status: 'open' });
const rows = await client.table('orders').atLeast(store.get('mydb')!).execute();
const current = await client.getConsistencyToken();
```

### With Authentication

```typescript
// App auth with anon API key (for end-user sign-in flows)
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  appAuth: { apiKey: 'mk_anon_abc123...' },
});
await client.connect();

// App auth with service key (backend service acting on behalf of users)
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  appAuth: { apiKey: 'mk_svc_abc123...' },
});
await client.connect();

// Server/admin auth with API key
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  serverAuth: { apiKey: 'mk_srv_abc123...' },
});
await client.connect();

// Session auth — use appAuth for Layer-1, then signIn for Layer-2 user identity
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  appAuth: { apiKey: 'mk_anon_abc123...' },
});
await client.connect();
await client.auth.signIn('user@example.com', 'secret');
```

**Auth option rules:**
- `appAuth` and `serverAuth` are mutually exclusive.
- Within each, `apiKey` and `token` are mutually exclusive.
- `refreshToken` requires `token` to also be set.
- The `apiKey` is a Layer-1 connection key (`mk_anon_`, `mk_pub_`, `mk_svc_`, `mk_srv_`, or custom `mk_`). Call `client.auth.signIn()` to establish Layer-2 user identity. `mk_pub_*` is accepted only on the [data-plane listener](../guides/direct-client-access.md).

**Common mistake:** passing `apiKey` at the top level (no such option exists — it must be nested inside `appAuth` or `serverAuth`).

---

## 4) Query Builder

### Basic Query

```typescript
const users = await client.table('users')
  .where('active', '=', true)
  .orderBy('name', 'asc')
  .limit(10)
  .execute();
```

### Projection

`select()` takes column names as rest arguments (not an array):

```typescript
const names = await client.table('users')
  .select('name', 'email')
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
  .where('active', '=', true)
  .count();
```

### All Filter Operators

`where(column, operator, value)` adds an AND predicate. All operators:

```typescript
// Equality / comparison
.where('age', '>', 18)
.where('age', '>=', 18)
.where('age', '<', 65)
.where('age', '<=', 65)
.where('name', '=', 'Alice')
.where('name', '!=', 'Bob')

// Extended operators (P16)
.where('role', 'in', ['admin', 'owner'])
.where('status', 'notIn', ['deleted', 'archived'])
.where('name', 'like', 'A%')
.where('email', 'isNull')
.where('email', 'isNotNull')
.where('age', 'between', [18, 65])  // two-element [min, max] tuple
```

Multiple `.where()` calls are combined with AND at the top level.

### Nested Groups (OR inside AND)

Use `whereGroup(fn)` with a `WhereGroupBuilder` for nested boolean logic. Inside the group, `where()` ANDs predicates and `orWhere()` ORs them:

```typescript
// Matches: active=true AND (role='admin' OR role='owner')
const results = await client.table('users')
  .where('active', '=', true)
  .whereGroup(g => g
    .where('role', '=', 'admin')
    .orWhere('role', '=', 'owner')
  )
  .execute();
```

For deeper nesting, use `subgroup()` inside a `WhereGroupBuilder`:

```typescript
// Matches: status='active' AND ((role='admin' AND region='us') OR tier='enterprise')
const results = await client.table('users')
  .where('status', '=', 'active')
  .whereGroup(g => g
    .subgroup(inner => inner
      .where('role', '=', 'admin')
      .where('region', '=', 'us')
    )
    .orWhere('tier', '=', 'enterprise')
  )
  .execute();
```

---

## 5) Joins

All five join types are supported with full post-join operations.

Join methods take `(rightTable, leftColumn, rightColumn)` as positional string arguments. For multi-column keys, pass two string arrays instead.

### Inner Join

```typescript
const orders = await client.table('orders')
  .join('customers', 'customerId', 'id')
  .select('orders.id', 'customers.name', 'orders.total')
  .where('orders.total', '>', 100)
  .orderBy('orders.total', 'desc')
  .limit(50)
  .execute();
```

### Left Join

```typescript
const all = await client.table('customers')
  .leftJoin('orders', 'id', 'customerId')
  .execute();
```

### Right Join

```typescript
const result = await client.table('orders')
  .rightJoin('products', 'productId', 'id')
  .execute();
```

### Full Outer Join

```typescript
const result = await client.table('students')
  .fullJoin('enrollments', 'id', 'studentId')
  .execute();
```

### Cross Join

```typescript
const result = await client.table('colors')
  .crossJoin('sizes')
  .execute();
```

### Multi-Column Join Keys

Pass two parallel string arrays — left columns and right columns must have equal length:

```typescript
const result = await client.table('orders')
  .join('shipments', ['orderId', 'warehouseId'], ['orderId', 'warehouseId'])
  .execute();
```

### Chained Joins (up to 8 tables)

```typescript
const result = await client.table('orders')
  .join('customers', 'customerId', 'id')
  .join('products', 'orders.productId', 'id')
  .join('categories', 'products.categoryId', 'id')
  .select('orders.id', 'customers.name', 'products.name', 'categories.name')
  .execute();
```

### Post-Join Operations

All standard operations work after joins:
- `select('col1', 'col2', ...)` — project specific columns (rest args, not an array)
- `where(column, op, value)` — filter on any column (use `'table.column'` for prefixed names)
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
  .groupBy('status', 'priority')   // rest args, not an array
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

// Bulk insert (ordinary multi-row — not P20 bulk-load)
await client.table('events').insertMany([
  { type: 'click', timestamp: new Date() },
  { type: 'view', timestamp: new Date() },
]);
```

#### Identity-insert (explicit autoIncrement IDs)

Use `{ identityInsert: true }` when you must supply IDs on an `autoIncrement` column without flipping schema (Bond `isAutoIncrementDisabled: true`). Every autoIncrement column must be present and non-null; literal `0` is stored as-is; after success the runtime counter advances to `max(inserted)`.

```typescript
await client.table('orders').insert(
  { id: 1000, status: 'seeded' },
  { identityInsert: true }
);

await client.table('orders').insertMany(
  [
    { id: 0, status: 'literal-zero' },
    { id: 500, status: 'reserved' },
  ],
  { identityInsert: true }
);
```

For large ingest, use P20 bulk-load with the same flag:

```typescript
await client.table('orders').bulkLoad(rows, {
  identityInsert: true,
  idempotencyKey: 'orders-reseed-2026-07-31',
});
```

See also: [Getting Started — Seeding explicit IDs](../getting-started/index.md), [HTTP API insert / bulk-load options](../reference/http-api.md), [Bulk Load guide § Scenario 4](../guides/bulk-load.md), [Schema — autoIncrement toggle vs identity-insert](../guides/schema.md).

### Update

```typescript
await client.table('users')
  .where('id', '=', 123)
  .update({ active: false });
```

### Delete

```typescript
await client.table('users')
  .where('id', '=', 123)
  .delete();
```

---

## 8) Schema Management

### Table Operations

```typescript
// List tables
const tables = await client.tables.list();

// Get table schema
const schema = await client.tables.get('users');

// Create table
await client.tables.createTable({
  database: 'mydb',
  name: 'users',
  columns: [
    { name: 'id', type: 'Int64', primaryKeyOrder: 1 },
    { name: 'name', type: 'String' },
    { name: 'email', type: 'String' },
  ],
});

// Add a column
await client.tables.addColumn('users', { database: 'mydb', name: 'phone', type: 'String' });

// Rename a column
await client.tables.renameColumn('users', 'phone', { database: 'mydb', newName: 'phoneNumber' });

// Drop a column
await client.tables.dropColumn('users', 'phoneNumber');

// Delete a table
await client.tables.deleteTable('users');
```

### Declarative Schema Operations

`client.schema` provides the full diff / apply / export / history surface for declarative schema management:

```typescript
// Export the current live schema as a plain JSON document
const exported: Record<string, unknown> = await client.schema.export();

// Compute a diff between the live catalog and a desired schema document
const diff = await client.schema.diff(desiredSchemaDoc);
// diff.changes: SchemaChange[]
// diff.summary: DiffSummary
// diff.warnings: SchemaChangeWarning[]  ← unsupported modifications (type changes, PK changes, etc.)

// Apply a desired schema document (returns apply result + optional historyId)
const result = await client.schema.apply(desiredSchemaDoc);
// result.result.summary.applied, .skipped, .failed
// result.historyId

// Apply with options
const result = await client.schema.apply(desiredSchemaDoc, {
  allowDestructive: true,  // allow DropColumn / DropTable
  dryRun: true,            // plan only, do not execute
});

// Schema history (newest first)
const history = await client.schema.history({ limit: 20, offset: 0 });
```

#### `DiffSummary` — shape and field reference

`DiffSummary` is returned inside `SchemaDiffResult.summary`:

```typescript
interface DiffSummary {
  totalChanges: number;          // safeChanges + destructiveChanges
  safeChanges: number;           // non-destructive changes
  destructiveChanges: number;    // DropColumn + DropTable
  tablesCreated: number;         // CreateTable count
  tablesDropped: number;         // DropTable count
  columnsAdded: number;          // AddColumn count
  columnsDropped: number;        // DropColumn count
  columnsAltered?: number;       // UpdateColumnAutoIncrement count (optional — undefined on older servers)
  policiesUpdated: number;       // UpdatePolicy count
  durabilitiesUpdated: number;   // UpdateDurability count
  settingsUpdated: number;       // UpdateSettings count
}
```

`columnsAltered` is optional because older servers do not return it. Always guard with `?? 0` when displaying counts:

```typescript
const altered = diff.summary.columnsAltered ?? 0;
if (altered > 0) {
  console.log(`${altered} column(s) altered`);
}
```

#### `SchemaChange` — shape

Each entry in `diff.changes` is a `SchemaChange`:

```typescript
interface SchemaChange {
  type: string;             // e.g. "AddColumn", "DropColumn", "UpdateColumnAutoIncrement"
  tableName?: string | null;
  columnName?: string | null;
  isDestructive: boolean;
  details: string;          // human-readable description
  before?: unknown;         // previous value (where applicable)
  after?: unknown;          // new value (where applicable)
}
```

Known `type` values: `AddColumn`, `DropColumn`, `CreateTable`, `DropTable`, `UpdatePolicy`, `UpdateDurability`, `UpdatePartitionLevelSecurity`, `UpdateAuthorizationOptions`, `UpdateSettings`, `UpdateColumnAutoIncrement`. The field is `string` (not a union) — forward-compatibility is guaranteed.

#### `SchemaChangeWarning` — unsupported modifications

Warnings are returned alongside changes for modifications the engine cannot execute:

```typescript
interface SchemaChangeWarning {
  code?: string;
  message?: string;
}
```

Always inspect `diff.warnings` before applying. Warnings are never applied — they require manual intervention (typically drop and re-create). See [Schema Lifecycle guide §2.11](../guides/schema.md) for the full warning reference.

#### Enabling / disabling autoIncrement on an existing column

The recommended pattern is export → patch → apply:

```typescript
// Get the current live schema
const exported = await client.schema.export();

// Locate the column and flip its autoIncrement flag
const tables = exported['tables'] as Record<string, unknown>;
const table = tables['orders'] as Record<string, unknown>;
const columns = table['columns'] as Array<Record<string, unknown>>;

const patched = {
  ...exported,
  tables: {
    ...tables,
    orders: {
      ...table,
      columns: columns.map(col =>
        col['name'] === 'id'
          ? { ...col, autoIncrement: true }   // or false to disable
          : col
      ),
    },
  },
};

// Apply — no allowDestructive needed (this is a safe change)
const result = await client.schema.apply(patched);
console.log('ColumnsAltered:', result.result.summary);
```

**Column eligibility:** only integer types (`Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`). The server rejects the change for other types. The diff engine produces `UpdateColumnAutoIncrement` changes only for eligible types.

**Counter recovery:** when you enable auto-increment on a column that already has data, the server counter initializes to `MAX(existing values) + 1` on first use. Existing values are not overwritten.

**Schema document field name:** the JSON field inside a column entry is `autoIncrement` (not `isAutoIncrement`). The TypeScript `ColumnSchema.isAutoIncrement` is the read-side field name returned by the table schema endpoint; the schema document uses `autoIncrement` for apply/export. This is a known naming asymmetry.

### Type Generation CLI

```bash
npx @aouda/client generate --server http://localhost:5000 --database mydb --output ./types
```

Generates TypeScript interfaces from Aouda table schemas.

### Schema Seed CLI

```bash
npx @aouda/client schema seed --server http://localhost:5000 --database mydb --file seed.json
```

---

## 9) Branches

Branches are schema-level constructs managed via `client.branches`. Data operations always target the current database; branch-scoped data queries are not supported directly on `TableQuery`.

```typescript
// List branches (excludes implicit main)
const branches = await client.branches.list();

// Create branch (parent defaults to "main")
await client.branches.create({ name: 'feature-x' });

// Create branch from a specific parent
await client.branches.create({ name: 'feature-x', from: 'main' });

// Get branch details
const branch = await client.branches.get('feature-x');

// Diff branch vs parent (schema changes only)
const diff = await client.branches.diff('feature-x');

// Dry-run merge (returns plan without applying)
const plan = await client.branches.merge('feature-x');

// Execute merge (apply schema changes to parent)
const result = await client.branches.merge('feature-x', { execute: true });

// Delete
await client.branches.delete('feature-x');
```

**Note:** `client.branches.merge()` with no options (or `dryRun: true`) returns a `MergeResult` with the plan. Pass `{ execute: true }` to actually apply the merge and get back a `MergeExecutionResult`.

---

## 10) Real-Time Streaming

### WebSocket Subscriptions

`subscribe()` is synchronous (no `await`). It returns a `Subscription` that is also an `AsyncIterable`. Unsubscribe with `await subscription.unsubscribe()`.

The subscription delivers two event types via `onChange`:
- `op: "insert"` — a row was inserted; `row` contains the new row.
- `op: "update"` — a row was updated; `row` is the new row, `prev` is the previous row.
- `op: "delete"` — a row was deleted; `key` contains the deleted primary key.

An `onSnapshot` callback receives the initial consistent snapshot of existing rows when the subscription first connects.

```typescript
// Callback style
const subscription = client.table('events')
  .subscribe({
    onSnapshot: (rows, version) => console.log('Initial rows:', rows),
    onChange: (event) => {
      if (event.op === 'insert') console.log('New:', event.row);
      if (event.op === 'update') console.log('Updated:', event.row, 'was:', event.prev);
      if (event.op === 'delete') console.log('Deleted key:', event.key);
    },
    onError: (err) => console.error('Subscription error:', err),
  });

// Async-iterator style
for await (const event of subscription) {
  if (event.type === 'snapshot') {
    console.log('Snapshot rows:', event.rows);
  } else {
    console.log('Change:', event.op, event.row ?? event.key);
  }
}

// Unsubscribe (always await — it sends an unsubscribe frame to the server)
await subscription.unsubscribe();
```

Subscriptions can also be filtered using the query builder's `where()` predicates:

```typescript
// Subscribe only to events matching a filter
const sub = client.table('events')
  .where('severity', '=', 'error')
  .subscribe({
    onChange: (event) => console.log('Error event:', event.row),
  });
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
| `aouda_cluster_status` | Replication status, topology, and optional WAL coverage |
| `aouda_cluster_health` | Health, readiness, replication health, and optional detail + node info |
| `aouda_backup_trigger` | Trigger an immediate backup |
| `aouda_backup_list` | List existing backups |
| `aouda_backup_restore` | Restore a backup by ID |
| `aouda_backup_get_schedule` | Get current backup schedule |
| `aouda_backup_set_schedule` | Update backup schedule |
| `aouda_cluster_join` | Join this node to a replica set |
| `aouda_cluster_leave` | Leave cluster and return to standalone |
| `aouda_cluster_promote` | Trigger election to promote this node to primary |
| `aouda_cluster_failover` | Step down current primary and trigger new election |
| `aouda_cluster_drain` | Mark a node as draining for maintenance |
| `aouda_cluster_get_config` | Get mutable cluster configuration |
| `aouda_cluster_patch_config` | Patch mutable cluster config fields (`heartbeatIntervalMs`, `electionTimeoutMs`) |

### Usage

```typescript
import { createAoudaClusterMcpToolSet } from '@aouda/client';

const tools = createAoudaClusterMcpToolSet(client);
// tools is an object keyed by tool name, e.g. tools.aouda_cluster_status
// Each value: { name, description, inputSchema, execute }
// Register individual tools with your MCP host implementation

// Example: read cluster status
const status = await tools.aouda_cluster_status.execute({ includeCoverage: true });

// Example: trigger backup
const result = await tools.aouda_backup_trigger.execute({ incremental: true });
```

Each tool definition has:
- `name` — stable tool name (e.g. `aouda_cluster_status`)
- `description` — human-readable description for the MCP host
- `inputSchema` — JSON Schema object describing valid inputs
- `execute(params)` — async handler calling typed `client.admin.*` methods

Documentation: `aouda-client-ts/docs/dev/MCP-Cluster-Tools.md`.

---

## 13) Materialized Queries

```typescript
import { MaterializedQueryType } from '@aouda/client';

// List materialized queries
const queries = await client.materializedQueries.list();

// Create — type and config are required
await client.materializedQueries.create({
  name: 'active_users_summary',
  sourceTable: 'users',
  type: MaterializedQueryType.Filter,         // 4 — only active rows
  config: { where: [{ column: 'active', op: '=', value: true }] },
});

// Check status
const status = await client.materializedQueries.status('active_users_summary');
// status.state: 0=Building, 1=Ready, 2=Rebuilding, 3=Error
// status.rowCount, status.lastUpdatedUtc, status.errorMessage

// Query results (returns all rows; options reserved for future use)
const results = await client.materializedQueries.query('active_users_summary');
// results.rows: Record<string, unknown>[]
// results.stats: { rowsScanned, rowsReturned, executionMs }

// Drop
await client.materializedQueries.drop('active_users_summary');
```

---

## 14) Columnar Output

For high-performance data processing, bypass row conversion and get the raw columnar payload directly. `select()` takes rest args (not an array):

```typescript
const columnar = await client.table('events')
  .select('timestamp', 'value')
  .limit(10000)
  .toColumnar();

// columnar.columns: ['timestamp', 'value']
// columnar.types: ['Timestamp', 'Double']   ← exact wire type names (capitalized)
// columnar.data: [[...ticks as numbers], [...values]]
// columnar.rowCount: 10000
// columnar.stats: { rowsScanned, rowsReturned, segmentsAccessed, executionMs }
```

`columnar.types` contains the server-declared Aouda type names (`'Int64'`, `'String'`, `'Timestamp'`, `'Double'`, etc.). Timestamp values arrive as Int64 .NET ticks — use `coerceColumnarValue(value, typeName)` (exported from `@aouda/client`) to convert them to ISO 8601 strings if needed.

---

## 15) Phase Coverage Matrix

| Phase | Delivered | Key Capability |
|-------|----------|----------------|
| P5 | Core client, query builder, CRUD, schema, type generation CLI | Foundation |
| P6 | Multi-database support | `new AoudaClient({ database: 'db2' })` |
| P10 | WebSocket transport, streaming API | Real-time subscriptions |
| P12 | Session auth, API key auth | `client.auth.signIn()`, `apiKey` option |
| P14 | Server-side count, WhereClause groups | `count()`, nested `whereGroup` |
| P15 | All join types (inner/left/right/full/cross), chained joins, multi-column keys | `join()`, `leftJoin()`, `rightJoin()`, `fullJoin()`, `crossJoin()` |
| P16 H.1 | Aggregate query builder | `sum()`, `min()`, `max()`, `groupBy()` |
| P16 H.2 | Extended filter operators | `where(col, 'in', [...])`, `'notIn'`, `'like'`, `'isNull'`, `'isNotNull'`, `'between'` |
| P16 H.3 | Materialized queries client API | `client.materializedQueries.*` |
| P16 H.4 | Columnar output API | `.toColumnar()` |
| P16 H.5 | Schema seed CLI | `npx @aouda/client schema seed` |
| P16 H.6 | Admin API coverage (cluster, backup, config, node) | `client.admin.cluster.*`, `client.admin.backup.*`, etc. |
| P16 G.1–G.4 | MCP cluster tools + docs | `createAoudaClusterMcpToolSet()` |
| BL-126b (0.1.6) | `DiffSummary.columnsAltered` field; `UpdateColumnAutoIncrement` schema change type surfaced in diffs | `diff.summary.columnsAltered` |
