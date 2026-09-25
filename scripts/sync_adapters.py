#!/usr/bin/env python3
"""Materialise the canonical ``skills/`` tree into the Claude and Codex adapter directories, link-safely.

Usage:
    python scripts/sync_adapters.py            synchronise .claude/skills and .agents/skills from skills/
    python scripts/sync_adapters.py --check    report drift without modifying anything
    python scripts/sync_adapters.py --dry-run  run every guard and print the plan; modify nothing

All guards run for every target before anything is modified; a single unsafe target aborts the whole run.
Targets already in parity are left untouched. Drifted targets are rebuilt in a sibling staging directory and
swapped into place with atomic renames (see scripts/fssafety.py for the guard and swap contract).

Exit codes (stable):
    0  success / parity confirmed
    1  --check found adapter drift
    2  command-line usage error
    3  unsafe path state (link, junction or reparse point in the root->target chain or inside skills/,
       target not a directory, or resolved path outside the repository); nothing was modified
    4  skills/ missing or empty (fail closed); nothing was modified
    5  I/O failure while staging or swapping; the previous target was left in place or restored
    6  leftover staging directories from an interrupted earlier run; nothing was modified
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import fssafety  # noqa: E402

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_IO = 5

ADAPTER_TARGETS = (Path(".claude") / "skills", Path(".agents") / "skills")


def repo_root() -> Path:
    return _HERE.parent


def adapter_targets(root: Path) -> list[Path]:
    return [root / rel for rel in ADAPTER_TARGETS]


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def _preflight(root: Path, source: Path, targets: list[Path]) -> int:
    """Every guard for every target, before any mutation. Returns the number of files in the source tree."""
    _, n_files = fssafety.scan_tree(root, source)
    for target in targets:
        parent_exists = fssafety.check_chain(root, target.parent, allow_missing_leaf=True, leaf_kind="dir")
        if not parent_exists:
            fssafety.assert_contained(root, target.parent)
            continue
        exists = fssafety.check_chain(root, target, allow_missing_leaf=True, leaf_kind="dir")
        fssafety.assert_contained(root, target if exists else target.parent)
        leftovers = fssafety.find_leftovers(target)
        if leftovers:
            names = ", ".join(_rel(root, p) for p in leftovers)
            raise fssafety.LeftoverStateError(
                f"{_rel(root, target.parent)}: leftover staging state from an interrupted run: {names}; "
                "inspect and remove it by hand, nothing was modified")
    return n_files


def check(root: Path, source: Path, targets: list[Path]) -> int:
    _preflight(root, source, targets)
    drifted = [_rel(root, t) for t in targets if not fssafety.trees_equal(source, t)]
    if drifted:
        print("Adapter drift: " + ", ".join(drifted), file=sys.stderr)
        return EXIT_DRIFT
    print("Adapter parity: OK")
    return EXIT_OK


def sync(root: Path, source: Path, targets: list[Path], *, dry_run: bool) -> int:
    _preflight(root, source, targets)
    for target in targets:
        if fssafety.trees_equal(source, target):
            print(f"{'dry-run: ' if dry_run else ''}{_rel(root, target)}: in sync, unchanged")
            continue
        print(fssafety.replace_tree_atomically(root, source, target, dry_run=dry_run))
    n_skills = len(list(source.glob("*/SKILL.md")))
    if dry_run:
        print(f"dry-run: {n_skills} skills; nothing was modified.")
    else:
        print(f"Synchronized {n_skills} skills to Claude and Codex adapters.")
    return EXIT_OK


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronise skills/ into the Claude and Codex adapter directories")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report drift only; exit 1 on drift, modify nothing")
    mode.add_argument("--dry-run", action="store_true", help="run all guards and print the plan; modify nothing")
    args = parser.parse_args(argv)
    root = Path(root).resolve() if root is not None else repo_root()
    source = root / "skills"
    targets = adapter_targets(root)
    try:
        if args.check:
            return check(root, source, targets)
        return sync(root, source, targets, dry_run=args.dry_run)
    except fssafety.FsSafetyError as exc:
        print(f"ERROR[{exc.label}] {exc}", file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(f"ERROR[io] {exc}", file=sys.stderr)
        return EXIT_IO


if __name__ == "__main__":
    raise SystemExit(main())
