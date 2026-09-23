# 5-Minute Hackathon Demo Checklist

## Before judges arrive
- [ ] Backend running at 127.0.0.1:8000
- [ ] Frontend running at localhost:5173
- [ ] `/docs` opens
- [ ] Satellite tile appears (internet available)
- [ ] Browser notification permission enabled
- [ ] Speaker volume at a comfortable level
- [ ] Gangtok selected
- [ ] PPT and screenshots available offline as backup

## Live flow
1. **Problem:** mountainous NER + rainfall + vulnerable roads/settlements need earlier risk intelligence.
2. **Overview:** show fused risk and regional exposure.
3. **Satellite:** show imagery/terrain, overlays and selected-zone intelligence.
4. **Critical event:** run emergency warning demo.
5. **Alert:** show toast/browser warning, then alert timeline + action + acknowledgement.
6. **AI:** run Cloudburst scenario; explain why factors drive the score.
7. **Citizen report:** field evidence enters command center and can escalate.
8. **Infrastructure:** route restriction + exposed communities.
9. **Close:** production pipeline = validated satellite + DEM + weather/IoT + calibrated ML + government gateways.

## One sentence to remember
> PRAHARI does not depend on one sensor: it fuses terrain, rainfall, ground observations, historical susceptibility and satellite context into an actionable location-specific warning workflow.


## ML check
- Open `http://127.0.0.1:8000/api/ml/status` and confirm `model_loaded: true`.
- Open `/api/ml/feature-importance` to show the model's top factors.
- In AI Analysis, use the cloudburst scenario and confirm a HIGH/CRITICAL result triggers an alert.
- Say clearly: bundled Random Forest is a bootstrap integration model; production calibration uses validated landslide inventories and remote-sensing/field observations.
