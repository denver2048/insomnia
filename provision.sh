#!/usr/bin/env bash
# INSOMNIA – Full local stack provisioning
# 1. Infracore: Kind cluster, kube-prometheus-stack, Alertmanager config, alert rules
# 2. Insomnia app: build image, load into Kind, install via Helm
# 3. ai-system: Gateway API, AgentGateway, Kagent, LLM backend (set OPENAI_API_KEY for secrets)

set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRACORE_DIR="$REPO_ROOT/infracore"
CHARTS_DIR="$REPO_ROOT/charts/insomnia"
AI_SYSTEM_SCRIPT="$REPO_ROOT/scripts/provision-ai-system.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

format_elapsed() {
  local s=$1
  if (( s >= 60 )); then
    printf "%dm %ds" $(( s / 60 )) $(( s % 60 ))
  else
    printf "%ds" "$s"
  fi
}

run_step() {
  local name="$1"
  local start end elapsed
  start=$(date +%s)
  log_info "--- $name ---"
  "$2"
  end=$(date +%s)
  elapsed=$(( end - start ))
  log_info "--- $name completed in $(format_elapsed $elapsed) ---"
}

# --- Infracore: Kind + Prometheus stack + alert rules ---
run_infracore() {
  if [[ ! -x "$INFRACORE_DIR/provision.sh" ]]; then
    log_error "Infracore script not found or not executable: $INFRACORE_DIR/provision.sh"
    exit 1
  fi
  log_info "Running infracore provisioning..."
  (cd "$INFRACORE_DIR" && ./provision.sh)
}

# --- Resolve Kind cluster name from infracore config ---
get_cluster_name() {
  local config="$INFRACORE_DIR/kind-cluster-config.yaml"
  if [[ -f "$config" ]]; then
    grep -E '^name:' "$config" | head -1 | awk '{print $2}' || echo "insomnia-cluster"
  else
    echo "insomnia-cluster"
  fi
}

# --- Build Insomnia Docker image ---
build_insomnia_image() {
  if ! docker image inspect insomnia:latest &>/dev/null; then
    log_info "Building insomnia:latest from $REPO_ROOT..."
    docker build -t insomnia:latest "$REPO_ROOT"
  else
    log_warn "Image insomnia:latest already exists. Rebuild with: docker build -t insomnia:latest $REPO_ROOT"
  fi
}

# --- Load Insomnia image into Kind ---
load_insomnia_image() {
  local cluster_name
  cluster_name=$(get_cluster_name)
  if docker image inspect insomnia:latest &>/dev/null; then
    log_info "Loading insomnia:latest into Kind cluster '$cluster_name'..."
    kind load docker-image insomnia:latest --name "$cluster_name"
  else
    log_error "Image insomnia:latest not found. Build it first (see build_insomnia_image)."
    exit 1
  fi
}

# --- Helm install Insomnia chart ---
helm_install_insomnia() {
  if [[ ! -d "$CHARTS_DIR" ]] || { [[ ! -f "$CHARTS_DIR/Chart.yaml" ]] && [[ ! -f "$CHARTS_DIR/chart.yaml" ]]; }; then
    log_error "Insomnia Helm chart not found at $CHARTS_DIR"
    exit 1
  fi

  kubectl create namespace insomnia --dry-run=client -o yaml | kubectl apply -f -

  if helm status insomnia -n insomnia &>/dev/null; then
    log_warn "Insomnia release already installed in namespace insomnia. Upgrading..."
    helm upgrade insomnia "$CHARTS_DIR" -n insomnia
  else
    log_info "Installing Insomnia via Helm..."
    helm install insomnia "$CHARTS_DIR" -n insomnia
  fi

  log_info "Waiting for Insomnia pods to be ready..."
  kubectl wait --for=condition=ready pod -l app=insomnia -n insomnia --timeout=120s || true
  kubectl get pods -n insomnia
}

# --- Provision ai-system (AgentGateway, Kagent with no built-in agents, LLM backend) ---
run_ai_system() {
  if [[ ! -x "$AI_SYSTEM_SCRIPT" ]]; then
    log_warn "ai-system script not found or not executable: $AI_SYSTEM_SCRIPT. Skipping."
    return 0
  fi
  log_info "Running ai-system provisioning (Gateway API, AgentGateway, Kagent, OpenAI backend)..."
  "$AI_SYSTEM_SCRIPT"
}

# --- Point Insomnia at AgentGateway so Insomnia is the agent using the LLM ---
configure_insomnia_for_gateway() {
  if ! helm status insomnia -n insomnia &>/dev/null; then
    return 0
  fi
  local gateway_url="http://agentgateway-proxy.agentgateway-system.svc.cluster.local/v1"
  log_info "Configuring Insomnia to use AgentGateway as LLM endpoint (Insomnia = agent)..."
  helm upgrade insomnia "$CHARTS_DIR" -n insomnia --set "openai.baseUrl=$gateway_url"
  kubectl rollout restart deployment/insomnia -n insomnia
}

# --- Create OpenAI secret from OPENAI_API_KEY env (optional) ---
create_openai_secret() {
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    log_warn "OPENAI_API_KEY not set. Skipping OpenAI secret; set it to enable LLM analysis."
    return 0
  fi
  log_info "Creating OpenAI secret from OPENAI_API_KEY..."
  export OPENAI_API_KEY
  export OPENAI_MODEL="${OPENAI_MODEL:-}"
  if [[ -x "$REPO_ROOT/scripts/create-openai-secret.sh" ]]; then
    "$REPO_ROOT/scripts/create-openai-secret.sh"
    kubectl rollout restart deployment/insomnia -n insomnia
  else
    kubectl create secret generic insomnia-openai \
      --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
      -n insomnia --dry-run=client -o yaml | kubectl apply -f -
    if [[ -n "${OPENAI_MODEL:-}" ]]; then
      kubectl patch secret insomnia-openai -n insomnia -p "{\"stringData\":{\"OPENAI_MODEL\":\"$OPENAI_MODEL\"}}"
    fi
    log_info "Restarting Insomnia deployment to pick up secret..."
    kubectl rollout restart deployment/insomnia -n insomnia
  fi
}

# --- Main ---
main() {
  local total_start total_end total_elapsed
  total_start=$(date +%s)
  log_info "Starting INSOMNIA full stack provisioning (infracore + Helm)..."

  run_step "Infracore (Kind, Prometheus stack, alert rules)" run_infracore
  run_step "Build Insomnia image" build_insomnia_image
  run_step "Load Insomnia image into Kind" load_insomnia_image
  run_step "Helm install Insomnia" helm_install_insomnia
  run_step "Create OpenAI secret (if OPENAI_API_KEY set)" create_openai_secret
  run_step "ai-system (Gateway API, AgentGateway, Kagent, LLM backend)" run_ai_system
  run_step "Configure Insomnia to use gateway as agent" configure_insomnia_for_gateway

  total_end=$(date +%s)
  total_elapsed=$(( total_end - total_start ))
  log_info "Provisioning complete. Total time: $(format_elapsed $total_elapsed)"
}

main "$@"
