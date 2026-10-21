# Review — Flywheel S01 public docs

Reviewed the uncommitted diff on `claude/flywheel-s01-docs` against `CreateDatabaseRequest` / `CreateDatabaseAuthRequest` and the rejection in `DatabasesController.CreateDatabase` (about lines 161–166), and against `databases.create` in the Flywheel S01 client worktree (`src/databases.ts`, `src/types.ts`). Date: 2026-10-21. The client worktree was not edited.

## Summary

The two-file diff documents create-database signup fields the HTTP reference had omitted, and it drops the old claim that `kind` is mutually exclusive with `auth`. The server rejects only a kind that normalizes to `auth` when an `auth` object is also present. `kind: "data"` with `auth` is accepted, and so is an omitted `kind` with `auth`. Top-level `allowSelfSignup` / `selfSignupRole` are applied on the `kind: "auth"` path. Nested `auth.allowSelfSignup` / `auth.selfSignupRole` are applied to the application database being linked. An omitted signup flag deserializes as false. A null or omitted role is stored null and resolved to `db_writer` at signup.

The client sends each of those fields only when the caller sets it, including `false`, `null`, and an empty string, and it sends both `kind` and `auth` when both are set. It does not send `dataDurability`.

Two statements in the draft were wrong: the TypeScript page marked the client behaviour as 0.5.0, and the `kind` note said the auth-plus-`auth` pair was the only rejection. Those are fixed below. The signup rows were already right and were left as written.

The review file is `_review/Flywheel-S01-docs-review.md`. `_config.yml` has no `collections` entry and does not exclude `docs` or `docs/review`. The site root is the repo root, and `defaults` apply `layout: default` to every page, so a markdown file at `docs/review/` would be published. `_review/` is not a Jekyll special directory, so Jekyll ignores it.

## Must Fix

- **S01-M1** `clients/typescript.md` marked `client.databases.create` auth options as `(**0.5.0**)`. `@aouda/client` 0.5.0 is already published. On that release, `databases.create` writes `enableWal`, `replicationMode`, `maxMemoryShareBytes`, and `defaultTemperature` only, and drops anything else. The Flywheel S01 changeset is an unreleased minor (BL-1123). A 0.5.0 marker tells a reader the installed client already sends `kind` and `auth`.

  Resolution: the marker is `(**BL-1123, next train**)`.

## Should Fix

- **S01-S1** `reference/http-api.md` said “Only `kind: "auth"` together with `auth` is rejected (400).” That is too strong: a `kind` other than `auth` or `data` is also 400. It also never said the combination the old “mutually exclusive” sentence had forbidden. `kind: "data"` with an `auth` object is valid, and omitting `kind` with `auth` is valid. The request example already shows `"kind": "data"` plus `"auth"`.

  Resolution: the `kind` note now says `"data"` or an omitted `kind` is a data database and both may include `auth`, and that `kind: "auth"` together with an `auth` object is rejected (400).

- **S01-S2** The TypeScript sentence listed `auth` as one field sent when set. The client does not forward the object whole: `enabled`, `database`, `allowSelfSignup`, and `selfSignupRole` are copied only when each one is set, so an unset nested key is absent and the server default applies. The same sentence did not say the client still sends `kind` and `auth` together, which is what the server then accepts or rejects.

  Resolution: the paragraph says nested keys are included only when set, that both `kind` and `auth` are sent when the caller sets both, that the server rejects `kind: "auth"` together with an `auth` object (400), and that `kind: "data"` with `auth` is valid.

## Nice to Have

- The kind check folds case (`ToLowerInvariant`, then `OrdinalIgnoreCase` on the auth path). `"Auth"` with an `auth` object is the same 400, and `"Data"` is a data database. The pages quote the lowercase tokens the table already lists. Not edited.
- A non-empty `selfSignupRole` is stored as given. Create does not look the role up. Signup and `PUT …/auth/admin/signup-settings` refuse a name that is not in the auth database; whitespace is treated as omitted and becomes `db_writer`. `auth/setup.md` already says the role must exist. Not edited.
- `CHANGELOG.md` `## Unreleased` does not mention BL-1123. Left alone so this diff stays the two public pages plus this review.

## Left because already correct

- Top-level `allowSelfSignup` / `selfSignupRole`: applied when `kind` is `"auth"`. Omitted signup is off. Null or omitted role is `db_writer`.
- `auth.allowSelfSignup` / `auth.selfSignupRole`: applied to the linked application database, with the same omitted defaults.
- The TypeScript page does not mention `dataDurability`. The client does not send it. The HTTP `dataDurability` row was already there and still matches the server.
- `guides/storage.md`, `guides/write-durability.md`, and `guides/partitioning.md` were not part of this diff and were not edited.

## Tests & Coverage

Docs only. No tests run. Checked by reading the controller and the client `create` body builder.
