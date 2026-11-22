#!/usr/bin/env python3
"""
Parse a build-request issue body (GitHub issue form markdown) from $ISSUE_BODY.

Writes version=..., marlin_ref=..., configs_ref=..., mode=..., config=..., upload=... and env=...
to $GITHUB_OUTPUT (or stdout), or exits non-zero with a message suitable for posting back to the user.

mode=example builds an example from MarlinFirmware/Configurations (config=<path>).
mode=upload builds the user's own files, attached as a zip (upload=<attachment URL>).
"""

import os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import versions, user_config

FIELDS = {'Marlin version': 'version', 'Configuration': 'config', 'Build environment': 'env',
          'Configuration files': 'files'}
MULTILINE = {'files'}
PATH_RE = re.compile(r"^[\w .,+&()'-]+(/[\w .,+&()'-]+)*$")
ENV_RE = re.compile(r'^\w+$')

def parse(body):
    out, key = {}, None
    for line in body.replace('\r', '').split('\n'):
        m = re.match(r'^###\s+(.+?)\s*$', line)
        if m:
            key = FIELDS.get(m.group(1))
            continue
        if key in MULTILINE:
            out[key] = (out.get(key, '') + '\n' + line).strip()
        elif key and line.strip() and key not in out:
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

    offered = versions.available() if versions.looks_valid(version) else []
    refs = versions.refs(version, offered)
    if not refs:
        names = ', '.join(f"`{v['version']}`" for v in offered) or f"`{versions.BUGFIX}` or the latest patch release of a series"
        sys.exit(f"`{version[:64]}` is not a Marlin version this builder offers. Choose one of: {names}.")
    mode, upload = ('upload' if 'files' in req else 'example'), ''
    if mode == 'upload':
        urls = user_config.find_urls(req.get('files'))
        if not urls:
            sys.exit("No zip file was attached. Zip your `Configuration.h` and `Configuration_adv.h`, "
                     "then open a new request and drag the zip into the *Configuration files* box.")
        if len(urls) > 1:
            sys.exit("More than one zip was attached. Put all the configuration files in one zip.")
        upload, config = urls[0], ''
    elif not config:
        sys.exit("No configuration was given.")
    if mode == 'example' and (len(config) > 200 or not PATH_RE.match(config) or any(p in ('.', '..') for p in config.split('/'))):
        sys.exit(f"`{config[:200]}` is not a valid configuration path.")
    if env and (len(env) > 64 or not ENV_RE.match(env)):
        sys.exit(f"`{env[:64]}` is not a valid environment name.")

    dest = os.environ.get('GITHUB_OUTPUT')
    with open(dest, 'a') if dest else sys.stdout as f:
        f.write(f"version={version}\nmarlin_ref={refs[0]}\nconfigs_ref={refs[1]}\n"
                f"mode={mode}\nconfig={config}\nupload={upload}\nenv={env}\n")

if __name__ == '__main__':
    main()
