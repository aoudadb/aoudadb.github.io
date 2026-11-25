---
title: "Direct client access"
nav_order: 9
parent: "Guides"
---

# Direct client access and listeners

Document status: Complete (P40 S09)  
Last updated: 2026-08-21

Aouda serves **two browser populations with different trust**. The distinction is a property of the **listener** a client connects to — not of a route, an origin header, or a credential negotiated per request.

| Population | Who | Listener | Surface |
|---|---|---|---|
| **Operators** | Studio, Hub, DBAs | **Admin** (default bind/port) | Everything, including ad-hoc query and `admin/*` |
| **Application end users** | Your product's browsers | **Data plane** (optional second bind) | Auth + named query + named mutation + subscribe. Everything else is **404**. |

Wire-level matrix and routes: [HTTP API — Listeners](../reference/http-api.md#listeners-and-profiles). Named artifacts: [Named queries](named-queries.md).

---

## Start here

| I want to… | Go to |
|---|---|
| See a complete end-to-end example | [Market-data guide](market-data.md) and `examples/p40-browser-tier/` |
| Turn on the data-plane listener | [Configure dual-listen](#configure-dual-listen) |
| Let a browser read data | [A browser holds no key](#credentials-on-each-listener) |
| Let a browser read a materialized-query result | [Opening an artifact to the browser](#opening-an-artifact-to-the-browser) |
| Connect Studio or Hub | [Studio and Hub](#studio-and-hub) |
| Put TLS/WAF in front | [Topology](#topology-a-thin-edge) · [Behind a reverse proxy](../deployment/reverse-proxy.md) |
| Sign users in from a browser | [Authentication that exists](#authentication-that-exists) |
| See what a browser-tier read cannot do | [Browser-tier read limits](browser-tier-read-limits.md) |

---

## Configure dual-listen

Keep today's `Aouda:Bind` / `Aouda:Port` (or `--port`) as the **admin** listener. Add a second bind:

```json
{
  "Aouda": {
    "Port": 5433,
    "Listeners": {
      "DataPlane": {
        "Bind": "0.0.0.0:5434",
        "CorsOrigins": "https://app.example.com"
      }
    }
  }
}
```

`CorsOrigins` is a **single string** (comma-separated if you need more than one). It is not a JSON array and not an indexed env key — `Aouda__Listeners__DataPlane__CorsOrigins__0=…` can crash Kestrel on 0.1.9.

Environment: `Aouda__Listeners__DataPlane__Bind=0.0.0.0:5434` and `Aouda__Listeners__DataPlane__CorsOrigins=https://app.example.com`.

If `DataPlane:Bind` is **unset**, there is one listener, the admin one, with its CORS settings, and no request acts as `anonymous`: a call with no credential is `401 AUTH_CREDENTIAL_MISSING`.

**CORS is per listener.** Admin defaults include Studio / Hub origins (`https://studio.aouda.com`, `https://hub.aouda.dev`, plus `Aouda:StudioOrigin`) unless `Aouda:CorsOrigins` replaces them. Data-plane origins come **only** from `Aouda:Listeners:DataPlane:CorsOrigins` (empty = no browser origins). The setting accepts `*` — that lets **any** website's JavaScript call public auth POSTs and, after login, any data-plane route the JWT can reach. Prefer an explicit origin list. Do not put the Studio origin on the data-plane.

The profile is tagged on the **Kestrel connection**. There is no request header you can send to switch profiles.

### What the data-plane returns 404 for

`admin/*`, `_studio/*`, `POST /api/server/shutdown`, `POST …/schema/apply`, `POST …/query`, tables/MQ/graph/jobs/branches, write-stream, `GET /api/databases`, `GET /health/detailed`. Status is **404**, not 403 — a 403 would admit that an admin surface exists.

Allowed: `/health` `/ready` `/startup`, app-auth except `/auth/admin/*`, OIDC/JWKS, named-query execute + batch, named-mutation execute, `/api/databases/{db}/ws`.

The data-plane listener **ignores `crossPartitionAccess`** (**BL-1227, 0.9.0**): the partition-filter guard decides, and the error says the flag is not accepted there. The flag only waives that guard on the admin listener and never widens what a credential sees — [`crossPartitionAccess` on the data-plane listener](browser-tier-read-limits.md#crosspartitionaccess-on-the-data-plane-listener).

Listed named-artifact routes still **do not enumerate names**. On the data-plane, a caller with no `execute` statement for the name (`anonymous` included, whatever table statements it holds) gets **404** `NAMED_QUERY_NOT_FOUND` / `NAMED_MUTATION_NOT_FOUND` — the same code as an unknown name — not 401 vs 404. Unlisted paths stay empty 404 (D-11). The admin listener keeps 401/403 so operators can tell missing credential from denied. Invalid credentials stay 401 on both listeners.

---

## Credentials on each listener

A **browser holds no key**. With no credential its data-plane request acts as the `anonymous` principal of the auth database that governs the
database; after sign-in it sends the user's session. There is one key format and no browser kind of key (**BL-1464, 0.16.0**). What a caller may
do is its statements, whichever credential it sends:

| Caller | May call | Listener |
|---|---|---|
| No credential (`anonymous`) | Sign-up, sign-in, refresh; the named queries and mutations `anonymous` has an `execute` statement for. A subscription needs a credential | Data-plane. On admin → `401 AUTH_CREDENTIAL_MISSING` |
| A session of an end user | Named query / mutation / subscribe, as its statements allow | Data-plane |
| A key of a backend's principal | What its statements allow: tables, named artifacts, admin routes with `manage` | Either; **ad-hoc query only on admin** (data-plane `/query` is 404 for everyone) |
| A session or key of a `_serverauth` principal (Studio operator) | Ad-hoc + admin | Admin |

`GET /api/auth/whoami` (both listeners) says which principal a credential is and which statements it holds. The retired second-token header is
refused `400 INVALID_REQUEST`: to act as a user, send that user's session or a [limited key](../auth/credentials.md#limited-keys) minted from it.

---

## Opening an artifact to the browser

The browser tier reaches named artifacts only, and an artifact is closed until a statement opens it: `anonymous` and `signup` hold
nothing by default. Give the caller an `execute` statement; nothing is set on the table or the materialized query.

<!-- declaration-example -->
```json
{
  "version": 1,
  "databases": {
    "auth": {
      "kind": "auth",
      "signup": {
        "enabled": true,
        "statements": [
          { "actions": ["execute"], "resources": ["trading/query/equity.positions"],
            "where": { "and": [ { "column": "accountId", "op": "eq", "principal": "id" } ] } }
        ]
      },
      "principals": {
        "anonymous": {
          "statements": [
            { "actions": ["execute"], "resources": ["trading/query/equity.quoteByTicker"] }
          ]
        }
      }
    },
    "trading": { "kind": "data", "authDatabase": "auth", "schema": "schema/trading.aouda.schema.json" }
  }
}
```

A materialized-query result is opened the same way: define a named query over the result table, and give `execute` on that query. A table or
schema document that still carries the old opt-in member is refused `SCHEMA_UNKNOWN_MEMBER`.

A named query nobody may execute from a browser is still **allowed to apply** — operators and services need it. What widens the browser tier is a
change of statements, so it is in the diff of `aouda.json`; a public statement on a table other statements restrict is refused
`AUTH_PUBLIC_UNRESTRICTED` unless it says `"unrestricted": true` ([Public reach](../auth/authorization.md#public-reach)).

---

## Quotas and cost

**Persist time (schema apply):** named-query cost is `1 + joinCount`. Defaults: max 3 joins, max cost 8. Exceed → `NAMED_QUERY_TOO_MANY_JOINS` / `NAMED_QUERY_COST_EXCEEDED` with a modelling-fix string ("split the query or drop a join"). Override: `Aouda:NamedQuery:MaxJoins` / `MaxCost`.

**Runtime (data-plane only):** per-identity sliding window, default 60 permits / 60 seconds. One permit per execute, per **batch envelope**, per mutation execute; a subscribe attempt spends none (**BL-1383, 0.11.0**) (see below). Exceed → `429 IDENTITY_QUOTA_EXCEEDED` + `Retry-After`. Disabled on admin-only deployments. Config: `Aouda:IdentityQuota:PermitLimit` / `WindowSeconds` / `Enabled`.

**Several devices, one identity.** The quota and the subscription caps (`Aouda:WebSocket:MaxSubscriptionsPerConnection`,
default 32; `MaxSubscriptionsPerIdentity`, default 128) count the identity, not the device, so a user on a browser, a desktop
agent and a phone shares them: size `PermitLimit` from the sum of every device's steady rate (a 30 s heartbeat is 2 permits a
minute per device) plus headroom for page loads and reconnects, and `MaxSubscriptionsPerIdentity` from the sum of their live
subscriptions. Two more per-identity bounds apply (**BL-1383, 0.11.0**): a **connection limit** (`MaxConnectionsPerIdentity`, default 16; WebSocket and long-poll sessions together; refused inside the handshake with `IDENTITY_CONNECTION_LIMIT_EXCEEDED`, which a client must treat as final rather than reconnect in a loop) and a **subscribe-rate bucket** (`Aouda:WebSocket:SubscribeRate`, burst 512, 32 per second; `SUBSCRIBE_RATE_EXCEEDED` with `retry_after_ms`). The identity is the principal, whatever credential it presents: every key and session of one principal shares the limits, a backend's as a user's. For `anonymous` it is the visitor's remote address — **provided the server sees the visitor's address**: behind a reverse proxy, configure `Aouda:ForwardedHeaders`, or every visitor shares one quota. Worked numbers: [Defaults reference](defaults-reference.md#data-plane-subscriptions-and-the-identity-quota)
(**NativeClients, 0.4.0**).

**Server clock.** Every response carries a `Date` header that a browser can read cross-origin; the SDKs keep the offset from it (`serverClockOffsetMs` / `ServerClockOffset`) so a client can judge a
server-stamped lease against the server's clock.

Signup 5/min and signin 20/min per IP still apply. An optional failed-signin ceiling (`Aouda:Auth:FailedSigninCeiling`, off by default) caps **failed** sign-ins per auth database — the attack shape per-IP limiting cannot see. It is per process. A tripped ceiling is a full login outage on that database until the window drains (correct passwords included); see [Auth reference](../auth/reference.md#rate-limiting).

---

## Studio and Hub

**Studio must use the admin listener URL.** Studio's connect probe hits `GET /api/databases`. On the data-plane that is 404 — Studio treats that as "this URL is a data-plane listener, use the admin URL", not as "auth is missing". `_studio/config` is admin-only.

**Hub's `AOUDA_HUB_AOUDA_URL` must be the admin listener.** JWKS works on both listeners; Hub data/admin calls 404 on the data-plane. Hub never proxies customer data (ADR 0026). Named queries are per-database catalog objects — Hub does not distribute them.

---

## Topology: a thin edge

Commit to a **thin edge** in front of the data-plane: TLS termination, WAF, CDN. The edge **must not parse or reshape** the JSON payload. A hop that only relays bytes is waste; a hop that adds trust (TLS, DDoS, geo-allow) has earned its place.

The data-plane profile is built to the standard a **bare** exposure would require, so you do not silently scope it down to "the edge handles it" and then point the internet at `admin/*`.

**Direct internet exposure without an edge is not a supported configuration in this release.** There is no published TLS-termination policy, DDoS posture, or public-exposure security review.

Typical layout:

```
Browser ──TLS──► CDN/WAF ──► Aouda data-plane :5434
Studio  ──TLS──►              Aouda admin      :5433
Hub     ──────────────────►  Aouda admin      :5433
```

**Trusted proxies.** The edge is the TCP peer. Until you set `Aouda:ForwardedHeaders`, per-IP rate limits, lockout attribution, and `_audit_log` client IPs are the proxy's address — one global bucket. Configure the feature and name the proxies; see [Behind a reverse proxy](../deployment/reverse-proxy.md).

---

## Authentication that exists

Application end users today:

1. Browser holds the **data-plane URL and database name** — no key. CORS on `Aouda:Listeners:DataPlane:CorsOrigins` is the origin control (unset = no browser origins; `*` = any origin can call public auth POSTs — prefer an explicit list).
2. `POST /api/databases/{db}/auth/signup` or `/signin` with **no credential** → an access token + refresh token. Signup is **opt-in** (`signup.enabled` on the auth database, default off), and what a signed-up principal may do is that setting's `roles` and `statements`, default nothing. Set it in `aouda.json` or with `PUT /api/auth/{authDatabase}/signup`. Password reset can send email unauthenticated at 20/min/IP; `request-password-reset` does not disclose whether the account exists.
3. Subsequent named-query calls: `Authorization: Bearer <access token>` on the **data-plane**. Before sign-in they carry nothing and run as `anonymous`.
4. `POST …/auth/refresh` when the access token expires (also keyless).
5. WebSocket: first message `auth` with the JWT; later `re_auth` with the refreshed token so subscriptions survive. Failed `re_auth` closes the session.

### What is not shipped

**A hosted OAuth 2.0 authorization server is not available** — no `/authorize` login page, social login or third-party consent
(tracked as BL-043). Token introspection (BL-042) is not available. Do not implement a SPA that redirects to an IdP and expects Aouda
to complete the code exchange. **Native apps** can sign in through the browser: the signed-in web front issues a single-use PKCE code
and the app redeems it for its own session (**NativeClients, 0.4.0**) — [Native apps](../auth/setup.md#native-apps-sign-in-through-the-browser).

OIDC discovery and JWKS **are** published for **validating JWTs Aouda issued**. That is not a federated login.

For the browser itself, the supported pattern is: Aouda app-auth signup/signin/refresh (email/password, optional MFA as documented under [Auth](../auth/setup.md)) with **no key**, or a **backend** that holds a key and never exposes it to the browser.

The **application** holds the consistency token (cookie or header **you** name). The SDK captures `X-Aouda-Token` in memory and **never** `Set-Cookie`. Recreating the client without a shared store loses read-your-writes. See [Freshness](freshness.md).

---

## Worked example: SPA on the data-plane

```typescript
import { AoudaClient } from "@aouda/client";
import { equityQuoteByTicker } from "./generated/named-queries";

const dataPlane = "https://data.example.com"; // :5434 behind TLS

const client = new AoudaClient({
  serverUrl: dataPlane,
  database: "trading",
  // no apiKey: a browser holds no key
});
await client.connect();

await client.auth.signIn("trader@example.com", password); // later calls carry the session, refreshed as it expires

const quote = await client.namedQueries.execute("equity.quoteByTicker", {
  ticker: "AAPL",
});
```

Ad-hoc from the same client against the data-plane:

```bash
curl -i -X POST https://data.example.com/api/databases/trading/query \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"database":"trading","table":"EquityQuote"}'
# 404
```

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Studio connect 404 | URL is the data-plane | Point Studio at the **admin** port |
| `AUTH_CREDENTIAL_MISSING` from a browser | The admin URL, with no credential; or a subscribe before sign-in | Use the data-plane URL for named queries; sign in before subscribing |
| `IDENTITY_QUOTA_EXCEEDED` | 60 req / 60 s default | Back off using `Retry-After`; raise `PermitLimit` for known clients |
| `IDENTITY_CONNECTION_LIMIT_EXCEEDED` (**BL-1383, 0.11.0**) | 16 connections per identity (public key: per remote address) | Close unused sockets; terminal for the handshake |
| `SUBSCRIBE_RATE_EXCEEDED` (**BL-1383, 0.11.0**) | Subscribe bucket empty | Wait `retry_after_ms` / `Retry-After` |
| Data-plane CORS fails from Studio origin | Different CORS policies | Do not add Studio to data-plane origins |
| Data-plane named-query 404 with no credential | Listed-route non-disclosure: `anonymous` has no `execute` statement for the name. The admin listener answers 401 | Give `anonymous` the statement, or sign in |
| Data-plane named-mutation 404 with a valid session | Same listed-route non-disclosure: the principal has no `execute` statement for this mutation — a table `write` does not count, and it is **not** the name | Same masked 404 (not 403). Check the principal's statements with `whoami?database=`, before suspecting the artifact name; the server log names the refusal |
| WS `NAMED_QUERY_SUBSCRIBE_REQUIRED` | Ad-hoc subscribe on data-plane | Subscribe by `name` |
| WS `DATA_PLANE_WRITE_STREAM` | `stream_open` on data-plane | Ingest with a backend's key on admin, or HTTP named mutation |

---

## Not in this release

- Bare internet exposure (no edge).
- A hosted OAuth authorization server (login page, social login, consent) / token introspection. (Native sign-in through the
  browser with a PKCE code ships in the 0.4.0 — **NativeClients**.)
- Per-identity quotas on the admin listener (operators use the existing global concurrency limiter).
- Subscriptions with no credential (`anonymous` runs named queries and mutations over HTTP).

---

## Related

- [How to build apps effortlessly with Aouda](build-apps.md) — the full build path this listener model serves
- [Named queries](named-queries.md)
- [Freshness and replica consistency](freshness.md) — token in the browser; SDK never sets cookies
- [Division of responsibility](division-of-responsibility.md)
- [Adopting Aouda](adoption.md) — migrating an existing app onto this model
- [HTTP API](../reference/http-api.md)
- [Studio](studio.md)
- [Cloud and Hub](cloud-hub.md)
- [Server configuration](server-configuration.md)
