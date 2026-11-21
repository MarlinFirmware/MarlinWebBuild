#!/usr/bin/env python3
"""
Build the picker's data files for every offered Marlin version.

  build_site.py <site_dir> [--repo OWNER/NAME] [--only VERSION ...] [--jobs N]

Writes <site_dir>/versions.json and <site_dir>/index/<version>.json.
Each version needs only pins.h and a sparse clone of the Configuration.h files,
so indexing all of them takes well under a minute.
"""

import argparse, json, subprocess, sys, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import marlin_index, versions

RAW = 'https://raw.githubusercontent.com/MarlinFirmware/Marlin/{sha}/Marlin/src/pins/pins.h'

def fetch_pins(sha):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(RAW.format(sha=sha), timeout=60) as r:
                return r.read().decode('utf-8', 'replace').splitlines()
        except OSError:
            if attempt == 2: raise
            time.sleep(5)

def index_version(v, work):
    """Index the example configs of one version. Returns the index document."""
    cfg_ref = v['configs_ref']
    pins = fetch_pins(v['marlin'])
    cfg = Path(work) / 'cfg'
    run = lambda *a: subprocess.run(['git', *a], check=True, capture_output=True)
    run('clone', '-q', '--depth', '1', '--filter=blob:none', '--sparse', '-b', cfg_ref, versions.CONFIGS_URL, str(cfg))
    run('-C', str(cfg), 'sparse-checkout', 'set', '--no-cone', '/config/examples/**/Configuration.h')
    configs_sha = subprocess.run(['git', '-C', str(cfg), 'rev-parse', 'HEAD'],
                                 check=True, capture_output=True, text=True).stdout.strip()
    items = []
    for rel, d in marlin_index.example_dirs(cfg):
        board = marlin_index.board_of(d)
        items.append({'path': rel, 'board': board,
                      'envs': marlin_index.envs_for(None, board, pins) if board else []})
    return {'version': v['version'], 'release': v['release'], 'series': v.get('series'), 'configs_ref': cfg_ref,
            'marlin': v['marlin'], 'configs': configs_sha, 'items': items}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('site')
    ap.add_argument('--repo', default='MarlinFirmware/MarlinWebBuild', help='Repo that takes build requests')
    ap.add_argument('--only', nargs='+', metavar='VERSION')
    ap.add_argument('--jobs', type=int, default=6)
    args = ap.parse_args()

    site = Path(args.site)
    (site / 'index').mkdir(parents=True, exist_ok=True)

    vers = versions.available()
    if args.only: vers = [v for v in vers if v['version'] in args.only]

    def one(v):
        with tempfile.TemporaryDirectory() as work:
            doc = index_version(v, work)
        doc['generated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        return doc

    results, failed = [], []
    with ThreadPoolExecutor(args.jobs) as ex:
        futures = [(v, ex.submit(one, v)) for v in vers]
        for v, f in futures:
            try:
                doc = f.result()
            except Exception as e:  # One broken branch shouldn't take the whole site down
                failed.append(v['version'])
                print(f"{v['version']}: FAILED ({e})", file=sys.stderr)
                continue
            print(f"{v['version']}: {len(doc['items'])} configs", file=sys.stderr)
            results.append(doc)

    for doc in results:
        (site / 'index' / f"{doc['version']}.json").write_text(json.dumps(doc, separators=(',', ':')))

    listing = [{'version': d['version'], 'release': d['release'], 'series': d['series'], 'marlin': d['marlin'],
                'configs': d['configs'], 'count': len(d['items']), 'generated': d['generated']}
               for d in results]
    (site / 'versions.json').write_text(json.dumps({
        'repo': args.repo,
        'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'default': versions.BUGFIX,
        'versions': listing,
    }, separators=(',', ':')))
    print(f"{len(results)} versions indexed, {len(failed)} failed", file=sys.stderr)
    if not results or (versions.BUGFIX not in [d['version'] for d in results] and not args.only):
        sys.exit("bugfix index missing")

if __name__ == '__main__':
    main()
