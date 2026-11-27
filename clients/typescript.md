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
- **Authentication and access** — one credential (a key or a session), `client.auth` for sign-in and sessions, `client.whoami()`, `client.access` for principals, roles and credentials
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

The client captures `X-Aouda-Token` after every data-plane response and presents it on the next request. The default store is **in-memory per instance**. Recreating the client without sharing `consistencyTokenStore` **loses** read-your-writes. Pin a token with `.atLeast(token)`; fetch this node's current token with `getConsistencyToken()`. `client.forgetConsistencyTokens()` discards the client's tokens for every database (a custom `ConsistencyTokenStore` implements `forget(database)` and `forgetAll()`; a successful `admin.backup.restore` calls it for you) (**BL-1731, next train**). Full caveats: [Freshness](../guides/freshness.md).

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
// A browser app: URL and database only, no key. Until a user signs in, its calls act as `anonymous`.
const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
});
await client.connect();
await client.auth.signIn('user@example.com', 'secret', { deviceInfo: 'Ann’s laptop — MyApp' });

// Sessions are devices (NativeClients, 0.4.0): signOut() ends this one; listSessions / revokeSession manage the others
await client.auth.signOut({ scope: 'others' });
const devices = await client.auth.listSessions();

// A backend: a principal's key. `apiKey` takes a key of any kind: stored, derived or limited
const backend = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  apiKey: process.env.AOUDA_KEY, // 'aouda_...'
});
await backend.connect();

// An operator, for server/admin calls: a key of a `_serverauth` principal, in the same option
const admin = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
  apiKey: process.env.AOUDA_OPERATOR_KEY,
});
await admin.connect();
```

**Keeping tokens across restarts** (**NativeClients, 0.4.0**): `client.auth.onTokensChanged(({ accessToken, refreshToken,
reason }) => …)` is called on sign-in, on every refresh (automatic ones too) and on sign-out (`reason`: `"signedIn"` /
`"refreshed"` / `"signedOut"`); it returns the unsubscribe, and any number of listeners may subscribe. Persist the pair each time
and seed a restarted client with `session: { token, refreshToken }` — the server rotates the refresh token on every refresh, and a
spent one ends the session.

**One session at a time** (**BL-1852, next train**; BL-1014). `signIn`, `signUp`, `exchangeCode` and `exchangeOidcToken` replace the session
the client holds, and a call in flight belongs to the session it was made in:

- A refresh of the earlier session that ends after a sign-in, an exchange or a sign-out changes nothing and reports nothing to
  `onTokensChanged`; `client.auth.refresh()` rejects with `AoudaSessionReplacedError` (`code` `AUTH_REFRESH_SUPERSEDED`; it is not an
  `AoudaAuthenticationError`: nothing was refused, so do not answer it by signing the user out). Before, it put the earlier user's tokens back,
  or cleared the new ones.
- `signOut()` ends, on the server and here, the session it was called in; one a sign-in stored meanwhile stays.
- A request answered 401 after its session was replaced or ended is thrown, not sent again, and a `retryPolicy` sends nothing again once the
  session changed (the last failure is thrown). A call that was waiting for a refresh when another session was stored is rejected with
  `AUTH_REFRESH_SUPERSEDED`, unsent. Make it again if it is meant for the new session.
- An insert whose binary body the server refused (`415`) is not sent again as JSON in another session: it is rejected with
  `AUTH_REFRESH_SUPERSEDED`, and nothing was inserted.
- A `bulkLoadJobs` sequence is the user's who made the call (**BL-1854, next train**; or, when nobody was signed in, the user's who is when its
  first job begins). Once another user is signed in, or nobody, nothing more is sent for it — no further job, and no rows, commit or abort of
  the one under way: it ends, after every earlier job's handle, with an `AoudaSessionReplacedError` whose `code` is `AUTH_SESSION_REPLACED`.
  The rest of one `bulkLoad` whose job has begun is the same. The server ends such a job, uncommitted, at its idle timeout; until then it
  holds its tables' load locks. A request already on its way goes on as the user it was sent as: if it commits the job, the rows are loaded.

**When the user changes** (**BL-1854, next train**) everything realtime of the earlier user ends, at once and by name, on the WebSocket and on
long-poll, open or not (connecting, falling back, waiting to reconnect). It ends when another principal's session replaces the one held
(`signIn`, `signUp`, `exchangeCode`, `exchangeOidcToken`), and when the session ends (`signOut()`, `signOut({ scope: 'global' })`, a refresh the
server refuses for good):

- A subscription's `onError` gets an `AoudaSessionReplacedError` (`code` `AUTH_SESSION_REPLACED`; its message says whether the session was
  replaced or ended), and its iterator throws it. Events it had queued and you had not read are **not** handed out. It is not resumed.
- A write stream's `write()` and `close()` reject with an `AoudaWriteStreamError` whose `code` is `AUTH_SESSION_REPLACED` (`cause`: the error
  above); `lastAcknowledgedSeq` and `unacknowledgedFrames` say what is known of its frames, as for a lost connection.
- A subscription that was still connecting ends the same way, and an `openWriteStream` that was rejects with the same code.
- A node's log stream (`admin.node.streamLogs`) throws the same `AoudaSessionReplacedError`; entries not handed out are dropped.
- What you make from then on — in that `onError`, in an `onTokensChanged` listener, after the `signIn` — is on a new connection, as the user
  signed in then, and shares nothing with what there was. After a sign-out, with nobody signed in, it is refused as any realtime call without
  a credential is (`AUTH_CREDENTIAL_MISSING`).

Rows your callbacks and queries already gave you are yours to clear. The code is not an authentication failure — nothing was refused — so do not
answer it by signing the user out: subscribe again if somebody is signed in. When the server ends the session first (it checks an open
connection every heartbeat, 20 s by default, so it can during a `signOut()`), the code is its own, `AUTH_CREDENTIAL_REVOKED`: handle both.

```typescript
import { AUTH_SESSION_REPLACED, type Subscription } from '@aouda/client';

let orders: Subscription | null = null;

function bind(): void {
  orders = client.table('orders').subscribe({
    onSnapshot: show,
    onChange: apply,
    onError: (err) => {
      const code = (err as { code?: string }).code;
      if (code !== AUTH_SESSION_REPLACED && code !== 'AUTH_CREDENTIAL_REVOKED') return report(err);
      orders = null;
      clear(); // the earlier user's rows
    },
  });
}

// The subscription has ended before any listener hears of the change. A repeat sign-in of the same user leaves it running.
client.auth.onTokensChanged(({ reason }) => {
  if (reason === 'signedIn' && orders === null) bind();
});
```

**The same user's new token keeps the connection** (**BL-1858, next train**): after a refresh, a repeat sign-in or an OIDC exchange of the same
principal (the same issuer and subject), and after `signOut({ scope: 'others' })`, subscriptions and streams go on, and the connection — the
WebSocket and long-poll alike — is re-authenticated with the new token. Before, only a refresh over the WebSocket did that: after a repeat
sign-in or an exchange, and always over long-poll, everything ended when the token the connection was opened with expired.

**An access token that expires on an open connection is renewed** (**BL-1921, next train**). The server ends a realtime session when its
token expires and nothing re-authenticated it (`auth_error` or a poll's `401` `AUTH_CREDENTIAL_EXPIRED`, remedy `renew`); an application that
only subscribes makes no call that would refresh the token first. The client now reconnects, refreshing the token before it does (even when the
token's own expiry says it is still valid: the server's clock decides), and what was open resumes. A credential that cannot renew — a key past its
expiry, a refresh the server refuses, an OIDC session (no refresh token) — is refused at that reconnect and ends every subscription and stream by
name, once. A revoke, a sign-out elsewhere or a disabled user still ends everything at once. Before, every subscription and write stream ended
with `AUTH_CREDENTIAL_EXPIRED` at the access token's lifetime (15 minutes by default). The C# client renews it too (**next train**).

Before this, an open connection was neither replaced by a sign-in nor closed by `signOut()`: the earlier user's subscriptions, and new ones
made after the next sign-in, delivered the earlier user's rows and their streams wrote as that user, until the connection was lost; then the
earlier user's subscriptions resumed as the next one. On those versions, `await client.disconnect()` and make a new client when the user changes
— once the first connect has ended: with the long-poll fallback on (the default), a `disconnect()` during it fell back to long-poll and went on
(**BL-1862, next train**).

**Native sign-in through the browser** (**NativeClients, 0.4.0**): `createPkcePair()` (needs `crypto.getRandomValues` — on
React Native, `react-native-get-random-values`; see [React Native](#react-native-nativeclients-040)), then
`web.auth.createAuthorizationCode({ clientId, redirectUri, codeChallenge, state })` in the signed-in web front and
`app.auth.exchangeCode({ code, codeVerifier, clientId, redirectUri, deviceInfo })` in the native app — a new session at the web
session's `aal`. Recipes: [Native apps](../auth/setup.md#native-apps-sign-in-through-the-browser).

**Which databases a sign-in opens** (**BL-1464, 0.16.0**): omit `databases` and the session has no database limit. `client.auth.signIn(email, password, { databases: ['orders', 'reports'] })` limits the session to those databases, and so does `createAuthorizationCode({ …, databases })` for native sign-in.
An empty list, a blank name, or a name the auth database does not govern is `400 INVALID_REQUEST`.
A token used elsewhere is `403 AUTH_POLICY_DENIED` with remedy `none` and `reason: credential-limit` (**BL-1464, 0.16.0**). `AUTH_DATABASE_NOT_IN_ALLOWANCE` is not produced. A refresh refused for that limit ends the session
like `AUTH_REFRESH_TOKEN_INVALID` — the client clears its tokens, reports `"signedOut"` and does not retry, and the realtime transports
stop reconnecting. See [Sessions](../reference/http-api.md#sessions).

**One credential (BL-1464, 0.16.0, breaking).** `apiKey` takes a key of any kind (stored, derived or limited; all have the one format
`aouda_<id>_<secret>`), `session` a signed-in session. The 0.15 options for a user's session, a server user's session and a second user token
are gone, with no alias: the constructor throws, naming what replaces each ([Moving from 0.14](../auth/migrating-from-0-14.md)). A key goes out as `Authorization: Bearer <key>` to the same URLs and the server resolves it to
its principal; nothing about the key's text says what it may do. The client checks the key at construction (shape, checksum, the retired
format) and the error never contains the value. `client.whoami()` says which principal the credential is and what it may do.
`client.databases.list()` and `create()` need `manage` on `server`, which only a principal of `_serverauth` can hold: one without it
is refused `403 AUTH_POLICY_DENIED`, a principal of an application auth database `403 AUTH_WRONG_AUTH_DATABASE`.

**Auth option rules:**
- `apiKey` cannot be combined with a `session` that holds a token: a key and a signed-in session are two credentials, refused at
  construction. With neither, the client is keyless: `client.auth` signs a user in, and until then its calls act as `anonymous` on the
  [data-plane listener](../guides/direct-client-access.md) (the admin listener answers `401 AUTH_CREDENTIAL_MISSING`).
- `session.scope` says where sign-in, refresh and sign-out go: `"database"` (the default) is the auth database that governs the client's
  database, `"server"` is `_serverauth`, for an operator with a password. A key has no such option.
- `refreshToken` requires `token` to also be set.
- A client with `apiKey` does not sign in: `client.auth.signIn` and the other calls that make a session throw. Use one client per user.

**Common mistake:** sending a backend's key and a user's token together. A request carries one credential. To act as a user, use a client
that holds that user's session, or a [limited key](../auth/credentials.md#limited-keys) minted from it (`client.auth.createLimitedKey`).

**A refused credential (BL-1386, 0.11.0).** The client never retries a 401 or a credential-refusing 403, but a writer that treats
the error as "try again later" drops or re-buffers every row while the key is bad. Opt in with `authFailurePolicy`:

```typescript
const client = new AoudaClient({
  serverUrl, database, apiKey,
  authFailurePolicy: {
    failFast: true,                       // throw AoudaAuthenticationFatalError (an AoudaAuthenticationError; `cause` is the original)
    sustainedAfter: 3,                    // default 3
    onSustained: (info) => alert(info),   // once per streak: { errorCode, statusCode, consecutiveFailures, firstSeenAt, lastSeenAt, requestId }
  },
});
```

Fatal is HTTP 401 (`AUTH_CREDENTIAL_MISSING`, `AUTH_KEY_MALFORMED`, `AUTH_CREDENTIAL_INVALID`, `AUTH_CREDENTIAL_EXPIRED`,
`AUTH_CREDENTIAL_REVOKED`, ...), and HTTP 403 with `AUTH_WRONG_AUTH_DATABASE` or `AUTH_ACCOUNT_DISABLED`; not `AUTH_POLICY_DENIED` or
`AUTH_ROW_DENIED` (the credential is valid, and another table or operation may be allowed). A streak is consecutive such failures with no successful request between them, counted over HTTP requests (queries, inserts,
bulk load, schema calls); a realtime socket's own handshake is not counted, an authentication failure stays out of the circuit
breaker, and neither the error nor `info` carries the key. The SDK has no batch writer: a loop of `insert` / `bulkLoad` calls should
stop on `AoudaAuthenticationFatalError`.

**Refusals that say what to do (BL-1464, 0.16.0).** A refusal of the credential or the policy (`AUTH_CREDENTIAL_*`, `AUTH_KEY_MALFORMED`,
`AUTH_WRONG_AUTH_DATABASE`, `AUTH_POLICY_DENIED`, `AUTH_ROW_DENIED`, `AUTH_PUBLIC_UNRESTRICTED`) carries the server's
[`remedy`](../auth/whoami.md#remedy) as a typed value on the error. The error's `message` is the server's, then the remedy as a sentence, and for
`sign-in` and `fix-key` the option to set (`apiKey` or `session`) with the
kind of credential the client was sending, a key by its public id. `code`, `statusCode` and `requestId` are unchanged; a data error (404, 400, ...) keeps the
server's message exactly. The `/ready` reason codes `schema_pending` and `schema_drift` are documented in the [HTTP API](../reference/http-api.md#get-ready).

**Named queries and mutations need an `execute` statement (BL-1464, 0.16.0).** The client sends named-artifact calls as before. A `403
AUTH_POLICY_DENIED` (admin listener) or a data-plane `404 NAMED_QUERY_NOT_FOUND` / `NAMED_MUTATION_NOT_FOUND` on a call that worked before
means the caller's statements do not `execute` that artifact; a batch answers `NAMED_QUERY_NOT_FOUND` in the slot. `INSUFFICIENT_PERMISSIONS` is not produced. See
[Execute](../auth/authorization.md#execute).

### Managing access — `client.access` (**BL-1464, 0.16.0**)

`client.access` calls the [access routes](../reference/http-api.md#access-routes): principals, roles, the `signup` setting and credentials
of one auth database. The caller needs `manage` on what it changes and must itself hold every statement it grants
([Grant only what you hold](../auth/authorization.md#grant-only-what-you-hold)). What a user may reach is an attribute of the principal that a
statement's `where` reads, where 0.13 to 0.15 had calls for per-user rows of their own on `client.auth` (gone).

```ts
const access = client.access.authDatabase('auth');

await access.roles.create({
  name: 'member',
  statements: [{
    actions: ['read', 'write'],
    resources: ['chat/table/messages'],
    where: { and: [ { column: 'room', op: 'in', principal: 'attributes.rooms' } ] },
  }],
});
await access.principals.create({ name: 'ann@example.com', roles: ['member'], attributes: { rooms: ['room_42'] } });
await access.principals.update('ann@example.com', { attributes: { rooms: ['room_42', 'room_43'] } });   // replaces the member

await access.principals.create({ name: 'feeder', roles: ['writer'] });
const { key, id } = await access.credentials('feeder').mintKey({ name: 'first' });   // `key` is in this answer once
await access.credentials.revoke(id);
```

| Call | Route |
|---|---|
| `principals.list` / `get` / `create` / `update` / `delete` | `/api/auth/{authDatabase}/principals[/{name}]` |
| `roles.list` / `get` / `create` / `update` / `delete` | `/api/auth/{authDatabase}/roles[/{name}]` |
| `signup.get` / `set` | `/api/auth/{authDatabase}/signup` |
| `credentials(name).list` / `mintKey` / `addOidcTrust` | `…/principals/{name}/credentials`, `/keys`, `/oidc` |
| `credentials.delete(id)` / `revoke(id)` | `…/credentials/{id}`, `…/credentials/{id}/revoke` |

A write to an object the declaration file owns is refused `409 DECLARED_IN_CONFIGURATION`. In .NET the same calls are on `client.Access`.

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

### Reading across partitions — `withCrossPartitionAccess()`

A table with a partition key refuses a read that names no partition (`PARTITION_FILTER_REQUIRED`), because it would scan every
partition. `withCrossPartitionAccess()` asks the server to skip that guard for the query, and it works on `execute()`, on `count()`
and on `subscribe()` (**BL-1227, 0.9.0**; until this train it reached `execute()` and `count()` only, and `subscribe()` had no way to send it).

```typescript
// A trusted backend reads open orders across every partition
const open = await client.table('orders')
  .where('status', '=', 'open')
  .withCrossPartitionAccess()
  .execute();
```

**The flag is a cost waiver, not a grant.** It waives `PARTITION_FILTER_REQUIRED` and nothing else: what the query returns is what
the caller's `read` statements admit, with the flag or without it. A statement with no `where` admits every partition; one whose `where`
names the partition column, only the partitions it admits; and a caller with no `read` statement on the table is still refused
(`403 AUTH_POLICY_DENIED`). See [Row conditions](../auth/authorization.md#row-conditions).
The **data-plane** listener (the browser tier) ignores the flag. For subscriptions and named queries see
[A subscription that spans partitions](#a-subscription-that-spans-partitions) and
[Named queries and the flag](#named-queries-and-the-flag).

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

**A `5xx` that no retry can satisfy is sent once** (**BL-1956, next train**): `500 BRANCH_SET_DAMAGED`, `500 EXACT_RESTORE_REFUSED`,
`500 BULK_LOAD_CORRUPTION`, `503 FILE_FORMAT_REFUSED`, `503 DATABASE_QUARANTINED`, `503 LEGACY_WAL_PRESENT`, `503 RESTORE_INCOMPLETE` and
`503 FORMULA_NOT_MAINTAINED` each wait for an operator (a file restored or repaired, a database unquarantined or restored, a branch made again)
or for the node's state to change. A `retryPolicy` does not re-send them, even a read, and they do not count toward the circuit breaker —
before, a branch list over a damaged branch file was sent four times and moved the breaker that guards every other call of the client. The C#
client's list is the same. `FILE_FORMAT_REFUSED` is typed `AoudaServerError` and
`AUTH_SESSION_NOT_FOUND` (`404`, a revoke of a session that does not exist) `AoudaNotFoundError`; both were a plain `AoudaApiError`.

**A request no idle server could serve is `400 STATEMENT_TOO_LARGE`**, thrown as `AoudaValidationError` (**BL-1706, next train**; it
was a plain `AoudaApiError`) and never re-sent: the same request is refused the same way. `details` says what to do — a write: send
fewer rows in one request, or have the operator raise the database's memory share or the server's memory budget; a read: narrow the
statement. Before, a write this large waited and was refused `503 MEMORY_BUDGET_EXCEEDED` with a `Retry-After`, every time, and a
`retryPolicy` re-sent it to its bound. See the [error codes](../reference/http-api.md#request-validation-errors-4xx).

**A read whose materialized query's result was replaced while it was starting is `409 MQ_RESULT_REPLACED`**, thrown as
`AoudaConflictError` (**BL-1932, next train**) and re-sent under a `retryPolicy`: nothing was read, and the next read is bound to the
query's current result. The server answers it when the query was dropped and re-created with other columns during the read (or its
result rebuilt more than four times during it); it was `500 INTERNAL_ERROR` on `/query` and `400 INVALID_REQUEST` on
`materializedQueries.query`, which were not re-sent.

**A realtime message larger than the server reads in one is `MESSAGE_TOO_LARGE`** (**BL-1938, next train**): 64 KiB before
authentication, `Aouda:WebSocket:MaxMessageBytes` (4 MiB by default) after. On a WebSocket a write stream whose frame is refused this
way ends with `AoudaWriteStreamError` of that `code`, and the frame is not sent again; on long-poll the `/send` is `413` and rejects
with `AoudaValidationError` of that `code` (a send that did nothing, never retried), so the write rejects alone. The code is exported
(`MESSAGE_TOO_LARGE`) and typed `AoudaValidationError` on an HTTP answer too. Send fewer rows in one frame.

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
  column.decimal('price', ['187.50', 410.25, undefined], 4),     // undefined = absent: insert and bulkLoad apply the default
  column.bool('open', new Uint8Array([1, 0, 1])),
).validate();

await client.table('trades').bulkLoad([batch]);   // one batch, an array, or a (async) generator of batches
await client.table('trades').insert(batch);       // one insert; frames once the server has advertised them
```

| Factory | Values | Kind on the wire |
|---|---|---|
| `column.int64(name, values)` | `BigInt64Array`, a `Float64Array` of safe integers, or numbers / bigints | Int64 |
| `column.uint64(name, values)` (**BL-1775, next train**) | `BigUint64Array`, or non-negative safe integers and bigints up to 18446744073709551615 | Int64, flagged unsigned (a `UInt64` column stores each value exactly; an unflagged negative is refused there) |
| `column.double(name, values)` | `Float64Array` or numbers (NaN and the infinities are carried) | Double |
| `column.bool(name, values)` | `Uint8Array` of 0 / 1, or booleans | Bool |
| `column.string(name, values)` | strings | String (a dictionary of the values each frame's rows use) |
| `column.dictionary(name, dictionary, codes)` | the distinct values and one `Uint32Array` code per row (Arrow / Parquet dictionaries) | String |
| `column.timestamp(name, values)` / `column.timestampTicks(name, ticks)` | `Date`s or epoch ms / `BigInt64Array` of 100-ns ticks since the Unix epoch | Timestamp |
| `column.decimal(name, values, scale)` / `column.scaledDecimal(name, unscaled, scale)` | numbers or decimal text at one scale / `BigInt64Array` of unscaled values | ScaledDecimal (a server `Decimal(p,s)`) |
| `column.nulls(name, length)` | — | Null |

A typed array is kept as it is, not copied: do not change it until the call that sends it has returned. A plain array may
hold `null` (a null cell) and `undefined` (an **absent** cell — not given, so a generated id or the column's default applies;
a bulk load applies it too); a typed array takes `{ nulls, absent }` bitmaps. **Call `validate()` while building
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

### Array columns (**BL-035, 0.9.0**) {#array-columns}

(**BL-035, 0.9.0**) The six [array column types](../guides/array-columns.md) read and write as typed arrays, **the same type on
every surface**: query results (frames or JSON), named queries, materialized queries, WebSocket and long-poll subscriptions.

| Server type | Read as | Write with |
|---|---|---|
| `Double[]` (**BL-035, 0.9.0**) | `Float64Array` | `Float64Array` or `number[]` |
| `Float32[]` (**BL-035, 0.9.0**) | `Float32Array` | `Float32Array` or `number[]` |
| `Int32[]` (**BL-035, 0.9.0**) | `Int32Array` | `Int32Array` or `number[]` |
| `Int64[]` (**BL-035, 0.9.0**) | `BigInt64Array` (exact past 2^53, from JSON too) | `BigInt64Array`, `bigint[]` or `number[]` |
| `Byte[]` (**BL-035, 0.9.0**) | `Uint8Array` | `Uint8Array` (in a `ColumnBatch`, also a `number[]` of 0–255) |
| `String[]` (**BL-035, 0.9.0**) | `string[]` | `string[]` |

A null cell is `null`; an empty array is an empty typed array. `AoudaArrayValue` is the union of the six read types and
`AOUDA_DATA_TYPES` lists every column type, the six array names included. A row object with arrays is inserted as JSON; a
`ColumnBatch` goes as frames when the server advertises them, else as JSON column arrays
([the factories](#column-batches-lead-s14-060) gain `doubleArray`, `float32Array`, `int32Array`, `int64Array`, `byteArray` and
`stringArray`, taking one array per row: a typed array is kept, a plain numeric array is converted once, a `string[]` is kept as it is (do not
change it before the send), and `null` is a null row).

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

**The client does not repeat the server's limits for a row object**, but it refuses NaN and the infinities in a
`Float64Array` / `Float32Array` (a `RangeError`; in a plain `number[]`, `JSON.stringify` writes them as `null` and the server
refuses the null element), and checks a `ColumnBatch` before sending (`validate()`): at most 65,536 elements and 1 MiB a value, finite floats, no lone
surrogate. A `float32Array` factory rounds a plain `number` to the nearest float once, at construction; `int32Array`, `int64Array`
and `byteArray` refuse an out-of-range element with a `RangeError`. A frame column's rows are fresh typed arrays you may keep and change.

```text
RangeError  Value '0': element 0 is NaN; array elements must be finite numbers (NaN and ±Infinity are refused).
AoudaApiError (ARRAY_COLUMN_UNSUPPORTED)  … an array column cannot be used in a where (an array column can only be selected — ADR 0067 D-5).
```

An array column cannot be filtered, ordered, grouped, aggregated or joined on, in the builder or in a named query. The
generator (`npx @aouda/client generate` ([Type Generation CLI](#type-generation-cli)) or `GET /api/databases/{db}/schema/typescript`) writes the read types above for rows and tables,
and for a named mutation's arguments a union that also takes a plain array (`Float64Array | number[]`); `aouda generate typescript`,
which works offline from a schema file, writes the named queries' and mutations' types the same way, and no table types.

A client older than this train fails on a framed response with an array column (*"Malformed column-batch frame: column '…' has
unknown kind 9."*), and on the JSON surfaces (subscriptions, materialized queries, `returning`) it does not fail: it gives plain
arrays, a `Byte[]` as base64 text and `Int64[]` elements past 2^53 rounded. Use this train's client for array columns.

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
- **A table another load holds** (**BL-1743, next train**). `conflictPolicy: "block"` (the default) waits for it, at most 30 s;
  `"failFast"` does not wait. A load that cannot have it rejects with an `AoudaConflictError` whose `code` is
  `BULK_LOAD_TABLE_LOCKED`; `JSON.parse(error.details)` names the table (`table`) and the job that holds it (`activeJobId`) — every
  member is in [the HTTP reference](../reference/http-api.md#a-table-another-load-holds-bulk_load_table_locked) — and
  `error.retryAfterSeconds` says when to call again. Nothing was committed, and neither `bulkLoad` nor `bulkLoadJobs` sends it again
  by itself. (It was a `500` from the commit.)
- **A load whose job ended for capacity** (**BL-1897, next train**) — its memory wait ran out after `:begin` — rejects with the
  server's `503`: an `AoudaApiError` coded `MEMORY_BUDGET_EXCEEDED` (or `WAL_CAPACITY_EXCEEDED`), `retryAfterSeconds` set, as a
  `:commit` refused for capacity does. Nothing was committed: wait, then run the load again. The SDK learns it with one keyed
  `:begin`, which now begins a new job (aborted). It was a `BULK_LOAD_INVALID_STATE` that lost the reason.
- **A key whose job already committed** (within `Aouda:BulkLoad:IdempotencyWindowMinutes`, 10) returns that job's handle with
  `alreadyCompleted: true` — `rowsLoaded` its durable rows, `token` its commit token — and sends nothing (it used to fail
  `409 BULK_LOAD_INVALID_STATE`). (**BL-1649, next train**) Only while the job's rows can be there: after the database is dropped and
  created again, restored to before the job, or the job's table dropped, the same key loads again. A key whose job loaded several
  tables, some of them dropped since, rejects with an `AoudaConflictError` coded `BULK_LOAD_JOB_EXISTS` and loads nothing — load
  what is missing under a new key ([idempotency keys](../reference/http-api.md#idempotency-keys-bl-1649-next-train)).
- **A bulk load refuses a column its table does not have and a missing key** (**Lead S27a, 0.6.0**; BL-1130, BL-1129). With
  `validation: "strict"` it also refuses a null in any NOT NULL column, and a key the job holds twice or the table already holds
  fails the job (`409 BULK_LOAD_DUPLICATE_PK`, an `AoudaApiError` with that `code`); `handle.validation` names the level.
  See [A load's validation](../guides/bulk-load.md#a-loads-validation-coerce-or-strict-lead-s27a-060).

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
takes the database's level for a load: `'os'` in a database at `os` (`'strict'` when every table of the job names `strict`), `'strict'` everywhere else.

```typescript
const handle = await client.table('trades').bulkLoad(batches, { durability: 'os' });
handle.durability;   // 'os'
```

`'os'` skips the fsync before the commit. After a power loss before the server has synced the job, the job is dropped whole and
`GET .../bulk-load/{jobId}` reads `state: "lost"`, `errorCode: "BULK_LOAD_LOST"`: run the same `bulkLoad` again with the same
`idempotencyKey`. `'os'` for a multi-table job, a table with vector columns, or an edge or
vector table is refused `400 BULK_LOAD_INVALID_OPTIONS` — such a job in an `os` database names `durability: 'strict'`, which is allowed there. See [A load's durability](../guides/bulk-load.md#a-loads-durability-strict-or-os-lead-s26c-060).

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

(**BL-1788, next train**) An update acts on **every** row its conditions (`where`, `whereGroup`) match; nothing else of the query travels
with it. A query that names fewer rows another way is refused before anything is sent: `update() cannot carry the query's limit(): …`. Up to
0.17.0 the rest was dropped, and `.where(…).limit(1).update(…)` updated every match. What each call carries and refuses (the .NET client's
rule):

| Call | Carries | Refuses, sending nothing |
|---|---|---|
| `update()` | the conditions | `limit`, `offset` > 0, `latestPerKey` / `firstPerKey`, a join, an aggregate, `groupBy`, `distinct` |
| `delete()` | the conditions, `limit`, `orderBy` | `offset` > 0, `latestPerKey` / `firstPerKey`, a join, an aggregate, `groupBy`, `distinct` |
| `truncate()` | — (it is the whole table) | any condition, `limit`, `offset` > 0, and the shapes above. Use `delete()` for some of the rows |
| `batch()` | each operation's conditions, an update's values, a delete's `limit` and `orderBy` **members** | any state on the query it is called on; anything but conditions on a callback's query; `limit` / `orderBy` on an update; `update` beside `delete: true`; a member an operation does not have |
| `subscribe()` | the conditions and [`options.filter`](#a-subscriptions-filter) | `latestPerKey` / `firstPerKey`, a join, an aggregate, `groupBy`, `distinct` |

`select` and `selectExpr` (they shape an answer), an `orderBy` on an update (without a limit it names no rows), and `limit` / `offset` /
`orderBy` on a subscription (a stream of changes, not a window) have no effect and are not refused — except in a `batch()`, which refuses
all of them. `insert`, `insertMany`, `bulkLoad` and `openWriteStream` name their own rows and do not use the query's state.

### Delete

```typescript
await client.table('users')
  .where('id', '=', 123)
  .delete();

// The ten oldest
await client.table('events').where('level', '=', 'debug').orderBy('at').limit(10).delete();
```

`limit` and `orderBy` are carried; the rest is refused as [Update](#update) says (**BL-1788, next train**).

(**Horizon, 0.5.0**) A delete whose only condition is the table's first cluster column (a `Timestamp` or `Date`) `<` or `<=` a
time — no `limit`, `orderBy` or `returning`, on a tabular table with no vector column that no foreign key references (an edge
table takes the row path) — costs metadata, not rows: on a table with retention it raises the table's horizon (an
early expiry), on any other table it is one log record and whole segments retired. See
[Retention — Deleting everything before a time](../guides/retention.md#deleting-everything-before-a-time).

---

## 8) Schema Management

### Databases

`client.databases.create(name, options)` (**BL-1123, 0.6.0**) sends `kind` and `auth` only when the caller sets each one, and sends both when the caller sets both. On `auth`, `enabled` and `database` are included only when set there. The server rejects `kind: "auth"` together with an `auth` object (400). `kind: "data"` with `auth` is valid. Sign-up is not an option of the call: set it with `client.access.authDatabase(name).signup.set(...)`; the removed sign-up options throw, naming it (**BL-1464, 0.16.0**).

(**Lead S26, 0.6.0**) A database's durability level is `options.durability` — `'strict'` (the server's default when
omitted), `'os'`, `'unlogged'` or `'memory'` (the `DurabilityLevel` type), sent only when set. It replaces `enableWal` (`false` is
`'unlogged'`) and `dataDurability` (`'MemoryOnly'` is `'memory'`); the client no longer sends either, and the server refuses both as
members the body does not have, `400 REQUEST_MEMBER_UNKNOWN` (**BL-1832, next train**). `DatabaseOptionsInfo` reads `durability` in place of the boolean `enableWal`; a table's detail carries
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

**A refused rename** (**BL-1902, BL-1903, next train**): `renameTable`, `renameColumn` and `alterColumn` with a `newName` reject with an
`AoudaConflictError` coded `TABLE_RENAME_REFERENCED` or `COLUMN_RENAME_REFERENCED` (409) while a materialized query, a named query or
mutation, or an access-policy statement names the table or reads the column (a statement also refuses renaming a column to a name its
`where` reads). The message names each definition and nothing was
changed; it is not retried. Drop or redefine them, rename, then re-create them by the new name. See
[the HTTP API](../reference/http-api.md) (`COLUMN_RENAME_REFERENCED`). Before, the same `409` was a plain `AoudaApiError`.

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

Branches are schema-level constructs managed via `client.branches`. `create` takes the parent as `from` (`main` when left out); `parentBranch`, a second name of it, is refused by name (**Operability S25b, next train**). Data operations always target the current database; branch-scoped data queries are not supported directly on `TableQuery`.

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

An `onSnapshot` callback receives the initial consistent snapshot of existing rows when the subscription first connects:
`onSnapshot(rows, version, totalMatches, snapshot)`. `snapshot` is the whole snapshot event — `horizon`, `horizonColumn`, `horizonColumnType` and `token`
as the async iterator's snapshot event carries them (**BL-1068, next train**); a callback of two or three parameters is unchanged.

**Dates and timestamps in a subscription** (**BL-1391, 0.11.0**). A snapshot page names a `Timestamp` or `Date` column in
`column_types`, and the SDK hands a JavaScript `Date` for both, in the snapshot and in every later change's `row` and `prev` — by the
names each message carries (**BL-1866, next train**: a change names them too, and the SDK keeps nothing from a snapshot for later
changes, so a resumed change is typed and a column made again as a number is a number). A `Timestamp` arrives on the wire as .NET ticks (UTC) and becomes its instant, rounded to the millisecond.
A `Date` arrives as whole days since 1970-01-01 and becomes a `Date` at **00:00:00 UTC** of that day: read it with `getUTCFullYear()` /
`getUTCMonth()` / `getUTCDate()` or `toISOString().slice(0, 10)`, never the local-time getters. **Breaking for a caller that read the
day number itself.** A change event's own `key` payload (a delete) stays the wire value. Query results are different: there a `Date`
column is still the day number.
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

A filter may use any operator the query builder has, `in` and `notIn` (the wire's `nin`) included
(`.where('severity', 'in', ['error', 'fatal'])`). (**BL-1226, 0.9.0**) A server up to 0.8.0 refuses a subscription whose filter
uses `in` or `notIn` with `INVALID_SUBSCRIPTION_FILTER` ("IN/NIN value must be an array"); the client's request was correct.

<a id="a-subscriptions-filter"></a>
**The builder's conditions and `options.filter` together** (**BL-1788, next train**; BL-1661). A row is delivered when **both** select it.
`options.filter` takes the wire's two forms, with or without conditions on the query:

```typescript
client.table('events').where('level', '>=', 3)
  .subscribe({ filter: { severity: { eq: 'error' }, region: { in: ['eu', 'us'] } } }); // shorthand: one operator per column, all must hold

client.table('events').where('level', '>=', 3)
  .subscribe({ filter: { or: [                                                        // structured: and / or / groups
    { column: 'severity', op: 'eq', value: 'error' },
    { column: 'severity', op: 'eq', value: 'fatal' } ] } });
```

Beside conditions on the query, the client throws, sending nothing, for an `options.filter` with no condition (`{}`, `{ and: [] }`) and for a
shorthand column that is not exactly one operator with its value (use `{ and: [...] }` for two on one column). A structured filter's own
mistake — an unknown member, an empty group — is the server's to refuse, `INVALID_SUBSCRIPTION_FILTER`, by name. The combination adds one
`groups` level, and a filter nests at most five. Up to `@aouda/client` 0.17.0 the two were merged member by member: a structured
`options.filter` **replaced** the query's lists of the same name, so the subscription saw rows its `where` excludes, and a shorthand one was
refused. The server refuses a filter with no condition (`{}`) given alone: to subscribe to every row, give no filter. (**BL-1853, next
train**) Given as `options.filter` with nothing on the query, `{}` is its own subscription, refused by the server; it used to share the
whole table's subscription and receive every row.

**Which listener takes this.** `client.table(t).subscribe(...)` is a **table subscription** (a table and a filter). It works on the
**admin** listener, for a principal with `read` on the table. The **data-plane** listener, the one browsers reach, refuses
it with `NAMED_QUERY_SUBSCRIBE_REQUIRED`: its callers cannot compose a query, so they subscribe **by name**
(`client.namedQueries.subscribe(name, args)`, see [Named queries](../guides/named-queries.md#subscribe-by-name)). A trusted backend that
wants a filtered table subscription connects to the admin listener with its key. Do not work around the error by moving the
filter into a different request: there is none, by design ([Direct client access](../guides/direct-client-access.md)).

**What a subscription sees** (**BL-1227, 0.9.0**). A subscription's snapshot and its change events hold the rows the caller's `read`
statements admit, as an HTTP query by the same credential does; `subscribe` is authorized as that query is (`read` on the table; for a named
query `execute` on it), and the server re-reads the principal's statements on every `subscribe`. Every credential that works over HTTP on the
database opens its socket too. How it works: [Real-time Streaming](../guides/real-time.md#who-may-subscribe-and-what-a-subscription-sees).

#### A subscription that spans partitions

On a partitioned table that requires a partition filter, a subscription that names no partition is refused with
`PARTITION_FILTER_REQUIRED`, as the read would be. A trusted backend that really wants every partition's events asks for the waiver,
either on the builder or in the options; if both ask, the subscription asks once, and neither cancels the other (**BL-1227, 0.9.0**).

```typescript
// On the query builder
const sub = client.table('orders')
  .withCrossPartitionAccess()
  .subscribe({
    onSnapshot: (rows, version) => console.log('Initial rows:', rows.length, version),
    onChange: (event) => console.log(event.op, event.row ?? event.key),
  });

// Or in the subscribe options (SubscribeOptions.crossPartitionAccess)
const sub2 = client.table('orders')
  .where('status', '=', 'open')
  .subscribe({
    crossPartitionAccess: true,
    onChange: (event) => console.log(event.op, event.row),
  });
```

The SDK sends `cross_partition_access: true` on the `subscribe` message, only when you ask, and sends it again on every resubscribe after
a reconnect. **It is a cost waiver, not a grant**: it waives `PARTITION_FILTER_REQUIRED` and nothing else, so the snapshot and the events
are what the caller's `read` statements admit (a statement with no `where` admits every partition, those created
later too; one whose `where` names the partition column, only the partitions it admits). The data-plane listener ignores it. An older server ignores the field and
answers `PARTITION_FILTER_REQUIRED` ([compatibility](compatibility.md)). The wire rule:
[A subscription that spans partitions](../guides/partitioning.md#a-subscription-that-spans-partitions).

#### Named queries and the flag

A named query that binds no partition key on a partitioned table is refused `PARTITION_FILTER_REQUIRED` too, on `execute()`,
`batch()` and `subscribe()`. Each takes the flag **per call**, as a sibling of the arguments (**BL-1227, 0.9.0**). A definition
cannot set it, and there is no batch-wide switch: each batch item carries its own.

```typescript
import type {
  NamedQueryBatchItem,
  NamedQueryBatchOptions,
  NamedQueryExecuteOptions,
  NamedQuerySubscribeOptions,
} from '@aouda/client';

// execute(name, args, NamedQueryExecuteOptions)
const execOptions: NamedQueryExecuteOptions = { crossPartitionAccess: true };
const open = await client.namedQueries.execute('orders_by_status', { status: 'open' }, execOptions);

// batch(items, NamedQueryBatchOptions): the flag is on the item; the options hold { signal?, atLeast? }
const items: NamedQueryBatchItem[] = [
  { name: 'orders_by_status', args: { status: 'open' }, crossPartitionAccess: true },
  { name: 'customer_card', args: { id: 7 } },
];
const batchOptions: NamedQueryBatchOptions = { signal: AbortSignal.timeout(10_000) };
const slots = await client.namedQueries.batch(items, batchOptions);

// subscribe(name, args, NamedQuerySubscribeOptions)
const subOptions: NamedQuerySubscribeOptions = {
  crossPartitionAccess: true,
  onChange: (event) => console.log(event.op, event.row),
};
const live = client.namedQueries.subscribe('orders_by_status', { status: 'open' }, subOptions);
```

The flag is sent only when it is `true`. It waives the guard and widens nothing: the rows are the credential's grants. Alternatively bind
the partition key in the definition's `where` clause, which needs no flag and works on the data-plane listener, where the flag is
ignored ([`crossPartitionAccess` on the data-plane listener](../guides/browser-tier-read-limits.md#crosspartitionaccess-on-the-data-plane-listener)).

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
  onSnapshot: (snapshot, _version, _total, event) => { rows = applyNotice(snapshot, event); },
  onChange: (event) => { /* insert / update / delete, as before */ },
  onHorizon: (event) => { rows = applyNotice(rows, event); },
  onRangeDelete: (event) => { rows = applyNotice(rows, event); },
});
```

The snapshot's horizon is read after the snapshot, so for a moment the snapshot can hold a row below it (a `horizon` event then
follows): apply it to the snapshot event too — `applyNotice(rows, snapshotEvent)` in the async iterator, and in the callback style
the fourth argument of `onSnapshot` is that event (**BL-1068, next train**; before it the callback received no horizon, and a
callback-only client dropped those rows at the next `horizon` event instead).

A client older than this ignores both messages, so its rows include ones the server no longer returns until it subscribes again. A
`TRUNCATE` sends no notice. The wire contract: [Real-time Streaming — Horizons and range deletes](../guides/real-time.md#horizons-and-range-deletes).

#### Embargoed tables (**BL-418, 0.9.0**)

A principal whose `read` statements on a table all carry [`embargoSeconds`](../auth/authorization.md#embargo)
reads it on a delay: queries return only rows at least N seconds old, and a subscription's changes arrive as they come of
age. Nothing changes in the calls you make. Two error codes are exported for it:

- `AUTH_EMBARGO_UNSUPPORTED` — thrown as an `AoudaApiError` (`403`) by a read that cannot be cut by a row time: a materialized
  result, graph traversal, vector search, and a named mutation whose `execute` statements are all embargoed. An embargo refuses no write
  (**BL-1464, 0.16.0**): an insert needs a `write` statement, as always. Retrying with the same credential gets the same answer.
- `SUBSCRIPTION_EMBARGO_RESET` — the server ended the subscription: it held back more changes than its limit, or the credential's
  embargo changed. The `Subscription` **resubscribes fresh by itself** (a new snapshot, no `resume_from`) and your `onSnapshot`
  receives it. A second reset before that snapshot arrives goes to `onError`, as any other subscription error does.

```typescript
import { AoudaApiError, AUTH_EMBARGO_UNSUPPORTED } from '@aouda/client';

try {
  await client.table('latest_quote').execute(); // a materialized result
} catch (err) {
  if (err instanceof AoudaApiError && err.code === AUTH_EMBARGO_UNSUPPORTED) {
    // This principal reads `latest_quote` on a delay only, and a result cannot be cut by one caller's delay.
  }
}
```

#### One connection, many subscriptions

Every subscription and write stream on a client shares **one** WebSocket per
`(serverUrl, database)`. `subscribe()` on an already-connected client reuses that socket; it does
not open another. Bind as many live views as the application needs — a list, a detail pane, a
presence feed — and they multiplex.

**Identical subscribes share one server subscription** (**BL-1384, 0.11.0**). Every `subscribe`
on one client — `client.namedQueries.subscribe(name, args, options)` and
`client.table(name)…subscribe(options)` — is shared by *(name or table, arguments or filter,
options)*. The first opens the server subscription, later identical ones join it, and the last one
to unsubscribe closes it. Arguments and filters are compared by content, not by the order of their
keys; the options that count are `conflate`, `atLeast`, `waitMs`, `onExceeded`, `orderByIndex` and
`crossPartitionAccess`. Twenty components binding the same view cost the server one subscription,
not twenty. This holds over the WebSocket and over the long-poll fallback alike. There is no opt-out:
for an independent stream, use another client instance.

What stays yours, per call: `onSnapshot`, `onChange`, `onError` (and the notice callbacks), your
own event iterator, and `keyOf` (it fills `key` on *your* insert and update events, which arrive
with `key: null`). A consumer that joins an entry already running is handed the rows the entry
holds as a snapshot, then its own `snapshot` event — no second request reaches the server. One that
joins while the snapshot is still arriving, or while the client re-subscribes fresh, waits for it. (A joiner's callbacks run a
microtask after `subscribe()` returns.)
Rows are shared between consumers, not copied: treat them as read-only.
A callback that throws (and a throwing `keyOf`) is reported to *that* consumer's `onError` — logged with `console.error` when it has
none — and never stops the others receiving the event. `for await … break` disposes the consumer. Arguments the key cannot represent
(a `Map`, a `Set`, a class instance, an invalid `Date`, a cycle) make that subscribe unshared; `args: {}` and no args are one query.

Four cases do **not** share, and the consumer gets a server subscription of its own:

- a subscribe that passes `resumeFrom` (it asks for a position in the stream);
- a late joiner when the entry holds more than 100 000 rows (a fixed SDK limit that equals the server's default `MaxSnapshotRows`; changing the server key does not change it);
- a late joiner when the entry's rows cannot be kept current — most often a projection that omits
  the primary key, so a `delete` (which carries only the key) cannot be applied;
- anything with different arguments or options.

A consumer that falls more than 10 000 events behind its own iterator is ended with a plain `AoudaError` (no dedicated class or `code`, unlike the C# SDK's `CLIENT_CONSUMER_OVERFLOW`) in `@aouda/client` before **0.12.0**; the
other consumers of the subscription and the server subscription are not affected. (**BL-1421, 0.12.0**) From `@aouda/client` 0.12.0 (npm, 2026-11-12) the bound is
`AoudaClientOptions.subscriptionConsumerQueueCapacity` (default 10 000, an integer of at least 1, refused at construction otherwise) with a
per-subscription `consumerQueueCapacity` on `subscribe` (table and named query) that is not part of the sharing key, and overflow ends the consumer with the new
`AoudaConsumerOverflowError` (`code: "CLIENT_CONSUMER_OVERFLOW"`) on its iterator and `onError`, carrying the C# SDK's message. The old message text is gone; match on `code`.
(A consumer
driven by callbacks that is never iterated is not "behind": past that many unread events it stops
queuing, and iterating it afterwards throws.)

**The protocol version** (**BL-1830, next train**). The client speaks protocol version `3` (`PROTOCOL_VERSION`, exported with
`PROTOCOL_VERSION_HEADER` and `PROTOCOL_VERSION_UNSUPPORTED`) and names it on every request — data, auth and long poll, set last so a
`defaultHeaders` entry cannot override it — and in the realtime `auth` (`protocol_version`). `localNetworkFetch`, which an application
may use for any URL, stamps nothing. A server of another version is refused by name: **`AoudaProtocolVersionError`** (an
`AoudaApiError`, code `PROTOCOL_VERSION_UNSUPPORTED`, with `serverVersion` — `null` when it named none — and `clientVersion`), from an
HTTP call, an auth call, the WebSocket handshake and long poll. It is **terminal**: not retried, not counted by the circuit breaker or
`authFailurePolicy`, no reconnect and no fallback to long poll, and every subscription and write stream ends with it. The client also
refuses a server whose `auth_ok` names another version, or has no `protocol` block: the connect rejects with the same error. Use the
client release published with the server ([compatibility](compatibility.md#the-protocol-version-one-rule-bl-1830-next-train)); before
this train the client sent `"1"` and the refusal was an `AoudaValidationError` coded `UNSUPPORTED_VERSION`.

**Server limits and refusals** (**BL-1383, 0.11.0**). `client.serverLimits` holds what the server sent in `auth_ok` —
`limits` (`maxSubscriptionsPerConnection`, `maxSubscriptionsPerIdentity`, `maxConnectionsPerIdentity`, `subscribeBurst`,
`subscribeRefillPerSecond`) and `protocol` (`version`, `capabilities`) — so an application can size itself instead of meeting a hard
error first. It is `undefined` before the streaming connection is open and over the long-poll fallback (its
handshake carries none). Three refusals have typed errors, all `AoudaApiError`s (status 429) and **not** `AoudaConnectionError`s, so a
catch for connection failures does not swallow a cap:

- **`IDENTITY_CONNECTION_LIMIT_EXCEEDED`** (`AoudaConnectionLimitError`): the identity already holds its connections. It is
  **terminal** on both transports: the first `connect()` rejects with it, a reconnect stops and reports it, and every consumer of
  every subscription hears it. The client does **not** fall back to long-poll, which counts against the same limit.
- **`SUBSCRIBE_RATE_EXCEEDED`**: the server's per-identity subscribe bucket was empty. The client waits for `retry_after_ms` (or the
  long-poll `Retry-After` header) and sends the subscribe again, up to 3 times; then every consumer fails with
  `AoudaSubscribeRateLimitError` (`retryAfterMs`). A reconnect that replays more than 256 subscriptions spreads the rest out (one every
  40 ms) so recovery does not trip the bucket itself.
- **`SUBSCRIPTION_LIMIT_EXCEEDED`** (`AoudaSubscriptionLimitError`): the server's message, which names the cap and the count, is the
  error's `message`, unchanged.

A reconnect's backoff starts over only after the connection has **stayed up for 10 seconds**, not as soon as `auth_ok` arrives, so a
server that authenticates and then closes is retried at 1, 2, 4, 8 … seconds rather than once a second.

If the server refuses a shared subscription (an `error` message), **every** consumer of it hears: its
`onError` is called and its iterator throws. `client.activeConsumers` and
`client.activeServerSubscriptions` count the client's consumers and its open server subscriptions;
their ratio is how much sharing the application gets.

The transport owns reconnection. On a drop it reconnects with exponential backoff and jitter, then
re-sends each live server subscription — **once per shared subscription**, whatever the number of consumers — with `resume_from` set to the last version it saw, so the server
can replay from its buffer or fall back to a fresh snapshot. A `gap` is answered the same way.
(**BL-1823, next train**) A version is a number of one change stream, which the server starts again at every open of the database's engine
(a restart, a restore, an unquarantine, a drop and create, a replica's checkpoint): the SDK keeps the stream the last snapshot named and
sends it as `resume_stream`, and resumes nothing when no stream is known. A resume of a stream the server no longer has is answered with a
fresh snapshot, delivered to `onSnapshot` like any (its versions may be lower). Up to 0.17.0 a reconnect after a plain server restart was
told it was current, and what it missed was lost.

**Resuming a subscription you kept** (**BL-1823, next train**). `subscription.resumePoint` is `{ stream, version }` — the stream the
snapshot event names (`snapshot.stream`) and the last version seen — or `undefined` before a stream is known. Pass it as `resumeFrom` to
continue from there: `table.subscribe({ resumeFrom: saved })` (and `namedQueries.subscribe(name, args, { resumeFrom: saved })`). It used to be
a number (`resumeFrom: 41`), which no longer compiles.
Subscription ids are stable for the life of the `Subscription` object and are reused across
reconnects, which is what the server expects — see [the `id`
contract](../reference/http-api.md#subscribe).

> **Fixed in 0.1.25 (`BL-635`), released 2026-09-23.** Before that release `connect()` was not idempotent:
> each subscription's start opened its **own** socket, orphaning the previous one — still open,
> unpinged, still delivering — and overwriting the single pair of handshake callbacks, so one
> socket's `auth_ok` completed a different socket's `connect()` and the rest never settled. An
> application binding several live views in one tick got several server sessions, and the
> reconnect replay could then land a subscription id on a session that already held it. The server
> refused it with `DUPLICATE_SUBSCRIPTION_ID`, the client treated any subscription error as fatal
> and unsubscribed, and the view stayed dead until a page reload. If you are pinned below 0.1.25
> and cannot upgrade, the workaround is to bind one subscription per client instance; the real fix
> is the upgrade.

**A message the client cannot read** (**BL-1833, BL-1835, next train**). A message from the server that is not readable — malformed JSON, undecodable
MessagePack, a binary frame in the `json` wire mode, a `Blob` (a `wsFactory` socket without `binaryType: "arraybuffer"`), something
that is not an object with a string `type`, or a long-poll answer without `messages` — ends the connection, and every subscription and
write stream on it, with an `AoudaServerMessageError` (`code: "SERVER_MESSAGE_UNREADABLE"`, `reason`). It names the size, never the
content. There is no reconnect, because the same bytes would come again; the next `subscribe` or `openWriteStream` opens a new
connection. On long-poll the messages before the unreadable one are delivered first. A message of an **unknown `type`** is ignored, as
the protocol says. Before, the message was dropped and the subscription went on past it. If the unreadable message arrives while the
connection is being opened, only that attempt fails.

**While the connection is being opened** (**BL-1836, BL-1840, next train**) the client sends nothing but `auth`, and an `error` from the server
(`CONNECTION_LIMIT_EXCEEDED`: the server is full) fails that attempt only: a first connect rejects with an
`AoudaConnectionRefusedError` (its `code` is the server's) or falls back to long-poll, and a reconnect goes on with its backoff and then
resumes the subscriptions. Before, it ended every subscription. A connection that stops answering pings is closed and reconnected
(**BL-1839, next train**; before, the close threw in a browser and in Node.js, and nothing reconnected).

**When the client switches to long-poll** (**BL-1848, next train**). With `streaming.enableLongPollFallback` (the default), a `subscribe` or
`openWriteStream` that cannot connect over the WebSocket tries long-poll. If long-poll connects, the client stays on it, and what the
WebSocket carried moves there as after a reconnect: subscriptions resume, streams follow the rule under [write streams](#write-streams), and
the WebSocket is closed. If long-poll fails too, the call rejects, and the subscriptions and streams there are stay with the WebSocket's
reconnect. Before, they were left behind and went silent. A `subscribe` or `openWriteStream` made while a lost WebSocket waits for its
reconnect connects at once, and that connection is the reconnect (**BL-1849, next train**). The same holds over long-poll: the session it
opens is the reconnect's, and is polled from then on (**BL-1860, next train**; before, the call failed with `Long-poll session is not
connected`).

#### When the database is replaced (**BL-1818, next train**)

When the server replaces a subscription's database under it — a set restore, a quarantine and unquarantine, a drop and create, a replica's
checkpoint — it ends the subscription with `SUBSCRIPTION_DATABASE_REPLACED` (exported) on the open connection. The `Subscription`
**subscribes again by itself**, fresh (no `resume_from`), and your `onSnapshot` receives the new engine's rows; its changes follow. The
versions may be lower than before. It makes at most five attempts between two snapshots that land, after 0, 250, 500, 1000 and 2000 ms;
past that the code goes to `onError` as an `AoudaSubscriptionServerError`. A consumer that joins the shared subscription meanwhile waits
for the new snapshot and is never handed the replaced engine's rows. `DATABASE_QUARANTINED` and `DATABASE_NOT_FOUND` end the subscription
(`onError`): the database has no engine any more. Up to 0.17.1 such a subscription went silent until the server restarted. See
[When the database is replaced](../guides/real-time.md#when-the-database-is-replaced-bl-1818-next-train).

### Write streams

```typescript
import { AoudaWriteStreamError, STREAM_INTERRUPTED, STREAM_ROW_REJECTED } from '@aouda/client';

const stream = await client.table('quotes').openWriteStream({ mode: 'upsert' });
try {
  await stream.write({ symbol: 'AAPL', price: 191.2 });
  await stream.write([{ symbol: 'MSFT', price: 402.1 }, { symbol: 'NVDA', price: 875.3 }]);
  await stream.close(); // resolves only when the server acknowledged every frame
} catch (err) {
  if (!(err instanceof AoudaWriteStreamError)) throw err;
  if (err.code === STREAM_ROW_REJECTED) {
    console.error(`frame ${err.refusedSeq}: refused rows`, err.rowErrors); // its other rows were written
  } else if (err.code === STREAM_INTERRUPTED) {
    // The outcome of `err.unacknowledgedFrames` frames after `err.lastAcknowledgedSeq` is unknown. Read back what is there,
    // or send the rows again on a stream in `upsert` mode, where the same row twice is one row.
  } else {
    console.error(err.code, err.serverMessage, err.rowErrors, err.remedy); // the server's refusal
  }
}
```

(**BL-1776, BL-1834, BL-1627, next train**) What a stream promises:

- **`write()`** sends one frame and resolves when the frame was **sent**, so writes can be pipelined. Frames are sent one at a time, in call
  order, on the WebSocket and on the long-poll fallback alike (before, the fallback could deliver pipelined frames out of order, and rows were lost).
- **`close()`** resolves only when the server acknowledged **every** frame. Calling it twice gives both callers the same outcome.
- **A stream that lost a row, or cannot know, says so.** It ends with an `AoudaWriteStreamError`; the first error is kept, the
  waiting and the next `write()` and **every** `close()` reject with it, and no frame behind it is sent. Before, a refusal that arrived between two
  calls was dropped and `close()` resolved.
- **A frame is never sent again** by the client, in either mode: an insert sent twice is two rows.
- A `write()` that **did not leave the client** (not connected, or a value that cannot be encoded) rejects alone, and the stream goes on.
  `AoudaConnectionError.reachedServer === false` says so; an encoding failure is the platform's own error, e.g. a `TypeError`.

| What happened | `code` of the error |
|---|---|
| The server refused a frame, the open or the close (`error`) | The server's code, with its `rowErrors` and `remedy`. The refused frame was not acknowledged; none behind it was written. Some rows of the refused frame may have been written when it also held rows a write statement refuses |
| The server refused **some rows** of a frame (a `stream_ack` with `errors`) | `STREAM_ROW_REJECTED`; `rowErrors` names the rows of frame `refusedSeq`, whose other rows were written |
| The connection was lost and came back with a frame unacknowledged; the server closed the stream, or `stream_closed` came with one unacknowledged; a send failed that may have reached the server; `client.disconnect()` | `STREAM_INTERRUPTED`: the rows of the unacknowledged frames may or may not have been written |
| The credential was refused or ended, or a message could not be read | That code, e.g. `AUTH_CREDENTIAL_REVOKED`, `SERVER_MESSAGE_UNREADABLE`; `cause` is the connection's error |
| The stream could not be opened again after a reconnect | The server's code, or `STREAM_RECONNECT_FAILED` when the request could not be sent |

`AoudaWriteStreamError` extends `AoudaConnectionError`:

| Member | Meaning |
|---|---|
| `code`, `serverMessage` | The table above, and the message that goes with it |
| `rowErrors` | `{ index, code, message }` per refused row; `index` is the row's index in its frame. `undefined` when the server named none |
| `remedy` | The [remedy](#with-authentication) of an authorization refusal; `undefined` when there is none |
| `refusedSeq` | `STREAM_ROW_REJECTED` only: the frame `rowErrors` is about |
| `lastAcknowledgedSeq` | The last frame the server acknowledged. Frames count from 1, and again from 1 when a reconnect re-opened the stream |
| `unacknowledgedFrames` | Frames sent and not acknowledged |
| `cause` | The failure below it, if any |

**A reconnect** with every frame acknowledged re-opens the stream, and it goes on: a `write()` waits for the re-open, and the frames
count from 1 again. A stream whose `stream_close` was already sent is done when the connection is lost with every frame acknowledged, so its `close()`
resolves. `open`, `write()` and `close()` settle on every end of the connection, `client.disconnect()` included; none waits for ever.


---

## 11) Admin APIs

Full typed `client.admin.*` surface covering all server management operations.

### Health and Metrics

```typescript
const health = await client.admin.health.check();
const readiness = await client.admin.health.ready(); // { ready, reasons } (BL-1393, 0.11.0)
const metrics = await client.admin.metrics.snapshot();   // ADR 0073 (BL-851, next train)
const info = await client.admin.server.info();
```

`admin.metrics.snapshot()` is the [admin metrics contract](../reference/http-api.md#admin-metrics-bl-851-next-train) (**BL-851, next train**): an object
keyed by metric name, each `{ type, unit, points }`. `METRICS` is the catalogue (type, unit, labels and one sentence per metric) and
`MetricName` names one. `metricValue(snapshot, name, labels?)` sums the matching points — `undefined` when none matches (the server does
not know it: never `0`), `0` for an absent combination of a sparse counter; `metricIncrease(earlier, later, name)` reads a different
`server.startedAt`, or a lower value, as a reset; `metricQuantile(snapshot, name, q)` reads a histogram's buckets. `admin.metrics.history()`
takes `minutes` 1–1440 and `interval` 10–3600 (outside: `400 INVALID_REQUEST`). `summary()`, `subsystem()`, `admin.server.metrics()` and
`admin.server.databaseMetrics()` are gone with their routes.

`admin.health.ready()` returns every reason the server is not ready (**BL-1393, 0.11.0**). `ReadinessResponse` is
`{ ready, reasons }`, each reason `{ code, message, subject? }` with a stable `code` (`setup_required`, `database_pending`,
`database_not_open`, `configured_key_inactive`, `component_unhealthy`, and the rest listed under [`GET /ready`](../reference/http-api.md#get-ready)); `reasons`
is empty when `ready`. The single `reason` string is gone, so a caller that printed it prints `reasons` instead.

### Replication

```typescript
const status = await client.admin.replication.status();
const topology = await client.admin.replication.topology();
const coverage = await client.admin.replication.coverage();

// (BL-1477, next train) Which secondary is behind, per database: ask the primary. The topology's members carry no lag.
for (const member of status.members) {
  for (const [db, entry] of Object.entries(member.perDatabaseStatus)) {
    console.log(member.address, db, entry.lagBytes ?? 'unknown');
  }
}
```

(**BL-1477, next train**) `status().members` is the topology's member list with `perDatabaseStatus` and `subscriptions`; it needs `manage`
on the server. `lagBytes` is `null` when the server asked does not know the primary's position, and a member it has not heard from has an
empty `perDatabaseStatus`: both are unknown, not "no lag". `topology().members` has neither field.

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

A backup is a **set** (one id, every database, the auth database first); see [Backup and restore](../guides/backup.md). Every call below is
`client.admin.backup.*` and needs an administrator's key.

```typescript
import {
  AoudaApiError,
  BACKUP_OPERATION_TIMEOUT_MS,
  isBackupErrorCode,
  type RetentionPolicy,
} from '@aouda/client';

// Trigger backup (a set for every database)
const made = await client.admin.backup.trigger({ incremental: true });

// List backups: `complete` is false for a set a member failed, `refused` says why a record could not be read
const { backups } = await client.admin.backup.list();
const restorable = backups.filter((b) => b.complete && b.refused === undefined);

// One set: per member database, the manifest's cut, redo-start position and its branches
const detail = await client.admin.backup.show(made.backupId);
console.log(detail.members.map((m) => `${m.database} R=${m.redoStartPosition} P=${m.walPosition}`));

// Restore exact backup
await client.admin.backup.restore(made.backupId);

// Point-in-time restore — the last transaction commit <= targetTime; backupId is optional
// (omitted, the server chooses the newest backup at or before the target)
const restored = await client.admin.backup.restore({
  backupId: made.backupId,
  targetTime: '2026-05-01T12:00:00Z',
});
console.log(restored.pitr, restored.branches);

// Retention: none by default (nothing is pruned). setRetention replaces the whole policy;
// pitrWindow is a duration as the server writes it (d.hh:mm:ss)
const policy: RetentionPolicy = { keepLast: 5, pitrWindow: '7.00:00:00' };
await client.admin.backup.setRetention(policy);
console.log(await client.admin.backup.getRetention());

// Prune: a dry run by default; { execute: true } deletes what the server plans when it executes
const plan = await client.admin.backup.prune();
for (const set of plan.sets) console.log(set.backupId, set.keep ? 'kept' : 'deleted', set.rules);
await client.admin.backup.prune({ execute: true });

// Schedule
const schedule = await client.admin.backup.getSchedule();
await client.admin.backup.setSchedule({ cronExpression: '0 2 * * *', incremental: schedule.incremental });

// A backup error carries the server's code and a `remedyText`: what to do, as an instruction
try {
  await client.admin.backup.restore('no-such-backup');
} catch (error) {
  if (error instanceof AoudaApiError && isBackupErrorCode(error.code)) {
    console.error(error.code, error.remedyText);
  }
}
```

- **`show`, `prune`, `getRetention` and `setRetention`**, the `{ backupId, targetTime }` form of `restore` and **`remedyText`** are new.
  `setSchedule` takes `cronExpression` — a `cron` property was never part of the contract and is refused by the compiler (this page used to show it).
- **A backup call that runs long is not cut off at the client's 30 s default.** `trigger`, `restore` (both forms) and an *executed*
  `prune` wait up to `BACKUP_OPERATION_TIMEOUT_MS` (one hour) and take a last argument `{ timeout?, signal? }`; every other backup
  call keeps the client's default. A call that times out may still be running on the server — a retry meets `409 BACKUP_IN_PROGRESS`.
- **`remedyText`** is set on the `AoudaApiError` of every `/admin/backup/*` error (`BACKUP_ERROR_CODES` is the closed list;
  `isBackupErrorCode` narrows). It is a different member from `remedy`, which stays the structured auth remedy of a `403`.
  A backup call can also meet `DISK_FULL` (507) and `WAL_FAILED` (503): the server applied nothing, but with a `retryPolicy` set (the
  default is none) the client re-sends `trigger`, `restore` and `prune` only after a refusal that proves "not applied" — `503`
  `MEMORY_BUDGET_EXCEEDED`, `WAL_CAPACITY_EXCEEDED`, `SERVER_STARTING`, `SETUP_REQUIRED`, `429 SERVER_AT_CAPACITY` — or a connection that
  never opened, so these two reach your code: retry after `Retry-After` yourself. `setSchedule` and `setRetention` replace the whole value,
  so a repeat changes nothing, and they are re-sent after any transient failure, these two included.
- **A restore that succeeded clears the consistency tokens of the client that ran it** (**BL-1731, next train**), for every database. A restore
  rewinds the node; a token from before it is ahead of the node, and every read carrying it answers `409 TOKEN_UNSATISFIED` — again and
  again — until it is discarded. A refused restore changes nothing; nor does one whose answer never came (a timeout, a lost connection):
  the server may have gone on and restored, and then the call below is yours to make. A client that did not run the restore (another process did, or
  another client of this process) calls `client.forgetConsistencyTokens()`; a store you share between clients is cleared for all of them.
  A custom `ConsistencyTokenStore` has to implement `forget(database)` (it was optional) and `forgetAll()`: it fails to compile without them. Before this change `AoudaClient` had no
  such call: the remedy was a fresh client, or `forget(database)` on a `MemoryConsistencyTokenStore` you had passed in.
  Studio discards its data clients after a restore it ran.

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
| `aouda_backup_restore` | Restore a backup by ID — an **exact** restore only: it takes no `targetTime`, and point-in-time restore, retention and prune are not offered to an agent |
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

// ⚠️ state === Ready means READABLE, not CURRENT. Read these for currency:
//   status.current       — the server's own rule, for a reader starting now
//   status.isStale       — true when the result is readable but not up to date; omitted otherwise
//   status.staleReason   — why, in a sentence; there exactly when isStale is
//   status.currentLagMs  — how long it has BEEN behind, in whole milliseconds; null exactly when isStale
//                          is not true (BL-1477, next train)
// A caught-up idle query reports currentLagMs === null forever, not a growing number, so
// null on a Ready query means "current", never "unknown" (one that is Building, Rebuilding or in
// Error says so in state). See reference/http-api.md, "Is this query current?". Polling state alone is how twelve of thirteen queries on one production
// deployment reported Ready while holding 1.7 % of their source (BL-642, 0.1.38).
//
// For "how fresh is it", read status.stalenessMs (server 0.2.0, @aouda/client 0.2.0): the age in
// milliseconds of the oldest change the result does not reflect yet; absent when current.
// currentLagMs is not that number — under a steady insert stream it grows for as long as the
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

## 13a) Formula tables (**ADR 0072, 0.14.0**)

A table may declare an `Expression` column ([Formulas](../guides/formulas.md)): it holds a formula and **drives** one value column of the
same table. A row whose formula is `null` is an *input*, written like any row; a row with a formula is computed by the server, which keeps
its value current whenever an input it reads changes and refuses a hand-written value there. There is no model object: creating the table,
writing inputs and formulas, reading, waiting on a token and subscribing are the table calls. A whole model, step by step:
[Build a live financial model](../guides/financial-model.md).

```typescript
import { AoudaConflictError, Formula, FormulaConflictError, fx } from "@aouda/client";

// An ordinary table with one extra column: "formula" is an Expression column that drives "value".
await client.tables.createTable({
  database,
  name: "pnl",
  columns: [
    { name: "Field", type: "String", primaryKeyOrder: 1 },
    { name: "Period", type: "Int64", primaryKeyOrder: 2 },
    { name: "value", type: "Decimal", precision: 18, scale: 2, isNullable: true },
    { name: "formula", type: "Expression", drives: "value" },
  ],
});

// A row with no formula is an input. A key column a reference leaves out (Period) is the formula row's own,
// so the same formula serves every period.
const revenue = fx.cellHere("value", { Field: "Revenue" });
const cost = fx.cellHere("value", { Field: "Cost" });
const profit = fx.sub(revenue, cost);
await client.table("pnl").insertMany([
  { Field: "Revenue", Period: 2026, value: 1000 },
  { Field: "Cost", Period: 2026, value: 600 },
  { Field: "Profit", Period: 2026, formula: Formula.from(profit) },
  { Field: "Margin", Period: 2026, formula: Formula.from(fx.round(fx.div(profit, revenue), 2)) },
]);

// A read right after a write waits for the formulas (the client's own token) and answers 409 TOKEN_UNSATISFIED
// if they are still behind: read again.
async function readPeriod(): Promise<Record<string, unknown>[]> {
  for (let attempt = 0; ; attempt++) {
    try {
      return (await client.table("pnl").where("Period", "=", 2026).execute()).rows;
    } catch (e) {
      if (!(e instanceof AoudaConflictError && e.code === "TOKEN_UNSATISFIED") || attempt >= 40) throw e;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
}

// Zero revenue makes Margin a division by zero: its value is null, and explain says why.
await client.table("pnl").where("Field", "=", "Revenue").update({ value: 0 });
const why = await client.table("pnl").explain({ Field: "Margin", Period: 2026 }, "value");   // why.reason: "division by zero."

// Only the server writes a formula row's value.
try {
  await client.table("pnl").where("Field", "=", "Profit").update({ value: 5 });
} catch (e) {
  if (!(e instanceof FormulaConflictError && e.kind === "valueWriteRefused")) throw e;
}
```

- **`fx` builds the formula as the wire node; nothing is evaluated in the client.** `fx.cell(table, column, key)` reads a value of another
  table by its full primary key, `fx.cellHere(column, key)` a value of the formula row's own table, `fx.col(column)` a column of the formula
  row itself. A primary-key column left out of a `key` is the formula row's own. The functions are `fx.add`, `sub`, `mul`, `div`, `min`,
  `max`, `abs`, `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `if`, `and`, `or`, `not`, `round`, `coalesce`, `concat` and `cast`; a constant is
  `fx.lit(value)`. Arity, a null key part and a bad `cast` type are checked locally; everything else is the server's. A `bigint` is exact at
  any magnitude in a key or a literal.
- **`Formula.from(node)` is the value of an Expression column** in an `insert` or `update` row; `null` makes the row an input again. It goes
  on the wire as its JSON object. A read gives the Expression column back as a `Formula` (`null` for an input row); the type
  `GET …/schema/typescript` generates for it is `Formula | null`. A live subscription's snapshot and change rows (`row`, `prev`) give the
  Expression column as a `Formula` too, `null` for an input row (**Operability S25b, next train**; before it they carried the formula's JSON object);
  `Formula.fromValue(cell)` reads a JSON object, the formula's text or `null` to the same `Formula`. A change message does not name the
  column too (**BL-1866, next train**; it used to keep the names its snapshot gave, so a subscription that `resumeFrom` resumed, with no
  snapshot, gave the JSON object): each message is read by its own names. An integer literal past 2^53 is exact in both. `formula.equals(other)` compares two by
  structure, property order aside (`1` and `1.0` are one number in JavaScript); `formula.toString()` is its JSON text.
- **The driven column is an ordinary typed column** (a `Decimal` is a `number` in a query read). A formula whose value cannot be computed
  leaves the cell `null`, not `0`; `client.table(name).explain(key, column)` returns a `FormulaExplanation` — the row's `kind` and `formula`,
  each reference's resolved key and current value, the `value` computed now or the `reason` it has none, the `storedValue` and the cells
  that read this one (`readBy`) — showing only what the caller may read. A division is typed `Decimal` with scale 6: `fx.round(x, 2)` it to
  put it in a `Decimal(18,2)` column, or the write is refused (`FormulaValidationError`, `invalid`).
- **A read waits for your own writes** (the client's stored token) for the server's default 250 ms. If the formulas are further behind, the
  read answers `409 TOKEN_UNSATISFIED` (`AoudaConflictError`), which is not retried automatically: read again. There is no per-read wait
  option. A replica refuses a token read of a formula table (`FormulaTokenRequiresPrimaryError`, 421): read from the primary.
- **Security is the table's:** a formula may reference only rows its writer may read (`FormulaReferenceNotReadableError`, 403), and a
  formula table's grants and row conditions are an ordinary table's.

**Typed errors.** Each is a subclass of the class the client already throws for its status, so existing handlers keep catching it:

| Code (status) | Error |
|---|---|
| `FORMULA_COLUMN_INVALID`, `FORMULA_INVALID`, `FORMULA_REFERENCE_INVALID`, `FORMULA_REFERENCE_NOT_PRIMARY_KEY`, `FORMULA_CYCLE`, `FORMULA_DEPTH_EXCEEDED`, `FORMULA_LIMIT_EXCEEDED` (400) | `FormulaValidationError` (an `AoudaValidationError`); `kind` is `columnInvalid`, `invalid`, `referenceInvalid`, `referenceNotPrimaryKey`, `cycle`, `depthExceeded` or `limitExceeded`. Nothing was written. |
| `FORMULA_VALUE_WRITE_REFUSED`, `FORMULA_TABLE_REFERENCED` (409) | `FormulaConflictError` (an `AoudaConflictError`); `kind` is `valueWriteRefused` or `tableReferenced` |
| `FORMULA_REFERENCE_NOT_READABLE` (403) | `FormulaReferenceNotReadableError`; `kind` is `referenceNotReadable` |
| `FORMULA_TOKEN_REQUIRES_PRIMARY` (421) | `FormulaTokenRequiresPrimaryError` |
| `FORMULA_NOT_MAINTAINED` (503) | `FormulaNotMaintainedError`: a node whose formula maintainer is not running; **never retried** and never counted toward the circuit breaker |

`isFormulaError(e)` tests for all five, and `FORMULA_CODES` maps each server code to its status. Errors carry `code` and `statusCode`.

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

(**BL-1887, next train**) `result.typedColumns[i].exact(r)` of a `Timestamp` column read from frames is a `bigint`: the stored
.NET ticks, to the tick (a tick is 100 ns), where the cell itself is the millisecond. For an instant after 1970 the millisecond it
falls in is `new Date(Number((ticks - 621355968000000000n) / 10000n))` (divide the `bigint`: a tick count since 1970 of any date after 1998 is past 2^53, and
`Number(…)` of it before dividing can land a millisecond late). The ticks themselves are what to keep when a key must name the row
exactly (a `Timestamp` primary key with sub-millisecond ticks, which the millisecond cell cannot). A result read as JSON has no
`typedColumns`, so no exact `Timestamp`.

---

## 15) Phase Coverage Matrix

| Phase | Delivered | Key Capability |
|-------|----------|----------------|
| P5 | Core client, query builder, CRUD, schema, type generation CLI | Foundation |
| P6 | Multi-database support | `new AoudaClient({ database: 'db2' })` |
| P10 | WebSocket transport, streaming API | Real-time subscriptions |
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
