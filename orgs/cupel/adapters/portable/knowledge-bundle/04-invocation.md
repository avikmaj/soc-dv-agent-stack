# Cupel Knowledge Bundle 4 of 4: invocation on a chat surface

## How to ask

```text
Use Cupel to review this UVM environment (pasted below).
Ask Cupel's protocol department to review this AXI implementation.
Ask the Chamber to challenge this PASS claim.
Use Cupel to investigate this regression failure; the log is pasted below.
Use Cupel to give a verdict on candidate <repo@sha ...>, configuration hash <digest>, tag <tag>; the raw regression summary and coverage report are pasted below.
```

Department words resolve through the alias table in `02-departments.md`. The block form (`CUPEL-REQUEST` in `03-report-format.md`) is recommended for verdicts because it forces the candidate pin to be stated.

## How the reply is built

1. `CUPEL-ROUTING`: path, tripwires, dispatch order.
2. One `CUPEL-REPORT` per face, in dispatch order. Before each report the model re-reads that unit's row in `02-departments.md` (or its full card if uploaded) and writes the report fresh; no later unit revises an earlier report.
3. On the verdict path: intake-registry first (pin or UNPINNED, evidence manifest), charter-bench (closure contract), the routed departments, evidence-vault (records minted from pasted raw output only, report-only at best), challenge-chamber last with its three stations and the ceiling computation.
4. The composed deliverable, ending with `STATUS · EVIDENCE · NEXT`.

If the reply cannot hold everything, it ends with the deliverable so far and `chamber_pass: Chamber not run`; the next reply continues from the next face in order. A verdict is never produced by a truncated Chamber.

## What a chat surface cannot do, said plainly

Nothing is executed, so every record is report-only at best and the ceiling is at most CONDITIONAL; with an UNPINNED candidate it is NOT READY. Nothing is edited; an elevation sentence yields an unapplied patch inside the report. A request to run a tool yields the exact command for a human to run, and the provenance fields the output must carry for the Vault to mint from it later. The independence between units is procedural (fresh read, fresh report), not structural; the deliverable says so under residual gaps.

## Confidentiality

Do not paste confidential RTL, specifications, or logs into a surface whose knowledge or history is shared beyond the people entitled to see them. The repository's rule applies unchanged.
