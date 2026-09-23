"""Warm PRAHARI's low-zoom NASA GIBS cache before a low-bandwidth demo.
Backend must be running on http://127.0.0.1:8000.
"""
import json, sys
from urllib.request import Request, urlopen
base=(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000').rstrip('/')
print('PRAHARI — preparing low-bandwidth NASA imagery cache (zoom 4–6)...')
try:
    req=Request(base+'/api/satellite/cache/warm?max_zoom=6',method='POST')
    with urlopen(req,timeout=180) as r: data=json.loads(r.read().decode())
    print(json.dumps(data,indent=2))
    if data.get('cached_tiles',0):
        print('\nREADY: Cached NASA can now load from localhost. The app will also keep older cached imagery for the next-day demo if internet is unavailable.')
    else:
        print('\nNo NASA tiles could be downloaded. This is NOT a demo blocker: use Offline EO Lite, which is fully local.')
except Exception as e:
    print('Could not reach the backend/cache service:',e)
    print('Start the backend first. Offline EO Lite remains available regardless.')
    raise SystemExit(1)
