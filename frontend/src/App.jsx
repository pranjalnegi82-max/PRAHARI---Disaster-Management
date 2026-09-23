import React, { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import { API, downloadUrl, get, patch, post, postForm, getOperatorKey, setOperatorKey, getPortalSession, setPortalSession, clearPortalSession, loginPortal } from './api.js';

const RISK = {
  LOW: { label: 'Low', cls: 'risk-low' },
  MODERATE: { label: 'Moderate', cls: 'risk-moderate' },
  HIGH: { label: 'High', cls: 'risk-high' },
  CRITICAL: { label: 'Critical', cls: 'risk-critical' },
  UNKNOWN: { label: 'Unknown', cls: 'risk-unknown' },
};
const NAV = ['Overview', 'Risk Map', 'Reports & Alerts', 'Data & Settings'];
const NAV_ICONS = { 'Overview':'home', 'Risk Map':'map', 'Reports & Alerts':'report', 'Data & Settings':'settings' };
const STATE_LABEL = { CURRENT: 'Current', STALE: 'Cached / stale', MISSING: 'Missing', HISTORICAL_REPLAY: 'Historical replay', BASELINE_DEMO: 'Prototype baseline' };
const RISK_COLOR = { LOW:'#2f855a', MODERATE:'#b7791f', HIGH:'#c05621', CRITICAL:'#c53030', UNKNOWN:'#718096' };

const fmt = (v, digits=1) => v === null || v === undefined || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
const fmtTime = (v) => {
  if (!v) return 'Not available';
  const n = typeof v === 'number' && v < 1e12 ? v * 1000 : v;
  const d = new Date(n);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
};

function Badge({children, tone='neutral'}) { return <span className={`badge badge-${tone}`}>{children}</span>; }
function StateBadge({state}) {
  const tone = state === 'CURRENT' ? 'good' : state === 'STALE' || state === 'HISTORICAL_REPLAY' ? 'warn' : state === 'MISSING' ? 'danger' : 'neutral';
  return <Badge tone={tone}>{STATE_LABEL[state] || state || 'Unknown'}</Badge>;
}
function RiskBadge({level='UNKNOWN'}) {
  const item = RISK[level] || RISK.UNKNOWN;
  return <span className={`risk-pill ${item.cls}`}><span aria-hidden="true">●</span>{item.label}</span>;
}
function Panel({title, subtitle, actions, children, className=''}) {
  return <section className={`panel ${className}`}>
    {(title || actions) && <header className="panel-head"><div>{title && <h2>{title}</h2>}{subtitle && <p>{subtitle}</p>}</div>{actions && <div className="panel-actions">{actions}</div>}</header>}
    {children}
  </section>;
}
function Empty({title, detail}) { return <div className="empty"><strong>{title}</strong>{detail && <span>{detail}</span>}</div>; }
function ErrorBox({message, onRetry}) { return <div className="notice notice-error"><strong>Could not load this section.</strong><span>{message}</span>{onRetry && <button className="btn btn-secondary" onClick={onRetry}>Retry</button>}</div>; }
function Loading() { return <div className="loading" aria-live="polite"><span className="spinner"/>Loading…</div>; }

function Icon({name, size=18}) {
  const common = { width:size, height:size, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', strokeWidth:1.8, strokeLinecap:'round', strokeLinejoin:'round', 'aria-hidden':true };
  const paths = {
    home: <><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10.5V20h13v-9.5"/><path d="M9.5 20v-5.5h5V20"/></>,
    map: <><path d="m3.5 6.5 5-2 7 2 5-2v13l-5 2-7-2-5 2z"/><path d="M8.5 4.5v13M15.5 6.5v13"/></>,
    report: <><path d="M6 3.5h8l4 4V20.5H6z"/><path d="M14 3.5v4h4M9 12h6M9 16h5"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1A7 7 0 0 0 15 6l-.3-2.5h-4L10.4 6A7 7 0 0 0 8 7.1l-2.4-1-2 3.4 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.4-1A7 7 0 0 0 10.4 18l.3 2.5h4L15 18a7 7 0 0 0 1.5-1.1l2.4 1 2-3.4-2-1.5c.1-.3.1-.7.1-1z"/></>,
    search: <><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></>,
    users: <><path d="M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20"/><circle cx="9.5" cy="7" r="3.5"/><path d="M21 20v-1.5a4 4 0 0 0-3-3.7M15.5 3.7a3.5 3.5 0 0 1 0 6.6"/></>,
    shield: <><path d="M12 3 4.5 6v5.5c0 4.6 3 7.4 7.5 9.5 4.5-2.1 7.5-4.9 7.5-9.5V6z"/><path d="m9 12 2 2 4-4"/></>,
    logout: <><path d="M10 5H5v14h5"/><path d="M14 8l4 4-4 4M18 12H9"/></>,
    refresh: <><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 8.2A7 7 0 0 1 18.7 9M5.3 15A7 7 0 0 0 17.9 15.8"/></>,
    alert: <><path d="M12 3 2.8 20h18.4z"/><path d="M12 9v4M12 17h.01"/></>,
    rain: <><path d="M7 15.5h9a4 4 0 0 0 .4-8A5 5 0 0 0 7 8.5a3.5 3.5 0 0 0 0 7z"/><path d="m8 18-1 2M12 18l-1 2M16 18l-1 2"/></>,
    water: <path d="M12 3s5 6.1 5 10a5 5 0 1 1-10 0c0-3.9 5-10 5-10z"/>,
    data: <><ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
    arrow: <><path d="M5 12h14"/><path d="m14 7 5 5-5 5"/></>
  };
  return <svg {...common}>{paths[name] || paths.home}</svg>;
}

function QuickAction({icon,title,detail,onClick,tone='blue'}) {
  return <button className={`quick-card quick-${tone}`} onClick={onClick}><span className="quick-icon"><Icon name={icon} size={20}/></span><span><strong>{title}</strong><small>{detail}</small></span><Icon name="arrow" size={16}/></button>;
}
function StatCard({icon,label,value,unit,detail,tone='blue'}) {
  return <div className={`stat-card stat-${tone}`}><span className="stat-icon"><Icon name={icon} size={20}/></span><div><span>{label}</span><strong>{value}<small>{unit}</small></strong>{detail&&<em>{detail}</em>}</div></div>;
}

function MapFocus({location}) {
  const map = useMap();
  useEffect(() => { if (location) map.flyTo([location.lat, location.lon], Math.max(map.getZoom(), 7), { duration: .7 }); }, [location?.id]);
  return null;
}

function RiskMapView({locations, selected, onSelect, basemap='street', compact=false}) {
  const tiles = basemap === 'satellite'
    ? {url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr:'Tiles © Esri — visual basemap only'}
    : {url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', attr:'© OpenStreetMap contributors'};
  return <div className={`map-wrap ${compact ? 'map-compact' : ''}`}>
    <MapContainer center={[25.6, 92.7]} zoom={5} scrollWheelZoom={!compact} className="map-canvas">
      <TileLayer url={tiles.url} attribution={tiles.attr}/>
      <MapFocus location={selected}/>
      {locations.map(loc => <CircleMarker key={loc.id} center={[loc.lat, loc.lon]} radius={loc.id===selected?.id ? 12 : 9}
          pathOptions={{ color:'#fff', weight:2, fillColor:RISK_COLOR[loc.risk_level] || RISK_COLOR.UNKNOWN, fillOpacity:.92 }}
          eventHandlers={{ click:()=>onSelect(loc) }}>
        <Popup><strong>{loc.name}, {loc.state}</strong><br/><RiskBadge level={loc.risk_level}/><br/>Risk index: {fmt(loc.risk_percent)} / 100<br/><small>{STATE_LABEL[loc.data_state] || loc.data_state}</small></Popup>
      </CircleMarker>)}
    </MapContainer>
    {basemap === 'satellite' && <div className="map-disclaimer">Satellite imagery is visual context only. No image-model inference is performed.</div>}
  </div>;
}


function PortalLogin({onAuthenticated,initialPortal='ADMIN'}) {
  const [portal,setPortal]=useState(initialPortal);
  const [accessKey,setAccessKey]=useState('');
  const [officerCode,setOfficerCode]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');

  async function submit(e){
    e.preventDefault(); setBusy(true); setError('');
    try{
      clearPortalSession();
      const result=await loginPortal({portal,accessKey:accessKey.trim(),officerCode:officerCode.trim()});
      setOperatorKey(accessKey.trim());
      setPortalSession(result.portal,result.actor||null);
      onAuthenticated({portal:result.portal,actor:result.actor||null,role:result.current_role,authRequired:result.auth_required});
    }catch(err){setError(err.message);}finally{setBusy(false);}
  }

  return <div className="login-shell">
    <div className="login-backdrop"/>
    <header className="login-brand"><span className="brand-symbol">P</span><div><strong>PRAHARI</strong><small>Predictive Risk Assessment, Hazard Alert & Response Intelligence</small></div></header>
    <main className="login-card-wrap">
      <section className="login-intro">
        <span className="hero-kicker">SIH26001 · Northeast India</span>
        <h1>One platform.<br/>Two operational portals.</h1>
        <p>Role-separated access keeps command decisions and field enrollment clear, traceable and appropriately restricted.</p>
        <div className="login-safety"><Icon name="shield" size={18}/><span>PRAHARI is advisory decision support. Official warnings remain with authorized agencies.</span></div>
      </section>
      <section className="login-panel">
        <div className="portal-choice" role="tablist" aria-label="Choose PRAHARI portal">
          <button type="button" className={portal==='ADMIN'?'active':''} onClick={()=>{setPortal('ADMIN');setError('')}}><span className="portal-choice-icon"><Icon name="shield" size={22}/></span><strong>Admin Portal</strong><small>Command center, alerts, risk, registry & system oversight</small></button>
          <button type="button" className={portal==='FIELD_OFFICER'?'active':''} onClick={()=>{setPortal('FIELD_OFFICER');setError('')}}><span className="portal-choice-icon"><Icon name="users" size={22}/></span><strong>Field Officer Portal</strong><small>Posting-specific civilian enrollment & field observations</small></button>
        </div>
        <form className="portal-login-form" onSubmit={submit}>
          <div className="portal-login-heading"><h2>{portal==='ADMIN'?'Admin sign in':'Field officer sign in'}</h2><p>{portal==='ADMIN'?'Access the PRAHARI command and alert-management workspace.':'Your assigned posting is enforced by the backend after sign in.'}</p></div>
          {portal==='FIELD_OFFICER'&&<label className="field"><span>Officer code</span><input value={officerCode} onChange={e=>setOfficerCode(e.target.value)} placeholder="e.g. FO-GTK-01" autoComplete="username" required/></label>}
          <label className="field"><span>{portal==='ADMIN'?'Admin access key':'Officer access key'}</span><input type="password" value={accessKey} onChange={e=>setAccessKey(e.target.value)} placeholder={portal==='ADMIN'?'Enter admin key':'Enter field-officer key'} autoComplete="current-password"/></label>
          {portal==='ADMIN'&&<p className="fine login-hint">For local development only, if no admin key is configured and authentication is open, this field may be left blank.</p>}
          {error&&<div className="notice notice-error"><strong>Sign in failed.</strong><span>{error}</span></div>}
          <button className="btn btn-primary portal-submit" disabled={busy}>{busy?'Signing in…':portal==='ADMIN'?'Open Admin Portal':'Open Field Officer Portal'}</button>
        </form>
      </section>
    </main>
    <footer className="login-footer">PRAHARI · Role-separated operational access · SIH26001</footer>
  </div>;
}

function FieldOfficerPortal({session,onLogout}) {
  const [view,setView]=useState('Overview');
  const [profile,setProfile]=useState(session?.actor||null);
  const [auth,setAuth]=useState(null);
  const [locations,setLocations]=useState([]);
  const [reports,setReports]=useState([]);
  const [alerts,setAlerts]=useState([]);
  const [households,setHouseholds]=useState([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [refreshing,setRefreshing]=useState(false);

  async function loadAll(){
    setError(''); setRefreshing(true);
    try{
      const [a,p,l,r,al,h]=await Promise.all([
        get('/api/auth/status'), get('/api/field/profile'), get('/api/live/locations?mode=live'),
        get('/api/reports'), get('/api/alerts'), get('/api/field/households')
      ]);
      if(a.current_role!=='FIELD_OFFICER') throw new Error('This session is not authorized for the Field Officer Portal.');
      setAuth(a); setProfile({...p,posting_location_id:p.location_id}); setLocations(l); setReports(r); setAlerts(al); setHouseholds(h);
    }catch(e){setError(e.message);}finally{setLoading(false);setRefreshing(false);}
  }
  useEffect(()=>{loadAll();},[]);

  const postingId=profile?.location_id||profile?.posting_location_id;
  const selected=locations.find(x=>x.id===postingId)||null;
  const postingReports=selected?reports.filter(r=>String(r.location||'').toLowerCase().includes(String(selected.name).toLowerCase())):[];
  const postingAlerts=selected?alerts.filter(a=>a.location_id===selected.id || String(a.location||'').toLowerCase().includes(String(selected.name).toLowerCase())):[];
  const issuedAlerts=postingAlerts.filter(a=>['ISSUED','ACKNOWLEDGED'].includes(a.lifecycle_status));
  const activeHouseholds=households.filter(h=>h.consent_status==='ACTIVE').length;
  const nav=[['Overview','home'],['Civilian Registry','users'],['Field Reports','report'],['Alerts','alert']];

  return <div className="app-shell field-portal-shell">
    <aside className="sidebar field-sidebar">
      <button className="sidebar-brand" onClick={()=>setView('Overview')}><span className="brand-symbol">P</span><span><strong>PRAHARI</strong><small>Field Operations</small></span></button>
      <div className="field-posting-mini"><Icon name="map" size={16}/><div><span>Assigned posting</span><strong>{profile?.posting||'Loading…'}</strong></div></div>
      <nav className="side-nav" aria-label="Field officer navigation">{nav.map(([item,icon])=><button key={item} className={view===item?'active':''} onClick={()=>setView(item)}><Icon name={icon} size={18}/><span>{item}</span>{item==='Alerts'&&issuedAlerts.length>0&&<b className="nav-count">{issuedAlerts.length}</b>}</button>)}</nav>
      <div className="sidebar-spacer"/>
      <div className="field-officer-card"><span className="user-avatar">F</span><div><strong>{profile?.name||'Field Officer'}</strong><small>{profile?.officer_code||'Posting restricted'}</small></div></div>
      <button className="btn field-logout" onClick={onLogout}><Icon name="logout" size={16}/> Sign out</button>
      <p className="sidebar-note">Field portal · Posting-scoped civilian registration</p>
    </aside>
    <div className="app-frame">
      <header className="topbar field-topbar">
        <div className="field-top-title"><span>Field Officer Portal</span><strong>{profile?.posting||'Assigned posting'}</strong></div>
        <div className="top-actions"><button className="icon-btn" onClick={loadAll} disabled={refreshing} aria-label="Refresh field portal"><Icon name="refresh" size={18}/></button><div className="portal-chip"><Icon name="shield" size={15}/> FIELD OFFICER</div></div>
      </header>
      <main className="workspace">
        {error&&<ErrorBox message={error} onRetry={loadAll}/>} {loading?<Loading/>:<>
          {view==='Overview'&&<FieldOverview selected={selected} profile={profile} activeHouseholds={activeHouseholds} reports={postingReports} alerts={issuedAlerts} onNavigate={setView}/>} 
          {view==='Civilian Registry'&&<div><div className="page-title"><div><h1>Civilian Registry</h1><p>Register opted-in households only for your assigned posting.</p></div><button className="btn btn-secondary" onClick={loadAll}>Refresh registry</button></div><CivilianEnrollmentPane auth={auth||{current_role:'FIELD_OFFICER',actor:profile}} locations={locations} selected={selected}/></div>}
          {view==='Field Reports'&&<div><div className="page-title"><div><h1>Field Reports</h1><p>Submit observations from {profile?.posting||'your posting'}. Report review remains with the command center.</p></div></div><ReportsPane reports={postingReports} selected={selected} onRefresh={loadAll} canManage={false}/></div>}
          {view==='Alerts'&&<FieldAlertsReadOnly alerts={issuedAlerts} posting={profile?.posting}/>} 
        </>}
      </main>
      <footer>Field observations support decision-making; only authorized command staff issue public advisories.</footer>
    </div>
  </div>;
}

function FieldOverview({selected,profile,activeHouseholds,reports,alerts,onNavigate}){
  const level=selected?.risk_level||'UNKNOWN';
  return <div className="field-overview">
    <div className="page-title"><div><span className="eyebrow">Posting-scoped workspace</span><h1>{profile?.posting||'Field posting'}</h1><p>Collect verified contact details and field observations for your assigned area.</p></div><RiskBadge level={level}/></div>
    <div className="field-summary-grid">
      <StatCard icon="users" label="Active SMS civilians" value={activeHouseholds} detail="Explicitly opted-in contacts" tone="blue"/>
      <StatCard icon="report" label="Field reports" value={reports.length} detail="Reports linked to this posting" tone="purple"/>
      <StatCard icon="alert" label="Issued advisories" value={alerts.length} detail="Current/acknowledged alerts" tone={alerts.length?'red':'green'}/>
      <StatCard icon="data" label="Data status" value={STATE_LABEL[selected?.data_state]||'Unknown'} detail={`${fmt(selected?.data_completeness_pct,0)}% complete`} tone={selected?.data_state==='CURRENT'?'green':'amber'}/>
    </div>
    {selected&&<Panel title="Current posting context" subtitle="Read-only risk context from the PRAHARI command pipeline."><div className="field-risk-context"><div><span>Assessment</span><RiskBadge level={level}/></div><div><span>Screening index</span><strong>{selected.risk_percent==null?'—':`${fmt(selected.risk_percent,0)}/100`}</strong></div><div><span>24 h rainfall</span><strong>{fmt(selected.rainfall)} mm</strong></div><div><span>Soil wetness</span><strong>{fmt(selected.soil_moisture)}%</strong></div><div><span>Last source update</span><strong>{fmtTime(selected.updated_at)}</strong></div></div></Panel>}
    <div className="field-action-grid"><button className="field-action-card" onClick={()=>onNavigate('Civilian Registry')}><span><Icon name="users" size={22}/></span><div><strong>Register civilians</strong><small>Add household details, phone number and SMS consent.</small></div><Icon name="arrow" size={17}/></button><button className="field-action-card" onClick={()=>onNavigate('Field Reports')}><span><Icon name="report" size={22}/></span><div><strong>Submit field report</strong><small>Record cracks, slope movement, drainage issues or damage.</small></div><Icon name="arrow" size={17}/></button><button className="field-action-card" onClick={()=>onNavigate('Alerts')}><span><Icon name="alert" size={22}/></span><div><strong>View issued alerts</strong><small>See advisories relevant to your assigned posting.</small></div><Icon name="arrow" size={17}/></button></div>
  </div>;
}

function FieldAlertsReadOnly({alerts,posting}){
  return <div><div className="page-title"><div><h1>Issued Alerts</h1><p>Read-only advisories for {posting||'your assigned posting'}.</p></div></div><Panel title="Current advisories" subtitle="Field officers cannot issue or modify command-center alerts."><div className="card-list">{alerts.length?alerts.map(a=><article className="record-card alert-card" key={a.id}><div className="record-top"><RiskBadge level={a.level}/><Badge tone={a.lifecycle_status==='ISSUED'?'danger':'neutral'}>{a.lifecycle_status}</Badge></div><h3>{a.location}</h3><p>{a.message}</p><div className="record-meta">Issued {fmtTime(a.issued_at||a.created_at)} · Alert #{a.id}</div></article>):<Empty title="No active issued alerts" detail="Command-center advisories for this posting will appear here after issuance."/>}</div></Panel></div>;
}

function PortalApp(){
  const saved=getPortalSession();
  const requestedPortal=window.location.hash.toLowerCase().includes('/field')?'FIELD_OFFICER':'ADMIN';
  const [session,setSession]=useState(()=>saved);
  const [checking,setChecking]=useState(Boolean(saved));
  const [sessionError,setSessionError]=useState('');
  function authenticated(next){window.location.hash=next.portal==='FIELD_OFFICER'?'#/field':'#/admin';setSession(next);}
  function logout(){clearPortalSession();window.location.hash='#/login';setSession(null);setChecking(false);setSessionError('');}
  useEffect(()=>{
    let cancelled=false;
    async function validate(){
      if(!session){setChecking(false);return;}
      setChecking(true);
      try{
        const status=await get('/api/auth/status');
        const valid=session.portal==='FIELD_OFFICER' ? status.current_role==='FIELD_OFFICER' : ['ADMIN','DEV_OPERATOR'].includes(status.current_role);
        if(!valid) throw new Error('The saved session does not match this portal. Please sign in again.');
        if(!cancelled){window.location.hash=session.portal==='FIELD_OFFICER'?'#/field':'#/admin';setSessionError('');setChecking(false);}
      }catch(e){
        if(!cancelled){clearPortalSession();window.location.hash='#/login';setSession(null);setSessionError(e.message);setChecking(false);}
      }
    }
    validate(); return()=>{cancelled=true};
  },[session?.portal]);
  if(checking) return <div className="portal-check"><div className="portal-check-card"><span className="brand-symbol">P</span><Loading/><span>Validating PRAHARI portal session…</span></div></div>;
  if(!session) return <><PortalLogin initialPortal={requestedPortal} onAuthenticated={authenticated}/>{sessionError&&<div className="sr-only" aria-live="polite">{sessionError}</div>}</>;
  if(session.portal==='FIELD_OFFICER') return <FieldOfficerPortal session={session} onLogout={logout}/>;
  return <AdminPortal session={session} onLogout={logout}/>;
}

function AdminPortal({session,onLogout}) {
  const [view, setView] = useState('Overview');
  const [mode, setMode] = useState('live');
  const [locations, setLocations] = useState([]);
  const [selectedId, setSelectedId] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [assessment, setAssessment] = useState(null);
  const [assessmentId, setAssessmentId] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [reports, setReports] = useState([]);
  const [system, setSystem] = useState(null);
  const [sources, setSources] = useState(null);
  const [auth, setAuth] = useState(null);

  const selected = useMemo(() => locations.find(x=>x.id===selectedId) || locations[0], [locations, selectedId]);

  async function loadLocations(force=false) {
    setError(''); setRefreshing(true);
    try {
      const data = await get(`/api/live/locations?mode=${mode}&force=${force}`);
      setLocations(data);
      if (!data.some(x=>x.id===selectedId) && data[0]) setSelectedId(data[0].id);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); setRefreshing(false); }
  }
  async function loadSideData() {
    const tasks = await Promise.allSettled([get('/api/alerts'), get('/api/reports'), get('/api/system/status'), get('/api/data/sources'), get('/api/auth/status')]);
    if (tasks[0].status==='fulfilled') setAlerts(tasks[0].value);
    if (tasks[1].status==='fulfilled') setReports(tasks[1].value);
    if (tasks[2].status==='fulfilled') setSystem(tasks[2].value);
    if (tasks[3].status==='fulfilled') setSources(tasks[3].value);
    if (tasks[4].status==='fulfilled') setAuth(tasks[4].value);
  }
  useEffect(()=>{ loadLocations(); loadSideData(); }, [mode]);
  useEffect(()=>{ setAssessment(null); setAssessmentId(null); }, [selectedId, mode]);

  async function runAssessment() {
    if (!selected) return;
    setRefreshing(true); setError('');
    try {
      const out = await post(`/api/assessments/${selected.id}?mode=${mode}&force=true`, {});
      setAssessment(out.assessment); setAssessmentId(out.assessment_id);
      await loadLocations(true); await loadSideData();
    } catch(e) { setError(e.message); }
    finally { setRefreshing(false); }
  }

  const activeAssessment = assessment || selected;
  const unresolved = alerts.filter(a=>a.lifecycle_status !== 'RESOLVED');
  const attention = unresolved.filter(a=>['DRAFT','REVIEWED','ISSUED'].includes(a.lifecycle_status)).length;

  return <div className="app-shell">
    <aside className="sidebar">
      <button className="sidebar-brand" onClick={()=>setView('Overview')} aria-label="PRAHARI overview">
        <span className="brand-symbol">P</span>
        <span><strong>PRAHARI</strong><small>Predict · Prepare · Protect</small></span>
      </button>
      <nav className="side-nav" aria-label="Main navigation">
        {NAV.map(item=><button key={item} className={view===item?'active':''} onClick={()=>setView(item)}><Icon name={NAV_ICONS[item]} size={18}/><span>{item}</span>{item==='Reports & Alerts' && attention>0 && <b className="nav-count">{attention}</b>}</button>)}
      </nav>
      <div className="sidebar-spacer"/>
      <div className="sidebar-status">
        <span className={`status-dot ${selected?.data_state==='CURRENT'?'online':'degraded'}`}/>
        <div><strong>{selected?.data_state==='CURRENT'?'Live context':'Data status'}</strong><small>{STATE_LABEL[selected?.data_state] || 'Waiting for source'}</small></div>
      </div>
      <p className="sidebar-note">Decision-support prototype · SIH26001</p>
    </aside>

    <div className="app-frame">
      <header className="topbar">
        <LocationSelector locations={locations} selectedId={selectedId} onSelect={setSelectedId} compact/>
        <div className="top-actions">
          <div className="mode-toggle compact" role="group" aria-label="Data mode">
            <button className={mode==='live'?'active':''} onClick={()=>setMode('live')}>Live</button>
            <button className={mode==='replay'?'active':''} onClick={()=>setMode('replay')}>Replay</button>
          </div>
          <button className="icon-btn" onClick={()=>loadLocations(true)} disabled={refreshing} title="Refresh data" aria-label="Refresh data"><Icon name="refresh" size={18}/></button>
          <button className="icon-btn" onClick={()=>setView('Reports & Alerts')} title="Reports and alerts" aria-label="Reports and alerts"><Icon name="bell" size={18}/>{attention>0&&<span className="icon-count">{attention}</span>}</button>
          <div className="portal-identity" title="Admin Command Center"><span className="user-avatar">A</span><div><strong>Admin</strong><small>Command Center</small></div></div>
          <button className="btn btn-ghost small portal-logout" onClick={onLogout}><Icon name="logout" size={16}/> Logout</button>
        </div>
      </header>

      <main className="workspace">
        {error && <ErrorBox message={error} onRetry={()=>loadLocations(true)}/>} 
        {loading ? <Loading/> : <>
          {view==='Overview' && <Overview location={activeAssessment} locations={locations} alerts={unresolved} reports={reports} assessmentId={assessmentId} onAssess={runAssessment} onNavigate={setView} refreshing={refreshing} mode={mode}/>} 
          {view==='Risk Map' && <RiskMapPage locations={locations} selected={selected} onSelect={loc=>setSelectedId(loc.id)} onAssess={runAssessment} assessment={activeAssessment}/>} 
          {view==='Reports & Alerts' && <ReportsAlerts reports={reports} alerts={alerts} selected={selected} locations={locations} auth={auth} onRefresh={loadSideData}/>} 
          {view==='Data & Settings' && <DataSettings system={system} sources={sources} auth={auth} selected={selected} locations={locations} session={session} onLogout={onLogout} onAuthRefresh={loadSideData}/>} 
        </>}
      </main>
      <footer>Advisory decision support only · Public warnings and evacuation orders remain with authorized agencies.</footer>
    </div>
  </div>;
}

function LocationSelector({locations, selectedId, onSelect, compact=false}) {
  const selected = locations.find(x=>x.id===selectedId);
  const [query,setQuery]=useState(selected ? `${selected.name}, ${selected.state}` : '');
  useEffect(()=>{ if(selected) setQuery(`${selected.name}, ${selected.state}`); },[selectedId, locations.length]);
  const matches=locations.filter(x=>`${x.name} ${x.state}`.toLowerCase().includes(query.toLowerCase().trim())).slice(0,8);
  return <div className={`location-search ${compact?'location-search-compact':''}`}>
    <label className="field location-select"><span className={compact?'sr-only':''}>Search / select area</span><span className="search-icon"><Icon name="search" size={17}/></span><input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search location in Northeast India…" aria-controls="location-results"/></label>
    {query && selected && query !== `${selected.name}, ${selected.state}` && <div className="location-results" id="location-results">{matches.length?matches.map(x=><button key={x.id} onClick={()=>{onSelect(x.id);setQuery(`${x.name}, ${x.state}`)}}><strong>{x.name}</strong><span>{x.state}</span></button>):<span>No configured area matches. General geocoding is not connected yet.</span>}</div>}
  </div>;
}

function Overview({location, locations, alerts, reports, assessmentId, onAssess, onNavigate, refreshing, mode}) {
  if (!location) return <Empty title="No area available"/>;
  const factors = location.factors || [];
  const stale = location.data_state === 'STALE';
  const missing = location.assessment_status === 'INSUFFICIENT_DATA' || location.data_state === 'MISSING';
  const newReports = reports.filter(r=>r.status==='NEW').length;
  const riskLevel = location.risk_level || 'UNKNOWN';
  const dataDetail = mode==='replay' ? 'Historical replay' : (location.data_state==='CURRENT' ? 'Live / latest' : STATE_LABEL[location.data_state] || 'Unknown');

  return <div className="overview-page">
    <section className="overview-hero" aria-labelledby="overview-title">
      <div className="hero-overlay"/>
      <div className="hero-copy">
        <span className="hero-kicker">Northeast India · Landslide intelligence</span>
        <h1 id="overview-title">Stay Ahead.<br/>Stay Safer.</h1>
        <p>Traceable landslide risk monitoring, field reporting and advisory support—without hiding missing or stale data.</p>
        <div className="hero-actions">
          <button className="btn btn-hero" onClick={()=>onNavigate('Risk Map')}><Icon name="map" size={18}/> View risk map</button>
          <button className="btn btn-hero-secondary" onClick={()=>onNavigate('Reports & Alerts')}><Icon name="report" size={18}/> Report incident</button>
        </div>
      </div>
      <div className="hero-risk-card">
        <div className="hero-risk-top"><span>Current assessment</span><StateBadge state={location.data_state}/></div>
        <RiskBadge level={riskLevel}/>
        <h2>{location.name}, {location.state}</h2>
        <div className="hero-risk-index"><strong>{location.risk_percent == null ? '—' : fmt(location.risk_percent,0)}</strong><span>/100<br/><small>screening index</small></span></div>
        <div className="hero-mini-metrics"><div><Icon name="rain"/><span><b>{fmt(location.rainfall)} mm</b>24 h rain</span></div><div><Icon name="water"/><span><b>{fmt(location.soil_moisture)}%</b>soil wetness</span></div></div>
        <button className="text-link hero-link" onClick={()=>onNavigate('Risk Map')}>View location details <Icon name="arrow" size={15}/></button>
      </div>
    </section>

    <section className="summary-strip" aria-label="Current observation summary">
      <StatCard icon="alert" label="Current risk" value={RISK[riskLevel]?.label || 'Unknown'} unit="" detail={location.risk_percent == null ? 'Insufficient data' : `${fmt(location.risk_percent,0)}/100 screening index`} tone={riskLevel==='LOW'?'green':riskLevel==='MODERATE'?'amber':riskLevel==='UNKNOWN'?'blue':'red'}/>
      <StatCard icon="rain" label="Rainfall · 24 h" value={fmt(location.rainfall)} unit=" mm" detail={`72 h: ${fmt(location.antecedent_rainfall_72h)} mm`} tone="blue"/>
      <StatCard icon="water" label="Soil wetness" value={fmt(location.soil_moisture)} unit="%" detail={`Slope context: ${fmt(location.slope)}°`} tone="teal"/>
      <StatCard icon="data" label="Data status" value={dataDetail} unit="" detail={`${fmt(location.data_completeness_pct,0)}% complete`} tone={location.data_state==='CURRENT'?'green':'amber'}/>
    </section>

    {stale && <div className="notice notice-warn"><strong>Cached observations in use.</strong><span>Review source timestamps before operational decisions.</span></div>}
    {missing && <div className="notice notice-error"><strong>Assessment incomplete.</strong><span>Missing data is not converted into low risk. Missing: {(location.missing_inputs||[]).join(', ') || 'required weather fields'}.</span></div>}

    <section className="quick-section">
      <div className="section-heading"><div><span className="eyebrow">Quick access</span><h2>What do you need to do?</h2></div><span className="section-meta">{alerts.length} open alerts · {newReports} new reports</span></div>
      <div className="quick-grid">
        <QuickAction icon="map" title="Risk Map" detail="Explore areas and risk context" onClick={()=>onNavigate('Risk Map')} tone="blue"/>
        <QuickAction icon="report" title="Citizen Reports" detail="Submit or review field evidence" onClick={()=>onNavigate('Reports & Alerts')} tone="purple"/>
        <QuickAction icon="bell" title="Alerts" detail="Review advisory lifecycle" onClick={()=>onNavigate('Reports & Alerts')} tone="red"/>
        <QuickAction icon="data" title="Data & Settings" detail="Sources, freshness and system health" onClick={()=>onNavigate('Data & Settings')} tone="teal"/>
      </div>
    </section>

    <div className="overview-detail-grid">
      <Panel title="Assessment details" subtitle="Why this level was assigned and how complete the evidence is."
        actions={<button className="btn btn-primary" onClick={onAssess} disabled={refreshing}>{refreshing?'Assessing…':'Run & record assessment'}</button>}>
        <div className="assessment-compact">
          <div className="assessment-score"><RiskBadge level={riskLevel}/><strong>{location.risk_percent == null ? '—' : `${fmt(location.risk_percent,0)}/100`}</strong><span>uncalibrated screening index</span></div>
          <div className="assessment-meta">
            <Meta label="Completeness" value={`${fmt(location.data_completeness_pct,0)}%`}/>
            <Meta label="Valid time" value={fmtTime(location.weather_valid_time || location.weather_updated_at)}/>
            <Meta label="Forecast rain · 24 h" value={`${fmt(location.rain_forecast_24h_mm)} mm`}/>
            <Meta label="Assessment version" value={location.assessment_version || 'Not recorded yet'}/>
          </div>
        </div>
        <div className="factor-list"><h3>Contributing factors</h3>{factors.length ? factors.map((f,i)=><div className="factor" key={i}><span className="factor-dot"/> <span>{typeof f==='string' ? f : (f.label || JSON.stringify(f))}</span></div>) : <p className="muted">No contributing factors available until required observations are present.</p>}</div>
        {assessmentId && <div className="button-row"><a className="btn btn-secondary" href={downloadUrl(`/api/assessment-records/${assessmentId}/export?format=json`)}>Export JSON</a><a className="btn btn-secondary" href={downloadUrl(`/api/assessment-records/${assessmentId}/export?format=csv`)}>Export CSV</a></div>}
      </Panel>

      <Panel title="Map preview" subtitle="Geographic context for the selected area." actions={<button className="btn btn-secondary" onClick={()=>onNavigate('Risk Map')}>Open full map</button>}>
        <RiskMapView locations={locations} selected={location} onSelect={()=>{}} compact/>
      </Panel>
    </div>

    <details className="disclosure overview-disclosure"><summary>Technical details & limitations</summary><div className="disclosure-body">
      <p><strong>Terrain context:</strong> bundled prototype point attributes until authoritative DEM-derived features are integrated.</p>
      {(location.assessment_limitations||[]).map((x,i)=><p key={i}>{x}</p>)}
      {location.experimental_model && <p><strong>Experimental ensemble:</strong> visible for research comparison only; synthetic/bootstrap training and not field-calibrated.</p>}
    </div></details>
  </div>;
}

function Meta({label,value}) { return <div className="meta"><span>{label}</span><strong>{value}</strong></div>; }
function Metric({label,value,unit}) { return <div className="metric"><span>{label}</span><strong>{value}<small>{unit}</small></strong></div>; }
function Attention({count,label,action}) { return <button className="attention" onClick={action}><span className={count?'count count-hot':'count'}>{count}</span><span>{label}</span><span aria-hidden="true">→</span></button>; }

function RiskMapPage({locations,selected,onSelect,onAssess,assessment}) {
  const [basemap,setBasemap]=useState('street');
  const [history,setHistory]=useState([]);
  const [forecast,setForecast]=useState(null);
  const [extraError,setExtraError]=useState('');
  useEffect(()=>{ if (!selected) return; setExtraError(''); Promise.allSettled([get(`/api/assessments/${selected.id}/history`),get(`/api/forecast-risk/${selected.id}`)]).then(([h,f])=>{if(h.status==='fulfilled')setHistory(h.value);if(f.status==='fulfilled')setForecast(f.value);}); },[selected?.id]);
  return <div className="risk-map-page">
    <div className="map-toolbar"><div><h1>Risk Map</h1><p>Map-led situational awareness with explicit data state.</p></div><div className="segmented"><button className={basemap==='street'?'active':''} onClick={()=>setBasemap('street')}>Street</button><button className={basemap==='satellite'?'active':''} onClick={()=>setBasemap('satellite')}>Satellite · visual only</button></div></div>
    <div className="map-layout">
      <RiskMapView locations={locations} selected={selected} onSelect={onSelect} basemap={basemap}/>
      <aside className="map-detail">
        <Panel title={selected?`${selected.name}, ${selected.state}`:'Select an area'} actions={selected&&<button className="btn btn-primary" onClick={onAssess}>Record assessment</button>}>
          {selected && <><div className="detail-risk"><RiskBadge level={assessment?.risk_level || selected.risk_level}/><strong>{assessment?.risk_percent == null ? 'Index unavailable' : `${fmt(assessment.risk_percent,0)} / 100`}</strong></div>
          <StateBadge state={assessment?.data_state || selected.data_state}/>
          <dl className="kv"><dt>24 h rain</dt><dd>{fmt(assessment?.rainfall ?? selected.rainfall)} mm</dd><dt>72 h antecedent rain</dt><dd>{fmt(assessment?.antecedent_rainfall_72h ?? selected.antecedent_rainfall_72h)} mm</dd><dt>Soil wetness</dt><dd>{fmt(assessment?.soil_moisture ?? selected.soil_moisture)}%</dd><dt>Slope context</dt><dd>{fmt(selected.slope)}° <Badge>prototype</Badge></dd></dl></>}
        </Panel>
        <details className="disclosure" open><summary>Assessment history</summary><div className="disclosure-body history-list">{history.length?history.slice(0,8).map(h=><div key={h.id}><RiskBadge level={h.risk_level}/><span>{h.mode}</span><span>{fmtTime(h.created_at)}</span></div>):<p className="muted">No recorded assessments yet.</p>}</div></details>
        <details className="disclosure"><summary>Forecast guidance</summary><div className="disclosure-body">{forecast?.available ? <div className="forecast-list">{forecast.points.map(p=><div key={p.horizon}><strong>{p.horizon}</strong><RiskBadge level={p.risk_level}/><span>{p.risk_index ?? '—'}/100</span></div>)}</div>:<p className="muted">{forecast?.note || 'Forecast guidance unavailable.'}</p>}<p className="fine">Screening trajectory only; not a calibrated probability forecast.</p></div></details>
      </aside>
    </div>
  </div>;
}

function ReportsAlerts({reports,alerts,selected,locations,auth,onRefresh}) {
  const [tab,setTab]=useState('reports');
  const canEnroll=['FIELD_OFFICER','ADMIN','DEV_OPERATOR'].includes(auth?.current_role);
  return <div><div className="page-title"><div><h1>Reports & Alerts</h1><p>Field evidence, civilian enrollment and advisory delivery remain traceable and role-controlled.</p></div><button className="btn btn-secondary" onClick={onRefresh}>Refresh</button></div>
    <div className="subnav"><button className={tab==='reports'?'active':''} onClick={()=>setTab('reports')}>Citizen reports <Badge>{reports.length}</Badge></button>{canEnroll&&<button className={tab==='enrollment'?'active':''} onClick={()=>setTab('enrollment')}>Civilian enrollment</button>}<button className={tab==='alerts'?'active':''} onClick={()=>setTab('alerts')}>Advisory alerts <Badge>{alerts.length}</Badge></button></div>
    {tab==='reports'?<ReportsPane reports={reports} selected={selected} onRefresh={onRefresh}/>:tab==='enrollment'?<CivilianEnrollmentPane auth={auth} locations={locations} selected={selected}/>:<AlertsPane alerts={alerts} auth={auth} locations={locations} onRefresh={onRefresh}/>} 
  </div>;
}

function ReportsPane({reports,selected,onRefresh,canManage=true}) {
  const [form,setForm]=useState({reporter:'',phone:'',location:selected?`${selected.name}, ${selected.state}`:'',lat:selected?.lat||'',lon:selected?.lon||'',hazard_type:'Slope movement',severity:'MODERATE',description:''});
  const [image,setImage]=useState(null); const [busy,setBusy]=useState(false); const [msg,setMsg]=useState(''); const [locationMethod,setLocationMethod]=useState('manual');
  useEffect(()=>{ if(selected) setForm(f=>({...f,location:`${selected.name}, ${selected.state}`,lat:selected.lat,lon:selected.lon})); },[selected?.id]);
  const set=(k,v)=>setForm(f=>({...f,[k]:v}));
  function gps(){ if(!navigator.geolocation){setMsg('Geolocation is not supported. Enter coordinates manually.');return;} navigator.geolocation.getCurrentPosition(p=>{set('lat',p.coords.latitude.toFixed(6));set('lon',p.coords.longitude.toFixed(6));setLocationMethod('gps');setMsg('GPS location captured.');},()=>setMsg('Location permission denied. Enter coordinates manually.')); }
  async function submit(e){e.preventDefault();setBusy(true);setMsg('');try{const fd=new FormData();Object.entries(form).forEach(([k,v])=>fd.append(k,v));fd.append('location_method',locationMethod);if(image)fd.append('image',image);await postForm('/api/reports',fd);setMsg('Report submitted for operator review.');set('description','');setImage(null);await onRefresh();}catch(err){setMsg(err.message);}finally{setBusy(false);}}
  async function update(id,status){try{await patch(`/api/reports/${id}/status?status=${status}`,{});await onRefresh();}catch(e){setMsg(e.message);}}
  return <div className="split-layout"><Panel title="Submit field observation" subtitle="Citizen reports are evidence, not automatic public warnings."><form onSubmit={submit} className="report-form">
    <div className="form-row"><label className="field"><span>Name</span><input value={form.reporter} onChange={e=>set('reporter',e.target.value)} required maxLength={120}/></label><label className="field"><span>Phone · optional</span><input value={form.phone} onChange={e=>set('phone',e.target.value)} maxLength={40}/></label></div>
    <label className="field"><span>Location</span><input value={form.location} onChange={e=>set('location',e.target.value)} required/></label>
    <div className="form-row"><label className="field"><span>Latitude</span><input type="number" step="any" value={form.lat} onChange={e=>{set('lat',e.target.value);setLocationMethod('manual')}} required/></label><label className="field"><span>Longitude</span><input type="number" step="any" value={form.lon} onChange={e=>{set('lon',e.target.value);setLocationMethod('manual')}} required/></label></div>
    <button type="button" className="btn btn-secondary small" onClick={gps}>Use my GPS</button>
    <div className="form-row"><label className="field"><span>Hazard type</span><select value={form.hazard_type} onChange={e=>set('hazard_type',e.target.value)}>{['Slope movement','Surface crack','Road crack','Debris / rockfall','Water seepage','Blocked drainage','Flooding','Structural damage','Other'].map(x=><option key={x}>{x}</option>)}</select></label><label className="field"><span>Observed severity</span><select value={form.severity} onChange={e=>set('severity',e.target.value)}>{['LOW','MODERATE','HIGH','CRITICAL'].map(x=><option key={x}>{x}</option>)}</select></label></div>
    <label className="field"><span>Description</span><textarea minLength={10} value={form.description} onChange={e=>set('description',e.target.value)} required placeholder="Describe what you observed, extent, change over time, and anything at risk."/></label>
    <label className="field"><span>Photo · optional, JPEG/PNG/WEBP ≤ 2 MB</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setImage(e.target.files?.[0]||null)}/></label>
    <div className="button-row"><button className="btn btn-primary" disabled={busy}>{busy?'Submitting…':'Submit report'}</button>{msg&&<span className="form-message">{msg}</span>}</div>
  </form></Panel>
  <Panel title="Recent reports" subtitle="Operators can verify, dispatch, and resolve reports."><div className="card-list">{reports.length?reports.map(r=><article className="record-card" key={r.id}><div className="record-top"><strong>{r.hazard_type}</strong><Badge tone={r.status==='NEW'?'warn':'neutral'}>{r.status}</Badge></div><p>{r.location}</p><p>{r.description}</p><div className="record-meta">{r.severity} · {fmtTime(r.created_at)}</div>{canManage&&<div className="record-actions">{r.status==='NEW'&&<button className="btn btn-secondary small" onClick={()=>update(r.id,'VERIFIED')}>Verify</button>}{r.status==='VERIFIED'&&<button className="btn btn-secondary small" onClick={()=>update(r.id,'DISPATCHED')}>Mark dispatched</button>}{r.status!=='RESOLVED'&&<button className="btn btn-ghost small" onClick={()=>update(r.id,'RESOLVED')}>Resolve</button>}</div>}</article>):<Empty title="No citizen reports" detail="Submitted observations will appear here."/>}</div></Panel></div>;
}

function CivilianEnrollmentPane({auth,locations,selected}) {
  const role=auth?.current_role || 'PUBLIC';
  const isField=role==='FIELD_OFFICER';
  const isAdmin=['ADMIN','DEV_OPERATOR'].includes(role);
  const postingId=auth?.actor?.posting_location_id || null;
  const defaultLoc=postingId || selected?.id || locations[0]?.id || '';
  const [profile,setProfile]=useState(null);
  const [records,setRecords]=useState([]);
  const [filterLocation,setFilterLocation]=useState(defaultLoc);
  const [form,setForm]=useState({name:'',phone_e164:'+91',household_label:'',village:'',household_size:'',language:'en',location_id:defaultLoc,consent_confirmed:false});
  const [busy,setBusy]=useState(false); const [message,setMessage]=useState(''); const [error,setError]=useState('');

  async function load(){setError('');try{const prof=await get('/api/field/profile');setProfile(prof);const loc=isField?(prof.location_id||postingId):filterLocation;const q=loc?`?location_id=${loc}`:'';const rows=await get(`/api/field/households${q}`);setRecords(rows);}catch(e){setError(e.message);}}
  useEffect(()=>{load();},[role,filterLocation]);
  useEffect(()=>{if(postingId){setFilterLocation(postingId);setForm(f=>({...f,location_id:postingId}));}},[postingId]);
  async function submit(e){e.preventDefault();setBusy(true);setMessage('');setError('');try{const payload={...form,household_size:form.household_size?Number(form.household_size):null,location_id:isField?undefined:Number(form.location_id)};await post('/api/field/households',payload);setMessage(`Civilian registered for ${profile?.posting || locations.find(x=>x.id===Number(form.location_id))?.name || 'selected area'}.`);setForm(f=>({...f,name:'',phone_e164:'+91',household_label:'',village:'',household_size:'',consent_confirmed:false}));await load();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function revoke(id){if(!window.confirm('Revoke this civilian from future PRAHARI SMS alerts?'))return;setError('');try{await patch(`/api/field/households/${id}`,{consent_status:'REVOKED'});await load();}catch(e){setError(e.message);}}
  if(!isField&&!isAdmin) return <Panel title="Civilian enrollment"><div className="notice notice-warn">A FIELD_OFFICER or ADMIN key is required for this workflow.</div></Panel>;
  const postingLabel=isField?(profile?.posting||auth?.actor?.posting||'Assigned posting'):'Administrator view';
  return <div className="split-layout enrollment-layout">
    <Panel title="Register household / civilian" subtitle={isField?`Posting locked to ${postingLabel}. You cannot enroll civilians outside your assigned alert area.`:'Admin-assisted registration. Select the alert area explicitly.'}>
      {error&&<div className="notice notice-error">{error}</div>}{message&&<div className="notice notice-warn">{message}</div>}
      <div className="posting-banner"><span>Role</span><strong>{role.replace('_',' ')}</strong><span>Posting</span><strong>{postingLabel}</strong></div>
      <form className="recipient-form" onSubmit={submit}>
        <div className="form-row"><label className="field"><span>Name / household head</span><input required maxLength={120} value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}/></label><label className="field"><span>Phone number</span><input required placeholder="+919876543210" value={form.phone_e164} onChange={e=>setForm(f=>({...f,phone_e164:e.target.value}))}/></label></div>
        <div className="form-row"><label className="field"><span>Household / landmark · optional</span><input maxLength={120} value={form.household_label} onChange={e=>setForm(f=>({...f,household_label:e.target.value}))} placeholder="House 12, Upper Ward"/></label><label className="field"><span>Village / locality · optional</span><input maxLength={120} value={form.village} onChange={e=>setForm(f=>({...f,village:e.target.value}))}/></label></div>
        <div className="form-row"><label className="field"><span>Household size · optional</span><input type="number" min="1" max="50" value={form.household_size} onChange={e=>setForm(f=>({...f,household_size:e.target.value}))}/></label><label className="field"><span>Language</span><select value={form.language} onChange={e=>setForm(f=>({...f,language:e.target.value}))}><option value="en">English</option><option value="hi">Hindi</option><option value="as">Assamese</option></select></label></div>
        {!isField&&<label className="field"><span>Alert area</span><select required value={form.location_id} onChange={e=>setForm(f=>({...f,location_id:e.target.value}))}>{locations.map(x=><option key={x.id} value={x.id}>{x.name}, {x.state}</option>)}</select></label>}
        {isField&&<div className="locked-area"><span>Alert area</span><strong>{postingLabel}</strong><small>Automatically assigned from your field posting.</small></div>}
        <label className="consent-check"><input type="checkbox" required checked={form.consent_confirmed} onChange={e=>setForm(f=>({...f,consent_confirmed:e.target.checked}))}/><span>I confirm this civilian explicitly opted in to PRAHARI SMS advisories and understands how to request removal.</span></label>
        <button className="btn btn-primary" disabled={busy}>{busy?'Registering…':'Register civilian'}</button>
      </form>
    </Panel>
    <Panel title="Civilian registry" subtitle={isField?'Only civilians in your assigned posting are visible here.':'Filter the registry by monitored alert area.'} actions={!isField&&<select className="compact-select" value={filterLocation} onChange={e=>setFilterLocation(e.target.value)}><option value="">All monitored areas</option>{locations.map(x=><option key={x.id} value={x.id}>{x.name}, {x.state}</option>)}</select>}>
      <div className="registry-summary"><strong>{records.filter(r=>r.consent_status==='ACTIVE').length}</strong><span>active SMS recipients</span><strong>{records.length}</strong><span>records shown</span></div>
      <div className="recipient-list">{records.length?records.map(r=>{const loc=locations.find(x=>x.id===r.location_id);return <div className={`recipient-row ${r.consent_status!=='ACTIVE'?'recipient-revoked':''}`} key={r.id}><div><strong>{r.name}</strong><span>{r.phone_e164}</span><small>{loc?`${loc.name}, ${loc.state}`:'Unassigned'}{r.village?` · ${r.village}`:''}{r.household_size?` · ${r.household_size} people`:''}</small><small>Registered by {r.registered_by_officer||r.registered_by_role||'Admin'}{r.registered_by_officer_code?` (${r.registered_by_officer_code})`:''}</small></div><div className="recipient-channels"><Badge>SMS</Badge><Badge tone={r.consent_status==='ACTIVE'?'good':'neutral'}>{r.consent_status}</Badge></div>{r.consent_status==='ACTIVE'&&<button className="btn btn-ghost small" onClick={()=>revoke(r.id)}>Revoke</button>}</div>}):<Empty title="No civilians registered" detail="Use the enrollment form to add opted-in households for this posting."/>}</div>
    </Panel>
  </div>;
}

function AlertsPane({alerts,auth,locations,onRefresh}) {
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(null);
  const role=auth?.current_role || 'PUBLIC';
  const isAdmin=['ADMIN','DEV_OPERATOR'].includes(role);
  const [targetByAlert,setTargetByAlert]=useState({});
  async function transition(a,to){setError('');setBusy(`${a.id}-${to}`);try{await patch(`/api/alerts/${a.id}/transition`,{to_status:to,note:`Transitioned from PRAHARI command center`});await onRefresh();}catch(e){setError(e.message);}finally{setBusy(null);}}
  async function issueAndNotify(a){
    setError('');setBusy(`${a.id}-notify`);
    try{
      const target=targetByAlert[a.id] ?? String(a.location_id ?? 'ALL');
      const scope=target==='ALL'?'ALL_MONITORED':Number(target)===Number(a.location_id)?'ALERT_AREA':'SPECIFIC_AREA';
      const targetId=target==='ALL'?null:Number(target);
      const query=`?scope=${scope}${scope==='SPECIFIC_AREA'?`&target_location_id=${targetId}`:''}`;
      const preview=await get(`/api/alerts/${a.id}/notification-preview${query}`);
      if(!(preview.provider?.sms?.ready && preview.sms_recipients>0)) throw new Error('SMS is not provider-ready or there are no opted-in civilians in the selected alert area.');
      const ok=window.confirm(`Issue this advisory and send SMS to ${preview.target_label}?\n\nRecipients: ${preview.sms_recipients}\nAlert source: ${a.location}\n\nOnly provider delivery receipts will be treated as delivered.`);
      if(!ok) return;
      const out=await post(`/api/alerts/${a.id}/issue-and-notify`,{note:`Admin initiated SMS broadcast to ${preview.target_label}`,scope,target_location_id:targetId});
      setError(out.failed ? `${out.accepted_or_queued} accepted/queued for ${out.target_label}; ${out.failed} failed.` : `${out.accepted_or_queued} SMS request(s) accepted/queued for ${out.target_label}. Delivery confirmation updates separately.`);
      await onRefresh();
    }catch(e){setError(e.message);}finally{setBusy(null);}
  }
  async function refreshDelivery(a){setError('');setBusy(`${a.id}-refresh`);try{await post(`/api/alerts/${a.id}/deliveries/refresh`,{});await onRefresh();}catch(e){setError(e.message);}finally{setBusy(null);}}
  function nextActions(a){const s=a.lifecycle_status||'DRAFT'; if(s==='DRAFT')return['REVIEWED','RESOLVED'];if(s==='REVIEWED')return isAdmin?['RESOLVED']:['ISSUED','RESOLVED'];if(s==='ISSUED')return['ACKNOWLEDGED','RESOLVED'];if(s==='ACKNOWLEDGED')return['RESOLVED'];return[];}
  return <Panel title="Advisory lifecycle" subtitle="DRAFT → REVIEWED → ISSUED → ACKNOWLEDGED → RESOLVED. External SMS delivery requires an explicit admin action.">
    {error&&<div className={error.includes('failed')||error.includes('No provider')?'notice notice-error':'notice notice-warn'}>{error}</div>}
    <div className="card-list">{alerts.length?alerts.map(a=><article className="record-card alert-card" key={a.id}>
      <div className="record-top"><RiskBadge level={a.level}/><Badge tone={a.lifecycle_status==='ISSUED'?'danger':a.lifecycle_status==='DRAFT'?'warn':'neutral'}>{a.lifecycle_status}</Badge></div>
      <h3>{a.location}</h3><p>{a.message}</p><div className="record-meta">Created {fmtTime(a.created_at)} · Source: {a.source}</div>
      <div className="record-actions">
        {nextActions(a).map(to=><button disabled={!!busy} key={to} className={to==='ISSUED'?'btn btn-primary small':'btn btn-secondary small'} onClick={()=>transition(a,to)}>{to==='REVIEWED'?'Mark reviewed':to==='ISSUED'?'Issue internally':to==='ACKNOWLEDGED'?'Acknowledge':to==='RESOLVED'?'Resolve':to}</button>)}
        {isAdmin && ['REVIEWED','ISSUED'].includes(a.lifecycle_status) && <label className="alert-target"><span>SMS area</span><select value={targetByAlert[a.id] ?? String(a.location_id ?? 'ALL')} onChange={e=>setTargetByAlert(m=>({...m,[a.id]:e.target.value}))}><option value="ALL">All monitored areas</option>{locations.map(x=><option key={x.id} value={x.id}>{x.name}, {x.state}{x.id===a.location_id?' · alert area':''}</option>)}</select></label>}
        {isAdmin && ['REVIEWED','ISSUED'].includes(a.lifecycle_status) && <button disabled={!!busy} className="btn btn-danger small" onClick={()=>issueAndNotify(a)}>{busy===`${a.id}-notify`?'Sending…':a.lifecycle_status==='REVIEWED'?'Issue & send SMS':'Send / retry SMS'}</button>}
        {isAdmin && a.lifecycle_status==='ISSUED' && <button disabled={!!busy} className="btn btn-ghost small" onClick={()=>refreshDelivery(a)}>Refresh delivery status</button>}
      </div>
      {a.channels&&<details><summary>Delivery channels</summary><div className="channel-list">{Object.entries(a.channels).map(([k,v])=><span key={k}><strong>{k}</strong>: {v.status}{v.delivered?` · ${v.delivered} delivered`:''}{v.accepted_or_sent?` · ${v.accepted_or_sent} queued/sent`:''}{v.failed?` · ${v.failed} failed`:''}{v.confirmed_delivery?' · provider confirmed':''}</span>)}</div><p className="fine">{a.delivery_note}</p></details>}
    </article>):<Empty title="No advisories" detail="High/critical recorded assessments can create draft advisories."/>}</div>
  </Panel>;
}

function DataSettings({system,sources,auth,selected,locations,session,onLogout,onAuthRefresh}) {
  const [channels,setChannels]=useState(null); const [satellite,setSatellite]=useState(null); const [model,setModel]=useState(null); const [infra,setInfra]=useState([]); const [routes,setRoutes]=useState([]);
  const [recipients,setRecipients]=useState([]); const [recipientError,setRecipientError]=useState(''); const [recipientMsg,setRecipientMsg]=useState('');
  const [recipientForm,setRecipientForm]=useState({name:'',phone_e164:'+91',location_id:selected?.id||'',language:'en',sms_enabled:true,consent_confirmed:false});
  const isAdmin=['ADMIN','DEV_OPERATOR'].includes(auth?.current_role);
  async function loadSettings(){
    const tasks=await Promise.allSettled([get('/api/notification/channels'),selected?get(`/api/satellite/${selected.id}`):Promise.resolve(null),get('/api/research/model-card'),get('/api/infrastructure'),get('/api/routes'),get('/api/notification/recipients')]);
    const [c,s,m,i,r,n]=tasks;if(c.status==='fulfilled')setChannels(c.value);if(s.status==='fulfilled')setSatellite(s.value);if(m.status==='fulfilled')setModel(m.value);if(i.status==='fulfilled')setInfra(i.value);if(r.status==='fulfilled')setRoutes(r.value);if(n.status==='fulfilled'){setRecipients(n.value);setRecipientError('');}else setRecipientError(n.reason?.message||'Admin key required to manage notification recipients.');
  }
  useEffect(()=>{loadSettings();},[selected?.id,auth?.current_role]);
  useEffect(()=>{setRecipientForm(f=>({...f,location_id:selected?.id||''}));},[selected?.id]);
  async function addRecipient(e){e.preventDefault();setRecipientMsg('');setRecipientError('');try{const payload={...recipientForm,location_id:recipientForm.location_id===''?null:Number(recipientForm.location_id)};await post('/api/notification/recipients',payload);setRecipientMsg('SMS recipient enrolled. Only explicitly opted-in contacts will receive alerts.');setRecipientForm(f=>({...f,name:'',phone_e164:'+91',consent_confirmed:false}));await loadSettings();}catch(err){setRecipientError(err.message);}}
  async function revokeRecipient(id){if(!window.confirm('Revoke this recipient from future PRAHARI SMS alerts?'))return;setRecipientError('');try{await patch(`/api/notification/recipients/${id}`,{consent_status:'REVOKED'});await loadSettings();}catch(err){setRecipientError(err.message);}}
  const sourceList=sources?.sources ? Object.entries(sources.sources) : [];
  return <div><div className="page-title"><div><h1>Data & Settings</h1><p>Source provenance, system health, authorization and external alert delivery.</p></div></div>
    <div className="settings-grid">
      <Panel title="Data sources" subtitle="Origin and operational status are shown explicitly."><div className="source-table" role="table">{sourceList.map(([id,s])=><div className="source-row" key={id}><div><strong>{s.name}</strong><span>{s.kind}</span></div><StateBadge state={s.status}/><div><span>{s.coverage}</span><small>{s.spatial_resolution}</small></div><a href={s.origin?.startsWith('http')?s.origin:undefined} target="_blank" rel="noreferrer">{s.origin}</a></div>)}</div><p className="fine">{sources?.policy}</p></Panel>
      <Panel title="System health"><div className="status-grid">{system?Object.entries(system).filter(([k])=>!['last_sync'].includes(k)).slice(0,14).map(([k,v])=><div key={k}><span>{k.replaceAll('_',' ')}</span><strong>{typeof v==='boolean'?(v?'Yes':'No'):String(v)}</strong></div>):<Loading/>}</div></Panel>
      <Panel title="Admin portal session" subtitle={auth?.auth_required?'Protected admin session. Credentials remain in this browser session only.':'Local development mode is open; enable authentication before shared deployment.'}><div className="session-card"><span className="session-role"><Icon name="shield" size={18}/><strong>{auth?.current_role||session?.portal||'ADMIN'}</strong></span><div><span>Portal</span><strong>Administration & Command Center</strong></div><div><span>Scope</span><strong>All monitored areas</strong></div><button className="btn btn-secondary small" onClick={onLogout}><Icon name="logout" size={15}/> Sign out</button></div></Panel>
      <Panel title="Notification channels" subtitle="Provider readiness, not just toggle state."><div className="channel-list">{channels?Object.entries(channels).filter(([k])=>!['policy','status_callback','active_recipients'].includes(k)).map(([k,v])=><span key={k}><strong>{k}</strong>: {v.status} · {v.delivery}{v.opted_in_recipients!=null?` · ${v.opted_in_recipients} opted in`:''}</span>):<Loading/>}</div>{channels&&<div className="notification-summary"><span>Active recipients <strong>{channels.active_recipients??0}</strong></span><span>Status callback <strong>{channels.status_callback?'Configured':'Not configured'}</strong></span></div>}<p className="fine">{channels?.policy}</p></Panel>
    </div>

    <Panel title="Civilian SMS registry" subtitle="Field officers register opted-in civilians by posting; admins retain oversight and emergency correction access." className="recipient-panel">
      {!isAdmin&&<div className="notice notice-warn">Field officers should use Reports & Alerts → Civilian enrollment. Admin access is required for the full cross-area registry.</div>}
      {recipientError&&<div className="notice notice-error">{recipientError}</div>}{recipientMsg&&<div className="notice notice-warn">{recipientMsg}</div>}
      {isAdmin&&<div className="recipient-layout">
        <form className="recipient-form" onSubmit={addRecipient}>
          <div className="form-row"><label className="field"><span>Name / household / officer</span><input required maxLength={120} value={recipientForm.name} onChange={e=>setRecipientForm(f=>({...f,name:e.target.value}))}/></label><label className="field"><span>Phone number</span><input required placeholder="+919876543210" value={recipientForm.phone_e164} onChange={e=>setRecipientForm(f=>({...f,phone_e164:e.target.value}))}/></label></div>
          <div className="form-row"><label className="field"><span>Alert area</span><select value={recipientForm.location_id} onChange={e=>setRecipientForm(f=>({...f,location_id:e.target.value}))}><option value="">All monitored areas</option>{locations.map(x=><option key={x.id} value={x.id}>{x.name}, {x.state}</option>)}</select></label><label className="field"><span>Language</span><select value={recipientForm.language} onChange={e=>setRecipientForm(f=>({...f,language:e.target.value}))}><option value="en">English</option><option value="hi">Hindi</option><option value="as">Assamese</option></select></label></div>
          <div className="channel-checks"><span><strong>Delivery channel:</strong> Text SMS</span></div>
          <label className="consent-check"><input type="checkbox" required checked={recipientForm.consent_confirmed} onChange={e=>setRecipientForm(f=>({...f,consent_confirmed:e.target.checked}))}/><span>I confirm this recipient explicitly opted in to PRAHARI emergency/advisory notifications and understands how to request removal.</span></label>
          <button className="btn btn-primary">Add SMS recipient</button>
        </form>
        <div className="recipient-list">{recipients.length?recipients.map(r=>{const loc=locations.find(x=>x.id===r.location_id);return <div className={`recipient-row ${r.consent_status!=='ACTIVE'?'recipient-revoked':''}`} key={r.id}><div><strong>{r.name}</strong><span>{r.phone_e164}</span><small>{loc?`${loc.name}, ${loc.state}`:'All monitored areas'} · {r.language.toUpperCase()}{r.registered_by_officer?` · by ${r.registered_by_officer}`:''}</small></div><div className="recipient-channels">{r.sms_enabled&&<Badge>SMS</Badge>}<Badge tone={r.consent_status==='ACTIVE'?'good':'neutral'}>{r.consent_status}</Badge></div>{r.consent_status==='ACTIVE'&&<button className="btn btn-ghost small" onClick={()=>revokeRecipient(r.id)}>Revoke</button>}</div>}):<Empty title="No opted-in recipients" detail="Add opted-in phone numbers here before issuing SMS alerts."/>}</div>
      </div>}
      <p className="fine">PRAHARI never sends to arbitrary numbers. SMS delivery is restricted to this consented directory and is logged per recipient.</p>
    </Panel>

    <details className="disclosure"><summary>Twilio setup & delivery behavior</summary><div className="disclosure-body"><p>Set Twilio credentials and the SMS sender only in the backend <code>.env</code>. Never place them in Vite/frontend environment files.</p><p>Delivery status callbacks require a public HTTPS base URL. For a local demo, the admin can refresh delivery status manually.</p><p>For India SMS, sender/DLT requirements depend on the route and account setup; finish provider compliance before relying on this for public deployment.</p></div></details>
    <details className="disclosure"><summary>Satellite & post-event detection roadmap</summary><div className="disclosure-body"><p><strong>Current:</strong> {satellite?.pipeline_status || 'Visual basemap context only'}.</p><p>{satellite?.detection_module?.note}</p><p>Landslide4Sense-style semantic segmentation remains a separate post-event inventory capability and is not represented as future-risk forecasting.</p></div></details>
    <details className="disclosure"><summary>Experimental ML model</summary><div className="disclosure-body"><p><strong>{model?.model_type || 'Research ensemble'}</strong></p><p>{model?.warning || 'Experimental model is not field calibrated.'}</p><p className="fine">Primary operational UI uses the transparent screening baseline until a real NER dataset is trained and validated spatially/temporally.</p></div></details>
    <details className="disclosure"><summary>Infrastructure & routing · prototype data</summary><div className="disclosure-body"><p>These modules are preserved but clearly marked as non-authoritative until verified GIS layers are connected.</p><div className="mini-list">{infra.filter(x=>x.location_id===selected?.id).map(x=><span key={`${x.type}-${x.name}`}>{x.type}: {x.name} · {x.data_status}</span>)}{routes.filter(x=>x.location_id===selected?.id).map(x=><span key={x.id}>Route suggestion: {x.route} · {x.status} · not a safety claim</span>)}</div></div></details>
    <details className="disclosure"><summary>Reference adaptations & licensing</summary><div className="disclosure-body"><p>GLAS informed rainfall-history and data-provenance design. Landslide4Sense informed the separate post-event segmentation roadmap. The boosted-tree competition repository informed reproducible training organization. No third-party repository code is copied into the core application unless its license is recorded in the project documentation.</p></div></details>
  </div>;
}

export default PortalApp;
