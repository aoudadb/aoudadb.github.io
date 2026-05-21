---
title: "Home"
nav_order: 0
description: "Aouda — columnar database engine for .NET with TypeScript client SDK"
---

# Aouda Documentation

Aouda is a **columnar database engine** for .NET with a TypeScript client SDK. It runs embedded in your process (like SQLite) or as a standalone server (like PostgreSQL). You control what stays in memory — from fully in-memory sub-millisecond access to terabytes on disk with only active partitions loaded.

---

## Install and run in 60 seconds

```bash
# Install the CLI
dotnet tool install -g Aouda.Cli

# Start a dev server (port 5433, database "default", schema-on-write)
aouda dev
```

```bash
# .NET client
dotnet add package Aouda.Client

# TypeScript client
npm install @aouda/client
```

```bash
# Docker (server + Studio)
docker compose up
# Aouda at http://localhost:5000  •  Studio at http://localhost:3000
```

---

## What Aouda gives you

| Capability | Detail |
|---|---|
| **Columnar storage** | Data stored column-by-column — analytical queries only read the columns they need |
| **Configurable memory residency** | Hot data in raw arrays for sub-ms access; cold data compressed on disk, loaded on demand |
| **Schema-on-write** | Tables and columns created automatically on first insert — no upfront design required |
| **Zero index management** | Zone maps, bloom filters, and sparse primary indexes maintained automatically |
| **Dual deployment** | Embedded (in-process, no network) or server (HTTP, multi-client, multi-language) |
| **Two-layer auth** | Server auth (who can connect) + Application auth (your app's end users) — independent systems |
| **AI-native** | `aouda dev` starts with defaults; structured errors with `suggestion` field; schema inference |

---

## Where to start

**Building an application on Aouda?**
→ [Getting Started](getting-started/) — full guide covering embedded mode, server mode, data operations, schema, and auth

**Using the TypeScript client?**
→ [TypeScript Client](clients/typescript/) — query builder, typed queries, auth, MCP tools

**Setting up authentication?**
→ [Auth and Authorization](auth/) — two-layer auth model, API keys, JWT, ADRA modes

**Deploying to production?**
→ [Deployment](deployment/) — Kubernetes, Helm, Docker, Windows Service, systemd

**Building with AI agents?**
→ [AI Agent Quick Start](ai/quick-start/) — minimal bootstrap for agent-driven workflows

---

## Key concepts

Aouda has **two deployment modes** — the database engine is the same in both:

- **Embedded** — engine runs inside your process, direct API calls, no network, ideal for tests, tools, and single-process apps
- **Server** — standalone HTTP server, multiple clients, .NET + TypeScript + HTTP, replication, Studio management console

Aouda has **two independent auth systems**:

- **Server auth** — controls which services and developers can connect to the Aouda server (like PostgreSQL roles)
- **Application auth** — provides signup/signin/JWT for your app's end users (like Supabase Auth or Auth0)

Either can be used independently, together, or not at all.
