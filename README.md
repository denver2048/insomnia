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
├── provision.sh              # Full stack: infracore + Helm install of Insomnia
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
2. **API** (`api.py`) parses the first alert, reads `namespace` and `pod` from labels, and invokes the agent with initial state `{ "alert": { "namespace", "pod" } }`.
3. **Agent** (`agent.py`) runs the graph:
   - **k8s_investigator** — MCP `pods_get`, `events_list` → `state["k8s_data"]`
   - **log_investigator** — MCP `pods_log` → `state["logs"]`
   - **aggregate** — Builds a single evidence string (scope, k8s_data, logs).
   - **analysis** — If the evidence mentions an image, optionally enriches with ECR auth check, Docker Hub tags, or “other registry”; then calls `llm.analyze(evidence)` and sets `state["report"]`.
4. **LLM** (`agent/llm.py`) uses a fixed system prompt (senior Kubernetes SRE, structured output: Root Cause, Confidence, Evidence, Suggested Fix) and returns the analysis text. The API logs the report and responds `{"status": "processed"}`.

## Configuration

- **Environment** — Copy `insomnia/.env.example` to `insomnia/.env` and set:
  - `OPENAI_API_KEY` — OpenAI API key for the analysis model.
  - `OPENAI_MODEL` — Model name (default `gpt-5.2`).
- **MCP server** — The app expects an MCP server at `http://localhost:8081/sse` (see `mcp_client.py`) exposing tools such as `pods_get`, `events_list`, `pods_log`. The **infracore** RBAC is intended for a Kubernetes MCP server that reads pods, events, and logs.
- **Alertmanager** — Use `infracore/alertmanager-config.yaml` so alerts with `insomnia: "true"` are sent to the Insomnia webhook (e.g. `http://insomnia.insomnia.svc:8000/alert` in-cluster or `http://host.docker.internal:8080/alert` when running locally).

## Provisioning (full stack)

From the **repository root**, provision the full local stack (Kind cluster, kube-prometheus-stack, alert rules, then Insomnia app via Helm):

```bash
./provision.sh
```

This script:

1. Runs **infracore** (`infracore/provision.sh`): Kind cluster, kube-prometheus-stack, Alertmanager config, Prometheus alert rules.
2. Builds the Insomnia Docker image (`insomnia:latest`) and loads it into the Kind cluster.
3. Installs the Insomnia app with **Helm** from `charts/insomnia` into the `insomnia` namespace (Deployment, Service, ServiceAccount, RBAC).

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

## Maintainer

**Denys Verveiko** — [@denver2048](https://github.com/denver2048) (GitHub)
