#!/usr/bin/env python3
"""Look up three.js r186 API docs offline.

  api.py Mesh                 # print full doc page for class/module
  api.py Mesh InstancedMesh   # several pages
  api.py -s instanc           # search index (name + description, case-insensitive)
  api.py -m Mesh raycast      # only the section matching 'raycast' in Mesh page
"""
import sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, '..', 'references', 'api')
IDX = os.path.join(HERE, '..', 'references', 'api-index.txt')

def page(name):
    p = os.path.join(API, name + '.md')
    if not os.path.exists(p):
        p = os.path.join(API, 'module-' + name + '.md')
    if not os.path.exists(p):
        hits = [f[:-3] for f in os.listdir(API) if name.lower() in f.lower()]
        return f'No page "{name}". Close matches: {", ".join(sorted(hits)[:20]) or "none"}\n'
    return open(p).read()

args = sys.argv[1:]
if not args or args[0] in ('-h', '--help'):
    print(__doc__); sys.exit(0)
if args[0] == '-s':
    q = ' '.join(args[1:]).lower()
    for line in open(IDX):
        if q in line.lower(): print(line, end='')
elif args[0] == '-m':
    name, q = args[1], ' '.join(args[2:]).lower()
    t = page(name)
    for sec in re.split(r'\n(?=### )', t):
        if q in sec.lower(): print(sec.strip(), '\n')
else:
    for n in args: print(page(n))
