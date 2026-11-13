---
title: "Development admin"
nav_order: 2.7
parent: "Guides"
---

# Development admin: `AOUDA_DEV_ADMIN=true` (**BL-1423, 0.12.0**)

**For development and tests only.** A throwaway server needs a first admin, and an agent or a test harness that has to invent a
password, or reuse an old one, ends up with a known credential. `AOUDA_DEV_ADMIN=true` makes the server create the admin and a server key
itself, with random secrets, at every start, and print them once.

Status: shipped in **0.12.0**. Never use it on a shared or production server.

## Turn it on

Any one of these, together with `ASPNETCORE_ENVIRONMENT=Development`:

| Form | Value |
|---|---|
| Environment variable | `AOUDA_DEV_ADMIN=true` |
| Configuration | `Aouda:Auth:DevAdmin:Enabled` = `true` (environment form `AOUDA_AUTH__DEVADMIN__ENABLED=true`) |
| Command line | `aouda start --dev-admin` |

| Setting | Default | Meaning |
|---|---|---|
| `Aouda:Auth:DevAdmin:Enabled` | `false` | The flag. `AOUDA_DEV_ADMIN` accepts only `true` or `false` in any case; an empty value is "unset"; any other value (`1` included) fails the start naming the variable and saying `AOUDA_DEV_ADMIN=true` |
| `Aouda:Auth:DevAdmin:Email` | `admin@aouda.local` | The throwaway admin's email. It must hold an `@` and no whitespace, or the start fails |

```bash
ASPNETCORE_ENVIRONMENT=Development AOUDA_DEV_ADMIN=true aouda start --data-dir "$TMPDIR/aouda-dev"
```

## What it does at every start

- Creates the server auth database and the admin if they are missing, **replaces the admin's password with a new random one** (32 characters)
  and unlocks and activates the user. A kept data directory therefore never holds a password nobody remembers, and the dev admin's
  sessions from the previous run end.
- Leaves setup mode, so `/ready` is `200` once the server has started.
- Declares a new random `mk_srv_` server key as the only bootstrap key, so the previous run's key is revoked as a removed declaration.
- Prints **one line to standard output**, never to a logger, after everything has succeeded:

```text
AOUDA-DEV-ADMIN email=<email> password=<password> server_key=<mk_srv_...>
```

A separate warning goes to the log, with no secret in it. The line is on stdout on purpose: `docker logs` and any log collector that captures
stdout will hold the password and the key. That is acceptable for a throwaway server and is the reason never to use the flag on a shared one.

## What refuses it

The start fails, naming the setting and never a secret, when the flag is set and:

| Condition | First words of the refusal |
|---|---|
| The environment is Production, or unset (Production is the default when `ASPNETCORE_ENVIRONMENT` is not set) | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused in the Production environment, which is also the default when ASPNETCORE_ENVIRONMENT is not set.` |
| `Aouda:Auth:RootUser` has a password (the setting or the `aouda-admin-password` credential) | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused because Aouda:Auth:RootUser has a password` |
| Another server key is declared (`Aouda:Auth:Bootstrap:ServerKey`, `ServerKeyFile`, the `aouda-server-key` credential or a `server_admin` identity) | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused because a server key is already declared` |
| The node is configured with `Aouda:Join` or `Aouda:ReplicaSet` | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused on a node that is configured for replication` |

A node that becomes a follower by some other means is not detected. The key is an ordinary `config`-source server-key row, so reloading
configuration treats it like any other declared key.

## Docker compose

The repository's `docker-compose.yml` runs the container in the Development environment when `AOUDA_DEV_ADMIN` is set:

```bash
AOUDA_DEV_ADMIN=true docker compose up -d
docker compose logs aouda | grep AOUDA-DEV-ADMIN
```

Any non-empty value, `false` included, switches the container's environment to Development; leave the variable **unset** otherwise. It is
refused next to `AOUDA_ROOT_PASSWORD`. See [Docker](../deployment/docker.md#compose).

## `Aouda:Auth:RequireFirstAdmin` is gone

(**BL-1462, next train**) It made a server with no admin, no root password and no dev admin **fail the start** instead of waiting in
setup mode; `docker-compose.yml` set it, so under `restart: unless-stopped` a forgotten password was a restart loop. It is deleted, with
no replacement: setup mode now exists only for a data directory never set up with nothing declared, so a server that declares a server
key needs no admin at all, and a new server that declares nothing waits in setup mode with `/ready` answering `503 setup_required` and naming the ways out. A leftover
`AOUDA_AUTH__REQUIREFIRSTADMIN` is ignored. See [Docker](../deployment/docker.md#setup-mode-only-when-nothing-is-declared).

## See also

- [Authentication setup](../getting-started/auth.md) and [Keys that survive a wipe](keys-that-survive-a-wipe.md) for a real first admin and a real server key.
- [Docker](../deployment/docker.md) for compose and the health check.
