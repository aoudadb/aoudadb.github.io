---
title: "Local CLI testing (agents)"
parent: "AI Agents"
nav_order: 2
---

# Local CLI testing for AI agents

**When:** you need a live Aouda engine (schema apply, data-plane, keys) and must not disturb an existing local or lab server.

**Not this:** in-process tests with `Aouda.Testing` ([Getting started — Testing](../getting-started/testing.md)), or a human's long-lived `aouda start --port 5433` workspace. Prefer unused ports and a throwaway `--data-dir` under the OS temp folder.

Pin the CLI to the version your project expects (example below uses **0.1.9**). Check `aouda --version` before assuming flags.

---

## Working recipe

```powershell
# 1. Match the pin. `aouda start -h` / `--help` print flags and do not bind.
dotnet tool uninstall -g Aouda.Cli -ErrorAction SilentlyContinue
dotnet tool install -g Aouda.Cli --version 0.1.9
aouda --version   # expect Aouda 0.1.9 (or your pin)

# 2. Own ports + own data dir. Pick free ports; do not reuse a maintainer's or lab map.
$dd = Join-Path $env:TEMP "aouda-agent-probe"
$admin = 26133
$data  = 26134
Start-Process aouda -ArgumentList @(
  "start","--port","$admin","--bind","127.0.0.1","--data-dir",$dd,
  "--data-plane-bind","127.0.0.1:$data"
) -WindowStyle Hidden
# wait until GET http://127.0.0.1:26133/health and :26134/health return 200

# 3. Fresh store → init creates the admin on THIS server.
aouda init --server http://127.0.0.1:26133 --admin-email … --admin-password … --json
# save accessToken; do not print it. Then:
aouda databases create -n auth --kind auth -s http://127.0.0.1:26133 -t <token> --json
# capture auth.keys.anonKey / publicKey from that JSON now — GET list is prefix-only.

# 4. Schema: HTTP body { "schema": <doc>, "options": { "allowDestructive": true } }
#    or `aouda schema apply -s … -d … -f aouda.schema.json`.
#    Named-query names: string literals from aouda.schema.json (codegen Args/Row is optional).

# 5. Data-plane reads: POST …/named-queries/{name}/query — not POST …/query.
# 6. Stop only this process:
aouda stop -s http://127.0.0.1:26133 --force
```

On bash/zsh the same flags apply (`aouda start --port … --data-dir … --data-plane-bind …`). Always pass `-s http://127.0.0.1:<your-admin-port>` to `stop`.

---

## Do not (engine / CLI traps)

| Action | What happens |
|--------|----------------|
| `aouda start -h` / `aouda start --help` | Print start help (flags such as `--port`, `--data-dir`) and **do not** bind a port or create `./data`. |
| `aouda stop` without Bearer | HTTP `stop` is **401**. Kill the recorded PID with `aouda stop -s http://127.0.0.1:<port> --force`. Do not expect unauthenticated HTTP shutdown. |
| `aouda stop` without `-s http://127.0.0.1:<your-port>` | Can target the wrong process / URL |
| Reuse another store's `mk_svc_` / admin token against a new `--data-dir` | `AUTH_API_KEY_INVALID` — keys belong to that store |
| Sign in / init against someone else's running server | Wrong admin, wrong data; init is for **this** server's setup mode |
| `POST /api/databases/{db}/query` on the **data-plane** | **404 by design.** Execute `POST /named-queries/{name}/query` (or batch). Ad-hoc query is admin-listener only. |
| `partitionKey: 1` (or a bare number) on a column | `INVALID_REQUEST`. Table-level: `"partitionKey": [{"column":"Ticker"},{"column":"Source"}]`, `"clusterColumns": ["Time"]` |
| Named-query `where` as a JSON **array** | Use an object: `{ "and": [ … ] }` (same for join `on`) |
| `offsetParam` without a positive `"offset"` cap | Schema apply fails |
| `Timestamp` as the time column for some `latestPerKey` / `aggregate` paths | `Invalid cast from DateTime to Int64`. Prefer **Int64** epoch milliseconds for that `orderBy` / time-bucket input when you hit this |
| Treat query `data` as an array of row objects | Default body is **columnar**: `columns` + `data` + `rowCount` |
| Expect raw `mk_anon_` / `mk_pub_` on `GET` keys list | Full secrets appear on **create** / **regenerate-keys** only. List responses are prefix / metadata, not usable keys |
| `mk_pub_*` on the **admin** listener | `AUTH_KEY_LISTENER_MISMATCH` (expected — use the data-plane bind) |
| Data-plane CORS as an indexed env key (`…CorsOrigins__0=…`) or a JSON **array** | `CorsOrigins` is a **single string** (comma-separated origins). Indexed/`__0` binding can crash Kestrel on 0.1.9 |

### CORS shape (correct)

```json
{
  "Aouda": {
    "Listeners": {
      "DataPlane": {
        "Bind": "127.0.0.1:26134",
        "CorsOrigins": "https://app.example.com"
      }
    }
  }
}
```

Compose / env (one string, not `__0`):

```text
Aouda__Listeners__DataPlane__CorsOrigins=https://app.example.com
```

---

## Schema and execute reminders

- Apply envelope wraps the document: `{ "schema": { … }, "options": { "allowDestructive": true } }`. A bare table map is not the HTTP body.
- Browser / data-plane callers execute by **name** (string literal from the schema). See [Named queries](../guides/named-queries.md) and [Direct client access](../guides/direct-client-access.md).
- For product-shaped examples (watchlist, `latestPerKey`, candles), see [Market data](../guides/market-data.md) and `examples/p40-browser-tier/`.

---

## Related

- [Quick start for AI agents](quick-start.md) — minimal connect / insert path
- [How to build apps](../guides/build-apps.md#rules-for-ai-agents) — hard rules once a server exists
- [Server configuration](../guides/server-configuration.md) — ports, data-dir, env naming
- [HTTP API](../reference/http-api.md) — wire truth for apply / named-query execute
