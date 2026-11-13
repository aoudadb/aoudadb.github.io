---
title: "Check a schema file offline"
nav_order: 4.5
parent: "Guides"
---

# Check a schema file with no server: `aouda schema check` (**BL-1419, 0.12.0**)

`aouda schema check` validates a schema file (`aouda.schema.json`, and with `--env` its overlay) with **no server and no data directory**.
It is made for CI, before anything is running, and for the step before `schema apply`.

Status: shipped in **0.12.0** in the `aouda` command-line tool.

```bash
aouda schema check --file aouda.schema.json
aouda schema check --file aouda.schema.json --env prod
aouda schema check --file aouda.schema.json --json
```

| Option | Meaning |
|---|---|
| `--file <path>` | The schema file. Without it the tool looks for `aouda.schema.json` from the current directory, and reports `No schema file found. Add aouda.schema.json or use --file <path>.` when there is none |
| `--env <name>` | Also merge the overlay that sits beside the file, as the server would read it: `<file without .json>.<name>.json` (`aouda.schema.<name>.json` for `aouda.schema.json`; **BL-1460, next train**: named after the file, it was always `aouda.schema.<name>.json`) |
| `--json` | Print one JSON document instead of text |

It takes no `--server`, `--database` or token, and reads none.

## What it checks

In this order, stopping at the first stage that fails:

1. **JSON syntax.** `Not valid JSON (line <n>, column <m>): ...`
2. **The server's own read of the file**: the one reader `schema apply`, `schema diff`, `POST …/schema/apply` and `…/schema/diff` and the
   start-time apply use (**BL-1460, next train**). It refuses every **unknown or wrong-case member** first, each with its JSON pointer and,
   when one is close, the member meant, code `SCHEMA_UNKNOWN_MEMBER`:

   ```text
   error: aouda.schema.json: /tables/orders/columns/status/nulable: unknown member 'nulable' at /tables/orders/columns/status; did you mean 'nullable'? (SCHEMA_UNKNOWN_MEMBER)
   error: aouda.schema.json: /tables/orders/Policy: unknown member 'Policy' at /tables/orders; did you mean 'policy'? Member names are case-sensitive. (SCHEMA_UNKNOWN_MEMBER)
   ```

   When no member is close it lists the members known there (`… Known members here: …`). Then a wrong JSON type (`"nullable": "yes"`)
   and the document's own rules (column types, partition functions, a `clusterColumns` entry that is not a column of the table, …).
3. **The `--env` overlay**, read the same way, and the merge. An `--env` with no overlay file is a **warning**, not an error: `environment
   '<name>' has no overlay file (<path>); the base file alone was checked, as the server would read it.` (the server also uses the base
   file). An overlay that exists but cannot be read, or is empty, is an error naming it (**BL-1460, next train**; it was skipped).
4. **The apply-time checks that need no tables**: authorization mode and its resolver or column, partition-level security needing a partition
   key, partition and `pkUniqueness` values, column defaults, and the shape and ceilings of named queries and named mutations. They are the same
   functions the apply path calls, not copies of them. `check` uses the **default** named-query ceilings (max 3 joins, max cost 8), not the
   ceilings a particular server is configured with.

Every problem of a stage is reported, not only the first.

**One reader, one verdict (BL-1460, next train).** Until this train `check` first evaluated the published JSON Schema
(`aouda-schema.v1.json`), which had fallen behind the server: it refused valid files (named-query `aggregates`, `groupBy`, `perKey`, a
parameter's `serverTime`, `settings.allowTruncatingTimestampToDate`, an overlay's `extends`, the server's own `schema export`), while the
server applied the files `check` refused with the unknown member dropped. Now `check` gives the server's verdict. The JSON Schema is still
published for editors (`"$schema": "https://aouda.io/schema/v1.json"`) and lists exactly the members the server reads.

## Output and exit status

| Exit | Meaning |
|---|---|
| `0` | The file is valid |
| `2` | The file is not valid (or could not be read) |

Text form, one line per problem on standard error, then a summary:

```text
error: <file>: <JSON pointer>: <reason>
Schema file is invalid: <n> problem(s).
```

On success: `Schema file is valid: <file>`, then `. Checked offline: references between tables and columns are checked when the schema is
applied.`

With `--json` the output is one document, and the exit status is the same:

```json
{ "ok": false, "file": "aouda.schema.json", "problems": [ { "file": "aouda.schema.json", "path": "/tables/orders", "message": "...", "code": null } ], "warnings": [] }
```

`path` is a JSON pointer into the document (`/` when the whole file); for an unknown member it points at the member itself.
`code` is the error code the server answers the same problem with when it has its own (`SCHEMA_UNKNOWN_MEMBER`), else `null`
(**BL-1460, next train**).

## What it cannot see

Everything that needs the tables to exist is still refused at **apply** time, not by `check`: references between tables and columns; a
primary-key column being a column of the table; a named query or mutation naming a missing column; a materialized query's source; and the
difference between the file and the live database (a partition-key change, a column dropped from a table). (Partition-key and cluster
columns are checked against the table's own columns in the file.)

## `schema check` and `schema validate` are different

| | `schema check` | `schema validate` |
|---|---|---|
| Needs a running server | no | **yes** |
| Question | Is the file well-formed and acceptable on its own? | Does the live database match the file (drift)? |
| Exit | 0 valid, 2 invalid | 0 in sync, 1 drift, 2 error |

Use `check` on every pull request and `validate` in a job that should fail when someone changed the database by hand. Their `--help` texts say
which is which.

## The server's start runs the same check

A declared database whose `SchemaFile` is applied at start ([Declared databases](declared-databases.md)) now runs the same checks on every
file **before it changes any database**, with that server's own named-query ceilings. A file `schema check` passes therefore cannot fail the
start for a reason that sits in the document alone. Before 0.12.0 such an error (say `partitionLevelSecurity` on a table with no partition key)
surfaced as a failed change after the databases before it had been applied.

`POST …/schema/apply` and `…/schema/diff` run them too, before anything changes, with the server's ceilings (**BL-1460, next train**): a
document with such an error is answered `400` and nothing is applied. The apply used to create the valid tables beside it and report the
bad one as a failed entry.

## See also

- [Schema CI/CD](schema-cicd.md) and [Schema management](schema-management.md).
- [Access-surface diff](access-surface.md) for a gate on widened access.
