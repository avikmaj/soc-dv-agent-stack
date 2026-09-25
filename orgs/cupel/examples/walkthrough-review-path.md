# Walkthrough: review path with a negated tripwire

This walkthrough mirrors the accepted design's first fresh-process routing test. The request contains the word `PASS` inside a negation. Cupel does not interpret negation: the tripwire fires and the Chamber is appended, but the path stays review because nothing asserts success and no verdict was asked for. No Chamber pass identifier is minted.

## Request (human to Marshal)

```text
Use Cupel to review tb/axi_env/ for UVM phase and objection hygiene. Do not claim PASS; I only want findings.
```

## Marshal routing

```text
path: review              (deliverable is a review; no input asserts success)
tripwires_detected: pass  (in the request, inside a negation; negation is not interpreted)
routed: cupel-testbench-works
appended: cupel-challenge-chamber (tripwire)
case: C-002 (bookkeeping label)
```

## Dispatch (Marshal to testbench-works)

```text
CUPEL-DISPATCH
case: C-002
face: cupel-testbench-works
mode: read-only
path: review
elevation: none
approved_commands: none
platform: claude-code
candidate: UNPINNED (no commit, configuration hash, or tag supplied)
targets: tb/axi_env/
evidence: none supplied
open_ledger: (empty)
claim_classes: Observed, Derived, Assumed, Unverified, Proposed
ledger_id_form: ^C-[0-9]+/DL-[a-z][a-z-]*[a-z]-[0-9]{3}$
tripwires_detected: pass (request, line 1, "Do not claim PASS")
task: Review tb/axi_env/ for UVM phase and objection hygiene; report findings only.
```

## Report (testbench-works to Marshal), abridged

```text
CUPEL-REPORT
face: cupel-testbench-works
case: C-002
mode: read-only
path: review
claims_of_success:
  - word: pass; source: request line 1; quote: "Do not claim PASS"
findings:
  Observed:
    - F-001 (medium, rank 3): axi_env.sv:88 raises the run_phase objection in the env but the sequence that drops it lives in axi_base_test.sv:41; an early test end leaves the objection owned by a component that never drops it.
    - F-002 (low, rank 3): axi_driver.sv:130 samples `vif.cb.awvalid` on the clocking block but writes `vif.awready_drive` without the clocking block, mixing sampled and unsampled access in one always block.
  Derived:
    - F-003 (medium, rank 2): Given F-001, a `phase_ready_to_end` extension of the drain time would mask, not fix, the ownership mismatch.
  Proposed:
    - F-004 (rank 1): Move the objection raise/drop pair into axi_base_test.sv, or hand ownership to a virtual sequence; add `+UVM_OBJECTION_TRACE` to the smoke run to observe the change.
evidence_records: (none cited)
requirement_states: (none; no closure contract on the review path)
ledger_entries: (none)
ceiling_suggestion: NOT READY; reasons: candidate UNPINNED; no records
verdict: NONE
ceiling_computation: NONE
human_decisions: none
validation_performed: none
next_commands:
  - python3 scripts/run_tool.py --config .soc-dv/config.json --tool sim --dry-run
residual_gaps: no commit or configuration hash supplied; findings are against the working tree as read
ledger_control: received 0; returned unchanged: true; defects: none
chamber_pass: NONE
```

## Chamber (appended; claim-challenger and ledger-reconciler only), abridged

```text
CUPEL-REPORT
face: cupel-challenge-chamber
case: C-002
mode: challenge
path: review
stations: claim-challenger, ledger-reconciler
claims_of_success:
  - word: pass; source: request line 1; quote: "Do not claim PASS" (no claim of success is made; scrutiny recorded, nothing to challenge)
findings:
  Observed:
    - F-001 (info, rank 3): testbench-works report contains no verdict, no ceiling computation, and no Chamber pass identifier; integrity intact.
ledger_entries: (none)
ceiling_suggestion: NOT READY; reasons: review path; UNPINNED
verdict: NONE (ceiling-setter not run)
ceiling_computation: NONE (ceiling-setter not run)
chamber_pass: NONE (ceiling-setter not run)
ledger_control: received 0; returned unchanged: true; defects: none
```

The Chamber refuses to mint a `C-002/CP-<k>`: the ceiling-setter station does not run on the review path, and no request for a verdict was made.

## Deliverable (Marshal), abridged

```text
CUPEL CASE C-002 · not adjudicated; no verdict
path: review · mode: read-only · platform: claude-code · candidate: UNPINNED
faces: cupel-testbench-works, cupel-challenge-chamber
findings (by rank): F-001, F-002 (Observed, 3) · F-003 (Derived, 2) · F-004 (Proposed, 1)
evidence records: none
dissent ledger: empty
chamber_pass: NONE (ceiling-setter not run)
human decisions: none
validation performed: none · not performed: any simulation
next commands: python3 scripts/run_tool.py --config .soc-dv/config.json --tool sim --dry-run
residual gaps: candidate UNPINNED
STATUS: review complete, not adjudicated · EVIDENCE: none (static review only) · NEXT: pin the candidate if a verdict is wanted
```
