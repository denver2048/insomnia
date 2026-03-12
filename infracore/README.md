# INSOMNIA – Infracore (Local Infrastructure Only)

This directory contains the **infracore** setup for developing and testing **INSOMNIA**: Kind cluster, monitoring stack, and alert configuration. It does **not** deploy the Insomnia app.

## What infracore provisions

- **Kubernetes cluster (Kind)** — 1 control-plane node, 3 worker nodes
- **kube-prometheus-stack** — metrics and monitoring (Prometheus, Alertmanager, Grafana)
- **Alertmanager config** — webhook to Insomnia app (when deployed)
- **Prometheus alert rules** — demo alerts (ImagePullBackOff, PodPending, OOMKilled)

## Full stack (infracore + Insomnia via Helm)

To provision **everything** (infracore + Insomnia app) in one go, run from the **repository root**:

```bash
./provision.sh
```

That script runs infracore first, then builds the Insomnia image, loads it into Kind, and installs the Insomnia app via Helm.

## Infracore only

To provision **only** the infrastructure (no Insomnia app), run from this directory:

```bash
./provision.sh
```

Then deploy Insomnia separately (e.g. from repo root with `./provision.sh`, or manually with Helm as described in the root README).

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

## 3. Install kube-prometheus-stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  -n monitoring
```

Verify:

```bash
kubectl get pods -n monitoring
```

You should see Prometheus, Alertmanager, Grafana, kube-state-metrics, and node-exporter.

## 4. (Optional) Install Kubernetes MCP Server

```bash
helm upgrade -i -n kubernetes-mcp-server --create-namespace kubernetes-mcp-server \
  oci://ghcr.io/containers/charts/kubernetes-mcp-server \
  --set ingress.host=localhost
```

## 5. Apply Alertmanager configuration

```bash
kubectl apply -f alertmanager-config.yaml
```

This configures Alertmanager to send alerts with `insomnia: "true"` to the Insomnia webhook (e.g. `http://insomnia.insomnia.svc:8000/alert` once the app is deployed).

## 6. Apply alert rules

```bash
kubectl apply -f alert-rules.yaml
```

The rules (see `alert-rules.yaml`) define PrometheusRule resources for ImagePullBackOff, PodPending, and OOMKilled with the `insomnia: "true"` label so they are routed to Insomnia.

---

**Deploying the Insomnia app** (namespace, ServiceAccount, RBAC, Deployment, Service) is done from the **repository root** via the root `provision.sh`, which uses the Helm chart under `charts/insomnia`. See the root [README](../README.md) for full-stack and app details.
