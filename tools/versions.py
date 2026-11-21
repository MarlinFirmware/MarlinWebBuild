#!/usr/bin/env python3
"""
Marlin versions offered by the builder.

A version is either the bugfix branch or a Marlin release tag (2.0.0 or newer)
that has a matching "release-<tag>" branch in MarlinFirmware/Configurations.
Beta tags (e.g. 2.1.3-b1) are left out: they pin library branches that no longer exist.

  versions.py list              -> JSON list of buildable versions, newest first
  versions.py refs <version>    -> "marlin_ref configs_ref" for a valid version name

"refs" only checks the name. Whether the refs exist is checked by cloning them.
"""

import json, re, subprocess, sys

MARLIN_URL = 'https://github.com/MarlinFirmware/Marlin'
CONFIGS_URL = 'https://github.com/MarlinFirmware/Configurations'
BUGFIX = 'bugfix-2.1.x'
OLDEST = (2, 0, 0)

VERSION_RE = re.compile(r'^(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-b(\d+))?$')

def parse(version):
    """Release version -> sortable key, or None if not a release version name."""
    m = VERSION_RE.match(version)
    if not m: return None
    nums = tuple(int(n or 0) for n in m.groups()[:4])
    beta = m.group(5)
    # A beta sorts before the release it leads up to
    return nums + ((0, int(beta)) if beta else (1, 0))

def is_valid(version):
    if version == BUGFIX: return True
    key = parse(version)
    return key is not None and key[:3] >= OLDEST and key[4] == 1   # No betas

def refs(version):
    """Version name -> (Marlin ref, Configurations ref)."""
    if version == BUGFIX: return BUGFIX, BUGFIX
    return version, f'release-{version}'

def ls_remote(url, kind):
    """Ref name -> commit SHA for refs/<kind>/*. Annotated tags resolve to their commit."""
    out = subprocess.run(['git', 'ls-remote', f'--{kind}', url],
                         check=True, capture_output=True, text=True).stdout
    shas = {}
    for line in out.splitlines():
        sha, ref = line.split('\t')
        name = ref.split('/', 2)[2]
        if name.endswith('^{}'):
            shas[name[:-3]] = sha   # peeled tag wins
        else:
            shas.setdefault(name, sha)
    return shas

def available():
    """All buildable versions, bugfix first, then releases newest first."""
    tags = ls_remote(MARLIN_URL, 'tags')
    heads = ls_remote(MARLIN_URL, 'heads')
    cfg = ls_remote(CONFIGS_URL, 'heads')
    out = []
    if BUGFIX in heads and BUGFIX in cfg:
        out.append({'version': BUGFIX, 'release': False,
                    'marlin': heads[BUGFIX], 'configs': cfg[BUGFIX]})
    rel = [t for t in tags if is_valid(t) and t != BUGFIX and f'release-{t}' in cfg]
    for t in sorted(rel, key=parse, reverse=True):
        out.append({'version': t, 'release': True,
                    'marlin': tags[t], 'configs': cfg[f'release-{t}']})
    return out

def main(argv):
    if argv == ['list']:
        print(json.dumps(available(), indent=1))
    elif len(argv) == 2 and argv[0] == 'refs':
        if not is_valid(argv[1]):
            sys.exit(f"`{argv[1][:64]}` is not a Marlin version this builder offers.")
        print(*refs(argv[1]))
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main(sys.argv[1:])
