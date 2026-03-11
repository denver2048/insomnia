from fastapi import FastAPI, Request

from agent.commander import investigate

app = FastAPI()


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

    alert = payload.get("alert", [])
    
    if alert:
        await investigate(alert)
    else:
        return {"status": "no alert"}

    return {"status": "received"}