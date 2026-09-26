"""Unit tests for tests/ci_skip_policy.py (audit finding F16: the CI skip-gating policy).

Synthetic ``unittest -v`` logs stand in for the real suite output so every rule is exercised for every platform
without running CI: the eight skips Linux and macOS are expected to produce, Windows with junction and symlink skips,
CI_REQUIRE_SYMLINKS, non-zero exit statuses, missing or FAILED summaries, unknown reasons, --allow-reason, the
required junction tests on Windows, the Python 3.10 and 3.11+ output formats, sub-test, docstring and bare status
continuation lines, CRLF line endings, the command line exit codes and the capability probe.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load():
    spec = importlib.util.spec_from_file_location("ci_skip_policy_under_test", HERE / "ci_skip_policy.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # the documented importlib recipe; dataclasses look the module up by name
    spec.loader.exec_module(mod)
    return mod


policy = _load()

# The eight skips the suite produces on Linux and macOS: verbatim ids and reasons from a 3.11 discover run.
LINUX_EXPECTED_SKIPS = (
    ("test_bootstrap.ForceAndBackupTests.test_t2_7b_windows_force_replaces_a_read_only_file_after_backing_it_up",
     "the read-only attribute is a Windows concept"),
    ("test_bootstrap.RefusalTests.test_t2_3_windows_junction_parent_refused",
     "T2.3 requires Windows: junctions are NTFS reparse points and cannot be created on this host"),
    ("test_bootstrap.TargetAndPreflightTests.test_t2_5c_windows_drive_root_and_system_directories_refused",
     "drive roots and %SystemRoot% exist only on Windows"),
    ("test_fssafety.ChainTests.test_windows_junction_parent_refused",
     "Windows junctions (NTFS reparse points) do not exist on this host"),
    ("test_fssafety.ReadOnlyAttributeTests.test_windows_read_only_entries_are_deleted_and_replaced",
     "the read-only attribute exists only on Windows"),
    ("test_run_tool.EnvironmentTests.test_windows_essential_variables_passed",
     "Windows-only: OS-essential variables are passed only on win32"),
    ("test_sync_adapters.RefusalTests.test_t1_2_windows_junction_parent_refused",
     "T1.2 requires Windows: junctions are NTFS reparse points and cannot be created on this host"),
    ("test_validate.LinkSafetyTests.test_windows_junction_skill_directory",
     "Windows junctions (NTFS reparse points) do not exist on this host"),
)
# The three skips Windows is expected to produce.
WINDOWS_EXPECTED_SKIPS = (
    ("test_run_tool.EnvironmentTests.test_bare_name_resolved_against_child_path",
     "POSIX-only: uses a #! script as the tool executable"),
    ("test_run_tool.ProcessControlTests.test_timeout_kills_process_group_exit_124",
     "POSIX-only: observes the grandchild with kill(pid, 0) after an os.killpg"),
    ("test_run_tool.ProcessControlTests.test_signal_death_maps_to_128_plus_n",
     "POSIX-only: signal deaths do not exist on Windows"),
)
# Capability and line-ending skip reasons, in the shape the suite raises them (exception text appended).
SYMLINK_REASON = ("cannot create symbolic links on this host: [WinError 1314] A required privilege is not held by "
                  "the client: 'C:\\Users\\r\\t.txt' -> 'D:\\a\\_temp\\link.txt'")
HARDLINK_REASON = "hard links unavailable on this host: [Errno 1] Operation not permitted"
JUNCTION_REASON = "T1.2 skipped: junction creation not permitted for this user: [WinError 5] Access is denied"
LINE_ENDINGS_REASON = "checkout translated line endings (core.autocrlf); LF is enforced on POSIX"

COMMON_OK = (
    "test_stack.StackTests.test_adapters_match",
    "test_validate.TopLevelDirTests.test_missing_templates_dir",
    "test_schemas.SchemaTests.test_schema_files_byte_stable",
)
ALL_PLATFORMS = (policy.LINUX, policy.MACOS, policy.WINDOWS)
POSIX_PLATFORMS = (policy.LINUX, policy.MACOS)


def skipped(reason: str) -> str:
    return f"skipped {reason!r}"


def result_line(test_id: str, status: str, py310: bool = False, indent: str = "", subtest: str = "") -> str:
    module_class, _, name = test_id.rpartition(".")
    qual = module_class if py310 else test_id
    sub = f" {subtest}" if subtest else ""
    return f"{indent}{name} ({qual}){sub} ... {status}"


def build_log(results, ran=None, summary="OK", extra_counts="", py310=False, eol="\n", omit_ran=False,
              omit_summary=False, skipped_count=None) -> str:
    """Render a ``unittest -v`` log from (test_id, status) pairs; ``status`` is ``ok``, ``FAIL`` or ``skipped(...)``."""
    lines = [result_line(test_id, status, py310=py310) for test_id, status in results]
    if skipped_count is None:
        skipped_count = sum(1 for _, status in results if status.startswith("skipped"))
    if ran is None:
        ran = len(results)
    lines += ["", "-" * 70]
    if not omit_ran:
        lines.append(f"Ran {ran} tests in 1.234s")
    lines.append("")
    if not omit_summary:
        counts = [extra_counts] if extra_counts else []
        if skipped_count:
            counts.append(f"skipped={skipped_count}")
        lines.append(summary + (f" ({', '.join(counts)})" if counts else ""))
    return eol.join(lines) + eol


def linux_results(extra=()):
    return [(t, "ok") for t in COMMON_OK] + [(t, skipped(r)) for t, r in LINUX_EXPECTED_SKIPS] + list(extra)


def windows_results(extra=(), drop=()):
    windows_ok = [t for t, _ in LINUX_EXPECTED_SKIPS if t not in drop]
    return ([(t, "ok") for t in COMMON_OK] + [(t, "ok") for t in windows_ok]
            + [(t, skipped(r)) for t, r in WINDOWS_EXPECTED_SKIPS] + list(extra))


@contextlib.contextmanager
def env_without_symlink_requirement(**extra):
    with mock.patch.dict(os.environ, extra, clear=False):
        os.environ.pop(policy.REQUIRE_SYMLINKS_ENV, None)
        os.environ.update(extra)
        yield


def evaluate(log, platform, rc=0, **kwargs):
    with env_without_symlink_requirement():
        return policy.evaluate(log, rc, platform, **kwargs)


# --------------------------------------------------------------------------- classification
class ClassificationTests(unittest.TestCase):
    def test_every_verbatim_reason_is_classified(self):
        expected = {reason: policy.WINDOWS_ONLY for _, reason in LINUX_EXPECTED_SKIPS}
        expected.update({reason: policy.POSIX_ONLY for _, reason in WINDOWS_EXPECTED_SKIPS})
        expected.update({
            SYMLINK_REASON: policy.SYMLINK_CAPABILITY,
            HARDLINK_REASON: policy.HARDLINK_CAPABILITY,
            JUNCTION_REASON: policy.JUNCTION_CAPABILITY,
            "junction creation not permitted for this user: [WinError 5]": policy.JUNCTION_CAPABILITY,
            LINE_ENDINGS_REASON: policy.LINE_ENDINGS,
            "needs a network connection": policy.UNKNOWN,
            "": policy.UNKNOWN,
        })
        for reason, reason_class in expected.items():
            with self.subTest(reason=reason):
                self.assertEqual(policy.classify_reason(reason), reason_class)

    def test_policy_table_is_complete(self):
        self.assertEqual(set(policy.POLICY), set(policy.REASON_CLASSES))
        for reason_class, row in policy.POLICY.items():
            self.assertEqual(set(row), set(policy.PLATFORMS), reason_class)
            for verdict in row.values():
                self.assertIn(verdict, (policy.EXPECTED, policy.WARNING, policy.FAIL))
        self.assertEqual(policy.POLICY[policy.WINDOWS_ONLY],
                         {policy.LINUX: "EXPECTED", policy.MACOS: "EXPECTED", policy.WINDOWS: "FAIL"})
        self.assertEqual(policy.POLICY[policy.POSIX_ONLY],
                         {policy.LINUX: "FAIL", policy.MACOS: "FAIL", policy.WINDOWS: "EXPECTED"})
        self.assertEqual(policy.POLICY[policy.SYMLINK_CAPABILITY],
                         {policy.LINUX: "FAIL", policy.MACOS: "FAIL", policy.WINDOWS: "WARNING"})
        for reason_class in (policy.JUNCTION_CAPABILITY, policy.HARDLINK_CAPABILITY, policy.LINE_ENDINGS,
                             policy.UNKNOWN):
            self.assertEqual(set(policy.POLICY[reason_class].values()), {"FAIL"}, reason_class)

    def test_symlink_warning_becomes_failure_when_required(self):
        self.assertEqual(policy.verdict_for(policy.SYMLINK_CAPABILITY, policy.WINDOWS), policy.WARNING)
        self.assertEqual(policy.verdict_for(policy.SYMLINK_CAPABILITY, policy.WINDOWS, True), policy.FAIL)
        self.assertEqual(policy.verdict_for(policy.WINDOWS_ONLY, policy.LINUX, True), policy.EXPECTED)

    def test_symlinks_required_reads_the_environment(self):
        for value, expected in (("1", True), ("true", True), ("YES", True), ("0", False), ("", False)):
            self.assertIs(policy.symlinks_required({policy.REQUIRE_SYMLINKS_ENV: value}), expected, value)
        self.assertFalse(policy.symlinks_required({}))

    def test_normalize_platform(self):
        for value, expected in (("Linux", "Linux"), ("linux", "Linux"), ("Windows", "Windows"), ("win32", "Windows"),
                                ("macOS", "macOS"), ("MACOS", "macOS"), ("darwin", "macOS"), (" Linux ", "Linux")):
            self.assertEqual(policy.normalize_platform(value), expected)
        with self.assertRaises(ValueError):
            policy.normalize_platform("freebsd")

    def test_required_windows_tests_are_the_four_junction_tests(self):
        self.assertEqual(len(policy.REQUIRED_OK_ON_WINDOWS), 4)
        for test_id in policy.REQUIRED_OK_ON_WINDOWS:
            self.assertTrue(test_id.startswith("tests.test_"), test_id)
            self.assertIn("junction", test_id)
            self.assertIn(policy.canonical_test_id(test_id), [t for t, _ in LINUX_EXPECTED_SKIPS])
        self.assertEqual(policy.canonical_test_id("tests.test_x.C.test_y"), "test_x.C.test_y")
        self.assertEqual(policy.canonical_test_id("test_x.C.test_y"), "test_x.C.test_y")


# --------------------------------------------------------------------------- parsing
class ParserTests(unittest.TestCase):
    def test_311_format_with_crlf(self):
        log = build_log(linux_results(), eol="\r\n")
        parsed = policy.parse_unittest_log(log)
        self.assertEqual(parsed.ran, len(COMMON_OK) + len(LINUX_EXPECTED_SKIPS))
        self.assertEqual(parsed.summary, "OK")
        self.assertEqual(parsed.counts, {"skipped": 8})
        self.assertEqual([o.test_id for o in parsed.skips], [t for t, _ in LINUX_EXPECTED_SKIPS])
        self.assertEqual([o.reason for o in parsed.skips], [r for _, r in LINUX_EXPECTED_SKIPS])
        self.assertTrue(all(o.status == "ok" for o in parsed.outcomes if o.test_id in COMMON_OK))
        self.assertFalse(any("\r" in o.reason for o in parsed.skips))

    def test_310_format_completes_the_method_name(self):
        log = build_log(linux_results(), py310=True)
        parsed = policy.parse_unittest_log(log)
        self.assertEqual([o.test_id for o in parsed.skips], [t for t, _ in LINUX_EXPECTED_SKIPS])
        self.assertIn(result_line(COMMON_OK[0], "ok", py310=True).split(" ...")[0],
                      "test_adapters_match (test_stack.StackTests)")

    def test_subtest_lines_311(self):
        parent = "test_schemas.SchemaTests.test_schema_files_byte_stable"
        module_class, _, name = parent.rpartition(".")
        lines = [
            f"{name} ({parent}) ... ",
            result_line(parent, skipped(LINE_ENDINGS_REASON), indent="  ", subtest="(path='waiver.schema.json')"),
            result_line(parent, skipped(LINE_ENDINGS_REASON), indent="  ", subtest="(path='x.example.json')"),
            result_line(COMMON_OK[0], "ok"),
            "", "-" * 70, "Ran 2 tests in 0.010s", "", "OK (skipped=2)",
        ]
        parsed = policy.parse_unittest_log("\n".join(lines) + "\n")
        self.assertEqual(len(parsed.skips), 2)
        self.assertEqual({o.test_id for o in parsed.skips}, {parent})
        self.assertEqual([o.subtest for o in parsed.skips], ["(path='waiver.schema.json')", "(path='x.example.json')"])
        self.assertEqual(parsed.counts, {"skipped": 2})

    def test_bare_status_lines_310_subtests(self):
        parent = "test_schemas.SchemaTests.test_schema_files_byte_stable"
        lines = [
            result_line(parent, skipped(LINE_ENDINGS_REASON), py310=True),
            skipped(LINE_ENDINGS_REASON),
            skipped(LINE_ENDINGS_REASON),
            result_line(COMMON_OK[0], "ok", py310=True),
            "", "-" * 70, "Ran 2 tests in 0.010s", "", "OK (skipped=3)",
        ]
        parsed = policy.parse_unittest_log("\n".join(lines) + "\n")
        self.assertEqual([o.test_id for o in parsed.skips], [parent] * 3)
        self.assertEqual(parsed.counts, {"skipped": 3})

    def test_docstring_continuation_and_interleaved_output(self):
        lines = [
            "test_with_docstring (test_x.DemoTests.test_with_docstring)",
            "First docstring line is printed by -v. ... ok",
            "test_noisy (test_x.DemoTests.test_noisy) ... some stderr noise from a child process",
            "ok",
            result_line(COMMON_OK[0], "ok"),
            "Validation OK: 20 skills, 4 schemas, adapter parity confirmed.",
            "ERROR: skills.lock: must use LF line endings (found CR)",
            "", "-" * 70, "Ran 3 tests in 0.010s", "", "OK",
        ]
        parsed = policy.parse_unittest_log("\n".join(lines) + "\n")
        self.assertEqual([(o.test_id, o.status) for o in parsed.outcomes],
                         [("test_x.DemoTests.test_with_docstring", "ok"), ("test_x.DemoTests.test_noisy", "ok"),
                          (COMMON_OK[0], "ok")])
        self.assertEqual(parsed.ran, 3)
        self.assertEqual(parsed.summary, "OK")
        self.assertEqual(parsed.counts, {})

    def test_reason_repr_with_quotes_and_backslashes_is_recovered(self):
        log = build_log([(COMMON_OK[0], skipped(SYMLINK_REASON))])
        self.assertIn('skipped "cannot create', log)
        parsed = policy.parse_unittest_log(log)
        self.assertEqual(parsed.skips[0].reason, SYMLINK_REASON)

    def test_other_statuses_and_failed_summary(self):
        log = build_log([(COMMON_OK[0], "FAIL"), (COMMON_OK[1], "ERROR"), (COMMON_OK[2], "expected failure"),
                         ("test_x.C.test_u", "unexpected success")],
                        summary="FAILED", extra_counts="failures=1, errors=1, expected failures=1")
        parsed = policy.parse_unittest_log(log)
        self.assertEqual([o.status for o in parsed.outcomes],
                         ["FAIL", "ERROR", "expected failure", "unexpected success"])
        self.assertEqual(parsed.summary, "FAILED")
        self.assertEqual(parsed.counts, {"failures": 1, "errors": 1, "expected failures": 1})

    def test_missing_ran_and_summary(self):
        parsed = policy.parse_unittest_log(build_log(linux_results(), omit_ran=True, omit_summary=True))
        self.assertIsNone(parsed.ran)
        self.assertIsNone(parsed.summary)
        self.assertEqual(policy.parse_unittest_log("").line_count, 0)


# --------------------------------------------------------------------------- policy on POSIX runners
class PosixPolicyTests(unittest.TestCase):
    def test_linux_and_macos_baseline_pass_with_eight_expected_skips(self):
        for platform in POSIX_PLATFORMS:
            with self.subTest(platform=platform):
                ev = evaluate(build_log(linux_results()), platform)
                self.assertTrue(ev.passed, ev.failures)
                self.assertEqual(ev.warnings, [])
                self.assertEqual(len(ev.skips), 8)
                self.assertEqual({f.verdict for f in ev.skips}, {policy.EXPECTED})
                self.assertEqual({f.reason_class for f in ev.skips}, {policy.WINDOWS_ONLY})
                self.assertEqual(ev.required, [])
                report = policy.render_report(ev)
                for test_id, reason in LINUX_EXPECTED_SKIPS:
                    self.assertIn(f"EXPECTED | windows-only        | {test_id} | {reason}", report)
                self.assertIn("verdict: PASS", report)
                self.assertNotIn("required '... ok' on Windows", report)

    def test_posix_only_skip_on_a_posix_runner_fails(self):
        test_id, reason = WINDOWS_EXPECTED_SKIPS[0]
        for platform in POSIX_PLATFORMS:
            ev = evaluate(build_log(linux_results([(test_id, skipped(reason))])), platform)
            self.assertFalse(ev.passed)
            self.assertEqual([f.verdict for f in ev.skips if f.test_id == test_id], [policy.FAIL])
            self.assertTrue(any(test_id in f and "posix-only" in f for f in ev.failures), ev.failures)

    def test_symlink_skip_on_a_posix_runner_fails(self):
        for platform in POSIX_PLATFORMS:
            extra = [("test_fssafety.ChainTests.test_symlink", skipped(SYMLINK_REASON))]
            ev = evaluate(build_log(linux_results(extra)), platform)
            self.assertFalse(ev.passed)
            self.assertEqual(ev.warnings, [])
            self.assertIn("symlink-capability", " ".join(ev.failures))

    def test_hardlink_line_endings_junction_and_unknown_skips_fail_everywhere(self):
        cases = {
            HARDLINK_REASON: policy.HARDLINK_CAPABILITY,
            LINE_ENDINGS_REASON: policy.LINE_ENDINGS,
            JUNCTION_REASON: policy.JUNCTION_CAPABILITY,
            "needs a network connection": policy.UNKNOWN,
        }
        for reason, reason_class in cases.items():
            for platform in ALL_PLATFORMS:
                with self.subTest(platform=platform, reason_class=reason_class):
                    base = windows_results if platform == policy.WINDOWS else linux_results
                    ev = evaluate(build_log(base([("test_x.C.test_extra", skipped(reason))])), platform)
                    self.assertFalse(ev.passed)
                    finding = [f for f in ev.skips if f.test_id == "test_x.C.test_extra"][0]
                    self.assertEqual((finding.reason_class, finding.verdict), (reason_class, policy.FAIL))
                    self.assertTrue(any("test_x.C.test_extra" in f for f in ev.failures), ev.failures)


# --------------------------------------------------------------------------- policy on Windows
class WindowsPolicyTests(unittest.TestCase):
    def test_windows_baseline_passes_and_proves_the_junction_tests_ran(self):
        ev = evaluate(build_log(windows_results()), policy.WINDOWS)
        self.assertTrue(ev.passed, ev.failures)
        self.assertEqual(ev.warnings, [])
        self.assertEqual({f.reason_class for f in ev.skips}, {policy.POSIX_ONLY})
        self.assertEqual({f.verdict for f in ev.skips}, {policy.EXPECTED})
        self.assertEqual(ev.required, [(t, "ok") for t in policy.REQUIRED_OK_ON_WINDOWS])
        report = policy.render_report(ev)
        self.assertIn("required '... ok' on Windows (4)", report)
        for test_id in policy.REQUIRED_OK_ON_WINDOWS:
            self.assertIn(f"  ok       | {test_id}", report)

    def test_windows_only_skip_on_windows_fails(self):
        test_id, reason = LINUX_EXPECTED_SKIPS[0]   # the read-only attribute test, not a required junction test
        ev = evaluate(build_log(windows_results([(test_id, skipped(reason))], drop=(test_id,))), policy.WINDOWS)
        self.assertFalse(ev.passed)
        self.assertEqual([f.verdict for f in ev.skips if f.test_id == test_id], [policy.FAIL])
        self.assertTrue(any(test_id in f and "windows-only" in f for f in ev.failures), ev.failures)

    def test_junction_capability_skip_on_windows_fails(self):
        test_id = "test_sync_adapters.RefusalTests.test_t1_2_windows_junction_parent_refused"
        ev = evaluate(build_log(windows_results([(test_id, skipped(JUNCTION_REASON))], drop=(test_id,))),
                      policy.WINDOWS)
        self.assertFalse(ev.passed)
        finding = [f for f in ev.skips if f.test_id == test_id][0]
        self.assertEqual((finding.reason_class, finding.verdict), (policy.JUNCTION_CAPABILITY, policy.FAIL))
        self.assertIn(("tests." + test_id, "skipped"), ev.required)
        self.assertEqual(sum(1 for f in ev.failures if test_id in f), 2)   # the skip itself and the required-ok rule

    def test_symlink_skip_on_windows_warns_but_passes(self):
        test_id = "test_fssafety.ChainTests.test_symlinked_parent_refused"
        ev = evaluate(build_log(windows_results([(test_id, skipped(SYMLINK_REASON))])), policy.WINDOWS)
        self.assertTrue(ev.passed, ev.failures)
        self.assertEqual(len(ev.warnings), 1)
        self.assertIn(test_id, ev.warnings[0])
        finding = [f for f in ev.skips if f.test_id == test_id][0]
        self.assertEqual((finding.reason_class, finding.verdict), (policy.SYMLINK_CAPABILITY, policy.WARNING))
        self.assertIn("CI_REQUIRE_SYMLINKS=1", finding.note)
        lines = policy.annotations(ev)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("::warning title=ci_skip_policy::"), lines[0])
        self.assertIn(test_id, lines[0])
        self.assertNotIn("\n", lines[0])
        self.assertIn("verdict: PASS", policy.render_report(ev))

    def test_symlink_skip_on_windows_fails_when_ci_require_symlinks_is_set(self):
        test_id = "test_fssafety.ChainTests.test_symlinked_parent_refused"
        log = build_log(windows_results([(test_id, skipped(SYMLINK_REASON))]))
        with env_without_symlink_requirement(CI_REQUIRE_SYMLINKS="1"):
            ev = policy.evaluate(log, 0, policy.WINDOWS)
        self.assertFalse(ev.passed)
        self.assertTrue(ev.require_symlinks)
        self.assertEqual(ev.warnings, [])
        self.assertEqual([f.verdict for f in ev.skips if f.test_id == test_id], [policy.FAIL])
        self.assertTrue(any(test_id in f and "CI_REQUIRE_SYMLINKS" in f for f in ev.failures), ev.failures)
        self.assertFalse(evaluate(log, policy.WINDOWS, require_symlinks=True).passed)
        self.assertTrue(evaluate(log, policy.WINDOWS, require_symlinks=False).passed)

    def test_missing_required_junction_ok_line_fails(self):
        for required in policy.REQUIRED_OK_ON_WINDOWS:
            with self.subTest(required=required):
                dropped = policy.canonical_test_id(required)
                ev = evaluate(build_log(windows_results(drop=(dropped,))), policy.WINDOWS)
                self.assertFalse(ev.passed)
                self.assertIn((required, "MISSING"), ev.required)
                self.assertTrue(any(required in f and "missing" in f for f in ev.failures), ev.failures)
                self.assertIn(f"  MISSING  | {required}", policy.render_report(ev))

    def test_required_junction_test_reported_fail_is_a_failure(self):
        test_id = "test_fssafety.ChainTests.test_windows_junction_parent_refused"
        log = build_log(windows_results([(test_id, "FAIL")], drop=(test_id,)), summary="FAILED",
                        extra_counts="failures=1")
        ev = evaluate(log, policy.WINDOWS, rc=1)
        self.assertFalse(ev.passed)
        self.assertIn(("tests." + test_id, "FAIL"), ev.required)
        self.assertTrue(any("did not pass" in f and test_id in f for f in ev.failures), ev.failures)

    def test_package_prefixed_ids_satisfy_the_required_list(self):
        results = [("tests." + t, s) for t, s in windows_results()]
        ev = evaluate(build_log(results), policy.WINDOWS)
        self.assertTrue(ev.passed, ev.failures)
        self.assertEqual({status for _, status in ev.required}, {"ok"})


# --------------------------------------------------------------------------- run-level rules and escape hatches
class RunLevelTests(unittest.TestCase):
    def test_nonzero_exit_status_fails(self):
        ev = evaluate(build_log(linux_results()), policy.LINUX, rc=1)
        self.assertFalse(ev.passed)
        self.assertIn("unittest exit status 1 (expected 0)", ev.failures)

    def test_missing_summary_or_ran_line_fails(self):
        ev = evaluate(build_log(linux_results(), omit_summary=True), policy.LINUX)
        self.assertFalse(ev.passed)
        self.assertTrue(any("no OK/FAILED summary" in f for f in ev.failures), ev.failures)
        ev = evaluate(build_log(linux_results(), omit_ran=True), policy.LINUX)
        self.assertFalse(ev.passed)
        self.assertTrue(any("no 'Ran N tests' line" in f for f in ev.failures), ev.failures)
        ev = evaluate("", policy.LINUX)
        self.assertFalse(ev.passed)

    def test_failed_summary_fails_even_with_exit_status_zero(self):
        log = build_log(linux_results([(COMMON_OK[0], "FAIL")]), summary="FAILED", extra_counts="failures=1")
        ev = evaluate(log, policy.LINUX, rc=0)
        self.assertFalse(ev.passed)
        self.assertTrue(any(f.startswith("unittest summary is FAILED (failures=1, skipped=8)") for f in ev.failures),
                        ev.failures)

    def test_ran_zero_tests_fails(self):
        ev = evaluate(build_log([], ran=0), policy.LINUX)
        self.assertFalse(ev.passed)
        self.assertIn("Ran 0 tests", ev.failures)

    def test_skip_count_mismatch_fails(self):
        ev = evaluate(build_log(linux_results(), skipped_count=9), policy.LINUX)
        self.assertFalse(ev.passed)
        self.assertTrue(any("skipped=9 but 8 skip lines" in f for f in ev.failures), ev.failures)

    def test_allow_reason_turns_a_failing_reason_into_an_allowed_one(self):
        test_id = "test_fssafety.DestinationTests.test_hard_link_refused"
        log = build_log(linux_results([(test_id, skipped(HARDLINK_REASON))]))
        self.assertFalse(evaluate(log, policy.LINUX).passed)
        ev = evaluate(log, policy.LINUX, allow_reasons=["HARD LINKS UNAVAILABLE"])
        self.assertTrue(ev.passed, ev.failures)
        finding = [f for f in ev.skips if f.test_id == test_id][0]
        self.assertEqual((finding.reason_class, finding.verdict), (policy.HARDLINK_CAPABILITY, policy.ALLOWED))
        self.assertIn("allowed by --allow-reason", finding.note)
        self.assertEqual(ev.allow_reasons, ("HARD LINKS UNAVAILABLE",))
        self.assertIn(f"ALLOWED  | hardlink-capability | {test_id} | {HARDLINK_REASON}", policy.render_report(ev))
        self.assertFalse(evaluate(log, policy.LINUX, allow_reasons=["some other reason"]).passed)

    def test_allow_reason_silences_a_warning_but_never_the_required_ok_rule(self):
        symlink_test = "test_fssafety.ChainTests.test_symlinked_parent_refused"
        ev = evaluate(build_log(windows_results([(symlink_test, skipped(SYMLINK_REASON))])), policy.WINDOWS,
                      allow_reasons=["cannot create symbolic links"])
        self.assertTrue(ev.passed)
        self.assertEqual(ev.warnings, [])
        junction_test = "test_validate.LinkSafetyTests.test_windows_junction_skill_directory"
        ev = evaluate(build_log(windows_results([(junction_test, skipped(JUNCTION_REASON))], drop=(junction_test,))),
                      policy.WINDOWS, allow_reasons=["junction creation not permitted"])
        self.assertFalse(ev.passed)
        self.assertEqual([f.verdict for f in ev.skips if f.test_id == junction_test], [policy.ALLOWED])
        self.assertTrue(any("did not pass" in f and junction_test in f for f in ev.failures), ev.failures)


# --------------------------------------------------------------------------- command line
class CliTests(unittest.TestCase):
    def run_cli(self, argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with env_without_symlink_requirement(**(env or {})):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = policy.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def write_inputs(self, directory, log, rc="0", eol="\n"):
        log_path = Path(directory) / "unittest.log"
        rc_path = Path(directory) / "unittest.rc"
        log_path.write_bytes(log.encode("utf-8"))
        rc_path.write_bytes((rc + eol).encode("utf-8"))
        return str(log_path), str(rc_path)

    def test_pass_exit_0_with_report_file(self):
        with tempfile.TemporaryDirectory() as d:
            log_path, rc_path = self.write_inputs(d, build_log(linux_results(), eol="\r\n"), eol="\r\n")
            report_path = str(Path(d) / "report.txt")
            rc, out, err = self.run_cli(["--platform", "Linux", "--log", log_path, "--rc", rc_path,
                                         "--report", report_path])
            self.assertEqual(rc, 0, out + err)
            self.assertIn("verdict: PASS", out)
            self.assertNotIn("::warning", out)
            self.assertNotIn("::error", out)
            written = Path(report_path).read_text(encoding="utf-8")
            self.assertEqual(written.rstrip("\n"), out.rstrip("\n"))
            for test_id, _ in LINUX_EXPECTED_SKIPS:
                self.assertIn(test_id, written)

    def test_fail_exit_1_with_error_annotations(self):
        with tempfile.TemporaryDirectory() as d:
            log_path, rc_path = self.write_inputs(d, build_log(linux_results()), rc="1")
            rc, out, _ = self.run_cli(["--platform", "Linux", "--log", log_path, "--rc", rc_path])
            self.assertEqual(rc, 1)
            self.assertIn("verdict: FAIL", out)
            self.assertIn("::error title=ci_skip_policy::unittest exit status 1 (expected 0)", out)

    def test_windows_symlink_warning_annotation_and_require_flag(self):
        test_id = "test_fssafety.ChainTests.test_symlinked_parent_refused"
        with tempfile.TemporaryDirectory() as d:
            log = build_log(windows_results([(test_id, skipped(SYMLINK_REASON))]), eol="\r\n")
            log_path, rc_path = self.write_inputs(d, "\ufeff" + log, eol="\r\n")
            argv = ["--platform", "Windows", "--log", log_path, "--rc", rc_path]
            rc, out, _ = self.run_cli(argv)
            self.assertEqual(rc, 0, out)
            self.assertIn("::warning title=ci_skip_policy::", out)
            self.assertIn(test_id, out.split("::warning")[1])
            self.assertEqual(self.run_cli(argv + ["--require-symlinks"])[0], 1)
            self.assertEqual(self.run_cli(argv, env={"CI_REQUIRE_SYMLINKS": "1"})[0], 1)
            self.assertEqual(self.run_cli(argv + ["--allow-reason", "cannot create symbolic links"])[0], 0)

    def test_usage_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            log_path, rc_path = self.write_inputs(d, build_log(linux_results()))
            for argv in ([], ["--platform", "Linux"], ["--log", log_path, "--rc", rc_path],
                         ["--platform", "Solaris", "--log", log_path, "--rc", rc_path]):
                with self.subTest(argv=argv):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as cm:
                            policy.main(argv)
                    self.assertEqual(cm.exception.code, 2)
            missing = str(Path(d) / "absent.log")
            self.assertEqual(self.run_cli(["--platform", "Linux", "--log", missing, "--rc", rc_path])[0], 2)
            bad_rc = Path(d) / "bad.rc"
            bad_rc.write_text("not-a-number\n", encoding="utf-8")
            rc, _, err = self.run_cli(["--platform", "Linux", "--log", log_path, "--rc", str(bad_rc)])
            self.assertEqual(rc, 2)
            self.assertIn("expected the unittest exit status as an integer", err)

    def test_module_runs_as_a_script(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            log_path, rc_path = self.write_inputs(d, build_log(linux_results()))
            env = {k: v for k, v in os.environ.items() if k != policy.REQUIRE_SYMLINKS_ENV}
            result = subprocess.run([sys.executable, str(HERE / "ci_skip_policy.py"), "--platform", "Linux",
                                     "--log", log_path, "--rc", rc_path], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("verdict: PASS", result.stdout)


# --------------------------------------------------------------------------- capability probe
class ProbeTests(unittest.TestCase):
    def test_probe_reports_each_capability_without_raising(self):
        results = policy.probe_capabilities()
        self.assertEqual(list(results), ["symlink", "hardlink", "junction"])
        for key in ("symlink", "hardlink"):
            self.assertTrue(results[key] == "yes" or results[key].startswith("no: "), (key, results[key]))
        if sys.platform == "win32":  # pragma: no cover - Windows only
            self.assertTrue(results["junction"] == "yes" or results["junction"].startswith("no: "))
        else:
            self.assertEqual(results["junction"], "not applicable (junctions exist only on Windows)")
            self.assertEqual(results["symlink"], "yes")
            self.assertEqual(results["hardlink"], "yes")

    def test_probe_survives_an_unusable_temporary_directory(self):
        with tempfile.TemporaryDirectory() as d:
            results = policy.probe_capabilities(base_dir=Path(d) / "does-not-exist")
        self.assertEqual(list(results), ["symlink", "hardlink", "junction"])
        self.assertTrue(all(value.startswith("not probed: ") for value in results.values()), results)

    def test_probe_cli_exits_zero_and_prints_the_answers(self):
        out = io.StringIO()
        with env_without_symlink_requirement(), contextlib.redirect_stdout(out):
            rc = policy.main(["--probe"])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        for label in ("capability probe", "platform:", "sys.platform:", "python:", "tempdir:", "symlink:",
                      "hardlink:", "junction:", "CI_REQUIRE_SYMLINKS: unset"):
            self.assertIn(label, text)


if __name__ == "__main__":
    unittest.main()
