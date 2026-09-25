# Modes, Elevation, Execution Approval, and Tripwires

Cupel is read-only unless a human says otherwise in a fixed sentence. This document defines the five operating modes, the two approval sentences, and the tripwire list. The sentences are matched verbatim by the Marshal and by the receiving face; a paraphrase is not an approval.

## Modes

| Mode | Who | What is allowed | What is not |
|---|---|---|---|
| **Read-only** (default) | every review face, every office except stewardship's allowlist, the Marshal | inspect, search, analyse, explain, review, trace, classify, challenge, recommend, produce patches and diffs as text inside a report | editing any file, deleting, altering configuration, executing anything, commit, push, pull request |
| **Planning** | review faces, chiefly `charter-bench` | plans, architecture, test strategy, coverage strategy, implementation strategy, closure contracts, all as text | any change to the project |
| **Implementation** | drafting faces only, under elevation | create or modify files under the elevation glob; implement RTL, testbench, UVM, SVA, scripts, or configuration as minimal reviewable patches | edits outside the glob; `.git/`, `.github/`, generated or vendor collateral, encrypted IP, tool databases; this stack's `skills/`, `scripts/`, `tests/`, `schemas/` unless the glob names the directory; any execution; any git write |
| **Validation** | `cupel-regression-yard-runner`, plus `cupel-stack-stewardship`'s check-only allowlist | one approved `.soc-dv/config.json` entry through `scripts/run_tool.py` per verbatim approval; quoting raw output | any other program, chaining, redirection, editing the configuration, rerunning without a new approval |
| **Challenge** | `cupel-challenge-chamber` | adversarial review of every claim, ledger reconciliation, ceiling computation, Chamber pass issuance | any modification of anything, ever |

A face in the wrong mode for its class does not switch modes; it reports the mismatch and continues in the mode its class permits.

## The read-only-first sequence

Before any change, in this order: inspect; understand; identify the affected scope; propose the change as text; explain the validation strategy; obtain the elevation sentence; implement under the glob; obtain execution approval; validate through the runner; report evidence through the Vault. Skipping a step is a finding against the case.

## Elevation sentence (implementation)

The Marshal dispatches a drafting face only when the request contains this sentence verbatim, with `<dept>` replaced by a department that has a drafting face and `<path-glob>` replaced by the paths the human is opening:

```text
Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.
```

One sentence elevates one department for one glob for one case. `Elevate Cupel/testbench-works to implementation for tb/**; I approve file edits under that path.` does not permit an edit under `rtl/`, does not permit `comparator-desk-drafting` to act, and does not carry over to the next case. Elevation never grants execution, commit, push, or publication.

## Execution approval sentence (validation)

The runner executes one configuration entry per sentence of this exact form, quoted in the dispatch's `approved_commands`:

```text
Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.
```

`<config-path>` is the path to the project's `.soc-dv/config.json`; `<entry>` is a key under its `tools` object. The runner performs a `--dry-run` first, then the single real execution, and quotes the raw output. A rerun, a different seed, or a different entry needs a new sentence. The runner script has open findings in `docs/audits/2026-09-24/static-security-audit.md`; the sentence is the compensating human control, not a licence.

## Tripwires

Tripwire words: pass, passed, proven, closed, covered, compliant, clean, signoff, ready, verified, success, closure, complete, green.

Rules:

- Matching is lexical and case-insensitive, in the request, the targets a face reads, and every report; substring hits count (`complete` inside `completeness`, `pass` inside `passing`) because the scan is deliberately conservative. Negation is not interpreted: "do not claim PASS" is a hit.
- A hit is reported under `claims_of_success` with its source and line, and it appends Challenge Chamber scrutiny (claim-challenger and ledger-reconciler stations) to the case.
- A tripwire never selects the verdict path, never grants PASS, and never assigns a Chamber pass identifier. Path selection is the Marshal's reading of whether a verdict is requested or an input asserts success.
- Reserved words inside department reports (for example `NOT READY` in `ceiling_suggestion`, or `closed` in a coverage finding) also trigger scrutiny. That over-triggering is accepted for now; exclusion rules are deferred to Phase 2 (`rebuild-notes.md`).

The first nine words are the accepted design's list; the last five were added in this rebuild as permitted by the accepted design. The list is machine-checked for consistency between this file, `cupel.json`, and every card.

## Approval boundaries the human keeps

Regardless of mode: network access, package installation, destructive operations, writes outside the project, following or creating symbolic links, commit, push, force-push, pull request, merge, tag, release, deployment, publication, persistent memory writes, and uploading confidential material are separate approval boundaries, each requiring its own explicit human approval in the words of the repository's `AGENTS.md`. Cupel adds the two sentences above; it removes none of these.
