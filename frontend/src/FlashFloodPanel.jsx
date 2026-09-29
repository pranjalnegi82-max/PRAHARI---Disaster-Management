import React, {useEffect, useMemo, useState} from 'react';
import {MapContainer, TileLayer, CircleMarker, Popup} from 'react-leaflet';
import {get, post, downloadUrl} from './api.js';

const value = v => v == null ? '—' : Number(v).toFixed(1);
const date = v => v ? new Date(v * 1000).toLocaleString() : '—';

function blankConfig(selected) {
  return {
    name: `${selected?.name || 'Monitored area'} catchment`,
    context_status: 'CONFIGURED',
    provenance: '',
    thresholds_mm: {'1': 0, '3': 0, '6': 0},
    villages: selected ? [{name:selected.name, lat:selected.lat, lon:selected.lon}] : [],
    slope_context: '',
    historical_events_source: '',
    station_id: null,
    danger_stage_m: null
  };
}

function validateAssessment(data) {
  if (!data || typeof data.status !== 'string' || !Array.isArray(data.windows) ||
      !Array.isArray(data.missing) || !data.basin || !Array.isArray(data.basin.villages)) {
    throw new Error('Flood service returned incomplete data.');
  }
  return data;
}

export default function FlashFloodPanel({selected, readOnly=false, onRefreshAlerts}) {
  const [result,setResult]=useState(null), [history,setHistory]=useState([]), [config,setConfig]=useState('');
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState(''), [recordId,setRecordId]=useState(null);
  const [configured,setConfigured]=useState(true);
  const id=selected?.id;

  const configObject=useMemo(()=>{try{return JSON.parse(config)}catch{return null}},[config]);

  async function load() {
    if(!id)return;
    setBusy(true); setError(''); setNotice('');
    try {
      const basin=await get(`/api/flood/basins/${id}`);
      setConfigured(true);
      setConfig(JSON.stringify(basin,null,2));
      const [r,h]=await Promise.all([get(`/api/flood/screen/${id}`),get(`/api/flood/history/${id}`)]);
      setResult(validateAssessment(r)); setHistory(h);
    } catch(e) {
      if(String(e.message).includes('Catchment configuration required')) {
        setConfigured(false); setResult(null); setHistory([]);
        setConfig(JSON.stringify(blankConfig(selected),null,2));
      } else setError(e.message);
    } finally { setBusy(false); }
  }

  useEffect(()=>{load();},[id]);

  async function run(){
    setBusy(true);setError('');setNotice('');setRecordId(null);
    try{
      const out=await post(`/api/flood/assessments/${id}`,{});
      setResult(validateAssessment(out.assessment));setRecordId(out.id);
      setHistory(await get(`/api/flood/history/${id}`));
      setNotice(`Assessment #${out.id} recorded.`);
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function save(){
    setBusy(true);setError('');setNotice('');
    try{
      if(!configObject) throw new Error('Catchment configuration is not valid JSON.');
      await post(`/api/flood/basins/${id}`,configObject);
      setConfigured(true);setRecordId(null);setNotice('Catchment configuration saved.');
      await load();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function draft(){
    setBusy(true);setError('');
    try{
      const out=await post(`/api/flood/records/${recordId}/draft`,{});
      setNotice(`Draft #${out.alert.id} created.`);
      await onRefreshAlerts?.();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  const eligible=recordId && result?.data_state==='CURRENT' && result?.status==='SCREENED' && ['HIGH','CRITICAL'].includes(result?.level);

  return <div className="flood-page">
    <header className="page-title">
      <div><span className="hero-kicker">Hilly-region monitoring</span><h1>Flash Flood Intelligence</h1><p>{selected?.name || 'Select a monitored area'}</p></div>
      {!readOnly&&configured&&<button className="btn btn-primary" disabled={busy||!id} onClick={run}>{busy?'Refreshing…':'Run assessment'}</button>}
    </header>

    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {notice&&<div className="notice" role="status">{notice}</div>}

    {!configured&&<section className="panel flood-setup">
      <h2>Catchment configuration required</h2>
      {!readOnly&&<><label className="field"><span>Catchment configuration</span><textarea className="flood-config" value={config} onChange={e=>setConfig(e.target.value)} spellCheck="false"/></label><button className="btn btn-primary" disabled={busy} onClick={save}>Save</button></>}
    </section>}

    {busy&&!result&&configured&&<p role="status">Loading current hydrometeorological data…</p>}

    {result&&<>
      <section className="flood-kpi-grid">
        <article className="metric-card"><span>Risk level</span><strong>{result.level}</strong><small>{result.status.replaceAll('_',' ')}</small></article>
        <article className="metric-card"><span>1 h rainfall</span><strong>{value(result.windows.find(x=>x.hours===1)?.rainfall_mm)} mm</strong><small>{result.windows.find(x=>x.hours===1)?.level}</small></article>
        <article className="metric-card"><span>3 h rainfall</span><strong>{value(result.windows.find(x=>x.hours===3)?.rainfall_mm)} mm</strong><small>{result.windows.find(x=>x.hours===3)?.level}</small></article>
        <article className="metric-card"><span>6 h rainfall</span><strong>{value(result.windows.find(x=>x.hours===6)?.rainfall_mm)} mm</strong><small>{result.windows.find(x=>x.hours===6)?.level}</small></article>
      </section>

      {result.missing.length>0&&<div className="notice notice-error">Missing inputs: {result.missing.join(', ')}</div>}

      <div className="flood-columns">
        <section className="panel">
          <div className="section-heading"><div><span className="eyebrow">Catchment</span><h2>{result.basin.name}</h2></div><span className="section-meta">{result.data_state}</span></div>
          <div className="flood-map"><MapContainer key={JSON.stringify(result.basin.villages)} center={[result.basin.villages[0].lat,result.basin.villages[0].lon]} zoom={11} style={{height:'100%',width:'100%'}}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap contributors'/>
            {result.basin.villages.map((v,i)=><CircleMarker key={i} center={[v.lat,v.lon]} radius={8}><Popup>{v.name}</Popup></CircleMarker>)}
          </MapContainer></div>
          <div className="mini-list">{result.basin.villages.map((v,i)=><span key={i}>{v.name}</span>)}</div>
        </section>

        <section className="panel">
          <div className="section-heading"><div><span className="eyebrow">Hydrometeorology</span><h2>Current drivers</h2></div><span className="section-meta">{date(result.valid_at_epoch)}</span></div>
          <div className="status-grid">
            <div><span>Soil wetness</span><strong>{value(result.soil_wetness_proxy_pct)}%</strong></div>
            <div><span>72 h rainfall</span><strong>{value(result.antecedent_rainfall_72h_mm)} mm</strong></div>
            <div><span>Water level</span><strong>{result.sensor_used?value(result.sensor?.water_level_m)+' m':'—'}</strong></div>
            <div><span>Source</span><strong>{result.source || '—'}</strong></div>
          </div>
          {!readOnly&&<button className="btn btn-primary" disabled={busy||!eligible} onClick={draft}>Create alert draft</button>}
        </section>
      </div>

      <section className="panel">
        <div className="section-heading"><div><span className="eyebrow">Threshold windows</span><h2>Rainfall exceedance</h2></div></div>
        <div className="flood-windows">{result.windows.map(w=><article className="metric-card" key={w.hours}><span>{w.hours} hour</span><strong>{value(w.rainfall_mm)} mm</strong><small>Threshold {value(w.screening_threshold_mm)} mm · ratio {value(w.exceedance_ratio)} · {w.level}</small></article>)}</div>
      </section>

      <section className="panel"><div className="section-heading"><div><span className="eyebrow">Records</span><h2>Assessment history</h2></div></div>
        {history.length===0?<p className="muted">No recorded assessments.</p>:<div className="flood-history">{history.map(h=><div key={h.id}><strong>#{h.id} · {h.assessment.level}</strong><span>{date(h.assessment.created_at)} · {h.assessment.data_state}</span><a href={downloadUrl(`/api/flood/records/${h.id}`)} target="_blank" rel="noreferrer">JSON</a></div>)}</div>}
      </section>

      {!readOnly&&<details className="panel"><summary>Catchment settings</summary><label className="field"><span>Configuration</span><textarea className="flood-config" value={config} onChange={e=>setConfig(e.target.value)} spellCheck="false"/></label><button className="btn btn-secondary" disabled={busy} onClick={save}>Save</button></details>}
    </>}
  </div>;
}
