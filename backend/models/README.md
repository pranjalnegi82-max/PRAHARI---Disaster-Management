# PRAHARI satellite model directory

Large neural-network weights are intentionally **not committed to Git**.

For the optional Landslide4Sense-compatible baseline adapter:

1. Install the optional runtime:
   `pip install -r backend/requirements-satellite.txt`
2. Obtain compatible IARAI Landslide4Sense baseline weights from the official project.
3. Place the file at:
   `backend/models/landslide4sense_unet.pth`

   or set:
   `PRAHARI_L4S_WEIGHTS_PATH=<absolute path to the .pth file>`
4. Restart the backend and check:
   `GET /api/satellite/model/status`

The adapter expects the official benchmark input contract: a 128×128×14 float array containing Sentinel-2 B1–B12, slope, and DEM using the benchmark preprocessing statistics.

Do not treat the competition validation score as Northeast India operational accuracy. Live-scene preprocessing and regional validation are separate requirements.
