#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib import error, parse, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line.removeprefix('export ').strip()
        key, sep, value = line.partition('=')
        if sep and ENV_KEY_RE.match(key.strip()):
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))

def main() -> None:
    load_env_file(PROJECT_ROOT / '.env.render')
    parser = argparse.ArgumentParser(description='Trigger a Render deploy/restart after data upload.')
    parser.add_argument('--service-id', default=os.getenv('RENDER_SERVICE_ID', '').strip())
    parser.add_argument('--api-base', default=os.getenv('RENDER_API_BASE', 'https://api.render.com/v1').rstrip('/'))
    parser.add_argument('--clear-cache', choices=('clear', 'do_not_clear'), default='do_not_clear')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    api_key = os.getenv('RENDER_API_KEY', '').strip()
    if not args.service_id:
        raise SystemExit('Missing RENDER_SERVICE_ID in .env.render or --service-id.')
    print(f'Service: {args.service_id}')
    if args.dry_run:
        return
    if not api_key:
        raise SystemExit('Missing RENDER_API_KEY in .env.render or environment.')
    payload = {'clearCache': args.clear_cache}
    req = request.Request(
        url=f"{args.api_base}/services/{parse.quote(args.service_id, safe='')}/deploys",
        data=json.dumps(payload, separators=(',', ':')).encode('utf-8'),
        method='POST',
        headers={'Accept': 'application/json', 'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            print(response.read().decode('utf-8', 'replace'))
    except error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')[:1000]
        raise SystemExit(f'Render deploy failed: HTTP {exc.code} {raw}') from exc

if __name__ == '__main__':
    main()
