"""MSG91 Flow API adapter for DLT-approved, variable-based Indian SMS templates."""
import hmac
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from settings import (MSG91_AUTHKEY, MSG91_TEMPLATES_JSON,
                      MSG91_TEMPLATES_APPROVED, MSG91_WEBHOOK_TOKEN)

API_URL = 'https://control.msg91.com/api/v5/flow'
INDIAN_MOBILE = re.compile(r'^\+91[6-9]\d{9}$')
IDS = re.compile(r'^[A-Za-z0-9_-]{6,80}$')
PLACEHOLDERS = ('##VAR1##', '##VAR2##')
LANGUAGES = ('en', 'hi', 'as')


class Msg91Rejection(Exception):
    def __init__(self, status=400, code=None):
        self.status = status
        self.code = code
        super().__init__('MSG91 rejected the request. Check the provider dashboard for details.')


def templates():
    try:
        data = json.loads(MSG91_TEMPLATES_JSON or '{}')
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for lang in LANGUAGES:
        item = data.get(lang)
        if not isinstance(item, dict):
            continue
        ident = item.get('template_id')
        body = item.get('body')
        if not isinstance(ident, str) or not IDS.fullmatch(ident):
            continue
        if not isinstance(body, str) or not all(body.count(v) == 1 for v in PLACEHOLDERS):
            continue
        if re.search(r'##[A-Za-z0-9_]+##', body.replace('##VAR1##', '').replace('##VAR2##', '')):
            continue
        out[lang] = {'template_id': ident, 'body': body}
    return out


def status():
    configured = templates()
    issues = []
    if not MSG91_AUTHKEY:
        issues.append('Add PRAHARI_MSG91_AUTHKEY privately on the API and worker.')
    missing = [lang for lang in LANGUAGES if lang not in configured]
    if missing:
        issues.append('Configure approved MSG91 SMS templates for: ' + ', '.join(missing) + '.')
    if not MSG91_TEMPLATES_APPROVED:
        issues.append('Confirm the three MSG91 templates and sender are approved on the DLT/MSG91 panels, then set PRAHARI_MSG91_TEMPLATES_APPROVED=true.')
    if len(MSG91_WEBHOOK_TOKEN) < 32:
        issues.append('Set a private PRAHARI_MSG91_WEBHOOK_TOKEN of at least 32 characters and use it as the webhook custom header.')
    return {'provider': 'msg91', 'ready': not issues, 'issues': issues,
            'configured_languages': sorted(configured),
            'note': 'Configuration cannot confirm available credits, throughput, or actual DLT approval; test with an approved recipient first.'}


def message_plan(alert, language, message):
    item = templates().get(language)
    if not item:
        raise ValueError(f'Missing approved MSG91 template for {language}.')
    values = {'VAR1': alert.get('location') or 'selected area', 'VAR2': message}
    text = item['body'].replace('##VAR1##', values['VAR1']).replace('##VAR2##', values['VAR2'])
    return {'text': text, 'template_id': item['template_id'],
            'template_variables': json.dumps(values, ensure_ascii=False)}


def verify_webhook(token):
    return len(MSG91_WEBHOOK_TOKEN) >= 32 and bool(token) and hmac.compare_digest(token, MSG91_WEBHOOK_TOKEN)


def send(item, opener=None):
    if opener is None:
        opener = urlopen
    if not status()['ready']:
        raise Msg91Rejection(403)
    if not INDIAN_MOBILE.fullmatch(item['phone_e164']):
        raise Msg91Rejection(400, 'INVALID_INDIAN_MOBILE')
    try:
        variables = json.loads(item['template_variables'])
        template_id = item['template_id']
        if not isinstance(variables, dict) or set(variables) != {'VAR1', 'VAR2'}:
            raise ValueError('Invalid variables')
        current = next((x for x in templates().values() if x['template_id'] == template_id), None)
        if not current or current['body'].replace('##VAR1##', variables['VAR1']).replace('##VAR2##', variables['VAR2']) != item['message']:
            raise ValueError('Approved template changed since the broadcast was queued')
    except (ValueError, TypeError, KeyError):
        raise Msg91Rejection(400, 'TEMPLATE_MISMATCH') from None
    payload = {'template_id': template_id, 'short_url': '0',
               'recipients': [{'mobiles': item['phone_e164'][1:], **variables,
                               'CRQID': f"B{item['id']}"}]}
    request = Request(API_URL, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                      headers={'authkey': MSG91_AUTHKEY, 'content-type': 'application/json',
                               'accept': 'application/json'}, method='POST')
    try:
        with opener(request, timeout=20) as response:
            data = json.loads(response.read(4096))
    except HTTPError as exc:
        # Provider error bodies may contain personal data and credentials.
        raise Msg91Rejection(exc.code) from None
    except (ValueError, UnicodeDecodeError):
        # Provider may have accepted the message even when its response is invalid.
        return {'sid': None, 'status': 'UNKNOWN'}
    if not isinstance(data, dict):
        return {'sid': None, 'status': 'UNKNOWN'}
    if data.get('type') == 'error':
        code = str(data.get('code') or '')[:20]
        raise Msg91Rejection(400, code if code.isdigit() else None)
    if data.get('type') != 'success':
        return {'sid': None, 'status': 'UNKNOWN'}
    sid = data.get('message')
    if not isinstance(sid, str) or not IDS.fullmatch(sid):
        return {'sid': None, 'status': 'UNKNOWN'}
    return {'sid': sid, 'status': 'QUEUED'}


STATUS_MAP = {'0': 'SENT', '1': 'DELIVERED', '2': 'FAILED', '9': 'FAILED',
              '16': 'FAILED', '25': 'FAILED', '17': 'FAILED', '20': 'FAILED'}


def parse_webhook(payload):
    if not isinstance(payload, dict):
        return None
    correlation = payload.get('CRQID')
    status = STATUS_MAP.get(str(payload.get('status')))
    item_id = (int(correlation[1:]) if isinstance(correlation, str) and
               re.fullmatch(r'B[1-9]\d{0,17}', correlation) else None)
    if not status:
        return None
    number = str(payload.get('telNum') or '').lstrip('+')
    if not INDIAN_MOBILE.fullmatch('+' + number):
        return None
    request_id = payload.get('requestId')
    if request_id is not None and not isinstance(request_id, str):
        return None
    if not item_id and (not request_id or not IDS.fullmatch(request_id)):
        return None
    return {'id': item_id, 'status': status,
            'phone': '+' + number, 'sid': request_id,
            'error_code': str(payload.get('status')) if status == 'FAILED' else None}
