---
title: "Windows Service"
nav_order: 4
parent: "Deployment"
---

# Deploying Aouda as a Windows Service

Install the server on a Windows host, register it with the Service Control Manager, and know where it differs from Linux — because in one respect that matters, it does.

---

## Before you start

| Requirement | Why |
|---|---|
| **The .NET 8 ASP.NET Core runtime** | Aouda ships **framework-dependent**: the binaries do not bundle a runtime. ⚠️ Without it the process fails in the .NET host loader — *before any Aouda code runs* — so you get no Aouda error message at all. See [If .NET 8 is missing](#if-net-8-is-missing) |
| **An elevated prompt** | Registering a service |
| **Access to the private artefact feed** | ⚠️ Aouda's artefacts are **private**. There is no public download. See [Getting the artefact](#getting-the-artefact) |

```powershell
winget install Microsoft.DotNet.AspNetCore.8
dotnet --list-runtimes | Select-String Microsoft.AspNetCore.App
```

---

## Getting the artefact

Server artefacts are published to the **private** GitHub Releases of `aoudadb/aouda`:

| Platform | Archive |
|---|---|
| x86-64 | `aouda-server-<version>-win-x64.zip` |
| arm64 | `aouda-server-<version>-win-arm64.zip` |

You need a GitHub token with access to that repository:

```powershell
gh release download v<version> --repo aoudadb/aouda --pattern 'aouda-server-*-win-x64.zip'
Expand-Archive aouda-server-*-win-x64.zip -DestinationPath .
```

**Verify it before installing.** Each archive ships a `SHA256SUMS`; the install script checks it for you, and by hand:

```powershell
Get-FileHash .\win-x64\Aouda.Server.exe -Algorithm SHA256
```

---

## Install

From an **elevated** PowerShell prompt:

```powershell
.\scripts\install-aouda.ps1 -ArtifactDir .\win-x64
```

The script checks for the .NET 8 runtime, verifies the checksums, copies the binaries to `C:\Program Files\Aouda`, and hands over to `aouda service install`. Everything else — the service registration itself — is done by the server binary, where it is one tested code path.

Any argument the script does not recognise is passed through:

```powershell
.\scripts\install-aouda.ps1 -ArtifactDir .\win-x64 --port 5433 --data-path 'D:\Aouda\data'
```

**See what it will register before it does:**

```powershell
& 'C:\Program Files\Aouda\Aouda.Server.exe' service install --dry-run
```

which prints the service command line and changes nothing:

```
"C:\Program Files\Aouda\Aouda.Server.exe" start --data-path C:\ProgramData\Aouda\data --port 5433 --bind 127.0.0.1
```

⚠️ **Note the explicit `start`.** Bare options are an error — `aouda` is a CLI, and a CLI that binds a port and creates a data directory when you fumble a flag is a bad CLI. A service registered without the subcommand installs cleanly and then fails to start.

### Options worth knowing

| Option | Default | When to change it |
|---|---|---|
| `--data-path` | `C:\ProgramData\Aouda\data` | Put the data on the volume with the disk |
| `--port` | `5433` | — |
| `--bind` | `127.0.0.1` | ⚠️ Only with a reverse proxy in front — see [Exposure](#exposure) |
| `--name` | `Aouda` | Running more than one instance |

---

## ⚠️ Where Windows differs from Linux: there is no memory limit

On Linux the systemd unit carries `MemoryMax`, which does two things: it caps the process, **and** it creates a cgroup boundary that lets Aouda size its own budget from a grant it was actually given (70 % of the limit) rather than from a guess about the host (40 % of total RAM).

**Windows has no equivalent that Aouda uses.** The nearest thing is a Job Object, and Aouda does not create one. So on Windows:

- there is **no enforced ceiling** on the process;
- Aouda finds no isolation boundary, so it applies the conservative **40 %** fraction.

`aouda service install` says so when it registers the service, rather than leaving you to infer parity from the Linux page.

**On a machine dedicated to Aouda, set the budget explicitly:**

```powershell
[Environment]::SetEnvironmentVariable(
  'AOUDA__MEMORY__MAXTOTALRAMBYTES', '17179869184', 'Machine')   # 16 GiB
```

Then restart the service. Check what it took:

```powershell
aouda doctor
```

The startup log also prints its own derivation — `Memory budget derivation: … cgroupBounded=False …`, which on Windows is always `False`.

### CPU

The same shape: Aouda sizes scan parallelism from the cores it can see. On a dedicated machine that is right. On a shared one, set `AOUDA__CPU__CONFIGUREDCORES`.

---

## The first admin

⚠️ **Aouda does not accept a password on the command line**, on any platform. A command line is recorded by shell history, by process-creation audit events, and by CI logs; none of that can be un-leaked.

```powershell
# A file
$path = 'C:\ProgramData\Aouda\admin-password'
Set-Content -Path $path -Value $env:ADMIN_PASSWORD -NoNewline -Encoding utf8
icacls $path /inheritance:r /grant:r "$env:USERNAME:(R)"

& 'C:\Program Files\Aouda\Aouda.Server.exe' create-admin `
  --email admin@example.com --password-file $path `
  --data 'C:\ProgramData\Aouda\data'

# Or standard input, which touches no filesystem
$env:ADMIN_PASSWORD | & 'C:\Program Files\Aouda\Aouda.Server.exe' create-admin `
  --email admin@example.com --password-stdin `
  --data 'C:\ProgramData\Aouda\data'
```

⚠️ **The file-permission check is Linux and macOS only.** On Windows Aouda cannot inspect the mode the way it can a Unix one, so a loose ACL is **not** refused — set it yourself, as above, and delete the file once the admin exists.

---

## Exposure

**An install binds `127.0.0.1`.** The admin API creates users and issues keys, and a fresh server has exactly one account on it.

```powershell
& 'C:\Program Files\Aouda\Aouda.Server.exe' service install --bind 0.0.0.0
```

prints a warning naming what that reaches. Aouda does not terminate TLS; put IIS, YARP or another reverse proxy in front and read [Behind a reverse proxy](reverse-proxy.md) — without the trusted-proxy configuration, **per-IP rate limits, lockout attribution and audit-log client IPs are all wrong**.

Restrict the port with a firewall rule as well as a proxy:

```powershell
New-NetFirewallRule -DisplayName 'Aouda admin' -Direction Inbound `
  -LocalPort 5433 -Protocol TCP -RemoteAddress 10.0.0.0/8 -Action Allow
```

---

## Day-to-day

```powershell
aouda service status      # or: Get-Service Aouda
aouda service start
aouda service stop
aouda status              # running? where? what budget?
aouda doctor              # what is misconfigured on this machine
```

Both take `--output json`. `doctor`'s findings carry an id, a severity and a remedy, and are meant to be pasted into a support thread.

### Logs

Aouda logs to the console; under the SCM that goes to the service's stdout. ⚠️ **The default log level is `Warning`** for everything except startup narration — see [Defaults reference](../guides/defaults-reference.md#logging-defaults) if a line the docs mention is not appearing.

---

## Uninstall

```powershell
& 'C:\Program Files\Aouda\Aouda.Server.exe' service uninstall
```

Stops and removes the service. **The data directory is never touched.**

---

## If .NET 8 is missing

The install script checks first. If you skipped it, the failure comes from the .NET host loader rather than from Aouda:

```
You must install .NET to run this application.
App: C:\Program Files\Aouda\Aouda.Server.exe
Architecture: x64
Framework: 'Microsoft.AspNetCore.App', version '8.0.0' (x64)
```

⚠️ **There is no Aouda error message for this, and there cannot be** — the binary is framework-dependent, so the loader fails before any Aouda code runs.
