/* Offline browser regressions. Every scene, mask and score below is SYNTHETIC TEST DATA. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = process.env.PRAHARI_UI_URL || 'http://127.0.0.1:5173';
const out = process.env.PRAHARI_UI_OUTPUT || path.resolve(__dirname, '../test-results');
fs.mkdirSync(out, { recursive: true });
const locations = [
  { id: 1, name: 'Gangtok', state: 'Sikkim', lat: 27.3314, lon: 88.6138 },
  { id: 2, name: 'Aizawl', state: 'Mizoram', lat: 23.7271, lon: 92.7176 },
].map(x => ({ ...x, data_state: 'CURRENT', risk_level: 'UNKNOWN', sources: [], factors: [] }));
const scene = { id: 'SYNTHETIC_TEST_ONLY', datetime: '2026-01-01T00:00:00Z', cloud_cover_pct: 5 };
const patch = { patch_id: 'a'.repeat(32), scene, shape: [128, 128, 14], terrain: { source: 'SYNTHETIC_TEST_ONLY' } };
const candidate = { type: 'Feature', properties: { candidate_id: 1, area_m2: 1200, mean_softmax_score_pct: 80 }, geometry: { type: 'Polygon', coordinates: [[[88.612, 27.33], [88.614, 27.33], [88.614, 27.332], [88.612, 27.332], [88.612, 27.33]]] } };
// One transparent PNG for exercising image overlay lifecycle; not a real inference mask.
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB1sAAAAASUVORK5CYII=';
function result(empty) {
  return { location: 'SYNTHETIC TEST ONLY', location_id: 1, patch,
    inference: { candidate_pixel_pct: empty ? 0 : 1.2, checkpoint_sha256: 'b'.repeat(64), generated_at: '2026-01-02T00:00:00Z', warning: 'SYNTHETIC TEST ONLY' },
    candidate_polygons: { type: 'FeatureCollection', features: empty ? [] : [candidate], properties: { total_area_m2: empty ? 0 : 1200, minimum_component_pixels: 8 } },
    mask_overlay: { image_url: image, bounds: [[27.325, 88.608], [27.338, 88.62]] }, warning: 'SYNTHETIC TEST ONLY' };
}

async function run() {
  const deadline = Date.now() + 30000;
  while (true) {
    try { if ((await fetch(base)).ok) break; } catch {}
    if (Date.now() > deadline) throw new Error('Vite did not start');
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, acceptDownloads: true });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => { sessionStorage.setItem('prahari_portal', 'ADMIN'); sessionStorage.setItem('prahari_operator_key', 'test-only'); });
    let ready = false, mode = 'normal', current = null, sequence = 0;
    const requests = [];
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (!url.pathname.startsWith('/api/')) {
        if (url.origin === new URL(base).origin || url.protocol === 'data:') return route.continue();
        return route.abort();
      }
      let body = [];
      if (url.pathname === '/api/auth/status') body = { current_role: 'ADMIN', auth_required: true };
      else if (url.pathname === '/api/live/locations') body = locations;
      else if (url.pathname === '/api/system/status') body = { api: 'online' };
      else if (url.pathname === '/api/satellite/model/status') body = ready ? { status: 'READY', verified: true, checkpoint_sha256: 'b'.repeat(64) } : { status: 'NOT_CONFIGURED', verified: false, reason: 'Trained weights required' };
      else if (url.pathname === '/api/satellite/preprocess/status') body = { status: 'READY', live_inference_ready: ready, input_profile_configured: ready, profile_checkpoint_sha256: ready ? 'b'.repeat(64) : null, experimental_fallback_allowed: ready };
      else if (url.pathname.startsWith('/api/satellite/sentinel2/')) body = { status: 'AVAILABLE', scene_count: 2, pair: { status: 'PAIR_READY', reference: scene, recent: scene } };
      else if (url.pathname.startsWith('/api/satellite/jobs/status/')) body = { ...current, status: mode === 'hold' ? 'RUNNING' : 'SUCCEEDED', stage: 'Reading Sentinel-2 band B2', result: current.operation === 'prepare' ? patch : result(mode === 'empty') };
      else if (url.pathname.startsWith('/api/satellite/jobs/')) {
        const data = route.request().postDataJSON(); requests.push(data);
        current = { job_id: `job-${++sequence}`, location_id: Number(url.pathname.split('/').pop()), operation: data.operation, status: 'QUEUED' };
        body = current;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(base);
    await page.getByRole('button', { name: 'Risk Map', exact: true }).click();
    await page.getByRole('button', { name: 'Sentinel-2 intelligence', exact: true }).click();
    await page.getByText('AI analysis unavailable', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Run segmentation', exact: true }).isDisabled(), true);
    async function noOverflow(width) {
      await page.setViewportSize({ width, height: 844 });
      const overflow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        elements: [...document.querySelectorAll('body *')].filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1); })
          .slice(0, 25).map(el => ({ tag: el.tagName, cls: el.className, text: el.textContent.slice(0, 80), left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right })) }));
      if (overflow.scrollWidth > width + 1) {
        await page.screenshot({ path: path.join(out, `overflow-${width}-SYNTHETIC.png`), fullPage: true });
        console.error(JSON.stringify(overflow));
      }
      assert.equal(overflow.scrollWidth <= width + 1, true, `Horizontal overflow at ${width}px`);
    }
    await noOverflow(320); await noOverflow(390);
    await page.screenshot({ path: path.join(out, 'mobile-unavailable.png'), fullPage: true });
    ready = true;
    await page.getByRole('button', { name: 'Refresh status & scenes', exact: true }).click();
    await page.getByText('Experimental analysis available', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Run segmentation', exact: true }).isDisabled(), true);
    await page.getByRole('checkbox', { name: /I understand/ }).check();
    await page.getByRole('button', { name: 'Prepare patch', exact: true }).click();
    await page.getByRole('heading', { name: 'Patch prepared', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Run segmentation', exact: true }).click();
    await page.getByRole('heading', { name: '1 candidate polygon', exact: true }).waitFor();
    assert.equal(requests.at(-1).patch_id, patch.patch_id);
    assert.equal(requests.at(-1).confirm_experimental, true);
    await page.getByRole('checkbox', { name: 'Candidate pixel mask', exact: true }).uncheck();
    assert.equal(await page.locator('.leaflet-image-layer').count(), 0);
    await page.getByRole('checkbox', { name: 'Candidate pixel mask', exact: true }).check();
    await page.getByRole('checkbox', { name: 'Candidate polygons', exact: true }).uncheck();
    assert.equal(await page.locator('.leaflet-overlay-pane path').count(), 0);
    await page.getByRole('checkbox', { name: 'Candidate polygons', exact: true }).check();
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export GeoJSON', exact: true }).click();
    const download = await downloadEvent;
    await download.saveAs(path.join(out, 'SYNTHETIC_TEST_ONLY.geojson'));
    const exported = JSON.parse(fs.readFileSync(path.join(out, 'SYNTHETIC_TEST_ONLY.geojson'), 'utf8'));
    assert.equal(exported.properties.human_review_required, true);
    assert.equal(exported.features.length, 1);
    await noOverflow(320); await noOverflow(390);
    await page.screenshot({ path: path.join(out, 'mobile-result-SYNTHETIC.png'), fullPage: true });
    await noOverflow(1280);
    await page.screenshot({ path: path.join(out, 'desktop-result-SYNTHETIC.png'), fullPage: true });
    mode = 'empty';
    await page.getByRole('button', { name: 'Run segmentation', exact: true }).click();
    await page.getByRole('heading', { name: 'No candidate polygons', exact: true }).waitFor();
    await page.getByText('No components met the polygon size threshold. This is not proof that the area is safe.', { exact: true }).waitFor();
    mode = 'hold';
    await page.getByRole('button', { name: 'Run segmentation', exact: true }).click();
    await page.getByText('Reading Sentinel-2 band B2', { exact: true }).waitFor();
    await page.getByRole('searchbox').fill('Aizawl');
    await page.locator('.location-results').getByRole('button', { name: 'Aizawl Mizoram' }).click();
    await page.getByRole('heading', { name: 'Aizawl · post-event review', exact: true }).waitFor();
    assert.equal(await page.getByRole('region', { name: 'Segmentation result' }).count(), 0);
    assert.equal(await page.getByRole('checkbox', { name: /I understand/ }).isChecked(), false);
    assert.equal(await page.getByText('Reading Sentinel-2 band B2', { exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('Satellite browser checks passed: readiness, consent, patch reuse, layers, export, empty results, location switching, 320/390/1280px layouts. Synthetic fixtures only.');
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
