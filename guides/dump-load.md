---
title: "Dump and Load"
nav_order: 8
parent: "Guides"
---

# Dump and load

`aouda dump` writes a server's data to a directory in a format that **no data-directory format version
touches**; `aouda load` reads it into a server of this or another version. It is how you keep your data across a release that changes
the data-directory format (see [Upgrading](upgrading.md)), and how you copy databases to a new server.

**A dump is not a backup.** It is one read of the data at one moment: no point in time, no point-in-time restore, no cut across
databases, no branches. To protect data from a failed disk use [backups](backup.md).

## The procedure

1. **Stop the writers.** A database that is written while it is dumped fails the dump (`DUMP_WRITES_DURING_DUMP`): every table is
   read again at the end and its row count and digest compared with what was written.
2. **Dump from the old server**, running its own build, with an operator key. Use the `aouda` of a build that has `dump` (the new one):

   ```bash
   export AOUDA_KEY=<an operator key>
   aouda dump --server http://old-host:5000 --key-env AOUDA_KEY --out /srv/dump-2026-11-21
   # dumped shop.orders: 3 rows
   # note EXPORT_PASSWORDS_OMITTED: 1 principal(s) have a password: a password is a person's own and is never exported. …
   # aouda dump: 1 database(s), 1 table(s), 3 rows written to /srv/dump-2026-11-21.
   ```

   The exit status is 0 only for a complete dump; on any refusal no `dump.json` is written and `load` refuses the directory.
3. **Keep the old data directory** until step 5 has passed.
4. **Start the new build on a new, empty data directory** — with the dump's declaration (`--declaration <dump>/declaration/aouda.json`)
   when a dumped database is linked to an auth database, and with the key root the old server used when it derived keys.
5. **Load**, and verify:

   ```bash
   aouda load --server http://new-host:5000 --key-env AOUDA_KEY --in /srv/dump-2026-11-21
   # created database shop (strict)
   # applied the schema of shop (1 change(s))
   # loaded and verified shop.orders: 3 rows
   ```

   Every table is verified by **row count and an order-independent digest** as it is loaded. Exit 0 means done; **exit 2** means the data
   is loaded and the dump's declaration is left for you to adopt: it prints the step (adopt `<dump>/declaration/aouda.json`, then
   `aouda reload`). **Run `load` again to resume** — a table that is already loaded is skipped (`already loaded shop.orders: 3 rows`).

   A declaration that cannot be planned clean against the target (it prints the findings and `the data is loaded; …`) ends with the plan's
   status — **exit 1**, or 69 / 77 if the plan could not run or its key was refused — after the data is loaded and verified. On a server started with `--dev-admin` that is always so (a development flag may not coexist with a declared credential): pass
   `--no-declaration` there.
6. Tell the people who had a password to **set it again**: passwords are not carried.

## Options

`aouda dump`

| Option | Meaning |
|---|---|
| `-s`, `--server <url>` | The server. Default: `AOUDA_SERVER`, then `AOUDA_URL` |
| `--key-file <file>` / `--key-env <name>` | An operator key, from a file or from an environment variable |
| `-o`, `--out <dir>` | The directory to write: new, or empty (`DUMP_OUT_NOT_EMPTY` otherwise) |
| `--database <name>` | Dump only this database (repeatable). Default: every data database |
| `--tables <db>.<table>,…` | Dump only these tables (repeatable) |
| `--allow-writes` | Finish a dump whose database was written while it was dumped; recorded as `consistent: false` |
| `--json` | Machine-readable output |

`aouda load`

| Option | Meaning |
|---|---|
| `-s`, `--server <url>`, `--key-file`, `--key-env` | As for `dump` |
| `-i`, `--in <dir>` | The directory `aouda dump` wrote |
| `--database <name>`, `--tables <db>.<table>,…` | Load only these (repeatable) |
| `--no-verify` | Skip the re-read of each loaded table (its count and digest) |
| `--mq-timeout <duration>` | How long the materialized queries may take to be `Ready` (default 30 minutes) |
| `--no-declaration` | Do not plan the dump's declaration against the server (it is managed elsewhere) |
| `--json` | Machine-readable output |

Exit statuses — `dump`: 0 complete, 1 refused or failed, 64 misuse, 69 the server unreachable or failing, 77 the key refused.
`load`: the same, and 2 (loaded; the declaration is left to adopt).

## What a dump carries, and what it does not

**Carried**: every data database with its options, its schema (tables, columns, materialized queries), and every table's rows —
tabular tables, **edge tables** and **`Vector` columns**. Materialized queries are created on the target and rebuilt;
`load` waits for them to be `Ready`. The server's declaration is exported beside the data (`declaration/`) with its notes.

**Not carried**:

- **Passwords** (a person's own; `EXPORT_PASSWORDS_OMITTED`), and **branches** (`DUMP_BRANCH_NOT_DUMPED`).
- **Runtime principals and roles** of an auth database are in the exported file but are never adopted by a declaration
  (`EXPORT_RUNTIME_NOT_ADOPTED`): start the new server from the dump's files, or delete the runtime objects and reload.
- **Internal tables**, and the server's own state.
- An **`MdVector`** column's values: its schema only. A **vector index** (IVF centroids) is trained again at the target's flushes, so with more than
  one cell an approximate search can rank differently on the target while the vectors are equal.
- A dump taken from a server **older than this release** refuses its edge tables and vector columns (the route that exports vectors is new).

**Load refusals** that name what to do: `LOAD_TABLE_NOT_EMPTY` (the target table holds rows that are not the dumped ones),
`LOAD_DATABASE_DIFFERS` (the database exists with other options), `LOAD_SCHEMA_DIFFERS` (the target's schema differs and a table the difference
touches has rows), `LOAD_AUTH_DATABASE_MISSING` (a dumped database is linked to an auth database the target does not have: start the target
with the dump's declaration first), `LOAD_VERIFY_FAILED` (a loaded table's count or digest differs — the table is named), `LOAD_MQ_NOT_READY`.
A table with a **server-time or identity column** is loaded with its stamps as dumped: that needs the **server operator's** key
(`LOAD_RESTORE_REQUIRES_OPERATOR`, exit 77, nothing written), and the audit log records `bulk_load_restore`. Tables with a `unique` or `references` column, edge tables and
vector columns are **inserted, not bulk-loaded**, so they are not atomic: if a load of one fails part-way, truncate that table and load again.
Two such tables are refused with `LOAD_TABLE_UNSUPPORTED`, because the insert path would change what they hold: one that also has a server-time or
identity column (refused before the first write; load the others with `--tables`), and one with a write-time computed column (refused when
`load` reaches it, after the tables before it were loaded).

## Memory, time and secrets

- **Memory is bounded and does not grow with the rows**: one export batch and one append body are in flight. In the repository's test
  with real processes, a table of 2 million rows kept the peak resident set of `dump` at about 98 MB and of `load` at about 150 MB (bound: 512 MB).
- **A dump holds secret-class values** — the stored keys' SHA-256 from the declaration export, and every column value. Its files are
  readable by their owner only (`0600`, directories `0700`). Keep it as you keep the server's keys and your backups; Aouda does not encrypt a
  dump ([Backup and restore](backup.md#9-encryption-and-who-can-read-a-backup)).
- No key is ever printed.
