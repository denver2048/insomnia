#!/usr/bin/env bash
# INSOMNIA – Local stack provisioning
# 1. Infracore: Kind cluster + Flux CD only
# 2. Flux GitOps: GitRepository + Kustomizations (clusters/kind) — monitoring, alerts, AgentGateway, Kagent, ai-system, Insomnia
# 3. Optional: GHCR pull secret for private insomnia image (GHCR_TOKEN + GHCR_USERNAME), build/load local image (PROVISION_LOAD_INSOMNIA_IMAGE=1), OpenAI (OPENAI_API_KEY)
#
# GitOps: push commits to origin before expecting Flux to reconcile app manifests.

set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRACORE_DIR="$REPO_ROOT/infracore"
BOOTSTRAP_GIT_REPO="$REPO_ROOT/clusters/kind/bootstrap/git-repository.yaml"
BOOTSTRAP_KUSTOMIZATIONS="$REPO_ROOT/clusters/kind/bootstrap/gitops-kustomizations.yaml"

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

# --- Infracore: Kind + Flux + Prometheus stack + alert rules ---
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

# --- Flux: GitRepository (from git remote) + Kustomizations for clusters/kind ---
apply_flux_bootstrap() {
  if [[ ! -f "$BOOTSTRAP_GIT_REPO" ]] || [[ ! -f "$BOOTSTRAP_KUSTOMIZATIONS" ]]; then
    log_error "Flux bootstrap manifests missing under clusters/kind/bootstrap/"
    exit 1
  fi

  local REPO_URL BRANCH
  REPO_URL=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)
  if [[ -z "$REPO_URL" ]]; then
    log_error "Git remote 'origin' is required. Flux syncs from your published repository."
    exit 1
  fi
  if [[ "$REPO_URL" =~ ^git@github.com: ]]; then
    REPO_URL="https://github.com/${REPO_URL#git@github.com:}"
  fi
  if [[ "$REPO_URL" =~ ^ssh://git@github.com/ ]]; then
    REPO_URL="https://github.com/${REPO_URL#ssh://git@github.com/}"
  fi
  if [[ ! "$REPO_URL" =~ \.git$ ]]; then
    REPO_URL="${REPO_URL}.git"
  fi

  BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
  if [[ "$BRANCH" == "HEAD" ]]; then
    BRANCH=main
  fi

  log_info "Applying Flux GitRepository (url=$REPO_URL branch=$BRANCH)..."
  sed \
    -e "s|REPLACE_GIT_URL|${REPO_URL}|g" \
    -e "s|REPLACE_GIT_BRANCH|${BRANCH}|g" \
    "$BOOTSTRAP_GIT_REPO" | kubectl apply -f -

  log_info "Applying Flux Kustomizations (insomnia-infra, insomnia-releases)..."
  kubectl apply -f "$BOOTSTRAP_KUSTOMIZATIONS"

  log_info "Flux will reconcile clusters/kind from origin once changes are pushed. Check: kubectl get kustomization -n flux-system"
}

# --- GHCR pull secret for private ghcr.io/<owner>/<repo> insomnia image (optional) ---
ensure_ghcr_pull_secret() {
  kubectl create namespace insomnia --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
  if [[ -z "${GHCR_TOKEN:-}" ]]; then
    log_warn "GHCR_TOKEN not set. If the insomnia image on GHCR is private, the pod will ImagePullBackOff until you:"
    log_warn "  export GHCR_TOKEN=<PAT with read:packages>  # optional: GHCR_USERNAME=your-github-username"
    log_warn "  re-run ./provision.sh (this step), or: kubectl create secret docker-registry ghcr-credentials -n insomnia ..."
    log_warn "Or make the GHCR package public: Package settings → Change visibility."
    return 0
  fi
  local user="${GHCR_USERNAME:-}"
  if [[ -z "$user" ]]; then
    user=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null | sed -n 's/.*github\.com[:/]\([^/]*\).*/\1/p' || true)
  fi
  if [[ -z "$user" ]]; then
    log_error "Set GHCR_USERNAME or use a GitHub origin remote so GHCR login username can be inferred."
    exit 1
  fi
  kubectl create secret docker-registry ghcr-credentials \
    --docker-server=ghcr.io \
    --docker-username="$user" \
    --docker-password="$GHCR_TOKEN" \
    -n insomnia \
    --dry-run=client -o yaml | kubectl apply -f -
  log_info "Applied docker-registry secret ghcr-credentials in namespace insomnia."
  if kubectl get deployment insomnia -n insomnia &>/dev/null; then
    kubectl rollout restart deployment/insomnia -n insomnia 2>/dev/null || true
  fi
}

# --- Build and load insomnia:latest into Kind (optional; for local image) ---
build_load_insomnia_image() {
  log_info "Building insomnia:latest from $REPO_ROOT..."
  docker build -t insomnia:latest "$REPO_ROOT"
  local cluster_name
  cluster_name=$(get_cluster_name)
  log_info "Loading insomnia:latest into Kind cluster '$cluster_name'..."
  kind load docker-image insomnia:latest --name "$cluster_name"
  log_warn "Flux HelmRelease may need a reconcile or rollout restart after image load."
}

# --- OpenAI secrets (optional) — same namespaces as Insomnia / AgentGateway ---
create_openai_secrets_if_env_set() {
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    log_warn "OPENAI_API_KEY not set. Skipping secrets; create insomnia-openai and agentgateway-system/openai-secret manually if needed."
    return 0
  fi
  export OPENAI_API_KEY
  export OPENAI_MODEL="${OPENAI_MODEL:-}"
  if [[ -x "$REPO_ROOT/scripts/create-openai-secret.sh" ]]; then
    "$REPO_ROOT/scripts/create-openai-secret.sh"
  else
    kubectl create secret generic insomnia-openai \
      --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
      -n insomnia --dry-run=client -o yaml | kubectl apply -f -
    if [[ -n "${OPENAI_MODEL:-}" ]]; then
      kubectl patch secret insomnia-openai -n insomnia -p "{\"stringData\":{\"OPENAI_MODEL\":\"$OPENAI_MODEL\"}}"
    fi
  fi
  kubectl create secret generic openai-secret \
    --namespace agentgateway-system \
    --from-literal=Authorization="$OPENAI_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -

  if kubectl get deployment insomnia -n insomnia &>/dev/null; then
    kubectl rollout restart deployment/insomnia -n insomnia
  fi
}

# --- Main ---
main() {
  local total_start total_end total_elapsed
  total_start=$(date +%s)
  log_info "Starting INSOMNIA provisioning (infracore + Flux bootstrap + optional secrets)..."

  run_step "Infracore (Kind + Flux only)" run_infracore
  run_step "Flux GitOps bootstrap (GitRepository + Kustomizations)" apply_flux_bootstrap
  run_step "Optional GHCR pull secret (GHCR_TOKEN)" ensure_ghcr_pull_secret

  if [[ "${PROVISION_LOAD_INSOMNIA_IMAGE:-}" == "1" ]]; then
    run_step "Build and load insomnia:latest into Kind" build_load_insomnia_image
  else
    log_warn "Skipping Docker build/kind load. For local insomnia:latest on Kind, set PROVISION_LOAD_INSOMNIA_IMAGE=1 and re-run."
  fi

  run_step "Optional OpenAI secrets (OPENAI_API_KEY)" create_openai_secrets_if_env_set

  total_end=$(date +%s)
  total_elapsed=$(( total_end - total_start ))
  log_info "Provisioning complete. Total time: $(format_elapsed $total_elapsed)"
  log_info "Push commits to origin, then: kubectl get helmrelease,kustomization -n flux-system"
}

main "$@"
