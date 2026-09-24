export const API = import.meta.env.VITE_PRAHARI_API || 'http://127.0.0.1:8000';

const KEY_STORAGE = 'prahari_operator_key';
const PORTAL_STORAGE = 'prahari_portal';
const ACTOR_STORAGE = 'prahari_actor';

export function getOperatorKey() {
  return sessionStorage.getItem(KEY_STORAGE) || '';
}

export function setOperatorKey(value) {
  if (value) sessionStorage.setItem(KEY_STORAGE, value);
  else sessionStorage.removeItem(KEY_STORAGE);
}

export function getPortalSession() {
  const portal = sessionStorage.getItem(PORTAL_STORAGE) || '';
  let actor = null;
  try { actor = JSON.parse(sessionStorage.getItem(ACTOR_STORAGE) || 'null'); } catch { actor = null; }
  return portal ? { portal, actor } : null;
}

export function setPortalSession(portal, actor = null) {
  if (portal) sessionStorage.setItem(PORTAL_STORAGE, portal);
  else sessionStorage.removeItem(PORTAL_STORAGE);
  if (actor) sessionStorage.setItem(ACTOR_STORAGE, JSON.stringify(actor));
  else sessionStorage.removeItem(ACTOR_STORAGE);
}

export function clearPortalSession() {
  sessionStorage.removeItem(KEY_STORAGE);
  sessionStorage.removeItem(PORTAL_STORAGE);
  sessionStorage.removeItem(ACTOR_STORAGE);
}

function headers(extra = {}) {
  const key = getOperatorKey();
  return { ...(key ? { 'X-PRAHARI-Key': key } : {}), ...extra };
}

export async function request(path, options = {}) {
  const { timeout = 60000, signal, ...fetchOptions } = options;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(`${API}${path}`, {
      ...fetchOptions, signal: controller.signal, headers: headers(options.headers || {}),
    });
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        const detail = body.detail || body.message;
        if (detail) message = typeof detail === 'string' ? detail : JSON.stringify(detail);
      } catch { /* non-json response */ }
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    const type = response.headers.get('content-type') || '';
    return await (type.includes('application/json') ? response.json() : response.text());
  } catch (error) {
    if (timedOut) throw new Error('Request timed out. Check the connection and retry.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export async function loginPortal({ portal, accessKey = '', officerCode = '' }) {
  const response = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ portal, access_key: accessKey, officer_code: officerCode || null }),
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch { /* non-json response */ }
    throw new Error(message);
  }
  return response.json();
}

export const get = (path, options = {}) => request(path, options);
export const post = (path, body, options = {}) => request(path, {
  ...options,
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body ?? {}),
});
export const patch = (path, body) => request(path, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body ?? {}),
});
export const postForm = (path, formData) => request(path, { method: 'POST', body: formData });

export function downloadUrl(path) {
  return `${API}${path}`;
}
