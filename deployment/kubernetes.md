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

**Declare a server key and there is no setup mode.** The pod starts ready, operated through the key, with no human admin:

```bash
printf 'mk_srv_%s' "$(openssl rand -hex 32)" |
  kubectl create secret generic aouda-server-key -n aouda --from-file=server-key=/dev/stdin
helm upgrade --install aouda ./charts/aouda-cluster --namespace aouda \
  --set auth.serverKeySecret.name=aouda-server-key
```

(`auth.serverKeySecret.key` defaults to `server-key`; the chart passes it as `AOUDA_AUTH__BOOTSTRAP__SERVERKEY`. The key reaches
kubectl on standard input, not on its command line.) ⚠️ With `replicaCount` above 1 every replica gets the key, and each creates
its own server auth database at its first start, before replication assigns it a role: that is aouda **BL-1396** (startup writes on
a replicated node), not handled by this chart yet.

With no key declared, a pod whose volume has never been set up is in setup mode: `/startup` is `200`, `/ready` is `503 setup_required`, and the pod stays NotReady.
Create the first admin over a port-forward, which reaches the pod as loopback:

```bash
kubectl port-forward -n aouda pod/aouda-0 5000:5000 &
printf '{"email":"%s","password":"%s"}' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" |
  curl -s -X POST http://localhost:5000/api/auth/setup -H 'Content-Type: application/json' --data-binary @-
```

The password goes on standard input, never on curl's command line.

`kubectl exec ... aouda create-admin` refuses while the server runs in the pod: the server holds the data directory.

## Declaring databases, keys and schema files (**next train**) {#declaring-databases-keys-and-schema-files}

Before this release the chart could declare nothing beyond `auth.serverKeySecret`: it had no way to add an environment variable, a volume or a mount to the Aouda pods, so the
declarative flow ([Declare a deployment](../guides/declare-a-deployment.md)) did not work on Kubernetes. Five values, all empty by default, change that. They apply to the **data-node
StatefulSet** only (not the witness, not Studio):

| Value | What it is |
|---|---|
| `declaration.config` | An object rendered as JSON into a ConfigMap named `<fullname>-declaration` and mounted **read-only at `/etc/aouda`** as a directory, so the server reads `/etc/aouda/aouda.json` with no setting. Empty = no ConfigMap and no mount. Its shape is `appsettings.json`: a top-level `Aouda` object |
| `declaration.restartOnChange` | Default `false`. `true` adds a checksum annotation to the pod template, so a changed `declaration.config` **rolls the pods** instead of waiting for a reload |
| `extraEnv` | Container `env` entries (`name` / `value`, or `valueFrom`: a value from a Secret through `secretKeyRef`) |
| `extraEnvFrom` | Container `envFrom` entries (a ConfigMap or Secret whose keys become variables) |
| `extraVolumes`, `extraVolumeMounts` | Pod volumes and container volume mounts: the Secret or ConfigMap that holds the identities file, the schema files and the key files |

```yaml
declaration:
  restartOnChange: false
  config:
    Aouda:
      Auth: { Keys: { File: /etc/aouda-files/identities.json } }
      Databases:
        orders: { SchemaFile: /etc/aouda-files/orders.schema.json }
extraVolumes:
  - name: declaration-files
    secret: { secretName: aouda-declaration }
extraVolumeMounts:
  - name: declaration-files
    mountPath: /etc/aouda-files
    readOnly: true
```

Create the Secret from the files (the key files go in it too, and the identities file names them by their mounted path):

```bash
kubectl create secret generic aouda-declaration -n aouda \
  --from-file=identities.json --from-file=orders.schema.json \
  --from-file=orders_service_key --from-file=feeder_key
```

Rules that follow from how the chart mounts things:

- **Mount your other files somewhere other than `/etc/aouda`.** When `declaration.config` is set, that directory is the ConfigMap's; anything else mounted there conflicts. The example uses `/etc/aouda-files`.
- **Never put a secret in `declaration.config`.** It is a ConfigMap, readable by anything that can read ConfigMaps in the namespace. A key, a password or a hash-less secret goes in a Secret mounted through `extraVolumes`, and the identities file names it as `{ "file": "/etc/aouda-files/feeder_key" }`; or pass a value through `extraEnv` with `valueFrom.secretKeyRef`.
- **The directory is mounted, not one file (no `subPath`)**, deliberately: a `subPath` mount never sees a ConfigMap update, so a reload could not either.
- **After `helm upgrade` the ConfigMap reaches the running pods in about a minute** (the kubelet's sync), and nothing watches it: run `aouda reload` once it has arrived (`kubectl exec -n aouda aouda-0 -- aouda reload --server http://localhost:5000 --key-file /etc/aouda-files/server_key`, with the server key in the mounted Secret). With `restartOnChange: true` the pods roll instead; a changed Secret never rolls them by itself.
- A setting that needs a restart (the port, memory) is reported by the reload as `restartRequired`: [the table](../guides/server-configuration.md#reload-or-restart).
- Declaring `Aouda:Databases` through `extraEnv` works, but a database declared there is **fixed for the life of the pod**: a reload reports `SOURCE_NOT_RELOADABLE` and `aouda plan` says `SOURCE_FIXED_AT_START` (info). Declare them in `declaration.config`.
- The server key still comes from `auth.serverKeySecret` (or a `server_admin` entry in the identities file); see the first-start section above.

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
