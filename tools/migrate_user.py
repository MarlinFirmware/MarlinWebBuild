#!/usr/bin/env python3
"""
Bring a user's configuration to the Marlin version they asked to build.

  migrate_user.py <marlin_git_dir> <target_ref> <in_dir> <out_dir> [<target_label>]

Uses Marlin's own buildroot/share/scripts/config-migrate.py (from bugfix-2.1.x in
the same clone, so the newest rename rules apply) to find the stock files the
user started from, then:

  - same stock files as the target: copies the files unchanged (no migration)
  - older stock files:              migrates them to the target, writes report.txt
  - newer than the target:          refuses (only upgrades are offered)

Writes the files to build with to <out_dir> and prints a JSON summary:
  {"base": "2.0.9.5 to 2.0.9.13", "base_sha": "...", "migrated": true, "counts": {"Conflicts ...": 2, ...}}
"base" names the releases whose stock files match the user's starting point.
Needs a full clone with tags (a bare clone is fine); exits non-zero with a message
for the user if the files can't be matched to any Marlin version.
"""

import importlib.util, json, re, subprocess, sys, tempfile
from pathlib import Path

SCRIPT = 'buildroot/share/scripts/config-migrate.py'
SCRIPT_REF = 'bugfix-2.1.x'
FILES = ('Configuration.h', 'Configuration_adv.h')
RELEASE_RE = re.compile(r'^(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?$')
VER_RE = re.compile(r'#define\s+CONFIGURATION_(?:ADV_)?H_VERSION\s+(\w+)')

def load_migrator(repo):
    src = subprocess.run(['git', '-C', str(repo), 'show', f'{SCRIPT_REF}:{SCRIPT}'],
                         check=True, capture_output=True, text=True).stdout
    tmp = Path(tempfile.mkdtemp()) / 'config_migrate.py'
    tmp.write_text(src)
    spec = importlib.util.spec_from_file_location('config_migrate', tmp)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def config_version(text):
    """CONFIGURATION_H_VERSION as written (e.g. "02010300"), or None."""
    m = VER_RE.search(text or '')
    return m.group(1) if m and m.group(1).isdigit() else None

def base_label(git, base, files, fallback):
    """Release tags with the same stock files as base, as "2.0.9.5" or "2.0.9.5 to 2.0.9.13"."""
    tags = [fallback] + list(git.same_tags(base, ['Marlin/' + f for f in files]))
    rel = sorted({t for t in tags if RELEASE_RE.match(t)}, key=lambda t: tuple(int(n or 0) for n in RELEASE_RE.match(t).groups()))
    if not rel: return fallback
    return rel[0] if len(rel) == 1 else f'{rel[0]} to {rel[-1]}'

def main(argv):
    if len(argv) not in (4, 5): sys.exit(__doc__)
    repo, target_ref, ind, outd = Path(argv[0]), argv[1], Path(argv[2]), Path(argv[3])
    cm = load_migrator(repo)
    git = cm.Git(str(repo))
    git.check()

    user = {}
    for f in FILES:
        p = ind / f
        if p.is_file():
            t = p.read_text(encoding='utf-8', errors='replace')
            if t.strip(): user[f] = t
    if not user: sys.exit('No `Configuration.h` was found.')
    target = git.rev(target_ref)

    # Only upgrades: a configuration made for a newer Marlin can't be built with an older one
    for f, t in user.items():
        uv, tv = config_version(t), config_version(git.show(target, 'Marlin/' + f))
        if uv and tv and int(uv) > int(tv):
            sys.exit(f'Your `{f}` is from a newer Marlin (`CONFIGURATION_H_VERSION` {uv}) than the version you chose '
                     f'(`{tv}`). Choose a newer Marlin version, or `bugfix-2.1.x`.')

    try:
        base, score, bases, stock_lines = cm.detect_base(git, user, target)
    except SystemExit:
        sys.exit("Your configuration files couldn't be matched to any Marlin version, so they can't be "
                 "migrated. Make sure they're Marlin's `Configuration.h` and `Configuration_adv.h`.")

    blabel = git.describe(base)
    shown = base_label(git, base, list(user), blabel)
    same = all(git.run('rev-parse', f'{bases[f]}:Marlin/{f}', check=False).stdout.strip()
               == git.run('rev-parse', f'{target}:Marlin/{f}', check=False).stdout.strip() for f in user)

    outd.mkdir(parents=True, exist_ok=True)
    summary = {'base': shown, 'base_sha': base, 'score': score, 'migrated': not same, 'counts': {}}
    if same:
        for f, t in user.items(): (outd / f).write_text(t, encoding='utf-8', newline='')
    else:
        report = cm.Report()
        tlabel = argv[4] if len(argv) == 5 else git.describe(target)
        for f, b in bases.items():
            if b != base:
                report.add('Warnings', f'{f} matches {git.describe(b)} better than {blabel}; used that as its base')
        out = cm.migrate_texts(git, user, bases, target, report, blabel, tlabel, stock_lines)
        for f, t in out.items(): (outd / f).write_text(t, encoding='utf-8', newline='')
        header = [f'Base:   {shown} ({base[:10]})', f'Target: {tlabel} ({target[:10]})']
        (outd / 'report.txt').write_text(report.text(header), encoding='utf-8')
        summary['counts'] = {k: len(v) for k, v in report.sections.items()}
    print(json.dumps(summary))

if __name__ == '__main__':
    main(sys.argv[1:])
