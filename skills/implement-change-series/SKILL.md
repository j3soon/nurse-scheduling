---
name: implement-change-series
description: Implement a user-authorized batch of small repository changes with an upfront plan and self-contained commits. Group related items, validate each slice, and maintain a reviewable commit series. Do not use for single changes, planning-only requests, or requests that do not authorize commits.
---

# Implement Change Series

Turn a batch of small changes into a coherent, verified commit series. Preserve
the user's requested scope and let repository instructions govern Git, testing,
and style details.

## Plan the series

Before editing:

1. Read the repository instructions and the instructions for every affected
   module.
2. Inspect the worktree, current branch, configured Git identity, and the narrow
   code paths likely involved. Record the current `HEAD` as the series base and
   preserve existing staged and unstaged state. Track each commit created for
   the series so unrelated commits can be excluded later.
3. Present a concise plan that maps the requested changes to proposed commits.
   Call out any grouping that depends on what the implementation reveals.

Choose commit boundaries by behavior and revertability:

- Combine changes that implement one user-visible behavior, share a mechanism
  and its representative usage, or require the same validation path.
- Separate changes that can be understood, validated, and reverted
  independently.
- Do not group items merely because they touch the same file or module.
- Do not force one commit per requested bullet when a smaller coherent grouping
  is easier to review.
- Keep tests and directly related documentation with the behavior they verify.

## Implement one slice at a time

For each planned commit:

1. Implement the smallest complete slice, including its necessary tests and
   documentation.
2. Run the narrow affected checks before committing. Confirm the command
   selected the intended tests because a successful run with every relevant
   test deselected is not validation. Diagnose missing tools or dependencies
   directly instead of rerunning a broad suite for more output.
3. Review the diff and whitespace. Stage only files and entries belonging to
   that slice.
4. Commit only after the slice is coherent and its affected checks pass. Follow
   the repository's identity, message, attribution, and post-commit inspection
   rules.

If inspection changes the natural grouping, briefly update the user before
proceeding. Do not accumulate work from later independent slices in an earlier
commit.

Check once whether repository wrapper commands honor path or test filters. If a
wrapper always runs a broad suite, use an allowed direct narrow command for each
slice and reserve the broad wrapper for final combined validation.

## Incorporate corrections safely

Apply feedback to uncommitted work directly. When feedback changes an existing
commit, create a corrective commit by default. Rewrite, amend, squash, or fold
history only when the user explicitly requests it.

For an authorized local history rewrite:

1. Immediately before rewriting, enumerate the complete commit path from the
   target through `HEAD` and ensure the worktree is suitable. Include commits
   added since the original task or plan.
2. Create a temporary recovery reference before changing history.
3. Fold the correction into the intended commit and replay descendants in their
   original order. If the correction was authored against the later tree,
   resolve it at the target to the behavior appropriate at that point and let
   descendants reapply their own changes.
4. Once the recovery reference contains the intended final content, compare the
   rewritten final tree with it and require no content difference. If the
   rewrite intentionally changes content, inspect and validate that difference.
5. Inspect every changed commit message that could now be inaccurate. Update a
   target subject or body whose scope changed. Confirm real paragraph breaks,
   required attribution, and nothing after the final attribution line.
6. Report the old-to-new hash mapping because all descendants may change. Remove
   the temporary recovery reference only after verification succeeds.

Never force-push rewritten history unless the user separately authorizes that
external change.

## Finish the batch

After the last slice:

1. Use the recorded commit list to identify every path affected by the series,
   then run appropriate combined validation. A contiguous series may use
   `base..HEAD`. If unrelated commits landed, derive the paths from the tracked
   commits instead. Do not rely on a helper that only sees uncommitted changes
   after the slices have already been committed.
2. Run the repository whitespace check over the contiguous series range or its
   tracked commits, then inspect the final worktree state.
3. Report the ordered commits, validation evidence, intentionally skipped
   expensive checks, and any remaining uncertainty.

Keep progress updates concise. The final report must stand alone without
requiring the user to reconstruct results from earlier updates.
