# Insomnia

**I**ntelligent **N**ight **O**perations **M**onitoring & **I**nvestigation **A**gent — an AI-powered Kubernetes incident analysis service that consumes Prometheus/Alertmanager alerts, gathers cluster evidence via MCP, and produces root-cause reports using an LLM.

## Overview

Insomnia runs as a web service that receives alert webhooks from Alertmanager. For each alert (e.g. ImagePullBackOff, PodPending, OOMKilled), it:

1. **Collects evidence** — Fetches pod details, events, and logs from the cluster via an MCP (Model Context Protocol) server.
2. **Enriches context** — For image-related issues: checks ECR auth (imagePullSecrets), Docker Hub tag availability, or flags other registries.
3. **Analyzes** — Sends aggregated evidence to an LLM (OpenAI) to produce a structured report: Root Cause, Confidence, Evidence, Suggested Fix.

The pipeline is implemented as a **LangGraph** state graph: investigators run in sequence, evidence is aggregated, then a single analysis node produces the final report.

## Repository structure

```
insomnia/
├── provision.sh              # Infracore + Flux bootstrap (apps from clusters/kind via GitOps)
├── clusters/kind/            # Flux: infra, monitoring (Prometheus stack + rules), app HelmReleases
├── insomnia/                 # Main application
│   ├── main.py               # Entrypoint: startup + uvicorn (FastAPI on :8080)
│   ├── api.py                # FastAPI app; POST /alert webhook handler
│   ├── agent/                 # LangGraph pipeline, analysis, LLM
│   │   ├── llm.py            # OpenAI client + system/user prompts for SRE-style analysis
│   │   ├── graph.py
│   │   ├── commander.py
│   │   └── analysis.py
│   ├── mcp_client.py         # MCP SSE client; list_tools, call(tool_name, args)
│   ├── ecr.py                # ECR image detection + registry extraction
│   ├── ecr_auth.py           # imagePullSecrets check for ECR auth
│   ├── dockerhub.py          # Docker Hub tag listing for a repository
│   ├── investigators/
│   │   ├── k8s.py            # MCP: pods_get, events_list → k8s_data
│   │   └── logs.py          # MCP: pods_log → logs
│   ├── requirements.txt
│   ├── .env.example
│   └── .gitignore
├── charts/insomnia/          # Helm chart for Insomnia (Deployment, Service, RBAC)
│   ├── chart.yaml
│   ├── values.yaml
│   └── templates/
├── charts/ai-system/         # AgentGateway + Kagent + Gateway API + Google AI Studio backend
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── README.md
│   └── templates/           # Gateway, HTTPRoute, AgentgatewayBackend, ConfigMaps, ModelConfig
├── scripts/
│   ├── provision-ai-system.sh   # Legacy manual deploy (prefer Flux clusters/kind)
│   ├── run-builtin-agent.sh     # Run a built-in Kagent agent through the gateway
│   └── create-openai-secret.sh
├── demo-cases/               # Example K8s manifests to trigger alerts
│   ├── OOM.yaml              # OOMKilled (memory limit + memory-hog)
│   ├── Pending.yaml          # Pending (unschedulable resource requests)
│   └── ImagePull-tag.yaml    # ImagePullBackOff (missing image tag)
├── infracore/                # Kind cluster, Prometheus stack, alert rules
│   ├── provision.sh          # Infracore only (no Insomnia app)
│   ├── kind-cluster-config.yaml
│   ├── alert-rules.yaml      # PrometheusRule: ImagePullBackOff, PodPending, OOMKilled
│   ├── alertmanager-config.yaml  # AlertmanagerConfig → webhook to Insomnia
│   └── README.md
└── README.md                 # This file
```

## How it works

1. **Alertmanager** fires alerts that match the Infra rules (e.g. `insomnia: "true"`) and POSTs to `http://<insomnia>/alert` with the standard Alertmanager webhook JSON.
2. **Event hub** receives the webhook, normalizes the payload (supports `alerts` list or single `alert`), then runs **guardrails** before any investigation:
   - Required labels: `namespace` and `pod` must be present.
   - Optional allowlist: only listed `alertname` values are accepted (env `INSOMNIA_GUARDRAIL_ALLOWED_ALERTNAMES`).
   - Optional blocklist: listed `alertname` values are rejected (env `INSOMNIA_GUARDRAIL_BLOCKED_ALERTNAMES`).
   - Rate limit: same `namespace/pod` is not investigated again within a cooldown window (env `INSOMNIA_GUARDRAIL_COOLDOWN_SECONDS`, default 300).
3. **Triage** (optional) — For each alert that passes guardrails, a triage agent classifies severity (low/medium/high/critical) and decides whether to run full investigation. Set `INSOMNIA_USE_TRIAGE=false` to skip triage and investigate all approved alerts.
4. **API** forwards only approved alerts that triage recommends investigating; rejected alerts are logged and returned in the webhook response as `rejected` with reasons.
5. **Agent** runs the graph with initial state `{ "alert": { "namespace", "pod" } }`:
   - **k8s_investigator** — MCP `pods_get`, `events_list` → `state["k8s_data"]`
   - **log_investigator** — MCP `pods_log` → `state["logs"]`
   - **aggregate** — Builds a single evidence string (scope, k8s_data, logs).
   - **analysis** — If the evidence mentions an image, optionally enriches with ECR auth check, Docker Hub tags, or “other registry”; then calls `llm.analyze(evidence)` and sets `state["report"]`.
6. **LLM** (`agent/llm.py`) uses a fixed system prompt (senior Kubernetes SRE, structured output: Root Cause, Confidence, Evidence, Suggested Fix) and returns the analysis text. The API logs the report and responds `{"status": "processed"}`.

## Configuration

- **Environment** — Copy `insomnia/.env.example` to `insomnia/.env` and set:
  - `OPENAI_API_KEY` — OpenAI API key for the analysis model.
  - `OPENAI_MODEL` — Model name (default `gpt-5.2`).
- **MCP server** — The app expects an MCP server at `http://localhost:8081/sse` (see `mcp_client.py`) exposing tools such as `pods_get`, `events_list`, `pods_log`. The **infracore** RBAC is intended for a Kubernetes MCP server that reads pods, events, and logs.
- **Alertmanager** — Use `infracore/alertmanager-config.yaml` so alerts with `insomnia: "true"` are sent to the Insomnia webhook (e.g. `http://insomnia.insomnia.svc:8000/alert` in-cluster or `http://host.docker.internal:8080/alert` when running locally).
- **Guardrails** (event hub) — Optional env: `INSOMNIA_GUARDRAIL_ALLOWED_ALERTNAMES` (comma-separated alert names to allow; empty = all), `INSOMNIA_GUARDRAIL_BLOCKED_ALERTNAMES` (comma-separated to block), `INSOMNIA_GUARDRAIL_COOLDOWN_SECONDS` (default 300) to avoid re-investigating the same pod within that many seconds.
- **Triage agent** — `INSOMNIA_USE_TRIAGE` (default `true`) enables triage. By default triage uses the same OpenAI key as analysis (`OPENAI_API_KEY`). To use a remote **ADK (Bedrock AgentCore) triage agent**, set `INSOMNIA_TRIAGE_AGENT_URL` to the agent’s base URL (e.g. `http://triage-agent:8001`); the main app will POST to `/invocations` with `{"alert": {...}}` and expect `{"severity", "should_investigate", "summary"}`. To run the triage agent as an ADK app locally: `python -m agent.adk_triage` (requires `bedrock-agentcore`); it listens on port 8001 by default (`TRIAGE_AGENT_PORT`).

## Provisioning (full stack)

From the **repository root**, provision the cluster (Kind, Prometheus stack, Flux) and **Flux GitOps** for apps defined under `clusters/kind/`:

```bash
./provision.sh
```

This script:

1. Runs **infracore** (`infracore/provision.sh`): Kind cluster and Flux (Operator + controllers) only.
2. Applies **Flux bootstrap** (`clusters/kind/bootstrap/`): `GitRepository` (from `git remote origin`) and `Kustomization` resources for `clusters/kind/infrastructure`, `clusters/kind/monitoring/stack` (kube-prometheus-stack), `clusters/kind/monitoring/config` (PrometheusRule + AlertmanagerConfig), and `clusters/kind/releases` (AgentGateway, Kagent, `charts/ai-system`, `charts/insomnia`).
3. Optionally builds and loads `insomnia:latest` into Kind when `PROVISION_LOAD_INSOMNIA_IMAGE=1` (needed for a **local** image with `imagePullPolicy: IfNotPresent`).
4. Optionally creates OpenAI secrets when `OPENAI_API_KEY` is set.

**GitOps:** push your branch to `origin` so Flux can pull the same manifests it reconciles. Check `kubectl get kustomization,helmrelease -n flux-system`.

Prerequisites: `docker`, `kind`, `kubectl`, `helm` (e.g. `brew install kind kubectl helm`). See `infracore/README.md` for manual infracore steps.

### OpenAI API key (optional)

To enable LLM root-cause analysis, create a secret with your OpenAI API key in the `insomnia` namespace:

```bash
# From repo root
OPENAI_API_KEY=sk-your-key ./scripts/create-openai-secret.sh
# Optional: set model
OPENAI_API_KEY=sk-your-key OPENAI_MODEL=gpt-4o ./scripts/create-openai-secret.sh
```

Or manually:

```bash
kubectl create secret generic insomnia-openai --from-literal=OPENAI_API_KEY=sk-your-key -n insomnia
kubectl rollout restart deployment/insomnia -n insomnia
```

The Helm chart injects the secret `insomnia-openai` into the deployment via `envFrom` (optional); without it, the app runs with stub analysis.

## Running

From the `insomnia` app directory:

```bash
cd insomnia
pip install -r requirements.txt
# Configure .env and ensure MCP server is running on :8081
python main.py
```

The service listens on `0.0.0.0:8080`. Trigger alerts (e.g. by applying manifests in `demo-cases/`) and ensure Alertmanager is configured to send them to `/alert`.

## Dependencies

- **FastAPI / Uvicorn** — HTTP server and webhook endpoint.
- **LangGraph** — State graph for the investigation pipeline.
- **MCP** — Client for the SSE-based MCP server (cluster data).
- **OpenAI** — Chat completion for root-cause analysis.
- **python-dotenv** — Load `OPENAI_*` from `.env`.
- **requests** — Used by `dockerhub.py` for Docker Hub API.

## Demo cases

| File               | Intent |
|--------------------|--------|
| `demo-cases/OOM.yaml` | Pod OOMKilled (memory limit 64Mi, process allocates until OOM). |
| `demo-cases/Pending.yaml` | Pod stuck Pending (e.g. requests 8 CPU / 8Gi). |
| `demo-cases/ImagePull-tag.yaml` | ImagePullBackOff (tag `nginx:this-tag-does-not-exist`). |

Apply with `kubectl apply -f demo-cases/<file>.yaml`; ensure Prometheus/Alertmanager and Insomnia are running so alerts flow to the agent.

## AI system (AgentGateway + Kagent + LLM)

For a Kubernetes deployment that includes **AgentGateway**, **Kagent**, and an **OpenAI** backend (default model: gpt-5.2) with Gateway API routing, manifests live under **`clusters/kind/releases`** (Flux). **Kagent**, the **ai-system** chart (**`gateway-llm`** `ModelConfig` and gateways), and the **Insomnia** Helm release (`charts/insomnia`) all target namespace **`insomnia`** (where applicable). **All Kagent built-in agents are disabled**; the Insomnia **workload** is the webhook/LLM app deployed by Flux. The Insomnia HelmRelease sets `openai.baseUrl` to the AgentGateway service so LLM traffic flows Insomnia → Gateway → OpenAI.

- **Deploy**: `./provision.sh`, then push to `origin` so Flux reconciles. Optionally `./scripts/provision-ai-system.sh` for a legacy manual install.
- **Chart**: `charts/ai-system/` — Gateway, HTTPRoute, AgentgatewayBackend, ConfigMaps, Kagent ModelConfig (wired by Flux).
- **Flow**: Insomnia → Gateway (Gateway API) → AgentgatewayBackend → OpenAI; API keys in Kubernetes Secrets (`OPENAI_API_KEY` / `./provision.sh` optional step).
- **Kagent**: control plane only (built-in agents off). Alertmanager webhooks hit `insomnia.insomnia.svc` (see demo-cases/).

See [charts/ai-system/README.md](charts/ai-system/README.md) for details and manual install steps.

## Maintainer

**Denys Verveiko** — [@denver2048](https://github.com/denver2048) (GitHub)
