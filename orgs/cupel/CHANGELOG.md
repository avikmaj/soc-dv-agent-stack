# Cupel Changelog

Semantic versioning; the rules are in `docs/extension-guide.md`. The stack's own `VERSION` and `CHANGELOG.md` are separate.

## 0.2.0 - 2026-09-25

Rebuild of the accepted design in the owner's requested v2 layout, after the Phase 1 implementation of the same day was lost uncommitted with its cloud container (see `docs/rebuild-notes.md`).

- Canonical core under `orgs/cupel/` with `docs/`, `agents/`, `schemas/`, `examples/`, `adapters/`, `tools/`, `tests/`, and `cupel.json` as the machine-readable identity and face inventory.
- 28 cards: 14 review faces, 9 drafting faces, 1 runner face, 3 offices, 1 entry point; the law's first sentence verbatim in every card and the full law in the Marshal, the Chamber, and the Vault.
- Marshal controls from the accepted design baked into the cards and the operating model: verdict integrity (only the Chamber's ceiling-setter writes a verdict or a `C-<n>/CP-<k>`; `chamber_pass: Chamber not run` otherwise), ledger integrity (`C-<case>/DL-<face>-<seq>`, never renumbered, merged, deleted, or reworded), conservative tripwires (lexical, no negation handling, scrutiny only).
- Tripwire list extended with the five words the accepted design permitted a rebuild to add: verified, success, closure, complete, green.
- Evidence ranks 1..6 written out (the accepted design fixed the rank rule, higher wins regardless of headcount; the six levels are reconstructed and documented as such).
- Five JSON Schemas (draft 2020-12, closed objects, enumerations, identifier patterns) with one validated example each and two walkthroughs mirroring the accepted design's T1 and T2 routing tests.
- `tools/check_parity.py` (card shape, byte-for-byte mirrors, no deletion, symlink refusal, `--sync`) and `tools/validate_cupel.py` (law verbatim, patterns, tripwires, sentences, pointer blocks, schema and example validation, path and link existence, unsafe-pattern scan); `tests/test_cupel_static.py` with negative tests that break a copy and require failure.
- Adapters: Claude Code (primary; `.claude/agents/cupel/` mirror and `CLAUDE.md` block), Codex and other `AGENTS.md` readers (routing section plus portable protocol), portable chat kernel and four-file knowledge bundle for Claude Projects, ChatGPT Projects, and generic LLMs; optional agent-teams note marked Unverified.
- Pointer edits to `CLAUDE.md`, `AGENTS.md`, `README.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/harnesses.md`; no change under `skills/`, `scripts/`, `tests/`, `schemas/`, `.github/`.

## 0.1.0 - 2026-09-25 (not in history)

Phase 1 implementation of the accepted design (90 files) written and statically validated inside a Claude Code cloud session on branch `claude/sharp-tesla-bj3jv8` at `2b47129`; never committed or pushed; lost with the container. Its manifest and restore notes survive at the private artifact referenced in `docs/rebuild-notes.md`. Nothing from it is in this repository's history.
