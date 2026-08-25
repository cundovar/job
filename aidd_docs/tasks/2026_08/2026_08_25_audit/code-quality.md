---
name: audit
description: Code-quality audit of the AI CV generation prompts
argument-hint: N/A
---

# Codebase Audit: AI CV generation prompts

The four-agent design is well grounded, but education selection, score calibration, and revision traceability can be made more deterministic.

- **Date**: 2026-08-25
- **Scope**: `cv_generator/ai_agents.py`, prompt inputs, sanitizers, and focused tests
- **Health**: good
- **Findings**: 0 critical, 4 warning, 2 minor

## Findings

| Sev | Category | Location | Issue | Suggested fix | Effort |
| --- | --- | --- | --- | --- | --- |
| 🟡 | code-quality | `cv_generator/ai_agents.py:268` | `source_verite` omits `person`, including education and languages; the agents cannot reason over the complete candidate source. | Include a bounded `person` context, with contact data excluded where unnecessary. | S |
| 🟡 | code-quality | `cv_generator/cv_creator.py:80` | Education marked `only_if_relevant` is always removed before the AI draft and the sanitizer later preserves only that fixed list. Older relevant education can never be selected for a targeted CV. | Add an education-selection plan analogous to `experience_plan`, then sanitize by source identifiers. | M |
| 🟡 | code-quality | `cv_generator/ai_agents.py:219` | The reviewer must emit quality and ATS scores but receives no scoring rubric or anchors; scores can vary substantially between providers and runs. | Define weighted criteria, deductions, and score bands in the prompt or compute scores deterministically from structured findings. | S |
| 🟡 | code-quality | `cv_generator/job_analyzer.py:73` | The fallback plan gives fixed variant experiences priority even when the job is unrelated; smoke checks for accueil and logistics included the relevant legacy role but also filled slots with web roles. | Require a minimum relevance score for every experience and explicitly tell the analyzer not to fill all slots when fewer experiences are relevant. | M |
| 🟢 | code-quality | `cv_generator/ai_agents.py:241` | The reviser is not required to report which review problems it resolved, rejected, or could not resolve. Revision completeness is therefore hard to verify. | Give findings stable IDs and require a `resolution_log` in the reviser output. | M |
| 🟢 | code-quality | `tests/test_cv_generator.py:111` | The main pipeline test verifies agent order and generated files, but not prompt contracts or behavior under irrelevant/contradictory experience suggestions. | Add contract tests for required prompt clauses and adversarial fake-agent outputs. | M |

## Top actions

1. Make education a grounded, dynamically selectable part of the analysis plan; this resolves findings 1 and 2.
2. Add a minimum relevance threshold and allow short experience lists instead of filling with unrelated roles; this resolves finding 4.
3. Replace free-form reviewer scoring with an explicit weighted rubric, then add revision traceability and adversarial tests; this resolves findings 3, 5, and 6.

## Coverage

- **Scanned**: code-quality
- **Skipped**: architecture, security, dependencies, performance, tests, and UI were outside the requested prompt-quality scope
