#!/usr/bin/env python3
import argparse, hashlib, json, shutil, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def safe_target(raw):
    p=Path(raw).expanduser().resolve()
    if p==Path.home().resolve() or p==Path('/').resolve(): raise ValueError('Refusing home/root target')
    return p

def plan(target,harness):
    items=[]
    if harness in ('claude','all'):
        items.append((ROOT/'CLAUDE.md',target/'CLAUDE.md'))
        for s in (ROOT/'.claude'/'skills').glob('*/SKILL.md'): items.append((s,target/'.claude'/'skills'/s.parent.name/'SKILL.md'))
    if harness in ('codex','all'):
        items.append((ROOT/'AGENTS.md',target/'AGENTS.md'))
        for s in (ROOT/'.agents'/'skills').glob('*/SKILL.md'): items.append((s,target/'.agents'/'skills'/s.parent.name/'SKILL.md'))
    cfg=target/'.soc-dv'/'config.json'
    if not cfg.exists(): items.append((ROOT/'templates'/'project-config.example.json',cfg))
    return items

p=argparse.ArgumentParser(description='Project-local installer')
p.add_argument('--target',required=True); p.add_argument('--harness',choices=['claude','codex','all'],default='all')
p.add_argument('--dry-run',action='store_true'); p.add_argument('--force',action='store_true'); a=p.parse_args()
try: target=safe_target(a.target)
except ValueError as e: print(e,file=sys.stderr); raise SystemExit(2)
items=plan(target,a.harness)
conflicts=[dst for src,dst in items if dst.exists() and digest(src)!=digest(dst)]
if conflicts and not a.force:
    print('Refusing to overwrite existing files:',file=sys.stderr)
    for x in conflicts: print('  '+str(x),file=sys.stderr)
    print('Review them or rerun with --force.',file=sys.stderr); raise SystemExit(3)
for src,dst in items:
    print(f'{src.relative_to(ROOT)} -> {dst}')
    if not a.dry_run:
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
if not a.dry_run:
    manifest={'stack_version':(ROOT/'VERSION').read_text().strip(),'harness':a.harness,'files':[{'path':str(dst.relative_to(target)),'sha256':digest(dst)} for src,dst in items]}
    mp=target/'.soc-dv'/'install-manifest.json'; mp.parent.mkdir(parents=True,exist_ok=True); mp.write_text(json.dumps(manifest,indent=2)+'\n')
    print('Installed project-local stack. Review .soc-dv/install-manifest.json.')
