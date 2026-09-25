#!/usr/bin/env python3
"""Cupel card parity and card-shape checker (standard library only).

Checks that every canonical card under orgs/cupel/agents/ is well-formed and is
mirrored byte-for-byte into each mirror directory listed in orgs/cupel/cupel.json
(Phase 1: .claude/agents/cupel/). With --sync it regenerates the mirrors from the
canonical cards. It never deletes anything, never follows or creates symbolic
links, and writes only inside the listed mirror directories.

Exit status: 0 on success, 1 on any error.
"""
import argparse
import filecmp
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "orgs" / "cupel"
MANIFEST = CORE / "cupel.json"
CANON = CORE / "agents"
SCHEMAS = CORE / "schemas"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def parse_frontmatter(text, allowed_keys):
    """Strict parse of a card: '---', 'key: value' lines only, '---', body.

    Returns (fields, body, errors). Only the keys in allowed_keys are accepted,
    each at most once, in a flat 'key: value' form with a non-empty value.
    """
    errors = []
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, "", ["missing or malformed YAML frontmatter"]
    fields = {}
    for raw in m.group(1).split("\n"):
        if not raw.strip():
            errors.append("blank line inside frontmatter")
            continue
        if ":" not in raw or raw[0] in " \t":
            errors.append(f"frontmatter line is not 'key: value': {raw!r}")
            continue
        key, value = raw.split(":", 1)
        key, value = key.strip(), value.strip()
        if key not in allowed_keys:
            errors.append(f"frontmatter key not allowed: {key!r}")
        if key in fields:
            errors.append(f"duplicate frontmatter key: {key!r}")
        if not value:
            errors.append(f"empty frontmatter value for {key!r}")
        fields[key] = value
    for key in allowed_keys:
        if key not in fields:
            errors.append(f"frontmatter key missing: {key!r}")
    return fields, m.group(2), errors


def check_card(path, manifest):
    errors = []
    text = path.read_text(encoding="utf-8")
    if "\r" in text:
        errors.append("carriage return found; cards use LF line endings")
    limits = manifest["card_limits"]
    fields, body, ferr = parse_frontmatter(text, limits["frontmatter_keys"])
    errors += ferr
    if ferr:
        return errors
    face = path.stem
    faces = {f["face"]: f for f in manifest["faces"]}
    if face not in faces:
        errors.append(f"face {face!r} is not listed in cupel.json")
        return errors
    expected_name = f"cupel-{face}"
    if fields["name"] != expected_name:
        errors.append(f"name {fields['name']!r} != {expected_name!r}")
    expected_tools = manifest["face_classes"][faces[face]["class"]]
    if fields["tools"] != expected_tools:
        errors.append(f"tools {fields['tools']!r} != {expected_tools!r} for class {faces[face]['class']}")
    if len(fields["description"]) > limits["description_max_chars"]:
        errors.append(f"description is {len(fields['description'])} chars (> {limits['description_max_chars']})")
    if not (limits["body_min_chars"] <= len(body) <= limits["body_max_chars"]):
        errors.append(f"body is {len(body)} chars (allowed {limits['body_min_chars']}..{limits['body_max_chars']})")
    return errors


def no_symlinks(base):
    """Return error strings for any symbolic link at or under base."""
    errors = []
    if base.is_symlink():
        errors.append(f"{base} is a symbolic link")
        return errors
    if base.exists():
        for p in base.rglob("*"):
            if p.is_symlink():
                errors.append(f"{p} is a symbolic link")
    return errors


def canonical_cards():
    return sorted(p for p in CANON.glob("*.md") if p.is_file() and not p.is_symlink())


def check_all(manifest):
    errors = []
    errors += no_symlinks(CANON)
    cards = canonical_cards()
    if not cards:
        errors.append(f"no canonical cards found under {CANON}")
    expected = {f["face"] for f in manifest["faces"]}
    found = {p.stem for p in cards}
    for missing in sorted(expected - found):
        errors.append(f"card listed in cupel.json but missing on disk: {missing}.md")
    for extra in sorted(found - expected):
        errors.append(f"card on disk but not listed in cupel.json: {extra}.md")
    for p in cards:
        for e in check_card(p, manifest):
            errors.append(f"{p.relative_to(ROOT)}: {e}")
    copies = 0
    for mirror in manifest["card_paths"]["mirrors"]:
        mdir = ROOT / mirror
        errors += no_symlinks(mdir)
        if not mdir.is_dir():
            errors.append(f"mirror directory missing: {mirror}")
            continue
        mirror_files = {p.name for p in mdir.iterdir() if p.is_file()}
        for p in cards:
            q = mdir / p.name
            if not q.is_file():
                errors.append(f"mirror copy missing: {mirror}/{p.name}")
            elif not filecmp.cmp(p, q, shallow=False):
                errors.append(f"mirror copy differs from canonical: {mirror}/{p.name}")
            else:
                copies += 1
        for stray in sorted(mirror_files - {p.name for p in cards}):
            errors.append(f"stray file in mirror (not deleted; remove by hand): {mirror}/{stray}")
    schemas = sorted(p for p in SCHEMAS.glob("*.schema.json") if p.is_file())
    if not schemas:
        errors.append(f"no schemas found under {SCHEMAS}")
    for s in schemas:
        try:
            doc = json.loads(s.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{s.relative_to(ROOT)}: invalid JSON: {e}")
            continue
        for key in ("$schema", "$id", "title", "type"):
            if key not in doc:
                errors.append(f"{s.relative_to(ROOT)}: missing {key}")
    return errors, len(cards), copies, len(schemas)


def sync(manifest):
    """Regenerate mirrors from canonical cards. Never deletes; refuses symlinks."""
    errors = no_symlinks(CANON)
    cards = canonical_cards()
    written = 0
    for mirror in manifest["card_paths"]["mirrors"]:
        mdir = ROOT / mirror
        errors += no_symlinks(mdir)
        if errors:
            break
        mdir.mkdir(parents=True, exist_ok=True)
        for p in cards:
            q = mdir / p.name
            if q.is_symlink():
                errors.append(f"refusing to write through symbolic link: {mirror}/{p.name}")
                continue
            q.write_bytes(p.read_bytes())
            written += 1
        for stray in sorted(x.name for x in mdir.iterdir() if x.is_file()) :
            if stray not in {p.name for p in cards}:
                print(f"WARNING: stray file left in place: {mirror}/{stray}", file=sys.stderr)
    return errors, written


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check (or --sync) Cupel card mirrors")
    ap.add_argument("--sync", action="store_true", help="regenerate mirror copies from canonical cards")
    args = ap.parse_args(argv)
    if not MANIFEST.is_file():
        print(f"ERROR: manifest missing: {MANIFEST}", file=sys.stderr)
        return 1
    manifest = load_manifest()
    if args.sync:
        errors, written = sync(manifest)
        if errors:
            print("\n".join("ERROR: " + e for e in errors), file=sys.stderr)
            return 1
        print(f"Synchronized {written} card copies.")
    errors, cards, copies, schemas = check_all(manifest)
    if errors:
        print("\n".join("ERROR: " + e for e in errors), file=sys.stderr)
        return 1
    print(f"OK: {cards} cards, {copies} copies, {schemas} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
