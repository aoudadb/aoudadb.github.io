---
title: "Direct client access"
nav_order: 9
parent: "Guides"
---

# Direct client access and listeners

Document status: Complete (P37)  
Last updated: 2026-08-14

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
| Turn on the data-plane listener | [Configure dual-listen](#configure-dual-listen) |
| Give a SPA a data credential | [`mk_pub_*`](#mk_pub_-vs-mk_anon_-) |
| Opt a table into browser reads | [`dataPlaneAccess`](#table-opt-in-fail-closed) |
| Connect Studio or Hub | [Studio and Hub](#studio-and-hub) |
| Put TLS/WAF in front | [Topology](#topology-a-thin-edge) |
| Sign users in from a browser | [Authentication that exists](#authentication-that-exists) |

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
        "CorsOrigins": [ "https://app.example.com" ]
      }
    }
  }
}
```

Environment: `Aouda__Listeners__DataPlane__Bind=0.0.0.0:5434`.

If `DataPlane:Bind` is **unset**, behaviour equals today: one listener, current CORS, **no** `mk_pub_*` acceptance. The fail-closed table default (`dataPlaneAccess: false`) only affects browser-tier credentials on a data-plane listener that is actually listening.

**CORS is per listener.** Admin defaults include Studio / Hub origins (`https://studio.aouda.com`, `https://hub.aouda.dev`, plus `Aouda:StudioOrigin`) unless `Aouda:CorsOrigins` replaces them. Data-plane origins come **only** from `Aouda:Listeners:DataPlane:CorsOrigins` (empty = no browser origins). Do not put the Studio origin on the data-plane.

The profile is tagged on the **Kestrel connection**. There is no request header you can send to switch profiles.

### What the data-plane returns 404 for

`admin/*`, `_studio/*`, `POST /api/server/shutdown`, `POST …/schema/apply`, `POST …/query`, tables/MQ/graph/jobs/branches, write-stream, `GET /api/databases`, `GET /health/detailed`. Status is **404**, not 403 — a 403 would admit that an admin surface exists.

Allowed: `/health` `/ready` `/startup`, app-auth except `/auth/admin/*`, OIDC/JWKS, named-query execute + batch, named-mutation execute, `/api/databases/{db}/ws`.

---

## `mk_pub_*` vs `mk_anon_*`

| Prefix | May call | Listener |
|---|---|---|
| `mk_anon_` | Signup, signin, refresh, OIDC only | Data-plane (auth). **Denied on data routes.** Keep it that way. |
| `mk_pub_` | Named query / mutation / subscribe (plus auth) | **Data-plane only.** On admin → `401 AUTH_KEY_LISTENER_MISMATCH`. |
| `mk_svc_` | Full data + admin (per RBAC) | Either; **ad-hoc query only on admin** (data-plane `/query` is 404 for everyone). |
| User JWT (end user) | Same as `mk_pub_*` | Data-plane |
| User JWT (Studio operator) | Ad-hoc + admin | Admin |

`mk_pub_*` is provisioned next to anon and service-role when you enable application auth (`PublicKey` on the keys response). It is a distinct prefix so "which keys can read data?" is answerable by inspection.

Do **not** send `X-User-Token` with `mk_pub_*`. That header remains a service-key (`mk_svc_*` / `mk_srv_*`) feature.

---

## Table opt-in (fail-closed)

```json
{
  "tables": {
    "EquityQuote": {
      "dataPlaneAccess": true,
      "columns": { }
    }
  }
}
```

Default is **false**. Existing catalogs deserialize to false. On the data-plane, for `mk_pub_*` and user JWT, a named query that touches a non-opted-in table (including join tables) returns **404 `TABLE_NOT_FOUND`**. Service keys on the data-plane may execute named artifacts over non-opted-in tables. The admin listener ignores the flag.

A named query over a non-opted-in table is still **allowed to apply** — operators and services need it. Browser-tier widening of `dataPlaneAccess` false→true is reported by [`aouda schema diff --access`](access-surface.md).

---

## Quotas and cost

**Persist time (schema apply):** named-query cost is `1 + joinCount`. Defaults: max 3 joins, max cost 8. Exceed → `NAMED_QUERY_TOO_MANY_JOINS` / `NAMED_QUERY_COST_EXCEEDED` with a modelling-fix string ("split the query or drop a join"). Override: `Aouda:NamedQuery:MaxJoins` / `MaxCost`.

**Runtime (data-plane only):** per-identity sliding window, default 60 permits / 60 seconds. One permit per execute, per **batch envelope**, per mutation execute, per subscribe attempt. Exceed → `429 IDENTITY_QUOTA_EXCEEDED` + `Retry-After`. Disabled on admin-only deployments. Config: `Aouda:IdentityQuota:PermitLimit` / `WindowSeconds` / `Enabled`.

Signup 5/min and signin 20/min per IP still apply.

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

---

## Authentication that exists

Application end users today:

1. Browser holds `mk_anon_` (auth endpoints) or `mk_pub_` (auth + named data).
2. `POST /api/databases/{db}/auth/signup` or `/signin` with that key → user JWT + refresh token.
3. Subsequent named-query calls: `Authorization: Bearer <user JWT>` on the **data-plane**.
4. `POST …/auth/refresh` when the access token expires.
5. WebSocket: first message `auth` with the JWT; later `re_auth` with the refreshed token so subscriptions survive. Failed `re_auth` closes the session.

### What is not shipped

**OAuth 2.0 authorization code flow with PKCE is not available** (tracked as BL-043). Token introspection (BL-042) is not available. Do not implement a SPA that redirects to an IdP and expects Aouda to complete the code exchange.

OIDC discovery and JWKS **are** published for **validating JWTs Aouda issued**. That is not a federated login.

Until PKCE exists, the supported browser pattern is: Aouda app-auth signup/signin/refresh (email/password, optional MFA as documented under [Auth](../auth/setup.md)), or a **backend** that holds `mk_svc_*` and never exposes it to the browser.

---

## Worked example: SPA on the data-plane

```typescript
import { AoudaClient } from "@aouda/client";
import { equityQuoteByTicker } from "./generated/named-queries";

const dataPlane = "https://data.example.com"; // :5434 behind TLS

const client = new AoudaClient({
  serverUrl: dataPlane,
  database: "trading",
  appAuth: { apiKey: import.meta.env.VITE_AOUDA_PUB_KEY }, // mk_pub_…
});
await client.connect();

const session = await client.auth.signIn({
  email: "trader@example.com",
  password: "…",
});
// attach session.accessToken per client docs

const quote = await client.namedQueries.execute(equityQuoteByTicker.hash, {
  ticker: "AAPL",
});
```

Ad-hoc from the same client against the data-plane:

```bash
curl -i -X POST https://data.example.com/api/databases/trading/query \
  -H "Authorization: Bearer $JWT" \
  -d '{"table":"EquityQuote"}'
# 404
```

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Studio connect 404 | URL is the data-plane | Point Studio at the **admin** port |
| `AUTH_KEY_LISTENER_MISMATCH` | `mk_pub_*` on admin | Use the data-plane URL, or use `mk_svc_*` / operator JWT on admin |
| `TABLE_NOT_FOUND` for a table you created | `dataPlaneAccess` false | Set true; re-apply; check join tables too |
| `IDENTITY_QUOTA_EXCEEDED` | 60 req / 60 s default | Back off using `Retry-After`; raise `PermitLimit` for known clients |
| Data-plane CORS fails from Studio origin | Different CORS policies | Do not add Studio to data-plane origins |
| WS `NAMED_QUERY_SUBSCRIBE_REQUIRED` | Ad-hoc subscribe on data-plane | Subscribe by `hash` |
| WS `DATA_PLANE_WRITE_STREAM` | `stream_open` on data-plane | Ingest from a service key on admin, or HTTP named mutation |

---

## Not in this release

- Bare internet exposure (no edge).
- PKCE / OAuth authorization code / token introspection.
- Per-identity quotas on the admin listener (operators use the existing global concurrency limiter).
- Extending `mk_anon_*` to read data.

---

## Related

- [Named queries](named-queries.md)
- [Division of responsibility](division-of-responsibility.md)
- [Adopting Aouda](adoption.md) — migrating an existing app onto this model
- [HTTP API](../reference/http-api.md)
- [Studio](studio.md)
- [Cloud and Hub](cloud-hub.md)
- [Server configuration](server-configuration.md)
