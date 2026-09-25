#!/usr/bin/env python3
"""Cupel consistency validator (standard library only).

Runs the parity checks, then verifies that the organisation is internally
consistent: the law is verbatim wherever it must be, identifier patterns and
tripwire lists agree between cupel.json, documents, schemas, and cards, the
approval sentences and Marshal sentinels are quoted exactly, the CLAUDE.md and
AGENTS.md pointer blocks match their canonical sources, examples validate
against the schemas, referenced paths exist, and no unsafe pattern appears.

Exit status: 0 on success, 1 on any error. Nothing is modified.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORE = ROOT / "orgs" / "cupel"
DOCS = CORE / "docs"
ADAPTERS = CORE / "adapters"
BUNDLE = ADAPTERS / "portable" / "knowledge-bundle"
SCHEMAS = CORE / "schemas"
EXAMPLES = CORE / "examples"
CANON = CORE / "agents"

UNSAFE = [r"curl\s", r"wget\s", r"rm\s+-rf", r"--dangerously-skip-permissions", r"child_process", r"shell\s*=\s*True"]
UNSAFE_EXEMPT = {"validate_cupel.py"}


def _load_parity():
    spec = importlib.util.spec_from_file_location("check_parity", HERE / "check_parity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(p):
    return p.read_text(encoding="utf-8")


# ----------------------------------------------------------------- mini JSON Schema
JSON_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def resolve_ref(ref, root):
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref: {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate_instance(inst, schema, root, path="$"):
    """Validate inst against the supported JSON Schema subset; return error list."""
    errors = []
    if "$ref" in schema:
        schema = resolve_ref(schema["$ref"], root)
    if "const" in schema and inst != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {inst!r}")
    if "enum" in schema and inst not in schema["enum"]:
        errors.append(f"{path}: {inst!r} not in enum {schema['enum']!r}")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(JSON_TYPES[t](inst) for t in types):
            errors.append(f"{path}: expected type {types}, got {type(inst).__name__}")
            return errors
    if isinstance(inst, str):
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            errors.append(f"{path}: {inst!r} does not match {schema['pattern']!r}")
        if "minLength" in schema and len(inst) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(inst) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errors.append(f"{path}: {inst} < minimum {schema['minimum']}")
        if "maximum" in schema and inst > schema["maximum"]:
            errors.append(f"{path}: {inst} > maximum {schema['maximum']}")
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(inst):
                errors += validate_instance(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(inst, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in inst:
                errors.append(f"{path}: missing required property {key!r}")
        if schema.get("additionalProperties") is False:
            for key in inst:
                if key not in props:
                    errors.append(f"{path}: additional property not allowed: {key!r}")
        for key, sub in props.items():
            if key in inst:
                errors += validate_instance(inst[key], sub, root, f"{path}.{key}")
    return errors


# ----------------------------------------------------------------- checks
def law_texts():
    law_doc = read(DOCS / "law.md")
    quotes = [ln[2:].strip() for ln in law_doc.splitlines() if ln.startswith("> ")]
    if not quotes:
        return None, None
    law = quotes[0]
    anchor = law.split(". ", 1)[0] + "."
    return law, anchor


def must_contain(errors, path, needle, label):
    text = read(path)
    if needle not in text:
        errors.append(f"{path.relative_to(ROOT)}: does not contain {label}")


def marker_block(text, begin, end):
    i, j = text.find(begin), text.find(end)
    if i < 0 or j < 0 or j < i:
        return None
    return text[i:j + len(end)]


def check_paths_exist(errors, md_files):
    prefixes = ("orgs/cupel/", ".claude/agents/cupel/", "schemas/", "skills/", "scripts/", "docs/", "templates/", "tests/")
    pat = re.compile(r"`([^`\s]+)`")
    for p in md_files:
        text = read(p)
        for tok in pat.findall(text):
            if "<" in tok or "*" in tok or tok.endswith("/**"):
                continue
            tok = tok.rstrip(".,;:")
            if not tok.startswith(prefixes):
                continue
            # A path may be written relative to the repository root, to the
            # Cupel core directory, or to the document's own directory.
            bases = (ROOT, CORE, p.parent)
            if tok.endswith("/"):
                ok = any((b / tok).is_dir() for b in bases)
            else:
                ok = any((b / tok).exists() for b in bases)
            if not ok:
                errors.append(f"{p.relative_to(ROOT)}: referenced path does not exist: {tok}")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = (p.parent / link.split("#", 1)[0]).resolve()
            if not target.exists():
                errors.append(f"{p.relative_to(ROOT)}: broken link: {link}")


def main():
    errors = []
    parity = _load_parity()
    manifest = parity.load_manifest()
    perr, n_cards, _, n_schemas = parity.check_all(manifest)
    errors += ["parity: " + e for e in perr]

    cards = {p.stem: p for p in parity.canonical_cards()}
    md_files = sorted(set(CORE.rglob("*.md")))

    # law verbatim
    law, anchor = law_texts()
    if not law:
        errors.append("docs/law.md: no blockquoted law text found")
    else:
        for rel in ("adapters/portable/knowledge-bundle/01-law.md", "adapters/portable/chat-kernel.md"):
            must_contain(errors, CORE / rel, law, "the law verbatim")
        for face in ("case-marshal", "challenge-chamber", "evidence-vault"):
            if face in cards:
                must_contain(errors, cards[face], law, "the full law verbatim")
        for face, p in cards.items():
            must_contain(errors, p, anchor, "the law's first sentence verbatim")
        if "undetermined" not in law or "untested" not in law:
            errors.append("docs/law.md: law text lost its closing vocabulary sentence")

    # tripwires
    trip = ", ".join(manifest["tripwire_words"])
    for target in [DOCS / "modes.md", ADAPTERS / "portable" / "chat-kernel.md", ADAPTERS / "portable" / "prompt-protocol.md", BUNDLE / "03-report-format.md"] + list(cards.values()):
        must_contain(errors, target, trip, "the tripwire word list")

    # identifier patterns
    pats = manifest["identifier_patterns"]
    evm = DOCS / "evidence-and-verdict-model.md"
    for key, rel_schema, field in (
        ("dissent_entry", "dissent-ledger-entry.schema.json", "id"),
        ("evidence_record", "evidence-record.schema.json", "id"),
    ):
        must_contain(errors, evm, pats[key], f"the {key} regex")
        sch = json.loads(read(SCHEMAS / rel_schema))
        if sch["properties"][field].get("pattern") != pats[key]:
            errors.append(f"schemas/{rel_schema}: {field} pattern differs from cupel.json {key}")
    must_contain(errors, evm, pats["chamber_pass"], "the chamber_pass regex")
    for face in ("case-marshal", "challenge-chamber"):
        must_contain(errors, cards[face], pats["dissent_entry"], "the dissent regex")
    must_contain(errors, cards["challenge-chamber"], pats["chamber_pass"], "the chamber_pass regex")
    must_contain(errors, cards["evidence-vault"], pats["evidence_record"], "the evidence_record regex")
    for face, p in cards.items():
        if face not in ("case-marshal",):
            must_contain(errors, p, pats["dissent_entry"], "the dissent regex in its Dissent section")

    # approval sentences and sentinels
    elev = manifest["approval_sentences"]["elevation"]
    runs = manifest["approval_sentences"]["execution"]
    for target in (DOCS / "modes.md", cards["case-marshal"], ROOT / "CLAUDE.md", ROOT / "AGENTS.md", ADAPTERS / "portable" / "chat-kernel.md", ADAPTERS / "portable" / "prompt-protocol.md"):
        must_contain(errors, target, elev, "the elevation sentence")
    for target in (DOCS / "modes.md", cards["case-marshal"], cards["regression-yard-runner"], ROOT / "CLAUDE.md", ROOT / "AGENTS.md", ADAPTERS / "portable" / "prompt-protocol.md"):
        must_contain(errors, target, runs, "the execution approval sentence")
    for f in manifest["faces"]:
        if f["class"] == "drafting":
            must_contain(errors, cards[f["face"]], elev, "the elevation sentence")
    sent = manifest["marshal_sentinels"]
    for target in (cards["case-marshal"], DOCS / "operating-model.md", ROOT / "CLAUDE.md", ROOT / "AGENTS.md", ADAPTERS / "portable" / "chat-kernel.md"):
        must_contain(errors, target, sent["chamber_not_run"], "the Chamber-not-run sentinel")
    for target in (cards["case-marshal"], DOCS / "operating-model.md", ADAPTERS / "portable" / "chat-kernel.md"):
        must_contain(errors, target, sent["review_path_header"], "the review-path header")

    # pointer blocks
    for host, section, begin, end in (
        (ROOT / "CLAUDE.md", ADAPTERS / "claude" / "claude-md-section.md", "<!-- cupel:claude-md:begin -->", "<!-- cupel:claude-md:end -->"),
        (ROOT / "AGENTS.md", ADAPTERS / "codex" / "agents-md-section.md", "<!-- cupel:agents-md:begin -->", "<!-- cupel:agents-md:end -->"),
    ):
        canonical = marker_block(read(section), begin, end)
        actual = marker_block(read(host), begin, end)
        if canonical is None:
            errors.append(f"{section.relative_to(ROOT)}: marker block missing")
        elif actual != canonical:
            errors.append(f"{host.relative_to(ROOT)}: pointer block differs from {section.relative_to(ROOT)}")

    # manifest vs cards
    faces = {f["face"]: f for f in manifest["faces"]}
    for d in manifest["departments"]:
        if d not in faces or faces[d]["class"] != ("review" if d != "challenge-chamber" else "review"):
            errors.append(f"cupel.json: department {d} has no review face")
    if manifest["entry_point"] not in faces or faces[manifest["entry_point"]]["class"] != "marshal":
        errors.append("cupel.json: entry_point is not a marshal-class face")
    for face, f in faces.items():
        text = read(cards[face]) if face in cards else ""
        m = re.search(r"^tools: (.*)$", text, re.M)
        tools = m.group(1) if m else ""
        if "Bash" in tools and f["class"] not in ("runner", "steward"):
            errors.append(f"{face}: Bash outside runner/steward class")
        if "Agent" in tools and f["class"] != "marshal":
            errors.append(f"{face}: Agent tool outside the marshal class")
        if f["class"] in ("review", "office") and any(t in tools for t in ("Edit", "Write", "Bash", "Agent")):
            errors.append(f"{face}: write or execute tool on a read-only class")
    if len(faces) != len(manifest["faces"]):
        errors.append("cupel.json: duplicate face entries")

    # alias coverage and department presence
    op = read(DOCS / "operating-model.md")
    marshal = read(cards["case-marshal"])
    bundle2 = read(BUNDLE / "02-departments.md")
    dmap = read(DOCS / "department-map.md")
    for d in manifest["departments"]:
        if f"`{d}`" not in op:
            errors.append(f"docs/operating-model.md: alias table lacks `{d}`")
        if f"`{d}`" not in marshal:
            errors.append(f"agents/case-marshal.md: alias table lacks `{d}`")
        if d not in bundle2:
            errors.append(f"knowledge-bundle/02-departments.md lacks {d}")
        if f"`{d}`" not in dmap:
            errors.append(f"docs/department-map.md lacks `{d}`")

    # evidence areas
    ev_schema = json.loads(read(SCHEMAS / "evidence-record.schema.json"))
    if ev_schema["properties"]["area"]["enum"] != manifest["evidence_areas"]:
        errors.append("schemas/evidence-record.schema.json: area enum differs from cupel.json evidence_areas")
    evm_text = read(evm)
    for a in manifest["evidence_areas"]:
        if f"`{a}`" not in evm_text:
            errors.append(f"docs/evidence-and-verdict-model.md lacks evidence area `{a}`")
    for a in manifest["evidence_areas"]:
        if a not in read(cards["evidence-vault"]):
            errors.append(f"agents/evidence-vault.md lacks evidence area {a}")

    # inline $defs consistency
    ev_req = ev_schema["required"]
    dl_req = json.loads(read(SCHEMAS / "dissent-ledger-entry.schema.json"))["required"]
    for rel in ("department-report.schema.json", "final-verdict.schema.json"):
        sch = json.loads(read(SCHEMAS / rel))
        if sch["$defs"]["evidence_record"]["required"] != ev_req:
            errors.append(f"schemas/{rel}: $defs.evidence_record.required differs from evidence-record.schema.json")
        if sch["$defs"]["dissent_entry"]["required"] != dl_req:
            errors.append(f"schemas/{rel}: $defs.dissent_entry.required differs from dissent-ledger-entry.schema.json")
    prov_required = ev_schema["properties"]["provenance"]["required"]
    for f in ("source", "revision", "config_hash", "tool", "tool_version", "argv", "run_id", "started_at", "finished_at", "report_path", "owner", "reproduced"):
        if f not in prov_required:
            errors.append(f"schemas/evidence-record.schema.json: provenance lacks required field {f}")
        if f"`{f}`" not in evm_text:
            errors.append(f"docs/evidence-and-verdict-model.md lacks provenance field `{f}`")

    # examples validate
    n_examples = 0
    for ex in sorted(EXAMPLES.glob("*.example.json")):
        stem = ex.name.replace(".example.json", "")
        sch_path = SCHEMAS / f"{stem}.schema.json"
        if not sch_path.is_file():
            errors.append(f"examples/{ex.name}: no schema {sch_path.name}")
            continue
        schema = json.loads(read(sch_path))
        inst = json.loads(read(ex))
        errs = validate_instance(inst, schema, schema)
        errors += [f"examples/{ex.name}: {e}" for e in errs]
        n_examples += 1
    if n_examples != n_schemas:
        errors.append(f"examples: {n_examples} example(s) for {n_schemas} schema(s); every schema needs one example")

    # referenced paths and links
    check_paths_exist(errors, md_files)

    # unsafe patterns
    scan = [p for p in CORE.rglob("*") if p.is_file()] + [p for p in (ROOT / ".claude" / "agents" / "cupel").rglob("*") if p.is_file()]
    for p in scan:
        if p.name in UNSAFE_EXEMPT or "__pycache__" in p.parts or p.suffix in (".pyc", ".pyo"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in UNSAFE:
            if re.search(pat, text, re.I):
                errors.append(f"{p.relative_to(ROOT)}: unsafe pattern {pat}")

    # version consistency
    ver = manifest["version"]
    for rel in ("README.md", "CHANGELOG.md"):
        must_contain(errors, CORE / rel, ver, f"cupel version {ver}")
    if manifest["schema_version"] != "1.0":
        errors.append("cupel.json: schema_version is not 1.0 (update the schemas' const and this check together)")

    n_docs = len([p for p in md_files])
    if errors:
        print("\n".join("ERROR: " + e for e in errors), file=sys.stderr)
        return 1
    print(f"Cupel validation OK: {n_cards} cards, {n_schemas} schemas, {n_docs} markdown documents, {n_examples} examples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
