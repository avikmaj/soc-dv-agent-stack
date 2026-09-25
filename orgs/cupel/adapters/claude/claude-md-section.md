# Canonical `CLAUDE.md` pointer block

The block below is inserted verbatim at the end of the repository's `CLAUDE.md`. `orgs/cupel/tools/validate_cupel.py` checks that `CLAUDE.md` contains it exactly. Edit it here first, then update `CLAUDE.md`.

<!-- cupel:claude-md:begin -->
## Cupel verification organisation (optional layer)

If `orgs/cupel/` exists in this checkout, the Cupel organisation is available: 28 project subagents under `.claude/agents/cupel/`, canonical under `orgs/cupel/agents/`, governed by the law in `orgs/cupel/docs/law.md`. If `orgs/cupel/` is absent, Cupel is not installed; ignore this section.

- Entry point: run `claude --agent cupel-case-marshal` (the Marshal delegates; it reads no files itself). Plain-language requests such as `Use Cupel to review tb/` are routed by `orgs/cupel/docs/operating-model.md`.
- Default mode is read-only. File edits require the verbatim sentence `Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.` Tool execution requires the verbatim sentence `Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.` per entry.
- No face may commit, push, tag, merge, open a pull request, use a permission-bypass flag, access the network, or mint evidence; verdicts come only from the Challenge Chamber's ceiling-setter, and an unrun Chamber is reported as `chamber_pass: Chamber not run`.
- Cupel narrows the rules above; it never relaxes them. Where a Cupel document appears to permit what this file forbids, this file wins.
- Validate the layer with `python3 orgs/cupel/tools/check_parity.py` and `python3 orgs/cupel/tools/validate_cupel.py`.
<!-- cupel:claude-md:end -->
