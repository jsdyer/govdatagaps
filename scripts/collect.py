#!/usr/bin/env python3
"""Capture public CKAN metadata and bounded resource availability observations."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://open.canada.ca/data/en/api/3/action/package_show?'
UA = 'CoolCodeGovDataGaps/1.0 (+https://coolcode.ca/govdatagaps/; public metadata monitor)'
MAX_BYTES = 4_000_000


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def public_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('Only public HTTP(S) URLs on standard ports are checked')
    if p.hostname == 'localhost' or p.hostname.endswith(('.localhost', '.local', '.internal')) or '.' not in p.hostname:
        raise ValueError('Local destination is not checked')
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError('Non-public address is not checked')
    return url


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = build_opener(PublicRedirect())


def request(url, method='GET', headers=None):
    public_url(url)
    return OPENER.open(Request(url, method=method, headers={'User-Agent': UA, **(headers or {})}), timeout=20)


def classify_status(code):
    if 200 <= code < 400:
        return 'reachable'
    if code in (404, 410):
        return 'unavailable'
    if code in (401, 403, 429):
        return 'blocked'
    return 'inconclusive'


def check_resource(url):
    result = {'checked_at': stamp(), 'method': 'HEAD', 'status': 'inconclusive', 'http_status': None, 'final_url': url}
    try:
        try:
            response = request(url, 'HEAD')
        except HTTPError as exc:
            if exc.code not in (405, 501):
                raise
            result['method'] = 'GET Range 0-0'
            response = request(url, headers={'Range': 'bytes=0-0'})
        with response:
            result.update(status=classify_status(response.status), http_status=response.status, final_url=response.url,
                          content_type=response.headers.get('Content-Type', ''), last_modified=response.headers.get('Last-Modified', ''))
            # No file body is read. A 200 response does not prove a usable dataset.
    except HTTPError as exc:
        result.update(status=classify_status(exc.code), http_status=exc.code, final_url=exc.url,
                      detail=f'HTTP {exc.code}; a point-in-time observation, not proof of deletion.')
    except (URLError, OSError, ValueError) as exc:
        result['detail'] = f'{type(exc).__name__}: {str(exc)[:200]}'
    return result


def english(value):
    if isinstance(value, dict):
        return value.get('en') or value.get('fr') or ''
    return value or ''


def normalize(raw, item, digest):
    resources = []
    for r in raw.get('resources', []):
        resources.append({k: v for k, v in {
            'id': r.get('id', ''), 'name': english(r.get('name_translated')) or r.get('name', ''),
            'url': r.get('url', ''), 'format': r.get('format', ''), 'language': r.get('language', []),
            'last_modified': r.get('last_modified'), 'created': r.get('created')
        }.items()})
    return {**item, 'state': 'present', 'title': english(raw.get('title_translated')) or raw.get('title', item['label']),
            'publisher': english(raw.get('org_title_at_publication')) or english(raw.get('organization', {}).get('title', '')),
            'metadata_modified': raw.get('metadata_modified'), 'dataset_modified': raw.get('date_modified'),
            'frequency': raw.get('frequency', 'unknown'), 'license': raw.get('license_title', raw.get('license_id', '')),
            'source_url': f"https://open.canada.ca/data/en/dataset/{item['id']}",
            'source_api': BASE + urlencode({'id': item['id']}), 'source_sha256': digest, 'resources': resources}


def validate(snapshot):
    if snapshot.get('schema_version') != 1 or not snapshot.get('captured_at') or not snapshot.get('datasets'):
        raise ValueError('Incomplete snapshot')
    ids = [x['id'] for x in snapshot['datasets']]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate dataset IDs')
    for row in snapshot['datasets']:
        if row['state'] not in ('present', 'not_found') or not row.get('source_api'):
            raise ValueError('Invalid dataset state')
        if row['state'] == 'present' and (not row.get('title') or not row.get('source_sha256')):
            raise ValueError('Missing source identity')
        for resource in row.get('resources', []):
            if resource.get('check', {}).get('status', 'not_checked') not in ('reachable', 'unavailable', 'blocked', 'inconclusive', 'not_checked'):
                raise ValueError('Invalid resource observation')


def collect(root=ROOT, check_limit=2):
    items = json.loads((root / 'config/watchlist.json').read_text())
    captured = stamp()
    capture_id = captured.replace(':', '').replace('-', '')
    snapshot = {'schema_version': 1, 'captured_at': captured, 'collector': 'CKAN GET + bounded HTTP resource checks',
                'resource_check_limit_per_dataset': check_limit, 'datasets': []}
    bodies = {}
    # All metadata must be valid before any dated snapshot is written. An upstream
    # outage fails collection and leaves the published history untouched.
    for item in items:
        url = BASE + urlencode({'id': item['id']})
        try:
            with request(url) as response:
                body = response.read(MAX_BYTES + 1)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            body = exc.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Metadata exceeded limit')
        envelope = json.loads(body)
        digest = hashlib.sha256(body).hexdigest()
        bodies[item['id']] = body
        if envelope.get('success') is False and envelope.get('error', {}).get('__type') == 'Not Found Error':
            snapshot['datasets'].append({**item, 'state': 'not_found', 'source_api': url, 'source_sha256': digest,
                'source_url': f"https://open.canada.ca/data/en/dataset/{item['id']}", 'resources': []})
        elif envelope.get('success') is True and envelope.get('result', {}).get('id') == item['id']:
            snapshot['datasets'].append(normalize(envelope['result'], item, digest))
        else:
            raise ValueError(f"Invalid or unsuccessful metadata response for {item['id']}")
        print(f"Metadata: {item['label']}", flush=True)
        time.sleep(0.4)
    for row in snapshot['datasets']:
        # Deterministic sample: downloadable formats first, English first, then ID.
        priority = lambda r: (r['format'].lower() not in ('csv', 'json', 'xml', 'xlsx', 'zip'), 'en' not in r.get('language', []), r['id'])
        selected = sorted(row['resources'], key=priority)[:check_limit]
        for resource in row['resources']:
            resource['check'] = check_resource(resource['url']) if resource in selected else {'status': 'not_checked'}
            if resource in selected:
                print(f"Resource: {row['label']} / {resource['format']}: {resource['check']['status']}", flush=True)
                time.sleep(0.4)
    validate(snapshot)
    data = root / 'web/data'
    manifest_path = data / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'schema_version': 1, 'captures': []}
    if any(c['id'] == capture_id for c in manifest['captures']):
        raise ValueError('Capture already exists; never overwrite history')
    folder = data / 'snapshots' / capture_id
    folder.mkdir(parents=True, exist_ok=False)
    for key, body in bodies.items():
        (folder / f'{key}.json').write_bytes(body)
    for row in snapshot['datasets']:
        row['raw_file'] = f"./data/snapshots/{capture_id}/{row['id']}.json"
    (folder / 'snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    manifest['captures'].append({'id': capture_id, 'captured_at': captured, 'file': f'./data/snapshots/{capture_id}/snapshot.json', 'dataset_count': len(items)})
    manifest['captures'].sort(key=lambda c: c['captured_at'], reverse=True)
    manifest['captured_at'] = captured
    manifest['dataset_count'] = len(items)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f"Saved {capture_id}: {len(items)} datasets", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-limit', type=int, default=2)
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    if args.validate:
        files = list((ROOT / 'web/data/snapshots').glob('*/snapshot.json'))
        if not files:
            raise SystemExit('No captured data')
        for path in files:
            validate(json.loads(path.read_text()))
        print(f'Validated {len(files)} snapshots')
    else:
        if not 0 <= args.check_limit <= 5:
            parser.error('check limit must be 0–5')
        collect(check_limit=args.check_limit)
