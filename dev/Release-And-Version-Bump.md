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
| Server | `0.1.22` |
| Wire / HTTP API notes | MQ `isStale`/`staleReason`; refresh await + bulk-load `mqRebuildStatus`; `MaxConnections` default `0`; `RefreshAwaitTimeout` 120s; P46 bulk-load MQ materialization |
| `@aouda/client` | `≥ 0.1.21` (pin after npm — published line still `0.1.20`) |
| `Aouda.Client` | `≥ 0.1.22` |
| Studio | `≥ 0.0.24` (pin `0.1.21` after npm) |

---

## 2. Public changelog

Move `CHANGELOG.md` **Unreleased** bullets into a dated section that names the same versions (this train: **0.1.22 — 2026-09-10**). Keep Unreleased for not-yet-shipped clarifications only.

Include user-facing cross-repo facts for this train: P46 bulk-load MQ materialization, BL-419 wait APIs / `MaxConnections` default / `RefreshAwaitTimeout`, BL-427 staleness + health Degraded, BL-432/424 correctness, BL-423 lifecycle, WS auth handshake. Link [HTTP API](../reference/http-api.md) and [Compatibility](../clients/compatibility.md).

Update the intro line phase range when newer phases ship (currently P0–P46).

---

## 3. Moment 2 (stop)

- [ ] Matrix row matches the versions the maintainer approved
- [ ] Changelog dated section reviewed
- [ ] Ready to **commit**?
- [ ] Ready to **push**? (docs site deploys from `main`)

If `@aouda/client` **0.1.21** is not yet on npm, write “pin after npm” and ship the docs row with that marker; refresh the pin note after publish.

---

## 4. Chain — where this file sits

```
aouda (server 0.1.22)
  ├─ aouda-client-ts (npm 0.1.21 after publish; published line still 0.1.20)
  ├─ THIS REPO (matrix + public changelog)   ← can start as soon as numbers are known
  └─ aouda-studio (app 0.0.24, pin 0.1.21 after npm)
```

**Upstream:**

- `aouda/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda/blob/main/docs/dev/Release-And-Version-Bump.md
- `aouda-client-ts/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda-client-ts/blob/main/docs/dev/Release-And-Version-Bump.md

There is usually **no downstream** after docs. Hub is not this chain unless the maintainer asks.
