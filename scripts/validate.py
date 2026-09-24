#!/usr/bin/env python3
import json, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; errors=[]
required=['## Purpose','## Inputs','## Workflow','## Checks','## Deliverables','## Evidence Gate','## Stop Conditions','## Safety']
names=[]
for p in sorted((ROOT/'skills').glob('*/SKILL.md')):
    s=p.read_text()
    m=re.match(r'^---\n(.*?)\n---\n',s,re.S)
    if not m: errors.append(f'{p}: missing YAML frontmatter'); continue
    fields={x.split(':',1)[0].strip():x.split(':',1)[1].strip() for x in m.group(1).splitlines() if ':' in x}
    name=fields.get('name'); names.append(name)
    if name!=p.parent.name: errors.append(f'{p}: name mismatch')
    for h in required:
        if h not in s: errors.append(f'{p}: missing {h}')
    if len(s)<1800: errors.append(f'{p}: insufficient detail')
if len(names)!=len(set(names)): errors.append('Duplicate skill name')
for p in (ROOT/'schemas').glob('*.json'):
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'{p}: invalid JSON: {e}')
for p in [ROOT/'templates'/'project-config.example.json',ROOT/'templates'/'verification-plan.example.json']:
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'{p}: invalid JSON: {e}')
r=subprocess.run([sys.executable,str(ROOT/'scripts'/'sync_adapters.py'),'--check'],capture_output=True,text=True)
if r.returncode: errors.append(r.stderr.strip() or r.stdout.strip())
unsafe=[r'curl\s',r'wget\s',r'rm\s+-rf',r'--dangerously-skip-permissions',r'child_process',r'shell\s*=\s*True']
for p in list((ROOT/'scripts').glob('*'))+list((ROOT/'skills').glob('*/SKILL.md')):
    if not p.is_file() or p.name == 'validate.py': continue
    s=p.read_text(errors='ignore')
    for pat in unsafe:
        if re.search(pat,s,re.I): errors.append(f'{p}: unsafe pattern {pat}')
if errors:
    print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); raise SystemExit(1)
print(f'Validation OK: {len(names)} skills, {len(list((ROOT/"schemas").glob("*.json")))} schemas, adapter parity confirmed.')
