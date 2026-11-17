---
title: "Adopting Aouda in an existing application"
nav_order: 8
parent: "Guides"
---

# Adopting Aouda in an existing application

Document status: Complete (P37, BL-183)  
Last updated: 2026-08-20

This is the page to read when you already have an application — a frontend, a gateway, some domain services — and you want to know **what the architecture should look like now** and **what you should delete**.

It is the **existing-application branch** of [How to build apps effortlessly with Aouda](build-apps.md), which is the canonical build path. The destination is identical; you arrive at it by deleting rather than by not building. If you have not read that page, start there — then come back here for the parts that only apply when there is already something in production.

[Division of responsibility](division-of-responsibility.md) gives you the principle. [Direct client access](direct-client-access.md) and [Named queries](named-queries.md) give you the mechanisms. This page gives you the **target architecture, the order of operations, and the capacity consequences** — including the places where the engine is ahead of the SDKs and you have to plan around it.

---

## Start here

| I want to… | Go to |
|---|---|
| See the target topology | [Reference architecture](#reference-architecture) |
| Decide what happens to each existing hop | [The four hops](#the-four-hops) |
| Know what the client SDKs actually wrap | [SDK coverage](#sdk-coverage-read-this-before-you-plan) |
| Size a direct-access deployment | [Capacity](#capacity-what-changes-when-the-relay-is-gone) |
| Sequence the migration | [Migration order](#migration-order) |
| Hand a plan to an agent | [Adoption checklist](#adoption-checklist) |

---

## Reference architecture

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
                  │ (orchestration,  │    │ auth · named query ·     │
                  │  workflow,       │    │ named mutation · ws      │
                  │  vendor I/O)     │    │ everything else → 404    │
                  └────────┬─────────┘    └────────────┬─────────────┘
See [Access](../auth/index.md) (**BL-1464, next train**).
                           ▼                           ▼
                  ┌────────────────────────────────────────────────┐
                  │            Aouda ADMIN :5433                    │
                  │  never published — schema apply, ad-hoc query,  │
                  │  bulk load, admin/*, Studio, Hub                │
                  └────────────────────────────────────────────────┘
```

Four rules hold this together:

1. **The trust boundary is the listener, not a route or a header.** The profile is tagged on the Kestrel connection. There is no request you can send to switch profiles.
See [Access](../auth/index.md) (**BL-1464, next train**).
3. **The edge stays thin.** TLS, WAF, CDN, geo-allow — yes. Deserializing the JSON and re-serializing it — no. A hop that only relays bytes is waste; a hop that adds trust has earned its place. Direct internet exposure with **no** edge is not a supported configuration in this release.
4. **Browsers read through named artifacts only.** They cannot compose a query, cannot name a table, and cannot see that `admin/*` exists.

### Where each credential lives

| Credential | Held by | Listener | Ships in a browser bundle? |
|---|---|---|---|
See [Access](../auth/index.md) (**BL-1464, next train**).
| End-user JWT | The signed-in browser | Data-plane | Held in memory, refreshed |
| Operator JWT | Studio / Hub users | Admin | n/a |

---

## The four hops

Most existing applications have some combination of four hops between the browser and the database. Here is what happens to each.

### 1. The read gateway (BFF) — **delete**

A controller that takes `GET /instrument/{id}/overview`, forwards it to a service, which builds a query, runs it, and maps the result back. It does not change the data. It does not change the trust — the JWT is Aouda-issued and Aouda validates it itself.

Replace it with a **named query**: a server-authored template in `aouda.schema.json`, identified by the SHA-256 of its canonical form, pinned into the frontend at build time by codegen. Adding a field becomes a schema PR that CI can diff for access widening — not a redeploy of two services.

Keep the gateway for: cross-service aggregation, anything that calls a third party, anything with a workflow.

### 2. The streaming relay — **delete, on a P37 build**

A service that holds one subscription open against Aouda and re-broadcasts rows over its own WebSocket/SignalR hub. Before P37 this was correct engineering, because the change stream could drop events silently, snapshots stopped early, and a token refresh tore the subscription down.

All of that shipped: paged snapshots terminated by `snapshot_complete`, a server-emitted per-subscription `gap` with `resume_from`, opt-in `conflate` with `values_skipped` (**value updates only** — a no-op on insert-only streams), `re_auth`, `SLOW_CONSUMER`, and fan-out that costs O(authorization classes) rather than O(subscribers).

**Verify you are on a build that includes it** (server `0.1.8` or later — [compatibility matrix](../clients/compatibility.md)), then read [SDK coverage](#sdk-coverage-read-this-before-you-plan) and [Capacity](#capacity-what-changes-when-the-relay-is-gone) before you delete anything.

### 3. The ingest / normalization service — **shrink, sometimes delete**

A worker that drops malformed rows, filters row kinds, normalizes a timestamp, derives a column, and fans rows out to two tables is [`checks` + `derived` + `route`](insert-transforms.md).

It is **not** deletable if it resolves an identifier against another system, quarantines and notifies, or needs a loop. The expression substrate is `literal`, `colRef`, `arithmetic`, `coalesce`, `conditional`, and a closed `call` allowlist covering case, trim, concat, substring, rounding, and numeric casts — so normalization and tick-size rounding **can** move in, but vendor-code mapping and anything that needs a lookup cannot. Do not encode a lookup table as a `conditional` tree; that is the signal to keep the service.

### 4. The auth proxy — **delete the user-facing half**

See [Access](../auth/index.md) (**BL-1464, next train**).

See [Access](../auth/index.md) (**BL-1464, next train**).

**Do not delete your JWT validation** in services that still exist. They validate the same Aouda-issued token via OIDC discovery / JWKS, which is published on both listeners.

---

## SDK coverage: read this before you plan

The wire protocol and the client SDKs are not at the same level of coverage. Planning as if every documented capability has a typed method is the single most common way an adoption plan goes wrong.

| Capability | HTTP / wire | `@aouda/client` | `Aouda.Client` (C#) |
|---|---|---|---|
| Named-query execute by name | ✅ | ✅ `client.namedQueries.execute(name, args)` | ✅ `client.NamedQueries.ExecuteAsync(name, args)` |
| Named-query batch (cap 32) | ✅ | ✅ `client.namedQueries.batch([{ name, args }])` | ✅ `client.NamedQueries.BatchAsync([…])` |
| Named-mutation execute by name | ✅ | ✅ `client.namedMutations.execute(name, args)` | ✅ `client.NamedMutations.ExecuteAsync(name, args)` |
| Optional Args/Row types | ✅ `GET …/schema/typescript` | ✅ `npx @aouda/client generate` | ✅ `aouda generate csharp` |
| Table subscribe (admin listener) | ✅ | ✅ `client.table(t).subscribe({…})` | ✅ `SubscribeAsync(…)` |
| Snapshot paging + `snapshot_complete` | ✅ | ✅ handled in the transport | ✅ |
| `gap` → automatic `resume_from` | ✅ | ✅ handled in the transport | ✅ |
| `re_auth` on token refresh | ✅ | ✅ handled in the transport | ✅ |
| **Subscribe by name (required on the data-plane)** | ✅ | ✅ `client.namedQueries.subscribe(name, args, { conflate })` | ✅ `client.NamedQueries.SubscribeAsync(name, args, options)` |
| Declaring MQs in `aouda.schema.json` | ✅ `materializedQueries` map | ✅ via `schema apply` | ✅ via `schema apply` |
| String / rounding functions in write-time expressions | ✅ `call` allowlist | ✅ `$upper` … `$cast` in `.update()` | ✅ `SetExpr` builder |
| `aouda schema diff --access` | ✅ | ❌ not shipped | ✅ (the `aouda` C# CLI) |
| Materialized-query create / list **at runtime** | ✅ admin HTTP | ❌ | ❌ (`RefreshAsync` only) |

Two caveats that still shape a plan:

- **`schema diff --access` is C#-CLI only.** The CI gate that stops accidental access widening needs the `aouda` tool (`dotnet tool install --global Aouda.Cli`). If your pipeline already runs .NET anywhere, this costs one line. If it is a pure Node pipeline, adding .NET to CI is the price of the gate — and it is worth paying.
- **Runtime MQ management is still .NET-only.** Declaring MQs in the schema file covers provisioning, which is what most applications need. Creating one dynamically at runtime is not something the TypeScript client can do.

### Subscribing on the data-plane

`subscribe` on the data-plane **requires** a `name`; sending `target` + `filter` returns `NAMED_QUERY_SUBSCRIBE_REQUIRED`. Both SDKs expose this directly, returning the same subscription object as table subscribe — so snapshot paging, `gap` → `resume_from`, reconnect, `re_auth`, and `SLOW_CONSUMER` recovery are the transport paths you already have, and every resend carries the same `name` + `args`.

```typescript
// Watchlist — table emits value updates (upsert), conflate works:
const sub = client.namedQueries.subscribe(
  "equity.quotes",
  { tickers: ["AAPL", "MSFT"] },
  {
    conflate: { key: ["ticker"], interval_ms: 100 },
    onSnapshot: (rows, version) => grid.reset(rows, version),
    onChange: (event) => grid.apply(event),
  }
);

// Insert-only tick table — add collapse_inserts to throttle, or use a latestPerKey MQ:
const lastPrice = client.namedQueries.subscribe(
  "quotes.lastPrice",
  { tickers: ["AAPL"], source: "nasdaq" },
  {
    conflate: { collapse_inserts: true },
    onSnapshot: (rows) => grid.reset(rows),
    onChange: (event) => grid.apply(event),
  }
);
```

Do not hand-roll the frames. Full API, including the deprecation-warning path and which definitions are refused live, is in [Named queries — subscribe by name](named-queries.md#subscribe-by-name). `conflate` without `collapse_inserts` throttles only **value updates** — a no-op on insert-only streams. Use `collapse_inserts: true` or a `latestPerKey` named-query subscribe for last-price.

---

## Capacity: what changes when the relay is gone

A relay hides two properties of your workload. Deleting it exposes both, and both have hard limits.

### Subscription count multiplies by the number of browsers

A relay typically holds **one** Aouda subscription per data partition and fans it out to every connected client. Direct access means each browser holds its own subscriptions, **one per distinct thing it watches**: the official SDKs share identical subscriptions on one client (one server subscription however many widgets read it), but distinct feeds each count against the caps below.

| Limit | Default | Error |
|---|---|---|
| Subscriptions per WebSocket connection | **32** | `SUBSCRIPTION_LIMIT_EXCEEDED` |
| Subscriptions per identity | **128** | `SUBSCRIPTION_LIMIT_EXCEEDED` |
See [Access](../auth/index.md) (**BL-1464, next train**).
| Connections per identity, WebSocket and long-poll (**BL-1383, 0.11.0**) | **16** | `IDENTITY_CONNECTION_LIMIT_EXCEEDED` |
| Subscribe attempts per identity (**BL-1383, 0.11.0**) | burst **512**, **32** per second | `SUBSCRIBE_RATE_EXCEEDED` |
| Send-buffer high-water mark | 1 MiB | close with `SLOW_CONSUMER` |

The server tells a connecting client its limits in `auth_ok` (`limits`) (**BL-1383, 0.11.0**). The connection and rate defaults here are provisional.

The design consequence is concrete: **make subscriptions collection-shaped, not item-shaped.** A named query that takes a list parameter (`{ "column": "ticker", "op": "in", "param": "tickers" }`, constrained with `maxItems`) lets one subscription cover a whole watchlist or grid. A named query that takes a single id, subscribed once per row with a different id each time, is a distinct subscription per row and hits 32 on a dashboard with that many rows; SDK sharing does not help there, because the arguments differ. (Per-key merging of such subscriptions is not built.)

Then use `conflate` with a key **on a table that actually emits value updates**. Latest-wins on updates, per key, per interval — and `values_skipped` tells the client it happened. Conflation never collapses an insert, a delete, or a row leaving the caller's visibility scope. On an **insert-only** tick stream it therefore reduces the event rate by zero; last-price belongs on a `latestPerKey` MQ, not on `quotes` plus `conflate`. See [browser-tier read limits](browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

### Requests are metered per identity, not per connection

The data-plane applies a sliding window per identity — default **60 permits / 60 seconds**, one permit per execute, per **batch envelope** and per mutation. Exceeding it returns `429 IDENTITY_QUOTA_EXCEEDED` with `Retry-After`. A **subscribe attempt no longer spends a permit** (**BL-1383, 0.11.0**); it is bounded by its own per-identity token bucket (above), so mounting a dashboard's subscriptions or replaying them after a reconnect does not use up the HTTP quota.

That makes the batch envelope a capacity decision, not just a latency one: a dashboard that fires ten independent named queries on load burns ten permits; the same ten in one batch burn **one** — and come from **one read snapshot**, so the panels cannot disagree with each other. Use joins when one panel's filter comes from another panel's data, and batch when they are genuinely independent.

Measure real usage against `Aouda:IdentityQuota:PermitLimit` before cutover. Do not raise the limit first and measure later.

### Persist-time cost is checked when you apply the schema

Named-query cost is `1 + joinCount`, capped at 3 joins / cost 8. A view that needs a five-way join is telling you to split it — the cap is not a tuning knob you raise to make a design work.

---

## Migration order

Do these in order. Each step is independently shippable and independently revertible.

See [Access](../auth/index.md) (**BL-1464, next train**).
2. **Move the schema into a file.** `schema export` → `aouda.schema.json` in git → `schema diff` on every PR → `schema apply` on merge ([schema management](schema-management.md), [schema CI/CD](schema-cicd.md)). Named queries, named mutations, checks, and transforms can only be declared in this file — there is no runtime registration. Materialized queries can now be declared here too, but **export before you hand-edit**: a present `materializedQueries` map is desired state and drops anything not listed. Everything after this step depends on it.
3. **Turn on the data-plane listener** behind your existing edge, on its own hostname. Prove the isolation before you use it: `POST …/query` and `GET /api/databases` must return **404** on the data-plane and work on admin.
See [Access](../auth/index.md) (**BL-1464, next train**).
6. **Author named queries and switch reads over behind a flag.** Old gateway route and new named query both work. Compare results.
7. **Move ingest normalization** that passes the [decision test](division-of-responsibility.md#the-test-when-it-is-not-obvious) into `checks` / `derived` / `route`. Expect an error-handling change: a failed check **fails the whole batch**, it does not skip the row, and the error names the check rather than the row. Decide where rejected rows go and who is alerted **before** you apply it. `route` must also be exhaustive — an unmatched row is `TRANSFORM_ROUTE_UNMATCHED`, not a row left behind on the landing table — so declare a catch-all route to a quarantine table. See [failure semantics](insert-transforms.md#failure-semantics-the-batch-fails-the-row-does-not-skip).
8. **Move streaming** with `namedQueries.subscribe`, subject to [capacity](#capacity-what-changes-when-the-relay-is-gone) — this is where losing the relay's fan-out shows up. Build the direct path behind a flag while the relay still runs.
9. **Move browser auth** to direct data-plane calls. Keep service-key flows server-side.
10. **Delete — in separate commits from the construction.** Never delete a relay and build its replacement in the same change. That is how you find out in production that `conflate` was collapsing something you needed.

---

## Adoption checklist

Hand this to whoever (or whatever) is writing the plan.

- [ ] Server is `0.1.8`+ and the four trusted-surface breaks have been checked against current usage
- [ ] `aouda.schema.json` is in git and `schema validate` is clean against every environment
- [ ] Admin listener is unreachable from outside the private network — probed, not assumed
See [Access](../auth/index.md) (**BL-1464, next train**).
- [ ] `aouda schema diff --access` runs on every PR that touches the schema
- [ ] Named queries have `select` (never `*`), a capped `limit`, and ≤3 joins
- [ ] Subscriptions are collection-shaped; measured count per connection is well under 32
- [ ] Measured permits/minute per identity is recorded and `PermitLimit` is set from it
- [ ] Independent panels use the batch envelope; dependent ones use joins
- [ ] Rejected-row handling is defined for every table that gained a `check`
- [ ] Every deletion is a separate PR from the construction that replaces it, and the rollback has been exercised

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `NAMED_QUERY_SUBSCRIBE_REQUIRED` on the data-plane | You called `client.table(t).subscribe(…)`, which sends `target` | Use `client.namedQueries.subscribe(name, args)` — [subscribing](#subscribing-on-the-data-plane) |
| `NAMED_QUERY_SUBSCRIBE_UNSUPPORTED` | The definition has `joins`, `selectExpr`, `distinct`, or an offset | Only the live path is restricted; HTTP execute still works. Split the view or poll it |
| Every MQ disappeared after a `schema apply` | `materializedQueries` present but incomplete — the map is desired state | `schema export` first; omit the map entirely to leave MQs unmanaged |
| `SCHEMA_EXPR_UNKNOWN_FUNCTION` on apply | Unknown `call` `fn`, wrong arity, or non-literal `cast` type | Names are lowercase and the list is closed — [`call` functions](insert-transforms.md#call--string-and-rounding-functions) |
| `SUBSCRIPTION_LIMIT_EXCEEDED` after deleting a relay | Item-shaped subscriptions × N browsers | Make the named query take a list parameter; one subscription per view, not one per row |
| `429 IDENTITY_QUOTA_EXCEEDED` on page load | N independent executes | Use the batch envelope; then size `PermitLimit` from measurement |
| `IDENTITY_CONNECTION_LIMIT_EXCEEDED` (**BL-1383, 0.11.0**) | One identity holds 16 sockets (tabs, devices, a reconnect loop) | Close what is not needed; do not retry in a loop; raise `MaxConnectionsPerIdentity` only from measurement |
| `SUBSCRIBE_RATE_EXCEEDED` (**BL-1383, 0.11.0**) | A resubscribe loop, or a mass reconnect replay | Wait `retry_after_ms` (frame) or `Retry-After` (long-poll `/send`); pace the replay |
See [Access](../auth/index.md) (**BL-1464, next train**).
| Studio shows a connect error after adding the listener | Studio is pointed at the data-plane | Studio and Hub use the **admin** URL |
| Ingest throughput fell after adding transforms | Write amplification on small batches | Batch size is the tuning parameter; avoid stacking `tee`s on a hot path |
| Rows silently vanished after adding `route` | Events follow storage, not the request | Query the target table, or use `tee` if you meant to keep both |
See [Access](../auth/index.md) (**BL-1464, next train**).

---

## Not in this release

- `schema diff --access` in the npm CLI — the CI gate needs the C# `aouda` tool.
- Runtime MQ create/list in either client; declaring them in `aouda.schema.json` covers provisioning.
- Live subscribe to a named query that uses `joins`, `selectExpr`, `distinct`, or an offset.
- Timestamp truncation as a derived `call`, and `cast` to `Timestamp` / `Date` / `Guid` / `Bool`.
- OAuth 2.0 authorization code + PKCE, and token introspection.
- Bare internet exposure with no edge.
- Tier 3 embedded functions (loops, branch trees, outbound calls).

---

## Related

- [How to build apps effortlessly with Aouda](build-apps.md) — the canonical build path this page branches from, plus the capability map and the agent contract
- [Division of responsibility](division-of-responsibility.md) — the decision test
- [Direct client access](direct-client-access.md) — listeners, keys, quotas, topology
- [Named queries and mutations](named-queries.md) — authoring, execute, batch, subscribe
- [Insert-time transforms](insert-transforms.md) — `derived`, `checks`, `route`/`tee`
See [Access](../auth/index.md) (**BL-1464, next train**).
- [Schema CI/CD](schema-cicd.md) · [Compatibility matrix](../clients/compatibility.md) · [HTTP API](../reference/http-api.md)
