"""Focused regression tests for audit finding F1 in scripts/sync_adapters.py (T1.1 .. T1.6).

Run: python3 -m unittest tests.test_sync_adapters -v

Each test builds its own synthetic repository inside a temporary directory: a copy of scripts/sync_adapters.py
and scripts/fssafety.py, a small synthetic skills/ tree, adapter directories in the requested state, and an
external canary directory beside the repository. The real repository's adapter directories are never touched.

  T1.1  POSIX symlinked `.agents` parent      -> exit 3, canary intact, nothing modified
  T1.2  Windows junction `.agents` parent     -> exit 3 (skipped with the reason where junctions cannot be made)
  T1.3  symlinked final target                -> exit 3, canary intact
  T1.4  symlink inside the source skills tree -> exit 3, adapters unchanged, linked content never materialised
  T1.5  injected staged-copy failure          -> exit 5, existing target byte-identical, no leftovers
  T1.6  --dry-run mutates nothing; a normal sync reaches parity with skills/ and --check confirms it
"""
import contextlib
import hashlib
import importlib.util
import io
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
SKILLS = {"alpha": "# alpha\nsynthetic skill alpha\n", "beta": "# beta\nsynthetic skill beta\n",
          "gamma": "# gamma\nsynthetic skill gamma\n"}
EXIT_UNSAFE, EXIT_SOURCE, EXIT_SWAP, EXIT_LEFTOVER = 3, 4, 5, 6


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp: Path, adapters: str = "drift") -> Path:
    """adapters: 'drift' (stale content), 'in-sync' (parity), or 'missing' (empty .claude/ and .agents/)."""
    repo = tmp / "repo"
    (repo / "scripts").mkdir(parents=True)
    for name in ("sync_adapters.py", "fssafety.py"):
        shutil.copy2(SCRIPTS / name, repo / "scripts" / name)
    for skill, text in SKILLS.items():
        _write(repo / "skills" / skill / "SKILL.md", text)
    for parent in (".claude", ".agents"):
        (repo / parent).mkdir()
        if adapters == "missing":
            continue
        for skill, text in SKILLS.items():
            _write(repo / parent / "skills" / skill / "SKILL.md", text if adapters == "in-sync" else "stale\n")
    return repo


def make_canary(tmp: Path) -> Path:
    canary = tmp / "canary"
    _write(canary / "skills" / "CANARY-A.txt", "canary A\n")
    _write(canary / "skills" / "nested" / "CANARY-B.txt", "canary B\n")
    _write(canary / "SIBLING.txt", "sibling\n")
    return canary


def run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")  # keep the interpreter's bytecode cache out of the fixture
    return subprocess.run([sys.executable, str(repo / "scripts" / "sync_adapters.py"), *args],
                          capture_output=True, text=True, cwd=str(repo), env=env)


def snapshot(base: Path) -> dict:
    """Relative path -> ('d'|'f'|'l', sha256-or-link-target), without following links."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]  # interpreter bytecode cache, not sync output
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = os.lstat(p)
            rel = str(p.relative_to(base))
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("l", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("d", None)
            else:
                out[rel] = ("f", hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def symlink_or_skip(case: unittest.TestCase, target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        case.skipTest(f"cannot create symbolic links on this host: {exc}")


def load_module(repo: Path):
    """Import the fixture's copy of sync_adapters.py in-process (it imports the fixture's fssafety.py)."""
    sys.modules.pop("fssafety", None)
    spec = importlib.util.spec_from_file_location("sync_adapters_under_test", repo / "scripts" / "sync_adapters.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RefusalTests(unittest.TestCase):
    """T1.1 .. T1.4: unsafe path states are refused before anything is modified."""

    def _assert_refused_everywhere(self, repo: Path, canary: Path, needle: str, canary_before: dict,
                                   claude_before: dict) -> None:
        for args in ((), ("--check",), ("--dry-run",)):
            r = run_cli(repo, *args)
            self.assertEqual(r.returncode, EXIT_UNSAFE, f"{args}: {r.stdout}{r.stderr}")
            self.assertIn("ERROR[unsafe-path]", r.stderr)
            self.assertIn(needle, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertEqual(r.stdout, "", "nothing may be synchronised or reported as synchronised")
        self.assertEqual(snapshot(canary), canary_before, "external canary must be intact")
        self.assertEqual(snapshot(repo / ".claude"), claude_before, "the other adapter must be untouched")

    def test_t1_1_symlinked_agents_parent_refused(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            canary = make_canary(tmp)
            shutil.rmtree(repo / ".agents")
            symlink_or_skip(self, canary, repo / ".agents")
            canary_before, claude_before = snapshot(canary), snapshot(repo / ".claude")
            self._assert_refused_everywhere(repo, canary, "symbolic link", canary_before, claude_before)
            self.assertTrue((canary / "skills" / "CANARY-A.txt").exists())
            self.assertTrue(os.path.islink(repo / ".agents"))

    @unittest.skipUnless(sys.platform == "win32",
                         "T1.2 requires Windows: junctions are NTFS reparse points and cannot be created on this host")
    def test_t1_2_windows_junction_parent_refused(self):  # pragma: no cover - Windows only
        import _winapi
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            canary = make_canary(tmp)
            shutil.rmtree(repo / ".agents")
            try:
                _winapi.CreateJunction(str(canary), str(repo / ".agents"))
            except OSError as exc:
                self.skipTest(f"T1.2 skipped: junction creation not permitted for this user: {exc}")
            canary_before, claude_before = snapshot(canary), snapshot(repo / ".claude")
            self._assert_refused_everywhere(repo, canary, "reparse point", canary_before, claude_before)

    def test_t1_3_symlinked_final_target_refused(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            canary = make_canary(tmp)
            shutil.rmtree(repo / ".agents" / "skills")
            symlink_or_skip(self, canary / "skills", repo / ".agents" / "skills")
            canary_before, claude_before = snapshot(canary), snapshot(repo / ".claude")
            self._assert_refused_everywhere(repo, canary, "symbolic link", canary_before, claude_before)
            self.assertTrue(os.path.islink(repo / ".agents" / "skills"))

    def test_t1_4_symlink_inside_source_refused_and_never_dereferenced(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            secret = tmp / "secret"
            _write(secret / "SKILL.md", "SECRET-MATERIAL-MUST-NOT-LEAK\n")
            _write(tmp / "secret.txt", "SECRET-FILE-MUST-NOT-LEAK\n")
            symlink_or_skip(self, secret, repo / "skills" / "evil")
            symlink_or_skip(self, tmp / "secret.txt", repo / "skills" / "alpha" / "ref.md")
            before = {p: snapshot(repo / p) for p in (".claude", ".agents")}
            for args in ((), ("--check",), ("--dry-run",)):
                r = run_cli(repo, *args)
                self.assertEqual(r.returncode, EXIT_UNSAFE, f"{args}: {r.stdout}{r.stderr}")
                self.assertIn("ERROR[unsafe-path]", r.stderr)
                self.assertIn("symbolic link", r.stderr)
                self.assertNotIn("Traceback", r.stderr)
            for p in (".claude", ".agents"):
                self.assertEqual(snapshot(repo / p), before[p])
                for f in (repo / p).rglob("*"):
                    if f.is_file():
                        self.assertNotIn(b"MUST-NOT-LEAK", f.read_bytes())


class FailureInjectionTests(unittest.TestCase):
    """T1.5: a failure while staging or swapping leaves the existing target byte-identical, with no leftovers."""

    def test_t1_5_staged_copy_failure_leaves_target_intact(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            mod = load_module(repo)
            before = snapshot(repo)
            calls = []

            def failing_copy(src, dst, *args, **kwargs):
                calls.append(src)
                if len(calls) >= 2:
                    raise OSError(5, "injected staging failure")
                return shutil.copy2(src, dst, *args, **kwargs)

            err = io.StringIO()
            with mock.patch.object(mod.fssafety, "copy_file", failing_copy), contextlib.redirect_stderr(err):
                rc = mod.main([], root=repo)
            self.assertEqual(rc, EXIT_SWAP)
            self.assertIn("ERROR[swap-failed]", err.getvalue())
            self.assertIn("existing target left untouched", err.getvalue())
            self.assertEqual(snapshot(repo), before, "no file may change when staging fails")
            for parent in (".claude", ".agents"):
                self.assertEqual(mod.fssafety.find_leftovers(repo / parent / "skills"), [])
            # recovery: with the fault removed the same tree synchronises normally
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(mod.main([], root=repo), 0)
            for parent in (".claude", ".agents"):
                self.assertTrue(mod.fssafety.trees_equal(repo / "skills", repo / parent / "skills"))

    def test_t1_5b_swap_failure_restores_previous_tree(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            mod = load_module(repo)
            before = snapshot(repo)
            real_rename = os.rename

            def failing_rename(src, dst, *args, **kwargs):
                if mod.fssafety.STAGED_PREFIX in Path(src).name:
                    raise OSError(5, "injected swap failure")
                return real_rename(src, dst, *args, **kwargs)

            err = io.StringIO()
            with mock.patch.object(os, "rename", failing_rename), contextlib.redirect_stderr(err):
                rc = mod.main([], root=repo)
            self.assertEqual(rc, EXIT_SWAP)
            self.assertIn("previous tree restored", err.getvalue())
            self.assertEqual(snapshot(repo), before)


class DryRunAndParityTests(unittest.TestCase):
    """T1.6 plus the fail-closed --check and leftover-state contracts."""

    def test_t1_6_dry_run_then_sync_reaches_parity(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo = make_repo(tmp, adapters="drift")
            before = snapshot(repo)
            r = run_cli(repo, "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("dry-run: would replace existing tree", r.stdout)
            self.assertIn("nothing was modified", r.stdout)
            self.assertEqual(snapshot(repo), before, "--dry-run must not change a single byte")
            r = run_cli(repo, "--check")
            self.assertEqual(r.returncode, 1)
            self.assertIn("Adapter drift:", r.stderr)
            r = run_cli(repo)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Synchronized 3 skills to Claude and Codex adapters.", r.stdout)
            skills = snapshot(repo / "skills")
            for parent in (".claude", ".agents"):
                self.assertEqual(snapshot(repo / parent / "skills"), skills)
                self.assertEqual(sorted(p.name for p in (repo / parent).iterdir()), ["skills"], "no leftovers")
            r = run_cli(repo, "--check")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Adapter parity: OK", r.stdout)
            r = run_cli(repo)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(".claude/skills: in sync, unchanged".replace("/", os.sep), r.stdout)

    def test_sync_creates_missing_targets(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), adapters="missing")
            r = run_cli(repo, "--check")
            self.assertEqual(r.returncode, 1)
            r = run_cli(repo)
            self.assertEqual(r.returncode, 0, r.stderr)
            skills = snapshot(repo / "skills")
            for parent in (".claude", ".agents"):
                self.assertEqual(snapshot(repo / parent / "skills"), skills)

    def test_check_and_sync_fail_closed_on_missing_or_empty_source(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), adapters="in-sync")
            before = snapshot(repo / ".claude")
            shutil.rmtree(repo / "skills")
            for args in (("--check",), (), ("--dry-run",)):
                r = run_cli(repo, *args)
                self.assertEqual(r.returncode, EXIT_SOURCE, f"{args}: {r.stdout}{r.stderr}")
                self.assertIn("ERROR[source-tree]", r.stderr)
            (repo / "skills").mkdir()
            for args in (("--check",), ()):
                r = run_cli(repo, *args)
                self.assertEqual(r.returncode, EXIT_SOURCE, f"{args}: {r.stdout}{r.stderr}")
            self.assertEqual(snapshot(repo / ".claude"), before, "adapters must survive a missing/empty source")

    def test_leftover_staging_state_refused(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), adapters="drift")
            _write(repo / ".claude" / ".skills.staged-1-deadbeef" / "alpha" / "SKILL.md", "orphan\n")
            before = snapshot(repo)
            r = run_cli(repo)
            self.assertEqual(r.returncode, EXIT_LEFTOVER, r.stderr)
            self.assertIn("ERROR[leftover-state]", r.stderr)
            self.assertEqual(snapshot(repo), before)

    def test_usage_error_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), adapters="in-sync")
            r = run_cli(repo, "--check", "--dry-run")
            self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
