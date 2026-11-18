---
title: "How to build apps effortlessly with Aouda"
nav_order: 0
parent: "Guides"
---

# How to build apps effortlessly with Aouda

Document status: Complete (BL-183)  
Last updated: 2026-08-20

Most databases give you a place to put rows. To turn that into an application you then build a tier: a read gateway that translates HTTP into queries, a streaming relay that fans changes out to browsers, an auth proxy, an ingest worker that tidies incoming data, a rollup job, and an endpoint whose entire job is to return a total count. None of those hops add trust or make a decision. They exist because the database could not be spoken to safely from where the user is.

Aouda closes that gap. Reads and writes are **server-authored named artifacts** identified by a unique name, so a browser can execute one without being able to compose a query. A separate **data-plane listener** is a different trust boundary at the socket level, not a middleware check. **Identity and row-level authorization live in the database**, so the same predicate protects HTTP, WebSocket, and batch. The **change stream** is complete enough for a browser to hold directly — paged snapshots, an explicit gap signal, resumable, survives a token refresh. The consequence is that the tiers above stop being things you deploy and become things you **declare**, in one file, under code review.

This is the page to read before you write any code. It is the canonical build path, it names the alternative for every recommendation — because no two teams have the same constraints — and it is explicit about what Aouda will not do for you.

**Three audiences, three entry points.** Starting something new: read [the build sequence](#the-build-sequence) in order. You already have an application: skim the sequence, then go to [Adopting an existing application](#adopting-an-existing-application). You are an AI agent writing this application: read [Rules for AI agents](#rules-for-ai-agents) first, then the sequence.

---

## Start here

| I want to… | Go to |
|---|---|
| See it work before I commit to anything | [The 10-minute app](#the-10-minute-app) |
| Understand why this is different from a normal database | [The tiers you do not build](#the-tiers-you-do-not-build) |
| Build a new application, properly, in order | [The build sequence](#the-build-sequence) |
| Know what to use for a specific feature I have to ship | [Capability map](#capability-map) |
| Work out the shape when the ideal path does not fit me | [Choose your shape](#choose-your-shape) |
| Migrate an application that already exists | [Adopting an existing application](#adopting-an-existing-application) · [full guide](adoption.md) |
| Point an AI agent at one URL and get correct code | [Rules for AI agents](#rules-for-ai-agents) |
| Avoid the mistakes everyone makes first | [Anti-patterns](#anti-patterns) |
| Ship this to production | [Production checklist](#production-checklist) |
| See the honest limits before I design around a guess | [What Aouda will not do for you](#what-aouda-will-not-do-for-you) |

---

## The tiers you do not build

Each row below is a service you would normally write, deploy, monitor, and version. The test for whether a hop deserves to exist is [the hop test](division-of-responsibility.md#the-test-when-it-is-not-obvious): **does it add trust, or does it only move bytes?** A hop that adds trust has earned its place. A hop that relays is waste — and waste you have to keep running.

| The hop you would normally deploy | What it actually does | What you declare instead | Read |
|---|---|---|---|
| **Read gateway / BFF** — `GET /orders/:id/overview` forwards to a service that builds a query and maps the result back | Nothing. It does not change the data and it does not change the trust: the JWT is Aouda-issued and Aouda validates it | A **named query** in `aouda.schema.json`, identified by the SHA-256 of its canonical form and pinned into your bundle at build time. Adding a field becomes a schema PR that CI can diff for access widening | [Named queries](named-queries.md) |
| **Streaming relay** — a hub that holds one subscription and re-broadcasts rows over its own WebSocket | Fan-out, and it hides how many subscriptions you really have | **Subscribe by name** directly from the browser: paged snapshots ending in `snapshot_complete`, a server-emitted `gap` with `resume_from`, `re_auth` on token refresh, and fan-out that costs O(authorization classes) rather than O(subscribers) | [Subscribe by name](named-queries.md#subscribe-by-name) · [Real-time](real-time.md) |
| **Ingest / normalization worker** — drops malformed rows, trims a string, rounds a price, derives a column, fans rows to two tables | Checks, derived values, and routing — all of which are pure functions of the row | `checks`, `derived`, and `route` / `tee` **on the table**, evaluated at insert time. Keep the worker for anything needing a lookup, a loop, or an outbound call | [Insert-time transforms](insert-transforms.md) |
| **Rollup / aggregation job** — a cron that recomputes hourly candles or "latest value per key" | Recomputes something the database already watched change | A **materialized query** declared in the same file, maintained incrementally, readable by a browser through a named query | [Materialized queries](materialized.md) |
| **Count endpoint** — the one route that exists because the grid needs "1–25 of 412" | One extra round trip and one more thing to keep consistent with the list query | `count: true` on the named query → `totalMatches` on the same response, cost-checked when you apply the schema | [Paging, distinct, and count](named-queries.md#paging-distinct-and-count) |

The thing to notice is that none of these are conveniences. Each one removes a **deployable artifact** — with its own release, its own on-call, and its own opportunity to disagree with the database about what a row means.

---

## The 10-minute app

A complete, production-*shaped* application: a schema under review, a table a browser may read, a validated write, and typed client code. Not a toy — the same five steps scale to a real product.

### 1. Get a server and a database

```bash
dotnet tool install --global Aouda.Cli

aouda start --port 5433 --data-dir ./data
# in another terminal
aouda databases create --name tasks
```

### 2. Describe everything in one file

`aouda.schema.json` is the only thing that creates catalog objects. Tables, constraints, derived columns, the queries a browser may run, and the writes it may perform all live here.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "tasks",
  "tables": {
    "Task": {
      "columns": {
        "id":        { "type": "Int64", "primaryKey": 1, "autoIncrement": true },
        "ownerId":   { "type": "String" },
        "title":     { "type": "String" },
        "titleNorm": { "type": "String", "derived": { "type": "call", "fn": "trim", "args": [{ "type": "colRef", "col": "title" }] } },
        "done":      { "type": "Bool" },
        "createdAt": { "type": "Timestamp" }
      },
      "clusterColumns": ["createdAt"],
      "checks": {
        "title_not_empty": { "and": [{ "column": "title", "op": "ne", "value": "" }] }
      }
    }
  },
  "namedQueries": {
    "tasks.page": {
      "table": "Task",
      "select": ["id", "title", "done", "createdAt"],
      "limit": 25,
      "limitParam": "pageSize",
      "offsetParam": "pageOffset",
      "count": true,
      "orderBy": [{ "column": "createdAt", "descending": true }],
      "where": { "and": [{ "column": "done", "op": "eq", "param": "done" }] },
      "params": {
        "done":       { "required": true },
        "pageSize":   { "min": 1, "max": 25 },
        "pageOffset": { "min": 0, "max": 5000 }
      },
      "version": "v1"
    }
  },
  "namedMutations": {
    "tasks.setDone": {
      "op": "update",
      "table": "Task",
      "limit": 1,
      "where": { "and": [{ "column": "id", "op": "eq", "param": "id" }] },
      "set": { "done": { "param": "done" } },
      "returning": ["id", "done"],
      "params": { "id": { "required": true }, "done": { "required": true } },
      "version": "v1"
    }
  }
}
```

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

### 3. Apply it

```bash
aouda schema diff  --file aouda.schema.json   # review before you change anything
aouda schema apply --file aouda.schema.json
```

### 4. Generate optional Args/Row types

```bash
npx @aouda/client generate --server http://localhost:5433 --database tasks --output ./src/generated/aouda.ts
# or, offline from the file, for .NET:
aouda generate csharp --file aouda.schema.json --output ./Generated/NamedQueries.cs
```

### 5. Call it from the browser

```typescript
import { createAoudaClient } from "@aouda/client";
import { tasksPage, tasksSetDone } from "./generated/aouda";

const client = createAoudaClient({
  serverUrl: "https://data.example.com",   // the data-plane listener
  database: "tasks",
// client.whoami() — apiKey is an aouda_ key, or session, never both.
});
await client.connect();

await client.auth.signIn("ada@example.com", "correct-horse");

const page = await client.namedQueries.execute("tasks.page", {
  done: false,
  pageSize: 25,
  pageOffset: 0,
});
render(page.rows, `1–${page.rows.length} of ${page.totalMatches}`);

await client.namedMutations.execute("tasks.setDone", { id: 42, done: true });
```

**Backend services written: zero.** There is no read route, no write route, no auth route, and no count route — and the authorization rule is enforced in one place rather than in every caller. When this application grows a workflow, a third-party integration, or anything that needs to call out, *that* is when you write a service, and [the hop test](division-of-responsibility.md#the-test-when-it-is-not-obvious) will tell you.

---

## The architecture you are building toward

```
                     ┌───────────────────────────────────────────┐
  Browser / mobile ──┤  Thin edge (TLS, WAF, CDN)                │
                     │  — moves bytes, does not parse the body   │
                     └───────┬───────────────────────┬───────────┘
                             │                       │
             app.example.com │                       │ data.example.com
                             ▼                       ▼
                  ┌──────────────────┐    ┌──────────────────────────┐
                  │ Your services    │    │ Aouda DATA-PLANE :5434   │
                  │ (only where a    │    │ auth · named query ·     │
                  │  hop adds trust  │    │ named mutation · ws      │
                  │  or calls out)   │    │ everything else → 404    │
                  └────────┬─────────┘    └────────────┬─────────────┘
a principal, its statements, and an aouda_ key or a session (GET /api/auth/whoami)
                           ▼                           ▼
                  ┌────────────────────────────────────────────────┐
                  │            Aouda ADMIN :5433                   │
                  │  never published — schema apply, ad-hoc query, │
                  │  bulk load, admin/*, Studio, Hub               │
                  └────────────────────────────────────────────────┘
```

Four rules hold this together, and every one of them is enforced rather than documented:

1. **The trust boundary is the listener, not a route or a header.** The profile is tagged on the connection. There is no request you can send to switch profiles, and no header you can forge to get the other one.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
3. **The edge stays thin.** TLS, WAF, CDN, geo-allow — yes. Deserializing the JSON and re-serializing it — no. Direct internet exposure with **no** edge is not a supported configuration in this release.
4. **Browsers read through named artifacts only.** They cannot compose a query, cannot name a table, and cannot see that `admin/*` exists.

### Where each credential lives

| Credential | Held by | Listener | Ships in a browser bundle? |
|---|---|---|---|
| End-user JWT | The signed-in browser | Data-plane | Held in memory, refreshed automatically |
| Operator JWT | Studio / Hub users | Admin | n/a |

Full treatment, including how to configure dual-listen and how to prove the isolation: [Direct client access](direct-client-access.md).

---

## The build sequence

Twelve steps in four phases. Each step states **what you do**, **why it belongs in the database** (or why it does not), the **code**, and the **alternative if this does not fit you** — because a recommendation without its alternatives is not advice, it is a sales pitch.

Steps 1–4 are load-bearing: everything after them assumes the schema file exists and the trust boundary is set. Steps 5–12 can be adopted in almost any order.

### Phase 1 — Declare

#### 1. Model the data in one file

**What you do.** Write `aouda.schema.json`. It is the desired state of the database: tables, columns and types, primary keys, uniqueness, foreign keys, partitioning, storage temperature, derived columns, check constraints, insert-time routing, materialized queries, named queries, and named mutations.

**Why here.** Named queries, named mutations, checks, and transforms **can only** be declared in this file — there is no runtime registration endpoint, deliberately. A capability that can only be created by a reviewed commit is a capability an auditor can read.

```json
{
  "$schema": "https://aouda.io/schema/v1.json",
  "database": "appdb",
  "tables": {
    "Order": {
      "columns": {
        "id":         { "type": "Int64",  "primaryKey": 1, "autoIncrement": true },
        "tenantId":   { "type": "String" },
        "customerId": { "type": "Int64",  "references": "Customer.id" },
        "reference":  { "type": "String", "unique": true },
        "status":     { "type": "String" },
        "total":      { "type": "Decimal", "precision": 18, "scale": 2 },
        "createdAt":  { "type": "Timestamp" }
      },
      "partitionKey":   [{ "column": "tenantId" }],
      "clusterColumns": ["createdAt"],
      "policy":         { "storageTemperature": "Auto" },
      "durability":     { "level": "strict" }
    }
  }
}
```

The `partitionKey` line above is illustrative, not a default to copy: it is right when the orders table
will hold many full segments and reads name the tenant, including a tenant that holds only a few thousand
rows of a much larger table. It is wrong when the whole table is only a handful of segments. A single
tenant that itself holds ~1 M rows is the later `Dedicated` case. The row for it below says how to tell
which you have.

What each choice buys you, in the order you should think about it:

| Decide | Field | Why it matters later |
|---|---|---|
| Types | `type` | Full list and semantics in [Schema lifecycle](schema.md). `Timestamp` is Int64 UTC ticks and `Date` is epoch days — see [Timestamp type](../reference/timestamp.md) before you store a date as a string |
| Primary key | `primaryKey: n`, `autoIncrement` | Composite keys are ordered by `n`. Server-generated ids, or bring your own with identity-insert |
| Uniqueness | `unique: true` | Enforced on write, not just indexed |
| Relationships | `references: "Table.col"` | Enforced on write. This is what lets a detail page be one named query with joins instead of three round trips |
| Tenancy / sharding | `partitionKey` | The single highest-leverage decision on this page — including the decision **not** to set it, which is right for more tables than not. Partition when the table's total rows will fill many segments (~1 000 000 rows each). A key of a few hundred rows is then a normal shared-bucket key; a key needs about a million rows of its own only for a directory per key. Below a handful of segments a partition key buys no useful pruning and costs `PARTITION_FILTER_REQUIRED` on every read and every subscribe for the life of the table. Read [Should this table have a partition key?](partitioning.md#should-this-table-have-a-partition-key-p45) **before** you pick |
| Physical ordering | `clusterColumns` | Time-ordered data scans dramatically better clustered — and on an unpartitioned table this is what gives you segment pruning, with no query-shape guard attached. [Time-series and clustering](time-series.md) |
| Memory residency | `policy.storageTemperature` | `Hot` / `Auto` / `ColdPreferred` / mutable tiers. You control what stays in RAM. [Hot/cold storage](hot-cold.md) |
| Durability | `durability.level` | What a write survives: `strict` (WAL forced to disk), `unlogged` (no WAL; (**Lead S26c, 0.6.0**) emptied by an open that does not follow a clean close if it was being changed) or `memory` (no files at all); omitted, the table inherits its database's level (default `strict`). Replaces `walEnabled` (**Lead S26, 0.6.0**). [Write path durability](write-durability.md#durability-levels-lead-s26-060) |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Indexes are deliberately absent: zone maps, bloom filters, and sparse primary-key indexes are maintained for you and there is no index DDL to get wrong. See [Primary key indexing and memory](pk-indexing.md) for what that costs in RAM and how to bound it.

**Alternatives.** Prototyping, or you do not yet know the shape? **Schema-on-write** creates tables and columns on first insert — see [Schema lifecycle](schema.md) for inference modes, and `schema export` when you are ready to freeze what you discovered into a file. Writing a single-process .NET app or a test suite? **Embedded mode** runs the engine in-process with no server and no network at all.

#### 2. Put the schema in git and gate it in CI

**What you do.** Commit `aouda.schema.json`. Run `schema diff` on every pull request, `schema apply` on merge, and — the important one — `schema diff --access` to fail the build when a change widens what a browser-tier identity can read.

**Why here.** `select` is the whole column-exposure mechanism, so *adding a field to a named query is a security change*. The access diff makes that reviewable instead of invisible: it compares the effective read surface for a set of declared test identities and reports widening.

```bash
aouda schema validate --file aouda.schema.json
# an aouda_ key or a session. GET /api/auth/whoami names the principal.
aouda schema apply    --file aouda.schema.json
```

Add the gate **now**, on day one. Adding it after ten named queries exist means approving ten findings at once, which means approving them without reading them. Ready-made workflows for both toolchains: [Schema CI/CD](schema-cicd.md). What the gate compares and how to write the identities fixture: [Access-surface diff](../auth/authorization.md#audit).

**Alternatives.** `schema diff --access` ships in the **C# `aouda` CLI only** — `npx @aouda/client schema diff` has no `--access` flag ([BL-176](browser-tier-read-limits.md#schema-diff---access-is-c-cli-only-bl-176)). If your pipeline already touches .NET this costs one line: `dotnet tool install --global Aouda.Cli`. If it is pure Node, either add that one step, or call `POST …/schema/diff?access=true` on the admin listener from your existing job. Adding .NET to CI is the price of the gate, and it is worth paying.

### Phase 2 — Secure

#### 3. Set the trust boundary before you write any client code

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

**Why here.** Because the boundary is the socket, not a check you can forget. Prove the isolation rather than assuming it — on the data-plane listener, `POST …/query` and `GET /api/databases` must return **404**, and must work on admin. If they do not, stop and fix that before anything else.

```bash
# Verify, do not assume
Q='{"database":"appdb","table":"Order","limit":1}'
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://data.example.com/api/databases/appdb/query \
  -H "Content-Type: application/json" -d "$Q"   # expect 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://admin.internal/api/databases/appdb/query \
  -H "Content-Type: application/json" -d "$Q"   # expect 200 (401 without a credential when auth is on)
```

Configuration, the full data-plane allowlist, and the quota surface: [Direct client access](direct-client-access.md). What that listener refuses and why: [What a browser-tier read cannot do](browser-tier-read-limits.md).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

#### 4. Put identity and authorization inside the database

**What you do. ** Enable application auth, then choose an authorization mode per table.

**Why here.** A row filter enforced in the database applies to HTTP, WebSocket, batch, and subscribe with one definition. A row filter enforced in a service applies to the paths that service owns, and is silently absent everywhere else.

Aouda has **two independent auth systems**, and conflating them is the most common early mistake:

| System | Answers | Used by |
|---|---|---|
| **Server auth** | Which services and developers may connect to this server | Your backend, CI, operators, Studio. Like PostgreSQL roles |
| **Application auth** | Who your end users are | Your app's sign-up, sign-in, JWT, refresh, MFA. Like Auth0 or Supabase Auth |

Either can be used alone, together, or not at all — [Auth and Authorization](../auth/index.md) has the full model. Then pick the data-authorization mode:

| Mode | Use when | Cost |
|---|---|---|
| `jwt-claim` | The user belongs to exactly one tenant/partition, carried as a JWT claim | Cheapest; nothing to maintain |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

MFA (TOTP) is available, and password-reset and OTP delivery are configurable through [Email, SMS & notifications](../auth/notifications.md). Note that neither client SDK wraps password reset or MFA enrolment — the endpoints exist, and you call them over HTTP.

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

### Phase 3 — Build the surface

#### 5. Author every read as a named query

**What you do.** For each screen, write a definition: the table, an explicit `select`, a capped `limit`, a `where` whose values are parameters, and constraints on those parameters.

**Why here.** The client sends a **name plus arguments**. It cannot name a table, a column, an operator, or a sort direction — so the set of queries your application can issue is a finite, reviewable list that CI can diff, and whose cost is checked when you apply the schema (`1 + joinCount`, capped at 3 joins).

```json
"orders.page": {
  "table": "Order",
  "select": ["id", "reference", "status", "total", "createdAt"],
  "limit": 25,
  "limitParam": "pageSize",
  "offsetParam": "pageOffset",
  "count": true,
  "orderBy": [{ "column": "createdAt", "descending": true }],
  "where": {
    "and": [
      { "column": "tenantId", "op": "eq",  "param": "tenantId" },
      { "column": "status",   "op": "in",  "param": "statuses" }
    ]
  },
  "params": {
    "tenantId":   { "required": true },
    "statuses":   { "required": true, "maxItems": 8 },
    "pageSize":   { "min": 1, "max": 25 },
    "pageOffset": { "min": 0, "max": 5000 }
  },
  "version": "v1"
}
```

The fields that make a real UI possible, each of which is often the reason a team keeps a BFF:

- **`count: true`** → `totalMatches` on the same response, so a footer renders "1–25 of 412" in one round trip. Count ignores limit/offset. Apply **rejects** a count whose cost is not bounded (`NAMED_QUERY_COUNT_UNBOUNDED`) rather than quietly allowing a full scan.
- **`limit` / `limitParam`, `offset` / `offsetParam`** — the cap is mandatory; `limitParam` lets the caller choose a *smaller* page; omitted `offsetParam` binds skip **0** (the cap is max skip, not the default). A non-zero offset disqualifies subscribe but HTTP paging still works.
- **`distinct: true`** — and when every distinct column is a raw partition key and the predicate touches only partition keys, one constrained key is enough to pass the partition-filter rule. That is your "which values exist for this key?" filter dropdown. It is a scan pruned to that key, answered from row-group statistics where they hold the values (**architecture review, 0.3.0** — it used to be answered from the partition directories, which listed partitions whose rows had been deleted).
- **`joins`** — up to three, so a detail page is one request instead of a waterfall.
- **The batch envelope** — up to **32** named queries in one request, from **one read snapshot**, costing **one** rate-limit permit. A dashboard's ten independent panels cannot disagree with each other, and burn one permit instead of ten.

```typescript
const [summary, recent, alerts] = await client.namedQueries.batch([
  { name: "orders.summary", args: { tenantId } },
  { name: "orders.page",    args: { tenantId, statuses: ["open"], pageSize: 10 } },
  { name: "alerts.open",    args: { tenantId } },
]);
```

Use **joins** when one panel's filter comes from another panel's data; use **batch** when the panels are genuinely independent. Full authoring reference, execute/batch/subscribe, and the error table: [Named queries and mutations](named-queries.md).

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

#### 6. Author every write as a named mutation, and push validation into the table

**What you do.** Declare `namedMutations` for the writes a client may perform, and move row-shaped validation and normalization onto the table itself.

**Why here.** A `check` cannot be bypassed by a new caller, a forgotten code path, or a bulk import. A `derived` column is computed once, at write time, stored, indexed, and — importantly — **sortable**, which read-time expressions are not.

```json
"transforms": [
  { "name": "to_quotes",     "kind": "route", "when": { "and": [{ "column": "kind", "op": "eq", "value": "quote" }] }, "to": "Quote" },
  { "name": "to_quarantine", "kind": "route", "when": { "and": [{ "column": "kind", "op": "ne", "value": "quote" }] }, "to": "Quarantine" }
]
```

Two failure semantics to design around **before** you apply this, because both surprise people:

- A failed `check` **fails the whole batch**. It does not skip the row, and the error names the check rather than the row. Decide where rejected rows go and who is alerted first. (The failing row *index* is not on the error today.)
- `route` must be **exhaustive**. An unmatched row is `TRANSFORM_ROUTE_UNMATCHED`, not a row quietly left behind — so declare a catch-all route to a quarantine table, as above.

The expression substrate is deliberately closed: `literal`, `colRef`, `arithmetic`, `coalesce`, `conditional`, `param`, and a `call` allowlist covering case, trim, concat, substring, rounding (`roundTo` is the one for tick sizes), and numeric casts. It covers normalization so the ingest hop can be deleted. It does not cover lookups, I/O, or cross-row state — and a lookup table encoded as a `conditional` tree is the signal that you should keep the service. Full reference: [Insert-time transforms](insert-transforms.md). (**ADR 0072, 0.14.0**) The one exception to "no cross-row state" is a [formula](formulas.md), the value of an `Expression` column: it may read another row, of its own table or another, by primary key with `cellRef`, and only there. A live model — a P&L, a budget — is a table with a formula column: see [Build a live financial model](financial-model.md).

**Alternatives.** Multi-row expression updates, `TRUNCATE`, `DELETE` with a limit, and `RETURNING` are available to trusted callers — [Bulk mutations](bulk-mutations.md). Anything that resolves an identifier against another system, quarantines and notifies, or needs a loop stays in a service; that is [the correct answer](division-of-responsibility.md#what-stays-in-application-services), not a workaround.

#### 7. Go live: subscribe instead of poll

**What you do.** Replace polling with a subscription by name, straight from the client.

**Why here.** The change stream is complete enough to trust directly: snapshots are paged and terminated by `snapshot_complete`, a dropped event produces an explicit server-emitted `gap` carrying `resume_from`, a token refresh raises `re_auth` instead of tearing the socket down, and a client that cannot keep up is closed with `SLOW_CONSUMER` rather than being silently starved.

```typescript
const sub = client.namedQueries.subscribe(
  "orders.live",
  { tenantId, statuses: ["open", "picking"] },
  {
    conflate: { key: ["id"], interval_ms: 100 },
    onSnapshot: (rows, version) => grid.reset(rows, version),
    onChange:   (event) => grid.apply(event),
    onError:    (error) => log(error),
  },
);
// later
await sub.unsubscribe();
```

Do not hand-roll the frames. Both SDKs return the same subscription object as table subscribe, so paging, `gap` → `resume_from`, reconnect, `re_auth`, and slow-consumer recovery are transport paths you already have.

**Two design rules that are not optional at scale.** Without a relay, each client holds a subscription **per distinct thing it watches** (identical subscriptions on one SDK client are shared and count once) — and the limits are hard:

| Limit | Default | Error |
|---|---|---|
| Subscriptions per WebSocket connection | **32** | `SUBSCRIPTION_LIMIT_EXCEEDED` |
| Subscriptions per identity | **128** | `SUBSCRIPTION_LIMIT_EXCEEDED` |
| Connections per identity (**BL-1383, 0.11.0**) | **16** | `IDENTITY_CONNECTION_LIMIT_EXCEEDED` |
| Subscribe attempts per identity (**BL-1383, 0.11.0**) | burst **512**, **32**/s | `SUBSCRIBE_RATE_EXCEEDED` |
| Send-buffer high-water mark | 1 MiB | close with `SLOW_CONSUMER` |
| Other requests per identity | 60 permits / 60 s | `429 IDENTITY_QUOTA_EXCEEDED` + `Retry-After` |

So: **make subscriptions collection-shaped, not item-shaped.** A named query taking a list parameter (`{ "column": "id", "op": "in", "param": "ids" }`, capped with `maxItems`) lets one subscription cover a whole grid. A query taking a single id, subscribed once per row with a different id each time, is one distinct subscription per row and hits 32 at 32 rows; SDK sharing does not merge those, because the arguments differ. And measure real permit usage against `Aouda:IdentityQuota:PermitLimit` before cutover — do not raise the limit first and measure afterwards. A subscribe attempt costs no permit (**BL-1383, 0.11.0**); it is bounded by the subscribe-rate bucket instead.

> **Be honest about `conflate`.** It holds only a **value update** to a row that is visible before *and* after. On an **insert-only** stream — a tick feed, an event log, an audit table — it reduces the event rate by **zero**, and `values_skipped` never fires. Conflation never collapses an insert, a delete, or a row leaving your visibility scope, because a client that misses one of those has a permanently wrong grid. For last-value-per-key, model it as a `latestPerKey` materialized query (step 8) and subscribe to that. Be precise about what that buys you: the MQ result table holds one row per key, so the grid stays bounded no matter how many ticks arrive — but MQ upserts do not carry `prev` today, so a subscribe over the MQ does not throttle the **event rate** either. It is the correct catalog shape, not a rate limiter. If you need a hard cap on messages per second right now, that belongs in a service that owns the fan-out. Details and the current caveats: [conflate is a no-op on insert-only streams](browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

**Alternatives, in descending order of preference.** WebSockets blocked by a proxy? The client falls back to **HTTP long-poll** automatically (`streaming.enableLongPollFallback`, on by default). Need to disable streaming entirely? Poll a named query on an interval — you keep name identity, the access gate, and `totalMatches`; you lose latency and you spend more permits. Genuinely need fan-out to more clients than the caps allow, or a wire protocol Aouda does not speak? Keep a relay, and let it hold **one** subscription per authorization class. That is a real answer for a real constraint. Streaming internals, wire modes, and reconnect playbooks: [Real-time streaming](real-time.md).

#### 8. Pre-aggregate what a dashboard needs

**What you do.** Declare materialized queries in the same file, and read them through named queries like any other table.

**Why here.** A rollup job you deploy recomputes on a schedule and is wrong between runs. A materialized query is maintained incrementally as the source changes, is a real catalog table under its own name, and can be subscribed to.

```json
"materializedQueries": {
  "latest_quote": {
    "type": "latestPerKey",
    "sourceTable": "Quote",
    "groupBy": ["ticker"],
    "orderBy": "ts",
    "descending": true,
    "select": ["ticker", "price", "ts"]
  },
  "candles_1h": {
    "type": "aggregate",
    "sourceTable": "Quote",
    "groupBy": ["ticker", { "column": "ts", "function": "TruncateToHour", "outputName": "hour" }],
    "aggregates": [
      { "function": "max",   "sourceColumn": "price", "outputName": "high" },
      { "function": "min",   "sourceColumn": "price", "outputName": "low" },
      { "function": "first", "sourceColumn": "price", "outputName": "open" },
      { "function": "last",  "sourceColumn": "price", "outputName": "close" }
    ]
  }
}
```

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

> **The map is desired state.** `"materializedQueries": { … }` **drops anything live that is not listed**, and `{}` drops all of them. Omitting the key entirely leaves them unmanaged. On an existing database, always `schema export` first rather than hand-adding a partial map.

Lifecycle, refresh, incremental maintenance, and auto-routing (an ad-hoc query can be answered from a matching MQ without naming it): [Materialized queries](materialized.md).

**Leader boards.** Declare `topNPerGroup` (`orderBy` + `n`, optional `groupBy`) so the result table is size N, not universe size. `firstPerKey` is MIN of `orderBy`, not arrival order. Top-N holds every observed source row in maintainer memory — use a compact per-key source. Query the result table by name (no planner auto-route). The source must have a primary key. Grouped aggregates on the data plane remain absent: an MQ is the sanctioned mechanism.

### Phase 4 — Feed, ship, and run it

#### 9. Get data in at volume

**What you do.** Pick the write path that matches the shape of your traffic.

| Shape | Use | Notes |
|---|---|---|
| A user clicked save | Named mutation, or `insert` / `update` from a trusted service | |
| A steady stream of events | **Write stream** over WebSocket, `mode: "insert"` or `"upsert"` | Acked, back-pressured. This is also the **only** upsert path — there is no `upsert()` on the table builder |
| A migration, a nightly file, a backfill | **Bulk load** | Single- or multi-table and atomic across tables; idempotency keys; identity-insert to preserve source ids; `applyTransforms` / `preTransformed` to control whether step 6's checks and routes run |

```typescript
const stream = await client.table("Event").openWriteStream({ mode: "upsert" });
await stream.write(batch);
await stream.close();
```

Bulk load into a table carrying checks or transforms requires an **explicit intent flag** — deliberately, so a 50-million-row import cannot silently skip the validation your interactive path enforces. Throughput characteristics, resumability, and replication interaction: [Bulk load](bulk-load.md).

#### 10. Make types flow end to end

**What you do.** Optionally generate Args/Row types from the schema. The identity is a string literal from `aouda.schema.json`.

```bash
npx @aouda/client generate --server $AOUDA_URL --database appdb --output ./src/generated/aouda.ts
aouda generate typescript --file aouda.schema.json --output ./src/generated/aouda.ts   # offline, from the file
aouda generate csharp     --file aouda.schema.json --output ./Generated/Queries.cs
```

You get optional argument and row types per definition. Editing a definition under the same name changes behaviour at apply time — coexistence is two names (`quoteByTicker` + `quoteByTickerV2`). Deprecate with `deprecatedAt` / `sunsetAt`; execute still returns 200 plus a `NAMED_QUERY_DEPRECATED` warning. There is no runtime registration endpoint. A frontend that never runs codegen is fully functional. [Types (optional codegen)](named-queries.md#types-optional-codegen) · [TypeScript client](../clients/typescript.md) · [SDK compatibility](../clients/compatibility.md).

#### 11. Operate it

You are running a database now, so the operational surface matters. Every one of these has a guide; this is the map.

| Concern | Mechanism | Read |
|---|---|---|
| What stays in RAM | Per-table temperature, hot retention, demotion/promotion | [Hot/cold storage](hot-cold.md) |
| Not being killed by the OOM killer | Process RSS ceiling, admission back-pressure (503 + `Retry-After`), runtime `budget set` | [Sizing memory and WAL](sizing.md) |
| Surviving a crash | Segmented WAL, checkpoints, write concern, budgeted recovery | [Write path durability](write-durability.md) |
| Getting data back | Incremental backups, exact restore, retention, S3-compatible targets, point-in-time recovery over HTTP and both SDKs (Studio UI is exact-restore-only) | [Backup and restore](backup.md) |
| Surviving a node | WAL-stream replication, witness, failover, read preference | [Replication and clustering](replication.md) |
| Many apps, one server | Multi-database, isolation, async drop, quarantine | [Server and multi-database](server-multi-database.md) |
| Knowing what it is doing | Prometheus metrics, health/ready probes, structured logs, query stats | [Server configuration](server-configuration.md) |
| Looking at your data | Studio — data explorer, schema, cluster ops, backups, MQ browser | [Studio](studio.md) |
| Running it somewhere | Docker, Compose, Kubernetes + Helm, Windows Service, systemd | [Deployment](../deployment/index.md) · [Kubernetes and Helm](../deployment/kubernetes.md) |
| Managed control plane | Hub | [Cloud and Hub](cloud-hub.md) |

Two settings worth deciding deliberately rather than discovering: `storageTemperature` per table (step 1) and the memory budget. Everything else has a defensible default.

#### 12. Test it — including the authorization

**What you do.** Three layers, all of which run in `dotnet test` or `npm test` with no external infrastructure.

- **Engine-level and integration:** `Aouda.Testing` starts a **full in-process server** with auth helpers and ephemeral databases. Embedded mode gives you a real database per test with no server at all. [Testing](../getting-started/testing.md) · [Testing and DX](testing-dx.md)
- **Schema:** `schema validate` in CI against every environment overlay, and `schema diff` as a review artifact.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

---

## Capability map

The showcase, and the table to check your feature list against. If something you need is not here, it is probably in [What Aouda will not do for you](#what-aouda-will-not-do-for-you) — an omission from this table is not a yes.

| I need to build… | Use | Read |
|---|---|---|
| A paged table with "1–25 of 412" | Named query with `limit`/`limitParam`, `offsetParam`, `count: true` | [Paging, distinct, and count](named-queries.md#paging-distinct-and-count) |
| A filter panel with several optional facets | One definition with `whenParamPresent: true` on each optional condition — omitting the arg skips the predicate entirely | [Optional predicates](browser-tier-read-limits.md#optional-predicates-whenparampresent) |
| A filter dropdown of "values that exist" | Named query with `distinct: true` — one constrained key is enough when the columns are partition keys | [Paging, distinct, and count](named-queries.md#paging-distinct-and-count) |
| Search-as-you-type over a name | A stored `derived` normalized column plus a prefix/`in` predicate. There is **no full-text search** | [Derived columns](insert-transforms.md#derived-columns) |
| A sortable grid | Declare `orderByChoices` in the definition; caller picks with `orderByIndex`. Cursor paging is **not shipped** (BL-182) — use `offsetParam` | [Bounded sort choices](named-queries.md#bounded-sort-choices-orderbychoices--orderbyindex) |
| A live-updating grid or ticker | `namedQueries.subscribe` by name, collection-shaped, list parameter capped with `maxItems` | [Subscribe by name](named-queries.md#subscribe-by-name) |
| A "latest value per key" board | `latestPerKey` materialized query, subscribed. **Not** the raw table plus `conflate` | [Materialized queries](materialized.md) |
| A dashboard of N independent panels | The batch envelope — up to 32, one snapshot, one permit | [Batch](named-queries.md#batch-one-snapshot) |
| Ranking by a computed value ("top gainers by %") | A `computed` output on an `aggregate` MQ — physically stored and orderable. Or a `derived` column on a base table. Expression `orderBy` on runtime columns is **not shipped** (BL-183) | [No expression orderBy](browser-tier-read-limits.md#no-expression-orderby) |
| A record create/edit/delete form | Named mutations with `set`, `returning`, and capped `limit`; `checks` on the table | [Named mutations](named-queries.md#named-mutations) |
| Server-side validation nobody can bypass | `checks`, `unique`, `references` — all enforced on write | [Insert-time transforms](insert-transforms.md) |
| A bulk import or a migration | Bulk load, multi-table atomic, idempotency keys, identity-insert | [Bulk load](bulk-load.md) |
| A high-rate event or telemetry ingest | Write stream (`insert`/`upsert`), plus `route`/`tee` to fan rows out | [Real-time](real-time.md) · [Insert-time transforms](insert-transforms.md) |
| An append-only audit or event log | Table clustered on time, `ColdPreferred` temperature, durability `strict` | [Time-series](time-series.md) · [Hot/cold](hot-cold.md) |
| Sign-up, sign-in, refresh, password change | Application auth, called directly from the browser | [Setup and flows](../auth/setup.md) |
| MFA | TOTP enrolment and verification (HTTP; not wrapped by the SDKs) | [Auth reference](../auth/reference.md) |
| Password-reset emails, OTP by SMS | Notification providers (SendGrid, GatewayAPI, console for local) | [Email, SMS & notifications](../auth/notifications.md) |
| Semantic search / recommendations | `Vector` / `MdVector` columns and nearest-neighbour search — **engine and .NET only**, not in `@aouda/client` | [Graph and vector](graph-vector.md) |
| Relationship traversal (who follows whom) | Edge tables, traverse / k-hop / shortest-path — **engine and .NET only** | [Graph and vector](graph-vector.md) |
| Market data, quotes, OHLC candles | The end-to-end worked use case | [Market data and stock quotes](market-data.md) |
| Reporting and ad-hoc analysis | Ad-hoc queries with joins and grouped aggregates from a **trusted** caller on the admin listener | [Query execution](query.md) |
| A data export | Ad-hoc query or bulk read from a service; paged named query for a user-facing export | [Query execution](query.md) |
| Soft deletes and history | A `deleted`/`validFrom` column plus a `filter` MQ for the live view | [Materialized queries](materialized.md) |
| Reading your own writes off a replica | Read preference (`Primary` is the default) | [Replication](replication.md) |
| **File and image storage** | **Not Aouda.** Use object storage and keep the key in a column | — |
| **Background jobs and queues** | **Not Aouda.** Use your job runner; Aouda holds the state it operates on | [Division of responsibility](division-of-responsibility.md) |
| **Calling a third-party API** | **Not Aouda.** A service does this. It is the clearest case where a hop adds trust | [Division of responsibility](division-of-responsibility.md) |
| **Workflow orchestration** | **Not Aouda.** Anything needing a loop, a retry policy, or a saga is a service | [Division of responsibility](division-of-responsibility.md) |

---

## Choose your shape

The path above is the one that removes the most work. It is not the only supported one, and being unable to use it is common. Find your constraint.

| Your constraint | Recommended shape | What you give up | Read |
|---|---|---|---|
| No WebSockets survive your network path | Keep subscriptions; the client falls back to **HTTP long-poll** automatically | Some latency; more connections | [Real-time](real-time.md) |
| Streaming is off the table entirely | Poll a named query on an interval | Latency, and permits — measure against the 60/60 s quota | [Direct client access](direct-client-access.md#quotas-and-cost) |
| Pure Node/JS CI, cannot add .NET | Call `POST …/schema/diff?access=true` on admin from your existing job | Convenience only — the gate still runs | [BL-176](browser-tier-read-limits.md#schema-diff---access-is-c-cli-only-bl-176) |
| Your team needs SQL | A trusted service using the fluent query builder; ad-hoc queries on admin | There is **no SQL surface** | [Query execution](query.md) |
| Regulated: the database may not be internet-reachable | Gateway pattern — but still author reads as named queries and run the access gate | The extra hop. You keep every reviewability property | [Division of responsibility](division-of-responsibility.md) |
| Single-process .NET app, or a test suite | **Embedded mode** — engine in-process, no server, no network | Multi-client access, replication, Studio | [Getting started](../getting-started/index.md) |
| You already have an application | Start from the existing-app branch below | Nothing — it is the same destination | [Adoption](adoption.md) |

---

## Adopting an existing application

If the application already exists, the destination is identical — you just arrive by deleting rather than by not building. The verdicts:

| Existing hop | Verdict | Why |
|---|---|---|
| **Read gateway / BFF** | **Delete** | It does not change the data, and it does not change the trust. Replace with named queries. Keep it for cross-service aggregation, third-party calls, and workflow |
| **Streaming relay** | **Delete** on a current build | Paged snapshots, `gap` + `resume_from`, `re_auth`, `SLOW_CONSUMER`, and authorization-class fan-out all shipped. Check [capacity](adoption.md#capacity-what-changes-when-the-relay-is-gone) first — you lose the relay's fan-out |
| **Ingest / normalization worker** | **Shrink**, sometimes delete | Checks + derived + route move in. Anything resolving an identifier against another system, quarantining and notifying, or needing a loop stays |
| **Auth proxy** | **Delete the user-facing half** | Sign-in, refresh, `me`, sign-out are data-plane endpoints designed to be called from a browser. Keep service-key flows server-side, and **do not** delete JWT validation in the services that remain |

Migration order — each step independently shippable and independently revertible:

1. Upgrade, and check the deliberate breaks on the trusted surface against your current usage.
2. **Move the schema into a file** (`schema export` → git → `diff` on every PR → `apply` on merge). Everything after this depends on it.
3. Turn on the data-plane listener behind your existing edge, on its own hostname, and **prove** the isolation.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
5. Add the CI access gate **now**, while there is one named query to approve rather than ten.
6. Author named queries and switch reads over behind a flag; run both and compare.
7. Move ingest normalization that passes the decision test, having first decided where rejected rows go.
8. Move streaming, subject to the capacity arithmetic, building the direct path while the relay still runs.
9. Move browser auth to direct data-plane calls; keep service-key flows server-side.
10. **Delete — in separate commits from the construction.** Never delete a relay and build its replacement in the same change.

**Read [Adopting Aouda in an existing application](adoption.md) for the full treatment**: the SDK coverage matrix (which capabilities have a typed method versus wire-only — planning as if everything does is the most common way an adoption plan goes wrong), the capacity arithmetic for losing the relay's fan-out, the complete adoption checklist, and a troubleshooting table for the migration itself.

---

## Rules for AI agents

If you are an AI agent writing an application against Aouda, this section is your contract. If you are a human, this is the section to point your agent at.

### Reading order

1. **This page** — the build path and the boundaries.
2. [What a browser-tier read cannot do](browser-tier-read-limits.md) — the refusal list. Its tables are generated from the validators that enforce them, so it cannot drift. **Read this before designing any screen.**
3. [Named queries and mutations](named-queries.md) — the authoring reference you will use most.
4. [Division of responsibility](division-of-responsibility.md) — the test for whether code belongs in a service.
5. [Direct client access](direct-client-access.md) — listeners, keys, quotas.
6. [Data authorization](../auth/authorization.md) — pick a mode per table.
7. [HTTP API](../reference/http-api.md) — the wire truth when a field name is in doubt.
8. [Quick start for AI agents](../ai/quick-start.md) — if you need a database running in one command first.
9. [Local CLI testing (agents)](../ai/local-cli-testing.md) — throwaway server + traps (`start -h`, data-plane allowlist, CorsOrigins, schema shape) before you burn a session on a wrong port or `POST /query`.

### Hard rules

| Do | Never |
|---|---|
| Put every table, query, mutation, and MQ in `aouda.schema.json` | Look for a runtime registration endpoint — there is none, by design |
| Give every named query an explicit `select` | Use `*`, or select a column the screen does not render |
| Give every named query a capped `limit` | Rely on a default page size |
| Pass schema names as string literals | Guess a name that is not in `aouda.schema.json` |
| Make subscriptions collection-shaped with a capped list parameter | Subscribe once per row |
| Use the batch envelope for independent panels, joins for dependent ones | Fire N independent executes on page load |
| Push row validation into `checks` and normalization into `derived` | Validate only in the client, or in one of several callers |
| State that `conflate` is a no-op on insert-only streams | Recommend `conflate` for a tick feed or event log |
| Read an aggregate MQ by its `outputName` (`high`, `open`) | Read internal state columns (`_max_bid`, `_first_open_val`) |
| Say "not shipped" and link the alternative | Invent cursor paging, expression `orderBy`, a SQL surface, a hosted OAuth login page, or full-text search. (`whenParamPresent`, `orderByChoices`, `collapse_inserts`, `computed` MQ outputs, `topNPerGroup`, `firstPerKey`, and a named query's declared `aggregates` / `groupBy` / `perKey` (**BL-796, 0.3.0**) **are** shipped — do not list them as absent) |

### Per-screen decision procedure

For each screen or feature, in order:

1. **Is the data already in a table?** If not, step 1 of the build sequence.
2. **Can the read be expressed as one definition** — one table plus ≤ 3 joins, an explicit `select`, a capped `limit`, values as parameters? If yes, write a named query. If it needs a groupBy, declare `aggregates` / `groupBy` in the definition (**BL-796, 0.3.0**); if the rollup must stay current as rows arrive, or be subscribed to, write a materialized query and read *that*. If it needs a lookup, a loop, or an outbound call, it is a service.
3. **Does the screen need a total?** Add `count: true`. If apply rejects it with `NAMED_QUERY_COUNT_UNBOUNDED`, the definition's cost is not bounded — cover the partition keys or drop the count. Do not add a count endpoint.
4. **Does it need to update live?** Subscribe by name, collection-shaped. If the table is insert-only, do not reach for `conflate` — it holds value updates only. Model a `latestPerKey` MQ and subscribe to that: it bounds the grid to one row per key, which is the shape you want, though it does not throttle the event rate today.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
6. **Does it write?** Named mutation, with the row rules as `checks` on the table.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

### The error contract

Errors are structured and designed to be acted on programmatically:

```json
{
  "error": "TABLE_NOT_FOUND",
  "message": "Table 'Order' was not found.",
  "requestId": "req_01J..."
}
```

Branch on `error`; show `suggestion` to whoever can act on it; log `requestId`. Codes you should recognise without looking them up:

| Code | It means | Do |
|---|---|---|
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` | You called table subscribe on the data plane | Use `namedQueries.subscribe(name, args)` |
| `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED` | The definition has joins, `selectExpr`, `distinct`, or an offset | Split the view, or poll it — HTTP execute still works |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | Item-shaped subscriptions | Make the definition take a capped list parameter |
| `IDENTITY_CONNECTION_LIMIT_EXCEEDED` (**BL-1383, 0.11.0**) | The identity already holds the maximum number of connections | Close unused sockets; do not retry in a loop |
| `SUBSCRIBE_RATE_EXCEEDED` (**BL-1383, 0.11.0**) | Subscribing faster than the per-identity bucket refills | Wait `retry_after_ms`; pace a reconnect replay |
| `429 IDENTITY_QUOTA_EXCEEDED` | Too many requests for one identity | Batch; honour `Retry-After`; then size the quota from measurement |
| `PARTITION_FILTER_REQUIRED` | The predicate does not pin every partition key | Add `eq`/`in` on each one — [the exact rule](browser-tier-read-limits.md#partition-filter-rule) |
| `NAMED_QUERY_UNCAPPED_LIMIT` | Missing `limit` at apply | Add a numeric cap |
| `NAMED_QUERY_IDENTIFIER_PARAM` | You parameterized a table, column, operator, or direction | Not permitted, ever. Parameters are values only |
| `TRANSFORM_ROUTE_UNMATCHED` | A row matched no `route` | Declare a catch-all route to a quarantine table |
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

### Self-verification checklist

Before reporting the work complete:

- [ ] Every table, query, mutation, and MQ is declared in `aouda.schema.json`; no imperative catalog call anywhere.
- [ ] `aouda schema validate` is clean.
- [ ] Every named query has an explicit `select`, a capped `limit`, and ≤ 3 joins.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
- [ ] Names are string literals from the schema; codegen is optional Args/Row types.
- [ ] Subscriptions are collection-shaped; the count per connection is well under 32.
- [ ] Independent panels use the batch envelope.
- [ ] `conflate` is not used on an insert-only stream, or its no-op is stated where used.
- [ ] `aouda schema diff --access` runs and passes.
- [ ] No API, field, or capability was used that is not in the docs — anything absent was reported as absent, with the alternative.

---

## Anti-patterns

| Anti-pattern | Why it hurts | Do this instead |
|---|---|---|
| A read gateway that forwards a query and maps the result back | A deployable artifact that adds no trust, plus a second place the column list can drift | A named query |
| Hand-rolling WebSocket frames | You will reimplement snapshot paging, `gap`/`resume_from`, `re_auth`, and reconnect — badly | `namedQueries.subscribe` |
| One subscription per row, each with its own id | 32 per connection is reached at 32 rows; SDK sharing does not merge distinct arguments | A capped list parameter, one subscription per view |
| Ten independent executes on page load | Ten permits, and ten snapshots that can disagree | The batch envelope: one permit, one snapshot |
| `conflate` on a tick feed | Zero reduction, and a false sense that throttling is handled | A `latestPerKey` MQ, subscribed — it bounds rows per key, not yet the event rate |
| Raising `PermitLimit` because of a 429 | You have hidden the design problem and will find it again at scale | Measure, batch, then size the quota from the measurement |
| A five-way join in one definition | The cost cap is not a tuning knob; a view needing it is telling you to split | Split the view, or pre-aggregate with an MQ |
| A lookup table encoded as a `conditional` tree in `derived` | Unmaintainable, and it will outgrow the expression substrate | Keep the service — this is the case where a hop earns its place |
| Adding the access gate after the queries exist | Ten findings approved at once means ten findings unread | Add the gate on day one |
| Deleting a hop in the same commit that replaces it | You find out in production that something was load-bearing | Two commits, and exercise the rollback |
| Hand-editing `materializedQueries` into an existing file | The map is desired state; unlisted MQs are dropped | `schema export` first |
| Storing a date as a String | Loses comparison, ordering, and bucketing | `Timestamp` or `Date` — [Timestamp type](../reference/timestamp.md) |

---

## Production checklist

- [ ] `aouda.schema.json` is in git; `schema validate` is clean against **every** environment overlay.
- [ ] `schema diff` runs on every PR; `schema apply` runs on merge; neither is done by hand.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
- [ ] The admin listener is unreachable from outside the private network — **probed, not assumed**.
- [ ] `POST …/query` and `GET /api/databases` return 404 on the data-plane listener.
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).
- [ ] Every named query has an explicit `select`, a capped `limit`, and ≤ 3 joins.
- [ ] Subscriptions are collection-shaped; the measured count per connection is well under 32.
- [ ] Measured permits/minute per identity is recorded, and `PermitLimit` is set **from** that measurement.
- [ ] Independent panels use the batch envelope; dependent ones use joins.
- [ ] Rejected-row handling is defined for every table carrying a `check`, and every `route` set has a catch-all.
- [ ] `storageTemperature` and the memory budget are set deliberately, and sizing was checked against expected data volume.
- [ ] Backups are configured **and a restore has been performed** into a scratch database.
- [ ] Metrics and health probes are scraped; alerts exist for memory-budget pressure and replication lag.
- [ ] Tests cover at least one cross-tenant isolation case that must fail.
- [ ] Client, server, and Studio versions are a supported combination — [SDK compatibility](../clients/compatibility.md).

---

## Troubleshooting your first week

| Symptom | Cause | Action |
|---|---|---|
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` | `client.table(t).subscribe(...)` sends a target | `client.namedQueries.subscribe(name, args)` |
| `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED` | The definition has joins, `selectExpr`, `distinct`, or an offset | Only the live path is restricted; HTTP execute still works. Split the view or poll it |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | Item-shaped subscriptions (distinct arguments per row) × N clients | A capped list parameter, one subscription per view |
| `429 IDENTITY_QUOTA_EXCEEDED` on page load | N independent executes | Batch, honour `Retry-After`, then size `PermitLimit` from measurement |
| Socket closed with `SLOW_CONSUMER` | 1 MiB send buffer exceeded — the client cannot keep up | Conflate value updates, narrow the projection, or reduce the subscription's scope |
| `PARTITION_FILTER_REQUIRED` | The predicate does not pin every partition key. `in` **does** satisfy it; ranges and prefixes do not | Add `eq`/`in` on each partition key — [the exact rule](browser-tier-read-limits.md#partition-filter-rule) |
| `NAMED_QUERY_COUNT_UNBOUNDED` at apply | `count: true` on a join, a `distinct`, or uncovered partition keys | Cover every partition key with a required `eq`/`in`, or drop the count |
| `NAMED_QUERY_UNCAPPED_LIMIT` at apply | No numeric `limit` | Add the cap; `limitParam` does not replace it |
| `NAMED_QUERY_IDENTIFIER_PARAM` at apply | A table, column, operator, or direction was parameterized | Not permitted. Write one definition per shape |
| `SCHEMA_EXPR_UNKNOWN_FUNCTION` at apply | Unknown `call` fn, wrong arity, or a non-literal cast type | Names are lowercase and the list is closed — [call functions](insert-transforms.md#call--string-and-rounding-functions) |
| Every MQ disappeared after an apply | `materializedQueries` present but incomplete — the map is desired state | `schema export` first; omit the map entirely to leave MQs unmanaged |
| Rows silently vanished after adding `route` | Change events follow storage, not the request | Query the target table, or use `tee` if you meant to keep both |
| A whole batch was rejected for one bad row | A failed `check` fails the batch, by design | Pre-validate, or route suspect rows to quarantine. The row index is not on the error today |
| `conflate` changed nothing | Insert-only stream — it holds value updates only | A `latestPerKey` MQ, subscribed. Expect fewer rows, not yet a lower event rate |
| Aggregate MQ columns are `_max_bid`, not `high` | Reading internal state columns | Read by `outputName`; re-apply if the result schema is stale |
| Studio shows a connect error | Studio is pointed at the data-plane listener | Studio and Hub use the **admin** URL |
| Ingest throughput fell after adding transforms | Write amplification on small batches | Batch size is the tuning parameter; avoid stacking tees on a hot path |
| `MEMORY_BUDGET_EXCEEDED` / 503 with `Retry-After` | The RSS ceiling is doing its job | [Sizing memory and WAL](sizing.md); raise the budget deliberately or demote a table. If the message says **refused by the server-level budget** (**BL-737, 0.2.0**), the database's own budget had room — raising it will not help; the message lists what holds the server's budget by category. Honour `Retry-After` either way |
| `DECLARATIVE_SCHEMA_DDL_FORBIDDEN` | An imperative DDL call against an apply-managed table, refused in every `InferenceMode` (**BL-1177, 0.7.1**). Often the C# client's default reconcile trying to drop a column the model omits | Change the schema file and re-apply. Set `AutoReconcileSchema = false` on C# clients that write to these tables |
| `PARTITION_KEY_FIXED` (**BL-1199, 0.9.0**) | A drop or rename of a partition-key column, or a schema document that changes a table's `partitionKey` / `partitionFunction` — the key is fixed when the table is created. Nothing was applied. On a C# client, often the default reconcile dropping a key column its model omits | Keep the key column in the model and the document. To change a key, drop and re-create the table |

---

## What Aouda will not do for you

Two lists. The first is *not yet*; the second is *not ever*, on purpose.

### Not in this release

| Not shipped | Do this instead |
|---|---|
| Cursor / keyset paging (BL-182) | `offset` / `offsetParam` for page-by-offset today |
| Expression `orderBy` on runtime columns (BL-183) | A `computed` output on an `aggregate` MQ, or a stored `derived` column — both are physically stored and orderable |
| `topNPerGroup` / `firstPerKey` materialized queries | Shipped — declare them in `materializedQueries` or HTTP create. `firstPerKey` is MIN(`orderBy`), not arrival order. Top-N working set is in-memory; query the result by name |
| Ad-hoc aggregates built by the caller on the data plane | Declare `aggregates` / `groupBy` in the named query (**BL-796, 0.3.0**), or an aggregate MQ read through a named query when it must be live or subscribed |
| Subscribe by name for definitions using joins, `selectExpr`, or `distinct` | HTTP execute plus polling, or split the view |
| The failing row index on a rejected batch | The error names the check; pre-validate or quarantine |
| Password reset / MFA methods on the client SDKs | The HTTP endpoints exist — call them directly |
| `schema diff --access` in the npm CLI | The C# `aouda` CLI, or `POST …/schema/diff?access=true` on admin |
| A SQL query surface | The fluent query builder, or named queries |
| Full-text search | A stored `derived` normalized column plus prefix/`in` predicates |
| Graph traversal and vector search from `@aouda/client` | The .NET client or the engine API |
| Server-side MCP data tools | `@aouda/client` does ship cluster MCP tool types |
| Bare internet exposure with no edge | A thin edge — TLS, WAF, CDN |

Anything above that you need should be raised rather than worked around silently; several are actively in progress. The refusal list that is generated from the enforcing validators — and therefore cannot go stale — is [What a browser-tier read cannot do](browser-tier-read-limits.md).

### Deliberately not a database concern

Files and images (use object storage, keep the key in a column). Background jobs and queues. Outbound calls to third parties. Workflow and saga orchestration. Anything needing a loop, a retry policy, or a lookup against another system. These are the cases where a hop **does** add trust, which is exactly why they stay in a service — see [Division of responsibility](division-of-responsibility.md). A database that tried to absorb them would be a worse database and a worse application server.

---

## Related

**The mechanisms**
- [Named queries and mutations](named-queries.md) — authoring, execute, batch, subscribe by name, optional types
- [Direct client access](direct-client-access.md) — listeners, key types, quotas, thin-edge topology
- [What a browser-tier read cannot do](browser-tier-read-limits.md) — the generated refusal list
- [Insert-time transforms](insert-transforms.md) — `derived`, `checks`, `route` / `tee`, failure semantics
- [Materialized queries](materialized.md) — `latestPerKey`, `aggregate`, `filter`, incremental maintenance
- [Division of responsibility](division-of-responsibility.md) — the hop test

**Schema and governance**
- [Schema management](schema-management.md) · [Schema lifecycle](schema.md) · [Schema CI/CD](schema-cicd.md) · [Access-surface diff](../auth/authorization.md#audit)
- [Partitioning and multi-tenancy](partitioning.md) · [Time-series and clustering](time-series.md) · [Timestamp type](../reference/timestamp.md)

**Auth**
- [Auth and Authorization](../auth/index.md) · [Architecture patterns](../auth/architecture.md) · [Setup and flows](../auth/setup.md) · [Data authorization](../auth/authorization.md) · [Client integration](../auth/client-integration.md) · [Email, SMS & notifications](../auth/notifications.md) · [Reference](../auth/reference.md)

**Reads, writes, and streaming**
- [Query execution](query.md) · [Bulk mutations](bulk-mutations.md) · [Bulk load](bulk-load.md) · [Real-time streaming](real-time.md) · [Graph and vector](graph-vector.md)

**Operations**
- [Hot/cold storage](hot-cold.md) · [Sizing memory and WAL](sizing.md) · [Write path durability](write-durability.md) · [Storage and persistence](storage.md) · [Primary key indexing and memory](pk-indexing.md)
- [Backup and restore](backup.md) · [Replication and clustering](replication.md) · [Server and multi-database](server-multi-database.md) · [Server configuration](server-configuration.md)
- [Studio](studio.md) · [Cloud and Hub](cloud-hub.md) · [Deployment](../deployment/index.md) · [Kubernetes and Helm](../deployment/kubernetes.md)

**Clients, testing, and reference**
- [TypeScript client](../clients/typescript.md) · [SDK compatibility](../clients/compatibility.md) · [Distribution and licensing](../clients/distribution.md)
- [Testing](../getting-started/testing.md) · [Testing and DX](testing-dx.md) · [Getting started](../getting-started/index.md)
- [HTTP API](../reference/http-api.md) · [Changelog](../CHANGELOG.md)

**Worked end-to-end use case**
Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, next train**).

**Existing applications**
- [Adopting Aouda in an existing application](adoption.md) — SDK coverage matrix, capacity arithmetic, full migration order and checklist
