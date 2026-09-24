# Experimental satellite analysis setup

PRAHARI can prepare live Sentinel-2 L1C patches, run a compatible U-Net, and show candidate masks and polygons. The integration does **not** include trained weights, a validated raw-scene preprocessing recipe, or Northeast India accuracy measurements. Until the model and matching input profile are configured, the UI correctly shows **AI analysis unavailable**. Scene review and patch preparation remain independent.

## What changed

- Model readiness requires a strict checkpoint load, finite tensors, and a successful 14-channel forward pass. A filename alone is insufficient. Optional SHA-256 pinning identifies the intended checkpoint. These checks establish structural compatibility, not training quality.
- Background jobs return progress while the browser polls. A prepared patch can be reused for the same location for up to one hour.
- Raster reads are restricted to the 128×128 target grid. Missing scene or terrain pixels stop preparation instead of being filled and classified.
- Results include a geographic pixel mask, candidate polygons, area in square metres/hectares, acquisition time, checkpoint identity, terrain/input provenance, and GeoJSON export. Polygon areas subtract holes. Components smaller than eight pixels are omitted from polygons but remain visible in the pixel mask.
- Scores are uncalibrated softmax outputs. Empty results do not establish safety. Nothing in this workflow issues an alert or verifies a landslide.

## Required model and preprocessing information

Obtain a legitimate trained checkpoint compatible with the official [IARAI Landslide4Sense U-Net](https://github.com/iarai/Landslide4Sense-2022). The official README links its baseline weights. That download was not available during implementation; no trained checkpoint was tested or bundled. Keep weights outside Git and load only trusted artifacts.

The baseline's mean/std normalization is applied to already-prepared benchmark inputs. It is **not** a recipe for converting arbitrary reflectance, slope degrees and raw DEM metres into those inputs. Applying benchmark statistics directly to raw elevation can produce meaningless output. The adapter therefore includes a gross scale rejection check, which does not establish scientific parity.

For live inference, supply a JSON profile derived from the actual model's training preprocessing. Do not guess constants to enable the button. It must contain:

| Field | Required value |
| --- | --- |
| `channel_order` | `["B1","B2","B3","B4","B5","B6","B7","B8","B9","B10","B11","B12","SLOPE","DEM"]` |
| `scales` | Fourteen finite, nonzero multipliers from the training pipeline |
| `offsets` | Fourteen finite offsets from the training pipeline |
| `checkpoint_sha256` | Lowercase SHA-256 of the intended checkpoint |
| `terrain_source` | `ALOS_LOCAL_SLOPE_DEM`, `ALOS_LOCAL_DEM_DERIVED_SLOPE`, or `COPERNICUS_DEM_GLO30_DERIVED_SLOPE`, matching training and deployment |
| `provenance` | Description/reference for the training recipe and its verification |

PRAHARI first reads Sentinel reflectance using STAC scale/offset metadata, slope in degrees, and DEM elevation. It then applies `benchmark_value = prepared_channel * scales + offsets`, followed by the official baseline mean/std. This profile format supports only an affine conversion. If training used a different transform, implement and validate that exact transform before enabling live inference. An identity profile is not evidence of compatibility.

The benchmark uses ALOS terrain. The optional Copernicus fallback is a different distribution and requires a correspondingly trained/validated model. Scene-level cloud cover is available; a local pixel cloud mask is not applied. The visual L2A comparison pair is separate from the selected L1C inference acquisition. The model segments one patch and does not infer before/after change from the displayed pair.

## Option A: API and inference on one capable host

From the project root, in a Python virtual environment:

```sh
pip install -r backend/requirements.txt
pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu
```

Configure these server-side environment variables (or the existing project `.env`):

```text
PRAHARI_L4S_WEIGHTS_PATH=/absolute/path/to/trained-checkpoint.pth
PRAHARI_L4S_WEIGHTS_SHA256=<actual checkpoint sha256>
PRAHARI_L4S_DEVICE=cpu
PRAHARI_L4S_INPUT_PROFILE=/absolute/path/to/training-input-profile.json
PRAHARI_L4S_ALLOW_EXPERIMENTAL_PREPROCESS=true
```

If the training recipe uses local ALOS rasters, also configure `PRAHARI_L4S_ALOS_DEM_PATH` and `PRAHARI_L4S_ALOS_SLOPE_PATH`. A missing slope raster causes slope derivation from the DEM, which is a different named terrain source. Verify georeferencing, coverage, units, and agreement with training.

Run `python tools/check_satellite_setup.py` from the root. It exits nonzero until the model, profile identity, terrain source, and experimental opt-in agree. A zero exit is a configuration check, not a regional accuracy evaluation. Restart after environment or checkpoint changes, then refresh status in the UI.

## Option B: dedicated inference worker

The existing Render API build omits PyTorch. The optional worker keeps the model on a separate host with sufficient memory and compute; the API still prepares geospatial patches. No host is provisioned by this change.

On the worker, install:

```sh
pip install -r backend/requirements-worker.txt
pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu
```

Set the checkpoint path/checksum/device there and a new `PRAHARI_L4S_SERVICE_TOKEN` of at least 32 characters. Use an independently generated secret and keep it out of the browser and repository. Start one worker process from `backend`:

```sh
uvicorn satellite_worker:app --host 0.0.0.0 --port 8001
```

Expose the service through HTTPS. `/health` reports service liveness only; `/v1/status` and `/v1/infer` require the bearer token. On the PRAHARI API, configure:

```text
PRAHARI_L4S_SERVICE_URL=https://your-inference-host
PRAHARI_L4S_SERVICE_TOKEN=<same worker token>
PRAHARI_L4S_INPUT_PROFILE=/absolute/path/to/training-input-profile.json
PRAHARI_L4S_ALLOW_EXPERIMENTAL_PREPROCESS=true
```

HTTP is allowed only for localhost testing. Redirects are refused to prevent forwarding the token. The worker accepts bounded float32 NPY input and uses restricted checkpoint loading. Raw uploaded patches must already satisfy the benchmark-value contract; their provenance is not verified by upload.

## Job/API behavior

Admin-only `POST /api/satellite/jobs/{location_id}` accepts `operation` (`prepare` or `infer`), `confirm_experimental: true`, and an optional 32-character `patch_id` for reuse. It returns 202 and a job ID. Poll admin-only `GET /api/satellite/jobs/status/{job_id}` until `SUCCEEDED` or `FAILED`. Success includes the result; failure includes the reason. The legacy synchronous endpoints remain available, but the UI uses jobs to avoid a single long HTTP request.

Jobs and prepared patches are process-local: **run the API with one Uvicorn worker**. Only one satellite job runs at a time; another submission gets 409. Retention is one hour and bounded to 16 jobs/eight patches. Restart, process recycle, or idle suspension loses these records; polling then returns 404. Switching locations aborts browser polling and clears displayed results/consent but does not cancel server processing. For multi-instance or durable operation, replace this store with a shared queue and object storage.

## Verification

```sh
pip install -r qa/requirements-dev.txt
python -m pytest qa/test_v9.py qa/test_satellite.py -q
cd frontend
npm ci
npm run build
```

GitHub Actions also runs `qa/satellite_ui.cjs` using Playwright 1.55.1 and uploads screenshots. Browser fixtures and the generated structural test checkpoint are explicitly synthetic. Tests cover missing/corrupt weights, actual forward-pass execution, checksum mismatch, unsafe NPY headers, nodata, polygon holes, patch identity, authorization, queue serialization, readiness, consent, map layers, export, empty results, and location changes at desktop/mobile widths. They are not accuracy, live-data, or Render deployment tests.

Before treating results as evidence, obtain representative labeled data, verify preprocessing against training inputs, measure regional precision/recall and failure cases, and establish the human review workflow. The upstream architecture license is included in `backend/models/L4S_LICENSE.txt`.
