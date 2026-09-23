# PRAHARI v7 — Low-Bandwidth / Offline Demo Mode

The project no longer depends on a fast tile service to show the core GIS workflow.

## Three levels of map resilience

1. **Offline EO Lite (default)** — a local geospatial context layer bundled inside the React app. It loads instantly with no internet. It is clearly labelled **NOT SATELLITE IMAGERY**. Risk zones, rainfall footprints, citizen reports and assets still overlay normally.
2. **Cached NASA** — real NASA GIBS VIIRS NRT imagery served from the local FastAPI backend. Run `prepare_offline_satellite.bat` once on good internet before travelling to college. PRAHARI caches only zoom 4–6 over Northeast India to minimize download size.
3. **NASA Live / Esri / OSM / Terrain** — optional online modes. They are never required for the core jury demo.

## Important next-day behavior

If the date changes after you cache the imagery, the backend prefers the newest already-cached scene instead of discarding it and attempting a slow network request. This is intentional demo resilience. The UI remains honest about imagery being near-real-time rather than live video.

## Recommended jury setting

Use **Offline EO Lite** for guaranteed responsiveness. If you prepared the cache successfully, switch once to **Cached NASA** to demonstrate the real NRT satellite layer without depending on college internet.
