# Scorecard - word-wrap

Judge: example judge (canned, so the demo runs with no model calls)

## submission-1
Score: 6
Notes: Two clean passes - split into chunks, then join chunks into lines - and the join condition is easy to check by eye. But it slices words that exceed the width, which SPEC rule 3 forbids, and the slicing is silent: nothing in the code marks it as a decision. The error message names no value.

## submission-2
Score: 9
Notes: One loop, one buffer, one flush; it reads like the greedy rule it implements. The over-long word case falls out of the structure instead of being special-cased, and the comment says why that works. Boundary check first, with the offending value in the message.

## verdict
Winner: submission-2
Graft reviewed: yes
Graft notes: The loser's explicit chunk-then-join split would be the better shape if this ever grows a hyphenation mode, since breaking would become a real step rather than a bug. Nothing to graft for the task as specified.
