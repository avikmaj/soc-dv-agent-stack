# Cupel Examples

Every `*.example.json` file here validates against the schema of the same stem under `orgs/cupel/schemas/`; `orgs/cupel/tools/validate_cupel.py` checks that on every run. The two walkthroughs show the same case in the text form a human sees on a platform.

| File | Shows |
|---|---|
| `case-request.example.json` | A `CUPEL-REQUEST` asking for a verdict on a pinned candidate whose nightly report asserts success |
| `department-report.example.json` | The `CUPEL-REPORT` of `cupel-testbench-works` for that case: an Observed checker defect, a Derived consequence, a Proposed fix, one BLOCKING dissent, `verdict: NONE` |
| `evidence-record.example.json` | A record the Vault minted from the retained regression report: report-only, STALE, rank 4 |
| `dissent-ledger-entry.example.json` | The BLOCKING entry raised by `testbench-works`, OPEN, with its discriminating command |
| `final-verdict.example.json` | The Marshal's composed deliverable with the Chamber's `NOT READY`, `C-001/CP-1`, and the ceiling computation copied verbatim |
| `walkthrough-review-path.md` | A review request containing a negated tripwire: review path, Chamber appended, no verdict, no CP identifier |
| `walkthrough-verdict-path.md` | The same design with a report that asserts success: verdict path end to end |

The example data is synthetic. Commit hashes, tool names, and file paths are placeholders and are not evidence of anything.
