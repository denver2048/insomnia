#!/usr/bin/env bash
# Copy Phoenix PHOENIX_ADMIN_SECRET (bearer-capable) into insomnia namespace as insomnia-phoenix / PHOENIX_API_KEY.
# Use when Phoenix has auth.enableAuth=true and you need OTLP auth without creating a key in the UI first.
# With auth disabled on Phoenix, this secret is optional (Insomnia optional secretKeyRef tolerates missing secret).
#
# Usage: ./scripts/sync-phoenix-api-key.sh
# Requires: kubectl, phoenix-secret in monitoring (default namespaces below).

set -euo pipefail

PHOENIX_NS="${PHOENIX_NAMESPACE:-monitoring}"
INSOMNIA_NS="${INSOMNIA_NAMESPACE:-insomnia}"
SRC_SECRET="${PHOENIX_SECRET_NAME:-phoenix-secret}"
DST_SECRET="${INSOMNIA_PHOENIX_SECRET_NAME:-insomnia-phoenix}"

if ! kubectl get secret "$SRC_SECRET" -n "$PHOENIX_NS" &>/dev/null; then
  echo "Secret $SRC_SECRET not found in $PHOENIX_NS (Flux may not have reconciled Phoenix yet). Re-run after Phoenix is ready." >&2
  exit 0
fi

KEY="$(kubectl get secret "$SRC_SECRET" -n "$PHOENIX_NS" -o jsonpath='{.data.PHOENIX_ADMIN_SECRET}' | base64 -d)"
if [[ -z "$KEY" ]]; then
  echo "PHOENIX_ADMIN_SECRET missing in $SRC_SECRET; cannot sync." >&2
  exit 0
fi

kubectl create namespace "$INSOMNIA_NS" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true

kubectl create secret generic "$DST_SECRET" \
  --namespace "$INSOMNIA_NS" \
  --from-literal=PHOENIX_API_KEY="$KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Applied secret $DST_SECRET in $INSOMNIA_NS (PHOENIX_API_KEY from $SRC_SECRET PHOENIX_ADMIN_SECRET)."
echo "Restart Insomnia if needed: kubectl rollout restart deployment/insomnia -n $INSOMNIA_NS"
