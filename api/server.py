import logging
import os
import sys

from fastapi import FastAPI, Request

from agent.commander import investigate

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


@app.post("/alert")
async def alert(request: Request):

    payload = await request.json()
    # Alertmanager sends "alerts" (list); support "alert" (single) or "alerts"
    raw = payload.get("alerts") or payload.get("alert")
    alert = (raw[0] if isinstance(raw, list) and raw else raw) if raw else None

    if alert and isinstance(alert, dict):
        labels = alert.get("labels", {})
        ns = labels.get("namespace", "?")
        pod = labels.get("pod", "?")
        logger.info("Alert received → starting investigation for namespace=%s pod=%s", ns, pod)
        await investigate(alert)
        logger.info("Investigation complete for %s/%s", ns, pod)
        return {"status": "processed"}
    logger.info("Alert received with no alert payload")
    return {"status": "no alert"}