from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Optional, Literal
from pathlib import Path
import math
import time
import shutil
import json
import os
import uuid
import csv
import io
import numpy as np
from collections import OrderedDict
from threading import Lock
from copy import deepcopy
from starlette.concurrency import run_in_threadpool
import satellite_jobs
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from ml.risk_engine import predict as ml_predict, status as ml_status
from settings import (ALLOWED_ORIGINS, AUTH_REQUIRED, APP_ENV, ADMIN_KEY, WEATHER_TIMEOUT_SECONDS, WEATHER_CACHE_TTL_SECONDS,
                      WEATHER_STALE_MAX_SECONDS, EXTERNAL_SMS_ENABLED,
                      NOTIFICATION_PROVIDER, MAX_UPLOAD_BYTES, DB_PATH, FIELD_OFFICERS,
                      FIELD_OFFICERS_CONFIG_ERROR, ENV_SOURCE, DATABASE_URL,
                      BROADCAST_ENABLED, BROADCAST_PROVIDER)
from database import connect as connect_database, insert_row, storage_status
from database_schema import initialize_schema
from auth import resolve_role, require_role, field_officer_for_key
from risk_baseline import assess as baseline_assess, VERSION as BASELINE_VERSION
from satellite_engine import status as l4s_status, infer_patch as l4s_infer_patch
from satellite_preprocess import (status as satprep_status, prepare_patch as satprep_prepare_patch,
                                  patch_summary as satprep_patch_summary, candidate_geojson as satprep_candidate_geojson,
                                  model_input as satprep_model_input, mask_overlay as satprep_mask_overlay)
from notifications import (
    FAILED_DELIVERY_STATUSES,
    config_status as notification_config_status, normalize_e164, send as send_notification,
    fetch_status as fetch_notification_status, validate_signature as validate_twilio_signature,
    callback_url as notification_callback_url, NotificationConfigError,
)

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)
DB = DB_PATH
TILE_CACHE = BASE / "tile_cache" / "nasa"
TILE_CACHE.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PRAHARI Command Center API", version="11.0.0", description="Multi-source flash-flood and hill-hazard monitoring for hilly regions of India")
app.add_middleware(GZipMiddleware, minimum_size=700)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-PRAHARI-Key"],
)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")

LOCATIONS = [
    # Curated real place coordinates spanning major Indian hill systems. These
    # records are only monitoring points; no synthetic hazard attributes are attached.
    {"id":1,"name":"Gangtok","state":"Sikkim","country":"India","lat":27.3314,"lon":88.6138,"source":"CURATED_PLACE"},
    {"id":2,"name":"Aizawl","state":"Mizoram","country":"India","lat":23.7271,"lon":92.7176,"source":"CURATED_PLACE"},
    {"id":3,"name":"Kohima","state":"Nagaland","country":"India","lat":25.6751,"lon":94.1086,"source":"CURATED_PLACE"},
    {"id":4,"name":"Shillong","state":"Meghalaya","country":"India","lat":25.5788,"lon":91.8933,"source":"CURATED_PLACE"},
    {"id":5,"name":"Itanagar","state":"Arunachal Pradesh","country":"India","lat":27.0844,"lon":93.6053,"source":"CURATED_PLACE"},
    {"id":6,"name":"Manali","state":"Himachal Pradesh","country":"India","lat":32.2396,"lon":77.1887,"source":"CURATED_PLACE"},
    {"id":7,"name":"Shimla","state":"Himachal Pradesh","country":"India","lat":31.1048,"lon":77.1734,"source":"CURATED_PLACE"},
    {"id":8,"name":"Nainital","state":"Uttarakhand","country":"India","lat":29.3919,"lon":79.4542,"source":"CURATED_PLACE"},
    {"id":9,"name":"Joshimath","state":"Uttarakhand","country":"India","lat":30.5553,"lon":79.5650,"source":"CURATED_PLACE"},
    {"id":10,"name":"Pithoragarh","state":"Uttarakhand","country":"India","lat":29.5829,"lon":80.2182,"source":"CURATED_PLACE"},
    {"id":11,"name":"Dharamshala","state":"Himachal Pradesh","country":"India","lat":32.2190,"lon":76.3234,"source":"CURATED_PLACE"},
    {"id":12,"name":"Srinagar","state":"Jammu and Kashmir","country":"India","lat":34.0837,"lon":74.7973,"source":"CURATED_PLACE"},
    {"id":13,"name":"Leh","state":"Ladakh","country":"India","lat":34.1526,"lon":77.5771,"source":"CURATED_PLACE"},
    {"id":14,"name":"Darjeeling","state":"West Bengal","country":"India","lat":27.0410,"lon":88.2663,"source":"CURATED_PLACE"},
    {"id":15,"name":"Tawang","state":"Arunachal Pradesh","country":"India","lat":27.5861,"lon":91.8594,"source":"CURATED_PLACE"},
    {"id":16,"name":"Haflong","state":"Assam","country":"India","lat":25.1648,"lon":93.0176,"source":"CURATED_PLACE"},
    {"id":17,"name":"Munnar","state":"Kerala","country":"India","lat":10.0889,"lon":77.0595,"source":"CURATED_PLACE"},
    {"id":18,"name":"Kalpetta","state":"Kerala","country":"India","lat":11.6087,"lon":76.0834,"source":"CURATED_PLACE"},
    {"id":19,"name":"Ooty","state":"Tamil Nadu","country":"India","lat":11.4102,"lon":76.6950,"source":"CURATED_PLACE"},
    {"id":20,"name":"Kodaikanal","state":"Tamil Nadu","country":"India","lat":10.2381,"lon":77.4892,"source":"CURATED_PLACE"},
    {"id":21,"name":"Madikeri","state":"Karnataka","country":"India","lat":12.4244,"lon":75.7382,"source":"CURATED_PLACE"},
    {"id":22,"name":"Mahabaleshwar","state":"Maharashtra","country":"India","lat":17.9307,"lon":73.6477,"source":"CURATED_PLACE"},
    {"id":23,"name":"Mount Abu","state":"Rajasthan","country":"India","lat":24.5926,"lon":72.7156,"source":"CURATED_PLACE"},
    {"id":24,"name":"Pachmarhi","state":"Madhya Pradesh","country":"India","lat":22.4674,"lon":78.4346,"source":"CURATED_PLACE"},
]

# Operational endpoints never return invented road, shelter or infrastructure
# inventories. Verified agency GIS can be connected later through dedicated sources.
ROUTES = []
INFRA = []

DATA_CATALOG = {
    "open_meteo": {
        "name": "Open-Meteo Forecast API", "kind": "weather_model", "status": "LIVE_WHEN_REACHABLE",
        "origin": "https://open-meteo.com/", "coverage": "global", "spatial_resolution": "provider/model dependent",
        "freshness": "current/hourly model fields", "license_note": "See provider terms; values are model-derived observations/forecasts, not station measurements."
    },
    "open_meteo_elevation": {
        "name": "Open-Meteo Elevation API", "kind": "terrain_elevation", "status": "LIVE_WHEN_REACHABLE",
        "origin": "https://open-meteo.com/en/docs/elevation-api", "coverage": "global",
        "spatial_resolution": "provider DEM dependent", "freshness": "static terrain",
        "license_note": "Elevation samples are provider-derived. PRAHARI derives a local slope proxy from a 3×3 neighborhood and preserves source provenance."
    },
    "nasa_gibs": {
        "name": "NASA EOSDIS GIBS VIIRS imagery", "kind": "visual_satellite_basemap", "status": "VISUAL_ONLY",
        "origin": "https://gibs.earthdata.nasa.gov/", "coverage": "global", "spatial_resolution": "layer dependent",
        "freshness": "near-real-time imagery where available",
        "license_note": "Used as visual context only. PRAHARI v9 does not run a landslide detector on these tiles."
    },
    "earth_search_s2": {
        "name": "Element 84 Earth Search / Sentinel-2 L2A", "kind": "optical_satellite_scene_catalog", "status": "LIVE_SCENE_DISCOVERY",
        "origin": "https://earth-search.aws.element84.com/v1", "coverage": "global Sentinel-2 archive",
        "spatial_resolution": "10-20 m multispectral bands", "freshness": "catalog dependent; newest cloud-screened acquisition",
        "license_note": "Scene metadata and COG asset links are discovered through Earth Search. Sentinel data terms/attribution apply. PRAHARI scene discovery is not itself landslide inference."
    },
    "nasa_glc": {
        "name": "NASA Global Landslide Catalog", "kind": "historical_inventory", "status": "REFERENCE_NOT_BUNDLED",
        "origin": "https://data.nasa.gov/dataset/global-landslide-catalog-export", "coverage": "global reported rainfall-triggered events",
        "spatial_resolution": "event locations", "freshness": "catalog/export dependent",
        "license_note": "Reference dataset; current project package does not redistribute the catalog. Follow NASA catalog terms/citation requirements before ingestion."
    },
    "landslide4sense": {
        "name": "Landslide4Sense", "kind": "post_event_satellite_detection", "status": "ROADMAP",
        "origin": "https://github.com/iarai/Landslide4Sense-2022", "coverage": "benchmark patches from globally distributed events",
        "spatial_resolution": "~10 m benchmark pixels", "freshness": "benchmark dataset",
        "license_note": "Official baseline code is MIT licensed. No Landslide4Sense inference model is bundled in PRAHARI v9."
    },
}

REPLAY_NOTICE = "Historical replay/demo data. Values are bundled examples for workflow testing and must not be presented as current observations."

def build_replay_packet(x):
    """Synthetic QA fixture. Disabled unless explicitly enabled for automated tests."""
    if not _test_fixtures_enabled():
        raise HTTPException(404, "Replay fixtures are disabled")
    now=int(time.time())
    return {
        'availability':'HISTORICAL_REPLAY','live':False,'stale_public':False,'location_id':x['id'],
        'location':f"{x['name']}, {x['state']}",'source':'PRAHARI automated-test fixture',
        'source_url':None,'updated_at':now,'valid_time':'TEST_FIXTURE','valid_at_epoch':now,
        'temperature_c':None,'humidity':80,'precipitation_now_mm':0,'rain_now_mm':0,
        'cloud_cover_pct':90,'wind_kmh':5,'wind_gust_kmh':8,'soil_moisture_m3m3':0.42,
        'soil_moisture_proxy_pct':84,'rainfall_6h_mm':34,'rainfall_24h_mm':168,
        'antecedent_rainfall_72h_mm':360,'cumulative_rainfall_7d_mm':720,
        'effective_rainfall_11d_mm':520,'max_hourly_rain_24h_mm':28,
        'rain_forecast_1h_mm':38,'rain_forecast_3h_mm':82,'rain_forecast_6h_mm':125,
        'rain_forecast_24h_mm':140,'rain_forecast_48h_mm':180,'rain_forecast_72h_mm':210,
        'max_rain_probability_24h':95,'forecast':[],
        'terrain_slope_deg':46.0,'elevation_model_m':1650.0,
        'note':'Synthetic data for automated tests only.'
    }

# ---- Live public-data integration -------------------------------------------------
# Open-Meteo provides the latest continuously updated weather-model conditions
# without an API key. Static terrain/history remain local because those variables
# do not change minute-to-minute. A short cache avoids hammering the public API.
LIVE_WEATHER_CACHE = {}
LIVE_REGIONAL_CACHE = {"ts": 0, "data": None}
TERRAIN_CACHE = {}
LIVE_TTL_SECONDS = WEATHER_CACHE_TTL_SECONDS

def _test_fixtures_enabled() -> bool:
    return str(os.getenv("PRAHARI_ENABLE_TEST_FIXTURES", "false")).strip().lower() in {"1","true","yes","on"}

def _cache_key_weather(location_id:int) -> str:
    return f"open-meteo:{location_id}"

def _persist_source_cache(cache_key:str, provider:str, payload:dict, valid_at=None):
    try:
        con=db(); con.execute("INSERT INTO source_cache(cache_key,provider,payload_json,fetched_at,valid_at) VALUES(?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET provider=excluded.provider,payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,valid_at=excluded.valid_at",
            (cache_key,provider,json.dumps(payload),int(time.time()),valid_at)); con.commit(); con.close()
    except Exception:
        pass

def _load_source_cache(cache_key:str):
    try:
        con=db(); row=con.execute("SELECT * FROM source_cache WHERE cache_key=?",(cache_key,)).fetchone(); con.close()
        if not row: return None
        out=dict(row); out['payload']=json.loads(out.pop('payload_json')); return out
    except Exception:
        return None

def _sum_indices(values, indices):
    total = 0.0
    for i in indices:
        try:
            v = values[i]
            if v is not None:
                total += float(v)
        except Exception:
            pass
    return round(total, 1)

def _complete_rain_window(values, indices, count, times=None):
    """Missing/invalid provider hours must never become zero rainfall."""
    from flood_risk import number
    if len(indices) != count:
        return None
    if times is not None:
        try:
            stamps = [datetime.fromisoformat(times[i]) for i in indices]
            if any((b-a).total_seconds() != 3600 for a,b in zip(stamps, stamps[1:])):
                return None
        except (ValueError, IndexError, TypeError):
            return None
    samples = [number(values[i]) if i < len(values) else None for i in indices]
    return round(sum(samples), 2) if all(v is not None for v in samples) else None


def _fetch_json_with_retries(url:str, timeout:float, attempts:int=3):
    """Small retry wrapper for public weather APIs.

    Render free instances can have transient DNS/connectivity delays after a cold
    start. Retry only transport/HTTP failures; never replace missing live data
    with invented observations.
    """
    last_error=None
    for attempt in range(max(1, attempts)):
        try:
            req=UrlRequest(url, headers={'User-Agent':'PRAHARI/11.0'})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except HTTPError as exc:
            last_error=exc
            if attempt < attempts-1:
                retry_after=exc.headers.get('Retry-After') if getattr(exc,'headers',None) else None
                try: delay=float(retry_after) if retry_after else 2.5*(attempt+1)
                except Exception: delay=2.5*(attempt+1)
                time.sleep(min(max(delay,1.0),10.0))
        except (URLError, TimeoutError, ValueError) as exc:
            last_error=exc
            if attempt < attempts-1:
                time.sleep(0.8 * (attempt+1))
    raise last_error or RuntimeError('Weather provider request failed')


def _cache_key_terrain(location_id:int) -> str:
    return f"open-meteo-elevation:{location_id}"

def fetch_terrain_profile(x, force:bool=False, data_override=None):
    """Fetch provider DEM elevations and derive a transparent local slope proxy.

    No terrain value is invented when the provider is unavailable. A real cached
    profile may be reused for up to 30 days because terrain is static.
    """
    now=int(time.time())
    cached=TERRAIN_CACHE.get(x['id'])
    if not force and cached and now-cached['cached_at'] < 7*86400:
        return cached['profile']
    persisted=_load_source_cache(_cache_key_terrain(x['id']))
    if not force and persisted and now-int(persisted.get('fetched_at') or 0) <= 30*86400:
        profile=dict(persisted['payload'])
        profile['state']='STALE' if now-int(persisted.get('fetched_at') or 0) > 7*86400 else profile.get('state','CURRENT')
        TERRAIN_CACHE[x['id']]={'cached_at':int(persisted.get('fetched_at') or now),'profile':profile}
        return profile

    lat=float(x['lat']); lon=float(x['lon'])
    dlat=0.0045
    dlon=dlat/max(0.25,math.cos(math.radians(lat)))
    coords=[
        (lat,lon),(lat+dlat,lon),(lat-dlat,lon),(lat,lon+dlon),(lat,lon-dlon),
        (lat+dlat,lon+dlon),(lat+dlat,lon-dlon),(lat-dlat,lon+dlon),(lat-dlat,lon-dlon)
    ]
    params={'latitude':','.join(f'{a:.6f}' for a,_ in coords),'longitude':','.join(f'{b:.6f}' for _,b in coords)}
    url='https://api.open-meteo.com/v1/elevation?'+urlencode(params)
    try:
        data=data_override if data_override is not None else _fetch_json_with_retries(url, WEATHER_TIMEOUT_SECONDS, attempts=2)
        elevations=data.get('elevation') if isinstance(data,dict) else None
        if not isinstance(elevations,list) or len(elevations)!=len(coords) or any(v is None for v in elevations):
            raise ValueError('Elevation provider returned an incomplete neighborhood')
        elevations=[float(v) for v in elevations]
        center=elevations[0]
        slopes=[]
        for (plat,plon),z in zip(coords[1:],elevations[1:]):
            dy=(plat-lat)*111320.0
            dx=(plon-lon)*111320.0*math.cos(math.radians(lat))
            horizontal=max(1.0,math.hypot(dx,dy))
            slopes.append(math.degrees(math.atan(abs(z-center)/horizontal)))
        profile={
            'state':'CURRENT','source':'Open-Meteo Elevation API','source_url':'https://open-meteo.com/en/docs/elevation-api',
            'fetched_at':now,'elevation_m':round(center,1),'local_slope_proxy_deg':round(max(slopes),2),
            'mean_neighbor_slope_deg':round(sum(slopes)/len(slopes),2),'sample_radius_m':500,
            'sample_count':len(coords)
        }
        TERRAIN_CACHE[x['id']]={'cached_at':now,'profile':profile}
        _persist_source_cache(_cache_key_terrain(x['id']),'Open-Meteo Elevation',profile,None)
        return profile
    except Exception as exc:
        persisted=_load_source_cache(_cache_key_terrain(x['id']))
        if persisted and now-int(persisted.get('fetched_at') or 0) <= 30*86400:
            profile=dict(persisted['payload']); profile['state']='STALE'; profile['error']=str(exc)
            return profile
        return {'state':'MISSING','source':'Open-Meteo Elevation API','source_url':'https://open-meteo.com/en/docs/elevation-api',
                'fetched_at':None,'elevation_m':None,'local_slope_proxy_deg':None,'mean_neighbor_slope_deg':None,
                'sample_radius_m':500,'sample_count':0,'error':str(exc)}

def fetch_live_weather(x, force=False, data_override=None):
    now = int(time.time())
    cached = LIVE_WEATHER_CACHE.get(x['id'])
    if data_override is None and cached and not force and now - cached['cached_at'] < LIVE_TTL_SECONDS:
        return cached['packet']

    # Keep the request compact and Render-friendly. We need 11 days of
    # antecedent rainfall for the research features, so 264 past hours are
    # sufficient. forecast_hours gives the exact +72 h horizon; forecast_days
    # is intentionally not combined with it.
    params = {
        'latitude': x['lat'],
        'longitude': x['lon'],
        'timezone': 'auto',
        'current': ','.join([
            'temperature_2m','relative_humidity_2m','precipitation','rain','cloud_cover',
            'wind_speed_10m','wind_gusts_10m'
        ]),
        'hourly': ','.join([
            'precipitation','rain','precipitation_probability','temperature_2m',
            'relative_humidity_2m','soil_moisture_0_to_1cm'
        ]),
        'past_hours': 264,
        'forecast_hours': 72
    }
    url = 'https://api.open-meteo.com/v1/forecast?' + urlencode(params)
    try:
        data = data_override if data_override is not None else _fetch_json_with_retries(url, WEATHER_TIMEOUT_SECONDS, attempts=3)
        current = data.get('current') or {}
        hourly = data.get('hourly') or {}
        times = hourly.get('time') or []
        cur_iso = current.get('time')
        cur_dt = datetime.fromisoformat(cur_iso) if cur_iso else datetime.now()
        past_idx, future_idx = [], []
        for i,t in enumerate(times):
            try:
                dt = datetime.fromisoformat(t)
                (past_idx if dt <= cur_dt else future_idx).append(i)
            except Exception:
                pass
        # The first forecast hour and latest history hour must abut current time.
        if future_idx and (datetime.fromisoformat(times[future_idx[0]]) - cur_dt).total_seconds() > 3600:
            future_idx = []
        if past_idx and (cur_dt - datetime.fromisoformat(times[past_idx[-1]])).total_seconds() >= 3600:
            past_idx = []
        past_idx_all = list(past_idx)
        past_idx_6h = past_idx_all[-6:]
        past_idx_24h = past_idx_all[-24:]
        past_idx_72h = past_idx_all[-72:]
        future_idx = future_idx[:72]
        precip = hourly.get('precipitation') or []
        rain = hourly.get('rain') or []
        probs = hourly.get('precipitation_probability') or []
        temps = hourly.get('temperature_2m') or []
        hums = hourly.get('relative_humidity_2m') or []
        # Soil moisture is an hourly model field. Read the latest available
        # hourly value instead of requesting it in the current block, which
        # keeps compatibility across Open-Meteo model combinations.
        soil = None
        soil_series = hourly.get('soil_moisture_0_to_1cm') or []
        if past_idx_all:
            try: soil = soil_series[past_idx_all[-1]]
            except Exception: soil = None
        # Convert volumetric water content to a 0-100 wetness proxy for the existing
        # prototype model. This is not a direct field-probe saturation percentage.
        soil_proxy = round(clamp(float(soil) / 0.5) * 100, 1) if soil is not None else None

        def hval(arr, idx, default=None):
            try:
                v = arr[idx]
                return default if v is None else v
            except Exception:
                return default
        points=[]
        for offset,label in [(0,'+1h'),(2,'+3h'),(5,'+6h'),(11,'+12h'),(23,'+24h')]:
            if future_idx:
                idx=future_idx[min(offset,len(future_idx)-1)]
                points.append({
                    'label':label,
                    'time':hval(times,idx,''),
                    'rain_mm':round(float(hval(precip,idx,0) or 0),1),
                    'rain_probability':round(float(hval(probs,idx,0) or 0),0),
                    'humidity':round(float(hval(hums,idx,current.get('relative_humidity_2m',0)) or 0),0),
                    'temp_c':round(float(hval(temps,idx,current.get('temperature_2m',0)) or 0),1)
                })
        # Research-inspired dynamic rainfall features. Daily effective rainfall uses
        # an exponentially decaying antecedent-memory term (K=0.84) as a
        # screening feature; it is not an official local rainfall threshold.
        daily_sums = {}
        for i in past_idx_all:
            try:
                day = datetime.fromisoformat(times[i]).date().isoformat()
                daily_sums[day] = daily_sums.get(day, 0.0) + float(hval(precip, i, 0) or 0)
            except Exception:
                pass
        recent_days = sorted(daily_sums.keys(), reverse=True)[:11]
        rain_7d_days = sorted(daily_sums.keys(), reverse=True)[:7]
        cumulative_rainfall_7d = round(sum(daily_sums[d] for d in rain_7d_days), 1)
        effective_rainfall_11d = 0.0
        for lag, day in enumerate(recent_days):
            effective_rainfall_11d += (0.84 ** lag) * daily_sums[day]
        effective_rainfall_11d = round(effective_rainfall_11d, 1)
        max_hourly_rain_24h = round(max([float(hval(precip,i,0) or 0) for i in past_idx_24h] or [0]), 1)

        packet={
            'availability':'CURRENT',
            'live': True,
            'location_id': x['id'],
            'location': f"{x['name']}, {x['state']}",
            'source': 'Open-Meteo latest weather-model feed',
            'source_url': 'https://open-meteo.com/',
            'updated_at': int(time.time()),
            'valid_time': cur_iso,
            'valid_at_epoch': (int(cur_dt.timestamp()) if cur_dt.tzinfo else int(cur_dt.replace(tzinfo=timezone.utc).timestamp()) - int(data.get('utc_offset_seconds',0))) if cur_iso else None,
            'latitude': data.get('latitude',x['lat']),
            'longitude': data.get('longitude',x['lon']),
            'elevation_model_m': data.get('elevation'),
            'temperature_c': current.get('temperature_2m'),
            'humidity': current.get('relative_humidity_2m'),
            'precipitation_now_mm': current.get('precipitation'),
            'rain_now_mm': current.get('rain'),
            'cloud_cover_pct': current.get('cloud_cover'),
            'wind_kmh': current.get('wind_speed_10m'),
            'wind_gust_kmh': current.get('wind_gusts_10m'),
            'soil_moisture_m3m3': soil,
            'soil_moisture_proxy_pct': soil_proxy,
            'rainfall_6h_mm': _sum_indices(precip,past_idx_6h),
            'rainfall_24h_mm': _sum_indices(precip,past_idx_24h),
            'antecedent_rainfall_72h_mm': _complete_rain_window(precip,past_idx_72h,72,times),
            'cumulative_rainfall_7d_mm': cumulative_rainfall_7d,
            'effective_rainfall_11d_mm': effective_rainfall_11d,
            'max_hourly_rain_24h_mm': max_hourly_rain_24h,
            'rain_forecast_1h_mm': _complete_rain_window(precip,future_idx[:1],1,times),
            'rain_forecast_3h_mm': _complete_rain_window(precip,future_idx[:3],3,times),
            'rain_forecast_6h_mm': _complete_rain_window(precip,future_idx[:6],6,times),
            'rain_forecast_24h_mm': _sum_indices(precip,future_idx[:24]),
            'rain_forecast_48h_mm': _sum_indices(precip,future_idx[:48]),
            'rain_forecast_72h_mm': _sum_indices(precip,future_idx[:72]),
            'max_rain_probability_24h': max([float(hval(probs,i,0) or 0) for i in future_idx[:24]] or [0]),
            'forecast': points,
            'note': 'Current conditions are model-derived. Soil moisture is converted to a wetness proxy for screening.'
        }
        if data_override is None:
            LIVE_WEATHER_CACHE[x['id']]={'cached_at':now,'packet':packet}
            _persist_source_cache(_cache_key_weather(x['id']), 'Open-Meteo', packet, cur_iso)
        else:
            # Render's shared egress can be throttled by the free provider. In that
            # case the authenticated web client may fetch the same CORS-enabled
            # Open-Meteo response directly and relay the raw provider JSON here for
            # parsing. Never write browser-relayed payloads into the trusted server
            # source cache.
            packet['source']='Open-Meteo direct browser feed'
            packet['transport']='BROWSER_DIRECT_RELAY'
            packet['note']='Current Open-Meteo data fetched directly by the authenticated browser because server egress was rate-limited. Provider payload was parsed server-side but not independently re-fetched.'
        return packet
    except Exception as e:
        # Never invent live observations. Prefer a timestamp-preserving cached public packet;
        # otherwise return explicit MISSING state and let the assessment become incomplete.
        candidates=[]
        if cached and cached.get('packet'):
            candidates.append({'packet':cached['packet'],'fetched_at':cached.get('cached_at',0)})
        persisted=_load_source_cache(_cache_key_weather(x['id']))
        if persisted:
            candidates.append({'packet':persisted['payload'],'fetched_at':persisted.get('fetched_at',0)})
        candidates.sort(key=lambda z:z.get('fetched_at',0), reverse=True)
        if candidates:
            age=max(0, now-int(candidates[0].get('fetched_at') or 0))
            if age <= WEATHER_STALE_MAX_SECONDS:
                stale=dict(candidates[0]['packet']); stale['availability']='STALE'; stale['live']=False; stale['stale_public']=True
                stale['source']='Open-Meteo cached last-known packet'; stale['cache_age_seconds']=age; stale['error']=str(e)
                stale['note']='Refresh failed; using a real previously fetched public packet. Timestamp and stale state are preserved.'
                return stale
        return {
            'availability':'MISSING','live':False,'stale_public':False,'location_id':x['id'],'location':f"{x['name']}, {x['state']}",
            'source':'Open-Meteo unavailable','source_url':'https://open-meteo.com/','updated_at':None,'valid_time':None,'error':str(e),
            'temperature_c':None,'humidity':None,'precipitation_now_mm':None,'rain_now_mm':None,'cloud_cover_pct':None,'wind_kmh':None,'wind_gust_kmh':None,
            'soil_moisture_m3m3':None,'soil_moisture_proxy_pct':None,'rainfall_6h_mm':None,'rainfall_24h_mm':None,
            'antecedent_rainfall_72h_mm':None,'cumulative_rainfall_7d_mm':None,'effective_rainfall_11d_mm':None,'max_hourly_rain_24h_mm':None,
            'rain_forecast_6h_mm':None,'rain_forecast_24h_mm':None,'rain_forecast_48h_mm':None,'rain_forecast_72h_mm':None,'max_rain_probability_24h':None,
            'forecast':[],'note':'Live source unavailable and no sufficiently fresh cached observation exists. No values were fabricated.'
        }

def enrich_with_live(x, packet):
    d=dict(x)
    availability=packet.get('availability') or ('CURRENT' if packet.get('live') else 'STALE' if packet.get('stale_public') else 'MISSING')
    d['data_state']=availability
    d['live_weather']=availability=='CURRENT'
    d['weather_source']=packet.get('source')
    d['weather_updated_at']=packet.get('updated_at')
    d['weather_valid_time']=packet.get('valid_time')
    d['weather_error']=packet.get('error')
    d['weather_note']=packet.get('note')
    d['weather_transport']=packet.get('transport') or 'SERVER'
    d['temperature_c']=packet.get('temperature_c')
    d['humidity']=packet.get('humidity')
    d['rainfall']=packet.get('rainfall_24h_mm')
    d['rainfall_6h_mm']=packet.get('rainfall_6h_mm')
    d['soil_moisture']=packet.get('soil_moisture_proxy_pct')
    d['antecedent_rainfall_72h']=packet.get('antecedent_rainfall_72h_mm')
    d['cumulative_rainfall_7d']=packet.get('cumulative_rainfall_7d_mm')
    d['effective_rainfall_11d']=packet.get('effective_rainfall_11d_mm')
    d['max_hourly_rain_24h']=packet.get('max_hourly_rain_24h_mm')
    d['rain_forecast_1h_mm']=packet.get('rain_forecast_1h_mm')
    d['rain_forecast_3h_mm']=packet.get('rain_forecast_3h_mm')
    d['rain_forecast_6h_mm']=packet.get('rain_forecast_6h_mm')
    d['rain_forecast_24h_mm']=packet.get('rain_forecast_24h_mm')
    d['rain_forecast_48h_mm']=packet.get('rain_forecast_48h_mm')
    d['rain_forecast_72h_mm']=packet.get('rain_forecast_72h_mm')
    d['rain_probability_24h']=packet.get('max_rain_probability_24h')
    d['soil_moisture_m3m3']=packet.get('soil_moisture_m3m3')
    d['month']=datetime.now().month

    if availability=='HISTORICAL_REPLAY' and _test_fixtures_enabled():
        terrain={'state':'TEST_FIXTURE','source':'automated-test fixture','source_url':None,'fetched_at':packet.get('updated_at'),
                 'elevation_m':packet.get('elevation_model_m'),'local_slope_proxy_deg':packet.get('terrain_slope_deg'),
                 'mean_neighbor_slope_deg':packet.get('terrain_slope_deg'),'sample_radius_m':500,'sample_count':9}
    else:
        terrain=fetch_terrain_profile(x)
    d['terrain_state']=terrain.get('state')
    d['terrain_source']=terrain.get('source')
    d['elevation']=terrain.get('elevation_m')
    d['slope']=terrain.get('local_slope_proxy_deg')
    d['terrain_mean_slope_deg']=terrain.get('mean_neighbor_slope_deg')

    try:
        tele=latest_telemetry(x['id']) if 'latest_telemetry' in globals() else None
    except Exception:
        tele=None
    fresh_tele=bool(tele and int(time.time())-int(tele.get('created_at') or 0) <= 1800)
    d['telemetry']=tele; d['telemetry_fresh']=fresh_tele
    if fresh_tele and tele.get('source')=='REAL_SENSOR':
        if tele.get('soil_moisture') is not None: d['soil_moisture']=float(tele['soil_moisture'])
        for k in ('rainfall_intensity','tilt_deg','vibration_g','pore_pressure_kpa','displacement_mm','quality'):
            if tele.get(k) is not None: d['telemetry_'+k]=tele.get(k)

    vals={
        'rainfall_24h':d.get('rainfall'),'antecedent_rainfall_72h':d.get('antecedent_rainfall_72h'),
        'cumulative_rainfall_7d':d.get('cumulative_rainfall_7d'),'soil_moisture':d.get('soil_moisture'),
        'slope':d.get('slope'),'max_hourly_rain_24h':d.get('max_hourly_rain_24h'),
        'rain_forecast_24h':d.get('rain_forecast_24h_mm'),'month':d.get('month'),
    }
    if fresh_tele and tele.get('source')=='REAL_SENSOR':
        vals.update({
            'rainfall_intensity':tele.get('rainfall_intensity'),'tilt_deg':tele.get('tilt_deg'),
            'vibration_g':tele.get('vibration_g'),'pore_pressure_kpa':tele.get('pore_pressure_kpa'),
            'displacement_mm':tele.get('displacement_mm'),'telemetry_quality':tele.get('quality'),
        })
    baseline=baseline_assess(vals, tele.get('source') if fresh_tele and tele else None)
    d['assessment_status']=baseline.status
    d['assessment_kind']='TRANSPARENT_HILL_SCREEN'
    d['assessment_version']=BASELINE_VERSION
    d['risk_probability']=None
    d['risk_percent']=baseline.index
    d['risk_level']=baseline.level
    d['factors']=baseline.reasons
    d['assessment_limitations']=baseline.limitations
    d['missing_inputs']=baseline.missing
    required_count=4; available_count=required_count-len(baseline.missing)
    d['data_completeness_pct']=round(100*available_count/required_count,1)
    d['trend']='UNKNOWN' if baseline.status!='ASSESSED' else ('RISING' if (d.get('rain_forecast_24h_mm') or 0)>=60 else 'WATCH' if baseline.level in ('HIGH','CRITICAL') else 'STABLE')
    d['experimental_model']=None

    d['sources']=[
        {
            'id':'open_meteo','name':DATA_CATALOG['open_meteo']['name'],'state':availability,
            'timestamp':packet.get('valid_time') or packet.get('updated_at'),'units':{'rainfall':'mm','soil_moisture':'m3/m3 + derived wetness proxy'},
            'coverage':DATA_CATALOG['open_meteo']['coverage'],'spatial_resolution':DATA_CATALOG['open_meteo']['spatial_resolution'],
            'freshness':DATA_CATALOG['open_meteo']['freshness'],'origin':DATA_CATALOG['open_meteo']['origin'],
            'note':packet.get('note')
        },
        {
            'id':'open_meteo_elevation','name':DATA_CATALOG['open_meteo_elevation']['name'],'state':terrain.get('state'),
            'timestamp':terrain.get('fetched_at'),'units':{'elevation':'m','slope_proxy':'deg'},
            'coverage':'local 3×3 elevation neighborhood','spatial_resolution':DATA_CATALOG['open_meteo_elevation']['spatial_resolution'],
            'freshness':'static terrain','origin':DATA_CATALOG['open_meteo_elevation']['origin'],
            'note':'Local slope proxy derived from provider elevation samples.'
        },
    ]
    if tele:
        d['sources'].append({'id':'field_telemetry','name':'Field sensor telemetry','state':('CURRENT' if fresh_tele else 'STALE') if tele.get('source')=='REAL_SENSOR' else 'EXCLUDED',
            'timestamp':tele.get('created_at'),'units':'sensor-specific','coverage':tele.get('station_id'),'spatial_resolution':'point sensor',
            'freshness':'<=30 min considered fresh','origin':tele.get('source'),'note':'Only authenticated REAL_SENSOR telemetry affects live escalation.'})
    return d

def locs():
    # Registry metadata only. Live hazard state is provided by /api/live/locations.
    return [{**x,'data_state':'NOT_FETCHED','assessment_status':'NOT_ASSESSED','risk_level':'UNKNOWN',
             'risk_percent':None,'risk_probability':None,'data_completeness_pct':0,'sources':[]} for x in LOCATIONS]

def _missing_or_cached_packet(x, error_message:str):
    """Return a real cached packet when fresh enough, otherwise explicit MISSING."""
    now=int(time.time())
    candidates=[]
    mem=LIVE_WEATHER_CACHE.get(x['id'])
    if mem and mem.get('packet'):
        candidates.append({'packet':mem['packet'],'fetched_at':mem.get('cached_at',0)})
    persisted=_load_source_cache(_cache_key_weather(x['id']))
    if persisted:
        candidates.append({'packet':persisted['payload'],'fetched_at':persisted.get('fetched_at',0)})
    candidates.sort(key=lambda z:z.get('fetched_at',0), reverse=True)
    if candidates:
        age=max(0, now-int(candidates[0].get('fetched_at') or 0))
        if age <= WEATHER_STALE_MAX_SECONDS:
            stale=dict(candidates[0]['packet'])
            stale.update({
                'availability':'STALE','live':False,'stale_public':True,
                'source':'Open-Meteo cached last-known packet',
                'cache_age_seconds':age,'error':error_message,
                'note':'Live refresh failed; using a real previously fetched Open-Meteo packet with preserved timestamp.'
            })
            return stale
    return {
        'availability':'MISSING','live':False,'stale_public':False,'location_id':x['id'],
        'location':f"{x['name']}, {x['state']}",'source':'Open-Meteo unavailable',
        'source_url':'https://open-meteo.com/','updated_at':None,'valid_time':None,
        'error':error_message,'temperature_c':None,'humidity':None,'precipitation_now_mm':None,
        'rain_now_mm':None,'cloud_cover_pct':None,'wind_kmh':None,'wind_gust_kmh':None,
        'soil_moisture_m3m3':None,'soil_moisture_proxy_pct':None,'rainfall_6h_mm':None,
        'rainfall_24h_mm':None,'antecedent_rainfall_72h_mm':None,'cumulative_rainfall_7d_mm':None,
        'effective_rainfall_11d_mm':None,'max_hourly_rain_24h_mm':None,'rain_forecast_1h_mm':None,'rain_forecast_3h_mm':None,'rain_forecast_6h_mm':None,
        'rain_forecast_24h_mm':None,'rain_forecast_48h_mm':None,'rain_forecast_72h_mm':None,
        'max_rain_probability_24h':None,'forecast':[],
        'note':'Live source unavailable and no sufficiently fresh cached observation exists. No values were fabricated.'
    }

def live_locs(force=False, mode='live'):
    if mode == 'replay':
        if not _test_fixtures_enabled():
            raise HTTPException(404,'Replay fixtures are disabled')
        return [enrich_with_live(x, build_replay_packet(x)) for x in LOCATIONS]
    now=int(time.time())
    if LIVE_REGIONAL_CACHE['data'] is not None and not force and now-LIVE_REGIONAL_CACHE['ts'] < LIVE_TTL_SECONDS:
        return LIVE_REGIONAL_CACHE['data']

    packets={}
    # Keep requests small as monitoring expands beyond a single region. A provider
    # failure now degrades only that chunk instead of blanking every monitored area.
    chunk_size=10
    for start in range(0,len(LOCATIONS),chunk_size):
        group=LOCATIONS[start:start+chunk_size]
        params = {
            'latitude': ','.join(str(x['lat']) for x in group),
            'longitude': ','.join(str(x['lon']) for x in group),
            'timezone': 'auto',
            'current': ','.join([
                'temperature_2m','relative_humidity_2m','precipitation','rain','cloud_cover',
                'wind_speed_10m','wind_gusts_10m'
            ]),
            'hourly': ','.join([
                'precipitation','rain','precipitation_probability','temperature_2m',
                'relative_humidity_2m','soil_moisture_0_to_1cm'
            ]),
            'past_hours': 264,
            'forecast_hours': 72
        }
        url='https://api.open-meteo.com/v1/forecast?'+urlencode(params)
        try:
            batch=_fetch_json_with_retries(url, WEATHER_TIMEOUT_SECONDS, attempts=2)
            if len(group)==1 and isinstance(batch,dict):
                batch=[batch]
            if not isinstance(batch,list) or len(batch)!=len(group):
                raise ValueError(f'Unexpected Open-Meteo batch response shape: {type(batch).__name__}')
            for x,item in zip(group,batch):
                packets[x['id']]=fetch_live_weather(x, force=True, data_override=item)
        except Exception as exc:
            err=f'{type(exc).__name__}: {exc}'
            for x in group:
                packets[x['id']]=_missing_or_cached_packet(x, err)

    # Elevation is static and cached; parallel first-load calls keep the dashboard
    # responsive without substituting local constants when the source is absent.
    uncached=[x for x in LOCATIONS if x['id'] not in TERRAIN_CACHE]
    if uncached:
        with ThreadPoolExecutor(max_workers=min(6,len(uncached))) as pool:
            list(pool.map(fetch_terrain_profile,uncached))

    data=[enrich_with_live(x,packets[x['id']]) for x in LOCATIONS]
    LIVE_REGIONAL_CACHE['ts']=now
    LIVE_REGIONAL_CACHE['data']=data
    return data

class PortalLoginRequest(BaseModel):
    portal: Literal['ADMIN','FIELD_OFFICER']
    access_key: str = Field(default='', max_length=256)
    officer_code: Optional[str] = Field(default=None, max_length=80)


class AlertFeedback(BaseModel):
    outcome: Literal['CONFIRMED','FALSE_ALARM','PARTIAL']
    note: str = Field(default='', max_length=500)

class AlertTransition(BaseModel):
    to_status: Literal['REVIEWED','ISSUED','ACKNOWLEDGED','RESOLVED']
    note: str = Field(default='', max_length=500)


class ManualAlertCreate(BaseModel):
    location_id: int = Field(ge=1)
    level: Literal['LOW','MODERATE','HIGH','CRITICAL'] = 'MODERATE'
    message: str = Field(min_length=10, max_length=500)


class NotificationRecipientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone_e164: str = Field(min_length=8, max_length=16)
    location_id: Optional[int] = None
    language: Literal['en','hi','as'] = 'en'
    sms_enabled: bool = True
    consent_confirmed: bool = False
    household_label: Optional[str] = Field(default=None, max_length=120)
    village: Optional[str] = Field(default=None, max_length=120)
    household_size: Optional[int] = Field(default=None, ge=1, le=50)


class NotificationRecipientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    location_id: Optional[int] = None
    language: Optional[Literal['en','hi','as']] = None
    sms_enabled: Optional[bool] = None
    consent_status: Optional[Literal['ACTIVE','REVOKED']] = None
    household_label: Optional[str] = Field(default=None, max_length=120)
    village: Optional[str] = Field(default=None, max_length=120)
    household_size: Optional[int] = Field(default=None, ge=1, le=50)


class FieldHouseholdCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone_e164: str = Field(min_length=8, max_length=16)
    language: Literal['en','hi','as'] = 'en'
    consent_confirmed: bool = False
    household_label: Optional[str] = Field(default=None, max_length=120)
    village: Optional[str] = Field(default=None, max_length=120)
    household_size: Optional[int] = Field(default=None, ge=1, le=50)
    # Used only by ADMIN/DEV_OPERATOR. FIELD_OFFICER posting always overrides it.
    location_id: Optional[int] = None


class FieldHouseholdUpdate(BaseModel):
    language: Optional[Literal['en','hi','as']] = None
    consent_status: Optional[Literal['ACTIVE','REVOKED']] = None
    household_label: Optional[str] = Field(default=None, max_length=120)
    village: Optional[str] = Field(default=None, max_length=120)
    household_size: Optional[int] = Field(default=None, ge=1, le=50)


class AlertBroadcastRequest(BaseModel):
    note: str = Field(default='Admin initiated external alert broadcast', max_length=500)
    retry_failed: bool = False
    scope: Literal['ALERT_AREA','SPECIFIC_AREA','ALL_MONITORED'] = 'ALERT_AREA'
    target_location_id: Optional[int] = None


class RiskInput(BaseModel):
    rainfall: float = Field(ge=0, le=500, description='Observed/estimated rainfall over the latest 24 h')
    soil_moisture: float = Field(ge=0, le=100)
    slope: float = Field(ge=0, le=90)
    elevation: float = Field(default=1200, ge=0, le=9000)
    historical_risk: float = Field(default=0.5, ge=0, le=1)
    ndvi: float = Field(default=0.65, ge=-1, le=1)
    antecedent_rainfall_72h: Optional[float] = Field(default=None, ge=0, le=1500)
    cumulative_rainfall_7d: Optional[float] = Field(default=None, ge=0, le=3500)
    effective_rainfall_11d: Optional[float] = Field(default=None, ge=0, le=4000)
    rain_forecast_24h: Optional[float] = Field(default=None, ge=0, le=700)
    max_hourly_rain_24h: Optional[float] = Field(default=None, ge=0, le=250)
    month: Optional[int] = Field(default=None, ge=1, le=12)
    rainfall_intensity: Optional[float] = Field(default=None, ge=0, le=500)
    tilt_deg: Optional[float] = Field(default=None, ge=-90, le=90)
    vibration_g: Optional[float] = Field(default=None, ge=0, le=20)
    pore_pressure_kpa: Optional[float] = Field(default=None, ge=0, le=1000)
    displacement_mm: Optional[float] = Field(default=None, ge=0, le=10000)
    telemetry_quality: Optional[float] = Field(default=None, ge=0, le=1)
    method: Literal['baseline','experimental_ensemble'] = 'baseline'
    location_id: Optional[int] = None
    location_name: Optional[str] = None


class AlertCreate(BaseModel):
    location_id: Optional[int] = None
    location: str
    level: str
    risk_percent: float
    source: str = "risk-engine"


def db():
    return connect_database(DB, DATABASE_URL)


def init_db():
    initialize_schema(db)


init_db()

def _load_persisted_locations():
    try:
        con=db()
        rows=con.execute("SELECT id,name,state,country,lat,lon,source,source_ref FROM monitored_locations WHERE active=1 ORDER BY id").fetchall()
        con.close()
        known={x['id'] for x in LOCATIONS}
        for row in rows:
            item=dict(row)
            if item['id'] not in known:
                LOCATIONS.append(item); known.add(item['id'])
    except Exception:
        # Location persistence must not prevent the API from starting.
        return

_load_persisted_locations()


def clamp(v, lo=0.0, hi=1.0):
    return min(max(v, lo), hi)


def risk_score(x: RiskInput):
    vals={
        'rainfall':x.rainfall,'soil_moisture':x.soil_moisture,'slope':x.slope,'elevation':x.elevation,
        'historical_risk':x.historical_risk,'ndvi':x.ndvi,
    }
    for key in ('antecedent_rainfall_72h','cumulative_rainfall_7d','effective_rainfall_11d','rain_forecast_24h','max_hourly_rain_24h','month','rainfall_intensity','tilt_deg','vibration_g','pore_pressure_kpa','displacement_mm','telemetry_quality'):
        value=getattr(x,key,None)
        if value is not None: vals[key]=value
    return ml_predict(vals)



def action_for(level):
    return {
        "LOW":"Routine monitoring; no immediate action required.",
        "MODERATE":"Increase monitoring frequency and verify drainage/slope conditions.",
        "HIGH":"Issue local advisory, inspect vulnerable slopes and prepare route diversions.",
        "CRITICAL":"Trigger emergency warning, restrict vulnerable routes and activate response teams."
    }[level]


def alert_texts(location, level):
    return {
        "en": f"PRAHARI screening indicates {level} landslide concern near {location}. This is an advisory for review, not an issued public warning. Avoid vulnerable slopes and follow authorized local instructions.",
        "hi": f"{location} के पास भूस्खलन का {level} जोखिम पाया गया है। संवेदनशील ढलानों से दूर रहें और स्थानीय प्रशासन के निर्देशों का पालन करें।",
        "as": f"{location} অঞ্চলৰ ওচৰত ভূমিস্খলনৰ {level} আশংকা ধৰা পৰিছে। বিপদজনক ঢাল এৰাই চলক আৰু স্থানীয় কৰ্তৃপক্ষৰ নিৰ্দেশ মানক।"
    }


def create_alert(location_id, location, level, risk_percent, source="risk-engine", dedupe_seconds=120):
    """Create a DRAFT advisory. Creating an assessment never equals issuing a public warning."""
    if level not in ("HIGH", "CRITICAL"):
        return None
    con=db(); cur=con.cursor(); cutoff=int(time.time())-dedupe_seconds
    row=cur.execute("SELECT * FROM alerts WHERE location=? AND level=? AND source=? AND lifecycle_status!='RESOLVED' AND created_at>=? ORDER BY id DESC LIMIT 1",
                    (location,level,source,cutoff)).fetchone()
    if row:
        con.close(); return dict(row)
    msgs=alert_texts(location,level); now=int(time.time())
    aid=insert_row(cur, """INSERT INTO alerts(location_id,location,level,risk_percent,message_en,message_hi,message_as,
        recommended_action,source,acknowledged,created_at,lifecycle_status,advisory_type,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (location_id,location,level,risk_percent,msgs['en'],msgs['hi'],msgs['as'],action_for(level),source,0,now,'DRAFT','ADVISORY',now))

    cur.execute("INSERT INTO alert_audit(alert_id,from_status,to_status,actor_role,note,created_at) VALUES(?,?,?,?,?,?)",
                (aid,None,'DRAFT','SYSTEM','Assessment created draft advisory; operator review required',now))
    cur.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",('ALERT_DRAFT_CREATED',f'{level} draft advisory for {location}',now))
    con.commit(); row=cur.execute('SELECT * FROM alerts WHERE id=?',(aid,)).fetchone(); con.close(); return dict(row)

def seed_baseline_alerts():
    # v9 deliberately does not generate warnings on application startup.
    return []

def _delivery_summary(alert_id:int) -> dict:
    con=db()
    rows=con.execute("SELECT channel,status,COUNT(*) c FROM notification_deliveries WHERE alert_id=? GROUP BY channel,status",(alert_id,)).fetchall()
    bulk=con.execute("SELECT status,COUNT(*) c FROM broadcast_items WHERE alert_id=? GROUP BY status",(alert_id,)).fetchall()
    con.close()
    summary={'sms':{}}
    for r in rows:
        summary.setdefault(r['channel'],{})[str(r['status']).upper()]=r['c']
    for r in bulk:
        key=str(r['status']).upper()
        summary['sms'][key]=summary['sms'].get(key,0)+r['c']
    return summary


def localized_alert(row, language="en"):
    if not row: return None
    d=dict(row); key=f"message_{language}" if language in ('en','hi','as') else 'message_en'
    d['message']=d.get(key) or d.get('message_en'); d['acknowledged']=bool(d.get('acknowledged'))
    delivery=_delivery_summary(d['id']) if d.get('id') else {'sms':{}}
    cfg=notification_config_status()
    if BROADCAST_ENABLED and BROADCAST_PROVIDER == 'msg91':
        from msg91_provider import status as msg91_status
        cfg={'sms':{'ready':msg91_status()['ready']}}
    def channel_state(name, enabled):
        counts=delivery.get(name,{})
        delivered=sum(counts.get(k,0) for k in ('DELIVERED','READ'))
        failed=sum(counts.get(k,0) for k in FAILED_DELIVERY_STATUSES)
        accepted=sum(counts.get(k,0) for k in ('QUEUED','ACCEPTED','SENDING','SENT'))
        return {
            'status':'ENABLED' if enabled else 'DISABLED',
            'ready':bool(cfg.get(name,{}).get('ready')),
            'confirmed_delivery':delivered>0,
            'delivered':delivered,'accepted_or_sent':accepted,'failed':failed,'counts':counts,
        }
    d['channels']={
        'command_center':{'status':'LOCAL_RECORD','confirmed_delivery':True},
        'browser':{'status':'LOCAL_UI_ONLY','confirmed_delivery':False},
        'sms':channel_state('sms',EXTERNAL_SMS_ENABLED or (BROADCAST_ENABLED and BROADCAST_PROVIDER == 'msg91')),
    }
    d['broadcast_queue_enabled']=BROADCAST_ENABLED
    d['public_warning_issued']=bool(d.get('issued_at'))
    d['delivery_note']='External delivery is confirmed only from provider delivery/read status, never from a button click.'
    for k in ('message_en','message_hi','message_as'): d.pop(k,None)
    return d


def _recipient_public(row):
    d=dict(row)
    d['sms_enabled']=bool(d.get('sms_enabled'))
    d.pop('whatsapp_enabled', None)
    return d


def _alert_broadcast_text(alert:dict, language:str='en', sms:bool=False) -> str:
    location=alert.get('location') or 'the selected area'; level=alert.get('level') or 'HIGH'
    if alert.get('advisory_type')=='MANUAL':
        # Preserve the reviewed message, including its language and complete instructions.
        return f"PRAHARI | {location}\n{alert.get('message_en') or ''}"
    if language=='hi':
        text=f"PRAHARI सलाह: {location} में भूस्खलन का {level} जोखिम। संवेदनशील ढलानों/सड़कों से दूर रहें और अधिकृत स्थानीय निर्देशों का पालन करें।"
    elif language=='as':
        text=f"PRAHARI পৰামৰ্শ: {location} ত ভূমিস্খলনৰ {level} আশংকা। বিপদজনক ঢাল/পথ এৰাই চলক আৰু অনুমোদিত স্থানীয় নিৰ্দেশ মানক।"
    else:
        text=f"PRAHARI advisory: {level} landslide concern near {location}. Avoid vulnerable slopes/roads and follow authorized local instructions."
    if sms and len(text) > 300:
        text=text[:297]+'...'
    return text


def _eligible_recipients(alert:dict, scope:str='ALERT_AREA', target_location_id:int|None=None):
    scope=(scope or 'ALERT_AREA').upper()
    con=db()
    if scope=='ALL_MONITORED':
        rows=con.execute("SELECT * FROM notification_recipients WHERE consent_status='ACTIVE' AND sms_enabled=1 ORDER BY id").fetchall()
    else:
        location_id = target_location_id if scope=='SPECIFIC_AREA' else alert.get('location_id')
        if location_id is None:
            rows=con.execute("SELECT * FROM notification_recipients WHERE consent_status='ACTIVE' AND sms_enabled=1 ORDER BY id").fetchall()
        else:
            if not any(x['id']==location_id for x in LOCATIONS):
                con.close(); raise HTTPException(400,'Unknown target alert area')
            rows=con.execute("SELECT * FROM notification_recipients WHERE consent_status='ACTIVE' AND sms_enabled=1 AND (location_id=? OR location_id IS NULL) ORDER BY id",(location_id,)).fetchall()
    con.close()
    # A household may have been enrolled more than once during migration/admin cleanup.
    # Never send the same alert twice to the same phone number in one broadcast.
    unique=[]; seen=set()
    for row in rows:
        d=dict(row); phone=d.get('phone_e164')
        if phone in seen: continue
        seen.add(phone); unique.append(d)
    return unique


def _broadcast_target_label(scope:str, alert:dict, target_location_id:int|None=None):
    scope=(scope or 'ALERT_AREA').upper()
    if scope=='ALL_MONITORED':
        return 'All monitored areas'
    location_id=target_location_id if scope=='SPECIFIC_AREA' else alert.get('location_id')
    loc=next((x for x in LOCATIONS if x['id']==location_id),None)
    return f"{loc['name']}, {loc['state']}" if loc else (alert.get('location') or 'Selected alert area')


def _upsert_delivery(alert_id:int, recipient_id:int, channel:str, *, status:str, provider:str='twilio', sid:str|None=None, error_code:str|None=None, error_message:str|None=None):
    now=int(time.time()); con=db(); cur=con.cursor()
    existing=cur.execute("SELECT id FROM notification_deliveries WHERE alert_id=? AND recipient_id=? AND channel=?",(alert_id,recipient_id,channel)).fetchone()
    if existing:
        cur.execute("""UPDATE notification_deliveries SET provider=?,provider_message_sid=?,status=?,error_code=?,error_message=?,updated_at=?,attempted_at=?,delivered_at=NULL,read_at=NULL WHERE id=?""",
                    (provider,sid,status,error_code,error_message,now,now,existing['id']))
        did=existing['id']
    else:
        did=insert_row(cur, """INSERT INTO notification_deliveries(alert_id,recipient_id,channel,provider,provider_message_sid,status,error_code,error_message,attempted_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (alert_id,recipient_id,channel,provider,sid,status,error_code,error_message,now,now))

    con.commit(); row=cur.execute("SELECT * FROM notification_deliveries WHERE id=?",(did,)).fetchone(); con.close(); return dict(row)


def _record_provider_status(message_sid:str,status:str,error_code:str|None=None,error_message:str|None=None):
    status=(status or 'UNKNOWN').upper(); now=int(time.time()); con=db(); cur=con.cursor()
    row=cur.execute("SELECT * FROM notification_deliveries WHERE provider_message_sid=?",(message_sid,)).fetchone()
    if not row:
        con.close(); return None
    delivered_at=now if status in ('DELIVERED','READ') else row['delivered_at']
    read_at=now if status=='READ' else row['read_at']
    cur.execute("UPDATE notification_deliveries SET status=?,error_code=?,error_message=?,updated_at=?,delivered_at=?,read_at=? WHERE id=?",
                (status,error_code,error_message,now,delivered_at,read_at,row['id']))
    con.commit(); out=cur.execute("SELECT * FROM notification_deliveries WHERE id=?",(row['id'],)).fetchone(); con.close(); return dict(out)

def satellite_packet(x):
    return {
        'location_id':x['id'],'location':f"{x['name']}, {x['state']}",'coordinates':{'lat':x['lat'],'lon':x['lon']},
        'pipeline_status':'SCENE_DISCOVERY_IMPLEMENTED','imagery_basemap':'NASA GIBS / Esri imagery when reachable',
        'terrain_basemap':'OpenTopoMap when reachable','analysis_mode':'SENTINEL2_SCENE_QA_PLUS_VISUAL_CONTEXT',
        'risk_level':x.get('risk_level','UNKNOWN'),'risk_percent':x.get('risk_percent'),
        'terrain_context':{'slope_deg':x.get('slope'),'elevation_m':x.get('elevation'),'source_state':x.get('terrain_state','NOT_FETCHED'),'source':x.get('terrain_source')},
        'scene_discovery':{'provider':'Element 84 Earth Search','collection':'sentinel-2-l2a','status':'IMPLEMENTED',
                           'note':'PRAHARI searches real Sentinel-2 L2A acquisitions and identifies recent/reference scene pairs using acquisition date and cloud metadata.'},
        'detection_module':{'name':'Landslide4Sense-compatible post-event segmentation','status':'CHECK_MODEL_STATUS_ENDPOINT',
                            'note':'Read /api/satellite/model/status for verified model readiness. Any output is experimental and requires human review.'},
        'provenance':[
            'NASA/Esri imagery tiles remain visual geographic context only.',
            'Sentinel-2 scene dates, cloud cover and asset links come from the live Earth Search STAC catalog.',
            'Scene-pair readiness is not a landslide detection result.',
            'Automatic post-event landslide segmentation remains a separate model stage based on Landslide4Sense-style semantic segmentation.'
        ]
    }

EARTH_SEARCH_STAC = "https://earth-search.aws.element84.com/v1"

def _iso_utc(dt:datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def _sentinel_scene_summary(item:dict) -> dict:
    props=item.get('properties') or {}
    links=item.get('links') or []
    assets=item.get('assets') or {}
    def link(rel):
        row=next((x for x in links if x.get('rel')==rel and x.get('href')),None)
        return row.get('href') if row else None
    def asset_href(*names):
        for name in names:
            a=assets.get(name)
            if isinstance(a,dict) and a.get('href'):
                return a.get('href')
        return None
    return {
        'id':item.get('id'),
        'datetime':props.get('datetime'),
        'cloud_cover_pct':props.get('eo:cloud_cover'),
        'platform':props.get('platform'),
        'mgrs_tile':props.get('grid:code') or props.get('mgrs:utm_zone') or props.get('s2:mgrs_tile'),
        'thumbnail_url':link('thumbnail'),
        'stac_url':link('self'),
        'bbox':item.get('bbox'),
        'assets':{
            'visual':asset_href('visual'),
            'red':asset_href('red','B04'),
            'nir':asset_href('nir','nir08','B08'),
            'swir16':asset_href('swir16','B11'),
            'swir22':asset_href('swir22','B12'),
            'scl':asset_href('scl','SCL')
        }
    }

def _scene_dt(scene:dict):
    try:
        return datetime.fromisoformat(str(scene.get('datetime')).replace('Z','+00:00'))
    except Exception:
        return None

def _choose_scene_pair(scenes:list[dict], min_gap_days:int=10):
    valid=[x for x in scenes if _scene_dt(x)]
    valid.sort(key=lambda x:_scene_dt(x), reverse=True)
    if not valid:
        return None
    recent=valid[0]
    rdt=_scene_dt(recent)
    candidates=[x for x in valid[1:] if (rdt-_scene_dt(x)).days >= min_gap_days]
    if not candidates:
        return {'recent':recent,'reference':None,'days_between':None,'status':'REFERENCE_SCENE_NOT_FOUND'}
    # Prefer a low-cloud reference within ~90 days while preserving temporal separation.
    candidates.sort(key=lambda x:((x.get('cloud_cover_pct') if x.get('cloud_cover_pct') is not None else 999), abs((rdt-_scene_dt(x)).days-30)))
    reference=candidates[0]
    return {'recent':recent,'reference':reference,'days_between':(rdt-_scene_dt(reference)).days,'status':'PAIR_READY'}

def search_sentinel2_scenes(x:dict, days:int=120, max_cloud:float=45.0, limit:int=12):
    end=datetime.now(timezone.utc)
    start=end-timedelta(days=days)
    pad=0.15
    payload={
        'collections':['sentinel-2-l2a'],
        'bbox':[x['lon']-pad,x['lat']-pad,x['lon']+pad,x['lat']+pad],
        'datetime':f"{_iso_utc(start)}/{_iso_utc(end)}",
        'query':{'eo:cloud_cover':{'lte':max_cloud}},
        'limit':max(2,min(50,limit))
    }
    req=UrlRequest(
        EARTH_SEARCH_STAC+'/search',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type':'application/json','Accept':'application/geo+json','User-Agent':'PRAHARI/11.0'},
        method='POST'
    )
    try:
        with urlopen(req, timeout=12) as resp:
            raw=json.loads(resp.read().decode('utf-8'))
        scenes=[_sentinel_scene_summary(item) for item in (raw.get('features') or [])]
        scenes.sort(key=lambda x:_scene_dt(x) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        pair=_choose_scene_pair(scenes)
        return {
            'status':'AVAILABLE' if scenes else 'NO_SCENES',
            'provider':'Element 84 Earth Search',
            'collection':'sentinel-2-l2a',
            'location_id':x['id'],'location':f"{x['name']}, {x['state']}",
            'searched_at':int(time.time()),'search_days':days,'max_cloud_pct':max_cloud,
            'scene_count':len(scenes),'scenes':scenes,'pair':pair,
            'analysis_status':'SCENE_PAIR_READY' if pair and pair.get('status')=='PAIR_READY' else 'SCENE_DISCOVERY_ONLY',
            'segmentation_status':'CHECK_MODEL_STATUS_ENDPOINT',
            'note':'Real Sentinel-2 scene discovery is active. Scene pairing and cloud metadata are quality-control steps, not a landslide detection result.'
        }
    except Exception as exc:
        return {
            'status':'SOURCE_UNAVAILABLE','provider':'Element 84 Earth Search','collection':'sentinel-2-l2a',
            'location_id':x['id'],'location':f"{x['name']}, {x['state']}",'scene_count':0,'scenes':[],'pair':None,
            'analysis_status':'UNAVAILABLE','segmentation_status':'CHECK_MODEL_STATUS_ENDPOINT',
            'error':f'{type(exc).__name__}: {exc}',
            'note':'Sentinel-2 catalog lookup failed. PRAHARI does not invent satellite scenes.'
        }

@app.get("/api/satellite/sentinel2/{location_id}", tags=["Satellite Intelligence"])
def sentinel2_scenes(location_id:int, days:int=Query(120,ge=14,le=365), max_cloud:float=Query(45,ge=0,le=100), limit:int=Query(12,ge=2,le=30)):
    x=next((z for z in LOCATIONS if z['id']==location_id),None)
    if not x:
        raise HTTPException(404,'Location not found')
    return search_sentinel2_scenes(x,days=days,max_cloud=max_cloud,limit=limit)

@app.get("/api/satellite/architecture", tags=["Satellite Intelligence"])
def satellite_architecture():
    return {
        'post_event_detection':{
            'status':'EXPERIMENTAL_INTEGRATION',
            'implemented':['Sentinel-2 L2A scene discovery','cloud metadata QA','visual scene pairing',
                           'live L1C/terrain patch preparation','verified-checkpoint inference adapter',
                           'background jobs','pixel masks and unreviewed candidate polygons'],
            'requires_configuration':['trained compatible weights','matching training-derived input profile'],
            'pending':['preprocessing parity verification','regional accuracy validation','human review of candidates'],
            'model_status_endpoint':'/api/satellite/model/status',
            'preprocess_status_endpoint':'/api/satellite/preprocess/status'
        },
        'susceptibility':{'status':'SCREENING_ONLY','note':'Terrain context uses provider elevation samples; no validated susceptibility raster is claimed.'},
        'deformation_monitoring':{'status':'ROADMAP','note':'Sentinel-1/InSAR slope-deformation monitoring is intentionally separate from optical post-event detection.'},
        'research_basis':{
            'landslide4sense':'Official benchmark uses 12 Sentinel-2 multispectral bands plus slope and DEM at approximately 10 m pixels.',
            'earth_search':'Earth Search provides STAC discovery and cloud-optimized Sentinel-2 L2A assets.'
        }
    }


@app.get("/api/satellite/model/status", tags=["Satellite Intelligence"])
def satellite_model_status(role:str=Depends(resolve_role)):
    if AUTH_REQUIRED and role == 'PUBLIC':
        raise HTTPException(403,'Authenticated PRAHARI session required')
    return l4s_status()

@app.get("/api/satellite/preprocess/status", tags=["Satellite Intelligence"])
def satellite_preprocess_status(role:str=Depends(resolve_role)):
    if AUTH_REQUIRED and role == 'PUBLIC':
        raise HTTPException(403,'Authenticated PRAHARI session required')
    return satprep_status()

_SATELLITE_LOCK = Lock()
_SATELLITE_PATCHES = OrderedDict()


def _satellite_work(location_id, operation, *, days=120, max_cloud=35, patch_id=None, progress=None):
    if not _SATELLITE_LOCK.acquire(blocking=False):
        raise RuntimeError("Satellite processing is busy. Try again when the current operation completes.")
    try:
        return _satellite_process(location_id, operation, days=days, max_cloud=max_cloud, patch_id=patch_id, progress=progress)
    finally:
        _SATELLITE_LOCK.release()


def _satellite_process(location_id, operation, *, days, max_cloud, patch_id, progress):
    progress = progress or (lambda stage: None)
    location = next((row for row in LOCATIONS if row["id"] == location_id), None)
    if not location:
        raise ValueError("Location not found.")
    model = None
    if operation == "infer":
        progress("Checking model and input configuration")
        model = l4s_status()
        if model.get("status") != "READY" or model.get("verified") is not True:
            raise RuntimeError(model.get("reason") or "Model is not verified and ready.")
        prep = satprep_status()
        if not prep.get("live_inference_ready"):
            raise RuntimeError(prep.get("input_profile_error") or "Enable experimental preprocessing after reviewing SATELLITE_SETUP.md.")
        if prep.get("profile_checkpoint_sha256") != model.get("checkpoint_sha256"):
            raise RuntimeError("The input profile belongs to a different model checkpoint.")
    now = time.time()
    for key, value in list(_SATELLITE_PATCHES.items()):
        if now - value["created_at"] > 3600:
            del _SATELLITE_PATCHES[key]
    if patch_id:
        cached = _SATELLITE_PATCHES.get(patch_id)
        if not cached or cached["location_id"] != location_id:
            raise ValueError("Prepared patch expired or belongs to another location. Prepare it again.")
        patch, meta = cached["patch"], deepcopy(cached["meta"])
        progress("Reusing prepared patch")
    else:
        patch, meta = satprep_prepare_patch(location["lat"], location["lon"], days=days, max_cloud=max_cloud, persist=False, progress=progress)
        _SATELLITE_PATCHES[meta["patch_id"]] = {"patch": patch, "meta": deepcopy(meta), "location_id": location_id, "created_at": time.time()}
        while len(_SATELLITE_PATCHES) > 8:
            _SATELLITE_PATCHES.popitem(last=False)
    label = f"{location['name']}, {location['state']}"
    if operation == "prepare":
        return {**satprep_patch_summary(meta), "status": "PATCH_READY", "location_id": location_id, "location": label,
                "note": "Research input prepared. This is not a detection result."}
    progress("Running experimental segmentation")
    prepared = satprep_model_input(patch, meta, model["checkpoint_sha256"])
    inference = l4s_infer_patch(prepared)
    if inference.get("checkpoint_sha256") != model["checkpoint_sha256"]:
        raise RuntimeError("The model changed during processing. Retry with its matching input profile.")
    scores = inference.pop("score_grid", None)
    if scores is None:
        raise RuntimeError("The inference worker did not return a score grid.")
    progress("Generating mask and candidate polygons")
    polygons = satprep_candidate_geojson(inference["mask_rle"], meta, scores=np.asarray(scores))
    overlay = satprep_mask_overlay(inference["mask_rle"], meta)
    return {
        "status": "EXPERIMENTAL_MODEL_OUTPUT", "location_id": location_id, "location": label,
        "patch": satprep_patch_summary(meta), "inference": inference,
        "candidate_polygons": polygons, "mask_overlay": overlay,
        "human_review_required": True,
        "warning": "Unreviewed post-event model candidates, not verified landslides, forecasts, or public warnings.",
    }


class SatelliteJobRequest(BaseModel):
    operation: Literal["prepare", "infer"]
    confirm_experimental: bool = False
    patch_id: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    days: int = Field(default=120, ge=14, le=365)
    max_cloud: float = Field(default=35, ge=0, le=100)


@app.post("/api/satellite/jobs/{location_id}", status_code=202, tags=["Satellite Intelligence"])
def satellite_start_job(location_id: int, body: SatelliteJobRequest, role: str = Depends(resolve_role)):
    require_role(role, "ADMIN")
    if not body.confirm_experimental:
        raise HTTPException(400, "Confirm the experimental limitations before processing.")
    if not any(row["id"] == location_id for row in LOCATIONS):
        raise HTTPException(404, "Location not found.")
    try:
        return satellite_jobs.submit(location_id, body.operation, lambda progress: _satellite_work(
            location_id, body.operation, days=body.days, max_cloud=body.max_cloud, patch_id=body.patch_id, progress=progress))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/satellite/jobs/status/{job_id}", tags=["Satellite Intelligence"])
def satellite_job_status(job_id: str, role: str = Depends(resolve_role)):
    require_role(role, "ADMIN")
    job = satellite_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job expired or the service restarted. Start a new operation.")
    return job


def _satellite_sync(location_id, operation, days, max_cloud, confirm_experimental, role):
    require_role(role, "ADMIN")
    if not confirm_experimental:
        raise HTTPException(400, "Confirm the experimental limitations before processing.")
    if not any(row["id"] == location_id for row in LOCATIONS):
        raise HTTPException(404, "Location not found.")
    try:
        return _satellite_work(location_id, operation, days=days, max_cloud=max_cloud)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/satellite/preprocess/{location_id}", tags=["Satellite Intelligence"])
def satellite_prepare_location_patch(location_id: int, days: int = Query(120, ge=14, le=365),
                                     max_cloud: float = Query(35, ge=0, le=100),
                                     confirm_experimental: bool = False, role: str = Depends(resolve_role)):
    return _satellite_sync(location_id, "prepare", days, max_cloud, confirm_experimental, role)


@app.post("/api/satellite/model/infer-location/{location_id}", tags=["Satellite Intelligence"])
def satellite_infer_location(location_id: int, days: int = Query(120, ge=14, le=365),
                             max_cloud: float = Query(35, ge=0, le=100),
                             confirm_experimental: bool = False, role: str = Depends(resolve_role)):
    return _satellite_sync(location_id, "infer", days, max_cloud, confirm_experimental, role)


@app.post("/api/satellite/model/infer-patch", tags=["Satellite Intelligence"])
async def satellite_model_infer_patch(file: UploadFile = File(...), role: str = Depends(resolve_role)):
    require_role(role, "ADMIN")
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Upload a 128×128×14 float32 NPY patch (maximum 2 MiB).")
    if not (file.filename or "").lower().endswith(".npy"):
        raise HTTPException(400, "Upload a NPY array using the Landslide4Sense input contract.")
    try:
        from satellite_l4s import read_patch_bytes
        arr = read_patch_bytes(content)
        result = await run_in_threadpool(l4s_infer_patch, arr)
        result.pop("score_grid", None)
        result["source_contract"] = "Uploaded benchmark-compatible 14-channel patch; input provenance not verified."
        return result
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.on_event("startup")
def startup_seed():
    init_db()


@app.get("/")
def root():
    return {"service":"PRAHARI","status":"ok","version":"11.0.0","mode":"live-hilly-region-monitoring"}


@app.get("/api/system/status")
def status():
    con = db()
    alert_count = con.execute("SELECT COUNT(*) c FROM alerts WHERE acknowledged=0").fetchone()['c']
    con.close()
    return {
        "api":"online",
        "database":"online",
        "database_storage":storage_status(DATABASE_URL, hosted=bool(os.getenv("RENDER"))),
        "risk_engine":"transparent-screening",
        "alert_engine":"draft-advisory-lifecycle; operator review required",
        "browser_notifications":"frontend-ready",
        "satellite_intelligence":"Sentinel-2 live scene discovery/pairing + optional Landslide4Sense-compatible U-Net adapter; live 14-channel research patch preparation; inference requires verified weights and matching input profile",
        "map":"offline EO Lite / cached NASA / street / terrain / satellite",
        "weather":"Open-Meteo current/stale/missing states; no invented live fallback",
        "live_risk_refresh":"5-minute cache / manual force refresh",
        "satellite_nrt":"NASA GIBS VIIRS NRT with pre-warm local tile cache",
        "unacknowledged_alerts":alert_count,
        "last_sync":int(time.time()),
        "historical_replay_mode":False,
        "auth_required":AUTH_REQUIRED
    }


@app.get("/api/ml/status")
def machine_learning_status():
    return {
        "status":"NOT_DEPLOYED",
        "operational":False,
        "reason":"No spatially and temporally validated all-hilly-region susceptibility model is deployed."
    }

@app.get("/api/ml/feature-importance")
def machine_learning_feature_importance():
    return []


@app.get("/api/locations")
def locations():
    return locs()


@app.get("/api/live/locations")
def live_locations(force:bool=False, mode:Literal['live','replay']='live'):
    return live_locs(force=force, mode=mode)


@app.get("/api/live/locations/{location_id}")
def live_location(location_id:int, force:bool=False, mode:Literal['live','replay']='live'):
    x = next((z for z in LOCATIONS if z['id']==location_id), None)
    if not x:
        raise HTTPException(404,"Location not found")
    packet=build_replay_packet(x) if mode=='replay' else fetch_live_weather(x, force=force)
    return enrich_with_live(x, packet)

@app.post("/api/live/browser-relay/{location_id}", tags=["System"])
def browser_relay_live(location_id:int, body:dict, role:str=Depends(resolve_role)):
    raise HTTPException(410,'Client-relayed weather is disabled; live assessments use server-fetched provider data only')

@app.post("/api/assessments/{location_id}/browser-relay", tags=["Assessments"])
def record_browser_relay_assessment(location_id:int, body:dict, role:str=Depends(resolve_role)):
    raise HTTPException(410,'Client-relayed assessments are disabled; record an assessment from the server-fetched live source')

@app.get("/api/live/diagnostics/{location_id}", tags=["System"])
def live_diagnostics(location_id:int, force:bool=True, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    x=next((z for z in LOCATIONS if z['id']==location_id),None)
    if not x:
        raise HTTPException(404,'Location not found')
    packet=fetch_live_weather(x, force=force)
    return {
        'location_id':location_id,
        'location':f"{x['name']}, {x['state']}",
        'availability':packet.get('availability'),
        'source':packet.get('source'),
        'valid_time':packet.get('valid_time'),
        'updated_at':packet.get('updated_at'),
        'error':packet.get('error'),
        'note':packet.get('note'),
        'has_rainfall_24h':packet.get('rainfall_24h_mm') is not None,
        'has_rainfall_72h':packet.get('antecedent_rainfall_72h_mm') is not None,
        'has_soil_moisture':packet.get('soil_moisture_proxy_pct') is not None,
        'provider':'Open-Meteo'
    }


def _save_assessment(location_id:int, mode:str, result:dict) -> int:
    con=db(); cur=con.cursor(); now=int(time.time())
    aid=insert_row(cur, """INSERT INTO assessments(location_id,location,mode,assessment_kind,risk_level,risk_score,data_completeness,model_version,inputs_json,sources_json,result_json,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(location_id,f"{result['name']}, {result['state']}",mode,result.get('assessment_kind'),result.get('risk_level'),result.get('risk_percent'),result.get('data_completeness_pct'),result.get('assessment_version'),
        json.dumps({'rainfall_24h_mm':result.get('rainfall'),'antecedent_rainfall_72h_mm':result.get('antecedent_rainfall_72h'),'soil_wetness_pct':result.get('soil_moisture'),'slope_deg':result.get('slope')}),json.dumps(result.get('sources',[])),json.dumps(result),now))
    con.commit(); con.close(); return aid

@app.post('/api/assessments/{location_id}')
def run_assessment(location_id:int, mode:Literal['live','replay']='live', force:bool=False, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    x=next((z for z in LOCATIONS if z['id']==location_id),None)
    if not x: raise HTTPException(404,'Location not found')
    packet=build_replay_packet(x) if mode=='replay' else fetch_live_weather(x,force=force)
    result=enrich_with_live(x,packet); assessment_id=_save_assessment(location_id,mode,result)
    draft=None
    if result.get('assessment_status')=='ASSESSED' and result.get('risk_level') in ('HIGH','CRITICAL'):
        draft=create_alert(location_id,f"{x['name']}, {x['state']}",result['risk_level'],result.get('risk_percent') or 0,
                           'assessment-'+mode,dedupe_seconds=300)
    return {'assessment_id':assessment_id,'assessment':result,'draft_advisory':localized_alert(draft,'en') if draft else None,
            'note':'High/critical assessments create a DRAFT advisory only. A reviewer must issue it explicitly.'}

@app.get('/api/assessments/{location_id}/history')
def assessment_history(location_id:int, limit:int=Query(20,ge=1,le=100)):
    if not any(x['id']==location_id for x in LOCATIONS): raise HTTPException(404,'Location not found')
    con=db(); rows=con.execute('SELECT id,location_id,location,mode,assessment_kind,risk_level,risk_score,data_completeness,model_version,created_at FROM assessments WHERE location_id=? ORDER BY id DESC LIMIT ?',(location_id,limit)).fetchall(); con.close()
    return [dict(r) for r in rows]

@app.get('/api/assessment-records/{assessment_id}/export')
def export_assessment(assessment_id:int, format:Literal['json','csv']='json'):
    con=db(); row=con.execute('SELECT * FROM assessments WHERE id=?',(assessment_id,)).fetchone(); con.close()
    if not row: raise HTTPException(404,'Assessment not found')
    r=dict(row); result=json.loads(r['result_json']); sources=json.loads(r['sources_json']); inputs=json.loads(r['inputs_json'])
    export={'assessment_id':assessment_id,'location':r['location'],'created_at':r['created_at'],'mode':r['mode'],'assessment_kind':r['assessment_kind'],
            'risk_level':r['risk_level'],'risk_index':r['risk_score'],'data_completeness_pct':r['data_completeness'],'model_version':r['model_version'],
            'inputs':inputs,'sources':sources,'factors':result.get('factors',[]),'limitations':result.get('assessment_limitations',[]),
            'disclaimer':'PRAHARI is decision-support. This export is not an authorized public warning or evacuation order.'}
    if format=='json':
        payload=json.dumps(export,indent=2,ensure_ascii=False).encode('utf-8')
        return Response(payload,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="prahari_assessment_{assessment_id}.json"'})
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(['field','value'])
    for k in ['assessment_id','location','created_at','mode','assessment_kind','risk_level','risk_index','data_completeness_pct','model_version','disclaimer']:
        w.writerow([k,export.get(k)])
    w.writerow(['inputs_json',json.dumps(inputs)]); w.writerow(['sources_json',json.dumps(sources)]); w.writerow(['factors_json',json.dumps(export['factors'])]); w.writerow(['limitations_json',json.dumps(export['limitations'])])
    return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="prahari_assessment_{assessment_id}.csv"'})

class MonitoredLocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=120)
    lat: float = Field(ge=6.0, le=38.5)
    lon: float = Field(ge=67.0, le=98.5)
    source_ref: Optional[str] = Field(default=None, max_length=160)

@app.get('/api/locations/search')
def search_locations(q:str=Query('',min_length=2,max_length=80)):
    query=q.strip()
    params={'name':query,'count':10,'language':'en','format':'json','countryCode':'IN'}
    try:
        raw=_fetch_json_with_retries('https://geocoding-api.open-meteo.com/v1/search?'+urlencode(params),WEATHER_TIMEOUT_SECONDS,attempts=2)
    except Exception as exc:
        raise HTTPException(503,f'Location search is temporarily unavailable: {type(exc).__name__}')
    existing={(round(float(x['lat']),4),round(float(x['lon']),4)):x['id'] for x in LOCATIONS}
    out=[]
    for item in (raw.get('results') or []):
        if str(item.get('country_code') or '').upper()!='IN':
            continue
        lat=item.get('latitude'); lon=item.get('longitude')
        if lat is None or lon is None: continue
        state=item.get('admin1') or item.get('admin2') or 'India'
        out.append({
            'provider_id':str(item.get('id') or ''),'name':item.get('name') or query,'state':state,'country':'India',
            'lat':float(lat),'lon':float(lon),'elevation_m':item.get('elevation'),
            'timezone':item.get('timezone'),'monitored_location_id':existing.get((round(float(lat),4),round(float(lon),4)))
        })
    return out

@app.post('/api/locations', status_code=201)
def add_monitored_location(body:MonitoredLocationCreate, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    for x in LOCATIONS:
        if abs(float(x['lat'])-body.lat)<0.0005 and abs(float(x['lon'])-body.lon)<0.0005:
            return x
    location_id=max([1000]+[int(x['id']) for x in LOCATIONS])+1
    now=int(time.time())
    item={'id':location_id,'name':body.name.strip(),'state':body.state.strip(),'country':'India',
          'lat':float(body.lat),'lon':float(body.lon),'source':'OPEN_METEO_GEOCODING','source_ref':body.source_ref}
    con=db()
    try:
        con.execute("INSERT INTO monitored_locations(id,name,state,country,lat,lon,source,source_ref,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)",
                    (location_id,item['name'],item['state'],'India',item['lat'],item['lon'],item['source'],item['source_ref'],now,now))
        con.commit()
    finally: con.close()
    LOCATIONS.append(item)
    LIVE_REGIONAL_CACHE['data']=None; LIVE_REGIONAL_CACHE['ts']=0
    return item

@app.delete('/api/locations/{location_id}', status_code=204)
def remove_monitored_location(location_id:int, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    target=next((x for x in LOCATIONS if x['id']==location_id),None)
    if not target: raise HTTPException(404,'Location not found')
    if location_id<=1000:
        raise HTTPException(409,'Curated monitoring points cannot be removed')
    con=db()
    try:
        con.execute("UPDATE monitored_locations SET active=0,updated_at=? WHERE id=?",(int(time.time()),location_id));con.commit()
    finally: con.close()
    LOCATIONS[:] = [x for x in LOCATIONS if x['id']!=location_id]
    LIVE_WEATHER_CACHE.pop(location_id,None); TERRAIN_CACHE.pop(location_id,None)
    LIVE_REGIONAL_CACHE['data']=None; LIVE_REGIONAL_CACHE['ts']=0
    return Response(status_code=204)

@app.get("/api/locations/{location_id}")
def location(location_id:int):
    for x in locs():
        if x['id'] == location_id:
            return x
    raise HTTPException(404,"Location not found")


@app.post("/api/predict-risk")
def predict(inp: RiskInput):
    values=inp.model_dump(exclude_none=True)
    if inp.method=='experimental_ensemble':
        if not _test_fixtures_enabled():
            raise HTTPException(410,'Synthetic/bootstrap research ensemble is disabled for operational use')
        result=risk_score(inp); p=float(result['probability']); level=result['level']
        return {
            'assessment_kind':'EXPERIMENTAL_BOOTSTRAP_ENSEMBLE','calibrated_probability':False,
            'risk_probability':None,'experimental_score_percent':round(p*100,1),'risk_percent':round(p*100,1),'risk_level':level,
            'recommended_action':action_for(level),'model_probabilities':result.get('model_probabilities',{}),'shap_local':result.get('shap_local',[]),
            'engine':result.get('engine'),'model_provenance':result.get('provenance'),
            'limitations':['Synthetic/bootstrap training; automated-test use only.','Score is not an operational probability.'],
            'automatic_alert_triggered':False
        }
    base=baseline_assess({
        'rainfall_24h':inp.rainfall,'antecedent_rainfall_72h':inp.antecedent_rainfall_72h,
        'cumulative_rainfall_7d':inp.cumulative_rainfall_7d,'soil_moisture':inp.soil_moisture,'slope':inp.slope,
        'max_hourly_rain_24h':inp.max_hourly_rain_24h,'tilt_deg':inp.tilt_deg,'displacement_mm':inp.displacement_mm,
        'pore_pressure_kpa':inp.pore_pressure_kpa,'telemetry_quality':inp.telemetry_quality
    }, 'MANUAL_TEST' if any(v is not None for v in [inp.tilt_deg,inp.displacement_mm,inp.pore_pressure_kpa]) else None)
    # Stateless screening endpoint: never creates or issues alerts. Persisted advisories are created only through /api/assessments/{location_id}.
    return {
        'assessment_kind':'TRANSPARENT_SCREENING_BASELINE','calibrated_probability':False,'risk_probability':None,
        'risk_percent':base.index,'risk_level':base.level,'assessment_status':base.status,'missing_inputs':base.missing,
        'factors':base.reasons,'limitations':base.limitations,'recommended_action':action_for(base.level) if base.level!='UNKNOWN' else 'Acquire missing observations before assessment.',
        'model_version':BASELINE_VERSION,'automatic_alert_triggered':False,'draft_advisory_created':False,
        'alert':None
    }

@app.get("/api/dashboard/summary")
def summary():
    data = LIVE_REGIONAL_CACHE['data'] or locs()
    critical = sum(x['risk_level']=='CRITICAL' for x in data)
    high = sum(x['risk_level']=='HIGH' for x in data)
    con = db()
    report_count = con.execute("SELECT COUNT(*) c FROM reports").fetchone()['c']
    unacked = con.execute("SELECT COUNT(*) c FROM alerts WHERE acknowledged=0").fetchone()['c']
    con.close()
    assessed=[x for x in data if x.get('risk_percent') is not None]
    return {
        "monitored_zones":len(data),
        "assessed_zones":len(assessed),
        "critical_zones":critical,
        "high_zones":high,
        "active_alerts":unacked,
        "citizen_reports":report_count,
        "avg_risk_index":round(sum(float(x['risk_percent']) for x in assessed)/len(assessed),1) if assessed else None,
        "note":"Risk index is a transparent screening index; no population exposure total is produced without verified GIS."
    }


@app.get("/api/alerts")
def alerts(language:str="en", limit:int=50, lifecycle_status:Optional[str]=None):
    con=db(); sql="SELECT * FROM alerts"; params=[]
    if lifecycle_status:
        sql+=" WHERE lifecycle_status=?"; params.append(lifecycle_status)
    sql+=" ORDER BY created_at DESC, id DESC LIMIT ?"; params.append(min(limit,100))
    rows=con.execute(sql,params).fetchall(); con.close()
    return [localized_alert(r,language) for r in rows]


@app.post('/api/alerts', status_code=201)
def create_manual_advisory(body:ManualAlertCreate, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    location=next((x for x in LOCATIONS if x['id']==body.location_id),None)
    if not location:
        raise HTTPException(400,'Unknown alert area')
    message=body.message.strip()
    if len(message)<10:
        raise HTTPException(400,'Write an advisory message of at least 10 non-padding characters')
    now=int(time.time())
    label=f"{location['name']}, {location['state']}"
    con=db(); cur=con.cursor()
    alert_id=insert_row(cur, """INSERT INTO alerts(location_id,location,level,risk_percent,message_en,
        source,acknowledged,created_at,lifecycle_status,advisory_type,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (body.location_id,label,body.level,None,message,'admin-manual',0,now,'DRAFT','MANUAL',now))

    cur.execute("INSERT INTO alert_audit(alert_id,from_status,to_status,actor_role,note,created_at) VALUES(?,?,?,?,?,?)",
                (alert_id,None,'DRAFT',role,'Administrator created a manual advisory draft',now))
    cur.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",
                ('ALERT_DRAFT_CREATED',f'Manual advisory {alert_id} drafted by {role} for {label}',now))
    con.commit(); row=cur.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone(); con.close()
    return {'ok':True,'alert':localized_alert(row,'en')}


@app.get('/api/alerts/{alert_id}/history')
def alert_history(alert_id:int):
    con=db(); alert=con.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone()
    if not alert:
        con.close(); raise HTTPException(404,'Alert not found')
    rows=con.execute('SELECT * FROM alert_audit WHERE alert_id=? ORDER BY id',(alert_id,)).fetchall(); con.close()
    return {'alert':localized_alert(alert,'en'),'history':[dict(r) for r in rows]}

def _transition_alert(alert_id:int,to_status:str,role:str,note:str=''):
    allowed={
        'DRAFT':{'REVIEWED','RESOLVED'},'REVIEWED':{'ISSUED','RESOLVED'},
        'ISSUED':{'ACKNOWLEDGED','RESOLVED'},'ACKNOWLEDGED':{'RESOLVED'},'RESOLVED':set()
    }
    con=db(); cur=con.cursor(); row=cur.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone()
    if not row:
        con.close(); raise HTTPException(404,'Alert not found')
    current=row['lifecycle_status'] or 'DRAFT'
    if to_status not in allowed.get(current,set()):
        con.close(); raise HTTPException(409,f'Invalid alert transition {current} -> {to_status}')
    now=int(time.time()); fields=['lifecycle_status=?','updated_at=?']; vals=[to_status,now]
    if to_status=='ISSUED': fields.append('issued_at=?'); vals.append(now)
    if to_status=='ACKNOWLEDGED': fields.extend(['acknowledged=1','acknowledged_at=?']); vals.append(now)
    if to_status=='RESOLVED': fields.append('resolved_at=?'); vals.append(now)
    vals.append(alert_id); cur.execute(f"UPDATE alerts SET {','.join(fields)} WHERE id=?",vals)
    cur.execute('INSERT INTO alert_audit(alert_id,from_status,to_status,actor_role,note,created_at) VALUES(?,?,?,?,?,?)',(alert_id,current,to_status,role,note,now))
    cur.execute('INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)',('ALERT_TRANSITION',f'Alert {alert_id}: {current}->{to_status} by {role}',now))
    con.commit(); out=cur.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone(); con.close(); return localized_alert(out,'en')

@app.patch('/api/alerts/{alert_id}/transition')
def transition_alert(alert_id:int, body:AlertTransition, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    if body.to_status=='ISSUED': require_role(role,'REVIEWER')
    return {'ok':True,'alert':_transition_alert(alert_id,body.to_status,role,body.note)}

@app.patch("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id:int, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    return {'ok':True,'alert':_transition_alert(alert_id,'ACKNOWLEDGED',role,'Acknowledged from command center')}

def _field_actor(role:str, x_prahari_key:str|None):
    if role=='FIELD_OFFICER':
        officer=field_officer_for_key(x_prahari_key)
        if not officer:
            raise HTTPException(401,'Field officer key is not recognized')
        loc=next((x for x in LOCATIONS if x['id']==officer.get('location_id')),None)
        if not loc:
            raise HTTPException(403,'Field officer posting is not mapped to a monitored PRAHARI area')
        out=dict(officer); out['posting']=f"{loc['name']}, {loc['state']}"
        return out
    if role in ('ADMIN','DEV_OPERATOR'):
        return None
    raise HTTPException(403,'FIELD_OFFICER or ADMIN role required')


@app.get('/api/field/profile')
def field_profile(x_prahari_key:Optional[str]=Header(default=None,alias='X-PRAHARI-Key'), role:str=Depends(resolve_role)):
    officer=_field_actor(role,x_prahari_key)
    if officer:
        return {'role':'FIELD_OFFICER',**officer}
    return {'role':role,'name':'Administrator / development operator','posting':'All monitored areas','location_id':None}


@app.get('/api/field/households')
def field_households(location_id:Optional[int]=None, x_prahari_key:Optional[str]=Header(default=None,alias='X-PRAHARI-Key'), role:str=Depends(resolve_role)):
    officer=_field_actor(role,x_prahari_key)
    if officer:
        location_id=int(officer['location_id'])
    elif location_id is not None and not any(x['id']==location_id for x in LOCATIONS):
        raise HTTPException(400,'Unknown location_id')
    con=db()
    if location_id is None:
        rows=con.execute("SELECT * FROM notification_recipients ORDER BY location_id,name,id").fetchall()
    else:
        rows=con.execute("SELECT * FROM notification_recipients WHERE location_id=? ORDER BY consent_status,name,id",(location_id,)).fetchall()
    con.close()
    return [_recipient_public(r) for r in rows]


@app.post('/api/field/households')
def field_register_household(body:FieldHouseholdCreate, x_prahari_key:Optional[str]=Header(default=None,alias='X-PRAHARI-Key'), role:str=Depends(resolve_role)):
    officer=_field_actor(role,x_prahari_key)
    if not body.consent_confirmed:
        raise HTTPException(400,'Explicit civilian SMS opt-in/consent must be confirmed before registration')
    try:
        phone=normalize_e164(body.phone_e164)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    if officer:
        location_id=int(officer['location_id'])
        registered_by_role='FIELD_OFFICER'; registered_by_officer=officer.get('name'); registered_by_code=officer.get('officer_code')
        posting_id=location_id; source='FIELD_OFFICER_PORTAL'
    else:
        location_id=body.location_id
        if location_id is None:
            raise HTTPException(400,'Admin registration requires an alert area')
        if not any(x['id']==location_id for x in LOCATIONS):
            raise HTTPException(400,'Unknown location_id')
        registered_by_role=role; registered_by_officer='Administrator'; registered_by_code=None; posting_id=location_id; source='ADMIN_FIELD_REGISTRY'
    now=int(time.time()); con=db(); cur=con.cursor()
    existing=cur.execute("SELECT id,consent_status FROM notification_recipients WHERE phone_e164=? AND location_id=?",(phone,location_id)).fetchone()
    if existing:
        con.close(); raise HTTPException(409,'This phone number is already registered for this alert area')
    rid=insert_row(cur, """INSERT INTO notification_recipients(
        name,phone_e164,location_id,language,sms_enabled,whatsapp_enabled,consent_status,consent_at,created_at,updated_at,
        household_label,village,household_size,registered_by_role,registered_by_officer,registered_by_officer_code,
        registered_by_posting_location_id,registration_source
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name.strip(),phone,location_id,body.language,1,0,'ACTIVE',now,now,now,
         (body.household_label or '').strip() or None,(body.village or '').strip() or None,body.household_size,
         registered_by_role,registered_by_officer,registered_by_code,posting_id,source))

    detail=f'Civilian recipient {rid} registered for location {location_id} by {registered_by_role} {registered_by_officer or ""}'.strip()
    cur.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",('FIELD_CIVILIAN_REGISTERED',detail,now))
    con.commit(); row=cur.execute("SELECT * FROM notification_recipients WHERE id=?",(rid,)).fetchone(); con.close()
    return {'ok':True,'recipient':_recipient_public(row),'posting_enforced':bool(officer)}


@app.patch('/api/field/households/{recipient_id}')
def field_update_household(recipient_id:int, body:FieldHouseholdUpdate, x_prahari_key:Optional[str]=Header(default=None,alias='X-PRAHARI-Key'), role:str=Depends(resolve_role)):
    officer=_field_actor(role,x_prahari_key)
    con=db(); cur=con.cursor(); row=cur.execute("SELECT * FROM notification_recipients WHERE id=?",(recipient_id,)).fetchone()
    if not row:
        con.close(); raise HTTPException(404,'Civilian record not found')
    if officer and int(row['location_id'] or -1)!=int(officer['location_id']):
        con.close(); raise HTTPException(403,'Field officers can only manage civilians in their assigned posting')
    fields=[]; vals=[]
    for key in ('language','consent_status','household_label','village','household_size'):
        value=getattr(body,key)
        if value is not None:
            fields.append(f"{key}=?"); vals.append(value)
    if not fields:
        con.close(); return {'ok':True,'recipient':_recipient_public(row)}
    now=int(time.time()); fields.append('updated_at=?'); vals.extend([now,recipient_id])
    cur.execute(f"UPDATE notification_recipients SET {','.join(fields)} WHERE id=?",vals)
    cur.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",('FIELD_CIVILIAN_UPDATED',f'Civilian recipient {recipient_id} updated by {role}',now))
    con.commit(); out=cur.execute("SELECT * FROM notification_recipients WHERE id=?",(recipient_id,)).fetchone(); con.close()
    return {'ok':True,'recipient':_recipient_public(out)}


@app.get('/api/notification/recipients')
def notification_recipients(role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    con=db(); rows=con.execute("SELECT * FROM notification_recipients ORDER BY consent_status,name,id").fetchall(); con.close()
    return [_recipient_public(r) for r in rows]


@app.post('/api/notification/recipients')
def create_notification_recipient(body:NotificationRecipientCreate, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    if not body.consent_confirmed:
        raise HTTPException(400,'Explicit recipient opt-in/consent must be confirmed before enrollment')
    try: phone=normalize_e164(body.phone_e164)
    except ValueError as exc: raise HTTPException(400,str(exc))
    if body.location_id is not None and not any(x['id']==body.location_id for x in LOCATIONS):
        raise HTTPException(400,'Unknown location_id')
    now=int(time.time()); con=db(); cur=con.cursor()
    existing=cur.execute("SELECT id FROM notification_recipients WHERE phone_e164=? AND COALESCE(location_id,-1)=COALESCE(?,-1)",(phone,body.location_id)).fetchone()
    if existing:
        con.close(); raise HTTPException(409,'This phone number is already enrolled for the selected area')
    rid=insert_row(cur, """INSERT INTO notification_recipients(
        name,phone_e164,location_id,language,sms_enabled,whatsapp_enabled,consent_status,consent_at,created_at,updated_at,
        household_label,village,household_size,registered_by_role,registration_source
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name.strip(),phone,body.location_id,body.language,int(body.sms_enabled),0,'ACTIVE',now,now,now,
         (body.household_label or '').strip() or None,(body.village or '').strip() or None,body.household_size,'ADMIN','ADMIN_PORTAL'))

    cur.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",('NOTIFICATION_RECIPIENT_ADDED',f'Recipient {rid} enrolled with explicit consent',now))
    con.commit(); row=cur.execute("SELECT * FROM notification_recipients WHERE id=?",(rid,)).fetchone(); con.close()
    return {'ok':True,'recipient':_recipient_public(row)}


@app.patch('/api/notification/recipients/{recipient_id}')
def update_notification_recipient(recipient_id:int, body:NotificationRecipientUpdate, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    con=db(); cur=con.cursor(); row=cur.execute("SELECT * FROM notification_recipients WHERE id=?",(recipient_id,)).fetchone()
    if not row:
        con.close(); raise HTTPException(404,'Recipient not found')
    fields=[]; vals=[]
    for key in ('name','location_id','language','sms_enabled','consent_status','household_label','village','household_size'):
        value=getattr(body,key)
        if value is not None:
            if key=='location_id' and value is not None and not any(x['id']==value for x in LOCATIONS):
                con.close(); raise HTTPException(400,'Unknown location_id')
            fields.append(f"{key}=?"); vals.append(int(value) if key == 'sms_enabled' else value)
    if not fields:
        con.close(); return {'ok':True,'recipient':_recipient_public(row)}
    now=int(time.time()); fields.append('updated_at=?'); vals.append(now); vals.append(recipient_id)
    cur.execute(f"UPDATE notification_recipients SET {','.join(fields)} WHERE id=?",vals)
    cur.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",('NOTIFICATION_RECIPIENT_UPDATED',f'Recipient {recipient_id} updated',now))
    con.commit(); out=cur.execute("SELECT * FROM notification_recipients WHERE id=?",(recipient_id,)).fetchone(); con.close()
    return {'ok':True,'recipient':_recipient_public(out)}


@app.get('/api/alerts/{alert_id}/notification-preview')
def notification_preview(alert_id:int, scope:Literal['ALERT_AREA','SPECIFIC_AREA','ALL_MONITORED']='ALERT_AREA', target_location_id:Optional[int]=None, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    con=db(); row=con.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone(); con.close()
    if not row: raise HTTPException(404,'Alert not found')
    alert=dict(row)
    if scope=='SPECIFIC_AREA' and target_location_id is None:
        raise HTTPException(400,'target_location_id is required for SPECIFIC_AREA')
    recipients=_eligible_recipients(alert,scope,target_location_id); cfg=notification_config_status()
    return {
        'alert_id':alert_id,'location':alert.get('location'),'level':alert.get('level'),'lifecycle_status':alert.get('lifecycle_status'),
        'broadcast_scope':scope,'target_location_id':target_location_id,'target_label':_broadcast_target_label(scope,alert,target_location_id),
        'eligible_recipients':len(recipients),'sms_recipients':len(recipients),
        'message':_alert_broadcast_text(alert,'en',sms=True),
        'provider':cfg,'policy':'Only ACTIVE, explicitly opted-in civilians in the selected broadcast scope are eligible. Duplicate phone numbers are de-duplicated.'
    }


@app.get('/api/alerts/{alert_id}/deliveries')
def alert_deliveries(alert_id:int, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    con=db(); exists=con.execute('SELECT id FROM alerts WHERE id=?',(alert_id,)).fetchone()
    if not exists:
        con.close(); raise HTTPException(404,'Alert not found')
    rows=con.execute("""SELECT d.*,r.name recipient_name,r.phone_e164 FROM notification_deliveries d LEFT JOIN notification_recipients r ON r.id=d.recipient_id WHERE d.alert_id=? ORDER BY d.id""",(alert_id,)).fetchall(); con.close()
    return [dict(r) for r in rows]


@app.post('/api/alerts/{alert_id}/issue-and-notify')
def issue_and_notify(alert_id:int, body:AlertBroadcastRequest, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    if BROADCAST_ENABLED:
        raise HTTPException(409,'Use Reports & Alerts → Bulk broadcasts. Synchronous sending is disabled in broadcast mode.')
    con=db(); row=con.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone(); con.close()
    if not row: raise HTTPException(404,'Alert not found')
    alert=dict(row); current=alert.get('lifecycle_status') or 'DRAFT'
    if current=='DRAFT':
        raise HTTPException(409,'Alert must be REVIEWED before an admin can issue and send SMS')
    if current in ('ACKNOWLEDGED','RESOLVED'):
        raise HTTPException(409,f'Cannot broadcast an alert in {current} state')
    if body.scope=='SPECIFIC_AREA' and body.target_location_id is None:
        raise HTTPException(400,'target_location_id is required for SPECIFIC_AREA')
    recipients=_eligible_recipients(alert,body.scope,body.target_location_id)
    if len(recipients)>100:
        raise HTTPException(409,'Use Bulk broadcasts for audiences larger than 100 recipients.')
    if not recipients:
        raise HTTPException(409,'No ACTIVE opted-in SMS recipients are enrolled for the selected area')
    cfg=notification_config_status()
    if not cfg.get('sms',{}).get('ready'):
        issues=cfg.get('sms',{}).get('issues',[])
        raise HTTPException(503,' '.join(issues) or 'SMS provider is not ready. Configure Twilio credentials and SMS sender first.')
    if current=='REVIEWED':
        alert=_transition_alert(alert_id,'ISSUED',role,body.note)
        con=db(); row=con.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone(); con.close(); alert=dict(row)

    results=[]
    for recipient in recipients:
        con=db(); existing=con.execute("SELECT * FROM notification_deliveries WHERE alert_id=? AND recipient_id=? AND channel='sms'",(alert_id,recipient['id'])).fetchone(); con.close()
        if existing and not (body.retry_failed and str(existing['status']).upper() in FAILED_DELIVERY_STATUSES):
            results.append({'recipient_id':recipient['id'],'channel':'sms','status':'SKIPPED_DUPLICATE','provider_message_sid':existing['provider_message_sid']})
            continue
        message=_alert_broadcast_text(alert,recipient.get('language') or 'en',sms=True)
        try:
            _upsert_delivery(alert_id,recipient['id'],'sms',status='ATTEMPTING')
            sent=send_notification('sms',recipient['phone_e164'],message)
            status=str(sent.get('status') or 'QUEUED').upper()
            error_code=str(sent.get('error_code') or '') or None
            error_message=sent.get('error_message')
            _upsert_delivery(alert_id,recipient['id'],'sms',status=status,sid=sent.get('sid'),error_code=error_code,error_message=error_message)
            results.append({'recipient_id':recipient['id'],'channel':'sms','status':status,'provider_message_sid':sent.get('sid'),
                            'error_code':error_code,'error':error_message})
        except Exception as exc:
            error_code=str(getattr(exc,'code',None) or '') or None
            error_message=getattr(exc,'msg',None) or str(exc)
            _upsert_delivery(alert_id,recipient['id'],'sms',status='FAILED',error_code=error_code,error_message=error_message)
            results.append({'recipient_id':recipient['id'],'channel':'sms','status':'FAILED','error_code':error_code,'error':error_message})
    now=int(time.time()); con=db(); con.execute("INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)",('ALERT_EXTERNAL_BROADCAST',f'Alert {alert_id} SMS broadcast initiated by {role}; scope={body.scope}; target={_broadcast_target_label(body.scope,alert,body.target_location_id)}',now)); con.commit(); con.close()
    accepted=sum(1 for r in results if r['status'] not in FAILED_DELIVERY_STATUSES and r['status']!='SKIPPED_DUPLICATE')
    failed=sum(1 for r in results if r['status'] in FAILED_DELIVERY_STATUSES)
    skipped=sum(1 for r in results if r['status']=='SKIPPED_DUPLICATE')
    return {'ok':True,'alert':localized_alert(row if current=='ISSUED' else dict(row),'en'),'broadcast_scope':body.scope,
            'target_label':_broadcast_target_label(body.scope,alert,body.target_location_id),
            'eligible_recipients':len(recipients),'accepted_or_queued':accepted,'failed':failed,'skipped_duplicates':skipped,'results':results,
            'delivery_note':'queued/sent is not delivery confirmation; delivered status is tracked separately.'}


@app.post('/api/alerts/{alert_id}/deliveries/refresh')
def refresh_alert_deliveries(alert_id:int, role:str=Depends(resolve_role)):
    require_role(role,'ADMIN')
    con=db(); rows=con.execute("SELECT * FROM notification_deliveries WHERE alert_id=? AND provider_message_sid IS NOT NULL",(alert_id,)).fetchall(); con.close()
    refreshed=[]
    for r in rows:
        try:
            st=fetch_notification_status(r['provider_message_sid'])
            out=_record_provider_status(r['provider_message_sid'],st.get('status'),str(st.get('error_code') or '') or None,st.get('error_message'))
            refreshed.append(out)
        except Exception as exc:
            refreshed.append({'id':r['id'],'provider_message_sid':r['provider_message_sid'],'refresh_error':str(exc)})
    return {'ok':True,'deliveries':refreshed}


@app.post('/api/notification/twilio/status')
async def twilio_status_callback(request:Request):
    form=await request.form(); data={k:str(v) for k,v in form.items()}
    signature=request.headers.get('X-Twilio-Signature')
    validation_url=notification_callback_url() or str(request.url)
    try:
        valid=validate_twilio_signature(validation_url,data,signature)
    except Exception:
        valid=False
    if not valid:
        raise HTTPException(403,'Invalid Twilio webhook signature')
    sid=data.get('MessageSid') or data.get('SmsSid'); status=data.get('MessageStatus') or data.get('SmsStatus') or 'UNKNOWN'
    if sid:
        from broadcasts import record_status
        record_status(db,sid,status,data.get('ErrorCode'))
        _record_provider_status(sid,status,data.get('ErrorCode'),data.get('ChannelStatusMessage'))
    return Response(status_code=204)


@app.post('/api/notification/msg91/status')
async def msg91_status_callback(request:Request):
    from msg91_provider import verify_webhook, parse_webhook
    from broadcasts import record_msg91_status
    if not verify_webhook(request.headers.get('X-PRAHARI-Webhook-Token')):
        raise HTTPException(403, 'Invalid MSG91 webhook credentials')
    body=await request.body()
    if len(body)>16384:
        raise HTTPException(413, 'Webhook payload too large')
    try:
        receipt=parse_webhook(json.loads(body))
    except (ValueError, UnicodeDecodeError):
        receipt=None
    if receipt:
        record_msg91_status(db,receipt)
    return Response(status_code=204)


@app.get("/api/notification/channels")
def notification_channels():
    cfg=notification_config_status(); con=db()
    total=con.execute("SELECT COUNT(*) c FROM notification_recipients WHERE consent_status='ACTIVE'").fetchone()['c']
    sms_count=con.execute("SELECT COUNT(*) c FROM notification_recipients WHERE consent_status='ACTIVE' AND sms_enabled=1").fetchone()['c']
    con.close()
    sms_status={'status':'READY' if cfg['sms']['ready'] else ('ENABLED_NOT_READY' if EXTERNAL_SMS_ENABLED else 'DISABLED'),
                'provider':cfg['provider'],'delivery':'Twilio delivery receipts/status are tracked',
                'opted_in_recipients':sms_count,'issues':cfg['sms'].get('issues',[])}
    if BROADCAST_ENABLED and BROADCAST_PROVIDER == 'msg91':
        from msg91_provider import status as msg91_status
        from broadcasts import overview
        readiness=msg91_status()
        online=overview(db)['worker_online']
        sms_status={'status':'READY' if readiness['ready'] and online else 'ENABLED_NOT_READY',
                    'provider':'msg91','delivery':'MSG91 delivery webhook',
                    'opted_in_recipients':sms_count,
                    'issues':readiness['issues']+([] if online else ['Broadcast worker is offline.'])}
    return {
        'command_center':{'status':'ACTIVE','delivery':'local database record'},
        'browser':{'status':'LOCAL_UI_ONLY','delivery':'requires user browser permission; not an external public warning'},
        'sms':sms_status,
        'active_recipients':total,'status_callback':cfg.get('status_callback'),
        'policy':'SMS messages are sent only after explicit ADMIN issue-and-notify action, only to ACTIVE opted-in recipients. A click is not treated as delivery confirmation.'
    }

@app.get('/api/auth/config-status')
def auth_config_status():
    """Safe authentication diagnostics. Never returns access keys/secrets."""
    return {
        'auth_required': AUTH_REQUIRED,
        'admin_configured': bool(ADMIN_KEY),
        'field_officer_count': len(FIELD_OFFICERS),
        'field_officer_codes': [str(x.get('officer_code') or '') for x in FIELD_OFFICERS],
        'field_officer_location_ids': [x.get('location_id') for x in FIELD_OFFICERS],
        'field_officer_config_error': FIELD_OFFICERS_CONFIG_ERROR,
        'environment_source': ENV_SOURCE,
        'note': 'Diagnostic metadata only; PRAHARI never returns configured access keys.'
    }

@app.post('/api/auth/login')
def portal_login(body:PortalLoginRequest):
    """Validate a portal-specific access key without exposing configured secrets.

    This keeps the existing lightweight API-key architecture while giving the UI a
    clean separation between the command/admin portal and posting-restricted field
    portal. Production deployments should replace shared keys with organizational
    identity/OIDC.
    """
    key=(body.access_key or '').strip()
    if body.portal=='FIELD_OFFICER':
        officer=field_officer_for_key(key)
        if not officer:
            raise HTTPException(401,'Field officer access key is not recognized')
        if body.officer_code and str(body.officer_code).strip().upper() != str(officer.get('officer_code') or '').strip().upper():
            raise HTTPException(401,'Officer code and access key do not match')
        loc=next((x for x in LOCATIONS if x['id']==officer.get('location_id')),None)
        if not loc:
            raise HTTPException(403,'Field officer posting is not mapped to a monitored PRAHARI area')
        actor={
            'name':officer.get('name'),'officer_code':officer.get('officer_code'),
            'posting_location_id':officer.get('location_id'),
            'posting':f"{loc['name']}, {loc['state']}"
        }
        return {'ok':True,'portal':'FIELD_OFFICER','current_role':'FIELD_OFFICER','actor':actor,'auth_required':AUTH_REQUIRED}

    # Admin portal. In protected/shared deployments the configured admin key is mandatory.
    # In local development, if no admin key is configured, a blank key may open the
    # development command portal; this is explicitly reported as DEV_OPERATOR.
    if ADMIN_KEY:
        if key != ADMIN_KEY:
            raise HTTPException(401,'Admin access key is not recognized')
        return {'ok':True,'portal':'ADMIN','current_role':'ADMIN' if AUTH_REQUIRED else 'DEV_OPERATOR',
                'actor':{'name':'PRAHARI Administrator','posting':'All monitored areas'},'auth_required':AUTH_REQUIRED}
    if AUTH_REQUIRED or APP_ENV != 'development':
        raise HTTPException(503,'Admin portal is not configured. Set PRAHARI_ADMIN_KEY on the server.')
    return {'ok':True,'portal':'ADMIN','current_role':'DEV_OPERATOR',
            'actor':{'name':'Development Administrator','posting':'All monitored areas'},'auth_required':False,
            'development_warning':'Authentication is open because PRAHARI_AUTH_REQUIRED=false and no admin key is configured.'}


@app.get('/api/auth/status')
def auth_status(x_prahari_key:Optional[str]=Header(default=None,alias='X-PRAHARI-Key'), role:str=Depends(resolve_role)):
    officer=field_officer_for_key(x_prahari_key) if role=='FIELD_OFFICER' else None
    actor=None
    if officer:
        loc=next((x for x in LOCATIONS if x['id']==officer.get('location_id')),None)
        actor={'name':officer.get('name'),'officer_code':officer.get('officer_code'),'posting_location_id':officer.get('location_id'),
               'posting':f"{loc['name']}, {loc['state']}" if loc else 'Unknown posting'}
    return {'auth_required':AUTH_REQUIRED,'mode':'operator-key' if AUTH_REQUIRED else 'development-open','current_role':role,'actor':actor,
            'mutation_roles':['FIELD_OFFICER','OPERATOR','REVIEWER','ADMIN'],
            'note':'Field-officer keys are posting-restricted for civilian enrollment. Admin/reviewer/operator keys remain separate. Keys are never returned by the API.'}

@app.get('/api/data/sources')
def data_sources():
    return {'sources':DATA_CATALOG,'policy':'CURRENT, STALE and MISSING source states are explicit. Missing data never silently becomes low risk.'}

@app.get("/api/weather/{location_id}")
def weather(location_id:int, force:bool=False):
    x = next((z for z in LOCATIONS if z['id']==location_id), None)
    if not x:
        raise HTTPException(404,"Location not found")
    return fetch_live_weather(x, force=force)


@app.get("/api/sensors/{location_id}")
def sensors(location_id:int):
    base = next((z for z in LOCATIONS if z['id']==location_id), None)
    if not base:
        raise HTTPException(404,"Location not found")
    w = fetch_live_weather(base)
    x = enrich_with_live(base,w)
    tele = latest_telemetry(location_id) if 'latest_telemetry' in globals() else None
    weather_state=w.get('availability','MISSING')
    nodes=[
        {"name":"Soil wetness proxy","value":x.get('soil_moisture'),"unit":"%","status":weather_state,"source":"Open-Meteo model field"},
        {"name":"Precipitation (past 24h)","value":x.get('rainfall'),"unit":"mm","status":weather_state,"source":"Open-Meteo model field"},
        {"name":"Rain forecast (next 24h)","value":w.get('rain_forecast_24h_mm'),"unit":"mm","status":weather_state,"source":"Open-Meteo forecast"},
    ]
    if tele:
        for name,key,unit in [("Edge rainfall intensity","rainfall_intensity","mm/h"),("Edge soil moisture","soil_moisture","%"),("Slope tilt change","tilt_deg","°"),("Ground vibration","vibration_g","g"),("Pore pressure","pore_pressure_kpa","kPa"),("Slope displacement","displacement_mm","mm")]:
            if tele.get(key) is not None: nodes.append({"name":name,"value":tele[key],"unit":unit,"status":tele.get('source','TELEMETRY')})
    else:
        nodes.append({"name":"Field deformation telemetry","value":None,"unit":None,"status":"MISSING","source":"No sensor connected"})
    return {"location_id":location_id,"updated_at":int(time.time()),"weather_state":weather_state,"edge_telemetry_available":bool(tele),"telemetry":tele,"nodes":nodes}


@app.get("/api/satellite/{location_id}")
def satellite(location_id:int):
    base=next((z for z in LOCATIONS if z['id']==location_id),None)
    if not base: raise HTTPException(404,'Location not found')
    w=fetch_live_weather(base); x=enrich_with_live(base,w); packet=satellite_packet(x)
    today=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
    packet['weather_context']={
        'state':w.get('availability','MISSING'),'valid_time':w.get('valid_time'),'rainfall_24h_mm':w.get('rainfall_24h_mm'),
        'cloud_cover_pct':w.get('cloud_cover_pct'),'source':w.get('source')
    }
    packet['nasa_gibs']={
        'provider':'NASA EOSDIS GIBS / VIIRS NOAA-20 Corrected Reflectance True Color','purpose':'VISUAL_BASEMAP_ONLY',
        'date':today,'tile_template':f'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/{today}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg',
        'cached_proxy_template':'http://127.0.0.1:8000/api/satellite/tile/{z}/{y}/{x}.jpg',
        'note':'Presence of satellite imagery does not mean PRAHARI has processed it for landslide detection.'
    }
    return packet

@app.get("/api/forecast-risk/{location_id}")
def forecast_risk(location_id:int):
    _loc(location_id)
    raise HTTPException(410,'Synthetic risk trajectories are disabled; use the live flash-flood screen with configured catchment thresholds')

@app.get("/api/research/model-card")
def research_model_card():
    return {
        "project":"PRAHARI",
        "status":"NOT_OPERATIONAL",
        "model_type":None,
        "validation":None,
        "warning":"A flood-susceptibility model will only be exposed after real inventory training, spatial/temporal holdout validation and calibration."
    }


@app.get("/api/satellite/scenes")
def satellite_scenes():
    return [satellite_packet(x) for x in (LIVE_REGIONAL_CACHE['data'] or locs())]


@app.get("/api/routes")
def routes():
    return []

@app.get("/api/infrastructure")
def infrastructure():
    return []


@app.get("/api/scenarios")
def scenarios():
    if not _test_fixtures_enabled():
        raise HTTPException(404,'Test fixtures are disabled')
    return [
        {"name":"Cloudburst / saturated slope","values":{"rainfall":225,"antecedent_rainfall_72h":480,"cumulative_rainfall_7d":910,"effective_rainfall_11d":760,"rain_forecast_24h":95,"max_hourly_rain_24h":34,"soil_moisture":93,"slope":52,"elevation":1650,"historical_risk":0.86,"ndvi":0.55,"month":7}},
        {"name":"Severe monsoon watch","values":{"rainfall":165,"antecedent_rainfall_72h":390,"cumulative_rainfall_7d":720,"effective_rainfall_11d":640,"rain_forecast_24h":82,"max_hourly_rain_24h":27,"soil_moisture":84,"slope":43,"elevation":1350,"historical_risk":0.72,"ndvi":0.63,"month":8}},
        {"name":"Stable conditions","values":{"rainfall":34,"antecedent_rainfall_72h":70,"cumulative_rainfall_7d":145,"effective_rainfall_11d":135,"rain_forecast_24h":18,"max_hourly_rain_24h":5,"soil_moisture":42,"slope":19,"elevation":850,"historical_risk":0.22,"ndvi":0.76,"month":2}},
    ]


def _valid_image_signature(content:bytes, content_type:str) -> bool:
    if content_type=='image/jpeg': return content.startswith(b'\xff\xd8\xff')
    if content_type=='image/png': return content.startswith(b'\x89PNG\r\n\x1a\n')
    if content_type=='image/webp': return len(content)>=12 and content[:4]==b'RIFF' and content[8:12]==b'WEBP'
    return False

@app.post("/api/reports")
async def create_report(
    reporter:str=Form(...), phone:str=Form(""), location:str=Form(...),
    lat:float=Form(...), lon:float=Form(...), hazard_type:str=Form("Other"),
    location_method:str=Form("manual"), severity:str=Form("MODERATE"),
    description:str=Form(...), image:Optional[UploadFile]=File(None)
):
    severity = severity.upper().strip()
    if severity not in ("LOW", "MODERATE", "HIGH", "CRITICAL"):
        raise HTTPException(400, "Invalid severity")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, "Coordinates are out of range")
    if len(reporter.strip()) > 120 or len(location.strip()) > 180 or len(phone.strip()) > 40:
        raise HTTPException(400, "Report field length exceeds limit")
    allowed_hazards = {"Road crack","Debris / rockfall","Slope movement","Surface crack","Water seepage","Unusual ground sound","Leaning tree / pole","Flooding","Structural damage","Blocked drainage","Road blockage","Other"}
    if hazard_type not in allowed_hazards:
        hazard_type = "Other"
    location_method = location_method if location_method in ("gps","manual") else "manual"
    if len(description.strip()) < 10:
        raise HTTPException(400, "Description must contain at least 10 characters")

    image_name = None
    if image and image.filename:
        if image.content_type not in ("image/jpeg","image/png","image/webp"):
            raise HTTPException(400, "Evidence image must be JPEG, PNG or WEBP")
        content = await image.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"Evidence image must be {MAX_UPLOAD_BYTES//(1024*1024)} MB or smaller")
        if not _valid_image_signature(content,image.content_type):
            raise HTTPException(400, 'Evidence image content does not match its declared image type')
        ext={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}[image.content_type]
        safe = f"{uuid.uuid4().hex}{ext}"
        with (UPLOADS/safe).open('wb') as f:
            f.write(content)
        image_name = safe

    con = db()
    cur = con.cursor()
    now = int(time.time())
    rid=insert_row(cur,
        """INSERT INTO reports(
            reporter,phone,location,lat,lon,hazard_type,location_method,severity,
            description,image_name,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (reporter.strip(),phone.strip(),location.strip(),lat,lon,hazard_type,location_method,
         severity,description.strip(),image_name,"NEW",now)
    )

    con.commit()
    con.close()
    if severity in ("HIGH","CRITICAL"):
        create_alert(None, location, severity, None, f"citizen-report-{hazard_type.lower().replace(' ','-')}", dedupe_seconds=30)
    return {
        "ok":True,
        "report":{
            "id":rid,"reporter":reporter.strip(),"phone":phone.strip(),"location":location.strip(),
            "lat":lat,"lon":lon,"hazard_type":hazard_type,"location_method":location_method,
            "severity":severity,"description":description.strip(),"image_name":image_name,
            "status":"NEW","created_at":now
        }
    }


@app.get("/api/reports")
def reports():
    con = db()
    rows = con.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 50").fetchall()
    con.close()
    return [dict(r) for r in rows]


@app.patch("/api/reports/{report_id}/status")
def report_status(report_id:int, status:str, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    if status not in ('NEW','VERIFIED','DISPATCHED','RESOLVED'):
        raise HTTPException(400,"Invalid status")
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE reports SET status=? WHERE id=?", (status,report_id))
    con.commit()
    changed = cur.rowcount
    con.close()
    if not changed:
        raise HTTPException(404,"Report not found")
    return {"ok":True,"id":report_id,"status":status}


@app.get("/api/system/events")
def system_events():
    con = db()
    rows = con.execute("SELECT * FROM system_events ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    return [dict(r) for r in rows]


# =============================================================================
# PRAHARI v8 — RESEARCH SYNTHESIS / UNCERTAINTY / EDGE / LOW-BANDWIDTH UPGRADE
# =============================================================================
# Design basis: EW4All four-pillar EWS, impact-based warning, community evidence,
# edge/IoT monitoring, geotechnical screening, geo-fenced response and cached EO.

class TelemetryInput(BaseModel):
    location_id: int
    station_id: str = "EDGE-01"
    rainfall_intensity: Optional[float] = Field(default=None, ge=0, le=500)
    soil_moisture: Optional[float] = Field(default=None, ge=0, le=100)
    tilt_deg: Optional[float] = Field(default=None, ge=-90, le=90)
    vibration_g: Optional[float] = Field(default=None, ge=0, le=20)
    pore_pressure_kpa: Optional[float] = Field(default=None, ge=0, le=1000)
    displacement_mm: Optional[float] = Field(default=None, ge=0, le=10000)
    battery_pct: Optional[float] = Field(default=100, ge=0, le=100)
    quality: Optional[float] = Field(default=1.0, ge=0, le=1)
    source: Literal['REAL_SENSOR','SIMULATED_HACKATHON','MANUAL_TEST'] = 'REAL_SENSOR'

class GeoTechInput(BaseModel):
    cohesion_kpa: float = Field(ge=0, le=500)
    friction_angle_deg: float = Field(ge=0, le=60)
    slope_deg: float = Field(gt=0, lt=89)
    soil_depth_m: float = Field(gt=0.05, le=100)
    unit_weight_kn_m3: float = Field(default=18.0, ge=5, le=35)
    pore_pressure_ratio: float = Field(default=0.35, ge=0, le=1)

PRECURSOR_WEIGHTS = {
    'Slope movement':1.00, 'Surface crack':0.95, 'Water seepage':0.80,
    'Unusual ground sound':0.85, 'Leaning tree / pole':0.72,
    'Debris / rockfall':0.82, 'Blocked drainage':0.62, 'Road crack':0.72,
    'Road blockage':0.70, 'Structural damage':0.60, 'Flooding':0.45, 'Other':0.35
}
SEVERITY_W = {'LOW':.2,'MODERATE':.45,'HIGH':.75,'CRITICAL':1.0}

# Prototype assembly points and a tiny offline routing graph. These are not
# official shelters; they demonstrate how verified emergency GIS would plug in.
SHELTERS = {}

def _haversine(lat1,lon1,lat2,lon2):
    r=6371.0
    a1,a2=math.radians(lat1),math.radians(lat2)
    dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2+math.cos(a1)*math.cos(a2)*math.sin(dlon/2)**2
    return 2*r*math.asin(math.sqrt(a))

def _loc(location_id):
    x=next((z for z in LOCATIONS if z['id']==location_id),None)
    if not x: raise HTTPException(404,'Location not found')
    return x

def latest_telemetry(location_id):
    con=db(); row=con.execute('SELECT * FROM telemetry WHERE location_id=? ORDER BY id DESC LIMIT 1',(location_id,)).fetchone(); con.close()
    return dict(row) if row else None

def community_signal_value(location_id, hours=48):
    x=_loc(location_id); cutoff=int(time.time())-hours*3600
    con=db(); rows=con.execute('SELECT * FROM reports WHERE created_at>=? ORDER BY id DESC',(cutoff,)).fetchall(); con.close()
    score=0.0; evidence=[]
    for rr in rows:
        r=dict(rr)
        try: dist=_haversine(x['lat'],x['lon'],float(r['lat']),float(r['lon']))
        except Exception: continue
        if dist>18: continue
        age_h=max(0,(int(time.time())-int(r['created_at']))/3600)
        time_decay=math.exp(-age_h/18.0)
        verify=1.2 if r.get('status')=='VERIFIED' else (1.05 if r.get('status')=='DISPATCHED' else .8)
        raw=PRECURSOR_WEIGHTS.get(r.get('hazard_type'),.35)*SEVERITY_W.get(r.get('severity'),.45)*time_decay*verify*max(.25,1-dist/22)
        score+=raw
        evidence.append({'id':r['id'],'hazard_type':r.get('hazard_type'),'severity':r.get('severity'),'status':r.get('status'),'distance_km':round(dist,1),'age_hours':round(age_h,1),'contribution':round(raw,3)})
    evidence.sort(key=lambda e:e['contribution'],reverse=True)
    pct=round(min(100, (1-math.exp(-score))*100),1)
    level='STRONG' if pct>=65 else ('CORROBORATING' if pct>=35 else ('WEAK' if pct>0 else 'NONE'))
    return {'location_id':location_id,'location':f"{x['name']}, {x['state']}",'score':pct,'level':level,'reports_considered':len(evidence),'evidence':evidence[:8],
            'note':'Community observations are corroborating evidence with time/distance/verification weighting; they do not replace the physical hazard model.'}

def impact_assessment_value(location_id, hazard_percent=None):
    x=_loc(location_id)
    current=next((z for z in (LIVE_REGIONAL_CACHE.get('data') or []) if z.get('id')==location_id),None)
    if hazard_percent is None and current:
        hazard_percent=current.get('risk_percent')
    comm=community_signal_value(location_id)
    # No population, road or asset score is fabricated. Exposure becomes
    # available only when an authoritative inventory is connected.
    return {
        'location_id':location_id,'available':False,'hazard_index':round(float(hazard_percent),1) if hazard_percent is not None else None,
        'impact_score':None,'priority':'UNKNOWN','community_signal':comm['score'],
        'assets_at_risk':None,'population_exposed':None,'data_status':'NO_VERIFIED_EXPOSURE_DATA',
        'asset_source':None,'interpretation':'Verified exposure GIS is not connected for this monitoring point.'
    }

def _route_plan(location_id, hazard_percent):
    x=_loc(location_id); shelters=SHELTERS.get(location_id,[])
    if not shelters: return None
    # Two conceptual corridors per shelter: direct/shorter vs bypass/safer. We use
    # Dijkstra on this offline graph so the route can remain available without internet.
    nodes={'ZONE':(x['lat'],x['lon'])}
    edges={}
    def add(a,b,km,exposure):
        w=km*(1+3.2*exposure*(hazard_percent/100))
        edges.setdefault(a,[]).append((b,w,km,exposure)); edges.setdefault(b,[]).append((a,w,km,exposure))
    for idx,sh in enumerate(shelters):
        sid=sh['id']; nodes[sid]=(sh['lat'],sh['lon'])
        j=f'J{idx+1}'; nodes[j]=((x['lat']+sh['lat'])/2+.006,(x['lon']+sh['lon'])/2-.006)
        direct=max(.4,_haversine(x['lat'],x['lon'],sh['lat'],sh['lon']))
        add('ZONE',sid,direct,.78)           # shortest but exposed
        add('ZONE',j,direct*.62,.18)        # safer bypass
        add(j,sid,direct*.62,.12)
    import heapq
    dist={'ZONE':0.0}; prev={}; pq=[(0.0,'ZONE')]
    while pq:
        d,u=heapq.heappop(pq)
        if d!=dist.get(u): continue
        for v,w,km,ex in edges.get(u,[]):
            nd=d+w
            if nd<dist.get(v,1e99): dist[v]=nd;prev[v]=(u,km,ex);heapq.heappush(pq,(nd,v))
    best=min(shelters,key=lambda sh:dist.get(sh['id'],1e99)); cur=best['id']; path=[cur]; raw=0; exposure=[]
    while cur!='ZONE':
        u,km,ex=prev[cur]; raw+=km; exposure.append(ex); cur=u; path.append(cur)
    path=list(reversed(path))
    coords=[{'node':p,'lat':round(nodes[p][0],6),'lon':round(nodes[p][1],6)} for p in path]
    return {'safe_point':best,'path':path,'coordinates':coords,'distance_km':round(raw,2),'route_risk_index':round(sum(exposure)/max(1,len(exposure))*100,1),'algorithm':'Dijkstra on offline prototype evacuation graph','offline_ready':True,
            'warning':'Assembly points and graph are prototype demo data, not official evacuation routes.'}

@app.get('/api/community/signal/{location_id}', tags=['People-centred EWS'])
def community_signal(location_id:int): return community_signal_value(location_id)

@app.get('/api/impact/{location_id}', tags=['Impact-based warning'])
def impact(location_id:int): return impact_assessment_value(location_id)

@app.get('/api/response/plan/{location_id}', tags=['Preparedness & response'])
def response_plan(location_id:int):
    x=_loc(location_id)
    current=next((z for z in (LIVE_REGIONAL_CACHE.get('data') or []) if z.get('id')==location_id),None)
    if not current:
        packet=fetch_live_weather(x)
        current=enrich_with_live(x,packet)
    hazard=current.get('risk_percent')
    imp=impact_assessment_value(location_id,hazard)
    route=_route_plan(location_id,hazard) if hazard is not None else None
    level=current.get('risk_level','UNKNOWN')
    action=action_for(level) if level in ('LOW','MODERATE','HIGH','CRITICAL') else 'Acquire missing observations before recommending action.'
    return {
        'location_id':location_id,'location':f"{x['name']}, {x['state']}",'assessment_state':current.get('assessment_status'),
        'impact':imp,'routing_suggestion':route,'recommended_action':action,
        'route_policy':'No route is generated until verified road-closure and shelter GIS are connected.',
        'checklist':[],
        'ew4all_pillars':{'risk_knowledge':'GIS + traceable assessment','monitoring_forecasting':'weather + optional real telemetry','warning_communication':'reviewed advisory lifecycle','preparedness_response':'operator checklist + audit history'},
        'human_decision_gate':{'required':True,'policy':'PRAHARI provides decision support; competent geological/emergency authorities authorize public warnings, evacuation and road closure.'}
    }

@app.post('/api/iot/telemetry', tags=['Edge & IoT'])
def ingest_telemetry(t:TelemetryInput, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    if t.source!='REAL_SENSOR' and not _test_fixtures_enabled():
        raise HTTPException(422,'Only REAL_SENSOR telemetry is accepted outside automated tests')
    x=_loc(t.location_id); now=int(time.time()); con=db(); cur=con.cursor()
    tid=insert_row(cur, 'INSERT INTO telemetry(location_id,station_id,rainfall_intensity,soil_moisture,tilt_deg,vibration_g,pore_pressure_kpa,displacement_mm,battery_pct,quality,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (t.location_id,t.station_id,t.rainfall_intensity,t.soil_moisture,t.tilt_deg,t.vibration_g,t.pore_pressure_kpa,t.displacement_mm,t.battery_pct,t.quality,t.source,now))
    con.commit(); con.close()

    # Transparent edge precursor screen. Only REAL_SENSOR may create an operational draft advisory.
    danger=0; reasons=[]
    if t.soil_moisture is not None and t.soil_moisture>=85: danger+=2; reasons.append('high field soil moisture')
    if t.rainfall_intensity is not None and t.rainfall_intensity>=30: danger+=2; reasons.append('intense local rainfall')
    if t.displacement_mm is not None and t.displacement_mm>=8: danger+=3; reasons.append('rapid displacement')
    if t.tilt_deg is not None and abs(t.tilt_deg)>=2.5: danger+=2; reasons.append('tilt change')
    if t.vibration_g is not None and t.vibration_g>=.35: danger+=1; reasons.append('abnormal vibration')
    edge_state='CRITICAL' if danger>=6 else ('WARNING' if danger>=4 else ('WATCH' if danger>=2 else 'NORMAL'))
    draft=None
    if t.source=='REAL_SENSOR' and edge_state=='CRITICAL' and (t.quality or 0)>=.6:
        draft=create_alert(x['id'],f"{x['name']}, {x['state']}",'CRITICAL',None,'edge-real-sensor-screen',dedupe_seconds=300)

    weather=fetch_live_weather(x)
    terrain=fetch_terrain_profile(x)
    baseline=baseline_assess({
        'rainfall_24h':weather.get('rainfall_24h_mm'),
        'antecedent_rainfall_72h':weather.get('antecedent_rainfall_72h_mm'),
        'cumulative_rainfall_7d':weather.get('cumulative_rainfall_7d_mm'),
        'soil_moisture':t.soil_moisture if t.soil_moisture is not None else weather.get('soil_moisture_proxy_pct'),
        'slope':terrain.get('local_slope_proxy_deg'),'max_hourly_rain_24h':weather.get('max_hourly_rain_24h_mm'),
        'rainfall_intensity':t.rainfall_intensity,'tilt_deg':t.tilt_deg,'vibration_g':t.vibration_g,
        'pore_pressure_kpa':t.pore_pressure_kpa,'displacement_mm':t.displacement_mm,'telemetry_quality':t.quality,
    }, t.source)
    fused_draft=None
    if t.source=='REAL_SENSOR' and baseline.status=='ASSESSED' and baseline.level in ('HIGH','CRITICAL'):
        fused_draft=create_alert(x['id'],f"{x['name']}, {x['state']}",baseline.level,baseline.index,'weather-real-sensor-baseline',dedupe_seconds=300)
    return {
        'ok':True,'telemetry_id':tid,'source':t.source,'created_at':now,'quality':t.quality,
        'edge_screen':{'state':edge_state,'score':danger,'reasons':reasons,'rule_version':'edge-screen-v1','operational_effect':t.source=='REAL_SENSOR'},
        'assessment':{'status':baseline.status,'risk_index':baseline.index,'risk_level':baseline.level,'calibrated_probability':False,
                      'model_version':BASELINE_VERSION,'missing_inputs':baseline.missing,'factors':baseline.reasons,'limitations':baseline.limitations},
        'draft_advisory_created':bool(draft or fused_draft),
        'alert':localized_alert(fused_draft or draft,'en') if (fused_draft or draft) else None,
        'note':'SIMULATED_HACKATHON and MANUAL_TEST telemetry are stored for demo/testing but cannot escalate live advisories.'
    }

@app.get('/api/iot/telemetry/latest', tags=['Edge & IoT'])
def latest_iot(location_id:int=Query(...)):
    _loc(location_id); row=latest_telemetry(location_id)
    return {'location_id':location_id,'available':bool(row),'telemetry':row,'note':'Only authenticated REAL_SENSOR telemetry is accepted for operational monitoring.'}

@app.post('/api/iot/demo/{location_id}', tags=['Edge & IoT'])
def demo_iot(location_id:int, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    if not _test_fixtures_enabled():
        raise HTTPException(404,'Test fixtures are disabled')
    x=_loc(location_id)
    # Explicit synthetic demonstration packet. It is stored as SIMULATED_HACKATHON and is excluded from live escalation.
    replay=build_replay_packet(x)
    rain=float(replay.get('rainfall_24h_mm') or 0)
    wet=float(replay.get('soil_moisture_proxy_pct') or 0)
    severity=max(0.0,min(1.0,(rain/200.0 + wet/100.0 + float(replay.get('terrain_slope_deg') or 0)/60.0)/3.0))
    t=TelemetryInput(location_id=location_id,station_id=f"DEMO-{location_id:02d}",rainfall_intensity=round(max(2,rain/8),1),soil_moisture=wet,
        tilt_deg=round(.4+severity*2.7,2),vibration_g=round(.05+severity*.38,3),pore_pressure_kpa=round(18+severity*68,1),
        displacement_mm=round(.7+severity*10.5,2),battery_pct=94,quality=.96,source='SIMULATED_HACKATHON')
    result=ingest_telemetry(t, role)
    result['demo_mode']='SYNTHETIC_DEMONSTRATION'
    return result

@app.post('/api/geotech/factor-of-safety', tags=['Physics guardrail'])
def factor_of_safety(g:GeoTechInput):
    # Simplified infinite-slope screening. This is intentionally a transparent
    # engineering indicator, NOT a substitute for a site-specific geotechnical model.
    beta=math.radians(g.slope_deg); phi=math.radians(g.friction_angle_deg)
    normal=max(1e-6,g.unit_weight_kn_m3*g.soil_depth_m*math.cos(beta)**2)
    shear=max(1e-6,g.unit_weight_kn_m3*g.soil_depth_m*math.sin(beta)*math.cos(beta))
    effective_normal=normal*(1-g.pore_pressure_ratio)
    fs=(g.cohesion_kpa+effective_normal*math.tan(phi))/shear
    fs=round(fs,3)
    state='UNSTABLE' if fs<1 else ('MARGINAL' if fs<1.3 else ('WATCH' if fs<1.5 else 'STABLE'))
    return {'factor_of_safety':fs,'state':state,'physics_screen':'simplified infinite-slope model','inputs':g.model_dump(),
            'warning':'Research/education screening only. Real warnings require field-calibrated stratigraphy, groundwater and geotechnical parameters.'}

@app.post('/api/alerts/{alert_id}/feedback', tags=['Learning loop'])
def alert_feedback(alert_id:int, body:AlertFeedback, role:str=Depends(resolve_role)):
    require_role(role,'OPERATOR')
    con=db(); exists=con.execute('SELECT id FROM alerts WHERE id=?',(alert_id,)).fetchone()
    if not exists: con.close(); raise HTTPException(404,'Alert not found')
    now=int(time.time()); con.execute('INSERT INTO alert_feedback(alert_id,outcome,note,created_at) VALUES(?,?,?,?)',(alert_id,body.outcome,body.note[:500],now)); con.commit(); con.close()
    return {'ok':True,'alert_id':alert_id,'outcome':body.outcome,'created_at':now}

@app.get('/api/alerts/metrics', tags=['Learning loop'])
def alert_metrics():
    con=db()
    rows=con.execute('SELECT outcome,COUNT(*) n FROM alert_feedback GROUP BY outcome').fetchall(); counts={r['outcome']:r['n'] for r in rows}; total=sum(counts.values())
    ar=con.execute('SELECT acknowledged,created_at,acknowledged_at FROM alerts').fetchall(); con.close()
    acked=[r for r in ar if r['acknowledged']]
    ack_minutes=[(r['acknowledged_at']-r['created_at'])/60 for r in acked if r['acknowledged_at'] and r['created_at'] and r['acknowledged_at']>=r['created_at']]
    verified=counts.get('CONFIRMED',0)+counts.get('FALSE_ALARM',0)+counts.get('PARTIAL',0)
    return {'feedback_total':total,'counts':counts,'reviewed_alerts':verified,'confirmed_rate_pct':round(counts.get('CONFIRMED',0)/verified*100,1) if verified else None,'observed_false_alarm_rate_pct':round(counts.get('FALSE_ALARM',0)/verified*100,1) if verified else None,'acknowledgement_rate_pct':round(len(acked)/len(ar)*100,1) if ar else None,'mean_acknowledgement_minutes':round(sum(ack_minutes)/len(ack_minutes),1) if ack_minutes else None,'note':'Operational-learning metrics follow warning-performance literature. They are descriptive only until enough verified real events exist.'}

@app.get('/api/deformation/trend/{location_id}', tags=['Edge & IoT'])
def deformation_trend(location_id:int, hours:int=24):
    _loc(location_id); cutoff=int(time.time())-max(1,min(hours,168))*3600; con=db(); rows=con.execute('SELECT * FROM telemetry WHERE location_id=? AND created_at>=? ORDER BY created_at ASC',(location_id,cutoff)).fetchall(); con.close(); pts=[dict(r) for r in rows]
    if len(pts)<2: return {'location_id':location_id,'available':False,'samples':len(pts),'note':'Need at least two telemetry samples. This is a point-sensor trend screen, not InSAR persistent-homology analysis.'}
    first,last=pts[0],pts[-1]; dt=(last['created_at']-first['created_at'])/3600
    dd=(last.get('displacement_mm') or 0)-(first.get('displacement_mm') or 0); dtilt=(last.get('tilt_deg') or 0)-(first.get('tilt_deg') or 0)
    if dt < (5/60):
        return {'location_id':location_id,'available':False,'samples':len(pts),'window_hours':round(max(dt,0),3),'displacement_change_mm':round(dd,2),'tilt_change_deg':round(dtilt,3),'note':'Samples are too close in time for a meaningful rate. Wait at least 5 minutes between field readings. This is not a failure-time forecast.'}
    velocity=dd/dt; score=min(100,abs(velocity)*18+abs(dtilt)*12+max(0,(last.get('pore_pressure_kpa') or 0)-40)*.7)
    state='ESCALATING' if score>=65 else ('WATCH' if score>=35 else 'STABLE')
    return {'location_id':location_id,'available':True,'samples':len(pts),'window_hours':round(dt,2),'displacement_change_mm':round(dd,2),'displacement_rate_mm_per_h':round(velocity,3),'tilt_change_deg':round(dtilt,3),'precursor_trend_score':round(score,1),'state':state,'note':'Point-sensor deformation trend inspired by precursor literature; not a failure-time forecast and not persistent homology.'}


# ---- Low-bandwidth NASA GIBS tile cache ---------------------------------------
def _active_sat_date(): return (datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
def _nasa_url(date,z,y,x): return f'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg'
def _tile_path(date,z,y,x): return TILE_CACHE/date/str(z)/str(y)/f'{x}.jpg'
def _tile_xy(lon,lat,z):
    lat=max(-85.0511,min(85.0511,lat)); n=2**z
    x=int((lon+180)/360*n); y=int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
    return x,y

def _india_tiles(min_zoom=4,max_zoom=6):
    # Low-zoom cache covers India so western, central, northeastern and peninsular
    # hill systems share the same satellite context.
    west,south,east,north=68.0,6.0,98.5,38.0; out=[]
    for z in range(min_zoom,max_zoom+1):
        x1,y2=_tile_xy(west,south,z); x2,y1=_tile_xy(east,north,z)
        for x in range(min(x1,x2),max(x1,x2)+1):
            for y in range(min(y1,y2),max(y1,y2)+1): out.append((z,y,x))
    return out

def _fetch_tile(date,z,y,x,timeout=4):
    path=_tile_path(date,z,y,x)
    if path.exists() and path.stat().st_size>500: return path,False
    path.parent.mkdir(parents=True,exist_ok=True)
    req=Request(_nasa_url(date,z,y,x),headers={'User-Agent':'PRAHARI/11.0'})
    with urlopen(req,timeout=timeout) as resp:
        data=resp.read(2_000_000)
        ctype=(resp.headers.get('Content-Type') or '').lower()
        if len(data)<500 or ('image' not in ctype and not data.startswith(b'\xff\xd8')): raise ValueError('Invalid imagery response')
    tmp=path.with_suffix('.tmp'); tmp.write_bytes(data); tmp.replace(path)
    return path,True

def _cached_dates():
    return sorted([d.name for d in TILE_CACHE.iterdir() if d.is_dir() and len(d.name)==10], reverse=True) if TILE_CACHE.exists() else []

def _cache_status(max_zoom=6):
    active=_active_sat_date(); tiles=_india_tiles(4,max_zoom); dates=[active]+[d for d in _cached_dates() if d!=active]
    best_date=active; best_cached=0
    for date in dates:
        n=sum(1 for z,y,x in tiles if _tile_path(date,z,y,x).exists())
        if n>best_cached: best_cached=n; best_date=date
    return {'date':best_date,'requested_nrt_date':active,'using_previous_cached_scene':best_date!=active and best_cached>0,'min_zoom':4,'max_zoom':max_zoom,'expected_tiles':len(tiles),'cached_tiles':best_cached,'ready_pct':round(best_cached/max(1,len(tiles))*100,1),'cache_dir':str(TILE_CACHE),'mode':'NASA GIBS NRT local tile cache'}

@app.get('/api/satellite/cache/status', tags=['Satellite / Offline'])
def satellite_cache_status(max_zoom:int=6):
    return _cache_status(max(4,min(7,max_zoom)))

@app.post('/api/satellite/cache/warm', tags=['Satellite / Offline'])
def satellite_cache_warm(max_zoom:int=6):
    max_zoom=max(4,min(7,max_zoom)); date=_active_sat_date(); tiles=_india_tiles(4,max_zoom); failures=[]; downloaded=0; start=time.time()
    def one(t):
        z,y,x=t
        try: return t,_fetch_tile(date,z,y,x,timeout=5)[1],None
        except Exception as exc: return t,False,str(exc)[:120]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for t,new,err in ex.map(one,tiles):
            if new: downloaded+=1
            if err: failures.append({'tile':t,'error':err})
    st=_cache_status(max_zoom); st.update({'downloaded_now':downloaded,'failed':len(failures),'sample_failures':failures[:5],'elapsed_seconds':round(time.time()-start,1),
                                         'instruction':'Run this on good internet before college. Cached NASA tiles then load from localhost with no internet.'})
    return st

@app.get('/api/satellite/tile/{z}/{y}/{x}.jpg', tags=['Satellite / Offline'])
def satellite_cached_tile(z:int,y:int,x:int):
    if z<0 or z>9: raise HTTPException(404,'Unsupported zoom')
    active=_active_sat_date(); date=active; path=_tile_path(active,z,y,x)
    if not path.exists():
        # Prefer an older local scene over a network request. This is what keeps
        # the jury demo working if the college connection is weak or absent.
        for d in _cached_dates():
            candidate=_tile_path(d,z,y,x)
            if candidate.exists(): path=candidate; date=d; break
    if not path.exists():
        try: path,_=_fetch_tile(active,z,y,x,timeout=3); date=active
        except Exception: raise HTTPException(503,'Imagery tile is not cached and upstream NASA imagery is unavailable. Use Offline EO Lite or warm the cache beforehand.')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'public, max-age=604800, immutable','X-PRAHARI-Imagery-Date':date,'X-PRAHARI-Cache':'LOCAL'})



RESEARCH_EVIDENCE = [
 {'paper':'Felsberg et al. (2022)','focus':'Susceptibility uncertainty','gap':'Deterministic susceptibility can hide model/input and spatial-representativeness uncertainty.','response':'Model disagreement, indicative decision interval, blocked bootstrap validation, provenance labels.','status':'IMPLEMENTED'},
 {'paper':'Fathani et al. (2016)','focus':'People-centred LEWS standard','gap':'Prediction alone is insufficient without communication, response teams, evacuation maps, SOPs and local ownership.','response':'Multilingual alerts, response checklist, offline route prototype, acknowledgement, human decision gate.','status':'IMPLEMENTED'},
 {'paper':'Stähli et al. (2015)','focus':'Monitoring & prediction gaps','gap':'Rainfall proxies miss pore pressure, deformation precursors, uncertainty and possible runout.','response':'IoT pore pressure/tilt/displacement fusion + precursor trend + uncertainty. Runout remains roadmap until terrain-calibrated data exist.','status':'PARTIAL'},
 {'paper':'Mei et al. (2025)','focus':'Spatiotemporal InSAR precursors','gap':'Single monitoring points can miss slope-wide deformation patterns.','response':'Point-sensor trend endpoint now; explicit InSAR persistent-homology adapter is roadmap and is not falsely claimed active.','status':'ROADMAP'},
 {'paper':'Khan et al. (2022)','focus':'LHASA forecast','gap':'Operational value improves with multi-day forecast lead time and periodic validation.','response':'Risk trajectory extended through +72 h with transparent forecast provenance.','status':'IMPLEMENTED'},
 {'paper':'Nocentini et al. (2024)','focus':'Dynamic spatiotemporal RF','gap':'Static susceptibility maps do not capture time-varying triggering.','response':'Added 7-day cumulative rain + seasonality to dynamic ensemble features.','status':'IMPLEMENTED'},
 {'paper':'Krøgli et al. (2018)','focus':'Operational national service','gap':'Effective warning needs hydromet stations, history, forecasts, thresholds and trained forecasters.','response':'Multi-source dashboard + operator review gate + 72 h outlook + threshold context.','status':'IMPLEMENTED'},
 {'paper':'Piciullo et al. (2017)','focus':'Warning performance evaluation','gap':'Simple accuracy misses warning duration, alert level, multiple events and error costs.','response':'Alert feedback, false-alarm/confirmation and acknowledgement metrics; full EDuMaP duration matrix is roadmap.','status':'PARTIAL'},
 {'paper':'Pan et al. (2018)','focus':'Rainfall thresholds in data-scarce areas','gap':'Current rain alone misses antecedent wetness; sparse inventories limit calibration.','response':'72 h antecedent rain, 7-day cumulative rain, 11-day decayed effective rain and peak 1 h screening.','status':'IMPLEMENTED'},
 {'paper':'Stanley et al. (2021)','focus':'LHASA v2 XGBoost nowcast','gap':'Threshold-only systems miss nonlinear interactions and probability trade-offs.','response':'Monotonic XGBoost + LightGBM + RF ensemble, probabilistic risk, TreeSHAP and uncertainty.','status':'IMPLEMENTED'},
 {'paper':'Saito et al. (2010)','focus':'Rainfall regimes + soil-water state','gap':'One rainfall threshold cannot represent short-intense and long-saturating triggering.','response':'SHORT_INTENSE / LONG_SATURATING / MIXED regime classifier + soil-water stress indicator.','status':'IMPLEMENTED'},
 {'paper':'Marra et al. (2025)','focus':'ID threshold vs IDF probability','gap':'Confusing trigger thresholds with return-period probability can create misleading probabilities/false alarms.','response':'UI/API explicitly labels threshold output as trigger-condition screening, not IDF return-period probability.','status':'IMPLEMENTED'},
]

@app.get('/api/research/evidence-matrix', tags=['Research'])
def research_evidence_matrix():
    return {'version':'v8','unique_papers_reviewed':len(RESEARCH_EVIDENCE),'items':RESEARCH_EVIDENCE,'principle':'Implement evidence-supported improvements only when the available data can support them; otherwise label them as roadmap rather than simulating scientific capability.'}

@app.get('/api/system/health', tags=['System'])
def system_health_v8():
    cache=_cache_status(6)
    con=db(); tele=con.execute('SELECT COUNT(*) n FROM telemetry').fetchone()['n']; con.close()
    return {
        'project':'PRAHARI','api_version':'11.0.0','status':'READY',
        'ml_engine':'NOT_DEPLOYED','ml_loaded':False,
        'weather':'LIVE_WITH_TRANSPARENT_STALE_OR_MISSING_STATES',
        'terrain':'OPEN_METEO_ELEVATION',
        'satellite':{'scene_discovery':'READY','local_nasa_cache_pct':cache['ready_pct']},
        'edge_iot':{'ingest_api':'READY','telemetry_records':tele,'operational_source':'REAL_SENSOR_ONLY'},
        'exposure_gis':'NOT_CONNECTED','routing_gis':'NOT_CONNECTED'
    }

@app.get('/api/research/data-readiness', tags=['Research'])
def research_data_readiness():
    return {
        'live_dynamic':['1/3/6h forecast rainfall','24h rainfall','72h antecedent rainfall','model soil moisture','provider elevation/slope proxy'],
        'optional_real_sensor':['water level','rainfall intensity','soil moisture','tilt','vibration','pore pressure','displacement'],
        'available_context':['Sentinel-2 scene discovery','field reports','assessment/advisory audit trail'],
        'not_connected':['watershed-mean gauge/radar/satellite rainfall fusion','verified flood inventory','hydrologic routing','2D inundation','exposure GIS','spatially validated susceptibility ML','conformal uncertainty'],
        'policy':'Unavailable scientific inputs remain unavailable rather than being filled with demo values.'
    }

@app.get('/api/geofence/check', tags=['People-centred EWS'])
def geofence_check(lat:float=Query(...,ge=-90,le=90), lon:float=Query(...,ge=-180,le=180), radius_km:float=Query(25,ge=1,le=100)):
    data=LIVE_REGIONAL_CACHE.get('data') or locs(); nearby=[]
    for x in data:
        d=_haversine(lat,lon,x['lat'],x['lon'])
        if d<=radius_km:
            imp=impact_assessment_value(x['id'],x['risk_percent'])
            nearby.append({'location_id':x['id'],'location':f"{x['name']}, {x['state']}",'distance_km':round(d,1),'risk_level':x['risk_level'],'risk_percent':x['risk_percent'],'impact_priority':imp['priority'],'recommended_action':action_for(x['risk_level'])})
    nearby.sort(key=lambda a:(0 if a['risk_level']=='CRITICAL' else 1 if a['risk_level']=='HIGH' else 2, a['distance_km']))
    danger=[x for x in nearby if x['risk_level'] in ('HIGH','CRITICAL')]
    return {'lat':lat,'lon':lon,'radius_km':radius_km,'inside_monitored_geofence':bool(nearby),'danger_nearby':bool(danger),'nearby':nearby,
            'message':('Dangerous monitored zone nearby — follow the listed action and official authority instructions.' if danger else 'No HIGH/CRITICAL PRAHARI monitored zone found within the selected radius.'),
            'note':'Geo-fence is a prototype location-targeting aid, not an official evacuation boundary.'}


from broadcast_api import routes as broadcast_routes
app.include_router(broadcast_routes(db, LOCATIONS, _alert_broadcast_text))


from flood_api import routes as flood_routes
app.include_router(flood_routes(db, LOCATIONS, lambda x: fetch_live_weather(x), build_replay_packet, localized_alert))
