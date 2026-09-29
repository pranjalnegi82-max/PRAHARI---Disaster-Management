import React, {useEffect, useState} from 'react';
import {get} from './api.js';

const fmt=(v,d=0)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);

export default function SatelliteIntelligence({selected, SceneCard}) {
  const [data,setData]=useState(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);

  async function load(){
    if(!selected)return;
    setLoading(true);setError('');
    try{setData(await get('/api/satellite/sentinel2/'+selected.id,{timeout:25000}));}
    catch(e){setError(e.message);setData(null);}
    finally{setLoading(false);}
  }

  useEffect(()=>{load();},[selected?.id]);
  if(!selected)return null;
  const pair=data?.pair;

  return <section className="sat-intel sat-intel-focus">
    <div className="sat-intel-head">
      <div><span className="eyebrow">Sentinel-2</span><h2>{selected.name}, {selected.state}</h2><p>Recent satellite acquisitions</p></div>
      <button className="btn btn-secondary" onClick={load} disabled={loading}>{loading?'Refreshing…':'Refresh'}</button>
    </div>
    {error&&<div className="notice notice-error">{error}</div>}
    <div className="sat-result-stats">
      <div><span>Scenes</span><strong>{data?.scene_count??'—'}</strong></div>
      <div><span>Cloud limit</span><strong>{data?.max_cloud_pct==null?'—':fmt(data.max_cloud_pct)+'%'}</strong></div>
      <div><span>Pair gap</span><strong>{pair?.days_between==null?'—':pair.days_between+' d'}</strong></div>
      <div><span>Source</span><strong>{data?.provider||'—'}</strong></div>
    </div>
    {!loading&&data&&<div className="sat-scene-grid">
      <SceneCard scene={pair?.reference} label="Reference"/>
      <SceneCard scene={pair?.recent} label="Recent"/>
    </div>}
    {!loading&&data?.status==='NO_SCENES'&&<div className="empty"><strong>No suitable scenes</strong></div>}
  </section>;
}
