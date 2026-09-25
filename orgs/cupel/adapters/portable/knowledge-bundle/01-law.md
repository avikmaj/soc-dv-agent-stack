# Cupel Knowledge Bundle 1 of 4: the Law, claim classes, ranks, and the ceiling

Upload this file with `02-departments.md`, `03-report-format.md`, and `04-invocation.md` to a project's knowledge. It is a faithful condensation of `orgs/cupel/docs/law.md` and `orgs/cupel/docs/evidence-and-verdict-model.md`; the law text is verbatim.

## The law

> A verdict is bounded above by what has been registered against the named candidate, never by how much has been thought, argued, or agreed about it. Reading, review, debate, and agreement among any number of agents, departments, or people can hold a verdict where it stands or push it lower; none of them can raise it by one step. The only thing that raises it is a fresh, admissible evidence record minted by the Evidence Vault from a reproducible tool run at the candidate's own commit and configuration hash, or a blocking dissent cleared by such a record. Where that record is missing, stale, incomplete, or cannot be rerun, every claim that needed it stays Unverified and the verdict stays NOT READY, stated as an absence of evidence and not as a judgment of the design. A dissent that has not been cleared by such a record or accepted by a named human is carried forward verbatim; no agent may delete, reword, renumber, or downgrade it. The honest word for a proof that has not been produced is undetermined, and the honest word for a test that has not been run is untested.

## Claim classes

Observed (present in a precisely identified file, line, signal, or raw tool output) · Derived (inferred from Observed material, chain shown) · Assumed (working assumption with an owner or trigger) · Unverified (insufficient admissible evidence) · Proposed (a change, test, property, or command not yet executed). A Derived claim is never relabelled Observed because it seems likely.

## The candidate

PINNED: the commit of every source repository and submodule, the configuration hash (digest of `.soc-dv/config.json` plus defines, plusargs, and tool switches), and a tag, all identified and consistent. UNPINNED: anything less; a branch name is not a commit. UNPINNED fixes the ceiling at NOT READY on the verdict path.

## Evidence records

Identifier `C-<n>/EV-<area>-<k>`; area one of compile, elaborate, sim, regression, assertion, formal, coverage, lint, synth, cdc, rdc, reset, upf, perf, security, parity, other. Minted only by the Evidence Vault, only from raw tool output or a retained report bound to the pinned candidate, and only with all twelve provenance fields: source, revision, config_hash, tool, tool_version, argv, run_id, started_at, finished_at, report_path, owner, reproduced (this-session | ci-immutable | report-only). A record missing any field is UNVERIFIED-RECORD and counts as absent. CURRENT only when revision, configuration hash, tool version, and the revision of every requirement, property, waiver, or exclusion it depends on equal the pinned candidate's; otherwise STALE. The Vault's currency call is non-arbitrable.

## Ranks

6 reproduced in this session (this-session) · 5 immutable CI record at the candidate commit (ci-immutable) · 4 retained report or database bound to the candidate, not rerun (report-only; caps at CONDITIONAL) · 3 Observed · 2 Derived · 1 Assumed, Proposed, opinion, or agreement among any number of agents or people. A higher rank beats any number of lower-rank voices; headcount never counts; an equal-rank disagreement becomes a dissent entry with the discriminating command.

## Requirement states

none · Exercised (a CURRENT record shows the stimulus reached the behaviour) · Checked (Exercised, plus a CURRENT record shows a checker, assertion, or scoreboard judged it) · Qualified (Checked in every signoff configuration, coverage items closed, no OPEN dissent naming it). A state follows the record, never a test name or a plan.

## Dissent ledger

Identifier `C-<case>/DL-<raising-face>-<three-digit-seq>` (regex `^C-[0-9]+/DL-[a-z][a-z-]*[a-z]-[0-9]{3}$`). Class BLOCKING or ADVISORY; status OPEN, CLEARED (names a CURRENT record), or ACCEPTED (names a human). Entries are carried verbatim; nobody renumbers, merges, deletes, or rewords one; collisions and malformed identifiers are preserved and recorded as new defect entries. A majority never suppresses an OPEN entry.

## Chamber pass and the ceiling

Only the Challenge Chamber's ceiling-setter station, on the verdict path, issues exactly one `C-<n>/CP-<k>` per case and writes the verdict. It computes the ceiling in this order, first rule that fires decides:

```text
NOT READY   if the candidate is UNPINNED
NOT READY   if no admissible record exists
NOT READY   if any record required by the closure contract is STALE or missing
NOT READY   if any OPEN BLOCKING dissent entry exists
NOT READY   if any P0 or P1 requirement lacks a CURRENT record
NOT READY   if any reproducibility defect is recorded
NOT READY   if the ceiling-setter station did not run
CONDITIONAL if any supporting record is report-only
CONDITIONAL if any OPEN ADVISORY entry exists
CONDITIONAL if any BLOCKING entry is human-ACCEPTED rather than CLEARED
PASS        only if every record is CURRENT and reproduced (rank 5 or 6), every P0/P1 requirement is Qualified, and the OPEN set is empty
```

The verdict equals the ceiling. When the ceiling is PASS or CONDITIONAL, a named human spot re-reads the raw tool output behind at least one rank-5-or-6 record before anyone acts. When the Chamber did not run, the deliverable says exactly `chamber_pass: Chamber not run`. `No issue identified by static review` is a finding; `Verification passed` is a verdict and needs a Chamber pass.
