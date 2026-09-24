# Evaluation Framework

Score each skill execution from 0 to 2 on: requirement fidelity, technical correctness, traceability, tool reproducibility, uncertainty handling, safety, reuse, and reviewability.

A release candidate must pass golden tasks for:

- IP: register-controlled datapath with interrupts and error injection.
- Subsystem: DMA plus memory/interconnect and reset/clock crossings.
- SoC: software boot, interrupts, security/firewall, and end-to-end traffic.
- NoC: ordering, QoS, backpressure, congestion, fairness, and deadlock risks.
- VIP: active/passive modes, responder, protocol errors, coverage, and portability.

No task passes solely from generated prose. At least one machine-checkable artifact or current tool result is required for implementation tasks.
