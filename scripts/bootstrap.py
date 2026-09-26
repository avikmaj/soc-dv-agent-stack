#!/usr/bin/env python3
"""Project-local installer for the SoC DV agent stack (link-safe rewrite; audit findings F2, F8, F9, F14, F17, F18).

Usage:
    python scripts/bootstrap.py --target ../my-dv-project [--harness claude|codex|all] [--dry-run] [--force]

What it installs into the target project: CLAUDE.md and .claude/skills/<skill>/... (harness ``claude``), AGENTS.md
and .agents/skills/<skill>/... (harness ``codex``), .soc-dv/config.json from the template when the project has no
config yet, and .soc-dv/install-manifest.json describing the installation. Skills are installed whole: every
regular file below skills/<skill>/ in the canonical tree, byte for byte, after both adapter trees have been
verified to be identical to that tree.

Safety model (docs/audits/2026-09-24/static-security-audit.md):
  * Target (F8): the path given must exist and be a plain directory, and no component between the filesystem
    anchor and the target may be a symbolic link, junction or other reparse point. Refused outright: filesystem
    anchors (POSIX ``/``, Windows drive and UNC roots); the home directory and every ancestor of it; every hidden
    entry directly below the home directory together with everything inside it (~/.config, ~/.claude, ~/.codex,
    ~/.ssh, ~/.local: user configuration and agent control-plane locations, audit TB8); the stack checkout itself,
    anything inside it and every ancestor of it; and well-known system prefixes (/etc, /usr, /bin, /sbin, /lib,
    /lib64, /boot, /sys, /proc, /dev, /root; on Windows %SystemRoot%, %ProgramFiles%, %ProgramFiles(x86)%,
    %ProgramData%, %windir% and %APPDATA% when set). Ordinary subdirectories of the home directory (~/projects/x)
    and temporary directories stay allowed; whether the target is a git repository is not checked.
  * Destinations (F2): every destination is checked with lstat from the target downwards: no symbolic link,
    junction or other reparse point anywhere in the chain (a dangling link counts as a link), no directory or
    special file where a file is expected, and no regular file with more than one hard link. Any such state fails
    closed before the first write, with or without --force. Files are written to a sibling temporary file and moved
    into place with os.replace; the manifest and the journal get the same treatment.
  * Sources (F14, F18): VERSION, CLAUDE.md, AGENTS.md, the config template and every skill file are read and
    checked before the first write. The canonical skills/ tree must be link-free and non-empty, every skill
    directory must carry a SKILL.md, every relative path component must match ``[A-Za-z0-9][A-Za-z0-9._-]*``, and
    both adapter trees (.claude/skills, .agents/skills) must be identical to skills/; otherwise nothing is
    installed (exit 4), whichever harness was selected.
  * Existing files (F9): identical files are left untouched; differing files are replaced only with --force, after
    a backup copy under .soc-dv/backups/<install_id>/ whose path and hash (previous_sha256) are recorded in the
    manifest. A previous manifest is backed up and referenced from the new one.
  * Every mutation is journaled (.soc-dv/journal/<install_id>.jsonl, append-only, fsync'ed). A failure rolls the
    run back from that journal: created files and directories are removed, replaced files are restored from their
    backups. The manifest is written last, after every installed file has been re-read and verified.
  * Bytes in, bytes out (F17): sources are copied in binary mode, so installed files are identical to the checkout
    on every platform; manifest and journal are UTF-8 with LF line endings; on Windows the read-only attribute is
    cleared, behind an lstat guard, immediately before a file is deleted or replaced (see scripts/fssafety.py).
  * Errors are reported as one ``ERROR[<label>] <message>`` line with a stable exit status; a traceback is shown
    only with --debug.

Exit codes:
    0  installed, or --dry-run plan printed        5  I/O failure during installation; changes rolled back
    2  command-line usage error                    6  recovery needed: an earlier run left an unfinished journal,
    3  unsafe target (label ``target``) or             or this run's rollback could not finish
       destination path state (``unsafe-path``)    7  existing files differ and --force was not given
    4  preflight failure: source, VERSION,        130  interrupted; changes rolled back where possible
       adapter parity or plan (``preflight``)

Known limitations (documented residual risk): the guard checks and the operations they protect are separate system
calls, so a same-user race between them is not excluded; on POSIX the write, read and delete paths are relative to
directory descriptors opened with O_NOFOLLOW, while directory creation and every Windows code path rely on lstat
checks made immediately before the operation. The target denylist is a fixed list of well-known locations, not a
proof that a directory is a project; empty directories inside a skill are not reproduced in the target.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import secrets
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import fssafety  # noqa: E402

ROOT = _HERE.parent

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNSAFE = 3
EXIT_PREFLIGHT = 4
EXIT_IO = 5
EXIT_RECOVERY = 6
EXIT_CONFLICT = 7
EXIT_INTERRUPTED = 130

SOC_DV = PurePosixPath(".soc-dv")
CONFIG_REL = SOC_DV / "config.json"
MANIFEST_REL = SOC_DV / "install-manifest.json"
JOURNAL_DIR_REL = SOC_DV / "journal"
BACKUP_DIR_REL = SOC_DV / "backups"
SKILLS_REL = PurePosixPath("skills")
CONFIG_TEMPLATE_REL = PurePosixPath("templates") / "project-config.example.json"
HARNESSES = {"claude": ("CLAUDE.md", ".claude"), "codex": ("AGENTS.md", ".agents")}
ADAPTERS = tuple(adapter for _, adapter in HARNESSES.values())
TERMINAL_EVENTS = ("complete", "rolled_back")

# F8: locations that are never installation targets, neither themselves nor anything below them. /var and /opt are
# deliberately absent (macOS keeps temporary directories under /var, realpath /private/var; /opt hosts projects), and
# so is %LOCALAPPDATA% (%TEMP% lives below it on every default Windows account): temporary directories must work.
POSIX_SYSTEM_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/sys", "/proc", "/dev", "/root")
WINDOWS_SYSTEM_VARIABLES = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "windir", "APPDATA")

_COMPONENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_INSTALL_ID = r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}"
_INSTALLED = rf"(?:CLAUDE\.md|AGENTS\.md|\.(?:claude|agents)/skills/{_COMPONENT}(?:/{_COMPONENT})+)"
COMPONENT_RE = re.compile(rf"^{_COMPONENT}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
PERMITTED_RE = re.compile(
    rf"^(?:{_INSTALLED}|\.soc-dv/config\.json|\.soc-dv/install-manifest\.json"
    rf"|\.soc-dv/journal/{_INSTALL_ID}\.jsonl"
    rf"|\.soc-dv/backups/{_INSTALL_ID}/(?:{_INSTALLED}|\.soc-dv/install-manifest\.json))$"
)


class TargetError(fssafety.UnsafePathError):
    label = "target"


class PreflightError(fssafety.SourceTreeError):
    label = "preflight"


class ConflictError(fssafety.FsSafetyError):
    exit_code = EXIT_CONFLICT
    label = "conflict"


class InstallError(fssafety.SwapError):
    label = "install-failed"


class RecoveryError(fssafety.LeftoverStateError):
    label = "recovery-needed"


class Interrupted(fssafety.FsSafetyError):
    exit_code = EXIT_INTERRUPTED
    label = "interrupted"


@dataclass
class Item:
    source: Path                 # absolute path inside the stack checkout
    source_rel: str              # POSIX-style path relative to the stack checkout
    rel: PurePosixPath           # destination relative to the target
    data: bytes
    sha256: str
    mode: int
    action: str = "create"       # create | replace | unchanged
    previous_sha256: str | None = None
    backup_rel: PurePosixPath | None = None


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_install_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4)


def _abs(base: Path, rel: PurePosixPath) -> Path:
    return base.joinpath(*rel.parts)


def _rel(base: Path, path: Path) -> str:
    return PurePosixPath(*path.relative_to(base).parts).as_posix()


def assert_permitted(rel: PurePosixPath) -> None:
    if not PERMITTED_RE.match(rel.as_posix()):
        raise PreflightError(f"{rel.as_posix()}: destination is outside the installer's permitted write set")


# --------------------------------------------------------------------------- target (F8)
def _real_home() -> Path | None:
    try:
        return Path(os.path.realpath(Path.home()))
    except (RuntimeError, KeyError):  # pragma: no cover - no resolvable home directory on this host
        return None


def system_prefixes() -> list[Path]:
    """Well-known system locations for this platform (plus the roaming user configuration root on Windows), resolved
    (e.g. /lib -> /usr/lib on merged-usr systems)."""
    if os.name == "nt":
        raw = [os.environ.get(name, "") for name in WINDOWS_SYSTEM_VARIABLES]
    else:
        raw = list(POSIX_SYSTEM_PREFIXES)
    return [Path(os.path.realpath(p)) for p in raw if p]


def resolve_target(raw: str, root: Path) -> Path:
    """Validate --target: an existing plain directory on a link-free path, outside every refused location.

    The given path is made absolute lexically (no link is followed) and every component below the filesystem anchor
    is inspected with lstat; a link-like component anywhere is refused with the real directory named in the
    message. The resolved path is then compared, in this order, with the filesystem anchor, the stack checkout
    (itself, inside it, ancestor of it), the home directory (itself, ancestor of it, hidden entry directly below it
    such as ~/.config or ~/.claude) and the system prefixes. Raises TargetError (exit 3, label ``target``).
    """
    given = Path(os.path.abspath(Path(raw).expanduser()))
    cur = Path(given.anchor)
    for part in given.parts[1:]:
        cur = cur / part
        where = "target" if cur == given else f"path component {cur}"
        st = fssafety.lstat_or_none(cur)
        if st is None:
            hint = "; create the project directory first" if cur == given else ""
            raise TargetError(f"{given}: {where} does not exist{hint}")
        if fssafety.is_link_like(st):
            raise TargetError(f"{given}: {where} is a {fssafety.describe_link(st)}; pass the real directory "
                              f"{os.path.realpath(given)} instead")
        if not stat.S_ISDIR(st.st_mode):
            raise TargetError(f"{given}: {where} is not a directory")
    target = Path(os.path.realpath(given))  # equals ``given`` up to the platform's canonical spelling
    st = fssafety.lstat_or_none(target)
    if st is None or fssafety.is_link_like(st) or not stat.S_ISDIR(st.st_mode):
        raise TargetError(f"{target}: resolved target is not a plain directory")
    if target == Path(target.anchor):
        raise TargetError(f"{target}: refusing to install into a filesystem root")
    real_root = Path(os.path.realpath(root))
    if target == real_root:
        raise TargetError(f"{target}: refusing to install into the stack checkout itself")
    if real_root in target.parents:
        raise TargetError(f"{target}: refusing to install inside the stack checkout {real_root}")
    if target in real_root.parents:
        raise TargetError(f"{target}: refusing to install into an ancestor of the stack checkout {real_root}")
    home = _real_home()
    if home is not None:
        if target == home:
            raise TargetError(f"{target}: refusing to install into the home directory")
        if target in home.parents:
            raise TargetError(f"{target}: refusing to install into an ancestor of the home directory {home}")
        if home in target.parents:
            first = target.parts[len(home.parts)]  # the entry directly below the home directory
            if first.startswith("."):
                raise TargetError(f"{target}: refusing to install into the user configuration directory "
                                  f"{home / first}")
    for prefix in system_prefixes():
        if target == prefix or prefix in target.parents:
            raise TargetError(f"{target}: refusing to install into the system directory {prefix}")
    return target


# --------------------------------------------------------------------------- sources (F14, F18)
def _read_source(root: Path, path: Path) -> bytes:
    if fssafety.lstat_or_none(path) is None:
        raise PreflightError(f"{_rel(root, path)}: source file is missing")
    fssafety.check_chain(root, path, leaf_kind="file")
    fssafety.assert_contained(root, path)
    return fssafety.read_regular_nofollow(root, path, allow_hard_links=True)


def _source_item(root: Path, source: Path, rel: PurePosixPath) -> Item:
    data = _read_source(root, source)
    return Item(source=source, source_rel=_rel(root, source), rel=rel, data=data, sha256=fssafety.sha256_bytes(data),
                mode=stat.S_IMODE(os.lstat(source).st_mode))


def read_version(root: Path) -> str:
    try:
        text = _read_source(root, root / "VERSION").decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise PreflightError(f"VERSION: not valid UTF-8 ({exc})") from exc
    if not VERSION_RE.match(text):
        raise PreflightError(f"VERSION: {text!r} is not a valid version string")
    return text


def scan_skills(root: Path) -> list[PurePosixPath]:
    """Guard the canonical skills/ tree and its adapters; return every skill file path relative to skills/.

    skills/ must exist, contain no link or special file and at least one file (fssafety.scan_tree); both adapter
    trees must be identical to it (fssafety.trees_equal, the same parity rule as scripts/sync_adapters.py --check);
    every top-level entry must be a skill directory carrying a SKILL.md; every path component must match
    COMPONENT_RE, which excludes '.', '..', hidden names, separators and whitespace.
    """
    source = _abs(root, SKILLS_REL)
    manifest, _ = fssafety.scan_tree(root, source)
    for adapter in ADAPTERS:
        adapter_dir = root / adapter / "skills"
        if not fssafety.check_chain(root, adapter_dir, allow_missing_leaf=True, leaf_kind="dir"):
            raise PreflightError(f"{adapter}/skills: adapter tree is missing; run scripts/sync_adapters.py first")
        fssafety.assert_contained(root, adapter_dir)
        if not fssafety.trees_equal(source, adapter_dir):
            raise PreflightError(f"{adapter}/skills: adapter tree differs from skills/ (drift); run "
                                 "scripts/sync_adapters.py --check, resynchronise, then install again")
    files: list[PurePosixPath] = []
    skills = 0
    for rel, kind in sorted(manifest.items()):
        for part in rel.parts:
            if not COMPONENT_RE.match(part):
                raise PreflightError(f"skills/{rel.as_posix()}: path component {part!r} is not permitted")
        if len(rel.parts) == 1:
            if kind != "d":
                raise PreflightError(f"skills/{rel.as_posix()}: a file at the top of skills/ belongs to no skill")
            if manifest.get(rel / "SKILL.md") != "f":
                raise PreflightError(f"skills/{rel.as_posix()}: skill directory has no SKILL.md")
            skills += 1
        elif kind == "f":
            files.append(rel)
    if skills == 0:
        raise PreflightError("skills/: no skill directory found; refusing to install an empty skill set")
    return files


def read_sources(root: Path, harness: str) -> tuple[str, list[Item]]:
    """Read and check every source before the first write. Any unsafe state inside the checkout is exit 4.

    Skill files are read once from skills/ and planned for every selected adapter; the config template is always
    read, whether it is installed is decided against the target in ``_run``.
    """
    try:
        version = read_version(root)
        skill_files = scan_skills(root)
        skill_items = [_source_item(root, _abs(root, SKILLS_REL / rel), rel) for rel in skill_files]
        items: list[Item] = []
        for name, (contract, adapter) in HARNESSES.items():
            if harness not in (name, "all"):
                continue
            items.append(_source_item(root, root / contract, PurePosixPath(contract)))
            items.extend(dataclasses.replace(item, rel=PurePosixPath(adapter) / "skills" / item.rel)
                         for item in skill_items)
        items.append(_source_item(root, _abs(root, CONFIG_TEMPLATE_REL), CONFIG_REL))
    except PreflightError:
        raise
    except (fssafety.UnsafePathError, fssafety.SourceTreeError) as exc:
        raise PreflightError(str(exc)) from exc
    for item in items:
        assert_permitted(item.rel)
    return version, items


# --------------------------------------------------------------------------- destinations and journals
def classify_destinations(target: Path, items: list[Item], *, force: bool) -> list[Item]:
    """Set each item's action from the destination state (never following links); conflicts need --force."""
    conflicts: list[Item] = []
    for item in items:
        dst = _abs(target, item.rel)
        if fssafety.classify_destination(target, dst) == "missing":
            item.action = "create"
            continue
        existing = fssafety.read_regular_nofollow(target, dst)
        item.previous_sha256 = fssafety.sha256_bytes(existing)
        if existing == item.data:
            item.action = "unchanged"
        else:
            item.action = "replace"
            conflicts.append(item)
    if conflicts and not force:
        listing = "\n".join(f"  {_abs(target, c.rel)}" for c in conflicts)
        raise ConflictError(f"Refusing to overwrite existing files:\n{listing}\nReview them or rerun with --force.")
    return conflicts


def _check_directory_slot(target: Path, rel: PurePosixPath) -> None:
    _, st = fssafety.chain_state(target, _abs(target, rel))
    if st is not None and not stat.S_ISDIR(st.st_mode):
        raise fssafety.UnsafePathError(f"{rel.as_posix()}: exists and is not a directory")


def _last_event(data: bytes) -> str:
    lines = [line for line in data.decode("utf-8", errors="replace").splitlines() if line.strip()]
    if not lines:
        return "none"
    try:
        return str(json.loads(lines[-1]).get("event", "unknown"))
    except (ValueError, AttributeError):
        return "unparseable"


def check_journals(target: Path) -> None:
    """Refuse to install while a previous run's journal is not terminal (complete or rolled back)."""
    journal_dir = _abs(target, JOURNAL_DIR_REL)
    _, st = fssafety.chain_state(target, journal_dir)
    if st is None:
        return
    if not stat.S_ISDIR(st.st_mode):
        raise fssafety.UnsafePathError(f"{JOURNAL_DIR_REL.as_posix()}: exists and is not a directory")
    for entry in sorted(journal_dir.iterdir()):
        est = os.lstat(entry)
        if fssafety.is_link_like(est) or not stat.S_ISREG(est.st_mode) or not entry.name.endswith(".jsonl"):
            raise fssafety.UnsafePathError(f"{_rel(target, entry)}: unexpected entry in the journal directory")
        last = _last_event(fssafety.read_regular_nofollow(target, entry, allow_hard_links=True))
        if last not in TERMINAL_EVENTS:
            raise RecoveryError(f"{_rel(target, entry)}: an earlier installation did not finish (last event: {last}); "
                                "inspect the journal, restore or remove the files it lists, then move the journal "
                                "away before installing again")


class Journal:
    """Append-only JSON-lines record of every mutation, fsync'ed per record, held open for the whole run."""

    def __init__(self, target: Path, rel: PurePosixPath):
        self.rel = rel
        path = _abs(target, rel)
        if fssafety.classify_destination(target, path) != "missing":
            raise fssafety.UnsafePathError(f"{rel.as_posix()}: journal file already exists")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_BINARY", 0)
        self.fd = os.open(path, flags, 0o644)
        self.events: list[dict] = []

    def record(self, event: str, **fields) -> dict:
        rec = {"t": _utc(), "event": event, **fields}
        view = memoryview((json.dumps(rec, sort_keys=True) + "\n").encode("utf-8"))
        while view:
            view = view[os.write(self.fd, view):]
        os.fsync(self.fd)
        self.events.append(rec)
        return rec

    def close(self) -> None:
        os.close(self.fd)


# --------------------------------------------------------------------------- installation
def _restore_or_remove(target: Path, rec: dict, restored: set) -> None:
    path = _abs(target, PurePosixPath(rec["path"]))
    backup = rec.get("backup")
    if backup:
        backup_path = _abs(target, PurePosixPath(backup))
        current = fssafety.read_regular_nofollow(target, backup_path)
        if fssafety.sha256_bytes(current) != rec["previous_sha256"]:
            raise InstallError(f"{backup}: backup content changed; not restored")
        fssafety.replace_regular_nofollow(target, backup_path, path)
        restored.add(backup)
    else:
        fssafety.unlink_regular_nofollow(target, path, expect_sha256=rec["sha256"])


def rollback(target: Path, performed: list[dict], journal: Journal) -> list[str]:
    """Undo the journaled mutations in reverse order; returns the failures (empty when fully rolled back)."""
    failures: list[str] = []
    restored: set = set()
    try:
        journal.record("rollback", steps=len(performed))
    except OSError as exc:  # pragma: no cover - journal no longer writable
        failures.append(f"journal: {exc}")
    for rec in reversed(performed):
        event = rec["event"]
        try:
            if event in ("replace", "manifest"):
                _restore_or_remove(target, rec, restored)
            elif event == "create":
                fssafety.unlink_regular_nofollow(target, _abs(target, PurePosixPath(rec["path"])),
                                                 expect_sha256=rec["sha256"])
            elif event == "backup":
                if rec["backup"] not in restored:  # the replacement never happened: the copy is surplus
                    fssafety.unlink_regular_nofollow(target, _abs(target, PurePosixPath(rec["backup"])),
                                                     expect_sha256=rec["sha256"])
            elif event == "mkdir":
                if not fssafety.rmdir_if_empty(target, _abs(target, PurePosixPath(rec["path"]))):
                    failures.append(f"{rec['path']}: directory left in place (not empty)")
        except (fssafety.FsSafetyError, OSError) as exc:
            failures.append(f"{rec.get('path') or rec.get('backup')}: {exc}")
    try:
        journal.record("rolled_back" if not failures else "rollback_incomplete", failures=failures)
    except OSError as exc:  # pragma: no cover - journal no longer writable
        failures.append(f"journal: {exc}")
    return failures


def build_manifest(target: Path, items: list[Item], version: str, harness: str, install_id: str,
                   previous_manifest: dict | None, journal_rel: PurePosixPath) -> dict:
    files = []
    for item in items:
        entry = {"path": item.rel.as_posix(), "sha256": item.sha256, "action": item.action, "source": item.source_rel}
        if item.action == "replace":
            entry["previous_sha256"] = item.previous_sha256
            entry["backup"] = item.backup_rel.as_posix() if item.backup_rel is not None else None
        files.append(entry)
    return {
        "schema_version": 2,
        "install_id": install_id,
        "installed_utc": _utc(),
        "stack_version": version,
        "harness": harness,
        "target": str(target),
        "files": files,
        "previous_manifest": previous_manifest,
        "journal": journal_rel.as_posix(),
    }


def execute(target: Path, items: list[Item], version: str, harness: str, install_id: str) -> dict:
    """Perform the journaled installation; any failure is rolled back before the error is raised."""
    journal_rel = JOURNAL_DIR_REL / f"{install_id}.jsonl"
    assert_permitted(journal_rel)
    backup_root = BACKUP_DIR_REL / install_id
    created_dirs = fssafety.mkdir_chain(target, _abs(target, JOURNAL_DIR_REL))
    try:
        journal = Journal(target, journal_rel)
    except (fssafety.FsSafetyError, OSError):
        for directory in reversed(created_dirs):
            fssafety.rmdir_if_empty(target, directory)
        raise
    performed: list[dict] = []

    def mkdirs(directory: Path) -> None:
        for created in fssafety.mkdir_chain(target, directory):
            performed.append(journal.record("mkdir", path=_rel(target, created)))

    def back_up(rel: PurePosixPath, content: bytes) -> PurePosixPath:
        backup_rel = backup_root / rel
        assert_permitted(backup_rel)
        backup_path = _abs(target, backup_rel)
        mkdirs(backup_path.parent)
        fssafety.write_regular_atomically(target, backup_path, content, mode=0o600, expect_existing=False)
        performed.append(journal.record("backup", path=rel.as_posix(), backup=backup_rel.as_posix(),
                                        sha256=fssafety.sha256_bytes(content)))
        return backup_rel

    try:
        try:
            journal.record("begin", install_id=install_id, target=str(target), stack_version=version,
                           harness=harness, created_dirs=[_rel(target, d) for d in created_dirs],
                           plan=[{"path": item.rel.as_posix(), "action": item.action} for item in items])
            for item in items:
                dst = _abs(target, item.rel)
                if item.action == "unchanged":
                    journal.record("skip", path=item.rel.as_posix(), sha256=item.sha256)
                    continue
                mkdirs(dst.parent)
                if item.action == "replace":
                    current = fssafety.read_regular_nofollow(target, dst)
                    if fssafety.sha256_bytes(current) != item.previous_sha256:
                        raise InstallError(f"{item.rel.as_posix()}: file changed since preflight; not replaced")
                    item.backup_rel = back_up(item.rel, current)
                    fssafety.write_regular_atomically(target, dst, item.data, mode=item.mode, expect_existing=True)
                    performed.append(journal.record("replace", path=item.rel.as_posix(), sha256=item.sha256,
                                                    previous_sha256=item.previous_sha256,
                                                    backup=item.backup_rel.as_posix()))
                else:
                    fssafety.write_regular_atomically(target, dst, item.data, mode=item.mode, expect_existing=False)
                    performed.append(journal.record("create", path=item.rel.as_posix(), sha256=item.sha256))
            # verify every installed file by re-reading it without following links
            written = [item for item in items if item.action != "unchanged"]
            for item in written:
                got = fssafety.read_regular_nofollow(target, _abs(target, item.rel))
                if fssafety.sha256_bytes(got) != item.sha256:
                    raise InstallError(f"{item.rel.as_posix()}: verification after writing failed")
            journal.record("verify", files=len(written))
            # the manifest is written last; a previous manifest is backed up and referenced
            manifest_path = _abs(target, MANIFEST_REL)
            previous_manifest = None
            if fssafety.classify_destination(target, manifest_path) == "file":
                old = fssafety.read_regular_nofollow(target, manifest_path)
                backup_rel = back_up(MANIFEST_REL, old)
                previous_manifest = {"sha256": fssafety.sha256_bytes(old), "backup": backup_rel.as_posix()}
            manifest = build_manifest(target, items, version, harness, install_id, previous_manifest, journal_rel)
            data = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            mkdirs(manifest_path.parent)
            fssafety.write_regular_atomically(target, manifest_path, data, mode=0o644)
            previous = previous_manifest or {}
            performed.append(journal.record("manifest", path=MANIFEST_REL.as_posix(),
                                            sha256=fssafety.sha256_bytes(data),
                                            previous_sha256=previous.get("sha256"), backup=previous.get("backup")))
            journal.record("complete", install_id=install_id)
            return manifest
        except BaseException as exc:
            failures = rollback(target, performed, journal)
            reason = str(exc) or type(exc).__name__
            where = f"journal {journal_rel.as_posix()}"
            if failures:
                raise RecoveryError(f"{reason}; rollback incomplete: " + "; ".join(failures) + f" ({where})") from exc
            if isinstance(exc, KeyboardInterrupt):
                raise Interrupted(f"interrupted; the installation was rolled back ({where})") from exc
            raise InstallError(f"{reason}; the installation was rolled back and the target restored ({where})") from exc
    finally:
        journal.close()


# --------------------------------------------------------------------------- command line
def _run(root: Path, args: argparse.Namespace) -> int:
    target = resolve_target(args.target, root)
    version, items = read_sources(root, args.harness)
    check_journals(target)
    for rel in (SOC_DV, JOURNAL_DIR_REL, BACKUP_DIR_REL):
        _check_directory_slot(target, rel)
    fssafety.classify_destination(target, _abs(target, MANIFEST_REL))
    # the config template is installed only when the project has no config yet (an existing one is never touched)
    if fssafety.classify_destination(target, _abs(target, CONFIG_REL), allow_hard_links=True) == "file":
        items = [item for item in items if item.rel != CONFIG_REL]
    classify_destinations(target, items, force=args.force)
    print(f"target: {target}")
    for item in items:
        print(f"{item.source_rel} -> {item.rel.as_posix()} [{item.action}]")
    written = sum(1 for item in items if item.action != "unchanged")
    unchanged = len(items) - written
    if args.dry_run:
        print(f"dry-run: {written} file(s) would be written, {unchanged} unchanged; nothing was modified.")
        return EXIT_OK
    install_id = new_install_id()
    execute(target, items, version, args.harness, install_id)
    print(f"Installed project-local stack: {written} file(s) written, {unchanged} unchanged "
          f"(install {install_id}). Review {MANIFEST_REL.as_posix()}.")
    return EXIT_OK


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project-local installer for the SoC DV agent stack")
    parser.add_argument("--target", required=True, help="existing project directory to install into")
    parser.add_argument("--harness", choices=["claude", "codex", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="run every check and print the plan; write nothing")
    parser.add_argument("--force", action="store_true",
                        help="replace existing files that differ (a backup is kept under .soc-dv/backups/)")
    parser.add_argument("--debug", action="store_true", help="show Python tracebacks instead of one-line errors")
    args = parser.parse_args(argv)
    root = Path(root).resolve() if root is not None else ROOT
    try:
        return _run(root, args)
    except fssafety.FsSafetyError as exc:
        if args.debug:
            raise
        print(f"ERROR[{exc.label}] {exc}", file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        if args.debug:
            raise
        print(f"ERROR[io] {exc}", file=sys.stderr)
        return EXIT_IO
    except KeyboardInterrupt:
        print("ERROR[interrupted] interrupted before any change was made", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    raise SystemExit(main())
