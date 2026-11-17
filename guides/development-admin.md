---
title: "Development admin"
nav_order: 2.7
parent: "Guides"
---

# Development admin: `AOUDA_DEV_ADMIN=true` (**BL-1423, 0.12.0**)

**For development and tests only.** A throwaway server needs a first admin, and an agent or a test harness that has to invent a
password, or reuse an old one, ends up with a known credential. `AOUDA_DEV_ADMIN=true` makes the server create the admin and its key
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
- Gives the admin the built-in role `admin` and a new random `aouda_` key, named `dev-admin`, after deleting the previous run's key of
  that name, so the previous run's key stops working.
- Prints **one line to standard output**, never to a logger, after everything has succeeded:

```text
AOUDA-DEV-ADMIN email=<email> password=<password> key=<aouda_...>
```

See [Access](../auth/index.md) (**BL-1464, next train**).

A separate warning goes to the log, with no secret in it. The line is on stdout on purpose: `docker logs` and any log collector that captures
stdout will hold the password and the key. That is acceptable for a throwaway server and is the reason never to use the flag on a shared one.

## What refuses it

The start fails, naming the setting and never a secret, when the flag is set and:

| Condition | First words of the refusal |
|---|---|
| The environment is Production, or unset (Production is the default when `ASPNETCORE_ENVIRONMENT` is not set) | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused in the Production environment, which is also the default when ASPNETCORE_ENVIRONMENT is not set.` |
| The declaration file's `server.principals` declares a credential (a password seed, a key, an OIDC trust) — `SERVER_KEY_DEV_ADMIN_CONFLICT` (**BL-1464, next train**) | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused because server.principals declares a credential ('<name>', ...).` |
| The node is configured with `Aouda:Join` or `Aouda:ReplicaSet` | `Aouda:Auth:DevAdmin:Enabled (AOUDA_DEV_ADMIN) is refused on a node that is configured for replication` |

See [Access](../auth/index.md) (**BL-1464, next train**).
`Aouda:Auth:Bootstrap:*` settings and their systemd credentials are not a guard any more: they are refused on their own
(`SETTING_REMOVED`, **BL-1464, next train**). A node that becomes a follower by some other means is not detected. (**BL-1427,
0.14.0**) `Aouda:Auth:DevAdmin` is restart-only: a reload lists a change to it under `restartRequired`.

## Docker compose

The repository's `docker-compose.yml` runs the container in the Development environment when `AOUDA_DEV_ADMIN` is set:

```bash
AOUDA_DEV_ADMIN=true docker compose up -d
docker compose logs aouda | grep AOUDA-DEV-ADMIN
```

Any non-empty value, `false` included, switches the container's environment to Development; leave the variable **unset** otherwise. It is
refused next to a declared server operator's credentials. See [Docker](../deployment/docker.md#compose).

## `Aouda:Auth:RequireFirstAdmin` is gone

(**BL-1462, 0.14.0**) It made a server with no admin, no root password and no dev admin **fail the start** instead of waiting in
setup mode; `docker-compose.yml` set it, so under `restart: unless-stopped` a forgotten password was a restart loop. It is deleted, with
no replacement: setup mode now exists only for a data directory never set up with nothing declared, so a server that declares a
key-only operator (**BL-1464, next train**: in the declaration file's `server.principals`) needs no admin at all, and a new server that declares nothing waits in setup mode with `/ready` answering `503 setup_required` and naming the ways out. A leftover
`AOUDA_AUTH__REQUIREFIRSTADMIN` is ignored. See [Docker](../deployment/docker.md#setup-mode-only-when-nothing-is-declared).

## See also

- [Declared access](declared-access.md) and [Keys that survive a wipe](keys-that-survive-a-wipe.md) for a real first admin and a real operator key.
- [Docker](../deployment/docker.md) for compose and the health check.
