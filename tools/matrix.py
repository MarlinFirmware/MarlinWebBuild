#!/usr/bin/env python3
"""
Pick test builds that show which Marlin versions still build with today's tools.

  matrix.py <site_dir> [all | sample | VERSION ...]   -> GitHub Actions matrix JSON

For each version, picks one example configuration per platform family, using
its default env. "sample" (the default) takes the oldest and newest release of
each x.y.z series plus bugfix. Needs the index files from build_site.py.
"""

import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import versions

FAMILIES = {
    'avr':     r'^(mega2560|megaatmega2560)$',
    'stm32f1': r'^STM32F103R',
    'stm32f4': r'^(BIGTREE_SKR_PRO|BIGTREE_GTR_V1_0|STM32F407VE_black)',
    'lpc176x': r'^LPC176[89]$',
}

def series(v):
    k = versions.parse(v)
    return k[:3] if k else (v,)

def pick_versions(listing, how):
    names = [v['version'] for v in listing]
    if how == ['all']: return names
    if how and how != ['sample']: return [n for n in names if n in how]
    groups = {}
    for n in names: groups.setdefault(series(n), []).append(n)   # listing is newest first
    out = []
    for g in groups.values():
        out += [g[0]] if len(g) == 1 else [g[0], g[-1]]
    return out

def main(argv):
    if not argv: sys.exit(__doc__)
    site = Path(argv[0])
    listing = json.loads((site / 'versions.json').read_text())['versions']
    include = []
    for name in pick_versions(listing, argv[1:]):
        idx = json.loads((site / 'index' / f'{name}.json').read_text())
        for fam, pat in FAMILIES.items():
            it = next((i for i in idx['items'] if i['envs'] and re.search(pat, i['envs'][0])), None)
            if it:
                include.append({'version': name, 'family': fam, 'config': it['path'], 'env': it['envs'][0],
                                'marlin': idx['marlin'], 'configs': idx['configs']})
    print(json.dumps({'include': include}, separators=(',', ':')))

if __name__ == '__main__':
    main(sys.argv[1:])
