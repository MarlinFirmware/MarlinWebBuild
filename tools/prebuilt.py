#!/usr/bin/env python3
"""
Fetch a firmware file already published in MarlinFirmware/MarlinBuilds, so a request
for a stock example at a release doesn't need a build.

  prebuilt.py <version> <config> <env> <out_dir>

MarlinBuilds tags each drop with the Marlin release it was built from (e.g. 2.1.2.8),
built from the unmodified examples of Configurations `release-<version>`, with one folder
per example and PlatformIO env:

  builds/<config>/<env>/<name>.zip              the firmware file, zipped
  builds/<config>/<env>/<name>.<ext>.sha256.txt its SHA-256 (the last 64 hex digits in the file;
                                                older drops hold a literal "<config>\\n<sha>")

Unpacks the firmware into <out_dir>, checks its SHA-256, and prints
  {"tag": "2.1.2.8", "files": ["firmware.hex"], "url": "https://github.com/.../tree/2.1.2.8/builds/..."}
Exits 2 when there's no prebuilt firmware for the request (build it instead), and
1 on anything unexpected (also: build it instead).
"""

import hashlib, io, json, os, re, sys, zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = 'MarlinFirmware/MarlinBuilds'
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+(\.\d+)?$')
FIRMWARE_RE = re.compile(r'^[A-Za-z0-9_.-]+\.(bin|hex|srec|uf2)$')
MAX_ZIP = 8 << 20       # Bytes: firmware zips are well under 1 MB
MAX_FILE = 16 << 20     # Unpacked bytes

def get(url, api=False):
    headers = {'User-Agent': 'MarlinWebBuild'}
    if api:
        headers['Accept'] = 'application/vnd.github+json'
        if os.environ.get('GH_TOKEN'): headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urlopen(Request(url, headers=headers), timeout=60) as r:
        data = r.read(MAX_ZIP + 1)
    if len(data) > MAX_ZIP: raise ValueError(f'{url} is too large')
    return data

def none(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)

def main(argv):
    if len(argv) != 4: sys.exit(__doc__)
    version, config, env, out = argv[0], argv[1].strip('/'), argv[2], Path(argv[3])
    if not VERSION_RE.match(version): none(f'No prebuilt firmware for {version} (not a release)')
    if any(p in ('', '.', '..') for p in config.split('/')) or not re.match(r'^[A-Za-z0-9_.-]+$', env):
        none('Unexpected configuration or env name')

    path = f'builds/{config}/{env}'
    api = f'https://api.github.com/repos/{REPO}/contents/{quote(path)}?ref={quote(version)}'
    try:
        listing = json.loads(get(api, api=True))
    except HTTPError as e:
        if e.code == 404: none(f'No prebuilt firmware for {config} / {env} at {version}')
        raise
    if not isinstance(listing, list): none(f'{path} is not a folder')

    names = {f['name']: f for f in listing if f.get('type') == 'file'}
    zips = [n for n in names if n.endswith('.zip')]
    if len(zips) != 1: none(f'Expected one firmware zip in {path}, found {len(zips)}')

    data = get(names[zips[0]]['download_url'])
    files = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir(): continue
            name = info.filename
            if not FIRMWARE_RE.match(name): raise ValueError(f'Unexpected file {name!r} in {zips[0]}')
            if info.file_size > MAX_FILE: raise ValueError(f'{name} is too large')
            blob = z.read(info)
            sums = names.get(name + '.sha256.txt')
            if not sums: raise ValueError(f'No {name}.sha256.txt next to {zips[0]}')
            want = re.findall(r'[0-9a-fA-F]{64}', get(sums['download_url']).decode())
            if not want: raise ValueError(f'No SHA-256 in {name}.sha256.txt')
            want = want[-1].lower()
            if hashlib.sha256(blob).hexdigest() != want: raise ValueError(f'{name} does not match its SHA-256')
            out.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(blob)
            files.append(name)
    if not files: raise ValueError(f'{zips[0]} is empty')

    print(json.dumps({'tag': version, 'files': files,
                      'url': f'https://github.com/{REPO}/tree/{quote(version)}/{quote(path)}'}))

if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except SystemExit:
        raise
    except Exception as e:
        print(f'Prebuilt firmware not usable: {e}', file=sys.stderr)
        sys.exit(1)
