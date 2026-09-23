# PRAHARI v8 — Research Paper Synthesis and Implementation Matrix

This document records how the uploaded research set was reviewed and translated into engineering changes. Three uploads were duplicate copies, leaving **12 unique papers**. PRAHARI implements a finding only when the current data can support it; otherwise the capability is explicitly marked **PARTIAL** or **ROADMAP** rather than simulated as if scientifically operational.

## 1. Felsberg et al. (2022) — *Estimating global landslide susceptibility and its uncertainty through ensemble modeling*
**Key contribution:** ensemble susceptibility, blocked cross-validation, input perturbation, explicit uncertainty, attention to inventory/reporting and spatial-representativeness bias.  
**Gap relevant to PRAHARI:** a single risk number can hide large model/input uncertainty.  
**Implemented:** model disagreement, an indicative decision interval, blocked bootstrap validation, provenance and uncertainty labels. The interval is explicitly **not** presented as a calibrated statistical confidence interval.  
**Status:** IMPLEMENTED.

## 2. Fathani, Karnawati & Wilopo (2016) — *An integrated methodology to develop a standard for landslide early warning systems*
**Key contribution:** seven-subsystem people-centred LEWS: risk mapping, communication, response team, evacuation map, SOP, monitoring/warning services, local commitment/maintenance.  
**Gap relevant to PRAHARI:** prediction-only systems do not complete the warning-to-action loop.  
**Implemented:** multilingual warning, acknowledgement, citizen reports, response checklist, offline assembly-point route prototype, human decision gate, monitoring/maintenance status.  
**Status:** IMPLEMENTED.

## 3. Stähli et al. (2015) — *Monitoring and prediction in early warning systems for rapid mass movements*
**Key contribution:** identifies limitations of proxy-only monitoring, weak treatment of precursors/uncertainty, and missing mobility/runout estimates; advocates complementary multi-source monitoring and sensor/model recalibration.  
**Gap relevant to PRAHARI:** rainfall alone is not enough; pore pressure, water state and deformation precursors matter.  
**Implemented:** IoT inputs for soil moisture, rainfall intensity, tilt, vibration, pore pressure and displacement; field precursor screen; model uncertainty; sensor-weather fusion.  
**Not implemented:** physically calibrated runout/mobility because the prototype lacks site-specific rheology/material/deposition data.  
**Status:** PARTIAL.

## 4. Mei et al. (2025) — *Deciphering Landslide Precursors From Spatiotemporal Ground Motion Using Persistent Homology*
**Key contribution:** slope-wide InSAR deformation fields + persistent homology can detect spatiotemporal precursors earlier than many single-point alert methods.  
**Gap relevant to PRAHARI:** point sensors can miss the spatial organisation of slope deformation.  
**Implemented now:** a point-sensor deformation-trend endpoint with honest minimum-time-window checks.  
**Roadmap:** Sentinel-1/InSAR deformation cube + persistent-homology analysis once real slope-wide displacement fields are available. PRAHARI does **not** claim PH is active today.  
**Status:** ROADMAP / PARTIAL FOUNDATION.

## 5. Khan et al. (2022) — *Global Landslide Forecasting System for Hazard Assessment and Situational Awareness*
**Key contribution:** LHASA forecast extension using forecast precipitation, soil moisture and snow information for up to 3-day probabilistic hazard outlooks; stresses periodic validation and user-oriented representation.  
**Gap relevant to PRAHARI:** a nowcast alone offers limited preparation time.  
**Implemented:** NOW / +6h / +24h / +48h / +72h risk trajectory using forecast rainfall while carrying antecedent wetness forward, with explicit non-official forecast wording.  
**Status:** IMPLEMENTED.

## 6. Nocentini et al. (2024) — *Regional-scale spatiotemporal landslide probability assessment through machine learning and potential applications for operational warning systems*
**Key contribution:** dynamic Random Forest integrating cumulative rainfall/snowmelt/seasonal variability with static susceptibility factors.  
**Gap relevant to PRAHARI:** static susceptibility does not describe *when* triggering conditions are changing.  
**Implemented:** explicit 7-day cumulative rainfall and month seasonality features in the research ensemble, alongside 24h/72h/11d dynamic rainfall measures.  
**Status:** IMPLEMENTED.

## 7. Krøgli et al. (2018) — *The Norwegian forecasting and warning service for rainfall- and snowmelt-induced landslides*
**Key contribution:** operational warning as a system of hydrometeorological stations, historical data, forecast models, thresholds/return periods and trained forecasters, with multi-day updates to stakeholders.  
**Gap relevant to PRAHARI:** an ML score should not autonomously make evacuation/road-closure decisions.  
**Implemented:** human decision gate, 72h outlook, threshold context, live/last-known/fallback provenance, acknowledgement and operational dashboard.  
**Status:** IMPLEMENTED.

## 8. Piciullo et al. (2017) — *Adapting the EDuMaP method to test the performance of the Norwegian early warning system for weather-induced landslides*
**Key contribution:** warning performance must consider warning duration, level, landslide density/multiple events and different error costs—not only a simple classification score.  
**Gap relevant to PRAHARI:** model AUC alone says little about operational alert quality.  
**Implemented:** event feedback (confirmed / false alarm / partial), observed false-alarm rate, confirmation rate, acknowledgement rate and mean acknowledgement time.  
**Roadmap:** full EDuMaP duration matrix after sufficient real alert/event history exists.  
**Status:** PARTIAL.

## 9. Pan et al. (2018) — *Rainfall threshold calculation for debris flow early warning in areas with scarcity of data*
**Key contribution:** antecedent precipitation and short-duration rainfall should be considered together, especially when inventories are sparse; antecedent rainfall may be represented with a decay term.  
**Gap relevant to PRAHARI:** current 24h rainfall alone can miss preconditioning.  
**Implemented:** 72h antecedent rain, 7-day cumulative rain, exponentially decayed 11-day effective rain (prototype K=0.84) and peak 1-hour rainfall.  
**Status:** IMPLEMENTED.

## 10. Stanley et al. (2021) — *Data-Driven Landslide Nowcasting at the Global Scale*
**Key contribution:** LHASA v2 uses XGBoost with dynamic rainfall/soil moisture and probabilistic output; stresses time-separated evaluation and physically sensible constraints.  
**Gap relevant to PRAHARI:** simple thresholds cannot learn nonlinear hydro-terrain interactions and probability trade-offs.  
**Implemented:** weighted XGBoost + LightGBM + Random Forest ensemble, monotonic constraints on physically directional features, probabilistic output, model disagreement and TreeSHAP local explanations.  
**Status:** IMPLEMENTED.

## 11. Saito, Nakayama & Matsuyama (2010) — *Two Types of Rainfall Conditions Associated with Shallow Landslide Initiation in Japan as Revealed by Normalized Soil Water Index*
**Key contribution:** differentiates short-duration/high-intensity rainfall from long-duration/low-intensity saturation pathways and uses soil-water state to improve early warning.  
**Gap relevant to PRAHARI:** one generic rainfall threshold hides distinct triggering regimes.  
**Implemented:** `SHORT_INTENSE`, `LONG_SATURATING`, `MIXED`, `QUIET` rainfall-regime classifier plus a soil-water stress proxy. It is **not** labelled as the official Japanese NSWI.  
**Status:** IMPLEMENTED.

## 12. Marra et al. (2025) — *Threshold and probability. The conceptual difference between ID thresholds for landslide initiation and IDF curves*
**Key contribution:** an intensity-duration landslide trigger threshold and an IDF rainfall-frequency probability are conceptually different; mixing them can cause misleading probability interpretations and false alarms.  
**Gap relevant to PRAHARI:** a UI label could accidentally present a trigger screen as a return-period probability.  
**Implemented:** rainfall threshold output is now explicitly labelled **TRIGGER-CONDITION SCREEN — NOT IDF RETURN-PERIOD / OCCURRENCE PROBABILITY**.  
**Status:** IMPLEMENTED.

---

# Resulting v8 architecture

**Static risk knowledge**: slope + elevation + historical susceptibility + NDVI baseline  
**Dynamic hydro trigger**: 1h peak + 24h + 72h + 7d cumulative + 11d effective rainfall + 24/48/72h forecast + soil wetness + seasonality  
**Ground precursors**: local rain intensity + soil moisture + tilt + vibration + pore pressure + displacement  
**Remote sensing**: NASA GIBS NRT visual context now; Sentinel/InSAR analytics on roadmap  
**Prediction**: monotonic XGBoost + LightGBM + Random Forest + physics/precursor safety guardrails  
**Interpretation**: susceptibility vs dynamic trigger, TreeSHAP, model votes, decision interval, rainfall regime, soil-water stress  
**Operational warning**: impact/exposure, multilingual alert, acknowledgement, field feedback, human decision gate, offline response route  
**Evaluation**: model bootstrap diagnostics + separate operational alert-learning metrics

# Scientific boundary

PRAHARI v8 remains a **research/hackathon decision-support prototype**. The bundled ML artefact is trained on physics-guided synthetic bootstrap scenarios to prove the data/ML/alert pipeline. Production deployment requires regional real-event calibration and validation using GSI/ISRO/NASA inventories, high-resolution DEM/geology/land-cover data, GPM/SMAP/Sentinel products and calibrated field instrumentation.
