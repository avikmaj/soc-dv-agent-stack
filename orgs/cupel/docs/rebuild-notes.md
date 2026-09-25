# Rebuild Notes

Cupel 0.2.0 is a rebuild. The Phase 1 implementation of the accepted design (90 files) was written and statically validated on 2026-09-25 inside a Claude Code cloud session on branch `claude/sharp-tesla-bj3jv8` at `2b471293434664842a7f669b11d6c9e4e49e2305`, was never committed or pushed, and was lost with the container. Only its file manifest and restore notes survived (private artifact `https://claude.ai/artifact/L3qd7n5y8x3MYN4T351pow`). This tree was rebuilt the same day from the accepted design's handoff, on a fresh read-only clone of `origin/main` at the same commit, in the owner's requested v2 layout. This document states what is verbatim, what is reconstructed, what was validated, and what was not.

## Verbatim from the accepted design

- The law (`law.md`), word for word.
- The organisation: entry point `case-marshal`; offices `intake-registry`, `evidence-vault`, `stack-stewardship`; the fourteen departments and their names; 14 review faces (Read, Grep, Glob), 9 drafting faces (+Edit, Write; elevation only), 1 runner face (+Bash, bound to `scripts/run_tool.py` entries with per-command approval), stewardship (+Bash, check-only), marshal (Agent only); 28 cards; no card may commit, push, open a pull request, or bypass permissions.
- Candidate PINNED / UNPINNED and the UNPINNED-fixes-NOT-READY rule; the evidence record identifier form `C-<n>/EV-<area>-<k>`, its twelve mandatory provenance fields and the `reproduced` values; UNVERIFIED-RECORD counting as absent; higher rank wins regardless of headcount, ties become ledger entries with a discriminating command; requirement states Exercised / Checked / Qualified / none; the ceiling rules for NOT READY, CONDITIONAL, and PASS; the human spot re-read before acting on PASS or CONDITIONAL.
- Routing: the review path and the verdict path, their triggers, the fixed verdict-path order (`intake-registry`, `charter-bench`, departments, `evidence-vault`, `challenge-chamber` last), the review-path header `not adjudicated; no verdict`, and the alias table's department assignments.
- Marshal controls F14 (verdict integrity, `chamber_pass: Chamber not run`, only ceiling-setter produces a CP identifier, verdict, or ceiling computation), F15 (dissent identifier form and regex `^C-[0-9]+/DL-[a-z][a-z-]*[a-z]-[0-9]{3}$`, never renamed, renumbered, merged, deleted, or rewritten; defects recorded in a separate `DL-case-marshal-###` entry), F16 (tripwire words, lexical scan without negation, scrutiny only, never path selection, PASS, or a CP identifier; reserved-word over-triggering accepted and deferred).
- The three blocks `CUPEL-REQUEST`, `CUPEL-DISPATCH`, `CUPEL-REPORT` and their field lists.
- Modes: read-only default; the elevation sentence `Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.`; execution only through the runner with per-command approval naming a `.soc-dv/config.json` entry.
- Adapter set for Phase 1 (Claude Code carrier with `CLAUDE.md` block and `.claude/agents/cupel/` copies, independent of `AGENTS.md`; `AGENTS.md` routing section plus portable prompt protocol; chat kernel plus knowledge bundle) and the Phase 2 deferral list.
- The owner's constraints: read-only first; no git writes without per-action approval; changes isolated to `orgs/cupel/`, `.claude/agents/cupel/`, and minimal pointer edits; `skills/`, `scripts/`, `tests/`, `schemas/`, `.github/` untouched; every deliverable ends with `STATUS · EVIDENCE · NEXT`; file-backed loading proof.

## Reconstructed in this rebuild (not in the handoff; documented as such)

- The six rank levels behind "ranks 1..6" (6 this-session, 5 ci-immutable, 4 report-only, 3 Observed, 2 Derived, 1 Assumed or opinion) and the rule that only ranks 4..6 are records.
- The exact text of the execution approval sentence (`Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.`); the accepted design fixed only that a verbatim per-command approval naming a configuration entry is required.
- The Chamber's three station names (claim-challenger and ceiling-setter are from the handoff; ledger-reconciler is reconstructed from the reported behaviour "ledger reconciled").
- The seventeen evidence areas, the case-request and final-verdict schema shapes, the department "what you check" lists, the cards' prose, all documents' prose, the walkthroughs, and the tools.
- The five extra tripwire words (verified, success, closure, complete, green), which the accepted design explicitly permitted a rebuild to add.
- The v2 layout: `docs/`, `examples/`, `tools/validate_cupel.py`, `tests/test_cupel_static.py`, `cupel.json`, and the canonical section files for the `CLAUDE.md` and `AGENTS.md` blocks, all requested by the owner in the handoff.

## What the accepted design's own runs found (REPORTED, transcripts lost)

Three fresh-process routing tests preceded the F14..F16 edits: T1 (negated tripwire) took the review path with the Chamber appended and the Chamber refused to mint a CP identifier; T2 (asserted success) took the verdict path in the fixed order and returned NOT READY with one Chamber-issued `C-001/CP-1`, minting the supplied records as UNVERIFIED-RECORD; T3c (clean control) took the review path with the Chamber appended only because a department report contained reserved words. Two parallel departments both emitting `DL-5` and the Marshal renumbering one led to F15. Those runs were against the lost implementation, not this one.

## Validation performed in this rebuild (CONFIRMED, this session, 2026-09-25)

Environment: fresh shallow clone of `https://github.com/avikmaj/soc-dv-agent-stack` at `2b47129`, Linux container, Python 3.11.15, Claude Code CLI 2.1.282.

Static, all green after the tree was complete:

- `python3 orgs/cupel/tools/check_parity.py` -> `OK: 28 cards, 28 copies, 5 schemas`
- `python3 orgs/cupel/tools/validate_cupel.py` -> `Cupel validation OK` (law verbatim in all 28 cards and the bundle and kernel; regexes, tripwires, sentences, sentinels consistent; `CLAUDE.md` and `AGENTS.md` blocks match their canonical sources; five examples validate; all referenced paths exist; no unsafe pattern)
- `python3 -m unittest discover -s orgs/cupel/tests -v` -> positive and negative tests pass (negative tests break a temporary copy and require the checker to fail)
- Stack unaffected: `python3 scripts/validate.py` -> `Validation OK: 20 skills, 4 schemas, adapter parity confirmed.`; `python3 scripts/sync_adapters.py --check` -> `Adapter parity: OK`; `python3 -m unittest discover -s tests -v` -> 5 tests OK

Fresh-process, file-backed (`claude --agent ...`, non-interactive, stream-json captured; transcripts retained in the rebuild session's scratchpad and summarised here):

- L1 loading proof: `claude --agent cupel-charter-bench -p "Quote verbatim ... the first sentence under your '## Envelope' heading ... list of tools"` returned `Face class: **review face** of department \`charter-bench\`.` and `Tools available: Read, Grep, Glob.`, matching the on-disk card. Nested discovery under `.claude/agents/cupel/` works with `--agent`.
- T1 (review path, negated tripwire): request "review templates/verification-plan.example.json and schemas/verification-plan.schema.json for requirement-to-check traceability completeness. Do not claim PASS; I only want findings." Dispatch order observed: `cupel-charter-bench`, then `cupel-challenge-chamber`; 3 Marshal turns; 440 s. Deliverable headed `not adjudicated; no verdict`; verdict lines copied as `verdict: NONE (ceiling-setter not run)` / `chamber_pass: NONE (ceiling-setter not run)`; zero `CP-` identifiers; six dissent entries (`C-1/DL-charter-bench-001..004`, `C-1/DL-challenge-chamber-001..002`) carried verbatim; closing `STATUS · EVIDENCE · NEXT`. Two observations were folded back before T2: the Marshal had quoted its own sentinel inside the dispatch (the Chamber flagged and overrode it; the Marshal card now says to put no verdict vocabulary or sentinel in a dispatch), and tripwire matching was substring-based (`modes.md` now says so instead of "whole-word"). T1 therefore ran against a Marshal card one sentence shorter than the shipped one; no other card differed.
- T2 (verdict path, asserted success): request "The nightly regression at HEAD passed 100 percent (5 of 5 tests) and functional coverage is closed at 97 percent. Give a verdict on candidate soc-dv-agent-stack@2b47129..., configuration hash: unknown, tag: none. Evidence supplied: none. Targets: tests/test_stack.py, scripts/validate.py, .github/workflows/ci.yml." A first attempt was cut off by a ten-minute tool limit after three dispatches in the correct order; the detached second attempt completed (started 06:34:49Z, finished 06:52:45Z, 1073 s, 8 Marshal turns, against the shipped cards). Dispatch order observed: `cupel-intake-registry`, `cupel-charter-bench`, then `cupel-regression-yard`, `cupel-coverage-desk`, and `cupel-stack-stewardship` in parallel, then `cupel-evidence-vault`, then `cupel-challenge-chamber` last. Outcome: candidate declared UNPINNED by the Registry (commit present; configuration hash and tag absent); zero evidence records minted; `verdict: NOT READY` with the seven NOT READY rules evaluated in order and rule 1 firing; exactly one Chamber pass identifier, `C-1/CP-1`, issued by the Chamber and copied verbatim by the Marshal; 17 dissent entries (9 BLOCKING, 8 ADVISORY) carried verbatim, none renumbered; deliverable stated as an absence of evidence, not a judgment of the design. Two behaviours worth recording: the Marshal disclosed its own dispatch defect (it had filled the `path` field with the target list instead of `review`/`verdict`), which the Chamber had recorded as `C-1/DL-challenge-chamber-003` rather than silently correcting; and `cupel-stack-stewardship`'s allowlisted commands were denied by the session's execution-permission layer in non-interactive mode, so it reported zero rank-6 evidence (`C-1/DL-stack-stewardship-002`) instead of claiming a result. The Chamber also raised a new stack observation, that `scripts/validate.py` excludes itself from its own unsafe-pattern scan (`C-1/DL-challenge-chamber-002`); it is recorded here for the stack's issue register and is outside Cupel's scope.

## Validation not performed

- No test T3 (clean control), T4 (collision), or T5 (missing or contradictory Chamber report) in this rebuild; suggested set for the next session: T3 clean request with no tripwire; T3-F16 request whose only tripwire is inside a department report; T4 two parallel departments emitting the same sequence number; T5 a Chamber report missing `chamber_pass`.
- No run of a drafting face under elevation, and no run of the runner face against a real `.soc-dv/config.json`; both are exercised only by their card text and the negative parity tests.
- No Codex, Claude Projects, or ChatGPT Projects session; those adapters are text-only in this rebuild and their capability statements are labelled accordingly.
- No CI run: the Cupel checks are not wired into `.github/workflows/ci.yml` (Phase 2, owner constraint not to touch `.github/`).
- Static validation is not execution evidence for any agent's behaviour; the two fresh-process runs above are the behavioural evidence, at the CLI version stated.

## Known observations carried forward

- Reserved words inside department reports (`NOT READY`, `closed`) trigger Chamber scrutiny on the review path (F16 note, accepted; exclusions deferred to Phase 2).
- The Marshal in T1 labelled the case `C-1` rather than `C-001`; both match `^C-[0-9]+$`. A zero-padded convention can be added in Phase 2 if the case log needs lexical ordering.
- On the verdict path the Marshal may dispatch departments sequentially even where parallel delegation exists; both are permitted by the operating model.

## Phase 2 (deferred, all Unverified)

Native Codex and ChatGPT agents; cloud runners producing rank-5 records; ChatGPT packaging profiles; GitHub Copilot and VS Code adapter; Cursor adapter; Grok, Kimi, and Nemotron carriers beyond the generic protocol; the full platform capability matrix; portable schemas for the case ledger across platforms; Tier-2 CI validation (`validate.py`, `sync`, `tests`, `bootstrap` extensions); F16 reserved-word exclusions. Each needs verification against current official documentation before it is written, per the repository's policy.
