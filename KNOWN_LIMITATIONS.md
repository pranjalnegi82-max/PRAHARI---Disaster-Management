# SIH26192 flash flood limitations

- Screening thresholds and wetness adjustments are illustrative and uncalibrated.
- Catchments and settlement points are demo data until configured; configuration is not validation.
- Point weather samples do not establish hyper-local basin rainfall or flood arrival time.
- No verified event inventory, watershed routing or inundation model is included.
- Slope/history configuration is supporting metadata, not a trained flood feature pipeline.
- No guaranteed evacuation lead time or calibrated flood probability is available.
- Village map points are contextual; SMS recipient selection remains area based.
- IoT endpoints require actual deployed sensors; authenticated source labels are not hardware attestation.

See [SIH26192_IMPLEMENTATION.md](SIH26192_IMPLEMENTATION.md).

# Known Limitations & Highest-Value Next Improvements

## Known limitations
- The primary screening index is transparent but not a calibrated probability of landslide occurrence.
- The experimental tree ensemble was trained on bootstrap/synthetic labels, so its validation numbers are not field accuracy for Northeast India.
- Slope/elevation/NDVI/history for the eight bundled locations are prototype seed context, not an authoritative DEM/geology product.
- Open-Meteo fields are weather-model data and may differ from a local gauge or geotechnical station.
- No authoritative asset, road-closure, shelter or administrative exposure layer is bundled; infrastructure/routing modules are visibly prototype-only.
- NASA/Esri basemaps are visual context. Experimental satellite preprocessing/inference exists but requires compatible weights and regional validation.
- Point IoT telemetry is supported in software, but no physical field station is bundled with this repository.
- SQLite and external PostgreSQL are supported; multi-agency deployment still needs organizational identity, appropriate GIS storage, audit retention and operational governance.

## Next three highest-value improvements
1. **Build a real Northeast India spatiotemporal training table.** Combine a verified landslide inventory with prediction-time rainfall histories, DEM-derived terrain, geology/land cover and soil-moisture features. Split validation by event/time and geography, compare a simple baseline, then calibrate probabilities and report precision/recall/F1/false alarms.
2. **Replace seed GIS with authoritative exposure layers.** Ingest verified roads, settlements, hospitals/schools/bridges and shelters into PostGIS; perform actual hazard-zone intersections. Keep routing as a suggestion unless official closure and hazard layers are available.
3. **Complete the ground + EO observation loop.** Connect the Heltec/ESP32-S3 field node as `REAL_SENSOR`; separately build a Landslide4Sense-style post-event scene pipeline for inventory updates. Validate both against field observations before allowing either to escalate operational policy.
