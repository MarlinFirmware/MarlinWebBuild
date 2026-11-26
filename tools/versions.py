#!/usr/bin/env python3
"""
Marlin versions offered by the builder.

The builder offers bugfix-2.1.x plus the latest patch release of each maintained
series. A series is maintained if Marlin has an "lts-<series>" branch for it
(e.g. lts-2.1.2), and its latest patch release is the newest Marlin tag in that
series (e.g. 2.1.2.10). Series older than OLDEST don't build with PlatformIO 6.
Beta tags are never offered.

Example configurations come from the first Configurations ref that exists:
  release-<tag>     branch, e.g. release-2.1.2.10
  latest-<series>   tag, e.g. latest-2.0.7
  release-<series>  branch, e.g. release-2.1.1 (release-2.1 for the 2.1.0 series)

  versions.py list              -> JSON list of offered versions, newest first
  versions.py refs <version>    -> "marlin_ref configs_ref" for an offered version
"""

import json, re, subprocess, sys

MARLIN_URL = 'https://github.com/MarlinFirmware/Marlin'
CONFIGS_URL = 'https://github.com/MarlinFirmware/Configurations'
BUGFIX = 'bugfix-2.1.x'
OLDEST = (2, 0, 7)

RELEASE_RE = re.compile(r'^(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?$')   # No betas
LTS_RE = re.compile(r'^lts-(\d+\.\d+\.\d+)$')

def parse(version):
    """Release version -> sortable (major, minor, patch, sub), or None."""
    m = RELEASE_RE.match(version)
    return tuple(int(n or 0) for n in m.groups()) if m else None

def looks_valid(version):
    """Cheap name check before any network lookup."""
    return version == BUGFIX or parse(version) is not None

def ls_remote(url):
    """{'tags': {name: sha}, 'heads': {name: sha}}. Annotated tags resolve to their commit."""
    out = subprocess.run(['git', 'ls-remote', '--tags', '--heads', url],
                         check=True, capture_output=True, text=True).stdout
    refs = {'tags': {}, 'heads': {}}
    for line in out.splitlines():
        sha, ref = line.split('\t')
        _, kind, name = ref.split('/', 2)
        if name.endswith('^{}'):
            refs[kind][name[:-3]] = sha   # Peeled tag wins
        else:
            refs[kind].setdefault(name, sha)
    return refs

def configs_ref(tag, series, cfg):
    """(Configurations ref, SHA) for a release tag, or None."""
    base = series[:-2] if series.endswith('.0') else series   # Series "2.1.0" -> "release-2.1"
    for kind, name in (('heads', f'release-{tag}'), ('tags', f'latest-{series}'), ('heads', f'release-{base}')):
        if name in cfg[kind]: return name, cfg[kind][name]
    return None

def available():
    """Offered versions, bugfix first, then releases newest first."""
    mar, cfg = ls_remote(MARLIN_URL), ls_remote(CONFIGS_URL)
    out = []
    if BUGFIX in mar['heads'] and BUGFIX in cfg['heads']:
        out.append({'version': BUGFIX, 'release': False, 'marlin_ref': BUGFIX, 'configs_ref': BUGFIX,
                    'marlin': mar['heads'][BUGFIX], 'configs': cfg['heads'][BUGFIX]})
    rels = []
    for m in map(LTS_RE.match, mar['heads']):
        if not m: continue
        series = m.group(1)
        skey = parse(series)
        if skey[:3] < OLDEST: continue
        tags = [t for t in mar['tags'] if (parse(t) or ())[:3] == skey[:3]]
        if not tags: continue
        tag = max(tags, key=parse)
        c = configs_ref(tag, series, cfg)
        if not c: continue
        rels.append({'version': tag, 'release': True, 'series': series, 'marlin_ref': tag,
                     'configs_ref': c[0], 'marlin': mar['tags'][tag], 'configs': c[1]})
    # The newest bugfix-line release has no lts-* branch. latest-<line>.x marks it:
    # any release tag on the same commit (e.g. 2.1.3 on latest-2.1.x) is offered too.
    for lat in ('latest-2.1.x',):
        sha = mar['tags'].get(lat)
        for tag, tsha in mar['tags'].items():
            if tsha != sha or not parse(tag) or any(v['version'] == tag for v in rels): continue
            c = configs_ref(tag, tag, cfg)
            if c: rels.append({'version': tag, 'release': True, 'series': tag, 'marlin_ref': tag,
                               'configs_ref': c[0], 'marlin': tsha, 'configs': c[1]})
    return out + sorted(rels, key=lambda v: parse(v['version']), reverse=True)

def refs(version, offered=None):
    """Offered version name -> (Marlin ref, Configurations ref), or None."""
    if not looks_valid(version): return None
    for v in available() if offered is None else offered:
        if v['version'] == version: return v['marlin_ref'], v['configs_ref']
    return None

def main(argv):
    if argv == ['list']:
        print(json.dumps(available(), indent=1))
    elif len(argv) == 2 and argv[0] == 'refs':
        r = refs(argv[1])
        if not r: sys.exit(f"`{argv[1][:64]}` is not a Marlin version this builder offers.")
        print(*r)
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main(sys.argv[1:])
