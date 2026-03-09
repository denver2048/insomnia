# INSOMNIA – Local Infrastructure Setup

This guide explains how to deploy a local infrastructure environment for developing and testing the **INSOMNIA**.

The stack includes:

- **Kubernetes cluster (Kind)**
  - 1 control-plane node
  - 3 worker nodes
- **kube-prometheus-stack** for metrics and monitoring
- **Alertmanager rules** for demo
- **Kubernetes MCP Server** to expose Kubernetes operations as MCP tools for AI agents

This environment allows an AI agent to investigate incidents using:

- Kubernetes API
- Pod logs and events
- Prometheus metrics

# Architecture

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

# 1. Prerequisites

Install the following tools:

- docker
- kind
- kubectl
- helm

Example installation on macOS:

```bash
brew install kind kubectl helm
```

To check if all components are installed, run the commands:

```bash
docker --version
kind --version
kubectl version --client
helm version
```

# 2. Create a Kind Cluster (1 control-plane + 3 workers)

Create the cluster configuration file **kind-cluster-config.yaml**:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: sre-agent-lab

nodes:
- role: control-plane

- role: worker
- role: worker
- role: worker

networking:
  disableDefaultCNI: false
```

Create cluster:

```bash
kind create cluster --config kind-cluster-config.yaml
```

Verify nodes:

```bash
kubectl get nodes
```

# 3. Install kube-prometheus-stack

Add the Helm repository:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

Create the monitoring namespace:

```bash
kubectl create namespace monitoring
```

Install the stack:

```bash
helm install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  -n monitoring
```

Verify deployment:

```bash
kubectl get pods -n monitoring
```

The following components should be running:

- Prometheus
- Alertmanager
- Grafana
- kube-state-metrics
- node-exporter

# 4. Install Kubernetes MCP Server

Install MCP server:

```bash
helm upgrade -i -n kubernetes-mcp-server --create-namespace kubernetes-mcp-server oci://ghcr.io/containers/charts/kubernetes-mcp-server --set ingress.host=localhost
```

# 5. Apply alertmanager rules

Create manifest with rules for alertmanager

Examlpe of manifest:
```bash
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: insomnia-imagepull-alert
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:
  - name: insomnia.rules
    rules:
    - alert: KubernetesImagePullBackOff
      expr: kube_pod_container_status_waiting_reason{reason=~"ImagePullBackOff|ErrImagePull"} == 1
      for: 10s
      labels:
        severity: warning
        insomnia: "true"
      annotations:
        summary: "Pod {{$labels.pod}} cannot pull image"
        description: "Container {{$labels.container}} in {{$labels.namespace}}/{{$labels.pod}} is in ImagePullBackOff"
```

Apply these rules in cluster:

```bash
kubectl apply -f alert-rules.yaml
```

# 6. Apply RBAC policies

To ensure the operation of the MCP server, it is necessary to grant it rights via RBAC (in our case, read-only):

```bash
kubectl apply -f rbac.yaml
```