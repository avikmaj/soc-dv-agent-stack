#!/usr/bin/env python3
import argparse, json, os, subprocess, sys
from pathlib import Path

p=argparse.ArgumentParser(description='Run an approved project tool without a shell')
p.add_argument('--config',required=True); p.add_argument('--tool',required=True); p.add_argument('--dry-run',action='store_true'); a=p.parse_args()
cp=Path(a.config).expanduser().resolve(); cfg=json.loads(cp.read_text()); root=(cp.parent.parent if cp.parent.name=='.soc-dv' else cp.parent).resolve()
t=cfg.get('tools',{}).get(a.tool)
if not t: print(f'Unknown tool: {a.tool}',file=sys.stderr); raise SystemExit(2)
argv=t.get('argv');
if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv): print('Tool argv must be a non-empty string array',file=sys.stderr); raise SystemExit(3)
cwd=(root/t.get('cwd','.')).resolve()
try: cwd.relative_to(root)
except ValueError: print('Tool cwd escapes project root',file=sys.stderr); raise SystemExit(4)
allow=set(cfg.get('environment_allowlist',[])); env={k:v for k,v in os.environ.items() if k in allow}
print(json.dumps({'argv':argv,'cwd':str(cwd),'timeout_seconds':t.get('timeout_seconds',3600)},indent=2))
if a.dry_run: raise SystemExit(0)
r=subprocess.run(argv,cwd=cwd,env=env,shell=False,timeout=int(t.get('timeout_seconds',3600)),check=False)
raise SystemExit(r.returncode)
