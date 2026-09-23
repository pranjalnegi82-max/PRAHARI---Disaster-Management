from __future__ import annotations
from dataclasses import dataclass
from typing import Any

VERSION = "baseline-screen-v1.0"

@dataclass
class BaselineResult:
    status: str
    level: str
    index: float | None
    reasons: list[dict[str, Any]]
    missing: list[str]
    limitations: list[str]


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def assess(values: dict[str, Any], telemetry_source: str | None = None) -> BaselineResult:
    rain24 = _num(values.get("rainfall_24h", values.get("rainfall")))
    rain72 = _num(values.get("antecedent_rainfall_72h"))
    rain7 = _num(values.get("cumulative_rainfall_7d"))
    soil = _num(values.get("soil_moisture"))
    slope = _num(values.get("slope"))
    peak1h = _num(values.get("max_hourly_rain_24h"))
    tilt = _num(values.get("tilt_deg"))
    displacement = _num(values.get("displacement_mm"))
    pore = _num(values.get("pore_pressure_kpa"))
    quality = _num(values.get("telemetry_quality"))

    required = {"rainfall_24h": rain24, "antecedent_rainfall_72h": rain72, "soil_moisture": soil, "slope": slope}
    missing = [k for k, v in required.items() if v is None]
    limitations = [
        "This is a transparent screening baseline, not a calibrated landslide probability.",
        "Thresholds are research-informed generic screening rules and are not locally calibrated warning thresholds for Northeast India.",
    ]
    if missing:
        return BaselineResult("INSUFFICIENT_DATA", "UNKNOWN", None, [], missing, limitations)

    rain7 = rain7 if rain7 is not None else rain72 * 1.7
    peak1h = peak1h if peak1h is not None else 0.0
    reasons: list[dict[str, Any]] = []

    def add(name: str, value: float, unit: str, condition: bool, note: str):
        if condition:
            reasons.append({"factor": name, "value": round(value, 2), "unit": unit, "note": note})

    steep = slope >= 35
    very_steep = slope >= 45
    saturated = soil >= 80
    very_saturated = soil >= 88
    heavy = rain24 >= 100 or peak1h >= 20
    extreme = rain24 >= 150 or peak1h >= 30
    antecedent_wet = rain72 >= 250 or rain7 >= 450
    prolonged = rain72 >= 350 or rain7 >= 650

    real_ground_precursor = False
    if telemetry_source == "REAL_SENSOR" and quality is not None and quality >= 0.6:
        real_ground_precursor = (
            (tilt is not None and abs(tilt) >= 2.0)
            or (displacement is not None and displacement >= 5.0)
            or (pore is not None and pore >= 70.0)
        )

    if real_ground_precursor and steep and (saturated or heavy):
        level = "CRITICAL"
    elif steep and very_saturated and (extreme or prolonged):
        level = "CRITICAL"
    elif (steep and saturated and (heavy or antecedent_wet)) or (very_steep and antecedent_wet):
        level = "HIGH"
    elif slope >= 25 and (rain24 >= 60 or rain72 >= 160 or soil >= 65):
        level = "MODERATE"
    else:
        level = "LOW"

    # An interpretable screening index for sorting/visualisation only. It is intentionally
    # not named or returned as a probability.
    components = [
        min(rain24 / 180.0, 1.0),
        min(rain72 / 400.0, 1.0),
        min(soil / 100.0, 1.0),
        min(slope / 55.0, 1.0),
    ]
    index = round(100 * sum(components) / len(components), 1)
    if real_ground_precursor:
        index = max(index, 85.0)

    add("24 h rainfall", rain24, "mm", rain24 >= 60, "Recent rainfall is elevated")
    add("72 h antecedent rainfall", rain72, "mm", rain72 >= 160, "Antecedent wetness can reduce available drainage/storage")
    add("7 d cumulative rainfall", rain7, "mm", rain7 >= 300, "Prolonged rainfall indicates sustained wetting")
    add("Soil wetness proxy", soil, "%", soil >= 65, "Higher wetness is associated with reduced matric suction / saturation")
    add("Slope", slope, "deg", slope >= 25, "Steeper terrain increases gravitational driving stress")
    add("Peak hourly rainfall", peak1h, "mm/h", peak1h >= 20, "Short intense rainfall can be a triggering pattern")
    if real_ground_precursor:
        reasons.insert(0, {"factor": "Field precursor", "value": 1, "unit": "flag", "note": "Fresh REAL_SENSOR telemetry crossed a ground-motion/pore-pressure screening threshold"})

    if telemetry_source and telemetry_source != "REAL_SENSOR":
        limitations.append(f"Telemetry source {telemetry_source} is excluded from live operational precursor escalation.")

    return BaselineResult("ASSESSED", level, index, reasons[:6], [], limitations)
