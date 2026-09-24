# Signoff-Readiness Audit: Initialization

- **Date:** 2026-09-24
- **Scope:** Independent signoff-readiness audit of a DUT or project that has not yet been identified.
- **Selected skill:** signoff-audit, the only primary skill. Domain skills are used only to judge their own evidence classes: coverage-closure, formal-sva, cdc-rdc-reset, low-power-upf, lint-synth-closure, vip-qualifier, regression-triage and noc-verification.
- **Audit default:** NOT READY until objective evidence proves otherwise.

## 1. Current evidence state

Observed: The project knowledge contains only the agent-stack collateral. That means the evidence contract, the methodology, 20 skill files, 4 schemas, 1 template, 4 scripts, CI config and a changelog. It contains no DUT evidence of any kind. There are no specifications, vplan, RTL or TB revisions, regression databases, coverage databases, formal, CDC, RDC or UPF reports, bug list, waivers, or CI and tag records.

Decision if forced today: **NOT READY**. This verdict reflects missing evidence. It is not an assessment of the design.

| # | Area | Status | Basis |
|---|---|---|---|
| 1 | Specs / revisions | MISSING | none supplied |
| 2 | Req / vplan closure | MISSING | only a template (REQ-TBD) |
| 3 | DUT/TB/FW/config revisions | MISSING | no candidate commit or tag |
| 4 | Regression / intermittents | MISSING | none |
| 5 | Functional + code coverage | MISSING | none |
| 6 | Coverage exclusions | MISSING | none |
| 7 | SVA / formal | MISSING | none |
| 8 | CDC / RDC | MISSING | none |
| 9 | Reset verification | MISSING | none |
| 10 | Low-power / UPF | MISSING or N/A? | applicability not declared |
| 11 | Lint / synthesis | MISSING | none |
| 12 | Protocol / VIP qualification | MISSING | none |
| 13 | Performance | MISSING or N/A? | no performance requirements supplied |
| 14 | Bugs / deferrals / limitations | MISSING | none |
| 15 | Waivers / approvals | MISSING | none |
| 16 | Repro / retention | MISSING | none |
| 17 | CI / release tag | MISSING | none |

## 2. Findings on the audit instrument itself

These are Observed in the uploaded files. They matter because the audit would otherwise rely on this tooling as evidence infrastructure.

| ID | Finding | Class | Impact |
|---|---|---|---|
| AI-1 | `validate.py` requires the headings `## Inputs`, `## Checks` and `## Evidence Gate`. The uploaded skills use `## Required inputs` and `## Evidence gate`, and have no `## Checks`. They are also about 1.3–1.5 KB, below the 1800-char minimum. | Observed (text); Derived (validate would fail if these are the canonical `skills/` sources) | Contradicts the changelog's "production-ready" claim. CI green status is Unverified: there is no run ID or log. |
| AI-2 | `run_tool.py` prints argv, cwd and timeout only. It does not record the git commit, tool version, start/end timestamp, run ID, or log path, and it does not capture stdout/stderr. | Observed | Its runs do not satisfy the Evidence Contract. Output from this runner alone is not admissible signoff evidence. |
| AI-3 | `run_tool.py` filters the environment to an allowlist. If PATH or tool license variables are not listed, the tool resolution becomes environment-dependent. | Derived | Reproducibility risk: the same config can behave differently on different hosts. |
| AI-4 | The regression schema has no fields for the command, defines/params, config hash, owner, or retained-artifact location. | Observed | The configuration and reproducibility columns can't be filled from schema-conformant results. |
| AI-5 | The traceability schema has no revision or timestamp field. Its status enum has no `failing` or `stale`. | Observed | "passing" can't be tied to the candidate revision. Staleness is undetectable by schema. |
| AI-6 | The waiver schema has no field binding a waiver to a design revision or scope. | Observed | A waiver approved on rev N can silently carry forward to rev N+1. The audit will treat any unbound waiver as requiring re-approval. |
| AI-7 | The template's signoff criterion reads "current passing evidence" but never defines "current". | Observed | Section 3 below supplies a definition, which needs your approval. |

## 3. Objective criteria I will apply

These are proposed and require your approval (see Human decisions).

**Freshness.** Evidence is current only if its source commit and config hash equal the signoff candidate's. Otherwise it is STALE, unless there is a reviewed diff showing the change is outside that evidence's cone of influence.

**Admissibility.** Each item must carry:

- source, revision and tool/version
- full command, including defines/params and seed
- run ID and timestamp
- report path
- owner

An item missing any of these is Unverified, which counts as MISSING.

**Formal.** Bounded or undetermined results are not proofs. Each one needs an explicit bound justified against the design's latency or depth, plus covers that are shown reachable.

**Waivers and exclusions.** Each must have rationale, evidence, owner, approver distinct from the owner, expiry, and revision binding. Expired or unbound entries count as open issues.

**Intermittents.** An intermittent failure is closed only with a root cause and a fix validated on the failing seed plus a seed sweep. A rerun that passes is not closure.

**Verdicts.**

- **PASS:** all P0/P1 requirements are passing with current, admissible evidence, and there are no open blockers.
- **CONDITIONAL:** only bounded residuals remain, each with an approved disposition, owner, and expiry.
- **NOT READY:** anything else.

## 4. Evidence intake request

Please supply the following, per area. Paths and exports are enough; raw databases are not needed.

- **Candidate identity:** release tag and commit(s) for DUT, TB, VIP, firmware and UPF, plus the config hash and the list of configurations or parameter sets in signoff scope.
- **Specs:** document IDs and revisions, approval records, and the conflict/errata log.
- **Vplan:** the requirement list with priorities, and a traceability export mapping requirement to tests, assertions and coverpoints.
- **Regression:**
  - per-run results (schema-03 or equivalent) with seeds, tool/version and run IDs
  - pass-rate history across the last N regressions
  - the list of intermittents
- **Coverage:**
  - the merged-DB report command and tool version
  - functional and code coverage per scope
  - the hole list, the exclusion file(s), and exclusion review records
- **Formal and SVA:**
  - property list with status (proven, bounded with depth, undetermined, CEX)
  - assumption list and cover results
  - vacuity report
- **CDC, RDC and reset:** reports, the constraint/SDC set used, waiver files, and reset-sequencing tests.
- **UPF:** either the UPF revision plus power-aware sim, static checks and state/transition coverage, or an explicit N/A with justification.
- **Lint and synthesis:** reports, rule-set version, waivers, and the synth run including latch and inferred-structure reports.
- **VIP:** vendor/version, qualification evidence, and known-limitations list.
- **Performance:** requirements, workload definitions, results with provenance, or an N/A declaration.
- **Bugs:** tracker export with severity, state, deferral approvals, and the known-limitations document.
- **Waivers:** all categories, with approver and expiry.
- **Reproduction and CI:** rerun instructions, artifact retention location and policy, CI run IDs for the candidate tag, and tag signature/immutability.

Mark anything confidential. It stays in this chat and is not generalized into public examples.

## 5. Human decisions needed before auditing

1. Identify the signoff candidate tag or commit. Without it, freshness cannot be judged.
2. Approve or amend the criteria in section 3, especially coverage targets per scope and the priority threshold for blocking.
3. Declare the waiver approver authority: who may approve, and whether self-approval is barred.
4. Declare whether UPF and performance are in scope or N/A.
5. Decide whether findings AI-1 through AI-7 should be fixed first, or whether the audit should proceed with them recorded as tooling residual risk. My recommendation is to proceed and treat AI-2, AI-4 and AI-5 as reasons to require raw tool logs rather than schema exports alone.

## 6. Next step

On receipt, I will populate the evidence-provenance matrix item by item. The remaining deliverables follow from it: requirement closure, risk register, waiver and exclusion audit, stale/missing list, blockers, release conditions, and a final verdict. Nothing will be inferred for absent items.
