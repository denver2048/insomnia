# INSOMNIA – Infracore (Local Infrastructure Only)

This directory contains the **infracore** setup: **Kind** cluster plus **Flux CD** (Operator + controllers). Monitoring (**kube-prometheus-stack**), **Alertmanager** routing, **PrometheusRule** alerts, and application workloads are deployed by **Flux** from `clusters/kind/` (see repository root `provision.sh`).

## What infracore provisions

- **Kubernetes cluster (Kind)** — 1 control-plane node, 3 worker nodes
- **Flux CD** — Flux Operator + controllers (`flux-system`)

**Not** in this script (handled by Flux under `clusters/kind/monitoring/` and `clusters/kind/releases/`): Prometheus stack, alert rules, AgentGateway, Kagent, Insomnia.

## Full stack (infracore + Flux GitOps for apps)

To provision **everything** (infracore + Flux bootstrap for `clusters/kind`) in one go, run from the **repository root**:

```bash
./provision.sh
```

That script runs infracore (Kind + Flux), applies Flux `GitRepository` + `Kustomization` resources for `clusters/kind` (monitoring stack, alert rules, apps), and optionally loads a local `insomnia:latest` image into Kind (`PROVISION_LOAD_INSOMNIA_IMAGE=1`). Push your branch to `origin` so Flux can reconcile.

## Infracore only

To provision **only** the infrastructure (no Insomnia app), run from this directory:

```bash
./provision.sh
```

Then deploy apps via Flux from the repo root (`./provision.sh` bootstrap) after pushing `clusters/kind` to `origin`, or use legacy `./scripts/provision-ai-system.sh` for manual Helm installs.

## Architecture

```
            +----------------------+
            |      AI Agent        |
            |  (LangGraph / LLM)   |
            +----------+-----------+
                       |
                       | MCP
                       v
            +----------------------+
            | Kubernetes MCP       |
            | Server               |
            +----------+-----------+
                       |
                       v
                 Kubernetes API
                       |
               +-------+--------+
               | Kind Cluster   |
               | 1 master       |
               | 3 workers      |
               +----------------+
```

## 1. Prerequisites

Install:

- docker
- kind
- kubectl
- helm

Example on macOS:

```bash
brew install kind kubectl helm
```

Check versions:

```bash
docker --version
kind --version
kubectl version --client
helm version
```

## 2. Create a Kind cluster (1 control-plane + 3 workers)

Create **kind-cluster-config.yaml** (or use the one in this directory):

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: insomnia-cluster

nodes:
- role: control-plane

- role: worker
- role: worker
- role: worker

networking:
  disableDefaultCNI: false
```

Create the cluster:

```bash
kind create cluster --config kind-cluster-config.yaml
```

Verify:

```bash
kubectl get nodes
```

## 3. Monitoring and alerts (Flux)

**kube-prometheus-stack**, **PrometheusRule** demo alerts, and **AlertmanagerConfig** are defined under `../clusters/kind/monitoring/` and reconciled by Flux after you run the root `./provision.sh` bootstrap and push to `origin`. Verify with:

```bash
kubectl get helmrelease kube-prometheus-stack -n flux-system
kubectl get pods -n monitoring
```

## 4. (Optional) Install Kubernetes MCP Server

```bash
helm upgrade -i -n kubernetes-mcp-server --create-namespace kubernetes-mcp-server \
  oci://ghcr.io/containers/charts/kubernetes-mcp-server \
  --set ingress.host=localhost
```

---

**Alertmanager** webhook and **Prometheus** rules live in `../clusters/kind/monitoring/config/`. **Deploying the Insomnia app** is via Flux `HelmRelease` in `../clusters/kind/releases/`. See the root [README](../README.md).
