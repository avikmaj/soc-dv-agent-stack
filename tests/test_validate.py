"""Unit tests for scripts/validate.py (WS3-A: fail-closed repository validation with a skills lock).

Run: python -m unittest tests.test_validate -v

Every test other than the real-repository smoke test works inside its own temporary directory with
synthetic content; nothing in the repository is written by these tests.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("validate_under_test", ROOT / "scripts" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate = _load()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_text(path: Path, text: str) -> None:
    _write_bytes(path, text.encode("utf-8"))


def _symlink_or_skip(case: unittest.TestCase, target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:  # Windows without the symlink privilege, exotic filesystems
        case.skipTest(f"cannot create symbolic links on this host: {exc}")


def _valid_skill_body(headings=None) -> str:
    headings = validate.REQUIRED_HEADINGS if headings is None else headings
    filler = "This section provides enough substantive detail to satisfy the minimum evidence threshold. " * 2
    parts = []
    for heading in headings:
        parts.append(f"## {heading}\n\n{filler}\n")
    return "\n".join(parts)


def _valid_skill_md(name: str, description: str = "Validate example skill body content.",
                     version: str = "1.0.0", headings=None) -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\nversion: {version}\n---\n\n"
        f"# {name}\n\n{_valid_skill_body(headings)}"
    )


def _write_schema(root: Path, name: str) -> None:
    _write_text(root / "schemas" / name, json.dumps({"type": "object"}))


def _write_template(root: Path, name: str) -> None:
    _write_text(root / "templates" / name, json.dumps({"example": True}))


def _make_root(tmp: Path, skill_names=("sample-skill",), skill_md_by_name=None) -> Path:
    """A minimal fully-valid tree: skills/<name>/SKILL.md for each name, matching skills.lock,
    every required schema and template. No scripts/sync_adapters.py, so adapter parity is skipped."""
    root = tmp / "root"
    skill_md_by_name = skill_md_by_name or {}
    for name in skill_names:
        text = skill_md_by_name.get(name, _valid_skill_md(name))
        _write_text(root / "skills" / name / "SKILL.md", text)
    _write_text(root / "skills.lock", "".join(f"{n}\n" for n in sorted(skill_names)))
    for schema_name in validate.REQUIRED_SCHEMAS:
        _write_schema(root, schema_name)
    for template_name in validate.REQUIRED_TEMPLATES:
        _write_template(root, template_name)
    return root


def _run_main(root: Path):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = validate.main([], root=root)
    return rc, out.getvalue(), err.getvalue()


class TopLevelDirTests(unittest.TestCase):
    def test_missing_skills_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            import shutil
            shutil.rmtree(root / "skills")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: skills: missing", err)
            self.assertIn("Validation FAILED:", err)

    def test_empty_skills_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            import shutil
            shutil.rmtree(root / "skills")
            (root / "skills").mkdir()
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: skills: is empty", err)

    def test_missing_schemas_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            import shutil
            shutil.rmtree(root / "schemas")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: schemas: missing", err)

    def test_empty_schemas_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            import shutil
            shutil.rmtree(root / "schemas")
            (root / "schemas").mkdir()
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: schemas: is empty", err)

    def test_missing_expected_schema(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            (root / "schemas" / "waiver.schema.json").unlink()
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: schemas/waiver.schema.json: missing expected schema", err)

    def test_missing_templates_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            import shutil
            shutil.rmtree(root / "templates")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: templates: missing", err)

    def test_empty_templates_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            import shutil
            shutil.rmtree(root / "templates")
            (root / "templates").mkdir()
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: templates: is empty", err)

    def test_missing_expected_template(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            (root / "templates" / "project-config.example.json").unlink()
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: templates/project-config.example.json: missing expected template", err)


class SkillsLockTests(unittest.TestCase):
    def test_partial_canonical_deletion_while_adapters_remain_in_parity(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d), skill_names=("alpha-skill", "beta-skill", "gamma-skill"))
            import shutil
            # Canonical directory for gamma-skill is deleted...
            shutil.rmtree(root / "skills" / "gamma-skill")
            # ...but both adapter trees still carry a stale, mutually-identical copy of it.
            for adapter in (".claude", ".agents"):
                _write_text(root / adapter / "skills" / "gamma-skill" / "SKILL.md",
                            _valid_skill_md("gamma-skill"))
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("ERROR: skills/gamma-skill: missing skill directory listed in skills.lock", err)

    def test_stray_regular_file_under_skills(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            _write_text(root / "skills" / "README.txt", "not a skill\n")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("stray regular file directly under skills/", err)

    def test_extra_skill_directory_not_in_lock(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            _write_text(root / "skills" / "extra-skill" / "SKILL.md", _valid_skill_md("extra-skill"))
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("skill directory not listed in skills.lock", err)

    def test_skills_lock_duplicate_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            _write_text(root / "skills.lock", "sample-skill\nsample-skill\n")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("duplicate name", err)

    def test_skills_lock_unsorted(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d), skill_names=("bbb-skill", "aaa-skill"))
            _write_text(root / "skills.lock", "bbb-skill\naaa-skill\n")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("sorted in lexical order", err)


class FrontmatterTests(unittest.TestCase):
    def test_missing_frontmatter(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": "# no frontmatter here\n"})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("frontmatter must start at byte 0 with '---'", err)

    def test_utf8_bom(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            content = b"\xef\xbb\xbf" + _valid_skill_md("sample-skill").encode("utf-8")
            _write_bytes(root / "skills" / "sample-skill" / "SKILL.md", content)
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("UTF-8 byte-order mark (BOM) is not allowed", err)

    def test_duplicate_key(self):
        with tempfile.TemporaryDirectory() as d:
            text = ("---\nname: sample-skill\ndescription: first\ndescription: second\nversion: 1.0.0\n---\n\n"
                    + _valid_skill_body())
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("duplicate frontmatter key 'description'", err)

    def test_unknown_key(self):
        with tempfile.TemporaryDirectory() as d:
            text = ("---\nname: sample-skill\ndescription: valid description text\nversion: 1.0.0\n"
                    "extra: not allowed\n---\n\n" + _valid_skill_body())
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("unknown frontmatter key 'extra'", err)

    def test_invalid_name_pattern(self):
        with tempfile.TemporaryDirectory() as d:
            text = _valid_skill_md("sample-skill").replace("name: sample-skill", "name: Sample_Skill")
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("does not match required pattern", err)

    def test_mismatched_name(self):
        with tempfile.TemporaryDirectory() as d:
            text = _valid_skill_md("sample-skill").replace("name: sample-skill", "name: other-skill")
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("does not match directory 'sample-skill'", err)

    def test_missing_description(self):
        with tempfile.TemporaryDirectory() as d:
            text = "---\nname: sample-skill\nversion: 1.0.0\n---\n\n" + _valid_skill_body()
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("missing required key 'description'", err)

    def test_multiline_description_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            text = ("---\nname: sample-skill\ndescription: first line\nsecond line\nversion: 1.0.0\n---\n\n"
                    + _valid_skill_body())
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("malformed frontmatter line", err)

    def test_oversized_description(self):
        with tempfile.TemporaryDirectory() as d:
            long_desc = "x" * 1025
            text = _valid_skill_md("sample-skill", description=long_desc)
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("must be 1-1024 characters", err)

    def test_control_character_description(self):
        with tempfile.TemporaryDirectory() as d:
            text = ("---\nname: sample-skill\ndescription: bad\x01description\nversion: 1.0.0\n---\n\n"
                    + _valid_skill_body())
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("control character", err)

    def test_invalid_version(self):
        with tempfile.TemporaryDirectory() as d:
            text = _valid_skill_md("sample-skill", version="1.0")
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("frontmatter version '1.0' does not match required pattern", err)


class HeadingTests(unittest.TestCase):
    def test_missing_mandatory_heading(self):
        with tempfile.TemporaryDirectory() as d:
            headings = [h for h in validate.REQUIRED_HEADINGS if h != "Safety"]
            text = _valid_skill_md("sample-skill", headings=headings)
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("missing required heading '## Safety'", err)

    def test_heading_text_only_in_paragraph_does_not_satisfy(self):
        with tempfile.TemporaryDirectory() as d:
            headings = [h for h in validate.REQUIRED_HEADINGS if h != "Safety"]
            text = _valid_skill_md("sample-skill", headings=headings)
            text += "\nA paragraph that merely mentions Safety in passing, not as a real heading line.\n"
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("missing required heading '## Safety'", err)

    def test_empty_required_section(self):
        with tempfile.TemporaryDirectory() as d:
            body_headings = list(validate.REQUIRED_HEADINGS)
            filler = "This section provides enough substantive detail to satisfy the minimum evidence threshold. " * 2
            parts = []
            for heading in body_headings:
                if heading == "Safety":
                    parts.append(f"## {heading}\n\n")
                else:
                    parts.append(f"## {heading}\n\n{filler}\n")
            text = (f"---\nname: sample-skill\ndescription: valid description\nversion: 1.0.0\n---\n\n"
                    f"# sample-skill\n\n" + "\n".join(parts))
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("section '## Safety' has no non-blank body content", err)

    def test_incorrect_heading_order(self):
        with tempfile.TemporaryDirectory() as d:
            headings = ["Safety"] + [h for h in validate.REQUIRED_HEADINGS if h != "Safety"]
            text = _valid_skill_md("sample-skill", headings=headings)
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("required headings are out of order", err)


class EncodingTests(unittest.TestCase):
    def test_valid_crlf_and_nonascii_skill(self):
        with tempfile.TemporaryDirectory() as d:
            text = _valid_skill_md("sample-skill", description="Revue en francais: cafe, tres bien, and 日本語.")
            crlf_bytes = text.replace("\n", "\r\n").encode("utf-8")
            root = _make_root(Path(d))
            _write_bytes(root / "skills" / "sample-skill" / "SKILL.md", crlf_bytes)
            rc, out, err = _run_main(root)
            self.assertEqual(rc, 0, err)
            self.assertIn("Validation OK: 1 skills, 4 schemas, adapter parity confirmed.", out)

    def test_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            _write_bytes(root / "skills" / "sample-skill" / "SKILL.md", b"---\nname: sample-skill\xff\n---\n")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("invalid UTF-8", err)

    def test_lone_cr(self):
        with tempfile.TemporaryDirectory() as d:
            text = _valid_skill_md("sample-skill").replace("This section", "This\rsection", 1)
            content = text.encode("utf-8")
            root = _make_root(Path(d))
            _write_bytes(root / "skills" / "sample-skill" / "SKILL.md", content)
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("lone CR line ending is not allowed", err)


class LinkSafetyTests(unittest.TestCase):
    def test_symlinked_skill_md(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            external = Path(d) / "external.md"
            _write_text(external, _valid_skill_md("sample-skill"))
            skill_md = root / "skills" / "sample-skill" / "SKILL.md"
            skill_md.unlink()
            _symlink_or_skip(self, external, skill_md)
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("symbolic link", err)
            self.assertNotIn(str(external), err)

    def test_symlinked_skill_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            external_dir = Path(d) / "external-skill-dir"
            _write_text(external_dir / "SKILL.md", _valid_skill_md("sample-skill"))
            import shutil
            shutil.rmtree(root / "skills" / "sample-skill")
            _symlink_or_skip(self, external_dir, root / "skills" / "sample-skill")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("symbolic link", err)
            self.assertNotIn(str(external_dir), err)

    def test_refused_link_expected_schema_reported_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            external = Path(d) / "external-schema.json"
            _write_text(external, json.dumps({"type": "object"}))
            target_path = root / "schemas" / "waiver.schema.json"
            target_path.unlink()
            _symlink_or_skip(self, external, target_path)
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("schemas/waiver.schema.json: refusing to read", err)
            self.assertNotIn("schemas/waiver.schema.json: missing expected schema", err)

    @unittest.skipUnless(sys.platform == "win32",
                          "Windows junctions (NTFS reparse points) do not exist on this host")
    def test_windows_junction_skill_directory(self):  # pragma: no cover - Windows only
        import _winapi
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            external_dir = Path(d) / "external-junction-dir"
            _write_text(external_dir / "SKILL.md", _valid_skill_md("sample-skill"))
            import shutil
            shutil.rmtree(root / "skills" / "sample-skill")
            try:
                _winapi.CreateJunction(str(external_dir), str(root / "skills" / "sample-skill"))
            except OSError as exc:
                self.skipTest(f"junction creation not permitted for this user: {exc}")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("reparse point", err)


class LegacyUnsafePatternTests(unittest.TestCase):
    """Pre-WS3 unsafe-pattern regex scan (kept behaviorally intact until F7's AST validator lands)."""

    def test_unsafe_pattern_in_script_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            _write_text(root / "scripts" / "helper.py", "import subprocess\nsubprocess.run(cmd, shell=True)\n")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("unsafe pattern", err)

    def test_unsafe_pattern_in_skill_md_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            text = _valid_skill_md("sample-skill") + "\nUse curl https://example.com to fetch things.\n"
            root = _make_root(Path(d), skill_md_by_name={"sample-skill": text})
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 1)
            self.assertIn("unsafe pattern", err)

    def test_unsafe_pattern_exempts_validate_py_itself(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_root(Path(d))
            _write_text(root / "scripts" / "validate.py",
                        "# documentation mentioning shell=True and rm -rf only as examples\n")
            rc, _out, err = _run_main(root)
            self.assertEqual(rc, 0, err)


class RealRepositorySmokeTest(unittest.TestCase):
    def test_real_repository_validates_clean(self):
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = validate.main([])
        self.assertEqual(rc, 0, err_buf.getvalue())
        self.assertIn("Validation OK:", out_buf.getvalue())
        self.assertIn("adapter parity confirmed.", out_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
