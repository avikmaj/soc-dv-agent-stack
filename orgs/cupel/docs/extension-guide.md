# Extension Guide

Cupel grows by adding units, faces, adapters, or protocol expertise without touching the law, the ceiling computation, or an existing card's envelope. This guide lists the allowed extension points and the checks that keep an extension honest.

## Versioning

`orgs/cupel/cupel.json` carries `organization_id`, `organization_name`, `version` (semantic), `schema_version`, `created_date`, `core_path`, `supported_adapter_versions`, and the face inventory. Rules:

- Patch: wording, examples, documentation, validator improvements.
- Minor: a new card, a new department, a new adapter, a new schema field with a default.
- Major: a renamed or removed card, a changed tool envelope, a changed identifier pattern, a change to the ceiling computation, or any change to the law's text.
- `schema_version` changes only when a block or schema changes shape. Adapters state the `schema_version` they were written against; `validate_cupel.py` refuses a mismatch.

## Adding a protocol department

Protocol depth (PCIe, CXL, USB, Ethernet, DDR and LPDDR, HBM, NVMe, SATA, chiplet and UCIe) is added as a department when `interconnect-rulebook` would otherwise carry a rulebook too large to review in one card.

1. Create `orgs/cupel/agents/<name>.md` (review face, `Read, Grep, Glob`) and, if the protocol's VIP configuration is expected to be edited, `<name>-drafting.md`. Follow the card anatomy in `execution-agent-map.md`; quote the law's first sentence verbatim; keep the body between 1800 and 9000 characters and the description at or under 200.
2. Add the unit to `cupel.json` (`departments`, `faces`) and to the alias table in `operating-model.md` and in `case-marshal.md` (both copies).
3. Add the unit's row to `department-map.md` and `execution-agent-map.md`, and to `adapters/portable/knowledge-bundle/02-departments.md`.
4. Run `python3 orgs/cupel/tools/check_parity.py --sync`, then `python3 orgs/cupel/tools/validate_cupel.py` and `python3 -m unittest discover -s orgs/cupel/tests -v`.
5. If the protocol has its own evidence area, add it to the `<area>` enumeration in `evidence-and-verdict-model.md`, `schemas/evidence-record.schema.json`, and `cupel.json` together.

The new department cites specification revisions and sections exactly as `interconnect-rulebook` does. It never carries protocol rules from memory without a citation.

## Adding an execution surface (emulation, FPGA prototyping, post-silicon)

These are evidence areas and runner bindings, not new departments. Add the evidence area (step 5 above), extend the project's `.soc-dv/config.json` with entries for the platform's tools, and let `regression-yard` and its runner face carry them. A platform whose results cannot be bound to a commit and configuration hash produces report-only records at best.

## Adding analog or mixed-signal, AI-assisted formal, or corporate methodology units

Add a department (as above) when the domain has its own review discipline. A corporate methodology unit is a department whose "what you check" list is the company's methodology checklist; it never overrides the law or the ceiling computation, and its card is kept free of confidential material.

## Adding a platform adapter

An adapter maps the six face classes onto a platform's mechanisms and states, per capability, whether the mapping is confirmed, unverified, or absent. It never adds a unit or changes a word of any card.

1. Create `orgs/cupel/adapters/<platform>/README.md` with the adapter contract fields (`adapters/README.md`): platform, supported surfaces, instruction mechanism, repository context, agent mechanism, delegation mechanism, parallelism, tool execution, persistent context, limitations, capability mapping, fallback strategy, invocation examples, and the `schema_version` targeted.
2. If the platform has a native agent mechanism, generate its agent files from the canonical cards (a copy, a rename, or a wrapper; never a rewrite) and add the copy location to `check_parity.py`'s mirror list so drift fails validation.
3. If it has none, point the adapter at `adapters/portable/prompt-protocol.md` and `chat-kernel.md`; that is a complete adapter.
4. Add the adapter to `supported_adapter_versions` in `cupel.json` and to the table in `adapters/README.md`.

Adapters for GitHub Copilot and VS Code, Cursor, Grok, Kimi, and Nemotron or other open-model environments are Phase 2 (`rebuild-notes.md`). Until they exist, those platforms use the generic prompt protocol, which is complete.

## Adding a Chamber station

A station is a labelled, ordered section of the Chamber's report. Add it to the Chamber card (both copies) and to `role-map.md`. A new station never issues a Chamber pass identifier; only the ceiling-setter does.

## What may never be extended

- The law's text.
- The rule that only the Vault mints evidence records and only the ceiling-setter writes a verdict.
- The rule that dissent is carried forward verbatim.
- The read-only default and the two approval sentences' verbatim matching.
- The tool envelope of the Chamber (read-only) and the Marshal (delegation only).
