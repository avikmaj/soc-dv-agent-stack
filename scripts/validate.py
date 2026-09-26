#!/usr/bin/env python3
"""Fail-closed repository validator for the SoC DV Agent skill/schema/template tree.

Checks, in order: the skills/, schemas/ and templates/ trees exist and are non-empty; the root
``skills.lock`` inventory matches the direct entries under skills/ (catching a partial canonical
deletion even when the adapter trees still agree with each other); every canonical skill has a
strictly-formatted frontmatter block and the eight mandatory H2 sections with real body content;
every schema/template JSON file decodes and parses; no symbolic link, Windows junction or other
reparse point is read through in skills/, schemas/, templates/, .claude/skills/ or .agents/skills/;
and scripts/sync_adapters.py --check still reports adapter parity. Every expected failure produces a
deterministic ``ERROR: <repo-relative path>: <message>`` line on stderr, never a traceback.
"""
from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import fssafety  # noqa: E402

ROOT = _HERE.parent

REQUIRED_HEADINGS = [
    "Purpose",
    "Inputs",
    "Workflow",
    "Checks",
    "Deliverables",
    "Evidence Gate",
    "Stop Conditions",
    "Safety",
]
MIN_SECTION_CHARS = 80

REQUIRED_SCHEMAS = [
    "regression-result.schema.json",
    "traceability.schema.json",
    "verification-plan.schema.json",
    "waiver.schema.json",
]
REQUIRED_TEMPLATES = [
    "project-config.example.json",
    "verification-plan.example.json",
]

ADAPTER_DIRS = ["/".join((".claude", "skills")), "/".join((".agents", "skills"))]

# Legacy pre-WS3 unsafe-pattern regex scan (scripts/* + skills/*/SKILL.md, validate.py itself exempt).
# F7 will replace this with an AST-based validator and a reviewed allowlist; until then it stays as-is.
LEGACY_UNSAFE_PATTERNS = [
    r"curl\s",
    r"wget\s",
    r"rm\s+-rf",
    r"--dangerously-skip-permissions",
    r"child_process",
    r"shell\s*=\s*True",
]

FRONTMATTER_KEYS = ("name", "description", "version")
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
H2_RE = re.compile(r"^## (.+?)\s*$")
HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
CONTROL_RE = re.compile(r"[\x00-\x08\x0B-\x1F\x7F\x80-\x9F]")
FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z0-9_]+):(.*)$")


def _relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _lstat_or_none(path: Path):
    """Local stand-in: c128ef37 does not provide fssafety.lstat_or_none."""
    try:
        return path.lstat()
    except OSError:
        return None


def _decode_utf8(raw: bytes, rel: str) -> tuple[str | None, list[str]]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return None, [f"{rel}: UTF-8 byte-order mark (BOM) is not allowed"]
    try:
        return raw.decode("utf-8", errors="strict"), []
    except UnicodeDecodeError as exc:
        return None, [f"{rel}: invalid UTF-8 ({exc})"]


def _read_text_utf8(path: Path, rel: str) -> tuple[str | None, list[str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [f"{rel}: cannot read ({exc.strerror or exc})"]
    return _decode_utf8(raw, rel)


def _normalize_newlines(text: str, rel: str) -> tuple[str | None, list[str]]:
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        return None, [f"{rel}: lone CR line ending is not allowed"]
    return normalized, []


# --------------------------------------------------------------------------- top-level directories
def check_top_level_dir(root: Path, rel: str) -> tuple[list[Path] | None, list[str]]:
    """Guard and list the direct entries of a required top-level directory (skills/, schemas/, templates/)."""
    path = root / rel
    st = _lstat_or_none(path)
    if st is None:
        return None, [f"{rel}: missing"]
    if fssafety.is_link_like(st):
        return None, [f"{rel}: refusing to read - is a {fssafety.describe_link(st)}"]
    if not stat.S_ISDIR(st.st_mode):
        return None, [f"{rel}: exists but is not a directory"]
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        return None, [f"{rel}: cannot list directory ({exc.strerror or exc})"]
    if not entries:
        return [], [f"{rel}: is empty"]
    return entries, []


def check_no_links_in_dir(root: Path, rel: str) -> list[str]:
    """Refuse any link-like direct entry of an adapter directory without reading its target."""
    path = root / rel
    st = _lstat_or_none(path)
    if st is None:
        return []
    if fssafety.is_link_like(st):
        return [f"{rel}: refusing to read - is a {fssafety.describe_link(st)}"]
    if not stat.S_ISDIR(st.st_mode):
        return []
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        return [f"{rel}: cannot list directory ({exc.strerror or exc})"]
    errors = []
    for entry in entries:
        est = _lstat_or_none(entry)
        if est is not None and fssafety.is_link_like(est):
            errors.append(f"{_relpath(root, entry)}: refusing to read - is a {fssafety.describe_link(est)}")
    return errors


# --------------------------------------------------------------------------- skills.lock
def load_skills_lock(root: Path) -> tuple[list[str] | None, list[str]]:
    rel = "skills.lock"
    path = root / rel
    st = _lstat_or_none(path)
    if st is None:
        return None, [f"{rel}: missing"]
    if fssafety.is_link_like(st):
        return None, [f"{rel}: refusing to read - is a {fssafety.describe_link(st)}"]
    if not stat.S_ISREG(st.st_mode):
        return None, [f"{rel}: exists but is not a regular file"]
    text, errors = _read_text_utf8(path, rel)
    if text is None:
        return None, errors
    if "\r" in text:
        return None, [f"{rel}: must use LF line endings, found CR"]
    if text == "":
        return None, [f"{rel}: is empty"]
    if not text.endswith("\n"):
        return None, [f"{rel}: must be LF-terminated (missing trailing newline)"]
    lines = text.split("\n")[:-1]
    names: list[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines, start=1):
        if line == "":
            errors.append(f"{rel}: line {lineno}: blank line not allowed")
            continue
        if not NAME_RE.match(line):
            errors.append(f"{rel}: line {lineno}: invalid skill name '{line}'")
            continue
        if line in seen:
            errors.append(f"{rel}: line {lineno}: duplicate name '{line}'")
            continue
        seen.add(line)
        names.append(line)
    if names != sorted(names):
        errors.append(f"{rel}: names must be sorted in lexical order")
    if errors:
        return None, errors
    return names, errors


def check_skills_inventory(root: Path, entries: list[Path], lock_names: list[str]) -> tuple[list[Path], list[str]]:
    """Reconcile skills.lock against the direct entries under skills/."""
    errors: list[str] = []
    lock_set = set(lock_names)
    present: set[str] = set()
    valid_dirs: list[Path] = []
    for entry in entries:
        rel = _relpath(root, entry)
        st = _lstat_or_none(entry)
        if st is None:
            continue
        if fssafety.is_link_like(st):
            errors.append(f"{rel}: refusing to read - is a {fssafety.describe_link(st)}")
            present.add(entry.name)
            continue
        if stat.S_ISREG(st.st_mode):
            errors.append(f"{rel}: stray regular file directly under skills/")
            continue
        if not stat.S_ISDIR(st.st_mode):
            errors.append(f"{rel}: unsupported filesystem entry type")
            continue
        present.add(entry.name)
        if entry.name not in lock_set:
            errors.append(f"{rel}: skill directory not listed in skills.lock")
            continue
        valid_dirs.append(entry)
    for name in sorted(lock_set - present):
        errors.append(f"skills/{name}: missing skill directory listed in skills.lock")
    return sorted(valid_dirs, key=lambda p: p.name), errors


# --------------------------------------------------------------------------- frontmatter + headings
def parse_frontmatter(text: str, rel: str) -> tuple[dict[str, str] | None, str, list[str]]:
    errors: list[str] = []
    if not text.startswith("---\n"):
        return None, text, [f"{rel}: frontmatter must start at byte 0 with '---'"]
    lines = text.split("\n")
    end_index = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end_index = i
            break
    if end_index is None:
        return None, text, [f"{rel}: frontmatter closing '---' not found"]
    body = "\n".join(lines[end_index + 1:])
    fields: dict[str, str] = {}
    seen: set[str] = set()
    for offset, line in enumerate(lines[1:end_index]):
        lineno = offset + 2
        if line.strip() == "":
            errors.append(f"{rel}: line {lineno}: blank line not allowed in frontmatter")
            continue
        m = FRONTMATTER_LINE_RE.match(line)
        if not m:
            errors.append(f"{rel}: line {lineno}: malformed frontmatter line (expected 'key: value')")
            continue
        key, rest = m.group(1), m.group(2)
        if not rest.startswith(" ") or rest.startswith("  "):
            errors.append(f"{rel}: line {lineno}: expected exactly one space after ':'")
            continue
        value = rest[1:]
        if key not in FRONTMATTER_KEYS:
            errors.append(f"{rel}: line {lineno}: unknown frontmatter key '{key}'")
            continue
        if key in seen:
            errors.append(f"{rel}: line {lineno}: duplicate frontmatter key '{key}'")
            continue
        seen.add(key)
        fields[key] = value
    if errors:
        return None, body, errors
    return fields, body, errors


def validate_frontmatter_fields(fields: dict[str, str], dir_name: str, rel: str) -> list[str]:
    errors = []
    name = fields.get("name")
    if name is None:
        errors.append(f"{rel}: frontmatter missing required key 'name'")
    else:
        if name != dir_name:
            errors.append(f"{rel}: frontmatter name '{name}' does not match directory '{dir_name}'")
        if not NAME_RE.match(name):
            errors.append(f"{rel}: frontmatter name '{name}' does not match required pattern")

    description = fields.get("description")
    if description is None:
        errors.append(f"{rel}: frontmatter missing required key 'description'")
    else:
        if description != description.strip():
            errors.append(f"{rel}: frontmatter description has leading or trailing whitespace")
        if "\t" in description:
            errors.append(f"{rel}: frontmatter description contains a tab character")
        if CONTROL_RE.search(description):
            errors.append(f"{rel}: frontmatter description contains a control character")
        if not (1 <= len(description) <= 1024):
            errors.append(f"{rel}: frontmatter description must be 1-1024 characters")

    version = fields.get("version")
    if version is None:
        errors.append(f"{rel}: frontmatter missing required key 'version'")
    elif not VERSION_RE.match(version):
        errors.append(f"{rel}: frontmatter version '{version}' does not match required pattern")
    return errors


def validate_headings(body: str, rel: str) -> list[str]:
    errors: list[str] = []
    body_lines = body.split("\n")
    headings: list[tuple[int, str]] = []
    for idx, line in enumerate(body_lines):
        m = H2_RE.match(line)
        if m:
            headings.append((idx, m.group(1)))

    counts: dict[str, int] = {h: 0 for h in REQUIRED_HEADINGS}
    for _idx, text in headings:
        if text in counts:
            counts[text] += 1
    for heading in REQUIRED_HEADINGS:
        if counts[heading] == 0:
            errors.append(f"{rel}: missing required heading '## {heading}'")
        elif counts[heading] > 1:
            errors.append(f"{rel}: heading '## {heading}' appears {counts[heading]} times, expected exactly once")

    first_seen: list[str] = []
    seen_set: set[str] = set()
    for _idx, text in headings:
        if text in counts and text not in seen_set:
            seen_set.add(text)
            first_seen.append(text)
    if seen_set == set(REQUIRED_HEADINGS) and first_seen != REQUIRED_HEADINGS:
        errors.append(f"{rel}: required headings are out of order (expected {', '.join(REQUIRED_HEADINGS)})")

    boundaries = [idx for idx, _ in headings] + [len(body_lines)]
    for heading in REQUIRED_HEADINGS:
        matches = [idx for idx, text in headings if text == heading]
        if not matches:
            continue
        start = matches[0]
        next_idx = next((j for j in boundaries if j > start), len(body_lines))
        section_lines = body_lines[start + 1:next_idx]
        content_lines = [ln for ln in section_lines if ln.strip() != "" and not HEADING_LINE_RE.match(ln)]
        if not content_lines:
            errors.append(f"{rel}: section '## {heading}' has no non-blank body content")
        nonwhitespace = sum(len(re.sub(r"\s", "", ln)) for ln in section_lines)
        if nonwhitespace < MIN_SECTION_CHARS:
            errors.append(
                f"{rel}: section '## {heading}' has {nonwhitespace} non-whitespace characters, "
                f"needs at least {MIN_SECTION_CHARS}"
            )
    return errors


def validate_skill(root: Path, skill_dir: Path) -> list[str]:
    rel_dir = _relpath(root, skill_dir)
    skill_md = skill_dir / "SKILL.md"
    rel_md = _relpath(root, skill_md)
    st = _lstat_or_none(skill_md)
    if st is None:
        return [f"{rel_dir}: missing SKILL.md"]
    if fssafety.is_link_like(st):
        return [f"{rel_md}: refusing to read - is a {fssafety.describe_link(st)}"]
    if not stat.S_ISREG(st.st_mode):
        return [f"{rel_md}: exists but is not a regular file"]

    text, errors = _read_text_utf8(skill_md, rel_md)
    if text is None:
        return errors
    text, newline_errors = _normalize_newlines(text, rel_md)
    if text is None:
        return newline_errors

    fields, body, fm_errors = parse_frontmatter(text, rel_md)
    errors.extend(fm_errors)
    if fields is not None:
        errors.extend(validate_frontmatter_fields(fields, skill_dir.name, rel_md))
        errors.extend(validate_headings(body, rel_md))
    return errors


# --------------------------------------------------------------------------- schemas / templates
def _scan_json_dir(root: Path, rel_dir: str, required_names: list[str]) -> tuple[int, list[str]]:
    errors: list[str] = []
    entries, dir_errors = check_top_level_dir(root, rel_dir)
    errors.extend(dir_errors)
    if entries is None:
        return 0, errors
    present: set[str] = set()
    n_json = 0
    for entry in entries:
        rel = _relpath(root, entry)
        st = _lstat_or_none(entry)
        if st is None:
            continue
        if fssafety.is_link_like(st):
            errors.append(f"{rel}: refusing to read - is a {fssafety.describe_link(st)}")
            present.add(entry.name)
            continue
        present.add(entry.name)
        if not stat.S_ISREG(st.st_mode) or entry.suffix != ".json":
            continue
        n_json += 1
        text, read_errors = _read_text_utf8(entry, rel)
        if text is None:
            errors.extend(read_errors)
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
    label = "schema" if rel_dir == "schemas" else "template"
    for name in required_names:
        if name not in present:
            errors.append(f"{rel_dir}/{name}: missing expected {label}")
    return n_json, errors


def check_schemas(root: Path) -> tuple[int, list[str]]:
    return _scan_json_dir(root, "schemas", REQUIRED_SCHEMAS)


def check_templates(root: Path) -> list[str]:
    _n, errors = _scan_json_dir(root, "templates", REQUIRED_TEMPLATES)
    return errors


# --------------------------------------------------------------------------- legacy unsafe-pattern scan
def check_legacy_unsafe_patterns(root: Path) -> list[str]:
    """Pre-WS3 regex scan for unsafe shell/process patterns; same scope and exemption as before WS3-A."""
    errors: list[str] = []
    candidates = list((root / "scripts").glob("*")) + list((root / "skills").glob("*/SKILL.md"))
    for p in candidates:
        if not p.is_file() or p.name == "validate.py":
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        for pattern in LEGACY_UNSAFE_PATTERNS:
            if re.search(pattern, text, re.I):
                errors.append(f"{_relpath(root, p)}: unsafe pattern {pattern}")
    return errors


# --------------------------------------------------------------------------- adapter parity
def check_adapter_parity(root: Path) -> list[str]:
    """Shell out to scripts/sync_adapters.py --check under this root; never --sync, never mutate."""
    sync_script = root / "scripts" / "sync_adapters.py"
    if not sync_script.exists():
        return []
    try:
        result = subprocess.run(
            [sys.executable, str(sync_script), "--check"],
            capture_output=True,
            timeout=120,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return ["scripts/sync_adapters.py: adapter parity check timed out after 120 seconds"]
    except OSError as exc:
        return [f"scripts/sync_adapters.py: cannot run adapter parity check ({exc.strerror or exc})"]
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip() or f"exit code {result.returncode}"
        return [f"scripts/sync_adapters.py: adapter parity check failed: {detail}"]
    return []


# --------------------------------------------------------------------------- orchestration
def collect_errors(root: Path) -> tuple[list[str], int, int]:
    errors: list[str] = []

    skill_entries, skills_dir_errors = check_top_level_dir(root, "skills")
    errors.extend(skills_dir_errors)
    lock_names, lock_errors = load_skills_lock(root)
    errors.extend(lock_errors)

    n_skills = 0
    if skill_entries is not None and lock_names is not None:
        valid_dirs, inv_errors = check_skills_inventory(root, skill_entries, lock_names)
        errors.extend(inv_errors)
        n_skills = len(valid_dirs)
        for skill_dir in valid_dirs:
            errors.extend(validate_skill(root, skill_dir))

    n_schemas, schema_errors = check_schemas(root)
    errors.extend(schema_errors)
    errors.extend(check_templates(root))

    for adapter_dir in ADAPTER_DIRS:
        errors.extend(check_no_links_in_dir(root, adapter_dir))

    errors.extend(check_adapter_parity(root))
    errors.extend(check_legacy_unsafe_patterns(root))

    return errors, n_skills, n_schemas


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print(f"ERROR: command line: unexpected arguments: {' '.join(argv)}", file=sys.stderr)
        print("Validation FAILED: 1 error(s)", file=sys.stderr)
        return 1

    resolved_root = Path(root).resolve() if root is not None else ROOT
    errors, n_skills, n_schemas = collect_errors(resolved_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Validation FAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(f"Validation OK: {n_skills} skills, {n_schemas} schemas, adapter parity confirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
