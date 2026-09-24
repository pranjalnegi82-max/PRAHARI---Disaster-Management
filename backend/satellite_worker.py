"""Optional dedicated PyTorch service; run from backend with uvicorn."""
from pathlib import Path
import hmac
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from satellite_l4s import infer_patch, read_patch_bytes, status

app = FastAPI(title="PRAHARI experimental satellite worker")


def authorize(authorization: str = Header(default="")):
    token = os.getenv("PRAHARI_L4S_SERVICE_TOKEN", "").strip()
    if len(token) < 32:
        raise HTTPException(503, "Worker authentication is not configured.")
    if not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Invalid worker token.")


@app.get("/health")
def health():
    return {"service": "satellite-worker", "status": "online"}


@app.get("/v1/status", dependencies=[Depends(authorize)])
def model_status():
    return status()


@app.post("/v1/infer", dependencies=[Depends(authorize)])
async def infer(request: Request):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(413, "Patch exceeds the 2 MiB limit.")
    try:
        patch = read_patch_bytes(bytes(content))
        return await run_in_threadpool(infer_patch, patch)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
