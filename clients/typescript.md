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
| Execute named queries / batch | [Named queries](../guides/named-queries.md) — `client.namedQueries.execute(name, args)`, `.batch([{ name, args }])`, `subscribe(name)` |
| Execute named mutations | [Named queries](../guides/named-queries.md#named-mutations) — `client.namedMutations.execute(name, args)` |
| Manage cluster via API | §11 Admin APIs |
| Use MCP tools for AI | §12 MCP Tools |

---

## 3) Getting Started

### Installation

```bash
npm install @aouda/client
```

Runs in browsers, on React Native (below) and on Node 22+ (**NativeClients, 0.4.0**: Node 22 is the floor, because the client
uses the platform's `WebSocket` and no longer ships the `ws` package; on an older Node, pass `streaming.wsFactory`).

### React Native (**NativeClients, 0.4.0**)

`@aouda/client` runs on React Native with Hermes — no Node built-in is reachable from it, and it assumes nothing Hermes lacks
(`TextDecoder`, `crypto.subtle`, `AbortSignal.timeout`). Install it as on the web; Metro bundles it as it is. One thing the app
supplies:

- **`crypto.getRandomValues`, for `createPkcePair()`** (native sign-in): install
  [`react-native-get-random-values`](https://github.com/LinusU/react-native-get-random-values) (or use `expo-crypto`) and import it
  once, before `@aouda/client`. Without it the pair is refused with an error that says so — the verifier is never made from
  `Math.random`. The S256 hash needs nothing: where `crypto.subtle` is missing, the client hashes in JavaScript.

```typescript
import "react-native-get-random-values";
import { AoudaClient } from "@aouda/client";

const client = new AoudaClient({
  serverUrl: "https://db.example.com",
  database: "myapp",
  // Optional on React Native, which has both globally — pass your own to pin certificates or to test:
  fetch: pinnedFetch,
  streaming: { wsFactory: (url) => new WebSocket(url) },
});
client.auth.onTokensChanged((t) => SecureStore.setItemAsync("aouda", JSON.stringify(t)));   // keep the rotated refresh token
```

`fetch` (every HTTP call: data, auth, the long-poll fallback) and `streaming.wsFactory` (the streaming socket) work on every
platform; both default to the platform's own.

`streaming.wireMode: "msgpack"` needs a global `TextDecoder` (the MessagePack codec builds one when it loads): install a polyfill such
as `fast-text-encoding`, or keep the default `"json"` — without one, connecting fails with an `AoudaConnectionError` that says so.
Nothing else needs a polyfill: the client brings its own UTF-8, base64 and SHA-256.

What does not work on React Native, because its `fetch` has no streaming response body: `client.admin.node` log tailing. Iterating a
subscription with `for await` needs `Symbol.asyncIterator`, which Hermes may not define — use the `onSnapshot` / `onChange`
callbacks there. CI runs a smoke on Hermes (sign in, a named query, a subscription, a refresh, PKCE) against every change.

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

### The server's clock (**NativeClients, 0.4.0**)

Every response's `Date` header tells the client how far the server's clock is from the device's. `client.serverClockOffsetMs`
holds the last difference (undefined before the first response; about one second of resolution) and `client.serverNow()`
applies it. Use it to judge a lease the server stamped — a `derived: { serverTime: "write" }` column such as `lastSeen` —
against the server's clock, not the device's:

```typescript
const online = rows.filter((r) => client.serverNow().getTime() - Date.parse(r.lastSeen) < 75_000);
```

`namedMutations.execute()` returns `op: "upsert"` (and `rowsAffected` = inserted + replaced) for an upsert, and `returning`
rows for `insert` and `upsert` definitions that declare them (**NativeClients, 0.4.0**).

### With Authentication

```typescript
// Browser login — URL + database only (no API key)
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
});
await client.connect();
await client.auth.signIn('user@example.com', 'secret', { deviceInfo: 'Ann’s laptop — MyApp' });

// Sessions are devices (NativeClients, 0.4.0): signOut() ends this one; listSessions / revokeSession manage the others
await client.auth.signOut({ scope: 'others' });
const devices = await client.auth.listSessions();

// App auth with service key (backend service acting on behalf of users)
const backend = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  appAuth: { apiKey: 'mk_svc_abc123...' },
});
await backend.connect();

// Server/admin auth with API key
const admin = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  serverAuth: { apiKey: 'mk_srv_abc123...' },
});
await admin.connect();
```

**Keeping tokens across restarts** (**NativeClients, 0.4.0**): `client.auth.onTokensChanged(({ accessToken, refreshToken,
reason }) => …)` is called on sign-in, on every refresh (automatic ones too) and on sign-out (`reason`: `"signedIn"` /
`"refreshed"` / `"signedOut"`); it returns the unsubscribe, and any number of listeners may subscribe. Persist the pair each time
and seed a restarted client with `appAuth: { token, refreshToken }` — the server rotates the refresh token on every refresh, and a
spent one ends the session. See [Keeping tokens across restarts](../auth/client-integration.md#keeping-tokens-across-restarts-nativeclients-040).

**Native sign-in through the browser** (**NativeClients, 0.4.0**): `createPkcePair()` (needs `crypto.getRandomValues` — on
React Native, `react-native-get-random-values`; see [React Native](#react-native-nativeclients-040)), then
`web.auth.createAuthorizationCode({ clientId, redirectUri, codeChallenge, state })` in the signed-in web front and
`app.auth.exchangeCode({ code, codeVerifier, clientId, redirectUri, deviceInfo })` in the native app — a new session at the web
session's `aal`. Recipes: [Native apps](../auth/setup.md#native-apps-sign-in-through-the-browser).

**Auth option rules:**
- `appAuth` and `serverAuth` are mutually exclusive. Omitting both still exposes `client.auth` for keyless browser login.
- Within each, `apiKey` and `token` are mutually exclusive.
- `refreshToken` requires `token` to also be set.
- Browser signup/signin do not need `apiKey`. Backends pass `mk_svc_*`. `mk_pub_*` is for pre-auth named queries on the [data-plane listener](../guides/direct-client-access.md).

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

`count()` posts to `/query/count`: the server counts and returns only the number (**architecture review, 0.3.0**).

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

`in`, `notIn`, and `like` are wire operators the engine evaluates. `isNull`, `isNotNull`, and `between`
are client-side spellings the builder desugars before the request leaves the process — `eq null`,
`ne null`, and `gte` + `lte` respectively.

**`like`** takes a SQL `LIKE` pattern and works on **String columns only**:

- `%` matches any sequence of characters including none; `_` matches exactly one.
- `\` escapes `%`, `_`, or `\` itself. A pattern ending in a lone `\`, or escaping anything else, is a
  `400` — it is never reinterpreted as a literal.
- Matching is **ordinal and case-sensitive**, the same as `=` on a String column. Upper- or lower-case
  both the column and the pattern if you need a case-insensitive search.
- A null column value never matches, not even `'%'`.
- Strip user-supplied wildcards before wrapping, or a search box lets callers write their own patterns:

```ts
const safe = userInput.replace(/[%_\\]/g, '');
const { rows } = await client.table('instruments').where('searchText', 'like', `%${safe}%`).toList();
```

`like` does not satisfy the partition-filter rule and is not index-accelerated — it scans the column.

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

### Filtering a joined table — `joinWhere` (**0.3.0**)

`where()` filters the base table. `joinWhere(column, op, value)` filters the **last** join's table, by that table's column
names, before it joins: a joined row it rejects takes part in no match (an inner join drops it, a left join answers the base
row with nulls on that side). The server applies your row- and partition-level security for each joined table the same way,
so a join onto a table you may read only part of is answered with that part.

```typescript
const euOrders = await client.table('orders')
  .leftJoin('owners', 'ownerId', 'id')
  .joinWhere('region', '=', 'EU')
  .execute();
```

---

## 6) Aggregates

(**ColumnarRead S16, 0.3.0.** Before this, `sum` / `min` / `max` / `groupBy` sent a field the server ignored, and
`execute()` returned the table's plain rows. They now send the query message's `aggregates` / `groupBy`; see
[`POST …/query`](../reference/http-api.md#post-apidatabasesdbquery).)

### Simple Aggregates

Without `groupBy` the answer is one row: one column per aggregate, named by its alias when given.

```typescript
const { rows: [totals] } = await client.table('orders')
  .countRows('n')                 // COUNT(*)
  .sum('amount', 'total')         // optional alias names the output column
  .min('createdAt')
  .max('price')
  .avg('price')
  .countValues('discount')        // COUNT(discount): non-null values
  .countDistinct('customerId')
  .execute();
```

### Group By

```typescript
const { rows } = await client.table('trades')
  .where('Ticker', '=', 'AAPL')
  .groupBy('Source', { column: 'DateTime', bucket: 'day', alias: 'd' })  // keys; bucket: minute, hour, day, week, month, year
  .sum('Volume', 'vol')
  .countRows('n')
  .orderBy('vol', 'desc')         // over the output's names (keys and aggregates)
  .limit(30)
  .execute();                     // rows: the group keys, then one column per aggregate
```

`where`, `orderBy`, `offset` and `limit` combine with aggregates; `select`, `selectExpr`, `distinct` and joins do not
(the server answers `400`). `count()` returns the number of matching rows, not an aggregate column: it drops the
aggregates and `groupBy` and posts the query to `/query/count`, so no row is transferred — the filter and joins
count, `select`, `orderBy`, `limit`, `offset` and `distinct` do not (**architecture review, 0.3.0**; it used to
download every matching row through `/query`).

### The latest (or first) row per key — `latestPerKey` / `firstPerKey` (**0.3.0**)

```typescript
// One row per ticker: the one with the greatest ts (ties: the lowest primary key).
const latest = await client.table('quotes')
  .latestPerKey('ts', 'ticker')
  .select('ticker', 'price', 'ts')
  .execute();
```

`select`, `orderBy` and the page apply to the collapsed rows. A `LatestPerKey` materialized query of the same shape answers it
when it is current (`stats.routedTo`). It does not combine with aggregates, `groupBy`, `distinct`, `selectExpr` or joins.

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

**A key a row leaves out is absent, not null** (**Lead S12, 0.6.0**): an absent `autoIncrement` column is generated
(as `0` is), and an absent column that has a default takes it; an explicit `null` is a null. So a row may leave its
`autoIncrement` id out (until Lead S12 that was `400 INVALID_REQUEST`, `Missing required column`; BL-429). See
[column arrays](../reference/http-api.md#column-arrays-the-write-body).

**`generatedValues`** (**Lead S14, 0.6.0; breaking**: it was an object keyed by row index, `{ "0": { id: 42 } }`) holds
the generated ids as column arrays, one cell per inserted row, `null` where the row gave its own value; `forRow(i)` gives row
`i`'s as an object:

```typescript
const result = await client.table('orders').insertMany([{ status: 'new' }, { id: 7, status: 'given' }]);
result.generatedValues?.forRow(0); // { id: 42 }
result.generatedValues?.forRow(1); // undefined — row 1 gave its own id
result.generatedValues?.data;      // [[42, null]]
```

**On the wire** (**ColumnarCore S06, 0.2.0**): `insert` and `insertMany` send the rows as a binary column-batch
frame once the server has advertised that it reads one (`Accept-Post` on an earlier insert's response), and JSON
otherwise — so the first insert on a client, and every insert to an older server, is JSON. (**Lead S14, 0.6.0**)
The JSON body is [column arrays](../reference/http-api.md#column-arrays-the-write-body) (`{database, columns, data,
absent?}`), as this server requires (a body of row objects is refused `400 ROW_OBJECTS_UNSUPPORTED`). `insert` and
`insertMany` also take a [`ColumnBatch`](#column-batches-lead-s14-060). Rows holding an object, an
array, a column whose rows disagree on type, a number in exponent notation (`1e21`), or more than the frame holds (4,096
columns, 1,000,000 rows, a 16 MB string, an empty or 1 KB+ column name) are sent as JSON; so is everything for five
minutes after a `415`, whatever a later response advertises (**BL-716, 0.2.0**).
A `Date` goes as its JSON text (`toJSON()`), as the JSON body carries it, and a `bigint` as the integer's digits, unrounded
(**Lead S15, 0.6.0**; it was refused, as `JSON.stringify` refuses it). A number goes in the frame as the kind its JSON text takes on the server — an integer as an integer, a
fraction as a decimal, digit for digit (**BL-704, 0.2.0**) — so the inserted rows are the same either way. A
decimal column whose every value in the batch fits 64 bits at the column's largest scale goes as the frame's
`ScaledDecimal` kind — what a server `Decimal(p,s)` column stores (**ColumnarCore S13, 0.2.0**; a server
from an earlier train refuses that kind with a `400`, so pair this client with a server of the same train). (**LoadSpeed
S13, 0.4.0**) It is the only decimal kind the client writes: a batch whose decimals do not fit that way goes as JSON,
where it was sent as the 16-byte `Decimal` kind, which the server now refuses. A frame carries one scale per decimal
column, so a number sent into a `String` column is stored at the column's largest scale (`3` beside `2.50` is `3.00`). See [HTTP API insert](../reference/http-api.md#post-apidatabasesdbtablesnamerows).

**A write is re-sent only when the server provably did not apply it** (**Lead S14, 0.6.0**): under a `retryPolicy`, an
insert is sent again only after one of two failures — a **capacity refusal** (`503 MEMORY_BUDGET_EXCEEDED` /
`WAL_CAPACITY_EXCEEDED`, `429 SERVER_AT_CAPACITY`), which the server answers only for a request it did not apply, or a failure
**before the connection opened** (refused, a host name that did not resolve, a connect timeout). Everything else is yours: a
timeout, a connection lost after sending, and any other `5xx`. An insert has no idempotency key, so a blind repeat could insert
twice (it was retried like a read). (**Lead group 3 review, 0.6.0**) The rule now covers every write — updates, deletes,
`/rows/batch`, `namedMutations.execute`, a bulk load's `:commit`, schema and admin writes: any request but a `GET` that is not a
read. A capacity refusal is re-sent no sooner than its `Retry-After`. **Any other `503` is not re-sent, `Retry-After` or not** —
until this train one with a `Retry-After` was; a proxy may answer it after forwarding the request, and the server answers
`503 BATCH_PARTIALLY_APPLIED` and `500 WRITE_APPLIED_RESPONSE_FAILED` for writes it applied at least in part (see the
[error codes](../reference/http-api.md#server-errors-5xx)). This is the C# SDK's rule. Reads — `GET`s, and the queries, counts and
diffs sent as a `POST` — are re-sent after any transient failure, as before; a bulk load's `:append` is never re-sent by the retry
policy — the bulk loader recovers it itself, after asking the server where the job is (below).

**`expiredRows`** (**Horizon, 0.5.0**): on a table with [retention](../guides/retention.md), a row whose time lies below the
table's horizon — or is an explicit `null` in a nullable time column — is accepted and left out, and `InsertResult.expiredRows`
counts it (a row that omits the column is stored, hidden and dropped by the next flush, and not counted). It is absent when 0, always
on a table without retention.

```typescript
const result = await client.table('trades').insertMany(rows);
result.rowsInserted;  // stored
result.expiredRows;   // accepted, below the horizon: never returned (undefined when 0)
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

### Column batches (**Lead S14, 0.6.0**)

Data you already hold as columns — an Arrow table, a Parquet reader's output, typed arrays — goes to `bulkLoad` and `insert`
as a `ColumnBatch`, and reaches the server as column-batch frames with **no row object in between**. A batch is shaped like a
query result's [typed columns](#query-responses-are-column-batch-frames-columnarread-s16-030): typed arrays, and bitmaps
(bit `i % 8` of byte `i >> 3` for row `i`) for nulls and absent cells.

```typescript
import { ColumnBatch, column } from '@aouda/client';

const batch = ColumnBatch.of(
  column.int64('id', new BigInt64Array([1n, 2n, 3n])),          // or a Float64Array of safe integers, or numbers / bigints
  column.string('sym', ['AAPL', 'MSFT', null]),                  // null = a null cell
  column.double('px', new Float64Array([187.5, 410.25, 0.5])),
  column.timestamp('ts', [new Date(), new Date(), new Date()]),  // or epoch ms; column.timestampTicks for 100-ns ticks
  column.decimal('price', ['187.50', 410.25, undefined], 4),     // undefined = absent: insert applies the default; bulkLoad stores null (BL-1104)
  column.bool('open', new Uint8Array([1, 0, 1])),
).validate();

await client.table('trades').bulkLoad([batch]);   // one batch, an array, or a (async) generator of batches
await client.table('trades').insert(batch);       // one insert; frames once the server has advertised them
```

| Factory | Values | Kind on the wire |
|---|---|---|
| `column.int64(name, values)` | `BigInt64Array`, a `Float64Array` of safe integers, or numbers / bigints | Int64 |
| `column.double(name, values)` | `Float64Array` or numbers (NaN and the infinities are carried) | Double |
| `column.bool(name, values)` | `Uint8Array` of 0 / 1, or booleans | Bool |
| `column.string(name, values)` | strings | String (a dictionary of the values each frame's rows use) |
| `column.dictionary(name, dictionary, codes)` | the distinct values and one `Uint32Array` code per row (Arrow / Parquet dictionaries) | String |
| `column.timestamp(name, values)` / `column.timestampTicks(name, ticks)` | `Date`s or epoch ms / `BigInt64Array` of 100-ns ticks since the Unix epoch | Timestamp |
| `column.decimal(name, values, scale)` / `column.scaledDecimal(name, unscaled, scale)` | numbers or decimal text at one scale / `BigInt64Array` of unscaled values | ScaledDecimal (a server `Decimal(p,s)`) |
| `column.nulls(name, length)` | — | Null |

A typed array is kept as it is, not copied: do not change it until the call that sends it has returned. A plain array may
hold `null` (a null cell) and `undefined` (an **absent** cell — not given, so a generated id or the column's default applies;
a bulk load stores it as null, BL-1104); a typed array takes `{ nulls, absent }` bitmaps. **Call `validate()` while building
batches**: it throws, naming the column and row, for everything the server's frame reader would refuse — a name given twice,
empty or over 1 KB, a code past its dictionary, a timestamp outside .NET's `DateTime`, an int64 in a `Float64Array` that is
not a safe integer, a string over 16 MiB, a bitmap shorter than its rows, more than 4,096 columns. A load validates each batch
as it reaches it; a malformed one fails the load (the job stays open under your own `idempotencyKey` — see below).

A bulk load packs batches into `:append` bodies as consecutive frames, up to the job's rows per append (`appendBatchSize`,
50,000) and about `maxAppendBytes` (8 MiB; `0` turns the bound off), and cuts a larger batch across bodies, each frame's
string dictionary cut to the values its rows use. Batches of a few thousand rows or more load fastest. A server that does not
advertise frames gets JSON column arrays of the same rows. Row objects work as before (`bulkLoad(rows)`): the SDK pivots
them, one frame per body, JSON column arrays for rows no frame carries (an object, an array); a source may not mix rows and
batches.

On kb2, 1 M rows of six columns through the SDK alone (the server stubbed): **0.32 s and 0.57 CPU-s as batches**, 5.7 s and
7.4 CPU-s as row objects — the same 42 MB of frames either way.

### Array columns (**BL-035, next train**) {#array-columns}

(**BL-035, next train**) The six [array column types](../guides/array-columns.md) read and write as typed arrays, **the same type on
every surface**: query results (frames or JSON), named queries, materialized queries, WebSocket and long-poll subscriptions.

| Server type | Read as | Write with |
|---|---|---|
| `Double[]` (**BL-035, next train**) | `Float64Array` | `Float64Array` or `number[]` |
| `Float32[]` (**BL-035, next train**) | `Float32Array` | `Float32Array` or `number[]` |
| `Int32[]` (**BL-035, next train**) | `Int32Array` | `Int32Array` or `number[]` |
| `Int64[]` (**BL-035, next train**) | `BigInt64Array` (exact past 2^53, from JSON too) | `BigInt64Array`, `bigint[]` or `number[]` |
| `Byte[]` (**BL-035, next train**) | `Uint8Array` | `Uint8Array` |
| `String[]` (**BL-035, next train**) | `string[]` | `string[]` |

A null cell is `null`; an empty array is an empty typed array. `AoudaArrayValue` is the union of the six read types and
`AOUDA_DATA_TYPES` lists the six names. A row object with arrays is inserted as JSON; a `ColumnBatch` goes as frames
([the factories](#column-batches-lead-s14-060) gain `doubleArray`, `float32Array`, `int32Array`, `int64Array`, `byteArray` and
`stringArray`, taking one array per row: a typed array is kept, a plain array is converted once, and `null` is a null row).

```typescript
await client.table('Samples').insert({
  Id: 600,
  D: new Float64Array([1.5, -0, 5e-324]),
  F: new Float32Array([0.1]),
  I: new Int32Array([1, 2, 3]),
  L: new BigInt64Array([9007199254740993n]),
  B: new Uint8Array([1, 2, 3]),
  S: ['a', '日本語'],
});

const { rows } = await client.table('Samples').where('Id', '=', 600).execute();
rows[0].D;   // Float64Array [1.5, -0, 5e-324]  (the bits of -0 are kept: 8000000000000000)
rows[0].L;   // BigInt64Array [9007199254740993n]
```

**`-0` and plain arrays.** A typed float array keeps `-0` exactly. **A plain `number[]` written in a row object loses it**: it
goes through `JSON.stringify`, which writes `-0` as `0`. To keep `-0`, write a `Float64Array` / `Float32Array`. (The same plain
`[1.5, -0]` read back as `3ff8000000000000, 0000000000000000` in the run this page was checked with; the typed array read back
`3ff8000000000000, 8000000000000000`.)

```typescript
const batch = ColumnBatch.of(
  column.int64('Id', new BigInt64Array([602n, 603n])),
  column.doubleArray('D', [new Float64Array([1, -0]), null]),   // row 603 is a null cell
  column.stringArray('S', [[], ['x']]),                          // row 602 is an empty array
).validate();
await client.table('Samples').insert(batch);
```

**The client does not repeat the server's limits for a row object**, but it does refuse NaN and the infinities (a `RangeError`)
and checks a `ColumnBatch` before sending (`validate()`): at most 65,536 elements and 1 MiB a value, finite floats, no lone
surrogate. A `float32Array` factory rounds a plain `number` to the nearest float once, at construction; `int32Array`, `int64Array`
and `byteArray` refuse an out-of-range element with a `RangeError`. A frame column's rows are fresh typed arrays you may keep and change.

```text
RangeError  Value '0': element 0 is NaN; array elements must be finite numbers (NaN and ±Infinity are refused).
AoudaApiError (ARRAY_COLUMN_UNSUPPORTED)  … an array column cannot be used in a where (an array column can only be selected — ADR 0067 D-5).
```

An array column cannot be filtered, ordered, grouped, aggregated or joined on, in the builder or in a named query. The
generator (`aouda generate typescript`, `npx @aouda/client generate` ([Type Generation CLI](#type-generation-cli)), or `GET /api/databases/{db}/schema/typescript`) writes the read types above for rows and tables,
and for a named mutation's arguments a union that also takes a plain array (`Float64Array | number[]`).

A client older than this train fails on a response with an array column: *"Column '…': unknown kind 9."*

### Bulk load: a body sent again, resume, and a committed job (**Lead S14, S22, 0.6.0**)

- **The job's last body commits it** (**Lead S22, 0.6.0**). A load's frame bodies are numbered across the job, and the last
  one carries the commit in its end frame, so a job is `:begin` and its `:append`s — no `:commit` round trip. `:commit` is sent
  only for a job whose last rows went as JSON column arrays (a value no frame carries) or that has no rows, and names the frames
  sent (`nextSequence`). `writeConcern`, `writeConcernTimeoutMs`, `mqWaitMs` and `waitForDeferredWork` go where they always did,
  as far as you can see.
- **A failed `:append` is sent again, safely** (**Lead S22, 0.6.0**; until then it was yours). On a lost connection, a timeout,
  a `503` or a capacity refusal the SDK asks the server where the job is — a `:begin` with the job's idempotency key, which also
  stops a stale request still reading the cut body — and sends the same body again: the server skips the frames it already holds,
  so **a body sent twice is applied once**. A body the server applied whole is not sent again. Up to 4 attempts, 250 ms doubling
  between them (or the server's `Retry-After`, at most 30 s). The retry policy (`retryPolicy`) still never re-sends an `:append`
  itself: until Lead S14 it did, and a body the server partly applied was applied twice. A committing body whose answer was lost
  returns the committed job (`alreadyCompleted: true`); one sent again while the first one's commit runs waits for it.
- **A failed load leaves its job open** (holding its tables until the session's idle timeout). Run the same `bulkLoad` again
  with the **same `idempotencyKey`** — pass one if you may need to — and it resumes from the server's `nextSequence`: bodies the
  server holds are not sent, a body that straddles it is sent whole (the server skips its first frames), and the frames skipped
  must carry exactly the rows the server holds — so the call must send the same rows with the same `appendBatchSize` /
  `maxAppendBytes`; otherwise it is refused `409 BULK_LOAD_CURSOR_MISMATCH` and sends nothing (**Lead S22, 0.6.0**; it
  resumed by rows, from `resumeFromRow`, which is gone). `handle.wasResumed` says so. Only a cancellation (`signal`) aborts the
  job — and (**Lead group 3 review, 0.6.0**) a failed load whose `idempotencyKey` the SDK generated, since nothing could resume
  it: on any failure before the commit is sent, and on a refusal of it; a lost answer after the last attempt aborts nothing, since
  the commit may be running. The error does not carry the generated key. A job does not survive a server restart: the same key
  then starts a fresh job and the load is sent from its first frame.
- **A key whose job already committed** (within `Aouda:BulkLoad:IdempotencyWindowMinutes`, 10) returns that job's handle with
  `alreadyCompleted: true` — `rowsLoaded` its durable rows, `token` its commit token — and sends nothing (it used to fail
  `409 BULK_LOAD_INVALID_STATE`).
- **A bulk load refuses a column its table does not have and a missing key** (**Lead S27a, 0.6.0**; BL-1130, BL-1129). With
  `validation: "strict"` it also refuses a null in any NOT NULL column, and a key the job holds twice or the table already holds
  fails the job (`409 BULK_LOAD_DUPLICATE_PK`, an `AoudaApiError` with that `code`); `handle.validation` names the level.
  `pkUniquenessOverride` is gone (**breaking**). See [A load's validation](../guides/bulk-load.md#a-loads-validation-coerce-or-strict-lead-s27a-060).

```typescript
const key = `orders-${day}`;
try {
  await client.table('orders').bulkLoad(batches(), { idempotencyKey: key });
} catch {
  const handle = await client.table('orders').bulkLoad(batches(), { idempotencyKey: key }); // resumes, or returns the commit
  handle.wasResumed; handle.alreadyCompleted;
}
```

### Bulk load durability: `strict` or `os` (**Lead S26c, 0.6.0**)

`bulkLoad` (and `bulkLoadJobs`) take `durability?: 'strict' | 'os'`, sent as `:begin`'s `options.durability`, and the handle's
`durability` says the level the job committed at (`BulkLoadDurability`; an outcome read from `:status` carries it too). Omitted, the load
takes the database's level for a load: `'os'` in a database at `os`, `'strict'` everywhere else.

```typescript
const handle = await client.table('trades').bulkLoad(batches, { durability: 'os' });
handle.durability;   // 'os'
```

`'os'` skips the fsync before the commit. After a power loss before the server has synced the job, the job is dropped whole and
`GET .../bulk-load/{jobId}` reads `state: "lost"`, `errorCode: "BULK_LOAD_LOST"`: run the same `bulkLoad` again with the same
`idempotencyKey`. `'strict'` in an `os` database, and `'os'` for a multi-table job, a table with vector columns, or an edge or
vector table, are refused `400 BULK_LOAD_INVALID_OPTIONS`. See [A load's durability](../guides/bulk-load.md#a-loads-durability-strict-or-os-lead-s26c-060).

### Several jobs into one table (**Lead S18b, S22, 0.6.0**)

A load that arrives as several jobs goes through `bulkLoadJobs`, not a loop of `bulkLoad` calls. It sends job N+1 while job N
commits — the server queues it behind the table's load lock — and yields each job's handle in job order as its commit returns:

```typescript
for await (const handle of client.table('trades').bulkLoadJobs(days, { idempotencyKey: 'trades-2026-10' })) {
  console.log(`${handle.jobId}: ${handle.rowsLoaded} rows`);   // days: an (async) iterable of bulkLoad sources
}
```

Each job is any source `bulkLoad` takes (batches or row objects) and is committed, visible and answered on its own. **One job
sends while one commits** (**Lead S22, 0.6.0**; it was "one `:append` and one `:commit` in flight"): job N's last body commits
it, and job N+1 is begun — naming N as its `afterJobId` — as soon as that body has been written, so the server commits N+1 only
after N, and only if N committed. Node's `fetch` says when a body was written (the SDK streams the last body, `duplex: "half"`); a
browser's `fetch`, or one passed in the client options, does not, and there each job is committed by `:commit` while the next job's
rows are sent (Lead S18b's shape, `afterJobId` still set). The first failure ends the sequence after every earlier job's handle, and
no job after it commits; the job being sent behind a failure — or in flight when you `break` — is aborted (a committing one is
aborted unless its commit point came first, in which case it is committed and its handle is not yielded). With `idempotencyKey`,
job `i` is keyed `{key}.{i}`, so repeating the call replays the jobs that committed. `conflictPolicy: "failFast"` runs the jobs
one at a time.
`client.bulkLoadJobs(table, jobs, options)` is the same call.

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

(**Horizon, 0.5.0**) A delete whose only condition is the table's first cluster column (a `Timestamp` or `Date`) `<` or `<=` a
time — no `limit`, `orderBy` or `returning`, on a tabular table with no vector column that no foreign key references (an edge
table takes the row path) — costs metadata, not rows: on a table with retention it raises the table's horizon (an
early expiry), on any other table it is one log record and whole segments retired. See
[Retention — Deleting everything before a time](../guides/retention.md#deleting-everything-before-a-time).

---

## 8) Schema Management

### Databases

`client.databases.create(name, options)` (**BL-1123, 0.6.0**) sends `kind`, `auth`, `allowSelfSignup`, and `selfSignupRole` only when the caller sets each one, and sends both `kind` and `auth` when the caller sets both. On `auth`, `enabled`, `database`, `allowSelfSignup`, and `selfSignupRole` are included only when set there. The server rejects `kind: "auth"` together with an `auth` object (400). `kind: "data"` with `auth` is valid.

(**Lead S26, 0.6.0**) A database's durability level is `options.durability` — `'strict'` (the server's default when
omitted), `'os'`, `'unlogged'` or `'memory'` (the `DurabilityLevel` type), sent only when set. It replaces `enableWal` (`false` is
`'unlogged'`) and `dataDurability` (`'MemoryOnly'` is `'memory'`); the client no longer sends either, and the server refuses both with
`400 INVALID_REQUEST`. `DatabaseOptionsInfo` reads `durability` in place of the boolean `enableWal`; a table's detail carries
`durability: { level, source }` (`TableDurabilityInfo`) in place of `policy.residency.dataDurability`; and the schema document's
table `durability` takes `level` (`'strict'`, `'unlogged'` or `'memory'`). See
[Write Path Durability](../guides/write-durability.md#durability-levels-lead-s26-060).

```typescript
await client.databases.create('events', { durability: 'os' });
const db = await client.databases.get('events');
db.options.durability; // 'os'
```

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

// Add a Decimal(p,s) column — precision and scale, both required from the 0.4.0 (server 0.2.0, @aouda/client 0.2.0)
await client.tables.addColumn('users', { database: 'mydb', name: 'balance', type: 'Decimal', precision: 18, scale: 2 });

// Rename a column
await client.tables.renameColumn('users', 'phone', { database: 'mydb', newName: 'phoneNumber' });

// Drop a column
await client.tables.dropColumn('users', 'phoneNumber');

// Delete a table
await client.tables.deleteTable('users');
```

**Retention** (**Horizon, 0.5.0**): `policy.retention` on `createTable` and `retention` on `updatePolicy` declare that a table
keeps only its recent rows — `{ keep: '90d' }`, a whole number of `m` / `h` / `d` / `w` (`TableRetention`). The first cluster column
must be a `Timestamp` or `Date`. An `updatePolicy` body that only sets `retention` may omit `storageTemperature`. Once declared it can
be changed, not removed. The returned `TablePolicy` (and the table detail's `policy`) carries `retention` and `horizon` (ISO-8601 UTC,
the instant below which rows are gone). See [Retention](../guides/retention.md).

```typescript
await client.tables.createTable({
  database: 'market',
  name: 'trades',
  columns: [
    { name: 'Id', type: 'Int64', primaryKeyOrder: 1 },
    { name: 'Ts', type: 'Timestamp', clusterOrder: 1, isNullable: true },
    { name: 'Price', type: 'Double' },
  ],
  policy: { storageTemperature: 'Auto', retention: { keep: '90d' } },
});

const policy = await client.tables.updatePolicy('trades', { retention: { keep: '30d' } });
policy.retention; // { keep: '30d' }
policy.horizon;   // e.g. '2026-09-16T08:41:00Z'
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

(**Lead S12, 0.6.0**) The seed file's tables hold their rows as column arrays —
`{ "tables": { "orders": { "columns": ["id", "status"], "data": [[1, 2], ["open", "paid"]] } } }`; a table given as `"rows"` is
refused `400 ROW_OBJECTS_UNSUPPORTED` ([HTTP reference](../reference/http-api.md#schema-seed)).

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
(**Lead S14, 0.6.0**) The server sends a snapshot's pages as column arrays; the SDK gives you rows, as before. A snapshot
whose pages carry fewer rows than the server counted (`snapshot_complete`'s `row_count`) is an error (`onError`, and the
subscription ends) — never a snapshot with rows missing.

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

#### Horizons and range deletes (**Horizon, 0.5.0**)

A windowed materialized query's result and a table with [retention](../guides/retention.md) drop old rows without a row event per
row, and a delete before a time on any other table removes a range in one statement. The subscription tells you with two more events
in the `SubscriptionEvent` union:

- `SubscriptionHorizonEvent` — `type: "horizon"`, `column`, `horizon` (ISO-8601 UTC), `version`, `token?`, `columnType?`: the table's horizon rose.
  Drop every held row whose `column` is below `horizon` or null, and keep no later row below it.
- `SubscriptionRangeDeleteEvent` — `type: "range_delete"`, `column`, `before`, `version`, `token?`, `columnType?`: rows below `before` were deleted
  (a null time was not). Rows that arrive later are live whatever their time.

The snapshot event (`SubscriptionSnapshotEvent`) of such a table carries `horizon` and `horizonColumn`; a windowed result's snapshot
holds only its stored rows, at or after the horizon. The `subscribe` options (and a named-query subscribe's) take `onHorizon(event)`
and `onRangeDelete(event)`; the async iterator yields the same events. Two helpers, exported from `@aouda/client`, do the dropping:
`applyNotice(rows, event)` returns the rows a notice (or a snapshot's horizon) keeps, and `noticeRemoves(row, event)` answers for one
row. They compare times exactly, in .NET ticks — rows carry a `Timestamp` as ticks on the JSON wire, the notices carry ISO strings.
On a `Date` column a row carries its day number (days since the Unix epoch); the notice says so (`columnType: "date"`, and
`horizonColumnType: "date"` on the snapshot event), and the helpers read a whole number there as days.

```typescript
import { applyNotice } from '@aouda/client';

let rows: Trade[] = [];
const sub = client.table<Trade>('trades').subscribe({
  onSnapshot: (snapshot) => { rows = snapshot; },
  onChange: (event) => { /* insert / update / delete, as before */ },
  onHorizon: (event) => { rows = applyNotice(rows, event); },
  onRangeDelete: (event) => { rows = applyNotice(rows, event); },
});
```

The snapshot's horizon is read after the snapshot, so for a moment the snapshot can hold a row below it (a `horizon` event then
follows): apply it to the async iterator's snapshot event too, `applyNotice(rows, snapshotEvent)`. The `onSnapshot` callback receives
no horizon (BL-1068), so a callback-only client drops those rows at the next `horizon` event instead.

A client older than this ignores both messages, so its rows include ones the server no longer returns until it subscribes again. A
`TRUNCATE` sends no notice. The wire contract: [Real-time Streaming — Horizons and range deletes](../guides/real-time.md#horizons-and-range-deletes).

#### One connection, many subscriptions

Every subscription and write stream on a client shares **one** WebSocket per
`(serverUrl, database)`. `subscribe()` on an already-connected client reuses that socket; it does
not open another. Bind as many live views as the application needs — a list, a detail pane, a
presence feed — and they multiplex.

The transport owns reconnection. On a drop it reconnects with exponential backoff and jitter, then
re-sends each live subscription with `resume_from` set to the last version it saw, so the server
can replay from its buffer or fall back to a fresh snapshot. A `gap` is answered the same way.
Subscription ids are stable for the life of the `Subscription` object and are reused across
reconnects, which is what the server expects — see [the `id`
contract](../reference/http-api.md#subscribe).

> **Fixed in 0.1.25 (`BL-635`), released 2026-09-23.** Before that release `connect()` was not idempotent:
> each subscription's start opened its **own** socket, orphaning the previous one — still open,
> unpinged, still delivering — and overwriting the single pair of handshake resolvers, so one
> socket's `auth_ok` completed a different socket's `connect()` and the rest never settled. An
> application binding several live views in one tick got several server sessions, and the
> reconnect replay could then land a subscription id on a session that already held it. The server
> refused it with `DUPLICATE_SUBSCRIPTION_ID`, the client treated any subscription error as fatal
> and unsubscribed, and the view stayed dead until a page reload. If you are pinned below 0.1.25
> and cannot upgrade, the workaround is to bind one subscription per client instance; the real fix
> is the upgrade.


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

// Restore exact backup
await client.admin.backup.restore(backupId);

// Point-in-time restore — last transaction commit <= targetTime
await client.admin.backup.restore({
  backupId,
  targetTime: "2026-05-01T12:00:00Z",
});

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

// ⚠️ state === Ready means READABLE, not CURRENT. Read these three for currency:
//   status.isStale      — true when the result is readable but not up to date
//   status.staleReason  — why, in a sentence; null unless isStale
//   status.currentLag   — how long it has BEEN behind; null when it is not behind
// A caught-up idle query reports currentLag === null forever, not a growing number, so
// null means "current", never "unknown". See reference/http-api.md, "Is this query
// current?". Polling state alone is how twelve of thirteen queries on one production
// deployment reported Ready while holding 1.7 % of their source (BL-642, 0.1.38).
//
// For "how fresh is it", read status.stalenessMs (server 0.2.0, @aouda/client 0.2.0): the age in
// milliseconds of the oldest change the result does not reflect yet; absent when current.
// currentLag is not that number — under a steady insert stream it grows for as long as the
// stream runs, however promptly each commit is applied.

// Query results (returns all rows; options reserved for future use)
const results = await client.materializedQueries.query('active_users_summary');
// results.columns / results.data: the column arrays the server sends (Lead S14, 0.6.0); results.rowCount
// results.rows: Record<string, unknown>[] — the same cells as objects
// results.stats: { rowsScanned, rowsReturned, executionMs }; results.token

// Drop
await client.materializedQueries.drop('active_users_summary');

// Refresh (BL-419, 0.1.22): refresh() now resolves the outcome instead of void.
// "complete" (200) only reaches you with await: true; "scheduled" (202) means the rebuild is
// still running — fire-and-forget, or the server's await window elapsed. Either way the rebuild
// is never cancelled. A 202 with an empty body (an already-deployed server hitting the
// ambient-timeout race this fix closes server-side) also resolves "scheduled" rather than
// throwing; a 200 with an empty body still throws — that's a real protocol violation.
const outcome = await client.materializedQueries.refresh('active_users_summary', { await: true });
// outcome: "complete" | "scheduled"

// refreshAndWait() (BL-419, 0.1.22) is the answer to "after a 202, how do I know it's done?"
// — it issues the refresh and, on "scheduled", polls status() until the query leaves Rebuilding.
const finished = await client.materializedQueries.refreshAndWait('active_users_summary', {
  timeoutMs: 5 * 60_000,   // optional caller deadline; default: none
  pollIntervalMs: 2000,    // optional; default 2000, floor 250
});
// Throws if the query reaches state 3 (Error), or if timeoutMs elapses.
```

**Windows** (**Horizon, 0.5.0**): `create` takes `window: { keep, column? }` (`MaterializedQueryWindow`) on an `aggregate` with
a time bucket or a `topNPerGroup` grouped by a time column; the result stores only its groups within `keep` of the server's clock, and
a read of an older range is computed from the source. `status()` reports `window` and `horizon` (ISO-8601 UTC). A window over a table
with retention is refused. See [Materialized Queries](../guides/materialized.md).

```typescript
await client.materializedQueries.create({
  name: 'candles_1m',
  sourceTable: 'trades',
  type: MaterializedQueryType.Aggregate,
  config: {
    groupByColumns: [{ column: 'Ticker' }, { column: 'Ts', function: 'truncateToMinute', outputName: 'Minute' }],
    aggregates: [{ function: 'count', outputName: 'n' }],
  },
  window: { keep: '7d' },
});
const candles = await client.materializedQueries.status('candles_1m');
candles.window;  // { keep: '7d' }
candles.horizon; // groups before it are computed from the source on read
```

**Do not** call `refresh()` for a table you just bulk-loaded with the default
`postLoadMqBehavior: "auto"` — the engine brings those queries current after the commit, in the background, with the
table's pass over the load's segments (**WorkloadCore S10, 0.3.0**; before, it accumulated them during the load).
The bulk-load handle can wait on it directly instead (BL-419, 0.1.22):

```typescript
const handle = await client.table('users').bulkLoad(rows);
handle.mqRebuildStatus;                     // snapshot at commit: "pending" | "inProgress" | …
const finalStatus = await handle.waitForMaterializedQueries({ pollIntervalMs: 2000 });
// finalStatus: "completed" | "skipped" | "unknown" (terminal — no live session to report from)
// Throws if the rebuild status reaches "failed".
```

(**WorkloadCore S09, 0.3.0**) `:commit` itself can wait, bounded, for the load's queries to be current — (**LoadSpeed M.2, 0.4.0**) only when `mqWaitMs` asks it to — and the handle says how that ended:

```typescript
const loaded = await client.table('users').bulkLoad(rows, { mqWaitMs: 10_000 }); // server default 0 = no wait (0.4.0; 30000 in 0.3.0)
loaded.mqStatus;        // "current" | "behind" | "skipped" | "none"; "unknown" from an older server
loaded.mqFrontierToken; // the lowest frontier among the load's queries, as a consistency token (absent: no query)
loaded.mqWaitedMs;      // how long :commit waited for them
```

The load is durable whatever `mqStatus` says; `"behind"` means the queries' maintenance is still running. To read
them current, read with `loaded.token`, which waits for them.

(**Horizon, 0.5.0**) `handle.expiredRows` counts the rows a load into a table with [retention](../guides/retention.md) left out —
below the horizon, or with a null time — never written and not in `rowsLoaded` (0 without retention). Such a table is loaded one
segment per time slice; see [Bulk Load](../guides/bulk-load.md#loading-a-table-with-retention).

See also: [Bulk Load: don't hand-refresh](../guides/bulk-load.md#available-now).

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

### Query responses are column-batch frames (**ColumnarRead S16, 0.3.0**)

A query (`execute()`, `toColumnar()`, `namedQueries.execute()`) asks for the binary
[column-batch frame](../reference/http-api.md#post-apidatabasesdbquery)
(`Accept: application/vnd.aouda.column-batch-v2, application/json;q=0.5`) and reads whatever the server sends by its
`Content-Type`. An older server, or a result a frame cannot carry, answers JSON as before.

(**Lead S09, 0.6.0; breaking**) The frames are `ACB2`: the body ends with an **end frame** that carries the row count, the
`stats`, `totalMatches` and `warnings` (they were `X-Aouda-*` headers). A body without one — cut anywhere, between two frames
included — or with a frame out of sequence throws `AoudaResponseError`, never returns fewer rows. A server that fails after the
response started writes the error in the end frame; the client drops the frames before it and throws the `AoudaApiError` that
error's code gets as a JSON body (an `INTERNAL_ERROR` is an `AoudaServerError`). `stats.rowsScanned` of a streamed read is the rows
the server read. This client needs a server that speaks `ACB2`; an `ACB1` frame body (an older server) throws, naming the version. The values are the same either
way: integers, `Date` (days since 1970-01-01), decimals and `UInt64` as numbers, `Guid` as a string, and a `Timestamp`
row value as an ISO 8601 string. `toColumnar().data` keeps the JSON body's .NET ticks. (**LoadSpeed S13, 0.4.0**) A
decimal column arrives as `ScaledDecimal` at the column's scale and is read as a number as before; a frame carrying the
retired 128-bit `Decimal` kind (6) throws.

From frames, the columns are held as typed arrays (`result.typedColumns`) and `result.rows` are **views** over them
rather than one object per row. Property access, `Object.keys`, spread, `JSON.stringify`, assignment and `delete` behave
as on a plain object. A view cannot be structured-cloned: pass `{ ...row }` to `structuredClone`, `postMessage` or
IndexedDB.

**An `Int64` past 2^53** (**Lead S15, 0.6.0**). A row holds every integer as a JavaScript number, so a value above
9,007,199,254,740,991 (or below its negative) is rounded, as `JSON.parse` rounds it — and a filter on the rounded value names a
different key. From frames, the exact value is kept: `result.typedColumns[i].exact(r)` gives an `Int64` or `UInt64` cell outside
that range as a `bigint` (any other cell as `raw(r)` gives it), and a `bigint` in a request — a `where` or `update` value, a named
query's argument, an inserted value — is sent as its digits:

```typescript
const result = await client.table('events').limit(100).execute();
const id = result.typedColumns?.find((c) => c.name === 'id');
const key = id?.exact(0) ?? result.rows[0].id;         // 9007199254740993n, not 9007199254740992
await client.table('events').where('id', '=', key).delete();
```

A result read as JSON (an older server) has no `typedColumns`, so its keys past 2^53 cannot be recovered.

A `Timestamp` read through JSON could come back one millisecond early, because a JavaScript number cannot hold its
.NET ticks exactly. It now reads as the millisecond the ticks round to, on both paths.

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
