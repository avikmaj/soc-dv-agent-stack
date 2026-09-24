# SoC DV Agent Stack — Issue Register

- Type: issue register (evidence artifact, authority level 6). Not a session initializer.
- Register version: 1 — created by consolidating findings embedded in the previous session files 00 and 02–13.
- Basis: document review of the Project Knowledge snapshot. No script, test, validator, or tool was executed. Every "fails validation" statement is Derived from reading the validator and the skill text, not from running it.
- Stack baseline status: **NOT READY for evidence-gated automation; usable for advisory work only.** (Replaces the document-review CONDITIONAL verdict formerly in `00-stack-validation-baseline.md` §9.)
- Security findings F1–F19 and hypotheses H1–H6 remain in `static-security-audit.md` and are **not duplicated** here. All are Open by default. Where a register item overlaps one, the audit ID is cross-referenced.
- Tags: Observed / Derived / Assumed / Unverified / Proposed. Historical audit tags keep their meaning: [O] Observed, [D] Derived, [H] Hypothetical analysis, [N] Not assessable/Unverified.

## Status vocabulary

Open · In progress · Superseded (overtaken by an approved decision; not a technical closure) · Closed (only with evidence recorded in the Evidence column and approver named).

## Register

| ID | Issue | Class | Source(s) in previous files | Audit cross-ref | Status |
|---|---|---|---|---|---|
| ISS-001 | Skill files do not match the section contract in `scripts/validate.py` and `CONTRIBUTING.md` (heading names/case, no Checks section) and are likely below the 1800-char minimum. Repository CI state is unknown. | Observed (text); Derived (validator outcome); length Unverified (not measured) | 00 §6.1; 02 STK-001; 03 §5; 04 #1; 05; 07 §13; 08 §8; 09 §10; 10 §0; 11 §11; 13 AI-1 | F5 | Open |
| ISS-002 | Changelog "production-ready" claim is unsupported by any supplied validation, test, or CI evidence and contradicts the roadmap's 1.0 criteria. | Derived | 00 §6.2; 02; 04 #1 | F19 | Open |
| ISS-003 | Files referenced by repository scripts or changelog are absent from Project Knowledge: `CLAUDE.md`, `AGENTS.md`, `VERSION`, `templates/project-config.example.json`, `templates/verification-plan.example.json`, `LICENSE`, threat model, evaluation framework, canonical `skills/` tree. | Observed (absence in snapshot) | 00 §6.3; 02 STK-002 | §1 [N] | Open |
| ISS-004 | Skill frontmatter has only `name` and `version`; no `description`. | Observed | 00 §6.4 | F11 | Open |
| ISS-005 | `03-schema-*` files are field-name lists, not enforceable schemas; nothing validates artifacts against them. | Observed | 00 §6.5; 13 AI-4/AI-5 | F6 | Open |
| ISS-006 | Regression-result field list cannot carry required provenance: command/argv, defines/plusargs, parameters, UVM version, config profile/hash, end time, dirty flag, coverage DB path, compile/elab options, timeout/kill reason, owner, retained-artifact location; test `status` has no value set. | Observed | 00 §6.5; 03 §5; 04 #2; 11 §6; 13 AI-4 | F6 | Open |
| ISS-007 | Traceability field list: status set lacks failing, stale, excluded, unreachable, unsupported, retired; no revision/timestamp/freshness; no config profile; no bin granularity; cannot distinguish Exercised/Checked/Qualified. | Observed | 00 §6.5; 03 §5; 04 #4; 11 §6; 13 AI-5 | F6 | Open |
| ISS-008 | Verification-plan field list lacks spec revision, clause reference, configuration matrix, profile; `priority` values undefined; template signoff criterion does not define "current" and omits coverage goals and exclusion approval. | Observed | 00 §6.5; 04 #3; 11 §6; 13 AI-7 | F6 | Open |
| ISS-009 | Waiver field list lacks a low-power category, status value set, expiry format, scope, residual risk, review trigger, and binding to a design revision. | Observed | 00 §6.5; 10 §10; 11 §6; 13 AI-6 | F6 | Open |
| ISS-010 | No evidence record formats for coverage holes/exclusions, formal results, CDC/RDC, lint/synthesis, UPF, performance workloads, emulation, RAL consistency, signoff verdicts, or claim records. | Observed (absence) | 00 §6.6 | — | Open |
| ISS-011 | `coverage-closure` skill lists six hole causes; Project Instructions define twelve. PI governs by authority order; the skill text is stale. | Observed | 00 §6.7 | — | Open |
| ISS-012 | The Safety section is duplicated verbatim in all 20 skills and in `01-security-policy.md` (drift risk). | Observed | 00 §6.8 | — | Open |
| ISS-013 | `run_tool.py` environment allowlist may omit PATH or license variables, making tool resolution host-dependent. | Derived | 02 STK-002; 13 AI-3 | F3, F17, H4 | Open |
| ISS-014 | `run_tool.py` emits no evidence record (run ID, tool version, commit, timestamps, captured output); its output is not admissible evidence. | Observed | 00 §6.9; 13 AI-2 | F10 | Open |
| ISS-015 | `01-evidence-contract.md` defines four claim classes; Project Instructions define five (adds Proposed). | Observed | this normalization review | — | Open |
| ISS-016 | All 20 skills' Deliverables list four claim classes (no Proposed). Consistent as a subset but incomplete against PI. | Observed | this normalization review | — | Open |
| ISS-017 | Project Instructions list 00 and 02–13 as "workflow initializers", but most are mixed or completed session outputs; no S01/S14 initializer exists. | Observed | this normalization review | — | Open (resolved by the replacement plan once approved) |
| ISS-018 | Capability gaps without a canonical skill or evidence contract: AMBA protocol packs and crossbar/bridge verification, RTL authoring, standalone performance analysis, security/privilege verification, GLS/X-propagation, timing/STA, simulator portability and regression infrastructure, stack validation, stack maintenance. | Observed (absence) | 00 §7; this review | — | Open |
| ISS-019 | Security policy forbids persistent learning without approval; the chat platform can file memory from conversations. Confidential RTL/spec work in this Project needs a memory decision. | Derived | 00 §6.10 | — | Open |
| ISS-020 | Skills' Required inputs are identical generic text; domain-specific inputs are missing (per-skill list in 00 §2, third column). | Observed | 00 §2 | — | Open |
| ISS-021 | A six-level authority order stated in 00 §4 diverges from the eight-level PI order. | Observed | 00 §4 | — | Superseded (decision: PI eight-level order is authoritative) |
| ISS-022 | Previous session files referenced external project assets not in Project Knowledge (`soc_cuvm_suite v0.4`, `noc_vip` and its "open GAPs"). Staleness and confidentiality risk; not reproducible from the snapshot. | Observed | 06 §1 P12, §12; 07 §2, §14 | — | Open |
| ISS-023 | Proposed content defect: mailbox struct in 06 §3 uses a single scalar `ev_wr_idx` for per-core rings described as single-writer per core slot. | Derived | 06 §3 | — | Open (applies only if that content is reused) |
| ISS-024 | Proposed content defect: `p_rst_release` in 09 §6 checks one sample `SYNC_DEPTH` cycles back, not "high for SYNC_DEPTH clocks" as its comment states. | Derived | 09 §6 | — | Open (applies only if reused) |
| ISS-025 | Proposed default in 03 §4 asserts UVM 1.2 is source-compatible with IEEE 1800.2-2020; unverified and not generally true without porting. | Unverified | 03 §4 | — | Open (applies only if reused) |
| ISS-026 | 07 §12 CONDITIONAL criterion ("documented risk acceptance") is weaker than PI ("explicit, approved disposition"). | Observed | 07 §12 | — | Superseded by S07 wording |
| ISS-027 | Several previous files state the validator outcome as Observed or as fact ("fails its own CI") although nothing was executed; claim-class misuse. | Observed | 04 #1; 05; 07 §13; 10 §0 | — | Superseded by S-namespace rules |
| ISS-028 | Several previous files used a seven-class hole taxonomy instead of the PI's twelve. | Observed | 05 §8; 07 §11; 10 §8 | — | Superseded by S05/S07/S10 wording |

## Human decisions pending on this register

- Owner per Open item
- Whether ISS-005–ISS-010 are addressed by one schema revision (JSON Schema) or incrementally
- Whether ISS-011, ISS-015, ISS-016, ISS-020 are fixed in the skills/contract text or left to PI precedence
- Canonical heading set for ISS-001 (same decision as audit item (a))
