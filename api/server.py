import logging
import os
import sys

from api.phoenix_otel import init_phoenix_otel

# Phoenix + OpenInference must run before any OpenAI client is constructed (lazy imports included).
init_phoenix_otel()

from fastapi import FastAPI, HTTPException, Request

from agent.commander import investigate
from agent.triage import triage_result_to_dict
from eventhub.hub import process_webhook

logger = logging.getLogger(__name__)
app = FastAPI()


def _triage_enabled() -> bool:
    val = os.getenv("INSOMNIA_USE_TRIAGE", "true").strip().lower()
    return val in ("1", "true", "yes")


@app.on_event("startup")
def _startup():
    """Suppress health/ready probe access logs; ensure app logs go to stdout; check OPENAI_API_KEY."""
    import logging
    from api.log_config import install_access_log_filter
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    install_access_log_filter()
    if not os.getenv("OPENAI_API_KEY", "").strip():
        msg = (
            "ERROR: OPENAI_API_KEY is not set or empty. Create secret 'insomnia-openai' with "
            "OPENAI_API_KEY or set OPENAI_API_KEY in the environment to enable LLM analysis."
        )
        print(msg, file=sys.stderr, flush=True)
    if _triage_enabled():
        logger.info(
            "Triage is enabled. Alerts are classified by severity and only those marked for "
            "investigation run the full pipeline. To use a remote ADK triage agent set "
            "INSOMNIA_TRIAGE_AGENT_URL to the agent base URL (e.g. http://triage-agent:8001)."
        )
    else:
        logger.info(
            "Triage is disabled. All alerts that pass guardrails will be fully investigated. "
            "To enable triage: set INSOMNIA_USE_TRIAGE=true (or omit it; default is true). "
            "Optionally set INSOMNIA_TRIAGE_AGENT_URL to use a remote ADK triage agent."
        )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    # тут пізніше можна додати перевірку Prometheus/Loki
    return {"status": "ready"}


@app.get("/debug/phoenix-trace")
async def phoenix_debug_trace():
    """Emit a test @tracer.chain span (enable with INSOMNIA_PHOENIX_DEBUG_ENDPOINT=true)."""
    if os.getenv("INSOMNIA_PHOENIX_DEBUG_ENDPOINT", "").strip().lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="disabled")
    from api.phoenix_otel import emit_debug_phoenix_chain_trace

    if not emit_debug_phoenix_chain_trace():
        raise HTTPException(status_code=503, detail="Phoenix OTEL not initialized")
    return {"ok": True, "detail": "debug chain span emitted"}


@app.post("/alert/raw")
async def alert_raw(request: Request):
    """Receive Alertmanager webhook and return the raw payload (no event hub, no guardrails)."""
    payload = await request.json()
    return payload


@app.post("/alert")
async def alert(request: Request):
    payload = await request.json()
    # Event hub: normalize, guardrails, triage, then investigate only when triage says so
    rejected, approved, triage_results = await process_webhook(
        payload, on_approved=investigate, use_triage=True
    )

    if not approved and not rejected:
        logger.info("Alert webhook received with no alert payload")
        return {"status": "no alert"}

    triage_list = (
        [triage_result_to_dict(t) for t in triage_results if t is not None]
        if triage_results
        else []
    )

    if rejected and not approved:
        return {
            "status": "rejected",
            "reason": "guardrails",
            "rejected": [{"namespace": r.namespace, "pod": r.pod, "reason": r.reason} for r in rejected],
            "triage": triage_list,
        }

    if rejected:
        return {
            "status": "processed",
            "investigated": len(approved),
            "rejected": [{"namespace": r.namespace, "pod": r.pod, "reason": r.reason} for r in rejected],
            "triage": triage_list,
        }

    return {"status": "processed", "investigated": len(approved), "triage": triage_list}