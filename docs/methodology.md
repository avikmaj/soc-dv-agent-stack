# Methodology

## Lifecycle

1. Establish specification baseline, assumptions, risks, and configuration space.
2. Create requirement IDs and verification features.
3. Choose checking methods: simulation, assertion, formal, static, software-driven, emulation, or review.
4. Define stimulus, checks, coverage, negative cases, and evidence.
5. Implement in reusable layers with configuration separated from behavior.
6. Execute deterministic smoke, feature, stress, error, performance, and regression tiers.
7. Triage failures using first-divergence evidence.
8. Close requirements and coverage; review exclusions and waivers.
9. Audit signoff evidence and residual risk.

## Quality principles

- Requirement closure is more important than raw test count.
- Functional coverage measures intent only when bins map to requirements and illegal/impossible cases are controlled.
- Assertions and scoreboards complement rather than replace one another.
- A reusable VIP separates protocol semantics, transport, configuration, coverage, checking, and integration policy.
- SoC verification combines block reuse with software-driven scenarios and end-to-end data/control-flow checking.
