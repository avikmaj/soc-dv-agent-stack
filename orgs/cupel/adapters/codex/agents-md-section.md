# Canonical `AGENTS.md` routing section

The block below is inserted verbatim at the end of the repository's `AGENTS.md`. `orgs/cupel/tools/validate_cupel.py` checks that `AGENTS.md` contains it exactly. Edit it here first, then update `AGENTS.md`. It is deliberately short: `AGENTS.md` is loaded into every Codex session, so the section carries routing and pointers, and the portable protocol carries the rest.

<!-- cupel:agents-md:begin -->
## Cupel routing (portable verification organisation)

If `orgs/cupel/` exists in this checkout, requests that name Cupel, a Cupel department, "the Chamber", or ask for a verdict are handled by the Cupel organisation. Read `orgs/cupel/adapters/portable/prompt-protocol.md` and act as its Case Marshal: classify the request onto the review path or the verdict path, route by the alias table in `orgs/cupel/docs/operating-model.md`, and emulate each dispatched face sequentially by reading its card under `orgs/cupel/agents/<face>.md` in full before writing that face's `CUPEL-REPORT`. On the verdict path the order is fixed: `intake-registry`, `charter-bench`, routed departments, `evidence-vault`, `challenge-chamber` last. If `orgs/cupel/` is absent, Cupel is not installed; ignore this section.

- The law in `orgs/cupel/docs/law.md` binds every emulated face. A verdict comes only from the Chamber's ceiling-setter station; when the Chamber was not emulated the deliverable says `chamber_pass: Chamber not run`.
- Read-only by default. Edit files only under the verbatim sentence `Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.`; execute only `scripts/run_tool.py` entries named in the verbatim sentence `Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.`
- Dissent entries (`C-<case>/DL-<face>-<seq>`) are carried verbatim; never renumber, merge, or delete one.
- These rules narrow this file's permission boundaries; they never relax them.
<!-- cupel:agents-md:end -->
