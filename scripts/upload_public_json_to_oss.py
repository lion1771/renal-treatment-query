#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request
from urllib.parse import quote, urlsplit, urlunparse

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
        if not sep:
            continue
        key = key.strip()
        if not ENV_KEY_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)

def main() -> None:
    load_env_file(PROJECT_ROOT / '.env.upload')
    parser = argparse.ArgumentParser(description='Upload compiled_public/*.json to Aliyun OSS.')
    parser.add_argument('--dir', default='compiled_public')
    parser.add_argument('--bucket', default=os.getenv('ALIYUN_OSS_BUCKET', 'renal'))
    parser.add_argument('--region', default=os.getenv('ALIYUN_OSS_REGION', 'cn-hongkong'))
    parser.add_argument('--endpoint', default=os.getenv('ALIYUN_OSS_ENDPOINT', 'https://oss-cn-hongkong.aliyuncs.com'))
    parser.add_argument('--prefix', default=os.getenv('COMPILED_DATA_OSS_PREFIX', 'public/renal-treatment-query/compiled_public'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    access_key_id = env_first('ALIYUN_OSS_UPLOAD_ACCESS_KEY_ID', 'ALIYUN_OSS_ACCESS_KEY_ID')
    access_key_secret = env_first('ALIYUN_OSS_UPLOAD_ACCESS_KEY_SECRET', 'ALIYUN_OSS_ACCESS_KEY_SECRET')
    security_token = env_first('ALIYUN_OSS_UPLOAD_SECURITY_TOKEN', 'ALIYUN_OSS_SECURITY_TOKEN')
    data_dir = (PROJECT_ROOT / args.dir).resolve()
    files = sorted(data_dir.glob('*.json'))
    if not files:
        raise SystemExit(f'No JSON files found in {data_dir}')
    if not args.dry_run and (not access_key_id or not access_key_secret):
        raise SystemExit('Missing OSS upload credentials in .env.upload or environment.')
    base_url = build_object_url(args.endpoint, args.bucket, args.prefix.strip('/') + '/manifest.json').removesuffix('/manifest.json')
    print(f'BASE_URL={base_url}')
    for path in files:
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        object_key = f"{args.prefix.strip('/')}/{path.name}"
        url = build_object_url(args.endpoint, args.bucket, object_key)
        print(f'{path.name}\t{len(data)}\t{sha}\t{url}')
        if args.dry_run:
            continue
        req = build_put_request(
            data=data, url=url, region=args.region, bucket=args.bucket, object_key=object_key,
            access_key_id=access_key_id, access_key_secret=access_key_secret, security_token=security_token,
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                print(f'uploaded {path.name}: HTTP {response.status}')
        except error.HTTPError as exc:
            raw = exc.read().decode('utf-8', 'replace')[:1000]
            raise SystemExit(f'Upload failed for {path.name}: HTTP {exc.code} {raw}') from exc

def env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name, '').strip()
        if value:
            return value
    return ''

def build_put_request(*, data: bytes, url: str, region: str, bucket: str, object_key: str, access_key_id: str, access_key_secret: str, security_token: str = '') -> request.Request:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y%m%dT%H%M%SZ')
    headers = {
        'Content-Length': str(len(data)),
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'public, max-age=300',
        'x-oss-content-sha256': 'UNSIGNED-PAYLOAD',
        'x-oss-date': timestamp,
    }
    if security_token:
        headers['x-oss-security-token'] = security_token
    headers['Authorization'] = build_v4_authorization(
        method='PUT', canonical_uri=uri_encode(f'/{bucket}/{object_key}', encode_slash=False),
        canonical_query='', headers=headers, additional_header_names=['content-length', 'content-type', 'cache-control'],
        payload_hash='UNSIGNED-PAYLOAD', access_key_id=access_key_id, access_key_secret=access_key_secret,
        region=region, timestamp=timestamp,
    )
    return request.Request(url=url, data=data, headers=headers, method='PUT')

def build_object_url(endpoint: str, bucket: str, object_key: str) -> str:
    parsed = urlsplit(endpoint.strip().rstrip('/'))
    if not parsed.scheme:
        parsed = urlsplit(f"https://{endpoint.strip().rstrip('/')}")
    host = parsed.netloc
    netloc = host if host == bucket or host.startswith(f'{bucket}.') else f'{bucket}.{host}'
    path = '/' + uri_encode(object_key, encode_slash=False)
    return urlunparse((parsed.scheme or 'https', netloc, path, '', '', ''))

def build_v4_authorization(*, method: str, canonical_uri: str, canonical_query: str, headers: dict[str, str], additional_header_names: list[str], payload_hash: str, access_key_id: str, access_key_secret: str, region: str, timestamp: str) -> str:
    date = timestamp[:8]
    additional_header_names = sorted({name.lower() for name in additional_header_names})
    lower_headers = {name.lower(): normalize_header(value) for name, value in headers.items()}
    signed_header_names = sorted(name for name in lower_headers if name.startswith('x-oss-') or name in {'content-type', 'content-md5'} or name in additional_header_names)
    canonical_headers = ''.join(f'{name}:{lower_headers[name]}\n' for name in signed_header_names)
    canonical_additional_headers = ';'.join(additional_header_names)
    canonical_request = f'{method.upper()}\n{canonical_uri}\n{canonical_query}\n{canonical_headers}\n{canonical_additional_headers}\n{payload_hash}'
    hashed_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    scope = f'{date}/{region}/oss/aliyun_v4_request'
    string_to_sign = f'OSS4-HMAC-SHA256\n{timestamp}\n{scope}\n{hashed_request}'
    signature = hmac.new(signing_key(access_key_secret, date, region), string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    authorization = f'OSS4-HMAC-SHA256 Credential={access_key_id}/{scope}'
    if canonical_additional_headers:
        authorization += f',AdditionalHeaders={canonical_additional_headers}'
    return f'{authorization},Signature={signature}'

def signing_key(access_key_secret: str, date: str, region: str) -> bytes:
    key = hmac.new(f'aliyun_v4{access_key_secret}'.encode('utf-8'), date.encode('utf-8'), hashlib.sha256).digest()
    key = hmac.new(key, region.encode('utf-8'), hashlib.sha256).digest()
    key = hmac.new(key, b'oss', hashlib.sha256).digest()
    return hmac.new(key, b'aliyun_v4_request', hashlib.sha256).digest()

def uri_encode(value: str, encode_slash: bool) -> str:
    return quote(value, safe='-_.~' if encode_slash else '/-_.~')

def normalize_header(value: str) -> str:
    return re.sub(r'\s+', ' ', value.strip())

if __name__ == '__main__':
    main()
