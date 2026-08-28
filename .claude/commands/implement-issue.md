---
description: Plan, implement, and open a PR for a GitHub issue, with approval gates at each stage. Planning and PR writeup run on this command's model; coding is delegated to the opus-coder subagent.
allowed-tools: Read, Bash(gh:*), Bash(git:*), Task
argument-hint: [issue-number]
model: sonnet
---

I want you to implement GitHub issue #$ARGUMENTS for this project. Work in the following stages, and STOP at the end of each stage to wait for my explicit approval before moving to the next one. Do not skip ahead or combine stages, even if the work seems small.

## Stage 1: Plan

1. Read SPEC.md in full first, before doing anything else, so you have the complete project context (not just the section relevant to this issue).
2. Fetch the issue details with `gh issue view $ARGUMENTS` and re-read the specific section(s) of SPEC.md that it maps to.
3. Look at the current state of the codebase (relevant existing files/modules) so the plan is grounded in what's actually there, not assumptions.
4. Produce a written plan with these sections:
   1. **High-level explanation** — what you're building and how it fits into the existing architecture, in plain language.
   2. **Files / functions to create or modify** — a concrete list, with a one-line purpose for each (e.g. `solver/enumerate.py: find_legal_moves() — new`).
   3. **Ambiguities to resolve** — anything the issue or spec doesn't fully pin down that affects the implementation (naming, edge cases, exact function signatures, data shapes). Flag these explicitly rather than silently picking an interpretation. If there are none, say so rather than skipping the section.
   4. **Testing plan** — what test cases you'll write (unit tests, edge cases, property-based checks if relevant), which test file(s) they'll live in, and how you'll verify the feature works end-to-end.
5. Present this plan to me and STOP. Do not create a branch, write code, or run any git/gh commands yet.

## Stage 2: Implementation (only after I approve the plan, or after I give you changes and you've incorporated them)

1. Delegate this stage to the `opus-coder` subagent via the Task tool. Give it: the issue number and description, the relevant SPEC.md section(s), and the full approved plan (including the resolved ambiguities and testing plan) exactly as approved — do not let it re-derive or re-interpret the plan itself.
2. The subagent will create a branch, implement the feature, write and run the tests, and report back a summary (what was implemented, what was tested, pass/fail results, any deviations from the plan).
3. Relay that summary to me. If the subagent reported deviations from the plan, call them out clearly.
4. STOP. Do not open a pull request yet.

## Stage 3: Pull request (only after I approve the implementation, or after I give you changes — which may mean re-delegating a fix to `opus-coder` and re-confirming with me before proceeding)

1. Push the branch.
2. Open a pull request via `gh pr create` that references and closes the issue (e.g. "Closes #$ARGUMENTS"), with a description summarizing the change, how it was tested, and any notable decisions from Stage 1's ambiguities section.
3. Give me the PR link and STOP. Do not merge it yourself.

Wait for my go-ahead before starting Stage 1's investigation. Confirm you understand this three-stage, approval-gated process before beginning.