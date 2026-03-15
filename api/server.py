import logging
import os
import sys

from fastapi import FastAPI, Request

from agent.commander import investigate
from eventhub.hub import process_webhook

logger = logging.getLogger(__name__)
app = FastAPI()


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


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    # тут пізніше можна додати перевірку Prometheus/Loki
    return {"status": "ready"}


@app.post("/alert/raw")
async def alert_raw(request: Request):
    """Receive Alertmanager webhook and return the raw payload (no event hub, no guardrails)."""
    payload = await request.json()
    return payload


@app.post("/alert")
async def alert(request: Request):
    payload = await request.json()
    # Event hub: normalize webhook payload, run guardrails, then investigate only approved alerts
    rejected, approved = await process_webhook(payload, on_approved=investigate)

    if not approved and not rejected:
        logger.info("Alert webhook received with no alert payload")
        return {"status": "no alert"}

    if rejected and not approved:
        return {
            "status": "rejected",
            "reason": "guardrails",
            "rejected": [{"namespace": r.namespace, "pod": r.pod, "reason": r.reason} for r in rejected],
        }

    if rejected:
        return {
            "status": "processed",
            "investigated": len(approved),
            "rejected": [{"namespace": r.namespace, "pod": r.pod, "reason": r.reason} for r in rejected],
        }

    return {"status": "processed"}