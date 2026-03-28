#!/usr/bin/env bash
# INSOMNIA infracore – Core cluster only: Kind + Flux CD (Operator + controllers).
# Monitoring (kube-prometheus-stack), alert rules, and apps are deployed via Flux (clusters/kind/).

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

# --- 3. Install Flux (Operator + Instance / controllers) ---
install_flux() {
  log_info "Installing Flux Operator (OCI Helm chart)..."
  helm upgrade --install flux-operator oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator \
    --namespace flux-system \
    --create-namespace

  log_info "Installing Flux Instance (source, kustomize, helm, notification controllers)..."
  helm upgrade --install flux-instance oci://ghcr.io/controlplaneio-fluxcd/charts/flux-instance \
    --namespace flux-system \
    -f flux-instance-values.yaml

  log_info "Waiting for Flux workloads in flux-system..."
  kubectl wait --for=condition=ready pod --all -n flux-system --timeout=300s 2>/dev/null || true
  kubectl get pods -n flux-system
}

# --- Main ---
main() {
  local total_start total_end total_elapsed
  total_start=$(date +%s)
  log_info "Starting INSOMNIA infracore (Kind + Flux only). Apps and monitoring: Flux clusters/kind/..."

  run_step "Prerequisites" check_prereqs
  run_step "Create Kind cluster" create_cluster
  run_step "Install Flux (Operator + controllers)" install_flux

  total_end=$(date +%s)
  total_elapsed=$(( total_end - total_start ))
  log_info "Infracore provisioning complete. Total time: $(format_elapsed $total_elapsed)"
  log_info "From repo root: ./provision.sh applies Flux GitOps (monitoring + apps from clusters/kind)."
}

main "$@"
