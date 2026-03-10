#!/usr/bin/env bash
# INSOMNIA – Local Infrastructure Auto-Provisioning
# Deploys Kind cluster, kube-prometheus-stack, MCP server, Insomnia app, and configs.

set -euo pipefail

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

# --- 4. Install Kubernetes MCP Server ---
install_mcp_server() {
  if helm status kubernetes-mcp-server -n kubernetes-mcp-server &>/dev/null; then
    log_warn "kubernetes-mcp-server already installed. Skipping."
    return 0
  fi

  log_info "Installing Kubernetes MCP Server..."
  helm upgrade -i -n kubernetes-mcp-server --create-namespace kubernetes-mcp-server \
    oci://ghcr.io/containers/charts/kubernetes-mcp-server \
    --set ingress.host=localhost
}

# --- 5. Apply Alertmanager config ---
apply_alertmanager_config() {
  if [[ -f alertmanager-config.yaml ]]; then
    log_info "Applying alertmanager-config.yaml..."
    kubectl apply -f alertmanager-config.yaml
  else
    log_warn "alertmanager-config.yaml not found. Skipping."
  fi
}

# --- 6. Apply Alertmanager / Prometheus rules ---
apply_alert_rules() {
  if [[ -f alert-rules.yaml ]]; then
    log_info "Applying alert-rules.yaml..."
    kubectl apply -f alert-rules.yaml
  else
    log_warn "alert-rules.yaml not found. Skipping."
  fi
}

# --- 7. Apply Insomnia namespace and app resources ---
apply_namespace() {
  if [[ -f namespace.yaml ]]; then
    log_info "Applying namespace.yaml..."
    kubectl apply -f namespace.yaml
  else
    log_warn "namespace.yaml not found. Skipping."
  fi
}

apply_sa() {
  if [[ -f sa.yaml ]]; then
    log_info "Applying sa.yaml..."
    kubectl apply -f sa.yaml
  else
    log_warn "sa.yaml not found. Skipping."
  fi
}

apply_rbac() {
  if [[ -f rbac.yaml ]]; then
    log_info "Applying rbac.yaml..."
    kubectl apply -f rbac.yaml
  else
    log_warn "rbac.yaml not found. Skipping."
  fi
}

load_insomnia_image() {
  local cluster_name
  cluster_name=$(grep -E '^name:' kind-cluster-config.yaml 2>/dev/null | head -1 | awk '{print $2}')
  [[ -z "$cluster_name" ]] && cluster_name="insomnia-cluster"
  if docker image inspect insomnia:latest &>/dev/null; then
    log_info "Loading insomnia:latest into Kind cluster..."
    kind load docker-image insomnia:latest --name "$cluster_name"
  else
    log_warn "Image insomnia:latest not found. Build it from repo root: docker build -t insomnia:latest ."
  fi
}

apply_deployment() {
  if [[ -f deployment.yaml ]]; then
    log_info "Applying deployment.yaml..."
    kubectl apply -f deployment.yaml
  else
    log_warn "deployment.yaml not found. Skipping."
  fi
}

apply_service() {
  if [[ -f service.yaml ]]; then
    log_info "Applying service.yaml..."
    kubectl apply -f service.yaml
  else
    log_warn "service.yaml not found. Skipping."
  fi
}

# --- Main ---
main() {
  local total_start total_end total_elapsed
  total_start=$(date +%s)
  log_info "Starting INSOMNIA local infrastructure provisioning..."

  run_step "Prerequisites" check_prereqs
  run_step "Create Kind cluster" create_cluster
  run_step "Install kube-prometheus-stack" install_prometheus_stack
  run_step "Install Kubernetes MCP Server" install_mcp_server
  run_step "Apply Alertmanager config" apply_alertmanager_config
  run_step "Apply alert rules" apply_alert_rules
  run_step "Apply Insomnia namespace" apply_namespace
  run_step "Apply Insomnia ServiceAccount" apply_sa
  run_step "Apply RBAC" apply_rbac
  run_step "Load Insomnia image into Kind" load_insomnia_image
  run_step "Apply Insomnia deployment" apply_deployment
  run_step "Apply Insomnia service" apply_service

  total_end=$(date +%s)
  total_elapsed=$(( total_end - total_start ))
  log_info "Provisioning complete. Total time: $(format_elapsed $total_elapsed)"
}

main "$@"
