from __future__ import annotations

"""Train PRAHARI v8's research-synthesis hazard ensemble.

The shipped rows are physics-guided bootstrap scenarios used only to exercise the
software pipeline. They are NOT a field-validated Northeast India landslide
inventory and the diagnostics below are not real-world accuracy claims.
"""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, f1_score, recall_score, precision_score, brier_score_loss
from sklearn.model_selection import GroupKFold

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

BASE = Path(__file__).resolve().parent
SEED = 26001
FEATURES = [
    "rainfall_24h", "antecedent_rainfall_72h", "cumulative_rainfall_7d",
    "effective_rainfall_11d", "soil_moisture", "slope", "elevation",
    "historical_risk", "ndvi", "rain_forecast_24h", "max_hourly_rain_24h",
    "season_sin", "season_cos",
]
# 0 = unconstrained. Rain/soil/slope/history/forecast are constrained in the
# physically expected direction; seasonality is deliberately unconstrained.
MONOTONE = [1, 1, 1, 1, 1, 1, 0, 1, -1, 1, 1, 0, 0]


def clamp(x, lo=0.0, hi=1.0):
    return np.minimum(np.maximum(x, lo), hi)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def generate_bootstrap_dataset(n=7200, seed=SEED):
    rng = np.random.default_rng(seed)
    region = rng.integers(0, 8, size=n)
    month = rng.integers(1, 13, size=n)
    season_sin = np.sin(2*np.pi*(month-1)/12)
    season_cos = np.cos(2*np.pi*(month-1)/12)

    regional_rain = np.array([1.05, 1.15, .95, 1.20, 1.10, .90, 1.12, .88])[region]
    regional_terrain = np.array([1.15, 1.10, 1.05, 1.00, 1.12, .92, 1.08, .85])[region]
    # Synthetic monsoon-like seasonality only to make the feature path testable.
    monsoon = 1.0 + .28*np.maximum(0, np.sin(2*np.pi*(month-4)/12))

    rain24 = clamp(rng.gamma(2.0, 45.0, n) * regional_rain * monsoon, 0, 440)
    ant72 = clamp(rain24 * rng.uniform(1.3, 3.4, n) + rng.gamma(1.4, 24, n), 0, 900)
    rain7 = clamp(ant72 * rng.uniform(1.25, 2.2, n) + rng.gamma(1.3, 55, n), 0, 1700)
    eff11 = clamp(rain7 * rng.uniform(.75, 1.45, n) + rng.gamma(1.25, 36, n), 0, 1900)
    soil = clamp(20 + 0.085*ant72 + 0.022*rain7 + rng.normal(0, 12, n), 8, 100)
    slope = clamp(rng.beta(2.2, 2.4, n) * 66 * regional_terrain, 1, 75)
    elevation = clamp(rng.gamma(2.0, 650, n), 40, 4200)
    hist = clamp(rng.beta(2.0, 2.0, n) * regional_terrain, 0, 1)
    ndvi = clamp(rng.normal(.66 - .04*np.maximum(0, season_sin), .15, n), .05, .95)
    forecast24 = clamp(rng.gamma(1.7, 32, n) * regional_rain * monsoon, 0, 360)
    max1h = clamp(rain24 * rng.uniform(.04, .30, n) + rng.gamma(1.2, 2.0, n), 0, 100)

    static_z = -3.15 + 2.55*clamp(slope/60) + 1.75*hist + .28*clamp(elevation/3000) + .65*clamp((.82-ndvi)/.82)
    static_p = sigmoid(static_z)
    dyn_z = (-4.65 + 1.00*clamp(rain24/180) + 1.05*clamp(ant72/360) +
             .75*clamp(rain7/850) + .85*clamp(eff11/900) + 1.55*clamp(soil/100) +
             .65*clamp(forecast24/180) + .95*clamp(max1h/45) + .18*season_sin)
    trigger_p = sigmoid(dyn_z)

    z = (-4.15 + 2.15*static_p + 2.30*trigger_p +
         1.10*clamp(rain24/220)*clamp(soil/100) +
         .70*clamp(ant72/500)*clamp(slope/60) +
         .55*clamp(rain7/1000)*clamp(soil/100) +
         .58*clamp(max1h/60)*clamp(slope/60))
    event_p = clamp(sigmoid(z), .005, .995)
    y = rng.binomial(1, event_p)

    return pd.DataFrame({
        "rainfall_24h": rain24,
        "antecedent_rainfall_72h": ant72,
        "cumulative_rainfall_7d": rain7,
        "effective_rainfall_11d": eff11,
        "soil_moisture": soil,
        "slope": slope,
        "elevation": elevation,
        "historical_risk": hist,
        "ndvi": ndvi,
        "rain_forecast_24h": forecast24,
        "max_hourly_rain_24h": max1h,
        "season_sin": season_sin,
        "season_cos": season_cos,
        "month": month,
        "region_group": region,
        "event_probability_bootstrap": event_p,
        "landslide_event": y,
    })


def build_models(seed=SEED):
    return {
        "xgboost": XGBClassifier(
            n_estimators=140, max_depth=4, learning_rate=.055,
            subsample=.82, colsample_bytree=.88, min_child_weight=3,
            reg_lambda=2.0, reg_alpha=.08, objective="binary:logistic",
            eval_metric="logloss", random_state=seed, n_jobs=-1,
            monotone_constraints=tuple(MONOTONE),
        ),
        "lightgbm": LGBMClassifier(
            n_estimators=140, max_depth=5, num_leaves=24, learning_rate=.05,
            subsample=.84, colsample_bytree=.88, reg_lambda=1.5, reg_alpha=.06,
            random_state=seed, verbosity=-1, monotone_constraints=MONOTONE,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=220, max_depth=12, min_samples_leaf=4,
            class_weight="balanced_subsample", random_state=seed, n_jobs=-1,
            max_features=.72,
        ),
    }


def ensemble_prob(models, X):
    probs = {name: model.predict_proba(X)[:, 1] for name, model in models.items()}
    p = .45*probs["xgboost"] + .35*probs["lightgbm"] + .20*probs["random_forest"]
    return p, probs


def metrics(y, p, threshold=.5):
    pred = (p >= threshold).astype(int)
    recall = recall_score(y, pred, zero_division=0)
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall), 4),
        "false_negative_rate": round(float(1-recall), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def main():
    df = generate_bootstrap_dataset()
    df.to_csv(BASE / "research_bootstrap_training_data.csv", index=False)
    X, y, groups = df[FEATURES], df["landslide_event"].astype(int), df["region_group"].astype(int)

    gkf = GroupKFold(n_splits=4)
    oof = np.zeros(len(df), dtype=float)
    fold_metrics = []
    for fold, (tr, te) in enumerate(gkf.split(X, y, groups=groups), start=1):
        fold_models = build_models(SEED + fold)
        for model in fold_models.values(): model.fit(X.iloc[tr], y.iloc[tr])
        p_fold, _ = ensemble_prob(fold_models, X.iloc[te])
        oof[te] = p_fold
        fm = metrics(y.iloc[te], p_fold); fm["fold"] = fold
        fm["held_out_groups"] = sorted(set(groups.iloc[te].astype(int).tolist()))
        fold_metrics.append(fm)

    cv_summary = metrics(y, oof)
    cv_summary["folds"] = fold_metrics
    cv_summary["scheme"] = "4-fold GroupKFold over 8 synthetic pseudo-regions"

    models = build_models(SEED)
    for model in models.values(): model.fit(X, y)
    joblib.dump(models, BASE / "research_ensemble.joblib")

    xgb_imp = models["xgboost"].feature_importances_
    rf_imp = models["random_forest"].feature_importances_
    global_imp = .7*xgb_imp + .3*rf_imp
    global_imp = global_imp / max(global_imp.sum(), 1e-9)
    importance = {f: round(float(v), 4) for f, v in zip(FEATURES, global_imp)}

    metadata = {
        "project": "PRAHARI v8 Research Synthesis",
        "model_type": "Monotonic XGBoost + LightGBM + Random Forest weighted ensemble",
        "models": ["XGBoost", "LightGBM", "RandomForest"],
        "weights": {"xgboost": .45, "lightgbm": .35, "random_forest": .20},
        "features": FEATURES,
        "monotone_constraints": dict(zip(FEATURES, MONOTONE)),
        "training_rows": int(len(df)), "seed": SEED,
        "validation": "4-fold GroupKFold over 8 synthetic pseudo-regions, then refit on all bootstrap rows",
        "bootstrap_metrics": cv_summary,
        "feature_importance": importance,
        "local_explainability": "XGBoost TreeSHAP contributions via pred_contribs",
        "provenance": "Research-synthesis bootstrap ensemble trained on synthetic physics-guided labels for software integration. NOT field-validated Northeast India accuracy.",
        "research_basis": [
            "Stanley et al. (2021): XGBoost nowcasting with dynamic rainfall/soil moisture and probabilistic output.",
            "Nocentini et al. (2024): spatiotemporal Random Forest with dynamic cumulative rainfall and seasonal variables.",
            "Felsberg et al. (2022): blocked validation and explicit uncertainty from model/input variability.",
            "Saito et al. (2010): distinguish short-intense from long-saturating rainfall regimes.",
            "Pan et al. (2018): antecedent precipitation and 1-hour rainfall in data-scarce threshold screening.",
        ],
        "production_path": "Retrain/calibrate on GSI/ISRO/NASA inventories plus high-resolution DEM, lithology, lineaments, LULC, GPM/SMAP/Sentinel and calibrated field telemetry; evaluate with spatial + temporal blocked validation and alert-performance audits.",
    }
    (BASE / "research_model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    pd.DataFrame([{"feature":k,"importance":v} for k,v in sorted(importance.items(), key=lambda kv: kv[1], reverse=True)]).to_csv(BASE / "research_feature_importance.csv", index=False)
    print(json.dumps(metadata, indent=2))

if __name__ == "__main__": main()
