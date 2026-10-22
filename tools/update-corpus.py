#!/usr/bin/env python3
"""Refresh the bundled three.js documentation corpus for a new release.

Usage (from the threejs-skills/ folder):

    python3 tools/update-corpus.py                 # latest npm version
    python3 tools/update-corpus.py 0.187.0         # explicit version
    python3 tools/update-corpus.py --dry-run       # download + report only

What it does:
  1. Downloads from threejs.org: docs index + every API page, manual list +
     pages, TSL guide, TSL function reference, search.json; the migration guide
     from the GitHub wiki; examples/files.json from the GitHub r<N> tag, docs/llms.txt.
  2. Converts HTML to markdown (stdlib only) and rebuilds:
       threejs/references/api/*.md, api-index.txt, examples-index.md
       threejs-tsl-webgpu/references/tsl-reference.md, tsl-guide/*.md
       tools/corpus/manual/*.md, tools/corpus/migration.md, tools/corpus/llms.txt
  3. Prints a change report: added/removed API pages, new migration-guide
     entries, and every file that still mentions the old version string.

After running it, follow UPDATING.md (review the report, re-digest affected
reference files, bump version strings, re-run evals).
"""
import json, os, re, shutil, sys, urllib.request, concurrent.futures as cf
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, 'threejs', 'references')
TSL = os.path.join(ROOT, 'threejs-tsl-webgpu', 'references')
CORPUS = os.path.join(ROOT, 'tools', 'corpus')
DRY = '--dry-run' in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith('--')]

def get(url, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'threejs-skills-updater'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode('utf-8', 'replace')

# ---------- version ----------
version = args[0] if args else json.loads(get('https://registry.npmjs.org/three/latest'))['version']
rev = version.split('.')[1]
print(f'Target: three@{version} (r{rev})')

# ---------- HTML -> markdown ----------
class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.out = []; s.pre = 0; s.skip = 0; s.href = None
    def handle_starttag(s, t, a):
        a = dict(a)
        if t in ('script', 'style', 'nav'): s.skip += 1; return
        if s.skip: return
        if t in ('h1', 'h2', 'h3', 'h4'): s.out.append('\n\n' + '#' * int(t[1]) + ' ')
        elif t == 'p': s.out.append('\n\n')
        elif t == 'br': s.out.append('\n')
        elif t == 'pre': s.pre += 1; s.out.append('\n\n```js\n')
        elif t == 'code' and not s.pre: s.out.append('`')
        elif t == 'li': s.out.append('\n- ')
        elif t == 'tr': s.out.append('\n| ')
        elif t in ('td', 'th'): s.out.append(' ')
        elif t == 'a': s.href = a.get('href')
        elif t in ('strong', 'b'): s.out.append('**')
        elif t in ('em', 'i'): s.out.append('*')
        elif t == 'div' and 'class' in a and 'desc' not in a['class']: s.out.append('\n')
        elif t == 'table': s.out.append('\n')
    def handle_endtag(s, t):
        if t in ('script', 'style', 'nav'): s.skip -= 1; return
        if s.skip: return
        if t == 'pre': s.pre -= 1; s.out.append('\n```\n')
        elif t == 'code' and not s.pre: s.out.append('`')
        elif t in ('td', 'th'): s.out.append(' |')
        elif t in ('strong', 'b'): s.out.append('**')
        elif t in ('em', 'i'): s.out.append('*')
        elif t == 'a':
            h = s.href; s.href = None
            if h and h.startswith('http'): s.out.append(f' ({h})')
    def handle_data(s, d):
        if s.skip: return
        s.out.append(d if s.pre else re.sub(r'\s+', ' ', d))

def h2md(html):
    x = P(); x.feed(html); t = ''.join(x.out)
    t = re.sub(r'[ \t]+\n', '\n', t); t = re.sub(r'\n{3,}', '\n\n', t); t = re.sub(r'\| +', ' | ', t)
    return t.strip() + '\n'

# ---------- download ----------
docs_index = get('https://threejs.org/docs/')
pages = sorted(set(re.findall(r'href="([^"#]*)\.html(?:#[^"]*)?"', docs_index)))
pages = [p for p in pages if '/' not in p]
print(f'API pages listed: {len(pages)}')

def fetch_page(name):
    try: return name, get(f'https://threejs.org/docs/pages/{name}.html')
    except Exception as e: return name, None
with cf.ThreadPoolExecutor(16) as ex:
    api_html = dict(ex.map(fetch_page, pages))
missing = [k for k, v in api_html.items() if v is None]
if missing: print('WARNING: failed pages:', missing)

manual_list = json.loads(get('https://threejs.org/manual/list.json'))
manual_slugs = sorted({s.split('#')[0] for sec in manual_list.values() for s in sec.values()})
def fetch_manual(slug):
    try: return slug, get(f'https://threejs.org/manual/pages/{slug}.html')
    except Exception: return slug, None
with cf.ThreadPoolExecutor(16) as ex:
    manual_html = dict(ex.map(fetch_manual, manual_slugs))

tsl_guide = get('https://threejs.org/tsl/content/Guide.md')
migration = get('https://raw.githubusercontent.com/wiki/mrdoob/three.js/Migration-Guide.md')
files_json = json.loads(get(f'https://raw.githubusercontent.com/mrdoob/three.js/r{rev}/examples/files.json'))
llms = get('https://threejs.org/docs/llms.txt')

# ---------- build ----------
cat = {}; sec = grp = None
for m in re.finditer(r'<h2>([^<]*)</h2>|<h3>([^<]*)</h3>|<a href="([^"#]*)\.html(?:#[^"]*)?">([^<]*)</a>', docs_index):
    if m.group(1): sec = m.group(1).strip(); grp = None
    elif m.group(2): grp = m.group(2).strip()
    elif m.group(3) and m.group(3) not in cat: cat[m.group(3)] = (sec, grp)

api_md = {k: h2md(v) for k, v in api_html.items() if v}
index_lines = []
for page, (s, g) in sorted(cat.items(), key=lambda x: (x[1][0] or '', x[1][1] or '', x[0])):
    if page not in api_md or page in ('TSL', 'Global'): continue
    t = api_md[page]
    inh = re.search(r'^(.*?) →\s*$', t, re.M)
    inh = inh.group(1).replace(' → ', ' > ').strip() if inh else ''
    d = re.search(r'^# [^\n]*\n+([^\n#][^\n]*)', t, re.M); d = re.sub(r'\s+', ' ', d.group(1).strip())[:220] if d else ''
    index_lines.append(f'{s} / {g} | {page}' + (f' (extends {inh.split(" > ")[-1]})' if inh else '') + f' | {d}')

ex_lines = [f'# three.js r{rev} examples (https://threejs.org/examples/#<name>, source: examples/<name>.html)']
for k, v in files_json.items():
    ex_lines.append(f'\n## {k} ({len(v)})\n'); ex_lines += [f'- {x}' for x in v]

parts = re.split(r'<page name="([^"]*)">', tsl_guide)
guide_files = []; top = None; i = 1
while i < len(parts):
    name, body = parts[i], parts[i + 1].replace('</page>', '').strip(); i += 2
    if not body: top = name; continue
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    guide_files.append((top, name, f'{len(guide_files) + 1:02d}-{slug}.md', f'# {name}\n\n(TSL Guide section: {top} > {name})\n\n{body}\n'))

# ---------- report ----------
old_index = set()
p = os.path.join(CORE, 'api-index.txt')
if os.path.exists(p):
    old_index = {l.split(' | ')[1].split(' (')[0] for l in open(p) if ' | ' in l}
new_index = {l.split(' | ')[1].split(' (')[0] for l in index_lines}
print(f'\nAPI pages: {len(new_index)} (added {len(new_index - old_index)}, removed {len(old_index - new_index)})')
if new_index - old_index: print('  added:', ', '.join(sorted(new_index - old_index)))
if old_index - new_index: print('  removed:', ', '.join(sorted(old_index - new_index)))
old_mig = os.path.join(CORPUS, 'migration.md')
if os.path.exists(old_mig):
    old_heads = set(re.findall(r'^## .*', open(old_mig).read(), re.M))
    new_heads = [h for h in re.findall(r'^## .*', migration, re.M) if h not in old_heads]
    print('New migration-guide sections:', new_heads or 'none')
print(f'TSL guide sections: {len(guide_files)}; manual pages: {len(manual_html)}; examples: {sum(len(v) for v in files_json.values())}')

old_versions = set()
for dp, _, fs in os.walk(ROOT):
    if '/references/api' in dp or '/tsl-guide' in dp or '/corpus' in dp or '/tools' in dp: continue
    for f in fs:
        if f.endswith('.md') and f != 'versions-and-migration.md':
            txt = open(os.path.join(dp, f), errors='replace').read()
            for v in set(re.findall(r'\b0\.1\d\d\.\d+\b', txt)):
                if v != version: old_versions.add((os.path.relpath(os.path.join(dp, f), ROOT), v))
if old_versions:
    print('\nFiles still mentioning other versions (bump by hand, see UPDATING.md):')
    for f, v in sorted(old_versions): print(f'  {f}: {v}')

if DRY: print('\n--dry-run: nothing written.'); sys.exit(0)

# ---------- write ----------
api_dir = os.path.join(CORE, 'api')
shutil.rmtree(api_dir, ignore_errors=True); os.makedirs(api_dir)
for k, v in api_md.items():
    if k in ('TSL', 'Global'): continue
    open(os.path.join(api_dir, k + '.md'), 'w').write(v)
open(os.path.join(CORE, 'api-index.txt'), 'w').write('\n'.join(index_lines) + '\n')
open(os.path.join(CORE, 'examples-index.md'), 'w').write('\n'.join(ex_lines) + '\n')
if 'TSL' in api_md: open(os.path.join(TSL, 'tsl-reference.md'), 'w').write(api_md['TSL'])
gd = os.path.join(TSL, 'tsl-guide'); shutil.rmtree(gd, ignore_errors=True); os.makedirs(gd)
for top, name, fn, body in guide_files: open(os.path.join(gd, fn), 'w').write(body)
open(os.path.join(gd, 'INDEX.md'), 'w').write('\n'.join(f'- {t} > {n}: {f}' for t, n, f, _ in guide_files) + '\n')
md = os.path.join(CORPUS, 'manual'); shutil.rmtree(md, ignore_errors=True); os.makedirs(md)
for k, v in manual_html.items():
    if v: open(os.path.join(md, k + '.md'), 'w').write(h2md(v))
open(os.path.join(CORPUS, 'migration.md'), 'w').write(migration)
open(os.path.join(CORPUS, 'llms.txt'), 'w').write(llms)
open(os.path.join(CORPUS, 'VERSION'), 'w').write(version + '\n')
print(f'\nWritten. Corpus now at three@{version}. Next: UPDATING.md.')
