# Evidence and Verdict Model

This document defines every term the law (`law.md`) relies on: the candidate, the evidence record, currency, ranks, claim classes, requirement states, the dissent ledger, the ceiling computation, and the three verdicts. The schemas under `orgs/cupel/schemas/` are the machine-readable form of the same definitions; where prose and schema disagree, the schema is wrong and the disagreement is a finding.

## Vocabulary

Cupel keeps the repository's claim classes and verdict words so that a Cupel report is readable by every skill and every session template in the stack. It adds five terms of its own: the **candidate**, the **evidence record**, **currency** (CURRENT or STALE), the **ceiling**, and the **Chamber pass**. The verification law is enforced through those five.

## The candidate

A case is always about a **candidate**: a named revision of the design and its verification environment.

- **PINNED**: the commit of every source repository and submodule (RTL, testbench, VIP, firmware, scripts), the **configuration hash** (a stated digest of `.soc-dv/config.json` together with the defines, plusargs, and tool switches that select the build), and a tag or run label are all identified and mutually consistent.
- **UNPINNED**: anything less. A branch name is not a commit. A tag without a configuration hash is not a pin.

The Intake Registry pins or declares UNPINNED; nobody else does. On the verdict path an UNPINNED candidate fixes the ceiling at NOT READY.

## Claim classes

Every finding, in every report, carries exactly one class:

| Class | Meaning |
|---|---|
| Observed | Present in a precisely identified uploaded or repository file, line, signal, or in raw tool output quoted in the case |
| Derived | Logically inferred from Observed material, with the chain shown |
| Assumed | A necessary working assumption, with an owner or a validation trigger |
| Unverified | Insufficient admissible evidence |
| Proposed | A recommended change, test, property, command, or disposition not yet executed |

A Derived claim is never relabelled Observed because it seems likely. Generated prose, proposed code, a command example, or an unexecuted test is not execution evidence.

## Evidence records

An **evidence record** is the only object that can raise a verdict. It is minted by the Evidence Vault and by nobody else.

Identifier: `C-<n>/EV-<area>-<k>`, regex `^C-[0-9]+/EV-[a-z]+-[0-9]+$`, where `<area>` is one of `compile`, `elaborate`, `sim`, `regression`, `assertion`, `formal`, `coverage`, `lint`, `synth`, `cdc`, `rdc`, `reset`, `upf`, `perf`, `security`, `parity`, `other`.

Mandatory provenance, every field required:

| Field | Meaning |
|---|---|
| `source` | What produced the output (tool run, CI job, retained report) |
| `revision` | Every source and testbench commit the run used |
| `config_hash` | The configuration hash the run used |
| `tool`, `tool_version` | Tool identity as printed by the tool |
| `argv` | The exact command, as executed |
| `run_id` | The run's own identifier (job id, seed set label, report id) |
| `started_at`, `finished_at` | Timestamps |
| `report_path` | Where the raw output or report is retained |
| `owner` | Named human responsible for the record |
| `reproduced` | `this-session`, `ci-immutable`, or `report-only` |

A record missing any field is minted as **UNVERIFIED-RECORD**, with the missing fields named, and counts as absent for every ceiling purpose. The Vault never mints from prose, from a summary, from a badge, from a description of a run, or from a department's belief.

## Currency

A record is **CURRENT** only when its `revision`, `config_hash`, `tool_version`, and the revision of every requirement, property, waiver, or exclusion it depends on equal those of the pinned candidate. Any difference, and any difference that cannot be ruled out, makes it **STALE**. The Vault's currency call is non-arbitrable: no department, majority, or Marshal can overturn it; only a fresh run at the pinned candidate can replace it.

## Evidence ranks

Ranks order what can be said. A higher rank beats any number of lower-rank voices; headcount never counts.

| Rank | What it is | Who assigns | Effect on the verdict |
|---|---|---|---|
| 6 | Record whose tool run happened in this session with raw output quoted (`reproduced: this-session`) | Vault | Can raise |
| 5 | Immutable CI record at the candidate commit with workflow and run identifiers (`ci-immutable`) | Vault | Can raise |
| 4 | Retained report or database bound to the candidate but not rerun (`report-only`) | Vault | Caps at CONDITIONAL |
| 3 | Observed claim | Any face | Can hold or lower only |
| 2 | Derived claim | Any face | Can hold or lower only |
| 1 | Assumed, Proposed, opinion, or agreement among any number of agents or people | Any face | Can hold or lower only |

Ranks 4 to 6 exist only as minted records; ranks 1 to 3 are claim classes. When two items of equal rank disagree, the disagreement is not resolved by argument: it becomes a dissent ledger entry carrying the discriminating command that would settle it.

## Requirement states

Each requirement in the closure contract carries one state, bound to records:

| State | Requires |
|---|---|
| none | Nothing CURRENT shows the requirement was exercised |
| Exercised | A CURRENT record shows the stimulus reached the behaviour (coverage hit or directed observation) |
| Checked | Exercised, plus a CURRENT record shows a checker, assertion, or scoreboard judged that exercise |
| Qualified | Checked in every configuration of the signoff configuration set, with the requirement's coverage items closed and no OPEN dissent naming it |

A state is never granted from a test name, a plan, or a review; it follows the record.

## The dissent ledger

A **dissent ledger entry** records a technically grounded objection that has not been cleared or accepted.

Identifier: `C-<case>/DL-<raising-face>-<three-digit-seq>`, regex `^C-[0-9]+/DL-[a-z][a-z-]*[a-z]-[0-9]{3}$`; for example `C-014/DL-testbench-works-003` or `C-014/DL-case-marshal-001`.

| Field | Values |
|---|---|
| `class` | `BLOCKING` (would by itself prevent readiness) or `ADVISORY` |
| `status` | `OPEN`, `CLEARED` (names a CURRENT record), or `ACCEPTED` (names a human) |
| `statement`, `basis` | The objection, its claim class and rank |
| `discriminating_command` | The exact command whose output would settle it |

Rules: entries are carried forward verbatim; no agent may delete, reword, renumber, merge, or downgrade one. Malformed or colliding identifiers are preserved byte-for-byte and the defect is recorded in a new entry by whoever noticed (`DL-case-marshal-<seq>` or `DL-challenge-chamber-<seq>`). A simple majority never suppresses an OPEN entry.

## Chamber pass

The Challenge Chamber's ceiling-setter station issues exactly one **Chamber pass identifier** per adjudicated case: `C-<n>/CP-<k>`, regex `^C-[0-9]+/CP-[0-9]+$`. No other face, station, or the Marshal may produce, reserve, predict, or suggest one. A case without a Chamber pass has no verdict; the Marshal writes `chamber_pass: Chamber not run`.

## The ceiling computation

The **ceiling** is the highest verdict the registered evidence permits. The ceiling-setter computes it in this order and shows every step; the first rule that fires decides the ceiling:

```text
NOT READY   if the candidate is UNPINNED
NOT READY   if no admissible (non-UNVERIFIED) record exists
NOT READY   if any record required by the closure contract is STALE or missing
NOT READY   if any OPEN BLOCKING dissent entry exists
NOT READY   if any P0 or P1 requirement lacks a CURRENT record
NOT READY   if any reproducibility defect is recorded (a run that cannot be rerun from its own record)
NOT READY   if the ceiling-setter station did not run
CONDITIONAL if any record supporting the contract is report-only (rank 4)
CONDITIONAL if any OPEN ADVISORY entry exists
CONDITIONAL if any BLOCKING entry is ACCEPTED by a human rather than CLEARED by a record
PASS        only if every record is CURRENT and reproduced (rank 5 or 6), every P0 and P1 requirement is Qualified, and the OPEN set is empty
```

The verdict equals the ceiling. Nothing may state a verdict above the ceiling; a human may act below it.

## The three verdicts

| Verdict | Permitted only when |
|---|---|
| PASS | The ceiling computation reaches PASS with current, reproduced records for every P0 and P1 requirement in every signoff configuration and an empty OPEN set |
| CONDITIONAL | Bounded residual items exist, each with an explicit approved disposition: report-only records, OPEN ADVISORY entries, or human-ACCEPTED BLOCKING entries |
| NOT READY | Any NOT READY rule fires; stated as an absence of evidence, never as a judgment of the design |

`No issue identified by static review` is a finding, not a verdict. `Verification passed` is a verdict and requires a Chamber pass.

## Human step before acting

Whenever the ceiling is PASS or CONDITIONAL, the Chamber lists under `human_decisions` a spot re-read of the raw tool output behind at least one rank-5-or-6 record by a named human before anyone acts on the verdict. Cupel does not consider a verdict acted upon until that step is recorded by the human.

## Blocks

Three text blocks carry a case between faces. Their machine-readable forms are `schemas/case-request.schema.json`, the dispatch fields below, and `schemas/department-report.schema.json`.

**CUPEL-REQUEST** (human to Marshal): `organization: Cupel`, `deliverable` (`review` or `verdict`), `requested_by`, `platform`, `candidate` (pin data or `UNPINNED`), `targets`, `evidence_supplied`, `departments` (`auto` or a list), `elevation` (verbatim sentence or `none`), `approved_commands` (list of verbatim approval sentences or `none`), `task`.

**CUPEL-DISPATCH** (Marshal to face): `case`, `face`, `mode`, `path`, `elevation`, `approved_commands`, `platform`, `candidate`, `targets`, `evidence`, `open_ledger` (verbatim), `claim_classes`, `ledger_id_form`, `tripwires_detected`, `task`.

**CUPEL-REPORT** (face to Marshal): `face`, `case`, `mode`, `path`, `claims_of_success`, `findings`, `evidence_records`, `requirement_states`, `ledger_entries`, `ceiling_suggestion`, `verdict`, `ceiling_computation`, `human_decisions`, `validation_performed`, `next_commands`, `residual_gaps`, `ledger_control`, `chamber_pass`.

The Marshal's composed deliverable (`schemas/final-verdict.schema.json`) carries the case header, the ordered face list, merged findings, the Vault's records, requirement states, the ledger, and the verdict lines copied verbatim from the Chamber.
