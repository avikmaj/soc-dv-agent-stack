import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class StackTests(unittest.TestCase):
    def test_adapters_match(self):
        for src in (ROOT/'skills').glob('*/SKILL.md'):
            for base in [ROOT/'.claude'/'skills',ROOT/'.agents'/'skills']:
                dst=base/src.parent.name/'SKILL.md'
                self.assertTrue(dst.exists()); self.assertEqual(src.read_bytes(),dst.read_bytes())
    def test_json(self):
        for p in list((ROOT/'schemas').glob('*.json'))+list((ROOT/'templates').glob('*.json')): json.loads(p.read_text())
    def test_bootstrap_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([sys.executable,str(ROOT/'scripts'/'bootstrap.py'),'--target',d,'--harness','all','--dry-run'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr); self.assertFalse((Path(d)/'AGENTS.md').exists())
    def test_bootstrap_install(self):
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([sys.executable,str(ROOT/'scripts'/'bootstrap.py'),'--target',d,'--harness','all'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr); self.assertTrue((Path(d)/'.soc-dv/install-manifest.json').exists())
    def test_runner_rejects_escape(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.soc-dv/config.json'; p.parent.mkdir(); p.write_text(json.dumps({'tools':{'x':{'argv':['echo','x'],'cwd':'../../'}}}))
            r=subprocess.run([sys.executable,str(ROOT/'scripts'/'run_tool.py'),'--config',str(p),'--tool','x','--dry-run'],capture_output=True,text=True)
            self.assertEqual(r.returncode,4)
if __name__=='__main__': unittest.main()
