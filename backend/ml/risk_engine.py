from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
import numpy as np

BASE = Path(__file__).resolve().parent
FEATURES = [
    "rainfall_24h", "antecedent_rainfall_72h", "cumulative_rainfall_7d",
    "effective_rainfall_11d", "soil_moisture", "slope", "elevation",
    "historical_risk", "ndvi", "rain_forecast_24h", "max_hourly_rain_24h",
    "season_sin", "season_cos",
]
MODELS = None
LOAD_ERROR = None
METADATA = {"model_type":"transparent hybrid fallback","provenance":"Deterministic research-synthesis fallback","feature_importance":{}}


def clamp(v, lo=0.0, hi=1.0): return min(max(float(v), lo), hi)
def sigmoid(z): return 1.0/(1.0+math.exp(-max(-30,min(30,z))))

def _load():
    global MODELS, METADATA, LOAD_ERROR
    try:
        import joblib
        meta = BASE / "research_model_metadata.json"
        if meta.exists(): METADATA = json.loads(meta.read_text(encoding="utf-8"))
        model = BASE / "research_ensemble.joblib"
        if model.exists(): MODELS = joblib.load(model)
    except Exception as exc:
        LOAD_ERROR = str(exc); MODELS = None
_load()


def _season(vals):
    month = int(vals.get("month") or datetime.now().month)
    month = max(1,min(12,month))
    return math.sin(2*math.pi*(month-1)/12), math.cos(2*math.pi*(month-1)/12), month


def _prepare(vals):
    rain24=float(vals.get("rainfall_24h", vals.get("rainfall", 0)))
    ss,cc,month=_season(vals)
    ant=float(vals.get("antecedent_rainfall_72h", rain24*2.15))
    rain7=float(vals.get("cumulative_rainfall_7d", max(ant*1.8,rain24*4.2)))
    eff=float(vals.get("effective_rainfall_11d", max(rain7*.95,rain24*3.1)))
    return {
        "rainfall_24h":rain24,"antecedent_rainfall_72h":ant,
        "cumulative_rainfall_7d":rain7,"effective_rainfall_11d":eff,
        "soil_moisture":float(vals.get("soil_moisture",50)),"slope":float(vals.get("slope",25)),
        "elevation":float(vals.get("elevation",1200)),"historical_risk":float(vals.get("historical_risk",.5)),
        "ndvi":float(vals.get("ndvi",.65)),"rain_forecast_24h":float(vals.get("rain_forecast_24h",0)),
        "max_hourly_rain_24h":float(vals.get("max_hourly_rain_24h",max(0,rain24/10))),
        "season_sin":ss,"season_cos":cc,"month":month,
        "rainfall_intensity":float(vals.get("rainfall_intensity",0) or 0),
        "tilt_deg":float(vals.get("tilt_deg",0) or 0),"vibration_g":float(vals.get("vibration_g",0) or 0),
        "pore_pressure_kpa":float(vals.get("pore_pressure_kpa",0) or 0),
        "displacement_mm":float(vals.get("displacement_mm",0) or 0),
        "telemetry_quality":clamp(vals.get("telemetry_quality",0) or 0),
    }


def _susceptibility(v):
    slope=clamp(v["slope"]/60); hist=clamp(v["historical_risk"]); elev=clamp(v["elevation"]/3000); veg=clamp((.82-v["ndvi"])/.82)
    return sigmoid(-3.15+2.55*slope+1.75*hist+.28*elev+.65*veg)


def _trigger(v):
    return sigmoid(-4.65 + 1.00*clamp(v["rainfall_24h"]/180) + 1.05*clamp(v["antecedent_rainfall_72h"]/360) +
        .75*clamp(v["cumulative_rainfall_7d"]/850) + .85*clamp(v["effective_rainfall_11d"]/900) +
        1.55*clamp(v["soil_moisture"]/100) + .65*clamp(v["rain_forecast_24h"]/180) +
        .95*clamp(v["max_hourly_rain_24h"]/45) + .18*v["season_sin"])


def _fallback(v):
    s=_susceptibility(v); t=_trigger(v)
    return sigmoid(-4.15 + 2.15*s + 2.30*t + 1.10*clamp(v["rainfall_24h"]/220)*clamp(v["soil_moisture"]/100) +
                   .70*clamp(v["antecedent_rainfall_72h"]/500)*clamp(v["slope"]/60) +
                   .55*clamp(v["cumulative_rainfall_7d"]/1000)*clamp(v["soil_moisture"]/100) +
                   .58*clamp(v["max_hourly_rain_24h"]/60)*clamp(v["slope"]/60))


def _level(p):
    if p>=.80:return "CRITICAL"
    if p>=.60:return "HIGH"
    if p>=.35:return "MODERATE"
    return "LOW"


def _rainfall_regime(v):
    peak=v["max_hourly_rain_24h"]
    rain24=max(v["rainfall_24h"],1)
    saturation=clamp(.46*v["soil_moisture"]/100 + .28*v["antecedent_rainfall_72h"]/450 + .26*v["cumulative_rainfall_7d"]/1000)
    if peak>=22 and peak/rain24>=.17: regime="SHORT_INTENSE"
    elif saturation>=.62 or (v["cumulative_rainfall_7d"]>=350 and peak<22): regime="LONG_SATURATING"
    elif v["rainfall_24h"]<25 and saturation<.35: regime="QUIET"
    else: regime="MIXED"
    return regime, round(saturation*100,1)


def _precursor(v):
    # Screening fusion of field telemetry. It intentionally does not claim to be
    # persistent homology or a calibrated geotechnical failure-time predictor.
    components=[]
    def add(name,val,w):
        if val>0: components.append((name,clamp(val),w))
    add("tilt",abs(v["tilt_deg"])/4.0,.25)
    add("vibration",v["vibration_g"]/.5,.10)
    add("pore_pressure",v["pore_pressure_kpa"]/100.0,.25)
    add("displacement",v["displacement_mm"]/12.0,.30)
    add("local_rain_intensity",v["rainfall_intensity"]/45.0,.10)
    if not components:return 0.0,[],False
    raw=sum(x*w for _,x,w in components)/max(sum(w for _,_,w in components),1e-9)
    q=max(.35,v["telemetry_quality"])
    score=clamp(raw*q)
    ranked=sorted([{"name":n,"severity_pct":round(x*100,1)} for n,x,_ in components],key=lambda x:x["severity_pct"],reverse=True)
    return score,ranked,True


def _xgb_shap(model,row):
    try:
        import xgboost as xgb
        dm=xgb.DMatrix(row,feature_names=FEATURES)
        arr=model.get_booster().predict(dm,pred_contribs=True)[0]; contrib=arr[:-1]; total=max(float(np.sum(np.abs(contrib))),1e-9)
        out=[]
        for name,val in zip(FEATURES,contrib):
            out.append({"feature":name,"contribution":round(float(val),4),"direction":"raises" if val>0 else "reduces","share_pct":round(abs(float(val))/total*100,1)})
        return sorted(out,key=lambda x:x["share_pct"],reverse=True)
    except Exception:return []


def predict(vals):
    v=_prepare(vals); row=np.array([[v[k] for k in FEATURES]],dtype=float); model_probs={}; shap=[]; used=False
    if MODELS:
        try:
            import pandas as pd
            X=pd.DataFrame(row,columns=FEATURES)
            for name,model in MODELS.items(): model_probs[name]=float(model.predict_proba(X)[0,1])
            p=.45*model_probs["xgboost"]+.35*model_probs["lightgbm"]+.20*model_probs["random_forest"]
            shap=_xgb_shap(MODELS["xgboost"],X); used=True
        except Exception:
            p=_fallback(v); model_probs={"fallback":p}
    else:
        p=_fallback(v); model_probs={"fallback":p}

    raw_p=clamp(p); susceptibility=_susceptibility(v); trigger=_trigger(v)
    precursor,precursor_factors,telemetry_used=_precursor(v)
    regime,soil_water_stress=_rainfall_regime(v)

    guardrail_floor=0.0; reasons=[]
    if trigger>=.90 and susceptibility>=.72: guardrail_floor=max(guardrail_floor,.84);reasons.append("very high hydrologic trigger + high terrain susceptibility")
    elif trigger>=.80 and susceptibility>=.62: guardrail_floor=max(guardrail_floor,.68);reasons.append("high hydrologic trigger + susceptible terrain")
    if v["effective_rainfall_11d"]>=650 and v["soil_moisture"]>=88 and v["slope"]>=35:
        guardrail_floor=max(guardrail_floor,.80);reasons.append("extreme effective rainfall + saturated steep slope")
    if telemetry_used and precursor>=.78:
        guardrail_floor=max(guardrail_floor,.86);reasons.append("strong ground-deformation / pore-pressure precursor screen")
    elif telemetry_used and precursor>=.58:
        guardrail_floor=max(guardrail_floor,.68);reasons.append("elevated field precursor screen")
    p=clamp(max(raw_p,guardrail_floor))

    probs=list(model_probs.values()); model_std=float(np.std(probs)) if len(probs)>1 else 0.0
    # Input-sensitivity ensemble: perturb plausible measurement/model inputs and
    # re-run the trained ensemble. This operationalizes the uploaded uncertainty
    # literature without pretending the resulting envelope is a calibrated CI.
    sensitivity=[]
    if used and MODELS:
        try:
            import pandas as pd
            variants=[]
            for rain_f,soil_d,slope_d in [(0.90,0,0),(1.10,0,0),(1.0,-5,0),(1.0,5,0),(1.0,0,-2),(1.0,0,2),(.92,-3,-1),(1.08,3,1)]:
                vv=dict(v); vv['rainfall_24h']*=rain_f; vv['antecedent_rainfall_72h']*=rain_f; vv['cumulative_rainfall_7d']*=rain_f; vv['effective_rainfall_11d']*=rain_f
                vv['soil_moisture']=min(100,max(0,vv['soil_moisture']+soil_d)); vv['slope']=min(90,max(0,vv['slope']+slope_d))
                variants.append(vv)
            XX=pd.DataFrame([[vv[k] for k in FEATURES] for vv in variants],columns=FEATURES)
            pp={}
            for name,model in MODELS.items(): pp[name]=model.predict_proba(XX)[:,1]
            sensitivity=list(.45*pp['xgboost']+.35*pp['lightgbm']+.20*pp['random_forest'])
        except Exception:
            sensitivity=[]
    input_std=float(np.std(sensitivity)) if sensitivity else 0.0
    data_penalty=3.0 if telemetry_used and v["telemetry_quality"]>=.8 else (5.0 if telemetry_used else 7.0)
    combined_std=math.sqrt(model_std**2+input_std**2)
    margin=max(5.0,min(24.0,1.64*combined_std*100+data_penalty))
    risk_interval=[round(max(0,p*100-margin),1),round(min(100,p*100+margin),1)]
    sensitivity_interval=[round(float(min(sensitivity))*100,1),round(float(max(sensitivity))*100,1)] if sensitivity else None
    uncertainty=combined_std*100; agreement=round(max(50.0,min(99.0,100.0-uncertainty*2.5-data_penalty*.25)),1)

    threshold_mm=max(85.0,220.0-110.0*susceptibility); threshold_ratio=v["effective_rainfall_11d"]/threshold_mm
    fi=METADATA.get("feature_importance") or {}
    labels={
        "rainfall_24h":"Rainfall (24h)","antecedent_rainfall_72h":"Antecedent rain (72h)","cumulative_rainfall_7d":"Cumulative rain (7d)",
        "effective_rainfall_11d":"Effective rain (11d)","soil_moisture":"Soil wetness","slope":"Slope","elevation":"Elevation",
        "historical_risk":"Historical susceptibility","ndvi":"Vegetation / NDVI","rain_forecast_24h":"Forecast rain (24h)",
        "max_hourly_rain_24h":"Peak hourly rain","season_sin":"Seasonality (sin)","season_cos":"Seasonality (cos)",
    }
    norms={
        "rainfall_24h":clamp(v["rainfall_24h"]/220),"antecedent_rainfall_72h":clamp(v["antecedent_rainfall_72h"]/500),
        "cumulative_rainfall_7d":clamp(v["cumulative_rainfall_7d"]/1100),"effective_rainfall_11d":clamp(v["effective_rainfall_11d"]/1100),
        "soil_moisture":clamp(v["soil_moisture"]/100),"slope":clamp(v["slope"]/60),"elevation":clamp(v["elevation"]/3000),
        "historical_risk":clamp(v["historical_risk"]),"ndvi":clamp((.82-v["ndvi"])/.82),"rain_forecast_24h":clamp(v["rain_forecast_24h"]/220),
        "max_hourly_rain_24h":clamp(v["max_hourly_rain_24h"]/60),"season_sin":abs(v["season_sin"]),"season_cos":abs(v["season_cos"]),
    }
    factors=[]
    for k,val in norms.items():
        imp=float(fi.get(k,0)); factors.append({"name":labels[k],"feature":k,"value":round(val*100),"model_importance":round(imp,3),"weight":"high" if imp>=.12 else ("medium" if imp>=.06 else "supporting")})
    factors.sort(key=lambda x:x["model_importance"],reverse=True)

    return {
        "probability":round(p,4),"raw_ensemble_probability":round(raw_p,4),"level":_level(p),"factors":factors,
        "physics_guardrail_applied":bool(guardrail_floor and p>raw_p+1e-9),"physics_guardrail_floor":round(guardrail_floor,4),
        "physics_guardrail_reason":"; ".join(reasons) if reasons else None,
        "engine":"research-synthesis-ensemble" if used else "research-synthesis-fallback","model_loaded":used,"provenance":METADATA.get("provenance"),
        "susceptibility_probability":round(susceptibility,4),"trigger_probability":round(trigger,4),
        "ensemble_uncertainty_pct":round(uncertainty,2),"ensemble_agreement_pct":agreement,
        "model_spread_pct":round(model_std*100,2),"input_sensitivity_spread_pct":round(input_std*100,2),
        "input_sensitivity_interval_pct":sensitivity_interval,
        "decision_interval_pct":risk_interval,"decision_interval_note":"Indicative envelope combines model disagreement, input-sensitivity perturbations and a data-availability penalty; not a calibrated statistical confidence interval.",
        "model_probabilities":{k:round(vv,4) for k,vv in model_probs.items()},"shap_local":shap,
        "rainfall_regime":regime,"soil_water_stress_pct":soil_water_stress,
        "precursor_screen_pct":round(precursor*100,1),"precursor_factors":precursor_factors,"telemetry_used":telemetry_used,
        "rainfall_threshold_context":{"effective_rainfall_mm":round(v["effective_rainfall_11d"],1),"research_screening_threshold_mm":round(threshold_mm,1),
            "ratio":round(threshold_ratio,2),"state":"EXCEEDED" if threshold_ratio>=1 else ("APPROACHING" if threshold_ratio>=.75 else "BELOW"),
            "note":"Trigger-condition screening only. It is NOT an IDF return-period or occurrence probability."},
        "inputs_used":{k:(round(float(vv),3) if isinstance(vv,(int,float)) else vv) for k,vv in v.items()},
    }


def status():
    return {"model_loaded":MODELS is not None,"engine":"research-synthesis-ensemble" if MODELS is not None else "research-synthesis-fallback","load_error":LOAD_ERROR,**METADATA}
