# Aouda Documentation

This repository contains the public documentation for [Aouda](https://github.com/aoudadb) — a columnar database engine for .NET with a TypeScript client SDK.

**Published site:** https://aoudadb.github.io/  
**AI agent index:** https://aoudadb.github.io/llms.txt

## Structure

```
getting-started/   Main onboarding guides — embedded, server, auth, testing, backup
guides/            Deep functionality guides — query, schema, hot/cold, streaming, replication, etc.
auth/              Auth and authorization — architecture, setup, client integration, ADRA, reference
clients/           Client SDKs — TypeScript, .NET, distribution
deployment/        Deployment — Kubernetes, Helm, Docker, Windows Service, systemd
ai/                AI agent usage — bootstrap flows, auth patterns, MCP tools
reference/         HTTP API reference, wire protocol, type reference
```

## For AI agents

Read `llms.txt` at the root of the published site for a structured index of all documentation:
https://aoudadb.github.io/llms.txt

## Updating docs

The source files in `docs/dev/` of the main Aouda repository are the primary source of truth. When those files are updated, copy the relevant files here and re-add the Jekyll front matter (the `---` block at the top of each file).

The `_setup.ps1` script at the root of this repo automates that copy process.

## Local preview

```bash
gem install bundler jekyll
bundle exec jekyll serve
# Site at http://localhost:4000
```
