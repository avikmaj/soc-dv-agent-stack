# Optional: Claude Code agent teams

Status: **optional, experimental, UNVERIFIED in this rebuild. Cupel does not depend on it.**

Claude Code has shipped, at various times, experimental multi-agent "team" features in which several long-lived agents coordinate through shared tasks and messages rather than through one main thread dispatching subagents. Whether such a feature is present, what it is called, and how it is enabled (an environment variable or a setting) in the installed CLI must be checked against Anthropic's current documentation before use. Nothing in Cupel's Phase 1 requires it, and no card references it.

## If it is available

A team mapping would be: the Marshal as the lead that creates tasks; one teammate per routed department, each started from the department's card; the Vault and the Chamber as teammates started only after the department tasks close. The organisation, the law, the blocks, and the verdict rules are unchanged. The only things a team changes are:

- **Parallelism.** Departments run concurrently as teammates instead of as concurrent Agent calls; the Marshal still merges by rank and preserves the ledger byte-for-byte.
- **Ordering.** The Marshal must still enforce Registry first, Vault after departments, Chamber last. A team gives no ordering for free; the Marshal creates the Vault and Chamber tasks only after every department task has closed.
- **Independence.** Teammates can message each other. Cupel forbids departments from reading each other's reports before writing their own; the Marshal instructs teammates not to message departments, and a report that quotes another department's report is a finding against independence.
- **Verdict integrity.** Unchanged: only the Chamber teammate's ceiling-setter station writes a verdict or a Chamber pass identifier, and the Marshal copies them verbatim.

## If it is not available, or not enabled

Use `claude-code.md` as written. Concurrent Agent calls from the Marshal main thread give the department stage its parallelism; nothing else in Cupel needs a team.

## What would make this adapter CONFIRMED

A fresh-process run in which teammates started from the on-disk cards quote their own envelope lines, plus a T2-style verdict-path case whose transcript shows Registry-first, Chamber-last ordering and a single `C-<n>/CP-<k>` issued by the Chamber teammate only. Until such a run is recorded with the CLI version and the enabling setting, this document stays UNVERIFIED and optional.
