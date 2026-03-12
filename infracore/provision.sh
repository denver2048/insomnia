#!/usr/bin/env bash
# INSOMNIA infracore – Local infrastructure only (Kind, kube-prometheus-stack, alert rules).
# Does not deploy the Insomnia app; use the root provision.sh for full stack (infracore + Helm).

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

# --- 1. Prerequisites ---
check_prereqs() {
  log_info "Checking prerequisites..."
  for cmd in docker kind kubectl helm; do
    if ! command -v "$cmd" &>/dev/null; then
      log_error "'$cmd' is not installed. Install with: brew install kind kubectl helm"
      exit 1
    fi
  done
  docker --version
  kind --version
  kubectl version --client --short 2>/dev/null || kubectl version --client
  helm version --short
  log_info "Prerequisites OK"
}

# --- 2. Create Kind cluster ---
create_cluster() {
  local config="kind-cluster-config.yaml"
  if [[ ! -f "$config" ]]; then
    log_error "Missing $config. Create it as described in README.md."
    exit 1
  fi

  local cluster_name
  cluster_name=$(grep -E '^name:' "$config" | head -1 | awk '{print $2}')
  if [[ -z "$cluster_name" ]]; then
    cluster_name="insomnia-cluster"
  fi

  if kind get kubeconfig --name "$cluster_name" &>/dev/null; then
    log_warn "Kind cluster '$cluster_name' already exists. Skipping creation."
    return 0
  fi

  log_info "Creating Kind cluster from $config..."
  kind create cluster --config "$config"
  log_info "Cluster created. Verifying nodes..."
  kubectl get nodes
}

# --- 3. Install kube-prometheus-stack ---
install_prometheus_stack() {
  log_info "Adding Prometheus Helm repo..."
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  helm repo update

  kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

  if helm status kube-prometheus-stack -n monitoring &>/dev/null; then
    log_warn "kube-prometheus-stack already installed in monitoring. Skipping."
    return 0
  fi

  log_info "Installing kube-prometheus-stack..."
  helm install kube-prometheus-stack \
    prometheus-community/kube-prometheus-stack \
    -n monitoring

  log_info "Waiting for monitoring pods to be ready..."
  kubectl wait --for=condition=ready pod -l "release=kube-prometheus-stack" -n monitoring --timeout=300s || true
  kubectl get pods -n monitoring
}

# --- 4. Apply Alertmanager config ---
apply_alertmanager_config() {
  if [[ -f alertmanager-config.yaml ]]; then
    log_info "Applying alertmanager-config.yaml..."
    kubectl apply -f alertmanager-config.yaml
  else
    log_warn "alertmanager-config.yaml not found. Skipping."
  fi
}

# --- 5. Apply Prometheus alert rules ---
apply_alert_rules() {
  if [[ -f alert-rules.yaml ]]; then
    log_info "Applying alert-rules.yaml..."
    kubectl apply -f alert-rules.yaml
  else
    log_warn "alert-rules.yaml not found. Skipping."
  fi
}

# --- Main ---
main() {
  local total_start total_end total_elapsed
  total_start=$(date +%s)
  log_info "Starting INSOMNIA infracore provisioning (Kind + Prometheus stack + alert rules)..."

  run_step "Prerequisites" check_prereqs
  run_step "Create Kind cluster" create_cluster
  run_step "Install kube-prometheus-stack" install_prometheus_stack
  run_step "Apply Alertmanager config" apply_alertmanager_config
  run_step "Apply alert rules" apply_alert_rules

  total_end=$(date +%s)
  total_elapsed=$(( total_end - total_start ))
  log_info "Infracore provisioning complete. Total time: $(format_elapsed $total_elapsed)"
  log_info "To deploy the Insomnia app, run from repo root: ./provision.sh"
}

main "$@"
