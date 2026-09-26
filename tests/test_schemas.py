"""Regression tests for audit finding F6: schema and evidence-contract enforcement (scripts/schema_check.py).

Run: python -m unittest discover -s tests -p "test_schemas.py" -v

Positive: every shipped template that has a schema validates through the API and the CLI, --self-check passes,
every shipped schema stays inside the supported keyword subset, the tightened contract is present, and the
schema files are byte-stable (UTF-8, no BOM, LF, one trailing newline, json.dumps(indent=2) formatting).
Negative: structural violations (required, type, enum, additionalProperties, pattern, format, minItems, ...),
evidence-contract violations (duplicate ids, uncheckable requirement, passing without evidence, ...), and
validator robustness (unsupported keyword, remote or cyclic $ref, unreadable or non-strict JSON, usage errors).
Every fixture lives in memory or in a temporary directory; the repository is only ever read.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "schema_check.py"
SCHEMAS = ROOT / "schemas"
TEMPLATES = ROOT / "templates"
SHIPPED = ("regression-result", "traceability", "verification-plan", "waiver")
SHA256 = "0123456789abcdef" * 4
COMMIT = "c128ef37ab97eaacd84ecfcd74ac3230205d6906"


def _load_module():
    spec = importlib.util.spec_from_file_location("schema_check_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sc = _load_module()


def schema(name: str) -> dict:
    return sc.load_json(SCHEMAS / f"{name}.schema.json")


def template(name: str) -> dict:
    return sc.load_json(TEMPLATES / f"{name}.example.json")


def regression_result() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "nightly-2026-09-24",
        "tool": "verilator",
        "tool_version": "5.024",
        "git_commit": COMMIT,
        "config_sha256": SHA256,
        "command": ["make", "-C", "sim", "smoke"],
        "started_at": "2026-09-24T10:15:00Z",
        "ended_at": "2026-09-24T10:45:00+00:00",
        "report_path": ".soc-dv/runs/nightly-2026-09-24/report.txt",
        "tests": [
            {"name": "smoke_reset", "seed": 1, "status": "pass", "log": "logs/smoke_reset.1.log",
             "duration_seconds": 12.5},
            {"name": "smoke_reset", "seed": 2, "status": "fail", "signature": "SB mismatch @ 120ns",
             "first_error": "UVM_ERROR ... scoreboard mismatch", "log": "logs/smoke_reset.2.log"},
        ],
    }


def traceability() -> dict:
    return {
        "schema_version": "1.0",
        "records": [
            {"requirement_id": "REQ-RESET_001", "tests": ["smoke_reset"], "status": "passing",
             "evidence": ["RUN-nightly-2026-09-24"], "owner": "alice"},
            {"requirement_id": "REQ-RESET_002", "status": "failing", "evidence": [], "notes": "SB mismatch"},
            {"requirement_id": "REQ-RESET_003", "status": "open", "evidence": []},
        ],
    }


def waiver(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "id": "WVR-001",
        "category": "coverage",
        "target": "cov.fifo.overflow",
        "rationale": "Overflow is unreachable because the producer is throttled by the credit counter.",
        "evidence": ["formal/fifo_overflow.proof"],
        "owner": "alice",
        "approver": "bob",
        "expiry": "2026-12-31",
        "status": "approved",
    }
    base.update(overrides)
    return base


def plan() -> dict:
    return template("verification-plan")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def make_root(tmp: str, schemas: dict, templates: dict) -> Path:
    """A synthetic repository root holding schemas/<name>.schema.json and templates/<name>.example.json."""
    root = Path(tmp) / "repo"
    (root / "schemas").mkdir(parents=True)
    (root / "templates").mkdir()
    for name, obj in schemas.items():
        write_json(root / "schemas" / f"{name}.schema.json", obj)
    for name, obj in templates.items():
        write_json(root / "templates" / f"{name}.example.json", obj)
    return root


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT), env=env)


def run_main(argv: list, root=None) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sc.main(argv, root=root)
    return code, out.getvalue(), err.getvalue()


def keywords_of(node, found: set) -> set:
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key in ("properties", "$defs") and isinstance(value, dict):
                for sub in value.values():
                    keywords_of(sub, found)
            elif key == "items":
                keywords_of(value, found)
    return found


class Case(unittest.TestCase):
    def assert_finding(self, errors, path: str, rule: str) -> None:
        prefix = f"{path}: {rule}:"
        self.assertTrue(any(error.startswith(prefix) for error in errors), f"expected {prefix!r} in {errors}")

    def assert_no_finding(self, errors, path: str, rule: str) -> None:
        prefix = f"{path}: {rule}:"
        self.assertFalse(any(error.startswith(prefix) for error in errors), f"unexpected {prefix!r} in {errors}")

    def check(self, kind: str, instance) -> list:
        return sc.validate(instance, schema(kind)) + sc.check_semantics(kind, instance)


# --------------------------------------------------------------------------- shipped artifacts
class ShippedArtifactTests(Case):
    def test_templates_validate_via_api(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(sc.check_templates(ROOT), [])
        pairs = sc.template_pairs(ROOT)
        self.assertTrue(any(schema_path is not None for _, schema_path in pairs))
        for template_path, schema_path in pairs:
            rel = template_path.relative_to(ROOT).as_posix()
            self.assertEqual(schema_path is None, f"NOTICE[schema] {rel}:" in err.getvalue(), err.getvalue())

    def test_templates_validate_via_cli(self):
        result = run_cli("--templates")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Templates OK", result.stdout)
        self.assertNotIn("ERROR[", result.stderr)

    def test_template_with_kind_via_cli(self):
        result = run_cli("--schema", str(SCHEMAS / "verification-plan.schema.json"),
                         "--instance", str(TEMPLATES / "verification-plan.example.json"), "--kind", "verification-plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK:", result.stdout)

    def test_self_check(self):
        self.assertEqual(sc.self_check(ROOT), [])
        result = run_cli("--self-check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Schema self-check OK", result.stdout)

    def test_help_exits_zero(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Exit codes", result.stdout)

    def test_shipped_schemas_use_supported_subset(self):
        for name in SHIPPED:
            self.assertTrue((SCHEMAS / f"{name}.schema.json").is_file(), name)
        for path in sorted(SCHEMAS.glob("*.json")):
            with self.subTest(schema=path.name):
                loaded = sc.load_json(path)
                sc.check_schema(loaded)
                self.assertEqual(loaded["$schema"], sc.SCHEMA_2020_12)
                self.assertLessEqual(keywords_of(loaded, set()), sc.SUPPORTED_KEYWORDS)

    def test_tightened_contract_present(self):
        regression = schema("regression-result")
        for field in ("command", "report_path", "config_sha256"):
            self.assertIn(field, regression["required"])
            self.assertIn(field, regression["properties"])
        self.assertEqual(regression["properties"]["git_commit"]["pattern"], "^[0-9a-f]{7,40}$")
        self.assertEqual(regression["properties"]["config_sha256"]["pattern"], "^[0-9a-f]{64}$")
        self.assertEqual(regression["properties"]["ended_at"]["format"], "date-time")
        self.assertEqual(regression["properties"]["schema_version"]["const"], "1.0")
        trace = schema("traceability")
        self.assertIn("failing", trace["properties"]["records"]["items"]["properties"]["status"]["enum"])
        vplan = schema("verification-plan")
        self.assertEqual(vplan["properties"]["signoff_criteria"]["minItems"], 1)
        for field in ("checks", "coverage"):
            self.assertEqual(vplan["$defs"]["requirement"]["properties"][field]["items"]["minLength"], 1)

    def test_fixtures_are_valid(self):
        self.assertEqual(self.check("regression-result", regression_result()), [])
        self.assertEqual(self.check("traceability", traceability()), [])
        self.assertEqual(self.check("waiver", waiver()), [])
        self.assertEqual(self.check("waiver", waiver(status="proposed", approver="")), [])
        self.assertEqual(self.check("verification-plan", plan()), [])

    def test_schema_files_byte_stable(self):
        paths = [SCHEMAS / f"{name}.schema.json" for name in SHIPPED] + [TEMPLATES / "verification-plan.example.json"]
        for path in paths:
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                if os.name == "nt" and b"\r\n" in raw:
                    self.skipTest("checkout translated line endings (core.autocrlf); LF is enforced on POSIX")
                self.assertNotEqual(raw[:3], b"\xef\xbb\xbf", "UTF-8 BOM")
                text = raw.decode("utf-8")
                self.assertNotIn("\r", text, "CRLF line ending")
                self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"), "exactly one trailing newline")
                self.assertEqual(json.dumps(sc.loads_strict(text), indent=2) + "\n", text, "2-space json.dumps form")


# --------------------------------------------------------------------------- structural rejection
class StructuralRejectionTests(Case):
    def test_missing_required_field(self):
        instance = waiver()
        del instance["approver"]
        errors = sc.validate(instance, schema("waiver"))
        self.assert_finding(errors, "/", "required")
        self.assertTrue(any('"approver"' in error for error in errors), errors)
        instance = regression_result()
        for field in ("command", "report_path", "config_sha256"):
            del instance[field]
        errors = sc.validate(instance, schema("regression-result"))
        self.assertEqual(sum(1 for error in errors if error.startswith("/: required:")), 3, errors)

    def test_wrong_type(self):
        instance = plan()
        instance["requirements"] = "REQ-RESET_001"
        self.assert_finding(sc.validate(instance, schema("verification-plan")), "/requirements", "type")
        for bad_seed in (True, 1.0, None):
            instance = regression_result()
            instance["tests"][0]["seed"] = bad_seed
            with self.subTest(seed=bad_seed):
                self.assert_finding(sc.validate(instance, schema("regression-result")), "/tests/0/seed", "type")
        instance = regression_result()
        instance["tests"][0]["duration_seconds"] = "12"
        self.assert_finding(sc.validate(instance, schema("regression-result")), "/tests/0/duration_seconds", "type")
        instance["tests"][0]["duration_seconds"] = -1
        self.assert_finding(sc.validate(instance, schema("regression-result")), "/tests/0/duration_seconds", "minimum")

    def test_bad_enum_and_const(self):
        instance = plan()
        instance["requirements"][0]["priority"] = "P9"
        self.assert_finding(sc.validate(instance, schema("verification-plan")), "/requirements/0/priority", "enum")
        instance = traceability()
        instance["records"][0]["status"] = "done"
        self.assert_finding(sc.validate(instance, schema("traceability")), "/records/0/status", "enum")
        instance = regression_result()
        instance["tests"][0]["status"] = "passed"
        instance["schema_version"] = "2.0"
        errors = sc.validate(instance, schema("regression-result"))
        self.assert_finding(errors, "/tests/0/status", "enum")
        self.assert_finding(errors, "/schema_version", "const")

    def test_extra_field_top_level_and_nested(self):
        instance = waiver(reviewer="carol")
        self.assert_finding(sc.validate(instance, schema("waiver")), "/reviewer", "additionalProperties")
        instance = plan()
        instance["requirements"][0]["notes"] = "not in the contract"
        errors = sc.validate(instance, schema("verification-plan"))
        self.assert_finding(errors, "/requirements/0/notes", "additionalProperties")
        instance = regression_result()
        instance["tests"][1]["retries"] = 2
        errors = sc.validate(instance, schema("regression-result"))
        self.assert_finding(errors, "/tests/1/retries", "additionalProperties")

    def test_bad_pattern(self):
        instance = plan()
        instance["requirements"][0]["id"] = "req-1"
        instance["risks"][0]["id"] = "RISK_1"
        errors = sc.validate(instance, schema("verification-plan"))
        self.assert_finding(errors, "/requirements/0/id", "pattern")
        self.assert_finding(errors, "/risks/0/id", "pattern")
        for bad_sha in (SHA256.upper(), SHA256[:63], SHA256 + "0", "", "not-a-hash"):
            instance = regression_result()
            instance["config_sha256"] = bad_sha
            with self.subTest(config_sha256=bad_sha):
                self.assert_finding(sc.validate(instance, schema("regression-result")), "/config_sha256", "pattern")
        for bad_commit in ("HEAD", "abc123", COMMIT + "0", COMMIT.upper()):
            instance = regression_result()
            instance["git_commit"] = bad_commit
            with self.subTest(git_commit=bad_commit):
                self.assert_finding(sc.validate(instance, schema("regression-result")), "/git_commit", "pattern")

    def test_bad_date_and_datetime(self):
        for bad in ("2026-02-30", "24/12/2026", "2026-12-31T00:00:00Z", "2026-12-3", "2026-12-31\n", ""):
            with self.subTest(expiry=bad):
                self.assert_finding(sc.validate(waiver(expiry=bad), schema("waiver")), "/expiry", "format")
        for bad in ("2026-09-24 10:15:00Z", "2026-09-24T10:15:00", "2026-09-24T24:00:00Z", "2026-09-24T23:59:60Z",
                    "2026-09-24T10:15:00+24:00", "2026-09-24T10:15:00+05:60", "2026-02-30T10:15:00Z", "yesterday",
                    "2026-09-24T10:15:00Z\n"):
            instance = regression_result()
            instance["started_at"] = bad
            instance["ended_at"] = bad
            with self.subTest(timestamp=bad):
                errors = sc.validate(instance, schema("regression-result"))
                self.assert_finding(errors, "/started_at", "format")
                self.assert_finding(errors, "/ended_at", "format")

    def test_accepts_rfc3339_variants(self):
        for good in ("2026-09-24T10:15:00Z", "2026-09-24t10:15:00z", "2026-09-24T10:15:00+05:30",
                     "2026-09-24T10:15:00-08:00", "2026-09-24T10:15:00.5Z", "2026-09-24T10:15:00.1234567Z"):
            instance = regression_result()
            instance["started_at"] = good
            del instance["ended_at"]
            with self.subTest(timestamp=good):
                self.assertEqual(sc.validate(instance, schema("regression-result")), [])

    def test_empty_collections_and_blank_strings(self):
        instance = regression_result()
        instance["command"] = []
        instance["report_path"] = ""
        errors = sc.validate(instance, schema("regression-result"))
        self.assert_finding(errors, "/command", "minItems")
        self.assert_finding(errors, "/report_path", "minLength")
        instance["command"] = ["make", ""]
        self.assert_finding(sc.validate(instance, schema("regression-result")), "/command/1", "minLength")
        instance = plan()
        instance["signoff_criteria"] = []
        instance["requirements"][0]["checks"] = [""]
        instance["requirements"][0]["methods"] = []
        errors = sc.validate(instance, schema("verification-plan"))
        self.assert_finding(errors, "/signoff_criteria", "minItems")
        self.assert_finding(errors, "/requirements/0/checks/0", "minLength")
        self.assert_finding(errors, "/requirements/0/methods", "minItems")
        self.assert_finding(sc.validate(waiver(evidence=[]), schema("waiver")), "/evidence", "minItems")
        self.assert_finding(sc.validate(waiver(rationale="short"), schema("waiver")), "/rationale", "minLength")

    def test_all_errors_are_reported(self):
        instance = waiver(rationale="short", evidence=[], expiry="2026-02-30", extra=True)
        errors = sc.validate(instance, schema("waiver"))
        self.assertEqual(len(errors), 4, errors)
        for path, rule in (("/rationale", "minLength"), ("/evidence", "minItems"), ("/expiry", "format"),
                           ("/extra", "additionalProperties")):
            self.assert_finding(errors, path, rule)

    def test_json_equality_semantics(self):
        self.assertEqual(sc.validate(1.0, {"enum": [1, "a"]}), [])
        self.assert_finding(sc.validate(True, {"enum": [1, "a"]}), "/", "enum")
        self.assertEqual(sc.validate({"b": 2, "a": 1}, {"const": {"a": 1, "b": 2}}), [])
        unique = {"type": "array", "uniqueItems": True}
        self.assert_finding(sc.validate([1, 1.0], unique), "/", "uniqueItems")
        self.assert_finding(sc.validate([{"a": 1}, {"a": 1}], unique), "/", "uniqueItems")
        self.assertEqual(sc.validate([1, True, "1"], unique), [])
        self.assertEqual(sc.validate("x", {"type": ["integer", "string"]}), [])
        self.assert_finding(sc.validate(2.5, {"type": "integer"}), "/", "type")
        self.assertEqual(sc.validate(2.5, {"type": "number", "maximum": 2.5}), [])
        self.assert_finding(sc.validate(3, {"type": "number", "maximum": 2.5}), "/", "maximum")
        self.assert_finding(sc.validate("abcd", {"maxLength": 3}), "/", "maxLength")
        self.assert_finding(sc.validate([1, 2], {"maxItems": 1}), "/", "maxItems")


# --------------------------------------------------------------------------- evidence-contract rules
class ContractRuleTests(Case):
    def test_duplicate_requirement_and_risk_ids_in_plan(self):
        instance = plan()
        instance["requirements"].append(dict(instance["requirements"][0]))
        instance["risks"].append(dict(instance["risks"][0]))
        errors = sc.check_semantics("verification-plan", instance)
        self.assert_finding(errors, "/requirements/1/id", "unique-id")
        self.assert_finding(errors, "/risks/1/id", "unique-id")
        self.assertEqual(sc.validate(instance, schema("verification-plan")), [], "schema alone cannot see duplicates")

    def test_requirement_without_checks_or_coverage(self):
        instance = plan()
        instance["requirements"][0]["checks"] = []
        instance["requirements"][0]["coverage"] = []
        self.assert_finding(sc.check_semantics("verification-plan", instance), "/requirements/0", "checkable")
        instance["requirements"][0]["coverage"] = ["   "]
        self.assert_finding(sc.check_semantics("verification-plan", instance), "/requirements/0", "checkable")
        instance["requirements"][0]["coverage"] = ["Reset asserted in each state"]
        self.assert_no_finding(sc.check_semantics("verification-plan", instance), "/requirements/0", "checkable")

    def test_signoff_criteria_required(self):
        instance = plan()
        instance["signoff_criteria"] = []
        self.assert_finding(sc.check_semantics("verification-plan", instance), "/signoff_criteria", "non-empty")
        instance["signoff_criteria"] = [" "]
        self.assert_finding(sc.check_semantics("verification-plan", instance), "/signoff_criteria", "non-empty")

    def test_duplicate_traceability_requirement_id(self):
        instance = traceability()
        instance["records"][2]["requirement_id"] = "REQ-RESET_001"
        errors = sc.check_semantics("traceability", instance)
        self.assert_finding(errors, "/records/2/requirement_id", "unique-id")
        self.assertIn("/records/0/requirement_id", errors[0])

    def test_passing_or_waived_requires_evidence(self):
        instance = traceability()
        instance["records"][0]["evidence"] = []
        self.assert_finding(sc.check_semantics("traceability", instance), "/records/0/evidence", "evidence-required")
        instance["records"][0]["status"] = "waived"
        instance["records"][0]["evidence"] = [""]
        self.assert_finding(sc.check_semantics("traceability", instance), "/records/0/evidence", "evidence-required")
        for status in ("open", "implemented", "failing", "blocked"):
            instance["records"][0]["status"] = status
            with self.subTest(status=status):
                self.assert_no_finding(sc.check_semantics("traceability", instance), "/records/0/evidence",
                                       "evidence-required")

    def test_failing_status_accepted_by_schema(self):
        instance = traceability()
        self.assertEqual(instance["records"][1]["status"], "failing")
        self.assertEqual(sc.validate(instance, schema("traceability")), [])

    def test_regression_run_id_and_duplicate_tests(self):
        instance = regression_result()
        instance["run_id"] = "   "
        self.assert_finding(sc.check_semantics("regression-result", instance), "/run_id", "non-empty")
        instance = regression_result()
        instance["tests"][1]["seed"] = 1
        self.assert_finding(sc.check_semantics("regression-result", instance), "/tests/1/name", "unique-id")
        instance["tests"][1]["seed"] = "1"
        self.assertEqual(sc.check_semantics("regression-result", instance), [], "integer and string seeds differ")
        instance["tests"][1]["seed"] = 2
        self.assertEqual(sc.check_semantics("regression-result", instance), [], "same test, different seeds")

    def test_regression_time_order(self):
        instance = regression_result()
        instance["ended_at"] = "2026-09-24T10:14:59Z"
        self.assert_finding(sc.check_semantics("regression-result", instance), "/ended_at", "time-order")
        instance["ended_at"] = "2026-09-24T12:15:00+02:00"
        self.assertEqual(sc.check_semantics("regression-result", instance), [], "same instant in another offset")
        del instance["ended_at"]
        self.assertEqual(sc.check_semantics("regression-result", instance), [])

    def test_waiver_expiry_and_approver_rules(self):
        self.assert_finding(sc.check_semantics("waiver", waiver(expiry="2026-02-30")), "/expiry", "valid-date")
        self.assert_finding(sc.check_semantics("waiver", waiver(expiry="soon")), "/expiry", "valid-date")
        self.assert_finding(sc.check_semantics("waiver", waiver(approver="")), "/approver", "approver-required")
        self.assert_finding(sc.check_semantics("waiver", waiver(approver="  ")), "/approver", "approver-required")
        for same in ("alice", "Alice", " ALICE "):
            with self.subTest(approver=same):
                self.assert_finding(sc.check_semantics("waiver", waiver(approver=same)), "/approver",
                                    "approver-distinct")
        self.assertEqual(sc.check_semantics("waiver", waiver(status="proposed", approver="")), [])
        self.assertEqual(sc.check_semantics("waiver", waiver(status="rejected", approver="alice")), [])

    def test_unknown_kind_and_non_object(self):
        with self.assertRaises(ValueError):
            sc.check_semantics("bogus", {})
        errors = sc.check_semantics("waiver", [])
        self.assertEqual(len(errors), 1)
        self.assert_finding(errors, "/", "object")

    def test_rules_tolerate_malformed_shapes(self):
        malformed = {"requirements": "x", "risks": [1, None, {"id": 3}], "signoff_criteria": None}
        errors = sc.check_semantics("verification-plan", malformed)
        self.assert_finding(errors, "/signoff_criteria", "non-empty")
        self.assertEqual(sc.check_semantics("traceability", {"records": {"a": 1}}), [])
        self.assertEqual(sc.check_semantics("regression-result", {"run_id": "r", "tests": [{"name": "t"}]}), [])
        self.assert_finding(sc.check_semantics("waiver", {"status": "approved"}), "/approver", "approver-required")


# --------------------------------------------------------------------------- validator robustness
class ValidatorRobustnessTests(Case):
    def test_unsupported_keywords_fail_closed(self):
        cases = {
            "anyOf": {"type": "object", "anyOf": [{"required": ["a"]}]},
            "patternProperties": {"type": "object", "patternProperties": {"^x": {}}},
            "$comment": {"type": "object", "$comment": "note"},
            "default": {"type": "string", "default": "x"},
            "if": {"if": {"type": "string"}},
            "unused $defs entry": {"type": "object", "$defs": {"unused": {"oneOf": []}}},
            "nested in properties": {"type": "object", "properties": {"a": {"examples": [1]}}},
            "nested in items": {"type": "array", "items": {"not": {}}},
            "unsupported format": {"type": "string", "format": "email"},
            "boolean subschema": {"type": "object", "properties": {"a": True}},
            "schema-valued additionalProperties": {"type": "object", "additionalProperties": {"type": "string"}},
            "tuple items": {"type": "array", "items": [{"type": "string"}]},
            "other draft": {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
            "boolean root": True,
            "bad type name": {"type": "str"},
            "bad pattern": {"type": "string", "pattern": "("},
            "negative minItems": {"type": "array", "minItems": -1},
            "boolean minLength": {"type": "string", "minLength": True},
            "empty enum": {"enum": []},
            "duplicate required": {"required": ["a", "a"]},
        }
        for label, bad_schema in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(sc.SchemaError):
                    sc.validate({}, bad_schema)

    def test_remote_or_unresolvable_ref_rejected(self):
        for ref in ("https://example.com/x.json#/a", "other.json#/x", "#foo", "/local", "", 5):
            with self.subTest(ref=ref):
                with self.assertRaises(sc.SchemaError):
                    sc.validate({}, {"$ref": ref})
        with self.assertRaises(sc.SchemaError):
            sc.validate({}, {"$ref": "#/$defs/missing", "$defs": {}})

    def test_ref_cycles_rejected_and_reuse_accepted(self):
        direct = {"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"}
        root_recursion = {"type": "array", "items": {"$ref": "#"}}
        structural = {"$ref": "#/$defs/node", "$defs": {"node": {"type": "object", "properties": {
            "children": {"type": "array", "items": {"$ref": "#/$defs/node"}}}}}}
        for label, bad_schema in (("direct", direct), ("root", root_recursion), ("structural", structural)):
            with self.subTest(case=label):
                with self.assertRaises(sc.SchemaError):
                    sc.validate([], bad_schema)
        reuse = {"type": "object", "properties": {"x": {"$ref": "#/$defs/id"}, "y": {"$ref": "#/$defs/id"}},
                 "$defs": {"id": {"type": "string", "pattern": "^ID-[0-9]+$"}}}
        self.assertEqual(sc.validate({"x": "ID-1", "y": "ID-2"}, reuse), [])
        self.assert_finding(sc.validate({"x": "ID-1", "y": "bad"}, reuse), "/y", "pattern")

    def test_unreadable_or_non_strict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "instance.json"
            for label, raw in (("truncated", b'{"a": '), ("duplicate keys", b'{"a": 1, "a": 2}'),
                               ("NaN", b'{"a": NaN}'), ("Infinity", b'[Infinity]'), ("BOM", b'\xef\xbb\xbf{}'),
                               ("not UTF-8", b'{"a": "\xff"}')):
                path.write_bytes(raw)
                with self.subTest(case=label):
                    with self.assertRaises(sc.LoadError):
                        sc.load_json(path)
            with self.assertRaises(sc.LoadError):
                sc.load_json(Path(tmp) / "missing.json")
            path.write_bytes(b'{"a": [1, 2.5, "x", null, true]}\n')
            self.assertEqual(sc.load_json(path), {"a": [1, 2.5, "x", None, True]})
            missing = str(Path(tmp) / "missing.json")
            result = run_cli("--schema", str(SCHEMAS / "waiver.schema.json"), "--instance", missing)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("ERROR[unreadable]", result.stderr)
            path.write_bytes(b'{"a": ')
            result = run_cli("--schema", str(SCHEMAS / "waiver.schema.json"), "--instance", str(path))
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("not strict JSON", result.stderr)

    def test_unsupported_schema_exits_three_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = Path(tmp) / "instance.json"
            write_json(instance, {})
            for label, bad_schema in (("keyword", {"type": "object", "anyOf": []}),
                                      ("remote ref", {"$ref": "https://example.com/s.json#/a"}),
                                      ("cycle", {"$defs": {"a": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"})):
                bad = Path(tmp) / f"{label.replace(' ', '-')}.schema.json"
                write_json(bad, bad_schema)
                with self.subTest(case=label):
                    result = run_cli("--schema", str(bad), "--instance", str(instance))
                    self.assertEqual(result.returncode, 3, result.stderr)
                    self.assertTrue(result.stderr.startswith("ERROR[unsupported]"), result.stderr)

    def test_usage_errors_exit_two(self):
        self.assertEqual(run_cli().returncode, 2)
        self.assertEqual(run_cli("--schema", str(SCHEMAS / "waiver.schema.json")).returncode, 2)
        self.assertEqual(run_cli("--instance", str(TEMPLATES / "verification-plan.example.json")).returncode, 2)
        self.assertEqual(run_cli("--templates", "--kind", "waiver").returncode, 2)
        self.assertEqual(run_cli("--templates", "--self-check").returncode, 2)
        self.assertEqual(run_cli("--schema", str(SCHEMAS / "waiver.schema.json"), "--instance",
                                 str(TEMPLATES / "verification-plan.example.json"), "--kind", "bogus").returncode, 2)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                sc.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_instance_cli_reports_pointer_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad-waiver.json"
            write_json(bad, waiver(expiry="2026-02-30", approver="alice", extra=True, evidence=[]))
            result = run_cli("--schema", str(SCHEMAS / "waiver.schema.json"), "--instance", str(bad))
            self.assertEqual(result.returncode, 1, result.stderr)
            lines = result.stderr.splitlines()
            self.assertEqual(len(lines), 3, result.stderr)
            self.assertTrue(all(line.startswith("ERROR[schema] /") for line in lines), result.stderr)
            self.assertIn("ERROR[schema] /expiry: format:", result.stderr)
            self.assertIn("ERROR[schema] /extra: additionalProperties:", result.stderr)
            self.assertIn("ERROR[schema] /evidence: minItems:", result.stderr)
            result = run_cli("--schema", str(SCHEMAS / "waiver.schema.json"), "--instance", str(bad),
                             "--kind", "waiver")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("ERROR[schema] /approver: approver-distinct:", result.stderr)
            self.assertIn("ERROR[schema] /expiry: valid-date:", result.stderr)
            good = Path(tmp) / "good-waiver.json"
            write_json(good, waiver())
            result = run_cli("--schema", str(SCHEMAS / "waiver.schema.json"), "--instance", str(good),
                             "--kind", "waiver")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("OK:", result.stdout)

    def test_templates_mode_on_synthetic_roots(self):
        waiver_schema = schema("waiver")
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"waiver": waiver_schema}, {"waiver": waiver(), "project-config": {"x": 1}})
            code, out, err = run_main(["--templates"], root=root)
            self.assertEqual(code, 0, err)
            self.assertIn("Templates OK: 1 validated", out)
            self.assertIn("NOTICE[schema] templates/project-config.example.json: no schema", err)
            self.assertNotIn("ERROR[", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"waiver": waiver_schema}, {"waiver": waiver(expiry="never", approver="alice")})
            code, out, err = run_main(["--templates"], root=root)
            self.assertEqual(code, 1, err)
            self.assertIn("ERROR[schema] templates/waiver.example.json#/expiry: format:", err)
            self.assertIn("ERROR[schema] templates/waiver.example.json#/approver: approver-distinct:", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {}, {"project-config": {"x": 1}})
            code, out, err = run_main(["--templates"], root=root)
            self.assertEqual(code, 3, err)
            self.assertIn("NOTICE[schema]", err)
            self.assertIn("ERROR[unreadable]", err)
            self.assertIn("nothing was validated", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"waiver": waiver_schema}, {})
            code, out, err = run_main(["--templates"], root=root)
            self.assertEqual(code, 3, err)
            self.assertIn("nothing to validate", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"waiver": {"type": "object", "allOf": []}}, {"waiver": waiver()})
            code, out, err = run_main(["--templates"], root=root)
            self.assertEqual(code, 3, err)
            self.assertIn("ERROR[unsupported]", err)
            self.assertIn("allOf", err)

    def test_self_check_mode_on_synthetic_roots(self):
        good = schema("waiver")
        cases = {
            "missing $schema": {key: value for key, value in good.items() if key != "$schema"},
            "open object": {key: value for key, value in good.items() if key != "additionalProperties"},
            "no required": dict(good, required=[]),
            "array root": dict(good, type="array"),
            "unsupported keyword": dict(good, anyOf=[]),
        }
        for label, bad_schema in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                root = make_root(tmp, {"waiver": bad_schema}, {})
                with self.subTest(case=label):
                    code, out, err = run_main(["--self-check"], root=root)
                    self.assertEqual(code, 3, err)
                    self.assertIn("ERROR[unsupported] schemas/waiver.schema.json:", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {}, {})
            code, out, err = run_main(["--self-check"], root=root)
            self.assertEqual(code, 3, err)
            self.assertIn("no schemas found", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"waiver": good}, {})
            (root / "schemas" / "broken.json").write_text("{", encoding="utf-8")
            code, out, err = run_main(["--self-check"], root=root)
            self.assertEqual(code, 3, err)
            self.assertIn("ERROR[unsupported] schemas/broken.json: not strict JSON", err)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"waiver": good}, {})
            code, out, err = run_main(["--self-check"], root=root)
            self.assertEqual(code, 0, err)
            self.assertIn("Schema self-check OK: 1 schemas", out)


if __name__ == "__main__":
    unittest.main()
