---
title: "Declare a server in one file"
nav_order: 2.55
parent: "Guides"
---

# Declare a server in one file: `aouda.json` (**BL-1463, next train**)

A server has **one declaration**: a JSON file, `aouda.json`, that says which databases exist, which schema file each one applies and
which roles an auth database has. A wipe of the data directory followed by a plain start brings the same databases, links, schemas and roles back from it, empty of data. The
file is checked, in full and at once, before the server opens anything: [`aouda plan`](plan.md) runs that check offline, and
[`aouda reload`](declared-databases.md#changing-the-declaration-without-a-restart-bl-1427-0140) applies a changed file to a running server.

This page is the walkthrough. Every member, with its default and its code, is in the [reference](../reference/declaration.md).

**A declaration is not a setting.** The file holds *what exists*. *How the server runs* (the port, the memory budget, the data
directory, where the declaration is) stays in settings: `appsettings.json`, environment variables and switches. Two settings belong
to the file and are the only ones that name it: `Aouda:Declaration` and `Aouda:Environment`.

---

## The smallest file

```json
{ "version": 1 }
```

It declares nothing. `version` is required and `1` is the only version this server reads; a file without it, or with another
number, is refused with `DECLARATION_VERSION_UNSUPPORTED`.

## A file with databases

Two data databases share one application auth database. `shop` applies a schema file; the path is relative to the directory of
`aouda.json`.

```jsonc
{
  "$schema": "https://aoudadb.github.io/schemas/aouda-declaration.v1.json",
  "version": 1,
  // Comments and trailing commas are allowed.
  "databases": {
    "auth": {
      "kind": "auth",
      "roles": {
        "analyst": {
          "description": "Reads every table",
          "statements": [ { "actions": ["read"], "resources": ["shop/table/*", "reports/table/*"] } ],
        },
      },
    },
    "shop": {
      "kind": "data",
      "authDatabase": "auth",
      "schema": "schema/shop.aouda.schema.json",
      "memoryWeight": 2,
    },
    "reports": {
      "kind": "data",
      "authDatabase": "auth",
      "durability": "os",
      "defaultTemperature": "ColdPreferred",
    },
  },
}
```

`kind` is required on every database: an entry with only a name declares nothing and is refused (`DATABASE_KIND_INVALID`). Every
other member is optional and has a default (the [reference](../reference/declaration.md#databasesname) lists them).

---

## Where the server finds it

**Only where you say.** The setting `Aouda:Declaration` holds the path of the file; there is **no default path and no search**. A
server started without it declares nothing, and says so: `declaration: none` in the log and in the plan.

| Source | Spelling |
|---|---|
| Switch | `aouda start --declaration /etc/aouda/aouda.json`, `aouda plan --declaration ./aouda.json` |
| Environment | `AOUDA_DECLARATION=/etc/aouda/aouda.json`, or `Aouda__Declaration=…` |
| `appsettings.json` | `{ "Aouda": { "Declaration": "/etc/aouda/aouda.json" } }` |

A relative path is relative to the working directory. A value that is **set** and does not name a readable file refuses the start:
a missing file, a directory (a bind mount of a file that did not exist on the host makes one) or an empty file. That is on purpose:
a server that quietly started with nothing declared because a volume was not mounted would have no databases and no warning. A
missing file is reported as a fault of the environment (exit status 1, not 78), because a volume that is not mounted yet clears
when it is. An **empty** value, as a compose file passes through for a variable that is not set, counts as not set.

## Environments: an overlay

The process setting `Aouda:Environment` (`--env NAME`, `AOUDA_ENVIRONMENT=NAME`) selects an environment, one per process. With it
set, the server also reads `aouda.NAME.json` in the same directory and merges it over the file ([RFC 7396](https://www.rfc-editor.org/rfc/rfc7396)):
members merge, a value replaces, an array replaces whole, `null` removes. The same environment selects the overlay of each schema
file (`shop.aouda.schema.json` → `shop.aouda.schema.prod.json`, beside it), as `aouda schema --env` does.

`aouda.prod.json`, which makes `reports` memory-only in `prod`:

```json
{ "databases": { "reports": { "durability": "memory" } } }
```

An overlay may not carry `version`. An overlay that is named by the environment and does not exist is information
(`OVERLAY_ABSENT`) and the file is read alone; one that exists and cannot be read is an **error**, never a silent fallback to the
file. `Aouda:Environment` is a name (letters, digits, `_`, `.`, `-`), not a path.

---

## Running it

**Docker Compose.** Mount the directory that holds the file and name it:

```yaml
    environment:
      Aouda__Declaration: /etc/aouda/aouda.json
      AOUDA_ENVIRONMENT: prod
    volumes:
      - ./aouda:/etc/aouda:ro
```

with `aouda.json`, `aouda.prod.json` and `schema/shop.aouda.schema.json` in `./aouda`. Mount the **directory**, not the file: an
edit of a single bind-mounted file is not always seen by the running container, and a reload then reads the old content.

**Check it before you deploy.** `aouda plan --declaration ./aouda/aouda.json --env prod` runs the start's checks offline and
lists every problem at once, without a data directory ([Plan a declaration](plan.md)). Its report names the file it read, and `--json` carries
`declaration.file`, `declaration.overlay` and `declaration.environment` (the `Aouda:Environment` it used, or `null`).

**Change it without a restart.** `aouda reload` reads the file and its overlay again from the path the server was started with.
A new database, a schema file and the roles reload; the other members need a restart (the reload lists them as
`restartRequired`). A changed `Aouda:Declaration` or `Aouda:Environment` is `restartRequired` too and is not followed. A file that has disappeared or cannot be read refuses the reload and changes nothing; it does not retract
the databases. See [Declared databases](declared-databases.md#changing-the-declaration-without-a-restart-bl-1427-0140).

**Kubernetes.** The Helm chart renders the file from the value `declaration.file` into a ConfigMap, mounts it at
`/etc/aouda/aouda.json` and sets `Aouda__Declaration` for you ([Kubernetes](../deployment/kubernetes.md)).

---

## From `Aouda:Databases`

`Aouda:Databases` is **no longer read**. A server that finds one of its settings, in `appsettings.json`, in the environment or on
the command line, refuses to start (`SETTING_REMOVED`) and the message names the member of the file that replaces it. Nothing is
converted for you and the two are never merged. Declaring both `Aouda:Declaration` and `Aouda:Databases:app:Kind` is the same
refusal.

A server that declared this in `appsettings.json`:

```json
{
  "Aouda": {
    "Databases": {
      "shop": { "AuthDatabase": "auth", "SchemaFile": "schemas/shop.json", "SchemaEnvironment": "prod", "MemoryWeight": 2.0 }
    }
  }
}
```

declares it in `aouda.json` (and sets `AOUDA_ENVIRONMENT=prod`):

```json
{ "version": 1, "databases": { "shop": { "kind": "data", "authDatabase": "auth", "schema": "schemas/shop.json", "memoryWeight": 2 } } }
```

| Was | Is |
|---|---|
| `Aouda:Databases:<db>:Kind` | `databases.<db>.kind` (**required** now: there is no default) |
| `:AuthDatabase` | `databases.<db>.authDatabase` |
| `:SchemaFile` | `databases.<db>.schema` (relative to the file, not to the working directory) |
| `:SchemaEnvironment` | the process setting `Aouda:Environment` (`--env`, `AOUDA_ENVIRONMENT`), one for the whole server |
| `:SchemaAllowDestructive` | `databases.<db>.schemaAllowDestructive` |
| `:Durability`, `:ReplicationMode`, `:WriteConcern`, `:WriteConcernTimeoutMs`, `:OnWriteConcernTimeout`, `:DefaultTemperature`, `:MemoryWeight`, `:MaxMemoryShareBytes` | the same name in camelCase: `databases.<db>.durability`, … |
| `:Roles:<role>` (`Description`, `Permissions`) | `databases.<auth>.roles.<role>` (`description`, `statements`). A `permissions` list is refused |

The member names are **case-sensitive**: `"Kind"` is refused, and the message names `kind`.

If the declaration used the unreleased `--config` switch, `AOUDA_CONFIG_FILE` or a file read from `/etc/aouda/aouda.json` without
any setting (a build of `main` between 0.14.0 and this train), none of the three exists: name the file with `Aouda:Declaration`.

---

## Related

- [The declaration file: reference](../reference/declaration.md): every member, default and code
- [Declared databases](declared-databases.md): what a wipe loses and a start recreates, the order of a start, `/ready`
- [Plan a declaration](plan.md) and [Declaration Finding Codes](../reference/plan-codes.md)
- [Schema management: let the server apply it at start](schema-management.md#let-the-server-apply-it-at-start)
- [Kubernetes](../deployment/kubernetes.md), [Docker](../deployment/docker.md), [Linux](../deployment/linux.md)
