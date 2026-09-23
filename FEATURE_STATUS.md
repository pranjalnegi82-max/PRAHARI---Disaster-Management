# PRAHARI v9 Feature Status

| Capability | Status | What is true now |
|---|---|---|
| Area selection + synchronized map | **Implemented** | Eight configured NER demo areas; selected area synchronizes map/detail views. General geocoder is not yet connected. |
| Open-Meteo weather context | **Implemented** | Current/stale/missing states, cache, timeout and provenance. Model-derived weather, not a physical station measurement. |
| Historical replay | **Implemented** | Explicit independent demo mode; never silently substitutes for live data. |
| Primary risk assessment | **Implemented baseline** | Explainable rule-based screening index. It is not a calibrated probability. |
| XGBoost + LightGBM + Random Forest ensemble | **Baseline/demo** | Preserved as an experimental research comparison; bootstrap/synthetic training means no operational accuracy claim. |
| Spatial/temporal real-data validation | **Deferred** | Requires defensible NER inventory and prediction-time feature table. |
| Assessment persistence/history/export | **Implemented** | Inputs, source metadata, version, completeness, reasons, limitations; JSON/CSV export. |
| Citizen report workflow | **Implemented** | Location, time, severity, optional image validation, persistence and review states. |
| Advisory alert lifecycle | **Implemented** | Draft/review/issue/acknowledge/resolve with audit history and duplicate prevention. |
| Server-side authorization | **Implemented for prototype** | Configurable operator/reviewer/admin keys; production identity provider still recommended. |
| Text SMS public notification | **Implemented / credentials required** | Twilio SMS integration is present and off by default until provider credentials, sender, consented recipients, and compliance setup exist. |
| Leaflet risk map | **Implemented** | Risk label + color, selected area sync, street/satellite visual basemap. |
| Satellite imagery context | **Implemented** | NASA GIBS/Esri remain visual basemaps; Sentinel-2 L2A scene discovery now uses Element 84 Earth Search with real acquisition dates, cloud metadata and before/after scene pairing. |
| Sentinel-2 scene QA / pairing | **Implemented** | Searches recent L2A acquisitions around the selected PRAHARI area, exposes source STAC records/thumbnails, and chooses a reference/recent pair when temporal separation and cloud metadata permit. Pair readiness is not a landslide detection result. |
| Landslide4Sense segmentation | **Partial / adapter implemented** | PRAHARI now includes an optional official-baseline-compatible 14-channel U-Net inference adapter plus a protected .npy patch inference API. Compatible weights, automated live-scene 14-channel preprocessing, and Northeast India validation are still required before enabling map masks. |
| IoT ingestion | **Implemented API / hardware pending** | Real/simulated provenance is explicit; only real sensor packets can escalate advisories. |
| Deformation trend screen | **Baseline/demo** | Point-sensor trend aid; not InSAR persistent homology or failure-time prediction. |
| Infrastructure exposure | **Baseline/demo** | Seed asset inventory preserved; no authoritative GIS intersection claim. |
| Route guidance | **Baseline/demo** | Prototype graph suggestion only; never called a safe route. |
| Responsive simplified UI | **Implemented source** | Four main destinations, progressive disclosure, error/missing/stale states, accessible semantic risk labels. |

## v9.3 SMS notification status
| Capability | Status | Notes |
|---|---|---|
| Opt-in recipient directory | Implemented | Admin-only, E.164 phone numbers, area/language preferences, SMS consent required |
| SMS provider integration | Implemented / credentials required | Twilio Programmable Messaging; disabled until backend credentials/sender are configured |
| Delivery persistence | Implemented | One row per alert/recipient SMS attempt; duplicate prevention |
| Delivery confirmation | Implemented | Callback or manual provider refresh; never inferred from button click |
| Large-scale government broadcast authority | Externally blocked | Requires agency authorization, verified recipient program, compliance and production provider setup |


## v9.4 additions
| Capability | Status | Notes |
|---|---|---|
| Field-officer civilian enrollment | IMPLEMENTED | Unique field keys map to one monitored posting; server enforces posting. |
| Household SMS registry | IMPLEMENTED | Name, E.164 phone, optional locality/household metadata, language and explicit consent persist in SQLite. |
| Admin cross-area registry | IMPLEMENTED | Admin can review/revoke records across monitored areas. |
| Area-selectable SMS broadcast | IMPLEMENTED | Alert area, specific monitored area, or all monitored areas; phone de-duplication applied. |
| Field officer account management UI | DEFERRED | Officers are configured server-side in `PRAHARI_FIELD_OFFICERS_JSON`; agency identity/OIDC remains production work. |

## v9.5 role portals
| Capability | Status | Notes |
|---|---|---|
| Admin Portal login | IMPLEMENTED | Admin-key validation; dev-open fallback only when local authentication is explicitly disabled. |
| Field Officer Portal login | IMPLEMENTED | Officer code + unique field key; posting returned by backend. |
| Portal/session separation | IMPLEMENTED | Session revalidation prevents a field key from rendering the admin workspace. |
| Posting-scoped civilian enrollment | IMPLEMENTED | Backend-enforced; retained from v9.4. |
| Field Officer read-only alert view | IMPLEMENTED | Only issued/acknowledged posting-relevant advisories shown. |
| Production identity/OIDC | DEFERRED | Recommended before agency deployment; prototype currently uses server-side API keys. |


## Satellite Intelligence v9.7
| Capability | Status | Notes |
|---|---|---|
| Live 14-channel satellite patch preparation | **Implemented / experimental** | Builds a 128×128×14 patch centered on a monitored PRAHARI location from Sentinel-2 L1C B1-B12 plus slope and DEM. Uses Earth Search STAC and a 10 m UTM-aligned grid. |
| Benchmark terrain parity | **Partial** | Local ALOS slope + DEM can be configured. Without them, Copernicus DEM GLO-30 is used and slope is derived from the DEM; this is explicitly marked as a distribution-mismatched fallback. |
| Live U-Net location inference | **Implemented / externally configured** | Admin API can prepare a live patch, run compatible Landslide4Sense weights, and polygonize candidate mask regions when PyTorch + weights are available. |
| Candidate polygon review map | **Implemented** | Experimental candidate polygons can be overlaid in the Sentinel-2 workspace. They remain unreviewed evidence and cannot issue alerts automatically. |
| Northeast India validation | **Deferred / required** | No operational accuracy claim is made until regional validation and error analysis are completed. |
