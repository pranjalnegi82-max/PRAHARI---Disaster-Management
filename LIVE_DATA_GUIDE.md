# PRAHARI — Live Data Guide (v3)

## What is genuinely live / near-real-time in this build

### 1) Weather and hydrometeorological feed — Open-Meteo
For each monitored NER location, the backend requests the latest public model feed and uses:
- current temperature
- current relative humidity
- current precipitation / rain
- cloud cover
- wind and gusts
- near-surface model soil moisture
- accumulated precipitation from the previous 24 hours
- precipitation forecast for the next 6 and 24 hours
- maximum precipitation probability over the next 24 hours

No API key is required for the public hackathon flow.

### 2) NASA near-real-time satellite imagery — EOSDIS GIBS
The Satellite workspace includes a `NASA NRT` basemap using VIIRS NOAA-20 corrected-reflectance true-colour imagery.
This is **near-real-time satellite imagery**, not a live video feed. Satellite overpass and processing latency apply.

### 3) Live risk fusion
`GET /api/live/locations` merges the latest weather feed with static terrain/susceptibility inputs:
- dynamic: rainfall + soil-wetness proxy
- static/baseline: slope, elevation, historical susceptibility, NDVI baseline

The risk engine recomputes the map risk state. HIGH/CRITICAL live-fusion results can enter the automatic alert engine.

## What is NOT yet a real sensor feed
- slope displacement
- physical pore-pressure sensors
- local rain-gauge hardware
- real field soil probes

Those require IoT hardware. The UI labels simulated/edge-ready values accordingly.

## What is NOT yet real-time EO analytics
NDVI change and surface-change scores are prototype/baseline analytics. Production would run Sentinel-1/2 + DEM processing and validated landslide inventory data.

## Demo workflow
1. Start backend + frontend.
2. Keep internet connected.
3. Click **Refresh live data** in the header.
4. Confirm the selected-zone card says **LIVE WEATHER FEED**.
5. Open **Risk Map** and inspect current risk states.
6. Open **Satellite** → choose **NASA NRT**.
7. Open **AI Analysis** → click **Analyze selected LIVE data**.
8. If risk is HIGH/CRITICAL, show the automatic warning in **Alerts**.
9. If the live risk is LOW on hackathon day, use the Cloudburst scenario only to demonstrate emergency escalation; say clearly that the scenario is simulated.

## Offline safety
If the public API cannot be reached, the backend does not crash. It returns `live:false` and clearly-labelled fallback values, so the demo can continue.
