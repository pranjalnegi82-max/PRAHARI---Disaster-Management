# PRAHARI v7 Prize-Ready Handoff

This folder contains the final SIH26001 implementation and supporting documents.

## Start
- `start_all.bat` for one-click launch
- Backend: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Frontend: usually `http://localhost:5173`

## Before college demo
1. Run `prepare_offline_satellite.bat` on good internet.
2. Run `run_preflight.bat`.
3. Use Offline EO Lite first during demo; use Cached NASA only if ready.

## Included documents
- `docs/PRAHARI_SIH26001_Prize_Ready_Presentation.pptx`
- `docs/PRAHARI_Technical_Approach_Document.docx`
- `docs/PRAHARI_Working_Document_Demo_Manual.docx`

## Scientific honesty
PRAHARI is a research-backed hackathon decision-support prototype. It does not claim live satellite video, physical field sensors, field-validated ML accuracy, official evacuation routing, or real SMS/WhatsApp delivery without external provider integration.

## v7.1 Map restoration
- Overview and Risk Map use the original interactive Leaflet + OpenStreetMap basemap again.
- Offline EO Lite is retained only as a low-bandwidth/offline Earth-observation fallback in the Satellite workspace.
- Cached NASA remains available for the satellite demo without affecting the standard operational GIS map.
