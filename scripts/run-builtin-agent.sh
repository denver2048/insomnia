#!/usr/bin/env bash
# Run a built-in Kagent agent through AgentGateway (Agent -> Gateway -> LLM).
# Prerequisites: ai-system provisioned, kagent CLI installed (brew install kagent), Kagent in cluster.

set -eu

AGENT="${1:-helm-agent}"
PROMPT="${2:-What Helm charts are in my cluster?}"
NAMESPACE="${KAGENT_NAMESPACE:-ai-system}"

echo "Invoking agent: $AGENT with prompt: $PROMPT (namespace: $NAMESPACE)"
echo "Ensure Google AI secret exists in agentgateway-system and gateway is reachable from Kagent pods."
kagent invoke --agent "$AGENT" -t "$PROMPT" -n "$NAMESPACE"
