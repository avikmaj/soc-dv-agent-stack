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

File-level helpers (remediation of audit finding F2, used by scripts/bootstrap.py): ``chain_state``,
``classify_destination``, ``read_regular_nofollow``, ``write_regular_atomically``, ``mkdir_chain``,
``unlink_regular_nofollow``, ``rmdir_if_empty`` and ``replace_regular_nofollow`` apply the same rules to single
files below a root directory: no link-like component anywhere in the chain (a dangling link is a link), no
directory or special file where a regular file is expected, no regular file with more than one hard link as a
write destination, temporary-file-plus-rename replacement in the destination directory, and, on POSIX, file
operations relative to a directory descriptor opened with O_NOFOLLOW at every step.

Windows read-only attribute (audit finding F17): deleting or replacing a file that carries FILE_ATTRIBUTE_READONLY
fails with ERROR_ACCESS_DENIED. Immediately before such a delete or replace, and only after the entry was lstat'ed
as a plain (non-link) file or directory, the attribute is cleared with os.chmod so the operation neither fails
half-way nor is skipped silently; the tree deletion retries a refused entry once after clearing it. On other
platforms this is a no-op.
"""
from __future__ import annotations

import errno
import filecmp
import hashlib
import os
import secrets
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath

__all__ = [
    "FsSafetyError", "UnsafePathError", "SourceTreeError", "SwapError", "LeftoverStateError",
    "is_link_like", "describe_link", "lstat_or_none", "check_chain", "assert_contained", "scan_tree",
    "tree_manifest", "trees_equal", "find_leftovers", "safe_rmtree", "replace_tree_atomically", "copy_file",
    "STAGED_PREFIX", "OLD_PREFIX",
    "sha256_bytes", "chain_state", "classify_destination", "read_regular_nofollow", "write_regular_atomically",
    "mkdir_chain", "unlink_regular_nofollow", "rmdir_if_empty", "replace_regular_nofollow", "TMP_INFIX",
]

# Windows marks junctions (and every other reparse point) with this attribute; symlinks additionally set S_IFLNK.
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MOUNT_POINT_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
_READONLY = getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
_WINDOWS = os.name == "nt"

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


def lstat_or_none(path: Path) -> os.stat_result | None:
    """lstat without following the final component; None when the path (or one of its parents) is missing."""
    return _lstat(Path(path))


def _has_readonly_attribute(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_file_attributes", 0) & _READONLY)


def _clear_readonly(path: Path, st: os.stat_result) -> None:
    """Windows only: drop the read-only attribute of the plain entry ``path`` whose lstat ``st`` was taken just now.

    The delete or replace attempted next would otherwise fail with ERROR_ACCESS_DENIED. os.chmod follows links on
    Windows before Python 3.13, hence the lstat guard. Nothing to do on other platforms.
    """
    if not _WINDOWS or not _has_readonly_attribute(st):
        return
    if is_link_like(st):
        raise UnsafePathError(f"{path}: is a {describe_link(st)}; refusing to change its attributes")
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def _retry_readonly_delete(func, failed, exc: BaseException) -> None:
    """rmtree error hook: a delete refused because the entry is read-only clears the attribute (after an lstat
    guard against links) and retries once; every other failure propagates unchanged."""
    if func in (os.unlink, os.rmdir) and isinstance(exc, PermissionError):
        st = _lstat(Path(failed))
        if st is not None and not is_link_like(st) and _has_readonly_attribute(st):
            _clear_readonly(Path(failed), st)
            func(failed)
            return
    raise exc


def _rmtree_clearing_readonly(path: Path) -> None:
    """shutil.rmtree for the lstat-guarded (Windows) branch, retrying read-only entries once."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_readonly_delete)
    else:  # pragma: no cover - ``onerror`` is the pre-3.12 spelling of the same hook
        shutil.rmtree(path, onerror=lambda func, failed, exc_info: _retry_readonly_delete(func, failed, exc_info[1]))


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
    else:  # pragma: no cover - Windows: lstat-based guard only; read-only entries are cleared and retried once
        _rmtree_clearing_readonly(path)


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


# --------------------------------------------------------------------------- single-file helpers (F2)
TMP_INFIX = ".tmp-"

# Directory-descriptor-relative operations close the leaf-level race between check and use. They need POSIX
# O_NOFOLLOW/O_DIRECTORY and dir_fd support for every call used below; elsewhere (Windows) the helpers fall back
# to lstat checks made immediately before each path-based operation.
_DIR_FD_OPS = os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY") and all(
    fn in os.supports_dir_fd for fn in (os.open, os.replace, os.unlink, os.lstat))
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_root(root: Path) -> None:
    st_root = _lstat(root)
    if st_root is None or not stat.S_ISDIR(st_root.st_mode):
        raise UnsafePathError(f"{root}: root is not an existing directory")
    if is_link_like(st_root):
        raise UnsafePathError(f"{root}: root is a {describe_link(st_root)}; refusing")


def chain_state(root: Path, path: Path) -> tuple[int, os.stat_result | None]:
    """Walk ``root`` -> ``path`` with lstat, refusing any link-like component and any non-directory intermediate.

    Returns ``(existing, leaf_stat)``: ``existing`` is the number of components below ``root`` that exist, and
    ``leaf_stat`` is the lstat result of the leaf when every component exists (None otherwise). A dangling
    symbolic link exists as far as lstat is concerned and is therefore refused like any other link.
    """
    root = Path(root)
    path = Path(path)
    parts = _relative_inside(root, path).parts
    _check_root(root)
    cur = root
    st = None
    for index, part in enumerate(parts):
        cur = cur / part
        st = _lstat(cur)
        if st is None:
            return index, None
        if is_link_like(st):
            raise UnsafePathError(f"{cur}: is a {describe_link(st)}; refusing to operate through it")
        if index < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise UnsafePathError(f"{cur}: intermediate path component is not a directory")
    return len(parts), st


def classify_destination(root: Path, path: Path, *, allow_hard_links: bool = False) -> str:
    """``"missing"`` or ``"file"`` (a plain regular file); every other state raises UnsafePathError.

    Refused: any link-like component in the chain (including a dangling link at the leaf), a directory or special
    file at the leaf, and, unless ``allow_hard_links`` is set, a regular file with more than one hard link (writing
    it in place, or replacing it, would surprise whoever owns the other name).
    """
    root = Path(root)
    path = Path(path)
    _, st = chain_state(root, path)
    assert_contained(root, path)
    if st is None:
        return "missing"
    if stat.S_ISDIR(st.st_mode):
        raise UnsafePathError(f"{path}: destination exists and is a directory")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafePathError(f"{path}: destination exists and is not a regular file")
    if not allow_hard_links and st.st_nlink > 1:
        raise UnsafePathError(f"{path}: destination has {st.st_nlink} hard links; refusing to write a shared inode")
    return "file"


def _open_parent(root: Path, path: Path) -> int | None:
    """POSIX: descriptor of ``path.parent`` reached from ``root`` with O_NOFOLLOW at every step; else None."""
    if not _DIR_FD_OPS:
        return None
    return _open_dir_chain(root, Path(path).parent)


def _read_fd(fd: int) -> bytes:
    chunks = []
    while True:
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _write_fd(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def read_regular_nofollow(root: Path, path: Path, *, allow_hard_links: bool = False) -> bytes:
    """Read the regular file at ``path`` (below ``root``) without following any link in its chain."""
    root = Path(root)
    path = Path(path)
    if classify_destination(root, path, allow_hard_links=allow_hard_links) != "file":
        raise UnsafePathError(f"{path}: file does not exist")
    dfd = _open_parent(root, path)
    try:
        flags = os.O_RDONLY | _O_NOFOLLOW | _O_BINARY
        try:
            fd = os.open(path.name, flags, dir_fd=dfd) if dfd is not None else os.open(path, flags)
        except OSError as exc:
            if exc.errno == getattr(errno, "ELOOP", None):
                raise UnsafePathError(f"{path}: became a symbolic link before it was opened; refusing") from exc
            raise
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or (not allow_hard_links and st.st_nlink > 1):
                raise UnsafePathError(f"{path}: changed underneath us before reading; refusing")
            return _read_fd(fd)
        finally:
            os.close(fd)
    finally:
        if dfd is not None:
            os.close(dfd)


def write_regular_atomically(root: Path, path: Path, data: bytes, *, mode: int = 0o644,
                             expect_existing: bool | None = None) -> None:
    """Create or replace the regular file at ``path`` (below ``root``) atomically and without following links.

    Guards: link-free chain, containment, destination missing or a plain singly-linked regular file
    (``expect_existing`` pins which of the two is acceptable). The bytes go to a sibling temporary file created
    with O_CREAT|O_EXCL (O_NOFOLLOW where available), are fsync'ed, given ``mode``, and moved over the destination
    with ``os.replace`` (same directory, hence same volume); the destination is re-checked with lstat immediately
    before the rename. On any failure the temporary file is removed and the destination is left as it was.
    """
    root = Path(root)
    path = Path(path)
    kind = classify_destination(root, path)
    if expect_existing is True and kind != "file":
        raise UnsafePathError(f"{path}: expected an existing file to replace, found none")
    if expect_existing is False and kind != "missing":
        raise UnsafePathError(f"{path}: expected no existing file, found one")
    parent = path.parent
    st_parent = _lstat(parent)
    if st_parent is None or not stat.S_ISDIR(st_parent.st_mode) or is_link_like(st_parent):
        raise UnsafePathError(f"{parent}: destination directory is missing or not a plain directory")
    tmp_name = f".{path.name}{TMP_INFIX}{os.getpid()}-{secrets.token_hex(4)}"
    dfd = _open_parent(root, path)
    tmp_created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY
        if dfd is not None:
            fd = os.open(tmp_name, flags, 0o600, dir_fd=dfd)
        else:
            fd = os.open(parent / tmp_name, flags, 0o600)
        tmp_created = True
        try:
            _write_fd(fd, data)
            os.fsync(fd)
            if hasattr(os, "fchmod"):
                os.fchmod(fd, mode & 0o777)
        finally:
            os.close(fd)
        try:
            st_now = os.lstat(path.name, dir_fd=dfd) if dfd is not None else os.lstat(path)
        except FileNotFoundError:
            st_now = None
        if st_now is not None and (kind == "missing" or is_link_like(st_now) or not stat.S_ISREG(st_now.st_mode)
                                   or st_now.st_nlink > 1):
            raise UnsafePathError(f"{path}: destination changed underneath us before the rename; refusing")
        if st_now is not None:
            _clear_readonly(path, st_now)  # Windows: a read-only destination would make os.replace fail
        if dfd is not None:
            os.replace(tmp_name, path.name, src_dir_fd=dfd, dst_dir_fd=dfd)
            try:
                os.fsync(dfd)
            except OSError:  # pragma: no cover - directory fsync is best effort
                pass
        else:
            os.replace(parent / tmp_name, path)
        tmp_created = False
    finally:
        if tmp_created:
            try:
                if dfd is not None:
                    os.unlink(tmp_name, dir_fd=dfd)
                else:
                    os.unlink(parent / tmp_name)
            except OSError:  # pragma: no cover - nothing more can be done for a stray temporary file
                pass
        if dfd is not None:
            os.close(dfd)


def mkdir_chain(root: Path, directory: Path) -> list[Path]:
    """Create the missing components of ``directory`` (below ``root``) one at a time as plain directories.

    Returns the directories created, top-most first, so a caller can remove them again on rollback. Existing
    components must be plain directories; a link anywhere in the chain is refused before anything is created.
    """
    root = Path(root)
    directory = Path(directory)
    if directory == root:
        _check_root(root)
        return []
    existing, st = chain_state(root, directory)
    assert_contained(root, directory)
    parts = _relative_inside(root, directory).parts
    if st is not None:
        if not stat.S_ISDIR(st.st_mode):
            raise UnsafePathError(f"{directory}: exists and is not a directory")
        return []
    created: list[Path] = []
    cur = root.joinpath(*parts[:existing])
    for part in parts[existing:]:
        cur = cur / part
        os.mkdir(cur, 0o755)
        st_new = _lstat(cur)
        if st_new is None or is_link_like(st_new) or not stat.S_ISDIR(st_new.st_mode):
            raise UnsafePathError(f"{cur}: created directory changed underneath us; refusing")
        created.append(cur)
    return created


def unlink_regular_nofollow(root: Path, path: Path, *, expect_sha256: str | None = None) -> None:
    """Delete the regular file at ``path`` (below ``root``); with ``expect_sha256`` only if its content matches."""
    root = Path(root)
    path = Path(path)
    if classify_destination(root, path) != "file":
        raise UnsafePathError(f"{path}: not an existing regular file")
    if expect_sha256 is not None and sha256_bytes(read_regular_nofollow(root, path)) != expect_sha256:
        raise UnsafePathError(f"{path}: content differs from the recorded hash; refusing to delete it")
    dfd = _open_parent(root, path)
    try:
        st = os.lstat(path.name, dir_fd=dfd) if dfd is not None else os.lstat(path)
        if is_link_like(st) or not stat.S_ISREG(st.st_mode):
            raise UnsafePathError(f"{path}: changed underneath us before deletion; refusing")
        _clear_readonly(path, st)
        if dfd is not None:
            os.unlink(path.name, dir_fd=dfd)
        else:
            os.unlink(path)
    finally:
        if dfd is not None:
            os.close(dfd)


def rmdir_if_empty(root: Path, path: Path) -> bool:
    """Remove the plain directory at ``path`` (below ``root``) if it is empty; True when it is gone afterwards."""
    root = Path(root)
    path = Path(path)
    if path == root:
        return False
    _, st = chain_state(root, path)
    if st is None:
        return True
    if not stat.S_ISDIR(st.st_mode):
        raise UnsafePathError(f"{path}: not a directory")
    try:
        os.rmdir(path)
    except OSError as exc:
        if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
            return False
        if isinstance(exc, PermissionError) and _has_readonly_attribute(st):  # Windows read-only directory
            _clear_readonly(path, st)
            os.rmdir(path)
            return True
        raise
    return True


def replace_regular_nofollow(root: Path, src: Path, dst: Path) -> None:
    """Atomically move the regular file ``src`` over ``dst`` (both below ``root``); links and directories refused."""
    root = Path(root)
    src = Path(src)
    dst = Path(dst)
    if classify_destination(root, src) != "file":
        raise UnsafePathError(f"{src}: not an existing regular file")
    classify_destination(root, dst)
    st_dst = _lstat(dst)
    if st_dst is not None:
        if is_link_like(st_dst) or not stat.S_ISREG(st_dst.st_mode):
            raise UnsafePathError(f"{dst}: changed underneath us before the rename; refusing")
        _clear_readonly(dst, st_dst)
    os.replace(src, dst)
