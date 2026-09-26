"""Unit tests for scripts/fssafety.py (link-safe helpers behind the adapter sync and the installer; audit
findings F1 and F2).

Run: python3 -m unittest tests.test_fssafety -v

Every test works inside its own temporary directory with synthetic content. Nothing in the repository is read
except the module under test, and nothing in the repository is written.
"""
import importlib.util
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("fssafety_under_test", ROOT / "scripts" / "fssafety.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fs = _load()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _symlink_or_skip(case: unittest.TestCase, target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:  # Windows without the symlink privilege, exotic filesystems
        case.skipTest(f"cannot create symbolic links on this host: {exc}")


def _listing(base: Path) -> dict:
    """Relative path -> ('d'|'f'|'l', content-or-None), never following links."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = os.lstat(p)
            rel = str(p.relative_to(base))
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("l", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("d", None)
            else:
                out[rel] = ("f", p.read_bytes())
    return out


class Fixture:
    """root/ with skills/{a,b}/SKILL.md and an external/ directory beside the root."""

    def __init__(self, tmp: str):
        self.tmp = Path(tmp)
        self.root = self.tmp / "root"
        self.source = self.root / "skills"
        self.external = self.tmp / "external"
        _write(self.source / "a" / "SKILL.md", "alpha\n")
        _write(self.source / "b" / "SKILL.md", "beta\n")
        _write(self.external / "skills" / "CANARY.txt", "canary\n")
        _write(self.external / "SIBLING.txt", "sibling\n")
        (self.root / ".claude").mkdir()


class ChainTests(unittest.TestCase):
    def test_plain_chain_ok_and_missing_leaf_reported(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertTrue(fs.check_chain(f.root, f.source))
            self.assertFalse(fs.check_chain(f.root, f.root / ".claude" / "skills", allow_missing_leaf=True))
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.root / ".claude" / "skills")  # missing leaf not allowed by default

    def test_symlinked_parent_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _symlink_or_skip(self, f.external, f.root / ".agents")
            with self.assertRaises(fs.UnsafePathError) as cm:
                fs.check_chain(f.root, f.root / ".agents" / "skills", allow_missing_leaf=True)
            self.assertIn("symbolic link", str(cm.exception))

    def test_symlinked_leaf_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _symlink_or_skip(self, f.external / "skills", f.root / ".claude" / "skills")
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.root / ".claude" / "skills", allow_missing_leaf=True)

    def test_root_and_outside_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.root)
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.external)
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.root / ".." / "external")

    def test_file_as_intermediate_or_leaf_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _write(f.root / ".agents", "not a directory\n")
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.root / ".agents" / "skills", allow_missing_leaf=True)
            with self.assertRaises(fs.UnsafePathError):
                fs.check_chain(f.root, f.root / ".agents", leaf_kind="dir")
            self.assertTrue(fs.check_chain(f.root, f.root / ".agents", leaf_kind="file"))

    def test_containment_detects_redirect_through_link(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertEqual(fs.assert_contained(f.root, f.source), Path(os.path.realpath(f.source)))
            _symlink_or_skip(self, f.external, f.root / ".agents")
            with self.assertRaises(fs.UnsafePathError):
                fs.assert_contained(f.root, f.root / ".agents" / "skills")

    def test_reparse_point_detection_is_platform_independent(self):
        junction = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x400,
                                         st_reparse_tag=0xA0000003)
        plain = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x10, st_reparse_tag=0)
        self.assertTrue(fs.is_link_like(junction))
        self.assertIn("junction", fs.describe_link(junction))
        self.assertFalse(fs.is_link_like(plain))

    @unittest.skipUnless(sys.platform == "win32", "Windows junctions (NTFS reparse points) do not exist on this host")
    def test_windows_junction_parent_refused(self):  # pragma: no cover - Windows only
        import _winapi
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            try:
                _winapi.CreateJunction(str(f.external), str(f.root / ".agents"))
            except OSError as exc:
                self.skipTest(f"junction creation not permitted for this user: {exc}")
            with self.assertRaises(fs.UnsafePathError) as cm:
                fs.check_chain(f.root, f.root / ".agents" / "skills", allow_missing_leaf=True)
            self.assertIn("reparse point", str(cm.exception))


class TreeTests(unittest.TestCase):
    def test_manifest_and_strictness(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            manifest = fs.tree_manifest(f.source, strict=True)
            self.assertEqual({str(k): v for k, v in manifest.items()},
                             {"a": "d", "b": "d", "a/SKILL.md": "f", "b/SKILL.md": "f"})
            _symlink_or_skip(self, f.external / "SIBLING.txt", f.source / "a" / "ref.md")
            with self.assertRaises(fs.UnsafePathError):
                fs.tree_manifest(f.source, strict=True)
            self.assertEqual(fs.tree_manifest(f.source, strict=False)[PurePosixPath("a/ref.md")], "l")

    def test_linked_directory_is_not_descended(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _symlink_or_skip(self, f.external, f.source / "ext")
            lax = fs.tree_manifest(f.source, strict=False)
            self.assertEqual(lax[PurePosixPath("ext")], "l")
            self.assertFalse(any(str(k).startswith("ext/") for k in lax))

    def test_scan_tree_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            manifest, n_files = fs.scan_tree(f.root, f.source)
            self.assertEqual(n_files, 2)
            empty = f.root / "empty"
            empty.mkdir()
            with self.assertRaises(fs.SourceTreeError):
                fs.scan_tree(f.root, empty)
            with self.assertRaises(fs.SourceTreeError):
                fs.scan_tree(f.root, f.root / "absent")

    def test_trees_equal(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            target = f.root / ".claude" / "skills"
            _write(target / "a" / "SKILL.md", "alpha\n")
            _write(target / "b" / "SKILL.md", "beta\n")
            self.assertTrue(fs.trees_equal(f.source, target))
            (target / "b" / "SKILL.md").write_bytes(b"changed\n")
            self.assertFalse(fs.trees_equal(f.source, target))
            (target / "b" / "SKILL.md").write_bytes(b"beta\n")
            (target / "extra").mkdir()
            self.assertFalse(fs.trees_equal(f.source, target))  # an extra (even empty) directory is drift
            self.assertFalse(fs.trees_equal(f.source, f.root / "nowhere"))


class DeleteTests(unittest.TestCase):
    def test_safe_rmtree_deletes_plain_tree_and_refuses_linked_chain(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            victim = f.root / ".claude" / "skills"
            _write(victim / "x" / "SKILL.md", "x\n")
            fs.safe_rmtree(f.root, victim)
            self.assertFalse(victim.exists())
            _symlink_or_skip(self, f.external, f.root / ".agents")
            with self.assertRaises(fs.UnsafePathError):
                fs.safe_rmtree(f.root, f.root / ".agents" / "skills")
            self.assertTrue((f.external / "skills" / "CANARY.txt").exists())
            with self.assertRaises(fs.UnsafePathError):
                fs.safe_rmtree(f.root, f.root)


class ReplaceTests(unittest.TestCase):
    def test_create_then_replace_with_no_leftovers(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            target = f.root / ".claude" / "skills"
            msg = fs.replace_tree_atomically(f.root, f.source, target)
            self.assertTrue(msg.startswith("created"))
            self.assertTrue(fs.trees_equal(f.source, target))
            (target / "a" / "SKILL.md").write_bytes(b"stale\n")
            _write(target / "zombie" / "SKILL.md", "zombie\n")
            msg = fs.replace_tree_atomically(f.root, f.source, target)
            self.assertTrue(msg.startswith("replaced"))
            self.assertTrue(fs.trees_equal(f.source, target))
            self.assertEqual(fs.find_leftovers(target), [])
            self.assertEqual(sorted(p.name for p in (f.root / ".claude").iterdir()), ["skills"])

    def test_missing_parent_is_created_plainly(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            target = f.root / ".agents" / "skills"
            fs.replace_tree_atomically(f.root, f.source, target)
            self.assertTrue(fs.trees_equal(f.source, target))
            self.assertFalse(os.path.islink(f.root / ".agents"))

    def test_dry_run_mutates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            before = _listing(f.root)
            msg = fs.replace_tree_atomically(f.root, f.source, f.root / ".claude" / "skills", dry_run=True)
            self.assertTrue(msg.startswith("dry-run: would create"))
            self.assertEqual(_listing(f.root), before)

    def test_copy_failure_leaves_existing_target_intact(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            target = f.root / ".claude" / "skills"
            _write(target / "a" / "SKILL.md", "stale-a\n")
            _write(target / "b" / "SKILL.md", "stale-b\n")
            before = _listing(f.root)
            calls = []

            def failing_copy(src, dst, *args, **kwargs):
                calls.append(src)
                if len(calls) >= 2:
                    raise OSError(5, "injected staging failure")
                return fs.shutil.copy2(src, dst, *args, **kwargs)

            with mock.patch.object(fs, "copy_file", failing_copy):
                with self.assertRaises(fs.SwapError) as cm:
                    fs.replace_tree_atomically(f.root, f.source, target)
            self.assertIn("existing target left untouched", str(cm.exception))
            self.assertEqual(_listing(f.root), before)
            self.assertEqual(fs.find_leftovers(target), [])

    def test_swap_failure_restores_previous_tree(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            target = f.root / ".claude" / "skills"
            _write(target / "a" / "SKILL.md", "stale-a\n")
            before = _listing(f.root)
            real_rename = os.rename

            def failing_rename(src, dst, *args, **kwargs):
                if fs.STAGED_PREFIX in Path(src).name:  # the staged -> target step
                    raise OSError(5, "injected swap failure")
                return real_rename(src, dst, *args, **kwargs)

            with mock.patch.object(fs.os, "rename", failing_rename):
                with self.assertRaises(fs.SwapError) as cm:
                    fs.replace_tree_atomically(f.root, f.source, target)
            self.assertIn("previous tree restored", str(cm.exception))
            self.assertEqual(_listing(f.root), before)
            self.assertEqual(fs.find_leftovers(target), [])

    def test_leftover_state_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            target = f.root / ".claude" / "skills"
            _write(f.root / ".claude" / ".skills.staged-1-deadbeef" / "a" / "SKILL.md", "orphan\n")
            before = _listing(f.root)
            with self.assertRaises(fs.LeftoverStateError):
                fs.replace_tree_atomically(f.root, f.source, target)
            self.assertEqual(_listing(f.root), before)

    def test_source_with_link_never_dereferenced(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            _symlink_or_skip(self, f.external / "SIBLING.txt", f.source / "a" / "leak.md")
            target = f.root / ".claude" / "skills"
            before = _listing(f.root)
            with self.assertRaises(fs.UnsafePathError):
                fs.replace_tree_atomically(f.root, f.source, target)
            self.assertEqual(_listing(f.root), before)
            self.assertFalse(target.exists())


class FileHelperTests(unittest.TestCase):
    """Single-file helpers behind scripts/bootstrap.py (audit finding F2)."""

    def test_chain_state_reports_missing_tail_and_refuses_links(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertEqual(fs.chain_state(f.root, f.root / ".claude" / "skills" / "x" / "SKILL.md"), (1, None))
            existing, st = fs.chain_state(f.root, f.source / "a" / "SKILL.md")
            self.assertEqual(existing, 3)
            self.assertTrue(stat.S_ISREG(st.st_mode))
            with self.assertRaises(fs.UnsafePathError):
                fs.chain_state(f.root, f.root)
            _symlink_or_skip(self, f.root / "nowhere", f.root / "dangling")
            with self.assertRaises(fs.UnsafePathError):
                fs.chain_state(f.root, f.root / "dangling")
            with self.assertRaises(fs.UnsafePathError):
                fs.chain_state(f.root, f.root / "dangling" / "child")

    def test_classify_destination(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertEqual(fs.classify_destination(f.root, f.root / "new.txt"), "missing")
            self.assertEqual(fs.classify_destination(f.root, f.root / ".claude" / "skills" / "x.txt"), "missing")
            self.assertEqual(fs.classify_destination(f.root, f.source / "a" / "SKILL.md"), "file")
            with self.assertRaises(fs.UnsafePathError):
                fs.classify_destination(f.root, f.source)  # a directory
            _symlink_or_skip(self, f.external / "SIBLING.txt", f.root / "link.txt")
            with self.assertRaises(fs.UnsafePathError):
                fs.classify_destination(f.root, f.root / "link.txt")
            linked = f.root / "linked.txt"
            try:
                os.link(f.source / "a" / "SKILL.md", linked)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"hard links unavailable on this host: {exc}")
            with self.assertRaises(fs.UnsafePathError) as cm:
                fs.classify_destination(f.root, linked)
            self.assertIn("hard links", str(cm.exception))
            self.assertEqual(fs.classify_destination(f.root, linked, allow_hard_links=True), "file")

    def test_write_regular_atomically_creates_replaces_and_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            dst = f.root / "out.txt"
            fs.write_regular_atomically(f.root, dst, b"one\n", mode=0o640, expect_existing=False)
            self.assertEqual(dst.read_bytes(), b"one\n")
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(os.stat(dst).st_mode), 0o640)
            fs.write_regular_atomically(f.root, dst, b"two\n", expect_existing=True)
            self.assertEqual(dst.read_bytes(), b"two\n")
            with self.assertRaises(fs.UnsafePathError):
                fs.write_regular_atomically(f.root, dst, b"x", expect_existing=False)
            with self.assertRaises(fs.UnsafePathError):
                fs.write_regular_atomically(f.root, f.root / "absent.txt", b"x", expect_existing=True)
            with self.assertRaises(fs.UnsafePathError):
                fs.write_regular_atomically(f.root, f.source, b"x")  # a directory
            with self.assertRaises(fs.UnsafePathError):
                fs.write_regular_atomically(f.root, f.root / "missing-dir" / "x.txt", b"x")  # parent missing
            self.assertEqual(dst.read_bytes(), b"two\n")
            self.assertEqual(sorted(p.name for p in f.root.iterdir()), [".claude", "out.txt", "skills"],
                             "no temporary file may be left behind")
            _symlink_or_skip(self, f.external / "SIBLING.txt", f.root / "link.txt")
            with self.assertRaises(fs.UnsafePathError):
                fs.write_regular_atomically(f.root, f.root / "link.txt", b"leak\n")
            self.assertEqual((f.external / "SIBLING.txt").read_text(encoding="utf-8"), "sibling\n")
            _symlink_or_skip(self, f.external / "nothing-here", f.root / "dangling.txt")
            with self.assertRaises(fs.UnsafePathError):
                fs.write_regular_atomically(f.root, f.root / "dangling.txt", b"leak\n")
            self.assertFalse((f.external / "nothing-here").exists())

    def test_write_failure_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            dst = f.root / "out.txt"
            dst.write_bytes(b"old\n")
            before = _listing(f.root)
            with mock.patch.object(fs.os, "replace", side_effect=OSError(5, "injected rename failure")):
                with self.assertRaises(OSError):
                    fs.write_regular_atomically(f.root, dst, b"new\n")
            self.assertEqual(_listing(f.root), before)

    def test_mkdir_chain_rmdir_and_unlink(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            created = fs.mkdir_chain(f.root, f.root / ".agents" / "skills" / "x")
            self.assertEqual([p.relative_to(f.root).as_posix() for p in created],
                             [".agents", ".agents/skills", ".agents/skills/x"])
            self.assertEqual(fs.mkdir_chain(f.root, f.root / ".agents" / "skills"), [])
            self.assertEqual(fs.mkdir_chain(f.root, f.root), [])
            with self.assertRaises(fs.UnsafePathError):
                fs.mkdir_chain(f.root, f.source / "a" / "SKILL.md" / "sub")  # a file in the chain
            target = f.root / ".agents" / "skills" / "x" / "SKILL.md"
            fs.write_regular_atomically(f.root, target, b"x\n")
            self.assertFalse(fs.rmdir_if_empty(f.root, target.parent))
            with self.assertRaises(fs.UnsafePathError):
                fs.unlink_regular_nofollow(f.root, target, expect_sha256="0" * 64)
            self.assertTrue(target.exists())
            fs.unlink_regular_nofollow(f.root, target, expect_sha256=fs.sha256_bytes(b"x\n"))
            self.assertFalse(target.exists())
            self.assertTrue(fs.rmdir_if_empty(f.root, target.parent))
            self.assertTrue(fs.rmdir_if_empty(f.root, target.parent))  # already gone
            _symlink_or_skip(self, f.external / "SIBLING.txt", f.root / "link.txt")
            with self.assertRaises(fs.UnsafePathError):
                fs.unlink_regular_nofollow(f.root, f.root / "link.txt")
            self.assertTrue(os.path.islink(f.root / "link.txt"))

    def test_read_and_replace_regular_nofollow(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(d)
            self.assertEqual(fs.read_regular_nofollow(f.root, f.source / "a" / "SKILL.md"), b"alpha\n")
            with self.assertRaises(fs.UnsafePathError):
                fs.read_regular_nofollow(f.root, f.root / "absent.txt")
            _symlink_or_skip(self, f.external / "SIBLING.txt", f.root / "link.txt")
            with self.assertRaises(fs.UnsafePathError):
                fs.read_regular_nofollow(f.root, f.root / "link.txt")
            src = f.root / "moving.txt"
            src.write_bytes(b"moved\n")
            fs.replace_regular_nofollow(f.root, src, f.source / "a" / "SKILL.md")
            self.assertFalse(src.exists())
            self.assertEqual((f.source / "a" / "SKILL.md").read_bytes(), b"moved\n")
            with self.assertRaises(fs.UnsafePathError):
                fs.replace_regular_nofollow(f.root, f.root / "link.txt", f.root / "elsewhere.txt")


if __name__ == "__main__":
    unittest.main()
