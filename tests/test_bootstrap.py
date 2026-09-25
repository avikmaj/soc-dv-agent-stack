"""Regression tests for audit finding F2 in scripts/bootstrap.py (T2.1 .. T2.9) plus the installation contracts.

Run: python3 -m unittest tests.test_bootstrap -v

Each test builds a synthetic stack checkout inside a temporary directory (a copy of scripts/bootstrap.py and
scripts/fssafety.py, CLAUDE.md, AGENTS.md, VERSION, the config template and two skills per adapter), an empty
target project directory, an external canary directory and a fake home directory beside it. HOME is redirected to
that fake home for every run, so neither the real home directory nor the repository is ever a target or a
destination, and nothing in the repository is written.

  T2.1  dangling symlink at a destination          -> exit 3, nothing written anywhere
  T2.2  symlinked .claude / .soc-dv parents        -> exit 3, canary directories untouched
  T2.3  Windows junction parent                    -> exit 3 (skipped with the reason where junctions cannot be made)
  T2.4  --force through a symlink or a hard link   -> exit 3, external file byte-identical
  T2.5  unsafe targets (missing, file, link, home) -> exit 3 (unsafe-target), nothing written
  T2.6  preflight failures (VERSION, source, empty adapter, obstructed parent) -> exit 4 / 3, nothing written
  T2.7  conflicts exit 7 without --force; --force keeps hashed backups and the previous manifest
  T2.8  injected failures roll back to the pre-install state; the manifest is last; an unfinished journal exits 6
  T2.9  symlink inside the source tree             -> exit 3, nothing installed, linked content never materialised
"""
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
CONTRACTS = {"CLAUDE.md": "# CLAUDE contract\n", "AGENTS.md": "# AGENTS contract\n"}
CONFIG = '{\n  "schema_version": "1.0"\n}\n'
EXIT_UNSAFE, EXIT_PREFLIGHT, EXIT_IO, EXIT_RECOVERY, EXIT_CONFLICT = 3, 4, 5, 6, 7
INSTALLED_PATHS = {"CLAUDE.md", "AGENTS.md", ".soc-dv/config.json", ".claude/skills/alpha/SKILL.md",
                   ".claude/skills/beta/SKILL.md", ".agents/skills/alpha/SKILL.md", ".agents/skills/beta/SKILL.md"}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel_path(base: Path, rel: str) -> Path:
    return base.joinpath(*rel.split("/"))


class Fixture:
    """tmp/{stack,target,external,home}; the stack is a synthetic checkout with the real scripts copied in."""

    def __init__(self, tmp: str):
        self.tmp = Path(tmp).resolve()
        self.stack = self.tmp / "stack"
        self.target = self.tmp / "target"
        self.external = self.tmp / "external"
        self.home = self.tmp / "home"
        (self.stack / "scripts").mkdir(parents=True)
        for name in ("bootstrap.py", "fssafety.py"):
            shutil.copy2(SCRIPTS / name, self.stack / "scripts" / name)
        for name, text in CONTRACTS.items():
            _write(self.stack / name, text)
        _write(self.stack / "VERSION", "0.1.0\n")
        _write(self.stack / "templates" / "project-config.example.json", CONFIG)
        for adapter in (".claude", ".agents"):
            for skill, text in SKILLS.items():
                _write(self.stack / adapter / "skills" / skill / "SKILL.md", text)
        self.target.mkdir()
        self.external.mkdir()
        self.home.mkdir()

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
            symlink_or_skip(self, f.external / "planted" / "CLAUDE.md", f.target / "CLAUDE.md")
            before = (snapshot(f.target), snapshot(f.external))
            for args in ((), ("--force",), ("--dry-run",)):
                assert_refused(self, f.run(*args), EXIT_UNSAFE, "unsafe-path", "symbolic link")
            self.assertEqual((snapshot(f.target), snapshot(f.external)), before)
            self.assertFalse((f.external / "planted" / "CLAUDE.md").exists())

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
            os.unlink(f.stack / ".claude" / "skills" / "alpha" / "SKILL.md")
            symlink_or_skip(self, f.external / "secret.txt", f.stack / ".claude" / "skills" / "alpha" / "SKILL.md")
            before = snapshot(f.target)
            for args in (("--harness", "claude"), ("--dry-run",)):
                assert_refused(self, f.run(*args), EXIT_UNSAFE, "unsafe-path", "symbolic link")
            self.assertEqual(snapshot(f.target), before)
            for p in f.target.rglob("*"):
                if p.is_file():
                    self.assertNotIn(b"MUST-NOT-LEAK", p.read_bytes())


class TargetAndPreflightTests(unittest.TestCase):
    """T2.5 and T2.6: unsafe targets and preflight failures fail closed before the first write."""

    def test_t2_5_unsafe_targets_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            regular = f.tmp / "regular.txt"
            regular.write_text("not a directory\n", encoding="utf-8")
            cases = [(f.tmp / "does-not-exist", "does not exist"), (regular, "not a directory"),
                     (f.home, "Refusing home/root target")]
            link = f.tmp / "link-to-target"
            try:
                os.symlink(f.target, link, target_is_directory=True)
                cases.append((link, "pass the real directory"))
            except (OSError, NotImplementedError):
                pass
            for target, needle in cases:
                for args in ((), ("--dry-run",), ("--force",)):
                    assert_refused(self, f.run(*args, target=target), EXIT_UNSAFE, "unsafe-target", needle)
            self.assertEqual(snapshot(f.target), {})
            self.assertEqual(sorted(p.name for p in f.home.iterdir()), [])

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
            shutil.rmtree(f.stack / ".agents" / "skills")
            (f.stack / ".agents" / "skills").mkdir()
            assert_refused(self, f.run(), EXIT_PREFLIGHT, "preflight", "no SKILL.md")
            for skill, text in SKILLS.items():
                _write(f.stack / ".agents" / "skills" / skill / "SKILL.md", text)
            self.assertEqual(snapshot(f.target), before, "no preflight failure may leave anything in the target")
            # an obstructed destination parent is an unsafe path state, refused before any write
            _write(f.target / ".agents", "not a directory\n")
            assert_refused(self, f.run(), EXIT_UNSAFE, "unsafe-path", "not a directory")
            self.assertEqual(snapshot(f.target), {".agents": ("f", sha(b"not a directory\n"))})


class ForceAndBackupTests(unittest.TestCase):
    """T2.7: conflicts need --force; --force keeps hashed backups and the previous manifest; unchanged files rest."""

    def test_t2_7_conflicts_backups_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.target / "CLAUDE.md", "the project's own CLAUDE.md\n")
            _write(f.target / "AGENTS.md", "the project's own AGENTS.md\n")
            _write(f.target / ".soc-dv" / "install-manifest.json", '{"stack_version": "0.0.9"}\n')
            before = snapshot(f.target)
            r = f.run()
            assert_refused(self, r, EXIT_CONFLICT, "conflict", "Refusing to overwrite existing files")
            self.assertIn("CLAUDE.md", r.stderr)
            self.assertEqual(snapshot(f.target), before, "a refused conflict must not change anything")
            r = f.run("--force")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("CLAUDE.md -> CLAUDE.md [replace]", r.stdout)
            self.assertIn(".claude/skills/alpha/SKILL.md -> .claude/skills/alpha/SKILL.md [create]", r.stdout)
            m = f.manifest()
            self.assertEqual(m["schema_version"], 2)
            self.assertEqual(m["stack_version"], "0.1.0")
            entries = {e["path"]: e for e in m["files"]}
            self.assertEqual(set(entries), INSTALLED_PATHS)
            for name, text in CONTRACTS.items():
                e = entries[name]
                self.assertEqual(e["action"], "replace")
                self.assertEqual(e["previous_sha256"], before[name][1])
                self.assertEqual(sha(rel_path(f.target, e["backup"]).read_bytes()), e["previous_sha256"])
                self.assertEqual((f.target / name).read_text(encoding="utf-8"), text)
                self.assertEqual(e["sha256"], sha(text.encode("utf-8")))
            self.assertEqual(entries[".claude/skills/alpha/SKILL.md"]["action"], "create")
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

    def test_usage_error_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertEqual(f.run("--harness", "nope").returncode, 2)


if __name__ == "__main__":
    unittest.main()
