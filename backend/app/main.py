from fastapi import FastAPI

app = FastAPI(title="dept-rag-agent")


@app.get("/health")
def health():
    return {"status": "ok"}