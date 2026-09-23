# PRAHARI v7 — Research Gap Analysis and Implemented Design

## Research basis reviewed

PRAHARI v7 was designed after reviewing the earlier Sikkim/Dibang susceptibility papers plus the newly supplied work on Aizawl community risk, geotechnical/IoT monitoring, SAR/InSAR early warning, AI-EWS guardrails and integrated rescue/edge architectures.

### Main lessons from the papers

**Dibang Valley / Sikkim ML papers** — use richer terrain/geology and inventories, gradient boosting/ensembles, SHAP, dynamic rainfall/soil moisture, and future InSAR/GNSS/seismic integration. These papers are scientifically stronger than PRAHARI's current bootstrap data.

**Aizawl community-risk study (Scientific Reports, 2026)** — warning quality is not only model accuracy. Residents highlighted rainfall, poor drainage and experienced precursors; trust, clear/actionable instructions, coverage, evacuation knowledge and training matter. PRAHARI therefore treats community observations as a structured EWS input and adds preparedness logic.

**IoT-Based Landslide Monitoring and Prediction Using ML (E3S, 2026)** — geotechnical variables such as cohesion, internal friction angle, slope geometry and Factor of Safety complement environmental ML. PRAHARI adds a sensor-ingest schema and transparent FOS screening endpoint without pretending those field values currently exist.

**SAR + ML / LandSense survey (IJERT, 2026)** — highlights Sentinel-1 InSAR, geo-fencing, ensemble ML, FastAPI integration, safe routing and multi-channel alerts. PRAHARI implements the geo-fence API and offline route engine; real Sentinel-1 deformation remains a production data pipeline.

**Comprehensive IoT / rescue system (2025)** — edge processing and LoRa-like low-bandwidth communication are important where connectivity is weak. PRAHARI adds an edge-style local rule and explicitly designs its demo to continue without internet.

**AI for EWS guardrails (iScience, 2025)** — effective EWS is end-to-end and people-centred across risk knowledge, monitoring/forecasting, communication and preparedness/response. AI needs accountability, local knowledge, bias/data-quality awareness and human authority. PRAHARI v7 mirrors this four-pillar structure and adds data-provenance labels and feedback.

## Gap matrix

| Gap in v6 / common research prototypes | v7 response |
|---|---|
| Susceptibility/prediction stops at a map | Impact + warning + acknowledgement + response plan |
| Physical hazard conflated with consequences | Separate hazard, exposure, vulnerability and impact outputs |
| Community input treated as simple report list | Time/distance/severity/verification-weighted corroboration score |
| False alarms are not learned from | Alert CONFIRMED/FALSE_ALARM/PARTIAL feedback API and metrics |
| Sensor story is simulated only | Real telemetry ingest contract + explicit demo-source labelling |
| Cloud dependency in remote areas | Edge decision rule + local SQLite + offline response graph |
| Satellite tiles fail on slow network | Offline EO Lite + local NASA GIBS cache/proxy + previous-scene fallback |
| Map zoom generates many tile requests | Jury mode uses zoom 4–6 imagery and Leaflet idle/buffer tuning |
| ML can occasionally violate physical intuition | Conservative hydrologic/terrain decision guardrail |
| No geotechnical physics endpoint | Simplified FOS screening endpoint for real field inputs |
| Alerts are broad rather than location-targeted | Geo-fence check API |
| Preparedness absent | Response checklist + prototype assembly point + offline Dijkstra |
| “Accuracy” becomes the presentation focus | Explainability, uncertainty, provenance and verified-event learning loop |

## What PRAHARI still must NOT claim

- No real-world 97% accuracy. The shipped ML training is bootstrap/synthetic.
- No continuous live satellite video.
- No operational Sentinel-1 InSAR deformation processing yet.
- No installed physical sensor network yet; `SIMULATED_HACKATHON` packets are labelled.
- No official shelter or evacuation route database; v7 route nodes are prototype demonstration data.
- No real SMS/WhatsApp gateway delivery in the current build.
- No official geological warning authority status.

## Strongest novelty statement for judges

**“Most landslide studies focus on where susceptibility is high. PRAHARI connects long-term susceptibility to dynamic triggers, uncertainty, community precursor evidence, exposure and response — and keeps the critical GIS/response workflow usable even when internet connectivity is poor.”**

## Production data path

The next scientifically meaningful additions are real validated datasets, not more synthetic feature columns: lithology, lineament/fault distance, drainage/TWI/SPI/STI, LULC, soil depth/texture, Sentinel-1 InSAR displacement, GNSS, field rainfall/soil/pore-pressure/tilt nodes, and a temporally/spatially separated NER landslide inventory.
