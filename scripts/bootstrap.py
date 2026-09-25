#!/usr/bin/env python3
"""Project-local installer for the SoC DV agent stack (link-safe rewrite; remediation of audit finding F2).

Usage:
    python scripts/bootstrap.py --target ../my-dv-project [--harness claude|codex|all] [--dry-run] [--force]

What it installs into the target project: CLAUDE.md and .claude/skills/<skill>/SKILL.md (harness ``claude``),
AGENTS.md and .agents/skills/<skill>/SKILL.md (harness ``codex``), .soc-dv/config.json from the template when the
project has no config yet, and .soc-dv/install-manifest.json describing the installation.

Safety model (docs/audits/2026-09-24/static-security-audit.md, finding F2 with its F9/F14 overlaps):
  * The target must be an existing plain directory named by a non-link path; the home directory and the
    filesystem root are refused. Every destination is checked with lstat from the target downwards: no symbolic
    link, junction or other reparse point anywhere in the chain (a dangling link counts as a link), no directory or
    special file where a file is expected, and no regular file with more than one hard link. Any such state fails
    closed before the first write, with or without --force.
  * Every source (CLAUDE.md, AGENTS.md, the adapter SKILL.md files, the config template) and VERSION are read and
    checked before the first write; existing destinations are compared without following links. Identical files
    are left untouched; differing files are replaced only with --force, after a backup copy under
    .soc-dv/backups/<install_id>/ whose hash is recorded.
  * Files are written to a sibling temporary file and moved into place with os.replace. Every mutation is journaled
    (.soc-dv/journal/<install_id>.jsonl, append-only, fsync'ed). A failure rolls the run back from that journal:
    created files and directories are removed, replaced files are restored from their backups. The manifest is
    written last, after every installed file has been re-read and verified; a previous manifest is backed up and
    referenced from the new one.
  * Errors are reported as one ``ERROR[<label>] <message>`` line with a stable exit status; a traceback is shown
    only with --debug.

Exit codes:
    0  installed, or --dry-run plan printed        5  I/O failure during installation; changes rolled back
    2  command-line usage error                    6  recovery needed: an earlier run left an unfinished journal,
    3  unsafe target or destination path state        or this run's rollback could not finish
    4  preflight failure (source, VERSION, plan)   7  existing files differ and --force was not given
  130  interrupted; changes rolled back where possible

Known limitations (documented residual risk): the guard checks and the operations they protect are separate system
calls, so a same-user race between them is not excluded; on POSIX the write, read and delete paths are relative to
directory descriptors opened with O_NOFOLLOW, while directory creation and every Windows code path rely on lstat
checks made immediately before the operation. The target denylist itself (audit finding F8) is unchanged here.
"""
from __future__ import annotations

import argparse
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
HARNESSES = {"claude": ("CLAUDE.md", ".claude"), "codex": ("AGENTS.md", ".agents")}
TERMINAL_EVENTS = ("complete", "rolled_back")

_SKILL_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_INSTALL_ID = r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}"
_INSTALLED = rf"(?:CLAUDE\.md|AGENTS\.md|\.(?:claude|agents)/skills/{_SKILL_NAME}/SKILL\.md)"
SKILL_NAME_RE = re.compile(rf"^{_SKILL_NAME}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
PERMITTED_RE = re.compile(
    rf"^(?:{_INSTALLED}|\.soc-dv/config\.json|\.soc-dv/install-manifest\.json"
    rf"|\.soc-dv/journal/{_INSTALL_ID}\.jsonl"
    rf"|\.soc-dv/backups/{_INSTALL_ID}/(?:{_INSTALLED}|\.soc-dv/install-manifest\.json))$"
)


class TargetError(fssafety.UnsafePathError):
    label = "unsafe-target"


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
        raise TargetError(f"{rel.as_posix()}: destination is outside the installer's permitted write set")


# --------------------------------------------------------------------------- target and sources
def resolve_target(raw: str) -> Path:
    given = Path(raw).expanduser()
    st = fssafety.lstat_or_none(given)
    if st is None:
        raise TargetError(f"{given}: target does not exist; create the project directory first")
    if fssafety.is_link_like(st):
        raise TargetError(f"{given}: target path is a {fssafety.describe_link(st)}; pass the real directory "
                          f"{os.path.realpath(given)} instead")
    if not stat.S_ISDIR(st.st_mode):
        raise TargetError(f"{given}: target is not a directory")
    target = Path(os.path.realpath(given))
    st_real = fssafety.lstat_or_none(target)
    if st_real is None or fssafety.is_link_like(st_real) or not stat.S_ISDIR(st_real.st_mode):
        raise TargetError(f"{target}: resolved target is not a plain directory")
    refused = {Path(os.path.realpath(Path(target.anchor)))}
    try:
        refused.add(Path(os.path.realpath(Path.home())))
    except (RuntimeError, KeyError):  # pragma: no cover - no resolvable home directory on this host
        pass
    if target in refused:
        raise TargetError("Refusing home/root target")
    return target


def _read_source(root: Path, path: Path) -> bytes:
    if fssafety.lstat_or_none(path) is None:
        raise PreflightError(f"{_rel(root, path)}: source file is missing")
    fssafety.check_chain(root, path, leaf_kind="file")
    fssafety.assert_contained(root, path)
    return fssafety.read_regular_nofollow(root, path, allow_hard_links=True)


def read_version(root: Path) -> str:
    try:
        text = _read_source(root, root / "VERSION").decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise PreflightError(f"VERSION: not valid UTF-8 ({exc})") from exc
    if not VERSION_RE.match(text):
        raise PreflightError(f"VERSION: {text!r} is not a valid version string")
    return text


def build_plan(root: Path, target: Path, harness: str) -> list[Item]:
    items: list[Item] = []

    def add(source: Path, rel: PurePosixPath) -> None:
        data = _read_source(root, source)
        items.append(Item(source=source, source_rel=_rel(root, source), rel=rel, data=data,
                          sha256=fssafety.sha256_bytes(data), mode=stat.S_IMODE(os.lstat(source).st_mode)))

    for name, (contract, adapter) in HARNESSES.items():
        if harness not in (name, "all"):
            continue
        add(root / contract, PurePosixPath(contract))
        skills_dir = root / adapter / "skills"
        if fssafety.lstat_or_none(skills_dir) is None:
            raise PreflightError(f"{adapter}/skills: adapter skills directory is missing")
        fssafety.check_chain(root, skills_dir, leaf_kind="dir")
        count = 0
        for entry in sorted(skills_dir.iterdir()):
            st = os.lstat(entry)
            if fssafety.is_link_like(st):
                raise fssafety.UnsafePathError(f"{entry}: is a {fssafety.describe_link(st)}; refusing")
            if not stat.S_ISDIR(st.st_mode):
                continue
            if not SKILL_NAME_RE.match(entry.name):
                raise PreflightError(f"{entry}: skill directory name is not permitted")
            skill_file = entry / "SKILL.md"
            if fssafety.lstat_or_none(skill_file) is None:
                continue  # a directory without SKILL.md is not a skill (same selection as the former glob)
            add(skill_file, PurePosixPath(adapter) / "skills" / entry.name / "SKILL.md")
            count += 1
        if count == 0:
            raise PreflightError(f"{adapter}/skills: no SKILL.md found; refusing to install an empty skill set")
    # the config template is installed only when the project has no config yet (an existing one is never touched)
    if fssafety.classify_destination(target, _abs(target, CONFIG_REL), allow_hard_links=True) == "missing":
        add(root / "templates" / "project-config.example.json", CONFIG_REL)
    for item in items:
        assert_permitted(item.rel)
    return items


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
        raise TargetError(f"{rel.as_posix()}: exists and is not a directory")


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
        raise TargetError(f"{JOURNAL_DIR_REL.as_posix()}: exists and is not a directory")
    for entry in sorted(journal_dir.iterdir()):
        est = os.lstat(entry)
        if fssafety.is_link_like(est) or not stat.S_ISREG(est.st_mode) or not entry.name.endswith(".jsonl"):
            raise TargetError(f"{_rel(target, entry)}: unexpected entry in the journal directory")
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
            raise TargetError(f"{rel.as_posix()}: journal file already exists")
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
    target = resolve_target(args.target)
    version = read_version(root)
    items = build_plan(root, target, args.harness)
    check_journals(target)
    _check_directory_slot(target, SOC_DV)
    _check_directory_slot(target, JOURNAL_DIR_REL)
    _check_directory_slot(target, BACKUP_DIR_REL)
    fssafety.classify_destination(target, _abs(target, MANIFEST_REL))
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
