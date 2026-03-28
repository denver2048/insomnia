# ai-system Helm Chart

Deploys **AgentGateway**, **Kagent**, and **LLM backend configuration** (OpenAI) in Kubernetes using the Gateway API. Chart resources run in **`insomnia` by default** (same namespace as the Insomnia app and Kagent), with AgentGateway control plane in `agentgateway-system`. Built-in Kagent agents are disabled in Flux. The **Insomnia `Agent` CR** is **not** in this chart: it lives under **`clusters/kind/releases/agent/`** and is applied by Flux **`insomnia-kagent-agent`** (nested `spec.type` / `spec.declarative` would break Helm strict SSA and a flat spec crashes the kagent controller).

## Architecture

- **Gateway API**: Standard + optional experimental CRDs.
- **AgentGateway**: Control plane in `agentgateway-system`; Gateway resource creates the proxy (Deployment + Service). AgentgatewayBackend + HTTPRoute route traffic to the LLM.
- **LLM Backend**: OpenAI via AgentgatewayBackend (default model: gpt-5.2); API key from a Kubernetes Secret.
- **Kagent**: Installed in `insomnia` with **built-in agents disabled** (Flux Helm values). **Insomnia** uses the gateway for LLM (`openai.baseUrl` on the Insomnia chart). The **`Agent` `insomnia`** is applied by Flux from **`clusters/kind/releases/agent/`**.

## Prerequisites

- Kubernetes cluster (e.g. Kind), `kubectl`, `helm`
- [OpenAI API key](https://platform.openai.com/api-keys)

## Quick start

From the repo root:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=your-openai-api-key

# Run the full provision script (Gateway API CRDs, AgentGateway, ai-system chart, Kagent)
./scripts/provision-ai-system.sh
```

The script:

1. Installs Gateway API CRDs (v1.5.0)
2. Installs AgentGateway CRDs + control plane in `agentgateway-system`
3. Creates the OpenAI secret in `agentgateway-system` if `OPENAI_API_KEY` is set
4. Installs the ai-system Helm chart (Gateway, AgentgatewayBackend, HTTPRoute, ConfigMaps, optional ModelConfig)
5. Installs Kagent (Helm) with base URL pointing at the gateway

## Manual install

### 1. Gateway API CRDs

```bash
kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.0/standard-install.yaml
```

### 2. AgentGateway

```bash
helm upgrade -i --create-namespace -n agentgateway-system --version v1.0.0-rc.1 agentgateway-crds oci://cr.agentgateway.dev/charts/agentgateway-crds
helm upgrade -i agentgateway oci://cr.agentgateway.dev/charts/agentgateway -n agentgateway-system --version v1.0.0-rc.1 \
  --set controller.image.pullPolicy=Always \
  --set controller.extraEnv.KGW_ENABLE_GATEWAY_API_EXPERIMENTAL_FEATURES=true
```

### 3. OpenAI API secret

```bash
kubectl create secret generic openai-secret -n agentgateway-system --from-literal=Authorization=YOUR_OPENAI_API_KEY
```

### 4. ai-system chart (Gateway, Backend, HTTPRoute, ConfigMaps)

```bash
helm upgrade -i ai-system ./charts/ai-system -n insomnia --create-namespace
```

### 5. Kagent (optional, for built-in agents)

```bash
helm upgrade -i kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds -n insomnia --create-namespace
helm upgrade -i kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n insomnia \
  --set providers.default=openAI \
  --set "providers.openAI.apiKey=$OPENAI_API_KEY"
```

## Configuration

| Value | Description |
|-------|-------------|
| `namespace` | Namespace for ai-system resources (default: `insomnia`) |
| `agentgateway.systemNamespace` | AgentGateway control plane namespace (default: `agentgateway-system`) |
| `agentgateway.logging.level` | Proxy log level: `debug`, `info`, `warn`, `error` (default: `debug` for kgateway visibility) |
| `agentgateway.logging.format` | Proxy log format: `json` or `text` (default: `json`) |
| `llm.provider` | LLM provider (e.g. `openai`) |
| `llm.model` | Model name (default: `gpt-5.2`) |
| `llm.secretName` | Secret name for API key in `agentgateway-system` (key: `Authorization`) |
| `kagent.gatewayBaseUrl` | Base URL for agents (OpenAI-compatible) pointing at the gateway |
| `secrets.createOpenAISecret` | If true, chart creates a placeholder secret (replace key manually) |

Secrets must not be hardcoded; use `kubectl create secret` or a secret manager and reference by name.

## Verify

- **Gateway and proxy**: `kubectl get gateway,deployment -n agentgateway-system`
- **Backend and route**: `kubectl get agentgatewaybackend,httproute -n agentgateway-system`
- **Port-forward and test LLM**: `kubectl port-forward deployment/agentgateway-proxy -n agentgateway-system 8080:80` then:
  `curl -s localhost:8080/v1/chat/completions -H content-type:application/json -d '{"model":"","messages":[{"role":"user","content":"Hi"}]}' | jq`
- **Run a built-in agent**: `kagent invoke --agent helm-agent -t "What Helm charts are in my cluster?"` (requires [kagent CLI](https://kagent.dev/docs/kagent/getting-started/quickstart/) and Kagent installed in the cluster)

## References

- [AgentGateway Kubernetes](https://agentgateway.dev/docs/kubernetes/main/)
- [AgentGateway LLM (OpenAI)](https://agentgateway.dev/docs/kubernetes/main/quickstart/llm/)
- [Kagent Quickstart](https://kagent.dev/docs/kagent/getting-started/quickstart/)
- [OpenAI API keys](https://platform.openai.com/api-keys)
