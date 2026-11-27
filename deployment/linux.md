---
title: "Linux (systemd)"
nav_order: 3
parent: "Deployment"
---

# Deploying Aouda on Linux with systemd

Install the server on a Linux VM or bare-metal host, register it with systemd, and end up with a server that is bounded, hardened, and reports honestly when it is ready.

---

## Before you start

| Requirement | Why |
|---|---|
| **The .NET 10 ASP.NET Core runtime** (**BL-739, 0.2.0**; .NET 8 for 0.1.40 and earlier) | Aouda ships **framework-dependent**: the binaries do not bundle a runtime. ⚠️ Without it the process fails in the .NET host loader — *before any Aouda code runs* — so you get no Aouda error message at all. See [If .NET 10 is missing](#if-net-10-is-missing) |
| **Root** | Writing `/etc/systemd/system` and creating a service account |
| **Access to the private artefact feed** | ⚠️ Aouda's artefacts are **private**. There is no public download, no `curl \| sh`, and no anonymous `docker pull`. See [Getting the artefact](#getting-the-artefact) |

Install the runtime with your distribution's package:

```bash
sudo apt-get install -y aspnetcore-runtime-10.0     # Debian / Ubuntu
sudo dnf install -y aspnetcore-runtime-10.0         # RHEL / Fedora
```

Verify:

```bash
dotnet --list-runtimes | grep Microsoft.AspNetCore.App
```

---

## Getting the artefact

Server artefacts are published to the **private** GitHub Releases of `aoudadb/aouda`, one archive per platform:

| Platform | Archive |
|---|---|
| x86-64 | `aouda-server-<version>-linux-x64.tar.gz` |
| arm64 (Graviton, Ampere) | `aouda-server-<version>-linux-arm64.tar.gz` |

You need a GitHub token with access to that repository:

```bash
gh release download v<version> --repo aoudadb/aouda --pattern 'aouda-server-*-linux-x64.tar.gz'
tar -xzf aouda-server-*-linux-x64.tar.gz
```

The server in each archive is precompiled (ReadyToRun) for its platform (**Lead S06, 0.6.0**): it starts and answers its first
queries sooner, and an archive unpacks to ~40 MB instead of ~17. It is still framework-dependent — the .NET 10 runtime must be
installed first ([Before you start](#before-you-start)).

**Verify the download before installing it.** Every archive ships a `SHA256SUMS` covering the files beside it:

```bash
cd linux-x64
sha256sum -c SHA256SUMS
```

---

## Install

```bash
sudo ./install-aouda.sh --artifact-dir ./linux-x64
```

The script does three things and then gets out of the way: it checks for the .NET 10 runtime, verifies the checksums, copies the binaries to `/opt/aouda`, and hands over to `aouda service install`. Everything else — the unit file, the service account, the directories — is done by the server binary itself, where it is one tested code path rather than a shell script per platform.

Any option the script does not recognise is passed through, so these are equivalent:

```bash
sudo ./install-aouda.sh --artifact-dir ./linux-x64 --port 5433 --memory-max 70%
sudo /opt/aouda/Aouda.Server service install --port 5433 --memory-max 70%
```

**See what it will do before it does it:**

```bash
sudo /opt/aouda/Aouda.Server service install --dry-run
```

`--dry-run` changes nothing. It prints the exact unit file on standard output — so
`--dry-run > aouda.service` captures a clean file — and, on standard error, every step the install
would take:

```
getent group aouda >/dev/null || groupadd --system aouda
getent passwd aouda >/dev/null || useradd --system --gid aouda --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --comment 'Aouda server' aouda
mkdir -p -- /var/lib/aouda
chown -R -- aouda:aouda /var/lib/aouda
chmod -- 0750 /var/lib/aouda
mkdir -p -- /var/log/aouda
chown -R -- aouda:aouda /var/log/aouda
chmod -- 0750 /var/log/aouda
write /etc/systemd/system/aouda.service (the content printed above)
systemctl daemon-reload
systemctl enable aouda
systemctl restart aouda
```

The service account and the directories are created by the install, not by you: the account only
if it does not already exist, and the directories owned by it at `0750`. Re-running the install is
safe.

### Options worth knowing

| Option | Default | When to change it |
|---|---|---|
| `--data-path` | `/var/lib/aouda` | Put the data on the volume with the disk |
| `--port` | `5433` | — |
| `--bind` | `127.0.0.1` | ⚠️ Only with a reverse proxy in front — see [Exposure](#exposure) |
| `--memory-max` | `80%` | ⚠️ Read [The memory limit](#the-memory-limit-and-why-it-does-more-than-you-think) first |
| `--cpu-cores` | unset | Set it when the host is **shared** |
| `--max-open-files` | `65535` | Rarely |

`--admin-password-credential` and `--admin-email` are **removed** (**BL-1464, 0.16.0**): the install refuses them as a usage
error (exit status `64`), and the unit gets no `LoadCredential=` line. Declare the first admin in the declaration file and name the
file in the unit (`Environment=Aouda__Declaration=/etc/aouda/aouda.json`) — see [The first admin](#the-first-admin).

---

## The unit file

`aouda service install` writes `/etc/systemd/system/aouda.service`. This is its real output with the long comments shortened — `--dry-run` prints the full text. Every directive in it exists because something went wrong without it:

```ini
[Unit]
Description=Aouda Server
Documentation=https://github.com/aoudadb/aouda
# `network-online.target`, not `network.target`: the latter only means the network stack
# has been configured, not that an address is bound.
After=network-online.target
Wants=network-online.target
# A crash loop ends in a visible `failed` state: at most 5 starts in 300 s.
# `systemctl reset-failed aouda` clears it once the cause is fixed.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
# `Type=notify`, not `Type=simple`. With `simple`, `systemctl start` returns as soon as
# the process is forked — which on a large database is *before WAL recovery*, so an
# operator or an orchestrator believes the node is up while it is still replaying.
Type=notify
NotifyAccess=all

# Readiness is gated on WAL recovery, which takes as long as the log is. systemd's 90 s
# default would kill a recovery that is making progress and restart it from the
# beginning. To bound it, set Aouda:DatabaseOpenTimeout, which fails with a message.
TimeoutStartSec=infinity
# The server's own shutdown budget (Aouda:ShutdownTimeout, 120 s) plus 30 s. If you
# raise Aouda:ShutdownTimeout, raise this with it.
TimeoutStopSec=150
WorkingDirectory=/opt/aouda
ExecStart=/opt/aouda/Aouda.Server start --data-path /var/lib/aouda --port 5433 --bind 127.0.0.1
User=aouda
Group=aouda

# `on-failure`, not `always`. `always` restarts a process that exited zero because an
# operator stopped it, and turns a fail-fast configuration error into a crash loop that
# hides the message telling you which.
Restart=on-failure
RestartSec=10
# 78 is a start refused for its configuration: a restart fails the same way, so the unit
# goes straight to `failed` and the first journal line names the setting.
RestartPreventExitStatus=78

MemoryAccounting=yes
MemoryMax=80%

CPUAccounting=yes

LimitNOFILE=65535

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
ReadWritePaths=/var/lib/aouda
ReadWritePaths=/var/log/aouda

[Install]
WantedBy=multi-user.target
```

⚠️ **`ProtectSystem=strict` makes the whole filesystem read-only except the `ReadWritePaths`.** Those two lines are not decoration — remove them and the server cannot write its own data.

⚠️ **`LimitNOFILE` is not padding either.** Aouda stores a file per column, so descriptors scale with tables × columns × segments. The usual 1024 default is a real ceiling, and reaching it surfaces as IO errors that read like corruption rather than like a limit.

---

## The memory limit, and why it does more than you think

`MemoryMax` is the single most valuable line in the unit, and **not only because it caps memory**.

It creates a cgroup boundary, and Aouda sizes its own budget differently depending on whether it finds one:

| What Aouda finds | Budget it takes |
|---|---|
| A cgroup limit — an explicit grant | **70 %** of the limit |
| No cgroup — it can only see the host's RAM | **40 %** of that |

The fallback is conservative on purpose: a host's total memory says nothing about how much of it Aouda actually owns. So **a VM install with no `MemoryMax` under-uses the machine it was given**, and on a shared host even 40 % is a claim nobody promised.

⚠️ **The fractions compound, and that is intended.** `MemoryMax=80%` of host RAM gives Aouda a governed budget of roughly 70 % of that — about 56 % of the host. Leave headroom for the operating system here, in the unit, rather than inside Aouda's budget.

**Check it took effect.** The startup log prints its own derivation:

```
Memory budget derivation: detected=... available=... source=... cgroupBounded=... governed=...
```

`cgroupBounded=false` means the limit did not take. Aouda reads the limit on its **own** cgroup and every parent up to the root, and takes the tightest — so a limit set on a parent slice counts too. Or ask:

```bash
aouda doctor
```

### CPU

There is deliberately **no `CPUQuota`** by default: on a machine dedicated to Aouda, every core is Aouda's and a quota would only take cores away.

⚠️ **If the host is shared, set one.** Aouda sizes every scan's parallelism from the cores it believes it has, so on a 64-core node a co-tenanted server with no quota will scan 64 ways. A CPU *share* or *weight* is not a limit — it carries no core count, so the kernel exposes no quota and the process still sees the whole node.

```bash
sudo /opt/aouda/Aouda.Server service install --cpu-cores 4     # renders CPUQuota=400%
```

Where a quota is impossible, set `AOUDA__CPU__CONFIGUREDCORES` instead.

---

## The first admin

⚠️ **Aouda does not accept a password on the command line.** On Linux a command line is world-readable at `/proc/<pid>/cmdline` for the life of the process, and it is also kept by shell history, by process-launch audit rules and by CI logs. None of that can be un-leaked.

⚠️ The first operator is created through the **running** server in setup mode, from this host, or declared. The command of 0.15 and earlier
that wrote to a stopped server's data directory is removed (**BL-1464, 0.16.0**). A server that
declares a key-only operator in the declaration file's `server.principals` needs no admin and has no setup mode.

**The data-directory lock and its limits** (**BL-1462, 0.14.0**). The server holds an exclusive `flock` on
`<data>/Server/aouda.lock` while it runs; `aouda table backfill` and a second server on the same directory take the
same lock and refuse. The kernel releases it when the process exits, `kill -9` included, so there is never a stale lock to delete.
It protects a directory on a **local filesystem, between processes on one host**. On a mount without `flock` (some NFS, CIFS and
FUSE mounts answer `ENOLCK` or `EOPNOTSUPP`) .NET treats the failure as success and the lock is silently not held; on NFS mounted
`nolock`, or a CIFS share used from two hosts, it covers one host only; and `DOTNET_SYSTEM_IO_DISABLEFILELOCKING=1` turns it off.
Only a held lock is reported as "in use by another Aouda process"; any other error taking it (a read-only mount, a full disk) is
reported as itself.

Three supported ways, in order of preference:

```bash
# 1. A file only you can read
sudo install -m 600 /dev/null /etc/aouda/admin-password
sudo sh -c 'printf "%s" "$PASSWORD" > /etc/aouda/admin-password'
/opt/aouda/Aouda.Server init --server http://localhost:5000 \
  --admin-email admin@example.com --admin-password-file /etc/aouda/admin-password

# 2. Standard input — touches no filesystem
printf '%s' "$PASSWORD" | /opt/aouda/Aouda.Server init --server http://localhost:5000 \
  --admin-email admin@example.com --admin-password-stdin
```

⚠️ A file readable by group or other is **refused**, with the mode it found. `chmod 600` it.

**3. Declared in the declaration file** (**BL-1464, 0.16.0**), which is the right answer for a service: the server creates
the first admin itself, on its first start. Declare a `server.principals` entry named by the email, holding the role `admin`, with a
password seed read from the file (a relative path is read from the declaration file's directory):

```json
{ "version": 1, "server": { "principals": { "admin@example.com": { "roles": ["admin"],
    "credentials": { "password": { "file": "/etc/aouda/admin-password" } } } } } }
```

Write it to `/etc/aouda/aouda.json` and name it in the unit: `Environment=Aouda__Declaration=/etc/aouda/aouda.json` (`systemctl
edit aouda`), see [Declare the databases](#declare-the-databases-aoudajson-bl-1463-0160). The service account must be able to
read both files (way 1's password file is root's: `sudo chown aouda: /etc/aouda/admin-password`). The seed is applied only when the principal is created, with a forced password change at the first sign-in, and
never again, so once the admin exists the password file is inert — delete it whenever you like. A seed may also be
`{ "env": "<NAME>" }` or `{ "hash": ... }`. With no human admin at all, declare a key-only operator instead: an entry such as `ops`
holding the role `admin` with `"credentials": { "derivedKey": { "version": 1 } }` and the file's `"keyRoot": { "file": ... }`
([Keys that survive a wipe](../guides/keys-that-survive-a-wipe.md)).

The old way is **refused** (**BL-1464, 0.16.0**): `aouda service install --admin-password-credential` / `--admin-email` is a
usage error (exit `64`), and a server whose unit still loads the credential `aouda-admin-password` or `aouda-server-key`, or sets
a removed `Aouda:Auth` operator setting or `Aouda:Auth:Bootstrap:*`, refuses to start with `SETTING_REMOVED` (exit `78`): remove the
`LoadCredential=` or `Environment=` line from the unit and declare as above.

---

## Declare the databases: `aouda.json` (**BL-1463, 0.16.0**)

The databases, their schema files and their roles are one JSON file, `aouda.json`, that you write and **name**: the server reads
the declaration from the path in the process setting `Aouda:Declaration` and from no other (there is no default path, so
`/etc/aouda/aouda.json` is read only when something says so). For a unit, add the variable to the service's environment
(`Environment=Aouda__Declaration=/etc/aouda/aouda.json`, optionally `Environment=AOUDA_ENVIRONMENT=prod` to merge
`/etc/aouda/aouda.prod.json` over it), or pass `--declaration /etc/aouda/aouda.json` to `aouda start`. A file that is named and not
there fails the start with exit status `1` (a volume that is not mounted yet clears when it is, so a supervisor retries); a file
that is there and wrong exits `78`. Check it first with `aouda plan --declaration /etc/aouda/aouda.json`. `Aouda:Databases` is
**no longer read**: one in `appsettings.json` or the environment refuses the start (`SETTING_REMOVED`) and names the member that
replaces it. The file: [Declare a server in one file](../guides/declaration.md).

---

## Exposure

**An install binds `127.0.0.1`.** The admin API creates users and issues keys, and a fresh server has exactly one account on it, so it is not reachable from off the machine until you say so.

To expose it, say so explicitly — and put TLS in front of it:

```bash
sudo /opt/aouda/Aouda.Server service install --bind 0.0.0.0
```

That prints a warning naming what it just made reachable. Aouda does not terminate TLS itself; see [Behind a reverse proxy](reverse-proxy.md), which also covers the trusted-proxy configuration you need or **per-IP rate limits, lockout attribution and audit-log client IPs will all be wrong**.

---

## Day-to-day

```bash
aouda service status      # or: systemctl status aouda
aouda service start
aouda service stop
aouda status              # running? ready? where? what budget?
aouda doctor              # what is misconfigured on this machine
```

`aouda status` finds the server without being told where it is: it reads the installed service's port from the unit, probes `/ready` with a bounded timeout, and reports what it saw. The memory budget needs an admin token on a server with auth enabled (`--token`, or `AOUDA_TOKEN`); without one it says so rather than guessing.

Every command takes `--output json`, and commands with structured output then print one JSON document. Put it before the command name for `schema export` and `generate`, whose own `--output` after the name is a file path:

```bash
aouda doctor --output json
```

`doctor` reports findings with an id, a severity and a remedy — it is meant to be pasted into a support thread. It reads the limits of the cgroup the **server** runs in, not the shell you run it from, and what it cannot establish it reports as unknown rather than as a failure.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | OK |
| `1` | The command failed |
| `64` | Usage error — an unknown command or option, a missing value, an unknown `--output` format |
| `65` | `doctor` found at least one **failed** check (warnings alone do not fail it) |
| `69` | `status`: the server is running but not serving (still recovering, or nothing answered `/ready` within the probe's deadline) |
| `70` | `status`: the server is not running |
| `71` | The service manager (systemd, the SCM) refused an operation or could not be reached. (**BL-1461, 0.14.0**) It was `78` in 0.13.0 and earlier |
| `77` | Not permitted — `service install` or `service uninstall` without root (an elevated prompt on Windows) |
| `78` | (**BL-1461, BL-1463, 0.14.0**) `start`: the start was **refused for its configuration**, and restarting with the same configuration fails the same way. Standard error lists every finding with its code ([Declaration Finding Codes](../reference/plan-codes.md)). See [When the start is refused](#when-the-start-is-refused) |

These are the same on every platform and for every way of running the server (`aouda start`, the unit, the container).

(**BL-1472, next train**) **`aouda start` ends with `0`, `1`, `64` or `78`, and nothing else of its own.** `0` is a stop that was asked for
— a running server's SIGTERM, and a SIGTERM, SIGINT or `systemctl stop` that arrived before the server was ready, whatever the stop
interrupted (the last line is then `START_STOPPED`). `1` is a start that failed for a reason a restart may clear, `78` a start refused for
its configuration. Every failure ends with one line, the last on standard error, naming its code — `aouda start: START_ADDRESS_IN_USE:
… (exit status 1)`; the codes are in the [CLI reference](../reference/cli.md#start). Three statuses come from elsewhere: `70` from a
**running** server that the heap watchdog ended (`Aouda:Memory:TerminateOnHeapExhaustion`, its last log line says so); `143` (SIGTERM)
and `130` (SIGINT) when the signal arrives in the first second, before the host is up, which is the signal's own status. **`134`
(SIGABRT: an unhandled exception, a stack trace, a core dump) is a bug: report it.** Before this release most start failures ended
`134`.
(**BL-1463, 0.14.0**) [`aouda plan`](../guides/plan.md) exits `0` when the start would not refuse the declaration, `1` when it would
(or when a file it names cannot be read), and `64` for misuse; against a running server (`--server`) also `2` (changes), `69` (the
server cannot be reached or did not answer with a plan) and `77` (the key was refused). (**BL-1427, 0.14.0**)
[`aouda reload`](../guides/declared-databases.md#changing-the-declaration-without-a-restart-bl-1427-0140) exits `0` (nothing to change), `2` (applied),
`1` (refused, or stopped part-way), `69` (unreachable, busy, rate-limited or still starting), `77` (the key was refused) and `64` for misuse.

⚠️ **`78` means the configuration itself is wrong**: what it says (invalid content, a duplicate, a reference to something that does not
exist, a refused format), not whether the machine could act on it. A start that fails **while doing** what the configuration asks — a
key file, secret file or schema file that cannot be read (a volume not yet mounted, a permission), a data directory that cannot be
written, a full disk, an engine fault — is not `78`: it fails as any other start, and the unit restarts it. (**BL-1463, 0.14.0**) A
start whose only errors are files that could not be read yet exits `1`.

### When the start is refused

(**BL-1461, BL-1463, 0.14.0**) A start refused for its configuration prints **every** problem it found on **standard error**, each
with its code, the setting or file (and JSON pointer) it is about, and what to do, and exits with status `78` (`EX_CONFIG` in
`sysexits.h`). It checks the whole declaration before it opens anything, so a refused start has created no database. The format is the
one [`aouda plan`](../guides/plan.md) prints, headed `aouda start`, and the last line names the exit status:

```text
aouda start: declaration /etc/aouda/aouda.json, 1 database, 0 schema files

error    SETTING_REMOVED  Aouda:Auth:Bootstrap:ServerKey  (environment variable Aouda__Auth__Bootstrap__ServerKey)
         Aouda:Auth:Bootstrap:ServerKey is no longer read (ADR 0071: principals and their credentials are declared in the declaration file). Remove it and declare the operator in the declaration file (aouda.json): a server.principals entry holding the role admin, with a derivedKey (from the file's keyRoot) or a stored key { "id", "sha256" }.
         fix:  Remove the setting and use the one the message names instead.

stages   read ok, settings 1 error, principals ok, databases ok, bootstrap ok, schema ok, roles ok, principalRows ok
1 error, 0 warnings: the start was refused for its configuration (exit status 78). Restarting with the same configuration fails the same way: fix what is named above, then start again.
```

Every code, its stage and what fixes it is in [Declaration Finding Codes](../reference/plan-codes.md). Among them:
`SETTING_REMOVED` — a setting that is no longer read, such as the old operator settings above (`Aouda:Auth:Bootstrap:*`,
the first-admin and keys-file settings, the systemd credentials `aouda-server-key` and `aouda-admin-password`; **BL-1464, 0.16.0**;
an empty value counts as not set), naming its replacement and never its value; `SERVER_HAS_NO_OPERATOR` — the data
directory was set up before, and now has nobody who can manage the server and nothing declared (declare an operator in the
declaration file's `server.principals`, or `--dev-admin` for development; a data directory that was never set up starts in setup
mode instead, **BL-1462**); `DEV_ADMIN_REFUSED`; `CONFIGURATION_INVALID`; and
`DATA_DIRECTORY_FORMAT_REFUSED` — the data directory was written in another format, see [Upgrading](../guides/upgrading.md).
[`aouda plan`](../guides/plan.md) runs the same checks before you deploy.

The unit names `78` in `RestartPreventExitStatus=`, so a refused start goes to `failed` at once instead of being restarted five times;
`journalctl -u aouda` shows the findings. Fix the setting, then `systemctl reset-failed aouda` and `systemctl start aouda`. Any other
failed start (a port already bound, a file that cannot be read, a disk error) exits `1` with its coded line, and the unit restarts it, up
to five times in 300 s: the holder of a port may exit, a volume may be mounted, a permission may be fixed (**BL-1472, next train**). A
configuration the server cannot build with — a bind that is not an address, a port out of range, a `Logging:LogLevel` value that is not a
level, a list where one value is expected, an OTLP endpoint that is not a URI — is a refusal (`78`) with the code `aouda plan` reports,
and so is a `Server/databases.json` or `Server/pending_jobs.json` that is not what it is (`DATA_DIRECTORY_FILE_INVALID`, **BL-1548, next
train**): a restart cannot clear either. A unit
written by an earlier `aouda service install` lacks the line: re-run the install, or add `RestartPreventExitStatus=78` under
`[Service]` and `systemctl daemon-reload`.

### Upgrading from an install made before `aouda service install`

A unit written by the old `install-aouda.sh` runs `Aouda.Server --data-path … --port …` with no `start`, and the current binary rejects that as a usage error — **so the service fails to start after an in-place binary swap.** Re-run the install, which rewrites the unit (and creates nothing that already exists):

```bash
sudo /opt/aouda/Aouda.Server service install --data-path /var/lib/aouda --port 5433
```

### Logs

Aouda logs to the console, so systemd captures it:

```bash
journalctl -u aouda -f
```

⚠️ **The default log level is `Warning`** for everything except startup narration. If you are looking for a line the documentation says exists and not seeing it, that is why — see [Defaults reference](../guides/defaults-reference.md#logging-defaults).

**JSON lines, for a log collector** (**BL-1978, next train**). The console writes text by default. To write one JSON object per line, which Loki, Elastic, Datadog, Splunk and the cloud agents read, name Aouda's formatter:

```bash
Logging__Console__FormatterName=aouda-json   # an environment variable: a unit's Environment=, a container's -e
aouda start --output json                     # the same for one run; --Logging:Console:FormatterName=aouda-json also works
```

⚠️ **The name is `aouda-json`, not `json`.** `json` is the .NET framework's own formatter and the server leaves it as it is; its lines have no timestamp, and PascalCase names (`LogLevel`, `State`) that no field below matches. A line of Aouda's:

```json
{"timestamp":"2026-11-27T14:02:51.2216466+00:00","level":"Warning","eventId":104,"eventName":"RequestRefused","category":"Aouda.Server.Middleware.RequestLoggingMiddleware","message":"Request refused. Method=GET, Path=/api/databases/nosuchdb, StatusCode=404, Code=DATABASE_NOT_FOUND, RequestId=req-9, CorrelationId=probe123, ElapsedMs=12, Suppressed=0, Endpoint=-","properties":{"method":"GET","path":"/api/databases/nosuchdb","statusCode":404,"code":"DATABASE_NOT_FOUND","requestId":"req-9","correlationId":"probe123","elapsedMs":12,"suppressed":0,"endpoint":"-","serverRole":"Standalone"}}
```

| Field | Holds |
|---|---|
| `timestamp` | When the line was written, ISO 8601, UTC (`Logging:Console:FormatterOptions:UseUtcTimestamp`, `TimestampFormat`) |
| `level` | `Trace`, `Debug`, `Information`, `Warning`, `Error` or `Critical` |
| `eventId`, `eventName` | Present when the line has one (a request's refusal is `104`, `RequestRefused`) |
| `category` | The logger's name: filter on it with `Logging__LogLevel__<category>` |
| `message` | The rendered text |
| `exception`, `exceptionType` | The exception, with any key-shaped text replaced by `<redacted>` |
| `properties` | The named values of the message and of the request it was written in: each key once, `correlationId`, `serverRole` among them |

The formatter's options are under `Logging:Console:FormatterOptions:` (`UseCamelCase`, `IncludeScopes`, `IncludeEventId`, `IncludeException`, `IndentJson`); leave `IndentJson` off for a collector. The default format and the default levels are unchanged: text, and `Warning`.

**A refused request is one line, and the default shows it** (**BL-1978, next train**). A request the server answers with an error that has a code (a `400`, `401`, `403`, `404`, `409`, `429`, `503`) writes `Request refused.` at `Warning`, with the `code`, the `statusCode`, the `requestId` (the caller's `X-Request-Id`, `-` when it sent none), the `correlationId` (the `X-Correlation-ID` the response carries) and the path. A `5xx` other than `503` is written at `Error`. A line is not written for a success, and an answer with no coded body (a route that does not exist) keeps its `Request completed` line at `Information`. A server in a refusal storm does not write a storm: **at most ten lines per code per second** are written at `Warning`, the rest at `Information`, and the next line of the code reports how many lines were left out in `suppressed`; `Logging__LogLevel__Default=Information` brings every line back.

---

## Uninstall

```bash
sudo /opt/aouda/Aouda.Server service uninstall
```

Stops the service, disables it, removes the unit and reloads systemd. **The data directory is never touched** — removing a database because someone uninstalled a service is not a decision an installer gets to make.

---

## If .NET 10 is missing

The install script checks first and tells you what to run. If you skipped it and started the binary directly, the failure comes from the .NET host loader rather than from Aouda, and looks like:

```
You must install .NET to run this application.
App: /opt/aouda/Aouda.Server
Architecture: x64
Framework: 'Microsoft.AspNetCore.App', version '10.0.0' (x64)
```

⚠️ **There is no Aouda error message for this, and there cannot be.** The binary is framework-dependent, so the loader fails before a single line of Aouda code runs — which is also why the preflight lives in the install script rather than in `aouda doctor`. By the time `doctor` can run, the runtime is present by definition, and what it reports is the version.

⚠️ **Upgrading from 0.1.40 or earlier is the case that meets this** (**BL-739, 0.2.0**). Those servers ran on .NET 8, so a machine that has run Aouda for months does not necessarily have .NET 10. Install `aspnetcore-runtime-10.0` *before* replacing the binaries; the two runtimes install side by side, so the running server is not disturbed.
