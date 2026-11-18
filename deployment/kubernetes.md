---
title: "Kubernetes and Helm"
nav_order: 1
parent: "Deployment"
---

# Kubernetes Helm Deployment Guide

This guide describes how to deploy Aouda to Kubernetes using the official chart at `charts/aouda-cluster/`.

## Prerequisites

- Kubernetes cluster (local or managed)
- Helm 3
- Access to `ghcr.io/aoudadb/aouda-server` and (optionally) `aouda/studio` images

## Quick Start

Install Aouda cluster with default values:

```bash
helm install aouda ./charts/aouda-cluster --namespace aouda --create-namespace
```

Check resource status:

```bash
kubectl get pods,svc -n aouda
```

## Probes and the first start

(**BL-1462, 0.14.0**) The chart's probes follow the [three probe meanings](../reference/http-api.md#the-probes-one-meaning-each):

| Probe | Path | `200` when |
|---|---|---|
| `startupProbe` | `/startup` | The start sequence has finished: databases open, auth, declared schema files, roles, grants and keys. Setup mode included |
| `livenessProbe` | `/health` | Always, while the process answers |
| `readinessProbe` | `/ready` | The pod can serve application traffic; `503` with every reason otherwise |

`probes.startup.failureThreshold` × `probes.startup.periodSeconds` (default 30 × 10 s) must cover WAL recovery **plus** any
start-time schema apply; raise it for a large declared schema. The port is open for the whole start, so the probes see it
(`/startup` 503, `/ready` with `not_initialized`, `server_starting`, `schema_applying` and its `progress`). Before this, `/startup` answered `503` for as long as the pod was in
setup mode, so Kubernetes restarted a pod that had finished starting every five minutes, for ever.

**Declare an operator and there is no setup mode** (**BL-1464, 0.16.0**). The pod starts ready, operated by a key-only
principal of the declaration, with no human admin. Its key is derived from a **key root** that reaches the pod from a Secret, never
from values or a ConfigMap. Create the Secret, the root on standard input rather than on kubectl's command line:

```bash
openssl rand -hex 32 | tr -d '\n' |
  kubectl create secret generic aouda-key-root -n aouda --from-file=key-root=/dev/stdin
```

then pass it through `extraEnv` and declare the operator in `declaration.file`:

```yaml
extraEnv:
  - name: AOUDA_KEY_ROOT
    valueFrom: { secretKeyRef: { name: aouda-key-root, key: key-root } }
declaration:
  file:
    version: 1
    keyRoot: { env: AOUDA_KEY_ROOT }
    server:
      principals:
        ops: { roles: [admin], credentials: { derivedKey: { version: 1 } } }
```

The same root derives `ops`'s key for its client: [Keys that survive a wipe](../guides/keys-that-survive-a-wipe.md). The chart's
`auth.serverKeySecret` is **gone**: the setting it passed, `AOUDA_AUTH__BOOTSTRAP__SERVERKEY`, is refused at start (`SETTING_REMOVED`,
exit status `78`), so a values file that still sets it renders no key, and an `extraEnv` that sets the variable by hand refuses the
pod. ⚠️ With `replicaCount` above 1 every replica gets the declaration and converges its own server auth database at its first start,
before replication assigns it a role: that is aouda **BL-1396** (startup writes on a replicated node), not handled by this chart yet.

With no operator declared, a pod whose volume has never been set up is in setup mode: `/startup` is `200`, `/ready` is `503 setup_required`, and the pod stays NotReady.
Create the first admin over a port-forward, which reaches the pod as loopback:

```bash
kubectl port-forward -n aouda pod/aouda-0 5000:5000 &
printf '{"email":"%s","password":"%s"}' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" |
  curl -s -X POST http://localhost:5000/api/auth/setup -H 'Content-Type: application/json' --data-binary @-
```

The password goes on standard input, never on curl's command line.

Access is a principal's statements. The credential is an `aouda_` key or a session; `GET /api/auth/whoami` names the principal (**BL-1464, 0.16.0**).

## Declaring databases, keys and schema files

The chart value is `declaration.file`: `aouda.json` with no `Aouda` wrapper, mounted read-only and named with `Aouda__Declaration`. `declaration.config` (an `appsettings` shape) is not a value. The worked values, `extraEnv`, `extraEnvFrom`, `extraVolumes` and `extraVolumeMounts` are [below](#declare-the-databases-bl-1463-0160). A key root is a Secret mounted through `extraVolumes` and named from the file as `{ "file": "/etc/aouda-files/key-root" }`. It is never a ConfigMap entry. `Aouda__Databases__*` in `extraEnv` is refused (`SETTING_REMOVED`).

## Upgrade

```bash
helm upgrade aouda ./charts/aouda-cluster --namespace aouda
```

## Uninstall

```bash
helm uninstall aouda --namespace aouda
```

## Common Value Overrides

### Cluster Size and Storage

```bash
helm upgrade --install aouda ./charts/aouda-cluster \
  --namespace aouda --create-namespace \
  --set replicaCount=3 \
  --set persistence.size=50Gi \
  --set persistence.storageClass=fast-ssd
```

### Enable Witness (Arbiter)

```bash
helm upgrade --install aouda ./charts/aouda-cluster \
  --namespace aouda --create-namespace \
  --set witness.enabled=true
```

When enabled, the chart renders:
- witness `Deployment`
- witness `Service` (stable replication DNS)
- witness entry in `AOUDA_REPLICASET__MEMBERS__*` for data nodes

### Enable Studio

```bash
helm upgrade --install aouda ./charts/aouda-cluster \
  --namespace aouda --create-namespace \
  --set studio.enabled=true
```

Optional Studio overrides:

```bash
--set studio.image.tag=latest \
--set studio.service.type=ClusterIP \
--set studio.service.port=3000 \
--set studio.env.defaultServerUrl=http://aouda:5000
```

If `studio.env.defaultServerUrl` is empty, the chart defaults it to:
`http://<release-fullname>:5000`.

### Declare the databases (**BL-1463, 0.16.0**)

`declaration.file` is the declaration, `aouda.json`, as a value. The chart renders it as JSON into a ConfigMap, mounts it read-only
at `/etc/aouda/aouda.json` on the data pods and sets `Aouda__Declaration=/etc/aouda/aouda.json` for you (the server reads no other
path). With the value empty, which is the default, there is no ConfigMap, no mount and no setting: nothing is declared. The object is
the file's own grammar with no `Aouda` wrapper, `version` included:

```yaml
declaration:
  file:
    version: 1
    databases:
      derive_auth: { kind: auth }
      orders:
        kind: data
        authDatabase: derive_auth
        schema: /etc/aouda-files/orders.schema.json
```

renders (`helm template`)

```yaml
  aouda.json: |
    {
      "databases": { "derive_auth": { "kind": "auth" }, "orders": { "authDatabase": "derive_auth", "kind": "data", "schema": "/etc/aouda-files/orders.schema.json" } },
      "version": 1
    }
```

(the chart's output is indented and its members sorted). Mount the schema files it names with `extraVolumes` and
`extraVolumeMounts`, **not** under `/etc/aouda` (that directory is the ConfigMap's), and name them by absolute path. After
`helm upgrade` the ConfigMap changes in the running pods within about a minute and `aouda reload` applies it; nothing watches the
file. `declaration.restartOnChange: true` rolls the pods instead. Never put a secret in `declaration.file`: it is a ConfigMap. The
chart renders one file and no overlay; use one values file per environment. The value was `declaration.config` (an `appsettings`
shape with an `Aouda` wrapper) in an unreleased chart and has no alias: [Declare a server in one file](../guides/declaration.md).

`Aouda__Databases__*` through `extraEnv` is **refused** at start (`SETTING_REMOVED`): declare databases in `declaration.file`.

## Accessing Services

- Aouda API service: `<release-fullname>:5000` (in-cluster)
- Studio service: `<release-fullname>-studio:<studio.service.port>` (when enabled)

For local testing:

```bash
kubectl port-forward svc/aouda-aouda-cluster 5000:5000 -n aouda
kubectl port-forward svc/aouda-aouda-cluster-studio 3000:3000 -n aouda
```

Then browse:
- Aouda liveness: `http://localhost:5000/health` (process alive; not “ready for schema apply”)
- Aouda readiness: `http://localhost:5000/ready`
- Studio: `http://localhost:3000`

Chart probes: `livenessProbe` → `/health`, `readinessProbe` → `/ready`, `startupProbe` → `/startup`. Wait for `GET /api/databases/{name}` `state=Active` before applying schema.

## Chart Validation (No Cluster Required)

Validate chart syntax and render output:

```bash
helm lint charts/aouda-cluster
helm template aouda charts/aouda-cluster
helm template aouda charts/aouda-cluster --set witness.enabled=true --set studio.enabled=true
```

## Troubleshooting Studio Connectivity

- **Namespace mismatch:** verify the release namespace in all commands (`-n <namespace>`). A successful install in another namespace makes service DNS look broken.
- **Service DNS check:** from a pod in the same namespace, test `http://<release-fullname>:5000/health` and `http://<release-fullname>-studio:<port>`.
- **Port-forward target:** ensure port-forward points to the Studio service (`svc/<release-fullname>-studio`) and not the Aouda API service.
- **Default server URL override:** if Studio starts but cannot reach Aouda, set `studio.env.defaultServerUrl` explicitly to the in-cluster service URL used by your release.

## Notes

- `replicaCount=1` runs Aouda in standalone mode (no replica-set env vars).
- Witness is for election quorum and stores no data.
- Ingress/TLS/cert-manager are intentionally out of scope for this chart version. If you add an Ingress or cloud load balancer in front of the Service, configure [trusted proxies](reverse-proxy.md) on Aouda — otherwise per-IP rate limits, lockout attribution, and audit-log client IPs are the proxy's address.
