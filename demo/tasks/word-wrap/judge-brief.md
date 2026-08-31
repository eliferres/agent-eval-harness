# Judge brief: word-wrap

Written before either arm ran, so the bar cannot be bent to fit the
results.

**What good looks like here.** A greedy wrap is a ten-line function. The
best submission reads like the rule it implements: one loop, one buffer,
one flush. The interesting judgement is what happens at the edges the
spec names - a word longer than `width`, whitespace runs, `width` below
1 - and whether the code handles them where they arise rather than by
special-casing after the fact.

**Score 0-10.** 8+ means it would pass review unchanged. Below 5 means a
rewrite is cheaper than a fix.

**Weigh, in order:**

1. Correctness against every numbered rule in SPEC.md, edges included.
2. Readability: names that say what they hold, a loop you can follow once
   and trust.
3. Error handling at the boundary: `ValueError` raised with a message a
   caller can act on, and raised before any work is done.
4. Restraint: no class, no configuration, no abstraction the task did not
   ask for.

**Ignore:** formatting and import style, docstring length, and any guess
about who or what wrote a submission.
