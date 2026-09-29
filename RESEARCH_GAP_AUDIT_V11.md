# PRAHARI v11 Research Gap Audit

## Scope
This audit compares PRAHARI against the supplied flash-flood literature spanning susceptibility mapping, operational flash-flood guidance, precipitation evaluation, hydrological/hydrodynamic modelling, uncertainty quantification, class imbalance, interpretable ML, and remote sensing.

## Research-backed gaps

| Area | Literature signal | PRAHARI gap | v11 action |
|---|---|---|---|
| Watershed-scale forcing | SAsiaFFGS uses basin mean areal precipitation, gauge/radar/satellite inputs, soil moisture accounting and short-term threat products | Point weather samples were being treated as the primary flood driver | Live-only workflow retained; synthetic replay removed. Catchment configuration is now mandatory so point data cannot masquerade as a configured basin |
| Real event inventory | Himalayan susceptibility studies build flood/non-flood inventories from historical records and SAR/EO products | No verified multi-region inventory in the operational flood model | Synthetic/default catchment data removed from the flood workflow; inventory provenance must be configured |
| Terrain/hydrology factors | Studies use elevation, slope, aspect, curvature, TWI, SPI/STI, drainage density, lithology, LULC, soil, distance to streams/roads and rainfall | Current flood screen does not ingest a defensible multi-factor raster stack | Kept out of operational probability claims until a real pipeline and validation set exist |
| Spatial validation | Recent work shows random train/test splits inflate performance and recommends basin/block holdout | Existing research ensemble is bootstrap/synthetic and not operationally valid | Research ensemble removed from the normal settings UI; it must not be presented as operational intelligence |
| Class imbalance | Flash-flood occurrence data are strongly imbalanced; class-distribution strategies materially change results | No validated imbalance strategy in the flood pipeline | Required for the next trained model; event recall, precision, PR-AUC and false alarms must be reported |
| Interpretability | SHAP and feature importance are used to explain flood susceptibility models | PRAHARI currently explains only the threshold screen | Preserve transparent threshold reasons; any trained model must add SHAP/local explanations before operational surfacing |
| Uncertainty | Conformal prediction/uncertainty intervals distinguish confident from uncertain susceptibility estimates | No calibrated uncertainty interval | Do not expose model probability until calibration + uncertainty coverage are validated |
| Watershed connectivity | Graph/watershed-aware modelling captures upstream/downstream dependencies | Pixel/point screens ignore network propagation | Add watershed graph only when hydrography and basin topology are authoritative |
| Hydrological routing | HEC-HMS and SAsiaFFGS demonstrate rainfall-runoff / soil-moisture accounting | No runoff routing or discharge transformation | Required before claiming flood hydrograph or arrival time |
| Hydrodynamic inundation | HEC-RAS 2D rainfall-on-topography can reproduce local inundation and building impacts | No depth/velocity/inundation solver | Keep susceptibility/early-warning distinct from inundation; add only with DEM, roughness, channels and event validation |
| Multi-source precipitation | IMD, radar, GPM/IMERG, ERA5/WRF and gauge products have different skill in mountains | Single-provider dependence creates uncertainty | Source fusion and bias checking remain a high-priority data-engineering task |
| Cryosphere/compound hazards | Himalayan flash floods include GLOF, snowmelt, landslide-dam and debris-flow mechanisms | Rainfall-only logic misses non-pluvial triggers | GLOF/snowmelt/landslide-dam trigger modules require authoritative source feeds |
| Exposure | Recent hydrodynamic work validates against buildings/infrastructure and estimates impact | Prototype asset/route data are not defensible | Prototype infrastructure/routing panels removed from normal settings UI |
| Geographic scope | Literature spans Uttarakhand, Himachal Pradesh, Himalayan foreland and other mountainous settings | UI and text were Northeast-India-centric | User-facing scope changed to hilly regions; NER-specific copy removed |

## Bugs and product defects corrected
- Removed operational replay/synthetic mode from flash-flood API and dashboard.
- Removed automatic synthetic catchment creation. A flood assessment now requires an operator-configured catchment.
- Removed the live/replay toggle from the command centre.
- Removed NER-only wording from the primary UI and API description.
- Removed automation-looking technical instructions, research-model warnings, prototype route/asset blocks and licensing prose from the user dashboard.
- Simplified Data & Settings to operational source, health, authorization and notification controls.
- Reworked Flash Flood Intelligence into KPI cards, map, hydrometeorological drivers, threshold windows and record history, following the visual hierarchy of the supplied command-centre UI reference.
- Updated flood tests so unconfigured areas fail closed and synthetic replay is no longer a valid path.

## Scientific features intentionally not faked
The following are not generated from placeholder data: calibrated flood probabilities, inundation polygons, safe routes, exposure counts, watershed-average precipitation, discharge hydrographs, validated lead time, conformal intervals, SHAP explanations, GLOF state, or building-level loss. These require real datasets and validation.

## Next implementation tranche
1. Persist arbitrary monitored hilly-region locations rather than relying on the legacy location seed list.
2. Add authoritative DEM-derived watershed delineation and terrain factors.
3. Add GPM IMERG plus gauge/radar/NWP rainfall fusion and basin-average precipitation.
4. Build a verified flood/non-flood event inventory and spatial/temporal cross-validation harness.
5. Train RF/XGBoost/LightGBM baseline plus watershed-aware model; calibrate probabilities and conformal uncertainty.
6. Add hydrological routing before any lead-time claim and HEC-RAS-style inundation only where geometry/roughness data are available.
