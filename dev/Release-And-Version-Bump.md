# aouda-docs Release and Version Bump — Agent Instructions

**This file is this repo only.** Public docs are not version-lockstep with the server; they record **which** server / SDK / Studio versions a page describes. Sibling repos have their own `Release-And-Version-Bump.md` because not every agent session can see every checkout.

This directory is excluded from the Jekyll site (`_config.yml` `exclude`) — it is for agents and maintainers, not the published nav.

**Related:** [`clients/compatibility.md`](../clients/compatibility.md) (the matrix). Chain map (if available): `D:\GitHub\docs\Cross-Repo-Release-And-Version-Bump.md` or `C:\Data\GitHub\docs\…`.

**Agent guardrails:** Prepare files locally and **stop**. Do not commit, push a branch, or open a pull request unless the maintainer says yes in this session. **Changes reach `main` through a pull request, never a direct push** — the site deploys from `main`, so the merge is the publish, and the maintainer merges.

Do **not** copy a version number out of an old revision of this file. Read `aouda`'s `src/Aouda.Server/Aouda.Server.csproj` `<Version>`, `@aouda/client`'s `package.json`, and Studio's `package.json`.

---

## When this file is invoked

Typical triggers:

- Parallel handoff from `aouda` or `aouda-client-ts` while a train is being cut.
- Docs-only HTTP/guide fixes (no product version bump — still date the changelog if user-visible).
- After Studio pins a new `@aouda/client`.

You can run this **in parallel** with the TS client bump, and open the PR as soon as the pages are ready. **Merge it once the version numbers it cites actually exist** — the server tag, the npm version — or clearly mark them as the intended train.

---

## 1. Compatibility matrix

Edit [`clients/compatibility.md`](../clients/compatibility.md):

- Add a **new top row** for the server train (do not rewrite history rows).
- Minimum `@aouda/client`, `Aouda.Client`, and Studio for that generation.
- If this train did not change the TypeScript client, say so in the row and leave the Studio pin where it is.

---

## 2. Retire `next train` markers for what this train ships

Pages mark behaviour that is on `main` but not yet released as `(BL-NNN, next train)`. When the server version that contains that behaviour is the one you are cutting:

- Replace `next train` with the version you are cutting.
- Leave the marker on anything that is still unreleased.
- A marker left saying `next train` after the tag exists tells a reader the page describes a server they cannot install yet.

Do not find them by eye. Fetch the sibling checkouts (`git fetch` in `aouda`, `aouda-client-ts`, `aouda-studio`; the script never does), then run:

```bash
python3 scripts/check-next-train.py        # siblings found next to this repo; --aouda / --client-ts / --studio to point at them
```

It reads each sibling's `origin/main` changelog (`--ref` to change it) and fails, with `file:line`, the BL id, the release it shipped in and the replacement `(**BL-NNN, X.Y.Z**)`, for every marker whose id is in a released section. Run it after the tag exists, and again as the last step before the PR. A marker with no BL id (`Lead S12 (next train)`) is not checked; retire those by hand (`grep -rni "next train" --include=*.md --include=*.txt .`). Tests: `python3 -m unittest discover -s scripts -p "test_*.py"`.

Also move `CHANGELOG.md` **Unreleased** bullets into a dated section that names the same versions. Keep Unreleased for not-yet-shipped clarifications only.

---

## 3. Moment 2 (stop)

- [ ] Matrix row matches the versions the maintainer approved
- [ ] `next train` markers for this train now name the version, and `python3 scripts/check-next-train.py` exits 0
- [ ] Changelog dated section reviewed
- [ ] Ready to **commit** on a branch, push it, and **open the PR**? (publishes nothing)
- [ ] Ready to **merge**? (the docs site deploys from `main`; merge after the versions the pages cite exist)

---

## 4. Chain — where this file sits

```
aouda (server tag: NuGet + RID archives + private image)
  ├─ aouda-client-ts   only if the TS client gained or lost a type
  ├─ THIS REPO         matrix + public changelog + next-train markers
  └─ aouda-studio      only after an npm publish, and only if the pin or the UI moved
```

**Upstream:**

- `aouda/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda/blob/main/docs/dev/Release-And-Version-Bump.md
- `aouda-client-ts/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda-client-ts/blob/main/docs/dev/Release-And-Version-Bump.md

There is usually **no downstream** after docs. Hub is not this chain unless the maintainer asks.
