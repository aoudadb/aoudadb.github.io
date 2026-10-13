# Aouda Docs

This repository is the **canonical public documentation** for [Aouda](https://github.com/aoudadb) — a columnar database engine for .NET with a TypeScript client SDK.

**Published site:** https://aoudadb.github.io/  
**AI agent index:** https://aoudadb.github.io/llms.txt

End users and third-party clients have **no other internet source of truth** besides this site, the live HTTP API, and the published SDKs (`@aouda/client`, `Aouda.Client`). Engine-repo `docs/dev/` and ADRs are **implementer-facing**. When docs and code disagree, **code and tests win** and this site must be updated.

The wire contract is [reference/http-api.md](reference/http-api.md). Do not resurrect a `WIRE-PROTOCOL.md` in any Aouda repository.

## Structure

```
getting-started/   Main onboarding guides — embedded, server, auth, testing, backup
guides/            Deep functionality guides — query, schema, named queries, streaming, …
auth/              Auth and authorization — architecture, setup, client integration, ADRA, reference
clients/           Client SDKs — TypeScript, .NET, distribution
deployment/        Deployment — Kubernetes, Helm, Docker, Windows Service, systemd
ai/                AI agent usage — bootstrap flows, auth patterns, MCP tools
reference/         HTTP API reference, type reference
```

## For AI agents

Read `llms.txt` at the root of the published site for a structured index of all documentation:
https://aoudadb.github.io/llms.txt

Browser-tier apps must use [named queries](guides/named-queries.md) on the [data-plane listener](guides/direct-client-access.md). Do not compose ad-hoc queries with `mk_pub_*`. OAuth authorization-code + PKCE is **not shipped**.

Agents standing up a throwaway local engine: [Local CLI testing (agents)](ai/local-cli-testing.md) — do not run `aouda start -h`.

## Updating docs

Edit markdown **in this repository** with UTF-8-safe tools (not PowerShell `Set-Content`). **Save every page as UTF-8 without a BOM.** Jekyll does not recognise front matter that starts with a BOM, so the page is published as a raw `.md` file and its URL is a 404 — it happened twice (stripped 2026-05-21 and again 2026-10-09). The `aouda` repo's "UTF-8 with BOM" rule (its `AGENTS.md` §2.10) does **not** apply here. Match live `Aouda.Protocol` DTOs and controller routes. After HTTP-surface changes, update `reference/http-api.md` in the same change.

## Local preview

```bash
gem install bundler jekyll
bundle exec jekyll serve
# Site at http://localhost:4000
```

## Checking links

Link to another page by its `.md` file, relative to the page you are editing (`[sizing](../guides/sizing.md#anchor)`):
`jekyll-relative-links` rewrites it to the page's URL. A directory-style link (`../guides/sizing/`) is resolved against the
*published* URL, which is one level deeper than the source file, and breaks. After a change, build and check every internal
link and `#anchor`:

```bash
bundle exec jekyll build -d /tmp/aouda-site      # any directory outside the repo
python3 scripts/check-anchors.py /tmp/aouda-site # exit 1 and one line per broken link
python3 -m unittest discover -s scripts -p "test_*.py"
```
