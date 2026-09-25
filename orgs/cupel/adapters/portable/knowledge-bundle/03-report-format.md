# Cupel Knowledge Bundle 3 of 4: block formats

The three blocks that carry a case, in the text form used on chat surfaces. Machine-readable schemas: `orgs/cupel/schemas/`. Every field is present in every block; an empty field is written as `none` or `(empty)`, never omitted.

## CUPEL-REQUEST (human to Marshal)

```text
CUPEL-REQUEST
organization: Cupel
deliverable: review | verdict
requested_by: <name>
platform: claude-code | claude-project | codex | chatgpt-project | generic
candidate: UNPINNED | PINNED; commits: <repo@sha ...>; config_hash: <digest>; tag: <tag>
targets: <paths or "pasted below">
evidence_supplied: <paths, run ids, or "pasted raw output below">
departments: auto | <list>
elevation: none | Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.
approved_commands: none | Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.
task: <what you want>
```

## CUPEL-ROUTING and CUPEL-DISPATCH (Marshal)

```text
CUPEL-ROUTING
case: C-<n>
path: review | verdict
tripwires_detected: <word: source, line> | none
dispatch_order: <faces in order>
```

```text
CUPEL-DISPATCH
case: C-<n>
face: cupel-<face>
mode: read-only | planning | implementation | validation | challenge
path: review | verdict
elevation: none | <verbatim sentence>
approved_commands: none | <verbatim sentences>
platform: <platform>
candidate: <as pinned by the Registry, else UNPINNED>
targets: ...
evidence: ...
open_ledger: <prior entries verbatim> | (empty)
claim_classes: Observed, Derived, Assumed, Unverified, Proposed
ledger_id_form: ^C-[0-9]+/DL-[a-z][a-z-]*[a-z]-[0-9]{3}$
tripwires_detected: ...
task: ...
```

## CUPEL-REPORT (face to Marshal)

```text
CUPEL-REPORT
face: cupel-<face>
case: C-<n>
mode: ...
path: ...
claims_of_success:
  - word: <tripwire>; source: <file or block>; line: <n>; quote: "<text>"
findings:
  Observed:
    - F-001 (<severity>, rank 3): <statement> [files: ...] [requirements: ...] [evidence: none | C-<n>/EV-...]
  Derived: ...
  Assumed: ...
  Unverified: ...
  Proposed: ...
evidence_records: <ids cited with CURRENT | STALE | UNVERIFIED-RECORD> | none
requirement_states:
  - <REQ-ID>: none | Exercised | Checked | Qualified; record: <EV id> | none
ledger_entries:
  - id: C-<n>/DL-<face>-<seq>; class: BLOCKING | ADVISORY; status: OPEN; statement: ...; basis: <class>, rank <r>; discriminating_command: <command>
ceiling_suggestion: NOT READY | CONDITIONAL | PASS-eligible; reasons: ...
verdict: NONE                    (Chamber ceiling-setter only: PASS | CONDITIONAL | NOT READY)
ceiling_computation: NONE        (Chamber ceiling-setter only: the rule-by-rule computation)
human_decisions: ...
validation_performed: none | <commands executed with status and output location>
next_commands: <exact commands>
residual_gaps: ...
ledger_control: received <k> entries; returned unchanged: true; defects: none | <new defect entries>
chamber_pass: NONE               (Chamber ceiling-setter only: C-<n>/CP-<k>; review-path Chamber: NONE (ceiling-setter not run))
```

The Vault's report also lists each minted record with all twelve provenance fields, its status, its rank, and the claims it supports. The runner's report lists each execution with argv, cwd, timestamps, exit status, and quoted raw output.

## Deliverable (Marshal)

```text
CUPEL CASE C-<n> · not adjudicated; no verdict | adjudicated by the Challenge Chamber
path · mode · platform · candidate
faces: <in dispatch order>
findings (by rank, then class): ...
evidence records: <verbatim from the Vault> | none
requirement states: ...
dissent ledger: <verbatim, ordered> | empty
verdict: <copied verbatim from the Chamber>            (omitted when the Chamber did not run)
ceiling_computation: <copied verbatim>                  (omitted when the Chamber did not run)
chamber_pass: <copied verbatim> | Chamber not run
human decisions: ...
validation performed: ... · not performed: ...
next commands: ...
residual gaps: ...
STATUS: ... · EVIDENCE: ... · NEXT: ...
```

## Tripwire words

pass, passed, proven, closed, covered, compliant, clean, signoff, ready, verified, success, closure, complete, green. Lexical, case-insensitive, no negation handling. A hit appends Chamber scrutiny and does nothing else.
