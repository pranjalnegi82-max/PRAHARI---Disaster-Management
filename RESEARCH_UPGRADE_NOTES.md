# PRAHARI v6 — Research Review, Gap Analysis and Implemented Upgrade

## Purpose
This file documents how PRAHARI was improved after reviewing the three supplied landslide-susceptibility papers and additional recent work on dynamic early warning, spatial validation and physics-informed modeling.

The core research lesson is that **susceptibility is not the same as early warning**. Susceptibility expresses *where* terrain is predisposed to failure; early warning must also represent *when* dynamic hydrometeorological conditions make failure more likely. PRAHARI v6 therefore separates static susceptibility from dynamic triggering and fuses them into current hazard.

---

## A. Supplied papers reviewed

### 1. Mihu et al. (2026) — Dibang Valley, NE India
**Machine Learning-based Landslide Susceptibility Modeling in the Dibang Valley, NE India.** Earth Systems and Environment 10:8639–8663. DOI: 10.1007/s41748-026-01036-3.

Key lessons used:
- XGBoost and LightGBM are strong tabular geospatial learners.
- SHAP makes complex models explainable.
- Important factors extend beyond rainfall/slope to lithology, lineament density, elevation and other hydro-geospatial variables.
- Static inventory-based susceptibility is limited by temporal variability, incomplete inventories, multi-resolution sensor compatibility and missing in-situ geotechnical data.
- The authors explicitly point toward real-time rainfall/soil moisture, citizen science, multi-temporal satellite observations, seismicity, vegetation dynamics, InSAR/GPS deformation and hybrid models.

### 2. Mandal, Saha & Mandal (2021) — Rorachu River Basin, Sikkim
**Applying deep learning and benchmark machine learning algorithms for landslide susceptibility modelling in Rorachu river basin of Sikkim Himalaya, India.** Geoscience Frontiers 12, 101203. DOI: 10.1016/j.gsf.2021.101203.

Key lessons used:
- Twenty conditioning factors were evaluated; rainfall emerged as the dominant trigger.
- Feature screening/multicollinearity matters: VIF/TOL and Information Gain Ratio were used before modeling.
- Hydrological/geomorphic variables such as STI, LULC, elevation, soil, road proximity and slope add important context.
- CNN performed best in that study, but the paper also warns that neural models depend strongly on input structure/design and can contain unrecognized errors.
- Missing detailed soil/geological properties were a stated limitation.

### 3. Poddar & Roy (2026) — Namchi, Sikkim
**Assessing landslide susceptibility mapping in the Sikkim Himalayas using an ensemble machine learning approach.** Discover Geoscience 4:14. DOI: 10.1007/s44288-025-00375-4.

Key lessons used:
- Six diverse models plus a meta-classifier were compared on 23 environmental factors.
- Hyperparameter tuning, 5-fold CV, RFE and Shapley-style interpretation strengthen the modeling workflow.
- Ensemble/meta-learning can be more dependable than one model.
- The paper highlights Physics-Informed ML as a next-generation direction for improving physical consistency and transferability.
- High accuracy alone is insufficient in imbalanced hazard problems; precision/recall/F1 and other measures are important.

---

## B. Additional research consulted

### NASA LHASA v2 / Stanley et al. (2021)
NASA's Landslide Hazard Assessment for Situational Awareness v2 uses XGBoost with **current rainfall, antecedent rainfall, soil wetness and static terrain/geology**. The framework also supports probabilistic near-real-time nowcasting and forecast extensions. This directly motivated PRAHARI's multi-timescale dynamic trigger layer and monotonic constraints.

### Kang et al. (2024), Scientific Reports — Yunnan rainfall-induced early warning
This work combines static susceptibility with dynamic rain and uses an **11-day effective rainfall memory with K=0.84**. PRAHARI now computes this as a *research-inspired screening feature*, not an official NER threshold.

### Tanaka & Goto (2026) — Dynamic susceptibility
The study shows why event-time-aligned soil moisture and rainfall are valuable: dynamic trigger factors produce event-specific patterns, while terrain predisposition is more time-invariant. This supports PRAHARI's explicit **susceptibility vs dynamic trigger** decomposition and time trajectory.

### Recent spatial-validation studies (2025–2026)
Recent work shows that ordinary random cross-validation can overestimate geospatial model performance because nearby training/test samples share spatial structure. PRAHARI's synthetic trainer therefore demonstrates **group-blocked validation**, while the production roadmap calls for true spatial/temporal validation on real NER inventories.

### Hybrid CNN–ensemble work (2026)
Recent CNN–LightGBM/XGBoost studies show that spatial raster features can improve tabular ensembles when trained with rigorous spatial validation. PRAHARI does **not** add a decorative CNN today because its current runtime inputs are point/tabular features, not validated multi-band raster patches. A CNN feature extractor belongs in the future EO pipeline after real DEM/geology/LULC/Sentinel raster stacks are available.

### Physics-Informed Neural Networks (2026)
Emerging work couples Richards' infiltration equation with neural models to predict soil-moisture evolution under rainfall. PRAHARI does not pretend to solve a geotechnical PDE today; instead v6 adds monotonic physical constraints and a transparent fallback, while PIML/PINN is retained as the later field-validated research path.

---

## C. Gap matrix: papers vs old PRAHARI vs v6

| Research expectation | Old v5 gap | PRAHARI v6 implementation |
|---|---|---|
| Ensemble learning | One bootstrap RF | Weighted XGBoost + LightGBM + RF ensemble |
| Explainability | Global RF feature importance only | Local XGBoost TreeSHAP + global importance + model votes |
| Dynamic vs static risk | Mostly one fused score | Separate susceptibility, dynamic trigger and current hazard |
| Antecedent hydrology | 24h rainfall only | 6h, 24h, 72h antecedent, 11-day effective rain, peak hourly rain |
| Forecast warning | Weather forecast displayed, not directly risk-scored | NOW / +6h / +24h forecast-risk trajectory endpoint and UI |
| Physical plausibility | Synthetic labels could learn odd directions | Monotonic constraints on key hydrologic/terrain features |
| Model uncertainty | No uncertainty display | Inter-model disagreement + ensemble agreement indicator |
| Validation discipline | Simple synthetic validation | 4-fold GroupKFold over synthetic pseudo-regions; explicitly not real-world accuracy |
| Risk thresholds | UI/model mismatch | Unified 35/60/80 bands frontend + backend |
| Provenance | Some prototype labels | Dedicated research model card + input/provenance warnings |
| Disaster workflow | Papers mainly end at susceptibility maps | PRAHARI adds alerts, acknowledgement, citizen reports, GIS and infrastructure response |
| Offline reliability | Already strong | Preserved deterministic weather/model fallbacks |

---

## D. Features deliberately NOT fabricated
The papers use richer geospatial variables than the current hackathon data. The following are **not claimed as live inputs** until real datasets are connected:

- lithology and geologic strength
- lineament/fault density and distance
- slope aspect and curvature
- geomorphology
- drainage density
- TWI / SPI / STI
- verified road distance / road-cut geometry
- real LULC change
- soil texture, depth, permeability, cohesion and pore pressure
- seismicity / fault reactivation
- Sentinel-1 InSAR deformation
- GNSS / ground displacement
- physical soil/rain/pore-pressure sensors
- CNN-derived raster embeddings

Adding fake constants for these would make the model look more sophisticated while making it scientifically weaker. The production path is to ingest real raster/vector layers and retrain on a validated inventory.

---

## E. New v6 algorithm

### Inputs
1. 24h rainfall
2. 72h antecedent rainfall
3. 11-day effective rainfall (decay K=0.84)
4. soil-wetness proxy
5. slope
6. elevation
7. historical susceptibility
8. NDVI
9. next-24h forecast rain
10. maximum hourly rain in the latest 24h

### Three-stage reasoning
**Stage 1 — Static susceptibility:** terrain/history/vegetation describe how predisposed a slope is.  
**Stage 2 — Dynamic trigger:** rain accumulation, wetness, future rain and peak hourly intensity describe how close the hydrologic state is to failure-triggering conditions.  
**Stage 3 — Ensemble hazard:** XGBoost, LightGBM and RF probabilities are combined to obtain current hazard.

### Ensemble
`P = 0.45·P_XGB + 0.35·P_LGBM + 0.20·P_RF`

The weights are hackathon research-design choices, not regionally optimized production weights.

### Physical consistency
XGBoost/LightGBM monotonic constraints prevent higher rainfall, antecedent rain, soil wetness, slope, historical risk, forecast rain or peak rain from spuriously lowering hazard. NDVI is constrained in the opposite direction. Elevation remains unconstrained because its relationship is location-dependent.

### Explainability
- **Global importance:** which features matter most across the shipped bootstrap model.
- **Local TreeSHAP:** which features raised/reduced *this* prediction.
- **Model votes:** XGBoost, LightGBM and RF probabilities.
- **Uncertainty:** standard deviation among model probabilities.

### Warning trajectory
PRAHARI uses current wetness/state and forecast rainfall to produce NOW, +6h and +24h research projections. It is a scenario trajectory, not an official deterministic landslide forecast.

---

## F. What still prevents us from claiming a research-grade operational model

1. **No validated NER training inventory is bundled.** The shipped 6,000-row dataset is synthetic physics-guided bootstrap data.
2. **No true spatial raster sampling pipeline yet.** Real lithology, drainage, LULC, lineaments and road proximity must be extracted consistently at a common grid resolution.
3. **No real spatial/temporal external validation yet.** Synthetic GroupKFold only demonstrates the method.
4. **No calibrated probability / operational thresholds.** Risk bands are decision-support bands for the SIH prototype.
5. **No physical sensors or InSAR deformation feed.** Those are future production inputs.
6. **No field authority validation.** Alerts are prototype decision support, not official evacuation orders.

These limitations should be stated, because the research papers themselves show that data provenance, spatial validation and field measurements are major sources of uncertainty.

---

## G. Highest-value next implementation after the hackathon

1. Build a verified **NER landslide inventory** from GSI/BHUKOSH, NASA catalog, Sentinel/Google Earth verification and field/citizen verification.
2. Build a common raster grid using DEM-derived slope/aspect/curvature/TWI/SPI/STI, lithology/lineaments, LULC/NDVI and distance-to-road/drainage.
3. Add **GPM IMERG** rainfall and **SMAP** soil wetness as independent satellite-derived hydrologic sources.
4. Train XGBoost/LightGBM/ensemble with **spatial block CV + temporal holdout**, report AUROC, PR-AUC, Recall, F1, Brier/ECE and false-negative rate.
5. Calibrate probabilities and choose warning thresholds based on the cost of missed landslides vs false alarms.
6. Add Sentinel-1 InSAR / GNSS / field displacement where available.
7. After real raster data exists, compare standalone boosting with **CNN–LightGBM / CNN–XGBoost**.
8. For research-grade hydrology, evaluate a physics-informed infiltration model rather than only statistical wetness proxies.

---

## H. Judge-safe one-line summary
> PRAHARI v6 combines research-grade ideas—ensemble boosting, antecedent hydrology, explainability, physically constrained prediction and spatial-validation discipline—with a complete operational workflow of GIS, alerts, citizen intelligence and infrastructure response; the current model remains transparently labelled as a hackathon bootstrap until real NER inventories and field/satellite conditioning layers are connected.
