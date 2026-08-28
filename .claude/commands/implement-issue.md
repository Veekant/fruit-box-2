---
description: Plan, implement, and open a PR for a GitHub issue, with approval gates at each stage. Planning is delegated to the opus-planner subagent; implementation and PR writeup run on this command's model.
allowed-tools: Read, Edit, Write, Bash(gh:*), Bash(git:*), Task
argument-hint: [issue-number]
model: sonnet
---

I want you to implement GitHub issue #$ARGUMENTS for this project. Work in the following stages, and STOP at the end of each stage to wait for my explicit approval before moving to the next one. Do not skip ahead or combine stages, even if the work seems small.

## Stage 1: Plan

1. Delegate this stage to the `opus-planner` subagent via the Task tool, passing it the issue number $ARGUMENTS. It will read SPEC.md, fetch the issue, investigate the codebase, and return a plan covering: high-level explanation, files/functions to create or modify, ambiguities to resolve, and a testing plan.
2. Present that plan to me exactly as returned (don't summarize or compress it away) and STOP. Do not create a branch, write code, or run any git/gh commands yet.

## Stage 2: Implementation (only after I approve the plan, or after I give you changes and the plan has been updated accordingly — re-delegate to `opus-planner` for any substantive revision, don't patch the plan yourself)

1. Create a new branch named `issue-$ARGUMENTS-<short-description>`.
2. Implement the feature according to the approved plan, resolving ambiguities the way we agreed. If you discover partway through that the plan doesn't hold up (missing case, wrong assumption), stop and flag it to me rather than improvising past it.
3. Write and run the tests from the testing plan; make sure they pass. Run the existing test suite too, to check for regressions.
4. Summarize what you implemented, what you tested, and the results (pass/fail, coverage of edge cases). If anything deviated from the approved plan, call that out explicitly and why.
5. STOP. Do not open a pull request yet.

## Stage 3: Pull request (only after I approve the implementation, or after I give you changes and you've made them)

1. Push the branch.
2. Open a pull request via `gh pr create` that references and closes the issue (e.g. "Closes #$ARGUMENTS"), with a description summarizing the change, how it was tested, and any notable decisions from Stage 1's ambiguities section.
3. Give me the PR link and STOP. Do not merge it yourself.

Wait for my go-ahead before starting Stage 1. Confirm you understand this three-stage, approval-gated process before beginning.