---
title: "Access-surface diff"
nav_order: 12
parent: "Guides"
---

# Access-surface diff

Document status: Complete (P37; P38 freshness axis)  
Last updated: 2026-08-21

A schema change can widen what an untrusted credential can read. Aouda **reports that before it merges**.

The engine compares two schema states for the built-in browser-tier class (`mk_pub_*`) and for each identity in `aouda.identities.json`. Findings look like:

- *this branch widens what `mk_pub_*` can read from `EquityQuote`*
- *named query `equity.stockOverview` now exposes column `internalSpread`*

Computation lives in the engine so **CI can fail without Studio**. Studio renders the same payload in branch review.

HTTP shapes: [HTTP API — Access-surface diff](../reference/http-api.md#access-surface-diff). Fixture format: same file as policy inspect (`aouda.identities.json`). Identities are **never** a property of `aouda.schema.json`.

---

## Start here

| I want to… | Go to |
|---|---|
| Fail a PR on widening | [CI](#ci-gate) |
| Understand `__public__` | [What is compared](#what-is-compared) |
| Test a specific user | [Identities file](#identities-file) |
| Ask *"what would this user see?"* | [Policy inspect](#policy-inspect) |
| See why an incomparable predicate fails CI | [Fail-closed containment](#fail-closed-containment) |

---

## What is compared

| Axis | Widens when… |
|---|---|
| `__public__` / `mk_pub_*` | `dataPlaneAccess` false→true, or a named query becomes fully opted-in |
| Visibility rank | `none → filtered/full` or `filtered → full` for a fixture identity |
| Named-query projection | `select` / `selectExpr` **adds** a column the identity can already see |
| Named-query added | New alias reachable to that identity |
| Predicate | Effective filter gets weaker, or hashes differ and containment cannot prove narrowing |
| Freshness | Named-query alias `freshness` becomes weaker (`reason: freshness`, `widen`). A tightening is `narrow` and does not fail CI. See [Freshness](freshness.md). |

Narrowing (tighter RLS, removed column, `dataPlaneAccess` true→false, tighter freshness) is reported but **does not fail CI**.

`service_key` identities are skipped (always full; they cannot widen).

---

## Identities file

Sibling of `aouda.schema.json` (or `--identities`). Schema `https://aouda.io/identities/v1.json`. **One format** shared with `aouda policy inspect` and TestHarness RLS scenarios.

`identities` is an **object keyed by identity name**, not an array.

```json
{
  "$schema": "https://aouda.io/identities/v1.json",
  "identities": {
    "alice": {
      "kind": "user",
      "email": "alice@test.local",
      "roles": ["db_reader"],
      "claims": { "tenant_id": "acme" },
      "grants": [
        { "dimension": "org", "partitionKey": "acme", "accessLevel": "read" }
      ]
    },
    "svc": { "kind": "service_key" }
  }
}
```

| Field | Notes |
|---|---|
| key | `^[A-Za-z][A-Za-z0-9_.-]*$`. Duplicate keys are `AUTH_IDENTITY_INVALID`. |
| `kind` | **Required.** `user` or `service_key`. |
| `userId` | Optional UUID. Omitted → deterministic: SHA-256 of `"aouda.identity:" + name`, first 16 bytes as a GUID. A non-UUID value is `AUTH_IDENTITY_INVALID`. |
| `claims` | String values only. |
| `grants` | Each grant needs **all three** of `dimension`, `partitionKey`, `accessLevel` (`read` \| `write` \| `admin`). |

Cap: 32 identities (`ACCESS_SURFACE_TOO_MANY_IDENTITIES`). Invalid document → `AUTH_IDENTITY_INVALID`. Missing file is a **warning**, not a hard error: public-only (`mk_pub_*`) still runs.

The file is never applied and never persisted. Do not add RLS resolver bodies to the schema file. Optional `resolvers` / `baseResolvers` on the HTTP wrapper compare rule-body relaxation; default is the live auth DB (or one shared posted list).

---

## Policy inspect

The diff tells you what **changed**. `policy inspect` tells you what an identity can see **right now** — the mechanical answer to *"what would Alice see in this table?"*, which is what makes "ADRA is the floor" a claim you can check instead of a claim you make.

```bash
aouda policy inspect --identity alice
aouda policy inspect --identity alice --tables EquityQuote,Position --sample
```

The identities file is discovered in this order: `--file` → sibling of `aouda.schema.json` → walking up for `aouda.identities.json`.

HTTP:

```bash
curl -X POST "$AOUDA/api/databases/$DB/policy/inspect" \
  -H "Authorization: Bearer $ADMIN_OR_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "document": { "$schema": "https://aouda.io/identities/v1.json", "identities": { "alice": { "kind": "user" } } },
    "identityName": "alice",
    "tables": ["EquityQuote"],
    "includeSample": true,
    "sampleLimit": 20
  }'
```

You may pass an inline `identity` object instead of `document` + `identityName`. Optional `vectorProbe` (`{ table, column, k }`) and `traverseStart` (`{ table, id, hops }`) check the ANN and edge-traversal paths, which enforce the same predicate as tabular reads.

Per table, the response reports:

| Field | Meaning |
|---|---|
| `visibility` | `full` · `filtered` · `none` |
| `pls` / `rls` | The contributing predicates |
| `effective` | The conjunction actually injected into reads |
| `effectiveHash` | SHA-256 of the canonical `WhereClause` — the same hash the diff compares |
| `sample` / `sampleReason` | Rows the identity would actually get, when `includeSample` is set (`sample_failed` when it could not be produced) |

Errors: `AUTH_IDENTITY_NOT_FOUND`, `AUTH_IDENTITY_INVALID`.

**Credential and listener:** admin listener, with a **service key or an admin JWT**. A `db_reader` JWT gets 403, and the route is 404 on the data-plane — this is an operator and CI tool, not something an application calls.

Run it for one identity per authorization class before you opt a table into the data-plane, and put the output in the migration record.

---

## CI gate

```bash
aouda schema diff --access
```

| Exit | Meaning |
|------|---------|
| **1** | `hasWidening` is true — **fail the PR** |
| **0** | No widening (narrow-only or no findings). Successful plan. |
| **2** | Transport / parse / unreadable identities file |

**Without** `--access`, `schema diff` still exits **0** on a successful plan (even if the server would have reported widening). That is deliberate: existing jobs do not start failing until they opt in.

### GitHub Actions (.NET)

```yaml
- name: Access-surface gate
  env:
    AOUDA_SERVER: ${{ secrets.AOUDA_STAGING_SERVER }}
    AOUDA_DATABASE: ${{ secrets.AOUDA_DATABASE }}
  run: aouda schema diff --access
```

The engine repo's `examples/github-actions/schema-deploy-dotnet.yml` already passes `--access` on the PR step.

**C# CLI or admin HTTP. The TypeScript CLI `--access` flag is not shipped (BL-176).** `npx @aouda/client schema diff --access` does not exist. JS-only pipelines must still run the gate: `dotnet tool install --global Aouda.Cli` (the aoudadb NuGet feed already has `Aouda.Cli`) or the HTTP call below on the **admin** listener.

HTTP equivalent:

```bash
curl -X POST "$AOUDA/api/databases/$DB/schema/diff?access=true" \
  -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat aouda.schema.json), \"identities\": $(cat aouda.identities.json)}"
```

Posting identities requires **Admin**. `?access=true` with a raw schema (no identities) is **Read** and returns `__public__` findings only.

Branch diff: `POST /branches/{name}/diff` with `{ "includeAccess": true }`. Studio always sends that.

C# (`Aouda.Client` on the **admin** listener):

```csharp
var plan = await client.Schema.DiffAsync(
    desired,
    access: new AccessSurfaceDiffRequest { Identities = identitiesDocument });
if (plan.AccessSurface?.HasWidening == true)
    throw new InvalidOperationException("access surface widened");
```

TypeScript: `npx @aouda/client schema diff --access` is **not** shipped. Use the HTTP call above or `aouda schema diff --access`.

---

## Defaults

| Setting | Default |
|---|---|
| Identities file missing | Warning; public-only (`mk_pub_*`) still runs |
| Fixture cap | 32 (`ACCESS_SURFACE_TOO_MANY_IDENTITIES`) |
| `schema diff` without `--access` | Exit 0 on a successful plan (widening is not a CI failure until you opt in) |
| Incomparable predicates | Reported as `widen` / `incomparable_predicate` (CI fails) |
| Identities on `aouda.schema.json` | Rejected (`additionalProperties: false`) |

---

## Fail-closed containment

When both sides are `filtered` but the predicate hashes differ, the engine tries a **structural** compare (added/dropped conjuncts, `eq` vs `in` supersets). Everything else is **incomparable**.

**Incomparable is reported as `widen` / `incomparable_predicate`.** CI fails. That is intentional: a merge must not silently accept "we could not tell." This is not a SAT solver and not static admissibility of client-composed queries.

---

## Studio

Branch review renders widenings first (warning), then narrowings. Load `aouda.identities.json` in the dialog (in memory, never persisted) to see fixture identities; without a file you still see `mk_pub_*` findings.

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Exit 1 after adding a column to a named query `select` | Projection widening | Split a private named query, or accept and document the widening |
| Exit 1 `incomparable_predicate` | Hashes differ, not a proven subset | Rewrite the predicate as an added conjunct, or review as a real widen |
| Exit 0 after tightening RLS | Narrowing is not a CI failure | Expected |
| Missing identities: warning, still exit 1 | Public-only still caught `dataPlaneAccess` | Expected |
| `npx @aouda/client schema diff --access` missing | Not shipped | Use `aouda schema diff --access` |
| Identities in `aouda.schema.json` rejected | `additionalProperties: false` | Keep a sibling file |
| `AUTH_IDENTITY_INVALID` on a file that looks right | `identities` written as an array, or a grant missing `partitionKey` / `accessLevel` | It is an object keyed by name; grants need all three fields |
| `policy inspect` returns 404 | Called against the data-plane listener | Use the **admin** URL with a service key or admin JWT |

---

## Not in this release

- SAT / SMT prover.
- Named-mutation access surface (read surface only).
- Identity file overlays (`aouda.identities.{env}.json`).
- TypeScript CLI `--access` flag.

---

## Related

- [Named queries](named-queries.md)
- [Direct client access](direct-client-access.md)
- [Adopting Aouda](adoption.md) — where this gate sits in a migration
- [Schema CI/CD](schema-cicd.md)
- [HTTP API](../reference/http-api.md)
