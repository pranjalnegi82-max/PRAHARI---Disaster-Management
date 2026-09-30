import React, {useEffect, useRef, useState} from 'react';
import {MapContainer, TileLayer, CircleMarker, Popup} from 'react-leaflet';
import {get, post, downloadUrl} from './api.js';

import {value,date,freshness,draftEligible,missingLabel,historyCsv} from './floodView.js';
const color={LOW:'#087f6c',MODERATE:'#a56608',HIGH:'#d26726',CRITICAL:'#c23950',UNKNOWN:'#697b87'};

function validateAssessment(data) {
  if (!data || typeof data.status !== 'string' || !Array.isArray(data.windows) ||
      !Array.isArray(data.missing) || !data.basin || !Array.isArray(data.basin.villages)) {
    throw new Error('Flood service returned incomplete data.');
  }
  return data;
}

export default function FlashFloodPanel({selected, readOnly=false, onRefreshAlerts,alerts=[],onOpenAlerts,refreshToken=0}) {
  const [result,setResult]=useState(null), [history,setHistory]=useState([]);
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState(''), [recordId,setRecordId]=useState(null);
  const id=selected?.id;
  const [tileFailed,setTileFailed]=useState(false),[tileKey,setTileKey]=useState(0);
  const [auto,setAuto]=useState(false),[now,setNow]=useState(Date.now()/1000),[filter,setFilter]=useState('ALL'),[detail,setDetail]=useState(null);
  const busyRef=useRef(false),loadRef=useRef(null);
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()/1000),15000);return()=>clearInterval(timer);},[]);
  useEffect(()=>{if(!auto)return;const timer=setInterval(()=>{if(!document.hidden&&!busyRef.current)loadRef.current?.(false);},60000);return()=>clearInterval(timer);},[auto,id]);


  const generation=useRef(0), active=useRef(null);
  const [historyError,setHistoryError]=useState('');
  function begin(clear=false) {
    active.current?.abort();
    const controller=new AbortController(); active.current=controller;
    const seq=++generation.current;
    busyRef.current=true;setBusy(true);setError('');setNotice('');setHistoryError('');
    if(clear){setResult(null);setHistory([]);setRecordId(null);}
    return {options:{timeout:15000,signal:controller.signal},current:()=>seq===generation.current&&!controller.signal.aborted};
  }
  async function load(clear=false) {
    if(!id)return;
    const task=begin(clear);setRecordId(null);
    get(`/api/flood/history/${id}`,task.options).then(h=>{if(task.current())setHistory(h);})
      .catch(e=>{if(task.current())setHistoryError(e.message);});
    try {
      const r=await get(`/api/flood/screen/${id}`,task.options);
      if(task.current()){setResult(validateAssessment(r));if(!clear)Promise.resolve(onRefreshAlerts?.()).catch(()=>{});}
    } catch(e) {if(task.current())setError(e.message);}
    finally {if(task.current()){busyRef.current=false;setBusy(false);}}
  }
  loadRef.current=load;
  useEffect(()=>{setTileFailed(false);setDetail(null);setFilter('ALL');load(true);return()=>{generation.current++;active.current?.abort();};},[id,refreshToken]);

  async function run(){
    const task=begin();setRecordId(null);
    try {
      const out=await post(`/api/flood/assessments/${id}`,{},task.options);
      if(!task.current())return;
      setResult(validateAssessment(out.assessment));setRecordId(out.id);
      setNotice(`Assessment #${out.id} recorded.`);
      try {const h=await get(`/api/flood/history/${id}`,task.options);if(task.current())setHistory(h);}
      catch(e){if(task.current())setHistoryError(e.message);}
    }catch(e){if(task.current())setError(e.message);}
    finally{if(task.current()){busyRef.current=false;setBusy(false);}}
  }
  async function draft(){
    const task=begin();
    try {
      const out=await post(`/api/flood/records/${recordId}/draft`,{},task.options);
      if(!task.current())return;
      setNotice(`Draft #${out.alert.id} created.`);
      await onRefreshAlerts?.();
    }catch(e){if(task.current())setError(e.message);}
    finally{if(task.current()){busyRef.current=false;setBusy(false);}}
  }

  const verified=result?.basin?.context_status==='CONFIGURED';
  const eligible=draftEligible(result,recordId,now);
  const center=result?.basin?.villages?.[0]||selected;
  const state=freshness(result,now);
  const gaugeFresh=result?.sensor_used&&state==='Current'&&now-result.sensor.observed_at>=0&&now-result.sensor.observed_at<=900;
  const visibleHistory=history.filter(h=>filter==='ALL'||h.assessment.level===filter);
  const areaAlerts=(alerts||[]).filter(a=>a.location_id===id&&['ISSUED','ACKNOWLEDGED'].includes(a.lifecycle_status));
  function exportHistory(){
    const url=URL.createObjectURL(new Blob([historyCsv(visibleHistory)],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=`prahari-area-${id}-assessments.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  return <div className="flood-page command-dashboard">
    <header className="page-title">
      <div><span className="hero-kicker">Hilly-region monitoring</span><h1>Flash Flood Intelligence</h1><p>{selected?.name || 'Select a monitored area'}{selected?.state?` · ${selected.state}`:''}</p></div>
      <div className="dashboard-actions"><button className="btn btn-secondary" disabled={busy||!id} onClick={()=>load(false)}>Refresh</button>
      {!readOnly&&<button className="btn btn-primary" disabled={busy||!id} onClick={run}>{busy?'Refreshing…':'Run assessment'}</button>}</div>
    </header>

    {error&&<div className="notice notice-error" role="alert"><span>{error}</span><button className="btn btn-secondary" disabled={busy} onClick={load}>Retry</button></div>}
    {notice&&<div className="notice" role="status">{notice}</div>}
    {busy&&!result&&<p role="status">Loading current hydrometeorological data…</p>}

    {result&&<>
      <div className="data-status-bar"><span className={`source-state ${state==='Current'?'current':'degraded'}`}><i/>{state}</span><span>Provider time <strong>{date(result.valid_at_epoch)}</strong></span><span>Checked <strong>{date(result.created_at)}</strong></span><label className="auto-refresh"><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/>Auto-refresh · 1 min</label></div>
      {state!=='Current'&&<div className="notice notice-warning" role="status">{state==='Stale'?'Showing the last available observations.':'Current observations unavailable.'}</div>}

      <section className="flood-kpi-grid">
        <article className="metric-card"><span>Flood screening</span><strong style={{color:color[result.level]}}>{result.level==='UNKNOWN'?'Unavailable':result.level}</strong><small>{verified?'Locally configured thresholds':'Research thresholds · uncalibrated'}</small></article>
        <article className="metric-card"><span>1 h rainfall</span><strong>{value(result.windows.find(x=>x.hours===1)?.rainfall_mm)} mm</strong><small>{result.windows.find(x=>x.hours===1)?.level}</small></article>
        <article className="metric-card"><span>3 h rainfall</span><strong>{value(result.windows.find(x=>x.hours===3)?.rainfall_mm)} mm</strong><small>{result.windows.find(x=>x.hours===3)?.level}</small></article>
        <article className="metric-card"><span>6 h rainfall</span><strong>{value(result.windows.find(x=>x.hours===6)?.rainfall_mm)} mm</strong><small>{result.windows.find(x=>x.hours===6)?.level}</small></article>
      </section>

      {result.missing.length>0&&<div className="notice notice-error">Unavailable: {result.missing.map(missingLabel).join(' · ')}</div>}

      <div className="flood-columns">
        <section className="panel">
          <div className="section-heading"><div><span className="eyebrow">Monitoring area</span><h2>{result.basin.name}</h2></div><span className="section-meta">{verified?'Local profile':'Regional screen'}</span></div>
          {center&&<div className="flood-map"><MapContainer key={JSON.stringify(result.basin.villages)} center={[center.lat,center.lon]} zoom={11} style={{height:'100%',width:'100%'}}>
            <TileLayer key={tileKey} eventHandlers={{tileerror:()=>setTileFailed(true)}} url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap contributors'/>
            {result.basin.villages.map((v,i)=><CircleMarker key={i} center={[v.lat,v.lon]} radius={8}><Popup>{v.name}</Popup></CircleMarker>)}
          </MapContainer></div>}
          <div className="map-coordinates">Lat {value(selected?.lat,4)} · Lon {value(selected?.lon,4)}{tileFailed&&<button className="btn btn-ghost small" onClick={()=>{setTileFailed(false);setTileKey(k=>k+1);}}>Retry map tiles</button>}</div><div className="mini-list">{result.basin.villages.map((v,i)=><span key={i}>{v.name}</span>)}</div>
        </section>

        <section className="panel">
          <div className="section-heading"><div><span className="eyebrow">Hydrometeorology</span><h2>Current drivers</h2></div><span className="section-meta">{date(result.valid_at_epoch)}</span></div>
          <div className="status-grid">
            <div><span>Soil wetness</span><strong>{value(result.soil_wetness_proxy_pct)}%</strong></div>
            <div><span>72 h rainfall</span><strong>{value(result.antecedent_rainfall_72h_mm)} mm</strong></div>
            <div><span>Terrain gradient</span><strong>{value(result.terrain_slope_deg??selected?.slope)}°</strong></div>
            <div><span>Elevation</span><strong>{value(result.terrain_elevation_m??selected?.elevation)} m</strong></div>
          </div>
          <div className="gauge-reading"><span>River gauge</span><strong>{gaugeFresh?`${value(result.sensor?.water_level_m)} m`:'Unavailable'}</strong><small>{gaugeFresh?`${result.sensor.station_id} · ${date(result.sensor.observed_at)}`:result.sensor?'No eligible current reading':'No current station observation'}</small>{gaugeFresh&&<small>Danger stage {value(result.basin.danger_stage_m)} m</small>}</div>
          {!readOnly&&eligible&&<button className="btn btn-primary" disabled={busy} onClick={draft}>Create alert draft</button>}
          <div className="source-caption">{result.source || 'Weather source unavailable'} · {result.transport==='BROWSER_DIRECT_RELAY'?'Browser relay':'Server feed'}</div>
        </section>
      </div>

      <section className="panel">
        <div className="section-heading"><div><span className="eyebrow">Threshold windows</span><h2>Rainfall exceedance</h2></div><span className="section-meta">{result.source || 'Live source'}</span></div>
        <div className="flood-windows">{result.windows.map(w=><article className="metric-card" key={w.hours}><span>{w.hours} hour</span><strong>{value(w.rainfall_mm)} mm</strong><div className="rain-comparison" aria-label={`${w.hours}-hour rainfall ${value(w.rainfall_mm)} mm, screening threshold ${value(w.screening_threshold_mm)} mm`}><span style={{width:`${Math.min(100,(w.exceedance_ratio||0)*50)}%`,background:color[w.level]}}/><i/></div><small>Threshold {value(w.screening_threshold_mm)} mm · {w.level==='UNKNOWN'?'Unavailable':`${value(w.exceedance_ratio)}× threshold`}</small></article>)}</div>
      </section>

      <div className="dashboard-bottom">
      <section className="panel"><div className="section-heading"><div><span className="eyebrow">Response</span><h2>Active advisories</h2></div>{onOpenAlerts&&<button className="btn btn-ghost small" onClick={onOpenAlerts}>View alerts →</button>}</div>
        {areaAlerts.length?areaAlerts.slice(0,4).map(a=><article className="advisory-summary" key={a.id}><span style={{color:color[a.level]}}>{a.level} · {(a.advisory_type||'LANDSLIDE').replaceAll('_',' ')}</span><p>{a.message}</p><small>{date(a.issued_at||a.created_at)} · {a.lifecycle_status}</small></article>):<div className="dashboard-empty"><span>{alerts?'✓':'—'}</span><strong>{alerts?'No active issued advisories':'Advisories unavailable'}</strong><small>{alerts?'For this monitored area':'Refresh to retry'}</small></div>}
      </section>
      <section className="panel"><div className="section-heading"><div><span className="eyebrow">Evidence</span><h2>Source details</h2></div></div><dl className="source-details"><dt>Profile</dt><dd>{verified?'Locally configured':'Automatic research screening'}</dd><dt>Terrain</dt><dd>{result.terrain_source||selected?.terrain_source||'Unavailable'}</dd><dt>Model</dt><dd>{result.version}</dd><dt>Coverage</dt><dd>Point weather · settlement markers</dd></dl><details className="screening-details"><summary>Screening basis</summary><p>{result.basin.provenance}</p><p>Rainfall windows are accumulation periods. Flood arrival time and inundation extent are not calculated.</p></details></section>
      </div>
      <section className="panel"><div className="section-heading"><div><span className="eyebrow">Records</span><h2>Assessment history</h2></div><div className="dashboard-actions"><label className="sr-only" htmlFor="history-level">Filter history by risk level</label><select id="history-level" value={filter} onChange={e=>setFilter(e.target.value)}>{['ALL','LOW','MODERATE','HIGH','CRITICAL','UNKNOWN'].map(x=><option key={x} value={x}>{x==='ALL'?'All levels':x}</option>)}</select><button className="btn btn-secondary small" disabled={!visibleHistory.length} onClick={exportHistory}>Export CSV</button></div></div>
        {historyError&&<p role="alert">History unavailable. {historyError}</p>}
        {visibleHistory.length===0?<div className="dashboard-empty"><strong>{history.length?'No matching assessments':'No recorded assessments'}</strong></div>:<div className="flood-history">{visibleHistory.map(h=><div key={h.id}><button className="history-record" onClick={()=>setDetail(detail?.id===h.id?null:h)}>#{h.id} <span style={{color:color[h.assessment.level]}}>{h.assessment.level}</span></button><span>{date(h.assessment.created_at)}</span><span>{h.assessment.data_state}</span><a href={downloadUrl(`/api/flood/records/${h.id}`)} target="_blank" rel="noreferrer">JSON ↗</a></div>)}</div>}
        {detail&&<div className="record-detail"><div className="section-heading"><h3>Record #{detail.id}</h3><button className="btn btn-ghost small" onClick={()=>setDetail(null)}>Close record</button></div><p>Provider time {date(detail.assessment.valid_at_epoch)} · {detail.assessment.source}</p><div className="record-windows">{detail.assessment.windows.map(w=><div key={w.hours}><span>{w.hours} hours</span><strong>{value(w.rainfall_mm)} mm</strong><small>Threshold {value(w.screening_threshold_mm)} mm</small></div>)}</div></div>}
      </section>
    </>}
  </div>;
}
