#!/usr/bin/env python3
"""Link-safe filesystem helpers for the adapter sync (remediation of audit finding F1).

Threat model (docs/audits/2026-09-24/static-security-audit.md, F1/F13/F14): a path component between the
repository root and an adapter target, or an entry inside the canonical ``skills/`` tree, is a symbolic link,
Windows junction or other reparse point. A naive ``rmtree``/``copytree`` then deletes or dereferences content
outside the repository. Every helper here refuses such states instead of resolving through them, verifies that
the resolved target stays inside the repository root, builds new content in a sibling staging directory, swaps it
into place with atomic renames, and deletes an old tree only afterwards and only through the same guard.

Standard library only; Python 3.10+. Nothing here follows a link, ever.

Exit-code contract (used by scripts/sync_adapters.py; each exception class carries its code):
    3  unsafe path state: link/junction/reparse point in the root->target chain or inside the source tree,
       a target that is not a directory, or a resolved path that is not contained in the repository root
    4  source tree missing or empty (fail closed; never synchronise "nothing" over an adapter)
    5  I/O failure while staging or swapping; the previous target is left in place or restored
    6  leftover staging/old directories from an interrupted earlier run are present; nothing is modified

Known limitation (documented residual risk): the checks and the operations they protect are separate system
calls, so a same-user attacker racing between them (TOCTOU) can still win a narrow window. On POSIX the
deletion path walks the directory chain with O_NOFOLLOW|O_DIRECTORY file descriptors and, on Python 3.11+,
deletes relative to that descriptor, which closes the window for the delete step; the rename steps and all
Windows code paths rely on lstat-based checks made immediately before the operation.
"""
from __future__ import annotations

import filecmp
import os
import secrets
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath

__all__ = [
    "FsSafetyError", "UnsafePathError", "SourceTreeError", "SwapError", "LeftoverStateError",
    "is_link_like", "describe_link", "check_chain", "assert_contained", "scan_tree", "tree_manifest",
    "trees_equal", "find_leftovers", "safe_rmtree", "replace_tree_atomically", "copy_file",
    "STAGED_PREFIX", "OLD_PREFIX",
]

# Windows marks junctions (and every other reparse point) with this attribute; symlinks additionally set S_IFLNK.
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MOUNT_POINT_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)

STAGED_PREFIX = ".staged-"
OLD_PREFIX = ".old-"

# Module-level indirection so tests can inject a copy failure without touching shutil itself.
copy_file = shutil.copy2


class FsSafetyError(Exception):
    """Base class; ``exit_code`` is the documented process exit status for this failure class."""

    exit_code = 3
    label = "unsafe-path"


class UnsafePathError(FsSafetyError):
    exit_code = 3
    label = "unsafe-path"


class SourceTreeError(FsSafetyError):
    exit_code = 4
    label = "source-tree"


class SwapError(FsSafetyError):
    exit_code = 5
    label = "swap-failed"


class LeftoverStateError(FsSafetyError):
    exit_code = 6
    label = "leftover-state"


# --------------------------------------------------------------------------- primitives
def is_link_like(st: os.stat_result) -> bool:
    """True for a symbolic link on any platform and for any reparse point (junction, ...) on Windows."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def describe_link(st: os.stat_result) -> str:
    if stat.S_ISLNK(st.st_mode):
        return "symbolic link"
    tag = getattr(st, "st_reparse_tag", 0)
    if tag == _MOUNT_POINT_TAG:
        return "Windows junction (reparse point)"
    return f"reparse point (tag 0x{tag:08x})"


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None


def _relative_inside(root: Path, path: Path) -> PurePosixPath:
    """Lexical relative path of ``path`` under ``root``; refuses root itself and anything outside."""
    try:
        rel = Path(path).relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"{path}: not lexically inside repository root {root}") from exc
    if not rel.parts or any(part in ("..", ".") for part in rel.parts):
        raise UnsafePathError(f"{path}: refusing to operate on the repository root or a parent-relative path")
    return PurePosixPath(*rel.parts)


def check_chain(root: Path, path: Path, *, allow_missing_leaf: bool = False, leaf_kind: str = "dir") -> bool:
    """Verify every component from ``root`` (inclusive) to ``path`` (inclusive) with lstat.

    No component may be a symbolic link, junction or reparse point; intermediate components must be plain
    directories. ``leaf_kind`` is ``"dir"`` (default), ``"file"`` or ``"any"``. Returns True when the leaf exists
    and False when it does not (only if ``allow_missing_leaf``). Raises UnsafePathError otherwise.
    """
    root = Path(root)
    path = Path(path)
    parts = _relative_inside(root, path).parts
    st_root = _lstat(root)
    if st_root is None or not stat.S_ISDIR(st_root.st_mode):
        raise UnsafePathError(f"{root}: repository root is not an existing directory")
    if is_link_like(st_root):
        raise UnsafePathError(f"{root}: repository root is a {describe_link(st_root)}; refusing")
    cur = root
    for index, part in enumerate(parts):
        cur = cur / part
        is_leaf = index == len(parts) - 1
        st = _lstat(cur)
        if st is None:
            if is_leaf and allow_missing_leaf:
                return False
            raise UnsafePathError(f"{cur}: path component does not exist")
        if is_link_like(st):
            raise UnsafePathError(f"{cur}: is a {describe_link(st)}; refusing to operate through it")
        if not is_leaf and not stat.S_ISDIR(st.st_mode):
            raise UnsafePathError(f"{cur}: intermediate path component is not a directory")
        if is_leaf and leaf_kind == "dir" and not stat.S_ISDIR(st.st_mode):
            raise UnsafePathError(f"{cur}: exists but is not a directory")
        if is_leaf and leaf_kind == "file" and not stat.S_ISREG(st.st_mode):
            raise UnsafePathError(f"{cur}: exists but is not a regular file")
    return True


def assert_contained(root: Path, path: Path) -> Path:
    """Resolve ``path`` and require it to be exactly ``realpath(root)/<lexical relative path>``.

    Because no link may appear in the chain, the resolved path must equal the lexical one; any difference means
    something in the chain redirects elsewhere. Returns the resolved path.
    """
    root = Path(root)
    parts = _relative_inside(root, Path(path)).parts
    real_root = Path(os.path.realpath(root))
    resolved = Path(os.path.realpath(path))
    expected = real_root.joinpath(*parts)
    if resolved != expected:
        raise UnsafePathError(f"{path}: resolves to {resolved}, not to its expected location {expected}")
    try:
        common = os.path.commonpath([str(real_root), str(resolved)])
    except ValueError as exc:  # different drives on Windows
        raise UnsafePathError(f"{path}: not contained in {real_root}") from exc
    if Path(common) != real_root:
        raise UnsafePathError(f"{path}: not contained in {real_root}")
    return resolved


def _classify(full: Path, *, strict: bool) -> str:
    st = os.lstat(full)
    if is_link_like(st):
        kind = "l"
    elif stat.S_ISDIR(st.st_mode):
        kind = "d"
    elif stat.S_ISREG(st.st_mode):
        kind = "f"
    else:
        kind = "o"
    if strict and kind == "l":
        raise UnsafePathError(f"{full}: {describe_link(st)} inside a tree that must not contain links")
    if strict and kind == "o":
        raise UnsafePathError(f"{full}: unsupported file type inside a tree that must contain only files")
    return kind


def tree_manifest(base: Path, *, strict: bool) -> dict[PurePosixPath, str]:
    """Map relative entry -> kind for every entry under ``base`` without following or descending into links.

    Kinds: ``d`` directory, ``f`` regular file, ``l`` link-like, ``o`` other (device, socket, FIFO).
    With ``strict`` any ``l``/``o`` entry raises UnsafePathError (used for the source and staged trees); without it
    the entry is recorded and the caller decides (used for existing targets, where it simply counts as drift).
    Link-like directories are pruned explicitly because os.walk(followlinks=False) still descends into junctions.
    """
    base = Path(base)
    manifest: dict[PurePosixPath, str] = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        keep = []
        for name in sorted(dirnames):
            kind = _classify(here / name, strict=strict)
            manifest[PurePosixPath(*(here / name).relative_to(base).parts)] = kind
            if kind == "d":
                keep.append(name)
        dirnames[:] = keep
        for name in sorted(filenames):
            kind = _classify(here / name, strict=strict)
            manifest[PurePosixPath(*(here / name).relative_to(base).parts)] = kind
    return manifest


def scan_tree(root: Path, source: Path) -> tuple[dict[PurePosixPath, str], int]:
    """Guard the canonical source tree: chain-checked, contained, link-free, non-empty. Returns (manifest, files)."""
    exists = check_chain(root, source, allow_missing_leaf=True, leaf_kind="dir")
    if not exists:
        raise SourceTreeError(f"{source}: source tree is missing")
    assert_contained(root, source)
    manifest = tree_manifest(source, strict=True)
    n_files = sum(1 for kind in manifest.values() if kind == "f")
    if n_files == 0:
        raise SourceTreeError(f"{source}: source tree contains no files; refusing to synchronise an empty tree")
    return manifest, n_files


def trees_equal(source: Path, target: Path) -> bool:
    """Strict parity: identical entry sets and kinds, byte-identical regular files, no links on either side."""
    source = Path(source)
    target = Path(target)
    st = _lstat(target)
    if st is None or is_link_like(st) or not stat.S_ISDIR(st.st_mode):
        return False
    a = tree_manifest(source, strict=True)
    b = tree_manifest(target, strict=False)
    if a != b:
        return False
    return all(filecmp.cmp(source / rel, target / rel, shallow=False) for rel, kind in a.items() if kind == "f")


def find_leftovers(target: Path) -> list[Path]:
    """Staging/old directories left by an interrupted earlier run, next to ``target``."""
    target = Path(target)
    parent = target.parent
    st = _lstat(parent)
    if st is None or not stat.S_ISDIR(st.st_mode):
        return []
    prefixes = (f".{target.name}{STAGED_PREFIX}", f".{target.name}{OLD_PREFIX}")
    return sorted(p for p in parent.iterdir() if p.name.startswith(prefixes))


# --------------------------------------------------------------------------- deletion
def _open_dir_chain(root: Path, directory: Path) -> int:
    """POSIX only: open ``directory`` by walking from ``root`` one component at a time with O_NOFOLLOW."""
    flags = os.O_RDONLY | os.O_DIRECTORY
    parts = () if Path(directory) == Path(root) else _relative_inside(root, directory).parts
    fd = os.open(root, flags)
    try:
        cur = Path(root)
        for part in parts:
            cur = cur / part
            try:
                nfd = os.open(part, flags | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as exc:
                raise UnsafePathError(f"{cur}: cannot open without following links ({exc.strerror})") from exc
            os.close(fd)
            fd = nfd
    except BaseException:
        os.close(fd)
        raise
    return fd


def safe_rmtree(root: Path, path: Path) -> None:
    """Delete the directory tree at ``path`` (strictly inside ``root``) without following any link in its chain."""
    root = Path(root)
    path = Path(path)
    check_chain(root, path, allow_missing_leaf=False, leaf_kind="dir")
    assert_contained(root, path)
    if os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"):
        fd = _open_dir_chain(root, path.parent)
        try:
            st = os.lstat(path.name, dir_fd=fd)
            if is_link_like(st) or not stat.S_ISDIR(st.st_mode):
                raise UnsafePathError(f"{path}: changed underneath us before deletion; refusing")
            if sys.version_info >= (3, 11):
                shutil.rmtree(path.name, dir_fd=fd)
            else:  # pragma: no cover - Python 3.10 keeps the narrower guarantee described in the module docstring
                shutil.rmtree(path)
        finally:
            os.close(fd)
    else:  # pragma: no cover - Windows: lstat-based guard only
        shutil.rmtree(path)


# --------------------------------------------------------------------------- staged replace
def _remove_quietly(root: Path, path: Path) -> str | None:
    """Best-effort guarded removal used for cleanup; returns an error string instead of raising."""
    try:
        if os.path.lexists(path):
            safe_rmtree(root, path)
    except (FsSafetyError, OSError) as exc:
        return f"{path}: cleanup failed ({exc})"
    return None


def replace_tree_atomically(root: Path, source: Path, target: Path, *, dry_run: bool = False) -> str:
    """Materialise ``source`` at ``target`` through a sibling staging directory and atomic renames.

    Order of operations (nothing destructive happens before step 5):
      1. guards: root->target chain, containment, leftover detection, source scan (link-free, non-empty)
      2. create the parent directory if it is missing (plain mkdir, then re-checked)
      3. copy source -> sibling ``.<name>.staged-<token>`` with links never dereferenced, verify parity
      4. rename existing target -> sibling ``.<name>.old-<token>`` (atomic)
      5. rename staged -> target (atomic); on failure rename old back into place
      6. delete the old tree through safe_rmtree
    Returns a one-line human-readable summary. With ``dry_run`` only the guards run and the plan is returned.
    """
    root = Path(root)
    source = Path(source)
    target = Path(target)
    parent = target.parent
    parent_exists = check_chain(root, parent, allow_missing_leaf=True, leaf_kind="dir")
    target_exists = parent_exists and check_chain(root, target, allow_missing_leaf=True, leaf_kind="dir")
    assert_contained(root, target if target_exists else parent)
    leftovers = find_leftovers(target)
    if leftovers:
        names = ", ".join(str(p) for p in leftovers)
        raise LeftoverStateError(f"{parent}: leftover staging state from an interrupted run: {names}; "
                                 "inspect and remove it by hand, nothing was modified")
    manifest, n_files = scan_tree(root, source)
    token = f"{os.getpid()}-{secrets.token_hex(4)}"
    staged = parent / f".{target.name}{STAGED_PREFIX}{token}"
    old = parent / f".{target.name}{OLD_PREFIX}{token}"
    rel_target = target.relative_to(root)
    if dry_run:
        state = "replace existing tree" if target_exists else "create"
        return (f"dry-run: would {state} {rel_target} from {source.relative_to(root)} "
                f"({n_files} files) via {staged.name}")

    if not os.path.lexists(parent):
        try:
            os.mkdir(parent)
        except OSError as exc:
            raise SwapError(f"{parent}: cannot create adapter parent directory ({exc})") from exc
        check_chain(root, parent, allow_missing_leaf=False, leaf_kind="dir")
        assert_contained(root, parent)

    # 3. stage next to the target; the staged tree must reproduce the scanned source exactly
    try:
        shutil.copytree(source, staged, symlinks=True, copy_function=copy_file)
        if tree_manifest(staged, strict=True) != manifest or not trees_equal(source, staged):
            raise SwapError(f"{staged}: staged copy does not match the source tree")
    except (OSError, shutil.Error, FsSafetyError) as exc:
        cleanup = _remove_quietly(root, staged)
        suffix = f"; {cleanup}" if cleanup else ""
        raise SwapError(f"{rel_target}: staging copy failed, existing target left untouched "
                        f"({exc}){suffix}") from exc

    # 4. move the existing tree aside (atomic rename, re-checked immediately before)
    if target_exists:
        try:
            check_chain(root, target, allow_missing_leaf=False, leaf_kind="dir")
            os.rename(target, old)
        except (OSError, FsSafetyError) as exc:
            _remove_quietly(root, staged)
            raise SwapError(f"{rel_target}: could not move the existing tree aside, it is untouched ({exc})") from exc

    # 5. put the staged tree in place (atomic rename); restore the old tree if that fails
    try:
        os.rename(staged, target)
    except OSError as exc:
        restore_note = ""
        if target_exists:
            try:
                os.rename(old, target)
                restore_note = "previous tree restored"
            except OSError as restore_exc:
                restore_note = f"previous tree could not be restored and remains at {old} ({restore_exc})"
        _remove_quietly(root, staged)
        raise SwapError(f"{rel_target}: swap failed ({exc}); {restore_note or 'nothing was in place before'}") from exc

    # 6. delete the old tree, through the same guard
    if target_exists:
        try:
            safe_rmtree(root, old)
        except (FsSafetyError, OSError) as exc:
            raise SwapError(f"{rel_target}: new tree is in place but the previous tree at {old} "
                            f"could not be removed ({exc})") from exc
        return f"replaced {rel_target} ({n_files} files)"
    return f"created {rel_target} ({n_files} files)"
