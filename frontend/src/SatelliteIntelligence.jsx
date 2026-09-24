import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, ImageOverlay, useMap } from 'react-leaflet';
import { get, post } from './api.js';

const number = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);
const date = value => value ? new Date(value).toLocaleString() : 'Unavailable';

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [16, 16], maxZoom: 16 }); }, [map, bounds]);
  return null;
}

function CandidateMap({ selected, result }) {
  const [mask, setMask] = useState(true);
  const [polygons, setPolygons] = useState(true);
  const overlay = result.mask_overlay;
  return <div className="sat-candidate-map">
    <div className="sat-layer-controls" aria-label="Map layers">
      <label><input type="checkbox" checked={mask} onChange={e => setMask(e.target.checked)}/> Candidate pixel mask</label>
      <label><input type="checkbox" checked={polygons} onChange={e => setPolygons(e.target.checked)}/> Candidate polygons</label>
    </div>
    <MapContainer center={[selected.lat, selected.lon]} zoom={14} className="map-canvas" scrollWheelZoom={false}>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors"/>
      <FitBounds bounds={overlay?.bounds}/>
      {mask && overlay && <ImageOverlay url={overlay.image_url} bounds={overlay.bounds}/>}
      {polygons && <GeoJSON data={result.candidate_polygons} style={{ color: '#b83025', weight: 2, fillOpacity: .15 }} onEachFeature={(feature, layer) => {
        const p = feature.properties || {};
        const popup = document.createElement('div');
        popup.textContent = `Candidate ${p.candidate_id} · ${number(p.area_m2, 0)} m² · score ${number(p.mean_softmax_score_pct)}% · unreviewed`;
        layer.bindPopup(popup);
      }}/>}
    </MapContainer>
    <p className="fine">Red pixels and outlines are experimental candidates. Unmarked areas have not been established as safe.</p>
  </div>;
}

function Result({ selected, result }) {
  const features = result.candidate_polygons?.features || [];
  const patch = result.patch || {};
  const inference = result.inference || {};
  function download() {
    const payload = { ...result.candidate_polygons, properties: { ...result.candidate_polygons.properties,
      location: result.location, acquired_at: patch.scene?.datetime, generated_at: inference.generated_at,
      checkpoint_sha256: inference.checkpoint_sha256, terrain: patch.terrain, input_profile: patch.input_profile,
      quality: patch.quality, regional_validation: 'NOT_PERFORMED', human_review_required: true } };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/geo+json' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `prahari-${selected.id}-${patch.patch_id}-UNREVIEWED.geojson`;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="sat-result-panel sat-result-detection" aria-label="Segmentation result">
    <div className="sat-result-heading"><div><span className="eyebrow">Experimental result · human review required</span>
      <h3>{features.length ? `${features.length} candidate polygon${features.length === 1 ? '' : 's'}` : 'No candidate polygons'}</h3></div>
      <button className="btn btn-secondary" onClick={download}>Export GeoJSON</button></div>
    <div className="sat-result-stats">
      <div><span>Candidate area</span><strong>{number((result.candidate_polygons?.properties?.total_area_m2 || 0) / 10000, 2)} ha</strong></div>
      <div><span>Candidate pixels</span><strong>{number(inference.candidate_pixel_pct, 2)}%</strong></div>
      <div><span>Acquisition</span><strong>{date(patch.scene?.datetime)}</strong></div>
    </div>
    {!features.length && <p className="notice notice-warn">No components met the polygon size threshold. This is not proof that the area is safe.</p>}
    <CandidateMap key={patch.patch_id} selected={selected} result={result}/>
    {!!features.length && <div className="sat-table-scroll"><table className="sat-candidate-table"><caption>Unreviewed candidates · softmax scores are not calibrated probabilities</caption>
      <thead><tr><th>Candidate</th><th>Area (m²)</th><th>Mean score</th></tr></thead>
      <tbody>{features.map((feature, index) => <tr key={index}><td>{feature.properties.candidate_id}</td><td>{number(feature.properties.area_m2, 0)}</td><td>{number(feature.properties.mean_softmax_score_pct)}%</td></tr>)}</tbody>
    </table></div>}
    <details className="disclosure"><summary>Result provenance and limitations</summary><div className="disclosure-body sat-provenance">
      <p><strong>Source scene:</strong> {patch.scene?.id} · Sentinel-2 L1C</p>
      <p><strong>Processed:</strong> {date(inference.generated_at)}</p>
      <p><strong>Checkpoint SHA-256:</strong> {inference.checkpoint_sha256}</p>
      <p><strong>Terrain:</strong> {patch.terrain?.source}</p>
      <p><strong>Input profile:</strong> {patch.input_profile?.provenance || 'Unavailable'}</p>
      <p>Polygons smaller than {result.candidate_polygons?.properties?.minimum_component_pixels ?? 8} pixels are omitted. The pixel mask includes all model-positive pixels.</p>
      <p>Cloud screening uses scene metadata; a pixel cloud mask has not been applied. Regional accuracy and preprocessing parity are not established.</p>
      <p>{result.warning} {inference.warning}</p>
    </div></details>
  </section>;
}

export default function SatelliteIntelligence({ selected, searchScenes, SceneCard }) {
  const [scenes, setScenes] = useState(null);
  const [model, setModel] = useState(null);
  const [prep, setPrep] = useState(null);
  const [sceneError, setSceneError] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [consent, setConsent] = useState(false);
  const [patch, setPatch] = useState(null);
  const [result, setResult] = useState(null);
  const [job, setJob] = useState(null);
  const requests = useRef(new Set());
  const loadRequest = useRef(null);
  function controller() { const c = new AbortController(); requests.current.add(c); return c; }
  async function load() {
    if (!selected) return;
    loadRequest.current?.abort();
    const c = controller(); loadRequest.current = c;
    setLoading(true); setSceneError('');
    const responses = await Promise.allSettled([
      get(`/api/satellite/sentinel2/${selected.id}`, { signal: c.signal, timeout: 25000 }),
      get('/api/satellite/model/status', { signal: c.signal }),
      get('/api/satellite/preprocess/status', { signal: c.signal }),
    ]);
    if (c.signal.aborted) return;
    const [scene, m, p] = responses;
    setModel(m.status === 'fulfilled' ? m.value : { status: 'UNAVAILABLE', reason: m.reason.message });
    setPrep(p.status === 'fulfilled' ? p.value : { status: 'UNAVAILABLE', runtime_error: p.reason.message });
    try {
      let data = scene.status === 'fulfilled' ? scene.value : null;
      if (!data || data.status === 'UNAVAILABLE' || data.error) data = await searchScenes(selected, { signal: c.signal });
      if (!c.signal.aborted) setScenes(data);
    } catch (e) { if (!c.signal.aborted) { setScenes(null); setSceneError(e.message); } }
    finally { requests.current.delete(c); if (!c.signal.aborted) setLoading(false); }
  }
  useEffect(() => { load(); return () => { requests.current.forEach(c => c.abort()); requests.current.clear(); }; }, []);
  const jobId = job?.job_id;
  useEffect(() => {
    if (!jobId) return;
    const c = controller(); let timer;
    async function poll() {
      try {
        const next = await get(`/api/satellite/jobs/status/${jobId}`, { signal: c.signal, timeout: 15000 });
        if (c.signal.aborted) return;
        if (next.location_id !== selected.id) throw new Error('Job location does not match this area.');
        setJob(next); setError('');
        if (next.status === 'SUCCEEDED') {
          if (next.operation === 'infer') { setResult(next.result); setPatch(next.result.patch); }
          else { setPatch(next.result); setResult(null); }
        } else if (next.status === 'FAILED') setError(next.error || 'Satellite processing failed.');
        else timer = setTimeout(poll, 2000);
      } catch (e) {
        if (c.signal.aborted) return;
        setError(e.message);
        if ([401, 403, 404].includes(e.status) || e.message.includes('does not match')) setJob(j => ({ ...j, status: 'FAILED' }));
        else timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { clearTimeout(timer); c.abort(); requests.current.delete(c); };
  }, [jobId]);
  const busy = starting || ['QUEUED', 'RUNNING'].includes(job?.status);
  const modelReady = model?.status === 'READY' && model?.verified === true;
  const prepReady = prep?.status === 'READY';
  const profileMatches = !!model?.checkpoint_sha256 && prep?.profile_checkpoint_sha256 === model.checkpoint_sha256;
  const canInfer = modelReady && prep?.live_inference_ready && profileMatches;
  async function start(operation) {
    const c = controller(); setStarting(true); setError('');
    try {
      const next = await post(`/api/satellite/jobs/${selected.id}`, { operation, confirm_experimental: consent,
        ...(operation === 'infer' && patch?.patch_id ? { patch_id: patch.patch_id } : {}) }, { signal: c.signal });
      if (!c.signal.aborted) { setJob(next); setResult(null); if (operation === 'prepare') setPatch(null); }
    } catch (e) { if (!c.signal.aborted) setError(e.message); }
    finally { requests.current.delete(c); if (!c.signal.aborted) setStarting(false); }
  }
  if (!selected) return <p>Select an area to view satellite intelligence.</p>;
  const pair = scenes?.pair;
  const steps = [
    [!!scenes?.scene_count, 'Scene discovery', scenes?.scene_count ? `${scenes.scene_count} real L2A acquisitions` : 'No scenes loaded'],
    [!!scenes?.scene_count, 'Scene metadata review', 'Acquisition dates and scene cloud cover only'],
    [pair?.status === 'PAIR_READY', 'Visual scene pairing', pair?.status === 'PAIR_READY' ? 'Comparison available' : 'Suitable pair unavailable'],
    [!!patch, '14-channel patch', patch ? 'Prepared for this location' : 'Not prepared'],
    [!!result, 'Experimental inference', result ? 'Completed' : 'Not run'],
    [!!result, 'Candidate polygons', result ? `${result.candidate_polygons?.features?.length || 0} polygons generated` : 'Not generated'],
  ];
  return <section className="sat-intel sat-intel-focus">
    <div className="sat-intel-head"><div><span className="eyebrow">Satellite intelligence</span><h2>{selected.name} · post-event review</h2><p>Review satellite acquisitions and experimental landslide candidates.</p></div>
      <button className="btn btn-secondary" onClick={load} disabled={loading || busy}>{loading ? 'Checking…' : 'Refresh status & scenes'}</button></div>
    <div className={`sat-readiness ${canInfer ? 'sat-available' : ''}`} role="status"><strong>{canInfer ? 'Experimental analysis available' : !model || !prep ? 'Checking analysis setup…' : 'AI analysis unavailable'}</strong>
      <p>{canInfer ? 'Outputs require human review. Regional accuracy has not been established.' : 'Scene review and patch preparation are separate from model inference.'}</p></div>
    <div className="sat-run-controls">
      <label className="sat-consent"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)}/> I understand this is experimental research output, not an official warning.</label>
      <div className="sat-buttons"><button className="btn btn-secondary" disabled={!prepReady || !consent || busy} onClick={() => start('prepare')}>Prepare patch</button>
        <button className="btn btn-primary" disabled={!canInfer || !consent || busy} onClick={() => start('infer')}>Run segmentation</button></div>
    </div>
    {busy && <div className="sat-progress" role="status"><span className="pulse-dot"/><span>{job?.stage || 'Starting processing…'}</span><small>Switching areas hides this job; processing continues on the server.</small></div>}
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {result && <Result selected={selected} result={result}/>}
    {patch && !result && <div className="sat-result-panel"><h3>Patch prepared</h3><p>{patch.scene?.id} · {date(patch.scene?.datetime)}</p><p className="fine">128 × 128 × 14 research input. No detection has been performed. It can be reused for one hour while this service stays running.</p></div>}
    <details className="disclosure"><summary>Analysis setup</summary><div className="disclosure-body">
      <p><strong>Model:</strong> {model?.status || 'CHECKING'} · {model?.reason || (modelReady ? 'Checkpoint load and forward pass verified; training quality is not verified.' : 'Waiting for status.')}</p>
      <p><strong>Patch preparation:</strong> {prepReady ? 'Runtime available' : prep?.runtime_error || 'Unavailable'}. This does not mean a patch has been prepared.</p>
      <p><strong>Input profile:</strong> {prep?.input_profile_configured ? 'Configured' : prep?.input_profile_error || 'Unavailable'}</p>
      {modelReady && prep?.input_profile_configured && !profileMatches && <p>The input profile belongs to a different model checkpoint.</p>}
      {!prep?.experimental_fallback_allowed && <p>Experimental live preprocessing has not been enabled on the server.</p>}
      <p>Live inference needs trained weights and their training-derived preprocessing settings. See SATELLITE_SETUP.md in the repository.</p>
    </div></details>
    <details className="disclosure" open={!result}><summary>Satellite scenes · visual comparison</summary><div className="disclosure-body">
      {sceneError && <p className="notice notice-error">Catalog unavailable: {sceneError}</p>}
      <p>{scenes ? `${scenes.scene_count || 0} L2A scenes found` : 'No scenes loaded'} · {pair?.status === 'PAIR_READY' ? 'Comparison pair ready' : 'Suitable pair unavailable'}</p>
      <p>These L2A images are visual context. The inference patch uses a separately selected L1C acquisition; its actual date is shown with the result. A pair is not proof of change or a landslide.</p>
      <div className="sat-scene-grid"><SceneCard scene={pair?.reference} label="Reference acquisition"/><SceneCard scene={pair?.recent} label="Recent acquisition"/></div>
    </div></details>
    <details className="disclosure"><summary>Processing stages</summary><div className="disclosure-body sat-pipeline">{steps.map(([done, title, detail], i) => <div className={`sat-step ${done ? 'done' : 'pending'}`} key={title}><strong>{i + 1}</strong><span>{title}<small>{detail}</small></span></div>)}</div></details>
  </section>;
}
