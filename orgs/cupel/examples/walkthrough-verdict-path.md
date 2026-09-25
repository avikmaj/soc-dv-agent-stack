# Walkthrough: verdict path on an asserted success

This walkthrough mirrors the accepted design's second fresh-process routing test and matches the JSON examples in this directory. A nightly report asserts that everything passed and coverage is closed; the request asks for a verdict. The path is verdict; the fixed dispatch order applies; the Chamber runs last and issues the only Chamber pass identifier of the case.

## Request

The `CUPEL-REQUEST` block is `case-request.example.json`. In plain language:

```text
Use Cupel to give a verdict on candidate example-soc@9f2c1a7d…, axi-vip@4b1e9c0d, configuration hash sha256:3e1f8c2a…, tag regress-2026-09-24-nightly. The nightly regression report says all 412 tests passed and functional coverage is closed at 97 percent.
Run Cupel/regression-yard-runner: .soc-dv/config.json tool lint; I approve this single execution.
```

## Marshal routing

```text
path: verdict            (deliverable is a verdict; the report asserts success)
tripwires_detected: passed, closed (request line 1)
order: cupel-intake-registry -> cupel-charter-bench -> [cupel-testbench-works, cupel-comparator-desk, cupel-coverage-desk] -> cupel-evidence-vault -> cupel-challenge-chamber
runner: cupel-regression-yard-runner for entry `lint` only (one approval sentence present)
case: C-001
```

## Intake Registry (abridged)

```text
candidate: PINNED with a reservation — axi-vip is pinned by a 7-character SHA (4b1e9c0d); the full SHA must be confirmed before currency can be ruled on
case log: no prior ledger
evidence manifest:
  - logs/regress_2026-09-24/summary.txt: present; fields present: source, revision (example-soc full, axi-vip short), config_hash, argv, run_id, started_at, finished_at, report_path, owner; missing: tool_version
  - ci-run-88213: described, not supplied (no log attached)
  - cov/merged_2026-09-24.ucdb.report.txt: present; missing: config_hash, tool_version, argv
```

## Charter Bench (closure contract, abridged)

```text
REQ-AXI-ORD-003 (P0): same-ID write responses returned in order; evidence area: sim (Checked) + coverage; configurations: default, narrow-64
REQ-AXI-BST-011 (P1): WRAP bursts across 4KB boundary rejected; evidence area: assertion + sim; configurations: default
ambiguity A-001: the specification revision for the AXI ordering rules is not stated in the request; recorded, not resolved
```

## Departments (parallel)

`testbench-works` reports as in `department-report.example.json`: the scoreboard downgrades an unmatched write response to a warning (Observed, rank 3), so the 412/412 figure is not a Checked result (Derived, rank 2); one BLOCKING dissent `C-001/DL-testbench-works-001` is raised. `comparator-desk` independently reaches the same Observed finding and raises `C-001/DL-comparator-desk-001` with the same discriminating command; the two entries are kept, not merged. `coverage-desk` finds the merged report unbound to a configuration hash and classifies the "97 percent" as Unverified with primary hole cause `insufficient evidence`.

## Runner

```text
approved: Run Cupel/regression-yard-runner: .soc-dv/config.json tool lint; I approve this single execution.
dry-run plan quoted; executed once; exit status 0; tool banner "Verilator 5.050"; 0 warnings; raw output quoted (41 lines)
```

## Evidence Vault (abridged)

```text
minted:
  C-001/EV-regression-1  STALE   rank 4  report-only  (axi-vip SHA not shown equal to the pin; tool_version absent)  -> see evidence-record.example.json
  C-001/EV-coverage-1    UNVERIFIED-RECORD (missing: config_hash, tool_version, argv) -> counts as absent
  C-001/EV-lint-1        CURRENT rank 6  this-session (runner output quoted; revision and config_hash equal to the pin)
currency call is non-arbitrable
```

## Challenge Chamber (abridged)

```text
claim-challenger:
  "all 412 tests passed": would need a CURRENT sim record with the scoreboard reporting unmatched responses as errors; EV-regression-1 is STALE and the checker is downgraded (DL-testbench-works-001): Unverified
  "coverage closed at 97 percent": EV-coverage-1 is UNVERIFIED-RECORD: Unverified
ledger-reconciler:
  C-001/DL-testbench-works-001 OPEN BLOCKING (well-formed)
  C-001/DL-comparator-desk-001 OPEN BLOCKING (well-formed; same discriminating command; not merged)
ceiling-setter:
  rule 1 (UNPINNED): does not fire
  rule 2 (no admissible record): does not fire (EV-lint-1 is admissible)
  rule 3 (required record STALE or missing): fires; sim record for REQ-AXI-ORD-003 is STALE
  rule 4 (OPEN BLOCKING): would also fire
  rule 5 (P0/P1 without CURRENT record): would also fire
  ceiling = NOT READY, stated as an absence of evidence at the pinned candidate
verdict: NOT READY
chamber_pass: C-001/CP-1
human_decisions: named human to spot re-read the raw lint output behind C-001/EV-lint-1 before relying on it
```

## Deliverable (Marshal)

`final-verdict.example.json` is the composed deliverable. The verdict lines are copied verbatim from the Chamber; the two BLOCKING entries are carried byte-for-byte; the runner's lint record is the only CURRENT evidence in the case and does not bear on the P0 requirement.

```text
STATUS: NOT READY (C-001/CP-1) · EVIDENCE: 1 CURRENT (lint), 1 STALE (regression), 1 UNVERIFIED-RECORD (coverage); 2 OPEN BLOCKING · NEXT: pin the VIP SHA and approve one regression rerun at the pinned candidate
```

What did not happen: no face said the design was wrong. The report asserted success; the evidence registered against the candidate did not reach the bar; the verdict says exactly that and nothing more.
