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
| **The .NET 8 ASP.NET Core runtime** | Aouda ships **framework-dependent**: the binaries do not bundle a runtime. ⚠️ Without it the process fails in the .NET host loader — *before any Aouda code runs* — so you get no Aouda error message at all. See [If .NET 8 is missing](#if-net-8-is-missing) |
| **Root** | Writing `/etc/systemd/system` and creating a service account |
| **Access to the private artefact feed** | ⚠️ Aouda's artefacts are **private**. There is no public download, no `curl \| sh`, and no anonymous `docker pull`. See [Getting the artefact](#getting-the-artefact) |

Install the runtime with your distribution's package:

```bash
sudo apt-get install -y aspnetcore-runtime-8.0     # Debian / Ubuntu
sudo dnf install -y aspnetcore-runtime-8.0         # RHEL / Fedora
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

The script does three things and then gets out of the way: it checks for the .NET 8 runtime, verifies the checksums, copies the binaries to `/opt/aouda`, and hands over to `aouda service install`. Everything else — the unit file, the service account, the directories — is done by the server binary itself, where it is one tested code path rather than a shell script per platform.

Any option the script does not recognise is passed through, so these are equivalent:

```bash
sudo ./install-aouda.sh --artifact-dir ./linux-x64 --port 5433 --memory-max 70%
sudo /opt/aouda/Aouda.Server service install --port 5433 --memory-max 70%
```

**See what it will do before it does it:**

```bash
sudo /opt/aouda/Aouda.Server service install --dry-run
```

`--dry-run` prints the exact unit file and changes nothing.

### Options worth knowing

| Option | Default | When to change it |
|---|---|---|
| `--data-path` | `/var/lib/aouda` | Put the data on the volume with the disk |
| `--port` | `5433` | — |
| `--bind` | `127.0.0.1` | ⚠️ Only with a reverse proxy in front — see [Exposure](#exposure) |
| `--memory-max` | `80%` | ⚠️ Read [The memory limit](#the-memory-limit-and-why-it-does-more-than-you-think) first |
| `--cpu-cores` | unset | Set it when the host is **shared** |
| `--max-open-files` | `65535` | Rarely |
| `--admin-password-credential` | unset | A file holding the admin password; the unit gets a systemd `LoadCredential=` naming it |

---

## The unit file

`aouda service install` writes `/etc/systemd/system/aouda.service`. This is its real output, including its comments — every directive in it exists because something went wrong without it:

```ini
[Unit]
Description=Aouda Server
Documentation=https://github.com/aoudadb/aouda
# `network-online.target`, not `network.target`: the latter only means the network stack
# has been configured, not that an address is bound.
After=network-online.target
Wants=network-online.target

[Service]
# `Type=notify`, not `Type=simple`. With `simple`, `systemctl start` returns as soon as
# the process is forked — which on a large database is *before WAL recovery*, so an
# operator or an orchestrator believes the node is up while it is still replaying.
Type=notify
NotifyAccess=all
WorkingDirectory=/opt/aouda
ExecStart=/opt/aouda/Aouda.Server start --data-path /var/lib/aouda --port 5433 --bind 127.0.0.1
User=aouda
Group=aouda

# `on-failure`, not `always`. `always` restarts a process that exited zero because an
# operator stopped it, and turns a fail-fast configuration error into a crash loop that
# hides the message telling you which.
Restart=on-failure
RestartSec=5

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

It creates a cgroup v2 boundary, and Aouda sizes its own budget differently depending on whether it finds one:

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

`cgroupBounded=false` means the limit did not take. Or ask:

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

Three supported ways, in order of preference:

```bash
# 1. A file only you can read
sudo install -m 600 /dev/null /etc/aouda/admin-password
sudo sh -c 'printf "%s" "$PASSWORD" > /etc/aouda/admin-password'
sudo /opt/aouda/Aouda.Server create-admin \
  --email admin@example.com --password-file /etc/aouda/admin-password \
  --data /var/lib/aouda

# 2. Standard input — touches no filesystem
printf '%s' "$PASSWORD" | sudo /opt/aouda/Aouda.Server create-admin \
  --email admin@example.com --password-stdin --data /var/lib/aouda
```

⚠️ A file readable by group or other is **refused**, with the mode it found. `chmod 600` it.

**3. A systemd credential**, which is the right answer for a service. Point the installer at the file and the unit gets a `LoadCredential=` naming it:

```bash
sudo /opt/aouda/Aouda.Server service install \
  --admin-password-credential /etc/aouda/admin-password
```

systemd then reads that file as root at unit start and places the value at `$CREDENTIALS_DIRECTORY/aouda-admin-password`, mode `0400`, owned by the service account, on a tmpfs unmounted when the unit stops. **The unit names the credential; it never contains it.**

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
aouda status              # running? where? what budget?
aouda doctor              # what is misconfigured on this machine
```

`aouda status` and `aouda doctor` both take `--output json`:

```bash
aouda doctor --output json
```

`doctor` reports findings with an id, a severity and a remedy — it is meant to be pasted into a support thread. Its exit code is `0` unless something **failed** (warnings alone do not fail it), and `aouda status` exits `70` when the server is not running, which is a different answer from `69`, "I could not tell".

### Logs

Aouda logs to the console, so systemd captures it:

```bash
journalctl -u aouda -f
```

⚠️ **The default log level is `Warning`** for everything except startup narration. If you are looking for a line the documentation says exists and not seeing it, that is why — see [Defaults reference](../guides/defaults-reference.md#logging-defaults).

---

## Uninstall

```bash
sudo /opt/aouda/Aouda.Server service uninstall
```

Stops the service, disables it, removes the unit and reloads systemd. **The data directory is never touched** — removing a database because someone uninstalled a service is not a decision an installer gets to make.

---

## If .NET 8 is missing

The install script checks first and tells you what to run. If you skipped it and started the binary directly, the failure comes from the .NET host loader rather than from Aouda, and looks like:

```
You must install .NET to run this application.
App: /opt/aouda/Aouda.Server
Architecture: x64
Framework: 'Microsoft.AspNetCore.App', version '8.0.0' (x64)
```

⚠️ **There is no Aouda error message for this, and there cannot be.** The binary is framework-dependent, so the loader fails before a single line of Aouda code runs — which is also why the preflight lives in the install script rather than in `aouda doctor`. By the time `doctor` can run, the runtime is present by definition, and what it reports is the version.
