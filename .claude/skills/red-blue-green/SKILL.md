---
name: red-blue-green
description: Enforces the Red-Blue-Green TDD cycle (RED failing test, GREEN minimal implementation, BLUE refactor) when writing or changing code. Use whenever implementing a feature, fixing a bug, or refactoring in a project with this skill installed.
---

# Red-Blue-Green

A strict TDD cycle in three phases. Every behavior change goes through all three, in order, one test at a time.

## The cycle

1. **RED** - Write ONE small test that describes the next behavior you need. Run it. It must fail. A test that passes immediately is worthless: it proves nothing and tests nothing new. If it can't fail, it is not a test - fix it or replace it.
2. **GREEN** - Write the MINIMUM code that makes that test pass. No features you don't need, no "while I'm here" changes, no refactoring. Run the suite. All tests must pass.
3. **BLUE** - With the suite green, refactor: rename, extract, simplify, remove duplication. Behavior must not change. Re-run after every refactor step; the suite stays green.

Commit at every GREEN (and optionally at the end of BLUE). Then loop back to RED for the next behavior.

## Rules

- Never write implementation code while no failing test exists.
- One test at a time. Many small cycles beat one big one.
- The suite's green state is the only definition of "done" for a step.
- If a previously passing test breaks, fixing it outranks everything else. Never delete or weaken a test to get green.
- If you cannot write a test first (spike/exploration), say so explicitly, time-box the spike, and throw the spike code away - the real implementation still goes through the cycle.

## Enforcement

This skill ships with a companion hook (`hooks/rbg_gate.py`) that runs your test suite after every file edit and tells you the current RBG state (RED confirmed / still RED / GREEN / violation). When you see its guidance, act on it immediately - do not argue with a passing test you did not just watch fail.
