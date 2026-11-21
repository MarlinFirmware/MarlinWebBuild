#!/usr/bin/env python3
"""
Pick test builds that show which Marlin versions still build with today's tools.

  matrix.py <site_dir> [all | VERSION ...]   -> GitHub Actions matrix JSON

For each offered version (all by default), picks one example configuration per
platform family, using its default env. Needs the index files from build_site.py.
"""

import json, re, sys
from pathlib import Path

FAMILIES = {
    'avr':     r'^(mega2560|megaatmega2560)$',
    'stm32f1': r'^STM32F103R',
    'stm32f4': r'^(BIGTREE_SKR_PRO|BIGTREE_GTR_V1_0|STM32F407VE_black)',
    'lpc176x': r'^LPC176[89]$',
}

def pick_versions(listing, how):
    names = [v['version'] for v in listing]
    return names if how in ([], ['all']) else [n for n in names if n in how]

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
