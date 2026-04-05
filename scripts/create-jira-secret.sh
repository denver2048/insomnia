#!/usr/bin/env bash
# Create Kubernetes secret insomnia-jira for Jira MCP (Helm charts/insomnia jira.existingSecret).
# Usage:
#   export JIRA_BASE_URL=https://your-org.atlassian.net
#   export JIRA_USERNAME=you@example.com
#   export JIRA_API_TOKEN=your-atlassian-api-token
#   ./scripts/create-jira-secret.sh

set -eu

SECRET_NAME="${SECRET_NAME:-insomnia-jira}"
NAMESPACE="${NAMESPACE:-insomnia}"
BASE="${JIRA_BASE_URL:-}"
USER="${JIRA_USERNAME:-}"
TOKEN="${JIRA_API_TOKEN:-}"

if [[ -z "$BASE" || -z "$USER" || -z "$TOKEN" ]]; then
  echo "Set JIRA_BASE_URL, JIRA_USERNAME, and JIRA_API_TOKEN to create the secret, e.g.:"
  echo "  export JIRA_BASE_URL=https://your-org.atlassian.net"
  echo "  export JIRA_USERNAME=you@example.com"
  echo "  export JIRA_API_TOKEN=your-token"
  echo "  ./scripts/create-jira-secret.sh"
  exit 1
fi

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true

kubectl create secret generic "$SECRET_NAME" \
  --from-literal=JIRA_BASE_URL="$BASE" \
  --from-literal=JIRA_USERNAME="$USER" \
  --from-literal=JIRA_API_TOKEN="$TOKEN" \
  -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

echo "Secret $SECRET_NAME created in namespace $NAMESPACE."
echo "Enable Jira MCP in Helm (jira.enabled: true) and restart: kubectl rollout restart deployment/insomnia -n $NAMESPACE"
