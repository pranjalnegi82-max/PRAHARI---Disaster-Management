import React, {useEffect, useMemo, useState} from 'react';
import {CircleMarker, MapContainer, Popup, TileLayer} from 'react-leaflet';
import {downloadUrl, get, post} from './api.js';

const fmt=v=>v==null?'—':Number(v).toFixed(1);
const stamp=v=>v?new Date(v*1000).toLocaleString():'—';

function normalize(data){
  if(!data || typeof data.status!=='string' || !Array.isArray(data.windows) || !data.basin) {
    throw new Error('Flood service returned an incomplete response.');
  }
  return data;
}

function statusTone(level){
  return level==='CRITICAL'?'critical':level==='HIGH'?'high':level==='MODERATE'?'moderate':level==='LOW'?'low':'unknown';
}

export default function FlashFloodPanel({selected, readOnly=false, onRefreshAlerts}) {
  const [result,setResult]=useState(null);
  const [history,setHistory]=useState([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [recordId,setRecordId]=useState(null);
  const [editing,setEditing]=useState(false);
  const [form,setForm]=useState(null);
  const id=selected?.id;

  useEffect(()=>{
    if(!id)return;
    const controller=new AbortController();
    setBusy(true);setError('');setNotice('');setRecordId(null);
    Promise.all([
      get(`/api/flood/screen/${id}`,{signal:controller.signal}),
      get(`/api/flood/history/${id}`,{signal:controller.signal})
    ]).then(([screen,rows])=>{
      const next=normalize(screen);
      setResult(next);setHistory(rows);
      const basin=next.basin||{};
      setForm({
        name:basin.name||`${selected.name} catchment`,
        provenance:basin.provenance||'',
        t1:basin.thresholds_mm?.['1']??'',
        t3:basin.thresholds_mm?.['3']??'',
        t6:basin.thresholds_mm?.['6']??'',
        villageName:basin.villages?.[0]?.name||'',
        villageLat:basin.villages?.[0]?.lat??selected.lat,
        villageLon:basin.villages?.[0]?.lon??selected.lon,
        stationId:basin.station_id||'',
        dangerStage:basin.danger_stage_m??''
      });
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setBusy(false);});
    return()=>controller.abort();
  },[id]);

  async function refresh(){
    const next=normalize(await get(`/api/flood/screen/${id}`));
    setResult(next);
    setHistory(await get(`/api/flood/history/${id}`));
  }

  async function record(){
    setBusy(true);setError('');setNotice('');
    try{
      const out=await post(`/api/flood/assessments/${id}`,{});
      setResult(normalize(out.assessment));setRecordId(out.id);
      setHistory(await get(`/api/flood/history/${id}`));
      setNotice(`Assessment #${out.id} recorded.`);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }

  async function saveConfig(e){
    e.preventDefault();setBusy(true);setError('');setNotice('');
    try{
      const thresholdText=[form.t1,form.t3,form.t6].map(v=>String(v).trim());
      const thresholds=thresholdText.map(Number);
      const hasCore=!!form.provenance.trim() && !!form.villageName.trim() && thresholdText.every(Boolean) && thresholds.every(Number.isFinite);
      const hasGauge=form.stationId.trim() || form.dangerStage!=='';
      const body={
        name:form.name.trim()||`${selected.name} catchment`,
        context_status:hasCore?'CONFIGURED':'UNCONFIGURED',
        provenance:form.provenance.trim(),
        thresholds_mm:hasCore?{'1':thresholds[0],'3':thresholds[1],'6':thresholds[2]}:null,
        villages:hasCore?[{name:form.villageName.trim(),lat:Number(form.villageLat),lon:Number(form.villageLon)}]:[],
        slope_context:'',
        historical_events_source:'',
        station_id:hasGauge?form.stationId.trim():null,
        danger_stage_m:hasGauge?Number(form.dangerStage):null
      };
      await post(`/api/flood/basins/${id}`,body);
      await refresh();setEditing(false);setRecordId(null);setNotice('Catchment settings saved.');
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }

  async function createDraft(){
    setBusy(true);setError('');setNotice('');
    try{
      const out=await post(`/api/flood/records/${recordId}/draft`,{});
      setNotice(`Draft #${out.alert.id} created.`);
      await onRefreshAlerts?.();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }

  const eligible=recordId && result?.mode==='live' && result?.data_state==='CURRENT' &&
    result?.basin?.context_status==='CONFIGURED' && result?.status==='SCREENED' &&
    ['HIGH','CRITICAL'].includes(result?.level);

  const points=useMemo(()=>{
    const villages=result?.basin?.villages||[];
    return villages.length?villages:(selected?[{name:selected.name,lat:selected.lat,lon:selected.lon,monitorOnly:true}]:[]);
  },[result,selected]);

  if(!id)return null;

  return <div className="flood-page flood-command">
    <header className="page-title command-title">
      <div><span className="eyebrow">Live hydrometeorology</span><h1>Flash Flood Monitor</h1><p>{selected?.name}, {selected?.state}</p></div>
      <div className="command-actions">
        {!readOnly&&<button className="btn btn-secondary" onClick={()=>setEditing(v=>!v)} disabled={busy}>Catchment</button>}
        {!readOnly&&<button className="btn btn-primary" disabled={busy} onClick={record}>{busy?'Refreshing…':'Record assessment'}</button>}
      </div>
    </header>

    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {notice&&<div className="notice notice-success" role="status">{notice}</div>}

    {result&&<>
      <section className="flood-kpi-grid">
        <article className={`flood-kpi flood-${statusTone(result.level)}`}><span>Flood screen</span><strong>{result.level}</strong><small>{result.status.replaceAll('_',' ')}</small></article>
        {result.windows.map(w=><article className="flood-kpi" key={w.hours}><span>{w.hours}h rainfall</span><strong>{fmt(w.rainfall_mm)}<em> mm</em></strong><small>{w.screening_threshold_mm==null?'Threshold not set':`threshold ${fmt(w.screening_threshold_mm)} mm`}</small></article>)}
        <article className="flood-kpi"><span>Soil wetness</span><strong>{fmt(result.soil_wetness_proxy_pct)}<em>%</em></strong><small>72h rain {fmt(result.antecedent_rainfall_72h_mm)} mm</small></article>
      </section>

      <section className="flood-source-strip">
        <span className={`source-state source-${String(result.data_state).toLowerCase()}`}>{result.data_state}</span>
        <strong>{result.source||'Weather source unavailable'}</strong>
        <span>{result.valid_time||'No valid time'}</span>
        <span>{result.basin.context_status==='CONFIGURED'?'Catchment configured':'Catchment not configured'}</span>
      </section>

      <div className="flood-dashboard-grid">
        <section className="panel flood-map-card">
          <div className="panel-heading"><div><span className="eyebrow">Area view</span><h2>{result.basin.name}</h2></div></div>
          <div className="flood-map">
            {points.length>0&&<MapContainer key={id} center={[points[0].lat,points[0].lon]} zoom={11} style={{height:'100%',width:'100%'}}>
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors"/>
              {points.map((v,i)=><CircleMarker key={`${v.name}-${i}`} center={[v.lat,v.lon]} radius={v.monitorOnly?7:9}>
                <Popup>{v.name}</Popup>
              </CircleMarker>)}
            </MapContainer>}
          </div>
        </section>

        <section className="panel flood-rain-card">
          <div className="panel-heading"><div><span className="eyebrow">Forecast windows</span><h2>Rainfall vs threshold</h2></div></div>
          <div className="rain-bars">{result.windows.map(w=>{
            const ratio=w.exceedance_ratio==null?0:Math.min(1.6,w.exceedance_ratio);
            return <div className="rain-row" key={w.hours}><div><strong>{w.hours}h</strong><span>{fmt(w.rainfall_mm)} mm</span></div><div className="rain-track"><span style={{width:`${Math.min(100,ratio/1.6*100)}%`}}/></div><b>{w.level}</b></div>;
          })}</div>
          <div className="compact-metrics">
            <div><span>Gauge</span><strong>{result.sensor_used?'LIVE':'—'}</strong></div>
            <div><span>Adjustment</span><strong>{result.threshold_adjustment_factor==null?'—':result.threshold_adjustment_factor.toFixed(2)}</strong></div>
            <div><span>Updated</span><strong>{stamp(result.fetched_at)}</strong></div>
          </div>
          {!readOnly&&<button className="btn btn-danger" disabled={busy||!eligible} onClick={createDraft}>Create draft</button>}
        </section>
      </div>

      {editing&&!readOnly&&form&&<section className="panel flood-config-card">
        <div className="panel-heading"><div><span className="eyebrow">Catchment</span><h2>Local thresholds & gauge</h2></div></div>
        <form onSubmit={saveConfig} className="flood-form">
          <label className="field"><span>Catchment name</span><input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
          <label className="field field-wide"><span>Source / reference</span><input value={form.provenance} onChange={e=>setForm({...form,provenance:e.target.value})}/></label>
          <label className="field"><span>1h threshold (mm)</span><input type="number" min="0.1" step="0.1" value={form.t1} onChange={e=>setForm({...form,t1:e.target.value})}/></label>
          <label className="field"><span>3h threshold (mm)</span><input type="number" min="0.1" step="0.1" value={form.t3} onChange={e=>setForm({...form,t3:e.target.value})}/></label>
          <label className="field"><span>6h threshold (mm)</span><input type="number" min="0.1" step="0.1" value={form.t6} onChange={e=>setForm({...form,t6:e.target.value})}/></label>
          <label className="field"><span>Settlement / ward</span><input value={form.villageName} onChange={e=>setForm({...form,villageName:e.target.value})}/></label>
          <label className="field"><span>Latitude</span><input type="number" step="0.000001" value={form.villageLat} onChange={e=>setForm({...form,villageLat:e.target.value})}/></label>
          <label className="field"><span>Longitude</span><input type="number" step="0.000001" value={form.villageLon} onChange={e=>setForm({...form,villageLon:e.target.value})}/></label>
          <label className="field"><span>Gauge station ID</span><input value={form.stationId} onChange={e=>setForm({...form,stationId:e.target.value})}/></label>
          <label className="field"><span>Danger stage (m)</span><input type="number" min="0.01" step="0.01" value={form.dangerStage} onChange={e=>setForm({...form,dangerStage:e.target.value})}/></label>
          <div className="field field-actions"><button className="btn btn-primary" disabled={busy}>Save</button></div>
        </form>
      </section>}

      <section className="panel flood-history-card">
        <div className="panel-heading"><div><span className="eyebrow">Records</span><h2>Assessment history</h2></div></div>
        {history.length===0?<p className="muted">No recorded assessments.</p>:<div className="flood-history">{history.map(h=><div key={h.id}><strong>#{h.id}</strong><span>{h.assessment.level}</span><span>{stamp(h.assessment.created_at)}</span><a href={downloadUrl(`/api/flood/records/${h.id}`)} target="_blank" rel="noreferrer">JSON</a></div>)}</div>}
      </section>
    </>}
  </div>;
}
