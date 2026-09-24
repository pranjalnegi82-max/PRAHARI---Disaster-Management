"""Local inference or an explicitly configured authenticated worker."""
import io
import json
import os
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import numpy as np


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _config():
    url = os.getenv("PRAHARI_L4S_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("PRAHARI_L4S_SERVICE_TOKEN", "").strip()
    if url:
        parsed = urlsplit(url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if not parsed.hostname or (parsed.scheme != "https" and not (local and parsed.scheme == "http")) or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("Inference worker URL must use HTTPS (HTTP allowed only on localhost).")
        if len(token) < 32:
            raise RuntimeError("Configure an inference worker token of at least 32 characters.")
    return url, token


def _remote(path, data=None):
    url, token = _config()
    request = Request(url + path, data=data, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/octet-stream" if data is not None else "application/json",
    })
    try:
        with build_opener(_NoRedirect()).open(request, timeout=90 if data is not None else 12) as response:
            content = response.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            raise ValueError("Response too large")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("Invalid response")
        return result
    except Exception as exc:
        raise RuntimeError("Inference worker is unavailable or returned an invalid response.") from exc


def status():
    try:
        url, _ = _config()
        if not url:
            from satellite_l4s import status as local_status
            return {**local_status(), "transport": "LOCAL"}
        result = _remote("/v1/status")
        if result.get("status") == "READY" and (result.get("verified") is not True or not re.fullmatch(r"[0-9a-f]{64}", result.get("checkpoint_sha256") or "")):
            raise RuntimeError("Inference worker has not verified its checkpoint.")
        allowed = {"status", "verified", "checkpoint_sha256", "device", "reason", "engine", "input_contract", "verification_scope", "regional_validation", "operational_warning"}
        return {**{k: v for k, v in result.items() if k in allowed}, "transport": "REMOTE"}
    except RuntimeError as exc:
        return {"status": "UNAVAILABLE", "verified": False, "reason": str(exc), "transport": "REMOTE"}


def infer_patch(patch):
    url, _ = _config()
    if not url:
        from satellite_l4s import infer_patch as local_infer
        return local_infer(patch)
    stream = io.BytesIO()
    np.save(stream, np.asarray(patch, dtype=np.float32), allow_pickle=False)
    result = _remote("/v1/infer", stream.getvalue())
    if result.get("status") != "INFERRED":
        raise RuntimeError("Inference worker did not return a completed result.")
    return result
