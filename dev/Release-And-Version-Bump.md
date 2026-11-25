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

Pages mark behaviour that is on `main` but not yet released as `(**BL-NNN, next train**)`. When that behaviour ships:

- **Remove the marker** (or rewrite the sentence so it reads as current behaviour). Do **not** stamp a release version into the page prose.
- Version numbers belong in three places only: the [compatibility matrix](../clients/compatibility.md), this repo's [`CHANGELOG.md`](../CHANGELOG.md), and [Upgrading](../guides/upgrading.md) where a format or upgrade step needs them.
- Leave a `next train` marker only for work that is still unreleased (e.g. Studio UI still pending). Prefer **one** section-level marker over repeating the same id on every row.
- A marker left saying `next train` after the tag exists tells a reader the page describes a server they cannot install yet.

Do not find them by eye. Fetch the sibling checkouts (`git fetch` in `aouda`, `aouda-client-ts`, `aouda-studio`; the script never does), then run:

```bash
python3 scripts/check-next-train.py        # siblings found next to this repo; --aouda / --client-ts / --studio to point at them
```

It reads each sibling's `origin/main` changelog (`--ref` to change it) and fails, with `file:line`, the BL id and the release it shipped in, for every marker whose id is in a released section. `_ALLOW` holds ids whose released changelog mention is an older open note, not the fix still marked `next train` — clear an id in the same commit that removes its markers. Run it after the tag exists, and again as the last step before the PR. A marker with no BL id (`Lead S12 (next train)`) is not checked; retire those by hand (`grep -rni "next train" --include=*.md --include=*.txt .`). Tests: `python3 -m unittest discover -s scripts -p "test_*.py"`.

**Retire markers as edits of the marker, never as a rewrite of the page.** The 0.17.0 sweep (`42bfd3b`) ran one pattern that began at any `(**` and one that tidied the spaces and brackets a marker leaves; it broke the code of 80 pages and swallowed 18 passages (BL-1865). A pattern matches one marker, on its own ids (`(**BL-NNN, next train**)`), and touches nothing outside it; what punctuation it leaves is fixed by hand. A script that rewrote pages is checked before the PR, and its diff read:

```bash
python3 scripts/check-code-fences.py --base origin/main   # exit 0; --max-lines N for an intended change of more than two such lines
git diff --stat origin/main                               # a marker sweep changes as many lines as there were markers
```

Also move `CHANGELOG.md` **Unreleased** bullets into a dated section that names the same versions. Keep Unreleased for not-yet-shipped clarifications only. Changelog bullets may cite a card once when it helps an operator; do not decorate every guide sentence with backlog ids.

---

## 3. Moment 2 (stop)

- [ ] Matrix row matches the versions the maintainer approved
- [ ] Shipped `next train` markers are **removed** (not version-stamped), and `python3 scripts/check-next-train.py` exits 0
- [ ] `python3 scripts/check-code-fences.py --base origin/main` exits 0, and the diff removes markers only
- [ ] Changelog dated section reviewed
- [ ] Ready to **commit** on a branch, push it, and **open the PR**? (publishes nothing)
- [ ] Ready to **merge**? (the docs site deploys from `main`; merge after the versions the pages cite exist)

---

## 4. Chain — where this file sits

```
aouda (server tag: NuGet + RID archives + private image)
  ├─ aouda-client-ts   only if the TS client gained or lost a type
  ├─ THIS REPO         matrix + public changelog + strip shipped next-train markers
  └─ aouda-studio      only after an npm publish, and only if the pin or the UI moved
```

**Upstream:**

- `aouda/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda/blob/main/docs/dev/Release-And-Version-Bump.md
- `aouda-client-ts/docs/dev/Release-And-Version-Bump.md` — https://github.com/aoudadb/aouda-client-ts/blob/main/docs/dev/Release-And-Version-Bump.md

There is usually **no downstream** after docs. Hub is not this chain unless the maintainer asks.
