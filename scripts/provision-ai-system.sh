#!/usr/bin/env bash
# Legacy / manual: Gateway API CRDs, AgentGateway, Kagent, ai-system chart (same as clusters/kind/releases via Flux).
# Prefer: ./provision.sh (Flux GitOps) and push clusters/kind to origin.
# Run from repo root. Uses namespace insomnia (and agentgateway-system for AgentGateway). Override with NAMESPACE=...
# Prerequisites: kubectl, helm. Optional: kagent CLI for 'kagent invoke' at the end.

set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHARTS_DIR="$REPO_ROOT/charts/ai-system"
AGENTGATEWAY_NAMESPACE="agentgateway-system"
NAMESPACE="${NAMESPACE:-insomnia}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --- 1. Gateway API CRDs ---
install_gateway_api_crds() {
  log_info "Installing Kubernetes Gateway API CRDs (v1.5.0)..."
  kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.0/standard-install.yaml
  if [[ "${AGENTGATEWAY_EXPERIMENTAL:-0}" == "1" ]]; then
    kubectl apply --server-side --force-conflicts -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.0/experimental-install.yaml
  fi
}

# --- 2. AgentGateway CRDs + control plane ---
install_agentgateway() {
  log_info "Installing AgentGateway CRDs..."
  helm upgrade -i --create-namespace \
    --namespace "$AGENTGATEWAY_NAMESPACE" \
    --version v1.0.0-rc.1 agentgateway-crds oci://cr.agentgateway.dev/charts/agentgateway-crds

  log_info "Installing AgentGateway control plane (controller log level: debug for kgateway visibility)..."
  helm upgrade -i agentgateway oci://cr.agentgateway.dev/charts/agentgateway \
    --namespace "$AGENTGATEWAY_NAMESPACE" \
    --version v1.0.0-rc.1 \
    --set controller.image.pullPolicy=Always \
    --set controller.logLevel=debug \
    --set controller.extraEnv.KGW_ENABLE_GATEWAY_API_EXPERIMENTAL_FEATURES=true

  log_info "Waiting for AgentGateway control plane..."
  kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=agentgateway -n "$AGENTGATEWAY_NAMESPACE" --timeout=120s || true
  kubectl get pods -n "$AGENTGATEWAY_NAMESPACE"
}

# --- 3. Kagent CRDs only (required before ai-system chart so ModelConfig kind exists) ---
install_kagent_crds() {
  local kagent_ns="${KAGENT_NAMESPACE:-$NAMESPACE}"
  log_info "Installing Kagent CRDs (required for ai-system ModelConfig)..."
  helm upgrade -i kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
    --namespace "$kagent_ns" \
    --create-namespace
  log_info "Waiting for Kagent CRDs to be established..."
  kubectl wait --for=condition=established crd/modelconfigs.kagent.dev --timeout=60s 2>/dev/null || true
}

# --- 4. ai-system Helm chart (Gateway, Backend, HTTPRoute, ConfigMaps, ModelConfig) ---
install_ai_system_chart() {
  log_info "Installing ai-system chart (Gateway, Backend, HTTPRoute, ConfigMaps)..."
  if [[ ! -d "$CHARTS_DIR" ]] || [[ ! -f "$CHARTS_DIR/Chart.yaml" ]]; then
    log_error "Chart not found at $CHARTS_DIR"
    exit 1
  fi

  helm upgrade -i ai-system "$CHARTS_DIR" \
    --namespace "$NAMESPACE" \
    --create-namespace

  log_info "Waiting for Gateway to get a proxy deployment..."
  sleep 10
  kubectl get gateway -n "$AGENTGATEWAY_NAMESPACE" 2>/dev/null || true
  kubectl get deployment -n "$AGENTGATEWAY_NAMESPACE" 2>/dev/null || true
}

# --- 5. OpenAI API secret (must be created by user) ---
ensure_openai_secret() {
  if kubectl get secret openai-secret -n "$AGENTGATEWAY_NAMESPACE" &>/dev/null; then
    log_info "Secret openai-secret already exists in $AGENTGATEWAY_NAMESPACE."
    return 0
  fi
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    log_info "Creating openai-secret from OPENAI_API_KEY..."
    kubectl create secret generic openai-secret \
      --namespace "$AGENTGATEWAY_NAMESPACE" \
      --from-literal=Authorization="$OPENAI_API_KEY" \
      --dry-run=client -o yaml | kubectl apply -f -
  else
    log_warn "OPENAI_API_KEY not set. Create the secret manually:"
    log_warn "  kubectl create secret generic openai-secret -n $AGENTGATEWAY_NAMESPACE --from-literal=Authorization=YOUR_KEY"
  fi
}

# --- 6. Kagent (Helm in ai-system or kagent namespace; CRDs already installed in step 3) ---
install_kagent() {
  local kagent_ns="${KAGENT_NAMESPACE:-$NAMESPACE}"
  log_info "Installing Kagent in namespace $kagent_ns..."

  if helm status kagent -n "$kagent_ns" &>/dev/null; then
    log_warn "Kagent release already exists. Upgrade with: helm upgrade kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n $kagent_ns ..."
    return 0
  fi

  # Kagent: install with all built-in agents disabled; Insomnia is the agent that uses the gateway.
  log_info "Installing Kagent with built-in agents disabled (Insomnia uses the gateway as agent)..."

  local api_key_val="${OPENAI_API_KEY:-placeholder-replace-with-secret}"
  helm upgrade -i kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
    --namespace "$kagent_ns" \
    --set providers.default=openAI \
    --set "providers.openAI.apiKey=$api_key_val" \
    --set agents.argo-rollouts-agent.enabled=false \
    --set agents.cilium-debug-agent.enabled=false \
    --set agents.cilium-manager-agent.enabled=false \
    --set agents.cilium-policy-agent.enabled=false \
    --set agents.helm-agent.enabled=false \
    --set agents.istio-agent.enabled=false \
    --set agents.k8s-agent.enabled=false \
    --set agents.kgateway-agent.enabled=false \
    --set agents.observability-agent.enabled=false \
    --set agents.promql-agent.enabled=false

  log_info "Waiting for Kagent pods..."
  kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=kagent -n "$kagent_ns" --timeout=120s 2>/dev/null || \
  kubectl wait --for=condition=ready pod -l app=kagent -n "$kagent_ns" --timeout=120s 2>/dev/null || true
  kubectl get pods -n "$kagent_ns"
}

# --- Main ---
main() {
  log_info "Provisioning AI system (Gateway API, AgentGateway, Kagent, LLM backend)..."

  install_gateway_api_crds
  install_agentgateway
  ensure_openai_secret
  install_kagent_crds
  install_ai_system_chart
  install_kagent

  log_info "Done. Next steps:"
  echo "  1. If you did not set OPENAI_API_KEY, create the secret:"
  echo "     kubectl create secret generic openai-secret -n $AGENTGATEWAY_NAMESPACE --from-literal=Authorization=YOUR_OPENAI_API_KEY"
  echo "  2. Insomnia is the agent: root provision.sh configures it to use the gateway (OPENAI_BASE_URL)."
  echo "  3. Port-forward the gateway to test: kubectl port-forward deployment/agentgateway-proxy -n $AGENTGATEWAY_NAMESPACE 8080:80"
  echo "  4. Test LLM: curl -s localhost:8080/v1/chat/completions -H content-type:application/json -d '{\"model\":\"\",\"messages\":[{\"role\":\"user\",\"content\":\"Hi\"}]}' | jq"
  echo "  5. Trigger an alert so Insomnia runs analysis via the gateway (see demo-cases/)."
}

main "$@"
