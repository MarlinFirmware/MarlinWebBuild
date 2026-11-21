#!/usr/bin/env python3
"""
Parse a build-request issue body (GitHub issue form markdown) from $ISSUE_BODY.

Writes version=..., config=... and env=... to $GITHUB_OUTPUT (or stdout), or exits non-zero
with a message suitable for posting back to the user.
"""

import os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import versions

FIELDS = {'Marlin version': 'version', 'Configuration': 'config', 'Build environment': 'env'}
PATH_RE = re.compile(r"^[\w .,+&()'-]+(/[\w .,+&()'-]+)*$")
ENV_RE = re.compile(r'^\w+$')

def parse(body):
    out, key = {}, None
    for line in body.replace('\r', '').split('\n'):
        m = re.match(r'^###\s+(.+?)\s*$', line)
        if m:
            key = FIELDS.get(m.group(1))
            continue
        if key and line.strip() and key not in out:
            out[key] = line.strip()
    for k in list(out):
        if out[k] == '_No response_': out[k] = ''
    return out

def main():
    req = parse(os.environ.get('ISSUE_BODY', ''))
    config = req.get('config', '').strip('/ ').strip('`')
    env = req.get('env', '').strip('`')
    version = req.get('version', '').strip('` ') or versions.BUGFIX   # Older requests have no version
    if config.startswith('config/examples/'): config = config[len('config/examples/'):]

    if not versions.is_valid(version):
        sys.exit(f"`{version[:64]}` is not a Marlin version this builder offers. "
                 f"Use `{versions.BUGFIX}` or a release from {'.'.join(map(str, versions.OLDEST))} on.")
    if not config:
        sys.exit("No configuration was given.")
    if len(config) > 200 or not PATH_RE.match(config) or any(p in ('.', '..') for p in config.split('/')):
        sys.exit(f"`{config[:200]}` is not a valid configuration path.")
    if env and (len(env) > 64 or not ENV_RE.match(env)):
        sys.exit(f"`{env[:64]}` is not a valid environment name.")

    dest = os.environ.get('GITHUB_OUTPUT')
    with open(dest, 'a') if dest else sys.stdout as f:
        f.write(f"version={version}\nconfig={config}\nenv={env}\n")

if __name__ == '__main__':
    main()
