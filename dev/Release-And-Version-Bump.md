# aouda-docs Release and Version Bump — Agent Instructions

**This file is this repo only.** Public docs are not version-lockstep with the server; they record **which** server / SDK / Studio versions a page describes. Sibling repos have their own `Release-And-Version-Bump.md` because not every agent session can see every checkout.

This directory is excluded from the Jekyll site (`_config.yml` `exclude`) — it is for agents and maintainers, not the published nav.

**Related:** [`clients/compatibility.md`](../clients/compatibility.md) (the matrix). Chain map (if available): `D:\GitHub\docs\Cross-Repo-Release-And-Version-Bump.md` or `C:\Data\GitHub\docs\…`.

**Agent guardrails:** Prepare files locally and **stop**. Do not commit or push unless the maintainer says yes in this session.

---

## When this file is invoked

Typical triggers:

- Parallel handoff from `aouda` or `aouda-client-ts` while a train is being cut.
- Docs-only HTTP/guide fixes (no product version bump — still date the changelog if user-visible).
- After Studio pins a new `@aouda/client`.

You can run this **in parallel** with the TS client bump. Push the matrix once the version numbers you cite actually exist (or clearly mark them as the intended train).

---

## 1. Compatibility matrix

Edit [`clients/compatibility.md`](../clients/compatibility.md):

- Add a **new top row** for the server train (do not rewrite history rows).
- Minimum `@aouda/client`, `Aouda.Client`, and Studio for that generation.

This train:

| Artifact | Version |
|----------|---------|
| Server | `0.1.14` |
| Wire / HTTP API notes | v2.6 catalog GET auth linkage; P43 write-side; P42 catalog directory (ops, not wire) |
| `@aouda/client` | `≥ 0.1.16` |
| `Aouda.Client` | `≥ 0.1.14` |
| Studio | `≥ 0.0.21` (pin `0.1.16` after npm) |

---

## 2. Public changelog

Move `CHANGELOG.md` **Unreleased** bullets into a dated section that names the same versions (this train: **0.1.14 — 2026-08-29**). Keep Unreleased empty afterwards.

Include user-facing cross-repo facts: P42/P43, catalog GET `auth.enabled` / `auth.database`, create-role contract, identity stamp / `plsClaimBinding` / claims at mint. Link [HTTP API](../reference/http-api.md) and [Compatibility](../clients/compatibility.md).

Update the intro line that still says “P0–P40 complete” if phases shipped (P41–P43).

---

## 3. Moment 2 (stop)

- [ ] Matrix row matches the versions the maintainer approved
- [ ] Changelog dated section reviewed
- [ ] Ready to **commit**?
- [ ] Ready to **push**? (docs site deploys from `main`)

If Studio is not yet `0.0.21` on GitHub, either wait or write “Studio **0.0.21** (pin after npm)” and ship the docs row when Studio lands.

---

## 4. Chain — where this file sits

```
aouda (server 0.1.14)
  ├─ aouda-client-ts (npm 0.1.16)
  ├─ THIS REPO (matrix + public changelog)   ← can start as soon as numbers are known
  └─ aouda-studio (app 0.0.21, after npm)
```

**Upstream:**

- `aouda/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda/blob/main/docs/dev/Release-And-Version-Bump.md
- `aouda-client-ts/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda-client-ts/blob/main/docs/dev/Release-And-Version-Bump.md

There is usually **no downstream** after docs. Hub is not this chain unless the maintainer asks.
