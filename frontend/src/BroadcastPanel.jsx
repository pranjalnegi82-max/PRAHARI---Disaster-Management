import React, {useEffect, useState} from 'react';
import {get, post} from './api.js';

export default function BroadcastPanel({alerts, locations, onRefresh}) {
  const [data,setData]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false),[preview,setPreview]=useState(null),[details,setDetails]=useState({});
  const [form,setForm]=useState({alert_id:'',area:'ALERT_AREA',expires_in_minutes:60});
  const eligible=alerts.filter(a=>['REVIEWED','ISSUED'].includes(a.lifecycle_status));
  async function load(){setData(await get('/api/broadcasts'));}
  useEffect(()=>{let active=true;const refresh=()=>get('/api/broadcasts').then(d=>{if(active)setData(d);}).catch(e=>{if(active)setError(e.message);});refresh();const timer=setInterval(refresh,10000);return()=>{active=false;clearInterval(timer);};},[]);
  function change(key,value){setForm(f=>({...f,[key]:value}));setPreview(null);setError('');}
  function body(){return {alert_id:Number(form.alert_id),scope:form.area==='ALL'?'ALL_MONITORED':form.area==='ALERT_AREA'?'ALERT_AREA':'SPECIFIC_AREA',target_location_id:['ALL','ALERT_AREA'].includes(form.area)?null:Number(form.area),expires_in_minutes:Number(form.expires_in_minutes)};}
  async function inspect(e){e.preventDefault();setBusy(true);setError('');setNotice('');setPreview(null);try{setPreview(await post('/api/broadcasts/preview',body()));}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function queue(){
    if(!preview?.ready||!preview.recipients)return;
    if(!window.confirm(`Issue this advisory and queue SMS to ${preview.recipients.toLocaleString()} opted-in numbers in ${preview.target_label}? Provider charges apply. Pending messages expire after ${form.expires_in_minutes} minutes.`))return;
    setBusy(true);setError('');
    try{const out=await post('/api/broadcasts',{...body(),expected_recipients:preview.recipients});setNotice(`Broadcast #${out.id}: ${out.queued.toLocaleString()} messages queued. Delivery is confirmed separately.`);setPreview(null);await load();await onRefresh();}catch(e){setError(e.message);setPreview(null);}finally{setBusy(false);}
  }
  async function action(job,action){
    if(['cancel','retry_failed'].includes(action)&&!window.confirm(action==='cancel'?'Cancel messages still waiting? Messages already submitted cannot be recalled.':'Retry confirmed failures only? Additional provider charges may apply. Unknown outcomes will remain on hold.'))return;
    setBusy(true);setError('');try{await post(`/api/broadcasts/${job.id}/control`,{action});await load();setNotice(`Broadcast #${job.id} updated.`);}catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function show(job,after=0){setBusy(true);setError('');try{const out=await get(`/api/broadcasts/${job.id}/items?after=${after}`);setDetails(d=>({...d,[job.id]:out}));}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <section className="broadcast-panel" aria-label="Bulk broadcasts">
    <div className="page-title"><div><h2>Bulk broadcasts</h2><p>Reviewed advisories to opted-in recipients</p></div><span className="badge">{data?.worker_online?'Worker online':'Worker offline'}</span></div>
    {error&&<div className="notice notice-error" role="alert">{error}</div>}
    {notice&&<div className="notice notice-warn" role="status">{notice}</div>}
    {data&&!data.enabled&&<div className="notice notice-warn"><strong>Bulk SMS unavailable</strong></div>}
    <form className="report-form record-card" onSubmit={inspect}>
      <div className="form-row"><label className="field"><span>Reviewed advisory</span><select required disabled={busy} value={form.alert_id} onChange={e=>change('alert_id',e.target.value)}><option value="">Select advisory</option>{eligible.map(a=><option key={a.id} value={a.id}>#{a.id} · {a.location} · {a.level}</option>)}</select></label>
      <label className="field"><span>Broadcast audience</span><select disabled={busy} value={form.area} onChange={e=>change('area',e.target.value)}><option value="ALERT_AREA">Advisory area only</option><option value="ALL">All monitored areas</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}, {l.state}</option>)}</select></label></div>
      <label className="field"><span>Stop submitting after</span><select disabled={busy} value={form.expires_in_minutes} onChange={e=>change('expires_in_minutes',e.target.value)}>{[15,30,60,180,360,1440].map(n=><option key={n} value={n}>{n<60?`${n} minutes`:`${n/60} hour${n>60?'s':''}`}</option>)}</select></label>
      {!eligible.length&&<p>Create an advisory in Advisory alerts and mark it reviewed before broadcasting.</p>}
      <button className="btn btn-secondary" disabled={busy||!form.alert_id}>{busy?'Please wait…':'Preview broadcast'}</button>
    </form>
    {preview&&<div className="record-card"><h3>{preview.recipients.toLocaleString()} eligible numbers</h3><p>{preview.target_label} · Active, opted-in Indian mobile numbers. Duplicate numbers and previous attempts are excluded.</p>
      {preview.minimum_submission_seconds!=null&&<p>Submission needs at least {Math.ceil(preview.minimum_submission_seconds/60).toLocaleString()} minutes at the configured rate. Provider delays and worker capacity can increase this; it is not a delivery-time guarantee.</p>}
      {[...new Set(Object.values(preview.messages))].map((m,i)=><div className="sms-draft-preview" key={i}><strong>Message {i+1}</strong><p style={{whiteSpace:'pre-wrap'}}>{m}</p></div>)}
      
      {!!preview.issues?.length&&<div className="notice notice-warn"><ul>{preview.issues.map(x=><li key={x}>{x}</li>)}</ul></div>}
      <button className="btn btn-danger" disabled={busy||!preview.ready||!preview.recipients} onClick={queue}>Issue & queue broadcast</button>
    </div>}
    <h3>Recent broadcasts</h3>
    <div className="card-list">{data?.jobs?.length?data.jobs.map(j=><article className="record-card" key={j.id}><div className="record-top"><strong>Broadcast #{j.id} · {j.target_label}</strong><span className="badge">{j.status}</span></div><p>Advisory #{j.alert_id} · {j.total.toLocaleString()} numbers · Expires {new Date(j.expires_at*1000).toLocaleString()}</p>
      <div className="notification-summary">{Object.entries(j.counts).map(([s,n])=><span key={s}>{s==='READY'?'WAITING':s} <strong>{n.toLocaleString()}</strong></span>)}</div>{j.note&&<p>{j.note}</p>}
      {!!j.counts.UNKNOWN&&<p className="notice notice-warn">Some submission outcomes are unknown. Check provider logs before creating another advisory for these recipients.</p>}
      <div className="record-actions">{j.status==='RUNNING'&&<button className="btn btn-secondary small" disabled={busy} onClick={()=>action(j,'pause')}>Pause</button>}{j.status==='PAUSED'&&<button className="btn btn-primary small" disabled={busy} onClick={()=>action(j,'resume')}>Resume</button>}{['RUNNING','PAUSED'].includes(j.status)&&<button className="btn btn-secondary small" disabled={busy} onClick={()=>action(j,'cancel')}>Cancel pending</button>}{j.status!=='CANCELED'&&(!!j.counts.FAILED||!!j.counts.UNDELIVERED)&&<button className="btn btn-secondary small" disabled={busy} onClick={()=>action(j,'retry_failed')}>Retry confirmed failures</button>}<button className="btn btn-ghost small" disabled={busy} onClick={()=>show(j)}>Delivery details</button></div>
      {details[j.id]&&<div className="sms-delivery-list">{details[j.id].items.map(i=><div className="sms-delivery-row" key={i.id}><strong>Recipient #{i.recipient_id}</strong><span>{i.status} · {i.attempts} attempts{i.error_code?` · ${i.error_code}`:''}</span>{i.error_message&&<span>{i.error_message}</span>}</div>)}{details[j.id].next_after&&<button className="btn btn-secondary small" disabled={busy} onClick={()=>show(j,details[j.id].next_after)}>Next 100</button>}</div>}
    </article>):<p>No broadcasts queued yet.</p>}</div>
  </section>;
}
