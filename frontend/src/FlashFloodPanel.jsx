import React, {useEffect, useState} from 'react';
import {MapContainer, TileLayer, CircleMarker, Popup} from 'react-leaflet';
import {get, post, downloadUrl} from './api.js';

const value = v => v == null ? 'Unavailable' : Number(v).toFixed(1);
const date = v => v ? new Date(v * 1000).toLocaleString() : 'Unavailable';

export default function FlashFloodPanel({selected, mode='live', readOnly=false, onRefreshAlerts}) {
  const [result,setResult]=useState(null), [history,setHistory]=useState([]), [config,setConfig]=useState('');
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState(''), [recordId,setRecordId]=useState(null);
  const id=selected?.id;
  useEffect(()=>{
    if(!id)return;
    const controller=new AbortController();
    setBusy(true);
    Promise.all([get(`/api/flood/screen/${id}?mode=${mode}`,{signal:controller.signal}),get(`/api/flood/history/${id}`,{signal:controller.signal})])
      .then(([r,h])=>{setResult(r);setConfig(JSON.stringify(r.basin,null,2));setHistory(h);})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setBusy(false);});
    return ()=>controller.abort();
  },[id,mode]);
  async function run(){
    setBusy(true);setError('');setNotice('');setRecordId(null);
    try{const out=await post(`/api/flood/assessments/${id}?mode=${mode}`,{});setResult(out.assessment);setRecordId(out.id);setHistory(await get(`/api/flood/history/${id}`));setNotice(`Flood assessment #${out.id} recorded. No messages have been sent.`);}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function save(){
    setBusy(true);setError('');setNotice('');
    try{await post(`/api/flood/basins/${id}`,JSON.parse(config));setRecordId(null);setResult(await get(`/api/flood/screen/${id}?mode=${mode}`));setNotice('Catchment configuration saved. CONFIGURED does not mean scientifically validated.');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function draft(){
    setBusy(true);setError('');
    try{const out=await post(`/api/flood/records/${recordId}/draft`,{});setNotice(`Draft #${out.alert.id} created. Open Reports & Alerts to review it. SMS delivery uses the monitored area, not individual village boundaries.`);await onRefreshAlerts?.();}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const eligible=recordId && result?.mode==='live' && result?.data_state==='CURRENT' && result?.basin.context_status==='CONFIGURED' && result?.status==='SCREENED' && ['HIGH','CRITICAL'].includes(result?.level);
  return <div className="flood-page">
    <header className="page-title"><div><span className="hero-kicker">SIH26192 · Multi-source decision support</span><h1>Flash Floods</h1><p>{selected?.name || 'Select an area'} · Catchment conditions and village preparedness</p></div>
      {!readOnly&&<button className="btn btn-primary" disabled={busy||!id} onClick={run}>{busy?'Loading…':'Record flood assessment'}</button>}
    </header>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {notice&&<div className="notice" role="status">{notice}</div>}
    {busy&&!result&&<p role="status">Loading flood inputs…</p>}
    {result&&<>
      <section className="flood-banner">
        <div><span className="flood-eyebrow">Flash flood screening</span><h2>{result.level}</h2><p>{result.status.replaceAll('_',' ')}</p></div>
        <div><strong>{mode==='replay'?'Synthetic storm scenario':result.data_state}</strong><p>{result.source}</p><small>Provider valid time: {result.valid_time || 'Unavailable'}<br/>Fetched: {date(result.fetched_at)}</small></div>
        <div><strong>Lead time: unvalidated</strong><p>1 / 3 / 6 hours are forecast windows.</p><small>No flood arrival time is estimated.</small></div>
      </section>
      <div className="notice">{result.basin.context_status==='DEMO'?'Demonstration catchment and settlement coordinates. Configure local data before creating flood advisories.':'Configured catchment. Local thresholds and village exposure still require validation.'} Rainfall is a point weather-model proxy.</div>
      {result.missing.length>0&&<div className="notice notice-error">Missing or invalid inputs: {result.missing.join(', ')}. An unknown result must not be interpreted as low risk.</div>}
      <div className="flood-windows">{result.windows.map(w=><section className="panel" key={w.hours}>
        <span className="flood-eyebrow">Next {w.hours} hour{w.hours>1?'s':''}</span><h2>{value(w.rainfall_mm)} <small>mm rain</small></h2>
        <p>Adjusted screening threshold: {value(w.screening_threshold_mm)} mm</p><p>Threshold ratio: {value(w.exceedance_ratio)} · <strong>{w.level}</strong></p>
      </section>)}</div>
      <div className="flood-columns">
        <section className="panel"><h2>Catchment & settlement context</h2><p><strong>{result.basin.name}</strong></p><p>{result.basin.provenance}</p>
          <div className="flood-map"><MapContainer key={JSON.stringify(result.basin.villages)} center={[result.basin.villages[0].lat,result.basin.villages[0].lon]} zoom={11} style={{height:'100%',width:'100%'}}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap contributors'/>
            {result.basin.villages.map((v,i)=><CircleMarker key={i} center={[v.lat,v.lon]} radius={8} pathOptions={{color:'#087e8b'}}><Popup>{v.name}<br/>Configured settlement point; no inundation boundary.</Popup></CircleMarker>)}
          </MapContainer></div>
          <ul>{result.basin.villages.map((v,i)=><li key={i}>{v.name} · {v.lat}, {v.lon}</li>)}</ul>
        </section>
        <section className="panel"><h2>Inputs & response readiness</h2>
          <p>Soil wetness proxy: <strong>{value(result.soil_wetness_proxy_pct)}%</strong></p>
          <p>Previous 72 hours rainfall: <strong>{value(result.antecedent_rainfall_72h_mm)} mm</strong></p>
          <p>Terrain: {result.basin.slope_context}</p><p>Historical inventory: {result.basin.historical_events_source}</p>
          <p>Water-level sensor: <strong>{result.sensor_used?'Used in screening':'No eligible current reading'}</strong></p>
          {result.sensor&&<p>{result.sensor.station_id}: {value(result.sensor.water_level_m)} m · observed {date(result.sensor.observed_at)} · quality {result.sensor.quality}</p>}
          <p>Field teams should verify stream conditions and local access, contact responsible authorities, and check preparedness for the configured settlements.</p>
          {!readOnly&&<button className="btn btn-primary" disabled={busy||!eligible} onClick={draft}>Create reviewed-workflow draft</button>}
          <p className="fine">Drafts require a recorded, current, complete high/critical live assessment and configured catchment. Review and issue happen in Reports & Alerts.</p>
        </section>
      </div>
      <section className="panel"><h2>Assessment history</h2>{history.length===0?<p>No flood assessments recorded for this area.</p>:<div className="flood-history">{history.map(h=><div key={h.id}><strong>#{h.id} · {h.assessment.level}</strong><span>{date(h.assessment.created_at)} · {h.assessment.mode==='replay'?'Synthetic scenario':h.assessment.data_state}</span><a href={downloadUrl(`/api/flood/records/${h.id}`)} target="_blank" rel="noreferrer">Export JSON</a></div>)}</div>}</section>
      {!readOnly&&<details className="panel"><summary>Configure catchment, villages & gauge (admin)</summary><p>Provide local sources, duration thresholds and village coordinates. Set context_status to CONFIGURED only after replacing demo values. Gauge danger_stage_m must use the same vertical datum as the registered station. This does not certify the model.</p><label className="field"><span>Catchment configuration JSON</span><textarea className="flood-config" value={config} onChange={e=>setConfig(e.target.value)} spellCheck="false"/></label><button className="btn btn-secondary" disabled={busy} onClick={save}>Save configuration</button></details>}
      <details className="panel"><summary>Model boundaries & provenance</summary><ul>{result.limitations.map(s=><li key={s}>{s}</li>)}</ul><p>Model: {result.version}. Demo thresholds: 30 / 60 / 100 mm, adjusted by a documented experimental wetness factor. Landslide screening is available in Overview and Risk Map.</p></details>
    </>}
  </div>;
}
