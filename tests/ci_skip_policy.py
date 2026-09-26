#!/usr/bin/env python3
"""Gate the skips of ``python -m unittest discover -s tests -v`` against the per-platform CI policy (finding F16).

CI runs the full suite on Linux, Windows and macOS. The suite skips tests that exist for one platform only (Windows
junctions and file attributes, POSIX signals and ``#!`` scripts) and tests whose host capability is missing (symbolic
links, hard links, junction creation). Every skip must therefore be one the platform is expected to produce; any
other skip hides coverage and fails the job. All of the logic lives here as importable, unit-tested functions
(tests/test_ci_skip_policy.py); .github/workflows/ci.yml only calls this file.

Usage:
    python tests/ci_skip_policy.py --platform <Linux|Windows|macOS> --log <unittest.log> --rc <unittest.rc>
                                   [--report <path>] [--allow-reason <substring>]... [--require-symlinks]
        <unittest.log> is the complete ``-v`` output (stdout and stderr together) and <unittest.rc> holds its exit
        status. Prints a report naming every skipped test with its reason and classification, GitHub ``::warning::``
        and ``::error::`` annotations, and the verdict. --report also writes the report to a file (CI uploads it).
    python tests/ci_skip_policy.py --probe
        Print, without ever failing, whether this host can create a symbolic link, a hard link and (Windows) a
        junction inside its temporary directory. CI records the output as evidence next to the unittest log.

Exit codes (stable): 0 pass, 1 policy failure, 2 usage error (bad arguments, unknown platform, unreadable inputs).

Policy, reason class x platform (``POLICY`` below is the reviewable source of truth):
    windows-only          Linux, macOS: EXPECTED   Windows: FAIL (the feature exists there by definition)
    posix-only            Linux, macOS: FAIL       Windows: EXPECTED
    junction-capability   FAIL everywhere (windows-latest can create junctions; elsewhere the tests are win32-gated)
    symlink-capability    Linux, macOS: FAIL       Windows: WARNING (::warning:: annotation), or FAIL when
                          CI_REQUIRE_SYMLINKS=1 is set or --require-symlinks is given
    hardlink-capability   FAIL everywhere (NTFS and the POSIX runners support hard links in the temporary directory)
    line-endings          FAIL everywhere (.gitattributes eol=lf must give LF working copies even under core.autocrlf)
    unknown               FAIL everywhere (an unrecognised skip is not allowed to hide coverage)
    --allow-reason SUB    a skip whose reason contains SUB (case-insensitive) is ALLOWED: a coordinator escape hatch
Independently of the skips, the verdict is FAIL when the exit status is non-zero, the ``Ran N tests`` line or the
OK/FAILED summary is missing, the summary is FAILED, N is 0, the number of skip lines found differs from the
summary's ``skipped=N``, or (Windows only) a test in ``REQUIRED_OK_ON_WINDOWS`` is not reported ``... ok``.

The parser accepts the Python 3.10 (``name (module.Class)``) and 3.11+ (``name (module.Class.name)``) formats,
sub-test lines, first-docstring-line continuation lines, bare status lines and CRLF line endings.

No ``from __future__ import annotations``: every annotation is valid at run time on Python 3.10+, and real (non-string)
annotations keep the dataclasses working when this file is loaded through importlib.util without a sys.modules entry.
"""
import argparse
import ast
import dataclasses
import os
import platform as platform_module
import re
import sys
import tempfile
from pathlib import Path

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

LINUX = "Linux"
WINDOWS = "Windows"
MACOS = "macOS"
PLATFORMS = (LINUX, WINDOWS, MACOS)
_PLATFORM_ALIASES = {"linux": LINUX, "windows": WINDOWS, "win32": WINDOWS, "macos": MACOS, "darwin": MACOS}

EXPECTED = "EXPECTED"
WARNING = "WARNING"
FAIL = "FAIL"
ALLOWED = "ALLOWED"

WINDOWS_ONLY = "windows-only"
POSIX_ONLY = "posix-only"
JUNCTION_CAPABILITY = "junction-capability"
SYMLINK_CAPABILITY = "symlink-capability"
HARDLINK_CAPABILITY = "hardlink-capability"
LINE_ENDINGS = "line-endings"
UNKNOWN = "unknown"
REASON_CLASSES = (
    WINDOWS_ONLY, POSIX_ONLY, JUNCTION_CAPABILITY, SYMLINK_CAPABILITY, HARDLINK_CAPABILITY, LINE_ENDINGS, UNKNOWN,
)

# Matched first, in this order, as case-insensitive substrings of the skip reason. They come before the platform
# words because a junction-capability reason also says "junction" and a POSIX-only reason may mention Windows.
CAPABILITY_MARKERS = (
    (SYMLINK_CAPABILITY, "cannot create symbolic links on this host"),
    (HARDLINK_CAPABILITY, "hard links unavailable on this host"),
    (JUNCTION_CAPABILITY, "junction creation not permitted"),
    (LINE_ENDINGS, "checkout translated line endings"),
)
POSIX_ONLY_PREFIX = "posix-only"
WINDOWS_ONLY_WORDS = ("windows", "win32", "junction", "read-only attribute", "drive roots", "os-essential")

# Verdict per reason class and platform. WARNING becomes FAIL when symbolic links are required (see below).
POLICY: dict[str, dict[str, str]] = {
    WINDOWS_ONLY: {LINUX: EXPECTED, MACOS: EXPECTED, WINDOWS: FAIL},
    POSIX_ONLY: {LINUX: FAIL, MACOS: FAIL, WINDOWS: EXPECTED},
    JUNCTION_CAPABILITY: {LINUX: FAIL, MACOS: FAIL, WINDOWS: FAIL},
    SYMLINK_CAPABILITY: {LINUX: FAIL, MACOS: FAIL, WINDOWS: WARNING},
    HARDLINK_CAPABILITY: {LINUX: FAIL, MACOS: FAIL, WINDOWS: FAIL},
    LINE_ENDINGS: {LINUX: FAIL, MACOS: FAIL, WINDOWS: FAIL},
    UNKNOWN: {LINUX: FAIL, MACOS: FAIL, WINDOWS: FAIL},
}

# Set to 1 in the workflow only once a capability probe has shown that windows-latest can create symbolic links.
REQUIRE_SYMLINKS_ENV = "CI_REQUIRE_SYMLINKS"
_TRUE_VALUES = ("1", "true", "yes", "on")

# Audit finding F1: the junction tests must be proven to EXECUTE on Windows, not merely not to be skipped.
# ``python -m unittest discover -s tests`` prints them without the ``tests.`` package prefix; both spellings match.
REQUIRED_OK_ON_WINDOWS = (
    "tests.test_fssafety.ChainTests.test_windows_junction_parent_refused",
    "tests.test_sync_adapters.RefusalTests.test_t1_2_windows_junction_parent_refused",
    "tests.test_bootstrap.RefusalTests.test_t2_3_windows_junction_parent_refused",
    "tests.test_validate.LinkSafetyTests.test_windows_junction_skill_directory",
)

_TEST_LINE_RE = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*) \((?P<qual>[A-Za-z_][A-Za-z0-9_.]*)\)(?P<rest>.*)$")
_REST_RE = re.compile(r"^(?P<sub>.*?) \.\.\. (?P<status>.*)$")
_STATUS_RE = re.compile(r"^(?P<kind>ok|FAIL|ERROR|expected failure|unexpected success|skipped)(?: (?P<detail>.*))?$")
_CONTINUATION_RE = re.compile(r"^.* \.\.\. (?P<status>.*)$")
_RAN_RE = re.compile(r"^Ran (?P<n>\d+) tests? in ")
_SUMMARY_RE = re.compile(r"^(?P<verdict>OK|FAILED)(?: \((?P<counts>[^)]*)\))?\s*$")


# --------------------------------------------------------------------------- log parsing
@dataclasses.dataclass(frozen=True)
class TestOutcome:
    """One result line: ``test_id`` is ``module.Class.method`` as printed, ``reason`` is set for skips only."""

    test_id: str
    status: str
    reason: str
    line: int
    subtest: str = ""


@dataclasses.dataclass
class ParsedLog:
    outcomes: list[TestOutcome]
    ran: int | None
    summary: str | None
    counts: dict[str, int]
    line_count: int

    @property
    def skips(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if o.status == "skipped"]


@dataclasses.dataclass(frozen=True)
class _Status:
    kind: str
    reason: str


def _unrepr(text: str) -> str:
    """Recover a skip reason from unittest's ``{reason!r}`` rendering; fall back to stripping the quotes."""
    text = text.strip()
    if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            value = None
        return value if isinstance(value, str) else text[1:-1]
    return text


def _parse_status(text: str) -> _Status | None:
    match = _STATUS_RE.match(text.strip())
    if not match:
        return None
    kind, detail = match["kind"], match["detail"] or ""
    if kind == "skipped":
        return _Status(kind, _unrepr(detail))
    return _Status(kind, "") if detail == "" else None


def _full_id(name: str, qual: str) -> str:
    """3.11+ prints ``name (module.Class.name)``; 3.10 prints ``name (module.Class)``: complete the latter."""
    return qual if qual.endswith("." + name) else qual + "." + name


def canonical_test_id(test_id: str) -> str:
    """Strip the ``tests.`` package prefix so discover-style and package-style ids compare equal."""
    return test_id[len("tests."):] if test_id.startswith("tests.") else test_id


def parse_unittest_log(text: str) -> ParsedLog:
    """Parse ``unittest -v`` output (any line ending); lines other than results, ``Ran`` and the summary are ignored."""
    outcomes: list[TestOutcome] = []
    ran: int | None = None
    summary: str | None = None
    counts: dict[str, int] = {}
    last_id: str | None = None
    lines = text.splitlines()
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r")
        test_match = _TEST_LINE_RE.match(line)
        if test_match:
            test_id = _full_id(test_match["name"], test_match["qual"])
            last_id = test_id
            rest_match = _REST_RE.match(test_match["rest"])
            if rest_match:
                status = _parse_status(rest_match["status"])
                if status is not None:
                    outcomes.append(TestOutcome(test_id, status.kind, status.reason, lineno, rest_match["sub"].strip()))
            continue
        bare = _parse_status(line)
        if bare is not None and last_id is not None:
            outcomes.append(TestOutcome(last_id, bare.kind, bare.reason, lineno))
            continue
        continuation = _CONTINUATION_RE.match(line)
        if continuation and last_id is not None:
            status = _parse_status(continuation["status"])
            if status is not None:
                outcomes.append(TestOutcome(last_id, status.kind, status.reason, lineno))
                continue
        ran_match = _RAN_RE.match(line)
        if ran_match:
            ran = int(ran_match["n"])
            continue
        summary_match = _SUMMARY_RE.match(line)
        if summary_match and ran is not None:
            summary = summary_match["verdict"]
            counts = {}
            for item in (summary_match["counts"] or "").split(","):
                key, sep, value = item.strip().partition("=")
                if sep and value.strip().isdigit():
                    counts[key.strip()] = int(value.strip())
    return ParsedLog(outcomes, ran, summary, counts, len(lines))


# --------------------------------------------------------------------------- classification
def classify_reason(reason: str) -> str:
    """Map a skip reason to one of ``REASON_CLASSES``; see the module docstring for the marker order."""
    lowered = reason.lower()
    for reason_class, marker in CAPABILITY_MARKERS:
        if marker in lowered:
            return reason_class
    if lowered.lstrip().startswith(POSIX_ONLY_PREFIX):
        return POSIX_ONLY
    if any(word in lowered for word in WINDOWS_ONLY_WORDS):
        return WINDOWS_ONLY
    return UNKNOWN


def normalize_platform(value: str) -> str:
    """Accept GitHub's ``runner.os`` values (Linux, Windows, macOS) case-insensitively, plus win32/darwin aliases."""
    try:
        return _PLATFORM_ALIASES[value.strip().lower()]
    except KeyError:
        raise ValueError(f"unknown platform {value!r}; expected one of {', '.join(PLATFORMS)}") from None


def symlinks_required(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(REQUIRE_SYMLINKS_ENV, "").strip().lower() in _TRUE_VALUES


def verdict_for(reason_class: str, platform: str, require_symlinks: bool = False) -> str:
    verdict = POLICY[reason_class][platform]
    if verdict == WARNING and require_symlinks:
        return FAIL
    return verdict


# --------------------------------------------------------------------------- evaluation
@dataclasses.dataclass(frozen=True)
class SkipFinding:
    test_id: str
    subtest: str
    reason: str
    reason_class: str
    verdict: str
    note: str


@dataclasses.dataclass
class Evaluation:
    platform: str
    rc: int
    parsed: ParsedLog
    require_symlinks: bool
    allow_reasons: tuple[str, ...]
    skips: list[SkipFinding]
    required: list[tuple[str, str]]
    warnings: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def _summary_text(parsed: ParsedLog) -> str:
    if parsed.summary is None:
        return "missing"
    if not parsed.counts:
        return parsed.summary
    return parsed.summary + " (" + ", ".join(f"{k}={v}" for k, v in parsed.counts.items()) + ")"


def _check_required(parsed: ParsedLog, platform: str) -> tuple[list[tuple[str, str]], list[str]]:
    if platform != WINDOWS:
        return [], []
    statuses: dict[str, list[str]] = {}
    for outcome in parsed.outcomes:
        if not outcome.subtest:
            statuses.setdefault(canonical_test_id(outcome.test_id), []).append(outcome.status)
    rows: list[tuple[str, str]] = []
    failures: list[str] = []
    for test_id in REQUIRED_OK_ON_WINDOWS:
        seen = statuses.get(canonical_test_id(test_id), [])
        if not seen:
            rows.append((test_id, "MISSING"))
            failures.append(f"required Windows test is missing from the log (must run and pass): {test_id}")
        elif all(status == "ok" for status in seen):
            rows.append((test_id, "ok"))
        else:
            rows.append((test_id, seen[-1]))
            failures.append(f"required Windows test did not pass (status {seen[-1]!r}): {test_id}")
    return rows, failures


def evaluate(log_text: str, rc: int, platform: str, allow_reasons: tuple[str, ...] | list[str] = (),
             require_symlinks: bool | None = None) -> Evaluation:
    """Apply the policy; ``require_symlinks=None`` consults the CI_REQUIRE_SYMLINKS environment variable."""
    platform = normalize_platform(platform)
    if require_symlinks is None:
        require_symlinks = symlinks_required()
    allow = tuple(a for a in allow_reasons if a)
    parsed = parse_unittest_log(log_text)
    failures: list[str] = []
    warnings: list[str] = []
    if rc != 0:
        failures.append(f"unittest exit status {rc} (expected 0)")
    if parsed.ran is None:
        failures.append("no 'Ran N tests' line in the log (the run did not finish or this is not unittest -v output)")
    elif parsed.ran == 0:
        failures.append("Ran 0 tests")
    if parsed.summary is None:
        failures.append("no OK/FAILED summary line in the log")
    elif parsed.summary != "OK":
        failures.append(f"unittest summary is {_summary_text(parsed)}")
    skips: list[SkipFinding] = []
    for outcome in parsed.skips:
        reason_class = classify_reason(outcome.reason)
        lowered = outcome.reason.lower()
        allowed_by = next((a for a in allow if a.lower() in lowered), None)
        if allowed_by is not None:
            verdict, note = ALLOWED, f"allowed by --allow-reason {allowed_by!r}"
        else:
            verdict = verdict_for(reason_class, platform, require_symlinks)
            note = f"{reason_class} skip on {platform}"
            if reason_class == SYMLINK_CAPABILITY and platform == WINDOWS:
                note += (" with CI_REQUIRE_SYMLINKS set" if require_symlinks
                         else " (privilege question on windows-latest; set CI_REQUIRE_SYMLINKS=1 to fail)")
        where = outcome.test_id + (f" {outcome.subtest}" if outcome.subtest else "")
        skips.append(SkipFinding(outcome.test_id, outcome.subtest, outcome.reason, reason_class, verdict, note))
        if verdict == FAIL:
            failures.append(f"{note}: {where}: {outcome.reason}")
        elif verdict == WARNING:
            warnings.append(f"{note}: {where}: {outcome.reason}")
    if parsed.summary is not None:
        counted = parsed.counts.get("skipped", 0)
        if counted != len(skips):
            failures.append(f"the summary counts skipped={counted} but {len(skips)} skip lines were found in the log; "
                            "an unparsed skip could hide coverage")
    required, required_failures = _check_required(parsed, platform)
    failures.extend(required_failures)
    return Evaluation(platform, rc, parsed, require_symlinks, allow, skips, required, warnings, failures)


# --------------------------------------------------------------------------- reporting
def render_report(evaluation: Evaluation, log_path: str = "<text>") -> str:
    parsed = evaluation.parsed
    if evaluation.require_symlinks:
        symlink_rule = "set -> symlink-capability skips on Windows FAIL"
    else:
        symlink_rule = "unset -> symlink-capability skips on Windows are WARNINGs"
    allow_text = ", ".join(repr(a) for a in evaluation.allow_reasons) or "(none)"
    lines = [
        "ci_skip_policy report",
        f"  platform:             {evaluation.platform}",
        f"  log:                  {log_path} ({parsed.line_count} lines, {len(parsed.outcomes)} result lines)",
        f"  unittest exit status: {evaluation.rc}",
        f"  ran:                  {'missing' if parsed.ran is None else str(parsed.ran) + ' tests'}",
        f"  summary:              {_summary_text(parsed)}",
        f"  {REQUIRE_SYMLINKS_ENV}:  {symlink_rule}",
        f"  allow-reason:         {allow_text}",
        "",
        f"skipped tests ({len(evaluation.skips)}), verdict | class | test | reason:",
    ]
    for finding in evaluation.skips:
        where = finding.test_id + (f" {finding.subtest}" if finding.subtest else "")
        lines.append(f"  {finding.verdict:<8} | {finding.reason_class:<19} | {where} | {finding.reason}")
    if not evaluation.skips:
        lines.append("  (none)")
    if evaluation.platform == WINDOWS:
        lines += ["", f"required '... ok' on Windows ({len(evaluation.required)}), status | test:"]
        lines += [f"  {status:<8} | {test_id}" for test_id, status in evaluation.required]
    lines += ["", f"warnings ({len(evaluation.warnings)}):"] + [f"  {w}" for w in evaluation.warnings]
    lines += ["", f"failures ({len(evaluation.failures)}):"] + [f"  {f}" for f in evaluation.failures]
    lines += ["", f"verdict: {'PASS' if evaluation.passed else 'FAIL'}"]
    return "\n".join(lines)


def _annotation(level: str, title: str, message: str) -> str:
    def escape(text: str) -> str:
        return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::{level} title={escape(title)}::{escape(message)}"


def annotations(evaluation: Evaluation) -> list[str]:
    """GitHub workflow commands: one ``::warning::`` per warning and one ``::error::`` per failure."""
    out = [_annotation("warning", "ci_skip_policy", w) for w in evaluation.warnings]
    out += [_annotation("error", "ci_skip_policy", f) for f in evaluation.failures]
    return out


# --------------------------------------------------------------------------- capability probe
def _attempt(action) -> str:
    try:
        action()
    except (OSError, NotImplementedError, AttributeError, ImportError) as exc:
        return f"no: {exc}"
    return "yes"


def _create_junction(target: Path, junction: Path) -> None:  # pragma: no cover - Windows only
    import _winapi
    _winapi.CreateJunction(str(target), str(junction))


def probe_capabilities(base_dir: str | os.PathLike | None = None) -> dict[str, str]:
    """Try a symbolic link, a hard link and (win32) a junction in a fresh temporary directory; never raises."""
    results: dict[str, str] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="ci-probe-", dir=base_dir) as directory:
            root = Path(directory)
            target_file = root / "target.txt"
            target_file.write_bytes(b"probe\n")
            target_dir = root / "target-dir"
            target_dir.mkdir()
            results["symlink"] = _attempt(lambda: os.symlink(target_file, root / "symlink.txt"))
            results["hardlink"] = _attempt(lambda: os.link(target_file, root / "hardlink.txt"))
            if sys.platform == "win32":
                results["junction"] = _attempt(lambda: _create_junction(target_dir, root / "junction"))
            else:
                results["junction"] = "not applicable (junctions exist only on Windows)"
    except Exception as exc:  # noqa: BLE001 - the probe is evidence, never a gate
        for key in ("symlink", "hardlink", "junction"):
            results.setdefault(key, f"not probed: {exc!r}")
    return results


def render_probe(results: dict[str, str]) -> str:
    env_value = os.environ.get(REQUIRE_SYMLINKS_ENV)
    lines = [
        "capability probe (evidence only; this step never fails)",
        f"  platform:            {platform_module.platform()}",
        f"  sys.platform:        {sys.platform}",
        f"  python:              {sys.version.replace(chr(10), ' ')}",
        f"  tempdir:             {tempfile.gettempdir()}",
    ]
    lines += [f"  {key + ':':<20} {value}" for key, value in results.items()]
    lines.append(f"  {REQUIRE_SYMLINKS_ENV}: {'unset' if env_value is None else repr(env_value)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- command line
def read_log(path: str) -> str:
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace")


def read_rc(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"{path}: expected the unittest exit status as an integer, found {text!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci_skip_policy.py",
        description="Gate unittest skips against the per-platform CI policy, or probe link capabilities.")
    parser.add_argument("--probe", action="store_true",
                        help="print whether this host can create a symlink, a hard link and a junction; never fails")
    parser.add_argument("--platform", metavar="OS", help="runner OS: Linux, Windows or macOS (GitHub's RUNNER_OS)")
    parser.add_argument("--log", metavar="PATH", help="captured 'python -m unittest discover -s tests -v' output")
    parser.add_argument("--rc", metavar="PATH", help="file holding the exit status of that unittest run")
    parser.add_argument("--report", metavar="PATH", help="also write the report to this file")
    parser.add_argument("--allow-reason", action="append", default=[], metavar="SUBSTRING",
                        help="treat skips whose reason contains SUBSTRING as allowed (repeatable)")
    parser.add_argument("--require-symlinks", action="store_true",
                        help=f"fail symlink-capability skips on Windows too (same as {REQUIRE_SYMLINKS_ENV}=1)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.probe:
        print(render_probe(probe_capabilities()))
        return EXIT_PASS
    missing = [name for name in ("platform", "log", "rc") if getattr(args, name) is None]
    if missing:
        parser.error("--" + ", --".join(missing) + " are required unless --probe is given")
    try:
        platform = normalize_platform(args.platform)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        log_text = read_log(args.log)
        rc = read_rc(args.rc)
    except (OSError, ValueError) as exc:
        print(f"ci_skip_policy: cannot read the inputs: {exc}", file=sys.stderr)
        return EXIT_USAGE
    evaluation = evaluate(log_text, rc, platform, allow_reasons=args.allow_reason,
                          require_symlinks=True if args.require_symlinks else None)
    report = render_report(evaluation, log_path=args.log)
    print(report)
    if args.report:
        try:
            Path(args.report).write_text(report + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ci_skip_policy: cannot write the report: {exc}", file=sys.stderr)
            return EXIT_USAGE
    for line in annotations(evaluation):
        print(line)
    return EXIT_PASS if evaluation.passed else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
