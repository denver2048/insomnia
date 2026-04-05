#!/usr/bin/env bash
# Create Kubernetes secret for OPENAI_API_KEY (and optional OPENAI_MODEL) in the insomnia namespace.
# Usage:
#   OPENAI_API_KEY=sk-xxx ./scripts/create-openai-secret.sh
#   OPENAI_API_KEY=sk-xxx OPENAI_MODEL=gpt-4o ./scripts/create-openai-secret.sh
#   kubectl create secret generic insomnia-openai --from-literal=OPENAI_API_KEY=sk-xxx -n insomnia

set -eu

SECRET_NAME="${SECRET_NAME:-insomnia-openai}"
NAMESPACE="${NAMESPACE:-insomnia}"
KEY="${OPENAI_API_KEY:-}"
MODEL="${OPENAI_MODEL:-}"

if [[ -z "$KEY" ]]; then
  echo "Set OPENAI_API_KEY to create the secret, e.g.:"
  echo "  OPENAI_API_KEY=sk-your-key ./scripts/create-openai-secret.sh"
  echo ""
  echo "Or create it manually:"
  echo "  kubectl create secret generic $SECRET_NAME --from-literal=OPENAI_API_KEY=your-key -n $NAMESPACE"
  exit 1
fi

if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
  kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE"
fi

if [[ -n "$MODEL" ]]; then
  kubectl create secret generic "$SECRET_NAME" \
    --from-literal=OPENAI_API_KEY="$KEY" \
    --from-literal=OPENAI_KEY="$KEY" \
    --from-literal=OPENAI_MODEL="$MODEL" \
    -n "$NAMESPACE"
else
  kubectl create secret generic "$SECRET_NAME" \
    --from-literal=OPENAI_API_KEY="$KEY" \
    --from-literal=OPENAI_KEY="$KEY" \
    -n "$NAMESPACE"
fi

echo "Secret $SECRET_NAME created in namespace $NAMESPACE."
echo "Restart the deployment to pick it up: kubectl rollout restart deployment/insomnia -n $NAMESPACE"
