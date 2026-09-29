"""SIH26192 experimental duration-rainfall screening; no calibrated probabilities."""
import math

VERSION = 'flood-screen-v1.0'
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
    missing = []
    if wet is None: missing.append('soil_wetness_proxy_pct')
    if antecedent is None: missing.append('antecedent_rainfall_72h_mm')
    if state not in ('CURRENT', 'STALE'): missing.append('weather_packet')
    valid_at = number(packet.get('valid_at_epoch'), hi=1e12)
    if state == 'CURRENT' and (valid_at is None or not 0 <= now - valid_at <= 10800):
        missing.append('current_provider_timestamp')
    # Illustrative sensitivity only, not an empirically calibrated hydrologic model.
    multiplier = max(0.6, 1 - 0.25 * (wet or 0) / 100 - 0.15 * min((antecedent or 0) / 300, 1))
    windows = []
    for hours in HORIZONS:
        rain = number(packet.get(f'rain_forecast_{hours}h_mm'))
        threshold = basin['thresholds_mm'][str(hours)] * multiplier if not missing else None
        ratio = rain / threshold if rain is not None and threshold else None
        level = ('CRITICAL' if ratio >= 1.5 else 'HIGH' if ratio >= 1 else 'MODERATE' if ratio >= 0.7 else 'LOW') if ratio is not None else 'UNKNOWN'
        windows.append({'hours': hours, 'rainfall_mm': rain, 'screening_threshold_mm': round(threshold, 2) if threshold else None,
                        'exceedance_ratio': round(ratio, 3) if ratio is not None else None, 'level': level})
        if rain is None: missing.append(f'rain_forecast_{hours}h_mm')
    sensor_used = bool(sensor and sensor['source'] == 'REAL_SENSOR' and sensor['quality'] >= 0.8
                       and 0 <= now - sensor['observed_at'] <= 900 and state == 'CURRENT'
                       and basin.get('station_id') == sensor['station_id'] and basin.get('danger_stage_m') is not None)
    stage_exceeded = sensor_used and sensor['water_level_m'] >= basin['danger_stage_m']
    rank = {'UNKNOWN': -1, 'LOW': 0, 'MODERATE': 1, 'HIGH': 2, 'CRITICAL': 3}
    # Incomplete windows cannot be silently summarized as a complete forecast.
    level = 'UNKNOWN' if missing else max((w['level'] for w in windows), key=rank.get)
    if stage_exceeded: level = 'CRITICAL'
    return {'hazard': 'FLASH_FLOOD', 'version': VERSION, 'level': level,
            'status': 'INSUFFICIENT_DATA' if missing else 'SCREENED', 'windows': windows, 'missing': missing,
            'data_state': state, 'source': packet.get('source'), 'valid_time': packet.get('valid_time'),
            'fetched_at': packet.get('updated_at'), 'valid_at_epoch': valid_at, 'soil_wetness_proxy_pct': wet, 'antecedent_rainfall_72h_mm': antecedent,
            'basin': basin, 'sensor': sensor, 'sensor_used': sensor_used, 'stage_exceeded': bool(stage_exceeded),
            'terrain_slope_deg': number(packet.get('terrain_slope_deg'), hi=90),
            'terrain_elevation_m': number(packet.get('terrain_elevation_m'), lo=-500, hi=9000),
            'terrain_local_relief_m': number(packet.get('terrain_local_relief_m'), hi=10000),
            'terrain_source': packet.get('terrain_source'),
            'probability': None, 'validated_lead_time_minutes': None,
            'limitations': ([('Automatic research-screening profile is active; locally verified catchment thresholds are not configured.' if basin.get('context_status') == 'AUTO_SCREENING' else 'Configured rainfall thresholds are used for this monitored area.')] + [
                'Rainfall thresholds and wetness adjustment are screening rules and require local calibration.',
                'Weather is sampled at the configured area point, not averaged over a delineated catchment.',
                'Forecast windows are rainfall accumulation periods, not flood arrival times or evacuation lead times.',
                'No discharge routing, flood depth or inundation boundary is calculated.',
                'Village points indicate monitoring/recipient locations, not validated flood exposure.',
                'Slope stability and landslide history are supporting context, not substitutes for a flood model.'])}
