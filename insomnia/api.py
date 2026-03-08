from fastapi import FastAPI, Request
from agent import agent

app = FastAPI()


@app.post("/alert")
async def alert(req: Request):

    body = await req.json()

    alert = body["alerts"][0]
    labels = alert["labels"]

    state = {
        "alert": {
            "namespace": labels.get("namespace", "default"),
            "pod": labels.get("pod")
        }
    }

    result = await agent.ainvoke(state)

    print(result["report"])

    return {"status": "processed"}
