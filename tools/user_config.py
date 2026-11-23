#!/usr/bin/env python3
"""
Fetch, unpack and check the configuration a user attached to a build request.

  user_config.py fetch <url> <out_dir>    download the zip from an issue attachment, unpack, check
  user_config.py check <dir>              check files already on disk

Writes the accepted files to <out_dir> and prints a JSON summary. Exits non-zero
with a message suitable for posting back to the user if anything is wrong.

An uploaded configuration is compiled on our runner, and a compiler can be made to
read files from the build machine (#include, #embed, asm(".incbin ...")) and put
them in the firmware we publish. So only these preprocessor directives are allowed:
define, undef, if, ifdef, ifndef, elif, else, endif, error, warning, plus the exact
lines stock files use: "#pragma once" and "#include <avr/pgmspace.h>". Outside of
comments and strings, token pasting (##), asm and _Pragma are not allowed either.

Each Configuration.h on the import-2.1.x branch of MarlinFirmware/Configurations
(the repo's default branch, so a common download) has two #error lines that stop
the build. They're removed, and the summary has "import": true so the user can be told.
"""

import io, json, re, sys, urllib.request, zipfile
from pathlib import Path

ALLOWED_FILES = ('Configuration.h', 'Configuration_adv.h', '_Bootscreen.h', '_Statusscreen.h')
REQUIRED_FILE = 'Configuration.h'
MAX_ZIP = 4 << 20          # Downloaded zip
MAX_FILE = 2 << 20         # Each unpacked file (bitmaps can be large)
MAX_TOTAL = 6 << 20        # All unpacked files

URL_RE = re.compile(r'https://github\.com/user-attachments/files/\d+/[\w.()+-]+\.zip')

DIRECTIVES = {'define', 'undef', 'if', 'ifdef', 'ifndef', 'elif', 'else', 'endif', 'error', 'warning'}
EXACT_LINES = {'#pragma once', '#include <avr/pgmspace.h>'}
BANNED = [(re.compile(r'##|%:%:'), 'token pasting (##)'),
          (re.compile(r'\b(?:__)?asm(?:__)?\b'), 'inline assembly (asm)'),
          (re.compile(r'\b_Pragma\b'), '_Pragma'),
          (re.compile(r'\?\?[=/\'()!<>-]'), 'a trigraph'),
          (re.compile(r'\bincbin\b', re.I), '.incbin')]

IMPORT_ERROR_RE = re.compile(r"""\s*#\s*error\s+"(?:Don't build with import-|Use the 'bugfix\.\.\.' or 'release\.\.\.' configurations)""")

class Rejected(Exception): pass

def find_urls(text):
    return list(dict.fromkeys(URL_RE.findall(text or '')))

def download(url):
    if not URL_RE.fullmatch(url): raise Rejected('The attachment link must be a GitHub file attachment ending in `.zip`.')
    req = urllib.request.Request(url, headers={'User-Agent': 'MarlinWebBuild'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(MAX_ZIP + 1)
    if len(data) > MAX_ZIP: raise Rejected(f'The zip is larger than {MAX_ZIP >> 20} MB. Include only the configuration files.')
    return data

def unpack(data):
    """{name: text} for the allowed files in the zip. Folders inside the zip are ignored."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Rejected("The attachment isn't a valid zip file.")
    files, ignored, total = {}, [], 0
    for info in z.infolist():
        if info.is_dir(): continue
        name = info.filename.replace('\\', '/').rsplit('/', 1)[-1]
        if info.filename.startswith('__MACOSX/') or name.startswith('._') or name == '.DS_Store': continue
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise Rejected(f'`{name}` in the zip is a symbolic link. Zip the files themselves.')
        if name not in ALLOWED_FILES:
            ignored.append(info.filename); continue
        if name in files: raise Rejected(f'The zip has more than one `{name}`. Include one set of configuration files.')
        if info.file_size > MAX_FILE: raise Rejected(f'`{name}` is larger than {MAX_FILE >> 20} MB.')
        total += info.file_size
        if total > MAX_TOTAL: raise Rejected('The files in the zip are too large.')
        with z.open(info) as fh: raw = fh.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE: raise Rejected(f'`{name}` is larger than {MAX_FILE >> 20} MB.')
        if raw.startswith(b'\xef\xbb\xbf'): raw = raw[3:]
        try: text = raw.decode('utf-8')
        except UnicodeDecodeError: text = raw.decode('latin-1')
        files[name] = text
    if REQUIRED_FILE not in files:
        raise Rejected(f'No `{REQUIRED_FILE}` was found in the zip. Zip your `Configuration.h` and `Configuration_adv.h`.')
    return files, ignored

def strip_code(text):
    """Text with comments and string/char literals blanked, line structure kept."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i); j = n if j < 0 else j
            i = j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2); j = n if j < 0 else j + 2
            out.append('\n' * text.count('\n', i, j) or ' '); i = j
        elif c in '"\'':
            j = i + 1
            while j < n and text[j] != c and text[j] != '\n':
                j += 2 if text[j] == '\\' else 1
            out.append(c + c); i = j + 1
        else:
            out.append(c); i += 1
    return ''.join(out)

def check_text(name, text):
    code = strip_code(re.sub(r'\\\r?\n', '', text).replace('\r\n', '\n'))   # Splice continued lines like cpp does
    for lineno, line in enumerate(code.split('\n'), 1):
        s = line.strip()
        m = re.match(r'(?:#|%:)\s*(\w*)', s)
        if m:
            d = m.group(1)
            if d not in DIRECTIVES and ' '.join(s.replace('%:', '#', 1).split()) not in EXACT_LINES:
                raise Rejected(f'`{name}` line {lineno}: `#{d}` is not allowed in an uploaded configuration.')
        for rx, what in BANNED:
            if rx.search(line):
                raise Rejected(f'`{name}` line {lineno}: {what} is not allowed in an uploaded configuration.')
    if 'incbin' in text.lower():
        raise Rejected(f'`{name}`: .incbin is not allowed in an uploaded configuration.')

def check_files(files):
    for name, text in files.items(): check_text(name, text)

def strip_import(files):
    """Remove the import-2.1.x #error lines from Configuration.h. True if there were any."""
    lines = files.get(REQUIRED_FILE, '').splitlines(keepends=True)
    kept = [l for l in lines if not IMPORT_ERROR_RE.match(l)]
    if len(kept) == len(lines): return False
    files[REQUIRED_FILE] = ''.join(kept)
    return True

def save(files, out):
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text, encoding='utf-8', newline='')

def main(argv):
    try:
        if len(argv) == 3 and argv[0] == 'fetch':
            files, ignored = unpack(download(argv[1]))
            check_files(files)
            imported = strip_import(files)
            save(files, Path(argv[2]))
        elif len(argv) == 2 and argv[0] == 'check':
            d = Path(argv[1])
            files = {f: (d / f).read_text(errors='replace') for f in ALLOWED_FILES if (d / f).is_file()}
            ignored = []
            check_files(files)
            imported = strip_import(files)
        else:
            sys.exit(__doc__)
    except Rejected as e:
        sys.exit(str(e))
    except OSError as e:
        sys.exit(f"The attachment couldn't be downloaded ({e}).")
    print(json.dumps({'files': sorted(files), 'ignored': ignored[:20], 'import': imported}))

if __name__ == '__main__':
    main(sys.argv[1:])
