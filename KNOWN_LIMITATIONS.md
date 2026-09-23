# Known Limitations & Highest-Value Next Improvements

## Known limitations
- The primary screening index is transparent but not a calibrated probability of landslide occurrence.
- The experimental tree ensemble was trained on bootstrap/synthetic labels, so its validation numbers are not field accuracy for Northeast India.
- Slope/elevation/NDVI/history for the eight bundled locations are prototype seed context, not an authoritative DEM/geology product.
- Open-Meteo fields are weather-model data and may differ from a local gauge or geotechnical station.
- No authoritative asset, road-closure, shelter or administrative exposure layer is bundled; infrastructure/routing modules are visibly prototype-only.
- NASA/Esri satellite imagery is visual context. No satellite scene is currently processed for landslide segmentation.
- Point IoT telemetry is supported in software, but no physical field station is bundled with this repository.
- SQLite/operator keys are appropriate for a local prototype; a multi-agency deployment needs PostgreSQL/PostGIS, organizational authentication, secret management, audit retention and operational governance.

## Next three highest-value improvements
1. **Build a real Northeast India spatiotemporal training table.** Combine a verified landslide inventory with prediction-time rainfall histories, DEM-derived terrain, geology/land cover and soil-moisture features. Split validation by event/time and geography, compare a simple baseline, then calibrate probabilities and report precision/recall/F1/false alarms.
2. **Replace seed GIS with authoritative exposure layers.** Ingest verified roads, settlements, hospitals/schools/bridges and shelters into PostGIS; perform actual hazard-zone intersections. Keep routing as a suggestion unless official closure and hazard layers are available.
3. **Complete the ground + EO observation loop.** Connect the Heltec/ESP32-S3 field node as `REAL_SENSOR`; separately build a Landslide4Sense-style post-event scene pipeline for inventory updates. Validate both against field observations before allowing either to escalate operational policy.
