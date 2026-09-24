"""Read-only check of the configured model and live-input preparation gates."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import settings  # Load the existing project environment first.
import satellite_engine
import satellite_preprocess

model = satellite_engine.status()
prep = satellite_preprocess.status()
print(json.dumps({"model": model, "preprocessing": prep}, indent=2))
ready = (model.get("verified") and model.get("status") == "READY" and prep.get("live_inference_ready")
         and prep.get("profile_checkpoint_sha256") == model.get("checkpoint_sha256"))
sys.exit(0 if ready else 1)
