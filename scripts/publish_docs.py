"""Publish only this project's wiki pages; never log credentials."""
import importlib.util
import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--snapshot-dir', type=Path, help='Read remote pages into private reconciliation snapshots; no writes')
parser.add_argument('--baseline-dir', type=Path, help='Snapshots reviewed before local edits; abort if remote changed')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wiki_client', '/home/dean/Projects/WikiStream/scripts/wikistream_api.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
config = json.loads((ROOT / 'wikistream.json').read_text())
os.environ['WIKISTREAM_URL'] = config['url']
token = client.load_token(ROOT)
opener = build_opener(client.NoRedirect())


def call(path, method='GET', body=None, authenticated=True):
    headers = {'Content-Type': 'application/json'}
    if authenticated:
        headers['Authorization'] = 'Bearer ' + token
    req = Request(config['url'].rstrip('/') + path, method=method, headers=headers,
                  data=json.dumps(body).encode() if body is not None else None)
    with opener.open(req, timeout=15) as response:
        return json.load(response)


assert call('/health', authenticated=False)['status'] == 'ok'
projects = call('/api/projects')
project = next((p for p in projects if p['slug'] == config['slug']), None)
if args.snapshot_dir:
    args.snapshot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if project:
        for metadata in project['pages']:
            page = call('/api/pages/' + str(metadata['id']))
            path = args.snapshot_dir / (page['slug'] + '.json')
            path.write_text(json.dumps(page))
            path.chmod(0o600)
            print(page['slug'], 'snapshot version', page['version'])
    raise SystemExit(0)
if project is None:
    project = call('/api/projects', 'POST', {k: config[k] for k in ('name', 'slug', 'description')})
    project['pages'] = []
manifest = {
    'overview': ('Overview', 'Getting started'), 'architecture': ('Architecture & tools', 'Infrastructure'),
    'deployment': ('Deployment & configuration', 'Infrastructure'), 'data-and-recovery': ('Data, backup & recovery', 'Infrastructure'),
    'usage': ('Usage & examples', 'Getting started'), 'api': ('API & integrations', 'Reference'),
    'verification': ('Tests & verification', 'Verification'), 'troubleshooting': ('Operations & troubleshooting', 'Operations'),
    'changelog': ('Documentation change log', 'Reference')}
for slug, (title, section) in manifest.items():
    desired = dict(title=title, section=section, content=(ROOT / config['documentation_directory'] / (slug + '.md')).read_text())
    metadata = next((p for p in project['pages'] if p['slug'] == slug), None)
    if metadata:
        current = call('/api/pages/' + str(metadata['id']))
        if all(current[k] == v for k, v in desired.items()):
            print(slug, 'unchanged', current['id'])
            continue
        baseline_path = args.baseline_dir / (slug + '.json') if args.baseline_dir else None
        if not baseline_path or not baseline_path.exists():
            raise SystemExit('Existing remote page differs: ' + slug + '. Read and reconcile before publishing.')
        baseline = json.loads(baseline_path.read_text())
        if any(current[k] != baseline[k] for k in ('title', 'section', 'content', 'version')):
            raise SystemExit('Remote changed after reconciliation: ' + slug + '. Fetch and merge again.')
        saved = call('/api/pages/' + str(current['id']), 'PATCH', dict(version=current['version'], **desired))
        verified = call('/api/pages/' + str(saved['id']))
        assert all(verified[k] == v for k, v in desired.items())
        print(slug, 'updated and verified', saved['id'], 'version', verified['version'])
        continue
    saved = call('/api/projects/' + str(project['id']) + '/pages', 'POST', dict(slug=slug, **desired))
    verified = call('/api/pages/' + str(saved['id']))
    assert all(verified[k] == v for k, v in desired.items())
    print(slug, 'published and verified', saved['id'])
