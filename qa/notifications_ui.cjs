/* Offline SMS regressions. All recipients, provider errors and deliveries are synthetic. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = process.env.PRAHARI_UI_URL || 'http://127.0.0.1:5173';
const out = process.env.PRAHARI_UI_OUTPUT || path.resolve(__dirname, '../test-results');
const setupIssue = 'SMS is disabled. Set PRAHARI_SMS_ENABLED=true on the backend and restart/redeploy it.';

async function run() {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [], requests = [];
    let ready = false, recipients = 2, failed = false, refreshFails = false;
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', dialog => dialog.accept());
    await page.addInitScript(() => {
      sessionStorage.setItem('prahari_portal', 'ADMIN');
      sessionStorage.setItem('prahari_operator_key', 'synthetic-test-only');
    });
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (!url.pathname.startsWith('/api/')) {
        return url.origin === new URL(base).origin ? route.continue() : route.abort();
      }
      let body = [];
      if (url.pathname === '/api/auth/status') body = { current_role: 'ADMIN', auth_required: true };
      else if (url.pathname === '/api/live/locations') body = [{ id: 1, name: 'Gangtok', state: 'Sikkim', lat: 27.33, lon: 88.61, data_state: 'CURRENT', risk_level: 'UNKNOWN', sources: [], factors: [] }];
      else if (url.pathname === '/api/alerts') body = [{ id: 7, location_id: 1, location: 'Gangtok, Sikkim', level: 'HIGH', lifecycle_status: 'ISSUED', message: 'Synthetic test advisory only.', source: 'SYNTHETIC' }];
      else if (url.pathname === '/api/system/status') body = { api: 'online' };
      else if (url.pathname.endsWith('/notification-preview')) body = { target_label: 'Gangtok, Sikkim', sms_recipients: recipients, provider: { sms: { ready, issues: ready ? [] : [setupIssue] } } };
      else if (url.pathname.endsWith('/issue-and-notify')) {
        requests.push(route.request().postDataJSON());
        body = { accepted_or_queued: failed ? 0 : 1, failed: failed ? 1 : 0, skipped_duplicates: 1, target_label: 'Gangtok, Sikkim', results: failed ? [{ status: 'FAILED', error_code: '21608', error: 'Synthetic recipient is not verified.' }] : [{ status: 'QUEUED' }, { status: 'SKIPPED_DUPLICATE' }] };
      } else if (url.pathname.endsWith('/deliveries/refresh')) body = { deliveries: refreshFails ? [{ refresh_error: 'Synthetic provider status unavailable.' }] : [] };
      else if (url.pathname.endsWith('/deliveries')) body = [{ id: 1, recipient_id: 1, recipient_name: 'Synthetic recipient', status: failed ? 'FAILED' : 'QUEUED', error_code: failed ? '21608' : null, error_message: failed ? 'Synthetic recipient is not verified.' : null }];
      else if (url.pathname === '/api/notification/channels') body = { sms: { status: 'DISABLED', delivery: 'Provider receipts', issues: [setupIssue], opted_in_recipients: 2 }, active_recipients: 2 };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(base);
    await page.getByRole('button', { name: 'Reports & Alerts', exact: true }).click();
    await page.getByRole('button', { name: /Advisory alerts/ }).click();
    const send = page.getByRole('button', { name: 'Send / retry SMS', exact: true });
    await send.click();
    await page.getByRole('alert').filter({ hasText: 'PRAHARI_SMS_ENABLED=true' }).waitFor();
    assert.equal(requests.length, 0);

    ready = true; recipients = 0;
    await send.click();
    await page.getByRole('alert').filter({ hasText: 'No opted-in SMS recipients in Gangtok' }).waitFor();
    assert.equal(requests.length, 0);

    recipients = 2;
    await send.click();
    await page.getByRole('status').filter({ hasText: '1 accepted/queued' }).waitFor();
    assert.equal(requests.at(-1).retry_failed, true, 'The retry button must request failed-delivery retries');
    assert.equal(requests.at(-1).scope, 'ALERT_AREA');
    assert.equal(await page.getByRole('alert').count(), 0);
    await page.getByText(/1 already attempted and skipped/).waitFor();

    failed = true;
    await send.click();
    await page.getByRole('alert').filter({ hasText: 'Twilio 21608: Synthetic recipient is not verified.' }).waitFor();
    const explanation = page.getByRole('link', { name: 'Error explanation', exact: true });
    await explanation.waitFor();
    assert.equal(await explanation.getAttribute('href'), 'https://www.twilio.com/docs/api/errors/21608');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({ path: path.join(out, 'sms-failure-SYNTHETIC.png'), fullPage: true });

    refreshFails = true;
    await page.getByRole('button', { name: 'Refresh delivery status', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Synthetic provider status unavailable.' }).waitFor();
    refreshFails = false;
    await page.getByRole('button', { name: 'Refresh delivery status', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Delivery statuses refreshed.' }).waitFor();

    await page.getByRole('button', { name: 'Data & Settings', exact: true }).click();
    await page.getByText('SMS setup needed', { exact: true }).waitFor();
    await page.getByText(setupIssue, { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({ path: path.join(out, 'sms-setup-SYNTHETIC.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('SMS browser regressions passed: retry request, configuration/recipient blockers, provider errors, delivery details, refresh failures, mobile layout. No real messages sent.');
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
