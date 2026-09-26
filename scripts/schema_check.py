#!/usr/bin/env python3
"""Validate DV evidence artifacts against the shipped JSON Schemas, standard library only (audit finding F6).

Usage:
    python scripts/schema_check.py --templates
        validate every templates/<name>.example.json against schemas/<name>.schema.json and apply the
        evidence-contract rules registered for <name>; a template without a schema is a NOTICE, not an error
    python scripts/schema_check.py --self-check
        verify that every schemas/*.json is loadable, declares JSON Schema 2020-12, is an object schema with
        additionalProperties false and a non-empty required list, and uses only the supported keywords
    python scripts/schema_check.py --schema <path> --instance <path> [--kind <name>]
        validate one instance; --kind adds the evidence-contract rules for that artifact kind
        (verification-plan, traceability, regression-result, waiver)

Exit codes (stable):
    0  valid
    1  instance invalid; every finding is listed, one per line, as ``ERROR[schema] <path>: <rule>: <detail>``,
       where <path> is the JSON-pointer-like instance location (``/`` for the root; prefixed by
       ``<template>#`` in --templates mode) and <rule> is the schema keyword or evidence-contract rule that failed
    2  command-line usage error
    3  schema unsupported or invalid (``ERROR[unsupported] ...``), or a schema/instance file unreadable or not
       strict JSON (``ERROR[unreadable] ...``); nothing was accepted

Supported subset of JSON Schema 2020-12; anything else fails closed with exit 3 so no keyword is silently
ignored: ``$schema`` (must be the 2020-12 URI when present), ``$id``, ``title``, ``description`` as annotations;
``$defs``; ``$ref`` to a local JSON pointer (``#`` or ``#/...``) only, never to an ancestor (no cycles, no
recursion); ``type`` (one name or a list of names); ``enum``; ``const``; ``required``; ``properties``;
``additionalProperties`` (true/false only); ``items`` (a single schema); ``minItems``; ``maxItems``;
``uniqueItems``; ``minLength``; ``maxLength``; ``minimum``; ``maximum``; ``pattern``; ``format`` for exactly
``date`` and ``date-time``.

Deliberate deviations from the specification, chosen so that every accepted artifact is checkable:
    * ``format`` is an assertion here, not an annotation. ``date`` must be ``YYYY-MM-DD`` and a real calendar
      date. ``date-time`` must be RFC 3339: date, ``T``, ``HH:MM:SS``, an optional fraction, then ``Z`` or a
      ``+HH:MM``/``-HH:MM`` offset (lowercase ``t``/``z`` accepted; a leap second ``:60`` is rejected).
    * ``integer`` accepts only JSON integers: booleans and integral floats such as ``1.0`` are rejected.
    * ``pattern`` uses Python ``re.search``. The shipped patterns stay inside the ECMA-262 subset that Python
      shares; note that Python's ``$`` also matches before a final newline.
    * Schemas and instances must be strict JSON: duplicate object keys and ``NaN``/``Infinity`` are rejected.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

_HERE = Path(__file__).resolve().parent

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_UNSUPPORTED = 3

SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_SUFFIX = ".schema.json"
TEMPLATE_SUFFIX = ".example.json"

ANNOTATION_KEYWORDS = frozenset({"$schema", "$id", "title", "description"})
SUPPORTED_KEYWORDS = ANNOTATION_KEYWORDS | frozenset({
    "$defs", "$ref", "type", "enum", "const", "required", "properties", "additionalProperties", "items",
    "minItems", "maxItems", "uniqueItems", "minLength", "maxLength", "minimum", "maximum", "pattern", "format",
})
SUPPORTED_FORMATS = ("date", "date-time")
TYPE_NAMES = ("array", "boolean", "integer", "null", "number", "object", "string")

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATETIME_RE = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})[Tt]([0-9]{2}:[0-9]{2}:[0-9]{2})(\.[0-9]+)?([Zz]|[+-][0-9]{2}:[0-9]{2})")
_FORMAT_HINT = {"date": "YYYY-MM-DD", "date-time": "RFC 3339, e.g. 2026-09-24T10:15:00Z"}


class SchemaCheckError(Exception):
    """Base class; ``exit_code`` and ``label`` are the documented process exit status and ERROR label."""

    exit_code = EXIT_UNSUPPORTED
    label = "unsupported"


class SchemaError(SchemaCheckError):
    """The schema is outside the supported subset or is not a valid schema."""

    label = "unsupported"


class LoadError(SchemaCheckError):
    """A schema or instance file cannot be read or is not strict JSON."""

    label = "unreadable"

    def __init__(self, path: Path | str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = Path(path)
        self.reason = reason


# --------------------------------------------------------------------------- strict JSON loading
def _reject_constant(name: str):
    raise ValueError(f"non-finite number literal {name} is not valid JSON")


def _pairs_to_dict(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate object key {json.dumps(key)}")
        out[key] = value
    return out


def loads_strict(text: str):
    """``json.loads`` that rejects duplicate object keys and NaN/Infinity literals (fail closed)."""
    return json.loads(text, object_pairs_hook=_pairs_to_dict, parse_constant=_reject_constant)


def load_json(path: Path | str):
    """Load a UTF-8 (no BOM) strict-JSON file; raises LoadError for anything unreadable."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LoadError(path, str(exc)) from exc
    try:
        return loads_strict(text)
    except ValueError as exc:
        raise LoadError(path, f"not strict JSON: {exc}") from exc


# --------------------------------------------------------------------------- formats
def parse_date(text) -> datetime.date | None:
    """Strict ``YYYY-MM-DD`` calendar date, or None."""
    if not isinstance(text, str) or not _DATE_RE.fullmatch(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def parse_datetime(text) -> datetime.datetime | None:
    """Strict RFC 3339 date-time with a mandatory offset, or None. Fractions beyond microseconds are truncated."""
    if not isinstance(text, str):
        return None
    match = _DATETIME_RE.fullmatch(text)
    if not match:
        return None
    day, clock, fraction, offset = match.groups()
    if offset in ("Z", "z"):
        offset = "+00:00"
    elif int(offset[1:3]) > 23 or int(offset[4:6]) > 59:
        return None
    micro = ("." + (fraction[1:] + "000000")[:6]) if fraction else ""
    try:
        return datetime.datetime.fromisoformat(f"{day}T{clock}{micro}{offset}")
    except ValueError:
        return None


def _format_ok(name: str, text: str) -> bool:
    parser = parse_date if name == "date" else parse_datetime
    return parser(text) is not None


# --------------------------------------------------------------------------- value helpers
def _j(value, limit: int = 120) -> str:
    """Compact ASCII JSON rendering for messages (safe on any console), truncated for very large values."""
    text = json.dumps(value, ensure_ascii=True, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _pointer(parts) -> str:
    if not parts:
        return "/"
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _is_type(value, name: str) -> bool:
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return _type_name(value) == name


def _canonical(value):
    """Hashable form implementing JSON equality: booleans are not numbers, 1 == 1.0, object key order ignored."""
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if value is None:
        return ("null",)
    if isinstance(value, list):
        return ("array", tuple(_canonical(item) for item in value))
    if isinstance(value, dict):
        return ("object", tuple(sorted((key, _canonical(item)) for key, item in value.items())))
    return ("other", repr(value))


def _json_equal(left, right) -> bool:
    return _canonical(left) == _canonical(right)


# --------------------------------------------------------------------------- static schema check
def _expect(condition: bool, where: str, message: str) -> None:
    if not condition:
        raise SchemaError(f"{where}: {message}")


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _resolve_ref(root, ref, where: str):
    """Resolve a local JSON-pointer ``$ref``; returns ``(target, normalised pointer)`` or raises SchemaError."""
    if not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/")):
        raise SchemaError(f"{where}: $ref {_j(ref)} is not a local JSON pointer (only '#' and '#/...' are supported)")
    pointer = unquote(ref[1:])
    node = root
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            raise SchemaError(f"{where}: $ref {_j(ref)} does not resolve")
    return node, "#" + pointer


def check_schema(schema) -> None:
    """Raise SchemaError unless ``schema`` lies entirely inside the supported subset (see the module docstring).

    Every subschema, including unused ``$defs`` entries, is checked; every ``$ref`` must resolve locally and must
    not point at a schema currently being entered (a direct ``$ref`` cycle or a recursive structure).
    """
    _check_node(schema, schema, "#", ("#",))


def _check_node(node, root, where: str, active: tuple) -> None:
    _expect(isinstance(node, dict), where, "a schema must be a JSON object; boolean schemas are not supported")
    for keyword in node:
        _expect(keyword in SUPPORTED_KEYWORDS, where, f"unsupported keyword {_j(keyword)}")
    if "$schema" in node:
        _expect(node["$schema"] == SCHEMA_2020_12, where, f"$schema must be {SCHEMA_2020_12}")
    for keyword in ("$id", "title", "description"):
        if keyword in node:
            _expect(isinstance(node[keyword], str), where, f"{keyword} must be a string")
    if "type" in node:
        names = node["type"] if isinstance(node["type"], list) else [node["type"]]
        _expect(bool(names) and all(name in TYPE_NAMES for name in names) and len(set(names)) == len(names), where,
                f"type must be a type name or a list of distinct type names, got {_j(node['type'])}")
    if "enum" in node:
        _expect(isinstance(node["enum"], list) and bool(node["enum"]), where, "enum must be a non-empty array")
    if "required" in node:
        names = node["required"]
        _expect(isinstance(names, list) and all(isinstance(n, str) for n in names) and len(set(names)) == len(names),
                where, "required must be an array of distinct strings")
    if "properties" in node:
        _expect(isinstance(node["properties"], dict), where, "properties must be an object")
        for name, sub in node["properties"].items():
            _check_node(sub, root, f"{where}/properties/{name}", active)
    if "additionalProperties" in node:
        _expect(isinstance(node["additionalProperties"], bool), where,
                "additionalProperties must be true or false (a schema-valued additionalProperties is not supported)")
    if "items" in node:
        _expect(isinstance(node["items"], dict), where, "items must be a single schema object")
        _check_node(node["items"], root, f"{where}/items", active)
    for keyword in ("minItems", "maxItems", "minLength", "maxLength"):
        if keyword in node:
            _expect(_is_count(node[keyword]), where, f"{keyword} must be a non-negative integer")
    if "uniqueItems" in node:
        _expect(isinstance(node["uniqueItems"], bool), where, "uniqueItems must be true or false")
    for keyword in ("minimum", "maximum"):
        if keyword in node:
            _expect(_is_type(node[keyword], "number"), where, f"{keyword} must be a number")
    if "pattern" in node:
        _expect(isinstance(node["pattern"], str), where, "pattern must be a string")
        try:
            re.compile(node["pattern"])
        except re.error as exc:
            raise SchemaError(f"{where}: pattern {_j(node['pattern'])} does not compile: {exc}") from exc
    if "format" in node:
        _expect(node["format"] in SUPPORTED_FORMATS, where,
                f"format {_j(node['format'])} is not supported (supported: {', '.join(SUPPORTED_FORMATS)})")
    if "$defs" in node:
        _expect(isinstance(node["$defs"], dict), where, "$defs must be an object")
        for name, sub in node["$defs"].items():
            _check_node(sub, root, f"{where}/$defs/{name}", active)
    if "$ref" in node:
        target, pointer = _resolve_ref(root, node["$ref"], where)
        _expect(pointer not in active, where,
                f"$ref {_j(node['$ref'])} forms a cycle: {' -> '.join(active + (pointer,))}")
        _check_node(target, root, pointer, active + (pointer,))


# --------------------------------------------------------------------------- instance validation
def validate(instance, schema) -> list[str]:
    """Every violation of ``schema`` by ``instance`` as ``<path>: <keyword>: <detail>``; empty means valid.

    The schema is checked first (``check_schema``), so an unsupported or invalid schema raises SchemaError
    instead of validating anything.
    """
    check_schema(schema)
    errors: list[str] = []
    _validate(instance, schema, schema, (), ("#",), errors)
    return errors


def _validate(value, node: dict, root: dict, parts: tuple, active: tuple, errors: list[str]) -> None:
    path = _pointer(parts)

    def fail(keyword: str, detail: str, at: str = path) -> None:
        errors.append(f"{at}: {keyword}: {detail}")

    if "$ref" in node:
        target, pointer = _resolve_ref(root, node["$ref"], path)
        if pointer in active:
            raise SchemaError(f"{path}: $ref {_j(node['$ref'])} forms a cycle")
        _validate(value, target, root, parts, active + (pointer,), errors)
    if "type" in node:
        names = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(_is_type(value, name) for name in names):
            fail("type", f"expected {' or '.join(names)}, got {_type_name(value)}")
    if "enum" in node and not any(_json_equal(value, option) for option in node["enum"]):
        fail("enum", f"{_j(value)} is not one of {_j(node['enum'])}")
    if "const" in node and not _json_equal(value, node["const"]):
        fail("const", f"{_j(value)} is not the required constant {_j(node['const'])}")
    if isinstance(value, dict):
        for name in node.get("required", ()):
            if name not in value:
                fail("required", f"missing property {_j(name)}")
        properties = node.get("properties", {})
        for name, item in value.items():
            if name in properties:
                _validate(item, properties[name], root, parts + (name,), active, errors)
            elif node.get("additionalProperties", True) is False:
                fail("additionalProperties", f"property {_j(name)} is not allowed", _pointer(parts + (name,)))
    elif isinstance(value, list):
        if "items" in node:
            for index, item in enumerate(value):
                _validate(item, node["items"], root, parts + (index,), active, errors)
        if "minItems" in node and len(value) < node["minItems"]:
            fail("minItems", f"{len(value)} items, at least {node['minItems']} required")
        if "maxItems" in node and len(value) > node["maxItems"]:
            fail("maxItems", f"{len(value)} items, at most {node['maxItems']} allowed")
        if node.get("uniqueItems"):
            seen: dict = {}
            for index, item in enumerate(value):
                key = _canonical(item)
                if key in seen:
                    fail("uniqueItems", f"items {seen[key]} and {index} are equal")
                else:
                    seen[key] = index
    elif isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            fail("minLength", f"length {len(value)}, at least {node['minLength']} required")
        if "maxLength" in node and len(value) > node["maxLength"]:
            fail("maxLength", f"length {len(value)}, at most {node['maxLength']} allowed")
        if "pattern" in node and not re.search(node["pattern"], value):
            fail("pattern", f"{_j(value)} does not match {_j(node['pattern'])}")
        if "format" in node and not _format_ok(node["format"], value):
            fail("format", f"{_j(value)} is not a valid {node['format']} ({_FORMAT_HINT[node['format']]})")
    elif _is_type(value, "number"):
        if "minimum" in node and value < node["minimum"]:
            fail("minimum", f"{_j(value)} is less than {_j(node['minimum'])}")
        if "maximum" in node and value > node["maximum"]:
            fail("maximum", f"{_j(value)} is greater than {_j(node['maximum'])}")


# --------------------------------------------------------------------------- evidence-contract rules
def _blank(text) -> bool:
    return not (isinstance(text, str) and text.strip())


def _entries(value) -> int:
    """Number of non-blank strings in a list; 0 for anything that is not a list."""
    return sum(1 for item in value if not _blank(item)) if isinstance(value, list) else 0


def _objects(value, key: str) -> list[tuple[int, dict]]:
    """``(index, item)`` for the object items of the array at ``value[key]``; tolerant of malformed shapes."""
    items = value.get(key) if isinstance(value, dict) else None
    if not isinstance(items, list):
        return []
    return [(index, item) for index, item in enumerate(items) if isinstance(item, dict)]


def _unique(errors: list[str], pairs, keys: tuple, base: str, label: str) -> None:
    """Report items whose ``keys`` tuple repeats an earlier item's; the first key names the reported location."""
    first: dict = {}
    for index, item in pairs:
        if any(key not in item for key in keys):
            continue
        ident = _canonical([item[key] for key in keys])
        where = _pointer((base, index, keys[0]))
        if ident in first:
            shown = ", ".join(f"{key}={_j(item[key])}" for key in keys)
            errors.append(f"{where}: unique-id: duplicate {label} ({shown}); first seen at {first[ident]}")
        else:
            first[ident] = where


def _semantics_verification_plan(plan: dict) -> list[str]:
    errors: list[str] = []
    requirements = _objects(plan, "requirements")
    _unique(errors, requirements, ("id",), "requirements", "requirement id")
    _unique(errors, _objects(plan, "risks"), ("id",), "risks", "risk id")
    for index, requirement in requirements:
        if _entries(requirement.get("checks")) + _entries(requirement.get("coverage")) == 0:
            errors.append(f"{_pointer(('requirements', index))}: checkable: requirement {_j(requirement.get('id'))} "
                          "has neither checks nor coverage, so nothing can close it")
    if _entries(plan.get("signoff_criteria")) == 0:
        errors.append("/signoff_criteria: non-empty: at least one non-blank signoff criterion is required")
    return errors


def _semantics_traceability(trace: dict) -> list[str]:
    errors: list[str] = []
    records = _objects(trace, "records")
    _unique(errors, records, ("requirement_id",), "records", "requirement_id")
    for index, record in records:
        if record.get("status") in ("passing", "waived") and _entries(record.get("evidence")) == 0:
            errors.append(f"{_pointer(('records', index, 'evidence'))}: evidence-required: status "
                          f"{_j(record.get('status'))} for {_j(record.get('requirement_id'))} needs at least one "
                          "evidence reference")
    return errors


def _semantics_regression_result(result: dict) -> list[str]:
    errors: list[str] = []
    if _blank(result.get("run_id")):
        errors.append("/run_id: non-empty: run_id must be a non-blank string")
    _unique(errors, _objects(result, "tests"), ("name", "seed"), "tests", "test")
    started, ended = parse_datetime(result.get("started_at")), parse_datetime(result.get("ended_at"))
    if started is not None and ended is not None and ended < started:
        errors.append(f"/ended_at: time-order: ended_at {_j(result['ended_at'])} precedes started_at "
                      f"{_j(result['started_at'])}")
    return errors


def _semantics_waiver(waiver: dict) -> list[str]:
    errors: list[str] = []
    if parse_date(waiver.get("expiry")) is None:
        errors.append(f"/expiry: valid-date: expiry {_j(waiver.get('expiry'))} must be a calendar date YYYY-MM-DD")
    if waiver.get("status") == "approved":
        approver, owner = waiver.get("approver"), waiver.get("owner")
        if _blank(approver):
            errors.append("/approver: approver-required: an approved waiver names a non-blank approver")
        elif isinstance(owner, str) and approver.strip().casefold() == owner.strip().casefold():
            errors.append(f"/approver: approver-distinct: approver {_j(approver)} must differ from owner "
                          "(segregation of duties, docs/session-templates/S13-signoff-audit-init.md)")
    return errors


CONTRACT_RULES = {
    "verification-plan": _semantics_verification_plan,
    "traceability": _semantics_traceability,
    "regression-result": _semantics_regression_result,
    "waiver": _semantics_waiver,
}


def check_semantics(kind: str, instance) -> list[str]:
    """Evidence-contract rules for ``kind`` (a CONTRACT_RULES key), as ``<path>: <rule>: <detail>`` findings.

    The rules tolerate structurally invalid instances (they only report what they can see), so they can be
    combined with ``validate`` and every finding is listed. An unknown ``kind`` raises ValueError.
    """
    if kind not in CONTRACT_RULES:
        raise ValueError(f"unknown artifact kind {kind!r}; known kinds: {', '.join(sorted(CONTRACT_RULES))}")
    if not isinstance(instance, dict):
        return [f"/: object: a {kind} artifact must be a JSON object, got {_type_name(instance)}"]
    return CONTRACT_RULES[kind](instance)


# --------------------------------------------------------------------------- repository modes
def repo_root() -> Path:
    return _HERE.parent


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _kind_of(template: Path) -> str:
    return template.name[: -len(TEMPLATE_SUFFIX)]


def template_pairs(root: Path) -> list[tuple[Path, Path | None]]:
    """``(template, schema or None)`` for every templates/<name>.example.json, matched to schemas/<name>.schema.json."""
    pairs = []
    for template in sorted((root / "templates").glob(f"*{TEMPLATE_SUFFIX}")):
        if template.is_file():
            schema = root / "schemas" / f"{_kind_of(template)}{SCHEMA_SUFFIX}"
            pairs.append((template, schema if schema.is_file() else None))
    return pairs


def check_templates(root: Path | str) -> list[str]:
    """Validate every shipped template that has a schema by name, plus that kind's evidence-contract rules.

    Findings are ``<template>#<path>: <rule>: <detail>`` with the template path relative to ``root``. A template
    without a schema is reported as a NOTICE on stderr and skipped. Raises LoadError (fail closed) when there
    are no templates or none of them has a schema, and SchemaError when a shipped schema is unsupported.
    """
    root = Path(root).resolve()
    pairs = template_pairs(root)
    if not pairs:
        raise LoadError(root / "templates", f"no *{TEMPLATE_SUFFIX} templates found; nothing to validate")
    errors: list[str] = []
    validated = 0
    for template, schema in pairs:
        kind = _kind_of(template)
        if schema is None:
            print(f"NOTICE[schema] {_rel(root, template)}: no schema at schemas/{kind}{SCHEMA_SUFFIX}; not validated",
                  file=sys.stderr)
            continue
        instance = load_json(template)
        findings = validate(instance, load_json(schema))
        if kind in CONTRACT_RULES:
            findings += check_semantics(kind, instance)
        errors.extend(f"{_rel(root, template)}#{finding}" for finding in findings)
        validated += 1
    if validated == 0:
        raise LoadError(root / "templates", "no template has a matching schema; nothing was validated")
    return errors


def self_check(root: Path | str) -> list[str]:
    """Problems with the shipped schemas as ``schemas/<file>: <detail>``; empty means every schema passes.

    Each schema must load as strict JSON, pass ``check_schema``, declare ``$schema`` 2020-12, and be an object
    schema with ``additionalProperties`` false and a non-empty ``required`` list. Raises LoadError when there
    are no schemas at all (fail closed).
    """
    root = Path(root).resolve()
    paths = sorted(path for path in (root / "schemas").glob("*.json") if path.is_file())
    if not paths:
        raise LoadError(root / "schemas", "no schemas found; nothing to check")
    problems: list[str] = []
    for path in paths:
        rel = _rel(root, path)
        try:
            schema = load_json(path)
            check_schema(schema)
        except LoadError as exc:
            problems.append(f"{rel}: {exc.reason}")
            continue
        except SchemaError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        if schema.get("$schema") != SCHEMA_2020_12:
            problems.append(f"{rel}: $schema must declare {SCHEMA_2020_12}")
        if schema.get("type") != "object":
            problems.append(f"{rel}: root type must be \"object\"")
        if schema.get("additionalProperties") is not False:
            problems.append(f"{rel}: root additionalProperties must be false")
        if not schema.get("required"):
            problems.append(f"{rel}: root required must be a non-empty array")
    return problems


def _report(errors: list[str], label: str) -> None:
    for error in errors:
        print(f"ERROR[{label}] {error}", file=sys.stderr)


def _run_templates(root: Path) -> int:
    errors = check_templates(root)
    if errors:
        _report(errors, "schema")
        return EXIT_INVALID
    pairs = template_pairs(root)
    without = sum(1 for _, schema in pairs if schema is None)
    print(f"Templates OK: {len(pairs) - without} validated against schemas/*{SCHEMA_SUFFIX} with contract rules; "
          f"{without} without a schema (see NOTICE lines).")
    return EXIT_OK


def _run_self_check(root: Path) -> int:
    problems = self_check(root)
    if problems:
        _report(problems, "unsupported")
        return EXIT_UNSUPPORTED
    count = len(list((root / "schemas").glob("*.json")))
    print(f"Schema self-check OK: {count} schemas declare 2020-12, are closed object schemas with required "
          "properties, and use only supported keywords.")
    return EXIT_OK


def _run_instance(schema_path: Path, instance_path: Path, kind: str | None) -> int:
    schema = load_json(schema_path)
    instance = load_json(instance_path)
    errors = validate(instance, schema)
    if kind:
        errors += check_semantics(kind, instance)
    if errors:
        _report(errors, "schema")
        return EXIT_INVALID
    suffix = f" and satisfies the {kind} contract rules" if kind else ""
    print(f"OK: {instance_path} is valid against {schema_path}{suffix}.")
    return EXIT_OK


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DV evidence artifacts against the shipped JSON Schemas (standard library only)",
        epilog="Exit codes: 0 valid; 1 instance invalid; 2 usage error; 3 schema unsupported/invalid or file "
               "unreadable.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--templates", action="store_true",
                      help="validate every templates/*.example.json against schemas/*.schema.json by name")
    mode.add_argument("--self-check", action="store_true",
                      help="verify that every schemas/*.json is a supported, closed 2020-12 object schema")
    mode.add_argument("--schema", metavar="PATH", help="schema file; validates --instance against it")
    parser.add_argument("--instance", metavar="PATH", help="instance file to validate (with --schema)")
    parser.add_argument("--kind", choices=sorted(CONTRACT_RULES),
                        help="also apply this artifact kind's evidence-contract rules (with --schema)")
    args = parser.parse_args(argv)
    if (args.schema is None) != (args.instance is None):
        parser.error("--schema and --instance must be given together")
    if args.kind and args.schema is None:
        parser.error("--kind requires --schema and --instance")
    root = Path(root).resolve() if root is not None else repo_root()
    try:
        if args.templates:
            return _run_templates(root)
        if args.self_check:
            return _run_self_check(root)
        return _run_instance(Path(args.schema), Path(args.instance), args.kind)
    except SchemaCheckError as exc:
        print(f"ERROR[{exc.label}] {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
