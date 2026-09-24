#!/usr/bin/env python3
import argparse, filecmp, shutil, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'skills'
TARGETS=[ROOT/'.claude'/'skills', ROOT/'.agents'/'skills']

def files(base): return {p.relative_to(base):p for p in base.rglob('*') if p.is_file()}

def in_sync(target):
    a,b=files(SOURCE),files(target) if target.exists() else {}
    return a.keys()==b.keys() and all(filecmp.cmp(a[k],b[k],shallow=False) for k in a)

def sync(target):
    if target.exists(): shutil.rmtree(target)
    shutil.copytree(SOURCE,target)

p=argparse.ArgumentParser(); p.add_argument('--check',action='store_true'); a=p.parse_args()
if a.check:
    bad=[str(t.relative_to(ROOT)) for t in TARGETS if not in_sync(t)]
    if bad:
        print('Adapter drift: '+', '.join(bad),file=sys.stderr); raise SystemExit(1)
    print('Adapter parity: OK')
else:
    for t in TARGETS: sync(t)
    print(f'Synchronized {len(list(SOURCE.glob("*/SKILL.md")))} skills to Claude and Codex adapters.')
