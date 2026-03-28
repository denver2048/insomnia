# ADR-0001: Insomnia project architecture

## Status

Accepted (2025-03-16)

## Context

We need an AI-powered Kubernetes incident analysis service that reacts to Prometheus/Alertmanager alerts, gathers cluster evidence, and produces actionable root-cause reports. The system must integrate with existing observability, support a clear pipeline from alert to analysis, keep cluster access and LLM routing configurable, and work both locally and in-cluster with an optional central LLM gateway.

## Decision

### 1. Alert ingestion and event hub

- **Webhook-driven**: Insomnia runs as a web service. Alertmanager POSTs alerts to `POST /alert` (standard webhook JSON). Alerts are selected by infra rules (e.g. `insomnia: "true"`). No polling.
- **Event hub**: Normalizes payloads (supports `alerts` list or single `alert`), then applies **guardrails** before investigation: required labels (`namespace`, `pod`), optional allow/block lists for `alertname`, and a cooldown so the same `namespace/pod` is not re-investigated within a configurable window (default 300s).
- **Triage (optional)**: A triage step classifies severity and decides whether to run full investigation. Can be disabled via `INSOMNIA_USE_TRIAGE=false`. Supports same-LLM triage or remote ADK triage agent via `INSOMNIA_TRIAGE_AGENT_URL`.

### 2. Investigation pipeline

- **LangGraph state graph**: The agent is implemented as a LangGraph pipeline. Investigators run in sequence (e.g. k8s_investigator → log_investigator → aggregate); evidence is aggregated into a single string; an analysis node calls the LLM and produces a structured report (Root Cause, Confidence, Evidence, Suggested Fix).
- **MCP for cluster evidence**: Cluster data (pod details, events, logs) is obtained via **MCP (Model Context Protocol)**. Insomnia is an MCP client (SSE); it calls tools such as `pods_get`, `events_list`, `pods_log` on an MCP server (default `http://localhost:8081/sse`). Investigators use these tools and write results into graph state (`k8s_data`, `logs`). Cluster access and RBAC stay in the MCP server; the app stays agnostic to how the server talks to the cluster.

### 3. LLM and gateway

- **Insomnia as the agent**: In the full stack, Insomnia is the only application that uses the LLM. Kagent is installed with **all built-in agents disabled** (`agents.*.enabled=false`).
- **Routing**: LLM requests go through **AgentGateway** when deployed. The app uses `OPENAI_BASE_URL` (Helm: `openai.baseUrl`) pointing at the gateway (e.g. `http://agentgateway-proxy.agentgateway-system.svc.cluster.local/v1`). Flow: **Insomnia → Gateway (Gateway API) → AgentgatewayBackend → OpenAI**. Local dev can use direct OpenAI by not setting `openai.baseUrl`.
- **Secrets**: Insomnia uses `openai.existingSecret` (e.g. `insomnia-openai`) for `OPENAI_API_KEY`; the gateway injects its own key for upstream. Root `provision.sh` sets `openai.baseUrl` after the ai-system chart is deployed.

### 4. Deployment and provisioning

- **Infracore**: Kind cluster, kube-prometheus-stack, alert rules, Alertmanager config routing matching alerts to Insomnia.
- **App**: Docker image built from repo root; Helm chart `charts/insomnia` (Deployment, Service, RBAC) in namespace `insomnia`.
- **AI system (optional)**: `charts/ai-system` and `scripts/provision-ai-system.sh` deploy Gateway API, AgentGateway, Kagent (agents disabled), and OpenAI backend; root `provision.sh` then configures Insomnia to use the gateway.

## Consequences

- **Positive**: Single place for architecture decisions; clear flow from alert → guardrails → triage → graph (MCP evidence + LLM analysis); gateway optional; MCP keeps cluster access out of the main app.
- **Negative**: Depends on Alertmanager and (when used) MCP server and gateway; no built-in retry from Insomnia for failed investigations after webhook receipt.
- **Operational**: Alertmanager and optional MCP server must be configured; guardrail and triage env vars allow tuning without code changes; provision order: infracore → app → optional ai-system and gateway wiring.
