"""Static tests for the Cupel organisation (standard library only).

Run with: python3 -m unittest discover -s orgs/cupel/tests -v

The positive tests run the real checkers against the repository. The negative
tests copy the Cupel tree into a temporary directory, break one thing, and
require the checker to fail; a checker that cannot fail is not a check.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "orgs" / "cupel"
TOOLS = CORE / "tools"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _copy_tree(dst):
    """Copy the parts of the repository the Cupel checkers read into dst."""
    for rel in ("orgs/cupel", ".claude/agents/cupel"):
        shutil.copytree(ROOT / rel, dst / rel)
    for rel in ("CLAUDE.md", "AGENTS.md"):
        shutil.copy2(ROOT / rel, dst / rel)
    for rel in ("schemas", "skills", "scripts", "docs", "templates", "tests"):
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, dst / rel, ignore=shutil.ignore_patterns("__pycache__"))


def _run(script, cwd, *args):
    return subprocess.run([sys.executable, str(script), *args], cwd=cwd, capture_output=True, text=True)


class CupelPositiveTests(unittest.TestCase):
    def test_check_parity_ok(self):
        r = _run(TOOLS / "check_parity.py", ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 28 cards, 28 copies, 5 schemas", r.stdout)

    def test_validate_cupel_ok(self):
        r = _run(TOOLS / "validate_cupel.py", ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Cupel validation OK", r.stdout)

    def test_manifest_shape(self):
        m = json.loads((CORE / "cupel.json").read_text())
        self.assertEqual(m["organization_id"], "cupel")
        self.assertEqual(len(m["faces"]), 28)
        self.assertEqual(len(m["departments"]), 14)
        self.assertEqual(len(m["offices"]), 3)
        self.assertEqual(sorted(m["face_classes"]), ["drafting", "marshal", "office", "review", "runner", "steward"])

    def test_examples_validate(self):
        v = _load("validate_cupel")
        for ex in sorted((CORE / "examples").glob("*.example.json")):
            schema = json.loads((CORE / "schemas" / ex.name.replace(".example.json", ".schema.json")).read_text())
            inst = json.loads(ex.read_text())
            self.assertEqual(v.validate_instance(inst, schema, schema), [], ex.name)

    def test_law_is_verbatim_in_marshal_chamber_vault(self):
        v = _load("validate_cupel")
        law, anchor = v.law_texts()
        self.assertTrue(law and anchor)
        for face in ("case-marshal", "challenge-chamber", "evidence-vault"):
            self.assertIn(law, (CORE / "agents" / f"{face}.md").read_text(), face)
        for card in (CORE / "agents").glob("*.md"):
            self.assertIn(anchor, card.read_text(), card.name)

    def test_only_runner_and_steward_have_bash(self):
        m = json.loads((CORE / "cupel.json").read_text())
        for f in m["faces"]:
            text = (CORE / "agents" / f"{f['face']}.md").read_text()
            tools_line = [ln for ln in text.splitlines() if ln.startswith("tools:")][0]
            if f["class"] in ("runner", "steward"):
                self.assertIn("Bash", tools_line, f["face"])
            else:
                self.assertNotIn("Bash", tools_line, f["face"])
            if f["class"] == "marshal":
                self.assertEqual(tools_line, "tools: Agent")
            else:
                self.assertNotIn("Agent", tools_line, f["face"])


class CupelNegativeTests(unittest.TestCase):
    def test_parity_detects_mirror_drift(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            _copy_tree(dst)
            victim = dst / ".claude" / "agents" / "cupel" / "coverage-desk.md"
            victim.write_text(victim.read_text() + "\n<!-- drift -->\n")
            r = _run(dst / "orgs" / "cupel" / "tools" / "check_parity.py", dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("mirror copy differs", r.stderr)

    def test_parity_detects_missing_copy_and_stray(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            _copy_tree(dst)
            (dst / ".claude" / "agents" / "cupel" / "threat-desk.md").rename(dst / ".claude" / "agents" / "cupel" / "stray.md")
            r = _run(dst / "orgs" / "cupel" / "tools" / "check_parity.py", dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("mirror copy missing", r.stderr)
            self.assertIn("stray file", r.stderr)
            self.assertTrue((dst / ".claude" / "agents" / "cupel" / "stray.md").exists(), "checker must never delete")

    def test_parity_rejects_extra_frontmatter_key(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            _copy_tree(dst)
            card = dst / "orgs" / "cupel" / "agents" / "load-bench.md"
            text = card.read_text().replace("tools: Read, Grep, Glob\n", "tools: Read, Grep, Glob\nmodel: fast\n", 1)
            card.write_text(text)
            (dst / ".claude" / "agents" / "cupel" / "load-bench.md").write_text(text)
            r = _run(dst / "orgs" / "cupel" / "tools" / "check_parity.py", dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("frontmatter key not allowed", r.stderr)

    def test_parity_rejects_bash_on_review_face(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            _copy_tree(dst)
            card = dst / "orgs" / "cupel" / "agents" / "threat-desk.md"
            text = card.read_text().replace("tools: Read, Grep, Glob\n", "tools: Read, Grep, Glob, Bash\n", 1)
            card.write_text(text)
            (dst / ".claude" / "agents" / "cupel" / "threat-desk.md").write_text(text)
            r = _run(dst / "orgs" / "cupel" / "tools" / "check_parity.py", dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("tools", r.stderr)

    def test_validate_detects_law_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            _copy_tree(dst)
            law = dst / "orgs" / "cupel" / "docs" / "law.md"
            law.write_text(law.read_text().replace("never by how much has been thought", "rarely by how much has been thought"))
            r = _run(dst / "orgs" / "cupel" / "tools" / "validate_cupel.py", dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("law", r.stderr)

    def test_validate_detects_pointer_block_drift(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            _copy_tree(dst)
            claude_md = dst / "CLAUDE.md"
            claude_md.write_text(claude_md.read_text().replace("Default mode is read-only.", "Default mode is read-write."))
            r = _run(dst / "orgs" / "cupel" / "tools" / "validate_cupel.py", dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("pointer block differs", r.stderr)

    def test_schema_validator_rejects_bad_instances(self):
        v = _load("validate_cupel")
        schema = json.loads((CORE / "schemas" / "dissent-ledger-entry.schema.json").read_text())
        good = json.loads((CORE / "examples" / "dissent-ledger-entry.example.json").read_text())
        self.assertEqual(v.validate_instance(good, schema, schema), [])
        bad_id = dict(good, id="C-1/DL-TestbenchWorks-3")
        self.assertTrue(any("does not match" in e for e in v.validate_instance(bad_id, schema, schema)))
        missing = {k: val for k, val in good.items() if k != "discriminating_command"}
        self.assertTrue(any("missing required" in e for e in v.validate_instance(missing, schema, schema)))
        extra = dict(good, verdict="PASS")
        self.assertTrue(any("additional property" in e for e in v.validate_instance(extra, schema, schema)))
        downgraded = dict(good, verbatim=False)
        self.assertTrue(any("const" in e for e in v.validate_instance(downgraded, schema, schema)))


if __name__ == "__main__":
    unittest.main()
