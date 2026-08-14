---
title: "Access-surface diff"
nav_order: 12
parent: "Guides"
---

# Access-surface diff

Document status: Complete (P37)  
Last updated: 2026-08-14

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

Narrowing (tighter RLS, removed column, `dataPlaneAccess` true→false) is reported but **does not fail CI**.

`service_key` identities are skipped (always full; they cannot widen).

---

## Identities file

Sibling of `aouda.schema.json` (or `--identities`). Schema `https://aouda.io/identities/v1.json`. **One format** shared with `aouda policy inspect` and TestHarness RLS scenarios.

```json
{
  "$schema": "https://aouda.io/identities/v1.json",
  "identities": [
    {
      "name": "alice",
      "kind": "user",
      "claims": { "sub": "alice" },
      "grants": [{ "dimension": "org", "value": "acme" }]
    }
  ]
}
```

Cap: 32 identities (`ACCESS_SURFACE_TOO_MANY_IDENTITIES`). Invalid document → `AUTH_IDENTITY_INVALID`. Missing file is a **warning**, not a hard error: public-only (`mk_pub_*`) still runs.

Do not add RLS resolver bodies to the schema file. Optional `resolvers` / `baseResolvers` on the HTTP wrapper compare rule-body relaxation; default is the live auth DB (or one shared posted list).

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

The TypeScript CLI (`npx @aouda/client schema diff --access`) is **not** shipped yet. Use `aouda` (.NET tool) in CI.

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
- [Schema CI/CD](schema-cicd.md)
- [HTTP API](../reference/http-api.md)
