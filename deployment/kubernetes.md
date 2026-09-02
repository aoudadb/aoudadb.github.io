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
- Access to `aouda/server` and (optionally) `aouda/studio` images

## Quick Start

Install Aouda cluster with default values:

```bash
helm install aouda ./charts/aouda-cluster --namespace aouda --create-namespace
```

Check resource status:

```bash
kubectl get pods,svc -n aouda
```

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
