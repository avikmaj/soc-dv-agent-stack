"""Regression tests for scripts/bootstrap.py: audit findings F2, F8, F9, F14, F17 and F18 (T2.1 .. T2.12) plus the
installation contracts.

Run: python3 -m unittest tests.test_bootstrap -v

Each test builds a synthetic stack checkout inside a temporary directory (a copy of scripts/bootstrap.py and
scripts/fssafety.py, CLAUDE.md, AGENTS.md, VERSION, the config template, a canonical skills/ tree with two skills
and both adapter trees in parity with it), an empty target project directory, an external canary directory and a
fake home directory (home/user) beside it. HOME and USERPROFILE are redirected to that fake home for every run, so
neither the real home directory nor the repository is ever a target or a destination, and nothing in the repository
is written.

  T2.1  dangling symlink at a destination (file, manifest, config, journal dir) -> exit 3, nothing written anywhere
  T2.2  symlinked .claude / .soc-dv parents        -> exit 3, canary directories untouched
  T2.3  Windows junction parent                    -> exit 3 (skipped with the reason where junctions cannot be made)
  T2.4  --force through a symlink or a hard link   -> exit 3, external file byte-identical
  T2.5  target denylist (F8): filesystem root, home, home ancestor, hidden entry below home (~/.claude, ~/.config/x),
        stack checkout, inside it, its ancestor, system prefix, missing target, file, symlinked leaf or path
        component -> exit 3 (target), nothing written; an ordinary ~/projects/x stays accepted
  T2.6  preflight failures (VERSION, contract, template, emptied or missing adapter, obstructed parent) -> 4 / 3
  T2.7  conflicts exit 7 without --force; --force keeps byte-exact hashed backups and the previous manifest (F9)
  T2.8  injected failures roll back to the pre-install state; the manifest is last; an unfinished journal exits 6
  T2.9  symlink inside an adapter or the canonical tree -> exit 4, nothing installed, linked content never used
  T2.10 adapter drift (extra file, changed byte, missing skill) and a broken canonical tree -> exit 4, nothing (F18)
  T2.11 whole skill directories are installed and every file is listed in the manifest with its sha256 (F18)
  T2.12 byte stability: installed bytes identical to the sources; manifest and journal are UTF-8 with LF only (F17)
"""
import codecs
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILLS = {"alpha": "# alpha\nsynthetic skill alpha\n", "beta": "# beta\nsynthetic skill beta\n"}
SKILL_TREES = ("skills", ".claude/skills", ".agents/skills")
CONTRACTS = {"CLAUDE.md": "# CLAUDE contract\n", "AGENTS.md": "# AGENTS contract\n"}
CONFIG = '{\n  "schema_version": "1.0"\n}\n'
EXIT_UNSAFE, EXIT_PREFLIGHT, EXIT_IO, EXIT_RECOVERY, EXIT_CONFLICT = 3, 4, 5, 6, 7
INSTALLED_PATHS = {"CLAUDE.md", "AGENTS.md", ".soc-dv/config.json", ".claude/skills/alpha/SKILL.md",
                   ".claude/skills/beta/SKILL.md", ".agents/skills/alpha/SKILL.md", ".agents/skills/beta/SKILL.md"}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel_path(base: Path, rel: str) -> Path:
    return base.joinpath(*rel.split("/"))


class Fixture:
    """tmp/{stack,target,external,home/user}; the stack is a synthetic checkout with the real scripts copied in."""

    def __init__(self, tmp: str):
        self.tmp = Path(tmp).resolve()
        self.stack = self.tmp / "stack"
        self.target = self.tmp / "target"
        self.external = self.tmp / "external"
        self.home = self.tmp / "home" / "user"
        (self.stack / "scripts").mkdir(parents=True)
        for name in ("bootstrap.py", "fssafety.py"):
            shutil.copy2(SCRIPTS / name, self.stack / "scripts" / name)
        for name, text in CONTRACTS.items():
            _write(self.stack / name, text)
        _write(self.stack / "VERSION", "0.1.0\n")
        _write(self.stack / "templates" / "project-config.example.json", CONFIG)
        for skill, text in SKILLS.items():
            self.add_skill_file(f"{skill}/SKILL.md", text)
        self.target.mkdir()
        self.external.mkdir()
        self.home.mkdir(parents=True)

    def add_skill_file(self, rel: str, text: str) -> None:
        """Write a skill file into the canonical tree and both adapter trees, keeping them in parity."""
        for tree in SKILL_TREES:
            _write(rel_path(self.stack, f"{tree}/{rel}"), text)

    def run(self, *args: str, target: "Path | None" = None) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HOME=str(self.home), USERPROFILE=str(self.home))
        cmd = [sys.executable, str(self.stack / "scripts" / "bootstrap.py"),
               "--target", str(target if target is not None else self.target), *args]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.tmp), env=env)

    def load_module(self):
        """Import the fixture's copy of bootstrap.py in-process (it imports the fixture's fssafety.py).

        The module is registered in sys.modules only while it executes (dataclasses resolves the module's postponed
        annotations through sys.modules[cls.__module__]); the entry is removed again, also when execution fails.
        """
        sys.modules.pop("fssafety", None)
        spec = importlib.util.spec_from_file_location("bootstrap_under_test", self.stack / "scripts" / "bootstrap.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop(spec.name, None)
        return mod

    def manifest(self) -> dict:
        return json.loads((self.target / ".soc-dv" / "install-manifest.json").read_text(encoding="utf-8"))

    def journals(self) -> list:
        journal_dir = self.target / ".soc-dv" / "journal"
        return sorted(journal_dir.iterdir()) if journal_dir.is_dir() else []


def snapshot(base: Path, *, ignore_journal: bool = False) -> dict:
    """Relative path -> ('d'|'f'|'l', sha256-or-link-target), never following links."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(base).as_posix()
            if ignore_journal and (rel == ".soc-dv" or rel.startswith(".soc-dv/journal")):
                continue
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("l", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("d", None)
            else:
                out[rel] = ("f", sha(p.read_bytes()))
    return out


def symlink_or_skip(case: unittest.TestCase, target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        case.skipTest(f"cannot create symbolic links on this host: {exc}")


def remove_link(link: Path) -> None:
    try:
        os.unlink(link)
    except OSError:  # a directory symbolic link on Windows is removed with rmdir
        os.rmdir(link)


def assert_refused(case: unittest.TestCase, r: subprocess.CompletedProcess, code: int, label: str,
                   needle: str = "") -> None:
    case.assertEqual(r.returncode, code, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    case.assertIn(f"ERROR[{label}]", r.stderr)
    case.assertNotIn("Traceback", r.stderr)
    case.assertEqual(r.stdout, "", "nothing may be reported as planned or installed when a run is refused")
    if needle:
        case.assertIn(needle, r.stderr)


class RefusalTests(unittest.TestCase):
    """T2.1 .. T2.4 and T2.9: unsafe path states fail closed before anything is written."""

    def test_t2_1_dangling_symlink_destination_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            (f.external / "planted").mkdir()
            (f.target / ".soc-dv").mkdir()
            for rel in ("CLAUDE.md", ".soc-dv/install-manifest.json", ".soc-dv/config.json", ".soc-dv/journal"):
                link = rel_path(f.target, rel)
                symlink_or_skip(self, f.external / "planted" / link.name, link)
                before = (snapshot(f.target), snapshot(f.external))
                for args in ((), ("--force",), ("--dry-run",)):
                    with self.subTest(rel=rel, args=args):
                        assert_refused(self, f.run(*args), EXIT_UNSAFE, "unsafe-path", "symbolic link")
                self.assertEqual((snapshot(f.target), snapshot(f.external)), before)
                self.assertEqual(sorted(p.name for p in (f.external / "planted").iterdir()), [],
                                 "a dangling link must never be followed to create its target")
                remove_link(link)

    def test_t2_2_symlinked_parents_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.external / "ext_claude" / "skills" / "keep.txt", "canary\n")
            (f.external / "ext_socdv").mkdir()
            symlink_or_skip(self, f.external / "ext_claude", f.target / ".claude")
            symlink_or_skip(self, f.external / "ext_socdv", f.target / ".soc-dv")
            before = (snapshot(f.target), snapshot(f.external))
            for args in (("--harness", "claude"), ("--harness", "all", "--force"), ("--dry-run",)):
                assert_refused(self, f.run(*args), EXIT_UNSAFE, "unsafe-path", "symbolic link")
            self.assertEqual((snapshot(f.target), snapshot(f.external)), before)
            remove_link(f.target / ".claude")  # the .soc-dv link alone is refused as well
            assert_refused(self, f.run("--harness", "claude"), EXIT_UNSAFE, "unsafe-path", "symbolic link")
            self.assertEqual(snapshot(f.external), before[1])

    @unittest.skipUnless(sys.platform == "win32",
                         "T2.3 requires Windows: junctions are NTFS reparse points and cannot be created on this host")
    def test_t2_3_windows_junction_parent_refused(self):  # pragma: no cover - Windows only
        import _winapi
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.external / "ext_claude" / "skills" / "keep.txt", "canary\n")
            try:
                _winapi.CreateJunction(str(f.external / "ext_claude"), str(f.target / ".claude"))
            except OSError as exc:
                self.skipTest(f"T2.3 skipped: junction creation not permitted for this user: {exc}")
            before = snapshot(f.external)
            assert_refused(self, f.run("--harness", "claude", "--force"), EXIT_UNSAFE, "unsafe-path", "reparse point")
            self.assertEqual(snapshot(f.external), before)

    def test_t2_4_force_never_writes_through_symlink_or_hard_link(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.external / "user" / "AGENTS.md", "pre-existing external content\n")
            symlink_or_skip(self, f.external / "user" / "AGENTS.md", f.target / "AGENTS.md")
            before = snapshot(f.external)
            for args in (("--harness", "codex"), ("--harness", "codex", "--force")):
                assert_refused(self, f.run(*args), EXIT_UNSAFE, "unsafe-path", "symbolic link")
            self.assertEqual(snapshot(f.external), before)
            self.assertEqual(snapshot(f.target), {"AGENTS.md": ("l", str(f.external / "user" / "AGENTS.md"))})
            # a hard-linked destination shares its inode with an external file: refused, even with --force
            _write(f.external / "user2" / "CLAUDE.md", "pre-existing hard-linked content\n")
            try:
                os.link(f.external / "user2" / "CLAUDE.md", f.target / "CLAUDE.md")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"hard links unavailable on this host: {exc}")
            before = snapshot(f.external)
            assert_refused(self, f.run("--harness", "claude", "--force"), EXIT_UNSAFE, "unsafe-path", "hard links")
            self.assertEqual(snapshot(f.external), before)
            self.assertEqual(os.stat(f.target / "CLAUDE.md").st_nlink, 2)

    def test_t2_9_symlink_in_source_tree_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.external / "secret.txt", "SECRET-MATERIAL-MUST-NOT-LEAK\n")
            before = snapshot(f.target)
            # a link inside an adapter tree is drift against the canonical tree: refused whichever harness is chosen
            adapter_file = f.stack / ".claude" / "skills" / "alpha" / "SKILL.md"
            os.unlink(adapter_file)
            symlink_or_skip(self, f.external / "secret.txt", adapter_file)
            for args in (("--harness", "claude"), ("--harness", "codex"), ("--dry-run",)):
                assert_refused(self, f.run(*args), EXIT_PREFLIGHT, "preflight", "differs from skills/")
            remove_link(adapter_file)
            _write(adapter_file, SKILLS["alpha"])
            # a link inside the canonical tree is refused by the strict source scan, before parity is considered
            symlink_or_skip(self, f.external / "secret.txt", f.stack / "skills" / "alpha" / "leak.md")
            for args in (("--harness", "claude"), ("--dry-run",), ("--force",)):
                assert_refused(self, f.run(*args), EXIT_PREFLIGHT, "preflight", "symbolic link")
            self.assertEqual(snapshot(f.target), before)
            for p in f.target.rglob("*"):
                if p.is_file():
                    self.assertNotIn(b"MUST-NOT-LEAK", p.read_bytes())


class TargetAndPreflightTests(unittest.TestCase):
    """T2.5 and T2.6: unsafe targets and preflight failures fail closed before the first write."""

    def _assert_all_refused(self, f: Fixture, cases: list) -> None:
        before = snapshot(f.tmp)
        for target, needle in cases:
            for args in ((), ("--dry-run",), ("--force",)):
                with self.subTest(target=str(target), args=args):
                    assert_refused(self, f.run(*args, target=target), EXIT_UNSAFE, "target", needle)
        self.assertEqual(snapshot(f.tmp), before, "a refused target must not change anything anywhere")

    def test_t2_5_target_denylist_refuses_unsafe_targets(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            regular = f.tmp / "regular.txt"
            regular.write_bytes(b"not a directory\n")
            (f.home / ".claude").mkdir()
            (f.home / ".config" / "sub").mkdir(parents=True)
            (f.home / "projects" / "x").mkdir(parents=True)
            cases = [
                (f.tmp / "does-not-exist", "does not exist"),
                (regular, "is not a directory"),
                (Path(f.tmp.anchor), "filesystem root"),
                (f.home, "into the home directory"),
                (f.home.parent, "ancestor of the home directory"),
                (f.home / ".claude", f"user configuration directory {f.home / '.claude'}"),
                (f.home / ".config" / "sub", f"user configuration directory {f.home / '.config'}"),
                (f.stack, "stack checkout itself"),
                (f.stack / "skills", "inside the stack checkout"),
                (f.tmp, "ancestor of the stack checkout"),
            ]
            usr = Path("/usr")
            if os.name == "posix" and usr.is_dir() and not usr.is_symlink():
                cases.append((usr, "system directory"))
            self._assert_all_refused(f, cases)
            # an ordinary subdirectory of the home directory is a legitimate project location
            before = snapshot(f.tmp)
            r = f.run("--dry-run", target=f.home / "projects" / "x")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"target: {f.home / 'projects' / 'x'}", r.stdout)
            self.assertIn("CLAUDE.md -> CLAUDE.md [create]", r.stdout)
            self.assertIn("nothing was modified", r.stdout)
            self.assertEqual(snapshot(f.tmp), before, "--dry-run into an accepted target must not change anything")

    def test_t2_5b_target_through_symbolic_link_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            (f.tmp / "real-dir" / "proj").mkdir(parents=True)
            symlink_or_skip(self, f.target, f.tmp / "link-to-target")
            symlink_or_skip(self, f.tmp / "real-dir", f.tmp / "link-dir")
            self._assert_all_refused(f, [(f.tmp / "link-to-target", "pass the real directory"),
                                         (f.tmp / "link-dir" / "proj", "pass the real directory")])
            self.assertEqual(snapshot(f.tmp / "real-dir"), {"proj": ("d", None)})

    @unittest.skipUnless(sys.platform == "win32", "drive roots and %SystemRoot% exist only on Windows")
    def test_t2_5c_windows_drive_root_and_system_directories_refused(self):  # pragma: no cover - Windows only
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            cases = [(Path(os.environ.get("SystemDrive", "C:") + "\\"), "filesystem root")]
            for variable in ("SystemRoot", "ProgramFiles", "ProgramData", "APPDATA"):
                value = os.environ.get(variable)
                if value and Path(value).is_dir():
                    cases.append((Path(value), "system directory"))
            self.assertGreater(len(cases), 1, "the Windows runner must expose at least one system variable")
            self._assert_all_refused(f, cases)

    def test_t2_6_preflight_failures_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            before = snapshot(f.target)
            os.unlink(f.stack / "VERSION")
            assert_refused(self, f.run(), EXIT_PREFLIGHT, "preflight", "VERSION")
            _write(f.stack / "VERSION", "not-a-version\n")
            assert_refused(self, f.run(), EXIT_PREFLIGHT, "preflight", "valid version")
            _write(f.stack / "VERSION", "0.1.0\n")
            os.unlink(f.stack / "AGENTS.md")
            assert_refused(self, f.run(), EXIT_PREFLIGHT, "preflight", "AGENTS.md")
            _write(f.stack / "AGENTS.md", CONTRACTS["AGENTS.md"])
            os.unlink(f.stack / "templates" / "project-config.example.json")
            assert_refused(self, f.run(), EXIT_PREFLIGHT, "preflight", "project-config.example.json")
            _write(f.stack / "templates" / "project-config.example.json", CONFIG)
            shutil.rmtree(f.stack / ".agents" / "skills")
            (f.stack / ".agents" / "skills").mkdir()
            assert_refused(self, f.run("--harness", "claude"), EXIT_PREFLIGHT, "preflight", "differs from skills/")
            shutil.rmtree(f.stack / ".agents" / "skills")
            assert_refused(self, f.run(), EXIT_PREFLIGHT, "preflight", "adapter tree is missing")
            for skill, text in SKILLS.items():
                _write(f.stack / ".agents" / "skills" / skill / "SKILL.md", text)
            self.assertEqual(snapshot(f.target), before, "no preflight failure may leave anything in the target")
            # an obstructed destination parent is an unsafe path state, refused before any write
            _write(f.target / ".agents", "not a directory\n")
            assert_refused(self, f.run(), EXIT_UNSAFE, "unsafe-path", "not a directory")
            self.assertEqual(snapshot(f.target), {".agents": ("f", sha(b"not a directory\n"))})
            os.unlink(f.target / ".agents")
            _write(f.target / ".soc-dv", "not a directory\n")
            assert_refused(self, f.run(), EXIT_UNSAFE, "unsafe-path", "not a directory")
            self.assertEqual(snapshot(f.target), {".soc-dv": ("f", sha(b"not a directory\n"))})


class ForceAndBackupTests(unittest.TestCase):
    """T2.7: conflicts need --force; --force keeps hashed backups and the previous manifest; unchanged files rest."""

    def test_t2_7_conflicts_backups_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            originals = {"CLAUDE.md": b"the project's own CLAUDE.md\n", "AGENTS.md": b"the project's own AGENTS.md\n"}
            for name, data in originals.items():
                (f.target / name).write_bytes(data)
            _write(f.target / ".soc-dv" / "install-manifest.json", '{"stack_version": "0.0.9"}\n')
            before = snapshot(f.target)
            r = f.run()
            assert_refused(self, r, EXIT_CONFLICT, "conflict", "Refusing to overwrite existing files")
            self.assertIn("CLAUDE.md", r.stderr)
            self.assertEqual(snapshot(f.target), before, "a refused conflict must not change anything")
            r = f.run("--force")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("CLAUDE.md -> CLAUDE.md [replace]", r.stdout)
            self.assertIn("skills/alpha/SKILL.md -> .claude/skills/alpha/SKILL.md [create]", r.stdout)
            m = f.manifest()
            self.assertEqual(m["schema_version"], 2)
            self.assertEqual(m["stack_version"], "0.1.0")
            entries = {e["path"]: e for e in m["files"]}
            self.assertEqual(set(entries), INSTALLED_PATHS)
            for name, text in CONTRACTS.items():
                e = entries[name]
                self.assertEqual(e["action"], "replace")
                self.assertEqual(e["previous_sha256"], sha(originals[name]))
                backup = rel_path(f.target, e["backup"])
                self.assertTrue(e["backup"].startswith(".soc-dv/backups/"), e["backup"])
                self.assertEqual(backup.read_bytes(), originals[name], "the backup must hold the replaced bytes")
                self.assertEqual(sha(backup.read_bytes()), e["previous_sha256"])
                self.assertEqual((f.target / name).read_text(encoding="utf-8"), text)
                self.assertEqual(e["sha256"], sha(text.encode("utf-8")))
            self.assertEqual(entries[".claude/skills/alpha/SKILL.md"]["action"], "create")
            self.assertEqual(entries[".claude/skills/alpha/SKILL.md"]["source"], "skills/alpha/SKILL.md")
            self.assertEqual(entries[".soc-dv/config.json"]["action"], "create")
            self.assertEqual((f.target / ".soc-dv" / "config.json").read_text(encoding="utf-8"), CONFIG)
            self.assertIsNotNone(m["previous_manifest"])
            previous_backup = rel_path(f.target, m["previous_manifest"]["backup"])
            self.assertEqual(previous_backup.read_text(encoding="utf-8"), '{"stack_version": "0.0.9"}\n')
            self.assertEqual(sha(previous_backup.read_bytes()), m["previous_manifest"]["sha256"])
            journals = f.journals()
            self.assertEqual(len(journals), 1)
            events = [json.loads(line)["event"] for line in journals[0].read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[0], "begin")
            self.assertEqual(events[-1], "complete")
            self.assertEqual(events.index("manifest"), len(events) - 2, "the manifest is the last file written")
            # a second run finds every file unchanged and writes only a new manifest
            first_manifest_sha = sha((f.target / ".soc-dv" / "install-manifest.json").read_bytes())
            after_first = snapshot(f.target)
            r = f.run()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("[create]", r.stdout)
            self.assertNotIn("[replace]", r.stdout)
            m2 = f.manifest()
            self.assertTrue(all(e["action"] == "unchanged" for e in m2["files"]))
            self.assertEqual(m2["previous_manifest"]["sha256"], first_manifest_sha)
            after_second = snapshot(f.target)
            for rel, value in after_first.items():
                if not rel.startswith(".soc-dv/"):
                    self.assertEqual(after_second[rel], value, f"{rel} must not change when it is up to date")

    @unittest.skipUnless(sys.platform == "win32", "the read-only attribute is a Windows concept")
    def test_t2_7b_windows_force_replaces_a_read_only_file_after_backing_it_up(self):  # pragma: no cover
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            (f.target / "CLAUDE.md").write_bytes(b"read-only project file\n")
            os.chmod(f.target / "CLAUDE.md", stat.S_IREAD)
            r = f.run("--harness", "claude", "--force")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((f.target / "CLAUDE.md").read_bytes(), CONTRACTS["CLAUDE.md"].encode("utf-8"))
            e = {x["path"]: x for x in f.manifest()["files"]}["CLAUDE.md"]
            self.assertEqual(e["previous_sha256"], sha(b"read-only project file\n"))
            self.assertEqual(rel_path(f.target, e["backup"]).read_bytes(), b"read-only project file\n")


class RollbackTests(unittest.TestCase):
    """T2.8: any failure during installation rolls the target back; an unfinished journal blocks later runs."""

    def _inject_and_run(self, f: Fixture, fail_on_call: int, *args: str) -> tuple:
        mod = f.load_module()
        real = mod.fssafety.write_regular_atomically
        calls = {"n": 0}

        def failing(root, path, data, **kwargs):
            calls["n"] += 1
            if calls["n"] == fail_on_call:
                raise OSError(28, "injected write failure")
            return real(root, path, data, **kwargs)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(mod.fssafety, "write_regular_atomically", failing), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = mod.main(["--target", str(f.target), *args])
        return rc, out.getvalue(), err.getvalue(), calls["n"]

    def test_t2_8_failure_mid_install_rolls_back_to_pre_state(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.target / "CLAUDE.md", "the project's own CLAUDE.md\n")  # exercises backup and restore
            before = snapshot(f.target)
            rc, out, err, calls = self._inject_and_run(f, 3, "--force")
            self.assertEqual(rc, EXIT_IO, err)
            self.assertIn("ERROR[install-failed]", err)
            self.assertIn("rolled back", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(snapshot(f.target, ignore_journal=True), before)
            self.assertFalse((f.target / ".soc-dv" / "install-manifest.json").exists())
            self.assertFalse((f.target / ".soc-dv" / "backups").exists())
            journals = f.journals()
            self.assertEqual(len(journals), 1)
            events = [json.loads(line)["event"] for line in journals[0].read_text(encoding="utf-8").splitlines()]
            self.assertIn("rollback", events)
            self.assertEqual(events[-1], "rolled_back")

    def test_t2_8b_manifest_is_written_last_and_a_failure_there_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            rc, out, err, calls = self._inject_and_run(f, len(INSTALLED_PATHS) + 1)
            self.assertEqual(rc, EXIT_IO, err)
            self.assertEqual(calls, len(INSTALLED_PATHS) + 1, "the manifest must be the last file written")
            self.assertFalse((f.target / ".soc-dv" / "install-manifest.json").exists())
            self.assertEqual(snapshot(f.target, ignore_journal=True), {})
            # with the fault removed the same installation completes and the manifest appears
            mod = f.load_module()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--target", str(f.target)]), 0)
            self.assertEqual({e["path"] for e in f.manifest()["files"]}, INSTALLED_PATHS)

    def test_t2_8c_unfinished_journal_blocks_installation(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.target / ".soc-dv" / "journal" / "20260101T000000Z-deadbeef.jsonl",
                   json.dumps({"t": "2026-01-01T00:00:00Z", "event": "begin"}) + "\n")
            before = snapshot(f.target)
            for args in ((), ("--dry-run",), ("--force",)):
                assert_refused(self, f.run(*args), EXIT_RECOVERY, "recovery-needed", "did not finish")
            self.assertEqual(snapshot(f.target), before)


class ParityAndWholeSkillTests(unittest.TestCase):
    """T2.10 and T2.11 (F18): adapter parity is a preflight gate; skills are installed whole and fully listed."""

    def _assert_preflight_refused(self, mutate, needle: str, *runs: tuple) -> None:
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            mutate(f)
            before = (snapshot(f.target), snapshot(f.external))
            for args in runs or ((), ("--harness", "claude"), ("--dry-run",), ("--force",)):
                with self.subTest(needle=needle, args=args):
                    assert_refused(self, f.run(*args), EXIT_PREFLIGHT, "preflight", needle)
            self.assertEqual((snapshot(f.target), snapshot(f.external)), before, "a refused preflight writes nothing")

    def test_t2_10_adapter_drift_refused_without_writing(self):
        drift = "differs from skills/"

        def extra_file(f: Fixture) -> None:
            _write(f.stack / ".agents" / "skills" / "alpha" / "extra.md", "not in the canonical tree\n")

        def changed_byte(f: Fixture) -> None:
            (f.stack / ".claude" / "skills" / "beta" / "SKILL.md").write_bytes(SKILLS["beta"].encode("utf-8") + b"!")

        def missing_skill(f: Fixture) -> None:
            shutil.rmtree(f.stack / ".agents" / "skills" / "beta")

        self._assert_preflight_refused(extra_file, drift)
        self._assert_preflight_refused(changed_byte, drift)
        self._assert_preflight_refused(missing_skill, drift)

    def test_t2_10b_broken_canonical_tree_refused_without_writing(self):
        def missing_tree(f: Fixture) -> None:
            shutil.rmtree(f.stack / "skills")

        def empty_tree(f: Fixture) -> None:
            shutil.rmtree(f.stack / "skills")
            (f.stack / "skills").mkdir()

        def loose_file(f: Fixture) -> None:
            f.add_skill_file("README.md", "not a skill\n")

        def skill_without_skill_md(f: Fixture) -> None:
            f.add_skill_file("gamma/notes.md", "no SKILL.md here\n")

        def bad_component(f: Fixture) -> None:
            f.add_skill_file("alpha/bad name.md", "space in the name\n")

        def hidden_component(f: Fixture) -> None:
            f.add_skill_file("alpha/.hidden/a.md", "hidden directory\n")

        self._assert_preflight_refused(missing_tree, "source tree is missing")
        self._assert_preflight_refused(empty_tree, "contains no files")
        self._assert_preflight_refused(loose_file, "belongs to no skill")
        self._assert_preflight_refused(skill_without_skill_md, "has no SKILL.md")
        self._assert_preflight_refused(bad_component, "is not permitted")
        self._assert_preflight_refused(hidden_component, "is not permitted")

    def test_t2_11_whole_skill_directories_installed_and_listed(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            extra = {"alpha/references/a.md": "# reference a\n", "alpha/scripts/check.py": "print('check')\n",
                     "beta/data/table.json": '{"rows": []}\n'}
            for rel, text in extra.items():
                f.add_skill_file(rel, text)
            r = f.run("--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("skills/alpha/references/a.md -> .claude/skills/alpha/references/a.md [create]", r.stdout)
            self.assertEqual(snapshot(f.target), {}, "--dry-run must not change a single byte")
            r = f.run()
            self.assertEqual(r.returncode, 0, r.stderr)
            expected = set(INSTALLED_PATHS)
            for rel in extra:
                expected.update({f".claude/skills/{rel}", f".agents/skills/{rel}"})
            m = f.manifest()
            entries = {e["path"]: e for e in m["files"]}
            self.assertEqual(set(entries), expected)
            for rel, text in extra.items():
                for adapter in (".claude", ".agents"):
                    installed = rel_path(f.target, f"{adapter}/skills/{rel}")
                    self.assertEqual(installed.read_bytes(), text.encode("utf-8"))
                    e = entries[f"{adapter}/skills/{rel}"]
                    self.assertEqual(e["sha256"], sha(text.encode("utf-8")))
                    self.assertEqual(e["source"], f"skills/{rel}")
                    self.assertEqual(e["action"], "create")
            for e in m["files"]:
                self.assertEqual(sha(rel_path(f.target, e["path"]).read_bytes()), e["sha256"])
            # the target holds exactly the planned files (plus the .soc-dv bookkeeping), nothing else
            installed_files = {rel for rel, (kind, _) in snapshot(f.target).items()
                               if kind == "f" and not rel.startswith(".soc-dv/")}
            self.assertEqual(installed_files, expected - {".soc-dv/config.json"})
            # a single harness installs only its own side but is still gated on both adapters
            shutil.rmtree(f.target)
            f.target.mkdir()
            r = f.run("--harness", "codex")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((f.target / ".claude").exists())
            self.assertTrue(rel_path(f.target, ".agents/skills/alpha/references/a.md").is_file())
            self.assertEqual({e["path"] for e in f.manifest()["files"]},
                             {p for p in expected if not p.startswith((".claude/", "CLAUDE"))})

    def test_permitted_write_set_is_strict(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Fixture(d).load_module()
            for ok in ("CLAUDE.md", "AGENTS.md", ".agents/skills/x/SKILL.md", ".claude/skills/x/references/a.md",
                       ".claude/skills/x.y-z_1/deep/er/file.txt", ".soc-dv/config.json",
                       ".soc-dv/install-manifest.json", ".soc-dv/journal/20260101T000000Z-deadbeef.jsonl",
                       ".soc-dv/backups/20260101T000000Z-deadbeef/.claude/skills/x/SKILL.md",
                       ".soc-dv/backups/20260101T000000Z-deadbeef/.soc-dv/install-manifest.json"):
                self.assertTrue(mod.PERMITTED_RE.match(ok), ok)
            for bad in (".claude/skills/x", ".claude/skills/../x/SKILL.md", "/etc/passwd", "../CLAUDE.md",
                        ".claude/skills/.hidden/SKILL.md", ".claude/skills/x/sub dir/a.md", "skills/x/SKILL.md",
                        ".soc-dv/journal/evil.jsonl", ".soc-dv/backups/evil/CLAUDE.md", ".claude/skills//SKILL.md",
                        ".codex/skills/x/SKILL.md", "CLAUDE.md/extra"):
                self.assertFalse(mod.PERMITTED_RE.match(bad), bad)


class InstallContractTests(unittest.TestCase):
    def test_dry_run_then_install(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            r = f.run("--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[create]", r.stdout)
            self.assertIn("nothing was modified", r.stdout)
            self.assertEqual(snapshot(f.target), {}, "--dry-run must not change a single byte")
            r = f.run()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Installed project-local stack", r.stdout)
            for name, text in CONTRACTS.items():
                self.assertEqual((f.target / name).read_text(encoding="utf-8"), text)
            for adapter in (".claude", ".agents"):
                for skill, text in SKILLS.items():
                    self.assertEqual((f.target / adapter / "skills" / skill / "SKILL.md").read_text(encoding="utf-8"),
                                     text)
            m = f.manifest()
            self.assertEqual({e["path"] for e in m["files"]}, INSTALLED_PATHS)
            for e in m["files"]:
                self.assertEqual(e["action"], "create")
                self.assertEqual(sha(rel_path(f.target, e["path"]).read_bytes()), e["sha256"])
            self.assertIsNone(m["previous_manifest"])
            self.assertTrue(rel_path(f.target, m["journal"]).is_file())
            self.assertEqual([p for p in f.target.rglob("*") if ".tmp-" in p.name], [], "no temporary files")
            # an existing project config is never replaced, with or without --force
            _write(f.target / ".soc-dv" / "config.json", '{"custom": true}\n')
            r = f.run("--force")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((f.target / ".soc-dv" / "config.json").read_text(encoding="utf-8"), '{"custom": true}\n')
            self.assertNotIn(".soc-dv/config.json", r.stdout, "an existing config is not even part of the plan")

    def test_t2_12_installed_bytes_manifest_and_journal_are_byte_stable(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            crlf, utf8 = "line one\r\nline two\r\n", "# β — naïve ünicode\n"
            f.add_skill_file("alpha/references/crlf.md", crlf)
            f.add_skill_file("beta/references/utf8.md", utf8)
            r = f.run()
            self.assertEqual(r.returncode, 0, r.stderr)
            for adapter in (".claude", ".agents"):
                self.assertEqual(rel_path(f.target, f"{adapter}/skills/alpha/references/crlf.md").read_bytes(),
                                 crlf.encode("utf-8"), "source bytes must be copied exactly, CRLF included")
                self.assertEqual(rel_path(f.target, f"{adapter}/skills/beta/references/utf8.md").read_bytes(),
                                 utf8.encode("utf-8"))
            manifest = (f.target / ".soc-dv" / "install-manifest.json").read_bytes()
            self.assertFalse(manifest.startswith(codecs.BOM_UTF8))
            self.assertNotIn(b"\r", manifest)
            self.assertTrue(manifest.endswith(b"}\n"))
            self.assertEqual(json.loads(manifest.decode("utf-8"))["stack_version"], "0.1.0")
            journal = f.journals()[0].read_bytes()
            self.assertFalse(journal.startswith(codecs.BOM_UTF8))
            self.assertNotIn(b"\r", journal)
            self.assertTrue(journal.endswith(b"\n"))
            events = [json.loads(line)["event"] for line in journal.decode("utf-8").splitlines()]
            self.assertEqual((events[0], events[-1]), ("begin", "complete"))

    def test_usage_error_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertEqual(f.run("--harness", "nope").returncode, 2)


class LineEndingTests(unittest.TestCase):
    """F17: the repository pins LF for source types so checkouts (and installed copies) are byte-stable."""

    def test_gitattributes_pins_lf_for_source_types(self):
        data = (ROOT / ".gitattributes").read_bytes()
        self.assertFalse(data.startswith(codecs.BOM_UTF8), ".gitattributes must not start with a BOM")
        self.assertNotIn(b"\r", data, ".gitattributes must use LF line endings")
        self.assertTrue(data.endswith(b"\n") and not data.endswith(b"\n\n"), "exactly one trailing newline")
        rules = [" ".join(line.split()) for line in data.decode("utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        self.assertIn("* text=auto", rules)
        for pattern in ("*.py", "*.md", "*.json", "*.yml", "*.yaml", "*.toml", "VERSION", ".gitattributes"):
            self.assertIn(f"{pattern} text eol=lf", rules)
        for pattern in ("*.bat", "*.cmd", "*.ps1"):
            self.assertIn(f"{pattern} text eol=crlf", rules)


if __name__ == "__main__":
    unittest.main()
