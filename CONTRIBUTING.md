# Contributing

1. Open an issue describing the DV problem, affected domain, and expected artifact.
2. Create or edit only the canonical `skills/` source.
3. Run `python scripts/sync_adapters.py`.
4. Run `python scripts/validate.py` and `python -m unittest discover -s tests -v`.
5. Submit a focused pull request with threat, license, and methodology implications.

Skills must be vendor-neutral, evidence-gated, non-destructive by default, and free of employer-confidential or copied proprietary material. A new skill requires: Purpose, Inputs, Workflow, Checks, Deliverables, Evidence Gate, Stop Conditions, and Safety sections.
