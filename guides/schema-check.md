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
| `--env <name>` | Also merge the overlay `aouda.schema.<name>.json` that sits beside the file, as the server would read it |
| `--json` | Print one JSON document instead of text |

It takes no `--server`, `--database` or token, and reads none.

## What it checks

In this order, stopping at the first stage that fails:

1. **JSON syntax.** `Not valid JSON (line <n>, column <m>): ...`
2. **The published JSON Schema**, `aouda-schema.v1.json`, embedded in the tool. This is what finds a **misspelt member** such as `primaryKay`,
   which the engine's own reader would drop without a word. It reports `Unknown property '<name>' (not in the schema file format)`.
3. **The engine's own read of the file**, the same one the server makes.
4. **The `--env` overlay merge.** An `--env` with no overlay file is a **warning**, not an error: `environment '<name>' has no overlay file
   (<path>); the base file alone was checked, as the server would read it.` (the server also silently uses the base file).
5. **The apply-time checks that need no tables**: authorization mode and its resolver or column, partition-level security needing a partition
   key, partition and `pkUniqueness` values, column defaults, and the shape and ceilings of named queries and named mutations. They are the same
   functions the apply path calls, not copies of them. `check` uses the **default** named-query ceilings (max 3 joins, max cost 8), not the
   ceilings a particular server is configured with.

Every problem is reported, not only the first of a stage.

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
{ "ok": false, "file": "aouda.schema.json", "problems": [ { "file": "aouda.schema.json", "path": "/tables/orders", "message": "..." } ], "warnings": [] }
```

`path` is a JSON pointer into the document (`/` when the whole file).

## What it cannot see

Everything that needs the tables to exist is still refused at **apply** time, not by `check`: references between tables and columns; key,
cluster and partition columns being columns of the table; a named query or mutation naming a missing column; a materialized query's source;
and the difference between the file and the live database (a partition-key change, a column dropped from a table).

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

## See also

- [Schema CI/CD](schema-cicd.md) and [Schema management](schema-management.md).
- [Access-surface diff](access-surface.md) for a gate on widened access.
