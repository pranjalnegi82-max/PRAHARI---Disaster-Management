"""Transparent duration-rainfall flash-flood screening with explicit data provenance."""
import math

VERSION = 'flood-screen-v1.1'
HORIZONS = (1, 3, 6)


def number(value, lo=0, hi=1e6):
    try:
        value = float(value)
        return value if math.isfinite(value) and lo <= value <= hi else None
    except (TypeError, ValueError):
        return None


def assess(packet, basin, sensor=None, now=0):
    state = packet.get('availability', 'MISSING')
    wet = number(packet.get('soil_moisture_proxy_pct'), hi=100)
    antecedent = number(packet.get('antecedent_rainfall_72h_mm'))
    valid_at = number(packet.get('valid_at_epoch'), hi=1e12)

    base_missing = []
    if wet is None:
        base_missing.append('soil_wetness_proxy_pct')
    if antecedent is None:
        base_missing.append('antecedent_rainfall_72h_mm')
    if state not in ('CURRENT', 'STALE', 'HISTORICAL_REPLAY'):
        base_missing.append('weather_packet')
    if state == 'CURRENT' and (valid_at is None or not 0 <= now - valid_at <= 10800):
        base_missing.append('current_provider_timestamp')

    configured = basin.get('context_status') == 'CONFIGURED'
    thresholds = basin.get('thresholds_mm') if configured else None
    threshold_ready = isinstance(thresholds, dict) and all(str(h) in thresholds for h in HORIZONS)

    multiplier = None
    if not base_missing:
        # Sensitivity adjustment only; local rainfall thresholds themselves must
        # be supplied from a documented catchment source.
        multiplier = max(0.6, 1 - 0.25 * wet / 100 - 0.15 * min(antecedent / 300, 1))

    windows = []
    window_missing = []
    rank = {'UNKNOWN': -1, 'LOW': 0, 'MODERATE': 1, 'HIGH': 2, 'CRITICAL': 3}
    for hours in HORIZONS:
        rain = number(packet.get(f'rain_forecast_{hours}h_mm'))
        if rain is None:
            window_missing.append(f'rain_forecast_{hours}h_mm')
        threshold = None
        ratio = None
        level = 'UNKNOWN'
        if threshold_ready and multiplier is not None:
            raw_threshold = number(thresholds.get(str(hours)), lo=0.001, hi=2000)
            if raw_threshold is not None:
                threshold = raw_threshold * multiplier
                if rain is not None:
                    ratio = rain / threshold
                    level = 'CRITICAL' if ratio >= 1.5 else 'HIGH' if ratio >= 1 else 'MODERATE' if ratio >= 0.7 else 'LOW'
        windows.append({
            'hours': hours,
            'rainfall_mm': rain,
            'screening_threshold_mm': round(threshold, 2) if threshold is not None else None,
            'exceedance_ratio': round(ratio, 3) if ratio is not None else None,
            'level': level,
        })

    missing = list(dict.fromkeys(base_missing + window_missing))
    if not configured or not threshold_ready:
        missing.append('catchment_configuration')

    sensor_used = bool(
        configured and sensor and sensor.get('source') == 'REAL_SENSOR'
        and number(sensor.get('quality'), hi=1) is not None and sensor['quality'] >= 0.8
        and number(sensor.get('observed_at'), hi=1e12) is not None
        and 0 <= now - sensor['observed_at'] <= 900
        and state == 'CURRENT'
        and basin.get('station_id') == sensor.get('station_id')
        and basin.get('danger_stage_m') is not None
    )
    stage_exceeded = bool(sensor_used and sensor.get('water_level_m') is not None
                          and sensor['water_level_m'] >= basin['danger_stage_m'])

    if not configured or not threshold_ready:
        level = 'CRITICAL' if stage_exceeded else 'UNKNOWN'
        status = 'UNCONFIGURED' if not base_missing and not window_missing else 'INSUFFICIENT_DATA'
    elif missing:
        level = 'CRITICAL' if stage_exceeded else 'UNKNOWN'
        status = 'INSUFFICIENT_DATA'
    else:
        level = max((w['level'] for w in windows), key=rank.get)
        if stage_exceeded:
            level = 'CRITICAL'
        status = 'SCREENED'

    return {
        'hazard': 'FLASH_FLOOD',
        'version': VERSION,
        'level': level,
        'status': status,
        'windows': windows,
        'missing': list(dict.fromkeys(missing)),
        'data_state': state,
        'source': packet.get('source'),
        'valid_time': packet.get('valid_time'),
        'fetched_at': packet.get('updated_at'),
        'valid_at_epoch': valid_at,
        'soil_wetness_proxy_pct': wet,
        'antecedent_rainfall_72h_mm': antecedent,
        'threshold_adjustment_factor': round(multiplier, 3) if multiplier is not None else None,
        'basin': basin,
        'sensor': sensor,
        'sensor_used': sensor_used,
        'stage_exceeded': stage_exceeded,
        'probability': None,
        'validated_lead_time_minutes': None,
        'limitations': [
            'Rainfall thresholds require local catchment calibration and a documented source.',
            'Weather is sampled at the monitoring point rather than a watershed-mean radar/gauge field.',
            'Forecast windows are rainfall accumulation periods, not flood arrival or evacuation lead time.',
            'No discharge routing, flood depth or inundation boundary is calculated by this screening endpoint.',
        ],
    }
